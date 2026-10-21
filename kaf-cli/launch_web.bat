@echo off
chcp 65001 >nul
title kaf-cli 繁體中文 Web GUI

cd /d "%~dp0"
set PORT=8080
if not "%~1"=="" set PORT=%~1

echo 正在啟動 kaf-cli 繁體中文 Web GUI 服務 (Port: %PORT%)...
python gui.py --web --port %PORT%
pause
