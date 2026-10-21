#!/usr/bin/env bash
# kaf-cli 繁體中文 GUI 啟動腳本 (Linux / macOS)
cd "$(dirname "$0")"

# 優先使用 python3
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "錯誤：未找到 Python 環境，請先安裝 Python 3！"
    exit 1
fi

echo "正在啟動 kaf-cli 繁體中文電子書轉換器..."
$PYTHON_CMD gui.py "$@"
