#!/usr/bin/env python3
"""
G_Finance Pythonista 3 Native iOS UI Launcher
=============================================
Designed specifically for Pythonista 3 on iOS (iPhone / iPad).
Uses Pythonista's built-in `ui` module (UIKit) to present a full-screen,
touch-optimized, responsive financial dashboard with native navigation controls.

Features:
- Native Pythonista `ui.View` container with full-screen presentation
- High-performance `ui.WebView` loaded with G_Finance dashboard
- Native iOS Navigation Bar buttons:
  * 🔄 Reload / Refresh
  * ◀ / ▶ History Back & Forward
  * 🌐 Open in Mobile Safari
  * ☁️ Trigger Google Sheet Sync
- Native `ui.ActivityIndicator` spinner during page and quote loads
- Automatic background server lifecycle management with clean shutdown on close
- Rotation & split-view adaptive (flex='WH')
"""

from __future__ import annotations

import os
import sys
import time
import socket
import threading
from typing import Optional

# Ensure working directory is this file's directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
try:
    os.chdir(BASE_DIR)
except Exception:
    pass

try:
    import ui
    PYTHONISTA_UI_AVAILABLE = True
except ImportError:
    ui = None
    PYTHONISTA_UI_AVAILABLE = False

try:
    import console
except ImportError:
    console = None

from web_server import (
    find_free_port,
    is_server_alive,
    DashboardRequestHandler,
    get_lan_ip,
    ServerClass,
)

DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"


def make_button_item(icon_name: str, fallback_title: str, action) -> Any:
    """Creates a ui.ButtonItem with iOS icon if available, or fallback text."""
    if not PYTHONISTA_UI_AVAILABLE:
        return None
    try:
        img = ui.Image.named(icon_name)
        if img:
            item = ui.ButtonItem(image=img)
            item.action = action
            return item
    except Exception:
        pass
    item = ui.ButtonItem(title=fallback_title)
    item.action = action
    return item


class GFinanceWebViewDelegate:
    """Delegate for tracking WebView loading states and activity spinner."""
    def __init__(self, activity_indicator):
        self.indicator = activity_indicator

    def webview_did_start(self, webview):
        if self.indicator:
            self.indicator.start()

    def webview_did_finish(self, webview):
        if self.indicator:
            self.indicator.stop()

    def webview_did_fail(self, webview, error):
        if self.indicator:
            self.indicator.stop()
        print(f"[Pythonista UI] WebView load error: {error}")


