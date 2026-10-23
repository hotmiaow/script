"""
web_server.py
Zero-dependency, mobile-first Web & PWA server for Google Finance Portfolio Tracker.
Optimized for:
- Apple iPhone (Touch-friendly single-column, bottom navigation, cards)
- Apple iPad (Adaptive 2-column tablet layout, split view)
- Desktop PC / Mac (Widescreen multi-column dashboard)
- a-Shell & iSH (Runs standalone offline on iOS with Python standard library)
"""

from __future__ import annotations

import os
import sys
import time
import json
import socket
import threading
import tempfile
import math
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
try:
    from http.server import ThreadingHTTPServer as ServerClass
except ImportError:
    from http.server import HTTPServer as ServerClass
ServerClass.daemon_threads = True
ServerClass.allow_reuse_address = True

from urllib.parse import urlparse, parse_qs
from typing import Optional, Callable, Dict, Any, List, Tuple

import csv_manager
import financial_calc
import report_generator
from currency_converter import get_currency_converter

_SERVER_INSTANCE: Optional[ServerClass] = None
_SERVER_THREAD: Optional[threading.Thread] = None
_PORT: int = 8765
_HOST: str = "0.0.0.0"
_DATA_CALLBACK: Optional[Callable] = None
_API_CHART_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def get_lan_ip() -> str:
    """Detects local LAN IP address for Wi-Fi access from iPhone/iPad."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def is_server_alive(port: int = 8765, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """Checks if a G_Finance server is already healthy and responding on port."""
    import urllib.request
    try:
        req = urllib.request.Request(
            f"http://{host}:{port}/api/device",
            headers={"User-Agent": "G_Finance HealthCheck"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def find_free_port(start_port: int = 8765, max_attempts: int = 20, host: str = "0.0.0.0") -> int:
    """Finds an open localhost port starting from start_port, allowing socket reuse."""
    # If G_Finance server is already alive and running on start_port, reuse it directly
    if is_server_alive(start_port):
        return start_port

    for p in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if hasattr(socket, "SO_REUSEPORT"):
                    try:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                    except OSError:
                        pass
                s.bind((host, p))
                return p
            except OSError:
                continue
    return start_port


def parse_device_info(user_agent: str) -> Dict[str, Any]:
    """Detects device type from User-Agent string."""
    ua = (user_agent or "").lower()
    if "ipad" in ua or ("macintosh" in ua and "mobile" in ua):
        dev = "ipad"
        name = "Apple iPad"
        is_touch = True
    elif "iphone" in ua or "ipod" in ua:
        dev = "iphone"
        name = "Apple iPhone"
        is_touch = True
    elif "android" in ua:
        dev = "android"
        name = "Android Device"
        is_touch = True
    elif "macintosh" in ua or "mac os x" in ua:
        dev = "mac"
        name = "Apple Mac (Desktop)"
        is_touch = False
    elif "windows" in ua:
        dev = "windows"
        name = "Windows PC"
        is_touch = False
    elif "linux" in ua:
        dev = "linux"
        name = "Linux PC"
        is_touch = False
    else:
        dev = "desktop"
        name = "Desktop / Web Browser"
        is_touch = False

    return {
        "device_type": dev,
        "device_name": name,
        "is_touch": is_touch,
        "raw_user_agent": user_agent,
    }


# =============================================================================
# PWA MANIFEST & SERVICE WORKER
# =============================================================================

MANIFEST_JSON = json.dumps({
    "name": "G_Finance Portfolio & FIRE",
    "short_name": "G_Finance",
    "description": "Google Finance Portfolio & Bernstein FIRE Retirement Tracker",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#000000",
    "theme_color": "#0a84ff",
    "orientation": "portrait-primary",
    "icons": [
        {
            "src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%230a84ff'/><text x='50' y='65' font-size='50' font-family='sans-serif' text-anchor='middle' fill='white'>📈</text></svg>",
            "sizes": "192x192 512x512",
            "type": "image/svg+xml",
            "purpose": "any maskable"
        }
    ]
}, indent=2)

SERVICE_WORKER_JS = """
const CACHE_NAME = 'gfinance-v2';
const STATIC_URLS = ['/', '/manifest.json'];

self.addEventListener('install', (e) => {
    e.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_URLS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then((keys) => Promise.all(
            keys.map((k) => { if (k !== CACHE_NAME) return caches.delete(k); })
        ))
    );
    self.clients.claim();
});

