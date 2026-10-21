#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kaf-cli 繁體中文圖形介面 (支援 PyQt5 桌面版與 Web 雙模式)
專為把 TXT 文本小說轉成 EPUB / MOBI / AZW3 打造的現代化正體中文介面
"""

import sys
import os
import argparse

# 加入當前路徑以確保模組引用正確
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    parser = argparse.ArgumentParser(description="kaf-cli 繁體中文電子書轉換器圖形介面")
    parser.add_argument("--web", action="store_true", help="強制以 Web 瀏覽器模式啟動 (適合無螢幕環境或遠端伺服器)")
    parser.add_argument("--port", type=int, default=8080, help="Web 模式之通訊埠 (預設 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Web 模式之綁定 IP (預設 0.0.0.0)")
    args = parser.parse_args()

    # 如果明確要求 Web 模式
    if args.web:
        from kaf_gui.web_server import run_web_server
        run_web_server(port=args.port, host=args.host)
        return

    # 嘗試啟動 PyQt5 桌面版
    try:
        from PyQt5.QtWidgets import QApplication
        from kaf_gui.app import run_desktop_app
        run_desktop_app()
    except Exception as e:
        err_msg = str(e)
        print(f"[提示] 無法啟動桌面圖形視窗 ({err_msg})。")
        print("[提示] 自動為您切換至 Web 瀏覽器模式...")
        from kaf_gui.web_server import run_web_server
        run_web_server(port=args.port, host=args.host)

if __name__ == "__main__":
    main()
