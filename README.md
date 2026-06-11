# You Hit a WHAT — automated Instagram poster

A small, free, self-hosted pipeline: you (or your submitters) drop content into a
queue via the dashboard, a bot writes a caption in the house voice and posts it to
Instagram once a day from GitHub Actions. Everything lives in this repo — no
servers, no database.

```
dashboard/index.html   ← claims-desk dashboard (host anywhere static, e.g. Netlify)
bot/post_bot.py        ← posting bot (runs on GitHub Actions)
.github/workflows/post.yml
queue.json             ← the content queue (the dashboard and bot share it)
media/                 ← images/videos uploaded via the dashboard
```

## Setup checklist

### 1. Instagram / Meta (~30 min, the only annoying part)
1. Convert the Instagram account to **Business** or **Creator** (app → Settings →
   Account type).
2. Create a **Facebook Page** and link the IG account to it.
3. Go to https://developers.facebook.com → create an app (type: Business).
4. Add the **Instagram Graph API** product. In the Graph API Explorer, grant
   `instagram_basic`, `instagram_content_publish`, `pages_read_engagement`.
5. Generate a token, then exchange it for a **long-lived token** (60 days; you'll
   refresh it occasionally). Save it — this is `IG_ACCESS_TOKEN`.
6. Get your IG user id: `GET /me/accounts` → page id → `GET /{page-id}?fields=
   instagram_business_account`. That id is `IG_USER_ID`.

### 2. GitHub
1. Create a **public** repo with these files. (Public matters: Instagram fetches
   media by URL, and raw.githubusercontent.com URLs are only public in public
   repos. Don't put anything private in here — tokens go in Secrets, never in code.)
2. Repo → Settings → Secrets and variables → Actions → add:
   - `IG_USER_ID`
   - `IG_ACCESS_TOKEN`
   - `ANTHROPIC_API_KEY` (from https://console.anthropic.com)
3. Actions tab → enable workflows. You can fire a test post any time with
   **Run workflow** on `post-to-instagram`.

### 3. Dashboard
1. Create a **fine-grained personal access token** (GitHub → Settings → Developer
   settings) scoped to **this one repo**, permission: **Contents: read & write**.
2. Open `dashboard/index.html` — locally in a browser is fine, or drag the
   `dashboard` folder into Netlify Drop for a hosted version.
3. Enter owner / repo / branch / token and hit *Open the case file*. The token is
   held in memory only; you paste it each session.

## How it flows
1. **File a claim** in the dashboard: upload an image/video (stored in `media/`,
   public raw URL generated automatically) or paste a public URL; add the car
   model and a credit line.
2. New claims land as **pending**. Review, optionally write a caption override,
   hit **Approve**. (Blank caption = the bot writes one at post time.)
3. Each scheduled run, the bot posts the **oldest approved** item, appends the
   credit line, and stamps it **posted** with the timestamp and caption used.

## Notes & limits
- **Posting cadence**: one item per workflow run. Add more `cron:` lines in
  `post.yml` for more posts per day. Instagram's API caps content publishing at
  50 posts per 24h — you will not get anywhere near it.
- **Reels**: Instagram is picky about video sources. If a Reel fails from a
  raw.githubusercontent.com URL, host the video on a free Cloudinary account and
  paste that URL instead. Specs: MP4, 9:16 recommended, ≤ 90s for best results.
- **File sizes**: the dashboard uploads via the GitHub API — fine for images and
  short clips; very large videos belong on Cloudinary anyway.
- **Token refresh**: the long-lived IG token expires after ~60 days. Refresh it
  (`GET /oauth/access_token?grant_type=fb_exchange_token...`) and update the secret.
- **Content**: only queue media you made, generated, or have permission to post.
  The `source_credit` field is for crediting people who said yes — credit alone
  isn't permission.
