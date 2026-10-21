#!/usr/bin/env python3
"""
G_Finance Mobile & a-Shell Webview Launcher
==========================================
Usage:
    python webview.py
    python3 webview.py

Designed specifically for iOS a-Shell Shortcuts, mobile devices, and desktop:
1. Health checks if G_Finance server is already alive on port 8765.
2. If already running, immediately re-opens the webview without port conflicts.
3. If not running, launches the server with socket reuse (SO_REUSEADDR) and
   verifies HTTP 200 before launching internalbrowser / openurl, completely
   preventing the blank page issue on reopen.
"""

from __future__ import annotations

import os
import sys
import time
import socket
import argparse
import threading
from typing import Optional

# Ensure working directory is this file's directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
try:
    os.chdir(BASE_DIR)
except Exception:
    pass

from web_server import (
    find_free_port,
    is_server_alive,
    DashboardRequestHandler,
    get_lan_ip,
    ServerClass,
)

DEFAULT_PORT = 8765
DEFAULT_HOST = "0.0.0.0"


def is_pythonista() -> bool:
    """Check if running inside Pythonista 3 on iOS."""
    try:
        import ui
        return hasattr(ui, "WebView") and hasattr(ui, "View")
    except ImportError:
        return False


def launch_pythonista_view(url: str, server=None):
    """Launches full-screen native iOS WebView inside Pythonista 3 with full navigation controls."""
    try:
        from pythonista_app import GFinancePythonistaApp
        app = GFinancePythonistaApp(url=url, server=server)
        v = app.build_ui()
        v.present("fullscreen", hide_title_bar=False)
        try:
            v.wait_modal()
        finally:
            app.cleanup()
    except Exception as e:
        print(f"[Pythonista UI] Error presenting custom view: {e}, falling back to basic view...")
        import ui
        v = ui.View()
        v.name = "G_Finance"
        v.background_color = "#121212"
        wv = ui.WebView(frame=v.bounds, flex="WH")
        wv.load_url(url)
        v.add_subview(wv)
        v.present("fullscreen", hide_title_bar=False)
        try:
            v.wait_modal()
        finally:
            if server is not None:
                try:
                    server.shutdown()
                    server.server_close()
                except Exception:
                    pass


def launch_browser(url: str) -> bool:
    """Launches webview in Pythonista, a-Shell (internalbrowser / openurl), or desktop browser."""
    if is_pythonista():
        launch_pythonista_view(url)
        return True

    # 1. Try a-Shell commands:
    # - internalbrowser opens modal overlay webview inside a-Shell
    # - openurl opens system Safari
    # - open opens system URL scheme
    for cmd in [f"internalbrowser '{url}'", f"openurl '{url}'", f"open '{url}'"]:
        try:
            if os.system(f"{cmd} 2>/dev/null") == 0:
                return True
        except Exception:
            pass

    # 2. Desktop fallback
    try:
        import webbrowser
        return webbrowser.open(url)
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="G_Finance Mobile Webview & a-Shell Shortcut Launcher",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="Host address")
    parser.add_argument("--no-view", dest="auto_view", action="store_false", default=True, help="Don't auto-open browser")
    args = parser.parse_args()

    target_port = args.port

    # Step 1: Health check if server is ALREADY running on the target port
    if is_server_alive(target_port):
        url = f"http://localhost:{target_port}"
        print("=" * 64)
        print("🏛️  G_FINANCE MOBILE WEBVIEW")
        print("=" * 64)
        print(f"✅ G_Finance server is already active at {url}")
        print("🚀 Opening webview interface...")
        print("=" * 64)
        if args.auto_view:
            launch_browser(url)
        return

    # Step 2: Find free port (with SO_REUSEADDR reuse)
    actual_port = find_free_port(target_port, host=args.host)
    url = f"http://localhost:{actual_port}"
    lan_ip = get_lan_ip()

    print("=" * 64)
    print("🏛️  G_FINANCE MOBILE WEBVIEW")
    print("=" * 64)
    print(f"📱 Local / a-Shell URL:   {url}")
    print(f"🌐 Wi-Fi / Network URL:    http://{lan_ip}:{actual_port}")
    print("=" * 64)

    # Step 3: Start server in background thread
    server = ServerClass((args.host, actual_port), DashboardRequestHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Step 3.5: Startup sync with Google Sheet if configured
    try:
        from google_sheet_sync import get_google_sheet_sync
        sync_mgr = get_google_sheet_sync()
        if sync_mgr.is_configured() and sync_mgr.config.get("auto_sync_on_startup", True):
            print("☁️ Checking Google Sheet for latest updates...")
            threading.Thread(target=sync_mgr.perform_sync, daemon=True).start()
    except Exception:
        pass

    # Step 4: Health check polling until server is verified HTTP 200 (prevents blank page!)
    ready = False
    for _ in range(35):
        if is_server_alive(actual_port, timeout=0.25):
            ready = True
            break
        time.sleep(0.08)

    if ready:
        print(f"🚀 Server verified ready! Opening interface: {url}")
    else:
        print(f"⚠️ Opening interface: {url}")

    # Step 5: Launch browser / a-Shell webview / Pythonista webview
    if is_pythonista():
        if args.auto_view:
            launch_pythonista_view(url, server=server)
        return

    if args.auto_view:
        launch_browser(url)

    # Step 6: Keep alive in a-Shell foreground
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping G_Finance server...")
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
