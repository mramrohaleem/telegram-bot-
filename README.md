# Telegram Media Downloader Bot

This repository is a seed project for a **Telegram bot** that helps channel owners quickly download and re-upload media (video/audio) from the web and YouTube.

The bot should:
- Receive a **URL** (YouTube or other supported websites).
- Let the user choose **format & quality** (video / audio, resolution / bitrate where possible).
- Download the file to the server.
- Send the resulting file back to the user on Telegram.
- Be optimized for **fast publishing to Telegram channels**.

---

## High-level Requirements

1. **Platforms & Sources**
   - YouTube (videos, shorts, playlists if possible).
   - Direct media URLs (mp4, mp3, etc.).
   - Other common streaming sites supported by `yt-dlp`.

2. **Bot Features (User side)**
   - `/start` → short intro and how to use the bot.
   - User sends a **link** → bot:
     - Validates the URL.
     - Fetches available formats/qualities (via `yt-dlp` or similar).
     - Replies with inline buttons:
       - Example: “Video 1080p”, “Video 720p”, “Audio MP3 128kbps”, etc.
     - After user chooses:
       - Download the selected format.
       - Send file back to the user as:
         - **Video** (streamable in Telegram).
         - **Audio** (as voice / audio file).
   - Handle basic errors:
     - Invalid URL.
     - Unsupported site.
     - File too large for Telegram limits.

3. **Performance & UX**
   - Show status messages:
     - “Fetching info…”
     - “Downloading…”
     - “Uploading to Telegram…”
   - If download is too big or fails → send clear error message.

---

## Tech Stack Preference

I prefer **Python** for the bot, but Node.js is also acceptable if better for Vercel.

### Option A – Python
- Telegram framework: `aiogram` or `python-telegram-bot`.
- Downloader: `yt-dlp`.
- Entry file (example): `bot/main.py`.

### Option B – Node.js
- Telegram framework: `telegraf` or `grammY`.
- Downloader: `yt-dlp` called via child process or a Node wrapper.
- Entry file (example): `src/index.ts` or `src/index.js`.

---

## Deployment Notes (Vercel)

- The project will run on **Vercel**.
- Bot should be implemented using **webhook** mode (not long polling), with a single HTTP endpoint:
  - Example path: `/api/telegram-webhook`.
- There should be a simple way to set the webhook URL once deployed.

You can assume:
- I will provide the **Telegram Bot Token** as an environment variable.
- I understand that serverless filesystem is **ephemeral**, so temporary files are ok as long as they are cleaned or small.

---

## Environment Variables

Create a `.env.example` file with:

```env
TELEGRAM_BOT_TOKEN=your-telegram-bot-token-here
YT_DLP_BINARY=/usr/bin/yt-dlp  # or leave empty if installed via pip/node
