import os
import yt_dlp

MAX_FILE_SIZE_MB    = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def download_video(url: str, output_dir: str) -> str | None:
    """
    Download a video from YouTube or Instagram using yt-dlp.
    Returns the path to the downloaded file, or None on failure.
    """
    ydl_opts = {
        # Best quality video+audio under 45 MB; fall back to anything available
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
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info     = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

        # yt-dlp may rename the file after post-processing — check all common extensions
        base, _ = os.path.splitext(filename)
        for ext in ("mp4", "mkv", "webm", "mov", "avi"):
            candidate = f"{base}.{ext}"
            if os.path.exists(candidate):
                return candidate

        if os.path.exists(filename):
            return filename

    return None


def get_file_size_mb(path: str) -> float:
    """Return file size in megabytes."""
    return os.path.getsize(path) / (1024 * 1024)


def is_too_large(path: str) -> bool:
    """Return True if the file exceeds Telegram's 50 MB bot upload limit."""
    return os.path.getsize(path) > MAX_FILE_SIZE_BYTES
