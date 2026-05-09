import os
import yt_dlp

MAX_FILE_SIZE_MB    = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Path to Instagram/Facebook cookies file
# Export from your browser using the "Get cookies.txt LOCALLY" Chrome extension
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")


def _get_ydl_opts(output_dir: str) -> dict:
    """Build yt-dlp options, injecting cookies if cookies.txt is present."""
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
        # Mimic a real browser to avoid bot-detection blocks
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

    # Inject cookies for Instagram, Facebook, Twitter etc.
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE

    return opts


def download_video(url: str, output_dir: str) -> str | None:
    """
    Download a video from any supported platform using yt-dlp.
    Returns the path to the downloaded file, or None on failure.

    Supported: YouTube, Instagram, TikTok, Twitter/X, Facebook, and 1000+ sites.
    """
    ydl_opts = _get_ydl_opts(output_dir)

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

    return None


def get_file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)


def is_too_large(path: str) -> bool:
    return os.path.getsize(path) > MAX_FILE_SIZE_BYTES
