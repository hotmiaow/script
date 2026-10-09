"""
web_server.py
Zero-dependency, mobile-first Web & PWA server for Google Finance Portfolio Tracker.
Optimized for:
- Apple iPhone (Touch-friendly single-column, bottom navigation, cards)
- Apple iPad (Adaptive 2-column tablet layout, split view)
- Desktop PC / Mac (Widescreen multi-column dashboard)
- a-Shell & iSH (Runs standalone offline on iOS with Python standard library)
"""

import os
import sys
import json
import socket
import threading
import tempfile
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Callable, Dict, Any, List

import csv_manager
import financial_calc
import report_generator
from currency_converter import get_currency_converter

_SERVER_INSTANCE: Optional[HTTPServer] = None
_SERVER_THREAD: Optional[threading.Thread] = None
_PORT: int = 8765
_HOST: str = "0.0.0.0"
_DATA_CALLBACK: Optional[Callable] = None


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


def find_free_port(start_port: int = 8765, max_attempts: int = 20, host: str = "0.0.0.0") -> int:
    """Finds an open localhost port starting from start_port."""
    for p in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
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
    e.respondWith(
        fetch(e.request).catch(() => caches.match(e.request))
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

    <style>
        :root {
            --bg-body: #000000;
            --bg-card: #1c1c1e;
            --bg-card-subtle: #2c2c2e;
            --border-color: #38383a;
            --text-main: #ffffff;
            --text-muted: #8e8e93;
            --accent-blue: #0a84ff;
            --accent-green: #30d158;
            --accent-yellow: #ffd60a;
            --accent-red: #ff453a;
            --accent-purple: #bf5af2;
            --safe-bottom: env(safe-area-inset-bottom, 16px);
            --safe-top: env(safe-area-inset-top, 20px);
        }

        body.theme-light {
            --bg-body: #f2f2f7;
            --bg-card: #ffffff;
            --bg-card-subtle: #e5e5ea;
            --border-color: #d1d1d6;
            --text-main: #000000;
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
            padding: 0 16px;
        }

        /* Top Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0 16px 0;
        }
        .header-title {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .header-title h1 {
            margin: 0;
            font-size: 1.35rem;
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        .device-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 8px;
            background: var(--bg-card-subtle);
            border-radius: 20px;
            font-size: 0.72rem;
            font-weight: 600;
            color: var(--accent-blue);
            border: 1px solid var(--border-color);
        }

        .header-controls {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        select, .btn-icon {
            background: var(--bg-card);
            color: var(--text-main);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 7px 10px;
            font-size: 0.82rem;
            font-weight: 600;
            outline: none;
            cursor: pointer;
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
        @media (min-width: 768px) {
            .grid-2col {
                grid-template-columns: 1fr 1fr;
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
                display: none; /* Hide top tabs on iPhone */
            }
        }

        /* Holdings & Watchlist Touch Cards */
        .item-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 14px 16px;
            margin-bottom: 10px;
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
            right: 20px;
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
        @media (min-width: 768px) {
            .fab-refresh {
                bottom: 24px;
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
    </style>
</head>
<body class="platform-detect">

    <div class="app-container">
        <!-- Top App Bar -->
        <header>
            <div class="header-title">
                <h1>🏛️ G_Finance</h1>
                <span class="device-badge" id="platform-badge">Detecting...</span>
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
                    <option value="All">All Portfolios</option>
                </select>
                <button class="btn-icon" onclick="toggleTheme()" title="Toggle Dark/Light">🌓</button>
            </div>
        </header>

        <!-- Top Navigation Bar for iPad & Desktop -->
        <nav class="desktop-nav">
            <button class="nav-btn active" onclick="switchTab('portfolio')">📊 Portfolio</button>
            <button class="nav-btn" onclick="switchTab('fire')">🔥 FIRE Retirement</button>
            <button class="nav-btn" onclick="switchTab('watchlist')">👁️ Watchlist</button>
            <button class="nav-btn" onclick="switchTab('tools')">⚙️ Tools & Info</button>
        </nav>

        <!-- ============================================================= -->
        <!-- TAB 1: PORTFOLIO HOLDINGS -->
        <!-- ============================================================= -->
        <div id="tab-portfolio" class="tab-pane active">
            <!-- Hero Net Worth Card -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Total Portfolio Net Worth</span>
                    <span id="last-sync-time" style="font-size: 0.72rem; color: var(--text-muted);">Synced Just Now</span>
                </div>
                <div class="hero-amount" id="net-worth-val">$0.00</div>
                <div class="hero-pill-row">
                    <span class="pill" id="pill-gain">+0.00 (+0.0%)</span>
                    <span class="pill blue" id="pill-div">Div: $0.00/yr</span>
                    <span class="pill amber" id="pill-yield">Yield: 0.0%</span>
                </div>

                <!-- Step 1 Asset Allocation Visual Split -->
                <div class="visual-bar-wrap" style="margin-top: 18px;">
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
                <span class="card-title" id="holdings-count-title">Active Holdings (0)</span>
                <span style="font-size: 0.75rem; color: var(--accent-blue);" onclick="toggleHoldingsView()">Touch View ⮀</span>
            </div>

            <!-- Touch-Friendly Mobile Card List -->
            <div id="holdings-cards-container">
                <!-- Injected via JS -->
            </div>
        </div>

        <!-- ============================================================= -->
        <!-- TAB 2: BERNSTEIN FIRE RETIREMENT (ALL GAUGES & GRAPHICS) -->
        <!-- ============================================================= -->
        <div id="tab-fire" class="tab-pane">
            <div class="grid-2col">
                <!-- Gap 1: Safe Liability Matching Buffer (20-25 Yrs) -->
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">🛡️ Safe Liability Buffer (25-Yr)</span>
                        <span class="pill" id="fire-safe-badge">Auditing...</span>
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
                        <span class="card-title">💵 Passive Dividend Gap</span>
                        <span class="pill" id="fire-div-badge">Auditing...</span>
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
                        <span class="card-title">🏛️ Bernstein 3.2% Capital Gap</span>
                        <span class="pill" id="fire-cap-badge">Auditing...</span>
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
                        <span class="card-title">⚡ Burn Rate Corridor Speedometer</span>
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
                        <span>&lt;2.0% Safe</span>
                        <span>2.0-3.5% SWR</span>
                        <span>&gt;3.5% Fritz Red</span>
                    </div>
                </div>
            </div>

            <!-- Life Cycle Timeline Horizontal Bar -->
            <div class="card">
                <div class="card-title">⏳ Life Cycle & Retirement Horizon Timeline</div>
                <div class="bar-label-row" style="margin-top: 10px;">
                    <span id="tl-now">● Age 45 (Now)</span>
                    <span id="tl-ret" style="color: var(--accent-green)">★ Age 60 (FIRE)</span>
                    <span id="tl-end" style="color: var(--text-muted)">🏁 Age 90</span>
                </div>
                <div class="progress-track" style="height: 16px;">
                    <div class="progress-fill fill-blue" id="tl-accum-bar" style="width: 33%;"></div>
                    <div class="progress-fill fill-green" id="tl-dist-bar" style="width: 67%;"></div>
                </div>
                <div class="bar-label-row" style="font-size: 0.72rem; margin-top: 6px; color: var(--text-muted);">
                    <span id="tl-accum-txt">⏳ 15y Accumulation</span>
                    <span id="tl-dist-txt">🏖️ 30y Distribution Horizon</span>
                </div>
            </div>
        </div>

        <!-- ============================================================= -->
        <!-- TAB 3: WATCHLIST -->
        <!-- ============================================================= -->
        <div id="tab-watchlist" class="tab-pane">
            <div class="card-header" style="margin: 0 4px 10px 4px;">
                <span class="card-title">Real-Time Watchlist & Targets</span>
                <span id="wl-count-badge" class="pill blue">0 Tracked</span>
            </div>
            <div id="watchlist-cards-container">
                <!-- Injected via JS -->
            </div>
        </div>

        <!-- ============================================================= -->
        <!-- TAB 4: TOOLS & FINANCIAL UTILITIES SUITE -->
        <!-- ============================================================= -->
        <div id="tab-tools" class="tab-pane">
            <!-- Sub-Tools Scrollable Navigation Bar -->
            <div class="tool-subnav">
                <button class="tool-tab-btn active" id="btn-st-whatif" onclick="switchToolSubTab('whatif')">💡 What-If</button>
                <button class="tool-tab-btn" id="btn-st-rebalance" onclick="switchToolSubTab('rebalance')">⚖️ 再平衡</button>
                <button class="tool-tab-btn" id="btn-st-drip" onclick="switchToolSubTab('drip')">💧 股息複利</button>
                <button class="tool-tab-btn" id="btn-st-split" onclick="switchToolSubTab('split')">✂️ 股票分割</button>
                <button class="tool-tab-btn" id="btn-st-selling" onclick="switchToolSubTab('selling')">💰 賣出損益</button>
                <button class="tool-tab-btn" id="btn-st-health" onclick="switchToolSubTab('health')">🩺 健康檢查</button>
                <button class="tool-tab-btn" id="btn-st-reports" onclick="switchToolSubTab('reports')">📄 財務報表</button>
                <button class="tool-tab-btn" id="btn-st-backup" onclick="switchToolSubTab('backup')">💾 資料備份</button>
                <button class="tool-tab-btn" id="btn-st-diag" onclick="switchToolSubTab('diag')">📱 系統診斷</button>
            </div>

            <!-- SUBPANE 1: WHAT-IF SCENARIO SIMULATOR -->
            <div id="subpane-whatif" class="tool-subpane active">
                <div class="card">
                    <div class="card-title">💡 What-If 模擬加碼試算機</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;">
                        模擬加碼或買進新標的，即時預估對總資產、持有股數、配置比例與年股息的影響。
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">選擇持倉標的 (或手動輸入)</label>
                        <select id="whatif-select" class="form-control" onchange="onWhatIfHoldingSelected(this.value)">
                            <option value="">-- 自訂代碼 (Custom Ticker) --</option>
                        </select>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label">股票代碼 (Symbol)</label>
                            <input id="whatif-ticker" class="form-control" placeholder="如 VOO, AAPL" value="VOO" oninput="runWhatIfCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label">預估股價 (Price)</label>
                            <input id="whatif-price" type="number" step="any" class="form-control" placeholder="100.0" value="480" oninput="runWhatIfCalc()">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label">預估殖利率 % (Yield)</label>
                            <input id="whatif-yield" type="number" step="0.01" class="form-control" placeholder="1.8" value="1.5" oninput="runWhatIfCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label">加碼金額 ($ Amount)</label>
                            <input id="whatif-amt" type="number" step="any" class="form-control" value="5000" oninput="runWhatIfCalc()">
                        </div>
                    </div>

                    <div class="quick-btn-group">
                        <button class="quick-btn" onclick="addWhatIfAmt(1000)">+1,000</button>
                        <button class="quick-btn" onclick="addWhatIfAmt(5000)">+5,000</button>
                        <button class="quick-btn" onclick="addWhatIfAmt(10000)">+10,000</button>
                        <button class="quick-btn" onclick="addWhatIfAmt(20000)">+20,000</button>
                        <button class="quick-btn" onclick="setWhatIfAmt(5000)">重設 5,000</button>
                    </div>

                    <div class="result-box">
                        <div class="result-row">
                            <span style="color: var(--text-muted);">總資產變化:</span>
                            <strong id="whatif-res-total">$0.00 → $0.00</strong>
                        </div>
                        <div class="result-row">
                            <span style="color: var(--text-muted);">預計新增股數:</span>
                            <strong id="whatif-res-shares" style="color: var(--accent-blue)">0.00 shs</strong>
                        </div>
                        <div class="result-row">
                            <span style="color: var(--text-muted);">該標的配置佔比:</span>
                            <strong id="whatif-res-alloc">0.0% → 0.0%</strong>
                        </div>
                        <div class="result-row">
                            <span style="color: var(--text-muted);">被動年股息增長:</span>
                            <strong id="whatif-res-div" style="color: var(--accent-green)">+$0.00/yr (+$0.00/mo)</strong>
                        </div>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 2: PORTFOLIO REBALANCER -->
            <div id="subpane-rebalance" class="tool-subpane">
                <div class="card">
                    <div class="card-title">⚖️ 資產再平衡試算機</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;">
                        自訂各標的目標配置比例或套用模型，試算達成目標所需的買賣金額與股數。
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label">額外注入新資金 (現金加碼)</label>
                            <input id="rebal-cash" type="number" step="any" class="form-control" value="0" oninput="runRebalanceCalc()">
                        </div>
                    </div>

                    <div class="quick-btn-group" style="margin-bottom: 12px;">
                        <button class="quick-btn" onclick="applyRebalancePreset('equal')">均等權重 (Equal)</button>
                        <button class="quick-btn" onclick="applyRebalancePreset('reset')">重設為現況</button>
                    </div>

                    <div id="rebalance-holdings-list">
                        <!-- Injected via JS -->
                    </div>

                    <div class="result-box">
                        <div class="result-row">
                            <span style="color: var(--text-muted);">目標權重總和:</span>
                            <strong id="rebal-total-weight">100.0%</strong>
                        </div>
                        <div class="result-row">
                            <span style="color: var(--text-muted);">再平衡總資產規模:</span>
                            <strong id="rebal-total-val">$0.00</strong>
                        </div>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 3: DRIP & DIVIDEND COMPOUND -->
            <div id="subpane-drip" class="tool-subpane">
                <div class="card">
                    <div class="card-title">💧 股息再投資與複利試算 (DRIP)</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;">
                        試算股息複利滾存帶來的現金流指數級增長。
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label">目前年股息 (Annual Div)</label>
                            <input id="drip-init-div" type="number" step="any" class="form-control" oninput="runDripCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label">年股息成長率 % (Growth)</label>
                            <input id="drip-div-growth" type="number" step="0.1" class="form-control" value="5.0" oninput="runDripCalc()">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label">年化再投資報酬率 %</label>
                            <input id="drip-return" type="number" step="0.1" class="form-control" value="7.0" oninput="runDripCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label">每年額外加碼資金</label>
                            <input id="drip-extra" type="number" step="any" class="form-control" value="0" oninput="runDripCalc()">
                        </div>
                    </div>

                    <div class="desktop-table-card" style="margin-top: 10px;">
                        <table>
                            <thead>
                                <tr>
                                    <th>年期</th>
                                    <th>年被動股息</th>
                                    <th>月被動現金流</th>
                                    <th>複利滾存總資產</th>
                                </tr>
                            </thead>
                            <tbody id="drip-table-body">
                                <!-- Injected via JS -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 4: STOCK SPLIT CALCULATOR -->
            <div id="subpane-split" class="tool-subpane">
                <div class="card">
                    <div class="card-title">✂️ 股票分割 / 反分割計算機</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;">
                        當持股進行正分割 (如 2:1, 10:1) 或反分割 (如 1:2) 時，自動校正股數與每股平均買進成本。
                    </div>

                    <div class="form-group">
                        <label class="form-label">選擇持倉標的</label>
                        <select id="split-select" class="form-control" onchange="onSplitHoldingSelected(this.value)">
                            <option value="">-- 手動輸入 --</option>
                        </select>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label">分割前持有股數</label>
                            <input id="split-shares" type="number" step="any" class="form-control" value="10" oninput="runSplitCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label">分割前每股成本 ($)</label>
                            <input id="split-cost" type="number" step="any" class="form-control" value="200" oninput="runSplitCalc()">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label">分割分子 (換成幾股)</label>
                            <input id="split-num" type="number" step="any" class="form-control" value="2" oninput="runSplitCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label">分割分母 (原本幾股)</label>
                            <input id="split-den" type="number" step="any" class="form-control" value="1" oninput="runSplitCalc()">
                        </div>
                    </div>

                    <div class="quick-btn-group">
                        <button class="quick-btn" onclick="setSplitRatio(2,1)">2:1</button>
                        <button class="quick-btn" onclick="setSplitRatio(3,1)">3:1</button>
                        <button class="quick-btn" onclick="setSplitRatio(4,1)">4:1</button>
                        <button class="quick-btn" onclick="setSplitRatio(10,1)">10:1</button>
                        <button class="quick-btn" onclick="setSplitRatio(1,2)">1:2 反分割</button>
                        <button class="quick-btn" onclick="setSplitRatio(1,4)">1:4 反分割</button>
                    </div>

                    <div class="result-box">
                        <div class="result-row">
                            <span style="color: var(--text-muted);">校正後持有股數:</span>
                            <strong id="split-res-shares" style="color: var(--accent-blue)">20.0000 shs</strong>
                        </div>
                        <div class="result-row">
                            <span style="color: var(--text-muted);">校正後每股平均成本:</span>
                            <strong id="split-res-cost" style="color: var(--accent-green)">$100.00 / sh</strong>
                        </div>
                        <div class="result-row">
                            <span style="color: var(--text-muted);">總投資成本守恆:</span>
                            <strong id="split-res-total">$2,000.00 (不變 ✓)</strong>
                        </div>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 5: SELLING & PROFIT REALIZATION -->
            <div id="subpane-selling" class="tool-subpane">
                <div class="card">
                    <div class="card-title">💰 獲利了結與賣出損益試算機</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;">
                        試算部分或全部賣出時的已實現資本利得、現金入帳與剩餘持倉價值。
                    </div>

                    <div class="form-group">
                        <label class="form-label">選擇持倉標的</label>
                        <select id="sell-select" class="form-control" onchange="onSellHoldingSelected(this.value)">
                            <option value="">-- 手動輸入 --</option>
                        </select>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label">目前總持有股數</label>
                            <input id="sell-tot-shares" type="number" step="any" class="form-control" value="100" oninput="runSellCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label">平均每股買進成本 ($)</label>
                            <input id="sell-cost-price" type="number" step="any" class="form-control" value="150" oninput="runSellCalc()">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-col">
                            <label class="form-label">預計賣出股數</label>
                            <input id="sell-qty" type="number" step="any" class="form-control" value="50" oninput="runSellCalc()">
                        </div>
                        <div class="form-col">
                            <label class="form-label">預計每股賣出價 ($)</label>
                            <input id="sell-price" type="number" step="any" class="form-control" value="220" oninput="runSellCalc()">
                        </div>
                    </div>

                    <div class="quick-btn-group">
                        <button class="quick-btn" onclick="setSellPct(0.25)">賣出 25%</button>
                        <button class="quick-btn" onclick="setSellPct(0.50)">賣出 50%</button>
                        <button class="quick-btn" onclick="setSellPct(0.75)">賣出 75%</button>
                        <button class="quick-btn" onclick="setSellPct(1.00)">全部清倉 (100%)</button>
                    </div>

                    <div class="result-box">
                        <div class="result-row">
                            <span style="color: var(--text-muted);">賣出回收現金總額:</span>
                            <strong id="sell-res-proceeds" style="color: var(--accent-blue)">$11,000.00</strong>
                        </div>
                        <div class="result-row">
                            <span style="color: var(--text-muted);">已實現資本利得 (獲利):</span>
                            <strong id="sell-res-gain" style="color: var(--accent-green)">+$3,500.00 (+46.7%)</strong>
                        </div>
                        <div class="result-row">
                            <span style="color: var(--text-muted);">剩餘持倉股數:</span>
                            <strong id="sell-res-rem-shares">50.00 shs</strong>
                        </div>
                        <div class="result-row">
                            <span style="color: var(--text-muted);">剩餘部位市值:</span>
                            <strong id="sell-res-rem-val">$11,000.00</strong>
                        </div>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 6: DATA HEALTH & INTEGRITY -->
            <div id="subpane-health" class="tool-subpane">
                <div class="card">
                    <div class="card-title">🩺 資料完整性檢查與一鍵修復</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;">
                        自動審核 portfolio.csv 與 watchlist.csv，檢查是否有未填成本、缺少幣別、未分類標的或異常記錄。
                    </div>

                    <div style="display: flex; gap: 8px; margin-bottom: 12px;">
                        <button class="btn-action-primary" style="flex: 1;" onclick="scanDataHealth()">🔍 執行完整掃描</button>
                        <button class="btn-action-success" style="flex: 1;" onclick="repairDataHealth()">🛠️ 一鍵修復異常</button>
                    </div>

                    <div id="health-status-box" class="result-box">
                        <div id="health-summary" style="font-weight: 700; margin-bottom: 6px;">點擊上方按鈕開始檢查</div>
                        <div id="health-details" style="font-size: 0.78rem; color: var(--text-muted);">支援自動校正常見資料格式問題。</div>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 7: EXECUTIVE REPORTS -->
            <div id="subpane-reports" class="tool-subpane">
                <div class="card">
                    <div class="card-title">📄 完整財務執行摘要報表</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;">
                        產出專業的 HTML / PDF 格式財務報表，包含淨值圖表、資產配置分析、持股明細及收益預測。
                    </div>

                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <a id="btn-open-report" href="/api/report?currency=USD" target="_blank" class="btn-action-primary">
                            📑 開啟完整 HTML 財務報表 (新分頁)
                        </a>
                        <button class="btn-icon" style="padding: 10px; font-size: 0.84rem;" onclick="openReportInView()">
                            📱 在頁面內嵌預覽報表
                        </button>
                    </div>

                    <div id="report-preview-wrap" style="display: none; margin-top: 14px; border-radius: 12px; overflow: hidden; border: 1px solid var(--border-color);">
                        <iframe id="report-iframe" style="width: 100%; height: 420px; border: none; background: #ffffff;"></iframe>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 8: DATA BACKUP & EXPORT -->
            <div id="subpane-backup" class="tool-subpane">
                <div class="card">
                    <div class="card-title">💾 資料匯出與備份下載</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 12px;">
                        隨時下載持股與自選名單，保護您的財務資料安全無虞。
                    </div>

                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <a href="/api/export/csv" download="portfolio.csv" class="btn-action-primary" style="background: var(--bg-card); color: var(--text-dark); border: 1px solid var(--border-color);">
                            📥 下載持股資料 (portfolio.csv)
                        </a>
                        <a href="/api/export/watchlist_csv" download="watchlist.csv" class="btn-action-primary" style="background: var(--bg-card); color: var(--text-dark); border: 1px solid var(--border-color);">
                            📥 下載自選清單 (watchlist.csv)
                        </a>
                        <a href="/api/export/json" download="g_finance_backup.json" class="btn-action-primary">
                            📦 下載完整系統備份 (JSON Backup)
                        </a>
                    </div>
                </div>
            </div>

            <!-- SUBPANE 9: SYSTEM & DEVICE DIAGNOSTICS -->
            <div id="subpane-diag" class="tool-subpane">
                <div class="card">
                    <div class="card-title">📱 系統與裝置診斷</div>
                    <div style="font-size: 0.82rem; line-height: 1.8; margin-top: 8px;">
                        <div>執行平台辨識: <strong id="diag-platform" style="color: var(--accent-blue)">-</strong></div>
                        <div>觸控優化狀態: <strong id="diag-touch">-</strong></div>
                        <div>螢幕解析度: <strong id="diag-res">-</strong></div>
                        <div>獨立 PWA 模式: <strong id="diag-standalone">-</strong></div>
                    </div>
                    <div style="margin-top: 14px; display: flex; gap: 8px;">
                        <button class="btn-icon" style="flex: 1;" onclick="forceLayout('iphone')">📱 iPhone 模式</button>
                        <button class="btn-icon" style="flex: 1;" onclick="forceLayout('ipad')">📟 iPad 模式</button>
                        <button class="btn-icon" style="flex: 1;" onclick="forceLayout('desktop')">💻 PC 模式</button>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">⚡ 快速伺服器動作</div>
                    <div style="display: flex; flex-direction: column; gap: 10px; margin-top: 10px;">
                        <button class="btn-icon" style="padding: 12px; font-size: 0.9rem;" onclick="loadData()">🔄 立即刷新所有股價行情</button>
                        <button class="btn-icon" style="padding: 12px; font-size: 0.9rem; color: var(--accent-red);" onclick="stopServerRemote()">🛑 停止 G_Finance 伺服器</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Floating Action Button for 1-Tap Refresh -->
    <button class="fab-refresh" onclick="loadData()" title="Quick Refresh">🔄</button>

    <!-- Mobile Bottom Tab Navigation for iPhone -->
    <div class="bottom-tab-bar">
        <button class="tab-item active" id="btab-portfolio" onclick="switchTab('portfolio')">
            <span class="icon">📊</span>
            <span>Portfolio</span>
        </button>
        <button class="tab-item" id="btab-fire" onclick="switchTab('fire')">
            <span class="icon">🔥</span>
            <span>FIRE</span>
        </button>
        <button class="tab-item" id="btab-watchlist" onclick="switchTab('watchlist')">
            <span class="icon">👁️</span>
            <span>Watchlist</span>
        </button>
        <button class="tab-item" id="btab-tools" onclick="switchTab('tools')">
            <span class="icon">⚙️</span>
            <span>Tools</span>
        </button>
    </div>

    <!-- Application Script -->
    <script>
        let currentCurrency = 'USD';
        let currentPortfolio = 'All';
        let isTableView = false;

        // Auto Platform Detection
        function detectPlatform() {
            const ua = navigator.userAgent;
            const isTouch = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
            const w = window.innerWidth;
            let type = 'desktop';
            let label = '💻 Desktop';

            if (/iPad/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) {
                type = 'ipad';
                label = '📟 iPad (Tablet)';
            } else if (/iPhone|iPod/i.test(ua) || (isTouch && w < 768)) {
                type = 'iphone';
                label = '📱 iPhone (Touch)';
            } else if (isTouch) {
                type = 'touch';
                label = '📱 Touch Device';
            }

            document.body.className = 'platform-' + type;
            document.getElementById('platform-badge').textContent = label;
            document.getElementById('diag-platform').textContent = label;
            document.getElementById('diag-touch').textContent = isTouch ? 'Yes (Touch-Friendly)' : 'No (Mouse/Pointer)';
            document.getElementById('diag-res').textContent = window.innerWidth + ' × ' + window.innerHeight;
            document.getElementById('diag-standalone').textContent = (window.navigator.standalone || window.matchMedia('(display-mode: standalone)').matches) ? 'Yes (Installed PWA)' : 'Browser Mode';
        }

        function forceLayout(mode) {
            document.body.className = 'platform-' + mode;
            document.getElementById('platform-badge').textContent = 'Forced: ' + mode;
        }

        function toggleTheme() {
            document.body.classList.toggle('theme-light');
        }

        function switchTab(tabId) {
            // Update Tab Panes
            document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
            const targetPane = document.getElementById('tab-' + tabId);
            if (targetPane) targetPane.classList.add('active');

            // Update Top Desktop Nav
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            const desktopBtn = Array.from(document.querySelectorAll('.nav-btn')).find(b => b.getAttribute('onclick').includes(tabId));
            if (desktopBtn) desktopBtn.classList.add('active');

            // Update Mobile Bottom Tabs
            document.querySelectorAll('.tab-item').forEach(b => b.classList.remove('active'));
            const mobileBtn = document.getElementById('btab-' + tabId);
            if (mobileBtn) mobileBtn.classList.add('active');
        }

        function onCurrencyChange(val) {
            currentCurrency = val;
            loadData();
        }

        function onPortfolioChange(val) {
            currentPortfolio = val;
            loadData();
        }

        function toggleHoldingsView() {
            isTableView = !isTableView;
            loadData();
        }

        async function loadData() {
            try {
                // 1. Fetch Portfolio Data
                const pRes = await fetch(`/api/portfolio?currency=${currentCurrency}&portfolio=${encodeURIComponent(currentPortfolio)}`);
                const pData = await pRes.json();
                renderPortfolio(pData);

                // 2. Fetch FIRE Metrics
                const fRes = await fetch(`/api/fire?currency=${currentCurrency}`);
                const fData = await fRes.json();
                renderFIRE(fData);

                // 3. Fetch Watchlist
                const wRes = await fetch(`/api/watchlist`);
                const wData = await wRes.json();
                renderWatchlist(wData);
            } catch (err) {
                console.error('Failed to load G_Finance data:', err);
            }
        }

        function renderPortfolio(data) {
            const sym = data.currency_symbol || '$';
            document.getElementById('net-worth-val').textContent = sym + Number(data.total_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});

            // Gain pill
            const pl = Number(data.total_unrealized_pl || 0);
            const plPct = Number(data.overall_roi_pct || 0);
            const plEl = document.getElementById('pill-gain');
            plEl.textContent = (pl >= 0 ? '+' : '') + sym + pl.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' (' + plPct.toFixed(2) + '%)';
            plEl.className = 'pill ' + (pl >= 0 ? 'pos' : 'neg');

            // Dividend & Yield
            document.getElementById('pill-div').textContent = 'Div: ' + sym + Number(data.total_annual_dividend || 0).toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0}) + '/yr';
            const yld = data.total_value > 0 ? (data.total_annual_dividend / data.total_value * 100) : 0;
            document.getElementById('pill-yield').textContent = 'Yield: ' + yld.toFixed(2) + '%';

            // Asset split
            const eqVal = Number(data.equity_assets || 0);
            const safeVal = Number(data.safe_assets || 0);
            const tot = eqVal + safeVal;
            const eqPct = tot > 0 ? (eqVal / tot * 100) : 0;
            const safePct = tot > 0 ? (safeVal / tot * 100) : 0;

            document.getElementById('alloc-eq-lbl').textContent = `📈 Equity: ${sym}${eqVal.toLocaleString(undefined, {maximumFractionDigits: 0})} (${eqPct.toFixed(1)}%)`;
            document.getElementById('alloc-safe-lbl').textContent = `🛡️ Safe Buffer: ${sym}${safeVal.toLocaleString(undefined, {maximumFractionDigits: 0})} (${safePct.toFixed(1)}%)`;
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

            // Render holdings cards (Mobile touch cards)
            const listEl = document.getElementById('holdings-cards-container');
            listEl.innerHTML = '';
            document.getElementById('holdings-count-title').textContent = `Active Holdings (${(data.holdings || []).length})`;

            (data.holdings || []).forEach(h => {
                const card = document.createElement('div');
                card.className = 'item-card';
                const plH = Number(h.unrealized_pl || 0);
                const plHPct = Number(h.roi_pct || 0);
                const isPos = plH >= 0;

                card.innerHTML = `
                    <div class="item-left">
                        <strong>${h.symbol}</strong>
                        <div>${h.name || '-'} &bull; ${h.shares} shs</div>
                    </div>
                    <div class="item-right">
                        <div class="item-price">${sym}${Number(h.market_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
                        <span class="pill item-badge ${isPos ? 'pos' : 'neg'}">${isPos ? '+' : ''}${plHPct.toFixed(1)}%</span>
                    </div>
                `;
                listEl.appendChild(card);
            });

            // Sync with financial tools
            currentPortfolioData = data;
            populateToolsDropdowns(data.holdings || []);
            const reportBtn = document.getElementById('btn-open-report');
            if (reportBtn) reportBtn.href = `/api/report?currency=${currentCurrency}`;
            const dripInit = document.getElementById('drip-init-div');
            if (dripInit && (!dripInit.value || dripInit.value === '0')) {
                dripInit.value = (data.total_annual_dividend || 0).toFixed(0);
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
            document.getElementById('fire-safe-cur').textContent = `Current: ${sym}${safeCur.toLocaleString(undefined, {maximumFractionDigits: 0})} (${safePct.toFixed(1)}%)`;
            document.getElementById('fire-safe-tgt').textContent = `Target: ${sym}${safeTgt.toLocaleString(undefined, {maximumFractionDigits: 0})}`;
            document.getElementById('fire-safe-bar').style.width = safePct + '%';
            document.getElementById('fire-safe-gap-bar').style.width = (100 - safePct) + '%';
            document.getElementById('fire-safe-badge').textContent = safeGap > 0 ? `Gap: -${sym}${safeGap.toLocaleString(undefined, {maximumFractionDigits: 0})}` : '✓ Target Met';
            document.getElementById('fire-safe-badge').className = 'pill ' + (safeGap > 0 ? 'neg' : 'pos');
            document.getElementById('fire-safe-note').textContent = `🛡️ Buffer covers ${res.safe_asset_years_covered || (safeCur / (safeTgt / 25)).toFixed(1)} of 25.0 planned years`;

            // Gap 2: Passive Dividend Gap
            const divGap = Number(res.dividend_gap_annual || 0);
            const divCur = Number(res.current_annual_div || 0);
            const divTgt = Number(res.rle_annual || 0);
            const divPct = divTgt > 0 ? Math.min(100, (divCur / divTgt * 100)) : 100;

            document.getElementById('fire-div-val').textContent = `${sym}${divCur.toLocaleString(undefined, {maximumFractionDigits: 0})} / yr`;
            document.getElementById('fire-div-cur').textContent = `Current Div: ${sym}${divCur.toLocaleString(undefined, {maximumFractionDigits: 0})} (${divPct.toFixed(1)}%)`;
            document.getElementById('fire-div-tgt').textContent = `Target RLE: ${sym}${divTgt.toLocaleString(undefined, {maximumFractionDigits: 0})}`;
            document.getElementById('fire-div-bar').style.width = divPct + '%';
            document.getElementById('fire-div-gap-bar').style.width = (100 - divPct) + '%';
            document.getElementById('fire-div-badge').textContent = divGap > 0 ? `Gap: -${sym}${divGap.toLocaleString(undefined, {maximumFractionDigits: 0})}` : '✓ Free';
            document.getElementById('fire-div-badge').className = 'pill ' + (divGap > 0 ? 'amber' : 'pos');
            document.getElementById('fire-div-note').textContent = divGap > 0 ? `📈 Crossover in ${(res.years_to_crossover || 0).toFixed(1)} yrs @ 5% growth` : '✓ Full Dividend Freedom Achieved';

            // Gap 3: Bernstein 3.2% Principal Gap
            const capGap = Number(res.capital_gap_bernstein || 0);
            const capCur = Number(res.current_portfolio_val || 0);
            const capTgt = Number(res.bernstein_swr_32_target || 0);
            const capPct = capTgt > 0 ? Math.min(100, (capCur / capTgt * 100)) : 100;

            document.getElementById('fire-cap-val').textContent = sym + capCur.toLocaleString(undefined, {maximumFractionDigits: 0});
            document.getElementById('fire-cap-cur').textContent = `Current Wealth: ${sym}${capCur.toLocaleString(undefined, {maximumFractionDigits: 0})} (${capPct.toFixed(1)}%)`;
            document.getElementById('fire-cap-tgt').textContent = `3.2% Target: ${sym}${capTgt.toLocaleString(undefined, {maximumFractionDigits: 0})}`;
            document.getElementById('fire-cap-bar').style.width = capPct + '%';
            document.getElementById('fire-cap-gap-bar').style.width = (100 - capPct) + '%';
            document.getElementById('fire-cap-badge').textContent = capGap > 0 ? `Gap: -${sym}${capGap.toLocaleString(undefined, {maximumFractionDigits: 0})}` : '✓ Met';
            document.getElementById('fire-cap-badge').className = 'pill ' + (capGap > 0 ? 'amber' : 'pos');
            document.getElementById('fire-cap-note').textContent = capGap > 0 ? `💰 Monthly savings needed: ${sym}${Number(res.monthly_savings_needed || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}/mo` : '✓ Target Reached';

            // Burn Rate Speedometer
            const burn = Number(res.burn_rate_pct || 0);
            const burnEl = document.getElementById('fire-burn-rate');
            burnEl.textContent = burn.toFixed(2) + '%';
            const needleX = Math.max(5, Math.min(95, (burn / 6.0) * 100));
            document.getElementById('burn-needle').style.left = needleX + '%';
            document.getElementById('burn-needle-txt').textContent = burn.toFixed(2) + '%';

            let burnCol = 'var(--accent-green)';
            let burnTxt = 'Safe & Abundant';
            if (burn > 3.5) { burnCol = 'var(--accent-red)'; burnTxt = 'Over-Burn Danger'; }
            else if (burn >= 2.0) { burnCol = 'var(--accent-yellow)'; burnTxt = 'Sustainable SWR'; }
            burnEl.style.color = burnCol;
            document.getElementById('burn-needle').style.color = burnCol;
            document.getElementById('fire-burn-badge').textContent = `${burn.toFixed(2)}% (${burnTxt})`;
            document.getElementById('fire-burn-badge').className = 'pill ' + (burn <= 2.0 ? 'pos' : (burn <= 3.5 ? 'amber' : 'neg'));

            // Timeline
            const curAge = res.current_age || 45;
            const retAge = res.retire_age || 60;
            const lifeExp = res.life_expectancy || 90;
            const accumY = Math.max(0, retAge - curAge);
            const distY = Math.max(1, lifeExp - retAge);
            const span = lifeExp - curAge;

            document.getElementById('tl-now').textContent = `● Age ${curAge} (Now)`;
            document.getElementById('tl-ret').textContent = `★ Age ${retAge} (FIRE)`;
            document.getElementById('tl-end').textContent = `🏁 Age ${lifeExp}`;
            document.getElementById('tl-accum-bar').style.width = ((accumY / span) * 100) + '%';
            document.getElementById('tl-dist-bar').style.width = ((distY / span) * 100) + '%';
            document.getElementById('tl-accum-txt').textContent = `⏳ ${accumY}y Accumulation`;
            document.getElementById('tl-dist-txt').textContent = `🏖️ ${distY}y Distribution`;
        }

        function renderWatchlist(items) {
            const listEl = document.getElementById('watchlist-cards-container');
            listEl.innerHTML = '';
            document.getElementById('wl-count-badge').textContent = items.length + ' Tracked';

            items.forEach(w => {
                const card = document.createElement('div');
                card.className = 'item-card';
                const curP = Number(w.current_price || 0);
                const tgtP = Number(w.target_price || 0);
                const isMet = (tgtP > 0 && curP > 0 && curP <= tgtP);

                card.innerHTML = `
                    <div class="item-left">
                        <strong>${w.symbol}</strong>
                        <div>${w.name || '-'}</div>
                    </div>
                    <div class="item-right">
                        <div class="item-price">$${curP.toFixed(2)}</div>
                        <span class="pill item-badge ${isMet ? 'pos' : 'blue'}">
                            ${isMet ? '🎯 Target Hit: $' + tgtP.toFixed(2) : 'Target: $' + (tgtP > 0 ? tgtP.toFixed(2) : '-')}
                        </span>
                    </div>
                `;
                listEl.appendChild(card);
            });
        }

        // =============================================================
        // FINANCIAL TOOLS & UTILITIES LOGIC
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
        }

        function populateToolsDropdowns(holdings) {
            // 1. Populate What-If Select
            const whatIfSel = document.getElementById('whatif-select');
            if (whatIfSel) {
                const curVal = whatIfSel.value;
                whatIfSel.innerHTML = '<option value="">-- 自訂代碼 (Custom Ticker) --</option>';
                holdings.forEach(h => {
                    const opt = document.createElement('option');
                    opt.value = h.symbol;
                    opt.textContent = `${h.symbol} - ${h.name || ''} (${h.shares} shs @ $${Number(h.current_price || 0).toFixed(2)})`;
                    whatIfSel.appendChild(opt);
                });
                if (curVal) whatIfSel.value = curVal;
            }

            // 2. Populate Split Select
            const splitSel = document.getElementById('split-select');
            if (splitSel) {
                const curVal = splitSel.value;
                splitSel.innerHTML = '<option value="">-- 手動輸入 --</option>';
                holdings.forEach(h => {
                    const opt = document.createElement('option');
                    opt.value = h.symbol;
                    opt.textContent = `${h.symbol} (${h.shares} shs @ $${Number(h.current_price || 0).toFixed(2)})`;
                    splitSel.appendChild(opt);
                });
                if (curVal) splitSel.value = curVal;
            }

            // 3. Populate Sell Select
            const sellSel = document.getElementById('sell-select');
            if (sellSel) {
                const curVal = sellSel.value;
                sellSel.innerHTML = '<option value="">-- 手動輸入 --</option>';
                holdings.forEach(h => {
                    const opt = document.createElement('option');
                    opt.value = h.symbol;
                    opt.textContent = `${h.symbol} (${h.shares} shs @ $${Number(h.current_price || 0).toFixed(2)})`;
                    sellSel.appendChild(opt);
                });
                if (curVal) sellSel.value = curVal;
            }

            // 4. Populate Rebalance Holdings List
            const rebalContainer = document.getElementById('rebalance-holdings-list');
            if (rebalContainer && (!rebalContainer.children.length || rebalContainer.dataset.loadedCurrency !== currentCurrency)) {
                rebalContainer.dataset.loadedCurrency = currentCurrency;
                rebalContainer.innerHTML = '';
                const totalVal = currentPortfolioData ? Number(currentPortfolioData.total_value || 0) : 0;

                holdings.forEach((h) => {
                    const curWeight = totalVal > 0 ? ((Number(h.market_value || 0) / totalVal) * 100).toFixed(1) : '0.0';
                    const div = document.createElement('div');
                    div.className = 'item-card';
                    div.style.marginBottom = '8px';
                    div.id = `rebal-item-${h.symbol}`;
                    div.innerHTML = `
                        <div class="item-left" style="flex: 1;">
                            <strong>${h.symbol}</strong>
                            <div style="font-size: 0.72rem; color: var(--text-muted);">現值: $${Number(h.market_value || 0).toLocaleString(undefined, {maximumFractionDigits: 0})} (${curWeight}%)</div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <label style="font-size: 0.75rem; color: var(--text-muted);">目標%:</label>
                            <input type="number" step="0.5" class="form-control rebal-tgt-input" 
                                style="width: 72px; padding: 6px 8px; font-size: 0.84rem; text-align: right;" 
                                data-symbol="${h.symbol}" 
                                data-price="${h.current_price}" 
                                data-curval="${h.market_value}"
                                value="${curWeight}" 
                                oninput="runRebalanceCalc()">
                            <span class="pill item-badge rebal-action-badge" id="rebal-badge-${h.symbol}">-</span>
                        </div>
                    `;
                    rebalContainer.appendChild(div);
                });
            }

            runWhatIfCalc();
            runRebalanceCalc();
            runSplitCalc();
            runSellCalc();
        }

        // --- 1. WHAT-IF CALC ---
        function onWhatIfHoldingSelected(sym) {
            if (!sym || !currentPortfolioData || !currentPortfolioData.holdings) return;
            const h = currentPortfolioData.holdings.find(x => x.symbol === sym);
            if (h) {
                document.getElementById('whatif-ticker').value = h.symbol;
                document.getElementById('whatif-price').value = Number(h.current_price || 0).toFixed(2);
                const yld = (h.market_value > 0 && h.annual_dividend > 0) ? (h.annual_dividend / h.market_value * 100) : 1.5;
                document.getElementById('whatif-yield').value = yld.toFixed(2);
                runWhatIfCalc();
            }
        }

        function addWhatIfAmt(delta) {
            const el = document.getElementById('whatif-amt');
            el.value = (parseFloat(el.value) || 0) + delta;
            runWhatIfCalc();
        }

        function setWhatIfAmt(val) {
            document.getElementById('whatif-amt').value = val;
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
            document.getElementById('whatif-res-shares').textContent = `${shares.toFixed(2)} shs @ $${price.toFixed(2)}`;
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
                        badge.textContent = '✓ 持平 (HOLD)';
                        badge.className = 'pill item-badge blue';
                    } else if (diff > 0) {
                        badge.textContent = `買進 +${sym}${diff.toFixed(0)} (+${sharesDiff.toFixed(1)}shs)`;
                        badge.className = 'pill item-badge pos';
                    } else {
                        badge.textContent = `賣出 -${sym}${Math.abs(diff).toFixed(0)} (${sharesDiff.toFixed(1)}shs)`;
                        badge.className = 'pill item-badge neg';
                    }
                }
            });

            const totalEl = document.getElementById('rebal-total-weight');
            if (totalEl) {
                totalEl.textContent = `${sumW.toFixed(1)}% ` + (Math.abs(sumW - 100) < 0.2 ? '✓ 正常' : '⚠️ (未達100%)');
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

            const tbody = document.getElementById('drip-table-body');
            if (!tbody) return;
            tbody.innerHTML = '';

            const years = [1, 3, 5, 10, 15, 20, 25, 30];
            let accWealth = 0;
            let curDiv = initDiv;

            for (let y = 1; y <= 30; y++) {
                accWealth = (accWealth + curDiv + extra) * (1.0 + capR);
                curDiv = curDiv * (1.0 + divG);

                if (years.includes(y)) {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>第 ${y} 年</strong></td>
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

            document.getElementById('split-res-shares').textContent = `${newShs.toFixed(4)} shs`;
            document.getElementById('split-res-cost').textContent = `${sym}${newCost.toFixed(2)} / sh`;
            document.getElementById('split-res-total').textContent = `${sym}${tot.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (不變 ✓)`;
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
            document.getElementById('sell-res-rem-shares').textContent = `${remShs.toFixed(2)} shs`;
            document.getElementById('sell-res-rem-val').textContent = `${sym}${remVal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        }

        // --- 6. HEALTH CHECK & REPAIR ---
        async function scanDataHealth() {
            const sumEl = document.getElementById('health-summary');
            const detEl = document.getElementById('health-details');
            sumEl.textContent = '⏳ 正在檢查資料完整性...';
            detEl.textContent = '';
            try {
                const res = await fetch('/api/health');
                const data = await res.json();
                if (data.healthy || (data.total_issues === 0)) {
                    sumEl.textContent = '✅ 資料健康狀態良好 (100% 完整)';
                    sumEl.style.color = 'var(--accent-green)';
                    detEl.textContent = '已審核所有持倉與自選清單，無缺少成本、幣別不一致或異常代碼。';
                } else {
                    sumEl.textContent = `⚠️ 發現 ${data.total_issues || (data.issues || []).length} 項資料格式問題`;
                    sumEl.style.color = 'var(--accent-yellow)';
                    let msg = '';
                    (data.issues || []).forEach((iss, i) => {
                        msg += `${i+1}. [${iss.type || '異常'}] ${iss.desc || ''}\n`;
                    });
                    detEl.textContent = msg || '請點擊「一鍵修復異常」自動校正。';
                }
            } catch (err) {
                sumEl.textContent = '❌ 掃描失敗: ' + err.message;
                sumEl.style.color = 'var(--accent-red)';
            }
        }

        async function repairDataHealth() {
            const sumEl = document.getElementById('health-summary');
            const detEl = document.getElementById('health-details');
            sumEl.textContent = '⏳ 正在執行自動修復程序...';
            try {
                const res = await fetch('/api/repair', { method: 'POST' });
                const data = await res.json();
                sumEl.textContent = '✅ 資料修復完成！';
                sumEl.style.color = 'var(--accent-green)';
                detEl.textContent = `已修正資料問題，重新載入最新資料中...`;
                loadData();
                setTimeout(scanDataHealth, 800);
            } catch (err) {
                sumEl.textContent = '❌ 修復失敗: ' + err.message;
                sumEl.style.color = 'var(--accent-red)';
            }
        }

        // --- 7. REPORTS ---
        function openReportInView() {
            const wrap = document.getElementById('report-preview-wrap');
            const iframe = document.getElementById('report-iframe');
            wrap.style.display = 'block';
            iframe.src = `/api/report?currency=${currentCurrency}`;
        }

        // --- 8. STOP SERVER ---
        async function stopServerRemote() {
            if (confirm('確定要關閉 G_Finance 本地伺服器嗎？關閉後畫面將停止連線。')) {
                try {
                    await fetch('/api/stop', { method: 'POST' });
                    alert('伺服器正在停止，請手動關閉此分頁或 a-Shell 視窗。');
                } catch (e) {
                    alert('已發送停止指令。');
                }
            }
        }

        // Init
        window.addEventListener('DOMContentLoaded', () => {
            detectPlatform();
            loadData();
            // Auto refresh quotes every 45s
            setInterval(loadData, 45000);
        });

        // Register PWA Service Worker
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js').catch(err => console.log('SW registration skipped', err));
        }
    </script>
</body>
</html>
"""


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
                c = (h.get("currency") or "USD").upper()
                shares = float(h.get("shares", 0.0) or 0.0)
                price = float(h.get("current_price", h.get("price", 0.0)) or 0.0)
                buy_p = float(h.get("buy_price", 0.0) or 0.0)
                div = float(h.get("annual_dividend", 0.0) or 0.0)

                mv = shares * price
                cb = shares * buy_p

                mv_conv = converter.convert(mv, c, req_curr)
                cb_conv = converter.convert(cb, c, req_curr)
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

                pl = mv_conv - cb_conv
                roi = (pl / cb_conv * 100.0) if cb_conv > 0 else 0.0

                processed_holdings.append({
                    "symbol": sym,
                    "name": h.get("name", sym),
                    "shares": shares,
                    "current_price": converter.convert(price, c, req_curr),
                    "market_value": mv_conv,
                    "cost_basis": cb_conv,
                    "unrealized_pl": pl,
                    "roi_pct": roi,
                    "annual_dividend": div_conv,
                    "currency": req_curr,
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

        # 7. Watchlist API
        elif path == "/api/watchlist":
            watchlist = csv_manager.load_watchlist()
            self.send_json(watchlist)

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
                "watchlist": csv_manager.load_watchlist(),
            }
            json_bytes = json.dumps(backup, indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="g_finance_backup.json"')
            self.end_headers()
            self.wfile.write(json_bytes)

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/refresh":
            # Optional quote refresh
            self.send_json({"status": "success", "message": "Quotes refreshed"})
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

    def send_json(self, data: Any):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
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
    _SERVER_INSTANCE = HTTPServer((_HOST, _PORT), DashboardRequestHandler)
    _SERVER_THREAD = threading.Thread(target=_SERVER_INSTANCE.serve_forever, daemon=True)
    _SERVER_THREAD.start()
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

    if args.auto_view:
        _CLI_SERVER = HTTPServer((args.host, actual_port), DashboardRequestHandler)
        t = threading.Thread(target=_CLI_SERVER.serve_forever, daemon=True)
        t.start()
        time.sleep(0.4)
        target_url = f"http://localhost:{actual_port}"
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
            while t.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nStopping G_Finance server...")
            _CLI_SERVER.shutdown()
    else:
        _CLI_SERVER = HTTPServer((args.host, actual_port), DashboardRequestHandler)
        try:
            _CLI_SERVER.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping G_Finance server...")
            _CLI_SERVER.shutdown()
