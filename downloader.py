import os
import sys
import shutil
import base64
import tempfile
import logging
import subprocess
import yt_dlp
from youtube_invidious import download_youtube as _yt_invidious

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB    = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
COOKIE_PLATFORMS    = {"Instagram", "Facebook", "TikTok", "Twitter/X"}
DOWNLOAD_TIMEOUT    = 90
FFMPEG_AVAILABLE    = shutil.which("ffmpeg") is not None
# Always works — no binary path issues
YTDLP_CMD           = [sys.executable, "-m", "yt_dlp"]

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
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, prefix=prefix)
        tmp.write(decoded)
        tmp.flush()
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.error("Cookies load failed for %s: %s", platform, e)
        return None


def _build_cmd(url: str, output_dir: str, platform: str, cookies_path: str | None) -> list[str]:
    if FFMPEG_AVAILABLE:
        fmt = (
            "bestvideo[ext=mp4][filesize<40M]+bestaudio[ext=m4a]/"
            "best[ext=mp4][filesize<40M]/best[filesize<40M]/best"
        )
    else:
        fmt = "best[ext=mp4][filesize<40M]/best[filesize<40M]/worst[ext=mp4]/worst"

    cmd = YTDLP_CMD + [
        "--format", fmt,
        "--output", os.path.join(output_dir, "%(title).60s.%(ext)s"),
        "--restrict-filenames",
        "--no-playlist",
        "--socket-timeout", "15",
        "--retries", "2",
        "--fragment-retries", "2",
        "--quiet",
        "--no-warnings",
        "--user-agent",
        "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36",
    ]

    if FFMPEG_AVAILABLE:
        cmd += ["--merge-output-format", "mp4"]

    if platform in ("Instagram", "Facebook"):
        cmd += [
            "--add-header", "X-IG-App-ID:936619743392459",
            "--add-header", "Origin:https://www.instagram.com",
            "--add-header", "Referer:https://www.instagram.com/",
        ]

    if platform == "YouTube":
        cmd += [
            "--extractor-args",
            "youtube:player_client=tv_embedded,web_creator,ios,web",
            "--geo-bypass",
            "--no-check-certificates",
        ]

    if cookies_path:
        cmd += ["--cookies", cookies_path]

    cmd.append(url)
    return cmd


def download_video(url: str, output_dir: str, platform: str = "") -> str | None:
    """
    YouTube  → Invidious API (bypasses cloud IP block) → yt-dlp fallback
    Others   → yt-dlp
    """
    # ── YouTube: Invidious first ──────────────────────────────────────────────
    if platform == "YouTube":
        try:
            logger.info("Trying Invidious API for YouTube...")
            result = _yt_invidious(url, output_dir)
            if result and os.path.exists(result):
                logger.info("Invidious success: %s", result)
                return result
        except Exception as e:
            logger.warning("Invidious exception: %s", e)
        logger.warning("Invidious failed — falling back to yt-dlp")

    # ── Other platforms + YouTube fallback: yt-dlp ───────────────────────────
    cookies_path = None
    if platform in COOKIE_PLATFORMS:
        cookies_path = load_cookies_to_tempfile(platform)

    cmd = _build_cmd(url, output_dir, platform, cookies_path)
    logger.info("yt-dlp cmd: %s", " ".join(cmd[:8]) + " ...")

    try:
        result = subprocess.run(
            cmd,
            timeout=DOWNLOAD_TIMEOUT,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "Unknown error").strip()
            logger.warning("yt-dlp error (code %d): %s", result.returncode, err[:300])
            raise yt_dlp.utils.DownloadError(err)

        for f in sorted(os.listdir(output_dir)):
            if f.endswith((".mp4", ".mkv", ".webm", ".mov", ".avi")):
                return os.path.join(output_dir, f)

        logger.error("yt-dlp succeeded but no video file in %s", output_dir)
        return None

    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp timed out after %ds", DOWNLOAD_TIMEOUT)
        raise yt_dlp.utils.DownloadError("timed out")

    except yt_dlp.utils.DownloadError:
        raise   # re-raise — caught by handle_message

    except Exception as e:
        logger.error("Unexpected subprocess error: %s", e, exc_info=True)
        raise yt_dlp.utils.DownloadError(str(e))

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