class GFinancePythonistaApp:
    """Manages the Pythonista 3 native UI view and background server."""

    def __init__(self, url: str, server=None):
        self.url = url
        self.server = server
        self.view: Optional[ui.View] = None
        self.webview: Optional[ui.WebView] = None
        self.indicator: Optional[ui.ActivityIndicator] = None

    def build_ui(self) -> ui.View:
        v = ui.View()
        v.name = "G_Finance Portfolio"
        v.background_color = "#121212"
        v.tint_color = "#1a73e8"

        # Web view fills full bounds with automatic resizing
        wv = ui.WebView(frame=v.bounds, flex="WH")
        wv.scales_page_to_fit = True
        v.add_subview(wv)
        self.webview = wv

        # Centered Activity Indicator while initial server/dashboard loads
        indicator = ui.ActivityIndicator(style=ui.ACTIVITY_INDICATOR_STYLE_WHITE_LARGE)
        indicator.center = (v.width * 0.5, v.height * 0.5)
        indicator.flex = "LRTB"
        indicator.hides_when_stopped = True
        v.add_subview(indicator)
        self.indicator = indicator

        # Set delegate to control spinner
        wv.delegate = GFinanceWebViewDelegate(indicator)

        # Right Navigation Buttons: Sync, Safari, Refresh
        btn_refresh = make_button_item("iob:ios_refresh_empty_32", "⟳ Refresh", self.on_refresh)
        btn_safari = make_button_item("iob:ios_browsers_outline_32", "Safari", self.on_open_safari)
        btn_sync = make_button_item("iob:ios_cloud_upload_outline_32", "☁️ Sync", self.on_sync)

        right_items = [item for item in [btn_refresh, btn_safari, btn_sync] if item is not None]
        v.right_button_items = right_items

        # Left Navigation Buttons: Back, Forward
        btn_back = make_button_item("iob:ios_arrow_back_32", "◀ Back", self.on_back)
        btn_forward = make_button_item("iob:ios_arrow_forward_32", "▶ Next", self.on_forward)
        left_items = [item for item in [btn_back, btn_forward] if item is not None]
        v.left_button_items = left_items

        # Clean shutdown hook when view is closed
        def will_close():
            self.cleanup()

        v.will_close = will_close
        self.view = v

        # Trigger load
        indicator.start()
        wv.load_url(self.url)
        return v

    def on_refresh(self, sender):
        if self.webview:
            if self.indicator:
                self.indicator.start()
            self.webview.reload()
            if console:
                console.hud_alert("Reloading...", "none", 0.8)

    def on_back(self, sender):
        if self.webview and hasattr(self.webview, "go_back"):
            self.webview.go_back()

    def on_forward(self, sender):
        if self.webview and hasattr(self.webview, "go_forward"):
            self.webview.go_forward()

    def on_open_safari(self, sender):
        try:
            import webbrowser
            webbrowser.open(self.url)
            if console:
                console.hud_alert("Opened in Safari", "success", 1.0)
        except Exception as e:
            print(f"Could not open Safari: {e}")

    def on_sync(self, sender):
        def _do_sync():
            try:
                from google_sheet_sync import get_google_sheet_sync
                sync = get_google_sheet_sync()
                res = sync.perform_sync()
                msg = res.get("message", "Sync completed") if isinstance(res, dict) else "Sync completed"
                if console:
                    console.hud_alert(msg, "success" if res.get("success", False) else "error", 1.5)
                if self.webview:
                    self.webview.reload()
            except Exception as e:
                if console:
                    console.hud_alert(f"Sync error: {e}", "error", 2.0)

        threading.Thread(target=_do_sync, daemon=True).start()

    def cleanup(self):
        """Stops the local G_Finance server when the Pythonista window closes."""
        if self.server is not None:
            print("\n[Pythonista UI] Closing view. Shutting down G_Finance server...")
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None


def launch_pythonista_app(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST):
    """Starts the background server and launches the native Pythonista ui.View."""
    if not PYTHONISTA_UI_AVAILABLE:
        print("[Pythonista UI] Pythonista `ui` module not available on this platform.")
        print("Launching default browser/webview fallback...")
        import webview
        webview.main()
        return

    # Check if server is already running
    server_instance = None
    if not is_server_alive(port, host=host):
        actual_port = find_free_port(port, host=host)
        print(f"[Pythonista UI] Starting G_Finance backend on {host}:{actual_port}...")
        server_instance = ServerClass((host, actual_port), DashboardRequestHandler)
        t = threading.Thread(target=server_instance.serve_forever, daemon=True)
        t.start()
        target_port = actual_port
    else:
        target_port = port
        print(f"[Pythonista UI] Reusing active G_Finance server on port {target_port}...")

    # Wait briefly for server readiness
    url = f"http://{host}:{target_port}"
    for _ in range(40):
        if is_server_alive(target_port, host=host, timeout=0.2):
            break
        time.sleep(0.05)

    print(f"[Pythonista UI] Presenting native iOS view for {url}...")
    app = GFinancePythonistaApp(url=url, server=server_instance)
    v = app.build_ui()
    v.present("fullscreen", hide_title_bar=False)


def main():
    """Default to 100% native Pythonista UIKit GUI."""
    if "--web" in sys.argv:
        launch_pythonista_app()
    else:
        import pythonista_native_ui
        pythonista_native_ui.main()


if __name__ == "__main__":
    main()
