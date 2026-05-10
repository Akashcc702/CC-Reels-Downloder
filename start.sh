#!/bin/bash
echo "Installing ffmpeg..."
apt-get update -qq && apt-get install -y -qq ffmpeg
echo "ffmpeg installed: $(ffmpeg -version 2>&1 | head -1)"
echo "Starting bot..."
python main.py
