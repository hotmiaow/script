#!/bin/sh
# YouTube Audio Transcriber & Summarizer
# Usage: transcribe_youtube.sh <YouTube URL> [language] [mode]
# language: "en" (default) or "zh" for Traditional Chinese
# mode: "fast" (default) or "standard"
# Part of youtube-transcriber skill

if [ -z "$1" ]; then
    echo "Usage: transcribe_youtube.sh <YouTube URL> [language] [mode]"
    echo "  language: en (English, default) or zh (Traditional Chinese)"
    echo "  mode: fast (default, parallel processing) or standard"
    exit 1
fi

URL="$1"
LANGUAGE="${2:-en}"
MODE="${3:-fast}"

echo "=== YouTube Audio Transcriber ==="
echo "URL: $URL"
echo "Language: $LANGUAGE"
echo "Mode: $MODE"
echo ""

if [ "$MODE" = "fast" ]; then
    # Use optimized parallel version
    python3 /home/keith/.gemini/skills/youtube-transcriber/youtube_transcriber_fast.py "$URL" "$LANGUAGE"
else
    # Use standard version
    python3 /home/keith/.gemini/skills/youtube-transcriber/youtube_transcriber.py "$URL" "$LANGUAGE"
fi
