import os
import base64
import tempfile
import logging
import yt_dlp

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB    = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

COOKIE_PLATFORMS = {"Instagram", "Facebook"}


def load_cookies_to_tempfile() -> str | None:
    """
    Decode INSTAGRAM_COOKIES env var and write to temp file.
    Supports both raw cookies.txt content and base64-encoded content.
    """
    raw = os.environ.get("INSTAGRAM_COOKIES", "").strip()
    if not raw:
        logger.warning("INSTAGRAM_COOKIES env var is not set.")
        return None
    try:
        # Try base64 decode first
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
        except Exception:
            # If not base64, treat as raw cookies.txt text
            decoded = raw

        if "Netscape HTTP Cookie File" not in decoded and "# HTTP" not in decoded:
            # Add the required header if missing
            decoded = "# Netscape HTTP Cookie File\n" + decoded

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="ig_cookies_"
        )
        tmp.write(decoded)
        tmp.flush()
        tmp.close()
        logger.info("Cookies loaded to temp file: %s", tmp.name)
        return tmp.name
    except Exception as e:
        logger.error("Failed to load cookies: %s", e)
        return None


def _get_ydl_opts(output_dir: str, platform: str = "", cookies_path: str | None = None) -> dict:
    opts = {
        "outtmpl": os.path.join(output_dir, "%(title).60s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": False,           # Keep logs for debugging
        "no_warnings": False,
        "restrictfilenames": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 12; Pixel 6) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.6367.82 Mobile Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
        "retries": 5,
        "fragment_retries": 5,
    }

    # ── YouTube: use Android client to bypass server-side bot detection ──
    if platform == "YouTube":
        opts["format"] = (
            "bestvideo[ext=mp4][filesize<45M]+bestaudio[ext=m4a]/"
            "best[ext=mp4][filesize<45M]/"
            "best[filesize<45M]/"
            "best"
        )
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["android"],   # ← key fix for Render/VPS deployments
            }
        }

    # ── TikTok / Twitter: standard best format ──
    elif platform in ("TikTok", "Twitter/X"):
        opts["format"] = (
            "best[ext=mp4][filesize<45M]/"
            "best[filesize<45M]/"
            "best"
        )

    # ── Instagram / Facebook: best mp4 + cookies ──
    else:
        opts["format"] = (
            "bestvideo[ext=mp4][filesize<45M]+bestaudio[ext=m4a]/"
            "best[ext=mp4][filesize<45M]/"
            "best[filesize<45M]/"
            "best"
        )

    if cookies_path:
        opts["cookiefile"] = cookies_path

    return opts


def download_video(url: str, output_dir: str, platform: str = "") -> str | None:
    cookies_path = None
    if platform in COOKIE_PLATFORMS:
        cookies_path = load_cookies_to_tempfile()

    ydl_opts = _get_ydl_opts(output_dir, platform, cookies_path)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info     = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            base, _ = os.path.splitext(filename)
            for ext in ("mp4", "mkv", "webm", "mov", "avi"):
                candidate = f"{base}.{ext}"
                if os.path.exists(candidate):
                    return candidate

            if os.path.exists(filename):
                return filename
    finally:
        if cookies_path and os.path.exists(cookies_path):
            os.unlink(cookies_path)

    return None


def get_file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)


def is_too_large(path: str) -> bool:
    return os.path.getsize(path) > MAX_FILE_SIZE_BYTES


def cookies_status() -> str:
    """Return a debug string about cookie configuration."""
    raw = os.environ.get("INSTAGRAM_COOKIES", "").strip()
    if not raw:
        return "❌ INSTAGRAM_COOKIES not set"
    try:
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
            fmt = "base64-encoded"
        except Exception:
            decoded = raw
            fmt = "plain text"
        lines = [l for l in decoded.splitlines() if l.strip() and not l.startswith("#")]
        return f"✅ Cookies loaded ({fmt}), {len(lines)} cookie entries"
    except Exception as e:
        return f"❌ Cookies error: {e}"
