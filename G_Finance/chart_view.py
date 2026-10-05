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
from typing import Dict, List, Any, Optional, Tuple
from i18n import t
from financial_calc import calc_dividend_frequency

import warnings
# Ignore Matplotlib missing glyph user warnings for CJK / currency symbols
warnings.filterwarnings("ignore", message=r".*Glyph.*missing from font.*")

# Check Matplotlib availability
try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.font_manager as fm
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.pyplot as plt
    import numpy as np

    # Auto-register local CJK fonts if available
    cjk_font_paths = [
        "/usr/share/fonts/google-noto-sans-cjk-vf-fonts/NotoSansCJK-VF.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ]
    for fp in cjk_font_paths:
        if os.path.exists(fp):
            try:
                fm.fontManager.addfont(fp)
            except Exception:
                pass

    # Configure CJK fallback font family priorities
    CJK_FONTS = [
        "Noto Sans CJK TC",
        "Noto Sans CJK SC",
        "Noto Sans CJK HK",
        "Noto Sans TC",
        "Noto Sans SC",
        "Droid Sans Fallback",
        "Microsoft JhengHei",
        "Microsoft YaHei",
        "SimHei",
        "PingFang TC",
        "PingFang SC",
        "Hiragino Sans GB",
        "WenQuanYi Micro Hei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    existing_sans = list(matplotlib.rcParams.get("font.sans-serif", []))
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = CJK_FONTS + [f for f in existing_sans if f not in CJK_FONTS]
    matplotlib.rcParams["axes.unicode_minus"] = False

    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False

from chart_fetcher import get_chart_fetcher, YFINANCE_AVAILABLE


def get_tf_display_label(tf: str) -> str:
    key_map = {
        "1D": "tf_today",
        "5D": "tf_past_5d",
        "1M": "tf_past_1m",
        "6M": "tf_past_6m",
        "YTD": "tf_ytd",
        "1Y": "tf_past_1y",
        "5Y": "tf_past_5y",
        "MAX": "tf_all_time",
    }
    k = key_map.get(tf)
    if k:
        return t(k)
    return tf


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
        self.chart_metric = "total"
        self.current_benchmark = "none"
        self.benchmark_symbol = ""
        self.benchmark_data: Optional[Dict[str, Any]] = None
        self.ax2 = None

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
            text=t("lbl_portfolio_chart"),
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
                text=t("btn_install_packages"),
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

        self.lbl_chart_view = tk.Label(ctrl_frame, text=t("lbl_chart_view"), font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#5F6368")
        self.lbl_chart_view.pack(side=tk.LEFT, padx=(0, 4))
        self.scope_combo = ttk.Combobox(ctrl_frame, width=22, state="readonly")
        self.scope_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.scope_combo.bind("<<ComboboxSelected>>", self._on_scope_selected)

        self.lbl_chart_metric = tk.Label(ctrl_frame, text=t("lbl_chart_metric"), font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#5F6368")
        self.lbl_chart_metric.pack(side=tk.LEFT, padx=(0, 4))
        self.metric_combo = ttk.Combobox(
            ctrl_frame,
            width=24,
            state="readonly",
            values=[
                t("chart_metric_total"),
                t("chart_metric_price"),
                t("chart_metric_growth"),
                t("chart_metric_growth_div"),
                t("chart_metric_div_only"),
            ],
        )
        self.metric_combo.set(t("chart_metric_total"))
        self.metric_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.metric_combo.bind("<<ComboboxSelected>>", self._on_metric_changed)

        self.lbl_chart_style = tk.Label(ctrl_frame, text=t("lbl_chart_style"), font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#5F6368")
        self.lbl_chart_style.pack(side=tk.LEFT, padx=(0, 4))
        self.style_combo = ttk.Combobox(ctrl_frame, width=8, state="readonly", values=[t("chart_style_area"), t("chart_style_line")])
        self.style_combo.set(t("chart_style_area"))
        self.style_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.style_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        self.lbl_benchmark = tk.Label(ctrl_frame, text=t("lbl_benchmark"), font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#5F6368")
        self.lbl_benchmark.pack(side=tk.LEFT, padx=(0, 4))
        self.benchmark_combo = ttk.Combobox(
            ctrl_frame,
            width=16,
            state="readonly",
            values=[t("bm_none"), t("bm_sp500"), t("bm_tsx60")]
        )
        self.benchmark_combo.set(t("bm_none"))
        self.benchmark_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.benchmark_combo.bind("<<ComboboxSelected>>", self._on_benchmark_changed)

        self.btn_refresh = tk.Button(
            ctrl_frame,
            text=t("btn_refresh"),
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

    def _on_metric_changed(self, event=None):
        val = self.metric_combo.get().strip()
        div_only_match = (
            val in (t("chart_metric_div_only"), "Dividends Only", "僅累積股息分派", "仅累积股息分派")
            or "only" in val.lower()
            or "僅" in val
            or "仅" in val
        )
        price_match = (
            val in (t("chart_metric_price"), "Stock Price (Per Share)", "股價 (每股)", "股价 (每股)")
            or "price" in val.lower()
            or ("股價" in val or "股价" in val)
        )
        growth_match = (
            val in (t("chart_metric_growth"), "Net Growth / P&L (Excl. Invested)", "淨增長 / 盈虧 (扣除本金)", "净增长 / 盈亏 (扣除本金)")
            or "excl" in val.lower()
            or "扣除" in val
        )
        growth_div_match = (
            val in (t("chart_metric_growth_div"), "Net Growth + Dividends", "淨增長 + 累積股息分派", "净增长 + 累积股息分派")
            or "+" in val
            or "growth" in val.lower()
        )

        if div_only_match:
            self.chart_metric = "div_only"
        elif price_match:
            self.chart_metric = "price"
        elif growth_div_match:
            self.chart_metric = "growth_div"
        elif growth_match:
            self.chart_metric = "growth"
        else:
            self.chart_metric = "total"

        if self.chart_data:
            self._render_chart(self.chart_data)

    def _on_benchmark_changed(self, event=None):
        val = self.benchmark_combo.get()
        if t("bm_sp500") in val or "500" in val or "SPY" in val or "標普" in val or "标普" in val:
            self.current_benchmark = "sp500"
            self.benchmark_symbol = "SPY"
        elif t("bm_tsx60") in val or "60" in val or "XIU" in val or "多倫多" in val or "多伦多" in val:
            self.current_benchmark = "tsx60"
            self.benchmark_symbol = "XIU.TO"
        else:
            self.current_benchmark = "none"
            self.benchmark_symbol = ""
            self.benchmark_data = None
        self.refresh_chart()

    def _get_scope_invested_and_div(self, target_currency: Optional[str] = None) -> Tuple[float, float, float, float]:
        holdings = self.get_holdings(self.current_portfolio_name) if callable(getattr(self, "get_holdings", None)) else []
        holdings = holdings or []
        converter = self.get_converter() if callable(getattr(self, "get_converter", None)) else None
        total_cb = 0.0
        total_div = 0.0
        total_shares = 0.0
        total_rate = 1.0

        if self.current_scope == "portfolio":
            chart_curr = (target_currency or self.current_currency).strip().upper()
            for h in holdings:
                shares = float(h.get("shares", 0.0) or 0.0)
                bp = float(h.get("buy_price", 0.0) or 0.0)
                cb = float(h.get("cost_basis", 0.0) or (shares * bp))
                curr = (h.get("currency", "USD") or "USD").strip().upper()
                rate = converter.convert(1.0, curr, chart_curr) if converter else 1.0
                total_cb += cb * rate
                ann_d = float(h.get("annual_dividend", 0.0) or 0.0)
                total_div += ann_d * rate
            total_shares = 1.0
            total_rate = 1.0
        else:
            matching = [h for h in holdings if str(h.get("symbol", "")).strip().upper() == self.current_scope.strip().upper()]
            holding_curr = (matching[0].get("currency") if matching and matching[0].get("currency") else self.current_currency).strip().upper()
            chart_curr = (target_currency or holding_curr).strip().upper()
            for h in matching:
                shares = float(h.get("shares", 0.0) or 0.0)
                bp = float(h.get("buy_price", 0.0) or 0.0)
                cb = float(h.get("cost_basis", 0.0) or (shares * bp))
                curr = (h.get("currency", "USD") or "USD").strip().upper()
                rate = converter.convert(1.0, curr, chart_curr) if converter else 1.0
                total_shares += shares
                total_cb += cb * rate
                ann_d = float(h.get("annual_dividend", 0.0) or 0.0)
                total_div += ann_d * rate
                total_rate = rate

        return total_cb, total_div, total_shares, total_rate

    def _prepare_metric_series(self, data: Dict[str, Any]):
        raw_prices = data.get("prices", [])
        raw_timestamps = data.get("timestamps", [])
        raw_prev = data.get("prev_close") or data.get("previous_close") or (raw_prices[0] if raw_prices else 0.0)
        data_currency = (data.get("currency") or "USD").strip().upper()

        is_single_stock = getattr(self, "current_scope", "portfolio") != "portfolio"
        target_curr = data_currency if is_single_stock else getattr(self, "current_currency", "USD")

        try:
            scope_res = self._get_scope_invested_and_div(target_currency=target_curr)
        except TypeError:
            scope_res = self._get_scope_invested_and_div()

        if len(scope_res) == 4:
            total_cb, total_div, total_shares, total_rate = scope_res
        elif len(scope_res) == 3:
            total_cb, total_div, total_shares = scope_res
            total_rate = 1.0
        else:
            total_cb, total_div = scope_res
            total_shares = 1.0
            total_rate = 1.0

        scale_factor = (total_shares * total_rate) if (is_single_stock and total_shares > 0) else 1.0

        self.current_scope_shares = total_shares
        self.current_scope_scale = scale_factor
        self.current_scope_rate = total_rate
        self.current_scope_currency = target_curr

        # Fallback to data's annual dividend per share if holding dividend was 0.0
        data_ann_div = float(data.get("annual_dividend_per_share", 0.0) or 0.0)
        if total_div <= 0.0 and data_ann_div > 0 and total_shares > 0:
            total_div = round(data_ann_div * total_shares * total_rate, 2)

        tf = self.current_timeframe
        tf_mult = {
            "1D": 1.0 / 252.0,
            "5D": 5.0 / 252.0,
            "1M": 1.0 / 12.0,
            "6M": 0.5,
            "YTD": datetime.now().timetuple().tm_yday / 365.0,
            "1Y": 1.0,
            "5Y": 5.0,
            "MAX": 5.0,
        }.get(tf, 1.0)

        n_pts = len(raw_prices)
        div_events = data.get("dividend_events", [])
        if div_events and raw_timestamps and is_single_stock and total_shares > 0:
            start_ts = raw_timestamps[0]
            start_dt = start_ts if getattr(start_ts, "tzinfo", None) else start_ts.replace(tzinfo=timezone.utc)
            start_date = start_dt.date() if hasattr(start_dt, "date") else start_dt

            # Only include dividend events that occurred within the selected timeframe (on or after start_date)
            tf_div_events = []
            for dt, amt in div_events:
                d_dt = dt if getattr(dt, "tzinfo", None) else dt.replace(tzinfo=timezone.utc)
                d_date = d_dt.date() if hasattr(d_dt, "date") else d_dt
                if d_date >= start_date:
                    tf_div_events.append((d_dt, amt))

            # Construct cumulative dividend series from real dividend events
            div_series = []
            for ts in raw_timestamps:
                ts_comp = ts if getattr(ts, "tzinfo", None) else ts.replace(tzinfo=timezone.utc)
                cum_div = sum(
                    amt for dt, amt in tf_div_events
                    if dt <= ts_comp
                )
                div_series.append(round(cum_div * total_shares * total_rate, 2))
            timeframe_div = div_series[-1] if div_series else 0.0
            if timeframe_div == 0.0 and total_div > 0 and tf not in ("1D", "5D"):
                timeframe_div = round(total_div * tf_mult, 2)
                div_series = [round(timeframe_div * (i / max(1, n_pts - 1)), 2) for i in range(n_pts)]
        else:
            timeframe_div = round(total_div * tf_mult, 2)
            div_series = [round(timeframe_div * (i / max(1, n_pts - 1)), 2) for i in range(n_pts)]

        mode = getattr(self, "chart_metric", "total")
        curr_sym = "$" if target_curr in ("USD", "CAD") else (target_curr + " ")

        if mode == "growth":
            # Exclude money invested: Net growth / profit only (scaled to total holding size)
            prices = [round(p * scale_factor - total_cb, 2) for p in raw_prices]
            prev_close = 0.0
            curr_val = prices[-1] if prices else 0.0
            gain_pct = (curr_val / total_cb * 100) if total_cb > 0 else 0.0
            is_pos = curr_val >= 0
            line_color = "#188038" if is_pos else "#D93025"
            fill_color = "#E6F4EA" if is_pos else "#FCE8E6"
            ref_label = f" {t('chart_invested_capital')}{curr_sym}{total_cb:,.2f}"
            return prices, raw_timestamps, prev_close, curr_val, gain_pct, line_color, fill_color, True, ref_label, total_cb, timeframe_div
        elif mode == "growth_div":
            # Net growth + cumulative dividends
            prices = [round((p * scale_factor - total_cb) + d, 2) for p, d in zip(raw_prices, div_series)]
            prev_close = 0.0
            curr_val = prices[-1] if prices else 0.0
            ret_pct = (curr_val / total_cb * 100) if total_cb > 0 else 0.0
            is_pos = curr_val >= 0
            line_color = "#188038" if is_pos else "#D93025"
            fill_color = "#E6F4EA" if is_pos else "#FCE8E6"
            ref_label = f" {t('chart_invested_capital')}{curr_sym}{total_cb:,.2f}"
            return prices, raw_timestamps, prev_close, curr_val, ret_pct, line_color, fill_color, True, ref_label, total_cb, timeframe_div
        elif mode == "div_only":
            prices = div_series
            prev_close = 0.0
            curr_val = prices[-1] if prices else 0.0
            div_pct = (curr_val / total_cb * 100) if total_cb > 0 else 0.0
            line_color = "#1A73E8"
            fill_color = "#E8F0FE"
            ref_label = f" {curr_sym}0.00"
            return prices, raw_timestamps, prev_close, curr_val, div_pct, line_color, fill_color, True, ref_label, total_cb, timeframe_div
        elif mode == "price":
            # Per-share stock price quote (unscaled by holding shares)
            prices = raw_prices
            prev_close = raw_prev
            curr_val = prices[-1] if prices else 0.0
            change = curr_val - prev_close
            change_pct = (change / prev_close * 100) if prev_close > 0 else 0.0
            is_pos = change >= 0
            line_color = "#188038" if is_pos else "#D93025"
            fill_color = "#E6F4EA" if is_pos else "#FCE8E6"
            ref_label = f" Prev. close {curr_sym}{prev_close:,.2f}"
            return prices, raw_timestamps, prev_close, change, change_pct, line_color, fill_color, False, ref_label, total_cb, timeframe_div
        else:
            # Standard Total Value mode (scaled to position market value if single stock holding)
            prices = [round(p * scale_factor, 2) for p in raw_prices] if scale_factor != 1.0 else raw_prices
            prev_close = round(raw_prev * scale_factor, 2) if scale_factor != 1.0 else raw_prev
            curr_val = prices[-1] if prices else 0.0
            change = curr_val - prev_close
            change_pct = (change / prev_close * 100) if prev_close > 0 else 0.0
            is_pos = change >= 0
            line_color = "#188038" if is_pos else "#D93025"
            fill_color = "#E6F4EA" if is_pos else "#FCE8E6"
            ref_label = f" Prev. close {curr_sym}{prev_close:,.2f}"
            return prices, raw_timestamps, prev_close, change, change_pct, line_color, fill_color, False, ref_label, total_cb, timeframe_div

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
        self.lbl_subtitle.config(text=t("msg_fetching_chart_data"))

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

        if self.current_benchmark != "none" and self.benchmark_symbol:
            try:
                self.benchmark_data = fetcher.fetch_symbol_history(self.benchmark_symbol, self.current_timeframe)
            except Exception:
                self.benchmark_data = None
        else:
            self.benchmark_data = None

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
        if hasattr(self, "ax2") and self.ax2 is not None:
            try:
                self.fig.delaxes(self.ax2)
            except Exception:
                pass
            self.ax2 = None
        self.ax.clear()

        if not data or not data.get("prices"):
            self._set_empty_state()
            self.mpl_canvas.draw()
            return

        prices, timestamps, prev_close, change, change_pct, line_color, fill_color, is_growth_mode, ref_label, total_cb, total_div = self._prepare_metric_series(data)

        curr_price = prices[-1]
        display_curr = getattr(self, "current_scope_currency", data.get("currency", "USD"))
        curr_sym = "$" if display_curr in ("USD", "CAD") else (display_curr + " ")
        total_shares = getattr(self, "current_scope_shares", 1.0)
        scale_factor = getattr(self, "current_scope_scale", 1.0)
        self._update_header(curr_price, change, change_pct, curr_sym, display_curr, is_growth_mode, total_cb, total_div, total_shares, scale_factor, data=data)

        x = range(len(prices))
        self.plot_x = list(x)
        self.plot_prices = prices
        self.plot_timestamps = timestamps
        self.plot_prev_close = prev_close
        self.plot_currency = curr_sym
        self.plot_currency_str = display_curr
        self.plot_cost_basis = total_cb
        self.plot_total_div = total_div
        self.plot_total_shares = total_shares
        self.plot_scale_factor = scale_factor

        self.ax.plot(x, prices, color=line_color, linewidth=2.0, antialiased=True)

        if self.chart_type == "area":
            min_y = min(prices)
            base_y = min(0.0, min_y) if is_growth_mode else (min_y - (max(prices) - min_y) * 0.05 if max(prices) > min_y else min_y * 0.95)
            self.ax.fill_between(x, prices, base_y, color=fill_color, alpha=0.7)

        # Draw reference line
        ref_y = prev_close
        self.ax.axhline(ref_y, color="#9AA0A6", linestyle="--" if is_growth_mode else ":", linewidth=1.2)
        self.ax.text(
            0 if is_growth_mode else len(prices) - 1,
            ref_y,
            ref_label,
            color="#5F6368",
            fontsize=8,
            va="bottom" if is_growth_mode else "center",
            ha="left",
            fontweight="bold",
        )

        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        self.ax.spines["left"].set_color("#E0E0E0")
        self.ax.spines["bottom"].set_color("#E0E0E0")
        self.ax.grid(True, axis="y", color="#F1F3F4", linestyle="-", linewidth=1.0)
        self.ax.tick_params(axis="both", colors="#5F6368", labelsize=8)

        if self.current_benchmark != "none" and self.benchmark_data and self.benchmark_data.get("prices"):
            bm_prices = self.benchmark_data.get("prices", [])
            if len(bm_prices) > 1 and bm_prices[0] > 0:
                bm_n = len(bm_prices)
                bm_x = np.linspace(0, len(prices) - 1, bm_n)
                bm_pct = [(p - bm_prices[0]) / bm_prices[0] * 100.0 for p in bm_prices]
                self.ax2 = self.ax.twinx()
                self.ax2.plot(bm_x, bm_pct, color="#E37400", linestyle="--", linewidth=1.8, label=f"Benchmark ({self.benchmark_symbol})")
                self.ax2.spines["top"].set_visible(False)
                self.ax2.spines["left"].set_visible(False)
                self.ax2.spines["bottom"].set_visible(False)
                self.ax2.spines["right"].set_color("#E37400")
                self.ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda val, pos: f"{val:+.1f}%"))
                self.ax2.tick_params(axis="y", colors="#E37400", labelsize=8)
                self.ax2.grid(False)

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
        if is_growth_mode:
            y_min = min(y_min, 0.0)
            y_max = max(y_max, 0.0)
        elif prev_close:
            y_min = min(y_min, prev_close)
            y_max = max(y_max, prev_close)
        margin = (y_max - y_min) * 0.12 if y_max > y_min else max(10.0, abs(y_max) * 0.1)
        self.ax.set_ylim(y_min - margin, y_max + margin)
        self.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda val, pos: f"{curr_sym}{val:+,.0f}" if is_growth_mode else f"{curr_sym}{val:,.0f}"))

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

        prices, timestamps, prev_close, change, change_pct, line_color, fill_color, is_growth_mode, ref_label, total_cb, total_div = self._prepare_metric_series(data)

        curr_price = prices[-1]
        display_curr = getattr(self, "current_scope_currency", data.get("currency", "USD"))
        curr_sym = "$" if display_curr in ("USD", "CAD") else (display_curr + " ")
        total_shares = getattr(self, "current_scope_shares", 1.0)
        scale_factor = getattr(self, "current_scope_scale", 1.0)
        self._update_header(curr_price, change, change_pct, curr_sym, display_curr, is_growth_mode, total_cb, total_div, total_shares, scale_factor, data=data)

        self.plot_prices = prices
        self.plot_timestamps = timestamps
        self.plot_prev_close = prev_close
        self.plot_currency = curr_sym
        self.plot_currency_str = display_curr
        self.plot_cost_basis = total_cb
        self.plot_total_div = total_div
        self.plot_total_shares = total_shares
        self.plot_scale_factor = scale_factor

        pad_l, pad_r, pad_t, pad_b = 65, 120, 20, 30
        plot_w = w - pad_l - pad_r
        plot_h = h - pad_t - pad_b

        y_min, y_max = min(prices), max(prices)
        if is_growth_mode:
            y_min = min(y_min, 0.0)
            y_max = max(y_max, 0.0)
        elif prev_close:
            y_min = min(y_min, prev_close)
            y_max = max(y_max, prev_close)
        y_range = y_max - y_min if y_max > y_min else 1.0

        # Draw horizontal gridlines and Y-axis labels
        n_y_grid = 4
        for i in range(n_y_grid + 1):
            val = y_min + (i / n_y_grid) * y_range
            gy = pad_t + plot_h - (i / n_y_grid) * plot_h
            self.native_canvas.create_line(pad_l, gy, pad_l + plot_w, gy, fill="#F1F3F4", width=1)
            fmt_val = f"{curr_sym}{val:+,.0f}" if is_growth_mode else f"{curr_sym}{val:,.0f}"
            self.native_canvas.create_text(pad_l - 8, gy, text=fmt_val, anchor="e", fill="#5F6368", font=("Segoe UI", 8))

        # Calculate coordinates
        n_pts = len(prices)
        coords = []
        self.canvas_points = []
        for i, (ts, pr) in enumerate(zip(timestamps, prices)):
            cx = pad_l + (i / (n_pts - 1)) * plot_w if n_pts > 1 else pad_l + plot_w // 2
            cy = pad_t + plot_h - ((pr - y_min) / y_range) * plot_h
            coords.extend([cx, cy])
            self.canvas_points.append((cx, cy, pr, ts))

        # Baseline y
        base_val = 0.0 if is_growth_mode else y_min
        base_y = pad_t + plot_h - ((base_val - y_min) / y_range) * plot_h

        # Area polygon fill
        if self.chart_type == "area" and len(coords) >= 4:
            poly_coords = [coords[0], base_y] + coords + [coords[-2], base_y]
            self.native_canvas.create_polygon(poly_coords, fill=fill_color, outline="")

        # Main curve line
        if len(coords) >= 4:
            self.native_canvas.create_line(coords, fill=line_color, width=2)

        # Previous close or invested basis line
        ref_y_val = 0.0 if is_growth_mode else prev_close
        if y_min <= ref_y_val <= y_max:
            ry = pad_t + plot_h - ((ref_y_val - y_min) / y_range) * plot_h
            self.native_canvas.create_line(pad_l, ry, pad_l + plot_w, ry, fill="#9AA0A6", dash=(4, 4), width=1)
            self.native_canvas.create_text(
                pad_l + plot_w + 6,
                ry,
                text=ref_label,
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

    def _update_header(
        self,
        curr_price: float,
        change: float,
        change_pct: float,
        curr_sym: str,
        currency: str,
        is_growth_mode: bool = False,
        total_cb: float = 0.0,
        total_div: float = 0.0,
        total_shares: float = 1.0,
        scale_factor: float = 1.0,
        data: Optional[Dict[str, Any]] = None,
    ):
        if data is None:
            data = getattr(self, "chart_data", {}) or {}

        title_text = self.current_portfolio_name if self.current_scope == "portfolio" else self.current_scope
        self.lbl_title.config(text=title_text)

        mode = getattr(self, "chart_metric", "total")
        tf_label = get_tf_display_label(self.current_timeframe)

        if mode in ("growth", "growth_div"):
            is_positive = curr_price >= 0
            sign_char = "▲ +" if is_positive else "▼ -"
            badge_color = "#137333" if is_positive else "#C5221F"
            badge_bg = "#E6F4EA" if is_positive else "#FCE8E6"
            price_str = f"{curr_sym}{abs(curr_price):,.2f}"
            self.lbl_price.config(text=f"{'+' if is_positive else '-'}{price_str}")

            if mode == "growth":
                badge_text = f"{sign_char}{abs(change_pct):.2f}% ({sign_char[2:]}{curr_sym}{abs(curr_price):,.2f}) {tf_label} · {t('chart_invested_capital')}{curr_sym}{total_cb:,.2f}"
                sub_text = f"{t('chart_net_growth')} ({t('lbl_excl_invested_capital')}) · {currency}"
            else:
                badge_text = f"{sign_char}{abs(change_pct):.2f}% ({sign_char[2:]}{curr_sym}{abs(curr_price):,.2f}) {tf_label} · +{curr_sym}{total_div:,.2f} {t('lbl_chart_divs')}"
                sub_text = t("lbl_chart_total_return", curr=currency)

            self.lbl_badge.config(text=badge_text, fg=badge_color, bg=badge_bg)
            now_utc = datetime.now(timezone.utc).strftime("%d %b, %H:%M:%S UTC")
            if self.current_scope != "portfolio" and total_shares > 0:
                self.lbl_subtitle.config(text=f"{now_utc} · {total_shares:g} {t('lbl_unit_shares')} · {sub_text}")
            else:
                self.lbl_subtitle.config(text=f"{now_utc} · {sub_text}")
        elif mode == "div_only":
            self.lbl_price.config(text=f"{curr_sym}{curr_price:,.2f}")
            self.lbl_badge.config(
                text=f"💵 {t('lbl_accrued_dividends')}: {curr_sym}{curr_price:,.2f} {tf_label}",
                fg="#188038",
                bg="#E6F4EA",
            )
            now_utc = datetime.now(timezone.utc).strftime("%d %b, %H:%M:%S UTC")
            div_label = t("lbl_dividends_only")
            if self.current_scope != "portfolio" and total_shares > 0:
                self.lbl_subtitle.config(text=f"{now_utc} · {total_shares:g} {t('lbl_unit_shares')} · {div_label} · {currency}")
            else:
                self.lbl_subtitle.config(text=f"{now_utc} · {div_label} · {currency}")
        elif mode == "price":
            self.lbl_price.config(text=f"{curr_sym}{curr_price:,.2f}")
            is_positive = change >= 0
            sign_char = "▲ +" if is_positive else "▼ -"
            badge_color = "#137333" if is_positive else "#C5221F"
            badge_bg = "#E6F4EA" if is_positive else "#FCE8E6"
            self.lbl_badge.config(
                text=f"{sign_char}{abs(change_pct):.2f}% ({sign_char[2:]}{curr_sym}{abs(change):,.2f}) {tf_label}",
                fg=badge_color,
                bg=badge_bg,
            )
            now_utc = datetime.now(timezone.utc).strftime("%d %b, %H:%M:%S UTC")
            ann_div = float(data.get("annual_dividend_per_share", 0.0) or 0.0)
            div_info = ""
            if ann_div > 0 and curr_price > 0:
                yld = (ann_div / curr_price) * 100.0
                freq = calc_dividend_frequency(data.get("dividend_events", []))
                freq_str = f" · {freq}" if freq != "None" else ""
                div_info = f" · Div: {yld:.2f}% ({curr_sym}{ann_div:,.2f}/sh{freq_str})"

            if self.current_scope != "portfolio" and total_shares > 0:
                pos_val = curr_price * total_shares
                self.lbl_subtitle.config(text=f"{now_utc} · {total_shares:g} {t('lbl_unit_shares')} (Val: {curr_sym}{pos_val:,.2f}){div_info} · {currency}")
            else:
                self.lbl_subtitle.config(text=f"{now_utc}{div_info} · {currency}")
        else:
            self.lbl_price.config(text=f"{curr_sym}{curr_price:,.2f}")
            is_positive = change >= 0
            sign_char = "▲ +" if is_positive else "▼ -"
            badge_color = "#137333" if is_positive else "#C5221F"
            badge_bg = "#E6F4EA" if is_positive else "#FCE8E6"
            self.lbl_badge.config(
                text=f"{sign_char}{abs(change_pct):.2f}% ({sign_char[2:]}{curr_sym}{abs(change):,.2f}) {tf_label}",
                fg=badge_color,
                bg=badge_bg,
            )
            now_utc = datetime.now(timezone.utc).strftime("%d %b, %H:%M:%S UTC")
            if self.current_scope != "portfolio" and total_shares > 0 and scale_factor > 0:
                raw_curr_price = curr_price / scale_factor
                ann_div = float(data.get("annual_dividend_per_share", 0.0) or 0.0)
                div_info = ""
                if ann_div > 0 and raw_curr_price > 0:
                    yld = (ann_div / raw_curr_price) * 100.0
                    freq = calc_dividend_frequency(data.get("dividend_events", []))
                    freq_str = f" · {freq}" if freq != "None" else ""
                    div_info = f" · Div: {yld:.2f}% ({curr_sym}{ann_div:,.2f}/sh{freq_str})"
                self.lbl_subtitle.config(text=f"{now_utc} · {total_shares:g} {t('lbl_unit_shares')} @ {curr_sym}{raw_curr_price:,.2f}{div_info} · {currency}")
            else:
                self.lbl_subtitle.config(text=f"{now_utc} · {currency}")

    def _set_empty_state(self):
        self.lbl_title.config(text=self.current_portfolio_name if self.current_scope == "portfolio" else self.current_scope)
        self.lbl_price.config(text=t("lbl_no_data_available"))
        self.lbl_badge.config(text="")
        self.lbl_subtitle.config(text=t("msg_chart_unavailable"))

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
        closest = min(self.canvas_points, key=lambda pt: abs(pt[0] - mx))
        cx, cy, pr, ts = closest

        self.native_canvas.delete("hover_marker")
        h = self.native_canvas.winfo_height()
        self.native_canvas.create_line(cx, 20, cx, h - 30, fill="#1A73E8", dash=(2, 2), tags="hover_marker")
        self.native_canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#1A73E8", outline="#FFFFFF", width=2, tags="hover_marker")

        prev = getattr(self, "plot_prev_close", pr)
        curr_sym = getattr(self, "plot_currency", "$")
        self._update_hover_header(pr, ts, prev, curr_sym)

    def _update_hover_header(self, hover_price: float, hover_time: datetime, prev: float, curr_sym: str):
        mode = getattr(self, "chart_metric", "total")
        time_fmt = hover_time.strftime("%d %b, %H:%M:%S") if self.current_timeframe in ("1D", "5D") else hover_time.strftime("%d %b %Y")
        total_shares = getattr(self, "plot_total_shares", 1.0)
        scale_factor = getattr(self, "plot_scale_factor", 1.0)

        if mode in ("growth", "growth_div"):
            is_pos = hover_price >= 0
            sign = "▲ +" if is_pos else "▼ -"
            badge_color = "#137333" if is_pos else "#C5221F"
            badge_bg = "#E6F4EA" if is_pos else "#FCE8E6"
            total_cb = getattr(self, "plot_cost_basis", 0.0)
            pct = (hover_price / total_cb * 100) if total_cb > 0 else 0.0
            price_str = f"{curr_sym}{abs(hover_price):,.2f}"
            self.lbl_price.config(text=f"{'+' if is_pos else '-'}{price_str}")
            self.lbl_badge.config(
                text=f"{sign}{abs(pct):.2f}% ({sign[2:]}{curr_sym}{abs(hover_price):,.2f}) {t('lbl_at_time', time=time_fmt)}",
                fg=badge_color,
                bg=badge_bg,
            )
        elif mode == "div_only":
            self.lbl_price.config(text=f"{curr_sym}{hover_price:,.2f}")
            self.lbl_badge.config(
                text=f"💵 {t('lbl_accrued_dividends')}: {curr_sym}{hover_price:,.2f} {t('lbl_at_time', time=time_fmt)}",
                fg="#188038",
                bg="#E6F4EA",
            )
        else:
            change = hover_price - prev
            change_pct = (change / prev * 100) if prev > 0 else 0.0
            is_pos = change >= 0
            sign = "▲ +" if is_pos else "▼ -"
            badge_color = "#137333" if is_pos else "#C5221F"
            badge_bg = "#E6F4EA" if is_pos else "#FCE8E6"
            self.lbl_price.config(text=f"{curr_sym}{hover_price:,.2f}")
            share_info = f" · {total_shares:g} @ {curr_sym}{hover_price/scale_factor:,.2f}" if (getattr(self, "current_scope", "portfolio") != "portfolio" and total_shares > 0 and scale_factor > 0) else ""
            self.lbl_badge.config(
                text=f"{sign}{abs(change_pct):.2f}% ({sign[2:]}{curr_sym}{abs(change):,.2f}) {t('lbl_at_time', time=time_fmt)}{share_info}",
                fg=badge_color,
                bg=badge_bg,
            )

    def _on_leave(self, event):
        if hasattr(self, "native_canvas"):
            self.native_canvas.delete("hover_marker")
        if self.chart_data:
            self._render_chart(self.chart_data)

    # -------------------------------------------------------------
    # Package Installation Helper
    # -------------------------------------------------------------
    def _prompt_install_packages(self):
        if messagebox.askyesno(t("dlg_install_pkg_title"), t("msg_install_pkg_confirm"), parent=self):
            threading.Thread(target=self._run_pip_install, daemon=True).start()

    def _run_pip_install(self):
        self.lbl_subtitle.config(text=t("msg_installing_packages"))
        try:
            cmd = [sys.executable, "-m", "pip", "install", "matplotlib", "yfinance", "pandas"]
            subprocess.run(cmd, check=True, capture_output=True)
            messagebox.showinfo(t("msg_success"), t("msg_install_pkg_success"), parent=self)
        except Exception as e:
            messagebox.showerror(t("dlg_error"), t("msg_install_pkg_failed", error=str(e)), parent=self)

    def apply_language(self):
        """Update localized UI text when language changes."""
        if hasattr(self, "lbl_title") and self.current_scope == "portfolio":
            self.lbl_title.config(text=t("lbl_portfolio_chart"))
        if hasattr(self, "btn_install_pkg"):
            self.btn_install_pkg.config(text=t("btn_install_packages"))
        if hasattr(self, "lbl_chart_view"):
            self.lbl_chart_view.config(text=t("lbl_chart_view"))
        if hasattr(self, "lbl_chart_style"):
            self.lbl_chart_style.config(text=t("lbl_chart_style"))
        if hasattr(self, "style_combo"):
            current_s = self.style_combo.get()
            is_line = (current_s in ("Line", "折線圖", "折线图"))
            self.style_combo.config(values=[t("chart_style_area"), t("chart_style_line")])
            self.style_combo.set(t("chart_style_line") if is_line else t("chart_style_area"))
        if hasattr(self, "btn_refresh"):
            self.btn_refresh.config(text=t("btn_refresh"))
        if hasattr(self, "lbl_chart_metric"):
            self.lbl_chart_metric.config(text=t("lbl_chart_metric"))
        if hasattr(self, "metric_combo"):
            current_m = getattr(self, "chart_metric", "total")
            self.metric_combo.config(values=[
                t("chart_metric_total"),
                t("chart_metric_price"),
                t("chart_metric_growth"),
                t("chart_metric_growth_div"),
                t("chart_metric_div_only"),
            ])
            mapping = {
                "total": t("chart_metric_total"),
                "price": t("chart_metric_price"),
                "growth": t("chart_metric_growth"),
                "growth_div": t("chart_metric_growth_div"),
                "div_only": t("chart_metric_div_only"),
            }
            self.metric_combo.set(mapping.get(current_m, t("chart_metric_total")))
        if hasattr(self, "lbl_benchmark"):
            self.lbl_benchmark.config(text=t("lbl_benchmark"))
        if hasattr(self, "benchmark_combo"):
            current_bm = getattr(self, "current_benchmark", "none")
            self.benchmark_combo.config(values=[
                t("bm_none"),
                t("bm_sp500"),
                t("bm_tsx60"),
            ])
            mapping_bm = {
                "none": t("bm_none"),
                "sp500": t("bm_sp500"),
                "tsx60": t("bm_tsx60"),
            }
            self.benchmark_combo.set(mapping_bm.get(current_bm, t("bm_none")))
        self.refresh_chart()

