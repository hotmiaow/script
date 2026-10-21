#!/usr/bin/env bash
# kaf-cli Web GUI 啟動腳本
cd "$(dirname "$0")"

PORT=${1:-8080}
echo "正在啟動 kaf-cli 繁體中文 Web GUI 服務 (Port: $PORT)..."
python3 gui.py --web --port "$PORT"
