#!/bin/bash
# Install ffmpeg if not present
if ! command -v ffmpeg &> /dev/null; then
    echo "Installing ffmpeg..."
    apt-get update -qq && apt-get install -y -qq ffmpeg
fi
echo "ffmpeg: $(ffmpeg -version 2>&1 | head -1)"

# Always update yt-dlp to latest (YouTube breaks with old versions)
echo "Updating yt-dlp..."
pip install -q --upgrade yt-dlp
echo "yt-dlp: $(yt-dlp --version)"

echo "Starting bot..."
python main.py
