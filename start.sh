#!/bin/bash
echo "Checking ffmpeg..."
if command -v ffmpeg &> /dev/null; then
    echo "ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
else
    echo "ffmpeg not found, installing..."
    apt-get update -qq && apt-get install -y -qq ffmpeg
fi
echo "Updating yt-dlp to latest..."
pip install -q --upgrade yt-dlp
echo "yt-dlp: $(python -m yt_dlp --version)"
echo "Starting bot..."
python main.py
