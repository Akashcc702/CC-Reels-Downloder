import os
import re
import asyncio
import tempfile
import logging
from threading import Thread

from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from downloader import download_video, get_file_size_mb, is_too_large, cookies_status, FFMPEG_AVAILABLE

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
            logger.warning("Web server port %d: %s", port, e)
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
        r"(https?://)?(www\.)?instagram\.com/"
        r"([a-zA-Z0-9_.]+/)?(p|reel|tv|reels)/[a-zA-Z0-9_-]+",
        re.IGNORECASE
    ),
    "TikTok": re.compile(
        r"(https?://)?(www\.|vm\.|vt\.)?tiktok\.com/[@/]?[a-zA-Z0-9_@./-]+",
        re.IGNORECASE
    ),
    "Twitter/X": re.compile(
        r"(https?://)?(www\.)?(twitter\.com|x\.com)/",
        re.IGNORECASE
    ),
    "Facebook": re.compile(
        r"(https?://)?(www\.|web\.|m\.)?facebook\.com/"
        r"(share/[rv]/|.+/videos?/|watch|reel/|story\.php|permalink/)|"
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

# ─── Commands ─────────────────────────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ig_status = "✅" if os.environ.get("INSTAGRAM_COOKIES") else "⚠️ cookies not set"
    await update.message.reply_text(
        "👋 *Video Downloader Bot*\n\n"
        "▶️ YouTube & Shorts — ✅\n"
        "🎵 TikTok — ✅\n"
        "🐦 Twitter / X — ✅\n"
        f"📸 Instagram — {ig_status}\n"
        f"📘 Facebook — {ig_status}\n\n"
        "Just send a link!\n"
        "Use /debug to check bot status.",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Help*\n\n"
        "/start — Welcome\n"
        "/help — This message\n"
        "/debug — Check cookies & bot status\n\n"
        "*Instagram not working?*\n"
        "Set `INSTAGRAM_COOKIES` in Render → Environment.\n\n"
        "*Limits:* Max 50 MB, public videos only.",
        parse_mode="Markdown"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import yt_dlp
    from downloader import FFMPEG_AVAILABLE
    status = cookies_status()
    await update.message.reply_text(
        f"🔍 *Bot Debug Info*\n\n"
        f"*ffmpeg:* {'✅ available' if FFMPEG_AVAILABLE else '❌ not found'}\n"
        f"*Instagram Cookies:* {status}\n"
        f"*yt-dlp version:* `{yt_dlp.version.__version__}`\n"
        f"*Token:* {'✅ set' if os.environ.get('TELEGRAM_BOT_TOKEN') else '❌ not set'}\n",
        parse_mode="Markdown"
    )

# ─── Live progress updater ────────────────────────────────────────────────────
async def _progress_updater(status_msg, emoji: str, platform: str, stop_event: asyncio.Event):
    """Edit the status message every 20s so user knows it's still working."""
    dots  = ["⏳", "⌛"]
    steps = [20, 20, 20, 10]   # update at 20s, 40s, 60s, 70s
    msgs  = [
        f"{emoji} *Downloading from {platform}...*\n⏳ Still working... (20s)",
        f"{emoji} *Downloading from {platform}...*\n⌛ Almost there... (40s)",
        f"{emoji} *Downloading from {platform}...*\n⏳ Processing... (60s)",
        f"{emoji} *Downloading from {platform}...*\n⌛ Finalizing... (70s)",
    ]
    for wait, msg in zip(steps, msgs):
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=wait)
            return   # download finished — stop updating
        except asyncio.TimeoutError:
            pass
        if stop_event.is_set():
            return
        try:
            await status_msg.edit_text(msg, parse_mode="Markdown")
        except Exception:
            pass

# ─── Main Message Handler ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import yt_dlp

    user_text = update.message.text.strip()
    platform  = detect_platform(user_text)

    if not platform:
        await update.message.reply_text(
            "❌ *Unsupported link!*\n\n"
            "Supported: YouTube, Instagram, TikTok, Twitter/X, Facebook\n"
            "Use /help for info.",
            parse_mode="Markdown"
        )
        return

    emoji      = PLATFORM_EMOJI.get(platform, "📥")
    status_msg = await update.message.reply_text(
        f"{emoji} *Downloading from {platform}...*\n⏳ Please wait...",
        parse_mode="Markdown"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        stop_event = asyncio.Event()
        # Start live progress updater in background
        progress_task = asyncio.create_task(
            _progress_updater(status_msg, emoji, platform, stop_event)
        )

        try:
            loop       = asyncio.get_event_loop()
            video_path = await loop.run_in_executor(
                None, download_video, user_text, tmp_dir, platform
            )
        except yt_dlp.utils.DownloadError as e:
            stop_event.set()
            progress_task.cancel()
            err = str(e).lower()
            if any(k in err for k in ["private", "login", "sign in", "cookie", "auth"]):
                msg = (
                    "🔒 *Login required!*\n\n"
                    "Use /debug to check cookie status.\n"
                    "See /help for setup."
                )
            elif "timed out" in err:
                msg = (
                    "⏳ *Download timed out!*\n\n"
                    "Video took too long (90s limit).\n"
                    "Try a shorter video or try again later."
                )
            elif any(k in err for k in ["not available", "removed", "deleted"]):
                if platform == "YouTube":
                    msg = (
                        "🚫 *YouTube block detected!*\n\n"
                        "YouTube is blocking this server IP.\n"
                        "Trying different methods... please retry in 1 minute."
                    )
                else:
                    msg = "🚫 *Content unavailable!* Video may have been removed."
            elif any(k in err for k in ["geo", "region", "country"]):
                msg = "🌍 *Region-locked!* Not available in server's region."
            elif "http error 429" in err or "too many requests" in err:
                msg = "⏳ *Rate limited!* Please wait a minute and try again."
            else:
                msg = f"❌ *Download error:*\n`{str(e)[:300]}`"
            await status_msg.edit_text(msg, parse_mode="Markdown")
            logger.warning("DownloadError for %s: %s", user_text, e)
            return

        except Exception as e:
            stop_event.set()
            progress_task.cancel()
            await status_msg.edit_text(
                "⚠️ *Unexpected error!* Please try again later.",
                parse_mode="Markdown"
            )
            logger.error("Error for %s: %s", user_text, e, exc_info=True)
            return

        finally:
            stop_event.set()

        # ── Upload ────────────────────────────────────────────────────────────
        if video_path is None or not os.path.exists(video_path):
            extra = "\n\n📌 Use /debug to check Instagram cookie status." \
                    if platform in ("Instagram", "Facebook") else ""
            await status_msg.edit_text(
                f"❌ *Download failed!*\n\nContent may be private or unavailable.{extra}",
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

# ─── Entry Point ──────────────────────────────────────────────────────────────
def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    keep_alive()
    logger.info("Bot starting... ffmpeg=%s cookies=%s", FFMPEG_AVAILABLE, cookies_status())

    bot_app = ApplicationBuilder().token(token).build()
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("debug", debug_command))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running!")
    bot_app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,   # clear old updates on restart
    )

if __name__ == "__main__":
    main()