self.addEventListener('fetch', (e) => {
    if (e.request.method !== 'GET') return;
    if (e.request.url.includes('/api/')) return;
    e.respondWith(
        fetch(e.request)
            .then((res) => {
                if (res && res.status === 200) {
                    const clone = res.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone)).catch(() => {});
                }
                return res;
            })
            .catch(() => caches.match(e.request).then((cached) => cached || fetch(e.request)))
    );
});
"""


# =============================================================================
# RESPONSIVE, TOUCH-OPTIMIZED HTML5 APP TEMPLATE
# =============================================================================

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>G_Finance &bull; Portfolio & FIRE</title>

    <!-- iOS Standalone Web App Meta Tags -->
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="G_Finance">
    <meta name="theme-color" content="#000000">
    <link rel="manifest" href="/manifest.json">
    <link rel="apple-touch-icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%230a84ff'/><text x='50' y='65' font-size='50' font-family='sans-serif' text-anchor='middle' fill='white'>📈</text></svg>">

    <script>
        (function() {
            try {
                var t = localStorage.getItem('gfinance_theme');
                if (t === 'light') {
                    document.documentElement.classList.add('theme-light');
                }
            } catch (e) {}
        })();
    </script>

    <style>
        :root {
            --bg-body: #000000;
            --bg-card: #1c1c1e;
            --bg-card-subtle: #2c2c2e;
            --bg-main: #2c2c2e;
            --border-color: #38383a;
            --text-main: #ffffff;
            --text-dark: #ffffff;
            --text-muted: #8e8e93;
            --accent-blue: #0a84ff;
            --accent-green: #30d158;
            --accent-yellow: #ffd60a;
            --accent-red: #ff453a;
            --accent-purple: #bf5af2;
            --safe-bottom: env(safe-area-inset-bottom, 16px);
            --safe-top: env(safe-area-inset-top, 20px);
            --safe-left: env(safe-area-inset-left, 0px);
            --safe-right: env(safe-area-inset-right, 0px);
        }

        :root.theme-light, body.theme-light {
            --bg-body: #f2f2f7;
            --bg-card: #ffffff;
            --bg-card-subtle: #e5e5ea;
            --bg-main: #ffffff;
            --border-color: #d1d1d6;
            --text-main: #000000;
            --text-dark: #000000;
            --text-muted: #6c6c70;
            --accent-blue: #007aff;
            --accent-green: #34c759;
            --accent-yellow: #ff9500;
            --accent-red: #ff3b30;
            --accent-purple: #af52de;
        }

        * {
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
        }

        html, body {
            overflow-x: hidden;
            width: 100%;
            max-width: 100vw;
        }

        body {
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            min-height: 100vh;
            padding-top: max(var(--safe-top), 12px);
            padding-bottom: calc(75px + var(--safe-bottom));
            touch-action: manipulation;
            user-select: none;
            -webkit-user-select: none;
        }

        /* Container Layout */
        .app-container {
            max-width: 1180px;
            margin: 0 auto;
            padding-left: max(12px, var(--safe-left));
            padding-right: max(12px, var(--safe-right));
            padding-top: 0;
            padding-bottom: 0;
            width: 100%;
            box-sizing: border-box;
        }

        /* Top Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 0 12px 0;
            gap: 8px;
            flex-wrap: wrap;
            width: 100%;
        }
        .header-title {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-shrink: 0;
        }
        .header-title h1 {
            margin: 0;
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            white-space: nowrap;
        }
        .device-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 2px 7px;
            background: var(--bg-card-subtle);
            border-radius: 20px;
            font-size: 0.70rem;
            font-weight: 600;
            color: var(--accent-blue);
            border: 1px solid var(--border-color);
            white-space: nowrap;
        }

        .header-controls {
            display: flex;
            align-items: center;
            gap: 5px;
            flex-wrap: wrap;
            justify-content: flex-end;
            max-width: 100%;
        }
        select, .btn-icon {
            background: var(--bg-card);
            color: var(--text-main);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 5px 8px;
            font-size: 0.78rem;
            font-weight: 600;
            outline: none;
            cursor: pointer;
            box-sizing: border-box;
        }
        .header-controls select {
            max-width: 110px;
        }
        #curr-select {
            max-width: 82px;
        }
        #lang-select {
            max-width: 85px;
        }
        .btn-icon:active {
            transform: scale(0.95);
        }

        /* Navigation */
        /* Top Navigation for Desktop & iPad */
        .desktop-nav {
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
        }
        .nav-btn {
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 0.95rem;
            font-weight: 600;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .nav-btn.active {
            background: var(--bg-card);
            color: var(--accent-blue);
        }

        /* Mobile Bottom Tab Bar (iPhone thumb-friendly) */
        .bottom-tab-bar {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: rgba(28, 28, 30, 0.94);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: space-around;
            padding-top: 6px;
            padding-bottom: max(var(--safe-bottom), 10px);
            padding-left: max(12px, var(--safe-left));
            padding-right: max(12px, var(--safe-right));
            z-index: 1000;
        }
        body.theme-light .bottom-tab-bar {
            background: rgba(255, 255, 255, 0.94);
        }
        .tab-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 0.68rem;
            font-weight: 600;
            padding: 4px 12px;
            min-width: 65px;
            cursor: pointer;
        }
        .tab-item span.icon {
            font-size: 1.35rem;
        }
        .tab-item.active {
            color: var(--accent-blue);
        }
        .tab-item:active {
            transform: scale(0.92);
        }

        /* Cards & Components */
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 18px;
            margin-bottom: 14px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            transition: transform 0.1s ease;
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        .card-title {
            font-size: 0.8rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
        }

        /* Hero Net Worth Card */
        .hero-amount {
            font-size: 2.2rem;
            font-weight: 800;
            letter-spacing: -1px;
            margin: 4px 0 8px 0;
            color: var(--accent-green);
        }
        .hero-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }
        .pill {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 5px 10px;
            background: var(--bg-card-subtle);
            border-radius: 12px;
            font-size: 0.78rem;
            font-weight: 600;
        }
        .pill.pos { color: var(--accent-green); background: rgba(48, 209, 88, 0.15); }
        .pill.neg { color: var(--accent-red); background: rgba(255, 69, 58, 0.15); }
        .pill.blue { color: var(--accent-blue); background: rgba(10, 132, 255, 0.15); }
        .pill.amber { color: var(--accent-yellow); background: rgba(255, 214, 10, 0.15); }

        /* Gauges & Horizontal Visual Bars */
        .visual-bar-wrap {
            margin: 12px 0 6px 0;
        }
        .bar-label-row {
            display: flex;
            justify-content: space-between;
            font-size: 0.75rem;
            font-weight: 700;
            margin-bottom: 5px;
        }
        .progress-track {
            height: 14px;
            background: var(--bg-card-subtle);
            border-radius: 7px;
            overflow: hidden;
            display: flex;
            position: relative;
        }
        .progress-fill {
            height: 100%;
            transition: width 0.3s ease;
        }
        .fill-blue { background: var(--accent-blue); }
        .fill-green { background: var(--accent-green); }
        .fill-yellow { background: var(--accent-yellow); }
        .fill-red { background: var(--accent-red); }
        .fill-gap { background: rgba(255, 69, 58, 0.35); border: 1px dashed var(--accent-red); }

        /* Speedometer & Timeline */
        .gauge-note {
            font-size: 0.73rem;
            color: var(--text-muted);
            margin-top: 5px;
        }

        /* 3-Zone Speedometer Meter */
        .speedometer-track {
            height: 12px;
            border-radius: 6px;
            display: flex;
            overflow: hidden;
            margin-top: 14px;
        }
        .needle-box {
            position: relative;
            height: 18px;
            margin-top: 2px;
        }
        .needle-marker {
            position: absolute;
            transform: translateX(-50%);
            font-size: 0.72rem;
            font-weight: 800;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        /* Responsive Grid for iPad & PC */
        .grid-2col {
            display: grid;
            grid-template-columns: 1fr;
            gap: 14px;
        }

        /* Holdings & Watchlist Cards Responsive Grid */
        #holdings-cards-container, #watchlist-cards-container {
            display: grid;
            grid-template-columns: 1fr;
            gap: 10px;
        }
        .desktop-table-card {
            grid-column: 1 / -1;
        }

        @media (min-width: 768px) {
            .grid-2col {
                grid-template-columns: 1fr 1fr;
            }
            #holdings-cards-container, #watchlist-cards-container {
                grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
                gap: 12px;
            }
            .bottom-tab-bar {
                display: none; /* Hide bottom tabs on iPad/PC */
            }
            body {
                padding-bottom: 30px;
            }
        }

        @media (max-width: 767px) {
            .desktop-nav {
                display: none; /* Hide top tabs on iPhone portrait */
            }
        }

        /* Phone in Landscape Mode (Horizontal holding, compact height) */
        @media (orientation: landscape) and (max-height: 500px) {
            body {
                padding-top: max(var(--safe-top), 6px);
                padding-bottom: max(20px, calc(12px + var(--safe-bottom)));
            }
            .app-container {
                padding-left: max(16px, var(--safe-left));
                padding-right: max(16px, var(--safe-right));
            }
            header {
                padding: 3px 0 6px 0;
            }
            .header-title h1 {
                font-size: 1.1rem;
            }
            /* Hide bottom tab bar in horizontal phone mode to maximize vertical reading area */
            .bottom-tab-bar {
                display: none !important;
            }
            /* Show compact top nav in horizontal phone mode */
            .desktop-nav {
                display: flex !important;
                margin-bottom: 10px;
                padding-bottom: 6px;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
            }
            .desktop-nav .nav-btn {
                padding: 6px 12px;
                font-size: 0.82rem;
                white-space: nowrap;
            }
            .grid-2col {
                grid-template-columns: 1fr 1fr;
            }
            #holdings-cards-container, #watchlist-cards-container {
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 10px;
            }
            .hero-amount {
                font-size: 1.8rem;
            }
            .fab-refresh {
                bottom: max(14px, var(--safe-bottom)) !important;
                right: max(16px, calc(12px + var(--safe-right))) !important;
                width: 44px;
                height: 44px;
                font-size: 1.15rem;
            }
            .modal-overlay {
                align-items: center;
            }
            .modal-card {
                border-radius: 16px;
                max-height: 90vh;
                padding: 14px 18px;
            }
        }

        /* iPad & Large Tablets in Landscape Mode */
        @media (min-width: 1024px) and (orientation: landscape) {
            .app-container {
                max-width: 1240px;
                padding-left: max(20px, var(--safe-left));
                padding-right: max(20px, var(--safe-right));
            }
            .grid-2col {
                grid-template-columns: 1fr 1fr;
                gap: 18px;
            }
            #holdings-cards-container, #watchlist-cards-container {
                grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
                gap: 14px;
            }
        }

        @media (max-width: 480px) and (orientation: portrait) {
            .app-container {
                padding-left: max(8px, var(--safe-left));
                padding-right: max(8px, var(--safe-right));
            }
            header {
                padding: 4px 0 8px 0;
            }
            .header-title h1 {
                font-size: 1.15rem;
            }
            .device-badge {
                display: none; /* Auto-hide badge on narrow portrait screens */
            }
            .header-controls {
                gap: 4px;
            }
            .header-controls select, .header-controls .btn-icon {
                padding: 5px 6px;
                font-size: 0.74rem;
            }
            #curr-select {
                max-width: 72px;
            }
            #port-select {
                max-width: 90px;
            }
            #lang-select {
                max-width: 72px;
            }
        }

        /* Holdings & Watchlist Touch Cards */
        .item-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 14px 16px;
            margin-bottom: 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }
        .item-card:active {
            transform: scale(0.98);
        }
        .item-left strong {
            font-size: 1.05rem;
            letter-spacing: -0.3px;
        }
        .item-left div {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 2px;
        }
        .item-right {
            text-align: right;
        }
        .item-price {
            font-size: 1.05rem;
            font-weight: 700;
        }
        .item-badge {
            margin-top: 4px;
            display: inline-block;
        }

        /* Floating Action Button (FAB) */
        .fab-refresh {
            position: fixed;
            bottom: calc(85px + var(--safe-bottom));
            right: max(20px, calc(16px + var(--safe-right)));
            width: 52px;
            height: 52px;
            border-radius: 26px;
            background: var(--accent-blue);
            color: #ffffff;
            border: none;
            box-shadow: 0 6px 18px rgba(10, 132, 255, 0.45);
            font-size: 1.3rem;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            z-index: 990;
        }
        .fab-refresh:active {
            transform: scale(0.92);
        }
        .fab-refresh.spinning {
            animation: spin 0.8s linear infinite;
            pointer-events: none;
            opacity: 0.85;
        }
        @keyframes spin {
            100% { transform: rotate(360deg); }
        }
        @media (min-width: 768px) {
            .fab-refresh {
                bottom: max(24px, calc(16px + var(--safe-bottom)));
                right: max(24px, calc(16px + var(--safe-right)));
            }
        }

        /* Tab Content Switching */
        .tab-pane {
            display: none;
        }
        .tab-pane.active {
            display: block;
            animation: fadeIn 0.15s ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(4px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Interactive Chart Tab Styles */
        .chart-tf-group {
            display: flex;
            gap: 4px;
            background: var(--bg-card-subtle);
            padding: 3px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            overflow-x: auto;
            max-width: 100%;
        }
        .tf-btn {
            background: none;
            border: none;
            color: var(--text-muted);
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .tf-btn.active {
            background: var(--accent-blue);
            color: #ffffff;
        }
        .tf-btn:active {
            transform: scale(0.95);
        }
        .chart-canvas-wrapper {
            position: relative;
            width: 100%;
            height: 280px;
            touch-action: none;
            user-select: none;
            -webkit-user-select: none;
        }
        #price-chart-canvas {
            width: 100%;
            height: 100%;
            display: block;
            border-radius: 8px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.76rem;
            padding: 4px 8px;
            background: var(--bg-card-subtle);
            border-radius: 8px;
            border: 1px solid var(--border-color);
            cursor: pointer;
            transition: transform 0.1s;
        }
        .legend-item:active {
            transform: scale(0.97);
        }
        .legend-dot {
            width: 10px;
            height: 10px;
            border-radius: 5px;
            flex-shrink: 0;
        }

        /* Responsive Table for PC mode */
        .desktop-table-card {
            overflow-x: auto;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }
        th, td {
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }
        th {
            color: var(--text-muted);
            font-size: 0.75rem;
            text-transform: uppercase;
        }

        /* Sub-Tool Navigation & Touch Controls */
        .tool-subnav {
            display: flex;
            gap: 8px;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            padding-bottom: 8px;
            margin-bottom: 14px;
            scrollbar-width: none;
        }
        .tool-subnav::-webkit-scrollbar {
            display: none;
        }
        .tool-tab-btn {
            flex: 0 0 auto;
            padding: 8px 14px;
            border-radius: 20px;
            font-size: 0.82rem;
            font-weight: 600;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            color: var(--text-dark);
            cursor: pointer;
            white-space: nowrap;
        }
        .tool-tab-btn.active {
            background: var(--accent-blue);
            color: #ffffff;
            border-color: var(--accent-blue);
        }
        .tool-subpane {
            display: none;
        }
        .tool-subpane.active {
            display: block;
            animation: fadeIn 0.15s ease-out;
        }
        .form-group {
            margin-bottom: 12px;
        }
        .form-row {
            display: flex;
            gap: 10px;
            margin-bottom: 10px;
        }
        .form-col {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .form-label {
            font-size: 0.76rem;
            font-weight: 600;
            color: var(--text-muted);
        }
        .form-control {
            background: var(--bg-main);
            border: 1px solid var(--border-color);
            color: var(--text-dark);
            padding: 10px 12px;
            border-radius: 10px;
            font-size: 0.88rem;
            outline: none;
            width: 100%;
            box-sizing: border-box;
        }
        .form-control:focus {
            border-color: var(--accent-blue);
        }
        .btn-action-primary {
            background: var(--accent-blue);
            color: #ffffff;
            border: none;
            padding: 11px 16px;
            border-radius: 10px;
            font-size: 0.88rem;
            font-weight: 700;
            cursor: pointer;
            width: 100%;
            text-align: center;
            display: block;
            text-decoration: none;
            box-sizing: border-box;
        }
        .btn-action-primary:active {
            transform: scale(0.98);
        }
        .btn-action-success {
            background: var(--accent-green);
            color: #ffffff;
            border: none;
            padding: 11px 16px;
            border-radius: 10px;
            font-size: 0.88rem;
            font-weight: 700;
            cursor: pointer;
            width: 100%;
            text-align: center;
        }
        .btn-action-success:active {
            transform: scale(0.98);
        }
        .result-box {
            background: var(--bg-main);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 14px;
            margin-top: 14px;
            font-size: 0.84rem;
        }
        .result-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .result-row:last-child {
            margin-bottom: 0;
        }
        .quick-btn-group {
            display: flex;
            gap: 6px;
            margin-top: 6px;
            overflow-x: auto;
        }
        .quick-btn {
            background: var(--bg-main);
            border: 1px solid var(--border-color);
            color: var(--text-dark);
            border-radius: 8px;
            padding: 5px 10px;
            font-size: 0.74rem;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
        }

        /* Toast Notifications */
        .toast-notify {
            position: fixed;
            top: max(var(--safe-top), 16px);
            left: 50%;
            transform: translateX(-50%) translateY(-100px);
            background: rgba(28, 28, 30, 0.95);
            color: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 10px 20px;
            font-size: 0.84rem;
            font-weight: 600;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
            z-index: 9999;
            transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.25s;
            opacity: 0;
            pointer-events: none;
            display: flex;
            align-items: center;
            gap: 8px;
            max-width: 90vw;
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
        }
        .toast-notify.visible {
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }
        body.theme-light .toast-notify {
            background: rgba(255, 255, 255, 0.95);
            color: #000000;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
        }

        /* Detail & Action Modals */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.65);
            backdrop-filter: blur(5px);
            -webkit-backdrop-filter: blur(5px);
            display: none;
            justify-content: center;
            align-items: flex-end;
            z-index: 9990;
        }
        .modal-overlay.active {
            display: flex;
        }
        @media (min-width: 768px) {
            .modal-overlay {
                align-items: center;
            }
        }
        .modal-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 22px 22px 0 0;
            width: 100%;
            max-width: 500px;
            max-height: 85vh;
            overflow-y: auto;
            padding: 20px;
            box-sizing: border-box;
            animation: slideUp 0.25s ease-out;
        }
        @media (min-width: 768px) {
            .modal-card {
                border-radius: 20px;
                animation: fadeIn 0.2s ease-out;
            }
        }
        @keyframes slideUp {
            from { transform: translateY(100%); }
            to { transform: translateY(0); }
        }
    </style>
</head>
<body class="platform-detect">

    <div class="app-container">
        <!-- Top App Bar -->
        <header>
            <div class="header-title">
                <h1>🏛️ G_Finance</h1>
                <span class="device-badge" id="platform-badge" data-i18n="detecting">Detecting...</span>
            </div>
            <div class="header-controls">
                <select id="curr-select" onchange="onCurrencyChange(this.value)">
                    <option value="CAD">CAD C$</option>
                    <option value="USD" selected>USD $</option>
                    <option value="TWD">TWD NT$</option>
                    <option value="HKD">HKD HK$</option>
                    <option value="EUR">EUR €</option>
                </select>
                <select id="port-select" onchange="onPortfolioChange(this.value)">
                    <option value="All" data-i18n="all_portfolios">All Portfolios</option>
                </select>
                <select id="lang-select" onchange="setLanguage(this.value)" title="Language">
                    <option value="en">🇺🇸 EN</option>
                    <option value="zh_TW">🇭🇰 繁中</option>
                    <option value="zh_CN">🇨🇳 简中</option>
                </select>
                <button class="btn-icon" id="btn-cloud-sync" onclick="triggerGoogleSheetSync()" title="Google Sheet Sync" data-i18n-title="btn_google_sheet_sync">☁️</button>
                <button class="btn-icon" onclick="toggleTheme()" title="Toggle Dark/Light" data-i18n-title="theme_toggle">🌓</button>
            </div>
        </header>

        <!-- Top Navigation Bar for iPad & Desktop -->
        <nav class="desktop-nav">
            <button class="nav-btn active" id="dnav-portfolio" onclick="switchTab('portfolio')" data-i18n="nav_portfolio">📊 Portfolio</button>
            <button class="nav-btn" id="dnav-chart" onclick="switchTab('chart')" data-i18n="nav_chart">📈 Chart</button>
            <button class="nav-btn" id="dnav-fire" onclick="switchTab('fire')" data-i18n="nav_fire">🔥 FIRE Retirement</button>
            <button class="nav-btn" id="dnav-watchlist" onclick="switchTab('watchlist')" data-i18n="nav_watchlist">👁️ Watchlist</button>
            <button class="nav-btn" id="dnav-tools" onclick="switchTab('tools')" data-i18n="nav_tools">⚙️ Tools & Info</button>
        </nav>

        <!-- ============================================================= -->
        <!-- TAB 1: PORTFOLIO HOLDINGS -->
        <!-- ============================================================= -->
        <div id="tab-portfolio" class="tab-pane active">
            <!-- Hero Net Worth Card -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title" data-i18n="net_worth_title">Total Portfolio Net Worth</span>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span id="sheet-sync-badge" class="pill" style="cursor:pointer; font-size:0.72rem; padding:2px 8px; font-weight:700;" onclick="openGoogleSheetModal()">☁️ Sync</span>
                        <span id="last-sync-time" style="font-size: 0.72rem; color: var(--text-muted);" data-i18n="synced_now">Synced Just Now</span>
                    </div>
                </div>
                <div class="hero-amount" id="net-worth-val">$0.00</div>
                <div class="hero-pill-row">
                    <span class="pill" id="pill-gain">+0.00 (+0.0%)</span>
                    <span class="pill blue" id="pill-div">Div: $0.00/yr</span>
                    <span class="pill amber" id="pill-yield">Yield: 0.0%</span>
                </div>

                <!-- Live FX Rates Indicator Badge -->
                <div style="margin-top: 10px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 6px;">
                    <span id="fx-rates-badge" style="font-size: 0.72rem; color: var(--text-muted); font-weight: 600;">💱 1 USD = 1.399 CAD | 7.845 HKD</span>
                </div>

                <!-- Step 1 Asset Allocation Visual Split -->
                <div class="visual-bar-wrap" style="margin-top: 14px;">
                    <div class="bar-label-row">
                        <span id="alloc-eq-lbl" style="color: var(--accent-blue)">📈 Equity: $0 (0%)</span>
                        <span id="alloc-safe-lbl" style="color: var(--accent-green)">🛡️ Safe Buffer: $0 (0%)</span>
                    </div>
                    <div class="progress-track">
                        <div class="progress-fill fill-blue" id="alloc-eq-bar" style="width: 75%;"></div>
                        <div class="progress-fill fill-green" id="alloc-safe-bar" style="width: 25%;"></div>
                    </div>
                </div>
            </div>

            <!-- Holdings View -->
            <div class="card-header" style="margin: 16px 4px 8px 4px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="card-title" id="holdings-count-title">Active Holdings (0)</span>
                    <button class="quick-btn" style="color: var(--accent-blue); padding: 3px 8px; font-size: 0.75rem;" onclick="openAddHoldingModal()" data-i18n="btn_add">➕ 新增</button>
                </div>
                <span id="btn-toggle-view" style="font-size: 0.75rem; color: var(--accent-blue); cursor: pointer;" onclick="toggleHoldingsView()" data-i18n="toggle_to_table">📊 切換表格檢視 ⮀</span>
            </div>

            <!-- Touch-Friendly Mobile Card List -->
            <div id="holdings-cards-container">
                <!-- Injected via JS -->
            </div>
        </div>

        <!-- ============================================================= -->
        <!-- TAB 2: INTERACTIVE CHART & ASSET ALLOCATION (GOOGLE FINANCE) -->
        <!-- ============================================================= -->
        <div id="tab-chart" class="tab-pane">
            <!-- Chart Hero Card -->
            <div class="card" style="margin-bottom: 14px;">
                <!-- Header with Scope Selector & Dynamic Info -->
                <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <select id="chart-symbol-select" class="form-control" style="font-weight: 700; font-size: 0.92rem; padding: 6px 10px; width: auto; max-width: 220px;" onchange="onChartSymbolChange(this.value)">
                                <option value="PORTFOLIO">📈 總資產 Portfolio</option>
                            </select>

                            <div style="display: flex; align-items: center; gap: 4px;">
                                <label for="chart-metric-select" style="font-size: 0.78rem; font-weight: 600; color: var(--text-muted); white-space: nowrap;" data-i18n="chart_metric_lbl">Metric:</label>
                                <select id="chart-metric-select" class="form-control" style="font-size: 0.82rem; padding: 5px 8px; width: auto;" onchange="onChartMetricChange(this.value)">
                                    <option value="total" data-i18n="chart_metric_total">Total Value</option>
                                    <option value="price" data-i18n="chart_metric_price">Stock Price (Per Share)</option>
                                    <option value="growth" data-i18n="chart_metric_growth">Net Growth / P&L (Excl. Invested)</option>
                                    <option value="growth_div" data-i18n="chart_metric_growth_div">Net Growth + Dividends</option>
                                    <option value="div_only" data-i18n="chart_metric_div_only">Dividends Only</option>
                                </select>
                            </div>

                            <div style="display: flex; align-items: center; gap: 4px;">
                                <label for="chart-style-select" style="font-size: 0.78rem; font-weight: 600; color: var(--text-muted); white-space: nowrap;" data-i18n="chart_style_lbl">Style:</label>
                                <select id="chart-style-select" class="form-control" style="font-size: 0.82rem; padding: 5px 8px; width: auto;" onchange="onChartStyleChange(this.value)">
                                    <option value="area" data-i18n="chart_style_area">Area</option>
                                    <option value="line" data-i18n="chart_style_line">Line</option>
                                </select>
                            </div>
                        </div>
                        <div id="chart-display-price" style="font-size: 2.1rem; font-weight: 800; letter-spacing: -1px; margin-top: 6px;">$0.00</div>
                        <div style="display: flex; align-items: center; gap: 8px; margin-top: 2px;">
                            <span id="chart-display-change" class="pill pos">+0.00 (+0.0%)</span>
                            <span id="chart-display-time" style="font-size: 0.75rem; color: var(--text-muted);" data-i18n="realtime_trend">即時走勢</span>
                        </div>
                    </div>

                    <!-- Timeframe Pills -->
                    <div class="chart-tf-group">
                        <button class="tf-btn" data-tf="1D" onclick="setChartTimeframe('1D')">1D</button>
                        <button class="tf-btn" data-tf="5D" onclick="setChartTimeframe('5D')">5D</button>
                        <button class="tf-btn active" data-tf="1M" onclick="setChartTimeframe('1M')">1M</button>
                        <button class="tf-btn" data-tf="6M" onclick="setChartTimeframe('6M')">6M</button>
                        <button class="tf-btn" data-tf="YTD" onclick="setChartTimeframe('YTD')">YTD</button>
                        <button class="tf-btn" data-tf="1Y" onclick="setChartTimeframe('1Y')">1Y</button>
                        <button class="tf-btn" data-tf="5Y" onclick="setChartTimeframe('5Y')">5Y</button>
                        <button class="tf-btn" data-tf="MAX" onclick="setChartTimeframe('MAX')">MAX</button>
                    </div>
                </div>

                <!-- Interactive Touch Canvas Container -->
                <div class="chart-canvas-wrapper">
                    <canvas id="price-chart-canvas"></canvas>
                    <div id="chart-loading" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: none; align-items: center; justify-content: center; background: rgba(0,0,0,0.35); border-radius: 8px; font-weight: 600;" data-i18n="chart_loading">載入走勢中...</div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px; font-size: 0.72rem; color: var(--text-muted);">
                    <span id="chart-tip-text" data-i18n="chart_tip">👆 手指滑動或滑鼠懸停可查閱任意點位</span>
                    <span id="chart-ref-close">昨收參考: $0.00</span>
                </div>
            </div>

            <!-- Asset Allocation Donut Chart Card -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title" id="chart-donut-title" data-i18n="chart_donut_title">投資組合資產配置圖</span>
                    <span class="pill blue" id="chart-donut-count">0 標的</span>
                </div>
                <div style="display: flex; flex-direction: column; align-items: center; gap: 16px; margin-top: 10px;">
                    <div style="position: relative; width: 220px; height: 220px;">
                        <canvas id="donut-chart-canvas" width="220" height="220"></canvas>
                        <div id="donut-center-info" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; pointer-events: none;">
                            <div style="font-size: 0.70rem; color: var(--text-muted);" data-i18n="total_assets">總資產</div>
                            <div id="donut-center-val" style="font-size: 0.95rem; font-weight: 800;">$0</div>
                        </div>
                    </div>
                    <!-- Allocation Legend List -->
                    <div id="donut-legend-container" style="width: 100%; display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px;">
                        <!-- Injected via JS -->
                    </div>
                </div>
            </div>
        </div>

        <!-- ============================================================= -->
        <!-- TAB 3: BERNSTEIN FIRE RETIREMENT (ALL GAUGES & GRAPHICS) -->
        <!-- ============================================================= -->
        <div id="tab-fire" class="tab-pane">
            <div class="grid-2col">
                <!-- Gap 1: Safe Liability Matching Buffer (20-25 Yrs) -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title" data-i18n="fire_safe_title">🛡️ Safe Liability Buffer (25-Yr)</span>
                        <span class="pill" id="fire-safe-badge" data-i18n="fire_auditing">Auditing...</span>
                    </div>
                    <div style="font-size: 1.4rem; font-weight: 800;" id="fire-safe-val">$0.00</div>
                    <div class="visual-bar-wrap">
                        <div class="bar-label-row">
                            <span id="fire-safe-cur">Current Safe: $0</span>
                            <span id="fire-safe-tgt">Target: $0</span>
                        </div>
                        <div class="progress-track">
                            <div class="progress-fill fill-green" id="fire-safe-bar" style="width: 60%;"></div>
                            <div class="progress-fill fill-gap" id="fire-safe-gap-bar" style="width: 40%;"></div>
                        </div>
                        <div class="gauge-note" id="fire-safe-note">🛡️ Buffer covers 15.0 of 25.0 planned years</div>
                    </div>
                </div>

                <!-- Gap 2: Passive Annual Dividend Cash Flow Gap -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title" data-i18n="fire_div_title">💵 Passive Dividend Gap</span>
                        <span class="pill" id="fire-div-badge" data-i18n="fire_auditing">Auditing...</span>
                    </div>
                    <div style="font-size: 1.4rem; font-weight: 800;" id="fire-div-val">$0.00 / yr</div>
                    <div class="visual-bar-wrap">
                        <div class="bar-label-row">
                            <span id="fire-div-cur">Current Div: $0</span>
                            <span id="fire-div-tgt">Target RLE: $0</span>
                        </div>
                        <div class="progress-track">
                            <div class="progress-fill fill-blue" id="fire-div-bar" style="width: 45%;"></div>
                            <div class="progress-fill fill-gap" id="fire-div-gap-bar" style="width: 55%;"></div>
                        </div>
                        <div class="gauge-note" id="fire-div-note">📈 Crossover in 6.5 yrs @ 5% dividend growth</div>
                    </div>
                </div>

                <!-- Gap 3: Bernstein SWR 3.2% Principal Target Gap -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title" data-i18n="fire_cap_title">🏛️ Bernstein 3.2% Capital Gap</span>
                        <span class="pill" id="fire-cap-badge" data-i18n="fire_auditing">Auditing...</span>
                    </div>
                    <div style="font-size: 1.4rem; font-weight: 800;" id="fire-cap-val">$0.00</div>
                    <div class="visual-bar-wrap">
                        <div class="bar-label-row">
                            <span id="fire-cap-cur">Current Wealth: $0</span>
                            <span id="fire-cap-tgt">Target Principal: $0</span>
                        </div>
                        <div class="progress-track">
                            <div class="progress-fill fill-yellow" id="fire-cap-bar" style="width: 50%;"></div>
                            <div class="progress-fill fill-gap" id="fire-cap-gap-bar" style="width: 50%;"></div>
                        </div>
                        <div class="gauge-note" id="fire-cap-note">💰 Monthly savings needed: $1,200/mo</div>
                    </div>
                </div>

                <!-- Burn Rate Speedometer (Corridor Gauge) -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title" data-i18n="fire_burn_title">⚡ Burn Rate Corridor Speedometer</span>
                        <span class="pill" id="fire-burn-badge">2.1% (Safe)</span>
                    </div>
                    <div style="font-size: 1.4rem; font-weight: 800; color: var(--accent-green);" id="fire-burn-rate">2.14%</div>
                    <!-- 3-zone horizontal corridor meter -->
                    <div class="speedometer-track">
                        <div style="width: 33.3%; background: var(--accent-green);" title="<2.0% Safe"></div>
                        <div style="width: 25.0%; background: var(--accent-yellow);" title="2.0-3.5% Sustainable"></div>
                        <div style="width: 41.7%; background: var(--accent-red);" title=">3.5% Warning"></div>
                    </div>
                    <div class="needle-box">
                        <div class="needle-marker" id="burn-needle" style="left: 35%; color: var(--accent-green);">
                            ▲ <span style="font-size: 0.68rem;" id="burn-needle-txt">Current: 2.14%</span>
                        </div>
                    </div>
                    <div class="bar-label-row" style="font-size: 0.68rem; color: var(--text-muted); margin-top: 8px;">
                        <span data-i18n="burn_zone_safe">&lt;2.0% Safe</span>
                        <span data-i18n="burn_zone_swr">2.0-3.5% SWR</span>
                        <span data-i18n="burn_zone_danger">&gt;3.5% Warning</span>
                    </div>
                </div>
            </div>

            <!-- Life Cycle Timeline Horizontal Bar -->
            <div class="card">
                <div class="card-title" data-i18n="fire_timeline_title">⏳ Life Cycle & Retirement Horizon Timeline</div>
                <div class="bar-label-row" style="margin-top: 10px;">
                    <span id="tl-now" data-i18n="tl_age_now">● Age 45 (Now)</span>
                    <span id="tl-ret" style="color: var(--accent-green)" data-i18n="tl_age_fire">★ Age 60 (FIRE)</span>
                    <span id="tl-end" style="color: var(--text-muted)" data-i18n="tl_age_end">🏁 Age 90</span>
                </div>
                <div class="progress-track" style="height: 16px;">
                    <div class="progress-fill fill-blue" id="tl-accum-bar" style="width: 33%;"></div>
                    <div class="progress-fill fill-green" id="tl-dist-bar" style="width: 67%;"></div>
                </div>
                <div class="bar-label-row" style="font-size: 0.72rem; margin-top: 6px; color: var(--text-muted);">
                    <span id="tl-accum-txt" data-i18n="tl_accum_phase">⏳ 15y Accumulation</span>
                    <span id="tl-dist-txt" data-i18n="tl_dist_phase">🏖️ 30y Distribution Horizon</span>
                </div>
            </div>
        </div>

        <!-- ============================================================= -->
        <!-- TAB 4: WATCHLIST -->
        <!-- ============================================================= -->
        <div id="tab-watchlist" class="tab-pane">
            <div class="card-header" style="margin: 0 4px 10px 4px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="card-title" data-i18n="watchlist_title">Real-Time Watchlist & Targets</span>
                    <button class="quick-btn" style="color: var(--accent-blue); padding: 3px 8px; font-size: 0.75rem;" onclick="openAddWatchlistModal()" data-i18n="btn_add">➕ 新增</button>
                </div>
                <span class="pill blue" id="wl-count-badge">0 Tracked</span>
            </div>

            <!-- Touch Cards List -->
            <div id="watchlist-cards-container">
                <!-- Injected via JS -->
            </div>
        </div>

        <!-- ============================================================= -->
        <!-- TAB 5: COMPREHENSIVE FINANCIAL TOOLS & DIAGNOSTICS -->
        <!-- ============================================================= -->
        <div id="tab-tools" class="tab-pane">
            <!-- Sub-Tools Scrollable Navigation Bar -->
            <div class="tool-subnav">
                <button class="tool-tab-btn active" id="btn-st-whatif" onclick="switchToolSubTab('whatif')" data-i18n="st_whatif">💡 What-If</button>
                <button class="tool-tab-btn" id="btn-st-rebalance" onclick="switchToolSubTab('rebalance')" data-i18n="st_rebalance">⚖️ 再平衡</button>
                <button class="tool-tab-btn" id="btn-st-drip" onclick="switchToolSubTab('drip')" data-i18n="st_drip">💧 股息複利</button>
                <button class="tool-tab-btn" id="btn-st-split" onclick="switchToolSubTab('split')" data-i18n="st_split">✂️ 股票分割</button>
                <button class="tool-tab-btn" id="btn-st-selling" onclick="switchToolSubTab('selling')" data-i18n="st_selling">💰 賣出損益</button>
                <button class="tool-tab-btn" id="btn-st-health" onclick="switchToolSubTab('health')" data-i18n="st_health">🩺 健康檢查</button>
                <button class="tool-tab-btn" id="btn-st-reports" onclick="switchToolSubTab('reports')" data-i18n="st_reports">📄 財務報表</button>
                <button class="tool-tab-btn" id="btn-st-cloud" onclick="switchToolSubTab('cloud')" data-i18n="st_cloud">☁️ 雲端同步</button>
                <button class="tool-tab-btn" id="btn-st-backup" onclick="switchToolSubTab('backup')" data-i18n="st_backup">💾 資料備份</button>
                <button class="tool-tab-btn" id="btn-st-diag" onclick="switchToolSubTab('diag')" data-i18n="st_diag">📱 系統診斷</button>
            </div>

            <!-- SUBPANE 1: WHAT-IF SCENARIO CALCULATOR -->
            <div id="subpane-whatif" class="tool-subpane active">
                <div class="card">
                    <div class="card-title" data-i18n="whatif_title">💡 What-If 模擬加碼試算機</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;" data-i18n="whatif_desc">
                        模擬加碼或買進新標的，即時預估對總資產、持有股數、配置比例與年股息的影響。
                    </div>

                    <div class="form-group">
                        <label class="form-label" data-i18n="whatif_sel_lbl">選擇持倉標的 (或手動輸入)</label>
                        <select id="whatif-select" class="form-control" onchange="onWhatIfHoldingSelected(this.value)">
                            <option value="">-- 自訂代碼 (Custom Ticker) --</option>
                        </select>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label" data-i18n="lbl_symbol">股票代碼 (Symbol)</label>
                            <input id="whatif-ticker" class="form-control" placeholder="如 VOO, AAPL" value="VOO" oninput="runWhatIfCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label" data-i18n="lbl_price">預估股價 (Price)</label>
                            <input id="whatif-price" type="number" step="any" class="form-control" placeholder="100.0" value="480.0" oninput="runWhatIfCalc()">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label" data-i18n="lbl_yield">預估殖利率 % (Yield)</label>
                            <input id="whatif-yield" type="number" step="0.01" class="form-control" placeholder="1.8" value="1.5" oninput="runWhatIfCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label" data-i18n="lbl_amount">加碼金額 ($ Amount)</label>
                            <input id="whatif-amt" type="number" step="any" class="form-control" value="5000" oninput="runWhatIfCalc()">
                        </div>
                    </div>

                    <div style="display: flex; gap: 6px; margin: 10px 0 16px 0; overflow-x: auto; padding-bottom: 4px;">
                        <button class="quick-btn" onclick="addWhatIfAmt(1000)">+1,000</button>
                        <button class="quick-btn" onclick="addWhatIfAmt(5000)">+5,000</button>
                        <button class="quick-btn" onclick="addWhatIfAmt(10000)">+10,000</button>
                        <button class="quick-btn" onclick="addWhatIfAmt(20000)">+20,000</button>
                        <button class="quick-btn" onclick="setWhatIfAmt(5000)" data-i18n="whatif_reset_5k">重設 5,000</button>
                    </div>

                    <div style="font-size: 0.84rem; line-height: 2.0; background: var(--bg-card-subtle); padding: 12px; border-radius: 12px;">
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="whatif_res_tot">總資產變化:</span><strong id="whatif-res-total">$0.00 → $0.00</strong></div>
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="whatif_res_shs">預計新增股數:</span><span id="whatif-res-shares">0.00 shs</span></div>
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="whatif_res_alloc">該標的配置佔比:</span><strong id="whatif-res-alloc">0.0% → 0.0%</strong></div>
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="whatif_res_div">被動年股息增長:</span><span id="whatif-res-div" style="color: var(--accent-green);">+$0.00/yr (+$0.00/mo)</span></div>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 2: ASSET REBALANCING CALCULATOR -->
            <div id="subpane-rebalance" class="tool-subpane">
                <div class="card">
                    <div class="card-title" data-i18n="rebal_title">⚖️ 資產再平衡試算機</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;" data-i18n="rebal_desc">
                        自訂各標的目標配置比例或套用模型，試算達成目標所需的買賣金額與股數。
                    </div>

                    <div class="form-group">
                        <label class="form-label" data-i18n="rebal_cash_lbl">額外注入新資金 (現金加碼)</label>
                        <input id="rebal-cash" type="number" step="any" class="form-control" value="0" oninput="runRebalanceCalc()">
                    </div>

                    <div style="display: flex; gap: 8px; margin-bottom: 14px;">
                        <button class="quick-btn" onclick="applyRebalancePreset('equal')" data-i18n="rebal_btn_equal">均等權重 (Equal)</button>
                        <button class="quick-btn" onclick="applyRebalancePreset('reset')" data-i18n="rebal_btn_reset">重設為現況</button>
                    </div>

                    <div id="rebalance-holdings-list">
                        <!-- Injected via JS -->
                    </div>

                    <div style="font-size: 0.84rem; line-height: 2.0; background: var(--bg-card-subtle); padding: 12px; border-radius: 12px; margin-top: 14px;">
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="rebal_sum_lbl">目標權重總和:</span><strong id="rebal-total-weight">100.0%</strong></div>
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="rebal_total_val_lbl">再平衡總資產規模:</span><strong id="rebal-total-val">$0.00</strong></div>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 3: DRIP COMPOUNDING CALCULATOR -->
            <div id="subpane-drip" class="tool-subpane">
                <div class="card">
                    <div class="card-title" data-i18n="drip_title">💧 股息再投資與複利試算 (DRIP)</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;" data-i18n="drip_desc">
                        試算股息複利滾存帶來的現金流指數級增長。
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label" data-i18n="drip_init_div">目前年股息 (Annual Div)</label>
                            <input id="drip-init-div" type="number" step="any" class="form-control" oninput="runDripCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label" data-i18n="drip_div_growth">年股息成長率 % (Growth)</label>
                            <input id="drip-div-growth" type="number" step="0.1" class="form-control" value="5.0" oninput="runDripCalc()">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label" data-i18n="drip_return">年化再投資報酬率 %</label>
                            <input id="drip-return" type="number" step="0.1" class="form-control" value="7.0" oninput="runDripCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label" data-i18n="drip_extra">每年額外加碼資金</label>
                            <input id="drip-extra" type="number" step="any" class="form-control" value="0" oninput="runDripCalc()">
                        </div>
                    </div>

                    <div style="overflow-x: auto; margin-top: 14px;">
                        <table style="width: 100%; font-size: 0.80rem;">
                            <thead>
                                <tr>
                                    <th data-i18n="th_year">年期</th>
                                    <th data-i18n="th_ann_div">年被動股息</th>
                                    <th data-i18n="th_monthly_flow">月被動現金流</th>
                                    <th data-i18n="th_total_wealth">複利滾存總資產</th>
                                </tr>
                            </thead>
                            <tbody id="drip-tbody">
                                <!-- Injected via JS -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 4: STOCK SPLIT & REVERSE SPLIT -->
            <div id="subpane-split" class="tool-subpane">
                <div class="card">
                    <div class="card-title" data-i18n="split_title">✂️ 股票分割 / 反分割計算機</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;" data-i18n="split_desc">
                        當持股進行正分割 (如 2:1, 10:1) 或反分割 (如 1:2) 時，自動校正股數與每股平均買進成本。
                    </div>

                    <div class="form-group">
                        <label class="form-label" data-i18n="split_sel_lbl">選擇持倉標的</label>
                        <select id="split-select" class="form-control" onchange="onSplitHoldingSelected(this.value)">
                            <option value="">-- 手動輸入 --</option>
                        </select>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label" data-i18n="split_pre_shs">分割前持有股數</label>
                            <input id="split-shares" type="number" step="any" class="form-control" value="10" oninput="runSplitCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label" data-i18n="split_pre_cost">分割前每股成本 ($)</label>
                            <input id="split-cost" type="number" step="any" class="form-control" value="200" oninput="runSplitCalc()">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label" data-i18n="split_num">分割分子 (換成幾股)</label>
                            <input id="split-num" type="number" step="any" class="form-control" value="2" oninput="runSplitCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label" data-i18n="split_den">分割分母 (原本幾股)</label>
                            <input id="split-den" type="number" step="any" class="form-control" value="1" oninput="runSplitCalc()">
                        </div>
                    </div>

                    <div style="display: flex; gap: 6px; margin: 10px 0 16px 0; overflow-x: auto; padding-bottom: 4px;">
                        <button class="quick-btn" onclick="setSplitRatio(2,1)">2:1</button>
                        <button class="quick-btn" onclick="setSplitRatio(3,1)">3:1</button>
                        <button class="quick-btn" onclick="setSplitRatio(4,1)">4:1</button>
                        <button class="quick-btn" onclick="setSplitRatio(10,1)">10:1</button>
                        <button class="quick-btn" onclick="setSplitRatio(1,2)" data-i18n="split_ratio_1_2">1:2 反分割</button>
                        <button class="quick-btn" onclick="setSplitRatio(1,4)" data-i18n="split_ratio_1_4">1:4 反分割</button>
                    </div>

                    <div style="font-size: 0.84rem; line-height: 2.0; background: var(--bg-card-subtle); padding: 12px; border-radius: 12px;">
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="split_res_shs_lbl">校正後持有股數:</span><strong id="split-res-shares">20.0000 shs</strong></div>
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="split_res_cost_lbl">校正後每股平均成本:</span><strong id="split-res-cost">$100.00 / sh</strong></div>
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="split_res_tot_lbl">總投資成本守恆:</span><span id="split-res-total" style="color: var(--accent-green);">$2,000.00 (不變 ✓)</span></div>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 5: SELLING & PROFIT-TAKING CALCULATOR -->
            <div id="subpane-selling" class="tool-subpane">
                <div class="card">
                    <div class="card-title" data-i18n="sell_title">💰 獲利了結與賣出損益試算機</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;" data-i18n="sell_desc">
                        試算部分或全部賣出時的已實現資本利得、現金入帳與剩餘持倉價值。
                    </div>

                    <div class="form-group">
                        <label class="form-label" data-i18n="sell_sel_lbl">選擇持倉標的</label>
                        <select id="sell-select" class="form-control" onchange="onSellHoldingSelected(this.value)">
                            <option value="">-- 手動輸入 --</option>
                        </select>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label" data-i18n="sell_tot_shs">目前總持有股數</label>
                            <input id="sell-tot-shares" type="number" step="any" class="form-control" value="100" oninput="runSellCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label" data-i18n="sell_cost_price">平均每股買進成本 ($)</label>
                            <input id="sell-cost-price" type="number" step="any" class="form-control" value="150" oninput="runSellCalc()">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label" data-i18n="sell_qty">預計賣出股數</label>
                            <input id="sell-qty" type="number" step="any" class="form-control" value="50" oninput="runSellCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label" data-i18n="sell_price">預計每股賣出價 ($)</label>
                            <input id="sell-price" type="number" step="any" class="form-control" value="220" oninput="runSellCalc()">
                        </div>
                    </div>

                    <div style="display: flex; gap: 6px; margin: 10px 0 16px 0; overflow-x: auto; padding-bottom: 4px;">
                        <button class="quick-btn" onclick="setSellPct(0.25)" data-i18n="sell_pct_25">賣出 25%</button>
                        <button class="quick-btn" onclick="setSellPct(0.50)" data-i18n="sell_pct_50">賣出 50%</button>
                        <button class="quick-btn" onclick="setSellPct(0.75)" data-i18n="sell_pct_75">賣出 75%</button>
                        <button class="quick-btn" onclick="setSellPct(1.00)" data-i18n="sell_pct_100">全部清倉 (100%)</button>
                    </div>

                    <div style="font-size: 0.84rem; line-height: 2.0; background: var(--bg-card-subtle); padding: 12px; border-radius: 12px;">
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="sell_res_proceeds_lbl">賣出回收現金總額:</span><strong id="sell-res-proceeds">$11,000.00</strong></div>
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="sell_res_gain_lbl">已實現資本利得 (獲利):</span><strong id="sell-res-gain" style="color: var(--accent-green);">+$3,500.00 (+46.7%)</strong></div>
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="sell_res_rem_shs_lbl">剩餘持倉股數:</span><span id="sell-res-rem-shares">50.00 shs</span></div>
                        <div style="display: flex; justify-content: space-between;"><span data-i18n="sell_res_rem_val_lbl">剩餘部位市值:</span><strong id="sell-res-rem-val">$11,000.00</strong></div>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 6: DATA INTEGRITY & AUDIT -->
            <div id="subpane-health" class="tool-subpane">
                <div class="card">
                    <div class="card-title" data-i18n="health_title">🩺 資料完整性檢查與一鍵修復</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;" data-i18n="health_desc">
                        自動審核 portfolio.csv 與 watchlist.csv，檢查是否有未填成本、缺少幣別、未分類標的或異常記錄。
                    </div>

                    <div style="display: flex; gap: 10px; margin-bottom: 14px;">
                        <button class="btn-action-primary" style="flex: 1;" onclick="scanDataHealth()" data-i18n="btn_scan">🔍 執行完整掃描</button>
                        <button class="btn-action-success" style="flex: 1;" onclick="repairDataHealth()" data-i18n="btn_repair">🛠️ 一鍵修復異常</button>
                    </div>

                    <div style="background: var(--bg-card-subtle); border-radius: 12px; padding: 12px; font-size: 0.82rem; min-height: 80px;">
                        <div id="health-summary" style="font-weight: 700; margin-bottom: 6px;" data-i18n="health_init_sum">點擊上方按鈕開始檢查</div>
                        <div id="health-details" style="color: var(--text-muted); white-space: pre-wrap; line-height: 1.6;" data-i18n="health_init_det">支援自動校正常見資料格式問題。</div>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 7: REPORTS -->
            <div id="subpane-reports" class="tool-subpane">
                <div class="card">
                    <div class="card-title" data-i18n="reports_title">📄 完整財務執行摘要報表</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;" data-i18n="reports_desc">
                        產出專業的 HTML / PDF 格式財務報表，包含淨值圖表、資產配置分析、持股明細及收益預測。
                    </div>

                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <a id="btn-open-report" href="/api/report?currency=USD" target="_blank" class="btn-action-primary" data-i18n="btn_open_report">
                            📑 開啟完整 HTML 財務報表 (新分頁)
                        </a>
                        <button class="btn-icon" style="padding: 10px; font-size: 0.84rem;" onclick="openReportInView()" data-i18n="btn_preview_report">
                            📱 在頁面內嵌預覽報表
                        </button>
                    </div>

                    <div id="report-preview-wrap" style="display: none; margin-top: 14px; border-radius: 12px; overflow: hidden; border: 1px solid var(--border-color);">
                        <iframe id="report-iframe" style="width: 100%; height: 420px; border: none; background: #ffffff;"></iframe>
                    </div>
                </div>
            </div>

            <!-- SUBPANE: GOOGLE SHEET CLOUD SYNC -->
            <div id="subpane-cloud" class="tool-subpane">
                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div class="card-title" data-i18n="cloud_title" style="margin: 0;">☁️ Google 試算表雲端同步 (Cloud Sync)</div>
                        <span id="cloud-pane-badge" class="pill" style="font-size:0.75rem; padding: 2px 8px; font-weight: 700;">檢查中...</span>
                    </div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 14px;" data-i18n="cloud_desc">
                        使用 Google Sheets 試算表作為跨裝置雲端資料庫，無縫同步持倉、自選清單與交易歷史記錄。
                    </div>

                    <!-- Cloud Status Card -->
                    <div style="background: var(--bg-card-subtle); padding: 12px 14px; border-radius: 12px; margin-bottom: 14px; font-size: 0.82rem; line-height: 1.8;">
                        <div style="display:flex; justify-content:space-between;">
                            <span data-i18n="cloud_lbl_status">雲端連線狀態:</span>
                            <strong id="cloud-pane-status-txt">未設定</strong>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            <span data-i18n="cloud_lbl_last_sync">上次同步時間:</span>
                            <span id="cloud-pane-time-txt">-</span>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            <span data-i18n="cloud_lbl_device">本機裝置識別:</span>
                            <span id="cloud-pane-dev-txt" style="color: var(--text-muted); font-family: monospace; font-size: 0.76rem;">-</span>
                        </div>
                        <div id="cloud-pane-msg" style="margin-top: 6px; font-weight: 600; color: var(--text-muted);"></div>
                    </div>

                    <!-- Sync Actions Row -->
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; margin-bottom: 14px;">
                        <button class="btn-action-primary" style="padding: 10px; font-size: 0.85rem;" onclick="triggerGoogleSheetSync(true)">
                            🔄 <span data-i18n="btn_sync_now">立即雙向同步</span>
                        </button>
                        <button class="btn-action-primary" style="background: var(--bg-card-subtle); color: var(--text-main); border: 1px solid var(--border-color); padding: 10px; font-size: 0.85rem;" onclick="triggerGoogleSheetPush()">
                            ⬆️ <span data-i18n="btn_sync_push">上傳至 Google Sheet</span>
                        </button>
                        <button class="btn-action-primary" style="background: var(--bg-card-subtle); color: var(--text-main); border: 1px solid var(--border-color); padding: 10px; font-size: 0.85rem;" onclick="triggerGoogleSheetPull()">
                            ⬇️ <span data-i18n="btn_sync_pull">自 Google Sheet 下載</span>
                        </button>
                    </div>

                    <!-- Configuration Form -->
                    <div class="card-title" style="margin: 16px 0 8px 0; font-size: 0.92rem;" data-i18n="cloud_cfg_title">⚙️ Google Apps Script 設定</div>
                    <div class="form-group" style="margin-bottom: 10px;">
                        <label class="form-label" data-i18n="cloud_lbl_url">Google Apps Script Web App URL</label>
                        <input id="cloud-pane-url" class="form-control" placeholder="https://script.google.com/macros/s/.../exec">
                    </div>

                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 14px;">
                        <input type="checkbox" id="cloud-pane-autoupload" style="width: 16px; height: 16px; cursor: pointer;">
                        <label for="cloud-pane-autoupload" style="font-size: 0.82rem; cursor: pointer; user-select: none;" data-i18n="cloud_lbl_autoupload">編輯或交易時自動背景同步至雲端</label>
                    </div>

                    <div style="display: flex; gap: 8px; margin-bottom: 14px;">
                        <button class="btn-action-primary" style="background: var(--bg-card-subtle); color: var(--text-main); border: 1px solid var(--border-color); padding: 8px 14px; font-size: 0.82rem;" onclick="testGoogleSheetConnectionPane()">
                            🔌 <span data-i18n="btn_test_connection">測試連線</span>
                        </button>
                        <button class="btn-action-primary" style="flex: 1; padding: 8px 14px; font-size: 0.82rem;" onclick="saveGoogleSheetPaneConfig()">
                            💾 <span data-i18n="btn_save_config">儲存設定</span>
                        </button>
                    </div>

                    <!-- Apps Script Setup Guide -->
                    <details style="font-size: 0.78rem; color: var(--text-muted); background: var(--bg-card-subtle); padding: 10px 14px; border-radius: 10px; margin-top: 8px;">
                        <summary style="cursor: pointer; font-weight: 700; color: var(--accent-blue);" data-i18n="cloud_guide_summary">📖 30 秒快速安裝與部署教學 (點擊展開)</summary>
                        <div style="margin: 10px 0 6px 0; line-height: 1.7;" data-i18n="cloud_guide_steps">
                            1. 前往 Google 試算表建立新表格 (<a href="https://sheets.new" target="_blank" style="color:var(--accent-blue);">sheets.new</a>)<br>
                            2. 點選頂部選單「擴充功能」 &rarr; 「Apps Script」<br>
                            3. 貼上程式碼，點擊「部署」 &rarr; 「新增部署」 &rarr; 選擇「網頁應用程式」<br>
                            4. 執行身分選擇「我」，存取權限選擇「任何人 (Anyone)」<br>
                            5. 複製生成的網頁應用程式網址，貼至上方輸入框並儲存即可！
                        </div>
                        <button class="btn-action-primary" style="background: rgba(10,132,255,0.15); color: var(--accent-blue); padding: 8px 12px; font-size: 0.78rem; border: 1px solid var(--accent-blue); margin-top: 6px;" onclick="copyGoogleAppsScript()">
                            📋 <span data-i18n="btn_copy_script">複製 Google Apps Script 程式碼</span>
                        </button>
                    </details>
                </div>
            </div>

            <!-- SUBPANE 8: DATA BACKUP & EXPORT -->
            <div id="subpane-backup" class="tool-subpane">
                <div class="card">
                    <div class="card-title" data-i18n="backup_title">💾 資料匯出與備份下載</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;" data-i18n="backup_desc">
                        隨時下載持股與自選名單，保護您的財務資料安全無虞。
                    </div>

                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <a href="/api/export/csv" download="portfolio.csv" class="btn-action-primary" style="background: var(--bg-card); color: var(--text-dark); border: 1px solid var(--border-color);" data-i18n="btn_dl_portfolio">
                            📥 下載持股資料 (portfolio.csv)
                        </a>
                        <a href="/api/export/watchlist_csv" download="watchlist.csv" class="btn-action-primary" style="background: var(--bg-card); color: var(--text-dark); border: 1px solid var(--border-color);" data-i18n="btn_dl_watchlist">
                            📥 下載自選清單 (watchlist.csv)
                        </a>
                        <a href="/api/export/json" download="g_finance_backup.json" class="btn-action-primary" data-i18n="btn_dl_json">
                            📦 下載完整系統備份 (JSON Backup)
                        </a>
                    </div>

                    <div class="card-title" style="margin-top: 18px; font-size: 0.92rem;" data-i18n="cloud_backup_title">☁️ Google 試算表即時雲端同步</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 10px;" data-i18n="cloud_backup_desc">
                        與 Google Sheets 保持雙向同步，支援自動多版本備份與跨設備無縫接軌。
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn-action-primary" style="flex: 1; padding: 10px; font-size: 0.84rem;" onclick="triggerGoogleSheetSync(true)" data-i18n="btn_sync_now">
                            🔄 立即同步 Google 試算表
                        </button>
                        <button class="btn-action-primary" style="background: var(--bg-card-subtle); color: var(--text-main); border: 1px solid var(--border-color); padding: 10px 14px; font-size: 0.84rem;" onclick="switchToolSubTab('cloud')" data-i18n="btn_cloud_settings">
                            ⚙️ 雲端設定
                        </button>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 9: SYSTEM & DEVICE DIAGNOSTICS -->
            <div id="subpane-diag" class="tool-subpane">
                <div class="card">
                    <div class="card-title" data-i18n="diag_title">📱 系統與裝置診斷</div>
                    <div style="font-size: 0.82rem; line-height: 1.8; margin-top: 8px;">
                        <div><span data-i18n="diag_platform_lbl">執行平台辨識:</span> <strong id="diag-platform" style="color: var(--accent-blue)">-</strong></div>
                        <div><span data-i18n="diag_touch_lbl">觸控優化狀態:</span> <strong id="diag-touch">-</strong></div>
                        <div><span data-i18n="diag_res_lbl">螢幕解析度:</span> <strong id="diag-res">-</strong></div>
                        <div><span data-i18n="diag_pwa_lbl">獨立 PWA 模式:</span> <strong id="diag-standalone">-</strong></div>
                    </div>

                    <div style="display: flex; gap: 8px; margin-top: 14px;">
                        <button class="btn-icon" style="flex: 1;" onclick="forceLayout('iphone')" data-i18n="btn_mode_iphone">📱 iPhone 模式</button>
                        <button class="btn-icon" style="flex: 1;" onclick="forceLayout('ipad')" data-i18n="btn_mode_ipad">📟 iPad 模式</button>
                        <button class="btn-icon" style="flex: 1;" onclick="forceLayout('desktop')" data-i18n="btn_mode_pc">💻 PC 模式</button>
                    </div>

                    <div class="card-title" style="margin-top: 16px; font-size: 0.92rem;" data-i18n="quick_server_actions">⚡ 快速伺服器動作</div>
                    <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 8px;">
                        <button class="btn-icon" style="padding: 12px; font-size: 0.9rem;" onclick="triggerGoogleSheetSync(true)" data-i18n="btn_google_sheet_sync">
                            ☁️ 立即同步 Google 試算表
                        </button>
                        <button class="btn-icon" style="padding: 12px; font-size: 0.9rem;" onclick="triggerManualRefresh()" data-i18n="btn_refresh_quotes">
                            🔄 立即刷新所有股價行情
                        </button>
                        <button class="btn-icon" style="padding: 12px; font-size: 0.9rem; color: var(--accent-red);" onclick="stopServerRemote()" data-i18n="btn_stop_server">
                            🛑 停止 G_Finance 伺服器
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- ============================================================= -->
        <!-- ACTION SHEETS & TOUCH MODALS -->
        <!-- ============================================================= -->

        <!-- Modal 1: Holding Detail Sheet -->
        <div id="modal-holding-detail" class="modal-overlay" onclick="if(event.target===this)closeModal('modal-holding-detail')">
            <div class="modal-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 id="m-h-title" style="margin: 0; font-size: 1.15rem; color: var(--accent-blue);" data-i18n="holding_details">Stock Details</h3>
                    <button class="btn-icon" style="font-size: 1.1rem; padding: 4px 8px;" onclick="closeModal('modal-holding-detail')">✕</button>
                </div>
                <div style="font-size: 0.84rem; line-height: 1.9; background: var(--bg-card-subtle); padding: 12px; border-radius: 12px; margin-bottom: 14px;">
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_currency">幣種標別:</span><strong id="m-h-curr">USD ($)</strong></div>
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_cur_price">當前市價:</span><strong id="m-h-price">$0.00</strong></div>
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_shares">持有股數:</span><span id="m-h-shares">0 shs</span></div>
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_cost_basis">每股成本:</span><span id="m-h-cost">$0.00</span></div>
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_total_cost">成本總計:</span><span id="m-h-tot-cost">$0.00</span></div>
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_market_val">當前市值:</span><strong id="m-h-val">$0.00</strong></div>
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_unrealized_pl">未實現損益:</span><strong id="m-h-pl">+0.00 (+0.0%)</strong></div>
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_est_div">預估年股息:</span><span id="m-h-div" style="color: var(--accent-green);">$0.00/yr</span></div>
                </div>
                <div style="font-size: 0.76rem; font-weight: 700; color: var(--text-muted); margin-bottom: 8px;" data-i18n="quick_actions">🚀 快捷連動功能 (QUICK ACTIONS)</div>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <button id="btn-h-chart" class="btn-action-primary" style="background: rgba(10, 132, 255, 0.18); color: var(--accent-blue); border: 1px solid var(--accent-blue); padding: 10px; font-size: 0.85rem;" onclick="viewCurrentHoldingInChart()" data-i18n="btn_h_chart">📈 檢視即時走勢圖 (View Chart)</button>
                    <button id="btn-h-whatif" class="btn-action-primary" style="padding: 10px; font-size: 0.85rem;" data-i18n="btn_h_whatif">💡 帶入 What-If 加碼模擬試算</button>
                    <button id="btn-h-split" class="btn-action-primary" style="background: var(--bg-card-subtle); color: var(--text-main); border: 1px solid var(--border-color); padding: 10px; font-size: 0.85rem;" data-i18n="btn_h_split">✂️ 帶入股票分割 / 反分割計算機</button>
                    <button id="btn-h-sell" class="btn-action-primary" style="background: var(--bg-card-subtle); color: var(--text-main); border: 1px solid var(--border-color); padding: 10px; font-size: 0.85rem;" data-i18n="btn_h_sell">💰 帶入賣出獲利了結試算機</button>
                    <button id="btn-h-delete" class="btn-action-primary" style="background: rgba(255, 69, 58, 0.15); color: var(--accent-red); border: 1px solid var(--accent-red); padding: 9px; font-size: 0.82rem; margin-top: 4px;" data-i18n="btn_h_delete">🗑️ 刪除此持股標的</button>
                </div>
            </div>
        </div>

        <!-- Modal 2: Watchlist Detail Sheet -->
        <div id="modal-watchlist-detail" class="modal-overlay" onclick="if(event.target===this)closeModal('modal-watchlist-detail')">
            <div class="modal-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 id="m-w-title" style="margin: 0; font-size: 1.15rem; color: var(--accent-blue);" data-i18n="watchlist_details">Watchlist Item</h3>
                    <button class="btn-icon" style="font-size: 1.1rem; padding: 4px 8px;" onclick="closeModal('modal-watchlist-detail')">✕</button>
                </div>
                <div style="font-size: 0.84rem; line-height: 1.9; background: var(--bg-card-subtle); padding: 12px; border-radius: 12px; margin-bottom: 14px;">
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_w_curp">當前市價:</span><strong id="m-w-curp">$0.00</strong></div>
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_w_tgtp">目標買進價:</span><strong id="m-w-tgtp">$0.00</strong></div>
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_w_diff">距目標價差:</span><strong id="m-w-diff">-</strong></div>
                    <div style="display: flex; justify-content: space-between;"><span data-i18n="lbl_w_notes">備註標籤:</span><span id="m-w-notes">-</span></div>
                </div>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <button id="btn-w-chart" class="btn-action-primary" style="background: rgba(10, 132, 255, 0.18); color: var(--accent-blue); border: 1px solid var(--accent-blue); padding: 10px; font-size: 0.85rem;" onclick="viewCurrentWatchlistInChart()" data-i18n="btn_w_chart">📈 檢視即時走勢圖 (View Chart)</button>
                    <button id="btn-w-whatif" class="btn-action-primary" style="padding: 10px; font-size: 0.85rem;" data-i18n="btn_w_whatif">💡 帶入 What-If 模擬買進</button>
                    <button id="btn-w-delete" class="btn-action-primary" style="background: rgba(255, 69, 58, 0.15); color: var(--accent-red); border: 1px solid var(--accent-red); padding: 9px; font-size: 0.82rem;" data-i18n="btn_w_delete">🗑️ 從自選清單移除</button>
                </div>
            </div>
        </div>

        <!-- Modal 3: Add Holding -->
        <div id="modal-add-holding" class="modal-overlay" onclick="if(event.target===this)closeModal('modal-add-holding')">
            <div class="modal-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 style="margin: 0; font-size: 1.15rem;" data-i18n="add_holding_title">➕ 新增投資持股</h3>
                    <button class="btn-icon" style="font-size: 1.1rem; padding: 4px 8px;" onclick="closeModal('modal-add-holding')">✕</button>
                </div>
                <div class="form-row">
                    <div class="form-col">
                        <label class="form-label" data-i18n="lbl_sym_req">股票代碼 (Symbol)*</label>
                        <input id="add-h-sym" class="form-control" placeholder="如 VOO, AAPL" data-i18n-placeholder="ph_sym_h">
                    </div>
                    <div class="form-col">
                        <label class="form-label" data-i18n="lbl_name_opt">公司名稱 (Name)</label>
                        <input id="add-h-name" class="form-control" placeholder="可選填" data-i18n-placeholder="ph_name_h">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-col">
                        <label class="form-label" data-i18n="lbl_shares_req">持有股數 (Shares)*</label>
                        <input id="add-h-shares" type="number" step="any" class="form-control" placeholder="10" data-i18n-placeholder="ph_shares_h">
                    </div>
                    <div class="form-col">
                        <label class="form-label" data-i18n="lbl_cost_req">每股買進成本 (Cost)*</label>
                        <input id="add-h-price" type="number" step="any" class="form-control" placeholder="150.0" data-i18n-placeholder="ph_cost_h">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-col">
                        <label class="form-label" data-i18n="lbl_currency">幣別 (Currency)</label>
                        <select id="add-h-curr" class="form-control">
                            <option value="USD">USD ($)</option>
                            <option value="CAD">CAD (C$)</option>
                            <option value="TWD">TWD (NT$)</option>
                            <option value="HKD">HKD (HK$)</option>
                            <option value="EUR">EUR (€)</option>
                        </select>
                    </div>
                    <div class="form-col">
                        <label class="form-label" data-i18n="lbl_portfolio">所屬投資組合 (Portfolio)</label>
                        <input id="add-h-port" class="form-control" placeholder="如 Core, Tech" data-i18n-placeholder="ph_port_h">
                    </div>
                </div>
                <button class="btn-action-primary" style="margin-top: 10px;" onclick="submitAddHolding()" data-i18n="btn_confirm_add_h">確認新增持股</button>
            </div>
        </div>

        <!-- Modal 4: Add Watchlist -->
        <div id="modal-add-watchlist" class="modal-overlay" onclick="if(event.target===this)closeModal('modal-add-watchlist')">
            <div class="modal-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 style="margin: 0; font-size: 1.15rem;" data-i18n="add_watchlist_title">➕ 新增自選監控標的</h3>
                    <button class="btn-icon" style="font-size: 1.1rem; padding: 4px 8px;" onclick="closeModal('modal-add-watchlist')">✕</button>
                </div>
                <div class="form-row">
                    <div class="form-col">
                        <label class="form-label" data-i18n="lbl_sym_req">股票代碼 (Symbol)*</label>
                        <input id="add-w-sym" class="form-control" placeholder="如 NVDA, MSFT" data-i18n-placeholder="ph_sym_w">
                    </div>
                    <div class="form-col">
                        <label class="form-label" data-i18n="lbl_name_opt">標的名稱 (Name)</label>
                        <input id="add-w-name" class="form-control" placeholder="可選填" data-i18n-placeholder="ph_name_w">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-col">
                        <label class="form-label" data-i18n="lbl_tgt_req">目標買進價 (Target Price)*</label>
                        <input id="add-w-tgt" type="number" step="any" class="form-control" placeholder="120.0" data-i18n-placeholder="ph_tgt_w">
                    </div>
                    <div class="form-col">
                        <label class="form-label" data-i18n="lbl_currency">計價幣別 (Currency)</label>
                        <select id="add-w-curr" class="form-control">
                            <option value="USD">USD ($)</option>
                            <option value="CAD">CAD (C$)</option>
                            <option value="TWD">TWD (NT$)</option>
                            <option value="HKD">HKD (HK$)</option>
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label" data-i18n="lbl_notes_opt">備註說明 (Notes)</label>
                    <input id="add-w-notes" class="form-control" placeholder="例: 回檔至季線買進" data-i18n-placeholder="ph_notes_w">
                </div>
                <button class="btn-action-primary" style="margin-top: 10px;" onclick="submitAddWatchlist()" data-i18n="btn_confirm_add_w">確認加入自選</button>
            </div>
        </div>

        <!-- Modal 5: Google Sheet Cloud Sync Setup -->
        <div id="modal-google-sheet" class="modal-overlay" onclick="if(event.target===this)closeModal('modal-google-sheet')">
            <div class="modal-card" style="max-width: 540px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 style="margin: 0; font-size: 1.15rem; color: var(--accent-blue);">☁️ Google Sheet Cloud Sync</h3>
                    <button class="btn-icon" style="font-size: 1.1rem; padding: 4px 8px;" onclick="closeModal('modal-google-sheet')">✕</button>
                </div>
                <p style="font-size: 0.8rem; color: var(--text-muted); margin: 0 0 12px 0;">
                    Sync your portfolios, watchlist, and transaction history seamlessly across your phone, tablet, and computer using Google Sheets as cloud storage.
                </p>

                <!-- Status Card -->
                <div style="background: var(--bg-card-subtle); padding: 10px 12px; border-radius: 10px; margin-bottom: 12px; font-size: 0.8rem; line-height: 1.6;">
                    <div style="display:flex; justify-content:space-between;">
                        <span>Cloud Status:</span>
                        <strong id="sheet-modal-status-txt">Checking...</strong>
                    </div>
                    <div style="display:flex; justify-content:space-between;">
                        <span>Last Synced:</span>
                        <span id="sheet-modal-time-txt">-</span>
                    </div>
                    <div id="sheet-modal-msg" style="margin-top: 4px; font-weight: 600; color: var(--text-muted);"></div>
                </div>

                <div class="form-group" style="margin-bottom: 10px;">
                    <label class="form-label">Google Apps Script Web App URL</label>
                    <input id="sheet-modal-url" class="form-control" placeholder="https://script.google.com/macros/s/.../exec">
                </div>

                <div style="display: flex; gap: 8px; margin-bottom: 14px;">
                    <button class="btn-action-primary" style="background: var(--bg-card-subtle); color: var(--text-main); border: 1px solid var(--border-color); padding: 8px 12px; font-size: 0.82rem;" onclick="testGoogleSheetConnection()">🔌 Test Connection</button>
                    <button class="btn-action-primary" style="flex:1; padding: 8px 12px; font-size: 0.82rem;" onclick="saveAndSyncGoogleSheet()">💾 Save & Sync Now</button>
                </div>

                <details style="font-size: 0.78rem; color: var(--text-muted); background: var(--bg-card-subtle); padding: 8px 12px; border-radius: 8px;">
                    <summary style="cursor: pointer; font-weight: 700; color: var(--accent-blue);">📖 Setup Guide & Apps Script (Click to expand)</summary>
                    <p style="margin: 8px 0 4px 0;">
                        1. Create a Google Spreadsheet (sheets.new)<br>
                        2. Extensions &rarr; Apps Script<br>
                        3. Paste script &rarr; Deploy &rarr; New Deployment &rarr; Web App<br>
                        4. Set: 'Execute as Me' & 'Who has access: Anyone'<br>
                        5. Paste the Web App URL above!
                    </p>
                    <button class="btn-action-primary" style="background: rgba(10,132,255,0.15); color: var(--accent-blue); padding: 6px 10px; font-size: 0.76rem; border: 1px solid var(--accent-blue); margin-top: 4px;" onclick="copyGoogleAppsScript()">📋 Copy Google Apps Script Code</button>
                </details>
            </div>
        </div>

        <!-- Modal 6: Conflict Resolution -->
        <div id="modal-sheet-conflict" class="modal-overlay" onclick="if(event.target===this)closeModal('modal-sheet-conflict')">
            <div class="modal-card" style="max-width: 620px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <h3 style="margin: 0; font-size: 1.15rem; color: var(--accent-red);">⚠️ Cloud Sync Conflict Detected</h3>
                    <button class="btn-icon" style="font-size: 1.1rem; padding: 4px 8px;" onclick="closeModal('modal-sheet-conflict')">✕</button>
                </div>
                <p style="font-size: 0.8rem; color: var(--text-muted); margin: 0 0 10px 0;">
                    Differences were found between this device and Google Sheet. Please review the changes below and choose which version to keep:
                </p>

                <!-- Diff Table Container -->
                <div id="sheet-conflict-diff-list" style="max-height: 220px; overflow-y: auto; background: var(--bg-card-subtle); border-radius: 8px; padding: 8px; margin-bottom: 12px; font-size: 0.78rem;">
                    <!-- Populated dynamically -->
                </div>

                <!-- Action choices -->
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <button class="btn-action-primary" style="background: var(--accent-blue); color: white; padding: 9px; font-size: 0.85rem;" onclick="resolveCloudConflict('keep_local')">
                        📱 Keep Device Version (Upload to Google Sheet)
                    </button>
                    <button class="btn-action-primary" style="background: var(--accent-green); color: white; padding: 9px; font-size: 0.85rem;" onclick="resolveCloudConflict('keep_remote')">
                        ☁️ Keep Google Sheet (Download to Device with 10 Backups)
                    </button>
                    <button class="btn-action-primary" style="background: var(--bg-card-subtle); color: var(--text-main); border: 1px solid var(--border-color); padding: 8px; font-size: 0.82rem;" onclick="resolveCloudConflict('merge')">
                        🔀 Smart Merge (Combine non-conflicting records)
                    </button>
                </div>
            </div>
        </div>

        <!-- Mobile Bottom Tab Navigation for iPhone -->
        <div class="bottom-tab-bar">
            <button class="tab-item active" id="btab-portfolio" onclick="switchTab('portfolio')">
                <span class="icon">💼</span>
                <span data-i18n="tab_portfolio">持倉</span>
            </button>
            <button class="tab-item" id="btab-chart" onclick="switchTab('chart')">
                <span class="icon">📈</span>
                <span data-i18n="tab_chart">走勢</span>
            </button>
            <button class="tab-item" id="btab-fire" onclick="switchTab('fire')">
                <span class="icon">🎯</span>
                <span data-i18n="tab_fire">FIRE</span>
            </button>
            <button class="tab-item" id="btab-watchlist" onclick="switchTab('watchlist')">
                <span class="icon">👁️</span>
                <span data-i18n="tab_watchlist">自選</span>
            </button>
            <button class="tab-item" id="btab-tools" onclick="switchTab('tools')">
                <span class="icon">⚙️</span>
                <span data-i18n="tab_tools">工具</span>
            </button>
        </div>
    </div>

        <script>
        // State Management
        let currentCurrency = 'USD';
        let currentPortfolio = 'All';
        let isTableView = false;
        let currentLang = localStorage.getItem('g_finance_lang') || 'zh_TW';
        let currentPortfolioData = null;
        let windowLastFireData = null;
        let _lastWatchlistItems = [];
        let currentChartData = null;
        let currentChartSymbol = 'PORTFOLIO';
        let currentChartTimeframe = '1M';
        let currentChartMetric = 'total';
        let currentChartStyle = 'area';
        let currentPreparedChart = null;
        let currentSelectedHoldingSymbol = null;
        let currentSelectedHoldingPortfolio = '';
        let currentSelectedWatchlistSymbol = null;

        const I18N = {
        "en": {
                "tab_portfolio": "Portfolio",
                "tab_chart": "Chart",
                "tab_fire": "FIRE Retirement",
                "tab_watchlist": "Watchlist",
                "tab_tools": "Tools & Info",
                "nav_portfolio": "📊 Portfolio",
                "nav_chart": "📈 Chart",
                "nav_fire": "🔥 FIRE Retirement",
                "nav_watchlist": "👁️ Watchlist",
                "nav_tools": "⚙️ Tools & Info",
                "detecting": "Detecting...",
                "all_portfolios": "All Portfolios",
                "theme_toggle": "Toggle Dark/Light Mode",
                "synced_now": "Synced Just Now",
                "synced_at": "Synced {time}",
                "net_worth_title": "Total Portfolio Net Worth",
                "active_holdings": "Active Holdings ({count})",
                "btn_add": "➕ Add",
                "view_table": "📋 Table View",
                "view_card": "📱 Card View",
                "toggle_to_table": "📊 Table View ⮀",
                "toggle_to_card": "📱 Card View ⮀",
                "th_symbol": "Symbol",
                "th_shares": "Shares",
                "th_cost": "Avg Cost",
                "th_price": "Price",
                "th_value": "Total Value",
                "th_roi": "ROI %",
                "alloc_equity": "📈 Equity: {val} ({pct}%)",
                "alloc_safe": "🛡️ Safe Buffer: {val} ({pct}%)",
                "pill_div": "Div: {val}/yr",
                "pill_yield": "Yield: {val}%",
                "empty_holdings": "No holdings in this portfolio yet.",
                "shs_unit": "shs",
                "chart_title": "Market & Asset Trends",
                "chart_donut_title": "Asset Allocation Breakdown",
                "btn_view_chart": "📈 View Live Chart",
                "total_portfolio": "📈 Total Portfolio",
                "holdings_group": "💼 Holdings",
                "watchlist_group": "👁️ Watchlist",
                "chart_loading": "Loading chart data...",
                "chart_tip": "👆 Drag finger or hover mouse to inspect points",
                "ref_prev_close": "Prev Close: {val}",
                "realtime_trend": "Real-Time Trend",
                "updated_at": "Updated at {time}",
                "total_assets": "Total Assets",
                "holdings_unit": "Holdings",
                "other_assets": "Other Assets",
                "fire_safe_title": "🛡️ Safe Liability Buffer (25-Yr)",
                "fire_safe_note": "🛡️ Buffer covers {years} of 25.0 planned years",
                "fire_div_title": "💵 Passive Dividend Gap",
                "fire_div_note_gap": "📈 Crossover in {years} yrs @ 5% dividend growth",
                "fire_div_note_met": "✓ Full Dividend Freedom Achieved",
                "fire_cap_title": "🏛️ Bernstein 3.2% Capital Gap",
                "fire_cap_note_gap": "💰 Monthly savings needed: {val}/mo",
                "fire_cap_note_met": "✓ Target Principal Reached",
                "fire_burn_title": "⚡ Burn Rate Corridor Speedometer",
                "fire_timeline_title": "⏳ Life Cycle & Retirement Horizon Timeline",
                "current_safe": "Current: {val} ({pct}%)",
                "target_safe": "Target: {val}",
                "current_div": "Current Div: {val} ({pct}%)",
                "target_rle": "Target RLE: {val}",
                "current_wealth": "Current Wealth: {val} ({pct}%)",
                "target_capital": "3.2% Target: {val}",
                "fire_auditing": "Auditing...",
                "fire_gap_prefix": "Gap: -{val}",
                "fire_target_met": "✓ Target Met",
                "fire_burn_safe": "Safe & Abundant",
                "fire_burn_swr": "Sustainable SWR",
                "fire_burn_danger": "Over-Burn Danger",
                "burn_zone_safe": "<2.0% Safe",
                "burn_zone_swr": "2.0-3.5% SWR",
                "burn_zone_danger": ">3.5% Warning",
                "tl_age_now": "● Age 45 (Now)",
                "tl_age_fire": "★ Age 60 (FIRE)",
                "tl_age_end": "🏁 Age 90",
                "tl_accum_phase": "⏳ 15y Accumulation",
                "tl_dist_phase": "🏖️ 30y Distribution Horizon",
                "watchlist_title": "Real-Time Watchlist & Targets",
                "tracked_count": "{count} Tracked",
                "target_hit": "🎯 Target Hit: {val}",
                "target": "Target: {val}",
                "no_target": "No Target",
                "empty_watchlist": "No symbols in watchlist yet.",
                "st_whatif": "💡 What-If",
                "st_rebalance": "⚖️ Rebalance",
                "st_drip": "💧 DRIP",
                "st_split": "✂️ Split",
                "st_selling": "💰 Sell P&L",
                "st_health": "🩺 Health",
                "st_reports": "📄 Reports",
                "st_cloud": "☁️ Cloud Sync",
                "st_backup": "💾 Backup",
                "st_diag": "📱 System",
                "btn_google_sheet_sync": "Google Sheet Sync",
                "cloud_title": "☁️ Google Sheet Cloud Sync",
                "cloud_desc": "Use Google Sheets as a free cross-device cloud database to sync holdings, watchlist, and transactions seamlessly across all your devices.",
                "cloud_lbl_status": "Cloud Connection Status:",
                "cloud_lbl_last_sync": "Last Synchronized:",
                "cloud_lbl_device": "Local Device ID:",
                "cloud_cfg_title": "⚙️ Google Apps Script Configuration",
                "cloud_lbl_url": "Google Apps Script Web App URL",
                "cloud_lbl_autoupload": "Automatically sync edits to cloud in background",
                "btn_sync_now": "Sync Now",
                "btn_sync_push": "Push to Cloud",
                "btn_sync_pull": "Pull from Cloud",
                "btn_test_connection": "Test Connection",
                "btn_save_config": "Save Settings",
                "cloud_guide_summary": "📖 30-Second Quick Setup Guide (Click to expand)",
                "cloud_backup_title": "☁️ Google Sheets Cloud Sync",
                "cloud_backup_desc": "Keep your financial data synchronized with Google Sheets with automatic backups and conflict safety.",
                "btn_cloud_settings": "Cloud Settings",
                "btn_copy_script": "Copy Google Apps Script Code",
                "whatif_title": "💡 What-If Scenario Investment Calculator",
                "whatif_desc": "Simulate adding capital or new positions to forecast impact on total wealth, allocations, and dividend cash flow.",
                "whatif_sel_lbl": "Select Holding (or Enter Manually)",
                "whatif_custom_ticker": "-- Custom Ticker --",
                "lbl_symbol": "Symbol",
                "lbl_price": "Price",
                "lbl_yield": "Dividend Yield %",
                "lbl_amount": "Amount ($)",
                "whatif_reset_5k": "Reset 5,000",
                "whatif_res_tot": "Total Portfolio Shift:",
                "whatif_res_shs": "Estimated Shares Added:",
                "whatif_res_alloc": "Position Weight Shift:",
                "whatif_res_div": "Projected Annual Div Growth:",
                "rebal_title": "⚖️ Portfolio Rebalancing Calculator",
                "rebal_desc": "Customize target allocation weights or apply presets to calculate required buy/sell trades and cash flow.",
                "rebal_cash_lbl": "Inject Additional Cash (Deposit)",
                "rebal_btn_equal": "Equal Weight (均等權重)",
                "rebal_btn_reset": "Reset to Current",
                "rebal_sum_lbl": "Target Weight Sum:",
                "rebal_total_val_lbl": "Total Rebalanced Portfolio:",
                "rebal_cur_val": "Current: {val} ({pct}%)",
                "rebal_target_pct": "Target %:",
                "rebal_hold": "✓ HOLD",
                "rebal_buy": "Buy +{diff} (+{shs} shs)",
                "rebal_sell": "Sell -{diff} ({shs} shs)",
                "rebal_ok": "✓ Normal",
                "rebal_warn": "⚠️ (Not 100%)",
                "drip_title": "💧 Dividend Reinvestment & Compounding (DRIP)",
                "drip_desc": "Simulate exponential wealth growth and cash flow compounding from dividend reinvestment.",
                "drip_init_div": "Current Annual Div ($)",
                "drip_div_growth": "Annual Div Growth %",
                "drip_return": "Reinvestment Return %",
                "drip_extra": "Annual Extra Capital",
                "th_year": "Year",
                "th_ann_div": "Annual Dividend",
                "th_monthly_flow": "Monthly Cash Flow",
                "th_total_wealth": "Compounded Wealth",
                "split_title": "✂️ Stock Split & Reverse Split Calculator",
                "split_desc": "Recalibrate share quantities and cost basis per share upon forward or reverse stock splits.",
                "split_sel_lbl": "Select Holding",
                "split_manual": "-- Manual Input --",
                "split_pre_shs": "Shares Before Split",
                "split_pre_cost": "Cost Per Share Before ($)",
                "split_num": "Split Numerator (New Shares)",
                "split_den": "Split Denominator (Old Shares)",
                "split_ratio_1_2": "1:2 Reverse Split",
                "split_ratio_1_4": "1:4 Reverse Split",
                "split_res_shs_lbl": "Shares After Split:",
                "split_res_cost_lbl": "Cost Basis After:",
                "split_res_tot_lbl": "Total Cost Basis:",
                "split_unchanged": "(Unchanged ✓)",
                "sell_title": "💰 Realized Profit & Selling Calculator",
                "sell_desc": "Calculate realized capital gains, cash proceeds, and remaining portfolio value for partial or full exits.",
                "sell_sel_lbl": "Select Holding",
                "sell_tot_shs": "Total Shares Held",
                "sell_cost_price": "Avg Cost Per Share ($)",
                "sell_qty": "Shares to Sell",
                "sell_price": "Exit Price Per Share ($)",
                "sell_pct_25": "Sell 25%",
                "sell_pct_50": "Sell 50%",
                "sell_pct_75": "Sell 75%",
                "sell_pct_100": "Sell All (100%)",
                "sell_res_proceeds_lbl": "Gross Cash Proceeds:",
                "sell_res_gain_lbl": "Realized Capital Gain/Loss:",
                "sell_res_rem_shs_lbl": "Remaining Shares:",
                "sell_res_rem_val_lbl": "Remaining Market Value:",
                "health_title": "🩺 Data Integrity Check & One-Click Repair",
                "health_desc": "Audit portfolio.csv and watchlist.csv for missing fields, inconsistent currencies, or corrupted entries.",
                "btn_scan": "🔍 Run Full Scan",
                "btn_repair": "🛠️ One-Click Repair",
                "health_init_sum": "Click button above to start scan",
                "health_init_det": "Supports automatic correction of common formatting issues.",
                "health_scanning": "⏳ Scanning data integrity...",
                "health_ok_sum": "✅ Data health is excellent (100% Valid)",
                "health_ok_det": "All holdings and watchlist entries verified. No missing costs, abnormal tickers, or currency issues.",
                "health_issue_sum": "⚠️ Found {count} data formatting issue(s)",
                "health_repairing": "⏳ Running automatic repair...",
                "health_repaired_sum": "✅ Data repair completed!",
                "health_repaired_det": "Data anomalies resolved. Reloading latest records...",
                "reports_title": "📄 Executive Financial Summary Report",
                "reports_desc": "Generate professional HTML/PDF financial reports with net worth curves, allocation, performance, and income projections.",
                "btn_open_report": "📑 Open Full HTML Report (New Tab)",
                "btn_preview_report": "📱 Preview Report In-Page",
                "backup_title": "💾 Data Export & Backup Download",
                "backup_desc": "Download holdings and watchlist anytime to secure your financial records.",
                "btn_dl_portfolio": "📥 Download Portfolio CSV (portfolio.csv)",
                "btn_dl_watchlist": "📥 Download Watchlist CSV (watchlist.csv)",
                "btn_dl_json": "📦 Download Full System Backup (JSON)",
                "diag_title": "📱 System & Device Diagnostics",
                "diag_platform_lbl": "Detected Platform:",
                "diag_touch_lbl": "Touch Optimization:",
                "diag_res_lbl": "Screen Resolution:",
                "diag_pwa_lbl": "Standalone PWA Mode:",
                "btn_mode_iphone": "📱 iPhone Mode",
                "btn_mode_ipad": "📟 iPad Mode",
                "btn_mode_pc": "💻 PC Mode",
                "quick_server_actions": "⚡ Quick Server Actions",
                "btn_refresh_quotes": "🔄 Refresh Quotes Now",
                "btn_stop_server": "🛑 Stop G_Finance Server",
                "quick_refresh": "🔄 Refresh Quotes",
                "quick_stop": "🛑 Stop Server",
                "refreshing": "🔄 Fetching live market quotes...",
                "refresh_done": "✅ Quotes updated ({updated}/{total} updated)",
                "refresh_cache": "⚡ Quotes loaded from cache",
                "refresh_timeout": "⚠️ Quote refresh timed out",
                "holding_details": "Stock Details",
                "lbl_cur_price": "Current Price:",
                "lbl_shares": "Shares Held:",
                "lbl_cost_basis": "Cost Basis:",
                "lbl_market_val": "Market Value:",
                "lbl_unrealized_pl": "Unrealized P/L:",
                "lbl_est_div": "Est. Annual Dividend:",
                "quick_actions": "🚀 QUICK ACTIONS",
                "btn_h_chart": "📈 View Live Chart",
                "btn_h_whatif": "💡 Simulate What-If Purchase",
                "btn_h_split": "✂️ Stock Split Calculator",
                "btn_h_sell": "💰 Realized Profit Calculator",
                "btn_h_delete": "🗑️ Delete Position",
                "watchlist_details": "Watchlist Item Details",
                "lbl_w_curp": "Current Price:",
                "lbl_w_tgtp": "Target Price:",
                "lbl_w_diff": "Gap to Target:",
                "lbl_w_notes": "Notes & Tags:",
                "w_not_fetched": "Price Not Yet Fetched",
                "w_not_set": "Not Set",
                "w_target_hit_desc": "🎯 Target Hit (${diff} below target)",
                "w_above_target_desc": "Above Target +${diff} (+{pct}%)",
                "w_no_notes": "No Notes",
                "btn_w_chart": "📈 View Live Chart",
                "btn_w_whatif": "💡 Simulate What-If Buy",
                "btn_w_delete": "🗑️ Remove from Watchlist",
                "add_holding_title": "➕ Add New Position",
                "lbl_sym_req": "Symbol*",
                "lbl_name_opt": "Company Name",
                "lbl_shares_req": "Shares*",
                "lbl_cost_req": "Cost Basis Per Share*",
                "lbl_currency": "Currency",
                "lbl_portfolio": "Portfolio",
                "ph_sym_h": "e.g. VOO, AAPL",
                "ph_name_h": "Optional",
                "ph_shares_h": "10",
                "ph_cost_h": "150.0",
                "ph_port_h": "e.g. Core, Tech",
                "btn_confirm_add_h": "Confirm Add Position",
                "add_watchlist_title": "➕ Add to Watchlist",
                "lbl_tgt_req": "Target Buy Price*",
                "lbl_notes_opt": "Notes & Strategy",
                "ph_sym_w": "e.g. NVDA, MSFT",
                "ph_name_w": "Optional",
                "ph_tgt_w": "120.0",
                "ph_notes_w": "e.g. Buy on pullback",
                "btn_confirm_add_w": "Confirm Add to Watchlist",
                "confirm_del_holding": "Are you sure you want to delete holding {sym}?",
                "toast_del_holding": "🗑️ Successfully deleted {sym}",
                "err_del_holding": "Delete failed: {msg}",
                "confirm_del_watchlist": "Are you sure you want to remove {sym} from watchlist?",
                "toast_del_watchlist": "🗑️ Removed {sym} from watchlist",
                "err_del_watchlist": "Remove failed: {msg}",
                "err_fill_holding": "Please fill out symbol, shares, and cost basis!",
                "toast_add_holding": "✅ Successfully added holding {sym}",
                "err_add_holding": "Failed to add holding: {msg}",
                "err_fill_symbol": "Please enter a stock symbol!",
                "toast_add_watchlist": "✅ Added {sym} to watchlist",
                "err_add_watchlist": "Failed to add to watchlist: {msg}",
                "confirm_stop_server": "Are you sure you want to stop the local G_Finance server?",
                "alert_server_stopping": "Server is stopping. Please close this tab or terminal window.",
                "alert_stop_sent": "Stop command sent.",
                "err_network": "Network error: {msg}",
                "chart_metric_lbl": "Metric:",
                "chart_metric_total": "Total Value",
                "chart_metric_price": "Stock Price (Per Share)",
                "chart_metric_growth": "Net Growth / P&L (Excl. Invested)",
                "chart_metric_growth_div": "Net Growth + Dividends",
                "chart_metric_div_only": "Dividends Only",
                "chart_style_lbl": "Style:",
                "chart_style_area": "Area",
                "chart_style_line": "Line",
                "chart_invested_capital": "Invested Capital: ",
                "chart_div_received": "Dividends: ",
                "th_currency": "Currency",
                "lbl_total_cost": "Total Cost:"
        },
        "zh_TW": {
                "tab_portfolio": "投資組合",
                "tab_chart": "走勢圖表",
                "tab_fire": "FIRE 退休規劃",
                "tab_watchlist": "自選監控",
                "tab_tools": "工具與資訊",
                "nav_portfolio": "📊 投資組合",
                "nav_chart": "📈 走勢圖表",
                "nav_fire": "🔥 FIRE 退休規劃",
                "nav_watchlist": "👁️ 自選監控",
                "nav_tools": "⚙️ 工具與資訊",
                "detecting": "裝置辨識中...",
                "all_portfolios": "全部投資組合",
                "theme_toggle": "切換深色/淺色主題",
                "synced_now": "剛剛更新",
                "synced_at": "更新於 {time}",
                "net_worth_title": "投資組合總淨值",
                "active_holdings": "持倉標的 ({count})",
                "btn_add": "➕ 新增",
                "view_table": "📋 表格檢視",
                "view_card": "📱 卡片檢視",
                "toggle_to_table": "📊 切換表格檢視 ⮀",
                "toggle_to_card": "📱 切換卡片檢視 ⮀",
                "th_symbol": "代碼",
                "th_shares": "股數",
                "th_cost": "均價",
                "th_price": "市價",
                "th_value": "總市值",
                "th_roi": "報酬率",
                "alloc_equity": "📈 權益資產: {val} ({pct}%)",
                "alloc_safe": "🛡️ 安全緩衝: {val} ({pct}%)",
                "pill_div": "年股息: {val}",
                "pill_yield": "殖利率: {val}%",
                "empty_holdings": "目前此投資組合尚無持股標的。",
                "shs_unit": "股",
                "chart_title": "市場與資產走勢",
                "chart_donut_title": "投資組合資產配置圖",
                "btn_view_chart": "📈 檢視即時走勢圖",
                "total_portfolio": "📈 總資產 (Total Portfolio)",
                "holdings_group": "💼 持倉標的 (Holdings)",
                "watchlist_group": "👁️ 自選監控 (Watchlist)",
                "chart_loading": "載入走勢中...",
                "chart_tip": "👆 手指滑動或滑鼠懸停可查閱任意點位",
                "ref_prev_close": "昨收參考: {val}",
                "realtime_trend": "即時走勢",
                "updated_at": "更新於 {time}",
                "total_assets": "總資產",
                "holdings_unit": "檔標的",
                "other_assets": "其他標的",
                "fire_safe_title": "🛡️ 25年保證負債安全緩衝",
                "fire_safe_note": "🛡️ 緩衝儲備已覆蓋 {years} / 25.0 計畫年數",
                "fire_div_title": "💵 被動股息生活費覆蓋缺口",
                "fire_div_note_gap": "📈 依5%年增率預計 {years} 年黃金交叉",
                "fire_div_note_met": "✓ 已達成被動股息完全財務自由",
                "fire_cap_title": "🏛️ Bernstein 3.2% 本金安全缺口",
                "fire_cap_note_gap": "💰 預計每月需提存加碼: {val}/月",
                "fire_cap_note_met": "✓ 已達成安全提領本金目標",
                "fire_burn_title": "⚡ 實質提領率警戒儀表板",
                "fire_timeline_title": "⏳ 人生週期與退休提領時間軸",
                "current_safe": "當前安全資產: {val} ({pct}%)",
                "target_safe": "目標儲備: {val}",
                "current_div": "當前年股息: {val} ({pct}%)",
                "target_rle": "目標生活費: {val}",
                "current_wealth": "當前總淨值: {val} ({pct}%)",
                "target_capital": "3.2% 本金目標: {val}",
                "fire_auditing": "審核中...",
                "fire_gap_prefix": "缺口: -{val}",
                "fire_target_met": "✓ 已達標",
                "fire_burn_safe": "安全充裕",
                "fire_burn_swr": "永續區間",
                "fire_burn_danger": "超額提領危險",
                "burn_zone_safe": "<2.0% 安全充裕",
                "burn_zone_swr": "2.0-3.5% 永續 SWR",
                "burn_zone_danger": ">3.5% 警戒超額",
                "tl_age_now": "● 目前年齡 45歲",
                "tl_age_fire": "★ 預計退休 60歲",
                "tl_age_end": "🏁 預期壽命 90歲",
                "tl_accum_phase": "⏳ 15年資產累積期",
                "tl_dist_phase": "🏖️ 30年退休提領期",
                "watchlist_title": "即時自選監控與目標價",
                "tracked_count": "{count} 檔監控中",
                "target_hit": "🎯 已達買進: {val}",
                "target": "目標: {val}",
                "no_target": "未設目標",
                "empty_watchlist": "自選清單目前尚無追蹤標的。",
                "st_whatif": "💡 What-If 加碼",
                "st_rebalance": "⚖️ 再平衡",
                "st_drip": "💧 股息複利",
                "st_split": "✂️ 股票分割",
                "st_selling": "💰 賣出損益",
                "st_health": "🩺 健康檢查",
                "st_reports": "📄 財務報表",
                "st_cloud": "☁️ 雲端同步",
                "st_backup": "💾 資料備份",
                "st_diag": "📱 系統診斷",
                "btn_google_sheet_sync": "Google 試算表同步",
                "cloud_title": "☁️ Google 試算表雲端同步",
                "cloud_desc": "使用 Google Sheets 試算表作為跨裝置雲端資料庫，無縫同步持倉、自選清單與交易歷史記錄。",
                "cloud_lbl_status": "雲端連線狀態:",
                "cloud_lbl_last_sync": "上次同步時間:",
                "cloud_lbl_device": "本機裝置識別:",
                "cloud_cfg_title": "⚙️ Google Apps Script 設定",
                "cloud_lbl_url": "Google Apps Script 網頁應用程式網址 (Web App URL)",
                "cloud_lbl_autoupload": "編輯或交易時自動背景同步至雲端",
                "btn_sync_now": "立即雙向同步",
                "btn_sync_push": "強制上傳至試算表",
                "btn_sync_pull": "強制自試算表下載",
                "btn_test_connection": "測試連線",
                "btn_save_config": "儲存設定",
                "cloud_guide_summary": "📖 30 秒快速安裝與部署教學 (點擊展開)",
                "cloud_backup_title": "☁️ Google 試算表即時雲端同步",
                "cloud_backup_desc": "與 Google Sheets 保持雙向同步，支援自動多版本備份與跨設備無縫接軌。",
                "btn_cloud_settings": "雲端設定",
                "btn_copy_script": "複製 Google Apps Script 程式碼",
                "whatif_title": "💡 What-If 模擬加碼試算機",
                "whatif_desc": "模擬加碼或買進新標的，即時預估對總資產、持有股數、配置比例與年股息的影響。",
                "whatif_sel_lbl": "選擇持倉標的 (或手動輸入)",
                "whatif_custom_ticker": "-- 自訂代碼 (Custom Ticker) --",
                "lbl_symbol": "股票代碼 (Symbol)",
                "lbl_price": "預估股價 (Price)",
                "lbl_yield": "預估殖利率 % (Yield)",
                "lbl_amount": "加碼金額 ($ Amount)",
                "whatif_reset_5k": "重設 5,000",
                "whatif_res_tot": "總資產變化:",
                "whatif_res_shs": "預計新增股數:",
                "whatif_res_alloc": "該標的配置佔比:",
                "whatif_res_div": "被動年股息增長:",
                "rebal_title": "⚖️ 資產再平衡試算機",
                "rebal_desc": "自訂各標的目標配置比例或套用模型，試算達成目標所需的買賣金額與股數。",
                "rebal_cash_lbl": "額外注入新資金 (現金加碼)",
                "rebal_btn_equal": "均等權重 (Equal)",
                "rebal_btn_reset": "重設為現況",
                "rebal_sum_lbl": "目標權重總和:",
                "rebal_total_val_lbl": "再平衡總資產規模:",
                "rebal_cur_val": "現值: {val} ({pct}%)",
                "rebal_target_pct": "目標%:",
                "rebal_hold": "✓ 持平 (HOLD)",
                "rebal_buy": "買進 +{diff} (+{shs}股)",
                "rebal_sell": "賣出 -{diff} ({shs}股)",
                "rebal_ok": "✓ 正常",
                "rebal_warn": "⚠️ (未達100%)",
                "drip_title": "💧 股息再投資與複利試算 (DRIP)",
                "drip_desc": "試算股息複利滾存帶來的現金流指數級增長。",
                "drip_init_div": "目前年股息 (Annual Div)",
                "drip_div_growth": "年股息成長率 % (Growth)",
                "drip_return": "年化再投資報酬率 %",
                "drip_extra": "每年額外加碼資金",
                "th_year": "年期",
                "th_ann_div": "年被動股息",
                "th_monthly_flow": "月被動現金流",
                "th_total_wealth": "複利滾存總資產",
                "split_title": "✂️ 股票分割 / 反分割計算機",
                "split_desc": "當持股進行正分割 (如 2:1, 10:1) 或反分割 (如 1:2) 時，自動校正股數與每股平均買進成本。",
                "split_sel_lbl": "選擇持倉標的",
                "split_manual": "-- 手動輸入 --",
                "split_pre_shs": "分割前持有股數",
                "split_pre_cost": "分割前每股成本 ($)",
                "split_num": "分割分子 (換成幾股)",
                "split_den": "分割分母 (原本幾股)",
                "split_ratio_1_2": "1:2 反分割",
                "split_ratio_1_4": "1:4 反分割",
                "split_res_shs_lbl": "校正後持有股數:",
                "split_res_cost_lbl": "校正後每股平均成本:",
                "split_res_tot_lbl": "總投資成本守恆:",
                "split_unchanged": "(不變 ✓)",
                "sell_title": "💰 獲利了結與賣出損益試算機",
                "sell_desc": "試算部分或全部賣出時的已實現資本利得、現金入帳與剩餘持倉價值。",
                "sell_sel_lbl": "選擇持倉標的",
                "sell_tot_shs": "目前總持有股數",
                "sell_cost_price": "平均每股買進成本 ($)",
                "sell_qty": "預計賣出股數",
                "sell_price": "預計每股賣出價 ($)",
                "sell_pct_25": "賣出 25%",
                "sell_pct_50": "賣出 50%",
                "sell_pct_75": "賣出 75%",
                "sell_pct_100": "全部清倉 (100%)",
                "sell_res_proceeds_lbl": "賣出回收現金總額:",
                "sell_res_gain_lbl": "已實現資本利得 (獲利):",
                "sell_res_rem_shs_lbl": "剩餘持倉股數:",
                "sell_res_rem_val_lbl": "剩餘部位市值:",
                "health_title": "🩺 資料完整性檢查與一鍵修復",
                "health_desc": "自動審核 portfolio.csv 與 watchlist.csv，檢查是否有未填成本、缺少幣別、未分類標的或異常記錄。",
                "btn_scan": "🔍 執行完整掃描",
                "btn_repair": "🛠️ 一鍵修復異常",
                "health_init_sum": "點擊上方按鈕開始檢查",
                "health_init_det": "支援自動校正常見資料格式問題。",
                "health_scanning": "⏳ 正在檢查資料完整性...",
                "health_ok_sum": "✅ 資料健康狀態良好 (100% 完整)",
                "health_ok_det": "已審核所有持倉與自選清單，無缺少成本、幣別不一致或異常代碼。",
                "health_issue_sum": "⚠️ 發現 {count} 項資料格式問題",
                "health_repairing": "⏳ 正在執行自動修復程序...",
                "health_repaired_sum": "✅ 資料修復完成！",
                "health_repaired_det": "已修正資料問題，重新載入最新資料中...",
                "reports_title": "📄 完整財務執行摘要報表",
                "reports_desc": "產出專業的 HTML / PDF 格式財務報表，包含淨值圖表、資產配置分析、持股明細及收益預測。",
                "btn_open_report": "📑 開啟完整 HTML 財務報表 (新分頁)",
                "btn_preview_report": "📱 在頁面內嵌預覽報表",
                "backup_title": "💾 資料匯出與備份下載",
                "backup_desc": "隨時下載持股與自選名單，保護您的財務資料安全無虞。",
                "btn_dl_portfolio": "📥 下載持股資料 (portfolio.csv)",
                "btn_dl_watchlist": "📥 下載自選清單 (watchlist.csv)",
                "btn_dl_json": "📦 下載完整系統備份 (JSON Backup)",
                "diag_title": "📱 系統與裝置診斷",
                "diag_platform_lbl": "執行平台辨識:",
                "diag_touch_lbl": "觸控優化狀態:",
                "diag_res_lbl": "螢幕解析度:",
                "diag_pwa_lbl": "獨立 PWA 模式:",
                "btn_mode_iphone": "📱 iPhone 模式",
                "btn_mode_ipad": "📟 iPad 模式",
                "btn_mode_pc": "💻 PC 模式",
                "quick_server_actions": "⚡ 快速伺服器動作",
                "btn_refresh_quotes": "🔄 立即刷新所有股價行情",
                "btn_stop_server": "🛑 停止 G_Finance 伺服器",
                "quick_refresh": "🔄 立即刷新行情",
                "quick_stop": "🛑 停止伺服器",
                "refreshing": "🔄 正在擷取即時股價行情...",
                "refresh_done": "✅ 行情更新完成 ({updated}/{total} 檔已更新)",
                "refresh_cache": "⚡ 使用快取報價數據",
                "refresh_timeout": "⚠️ 更新行情連線逾時",
                "holding_details": "持倉標的明細",
                "lbl_cur_price": "當前市價:",
                "lbl_shares": "持有股數:",
                "lbl_cost_basis": "投資成本:",
                "lbl_market_val": "當前市值:",
                "lbl_unrealized_pl": "未實現損益:",
                "lbl_est_div": "預估年股息:",
                "quick_actions": "🚀 快捷連動功能",
                "btn_h_chart": "📈 檢視即時走勢圖",
                "btn_h_whatif": "💡 帶入 What-If 加碼模擬試算",
                "btn_h_split": "✂️ 帶入股票分割 / 反分割計算機",
                "btn_h_sell": "💰 帶入賣出獲利了結試算機",
                "btn_h_delete": "🗑️ 刪除此持股標的",
                "watchlist_details": "自選監控標的明細",
                "lbl_w_curp": "當前市價:",
                "lbl_w_tgtp": "目標買進價:",
                "lbl_w_diff": "距目標價差:",
                "lbl_w_notes": "備註標籤:",
                "w_not_fetched": "尚未獲取報價",
                "w_not_set": "未設定",
                "w_target_hit_desc": "🎯 已達買進目標 (低於目標價 ${diff})",
                "w_above_target_desc": "高於目標價 +${diff} (+{pct}%)",
                "w_no_notes": "無備註",
                "btn_w_chart": "📈 檢視即時走勢圖",
                "btn_w_whatif": "💡 帶入 What-If 模擬買進",
                "btn_w_delete": "🗑️ 從自選清單移除",
                "add_holding_title": "➕ 新增投資持股",
                "lbl_sym_req": "股票代碼 (Symbol)*",
                "lbl_name_opt": "公司名稱 (Name)",
                "lbl_shares_req": "持有股數 (Shares)*",
                "lbl_cost_req": "每股買進成本 (Cost)*",
                "lbl_currency": "幣別 (Currency)",
                "lbl_portfolio": "所屬投資組合 (Portfolio)",
                "ph_sym_h": "如 VOO, AAPL",
                "ph_name_h": "可選填",
                "ph_shares_h": "10",
                "ph_cost_h": "150.0",
                "ph_port_h": "如 Core, Tech",
                "btn_confirm_add_h": "確認新增持股",
                "add_watchlist_title": "➕ 新增自選監控標的",
                "lbl_tgt_req": "目標買進價 (Target Price)*",
                "lbl_notes_opt": "備註說明 (Notes)",
                "ph_sym_w": "如 NVDA, MSFT",
                "ph_name_w": "可選填",
                "ph_tgt_w": "120.0",
                "ph_notes_w": "例: 回檔至季線買進",
                "btn_confirm_add_w": "確認加入自選",
                "confirm_del_holding": "確定要刪除持股 {sym} 嗎？",
                "toast_del_holding": "🗑️ 已成功刪除持股 {sym}",
                "err_del_holding": "刪除失敗: {msg}",
                "confirm_del_watchlist": "確定要從自選清單移除 {sym} 嗎？",
                "toast_del_watchlist": "🗑️ 已從自選清單移除 {sym}",
                "err_del_watchlist": "移除失敗: {msg}",
                "err_fill_holding": "請完整填寫股票代碼、持有股數與買進成本！",
                "toast_add_holding": "✅ 已成功加入持股 {sym}",
                "err_add_holding": "新增失敗: {msg}",
                "err_fill_symbol": "請填寫股票代碼！",
                "toast_add_watchlist": "✅ 已將 {sym} 加入自選監控",
                "err_add_watchlist": "加入自選失敗: {msg}",
                "confirm_stop_server": "確定要關閉 G_Finance 本地伺服器嗎？關閉後畫面將停止連線。",
                "alert_server_stopping": "伺服器正在停止，請手動關閉此分頁或 a-Shell 視窗。",
                "alert_stop_sent": "已發送停止指令。",
                "err_network": "網路錯誤: {msg}",
                "chart_metric_lbl": "指標:",
                "chart_metric_total": "總市值 (含本金)",
                "chart_metric_price": "股價 (每股)",
                "chart_metric_growth": "淨增長 / 盈虧 (扣除本金)",
                "chart_metric_growth_div": "淨增長 + 累計股息",
                "chart_metric_div_only": "僅累計股息分派",
                "chart_style_lbl": "樣式:",
                "chart_style_area": "區域面積",
                "chart_style_line": "折線圖",
                "chart_invested_capital": "投入本金: ",
                "chart_div_received": "累計股息: ",
                "th_currency": "幣種",
                "lbl_total_cost": "成本總計:"
        },
        "zh_CN": {
                "tab_portfolio": "投资组合",
                "tab_chart": "走势图表",
                "tab_fire": "FIRE 退休规划",
                "tab_watchlist": "自选监控",
                "tab_tools": "工具与资讯",
                "nav_portfolio": "📊 投资组合",
                "nav_chart": "📈 走势图表",
                "nav_fire": "🔥 FIRE 退休规划",
                "nav_watchlist": "👁️ 自选监控",
                "nav_tools": "⚙️ 工具与资讯",
                "detecting": "设备检测中...",
                "all_portfolios": "全部投资组合",
                "theme_toggle": "切换深色/浅色主题",
                "synced_now": "刚刚更新",
                "synced_at": "更新于 {time}",
                "net_worth_title": "投资组合总净值",
                "active_holdings": "持仓标的 ({count})",
                "btn_add": "➕ 新增",
                "view_table": "📋 表格检视",
                "view_card": "📱 卡片检视",
                "toggle_to_table": "📊 切换表格检视 ⮀",
                "toggle_to_card": "📱 切换卡片检视 ⮀",
                "th_symbol": "代码",
                "th_shares": "股数",
                "th_cost": "均价",
                "th_price": "市价",
                "th_value": "总市值",
                "th_roi": "回报率",
                "alloc_equity": "📈 权益资产: {val} ({pct}%)",
                "alloc_safe": "🛡️ 安全缓冲: {val} ({pct}%)",
                "pill_div": "年股息: {val}",
                "pill_yield": "股息率: {val}%",
                "empty_holdings": "目前此投资组合尚无持仓标的。",
                "shs_unit": "股",
                "chart_title": "市场与资产走势",
                "chart_donut_title": "投资组合资产配置图",
                "btn_view_chart": "📈 查看实时走势图",
                "total_portfolio": "📈 总资产 (Total Portfolio)",
                "holdings_group": "💼 持仓标的 (Holdings)",
                "watchlist_group": "👁️ 自选监控 (Watchlist)",
                "chart_loading": "载入走势中...",
                "chart_tip": "👆 手指滑动或鼠标悬停可查阅任意点位",
                "ref_prev_close": "昨收参考: {val}",
                "realtime_trend": "实时走势",
                "updated_at": "更新于 {time}",
                "total_assets": "总资产",
                "holdings_unit": "档标的",
                "other_assets": "其他标的",
                "fire_safe_title": "🛡️ 25年保证负债安全缓冲",
                "fire_safe_note": "🛡️ 缓冲储备已覆盖 {years} / 25.0 计划年数",
                "fire_div_title": "💵 被动股息生活费覆盖缺口",
                "fire_div_note_gap": "📈 按5%年增率预计 {years} 年黄金交叉",
                "fire_div_note_met": "✓ 已达成被动股息完全财务自由",
                "fire_cap_title": "🏛️ Bernstein 3.2% 本金安全缺口",
                "fire_cap_note_gap": "💰 预计每月需定投加码: {val}/月",
                "fire_cap_note_met": "✓ 已达成安全提领本金目标",
                "fire_burn_title": "⚡ 实质提领率警戒仪表板",
                "fire_timeline_title": "⏳ 人生周期与退休提领时间轴",
                "current_safe": "当前安全资产: {val} ({pct}%)",
                "target_safe": "目标储备: {val}",
                "current_div": "当前年股息: {val} ({pct}%)",
                "target_rle": "目标生活费: {val}",
                "current_wealth": "当前总净值: {val} ({pct}%)",
                "target_capital": "3.2% 本金目标: {val}",
                "fire_auditing": "审核中...",
                "fire_gap_prefix": "缺口: -{val}",
                "fire_target_met": "✓ 已达标",
                "fire_burn_safe": "安全充裕",
                "fire_burn_swr": "永续区间",
                "fire_burn_danger": "超额提领危险",
                "burn_zone_safe": "<2.0% 安全充裕",
                "burn_zone_swr": "2.0-3.5% 永续 SWR",
                "burn_zone_danger": ">3.5% 警戒超额",
                "tl_age_now": "● 目前年龄 45岁",
                "tl_age_fire": "★ 预计退休 60岁",
                "tl_age_end": "🏁 预期寿命 90岁",
                "tl_accum_phase": "⏳ 15年资产积累期",
                "tl_dist_phase": "🏖️ 30年退休提领期",
                "watchlist_title": "实时自选监控与目标价",
                "tracked_count": "{count} 档监控中",
                "target_hit": "🎯 已达买进: {val}",
                "target": "目标: {val}",
                "no_target": "未设目标",
                "empty_watchlist": "自选清单目前尚无追踪标的。",
                "st_whatif": "💡 What-If 加码",
                "st_rebalance": "⚖️ 再平衡",
                "st_drip": "💧 股息复利",
                "st_split": "✂️ 股票分割",
                "st_selling": "💰 卖出损益",
                "st_health": "🩺 健康检查",
                "st_reports": "📄 财务报表",
                "st_cloud": "☁️ 云端同步",
                "st_backup": "💾 数据备份",
                "st_diag": "📱 系统诊断",
                "btn_google_sheet_sync": "Google 表格同步",
                "cloud_title": "☁️ Google 表格云端同步",
                "cloud_desc": "使用 Google Sheets 表格作为跨设备云端数据库，无缝同步持仓、自选清单与交易历史记录。",
                "cloud_lbl_status": "云端连接状态:",
                "cloud_lbl_last_sync": "上次同步时间:",
                "cloud_lbl_device": "本机设备识别:",
                "cloud_cfg_title": "⚙️ Google Apps Script 设置",
                "cloud_lbl_url": "Google Apps Script 网页应用网址 (Web App URL)",
                "cloud_lbl_autoupload": "编辑或交易时自动后台同步至云端",
                "btn_sync_now": "立即双向同步",
                "btn_sync_push": "强制上传至表格",
                "btn_sync_pull": "强制自表格下载",
                "btn_test_connection": "测试连接",
                "btn_save_config": "保存设置",
                "cloud_guide_summary": "📖 30 秒快速安装与部署教学 (点击展开)",
                "cloud_backup_title": "☁️ Google 表格实时云端同步",
                "cloud_backup_desc": "与 Google Sheets 保持双向同步，支持自动多版本备份与跨设备无缝接轨。",
                "btn_cloud_settings": "云端设置",
                "btn_copy_script": "复制 Google Apps Script 代码",
                "whatif_title": "💡 What-If 模拟加码试算机",
                "whatif_desc": "模拟加码或买进新标的，实时预估对总资产、持有股数、配置比例与年股息的影响。",
                "whatif_sel_lbl": "选择持仓标的 (或手动输入)",
                "whatif_custom_ticker": "-- 自定义代码 (Custom Ticker) --",
                "lbl_symbol": "股票代码 (Symbol)",
                "lbl_price": "预估股价 (Price)",
                "lbl_yield": "预估股息率 % (Yield)",
                "lbl_amount": "加码金额 ($ Amount)",
                "whatif_reset_5k": "重置 5,000",
                "whatif_res_tot": "总资产变化:",
                "whatif_res_shs": "预计新增股数:",
                "whatif_res_alloc": "该标的配置占比:",
                "whatif_res_div": "被动年股息增长:",
                "rebal_title": "⚖️ 资产再平衡试算机",
                "rebal_desc": "自定义各标的目标配置比例或套用模型，试算达成目标所需的买卖金额与股数。",
                "rebal_cash_lbl": "额外注入新资金 (现金加码)",
                "rebal_btn_equal": "均等权重 (Equal)",
                "rebal_btn_reset": "重置为现状",
                "rebal_sum_lbl": "目标权重总和:",
                "rebal_total_val_lbl": "再平衡总资产规模:",
                "rebal_cur_val": "现值: {val} ({pct}%)",
                "rebal_target_pct": "目标%:",
                "rebal_hold": "✓ 持平 (HOLD)",
                "rebal_buy": "买进 +{diff} (+{shs}股)",
                "rebal_sell": "卖出 -{diff} ({shs}股)",
                "rebal_ok": "✓ 正常",
                "rebal_warn": "⚠️ (未达100%)",
                "drip_title": "💧 股息再投资与复利试算 (DRIP)",
                "drip_desc": "试算股息复利滚存带来的现金流指数级增长。",
                "drip_init_div": "目前年股息 (Annual Div)",
                "drip_div_growth": "年股息增长率 % (Growth)",
                "drip_return": "年化再投资回报率 %",
                "drip_extra": "每年额外加码资金",
                "th_year": "年期",
                "th_ann_div": "年被动股息",
                "th_monthly_flow": "月被动现金流",
                "th_total_wealth": "复利滚存总资产",
                "split_title": "✂️ 股票分割 / 反分割计算机",
                "split_desc": "当持股进行正分割 (如 2:1, 10:1) 或反分割 (如 1:2) 时，自动校正股数与每股平均买入成本。",
                "split_sel_lbl": "选择持仓标的",
                "split_manual": "-- 手动输入 --",
                "split_pre_shs": "分割前持有股数",
                "split_pre_cost": "分割前每股成本 ($)",
                "split_num": "分割分子 (换成几股)",
                "split_den": "分割分母 (原本几股)",
                "split_ratio_1_2": "1:2 反分割",
                "split_ratio_1_4": "1:4 反分割",
                "split_res_shs_lbl": "校正后持有股数:",
                "split_res_cost_lbl": "校正后每股平均成本:",
                "split_res_tot_lbl": "总投资成本守恒:",
                "split_unchanged": "(不变 ✓)",
                "sell_title": "💰 获利了结与卖出损益试算机",
                "sell_desc": "试算部分或全部卖出时的已实现资本利得、现金入账与剩余持仓价值。",
                "sell_sel_lbl": "选择持仓标的",
                "sell_tot_shs": "目前总持有股数",
                "sell_cost_price": "平均每股买入成本 ($)",
                "sell_qty": "预计卖出股数",
                "sell_price": "预计每股卖出价 ($)",
                "sell_pct_25": "卖出 25%",
                "sell_pct_50": "卖出 50%",
                "sell_pct_75": "卖出 75%",
                "sell_pct_100": "全部清仓 (100%)",
                "sell_res_proceeds_lbl": "卖出回收现金总额:",
                "sell_res_gain_lbl": "已实现资本利得 (获利):",
                "sell_res_rem_shs_lbl": "剩余持仓股数:",
                "sell_res_rem_val_lbl": "剩余部位市值:",
                "health_title": "🩺 数据完整性检查与一键修复",
                "health_desc": "自动审核 portfolio.csv 与 watchlist.csv，检查是否有未填成本、缺少币别、未分类标的或异常记录。",
                "btn_scan": "🔍 执行完整扫描",
                "btn_repair": "🛠️ 一键修复异常",
                "health_init_sum": "点击上方按钮开始检查",
                "health_init_det": "支持自动校正常见数据格式问题。",
                "health_scanning": "⏳ 正在检查数据完整性...",
                "health_ok_sum": "✅ 数据健康状态良好 (100% 完整)",
                "health_ok_det": "已审核所有持仓与自选清单，无缺少成本、币别不一致或异常代码。",
                "health_issue_sum": "⚠️ 发现 {count} 项数据格式问题",
                "health_repairing": "⏳ 正在执行自动修复程序...",
                "health_repaired_sum": "✅ 数据修复完成！",
                "health_repaired_det": "已修正数据问题，重新载入最新数据中...",
                "reports_title": "📄 完整财务执行摘要报表",
                "reports_desc": "产出专业的 HTML / PDF 格式财务报表，包含净值图表、资产配置分析、持股明细及收益预测。",
                "btn_open_report": "📑 打开完整 HTML 财务报表 (新标签页)",
                "btn_preview_report": "📱 在页面内嵌预览报表",
                "backup_title": "💾 数据导出与备份下载",
                "backup_desc": "随时下载持股与自选名单，保护您的财务数据安全无虞。",
                "btn_dl_portfolio": "📥 下载持股数据 (portfolio.csv)",
                "btn_dl_watchlist": "📥 下载自选清单 (watchlist.csv)",
                "btn_dl_json": "📦 下载完整系统备份 (JSON Backup)",
                "diag_title": "📱 系统与设备诊断",
                "diag_platform_lbl": "运行平台识别:",
                "diag_touch_lbl": "触控优化状态:",
                "diag_res_lbl": "屏幕分辨率:",
                "diag_pwa_lbl": "独立 PWA 模式:",
                "btn_mode_iphone": "📱 iPhone 模式",
                "btn_mode_ipad": "📟 iPad 模式",
                "btn_mode_pc": "💻 PC 模式",
                "quick_server_actions": "⚡ 快速服务器操作",
                "btn_refresh_quotes": "🔄 立即刷新所有股价行情",
                "btn_stop_server": "🛑 停止 G_Finance 服务器",
                "quick_refresh": "🔄 立即刷新行情",
                "quick_stop": "🛑 停止服务器",
                "refreshing": "🔄 正在获取实时股价行情...",
                "refresh_done": "✅ 行情更新完成 ({updated}/{total} 档已更新)",
                "refresh_cache": "⚡ 使用缓存报价数据",
                "refresh_timeout": "⚠️ 更新行情连接超时",
                "holding_details": "持仓标的明细",
                "lbl_cur_price": "当前市价:",
                "lbl_shares": "持有股数:",
                "lbl_cost_basis": "投资成本:",
                "lbl_market_val": "当前市值:",
                "lbl_unrealized_pl": "未实现损益:",
                "lbl_est_div": "预估年股息:",
                "quick_actions": "🚀 快捷联动功能",
                "btn_h_chart": "📈 查看实时走势图",
                "btn_h_whatif": "💡 导入 What-If 加码模拟试算",
                "btn_h_split": "✂️ 导入股票分割 / 反分割计算机",
                "btn_h_sell": "💰 导入卖出获利了结试算机",
                "btn_h_delete": "🗑️ 删除此持股标的",
                "watchlist_details": "自选监控标的明细",
                "lbl_w_curp": "当前市价:",
                "lbl_w_tgtp": "目标买入价:",
                "lbl_w_diff": "距目标价差:",
                "lbl_w_notes": "备注标签:",
                "w_not_fetched": "尚未获取报价",
                "w_not_set": "未设定",
                "w_target_hit_desc": "🎯 已达买入目标 (低于目标价 ${diff})",
                "w_above_target_desc": "高于目标价 +${diff} (+{pct}%)",
                "w_no_notes": "无备注",
                "btn_w_chart": "📈 查看实时走势图",
                "btn_w_whatif": "💡 导入 What-If 模拟买入",
                "btn_w_delete": "🗑️ 从自选清单移除",
                "add_holding_title": "➕ 新增投资持股",
                "lbl_sym_req": "股票代码 (Symbol)*",
                "lbl_name_opt": "公司名称 (Name)",
                "lbl_shares_req": "持有股数 (Shares)*",
                "lbl_cost_req": "每股买入成本 (Cost)*",
                "lbl_currency": "币别 (Currency)",
                "lbl_portfolio": "所属投资组合 (Portfolio)",
                "ph_sym_h": "如 VOO, AAPL",
                "ph_name_h": "可选填",
                "ph_shares_h": "10",
                "ph_cost_h": "150.0",
                "ph_port_h": "如 Core, Tech",
                "btn_confirm_add_h": "确认新增持股",
                "add_watchlist_title": "➕ 新增自选监控标的",
                "lbl_tgt_req": "目标买入价 (Target Price)*",
                "lbl_notes_opt": "备注说明 (Notes)",
                "ph_sym_w": "如 NVDA, MSFT",
                "ph_name_w": "可选填",
                "ph_tgt_w": "120.0",
                "ph_notes_w": "例: 回调至季线买入",
                "btn_confirm_add_w": "确认加入自选",
                "confirm_del_holding": "确定要删除持股 {sym} 吗？",
                "toast_del_holding": "🗑️ 已成功删除持股 {sym}",
                "err_del_holding": "删除失败: {msg}",
                "confirm_del_watchlist": "确定要从自选清单移除 {sym} 吗？",
                "toast_del_watchlist": "🗑️ 已从自选清单移除 {sym}",
                "err_del_watchlist": "移除失败: {msg}",
                "err_fill_holding": "请完整填写股票代码、持有股数与买入成本！",
                "toast_add_holding": "✅ 已成功加入持股 {sym}",
                "err_add_holding": "新增失败: {msg}",
                "err_fill_symbol": "请填写股票代码！",
                "toast_add_watchlist": "✅ 已将 {sym} 加入自选监控",
                "err_add_watchlist": "加入自选失败: {msg}",
                "confirm_stop_server": "确定要关闭 G_Finance 本地服务器吗？关闭后画面将停止连接。",
                "alert_server_stopping": "服务器正在停止，请手动关闭此标签页或 a-Shell 窗口。",
                "alert_stop_sent": "已发送停止指令。",
                "err_network": "网络错误: {msg}",
                "chart_metric_lbl": "指标:",
                "chart_metric_total": "总市值 (含本金)",
                "chart_metric_price": "股价 (每股)",
                "chart_metric_growth": "净增长 / 盈亏 (扣除本金)",
                "chart_metric_growth_div": "净增长 + 股息收益",
                "chart_metric_div_only": "仅累计股息分派",
                "chart_style_lbl": "样式:",
                "chart_style_area": "区域面积",
                "chart_style_line": "折线图",
                "chart_invested_capital": "投入本金: ",
                "chart_div_received": "累计股息: ",
                "th_currency": "币种",
                "lbl_total_cost": "成本总计:"
        }
};

        function t(key, vars = {}) {
            const dict = I18N[currentLang] || I18N.zh_TW || {};
            let str = dict[key] || (I18N.zh_TW && I18N.zh_TW[key]) || (I18N.en && I18N.en[key]) || key;
            for (const [k, v] of Object.entries(vars)) {
                str = str.replace(`{${k}}`, v);
            }
            return str;
        }

        function setLanguage(lang) {
            if (!I18N[lang]) lang = 'zh_TW';
            currentLang = lang;
            try { localStorage.setItem('g_finance_lang', lang); } catch (e) {}
            const sel = document.getElementById('lang-select');
            if (sel) sel.value = lang;
            updateUIStrings();
            if (currentPortfolioData) renderPortfolio(currentPortfolioData);
            if (windowLastFireData) renderFIRE(windowLastFireData);
            if (_lastWatchlistItems && _lastWatchlistItems.length >= 0) renderWatchlist(_lastWatchlistItems);
            if (currentChartData) {
                currentPreparedChart = prepareMetricSeries(currentChartData);
                renderChartDisplay(currentPreparedChart);
                drawPriceChart(currentPreparedChart);
            }
            if (currentPortfolioData && currentPortfolioData.holdings) {
                populateToolsDropdowns(currentPortfolioData.holdings);
                drawDonutChart(currentPortfolioData.holdings);
            }
            // Re-trigger active tool calculation if visible
            const activeTool = document.querySelector('.tool-subpane.active');
            if (activeTool) {
                const tid = activeTool.id.replace('subpane-', '');
                if (tid === 'whatif') runWhatIfCalc();
                else if (tid === 'rebalance') runRebalanceCalc();
                else if (tid === 'drip') runDripCalc();
                else if (tid === 'split') runSplitCalc();
                else if (tid === 'selling') runSellCalc();
            }
        }

        function updateUIStrings() {
            // 1. Automatic attribute translation
            document.querySelectorAll('[data-i18n]').forEach(el => {
                const k = el.getAttribute('data-i18n');
                if (k) el.textContent = t(k);
            });
            document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
                const k = el.getAttribute('data-i18n-placeholder');
                if (k) el.placeholder = t(k);
            });
            document.querySelectorAll('[data-i18n-title]').forEach(el => {
                const k = el.getAttribute('data-i18n-title');
                if (k) el.title = t(k);
            });

            // 2. Desktop Top Navigation
            const dP = document.getElementById('dnav-portfolio');
            if (dP) dP.textContent = '📊 ' + t('tab_portfolio');
            const dC = document.getElementById('dnav-chart');
            if (dC) dC.textContent = '📈 ' + t('tab_chart');
            const dF = document.getElementById('dnav-fire');
            if (dF) dF.textContent = '🔥 ' + t('tab_fire');
            const dW = document.getElementById('dnav-watchlist');
            if (dW) dW.textContent = '👁️ ' + t('tab_watchlist');
            const dT = document.getElementById('dnav-tools');
            if (dT) dT.textContent = '⚙️ ' + t('tab_tools');

            // 3. Mobile Bottom Navigation
            const bP = document.getElementById('btab-portfolio');
            if (bP && bP.querySelector('span:last-child')) bP.querySelector('span:last-child').textContent = t('tab_portfolio');
            const bC = document.getElementById('btab-chart');
            if (bC && bC.querySelector('span:last-child')) bC.querySelector('span:last-child').textContent = t('tab_chart');
            const bF = document.getElementById('btab-fire');
            if (bF && bF.querySelector('span:last-child')) bF.querySelector('span:last-child').textContent = t('tab_fire');
            const bW = document.getElementById('btab-watchlist');
            if (bW && bW.querySelector('span:last-child')) bW.querySelector('span:last-child').textContent = t('tab_watchlist');
            const bT = document.getElementById('btab-tools');
            if (bT && bT.querySelector('span:last-child')) bT.querySelector('span:last-child').textContent = t('tab_tools');

            // 4. Toggle view button
            const btnTog = document.getElementById('btn-toggle-view');
            if (btnTog) btnTog.textContent = isTableView ? t('toggle_to_card') : t('toggle_to_table');

            // 5. Report link
            const repBtn = document.getElementById('btn-open-report');
            if (repBtn) repBtn.href = `/api/report?currency=${currentCurrency}&lang=${currentLang}`;

            // 6. Quick Server Buttons in Tools Tab
            const btnSRefresh = document.querySelector('#subpane-diag button[onclick*="triggerManualRefresh"]');
            if (btnSRefresh) btnSRefresh.textContent = t('btn_refresh_quotes');
            const btnSStop = document.querySelector('#subpane-diag button[onclick*="stopServerRemote"]');
            if (btnSStop) btnSStop.textContent = t('btn_stop_server');

            // 7. Metric and Style Selectors Value Sync
            const mSel = document.getElementById('chart-metric-select');
            if (mSel) mSel.value = currentChartMetric;
            const sSel = document.getElementById('chart-style-select');
            if (sSel) sSel.value = currentChartStyle;
        }

        // Auto Platform & Orientation Detection
        function detectPlatform() {
            const ua = navigator.userAgent;
            const isTouch = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
            const w = window.innerWidth;
            const h = window.innerHeight;
            const isLandscape = w > h;
            let type = 'desktop';
            let label = '💻 Desktop';

            if (/iPad/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) {
                type = 'ipad';
                label = isLandscape ? '📟 iPad (Landscape)' : '📟 iPad (Portrait)';
            } else if (/iPhone|iPod/i.test(ua)) {
                type = 'iphone';
                label = isLandscape ? '📱 iPhone (Landscape)' : '📱 iPhone (Portrait)';
            } else if (isTouch && (w < 768 || (isLandscape && h < 500))) {
                type = 'iphone';
                label = isLandscape ? '📱 Phone (Landscape)' : '📱 Phone (Portrait)';
            } else if (isTouch) {
                type = 'ipad';
                label = isLandscape ? '📟 Touch (Landscape)' : '📟 Touch (Portrait)';
            } else {
                label = isLandscape ? '💻 Desktop (Wide)' : '💻 Desktop (Portrait)';
            }

            const isLight = document.documentElement.classList.contains('theme-light') ||
                            document.body.classList.contains('theme-light') ||
                            (function() { try { return localStorage.getItem('gfinance_theme') === 'light'; } catch(e) { return false; } })();
            document.body.className = `platform-${type} ${isLandscape ? 'orientation-landscape' : 'orientation-portrait'}${isLight ? ' theme-light' : ''}`;
            if (isLight) {
                document.documentElement.classList.add('theme-light');
                document.body.classList.add('theme-light');
            } else {
                document.documentElement.classList.remove('theme-light');
                document.body.classList.remove('theme-light');
            }
            const badge = document.getElementById('platform-badge');
            if (badge) badge.textContent = label;
            const diagPlat = document.getElementById('diag-platform');
            if (diagPlat) diagPlat.textContent = label;
            const diagTouch = document.getElementById('diag-touch');
            if (diagTouch) diagTouch.textContent = isTouch ? 'Yes (Touch-Friendly)' : 'No (Mouse/Pointer)';
            const diagRes = document.getElementById('diag-res');
            if (diagRes) diagRes.textContent = `${w} × ${h} (${isLandscape ? 'Landscape' : 'Portrait'})`;
            const diagStand = document.getElementById('diag-standalone');
            if (diagStand) diagStand.textContent = (window.navigator.standalone || window.matchMedia('(display-mode: standalone)').matches) ? 'Yes (Installed PWA)' : 'Browser Mode';
        }

        function forceLayout(mode) {
            const isLight = document.body.classList.contains('theme-light');
            document.body.className = 'platform-' + mode + (isLight ? ' theme-light' : '');
            const badge = document.getElementById('platform-badge');
            if (badge) badge.textContent = 'Forced: ' + mode;
        }

        function toggleTheme() {
            const isLightNow = document.body.classList.toggle('theme-light');
            if (document.documentElement) {
                document.documentElement.classList.toggle('theme-light', isLightNow);
            }
            try {
                localStorage.setItem('gfinance_theme', isLightNow ? 'light' : 'dark');
            } catch (e) {
                console.error('Failed to save theme preference:', e);
            }
            if (currentChartData) {
                const prepared = currentPreparedChart || prepareMetricSeries(currentChartData);
                drawPriceChart(prepared);
            }
            if (currentPortfolioData && currentPortfolioData.holdings) {
                drawDonutChart(currentPortfolioData.holdings);
            }
        }

        function switchTab(tabId) {
            // Update Tab Panes
            document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
            const targetPane = document.getElementById('tab-' + tabId);
            if (targetPane) targetPane.classList.add('active');

            // Update Top Desktop Nav
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            const desktopBtn = document.getElementById('dnav-' + tabId) || Array.from(document.querySelectorAll('.nav-btn')).find(b => b.getAttribute('onclick') && b.getAttribute('onclick').includes(tabId));
            if (desktopBtn) desktopBtn.classList.add('active');

            // Update Mobile Bottom Tabs
            document.querySelectorAll('.tab-item').forEach(b => b.classList.remove('active'));
            const mobileBtn = document.getElementById('btab-' + tabId);
            if (mobileBtn) mobileBtn.classList.add('active');

            // Trigger chart refresh when entering Chart tab
            if (tabId === 'chart') {
                loadChart();
                if (currentPortfolioData && currentPortfolioData.holdings) drawDonutChart(currentPortfolioData.holdings);
            }
        }

        function onCurrencyChange(val) {
            currentCurrency = val;
            const repBtn = document.getElementById('btn-open-report');
            if (repBtn) repBtn.href = `/api/report?currency=${currentCurrency}&lang=${currentLang}`;
            loadData();
        }

        function onPortfolioChange(val) {
            currentPortfolio = val;
            loadData();
            const chartPane = document.getElementById('tab-chart');
            if (chartPane && chartPane.classList.contains('active')) {
                loadChart();
            }
        }

        let isRefreshing = false;

        function showToast(msg, duration = 3000) {
            const toast = document.getElementById('app-toast');
            if (!toast) return;
            toast.textContent = msg;
            toast.classList.add('visible');
            if (window._toastTimer) clearTimeout(window._toastTimer);
            window._toastTimer = setTimeout(() => {
                toast.classList.remove('visible');
            }, duration);
        }

        function hideToast() {
            const toast = document.getElementById('app-toast');
            if (toast) toast.classList.remove('visible');
        }

        async function triggerManualRefresh() {
            if (isRefreshing) return;
            isRefreshing = true;
            if (window._chartClientCache) window._chartClientCache.clear();

            const fabs = document.querySelectorAll('.fab-refresh');
            fabs.forEach(f => f.classList.add('spinning'));
            showToast(t('refreshing'));

            try {
                const res = await fetch('/api/refresh', { method: 'POST' });
                const json = await res.json();
                if (json.status === 'success') {
                    showToast(t('refresh_done', { updated: json.updated_count || 0, total: json.total || 0 }));
                } else {
                    showToast(t('refresh_cache'));
                }
            } catch (err) {
                console.error('Refresh request failed:', err);
                showToast(t('refresh_timeout'));
            } finally {
                await loadData();
                fabs.forEach(f => f.classList.remove('spinning'));
                isRefreshing = false;
            }
        }

        function toggleHoldingsView() {
            isTableView = !isTableView;
            const btn = document.getElementById('btn-toggle-view');
            if (btn) btn.textContent = isTableView ? t('toggle_to_card') : t('toggle_to_table');
            if (currentPortfolioData) {
                renderPortfolio(currentPortfolioData);
            } else {
                loadData();
            }
        }

        async function loadData() {
            // Update Sync Timestamp
            const syncEl = document.getElementById('last-sync-time');
            if (syncEl) {
                const now = new Date();
                syncEl.textContent = t('synced_at', { time: now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'}) });
            }

            // 1. Fetch Portfolio Data
            try {
                const pRes = await fetch(`/api/portfolio?currency=${currentCurrency}&portfolio=${encodeURIComponent(currentPortfolio)}`);
                if (pRes.ok) {
                    const pData = await pRes.json();
                    renderPortfolio(pData);
                }
            } catch (err) {
                console.error('Failed to load portfolio:', err);
            }

            // 2. Fetch FIRE Metrics
            try {
                const fRes = await fetch(`/api/fire?currency=${currentCurrency}`);
                if (fRes.ok) {
                    const fData = await fRes.json();
                    windowLastFireData = fData;
                    renderFIRE(fData);
                }
            } catch (err) {
                console.error('Failed to load FIRE:', err);
            }

            // 3. Fetch Watchlist
            try {
                const wRes = await fetch(`/api/watchlist`);
                if (wRes.ok) {
                    const wData = await wRes.json();
                    renderWatchlist(wData);
                }
            } catch (err) {
                console.error('Failed to load watchlist:', err);
            }

            // 4. Update Interactive Chart if active
            try {
                const chartTab = document.getElementById('tab-chart');
                if (chartTab && chartTab.classList.contains('active')) {
                    loadChart();
                }
            } catch (err) {
                console.error('Failed to refresh chart:', err);
            }
        }

        function renderPortfolio(data) {
            const sym = data.currency_symbol || '$';
            document.getElementById('net-worth-val').textContent = sym + Number(data.total_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
            const fxEl = document.getElementById('fx-rates-badge');
            if (fxEl && data.fx_rates_summary) {
                fxEl.textContent = '💱 ' + data.fx_rates_summary;
            }

            // Gain pill
            const pl = Number(data.total_unrealized_pl || 0);
            const plPct = Number(data.overall_roi_pct || 0);
            const plEl = document.getElementById('pill-gain');
            plEl.textContent = (pl >= 0 ? '+' : '') + sym + pl.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' (' + plPct.toFixed(2) + '%)';
            plEl.className = 'pill ' + (pl >= 0 ? 'pos' : 'neg');

            // Dividend & Yield
            const totDiv = Number(data.total_annual_dividend || 0);
            document.getElementById('pill-div').textContent = t('pill_div', { val: sym + totDiv.toLocaleString(undefined, {maximumFractionDigits: 0}) });
            const yld = data.total_value > 0 ? (totDiv / data.total_value * 100) : 0;
            document.getElementById('pill-yield').textContent = t('pill_yield', { val: yld.toFixed(2) });

            // Asset split
            const eqVal = Number(data.equity_assets || 0);
            const safeVal = Number(data.safe_assets || 0);
            const tot = eqVal + safeVal;
            const eqPct = tot > 0 ? (eqVal / tot * 100) : 0;
            const safePct = tot > 0 ? (safeVal / tot * 100) : 0;

            document.getElementById('alloc-eq-lbl').textContent = t('alloc_equity', { val: sym + eqVal.toLocaleString(undefined, {maximumFractionDigits: 0}), pct: eqPct.toFixed(1) });
            document.getElementById('alloc-safe-lbl').textContent = t('alloc_safe', { val: sym + safeVal.toLocaleString(undefined, {maximumFractionDigits: 0}), pct: safePct.toFixed(1) });
            document.getElementById('alloc-eq-bar').style.width = eqPct + '%';
            document.getElementById('alloc-safe-bar').style.width = safePct + '%';

            // Populate portfolio selector if empty
            const sel = document.getElementById('port-select');
            if (sel.options.length <= 1 && data.portfolios && data.portfolios.length > 0) {
                data.portfolios.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p;
                    opt.textContent = p;
                    sel.appendChild(opt);
                });
            }

            // Render holdings (Table or Touch Cards)
            const btnTog = document.getElementById('btn-toggle-view');
            if (btnTog) btnTog.textContent = isTableView ? t('toggle_to_card') : t('toggle_to_table');

            const listEl = document.getElementById('holdings-cards-container');
            listEl.innerHTML = '';
            const holdingsList = data.holdings || [];
            document.getElementById('holdings-count-title').textContent = t('active_holdings', { count: holdingsList.length });

            if (holdingsList.length === 0) {
                const emptyCard = document.createElement('div');
                emptyCard.className = 'card';
                emptyCard.style.textAlign = 'center';
                emptyCard.style.padding = '36px 16px';
                emptyCard.innerHTML = `
                    <div style="font-size: 2rem; margin-bottom: 8px;">💼</div>
                    <div style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 14px;">${t('empty_holdings')}</div>
                    <button class="quick-btn" style="color: var(--accent-blue); padding: 6px 16px;" onclick="openAddHoldingModal()">${t('btn_add')}</button>
                `;
                listEl.appendChild(emptyCard);
            } else if (isTableView) {
                // Table View
                const tableCard = document.createElement('div');
                tableCard.className = 'desktop-table-card card';
                tableCard.style.padding = '0';
                tableCard.style.overflowX = 'auto';

                let rowsHtml = '';
                holdingsList.forEach(h => {
                    const plH = Number(h.unrealized_pl || 0);
                    const plHPct = Number(h.roi_pct || 0);
                    const isPos = plH >= 0;
                    const cp = Number(h.current_price || 0);
                    const bp = Number(h.buy_price || (h.shares > 0 ? (Number(h.cost_basis || 0) / h.shares) : 0));
                    const mv = Number(h.market_value || 0);
                    const hSym = h.currency_symbol || '$';
                    const isDiff = h.currency && data.currency && (h.currency !== data.currency);

                    rowsHtml += `
                        <tr style="cursor: pointer;" onclick="openHoldingDetailModal('${h.symbol}', '${(h.portfolio || '').replace(/'/g, "\\'")}')">
                            <td><strong>${h.symbol}</strong><br><small style="color: var(--text-muted);">${h.name || '-'}${h.portfolio ? ' (' + h.portfolio + ')' : ''}</small></td>
                            <td style="text-align: center;"><span class="pill item-badge" style="font-size: 0.68rem; padding: 1px 5px;">${h.currency || 'USD'}</span></td>
                            <td style="text-align: right;">${h.shares}</td>
                            <td style="text-align: right;">${hSym}${bp.toFixed(2)}</td>
                            <td style="text-align: right;"><strong>${hSym}${cp.toFixed(2)}</strong></td>
                            <td style="text-align: right;">
                                ${hSym}${mv.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                                ${isDiff ? `<br><small style="color: var(--text-muted);">≈ ${data.currency_symbol}${Number(h.converted_market_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</small>` : ''}
                            </td>
                            <td style="text-align: right;"><span class="pill item-badge ${isPos ? 'pos' : 'neg'}">${isPos ? '+' : ''}${plHPct.toFixed(1)}%</span></td>
                        </tr>
                    `;
                });

                tableCard.innerHTML = `
                    <table>
                        <thead>
                            <tr>
                                <th>${t('th_symbol')}</th>
                                <th style="text-align: center;">${t('th_currency')}</th>
                                <th style="text-align: right;">${t('th_shares')}</th>
                                <th style="text-align: right;">${t('th_cost')}</th>
                                <th style="text-align: right;">${t('th_price')}</th>
                                <th style="text-align: right;">${t('th_value')}</th>
                                <th style="text-align: right;">${t('th_roi')}</th>
                            </tr>
                        </thead>
                        <tbody>${rowsHtml}</tbody>
                    </table>
                `;
                listEl.appendChild(tableCard);
            } else {
                // Mobile Touch Cards View
                holdingsList.forEach(h => {
                    const card = document.createElement('div');
                    card.className = 'item-card';
                    const plH = Number(h.unrealized_pl || 0);
                    const plHPct = Number(h.roi_pct || 0);
                    const isPos = plH >= 0;
                    const hSym = h.currency_symbol || '$';
                    const bp = Number(h.buy_price || 0);
                    const mv = Number(h.market_value || 0);
                    const isDiff = h.currency && data.currency && (h.currency !== data.currency);

                    card.innerHTML = `
                        <div class="item-left">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                <strong>${h.symbol}</strong>
                                <span class="pill item-badge" style="font-size: 0.65rem; padding: 1px 5px; font-weight: 700;">${h.currency || 'USD'}</span>
                            </div>
                            <div>${h.name || '-'}${h.portfolio ? ' (' + h.portfolio + ')' : ''} &bull; ${h.shares} ${t('shs_unit')} @ ${hSym}${bp.toFixed(2)}</div>
                        </div>
                        <div class="item-right">
                            <div class="item-price">${hSym}${mv.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
                            ${isDiff ? `<div style="font-size: 0.68rem; color: var(--text-muted);">≈ ${data.currency_symbol}${Number(h.converted_market_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>` : ''}
                            <span class="pill item-badge ${isPos ? 'pos' : 'neg'}">${isPos ? '+' : ''}${plHPct.toFixed(1)}%</span>
                        </div>
                    `;
                    card.onclick = () => openHoldingDetailModal(h.symbol, h.portfolio || '');
                    listEl.appendChild(card);
                });
            }

            // Sync with financial tools and charts
            currentPortfolioData = data;
            populateToolsDropdowns(data.holdings || []);
            populateChartSymbols(data.holdings || [], _lastWatchlistItems);
            drawDonutChart(data.holdings || []);
            const reportBtn = document.getElementById('btn-open-report');
            if (reportBtn) reportBtn.href = `/api/report?currency=${currentCurrency}&lang=${currentLang}`;
            const dripInit = document.getElementById('drip-init-div');
            if (dripInit && !dripInit.value) {
                dripInit.value = (data.total_annual_dividend || 1200).toFixed(0);
                runDripCalc();
            }
        }

        function renderFIRE(res) {
            const sym = res.currency_symbol || '$';

            // Gap 1: Safe Liability Buffer
            const safeGap = Number(res.safe_asset_gap || 0);
            const safeTgt = Number(res.liability_matching_target || 0);
            const safeCur = Number(res.current_safe_assets || 0);
            const safePct = safeTgt > 0 ? Math.min(100, (safeCur / safeTgt * 100)) : 100;

            document.getElementById('fire-safe-val').textContent = sym + safeCur.toLocaleString(undefined, {maximumFractionDigits: 0});
            document.getElementById('fire-safe-cur').textContent = t('current_safe', { val: sym + safeCur.toLocaleString(undefined, {maximumFractionDigits: 0}), pct: safePct.toFixed(1) });
            document.getElementById('fire-safe-tgt').textContent = t('target_safe', { val: sym + safeTgt.toLocaleString(undefined, {maximumFractionDigits: 0}) });
            document.getElementById('fire-safe-bar').style.width = safePct + '%';
            document.getElementById('fire-safe-gap-bar').style.width = (100 - safePct) + '%';
            document.getElementById('fire-safe-badge').textContent = safeGap > 0 ? t('fire_gap_prefix', { val: sym + safeGap.toLocaleString(undefined, {maximumFractionDigits: 0}) }) : t('fire_target_met');
            document.getElementById('fire-safe-badge').className = 'pill ' + (safeGap > 0 ? 'neg' : 'pos');
            const coveredY = res.safe_asset_years_covered || (safeCur / ((safeTgt || 1) / 25)).toFixed(1);
            document.getElementById('fire-safe-note').textContent = t('fire_safe_note', { years: coveredY });

            // Gap 2: Passive Dividend Gap
            const divGap = Number(res.dividend_gap_annual || 0);
            const divCur = Number(res.current_annual_div || 0);
            const divTgt = Number(res.rle_annual || 0);
            const divPct = divTgt > 0 ? Math.min(100, (divCur / divTgt * 100)) : 100;

            document.getElementById('fire-div-val').textContent = `${sym}${divCur.toLocaleString(undefined, {maximumFractionDigits: 0})} / yr`;
            document.getElementById('fire-div-cur').textContent = t('current_div', { val: sym + divCur.toLocaleString(undefined, {maximumFractionDigits: 0}), pct: divPct.toFixed(1) });
            document.getElementById('fire-div-tgt').textContent = t('target_rle', { val: sym + divTgt.toLocaleString(undefined, {maximumFractionDigits: 0}) });
            document.getElementById('fire-div-bar').style.width = divPct + '%';
            document.getElementById('fire-div-gap-bar').style.width = (100 - divPct) + '%';
            document.getElementById('fire-div-badge').textContent = divGap > 0 ? t('fire_gap_prefix', { val: sym + divGap.toLocaleString(undefined, {maximumFractionDigits: 0}) }) : t('fire_target_met');
            document.getElementById('fire-div-badge').className = 'pill ' + (divGap > 0 ? 'amber' : 'pos');
            document.getElementById('fire-div-note').textContent = divGap > 0 ? t('fire_div_note_gap', { years: (res.years_to_crossover || 0).toFixed(1) }) : t('fire_div_note_met');

            // Gap 3: Bernstein 3.2% Principal Gap
            const capGap = Number(res.capital_gap_bernstein || 0);
            const capCur = Number(res.current_portfolio_val || 0);
            const capTgt = Number(res.bernstein_swr_32_target || 0);
            const capPct = capTgt > 0 ? Math.min(100, (capCur / capTgt * 100)) : 100;

            document.getElementById('fire-cap-val').textContent = sym + capCur.toLocaleString(undefined, {maximumFractionDigits: 0});
            document.getElementById('fire-cap-cur').textContent = t('current_wealth', { val: sym + capCur.toLocaleString(undefined, {maximumFractionDigits: 0}), pct: capPct.toFixed(1) });
            document.getElementById('fire-cap-tgt').textContent = t('target_capital', { val: sym + capTgt.toLocaleString(undefined, {maximumFractionDigits: 0}) });
            document.getElementById('fire-cap-bar').style.width = capPct + '%';
            document.getElementById('fire-cap-gap-bar').style.width = (100 - capPct) + '%';
            document.getElementById('fire-cap-badge').textContent = capGap > 0 ? t('fire_gap_prefix', { val: sym + capGap.toLocaleString(undefined, {maximumFractionDigits: 0}) }) : t('fire_target_met');
            document.getElementById('fire-cap-badge').className = 'pill ' + (capGap > 0 ? 'amber' : 'pos');
            document.getElementById('fire-cap-note').textContent = capGap > 0 ? t('fire_cap_note_gap', { val: sym + Number(res.monthly_savings_needed || 0).toLocaleString(undefined, {maximumFractionDigits: 0}) }) : t('fire_cap_note_met');

            // Burn Rate Speedometer
            const burn = Number(res.burn_rate_pct || 0);
            const burnEl = document.getElementById('fire-burn-rate');
            burnEl.textContent = burn.toFixed(2) + '%';
            const needleX = Math.max(5, Math.min(95, (burn / 6.0) * 100));
            document.getElementById('burn-needle').style.left = needleX + '%';
            document.getElementById('burn-needle-txt').textContent = burn.toFixed(2) + '%';

            let burnCol = 'var(--accent-green)';
            let burnTxt = t('fire_burn_safe');
            if (burn > 3.5) { burnCol = 'var(--accent-red)'; burnTxt = t('fire_burn_danger'); }
            else if (burn >= 2.0) { burnCol = 'var(--accent-yellow)'; burnTxt = t('fire_burn_swr'); }
            burnEl.style.color = burnCol;
            document.getElementById('burn-needle').style.color = burnCol;
            document.getElementById('fire-burn-badge').textContent = `${burn.toFixed(2)}% (${burnTxt})`;
            document.getElementById('fire-burn-badge').className = 'pill ' + (burn > 3.5 ? 'neg' : (burn >= 2.0 ? 'amber' : 'pos'));

            // Timeline calculations
            const curAge = res.current_age || 45;
            const retAge = res.retire_age || 60;
            const lifeExp = res.life_expectancy || 90;
            const accumY = Math.max(0, retAge - curAge);
            const distY = Math.max(0, lifeExp - retAge);

            document.getElementById('tl-now').textContent = t('tl_age_now');
            document.getElementById('tl-ret').textContent = t('tl_age_fire');
            document.getElementById('tl-end').textContent = t('tl_age_end');
            document.getElementById('tl-accum-txt').textContent = t('tl_accum_phase');
            document.getElementById('tl-dist-txt').textContent = t('tl_dist_phase');

            const totalSpan = accumY + distY;
            if (totalSpan > 0) {
                document.getElementById('tl-accum-bar').style.width = (accumY / totalSpan * 100) + '%';
                document.getElementById('tl-dist-bar').style.width = (distY / totalSpan * 100) + '%';
            }
        }

        function renderWatchlist(items) {
            _lastWatchlistItems = items || [];
            const listEl = document.getElementById('watchlist-cards-container');
            listEl.innerHTML = '';
            document.getElementById('wl-count-badge').textContent = t('tracked_count', { count: _lastWatchlistItems.length });

            if (_lastWatchlistItems.length === 0) {
                const emptyCard = document.createElement('div');
                emptyCard.className = 'card';
                emptyCard.style.textAlign = 'center';
                emptyCard.style.padding = '36px 16px';
                emptyCard.innerHTML = `
                    <div style="font-size: 2rem; margin-bottom: 8px;">👁️</div>
                    <div style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 14px;">${t('empty_watchlist')}</div>
                    <button class="quick-btn" style="color: var(--accent-blue); padding: 6px 16px;" onclick="openAddWatchlistModal()">${t('btn_add')}</button>
                `;
                listEl.appendChild(emptyCard);
                return;
            }

            _lastWatchlistItems.forEach(w => {
                const card = document.createElement('div');
                card.className = 'item-card';
                const curP = Number(w.current_price || 0);
                const tgtP = Number(w.target_price || 0);
                const isMet = (tgtP > 0 && curP > 0 && curP <= tgtP);
                const curPDisplay = curP > 0 ? `$${curP.toFixed(2)}` : '-';

                card.innerHTML = `
                    <div class="item-left">
                        <strong>${w.symbol}</strong>
                        <div>${w.name || '-'}</div>
                    </div>
                    <div class="item-right">
                        <div class="item-price">${curPDisplay}</div>
                        <span class="pill item-badge ${isMet ? 'pos' : 'blue'}">
                            ${isMet ? t('target_hit', { val: '$' + tgtP.toFixed(2) }) : (tgtP > 0 ? t('target', { val: '$' + tgtP.toFixed(2) }) : t('no_target'))}
                        </span>
                    </div>
                `;
                card.onclick = () => openWatchlistDetailModal(w.symbol);
                listEl.appendChild(card);
            });

            // Keep chart symbol selector synced
            populateChartSymbols(currentPortfolioData ? currentPortfolioData.holdings : [], _lastWatchlistItems);
        }

        // =============================================================
        // INTERACTIVE CHART & ASSET ALLOCATION ENGINE (GOOGLE FINANCE)
        // =============================================================
        function onChartSymbolChange(sym) {
            currentChartSymbol = sym || 'PORTFOLIO';
            loadChart();
        }

        function setChartTimeframe(tf) {
            currentChartTimeframe = tf;
            document.querySelectorAll('.tf-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.tf === tf);
            });
            loadChart();
        }

        function onChartMetricChange(val) {
            currentChartMetric = val;
            if (currentChartData) {
                currentPreparedChart = prepareMetricSeries(currentChartData);
                renderChartDisplay(currentPreparedChart);
                drawPriceChart(currentPreparedChart);
            }
        }

        function onChartStyleChange(val) {
            currentChartStyle = val;
            if (currentPreparedChart) {
                currentPreparedChart.style = val;
                drawPriceChart(currentPreparedChart);
            } else if (currentChartData) {
                currentPreparedChart = prepareMetricSeries(currentChartData);
                drawPriceChart(currentPreparedChart);
            }
        }

        const _chartClientCache = new Map();
        window._chartClientCache = _chartClientCache;

        let _chartAbortController = null;
        let _prefetchTimer = null;

        function prefetchTimeframes() {
            if (_prefetchTimer) clearTimeout(_prefetchTimer);
            _prefetchTimer = setTimeout(() => {
                const list = ['6M', 'YTD', '1Y', '5D', '1D', '5Y', 'MAX'];
                let idx = 0;
                function fetchNext() {
                    if (idx >= list.length) return;
                    const tf = list[idx++];
                    const k = `${currentChartSymbol}_${tf}_${currentCurrency}_${currentPortfolio}`;
                    if (!_chartClientCache.has(k)) {
                        fetch(`/api/chart?symbol=${encodeURIComponent(currentChartSymbol)}&timeframe=${tf}&currency=${currentCurrency}&portfolio=${encodeURIComponent(currentPortfolio)}`)
                            .then(r => r.ok ? r.json() : null)
                            .then(d => {
                                if (d && d.prices && d.prices.length >= 2) {
                                    _chartClientCache.set(k, { data: d, timestamp: Date.now() });
                                }
                                setTimeout(fetchNext, 300);
                            })
                            .catch(() => {
                                setTimeout(fetchNext, 500);
                            });
                    } else {
                        fetchNext();
                    }
                }
                fetchNext();
            }, 800);
        }

        async function loadChart(forceRefresh = false) {
            const cacheKey = `${currentChartSymbol}_${currentChartTimeframe}_${currentCurrency}_${currentPortfolio}`;
            const cached = _chartClientCache.get(cacheKey);
            const now = Date.now();
            const ttl = (currentChartTimeframe === '1D') ? 60000 : 300000;

            // Instant cache render (0ms speed when switching between timeframes/portfolios)
            if (cached && !forceRefresh) {
                currentChartData = cached.data;
                currentPreparedChart = prepareMetricSeries(cached.data);
                renderChartDisplay(currentPreparedChart);
                drawPriceChart(currentPreparedChart);

                // Start prefetching remaining timeframes in background
                prefetchTimeframes();

                // If cache is fresh, avoid unnecessary network roundtrip
                if (now - cached.timestamp < ttl) {
                    return;
                }
            }

            // Cancel any pending in-flight request
            if (_chartAbortController) {
                try { _chartAbortController.abort(); } catch (e) {}
            }
            _chartAbortController = new AbortController();
            const currentSignal = _chartAbortController.signal;

            const loadingEl = document.getElementById('chart-loading');
            // Only show spinner if not already displaying cached data
            if (!cached && loadingEl) loadingEl.style.display = 'flex';

            let timeoutId = setTimeout(() => {
                try { _chartAbortController.abort(); } catch (e) {}
            }, 3500);

            try {
                const url = `/api/chart?symbol=${encodeURIComponent(currentChartSymbol)}&timeframe=${currentChartTimeframe}&currency=${currentCurrency}&portfolio=${encodeURIComponent(currentPortfolio)}`;
                const res = await fetch(url, { signal: currentSignal });
                clearTimeout(timeoutId);
                if (res.ok) {
                    const data = await res.json();
                    if (data && data.prices && data.prices.length >= 2) {
                        _chartClientCache.set(cacheKey, { data, timestamp: Date.now() });
                    }

                    const currentKey = `${currentChartSymbol}_${currentChartTimeframe}_${currentCurrency}_${currentPortfolio}`;
                    if (currentKey === cacheKey) {
                        currentChartData = data;
                        currentPreparedChart = prepareMetricSeries(data);
                        renderChartDisplay(currentPreparedChart);
                        drawPriceChart(currentPreparedChart);
                        prefetchTimeframes();
                    }
                }
            } catch (err) {
                clearTimeout(timeoutId);
                if (err.name !== 'AbortError') {
                    console.error('Failed to load chart data:', err);
                }
            } finally {
                if (loadingEl) loadingEl.style.display = 'none';
            }
        }

        function prepareMetricSeries(data) {
            if (!data) return null;
            const rawPrices = data.prices || [];
            const rawTimestamps = data.timestamps || [];
            const rawPrev = Number(data.prev_close || rawPrices[0] || 0);
            const totalCb = Number(data.total_cost_basis || 0);
            const totalShares = Number(data.total_shares || 0);
            const totalDiv = Number(data.total_annual_div || 0);
            const isSingleStock = (currentChartSymbol !== 'PORTFOLIO');
            const tf = currentChartTimeframe || '1M';
            const scaleFactor = (isSingleStock && totalShares > 0) ? totalShares : 1.0;
            const sym = (data && data.currency_symbol) ? data.currency_symbol : (currentPortfolioData ? (currentPortfolioData.currency_symbol || '$') : '$');
            const nPts = rawPrices.length;

            const tfMultMap = {
                '1D': 1.0 / 252.0,
                '5D': 5.0 / 252.0,
                '1M': 1.0 / 12.0,
                '6M': 0.5,
                'YTD': 0.5,
                '1Y': 1.0,
                '5Y': 5.0,
                'MAX': 5.0
            };
            const tfMult = tfMultMap[tf] || 1.0;

            let divSeries = [];
            let timeframeDiv = 0;
            if (data.dividend_events && data.dividend_events.length > 0 && isSingleStock && totalShares > 0 && rawTimestamps.length > 0) {
                const startStr = rawTimestamps[0];
                const tfDivEvents = data.dividend_events.filter(ev => ev[0] >= startStr);
                divSeries = rawTimestamps.map(ts => {
                    const cum = tfDivEvents.filter(ev => ev[0] <= ts).reduce((sum, ev) => sum + ev[1], 0);
                    return Math.round(cum * totalShares * 100) / 100;
                });
                timeframeDiv = divSeries[divSeries.length - 1] || 0;
                if (timeframeDiv === 0 && totalDiv > 0 && tf !== '1D' && tf !== '5D') {
                    timeframeDiv = Math.round(totalDiv * tfMult * 100) / 100;
                    divSeries = rawPrices.map((_, i) => Math.round(timeframeDiv * (i / Math.max(1, nPts - 1)) * 100) / 100);
                }
            } else {
                timeframeDiv = Math.round(totalDiv * tfMult * 100) / 100;
                divSeries = rawPrices.map((_, i) => Math.round(timeframeDiv * (i / Math.max(1, nPts - 1)) * 100) / 100);
            }

            const mode = currentChartMetric || 'total';
            let prices = [];
            let prevClose = 0.0;
            let currVal = 0.0;
            let change = 0.0;
            let changePct = 0.0;
            let isPos = true;
            let lineColor = '#0a84ff';
            let isGrowth = false;
            let refLabel = '';

            if (mode === 'growth') {
                if (totalCb > 0) {
                    prices = rawPrices.map(p => Math.round((p * scaleFactor - totalCb) * 100) / 100);
                    currVal = prices[prices.length - 1] || 0;
                    change = currVal;
                    changePct = (currVal / totalCb * 100);
                    refLabel = t('chart_invested_capital') + sym + totalCb.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                } else {
                    const base0 = rawPrices[0] || 0;
                    prices = rawPrices.map(p => Math.round((p - base0) * 100) / 100);
                    currVal = prices[prices.length - 1] || 0;
                    change = currVal;
                    changePct = base0 > 0 ? (currVal / base0 * 100) : 0;
                    refLabel = t('chart_invested_capital') + sym + base0.toFixed(2);
                }
                prevClose = 0.0;
                isPos = currVal >= 0;
                lineColor = isPos ? '#30d158' : '#ff453a';
                isGrowth = true;
            } else if (mode === 'growth_div') {
                if (totalCb > 0) {
                    prices = rawPrices.map((p, i) => Math.round(((p * scaleFactor - totalCb) + (divSeries[i] || 0)) * 100) / 100);
                    currVal = prices[prices.length - 1] || 0;
                    change = currVal;
                    changePct = (currVal / totalCb * 100);
                    refLabel = t('chart_invested_capital') + sym + totalCb.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                } else {
                    const base0 = rawPrices[0] || 0;
                    prices = rawPrices.map((p, i) => Math.round(((p - base0) + (divSeries[i] || 0)) * 100) / 100);
                    currVal = prices[prices.length - 1] || 0;
                    change = currVal;
                    changePct = base0 > 0 ? (currVal / base0 * 100) : 0;
                    refLabel = t('chart_invested_capital') + sym + base0.toFixed(2);
                }
                prevClose = 0.0;
                isPos = currVal >= 0;
                lineColor = isPos ? '#30d158' : '#ff453a';
                isGrowth = true;
            } else if (mode === 'div_only') {
                prices = divSeries.length > 0 ? divSeries : rawPrices.map(() => 0);
                prevClose = 0.0;
                currVal = prices[prices.length - 1] || 0;
                change = currVal;
                changePct = totalCb > 0 ? (currVal / totalCb * 100) : 0;
                isPos = true;
                lineColor = '#0a84ff';
                refLabel = t('chart_div_received') + sym + currVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                isGrowth = true;
            } else if (mode === 'price') {
                prices = rawPrices;
                prevClose = rawPrev;
                currVal = prices[prices.length - 1] || 0;
                change = currVal - prevClose;
                changePct = prevClose > 0 ? (change / prevClose * 100) : 0;
                isPos = change >= 0;
                lineColor = (currentChartSymbol === 'PORTFOLIO') ? '#0a84ff' : (isPos ? '#30d158' : '#ff453a');
                refLabel = t('ref_prev_close', { val: sym + prevClose.toFixed(2) });
                isGrowth = false;
            } else {
                // total
                if (isSingleStock && totalShares > 0) {
                    prices = rawPrices.map(p => Math.round(p * scaleFactor * 100) / 100);
                    prevClose = Math.round(rawPrev * scaleFactor * 100) / 100;
                } else {
                    prices = rawPrices;
                    prevClose = rawPrev;
                }
                currVal = prices[prices.length - 1] || 0;
                change = currVal - prevClose;
                changePct = prevClose > 0 ? (change / prevClose * 100) : 0;
                isPos = change >= 0;
                lineColor = (currentChartSymbol === 'PORTFOLIO') ? '#0a84ff' : (isPos ? '#30d158' : '#ff453a');
                refLabel = t('ref_prev_close', { val: sym + prevClose.toFixed(2) });
                isGrowth = false;
            }

            return {
                mode,
                style: currentChartStyle || 'area',
                prices,
                timestamps: rawTimestamps,
                currencySymbol: sym,
                currency: (data && data.currency) || (currentPortfolioData ? currentPortfolioData.currency : 'USD'),
                prevClose,
                currVal,
                change,
                changePct,
                isPos,
                lineColor,
                isGrowth,
                refLabel,
                totalCb,
                scaleFactor,
                timeframeDiv
            };
        }

        function renderChartDisplay(prepared) {
            if (!prepared) return;
            const sym = currentPortfolioData ? (currentPortfolioData.currency_symbol || '$') : '$';
            const priceEl = document.getElementById('chart-display-price');
            const chgEl = document.getElementById('chart-display-change');
            const refEl = document.getElementById('chart-ref-close');
            const timeEl = document.getElementById('chart-display-time');

            const val = prepared.currVal;
            const change = prepared.change;
            const pct = prepared.changePct;
            const isPos = prepared.isPos;

            if (priceEl) {
                if (prepared.mode === 'growth' || prepared.mode === 'growth_div') {
                    priceEl.textContent = `${val >= 0 ? '+' : '-'}${sym}${Math.abs(val).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    priceEl.style.color = isPos ? 'var(--accent-green)' : 'var(--accent-red)';
                } else if (prepared.mode === 'div_only') {
                    priceEl.textContent = `+${sym}${val.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    priceEl.style.color = 'var(--accent-blue)';
                } else {
                    priceEl.textContent = `${sym}${val.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    priceEl.style.color = '';
                }
            }

            if (chgEl) {
                if (prepared.mode === 'growth' || prepared.mode === 'growth_div') {
                    chgEl.textContent = `${isPos ? '+' : ''}${sym}${change.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${isPos ? '+' : ''}${pct.toFixed(2)}%)`;
                    chgEl.className = 'pill ' + (isPos ? 'pos' : 'neg');
                } else if (prepared.mode === 'div_only') {
                    chgEl.textContent = `+${sym}${val.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (Yield: ${pct.toFixed(2)}%)`;
                    chgEl.className = 'pill blue';
                } else {
                    chgEl.textContent = `${isPos ? '+' : ''}${sym}${change.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${isPos ? '+' : ''}${pct.toFixed(2)}%)`;
                    chgEl.className = 'pill ' + (isPos ? 'pos' : 'neg');
                }
            }

            if (timeEl) {
                const ts = (prepared.timestamps && prepared.timestamps.length > 0) ? prepared.timestamps[prepared.timestamps.length - 1] : '';
                timeEl.textContent = ts ? t('updated_at', { time: ts }) : t('realtime_trend');
            }

            if (refEl) {
                refEl.textContent = prepared.refLabel;
            }
        }

        function formatXAxisDate(rawTs, tf) {
            if (!rawTs) return '';
            const str = String(rawTs).trim();
            if (tf === '1D') {
                const m = str.match(/(\\d{1,2}:\\d{2})/);
                return m ? m[1] : str.slice(0, 5);
            }
            if (tf === '5D') {
                const mTime = str.match(/([A-Za-z]{3}\\s+\\d{1,2}:\\d{2})/);
                if (mTime) return mTime[1];
                const m = str.match(/(?:\\d{4}-)?(\\d{2})-(\\d{2})(?:\\s+(\\d{1,2}:\\d{2}))?/);
                if (m) return m[3] ? `${m[1]}/${m[2]} ${m[3]}` : `${m[1]}/${m[2]}`;
                return str;
            }
            if (tf === '1M' || tf === '6M' || tf === 'YTD') {
                const m = str.match(/(?:\\d{4}-)?(\\d{2})-(\\d{2})/);
                if (m) return `${m[1]}/${m[2]}`;
                return str;
            }
            if (tf === '1Y') {
                const m = str.match(/(\\d{4})-(\\d{2})/);
                if (m) return `${m[1].slice(2)}/${m[2]}`;
                return str;
            }
            const m = str.match(/^(\\d{4})/);
            if (m) return m[1];
            return str;
        }

        function formatYAxisNumber(val, isGrowth, sym, range) {
            const isPos = val >= 0;
            const absV = Math.abs(val);
            const prefix = isGrowth ? (isPos ? '+' : '-') : '';
            let numStr = '';
            if (absV >= 1000000) {
                numStr = `${(absV / 1000000).toFixed(1)}M`;
            } else if (absV >= 100000) {
                numStr = `${(absV / 1000).toFixed(0)}K`;
            } else if (absV >= 10000) {
                numStr = `${(absV / 1000).toFixed(1)}K`;
            } else {
                const dec = (range < 10 && absV < 1000) ? 2 : (absV < 10 ? 2 : 0);
                numStr = absV.toLocaleString(undefined, {minimumFractionDigits: dec, maximumFractionDigits: dec});
            }
            return `${prefix}${sym}${numStr}`;
        }

        function drawPriceChart(prepared, hoverIndex = -1) {
            const canvas = document.getElementById('price-chart-canvas');
            if (!canvas || !prepared) return;
            const prices = prepared.prices || [];
            if (prices.length < 2) return;

            const rect = canvas.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1;
            const w = rect.width || 340;
            const h = rect.height || 260;
            canvas.width = w * dpr;
            canvas.height = h * dpr;
            const ctx = canvas.getContext('2d');
            ctx.scale(dpr, dpr);
            ctx.clearRect(0, 0, w, h);

            const padLeft = 14;
            const padRight = 54;
            const padTop = 16;
            const padBottom = 26;
            const plotW = w - padLeft - padRight;
            const plotH = h - padTop - padBottom;

            const isLight = document.body.classList.contains('theme-light') || document.documentElement.classList.contains('theme-light');
            const axisTextColor = isLight ? '#6c6c70' : '#8e8e93';
            const gridLineColor = isLight ? 'rgba(0, 0, 0, 0.06)' : 'rgba(255, 255, 255, 0.07)';
            const tickLineColor = isLight ? 'rgba(0, 0, 0, 0.16)' : 'rgba(255, 255, 255, 0.22)';
            const sym = (prepared && prepared.currencySymbol) || (currentPortfolioData ? (currentPortfolioData.currency_symbol || '$') : '$');

            let minP = Math.min(...prices);
            let maxP = Math.max(...prices);
            const refVal = prepared.isGrowth ? 0.0 : prepared.prevClose;
            if (refVal !== undefined && refVal !== null) {
                minP = Math.min(minP, refVal);
                maxP = Math.max(maxP, refVal);
            }
            const rawSpan = (maxP - minP) || 1;
            minP -= rawSpan * 0.02;
            maxP += rawSpan * 0.02;
            const range = (maxP - minP) || 1;
            const mainColor = prepared.lineColor || '#0a84ff';
            const isArea = (prepared.style === 'area');

            // 1. Draw Y-Axis Grid Lines & Price Numbers
            const nYGrid = 4;
            for (let step = 0; step <= nYGrid; step++) {
                const frac = step / nYGrid;
                const yVal = maxP - frac * range;
                const yPos = padTop + frac * plotH;

                ctx.save();
                ctx.beginPath();
                ctx.strokeStyle = gridLineColor;
                ctx.lineWidth = 1;
                ctx.setLineDash([2, 4]);
                ctx.moveTo(padLeft, yPos);
                ctx.lineTo(padLeft + plotW, yPos);
                ctx.stroke();
                ctx.restore();

                const labelY = formatYAxisNumber(yVal, prepared.isGrowth, sym, range);
                ctx.save();
                ctx.font = '9px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
                ctx.fillStyle = axisTextColor;
                ctx.textAlign = 'left';
                ctx.textBaseline = 'middle';
                ctx.fillText(labelY, padLeft + plotW + 5, yPos);
                ctx.restore();
            }

            // 2. Reference baseline dotted horizontal line (prevClose or 0.0)
            if (refVal >= minP && refVal <= maxP) {
                const yRef = padTop + plotH - ((refVal - minP) / range) * plotH;
                ctx.save();
                ctx.beginPath();
                ctx.setLineDash([4, 4]);
                ctx.strokeStyle = isLight ? 'rgba(108, 108, 112, 0.5)' : 'rgba(142, 142, 147, 0.45)';
                ctx.lineWidth = 1;
                ctx.moveTo(padLeft, yRef);
                ctx.lineTo(padLeft + plotW, yRef);
                ctx.stroke();
                ctx.restore();
            }

            // 3. Compute curve points
            const pts = [];
            const n = prices.length;
            for (let i = 0; i < n; i++) {
                const x = padLeft + (i / (n - 1)) * plotW;
                const y = padTop + plotH - ((prices[i] - minP) / range) * plotH;
                pts.push({x, y});
            }

            // 4. Gradient Area Fill under Curve (if Area style is selected)
            if (isArea) {
                ctx.beginPath();
                ctx.moveTo(pts[0].x, pts[0].y);
                for (let i = 1; i < n; i++) {
                    const prev = pts[i - 1];
                    const cur = pts[i];
                    ctx.quadraticCurveTo(prev.x, prev.y, (prev.x + cur.x) / 2, (prev.y + cur.y) / 2);
                }
                ctx.lineTo(pts[n - 1].x, pts[n - 1].y);
                ctx.lineTo(padLeft + plotW, padTop + plotH);
                ctx.lineTo(padLeft, padTop + plotH);
                ctx.closePath();

                const grad = ctx.createLinearGradient(0, padTop, 0, padTop + plotH);
                if (prepared.mode === 'div_only') {
                    grad.addColorStop(0, 'rgba(10, 132, 255, 0.28)');
                } else if (prepared.isGrowth) {
                    grad.addColorStop(0, prepared.isPos ? 'rgba(48, 209, 88, 0.26)' : 'rgba(255, 69, 58, 0.26)');
                } else {
                    const isPortfolio = (currentChartSymbol === 'PORTFOLIO');
                    grad.addColorStop(0, isPortfolio ? 'rgba(10, 132, 255, 0.28)' : (prepared.isPos ? 'rgba(48, 209, 88, 0.26)' : 'rgba(255, 69, 58, 0.26)'));
                }
                grad.addColorStop(1, 'rgba(0, 0, 0, 0.0)');
                ctx.fillStyle = grad;
                ctx.fill();
            }

            // 5. Main Smoothed Stroke Line
            ctx.beginPath();
            ctx.moveTo(pts[0].x, pts[0].y);
            for (let i = 1; i < n; i++) {
                const prev = pts[i - 1];
                const cur = pts[i];
                ctx.quadraticCurveTo(prev.x, prev.y, (prev.x + cur.x) / 2, (prev.y + cur.y) / 2);
            }
            ctx.lineTo(pts[n - 1].x, pts[n - 1].y);
            ctx.strokeStyle = mainColor;
            ctx.lineWidth = 2.4;
            ctx.lineJoin = 'round';
            ctx.lineCap = 'round';
            ctx.stroke();

            // 6. Draw X-Axis Ticks & Date/Time Numbers
            const nXTicks = Math.min(5, n);
            if (nXTicks > 1 && prepared.timestamps && prepared.timestamps.length > 0) {
                for (let k = 0; k < nXTicks; k++) {
                    const idx = Math.round(k * (n - 1) / (nXTicks - 1));
                    const xPos = padLeft + (idx / (n - 1)) * plotW;
                    const rawTs = prepared.timestamps[idx] || '';
                    const labelX = formatXAxisDate(rawTs, currentChartTimeframe);

                    if (labelX) {
                        ctx.save();
                        ctx.beginPath();
                        ctx.strokeStyle = tickLineColor;
                        ctx.lineWidth = 1;
                        ctx.moveTo(xPos, padTop + plotH);
                        ctx.lineTo(xPos, padTop + plotH + 4);
                        ctx.stroke();

                        ctx.font = '9px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
                        ctx.fillStyle = axisTextColor;
                        if (k === 0) {
                            ctx.textAlign = 'left';
                        } else if (k === nXTicks - 1) {
                            ctx.textAlign = 'right';
                        } else {
                            ctx.textAlign = 'center';
                        }
                        ctx.textBaseline = 'top';
                        ctx.fillText(labelX, xPos, padTop + plotH + 6);
                        ctx.restore();
                    }
                }
            }

            // 7. Interactive Pointer Touch Inspection
            if (hoverIndex >= 0 && hoverIndex < n) {
                const hp = pts[hoverIndex];

                // Vertical Crosshair
                ctx.beginPath();
                ctx.strokeStyle = isLight ? 'rgba(0, 0, 0, 0.35)' : 'rgba(255, 255, 255, 0.4)';
                ctx.lineWidth = 1;
                ctx.setLineDash([3, 3]);
                ctx.moveTo(hp.x, padTop);
                ctx.lineTo(hp.x, padTop + plotH);
                ctx.stroke();
                ctx.setLineDash([]);

                // Outer halo & inner dot
                ctx.beginPath();
                ctx.arc(hp.x, hp.y, 6, 0, Math.PI * 2);
                ctx.fillStyle = isLight ? 'rgba(0, 0, 0, 0.15)' : 'rgba(255, 255, 255, 0.35)';
                ctx.fill();
                ctx.beginPath();
                ctx.arc(hp.x, hp.y, 3.5, 0, Math.PI * 2);
                ctx.fillStyle = isLight ? '#007aff' : '#ffffff';
                ctx.fill();

                // Dynamically update inspection header
                const hVal = prices[hoverIndex];
                const priceEl = document.getElementById('chart-display-price');
                const chgEl = document.getElementById('chart-display-change');
                const timeEl = document.getElementById('chart-display-time');

                if (prepared.isGrowth) {
                    const hPos = hVal >= 0;
                    const hPct = prepared.totalCb > 0 ? (hVal / prepared.totalCb * 100) : 0;
                    if (priceEl) {
                        priceEl.textContent = `${hPos ? '+' : '-'}${sym}${Math.abs(hVal).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                        priceEl.style.color = hPos ? 'var(--accent-green)' : 'var(--accent-red)';
                    }
                    if (chgEl) {
                        chgEl.textContent = `${hPos ? '+' : ''}${sym}${hVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${hPos ? '+' : ''}${hPct.toFixed(2)}%)`;
                        chgEl.className = 'pill ' + (hPos ? 'pos' : 'neg');
                    }
                } else {
                    const refBase = prepared.prevClose || prices[0];
                    const hDiff = hVal - refBase;
                    const hPct = refBase > 0 ? (hDiff / refBase * 100) : 0;
                    const hPos = hDiff >= 0;
                    if (priceEl) {
                        priceEl.textContent = `${sym}${hVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                        priceEl.style.color = '';
                    }
                    if (chgEl) {
                        chgEl.textContent = `${hPos ? '+' : ''}${sym}${hDiff.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${hPos ? '+' : ''}${hPct.toFixed(2)}%)`;
                        chgEl.className = 'pill ' + (hPos ? 'pos' : 'neg');
                    }
                }

                if (timeEl && prepared.timestamps && prepared.timestamps[hoverIndex]) {
                    timeEl.textContent = prepared.timestamps[hoverIndex];
                }
            }
        }

        function initChartCanvasEvents() {
            const canvas = document.getElementById('price-chart-canvas');
            if (!canvas) return;

            const handlePointer = (evt) => {
                if (!currentPreparedChart || !currentPreparedChart.prices || currentPreparedChart.prices.length < 2) return;
                const rect = canvas.getBoundingClientRect();
                const clientX = evt.touches ? evt.touches[0].clientX : evt.clientX;
                const x = clientX - rect.left;
                const padLeft = 14, padRight = 54;
                const plotW = (rect.width || 340) - padLeft - padRight;
                const frac = Math.max(0, Math.min(1, (x - padLeft) / plotW));
                const idx = Math.round(frac * (currentPreparedChart.prices.length - 1));
                drawPriceChart(currentPreparedChart, idx);
            };

            const resetPointer = () => {
                if (currentPreparedChart) {
                    drawPriceChart(currentPreparedChart, -1);
                    renderChartDisplay(currentPreparedChart);
                }
            };

            canvas.addEventListener('mousemove', handlePointer);
            canvas.addEventListener('mouseleave', resetPointer);
            canvas.addEventListener('touchmove', handlePointer, { passive: true });
            canvas.addEventListener('touchend', resetPointer);
        }

        function drawDonutChart(holdings) {
            const canvas = document.getElementById('donut-chart-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const w = 220, h = 220;
            ctx.clearRect(0, 0, w, h);

            const totalVal = currentPortfolioData ? Number(currentPortfolioData.total_value || 0) : 0;
            const sym = currentPortfolioData ? (currentPortfolioData.currency_symbol || '$') : '$';
            const centerVal = document.getElementById('donut-center-val');
            if (centerVal) centerVal.textContent = sym + Math.round(totalVal).toLocaleString();

            const legendEl = document.getElementById('donut-legend-container');
            if (legendEl) legendEl.innerHTML = '';

            if (!holdings || holdings.length === 0 || totalVal <= 0) return;

            const sorted = [...holdings].sort((a,b) => (Number(b.market_value||0) - Number(a.market_value||0)));
            const topHoldings = sorted.slice(0, 7);
            const otherVal = sorted.slice(7).reduce((acc, h) => acc + Number(h.market_value||0), 0);
            if (otherVal > 0) {
                topHoldings.push({ symbol: t('other_assets'), market_value: otherVal, name: '' });
            }

            const colors = ['#0a84ff', '#30d158', '#ffd60a', '#ff9f0a', '#bf5af2', '#64d2ff', '#ff375f', '#ac8e68', '#5e5ce6'];
            const cx = w / 2, cy = h / 2, outerR = 92, innerR = 60;
            let startAngle = -Math.PI / 2;

            const countBadge = document.getElementById('chart-donut-count');
            if (countBadge) countBadge.textContent = `${holdings.length} ${t('holdings_unit')}`;

            topHoldings.forEach((h, i) => {
                const val = Number(h.market_value || 0);
                const sliceAngle = (val / totalVal) * (2 * Math.PI);
                const col = colors[i % colors.length];

                ctx.beginPath();
                ctx.arc(cx, cy, outerR, startAngle, startAngle + sliceAngle);
                ctx.arc(cx, cy, innerR, startAngle + sliceAngle, startAngle, true);
                ctx.closePath();
                ctx.fillStyle = col;
                ctx.fill();

                startAngle += sliceAngle;

                if (legendEl) {
                    const pct = ((val / totalVal) * 100).toFixed(1);
                    const item = document.createElement('div');
                    item.className = 'legend-item';
                    item.innerHTML = `
                        <div class="legend-color-dot" style="background: ${col};"></div>
                        <div style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            <strong>${h.symbol}</strong>
                            <div style="font-size: 0.68rem; color: var(--text-muted);">${pct}% &bull; ${sym}${Math.round(val).toLocaleString()}</div>
                        </div>
                    `;
                    item.onclick = () => viewSymbolInChart(h.symbol);
                    legendEl.appendChild(item);
                }
            });
        }

        function populateChartSymbols(holdings, watchlist) {
            const sel = document.getElementById('chart-symbol-select');
            if (!sel) return;
            const curVal = currentChartSymbol || sel.value;
            sel.innerHTML = `<option value="PORTFOLIO">${t('total_portfolio')}</option>`;

            const seen = new Set();
            const optGroupH = document.createElement('optgroup');
            optGroupH.label = t('holdings_group');
            (holdings || []).forEach(h => {
                if (h.symbol && !seen.has(h.symbol)) {
                    seen.add(h.symbol);
                    const opt = document.createElement('option');
                    opt.value = h.symbol;
                    opt.textContent = `${h.symbol} - ${h.name || ''}`;
                    optGroupH.appendChild(opt);
                }
            });
            if (optGroupH.children.length > 0) sel.appendChild(optGroupH);

            const optGroupW = document.createElement('optgroup');
            optGroupW.label = t('watchlist_group');
            (watchlist || []).forEach(w => {
                if (w.symbol && !seen.has(w.symbol)) {
                    seen.add(w.symbol);
                    const opt = document.createElement('option');
                    opt.value = w.symbol;
                    opt.textContent = `${w.symbol} - ${w.name || ''}`;
                    optGroupW.appendChild(opt);
                }
            });
            if (optGroupW.children.length > 0) sel.appendChild(optGroupW);

            // Verify if targetVal exists in newly populated options; fallback gracefully
            let targetVal = curVal || 'PORTFOLIO';
            let exists = Array.from(sel.options).some(o => o.value === targetVal);
            if (!exists) {
                targetVal = 'PORTFOLIO';
                currentChartSymbol = 'PORTFOLIO';
            }
            sel.value = targetVal;
        }

        function viewSymbolInChart(sym) {
            currentChartSymbol = sym || 'PORTFOLIO';
            const sel = document.getElementById('chart-symbol-select');
            if (sel) {
                let exists = Array.from(sel.options).some(o => o.value === currentChartSymbol);
                if (!exists && currentChartSymbol !== 'PORTFOLIO') {
                    const opt = document.createElement('option');
                    opt.value = currentChartSymbol;
                    opt.textContent = currentChartSymbol;
                    sel.appendChild(opt);
                }
                sel.value = currentChartSymbol;
            }
            switchTab('chart');
        }

        function viewCurrentHoldingInChart() {
            closeModal('modal-holding-detail');
            if (currentSelectedHoldingSymbol) viewSymbolInChart(currentSelectedHoldingSymbol);
        }

        function viewCurrentWatchlistInChart() {
            closeModal('modal-watchlist-detail');
            if (currentSelectedWatchlistSymbol) viewSymbolInChart(currentSelectedWatchlistSymbol);
        }

        // =============================================================
        // FINANCIAL TOOLS & SIMULATORS (TAB 5)
        // =============================================================
        function switchToolSubTab(subId) {
            document.querySelectorAll('.tool-tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tool-subpane').forEach(p => p.classList.remove('active'));

            const btn = document.getElementById('btn-st-' + subId);
            if (btn) btn.classList.add('active');
            const pane = document.getElementById('subpane-' + subId);
            if (pane) pane.classList.add('active');

            if (subId === 'rebalance') runRebalanceCalc();
            else if (subId === 'drip') runDripCalc();
            else if (subId === 'whatif') runWhatIfCalc();
            else if (subId === 'split') runSplitCalc();
            else if (subId === 'selling') runSellCalc();
            else if (subId === 'cloud') fetchGoogleSheetStatus();
        }

        function populateToolsDropdowns(holdings) {
            // 1. Populate What-If Select
            const whatIfSel = document.getElementById('whatif-select');
            if (whatIfSel) {
                const curVal = whatIfSel.value;
                whatIfSel.innerHTML = `<option value="">-- ${t('whatif_custom_ticker')} --</option>`;
                holdings.forEach(h => {
                    const opt = document.createElement('option');
                    opt.value = h.symbol;
                    opt.textContent = `${h.symbol} - ${h.name || ''} (${h.shares} ${t('shs_unit')} @ $${Number(h.current_price || 0).toFixed(2)})`;
                    whatIfSel.appendChild(opt);
                });
                if (curVal) whatIfSel.value = curVal;
            }

            // 2. Populate Split Select
            const splitSel = document.getElementById('split-select');
            if (splitSel) {
                const curVal = splitSel.value;
                splitSel.innerHTML = `<option value="">-- ${t('split_manual')} --</option>`;
                holdings.forEach(h => {
                    const opt = document.createElement('option');
                    opt.value = h.symbol;
                    opt.textContent = `${h.symbol} (${h.shares} ${t('shs_unit')} @ $${Number(h.current_price || 0).toFixed(2)})`;
                    splitSel.appendChild(opt);
                });
                if (curVal) splitSel.value = curVal;
            }

            // 3. Populate Sell Select
            const sellSel = document.getElementById('sell-select');
            if (sellSel) {
                const curVal = sellSel.value;
                sellSel.innerHTML = `<option value="">-- ${t('split_manual')} --</option>`;
                holdings.forEach(h => {
                    const opt = document.createElement('option');
                    opt.value = h.symbol;
                    opt.textContent = `${h.symbol} (${h.shares} ${t('shs_unit')} @ $${Number(h.current_price || 0).toFixed(2)})`;
                    sellSel.appendChild(opt);
                });
                if (curVal) sellSel.value = curVal;
            }

            // 4. Populate Rebalance Holdings List
            const rebalContainer = document.getElementById('rebalance-holdings-list');
            if (rebalContainer) {
                rebalContainer.innerHTML = '';
                const totalVal = currentPortfolioData ? Number(currentPortfolioData.total_value || 0) : 0;
                const sym = currentPortfolioData ? (currentPortfolioData.currency_symbol || '$') : '$';

                holdings.forEach((h) => {
                    const curWeight = totalVal > 0 ? ((Number(h.market_value || 0) / totalVal) * 100).toFixed(1) : '0.0';
                    const div = document.createElement('div');
                    div.className = 'item-card';
                    div.style.marginBottom = '8px';
                    div.id = `rebal-item-${h.symbol}`;
                    div.innerHTML = `
                        <div class="item-left" style="flex: 1;">
                            <strong>${h.symbol}</strong>
                            <div style="font-size: 0.72rem; color: var(--text-muted);">${t('rebal_cur_val', { val: sym + Number(h.market_value || 0).toLocaleString(undefined, {maximumFractionDigits: 0}), pct: curWeight })}</div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <label style="font-size: 0.75rem; color: var(--text-muted);">${t('rebal_target_pct')}</label>
                            <input type="number" step="0.5" class="form-control rebal-tgt-input" 
                                style="width: 72px; padding: 6px 8px; font-size: 0.84rem; text-align: right;" 
                                data-symbol="${h.symbol}" 
                                data-price="${h.current_price}" 
                                data-curval="${h.market_value}"
                                value="${curWeight}" 
                                oninput="runRebalanceCalc()">
                            <span class="pill item-badge blue" id="rebal-badge-${h.symbol}">${t('rebal_hold')}</span>
                        </div>
                    `;
                    rebalContainer.appendChild(div);
                });
            }
        }

        // --- 1. WHAT-IF CALC ---
        function onWhatIfHoldingSelected(sym) {
            if (!sym || !currentPortfolioData || !currentPortfolioData.holdings) return;
            const h = currentPortfolioData.holdings.find(x => x.symbol === sym);
            if (h) {
                document.getElementById('whatif-ticker').value = h.symbol;
                document.getElementById('whatif-price').value = Number(h.current_price || 100).toFixed(2);
                const yld = Number(h.dividend_yield || (h.current_price > 0 ? (h.annual_dividend / (h.shares * h.current_price) * 100) : 0));
                document.getElementById('whatif-yield').value = yld.toFixed(2);
                runWhatIfCalc();
            }
        }

        function addWhatIfAmt(amt) {
            const el = document.getElementById('whatif-amt');
            el.value = (parseFloat(el.value) || 0) + amt;
            runWhatIfCalc();
        }

        function setWhatIfAmt(amt) {
            document.getElementById('whatif-amt').value = amt;
            runWhatIfCalc();
        }

        function runWhatIfCalc() {
            const sym = currentPortfolioData ? (currentPortfolioData.currency_symbol || '$') : '$';
            const price = parseFloat(document.getElementById('whatif-price').value) || 0;
            const yld = parseFloat(document.getElementById('whatif-yield').value) || 0;
            const amt = parseFloat(document.getElementById('whatif-amt').value) || 0;
            const curTot = currentPortfolioData ? Number(currentPortfolioData.total_value || 0) : 0;
            const newTot = curTot + amt;

            const shares = price > 0 ? (amt / price) : 0;
            const addDiv = amt * (yld / 100.0);

            // Allocation shift
            const ticker = (document.getElementById('whatif-ticker').value || '').trim().toUpperCase();
            let curTickerVal = 0;
            if (currentPortfolioData && currentPortfolioData.holdings) {
                const found = currentPortfolioData.holdings.find(h => h.symbol.toUpperCase() === ticker);
                if (found) curTickerVal = Number(found.market_value || 0);
            }
            const curWeight = curTot > 0 ? (curTickerVal / curTot * 100) : 0;
            const newWeight = newTot > 0 ? ((curTickerVal + amt) / newTot * 100) : 0;

            document.getElementById('whatif-res-total').textContent = `${sym}${curTot.toLocaleString(undefined, {maximumFractionDigits: 0})} → ${sym}${newTot.toLocaleString(undefined, {maximumFractionDigits: 0})} (+${sym}${amt.toLocaleString(undefined, {maximumFractionDigits: 0})})`;
            document.getElementById('whatif-res-shares').textContent = `${shares.toFixed(2)} ${t('shs_unit')} @ ${sym}${price.toFixed(2)}`;
            document.getElementById('whatif-res-alloc').textContent = `${curWeight.toFixed(1)}% → ${newWeight.toFixed(1)}%`;
            document.getElementById('whatif-res-div').textContent = `+${sym}${addDiv.toFixed(2)}/yr (+${sym}${(addDiv/12).toFixed(2)}/mo)`;
        }

        // --- 2. REBALANCE CALC ---
        function applyRebalancePreset(preset) {
            const inputs = document.querySelectorAll('.rebal-tgt-input');
            if (!inputs.length) return;
            if (preset === 'equal') {
                const eq = (100.0 / inputs.length).toFixed(1);
                inputs.forEach(inp => inp.value = eq);
            } else if (preset === 'reset') {
                const totalVal = currentPortfolioData ? Number(currentPortfolioData.total_value || 0) : 0;
                inputs.forEach(inp => {
                    const cv = parseFloat(inp.dataset.curval) || 0;
                    inp.value = totalVal > 0 ? (cv / totalVal * 100).toFixed(1) : 0;
                });
            }
            runRebalanceCalc();
        }

        function runRebalanceCalc() {
            const sym = currentPortfolioData ? (currentPortfolioData.currency_symbol || '$') : '$';
            const extraCash = parseFloat(document.getElementById('rebal-cash').value) || 0;
            const curTotal = currentPortfolioData ? Number(currentPortfolioData.total_value || 0) : 0;
            const newTotal = curTotal + extraCash;

            let sumW = 0;
            const inputs = document.querySelectorAll('.rebal-tgt-input');
            inputs.forEach(inp => {
                const w = parseFloat(inp.value) || 0;
                sumW += w;
                const ticker = inp.dataset.symbol;
                const price = parseFloat(inp.dataset.price) || 1;
                const curVal = parseFloat(inp.dataset.curval) || 0;

                const tgtVal = newTotal * (w / 100.0);
                const diff = tgtVal - curVal;
                const sharesDiff = price > 0 ? (diff / price) : 0;
                const badge = document.getElementById(`rebal-badge-${ticker}`);

                if (badge) {
                    if (Math.abs(diff) < 20) {
                        badge.textContent = t('rebal_hold');
                        badge.className = 'pill item-badge blue';
                    } else if (diff > 0) {
                        badge.textContent = t('rebal_buy', { diff: sym + diff.toFixed(0), shs: sharesDiff.toFixed(1) });
                        badge.className = 'pill item-badge pos';
                    } else {
                        badge.textContent = t('rebal_sell', { diff: sym + Math.abs(diff).toFixed(0), shs: Math.abs(sharesDiff).toFixed(1) });
                        badge.className = 'pill item-badge neg';
                    }
                }
            });

            const totalEl = document.getElementById('rebal-total-weight');
            if (totalEl) {
                totalEl.textContent = `${sumW.toFixed(1)}% ` + (Math.abs(sumW - 100) < 0.2 ? t('rebal_ok') : t('rebal_warn'));
                totalEl.style.color = (Math.abs(sumW - 100) < 0.2) ? 'var(--accent-green)' : 'var(--accent-yellow)';
            }
            document.getElementById('rebal-total-val').textContent = `${sym}${newTotal.toLocaleString(undefined, {maximumFractionDigits: 0})}`;
        }

        // --- 3. DRIP CALC ---
        function runDripCalc() {
            const sym = currentPortfolioData ? (currentPortfolioData.currency_symbol || '$') : '$';
            const initDiv = parseFloat(document.getElementById('drip-init-div').value) || 0;
            const divG = (parseFloat(document.getElementById('drip-div-growth').value) || 5.0) / 100.0;
            const capR = (parseFloat(document.getElementById('drip-return').value) || 7.0) / 100.0;
            const extra = parseFloat(document.getElementById('drip-extra').value) || 0;

            const tbody = document.getElementById('drip-tbody');
            if (tbody) {
                tbody.innerHTML = '';
                const years = [1, 3, 5, 10, 15, 20, 25, 30];
                let accWealth = 0;
                let curDiv = initDiv;

                for (let y of years) {
                    curDiv = initDiv * Math.pow(1 + divG, y);
                    accWealth = 0;
                    for (let i = 1; i <= y; i++) {
                        const divI = initDiv * Math.pow(1 + divG, i);
                        accWealth = (accWealth + divI + extra) * (1 + capR);
                    }
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>${y} yr</strong></td>
                        <td style="color: var(--accent-green); font-weight: 700;">${sym}${curDiv.toLocaleString(undefined, {maximumFractionDigits: 0})} / yr</td>
                        <td>${sym}${(curDiv/12).toLocaleString(undefined, {maximumFractionDigits: 0})} / mo</td>
                        <td style="font-weight: 700;">${sym}${accWealth.toLocaleString(undefined, {maximumFractionDigits: 0})}</td>
                    `;
                    tbody.appendChild(tr);
                }
            }
        }

        // --- 4. STOCK SPLIT CALC ---
        function onSplitHoldingSelected(sym) {
            if (!sym || !currentPortfolioData || !currentPortfolioData.holdings) return;
            const h = currentPortfolioData.holdings.find(x => x.symbol === sym);
            if (h) {
                document.getElementById('split-shares').value = h.shares || 10;
                document.getElementById('split-cost').value = (h.shares > 0 ? (h.cost_basis / h.shares) : 100).toFixed(2);
                runSplitCalc();
            }
        }

        function setSplitRatio(n, d) {
            document.getElementById('split-num').value = n;
            document.getElementById('split-den').value = d;
            runSplitCalc();
        }

        function runSplitCalc() {
            const sym = currentPortfolioData ? (currentPortfolioData.currency_symbol || '$') : '$';
            const shs = parseFloat(document.getElementById('split-shares').value) || 0;
            const cost = parseFloat(document.getElementById('split-cost').value) || 0;
            const n = parseFloat(document.getElementById('split-num').value) || 1;
            const d = parseFloat(document.getElementById('split-den').value) || 1;

            const ratio = (d > 0) ? (n / d) : 1;
            const newShs = shs * ratio;
            const newCost = (ratio > 0) ? (cost / ratio) : cost;
            const tot = shs * cost;

            document.getElementById('split-res-shares').textContent = `${newShs.toFixed(4)} ${t('shs_unit')}`;
            document.getElementById('split-res-cost').textContent = `${sym}${newCost.toFixed(2)} / ${t('shs_unit')}`;
            document.getElementById('split-res-total').textContent = `${sym}${tot.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} ${t('split_unchanged')}`;
        }

        // --- 5. SELLING CALC ---
        function onSellHoldingSelected(sym) {
            if (!sym || !currentPortfolioData || !currentPortfolioData.holdings) return;
            const h = currentPortfolioData.holdings.find(x => x.symbol === sym);
            if (h) {
                document.getElementById('sell-tot-shares').value = h.shares || 10;
                document.getElementById('sell-cost-price').value = (h.shares > 0 ? (h.cost_basis / h.shares) : 100).toFixed(2);
                document.getElementById('sell-price').value = Number(h.current_price || 100).toFixed(2);
                document.getElementById('sell-qty').value = (h.shares * 0.5).toFixed(2);
                runSellCalc();
            }
        }

        function setSellPct(pct) {
            const tot = parseFloat(document.getElementById('sell-tot-shares').value) || 0;
            document.getElementById('sell-qty').value = (tot * pct).toFixed(2);
            runSellCalc();
        }

        function runSellCalc() {
            const sym = currentPortfolioData ? (currentPortfolioData.currency_symbol || '$') : '$';
            const totShs = parseFloat(document.getElementById('sell-tot-shares').value) || 0;
            const costP = parseFloat(document.getElementById('sell-cost-price').value) || 0;
            const qty = parseFloat(document.getElementById('sell-qty').value) || 0;
            const sellP = parseFloat(document.getElementById('sell-price').value) || 0;

            const proceeds = qty * sellP;
            const costSold = qty * costP;
            const gain = proceeds - costSold;
            const gainPct = costSold > 0 ? (gain / costSold * 100) : 0;
            const remShs = Math.max(0, totShs - qty);
            const remVal = remShs * sellP;

            document.getElementById('sell-res-proceeds').textContent = `${sym}${proceeds.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
            const gainEl = document.getElementById('sell-res-gain');
            gainEl.textContent = `${gain >= 0 ? '+' : ''}${sym}${gain.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${gainPct.toFixed(1)}%)`;
            gainEl.style.color = gain >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
            document.getElementById('sell-res-rem-shares').textContent = `${remShs.toFixed(2)} ${t('shs_unit')}`;
            document.getElementById('sell-res-rem-val').textContent = `${sym}${remVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        }

        // --- 6. HEALTH CHECK & REPAIR ---
        async function scanDataHealth() {
            const sumEl = document.getElementById('health-summary');
            const detEl = document.getElementById('health-details');
            sumEl.textContent = t('health_scanning');
            detEl.textContent = '';
            try {
                const res = await fetch('/api/health');
                const data = await res.json();
                if (data.healthy || (data.total_issues === 0)) {
                    sumEl.textContent = t('health_ok_sum');
                    sumEl.style.color = 'var(--accent-green)';
                    detEl.textContent = t('health_ok_det');
                } else {
                    const issueCount = data.total_issues || (data.issues || []).length;
                    sumEl.textContent = t('health_issue_sum', { count: issueCount });
                    sumEl.style.color = 'var(--accent-yellow)';
                    let msg = '';
                    (data.issues || []).forEach((iss, i) => {
                        msg += `${i+1}. [${iss.type || 'ISSUE'}] ${iss.desc || ''}\n`;
                    });
                    detEl.textContent = msg || t('health_init_det');
                }
            } catch (err) {
                sumEl.textContent = '❌ ' + t('err_network', { msg: err.message });
                sumEl.style.color = 'var(--accent-red)';
            }
        }

        async function repairDataHealth() {
            const sumEl = document.getElementById('health-summary');
            const detEl = document.getElementById('health-details');
            sumEl.textContent = t('health_repairing');
            try {
                const res = await fetch('/api/repair', { method: 'POST' });
                const data = await res.json();
                sumEl.textContent = t('health_repaired_sum');
                sumEl.style.color = 'var(--accent-green)';
                detEl.textContent = t('health_repaired_det');
                loadData();
                setTimeout(scanDataHealth, 800);
            } catch (err) {
                sumEl.textContent = '❌ ' + t('err_network', { msg: err.message });
                sumEl.style.color = 'var(--accent-red)';
            }
        }

        // --- 7. REPORTS ---
        function openReportInView() {
            const wrap = document.getElementById('report-preview-wrap');
            const iframe = document.getElementById('report-iframe');
            if (wrap.style.display === 'block') {
                wrap.style.display = 'none';
            } else {
                wrap.style.display = 'block';
                iframe.src = `/api/report?currency=${currentCurrency}&lang=${currentLang}`;
            }
        }

        // --- 8. STOP SERVER ---
        async function stopServerRemote() {
            if (confirm(t('confirm_stop_server'))) {
                try {
                    await fetch('/api/stop', { method: 'POST' });
                    alert(t('alert_server_stopping'));
                } catch (e) {
                    alert(t('alert_stop_sent'));
                }
            }
        }

        // --- 9. MODALS & ACTION SHEETS ---
        function closeModal(modalId) {
            const m = document.getElementById(modalId);
            if (m) m.classList.remove('active');
        }

        function openHoldingDetailModal(sym, port) {
            if (!currentPortfolioData || !currentPortfolioData.holdings) return;
            const h = currentPortfolioData.holdings.find(x => x.symbol === sym && (!port || (x.portfolio || x.portfolio_name || '') === port)) || currentPortfolioData.holdings.find(x => x.symbol === sym);
            if (!h) return;
            currentSelectedHoldingSymbol = h.symbol;
            currentSelectedHoldingPortfolio = h.portfolio || h.portfolio_name || '';

            const nativeSym = h.currency_symbol || '$';
            const baseSym = currentPortfolioData.currency_symbol || '$';
            const isDiff = h.currency && currentPortfolioData.currency && (h.currency !== currentPortfolioData.currency);

            const portSuffix = h.portfolio ? ` (${h.portfolio})` : '';
            document.getElementById('m-h-title').textContent = `${h.symbol} - ${h.name || ''}${portSuffix}`;

            const currEl = document.getElementById('m-h-curr');
            if (currEl) currEl.textContent = `${h.currency || 'USD'} (${nativeSym})`;

            document.getElementById('m-h-shares').textContent = `${h.shares} ${t('shs_unit')}`;

            const bp = Number(h.buy_price || (h.shares > 0 ? (Number(h.cost_basis || 0) / h.shares) : 0));
            const cp = Number(h.current_price || 0);
            const cb = Number(h.cost_basis || (h.shares * bp));
            const mv = Number(h.market_value || (h.shares * cp));
            const pl = Number(h.unrealized_pl || (mv - cb));
            const plPct = Number(h.roi_pct || (cb > 0 ? (pl / cb * 100) : 0));
            const div = Number(h.annual_dividend || 0);

            // Native values with converted equivalents when currencies differ
            const convBp = isDiff ? ` <span style="font-size:0.75rem; color:var(--text-muted); font-weight:normal;">(≈ ${baseSym}${Number(h.converted_buy_price || 0).toFixed(2)})</span>` : '';
            document.getElementById('m-h-cost').innerHTML = `${nativeSym}${bp.toFixed(2)}${convBp}`;

            const convCp = isDiff ? ` <span style="font-size:0.75rem; color:var(--text-muted); font-weight:normal;">(≈ ${baseSym}${Number(h.converted_current_price || 0).toFixed(2)})</span>` : '';
            document.getElementById('m-h-price').innerHTML = `${nativeSym}${cp.toFixed(2)}${convCp}`;

            const convCb = isDiff ? ` <span style="font-size:0.75rem; color:var(--text-muted); font-weight:normal;">(≈ ${baseSym}${Number(h.converted_cost_basis || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})})</span>` : '';
            const totCostEl = document.getElementById('m-h-tot-cost');
            if (totCostEl) totCostEl.innerHTML = `${nativeSym}${cb.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}${convCb}`;

            const convMv = isDiff ? `<div style="font-size:0.72rem; color:var(--text-muted); text-align:right;">≈ ${baseSym}${Number(h.converted_market_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} ${currentPortfolioData.currency}</div>` : '';
            document.getElementById('m-h-val').innerHTML = `${nativeSym}${mv.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}${convMv}`;

            const convPl = isDiff ? ` <span style="font-size:0.72rem; color:var(--text-muted); font-weight:normal;">(≈ ${pl >= 0 ? '+' : ''}${baseSym}${Number(h.converted_unrealized_pl || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})})</span>` : '';
            const plEl = document.getElementById('m-h-pl');
            plEl.innerHTML = `${pl >= 0 ? '+' : ''}${nativeSym}${pl.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${plPct.toFixed(2)}%)${convPl}`;
            plEl.style.color = pl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

            const convDiv = isDiff ? ` <span style="font-size:0.72rem; color:var(--text-muted); font-weight:normal;">(≈ ${baseSym}${Number(h.converted_annual_dividend || 0).toFixed(2)}/yr)</span>` : '';
            document.getElementById('m-h-div').innerHTML = `${nativeSym}${div.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}/yr${convDiv}`;

            // Action Buttons
            document.getElementById('btn-h-whatif').onclick = () => {
                closeModal('modal-holding-detail');
                switchTab('tools');
                switchToolSubTab('whatif');
                const sel = document.getElementById('whatif-select');
                if (sel) { sel.value = h.symbol; onWhatIfHoldingSelected(h.symbol); }
            };

            document.getElementById('btn-h-split').onclick = () => {
                closeModal('modal-holding-detail');
                switchTab('tools');
                switchToolSubTab('split');
                const sel = document.getElementById('split-select');
                if (sel) { sel.value = h.symbol; onSplitHoldingSelected(h.symbol); }
            };

            document.getElementById('btn-h-sell').onclick = () => {
                closeModal('modal-holding-detail');
                switchTab('tools');
                switchToolSubTab('selling');
                const sel = document.getElementById('sell-select');
                if (sel) { sel.value = h.symbol; onSellHoldingSelected(h.symbol); }
            };

            document.getElementById('btn-h-delete').onclick = () => {
                deleteHolding(h.symbol);
            };

            const m = document.getElementById('modal-holding-detail');
            if (m) m.classList.add('active');
        }

        function openWatchlistDetailModal(sym) {
            const w = _lastWatchlistItems.find(x => x.symbol === sym);
            if (!w) return;
            currentSelectedWatchlistSymbol = w.symbol;

            document.getElementById('m-w-title').textContent = `${w.symbol} - ${w.name || ''}`;
            const curP = Number(w.current_price || 0);
            const tgtP = Number(w.target_price || 0);
            document.getElementById('m-w-curp').textContent = curP > 0 ? `$${curP.toFixed(2)}` : t('w_not_fetched');
            document.getElementById('m-w-tgtp').textContent = tgtP > 0 ? `$${tgtP.toFixed(2)}` : t('w_not_set');

            const diffEl = document.getElementById('m-w-diff');
            if (tgtP > 0 && curP > 0) {
                const diff = curP - tgtP;
                const diffPct = (diff / tgtP * 100);
                if (curP <= tgtP) {
                    diffEl.textContent = t('w_target_hit_desc', { diff: Math.abs(diff).toFixed(2) });
                    diffEl.style.color = 'var(--accent-green)';
                } else {
                    diffEl.textContent = t('w_above_target_desc', { diff: diff.toFixed(2), pct: diffPct.toFixed(1) });
                    diffEl.style.color = 'var(--accent-yellow)';
                }
            } else {
                diffEl.textContent = '-';
                diffEl.style.color = 'var(--text-main)';
            }
            document.getElementById('m-w-notes').textContent = w.notes || w.tags || t('w_no_notes');

            document.getElementById('btn-w-whatif').onclick = () => {
                closeModal('modal-watchlist-detail');
                switchTab('tools');
                switchToolSubTab('whatif');
                document.getElementById('whatif-ticker').value = w.symbol;
                if (curP > 0) document.getElementById('whatif-price').value = curP.toFixed(2);
                runWhatIfCalc();
            };

            document.getElementById('btn-w-delete').onclick = () => {
                deleteWatchlistItem(w.symbol);
            };

            const m = document.getElementById('modal-watchlist-detail');
            if (m) m.classList.add('active');
        }

        function openAddHoldingModal() {
            document.getElementById('add-h-sym').value = '';
            document.getElementById('add-h-name').value = '';
            document.getElementById('add-h-shares').value = '';
            document.getElementById('add-h-price').value = '';
            document.getElementById('add-h-curr').value = currentCurrency || 'USD';
            let defPort = (currentPortfolio && currentPortfolio !== 'All') ? currentPortfolio : '';
            if (!defPort && currentPortfolioData && currentPortfolioData.portfolios && currentPortfolioData.portfolios.length > 0) {
                defPort = currentPortfolioData.portfolios[0];
            }
            document.getElementById('add-h-port').value = defPort || 'USD HSBC';
            const m = document.getElementById('modal-add-holding');
            if (m) m.classList.add('active');
        }

        async function submitAddHolding() {
            const sym = document.getElementById('add-h-sym').value.trim().toUpperCase();
            const name = document.getElementById('add-h-name').value.trim();
            const sharesStr = document.getElementById('add-h-shares').value.replace(/,/g, '');
            const priceStr = document.getElementById('add-h-price').value.replace(/,/g, '');
            const shares = parseFloat(sharesStr);
            const price = parseFloat(priceStr);
            const curr = document.getElementById('add-h-curr').value.trim().toUpperCase() || 'USD';
            const port = document.getElementById('add-h-port').value.trim() || 'USD HSBC';

            if (!sym || isNaN(shares) || shares <= 0 || isNaN(price) || price < 0) {
                alert(t('err_fill_holding'));
                return;
            }

            try {
                const res = await fetch('/api/holding/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol: sym, name: name, shares: shares, buy_price: price, currency: curr, portfolio: port })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    closeModal('modal-add-holding');
                    showToast(t('toast_add_holding', { sym: sym }));
                    loadData();
                } else {
                    alert(t('err_add_holding', { msg: data.message || 'Error' }));
                }
            } catch (err) {
                alert(t('err_network', { msg: err.message }));
            }
        }

        async function deleteHolding(sym) {
            if (!confirm(t('confirm_del_holding', { sym: sym }))) return;
            try {
                const payload = { symbol: sym };
                if (currentSelectedHoldingPortfolio) payload.portfolio = currentSelectedHoldingPortfolio;
                const res = await fetch('/api/holding/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.status === 'success') {
                    closeModal('modal-holding-detail');
                    showToast(t('toast_del_holding', { sym: sym }));
                    loadData();
                } else {
                    alert(t('err_del_holding', { msg: data.message || 'Error' }));
                }
            } catch (err) {
                alert(t('err_network', { msg: err.message }));
            }
        }

        function openAddWatchlistModal() {
            document.getElementById('add-w-sym').value = '';
            document.getElementById('add-w-name').value = '';
            document.getElementById('add-w-tgt').value = '';
            document.getElementById('add-w-curr').value = currentCurrency || 'USD';
            document.getElementById('add-w-notes').value = '';
            const m = document.getElementById('modal-add-watchlist');
            if (m) m.classList.add('active');
        }

        async function submitAddWatchlist() {
            const sym = document.getElementById('add-w-sym').value.trim().toUpperCase();
            const name = document.getElementById('add-w-name').value.trim();
            const tgtStr = document.getElementById('add-w-tgt').value.replace(/,/g, '');
            const tgt = parseFloat(tgtStr) || 0;
            const curr = document.getElementById('add-w-curr').value.trim().toUpperCase() || 'USD';
            const notes = document.getElementById('add-w-notes').value.trim();

            if (!sym) {
                alert(t('err_fill_symbol'));
                return;
            }

            try {
                const res = await fetch('/api/watchlist/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol: sym, name: name, target_price: tgt, currency: curr, notes: notes })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    closeModal('modal-add-watchlist');
                    showToast(t('toast_add_watchlist', { sym: sym }));
                    loadData();
                } else {
                    alert(t('err_add_watchlist', { msg: data.message || 'Error' }));
                }
            } catch (err) {
                alert(t('err_network', { msg: err.message }));
            }
        }

        async function deleteWatchlistItem(sym) {
            if (!confirm(t('confirm_del_watchlist', { sym: sym }))) return;
            try {
                const res = await fetch('/api/watchlist/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol: sym })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    closeModal('modal-watchlist-detail');
                    showToast(t('toast_del_watchlist', { sym: sym }));
                    loadData();
                } else {
                    alert(t('err_del_watchlist', { msg: data.message || 'Error' }));
                }
            } catch (err) {
                alert(t('err_network', { msg: err.message }));
            }
        }

        // --- GOOGLE SHEETS CLOUD SYNC FUNCTIONS ---
        async function fetchGoogleSheetStatus() {
            try {
                const res = await fetch('/api/google_sheet/status');
                const cfg = await res.json();
                
                // 1. Update Header / Hero Badge
                const badge = document.getElementById('sheet-sync-badge');
                if (badge) {
                    if (!cfg.configured) {
                        badge.textContent = '☁️ ' + (currentLang === 'en' ? 'Setup Sync' : (currentLang === 'zh_CN' ? '未设置同步' : '未設定同步'));
                        badge.style.background = 'rgba(255, 179, 0, 0.2)';
                        badge.style.color = 'var(--accent-amber)';
                    } else if (cfg.has_conflict) {
                        badge.textContent = '⚠️ ' + (currentLang === 'en' ? 'Conflict' : (currentLang === 'zh_CN' ? '发现冲突' : '發現衝突'));
                        badge.style.background = 'rgba(255, 69, 58, 0.2)';
                        badge.style.color = 'var(--accent-red)';
                    } else if (cfg.last_sync_status === 'success') {
                        badge.textContent = '☁️ ' + (currentLang === 'en' ? 'Synced' : (currentLang === 'zh_CN' ? '已同步' : '已同步'));
                        badge.style.background = 'rgba(52, 199, 89, 0.2)';
                        badge.style.color = 'var(--accent-green)';
                    } else if (cfg.last_sync_status === 'offline') {
                        badge.textContent = '☁️ ' + (currentLang === 'en' ? 'Offline' : (currentLang === 'zh_CN' ? '离线' : '離線'));
                        badge.style.background = 'rgba(142, 142, 147, 0.2)';
                        badge.style.color = 'var(--text-muted)';
                    } else {
                        badge.textContent = '☁️ ' + (cfg.last_sync_status || 'Sync');
                    }
                }

                // 2. Update Tools Subpane
                const paneBadge = document.getElementById('cloud-pane-badge');
                if (paneBadge) {
                    if (!cfg.configured) {
                        paneBadge.textContent = currentLang === 'en' ? '⚠️ Not Configured' : (currentLang === 'zh_CN' ? '⚠️ 未设置' : '⚠️ 未設定');
                        paneBadge.style.background = 'rgba(255, 179, 0, 0.2)';
                        paneBadge.style.color = 'var(--accent-amber)';
                    } else if (cfg.has_conflict) {
                        paneBadge.textContent = currentLang === 'en' ? '⚠️ Conflict' : (currentLang === 'zh_CN' ? '⚠️ 发现冲突' : '⚠️ 發現衝突');
                        paneBadge.style.background = 'rgba(255, 69, 58, 0.2)';
                        paneBadge.style.color = 'var(--accent-red)';
                    } else if (cfg.last_sync_status === 'success') {
                        paneBadge.textContent = currentLang === 'en' ? '✅ Synced' : (currentLang === 'zh_CN' ? '✅ 已同步' : '✅ 已同步');
                        paneBadge.style.background = 'rgba(52, 199, 89, 0.2)';
                        paneBadge.style.color = 'var(--accent-green)';
                    } else {
                        paneBadge.textContent = '☁️ ' + (cfg.last_sync_status || 'Unknown');
                        paneBadge.style.background = 'rgba(142, 142, 147, 0.2)';
                        paneBadge.style.color = 'var(--text-muted)';
                    }
                }
                const paneSt = document.getElementById('cloud-pane-status-txt');
                if (paneSt) paneSt.textContent = (cfg.last_sync_status || 'not_configured').toUpperCase();
                const paneTm = document.getElementById('cloud-pane-time-txt');
                if (paneTm) paneTm.textContent = cfg.last_sync_time || (currentLang === 'en' ? 'Never' : '從未同步');
                const paneDev = document.getElementById('cloud-pane-dev-txt');
                if (paneDev) paneDev.textContent = `${cfg.device_name || 'Device'} (${(cfg.device_id || '').substring(0, 14)}...)`;
                const paneMsg = document.getElementById('cloud-pane-msg');
                if (paneMsg) paneMsg.textContent = cfg.last_sync_message || '';
                const paneUrl = document.getElementById('cloud-pane-url');
                if (paneUrl && !paneUrl.value && cfg.web_app_url) paneUrl.value = cfg.web_app_url;
                const paneAuto = document.getElementById('cloud-pane-autoupload');
                if (paneAuto && typeof cfg.auto_upload_on_edit !== 'undefined') paneAuto.checked = !!cfg.auto_upload_on_edit;

                // 3. Update Modal inputs if present
                const modalUrl = document.getElementById('sheet-modal-url');
                if (modalUrl && !modalUrl.value && cfg.web_app_url) modalUrl.value = cfg.web_app_url;

                return cfg;
            } catch (e) {
                console.error("Sheet status error:", e);
                return null;
            }
        }

        async function triggerGoogleSheetSync(fromTools = false) {
            const badge = document.getElementById('sheet-sync-badge');
            if (badge) badge.textContent = '🔄 Syncing...';
            const paneBadge = document.getElementById('cloud-pane-badge');
            if (paneBadge) paneBadge.textContent = '🔄 同步中...';
            try {
                const res = await fetch('/api/google_sheet/sync', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'not_configured') {
                    if (fromTools) {
                        showToast(currentLang === 'en' ? 'Please configure Google Apps Script URL below.' : '請在下方設定 Google Apps Script 網址');
                    } else {
                        openGoogleSheetModal();
                    }
                    return;
                }
                if (data.status === 'conflict') {
                    showSheetConflictModal(data);
                    return;
                }
                if (data.status === 'success' || data.status === 'up_to_date') {
                    showToast(data.message || 'Google Sheet Synced!');
                    await fetchGoogleSheetStatus();
                    loadData();
                    return;
                }
                if (data.status === 'offline') {
                    showToast('⚠️ Google Sheet is offline. Edits saved locally.', 3500);
                    await fetchGoogleSheetStatus();
                    return;
                }
                showToast(data.message || 'Sync failed', 3000);
            } catch (e) {
                showToast('Sync network error: ' + e, 3000);
            } finally {
                await fetchGoogleSheetStatus();
            }
        }

        async function triggerGoogleSheetPush() {
            const confirmMsg = currentLang === 'en'
                ? 'Are you sure you want to push local data to Google Sheet?'
                : (currentLang === 'zh_CN' ? '确定要将本地数据上传覆盖 Google 表格吗？' : '確定要將本機資料上傳覆蓋 Google 試算表嗎？');
            if (!confirm(confirmMsg)) return;

            const badge = document.getElementById('sheet-sync-badge');
            if (badge) badge.textContent = '⬆️ Uploading...';
            const paneBadge = document.getElementById('cloud-pane-badge');
            if (paneBadge) paneBadge.textContent = '⬆️ 上傳中...';

            try {
                const res = await fetch('/api/google_sheet/push', { method: 'POST' });
                const data = await res.json();
                showToast(data.message || '已成功上傳至 Google 試算表！');
                await fetchGoogleSheetStatus();
                loadData();
            } catch (e) {
                showToast('上傳失敗: ' + e, 3000);
            } finally {
                await fetchGoogleSheetStatus();
            }
        }

        async function triggerGoogleSheetPull() {
            const confirmMsg = currentLang === 'en'
                ? 'Are you sure you want to download data from Google Sheet? (Automatic local backup will be created)'
                : (currentLang === 'zh_CN' ? '确定要自 Google 表格下载数据覆盖本地吗？（系统将自动创建备份）' : '確定要自 Google 試算表下載資料覆蓋本機嗎？（系統將自動建立備份）');
            if (!confirm(confirmMsg)) return;

            const badge = document.getElementById('sheet-sync-badge');
            if (badge) badge.textContent = '⬇️ Downloading...';
            const paneBadge = document.getElementById('cloud-pane-badge');
            if (paneBadge) paneBadge.textContent = '⬇️ 下載中...';

            try {
                const res = await fetch('/api/google_sheet/pull', { method: 'POST' });
                const data = await res.json();
                showToast(data.message || '已成功自 Google 試算表下載！');
                await fetchGoogleSheetStatus();
                loadData();
            } catch (e) {
                showToast('下載失敗: ' + e, 3000);
            } finally {
                await fetchGoogleSheetStatus();
            }
        }

        async function testGoogleSheetConnectionPane() {
            const url = (document.getElementById('cloud-pane-url').value || '').trim();
            const msg = document.getElementById('cloud-pane-msg');
            if (msg) {
                msg.textContent = currentLang === 'en' ? 'Testing connection...' : '連線測試中...';
                msg.style.color = 'var(--accent-blue)';
            }
            try {
                const res = await fetch('/api/google_sheet/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ web_app_url: url })
                });
                const d = await res.json();
                if (msg) {
                    msg.textContent = d.message;
                    msg.style.color = d.success ? 'var(--accent-green)' : 'var(--accent-red)';
                }
                showToast(d.success ? '✅ Google Sheet 連線成功！' : '❌ 連線失敗: ' + d.message);
            } catch (e) {
                if (msg) {
                    msg.textContent = '連線測試失敗: ' + e;
                    msg.style.color = 'var(--accent-red)';
                }
            }
        }

        async function saveGoogleSheetPaneConfig() {
            const url = (document.getElementById('cloud-pane-url').value || '').trim();
            const autoupload = document.getElementById('cloud-pane-autoupload')?.checked ?? true;
            try {
                await fetch('/api/google_sheet/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ web_app_url: url, auto_upload_on_edit: autoupload })
                });
                showToast(currentLang === 'en' ? 'Google Sheet settings saved!' : 'Google 試算表設定已儲存！');
                await fetchGoogleSheetStatus();
            } catch (e) {
                showToast('儲存失敗: ' + e);
            }
        }

        async function openGoogleSheetModal() {
            const cfg = await fetchGoogleSheetStatus();
            if (cfg) {
                const urlInput = document.getElementById('sheet-modal-url');
                if (urlInput && cfg.web_app_url) urlInput.value = cfg.web_app_url;
                const st = document.getElementById('sheet-modal-status-txt');
                if (st) st.textContent = (cfg.last_sync_status || 'Unconfigured').toUpperCase();
                const tm = document.getElementById('sheet-modal-time-txt');
                if (tm) tm.textContent = cfg.last_sync_time || 'Never';
                const msg = document.getElementById('sheet-modal-msg');
                if (msg) msg.textContent = cfg.last_sync_message || '';
            }
            openModal('modal-google-sheet');
        }

        async function testGoogleSheetConnection() {
            const url = (document.getElementById('sheet-modal-url').value || '').trim();
            const msg = document.getElementById('sheet-modal-msg');
            if (msg) {
                msg.textContent = 'Testing connection...';
                msg.style.color = 'var(--accent-blue)';
            }
            try {
                const res = await fetch('/api/google_sheet/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ web_app_url: url })
                });
                const d = await res.json();
                if (msg) {
                    msg.textContent = d.message;
                    msg.style.color = d.success ? 'var(--accent-green)' : 'var(--accent-red)';
                }
            } catch (e) {
                if (msg) {
                    msg.textContent = 'Connection test failed: ' + e;
                    msg.style.color = 'var(--accent-red)';
                }
            }
        }

        async function saveAndSyncGoogleSheet() {
            const url = (document.getElementById('sheet-modal-url').value || '').trim();
            try {
                await fetch('/api/google_sheet/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ web_app_url: url })
                });
                closeModal('modal-google-sheet');
                triggerGoogleSheetSync();
            } catch (e) {
                showToast('Error saving config: ' + e);
            }
        }

        async function copyGoogleAppsScript() {
            try {
                const res = await fetch('/api/google_sheet/apps_script');
                const d = await res.json();
                if (d.code) {
                    await navigator.clipboard.writeText(d.code);
                    showToast('📋 Google Apps Script code copied to clipboard!');
                }
            } catch (e) {
                showToast('Failed to copy code: ' + e);
            }
        }

        function showSheetConflictModal(data) {
            const list = document.getElementById('sheet-conflict-diff-list');
            if (!list) return;
            list.innerHTML = '';
            const diffs = data.differences || (data.diff_report ? data.diff_report.differences : []) || [];
            if (diffs.length === 0) {
                list.innerHTML = '<div>No item differences found.</div>';
            } else {
                diffs.forEach(d => {
                    const row = document.createElement('div');
                    row.style.padding = '6px 8px';
                    row.style.marginBottom = '4px';
                    row.style.borderRadius = '6px';
                    row.style.background = d.type === 'MODIFIED' ? 'rgba(255,179,0,0.15)' : 'rgba(10,132,255,0.12)';
                    row.innerHTML = `<strong>[${d.tab}] ${d.key}</strong> (${d.type})<br><span style="color:var(--text-muted); font-size:0.74rem;">${d.description}</span>`;
                    list.appendChild(row);
                });
            }
            openModal('modal-sheet-conflict');
        }

        async function resolveCloudConflict(resolution) {
            try {
                const res = await fetch('/api/google_sheet/resolve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ resolution: resolution })
                });
                const d = await res.json();
                closeModal('modal-sheet-conflict');
                showToast(d.message || 'Conflict resolved!');
                await fetchGoogleSheetStatus();
                loadData();
            } catch (e) {
                showToast('Failed resolving conflict: ' + e);
            }
        }

        function initApp() {
            try {
                const savedTheme = localStorage.getItem('gfinance_theme');
                if (savedTheme === 'light') {
                    document.body.classList.add('theme-light');
                    document.documentElement.classList.add('theme-light');
                } else if (savedTheme === 'dark') {
                    document.body.classList.remove('theme-light');
                    document.documentElement.classList.remove('theme-light');
                }
            } catch (e) {}
            try { detectPlatform(); } catch (e) { console.error('detectPlatform error:', e); }
            try { setLanguage(currentLang); } catch (e) { console.error('setLanguage error:', e); }
            try { initChartCanvasEvents(); } catch (e) { console.error('initChartCanvasEvents error:', e); }
            loadData();
            try { fetchGoogleSheetStatus(); } catch (e) {}
            // Auto refresh quotes every 45s
            setInterval(loadData, 45000);
            setInterval(fetchGoogleSheetStatus, 45000);
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initApp);
        } else {
            initApp();
        }

        function onWindowResizeOrRotate() {
            detectPlatform();
            if (currentChartData) {
                const prepared = currentPreparedChart || prepareMetricSeries(currentChartData);
                if (prepared) drawPriceChart(prepared);
            }
            if (currentPortfolioData && currentPortfolioData.holdings) drawDonutChart(currentPortfolioData.holdings);
        }
        window.addEventListener('resize', onWindowResizeOrRotate);
        window.addEventListener('orientationchange', () => {
            setTimeout(onWindowResizeOrRotate, 150);
        });
        if (window.screen && window.screen.orientation) {
            window.screen.orientation.addEventListener('change', onWindowResizeOrRotate);
        }

        // Close active modals on Escape key
        window.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
            }
        });

        if ('serviceWorker' in navigator && !navigator.userAgent.includes('a-Shell')) {
            navigator.serviceWorker.register('/sw.js').catch(err => console.log('SW registration skipped', err));
        }
    </script>
</body>
</html>
"""


