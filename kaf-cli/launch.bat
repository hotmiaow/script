@echo off
chcp 65001 >nul
title kaf-cli 繁體中文電子書轉換器

cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [錯誤] 系統未檢測到 Python，請先安裝 Python 3 並勾選 Add to PATH！
    pause
    exit /b 1
)

echo 正在啟動 kaf-cli 繁體中文電子書轉換器...
python gui.py %*
if %errorlevel% neq 0 (
    pause
)
