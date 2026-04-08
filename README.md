# SocialMediaPoster

Automate video uploads to **YouTube** and **TikTok** from the command line. Populate all
metadata (title, description, hashtags, tags, category, thumbnail) and either post
immediately or schedule for a specific date and time.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Step 1 — Set up YouTube credentials](#step-1--set-up-youtube-credentials)
4. [Step 2 — Set up TikTok credentials](#step-2--set-up-tiktok-credentials)
5. [Step 3 — Configure your .env file](#step-3--configure-your-env-file)
6. [Step 4 — Authorize with each platform](#step-4--authorize-with-each-platform)
7. [Uploading a video](#uploading-a-video)
8. [Scheduling a post](#scheduling-a-post)
9. [Using a metadata file](#using-a-metadata-file)
10. [All CLI flags](#all-cli-flags)
11. [YouTube category IDs](#youtube-category-ids)
12. [Platform differences](#platform-differences)
13. [Token management](#token-management)

---

## Requirements

- Python 3.11 or later
- A Google account with a YouTube channel
- A TikTok developer account (only needed if posting to TikTok)

---

## Installation

```bash
# Clone the repo and enter the directory
cd SocialMediaPoster

# Install dependencies
pip install -r requirements.txt

# Copy the credentials template
cp .env.example .env
```

---

## Step 1 — Set up YouTube credentials

You need to create an OAuth 2.0 app in Google Cloud Console. This is free and takes
about 5 minutes.

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or select an existing one)
3. Go to **APIs & Services → Library** and enable the **YouTube Data API v3**
4. Go to **APIs & Services → Credentials**
5. Click **Create Credentials → OAuth 2.0 Client ID**
6. Choose **Desktop app** as the application type
7. Click **Download JSON** — this is your `client_secrets.json` file
8. Move that file into the `SocialMediaPoster/` folder (next to `main.py`)

> **Note:** The first time you authorize, Google will show a warning saying the app is
> "unverified". This is normal for personal apps — click **Advanced → Go to (app) anyway**.

---

## Step 2 — Set up TikTok credentials

You need a TikTok developer app with the Content Posting API enabled.

1. Go to [developers.tiktok.com](https://developers.tiktok.com) and log in
2. Click **Manage Apps → Create app**
3. Fill in the app name and description (anything works for personal use)
4. Under **Products**, add **Content Posting API**
5. Under **Redirect URIs**, add exactly: `http://localhost:8080/callback`
6. Save the app — you'll see your **Client Key** and **Client Secret** on the app page

> **Note:** TikTok may put new apps in "sandbox" mode initially, which limits uploads
> to your own account only. That's fine for personal use.

---

## Step 3 — Configure your .env file

Open the `.env` file you copied and fill it in:

```ini
# Path to the client_secrets.json you downloaded from Google Cloud Console
YOUTUBE_CLIENT_SECRETS_PATH=client_secrets.json

# From your TikTok developer app page
TIKTOK_CLIENT_KEY=your_client_key_here
TIKTOK_CLIENT_SECRET=your_client_secret_here

# Must match the redirect URI you registered in your TikTok app
TIKTOK_REDIRECT_URI=http://localhost:8080/callback

# Where OAuth tokens are cached — leave this as-is
TOKEN_DIR=tokens
```

---

## Step 4 — Authorize with each platform

Run this once per platform. It opens a browser window for you to log in and grant
permission. After you approve, a token file is saved locally so you don't have to
do this again.

**YouTube:**
```bash
python main.py auth --platform youtube
```
A browser tab opens → log into your Google account → click **Allow**.
You'll see: `[INFO]  YouTube authorization complete.`

**TikTok:**
```bash
python main.py auth --platform tiktok
```
A browser tab opens → log into TikTok → click **Authorize**.
You'll see: `[INFO]  TikTok authorization complete.`

Tokens are saved to the `tokens/` folder and automatically refreshed when they expire.
You only need to re-run `auth` if you revoke access or switch accounts.

---

## Uploading a video

### Post immediately to YouTube

```bash
python main.py upload \
  --video my_video.mp4 \
  --platforms youtube \
  --title "My Awesome Video" \
  --description "Check out this video about Python automation!" \
  --tags python automation tutorial \
  --category 28 \
  --thumbnail thumb.jpg \
  --privacy public
```

### Post immediately to TikTok

```bash
python main.py upload \
  --video my_video.mp4 \
  --platforms tiktok \
  --title "My Awesome Video" \
  --description "Check out this video!" \
  --tags python coding fyp \
  --privacy public
```

Tags are automatically converted to `#hashtags` and appended to the description on TikTok.

### Post to both platforms at once

```bash
python main.py upload \
  --video my_video.mp4 \
  --platforms youtube tiktok \
  --title "My Awesome Video" \
  --description "Check out this video!" \
  --tags python coding tutorial \
  --thumbnail thumb.jpg \
  --privacy public
```

The script uploads to YouTube first, then TikTok. A progress bar is shown for each upload.

---

## Scheduling a post

Add `--schedule` with a date and time. The video is uploaded now but published later.

```bash
python main.py upload \
  --video my_video.mp4 \
  --platforms youtube tiktok \
  --title "Scheduled Release" \
  --description "This drops at 9am!" \
  --tags announcement \
  --schedule "2026-04-15 09:00 UTC"
```

**Accepted time formats:**

| Format | Example |
|--------|---------|
| Date + time + timezone abbreviation | `"2026-04-15 09:00 UTC"` |
| Date + time + timezone abbreviation | `"2026-04-15 09:00 EST"` |
| ISO 8601 with offset | `"2026-04-15T09:00:00+05:30"` |
| Date + time (assumes UTC) | `"2026-04-15 09:00"` |

**Supported timezone abbreviations:** UTC, GMT, EST, EDT, CST, CDT, MST, MDT, PST, PDT,
BST, CET, IST, JST, AEST

**Platform scheduling rules:**

| Platform | How it works | Constraints |
|----------|-------------|-------------|
| YouTube | Video uploads as private, auto-publishes at the scheduled time | Must be any future time |
| TikTok | Post is queued and released at the scheduled time | Must be 10 minutes – 20 days from now |

---

## Using a metadata file

Instead of typing all your details on the command line every time, you can store them
in a YAML or JSON file and reuse it.

### YAML example (`meta.yaml`)

```yaml
title: My Awesome Video
description: Check out this video about Python automation!
tags:
  - python
  - automation
  - tutorial
category_id: "28"
thumbnail_path: thumb.jpg
privacy: public
```

### JSON example (`meta.json`)

```json
{
  "title": "My Awesome Video",
  "description": "Check out this video about Python automation!",
  "tags": ["python", "automation", "tutorial"],
  "category_id": "28",
  "thumbnail_path": "thumb.jpg",
  "privacy": "public"
}
```

### Using the file

```bash
python main.py upload \
  --video my_video.mp4 \
  --platforms youtube tiktok \
  --metadata-file meta.yaml
```

### Overriding individual fields

CLI flags always override the metadata file. Useful when you want to reuse the same
file but change the title for a specific upload:

```bash
python main.py upload \
  --video my_video.mp4 \
  --platforms youtube \
  --metadata-file meta.yaml \
  --title "Different Title This Time" \
  --privacy private
```

---

## All CLI flags

### `upload` command

| Flag | Required | Description |
|------|----------|-------------|
| `--video PATH` | Yes | Path to the video file (mp4, mov, avi, mkv, webm, etc.) |
| `--platforms` | Yes | One or more of: `youtube` `tiktok` |
| `--title TEXT` | Yes* | Video title. *Required unless in `--metadata-file` |
| `--description TEXT` | No | Video description |
| `--tags TAG [TAG ...]` | No | Tags/keywords. TikTok: appended as #hashtags |
| `--category ID` | No | YouTube category ID. Default: `22`. Ignored on TikTok |
| `--thumbnail PATH` | No | Thumbnail image (jpg/png). YouTube only |
| `--privacy` | No | `public` (default), `private`, or `unlisted` |
| `--schedule DATETIME` | No | Schedule for a future date instead of posting now |
| `--metadata-file PATH` | No | YAML or JSON file with metadata (CLI flags override it) |
| `--tiktok-cover-ms MS` | No | TikTok only — video frame offset (ms) to use as cover. Default: `0` |

### `auth` command

| Flag | Required | Description |
|------|----------|-------------|
| `--platform` | Yes | `youtube` or `tiktok` |

---

## YouTube category IDs

Pass one of these numbers to `--category`:

| ID | Category |
|----|----------|
| 1 | Film & Animation |
| 2 | Autos & Vehicles |
| 10 | Music |
| 15 | Pets & Animals |
| 17 | Sports |
| 20 | Gaming |
| 22 | People & Blogs *(default)* |
| 23 | Comedy |
| 24 | Entertainment |
| 25 | News & Politics |
| 26 | Howto & Style |
| 27 | Education |
| 28 | Science & Technology |
| 29 | Nonprofits & Activism |

---

## Platform differences

| Feature | YouTube | TikTok |
|---------|---------|--------|
| Custom thumbnail | Supported (`--thumbnail`) | Not supported via API — use `--tiktok-cover-ms` to pick a frame |
| Category | Supported (`--category`) | Not available in TikTok API |
| `unlisted` privacy | Supported | Mapped to "mutual followers only" |
| Scheduling | Any future date/time | 10 minutes – 20 days from now |
| Tags | Keyword tags on the video | Appended as #hashtags in the description |
| Upload method | Resumable chunked upload | 10 MB chunked upload |

---

## Token management

OAuth tokens are stored in the `tokens/` folder and **never committed to git**.

| File | Contains |
|------|----------|
| `tokens/youtube_token.json` | Google OAuth2 access + refresh token |
| `tokens/tiktok_token.json` | TikTok access + refresh token + expiry |

**Automatic refresh:** Tokens are refreshed silently in the background whenever they
expire. You don't need to do anything.

**Manual re-auth** (e.g. if you revoke access or switch accounts):
```bash
python main.py auth --platform youtube
python main.py auth --platform tiktok
```

Token files are created with `600` permissions (owner read/write only) to protect your
credentials at rest.
