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
    "YouTube": re.compile(
        r"(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)"
        r"/(watch\?v=|shorts/|embed/|v/|.+\?v=)?[a-zA-Z0-9_-]|"
        r"(https?://)?(www\.)?youtu\.be/[a-zA-Z0-9_-]",
        re.IGNORECASE
    ),
    "Instagram": re.compile(
        r"(https?://)?(www\.)?instagram\.com/(p|reel|tv|reels)/[a-zA-Z0-9_-]+",
        re.IGNORECASE
    ),
    "TikTok": re.compile(
        r"(https?://)?(www\.|vm\.)?tiktok\.com/",
        re.IGNORECASE
    ),
    "Twitter/X": re.compile(
        r"(https?://)?(www\.)?(twitter\.com|x\.com)/\w+/status/\d+",
        re.IGNORECASE
    ),
    "Facebook": re.compile(
        r"(https?://)?(www\.|web\.|m\.)?facebook\.com/.+/videos?/|"
        r"(https?://)?fb\.watch/",
        re.IGNORECASE
    ),
}

PLATFORM_EMOJI = {
    "YouTube": "▶️", "Instagram": "📸",
    "TikTok": "🎵", "Twitter/X": "🐦", "Facebook": "📘",
}

def detect_platform(text: str) -> str | None:
    for name, pattern in PLATFORMS.items():
        if pattern.search(text):
            return name
    return None

# ─── Command Handlers ─────────────────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ig_ready = "✅" if os.environ.get("INSTAGRAM_COOKIES") else "⚠️ (cookies not set)"
    await update.message.reply_text(
        "👋 *Welcome to Video Downloader Bot!*\n\n"
        "Supported platforms:\n"
        f"▶️ *YouTube* (Shorts, Music) — ✅\n"
        f"🎵 *TikTok* — ✅\n"
        f"🐦 *Twitter / X* — ✅\n"
        f"📸 *Instagram* (Reels, Posts) — {ig_ready}\n"
        f"📘 *Facebook* — {ig_ready}\n\n"
        "📌 Just send a link to download!\n\n"
        "⚠️ *Limits:* Max 50 MB, public videos only.",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Help*\n\n"
        "/start — Welcome message\n"
        "/help — This message\n\n"
        "*Instagram not working?*\n"
        "Set `INSTAGRAM_COOKIES` in Render → Environment Variables.\n"
        "See `HOW_TO_FIX_INSTAGRAM.md` for steps.\n\n"
        "*Troubleshooting:*\n"
        "• Video must be public\n"
        "• File must be under 50 MB\n"
        "• Some videos are region-locked\n",
        parse_mode="Markdown"
    )

# ─── Main Message Handler ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import yt_dlp

    user_text = update.message.text.strip()
    platform  = detect_platform(user_text)

    if not platform:
        await update.message.reply_text(
            "❌ *Unsupported link!*\n\n"
            "Supported: YouTube, Instagram, TikTok, Twitter/X, Facebook\n"
            "Send /help for info.",
            parse_mode="Markdown"
        )
        return

    emoji      = PLATFORM_EMOJI.get(platform, "📥")
    status_msg = await update.message.reply_text(
        f"{emoji} *Downloading from {platform}...*\n⏳ Please wait...",
        parse_mode="Markdown"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            loop       = asyncio.get_event_loop()
            video_path = await loop.run_in_executor(
                None, download_video, user_text, tmp_dir, platform
            )

            if video_path is None or not os.path.exists(video_path):
                await status_msg.edit_text(
                    "❌ *Download failed!*\n\n"
                    "Content may be private, removed, or region-locked.\n"
                    "For Instagram: set `INSTAGRAM_COOKIES` env var — see /help",
                    parse_mode="Markdown"
                )
                return

            file_size_mb = get_file_size_mb(video_path)
            if is_too_large(video_path):
                await status_msg.edit_text(
                    f"⚠️ *File too large!* ({file_size_mb:.1f} MB)\n"
                    "Telegram limit is 50 MB. Try a shorter clip.",
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
            if any(k in err for k in ["private", "login", "sign in", "cookie", "auth"]):
                msg = (
                    "🔒 *Login required!*\n\n"
                    "Set `INSTAGRAM_COOKIES` in Render Environment Variables.\n"
                    "See /help for steps."
                )
            elif any(k in err for k in ["not available", "removed", "deleted"]):
                msg = "🚫 *Content unavailable!* Video has been removed."
            elif any(k in err for k in ["geo", "region", "country"]):
                msg = "🌍 *Region-locked!* Not available in server's region."
            else:
                msg = f"❌ *Download error:*\n`{str(e)[:300]}`"
            await status_msg.edit_text(msg, parse_mode="Markdown")
            logger.warning("DownloadError for %s: %s", user_text, e)

        except Exception as e:
            await status_msg.edit_text(
                "⚠️ *Unexpected error!* Please try again later.",
                parse_mode="Markdown"
            )
            logger.error("Error for %s: %s", user_text, e, exc_info=True)

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
