import os
import shutil
import base64
import tempfile
import logging
import yt_dlp

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB    = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
COOKIE_PLATFORMS    = {"Instagram", "Facebook"}
FFMPEG_AVAILABLE    = shutil.which("ffmpeg") is not None


def load_cookies_to_tempfile() -> str | None:
    raw = os.environ.get("INSTAGRAM_COOKIES", "").strip()
    if not raw:
        return None
    try:
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
        except Exception:
            decoded = raw
        if "Netscape HTTP Cookie File" not in decoded:
            decoded = "# Netscape HTTP Cookie File\n" + decoded
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, prefix="ig_")
        tmp.write(decoded)
        tmp.flush()
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.error("Cookies load failed: %s", e)
        return None


def _get_ydl_opts(output_dir: str, platform: str = "", cookies_path: str | None = None) -> dict:
    if FFMPEG_AVAILABLE:
        fmt = (
            "bestvideo[ext=mp4][filesize<45M]+bestaudio[ext=m4a]/"
            "best[ext=mp4][filesize<45M]/best[filesize<45M]/best"
        )
    else:
        fmt = "best[ext=mp4][filesize<45M]/best[filesize<45M]/worst[ext=mp4]/worst"

    opts = {
        "format": fmt,
        "outtmpl": os.path.join(output_dir, "%(title).60s.%(ext)s"),
        "restrictfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 12; Pixel 6) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.6367.82 Mobile Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
    }

    if FFMPEG_AVAILABLE:
        opts["merge_output_format"] = "mp4"
        opts["postprocessors"] = [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}]

    if platform == "YouTube":
        opts["extractor_args"] = {
            "youtube": {"player_client": ["android", "web"]}
        }

    if cookies_path:
        opts["cookiefile"] = cookies_path

    return opts


def download_video(url: str, output_dir: str, platform: str = "") -> str | None:
    """Download video — called inside a thread via run_in_executor."""
    cookies_path = None
    if platform in COOKIE_PLATFORMS:
        cookies_path = load_cookies_to_tempfile()

    try:
        ydl_opts = _get_ydl_opts(output_dir, platform, cookies_path)
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

            for f in os.listdir(output_dir):
                if f.endswith((".mp4", ".mkv", ".webm", ".mov", ".avi")):
                    return os.path.join(output_dir, f)
    finally:
        if cookies_path and os.path.exists(cookies_path):
            os.unlink(cookies_path)

    return None


def get_file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)

def is_too_large(path: str) -> bool:
    return os.path.getsize(path) > MAX_FILE_SIZE_BYTES

def cookies_status() -> str:
    raw = os.environ.get("INSTAGRAM_COOKIES", "").strip()
    if not raw:
        return "❌ INSTAGRAM_COOKIES not set"
    try:
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
            fmt = "base64"
        except Exception:
            decoded = raw
            fmt = "plain text"
        lines = [l for l in decoded.splitlines() if l.strip() and not l.startswith("#")]
        return f"✅ Loaded ({fmt}), {len(lines)} cookie entries"
    except Exception as e:
        return f"❌ Error: {e}"
