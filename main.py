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
        r"(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+",
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
        "*Limits:* Max 50 MB, public videos only.",
        parse_mode="Markdown"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import yt_dlp
    status = cookies_status()
    await update.message.reply_text(
        f"🔍 *Bot Debug Info*\n\n"
        f"*ffmpeg:* {'✅ available' if FFMPEG_AVAILABLE else '❌ not found'}\n"
        f"*Cookies:*\n{status}\n\n"
        f"*yt-dlp:* `{yt_dlp.version.__version__}`\n"
        f"*Token:* {'✅ set' if os.environ.get('TELEGRAM_BOT_TOKEN') else '❌ not set'}\n",
        parse_mode="Markdown"
    )

# ─── Progress updater ─────────────────────────────────────────────────────────
async def _progress_updater(status_msg, emoji: str, platform: str, stop: asyncio.Event):
    steps = [
        (20, f"{emoji} *Downloading from {platform}...*\n⏳ 20s..."),
        (20, f"{emoji} *Downloading from {platform}...*\n⌛ 40s..."),
        (20, f"{emoji} *Downloading from {platform}...*\n⏳ 60s..."),
        (20, f"{emoji} *Downloading from {platform}...*\n⌛ 80s..."),
        (20, f"{emoji} *Downloading from {platform}...*\n⏳ Almost done..."),
    ]
    for wait, msg in steps:
        try:
            await asyncio.wait_for(asyncio.shield(stop.wait()), timeout=wait)
            return
        except asyncio.TimeoutError:
            pass
        if stop.is_set():
            return
        try:
            await status_msg.edit_text(msg, parse_mode="Markdown")
        except Exception:
            pass

# ─── Upload helper (video → document fallback) ────────────────────────────────
async def _send_video(update: Update, video_path: str, file_size_mb: float):
    caption = f"✅ Done! ({file_size_mb:.1f} MB)"
    try:
        with open(video_path, "rb") as vf:
            await update.message.reply_video(
                video=vf,
                caption=caption,
                supports_streaming=True,
                read_timeout=180,
                write_timeout=180,
                connect_timeout=30,
            )
    except Exception:
        # Fallback: send as document (no size re-encode, always works)
        with open(video_path, "rb") as vf:
            await update.message.reply_document(
                document=vf,
                caption=caption,
                read_timeout=180,
                write_timeout=180,
                connect_timeout=30,
            )

# ─── Main Message Handler ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import yt_dlp

    user_text = update.message.text.strip()
    platform  = detect_platform(user_text)

    if not platform:
        await update.message.reply_text(
            "❌ *Unsupported link!*\n\n"
            "Supported: YouTube, Instagram, TikTok, Twitter/X, Facebook",
            parse_mode="Markdown"
        )
        return

    emoji      = PLATFORM_EMOJI.get(platform, "📥")
    status_msg = await update.message.reply_text(
        f"{emoji} *Downloading from {platform}...*\n⏳ Please wait...",
        parse_mode="Markdown"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        stop       = asyncio.Event()
        progress_t = asyncio.create_task(
            _progress_updater(status_msg, emoji, platform, stop)
        )

        try:
            loop       = asyncio.get_event_loop()
            video_path = await asyncio.wait_for(
                loop.run_in_executor(None, download_video, user_text, tmp_dir, platform),
                timeout=300.0   # 5 minutes max
            )
        except asyncio.TimeoutError:
            stop.set(); progress_t.cancel()
            await status_msg.edit_text(
                "⏳ *Download timed out!*\n\nVideo took too long (5 min limit).\nTry a shorter video.",
                parse_mode="Markdown"
            )
            return
        except yt_dlp.utils.DownloadError as e:
            stop.set(); progress_t.cancel()
            err = str(e).lower()
            if any(k in err for k in ["private", "login", "sign in", "cookie", "auth"]):
                msg = "🔒 *Login required!*\n\nUse /debug to check cookie status."
            elif "timed out" in err:
                msg = "⏳ *Download timed out!*\n\nTry a shorter video."
            elif any(k in err for k in ["not available", "removed", "deleted"]):
                msg = "🚫 *Content unavailable!* Video may have been removed."
            elif any(k in err for k in ["geo", "region", "country"]):
                msg = "🌍 *Region-locked!* Not available in this region."
            elif "429" in err or "too many requests" in err:
                msg = "⏳ *Rate limited!* Wait a minute and try again."
            else:
                msg = f"❌ *Download error:*\n`{str(e)[:200]}`"
            await status_msg.edit_text(msg, parse_mode="Markdown")
            return
        except Exception as e:
            stop.set(); progress_t.cancel()
            await status_msg.edit_text(
                f"⚠️ *Unexpected error!*\n`{str(e)[:150]}`",
                parse_mode="Markdown"
            )
            logger.error("Unexpected error for %s: %s", user_text, e, exc_info=True)
            return
        finally:
            stop.set()

        # ── Upload ────────────────────────────────────────────────────────────
        if video_path is None or not os.path.exists(video_path):
            extra = "\n\n📌 Use /debug to check Instagram cookie status." if platform in ("Instagram", "Facebook") else ""
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
        try:
            await _send_video(update, video_path, file_size_mb)
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(
                f"⚠️ *Upload failed!*\n`{str(e)[:100]}`",
                parse_mode="Markdown"
            )
            logger.error("Upload failed: %s", e, exc_info=True)

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
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()
