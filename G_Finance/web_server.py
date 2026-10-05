"""
web_server.py
Embedded zero-dependency local web dashboard for Google Finance Portfolio Tracker.
Uses Python standard library http.server and threading.
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import socket
from typing import Optional, Callable
import csv_manager
import financial_calc

_SERVER_INSTANCE: Optional[HTTPServer] = None
_SERVER_THREAD: Optional[threading.Thread] = None
_PORT: int = 8765
_DATA_CALLBACK: Optional[Callable] = None


def find_free_port(start_port: int = 8765, max_attempts: int = 20) -> int:
    """Finds an open localhost port starting from start_port."""
    for p in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    return start_port


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>G_Finance Mobile & Web Dashboard</title>
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --border-color: #30363d;
            --text-primary: #c9d1d9;
            --text-secondary: #8b949e;
            --accent: #58a6ff;
            --green: #3fb950;
            --red: #f85149;
            --card-bg: #21262d;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1100px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 15px;
            margin-bottom: 25px;
        }
        h1 {
            margin: 0;
            font-size: 1.5rem;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .btn-refresh {
            background-color: var(--accent);
            color: #ffffff;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.9rem;
            transition: opacity 0.2s;
        }
        .btn-refresh:hover {
            opacity: 0.9;
        }
        .cards-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 16px;
        }
        .card-title {
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .card-value {
            font-size: 1.4rem;
            font-weight: 700;
        }
        .positive { color: var(--green); }
        .negative { color: var(--red); }
        .table-container {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            overflow-x: auto;
            margin-bottom: 30px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }
        th, td {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
        }
        th {
            background-color: var(--bg-secondary);
            color: var(--text-secondary);
            font-weight: 600;
        }
        tr:last-child td {
            border-bottom: none;
        }
        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            background-color: var(--border-color);
            color: var(--text-primary);
        }
        footer {
            text-align: center;
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-top: 30px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📈 Google Finance Portfolio Dashboard</h1>
            <div>
                <span id="last-updated" style="margin-right: 15px; font-size: 0.85rem; color: var(--text-secondary);"></span>
                <button class="btn-refresh" onclick="loadData()">🔄 Refresh</button>
            </div>
        </header>

        <div class="cards-grid">
            <div class="card">
                <div class="card-title">Total Portfolio Value</div>
                <div class="card-value" id="val-total">$0.00</div>
            </div>
            <div class="card">
                <div class="card-title">Unrealized P&L</div>
                <div class="card-value" id="val-pl">$0.00</div>
            </div>
            <div class="card">
                <div class="card-title">Est. Annual Dividend</div>
                <div class="card-value" id="val-div">$0.00</div>
            </div>
            <div class="card">
                <div class="card-title">Active Holdings</div>
                <div class="card-value" id="val-count">0</div>
            </div>
        </div>

        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Name</th>
                        <th>Sector</th>
                        <th>Shares</th>
                        <th>Current Price</th>
                        <th>Market Value</th>
                        <th>Unrealized P&L</th>
                        <th>Return %</th>
                        <th>Div. Yield</th>
                    </tr>
                </thead>
                <tbody id="holdings-body">
                    <tr><td colspan="9" style="text-align:center;">Loading holdings data...</td></tr>
                </tbody>
            </table>
        </div>

        <footer>
            Google Finance Local Dashboard &bull; Read-Only Localhost View
        </footer>
    </div>

    <script>
        async function loadData() {
            try {
                const res = await fetch('/api/portfolio');
                if (!res.ok) throw new Error('API returned ' + res.status);
                const data = await res.json();
                
                document.getElementById('last-updated').textContent = 'Updated: ' + new Date().toLocaleTimeString();
                document.getElementById('val-total').textContent = (data.currency || '$') + ' ' + (data.total_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                
                const pl = data.total_unrealized_pl || 0;
                const plEl = document.getElementById('val-pl');
                plEl.textContent = (pl >= 0 ? '+' : '') + (data.currency || '$') + ' ' + pl.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' (' + (data.overall_roi_pct || 0).toFixed(2) + '%)';
                plEl.className = 'card-value ' + (pl >= 0 ? 'positive' : 'negative');

                document.getElementById('val-div').textContent = (data.currency || '$') + ' ' + (data.total_annual_dividend || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                document.getElementById('val-count').textContent = (data.holdings || []).length;

                const tbody = document.getElementById('holdings-body');
                tbody.innerHTML = '';
                if (!data.holdings || data.holdings.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;">No holdings found.</td></tr>';
                    return;
                }

                data.holdings.forEach(h => {
                    const tr = document.createElement('tr');
                    const pl = h.unrealized_pl || 0;
                    const plClass = pl >= 0 ? 'positive' : 'negative';
                    const plSign = pl >= 0 ? '+' : '';
                    
                    tr.innerHTML = `
                        <td><strong>${h.symbol}</strong></td>
                        <td>${h.name || '-'}</td>
                        <td><span class="badge">${h.sector || 'Other'}</span></td>
                        <td>${(h.shares || 0).toLocaleString()}</td>
                        <td>$${(h.current_price || 0).toFixed(2)}</td>
                        <td>$${(h.market_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                        <td class="${plClass}">${plSign}$${pl.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                        <td class="${plClass}">${plSign}${(h.roi_pct || 0).toFixed(2)}%</td>
                        <td>${(h.dividend_yield || 0).toFixed(2)}%</td>
                    `;
                    tbody.appendChild(tr);
                });
            } catch (err) {
                console.error('Failed to load portfolio data:', err);
            }
        }

        window.onload = loadData;
        setInterval(loadData, 30000);
    </script>
</body>
</html>
"""


class DashboardRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging to console
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif self.path.startswith("/api/portfolio"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            # Retrieve data from callback or directly from csv_manager
            payload = {}
            if _DATA_CALLBACK:
                try:
                    payload = _DATA_CALLBACK()
                except Exception as ex:
                    payload = {"error": str(ex)}
            else:
                holdings = csv_manager.load_portfolio()
                metrics = financial_calc.calc_portfolio_metrics(holdings, base_currency="CAD", fx_rates={"USD": 1.35, "CAD": 1.0})
                payload = {
                    "currency": "CAD",
                    "total_value": metrics.get("total_market_value", 0.0),
                    "total_unrealized_pl": metrics.get("total_unrealized_pl", 0.0),
                    "overall_roi_pct": metrics.get("overall_roi_pct", 0.0),
                    "total_annual_dividend": metrics.get("total_annual_dividend", 0.0),
                    "holdings": holdings,
                    "sectors": metrics.get("sector_allocations", {})
                }
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def start_server(port: int = 8765, data_callback: Optional[Callable] = None) -> int:
    """Starts the HTTP server daemon on a free port."""
    global _SERVER_INSTANCE, _SERVER_THREAD, _PORT, _DATA_CALLBACK
    if is_running():
        return _PORT

    _PORT = find_free_port(port)
    _DATA_CALLBACK = data_callback
    _SERVER_INSTANCE = HTTPServer(('127.0.0.1', _PORT), DashboardRequestHandler)
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
    return f"http://127.0.0.1:{_PORT}"
