import os
import sys
import shutil
import base64
import tempfile
import logging
import requests
import yt_dlp
from youtube_invidious import download_youtube as _yt_invidious

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB    = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
COOKIE_PLATFORMS    = {"Instagram", "Facebook", "TikTok", "Twitter/X"}
FFMPEG_AVAILABLE    = shutil.which("ffmpeg") is not None

COOKIE_ENV_VARS = {
    "Instagram": "INSTAGRAM_COOKIES",
    "Facebook":  "INSTAGRAM_COOKIES",
    "TikTok":    "TIKTOK_COOKIES",
    "Twitter/X": "TWITTER_COOKIES",
}


def _decode_cookies(raw: str) -> tuple[str, str]:
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        return decoded, "base64"
    except Exception:
        return raw, "plain text"


def load_cookies_to_tempfile(platform: str = "Instagram") -> str | None:
    env_key = COOKIE_ENV_VARS.get(platform, "INSTAGRAM_COOKIES")
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        return None
    try:
        decoded, _ = _decode_cookies(raw)
        if "Netscape HTTP Cookie File" not in decoded:
            decoded = "# Netscape HTTP Cookie File\n" + decoded
        prefix = platform.lower().replace("/", "_") + "_"
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix=prefix
        )
        tmp.write(decoded)
        tmp.flush()
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.error("Cookies load failed for %s: %s", platform, e)
        return None


def _get_ydl_opts(output_dir: str, platform: str, cookies_path: str | None) -> dict:
    """Build yt-dlp options dict for Python API."""

    # ── Format ────────────────────────────────────────────────────────────────
    # Cap at 720p for speed + Telegram compatibility
    fmt = (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
        "best[height<=720][ext=mp4]/"
        "best[ext=mp4]/best"
    )

    opts = {
        "outtmpl":              os.path.join(output_dir, "%(title).80s.%(ext)s"),
        "format":               fmt,
        "merge_output_format":  "mp4",
        "noplaylist":           True,
        "extract_flat":         False,
        "quiet":                True,
        "no_warnings":          True,
        "socket_timeout":       30,
        "retries":              5,
        "fragment_retries":     5,
        "concurrent_fragment_downloads": 4,
        "geo_bypass":           True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    if FFMPEG_AVAILABLE:
        opts["postprocessors"] = [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }]

    # ── Platform-specific ─────────────────────────────────────────────────────
    if platform == "YouTube":
        # mweb → web_safari → tv_embedded: best server-IP combo
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["mweb", "web_safari", "tv_embedded", "ios"]
            }
        }
        # Shorts URL normalisation
    elif platform in ("Instagram", "Facebook"):
        opts["http_headers"].update({
            "X-IG-App-ID": "936619743392459",
            "Origin":      "https://www.instagram.com",
            "Referer":     "https://www.instagram.com/",
        })

    if cookies_path:
        opts["cookiefile"] = cookies_path

    return opts


def _find_video(output_dir: str, prepared_filename: str) -> str | None:
    """Find the downloaded video file."""
    base, _ = os.path.splitext(prepared_filename)
    for ext in ("mp4", "mkv", "webm", "mov", "avi"):
        candidate = f"{base}.{ext}"
        if os.path.exists(candidate):
            return candidate
    if os.path.exists(prepared_filename):
        return prepared_filename
    # Scan directory as last resort
    for f in sorted(os.listdir(output_dir)):
        if f.endswith((".mp4", ".mkv", ".webm", ".mov", ".avi")):
            return os.path.join(output_dir, f)
    return None


def download_video(url: str, output_dir: str, platform: str = "") -> str | None:
    """
    1. YouTube  → Invidious API (no bot-detection) → yt-dlp fallback
    2. Others   → yt-dlp Python API
    """
    # ── YouTube: Invidious first ──────────────────────────────────────────────
    if platform == "YouTube":
        # Normalise Shorts URL
        if "shorts/" in url:
            video_id = url.split("shorts/")[1].split("?")[0]
            url_norm = f"https://www.youtube.com/watch?v={video_id}"
        else:
            url_norm = url
        try:
            logger.info("Trying Invidious API for YouTube: %s", url_norm)
            result = _yt_invidious(url_norm, output_dir)
            if result and os.path.exists(result):
                logger.info("Invidious success: %s", result)
                return result
        except Exception as e:
            logger.warning("Invidious exception: %s", e)
        logger.warning("Invidious failed — falling back to yt-dlp")

    # ── yt-dlp Python API ─────────────────────────────────────────────────────
    cookies_path = None
    if platform in COOKIE_PLATFORMS:
        cookies_path = load_cookies_to_tempfile(platform)

    try:
        opts = _get_ydl_opts(output_dir, platform, cookies_path)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return None
            prepared = ydl.prepare_filename(info)
            return _find_video(output_dir, prepared)
    finally:
        if cookies_path and os.path.exists(cookies_path):
            os.unlink(cookies_path)


def get_file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)

def is_too_large(path: str) -> bool:
    return os.path.getsize(path) > MAX_FILE_SIZE_BYTES

def cookies_status() -> str:
    checks = [
        ("📸 Instagram", "INSTAGRAM_COOKIES", "sessionid"),
        ("▶️ YouTube",   "YOUTUBE_COOKIES",   ""),
        ("🎵 TikTok",    "TIKTOK_COOKIES",    ""),
        ("🐦 Twitter/X", "TWITTER_COOKIES",   ""),
    ]
    lines = []
    for label, env_key, req_cookie in checks:
        raw = os.environ.get(env_key, "").strip()
        if not raw:
            lines.append(f"{label}: ❌ not set")
        else:
            decoded, fmt = _decode_cookies(raw)
            entries = [l for l in decoded.splitlines() if l.strip() and not l.startswith("#")]
            if req_cookie:
                ok = any(req_cookie in l for l in decoded.splitlines())
                lines.append(f"{label}: ✅ {len(entries)} entries | {req_cookie}: {'✅' if ok else '❌ missing'}")
            else:
                lines.append(f"{label}: ✅ {len(entries)} entries")
    return "\n".join(lines)
