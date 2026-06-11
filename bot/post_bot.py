"""
You Hit a WHAT — Instagram posting bot.

Runs on a schedule (GitHub Actions). Each run:
  1. Loads queue.json from the repo root.
  2. Takes the oldest item with status "approved".
  3. Generates a caption with the Anthropic API (unless caption_override is set).
  4. Publishes it to Instagram via the official Graph API (image post or Reel).
  5. Marks the item "posted" and saves queue.json (the workflow commits it).

Required environment variables (set as GitHub Actions secrets):
  IG_USER_ID         - your Instagram Business/Creator account's IG User ID
  IG_ACCESS_TOKEN    - long-lived Graph API access token
  ANTHROPIC_API_KEY  - for caption generation
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

GRAPH = "https://graph.facebook.com/v21.0"
QUEUE_PATH = os.path.join(os.path.dirname(__file__), "..", "queue.json")

IG_USER_ID = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

CAPTION_SYSTEM_PROMPT = """You write captions for a comedy Instagram account called
"You Hit a WHAT" about absurd accidents involving extremely expensive cars.

The signature joke format: the moment an insurance agent, a parent, a spouse, or
the driver themselves finds out WHICH car was hit. Disbelief, financial dread,
deadpan acceptance.

Rules:
- 1-2 short lines max. Lowercase is fine. Deadpan beats wacky.
- Reference the specific car when given.
- No emojis except at most one, used like punctuation.
- End with 3-5 niche hashtags (mix of #youhitawhat #carcrash #insurance plus
  car-specific ones).
- Never joke about injuries or victims. The joke is always the money/the car.

Respond with ONLY the caption text, nothing else."""


def generate_caption(car_model: str) -> str:
    """Ask Claude for a caption in the house voice."""
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 300,
            "system": CAPTION_SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": f"Write a caption. The car involved: {car_model or 'an extremely expensive car'}.",
                }
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(b.get("text", "") for b in data["content"]).strip()


def graph_post(path: str, payload: dict) -> dict:
    payload = {**payload, "access_token": IG_ACCESS_TOKEN}
    r = requests.post(f"{GRAPH}/{path}", data=payload, timeout=120)
    if not r.ok:
        print("Graph API error:", r.status_code, r.text, file=sys.stderr)
    r.raise_for_status()
    return r.json()


def graph_get(path: str, params: dict) -> dict:
    params = {**params, "access_token": IG_ACCESS_TOKEN}
    r = requests.get(f"{GRAPH}/{path}", params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def wait_until_ready(creation_id: str, max_wait_s: int = 300) -> None:
    """Reels are processed asynchronously; poll until the container is ready."""
    waited = 0
    while waited < max_wait_s:
        status = graph_get(creation_id, {"fields": "status_code"}).get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError("Instagram failed to process the video.")
        time.sleep(10)
        waited += 10
    raise TimeoutError("Video container was not ready in time.")


def publish_item(item: dict, caption: str) -> str:
    """Create a media container and publish it. Returns the published media ID."""
    if item["type"] == "reel":
        container = graph_post(
            f"{IG_USER_ID}/media",
            {
                "media_type": "REELS",
                "video_url": item["media_url"],
                "caption": caption,
                "share_to_feed": "true",
            },
        )
        wait_until_ready(container["id"])
    else:
        container = graph_post(
            f"{IG_USER_ID}/media",
            {"image_url": item["media_url"], "caption": caption},
        )

    published = graph_post(
        f"{IG_USER_ID}/media_publish", {"creation_id": container["id"]}
    )
    return published["id"]


def main() -> None:
    with open(QUEUE_PATH, "r", encoding="utf-8") as f:
        queue = json.load(f)

    approved = [i for i in queue["items"] if i.get("status") == "approved"]
    if not approved:
        print("Nothing approved in the queue. Skipping this run.")
        return

    approved.sort(key=lambda i: i.get("added_at", ""))
    item = approved[0]
    print(f"Posting claim {item['id']}: {item.get('car_model', '?')} ({item['type']})")

    caption = (item.get("caption_override") or "").strip()
    if not caption:
        caption = generate_caption(item.get("car_model", ""))

    credit = (item.get("source_credit") or "").strip()
    if credit:
        caption = f"{caption}\n\n📸 {credit}"

    media_id = publish_item(item, caption)

    item["status"] = "posted"
    item["posted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    item["posted_caption"] = caption
    item["ig_media_id"] = media_id

    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Posted. IG media id: {media_id}")


if __name__ == "__main__":
    main()
