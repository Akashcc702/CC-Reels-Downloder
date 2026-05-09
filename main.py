import os
import re
import asyncio
import tempfile
import logging
from threading import Thread

from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from downloader import download_video, get_file_size_mb, is_too_large

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Flask Keep-Alive ─────────────────────────────────────────────────────────
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot is running!"

def keep_alive():
    def run():
        port = int(os.environ.get("PORT", 8080))
        try:
            flask_app.run(host="0.0.0.0", port=port)
        except OSError as e:
            logger.warning("Web server could not start on port %d: %s", port, e)
    Thread(target=run, daemon=True).start()

# ─── Platform Detection ───────────────────────────────────────────────────────
PLATFORMS = {
    "YouTube":   re.compile(
        r"(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)"
        r"/(watch\?v=|shorts/|embed/|v/|.+\?v=)?[a-zA-Z0-9_-]|"
        r"(https?://)?(www\.)?youtu\.be/[a-zA-Z0-9_-]",
        re.IGNORECASE
    ),
    "Instagram": re.compile(
        r"(https?://)?(www\.)?instagram\.com/(p|reel|tv|reels)/[a-zA-Z0-9_-]+",
        re.IGNORECASE
    ),
    "TikTok":    re.compile(
        r"(https?://)?(www\.|vm\.)?tiktok\.com/",
        re.IGNORECASE
    ),
    "Twitter/X": re.compile(
        r"(https?://)?(www\.)?(twitter\.com|x\.com)/\w+/status/\d+",
        re.IGNORECASE
    ),
    "Facebook":  re.compile(
        r"(https?://)?(www\.|web\.|m\.)?facebook\.com/.+/videos?/|"
        r"(https?://)?fb\.watch/",
        re.IGNORECASE
    ),
}

PLATFORM_EMOJI = {
    "YouTube":   "▶️",
    "Instagram": "📸",
    "TikTok":    "🎵",
    "Twitter/X": "🐦",
    "Facebook":  "📘",
}

def detect_platform(text: str) -> str | None:
    for name, pattern in PLATFORMS.items():
        if pattern.search(text):
            return name
    return None

def is_valid_url(text: str) -> bool:
    return detect_platform(text) is not None

# ─── Command Handlers ─────────────────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *Welcome to Video Downloader Bot!*\n\n"
        "I can download videos from:\n"
        "▶️ *YouTube* — videos, shorts & music\n"
        "📸 *Instagram* — reels, posts & IGTV\n"
        "🎵 *TikTok* — videos\n"
        "🐦 *Twitter / X* — videos & GIFs\n"
        "📘 *Facebook* — videos & reels\n\n"
        "📌 *How to use:*\n"
        "Simply send me a link and I'll download it for you!\n\n"
        "⚠️ *Limits:*\n"
        "• Max file size: 50 MB\n"
        "• Only public videos can be downloaded\n\n"
        "Send a link to get started 🚀",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Help & Commands*\n\n"
        "/start — Show welcome message\n"
        "/help — Show this help\n\n"
        "*Supported platforms:*\n"
        "• YouTube, YouTube Shorts, YouTube Music\n"
        "• Instagram (reels, posts, IGTV)\n"
        "• TikTok\n"
        "• Twitter / X\n"
        "• Facebook videos\n\n"
        "*Instagram / Facebook not downloading?*\n"
        "Add a `cookies.txt` file in the bot folder.\n"
        "Use the *'Get cookies.txt LOCALLY'* Chrome extension,\n"
        "log into Instagram, export cookies, and place the file next to `main.py`.\n\n"
        "*Troubleshooting:*\n"
        "• Make sure the video is public\n"
        "• Verify the link is correct\n"
        "• Some videos may be region-locked\n"
        "• File must be under 50 MB\n",
        parse_mode="Markdown"
    )

# ─── Main Message Handler ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import yt_dlp

    user_text = update.message.text.strip()

    if not is_valid_url(user_text):
        await update.message.reply_text(
            "❌ *Unsupported link!*\n\n"
            "Supported platforms:\n"
            "• YouTube / Shorts\n"
            "• Instagram (reel, post, IGTV)\n"
            "• TikTok\n"
            "• Twitter / X\n"
            "• Facebook\n\n"
            "Send /help for more info.",
            parse_mode="Markdown"
        )
        return

    platform = detect_platform(user_text)
    emoji    = PLATFORM_EMOJI.get(platform, "📥")

    status_msg = await update.message.reply_text(
        f"{emoji} *Downloading from {platform}...*\n\n"
        "⏳ Please wait, this may take a moment.",
        parse_mode="Markdown"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            loop       = asyncio.get_event_loop()
            video_path = await loop.run_in_executor(None, download_video, user_text, tmp_dir)

            if video_path is None or not os.path.exists(video_path):
                await status_msg.edit_text(
                    "❌ *Download failed!*\n\n"
                    "Could not download this content. It may be:\n"
                    "• Private or age-restricted\n"
                    "• Region-locked\n"
                    "• No longer available\n\n"
                    "For Instagram/Facebook, add `cookies.txt` — see /help",
                    parse_mode="Markdown"
                )
                return

            file_size_mb = get_file_size_mb(video_path)

            if is_too_large(video_path):
                await status_msg.edit_text(
                    f"⚠️ *File too large to send!*\n\n"
                    f"Video is *{file_size_mb:.1f} MB* (limit: 50 MB).\n"
                    "Please try a shorter clip.",
                    parse_mode="Markdown"
                )
                return

            await status_msg.edit_text("📤 *Uploading to Telegram...*", parse_mode="Markdown")

            with open(video_path, "rb") as vf:
                await update.message.reply_video(
                    video=vf,
                    caption=f"✅ Done! ({file_size_mb:.1f} MB)",
                    supports_streaming=True,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                )

            await status_msg.delete()

        except yt_dlp.utils.DownloadError as e:
            err = str(e).lower()
            if any(k in err for k in ["private", "login", "sign in", "cookie"]):
                msg = (
                    "🔒 *Login required!*\n\n"
                    "This content needs authentication.\n"
                    "Add `cookies.txt` to the bot folder — see /help"
                )
            elif any(k in err for k in ["not available", "removed", "deleted"]):
                msg = "🚫 *Content unavailable!*\n\nThis video has been removed."
            elif any(k in err for k in ["geo", "region", "country"]):
                msg = "🌍 *Region-locked!*\n\nNot available in this server's region."
            else:
                msg = (
                    "❌ *Cannot download this content.*\n\n"
                    f"`{str(e)[:200]}`\n\n"
                    "Try /help for troubleshooting tips."
                )
            await status_msg.edit_text(msg, parse_mode="Markdown")
            logger.warning("DownloadError for %s: %s", user_text, e)

        except Exception as e:
            await status_msg.edit_text(
                "⚠️ *Something went wrong!*\n\nPlease try again later.",
                parse_mode="Markdown"
            )
            logger.error("Unexpected error for %s: %s", user_text, e, exc_info=True)

# ─── Entry Point ──────────────────────────────────────────────────────────────
def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    keep_alive()
    logger.info("Starting Video Downloader Bot...")

    bot_app = ApplicationBuilder().token(token).build()
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running!")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
