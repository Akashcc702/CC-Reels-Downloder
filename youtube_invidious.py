"""
YouTube downloader using Invidious API.
Bypasses YouTube's bot/datacenter IP detection entirely.
"""
import os
import re
import logging
import requests

logger = logging.getLogger(__name__)

# Public Invidious instances — tried in order until one works
INSTANCES = [
    "https://invidious.privacyredirect.com",
    "https://invidious.kavin.rocks",
    "https://inv.riverside.rocks",
    "https://yt.artemislena.eu",
    "https://invidious.nerdvpn.de",
    "https://iv.datura.network",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from any YouTube URL format."""
    patterns = [
        r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def _download_file(video_url: str, filepath: str, timeout: int = 80) -> bool:
    """Stream-download a direct video URL to filepath."""
    try:
        with requests.get(video_url, stream=True, timeout=timeout, headers=HEADERS) as r:
            r.raise_for_status()
            content_len = int(r.headers.get("Content-Length", 0))
            # Skip if file would be > 48 MB
            if content_len and content_len > 48 * 1024 * 1024:
                logger.warning("File too large: %.1f MB", content_len / 1024 / 1024)
                return False
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        return os.path.getsize(filepath) > 1000   # at least 1 KB
    except Exception as e:
        logger.warning("Download failed: %s", e)
        return False


def download_youtube(url: str, output_dir: str) -> str | None:
    """
    Download YouTube video via Invidious API.
    Returns file path on success, None on failure.
    """
    video_id = extract_video_id(url)
    if not video_id:
        logger.error("Could not extract video ID from: %s", url)
        return None

    logger.info("Downloading YouTube video: %s", video_id)

    for instance in INSTANCES:
        try:
            api_url = f"{instance}/api/v1/videos/{video_id}"
            logger.info("Trying Invidious: %s", instance)

            resp = requests.get(api_url, timeout=15, headers=HEADERS)
            if resp.status_code != 200:
                logger.warning("%s returned %d", instance, resp.status_code)
                continue

            data = resp.json()
            if "error" in data:
                logger.warning("%s error: %s", instance, data["error"])
                continue

            title = re.sub(r'[^\w\s-]', '', data.get("title", video_id))[:50].strip()

            # ── 1. Progressive streams (video+audio in one file) — best for us ──
            progressive = [
                f for f in data.get("formatStreams", [])
                if "video/mp4" in f.get("type", "")
            ]
            # Sort by resolution descending
            progressive.sort(
                key=lambda f: int(f.get("resolution", "0p").replace("p", "") or 0),
                reverse=True
            )

            for fmt in progressive:
                video_url = fmt.get("url")
                if not video_url:
                    continue
                filepath = os.path.join(output_dir, f"{title}_{video_id}.mp4")
                logger.info("Trying progressive stream: %s", fmt.get("resolution"))
                if _download_file(video_url, filepath):
                    logger.info("Downloaded via Invidious (%s): %s", instance, filepath)
                    return filepath

            # ── 2. Fallback: adaptive video-only stream (no audio, rare fallback) ──
            adaptive = [
                f for f in data.get("adaptiveFormats", [])
                if "video/mp4" in f.get("type", "") and "avc" in f.get("type", "")
            ]
            adaptive.sort(
                key=lambda f: int(f.get("bitrate", 0)),
                reverse=True
            )
            for fmt in adaptive[:2]:
                video_url = fmt.get("url")
                if not video_url:
                    continue
                filepath = os.path.join(output_dir, f"{title}_{video_id}.mp4")
                logger.info("Trying adaptive stream: %s", fmt.get("qualityLabel"))
                if _download_file(video_url, filepath):
                    return filepath

        except requests.exceptions.Timeout:
            logger.warning("%s timed out", instance)
        except Exception as e:
            logger.warning("%s failed: %s", instance, e)

    logger.error("All Invidious instances failed for %s", video_id)
    return None
