import os
import base64
import tempfile
import yt_dlp

MAX_FILE_SIZE_MB    = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Platforms that use cookies (loaded from env var)
COOKIE_PLATFORMS = {"Instagram", "Facebook"}


def _write_cookies_to_tempfile() -> str | None:
    """
    Decode INSTAGRAM_COOKIES env var (base64) and write to a temp file.
    Returns the temp file path, or None if env var is not set.
    """
    raw = os.environ.get("INSTAGRAM_COOKIES", "").strip()
    if not raw:
        return None
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="cookies_"
        )
        tmp.write(decoded)
        tmp.flush()
        tmp.close()
        return tmp.name
    except Exception:
        return None


def _get_ydl_opts(output_dir: str, cookies_path: str | None = None) -> dict:
    opts = {
        "format": (
            "bestvideo[ext=mp4][filesize<45M]+bestaudio[ext=m4a]/"
            "best[ext=mp4][filesize<45M]/"
            "best[filesize<45M]/"
            "best"
        ),
        "outtmpl": os.path.join(output_dir, "%(title).60s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
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
    if cookies_path:
        opts["cookiefile"] = cookies_path
    return opts


def download_video(url: str, output_dir: str, platform: str = "") -> str | None:
    """
    Download video from any supported platform.
    YouTube / TikTok / Twitter  → no cookies needed.
    Instagram / Facebook        → cookies loaded from INSTAGRAM_COOKIES env var.
    """
    cookies_path = None
    if platform in COOKIE_PLATFORMS:
        cookies_path = _write_cookies_to_tempfile()

    ydl_opts = _get_ydl_opts(output_dir, cookies_path)

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
        # Clean up the temp cookies file
        if cookies_path and os.path.exists(cookies_path):
            os.unlink(cookies_path)

    return None


def get_file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)


def is_too_large(path: str) -> bool:
    return os.path.getsize(path) > MAX_FILE_SIZE_BYTES
