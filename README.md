# Telegram Media Downloader Bot

This repository is a production-ready **Telegram bot** that helps channel owners download, edit, and re-upload media using aiogram v3, yt-dlp, and ffmpeg.

## How to run

1. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in `TELEGRAM_BOT_TOKEN`.

3. Run the bot:

   ```bash
   python -m bot.main
   ```
