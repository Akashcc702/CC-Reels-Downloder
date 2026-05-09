# 📥 Reels Downloader Bot

A Telegram bot that downloads videos from **YouTube** and **Instagram** and sends them back to you — powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp).

---

## 📁 Project Structure

```
.
├── main.py          # Telegram bot + Flask keep-alive server
├── downloader.py    # yt-dlp download logic
├── requirements.txt # Python dependencies
├── .env.example     # Environment variable template
└── README.md
```

---

## ⚡ Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```
> **Note:** `ffmpeg` must also be installed on your system for video merging.

### 2. Set your bot token
```bash
cp .env.example .env
# Edit .env and paste your TELEGRAM_BOT_TOKEN
```
Or set it directly as an environment variable:
```bash
export TELEGRAM_BOT_TOKEN="your_token_here"
```

### 3. Run the bot
```bash
python main.py
```

---

## 🤖 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and usage guide |
| `/help`  | Help and troubleshooting tips |

Just send any YouTube or Instagram link — the bot will download and send back the video.

---

## 🌐 Supported Platforms

- **YouTube** — `youtube.com/watch?v=...`, `youtu.be/...`, `youtube.com/shorts/...`
- **Instagram** — `instagram.com/reel/...`, `instagram.com/p/...`, `instagram.com/tv/...`

---

## ⚠️ Limits

- Max file size: **50 MB** (Telegram bot limit)
- Only **public** videos can be downloaded
- Some videos may be region-locked or require login

---

## ☁️ Deploying on Replit

1. Add `TELEGRAM_BOT_TOKEN` in the **Secrets** tab.
2. Set the run command to `python main.py`.
3. The built-in Flask server keeps the Repl alive automatically.
