import os
import json
import shutil
import base64
import tempfile
import logging
import subprocess

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB    = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
COOKIE_PLATFORMS    = {"Instagram", "Facebook", "YouTube", "TikTok", "Twitter/X"}
DOWNLOAD_TIMEOUT    = 90          # subprocess is ACTUALLY killed after this
FFMPEG_AVAILABLE    = shutil.which("ffmpeg") is not None
YTDLP_PATH          = shutil.which("yt-dlp") or "yt-dlp"


# Map platform → env var name
COOKIE_ENV_VARS = {
    "Instagram": "INSTAGRAM_COOKIES",
    "Facebook":  "INSTAGRAM_COOKIES",   # reuse same cookies
    "YouTube":   "YOUTUBE_COOKIES",
    "TikTok":    "TIKTOK_COOKIES",
    "Twitter/X": "TWITTER_COOKIES",
}

def load_cookies_to_tempfile(platform: str = "Instagram") -> str | None:
    env_key = COOKIE_ENV_VARS.get(platform, "INSTAGRAM_COOKIES")
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        logger.info("No cookies set for %s (%s)", platform, env_key)
        return None
    try:
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
        except Exception:
            decoded = raw
        if "Netscape HTTP Cookie File" not in decoded:
            decoded = "# Netscape HTTP Cookie File\n" + decoded
        prefix = platform.lower().replace("/", "_") + "_"
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, prefix=prefix)
        tmp.write(decoded)
        tmp.flush()
        tmp.close()
        logger.info("Cookies loaded for %s from %s", platform, env_key)
        return tmp.name
    except Exception as e:
        logger.error("Cookies load failed for %s: %s", platform, e)
        return None


def _build_cmd(url: str, output_dir: str, platform: str, cookies_path: str | None) -> list[str]:
    """Build yt-dlp CLI command."""
    if FFMPEG_AVAILABLE:
        fmt = (
            "bestvideo[ext=mp4][filesize<40M]+bestaudio[ext=m4a]/"
            "best[ext=mp4][filesize<40M]/best[filesize<40M]/best"
        )
    else:
        fmt = "best[ext=mp4][filesize<40M]/best[filesize<40M]/worst[ext=mp4]/worst"

    cmd = [
        YTDLP_PATH,
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
        cmd += ["--merge-output-format", "mp4",
                "--postprocessor-args", "FFmpegVideoConvertor:-vcodec copy -acodec copy"]

    if platform == "YouTube":
        # With cookies → use "web" client (authenticates properly)
        # Without cookies → use "tv_embedded" (bypasses bot detection)
        yt_cookies_set = bool(os.environ.get("YOUTUBE_COOKIES", "").strip())
        if yt_cookies_set and cookies_path:
            yt_clients = "web,web_safari,tv_embedded"
        else:
            yt_clients = "tv_embedded,web_creator,ios,web"
        cmd += [
            "--extractor-args", f"youtube:player_client={yt_clients}",
            "--geo-bypass",
            "--no-check-certificates",
        ]

    # Instagram needs specific app headers
    if platform in ("Instagram", "Facebook"):
        cmd += [
            "--add-header", "X-IG-App-ID:936619743392459",
            "--add-header", "X-ASBD-ID:129477",
            "--add-header", "Origin:https://www.instagram.com",
            "--add-header", "Referer:https://www.instagram.com/",
        ]

    if cookies_path:
        cmd += ["--cookies", cookies_path]

    cmd.append(url)
    return cmd


def download_video(url: str, output_dir: str, platform: str = "") -> str | None:
    """
    Download using yt-dlp as a subprocess.
    The process is ACTUALLY killed after DOWNLOAD_TIMEOUT seconds.
    """
    cookies_path = None
    if platform in COOKIE_PLATFORMS:
        cookies_path = load_cookies_to_tempfile(platform)

    cmd = _build_cmd(url, output_dir, platform, cookies_path)
    logger.info("Running: %s", " ".join(cmd[:6]) + " ...")

    try:
        result = subprocess.run(
            cmd,
            timeout=DOWNLOAD_TIMEOUT,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            err = result.stderr.strip()
            logger.warning("yt-dlp error (code %d): %s", result.returncode, err[:300])
            # Re-raise as DownloadError so handle_message catches it properly
            raise _make_download_error(err)

        # Find the downloaded file
        for f in sorted(os.listdir(output_dir)):
            if f.endswith((".mp4", ".mkv", ".webm", ".mov", ".avi")):
                return os.path.join(output_dir, f)

        logger.error("yt-dlp succeeded but no video file found in %s", output_dir)
        return None

    except subprocess.TimeoutExpired:
        logger.warning("Download killed after %ds: %s", DOWNLOAD_TIMEOUT, url)
        raise _make_download_error("timed out")
    finally:
        if cookies_path and os.path.exists(cookies_path):
            os.unlink(cookies_path)


def _make_download_error(msg: str):
    """Wrap a string as a yt-dlp DownloadError."""
    import yt_dlp
    err = yt_dlp.utils.DownloadError(msg)
    return err


def get_file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)

def is_too_large(path: str) -> bool:
    return os.path.getsize(path) > MAX_FILE_SIZE_BYTES

def _decode_cookies(raw: str) -> tuple[str, str]:
    """Returns (decoded_text, format_label)."""
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        return decoded, "base64"
    except Exception:
        return raw, "plain text"

def cookies_status() -> str:
    lines = []
    checks = [
        ("📸 Instagram", "INSTAGRAM_COOKIES", "sessionid"),
        ("▶️ YouTube",   "YOUTUBE_COOKIES",   ""),
        ("🎵 TikTok",    "TIKTOK_COOKIES",    ""),
        ("🐦 Twitter/X", "TWITTER_COOKIES",   ""),
    ]
    for label, env_key, required_cookie in checks:
        raw = os.environ.get(env_key, "").strip()
        if not raw:
            lines.append(f"{label}: ❌ not set")
        else:
            decoded, fmt = _decode_cookies(raw)
            entries = [l for l in decoded.splitlines() if l.strip() and not l.startswith("#")]
            if required_cookie:
                has_req = any(required_cookie in l for l in decoded.splitlines())
                req_icon = "✅" if has_req else f"⚠️ {required_cookie} missing"
                lines.append(f"{label}: ✅ {len(entries)} entries | {req_icon}")
            else:
                lines.append(f"{label}: ✅ {len(entries)} entries")
    return "\n".join(lines)
