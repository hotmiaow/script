#!/bin/bash

if [ -z "$1" ]; then
    echo "使用方法: ./dl-yt.sh [YouTube URL]"
    exit 1
fi

URL=$1

echo "請選擇下載模式："
echo "1) 720p 影片 (MP4)"
echo "2) 480p 影片 (MP4 - 854x480)"
echo "3) 音訊 (MP3)"
read -p "輸入選項 (1, 2 或 3): " CHOICE

case $CHOICE in
    1)
        # 優先選擇 720p 的 MP4
        yt-dlp -f "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]" --merge-output-format mp4 -o "%(title)s_720p.%(ext)s" "$URL"
        ;;
    2)
        # 精確鎖定 480p (高度不超過 480)
        echo "正在下載 480p 影片..."
        yt-dlp -f "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]" --merge-output-format mp4 -o "%(title)s_480p.%(ext)s" "$URL"
        ;;
    3)
        yt-dlp -x --audio-format mp3 --audio-quality 192K -o "%(title)s.%(ext)s" "$URL"
        ;;
    *)
        echo "無效選項。"
        exit 1
        ;;
esac
