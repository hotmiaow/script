"""
Google Finance Style Interactive Chart Widget.
Supports dual rendering engines:
1. Matplotlib Mode: High-DPI anti-aliased vector rendering (when matplotlib is installed).
2. Pure Tkinter Canvas Fallback Mode: Zero-dependency native canvas renderer (works on ANY pc with only standard Python/tkinter).
Features:
- Area chart with soft gradient/fill and previous close reference line
- Dynamic hover crosshair & live tooltip updating header values
- Timeframe pills: 1D, 5D, 1M, 6M, YTD, 1Y, 5Y, MAX
- Portfolio aggregate and individual stock switching
- One-click package installer helper if packages are missing
"""

import sys
import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

# Check Matplotlib availability
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.pyplot as plt
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False

from chart_fetcher import get_chart_fetcher, YFINANCE_AVAILABLE


TF_DISPLAY_LABELS = {
    "1D": "Today",
    "5D": "Past 5 Days",
    "1M": "Past Month",
    "6M": "Past 6 Months",
    "YTD": "Year to Date",
    "1Y": "Past Year",
    "5Y": "Past 5 Years",
    "MAX": "All Time",
}


class GoogleFinanceChartView(ttk.Frame):
    def __init__(self, parent, get_holdings_callback, get_currency_converter_callback, default_currency="USD"):
        super().__init__(parent)
        self.get_holdings = get_holdings_callback
        self.get_converter = get_currency_converter_callback
        self.current_currency = default_currency
        self.current_timeframe = "1D"
        self.current_portfolio_name = "All Portfolios"
        self.current_scope = "portfolio"
        self.chart_type = "area"

        self.chart_data: Optional[Dict[str, Any]] = None
        self.is_loading = False
        self.is_running = True
        self.use_matplotlib = MATPLOTLIB_AVAILABLE

        self._build_ui()

    def _build_ui(self):
        # 1. Header Card (Title, Price, Change Badge, Subtitle)
        self.header_frame = tk.Frame(self, bg="#FFFFFF", padx=20, pady=10)
        self.header_frame.pack(fill=tk.X, side=tk.TOP)

        top_row = tk.Frame(self.header_frame, bg="#FFFFFF")
        top_row.pack(fill=tk.X)

        self.lbl_title = tk.Label(
            top_row,
            text="Portfolio Chart",
            font=("Segoe UI", 16, "bold"),
            bg="#FFFFFF",
            fg="#202124",
        )
        self.lbl_title.pack(side=tk.LEFT)

        # Engine Mode Indicator
        engine_txt = "📊 Matplotlib Mode" if self.use_matplotlib else "⚡ Native Canvas Mode (Zero Dependencies)"
        engine_fg = "#188038" if self.use_matplotlib else "#E37400"
        self.lbl_engine = tk.Label(
            top_row,
            text=engine_txt,
            font=("Segoe UI", 8, "bold"),
            bg="#FFFFFF",
            fg=engine_fg,
            padx=8,
        )
        self.lbl_engine.pack(side=tk.LEFT, padx=6)

        # Optional Install Button if packages missing
        if not (MATPLOTLIB_AVAILABLE and YFINANCE_AVAILABLE):
            self.btn_install_pkg = tk.Button(
                top_row,
                text="📦 Install Optional Packages",
                font=("Segoe UI", 8),
                bg="#FEF7E0",
                fg="#B06000",
                relief="solid",
                bd=1,
                padx=6,
                pady=1,
                cursor="hand2",
                command=self._prompt_install_packages,
            )
            self.btn_install_pkg.pack(side=tk.LEFT, padx=4)

        # Controls on top right (Scope selector, Chart Type, Refresh)
        ctrl_frame = tk.Frame(top_row, bg="#FFFFFF")
        ctrl_frame.pack(side=tk.RIGHT)

        tk.Label(ctrl_frame, text="View:", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#5F6368").pack(side=tk.LEFT, padx=(0, 4))
        self.scope_combo = ttk.Combobox(ctrl_frame, width=22, state="readonly")
        self.scope_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.scope_combo.bind("<<ComboboxSelected>>", self._on_scope_selected)

        tk.Label(ctrl_frame, text="Style:", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#5F6368").pack(side=tk.LEFT, padx=(0, 4))
        self.style_combo = ttk.Combobox(ctrl_frame, width=8, state="readonly", values=["Area", "Line"])
        self.style_combo.set("Area")
        self.style_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.style_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        self.btn_refresh = tk.Button(
            ctrl_frame,
            text="🔄 Refresh",
            font=("Segoe UI", 8, "bold"),
            bg="#F1F3F4",
            fg="#202124",
            relief="flat",
            padx=8,
            pady=2,
            command=self.refresh_chart,
        )
        self.btn_refresh.pack(side=tk.LEFT)

        # Price & Change Row
        price_row = tk.Frame(self.header_frame, bg="#FFFFFF")
        price_row.pack(fill=tk.X, pady=(4, 2))

        self.lbl_price = tk.Label(
            price_row,
            text="--",
            font=("Segoe UI", 26, "bold"),
            bg="#FFFFFF",
            fg="#202124",
        )
        self.lbl_price.pack(side=tk.LEFT, padx=(0, 12))

        self.lbl_badge = tk.Label(
            price_row,
            text="--",
            font=("Segoe UI", 12, "bold"),
            bg="#FFFFFF",
            fg="#137333",
            padx=8,
            pady=2,
        )
        self.lbl_badge.pack(side=tk.LEFT)

        # Subtitle (Time & Currency)
        self.lbl_subtitle = tk.Label(
            self.header_frame,
            text="Loading market data...",
            font=("Segoe UI", 9),
            bg="#FFFFFF",
            fg="#5F6368",
        )
        self.lbl_subtitle.pack(anchor="w")

        # 2. Chart Rendering Area
        self.canvas_frame = tk.Frame(self, bg="#FFFFFF")
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        if self.use_matplotlib:
            self._init_matplotlib_canvas()
        else:
            self._init_native_canvas()

        # 3. Timeframe Pills Bar (Bottom)
        self.pill_bar = tk.Frame(self, bg="#FFFFFF", pady=8, padx=20)
        self.pill_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.pills = {}
        for tf in ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"]:
            btn = tk.Button(
                self.pill_bar,
                text=tf,
                font=("Segoe UI", 9, "bold" if tf == "1D" else "normal"),
                bg="#E8F0FE" if tf == "1D" else "#FFFFFF",
                fg="#1A73E8" if tf == "1D" else "#5F6368",
                activebackground="#D2E3FC",
                relief="flat",
                bd=0,
                padx=12,
                pady=4,
                cursor="hand2",
                command=lambda t=tf: self._select_timeframe(t),
            )
            btn.pack(side=tk.LEFT, padx=3)
            self.pills[tf] = btn

    # -------------------------------------------------------------
    # Matplotlib Engine
    # -------------------------------------------------------------
    def _init_matplotlib_canvas(self):
        self.fig, self.ax = plt.subplots(figsize=(8, 4), dpi=100)
        self.fig.patch.set_facecolor("#FFFFFF")
        self.ax.set_facecolor("#FFFFFF")
        self.fig.tight_layout(pad=2.0)

        self.mpl_canvas = FigureCanvasTkAgg(self.fig, master=self.canvas_frame)
        self.mpl_widget = self.mpl_canvas.get_tk_widget()
        self.mpl_widget.pack(fill=tk.BOTH, expand=True)

        self.mpl_canvas.mpl_connect("motion_notify_event", self._on_mpl_hover)
        self.mpl_canvas.mpl_connect("figure_leave_event", self._on_leave)

    # -------------------------------------------------------------
    # Pure Tkinter Canvas Fallback Engine (Zero Dependencies)
    # -------------------------------------------------------------
    def _init_native_canvas(self):
        self.native_canvas = tk.Canvas(self.canvas_frame, bg="#FFFFFF", highlightthickness=0)
        self.native_canvas.pack(fill=tk.BOTH, expand=True)
        self.native_canvas.bind("<Configure>", lambda e: self._render_native_chart(self.chart_data))
        self.native_canvas.bind("<Motion>", self._on_native_hover)
        self.native_canvas.bind("<Leave>", self._on_leave)
        self.canvas_points = []

    def _select_timeframe(self, tf: str):
        if self.current_timeframe == tf:
            return
        self.current_timeframe = tf

        for t, btn in self.pills.items():
            if t == tf:
                btn.config(bg="#E8F0FE", fg="#1A73E8", font=("Segoe UI", 9, "bold"))
            else:
                btn.config(bg="#FFFFFF", fg="#5F6368", font=("Segoe UI", 9, "normal"))

        self.refresh_chart()

    def _on_style_changed(self, event=None):
        style = self.style_combo.get().strip().lower()
        self.chart_type = "line" if style == "line" else "area"
        if self.chart_data:
            self._render_chart(self.chart_data)

    def _on_scope_selected(self, event=None):
        val = self.scope_combo.get().strip()
        if not val:
            return
        if val.startswith("📁 Portfolio:"):
            self.current_scope = "portfolio"
        else:
            sym = val.split(" - ")[0].strip()
            self.current_scope = sym
        self.refresh_chart()

    def update_portfolio(self, portfolio_name: str, target_currency: str = "USD"):
        self.current_portfolio_name = portfolio_name
        self.current_currency = target_currency
        self._populate_scope_dropdown()
        self.refresh_chart()

    def _populate_scope_dropdown(self):
        holdings = self.get_holdings(self.current_portfolio_name)
        values = [f"📁 Portfolio: {self.current_portfolio_name}"]
        seen_syms = set()
        for h in holdings:
            sym = str(h.get("symbol", "")).strip()
            if not sym:
                continue
            sym_key = sym.upper()
            if sym_key in seen_syms:
                continue
            seen_syms.add(sym_key)
            name = h.get("name", "")
            display = f"{sym} - {name}" if name else sym
            values.append(display)

        self.scope_combo.config(values=values)
        matched_idx = None
        if self.current_scope != "portfolio":
            for idx, v in enumerate(values):
                if v == self.current_scope or v.startswith(f"{self.current_scope} - "):
                    matched_idx = idx
                    break

        if matched_idx is not None:
            self.scope_combo.current(matched_idx)
        else:
            self.scope_combo.current(0)
            self.current_scope = "portfolio"

    def cleanup(self):
        self.is_running = False
        self.is_loading = False

    def refresh_chart(self):
        if not getattr(self, "is_running", True):
            return
        if self.is_loading:
            return
        self.is_loading = True
        self.lbl_subtitle.config(text="Fetching latest chart data...")

        threading.Thread(target=self._fetch_and_render_thread, daemon=True).start()

    def _fetch_and_render_thread(self):
        if not getattr(self, "is_running", True):
            return
        fetcher = get_chart_fetcher()
        converter = self.get_converter()

        data = None
        if self.current_scope == "portfolio":
            holdings = self.get_holdings(self.current_portfolio_name)
            data = fetcher.fetch_portfolio_history(
                holdings=holdings,
                portfolio_name=self.current_portfolio_name,
                timeframe=self.current_timeframe,
                converter=converter,
                target_currency=self.current_currency,
            )
        else:
            data = fetcher.fetch_symbol_history(self.current_scope, self.current_timeframe)

        if not getattr(self, "is_running", True):
            return
        self.chart_data = data
        self.is_loading = False
        try:
            if self.winfo_exists():
                self.after(0, lambda: self._safe_render_chart(data))
        except Exception:
            pass

    def _safe_render_chart(self, data: Optional[Dict[str, Any]]):
        try:
            if self.winfo_exists():
                self._render_chart(data)
        except Exception:
            pass

    def _render_chart(self, data: Optional[Dict[str, Any]]):
        if self.use_matplotlib:
            self._render_matplotlib_chart(data)
        else:
            self._render_native_chart(data)

    # -------------------------------------------------------------
    # Matplotlib Renderer Implementation
    # -------------------------------------------------------------
    def _render_matplotlib_chart(self, data: Optional[Dict[str, Any]]):
        self.ax.clear()

        if not data or not data.get("prices"):
            self._set_empty_state()
            self.mpl_canvas.draw()
            return

        prices = data["prices"]
        timestamps = data["timestamps"]
        prev_close = data.get("prev_close", prices[0])
        curr_price = prices[-1]
        change = curr_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0.0

        curr_sym = "$" if data.get("currency") in ("USD", "CAD") else (data.get("currency") + " ")
        self._update_header(curr_price, change, change_pct, curr_sym, data.get("currency", "USD"))

        line_color = "#1A73E8"
        fill_color = "#E8F0FE"

        x = range(len(prices))
        self.plot_x = list(x)
        self.plot_prices = prices
        self.plot_timestamps = timestamps
        self.plot_prev_close = prev_close
        self.plot_currency = curr_sym

        self.ax.plot(x, prices, color=line_color, linewidth=2.0, antialiased=True)

        if self.chart_type == "area":
            min_y = min(prices)
            base_y = min_y - (max(prices) - min_y) * 0.05 if max(prices) > min_y else min_y * 0.95
            self.ax.fill_between(x, prices, base_y, color=fill_color, alpha=0.7)

        if prev_close and prev_close > 0:
            self.ax.axhline(prev_close, color="#9AA0A6", linestyle=":", linewidth=1.2)
            self.ax.text(
                len(prices) - 1,
                prev_close,
                f" Prev. close {curr_sym}{prev_close:,.2f}",
                color="#5F6368",
                fontsize=8,
                va="center",
                ha="left",
                fontweight="bold",
            )

        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        self.ax.spines["left"].set_color("#E0E0E0")
        self.ax.spines["bottom"].set_color("#E0E0E0")
        self.ax.grid(True, axis="y", color="#F1F3F4", linestyle="-", linewidth=1.0)
        self.ax.tick_params(axis="both", colors="#5F6368", labelsize=8)

        # X-axis
        n_ticks = 5
        indices = np.linspace(0, len(prices) - 1, n_ticks, dtype=int)
        labels = []
        for idx in indices:
            ts = timestamps[idx]
            if self.current_timeframe in ("1D", "5D"):
                labels.append(ts.strftime("%H:%M" if self.current_timeframe == "1D" else "%a %H:%M"))
            elif self.current_timeframe in ("1M", "6M", "YTD"):
                labels.append(ts.strftime("%b %d"))
            else:
                labels.append(ts.strftime("%b %Y"))

        self.ax.set_xticks(indices)
        self.ax.set_xticklabels(labels)

        # Y-axis
        y_min, y_max = min(prices), max(prices)
        if prev_close:
            y_min = min(y_min, prev_close)
            y_max = max(y_max, prev_close)
        margin = (y_max - y_min) * 0.1 if y_max > y_min else y_max * 0.05
        self.ax.set_ylim(y_min - margin, y_max + margin)
        self.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda val, pos: f"{curr_sym}{val:,.0f}"))

        self.fig.tight_layout(pad=2.0)
        self.mpl_canvas.draw()

    # -------------------------------------------------------------
    # Pure Tkinter Canvas Renderer Implementation (Zero Dependencies)
    # -------------------------------------------------------------
    def _render_native_chart(self, data: Optional[Dict[str, Any]]):
        if not hasattr(self, "native_canvas"):
            return

        self.native_canvas.delete("all")
        w = self.native_canvas.winfo_width()
        h = self.native_canvas.winfo_height()
        if w < 100 or h < 80:
            return

        if not data or not data.get("prices"):
            self._set_empty_state()
            self.native_canvas.create_text(w // 2, h // 2, text="Market data unavailable for selected range", fill="#5F6368", font=("Segoe UI", 11))
            return

        prices = data["prices"]
        timestamps = data["timestamps"]
        prev_close = data.get("prev_close", prices[0])
        curr_price = prices[-1]
        change = curr_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0.0

        curr_sym = "$" if data.get("currency") in ("USD", "CAD") else (data.get("currency") + " ")
        self._update_header(curr_price, change, change_pct, curr_sym, data.get("currency", "USD"))

        pad_l, pad_r, pad_t, pad_b = 65, 120, 20, 30
        plot_w = w - pad_l - pad_r
        plot_h = h - pad_t - pad_b

        y_min, y_max = min(prices), max(prices)
        if prev_close:
            y_min = min(y_min, prev_close)
            y_max = max(y_max, prev_close)
        y_range = y_max - y_min if y_max > y_min else 1.0

        # Draw horizontal gridlines and Y-axis labels
        n_y_grid = 4
        for i in range(n_y_grid + 1):
            val = y_min + (i / n_y_grid) * y_range
            gy = pad_t + plot_h - (i / n_y_grid) * plot_h
            self.native_canvas.create_line(pad_l, gy, pad_l + plot_w, gy, fill="#F1F3F4", width=1)
            self.native_canvas.create_text(pad_l - 8, gy, text=f"{curr_sym}{val:,.0f}", anchor="e", fill="#5F6368", font=("Segoe UI", 8))

        # Calculate coordinates
        n_pts = len(prices)
        coords = []
        self.canvas_points = []
        for i, (ts, pr) in enumerate(zip(timestamps, prices)):
            cx = pad_l + (i / (n_pts - 1)) * plot_w if n_pts > 1 else pad_l + plot_w // 2
            cy = pad_t + plot_h - ((pr - y_min) / y_range) * plot_h
            coords.extend([cx, cy])
            self.canvas_points.append((cx, cy, pr, ts))

        # Area polygon fill
        if self.chart_type == "area" and len(coords) >= 4:
            poly_coords = [coords[0], pad_t + plot_h] + coords + [coords[-2], pad_t + plot_h]
            self.native_canvas.create_polygon(poly_coords, fill="#E8F0FE", outline="")

        # Main curve line
        if len(coords) >= 4:
            self.native_canvas.create_line(coords, fill="#1A73E8", width=2)

        # Previous close dotted line
        if prev_close and y_min <= prev_close <= y_max:
            prev_y = pad_t + plot_h - ((prev_close - y_min) / y_range) * plot_h
            self.native_canvas.create_line(pad_l, prev_y, pad_l + plot_w, prev_y, fill="#9AA0A6", dash=(4, 4), width=1)
            self.native_canvas.create_text(
                pad_l + plot_w + 6,
                prev_y,
                text=f"Prev. close {curr_sym}{prev_close:,.2f}",
                anchor="w",
                fill="#5F6368",
                font=("Segoe UI", 8, "bold"),
            )

        # X-axis time ticks
        n_x_ticks = min(5, n_pts)
        step = max(1, (n_pts - 1) // (n_x_ticks - 1)) if n_x_ticks > 1 else 1
        for i in range(0, n_pts, step):
            cx = pad_l + (i / (n_pts - 1)) * plot_w if n_pts > 1 else pad_l + plot_w // 2
            ts = timestamps[i]
            if self.current_timeframe in ("1D", "5D"):
                lbl = ts.strftime("%H:%M" if self.current_timeframe == "1D" else "%a %H:%M")
            elif self.current_timeframe in ("1M", "6M", "YTD"):
                lbl = ts.strftime("%b %d")
            else:
                lbl = ts.strftime("%b %Y")
            self.native_canvas.create_text(cx, pad_t + plot_h + 15, text=lbl, fill="#5F6368", font=("Segoe UI", 8))

    def _update_header(self, curr_price: float, change: float, change_pct: float, curr_sym: str, currency: str):
        title_text = self.current_portfolio_name if self.current_scope == "portfolio" else self.current_scope
        self.lbl_title.config(text=title_text)
        self.lbl_price.config(text=f"{curr_sym}{curr_price:,.2f}")

        is_positive = change >= 0
        sign_char = "▲ +" if is_positive else "▼ -"
        badge_color = "#137333" if is_positive else "#C5221F"
        badge_bg = "#E6F4EA" if is_positive else "#FCE8E6"
        tf_label = TF_DISPLAY_LABELS.get(self.current_timeframe, "Today")

        self.lbl_badge.config(
            text=f"{sign_char}{abs(change_pct):.2f}% ({sign_char[2:]}{curr_sym}{abs(change):,.2f}) {tf_label}",
            fg=badge_color,
            bg=badge_bg,
        )

        now_utc = datetime.now(timezone.utc).strftime("%d %b, %H:%M:%S UTC")
        self.lbl_subtitle.config(text=f"{now_utc} · {currency}")

    def _set_empty_state(self):
        self.lbl_title.config(text=self.current_portfolio_name if self.current_scope == "portfolio" else self.current_scope)
        self.lbl_price.config(text="No Data Available")
        self.lbl_badge.config(text="")
        self.lbl_subtitle.config(text="Market data is unavailable for the selected range.")

    # -------------------------------------------------------------
    # Interactive Hover Crosshairs
    # -------------------------------------------------------------
    def _on_mpl_hover(self, event):
        if not hasattr(self, "plot_prices") or not self.plot_prices:
            return
        if event.inaxes != self.ax or event.xdata is None:
            return

        x_idx = int(round(event.xdata))
        if 0 <= x_idx < len(self.plot_prices):
            hover_price = self.plot_prices[x_idx]
            hover_time = self.plot_timestamps[x_idx]
            prev = self.plot_prev_close
            self._update_hover_header(hover_price, hover_time, prev, getattr(self, "plot_currency", "$"))

    def _on_native_hover(self, event):
        if not hasattr(self, "canvas_points") or not self.canvas_points or not self.chart_data:
            return

        mx, my = event.x, event.y
        # Find closest point
        closest = min(self.canvas_points, key=lambda pt: abs(pt[0] - mx))
        cx, cy, pr, ts = closest

        # Draw vertical crosshair & highlight dot
        self.native_canvas.delete("hover_marker")
        h = self.native_canvas.winfo_height()
        self.native_canvas.create_line(cx, 20, cx, h - 30, fill="#1A73E8", dash=(2, 2), tags="hover_marker")
        self.native_canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#1A73E8", outline="#FFFFFF", width=2, tags="hover_marker")

        prev = self.chart_data.get("prev_close", pr)
        curr_sym = "$" if self.chart_data.get("currency") in ("USD", "CAD") else (self.chart_data.get("currency", "") + " ")
        self._update_hover_header(pr, ts, prev, curr_sym)

    def _update_hover_header(self, hover_price: float, hover_time: datetime, prev: float, curr_sym: str):
        change = hover_price - prev
        change_pct = (change / prev * 100) if prev > 0 else 0.0
        is_pos = change >= 0
        sign = "▲ +" if is_pos else "▼ -"
        badge_color = "#137333" if is_pos else "#C5221F"
        badge_bg = "#E6F4EA" if is_pos else "#FCE8E6"
        time_fmt = hover_time.strftime("%d %b, %H:%M:%S") if self.current_timeframe in ("1D", "5D") else hover_time.strftime("%d %b %Y")

        self.lbl_price.config(text=f"{curr_sym}{hover_price:,.2f}")
        self.lbl_badge.config(
            text=f"{sign}{abs(change_pct):.2f}% ({sign[2:]}{curr_sym}{abs(change):,.2f}) at {time_fmt}",
            fg=badge_color,
            bg=badge_bg,
        )

    def _on_leave(self, event):
        if hasattr(self, "native_canvas"):
            self.native_canvas.delete("hover_marker")

        if self.chart_data:
            prices = self.chart_data.get("prices", [])
            if prices:
                curr_price = prices[-1]
                prev = self.chart_data.get("prev_close", curr_price)
                change = curr_price - prev
                change_pct = (change / prev * 100) if prev > 0 else 0.0
                curr_sym = "$" if self.chart_data.get("currency") in ("USD", "CAD") else (self.chart_data.get("currency", "") + " ")
                self._update_header(curr_price, change, change_pct, curr_sym, self.chart_data.get("currency", "USD"))

    # -------------------------------------------------------------
    # Package Installation Helper
    # -------------------------------------------------------------
    def _prompt_install_packages(self):
        msg = (
            "Enhanced vector charting benefits from 'matplotlib' and 'yfinance'.\n\n"
            "Would you like to install them now via pip?\n"
            "Command: pip install matplotlib yfinance pandas"
        )
        if messagebox.askyesno("Install Packages", msg, parent=self):
            threading.Thread(target=self._run_pip_install, daemon=True).start()

    def _run_pip_install(self):
        self.lbl_subtitle.config(text="Installing matplotlib and yfinance in background...")
        try:
            cmd = [sys.executable, "-m", "pip", "install", "matplotlib", "yfinance", "pandas"]
            subprocess.run(cmd, check=True, capture_output=True)
            messagebox.showinfo("Success", "Packages installed successfully! Please restart the app for enhanced mode.", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"Installation failed: {e}\nYou can install manually by running:\npip install matplotlib yfinance pandas", parent=self)