def execute_refresh_quotes() -> Dict[str, Any]:
    """
    Fetches real-time market quotes for all symbols in portfolio and watchlist
    using GoogleFinanceFetcher with thread pool concurrency, updates portfolio.csv
    and watchlist_quotes.json, and returns execution metrics.
    """
    import concurrent.futures
    try:
        from google_finance_fetcher import GoogleFinanceFetcher
        fetcher = GoogleFinanceFetcher()
    except Exception as e:
        return {"status": "error", "message": f"Fetcher unavailable: {e}", "updated_count": 0, "total": 0}

    portfolio_holdings = csv_manager.load_portfolio()
    watchlist_items = csv_manager.load_watchlist()

    # Collect unique symbols
    symbols_to_fetch = set()
    for h in portfolio_holdings:
        s = (h.get("symbol") or "").strip().upper()
        if s:
            symbols_to_fetch.add(s)
    for w in watchlist_items:
        s = (w.get("symbol") or "").strip().upper()
        if s:
            symbols_to_fetch.add(s)

    if not symbols_to_fetch:
        return {"status": "success", "updated_count": 0, "total": 0, "timestamp": datetime.now().isoformat()}

    quotes_map: Dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_to_sym = {executor.submit(fetcher.fetch_quote, s): s for s in symbols_to_fetch}
        for future in concurrent.futures.as_completed(future_to_sym):
            sym = future_to_sym[future]
            try:
                res = future.result()
                if res and res.get("success"):
                    quotes_map[sym] = res
            except Exception:
                pass

    # 1. Update portfolio holdings
    p_updated = 0
    if portfolio_holdings:
        for h in portfolio_holdings:
            sym = (h.get("symbol") or "").strip().upper()
            if sym in quotes_map:
                q = quotes_map[sym]
                new_price = float(q.get("price", 0.0) or 0.0)
                if new_price > 0:
                    h["current_price"] = new_price
                    if q.get("name") and (not h.get("name") or h.get("name") == sym):
                        h["name"] = q.get("name")
                    if q.get("change") is not None:
                        h["change"] = float(q.get("change", 0.0) or 0.0)
                    if q.get("change_percent") is not None:
                        h["change_percent"] = float(q.get("change_percent", 0.0) or 0.0)
                    if q.get("dividend_yield") is not None:
                        h["dividend_yield"] = float(q.get("dividend_yield", 0.0) or 0.0)
                    if q.get("annual_dividend_per_share") is not None:
                        h["annual_div_per_share"] = float(q.get("annual_dividend_per_share", 0.0) or 0.0)
                    h["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # Recompute holding summary
                    shares = float(h.get("shares", 0.0) or 0.0)
                    buy_price = float(h.get("buy_price", 0.0) or 0.0)
                    div_yield = float(h.get("dividend_yield", 0.0) or 0.0)
                    ann_div = float(h.get("annual_div_per_share", 0.0) or 0.0)
                    summary = financial_calc.calc_holding_summary(shares, buy_price, new_price, div_yield, ann_div)
                    h.update(summary)
                    p_updated += 1
        csv_manager.save_portfolio(portfolio_holdings)

    # 2. Update watchlist quotes cache
    w_cache = csv_manager.load_watchlist_quotes_cache()
    w_updated = 0
    for sym, q in quotes_map.items():
        w_cache[sym] = q
        w_updated += 1
    if quotes_map:
        csv_manager.save_watchlist_quotes_cache(w_cache)

    # Invalidate chart caches
    global _API_CHART_CACHE
    _API_CHART_CACHE.clear()
    try:
        from chart_fetcher import get_chart_fetcher
        get_chart_fetcher().clear_cache()
    except Exception:
        pass

    return {
        "status": "success",
        "updated_count": len(quotes_map),
        "total": len(symbols_to_fetch),
        "portfolio_updated": p_updated,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# =============================================================================
# REQUEST HANDLER ROUTING
# =============================================================================

class DashboardRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence console log noise in a-shell terminal
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # 1. Main HTML Interface
        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

        # 2. PWA Manifest
        elif path == "/manifest.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(MANIFEST_JSON.encode("utf-8"))

        # 3. Service Worker
        elif path == "/sw.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.end_headers()
            self.wfile.write(SERVICE_WORKER_JS.encode("utf-8"))

        # 4. Device Detection API
        elif path == "/api/device":
            ua = self.headers.get("User-Agent", "")
            dev_info = parse_device_info(ua)
            self.send_json(dev_info)

        # Google Sheet Sync Status API
        elif path in ("/api/google_sheet/status", "/api/sync/status", "/api/sync/google_sheets/status", "/api/sync/google_sheets"):
            from google_sheet_sync import get_google_sheet_sync
            sync_mgr = get_google_sheet_sync()
            self.send_json(sync_mgr.get_sync_status())

        # Google Sheet Apps Script Template API
        elif path in ("/api/google_sheet/apps_script", "/api/sync/apps_script"):
            from google_sheet_sync import get_google_apps_script_template
            self.send_json({"code": get_google_apps_script_template()})

        # 5. Portfolio API
        elif path == "/api/portfolio":
            req_curr = params.get("currency", ["USD"])[0].upper()
            req_port = params.get("portfolio", ["All"])[0]

            converter = get_currency_converter()
            raw_holdings = csv_manager.load_portfolio()
            registered_ports = csv_manager.load_registered_portfolios()

            # Filter by portfolio name if specified
            if req_port and req_port != "All":
                holdings = [h for h in raw_holdings if (h.get("portfolio") or h.get("portfolio_name") or "") == req_port]
            else:
                holdings = raw_holdings

            tot_val = 0.0
            tot_cost = 0.0
            tot_div = 0.0
            safe_val = 0.0
            eq_val = 0.0
            processed_holdings = []

            for h in holdings:
                sym = h.get("symbol", "")
                c = (h.get("currency") or "USD").strip().upper()
                shares = float(h.get("shares", 0.0) or 0.0)
                price = float(h.get("current_price", h.get("price", 0.0)) or 0.0)
                buy_p = float(h.get("buy_price", 0.0) or 0.0)
                div = float(h.get("annual_dividend", 0.0) or 0.0)

                # 1. Holding Native Values in its own currency
                mv_native = shares * price
                cb_native = shares * buy_p
                pl_native = mv_native - cb_native
                roi_native = (pl_native / cb_native * 100.0) if cb_native > 0 else 0.0
                c_sym = converter.CURRENCY_SYMBOLS.get(c, "$")

                # 2. Converted values in Portfolio Summary currency (req_curr)
                mv_conv = converter.convert(mv_native, c, req_curr)
                cb_conv = converter.convert(cb_native, c, req_curr)
                div_conv = converter.convert(div, c, req_curr)

                tot_val += mv_conv
                tot_cost += cb_conv
                tot_div += div_conv

                # Classification (Safe vs Equity)
                sym_upper = sym.upper()
                if any(x in sym_upper for x in ["BND", "TIP", "VTIP", "VGSH", "XSB", "CASH", "GIC", "TBILL"]):
                    safe_val += mv_conv
                else:
                    eq_val += mv_conv

                processed_holdings.append({
                    "symbol": sym,
                    "name": h.get("name", sym),
                    "shares": shares,
                    "buy_price": buy_p,
                    "current_price": price,
                    "market_value": mv_native,
                    "cost_basis": cb_native,
                    "unrealized_pl": pl_native,
                    "roi_pct": roi_native,
                    "annual_dividend": div,
                    "currency": c,
                    "currency_symbol": c_sym,
                    "converted_buy_price": converter.convert(buy_p, c, req_curr),
                    "converted_current_price": converter.convert(price, c, req_curr),
                    "converted_market_value": mv_conv,
                    "converted_cost_basis": cb_conv,
                    "converted_unrealized_pl": mv_conv - cb_conv,
                    "converted_annual_dividend": div_conv,
                    "rate_to_summary": converter.convert(1.0, c, req_curr),
                    "portfolio": h.get("portfolio") or h.get("portfolio_name") or "",
                })

            total_pl = tot_val - tot_cost
            overall_roi = (total_pl / tot_cost * 100.0) if tot_cost > 0 else 0.0

            payload = {
                "currency": req_curr,
                "currency_symbol": converter.CURRENCY_SYMBOLS.get(req_curr, "$"),
                "total_value": tot_val,
                "total_cost": tot_cost,
                "total_unrealized_pl": total_pl,
                "overall_roi_pct": overall_roi,
                "total_annual_dividend": tot_div,
                "equity_assets": eq_val,
                "safe_assets": safe_val,
                "portfolios": registered_ports,
                "holdings": processed_holdings,
                "fx_rates_summary": converter.get_rates_summary(req_curr) if hasattr(converter, "get_rates_summary") else f"1 USD = 1.399 CAD",
            }
            self.send_json(payload)

        # 6. Bernstein FIRE Metrics API
        elif path == "/api/fire":
            req_curr = params.get("currency", ["USD"])[0].upper()
            converter = get_currency_converter()
            raw_holdings = csv_manager.load_portfolio()
            settings_data = csv_manager.load_settings() if hasattr(csv_manager, "load_settings") else {}
            fire_params = settings_data.get("fire_params", {})

            # Sum portfolio totals in requested currency
            tot_p = 0.0
            tot_div = 0.0
            safe_p = 0.0

            for h in raw_holdings:
                c = (h.get("currency") or "USD").upper()
                shares = float(h.get("shares", 0.0) or 0.0)
                price = float(h.get("current_price", h.get("price", 0.0)) or 0.0)
                div = float(h.get("annual_dividend", 0.0) or 0.0)
                mv = converter.convert(shares * price, c, req_curr)
                tot_p += mv
                tot_div += converter.convert(div, c, req_curr)
                if any(x in (h.get("symbol") or "").upper() for x in ["BND", "TIP", "VTIP", "VGSH", "XSB", "CASH"]):
                    safe_p += mv

            outside_safe = float(fire_params.get("outside_safe_assets", 0.0) or 0.0)
            total_effective_safe = safe_p + outside_safe
            total_effective_wealth = tot_p + outside_safe

            cur_age = int(fire_params.get("current_age", 45))
            ret_age = int(fire_params.get("retire_age", 60))
            life_exp = int(fire_params.get("life_expectancy", 90))
            s_yrs = float(fire_params.get("target_safe_years", 25.0))
            m_exp = float(fire_params.get("target_monthly_expense", 3500.0))
            p_ann = float(fire_params.get("guaranteed_annual_pension", 15000.0))
            m_sav = float(fire_params.get("monthly_savings", 0.0))
            div_g = float(fire_params.get("expected_div_growth", 5.0)) / 100.0

            res = financial_calc.calc_fire_metrics(
                current_annual_div=tot_div,
                target_monthly_expense=m_exp,
                expected_div_growth=div_g,
                current_portfolio_val=total_effective_wealth,
                monthly_savings=m_sav,
                guaranteed_annual_pension=p_ann,
                target_safe_years=s_yrs,
                current_age=cur_age,
                retire_age=ret_age,
                life_expectancy=life_exp,
                current_safe_assets=total_effective_safe,
            )

            res["currency_symbol"] = converter.CURRENCY_SYMBOLS.get(req_curr, "$")
            res["safe_asset_years_covered"] = f"{total_effective_safe / (res.get('liability_matching_target', 1) / s_yrs):.1f}" if res.get('liability_matching_target', 0) > 0 else "25.0"
            self.send_json(res)

        # 6.5 Interactive Chart API
        elif path == "/api/chart":
            req_sym = params.get("symbol", ["PORTFOLIO"])[0].strip().upper()
            req_tf = params.get("timeframe", ["1M"])[0].strip().upper()
            req_curr = params.get("currency", ["USD"])[0].strip().upper()
            req_port = params.get("portfolio", ["All"])[0]

            # Fast cache lookup for instantaneous portfolio / symbol chart loading
            cache_key = f"{req_sym}:{req_port}:{req_tf}:{req_curr}"
            cached_entry = _API_CHART_CACHE.get(cache_key)
            if cached_entry:
                c_time, c_data = cached_entry
                ttl = 60 if req_tf == "1D" else (180 if req_tf == "5D" else 900)
                if time.time() - c_time < ttl:
                    self.send_json(c_data)
                    return

            converter = get_currency_converter()
            raw_holdings = csv_manager.load_portfolio()
            if req_port and req_port != "All":
                holdings = [h for h in raw_holdings if (h.get("portfolio") or h.get("portfolio_name") or "") == req_port]
            else:
                holdings = raw_holdings

            chart_data = None
            try:
                from chart_fetcher import get_chart_fetcher
                cf = get_chart_fetcher()
                if req_sym in ("PORTFOLIO", "TOTAL", "ALL"):
                    chart_data = cf.fetch_portfolio_history(
                        holdings=holdings,
                        portfolio_name=req_port,
                        timeframe=req_tf,
                        converter=converter,
                        target_currency=req_curr
                    )
                else:
                    chart_data = cf.fetch_symbol_history(req_sym, req_tf)
            except Exception:
                chart_data = None

            if not chart_data or not chart_data.get("prices"):
                chart_data = self._generate_fallback_chart_data(req_sym, req_tf, req_curr, holdings, converter)

            # Compute holding scale factor, cost basis, and dividend metadata for metric modes
            tot_shares = 0.0
            tot_cb = 0.0
            tot_div = 0.0
            chart_curr = req_curr
            is_single = req_sym not in ("PORTFOLIO", "TOTAL", "ALL")

            if is_single:
                matched = [h for h in holdings if (h.get("symbol") or "").strip().upper() == req_sym]
                if matched:
                    chart_curr = (matched[0].get("currency") or "USD").strip().upper()
                for h in matched:
                    shs = float(h.get("shares", 0.0) or 0.0)
                    bp = float(h.get("buy_price", 0.0) or 0.0)
                    ann_d = float(h.get("annual_dividend", 0.0) or 0.0)
                    tot_shares += shs
                    # In single stock mode, cost basis and dividends are in the stock's NATIVE currency!
                    tot_cb += (shs * bp)
                    tot_div += ann_d
            else:
                for h in holdings:
                    shs = float(h.get("shares", 0.0) or 0.0)
                    bp = float(h.get("buy_price", 0.0) or 0.0)
                    c = (h.get("currency") or "USD").strip().upper()
                    ann_d = float(h.get("annual_dividend", 0.0) or 0.0)
                    rate = converter.convert(1.0, c, req_curr) if converter else 1.0
                    tot_cb += (shs * bp * rate)
                    tot_div += (ann_d * rate)
                tot_shares = 1.0

            if chart_data:
                chart_data["total_shares"] = tot_shares
                chart_data["total_cost_basis"] = round(tot_cb, 2)
                chart_data["total_annual_div"] = round(tot_div, 2)
                chart_data["is_holding"] = (tot_shares > 0)
                chart_data["currency"] = chart_curr
                chart_data["currency_symbol"] = converter.CURRENCY_SYMBOLS.get(chart_curr, "$")

            if chart_data and "timestamps" in chart_data:
                ts_clean = []
                for t in chart_data["timestamps"]:
                    if hasattr(t, "strftime"):
                        ts_clean.append(t.strftime("%H:%M") if req_tf == "1D" else t.strftime("%Y-%m-%d"))
                    else:
                        ts_clean.append(str(t))
                chart_data["timestamps"] = ts_clean

            # Clean any non-serializable fields in dividend_events if present
            if chart_data and "dividend_events" in chart_data:
                clean_divs = []
                for ev in chart_data["dividend_events"]:
                    if isinstance(ev, (list, tuple)) and len(ev) >= 2:
                        d_str = ev[0].strftime("%Y-%m-%d") if hasattr(ev[0], "strftime") else str(ev[0])
                        clean_divs.append([d_str, float(ev[1])])
                chart_data["dividend_events"] = clean_divs

            if chart_data and chart_data.get("prices"):
                _API_CHART_CACHE[cache_key] = (time.time(), chart_data)

            self.send_json(chart_data)

        # 7. Watchlist API
        elif path == "/api/watchlist":
            raw_watchlist = csv_manager.load_watchlist()
            quotes_cache = csv_manager.load_watchlist_quotes_cache()
            raw_holdings = csv_manager.load_portfolio()
            holdings_price_map = {}
            for h in raw_holdings:
                s = (h.get("symbol") or "").strip().upper()
                p = float(h.get("current_price", h.get("price", 0.0)) or 0.0)
                if s and p > 0:
                    holdings_price_map[s] = p

            enriched = []
            for item in raw_watchlist:
                w = dict(item)
                sym = (w.get("symbol") or "").strip().upper()
                cur_price = 0.0
                change = 0.0
                change_pct = 0.0

                if sym in quotes_cache:
                    q = quotes_cache[sym]
                    cur_price = float(q.get("price", 0.0) or 0.0)
                    change = float(q.get("change", 0.0) or 0.0)
                    change_pct = float(q.get("change_percent", 0.0) or 0.0)
                    if q.get("name") and not w.get("name"):
                        w["name"] = q.get("name")

                if cur_price == 0.0 and sym in holdings_price_map:
                    cur_price = holdings_price_map[sym]

                w["current_price"] = cur_price
                w["change"] = change
                w["change_percent"] = change_pct
                enriched.append(w)

            self.send_json(enriched)

        # 8. Data Health Check API
        elif path == "/api/health":
            try:
                res = csv_manager.scan_data_integrity()
                self.send_json(res)
            except Exception as e:
                self.send_json({"healthy": False, "total_issues": 1, "issues": [{"desc": str(e), "type": "ERROR"}]})

        # 9. HTML Report API
        elif path == "/api/report":
            req_curr = params.get("currency", ["USD"])[0].upper()
            req_lang = params.get("lang", ["zh_TW"])[0]
            try:
                import i18n
                i18n.set_language(req_lang)
            except Exception:
                pass
            converter = get_currency_converter()
            raw_holdings = csv_manager.load_portfolio()
            holdings = []
            tot_v = 0.0
            tot_c = 0.0
            tot_d = 0.0
            for h in raw_holdings:
                h_copy = dict(h)
                c = (h_copy.get("currency") or "USD").upper()
                s = float(h_copy.get("shares", 0.0) or 0.0)
                p = float(h_copy.get("current_price", h_copy.get("price", 0.0)) or 0.0)
                bp = float(h_copy.get("buy_price", 0.0) or 0.0)
                d = float(h_copy.get("annual_dividend", 0.0) or 0.0)
                mv = converter.convert(s * p, c, req_curr)
                cb = converter.convert(s * bp, c, req_curr)
                tot_v += mv
                tot_c += cb
                tot_d += converter.convert(d, c, req_curr)
                h_copy["current_price"] = converter.convert(p, c, req_curr)
                h_copy["buy_price"] = converter.convert(bp, c, req_curr)
                h_copy["market_value"] = mv
                h_copy["cost_basis"] = cb
                h_copy["unrealized_gain"] = mv - cb
                h_copy["unrealized_gain_pct"] = ((mv - cb) / cb * 100) if cb > 0 else 0.0
                holdings.append(h_copy)
            metrics = {
                "base_currency": req_curr,
                "total_value": tot_v,
                "total_cost": tot_c,
                "total_gain": tot_v - tot_c,
                "total_gain_pct": ((tot_v - tot_c) / tot_c * 100) if tot_c > 0 else 0.0,
                "total_annual_div": tot_d,
                "total_monthly_div": tot_d / 12,
                "portfolio_yoc": (tot_d / tot_c * 100) if tot_c > 0 else 0.0,
                "overall_div_yield": (tot_d / tot_v * 100) if tot_v > 0 else 0.0,
                "total_day_change": 0.0,
                "total_day_change_pct": 0.0,
            }
            sales = csv_manager.load_sales_history() if hasattr(csv_manager, "load_sales_history") else []
            with tempfile.NamedTemporaryFile("w+", suffix=".html", delete=False, encoding="utf-8") as tmp:
                tmp_path = tmp.name
            report_generator.generate_html_report(holdings, metrics, sales, filepath=tmp_path)
            with open(tmp_path, "r", encoding="utf-8") as f:
                report_html = f.read()
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(report_html.encode("utf-8"))

        # 10. CSV Export API
        elif path == "/api/export/csv":
            csv_path = csv_manager.PORTFOLIO_CSV
            if os.path.exists(csv_path):
                with open(csv_path, "rb") as f:
                    csv_bytes = f.read()
            else:
                csv_bytes = b"symbol,name,shares,buy_price,currency,annual_dividend\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="g_finance_portfolio.csv"')
            self.end_headers()
            self.wfile.write(csv_bytes)

        # 11. Watchlist CSV Export API
        elif path == "/api/export/watchlist_csv":
            wl_path = csv_manager.WATCHLIST_CSV
            if os.path.exists(wl_path):
                with open(wl_path, "rb") as f:
                    csv_bytes = f.read()
            else:
                csv_bytes = b"symbol,name,target_price,notes\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="g_finance_watchlist.csv"')
            self.end_headers()
            self.wfile.write(csv_bytes)

        # 12. Complete JSON Backup API
        elif path == "/api/export/json":
            backup = {
                "version": "2.0",
                "exported_at": datetime.now().isoformat(),
                "portfolio": csv_manager.load_portfolio(),
                "holdings": csv_manager.load_portfolio(),
                "transactions": csv_manager.load_transactions(),
                "sales_history": csv_manager.load_sales_history(),
                "watchlist": csv_manager.load_watchlist(),
                "portfolios": csv_manager.load_registered_portfolios(),
            }
            json_bytes = json.dumps(backup, indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="g_finance_backup.json"')
            self.end_headers()
            self.wfile.write(json_bytes)

        elif path == "/api/portfolio/summary":
            stats = csv_manager.get_portfolio_summary_stats()
            self.send_json(stats)

        elif path == "/api/refresh":
            res = execute_refresh_quotes()
            self.send_json(res)

        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        """Handles CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def read_json_body(self) -> Dict[str, Any]:
        """Reads and parses JSON body from POST requests with size limit guard."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            content_length = 0
        if content_length > 0:
            content_length = min(content_length, 10 * 1024 * 1024)
            try:
                body = self.rfile.read(content_length).decode("utf-8", errors="replace")
                return json.loads(body)
            except Exception:
                return {}
        return {}

    def do_POST(self):
        if self.path in ("/api/google_sheet/sync", "/api/sync/google_sheets", "/api/sync"):
            data = self.read_json_body()
            direction = data.get("direction") or data.get("force_direction")
            from google_sheet_sync import get_google_sheet_sync
            sync_mgr = get_google_sheet_sync()
            res = sync_mgr.perform_sync(force_direction=direction)
            self.send_json(res)

        elif self.path in ("/api/google_sheet/push", "/api/sync/push", "/api/sync/google_sheets/push"):
            from google_sheet_sync import get_google_sheet_sync
            sync_mgr = get_google_sheet_sync()
            res = sync_mgr.perform_sync(force_direction="keep_local")
            self.send_json(res)

        elif self.path in ("/api/google_sheet/pull", "/api/sync/pull", "/api/sync/google_sheets/pull"):
            from google_sheet_sync import get_google_sheet_sync
            sync_mgr = get_google_sheet_sync()
            res = sync_mgr.perform_sync(force_direction="keep_remote")
            self.send_json(res)

        elif self.path in ("/api/google_sheet/resolve", "/api/sync/resolve"):
            data = self.read_json_body()
            choice = data.get("resolution", "keep_local")
            from google_sheet_sync import get_google_sheet_sync
            sync_mgr = get_google_sheet_sync()
            res = sync_mgr.perform_sync(force_direction=choice)
            self.send_json(res)

        elif self.path in ("/api/google_sheet/config", "/api/sync/config"):
            data = self.read_json_body()
            from google_sheet_sync import get_google_sheet_sync, save_sheet_config
            sync_mgr = get_google_sheet_sync()
            url = (data.get("web_app_url") or "").strip()
            if url:
                sync_mgr.set_web_app_url(url)
            if "auto_upload_on_edit" in data:
                sync_mgr.config["auto_upload_on_edit"] = bool(data["auto_upload_on_edit"])
                save_sheet_config(sync_mgr.config)
            self.send_json({"status": "ok", "config": sync_mgr.get_sync_status()})

        elif self.path in ("/api/google_sheet/test", "/api/sync/test"):
            data = self.read_json_body()
            test_url = (data.get("web_app_url") or "").strip()
            from google_sheet_sync import get_google_sheet_sync
            sync_mgr = get_google_sheet_sync()
            ok, msg, details = sync_mgr.test_connection(url=test_url if test_url else None)
            self.send_json({"success": ok, "message": msg, "details": details})

        elif self.path == "/api/refresh":
            res = execute_refresh_quotes()
            self.send_json(res)

        elif self.path == "/api/holding/add":
            try:
                data = self.read_json_body()
                sym = (data.get("symbol") or "").strip().upper()
                name = (data.get("name") or "").strip() or sym
                shares = float(data.get("shares", 0.0) or 0.0)
                buy_price = float(data.get("buy_price", 0.0) or 0.0)
                curr = (data.get("currency") or "USD").strip().upper()
                port = (data.get("portfolio") or "USD HSBC").strip()

                if not sym or shares <= 0 or buy_price < 0:
                    self.send_json({"status": "error", "message": "無效的標的代碼、股數或成本價"})
                    return

                ok = csv_manager.add_holding({
                    "portfolio": port,
                    "symbol": sym,
                    "name": name,
                    "shares": shares,
                    "buy_price": buy_price,
                    "currency": curr,
                })
                if ok:
                    self.send_json({"status": "success", "message": f"成功加入持股 {sym}"})
                else:
                    self.send_json({"status": "error", "message": f"無法加入持股 {sym}"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)})

        elif self.path == "/api/holding/update":
            try:
                data = self.read_json_body()
                orig_sym = (data.get("original_symbol") or data.get("symbol") or "").strip().upper()
                orig_port = (data.get("original_portfolio") or data.get("portfolio") or "USD HSBC").strip()
                new_sym = (data.get("symbol") or orig_sym).strip().upper()
                new_port = (data.get("portfolio") or orig_port).strip()
                new_curr = (data.get("currency") or "USD").strip().upper()
                shares = float(data.get("shares", 0.0) or 0.0)
                buy_price = float(data.get("buy_price", 0.0) or 0.0)

                if not orig_sym or shares <= 0 or buy_price < 0:
                    self.send_json({"status": "error", "message": "無效的標的代碼、股數或成本價"})
                    return

                ok = csv_manager.update_holding(
                    original_portfolio=orig_port,
                    original_symbol=orig_sym,
                    updated_data={
                        "portfolio": new_port,
                        "symbol": new_sym,
                        "currency": new_curr,
                        "shares": shares,
                        "buy_price": buy_price,
                        "target_sell_price": float(data.get("target_sell_price") or 0.0),
                        "stop_loss_price": float(data.get("stop_loss_price") or 0.0),
                    }
                )
                if ok:
                    self.send_json({"status": "success", "message": f"成功更新持股 {new_sym}"})
                else:
                    self.send_json({"status": "error", "message": f"未找到持股 {orig_sym} ({orig_port})"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)})

        elif self.path == "/api/holding/delete":
            try:
                data = self.read_json_body()
                sym = (data.get("symbol") or "").strip().upper()
                port = (data.get("portfolio") or "").strip()
                if not sym:
                    self.send_json({"status": "error", "message": "缺少標的代碼"})
                    return

                ok = csv_manager.delete_holding(portfolio=port, symbol=sym)
                if ok:
                    self.send_json({"status": "success", "message": f"已刪除持股 {sym}"})
                else:
                    self.send_json({"status": "error", "message": f"未找到持股 {sym}"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)})

        elif self.path == "/api/watchlist/add":
            try:
                data = self.read_json_body()
                sym = (data.get("symbol") or "").strip().upper()
                name = (data.get("name") or "").strip()
                tgt = float(data.get("target_price", 0.0) or 0.0)
                curr = (data.get("currency") or "USD").strip().upper()
                notes = (data.get("notes") or "").strip()

                if not sym:
                    self.send_json({"status": "error", "message": "缺少標的代碼"})
                    return

                ok = csv_manager.add_to_watchlist(symbol=sym, name=name, target_price=tgt, currency=curr, notes=notes)
                if ok:
                    self.send_json({"status": "success", "message": f"成功加入自選 {sym}"})
                else:
                    self.send_json({"status": "error", "message": "寫入自選清單失敗"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)})

        elif self.path == "/api/watchlist/delete":
            try:
                data = self.read_json_body()
                sym = (data.get("symbol") or "").strip().upper()
                if not sym:
                    self.send_json({"status": "error", "message": "缺少標的代碼"})
                    return

                ok = csv_manager.remove_from_watchlist(symbol=sym)
                if ok:
                    self.send_json({"status": "success", "message": f"已從自選清單移除 {sym}"})
                else:
                    self.send_json({"status": "error", "message": f"自選清單中未找到 {sym}"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)})

        elif self.path == "/api/portfolio/import":
            try:
                data = self.read_json_body()
                merge = bool(data.get("merge", False))
                payload = data.get("data", data)
                import tempfile
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tf:
                    json.dump(payload, tf)
                    tf_name = tf.name
                res = csv_manager.import_portfolio_from_json(tf_name, merge=merge)
                if os.path.exists(tf_name):
                    try:
                        os.remove(tf_name)
                    except OSError:
                        pass
                self.send_json(res)
            except Exception as e:
                self.send_json({"success": False, "error": str(e)})

        elif self.path == "/api/transaction/add":
            try:
                data = self.read_json_body()
                is_val, errs = csv_manager.validate_transaction_data(data)
                if not is_val:
                    self.send_json({"status": "error", "message": "; ".join(errs)})
                    return
                ok = csv_manager.append_transaction(data)
                if ok and data.get("sync_holding", True):
                    csv_manager.sync_transaction_change_to_portfolio(None, data)
                self.send_json({"status": "success" if ok else "error"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)})

        elif self.path == "/api/transaction/delete":
            try:
                data = self.read_json_body()
                idx = int(data.get("index", -1))
                all_tx = csv_manager.load_transactions()
                old_tx = all_tx[idx] if 0 <= idx < len(all_tx) else None
                ok = csv_manager.delete_transaction(idx)
                if ok and old_tx and data.get("sync_holding", True):
                    csv_manager.sync_transaction_change_to_portfolio(old_tx, None)
                self.send_json({"status": "success" if ok else "error"})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)})

        elif self.path == "/api/repair":
            try:
                res = csv_manager.repair_data_integrity()
                self.send_json({"status": "success", "result": res})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)})
        elif self.path == "/api/stop":
            self.send_json({"status": "stopping", "message": "Server stopping..."})
            def _delayed_shutdown():
                import time
                time.sleep(0.5)
                stop_server()
                global _CLI_SERVER
                if _CLI_SERVER:
                    try:
                        _CLI_SERVER.shutdown()
                    except Exception:
                        pass
            threading.Thread(target=_delayed_shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def _generate_fallback_chart_data(self, symbol: str, timeframe: str, currency: str, holdings: list, converter: Any) -> dict:
        """Generates realistic fallback/synthetic chart curve when offline or data fetching fails."""
        import math
        from datetime import timedelta

        now = datetime.now()
        tf = timeframe.upper()
        if tf == "YTD":
            start_time = datetime(now.year, 1, 1)
            days_span = max(5, (now - start_time).days)
            num_points = min(60, max(20, days_span // 4))
            delta = (now - start_time) / max(1, num_points - 1)
        elif tf == "1D":
            num_points = 24
            delta = timedelta(minutes=15)
            start_time = now - timedelta(hours=6)
        elif tf == "5D":
            num_points = 30
            delta = timedelta(hours=4)
            start_time = now - timedelta(days=5)
        elif tf == "1M":
            num_points = 30
            delta = timedelta(days=1)
            start_time = now - timedelta(days=30)
        elif tf == "6M":
            num_points = 45
            delta = timedelta(days=4)
            start_time = now - timedelta(days=182)
        elif tf == "1Y":
            num_points = 52
            delta = timedelta(weeks=1)
            start_time = now - timedelta(days=365)
        elif tf == "5Y":
            num_points = 60
            delta = timedelta(days=30)
            start_time = now - timedelta(days=1825)
        elif tf == "MAX":
            num_points = 72
            delta = timedelta(days=45)
            start_time = now - timedelta(days=3240)
        else:
            num_points = 30
            delta = timedelta(days=1)
            start_time = now - timedelta(days=30)

        # Determine baseline price or total portfolio value
        base_price = 100.0
        label = symbol
        if symbol in ("PORTFOLIO", "TOTAL", "ALL"):
            label = "總資產 (Total Portfolio)"
            total_val = 0.0
            for h in holdings:
                shares = float(h.get("shares", 0.0) or 0.0)
                price = float(h.get("current_price", h.get("buy_price", 0.0)) or 0.0)
                h_curr = (h.get("currency") or "USD").strip().upper()
                rate = 1.0
                if converter and h_curr != currency:
                    rate = converter.convert(1.0, h_curr, currency)
                total_val += (shares * price * rate)
            if total_val > 0:
                base_price = total_val
        else:
            # Look in holdings first
            matched = [h for h in holdings if (h.get("symbol") or "").strip().upper() == symbol]
            if matched:
                base_price = float(matched[0].get("current_price", matched[0].get("buy_price", 100.0)) or 100.0)
                label = f"{symbol} - {matched[0].get('name', '')}"
            else:
                # Look in watchlist
                wl = csv_manager.load_watchlist()
                w_match = [w for w in wl if (w.get("symbol") or "").strip().upper() == symbol]
                if w_match:
                    base_price = float(w_match[0].get("target_price", 100.0) or 100.0)
                    label = f"{symbol} - {w_match[0].get('name', '')}"

        # Generate smooth curve ending at base_price
        prices = []
        timestamps = []

        for i in range(num_points):
            t = start_time + (delta * i)
            # Gentle harmonic wave around trend
            progress = i / max(1, num_points - 1)
            wave = math.sin(progress * math.pi * 3) * 0.025 + math.cos(progress * math.pi * 1.5) * 0.015
            drift = (progress - 1.0) * 0.05
            p = max(1.0, base_price * (1.0 + drift + wave))
            prices.append(round(p, 2))
            timestamps.append(t.strftime("%H:%M") if tf == "1D" else t.strftime("%Y-%m-%d"))

        # Guarantee final point is base_price
        if prices:
            prices[-1] = round(base_price, 2)
            timestamps[-1] = now.strftime("%H:%M") if tf == "1D" else now.strftime("%Y-%m-%d")

        prev_close = prices[0] if prices else base_price
        curr_price = prices[-1] if prices else base_price
        change = curr_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0.0

        return {
            "label": label,
            "symbol": symbol,
            "timeframe": tf,
            "currency": currency,
            "prices": prices,
            "timestamps": timestamps,
            "current_price": round(curr_price, 2),
            "prev_close": round(prev_close, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "dividend_events": [],
            "source": "synthetic_fallback"
        }

    def send_json(self, data: Any):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


# =============================================================================
# SERVER LIFECYCLE MANAGEMENT
# =============================================================================

_CLI_SERVER: Optional[HTTPServer] = None


def start_server(port: int = 8765, host: str = "0.0.0.0", data_callback: Optional[Callable] = None) -> int:
    """Starts the HTTP server daemon on an available port."""
    global _SERVER_INSTANCE, _SERVER_THREAD, _PORT, _HOST, _DATA_CALLBACK
    if is_running():
        return _PORT

    _HOST = host
    _PORT = find_free_port(port, host=_HOST)
    _DATA_CALLBACK = data_callback
    _SERVER_INSTANCE = ServerClass((_HOST, _PORT), DashboardRequestHandler)
    _SERVER_THREAD = threading.Thread(target=_SERVER_INSTANCE.serve_forever, daemon=True)
    _SERVER_THREAD.start()

    # Automatic startup sync check with Google Sheet if configured
    try:
        from google_sheet_sync import get_google_sheet_sync
        sync_mgr = get_google_sheet_sync()
        if sync_mgr.is_configured() and sync_mgr.config.get("auto_sync_on_startup", True):
            threading.Thread(target=sync_mgr.perform_sync, daemon=True).start()
    except Exception:
        pass

    return _PORT


def stop_server():
    """Stops the running HTTP server instance."""
    global _SERVER_INSTANCE, _SERVER_THREAD
    if _SERVER_INSTANCE:
        _SERVER_INSTANCE.shutdown()
        _SERVER_INSTANCE.server_close()
        _SERVER_INSTANCE = None
        _SERVER_THREAD = None


def is_running() -> bool:
    """Checks if web server is currently running."""
    return _SERVER_INSTANCE is not None


def get_server_url() -> str:
    """Returns local web dashboard URL."""
    return f"http://localhost:{_PORT}"


# =============================================================================
# STANDALONE CLI ENTRYPOINT (RUNS DIRECTLY IN A-SHELL / ISH / PC)
# =============================================================================

if __name__ == "__main__":
    import argparse
    import time
    parser = argparse.ArgumentParser(
        description="G_Finance Mobile & Web Server for iPhone, iPad, PC & a-Shell",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("command", nargs="?", default="view", help="Command or mode: 'view' (default) or 'server'/'headless'")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address")
    parser.add_argument("--view", dest="auto_view", action="store_true", default=True,
                        help="Start server and auto-open a-Shell view overlay (Default)")
    parser.add_argument("--no-view", "--headless", dest="auto_view", action="store_false",
                        help="Run server in foreground without auto-opening view window")
    args = parser.parse_args()

    if args.command in ("server", "headless", "no-view"):
        args.auto_view = False

    actual_port = find_free_port(args.port, host=args.host)
    lan_ip = get_lan_ip()

    print("=" * 64)
    print("🏛️  G_FINANCE MOBILE & PWA SERVER READY")
    print("=" * 64)
    print(f"📱 Local / a-Shell URL:   http://localhost:{actual_port}")
    print(f"🌐 Wi-Fi / iPhone URL:     http://{lan_ip}:{actual_port}")
    print("=" * 64)
    print("💡 在 iPhone a-Shell 中執行：")
    print("   python3 web_server.py")
    print("   👉 預設已自動在背景啟動 Server，並透過 internalbrowser / openurl 開啟介面！")
    print("   (若只想單純在終端機跑 Server，可加 --no-view 或 --headless)")
    print("💡 a-Shell 常用網址開啟指令：")
    print(f"   • a-Shell 內建浮動瀏覽器: internalbrowser http://localhost:{actual_port}")
    print(f"   • 跳轉 iPhone Safari 開啟: openurl http://localhost:{actual_port}")
    print("💡 在 iPhone Safari 加入桌面 PWA：")
    print("   點擊 分享 ➔ 加入主畫面 (Add to Home Screen)")
    print("=" * 64)
    print("Press Ctrl+C to stop server.\n")

    target_url = f"http://localhost:{actual_port}"
    if args.auto_view:
        if not is_server_alive(actual_port):
            _CLI_SERVER = ServerClass((args.host, actual_port), DashboardRequestHandler)
            t = threading.Thread(target=_CLI_SERVER.serve_forever, daemon=True)
            t.start()
            # Health check polling to ensure socket is accepting connections before opening browser
            for _ in range(30):
                if is_server_alive(actual_port, timeout=0.2):
                    break
                time.sleep(0.08)
        else:
            _CLI_SERVER = None
            t = None

        print(f"🚀 Auto-launching interface: {target_url}")
        
        # In a-Shell:
        # - internalbrowser opens interactive in-app WebView
        # - openurl opens system browser (Safari)
        # - open opens system URL scheme
        # - webbrowser.open is cross-platform desktop fallback
        opened = False
        for cmd in [f"internalbrowser '{target_url}'", f"openurl '{target_url}'", f"open '{target_url}'"]:
            try:
                if os.system(f"{cmd} 2>/dev/null") == 0:
                    opened = True
                    break
            except Exception:
                pass
        if not opened:
            try:
                import webbrowser
                webbrowser.open(target_url)
            except Exception:
                pass

        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\nStopping G_Finance server...")
            if _CLI_SERVER:
                _CLI_SERVER.shutdown()
                _CLI_SERVER.server_close()
    else:
        _CLI_SERVER = ServerClass((args.host, actual_port), DashboardRequestHandler)
        try:
            _CLI_SERVER.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping G_Finance server...")
            _CLI_SERVER.shutdown()
            _CLI_SERVER.server_close()
