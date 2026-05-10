#!/bin/bash
# Install ffmpeg only if not already installed
if ! command -v ffmpeg &> /dev/null; then
    echo "Installing ffmpeg..."
    apt-get update -qq && apt-get install -y -qq ffmpeg
    echo "ffmpeg ready: $(ffmpeg -version 2>&1 | head -1)"
else
    echo "ffmpeg already installed: $(ffmpeg -version 2>&1 | head -1)"
fi
echo "Starting bot..."
python main.py
