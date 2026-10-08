"""
Google Finance Portfolio & Financial Calculator GUI
Desktop application for tracking live Google Finance quotes,
syncing with user's Google Finance account, performing dividend,
division/split, and selling calculations, and saving data in CSV.
"""

import os
import sys
import re
import time
import threading
import queue
import concurrent.futures
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import webbrowser
from google_finance_fetcher import GoogleFinanceFetcher
from google_account_sync import (
    GoogleAccountSync,
    load_sync_config,
    save_sync_config,
)
from financial_calc import (
    calc_holding_summary,
    calc_dividend_projection,
    calc_drip_simulation,
    calc_stock_split,
    calc_selling_proceeds,
    calc_breakeven_sell_price,
    calc_target_profit_sell_price,
    calc_portfolio_metrics,
    calc_holding_earned_already,
    calc_future_dividend_milestones,
    calc_split_future_projections,
    parse_date_to_days_held,
    parse_tx_date,
    calc_period_earnings,
    calc_risk_and_return_metrics,
    calc_tax_lot_proceeds,
    calc_dividend_calendar,
    infer_holding_sector,
    calc_portfolio_rebalance,
    calc_fire_metrics,
    calc_deep_risk_diagnostic,
    calc_historical_crisis_stress_test,
    calc_cape_dynamic_swr,
    calc_fee_and_tax_drag_autopsy,
    calc_rebalancing_5_25_bands,
    calc_simplicity_index,
    calc_retirement_spending_smile,
    calc_sequence_of_returns_risk_simulation,
    calc_guyton_klinger_guardrails,
    calc_three_bucket_architecture,
    calc_healthcare_ltc_contingency,
    calc_actuarial_longevity_table,
    calc_monte_carlo_distribution,
    calc_stagflation_sensitivity_matrix,
    calc_rising_equity_glidepath,
    KNOWN_ETF_TER,
    SUGGESTED_ALLOCATION_ETFS,
    ALLOCATION_PRESETS,
    get_preset_display_name as get_allocation_preset_display_name,
    get_etf_option_label,
)
from chart_canvas import draw_donut_chart, draw_drip_growth_chart, draw_fee_tax_trajectory_chart, ChartTheme
from report_generator import generate_html_report, generate_period_earnings_report_html
from currency_converter import get_currency_converter
from chart_view import GoogleFinanceChartView
from csv_manager import (
    PORTFOLIO_CSV,
    WATCHLIST_CSV,
    SALES_HISTORY_CSV,
    TRANSACTION_HISTORY_CSV,
    BACKUP_DIR,
    DEFAULT_PORTFOLIO_NAME,
    save_portfolio,
    load_portfolio,
    get_portfolio_names,
    add_portfolio,
    delete_portfolio,
    rename_portfolio,
    save_sales_history,
    load_sales_history,
    append_sale_record,
    save_transactions,
    load_transactions,
    append_transaction,
    update_transaction,
    delete_transaction,
    ensure_workspace_files,
    get_backup_files,
    restore_backup,
    export_period_report_to_csv,
    book_drip_transaction,
    load_watchlist,
    save_watchlist,
    load_watchlist_quotes_cache,
    save_watchlist_quotes_cache,
    add_to_watchlist,
    remove_from_watchlist,
    update_watchlist_item,
    bulk_update_watchlist_category,
    bulk_add_to_watchlist,
    import_watchlist_from_csv,
    parse_symbols_text,
    scan_data_integrity,
    repair_data_integrity,
)
from fee_manager import (
    BROKER_PRESETS,
    get_preset_display_name as get_broker_preset_display_name,
    get_portfolio_fee_config,
    save_portfolio_fee_config,
    delete_portfolio_fee_config,
    rename_portfolio_fee_config,
    calc_estimated_commission,
    log_storage_fee_transaction,
)
from tkinter import simpledialog
from i18n import (
    t,
    get_current_language,
    set_language,
    get_available_languages,
    load_settings,
    save_settings,
    TRANSLATIONS,
)
import web_server

POPULAR_TICKERS = [
    ("-- Select popular ticker --", "", ""),
    ("🇨🇦 VFV:TSE (Vanguard S&P 500 ETF - CAD)", "VFV:TSE", "CAD"),
    ("🇨🇦 XEQT:TSE (iShares Core Equity ETF - CAD)", "XEQT:TSE", "CAD"),
    ("🇨🇦 VDY:TSE (Vanguard High Dividend Yield - CAD)", "VDY:TSE", "CAD"),
    ("🇨🇦 ZAG:TSE (BMO Aggregate Bond Index - CAD)", "ZAG:TSE", "CAD"),
    ("🇨🇦 TD:TSE (Toronto-Dominion Bank - CAD)", "TD:TSE", "CAD"),
    ("🇺🇸 VOO (Vanguard S&P 500 ETF - USD)", "VOO", "USD"),
    ("🇺🇸 QQQ (Invesco Nasdaq 100 ETF - USD)", "QQQ", "USD"),
    ("🇺🇸 SCHD (Schwab US Dividend Equity - USD)", "SCHD", "USD"),
    ("🇺🇸 AAPL (Apple Inc. - USD)", "AAPL", "USD"),
    ("🇺🇸 MSFT (Microsoft Corp. - USD)", "MSFT", "USD"),
    ("🇭🇰 0005:HKG (HSBC Holdings plc - HKD)", "0005:HKG", "HKD"),
    ("🇭🇰 0700:HKG (Tencent Holdings - HKD)", "0700:HKG", "HKD"),
    ("🇭🇰 9988:HKG (Alibaba Group - HKD)", "9988:HKG", "HKD"),
    ("🇭🇰 1137:HKG (HK Tech Venture - HKD)", "1137:HKG", "HKD"),
]


class ToolTip:
    """
    Lightweight, thread-safe, theme-aware hover tooltip widget for Tkinter and ttk widgets.
    Dynamically re-evaluates text (supporting instant language switching) and respects screen boundaries.
    """
    def __init__(self, widget, text_provider, delay_ms: int = 350):
        self.widget = widget
        self.text_provider = text_provider
        self.delay_ms = delay_ms
        self.tip_window = None
        self._after_id = None

        try:
            self.widget.bind("<Enter>", self._on_enter, add="+")
            self.widget.bind("<Leave>", self._on_leave, add="+")
            self.widget.bind("<ButtonPress>", self._on_leave, add="+")
        except Exception:
            pass

    def _get_text(self) -> str:
        if callable(self.text_provider):
            try:
                return str(self.text_provider() or "")
            except Exception:
                return ""
        return str(self.text_provider or "")

    def _on_enter(self, event=None):
        self._cancel_timer()
        try:
            self._after_id = self.widget.after(self.delay_ms, self._show)
        except Exception:
            pass

    def _on_leave(self, event=None):
        self._cancel_timer()
        self._hide()

    def _cancel_timer(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        self._after_id = None
        text = self._get_text().strip()
        if not text:
            return
        try:
            if not self.widget.winfo_exists():
                return
        except Exception:
            return

        try:
            x = self.widget.winfo_rootx() + 8
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

            screen_w = self.widget.winfo_screenwidth()
            screen_h = self.widget.winfo_screenheight()

            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            try:
                tw.wm_attributes("-topmost", True)
            except Exception:
                pass

            border_frame = tk.Frame(tw, bg="#5f6368", padx=1, pady=1)
            border_frame.pack()

            lbl = tk.Label(
                border_frame,
                text=text,
                justify=tk.LEFT,
                background="#202124",
                foreground="#f1f3f4",
                font=("Segoe UI", 9),
                padx=8,
                pady=5,
                wraplength=380,
            )
            lbl.pack()

            tw.update_idletasks()
            w = tw.winfo_reqwidth()
            h = tw.winfo_reqheight()

            if x + w > screen_w - 12:
                x = max(6, screen_w - w - 12)
            if y + h > screen_h - 12:
                y = max(6, self.widget.winfo_rooty() - h - 5)

            tw.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            self._hide()

    def _hide(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            try:
                tw.destroy()
            except Exception:
                pass


def attach_tooltip(widget, key_or_text_or_func, delay_ms: int = 350) -> ToolTip:
    """Convenience helper to attach a dynamic tooltip to any widget."""
    def provider():
        if callable(key_or_text_or_func):
            return key_or_text_or_func()
        if isinstance(key_or_text_or_func, str):
            val = t(key_or_text_or_func)
            return val if val != key_or_text_or_func else key_or_text_or_func
        return str(key_or_text_or_func)
    return ToolTip(widget, provider, delay_ms=delay_ms)


class ModernPortfolioApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(t("app_title"))
        self.root.geometry("1280x860")
        self.root.minsize(1020, 700)

        # Initialize data
        ensure_workspace_files()
        self.converter = get_currency_converter()
        self.converter.refresh_rates_async()
        self.summary_currency: str = "USD"

        # Multi-portfolio support
        self.all_holdings: List[Dict[str, Any]] = load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
        self.portfolio_names: List[str] = get_portfolio_names(PORTFOLIO_CSV)
        self.current_portfolio: str = "All Portfolios (Consolidated)"

        # Active holdings filtered by current portfolio
        self.holdings: List[Dict[str, Any]] = list(self.all_holdings)
        self.transactions: List[Dict[str, Any]] = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=None, tx_type=None)
        self.sales_history: List[Dict[str, Any]] = self.transactions
        self.fetcher = GoogleFinanceFetcher()
        self.account_sync = GoogleAccountSync()

        # Threading and auto-update
        self.is_running: bool = True
        self.fetch_queue: queue.Queue = queue.Queue()
        self.is_fetching: bool = False
        self.queue_job = None
        self.auto_refresh_job = None

        # Auto-refresh interval persistence (default: 5 min / 300s)
        cfg = load_settings()
        self.saved_refresh_interval: str = cfg.get("auto_refresh_interval", "5 min")
        interval_mapping = {
            "Off": 0,
            "15s": 15,
            "30s": 30,
            "1 min": 60,
            "2 min": 120,
            "5 min": 300,
        }
        self.refresh_interval_sec: int = interval_mapping.get(self.saved_refresh_interval, 300)
        self.auto_refresh_enabled: bool = (self.refresh_interval_sec > 0)

        # Theme, Search & Filter state
        self.dark_mode: bool = False
        self.search_filter_var = tk.StringVar()
        self.filter_performance: str = "All"
        self.sort_col: Optional[str] = None
        self.sort_reverse: bool = False
        self._triggered_alerts = set()
        self._network_errors: List[Dict[str, Any]] = []
        self.watchlist_tag_filter_var = tk.StringVar(value=t("btn_filter_tag_all"))
        cfg = load_settings()
        self.visible_columns = cfg.get("visible_columns", None)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Configure style
        self._setup_style()

        # Build UI layout
        self._build_top_bar()
        self._build_portfolio_bar()
        self._build_metric_cards()
        self._build_status_bar()
        self._build_tabs()

        # Context Menu & Hotkeys
        self._build_context_menu()
        self._setup_keyboard_shortcuts()

        # Populate tables
        self._refresh_holdings_table()
        self._refresh_sales_table()
        self._update_metric_cards()
        self._refresh_dropdowns()
        self._refresh_analytics_tab()
        if hasattr(self, "chart_view"):
            self.chart_view.update_portfolio(self.current_portfolio, self.summary_currency)

        # Start background queue poller
        self.queue_job = self.root.after(100, self._process_fetch_queue)

        # Start initial background quotes update (showing cached data immediately)
        if self.all_holdings or load_watchlist():
            self._set_status(f"🔄 {t('msg_cached_data_notice')}")
            self.root.after(300, self.fetch_all_quotes)
        self._schedule_auto_refresh()

    def _setup_style(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        self._apply_theme_colors()

    def _apply_theme_colors(self):
        if getattr(self, "dark_mode", False):
            self.bg_main = "#1e222d"
            self.card_bg = "#2a2e39"
            self.primary_color = "#8ab4f8"
            self.text_dark = "#e8eaed"
            self.text_muted = "#9aa0a6"
            self.green_color = "#81c995"
            self.red_color = "#f28b82"
            self.tab_inactive_bg = "#2d3342"
            self.tree_bg = "#252a36"
            self.tree_fg = "#e8eaed"
            self.tree_heading_bg = "#1e222d"
            self.tree_select_bg = "#3c4043"
            self.tree_select_fg = "#8ab4f8"
            self.border_color = "#3c4043"
        else:
            self.bg_main = "#f4f6f9"
            self.card_bg = "#ffffff"
            self.primary_color = "#1a73e8"
            self.text_dark = "#202124"
            self.text_muted = "#5f6368"
            self.green_color = "#0f9d58"
            self.red_color = "#d93025"
            self.tab_inactive_bg = "#e0e4e9"
            self.tree_bg = "#ffffff"
            self.tree_fg = "#202124"
            self.tree_heading_bg = "#e8eaed"
            self.tree_select_bg = "#d2e3fc"
            self.tree_select_fg = "#174ea6"
            self.border_color = "#dadce0"

        self.root.configure(bg=self.bg_main)
        self.style.configure(".", background=self.bg_main, foreground=self.text_dark)
        self.style.configure("TFrame", background=self.bg_main)
        self.style.configure("Card.TFrame", background=self.card_bg, relief="solid", borderwidth=1)

        # Notebook / Tabs style
        self.style.configure("TNotebook", background=self.bg_main, tabmargins=[6, 5, 2, 0])
        self.style.configure(
            "TNotebook.Tab",
            background=self.tab_inactive_bg,
            foreground=self.text_dark,
            padding=[14, 7],
            font=("Segoe UI", 9, "bold"),
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", self.primary_color)],
            foreground=[("selected", "#ffffff" if not self.dark_mode else "#1e222d")],
        )

        # Treeview styling
        self.style.configure(
            "Treeview",
            background=self.tree_bg,
            foreground=self.tree_fg,
            fieldbackground=self.tree_bg,
            rowheight=28,
            font=("Segoe UI", 9),
        )
        self.style.configure(
            "Treeview.Heading",
            background=self.tree_heading_bg,
            foreground=self.text_dark,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        self.style.map("Treeview", background=[("selected", self.tree_select_bg)], foreground=[("selected", self.tree_select_fg)])

    def _toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self._apply_theme_colors()
        if hasattr(self, "btn_theme_toggle"):
            self.btn_theme_toggle.config(
                text=t("btn_theme_light") if self.dark_mode else t("btn_theme_dark"),
                bg="#3c4043" if self.dark_mode else "#ffffff",
                fg="#fbbc04" if self.dark_mode else "#202124",
            )
        if hasattr(self, "lbl_title"):
            self.lbl_title.config(bg=self.bg_main, fg=self.primary_color)
        if hasattr(self, "lbl_engine_badge"):
            self.lbl_engine_badge.config(
                bg="#133e24" if self.dark_mode else "#e6f4ea",
                fg="#81c995" if self.dark_mode else "#137333",
            )
        if hasattr(self, "btn_tools_menu"):
            self.btn_tools_menu.config(
                bg="#2d3342" if self.dark_mode else "#ffffff",
                fg=self.primary_color,
                activebackground="#3c4043" if self.dark_mode else "#e8f0fe",
                activeforeground=self.primary_color,
            )
        if hasattr(self, "tools_menu"):
            self.tools_menu.config(
                bg="#2a2e39" if self.dark_mode else "#ffffff",
                fg=self.text_dark,
                activebackground=self.primary_color,
                activeforeground="#ffffff",
            )
        if hasattr(self, "btn_refresh"):
            self.btn_refresh.config(
                bg="#2d3342" if self.dark_mode else "#ffffff",
                fg=self.primary_color,
                activebackground="#3c4043" if self.dark_mode else "#e8f0fe",
            )
        if hasattr(self, "btn_watch_category"):
            self.btn_watch_category.config(
                bg="#2d3342" if self.dark_mode else "#ffffff",
                fg=self.primary_color,
            )
        if hasattr(self, "lbl_auto"):
            self.lbl_auto.config(bg=self.bg_main, fg=self.text_dark)
        if hasattr(self, "status_frame"):
            self.status_frame.config(bg=self.card_bg)
        if hasattr(self, "lbl_status"):
            self.lbl_status.config(bg=self.card_bg, fg=self.text_muted)
        if hasattr(self, "lbl_time"):
            self.lbl_time.config(bg=self.card_bg, fg=self.text_muted)
        if hasattr(self, "card_frames"):
            for cf in self.card_frames:
                cf.config(bg=self.card_bg)
        if hasattr(self, "card_titles"):
            for lbl in self.card_titles.values():
                lbl.config(bg=self.card_bg, fg=self.text_muted)
        if hasattr(self, "cards"):
            for k, lbl in self.cards.items():
                lbl.config(bg=self.card_bg)
        if hasattr(self, "analytics_left_box"):
            self.analytics_left_box.config(bg=self.card_bg, fg=self.primary_color)
        if hasattr(self, "analytics_right_box"):
            self.analytics_right_box.config(bg=self.card_bg, fg=self.primary_color)
        if hasattr(self, "analytics_kpis"):
            for cell, lbl_t, lbl_v in self.analytics_kpis.values():
                cell.config(bg=self.card_bg)
                lbl_t.config(bg=self.card_bg, fg=self.text_muted)
                lbl_v.config(bg=self.card_bg)
        for tree in [getattr(self, "holdings_tree", None), getattr(self, "history_tree", None), getattr(self, "alloc_tree", None), getattr(self, "drip_tree", None), getattr(self, "watchlist_tree", None)]:
            if tree:
                tree.tag_configure("positive", foreground=self.green_color)
                tree.tag_configure("negative", foreground=self.red_color)
                tree.tag_configure("neutral", foreground=self.tree_fg)
        if hasattr(self, "watchlist_tree"):
            bg_hit = "#e6f4ea" if not self.dark_mode else "#183b27"
            self.watchlist_tree.tag_configure("reached_positive", foreground=self.green_color, background=bg_hit, font=("Segoe UI", 9, "bold"))
            self.watchlist_tree.tag_configure("reached_negative", foreground=self.red_color, background=bg_hit, font=("Segoe UI", 9, "bold"))
            self.watchlist_tree.tag_configure("reached", foreground=self.green_color, background=bg_hit, font=("Segoe UI", 9, "bold"))
        self._update_filter_button_styles()
        self._refresh_holdings_table()
        self._refresh_analytics_tab()
        if hasattr(self, "_refresh_watchlist_tab"):
            self._refresh_watchlist_tab()
        if hasattr(self, "drip_canvas"):
            self._calc_drip_results()
        if hasattr(self, "chart_view"):
            self.chart_view.update_portfolio(self.current_portfolio, self.summary_currency)
        self._set_status(f"Switched to {'Dark' if self.dark_mode else 'Light'} theme.")

    # -------------------------------------------------------------
    # Top Bar with Google Sync, Add/Remove, and Auto-Refresh
    # -------------------------------------------------------------
    def _build_top_bar(self):
        top_frame = ttk.Frame(self.root, padding="12 8 12 4")
        top_frame.pack(fill=tk.X)

        # Title & Engine Status
        title_box = ttk.Frame(top_frame)
        title_box.pack(side=tk.LEFT)
        self.lbl_title = tk.Label(
            title_box,
            text=t("app_header"),
            font=("Segoe UI", 13, "bold"),
            bg=self.bg_main,
            fg=self.primary_color,
        )
        self.lbl_title.pack(side=tk.LEFT, anchor="w")

        self.lbl_engine_badge = tk.Label(
            title_box,
            text=t("badge_safe_engine"),
            font=("Segoe UI", 8),
            bg="#e6f4ea" if not self.dark_mode else "#133e24",
            fg="#137333" if not self.dark_mode else "#81c995",
            padx=6,
            pady=1,
            relief="solid",
            bd=1,
        )
        self.lbl_engine_badge.pack(side=tk.LEFT, padx=(8, 0))

        # Action and control buttons on right
        ctrl_box = ttk.Frame(top_frame)
        ctrl_box.pack(side=tk.RIGHT)

        # 1. Google Account Sync button
        self.btn_sync = tk.Button(
            ctrl_box,
            text=t("btn_google_sync"),
            font=("Segoe UI", 9, "bold"),
            bg="#fbbc04",
            fg="#202124",
            activebackground="#f9ab00",
            relief="flat",
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._open_sync_dialog,
        )
        self.btn_sync.pack(side=tk.LEFT, padx=(0, 6))

        # 2. Add Stock button
        self.btn_add = tk.Button(
            ctrl_box,
            text=t("btn_add_stock"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            activebackground="#1557b0",
            relief="flat",
            padx=9,
            pady=3,
            cursor="hand2",
            command=self._open_add_dialog,
        )
        self.btn_add.pack(side=tk.LEFT, padx=(0, 6))

        # 3. Consolidated Tools & Utilities Menubutton
        self.btn_tools_menu = tk.Menubutton(
            ctrl_box,
            text=f"{t('menu_tools')} ▾",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg=self.primary_color,
            activebackground="#e8f0fe" if not self.dark_mode else "#3c4043",
            activeforeground=self.primary_color,
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            direction="below",
        )
        self.tools_menu = tk.Menu(self.btn_tools_menu, tearoff=0, font=("Segoe UI", 9))
        self.btn_tools_menu["menu"] = self.tools_menu
        self._rebuild_tools_menu()
        self.btn_tools_menu.pack(side=tk.LEFT, padx=(0, 8))

        # 4. Refresh Quotes button
        self.btn_refresh = tk.Button(
            ctrl_box,
            text=t("btn_refresh"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg=self.primary_color,
            activebackground="#e8f0fe" if not self.dark_mode else "#3c4043",
            relief="solid",
            bd=1,
            padx=6,
            pady=3,
            cursor="hand2",
            command=self.fetch_all_quotes,
        )
        self.btn_refresh.pack(side=tk.LEFT, padx=(0, 4))

        # 5. Auto-Refresh Controls
        self.lbl_auto = tk.Label(ctrl_box, text=t("lbl_auto"), font=("Segoe UI", 9, "bold"), bg=self.bg_main)
        self.lbl_auto.pack(side=tk.LEFT, padx=(0, 2))

        self.interval_var = tk.StringVar(value=getattr(self, "saved_refresh_interval", "5 min"))
        self.interval_menu = ttk.Combobox(
            ctrl_box,
            textvariable=self.interval_var,
            values=["Off", "15s", "30s", "1 min", "2 min", "5 min"],
            width=6,
            state="readonly",
        )
        self.interval_menu.pack(side=tk.LEFT, padx=(0, 8))
        self.interval_menu.bind("<<ComboboxSelected>>", self._on_interval_changed)

        # 6. Language Selector
        avail_langs = get_available_languages()
        cur_lang_name = dict(avail_langs).get(get_current_language(), "English")
        self.lang_var = tk.StringVar(value=cur_lang_name)
        self.lang_combo = ttk.Combobox(
            ctrl_box,
            textvariable=self.lang_var,
            values=[name for _, name in avail_langs],
            width=9,
            state="readonly",
            font=("Segoe UI", 9),
        )
        self.lang_combo.pack(side=tk.LEFT, padx=(0, 6))
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_language_changed)

        # 7. Theme Toggle
        self.btn_theme_toggle = tk.Button(
            ctrl_box,
            text=t("btn_theme_light") if self.dark_mode else t("btn_theme_dark"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#3c4043",
            fg="#202124" if not self.dark_mode else "#fbbc04",
            relief="solid",
            bd=1,
            padx=6,
            pady=3,
            cursor="hand2",
            command=self._toggle_theme,
        )
        self.btn_theme_toggle.pack(side=tk.LEFT)

        # Compatibility proxies for buttons that may be accessed or updated by code/tests
        self.btn_remove = tk.Button(self.root, text=t("btn_tbl_remove"), command=self._delete_selected_holding)
        self.btn_report = tk.Button(self.root, text=t("btn_report"), command=self._export_html_report_dialog)
        self.btn_watchlist = tk.Button(self.root, text=t("btn_watchlist"), command=self._switch_to_watchlist_tab)
        self.btn_what_if = tk.Button(self.root, text=t("btn_what_if"), command=self._open_what_if_dialog)
        self.btn_data_health = tk.Button(self.root, text=t("btn_data_health"), command=self._open_data_health_dialog)
        self.btn_web_view = tk.Button(self.root, text=t("btn_web_dashboard"), command=self._open_local_web_view)
        self.btn_feature_guide = tk.Button(self.root, text=t("btn_feature_guide"), command=self._open_feature_guide_dialog)
        self.btn_import = tk.Button(self.root, text=t("btn_import_csv"), command=self._import_csv_dialog)
        self.btn_export = tk.Button(self.root, text=t("btn_export_csv"), command=self._export_csv_dialog)
        self.btn_backups = tk.Button(self.root, text=t("btn_backups"), command=self._open_backups_dialog)

        # Attach hints / tooltips
        attach_tooltip(self.btn_sync, "tip_sync")
        attach_tooltip(self.btn_add, "tip_add_holding")
        attach_tooltip(self.btn_tools_menu, "tip_tools_menu")
        attach_tooltip(self.btn_refresh, "tip_refresh")
        attach_tooltip(self.interval_menu, "tip_auto_refresh")
        attach_tooltip(self.lang_combo, "tip_lang")
        attach_tooltip(self.btn_theme_toggle, "tip_theme")

    def _rebuild_tools_menu(self):
        if not hasattr(self, "tools_menu"):
            return
        self.tools_menu.delete(0, tk.END)
        self.tools_menu.add_command(
            label=f"📄 {t('btn_report')}",
            command=self._export_html_report_dialog,
            accelerator="Ctrl+P",
        )
        self.tools_menu.add_command(
            label=f"💡 {t('btn_what_if')}",
            command=self._open_what_if_dialog,
            accelerator="Ctrl+W",
        )
        self.tools_menu.add_command(
            label=f"🩺 {t('btn_data_health')}",
            command=self._open_data_health_dialog,
            accelerator="Ctrl+H",
        )
        self.tools_menu.add_command(
            label=f"🌐 {t('btn_web_dashboard')}",
            command=self._open_local_web_view,
        )
        self.tools_menu.add_command(
            label=f"⭐ {t('btn_watchlist')}",
            command=self._switch_to_watchlist_tab,
        )
        self.tools_menu.add_command(
            label=f"🏛️ {t('btn_fire_toolkit')}",
            command=self._open_retirement_advanced_toolkit_dialog,
        )
        self.tools_menu.add_separator()
        self.tools_menu.add_command(
            label=f"📂 {t('btn_import_csv')}",
            command=self._import_csv_dialog,
            accelerator="Ctrl+O",
        )
        self.tools_menu.add_command(
            label=f"💾 {t('btn_export_csv')}",
            command=self._export_csv_dialog,
            accelerator="Ctrl+E",
        )
        self.tools_menu.add_command(
            label=f"🔄 {t('btn_backups')}",
            command=self._open_backups_dialog,
        )
        self.tools_menu.add_separator()
        self.tools_menu.add_command(
            label=f"📖 {t('btn_feature_guide')}",
            command=self._open_feature_guide_dialog,
            accelerator="F1",
        )
        self.tools_menu.add_command(
            label=f"{t('btn_shortcuts')}",
            command=self._open_shortcuts_dialog,
            accelerator="Ctrl+/",
        )

    def _setup_keyboard_shortcuts(self):
        self.root.bind("<F5>", lambda e: self.fetch_all_quotes())
        self.root.bind("<Control-r>", lambda e: self.fetch_all_quotes())
        self.root.bind("<Control-R>", lambda e: self.fetch_all_quotes())
        self.root.bind("<Control-n>", lambda e: self._open_add_dialog())
        self.root.bind("<Control-N>", lambda e: self._open_add_dialog())
        self.root.bind("<Control-f>", lambda e: self._focus_search())
        self.root.bind("<Control-F>", lambda e: self._focus_search())
        self.root.bind("<Control-p>", lambda e: self._export_html_report_dialog())
        self.root.bind("<Control-P>", lambda e: self._export_html_report_dialog())
        self.root.bind("<Control-w>", lambda e: self._open_what_if_dialog())
        self.root.bind("<Control-W>", lambda e: self._open_what_if_dialog())
        self.root.bind("<Control-h>", lambda e: self._open_data_health_dialog())
        self.root.bind("<Control-H>", lambda e: self._open_data_health_dialog())
        self.root.bind("<Control-o>", lambda e: self._import_csv_dialog())
        self.root.bind("<Control-O>", lambda e: self._import_csv_dialog())
        self.root.bind("<Control-e>", lambda e: self._export_csv_dialog())
        self.root.bind("<Control-E>", lambda e: self._export_csv_dialog())
        self.root.bind("<Control-d>", lambda e: self._toggle_theme())
        self.root.bind("<Control-D>", lambda e: self._toggle_theme())
        self.root.bind("<Control-s>", lambda e: self._open_sync_dialog())
        self.root.bind("<Control-S>", lambda e: self._open_sync_dialog())
        self.root.bind("<F1>", lambda e: self._open_feature_guide_dialog())
        self.root.bind("<Control-slash>", lambda e: self._open_shortcuts_dialog())
        self.root.bind("<Control-question>", lambda e: self._open_shortcuts_dialog())

    def _focus_search(self):
        try:
            current_tab = self.notebook.select()
            if hasattr(self, "tab_watchlist") and str(current_tab) == str(self.tab_watchlist):
                if hasattr(self, "watchlist_search_entry"):
                    self.watchlist_search_entry.focus_set()
                    self.watchlist_search_entry.select_range(0, tk.END)
                    return "break"
            if hasattr(self, "tab_holdings"):
                self.notebook.select(self.tab_holdings)
            if hasattr(self, "search_entry"):
                self.search_entry.focus_set()
                self.search_entry.select_range(0, tk.END)
            return "break"
        except Exception:
            pass

    def _open_shortcuts_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_shortcuts_title"))
        dlg.geometry("640x480")
        dlg.minsize(560, 420)
        dlg.transient(self.root)
        dlg.grab_set()

        bg_col = self.card_bg if hasattr(self, "card_bg") else "#ffffff"
        dlg.configure(bg=self.bg_main)

        header = tk.Frame(dlg, bg=self.bg_main, padx=16, pady=12)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text=f"⌨️ {t('dlg_shortcuts_title')}",
            font=("Segoe UI", 12, "bold"),
            bg=self.bg_main,
            fg=self.primary_color,
        ).pack(anchor="w")

        content = tk.Frame(dlg, bg=bg_col, bd=1, relief="solid", padx=12, pady=12)
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        tree_frame = ttk.Frame(content)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("shortcut", "action", "scope")
        shortcut_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=10)
        shortcut_tree.heading("shortcut", text="Shortcut / 快捷鍵")
        shortcut_tree.heading("action", text="Function / 功能說明")
        shortcut_tree.heading("scope", text="Category / 分類")
        shortcut_tree.column("shortcut", width=120, anchor="center")
        shortcut_tree.column("action", width=260, anchor="w")
        shortcut_tree.column("scope", width=130, anchor="center")

        v_scr = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=shortcut_tree.yview)
        shortcut_tree.configure(yscrollcommand=v_scr.set)
        shortcut_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scr.pack(side=tk.RIGHT, fill=tk.Y)

        shortcut_data = [
            ("F5 / Ctrl+R", t("btn_refresh"), "行情報價 (Quotes)"),
            ("Ctrl+N", t("btn_add_stock"), "投資組合 (Portfolio)"),
            ("Ctrl+F", t("lbl_search"), "搜尋定位 (Search)"),
            ("Ctrl+D", "切換深淺主題 (Toggle Theme)", "外觀視覺 (Display)"),
            ("Ctrl+P", t("btn_report"), "分析報告 (Reports)"),
            ("Ctrl+W", t("btn_what_if"), "進階工具 (Tools)"),
            ("Ctrl+H", t("btn_data_health"), "健康檢查 (Diagnostic)"),
            ("Ctrl+O", t("btn_import_csv"), "數據匯入 (Data)"),
            ("Ctrl+E", t("btn_export_csv"), "數據匯出 (Data)"),
            ("Ctrl+S", t("btn_google_sync"), "帳號同步 (Cloud)"),
            ("Delete / Backspace", t("btn_tbl_remove"), "表格操作 (Table)"),
            ("Escape", "清除搜尋關鍵字 (Clear Search)", "表格操作 (Table)"),
            ("F1", t("btn_feature_guide"), "說明指南 (Help)"),
            ("Ctrl+/", t("btn_shortcuts"), "快捷鍵速查 (Help)"),
        ]

        for s_key, s_act, s_cat in shortcut_data:
            shortcut_tree.insert("", tk.END, values=(s_key, s_act, s_cat))

        btn_box = tk.Frame(dlg, bg=self.bg_main, padx=16, pady=8)
        btn_box.pack(fill=tk.X)
        tk.Button(
            btn_box,
            text=t("btn_close", default="Close"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            padx=16,
            pady=4,
            command=dlg.destroy,
        ).pack(side=tk.RIGHT)

    def _on_language_changed(self, event=None):
        selected_display = self.lang_var.get()
        for code, name in get_available_languages():
            if name == selected_display:
                set_language(code)
                break
        self._apply_language()

    def _apply_language(self):
        # 1. Update window title
        if hasattr(self, "current_portfolio"):
            if self.current_portfolio in ("All Portfolios (Consolidated)", "All Portfolios", "All",
                                          t("portfolio_all_consolidated"), t("portfolio_all_plain")):
                self.root.title(f"{t('app_title')} - {t('portfolio_all_consolidated')}")
            else:
                self.root.title(f"{t('app_title')} - {self.current_portfolio}")

        # 2. Update top bar
        if hasattr(self, "lbl_title"):
            self.lbl_title.config(text=t("app_header"))
        if hasattr(self, "lbl_engine_badge"):
            self.lbl_engine_badge.config(text=t("badge_safe_engine"))
        if hasattr(self, "btn_sync"):
            self.btn_sync.config(text=t("btn_google_sync"))
        if hasattr(self, "btn_add"):
            self.btn_add.config(text=t("btn_add_stock"))
        if hasattr(self, "btn_tools_menu"):
            self.btn_tools_menu.config(text=f"{t('menu_tools')} ▾")
            self._rebuild_tools_menu()
        if hasattr(self, "btn_remove"):
            self.btn_remove.config(text=t("btn_tbl_remove"))
        if hasattr(self, "btn_report"):
            self.btn_report.config(text=t("btn_report"))
        if hasattr(self, "btn_watchlist"):
            self.btn_watchlist.config(text=t("btn_watchlist"))
        if hasattr(self, "btn_web_view"):
            self.btn_web_view.config(text=t("btn_web_dashboard"))
        if hasattr(self, "btn_feature_guide"):
            self.btn_feature_guide.config(text=t("btn_feature_guide"))
        if hasattr(self, "btn_what_if"):
            self.btn_what_if.config(text=t("btn_what_if"))
        if hasattr(self, "btn_data_health"):
            self.btn_data_health.config(text=t("btn_data_health"))
        if hasattr(self, "btn_columns"):
            self.btn_columns.config(text=t("btn_column_selector"))
        if hasattr(self, "btn_theme_toggle"):
            self.btn_theme_toggle.config(text=t("btn_theme_light") if self.dark_mode else t("btn_theme_dark"))
        if hasattr(self, "lbl_auto"):
            self.lbl_auto.config(text=t("lbl_auto"))
        if hasattr(self, "btn_refresh"):
            self.btn_refresh.config(text=t("btn_refresh"))
        if hasattr(self, "btn_import"):
            self.btn_import.config(text=t("btn_import_csv"))
        if hasattr(self, "btn_export"):
            self.btn_export.config(text=t("btn_export_csv"))
        if hasattr(self, "btn_backups"):
            self.btn_backups.config(text=t("btn_backups"))

        # 3. Update Portfolio bar
        if hasattr(self, "lbl_portfolio"):
            self.lbl_portfolio.config(text=t("lbl_portfolio"))
        if hasattr(self, "btn_new_portfolio"):
            self.btn_new_portfolio.config(text=t("btn_new_portfolio"))
        if hasattr(self, "btn_rename_portfolio"):
            self.btn_rename_portfolio.config(text=t("btn_rename_portfolio"))
        if hasattr(self, "btn_delete_portfolio"):
            self.btn_delete_portfolio.config(text=t("btn_delete_portfolio"))
        if hasattr(self, "btn_portfolio_fees"):
            self.btn_portfolio_fees.config(text=t("btn_portfolio_fees"))
        if hasattr(self, "lbl_summary_in"):
            self.lbl_summary_in.config(text=t("lbl_summary_in"))

        # 4. Update Notebook tab titles
        if hasattr(self, "notebook"):
            tab_map = [
                (getattr(self, "tab_holdings", None), t("tab_holdings")),
                (getattr(self, "tab_analytics", None), t("tab_analytics")),
                (getattr(self, "tab_chart", None), t("tab_chart")),
                (getattr(self, "tab_dividend", None), t("tab_dividend")),
                (getattr(self, "tab_fire", None), t("tab_fire")),
                (getattr(self, "tab_split", None), t("tab_split")),
                (getattr(self, "tab_sell", None), t("tab_selling")),
                (getattr(self, "tab_history", None), t("tab_transactions")),
                (getattr(self, "tab_report", None), t("tab_report")),
                (getattr(self, "tab_watchlist", None), t("tab_monitoring")),
            ]
            for tab_widget, text in tab_map:
                if tab_widget is not None:
                    try:
                        self.notebook.tab(tab_widget, text=text)
                    except Exception:
                        pass

        # 5. Update Holdings tab
        if hasattr(self, "lbl_search"):
            self.lbl_search.config(text=t("lbl_search"))
        if hasattr(self, "lbl_filter"):
            self.lbl_filter.config(text=t("lbl_filter"))
        if hasattr(self, "holdings_tree"):
            headers = [
                ("portfolio", t("col_portfolio")),
                ("symbol", t("col_symbol")),
                ("name", t("col_name")),
                ("currency", t("col_currency")),
                ("shares", t("col_shares")),
                ("buy_price", t("col_buy_price")),
                ("current_price", t("col_current_price")),
                ("change", t("col_day_change")),
                ("market_value", t("col_market_value")),
                ("cost_basis", t("col_cost_basis")),
                ("unrealized_gain", t("col_unrealized_gain")),
                ("unrealized_gain_pct", t("col_unrealized_pct")),
                ("div_yield", t("col_dividend_yield")),
                ("annual_div", t("col_annual_div")),
                ("updated", t("col_last_updated")),
            ]
            for col, heading in headers:
                try:
                    self.holdings_tree.heading(col, text=heading)
                except Exception:
                    pass

        if hasattr(self, "btn_tbl_add"):
            self.btn_tbl_add.config(text=t("btn_tbl_add"))
        if hasattr(self, "btn_tbl_del"):
            self.btn_tbl_del.config(text=t("btn_tbl_remove"))
        if hasattr(self, "btn_tbl_chart"):
            self.btn_tbl_chart.config(text=t("btn_tbl_chart"))
        if hasattr(self, "btn_tbl_edit"):
            self.btn_tbl_edit.config(text=t("btn_tbl_edit"))
        if hasattr(self, "btn_tbl_to_div"):
            self.btn_tbl_to_div.config(text=t("btn_tbl_to_div"))
        if hasattr(self, "btn_tbl_to_split"):
            self.btn_tbl_to_split.config(text=t("btn_tbl_to_split"))
        if hasattr(self, "btn_tbl_to_sell"):
            self.btn_tbl_to_sell.config(text=t("btn_tbl_to_sell"))

        # Context menu
        if hasattr(self, "context_menu"):
            try:
                self.context_menu.delete(0, tk.END)
                self.context_menu.add_command(label=f"📈 {t('tab_chart').strip()}", command=self._send_selected_to_chart)
                self.context_menu.add_separator()
                self.context_menu.add_command(label=f"✏️ {t('btn_tbl_edit')}", command=self._open_edit_dialog)
                self.context_menu.add_command(label=f"➖ {t('btn_tbl_remove')}", command=self._delete_selected_holding)
                self.context_menu.add_separator()
                self.context_menu.add_command(label=f"🔄 {t('btn_refresh')}", command=self._refresh_selected_quote)
                self.context_menu.add_separator()
                self.context_menu.add_command(label=f"💵 {t('btn_tbl_to_div')}", command=self._send_selected_to_dividend_calc)
                self.context_menu.add_command(label=f"✂️ {t('btn_tbl_to_split')}", command=self._send_selected_to_split_calc)
                self.context_menu.add_command(label=f"🏷️ {t('btn_tbl_to_sell')}", command=self._send_selected_to_selling_calc)
            except Exception:
                pass

        # 6. Update Analytics tab
        if hasattr(self, "analytics_left_box"):
            self.analytics_left_box.config(text=f" {t('alloc_chart_title')} ")
        if hasattr(self, "analytics_right_box"):
            self.analytics_right_box.config(text=f" {t('health_box_title')} ")
        if hasattr(self, "analytics_kpis"):
            kpi_labels = {
                "top_asset": t("kpi_top_position"),
                "concentration": t("kpi_concentration"),
                "portfolio_yoc": t("kpi_yield_on_cost"),
                "div_yield": t("kpi_avg_dividend_yield"),
                "best_performer": t("kpi_best_performer"),
                "worst_performer": t("kpi_worst_performer"),
                "sharpe": t("metric_sharpe"),
                "max_drawdown": t("metric_max_drawdown"),
                "volatility": t("metric_volatility"),
                "cagr": t("metric_cagr"),
            }
            for k, lbl in kpi_labels.items():
                if k in self.analytics_kpis:
                    try:
                        self.analytics_kpis[k][1].config(text=lbl)
                    except Exception:
                        pass
        if hasattr(self, "lbl_alloc_mode"):
            self.lbl_alloc_mode.config(text=t("lbl_alloc_view_mode"))
        if hasattr(self, "alloc_mode_combo"):
            current_m = getattr(self, "alloc_view_mode", "assets")
            self.alloc_mode_combo.config(values=[t("alloc_view_assets"), t("alloc_view_currency"), t("alloc_view_sector")])
            mapping_alloc = {
                "assets": t("alloc_view_assets"),
                "currency": t("alloc_view_currency"),
                "sector": t("alloc_view_sector"),
            }
            self.alloc_mode_combo.set(mapping_alloc.get(current_m, t("alloc_view_assets")))
        if hasattr(self, "lbl_alloc_weights"):
            self.lbl_alloc_weights.config(text=t("lbl_alloc_weights"))
        if hasattr(self, "alloc_tree"):
            try:
                self.alloc_tree.heading("symbol", text=t("col_symbol"))
                self.alloc_tree.heading("name", text=t("col_name"))
                self.alloc_tree.heading("value", text=t("col_market_value"))
                self.alloc_tree.heading("weight", text=t("col_weight"))
            except Exception:
                pass

        # 7. Update Transaction History tab
        if hasattr(self, "lbl_hist_filter"):
            self.lbl_hist_filter.config(text=t("lbl_filter_history"))
        if hasattr(self, "lbl_tx_port"):
            self.lbl_tx_port.config(text=t("lbl_tx_portfolio"))
        if hasattr(self, "lbl_tx_type"):
            self.lbl_tx_type.config(text=t("lbl_tx_type"))
        if hasattr(self, "tx_type_filter_cb"):
            cur_idx = self.tx_type_filter_cb.current()
            new_vals = [t("tx_type_all"), t("tx_type_buy"), t("tx_type_sell")]
            self.tx_type_filter_cb.config(values=new_vals)
            if 0 <= cur_idx < len(new_vals):
                self.tx_type_filter_var.set(new_vals[cur_idx])
            else:
                self.tx_type_filter_var.set(t("tx_type_all"))

        if hasattr(self, "btn_tx_all"):
            self.btn_tx_all.config(text=t("btn_tx_all"))
        if hasattr(self, "btn_tx_match"):
            self.btn_tx_match.config(text=t("btn_tx_match"))
        if hasattr(self, "btn_tx_record"):
            self.btn_tx_record.config(text=t("btn_tx_record"))
        if hasattr(self, "btn_tx_edit"):
            self.btn_tx_edit.config(text=t("btn_tx_edit"))
        if hasattr(self, "btn_tx_report"):
            self.btn_tx_report.config(text=t("btn_tx_report"))
        if hasattr(self, "btn_tx_storage_fee"):
            self.btn_tx_storage_fee.config(text=t("btn_log_storage_fee"))
        if hasattr(self, "btn_tx_export"):
            self.btn_tx_export.config(text=t("btn_tx_export"))
        if hasattr(self, "btn_tx_clear"):
            self.btn_tx_clear.config(text=t("btn_tx_clear"))

        if hasattr(self, "history_tree"):
            hist_headers = [
                ("date", t("col_tx_date")),
                ("type", t("col_tx_type")),
                ("portfolio", t("col_tx_port")),
                ("symbol", t("col_tx_sym")),
                ("currency", t("col_tx_curr")),
                ("shares", t("col_tx_shares")),
                ("price", t("col_tx_price")),
                ("total_amount", t("col_tx_total")),
                ("commission", t("col_tx_fees")),
                ("tax", t("col_tx_tax")),
                ("net_profit", t("col_tx_profit")),
                ("roi", t("col_tx_roi")),
            ]
            for col, heading in hist_headers:
                try:
                    self.history_tree.heading(col, text=heading)
                except Exception:
                    pass

        # 7b. Update FIRE Tab
        if hasattr(self, "lbl_fire_title"):
            self.lbl_fire_title.config(text=f"🔥 {t('tab_fire').strip()} — {t('fire_title_header')}")
        if hasattr(self, "lbl_fire_sub"):
            self.lbl_fire_sub.config(text=t("fire_sub_desc"))
        if hasattr(self, "fire_s1_box"):
            self.fire_s1_box.config(text=f" {t('fire_step1_title')} ")
        if hasattr(self, "lbl_fire_outside"):
            self.lbl_fire_outside.config(text=t("lbl_outside_safe_assets"))
        if hasattr(self, "fire_holdings_tree"):
            fire_cols = [
                ("symbol", t("col_symbol")),
                ("name", t("col_name")),
                ("value", t("col_market_value")),
                ("weight", t("col_weight")),
                ("asset_class", t("lbl_holding_asset_class")),
            ]
            for col, heading_txt in fire_cols:
                try:
                    self.fire_holdings_tree.heading(col, text=heading_txt, command=lambda c=col: self._sort_fire_holdings_by(c))
                except Exception:
                    pass
        if hasattr(self, "fire_s2_box"):
            self.fire_s2_box.config(text=f" {t('fire_step2_title')} ")
        if hasattr(self, "lbl_fire_cur_age"):
            self.lbl_fire_cur_age.config(text=t("lbl_current_age"))
        if hasattr(self, "lbl_fire_retire_age"):
            self.lbl_fire_retire_age.config(text=t("lbl_retire_age"))
        if hasattr(self, "lbl_fire_horizon"):
            self.lbl_fire_horizon.config(text=t("lbl_life_expectancy"))
        if hasattr(self, "lbl_fire_safe_years"):
            self.lbl_fire_safe_years.config(text=t("lbl_safe_years"))
        if hasattr(self, "fire_delay_check"):
            self.fire_delay_check.config(text=t("lbl_delay_pension"))
        if hasattr(self, "fire_s3_box"):
            self.fire_s3_box.config(text=f" {t('fire_step3_title')} ")
        if hasattr(self, "lbl_fire_preset_profiles"):
            self.lbl_fire_preset_profiles.config(text=f"{t('lbl_preset_profiles')} ")
        if hasattr(self, "fire_btn_persona_young"):
            self.fire_btn_persona_young.config(text=t("preset_young"))
        if hasattr(self, "fire_btn_persona_trans"):
            self.fire_btn_persona_trans.config(text=t("preset_transition"))
        if hasattr(self, "fire_btn_persona_fritz"):
            self.fire_btn_persona_fritz.config(text=t("preset_fritz"))
        if hasattr(self, "fire_btn_persona_frank"):
            self.fire_btn_persona_frank.config(text=t("preset_frank"))
        if hasattr(self, "lbl_fire_quick_exp"):
            self.lbl_fire_quick_exp.config(text=f"{t('lbl_quick_exp')} ")
        if hasattr(self, "lbl_fire_exp"):
            self.lbl_fire_exp.config(text=t("lbl_target_monthly_expense"))
        if hasattr(self, "lbl_fire_pension"):
            self.lbl_fire_pension.config(text=t("lbl_guaranteed_pension"))
        if hasattr(self, "lbl_fire_savings"):
            self.lbl_fire_savings.config(text=t("lbl_monthly_savings"))
        if hasattr(self, "lbl_fire_growth"):
            self.lbl_fire_growth.config(text=t("lbl_dividend_growth_rate"))
        if hasattr(self, "fire_s4_box"):
            self.fire_s4_box.config(text=f" {t('fire_step4_title')} ")
        if hasattr(self, "lbl_fire_safe_title"):
            self.lbl_fire_safe_title.config(text=f"🛡️ {t('lbl_safe_asset_gap')}")
        if hasattr(self, "lbl_fire_chips"):
            self.lbl_fire_chips.config(text=t("fire_chips_lbl"))
        if hasattr(self, "lbl_fire_div_title"):
            self.lbl_fire_div_title.config(text=f"💵 {t('lbl_dividend_gap')}")
        if hasattr(self, "lbl_fire_cap_title"):
            self.lbl_fire_cap_title.config(text=f"🏛️ {t('lbl_capital_gap')}")
        if hasattr(self, "fire_s5_box"):
            self.fire_s5_box.config(text=f" {t('fire_step5_title')} ")
        if hasattr(self, "fire_action_box"):
            self.fire_action_box.config(text=f" {t('fire_bottom_actions_title')} ")
        if hasattr(self, "lbl_fire_models_suite"):
            self.lbl_fire_models_suite.config(text=f"🏛️ {t('lbl_fire_models_suite')}")
        if hasattr(self, "lbl_fire_actions_suite"):
            self.lbl_fire_actions_suite.config(text=f"⚡ {t('lbl_fire_actions_suite')}")
        if hasattr(self, "btn_fire_to_rebalance"):
            self.btn_fire_to_rebalance.config(text=t("btn_apply_to_rebalance"))
        if hasattr(self, "btn_fire_simulate"):
            self.btn_fire_simulate.config(text=t("btn_simulate_trade"))
        if hasattr(self, "btn_fire_toolkit"):
            self.btn_fire_toolkit.config(text=f"🚀 {t('btn_fire_toolkit')}")
        if hasattr(self, "btn_fire_toolkit_bar"):
            self.btn_fire_toolkit_bar.config(text=f"🚀 {t('btn_fire_toolkit')}")
        if hasattr(self, "btn_fire_deep_risk"):
            self.btn_fire_deep_risk.config(text=t("btn_deep_risk_short"))
        if hasattr(self, "btn_fire_crisis_stress"):
            self.btn_fire_crisis_stress.config(text=t("btn_crisis_stress_short"))
        if hasattr(self, "btn_fire_tax_drag"):
            self.btn_fire_tax_drag.config(text=t("btn_fee_tax_drag_short"))
        if hasattr(self, "btn_fire_rebalance_5_25"):
            self.btn_fire_rebalance_5_25.config(text=t("btn_rebalance_5_25_short"))
        if hasattr(self, "btn_fire_simplicity"):
            self.btn_fire_simplicity.config(text=t("btn_simplicity_short"))
        if hasattr(self, "btn_fire_recalc"):
            self.btn_fire_recalc.config(text=f"🔄 {t('btn_recalc_fire')}")
        if hasattr(self, "btn_fire_export"):
            self.btn_fire_export.config(text=t("btn_export_fire_report"))

        # 8. Update Dividend & DRIP Tab
        if hasattr(self, "div_param_box"):
            self.div_param_box.config(text=f" {t('div_param_box')} ")
        if hasattr(self, "lbl_div_select"):
            self.lbl_div_select.config(text=t("lbl_select_from_portfolio"))
        if hasattr(self, "div_input_labels"):
            div_lbl_map = {
                "ticker": t("col_symbol") + ":",
                "shares": t("col_shares") + ":",
                "current_price": t("col_current_price") + " ($):",
                "buy_price": t("col_buy_price") + " ($):",
                "purchase_date": t("lbl_purchase_date"),
                "div_yield": t("col_dividend_yield") + " (%):",
                "div_per_share": t("lbl_div_per_share"),
            }
            for k, text in div_lbl_map.items():
                if k in self.div_input_labels:
                    self.div_input_labels[k].config(text=text)
        if hasattr(self, "btn_calc_div"):
            self.btn_calc_div.config(text=t("btn_calc_div"))
        if hasattr(self, "btn_record_drip"):
            self.btn_record_drip.config(text=t("btn_book_drip"))
        if hasattr(self, "btn_show_cal"):
            self.btn_show_cal.config(text=f"📅 {t('grp_dividend_calendar')}")
        if hasattr(self, "lbl_drip_settings"):
            self.lbl_drip_settings.config(text=t("lbl_drip_settings"))
        if hasattr(self, "lbl_drip_years"):
            self.lbl_drip_years.config(text=t("lbl_drip_years"))
        if hasattr(self, "lbl_drip_div_growth"):
            self.lbl_drip_div_growth.config(text=t("lbl_drip_div_growth"))
        if hasattr(self, "lbl_drip_price_growth"):
            self.lbl_drip_price_growth.config(text=t("lbl_drip_price_growth"))
        if hasattr(self, "lbl_drip_monthly"):
            self.lbl_drip_monthly.config(text=t("lbl_drip_monthly"))
        if hasattr(self, "btn_calc_drip"):
            self.btn_calc_drip.config(text=t("btn_calc_drip"))

        if hasattr(self, "div_earned_box"):
            self.div_earned_box.config(text=f" {t('div_sec_earned_already')} ")
        if hasattr(self, "div_earned_title_labels"):
            earned_titles = {
                "cost_basis": t("lbl_cost_basis_invested"),
                "market_value": t("card_total_value"),
                "capital_gain": t("lbl_capital_gain_so_far"),
                "past_dividends": t("lbl_past_divs_earned"),
                "total_earned": t("lbl_total_earned_already"),
                "cagr": t("lbl_cagr"),
            }
            for k, text in earned_titles.items():
                if k in self.div_earned_title_labels:
                    self.div_earned_title_labels[k].config(text=text)

        if hasattr(self, "div_future_box"):
            self.div_future_box.config(text=f" {t('div_sec_future_earnings')} ")
        if hasattr(self, "div_milestone_title_labels"):
            ms_titles = {
                1: t("lbl_milestone_1yr"),
                3: t("lbl_milestone_3yr"),
                5: t("lbl_milestone_5yr"),
                10: t("lbl_milestone_10yr"),
            }
            for yr, text in ms_titles.items():
                if yr in self.div_milestone_title_labels:
                    self.div_milestone_title_labels[yr].config(text=text)

        if hasattr(self, "div_income_box"):
            self.div_income_box.config(text=f" {t('div_sec_projections')} ")
        if hasattr(self, "div_income_title_labels"):
            inc_titles = {
                "annual_total": t("div_proj_annual") + " ($):",
                "quarterly_total": t("div_proj_quarterly") + " ($):",
                "monthly_total": t("div_proj_monthly") + " ($):",
                "yield_on_cost": t("div_proj_yoc") + ":",
                "div_per_share": t("lbl_div_per_share"),
            }
            for k, text in inc_titles.items():
                if k in self.div_income_title_labels:
                    self.div_income_title_labels[k].config(text=text)

        if hasattr(self, "div_drip_box"):
            self.div_drip_box.config(text=f" {t('div_sec_drip')} ")
        if hasattr(self, "drip_tree"):
            drip_col_headers = [
                ("year", t("col_year")),
                ("shares", t("col_drip_shares")),
                ("price", t("col_current_price")),
                ("annual_div", t("col_drip_income")),
                ("portfolio_val", t("col_drip_val")),
                ("invested", t("col_cost_basis")),
                ("profit", t("col_unrealized_gain")),
            ]
            for col, text in drip_col_headers:
                try:
                    self.drip_tree.heading(col, text=text)
                except Exception:
                    pass

        # 9. Update Split Tab
        if hasattr(self, "split_param_box"):
            self.split_param_box.config(text=f" {t('split_param_box')} ")
        if hasattr(self, "lbl_split_holding"):
            self.lbl_split_holding.config(text=t("lbl_split_holding"))
        if hasattr(self, "lbl_split_sym"):
            self.lbl_split_sym.config(text=t("col_symbol") + ":")
        if hasattr(self, "lbl_split_shares"):
            self.lbl_split_shares.config(text=t("col_shares") + ":")
        if hasattr(self, "lbl_split_before_price"):
            self.lbl_split_before_price.config(text=t("lbl_split_before_price"))
        if hasattr(self, "lbl_split_cur_price"):
            self.lbl_split_cur_price.config(text=t("lbl_split_current_price"))
        if hasattr(self, "lbl_split_purchase_date"):
            self.lbl_split_purchase_date.config(text=t("lbl_purchase_date"))
        if hasattr(self, "lbl_split_target_price"):
            self.lbl_split_target_price.config(text=t("lbl_split_target_price"))
        if hasattr(self, "btn_split_recov"):
            self.btn_split_recov.config(text="🎯 " + t("lbl_split_presplit_recovery"))
        if hasattr(self, "lbl_split_ratio"):
            self.lbl_split_ratio.config(text=t("lbl_split_ratio"))
        if hasattr(self, "lbl_ratio_to"):
            self.lbl_ratio_to.config(text=t("lbl_ratio_to"))
        if hasattr(self, "lbl_ratio_from"):
            self.lbl_ratio_from.config(text=t("lbl_ratio_for_every"))
        if hasattr(self, "btn_calc_split"):
            self.btn_calc_split.config(text=t("btn_calc_split"))
        if hasattr(self, "btn_apply_split"):
            self.btn_apply_split.config(text="✅ " + t("btn_apply_split"))

        if hasattr(self, "split_earned_box"):
            self.split_earned_box.config(text=f" {t('split_sec_earned_already')} ")
        if hasattr(self, "split_earned_title_labels"):
            earned_titles = {
                "cost_basis": t("lbl_cost_basis_invested"),
                "market_value": t("card_total_value"),
                "capital_gain": t("lbl_capital_gain_so_far"),
                "holding_period": t("lbl_holding_period"),
            }
            for k, text in earned_titles.items():
                if k in self.split_earned_title_labels:
                    self.split_earned_title_labels[k].config(text=text)

        if hasattr(self, "split_comp_box"):
            self.split_comp_box.config(text=f" {t('split_sec_comparison')} ")
        if hasattr(self, "split_before_box"):
            self.split_before_box.config(text=f" {t('split_sec_before')} ")
        if hasattr(self, "split_after_box"):
            self.split_after_box.config(text=f" {t('split_sec_after')} ")
        if hasattr(self, "split_before_title_labels"):
            b_titles = {
                "shares": t("col_shares") + ":",
                "price": t("lbl_split_cost_basis_per_share"),
                "cur_price": t("lbl_split_cur_price_per_share"),
                "total": t("lbl_split_total_cost_basis"),
                "val": t("card_total_value") + ":",
            }
            for k, text in b_titles.items():
                if k in self.split_before_title_labels:
                    self.split_before_title_labels[k].config(text=text)
        if hasattr(self, "split_after_title_labels"):
            a_titles = {
                "shares": t("lbl_split_after_shares"),
                "price": t("lbl_split_after_price"),
                "cur_price": t("lbl_split_after_effective_price"),
                "total": t("lbl_split_total_cost_basis"),
                "val": t("card_total_value") + ":",
            }
            for k, text in a_titles.items():
                if k in self.split_after_title_labels:
                    self.split_after_title_labels[k].config(text=text)

        if hasattr(self, "split_future_box"):
            self.split_future_box.config(text=f" {t('split_sec_future')} ")
        if hasattr(self, "split_future_title_labels"):
            fut_titles = {
                "target_val": t("lbl_split_future_value"),
                "total_prof": t("lbl_future_total_profit") + ":",
                "new_gain": t("lbl_split_extra_gain"),
            }
            for k, text in fut_titles.items():
                if k in self.split_future_title_labels:
                    self.split_future_title_labels[k].config(text=text)
        if hasattr(self, "lbl_split_future_scenarios"):
            self.lbl_split_future_scenarios.config(text=t("lbl_future_scenarios"))

        # 10. Update Selling & Profit Tab
        if hasattr(self, "sell_order_box"):
            self.sell_order_box.config(text=f" {t('sell_order_box')} ")
        if hasattr(self, "lbl_sell_select"):
            self.lbl_sell_select.config(text=t("lbl_select_from_portfolio"))
        if hasattr(self, "sell_input_labels"):
            sell_lbl_map = {
                "symbol": t("col_symbol") + ":",
                "shares_to_sell": t("lbl_sell_shares"),
                "buy_price": t("lbl_sell_buy_price"),
                "sell_price": t("lbl_sell_price"),
                "commission_flat": t("lbl_sell_commission_flat"),
                "commission_pct": t("lbl_sell_commission_pct"),
            }
            for k, text in sell_lbl_map.items():
                if k in self.sell_input_labels:
                    self.sell_input_labels[k].config(text=text)
        if hasattr(self, "lbl_sell_tax_bracket"):
            self.lbl_sell_tax_bracket.config(text=t("lbl_sell_tax_bracket"))
        if hasattr(self, "lbl_sell_custom_tax"):
            self.lbl_sell_custom_tax.config(text=t("lbl_sell_custom_tax"))
        if hasattr(self, "lbl_sell_tax_lot"):
            self.lbl_sell_tax_lot.config(text=t("lbl_tax_lot_method"))
        if hasattr(self, "btn_calc_sell"):
            self.btn_calc_sell.config(text=t("btn_calc_sell"))
        if hasattr(self, "btn_record_sale"):
            self.btn_record_sale.config(text="💰 " + t("btn_execute_sell"))

        if hasattr(self, "sell_res_card"):
            self.sell_res_card.config(text=f" {t('sell_res_card')} ")
        if hasattr(self, "sell_res_title_labels"):
            sell_res_titles = {
                "gross_proceeds": t("lbl_sell_gross"),
                "cost_basis": t("lbl_sell_cost"),
                "commission_fee": t("lbl_sell_commission"),
                "gross_gain": t("lbl_sell_gross_gain"),
                "estimated_tax": t("lbl_sell_estimated_tax"),
                "net_proceeds": t("lbl_sell_net_proceeds"),
                "net_profit": t("lbl_sell_profit"),
                "net_roi_pct": t("lbl_sell_roi"),
            }
            for k, text in sell_res_titles.items():
                if k in self.sell_res_title_labels:
                    self.sell_res_title_labels[k].config(text=text)

        if hasattr(self, "sell_target_card"):
            self.sell_target_card.config(text=f" {t('sell_target_card')} ")
        if hasattr(self, "lbl_breakeven_title"):
            self.lbl_breakeven_title.config(text=t("lbl_breakeven_price"))
        if hasattr(self, "lbl_target_profit_title"):
            self.lbl_target_profit_title.config(text=t("lbl_target_profit_input"))
        if hasattr(self, "btn_find_target"):
            self.btn_find_target.config(text=t("btn_find_target_price"))

        # 11. Update Period Report Tab
        if hasattr(self, "lbl_report_tab_title"):
            self.lbl_report_tab_title.config(text=f"📊 {t('tab_report').strip()}")
        if hasattr(self, "lbl_rep_port"):
            self.lbl_rep_port.config(text=t("lbl_portfolio"))
        if hasattr(self, "lbl_rep_period"):
            self.lbl_rep_period.config(text=t("lbl_filter_period"))
        if hasattr(self, "rep_period_cb"):
            self.rep_period_modes = [
                ("this_month", t("period_this_month")),
                ("this_week", t("period_this_week")),
                ("in_months", t("period_in_months")),
                ("in_weeks", t("period_in_weeks")),
                ("custom", t("period_custom")),
            ]
            self.rep_period_cb.config(values=[m[1] for m in self.rep_period_modes])
        if hasattr(self, "lbl_rep_date_range"):
            self.lbl_rep_date_range.config(text=t("lbl_date_range"))
        if hasattr(self, "lbl_rep_to"):
            self.lbl_rep_to.config(text=t("lbl_to"))
        if hasattr(self, "btn_rep_calc"):
            self.btn_rep_calc.config(text=f"🔄 {t('btn_refresh')}")
        if hasattr(self, "btn_rep_export"):
            self.btn_rep_export.config(text=t("btn_export_report_html"))
        if hasattr(self, "btn_rep_export_csv"):
            self.btn_rep_export_csv.config(text=t("btn_export_report_csv"))
        if hasattr(self, "rep_kpi_lbl_profit"):
            self.rep_kpi_lbl_profit.config(text=t("card_realized_profit"))
        if hasattr(self, "rep_kpi_lbl_roi"):
            self.rep_kpi_lbl_roi.config(text=t("card_period_roi"))
        if hasattr(self, "rep_kpi_lbl_sales"):
            self.rep_kpi_lbl_sales.config(text=t("card_sales_proceeds"))
        if hasattr(self, "rep_kpi_lbl_cost"):
            self.rep_kpi_lbl_cost.config(text=t("card_cost_sold"))
        if hasattr(self, "rep_kpi_lbl_buys"):
            self.rep_kpi_lbl_buys.config(text=t("card_buy_volume"))
        if hasattr(self, "rep_nb"):
            if hasattr(self, "rep_tab_breakdown"):
                try:
                    self.rep_nb.tab(self.rep_tab_breakdown, text=t("tab_period_breakdown"))
                except Exception:
                    pass
            if hasattr(self, "rep_tab_records"):
                try:
                    self.rep_nb.tab(self.rep_tab_records, text=t("tab_individual_records"))
                except Exception:
                    pass
        if hasattr(self, "rep_b_tree"):
            b_headers = [
                ("interval", t("col_period_interval")),
                ("trades", t("col_trades_count")),
                ("buy_vol", t("col_buy_volume")),
                ("sell_proc", t("col_sell_proceeds")),
                ("cost_basis", t("col_cost_sold")),
                ("profit", t("col_realized_profit")),
                ("roi", t("col_net_roi")),
            ]
            for c, h in b_headers:
                try:
                    self.rep_b_tree.heading(c, text=h)
                except Exception:
                    pass
        if hasattr(self, "rep_r_tree"):
            r_headers = [
                ("date", t("col_tx_date")),
                ("type", t("col_tx_type")),
                ("portfolio", t("col_tx_port")),
                ("symbol", t("col_tx_sym")),
                ("shares", t("col_tx_shares")),
                ("price", t("col_tx_price")),
                ("total", t("col_tx_total")),
                ("cost", t("col_cost_basis")),
                ("profit", t("col_tx_profit")),
                ("roi", t("col_tx_roi")),
                ("notes", t("col_notes")),
            ]
            for c, h in r_headers:
                try:
                    self.rep_r_tree.heading(c, text=h)
                except Exception:
                    pass

        # 11. Update Interactive Chart View Language
        if hasattr(self, "chart_view"):
            try:
                self.chart_view.apply_language()
            except Exception:
                pass

        # 12. Update Monitoring tab
        if hasattr(self, "lbl_watch_search"):
            self.lbl_watch_search.config(text=f"🔍 {t('lbl_watch_search')}:")
        if hasattr(self, "btn_watch_add"):
            self.btn_watch_add.config(text=t("btn_add_watchlist"))
        if hasattr(self, "btn_watch_batch"):
            self.btn_watch_batch.config(text=t("btn_batch_import"))
        if hasattr(self, "btn_watch_edit"):
            self.btn_watch_edit.config(text=f"✏️ {t('btn_edit_watchlist')}")
        if hasattr(self, "btn_watch_category"):
            self.btn_watch_category.config(text=t("btn_change_category"))
        if hasattr(self, "btn_watch_refresh"):
            self.btn_watch_refresh.config(text=t("btn_refresh"))
        if hasattr(self, "btn_watch_buy"):
            self.btn_watch_buy.config(text=t("btn_buy_into_portfolio"))
        if hasattr(self, "btn_watch_remove"):
            self.btn_watch_remove.config(text=t("btn_remove_watchlist"))
        if hasattr(self, "btn_watch_export"):
            self.btn_watch_export.config(text=t("btn_export_csv"))

        if hasattr(self, "watchlist_tree"):
            cur_trans = TRANSLATIONS.get(get_current_language(), {})
            watch_col_configs = [
                ("symbol", t("col_watch_symbol")),
                ("name", t("col_watch_name")),
                ("tags", t("lbl_watchlist_tags")),
                ("current", t("col_watch_current")),
                ("change_pct", t("col_day_change_pct")),
                ("target", t("col_watch_target")),
                ("diff", t("col_watch_diff")),
                ("pe_ratio", t("col_pe_ratio")),
                ("52w_range", t("col_52w_range")),
                ("div_yield", t("col_dividend_yield") if "col_dividend_yield" in cur_trans else "殖利率"),
                ("status", t("col_watch_status")),
                ("currency", t("col_currency")),
                ("updated", t("col_last_updated")),
                ("added_date", t("col_watch_added")),
                ("notes", t("col_notes")),
            ]
            for cid, title in watch_col_configs:
                try:
                    self.watchlist_tree.heading(cid, text=title)
                except Exception:
                    pass

        if hasattr(self, "lbl_watch_stats_title"):
            self.lbl_watch_stats_title.config(text=f"📊 {t('lbl_watch_details')}")
        if hasattr(self, "btn_view_full_stats"):
            self.btn_view_full_stats.config(text=f"📈 {t('btn_view_full_stats')}")

        if hasattr(self, "watchlist_menu"):
            try:
                self.watchlist_menu.delete(0, tk.END)
                self.watchlist_menu.add_command(label=f"📊 {t('btn_view_full_stats')}", command=self._show_watchlist_stock_stats_dialog)
                self.watchlist_menu.add_command(label=f"➕ {t('btn_buy_into_portfolio')}", command=self._buy_from_watchlist_into_portfolio)
                self.watchlist_menu.add_command(label=f"✏️ {t('btn_edit_watchlist')}", command=self._open_edit_watchlist_dialog)
                self.watchlist_menu.add_command(label=f"📈 {t('tab_chart')}", command=self._view_watchlist_chart)
                self.watchlist_menu.add_separator()
                self.watchlist_menu.add_command(label=f"🗑️ {t('btn_remove_watchlist')}", command=self._remove_selected_watchlist)
            except Exception:
                pass

        if hasattr(self, "tab_watchlist"):
            try:
                self._refresh_watchlist_tab()
            except Exception:
                pass

        # 13. Refresh views
        self._update_filter_button_styles()
        self._update_metric_cards()
        self._refresh_holdings_table()
        self._refresh_sales_table()
        self._refresh_analytics_tab()
        if hasattr(self, "rep_port_cb"):
            self._refresh_report_tab()
        if hasattr(self, "tab_fire"):
            self._refresh_fire_tab()
        self._set_status(t("ready"))

    def _build_portfolio_bar(self):
        bar = ttk.Frame(self.root, padding="12 2 12 4")
        bar.pack(fill=tk.X)

        # Portfolio selector on left
        p_box = ttk.Frame(bar)
        p_box.pack(side=tk.LEFT)

        self.lbl_portfolio = tk.Label(p_box, text=t("lbl_portfolio"), font=("Segoe UI", 9, "bold"), bg=self.bg_main)
        self.lbl_portfolio.pack(side=tk.LEFT, padx=(0, 6))

        self.portfolio_var = tk.StringVar(value=self.current_portfolio)
        self.portfolio_combo = ttk.Combobox(
            p_box,
            textvariable=self.portfolio_var,
            values=self._get_portfolio_dropdown_values(),
            width=24,
            state="readonly",
            font=("Segoe UI", 9)
        )
        self.portfolio_combo.pack(side=tk.LEFT, padx=(0, 6))
        self.portfolio_combo.bind("<<ComboboxSelected>>", self._on_portfolio_selected)

        self.btn_new_portfolio = tk.Button(
            p_box,
            text=t("btn_new_portfolio"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            command=self._create_new_portfolio,
        )
        self.btn_new_portfolio.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_rename_portfolio = tk.Button(
            p_box,
            text=t("btn_rename_portfolio"),
            font=("Segoe UI", 8),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            command=self._rename_current_portfolio,
        )
        self.btn_rename_portfolio.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_delete_portfolio = tk.Button(
            p_box,
            text=t("btn_delete_portfolio"),
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg=self.red_color,
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            command=self._delete_current_portfolio,
        )
        self.btn_delete_portfolio.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_portfolio_fees = tk.Button(
            p_box,
            text=t("btn_portfolio_fees"),
            font=("Segoe UI", 8),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            command=self._open_portfolio_fee_settings_dialog,
        )
        self.btn_portfolio_fees.pack(side=tk.LEFT, padx=(0, 16))

        # Currency summary selector on right
        curr_box = ttk.Frame(bar)
        curr_box.pack(side=tk.RIGHT)

        self.lbl_summary_in = tk.Label(curr_box, text=t("lbl_summary_in"), font=("Segoe UI", 9, "bold"), bg=self.bg_main)
        self.lbl_summary_in.pack(side=tk.LEFT, padx=(0, 6))

        self.summary_curr_var = tk.StringVar(value=self.summary_currency)
        self.curr_combo = ttk.Combobox(
            curr_box,
            textvariable=self.summary_curr_var,
            values=["USD", "EUR", "GBP", "CAD", "CNY", "HKD", "JPY", "Native"],
            width=8,
            state="readonly",
            font=("Segoe UI", 9, "bold")
        )
        self.curr_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.curr_combo.bind("<<ComboboxSelected>>", self._on_summary_currency_changed)

        self.lbl_fx_badge = tk.Label(
            curr_box,
            text=self.converter.get_rates_summary(self.summary_currency),
            font=("Segoe UI", 8),
            bg="#e8f0fe",
            fg=self.primary_color,
            padx=8,
            pady=2,
            relief="solid",
            bd=1,
        )
        self.lbl_fx_badge.pack(side=tk.LEFT, padx=(0, 4))

        btn_fx = tk.Button(
            curr_box,
            text="🔄 FX",
            font=("Segoe UI", 8),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=4,
            pady=1,
            command=self._refresh_fx_rates,
        )
        btn_fx.pack(side=tk.LEFT)

        self.lbl_curr_exposure = tk.Label(
            curr_box,
            text="",
            font=("Segoe UI", 8),
            bg="#f1f3f4",
            fg=self.text_dark,
            padx=6,
            pady=2,
            relief="solid",
            bd=1,
        )
        self.lbl_curr_exposure.pack(side=tk.LEFT, padx=(6, 0))

        # Attach hints / tooltips
        attach_tooltip(self.portfolio_combo, "tip_portfolio_select")
        attach_tooltip(self.btn_new_portfolio, "tip_new_portfolio")
        attach_tooltip(self.btn_rename_portfolio, "tip_rename_portfolio")
        attach_tooltip(self.btn_delete_portfolio, "tip_delete_portfolio")
        attach_tooltip(self.btn_portfolio_fees, "tip_portfolio_fees")
        attach_tooltip(self.curr_combo, "tip_summary_curr")
        attach_tooltip(btn_fx, "tip_fx_refresh")

    def _get_portfolio_dropdown_values(self) -> List[str]:
        all_p = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        common = ["USD HSBC", "CAD TSFA", "CAD RRSP", "USD RRSP", "USD TSFA"]
        for c in common:
            if c not in all_p:
                all_p.append(c)
        if hasattr(self, "current_portfolio") and self.current_portfolio:
            if self.current_portfolio not in ("All Portfolios (Consolidated)", "All Portfolios", "All", t("portfolio_all_consolidated")) and self.current_portfolio not in all_p:
                all_p.append(self.current_portfolio)
        res = sorted(list(set(all_p)))
        if "All Portfolios (Consolidated)" not in res:
            res.append("All Portfolios (Consolidated)")
        return res

    def _get_holding_purchase_date(self, sym: str, portfolio: Optional[str] = None) -> str:
        """
        Finds the earliest BUY transaction date for this symbol and portfolio.
        Falls back to holding last_updated date or 1 year ago.
        """
        if getattr(self, "transactions", None):
            buys = [
                tx for tx in self.transactions
                if str(tx.get("type", "")).upper() == "BUY" and str(tx.get("symbol", "")).upper() == sym.upper()
            ]
            if portfolio and portfolio != "All Portfolios (Consolidated)":
                port_buys = [tx for tx in buys if tx.get("portfolio") == portfolio]
                if port_buys:
                    buys = port_buys
            if buys:
                raw_d = str(buys[0].get("date", "")).strip()
                if raw_d:
                    # extract YYYY-MM-DD
                    import re
                    m = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", raw_d)
                    if m:
                        return m.group(1).replace("/", "-")
                    return raw_d.split()[0]

        # Fallback to holding last_updated
        h = next((x for x in getattr(self, "all_holdings", []) if str(x.get("symbol", "")).upper() == sym.upper()), None)
        if h and h.get("last_updated"):
            return str(h["last_updated"]).split()[0]

        # Default to 1 year ago
        from datetime import date, timedelta
        return (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")

    def _on_portfolio_selected(self, event=None):
        sel = self.portfolio_var.get()
        self.current_portfolio = sel
        existing_changes = {
            (h.get("portfolio"), h.get("symbol")): (h.get("change"), h.get("change_percent"))
            for h in getattr(self, "all_holdings", [])
            if h.get("change") is not None or h.get("change_percent") is not None
        }
        self.all_holdings = load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
        for h in self.all_holdings:
            k = (h.get("portfolio"), h.get("symbol"))
            if h.get("change") is None and k in existing_changes:
                h["change"], h["change_percent"] = existing_changes[k]

        if sel in ("All Portfolios (Consolidated)", "All Portfolios", "All",
                   t("portfolio_all_consolidated"), t("portfolio_all_plain")):
            self.holdings = list(self.all_holdings)
            self.root.title(f"{t('app_title')} - {t('portfolio_all_consolidated')}")
            self.transactions = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=None)
            self.sales_history = self.transactions
        else:
            self.holdings = [h for h in self.all_holdings if h.get("portfolio") == sel]
            self.root.title(f"{t('app_title')} - {sel}")
            self.transactions = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=sel)
            self.sales_history = self.transactions

        self._refresh_holdings_table()
        self._refresh_sales_table()
        self._update_metric_cards()
        self._refresh_dropdowns()
        self._refresh_analytics_tab()
        if hasattr(self, "chart_view"):
            self.chart_view.update_portfolio(sel, self.summary_currency)
        if hasattr(self, "rep_port_cb"):
            all_vals = list(self.rep_port_cb["values"])
            if sel in all_vals:
                self.rep_port_cb.set(sel)
            elif sel in ("All Portfolios (Consolidated)", "All Portfolios", "All", t("portfolio_all_consolidated"), t("portfolio_all_plain")):
                self.rep_port_cb.set(t("portfolio_all_consolidated"))
            self._refresh_report_tab()
        self._set_status(f"Switched to {sel} ({len(self.holdings)} holdings, {len(self.sales_history)} sales).")

    def _create_new_portfolio(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("btn_new_portfolio"))
        dlg.geometry("480x360")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text=t("btn_new_portfolio"),
            font=("Segoe UI", 12, "bold"),
            fg=self.primary_color,
            bg=self.bg_main,
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(frame, text=t("col_portfolio") + " Name:", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        name_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark)
        name_entry.pack(fill=tk.X, pady=(2, 10))
        name_entry.focus_set()

        tk.Label(frame, text=t("lbl_fee_preset") + ":", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        preset_keys = list(BROKER_PRESETS.keys())
        preset_labels = [f"{k} - {get_broker_preset_display_name(k)}" for k in preset_keys]
        preset_cb = ttk.Combobox(frame, values=preset_labels, state="readonly", font=("Segoe UI", 9))
        preset_cb.set(preset_labels[0])
        preset_cb.pack(fill=tk.X, pady=(2, 8))

        lbl_desc = tk.Label(
            frame,
            text="",
            font=("Segoe UI", 8),
            fg=self.text_muted,
            bg=self.bg_main,
            justify=tk.LEFT,
            wraplength=440,
        )
        lbl_desc.pack(anchor="w", pady=(0, 12))

        def on_preset_select(event=None):
            idx = preset_cb.current()
            if 0 <= idx < len(preset_keys):
                pk = preset_keys[idx]
                pdata = BROKER_PRESETS[pk]
                ctype = pdata.get("commission_type", "flat")
                comm_str = ""
                if ctype == "flat":
                    comm_str = f"Flat ${float(pdata.get('commission_flat', 0.0) or 0.0):.2f}"
                elif "percent" in ctype:
                    comm_str = f"{float(pdata.get('commission_pct', 0.0) or 0.0):.2f}% (Min ${float(pdata.get('commission_min', pdata.get('min_commission', 0.0)) or 0.0):.2f})"
                else:
                    comm_str = "$0.00 (Zero Commission)"
                st_amt = float(pdata.get("storage_fee_amount", 0.0) or 0.0)
                st_freq = pdata.get("storage_fee_frequency", pdata.get("storage_fee_freq", "monthly"))
                st_str = f"${st_amt:.2f} / {st_freq}" if st_amt > 0 else "None ($0.00)"
                memo = pdata.get("description", pdata.get("notes", ""))
                lbl_desc.config(text=t("lbl_fee_storage_custody", memo=memo, comm=comm_str, storage=st_str))

        preset_cb.bind("<<ComboboxSelected>>", on_preset_select)
        on_preset_select()

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(8, 0))

        def on_submit():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror(t("dlg_error"), t("msg_portfolio_name_empty"), parent=dlg)
                return
            vals = self._get_portfolio_dropdown_values()
            if name in vals:
                messagebox.showinfo(t("msg_notice"), t("msg_portfolio_exists", name=name), parent=dlg)
                self.portfolio_var.set(name)
                self._on_portfolio_selected()
                dlg.destroy()
                return

            idx = preset_cb.current()
            pk = preset_keys[idx] if 0 <= idx < len(preset_keys) else "ZERO_COMMISSION"
            chosen_cfg = dict(BROKER_PRESETS[pk])
            save_portfolio_fee_config(name, chosen_cfg)

            # Register permanently in registry
            add_portfolio(name)
            self.portfolio_names = get_portfolio_names(PORTFOLIO_CSV)

            self.current_portfolio = name
            self.holdings = []
            new_vals = self._get_portfolio_dropdown_values()
            self.portfolio_combo.config(values=new_vals)
            self.portfolio_var.set(name)
            self._on_portfolio_selected()
            self._set_status(f"Created new portfolio: {name} (Tariff: {chosen_cfg.get('name')})")
            dlg.destroy()

        tk.Button(
            btn_row,
            text=t("btn_cancel"),
            font=("Segoe UI", 9),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=10,
            command=dlg.destroy,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(
            btn_row,
            text=t("btn_new_portfolio"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            padx=12,
            command=on_submit,
        ).pack(side=tk.RIGHT)

    def _rename_current_portfolio(self):
        if self.current_portfolio == "All Portfolios (Consolidated)":
            messagebox.showwarning(t("msg_warning"), t("msg_cannot_modify_consolidated"), parent=self.root)
            return
        new_name = simpledialog.askstring(t("dlg_rename_portfolio_title"), t("lbl_rename_portfolio_prompt", name=self.current_portfolio), initialvalue=self.current_portfolio, parent=self.root)
        if not new_name or not new_name.strip() or new_name.strip() == self.current_portfolio:
            return
        new_name = new_name.strip()
        old_name = self.current_portfolio
        rename_portfolio(old_name, new_name, PORTFOLIO_CSV)
        rename_portfolio_fee_config(old_name, new_name)
        self.portfolio_names = get_portfolio_names(PORTFOLIO_CSV)
        self.all_holdings = load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
        self.current_portfolio = new_name
        self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
        self.portfolio_var.set(new_name)
        self._on_portfolio_selected()
        messagebox.showinfo(t("msg_success"), t("msg_portfolio_renamed", name=new_name), parent=self.root)

    def _delete_current_portfolio(self):
        if self.current_portfolio == "All Portfolios (Consolidated)":
            messagebox.showwarning(t("msg_warning"), t("msg_cannot_modify_consolidated"), parent=self.root)
            return
        ans = messagebox.askyesno(t("dlg_delete_portfolio_title"), t("msg_delete_portfolio_confirm", name=self.current_portfolio, count=len(self.holdings)), parent=self.root)
        if not ans:
            return
        delete_portfolio_fee_config(self.current_portfolio)
        delete_portfolio(self.current_portfolio, PORTFOLIO_CSV)
        self.portfolio_names = get_portfolio_names(PORTFOLIO_CSV)
        self.all_holdings = load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
        p_names = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        self.current_portfolio = p_names[0] if p_names else DEFAULT_PORTFOLIO_NAME
        self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
        self.portfolio_var.set(self.current_portfolio)
        self._on_portfolio_selected()

    def _open_portfolio_fee_settings_dialog(self, portfolio_name=None):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_fee_settings_title"))
        dlg.geometry("540x640")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text=t("dlg_fee_settings_title"),
            font=("Segoe UI", 12, "bold"),
            fg=self.primary_color,
            bg=self.bg_main,
        ).pack(anchor="w", pady=(0, 10))

        # Portfolio selection
        p_row = ttk.Frame(frame)
        p_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(p_row, text=t("col_portfolio") + ":", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))

        available_ports = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        if not available_ports:
            available_ports = [DEFAULT_PORTFOLIO_NAME]
        init_port = portfolio_name if portfolio_name and portfolio_name in available_ports else (
            self.current_portfolio if self.current_portfolio in available_ports else available_ports[0]
        )
        available_ports = sorted(list(set(available_ports)))
        port_cb = ttk.Combobox(p_row, values=available_ports, state="readonly", width=24)
        port_cb.set(init_port)
        port_cb.pack(side=tk.LEFT)

        # Broker Tariff Preset
        pr_row = ttk.Frame(frame)
        pr_row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(pr_row, text=t("lbl_fee_preset") + ":", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))

        preset_keys = list(BROKER_PRESETS.keys())
        preset_labels = [f"{k} - {get_broker_preset_display_name(k)}" for k in preset_keys]
        preset_cb = ttk.Combobox(pr_row, values=preset_labels, state="readonly", width=36)
        preset_cb.pack(side=tk.LEFT)

        # Commission fields frame
        fields_box = ttk.LabelFrame(frame, text=t("grp_comm_settings"), padding=10)
        fields_box.pack(fill=tk.X, pady=(0, 10))

        # Comm type
        f_row1 = ttk.Frame(fields_box)
        f_row1.pack(fill=tk.X, pady=(0, 6))
        tk.Label(f_row1, text=t("lbl_comm_type") + ":", font=("Segoe UI", 9), width=20, anchor="w").pack(side=tk.LEFT)
        comm_type_cb = ttk.Combobox(f_row1, values=["flat", "percent", "percent_with_min", "flat_plus_percent", "none"], state="readonly", width=18)
        comm_type_cb.pack(side=tk.LEFT)

        # Flat Comm
        f_row2 = ttk.Frame(fields_box)
        f_row2.pack(fill=tk.X, pady=(0, 6))
        tk.Label(f_row2, text=t("lbl_flat_fee") + " ($):", font=("Segoe UI", 9), width=20, anchor="w").pack(side=tk.LEFT)
        flat_entry = tk.Entry(f_row2, font=("Segoe UI", 9), bd=1, relief="solid", bg=self.card_bg, width=14)
        flat_entry.pack(side=tk.LEFT)

        # Comm Pct
        f_row3 = ttk.Frame(fields_box)
        f_row3.pack(fill=tk.X, pady=(0, 6))
        tk.Label(f_row3, text=t("lbl_pct_rate") + " (%):", font=("Segoe UI", 9), width=20, anchor="w").pack(side=tk.LEFT)
        pct_entry = tk.Entry(f_row3, font=("Segoe UI", 9), bd=1, relief="solid", bg=self.card_bg, width=14)
        pct_entry.pack(side=tk.LEFT)

        # Min Comm
        f_row4 = ttk.Frame(fields_box)
        f_row4.pack(fill=tk.X, pady=(0, 6))
        tk.Label(f_row4, text=t("lbl_min_comm") + " ($):", font=("Segoe UI", 9), width=20, anchor="w").pack(side=tk.LEFT)
        min_comm_entry = tk.Entry(f_row4, font=("Segoe UI", 9), bd=1, relief="solid", bg=self.card_bg, width=14)
        min_comm_entry.pack(side=tk.LEFT)

        # Safe Custody / Storage Fee Box
        custody_box = ttk.LabelFrame(frame, text=t("grp_custody_settings"), padding=10)
        custody_box.pack(fill=tk.X, pady=(0, 10))

        # Storage Fee Amount
        c_row1 = ttk.Frame(custody_box)
        c_row1.pack(fill=tk.X, pady=(0, 6))
        tk.Label(c_row1, text=t("lbl_storage_fee") + " ($):", font=("Segoe UI", 9), width=20, anchor="w").pack(side=tk.LEFT)
        storage_amt_entry = tk.Entry(c_row1, font=("Segoe UI", 9), bd=1, relief="solid", bg=self.card_bg, width=14)
        storage_amt_entry.pack(side=tk.LEFT)

        # Storage Fee Frequency
        c_row2 = ttk.Frame(custody_box)
        c_row2.pack(fill=tk.X, pady=(0, 6))
        tk.Label(c_row2, text=t("lbl_fee_frequency") + ":", font=("Segoe UI", 9), width=20, anchor="w").pack(side=tk.LEFT)
        freq_cb = ttk.Combobox(c_row2, values=["monthly", "quarterly", "semi-annually", "annually", "none"], state="readonly", width=14)
        freq_cb.pack(side=tk.LEFT)

        # Tax rate & Notes
        misc_box = ttk.LabelFrame(frame, text=t("lbl_memo") + " / " + t("col_notes"), padding=10)
        misc_box.pack(fill=tk.X, pady=(0, 10))

        m_row1 = ttk.Frame(misc_box)
        m_row1.pack(fill=tk.X, pady=(0, 6))
        tk.Label(m_row1, text=t("lbl_default_tax") + " (%):", font=("Segoe UI", 9), width=20, anchor="w").pack(side=tk.LEFT)
        tax_entry = tk.Entry(m_row1, font=("Segoe UI", 9), bd=1, relief="solid", bg=self.card_bg, width=14)
        tax_entry.pack(side=tk.LEFT)

        m_row2 = ttk.Frame(misc_box)
        m_row2.pack(fill=tk.X, pady=(0, 4))
        tk.Label(m_row2, text=t("col_notes") + ":", font=("Segoe UI", 9), width=20, anchor="w").pack(side=tk.LEFT)
        notes_entry = tk.Entry(m_row2, font=("Segoe UI", 9), bd=1, relief="solid", bg=self.card_bg)
        notes_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def populate_fields(cfg: Dict[str, Any]):
            comm_type_cb.set(cfg.get("commission_type", "flat"))
            flat_entry.delete(0, tk.END)
            flat_entry.insert(0, str(cfg.get("commission_flat", 0.0)))
            pct_entry.delete(0, tk.END)
            pct_entry.insert(0, str(cfg.get("commission_pct", 0.0)))
            min_comm_entry.delete(0, tk.END)
            min_comm_entry.insert(0, str(cfg.get("commission_min", cfg.get("min_commission", 0.0))))
            storage_amt_entry.delete(0, tk.END)
            storage_amt_entry.insert(0, str(cfg.get("storage_fee_amount", 0.0)))
            freq_cb.set(cfg.get("storage_fee_frequency", cfg.get("storage_fee_freq", "monthly")))
            tax_entry.delete(0, tk.END)
            tax_entry.insert(0, str(cfg.get("default_tax_rate_pct", cfg.get("tax_rate", 0.0))))
            notes_entry.delete(0, tk.END)
            notes_entry.insert(0, str(cfg.get("description", cfg.get("notes", ""))))

        def load_current_portfolio_fees():
            pt = port_cb.get().strip()
            cfg = get_portfolio_fee_config(pt)
            matched_preset = "CUSTOM"
            for pk, pv in BROKER_PRESETS.items():
                if pk != "CUSTOM" and (
                    pv.get("commission_type") == cfg.get("commission_type") and
                    float(pv.get("commission_flat", 0.0)) == float(cfg.get("commission_flat", 0.0)) and
                    float(pv.get("commission_pct", 0.0)) == float(cfg.get("commission_pct", 0.0)) and
                    float(pv.get("commission_min", pv.get("min_commission", 0.0))) == float(cfg.get("commission_min", cfg.get("min_commission", 0.0))) and
                    float(pv.get("storage_fee_amount", 0.0)) == float(cfg.get("storage_fee_amount", 0.0))
                ):
                    matched_preset = pk
                    break
            for idx, pk in enumerate(preset_keys):
                if pk == matched_preset:
                    preset_cb.current(idx)
                    break
            populate_fields(cfg)

        def on_preset_changed(event=None):
            idx = preset_cb.current()
            if 0 <= idx < len(preset_keys):
                pk = preset_keys[idx]
                pdata = BROKER_PRESETS[pk]
                populate_fields(pdata)

        port_cb.bind("<<ComboboxSelected>>", lambda e: load_current_portfolio_fees())
        preset_cb.bind("<<ComboboxSelected>>", on_preset_changed)
        load_current_portfolio_fees()

        # Action Buttons
        btn_bar = ttk.Frame(frame)
        btn_bar.pack(fill=tk.X, pady=(6, 0))

        def on_log_storage_fee_clicked():
            pt = port_cb.get().strip()
            try:
                amt = float(storage_amt_entry.get().strip())
                if amt <= 0:
                    messagebox.showinfo(t("msg_notice"), t("msg_storage_fee_zero"), parent=dlg)
                    return
            except ValueError:
                messagebox.showerror(t("dlg_error"), t("msg_storage_fee_invalid"), parent=dlg)
                return
            nt = notes_entry.get().strip() or f"{pt} Safe Custody Fee"
            log_storage_fee_transaction(pt, amt, notes=nt)
            self.sales_history = load_sales_history()
            self._refresh_sales_table()
            self._update_metric_cards()
            self._set_status(f"Logged ${amt:.2f} safe custody fee for '{pt}'.")
            messagebox.showinfo(t("msg_success"), t("msg_storage_fee_logged", amt=amt, port=pt), parent=dlg)

        def on_save_clicked():
            pt = port_cb.get().strip()
            if not pt:
                return
            try:
                cfg = {
                    "name": pt,
                    "commission_type": comm_type_cb.get().strip(),
                    "commission_flat": float(flat_entry.get().strip() or "0.0"),
                    "commission_pct": float(pct_entry.get().strip() or "0.0"),
                    "commission_min": float(min_comm_entry.get().strip() or "0.0"),
                    "min_commission": float(min_comm_entry.get().strip() or "0.0"),
                    "storage_fee_amount": float(storage_amt_entry.get().strip() or "0.0"),
                    "storage_fee_frequency": freq_cb.get().strip() or "monthly",
                    "storage_fee_freq": freq_cb.get().strip() or "monthly",
                    "default_tax_rate_pct": float(tax_entry.get().strip() or "0.0"),
                    "tax_rate": float(tax_entry.get().strip() or "0.0"),
                    "currency": "USD",
                    "description": notes_entry.get().strip(),
                    "notes": notes_entry.get().strip(),
                }
            except ValueError:
                messagebox.showerror(t("dlg_error"), t("msg_enter_positive_shares_price"), parent=dlg)
                return
            save_portfolio_fee_config(pt, cfg)
            self._set_status(f"Saved fee tariff configuration for '{pt}'.")
            messagebox.showinfo(t("msg_success"), t("msg_fees_saved"), parent=dlg)
            dlg.destroy()

        tk.Button(
            btn_bar,
            text=t("btn_log_storage_fee"),
            font=("Segoe UI", 9),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=10,
            command=on_log_storage_fee_clicked,
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_bar,
            text=t("btn_cancel"),
            font=("Segoe UI", 9),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=10,
            command=dlg.destroy,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(
            btn_bar,
            text=t("btn_save_fees"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            padx=12,
            command=on_save_clicked,
        ).pack(side=tk.RIGHT)

    def _quick_log_storage_fee(self):
        target_port = self.current_portfolio
        if target_port in ("All Portfolios (Consolidated)", "All Portfolios", "All"):
            p_names = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
            target_port = p_names[0] if p_names else DEFAULT_PORTFOLIO_NAME

        cfg = get_portfolio_fee_config(target_port)
        default_amt = float(cfg.get("storage_fee_amount", 0.0) or 0.0)

        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_log_storage_fee_title"))
        dlg.geometry("440x300")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text=t("dlg_log_storage_fee_title"),
            font=("Segoe UI", 12, "bold"),
            fg=self.primary_color,
            bg=self.bg_main,
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(frame, text=t("col_portfolio") + ":", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        p_names = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        port_cb = ttk.Combobox(frame, values=p_names, state="readonly", font=("Segoe UI", 9))
        port_cb.set(target_port)
        port_cb.pack(fill=tk.X, pady=(2, 8))

        def on_p_changed(event=None):
            p = port_cb.get().strip()
            c = get_portfolio_fee_config(p)
            amt_ent.delete(0, tk.END)
            amt_ent.insert(0, f"{float(c.get('storage_fee_amount', 0.0) or 0.0):.2f}")
            note_ent.delete(0, tk.END)
            note_ent.insert(0, f"{p} Safe Custody / Storage Fee ({c.get('storage_fee_freq', 'monthly')})")

        port_cb.bind("<<ComboboxSelected>>", on_p_changed)

        tk.Label(frame, text=t("lbl_storage_fee") + " ($):", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        amt_ent = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg)
        amt_ent.insert(0, f"{default_amt:.2f}")
        amt_ent.pack(fill=tk.X, pady=(2, 8))

        tk.Label(frame, text=t("lbl_memo") + " / " + t("col_notes") + ":", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        note_ent = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg)
        note_ent.insert(0, f"{target_port} Safe Custody / Storage Fee ({cfg.get('storage_fee_freq', 'monthly')})")
        note_ent.pack(fill=tk.X, pady=(2, 12))

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(6, 0))

        def on_confirm():
            p = port_cb.get().strip()
            try:
                amt = float(amt_ent.get().strip())
                if amt <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(t("dlg_error"), t("msg_storage_fee_invalid"), parent=dlg)
                return
            nt = note_ent.get().strip()
            log_storage_fee_transaction(p, amt, notes=nt)
            self.sales_history = load_sales_history()
            self._refresh_sales_table()
            self._update_metric_cards()
            self._set_status(f"Logged ${amt:.2f} safe custody fee for '{p}'.")
            messagebox.showinfo(t("msg_success"), t("msg_storage_fee_logged", amt=amt, port=p), parent=dlg)
            dlg.destroy()

        tk.Button(
            btn_row,
            text=t("btn_cancel"),
            font=("Segoe UI", 9),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=10,
            command=dlg.destroy,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(
            btn_row,
            text=t("btn_log_storage_fee"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            padx=12,
            command=on_confirm,
        ).pack(side=tk.RIGHT)

    def _on_summary_currency_changed(self, event=None):
        self.summary_currency = self.summary_curr_var.get()
        self._update_metric_cards()
        self._refresh_sales_table()
        self._refresh_analytics_tab()
        if hasattr(self, "chart_view"):
            self.chart_view.update_portfolio(self.current_portfolio, self.summary_currency)
        self.lbl_fx_badge.config(text=self.converter.get_rates_summary(self.summary_currency))
        self._set_status(f"Summary metrics converted to {self.summary_currency}.")

    def _refresh_fx_rates(self):
        self.converter.refresh_rates_async()
        self.root.after(1500, self._after_fx_refreshed)

    def _after_fx_refreshed(self):
        self.lbl_fx_badge.config(text=self.converter.get_rates_summary(self.summary_currency))
        self._update_metric_cards()
        self._refresh_sales_table()
        self._refresh_analytics_tab()
        self._set_status(f"Updated live exchange rates.")

    def _build_metric_cards(self):
        cards_frame = ttk.Frame(self.root, padding="12 4 12 8")
        cards_frame.pack(fill=tk.X)

        self.cards = {}
        self.card_titles = {}
        self.card_frames = []
        curr_label = getattr(self, "summary_currency", "USD")
        metrics = [
            ("total_value", f"💼 {t('card_total_value')} ({curr_label})", "$0.00", self.text_dark),
            ("total_cost", f"🏷️ {t('col_cost_basis')} ({curr_label})", "$0.00", self.text_muted),
            ("total_gain", f"📈 {t('card_unrealized_pl')} ({curr_label})", "$0.00 (+0.00%)", self.green_color),
            ("annual_dividend", f"💵 {t('card_annual_dividend')} ({curr_label})", "$0.00", self.primary_color),
            ("monthly_dividend", f"🗓️ {t('div_proj_monthly')} ({curr_label})", "$0.00", self.primary_color),
        ]

        card_tooltip_keys = {
            "total_value": "tip_card_total_value",
            "total_cost": "tip_card_total_cost",
            "total_gain": "tip_card_total_gain",
            "annual_dividend": "tip_card_annual_div",
            "monthly_dividend": "tip_card_monthly_div",
        }

        for i, (key, title, default_val, default_color) in enumerate(metrics):
            card = tk.Frame(cards_frame, bg=self.card_bg, bd=1, relief="solid", padx=12, pady=8)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4 if i > 0 else (0, 4))
            self.card_frames.append(card)

            lbl_title = tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), bg=self.card_bg, fg=self.text_muted)
            lbl_title.pack(anchor="w")
            self.card_titles[key] = lbl_title

            lbl_val = tk.Label(card, text=default_val, font=("Segoe UI", 12, "bold"), bg=self.card_bg, fg=default_color)
            lbl_val.pack(anchor="w", pady=(2, 0))

            self.cards[key] = lbl_val

            tip_k = card_tooltip_keys.get(key)
            if tip_k:
                attach_tooltip(card, tip_k)
                attach_tooltip(lbl_title, tip_k)
                attach_tooltip(lbl_val, tip_k)

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))

        # Tab 1: Portfolio Holdings
        self.tab_holdings = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_holdings, text=t("tab_holdings"))
        self._build_holdings_tab()

        # Tab 2: Allocation & Analytics
        self.tab_analytics = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_analytics, text=t("tab_analytics"))
        self._build_analytics_tab()

        # Tab 3: Interactive Chart (Google Finance style)
        self.tab_chart = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_chart, text=t("tab_chart"))
        self._build_chart_tab()

        # Tab 4: Dividend & DRIP Calculator
        self.tab_dividend = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_dividend, text=t("tab_dividend"))
        self._build_dividend_tab()

        # Tab 5: William J. Bernstein FIRE & Retirement Freedom Model
        self.tab_fire = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_fire, text=t("tab_fire"))
        self._build_fire_tab()

        # Tab 6: Stock Division / Split
        self.tab_split = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_split, text=t("tab_split"))
        self._build_split_tab()

        # Tab 6: Selling Calculator
        self.tab_sell = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_sell, text=t("tab_selling"))
        self._build_selling_tab()

        # Tab 7: Transaction History
        self.tab_history = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_history, text=t("tab_transactions"))
        self._build_history_tab()

        # Tab 8: Period Earnings Report
        self.tab_report = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_report, text=t("tab_report"))
        self._build_report_tab()

        # Tab 9: Monitoring List
        self.tab_watchlist = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_watchlist, text=t("tab_monitoring"))
        self._build_watchlist_tab()

        # Apply user's saved tab sequence
        self._apply_saved_tab_order()

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.notebook.bind("<ButtonPress-1>", self._on_tab_drag_start, add="+")
        self.notebook.bind("<B1-Motion>", self._on_tab_drag_motion, add="+")
        self.notebook.bind("<ButtonRelease-1>", self._on_tab_drag_end, add="+")
        self.notebook.bind("<Button-3>", self._on_tab_right_click, add="+")

    def _get_tab_key_maps(self):
        widget_map = {
            "holdings": getattr(self, "tab_holdings", None),
            "analytics": getattr(self, "tab_analytics", None),
            "chart": getattr(self, "tab_chart", None),
            "dividend": getattr(self, "tab_dividend", None),
            "fire": getattr(self, "tab_fire", None),
            "split": getattr(self, "tab_split", None),
            "sell": getattr(self, "tab_sell", None),
            "history": getattr(self, "tab_history", None),
            "report": getattr(self, "tab_report", None),
            "watchlist": getattr(self, "tab_watchlist", None),
        }
        key_map = {str(w): k for k, w in widget_map.items() if w is not None}
        return widget_map, key_map

    def _apply_saved_tab_order(self):
        settings = load_settings()
        saved_order = settings.get("tab_order")
        if not saved_order or not isinstance(saved_order, list):
            return
        widget_map, _ = self._get_tab_key_maps()
        for idx, key in enumerate(saved_order):
            w = widget_map.get(key)
            if w is not None:
                try:
                    self.notebook.insert(idx, w)
                except Exception:
                    pass

    def _save_current_tab_order(self):
        if not hasattr(self, "notebook"):
            return
        _, key_map = self._get_tab_key_maps()
        current_tabs = self.notebook.tabs()
        current_order = [key_map[t] for t in current_tabs if t in key_map]
        if current_order:
            save_settings({"tab_order": current_order})

    def _on_tab_drag_start(self, event):
        try:
            tab_idx_str = self.notebook.tk.call(self.notebook._w, "identify", "tab", event.x, event.y)
            if tab_idx_str != "":
                self._dragged_tab_idx = int(tab_idx_str)
            else:
                self._dragged_tab_idx = None
        except Exception:
            self._dragged_tab_idx = None

    def _on_tab_drag_motion(self, event):
        if getattr(self, "_dragged_tab_idx", None) is None:
            return
        try:
            curr_tab_idx = self.notebook.tk.call(self.notebook._w, "identify", "tab", event.x, event.y)
            if curr_tab_idx != "":
                target_idx = int(curr_tab_idx)
                if target_idx != self._dragged_tab_idx:
                    tabs = self.notebook.tabs()
                    dragged_tab = tabs[self._dragged_tab_idx]
                    self.notebook.insert(target_idx, dragged_tab)
                    self._dragged_tab_idx = target_idx
        except Exception:
            pass

    def _on_tab_drag_end(self, event):
        if getattr(self, "_dragged_tab_idx", None) is not None:
            self._dragged_tab_idx = None
            self._save_current_tab_order()

    def _on_tab_right_click(self, event):
        try:
            tab_idx_str = self.notebook.tk.call(self.notebook._w, "identify", "tab", event.x, event.y)
            if tab_idx_str == "":
                return
            clicked_idx = int(tab_idx_str)
            tabs = self.notebook.tabs()
            num_tabs = len(tabs)

            tab_menu = tk.Menu(self.root, tearoff=0)
            if clicked_idx > 0:
                tab_menu.add_command(
                    label=t("menu_move_tab_left"),
                    command=lambda: self._move_tab_by_index(clicked_idx, -1),
                )
            if clicked_idx < num_tabs - 1:
                tab_menu.add_command(
                    label=t("menu_move_tab_right"),
                    command=lambda: self._move_tab_by_index(clicked_idx, 1),
                )
            tab_menu.add_separator()
            tab_menu.add_command(
                label=t("menu_reset_tab_order"),
                command=self._reset_tab_order,
            )
            tab_menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass

    def _move_tab_by_index(self, current_idx: int, direction: int):
        tabs = self.notebook.tabs()
        target_idx = current_idx + direction
        if 0 <= target_idx < len(tabs):
            tab_widget = tabs[current_idx]
            self.notebook.insert(target_idx, tab_widget)
            self.notebook.select(tab_widget)
            self._save_current_tab_order()

    def _reset_tab_order(self):
        default_order = ["holdings", "analytics", "chart", "dividend", "split", "sell", "history", "report", "watchlist"]
        save_settings({"tab_order": default_order})
        widget_map, _ = self._get_tab_key_maps()
        for idx, key in enumerate(default_order):
            w = widget_map.get(key)
            if w is not None:
                try:
                    self.notebook.insert(idx, w)
                except Exception:
                    pass

    def _on_tab_changed(self, event=None):
        if not hasattr(self, "notebook"):
            return
        try:
            sel_tab_id = self.notebook.select()
            if hasattr(self, "tab_analytics") and sel_tab_id == str(self.tab_analytics):
                self.root.after(10, self._refresh_analytics_tab)
            elif hasattr(self, "tab_chart") and sel_tab_id == str(self.tab_chart):
                if hasattr(self, "chart_view"):
                    self.chart_view.update_portfolio(self.current_portfolio, self.summary_currency)
            elif hasattr(self, "tab_report") and sel_tab_id == str(self.tab_report):
                self.root.after(10, self._refresh_report_tab)
            elif hasattr(self, "tab_fire") and sel_tab_id == str(self.tab_fire):
                self.root.after(10, self._refresh_fire_tab)
            elif hasattr(self, "tab_watchlist") and sel_tab_id == str(self.tab_watchlist):
                self.root.after(10, self._refresh_watchlist_tab)
                self.root.after(150, self._check_and_fetch_missing_watchlist_quotes)
        except Exception:
            pass

    def _build_analytics_tab(self):
        tab = self.tab_analytics
        container = ttk.Frame(tab, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        # Left: Donut Chart Canvas
        left_box = tk.LabelFrame(
            container,
            text=f" {t('alloc_chart_title')} ",
            font=("Segoe UI", 10, "bold"),
            bg=self.card_bg,
            fg=self.primary_color,
            padx=8,
            pady=8,
        )
        left_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        self.analytics_left_box = left_box

        top_ctrl = tk.Frame(left_box, bg=self.card_bg)
        top_ctrl.pack(fill=tk.X, pady=(0, 6))
        self.lbl_alloc_mode = tk.Label(
            top_ctrl,
            text=t("lbl_alloc_view_mode"),
            font=("Segoe UI", 9, "bold"),
            bg=self.card_bg,
            fg=self.text_dark,
        )
        self.lbl_alloc_mode.pack(side=tk.LEFT, padx=(2, 4))
        self.alloc_mode_combo = ttk.Combobox(
            top_ctrl,
            state="readonly",
            width=32,
            values=[t("alloc_view_assets"), t("alloc_view_currency"), t("alloc_view_sector")],
        )
        self.alloc_mode_combo.set(t("alloc_view_assets"))
        self.alloc_mode_combo.pack(side=tk.LEFT, padx=(0, 4))
        self.alloc_mode_combo.bind("<<ComboboxSelected>>", self._on_alloc_mode_changed)

        self.donut_canvas = tk.Canvas(left_box, bg=self.card_bg, highlightthickness=0)
        self.donut_canvas.pack(fill=tk.BOTH, expand=True)
        self.donut_canvas.bind("<Configure>", lambda e: self._draw_donut())

        # Right: KPI Cards and Concentration Weights
        right_box = tk.LabelFrame(
            container,
            text=f" {t('health_box_title')} ",
            font=("Segoe UI", 10, "bold"),
            bg=self.card_bg,
            fg=self.primary_color,
            padx=10,
            pady=8,
            width=420,
        )
        right_box.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False)
        self.analytics_right_box = right_box

        # KPI mini cards in 5x2 grid (Health & Risk Analytics)
        kpi_grid = ttk.Frame(right_box)
        kpi_grid.pack(fill=tk.X, pady=(0, 10))

        self.analytics_kpis = {}
        items = [
            ("top_asset", t("kpi_top_position"), "-", self.primary_color),
            ("concentration", t("kpi_concentration"), "0.0%", self.text_dark),
            ("portfolio_yoc", t("kpi_yield_on_cost"), "0.00%", self.green_color),
            ("div_yield", t("kpi_avg_dividend_yield"), "0.00%", self.primary_color),
            ("best_performer", t("kpi_best_performer"), "-", self.green_color),
            ("worst_performer", t("kpi_worst_performer"), "-", self.red_color),
            ("sharpe", t("metric_sharpe"), "0.00", self.primary_color),
            ("max_drawdown", t("metric_max_drawdown"), "0.00%", self.red_color),
            ("volatility", t("metric_volatility"), "0.00%", self.text_dark),
            ("cagr", t("metric_cagr"), "0.00%", self.green_color),
        ]

        for idx, (k, label, def_val, col) in enumerate(items):
            r = idx // 2
            c = idx % 2
            cell = tk.Frame(kpi_grid, bg=self.card_bg, bd=1, relief="solid", padx=8, pady=5)
            cell.grid(row=r, column=c, sticky="nsew", padx=3, pady=2)
            kpi_grid.columnconfigure(c, weight=1)

            lbl_t = tk.Label(cell, text=label, font=("Segoe UI", 8), bg=self.card_bg, fg=self.text_muted)
            lbl_t.pack(anchor="w")
            lbl_v = tk.Label(cell, text=def_val, font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=col)
            lbl_v.pack(anchor="w")
            self.analytics_kpis[k] = (cell, lbl_t, lbl_v)

        # Ranked Position Weights Tree
        self.lbl_alloc_weights = tk.Label(
            right_box,
            text=t("lbl_alloc_weights"),
            font=("Segoe UI", 9, "bold"),
            bg=self.card_bg,
            fg=self.text_dark,
        )
        self.lbl_alloc_weights.pack(anchor="w", pady=(6, 4))

        breakdown_frame = ttk.Frame(right_box)
        breakdown_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("symbol", "name", "value", "weight")
        self.alloc_tree = ttk.Treeview(breakdown_frame, columns=cols, show="headings", height=8)
        self.alloc_tree.heading("symbol", text=t("col_symbol"))
        self.alloc_tree.column("symbol", width=70, anchor="center")
        self.alloc_tree.heading("name", text=t("col_name"))
        self.alloc_tree.column("name", width=125, anchor="w")
        self.alloc_tree.heading("value", text=t("col_market_value"))
        self.alloc_tree.column("value", width=95, anchor="e")
        self.alloc_tree.heading("weight", text=t("col_weight"))
        self.alloc_tree.column("weight", width=70, anchor="e")

        alloc_scroll = ttk.Scrollbar(breakdown_frame, orient=tk.VERTICAL, command=self.alloc_tree.yview)
        self.alloc_tree.configure(yscrollcommand=alloc_scroll.set)
        alloc_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.alloc_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.btn_rebalance_portfolio = tk.Button(
            right_box,
            text=t("btn_rebalance_portfolio"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            padx=8,
            pady=4,
            command=self._open_rebalance_dialog,
        )
        self.btn_rebalance_portfolio.pack(fill=tk.X, pady=(6, 2))

    def _on_alloc_mode_changed(self, event=None):
        val = self.alloc_mode_combo.get()
        if t("alloc_view_sector") in val or "sector" in val.lower() or "行業" in val or "行业" in val:
            self.alloc_view_mode = "sector"
        elif t("alloc_view_currency") in val or "currency" in val.lower() or "貨幣" in val or "货币" in val:
            self.alloc_view_mode = "currency"
        else:
            self.alloc_view_mode = "assets"
        self._refresh_analytics_tab()

    def _draw_donut(self):
        if not hasattr(self, "donut_canvas"):
            return
        base_curr = self.summary_currency if hasattr(self, "summary_currency") else "USD"
        fx_rates = getattr(self.fetcher, "fx_cache", {})
        metrics = calc_portfolio_metrics(self.holdings, base_curr, fx_rates)
        port_name_display = t("portfolio_all_consolidated") if self.current_portfolio in ("All Portfolios (Consolidated)", "All Portfolios", "All") else self.current_portfolio

        alloc_mode = getattr(self, "alloc_view_mode", "assets")
        if alloc_mode == "sector":
            sec_allocs = metrics.get("sector_allocations", [])
            if isinstance(sec_allocs, list):
                labels = [d.get("sector", "") for d in sec_allocs]
                values = [d.get("value_base", 0.0) for d in sec_allocs]
            else:
                labels = list(sec_allocs.keys())
                values = [d["value_base"] for d in sec_allocs.values()]
            port_title = f"{t('alloc_view_sector')} ({base_curr}) - {port_name_display}"
        elif alloc_mode == "currency":
            curr_allocs = metrics.get("currency_allocations", [])
            labels = [c["currency"] for c in curr_allocs]
            values = [c["value_base"] for c in curr_allocs]
            port_title = f"{t('alloc_view_currency')} ({base_curr}) - {port_name_display}"
        else:
            allocs = metrics.get("allocations", [])
            labels = [a["symbol"] for a in allocs]
            values = [a["value_base"] for a in allocs]
            port_title = f"{t('alloc_chart_title')} ({base_curr}) - {port_name_display}"

        tot = metrics.get("total_value", 0.0)
        sym_char = self.converter.CURRENCY_SYMBOLS.get(base_curr, "$")
        center_str = f"{sym_char}{tot:,.2f}"
        draw_donut_chart(
            self.donut_canvas,
            labels=labels,
            values=values,
            title=port_title,
            center_text=center_str,
            dark_mode=self.dark_mode,
        )

    def _refresh_analytics_tab(self):
        if not hasattr(self, "donut_canvas") or not hasattr(self, "analytics_kpis"):
            return
        base_curr = self.summary_currency if hasattr(self, "summary_currency") else "USD"
        fx_rates = getattr(self.fetcher, "fx_cache", {})
        metrics = calc_portfolio_metrics(self.holdings, base_curr, fx_rates)

        self._draw_donut()

        allocs = metrics.get("allocations", [])
        top = allocs[0] if allocs else None
        top_str = f"{top['symbol']}" if top else "-"
        conc_str = f"{metrics.get('top_concentration_pct', 0.0):.1f}%" if top else "0.0%"

        best = metrics.get("best_performer")
        worst = metrics.get("worst_performer")
        best_str = f"{best['symbol']} ({float(best.get('unrealized_gain_pct', 0.0)):+.1f}%)" if best else "-"
        worst_str = f"{worst['symbol']} ({float(worst.get('unrealized_gain_pct', 0.0)):+.1f}%)" if worst else "-"

        self.analytics_kpis["top_asset"][2].config(text=top_str)
        self.analytics_kpis["concentration"][2].config(text=conc_str)
        self.analytics_kpis["portfolio_yoc"][2].config(text=f"{metrics.get('portfolio_yoc', 0.0):.2f}%")
        self.analytics_kpis["div_yield"][2].config(text=f"{metrics.get('overall_div_yield', 0.0):.2f}%")
        self.analytics_kpis["best_performer"][2].config(text=best_str)
        self.analytics_kpis["worst_performer"][2].config(text=worst_str)

        # Quantitative Risk Metrics calculation
        chart_prices = getattr(self.chart_view, "plot_prices", None) if hasattr(self, "chart_view") else None
        chart_ts = getattr(self.chart_view, "plot_timestamps", None) if hasattr(self, "chart_view") else None
        if chart_prices and len(chart_prices) > 2:
            risk = calc_risk_and_return_metrics(chart_prices, chart_ts)
        else:
            val_pts = [float(h.get("cost_basis", 0.0) or 100.0) for h in self.holdings]
            if not val_pts:
                val_pts = [100.0, 100.0]
            val_pts.append(max(1.0, metrics.get("total_value", 100.0)))
            risk = calc_risk_and_return_metrics(val_pts)

        if "sharpe" in self.analytics_kpis:
            self.analytics_kpis["sharpe"][2].config(text=f"{risk.get('sharpe_ratio', 0.0):.2f}")
            self.analytics_kpis["max_drawdown"][2].config(text=f"{risk.get('max_drawdown_pct', 0.0):.2f}%")
            self.analytics_kpis["volatility"][2].config(text=f"{risk.get('volatility_pct', 0.0):.2f}%")
            self.analytics_kpis["cagr"][2].config(text=f"{risk.get('cagr_pct', 0.0):+.2f}%")

        for item in self.alloc_tree.get_children():
            self.alloc_tree.delete(item)

        sym_char = self.converter.CURRENCY_SYMBOLS.get(base_curr, "$")
        alloc_mode = getattr(self, "alloc_view_mode", "assets")

        if alloc_mode == "sector":
            self.lbl_alloc_weights.config(text=t("alloc_view_sector"))
            self.alloc_tree.heading("symbol", text=t("col_sector"))
            self.alloc_tree.heading("name", text=t("lbl_col_positions"))
            sec_allocs = metrics.get("sector_allocations", [])
            items = sec_allocs if isinstance(sec_allocs, list) else [{"sector": k, **v} for k, v in sec_allocs.items()]
            for s in items:
                self.alloc_tree.insert(
                    "",
                    tk.END,
                    values=(
                        s.get("sector", "Other"),
                        "Diversified Sector",
                        f"{sym_char}{s.get('value_base', 0.0):,.2f}",
                        f"{s.get('weight_pct', 0.0):.1f}%",
                    ),
                )
        elif alloc_mode == "currency":
            self.lbl_alloc_weights.config(text=t("alloc_view_currency"))
            self.alloc_tree.heading("symbol", text=t("col_currency"))
            self.alloc_tree.heading("name", text=t("lbl_col_denomination"))
            curr_allocs = metrics.get("currency_allocations", [])
            for c in curr_allocs:
                self.alloc_tree.insert(
                    "",
                    tk.END,
                    values=(
                        c["currency"],
                        f"{c['currency']} Denominated Assets",
                        f"{sym_char}{c['value_base']:,.2f}",
                        f"{c['weight_pct']:.1f}%",
                    ),
                )
        else:
            self.lbl_alloc_weights.config(text=t("lbl_alloc_weights"))
            self.alloc_tree.heading("symbol", text=t("col_symbol"))
            self.alloc_tree.heading("name", text=t("col_name"))
            for a in allocs:
                self.alloc_tree.insert(
                    "",
                    tk.END,
                    values=(
                        a["symbol"],
                        a["name"],
                        f"{sym_char}{a['value_base']:,.2f}",
                        f"{a['weight_pct']:.1f}%",
                    ),
                )

    def _build_chart_tab(self):
        self.chart_view = GoogleFinanceChartView(
            parent=self.tab_chart,
            get_holdings_callback=self._get_holdings_for_chart,
            get_currency_converter_callback=lambda: self.converter,
            default_currency=self.summary_currency,
        )
        self.chart_view.pack(fill=tk.BOTH, expand=True)

    def _get_holdings_for_chart(self, portfolio_name: str) -> List[Dict[str, Any]]:
        if portfolio_name in ("All Portfolios (Consolidated)", "All Portfolios", "All", "*"):
            return load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
        return [h for h in load_portfolio(PORTFOLIO_CSV, portfolio_name=None) if h.get("portfolio") == portfolio_name]

    def _build_status_bar(self):
        bg_col = getattr(self, "card_bg", "#e8eaed")
        fg_col = getattr(self, "text_muted", "#5f6368")
        self.status_frame = tk.Frame(self.root, bg=bg_col, height=24)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_status = tk.Label(
            self.status_frame,
            text=t("status_ready_autosaved"),
            font=("Segoe UI", 8),
            bg=bg_col,
            fg=fg_col,
            anchor="w",
            padx=8,
        )
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_time = tk.Label(
            self.status_frame,
            text="",
            font=("Segoe UI", 8),
            bg=bg_col,
            fg=fg_col,
            padx=8,
        )
        self.lbl_time.pack(side=tk.RIGHT)

        self.btn_network_warnings = tk.Button(
            self.status_frame,
            text="",
            font=("Segoe UI", 8, "bold"),
            bg="#fef7e0",
            fg="#b06000",
            relief="solid",
            bd=1,
            padx=6,
            pady=0,
            command=self._open_network_diag_dialog,
        )

    # -------------------------------------------------------------
    # Context Menu on Holdings Table
    # -------------------------------------------------------------
    def _build_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="📈 View Chart", command=self._send_selected_to_chart)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✏️ Edit Holding", command=self._open_edit_dialog)
        self.context_menu.add_command(label="➖ Remove Selected Stock(s)", command=self._delete_selected_holding)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🔄 Refresh Quote from Google", command=self._refresh_selected_quote)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="💵 Send to Dividend Calc", command=self._send_selected_to_dividend_calc)
        self.context_menu.add_command(label="✂️ Send to Stock Split Tool", command=self._send_selected_to_split_calc)
        self.context_menu.add_command(label="🏷️ Send to Selling Calc", command=self._send_selected_to_selling_calc)

        # Bind events to auto-dismiss context menu when clicking anywhere outside or pressing Esc
        self.root.bind_all("<Button-1>", self._dismiss_context_menu, add="+")
        self.root.bind_all("<Button-2>", self._dismiss_context_menu, add="+")
        self.root.bind_all("<Escape>", self._dismiss_context_menu, add="+")

    def _dismiss_context_menu(self, event=None):
        if hasattr(self, "context_menu") and self.context_menu:
            if event and hasattr(event, "widget") and str(event.widget).startswith(str(self.context_menu)):
                return
            try:
                self.context_menu.unpost()
            except Exception:
                pass

    def _show_context_menu(self, event):
        item = self.holdings_tree.identify_row(event.y)
        # If clicked slightly off-center on an already selected row, preserve selection
        if not item:
            current_sel = self.holdings_tree.selection()
            if current_sel:
                item = current_sel[0]

        if item:
            if item not in self.holdings_tree.selection():
                self.holdings_tree.selection_set(item)
            try:
                self.context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.context_menu.grab_release()
        else:
            self._dismiss_context_menu()

    # -------------------------------------------------------------
    # Tab 1: Portfolio Holdings & Live Watchlist
    # -------------------------------------------------------------
    def _clear_search(self):
        self.search_filter_var.set("")
        self._refresh_holdings_table()
        if hasattr(self, "search_entry"):
            self.search_entry.focus_set()

    def _set_performance_filter(self, mode: str):
        self.filter_performance = mode
        self._update_filter_button_styles()
        self._refresh_holdings_table()

    def _update_filter_button_styles(self):
        if not hasattr(self, "filter_buttons"):
            return
        all_c = len(self.holdings) if hasattr(self, "holdings") else 0
        gain_c = sum(1 for h in self.holdings if float(h.get("change", 0.0) or 0.0) > 0) if hasattr(self, "holdings") else 0
        lose_c = sum(1 for h in self.holdings if float(h.get("change", 0.0) or 0.0) < 0) if hasattr(self, "holdings") else 0
        lbls = {
            "All": t("filter_all", count=all_c),
            "Gainers": t("filter_gainers", count=gain_c),
            "Losers": t("filter_losers", count=lose_c),
        }
        for mode, btn in self.filter_buttons.items():
            btn.config(text=lbls.get(mode, mode))
            if mode == self.filter_performance:
                btn.config(bg=self.primary_color, fg="#ffffff")
            else:
                btn.config(bg="#ffffff" if not self.dark_mode else "#2d3342", fg=self.text_dark)

    def _build_holdings_tab(self):
        tab = self.tab_holdings

        # Search & Filter Toolbar
        sf_bar = ttk.Frame(tab, padding="8 6 8 2")
        sf_bar.pack(fill=tk.X)

        self.lbl_search = tk.Label(sf_bar, text=t("lbl_search"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark)
        self.lbl_search.pack(side=tk.LEFT, padx=(0, 4))
        self.search_entry = tk.Entry(sf_bar, textvariable=self.search_filter_var, font=("Segoe UI", 9), width=22, bd=1, relief="solid")
        self.search_entry.pack(side=tk.LEFT, padx=(0, 4))
        self.search_entry.bind("<KeyRelease>", lambda e: self._refresh_holdings_table())
        self.search_entry.bind("<Escape>", lambda e: self._clear_search())

        btn_clear = tk.Button(sf_bar, text="✕", font=("Segoe UI", 8), bg="#ffffff", relief="solid", bd=1, padx=4, pady=1, command=self._clear_search)
        btn_clear.pack(side=tk.LEFT, padx=(0, 12))

        self.lbl_filter = tk.Label(sf_bar, text=t("lbl_filter"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark)
        self.lbl_filter.pack(side=tk.LEFT, padx=(0, 4))
        self.filter_buttons = {}
        for f_mode, f_lbl in [("All", t("filter_all", count=0)), ("Gainers", t("filter_gainers", count=0)), ("Losers", t("filter_losers", count=0))]:
            btn = tk.Button(
                sf_bar,
                text=f_lbl,
                font=("Segoe UI", 8, "bold"),
                relief="flat",
                padx=8,
                pady=1,
                command=lambda m=f_mode: self._set_performance_filter(m),
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.filter_buttons[f_mode] = btn
        self._update_filter_button_styles()

        self.btn_columns = tk.Button(
            sf_bar,
            text=t("btn_column_selector"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg=self.text_dark,
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            command=self._open_column_selector,
        )
        self.btn_columns.pack(side=tk.LEFT, padx=(10, 2))

        self.lbl_holdings_count = tk.Label(sf_bar, text="", font=("Segoe UI", 8), bg=self.bg_main, fg=self.text_muted)
        self.lbl_holdings_count.pack(side=tk.RIGHT, padx=4)

        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        columns = (
            "portfolio",
            "symbol",
            "name",
            "currency",
            "shares",
            "buy_price",
            "current_price",
            "change",
            "market_value",
            "cost_basis",
            "unrealized_gain",
            "unrealized_gain_pct",
            "stop_loss",
            "target_sell",
            "div_yield",
            "annual_div",
            "updated",
        )

        # Allow multi-row selection for batch operations
        self.holdings_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")

        headers = [
            ("portfolio", t("col_portfolio"), 100),
            ("symbol", t("col_symbol"), 75),
            ("name", t("col_name"), 150),
            ("currency", t("col_currency"), 55),
            ("shares", t("col_shares"), 70),
            ("buy_price", t("col_buy_price"), 85),
            ("current_price", t("col_current_price"), 85),
            ("change", t("col_day_change"), 90),
            ("market_value", t("col_market_value"), 105),
            ("cost_basis", t("col_cost_basis"), 100),
            ("unrealized_gain", t("col_unrealized_gain"), 105),
            ("unrealized_gain_pct", t("col_unrealized_pct"), 75),
            ("stop_loss", t("col_stop_loss"), 85),
            ("target_sell", t("col_target_sell"), 85),
            ("div_yield", t("col_dividend_yield"), 75),
            ("annual_div", t("col_annual_div"), 90),
            ("updated", t("col_last_updated"), 130),
        ]

        for col, heading, width in headers:
            self.holdings_tree.heading(col, text=heading, command=lambda c=col: self._sort_holdings_by(c))
            self.holdings_tree.column(col, width=width, anchor="center" if col in ("symbol", "shares") else "e")
        self.holdings_tree.column("name", anchor="w")

        if self.visible_columns:
            try:
                self.holdings_tree["displaycolumns"] = [c for c in columns if c in self.visible_columns]
            except Exception:
                pass

        v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.holdings_tree.yview)
        h_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.holdings_tree.xview)
        self.holdings_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.holdings_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.holdings_tree.tag_configure("positive", foreground=self.green_color)
        self.holdings_tree.tag_configure("negative", foreground=self.red_color)
        self.holdings_tree.tag_configure("neutral", foreground=self.text_dark)
        self.holdings_tree.tag_configure("stop_loss_alert", background="#fce8e6", foreground="#c5221f")
        self.holdings_tree.tag_configure("target_sell_alert", background="#e6f4ea", foreground="#137333")

        # Bindings
        self.holdings_tree.bind("<Double-1>", self._on_tree_double_click)
        self.holdings_tree.bind("<Button-3>", self._show_context_menu)
        self.holdings_tree.bind("<Delete>", lambda e: self._delete_selected_holding())
        self.holdings_tree.bind("<BackSpace>", lambda e: self._delete_selected_holding())

        # Buttons below table
        btn_bar = ttk.Frame(tab, padding="8 4 8 8")
        btn_bar.pack(fill=tk.X)

        self.btn_tbl_add = tk.Button(
            btn_bar,
            text=t("btn_tbl_add"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            padx=10,
            command=self._open_add_dialog,
        )
        self.btn_tbl_add.pack(side=tk.LEFT, padx=4)

        self.btn_tbl_del = tk.Button(
            btn_bar,
            text=t("btn_tbl_remove"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg=self.red_color,
            relief="solid",
            bd=1,
            padx=8,
            command=self._delete_selected_holding,
        )
        self.btn_tbl_del.pack(side=tk.LEFT, padx=4)

        self.btn_tbl_chart = tk.Button(
            btn_bar,
            text=t("tab_chart").strip(),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg=self.primary_color,
            relief="solid",
            bd=1,
            padx=8,
            command=self._send_selected_to_chart,
        )
        self.btn_tbl_chart.pack(side=tk.LEFT, padx=4)

        self.btn_tbl_edit = tk.Button(
            btn_bar,
            text=t("btn_tbl_edit"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            command=self._open_edit_dialog,
        )
        self.btn_tbl_edit.pack(side=tk.LEFT, padx=4)

        self.btn_tbl_to_div = tk.Button(
            btn_bar,
            text=t("btn_tbl_to_div"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            command=self._send_selected_to_dividend_calc,
        )
        self.btn_tbl_to_div.pack(side=tk.LEFT, padx=4)

        self.btn_tbl_to_split = tk.Button(
            btn_bar,
            text=t("tab_split").strip(),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            command=self._send_selected_to_split_calc,
        )
        self.btn_tbl_to_split.pack(side=tk.LEFT, padx=4)

        self.btn_tbl_to_sell = tk.Button(
            btn_bar,
            text=t("btn_tbl_to_sell"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            command=self._send_selected_to_selling_calc,
        )
        self.btn_tbl_to_sell.pack(side=tk.LEFT, padx=4)

    # -------------------------------------------------------------
    # Tab 2: Dividend & DRIP Calculator
    # -------------------------------------------------------------
    # -------------------------------------------------------------
    # Tab 2: Dividend & DRIP Calculator
    # -------------------------------------------------------------
    def _build_dividend_tab(self):
        tab = self.tab_dividend

        container = ttk.Frame(tab, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        left_frame = tk.LabelFrame(container, text=f" {t('div_param_box')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=10)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.div_param_box = left_frame

        self.lbl_div_select = tk.Label(left_frame, text=t("lbl_select_from_portfolio"), font=("Segoe UI", 9, "bold"), bg="#ffffff")
        self.lbl_div_select.pack(anchor="w", pady=(0, 2))
        self.div_holding_var = tk.StringVar()
        self.div_holding_cb = ttk.Combobox(left_frame, textvariable=self.div_holding_var, state="readonly", width=22)
        self.div_holding_cb.pack(fill=tk.X, pady=(0, 6))
        self.div_holding_cb.bind("<<ComboboxSelected>>", self._on_div_holding_selected)

        self.div_inputs = {}
        self.div_input_labels = {}
        fields = [
            ("ticker", t("col_symbol") + ":", "AAPL"),
            ("shares", t("col_shares") + ":", "50"),
            ("current_price", t("col_current_price") + " ($):", "220.00"),
            ("buy_price", t("col_buy_price") + " ($):", "180.00"),
            ("purchase_date", t("lbl_purchase_date"), ""),
            ("div_yield", t("col_dividend_yield") + " (%):", "2.5"),
            ("div_per_share", t("lbl_div_per_share"), ""),
        ]

        from datetime import date, timedelta
        def_date = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")

        for key, lbl, default in fields:
            l_w = tk.Label(left_frame, text=lbl, font=("Segoe UI", 8, "bold" if "Price" in lbl or "Shares" in lbl or "Date" in lbl or "股" in lbl else "normal"), bg="#ffffff")
            l_w.pack(anchor="w", pady=(2, 0))
            self.div_input_labels[key] = l_w
            entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
            if key == "purchase_date":
                entry.insert(0, def_date)
            else:
                entry.insert(0, default)
            entry.pack(fill=tk.X, pady=(0, 2))
            self.div_inputs[key] = entry

            if key == "purchase_date":
                d_row = ttk.Frame(left_frame)
                d_row.pack(fill=tk.X, pady=(0, 2))
                for p_lbl, p_days in [("Today", 0), ("6M", 182), ("1Y", 365), ("2Y", 730)]:
                    b = tk.Button(
                        d_row,
                        text=p_lbl,
                        font=("Segoe UI", 7),
                        bg="#f1f3f4",
                        relief="solid",
                        bd=1,
                        padx=2,
                        pady=1,
                        command=lambda d=p_days: self._set_div_purchase_date_days_ago(d),
                    )
                    b.pack(side=tk.LEFT, padx=1, expand=True, fill=tk.X)
                self.div_holding_days_lbl = tk.Label(left_frame, text=t("lbl_holding_days_fmt", days=365, years=1.0), font=("Segoe UI", 8, "italic"), bg="#ffffff", fg=self.text_muted)
                self.div_holding_days_lbl.pack(anchor="w", pady=(0, 2))

        self.btn_calc_div = tk.Button(
            left_frame,
            text=t("btn_calc_div"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=4,
            command=self._calc_dividend_results,
        )
        self.btn_calc_div.pack(fill=tk.X, pady=(6, 4))

        # 1-Click DRIP Booking Button
        self.btn_record_drip = tk.Button(
            left_frame,
            text=t("btn_book_drip"),
            font=("Segoe UI", 9, "bold"),
            bg="#0d904f",
            fg="#ffffff",
            relief="flat",
            pady=4,
            command=self._open_drip_dialog,
        )
        self.btn_record_drip.pack(fill=tk.X, pady=(0, 4))

        # 12-Month Projected Calendar Schedule Button
        self.btn_show_cal = tk.Button(
            left_frame,
            text=f"📅 {t('grp_dividend_calendar')}",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg=self.primary_color,
            relief="solid",
            bd=1,
            pady=3,
            command=self._show_dividend_calendar_dialog,
        )
        self.btn_show_cal.pack(fill=tk.X, pady=(0, 4))

        # FIRE & Freedom Runway Calculator Button
        self.btn_show_fire = tk.Button(
            left_frame,
            text=t("card_fire_title"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#e37400",
            relief="solid",
            bd=1,
            pady=3,
            command=self._switch_to_fire_tab,
        )
        self.btn_show_fire.pack(fill=tk.X, pady=(0, 8))

        self.lbl_drip_settings = tk.Label(left_frame, text=t("lbl_drip_settings"), font=("Segoe UI", 9, "bold"), bg="#ffffff")
        self.lbl_drip_settings.pack(anchor="w", pady=(4, 2))
        
        self.lbl_drip_years = tk.Label(left_frame, text=t("lbl_drip_years"), font=("Segoe UI", 8), bg="#ffffff")
        self.lbl_drip_years.pack(anchor="w")
        self.drip_years_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_years_entry.insert(0, "10")
        self.drip_years_entry.pack(fill=tk.X, pady=(0, 2))

        self.lbl_drip_div_growth = tk.Label(left_frame, text=t("lbl_drip_div_growth"), font=("Segoe UI", 8), bg="#ffffff")
        self.lbl_drip_div_growth.pack(anchor="w")
        self.drip_div_growth_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_div_growth_entry.insert(0, "5.0")
        self.drip_div_growth_entry.pack(fill=tk.X, pady=(0, 2))

        self.lbl_drip_price_growth = tk.Label(left_frame, text=t("lbl_drip_price_growth"), font=("Segoe UI", 8), bg="#ffffff")
        self.lbl_drip_price_growth.pack(anchor="w")
        self.drip_price_growth_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_price_growth_entry.insert(0, "6.0")
        self.drip_price_growth_entry.pack(fill=tk.X, pady=(0, 2))

        self.lbl_drip_monthly = tk.Label(left_frame, text=t("lbl_drip_monthly"), font=("Segoe UI", 8), bg="#ffffff")
        self.lbl_drip_monthly.pack(anchor="w")
        self.drip_monthly_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_monthly_entry.insert(0, "0.0")
        self.drip_monthly_entry.pack(fill=tk.X, pady=(0, 6))

        self.btn_calc_drip = tk.Button(
            left_frame,
            text=t("btn_calc_drip"),
            font=("Segoe UI", 9, "bold"),
            bg="#34a853",
            fg="#ffffff",
            relief="flat",
            pady=4,
            command=self._calc_drip_results,
        )
        self.btn_calc_drip.pack(fill=tk.X)

        right_frame = ttk.Frame(container)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 1. Earned Already Box (From Purchase Day Till Today)
        self.div_earned_box = tk.LabelFrame(right_frame, text=f" {t('div_sec_earned_already')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=6)
        self.div_earned_box.pack(fill=tk.X, pady=(0, 6))

        self.div_earned_labels = {}
        self.div_earned_title_labels = {}
        earned_fields = [
            ("cost_basis", t("lbl_cost_basis_invested"), "$0.00"),
            ("market_value", t("card_total_value"), "$0.00"),
            ("capital_gain", t("lbl_capital_gain_so_far"), "+$0.00 (+0.00%)"),
            ("past_dividends", t("lbl_past_divs_earned"), "$0.00"),
            ("total_earned", t("lbl_total_earned_already"), "+$0.00 (+0.00%)"),
            ("cagr", t("lbl_cagr"), "0.00% / yr"),
        ]
        for i, (k, label, default) in enumerate(earned_fields):
            r = i // 3
            c = (i % 3) * 2
            t_lbl = tk.Label(self.div_earned_box, text=label, font=("Segoe UI", 8, "bold"), bg="#ffffff", fg=self.text_muted)
            t_lbl.grid(row=r * 2, column=c, sticky="w", padx=6)
            self.div_earned_title_labels[k] = t_lbl
            val_lbl = tk.Label(self.div_earned_box, text=default, font=("Segoe UI", 10, "bold"), bg="#ffffff", fg=self.primary_color)
            val_lbl.grid(row=r * 2 + 1, column=c, sticky="w", padx=6, pady=(0, 2))
            self.div_earned_labels[k] = val_lbl

        # 2. Future Growth & Compounding Milestones Box (Till Later How Much You Can Earn)
        self.div_future_box = tk.LabelFrame(right_frame, text=f" {t('div_sec_future_earnings')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=6)
        self.div_future_box.pack(fill=tk.X, pady=(0, 6))

        self.div_milestone_labels = {}
        self.div_milestone_title_labels = {}
        milestone_defs = [
            (1, t("lbl_milestone_1yr")),
            (3, t("lbl_milestone_3yr")),
            (5, t("lbl_milestone_5yr")),
            (10, t("lbl_milestone_10yr")),
        ]
        for idx, (yr, title) in enumerate(milestone_defs):
            cell = tk.Frame(self.div_future_box, bg="#f8f9fa", bd=1, relief="solid", padx=6, pady=4)
            cell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            t_lbl = tk.Label(cell, text=title, font=("Segoe UI", 8, "bold"), bg="#f8f9fa", fg=self.primary_color)
            t_lbl.pack(anchor="w")
            self.div_milestone_title_labels[yr] = t_lbl
            lbl_val = tk.Label(cell, text="$0.00", font=("Segoe UI", 10, "bold"), bg="#f8f9fa", fg=self.text_dark)
            lbl_val.pack(anchor="w")
            lbl_new = tk.Label(cell, text=f"{t('lbl_future_new_profit')}: +$0.00", font=("Segoe UI", 8), bg="#f8f9fa", fg=self.green_color)
            lbl_new.pack(anchor="w")
            lbl_tot = tk.Label(cell, text=f"{t('lbl_future_total_profit')}: +$0.00", font=("Segoe UI", 8), bg="#f8f9fa", fg=self.text_muted)
            lbl_tot.pack(anchor="w")
            self.div_milestone_labels[yr] = (lbl_val, lbl_new, lbl_tot)

        # 3. Dividend Projection Summary Box
        self.div_income_box = tk.LabelFrame(right_frame, text=f" {t('div_sec_projections')} ", font=("Segoe UI", 9, "bold"), bg="#ffffff", padx=10, pady=4)
        self.div_income_box.pack(fill=tk.X, pady=(0, 6))

        self.div_results = {}
        self.div_income_title_labels = {}
        disp_fields = [
            ("annual_total", t("div_proj_annual") + " ($):", "$0.00"),
            ("quarterly_total", t("div_proj_quarterly") + " ($):", "$0.00"),
            ("monthly_total", t("div_proj_monthly") + " ($):", "$0.00"),
            ("yield_on_cost", t("div_proj_yoc") + ":", "0.00%"),
            ("div_per_share", t("lbl_div_per_share"), "$0.00"),
        ]
        for i, (k, label, default) in enumerate(disp_fields):
            t_lbl = tk.Label(self.div_income_box, text=label, font=("Segoe UI", 8), bg="#ffffff", fg=self.text_muted)
            t_lbl.grid(row=0, column=i, sticky="w", padx=6)
            self.div_income_title_labels[k] = t_lbl
            val_lbl = tk.Label(self.div_income_box, text=default, font=("Segoe UI", 10, "bold"), bg="#ffffff", fg=self.primary_color)
            val_lbl.grid(row=1, column=i, sticky="w", padx=6, pady=(0, 2))
            self.div_results[k] = val_lbl

        # 4. DRIP Box (Table + Chart)
        drip_box = tk.LabelFrame(right_frame, text=f" {t('div_sec_drip')} ", font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.primary_color, padx=8, pady=4)
        drip_box.pack(fill=tk.BOTH, expand=True)
        self.div_drip_box = drip_box

        tree_container = ttk.Frame(drip_box)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ("year", "shares", "price", "annual_div", "portfolio_val", "invested", "profit")
        self.drip_tree = ttk.Treeview(tree_container, columns=cols, show="headings", height=4)
        drip_headers = [
            ("year", t("col_year"), 50),
            ("shares", t("col_drip_shares"), 90),
            ("price", t("col_current_price"), 95),
            ("annual_div", t("col_drip_income"), 95),
            ("portfolio_val", t("col_drip_val"), 105),
            ("invested", t("col_cost_basis"), 95),
            ("profit", t("col_unrealized_gain"), 105),
        ]
        for col, h, w in drip_headers:
            self.drip_tree.heading(col, text=h)
            self.drip_tree.column(col, width=w, anchor="e" if col != "year" else "center")

        drip_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.drip_tree.yview)
        self.drip_tree.configure(yscrollcommand=drip_scroll.set)
        drip_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.drip_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.drip_canvas = tk.Canvas(drip_box, height=155, bg=self.card_bg, highlightthickness=0)
        self.drip_canvas.pack(fill=tk.X, expand=False, pady=(4, 0))

        self.drip_tree.configure(yscrollcommand=drip_scroll.set)
        drip_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.drip_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.drip_canvas = tk.Canvas(drip_box, height=155, bg=self.card_bg, highlightthickness=0)
        self.drip_canvas.pack(fill=tk.X, expand=False, pady=(4, 0))

    def _set_div_purchase_date_days_ago(self, days: int):
        from datetime import date, timedelta
        target_d = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        if "purchase_date" in getattr(self, "div_inputs", {}):
            self.div_inputs["purchase_date"].delete(0, tk.END)
            self.div_inputs["purchase_date"].insert(0, target_d)
            self._calc_dividend_results()

    def _switch_to_fire_tab(self):
        """Switches user to the dedicated Bernstein FIRE & Retirement tab."""
        if hasattr(self, "notebook") and hasattr(self, "tab_fire"):
            try:
                self.notebook.select(self.tab_fire)
                self.root.after(20, self._refresh_fire_tab)
            except Exception:
                pass

    def _get_holding_asset_class(self, holding: Dict[str, Any]) -> str:
        """
        Classifies a holding into 'safe' (Safe Debt/TIPS/Cash) vs 'equity' (Equities/ETFs)
        based on ticker symbol and asset name according to Bernstein's framework.
        """
        sym = (holding.get("symbol") or "").strip().upper()
        name = (holding.get("name") or "").strip().upper()
        clean_sym = sym.split(".")[0].split(":")[0]
        safe_syms = {"TIP", "VTIP", "VGSH", "SHV", "SHY", "BIL", "SGOV", "IEI", "IEF", "GOVT", "BND", "AGG", "XSB", "CBH", "CASH", "PSA", "CSAV"}
        if clean_sym in safe_syms:
            return "safe"
        safe_keywords = [
            "BOND", "TREASURY", "TIPS", "INFLATION", "SHORT-TERM", "SHORT TERM", "GOVERNMENT",
            "SAVINGS", "GIC", "TBILL", "MONEY MARKET", "債券", "國債", "短期國債", "高利儲蓄", "定存"
        ]
        for kw in safe_keywords:
            if kw in name or kw in sym:
                return "safe"
        return "equity"

    # -------------------------------------------------------------
    # Tab: William J. Bernstein FIRE & Retirement Freedom Model
    # -------------------------------------------------------------
    def _build_fire_tab(self):
        tab = self.tab_fire

        # Scrollable container for full-screen or laptop flexibility
        canvas = tk.Canvas(tab, highlightthickness=0, bg=self.bg_main)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, padding=12)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas_win = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _on_canvas_resize(event):
            canvas.itemconfig(canvas_win, width=event.width)

        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mwheel(event):
            try:
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                elif event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")
            except Exception:
                pass

        tab.bind("<MouseWheel>", _on_mwheel)
        tab.bind("<Button-4>", _on_mwheel)
        tab.bind("<Button-5>", _on_mwheel)

        # Header Title
        hdr = tk.Frame(scroll_frame, bg=self.bg_main)
        hdr.pack(fill=tk.X, pady=(0, 8))

        hdr_left = tk.Frame(hdr, bg=self.bg_main)
        hdr_left.pack(side=tk.LEFT, fill=tk.Y)

        self.lbl_fire_title = tk.Label(
            hdr_left,
            text=f"🔥 {t('tab_fire').strip()} — {t('fire_title_header')}",
            font=("Segoe UI", 13, "bold"),
            fg="#e37400",
            bg=self.bg_main,
        )
        self.lbl_fire_title.pack(anchor="w")

        self.lbl_fire_sub = tk.Label(
            hdr_left,
            text=t("fire_sub_desc"),
            font=("Segoe UI", 9),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
            bg=self.bg_main,
        )
        self.lbl_fire_sub.pack(anchor="w", pady=(1, 4))

        # =========================================================
        # TOP MASTER ACTION & RETIREMENT TOOLKIT TOOLBAR
        # =========================================================
        self.fire_action_box = tk.LabelFrame(
            scroll_frame,
            text=f" {t('fire_bottom_actions_title')} ",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=8,
        )
        self.fire_action_box.pack(fill=tk.X, pady=(0, 10))

        # Row 1: Actuarial Diagnostic Suite (10 Models & Specialized Audits)
        row1 = tk.Frame(self.fire_action_box)
        row1.pack(fill=tk.X, pady=(0, 5))

        self.lbl_fire_models_suite = tk.Label(
            row1,
            text=f"🏛️ {t('lbl_fire_models_suite')}",
            font=("Segoe UI", 9, "bold"),
            fg=self.primary_color,
        )
        self.lbl_fire_models_suite.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_fire_toolkit_bar = tk.Button(
            row1,
            text=f"🚀 {t('btn_fire_toolkit')}",
            font=("Segoe UI", 8, "bold"),
            bg="#1a73e8",
            fg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._open_retirement_advanced_toolkit_dialog,
        )
        self.btn_fire_toolkit_bar.pack(side=tk.LEFT, padx=(0, 5))
        attach_tooltip(self.btn_fire_toolkit_bar, "tip_fire_toolkit_all")
        self.btn_fire_toolkit = self.btn_fire_toolkit_bar

        self.btn_fire_deep_risk = tk.Button(
            row1,
            text=t("btn_deep_risk_short"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#1a73e8",
            relief="solid",
            bd=1,
            padx=7,
            pady=3,
            cursor="hand2",
            command=self._show_deep_risk_dialog,
        )
        self.btn_fire_deep_risk.pack(side=tk.LEFT, padx=(0, 5))
        attach_tooltip(self.btn_fire_deep_risk, "btn_deep_risk_audit")

        self.btn_fire_crisis_stress = tk.Button(
            row1,
            text=t("btn_crisis_stress_short"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#c5221f",
            relief="solid",
            bd=1,
            padx=7,
            pady=3,
            cursor="hand2",
            command=self._show_crisis_stress_test_dialog,
        )
        self.btn_fire_crisis_stress.pack(side=tk.LEFT, padx=(0, 5))
        attach_tooltip(self.btn_fire_crisis_stress, "btn_crisis_stress_test")

        self.btn_fire_tax_drag = tk.Button(
            row1,
            text=t("btn_fee_tax_drag_short"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#b06000",
            relief="solid",
            bd=1,
            padx=7,
            pady=3,
            cursor="hand2",
            command=self._show_fee_tax_drag_dialog,
        )
        self.btn_fire_tax_drag.pack(side=tk.LEFT, padx=(0, 5))
        attach_tooltip(self.btn_fire_tax_drag, "btn_fee_tax_drag")

        self.btn_fire_rebalance_5_25 = tk.Button(
            row1,
            text=t("btn_rebalance_5_25_short"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#137333",
            relief="solid",
            bd=1,
            padx=7,
            pady=3,
            cursor="hand2",
            command=self._show_rebalancing_5_25_dialog,
        )
        self.btn_fire_rebalance_5_25.pack(side=tk.LEFT, padx=(0, 5))
        attach_tooltip(self.btn_fire_rebalance_5_25, "btn_rebalance_5_25")

        self.btn_fire_simplicity = tk.Button(
            row1,
            text=t("btn_simplicity_short"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#681da8",
            relief="solid",
            bd=1,
            padx=7,
            pady=3,
            cursor="hand2",
            command=self._show_simplicity_index_dialog,
        )
        self.btn_fire_simplicity.pack(side=tk.LEFT)
        attach_tooltip(self.btn_fire_simplicity, "btn_simplicity_index")

        # Row 2: Decision Execution, Simulation & Report Export
        row2 = tk.Frame(self.fire_action_box)
        row2.pack(fill=tk.X, pady=(2, 0))

        self.lbl_fire_actions_suite = tk.Label(
            row2,
            text=f"⚡ {t('lbl_fire_actions_suite')}",
            font=("Segoe UI", 9, "bold"),
            fg="#e37400",
        )
        self.lbl_fire_actions_suite.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_fire_to_rebalance = tk.Button(
            row2,
            text=t("btn_apply_to_rebalance"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg=self.primary_color,
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._apply_fire_to_rebalance,
        )
        self.btn_fire_to_rebalance.pack(side=tk.LEFT, padx=(0, 5))
        attach_tooltip(self.btn_fire_to_rebalance, "tip_fire_apply_rebalance")

        self.btn_fire_simulate = tk.Button(
            row2,
            text=t("btn_simulate_trade"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#188038",
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            command=lambda: self._open_what_if_dialog(
                initial_symbol="TIP",
                initial_amount=getattr(self, "_last_safe_gap", 10000.0)
            ),
        )
        self.btn_fire_simulate.pack(side=tk.LEFT, padx=(0, 5))
        attach_tooltip(self.btn_fire_simulate, "tip_fire_simulate_trade")

        self.btn_fire_recalc = tk.Button(
            row2,
            text=f"🔄 {t('btn_recalc_fire')}",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#5f6368" if not self.dark_mode else "#c4c7c5",
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._refresh_fire_tab,
        )
        self.btn_fire_recalc.pack(side=tk.LEFT, padx=(0, 5))
        attach_tooltip(self.btn_fire_recalc, "tip_fire_recalc")

        self.btn_fire_export = tk.Button(
            row2,
            text=t("btn_export_fire_report"),
            font=("Segoe UI", 8, "bold"),
            bg="#e37400",
            fg="#ffffff",
            relief="solid",
            bd=1,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._export_fire_report_action,
        )
        self.btn_fire_export.pack(side=tk.RIGHT)
        attach_tooltip(self.btn_fire_export, "tip_fire_export_report")

        # Main 2-column layout container
        content_box = tk.Frame(scroll_frame, bg=self.bg_main)
        content_box.pack(fill=tk.BOTH, expand=True)

        left_col = tk.Frame(content_box, bg=self.bg_main, width=460)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        right_col = tk.Frame(content_box, bg=self.bg_main, width=540)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(8, 0))

        # =========================================================
        # LEFT COLUMN: STEPS 1 TO 3 (INPUTS & AUDIT)
        # =========================================================

        saved_fire = load_settings().get("fire_params", {})

        # STEP 1: Existing Holdings & Safe Asset Audit
        self.fire_s1_box = tk.LabelFrame(
            left_col,
            text=f" {t('fire_step1_title')} ",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=8,
        )
        self.fire_s1_box.pack(fill=tk.X, pady=(0, 8))

        self.fire_audit_summary_lbl = tk.Label(
            self.fire_s1_box,
            text=t("fire_scanning_holdings"),
            font=("Segoe UI", 9, "bold"),
            fg=self.text_dark,
            justify=tk.LEFT,
        )
        self.fire_audit_summary_lbl.pack(anchor="w", pady=(0, 4))

        # Outside safe assets input
        outside_row = tk.Frame(self.fire_s1_box)
        outside_row.pack(fill=tk.X, pady=(2, 6))
        self.lbl_fire_outside = tk.Label(outside_row, text=t("lbl_outside_safe_assets"), font=("Segoe UI", 8, "bold"))
        self.lbl_fire_outside.pack(side=tk.LEFT)
        self.fire_outside_safe_entry = tk.Entry(outside_row, font=("Segoe UI", 9), width=14, bd=1, relief="solid")
        self.fire_outside_safe_entry.insert(0, str(saved_fire.get("outside_safe_assets", "0.0")))
        self.fire_outside_safe_entry.pack(side=tk.RIGHT)

        def _on_outside_focus_out(e=None):
            cleaned = self.fire_outside_safe_entry.get().strip().replace("$", "").replace(",", "").replace(" ", "")
            if not cleaned:
                self.fire_outside_safe_entry.delete(0, tk.END)
                self.fire_outside_safe_entry.insert(0, "0.0")
            self._refresh_fire_tab()

        self.fire_outside_safe_entry.bind("<KeyRelease>", lambda e: self._refresh_fire_tab())
        self.fire_outside_safe_entry.bind("<FocusOut>", _on_outside_focus_out)
        self.fire_outside_safe_entry.bind("<Return>", lambda e: self._refresh_fire_tab())
        self.fire_outside_safe_entry.bind("<ButtonRelease-1>", lambda e: self._refresh_fire_tab())

        # Mini treeview of current holdings classified into safe vs equity
        tree_frame = tk.Frame(self.fire_s1_box)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical")
        self.fire_holdings_tree = ttk.Treeview(
            tree_frame,
            columns=("symbol", "name", "value", "weight", "asset_class"),
            show="headings",
            height=5,
            selectmode="browse",
            yscrollcommand=tree_scroll.set,
        )
        tree_scroll.config(command=self.fire_holdings_tree.yview)

        self.fire_holdings_tree.heading("symbol", text=t("col_symbol"), command=lambda: self._sort_fire_holdings_by("symbol"))
        self.fire_holdings_tree.heading("name", text=t("col_name"), command=lambda: self._sort_fire_holdings_by("name"))
        self.fire_holdings_tree.heading("value", text=t("col_market_value"), command=lambda: self._sort_fire_holdings_by("value"))
        self.fire_holdings_tree.heading("weight", text=t("col_weight"), command=lambda: self._sort_fire_holdings_by("weight"))
        self.fire_holdings_tree.heading("asset_class", text=t("lbl_holding_asset_class"), command=lambda: self._sort_fire_holdings_by("asset_class"))

        self.fire_holdings_tree.column("symbol", width=75, anchor="center")
        self.fire_holdings_tree.column("name", width=120, anchor="w")
        self.fire_holdings_tree.column("value", width=80, anchor="e")
        self.fire_holdings_tree.column("weight", width=60, anchor="center")
        self.fire_holdings_tree.column("asset_class", width=110, anchor="center")

        self.fire_holdings_tree.tag_configure("safe_asset", background="#e8f0fe", foreground="#1a73e8")
        self.fire_holdings_tree.tag_configure("equity_asset", background="#ffffff" if not self.dark_mode else "#202124")

        self.fire_holdings_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # STEP 2: Age, Retirement Timeline & Strategy
        self.fire_s2_box = tk.LabelFrame(
            left_col,
            text=f" {t('fire_step2_title')} ",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=8,
        )
        self.fire_s2_box.pack(fill=tk.X, pady=(0, 8))

        s2_grid = tk.Frame(self.fire_s2_box)
        s2_grid.pack(fill=tk.X)

        self.lbl_fire_cur_age = tk.Label(s2_grid, text=t("lbl_current_age"), font=("Segoe UI", 8, "bold"))
        self.lbl_fire_cur_age.grid(row=0, column=0, sticky="w", pady=2)
        self.fire_age_spin = tk.Spinbox(
            s2_grid, from_=18, to=95, width=6, font=("Segoe UI", 9), bd=1, relief="solid",
            command=self._refresh_fire_tab,
        )
        self.fire_age_spin.delete(0, tk.END)
        self.fire_age_spin.insert(0, str(saved_fire.get("current_age", "45")))
        self.fire_age_spin.grid(row=0, column=1, sticky="w", padx=(4, 12), pady=2)

        self.lbl_fire_retire_age = tk.Label(s2_grid, text=t("lbl_retire_age"), font=("Segoe UI", 8, "bold"))
        self.lbl_fire_retire_age.grid(row=0, column=2, sticky="w", pady=2)
        self.fire_retire_age_spin = tk.Spinbox(
            s2_grid, from_=30, to=95, width=6, font=("Segoe UI", 9), bd=1, relief="solid",
            command=self._refresh_fire_tab,
        )
        self.fire_retire_age_spin.delete(0, tk.END)
        self.fire_retire_age_spin.insert(0, str(saved_fire.get("retire_age", "60")))
        self.fire_retire_age_spin.grid(row=0, column=3, sticky="w", padx=(4, 0), pady=2)

        self.lbl_fire_horizon = tk.Label(s2_grid, text=t("lbl_life_expectancy"), font=("Segoe UI", 8, "bold"))
        self.lbl_fire_horizon.grid(row=1, column=0, sticky="w", pady=2)
        self.fire_horizon_spin = tk.Spinbox(
            s2_grid, from_=70, to=115, width=6, font=("Segoe UI", 9), bd=1, relief="solid",
            command=self._refresh_fire_tab,
        )
        self.fire_horizon_spin.delete(0, tk.END)
        self.fire_horizon_spin.insert(0, str(saved_fire.get("life_expectancy", "90")))
        self.fire_horizon_spin.grid(row=1, column=1, sticky="w", padx=(4, 12), pady=2)

        self.lbl_fire_safe_years = tk.Label(s2_grid, text=t("lbl_safe_years"), font=("Segoe UI", 8, "bold"))
        self.lbl_fire_safe_years.grid(row=1, column=2, sticky="w", pady=2)
        self.fire_safe_years_combo = ttk.Combobox(s2_grid, values=["20", "25", "30"], state="readonly", width=5, font=("Segoe UI", 9))
        self.fire_safe_years_combo.set(str(saved_fire.get("target_safe_years", "25")))
        self.fire_safe_years_combo.grid(row=1, column=3, sticky="w", padx=(4, 0), pady=2)

        pension_row = tk.Frame(self.fire_s2_box)
        pension_row.pack(fill=tk.X, pady=(4, 2))

        self.fire_delay_pension_var = tk.BooleanVar(value=bool(saved_fire.get("delay_pension_to_70", True)))
        self.fire_delay_check = tk.Checkbutton(
            pension_row,
            text=t("lbl_delay_pension"),
            variable=self.fire_delay_pension_var,
            font=("Segoe UI", 8, "bold"),
            fg="#188038",
            command=self._refresh_fire_tab,
        )
        self.fire_delay_check.pack(side=tk.LEFT)

        self.btn_fire_pension_actuary = tk.Button(
            pension_row,
            text=t("btn_pension_actuary"),
            font=("Segoe UI", 8, "bold"),
            relief="groove",
            bd=1,
            padx=6,
            pady=1,
            fg="#1a73e8",
            command=self._show_pension_actuary_dialog,
        )
        self.btn_fire_pension_actuary.pack(side=tk.RIGHT)

        self.fire_timeline_lbl = tk.Label(self.fire_s2_box, text="", font=("Segoe UI", 9, "bold"), fg="#1a73e8" if not self.dark_mode else "#8ab4f8")
        self.fire_timeline_lbl.pack(anchor="w", pady=(2, 0))

        # STEP 3: Living Expenses & Guaranteed Pension
        self.fire_s3_box = tk.LabelFrame(
            left_col,
            text=f" {t('fire_step3_title')} ",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=8,
        )
        self.fire_s3_box.pack(fill=tk.X, pady=(0, 4))

        # Quick preset personas
        preset_row = tk.Frame(self.fire_s3_box)
        preset_row.pack(fill=tk.X, pady=(0, 4))
        self.lbl_fire_preset_profiles = tk.Label(preset_row, text=f"{t('lbl_preset_profiles')} ", font=("Segoe UI", 8, "bold"))
        self.lbl_fire_preset_profiles.pack(side=tk.LEFT)

        def _apply_persona(age, ret_age, exp, pension, save, growth):
            self.fire_age_spin.delete(0, tk.END)
            self.fire_age_spin.insert(0, str(age))
            self.fire_retire_age_spin.delete(0, tk.END)
            self.fire_retire_age_spin.insert(0, str(ret_age))
            self.fire_exp_entry.delete(0, tk.END)
            self.fire_exp_entry.insert(0, str(exp))
            if hasattr(self, "fire_ess_exp_entry") and hasattr(self, "fire_disc_exp_entry"):
                ess = round(exp * 0.70, 2)
                disc = round(exp - ess, 2)
                self.fire_ess_exp_entry.delete(0, tk.END)
                self.fire_ess_exp_entry.insert(0, str(ess))
                self.fire_disc_exp_entry.delete(0, tk.END)
                self.fire_disc_exp_entry.insert(0, str(disc))
            self.fire_pension_entry.delete(0, tk.END)
            self.fire_pension_entry.insert(0, str(pension))
            self.fire_savings_entry.delete(0, tk.END)
            self.fire_savings_entry.insert(0, str(save))
            self.fire_growth_entry.delete(0, tk.END)
            self.fire_growth_entry.insert(0, str(growth))
            self._refresh_fire_tab()

        self.fire_btn_persona_young = tk.Button(preset_row, text=t("preset_young"), font=("Segoe UI", 7), relief="groove", bd=1, command=lambda: _apply_persona(30, 55, 3000.0, 0.0, 2000.0, 6.0))
        self.fire_btn_persona_young.pack(side=tk.LEFT, padx=1)
        self.fire_btn_persona_trans = tk.Button(preset_row, text=t("preset_transition"), font=("Segoe UI", 7), relief="groove", bd=1, command=lambda: _apply_persona(50, 60, 4000.0, 12000.0, 2500.0, 4.0))
        self.fire_btn_persona_trans.pack(side=tk.LEFT, padx=1)
        self.fire_btn_persona_fritz = tk.Button(preset_row, text=t("preset_fritz"), font=("Segoe UI", 7), relief="groove", bd=1, command=lambda: _apply_persona(60, 65, 3500.0, 15000.0, 0.0, 3.0))
        self.fire_btn_persona_fritz.pack(side=tk.LEFT, padx=1)
        self.fire_btn_persona_frank = tk.Button(preset_row, text=t("preset_frank"), font=("Segoe UI", 7), relief="groove", bd=1, command=lambda: _apply_persona(65, 65, 6000.0, 25000.0, 0.0, 4.0))
        self.fire_btn_persona_frank.pack(side=tk.LEFT, padx=1)

        # Quick expenses buttons
        qexp_row = tk.Frame(self.fire_s3_box)
        qexp_row.pack(fill=tk.X, pady=(2, 4))
        self.lbl_fire_quick_exp = tk.Label(qexp_row, text=f"{t('lbl_quick_exp')} ", font=("Segoe UI", 8, "bold"))
        self.lbl_fire_quick_exp.pack(side=tk.LEFT)
        for amt in [2000, 3000, 4000, 5000, 8000]:
            def _make_quick_cmd(val=amt):
                return lambda: (
                    self.fire_exp_entry.delete(0, tk.END),
                    self.fire_exp_entry.insert(0, str(float(val))),
                    self.fire_ess_exp_entry.delete(0, tk.END) if hasattr(self, "fire_ess_exp_entry") else None,
                    self.fire_ess_exp_entry.insert(0, str(round(val * 0.70, 2))) if hasattr(self, "fire_ess_exp_entry") else None,
                    self.fire_disc_exp_entry.delete(0, tk.END) if hasattr(self, "fire_disc_exp_entry") else None,
                    self.fire_disc_exp_entry.insert(0, str(round(val * 0.30, 2))) if hasattr(self, "fire_disc_exp_entry") else None,
                    self._refresh_fire_tab(),
                )
            tk.Button(
                qexp_row,
                text=f"${amt:,}",
                font=("Segoe UI", 7),
                relief="groove",
                bd=1,
                padx=4,
                command=_make_quick_cmd(amt),
            ).pack(side=tk.LEFT, padx=1)

        # Input fields
        s3_grid = tk.Frame(self.fire_s3_box)
        s3_grid.pack(fill=tk.X, pady=(2, 0))

        self.lbl_fire_exp = tk.Label(s3_grid, text=t("lbl_target_monthly_expense"), font=("Segoe UI", 8, "bold"))
        self.lbl_fire_exp.grid(row=0, column=0, sticky="w", pady=2)
        self.fire_exp_entry = tk.Entry(s3_grid, font=("Segoe UI", 9, "bold"), bd=1, relief="solid")
        self.fire_exp_entry.insert(0, str(saved_fire.get("target_monthly_expense", "3500.0")))
        self.fire_exp_entry.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=2)

        # Essential Floor & Discretionary Ceiling sub-inputs
        sub_exp_row = tk.Frame(self.fire_s3_box)
        sub_exp_row.pack(fill=tk.X, pady=(2, 4))

        self.lbl_fire_ess_exp = tk.Label(sub_exp_row, text=t("lbl_essential_expense"), font=("Segoe UI", 8))
        self.lbl_fire_ess_exp.pack(side=tk.LEFT)
        self.fire_ess_exp_entry = tk.Entry(sub_exp_row, font=("Segoe UI", 8), width=8, bd=1, relief="solid")
        self.fire_ess_exp_entry.insert(0, str(saved_fire.get("essential_monthly_expense", "2450.0")))
        self.fire_ess_exp_entry.pack(side=tk.LEFT, padx=(2, 6))

        self.lbl_fire_disc_exp = tk.Label(sub_exp_row, text=t("lbl_discretionary_expense"), font=("Segoe UI", 8))
        self.lbl_fire_disc_exp.pack(side=tk.LEFT)
        self.fire_disc_exp_entry = tk.Entry(sub_exp_row, font=("Segoe UI", 8), width=8, bd=1, relief="solid")
        self.fire_disc_exp_entry.insert(0, str(saved_fire.get("discretionary_monthly_expense", "1050.0")))
        self.fire_disc_exp_entry.pack(side=tk.LEFT, padx=(2, 0))

        def _on_tot_exp_change(e=None):
            try:
                tot = float(self.fire_exp_entry.get().strip() or "0.0")
                ess = round(tot * 0.70, 2)
                disc = round(tot - ess, 2)
                self.fire_ess_exp_entry.delete(0, tk.END)
                self.fire_ess_exp_entry.insert(0, str(ess))
                self.fire_disc_exp_entry.delete(0, tk.END)
                self.fire_disc_exp_entry.insert(0, str(disc))
            except ValueError:
                pass
            self._refresh_fire_tab()

        def _on_sub_exp_change(e=None):
            try:
                ess = float(self.fire_ess_exp_entry.get().strip() or "0.0")
                disc = float(self.fire_disc_exp_entry.get().strip() or "0.0")
                tot = round(ess + disc, 2)
                self.fire_exp_entry.delete(0, tk.END)
                self.fire_exp_entry.insert(0, str(tot))
            except ValueError:
                pass
            self._refresh_fire_tab()

        self.fire_exp_entry.bind("<KeyRelease>", _on_tot_exp_change)
        self.fire_exp_entry.bind("<FocusOut>", _on_tot_exp_change)
        self.fire_ess_exp_entry.bind("<KeyRelease>", _on_sub_exp_change)
        self.fire_ess_exp_entry.bind("<FocusOut>", _on_sub_exp_change)
        self.fire_disc_exp_entry.bind("<KeyRelease>", _on_sub_exp_change)
        self.fire_disc_exp_entry.bind("<FocusOut>", _on_sub_exp_change)

        self.lbl_fire_pension = tk.Label(s3_grid, text=t("lbl_guaranteed_pension"), font=("Segoe UI", 8, "bold"))
        self.lbl_fire_pension.grid(row=1, column=0, sticky="w", pady=2)
        self.fire_pension_entry = tk.Entry(s3_grid, font=("Segoe UI", 9), bd=1, relief="solid")
        self.fire_pension_entry.insert(0, str(saved_fire.get("guaranteed_annual_pension", "15000.0")))
        self.fire_pension_entry.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=2)

        self.lbl_fire_savings = tk.Label(s3_grid, text=t("lbl_monthly_savings"), font=("Segoe UI", 8, "bold"))
        self.lbl_fire_savings.grid(row=2, column=0, sticky="w", pady=2)
        self.fire_savings_entry = tk.Entry(s3_grid, font=("Segoe UI", 9), bd=1, relief="solid")
        self.fire_savings_entry.insert(0, str(saved_fire.get("monthly_savings", "1500.0")))
        self.fire_savings_entry.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=2)

        self.lbl_fire_growth = tk.Label(s3_grid, text=t("lbl_dividend_growth_rate"), font=("Segoe UI", 8, "bold"))
        self.lbl_fire_growth.grid(row=3, column=0, sticky="w", pady=2)
        self.fire_growth_entry = tk.Entry(s3_grid, font=("Segoe UI", 9), bd=1, relief="solid")
        self.fire_growth_entry.insert(0, str(saved_fire.get("expected_div_growth", "5.0")))
        self.fire_growth_entry.grid(row=3, column=1, sticky="ew", padx=(4, 0), pady=2)

        # Bind live keystrokes, focus loss, and mouse clicks to auto-calculate
        for w in [self.fire_age_spin, self.fire_retire_age_spin, self.fire_horizon_spin, self.fire_pension_entry, self.fire_savings_entry, self.fire_growth_entry]:
            w.bind("<KeyRelease>", lambda e: self._refresh_fire_tab())
            w.bind("<FocusOut>", lambda e: self._refresh_fire_tab())
            w.bind("<ButtonRelease-1>", lambda e: self._refresh_fire_tab())
        self.fire_safe_years_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_fire_tab())

        # Attach hints / tooltips
        attach_tooltip(self.fire_outside_safe_entry, "tip_fire_outside_safe")
        attach_tooltip(self.fire_age_spin, "tip_fire_current_age")
        attach_tooltip(self.fire_retire_age_spin, "tip_fire_retire_age")
        attach_tooltip(self.fire_horizon_spin, "tip_fire_horizon")
        attach_tooltip(self.fire_safe_years_combo, "tip_fire_safe_years")
        attach_tooltip(self.fire_delay_check, "tip_fire_delay_pension")
        attach_tooltip(self.fire_exp_entry, "tip_fire_exp")
        attach_tooltip(self.fire_pension_entry, "tip_fire_pension")
        attach_tooltip(self.fire_savings_entry, "tip_fire_savings")
        attach_tooltip(self.fire_growth_entry, "tip_fire_growth")

        # =========================================================
        # RIGHT COLUMN: STEPS 4 TO 5 (GAP ANALYSIS & ACTION PLAN)
        # =========================================================

        # STEP 4: Gap Analysis — What Is Missing?
        self.fire_s4_box = tk.LabelFrame(
            right_col,
            text=f" {t('fire_step4_title')} ",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=8,
        )
        self.fire_s4_box.pack(fill=tk.X, pady=(0, 8))

        # Gap Card 1: Safe Liability Matching Gap
        self.card_safe_gap = tk.Frame(self.fire_s4_box, bg=self.card_bg, bd=1, relief="solid", padx=10, pady=8)
        self.card_safe_gap.pack(fill=tk.X, pady=(0, 6))

        self.lbl_fire_safe_title = tk.Label(self.card_safe_gap, text=f"🛡️ {t('lbl_safe_asset_gap')}", font=("Segoe UI", 8, "bold"), fg=self.primary_color, bg=self.card_bg)
        self.lbl_fire_safe_title.pack(anchor="w")
        self.lbl_safe_gap_val = tk.Label(self.card_safe_gap, text="-", font=("Segoe UI", 11, "bold"), fg=self.text_dark, bg=self.card_bg)
        self.lbl_safe_gap_val.pack(anchor="w", pady=1)

        self.lbl_safe_gap_status = tk.Label(self.card_safe_gap, text="-", font=("Segoe UI", 8), bg=self.card_bg)
        self.lbl_safe_gap_status.pack(anchor="w")

        ladder_btn_row = tk.Frame(self.card_safe_gap, bg=self.card_bg)
        ladder_btn_row.pack(fill=tk.X, pady=(3, 2))

        self.btn_fire_view_ladder = tk.Button(
            ladder_btn_row,
            text=t("btn_view_bond_ladder"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg=self.primary_color,
            relief="groove",
            bd=1,
            padx=8,
            pady=2,
            command=self._show_bond_ladder_dialog,
        )
        self.btn_fire_view_ladder.pack(side=tk.LEFT)

        # Quick instrument shortcut chips for safe assets
        chips_frame = tk.Frame(self.card_safe_gap, bg=self.card_bg)
        chips_frame.pack(fill=tk.X, pady=(4, 0))
        self.lbl_fire_chips = tk.Label(chips_frame, text=t("fire_chips_lbl"), font=("Segoe UI", 8, "bold"), bg=self.card_bg, fg="#5f6368" if not self.dark_mode else "#9aa0a6")
        self.lbl_fire_chips.pack(side=tk.LEFT)
        for sym, name in [("TIP", "iShares TIPS"), ("VTIP", "Short TIPS"), ("VGSH", "Short Treasury"), ("XSB.TO", "CAD Short Bond"), ("CASH.TO", "CAD High Yield")]:
            btn_chip = tk.Button(
                chips_frame,
                text=f"+ {sym}",
                font=("Segoe UI", 7, "bold"),
                relief="groove",
                bd=1,
                padx=4,
                pady=1,
                command=lambda s=sym: self._open_what_if_dialog(initial_symbol=s),
            )
            btn_chip.pack(side=tk.LEFT, padx=2)

        # Gap Card 2: Passive Dividend Cashflow Gap
        self.card_div_gap = tk.Frame(self.fire_s4_box, bg=self.card_bg, bd=1, relief="solid", padx=10, pady=8)
        self.card_div_gap.pack(fill=tk.X, pady=(0, 6))

        self.lbl_fire_div_title = tk.Label(self.card_div_gap, text=f"💵 {t('lbl_dividend_gap')}", font=("Segoe UI", 8, "bold"), fg=self.green_color, bg=self.card_bg)
        self.lbl_fire_div_title.pack(anchor="w")
        self.lbl_div_gap_val = tk.Label(self.card_div_gap, text="-", font=("Segoe UI", 11, "bold"), fg=self.text_dark, bg=self.card_bg)
        self.lbl_div_gap_val.pack(anchor="w", pady=1)

        self.lbl_div_gap_status = tk.Label(self.card_div_gap, text="-", font=("Segoe UI", 8), bg=self.card_bg)
        self.lbl_div_gap_status.pack(anchor="w")

        # Gap Card 3: Capital Target Gap
        self.card_cap_gap = tk.Frame(self.fire_s4_box, bg=self.card_bg, bd=1, relief="solid", padx=10, pady=8)
        self.card_cap_gap.pack(fill=tk.X, pady=(0, 6))

        self.lbl_fire_cap_title = tk.Label(self.card_cap_gap, text=f"🏛️ {t('lbl_capital_gap')}", font=("Segoe UI", 8, "bold"), fg="#e37400", bg=self.card_bg)
        self.lbl_fire_cap_title.pack(anchor="w")
        self.lbl_cap_gap_val = tk.Label(self.card_cap_gap, text="-", font=("Segoe UI", 11, "bold"), fg=self.text_dark, bg=self.card_bg)
        self.lbl_cap_gap_val.pack(anchor="w", pady=1)

        self.lbl_cap_gap_status = tk.Label(self.card_cap_gap, text="-", font=("Segoe UI", 8), bg=self.card_bg)
        self.lbl_cap_gap_status.pack(anchor="w")

        # Gap Card 4: Shiller CAPE Dynamic SWR Corridor (Bernstein Pillar 1)
        self.card_cape_swr = tk.Frame(self.fire_s4_box, bg=self.card_bg, bd=1, relief="solid", padx=10, pady=8)
        self.card_cape_swr.pack(fill=tk.X)

        cape_hdr = tk.Frame(self.card_cape_swr, bg=self.card_bg)
        cape_hdr.pack(fill=tk.X)

        self.lbl_fire_cape_title = tk.Label(cape_hdr, text=f"🌐 {t('lbl_cape_swr_title')}", font=("Segoe UI", 8, "bold"), fg="#1a73e8", bg=self.card_bg)
        self.lbl_fire_cape_title.pack(side=tk.LEFT)

        cape_input_f = tk.Frame(cape_hdr, bg=self.card_bg)
        cape_input_f.pack(side=tk.RIGHT)

        self.lbl_current_cape_input = tk.Label(cape_input_f, text=t("lbl_current_cape_input"), font=("Segoe UI", 8), bg=self.card_bg)
        self.lbl_current_cape_input.pack(side=tk.LEFT, padx=(0, 4))

        self.fire_cape_spin = tk.Spinbox(
            cape_input_f,
            from_=10.0,
            to=65.0,
            increment=0.5,
            font=("Segoe UI", 8, "bold"),
            width=6,
            bd=1,
            relief="solid",
            command=lambda: self._refresh_fire_tab(),
        )
        self.fire_cape_spin.delete(0, tk.END)
        self.fire_cape_spin.insert(0, str(saved_fire.get("current_cape", "34.0")))
        self.fire_cape_spin.pack(side=tk.LEFT)
        self.fire_cape_spin.bind("<KeyRelease>", lambda e: self._refresh_fire_tab())
        self.fire_cape_spin.bind("<FocusOut>", lambda e: self._refresh_fire_tab())
        self.fire_cape_spin.bind("<ButtonRelease-1>", lambda e: self._refresh_fire_tab())

        self.lbl_cape_swr_val = tk.Label(self.card_cape_swr, text="-", font=("Segoe UI", 10, "bold"), fg="#1a73e8", bg=self.card_bg)
        self.lbl_cape_swr_val.pack(anchor="w", pady=(2, 1))

        self.lbl_cape_zone_badge = tk.Label(self.card_cape_swr, text="", font=("Segoe UI", 8, "bold"), bg=self.card_bg)
        self.lbl_cape_zone_badge.pack(anchor="w")

        self.lbl_cape_swr_status = tk.Label(self.card_cape_swr, text="-", font=("Segoe UI", 8), bg=self.card_bg)
        self.lbl_cape_swr_status.pack(anchor="w")

        # STEP 5: Burn Rate & Master Action Plan
        self.fire_s5_box = tk.LabelFrame(
            right_col,
            text=f" {t('fire_step5_title')} ",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=8,
        )
        self.fire_s5_box.pack(fill=tk.X, pady=(0, 4))

        # Burn rate banner
        self.fire_burn_banner = tk.Frame(self.fire_s5_box, bd=1, relief="solid", padx=10, pady=6)
        self.fire_burn_banner.pack(fill=tk.X, pady=(0, 6))

        self.lbl_fire_burn_badge = tk.Label(self.fire_burn_banner, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_fire_burn_badge.pack(anchor="w")

        self.lbl_fire_rle_summary = tk.Label(self.fire_burn_banner, text="", font=("Segoe UI", 8))
        self.lbl_fire_rle_summary.pack(anchor="w", pady=(1, 0))

        # Essential Floor Coverage indicator
        self.fire_floor_banner = tk.Frame(self.fire_s5_box, bd=1, relief="solid", padx=10, pady=5)
        self.fire_floor_banner.pack(fill=tk.X, pady=(0, 6))

        self.lbl_fire_floor_badge = tk.Label(self.fire_floor_banner, text="", font=("Segoe UI", 9, "bold"))
        self.lbl_fire_floor_badge.pack(anchor="w")

        self.lbl_fire_disc_badge = tk.Label(self.fire_floor_banner, text="", font=("Segoe UI", 8))
        self.lbl_fire_disc_badge.pack(anchor="w", pady=(1, 0))

        # Action Checklist & Master Guidance
        self.fire_checklist_box = tk.Frame(self.fire_s5_box, bg="#f8f9fa" if not self.dark_mode else "#252830", bd=1, relief="solid", padx=8, pady=6)
        self.fire_checklist_box.pack(fill=tk.X, pady=(0, 6))

        self.lbl_fire_checklist = tk.Label(
            self.fire_checklist_box,
            text="",
            font=("Segoe UI", 8),
            fg=self.text_dark,
            bg="#f8f9fa" if not self.dark_mode else "#252830",
            justify=tk.LEFT,
            wraplength=500,
        )
        self.lbl_fire_checklist.pack(anchor="w")

        # Initial calculation
        self._refresh_fire_tab()

    def _sort_fire_holdings_by(self, col: str):
        """Sorts the Step 1 FIRE holdings table by clicked column header."""
        if not hasattr(self, "fire_holdings_tree"):
            return
        if not hasattr(self, "_fire_sort_desc"):
            self._fire_sort_desc = {}
        desc = not self._fire_sort_desc.get(col, False)
        self._fire_sort_desc[col] = desc

        col_map = {"symbol": 0, "name": 1, "value": 2, "weight": 3, "asset_class": 4}
        idx = col_map.get(col, 0)

        items = self.fire_holdings_tree.get_children("")
        data = []
        for iid in items:
            vals = self.fire_holdings_tree.item(iid, "values")
            tags = self.fire_holdings_tree.item(iid, "tags")
            data.append((vals, tags))

        def parse_val(entry):
            raw = str(entry[0][idx]).strip()
            if col in ("value", "weight"):
                clean = raw.replace("$", "").replace("%", "").replace(",", "").replace(" ", "")
                try:
                    return (0, float(clean))
                except ValueError:
                    return (1, raw)
            return (0, raw.lower())

        data.sort(key=parse_val, reverse=desc)
        for iid in items:
            self.fire_holdings_tree.delete(iid)
        for vals, tags in data:
            self.fire_holdings_tree.insert("", tk.END, values=vals, tags=tags)

    def _refresh_fire_tab(self):
        """Refreshes holding audit, gap calculations, and roadmap recommendations on tab_fire."""
        if not hasattr(self, "tab_fire") or not hasattr(self, "fire_holdings_tree"):
            return

        target_curr = self.summary_currency
        cur_total_val = 0.0
        cur_ann_div = 0.0
        cur_equity_val = 0.0
        cur_safe_val = 0.0

        # Clear and repopulate Step 1 holdings tree
        for item in self.fire_holdings_tree.get_children():
            self.fire_holdings_tree.delete(item)

        aggregated_holdings: Dict[str, Dict[str, Any]] = {}
        for h in self.holdings:
            raw_sym = (h.get("symbol") or "").strip()
            if not raw_sym:
                continue
            sym_key = raw_sym.upper()

            c = (h.get("currency") or "USD").strip().upper()
            shares = float(h.get("shares", 0.0) or 0.0)
            price = float(h.get("current_price", h.get("price", 0.0)) or 0.0)
            mv = shares * price
            if mv <= 0.0 and h.get("market_value") is not None:
                try:
                    mv = float(str(h["market_value"]).replace("$", "").replace(",", "").strip())
                except ValueError:
                    pass

            ad = float(h.get("annual_dividend", 0.0) or 0.0)
            mv_conv = self.converter.convert(mv, c, target_curr)
            ad_conv = self.converter.convert(ad, c, target_curr)

            cur_total_val += mv_conv
            cur_ann_div += ad_conv

            aclass = self._get_holding_asset_class(h)
            if aclass == "safe":
                cur_safe_val += mv_conv
            else:
                cur_equity_val += mv_conv

            raw_name = (h.get("name") or "").strip()
            if sym_key not in aggregated_holdings:
                aggregated_holdings[sym_key] = {
                    "symbol": raw_sym,
                    "name": raw_name or raw_sym,
                    "shares": shares,
                    "value": mv_conv,
                    "annual_dividend": ad_conv,
                    "currency": target_curr,
                    "aclass": aclass,
                    "expense_ratio": h.get("expense_ratio"),
                    "mer": h.get("mer"),
                    "sector": h.get("sector"),
                }
            else:
                agg = aggregated_holdings[sym_key]
                agg["shares"] += shares
                agg["value"] += mv_conv
                agg["annual_dividend"] += ad_conv
                cur_n = agg.get("name", "")
                if (not cur_n or cur_n == agg["symbol"]) and raw_name:
                    agg["name"] = raw_name
                if aclass == "safe":
                    agg["aclass"] = "safe"

        # Calculate unit price for each aggregated holding
        combined_holdings = []
        for agg in aggregated_holdings.values():
            if agg["value"] <= 0.001 and agg["shares"] <= 0.001:
                continue
            if agg["shares"] > 0:
                agg["current_price"] = agg["value"] / agg["shares"]
                agg["price"] = agg["current_price"]
            else:
                agg["current_price"] = 0.0
                agg["price"] = 0.0
            combined_holdings.append(agg)

        # Sort by value descending so largest portfolio holdings appear at top
        combined_holdings.sort(key=lambda x: x["value"], reverse=True)
        self._last_combined_fire_holdings = combined_holdings

        # Add outside safe assets
        raw_outside = ""
        if hasattr(self, "fire_outside_safe_entry"):
            raw_outside = self.fire_outside_safe_entry.get().strip().replace("$", "").replace(",", "").replace(" ", "")
        try:
            outside_safe = float(raw_outside or "0.0")
        except ValueError:
            outside_safe = 0.0
        total_effective_safe = cur_safe_val + outside_safe
        total_effective_wealth = cur_total_val + outside_safe

        # Insert aggregated items into treeview
        for ph in combined_holdings:
            w_pct = (ph["value"] / cur_total_val * 100.0) if cur_total_val > 0 else 0.0
            tag = "safe_asset" if ph["aclass"] == "safe" else "equity_asset"
            aclass_label = t("col_class_safe") if ph["aclass"] == "safe" else t("col_class_equity")
            self.fire_holdings_tree.insert(
                "",
                tk.END,
                values=(
                    ph["symbol"],
                    ph["name"],
                    self.converter.format_money(ph["value"], target_curr),
                    f"{w_pct:.1f}%",
                    aclass_label,
                ),
                tags=(tag,),
            )

        eq_pct = (cur_equity_val / total_effective_wealth * 100.0) if total_effective_wealth > 0 else 0.0
        safe_pct = (total_effective_safe / total_effective_wealth * 100.0) if total_effective_wealth > 0 else 0.0
        div_yld_pct = (cur_ann_div / cur_total_val * 100.0) if cur_total_val > 0 else 0.0

        summary_audit_str = (
            f"{t('fire_audit_total_wealth', total=self.converter.format_money(total_effective_wealth, target_curr))}\n"
            f"{t('fire_audit_equity_assets', val=self.converter.format_money(cur_equity_val, target_curr), pct=eq_pct)}  |  "
            f"{t('fire_audit_safe_assets', val=self.converter.format_money(total_effective_safe, target_curr), pct=safe_pct)}\n"
            f"{t('fire_audit_passive_div', val=self.converter.format_money(cur_ann_div, target_curr), yld=div_yld_pct)}"
        )
        self.fire_audit_summary_lbl.config(text=summary_audit_str)

        # Parse inputs
        try:
            cur_age = int(self.fire_age_spin.get().strip() or "45")
        except ValueError:
            cur_age = 45
        try:
            ret_age = int(self.fire_retire_age_spin.get().strip() or "60")
        except ValueError:
            ret_age = 60
        try:
            life_exp = int(self.fire_horizon_spin.get().strip() or "90")
        except ValueError:
            life_exp = 90
        try:
            s_yrs = float(self.fire_safe_years_combo.get().strip() or "25.0")
        except ValueError:
            s_yrs = 25.0
        try:
            m_exp = float(self.fire_exp_entry.get().strip().replace("$", "").replace(",", "").replace(" ", "") or "3500.0")
        except ValueError:
            m_exp = 3500.0
        try:
            p_ann = float(self.fire_pension_entry.get().strip().replace("$", "").replace(",", "").replace(" ", "") or "15000.0")
        except ValueError:
            p_ann = 15000.0
        try:
            m_sav = float(self.fire_savings_entry.get().strip().replace("$", "").replace(",", "").replace(" ", "") or "0.0")
        except ValueError:
            m_sav = 0.0
        try:
            div_g = float(self.fire_growth_entry.get().strip().replace("%", "").replace(",", "").replace(" ", "") or "5.0") / 100.0
        except ValueError:
            div_g = 0.05

        try:
            ess_exp = float(self.fire_ess_exp_entry.get().strip().replace("$", "").replace(",", "").replace(" ", "") or "0.0") if hasattr(self, "fire_ess_exp_entry") else 0.0
        except ValueError:
            ess_exp = 0.0
        try:
            disc_exp = float(self.fire_disc_exp_entry.get().strip().replace("$", "").replace(",", "").replace(" ", "") or "0.0") if hasattr(self, "fire_disc_exp_entry") else 0.0
        except ValueError:
            disc_exp = 0.0

        try:
            cape_val = float(self.fire_cape_spin.get().strip() or "34.0") if hasattr(self, "fire_cape_spin") else 34.0
        except ValueError:
            cape_val = 34.0

        try:
            delay_to_70 = bool(self.fire_delay_pension_var.get()) if hasattr(self, "fire_delay_pension_var") else True
        except Exception:
            delay_to_70 = True

        # Store for dialogs and persistence
        self._last_total_portfolio_wealth = total_effective_wealth
        self._last_annual_dividend = cur_ann_div
        self._last_current_age = cur_age
        self._last_retire_age = ret_age
        self._last_life_expectancy = life_exp

        # Determine value to save for outside_safe_assets
        if raw_outside:
            outside_save_val = str(outside_safe)
        else:
            saved_fire_cfg = load_settings().get("fire_params", {})
            outside_save_val = str(saved_fire_cfg.get("outside_safe_assets", "0.0"))

        try:
            save_settings({
                "fire_params": {
                    "current_age": str(cur_age),
                    "retire_age": str(ret_age),
                    "life_expectancy": str(life_exp),
                    "target_safe_years": str(s_yrs),
                    "delay_pension_to_70": delay_to_70,
                    "target_monthly_expense": str(m_exp),
                    "essential_monthly_expense": str(ess_exp),
                    "discretionary_monthly_expense": str(disc_exp),
                    "guaranteed_annual_pension": str(p_ann),
                    "monthly_savings": str(m_sav),
                    "expected_div_growth": str(round(div_g * 100.0, 2)),
                    "current_cape": str(cape_val),
                    "outside_safe_assets": outside_save_val,
                }
            })
        except Exception:
            pass

        res = calc_fire_metrics(
            current_annual_div=cur_ann_div,
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
            delay_pension_to_70=delay_to_70,
            essential_monthly_expense=ess_exp,
            discretionary_monthly_expense=disc_exp,
            current_cape=cape_val,
            holdings=combined_holdings,
        )
        self._last_fire_res = res

        years_to_retire = res["years_to_retire"]
        ret_duration = res["retirement_duration_years"]
        self.fire_timeline_lbl.config(
            text=t("fire_timeline_status", years=years_to_retire, dur=ret_duration)
        )

        # Update Gap Cards
        safe_gap = res["safe_asset_gap"]
        self._last_safe_gap = safe_gap
        lm_target = res["liability_matching_target"]
        safe_cov_pct = res["safe_asset_coverage_pct"]

        if safe_gap > 0:
            self.lbl_safe_gap_val.config(text=t("fire_safe_gap_short", gap=safe_gap), fg="#d93025")
            self.lbl_safe_gap_status.config(
                text=t("fire_safe_gap_detail", yrs=s_yrs, target=lm_target, cur=total_effective_safe, cov=safe_cov_pct),
                fg="#d93025",
            )
        else:
            surplus = res["safe_asset_surplus"]
            self.lbl_safe_gap_val.config(text=t("fire_safe_gap_full", surplus=surplus), fg="#188038")
            self.lbl_safe_gap_status.config(
                text=t("fire_safe_gap_full_detail", target=lm_target, surplus=surplus),
                fg="#188038",
            )

        # Div gap
        div_gap_ann = res["dividend_gap_annual"]
        div_rle_pct = res["dividend_rle_coverage_pct"]
        rle_ann = res["rle_annual"]
        years_cross = res["years_to_crossover"]

        if div_gap_ann > 0:
            self.lbl_div_gap_val.config(text=t("fire_div_gap_short", gap=div_gap_ann, mo=div_gap_ann/12), fg="#e37400")
            self.lbl_div_gap_status.config(
                text=t("fire_div_gap_detail", rle=rle_ann, cov=div_rle_pct, cross=years_cross),
                fg=self.text_dark,
            )
        else:
            self.lbl_div_gap_val.config(text=t("fire_div_gap_full"), fg="#188038")
            self.lbl_div_gap_status.config(
                text=t("fire_div_gap_full_detail", div=cur_ann_div, rle=rle_ann),
                fg="#188038",
            )

        # Capital gap
        cap_32 = res["bernstein_swr_32_target"]
        cap_gap = res["capital_gap_bernstein"]
        savings_needed = res["monthly_savings_needed"]
        cap_cov_pct = (total_effective_wealth / cap_32 * 100.0) if cap_32 > 0 else 100.0

        if cap_gap > 0:
            self.lbl_cap_gap_val.config(text=t("fire_cap_gap_short", gap=cap_gap, cov=cap_cov_pct), fg="#e37400")
            self.lbl_cap_gap_status.config(
                text=t("fire_cap_gap_detail", target=cap_32, save=savings_needed, years=years_to_retire),
                fg=self.text_dark,
            )
        else:
            self.lbl_cap_gap_val.config(text=t("fire_cap_gap_full", cov=cap_cov_pct), fg="#188038")
            self.lbl_cap_gap_status.config(
                text=t("fire_cap_gap_full_detail", wealth=total_effective_wealth, target=cap_32),
                fg="#188038",
            )

        # Update CAPE Dynamic SWR Card
        if hasattr(self, "card_cape_swr"):
            cape_data = res.get("cape_swr_data", {})
            dyn_swr = cape_data.get("dynamic_swr_pct", 3.2)
            ann_cap = cape_data.get("annual_withdrawal_cap", 0.0)
            mo_cap = cape_data.get("monthly_withdrawal_cap", 0.0)
            z_name = cape_data.get("zone_name", "")
            z_color = cape_data.get("zone_color", self.text_dark)
            delta = cape_data.get("annual_withdrawal_delta", 0.0)
            delta_pct = dyn_swr - 4.0

            self.lbl_cape_swr_val.config(
                text=t("lbl_dynamic_swr_result", swr=dyn_swr, ann=ann_cap, mo=mo_cap),
                fg=z_color,
            )
            self.lbl_cape_zone_badge.config(
                text=t("lbl_cape_zone_badge", zone=z_name),
                fg=z_color,
            )
            self.lbl_cape_swr_status.config(
                text=t("lbl_cape_vs_static_delta", delta=delta, pct=delta_pct),
                fg=self.text_dark,
            )

        # Burn rate banner
        burn_rate = res["burn_rate_pct"]
        burn_zone = res["burn_zone"]
        rle_mo = res["rle_monthly"]
        ann_exp = res["target_annual_expense"]
        eff_pension = res["guaranteed_annual_pension"]

        if burn_zone == "green":
            badge_bg = "#e6f4ea"
            badge_fg = "#137333"
            b_txt = f"🟢 {t('fire_burn_rate_lbl', rate=burn_rate, zone=t('zone_green'))}"
        elif burn_zone == "yellow":
            badge_bg = "#fef7e0"
            badge_fg = "#b06000"
            b_txt = f"🟡 {t('fire_burn_rate_lbl', rate=burn_rate, zone=t('zone_yellow'))}"
        else:
            badge_bg = "#fce8e6"
            badge_fg = "#c5221f"
            b_txt = f"🔴 {t('fire_burn_rate_lbl', rate=burn_rate, zone=t('zone_red'))}"

        self.fire_burn_banner.config(bg=badge_bg)
        self.lbl_fire_burn_badge.config(text=b_txt, bg=badge_bg, fg=badge_fg)
        pension_boost_txt = t("fire_pension_boost_txt") if delay_to_70 else ""
        self.lbl_fire_rle_summary.config(
            text=t("fire_rle_summary_fmt", mo=rle_mo, yr=rle_ann, exp=ann_exp, pen=eff_pension, boost=pension_boost_txt),
            bg=badge_bg,
            fg=self.text_dark,
        )

        # Essential floor banner
        if hasattr(self, "fire_floor_banner"):
            ess_cov = res.get("essential_floor_coverage_pct", 100.0)
            ess_safe = res.get("essential_floor_is_safe", True)
            disc_cov = res.get("discretionary_buffer_pct", 100.0)
            ess_mo = res.get("essential_monthly_expense", 0.0)
            disc_mo = res.get("discretionary_monthly_expense", 0.0)

            if ess_safe:
                floor_bg = "#e6f4ea"
                floor_fg = "#137333"
                floor_badge = f"{t('badge_essential_safe')}  ({ess_cov:.1f}%)"
            else:
                floor_bg = "#fce8e6"
                floor_fg = "#c5221f"
                floor_badge = f"{t('badge_essential_vulnerable')}  ({ess_cov:.1f}%)"

            self.fire_floor_banner.config(bg=floor_bg)
            self.lbl_fire_floor_badge.config(text=floor_badge, bg=floor_bg, fg=floor_fg)
            self.lbl_fire_disc_badge.config(
                text=f"{t('lbl_discretionary_buffer_badge', cov=disc_cov)}  |  {t('lbl_essential_expense')} ${ess_mo:,.0f}  |  {t('lbl_discretionary_expense')} ${disc_mo:,.0f}",
                bg=floor_bg,
                fg=self.text_dark,
            )

        # Checklist & Master Guidance text
        chk_1 = t("fire_checklist_item1_pass") if safe_gap == 0 else t("fire_checklist_item1_fail", gap=safe_gap)
        chk_2 = t("fire_checklist_item2_pass") if delay_to_70 else t("fire_checklist_item2_fail")
        chk_3 = t("fire_checklist_item3_pass") if div_gap_ann == 0 else t("fire_checklist_item3_fail", cov=div_rle_pct, gap=div_gap_ann)
        chk_4 = t("fire_checklist_item4_pass") if burn_rate < 3.5 else t("fire_checklist_item4_fail")

        guidance_text = (
            f"{t('fire_checklist_hdr')}\n{chk_1}\n{chk_2}\n{chk_3}\n{chk_4}\n\n"
            f"{t('fire_master_advice_hdr')}\n"
            f"{res.get('bernstein_tip', '')}\n"
            f"{t('fire_master_quote')}"
        )
        self.lbl_fire_checklist.config(text=guidance_text)

    def _apply_fire_to_rebalance(self):
        """Passes recommended asset allocation from Bernstein model to Portfolio Rebalancing modal."""
        if not hasattr(self, "_last_fire_res"):
            return
        res = self._last_fire_res
        total_p = float(res.get("current_portfolio_val", 100000.0))
        lm_target = float(res.get("liability_matching_target", 50000.0))

        # Compute suggested safe vs equity weight
        safe_wt = min(90.0, max(10.0, (lm_target / total_p * 100.0))) if total_p > 0 else 50.0
        equity_wt = 100.0 - safe_wt

        # Build holding-level target dictionary
        suggested_weights = {}
        fire_holdings = getattr(self, "_last_combined_fire_holdings", self.holdings)
        for h in fire_holdings:
            sym = (h.get("symbol") or "").strip().upper()
            aclass = self._get_holding_asset_class(h)
            if aclass == "safe":
                suggested_weights[sym] = round(safe_wt, 1)
            else:
                suggested_weights[sym] = round(equity_wt, 1)

        self._open_rebalance_dialog(initial_target_weights=suggested_weights)

    def _export_fire_report_action(self):
        """Exports a comprehensive Markdown report of Bernstein FIRE status."""
        if not hasattr(self, "_last_fire_res"):
            self._refresh_fire_tab()
        res = getattr(self, "_last_fire_res", {})

        report_content = [
            "# 威廉·伯恩斯坦 退休自由與資產配置診斷報告",
            "## William J. Bernstein Dual-Engine FIRE Roadmap Report",
            f"- **產生時間**: {date.today().strftime('%Y-%m-%d')}",
            f"- **彙總貨幣**: {self.summary_currency}",
            "",
            "### 一、年齡與退休時間軸",
            f"- 目前年齡: {res.get('current_age')} 歲",
            f"- 預計退休年齡: {res.get('retire_age')} 歲",
            f"- 規劃壽命目標: {res.get('life_expectancy')} 歲",
            f"- 距離退休年數: {res.get('years_to_retire')} 年",
            f"- 退休規劃期: {res.get('retirement_duration_years')} 年",
            f"- 延後至70歲領取公積金/年金: {'是 (享受約+28%終身通膨加乘)' if res.get('delay_pension_to_70') else '否'}",
            "",
            "### 二、雙軌收支與待攤生活費用 (Two-Tier Expenses & RLE)",
            f"- 目標每月生活開銷: ${(res.get('target_monthly_expense') or 0):,.2f} (${(res.get('target_annual_expense') or 0):,.2f}/年)",
            f"  - 基礎生存支出 (Essential Floor): ${(res.get('essential_monthly_expense') or 0):,.2f}/月 (${(res.get('essential_annual_expense') or 0):,.2f}/年)",
            f"  - 彈性品質支出 (Discretionary Ceiling): ${(res.get('discretionary_monthly_expense') or 0):,.2f}/月 (${(res.get('discretionary_annual_expense') or 0):,.2f}/年)",
            f"- 基礎生存底層覆蓋率 (公積金 + 安全年金): **{(res.get('essential_floor_coverage_pct') or 100):.1f}%** ({'🟢 100% 免疫' if res.get('essential_floor_is_safe') else '⚠️ 存在缺口'})",
            f"- 彈性品質覆蓋率 (被動股息現金流): **{(res.get('discretionary_buffer_pct') or 100):.1f}%**",
            f"- 每年保證年金/公積金: ${(res.get('guaranteed_annual_pension') or 0):,.2f}",
            f"- **待攤生活費用 (RLE)**: **${(res.get('rle_monthly') or 0):,.2f}/月 (${(res.get('rle_annual') or 0):,.2f}/年)**",
            "",
            "### 三、資產配置缺口診斷 (What Is Missing?)",
            f"- 負債配合組合目標 (25年安全儲備): ${(res.get('liability_matching_target') or 0):,.2f}",
            f"- 目前持有無風險資產: ${(res.get('current_safe_assets') or 0):,.2f} (覆蓋率: {(res.get('safe_asset_coverage_pct') or 0):.1f}%)",
            f"- **無風險安全資產缺口**: **${(res.get('safe_asset_gap') or 0):,.2f}**",
            f"- 每年被動股息收入: ${(res.get('current_annual_dividend') or 0):,.2f}/年",
            f"- **被動股息現金流缺口**: **${(res.get('dividend_gap_annual') or 0):,.2f}/年** (覆蓋率: {(res.get('dividend_rle_coverage_pct') or 0):.1f}%)",
            f"- 伯恩斯坦 3.2% 守則目標本金: ${(res.get('bernstein_swr_32_target') or 0):,.2f}",
            f"- **本金缺口**: **${(res.get('capital_gap_bernstein') or 0):,.2f}**",
            "",
        ]

        ladder = res.get("ladder_data", {})
        if ladder and ladder.get("schedule"):
            report_content.append("### 四、20-25年 TIPS / 安全債券負債匹配階梯摘要")
            report_content.append(f"- 階梯規劃年數: {ladder.get('years')} 年 (退休年齡 {ladder.get('start_age')} 歲 ~ {ladder.get('end_age')} 歲)")
            report_content.append(f"- 實質所需安全本金: ${ladder.get('total_real_needed', 0):,.2f}")
            report_content.append(f"- 100% 完全鎖定年數: {ladder.get('fully_funded_years')} / {ladder.get('years')} 年")
            report_content.append("")
            report_content.append("| 年度 | 退休年齡 | 實質生活費 | 名目生活費 (CPI) | 覆蓋金額 | 狀態 | 推薦標的 |")
            report_content.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            for it in ladder.get("schedule", [])[:10]:
                st_mark = "🟢 已鎖定" if it["status"] == "fully_funded" else ("🟡 部分鎖定" if it["status"] == "partially_funded" else "🔴 缺口")
                report_content.append(f"| Yr {it['year_index']} | {it['age']} 歲 | ${it['real_liability']:,.2f} | ${it['nominal_liability']:,.2f} | ${it['funded_amount']:,.2f} | {st_mark} | {it['recommended_ticker']} |")
            if len(ladder.get("schedule", [])) > 10:
                report_content.append(f"| ... | ... | *(其餘 {len(ladder.get('schedule')) - 10} 年詳見完整階梯匯出表)* | ... | ... | ... | ... |")
            report_content.append("")

        p_act = res.get("pension_actuary_data", {})
        if p_act and p_act.get("base_annual_at_65", 0) > 0:
            report_content.extend([
                "### 五、延後至 70 歲領取年金長壽精算",
                f"- 65 歲標準領取: ${p_act['claim_65']['monthly']:,.2f}/月 (${p_act['claim_65']['annual']:,.2f}/年)",
                f"- 70 歲延後領取: ${p_act['claim_70']['monthly']:,.2f}/月 (${p_act['claim_70']['annual']:,.2f}/年，永久加成 +28%)",
                f"- **黃金打平年齡**: **{p_act.get('breakeven_age_70_vs_65', 83)} 歲** (壽命超過此年齡，延後領取產生巨大終身超額淨利)",
                f"- 規劃壽命 {p_act.get('life_expectancy')} 歲時累計超額收益: **+${p_act.get('gain_at_life_exp_vs_65', 0):,.2f}**",
                "",
            ])

        # Seven: CAPE Dynamic SWR
        cape_data = res.get("cape_swr_data", {})
        if cape_data:
            report_content.extend([
                "### 七、席勒 CAPE 估值聯動動態安全提領率 (Shiller CAPE Dynamic SWR)",
                f"- 當前標普 500 席勒 CAPE 估值: **{cape_data.get('current_cape'):.1f}** (歷史中位數: ~16.5)",
                f"- 估值區間判定: **{cape_data.get('zone_name')}**",
                f"- **動態安全提領率 (Dynamic SWR)**: **{cape_data.get('dynamic_swr_pct'):.2f}%**",
                f"- 推薦年度安全提領上限: **${cape_data.get('annual_withdrawal_cap', 0):,.2f}/年 (${cape_data.get('monthly_withdrawal_cap', 0):,.2f}/月)**",
                f"- 相較靜態 4% 法則差額: **${cape_data.get('annual_withdrawal_delta', 0):+,.2f}/年**",
                f"- 估值指引: {cape_data.get('guidance')}",
                "",
            ])

        # Eight: Deep Risk Audit
        d_data = res.get("deep_risk_data", {})
        if d_data:
            report_content.extend([
                "### 八、伯恩斯坦深層四重風險體檢 (Deep Risk Resilience Audit)",
                f"- **全組合深層風險總體防禦評級**: **{d_data.get('overall_score', 0):.1f} / 100 ({d_data.get('overall_grade')}級 — {d_data.get('grade_desc')})**",
                f"- 1. 持續性嚴重通膨防禦 (Severe Inflation): **{d_data.get('inflation_score', 0):.1f} / 100**",
                f"- 2. 嚴重通縮與大蕭條防禦 (Severe Deflation): **{d_data.get('deflation_score', 0):.1f} / 100**",
                f"- 3. 財產沒收、重稅與管制防禦 (Confiscation): **{d_data.get('confiscation_score', 0):.1f} / 100**",
                f"- 4. 戰亂與地緣毀滅防禦 (Devastation): **{d_data.get('devastation_score', 0):.1f} / 100**",
                "",
                "#### 防禦優勢與處方建議:",
            ])
            for st in d_data.get("strengths", []):
                report_content.append(f"- 🟢 [優勢] {st}")
            for wk in d_data.get("weaknesses", []):
                report_content.append(f"- ⚠️ [漏洞] {wk}")
            for rec in d_data.get("recommendations", []):
                report_content.append(f"- 👉 [處方-{rec.get('risk')}] {rec.get('action')}")
            report_content.append("")

        # Nine: Historical Crisis Stress Test
        c_data = res.get("crisis_stress_test_data", {})
        if c_data:
            report_content.extend([
                "### 九、歷史四大崩盤極端提領序列壓力測試 (Crisis Stress Test)",
                f"- 模擬安全緩衝儲備: ${c_data.get('safe_buffer_used', 0):,.2f}",
                f"- 平均守護資產差額: **+${c_data.get('avg_capital_preserved', 0):,.2f}** (相較無防禦被動賣股)",
                f"- 伯恩斯坦定律: {c_data.get('bernstein_stress_thesis')}",
                "",
                "| 歷史危機事件 | 情境A：無防禦終端資產 | 情境B：雙引擎安全階梯終端資產 | 保存資產差額 | 資本保存率 |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ])
            for k, info in c_data.get("results_by_crisis", {}).items():
                report_content.append(
                    f"| {info.get('name')} | ${info.get('terminal_unhedged', 0):,.2f} | ${info.get('terminal_hedged', 0):,.2f} | +${info.get('capital_preserved', 0):,.2f} | {info.get('wealth_preservation_pct')}% |"
                )
            report_content.append("")

        # Eleven: Fee & Cross-Border Tax Drag Autopsy
        f_data = res.get("fee_tax_data", {})
        if f_data:
            report_content.extend([
                f"### {t('fire_rep_sec11_title')}",
                f"- 投資人所在地 / 稅籍: {f_data.get('region')} | 帳戶類型: {f_data.get('account_type')}",
                f"- 加權投資組合費用率 (TER/MER): **{f_data.get('portfolio_weighted_ter_pct', 0):.2f}% / 年**",
                f"- 美股股息預扣稅率 (WHT): **{f_data.get('us_dividend_wht_pct', 0):.1f}%** | 資本利得稅率 (CGT): **{f_data.get('capital_gains_tax_pct', 0):.1f}%**",
                f"- **30年累計財富侵蝕總額**: **-${f_data.get('thirty_year_total_loss', 0):,.2f}** (侵蝕毛財富 **{f_data.get('thirty_year_loss_ratio_pct', 0):.1f}%**)",
                f"  - 30年內扣費用侵蝕 (TER/MER): -${f_data.get('thirty_year_fee_loss', 0):,.2f}",
                f"  - 30年美股股息預扣稅侵蝕 (WHT): -${f_data.get('thirty_year_wht_loss', 0):,.2f}",
                f"  - 30年資本利得稅侵蝕 (CGT): -${f_data.get('thirty_year_cgt_loss', 0):,.2f}",
                f"- 30年終端淨財富: **${f_data.get('thirty_year_portfolio_wealth', 0):,.2f}** (理想無損耗毛財富: ${f_data.get('thirty_year_gross_wealth', 0):,.2f})",
                "",
                "#### 伯恩斯坦資產配置避稅建言:",
            ])
            for tip in f_data.get("asset_location_tips", []):
                report_content.append(f"- 💡 {tip}")
            report_content.append("")

        # Twelve: 5/25 Rebalancing Bands & Bonus
        reb_data = res.get("rebalance_5_25_data", {})
        if reb_data:
            report_content.extend([
                f"### {t('fire_rep_sec12_title')}",
                f"- 5/25 偏離門檻法則: 絕對偏離 ≥ 5.0% 或 相對偏離 ≥ 25.0%",
                f"- 預估年化再平衡溢價 (Rebalancing Bonus): **+${reb_data.get('estimated_annual_rebalance_bonus', 0):,.2f} / 年** (+{reb_data.get('rebalancing_bonus_pct', 0):.2f}% / 年)",
                f"- 監控狀態: **{reb_data.get('triggered_count', 0)} / {reb_data.get('total_assets', 0)}** 隻標的觸發再平衡警戒線",
                f"- 伯恩斯坦定律: {reb_data.get('bernstein_rebalance_thesis')}",
                "",
                "| 標的 / 資產 | 當前佔比 | 目標佔比 | 絕對偏離 | 相對偏離 | 狀態 | 建議操作 | 再平衡金額 |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ])
            for item in reb_data.get("asset_drifts", []):
                st_icon = "🚨 觸發" if item["status"] == "triggered" else ("⚠️ 逼近" if item["status"] == "approaching" else "✅ 正常")
                act_str = "賣出 (平衡超配)" if item["action"] == "trim" else ("買入 (補充低配)" if item["action"] == "add" else "持有")
                report_content.append(
                    f"| {item['symbol']} | {item['actual_pct']:.1f}% | {item['target_pct']:.1f}% | {item['abs_drift_pct']:+.1f}% | {item['rel_drift_pct']:+.1f}% | {st_icon} | {act_str} | ${item['rebalance_amount_dollars']:,.2f} |"
                )
            report_content.append("")

        # Thirteen: Cognitive Decline Protection & Simplicity Index
        simp_data = res.get("simplicity_data", {})
        if simp_data:
            report_content.extend([
                f"### {t('fire_rep_sec13_title')}",
                f"- **投資組合極簡化評分**: **{simp_data.get('simplicity_score', 0)} / 100 ({simp_data.get('rating')} — {simp_data.get('rating_desc')})**",
                f"- 活躍持倉總數: {simp_data.get('holding_count')} 隻 (評分: {simp_data.get('holding_score')}/100)",
                f"- 指數化基金比例: {simp_data.get('indexing_ratio_pct', 0):.1f}% (評分: {simp_data.get('index_score')}/100)",
                f"- 涉及幣種數量: {simp_data.get('currency_count')} 種 (評分: {simp_data.get('currency_score')}/100)",
                f"- 70歲認知退化警報狀態: **{'⚠️ 高度警戒 (年齡 >= 70)' if simp_data.get('cognitive_alert') else '🟢 安全 (年齡 < 70)'}**",
                f"- 認知安全建言: {simp_data.get('cognitive_warning')}",
                "",
                "#### 伯恩斯坦資產極簡整合處方:",
            ])
            for rec in simp_data.get("recommendations", []):
                report_content.append(f"- 👉 {rec}")
            report_content.append("")

        report_content.extend([
            "### 十四、燒錢率與大師忠告",
            f"- 投資組合燒錢率 (Burn Rate): **{res.get('burn_rate_pct'):.2f}%** ({res.get('burn_zone_desc')})",
            f"- 評語建議: {res.get('bernstein_tip')}",
            "",
            "---",
            "*Report generated by Google Finance Portfolio Tracker & Calculator.*"
        ])

        report_txt = "\n".join(report_content)
        out_path = filedialog.asksaveasfilename(
            title=t("btn_fire_export_report") if "btn_fire_export_report" in TRANSLATIONS.get(get_current_language(), {}) else "Export FIRE Report",
            defaultextension=".md",
            filetypes=[("Markdown Document", "*.md"), ("All Files", "*.*")],
            initialfile=f"bernstein_fire_report_{date.today().strftime('%Y%m%d')}.md",
            parent=self.root,
        )
        if not out_path:
            return
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(report_txt)
            messagebox.showinfo(
                t("dlg_fire_export_success_title"),
                t("msg_fire_export_success", path=out_path),
            )
        except Exception as e:
            messagebox.showerror(t("dlg_fire_export_failed_title"), t("msg_fire_export_failed", error=str(e)))

    def _show_bond_ladder_dialog(self):
        """Displays the 20-25 year TIPS and safe bond liability matching ladder schedule modal."""
        if not hasattr(self, "_last_fire_res"):
            self._refresh_fire_tab()
        res = getattr(self, "_last_fire_res", {})
        ladder_data = res.get("ladder_data", {})
        schedule = ladder_data.get("schedule", [])
        if not schedule:
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_bond_ladder_title"))
        dlg.geometry("920x580")
        dlg.minsize(800, 480)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Header info
        hdr_frame = tk.Frame(frame, bg=self.card_bg, bd=1, relief="solid", padx=10, pady=8)
        hdr_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            hdr_frame,
            text=f"🪜 {t('dlg_bond_ladder_title')}",
            font=("Segoe UI", 11, "bold"),
            fg=self.primary_color,
            bg=self.card_bg,
        ).pack(anchor="w")

        years = ladder_data.get("years", 25)
        total_real = ladder_data.get("total_real_needed", 0.0)
        safe_assets = ladder_data.get("current_safe_assets", 0.0)
        cov = ladder_data.get("coverage_pct", 0.0)
        funded_yrs = ladder_data.get("fully_funded_years", 0)

        sub_txt = (
            f"{t('lbl_ladder_coverage_summary', years=years, real=total_real, safe=safe_assets, cov=cov)}  |  "
            f"100% {t('status_fully_funded')}: {funded_yrs} / {years} {t('col_ladder_year')}"
        )
        tk.Label(
            hdr_frame,
            text=sub_txt,
            font=("Segoe UI", 9),
            bg=self.card_bg,
            fg=self.text_dark,
        ).pack(anchor="w", pady=(2, 0))

        # Treeview
        tree_frame = tk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        scroll_y = ttk.Scrollbar(tree_frame, orient="vertical")
        scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")

        cols = ("year", "age", "real", "nominal", "funded", "gap", "status", "bucket", "ticker")
        tree = ttk.Treeview(
            tree_frame,
            columns=cols,
            show="headings",
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
            selectmode="browse",
        )
        scroll_y.config(command=tree.yview)
        scroll_x.config(command=tree.xview)

        tree.heading("year", text=t("col_ladder_year"))
        tree.heading("age", text=t("col_ladder_age"))
        tree.heading("real", text=t("col_ladder_real"))
        tree.heading("nominal", text=t("col_ladder_nominal"))
        tree.heading("funded", text=t("col_ladder_funded"))
        tree.heading("gap", text=t("col_ladder_gap"))
        tree.heading("status", text=t("col_ladder_status"))
        tree.heading("bucket", text=t("col_ladder_bucket"))
        tree.heading("ticker", text=t("col_ladder_ticker"))

        tree.column("year", width=55, anchor="center")
        tree.column("age", width=75, anchor="center")
        tree.column("real", width=95, anchor="e")
        tree.column("nominal", width=115, anchor="e")
        tree.column("funded", width=95, anchor="e")
        tree.column("gap", width=85, anchor="e")
        tree.column("status", width=105, anchor="center")
        tree.column("bucket", width=140, anchor="w")
        tree.column("ticker", width=120, anchor="center")

        tree.tag_configure("fully_funded", background="#e6f4ea", foreground="#137333")
        tree.tag_configure("partially_funded", background="#fef7e0", foreground="#b06000")
        tree.tag_configure("unfunded", background="#ffffff" if not self.dark_mode else "#202124", foreground="#c5221f")

        for item in schedule:
            st = item["status"]
            if st == "fully_funded":
                st_txt = t("status_fully_funded")
            elif st == "partially_funded":
                st_txt = t("status_partially_funded")
            else:
                st_txt = t("status_unfunded")

            gap_val = f"${item['gap_amount']:,.2f}" if item["gap_amount"] > 0 else "-"
            tree.insert(
                "",
                tk.END,
                values=(
                    f"Yr {item['year_index']}",
                    f"{item['age']} 歲",
                    f"${item['real_liability']:,.2f}",
                    f"${item['nominal_liability']:,.2f}",
                    f"${item['funded_amount']:,.2f}",
                    gap_val,
                    st_txt,
                    item["instrument_type"],
                    item["recommended_ticker"],
                ),
                tags=(st,),
            )

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        # Footer Actions
        btn_box = tk.Frame(frame)
        btn_box.pack(fill=tk.X, pady=(8, 0))

        def _export_csv():
            from tkinter import filedialog
            p = filedialog.asksaveasfilename(
                title=t("btn_export_ladder_csv"),
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv")],
                initialfile="bernstein_bond_ladder_25yr.csv",
                parent=dlg,
            )
            if not p:
                return
            try:
                import csv
                with open(p, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["Year", "Age", "Real_Liability", "Nominal_Liability", "Funded_Amount", "Gap_Amount", "Status", "Duration_Bucket", "Recommended_Ticker"])
                    for it in schedule:
                        w.writerow([it["year_index"], it["age"], it["real_liability"], it["nominal_liability"], it["funded_amount"], it["gap_amount"], it["status"], it["instrument_type"], it["recommended_ticker"]])
                messagebox.showinfo("Export Success", f"Bond ladder schedule exported to:\n{p}", parent=dlg)
            except Exception as ex:
                messagebox.showerror("Export Failed", str(ex), parent=dlg)

        tk.Button(btn_box, text=t("btn_export_ladder_csv"), font=("Segoe UI", 9, "bold"), relief="solid", bd=1, padx=10, pady=3, command=_export_csv).pack(side=tk.LEFT)
        tk.Button(btn_box, text=t("btn_close"), font=("Segoe UI", 9), padx=10, pady=3, command=dlg.destroy).pack(side=tk.RIGHT)

    def _open_retirement_advanced_toolkit_dialog(self):
        """Displays the Institutional Retirement & Actuarial Planning Toolkit (10 Dedicated Models)."""
        if not hasattr(self, "_last_fire_res"):
            self._refresh_fire_tab()
        res = getattr(self, "_last_fire_res", {})

        dlg = tk.Toplevel(self.root)
        dlg.title(t("fire_tk_title"))
        dlg.geometry("1020x760")
        dlg.minsize(900, 640)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Header Title
        hdr_box = tk.Frame(frame)
        hdr_box.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            hdr_box,
            text=f"🚀 {t('fire_tk_title')}",
            font=("Segoe UI", 12, "bold"),
            fg="#1a73e8",
        ).pack(anchor="w")

        tk.Label(
            hdr_box,
            text=t("fire_tk_sub"),
            font=("Segoe UI", 8),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
        ).pack(anchor="w", pady=(2, 0))

        # Notebook tabs (10 Dedicated Tabs)
        nb = ttk.Notebook(frame)
        nb.pack(fill=tk.BOTH, expand=True)

        card_bg = "#ffffff" if not self.dark_mode else "#2d3342"
        border_c = "#dadce0" if not self.dark_mode else "#3c4043"

        port_val = res.get("portfolio_value", 0.0)
        ann_rle = res.get("annual_rle", 0.0)
        cur_safe = res.get("current_safe_assets", 0.0)

        # =========================================================
        # TAB 1: BLANCHETT SPENDING SMILE
        # =========================================================
        t1 = ttk.Frame(nb, padding=10)
        nb.add(t1, text=f" {t('fire_tk_tab_1')} ")

        smile_data = res.get("spending_smile_data", {})
        if smile_data:
            cards_f1 = tk.Frame(t1)
            cards_f1.pack(fill=tk.X, pady=(0, 8))

            c_info = [
                (t("fire_tk_gogo_card"), smile_data.get("gogo_annual", 0), t("fire_tk_gogo_note"), "#e8f0fe", "#1a73e8"),
                (t("fire_tk_slowgo_card"), smile_data.get("slowgo_annual", 0), t("fire_tk_slowgo_note"), "#e6f4ea", "#188038"),
                (t("fire_tk_care_card"), smile_data.get("care_annual", 0), t("fire_tk_care_note"), "#fce8e6", "#d93025"),
            ]
            for title, amt, note, bg_col, fg_col in c_info:
                card = tk.Frame(cards_f1, bg=bg_col, bd=1, relief="solid", highlightbackground=fg_col, padx=8, pady=8)
                card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
                tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), fg=fg_col, bg=bg_col).pack(anchor="w")
                tk.Label(card, text=f"${amt:,.0f} / yr", font=("Segoe UI", 12, "bold"), fg=self.text_dark, bg=bg_col).pack(anchor="w", pady=2)
                tk.Label(card, text=note, font=("Segoe UI", 8), fg=self.text_dark, bg=bg_col).pack(anchor="w")

            sav_banner = tk.Frame(t1, bg="#e6f4ea", bd=1, relief="solid", padx=10, pady=6)
            sav_banner.pack(fill=tk.X, pady=(0, 8))
            tot_flat = smile_data.get("flat_total_lifetime", 0)
            tot_smile = smile_data.get("smile_total_lifetime", 0)
            savings = smile_data.get("capital_savings", 0)
            sav_pct = smile_data.get("savings_pct", 0)
            tk.Label(
                sav_banner,
                text=t("fire_tk_smile_banner", tot_smile=tot_smile, tot_flat=tot_flat),
                font=("Segoe UI", 9, "bold"),
                fg="#137333",
                bg="#e6f4ea",
            ).pack(anchor="w")
            tk.Label(
                sav_banner,
                text=t("fire_tk_smile_savings", savings=savings, sav_pct=sav_pct),
                font=("Segoe UI", 8),
                fg=self.text_dark,
                bg="#e6f4ea",
            ).pack(anchor="w")

            cols1 = ("age", "phase", "mult", "spend", "cum")
            tr1 = ttk.Treeview(t1, columns=cols1, show="headings", height=8, selectmode="browse")
            tr1.heading("age", text=t("col_tk_age"))
            tr1.heading("phase", text=t("col_tk_phase"))
            tr1.heading("mult", text=t("col_tk_mult"))
            tr1.heading("spend", text=t("col_tk_annual_spend"))
            tr1.heading("cum", text=t("col_tk_cum_spend"))
            tr1.column("age", width=70, anchor="center")
            tr1.column("phase", width=150, anchor="w")
            tr1.column("mult", width=90, anchor="center")
            tr1.column("spend", width=160, anchor="e")
            tr1.column("cum", width=180, anchor="e")

            for row in smile_data.get("annual_schedule", []):
                tr1.insert("", tk.END, values=(
                    f"{row['age']}",
                    row.get("phase_desc", row["phase"]),
                    f"{row['multiplier']:.2f}x",
                    f"${row['annual_spending']:,.0f}",
                    f"${row['cumulative_total']:,.0f}",
                ))
            sb1 = ttk.Scrollbar(t1, orient="vertical", command=tr1.yview)
            tr1.configure(yscrollcommand=sb1.set)
            tr1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb1.pack(side=tk.RIGHT, fill=tk.Y)

        # =========================================================
        # TAB 2: SEQUENCE OF RETURNS RISK (SRR CRASH SIMULATION)
        # =========================================================
        t2 = ttk.Frame(nb, padding=10)
        nb.add(t2, text=f" {t('fire_tk_tab_2')} ")

        srr_top = tk.Frame(t2)
        srr_top.pack(fill=tk.X, pady=(0, 8))

        tk.Label(srr_top, text=t("fire_tk_srr_select"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 8))

        scen_key_map = {
            t("scen_1973"): "stagflation_1973",
            t("scen_1929"): "great_depression_1929",
            t("scen_2000"): "dot_com_2000",
            t("scen_2008"): "gfc_2008",
            t("scen_custom"): "custom",
        }
        scen_combo = ttk.Combobox(
            srr_top,
            values=list(scen_key_map.keys()),
            state="readonly",
            width=38,
            font=("Segoe UI", 9),
        )
        scen_combo.set(t("scen_1973"))
        scen_combo.pack(side=tk.LEFT)

        srr_cards_f = tk.Frame(t2)
        srr_cards_f.pack(fill=tk.X, pady=(0, 8))

        srr_c1 = tk.Frame(srr_cards_f, bg="#fce8e6", bd=1, relief="solid", highlightbackground="#d93025", padx=8, pady=8)
        srr_c1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        lbl_srr_c1_title = tk.Label(srr_c1, text=t("fire_tk_srr_unprotected_title"), font=("Segoe UI", 8, "bold"), fg="#d93025", bg="#fce8e6")
        lbl_srr_c1_title.pack(anchor="w")
        lbl_srr_c1_val = tk.Label(srr_c1, text="", font=("Segoe UI", 12, "bold"), fg=self.text_dark, bg="#fce8e6")
        lbl_srr_c1_val.pack(anchor="w", pady=2)
        lbl_srr_c1_sub = tk.Label(srr_c1, text="", font=("Segoe UI", 8), fg=self.text_dark, bg="#fce8e6")
        lbl_srr_c1_sub.pack(anchor="w")

        srr_c2 = tk.Frame(srr_cards_f, bg="#e6f4ea", bd=1, relief="solid", highlightbackground="#188038", padx=8, pady=8)
        srr_c2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        lbl_srr_c2_title = tk.Label(srr_c2, text=t("fire_tk_srr_protected_title"), font=("Segoe UI", 8, "bold"), fg="#188038", bg="#e6f4ea")
        lbl_srr_c2_title.pack(anchor="w")
        lbl_srr_c2_val = tk.Label(srr_c2, text="", font=("Segoe UI", 12, "bold"), fg=self.text_dark, bg="#e6f4ea")
        lbl_srr_c2_val.pack(anchor="w", pady=2)
        lbl_srr_c2_sub = tk.Label(srr_c2, text="", font=("Segoe UI", 8), fg=self.text_dark, bg="#e6f4ea")
        lbl_srr_c2_sub.pack(anchor="w")

        cols2 = ("year", "return", "no_buf", "with_buf", "safe_rem")
        tr2 = ttk.Treeview(t2, columns=cols2, show="headings", height=8, selectmode="browse")
        tr2.heading("year", text=t("col_tk_year"))
        tr2.heading("return", text=t("col_tk_mkt_return"))
        tr2.heading("no_buf", text=t("col_tk_port_no_buf"))
        tr2.heading("with_buf", text=t("col_tk_port_with_buf"))
        tr2.heading("safe_rem", text=t("col_tk_safe_rem"))
        tr2.column("year", width=70, anchor="center")
        tr2.column("return", width=110, anchor="center")
        tr2.column("no_buf", width=170, anchor="e")
        tr2.column("with_buf", width=180, anchor="e")
        tr2.column("safe_rem", width=170, anchor="e")
        tr2.pack(fill=tk.BOTH, expand=True)

        def _update_srr(*_):
            sc_key = scen_key_map.get(scen_combo.get(), "stagflation_1973")
            srr_res = calc_sequence_of_returns_risk_simulation(
                portfolio_val=port_val,
                annual_withdrawal=ann_rle,
                safe_assets_val=cur_safe,
                crash_scenario=sc_key,
            )
            term_no = srr_res.get("terminal_no_buffer", 0)
            term_buf = srr_res.get("terminal_with_buffer", 0)
            dep_no = srr_res.get("depleted_no_buffer_year")
            sav = srr_res.get("equity_capital_saved", 0)

            lbl_srr_c1_val.config(text=t("fire_tk_srr_terminal", term=term_no))
            lbl_srr_c1_sub.config(text=t("fire_tk_srr_depleted", dep=dep_no) if dep_no else t("fire_tk_srr_survived"))

            lbl_srr_c2_val.config(text=t("fire_tk_srr_terminal", term=term_buf))
            lbl_srr_c2_sub.config(text=f"{t('fire_tk_srr_saved_lbl', sav=sav)} {t('fire_tk_srr_solvency')}")

            for item in tr2.get_children():
                tr2.delete(item)

            c_no = srr_res.get("curve_no_buffer", [])
            c_buf = srr_res.get("curve_with_buffer", [])
            for idx in range(len(c_no)):
                row_no = c_no[idx]
                row_buf = c_buf[idx]
                tr2.insert("", tk.END, values=(
                    f"{row_no['year']}",
                    f"{row_no['return_pct']:+.1f}%",
                    f"${row_no['balance']:,.0f}",
                    f"${row_buf['balance']:,.0f}",
                    f"${row_buf.get('safe_remaining', 0):,.0f}",
                ))

        scen_combo.bind("<<ComboboxSelected>>", _update_srr)
        _update_srr()

        # =========================================================
        # TAB 3: GUYTON-KLINGER GUARDRAILS
        # =========================================================
        t3 = ttk.Frame(nb, padding=10)
        nb.add(t3, text=f" {t('fire_tk_tab_3')} ")

        gk_data = res.get("guardrails_data", {})
        if gk_data:
            trig = gk_data.get("rule_triggered", "none")
            bg_gk = "#e6f4ea" if trig == "none" else ("#fce8e6" if trig == "capital_preservation" else "#e8f0fe")
            fg_gk = "#137333" if trig == "none" else ("#d93025" if trig == "capital_preservation" else "#1a73e8")

            gk_banner = tk.Frame(t3, bg=bg_gk, bd=1, relief="solid", padx=10, pady=8)
            gk_banner.pack(fill=tk.X, pady=(0, 10))

            tk.Label(gk_banner, text=t("fire_tk_gk_status", status=trig.replace('_', ' ').title()), font=("Segoe UI", 10, "bold"), fg=fg_gk, bg=bg_gk).pack(anchor="w")
            tk.Label(gk_banner, text=gk_data.get("rule_desc", ""), font=("Segoe UI", 9), fg=self.text_dark, bg=bg_gk).pack(anchor="w", pady=(2, 0))

            cards_gk = tk.Frame(t3)
            cards_gk.pack(fill=tk.X, pady=(0, 10))

            cur_rate = gk_data.get("current_withdrawal_rate_pct", 0)
            cur_draw = gk_data.get("current_annual_withdrawal", 0)
            up_rate = gk_data.get("upper_guardrail_pct", 0)
            up_dol = gk_data.get("upper_guardrail_dollars", 0)
            low_rate = gk_data.get("lower_guardrail_pct", 0)
            low_dol = gk_data.get("lower_guardrail_dollars", 0)
            rec_draw = gk_data.get("recommended_withdrawal", 0)
            adj_pct = gk_data.get("adjustment_pct", 0)

            c_gk_info = [
                (t("fire_tk_gk_cur_swr"), f"{cur_rate:.2f}%", f"${cur_draw:,.0f} / yr", card_bg, border_c),
                (t("fire_tk_gk_upper_card"), f"{up_rate:.2f}%", t("fire_tk_gk_cap_fmt", amt=up_dol), card_bg, "#d93025"),
                (t("fire_tk_gk_lower_card"), f"{low_rate:.2f}%", t("fire_tk_gk_floor_fmt", amt=low_dol), card_bg, "#188038"),
                (t("fire_tk_gk_rec_card"), f"${rec_draw:,.0f}", t("fire_tk_gk_adj_fmt", adj=adj_pct), card_bg, "#1a73e8"),
            ]
            for title, val, sub, bg_c, bd_c in c_gk_info:
                card = tk.Frame(cards_gk, bg=bg_c, bd=1, relief="solid", highlightbackground=bd_c, padx=8, pady=8)
                card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
                tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), fg=bd_c, bg=bg_c).pack(anchor="w")
                tk.Label(card, text=val, font=("Segoe UI", 12, "bold"), fg=self.text_dark, bg=bg_c).pack(anchor="w", pady=2)
                tk.Label(card, text=sub, font=("Segoe UI", 8), fg=self.text_dark, bg=bg_c).pack(anchor="w")

            guide_box3 = tk.Frame(t3, bg="#f8f9fa" if not self.dark_mode else "#252830", bd=1, relief="solid", padx=10, pady=8)
            guide_box3.pack(fill=tk.BOTH, expand=True)
            tk.Label(guide_box3, text=t("fire_tk_gk_principles_title"), font=("Segoe UI", 9, "bold"), fg="#1a73e8", bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w")
            tk.Label(guide_box3, text=t("fire_tk_gk_principles_body"), font=("Segoe UI", 8), justify=tk.LEFT, fg=self.text_dark, bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w", pady=(4, 0))

        # =========================================================
        # TAB 4: 3-BUCKET RUNWAY ARCHITECTURE
        # =========================================================
        t4 = ttk.Frame(nb, padding=10)
        nb.add(t4, text=f" {t('fire_tk_tab_4')} ")

        b_data = res.get("three_bucket_data", {})
        if b_data:
            rw_yrs = b_data.get("total_safe_runway_years", 0)
            rw_banner = tk.Frame(t4, bg="#e8f0fe", bd=1, relief="solid", padx=10, pady=8)
            rw_banner.pack(fill=tk.X, pady=(0, 10))

            tk.Label(
                rw_banner,
                text=t("fire_tk_b_runway_title", yrs=rw_yrs),
                font=("Segoe UI", 10, "bold"),
                fg="#1a73e8",
                bg="#e8f0fe",
            ).pack(anchor="w")
            tk.Label(
                rw_banner,
                text=t("fire_tk_b_runway_desc"),
                font=("Segoe UI", 8),
                fg=self.text_dark,
                bg="#e8f0fe",
            ).pack(anchor="w", pady=(2, 0))

            cards_b = tk.Frame(t4)
            cards_b.pack(fill=tk.X, pady=(0, 10))

            b_info = [
                (
                    t("fire_tk_b1_title"),
                    b_data.get("bucket1_target", 0),
                    b_data.get("bucket1_actual", 0),
                    t("fire_tk_b1_note", mo=b_data.get("bucket1_runway_months", 0), pct=b_data.get("bucket1_funded_pct", 0)),
                    "#e6f4ea" if b_data.get("bucket1_gap", 0) == 0 else "#fef7e0",
                    "#188038" if b_data.get("bucket1_gap", 0) == 0 else "#b06000",
                ),
                (
                    t("fire_tk_b2_title"),
                    b_data.get("bucket2_target", 0),
                    b_data.get("bucket2_actual", 0),
                    t("fire_tk_b2_note", mo=b_data.get("bucket2_runway_months", 0)),
                    "#e8f0fe",
                    "#1a73e8",
                ),
                (
                    t("fire_tk_b3_title"),
                    b_data.get("bucket3_target", 0),
                    b_data.get("bucket3_actual", 0),
                    t("fire_tk_b3_note"),
                    card_bg,
                    "#681da8",
                ),
            ]
            for title, tgt, act, note, bg_c, fg_c in b_info:
                card = tk.Frame(cards_b, bg=bg_c, bd=1, relief="solid", highlightbackground=fg_c, padx=8, pady=8)
                card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
                tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), fg=fg_c, bg=bg_c).pack(anchor="w")
                tk.Label(card, text=t("fire_tk_b_actual", act=act), font=("Segoe UI", 11, "bold"), fg=self.text_dark, bg=bg_c).pack(anchor="w", pady=2)
                tk.Label(card, text=t("fire_tk_b_target", tgt=tgt), font=("Segoe UI", 8), fg=self.text_dark, bg=bg_c).pack(anchor="w")
                tk.Label(card, text=note, font=("Segoe UI", 8, "italic"), fg=fg_c, bg=bg_c).pack(anchor="w", pady=(2, 0))

            gap_f = tk.Frame(t4, bg="#f8f9fa" if not self.dark_mode else "#252830", bd=1, relief="solid", padx=10, pady=8)
            gap_f.pack(fill=tk.BOTH, expand=True)

            b1_gap = b_data.get("bucket1_gap", 0)
            if b1_gap > 0:
                gap_txt = t("fire_tk_b1_gap_alert", gap=b1_gap)
                gap_col = "#d93025"
            else:
                gap_txt = t("fire_tk_b1_ok_alert", mo=b_data.get("bucket1_runway_months", 0))
                gap_col = "#188038"

            tk.Label(gap_f, text=t("fire_tk_b_health_title"), font=("Segoe UI", 9, "bold"), fg=gap_col, bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w")
            tk.Label(gap_f, text=gap_txt, font=("Segoe UI", 8), fg=self.text_dark, bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w", pady=(2, 0))

        # =========================================================
        # TAB 5: HEALTHCARE & LTC CONTINGENCY SHOCK AUDIT
        # =========================================================
        t5 = ttk.Frame(nb, padding=10)
        nb.add(t5, text=f" {t('fire_tk_tab_5')} ")

        ltc_data = res.get("ltc_data", {})
        if ltc_data:
            can_abs = ltc_data.get("can_absorb", True)
            bg_ltc = "#e6f4ea" if can_abs else "#fce8e6"
            fg_ltc = "#188038" if can_abs else "#d93025"

            ltc_f = tk.Frame(t5, bg=bg_ltc, bd=1, relief="solid", padx=10, pady=8)
            ltc_f.pack(fill=tk.X, pady=(0, 10))

            status_str = t("fire_tk_ltc_solvent") if can_abs else t("fire_tk_ltc_vulnerable")
            tk.Label(
                ltc_f,
                text=t("fire_tk_ltc_title", status=status_str),
                font=("Segoe UI", 10, "bold"),
                fg=fg_ltc,
                bg=bg_ltc,
            ).pack(anchor="w")

            cost_yr = ltc_data.get("annual_ltc_cost", 0)
            tot_ltc = ltc_data.get("total_ltc_cost", 0)
            pv_ltc = ltc_data.get("present_value_needed", 0)
            imp_pct = ltc_data.get("ltc_wealth_impact_pct", 0)
            st_age = ltc_data.get("ltc_start_age", 83)
            dur_yr = ltc_data.get("ltc_duration_years", 4)

            tk.Label(
                ltc_f,
                text=t("fire_tk_ltc_desc", start=st_age, dur=dur_yr, cost=cost_yr, tot=tot_ltc, pv=pv_ltc, pct=imp_pct),
                font=("Segoe UI", 8),
                fg=self.text_dark,
                bg=bg_ltc,
            ).pack(anchor="w", pady=(2, 0))

            cards_ltc = tk.Frame(t5)
            cards_ltc.pack(fill=tk.X, pady=(0, 10))

            c_ltc_info = [
                ("Nominal Shock Cost", f"${tot_ltc:,.0f}", f"{dur_yr} Yrs @ ${cost_yr:,.0f}/yr", card_bg, border_c),
                ("Present Value Needed", f"${pv_ltc:,.0f}", f"Discounted @ 4.0% Real", card_bg, "#1a73e8"),
                ("Impact on Total Wealth", f"{imp_pct:.1f}%", "Solvent" if can_abs else "Coverage Needed", bg_ltc, fg_ltc),
            ]
            for title, val, sub, bg_c, bd_c in c_ltc_info:
                card = tk.Frame(cards_ltc, bg=bg_c, bd=1, relief="solid", highlightbackground=bd_c, padx=8, pady=8)
                card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
                tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), fg=bd_c, bg=bg_c).pack(anchor="w")
                tk.Label(card, text=val, font=("Segoe UI", 12, "bold"), fg=self.text_dark, bg=bg_c).pack(anchor="w", pady=2)
                tk.Label(card, text=sub, font=("Segoe UI", 8), fg=self.text_dark, bg=bg_c).pack(anchor="w")

            guide_ltc = tk.Frame(t5, bg="#f8f9fa" if not self.dark_mode else "#252830", bd=1, relief="solid", padx=10, pady=8)
            guide_ltc.pack(fill=tk.BOTH, expand=True)
            tk.Label(guide_ltc, text=t("fire_tk_ltc_tips_title"), font=("Segoe UI", 9, "bold"), fg="#1a73e8", bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w")
            tk.Label(guide_ltc, text=t("fire_tk_ltc_tips_body"), font=("Segoe UI", 8), justify=tk.LEFT, fg=self.text_dark, bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w", pady=(4, 0))

        # =========================================================
        # TAB 6: ACTUARIAL LONGEVITY TABLE
        # =========================================================
        t6 = ttk.Frame(nb, padding=10)
        nb.add(t6, text=f" {t('fire_tk_tab_6')} ")

        long_data = res.get("longevity_data", {})
        if long_data:
            rec_age = long_data.get("recommended_planning_age", 95)
            tk.Label(
                t6,
                text=t("fire_tk_long_title", age=rec_age),
                font=("Segoe UI", 9, "bold"),
                fg="#1a73e8",
            ).pack(anchor="w", pady=(0, 6))

            cols6 = ("age", "male", "female", "joint")
            tr6 = ttk.Treeview(t6, columns=cols6, show="headings", height=7, selectmode="browse")
            tr6.heading("age", text=t("col_tk_target_age"))
            tr6.heading("male", text=t("col_tk_male_prob"))
            tr6.heading("female", text=t("col_tk_female_prob"))
            tr6.heading("joint", text=t("col_tk_joint_prob"))
            tr6.column("age", width=140, anchor="center")
            tr6.column("male", width=140, anchor="center")
            tr6.column("female", width=140, anchor="center")
            tr6.column("joint", width=160, anchor="center")

            for row in long_data.get("longevity_schedule", []):
                tr6.insert("", tk.END, values=(
                    f"Age {row['target_age']}",
                    f"{row['prob_male']:.1f}%",
                    f"{row['prob_female']:.1f}%",
                    f"{row['prob_joint']:.1f}%",
                ))
            tr6.pack(fill=tk.X, pady=(0, 10))

            guide_long = tk.Frame(t6, bg="#f8f9fa" if not self.dark_mode else "#252830", bd=1, relief="solid", padx=10, pady=8)
            guide_long.pack(fill=tk.BOTH, expand=True)
            tk.Label(guide_long, text=t("fire_tk_long_guidance_title"), font=("Segoe UI", 9, "bold"), fg="#1a73e8", bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w")
            tk.Label(guide_long, text=t("fire_tk_long_guidance_body"), font=("Segoe UI", 8), justify=tk.LEFT, fg=self.text_dark, bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w", pady=(4, 0))

        # =========================================================
        # TAB 7: MONTE CARLO 500-TRIAL PERCENTILES
        # =========================================================
        t7 = ttk.Frame(nb, padding=10)
        nb.add(t7, text=f" {t('fire_tk_tab_7')} ")

        mc = res.get("monte_carlo_dist", {})
        if mc:
            tk.Label(t7, text=t("fire_tk_mc_title"), font=("Segoe UI", 9, "bold"), fg="#1a73e8").pack(anchor="w", pady=(0, 6))
            mc_cards = tk.Frame(t7)
            mc_cards.pack(fill=tk.X, pady=(0, 10))

            mc_info = [
                (t("fire_tk_mc_success"), f"{mc.get('success_rate_pct', 0):.1f}%", t("fire_tk_mc_success_note"), "#e6f4ea", "#188038"),
                (t("fire_tk_mc_p10"), f"${mc.get('p10_terminal_wealth', 0):,.0f}", t("fire_tk_mc_p10_note"), "#fce8e6", "#d93025"),
                (t("fire_tk_mc_p50"), f"${mc.get('p50_terminal_wealth', 0):,.0f}", t("fire_tk_mc_p50_note"), "#e8f0fe", "#1a73e8"),
                (t("fire_tk_mc_p90"), f"${mc.get('p90_terminal_wealth', 0):,.0f}", t("fire_tk_mc_p90_note"), card_bg, "#681da8"),
            ]
            for title, val, note, bg_c, fg_c in mc_info:
                card = tk.Frame(mc_cards, bg=bg_c, bd=1, relief="solid", highlightbackground=fg_c, padx=8, pady=6)
                card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
                tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), fg=fg_c, bg=bg_c).pack(anchor="w")
                tk.Label(card, text=val, font=("Segoe UI", 11, "bold"), fg=self.text_dark, bg=bg_c).pack(anchor="w", pady=2)
                tk.Label(card, text=note, font=("Segoe UI", 8), fg=self.text_dark, bg=bg_c).pack(anchor="w")

            guide_mc = tk.Frame(t7, bg="#f8f9fa" if not self.dark_mode else "#252830", bd=1, relief="solid", padx=10, pady=8)
            guide_mc.pack(fill=tk.BOTH, expand=True)
            tk.Label(guide_mc, text=t("fire_tk_mc_guide_title"), font=("Segoe UI", 9, "bold"), fg="#1a73e8", bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w")
            tk.Label(guide_mc, text=t("fire_tk_mc_guide_body"), font=("Segoe UI", 8), justify=tk.LEFT, fg=self.text_dark, bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w", pady=(4, 0))

        # =========================================================
        # TAB 8: STAGFLATION SENSITIVITY MATRIX
        # =========================================================
        t8 = ttk.Frame(nb, padding=10)
        nb.add(t8, text=f" {t('fire_tk_tab_8')} ")

        stag = res.get("stagflation_data", {})
        if stag:
            tk.Label(t8, text=t("fire_tk_stag_title"), font=("Segoe UI", 9, "bold"), fg="#e37400").pack(anchor="w", pady=(0, 6))
            cols8 = ("infl", "r1", "r3", "r5", "r7")
            tr8 = ttk.Treeview(t8, columns=cols8, show="headings", height=5, selectmode="browse")
            tr8.heading("infl", text=t("col_tk_infl_level"))
            tr8.heading("r1", text=t("col_tk_r1"))
            tr8.heading("r3", text=t("col_tk_r3"))
            tr8.heading("r5", text=t("col_tk_r5"))
            tr8.heading("r7", text=t("col_tk_r7"))
            tr8.column("infl", width=140, anchor="w")
            tr8.column("r1", width=140, anchor="center")
            tr8.column("r3", width=140, anchor="center")
            tr8.column("r5", width=140, anchor="center")
            tr8.column("r7", width=140, anchor="center")

            for row in stag.get("matrix", []):
                vals = [f"{row[0]['inflation_pct']:.1f}%"]
                for cell in row:
                    dur = cell["longevity_years"]
                    vals.append(t("fire_tk_perpetual") if cell["is_perpetual"] else t("fire_tk_years_fmt", yr=dur))
                tr8.insert("", tk.END, values=tuple(vals))
            tr8.pack(fill=tk.X, pady=(0, 10))

            guide_stag = tk.Frame(t8, bg="#f8f9fa" if not self.dark_mode else "#252830", bd=1, relief="solid", padx=10, pady=8)
            guide_stag.pack(fill=tk.BOTH, expand=True)
            tk.Label(guide_stag, text=t("fire_tk_stag_guide_title"), font=("Segoe UI", 9, "bold"), fg="#e37400", bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w")
            tk.Label(guide_stag, text=t("fire_tk_stag_guide_body"), font=("Segoe UI", 8), justify=tk.LEFT, fg=self.text_dark, bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w", pady=(4, 0))

        # =========================================================
        # TAB 9: RISING EQUITY GLIDEPATH (KITCES-PFAU)
        # =========================================================
        t9 = ttk.Frame(nb, padding=10)
        nb.add(t9, text=f" {t('fire_tk_tab_9')} ")

        glide = res.get("glidepath_data", {})
        if glide:
            cur_eq = glide.get("current_equity_pct", 60.0)
            tgt_eq = glide.get("target_equity_pct", 50.0)
            tgt_bd = glide.get("target_bond_pct", 50.0)
            dev = glide.get("deviation_pct", 0.0)
            phase = glide.get("phase_desc", "")

            gp_banner = tk.Frame(t9, bg="#e8f0fe", bd=1, relief="solid", padx=10, pady=8)
            gp_banner.pack(fill=tk.X, pady=(0, 10))

            tk.Label(gp_banner, text=t("fire_tk_gp_title"), font=("Segoe UI", 10, "bold"), fg="#1a73e8", bg="#e8f0fe").pack(anchor="w")
            tk.Label(gp_banner, text=phase, font=("Segoe UI", 9), fg=self.text_dark, bg="#e8f0fe").pack(anchor="w", pady=(2, 0))

            cards_gp = tk.Frame(t9)
            cards_gp.pack(fill=tk.X, pady=(0, 10))

            dev_status = t("fire_tk_gp_over") if dev > 5 else (t("fire_tk_gp_under") if dev < -5 else t("fire_tk_gp_in_corridor"))
            gp_info = [
                (t("fire_tk_gp_cur_card"), f"{cur_eq:.1f}%", t("fire_tk_gp_cur_note"), card_bg, border_c),
                (t("fire_tk_gp_tgt_card"), f"{tgt_eq:.1f}%", t("fire_tk_gp_safe_tgt", pct=tgt_bd), "#e6f4ea", "#188038"),
                (t("fire_tk_gp_dev_card"), f"{dev:+.1f}%", dev_status, card_bg, "#e37400"),
            ]
            for title, val, note, bg_c, fg_c in gp_info:
                card = tk.Frame(cards_gp, bg=bg_c, bd=1, relief="solid", highlightbackground=fg_c, padx=8, pady=8)
                card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
                tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), fg=fg_c, bg=bg_c).pack(anchor="w")
                tk.Label(card, text=val, font=("Segoe UI", 12, "bold"), fg=self.text_dark, bg=bg_c).pack(anchor="w", pady=2)
                tk.Label(card, text=note, font=("Segoe UI", 8), fg=self.text_dark, bg=bg_c).pack(anchor="w")

            guide_gp = tk.Frame(t9, bg="#f8f9fa" if not self.dark_mode else "#252830", bd=1, relief="solid", padx=10, pady=8)
            guide_gp.pack(fill=tk.BOTH, expand=True)

            tk.Label(guide_gp, text=t("fire_tk_gp_findings_title"), font=("Segoe UI", 9, "bold"), fg="#1a73e8", bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w")
            tk.Label(guide_gp, text=t("fire_tk_gp_findings_body"), font=("Segoe UI", 8), justify=tk.LEFT, fg=self.text_dark, bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w", pady=(4, 0))

        # =========================================================
        # TAB 10: EXECUTIVE DIAGNOSTIC SUMMARY & ACTION PLAN
        # =========================================================
        t10 = ttk.Frame(nb, padding=10)
        nb.add(t10, text=f" {t('fire_tk_tab_10')} ")

        # Readiness Grade calculation
        rw_yrs = b_data.get("total_safe_runway_years", 0)
        mc_rate = mc.get("success_rate_pct", 0)
        ltc_ok = ltc_data.get("can_absorb", True)
        if rw_yrs >= 4.0 and mc_rate >= 85.0 and ltc_ok:
            grade = "A+ (Institutional Grade Ready)"
            grade_col = "#188038"
            bg_grade = "#e6f4ea"
        elif rw_yrs >= 2.0 and mc_rate >= 75.0:
            grade = "B+ (Substantial Security / Minor Optimization)"
            grade_col = "#1a73e8"
            bg_grade = "#e8f0fe"
        else:
            grade = "C (Action Required / Buffer Needed)"
            grade_col = "#c5221f"
            bg_grade = "#fce8e6"

        sum_banner = tk.Frame(t10, bg=bg_grade, bd=1, relief="solid", padx=10, pady=8)
        sum_banner.pack(fill=tk.X, pady=(0, 10))

        tk.Label(sum_banner, text=t("fire_tk_summary_score_title", grade=grade), font=("Segoe UI", 11, "bold"), fg=grade_col, bg=bg_grade).pack(anchor="w")
        tk.Label(sum_banner, text=t("fire_tk_summary_score_desc"), font=("Segoe UI", 8), fg=self.text_dark, bg=bg_grade).pack(anchor="w", pady=(2, 0))

        # 4 Core Pillar Health Cards
        cards_sum = tk.Frame(t10)
        cards_sum.pack(fill=tk.X, pady=(0, 10))

        pillars = [
            (t("fire_tk_metric_runway"), f"{rw_yrs:.1f} Yrs", "Liquid Cash / Safe Runway", "#e6f4ea" if rw_yrs >= 2.0 else "#fce8e6", "#188038" if rw_yrs >= 2.0 else "#d93025"),
            (t("fire_tk_metric_srr"), f"{mc_rate:.1f}%", "30-Year Stochastic Solvency", "#e8f0fe", "#1a73e8"),
            (t("fire_tk_metric_long"), "Solvent" if ltc_ok else "Caution", "Age 83-87 LTC Contingency", "#e6f4ea" if ltc_ok else "#fce8e6", "#188038" if ltc_ok else "#d93025"),
            (t("fire_tk_metric_guard"), f"{gk_data.get('current_withdrawal_rate_pct', 0):.2f}%", f"Floor: {gk_data.get('lower_guardrail_pct', 0):.1f}% / Cap: {gk_data.get('upper_guardrail_pct', 0):.1f}%", card_bg, "#681da8"),
        ]
        for title, val, sub, bg_c, fg_c in pillars:
            card = tk.Frame(cards_sum, bg=bg_c, bd=1, relief="solid", highlightbackground=fg_c, padx=8, pady=8)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
            tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), fg=fg_c, bg=bg_c).pack(anchor="w")
            tk.Label(card, text=val, font=("Segoe UI", 12, "bold"), fg=self.text_dark, bg=bg_c).pack(anchor="w", pady=2)
            tk.Label(card, text=sub, font=("Segoe UI", 8), fg=self.text_dark, bg=bg_c).pack(anchor="w")

        # Action Checklist Box
        act_box = tk.Frame(t10, bg="#f8f9fa" if not self.dark_mode else "#252830", bd=1, relief="solid", padx=10, pady=10)
        act_box.pack(fill=tk.BOTH, expand=True)

        tk.Label(act_box, text=t("fire_tk_summary_check_title"), font=("Segoe UI", 9, "bold"), fg="#1a73e8", bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w", pady=(0, 4))
        for act_key in ["fire_tk_act_1", "fire_tk_act_2", "fire_tk_act_3", "fire_tk_act_4"]:
            tk.Label(act_box, text=t(act_key), font=("Segoe UI", 8), fg=self.text_dark, bg="#f8f9fa" if not self.dark_mode else "#252830").pack(anchor="w", pady=2)

        # Bottom Bar: Export Report & Close
        btn_box = tk.Frame(frame)
        btn_box.pack(fill=tk.X, pady=(10, 0))

        def _export_toolkit_report():
            from tkinter import filedialog
            p = filedialog.asksaveasfilename(
                title=t("btn_export_toolkit_report"),
                defaultextension=".md",
                filetypes=[("Markdown Report", "*.md"), ("Text Document", "*.txt")],
                initialfile="Institutional_Retirement_Diagnostic_Report.md",
                parent=dlg,
            )
            if not p:
                return
            try:
                content = [
                    f"# 🚀 Institutional Retirement & Actuarial Planning Diagnostic Report",
                    f"*Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n",
                    f"## 1. Executive Summary",
                    f"- Current Age: {res.get('current_age', 60)} | Target Retirement Age: {res.get('retire_age', 65)} | Planning Horizon: {res.get('life_expectancy', 90)}",
                    f"- Total Liquid Wealth: ${res.get('portfolio_value', 0):,.2f} | Safe Assets Buffer: ${res.get('current_safe_assets', 0):,.2f}",
                    f"- Real Living Expenditure (Annual): ${res.get('annual_rle', 0):,.2f} | Base Monthly Expense: ${res.get('target_monthly_expense', 0):,.2f}",
                    f"- Safe Asset Runway: {b_data.get('total_safe_runway_years', 0):.1f} Years of Living Reserves",
                    f"- Overall Readiness Grade: {grade}\n",
                    f"## 2. David Blanchett Spending Smile Analysis",
                    f"- Flat Lifetime Spending Projection: ${smile_data.get('flat_total_lifetime', 0):,.2f}",
                    f"- Blanchett Spending Smile Lifetime: ${smile_data.get('smile_total_lifetime', 0):,.2f}",
                    f"- Actuarial Capital Saved: +${smile_data.get('capital_savings', 0):,.2f} ({smile_data.get('savings_pct', 0):+.1f}%)\n",
                    f"## 3. Sequence of Returns Risk (SRR Crash Simulation)",
                    f"- Scenario: 1973-1974 Stagflation Simulation",
                    f"- Unprotected Terminal Wealth: ${res.get('srr_data', {}).get('terminal_no_buffer', 0):,.2f}",
                    f"- Protected Terminal Wealth: ${res.get('srr_data', {}).get('terminal_with_buffer', 0):,.2f}",
                    f"- Net Capital Shielded: +${res.get('srr_data', {}).get('equity_capital_saved', 0):,.2f}\n",
                    f"## 4. Guyton-Klinger Dynamic Guardrails",
                    f"- Initial SWR Benchmark: {gk_data.get('initial_swr_pct', 4.0):.2f}% | Current Withdrawal Rate: {gk_data.get('current_withdrawal_rate_pct', 0):.2f}%",
                    f"- Upper Guardrail: {gk_data.get('upper_guardrail_pct', 0):.2f}% | Lower Guardrail: {gk_data.get('lower_guardrail_pct', 0):.2f}%",
                    f"- Active Status: {gk_data.get('rule_desc', '')}\n",
                    f"## 5. Three-Bucket Retirement Runway Architecture",
                    f"- Bucket 1 (Cash/GIC 1-3y): ${b_data.get('bucket1_actual', 0):,.2f} / Target ${b_data.get('bucket1_target', 0):,.2f} ({b_data.get('bucket1_runway_months', 0):.0f} months)",
                    f"- Bucket 2 (Fixed Income 4-7y): ${b_data.get('bucket2_actual', 0):,.2f} / Target ${b_data.get('bucket2_target', 0):,.2f}",
                    f"- Bucket 3 (Equity Growth 8+y): ${b_data.get('bucket3_actual', 0):,.2f}\n",
                    f"## 6. Healthcare & Long-Term Care (LTC) Shock Audit",
                    f"- Projected LTC Shock: ${ltc_data.get('total_ltc_cost', 0):,.2f} nominal @ Age {ltc_data.get('ltc_start_age', 83)}",
                    f"- Present Value Discounted Capital Needed: ${ltc_data.get('present_value_needed', 0):,.2f} ({ltc_data.get('ltc_wealth_impact_pct', 0):.1f}% net worth)",
                    f"- Estate Solvency Status: {'SOLVENT' if ltc_data.get('can_absorb') else 'ATTENTION NEEDED'}\n",
                    f"## 7. Actuarial Longevity Probabilities",
                    f"- Recommended Planning Horizon: Age {long_data.get('recommended_planning_age', 95)}",
                    f"- 60->90 Joint Survivor Survival Probability: 55%+",
                    f"- 60->95 Joint Survivor Survival Probability: ~25%\n",
                    f"## 8. Monte Carlo 500-Trial Percentile Distribution",
                    f"- 30-Year Success Rate: {mc.get('success_rate_pct', 0):.1f}%",
                    f"- P10 Adverse Estate: ${mc.get('p10_terminal_wealth', 0):,.2f}",
                    f"- P50 Median Estate: ${mc.get('p50_terminal_wealth', 0):,.2f}",
                    f"- P90 Abundant Estate: ${mc.get('p90_terminal_wealth', 0):,.2f}\n",
                    f"## 9. Rising Equity Glidepath (Kitces-Pfau)",
                    f"- Current Equity: {glide.get('current_equity_pct', 0):.1f}% | Target Equity: {glide.get('target_equity_pct', 0):.1f}%",
                    f"- Status: {glide.get('phase_desc', '')}\n",
                    f"## 10. Prioritized Master Action Plan",
                    f"- 1. Liquid Cash & Safe Buffer: Secure 24 months of essential expenses in CASH.TO / VGSH / GIC.",
                    f"- 2. TIPS / Bond Ladder: Construct 5-7 year duration protection to immunize against early Sequence Risk.",
                    f"- 3. Dynamic Guardrails: Apply Guyton-Klinger +/-10% spending rule to prevent forced capital liquidation.",
                    f"- 4. Longevity & LTC: Verify estate solvency against age 83-87 healthcare shock contingency.\n",
                    f"---",
                    f"*Report generated by Google Finance Portfolio Tracker & Actuarial Diagnostic Suite.*",
                ]
                with open(p, "w", encoding="utf-8") as f_out:
                    f_out.write("\n".join(content))
                messagebox.showinfo("Export Success", f"Institutional retirement report exported successfully to:\n{p}", parent=dlg)
            except Exception as ex:
                messagebox.showerror("Export Failed", str(ex), parent=dlg)

        tk.Button(
            btn_box,
            text=f"📑 {t('btn_export_toolkit_report')}",
            font=("Segoe UI", 9, "bold"),
            bg="#1a73e8",
            fg="#ffffff",
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            command=_export_toolkit_report,
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_box,
            text=t("btn_close_window"),
            font=("Segoe UI", 9),
            padx=14,
            pady=4,
            command=dlg.destroy,
        ).pack(side=tk.RIGHT)

    def _show_pension_actuary_dialog(self):
        """Displays William J. Bernstein's Delay-to-70 longevity actuarial comparison dialog."""
        if not hasattr(self, "_last_fire_res"):
            self._refresh_fire_tab()
        res = getattr(self, "_last_fire_res", {})
        p_data = res.get("pension_actuary_data", {})
        if not p_data or p_data.get("base_annual_at_65", 0) <= 0:
            messagebox.showinfo(
                t("dlg_pension_actuary_title"),
                "Please enter a non-zero guaranteed annual pension in Step 3 to run the longevity actuary model.",
                parent=self.root,
            )
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_pension_actuary_title"))
        dlg.geometry("820x600")
        dlg.minsize(720, 520)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Header Title
        tk.Label(
            frame,
            text=f"⏳ {t('dlg_pension_actuary_title')}",
            font=("Segoe UI", 12, "bold"),
            fg="#1a73e8",
        ).pack(anchor="w")

        tk.Label(
            frame,
            text=t("lbl_pension_actuary_sub"),
            font=("Segoe UI", 9),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
        ).pack(anchor="w", pady=(1, 8))

        # 3 Claim Comparison Cards Side-by-Side
        cards_frame = tk.Frame(frame)
        cards_frame.pack(fill=tk.X, pady=(0, 10))

        c60 = p_data.get("claim_60", {})
        c65 = p_data.get("claim_65", {})
        c70 = p_data.get("claim_70", {})

        for title, info, bg_c, border_c in [
            (t("lbl_claim_card_60"), c60, "#fce8e6", "#d93025"),
            (t("lbl_claim_card_65"), c65, "#f8f9fa" if not self.dark_mode else "#2d3342", "#dadce0"),
            (t("lbl_claim_card_70"), c70, "#e6f4ea", "#188038"),
        ]:
            card = tk.Frame(cards_frame, bg=bg_c, bd=1, relief="solid", highlightbackground=border_c, padx=8, pady=8)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)

            tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), fg=border_c, bg=bg_c).pack(anchor="w")
            tk.Label(
                card,
                text=f"${info.get('monthly', 0):,.2f} / mo",
                font=("Segoe UI", 13, "bold"),
                fg=self.text_dark,
                bg=bg_c,
            ).pack(anchor="w", pady=2)
            tk.Label(
                card,
                text=f"${info.get('annual', 0):,.2f} / yr (Factor: {info.get('multiplier', 1.0):.2f}x)",
                font=("Segoe UI", 8),
                fg=self.text_dark,
                bg=bg_c,
            ).pack(anchor="w")

        # Break-Even Banner
        be_age = p_data.get("breakeven_age_70_vs_65", 83)
        be_frame = tk.Frame(frame, bg="#e8f0fe", bd=1, relief="solid", padx=10, pady=8)
        be_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            be_frame,
            text=t("lbl_breakeven_title", age=be_age),
            font=("Segoe UI", 10, "bold"),
            fg="#1a73e8",
            bg="#e8f0fe",
        ).pack(anchor="w")
        tk.Label(
            be_frame,
            text=t("lbl_breakeven_desc", age=be_age),
            font=("Segoe UI", 8),
            fg=self.text_dark,
            bg="#e8f0fe",
        ).pack(anchor="w", pady=(2, 0))

        # Milestone Table
        tk.Label(frame, text=t("lbl_payout_at_age"), font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        tree_frame = tk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("age", "c60", "c65", "c70", "diff")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=7, selectmode="browse")
        tree.heading("age", text=t("col_actuary_age"))
        tree.heading("c60", text=t("col_actuary_claim_60"))
        tree.heading("c65", text=t("col_actuary_claim_65"))
        tree.heading("c70", text=t("col_actuary_claim_70"))
        tree.heading("diff", text=t("col_actuary_diff_70_65"))

        tree.column("age", width=90, anchor="center")
        tree.column("c60", width=120, anchor="e")
        tree.column("c65", width=120, anchor="e")
        tree.column("c70", width=120, anchor="e")
        tree.column("diff", width=130, anchor="e")

        tree.tag_configure("positive_gain", foreground="#137333", font=("Segoe UI", 9, "bold"))
        tree.tag_configure("early_phase", foreground=self.text_dark)

        milestones = p_data.get("milestones", {})
        for m_age in sorted(milestones.keys()):
            m = milestones[m_age]
            diff_val = m["diff_70_vs_65"]
            diff_str = f"+${diff_val:,.2f}" if diff_val > 0 else f"-${abs(diff_val):,.2f}"
            tag = "positive_gain" if diff_val > 0 else "early_phase"
            tree.insert(
                "",
                tk.END,
                values=(
                    f"{m_age} 歲",
                    f"${m['cum_60']:,.2f}",
                    f"${m['cum_65']:,.2f}",
                    f"${m['cum_70']:,.2f}",
                    diff_str,
                ),
                tags=(tag,),
            )

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Bottom Close button
        btn_box = tk.Frame(frame)
        btn_box.pack(fill=tk.X, pady=(8, 0))
        tk.Button(btn_box, text=t("btn_close"), font=("Segoe UI", 9), padx=12, pady=3, command=dlg.destroy).pack(side=tk.RIGHT)

    def _show_deep_risk_dialog(self):
        """Displays William J. Bernstein's 4 Deep Risks diagnostic modal."""
        if not hasattr(self, "_last_fire_res"):
            self._refresh_fire_tab()
        res = getattr(self, "_last_fire_res", {})
        d_data = res.get("deep_risk_data")
        cur_safe = float(res.get("current_safe_assets", 0.0))
        tot_p = float(res.get("current_portfolio_val", getattr(self, "_last_total_portfolio_wealth", 0.0)))
        if not d_data:
            fire_holdings = getattr(self, "_last_combined_fire_holdings", self.holdings)
            d_data = calc_deep_risk_diagnostic(fire_holdings, cur_safe, tot_p, self.summary_currency)

        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_deep_risk_title"))
        dlg.geometry("860x720")
        dlg.minsize(760, 580)
        dlg.transient(self.root)

        # Scrollable container
        canvas = tk.Canvas(dlg, highlightthickness=0, bg=self.bg_main)
        scrollbar = ttk.Scrollbar(dlg, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, padding=14)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas_win = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _on_canvas_resize(event):
            canvas.itemconfig(canvas_win, width=event.width)

        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_wheel(e):
            try:
                if e.delta:
                    canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
                elif e.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif e.num == 5:
                    canvas.yview_scroll(1, "units")
            except Exception:
                pass

        dlg.bind("<MouseWheel>", _on_wheel)
        dlg.bind("<Button-4>", _on_wheel)
        dlg.bind("<Button-5>", _on_wheel)

        # Header Title
        tk.Label(
            scroll_frame,
            text=f"🛡️ {t('dlg_deep_risk_title')}",
            font=("Segoe UI", 13, "bold"),
            fg="#1a73e8",
        ).pack(anchor="w")

        tk.Label(
            scroll_frame,
            text=t("lbl_deep_risk_sub"),
            font=("Segoe UI", 9),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
        ).pack(anchor="w", pady=(1, 8))

        # Overall Resilience Card
        overall_score = d_data.get("overall_score", 50.0)
        grade = d_data.get("overall_grade", "C")
        grade_desc = d_data.get("grade_desc", "")
        grade_color = "#188038" if grade == "A" else ("#1a73e8" if grade == "B" else ("#e37400" if grade == "C" else "#d93025"))

        overall_card = tk.Frame(scroll_frame, bg="#f8f9fa" if not self.dark_mode else "#252830", bd=1, relief="solid", padx=12, pady=10)
        overall_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            overall_card,
            text=t("lbl_overall_resilience_card"),
            font=("Segoe UI", 9, "bold"),
            fg=self.text_dark,
            bg="#f8f9fa" if not self.dark_mode else "#252830",
        ).pack(anchor="w")

        tk.Label(
            overall_card,
            text=f"{t('lbl_deep_risk_composite', score=overall_score, grade=grade)} — {grade_desc}",
            font=("Segoe UI", 12, "bold"),
            fg=grade_color,
            bg="#f8f9fa" if not self.dark_mode else "#252830",
        ).pack(anchor="w", pady=(2, 4))

        tk.Label(
            overall_card,
            text=d_data.get("bernstein_thesis", ""),
            font=("Segoe UI", 8),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
            bg="#f8f9fa" if not self.dark_mode else "#252830",
            wraplength=760,
            justify=tk.LEFT,
        ).pack(anchor="w")

        # 4 Risk Cards Grid (2x2)
        grid_frame = tk.Frame(scroll_frame)
        grid_frame.pack(fill=tk.X, pady=(0, 10))
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        risks = [
            (
                t("lbl_risk_inflation_title"),
                d_data.get("inflation_score", 50.0),
                t("lbl_risk_inflation_desc"),
                0, 0,
            ),
            (
                t("lbl_risk_deflation_title"),
                d_data.get("deflation_score", 50.0),
                t("lbl_risk_deflation_desc"),
                0, 1,
            ),
            (
                t("lbl_risk_confiscation_title"),
                d_data.get("confiscation_score", 50.0),
                t("lbl_risk_confiscation_desc"),
                1, 0,
            ),
            (
                t("lbl_risk_devastation_title"),
                d_data.get("devastation_score", 50.0),
                t("lbl_risk_devastation_desc"),
                1, 1,
            ),
        ]

        for title, score, desc, r, c in risks:
            sc_color = "#188038" if score >= 80 else ("#1a73e8" if score >= 70 else ("#e37400" if score >= 50 else "#d93025"))
            c_frame = tk.Frame(grid_frame, bg=self.card_bg, bd=1, relief="solid", padx=10, pady=8)
            c_frame.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)

            tk.Label(c_frame, text=title, font=("Segoe UI", 9, "bold"), fg=self.text_dark, bg=self.card_bg).pack(anchor="w")
            tk.Label(c_frame, text=f"{score:.1f} / 100", font=("Segoe UI", 12, "bold"), fg=sc_color, bg=self.card_bg).pack(anchor="w", pady=(2, 2))

            # Progress indicator bar
            pbar = ttk.Progressbar(c_frame, orient="horizontal", length=180, mode="determinate")
            pbar["value"] = score
            pbar.pack(anchor="w", fill=tk.X, pady=(0, 4))

            tk.Label(c_frame, text=desc, font=("Segoe UI", 8), fg="#5f6368" if not self.dark_mode else "#9aa0a6", bg=self.card_bg, wraplength=350, justify=tk.LEFT).pack(anchor="w")

        # Strengths & Weaknesses
        diag_box = tk.Frame(scroll_frame, bg="#ffffff" if not self.dark_mode else "#2d3342", bd=1, relief="solid", padx=10, pady=8)
        diag_box.pack(fill=tk.X, pady=(0, 10))

        tk.Label(diag_box, text=t("lbl_deep_risk_strengths"), font=("Segoe UI", 9, "bold"), fg="#188038", bg="#ffffff" if not self.dark_mode else "#2d3342").pack(anchor="w")
        for s in d_data.get("strengths", []):
            tk.Label(diag_box, text=f"  • {s}", font=("Segoe UI", 8), fg=self.text_dark, bg="#ffffff" if not self.dark_mode else "#2d3342").pack(anchor="w", pady=1)

        tk.Label(diag_box, text=t("lbl_deep_risk_weaknesses"), font=("Segoe UI", 9, "bold"), fg="#d93025", bg="#ffffff" if not self.dark_mode else "#2d3342").pack(anchor="w", pady=(6, 0))
        for w in d_data.get("weaknesses", []):
            tk.Label(diag_box, text=f"  • {w}", font=("Segoe UI", 8), fg=self.text_dark, bg="#ffffff" if not self.dark_mode else "#2d3342").pack(anchor="w", pady=1)

        # Prescription Actions
        if d_data.get("recommendations"):
            act_box = tk.Frame(scroll_frame, bg="#fef7e0" if not self.dark_mode else "#332d20", bd=1, relief="solid", padx=10, pady=8)
            act_box.pack(fill=tk.X, pady=(0, 10))
            tk.Label(act_box, text=t("lbl_deep_risk_actions"), font=("Segoe UI", 9, "bold"), fg="#b06000", bg="#fef7e0" if not self.dark_mode else "#332d20").pack(anchor="w")
            for rec in d_data.get("recommendations", []):
                tk.Label(act_box, text=f"  👉 [{rec.get('risk')}]: {rec.get('action')}", font=("Segoe UI", 8, "bold"), fg=self.text_dark, bg="#fef7e0" if not self.dark_mode else "#332d20", wraplength=760, justify=tk.LEFT).pack(anchor="w", pady=2)

        # Bottom Close button
        tk.Button(
            scroll_frame,
            text=t("btn_close") if "btn_close" in TRANSLATIONS.get(get_current_language(), {}) else "Close",
            font=("Segoe UI", 9),
            command=dlg.destroy,
            padx=12,
            pady=4,
        ).pack(anchor="e")

    def _show_crisis_stress_test_dialog(self):
        """Displays historical 10-year bear market sequence-of-returns stress test modal."""
        if not hasattr(self, "_last_fire_res"):
            self._refresh_fire_tab()
        res = getattr(self, "_last_fire_res", {})
        tot_p = float(res.get("current_portfolio_val", getattr(self, "_last_total_portfolio_wealth", 0.0)))
        rle_ann = float(res.get("rle_annual", 0.0))
        cur_safe = float(res.get("current_safe_assets", 0.0))
        s_yrs = float(res.get("target_safe_years", 25.0))
        c_data = res.get("crisis_stress_test_data")
        if not c_data or tot_p != c_data.get("portfolio_initial", 0.0):
            c_data = calc_historical_crisis_stress_test(tot_p, rle_ann, cur_safe, s_yrs)

        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_crisis_stress_test_title"))
        dlg.geometry("900x700")
        dlg.minsize(820, 600)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Header Title
        tk.Label(
            frame,
            text=f"📉 {t('dlg_crisis_stress_test_title')}",
            font=("Segoe UI", 12, "bold"),
            fg="#c5221f",
        ).pack(anchor="w")

        tk.Label(
            frame,
            text=t("lbl_crisis_stress_sub"),
            font=("Segoe UI", 9),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
        ).pack(anchor="w", pady=(1, 6))

        # Overall Preservation Comparison Banner
        avg_diff = c_data.get("avg_capital_preserved", 0.0)
        safe_used = c_data.get("safe_buffer_used", 0.0)
        res_by_crisis = c_data.get("results_by_crisis", {})

        banner = tk.Frame(frame, bg="#e6f4ea" if not self.dark_mode else "#1e3324", bd=1, relief="solid", padx=10, pady=8)
        banner.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            banner,
            text=t("lbl_crisis_comp_banner", diff=avg_diff, ratio="1.5~3.8"),
            font=("Segoe UI", 10, "bold"),
            fg="#137333",
            bg="#e6f4ea" if not self.dark_mode else "#1e3324",
        ).pack(anchor="w")

        tk.Label(
            banner,
            text=f"Initial Wealth: ${c_data.get('portfolio_initial', 0):,.0f}  |  Safe Buffer Allocated: ${safe_used:,.0f}  |  Annual Living Draw (RLE): ${c_data.get('rle_annual', 0):,.0f}",
            font=("Segoe UI", 8),
            fg=self.text_dark,
            bg="#e6f4ea" if not self.dark_mode else "#1e3324",
        ).pack(anchor="w", pady=(2, 0))

        # Notebook with 4 crisis tabs
        nb = ttk.Notebook(frame)
        nb.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        tab_keys = [
            ("1929", t("tab_crisis_1929")),
            ("1973", t("tab_crisis_1973")),
            ("2000", t("tab_crisis_2000")),
            ("2008", t("tab_crisis_2008")),
        ]

        for c_key, tab_title in tab_keys:
            c_info = res_by_crisis.get(c_key, {})
            tab_f = ttk.Frame(nb, padding=8)
            nb.add(tab_f, text=tab_title)

            # Sub-summary row
            sub_summary = tk.Frame(tab_f, bg=self.card_bg, bd=1, relief="solid", padx=8, pady=6)
            sub_summary.pack(fill=tk.X, pady=(0, 6))

            t_unh = c_info.get("terminal_unhedged", 0.0)
            t_hed = c_info.get("terminal_hedged", 0.0)
            diff = c_info.get("capital_preserved", 0.0)
            ruin_txt = "⚠️ Severe Impairment" if c_info.get("ruin_in_unhedged") else "Depleted"

            tk.Label(
                sub_summary,
                text=f"{c_info.get('name', '')} — {c_info.get('desc', '')}",
                font=("Segoe UI", 8, "bold"),
                fg=self.primary_color,
                bg=self.card_bg,
            ).pack(anchor="w")

            metrics_txt = (
                f"Year 10 Unhedged: ${t_unh:,.0f} ({ruin_txt})  vs.  "
                f"Year 10 Bernstein Dual-Engine: ${t_hed:,.0f}  |  "
                f"Capital Preserved: +${diff:,.0f} ({c_info.get('wealth_preservation_pct', 0)}% of Initial)"
            )
            tk.Label(
                sub_summary,
                text=metrics_txt,
                font=("Segoe UI", 9, "bold"),
                fg="#188038",
                bg=self.card_bg,
            ).pack(anchor="w", pady=(2, 0))

            # Table showing Year 1 to 10 trajectory
            tree_f = tk.Frame(tab_f)
            tree_f.pack(fill=tk.BOTH, expand=True)

            tree_sc = ttk.Scrollbar(tree_f, orient="vertical")
            c_tree = ttk.Treeview(
                tree_f,
                columns=("year", "draw", "return", "unhedged", "safe_drawn", "safe_rem", "hedged"),
                show="headings",
                height=10,
                yscrollcommand=tree_sc.set,
            )
            tree_sc.config(command=c_tree.yview)

            c_tree.heading("year", text=t("col_crisis_year"))
            c_tree.heading("draw", text=t("col_crisis_withdrawal"))
            c_tree.heading("return", text=t("col_crisis_stock_return"))
            c_tree.heading("unhedged", text=t("col_crisis_unhedged_wealth"))
            c_tree.heading("safe_drawn", text=t("col_crisis_safe_drawn"))
            c_tree.heading("safe_rem", text=t("col_crisis_safe_remain"))
            c_tree.heading("hedged", text=t("col_crisis_hedged_wealth"))

            c_tree.column("year", width=55, anchor="center")
            c_tree.column("draw", width=100, anchor="e")
            c_tree.column("return", width=90, anchor="center")
            c_tree.column("unhedged", width=140, anchor="e")
            c_tree.column("safe_drawn", width=100, anchor="e")
            c_tree.column("safe_rem", width=110, anchor="e")
            c_tree.column("hedged", width=150, anchor="e")

            c_tree.tag_configure("crash_down", foreground="#d93025")
            c_tree.tag_configure("rebound_up", foreground="#188038")

            unh_hist = c_info.get("unhedged_history", [])
            hed_hist = c_info.get("hedged_history", [])

            for y_i in range(min(len(unh_hist), len(hed_hist))):
                u_row = unh_hist[y_i]
                h_row = hed_hist[y_i]
                ret_val = u_row.get("stock_return_pct", 0.0)
                tag = "crash_down" if ret_val < 0 else "rebound_up"

                c_tree.insert(
                    "",
                    tk.END,
                    values=(
                        f"Yr {u_row.get('year', y_i+1)}",
                        f"${u_row.get('withdrawal', 0):,.0f}",
                        f"{ret_val:+.1f}%",
                        f"${u_row.get('ending_wealth', 0):,.0f}",
                        f"${h_row.get('safe_drawn', 0):,.0f}",
                        f"${h_row.get('safe_remaining', 0):,.0f}",
                        f"${h_row.get('ending_wealth', 0):,.0f}",
                    ),
                    tags=(tag,),
                )

            c_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tree_sc.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom thesis banner & Close button
        bottom_f = tk.Frame(frame)
        bottom_f.pack(fill=tk.X)

        tk.Label(
            bottom_f,
            text=t("lbl_crisis_thesis_banner"),
            font=("Segoe UI", 8, "italic"),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
            wraplength=740,
            justify=tk.LEFT,
        ).pack(side=tk.LEFT)

        tk.Button(
            bottom_f,
            text=t("btn_close") if "btn_close" in TRANSLATIONS.get(get_current_language(), {}) else "Close",
            font=("Segoe UI", 9),
            command=dlg.destroy,
            padx=12,
            pady=4,
        ).pack(side=tk.RIGHT)

    def _show_fee_tax_drag_dialog(self):
        """Displays 30-year fee & cross-border tax drag autopsy modal with interactive jurisdiction / account selectors."""
        if not hasattr(self, "_last_fire_res"):
            self._refresh_fire_tab()
        res = getattr(self, "_last_fire_res", {})

        tot_p = float(res.get("current_portfolio_val", getattr(self, "_last_total_portfolio_wealth", 0.0)))
        if tot_p <= 0.0:
            for h in self.holdings:
                c = (h.get("currency") or "USD").strip().upper()
                mv = float(h.get("shares", 0.0)) * float(h.get("current_price", h.get("price", 0.0)))
                tot_p += self.converter.convert(mv, c, self.summary_currency)

        cur_div = float(res.get("current_annual_dividend", getattr(self, "_last_annual_dividend", 0.0)))
        if cur_div <= 0.0 and tot_p > 0:
            for h in self.holdings:
                c = (h.get("currency") or "USD").strip().upper()
                ad = float(h.get("annual_dividend", 0.0))
                cur_div += self.converter.convert(ad, c, self.summary_currency)

        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_fee_tax_title"))
        dlg.geometry("900x730")
        dlg.minsize(800, 580)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Header Title
        tk.Label(
            frame,
            text=f"💸 {t('dlg_fee_tax_title')}",
            font=("Segoe UI", 12, "bold"),
            fg="#b06000",
        ).pack(anchor="w")

        tk.Label(
            frame,
            text=t("lbl_fee_tax_sub"),
            font=("Segoe UI", 9),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
        ).pack(anchor="w", pady=(1, 6))

        # Controls Bar: Region & Account Type
        ctrl_bar = tk.Frame(frame, bg=self.card_bg, bd=1, relief="solid", padx=10, pady=8)
        ctrl_bar.pack(fill=tk.X, pady=(0, 8))

        tk.Label(ctrl_bar, text=t("lbl_tax_region_select"), font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.text_dark).grid(row=0, column=0, sticky="w", padx=(0, 6))

        region_map = {
            "Canada (15% US Div WHT, 50% CGT)": "Canada",
            "Non-Treaty / Int'l (Taiwan/HK/SG - 30% WHT, 0% CGT)": "Non-Treaty",
            "US Resident (0% Div WHT, 15% CGT)": "US",
            "Custom / Other (15% WHT, 10% CGT)": "Custom",
        }
        region_combo = ttk.Combobox(ctrl_bar, values=list(region_map.keys()), state="readonly", width=40)
        region_combo.current(0)
        region_combo.grid(row=0, column=1, sticky="w", padx=(0, 12))

        tk.Label(ctrl_bar, text=t("lbl_tax_acct_select"), font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.text_dark).grid(row=0, column=2, sticky="w", padx=(0, 6))

        acct_map = {
            "Taxable / Non-Registered": "Taxable",
            "TFSA (Tax-Free Savings - 0% CGT, 15% WHT)": "TFSA",
            "RRSP / RRIF (0% US WHT Article XXI, 0% CGT)": "RRSP",
            "Roth IRA / 401(k) (0% WHT, 0% CGT)": "Roth IRA",
        }
        acct_combo = ttk.Combobox(ctrl_bar, values=list(acct_map.keys()), state="readonly", width=36)
        acct_combo.current(0)
        acct_combo.grid(row=0, column=3, sticky="w", padx=(0, 6))

        # Summary Card
        sum_card = tk.Frame(frame, bg="#fce8e6" if not self.dark_mode else "#3c2020", bd=1, relief="solid", padx=12, pady=10)
        sum_card.pack(fill=tk.X, pady=(0, 8))

        lbl_sum_headline = tk.Label(sum_card, text="", font=("Segoe UI", 11, "bold"), fg="#c5221f", bg=sum_card["bg"])
        lbl_sum_headline.pack(anchor="w")

        lbl_sum_breakdown = tk.Label(sum_card, text="", font=("Segoe UI", 9), fg=self.text_dark, bg=sum_card["bg"])
        lbl_sum_breakdown.pack(anchor="w", pady=(3, 0))

        lbl_sum_params = tk.Label(sum_card, text="", font=("Segoe UI", 8, "italic"), fg="#5f6368" if not self.dark_mode else "#9aa0a6", bg=sum_card["bg"])
        lbl_sum_params.pack(anchor="w", pady=(2, 0))

        # Notebook: Trajectory vs Advice
        nb = ttk.Notebook(frame)
        nb.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        # Tab A: Trajectory Visual Chart & Data Table
        tab_proj = ttk.Frame(nb, padding=6)
        nb.add(tab_proj, text=f"📈 {t('tab_fee_tax_projection')}")

        # Visual Trajectory Chart Canvas
        chart_f = tk.Frame(tab_proj, bg=ChartTheme.DARK["bg"] if self.dark_mode else ChartTheme.LIGHT["bg"], bd=1, relief="solid")
        chart_f.pack(fill=tk.X, pady=(0, 6))

        traj_canvas = tk.Canvas(
            chart_f,
            height=210,
            bg=ChartTheme.DARK["bg"] if self.dark_mode else ChartTheme.LIGHT["bg"],
            highlightthickness=0,
        )
        traj_canvas.pack(fill=tk.BOTH, expand=True)

        tree_f = ttk.Frame(tab_proj)
        tree_f.pack(fill=tk.BOTH, expand=True)

        sc = ttk.Scrollbar(tree_f, orient="vertical")
        tree = ttk.Treeview(
            tree_f,
            columns=("year", "gross", "benchmark", "portfolio", "total_drag", "drag_pct"),
            show="headings",
            height=8,
            yscrollcommand=sc.set,
        )
        sc.config(command=tree.yview)

        tree.heading("year", text=t("col_traj_year"))
        tree.heading("gross", text=t("col_traj_gross"))
        tree.heading("benchmark", text=t("col_traj_benchmark"))
        tree.heading("portfolio", text=t("col_traj_portfolio"))
        tree.heading("total_drag", text=t("col_traj_total_drag"))
        tree.heading("drag_pct", text=t("col_traj_drag_pct"))

        tree.column("year", width=65, anchor="center")
        tree.column("gross", width=150, anchor="e")
        tree.column("benchmark", width=155, anchor="e")
        tree.column("portfolio", width=155, anchor="e")
        tree.column("total_drag", width=140, anchor="e")
        tree.column("drag_pct", width=95, anchor="center")

        tree.tag_configure("highlight_30", font=("Segoe UI", 9, "bold"), foreground="#c5221f")

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)

        # Tab B: Asset Location Advice
        tab_adv = ttk.Frame(nb, padding=12)
        nb.add(tab_adv, text=f"💡 {t('tab_fee_tax_advice')}")

        adv_box = tk.LabelFrame(tab_adv, text=f" {t('lbl_tax_location_header')} ", font=("Segoe UI", 10, "bold"), bg=self.card_bg, padx=12, pady=10)
        adv_box.pack(fill=tk.BOTH, expand=True)

        tk.Label(adv_box, text=t("lbl_tax_location_p1"), font=("Segoe UI", 9), fg=self.text_dark, bg=self.card_bg, wraplength=760, justify=tk.LEFT).pack(anchor="w", pady=(0, 6))
        tk.Label(adv_box, text=t("lbl_tax_location_p2"), font=("Segoe UI", 9), fg=self.text_dark, bg=self.card_bg, wraplength=760, justify=tk.LEFT).pack(anchor="w", pady=(0, 6))
        tk.Label(adv_box, text=t("lbl_tax_location_p3"), font=("Segoe UI", 9), fg=self.text_dark, bg=self.card_bg, wraplength=760, justify=tk.LEFT).pack(anchor="w", pady=(0, 6))

        def _recalc():
            reg_key = region_combo.get()
            acct_key = acct_combo.get()
            sel_reg = region_map.get(reg_key, "Canada")
            sel_acct = acct_map.get(acct_key, "Taxable")

            fire_holdings = getattr(self, "_last_combined_fire_holdings", self.holdings)
            f_res = calc_fee_and_tax_drag_autopsy(
                holdings=fire_holdings,
                portfolio_val=tot_p,
                annual_dividend=cur_div,
                region=sel_reg,
                account_type=sel_acct,
                summary_currency=self.summary_currency,
            )

            loss_tot = f_res.get("thirty_year_total_loss", 0.0)
            loss_pct = f_res.get("thirty_year_loss_ratio_pct", 0.0)
            lbl_sum_headline.config(text=t("lbl_30yr_loss_headline", loss=loss_tot, pct=loss_pct))

            fee_l = f_res.get("thirty_year_fee_loss", 0.0)
            wht_l = f_res.get("thirty_year_wht_loss", 0.0)
            cgt_l = f_res.get("thirty_year_cgt_loss", 0.0)
            lbl_sum_breakdown.config(text=t("lbl_30yr_breakdown", fee=fee_l, wht=wht_l, cgt=cgt_l))

            w_ter = f_res.get("portfolio_weighted_ter_pct", 0.0)
            wht_r = f_res.get("us_dividend_wht_pct", 0.0)
            cgt_r = f_res.get("capital_gains_tax_pct", 0.0)
            lbl_sum_params.config(
                text=f"{t('lbl_fee_weighted_ter', rate=f'{w_ter:.2f}')}  |  {t('lbl_tax_param_wht', rate=f'{wht_r:.1f}')}  |  {t('lbl_tax_param_cgt', rate=f'{cgt_r:.1f}')}"
            )

            traj = f_res.get("trajectories", [])
            dlg._last_traj = traj
            draw_fee_tax_trajectory_chart(traj_canvas, traj, dark_mode=self.dark_mode)

            for item in tree.get_children():
                tree.delete(item)

            for row in traj:
                yr_val = row.get("year", 0)
                tag = "highlight_30" if yr_val == 30 else ""
                drag_val = row.get("total_drag", row.get("dollars_lost", 0.0))
                drag_pct = row.get("drag_pct", row.get("pct_wealth_lost", 0.0))
                tree.insert(
                    "",
                    tk.END,
                    values=(
                        f"Yr {yr_val}",
                        f"${row.get('gross_wealth', 0.0):,.0f}",
                        f"${row.get('benchmark_wealth', 0.0):,.0f}",
                        f"${row.get('portfolio_wealth', 0.0):,.0f}",
                        f"-${drag_val:,.0f}",
                        f"{drag_pct:.1f}%",
                    ),
                    tags=(tag,) if tag else (),
                )

        def _on_canvas_configure(e):
            traj = getattr(dlg, "_last_traj", None)
            if traj:
                draw_fee_tax_trajectory_chart(traj_canvas, traj, dark_mode=self.dark_mode)

        traj_canvas.bind("<Configure>", _on_canvas_configure)

        region_combo.bind("<<ComboboxSelected>>", lambda e: _recalc())
        acct_combo.bind("<<ComboboxSelected>>", lambda e: _recalc())

        _recalc()

        btn_box = tk.Frame(frame)
        btn_box.pack(fill=tk.X)
        tk.Button(btn_box, text=t("btn_close") if "btn_close" in TRANSLATIONS.get(get_current_language(), {}) else "Close", font=("Segoe UI", 9), padx=14, pady=4, command=dlg.destroy).pack(side=tk.RIGHT)

    def _show_rebalancing_5_25_dialog(self):
        """Displays William J. Bernstein 5/25 rebalancing tolerance bands modal."""
        if not hasattr(self, "_last_fire_res"):
            self._refresh_fire_tab()
        res = getattr(self, "_last_fire_res", {})

        reb_data = res.get("rebalance_5_25_data")
        tot_p = float(res.get("current_portfolio_val", getattr(self, "_last_total_portfolio_wealth", 0.0)))
        if not reb_data:
            fire_holdings = getattr(self, "_last_combined_fire_holdings", self.holdings)
            reb_data = calc_rebalancing_5_25_bands(fire_holdings, target_weights=None, total_portfolio_val=tot_p)

        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_rebalance_5_25_title"))
        dlg.geometry("900x680")
        dlg.minsize(800, 520)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text=f"⚖️ {t('dlg_rebalance_5_25_title')}",
            font=("Segoe UI", 12, "bold"),
            fg="#137333",
        ).pack(anchor="w")

        tk.Label(
            frame,
            text=t("lbl_rebalance_5_25_sub"),
            font=("Segoe UI", 9),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
        ).pack(anchor="w", pady=(1, 6))

        bonus_val = reb_data.get("estimated_annual_rebalance_bonus", 0.0)
        bonus_pct = reb_data.get("rebalancing_bonus_pct", 0.50)
        trig_count = reb_data.get("triggered_count", 0)
        tot_count = reb_data.get("total_assets", 0)

        banner = tk.Frame(frame, bg="#e6f4ea" if not self.dark_mode else "#1e3324", bd=1, relief="solid", padx=10, pady=8)
        banner.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            banner,
            text=t("lbl_reb_bonus_card"),
            font=("Segoe UI", 9, "bold"),
            fg="#137333",
            bg=banner["bg"],
        ).pack(anchor="w")

        tk.Label(
            banner,
            text=f"{t('lbl_reb_bonus_val', bonus=bonus_val, pct=bonus_pct)}  |  {t('lbl_reb_status_summary', triggered_count=trig_count, total_count=tot_count)}",
            font=("Segoe UI", 10, "bold"),
            fg="#188038",
            bg=banner["bg"],
        ).pack(anchor="w", pady=(2, 0))

        tree_f = ttk.Frame(frame)
        tree_f.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        sc = ttk.Scrollbar(tree_f, orient="vertical")
        tree = ttk.Treeview(
            tree_f,
            columns=("symbol", "actual", "target", "abs_drift", "rel_drift", "status", "action", "amount"),
            show="headings",
            height=10,
            yscrollcommand=sc.set,
        )
        sc.config(command=tree.yview)

        tree.heading("symbol", text=t("col_reb_symbol"))
        tree.heading("actual", text=t("col_reb_current_pct"))
        tree.heading("target", text=t("col_reb_target_pct"))
        tree.heading("abs_drift", text=t("col_reb_abs_drift"))
        tree.heading("rel_drift", text=t("col_reb_rel_drift"))
        tree.heading("status", text=t("col_reb_status"))
        tree.heading("action", text=t("col_reb_action"))
        tree.heading("amount", text=t("col_reb_amount"))

        tree.column("symbol", width=120, anchor="w")
        tree.column("actual", width=85, anchor="center")
        tree.column("target", width=85, anchor="center")
        tree.column("abs_drift", width=85, anchor="center")
        tree.column("rel_drift", width=85, anchor="center")
        tree.column("status", width=140, anchor="center")
        tree.column("action", width=130, anchor="center")
        tree.column("amount", width=110, anchor="e")

        tree.tag_configure("triggered", font=("Segoe UI", 9, "bold"), foreground="#c5221f")
        tree.tag_configure("approaching", font=("Segoe UI", 9), foreground="#b06000")
        tree.tag_configure("in_band", font=("Segoe UI", 9), foreground="#188038")

        for item in reb_data.get("asset_drifts", []):
            st = item["status"]
            if st == "triggered":
                st_label = t("status_triggered")
                tag = "triggered"
            elif st == "approaching":
                st_label = t("status_approaching")
                tag = "approaching"
            else:
                st_label = t("status_in_band")
                tag = "in_band"

            act = item["action"]
            if act == "trim":
                act_label = t("act_trim")
            elif act == "add":
                act_label = t("act_add")
            else:
                act_label = t("act_hold")

            tree.insert(
                "",
                tk.END,
                values=(
                    item["symbol"],
                    f"{item['actual_pct']:.1f}%",
                    f"{item['target_pct']:.1f}%",
                    f"{item['abs_drift_pct']:+.1f}%",
                    f"{item['rel_drift_pct']:+.1f}%",
                    st_label,
                    act_label,
                    f"${item['rebalance_amount_dollars']:,.0f}",
                ),
                tags=(tag,),
            )

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)

        bottom_f = tk.Frame(frame)
        bottom_f.pack(fill=tk.X)

        tk.Label(
            bottom_f,
            text=t("lbl_reb_bernstein_law"),
            font=("Segoe UI", 8, "italic"),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
            wraplength=740,
            justify=tk.LEFT,
        ).pack(side=tk.LEFT)

        tk.Button(
            bottom_f,
            text=t("btn_close") if "btn_close" in TRANSLATIONS.get(get_current_language(), {}) else "Close",
            font=("Segoe UI", 9),
            command=dlg.destroy,
            padx=12,
            pady=4,
        ).pack(side=tk.RIGHT)

    def _show_simplicity_index_dialog(self):
        """Displays cognitive decline protection & portfolio simplicity index modal."""
        if not hasattr(self, "_last_fire_res"):
            self._refresh_fire_tab()
        res = getattr(self, "_last_fire_res", {})

        try:
            cur_age = int(self.fire_age_spin.get().strip())
        except Exception:
            cur_age = int(res.get("current_age", getattr(self, "_last_current_age", 45)))

        tot_p = float(res.get("current_portfolio_val", getattr(self, "_last_total_portfolio_wealth", 0.0)))
        fire_holdings = getattr(self, "_last_combined_fire_holdings", self.holdings)
        simp_data = calc_simplicity_index(fire_holdings, current_age=cur_age, total_portfolio_val=tot_p)

        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_simplicity_title"))
        dlg.geometry("860x700")
        dlg.minsize(760, 540)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text=f"🧠 {t('dlg_simplicity_title')}",
            font=("Segoe UI", 12, "bold"),
            fg="#681da8",
        ).pack(anchor="w")

        tk.Label(
            frame,
            text=t("lbl_simplicity_sub"),
            font=("Segoe UI", 9),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
        ).pack(anchor="w", pady=(1, 6))

        score = simp_data.get("simplicity_score", 0)
        rating = simp_data.get("rating", "B")
        rating_desc = simp_data.get("rating_desc", "")

        score_bg = "#e6f4ea" if score >= 80 else ("#fef7e0" if score >= 60 else "#fce8e6")
        score_fg = "#137333" if score >= 80 else ("#b06000" if score >= 60 else "#c5221f")
        if self.dark_mode:
            score_bg = "#1e3324" if score >= 80 else ("#382d14" if score >= 60 else "#3c2020")

        score_card = tk.Frame(frame, bg=score_bg, bd=1, relief="solid", padx=12, pady=10)
        score_card.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            score_card,
            text=t("lbl_simplicity_score_card"),
            font=("Segoe UI", 9, "bold"),
            fg=score_fg,
            bg=score_bg,
        ).pack(anchor="w")

        tk.Label(
            score_card,
            text=f"{t('lbl_simplicity_score_val', score=score, rating=f'{rating} ({rating_desc})')}",
            font=("Segoe UI", 11, "bold"),
            fg=score_fg,
            bg=score_bg,
        ).pack(anchor="w", pady=(2, 0))

        tk.Label(
            score_card,
            text=t(
                "lbl_simplicity_details",
                count=simp_data.get("holding_count", 0),
                index_pct=simp_data.get("indexing_ratio_pct", 0.0),
                curr_count=simp_data.get("currency_count", 0),
            ),
            font=("Segoe UI", 9),
            fg=self.text_dark,
            bg=score_bg,
        ).pack(anchor="w", pady=(3, 0))

        has_alert = simp_data.get("cognitive_alert", False)
        warn_bg = "#fce8e6" if has_alert else ("#e8f0fe" if not self.dark_mode else "#1c2b42")
        warn_fg = "#c5221f" if has_alert else "#1a73e8"
        if self.dark_mode and has_alert:
            warn_bg = "#3c2020"

        warn_card = tk.Frame(frame, bg=warn_bg, bd=1, relief="solid", padx=12, pady=10)
        warn_card.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            warn_card,
            text=t("lbl_cognitive_warning_title", age=cur_age) if has_alert else f"ℹ️ 認知年齡規劃狀態 (當前年齡: {cur_age} 歲):",
            font=("Segoe UI", 9, "bold"),
            fg=warn_fg,
            bg=warn_bg,
        ).pack(anchor="w")

        tk.Label(
            warn_card,
            text=t("lbl_cognitive_warning_body"),
            font=("Segoe UI", 9),
            fg=self.text_dark,
            bg=warn_card["bg"],
            wraplength=760,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(2, 0))

        presc_frame = tk.LabelFrame(frame, text=f" {t('lbl_simplicity_rec_title')} ", font=("Segoe UI", 10, "bold"), bg=self.card_bg, padx=10, pady=8)
        presc_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        for rec in simp_data.get("recommendations", []):
            tk.Label(
                presc_frame,
                text=f"👉 {rec}",
                font=("Segoe UI", 9),
                fg=self.text_dark,
                bg=self.card_bg,
                wraplength=760,
                justify=tk.LEFT,
            ).pack(anchor="w", pady=(2, 2))

        btn_preset_bar = tk.Frame(presc_frame, bg=self.card_bg, pady=6)
        btn_preset_bar.pack(anchor="w")

        tk.Button(
            btn_preset_bar,
            text=t("btn_preset_2fund"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#1a73e8",
            relief="solid",
            bd=1,
            padx=10,
            pady=4,
            command=lambda: self._show_preset_blueprint_dialog("2fund"),
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            btn_preset_bar,
            text=t("btn_preset_3fund"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#137333",
            relief="solid",
            bd=1,
            padx=10,
            pady=4,
            command=lambda: self._show_preset_blueprint_dialog("3fund"),
        ).pack(side=tk.LEFT)

        btn_box = tk.Frame(frame)
        btn_box.pack(fill=tk.X)
        tk.Button(btn_box, text=t("btn_close") if "btn_close" in TRANSLATIONS.get(get_current_language(), {}) else "Close", font=("Segoe UI", 9), padx=14, pady=4, command=dlg.destroy).pack(side=tk.RIGHT)

    def _show_preset_blueprint_dialog(self, preset_type: str):
        """Displays 2-Fund or 3-Fund Bogleheads / Bernstein blueprint."""
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_preset_title"))
        dlg.geometry("560x360")
        dlg.minsize(480, 300)
        dlg.transient(self.root)

        f = ttk.Frame(dlg, padding=14)
        f.pack(fill=tk.BOTH, expand=True)

        tk.Label(f, text=t("dlg_preset_title"), font=("Segoe UI", 11, "bold"), fg="#1a73e8").pack(anchor="w")
        tk.Label(f, text=t("dlg_preset_desc"), font=("Segoe UI", 9), fg="#5f6368" if not self.dark_mode else "#9aa0a6").pack(anchor="w", pady=(1, 8))

        box = tk.Frame(f, bg=self.card_bg, bd=1, relief="solid", padx=12, pady=10)
        box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        if preset_type == "2fund":
            lines = [
                "🏛️ 經典兩基金極簡模型 (Classic 60/40 Simplicity):",
                "• 60% 全球股票指數 ETF (例如: VT 或 VOO + VXUS / 加拿大: XEQT)",
                "• 40% 綜合高品質債券指數 ETF (例如: BND / 加拿大: ZAG)",
                "",
                "優點: 每年僅需 15 分鐘再平衡，無繁瑣選股，認知負擔趨近於零。"
            ]
        else:
            lines = [
                "🏛️ Bogleheads / 伯恩斯坦三基金全球模型 (Global 3-Fund):",
                "• 50% 本國 / 美國全市場指數 ETF (例如: VTI / VOO)",
                "• 20% 國際成熟 + 新興市場指數 ETF (例如: VXUS)",
                "• 30% 綜合高品質安全債券 / TIPS (例如: BND / TIP)",
                "",
                "優點: 全球多元分散，抗通膨與防通縮兼顧，極致低費率 (TER < 0.08%)。"
            ]

        for ln in lines:
            tk.Label(box, text=ln, font=("Segoe UI", 9), fg=self.text_dark, bg=self.card_bg, wraplength=480, justify=tk.LEFT).pack(anchor="w", pady=1)

        tk.Button(f, text=t("btn_close") if "btn_close" in TRANSLATIONS.get(get_current_language(), {}) else "Close", font=("Segoe UI", 9), command=dlg.destroy, padx=12, pady=3).pack(side=tk.RIGHT)

    # -------------------------------------------------------------
    # Tab 3: Stock Division (Split) Calculator
    # -------------------------------------------------------------
    def _build_split_tab(self):
        tab = self.tab_split
        container = ttk.Frame(tab, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        left_card = tk.LabelFrame(container, text=f" {t('split_param_box')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=10)
        left_card.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        self.split_param_box = left_card

        self.lbl_split_holding = tk.Label(left_card, text=t("lbl_split_holding"), font=("Segoe UI", 9, "bold"), bg="#ffffff")
        self.lbl_split_holding.pack(anchor="w", pady=(0, 2))
        self.split_holding_var = tk.StringVar()
        self.split_holding_cb = ttk.Combobox(left_card, textvariable=self.split_holding_var, state="readonly", width=22)
        self.split_holding_cb.pack(fill=tk.X, pady=(0, 6))
        self.split_holding_cb.bind("<<ComboboxSelected>>", self._on_split_holding_selected)

        self.lbl_split_sym = tk.Label(left_card, text=t("col_symbol") + ":", font=("Segoe UI", 8, "bold"), bg="#ffffff")
        self.lbl_split_sym.pack(anchor="w")
        self.split_sym_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_sym_entry.pack(fill=tk.X, pady=(0, 4))

        self.lbl_split_shares = tk.Label(left_card, text=t("col_shares") + ":", font=("Segoe UI", 8, "bold"), bg="#ffffff")
        self.lbl_split_shares.pack(anchor="w")
        self.split_shares_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_shares_entry.pack(fill=tk.X, pady=(0, 4))

        self.lbl_split_before_price = tk.Label(left_card, text=t("lbl_split_before_price"), font=("Segoe UI", 8, "bold"), bg="#ffffff")
        self.lbl_split_before_price.pack(anchor="w")
        self.split_price_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_price_entry.pack(fill=tk.X, pady=(0, 4))

        self.lbl_split_cur_price = tk.Label(left_card, text=t("lbl_split_current_price"), font=("Segoe UI", 8, "bold"), bg="#ffffff")
        self.lbl_split_cur_price.pack(anchor="w")
        self.split_cur_price_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_cur_price_entry.pack(fill=tk.X, pady=(0, 4))

        self.lbl_split_purchase_date = tk.Label(left_card, text=t("lbl_purchase_date"), font=("Segoe UI", 8), bg="#ffffff")
        self.lbl_split_purchase_date.pack(anchor="w")
        self.split_purchase_date_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        from datetime import date, timedelta
        self.split_purchase_date_entry.insert(0, (date.today() - timedelta(days=365)).strftime("%Y-%m-%d"))
        self.split_purchase_date_entry.pack(fill=tk.X, pady=(0, 2))

        split_date_btn_row = ttk.Frame(left_card)
        split_date_btn_row.pack(fill=tk.X, pady=(0, 2))
        for p_lbl, p_days in [("Today", 0), ("6M", 182), ("1Y", 365), ("2Y", 730)]:
            b = tk.Button(
                split_date_btn_row,
                text=p_lbl,
                font=("Segoe UI", 7),
                bg="#f1f3f4",
                relief="solid",
                bd=1,
                padx=2,
                pady=1,
                command=lambda d=p_days: self._set_split_purchase_date_days_ago(d),
            )
            b.pack(side=tk.LEFT, padx=1, expand=True, fill=tk.X)
        self.split_holding_days_lbl = tk.Label(left_card, text=t("lbl_holding_days_fmt", days=365, years=1.0), font=("Segoe UI", 8, "italic"), bg="#ffffff", fg=self.text_muted)
        self.split_holding_days_lbl.pack(anchor="w", pady=(0, 4))

        self.lbl_split_target_price = tk.Label(left_card, text=t("lbl_split_target_price"), font=("Segoe UI", 8, "bold"), bg="#ffffff")
        self.lbl_split_target_price.pack(anchor="w")
        self.split_target_price_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_target_price_entry.pack(fill=tk.X, pady=(0, 2))

        split_target_presets_row = ttk.Frame(left_card)
        split_target_presets_row.pack(fill=tk.X, pady=(0, 4))
        for p_lbl, p_mult in [("+10%", 1.10), ("+25%", 1.25), ("+50%", 1.50), ("+100%", 2.0)]:
            b = tk.Button(
                split_target_presets_row,
                text=p_lbl,
                font=("Segoe UI", 7),
                bg="#f1f3f4",
                relief="solid",
                bd=1,
                padx=2,
                pady=1,
                command=lambda m=p_mult: self._apply_split_target_multiplier(m),
            )
            b.pack(side=tk.LEFT, padx=1, expand=True, fill=tk.X)
        self.btn_split_recov = tk.Button(
            left_card,
            text="🎯 " + t("lbl_split_presplit_recovery"),
            font=("Segoe UI", 8),
            bg="#f1f3f4",
            relief="solid",
            bd=1,
            padx=3,
            pady=1,
            command=self._apply_split_target_presplit,
        )
        self.btn_split_recov.pack(fill=tk.X, pady=(0, 6))

        self.lbl_split_ratio = tk.Label(left_card, text=t("lbl_split_ratio"), font=("Segoe UI", 8, "bold"), bg="#ffffff")
        self.lbl_split_ratio.pack(anchor="w")
        self.split_preset_var = tk.StringVar(value="2:1")
        presets = ["2:1 Split", "3:1 Split", "4:1 Split", "5:1 Split", "10:1 Split", "1:5 Reverse Split", "1:10 Reverse Split", "Custom"]
        preset_cb = ttk.Combobox(left_card, textvariable=self.split_preset_var, values=presets, state="readonly")
        preset_cb.pack(fill=tk.X, pady=(0, 4))
        preset_cb.bind("<<ComboboxSelected>>", self._on_split_preset_selected)

        ratio_frame = ttk.Frame(left_card)
        ratio_frame.pack(fill=tk.X, pady=(0, 8))
        self.lbl_ratio_to = tk.Label(ratio_frame, text=t("lbl_ratio_to"), font=("Segoe UI", 8), bg=self.bg_main)
        self.lbl_ratio_to.pack(side=tk.LEFT)
        self.split_to_entry = tk.Entry(ratio_frame, width=5, bd=1, relief="solid")
        self.split_to_entry.insert(0, "2")
        self.split_to_entry.pack(side=tk.LEFT, padx=3)

        self.lbl_ratio_from = tk.Label(ratio_frame, text=t("lbl_ratio_for_every"), font=("Segoe UI", 8), bg=self.bg_main)
        self.lbl_ratio_from.pack(side=tk.LEFT, padx=3)
        self.split_from_entry = tk.Entry(ratio_frame, width=5, bd=1, relief="solid")
        self.split_from_entry.insert(0, "1")
        self.split_from_entry.pack(side=tk.LEFT, padx=3)

        self.btn_calc_split = tk.Button(
            left_card,
            text=t("btn_calc_split"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=4,
            command=self._calc_split_results,
        )
        self.btn_calc_split.pack(fill=tk.X, pady=(0, 6))

        self.btn_apply_split = tk.Button(
            left_card,
            text="✅ " + t("btn_apply_split"),
            font=("Segoe UI", 9, "bold"),
            bg="#0f9d58",
            fg="#ffffff",
            relief="flat",
            pady=5,
            command=self._apply_split_to_portfolio,
        )
        self.btn_apply_split.pack(fill=tk.X)

        right_card = ttk.Frame(container)
        right_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 1. Earned Already Card
        self.split_earned_box = tk.LabelFrame(right_card, text=f" {t('split_sec_earned_already')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=8)
        self.split_earned_box.pack(fill=tk.X, pady=(0, 8))

        self.split_earned_labels = {}
        self.split_earned_title_labels = {}
        split_earned_fields = [
            ("cost_basis", t("lbl_cost_basis_invested")),
            ("market_value", t("card_total_value")),
            ("capital_gain", t("lbl_capital_gain_so_far")),
            ("holding_period", t("lbl_holding_period")),
        ]
        for i, (k, lbl) in enumerate(split_earned_fields):
            r = i // 2
            c = (i % 2) * 2
            t_lbl = tk.Label(self.split_earned_box, text=lbl, font=("Segoe UI", 8, "bold"), bg="#ffffff", fg=self.text_muted)
            t_lbl.grid(row=r * 2, column=c, sticky="w", padx=8)
            self.split_earned_title_labels[k] = t_lbl
            v = tk.Label(self.split_earned_box, text="-", font=("Segoe UI", 10, "bold"), bg="#ffffff", fg=self.text_dark)
            v.grid(row=r * 2 + 1, column=c, sticky="w", padx=8, pady=(0, 4))
            self.split_earned_labels[k] = v

        # 2. Before / After Split Comparison Card
        self.split_comp_box = tk.LabelFrame(right_card, text=f" {t('split_sec_comparison')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=8)
        self.split_comp_box.pack(fill=tk.X, pady=(0, 8))

        comp_frame = ttk.Frame(self.split_comp_box)
        comp_frame.pack(fill=tk.X)

        before_box = tk.LabelFrame(comp_frame, text=f" {t('split_sec_before')} ", font=("Segoe UI", 9, "bold"), bg="#f8f9fa", padx=10, pady=8)
        before_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        self.split_before_box = before_box

        self.split_before_labels = {}
        self.split_before_title_labels = {}
        for k, lbl in [("shares", t("col_shares") + ":"), ("price", t("lbl_split_cost_basis_per_share")), ("cur_price", t("lbl_split_cur_price_per_share")), ("total", t("lbl_split_total_cost_basis")), ("val", t("card_total_value") + ":")]:
            t_lbl = tk.Label(before_box, text=lbl, font=("Segoe UI", 8, "bold"), bg="#f8f9fa", fg=self.text_muted)
            t_lbl.pack(anchor="w")
            self.split_before_title_labels[k] = t_lbl
            v = tk.Label(before_box, text="-", font=("Segoe UI", 10, "bold"), bg="#f8f9fa", fg=self.text_dark)
            v.pack(anchor="w", pady=(0, 2))
            self.split_before_labels[k] = v

        after_box = tk.LabelFrame(comp_frame, text=f" {t('split_sec_after')} ", font=("Segoe UI", 9, "bold"), bg="#e8f0fe", padx=10, pady=8)
        after_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.split_after_box = after_box

        self.split_after_labels = {}
        self.split_after_title_labels = {}
        for k, lbl in [("shares", t("lbl_split_after_shares")), ("price", t("lbl_split_after_price")), ("cur_price", t("lbl_split_after_effective_price")), ("total", t("lbl_split_total_cost_basis")), ("val", t("card_total_value") + ":")]:
            t_lbl = tk.Label(after_box, text=lbl, font=("Segoe UI", 8, "bold"), bg="#e8f0fe", fg=self.text_muted)
            t_lbl.pack(anchor="w")
            self.split_after_title_labels[k] = t_lbl
            v = tk.Label(after_box, text="-", font=("Segoe UI", 10, "bold"), bg="#e8f0fe", fg=self.primary_color)
            v.pack(anchor="w", pady=(0, 2))
            self.split_after_labels[k] = v

        # 3. Future Potential Earnings Card ("Till later how much you can earn")
        self.split_future_box = tk.LabelFrame(right_card, text=f" {t('split_sec_future')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=12, pady=8)
        self.split_future_box.pack(fill=tk.BOTH, expand=True)

        self.split_future_labels = {}
        self.split_future_title_labels = {}
        fut_top_row = ttk.Frame(self.split_future_box)
        fut_top_row.pack(fill=tk.X, pady=(0, 6))

        fut_fields = [
            ("target_val", t("lbl_split_future_value")),
            ("total_prof", t("lbl_future_total_profit") + ":"),
            ("new_gain", t("lbl_split_extra_gain")),
        ]
        for i, (k, lbl) in enumerate(fut_fields):
            cell = tk.Frame(fut_top_row, bg="#f8f9fa", bd=1, relief="solid", padx=8, pady=4)
            cell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            t_lbl = tk.Label(cell, text=lbl, font=("Segoe UI", 8, "bold"), bg="#f8f9fa", fg=self.text_muted)
            t_lbl.pack(anchor="w")
            self.split_future_title_labels[k] = t_lbl
            v = tk.Label(cell, text="-", font=("Segoe UI", 11, "bold"), bg="#f8f9fa", fg=self.primary_color)
            v.pack(anchor="w")
            self.split_future_labels[k] = v

        self.lbl_split_future_scenarios = tk.Label(self.split_future_box, text=t("lbl_future_scenarios"), font=("Segoe UI", 8, "bold"), bg="#ffffff", fg=self.text_muted)
        self.lbl_split_future_scenarios.pack(anchor="w", pady=(4, 2))
        self.split_scenarios_frame = ttk.Frame(self.split_future_box)
        self.split_scenarios_frame.pack(fill=tk.X, pady=(0, 4))
        self.split_scenario_cells = []

    def _set_split_purchase_date_days_ago(self, days: int):
        from datetime import date, timedelta
        target_d = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        if hasattr(self, "split_purchase_date_entry"):
            self.split_purchase_date_entry.delete(0, tk.END)
            self.split_purchase_date_entry.insert(0, target_d)
            self._calc_split_results()

    def _apply_split_target_multiplier(self, mult: float):
        try:
            cur_p = float(self.split_cur_price_entry.get().strip())
            ratio_to = float(self.split_to_entry.get().strip())
            ratio_from = float(self.split_from_entry.get().strip())
            mult_split = ratio_to / ratio_from if ratio_from > 0 else 1.0
            new_cur_p = cur_p / mult_split if mult_split > 0 else cur_p
            target_p = round(new_cur_p * mult, 2)
            self.split_target_price_entry.delete(0, tk.END)
            self.split_target_price_entry.insert(0, f"{target_p:.2f}")
            self._calc_split_results()
        except ValueError:
            pass

    def _apply_split_target_presplit(self):
        try:
            cur_p = float(self.split_cur_price_entry.get().strip())
            self.split_target_price_entry.delete(0, tk.END)
            self.split_target_price_entry.insert(0, f"{cur_p:.2f}")
            self._calc_split_results()
        except ValueError:
            pass

    # -------------------------------------------------------------
    # Tab 4: Selling & Profit Calculator
    # -------------------------------------------------------------
    def _build_selling_tab(self):
        tab = self.tab_sell
        container = ttk.Frame(tab, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        left_box = tk.LabelFrame(container, text=f" {t('sell_order_box')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=12, pady=12)
        left_box.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.sell_order_box = left_box

        self.lbl_sell_select = tk.Label(left_box, text=t("lbl_select_from_portfolio"), font=("Segoe UI", 9, "bold"), bg="#ffffff")
        self.lbl_sell_select.pack(anchor="w", pady=(0, 2))
        self.sell_holding_var = tk.StringVar()
        self.sell_holding_cb = ttk.Combobox(left_box, textvariable=self.sell_holding_var, state="readonly", width=22)
        self.sell_holding_cb.pack(fill=tk.X, pady=(0, 8))
        self.sell_holding_cb.bind("<<ComboboxSelected>>", self._on_sell_holding_selected)

        pct_frame = ttk.Frame(left_box)
        pct_frame.pack(fill=tk.X, pady=(0, 8))
        for pct in [25, 50, 75, 100]:
            btn = tk.Button(
                pct_frame,
                text=f"{pct}%",
                font=("Segoe UI", 8),
                bg="#ffffff",
                relief="solid",
                bd=1,
                command=lambda p=pct: self._apply_sell_percentage(p),
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)

        self.sell_inputs = {}
        self.sell_input_labels = {}
        fields = [
            ("symbol", t("col_symbol") + ":", "AAPL"),
            ("shares_to_sell", t("lbl_sell_shares"), "25"),
            ("buy_price", t("lbl_sell_buy_price"), "150.00"),
            ("sell_price", t("lbl_sell_price"), "220.00"),
            ("commission_flat", t("lbl_sell_commission_flat"), "0.00"),
            ("commission_pct", t("lbl_sell_commission_pct"), "0.00"),
        ]

        for k, lbl, default in fields:
            l_w = tk.Label(left_box, text=lbl, font=("Segoe UI", 8), bg="#ffffff")
            l_w.pack(anchor="w")
            self.sell_input_labels[k] = l_w
            entry = tk.Entry(left_box, font=("Segoe UI", 9), bd=1, relief="solid")
            entry.insert(0, default)
            entry.pack(fill=tk.X, pady=(0, 4))
            self.sell_inputs[k] = entry

        self.lbl_sell_tax_bracket = tk.Label(left_box, text=t("lbl_sell_tax_bracket"), font=("Segoe UI", 8, "bold"), bg="#ffffff")
        self.lbl_sell_tax_bracket.pack(anchor="w", pady=(4, 0))
        self.tax_bracket_var = tk.StringVar(value="15% Long-Term")
        tax_cb = ttk.Combobox(
            left_box,
            textvariable=self.tax_bracket_var,
            values=["0% (Tax-Exempt / IRA)", "15% Long-Term", "20% Long-Term (High)", "28% Short-Term", "Custom %"],
            state="readonly",
        )
        tax_cb.pack(fill=tk.X, pady=(0, 4))
        tax_cb.bind("<<ComboboxSelected>>", self._on_tax_preset_changed)

        self.lbl_sell_custom_tax = tk.Label(left_box, text=t("lbl_sell_custom_tax"), font=("Segoe UI", 8), bg="#ffffff")
        self.lbl_sell_custom_tax.pack(anchor="w")
        self.sell_tax_entry = tk.Entry(left_box, font=("Segoe UI", 9), bd=1, relief="solid")
        self.sell_tax_entry.insert(0, "15.0")
        self.sell_tax_entry.pack(fill=tk.X, pady=(0, 4))

        self.lbl_sell_tax_lot = tk.Label(left_box, text=t("lbl_tax_lot_method"), font=("Segoe UI", 8, "bold"), bg="#ffffff")
        self.lbl_sell_tax_lot.pack(anchor="w", pady=(2, 0))
        self.tax_lot_var = tk.StringVar(value="ACB")
        tax_lot_cb = ttk.Combobox(
            left_box,
            textvariable=self.tax_lot_var,
            values=["ACB", "FIFO", "Specific"],
            state="readonly",
        )
        tax_lot_cb.pack(fill=tk.X, pady=(0, 8))

        self.btn_calc_sell = tk.Button(
            left_box,
            text=t("btn_calc_sell"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=4,
            command=self._calc_selling_results,
        )
        self.btn_calc_sell.pack(fill=tk.X, pady=(0, 6))

        self.btn_record_sale = tk.Button(
            left_box,
            text="💰 " + t("btn_execute_sell"),
            font=("Segoe UI", 9, "bold"),
            bg="#0f9d58",
            fg="#ffffff",
            relief="flat",
            pady=6,
            command=self._execute_and_record_sale,
        )
        self.btn_record_sale.pack(fill=tk.X)

        right_box = ttk.Frame(container)
        right_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        res_card = tk.LabelFrame(right_box, text=f" {t('sell_res_card')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=12, pady=10)
        res_card.pack(fill=tk.X, pady=(0, 8))
        self.sell_res_card = res_card

        self.sell_results = {}
        self.sell_res_title_labels = {}
        sell_res_fields = [
            ("gross_proceeds", t("lbl_sell_gross"), "$0.00", self.text_dark),
            ("cost_basis", t("lbl_sell_cost"), "$0.00", self.text_muted),
            ("commission_fee", t("lbl_sell_commission"), "$0.00", self.red_color),
            ("gross_gain", t("lbl_sell_gross_gain"), "$0.00", self.text_dark),
            ("estimated_tax", t("lbl_sell_estimated_tax"), "$0.00", self.red_color),
            ("net_proceeds", t("lbl_sell_net_proceeds"), "$0.00", self.primary_color),
            ("net_profit", t("lbl_sell_profit"), "$0.00", self.green_color),
            ("net_roi_pct", t("lbl_sell_roi"), "0.00%", self.green_color),
        ]

        for i, (k, lbl, default, col) in enumerate(sell_res_fields):
            r = i // 2
            c = (i % 2) * 2
            t_lbl = tk.Label(res_card, text=lbl, font=("Segoe UI", 8, "bold"), bg="#ffffff", fg=self.text_muted)
            t_lbl.grid(row=r * 2, column=c, sticky="w", padx=8)
            self.sell_res_title_labels[k] = t_lbl
            val_l = tk.Label(res_card, text=default, font=("Segoe UI", 11, "bold"), bg="#ffffff", fg=col)
            val_l.grid(row=r * 2 + 1, column=c, sticky="w", padx=8, pady=(0, 4))
            self.sell_results[k] = val_l

        target_card = tk.LabelFrame(right_box, text=f" {t('sell_target_card')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=12, pady=10)
        target_card.pack(fill=tk.BOTH, expand=True)
        self.sell_target_card = target_card

        be_row = ttk.Frame(target_card)
        be_row.pack(fill=tk.X, pady=(0, 6))
        self.lbl_breakeven_title = tk.Label(be_row, text=t("lbl_breakeven_price"), font=("Segoe UI", 9, "bold"), bg=self.bg_main)
        self.lbl_breakeven_title.pack(side=tk.LEFT)
        self.lbl_breakeven = tk.Label(be_row, text="$0.00", font=("Segoe UI", 11, "bold"), bg=self.bg_main, fg=self.primary_color)
        self.lbl_breakeven.pack(side=tk.LEFT, padx=8)

        tp_frame = ttk.Frame(target_card)
        tp_frame.pack(fill=tk.X, pady=(6, 0))
        self.lbl_target_profit_title = tk.Label(tp_frame, text=t("lbl_target_profit_input"), font=("Segoe UI", 8, "bold"), bg=self.bg_main)
        self.lbl_target_profit_title.pack(side=tk.LEFT)
        self.target_profit_entry = tk.Entry(tp_frame, width=10, bd=1, relief="solid")
        self.target_profit_entry.insert(0, "500.00")
        self.target_profit_entry.pack(side=tk.LEFT, padx=6)

        self.btn_find_target = tk.Button(
            tp_frame,
            text=t("btn_find_target_price"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=6,
            command=self._calc_target_sell_price,
        )
        self.btn_find_target.pack(side=tk.LEFT, padx=4)

        self.lbl_target_price_res = tk.Label(target_card, text="", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg=self.green_color)
        self.lbl_target_price_res.pack(anchor="w", pady=(4, 0))

    # -------------------------------------------------------------
    # Tab 5: Sales & Trade History
    # -------------------------------------------------------------
    def _build_history_tab(self):
        tab = self.tab_history

        # Top Filter Bar inside Transaction History Tab
        filter_bar = ttk.Frame(tab, padding="8 6 8 2")
        filter_bar.pack(fill=tk.X)

        self.lbl_tx_port = tk.Label(filter_bar, text=t("lbl_tx_portfolio"), font=("Segoe UI", 9, "bold"))
        self.lbl_tx_port.pack(side=tk.LEFT, padx=(0, 4))

        self.sales_filter_var = tk.StringVar(value=t("portfolio_all_consolidated"))
        self.sales_filter_cb = ttk.Combobox(
            filter_bar,
            textvariable=self.sales_filter_var,
            values=self._get_portfolio_dropdown_values(),
            state="readonly",
            width=22,
            font=("Segoe UI", 9)
        )
        self.sales_filter_cb.pack(side=tk.LEFT, padx=(0, 8))
        self.sales_filter_cb.bind("<<ComboboxSelected>>", self._on_sales_filter_changed)

        self.lbl_tx_type = tk.Label(filter_bar, text=t("lbl_tx_type"), font=("Segoe UI", 9, "bold"))
        self.lbl_tx_type.pack(side=tk.LEFT, padx=(0, 4))

        self.tx_type_filter_var = tk.StringVar(value=t("tx_type_all"))
        self.tx_type_filter_cb = ttk.Combobox(
            filter_bar,
            textvariable=self.tx_type_filter_var,
            values=[t("tx_type_all"), t("tx_type_buy"), t("tx_type_sell")],
            state="readonly",
            width=14,
            font=("Segoe UI", 9)
        )
        self.tx_type_filter_cb.pack(side=tk.LEFT, padx=(0, 8))
        self.tx_type_filter_cb.bind("<<ComboboxSelected>>", self._on_sales_filter_changed)

        self.btn_tx_all = tk.Button(
            filter_bar,
            text=t("btn_tx_all"),
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            pady=1,
            command=self._show_all_sales_clicked,
        )
        self.btn_tx_all.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_tx_match = tk.Button(
            filter_bar,
            text=t("btn_tx_match"),
            font=("Segoe UI", 8),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            pady=1,
            command=self._match_active_portfolio_sales,
        )
        self.btn_tx_match.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_tx_record = tk.Button(
            filter_bar,
            text=t("btn_tx_record"),
            font=("Segoe UI", 8, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            padx=8,
            pady=2,
            command=self._open_record_transaction_dialog,
        )
        self.btn_tx_record.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_tx_edit = tk.Button(
            filter_bar,
            text=t("btn_tx_edit"),
            font=("Segoe UI", 8),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            pady=1,
            command=self._open_edit_transaction_dialog,
        )
        self.btn_tx_edit.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_tx_report = tk.Button(
            filter_bar,
            text=t("btn_tx_report"),
            font=("Segoe UI", 8, "bold"),
            bg="#0f9d58",
            fg="#ffffff",
            relief="flat",
            padx=8,
            pady=2,
            command=self._switch_to_report_tab,
        )
        self.btn_tx_report.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_tx_storage_fee = tk.Button(
            filter_bar,
            text=t("btn_log_storage_fee"),
            font=("Segoe UI", 8),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            pady=1,
            command=self._quick_log_storage_fee,
        )
        self.btn_tx_storage_fee.pack(side=tk.LEFT, padx=(0, 8))

        self.lbl_hist_filter = tk.Label(
            filter_bar,
            text=t("lbl_filter_history"),
            font=("Segoe UI", 9, "bold"),
            bg=self.bg_main,
            fg=self.text_dark,
        )
        self.lbl_hist_filter.pack(side=tk.LEFT, padx=(6, 4))

        self.hist_search_var = tk.StringVar()
        self.hist_search_entry = ttk.Entry(filter_bar, textvariable=self.hist_search_var, width=18)
        self.hist_search_entry.pack(side=tk.LEFT, padx=(0, 8))
        self.hist_search_entry.bind("<KeyRelease>", lambda e: self._refresh_sales_table())

        self.lbl_sales_stats = tk.Label(
            filter_bar,
            text="",
            font=("Segoe UI", 9),
            fg=self.text_muted,
        )
        self.lbl_sales_stats.pack(side=tk.RIGHT)

        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        cols = (
            "date",
            "type",
            "portfolio",
            "symbol",
            "currency",
            "shares",
            "price",
            "total_amount",
            "commission",
            "tax",
            "net_profit",
            "roi",
        )
        self.history_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        hist_headers = [
            ("date", t("col_tx_date"), 125),
            ("type", t("col_tx_type"), 75),
            ("portfolio", t("col_tx_port"), 95),
            ("symbol", t("col_tx_sym"), 65),
            ("currency", t("col_tx_curr"), 45),
            ("shares", t("col_tx_shares"), 65),
            ("price", t("col_tx_price"), 75),
            ("total_amount", t("col_tx_total"), 90),
            ("commission", t("col_tx_fees"), 55),
            ("tax", t("col_tx_tax"), 50),
            ("net_profit", t("col_tx_profit"), 95),
            ("roi", t("col_tx_roi"), 70),
        ]

        for col, h, w in hist_headers:
            self.history_tree.heading(col, text=h, command=lambda c=col: self._sort_history_by(c))
            self.history_tree.column(col, width=w, anchor="e" if col not in ("type", "symbol", "portfolio", "currency", "date") else "center")

        v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.history_tree.tag_configure("positive", foreground=self.green_color)
        self.history_tree.tag_configure("negative", foreground=self.red_color)
        self.history_tree.tag_configure("buy", foreground="#00897b")
        self.history_tree.tag_configure("neutral", foreground=self.text_dark)
        self.history_tree.bind("<Double-1>", lambda event: self._open_edit_transaction_dialog())

        btn_bar = ttk.Frame(tab, padding="8 4 8 8")
        btn_bar.pack(fill=tk.X)

        self.btn_tx_export = tk.Button(
            btn_bar,
            text=t("btn_tx_export"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            command=self._export_sales_csv,
        )
        self.btn_tx_export.pack(side=tk.LEFT, padx=4)

        self.btn_tx_clear = tk.Button(
            btn_bar,
            text=t("btn_tx_clear"),
            bg="#ffffff",
            fg=self.red_color,
            relief="solid",
            bd=1,
            padx=8,
            command=self._clear_sales_history,
        )
        self.btn_tx_clear.pack(side=tk.LEFT, padx=4)

        self.lbl_total_realized = tk.Label(
            btn_bar,
            text=t("lbl_rep_total_realized", profit="$0.00"),
            font=("Segoe UI", 10, "bold"),
            bg=self.bg_main,
            fg=self.green_color,
        )
        self.lbl_total_realized.pack(side=tk.RIGHT, padx=12)

    # -------------------------------------------------------------
    # Period Earnings Report Tab (Tab 8)
    # -------------------------------------------------------------
    def _switch_to_report_tab(self):
        """Switch directly to the Period Earnings Report tab and refresh it."""
        if hasattr(self, "tab_report") and hasattr(self, "notebook"):
            self.notebook.select(self.tab_report)
            if hasattr(self, "rep_port_cb") and hasattr(self, "current_portfolio"):
                all_vals = list(self.rep_port_cb["values"])
                if self.current_portfolio in all_vals:
                    self.rep_port_cb.set(self.current_portfolio)
                elif self.current_portfolio in ("All Portfolios (Consolidated)", "All Portfolios", "All", t("portfolio_all_consolidated"), t("portfolio_all_plain")):
                    self.rep_port_cb.set(t("portfolio_all_consolidated"))
            self._refresh_report_tab()

    def _build_report_tab(self):
        tab = self.tab_report

        # Header / title frame
        header_frame = ttk.Frame(tab, padding="14 10 14 6")
        header_frame.pack(fill=tk.X)
        self.lbl_report_tab_title = tk.Label(
            header_frame,
            text=f"📊 {t('tab_report').strip()}",
            font=("Segoe UI", 12, "bold"),
            fg=self.primary_color,
            bg=self.bg_main,
        )
        self.lbl_report_tab_title.pack(side=tk.LEFT)

        # Filters toolbar frame
        filter_panel = ttk.LabelFrame(tab, text=f"🔍 {t('dlg_period_report')}", padding="10 8 10 8")
        filter_panel.pack(fill=tk.X, padx=14, pady=(0, 6))

        f_row = ttk.Frame(filter_panel)
        f_row.pack(fill=tk.X)

        self.lbl_rep_port = tk.Label(f_row, text=t("lbl_portfolio"), font=("Segoe UI", 9, "bold"))
        self.lbl_rep_port.pack(side=tk.LEFT, padx=(0, 6))

        all_port_names = [t("portfolio_all_consolidated")] + [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        self.rep_port_cb = ttk.Combobox(f_row, values=all_port_names, state="readonly", width=22)
        default_port = self.current_portfolio if self.current_portfolio in all_port_names else all_port_names[0]
        self.rep_port_cb.set(default_port)
        self.rep_port_cb.pack(side=tk.LEFT, padx=(0, 14))
        self.rep_port_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_report_tab())

        self.lbl_rep_period = tk.Label(f_row, text=t("lbl_filter_period"), font=("Segoe UI", 9, "bold"))
        self.lbl_rep_period.pack(side=tk.LEFT, padx=(0, 6))

        self.rep_period_modes = [
            ("this_month", t("period_this_month")),
            ("this_week", t("period_this_week")),
            ("in_months", t("period_in_months")),
            ("in_weeks", t("period_in_weeks")),
            ("custom", t("period_custom")),
        ]
        self.rep_period_cb = ttk.Combobox(f_row, values=[m[1] for m in self.rep_period_modes], state="readonly", width=24)
        self.rep_period_cb.set(self.rep_period_modes[0][1])
        self.rep_period_cb.pack(side=tk.LEFT, padx=(0, 12))

        # Custom Date Range sub-frame
        self.rep_date_frame = ttk.Frame(f_row)
        self.lbl_rep_date_range = tk.Label(self.rep_date_frame, text=t("lbl_date_range"), font=("Segoe UI", 8))
        self.lbl_rep_date_range.pack(side=tk.LEFT, padx=(0, 4))
        self.rep_start_entry = tk.Entry(self.rep_date_frame, font=("Segoe UI", 9), width=11, relief="solid", bd=1)
        today = date.today()
        self.rep_start_entry.insert(0, (today - timedelta(days=30)).strftime("%Y-%m-%d"))
        self.rep_start_entry.pack(side=tk.LEFT, padx=(0, 4))

        self.lbl_rep_to = tk.Label(self.rep_date_frame, text=t("lbl_to"), font=("Segoe UI", 8))
        self.lbl_rep_to.pack(side=tk.LEFT, padx=(0, 4))
        self.rep_end_entry = tk.Entry(self.rep_date_frame, font=("Segoe UI", 9), width=11, relief="solid", bd=1)
        self.rep_end_entry.insert(0, today.strftime("%Y-%m-%d"))
        self.rep_end_entry.pack(side=tk.LEFT)

        def _on_rep_mode_change(event=None):
            sel_text = self.rep_period_cb.get()
            if t("period_custom") in sel_text or "custom" in sel_text.lower():
                self.rep_date_frame.pack(side=tk.LEFT, padx=(0, 8))
            else:
                self.rep_date_frame.pack_forget()
            self._refresh_report_tab()

        self.rep_period_cb.bind("<<ComboboxSelected>>", _on_rep_mode_change)

        self.btn_rep_calc = tk.Button(
            f_row,
            text=f"🔄 {t('btn_refresh')}",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=10,
            pady=2,
            command=self._refresh_report_tab,
        )
        self.btn_rep_calc.pack(side=tk.LEFT, padx=(6, 8))

        self.btn_rep_export = tk.Button(
            f_row,
            text=t("btn_export_report_html"),
            font=("Segoe UI", 9, "bold"),
            bg="#0f9d58",
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=2,
            command=self._export_report_tab_html,
        )
        self.btn_rep_export.pack(side=tk.RIGHT, padx=(4, 0))

        self.btn_rep_export_csv = tk.Button(
            f_row,
            text=t("btn_export_report_csv"),
            font=("Segoe UI", 9, "bold"),
            bg="#1a73e8",
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=2,
            command=self._export_report_tab_csv,
        )
        self.btn_rep_export_csv.pack(side=tk.RIGHT)

        # KPI Summary Cards Frame
        kpi_frame = ttk.Frame(tab, padding="14 2 14 6")
        kpi_frame.pack(fill=tk.X)

        self.rep_kpi_profit = self._make_report_kpi_box(kpi_frame, t("card_realized_profit"), "rep_kpi_lbl_profit")
        self.rep_kpi_roi = self._make_report_kpi_box(kpi_frame, t("card_period_roi"), "rep_kpi_lbl_roi")
        self.rep_kpi_sales = self._make_report_kpi_box(kpi_frame, t("card_sales_proceeds"), "rep_kpi_lbl_sales")
        self.rep_kpi_cost = self._make_report_kpi_box(kpi_frame, t("card_cost_sold"), "rep_kpi_lbl_cost")
        self.rep_kpi_buys = self._make_report_kpi_box(kpi_frame, t("card_buy_volume"), "rep_kpi_lbl_buys")
        self.rep_kpi_trades = self._make_report_kpi_box(kpi_frame, "Trades (B / S / D)", "rep_kpi_lbl_trades")

        # Sub-Notebook for Breakdown and Records
        self.rep_nb = ttk.Notebook(tab)
        self.rep_nb.pack(fill=tk.BOTH, expand=True, padx=14, pady=(4, 10))

        # Sub-Tab 1: Breakdown
        tab_breakdown = ttk.Frame(self.rep_nb, padding=8)
        self.rep_tab_breakdown = tab_breakdown
        self.rep_nb.add(tab_breakdown, text=t("tab_period_breakdown"))

        b_cols = ("interval", "trades", "buy_vol", "sell_proc", "cost_basis", "profit", "roi")
        self.rep_b_tree = ttk.Treeview(tab_breakdown, columns=b_cols, show="headings")
        b_headers = [
            ("interval", t("col_period_interval"), 180),
            ("trades", t("col_trades_count"), 70),
            ("buy_vol", t("col_buy_volume"), 110),
            ("sell_proc", t("col_sell_proceeds"), 110),
            ("cost_basis", t("col_cost_sold"), 110),
            ("profit", t("col_realized_profit"), 120),
            ("roi", t("col_net_roi"), 80),
        ]
        for c, h, w in b_headers:
            self.rep_b_tree.heading(c, text=h)
            self.rep_b_tree.column(c, width=w, anchor="e" if c not in ("interval",) else "w")

        b_scroll = ttk.Scrollbar(tab_breakdown, orient=tk.VERTICAL, command=self.rep_b_tree.yview)
        self.rep_b_tree.configure(yscrollcommand=b_scroll.set)
        b_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.rep_b_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.rep_b_tree.tag_configure("positive", foreground=self.green_color)
        self.rep_b_tree.tag_configure("negative", foreground=self.red_color)

        # Sub-Tab 2: Individual Transactions
        tab_records = ttk.Frame(self.rep_nb, padding=8)
        self.rep_tab_records = tab_records
        self.rep_nb.add(tab_records, text=t("tab_individual_records"))

        r_cols = ("date", "type", "portfolio", "symbol", "shares", "price", "total", "cost", "profit", "roi", "notes")
        self.rep_r_tree = ttk.Treeview(tab_records, columns=r_cols, show="headings")
        r_headers = [
            ("date", t("col_tx_date"), 120),
            ("type", t("col_tx_type"), 70),
            ("portfolio", t("col_tx_port"), 90),
            ("symbol", t("col_tx_sym"), 65),
            ("shares", t("col_tx_shares"), 65),
            ("price", t("col_tx_price"), 75),
            ("total", t("col_tx_total"), 90),
            ("cost", t("col_cost_basis"), 90),
            ("profit", t("col_tx_profit"), 95),
            ("roi", t("col_tx_roi"), 70),
            ("notes", t("col_notes"), 140),
        ]
        for c, h, w in r_headers:
            self.rep_r_tree.heading(c, text=h)
            self.rep_r_tree.column(c, width=w, anchor="e" if c not in ("type", "symbol", "portfolio", "date", "notes") else "center")

        r_scroll = ttk.Scrollbar(tab_records, orient=tk.VERTICAL, command=self.rep_r_tree.yview)
        self.rep_r_tree.configure(yscrollcommand=r_scroll.set)
        r_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.rep_r_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.rep_r_tree.tag_configure("positive", foreground=self.green_color)
        self.rep_r_tree.tag_configure("negative", foreground=self.red_color)
        self.rep_r_tree.tag_configure("buy", foreground="#00897b")

        self.current_report_tab_result = {}

    def _make_report_kpi_box(self, parent, title, label_attr_name=None):
        box = tk.Frame(parent, bg="#ffffff", bd=1, relief="solid", padx=10, pady=8)
        box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        lbl_t = tk.Label(box, text=title, font=("Segoe UI", 8, "bold"), fg=self.text_muted, bg="#ffffff")
        lbl_t.pack(anchor="w")
        if label_attr_name:
            setattr(self, label_attr_name, lbl_t)
        lbl_v = tk.Label(box, text="$0.00", font=("Segoe UI", 12, "bold"), fg=self.text_dark, bg="#ffffff")
        lbl_v.pack(anchor="w", pady=(2, 0))
        return lbl_v

    def _refresh_report_tab(self):
        if not hasattr(self, "rep_port_cb") or not hasattr(self, "rep_period_cb"):
            return

        sel_port = self.rep_port_cb.get().strip()
        is_all_p = (
            sel_port in ("All Portfolios (Consolidated)", "All Portfolios", "All", "*",
                         t("portfolio_all_consolidated"), t("portfolio_all_plain"))
            or "consolidated" in sel_port.lower()
            or "合併" in sel_port
            or "合并" in sel_port
        )
        port_arg = None if is_all_p else sel_port

        sel_mode_text = self.rep_period_cb.get()
        mode_code = "this_month"
        for code, name in self.rep_period_modes:
            if name == sel_mode_text:
                mode_code = code
                break

        start_d = None
        end_d = None
        if mode_code == "custom":
            s_str = self.rep_start_entry.get().strip()
            e_str = self.rep_end_entry.get().strip()
            start_d = parse_tx_date(s_str)
            end_d = parse_tx_date(e_str)
            if not start_d or not end_d:
                messagebox.showerror(t("msg_error"), t("msg_invalid_date_range"), parent=self.root)
                return

        all_txs = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=None, tx_type=None)
        res = calc_period_earnings(
            all_txs,
            period_mode=mode_code,
            start_date=start_d,
            end_date=end_d,
            portfolio_name=port_arg,
        )
        self.current_report_tab_result = res

        # Update KPI Cards
        summ = res.get("summary", {})
        tot_p = float(summ.get("total_realized_profit", 0.0))
        roi_p = float(summ.get("net_roi_pct", 0.0))
        tot_s = float(summ.get("total_sell_proceeds", 0.0))
        tot_c = float(summ.get("total_cost_basis", 0.0))
        tot_b = float(summ.get("total_buy_volume", 0.0))
        b_cnt = summ.get("buy_count", 0)
        s_cnt = summ.get("sell_count", 0)
        d_cnt = summ.get("dividend_count", 0)

        p_color = self.green_color if tot_p >= 0 else self.red_color
        self.rep_kpi_profit.config(text=f"${tot_p:+,.2f}", fg=p_color)
        self.rep_kpi_roi.config(text=f"{roi_p:+.2f}%", fg=p_color)
        self.rep_kpi_sales.config(text=f"${tot_s:,.2f}")
        self.rep_kpi_cost.config(text=f"${tot_c:,.2f}")
        self.rep_kpi_buys.config(text=f"${tot_b:,.2f}", fg="#1a73e8")
        self.rep_kpi_trades.config(text=f"{b_cnt} B / {s_cnt} S / {d_cnt} D")

        # Update Breakdown Tree
        for it in self.rep_b_tree.get_children():
            self.rep_b_tree.delete(it)
        bd = res.get("breakdown", [])
        if bd:
            for b in bd:
                bp = float(b.get("total_realized_profit", 0.0))
                tag = "positive" if bp >= 0 else "negative"
                self.rep_b_tree.insert(
                    "",
                    tk.END,
                    values=(
                        b.get("period_label", ""),
                        b.get("total_transactions", 0),
                        f"${float(b.get('total_buy_volume', 0.0)):,.2f}",
                        f"${float(b.get('total_sell_proceeds', 0.0)):,.2f}",
                        f"${float(b.get('total_cost_basis', 0.0)):,.2f}",
                        f"${bp:+,.2f}",
                        f"{float(b.get('net_roi_pct', 0.0)):+.2f}%",
                    ),
                    tags=(tag,),
                )
            self.rep_nb.select(0)
        else:
            self.rep_b_tree.insert("", tk.END, values=("(Breakdown available in 'In Months' or 'In Weeks' modes)", "-", "-", "-", "-", "-", "-"))
            self.rep_nb.select(1)

        # Update Records Tree
        for it in self.rep_r_tree.get_children():
            self.rep_r_tree.delete(it)
        recs = res.get("records", [])
        for r in recs:
            rt = str(r.get("type", "BUY")).upper()
            rp = float(r.get("net_profit", 0.0) or 0.0)
            rr = float(r.get("net_roi_pct", 0.0) or 0.0)
            if "SELL" in rt:
                tag = "positive" if rp >= 0 else "negative"
                p_str = f"${rp:+,.2f}"
                r_str = f"{rr:+.2f}%"
            elif "BUY" in rt:
                tag = "buy"
                p_str = "—"
                r_str = "—"
            else:
                tag = "positive" if rp >= 0 else "neutral"
                p_str = f"${rp:+,.2f}"
                r_str = "—"

            self.rep_r_tree.insert(
                "",
                tk.END,
                values=(
                    r.get("date", ""),
                    rt,
                    r.get("portfolio", ""),
                    r.get("symbol", ""),
                    f"{float(r.get('shares', 0.0)):.4g}",
                    f"${float(r.get('price', 0.0)):,.2f}",
                    f"${float(r.get('total_amount', 0.0)):,.2f}",
                    f"${float(r.get('cost_basis', 0.0)):,.2f}",
                    p_str,
                    r_str,
                    r.get("notes", ""),
                ),
                tags=(tag,),
            )

    def _export_report_tab_html(self):
        if not getattr(self, "current_report_tab_result", None):
            self._refresh_report_tab()
        if not getattr(self, "current_report_tab_result", None):
            return

        def_filename = f"period_earnings_report_{self.current_report_tab_result.get('period_mode', 'report')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        path = filedialog.asksaveasfilename(
            title=t("btn_export_report_html"),
            defaultextension=".html",
            initialfile=def_filename,
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
            parent=self.root,
        )
        if not path:
            return

        ok = generate_period_earnings_report_html(self.current_report_tab_result, path)
        if ok:
            if messagebox.askyesno(t("msg_success"), t("msg_html_report_success", path=path), parent=self.root):
                webbrowser.open(f"file://{os.path.abspath(path)}")
        else:
            messagebox.showerror(t("msg_error"), t("msg_html_report_failed"), parent=self.root)

    def _export_report_tab_csv(self):
        if not getattr(self, "current_report_tab_result", None):
            self._refresh_report_tab()
        if not getattr(self, "current_report_tab_result", None):
            return

        def_filename = f"period_earnings_report_{self.current_report_tab_result.get('period_mode', 'report')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(
            title=t("btn_export_report_csv"),
            defaultextension=".csv",
            initialfile=def_filename,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            parent=self.root,
        )
        if not path:
            return

        ok = export_period_report_to_csv(self.current_report_tab_result, path)
        if ok:
            messagebox.showinfo(
                t("msg_success"),
                t("msg_report_exported_success", path=path),
                parent=self.root,
            )
        else:
            messagebox.showerror(t("msg_error"), t("msg_tx_export_failed"), parent=self.root)

    # -------------------------------------------------------------
    # Google Account Sync Dialog
    # -------------------------------------------------------------
    def _open_sync_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(f"🌐 {t('dlg_sync_title')}")
        dlg.geometry("640x520")
        dlg.minsize(560, 460)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        sync_notebook = ttk.Notebook(dlg)
        sync_notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Tab A: Live Account / Session Cookie Sync
        tab_live = ttk.Frame(sync_notebook, padding=12)
        sync_notebook.add(tab_live, text=t("tab_live_sync"))

        tk.Label(
            tab_live,
            text=t("lbl_sync_header"),
            font=("Segoe UI", 11, "bold"),
            fg=self.primary_color,
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            tab_live,
            text=t("lbl_sync_desc"),
            font=("Segoe UI", 8),
            fg=self.text_muted,
            wraplength=580,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(tab_live, text=t("lbl_sync_url"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
        url_entry = tk.Entry(tab_live, font=("Segoe UI", 9), bd=1, relief="solid")
        curr_cfg = load_sync_config()
        default_url = curr_cfg.get("portfolio_url") or "https://www.google.com/finance/beta/portfolio/c58e567d-3b90-41d3-92fa-6b200333ec17"
        url_entry.insert(0, default_url)
        url_entry.pack(fill=tk.X, pady=(2, 8))

        tk.Label(tab_live, text=t("lbl_sync_cookie"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
        cookie_text = tk.Text(tab_live, height=4, font=("Courier", 8), bd=1, relief="solid")
        if curr_cfg.get("cookie"):
            cookie_text.insert("1.0", curr_cfg.get("cookie"))
        cookie_text.pack(fill=tk.X, pady=(2, 8))

        status_test_lbl = tk.Label(tab_live, text="", font=("Segoe UI", 8, "bold"), wraplength=580)
        status_test_lbl.pack(anchor="w", pady=(0, 6))

        def test_conn():
            cookie = cookie_text.get("1.0", tk.END).strip()
            status_test_lbl.config(text=t("lbl_sync_testing"), fg=self.primary_color)
            dlg.update()
            success, msg = self.account_sync.test_connection(cookie)
            color = self.green_color if success else self.red_color
            status_test_lbl.config(text=msg, fg=color)

        def sync_live():
            url = url_entry.get().strip()
            cookie = cookie_text.get("1.0", tk.END).strip()
            status_test_lbl.config(text=t("lbl_sync_fetching"), fg=self.primary_color)
            dlg.update()

            res = self.account_sync.fetch_user_portfolio(url, cookie)
            if not res.get("success"):
                err_msg = res.get("error", "Failed to fetch portfolio.")
                status_test_lbl.config(text=t("msg_sync_failed_reason", reason=err_msg), fg=self.red_color)
                messagebox.showwarning(
                    t("dlg_sync_notice_title"),
                    t("msg_sync_notice_tip", error=err_msg),
                    parent=dlg,
                )
                return

            new_holdings = res["holdings"]
            for nh in new_holdings:
                summary = calc_holding_summary(
                    nh.get("shares", 0.0),
                    nh.get("buy_price", 0.0),
                    nh.get("current_price", 0.0),
                    nh.get("dividend_yield", 0.0),
                    nh.get("annual_div_per_share", 0.0),
                )
                nh.update(summary)

            target_p = self.current_portfolio if self.current_portfolio != "All Portfolios (Consolidated)" else DEFAULT_PORTFOLIO_NAME
            for nh in new_holdings:
                nh["portfolio"] = target_p
                if not nh.get("currency"):
                    nh["currency"] = "USD"

            ans = messagebox.askyesnocancel(
                t("dlg_sync_port_title"),
                t("msg_sync_merge_prompt", count=len(new_holdings), port=target_p),
                parent=dlg,
            )
            if ans is True:
                # Merge: avoid duplicates by updating or appending
                for nh in new_holdings:
                    existing = next((h for h in self.all_holdings if h["symbol"] == nh["symbol"] and h.get("portfolio") == target_p), None)
                    if existing:
                        existing["current_price"] = nh["current_price"]
                        summary = calc_holding_summary(
                            existing.get("shares", 0.0),
                            existing.get("buy_price", 0.0),
                            existing.get("current_price", 0.0),
                            existing.get("dividend_yield", 0.0),
                            existing.get("annual_div_per_share", 0.0),
                        )
                        existing.update(summary)
                    else:
                        self.all_holdings.append(nh)
            elif ans is False:
                self.all_holdings = [h for h in self.all_holdings if h.get("portfolio") != target_p] + new_holdings
            else:
                return

            save_portfolio(self.all_holdings, PORTFOLIO_CSV)
            self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
            self._on_portfolio_selected()
            self.fetch_all_quotes()

            status_test_lbl.config(
                text=t("msg_sync_success_status", count=len(new_holdings), time=datetime.now().strftime('%H:%M:%S')),
                fg=self.green_color,
            )
            messagebox.showinfo(t("dlg_sync_success_title"), t("msg_sync_success", count=len(new_holdings)), parent=dlg)

        btn_test = tk.Button(tab_live, text=t("btn_test_connection"), font=("Segoe UI", 9), bg="#ffffff", relief="solid", bd=1, padx=8, command=test_conn)
        btn_test.pack(side=tk.LEFT, padx=(0, 6))

        btn_do_sync = tk.Button(tab_live, text=t("btn_sync_now"), font=("Segoe UI", 9, "bold"), bg=self.primary_color, fg="#ffffff", relief="flat", padx=12, command=sync_live)
        btn_do_sync.pack(side=tk.LEFT)

        # Tab B: Google Finance CSV Import
        tab_csv = ttk.Frame(sync_notebook, padding=12)
        sync_notebook.add(tab_csv, text=t("tab_csv_sync"))

        tk.Label(tab_csv, text=t("lbl_sync_csv_header"), font=("Segoe UI", 11, "bold"), fg=self.primary_color).pack(anchor="w", pady=(0, 4))
        tk.Label(
            tab_csv,
            text=t("lbl_sync_csv_desc"),
            font=("Segoe UI", 8),
            fg=self.text_muted,
            wraplength=580,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        target_port_frame = ttk.Frame(tab_csv)
        target_port_frame.pack(anchor="w", pady=(0, 12))
        tk.Label(target_port_frame, text=t("lbl_sync_target_port"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        port_list = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        if not port_list:
            port_list = [DEFAULT_PORTFOLIO_NAME]
        port_list = sorted(list(set(port_list)))
        default_sync_port = self.current_portfolio if self.current_portfolio in port_list else port_list[0]
        import_port_var = tk.StringVar(value=default_sync_port)
        import_port_combo = ttk.Combobox(target_port_frame, textvariable=import_port_var, values=port_list, width=22, state="readonly")
        import_port_combo.pack(side=tk.LEFT)

        def import_gf_csv():
            target_p = import_port_var.get().strip() or DEFAULT_PORTFOLIO_NAME
            fn = filedialog.askopenfilename(
                title=t("dlg_select_gf_csv_title", port=target_p),
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                parent=dlg,
            )
            if fn:
                loaded = self.account_sync.parse_google_finance_csv(fn, target_portfolio=target_p)
                if not loaded:
                    messagebox.showerror(t("msg_error"), t("msg_gf_csv_parse_err"), parent=dlg)
                    return

                ans = messagebox.askyesno(
                    t("dlg_import_gf_title"),
                    t(
                        "msg_import_gf_confirm",
                        count=len(loaded),
                        port=target_p,
                        preview=f"{', '.join([h['symbol'] for h in loaded[:6]])}{'...' if len(loaded) > 6 else ''}"
                    ),
                    parent=dlg,
                )
                if ans:
                    for h in loaded:
                        summary = calc_holding_summary(h["shares"], h["buy_price"], h["current_price"])
                        h.update(summary)
                        # Check duplicate in target_p
                        existing = next((ex for ex in self.all_holdings if ex["symbol"] == h["symbol"] and ex.get("portfolio") == target_p), None)
                        if existing:
                            existing["current_price"] = h["current_price"]
                            if h.get("name"):
                                existing["name"] = h["name"]
                        else:
                            self.all_holdings.append(h)

                    save_portfolio(self.all_holdings, PORTFOLIO_CSV)
                    self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
                    self.portfolio_var.set(target_p)
                    self.current_portfolio = target_p
                    self._on_portfolio_selected()
                    self.fetch_all_quotes()
                    messagebox.showinfo(t("msg_success"), t("msg_gf_csv_imported", count=len(loaded), port=target_p), parent=dlg)

        tk.Button(
            tab_csv,
            text=t("btn_choose_gf_csv"),
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=12,
            pady=6,
            command=import_gf_csv,
        ).pack(anchor="w", pady=(0, 16))

        # Tab C: Export to Google Finance Format
        tab_export = ttk.Frame(sync_notebook, padding=12)
        sync_notebook.add(tab_export, text=t("tab_export_gf"))

        tk.Label(tab_export, text=t("lbl_sync_export_header"), font=("Segoe UI", 11, "bold"), fg=self.primary_color).pack(anchor="w", pady=(0, 4))
        tk.Label(
            tab_export,
            text=t("lbl_sync_export_desc"),
            font=("Segoe UI", 8),
            fg=self.text_muted,
            wraplength=580,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        def export_gf_format():
            fn = filedialog.asksaveasfilename(
                title=t("dlg_export_gf_title"),
                defaultextension=".csv",
                initialfile="google_finance_portfolio.csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                parent=dlg,
            )
            if fn:
                if self.account_sync.export_to_google_finance_csv(fn, self.holdings):
                    messagebox.showinfo(t("msg_success"), t("msg_export_gf_success", path=fn), parent=dlg)
                else:
                    messagebox.showerror(t("msg_error"), t("msg_export_gf_failed"), parent=dlg)

        tk.Button(
            tab_export,
            text=t("btn_export_gf_csv"),
            font=("Segoe UI", 10, "bold"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=12,
            pady=6,
            command=export_gf_format,
        ).pack(anchor="w")

        # Tab D: Instructions / Help
        tab_help = ttk.Frame(sync_notebook, padding=12)
        sync_notebook.add(tab_help, text=t("tab_sync_help"))

        help_text = t("lbl_sync_help_text")
        help_lbl = tk.Label(tab_help, text=help_text, font=("Segoe UI", 8), justify="left", wraplength=580)
        help_lbl.pack(anchor="w")

        dlg.bind("<Escape>", lambda e: dlg.destroy())

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 640, 520
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    # -------------------------------------------------------------
    # Enhanced Add Stock / Asset Dialog
    # -------------------------------------------------------------
    def _open_add_dialog(self, initial_symbol="", initial_name="", initial_price=None, initial_currency=None):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_add_asset_title"))
        dlg.geometry("480x560")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        # Header
        tk.Label(frame, text=t("dlg_add_asset_title"), font=("Segoe UI", 12, "bold"), fg=self.primary_color).pack(anchor="w", pady=(0, 4))

        # Target Portfolio & Currency
        port_curr_row = ttk.Frame(frame)
        port_curr_row.pack(fill=tk.X, pady=(4, 6))

        tk.Label(port_curr_row, text=t("lbl_portfolio"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        available_ports = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        if not available_ports:
            available_ports = [DEFAULT_PORTFOLIO_NAME]
        default_add_port = self.current_portfolio if self.current_portfolio != "All Portfolios (Consolidated)" else available_ports[0]
        if default_add_port not in available_ports:
            available_ports.append(default_add_port)
        available_ports = sorted(list(set(available_ports)))
        port_add_cb = ttk.Combobox(port_curr_row, values=available_ports, width=22, state="readonly")
        port_add_cb.set(default_add_port)
        port_add_cb.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(port_curr_row, text=t("col_currency") + ":", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        curr_add_cb = ttk.Combobox(port_curr_row, values=["USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY"], state="readonly", width=8)
        def_curr = "USD"
        if "CAD" in default_add_port.upper():
            def_curr = "CAD"
        elif "HKD" in default_add_port.upper():
            def_curr = "HKD"
        curr_add_cb.set(def_curr)
        curr_add_cb.pack(side=tk.LEFT)

        def on_add_port_changed(event=None):
            p_sel = port_add_cb.get().strip().upper()
            if "CAD" in p_sel:
                curr_add_cb.set("CAD")
            elif "HKD" in p_sel:
                curr_add_cb.set("HKD")
            elif "USD" in p_sel:
                curr_add_cb.set("USD")

        port_add_cb.bind("<<ComboboxSelected>>", on_add_port_changed)

        # Quick-picks dropdown
        quick_row = ttk.Frame(frame)
        quick_row.pack(fill=tk.X, pady=(2, 4))
        tk.Label(quick_row, text=t("lbl_quick_picks"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        quick_cb = ttk.Combobox(quick_row, values=[p[0] for p in POPULAR_TICKERS], state="readonly", width=38)
        quick_cb.current(0)
        quick_cb.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def on_quick_select(event=None):
            idx = quick_cb.current()
            if idx > 0 and idx < len(POPULAR_TICKERS):
                label, ticker_sym, curr_code = POPULAR_TICKERS[idx]
                sym_entry.delete(0, tk.END)
                sym_entry.insert(0, ticker_sym)
                if curr_code in curr_add_cb["values"]:
                    curr_add_cb.set(curr_code)
                on_verify()

        quick_cb.bind("<<ComboboxSelected>>", on_quick_select)

        # Symbol entry + live verify button
        sym_box = ttk.Frame(frame)
        sym_box.pack(fill=tk.X, pady=(4, 6))

        tk.Label(sym_box, text=t("col_symbol") + ":", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        input_row = ttk.Frame(sym_box)
        input_row.pack(fill=tk.X, pady=(2, 0))

        sym_entry = tk.Entry(input_row, font=("Segoe UI", 10, "bold"), bd=1, relief="solid")
        sym_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        sym_entry.focus_set()

        verify_status_lbl = tk.Label(frame, text="", font=("Segoe UI", 8, "bold"))

        live_data_box = {"price": 0.0, "name": "", "yield": 0.0, "div_share": 0.0, "currency": "USD"}

        def on_verify():
            sym = sym_entry.get().strip().upper()
            if not sym:
                return
            verify_status_lbl.config(text=t("msg_searching_gf", sym=sym), fg=self.primary_color)
            dlg.update()

            res = self.fetcher.search_or_verify_symbol(sym)
            if res.get("valid"):
                live_p = float(res["price"])
                live_data_box["price"] = live_p
                live_data_box["name"] = res["name"]
                live_data_box["yield"] = res["dividend_yield"]
                live_data_box["div_share"] = res.get("annual_dividend_per_share", 0.0)
                live_data_box["currency"] = res.get("currency", "USD")

                name_entry.delete(0, tk.END)
                name_entry.insert(0, res["name"])

                if res.get("currency") and res["currency"] in curr_add_cb["values"]:
                    curr_add_cb.set(res["currency"])

                # Auto-populate buy price if currently empty, 0, or default
                curr_p_val = price_entry.get().strip()
                if not curr_p_val or curr_p_val in ("0", "0.0", "0.00", "100.00"):
                    price_entry.delete(0, tk.END)
                    price_entry.insert(0, f"{live_p:.2f}")

                # Check if holding already exists in the selected portfolio
                target_port = port_add_cb.get().strip() or DEFAULT_PORTFOLIO_NAME
                existing_pos = next((h for h in self.all_holdings if h["symbol"] == sym and h.get("portfolio") == target_port), None)
                if existing_pos:
                    ex_sh = float(existing_pos.get("shares", 0.0))
                    ex_bp = float(existing_pos.get("buy_price", 0.0))
                    verify_status_lbl.config(
                        text=f"✅ {t('msg_holding_found_info', name=res['name'], price=live_p, curr=res.get('currency', 'USD'))}\n"
                             f"ℹ️ {t('msg_holding_exists_info', port=target_port, sh=ex_sh, bp=ex_bp)}",
                        fg=self.green_color,
                    )
                else:
                    verify_status_lbl.config(
                        text=f"✅ {t('msg_holding_found_info', name=res['name'], price=live_p, curr=res.get('currency', 'USD'))}",
                        fg=self.green_color,
                    )
            else:
                verify_status_lbl.config(text=f"⚠️ {res.get('error')}", fg=self.red_color)

        btn_verify = tk.Button(input_row, text=t("btn_lookup"), font=("Segoe UI", 9), bg="#ffffff", relief="solid", bd=1, padx=8, command=on_verify)
        btn_verify.pack(side=tk.RIGHT)

        verify_status_lbl.pack(anchor="w", pady=(0, 6))

        # Asset Type
        type_row = ttk.Frame(frame)
        type_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(type_row, text=t("lbl_asset_type"), font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 6))
        asset_type_cb = ttk.Combobox(
            type_row,
            values=[
                t("asset_type_stock"),
                t("asset_type_etf"),
                t("asset_type_crypto"),
                t("asset_type_mutual_fund"),
                t("asset_type_index"),
                t("asset_type_other"),
            ],
            state="readonly",
            width=12,
        )
        asset_type_cb.set(t("asset_type_stock"))
        asset_type_cb.pack(side=tk.LEFT)

        # Company / Asset Name
        tk.Label(frame, text=t("col_name") + ":", font=("Segoe UI", 8)).pack(anchor="w")
        name_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        name_entry.pack(fill=tk.X, pady=(2, 6))

        # Shares
        tk.Label(frame, text=t("lbl_shares_count"), font=("Segoe UI", 8, "bold")).pack(anchor="w")
        shares_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        shares_entry.insert(0, "10")
        shares_entry.pack(fill=tk.X, pady=(2, 6))
        shares_entry.bind("<FocusIn>", lambda e: shares_entry.select_range(0, tk.END))

        # Buy Price with quick "Use Live Price" button
        price_row = ttk.Frame(frame)
        price_row.pack(fill=tk.X, pady=(2, 10))

        tk.Label(price_row, text=t("lbl_buy_price_share"), font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)

        def use_live_price():
            if live_data_box["price"] > 0:
                price_entry.delete(0, tk.END)
                price_entry.insert(0, f"{live_data_box['price']:.2f}")
            else:
                on_verify()
                if live_data_box["price"] > 0:
                    price_entry.delete(0, tk.END)
                    price_entry.insert(0, f"{live_data_box['price']:.2f}")

        btn_use_live = tk.Button(price_row, text=t("btn_use_live_price"), font=("Segoe UI", 8), bg="#ffffff", relief="solid", bd=1, padx=4, command=use_live_price)
        btn_use_live.pack(side=tk.RIGHT)

        price_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        price_entry.pack(fill=tk.X, pady=(0, 8))
        price_entry.bind("<FocusIn>", lambda e: price_entry.select_range(0, tk.END))

        # Optional Price Alerts: Target Price and Stop Loss
        add_alert_row = ttk.Frame(frame)
        add_alert_row.pack(fill=tk.X, pady=(0, 12))

        t_sub = ttk.Frame(add_alert_row)
        t_sub.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Label(t_sub, text=t("lbl_target_sell"), font=("Segoe UI", 8)).pack(anchor="w")
        target_add_entry = tk.Entry(t_sub, font=("Segoe UI", 9), bd=1, relief="solid")
        target_add_entry.pack(fill=tk.X, pady=(2, 0))

        s_sub = ttk.Frame(add_alert_row)
        s_sub.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(s_sub, text=t("lbl_stop_loss"), font=("Segoe UI", 8)).pack(anchor="w")
        stop_add_entry = tk.Entry(s_sub, font=("Segoe UI", 9), bd=1, relief="solid")
        stop_add_entry.pack(fill=tk.X, pady=(2, 0))

        def on_save():
            sym = sym_entry.get().strip().upper()
            if not sym:
                messagebox.showerror(t("dlg_error"), t("msg_enter_symbol"), parent=dlg)
                return

            try:
                shares = float(shares_entry.get().strip())
                p_str = price_entry.get().strip()
                if not p_str:
                    messagebox.showerror(t("dlg_error"), t("msg_enter_buy_price"), parent=dlg)
                    return
                buy_price = float(p_str)
                if shares <= 0 or buy_price <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(t("dlg_error"), t("msg_enter_positive_shares_price"), parent=dlg)
                return

            target_port = port_add_cb.get().strip() or DEFAULT_PORTFOLIO_NAME
            curr = curr_add_cb.get().strip().upper() or "USD"
            name = name_entry.get().strip() or live_data_box["name"] or sym
            cur_price = live_data_box["price"] if live_data_box["price"] > 0 else buy_price
            div_yield = live_data_box["yield"]
            ann_div = live_data_box["div_share"]

            # If not looked up yet, attempt fetch
            if cur_price == buy_price:
                q = self.fetcher.fetch_quote(sym)
                if q.get("success"):
                    cur_price = q["price"]
                    name = q.get("name", name)
                    div_yield = q.get("dividend_yield", div_yield)
                    ann_div = q.get("annual_dividend_per_share", ann_div)
                    if q.get("currency") and curr == "USD":
                        curr = q["currency"]

            t_val = target_add_entry.get().strip()
            s_val = stop_add_entry.get().strip()
            try:
                t_price = float(t_val) if t_val else 0.0
            except ValueError:
                t_price = 0.0
            try:
                s_price = float(s_val) if s_val else 0.0
            except ValueError:
                s_price = 0.0

            summary = calc_holding_summary(shares, buy_price, cur_price, div_yield, ann_div)
            holding_record = {
                "portfolio": target_port,
                "symbol": sym,
                "name": name,
                "shares": shares,
                "buy_price": buy_price,
                "current_price": cur_price,
                "dividend_yield": div_yield,
                "annual_div_per_share": ann_div,
                "currency": curr,
                "target_sell_price": t_price,
                "stop_loss_price": s_price,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            holding_record.update(summary)

            existing = next((h for h in self.all_holdings if h["symbol"] == sym and h.get("portfolio") == target_port), None)
            if existing:
                ex_shares = float(existing.get("shares", 0.0))
                ex_bp = float(existing.get("buy_price", 0.0))
                tot_shares = round(ex_shares + shares, 4)
                ex_cost = round(ex_shares * ex_bp, 2)
                add_cost = round(shares * buy_price, 2)
                tot_cost = round(ex_cost + add_cost, 2)
                avg_p = (ex_cost + add_cost) / tot_shares if tot_shares > 0 else buy_price
                avg_p_rounded = round(avg_p, 4)

                ans = messagebox.askyesno(
                    t("msg_merge_holding_title"),
                    t(
                        "msg_merge_holding_prompt",
                        sym=sym,
                        port=target_port,
                        ex_sh=ex_shares,
                        ex_bp=ex_bp,
                        ex_cost=ex_cost,
                        sh=shares,
                        bp=buy_price,
                        add_cost=add_cost,
                        tot_sh=tot_shares,
                        avg_p=avg_p_rounded,
                        tot_cost=tot_cost,
                    ),
                    parent=dlg,
                )
                if ans:
                    existing["shares"] = tot_shares
                    existing["buy_price"] = avg_p_rounded
                    existing["cost_basis"] = tot_cost
                    existing["currency"] = curr
                    existing.update(calc_holding_summary(tot_shares, avg_p_rounded, cur_price, div_yield, ann_div))
                    existing["cost_basis"] = tot_cost
                    existing["unrealized_gain"] = round(existing["market_value"] - tot_cost, 2)
                    existing["unrealized_gain_pct"] = round((existing["unrealized_gain"] / tot_cost * 100), 2) if tot_cost > 0 else 0.0
                else:
                    return
            else:
                self.all_holdings.append(holding_record)

            save_portfolio(self.all_holdings, PORTFOLIO_CSV)

            # Record BUY transaction in transaction history
            buy_tx = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": "BUY",
                "portfolio": target_port,
                "symbol": sym,
                "shares": shares,
                "price": buy_price,
                "total_amount": round(shares * buy_price, 2),
                "cost_basis": round(shares * buy_price, 2),
                "commission_fee": 0.0,
                "estimated_tax": 0.0,
                "net_amount": round(shares * buy_price, 2),
                "currency": curr,
                "notes": f"Bought for {target_port}",
            }
            append_transaction(buy_tx, TRANSACTION_HISTORY_CSV)

            self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
            if self.current_portfolio not in ("All Portfolios (Consolidated)", target_port):
                self.current_portfolio = target_port
                self.portfolio_var.set(target_port)
            self._on_portfolio_selected()
            dlg.destroy()
            self._set_status(f"Added {sym} to {target_port} ({curr}) and recorded BUY transaction.")

        tk.Button(
            frame,
            text=t("btn_save_stock_to_portfolio"),
            font=("Segoe UI", 10, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=6,
            command=on_save,
        ).pack(fill=tk.X)

        dlg.bind("<Escape>", lambda e: dlg.destroy())

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 460, 560
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        if initial_currency and initial_currency in curr_add_cb["values"]:
            curr_add_cb.set(initial_currency)
        if initial_symbol:
            sym_entry.delete(0, tk.END)
            sym_entry.insert(0, initial_symbol)
            if initial_name:
                name_entry.delete(0, tk.END)
                name_entry.insert(0, initial_name)
            if initial_price is not None:
                try:
                    p_flt = float(initial_price)
                    if p_flt > 0:
                        price_entry.delete(0, tk.END)
                        price_entry.insert(0, f"{p_flt:.2f}")
                except Exception:
                    pass
            dlg.after(100, on_verify)

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    # -------------------------------------------------------------
    # Edit / Delete Selected Holding(s)
    # -------------------------------------------------------------
    def _get_holding_from_tree_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        if hasattr(self, "holding_map") and item_id in self.holding_map:
            return self.holding_map[item_id]
        try:
            row_vals = self.holdings_tree.item(item_id).get("values", [])
            raw_sym = ""
            if len(row_vals) > 1:
                raw_sym = str(row_vals[1]).replace("🎯 ", "").replace("⚠️ ", "").strip().upper()
            elif len(row_vals) == 1:
                raw_sym = str(row_vals[0]).replace("🎯 ", "").replace("⚠️ ", "").strip().upper()
            if raw_sym:
                return next((h for h in self.holdings if str(h.get("symbol", "")).strip().upper() == raw_sym or str(h.get("symbol", "")).split(":")[0].strip().upper() == raw_sym), None)
        except Exception:
            pass
        return None

    def _on_tree_double_click(self, event):
        item_id = self.holdings_tree.identify_row(event.y)
        if item_id:
            self.holdings_tree.selection_set(item_id)
            self.holdings_tree.focus(item_id)
            self._open_edit_dialog()

    def _open_edit_dialog(self):
        selected = self.holdings_tree.selection()
        if not selected:
            messagebox.showwarning(t("msg_warning"), t("msg_select_stock"))
            return

        item_id = selected[0]
        holding = self._get_holding_from_tree_item(item_id)
        if not holding:
            return

        sym = holding.get("symbol", "")
        cur_port = holding.get("portfolio", DEFAULT_PORTFOLIO_NAME)
        cur_curr = holding.get("currency", "USD")

        dlg = tk.Toplevel(self.root)
        dlg.title(f"{t('dlg_edit_asset_title')}: {sym}")
        dlg.geometry("440x480")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text=f"{t('col_symbol')}: {sym} ({holding.get('name', '')})",
            font=("Segoe UI", 10, "bold"),
            fg=self.primary_color,
            bg=self.bg_main,
        ).pack(anchor="w", pady=(0, 8))

        # Portfolio selection
        port_row = ttk.Frame(frame)
        port_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(port_row, text=t("lbl_portfolio"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        available_ports = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        if cur_port not in available_ports:
            available_ports.append(cur_port)
        available_ports = sorted(list(set(available_ports)))
        port_edit_cb = ttk.Combobox(port_row, values=available_ports, width=22, state="readonly")
        port_edit_cb.set(cur_port)
        port_edit_cb.pack(side=tk.LEFT, padx=(0, 8))

        # Currency selection
        tk.Label(port_row, text=t("col_currency") + ":", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        curr_edit_cb = ttk.Combobox(port_row, values=["USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY"], state="readonly", width=8)
        curr_edit_cb.set(cur_curr)
        curr_edit_cb.pack(side=tk.LEFT)

        tk.Label(frame, text=t("lbl_shares_count"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        shares_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, insertbackground=self.text_dark)
        shares_entry.insert(0, str(holding.get("shares", 0)))
        shares_entry.pack(fill=tk.X, pady=(2, 8))

        tk.Label(frame, text=t("lbl_buy_price_share"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        price_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, insertbackground=self.text_dark)
        price_entry.insert(0, str(holding.get("buy_price", 0)))
        price_entry.pack(fill=tk.X, pady=(2, 10))

        # Alert thresholds: Target Price and Stop Loss
        alert_row = ttk.Frame(frame)
        alert_row.pack(fill=tk.X, pady=(0, 12))

        target_sub = ttk.Frame(alert_row)
        target_sub.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Label(target_sub, text="🎯 " + t("lbl_target_sell"), font=("Segoe UI", 8, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        target_entry = tk.Entry(target_sub, font=("Segoe UI", 9), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, insertbackground=self.text_dark)
        target_entry.insert(0, str(holding.get("target_sell_price") or ""))
        target_entry.pack(fill=tk.X, pady=(2, 0))

        stop_sub = ttk.Frame(alert_row)
        stop_sub.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(stop_sub, text="⚠️ " + t("lbl_stop_loss"), font=("Segoe UI", 8, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        stop_entry = tk.Entry(stop_sub, font=("Segoe UI", 9), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, insertbackground=self.text_dark)
        stop_entry.insert(0, str(holding.get("stop_loss_price") or ""))
        stop_entry.pack(fill=tk.X, pady=(2, 0))

        def on_save_edit():
            try:
                shares = float(shares_entry.get().strip())
                buy_price = float(price_entry.get().strip())
                if shares <= 0 or buy_price < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(t("dlg_error"), t("msg_enter_positive_shares_price"), parent=dlg)
                return

            new_port = port_edit_cb.get().strip() or cur_port
            new_curr = curr_edit_cb.get().strip().upper() or cur_curr

            t_str = target_entry.get().strip()
            s_str = stop_entry.get().strip()
            try:
                target_p = float(t_str) if t_str else 0.0
            except ValueError:
                target_p = 0.0
            try:
                stop_p = float(s_str) if s_str else 0.0
            except ValueError:
                stop_p = 0.0

            # Match holding record in self.all_holdings by identity or (symbol, original portfolio)
            matched = None
            for h in self.all_holdings:
                if h is holding:
                    matched = h
                    break
            if not matched:
                for h in self.all_holdings:
                    if h.get("symbol") == sym and h.get("portfolio") == cur_port:
                        matched = h
                        break
            if not matched:
                for h in self.all_holdings:
                    if h.get("symbol") == sym:
                        matched = h
                        break
            if not matched:
                matched = holding
                self.all_holdings.append(matched)

            matched["portfolio"] = new_port
            matched["currency"] = new_curr
            matched["shares"] = shares
            matched["buy_price"] = buy_price
            matched["target_sell_price"] = target_p
            matched["stop_loss_price"] = stop_p

            cur_p = float(matched.get("current_price", buy_price))
            div_y = float(matched.get("dividend_yield", 0.0))
            ann_d = float(matched.get("annual_div_per_share", 0.0))
            summary = calc_holding_summary(shares, buy_price, cur_p, div_y, ann_d)
            matched.update(summary)

            if holding is not matched:
                holding.update(matched)

            save_portfolio(self.all_holdings, PORTFOLIO_CSV)
            self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
            self._on_portfolio_selected()
            self._refresh_holdings_table()
            self._update_metric_cards()
            self._refresh_analytics_tab()
            if hasattr(self, "chart_view"):
                self.chart_view.update_portfolio(self.current_portfolio, self.summary_currency)
            dlg.destroy()
            self._set_status(f"Updated holding {sym} ({new_port}, {new_curr}).")

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(10, 0))

        tk.Button(
            btn_row,
            text=t("btn_save_changes"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=6,
            command=on_save_edit,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        tk.Button(
            btn_row,
            text=t("btn_cancel"),
            font=("Segoe UI", 9),
            bg=self.tab_inactive_bg,
            fg=self.text_dark,
            relief="flat",
            pady=6,
            command=dlg.destroy,
        ).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(4, 0))

        dlg.bind("<Escape>", lambda e: dlg.destroy())

        # Ensure layout is computed, center dialog over parent, and safely focus & grab
        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 440, 480
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _delete_selected_holding(self):
        selected = self.holdings_tree.selection()
        if not selected:
            messagebox.showwarning(t("msg_warning"), t("msg_select_stock"))
            return

        to_remove = []
        for item_id in selected:
            h = self._get_holding_from_tree_item(item_id)
            if h and h not in to_remove:
                to_remove.append(h)

        count = len(to_remove)
        if count == 0:
            return

        names_display = [f"{h.get('symbol')} ({h.get('name', '')})" for h in to_remove]
        msg = t("confirm_delete_holding", sym=', '.join(names_display)) if count <= 3 else t("confirm_delete_holdings_count", count=count)

        if messagebox.askyesno(t("msg_warning"), msg):
            self.all_holdings = [h for h in self.all_holdings if h not in to_remove]
            save_portfolio(self.all_holdings, PORTFOLIO_CSV)
            self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
            self._on_portfolio_selected()
            self._set_status(f"Removed {count} stock(s) from portfolio.")

    def _refresh_selected_quote(self):
        selected = self.holdings_tree.selection()
        if not selected:
            return

        item_id = selected[0]
        holding = self._get_holding_from_tree_item(item_id)
        if not holding:
            return

        sym = holding.get("full_symbol") or holding.get("symbol")
        self._set_status(f"Refreshing quote for {sym}...")

        def worker():
            q = self.fetcher.fetch_quote(sym)
            if q.get("success"):
                holding["current_price"] = q["price"]
                holding["name"] = q.get("name", holding.get("name", sym))
                holding["change"] = q.get("change")
                holding["change_percent"] = q.get("change_percent")
                holding["dividend_yield"] = q.get("dividend_yield", 0.0)
                holding["annual_div_per_share"] = q.get("annual_dividend_per_share", 0.0)
                holding["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                holding.update(calc_holding_summary(holding["shares"], holding["buy_price"], holding["current_price"], holding["dividend_yield"], holding["annual_div_per_share"]))
                save_portfolio(self.all_holdings, PORTFOLIO_CSV)
                self.fetch_queue.put(("REFRESH_DONE", sym))

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------------
    # Navigation to Other Calculators
    # -------------------------------------------------------------
    def _send_selected_to_dividend_calc(self):
        selected = self.holdings_tree.selection()
        if not selected:
            messagebox.showwarning(t("msg_warning"), t("msg_select_stock"))
            return

        item_id = selected[0]
        holding = self._get_holding_from_tree_item(item_id)
        if not holding:
            return

        self.notebook.select(self.tab_dividend)
        self._load_holding_into_dividend_calc(holding)

    def _send_selected_to_split_calc(self):
        selected = self.holdings_tree.selection()
        if not selected:
            messagebox.showwarning(t("msg_warning"), t("msg_select_stock"))
            return

        item_id = selected[0]
        holding = self._get_holding_from_tree_item(item_id)
        if not holding:
            return

        self.notebook.select(self.tab_split)
        self._load_holding_into_split_calc(holding)

    def _send_selected_to_selling_calc(self):
        selected = self.holdings_tree.selection()
        if not selected:
            messagebox.showwarning(t("msg_warning"), t("msg_select_stock"))
            return

        item_id = selected[0]
        holding = self._get_holding_from_tree_item(item_id)
        if not holding:
            return

        self.notebook.select(self.tab_sell)
        self._load_holding_into_selling_calc(holding)

    def _send_selected_to_chart(self):
        selected = self.holdings_tree.selection()
        if not selected:
            messagebox.showwarning(t("msg_warning"), t("msg_select_stock"))
            return

        item_id = selected[0]
        holding = self._get_holding_from_tree_item(item_id)
        if not holding:
            return

        sym = holding.get("symbol", "")
        self.notebook.select(self.tab_chart)
        if hasattr(self, "chart_view"):
            self.chart_view.current_scope = sym
            self.chart_view._populate_scope_dropdown()
            self.chart_view.refresh_chart()

    # -------------------------------------------------------------
    # Dividend & DRIP Calculator Logic
    # -------------------------------------------------------------
    def _on_div_holding_selected(self, event=None):
        val = self.div_holding_var.get()
        sym = val.split()[0] if val else ""
        holding = next((h for h in self.holdings if h["symbol"] == sym), None)
        if holding:
            self._load_holding_into_dividend_calc(holding)

    def _load_holding_into_dividend_calc(self, holding: Dict[str, Any]):
        self.div_inputs["ticker"].delete(0, tk.END)
        self.div_inputs["ticker"].insert(0, holding["symbol"])

        self.div_inputs["shares"].delete(0, tk.END)
        self.div_inputs["shares"].insert(0, str(holding["shares"]))

        self.div_inputs["current_price"].delete(0, tk.END)
        self.div_inputs["current_price"].insert(0, str(holding["current_price"]))

        self.div_inputs["buy_price"].delete(0, tk.END)
        self.div_inputs["buy_price"].insert(0, str(holding["buy_price"]))

        p_date = self._get_holding_purchase_date(holding["symbol"], holding.get("portfolio"))
        if "purchase_date" in self.div_inputs:
            self.div_inputs["purchase_date"].delete(0, tk.END)
            self.div_inputs["purchase_date"].insert(0, p_date)

        self.div_inputs["div_yield"].delete(0, tk.END)
        self.div_inputs["div_yield"].insert(0, str(holding.get("dividend_yield", 0.0)))

        self.div_inputs["div_per_share"].delete(0, tk.END)
        self.div_inputs["div_per_share"].insert(0, str(holding.get("annual_div_per_share", 0.0)))

        self._calc_dividend_results()
        self._calc_drip_results()

    def _calc_dividend_results(self):
        try:
            shares = float(self.div_inputs["shares"].get().strip())
            price = float(self.div_inputs["current_price"].get().strip())
            buy_price = float(self.div_inputs["buy_price"].get().strip())
            div_yield = float(self.div_inputs["div_yield"].get().strip())
            ann_div_str = self.div_inputs["div_per_share"].get().strip()
            ann_div = float(ann_div_str) if ann_div_str else 0.0
            purchase_date_str = self.div_inputs["purchase_date"].get().strip() if "purchase_date" in self.div_inputs else None
        except ValueError:
            messagebox.showerror(t("dlg_error"), t("msg_enter_valid_numbers"))
            return

        # 1. Past Performance from Purchase Day Till Today (Earned Already)
        past = calc_holding_earned_already(shares, buy_price, price, purchase_date_str, ann_div, div_yield)
        if hasattr(self, "div_earned_labels"):
            self.div_earned_labels["cost_basis"].config(text=f"${past['cost_basis']:,.2f}")
            self.div_earned_labels["market_value"].config(text=f"${past['market_value']:,.2f}")
            
            gain_sign = "+" if past["capital_gain"] >= 0 else ""
            gain_fg = self.green_color if past["capital_gain"] >= 0 else self.red_color
            self.div_earned_labels["capital_gain"].config(
                text=f"{gain_sign}${past['capital_gain']:,.2f} ({gain_sign}{past['capital_gain_pct']:.2f}%)",
                fg=gain_fg
            )
            self.div_earned_labels["past_dividends"].config(text=f"${past['past_dividends']:,.2f}")
            
            tot_sign = "+" if past["total_earned_already"] >= 0 else ""
            tot_fg = self.green_color if past["total_earned_already"] >= 0 else self.red_color
            self.div_earned_labels["total_earned"].config(
                text=f"{tot_sign}${past['total_earned_already']:,.2f} ({tot_sign}{past['total_roi_pct']:.2f}%)",
                fg=tot_fg
            )
            self.div_earned_labels["cagr"].config(text=f"{past['cagr_pct']:.2f}% / yr")

        if hasattr(self, "div_holding_days_lbl"):
            self.div_holding_days_lbl.config(text=t("lbl_holding_days_format", days=past['days_held'], years=f"{past['years_held']:.2f}"))

        # 2. Future Milestones (Till Later How Much You Can Earn)
        try:
            div_growth = float(self.drip_div_growth_entry.get().strip())
            price_growth = float(self.drip_price_growth_entry.get().strip())
            monthly_contrib = float(self.drip_monthly_entry.get().strip())
        except (ValueError, AttributeError):
            div_growth, price_growth, monthly_contrib = 5.0, 6.0, 0.0

        fut_res = calc_future_dividend_milestones(
            shares, price, buy_price, div_yield, ann_div, div_growth, price_growth, monthly_contrib, horizons=[1, 3, 5, 10]
        )
        if hasattr(self, "div_milestone_labels"):
            for yr, (lbl_val, lbl_new, lbl_tot) in self.div_milestone_labels.items():
                m = fut_res["milestones"].get(yr)
                if m:
                    lbl_val.config(text=f"${m['portfolio_value']:,.2f}")
                    lbl_new.config(text=f"{t('lbl_future_new_profit')}: +${m['new_profit_from_today']:,.2f}")
                    tot_s = "+" if m["total_profit_from_start"] >= 0 else ""
                    lbl_tot.config(text=f"{t('lbl_future_total_profit')}: {tot_s}${m['total_profit_from_start']:,.2f} ({tot_s}{m['roi_from_start_pct']:.1f}%)")

        # 3. Dividend Projection Cash Flow Summary
        res = calc_dividend_projection(shares, price, div_yield, ann_div, buy_price)
        self.div_results["annual_total"].config(text=f"${res['annual_total']:,.2f}")
        self.div_results["quarterly_total"].config(text=f"${res['quarterly_total']:,.2f}")
        self.div_results["monthly_total"].config(text=f"${res['monthly_total']:,.2f}")
        self.div_results["yield_on_cost"].config(text=f"{res['yield_on_cost']:.2f}%")
        self.div_results["div_per_share"].config(text=f"${res['annual_div_per_share']:.4f}")

    def _calc_drip_results(self):
        try:
            shares = float(self.div_inputs["shares"].get().strip())
            price = float(self.div_inputs["current_price"].get().strip())
            div_yield = float(self.div_inputs["div_yield"].get().strip())
            years = int(self.drip_years_entry.get().strip())
            div_growth = float(self.drip_div_growth_entry.get().strip())
            price_growth = float(self.drip_price_growth_entry.get().strip())
            monthly_contrib = float(self.drip_monthly_entry.get().strip())
        except ValueError:
            messagebox.showerror(t("dlg_error"), t("msg_check_drip_numbers"))
            return

        history = calc_drip_simulation(
            shares,
            price,
            div_yield,
            div_growth,
            price_growth,
            monthly_contrib,
            years,
        )

        for item in self.drip_tree.get_children():
            self.drip_tree.delete(item)

        for row in history:
            self.drip_tree.insert(
                "",
                tk.END,
                values=(
                    f"Yr {row['year']}",
                    f"{row['shares']:.2f}",
                    f"${row['stock_price']:,.2f}",
                    f"${row['annual_dividend']:,.2f}",
                    f"${row['portfolio_value']:,.2f}",
                    f"${row['total_invested']:,.2f}",
                    f"${row['total_profit']:+,.2f}",
                ),
            )

        if hasattr(self, "drip_canvas"):
            draw_drip_growth_chart(self.drip_canvas, history, dark_mode=self.dark_mode)

    # -------------------------------------------------------------
    # Stock Split Logic
    # -------------------------------------------------------------
    def _on_split_holding_selected(self, event=None):
        val = self.split_holding_var.get()
        sym = val.split()[0] if val else ""
        holding = next((h for h in self.holdings if h["symbol"] == sym), None)
        if holding:
            self._load_holding_into_split_calc(holding)

    def _load_holding_into_split_calc(self, holding: Dict[str, Any]):
        self.split_sym_entry.delete(0, tk.END)
        self.split_sym_entry.insert(0, holding["symbol"])

        self.split_shares_entry.delete(0, tk.END)
        self.split_shares_entry.insert(0, str(holding["shares"]))

        self.split_price_entry.delete(0, tk.END)
        self.split_price_entry.insert(0, str(holding["buy_price"]))

        cur_p = holding.get("current_price", holding["buy_price"])
        if hasattr(self, "split_cur_price_entry"):
            self.split_cur_price_entry.delete(0, tk.END)
            self.split_cur_price_entry.insert(0, f"{cur_p:.2f}")

        p_date = self._get_holding_purchase_date(holding["symbol"], holding.get("portfolio"))
        if hasattr(self, "split_purchase_date_entry"):
            self.split_purchase_date_entry.delete(0, tk.END)
            self.split_purchase_date_entry.insert(0, p_date)

        if hasattr(self, "split_target_price_entry"):
            self.split_target_price_entry.delete(0, tk.END)
            self.split_target_price_entry.insert(0, f"{cur_p:.2f}")

        self._calc_split_results()

    def _on_split_preset_selected(self, event=None):
        preset = self.split_preset_var.get()
        mapping = {
            "2:1 Split": (2, 1),
            "3:1 Split": (3, 1),
            "4:1 Split": (4, 1),
            "5:1 Split": (5, 1),
            "10:1 Split": (10, 1),
            "1:5 Reverse Split": (1, 5),
            "1:10 Reverse Split": (1, 10),
        }
        if preset in mapping:
            to_val, from_val = mapping[preset]
            self.split_to_entry.delete(0, tk.END)
            self.split_to_entry.insert(0, str(to_val))
            self.split_from_entry.delete(0, tk.END)
            self.split_from_entry.insert(0, str(from_val))
            self._calc_split_results()

    def _calc_split_results(self):
        try:
            shares = float(self.split_shares_entry.get().strip())
            buy_price = float(self.split_price_entry.get().strip())
            cur_price = float(self.split_cur_price_entry.get().strip()) if hasattr(self, "split_cur_price_entry") else buy_price
            ratio_to = float(self.split_to_entry.get().strip())
            ratio_from = float(self.split_from_entry.get().strip())
            p_date = self.split_purchase_date_entry.get().strip() if hasattr(self, "split_purchase_date_entry") else None
            tgt_p = float(self.split_target_price_entry.get().strip()) if hasattr(self, "split_target_price_entry") and self.split_target_price_entry.get().strip() else 0.0
        except ValueError:
            return

        res = calc_split_future_projections(shares, buy_price, cur_price, ratio_from, ratio_to, p_date, tgt_p)
        self.last_split_result = res

        # 1. Earned Already Card
        if hasattr(self, "split_earned_labels"):
            self.split_earned_labels["cost_basis"].config(text=f"${res['cost_basis']:,.2f}")
            self.split_earned_labels["market_value"].config(text=f"${res['market_value']:,.2f}")
            g_sign = "+" if res["earned_already"] >= 0 else ""
            g_fg = self.green_color if res["earned_already"] >= 0 else self.red_color
            self.split_earned_labels["capital_gain"].config(
                text=f"{g_sign}${res['earned_already']:,.2f} ({g_sign}{res['earned_already_pct']:.2f}%)",
                fg=g_fg
            )
            self.split_earned_labels["holding_period"].config(
                text=t("lbl_holding_days_format", days=res['days_held'], years=f"{res['years_held']:.2f}")
            )
            if hasattr(self, "split_holding_days_lbl"):
                self.split_holding_days_lbl.config(text=t("lbl_holding_days_fmt", days=res['days_held'], years=res['years_held']))

        # 2. Before / After Split Comparison
        if hasattr(self, "split_before_labels"):
            self.split_before_labels["shares"].config(text=f"{res['original_shares']:.4g}")
            self.split_before_labels["price"].config(text=f"${res['original_buy_price']:.2f}")
            if "cur_price" in self.split_before_labels:
                self.split_before_labels["cur_price"].config(text=f"${res['original_current_price']:.2f}")
            self.split_before_labels["total"].config(text=f"${res['cost_basis']:,.2f}")
            if "val" in self.split_before_labels:
                self.split_before_labels["val"].config(text=f"${res['market_value']:,.2f}")

        if hasattr(self, "split_after_labels"):
            self.split_after_labels["shares"].config(text=f"{res['new_shares']:.4g}")
            self.split_after_labels["price"].config(text=f"${res['new_buy_price']:.4f}")
            if "cur_price" in self.split_after_labels:
                self.split_after_labels["cur_price"].config(text=f"${res['new_current_price']:.4f}")
            self.split_after_labels["total"].config(text=f"${res['new_cost_basis']:,.2f}")
            if "val" in self.split_after_labels:
                self.split_after_labels["val"].config(text=f"${res['new_market_value']:,.2f}")

        # 3. Future Potential Earnings Card ("Till later how much you can earn")
        if hasattr(self, "split_future_labels"):
            target_data = res.get("custom_target") or res.get("pre_split_recovery")
            if target_data:
                self.split_future_labels["target_val"].config(
                    text=f"${target_data['future_value']:,.2f} (@ ${target_data['target_price']:.2f})"
                )
                t_sign = "+" if target_data["total_profit_from_start"] >= 0 else ""
                t_fg = self.green_color if target_data["total_profit_from_start"] >= 0 else self.red_color
                self.split_future_labels["total_prof"].config(
                    text=f"{t_sign}${target_data['total_profit_from_start']:,.2f} ({t_sign}{target_data['total_roi_pct']:.1f}%)",
                    fg=t_fg
                )
                n_sign = "+" if target_data["new_profit_from_today"] >= 0 else ""
                n_fg = self.green_color if target_data["new_profit_from_today"] >= 0 else self.red_color
                self.split_future_labels["new_gain"].config(
                    text=f"{n_sign}${target_data['new_profit_from_today']:,.2f}",
                    fg=n_fg
                )

        # Update Scenario Pills in Frame
        if hasattr(self, "split_scenarios_frame"):
            for child in self.split_scenarios_frame.winfo_children():
                child.destroy()
            for sc in res.get("scenarios", []):
                pill = tk.Frame(self.split_scenarios_frame, bg="#f8f9fa", bd=1, relief="solid", padx=6, pady=3)
                pill.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
                tk.Label(pill, text=f"+{sc['growth_pct']:g}% (${sc['future_price']:.2f})", font=("Segoe UI", 8, "bold"), bg="#f8f9fa", fg=self.primary_color).pack(anchor="w")
                tk.Label(pill, text=t("lbl_pill_val", val=sc['future_value']), font=("Segoe UI", 8), bg="#f8f9fa").pack(anchor="w")
                tot_s = "+" if sc["total_profit_from_start"] >= 0 else ""
                tk.Label(pill, text=t("lbl_pill_total", sign=tot_s, amount=sc['total_profit_from_start']), font=("Segoe UI", 7), bg="#f8f9fa", fg=self.green_color).pack(anchor="w")
                new_s = "+" if sc["new_profit_from_today"] >= 0 else ""
                tk.Label(pill, text=t("lbl_pill_new", sign=new_s, amount=sc['new_profit_from_today']), font=("Segoe UI", 7), bg="#f8f9fa", fg=self.text_muted).pack(anchor="w")

    def _apply_split_to_portfolio(self):
        sym = self.split_sym_entry.get().strip().upper()
        holding = next((h for h in self.holdings if h["symbol"] == sym), None)
        if not holding:
            messagebox.showwarning(t("msg_notice"), t("msg_symbol_not_in_portfolio", symbol=sym))
            return

        self._calc_split_results()
        if not hasattr(self, "last_split_result"):
            return

        res = self.last_split_result
        msg = t(
            "msg_confirm_split_text",
            ratio=res['split_ratio'],
            symbol=sym,
            old_shares=f"{res['original_shares']:.4g}",
            old_price=res['original_buy_price'],
            new_shares=f"{res['new_shares']:.4g}",
            new_price=res['new_buy_price'],
        )
        if messagebox.askyesno(t("msg_confirm_split_title"), msg):
            holding["shares"] = res["new_shares"]
            holding["buy_price"] = res["new_buy_price"]
            if res["multiplier"] > 0:
                holding["current_price"] = round(holding["current_price"] / res["multiplier"], 4)

            summary = calc_holding_summary(
                holding["shares"],
                holding["buy_price"],
                holding["current_price"],
                holding.get("dividend_yield", 0.0),
                holding.get("annual_div_per_share", 0.0),
            )
            holding.update(summary)

            save_portfolio(self.all_holdings, PORTFOLIO_CSV)
            self._on_portfolio_selected()
            messagebox.showinfo(t("msg_success"), t("msg_split_success", symbol=sym))
            self._set_status(f"Applied {res['split_ratio']} split to {sym}.")

    # -------------------------------------------------------------
    # Selling & Profit Calculator Logic
    # -------------------------------------------------------------
    def _on_sell_holding_selected(self, event=None):
        val = self.sell_holding_var.get()
        sym = val.split()[0] if val else ""
        holding = next((h for h in self.holdings if h["symbol"] == sym), None)
        if holding:
            self._load_holding_into_selling_calc(holding)

    def _load_holding_into_selling_calc(self, holding: Dict[str, Any]):
        self.sell_inputs["symbol"].delete(0, tk.END)
        self.sell_inputs["symbol"].insert(0, holding["symbol"])

        self.sell_inputs["shares_to_sell"].delete(0, tk.END)
        self.sell_inputs["shares_to_sell"].insert(0, str(holding["shares"]))

        self.sell_inputs["buy_price"].delete(0, tk.END)
        self.sell_inputs["buy_price"].insert(0, str(holding["buy_price"]))

        self.sell_inputs["sell_price"].delete(0, tk.END)
        self.sell_inputs["sell_price"].insert(0, str(holding["current_price"]))

        # Load portfolio fee config
        p_name = holding.get("portfolio") or self.current_portfolio
        fee_cfg = get_portfolio_fee_config(p_name)
        if "commission_flat" in self.sell_inputs:
            self.sell_inputs["commission_flat"].delete(0, tk.END)
            self.sell_inputs["commission_flat"].insert(0, str(fee_cfg.get("commission_flat", 0.0)))
        if "commission_pct" in self.sell_inputs:
            self.sell_inputs["commission_pct"].delete(0, tk.END)
            self.sell_inputs["commission_pct"].insert(0, str(fee_cfg.get("commission_pct", 0.0)))
        if hasattr(self, "sell_tax_entry") and "tax_rate" in fee_cfg:
            self.sell_tax_entry.delete(0, tk.END)
            self.sell_tax_entry.insert(0, str(fee_cfg.get("tax_rate", 0.0)))

        self._calc_selling_results()

    def _apply_sell_percentage(self, pct: int):
        sym = self.sell_inputs["symbol"].get().strip().upper()
        holding = next((h for h in self.holdings if h["symbol"] == sym), None)
        if holding:
            shares = round(holding["shares"] * (pct / 100.0), 4)
            self.sell_inputs["shares_to_sell"].delete(0, tk.END)
            self.sell_inputs["shares_to_sell"].insert(0, str(shares))
            self._calc_selling_results()

    def _on_tax_preset_changed(self, event=None):
        val = self.tax_bracket_var.get()
        mapping = {
            "0% (Tax-Exempt / IRA)": 0.0,
            "15% Long-Term": 15.0,
            "20% Long-Term (High)": 20.0,
            "28% Short-Term": 28.0,
        }
        if val in mapping:
            self.sell_tax_entry.delete(0, tk.END)
            self.sell_tax_entry.insert(0, str(mapping[val]))
            self._calc_selling_results()

    def _calc_selling_results(self):
        try:
            sym = self.sell_inputs["symbol"].get().strip().upper()
            shares = float(self.sell_inputs["shares_to_sell"].get().strip())
            buy_p = float(self.sell_inputs["buy_price"].get().strip())
            sell_p = float(self.sell_inputs["sell_price"].get().strip())
            comm_flat = float(self.sell_inputs["commission_flat"].get().strip())
            comm_pct = float(self.sell_inputs["commission_pct"].get().strip())
            tax_rate = float(self.sell_tax_entry.get().strip())
        except ValueError:
            return

        holding = next((h for h in self.holdings if h["symbol"] == sym), None)
        p_name = holding.get("portfolio") if holding else self.current_portfolio
        fee_cfg = get_portfolio_fee_config(p_name)
        comm_min = float(fee_cfg.get("min_commission", 0.0) or 0.0)

        # Tax lot calculation (ACB, FIFO, or Specific Identification)
        method = self.tax_lot_var.get().strip().upper() if hasattr(self, "tax_lot_var") else "ACB"
        all_tx = load_transactions(TRANSACTION_HISTORY_CSV)
        buy_lots = [
            {"shares": float(tx.get("shares", 0.0) or 0.0), "price": float(tx.get("price", 0.0) or 0.0), "date": tx.get("date", "")}
            for tx in all_tx
            if str(tx.get("symbol", "")).strip().upper() == sym and str(tx.get("type", "")).strip().upper() in ("BUY", "DRIP")
        ]
        if not buy_lots and buy_p > 0:
            buy_lots = [{"shares": shares, "price": buy_p, "date": "Original"}]

        lot_calc = calc_tax_lot_proceeds(shares, sell_p, buy_lots, method=method)
        effective_cb = lot_calc.get("cost_basis_sold", shares * buy_p)
        effective_buy_p = (effective_cb / shares) if shares > 0 else buy_p

        res = calc_selling_proceeds(shares, effective_buy_p, sell_p, comm_flat, comm_pct, tax_rate, commission_min=comm_min)
        res["symbol"] = sym
        res["tax_method"] = method
        self.last_selling_result = res

        self.sell_results["gross_proceeds"].config(text=f"${res['gross_proceeds']:,.2f}")
        self.sell_results["cost_basis"].config(text=f"${res['cost_basis']:,.2f}")
        self.sell_results["commission_fee"].config(text=f"-${res['commission_fee']:,.2f}")

        gain_col = self.green_color if res["gross_gain"] >= 0 else self.red_color
        self.sell_results["gross_gain"].config(text=f"${res['gross_gain']:+,.2f}", fg=gain_col)
        self.sell_results["estimated_tax"].config(text=f"-${res['estimated_tax']:,.2f}")
        self.sell_results["net_proceeds"].config(text=f"${res['net_proceeds']:,.2f}")

        prof_col = self.green_color if res["net_profit"] >= 0 else self.red_color
        self.sell_results["net_profit"].config(text=f"${res['net_profit']:+,.2f}", fg=prof_col)
        self.sell_results["net_roi_pct"].config(text=f"{res['net_roi_pct']:+.2f}%", fg=prof_col)

        be_price = calc_breakeven_sell_price(shares, buy_p, comm_flat, comm_pct)
        self.lbl_breakeven.config(text=f"${be_price:.2f}")

    def _calc_target_sell_price(self):
        try:
            shares = float(self.sell_inputs["shares_to_sell"].get().strip())
            buy_p = float(self.sell_inputs["buy_price"].get().strip())
            comm_flat = float(self.sell_inputs["commission_flat"].get().strip())
            comm_pct = float(self.sell_inputs["commission_pct"].get().strip())
            tax_rate = float(self.sell_tax_entry.get().strip())
            target_profit = float(self.target_profit_entry.get().strip())
        except ValueError:
            messagebox.showerror(t("dlg_error"), t("msg_enter_valid_numbers"))
            return

        res = calc_target_profit_sell_price(
            shares,
            buy_p,
            target_profit_dollars=target_profit,
            commission_flat=comm_flat,
            commission_pct=comm_pct,
            tax_rate_pct=tax_rate,
        )
        self.lbl_target_price_res.config(
            text=t("lbl_need_to_sell_at", price=res['target_sell_price'], proceeds=res['gross_proceeds_at_target'])
        )

    def _execute_and_record_sale(self):
        self._calc_selling_results()
        if not hasattr(self, "last_selling_result"):
            return

        res = self.last_selling_result
        sym = res["symbol"]
        shares_to_sell = res["shares_to_sell"]

        holding = next((h for h in self.holdings if h["symbol"] == sym), None)
        if holding and shares_to_sell > holding["shares"]:
            messagebox.showerror(t("msg_error"), t("msg_cannot_sell_more", sell_shares=shares_to_sell, hold_shares=holding["shares"]))
            return

        confirm_msg = t(
            "msg_confirm_sale_text",
            shares=shares_to_sell,
            symbol=sym,
            price=res['sell_price'],
            gross=res['gross_proceeds'],
            comm=res['commission_fee'],
            tax=res['estimated_tax'],
            profit=res['net_profit'],
            roi=res['net_roi_pct'],
        )
        if not messagebox.askyesno(t("msg_confirm_sale_title"), confirm_msg):
            return

        res["portfolio"] = holding.get("portfolio", self.current_portfolio) if holding else (self.current_portfolio if self.current_portfolio != "All Portfolios (Consolidated)" else DEFAULT_PORTFOLIO_NAME)
        res["currency"] = holding.get("currency", "USD") if holding else "USD"
        sell_tx = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "SELL",
            "portfolio": res["portfolio"],
            "symbol": sym,
            "shares": shares_to_sell,
            "price": res["sell_price"],
            "total_amount": res["gross_proceeds"],
            "cost_basis": res["cost_basis"],
            "commission_fee": res["commission_fee"],
            "estimated_tax": res["estimated_tax"],
            "net_amount": res["net_proceeds"],
            "net_profit": res["net_profit"],
            "net_roi_pct": res["net_roi_pct"],
            "currency": res["currency"],
            "notes": "Sold via Selling Calculator",
        }
        append_transaction(sell_tx, TRANSACTION_HISTORY_CSV)
        self.transactions = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=self.current_portfolio if self.current_portfolio != "All Portfolios (Consolidated)" else None)
        self.sales_history = self.transactions
        self._refresh_sales_table()

        if holding:
            remaining_shares = round(holding["shares"] - shares_to_sell, 6)
            if remaining_shares <= 0.0001:
                self.all_holdings = [h for h in self.all_holdings if h is not holding]
                self._set_status(f"Closed entire position in {sym}.")
            else:
                holding["shares"] = remaining_shares
                summary = calc_holding_summary(
                    holding["shares"],
                    holding["buy_price"],
                    holding["current_price"],
                    holding.get("dividend_yield", 0.0),
                    holding.get("annual_div_per_share", 0.0),
                )
                holding.update(summary)
                self._set_status(f"Sold {shares_to_sell} shares of {sym}. Remaining: {remaining_shares:.4g}")

            save_portfolio(self.all_holdings, PORTFOLIO_CSV)
            self._on_portfolio_selected()

        messagebox.showinfo(t("msg_sale_recorded_title"), t("msg_sale_recorded_text"))

    # -------------------------------------------------------------
    # Background Auto-Receive & Fetching
    # -------------------------------------------------------------
    def _schedule_auto_refresh(self):
        if self.auto_refresh_job:
            try:
                self.root.after_cancel(self.auto_refresh_job)
            except Exception:
                pass
            self.auto_refresh_job = None

        if getattr(self, "is_running", True) and self.auto_refresh_enabled and self.refresh_interval_sec > 0:
            try:
                if self.root.winfo_exists():
                    ms = self.refresh_interval_sec * 1000
                    self.auto_refresh_job = self.root.after(ms, self._on_auto_refresh_timer)
            except Exception:
                pass

    def _on_auto_refresh_timer(self):
        if not getattr(self, "is_running", True):
            return
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return

        if self.auto_refresh_enabled and not self.is_fetching and (self.holdings or load_watchlist()):
            self.fetch_all_quotes()
        self._schedule_auto_refresh()

    def _on_interval_changed(self, event=None):
        val = self.interval_var.get()
        mapping = {
            "Off": 0,
            "15s": 15,
            "30s": 30,
            "1 min": 60,
            "2 min": 120,
            "5 min": 300,
        }
        sec = mapping.get(val, 300)
        self.saved_refresh_interval = val
        save_settings({"auto_refresh_interval": val})
        if sec == 0:
            self.auto_refresh_enabled = False
            self.refresh_interval_sec = 0
            self._set_status(f"Auto-receive paused ({val}).")
        else:
            self.auto_refresh_enabled = True
            self.refresh_interval_sec = sec
            self._set_status(f"Auto-receive active ({val} interval).")
        self._schedule_auto_refresh()

    def fetch_all_quotes(self):
        if getattr(self, "is_fetching", False):
            return

        hold_symbols = {h["symbol"].strip().upper() for h in self.all_holdings if h.get("symbol")}
        watch_symbols = {w.get("symbol", "").strip().upper() for w in load_watchlist() if w.get("symbol")}
        symbols = sorted(list(hold_symbols | watch_symbols))
        if not symbols:
            return

        self.is_fetching = True
        self._set_status(f"🔄 {t('msg_cached_data_notice', default='Showing cached data. Updating live quotes & statistics in background...')} (0/{len(symbols)})")
        if hasattr(self, "_refresh_watchlist_tab") and hasattr(self, "notebook") and hasattr(self, "tab_watchlist"):
            try:
                if self.notebook.select() == str(self.tab_watchlist):
                    self._refresh_watchlist_tab()
            except Exception:
                pass

        def worker():
            results = []
            tot = len(symbols)
            for idx, sym in enumerate(symbols, 1):
                if not getattr(self, "is_running", True):
                    return
                try:
                    quote = self.fetcher.fetch_quote(sym)
                except Exception as e:
                    quote = {"symbol": sym, "success": False, "error": str(e)}
                if not getattr(self, "is_running", True):
                    return
                results.append((sym, quote))
                self.fetch_queue.put(("STREAM_QUOTE", (sym, quote, idx, tot)))
                time.sleep(0.15)  # Single-thread respectful delay to avoid session bursts & blocking

            if getattr(self, "is_running", True):
                self.fetch_queue.put(("ALL_QUOTES", results))

        th = threading.Thread(target=worker, daemon=True)
        th.start()

    def _process_fetch_queue(self):
        if not getattr(self, "is_running", True):
            return
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return

        try:
            while True:
                msg_type, data = self.fetch_queue.get_nowait()
                if msg_type == "STREAM_QUOTE":
                    sym, quote, idx, tot = data
                    self._handle_stream_quote(sym, quote, idx, tot)
                elif msg_type == "ALL_QUOTES":
                    self._handle_all_quotes_result(data)
                elif msg_type == "REFRESH_DONE":
                    self._refresh_holdings_table()
                    self._update_metric_cards()
                    self._set_status(f"Updated quote for {data}.")
        except queue.Empty:
            pass
        except Exception:
            pass

        if getattr(self, "is_running", True):
            try:
                if self.root.winfo_exists():
                    self.queue_job = self.root.after(100, self._process_fetch_queue)
            except Exception:
                pass

    def _update_watchlist_row_in_place(self, sym_clean: str, quote: Dict[str, Any]) -> bool:
        if not hasattr(self, "watchlist_tree"):
            return False
        item_id = f"wl_{sym_clean}"
        raw_children = self.watchlist_tree.get_children()
        children = set(raw_children) if isinstance(raw_children, (list, tuple, set)) else set()
        if item_id not in children:
            return False

        try:
            vals = list(self.watchlist_tree.item(item_id, "values"))
            if not vals or len(vals) < 15:
                return False

            q_name = quote.get("name")
            if q_name and (not vals[1] or str(vals[1]).strip().upper() == sym_clean) and q_name.strip().upper() != sym_clean:
                vals[1] = q_name.strip()

            price = float(quote.get("price", 0.0) or 0.0)
            if price > 0:
                vals[3] = f"${price:.2f}"

            tgt_str = str(vals[5]).replace("$", "").replace(",", "").strip()
            try:
                tgt = float(tgt_str) if tgt_str and tgt_str != "-" else 0.0
            except ValueError:
                tgt = 0.0

            tag = "normal"
            if price > 0 and tgt > 0:
                diff_pct = ((price - tgt) / tgt) * 100.0
                vals[6] = f"{diff_pct:+.2f}%"
                if price <= tgt:
                    vals[10] = t("status_target_reached")
                    tag = "reached"
                else:
                    vals[10] = t("status_monitoring")
                    tag = "above"
            elif tgt > 0:
                vals[10] = t("status_monitoring")

            day_change_pct = quote.get("change_percent") or quote.get("change_pct")
            if day_change_pct is not None:
                try:
                    vals[4] = f"{float(day_change_pct):+.2f}%"
                except Exception:
                    vals[4] = str(day_change_pct)

            pe_val = quote.get("pe_ratio")
            if pe_val is not None:
                try:
                    vals[7] = f"{float(pe_val):.1f}"
                except Exception:
                    pass

            div_yield_val = quote.get("dividend_yield")
            if div_yield_val is not None and float(div_yield_val) > 0:
                try:
                    vals[9] = f"{float(div_yield_val):.2f}%"
                except Exception:
                    pass

            h52 = quote.get("52_week_high")
            l52 = quote.get("52_week_low")
            if h52 is not None and l52 is not None:
                try:
                    vals[8] = f"${float(l52):.2f} - ${float(h52):.2f}"
                except Exception:
                    pass

            if quote.get("currency"):
                vals[11] = str(quote["currency"]).strip().upper()

            now_str = quote.get("last_updated") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            vals[12] = now_str

            self.watchlist_tree.item(item_id, values=tuple(vals), tags=(tag,))

            if hasattr(self, "watch_stats_frame"):
                sel = self.watchlist_tree.selection()
                if item_id in sel:
                    self._update_watchlist_stats_panel()
            return True
        except Exception:
            return False

    def _schedule_watchlist_tab_refresh(self):
        if getattr(self, "_wl_refresh_scheduled", False):
            return
        self._wl_refresh_scheduled = True
        try:
            self.root.after(300, self._run_scheduled_watchlist_tab_refresh)
        except Exception:
            self._wl_refresh_scheduled = False

    def _run_scheduled_watchlist_tab_refresh(self):
        self._wl_refresh_scheduled = False
        if hasattr(self, "notebook") and hasattr(self, "tab_watchlist"):
            try:
                if self.notebook.select() == str(self.tab_watchlist):
                    self._refresh_watchlist_tab()
            except Exception:
                pass

    def _update_holdings_row_in_place(self, sym_clean: str, quote: Dict[str, Any]):
        if not hasattr(self, "holdings_tree") or not hasattr(self, "holding_map"):
            return
        price = float(quote.get("price", 0.0) or 0.0)
        if price <= 0:
            return

        for sid in self.holdings_tree.get_children():
            h = self.holding_map.get(sid)
            if not h:
                continue
            cur_sym = str(h.get("symbol", "")).strip().upper()
            if cur_sym != sym_clean:
                continue

            vals = list(self.holdings_tree.item(sid, "values"))
            if not vals or len(vals) < 17:
                continue

            h["current_price"] = price
            if quote.get("name"):
                h["name"] = quote["name"]
                vals[2] = quote["name"]
            h["change"] = quote.get("change")
            h["change_percent"] = quote.get("change_percent")
            if quote.get("dividend_yield") is not None:
                h["dividend_yield"] = quote["dividend_yield"]
            if quote.get("annual_dividend_per_share") is not None:
                h["annual_div_per_share"] = quote["annual_dividend_per_share"]

            summary = calc_holding_summary(
                h["shares"],
                h["buy_price"],
                price,
                h.get("dividend_yield", 0.0),
                h.get("annual_div_per_share", 0.0),
            )
            h.update(summary)

            shares = float(h.get("shares", 0.0))
            buy_price = float(h.get("buy_price", 0.0))
            cost_basis = float(h.get("cost_basis", 0.0))
            market_value = float(h.get("market_value", 0.0))
            unrealized = float(h.get("unrealized_gain", 0.0))
            unrealized_pct = float(h.get("unrealized_gain_pct", 0.0))
            curr = h.get("currency", "USD").strip().upper() or "USD"
            sym_char = self.converter.CURRENCY_SYMBOLS.get(curr, "$")
            unreal_sign = "+" if unrealized >= 0 else "-"

            chg = h.get("change")
            chg_pct = h.get("change_percent")
            if chg is not None and chg_pct is not None:
                c_val = float(chg)
                c_sign = "+" if c_val >= 0 else "-"
                chg_str = f"{c_sign}{sym_char}{abs(c_val):.2f} ({float(chg_pct):+.2f}%)"
            elif chg is not None:
                c_val = float(chg)
                c_sign = "+" if c_val >= 0 else "-"
                chg_str = f"{c_sign}{sym_char}{abs(c_val):.2f}"
            elif chg_pct is not None:
                chg_str = f"{float(chg_pct):+.2f}%"
            else:
                chg_str = "-"

            vals[6] = f"{sym_char}{price:.2f}"
            vals[7] = chg_str
            vals[8] = f"{sym_char}{market_value:,.2f}"
            vals[9] = f"{sym_char}{cost_basis:,.2f}"
            vals[10] = f"{unreal_sign}{sym_char}{abs(unrealized):,.2f}"
            vals[11] = f"{unrealized_pct:+.2f}%"
            vals[14] = f"{float(h.get('dividend_yield', 0.0)):.2f}%"
            vals[15] = f"{sym_char}{float(h.get('annual_dividend', 0.0)):,.2f}"
            vals[16] = h.get("last_updated", "")

            tag = "positive" if unrealized > 0 else ("negative" if unrealized < 0 else "neutral")
            row_tags = [tag]
            target_p = float(h.get("target_sell_price") or 0.0)
            stop_loss = float(h.get("stop_loss_price") or 0.0)
            if stop_loss > 0 and price <= stop_loss:
                row_tags.append("stop_loss_alert")
            elif target_p > 0 and price >= target_p:
                row_tags.append("target_sell_alert")

            self.holdings_tree.item(sid, values=tuple(vals), tags=tuple(row_tags))

    def _handle_stream_quote(self, sym: str, quote: Dict[str, Any], idx: int, tot: int):
        sym_clean = sym.strip().upper()
        if quote.get("success"):
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            quote["last_updated"] = quote.get("last_updated") or now_str
            if not hasattr(self, "_watchlist_quotes_cache"):
                self._watchlist_quotes_cache = {}
            self._watchlist_quotes_cache[sym_clean] = quote

            for h in self.all_holdings:
                if str(h.get("symbol", "")).strip().upper() == sym_clean:
                    h["current_price"] = quote["price"]
                    h["name"] = quote.get("name") or h.get("name", sym)
                    h["change"] = quote.get("change")
                    h["change_percent"] = quote.get("change_percent")
                    h["dividend_yield"] = quote.get("dividend_yield", 0.0)
                    h["annual_div_per_share"] = quote.get("annual_dividend_per_share", 0.0)
                    if quote.get("currency") and not h.get("currency"):
                        h["currency"] = quote["currency"]
                    h["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 1. Update Watchlist row in-place (preserves selection and eliminates UI churn)
            if hasattr(self, "notebook") and hasattr(self, "tab_watchlist"):
                try:
                    if self.notebook.select() == str(self.tab_watchlist):
                        updated = self._update_watchlist_row_in_place(sym_clean, quote)
                        if not updated:
                            self._schedule_watchlist_tab_refresh()
                except Exception:
                    pass

            # 2. Update Holdings row in-place (preserves selection and live-updates prices)
            if hasattr(self, "holdings_tree"):
                try:
                    self._update_holdings_row_in_place(sym_clean, quote)
                except Exception:
                    pass

        self._set_status(f"🔄 {t('msg_updating_background', default='Updating live quotes & statistics in background...')} ({idx}/{tot}): {sym}")

    def _handle_all_quotes_result(self, results):
        if not getattr(self, "is_running", True):
            return
        self.is_fetching = False
        updated_count = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Keep in-memory holdings in sync with any manual or external edits in portfolio.csv
        try:
            disk_holdings = load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
            disk_map = {(str(d.get("portfolio", "")).strip(), str(d.get("symbol", "")).strip().upper()): d for d in disk_holdings}
            for h in self.all_holdings:
                k = (str(h.get("portfolio", "")).strip(), str(h.get("symbol", "")).strip().upper())
                if k in disk_map:
                    d = disk_map[k]
                    d_bp = float(d.get("buy_price", 0.0) or 0.0)
                    h_bp = float(h.get("buy_price", 0.0) or 0.0)
                    if abs(d_bp - h_bp) > 0.0001 and d_bp > 0:
                        h["buy_price"] = d_bp
                    d_sh = float(d.get("shares", 0.0) or 0.0)
                    h_sh = float(h.get("shares", 0.0) or 0.0)
                    if abs(d_sh - h_sh) > 0.0001 and d_sh > 0:
                        h["shares"] = d_sh
        except Exception:
            pass

        if not hasattr(self, "_watchlist_quotes_cache"):
            self._watchlist_quotes_cache = {}

        for sym, quote in results:
            sym_clean = sym.strip().upper()
            if quote.get("success"):
                updated_count += 1
                quote["last_updated"] = quote.get("last_updated") or now_str
                self._watchlist_quotes_cache[sym_clean] = quote
                for h in self.all_holdings:
                    if str(h.get("symbol", "")).strip().upper() == sym_clean:
                        price = quote["price"]
                        h["current_price"] = price
                        h["name"] = quote.get("name") or h.get("name", sym)
                        h["change"] = quote.get("change")
                        h["change_percent"] = quote.get("change_percent")
                        h["dividend_yield"] = quote.get("dividend_yield", 0.0)
                        h["annual_div_per_share"] = quote.get("annual_dividend_per_share", 0.0)
                        if quote.get("currency") and not h.get("currency"):
                            h["currency"] = quote["currency"]
                        h["last_updated"] = now_str

                        summary = calc_holding_summary(
                            h["shares"],
                            h["buy_price"],
                            price,
                            h["dividend_yield"],
                            h["annual_div_per_share"],
                        )
                        h.update(summary)
            else:
                self._network_errors.append({
                    "time": now_str,
                    "symbol": sym,
                    "error": quote.get("error", "No data returned"),
                    "type": "Quote Fetch",
                })

        save_portfolio(self.all_holdings, PORTFOLIO_CSV)
        save_watchlist_quotes_cache(self._watchlist_quotes_cache)

        # Update watchlist items with resolved company names & currencies
        try:
            w_items = load_watchlist(WATCHLIST_CSV)
            w_updated = False
            for sym, quote in results:
                if not quote.get("success"):
                    continue
                q_name = str(quote.get("name", "")).strip()
                q_curr = str(quote.get("currency", "")).strip()
                sym_clean = sym.strip().upper()
                for w in w_items:
                    if str(w.get("symbol", "")).strip().upper() == sym_clean:
                        curr_w_name = str(w.get("name", "")).strip()
                        if q_name and (not curr_w_name or curr_w_name.upper() == sym_clean) and q_name.upper() != sym_clean:
                            w["name"] = q_name
                            w_updated = True
                        if q_curr and (not w.get("currency") or w.get("currency") == "USD"):
                            w["currency"] = q_curr
                            w_updated = True
            if w_updated:
                save_watchlist(w_items, WATCHLIST_CSV)
        except Exception:
            pass

        self._on_portfolio_selected()
        if hasattr(self, "_refresh_watchlist_tab"):
            self._refresh_watchlist_tab()
        self._update_network_status_badge()

        self._set_status(f"✅ {t('msg_update_completed')} ({updated_count}/{len(results)}) at {now_str}")
        self.lbl_time.config(text=t("last_sync", time=now_str))

    def _set_status(self, text: str):
        self.lbl_status.config(text=text)

    # -------------------------------------------------------------
    # Tables and Dropdowns Sync
    # -------------------------------------------------------------
    def _refresh_holdings_table(self):
        selected_keys = set()
        if hasattr(self, "holdings_tree"):
            try:
                for sid in self.holdings_tree.selection():
                    vals = self.holdings_tree.item(sid, "values")
                    if vals and len(vals) >= 2:
                        p_val = str(vals[0]).strip()
                        s_val = vals[1].replace("🎯 ", "").replace("⚠️ ", "").strip().upper()
                        selected_keys.add((p_val, s_val))
            except Exception:
                pass

            for item in self.holdings_tree.get_children():
                self.holdings_tree.delete(item)

        search_query = self.search_filter_var.get().strip().lower() if hasattr(self, "search_filter_var") else ""
        perf_filter = getattr(self, "filter_performance", "All")

        self.holding_map = {}
        displayed_count = 0

        for idx, h in enumerate(self.holdings):
            shares = float(h.get("shares", 0.0))
            buy_price = float(h.get("buy_price", 0.0))
            current_price = float(h.get("current_price", buy_price))

            cost_basis = float(h.get("cost_basis", 0.0))
            if cost_basis <= 0.0 and shares > 0 and buy_price > 0:
                cost_basis = round(shares * buy_price, 2)
                h["cost_basis"] = cost_basis

            market_value = float(h.get("market_value", 0.0))
            if market_value <= 0.0 and shares > 0 and current_price > 0:
                market_value = round(shares * current_price, 2)
                h["market_value"] = market_value

            unrealized = float(h.get("unrealized_gain", 0.0))
            if unrealized == 0.0 and market_value != cost_basis:
                unrealized = round(market_value - cost_basis, 2)
                h["unrealized_gain"] = unrealized

            unrealized_pct = float(h.get("unrealized_gain_pct", 0.0))
            if unrealized_pct == 0.0 and cost_basis > 0 and unrealized != 0.0:
                unrealized_pct = round((unrealized / cost_basis * 100), 2)
                h["unrealized_gain_pct"] = unrealized_pct

            # Apply performance filter
            if perf_filter == "Gainers" and unrealized < 0:
                continue
            elif perf_filter == "Losers" and unrealized > 0:
                continue

            # Apply search filter
            sym = str(h.get("symbol", ""))
            name = str(h.get("name", ""))
            port = str(h.get("portfolio", self.current_portfolio))
            if search_query:
                if search_query not in sym.lower() and search_query not in name.lower() and search_query not in port.lower():
                    continue

            item_id = f"holding_item_{idx}"
            self.holding_map[item_id] = h
            displayed_count += 1

            tag = "positive" if unrealized > 0 else ("negative" if unrealized < 0 else "neutral")

            curr = h.get("currency", "USD").strip().upper() or "USD"
            sym_char = self.converter.CURRENCY_SYMBOLS.get(curr, "$")
            unreal_sign = "+" if unrealized >= 0 else "-"

            chg = h.get("change")
            chg_pct = h.get("change_percent")
            if chg is not None and chg_pct is not None:
                c_val = float(chg)
                c_sign = "+" if c_val >= 0 else "-"
                chg_str = f"{c_sign}{sym_char}{abs(c_val):.2f} ({float(chg_pct):+.2f}%)"
            elif chg is not None:
                c_val = float(chg)
                c_sign = "+" if c_val >= 0 else "-"
                chg_str = f"{c_sign}{sym_char}{abs(c_val):.2f}"
            elif chg_pct is not None:
                chg_str = f"{float(chg_pct):+.2f}%"
            else:
                chg_str = "-"

            # Target alert indicators and audio alerts
            target_p = float(h.get("target_sell_price") or 0.0)
            stop_loss = float(h.get("stop_loss_price") or 0.0)
            alert_prefix = ""
            if target_p > 0 and current_price >= target_p:
                alert_prefix = "🎯 "
                if (sym, "target") not in getattr(self, "_triggered_alerts", set()):
                    self._triggered_alerts.add((sym, "target"))
                    try:
                        self.root.bell()
                    except Exception:
                        pass
                    self._show_alert_banner(t("alert_target_reached", symbol=sym, price=current_price, target=target_p))
            elif stop_loss > 0 and current_price <= stop_loss:
                alert_prefix = "⚠️ "
                if (sym, "stop") not in getattr(self, "_triggered_alerts", set()):
                    self._triggered_alerts.add((sym, "stop"))
                    try:
                        self.root.bell()
                    except Exception:
                        pass
                    self._show_alert_banner(t("alert_stop_loss", symbol=sym, price=current_price, stop=stop_loss))

            sl_str = f"{sym_char}{stop_loss:.2f}" if stop_loss > 0 else "-"
            tp_str = f"{sym_char}{target_p:.2f}" if target_p > 0 else "-"
            row_tags = [tag]
            if stop_loss > 0 and current_price <= stop_loss:
                row_tags.append("stop_loss_alert")
            elif target_p > 0 and current_price >= target_p:
                row_tags.append("target_sell_alert")

            self.holdings_tree.insert(
                "",
                tk.END,
                iid=item_id,
                values=(
                    port,
                    alert_prefix + sym,
                    name,
                    curr,
                    f"{shares:.4g}",
                    f"{sym_char}{buy_price:.2f}",
                    f"{sym_char}{current_price:.2f}",
                    chg_str,
                    f"{sym_char}{market_value:,.2f}",
                    f"{sym_char}{cost_basis:,.2f}",
                    f"{unreal_sign}{sym_char}{abs(unrealized):,.2f}",
                    f"{unrealized_pct:+.2f}%",
                    sl_str,
                    tp_str,
                    f"{float(h.get('dividend_yield', 0.0)):.2f}%",
                    f"{sym_char}{float(h.get('annual_dividend', 0.0)):,.2f}",
                    h.get("last_updated", ""),
                ),
                tags=tuple(row_tags),
            )

        # Restore selection
        if hasattr(self, "holdings_tree") and selected_keys:
            to_select = []
            try:
                for sid in self.holdings_tree.get_children():
                    vals = self.holdings_tree.item(sid, "values")
                    if vals and len(vals) >= 2:
                        p_val = str(vals[0]).strip()
                        s_val = vals[1].replace("🎯 ", "").replace("⚠️ ", "").strip().upper()
                        if (p_val, s_val) in selected_keys:
                            to_select.append(sid)
                if to_select:
                    self.holdings_tree.selection_set(to_select)
            except Exception:
                pass

        if hasattr(self, "lbl_holdings_count"):
            self.lbl_holdings_count.config(
                text=t("showing_holdings", shown=displayed_count, total=len(self.holdings))
            )

    def _refresh_sales_table(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        filter_sel = self.sales_filter_var.get() if hasattr(self, "sales_filter_var") else "All Portfolios (Consolidated)"
        type_filter_val = self.tx_type_filter_var.get() if hasattr(self, "tx_type_filter_var") else "All Types"
        target_curr = self.summary_currency if hasattr(self, "summary_currency") else "USD"

        # Determine portfolio filter
        is_all_p = (
            filter_sel in ("All Portfolios (Consolidated)", "All Portfolios", "All", "*",
                           t("portfolio_all_consolidated"), t("portfolio_all_plain"))
            or "consolidated" in filter_sel.lower()
            or "合併" in filter_sel
            or "合并" in filter_sel
        )
        port_param = None if is_all_p else filter_sel

        # Determine type filter
        if "BUY" in type_filter_val.upper() or "買入" in type_filter_val or "买入" in type_filter_val:
            type_param = "BUY"
        elif "SELL" in type_filter_val.upper() or "賣出" in type_filter_val or "卖出" in type_filter_val:
            type_param = "SELL"
        else:
            type_param = None

        all_txs = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=None, tx_type=None)
        displayed_txs = []
        for idx, tx in enumerate(all_txs):
            port = tx.get("portfolio", "")
            if not is_all_p and port != port_param:
                continue
            t_type = str(tx.get("type", "BUY")).strip().upper()
            if type_param and type_param not in t_type:
                continue
            displayed_txs.append((idx, tx))

        search_query = self.hist_search_var.get().strip().lower() if hasattr(self, "hist_search_var") else ""
        if search_query:
            filtered = []
            for idx, tx in displayed_txs:
                sym = str(tx.get("symbol", "")).lower()
                typ = str(tx.get("type", "")).lower()
                notes = str(tx.get("notes", "")).lower()
                port = str(tx.get("portfolio", "")).lower()
                curr = str(tx.get("currency", "")).lower()
                if (search_query in sym or search_query in typ or search_query in notes
                        or search_query in port or search_query in curr):
                    filtered.append((idx, tx))
            displayed_txs = filtered

        if hasattr(self, "hist_sort_col") and self.hist_sort_col:
            col = self.hist_sort_col
            numeric_cols = {
                "shares", "price", "total_amount", "commission",
                "commission_fee", "tax", "estimated_tax", "net_profit", "roi", "net_roi_pct"
            }
            col_map = {
                "commission": "commission_fee",
                "tax": "estimated_tax",
                "roi": "net_roi_pct",
            }
            lookup_key = col_map.get(col, col)

            def get_sort_val(tx_tuple):
                _, tx = tx_tuple
                val = tx.get(lookup_key)
                if col in numeric_cols:
                    try:
                        return float(val if val is not None else 0.0)
                    except (ValueError, TypeError):
                        return 0.0
                return str(val or "").lower()

            displayed_txs.sort(key=get_sort_val, reverse=getattr(self, "hist_sort_reverse", False))

        self.transactions = [t for _, t in displayed_txs]
        self.sales_history = [t for _, t in displayed_txs if t.get("type", "BUY") == "SELL"]

        total_profit_target = 0.0
        buy_count = 0
        sell_count = 0

        if not displayed_txs:
            total_across = len(all_txs)
            self.history_tree.insert(
                "",
                tk.END,
                values=(
                    "-",
                    "-",
                    filter_sel,
                    f"No transactions found matching filters ({total_across} total in history — click 'Show All')",
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                    "$0.00",
                    "0.00%",
                ),
            )
            if hasattr(self, "lbl_sales_stats"):
                self.lbl_sales_stats.config(text=t("lbl_tx_found_none", total=total_across))
        else:
            for raw_idx, tx in displayed_txs:
                t_type = str(tx.get("type", "BUY")).strip().upper() or "BUY"
                s_curr = tx.get("currency", "USD").strip().upper() or "USD"
                c_sym = self.converter.CURRENCY_SYMBOLS.get(s_curr, "$")
                shares = float(tx.get("shares", 0.0))
                price = float(tx.get("price", 0.0))
                tot_amt = float(tx.get("total_amount", 0.0))
                comm = float(tx.get("commission_fee", 0.0))
                tax = float(tx.get("estimated_tax", 0.0))

                if t_type == "SELL":
                    sell_count += 1
                    profit = float(tx.get("net_profit", 0.0))
                    roi = float(tx.get("net_roi_pct", 0.0))
                    total_profit_target += self.converter.convert(profit, s_curr, target_curr)
                    tag = "positive" if profit >= 0 else "negative"
                    type_display = "🔴 SELL"
                    profit_str = f"{c_sym}{profit:+,.2f}"
                    roi_str = f"{roi:+.2f}%"
                    tax_str = f"{c_sym}{tax:.2f}"
                else:
                    buy_count += 1
                    tag = "buy"
                    type_display = "🟢 BUY"
                    profit_str = "—"
                    roi_str = "—"
                    tax_str = "—"

                self.history_tree.insert(
                    "",
                    tk.END,
                    iid=f"tx_{raw_idx}",
                    values=(
                        tx.get("date", ""),
                        type_display,
                        tx.get("portfolio", DEFAULT_PORTFOLIO_NAME),
                        tx.get("symbol", ""),
                        s_curr,
                        f"{shares:.4g}",
                        f"{c_sym}{price:.2f}",
                        f"{c_sym}{tot_amt:,.2f}",
                        f"{c_sym}{comm:.2f}",
                        tax_str,
                        profit_str,
                        roi_str,
                    ),
                    tags=(tag,),
                )

            if hasattr(self, "lbl_sales_stats"):
                self.lbl_sales_stats.config(
                    text=t("lbl_tx_found_count", count=len(displayed_txs), buy=buy_count, sell=sell_count)
                )

        color = self.green_color if total_profit_target >= 0 else self.red_color
        formatted_profit = self.converter.format_money(total_profit_target, target_curr)
        filter_label = t("portfolio_all_plain") if filter_sel in ("All Portfolios (Consolidated)", "All Portfolios", "All", t("portfolio_all_consolidated"), t("portfolio_all_plain")) else filter_sel
        self.lbl_total_realized.config(text=t("lbl_realized_profit_scope", filter=filter_label, curr=target_curr, profit=formatted_profit), fg=color)

    def _sort_history_by(self, col: str):
        if not hasattr(self, "hist_sort_col"):
            self.hist_sort_col = "date"
            self.hist_sort_reverse = False

        if self.hist_sort_col == col:
            self.hist_sort_reverse = not self.hist_sort_reverse
        else:
            self.hist_sort_col = col
            self.hist_sort_reverse = False

        hist_headers = [
            ("date", t("col_tx_date")),
            ("type", t("col_tx_type")),
            ("portfolio", t("col_tx_port")),
            ("symbol", t("col_tx_sym")),
            ("currency", t("col_tx_curr")),
            ("shares", t("col_tx_shares")),
            ("price", t("col_tx_price")),
            ("total_amount", t("col_tx_total")),
            ("commission", t("col_tx_fees")),
            ("tax", t("col_tx_tax")),
            ("net_profit", t("col_tx_profit")),
            ("roi", t("col_tx_roi")),
        ]
        arrow = " ▼" if self.hist_sort_reverse else " ▲"
        for c, heading in hist_headers:
            disp_text = heading + (arrow if c == col else "")
            try:
                self.history_tree.heading(c, text=disp_text)
            except Exception:
                pass

        self._refresh_sales_table()

    def _on_sales_filter_changed(self, event=None):
        self._refresh_sales_table()

    def _show_all_sales_clicked(self):
        if hasattr(self, "sales_filter_var"):
            self.sales_filter_var.set("All Portfolios (Consolidated)")
        if hasattr(self, "tx_type_filter_var"):
            self.tx_type_filter_var.set("All Types")
        self._refresh_sales_table()

    def _match_active_portfolio_sales(self):
        if hasattr(self, "sales_filter_var"):
            self.sales_filter_var.set(self.current_portfolio)
        self._refresh_sales_table()

    def _open_record_transaction_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_record_tx_title"))
        dlg.geometry("460x540")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text=t("dlg_record_tx_header"),
            font=("Segoe UI", 12, "bold"),
            fg=self.primary_color,
            bg=self.bg_main,
        ).pack(anchor="w", pady=(0, 10))

        # Row 1: Type & Portfolio
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row1, text=t("lbl_tx_type_label"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        type_cb = ttk.Combobox(row1, values=["BUY", "SELL"], state="readonly", width=8)
        type_cb.set("BUY")
        type_cb.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(row1, text=t("lbl_portfolio"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        available_ports = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        if not available_ports:
            available_ports = [DEFAULT_PORTFOLIO_NAME]
        available_ports = sorted(list(set(available_ports)))
        default_port = self.current_portfolio if self.current_portfolio in available_ports else available_ports[0]
        port_cb = ttk.Combobox(row1, values=available_ports, width=22, state="readonly")
        port_cb.set(default_port)
        port_cb.pack(side=tk.LEFT)

        # Row 2: Symbol & Currency
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=(0, 8))

        def _get_symbols_for_port(p_name):
            return sorted(list(set(h["symbol"] for h in self.all_holdings if h.get("portfolio") == p_name)))

        tk.Label(row2, text=t("col_symbol") + ":", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        sym_cb = ttk.Combobox(row2, state="normal", width=12)
        sym_cb.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(row2, text=t("col_currency") + ":", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        curr_cb = ttk.Combobox(row2, values=["USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY"], state="readonly", width=8)
        curr_cb.set("USD")
        curr_cb.pack(side=tk.LEFT)

        # Row 3: Shares & Price
        row3 = ttk.Frame(frame)
        row3.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row3, text=t("lbl_shares_count"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        shares_entry = tk.Entry(row3, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=12)
        shares_entry.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(row3, text=t("lbl_buy_price_share"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        price_entry = tk.Entry(row3, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=12)
        price_entry.pack(side=tk.LEFT)

        comm_user_modified = [False]

        def _recalc_default_comm(*args):
            if comm_user_modified[0]:
                return
            try:
                sh_val = float(shares_entry.get().strip() or "0")
                pr_val = float(price_entry.get().strip() or "0")
                pt_val = port_cb.get().strip()
                ac_val = type_cb.get().strip().upper()
                est = calc_estimated_commission(pt_val, sh_val, pr_val, ac_val)
                comm_entry.delete(0, tk.END)
                comm_entry.insert(0, f"{est:.2f}")
            except Exception:
                pass

        def on_comm_entry_key(event=None):
            comm_user_modified[0] = True

        def on_sym_selected(event=None):
            chosen_sym = sym_cb.get().strip().upper()
            chosen_port = port_cb.get().strip()
            h = next((x for x in self.all_holdings if x["symbol"] == chosen_sym and x.get("portfolio") == chosen_port), None)
            if h:
                shares_entry.delete(0, tk.END)
                shares_entry.insert(0, f"{float(h.get('shares', 0.0)):.4g}")
                price_entry.delete(0, tk.END)
                cur_p = float(h.get("current_price", 0.0) or 0.0)
                if cur_p <= 0.0:
                    cur_p = float(h.get("buy_price", 0.0) or 0.0)
                price_entry.insert(0, f"{cur_p:.2f}")
                if h.get("currency"):
                    curr_cb.set(h.get("currency"))
            _recalc_default_comm()

        def on_sym_typed(event=None):
            if type_cb.get().strip().upper() != "BUY":
                return
            chosen_sym = sym_cb.get().strip().upper()
            chosen_port = port_cb.get().strip()
            h = next((x for x in self.all_holdings if x["symbol"] == chosen_sym and x.get("portfolio") == chosen_port), None)
            if h:
                cur_p = float(h.get("current_price", 0.0) or 0.0)
                if cur_p <= 0.0:
                    cur_p = float(h.get("buy_price", 0.0) or 0.0)
                if not price_entry.get().strip() or price_entry.get().strip() == "0.00":
                    price_entry.delete(0, tk.END)
                    price_entry.insert(0, f"{cur_p:.2f}")
                if h.get("currency"):
                    curr_cb.set(h.get("currency"))
            _recalc_default_comm()

        def on_type_changed(event=None):
            cur_t = type_cb.get().strip().upper()
            if cur_t == "BUY":
                sym_cb.config(state="normal")
            else:
                sym_cb.config(state="readonly")
                chosen_port = port_cb.get().strip()
                syms = _get_symbols_for_port(chosen_port)
                if sym_cb.get().strip().upper() not in syms:
                    if syms:
                        sym_cb.set(syms[0])
                        on_sym_selected()
                    else:
                        sym_cb.set("")
                        shares_entry.delete(0, tk.END)
                        price_entry.delete(0, tk.END)
            _recalc_default_comm()

        def on_port_changed(event=None):
            chosen_port = port_cb.get().strip()
            syms = _get_symbols_for_port(chosen_port)
            sym_cb["values"] = syms
            cur_t = type_cb.get().strip().upper()
            if cur_t == "BUY":
                sym_cb.config(state="normal")
                if not sym_cb.get().strip() and syms:
                    sym_cb.set(syms[0])
                    on_sym_selected()
            else:
                sym_cb.config(state="readonly")
                if syms:
                    sym_cb.set(syms[0])
                    on_sym_selected()
                else:
                    sym_cb.set("")
                    shares_entry.delete(0, tk.END)
                    price_entry.delete(0, tk.END)
            _recalc_default_comm()

        type_cb.bind("<<ComboboxSelected>>", on_type_changed)
        port_cb.bind("<<ComboboxSelected>>", on_port_changed)
        sym_cb.bind("<<ComboboxSelected>>", on_sym_selected)
        sym_cb.bind("<KeyRelease>", on_sym_typed)
        shares_entry.bind("<KeyRelease>", lambda e: _recalc_default_comm())
        price_entry.bind("<KeyRelease>", lambda e: _recalc_default_comm())

        # Row 4: Fees / Commission
        row4 = ttk.Frame(frame)
        row4.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row4, text=t("lbl_comm_fees"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        comm_entry = tk.Entry(row4, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=12)
        comm_entry.insert(0, "0.00")
        comm_entry.pack(side=tk.LEFT)
        comm_entry.bind("<Key>", on_comm_entry_key)

        # Initial populate of symbols based on default portfolio
        on_port_changed()

        # Row 5: Date
        tk.Label(frame, text=t("lbl_tx_date_time"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        date_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark)
        date_entry.insert(0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        date_entry.pack(fill=tk.X, pady=(2, 8))

        # Row 6: Notes
        tk.Label(frame, text=t("lbl_tx_notes_memo"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        notes_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark)
        notes_entry.pack(fill=tk.X, pady=(2, 12))

        # Checkbox: Update portfolio holdings
        update_holdings_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            frame,
            text=t("chk_update_holdings"),
            variable=update_holdings_var,
            bg=self.bg_main,
            fg=self.text_dark,
            font=("Segoe UI", 8),
            activebackground=self.bg_main,
        ).pack(anchor="w", pady=(0, 12))

        def on_save_manual_tx():
            t_type = type_cb.get().strip().upper()
            target_port = port_cb.get().strip() or DEFAULT_PORTFOLIO_NAME
            sym = sym_cb.get().strip().upper()
            curr = curr_cb.get().strip().upper() or "USD"
            if not sym:
                messagebox.showerror(t("dlg_error"), t("msg_enter_valid_symbol"), parent=dlg)
                return

            try:
                shares = float(shares_entry.get().strip())
                price = float(price_entry.get().strip())
                comm = float(comm_entry.get().strip() or "0.0")
                if shares <= 0 or price < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(t("dlg_error"), t("msg_enter_positive_shares_price"), parent=dlg)
                return

            dt = date_entry.get().strip() or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notes = notes_entry.get().strip()
            tot_amt = round(shares * price, 2)

            tx_record = {
                "date": dt,
                "type": t_type,
                "portfolio": target_port,
                "symbol": sym,
                "shares": shares,
                "price": price,
                "total_amount": tot_amt,
                "cost_basis": tot_amt,
                "commission_fee": comm,
                "estimated_tax": 0.0,
                "net_amount": (tot_amt - comm) if t_type == "SELL" else (tot_amt + comm),
                "net_profit": 0.0,
                "net_roi_pct": 0.0,
                "currency": curr,
                "notes": notes,
            }

            if update_holdings_var.get():
                existing = next((h for h in self.all_holdings if h["symbol"] == sym and h.get("portfolio") == target_port), None)
                if t_type == "SELL" and not existing:
                    messagebox.showerror(t("dlg_error"), t("msg_cannot_sell_not_found", sym=sym, port=target_port), parent=dlg)
                    return
                if t_type == "BUY":
                    if existing:
                        ex_sh = float(existing.get("shares", 0.0))
                        ex_bp = float(existing.get("buy_price", 0.0))
                        tot_sh = round(ex_sh + shares, 4)
                        ex_cb = round(ex_sh * ex_bp, 2)
                        add_cb = round(shares * price, 2)
                        tot_cb = round(ex_cb + add_cb, 2)
                        avg_p = round((ex_cb + add_cb) / tot_sh, 4) if tot_sh > 0 else price
                        existing["shares"] = tot_sh
                        existing["buy_price"] = avg_p
                        existing["cost_basis"] = tot_cb
                        existing.update(calc_holding_summary(tot_sh, avg_p, existing.get("current_price", avg_p), existing.get("dividend_yield", 0.0), existing.get("annual_div_per_share", 0.0)))
                        existing["cost_basis"] = tot_cb
                        existing["unrealized_gain"] = round(existing.get("market_value", 0.0) - tot_cb, 2)
                        existing["unrealized_gain_pct"] = round((existing["unrealized_gain"] / tot_cb * 100), 2) if tot_cb > 0 else 0.0
                    else:
                        new_h = {
                            "portfolio": target_port,
                            "symbol": sym,
                            "name": sym,
                            "shares": shares,
                            "buy_price": price,
                            "current_price": price,
                            "dividend_yield": 0.0,
                            "annual_div_per_share": 0.0,
                            "currency": curr,
                            "last_updated": dt,
                        }
                        new_h.update(calc_holding_summary(shares, price, price, 0.0, 0.0))
                        self.all_holdings.append(new_h)
                    save_portfolio(self.all_holdings, PORTFOLIO_CSV)
                elif t_type == "SELL" and existing:
                    cb = round(shares * existing["buy_price"], 2)
                    gain = round(tot_amt - comm - cb, 2)
                    roi = round((gain / cb * 100), 2) if cb > 0 else 0.0
                    tx_record["cost_basis"] = cb
                    tx_record["net_profit"] = gain
                    tx_record["net_roi_pct"] = roi

                    rem = round(existing["shares"] - shares, 6)
                    if rem <= 0.0001:
                        self.all_holdings = [h for h in self.all_holdings if h is not existing]
                    else:
                        existing["shares"] = rem
                        existing.update(calc_holding_summary(rem, existing["buy_price"], existing.get("current_price", existing["buy_price"]), existing.get("dividend_yield", 0.0), existing.get("annual_div_per_share", 0.0)))
                    save_portfolio(self.all_holdings, PORTFOLIO_CSV)

            append_transaction(tx_record, TRANSACTION_HISTORY_CSV)
            self.transactions = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=self.current_portfolio if self.current_portfolio != "All Portfolios (Consolidated)" else None)
            self.sales_history = self.transactions
            self._refresh_sales_table()
            self._on_portfolio_selected()
            dlg.destroy()
            self._set_status(t("msg_tx_recorded", type=t_type, shares=shares, sym=sym))

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(10, 0))

        tk.Button(
            btn_row,
            text=t("btn_save_transaction"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=6,
            command=on_save_manual_tx,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        tk.Button(
            btn_row,
            text=t("btn_cancel"),
            font=("Segoe UI", 9),
            bg=self.tab_inactive_bg,
            fg=self.text_dark,
            relief="flat",
            pady=6,
            command=dlg.destroy,
        ).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(4, 0))

        dlg.bind("<Escape>", lambda e: dlg.destroy())

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 460, 540
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _open_edit_transaction_dialog(self):
        sel = self.history_tree.selection()
        if not sel:
            messagebox.showwarning(t("msg_warning"), t("msg_select_tx_edit"), parent=self.root)
            return

        item_id = sel[0]
        if not item_id.startswith("tx_"):
            return

        try:
            raw_idx = int(item_id.split("_")[1])
        except ValueError:
            return

        all_txs = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=None, tx_type=None)
        if raw_idx < 0 or raw_idx >= len(all_txs):
            messagebox.showerror(t("msg_error"), t("msg_tx_record_not_found"), parent=self.root)
            return

        tx = all_txs[raw_idx]

        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_edit_tx"))
        dlg.geometry("480x580")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text=f"✏️ {t('dlg_edit_tx')} (#{raw_idx + 1})",
            font=("Segoe UI", 12, "bold"),
            fg=self.primary_color,
            bg=self.bg_main,
        ).pack(anchor="w", pady=(0, 10))

        # Row 1: Type & Portfolio
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row1, text=t("lbl_tx_type_label"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        type_cb = ttk.Combobox(row1, values=["BUY", "SELL", "DIVIDEND"], state="readonly", width=8)
        cur_type = str(tx.get("type", "BUY")).strip().upper()
        type_cb.set(cur_type if cur_type in ["BUY", "SELL", "DIVIDEND"] else "BUY")
        type_cb.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(row1, text=t("lbl_portfolio"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        available_ports = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        available_ports = sorted(list(set(available_ports)))
        port_cb = ttk.Combobox(row1, values=available_ports, width=22, state="readonly")
        port_cb.set(tx.get("portfolio", DEFAULT_PORTFOLIO_NAME))
        port_cb.pack(side=tk.LEFT)

        # Row 2: Symbol & Currency
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row2, text=t("col_symbol") + ":", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        sym_entry = tk.Entry(row2, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=12)
        sym_entry.insert(0, tx.get("symbol", ""))
        sym_entry.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(row2, text=t("col_currency") + ":", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        curr_cb = ttk.Combobox(row2, values=["USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY"], state="readonly", width=8)
        curr_cb.set(tx.get("currency", "USD"))
        curr_cb.pack(side=tk.LEFT)

        # Row 3: Shares & Price
        row3 = ttk.Frame(frame)
        row3.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row3, text=t("lbl_shares_count"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        shares_entry = tk.Entry(row3, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=12)
        shares_entry.insert(0, f"{float(tx.get('shares', 0.0)):.4g}")
        shares_entry.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(row3, text=t("lbl_buy_price_share"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        price_entry = tk.Entry(row3, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=12)
        price_entry.insert(0, f"{float(tx.get('price', 0.0)):.2f}")
        price_entry.pack(side=tk.LEFT)

        # Row 4: Cost Basis & Commission
        row4 = ttk.Frame(frame)
        row4.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row4, text=t("lbl_cost_basis_input"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        cb_entry = tk.Entry(row4, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=10)
        cb_entry.insert(0, f"{float(tx.get('cost_basis', 0.0)):.2f}")
        cb_entry.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(row4, text=t("lbl_comm_fees"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        comm_entry = tk.Entry(row4, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=8)
        comm_entry.insert(0, f"{float(tx.get('commission_fee', 0.0)):.2f}")
        comm_entry.pack(side=tk.LEFT)

        # Row 5: Tax
        row5 = ttk.Frame(frame)
        row5.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row5, text=t("lbl_estimated_tax_input"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        tax_entry = tk.Entry(row5, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=10)
        tax_entry.insert(0, f"{float(tx.get('estimated_tax', 0.0)):.2f}")
        tax_entry.pack(side=tk.LEFT)

        # Row 6: Date & Time
        tk.Label(frame, text=t("lbl_tx_date_time"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        date_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark)
        date_entry.insert(0, tx.get("date", ""))
        date_entry.pack(fill=tk.X, pady=(2, 8))

        # Row 7: Notes
        tk.Label(frame, text=t("lbl_tx_notes_memo"), font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        notes_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark)
        notes_entry.insert(0, tx.get("notes", ""))
        notes_entry.pack(fill=tk.X, pady=(2, 12))

        def on_save_edit():
            t_type = type_cb.get().strip().upper()
            target_port = port_cb.get().strip() or DEFAULT_PORTFOLIO_NAME
            sym = sym_entry.get().strip().upper()
            curr = curr_cb.get().strip().upper() or "USD"
            if not sym:
                messagebox.showerror(t("msg_error"), t("msg_enter_valid_symbol"), parent=dlg)
                return

            try:
                shares = float(shares_entry.get().strip())
                price = float(price_entry.get().strip())
                cb = float(cb_entry.get().strip() or "0.0")
                comm = float(comm_entry.get().strip() or "0.0")
                tax = float(tax_entry.get().strip() or "0.0")
                if shares <= 0 or price < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(t("msg_error"), t("msg_enter_positive_shares_price"), parent=dlg)
                return

            dt = date_entry.get().strip() or tx.get("date", "")
            notes = notes_entry.get().strip()
            tot_amt = round(shares * price, 2)
            if cb <= 0.0 and t_type == "BUY":
                cb = tot_amt

            if t_type == "SELL":
                net_amt = round(tot_amt - comm - tax, 2)
                gain = round(net_amt - cb, 2)
                roi = round((gain / cb * 100), 2) if cb > 0 else 0.0
            else:
                net_amt = round(tot_amt + comm, 2)
                gain = 0.0
                roi = 0.0

            updated_record = {
                "date": dt,
                "type": t_type,
                "portfolio": target_port,
                "symbol": sym,
                "shares": shares,
                "price": price,
                "total_amount": tot_amt,
                "cost_basis": cb,
                "commission_fee": comm,
                "estimated_tax": tax,
                "net_amount": net_amt,
                "net_profit": gain,
                "net_roi_pct": roi,
                "currency": curr,
                "notes": notes,
            }

            ok = update_transaction(raw_idx, updated_record, TRANSACTION_HISTORY_CSV)
            if ok:
                self._refresh_sales_table()
                dlg.destroy()
                self._set_status(f"Updated transaction #{raw_idx + 1} ({sym}).")
                messagebox.showinfo(t("msg_success"), t("msg_tx_updated", idx=raw_idx + 1), parent=self.root)
            else:
                messagebox.showerror(t("msg_error"), t("msg_tx_update_failed"), parent=dlg)

        def on_delete_record():
            if messagebox.askyesno(t("msg_warning"), t("confirm_delete_tx"), parent=dlg):
                ok = delete_transaction(raw_idx, TRANSACTION_HISTORY_CSV)
                if ok:
                    self._refresh_sales_table()
                    dlg.destroy()
                    self._set_status(f"Deleted transaction #{raw_idx + 1}.")
                    messagebox.showinfo(t("msg_success"), t("msg_tx_deleted", idx=raw_idx + 1), parent=self.root)
                else:
                    messagebox.showerror(t("msg_error"), t("msg_tx_delete_failed"), parent=dlg)

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(10, 0))

        tk.Button(
            btn_row,
            text=t("btn_save_changes"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=6,
            command=on_save_edit,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        tk.Button(
            btn_row,
            text=t("btn_delete_record"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg=self.red_color,
            relief="solid",
            bd=1,
            pady=5,
            command=on_delete_record,
        ).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(
            btn_row,
            text=t("btn_close"),
            font=("Segoe UI", 9),
            bg="#ffffff",
            relief="solid",
            bd=1,
            pady=5,
            command=dlg.destroy,
        ).pack(side=tk.LEFT)

        dlg.bind("<Escape>", lambda e: dlg.destroy())

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 480, 580
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _open_period_earnings_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_period_report"))
        dlg.geometry("980x700")
        dlg.minsize(820, 520)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        header_frame = ttk.Frame(dlg, padding="16 12 16 8")
        header_frame.pack(fill=tk.X)

        tk.Label(
            header_frame,
            text=f"📊 {t('dlg_period_report')}",
            font=("Segoe UI", 13, "bold"),
            fg=self.primary_color,
            bg=self.bg_main,
        ).pack(side=tk.LEFT)

        # Filters toolbar frame
        filter_panel = ttk.LabelFrame(dlg, text=t("lbl_report_filters_scope"), padding="10 8 10 8")
        filter_panel.pack(fill=tk.X, padx=16, pady=(0, 8))

        # Portfolio selection
        f_row1 = ttk.Frame(filter_panel)
        f_row1.pack(fill=tk.X, pady=(0, 6))

        tk.Label(f_row1, text=t("lbl_portfolio"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        all_port_names = [t("portfolio_all_consolidated")] + [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        port_cb = ttk.Combobox(f_row1, values=all_port_names, state="readonly", width=22)
        default_port = self.current_portfolio if self.current_portfolio in all_port_names else all_port_names[0]
        port_cb.set(default_port)
        port_cb.pack(side=tk.LEFT, padx=(0, 16))

        # Period mode
        tk.Label(f_row1, text=t("lbl_filter_period"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        period_modes = [
            ("this_month", t("period_this_month")),
            ("this_week", t("period_this_week")),
            ("in_months", t("period_in_months")),
            ("in_weeks", t("period_in_weeks")),
            ("custom", t("period_custom")),
        ]
        period_cb = ttk.Combobox(f_row1, values=[m[1] for m in period_modes], state="readonly", width=26)
        period_cb.set(period_modes[0][1])
        period_cb.pack(side=tk.LEFT, padx=(0, 16))

        # Custom Date Range sub-frame
        date_frame = ttk.Frame(f_row1)
        tk.Label(date_frame, text=t("lbl_date_range"), font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 4))
        start_entry = tk.Entry(date_frame, font=("Segoe UI", 9), width=11, relief="solid", bd=1)
        today = date.today()
        start_entry.insert(0, (today - timedelta(days=30)).strftime("%Y-%m-%d"))
        start_entry.pack(side=tk.LEFT, padx=(0, 4))

        tk.Label(date_frame, text=t("lbl_to"), font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 4))
        end_entry = tk.Entry(date_frame, font=("Segoe UI", 9), width=11, relief="solid", bd=1)
        end_entry.insert(0, today.strftime("%Y-%m-%d"))
        end_entry.pack(side=tk.LEFT)

        def on_period_mode_change(event=None):
            sel_text = period_cb.get()
            if t("period_custom") in sel_text or "custom" in sel_text.lower():
                date_frame.pack(side=tk.LEFT, padx=(0, 8))
            else:
                date_frame.pack_forget()

        period_cb.bind("<<ComboboxSelected>>", on_period_mode_change)

        btn_calc = tk.Button(
            f_row1,
            text=t("btn_refresh"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=10,
            pady=2,
            command=lambda: run_report(),
        )
        btn_calc.pack(side=tk.LEFT, padx=(8, 8))

        btn_export = tk.Button(
            f_row1,
            text=t("btn_export_report_html"),
            font=("Segoe UI", 9, "bold"),
            bg="#0f9d58",
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=2,
            command=lambda: export_html(),
        )
        btn_export.pack(side=tk.RIGHT)

        # KPI Summary Cards Frame
        kpi_frame = ttk.Frame(dlg, padding="16 4 16 8")
        kpi_frame.pack(fill=tk.X)

        def make_kpi_box(parent, title):
            box = tk.Frame(parent, bg="#ffffff", bd=1, relief="solid", padx=10, pady=8)
            box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
            lbl_t = tk.Label(box, text=title, font=("Segoe UI", 8, "bold"), fg=self.text_muted, bg="#ffffff")
            lbl_t.pack(anchor="w")
            lbl_v = tk.Label(box, text="$0.00", font=("Segoe UI", 12, "bold"), fg=self.text_dark, bg="#ffffff")
            lbl_v.pack(anchor="w", pady=(2, 0))
            return lbl_v

        kpi_profit = make_kpi_box(kpi_frame, t("card_realized_profit"))
        kpi_roi = make_kpi_box(kpi_frame, t("card_period_roi"))
        kpi_sales = make_kpi_box(kpi_frame, t("card_sales_proceeds"))
        kpi_cost = make_kpi_box(kpi_frame, t("card_cost_sold"))
        kpi_buys = make_kpi_box(kpi_frame, t("card_buy_volume"))
        kpi_trades = make_kpi_box(kpi_frame, t("col_trades_count"))

        # Notebook for Breakdown and Records
        nb = ttk.Notebook(dlg)
        nb.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 12))

        # Tab 1: Interval Breakdown
        tab_breakdown = ttk.Frame(nb, padding=8)
        nb.add(tab_breakdown, text=t("tab_period_breakdown"))

        b_cols = ("interval", "trades", "buy_vol", "sell_proc", "cost_basis", "profit", "roi")
        b_tree = ttk.Treeview(tab_breakdown, columns=b_cols, show="headings")
        b_headers = [
            ("interval", t("col_period_interval"), 180),
            ("trades", t("col_trades_count"), 70),
            ("buy_vol", t("col_buy_volume"), 110),
            ("sell_proc", t("col_sell_proceeds"), 110),
            ("cost_basis", t("col_cost_sold"), 110),
            ("profit", t("col_realized_profit"), 120),
            ("roi", t("col_net_roi"), 80),
        ]
        for c, h, w in b_headers:
            b_tree.heading(c, text=h)
            b_tree.column(c, width=w, anchor="e" if c not in ("interval",) else "w")

        b_scroll = ttk.Scrollbar(tab_breakdown, orient=tk.VERTICAL, command=b_tree.yview)
        b_tree.configure(yscrollcommand=b_scroll.set)
        b_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        b_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        b_tree.tag_configure("positive", foreground=self.green_color)
        b_tree.tag_configure("negative", foreground=self.red_color)

        # Tab 2: Individual Transactions
        tab_records = ttk.Frame(nb, padding=8)
        nb.add(tab_records, text=t("tab_individual_records"))

        r_cols = ("date", "type", "portfolio", "symbol", "shares", "price", "total", "cost", "profit", "roi", "notes")
        r_tree = ttk.Treeview(tab_records, columns=r_cols, show="headings")
        r_headers = [
            ("date", t("col_tx_date"), 120),
            ("type", t("col_tx_type"), 70),
            ("portfolio", t("col_tx_port"), 90),
            ("symbol", t("col_tx_sym"), 65),
            ("shares", t("col_tx_shares"), 65),
            ("price", t("col_tx_price"), 75),
            ("total", t("col_tx_total"), 90),
            ("cost", t("col_cost_basis"), 90),
            ("profit", t("col_tx_profit"), 95),
            ("roi", t("col_tx_roi"), 70),
            ("notes", t("col_notes"), 140),
        ]
        for c, h, w in r_headers:
            r_tree.heading(c, text=h)
            r_tree.column(c, width=w, anchor="e" if c not in ("type", "symbol", "portfolio", "date", "notes") else "center")

        r_scroll = ttk.Scrollbar(tab_records, orient=tk.VERTICAL, command=r_tree.yview)
        r_tree.configure(yscrollcommand=r_scroll.set)
        r_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        r_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        r_tree.tag_configure("positive", foreground=self.green_color)
        r_tree.tag_configure("negative", foreground=self.red_color)
        r_tree.tag_configure("buy", foreground="#00897b")

        current_period_result = {}

        def run_report():
            nonlocal current_period_result
            sel_port = port_cb.get().strip()
            is_all_p = (
                sel_port in ("All Portfolios (Consolidated)", "All Portfolios", "All", "*",
                             t("portfolio_all_consolidated"), t("portfolio_all_plain"))
                or "consolidated" in sel_port.lower()
                or "合併" in sel_port
                or "合并" in sel_port
            )
            port_arg = None if is_all_p else sel_port

            sel_mode_text = period_cb.get()
            mode_code = "this_month"
            for code, name in period_modes:
                if name == sel_mode_text:
                    mode_code = code
                    break

            start_d = None
            end_d = None
            if mode_code == "custom":
                s_str = start_entry.get().strip()
                e_str = end_entry.get().strip()
                start_d = parse_tx_date(s_str)
                end_d = parse_tx_date(e_str)
                if not start_d or not end_d:
                    messagebox.showerror(t("msg_error"), t("msg_invalid_date_range"), parent=dlg)
                    return

            all_txs = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=None, tx_type=None)
            res = calc_period_earnings(
                all_txs,
                period_mode=mode_code,
                start_date=start_d,
                end_date=end_d,
                portfolio_name=port_arg,
            )
            current_period_result = res

            # Update KPI Cards
            summ = res.get("summary", {})
            tot_p = float(summ.get("total_realized_profit", 0.0))
            roi_p = float(summ.get("net_roi_pct", 0.0))
            tot_s = float(summ.get("total_sell_proceeds", 0.0))
            tot_c = float(summ.get("total_cost_basis", 0.0))
            tot_b = float(summ.get("total_buy_volume", 0.0))
            b_cnt = summ.get("buy_count", 0)
            s_cnt = summ.get("sell_count", 0)
            d_cnt = summ.get("dividend_count", 0)

            p_color = self.green_color if tot_p >= 0 else self.red_color
            kpi_profit.config(text=f"${tot_p:+,.2f}", fg=p_color)
            kpi_roi.config(text=f"{roi_p:+.2f}%", fg=p_color)
            kpi_sales.config(text=f"${tot_s:,.2f}")
            kpi_cost.config(text=f"${tot_c:,.2f}")
            kpi_buys.config(text=f"${tot_b:,.2f}", fg="#1a73e8")
            kpi_trades.config(text=f"{b_cnt} B / {s_cnt} S / {d_cnt} D")

            # Update Breakdown Tree
            for it in b_tree.get_children():
                b_tree.delete(it)
            bd = res.get("breakdown", [])
            if bd:
                for b in bd:
                    bp = float(b.get("total_realized_profit", 0.0))
                    tag = "positive" if bp >= 0 else "negative"
                    b_tree.insert(
                        "",
                        tk.END,
                        values=(
                            b.get("period_label", ""),
                            b.get("total_transactions", 0),
                            f"${float(b.get('total_buy_volume', 0.0)):,.2f}",
                            f"${float(b.get('total_sell_proceeds', 0.0)):,.2f}",
                            f"${float(b.get('total_cost_basis', 0.0)):,.2f}",
                            f"${bp:+,.2f}",
                            f"{float(b.get('net_roi_pct', 0.0)):+.2f}%",
                        ),
                        tags=(tag,),
                    )
                nb.select(0)
            else:
                b_tree.insert("", tk.END, values=("(Breakdown available in 'In Months' or 'In Weeks' modes)", "-", "-", "-", "-", "-", "-"))
                nb.select(1)

            # Update Records Tree
            for it in r_tree.get_children():
                r_tree.delete(it)
            recs = res.get("records", [])
            for r in recs:
                rt = str(r.get("type", "BUY")).upper()
                rp = float(r.get("net_profit", 0.0) or 0.0)
                rr = float(r.get("net_roi_pct", 0.0) or 0.0)
                if "SELL" in rt:
                    tag = "positive" if rp >= 0 else "negative"
                    p_str = f"${rp:+,.2f}"
                    r_str = f"{rr:+.2f}%"
                elif "BUY" in rt:
                    tag = "buy"
                    p_str = "—"
                    r_str = "—"
                else:
                    tag = "positive" if rp >= 0 else "neutral"
                    p_str = f"${rp:+,.2f}"
                    r_str = "—"

                r_tree.insert(
                    "",
                    tk.END,
                    values=(
                        r.get("date", ""),
                        rt,
                        r.get("portfolio", ""),
                        r.get("symbol", ""),
                        f"{float(r.get('shares', 0.0)):.4g}",
                        f"${float(r.get('price', 0.0)):,.2f}",
                        f"${float(r.get('total_amount', 0.0)):,.2f}",
                        f"${float(r.get('cost_basis', 0.0)):,.2f}",
                        p_str,
                        r_str,
                        r.get("notes", ""),
                    ),
                    tags=(tag,),
                )

        def export_html():
            if not current_period_result:
                run_report()
            if not current_period_result:
                return

            def_filename = f"period_earnings_report_{current_period_result.get('period_mode', 'report')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            path = filedialog.asksaveasfilename(
                title=t("btn_export_report_html"),
                defaultextension=".html",
                initialfile=def_filename,
                filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
                parent=dlg,
            )
            if not path:
                return

            ok = generate_period_earnings_report_html(current_period_result, path)
            if ok:
                if messagebox.askyesno(t("msg_success"), t("msg_report_exported_open_browser", path=path), parent=dlg):
                    webbrowser.open(f"file://{os.path.abspath(path)}")
            else:
                messagebox.showerror(t("msg_error"), t("msg_report_export_failed"), parent=dlg)

        # Initial trigger
        run_report()

    def _update_metric_cards(self):
        target_curr = self.summary_currency if hasattr(self, "summary_currency") else "USD"

        for h in self.holdings:
            s = float(h.get("shares", 0.0))
            bp = float(h.get("buy_price", 0.0))
            cp = float(h.get("current_price", bp))
            cb = float(h.get("cost_basis", 0.0))
            if cb <= 0.0 and s > 0 and bp > 0:
                cb = round(s * bp, 2)
                h["cost_basis"] = cb
            mv = float(h.get("market_value", 0.0))
            if mv <= 0.0 and s > 0 and cp > 0:
                mv = round(s * cp, 2)
                h["market_value"] = mv
            ug = float(h.get("unrealized_gain", 0.0))
            if ug == 0.0 and mv != cb:
                ug = round(mv - cb, 2)
                h["unrealized_gain"] = ug
            if float(h.get("unrealized_gain_pct", 0.0)) == 0.0 and cb > 0 and ug != 0.0:
                h["unrealized_gain_pct"] = round((ug / cb * 100), 2)

        total_val = 0.0
        total_cost = 0.0
        total_ann_div = 0.0

        for h in self.holdings:
            h_curr = h.get("currency", "USD").strip().upper() or "USD"
            mv = float(h.get("market_value", 0.0))
            cb = float(h.get("cost_basis", 0.0))
            ad = float(h.get("annual_dividend", 0.0))

            if target_curr == "Native":
                total_val += mv
                total_cost += cb
                total_ann_div += ad
            else:
                total_val += self.converter.convert(mv, h_curr, target_curr)
                total_cost += self.converter.convert(cb, h_curr, target_curr)
                total_ann_div += self.converter.convert(ad, h_curr, target_curr)

        total_gain = total_val - total_cost
        total_gain_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0.0
        monthly_div = total_ann_div / 12.0

        total_day_chg = 0.0
        has_any_day_chg = False
        for h in self.holdings:
            chg = h.get("change")
            if chg is not None:
                has_any_day_chg = True
                s = float(h.get("shares", 0.0))
                h_curr = h.get("currency", "USD").strip().upper() or "USD"
                chg_converted = self.converter.convert(float(chg) * s, h_curr, target_curr) if target_curr != "Native" else float(chg) * s
                total_day_chg += chg_converted

        day_chg_pct = (total_day_chg / (total_val - total_day_chg) * 100) if (total_val - total_day_chg) > 0 else 0.0
        day_sign = "+" if total_day_chg >= 0 else "-"

        curr_label = target_curr if target_curr != "Native" else "Mix"
        sym = self.converter.CURRENCY_SYMBOLS.get(target_curr, "$") if target_curr != "Native" else "$"

        self.cards["total_value"].config(text=self.converter.format_money(total_val, target_curr))
        self.cards["total_cost"].config(text=self.converter.format_money(total_cost, target_curr))

        gain_sign = "+" if total_gain >= 0 else "-"
        abs_gain = abs(total_gain)
        self.cards["total_gain"].config(text=f"{gain_sign}{sym}{abs_gain:,.2f} ({total_gain_pct:+.2f}%)")

        color = self.green_color if total_gain >= 0 else self.red_color
        self.cards["total_gain"].config(fg=color)

        self.cards["annual_dividend"].config(text=self.converter.format_money(total_ann_div, target_curr))
        self.cards["monthly_dividend"].config(text=self.converter.format_money(monthly_div, target_curr))

        if hasattr(self, "card_titles"):
            if has_any_day_chg:
                self.card_titles["total_value"].config(
                    text=f"💼 {t('card_total_value')} ({curr_label}) • Day: {day_sign}{sym}{abs(total_day_chg):,.2f} ({day_chg_pct:+.2f}%)"
                )
            else:
                self.card_titles["total_value"].config(text=f"💼 {t('card_total_value')} ({curr_label})")
            self.card_titles["total_cost"].config(text=f"🏷️ {t('col_cost_basis')} ({curr_label})")
            self.card_titles["total_gain"].config(text=f"📈 {t('card_unrealized_pl')} ({curr_label})")
            self.card_titles["annual_dividend"].config(text=f"💵 {t('card_annual_dividend')} ({curr_label})")
            self.card_titles["monthly_dividend"].config(text=f"🗓️ {t('div_proj_monthly')} ({curr_label})")

        # Multi-currency Exposure Matrix
        if hasattr(self, "lbl_curr_exposure"):
            curr_totals = {}
            for h in self.holdings:
                c = (h.get("currency") or "USD").strip().upper()
                mv = float(h.get("shares", 0.0)) * float(h.get("current_price", h.get("price", 0.0)))
                mv_conv = self.converter.convert(mv, c, target_curr) if target_curr != "Native" else mv
                curr_totals[c] = curr_totals.get(c, 0.0) + mv_conv
            tot_exp = sum(curr_totals.values())
            if tot_exp > 0:
                exp_strs = [f"{c}: {val/tot_exp*100:.1f}%" for c, val in sorted(curr_totals.items(), key=lambda x: x[1], reverse=True)]
                self.lbl_curr_exposure.config(text=f"{t('lbl_curr_exposure')} " + " | ".join(exp_strs))
            else:
                self.lbl_curr_exposure.config(text="")

    def _refresh_dropdowns(self):
        syms = [f"{h['symbol']} ({h.get('name', '')})" for h in self.holdings]
        self.div_holding_cb["values"] = syms
        self.split_holding_cb["values"] = syms
        self.sell_holding_cb["values"] = syms
        all_dropdown_vals = self._get_portfolio_dropdown_values()
        if hasattr(self, "portfolio_combo"):
            self.portfolio_combo["values"] = all_dropdown_vals
        if hasattr(self, "rep_port_cb"):
            all_ports = [t("portfolio_all_consolidated")] + [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
            self.rep_port_cb["values"] = all_ports
        if hasattr(self, "sales_filter_cb"):
            self.sales_filter_cb["values"] = all_dropdown_vals

    def _sort_holdings_by(self, col: str):
        if self.sort_col == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_col = col
            self.sort_reverse = False

        numeric_cols = {
            "shares", "buy_price", "current_price", "change",
            "market_value", "cost_basis", "unrealized_gain",
            "unrealized_gain_pct", "div_yield", "annual_div"
        }

        def get_sort_val(h):
            val = h.get(col)
            if col in numeric_cols:
                try:
                    return float(val if val is not None else 0.0)
                except (ValueError, TypeError):
                    return 0.0
            return str(val or "").lower()

        self.holdings.sort(key=get_sort_val, reverse=self.sort_reverse)

        headers_def = [
            ("portfolio", "Portfolio"),
            ("symbol", "Symbol"),
            ("name", "Company Name"),
            ("currency", "Curr"),
            ("shares", "Shares"),
            ("buy_price", "Buy Price"),
            ("current_price", "Live Price"),
            ("change", "Day Change"),
            ("market_value", "Market Value"),
            ("cost_basis", "Cost Basis"),
            ("unrealized_gain", "Profit/Loss"),
            ("unrealized_gain_pct", "P/L (%)"),
            ("div_yield", "Div Yield"),
            ("annual_div", "Est. Ann Div"),
            ("updated", "Last Updated"),
        ]
        arrow = " ▼" if self.sort_reverse else " ▲"
        for c, heading in headers_def:
            disp_text = heading + (arrow if c == col else "")
            self.holdings_tree.heading(c, text=disp_text)

        self._refresh_holdings_table()

    def _export_html_report_dialog(self):
        default_name = f"portfolio_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filename = filedialog.asksaveasfilename(
            title=t("dlg_export_html_report"),
            initialfile=default_name,
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
        )
        if not filename:
            return

        base_curr = self.summary_currency if hasattr(self, "summary_currency") else "USD"
        fx_rates = getattr(self.fetcher, "fx_cache", {})
        metrics = calc_portfolio_metrics(self.holdings, base_curr, fx_rates)

        ok = generate_html_report(
            holdings=self.holdings,
            portfolio_metrics=metrics,
            sales_history=self.sales_history,
            filepath=filename,
        )
        if ok:
            ans = messagebox.askyesno(
                t("msg_success"),
                t("msg_html_report_success", path=filename),
                parent=self.root,
            )
            if ans:
                try:
                    webbrowser.open(f"file://{os.path.abspath(filename)}")
                except Exception as e:
                    messagebox.showinfo(t("msg_notice"), t("msg_html_report_saved", path=filename), parent=self.root)
            self._set_status(f"Exported HTML report: {os.path.basename(filename)}")
        else:
            messagebox.showerror(t("dlg_error"), t("msg_html_report_failed"), parent=self.root)

    # -------------------------------------------------------------
    # CSV Import / Export
    # -------------------------------------------------------------
    def _import_csv_dialog(self):
        filename = filedialog.askopenfilename(
            title=t("dlg_import_csv_title"),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if filename:
            imported = load_portfolio(filename)
            if not imported:
                # Try Google Finance CSV parser as fallback
                imported = self.account_sync.parse_google_finance_csv(filename)
                if imported:
                    for h in imported:
                        h.update(calc_holding_summary(h["shares"], h["buy_price"], h["current_price"]))

            if not imported:
                messagebox.showerror(t("dlg_error"), t("msg_import_csv_invalid"))
                return

            ans = messagebox.askyesnocancel(
                t("dlg_import_option_title"),
                t("msg_import_csv_option", count=len(imported)),
            )
            target_p = self.current_portfolio if self.current_portfolio != "All Portfolios (Consolidated)" else DEFAULT_PORTFOLIO_NAME
            for h in imported:
                if not h.get("portfolio"):
                    h["portfolio"] = target_p
                if not h.get("currency"):
                    h["currency"] = "USD"

            if ans is True:
                self.all_holdings.extend(imported)
            elif ans is False:
                if self.current_portfolio == "All Portfolios (Consolidated)":
                    self.all_holdings = imported
                else:
                    self.all_holdings = [h for h in self.all_holdings if h.get("portfolio") != self.current_portfolio] + imported
            else:
                return

            save_portfolio(self.all_holdings, PORTFOLIO_CSV)
            self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
            self._on_portfolio_selected()
            self.fetch_all_quotes()
            messagebox.showinfo(t("msg_success"), t("msg_import_csv_success", count=len(imported)))

    def _export_csv_dialog(self):
        filename = filedialog.asksaveasfilename(
            title=t("dlg_export_csv_title"),
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="my_portfolio_export.csv",
        )
        if filename:
            if save_portfolio(self.holdings, filename):
                messagebox.showinfo(t("msg_success"), t("msg_portfolio_saved", path=filename))
            else:
                messagebox.showerror(t("dlg_error"), t("msg_portfolio_export_failed"))

    def _export_sales_csv(self):
        filename = filedialog.asksaveasfilename(
            title=t("dlg_export_tx_csv_title"),
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="my_transactions_export.csv",
        )
        if filename:
            txs_to_export = getattr(self, "transactions", self.sales_history)
            if save_transactions(txs_to_export, filename):
                messagebox.showinfo(t("msg_success"), t("msg_tx_exported", path=filename))
            else:
                messagebox.showerror(t("dlg_error"), t("msg_tx_export_failed"))

    def _clear_sales_history(self):
        if messagebox.askyesno(t("msg_warning"), t("confirm_clear_history")):
            self.transactions = []
            self.sales_history = []
            save_transactions([], TRANSACTION_HISTORY_CSV)
            save_sales_history([], SALES_HISTORY_CSV)
            self._refresh_sales_table()
            self._set_status("Cleared transaction history.")

    def _open_backups_dialog(self):
        """Displays rolling backups dialog with restore capabilities."""
        dlg = tk.Toplevel(self.root)
        dlg.title(t("backup_dlg_title"))
        dlg.geometry("640x440")
        dlg.minsize(540, 340)
        dlg.configure(bg=self.bg_main)
        dlg.transient(self.root)

        # Header
        hdr = ttk.Frame(dlg, padding="16 12 16 6")
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr,
            text=t("backup_dlg_header"),
            font=("Segoe UI", 12, "bold"),
            fg=self.primary_color,
            bg=self.bg_main,
        ).pack(anchor="w")
        tk.Label(
            hdr,
            text=t("backup_dlg_sub"),
            font=("Segoe UI", 9),
            fg=self.text_muted,
            bg=self.bg_main,
        ).pack(anchor="w", pady=(2, 6))

        # Target selection
        sel_frame = ttk.Frame(dlg, padding="16 0 16 6")
        sel_frame.pack(fill=tk.X)
        tk.Label(sel_frame, text=t("backup_select_file"), font=("Segoe UI", 9, "bold"), bg=self.bg_main).pack(side=tk.LEFT, padx=(0, 8))

        file_choices = {
            t("opt_backup_portfolio"): PORTFOLIO_CSV,
            t("opt_backup_transactions"): TRANSACTION_HISTORY_CSV,
            t("opt_backup_sales"): SALES_HISTORY_CSV,
        }
        file_var = tk.StringVar(value=t("opt_backup_portfolio"))
        combo = ttk.Combobox(sel_frame, textvariable=file_var, values=list(file_choices.keys()), state="readonly", width=38)
        combo.pack(side=tk.LEFT)

        # Table frame
        tbl_frame = ttk.Frame(dlg, padding="16 6 16 10")
        tbl_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("slot", "filename", "modified", "size")
        tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", height=6)
        tree.heading("slot", text=t("backup_slot"))
        tree.heading("filename", text=t("backup_filename"))
        tree.heading("modified", text=t("backup_timestamp"))
        tree.heading("size", text=t("backup_size"))
        tree.column("slot", width=100, anchor="center")
        tree.column("filename", width=180, anchor="w")
        tree.column("modified", width=160, anchor="center")
        tree.column("size", width=100, anchor="e")
        tree.pack(fill=tk.BOTH, expand=True)

        def populate_tree():
            for item in tree.get_children():
                tree.delete(item)
            curr_target = file_choices[file_var.get()]
            backups = get_backup_files(curr_target)
            if not backups:
                tree.insert("", "end", values=("-", t("lbl_no_backups"), "-", "-"))
                return
            for b in backups:
                slot_label = t("lbl_backup_newest", idx=b['index']) if b['index'] == 1 else (t("lbl_backup_oldest", idx=b['index']) if b['index'] == 5 else f"#{b['index']}")
                tree.insert("", "end", iid=str(b['index']), values=(slot_label, b['filename'], b['modified_str'], f"{b['size_bytes']} B"))

        combo.bind("<<ComboboxSelected>>", lambda e: populate_tree())
        populate_tree()

        # Action buttons
        btn_frame = ttk.Frame(dlg, padding="16 8 16 16")
        btn_frame.pack(fill=tk.X)

        def restore_selected():
            sel = tree.selection()
            if not sel or sel[0] not in [str(i) for i in range(1, 6)]:
                messagebox.showwarning(t("msg_warning"), t("msg_select_backup_row"), parent=dlg)
                return
            idx = int(sel[0])
            curr_target = file_choices[file_var.get()]
            fname = os.path.basename(curr_target)
            if not messagebox.askyesno(
                t("msg_warning"),
                t("confirm_restore_backup", idx=idx, filename=fname),
                parent=dlg,
            ):
                return
            if restore_backup(curr_target, backup_index=idx):
                messagebox.showinfo(t("msg_success"), t("msg_backup_restored_success", idx=idx), parent=dlg)
                # Reload data in memory
                if curr_target == PORTFOLIO_CSV:
                    self.holdings = load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
                    self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
                    self._on_portfolio_selected()
                elif curr_target == TRANSACTION_HISTORY_CSV:
                    self.transactions = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=None, tx_type=None)
                    self._refresh_sales_table()
                populate_tree()
                self._set_status(f"Restored {fname} from backup #{idx}.")
            else:
                messagebox.showerror(t("msg_error"), t("msg_backup_restore_failed"), parent=dlg)

        def open_folder():
            os.makedirs(BACKUP_DIR, exist_ok=True)
            webbrowser.open(f"file://{os.path.abspath(BACKUP_DIR)}")

        btn_restore = tk.Button(
            btn_frame,
            text=t("btn_backup_restore"),
            font=("Segoe UI", 9, "bold"),
            bg="#1a73e8",
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=4,
            command=restore_selected,
        )
        btn_restore.pack(side=tk.LEFT, padx=(0, 8))

        btn_folder = tk.Button(
            btn_frame,
            text=t("btn_backup_open_folder"),
            font=("Segoe UI", 9),
            relief="solid",
            bd=1,
            padx=10,
            pady=4,
            command=open_folder,
        )
        btn_folder.pack(side=tk.LEFT)

        btn_close = tk.Button(
            btn_frame,
            text=t("btn_close"),
            font=("Segoe UI", 9),
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            command=dlg.destroy,
        )
        btn_close.pack(side=tk.RIGHT)

        dlg.update_idletasks()
        try:
            x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dlg.winfo_width() // 2)
            y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dlg.winfo_height() // 2)
            dlg.geometry(f"+{x}+{y}")
            dlg.grab_set()
        except Exception:
            pass

    def _show_alert_banner(self, msg: str):
        if hasattr(self, "lbl_status"):
            self.lbl_status.config(text=f"🔔 {msg}", fg=self.red_color)

    def _open_column_selector(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_column_selector_title"))
        dlg.geometry("360x520")
        dlg.transient(self.root)

        all_cols = [
            ("portfolio", t("col_portfolio")),
            ("symbol", t("col_symbol")),
            ("name", t("col_name")),
            ("currency", t("col_currency")),
            ("shares", t("col_shares")),
            ("buy_price", t("col_buy_price")),
            ("current_price", t("col_current_price")),
            ("change", t("col_day_change")),
            ("market_value", t("col_market_value")),
            ("cost_basis", t("col_cost_basis")),
            ("unrealized_gain", t("col_unrealized_gain")),
            ("unrealized_gain_pct", t("col_unrealized_pct")),
            ("stop_loss", t("col_stop_loss")),
            ("target_sell", t("col_target_sell")),
            ("div_yield", t("col_dividend_yield")),
            ("annual_div", t("col_annual_div")),
            ("updated", t("col_last_updated")),
        ]

        if not self.visible_columns:
            self.visible_columns = [c[0] for c in all_cols]

        vars_dict = {}
        tk.Label(dlg, text=t("dlg_column_selector_title"), font=("Segoe UI", 10, "bold"), pady=8).pack()

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        for col_id, col_name in all_cols:
            var = tk.BooleanVar(value=(col_id in self.visible_columns))
            vars_dict[col_id] = var
            chk = ttk.Checkbutton(frame, text=f"{col_name} ({col_id})", variable=var)
            chk.pack(anchor="w", pady=2)

        def save_cols():
            chosen = [c[0] for c in all_cols if vars_dict[c[0]].get()]
            if not chosen:
                chosen = [c[0] for c in all_cols]
            self.visible_columns = chosen
            save_settings({"visible_columns": chosen})
            self.holdings_tree["displaycolumns"] = chosen
            dlg.destroy()
            messagebox.showinfo(t("dlg_columns_title"), t("msg_columns_saved"), parent=self.root)

        btn_box = ttk.Frame(dlg, padding=10)
        btn_box.pack(fill=tk.X)
        tk.Button(btn_box, text=t("btn_save"), bg=self.primary_color, fg="#ffffff", font=("Segoe UI", 9, "bold"), command=save_cols, padx=12, pady=4).pack(side=tk.RIGHT, padx=4)
        tk.Button(btn_box, text=t("btn_cancel"), command=dlg.destroy, padx=8, pady=4).pack(side=tk.RIGHT)

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 360, 520
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _switch_to_watchlist_tab(self):
        if hasattr(self, "notebook") and hasattr(self, "tab_watchlist"):
            self.notebook.select(self.tab_watchlist)
            self._refresh_watchlist_tab()
            self._check_and_fetch_missing_watchlist_quotes()

    def _check_and_fetch_missing_watchlist_quotes(self):
        if getattr(self, "is_fetching", False):
            return
        items = load_watchlist()
        if not items:
            return
        cached = getattr(self, "_watchlist_quotes_cache", {})

        def has_valid_quote(sym, it_name=""):
            if sym in cached:
                q = cached[sym]
                price = float(q.get("price", 0.0) or 0.0)
                q_name = str(q.get("name", "")).strip()
                has_name = (it_name and it_name.upper() != sym) or (q_name and q_name.upper() != sym)
                if price > 0 and q.get("last_updated") and q.get("change_percent") != -0.83 and has_name:
                    return True
            for h in getattr(self, "all_holdings", []):
                if str(h.get("symbol", "")).strip().upper() == sym and float(h.get("current_price", 0.0) or 0.0) > 0 and h.get("last_updated"):
                    h_name = str(h.get("name", "")).strip()
                    if (it_name and it_name.upper() != sym) or (h_name and h_name.upper() != sym):
                        return True
            return False

        missing = [
            it.get("symbol", "").strip().upper()
            for it in items
            if it.get("symbol") and not has_valid_quote(it.get("symbol").strip().upper(), str(it.get("name", "")).strip())
        ]
        if missing:
            self.fetch_all_quotes()

    def _open_watchlist_dialog(self):
        self._switch_to_watchlist_tab()

    def _build_watchlist_tab(self):
        self._watchlist_quotes_cache = load_watchlist_quotes_cache()
        self._watchlist_sort_col = "symbol"
        self._watchlist_sort_desc = False

        container = ttk.Frame(self.tab_watchlist, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        # Toolbar Frame
        b_color = getattr(self, "border_color", "#dadce0")
        toolbar = tk.Frame(container, bg=self.card_bg, padx=8, pady=8, highlightthickness=1, highlightbackground=b_color)
        toolbar.pack(fill=tk.X, pady=(0, 8))

        # Search / Filter
        self.lbl_watch_search = tk.Label(toolbar, text=f"🔍 {t('lbl_watch_search')}:", font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.text_dark)
        self.lbl_watch_search.pack(side=tk.LEFT, padx=(0, 4))
        self.watchlist_search_var = tk.StringVar()
        self.watchlist_search_var.trace_add("write", lambda *args: self._refresh_watchlist_tab())
        self.watchlist_search_entry = tk.Entry(toolbar, textvariable=self.watchlist_search_var, width=15, font=("Segoe UI", 9), relief="solid", bd=1)
        self.watchlist_search_entry.pack(side=tk.LEFT, padx=(0, 2))
        self.watchlist_search_entry.bind("<Escape>", lambda e: self._clear_watchlist_search())

        self.btn_watch_clear = tk.Button(
            toolbar,
            text="✕",
            font=("Segoe UI", 8),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg=self.text_dark,
            relief="solid",
            bd=1,
            padx=4,
            pady=1,
            command=self._clear_watchlist_search,
        )
        self.btn_watch_clear.pack(side=tk.LEFT, padx=(0, 8))

        # Tag Filter
        self.lbl_watch_tag = tk.Label(toolbar, text=f"{t('lbl_watchlist_tags')}", font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.text_dark)
        self.lbl_watch_tag.pack(side=tk.LEFT, padx=(0, 4))
        self.watchlist_tag_combo = ttk.Combobox(toolbar, textvariable=self.watchlist_tag_filter_var, state="readonly", width=12)
        self.watchlist_tag_combo.set(t("btn_filter_tag_all"))
        self.watchlist_tag_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.watchlist_tag_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_watchlist_tab())

        # Action Buttons
        self.btn_watch_add = tk.Button(
            toolbar,
            text=t("btn_add_watchlist"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            activebackground="#1557b0",
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._open_add_watchlist_dialog,
        )
        self.btn_watch_add.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_watch_batch = tk.Button(
            toolbar,
            text=t("btn_batch_import"),
            font=("Segoe UI", 9, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._open_batch_watchlist_dialog,
        )
        self.btn_watch_batch.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_watch_edit = tk.Button(
            toolbar,
            text=f"✏️ {t('btn_edit_watchlist')}",
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg=self.primary_color,
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._open_edit_watchlist_dialog,
        )
        self.btn_watch_edit.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_watch_category = tk.Button(
            toolbar,
            text=t("btn_change_category"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg=self.primary_color,
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._open_batch_change_category_dialog,
        )
        self.btn_watch_category.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_watch_refresh = tk.Button(
            toolbar,
            text=t("btn_refresh"),
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg=self.text_dark,
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._refresh_watchlist_quotes,
        )
        self.btn_watch_refresh.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_watch_buy = tk.Button(
            toolbar,
            text=t("btn_buy_into_portfolio"),
            font=("Segoe UI", 9, "bold"),
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._buy_from_watchlist_into_portfolio,
        )
        self.btn_watch_buy.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_watch_remove = tk.Button(
            toolbar,
            text=t("btn_remove_watchlist"),
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg=self.red_color,
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._remove_selected_watchlist,
        )
        self.btn_watch_remove.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_watch_export = tk.Button(
            toolbar,
            text=t("btn_export_csv"),
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg=self.text_dark,
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._export_watchlist_csv,
        )
        self.btn_watch_export.pack(side=tk.LEFT, padx=(0, 8))

        # Attach hints / tooltips
        attach_tooltip(self.watchlist_search_entry, "tip_watch_search")
        attach_tooltip(self.watchlist_tag_combo, "tip_watch_tag")
        attach_tooltip(self.btn_watch_add, "tip_watch_add")
        attach_tooltip(self.btn_watch_batch, "tip_watch_batch")
        attach_tooltip(self.btn_watch_edit, "tip_watch_edit")
        attach_tooltip(self.btn_watch_category, "tip_watch_category")
        attach_tooltip(self.btn_watch_refresh, "tip_watch_refresh")
        attach_tooltip(self.btn_watch_buy, "tip_watch_buy")
        attach_tooltip(self.btn_watch_remove, "tip_watch_remove")
        attach_tooltip(self.btn_watch_export, "tip_watch_export")

        # Stats Badge (right side)
        self.lbl_watchlist_stats = tk.Label(
            toolbar,
            text="",
            font=("Segoe UI", 9, "bold"),
            bg=self.card_bg,
            fg=self.primary_color,
        )
        self.lbl_watchlist_stats.pack(side=tk.RIGHT, padx=6)

        # Table Frame
        tree_frame = ttk.Frame(container)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = (
            "symbol",
            "name",
            "tags",
            "current",
            "change_pct",
            "target",
            "diff",
            "pe_ratio",
            "52w_range",
            "div_yield",
            "status",
            "currency",
            "updated",
            "added_date",
            "notes",
        )
        self.watchlist_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")

        cur_lang = get_current_language()
        cur_trans = TRANSLATIONS.get(cur_lang, {})
        col_configs = [
            ("symbol", t("col_watch_symbol"), 90, "center"),
            ("name", t("col_watch_name"), 160, "w"),
            ("tags", t("lbl_watchlist_tags"), 80, "center"),
            ("current", t("col_watch_current"), 95, "e"),
            ("change_pct", t("col_day_change_pct"), 85, "e"),
            ("target", t("col_watch_target"), 95, "e"),
            ("diff", t("col_watch_diff"), 90, "e"),
            ("pe_ratio", t("col_pe_ratio"), 70, "e"),
            ("52w_range", t("col_52w_range"), 115, "center"),
            ("div_yield", t("col_dividend_yield") if "col_dividend_yield" in cur_trans else "殖利率", 75, "e"),
            ("status", t("col_watch_status"), 110, "center"),
            ("currency", t("col_currency"), 65, "center"),
            ("updated", t("col_last_updated"), 135, "center"),
            ("added_date", t("col_watch_added"), 95, "center"),
            ("notes", t("col_notes"), 120, "w"),
        ]

        for cid, title, width, anchor in col_configs:
            self.watchlist_tree.heading(cid, text=title, command=lambda c=cid: self._sort_watchlist_column(c))
            self.watchlist_tree.column(cid, width=width, anchor=anchor)

        v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.watchlist_tree.yview)
        self.watchlist_tree.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        h_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.watchlist_tree.xview)
        self.watchlist_tree.configure(xscrollcommand=h_scroll.set)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.watchlist_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Watchlist Row Color Tags: Gains, Losses, and Target Reached Alerts
        bg_hit = "#e6f4ea" if not self.dark_mode else "#183b27"
        self.watchlist_tree.tag_configure("positive", foreground=self.green_color, font=("Segoe UI", 9, "bold"))
        self.watchlist_tree.tag_configure("negative", foreground=self.red_color, font=("Segoe UI", 9, "bold"))
        self.watchlist_tree.tag_configure("neutral", foreground=self.text_dark)
        self.watchlist_tree.tag_configure("reached_positive", foreground=self.green_color, background=bg_hit, font=("Segoe UI", 9, "bold"))
        self.watchlist_tree.tag_configure("reached_negative", foreground=self.red_color, background=bg_hit, font=("Segoe UI", 9, "bold"))
        self.watchlist_tree.tag_configure("reached", foreground=self.green_color, background=bg_hit, font=("Segoe UI", 9, "bold"))
        self.watchlist_tree.tag_configure("above", foreground=self.text_dark)
        self.watchlist_tree.tag_configure("normal", foreground=self.text_dark)

        # Context Menu & Click Bindings
        self.watchlist_tree.bind("<<TreeviewSelect>>", self._on_watchlist_select)
        self.watchlist_tree.bind("<Double-1>", self._on_watchlist_double_click)
        self.watchlist_tree.bind("<Button-3>", self._on_watchlist_right_click)

        self.watchlist_menu = tk.Menu(self.root, tearoff=0)
        self.watchlist_menu.add_command(label=f"📊 {t('btn_view_full_stats')}", command=self._show_watchlist_stock_stats_dialog)
        self.watchlist_menu.add_command(label=f"➕ {t('btn_buy_into_portfolio')}", command=self._buy_from_watchlist_into_portfolio)
        self.watchlist_menu.add_command(label=f"✏️ {t('btn_edit_watchlist')}", command=self._open_edit_watchlist_dialog)
        self.watchlist_menu.add_command(label=f"🏷️ {t('btn_change_category')}", command=self._open_batch_change_category_dialog)
        self.watchlist_menu.add_command(label=f"📈 {t('tab_chart')}", command=self._view_watchlist_chart)
        self.watchlist_menu.add_separator()
        self.watchlist_menu.add_command(label=f"🗑️ {t('btn_remove_watchlist')}", command=self._remove_selected_watchlist)

        # Stock Statistics & Metrics Card (Bottom of Watchlist Tab)
        self.watch_stats_frame = tk.Frame(
            container,
            bg=self.card_bg,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=b_color,
        )
        self.watch_stats_frame.pack(fill=tk.X, pady=(8, 0))

        stats_top = tk.Frame(self.watch_stats_frame, bg=self.card_bg)
        stats_top.pack(fill=tk.X, pady=(0, 4))

        self.lbl_watch_stats_title = tk.Label(
            stats_top,
            text=f"📊 {t('lbl_watch_details')}",
            font=("Segoe UI", 9, "bold"),
            bg=self.card_bg,
            fg=self.primary_color,
        )
        self.lbl_watch_stats_title.pack(side=tk.LEFT)

        self.btn_view_full_stats = tk.Button(
            stats_top,
            text=f"📈 {t('btn_view_full_stats')}",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg=self.primary_color,
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            cursor="hand2",
            command=self._show_watchlist_stock_stats_dialog,
        )
        self.btn_view_full_stats.pack(side=tk.RIGHT)

        self.watch_metrics_box = tk.Frame(self.watch_stats_frame, bg=self.card_bg)
        self.watch_metrics_box.pack(fill=tk.X, pady=(2, 0))

        self.lbl_watch_metrics_content = tk.Label(
            self.watch_metrics_box,
            text=t("lbl_watch_no_selection"),
            font=("Segoe UI", 9),
            bg=self.card_bg,
            fg=self.text_muted,
            justify=tk.LEFT,
        )
        self.lbl_watch_metrics_content.pack(anchor="w")

        self._refresh_watchlist_tab()

    def _sort_watchlist_column(self, col: str):
        if self._watchlist_sort_col == col:
            self._watchlist_sort_desc = not self._watchlist_sort_desc
        else:
            self._watchlist_sort_col = col
            self._watchlist_sort_desc = False
        self._refresh_watchlist_tab()

    def _on_watchlist_select(self, event=None):
        self._update_watchlist_stats_panel()

    def _update_watchlist_stats_panel(self):
        if not hasattr(self, "watch_stats_frame") or not hasattr(self, "lbl_watch_metrics_content"):
            return
        sel = self.watchlist_tree.selection()
        if not sel:
            self.lbl_watch_metrics_content.config(text=t("lbl_watch_no_selection"), fg=self.text_muted)
            return

        item_vals = self.watchlist_tree.item(sel[0], "values")
        if not item_vals:
            return

        sym = item_vals[0].strip().upper()
        name = item_vals[1] if len(item_vals) > 1 else sym
        curr_price = item_vals[3] if len(item_vals) > 3 else "-"
        chg_pct = item_vals[4] if len(item_vals) > 4 else "-"
        tgt_price = item_vals[5] if len(item_vals) > 5 else "-"
        diff_pct = item_vals[6] if len(item_vals) > 6 else "-"
        pe_str = item_vals[7] if len(item_vals) > 7 else "-"
        range_52w = item_vals[8] if len(item_vals) > 8 else "-"
        div_yield_str = item_vals[9] if len(item_vals) > 9 else "-"
        status_txt = item_vals[10] if len(item_vals) > 10 else "-"
        curr_code = item_vals[11] if len(item_vals) > 11 else "USD"
        last_upd = item_vals[12] if len(item_vals) > 12 else "-"

        q = getattr(self, "_watchlist_quotes_cache", {}).get(sym, {})
        full_sym = q.get("symbol", sym)
        mkt_cap = q.get("market_cap", "N/A")
        vol = q.get("volume", "N/A")
        ann_div = q.get("annual_dividend_per_share", 0.0) or 0.0
        ex_div = q.get("ex_dividend_date", "N/A")
        chg_val = q.get("change")
        if q.get("pe_ratio") is not None:
            pe_str = f"{float(q['pe_ratio']):.2f}"

        chg_val_str = f"{chg_val:+.2f}" if chg_val is not None else ""
        day_chg_full = f"{chg_val_str} ({chg_pct})" if chg_val_str else chg_pct
        if chg_val is not None:
            c_prefix = "🟢 ▲ " if float(chg_val) > 0 else ("🔴 ▼ " if float(chg_val) < 0 else "")
            day_chg_full = f"{c_prefix}{day_chg_full}"
        elif "+" in chg_pct:
            day_chg_full = f"🟢 ▲ {day_chg_full}"
        elif "-" in chg_pct and chg_pct != "-":
            day_chg_full = f"🔴 ▼ {day_chg_full}"

        cur_lang = get_current_language()
        is_zh = cur_lang in ("zh_TW", "zh_CN")
        p_label = "現價" if is_zh else "Price"
        c_label = "今日漲跌" if is_zh else "Day Change"
        pe_label = "本益比 (P/E)" if is_zh else "P/E Ratio"
        mc_label = "市值" if is_zh else "Mkt Cap"
        r_label = "52週區間" if is_zh else "52W Range"
        dy_label = "股息殖利率" if is_zh else "Div Yield"
        vol_label = "成交量" if is_zh else "Volume"
        tgt_label = "目標價" if is_zh else "Target"
        upd_label = "最後更新" if is_zh else "Updated"

        line1 = f"📌 {sym} ({name} · {full_sym})  |  {p_label}: {curr_price} {curr_code}  |  {c_label}: {day_chg_full}  |  {pe_label}: {pe_str}  |  {mc_label}: {mkt_cap}"
        line2 = f"📅 {r_label}: {range_52w}  |  {dy_label}: {div_yield_str} (${ann_div:.2f}/年, Ex: {ex_div})  |  {vol_label}: {vol}  |  {tgt_label}: {tgt_price} ({diff_pct}) [{status_txt}]  |  {upd_label}: {last_upd}"

        self.lbl_watch_metrics_content.config(
            text=f"{line1}\n{line2}",
            fg=self.text_dark,
        )

    def _show_watchlist_stock_stats_dialog(self):
        sel = self.watchlist_tree.selection()
        if not sel:
            messagebox.showinfo(t("tab_monitoring"), t("lbl_watch_no_selection"), parent=self.root)
            return

        item_vals = self.watchlist_tree.item(sel[0], "values")
        if not item_vals:
            return

        sym = item_vals[0].strip().upper()
        q = getattr(self, "_watchlist_quotes_cache", {}).get(sym, {})
        if not q:
            messagebox.showinfo(t("tab_monitoring"), f"No cached quote data for {sym}. Please click Refresh Quotes.", parent=self.root)
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(f"📊 {sym} - Google Finance 完整統計數據")
        dlg.geometry("560x520")
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        header = tk.Label(frame, text=f"{q.get('name', sym)} ({q.get('symbol', sym)})", font=("Segoe UI", 12, "bold"), fg=self.primary_color)
        header.pack(anchor="w", pady=(0, 4))

        sub = tk.Label(frame, text=f"現價: ${q.get('price', 0.0):,.2f} {q.get('currency', 'USD')}  |  更新時間: {q.get('last_updated', q.get('timestamp', 'N/A'))}", font=("Segoe UI", 9, "bold"))
        sub.pack(anchor="w", pady=(0, 10))

        tree_s = ttk.Treeview(frame, columns=("stat", "val"), show="headings", height=14)
        tree_s.heading("stat", text="指標名稱 (Metric)")
        tree_s.heading("val", text="數值 (Value)")
        tree_s.column("stat", width=220, anchor="w")
        tree_s.column("val", width=260, anchor="w")
        tree_s.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        raw_stats = q.get("raw_stats", {})
        stat_rows = [
            ("Current Price", f"${q.get('price', 0.0):,.2f} {q.get('currency', 'USD')}"),
            ("Day Change", f"{q.get('change', 0.0):+,.2f} ({q.get('change_percent', 0.0):+,.2f}%)"),
            ("P/E Ratio", str(q.get("pe_ratio") or raw_stats.get("P/E ratio") or "N/A")),
            ("52-Week High", f"${q.get('52_week_high', 0.0):,.2f}" if q.get("52_week_high") else "N/A"),
            ("52-Week Low", f"${q.get('52_week_low', 0.0):,.2f}" if q.get("52_week_low") else "N/A"),
            ("Market Cap", str(q.get("market_cap") or raw_stats.get("Mkt. cap") or "N/A")),
            ("Volume", str(q.get("volume") or raw_stats.get("Volume") or "N/A")),
            ("Avg Volume", str(raw_stats.get("Avg. vol.") or "N/A")),
            ("Dividend Yield", f"{q.get('dividend_yield', 0.0):.2f}%" if q.get("dividend_yield") else "N/A"),
            ("Annual Dividend / Share", f"${q.get('annual_dividend_per_share', 0.0):.4f}" if q.get("annual_dividend_per_share") else "N/A"),
            ("Ex-Dividend Date", str(q.get("ex_dividend_date") or raw_stats.get("Ex-dividend date") or "N/A")),
            ("EPS", str(raw_stats.get("EPS") or "N/A")),
            ("Beta", str(raw_stats.get("Beta") or "N/A")),
            ("Shares Outstanding", str(raw_stats.get("Shares outstanding") or "N/A")),
            ("Google Finance Timestamp", str(q.get("timestamp") or "N/A")),
            ("Last App Sync Time", str(q.get("last_updated") or "N/A")),
        ]
        for k, v in raw_stats.items():
            if k not in ["P/E ratio", "Mkt. cap", "Volume", "Avg. vol.", "EPS", "Beta", "Shares outstanding", "Dividend", "Ex-dividend date", "52-wk high", "52-wk low"]:
                stat_rows.append((k, str(v)))

        for s_name, s_val in stat_rows:
            tree_s.insert("", tk.END, values=(s_name, s_val))

        btn_bar = ttk.Frame(frame)
        btn_bar.pack(fill=tk.X)

        url = q.get("url")
        if url:
            btn_web = tk.Button(btn_bar, text="🌐 開啟 Google Finance 網頁", font=("Segoe UI", 9), command=lambda: webbrowser.open(url))
            btn_web.pack(side=tk.LEFT)

        btn_close = tk.Button(btn_bar, text=t("btn_close") if "btn_close" in TRANSLATIONS.get(get_current_language(), {}) else "Close", font=("Segoe UI", 9), command=dlg.destroy)
        btn_close.pack(side=tk.RIGHT)

    def _clear_watchlist_search(self):
        self.watchlist_search_var.set("")
        self._refresh_watchlist_tab()
        if hasattr(self, "watchlist_search_entry"):
            self.watchlist_search_entry.focus_set()

    def _refresh_watchlist_tab(self):
        if not hasattr(self, "watchlist_tree"):
            return

        # Capture current selection (symbols) to preserve across refresh
        selected_symbols = set()
        try:
            for sid in self.watchlist_tree.selection():
                vals = self.watchlist_tree.item(sid, "values")
                if vals:
                    selected_symbols.add(str(vals[0]).strip().upper())
        except Exception:
            pass

        items = load_watchlist()
        q_filter = self.watchlist_search_var.get().strip().upper() if hasattr(self, "watchlist_search_var") else ""
        selected_tag = self.watchlist_tag_filter_var.get().strip() if hasattr(self, "watchlist_tag_filter_var") else ""

        all_tags = set()
        for row in items:
            t_str = str(row.get("tags", "")).strip()
            if t_str:
                for tg in t_str.replace(";", ",").split(","):
                    tg_clean = tg.strip()
                    if tg_clean:
                        all_tags.add(tg_clean)

        if hasattr(self, "watchlist_tag_combo"):
            current_choice = self.watchlist_tag_filter_var.get()
            tag_vals = [t("btn_filter_tag_all")] + sorted(list(all_tags))
            self.watchlist_tag_combo["values"] = tag_vals
            if current_choice not in tag_vals:
                self.watchlist_tag_combo.set(t("btn_filter_tag_all"))

        rows = []
        target_reached_count = 0
        watchlist_dirty = False

        for row in items:
            sym = str(row.get("symbol", "")).strip().upper()
            if not sym:
                continue
            name = str(row.get("name", "")).strip()
            tags = str(row.get("tags", "")).strip()
            tgt = float(row.get("target_buy_price", 0.0) or 0.0)
            curr_code = str(row.get("currency", "USD") or "USD").upper()
            notes = str(row.get("notes", "")).strip()
            added_date = str(row.get("added_date", "")).strip()

            curr_price = 0.0
            day_change_val = None
            day_change_pct = None
            last_updated_str = ""
            pe_val = None
            div_yield_val = None
            range_52w_str = "-"

            # 1. Check quotes cache
            if sym in self._watchlist_quotes_cache:
                q = self._watchlist_quotes_cache[sym]
                curr_price = float(q.get("price", 0.0) or 0.0)
                if (not name or name.strip().upper() == sym) and q.get("name") and q.get("name").strip().upper() != sym:
                    name = q.get("name").strip()
                    row["name"] = name
                    watchlist_dirty = True
                if q.get("currency"):
                    curr_code = q.get("currency")
                    if not row.get("currency") or row.get("currency") == "USD":
                        row["currency"] = curr_code
                        watchlist_dirty = True
                day_change_val = q.get("change")
                day_change_pct = q.get("change_percent") or q.get("change_pct")
                last_updated_str = q.get("last_updated") or q.get("timestamp", "")
                pe_val = q.get("pe_ratio")
                div_yield_val = q.get("dividend_yield")
                h52 = q.get("52_week_high")
                l52 = q.get("52_week_low")
                if h52 is not None and l52 is not None:
                    range_52w_str = f"${l52:.2f} - ${h52:.2f}"

            # 2. Check all holdings if not found or price <= 0 or name needs resolving
            for h in getattr(self, "all_holdings", getattr(self, "holdings", [])):
                if str(h.get("symbol", "")).strip().upper() == sym:
                    hp = float(h.get("current_price", 0.0) or 0.0)
                    if hp > 0 and curr_price <= 0:
                        curr_price = hp
                        if day_change_pct is None:
                            day_change_pct = h.get("change_percent")
                        if day_change_val is None:
                            day_change_val = h.get("change")
                    if (not name or name.strip().upper() == sym) and h.get("name") and h.get("name").strip().upper() != sym:
                        name = h.get("name").strip()
                        row["name"] = name
                        watchlist_dirty = True
                    if h.get("currency") and (not row.get("currency") or row.get("currency") == "USD"):
                        curr_code = h.get("currency")
                        row["currency"] = curr_code
                        watchlist_dirty = True
                    if not last_updated_str and h.get("last_updated"):
                        last_updated_str = h.get("last_updated")
                    if div_yield_val is None and h.get("dividend_yield") is not None:
                        div_yield_val = h.get("dividend_yield")
                    break

            if not last_updated_str:
                last_updated_str = added_date if added_date else "-"

            # Parse day change percentage & dollar value
            c_flt = None
            if day_change_pct is not None:
                try:
                    c_flt = float(day_change_pct)
                except (ValueError, TypeError):
                    pass
            if c_flt is None and day_change_val is not None:
                try:
                    c_val = float(day_change_val)
                    if curr_price > 0 and (curr_price - c_val) > 0:
                        c_flt = (c_val / (curr_price - c_val)) * 100.0
                    else:
                        c_flt = c_val
                except (ValueError, TypeError):
                    pass

            change_pct_str = "-"
            if c_flt is not None:
                change_pct_str = f"{c_flt:+.2f}%"

            # Parse target price & distance
            target_reached = False
            diff_str = "-"
            diff_val = 999999.0
            status_str = t("status_monitoring")

            if curr_price > 0 and tgt > 0:
                diff_pct = ((curr_price - tgt) / tgt) * 100.0
                diff_val = diff_pct
                diff_str = f"{diff_pct:+.2f}%"
                if curr_price <= tgt:
                    target_reached = True
                    status_str = t("status_target_reached")
                    target_reached_count += 1
            elif tgt > 0:
                status_str = t("status_monitoring")

            # Determine colorful row tag based on price raise/drop and target status
            if target_reached:
                if c_flt is not None and c_flt > 0:
                    tag = "reached_positive"
                elif c_flt is not None and c_flt < 0:
                    tag = "reached_negative"
                else:
                    tag = "reached"
            else:
                if c_flt is not None and c_flt > 0:
                    tag = "positive"
                elif c_flt is not None and c_flt < 0:
                    tag = "negative"
                elif curr_price > 0 and tgt > 0 and curr_price > tgt:
                    tag = "above"
                else:
                    tag = "neutral"

            pe_display = f"{float(pe_val):.1f}" if pe_val is not None else "-"
            div_display = f"{float(div_yield_val):.2f}%" if div_yield_val is not None and float(div_yield_val) > 0 else "-"
            tgt_display = f"${tgt:.2f}" if tgt > 0 else "-"
            curr_display = f"${curr_price:.2f}" if curr_price > 0 else "-"

            # Tag Filter check
            if selected_tag and selected_tag != t("btn_filter_tag_all") and selected_tag != "All":
                if selected_tag.upper() not in tags.upper():
                    continue

            # Text Search Filter check
            if q_filter:
                match_sym = q_filter in sym
                match_name = q_filter in name.upper()
                match_notes = q_filter in notes.upper()
                match_tags = q_filter in tags.upper()
                if not (match_sym or match_name or match_notes or match_tags):
                    continue

            rows.append({
                "symbol": sym,
                "name": name,
                "tags": tags,
                "current": curr_price,
                "curr_display": curr_display,
                "change_pct": change_pct_str,
                "day_change_raw": c_flt if c_flt is not None else -9999.0,
                "target": tgt,
                "tgt_display": tgt_display,
                "diff": diff_str,
                "diff_val": diff_val,
                "pe_display": pe_display,
                "pe_raw": float(pe_val) if pe_val is not None else 9999.0,
                "range_52w": range_52w_str,
                "div_display": div_display,
                "div_raw": float(div_yield_val) if div_yield_val is not None else -1.0,
                "status": status_str,
                "currency": curr_code,
                "updated": last_updated_str,
                "added_date": added_date,
                "notes": notes,
                "tag": tag,
            })

        # Sort rows
        sort_col = getattr(self, "_watchlist_sort_col", "symbol")
        reverse = getattr(self, "_watchlist_sort_desc", False)

        def sort_key(r):
            if sort_col == "current":
                return r["current"]
            elif sort_col == "target":
                return r["target"]
            elif sort_col == "diff":
                return r["diff_val"]
            elif sort_col == "change_pct":
                return r["day_change_raw"]
            elif sort_col == "pe_ratio":
                return r["pe_raw"]
            elif sort_col == "div_yield":
                return r["div_raw"]
            elif sort_col == "updated":
                return r["updated"]
            elif sort_col == "added_date":
                return r["added_date"]
            return str(r.get(sort_col, "")).lower()

        rows.sort(key=sort_key, reverse=reverse)

        raw_children = self.watchlist_tree.get_children()
        existing_items = set(raw_children) if isinstance(raw_children, (list, tuple, set)) else set()
        kept_items = set()

        for idx, r in enumerate(rows):
            item_id = f"wl_{r['symbol']}"
            kept_items.add(item_id)
            row_vals = (
                r["symbol"],
                r["name"],
                r["tags"],
                r["curr_display"],
                r["change_pct"],
                r["tgt_display"],
                r["diff"],
                r["pe_display"],
                r["range_52w"],
                r["div_display"],
                r["status"],
                r["currency"],
                r["updated"],
                r["added_date"],
                r["notes"],
            )
            row_tags = (r["tag"],)

            if item_id in existing_items:
                self.watchlist_tree.item(item_id, values=row_vals, tags=row_tags)
                try:
                    self.watchlist_tree.move(item_id, "", idx)
                except Exception:
                    pass
            else:
                try:
                    self.watchlist_tree.insert(
                        "",
                        idx,
                        iid=item_id,
                        values=row_vals,
                        tags=row_tags,
                    )
                except TypeError:
                    self.watchlist_tree.insert(
                        "",
                        idx,
                        values=row_vals,
                        tags=row_tags,
                    )

        # Remove any items that are no longer present
        for old_id in existing_items - kept_items:
            try:
                self.watchlist_tree.delete(old_id)
            except Exception:
                pass

        # Restore selection
        to_select = [f"wl_{s}" for s in selected_symbols if f"wl_{s}" in kept_items]
        if to_select:
            try:
                self.watchlist_tree.selection_set(to_select)
            except Exception:
                pass

        if hasattr(self, "lbl_watchlist_stats"):
            total_items = len(rows)
            gainers_count = sum(1 for r in rows if r["day_change_raw"] > 0)
            losers_count = sum(1 for r in rows if -9990.0 < r["day_change_raw"] < 0)
            stats_txt = f"{t('tab_monitoring')}: {total_items} (📈 {gainers_count}  📉 {losers_count})  |  {t('status_target_reached')}: {target_reached_count}"
            if getattr(self, "is_fetching", False):
                stats_txt += f"  |  🔄 {t('msg_updating_background')}"
            self.lbl_watchlist_stats.config(text=stats_txt)

        if watchlist_dirty:
            try:
                save_watchlist(items, WATCHLIST_CSV)
            except Exception:
                pass

        self._update_watchlist_stats_panel()

    def _refresh_watchlist_quotes(self):
        items = load_watchlist()
        if not items:
            messagebox.showinfo(t("tab_monitoring"), t("msg_watchlist_empty"), parent=self.root)
            return

        if getattr(self, "is_fetching", False):
            self._set_status("Quote refresh already in progress...")
            return

        if hasattr(self, "lbl_watchlist_stats"):
            self.lbl_watchlist_stats.config(text=t("msg_fetching_live_quotes"))

        self.fetch_all_quotes()

    def _open_add_watchlist_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("btn_add_watchlist"))
        dlg.geometry("460x440")
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        # Quick-picks dropdown
        quick_box = ttk.Frame(frame)
        quick_box.pack(fill=tk.X, pady=(0, 4))
        tk.Label(quick_box, text=t("lbl_quick_picks"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        quick_cb = ttk.Combobox(quick_box, values=[p[0] for p in POPULAR_TICKERS], state="readonly", width=32)
        quick_cb.current(0)
        quick_cb.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(frame, text=t("col_watch_symbol") + " *:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        sym_box = ttk.Frame(frame)
        sym_box.pack(fill=tk.X, pady=(2, 6))

        sym_entry = tk.Entry(sym_box, font=("Segoe UI", 10, "bold"), bd=1, relief="solid")
        sym_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        sym_entry.focus_set()

        lbl_lookup = tk.Label(frame, text="", font=("Segoe UI", 8))

        lookup_data = {}

        def on_lookup():
            s = sym_entry.get().strip().upper()
            if not s:
                return
            lbl_lookup.config(text=t("msg_searching_gf_generic"), fg=self.primary_color)
            dlg.update()
            res = self.fetcher.search_or_verify_symbol(s)
            if res.get("valid"):
                name_entry.delete(0, tk.END)
                name_entry.insert(0, res.get("name", ""))
                curr_cb.set(res.get("currency", "USD"))
                lbl_lookup.config(text=f"✅ {res.get('name')} | {t('col_current_price')}: ${res.get('price', 0.0):.2f}", fg=self.green_color)
                lookup_data[s] = res
            else:
                lbl_lookup.config(text=f"⚠️ {res.get('error', 'Not found')}", fg=self.red_color)

        btn_lookup = tk.Button(sym_box, text=t("btn_lookup"), font=("Segoe UI", 9), command=on_lookup, padx=6)
        btn_lookup.pack(side=tk.RIGHT)
        lbl_lookup.pack(anchor="w", pady=(0, 4))

        def on_quick_select(e=None):
            idx = quick_cb.current()
            if idx > 0:
                _, s_val, c_val = POPULAR_TICKERS[idx]
                sym_entry.delete(0, tk.END)
                sym_entry.insert(0, s_val)
                curr_cb.set(c_val)
                on_lookup()

        quick_cb.bind("<<ComboboxSelected>>", on_quick_select)

        tk.Label(frame, text=t("col_watch_name") + ":", font=("Segoe UI", 9)).pack(anchor="w")
        name_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        name_entry.pack(fill=tk.X, pady=(2, 6))

        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=(2, 6))

        tgt_box = ttk.Frame(row2)
        tgt_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Label(tgt_box, text=t("col_watch_target") + " ($):", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tgt_entry = tk.Entry(tgt_box, font=("Segoe UI", 9), bd=1, relief="solid")
        tgt_entry.pack(fill=tk.X, pady=(2, 0))

        curr_box = ttk.Frame(row2)
        curr_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(curr_box, text=t("col_currency") + ":", font=("Segoe UI", 9)).pack(anchor="w")
        curr_cb = ttk.Combobox(curr_box, values=["USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY"], state="readonly", width=8)
        curr_cb.set("USD")
        curr_cb.pack(fill=tk.X, pady=(2, 0))

        tk.Label(frame, text=t("lbl_watchlist_tags") + ":", font=("Segoe UI", 9)).pack(anchor="w")
        tags_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        tags_entry.pack(fill=tk.X, pady=(2, 6))

        tk.Label(frame, text=t("col_notes") + ":", font=("Segoe UI", 9)).pack(anchor="w")
        notes_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        notes_entry.pack(fill=tk.X, pady=(2, 10))

        btn_box = ttk.Frame(frame)
        btn_box.pack(fill=tk.X, pady=(6, 0))

        def save_item():
            s = sym_entry.get().strip().upper()
            if not s:
                messagebox.showerror(t("dlg_error"), t("msg_enter_symbol"), parent=dlg)
                return
            n = name_entry.get().strip()
            if not n or n.upper() == s:
                if s in lookup_data and lookup_data[s].get("name"):
                    n = lookup_data[s]["name"]
                elif s in self._watchlist_quotes_cache and self._watchlist_quotes_cache[s].get("name"):
                    n = self._watchlist_quotes_cache[s]["name"]
            t_str = tgt_entry.get().strip()
            try:
                t_val = float(t_str) if t_str else 0.0
            except ValueError:
                t_val = 0.0
            c = curr_cb.get().strip() or "USD"
            notes = notes_entry.get().strip()
            tag_val = tags_entry.get().strip()

            add_to_watchlist(s, n, t_val, currency=c, notes=notes, tags=tag_val)
            if s in lookup_data and float(lookup_data[s].get("price", 0.0) or 0.0) > 0:
                self._watchlist_quotes_cache[s] = lookup_data[s]
                save_watchlist_quotes_cache(self._watchlist_quotes_cache)
            dlg.destroy()
            self._refresh_watchlist_tab()
            self.root.after(100, self._check_and_fetch_missing_watchlist_quotes)

        tk.Button(btn_box, text=t("btn_save_changes"), bg=self.primary_color, fg="#ffffff", font=("Segoe UI", 9, "bold"), command=save_item, padx=12, pady=4).pack(side=tk.RIGHT, padx=4)
        tk.Button(btn_box, text=t("btn_cancel"), command=dlg.destroy, padx=8, pady=4).pack(side=tk.RIGHT)

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 440, 360
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _open_edit_watchlist_dialog(self, item_vals=None):
        if not item_vals:
            sel = self.watchlist_tree.selection()
            if not sel:
                messagebox.showinfo(t("tab_monitoring"), t("msg_select_stock_to_edit"), parent=self.root)
                return
            item_vals = self.watchlist_tree.item(sel[0], "values")

        if isinstance(item_vals, dict):
            item_vals = item_vals.get("values", [])

        if not item_vals or len(item_vals) < 2:
            return

        old_sym = item_vals[0]
        init_name = item_vals[1]
        w_items = load_watchlist()
        match_item = next((it for it in w_items if str(it.get("symbol", "")).strip().upper() == str(old_sym).strip().upper()), {})
        init_tags = match_item.get("tags", "") or (item_vals[2] if len(item_vals) > 2 else "")
        target_str = str(match_item.get("target_buy_price", "")) if match_item.get("target_buy_price") else (item_vals[5].replace("$", "").replace("-", "").strip() if len(item_vals) > 5 else "")
        curr_code = match_item.get("currency", item_vals[8] if len(item_vals) > 8 else "USD")
        notes_str = match_item.get("notes", item_vals[9] if len(item_vals) > 9 else "")

        dlg = tk.Toplevel(self.root)
        dlg.title(f"{t('dlg_edit_watchlist_title')}: {old_sym}")
        dlg.geometry("460x480")
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        # Symbol entry + live verify button
        tk.Label(frame, text=t("col_watch_symbol") + " *:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        sym_box = ttk.Frame(frame)
        sym_box.pack(fill=tk.X, pady=(2, 4))

        sym_entry = tk.Entry(sym_box, font=("Segoe UI", 10, "bold"), bd=1, relief="solid")
        sym_entry.insert(0, old_sym)
        sym_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        lbl_lookup_edit = tk.Label(frame, text="", font=("Segoe UI", 8))

        def on_lookup_edit():
            s = sym_entry.get().strip().upper()
            if not s:
                return
            lbl_lookup_edit.config(text=t("msg_searching_gf_generic"), fg=self.primary_color)
            dlg.update()
            res = self.fetcher.search_or_verify_symbol(s)
            if res.get("valid"):
                name_entry.delete(0, tk.END)
                name_entry.insert(0, res.get("name", ""))
                if res.get("currency") and res["currency"] in curr_cb["values"]:
                    curr_cb.set(res["currency"])
                lbl_lookup_edit.config(text=f"✅ {res.get('name')} | {t('col_current_price')}: ${res.get('price', 0.0):.2f}", fg=self.green_color)
            else:
                lbl_lookup_edit.config(text=f"⚠️ {res.get('error', 'Not found')}", fg=self.red_color)

        btn_lookup = tk.Button(sym_box, text=t("btn_lookup"), font=("Segoe UI", 9), command=on_lookup_edit, padx=6)
        btn_lookup.pack(side=tk.RIGHT)
        lbl_lookup_edit.pack(anchor="w", pady=(0, 4))

        tk.Label(frame, text=t("col_watch_name") + ":", font=("Segoe UI", 9)).pack(anchor="w")
        name_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        name_entry.insert(0, init_name)
        name_entry.pack(fill=tk.X, pady=(2, 6))

        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=(2, 6))

        tgt_box = ttk.Frame(row2)
        tgt_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Label(tgt_box, text=t("col_watch_target") + " ($):", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tgt_entry = tk.Entry(tgt_box, font=("Segoe UI", 9), bd=1, relief="solid")
        tgt_entry.insert(0, target_str)
        tgt_entry.pack(fill=tk.X, pady=(2, 0))

        curr_box = ttk.Frame(row2)
        curr_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(curr_box, text=t("col_currency") + ":", font=("Segoe UI", 9)).pack(anchor="w")
        curr_cb = ttk.Combobox(curr_box, values=["USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY"], state="readonly", width=8)
        curr_cb.set(curr_code if curr_code in ["USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY"] else "USD")
        curr_cb.pack(fill=tk.X, pady=(2, 0))

        tk.Label(frame, text=t("lbl_watchlist_tags") + ":", font=("Segoe UI", 9)).pack(anchor="w")
        tags_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        tags_entry.insert(0, init_tags)
        tags_entry.pack(fill=tk.X, pady=(2, 6))

        tk.Label(frame, text=t("col_notes") + ":", font=("Segoe UI", 9)).pack(anchor="w")
        notes_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        notes_entry.insert(0, notes_str)
        notes_entry.pack(fill=tk.X, pady=(2, 10))

        btn_box = ttk.Frame(frame)
        btn_box.pack(fill=tk.X, pady=(6, 0))

        def save_edit():
            new_sym = sym_entry.get().strip().upper()
            if not new_sym:
                messagebox.showerror(t("dlg_error"), t("msg_enter_symbol"), parent=dlg)
                return
            new_name = name_entry.get().strip()
            if not new_name or new_name.upper() == new_sym:
                if new_sym in self._watchlist_quotes_cache and self._watchlist_quotes_cache[new_sym].get("name"):
                    new_name = self._watchlist_quotes_cache[new_sym]["name"]
                elif old_sym.upper() in self._watchlist_quotes_cache and self._watchlist_quotes_cache[old_sym.upper()].get("name"):
                    new_name = self._watchlist_quotes_cache[old_sym.upper()]["name"]
                else:
                    new_name = new_sym
            t_str = tgt_entry.get().strip()
            try:
                t_val = float(t_str) if t_str else 0.0
            except ValueError:
                t_val = 0.0
            c = curr_cb.get().strip() or "USD"
            n = notes_entry.get().strip()
            tag_val = tags_entry.get().strip()

            update_watchlist_item(old_sym, new_sym, new_name, t_val, currency=c, notes=n, tags=tag_val)

            if old_sym.upper() != new_sym.upper():
                self._watchlist_quotes_cache.pop(old_sym.upper(), None)
                save_watchlist_quotes_cache(self._watchlist_quotes_cache)

            if new_sym.upper() not in self._watchlist_quotes_cache:
                def fetch_one():
                    try:
                        q = self.fetcher.fetch_quote(new_sym)
                        if q.get("success"):
                            self._watchlist_quotes_cache[new_sym.upper()] = q
                            save_watchlist_quotes_cache(self._watchlist_quotes_cache)
                        else:
                            v = self.fetcher.search_or_verify_symbol(new_sym)
                            if v.get("valid"):
                                self._watchlist_quotes_cache[new_sym.upper()] = v
                                save_watchlist_quotes_cache(self._watchlist_quotes_cache)
                    except Exception:
                        pass
                    self.root.after(0, self._refresh_watchlist_tab)
                threading.Thread(target=fetch_one, daemon=True).start()

            dlg.destroy()
            self._refresh_watchlist_tab()

        tk.Button(btn_box, text=t("btn_save_changes"), bg=self.primary_color, fg="#ffffff", font=("Segoe UI", 9, "bold"), command=save_edit, padx=12, pady=4).pack(side=tk.RIGHT, padx=4)
        tk.Button(btn_box, text=t("btn_cancel"), command=dlg.destroy, padx=8, pady=4).pack(side=tk.RIGHT)

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 460, 420
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _open_batch_change_category_dialog(self):
        sel = self.watchlist_tree.selection()
        if not sel:
            messagebox.showinfo(
                t("tab_monitoring"),
                t("msg_select_stock_for_category"),
                parent=self.root,
            )
            return

        selected_symbols = []
        for it in sel:
            vals = self.watchlist_tree.item(it, "values")
            if vals:
                selected_symbols.append(str(vals[0]).strip().upper())

        if not selected_symbols:
            return

        # Fetch existing categories from watchlist for suggestions
        w_items = load_watchlist()
        existing_tags_set = set()
        for item in w_items:
            tg = str(item.get("tags", "")).strip()
            if tg:
                for sub in re.split(r"[,;]+", tg):
                    if sub.strip():
                        existing_tags_set.add(sub.strip())

        preset_tags = ["Tech", "Core", "Dividend", "Growth", "Value", "Speculative", "ETF", "Energy", "Healthcare", "Crypto"]
        for pt in preset_tags:
            existing_tags_set.add(pt)
        available_tags = sorted(list(existing_tags_set))

        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_change_category_title"))
        dlg.geometry("520x450")
        dlg.minsize(480, 400)
        dlg.transient(self.root)
        dlg.grab_set()

        bg_main = getattr(self, "bg_main", "#f4f6f9")
        card_bg = getattr(self, "card_bg", "#ffffff")
        text_dark = getattr(self, "text_dark", "#202124")
        text_muted = getattr(self, "text_muted", "#5f6368")
        primary_col = getattr(self, "primary_color", "#1a73e8")

        dlg.configure(bg=bg_main)

        # Header Box
        header_box = tk.Frame(dlg, bg=bg_main, padx=16, pady=12)
        header_box.pack(fill=tk.X)

        tk.Label(
            header_box,
            text=f"🏷️ {t('dlg_change_category_title')}",
            font=("Segoe UI", 12, "bold"),
            bg=bg_main,
            fg=primary_col,
        ).pack(anchor="w")

        # Container Card
        card = tk.Frame(dlg, bg=card_bg, bd=1, relief="solid", padx=16, pady=12)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))

        # Selected Stocks Info
        tk.Label(
            card,
            text=t("lbl_category_target_stocks", count=len(selected_symbols)),
            font=("Segoe UI", 9, "bold"),
            bg=card_bg,
            fg=text_dark,
        ).pack(anchor="w", pady=(0, 2))

        sym_display = ", ".join(selected_symbols)
        if len(sym_display) > 80:
            sym_display = sym_display[:77] + "..."
        tk.Label(
            card,
            text=sym_display,
            font=("Segoe UI", 9, "bold"),
            bg=card_bg,
            fg=primary_col,
            wraplength=460,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 10))

        # Category Input / Dropdown
        tk.Label(
            card,
            text=t("lbl_new_category"),
            font=("Segoe UI", 9, "bold"),
            bg=card_bg,
            fg=text_dark,
        ).pack(anchor="w", pady=(0, 4))

        cat_var = tk.StringVar()
        cat_combo = ttk.Combobox(card, textvariable=cat_var, values=available_tags, font=("Segoe UI", 9))
        cat_combo.pack(fill=tk.X, pady=(0, 8))

        # Quick Tag Chips Frame
        chips_frame = tk.Frame(card, bg=card_bg)
        chips_frame.pack(fill=tk.X, pady=(0, 10))

        def add_chip(val):
            cur = cat_var.get().strip()
            if not cur:
                cat_var.set(val)
            else:
                existing = [x.strip() for x in re.split(r"[,;]+", cur) if x.strip()]
                if val not in existing:
                    existing.append(val)
                cat_var.set(", ".join(existing))

        tk.Label(chips_frame, text=t("lbl_quick_chips"), font=("Segoe UI", 8), bg=card_bg, fg=text_muted).pack(anchor="w", pady=(0, 4))
        chips_bar = tk.Frame(chips_frame, bg=card_bg)
        chips_bar.pack(anchor="w")

        for sample_chip in ["Tech", "Core", "Dividend", "Growth", "Value", "ETF"]:
            tk.Button(
                chips_bar,
                text=f"+ {sample_chip}",
                font=("Segoe UI", 8),
                bg="#ffffff" if not self.dark_mode else "#2d3342",
                fg=primary_col,
                relief="solid",
                bd=1,
                padx=6,
                pady=1,
                cursor="hand2",
                command=lambda sc=sample_chip: add_chip(sc),
            ).pack(side=tk.LEFT, padx=(0, 4))

        # Action Modes (Radiobuttons)
        mode_var = tk.StringVar(value="replace")
        modes_box = tk.LabelFrame(
            card,
            text=f" {t('lbl_update_mode')} ",
            font=("Segoe UI", 8, "bold"),
            bg=card_bg,
            fg=text_muted,
            padx=10,
            pady=6,
        )
        modes_box.pack(fill=tk.X, pady=(0, 4))

        tk.Radiobutton(
            modes_box,
            text=t("opt_category_replace"),
            variable=mode_var,
            value="replace",
            font=("Segoe UI", 9),
            bg=card_bg,
            fg=text_dark,
            activebackground=card_bg,
        ).pack(anchor="w", pady=1)

        tk.Radiobutton(
            modes_box,
            text=t("opt_category_append"),
            variable=mode_var,
            value="append",
            font=("Segoe UI", 9),
            bg=card_bg,
            fg=text_dark,
            activebackground=card_bg,
        ).pack(anchor="w", pady=1)

        tk.Radiobutton(
            modes_box,
            text=t("opt_category_clear"),
            variable=mode_var,
            value="clear",
            font=("Segoe UI", 9),
            bg=card_bg,
            fg=self.red_color if hasattr(self, "red_color") else "#d93025",
            activebackground=card_bg,
        ).pack(anchor="w", pady=1)

        # Buttons Box
        btn_bar = tk.Frame(dlg, bg=bg_main, padx=16, pady=8)
        btn_bar.pack(fill=tk.X)

        def on_confirm():
            new_cat = cat_var.get().strip()
            chosen_mode = mode_var.get()
            if chosen_mode != "clear" and not new_cat:
                messagebox.showwarning(t("dlg_warning", default="Warning"), t("msg_enter_category_name"), parent=dlg)
                return

            updated = bulk_update_watchlist_category(selected_symbols, new_cat, mode=chosen_mode)
            dlg.destroy()
            self._refresh_watchlist_tab()
            self._set_status(f"🏷️ {t('msg_category_updated', count=updated)}")

        tk.Button(
            btn_bar,
            text=t("btn_apply_changes"),
            font=("Segoe UI", 9, "bold"),
            bg=primary_col,
            fg="#ffffff",
            relief="flat",
            padx=14,
            pady=4,
            cursor="hand2",
            command=on_confirm,
        ).pack(side=tk.RIGHT, padx=(6, 0))

        tk.Button(
            btn_bar,
            text=t("btn_cancel"),
            font=("Segoe UI", 9),
            relief="solid",
            bd=1,
            padx=10,
            pady=4,
            cursor="hand2",
            command=dlg.destroy,
        ).pack(side=tk.RIGHT)

    def _open_batch_watchlist_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_batch_watchlist_title"))
        dlg.geometry("580x480")
        dlg.transient(self.root)

        nb = ttk.Notebook(dlg)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tab 1: Paste Text
        tab_paste = ttk.Frame(nb, padding=12)
        nb.add(tab_paste, text=t("btn_paste_import"))

        tk.Label(
            tab_paste,
            text=t("lbl_paste_instructions"),
            font=("Segoe UI", 9),
            justify=tk.LEFT,
            wraplength=530,
        ).pack(anchor="w", pady=(0, 6))

        text_box = tk.Text(tab_paste, font=("Consolas", 10), height=10, bd=1, relief="solid")
        text_box.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        lbl_paste_count = tk.Label(tab_paste, text=t("lbl_detected_symbols", count=0), font=("Segoe UI", 8, "bold"), fg=self.primary_color)
        lbl_paste_count.pack(anchor="w", pady=(0, 4))

        def update_paste_count(event=None):
            content = text_box.get("1.0", tk.END)
            records = parse_symbols_text(content)
            lbl_paste_count.config(text=t("lbl_detected_symbols", count=len(records)))

        text_box.bind("<KeyRelease>", update_paste_count)
        text_box.bind("<FocusIn>", update_paste_count)

        chk_fetch_var1 = tk.BooleanVar(value=True)
        chk_fetch1 = ttk.Checkbutton(tab_paste, text=t("chk_fetch_quotes_now"), variable=chk_fetch_var1)
        chk_fetch1.pack(anchor="w", pady=(0, 8))

        btn_box1 = ttk.Frame(tab_paste)
        btn_box1.pack(fill=tk.X)

        def do_paste_import():
            content = text_box.get("1.0", tk.END)
            records = parse_symbols_text(content)
            if not records:
                messagebox.showwarning(t("msg_warning"), t("msg_no_symbols_detected"), parent=dlg)
                return
            count = bulk_add_to_watchlist(records)
            dlg.destroy()
            self._refresh_watchlist_tab()
            if chk_fetch_var1.get():
                self._refresh_watchlist_quotes()
            messagebox.showinfo(t("msg_success"), t("msg_batch_imported", count=count), parent=self.root)

        tk.Button(btn_box1, text=t("btn_batch_import"), bg=self.primary_color, fg="#ffffff", font=("Segoe UI", 9, "bold"), command=do_paste_import, padx=12, pady=4).pack(side=tk.RIGHT, padx=4)
        tk.Button(btn_box1, text=t("btn_cancel"), command=dlg.destroy, padx=8, pady=4).pack(side=tk.RIGHT)

        # Tab 2: CSV Import
        tab_csv = ttk.Frame(nb, padding=12)
        nb.add(tab_csv, text=t("btn_csv_import"))

        tk.Label(
            tab_csv,
            text=t("lbl_csv_import_instructions"),
            font=("Segoe UI", 9),
            justify=tk.LEFT,
            wraplength=530,
        ).pack(anchor="w", pady=(0, 8))

        file_row = ttk.Frame(tab_csv)
        file_row.pack(fill=tk.X, pady=(0, 10))

        csv_path_var = tk.StringVar()
        csv_entry = tk.Entry(file_row, textvariable=csv_path_var, font=("Segoe UI", 9), bd=1, relief="solid")
        csv_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        def browse_csv():
            f = filedialog.askopenfilename(
                title=t("btn_csv_import"),
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
                parent=dlg,
            )
            if f:
                csv_path_var.set(f)

        tk.Button(file_row, text=t("btn_browse"), command=browse_csv, padx=8, pady=2).pack(side=tk.RIGHT)

        chk_fetch_var2 = tk.BooleanVar(value=True)
        chk_fetch2 = ttk.Checkbutton(tab_csv, text=t("chk_fetch_quotes_now"), variable=chk_fetch_var2)
        chk_fetch2.pack(anchor="w", pady=(0, 8))

        btn_box2 = ttk.Frame(tab_csv)
        btn_box2.pack(fill=tk.X, side=tk.BOTTOM)

        def do_csv_import():
            path = csv_path_var.get().strip()
            if not path or not os.path.exists(path):
                messagebox.showerror(t("dlg_error"), t("msg_select_valid_csv"), parent=dlg)
                return
            count = import_watchlist_from_csv(path)
            if count == 0:
                messagebox.showwarning(t("msg_warning"), t("msg_no_symbols_in_csv"), parent=dlg)
                return
            dlg.destroy()
            self._refresh_watchlist_tab()
            if chk_fetch_var2.get():
                self._refresh_watchlist_quotes()
            messagebox.showinfo(t("msg_success"), t("msg_batch_imported", count=count), parent=self.root)

        tk.Button(btn_box2, text=t("btn_csv_import"), bg=self.primary_color, fg="#ffffff", font=("Segoe UI", 9, "bold"), command=do_csv_import, padx=12, pady=4).pack(side=tk.RIGHT, padx=4)
        tk.Button(btn_box2, text=t("btn_cancel"), command=dlg.destroy, padx=8, pady=4).pack(side=tk.RIGHT)

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 580, 480
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _remove_selected_watchlist(self):
        sel = self.watchlist_tree.selection()
        if not sel:
            messagebox.showinfo(t("tab_monitoring"), t("msg_select_stock_to_remove"), parent=self.root)
            return

        symbols_to_remove = []
        for it in sel:
            vals = self.watchlist_tree.item(it, "values")
            if vals:
                symbols_to_remove.append(vals[0])

        if not symbols_to_remove:
            return

        msg = f"{t('confirm_delete')} {', '.join(symbols_to_remove)}?"
        if not messagebox.askyesno(t("dlg_confirm_removal_title"), msg, parent=self.root):
            return

        for s in symbols_to_remove:
            remove_from_watchlist(s)
            self._watchlist_quotes_cache.pop(s.upper(), None)
        save_watchlist_quotes_cache(self._watchlist_quotes_cache)

        self._refresh_watchlist_tab()

    def _buy_from_watchlist_into_portfolio(self):
        sel = self.watchlist_tree.selection()
        if not sel:
            messagebox.showinfo(t("tab_monitoring"), t("msg_select_stock_to_buy"), parent=self.root)
            return

        vals = self.watchlist_tree.item(sel[0], "values")
        if not vals:
            return

        sym = str(vals[0]).strip().upper()
        name = str(vals[1]).strip() if len(vals) > 1 else sym

        q = getattr(self, "_watchlist_quotes_cache", {}).get(sym, {})
        w_items = load_watchlist()
        match_w = next((it for it in w_items if str(it.get("symbol", "")).strip().upper() == sym), {})

        price_val = float(q.get("price", 0.0) or match_w.get("target_buy_price", 0.0) or 0.0)
        curr_code = q.get("currency") or match_w.get("currency", "USD")

        self._open_add_dialog(initial_symbol=sym, initial_name=name, initial_price=price_val, initial_currency=curr_code)

    def _export_watchlist_csv(self):
        items = load_watchlist()
        if not items:
            messagebox.showinfo(t("tab_monitoring"), t("msg_watchlist_empty"), parent=self.root)
            return

        file_path = filedialog.asksaveasfilename(
            title=t("dlg_export_csv_title"),
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile="monitoring_list.csv",
            parent=self.root,
        )
        if not file_path:
            return

        save_watchlist(items, filepath=file_path)
        messagebox.showinfo(t("msg_success"), t("msg_watchlist_exported", count=len(items), path=file_path), parent=self.root)

    def _view_watchlist_chart(self):
        sel = self.watchlist_tree.selection()
        if not sel:
            return
        vals = self.watchlist_tree.item(sel[0], "values")
        if not vals:
            return
        sym = vals[0]
        if hasattr(self, "notebook") and hasattr(self, "tab_chart"):
            self.notebook.select(self.tab_chart)
            if hasattr(self, "chart_view"):
                if hasattr(self.chart_view, "symbol_var"):
                    self.chart_view.symbol_var.set(sym)
                if hasattr(self.chart_view, "_on_symbol_changed"):
                    self.chart_view._on_symbol_changed()

    def _on_watchlist_double_click(self, event=None):
        sel = self.watchlist_tree.selection()
        if not sel:
            return
        self._open_edit_watchlist_dialog()

    def _on_watchlist_right_click(self, event):
        item = self.watchlist_tree.identify_row(event.y)
        if item:
            if item not in self.watchlist_tree.selection():
                self.watchlist_tree.selection_set(item)
            try:
                self.watchlist_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.watchlist_menu.grab_release()

    def _open_drip_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_drip_title"))
        dlg.geometry("440x380")
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text=t("dlg_drip_title"), font=("Segoe UI", 11, "bold"), fg=self.primary_color).pack(anchor="w", pady=(0, 10))

        # Symbol dropdown
        tk.Label(frame, text=t("col_symbol") + ":", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        symbols = [h.get("symbol", "") for h in self.holdings if h.get("symbol")]
        sym_var = tk.StringVar(value=symbols[0] if symbols else "")
        sym_cb = ttk.Combobox(frame, textvariable=sym_var, values=symbols, state="readonly")
        sym_cb.pack(fill=tk.X, pady=(2, 6))

        # Div Amount
        tk.Label(frame, text=t("lbl_drip_amount"), font=("Segoe UI", 9)).pack(anchor="w")
        amt_entry = tk.Entry(frame, font=("Segoe UI", 9))
        amt_entry.insert(0, "50.00")
        amt_entry.pack(fill=tk.X, pady=(2, 6))

        # Reinvest Price
        tk.Label(frame, text=t("lbl_drip_reinvest_price"), font=("Segoe UI", 9)).pack(anchor="w")
        price_entry = tk.Entry(frame, font=("Segoe UI", 9))
        price_entry.insert(0, "25.00")
        price_entry.pack(fill=tk.X, pady=(2, 6))

        # Date
        tk.Label(frame, text=t("lbl_drip_date"), font=("Segoe UI", 9)).pack(anchor="w")
        date_entry = tk.Entry(frame, font=("Segoe UI", 9))
        date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        date_entry.pack(fill=tk.X, pady=(2, 6))

        # Estimated new shares label
        lbl_shares = tk.Label(frame, text=t("lbl_drip_new_shares") + " 2.0000", font=("Segoe UI", 10, "bold"), fg="#0d904f")
        lbl_shares.pack(anchor="w", pady=(4, 10))

        def calc_shares(*args):
            try:
                amt = float(amt_entry.get().strip() or 0.0)
                p = float(price_entry.get().strip() or 0.0)
                if p > 0:
                    lbl_shares.config(text=f"{t('lbl_drip_new_shares')} {amt / p:.4f}")
            except Exception:
                pass

        def on_sym_change(event=None):
            s = sym_var.get()
            for h in self.holdings:
                if h.get("symbol") == s:
                    cp = float(h.get("current_price", 0.0) or 0.0)
                    if cp > 0:
                        price_entry.delete(0, tk.END)
                        price_entry.insert(0, f"{cp:.2f}")
                    ann_d = float(h.get("annual_dividend", 0.0) or 0.0)
                    if ann_d > 0:
                        amt_entry.delete(0, tk.END)
                        amt_entry.insert(0, f"{ann_d / 4:.2f}")
                    break
            calc_shares()

        sym_cb.bind("<<ComboboxSelected>>", on_sym_change)
        amt_entry.bind("<KeyRelease>", calc_shares)
        price_entry.bind("<KeyRelease>", calc_shares)
        on_sym_change()

        def do_book():
            s = sym_var.get().strip().upper()
            try:
                amt = float(amt_entry.get().strip() or 0.0)
                p = float(price_entry.get().strip() or 0.0)
            except ValueError:
                messagebox.showerror(t("dlg_error"), t("msg_enter_positive_div_drip"), parent=dlg)
                return
            if amt <= 0 or p <= 0:
                messagebox.showerror(t("dlg_error"), t("msg_amount_price_gt_zero"), parent=dlg)
                return
            dt = date_entry.get().strip()
            port = "All"
            for h in self.holdings:
                if h.get("symbol") == s:
                    port = h.get("portfolio", "All")
                    break

            success, msg, new_sh = book_drip_transaction(s, amt, p, dt, port)
            if success:
                dlg.destroy()
                self.all_holdings = load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
                self._filter_holdings_by_portfolio()
                self._refresh_holdings_table()
                self._refresh_sales_table()
                self._refresh_analytics_tab()
                self._update_metric_cards()
                messagebox.showinfo(t("msg_success"), t("msg_drip_booked", symbol=s, shares=new_sh), parent=self.root)
            else:
                messagebox.showerror(t("dlg_error"), msg, parent=dlg)

        btn_box = ttk.Frame(frame)
        btn_box.pack(fill=tk.X, pady=(6, 0))
        tk.Button(btn_box, text=t("btn_book_drip"), font=("Segoe UI", 9, "bold"), bg="#0d904f", fg="#ffffff", command=do_book, padx=12, pady=4).pack(side=tk.RIGHT, padx=4)
        tk.Button(btn_box, text=t("btn_cancel"), command=dlg.destroy, padx=8, pady=4).pack(side=tk.RIGHT)

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 440, 380
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _show_dividend_calendar_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("grp_dividend_calendar"))
        dlg.geometry("580x420")
        dlg.transient(self.root)

        base_curr = self.summary_currency if hasattr(self, "summary_currency") else "CAD"
        fx_rates = getattr(self.fetcher, "fx_cache", {})
        cal = calc_dividend_calendar(self.holdings, base_curr, fx_rates, months_ahead=12)

        header_frame = ttk.Frame(dlg, padding="12 12 12 6")
        header_frame.pack(fill=tk.X)
        tk.Label(header_frame, text=t("grp_dividend_calendar"), font=("Segoe UI", 12, "bold"), fg=self.primary_color).pack(anchor="w")

        total_12m = cal.get("annual_total", 0.0)
        sym_char = self.converter.CURRENCY_SYMBOLS.get(base_curr, "$")
        tk.Label(
            header_frame,
            text=t("lbl_annual_projected_total", val=f"{sym_char}{total_12m:,.2f} ({base_curr})"),
            font=("Segoe UI", 10, "bold"),
            fg="#0d904f",
        ).pack(anchor="w", pady=(2, 0))

        tree_frame = ttk.Frame(dlg, padding="12 6 12 12")
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("month", "cashflow", "payers")
        c_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=12)
        c_tree.heading("month", text=t("col_month"))
        c_tree.column("month", width=90, anchor="center")
        c_tree.heading("cashflow", text=t("col_est_cashflow"))
        c_tree.column("cashflow", width=120, anchor="e")
        c_tree.heading("payers", text=t("col_payers"))
        c_tree.column("payers", width=300, anchor="w")

        scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=c_tree.yview)
        c_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        c_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        schedule = cal.get("schedule", [])
        for item in schedule:
            m = item.get("month", "")
            cf = item.get("cashflow", 0.0)
            payers = ", ".join(item.get("payers", [])) or "-"
            c_tree.insert("", tk.END, values=(m, f"{sym_char}{cf:,.2f}", payers))

        bot = ttk.Frame(dlg, padding="12 0 12 12")
        bot.pack(fill=tk.X)
        tk.Button(bot, text=t("btn_close"), command=dlg.destroy, padx=12, pady=3).pack(side=tk.RIGHT)

    def _open_local_web_view(self):
        def get_data():
            base_curr = self.summary_currency if hasattr(self, "summary_currency") else "CAD"
            fx_rates = getattr(self.fetcher, "fx_cache", {})
            metrics = calc_portfolio_metrics(self.holdings, base_curr, fx_rates)
            return {
                "currency": base_curr,
                "total_value": metrics.get("total_market_value", 0.0),
                "total_unrealized_pl": metrics.get("total_unrealized_pl", 0.0),
                "overall_roi_pct": metrics.get("overall_roi_pct", 0.0),
                "total_annual_dividend": metrics.get("total_annual_dividend", 0.0),
                "holdings": self.holdings,
                "sectors": metrics.get("sector_allocations", {})
            }
        port = web_server.start_server(data_callback=get_data)
        url = web_server.get_server_url()
        webbrowser.open(url)
        messagebox.showinfo(t("title_web_dashboard"), t("msg_web_started", port=port), parent=self.root)

    def _update_network_status_badge(self):
        if not hasattr(self, "btn_network_warnings"):
            return
        n_errs = len(self._network_errors)
        if n_errs > 0:
            self.btn_network_warnings.config(text=t("btn_network_warning_badge", count=n_errs))
            if not self.btn_network_warnings.winfo_ismapped():
                self.btn_network_warnings.pack(side=tk.RIGHT, padx=4)
        else:
            if self.btn_network_warnings.winfo_ismapped():
                self.btn_network_warnings.pack_forget()

    def _open_network_diag_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_network_diag_title"))
        dlg.geometry("640x480")
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text=t("dlg_network_diag_title"), font=("Segoe UI", 12, "bold"), fg="#e37400").pack(anchor="w", pady=(0, 6))

        diag_text = tk.Text(frame, font=("Consolas", 9), height=14, bd=1, relief="solid", wrap=tk.WORD)
        diag_text.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        def populate_diag():
            diag_text.delete("1.0", tk.END)
            if not self._network_errors:
                diag_text.insert(tk.END, t("msg_no_network_errors") + "\n")
            else:
                diag_text.insert(tk.END, t("lbl_network_issues_found", count=len(self._network_errors)))
                for err in self._network_errors:
                    t_str = err.get("time", "")
                    s = err.get("symbol", "")
                    msg = err.get("error", "")
                    diag_text.insert(tk.END, f"[{t_str}] {t('col_symbol')}: {s} | {t('col_status')}: {msg}\n")

            diag_text.insert(tk.END, t("lbl_network_troubleshoot") + "\n")

        populate_diag()

        btn_box = ttk.Frame(frame)
        btn_box.pack(fill=tk.X)

        def clear_errs():
            self._network_errors.clear()
            self._update_network_status_badge()
            populate_diag()

        def retry_failed():
            symbols_to_retry = list(set([e.get("symbol") for e in self._network_errors if e.get("symbol")]))
            clear_errs()
            if symbols_to_retry:
                threading.Thread(target=lambda: [self.fetcher.fetch_quote(s) for s in symbols_to_retry], daemon=True).start()
                messagebox.showinfo(t("btn_retry"), t("msg_retry_dispatched", count=len(symbols_to_retry)), parent=dlg)

        tk.Button(btn_box, text=t("btn_retry_failed"), font=("Segoe UI", 9, "bold"), bg=self.primary_color, fg="#ffffff", command=retry_failed, padx=8, pady=4).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_box, text=t("btn_clear_diag"), command=clear_errs, padx=8, pady=4).pack(side=tk.LEFT)
        tk.Button(btn_box, text=t("btn_cancel"), command=dlg.destroy, padx=8, pady=4).pack(side=tk.RIGHT)

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 640, 480
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _open_rebalance_dialog(self, initial_target_weights: Optional[Dict[str, float]] = None):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_rebalance_title"))
        dlg.geometry("920x680")
        dlg.minsize(860, 560)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        frame = ttk.Frame(dlg, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)

        # Header title
        tk.Label(frame, text=t("dlg_rebalance_title"), font=("Segoe UI", 12, "bold"), fg=self.primary_color).pack(anchor="w", pady=(0, 4))

        # Top Control Row 1: Cash, Mode, Presets
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=(0, 6))

        tk.Label(row1, text=t("lbl_rebalance_cash"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        cash_entry = tk.Entry(row1, font=("Segoe UI", 9), width=11, bd=1, relief="solid")
        cash_entry.insert(0, "0.0")
        cash_entry.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(row1, text=t("lbl_rebalance_mode"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        mode_cb = ttk.Combobox(row1, values=[t("opt_rebalance_full"), t("opt_rebalance_cash_only")], state="readonly", width=24)
        mode_cb.current(0)
        mode_cb.pack(side=tk.LEFT, padx=(0, 10))

        cur_lang = get_current_language()
        tk.Label(row1, text=t("lbl_preset_models"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        preset_names = [t("opt_select_model")] + [get_allocation_preset_display_name(p, cur_lang) for p in ALLOCATION_PRESETS]
        preset_cb = ttk.Combobox(row1, values=preset_names, state="readonly", width=30)
        preset_cb.current(0)
        preset_cb.pack(side=tk.LEFT, padx=(0, 6))

        btn_apply_preset = tk.Button(row1, text=t("btn_apply_preset"), font=("Segoe UI", 8, "bold"), bg="#ffffff", relief="solid", bd=1, padx=6)
        btn_apply_preset.pack(side=tk.LEFT)

        # Top Control Row 2: Add Suggested ETFs & Custom Tickers
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row2, text=t("lbl_suggested_etfs"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        etf_options = [t("opt_select_suggested_etfs")] + [
            get_etf_option_label(e, cur_lang) for e in SUGGESTED_ALLOCATION_ETFS
        ]
        etf_cb = ttk.Combobox(row2, values=etf_options, state="readonly", width=36)
        etf_cb.current(0)
        etf_cb.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(row2, text=t("lbl_custom_ticker"), font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        custom_sym_entry = tk.Entry(row2, font=("Segoe UI", 9, "bold"), width=9, bd=1, relief="solid")
        custom_sym_entry.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(row2, text=t("col_target_weight") + ":", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        add_tgt_entry = tk.Entry(row2, font=("Segoe UI", 9), width=6, bd=1, relief="solid")
        add_tgt_entry.insert(0, "5.0")
        add_tgt_entry.pack(side=tk.LEFT, padx=(0, 8))

        btn_add_etf = tk.Button(row2, text=t("btn_add_to_plan"), font=("Segoe UI", 8, "bold"), bg=self.primary_color, fg="#ffffff", relief="flat", padx=8)
        btn_add_etf.pack(side=tk.LEFT, padx=(0, 8))

        lbl_status_hint = tk.Label(row2, text="", font=("Segoe UI", 8, "italic"))
        lbl_status_hint.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Holdings data model initialization
        target_weights: Dict[str, float] = {}
        holdings_list: List[Dict[str, Any]] = [dict(h) for h in self.holdings if float(h.get("shares", 0.0)) > 0]
        n_holdings = len(holdings_list)
        default_pct = round(100.0 / n_holdings, 2) if n_holdings > 0 else 0.0

        for h in holdings_list:
            sym = h.get("symbol", "")
            if initial_target_weights and sym in initial_target_weights:
                target_weights[sym] = initial_target_weights[sym]
            else:
                target_weights[sym] = default_pct

        # Table of holdings and added plan items
        tbl_frame = ttk.Frame(frame)
        tbl_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        cols = ("symbol", "name", "price", "current_val", "cur_weight", "target_pct", "action", "order_shares", "order_val")
        tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", height=11)
        headers = [
            ("symbol", t("col_symbol"), 85, "center"),
            ("name", t("col_name"), 160, "w"),
            ("price", t("col_current_price"), 80, "e"),
            ("current_val", t("col_market_value"), 95, "e"),
            ("cur_weight", t("col_weight"), 75, "e"),
            ("target_pct", t("col_target_weight"), 80, "e"),
            ("action", t("col_action"), 75, "center"),
            ("order_shares", t("col_shares_diff"), 80, "e"),
            ("order_val", t("col_amount_diff"), 95, "e"),
        ]
        for cid, text, w, anch in headers:
            tree.heading(cid, text=text)
            tree.column(cid, width=w, anchor=anch)

        sc = ttk.Scrollbar(tbl_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sc.set)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tree.tag_configure("buy", foreground="#188038", font=("Segoe UI", 9, "bold"))
        tree.tag_configure("sell", foreground="#d93025", font=("Segoe UI", 9, "bold"))
        tree.tag_configure("hold", foreground="#5f6368")
        tree.tag_configure("new_buy", foreground="#0d652d", font=("Segoe UI", 9, "bold"), background="#e6f4ea")

        # Edit Target Weight and Actions Row below table
        edit_row = ttk.Frame(frame)
        edit_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(edit_row, text=t("lbl_selected_holding_target"), font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        target_entry = tk.Entry(edit_row, font=("Segoe UI", 9), width=8, bd=1, relief="solid")
        target_entry.pack(side=tk.LEFT, padx=(0, 6))

        def set_selected_target():
            sel = tree.selection()
            if not sel:
                return
            sym = tree.item(sel[0], "values")[0]
            try:
                val = float(target_entry.get().strip())
                val = max(0.0, min(100.0, val))
                target_weights[sym] = val
                target_h = next((h for h in holdings_list if h.get("symbol") == sym), None)
                if val <= 0.0001 and target_h and float(target_h.get("shares", 0.0)) <= 0.0001:
                    holdings_list.remove(target_h)
                    if sym in target_weights:
                        del target_weights[sym]
                run_rebalance()
            except ValueError:
                pass

        btn_set_target = tk.Button(edit_row, text=t("btn_update_target"), font=("Segoe UI", 8, "bold"), command=set_selected_target, padx=6)
        btn_set_target.pack(side=tk.LEFT, padx=(0, 8))

        def remove_selected_from_plan():
            sel = tree.selection()
            if not sel:
                return
            sym = tree.item(sel[0], "values")[0]
            target_h = next((h for h in holdings_list if h.get("symbol") == sym), None)
            if target_h and float(target_h.get("shares", 0.0)) <= 0.0001:
                holdings_list.remove(target_h)
                if sym in target_weights:
                    del target_weights[sym]
                lbl_status_hint.config(text=t("msg_holding_pruned", sym=sym), fg=self.primary_color)
            else:
                target_weights[sym] = 0.0
                lbl_status_hint.config(text=t("msg_target_updated", sym=sym, tgt=0.0), fg=self.primary_color)
            run_rebalance()

        btn_remove = tk.Button(edit_row, text=t("btn_remove_from_plan"), font=("Segoe UI", 8), bg="#ffffff", relief="solid", bd=1, padx=6, command=remove_selected_from_plan)
        btn_remove.pack(side=tk.LEFT, padx=(0, 8))

        def apply_equal_weight():
            active_syms = [s for s in target_weights if target_weights[s] > 0 or float(next((h.get("shares", 0) for h in holdings_list if h.get("symbol") == s), 0)) > 0]
            if not active_syms:
                active_syms = list(target_weights.keys())
            if active_syms:
                eq = round(100.0 / len(active_syms), 2)
                for sym in target_weights:
                    target_weights[sym] = eq if sym in active_syms else 0.0
                run_rebalance()

        btn_equal = tk.Button(edit_row, text=f"⚖️ {t('btn_equal_weight')}", font=("Segoe UI", 8), bg="#ffffff", relief="solid", bd=1, padx=6, command=apply_equal_weight)
        btn_equal.pack(side=tk.LEFT, padx=(0, 8))

        lbl_sum_pct = tk.Label(edit_row, text=f"{t('lbl_total_target')}: 100.0%", font=("Segoe UI", 9, "bold"), fg=self.primary_color)
        lbl_sum_pct.pack(side=tk.RIGHT)

        def on_tree_select(event=None):
            sel = tree.selection()
            if sel:
                sym = tree.item(sel[0], "values")[0]
                target_entry.delete(0, tk.END)
                target_entry.insert(0, str(target_weights.get(sym, 0.0)))

        tree.bind("<<TreeviewSelect>>", on_tree_select)

        # Logic: Add Suggested or Custom ETF
        def add_etf_to_plan():
            sel_idx = etf_cb.current()
            sym = ""
            if sel_idx > 0 and sel_idx <= len(SUGGESTED_ALLOCATION_ETFS):
                sym = SUGGESTED_ALLOCATION_ETFS[sel_idx - 1]["symbol"]
            else:
                sym = custom_sym_entry.get().strip().upper()

            if not sym:
                messagebox.showwarning(t("msg_warning"), t("msg_select_etf_hint"), parent=dlg)
                return

            try:
                new_tgt = float(add_tgt_entry.get().strip() or "5.0")
                new_tgt = max(0.0, min(100.0, new_tgt))
            except ValueError:
                new_tgt = 5.0

            existing_item = next((h for h in holdings_list if h["symbol"] == sym), None)
            if existing_item:
                target_weights[sym] = new_tgt
                run_rebalance()
                lbl_status_hint.config(text=t("msg_target_updated", sym=sym, tgt=new_tgt), fg=self.primary_color)
                return

            lbl_status_hint.config(text=t("msg_fetching_quote", sym=sym), fg=self.primary_color)
            dlg.update()

            etf_meta = next((e for e in SUGGESTED_ALLOCATION_ETFS if e["symbol"] == sym), None)
            name = etf_meta["name"] if etf_meta else sym
            curr = etf_meta["currency"] if etf_meta else ("CAD" if ":TSE" in sym or ".TO" in sym else "USD")
            def_price = etf_meta.get("typical_price", 50.0) if etf_meta else 50.0

            q = self.fetcher.fetch_quote(sym)
            if q.get("success") and float(q.get("price", 0.0)) > 0:
                price = float(q["price"])
                name = q.get("name") or name
                if q.get("currency"):
                    curr = q["currency"]
            else:
                price = def_price

            new_item = {
                "symbol": sym,
                "name": name,
                "price": price,
                "current_price": price,
                "shares": 0.0,
                "current_value": 0.0,
                "currency": curr,
                "is_new_plan": True,
            }
            holdings_list.append(new_item)
            target_weights[sym] = new_tgt
            run_rebalance()

            lbl_status_hint.config(text=f"✅ {t('msg_etf_added_plan', sym=sym, price=price, tgt=new_tgt)}", fg=self.green_color)
            custom_sym_entry.delete(0, tk.END)
            etf_cb.current(0)

        btn_add_etf.config(command=add_etf_to_plan)

        # Logic: Apply Preset Model
        def apply_preset_model():
            sel_idx = preset_cb.current()
            if sel_idx <= 0 or sel_idx > len(ALLOCATION_PRESETS):
                return
            preset = ALLOCATION_PRESETS[sel_idx - 1]
            p_display = get_allocation_preset_display_name(preset, cur_lang)
            p_weights = preset["weights"]

            lbl_status_hint.config(text=t("msg_applying_preset", name=p_display), fg=self.primary_color)
            dlg.update()

            # Clean previous preset/plan items that have 0 shares held
            holdings_list[:] = [h for h in holdings_list if float(h.get("shares", 0.0)) > 0.0001]
            target_weights.clear()
            for h in holdings_list:
                target_weights[h["symbol"]] = 0.0

            for p_sym, p_pct in p_weights.items():
                p_sym_clean = p_sym.strip().upper()
                existing = next((h for h in holdings_list if h["symbol"] == p_sym_clean), None)
                if not existing:
                    etf_meta = next((e for e in SUGGESTED_ALLOCATION_ETFS if e["symbol"] == p_sym_clean), None)
                    name = etf_meta["name"] if etf_meta else p_sym_clean
                    curr = etf_meta["currency"] if etf_meta else ("CAD" if ":TSE" in p_sym_clean or ".TO" in p_sym_clean else "USD")
                    price = etf_meta.get("typical_price", 50.0) if etf_meta else 50.0

                    q = self.fetcher.fetch_quote(p_sym_clean)
                    if q.get("success") and float(q.get("price", 0.0)) > 0:
                        price = float(q["price"])
                        name = q.get("name") or name
                        if q.get("currency"):
                            curr = q["currency"]

                    new_item = {
                        "symbol": p_sym_clean,
                        "name": name,
                        "price": price,
                        "current_price": price,
                        "shares": 0.0,
                        "current_value": 0.0,
                        "currency": curr,
                        "is_new_plan": True,
                    }
                    holdings_list.append(new_item)

                target_weights[p_sym_clean] = p_pct

            run_rebalance()
            lbl_status_hint.config(text=f"✅ {t('msg_preset_applied', name=p_display)}", fg=self.green_color)

        btn_apply_preset.config(command=apply_preset_model)

        # Summary Bar & Bottom Action Row
        bottom_frame = ttk.Frame(frame)
        bottom_frame.pack(fill=tk.X, pady=(4, 0))

        lbl_summary_bar = tk.Label(bottom_frame, text="", font=("Segoe UI", 9), justify=tk.LEFT, anchor="w", fg=self.text_dark)
        lbl_summary_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def copy_orders():
            try:
                c_val = float(cash_entry.get().strip() or "0.0")
            except ValueError:
                c_val = 0.0
            m_str = "cash_only" if mode_cb.get() == t("opt_rebalance_cash_only") else "full"
            reb = calc_portfolio_rebalance(holdings_list, target_weights, new_cash=c_val, mode=m_str)
            lines = [
                t("order_plan_header"),
                t("order_plan_mode", mode=mode_cb.get(), cash=c_val),
                "----------------------------------------------------------------",
            ]
            for o in reb.get("orders", []):
                act = o["action"]
                if act in ("BUY", "SELL"):
                    lines.append(f"{act:<4} {o['symbol']:<10} {o['shares_diff']:+6d} shs @ ${o['price']:.2f}  = ${abs(o['amount_diff']):,.2f}  (Target: {o['target_weight_pct']:.1f}%)")
            lines.append("----------------------------------------------------------------")
            lines.append(f"Total Target Portfolio: ${reb.get('total_target_value', 0.0):,.2f}")
            text_to_copy = "\n".join(lines)
            self.root.clipboard_clear()
            self.root.clipboard_append(text_to_copy)
            messagebox.showinfo(t("msg_copied_title"), t("msg_copy_orders_success"), parent=dlg)

        btn_copy = tk.Button(bottom_frame, text=f"📋 {t('btn_copy_orders')}", font=("Segoe UI", 9), bg="#ffffff", relief="solid", bd=1, padx=8, pady=3, command=copy_orders)
        btn_copy.pack(side=tk.RIGHT, padx=(6, 0))

        def run_rebalance():
            for item in tree.get_children():
                tree.delete(item)
            try:
                c_val = float(cash_entry.get().strip() or "0.0")
            except ValueError:
                c_val = 0.0

            m_str = "cash_only" if mode_cb.get() == t("opt_rebalance_cash_only") else "full"
            reb = calc_portfolio_rebalance(holdings_list, target_weights, new_cash=c_val, mode=m_str)

            total_tgt = sum(target_weights.values())
            sum_color = self.green_color if abs(total_tgt - 100.0) < 0.1 else self.red_color
            lbl_sum_pct.config(text=f"{t('lbl_total_target')}: {total_tgt:.1f}%", fg=sum_color)

            total_curr = reb.get("total_current_value", 0.0)
            tot_target = reb.get("total_target_value", 0.0)
            buys = sum(abs(o.get("amount_diff", 0.0)) for o in reb.get("orders", []) if o.get("action") == "BUY")
            sells = sum(abs(o.get("amount_diff", 0.0)) for o in reb.get("orders", []) if o.get("action") == "SELL")

            lbl_summary_bar.config(
                text=t("summary_rebalance_bar_fmt", cur=total_curr, cash=c_val, tgt=tot_target, buys=buys, sells=sells, net=max(0.0, buys - sells))
            )

            for order in reb.get("orders", []):
                sym = order["symbol"]
                action = order["action"]
                is_new = float(order.get("current_shares", 0.0)) <= 0.0001
                tag = "new_buy" if (is_new and action == "BUY") else ("buy" if action == "BUY" else ("sell" if action == "SELL" else "hold"))
                display_name = f"✨ [NEW] {order.get('name', sym)}" if is_new else order.get("name", sym)

                tree.insert(
                    "",
                    tk.END,
                    values=(
                        sym,
                        display_name,
                        f"${order.get('price', 0.0):.2f}",
                        f"${order.get('current_value', 0.0):,.2f}",
                        f"{order.get('current_weight_pct', 0.0):.1f}%",
                        f"{order.get('target_weight_pct', 0.0):.1f}%",
                        action,
                        f"{order.get('shares_diff', 0):+d}" if order.get('shares_diff') != 0 else "-",
                        f"${abs(order.get('amount_diff', 0.0)):,.2f}" if order.get('amount_diff') != 0 else "-",
                    ),
                    tags=(tag,),
                )

        btn_calc = tk.Button(
            bottom_frame,
            text=t("btn_calc_rebalance"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            command=run_rebalance,
            padx=12,
            pady=3,
        )
        btn_calc.pack(side=tk.RIGHT)

        run_rebalance()

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 920, 680
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _show_fire_dialog(self):
        """
        Enhanced FIRE & Financial Freedom Calculator implementing William J. Bernstein's
        core retirement frameworks from 'The Four Pillars of Investing':
        1. Residual Living Expenses (RLE) = Total Expenses - Guaranteed Pension
        2. Burn Rate (%) = RLE / Portfolio Value (Safety Zones: <2% Abundant, 2-3.5% Sustainable, >3.5% Sequence Risk)
        3. Liability Matching Portfolio (20-25 yrs in safe assets) vs. Risk Portfolio (Growth/Legacy)
        4. Dual-Engine Model: Capital Target (3.2% vs 4%) & Passive Dividend Cashflow Runway
        """
        dlg = tk.Toplevel(self.root)
        dlg.title(f"{t('card_fire_title')} — William J. Bernstein Model")
        dlg.geometry("780x740")
        dlg.minsize(720, 640)
        dlg.transient(self.root)

        # Main scrollable canvas container
        canvas = tk.Canvas(dlg, highlightthickness=0, bg=self.bg_main)
        scrollbar = ttk.Scrollbar(dlg, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=14)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mouse wheel support
        def _on_mousewheel(event):
            try:
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                elif event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")
            except Exception:
                pass

        dlg.bind("<MouseWheel>", _on_mousewheel)
        dlg.bind("<Button-4>", _on_mousewheel)
        dlg.bind("<Button-5>", _on_mousewheel)

        # Header Title & Bernstein Thesis
        header_frame = tk.Frame(scrollable_frame, bg=self.bg_main)
        header_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            header_frame,
            text=f"🔥 {t('card_fire_title')}",
            font=("Segoe UI", 13, "bold"),
            fg="#e37400",
            bg=self.bg_main,
        ).pack(anchor="w")

        thesis_text = (
            "William J. Bernstein Dual-Engine Framework (威廉·伯恩斯坦雙軌退休模型)\n"
            "待攤生活費用 (RLE) • 燒錢率 (Burn Rate < 3.5%) • 負債配合組合 (20-25年無風險儲備)"
        )
        tk.Label(
            header_frame,
            text=thesis_text,
            font=("Segoe UI", 8),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
            bg=self.bg_main,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(1, 4))

        # Baseline info box (Current Portfolio)
        target_curr = self.summary_currency
        cur_ann_div = 0.0
        cur_total_val = 0.0
        for h in self.holdings:
            c = (h.get("currency") or "USD").strip().upper()
            mv = float(h.get("shares", 0.0)) * float(h.get("current_price", h.get("price", 0.0)))
            ad = float(h.get("annual_dividend", 0.0))
            cur_ann_div += self.converter.convert(ad, c, target_curr)
            cur_total_val += self.converter.convert(mv, c, target_curr)

        info_box = tk.Frame(scrollable_frame, bg=self.card_bg, bd=1, relief="solid", padx=10, pady=6)
        info_box.pack(fill=tk.X, pady=(0, 8))
        if cur_total_val > 0:
            info_text = t("fire_current_portfolio", val=self.converter.format_money(cur_total_val, target_curr), div=self.converter.format_money(cur_ann_div, target_curr), yield_val=f"{(cur_ann_div/cur_total_val*100):.2f}")
        else:
            info_text = t("fire_current_portfolio", val="$0.00", div="$0.00", yield_val="0.00")
        tk.Label(
            info_box,
            text=info_text,
            font=("Segoe UI", 9, "bold"),
            bg=self.card_bg,
            fg=self.text_dark,
        ).pack(anchor="w")

        # 1-Click Quick Preset Profiles
        preset_frame = tk.LabelFrame(scrollable_frame, text=f" {t('lbl_preset_profiles')} ", font=("Segoe UI", 9, "bold"), padx=8, pady=6)
        preset_frame.pack(fill=tk.X, pady=(0, 8))

        presets_box = tk.Frame(preset_frame)
        presets_box.pack(fill=tk.X)

        # Quick Monthly Expense Buttons
        exp_quick_frame = tk.Frame(preset_frame)
        exp_quick_frame.pack(fill=tk.X, pady=(4, 0))
        tk.Label(exp_quick_frame, text=f"{t('lbl_quick_exp')} ", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)

        # Inputs Grid
        input_frame = tk.LabelFrame(scrollable_frame, text=f" {t('lbl_calc_inputs')} ", font=("Segoe UI", 9, "bold"), padx=10, pady=8)
        input_frame.pack(fill=tk.X, pady=(0, 10))

        # 2 Columns for inputs
        col1 = tk.Frame(input_frame)
        col1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        col2 = tk.Frame(input_frame)
        col2.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        saved_f = load_settings().get("fire_params", {})

        # Col 1 inputs
        # Current Age & Retire Age inputs
        age_grid = tk.Frame(col1)
        age_grid.pack(fill=tk.X, pady=(0, 6))

        ag1 = tk.Frame(age_grid)
        ag1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        tk.Label(ag1, text=t("lbl_current_age"), font=("Segoe UI", 8, "bold")).pack(anchor="w")
        age_entry = tk.Entry(ag1, font=("Segoe UI", 9), bd=1, relief="solid")
        age_entry.insert(0, str(saved_f.get("current_age", getattr(self, "_last_current_age", "45"))))
        age_entry.pack(fill=tk.X, pady=(2, 0))

        ag2 = tk.Frame(age_grid)
        ag2.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))
        tk.Label(ag2, text=t("lbl_retire_age"), font=("Segoe UI", 8, "bold")).pack(anchor="w")
        ret_age_entry = tk.Entry(ag2, font=("Segoe UI", 9), bd=1, relief="solid")
        ret_age_entry.insert(0, str(saved_f.get("retire_age", getattr(self, "_last_retire_age", "60"))))
        ret_age_entry.pack(fill=tk.X, pady=(2, 0))

        tk.Label(col1, text=t("lbl_target_monthly_expense"), font=("Segoe UI", 8, "bold")).pack(anchor="w")
        exp_entry = tk.Entry(col1, font=("Segoe UI", 9), bd=1, relief="solid")
        exp_entry.insert(0, str(saved_f.get("target_monthly_expense", "3000.0")))
        exp_entry.pack(fill=tk.X, pady=(2, 6))

        tk.Label(col1, text=t("lbl_guaranteed_pension"), font=("Segoe UI", 8, "bold")).pack(anchor="w")
        pension_entry = tk.Entry(col1, font=("Segoe UI", 9), bd=1, relief="solid")
        pension_entry.insert(0, str(saved_f.get("guaranteed_annual_pension", "0.0")))
        pension_entry.pack(fill=tk.X, pady=(2, 6))

        tk.Label(col1, text=t("lbl_safe_years"), font=("Segoe UI", 8, "bold")).pack(anchor="w")
        safe_years_combo = ttk.Combobox(col1, values=["20", "25", "30"], state="readonly", font=("Segoe UI", 9))
        safe_years_combo.set(str(saved_f.get("target_safe_years", "25")))
        safe_years_combo.pack(fill=tk.X, pady=(2, 4))

        # Col 2 inputs
        tk.Label(col2, text=t("lbl_portfolio_capital"), font=("Segoe UI", 8, "bold")).pack(anchor="w")
        port_entry = tk.Entry(col2, font=("Segoe UI", 9), bd=1, relief="solid")
        port_entry.insert(0, f"{cur_total_val:.2f}")
        port_entry.pack(fill=tk.X, pady=(2, 6))

        tk.Label(col2, text=t("lbl_current_annual_dividends"), font=("Segoe UI", 8, "bold")).pack(anchor="w")
        div_entry = tk.Entry(col2, font=("Segoe UI", 9), bd=1, relief="solid")
        div_entry.insert(0, f"{cur_ann_div:.2f}")
        div_entry.pack(fill=tk.X, pady=(2, 6))

        # Row with growth and savings
        sub_grid = tk.Frame(col2)
        sub_grid.pack(fill=tk.X, pady=(2, 0))

        sg1 = tk.Frame(sub_grid)
        sg1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        tk.Label(sg1, text=t("lbl_div_growth_short"), font=("Segoe UI", 8, "bold")).pack(anchor="w")
        growth_entry = tk.Entry(sg1, font=("Segoe UI", 9), bd=1, relief="solid")
        growth_entry.insert(0, "5.0")
        growth_entry.pack(fill=tk.X, pady=(2, 0))

        sg2 = tk.Frame(sub_grid)
        sg2.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))
        tk.Label(sg2, text=t("lbl_monthly_savings_short"), font=("Segoe UI", 8, "bold")).pack(anchor="w")
        save_entry = tk.Entry(sg2, font=("Segoe UI", 9), bd=1, relief="solid")
        save_entry.insert(0, "1000.0")
        save_entry.pack(fill=tk.X, pady=(2, 0))

        # Results Display Container
        res_frame = tk.LabelFrame(scrollable_frame, text=f" {t('lbl_bernstein_analysis_title')} ", font=("Segoe UI", 9, "bold"), padx=12, pady=10)
        res_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 1. Burn Rate Indicator Banner
        badge_frame = tk.Frame(res_frame, bd=1, relief="solid", padx=10, pady=8)
        badge_frame.pack(fill=tk.X, pady=(0, 8))

        lbl_burn_badge = tk.Label(badge_frame, text="", font=("Segoe UI", 11, "bold"))
        lbl_burn_badge.pack(anchor="w")

        lbl_rle_summary = tk.Label(badge_frame, text="", font=("Segoe UI", 9))
        lbl_rle_summary.pack(anchor="w", pady=(2, 0))

        # 2. Liability Matching vs Risk Portfolio Cards
        split_box = tk.Frame(res_frame)
        split_box.pack(fill=tk.X, pady=(0, 8))

        card_lm = tk.Frame(split_box, bg=self.card_bg, bd=1, relief="solid", padx=10, pady=8)
        card_lm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        tk.Label(card_lm, text=t("lbl_liability_matching"), font=("Segoe UI", 8, "bold"), fg=self.primary_color, bg=self.card_bg).pack(anchor="w")
        lbl_lm_val = tk.Label(card_lm, text="-", font=("Segoe UI", 11, "bold"), fg=self.text_dark, bg=self.card_bg)
        lbl_lm_val.pack(anchor="w", pady=2)
        lbl_lm_cov = tk.Label(card_lm, text="-", font=("Segoe UI", 8), fg="#5f6368" if not self.dark_mode else "#9aa0a6", bg=self.card_bg)
        lbl_lm_cov.pack(anchor="w")

        card_rp = tk.Frame(split_box, bg=self.card_bg, bd=1, relief="solid", padx=10, pady=8)
        card_rp.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        tk.Label(card_rp, text=t("lbl_risk_portfolio"), font=("Segoe UI", 8, "bold"), fg="#188038", bg=self.card_bg).pack(anchor="w")
        lbl_rp_val = tk.Label(card_rp, text="-", font=("Segoe UI", 11, "bold"), fg=self.text_dark, bg=self.card_bg)
        lbl_rp_val.pack(anchor="w", pady=2)
        lbl_rp_status = tk.Label(card_rp, text="-", font=("Segoe UI", 8), fg="#5f6368" if not self.dark_mode else "#9aa0a6", bg=self.card_bg)
        lbl_rp_status.pack(anchor="w")

        # 3. Dual-Engine Cards (Capital SWR vs Dividend Runway)
        dual_box = tk.Frame(res_frame)
        dual_box.pack(fill=tk.X, pady=(0, 8))

        # Engine 1: Capital Safe Withdrawal Target
        eng1_card = tk.LabelFrame(dual_box, text=f" {t('lbl_engine_a_title')} ", font=("Segoe UI", 8, "bold"), padx=8, pady=6)
        eng1_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        lbl_swr_32 = tk.Label(eng1_card, text=f"• {t('lbl_swr_32_rule')}: -", font=("Segoe UI", 9, "bold"), fg=self.primary_color)
        lbl_swr_32.pack(anchor="w", pady=1)

        lbl_swr_40 = tk.Label(eng1_card, text=f"• {t('lbl_swr_40_rule')}: -", font=("Segoe UI", 8), fg=self.text_dark)
        lbl_swr_40.pack(anchor="w", pady=1)

        lbl_swr_prog = tk.Label(eng1_card, text=f"{t('lbl_capital_funded')}: -", font=("Segoe UI", 8), fg="#5f6368" if not self.dark_mode else "#9aa0a6")
        lbl_swr_prog.pack(anchor="w", pady=1)

        # Engine 2: Passive Dividend Cashflow Runway
        eng2_card = tk.LabelFrame(dual_box, text=f" {t('lbl_engine_b_title')} ", font=("Segoe UI", 8, "bold"), padx=8, pady=6)
        eng2_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        lbl_div_cov = tk.Label(eng2_card, text=f"• {t('lbl_dividend_coverage_rle')}: -", font=("Segoe UI", 9, "bold"), fg=self.green_color)
        lbl_div_cov.pack(anchor="w", pady=1)

        lbl_div_shortfall = tk.Label(eng2_card, text=f"• {t('lbl_monthly_shortfall_bullet')}: -", font=("Segoe UI", 8), fg=self.text_dark)
        lbl_div_shortfall.pack(anchor="w", pady=1)

        lbl_div_years = tk.Label(eng2_card, text=f"• {t('lbl_fire_years')}: -", font=("Segoe UI", 8, "bold"), fg="#e37400")
        lbl_div_years.pack(anchor="w", pady=1)

        # 4. Milestone Ladder
        ladder_frame = tk.LabelFrame(scrollable_frame, text=f" {t('lbl_ladder_title')} ", font=("Segoe UI", 8, "bold"), padx=8, pady=6)
        ladder_frame.pack(fill=tk.X, pady=(0, 8))

        tier_labels = {}
        for tier_key, tier_name_key in [
            ("coast", "tier_coast_full"),
            ("barista", "tier_barista_full"),
            ("lean", "tier_lean_full"),
            ("full", "tier_full_full"),
            ("abundant", "tier_abundant_full"),
        ]:
            lbl = tk.Label(ladder_frame, text=f"• {t(tier_name_key)}: -", font=("Segoe UI", 8), fg=self.text_dark)
            lbl.pack(anchor="w", pady=1)
            tier_labels[tier_key] = lbl

        # 5. Bernstein Wisdom Advice Callout Box
        wisdom_box = tk.Frame(res_frame, bg="#f8f9fa" if not self.dark_mode else "#252830", bd=1, relief="solid", padx=10, pady=8)
        wisdom_box.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            wisdom_box,
            text=t("lbl_wisdom_title"),
            font=("Segoe UI", 8, "bold"),
            fg="#e37400",
            bg="#f8f9fa" if not self.dark_mode else "#252830",
        ).pack(anchor="w")

        lbl_wisdom_text = tk.Label(
            wisdom_box,
            text="",
            font=("Segoe UI", 8),
            fg=self.text_dark,
            bg="#f8f9fa" if not self.dark_mode else "#252830",
            justify=tk.LEFT,
            wraplength=700,
        )
        lbl_wisdom_text.pack(anchor="w", pady=(3, 0))

        # Calculation function
        def calc_fire():
            try:
                c_age = int(age_entry.get().strip() or "45")
            except ValueError:
                c_age = 45
            try:
                r_age = int(ret_age_entry.get().strip() or "60")
            except ValueError:
                r_age = 60
            try:
                m_exp = float(exp_entry.get().strip() or "3000.0")
            except ValueError:
                m_exp = 3000.0
            try:
                p_ann = float(pension_entry.get().strip() or "0.0")
            except ValueError:
                p_ann = 0.0
            try:
                s_yrs = float(safe_years_combo.get().strip() or "25.0")
            except ValueError:
                s_yrs = 25.0
            try:
                p_val = float(port_entry.get().strip() or "0.0")
            except ValueError:
                p_val = cur_total_val
            try:
                a_div = float(div_entry.get().strip() or "0.0")
            except ValueError:
                a_div = cur_ann_div
            try:
                div_g = float(growth_entry.get().strip() or "5.0") / 100.0
            except ValueError:
                div_g = 0.05
            try:
                m_sav = float(save_entry.get().strip() or "0.0")
            except ValueError:
                m_sav = 0.0

            res = calc_fire_metrics(
                current_annual_div=a_div,
                target_monthly_expense=m_exp,
                expected_div_growth=div_g,
                current_portfolio_val=p_val,
                monthly_savings=m_sav,
                guaranteed_annual_pension=p_ann,
                target_safe_years=s_yrs,
                current_age=c_age,
                retire_age=r_age,
                holdings=self.holdings,
            )

            burn_rate = res.get("burn_rate_pct", 0.0)
            burn_zone = res.get("burn_zone", "yellow")
            rle_mo = res.get("rle_monthly", 0.0)
            rle_ann = res.get("rle_annual", 0.0)
            ann_exp = res.get("target_annual_expense", 0.0)
            pension_ann = res.get("guaranteed_annual_pension", 0.0)

            # Update Burn Rate Badge
            if burn_zone == "green":
                badge_bg = "#e6f4ea"
                badge_fg = "#137333"
                badge_text = f"🟢 {t('fire_burn_rate')}: {burn_rate:.2f}%  —  {t('zone_green')}"
            elif burn_zone == "yellow":
                badge_bg = "#fef7e0"
                badge_fg = "#b06000"
                badge_text = f"🟡 {t('fire_burn_rate')}: {burn_rate:.2f}%  —  {t('zone_yellow')}"
            else:
                badge_bg = "#fce8e6"
                badge_fg = "#c5221f"
                badge_text = f"🔴 {t('fire_burn_rate')}: {burn_rate:.2f}%  —  {t('zone_red')}"

            badge_frame.config(bg=badge_bg)
            lbl_burn_badge.config(text=badge_text, bg=badge_bg, fg=badge_fg)
            rle_info_str = t("lbl_rle_summary_format", rle_mo=f"{rle_mo:,.0f}", rle_ann=f"{rle_ann:,.0f}", exp=f"{ann_exp:,.0f}", pen=f"{pension_ann:,.0f}")
            lbl_rle_summary.config(text=rle_info_str, bg=badge_bg, fg=self.text_dark)

            # Update Liability Matching vs Risk Portfolio
            lm_target = res.get("liability_matching_target", 0.0)
            lm_cov = res.get("liability_coverage_pct", 0.0)
            rp_surplus = res.get("risk_portfolio_surplus", 0.0)

            lbl_lm_val.config(text=f"${lm_target:,.0f} ({t('lbl_safe_years_reserve', years=s_yrs)})")
            lbl_lm_cov.config(text=t("lbl_portfolio_coverage_format", cov=f"{lm_cov:.1f}"))

            if rp_surplus >= 0:
                lbl_rp_val.config(text=f"+${rp_surplus:,.0f}", fg="#188038")
                lbl_rp_status.config(text=t("lbl_lm_covered_status"), fg="#188038")
            else:
                lbl_rp_val.config(text=f"-${abs(rp_surplus):,.0f}", fg="#d93025")
                lbl_rp_status.config(text=t("lbl_lm_shortfall_status"), fg="#d93025")

            # Update Dual Engines
            cap_32 = res.get("bernstein_swr_32_target", 0.0)
            cap_40 = res.get("fire_number_4pct", 0.0)
            cap_32_pct = (p_val / cap_32 * 100.0) if cap_32 > 0 else 100.0
            cap_40_pct = (p_val / cap_40 * 100.0) if cap_40 > 0 else 100.0

            lbl_swr_32.config(text=f"• {t('lbl_swr_32_rule')}: ${cap_32:,.0f} ({cap_32_pct:.1f}%)")
            lbl_swr_40.config(text=f"• {t('lbl_swr_40_rule')}: ${cap_40:,.0f} ({cap_40_pct:.1f}%)")
            lbl_swr_prog.config(text=t("lbl_swr_prog_format", val=f"{p_val:,.0f}", cov=f"{cap_32_pct:.1f}"))

            div_rle_pct = res.get("dividend_rle_coverage_pct", 0.0)
            shortfall = res.get("monthly_shortfall", 0.0)
            years = res.get("years_to_crossover", 99.0)

            div_color = self.green_color if div_rle_pct >= 100.0 else (self.primary_color if div_rle_pct >= 50.0 else "#e37400")
            lbl_div_cov.config(text=f"• {t('lbl_passive_div_coverage')}: {div_rle_pct:.1f}%", fg=div_color)
            if div_rle_pct >= 100.0:
                lbl_div_shortfall.config(text=t("lbl_div_shortfall_zero"), fg="#188038")
            else:
                lbl_div_shortfall.config(text=t("lbl_div_shortfall_format", shortfall=f"{shortfall:,.0f}", div=f"{a_div/12:,.0f}"), fg=self.text_dark)
            lbl_div_years.config(text=t("lbl_est_crossover_years", years=f"{years:.1f}") if years < 90 else t("lbl_est_crossover_over30"))

            # Update Milestones
            m_data = res.get("milestones", {})
            for k, tier_name_key in [
                ("coast", "tier_coast_full"),
                ("barista", "tier_barista_full"),
                ("lean", "tier_lean_full"),
                ("full", "tier_full_full"),
                ("abundant", "tier_abundant_full"),
            ]:
                if k in m_data and k in tier_labels:
                    t_val = m_data[k]
                    status = t("milestone_reached") if a_div >= t_val else t("milestone_need", target=f"{t_val:,.0f}", need=f"{max(0.0, t_val - a_div):,.0f}")
                    tier_labels[k].config(text=f"• {t(tier_name_key)}: {status}")

            # Update Wisdom
            bernstein_advice = (
                f"{res.get('bernstein_tip', '')}\n\n"
                f"{t('lbl_wisdom_guidance')}"
            )
            lbl_wisdom_text.config(text=bernstein_advice)

        # Wire up presets
        def apply_preset(target_m_exp, target_pension, target_safe_yrs, target_save, target_growth):
            exp_entry.delete(0, tk.END)
            exp_entry.insert(0, str(target_m_exp))
            pension_entry.delete(0, tk.END)
            pension_entry.insert(0, str(target_pension))
            safe_years_combo.set(str(target_safe_yrs))
            save_entry.delete(0, tk.END)
            save_entry.insert(0, str(target_save))
            growth_entry.delete(0, tk.END)
            growth_entry.insert(0, str(target_growth))
            calc_fire()

        # Preset buttons
        btn_y = tk.Button(presets_box, text=t("preset_young"), font=("Segoe UI", 8), relief="groove", bd=1, padx=6, pady=2, command=lambda: apply_preset(3000.0, 0.0, 25, 1500.0, 6.0))
        btn_y.pack(side=tk.LEFT, padx=(0, 4))

        btn_t = tk.Button(presets_box, text=t("preset_transition"), font=("Segoe UI", 8), relief="groove", bd=1, padx=6, pady=2, command=lambda: apply_preset(4000.0, 12000.0, 25, 2500.0, 4.0))
        btn_t.pack(side=tk.LEFT, padx=(0, 4))

        btn_fritz = tk.Button(presets_box, text=t("preset_fritz"), font=("Segoe UI", 8), relief="groove", bd=1, padx=6, pady=2, command=lambda: apply_preset(3500.0, 15000.0, 25, 0.0, 3.0))
        btn_fritz.pack(side=tk.LEFT, padx=(0, 4))

        btn_frank = tk.Button(presets_box, text=t("preset_frank"), font=("Segoe UI", 8), relief="groove", bd=1, padx=6, pady=2, command=lambda: apply_preset(6000.0, 25000.0, 25, 0.0, 4.0))
        btn_frank.pack(side=tk.LEFT, padx=(0, 4))

        # Quick monthly expense buttons
        for amt in [2000, 3000, 4000, 5000, 8000]:
            b_amt = tk.Button(
                exp_quick_frame,
                text=f"${amt:,}",
                font=("Segoe UI", 8),
                relief="groove",
                bd=1,
                padx=5,
                pady=1,
                command=lambda val=amt: (exp_entry.delete(0, tk.END), exp_entry.insert(0, str(float(val))), calc_fire()),
            )
            b_amt.pack(side=tk.LEFT, padx=(0, 3))

        # Bind live keystrokes to auto-calculate
        for ent in [age_entry, ret_age_entry, exp_entry, pension_entry, port_entry, div_entry, growth_entry, save_entry]:
            ent.bind("<KeyRelease>", lambda e: calc_fire())
            ent.bind("<FocusOut>", lambda e: calc_fire())
        safe_years_combo.bind("<<ComboboxSelected>>", lambda e: calc_fire())

        # Bottom Action Bar
        bottom_bar = tk.Frame(scrollable_frame, bg=self.bg_main)
        bottom_bar.pack(fill=tk.X, pady=(6, 0))

        btn_ladder = tk.Button(
            bottom_bar,
            text=t("btn_view_bond_ladder"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg=self.primary_color,
            relief="solid",
            bd=1,
            command=self._show_bond_ladder_dialog,
            padx=10,
            pady=4,
        )
        btn_ladder.pack(side=tk.LEFT, padx=(0, 6))

        btn_actuary = tk.Button(
            bottom_bar,
            text=t("btn_pension_actuary"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#1a73e8",
            relief="solid",
            bd=1,
            command=self._show_pension_actuary_dialog,
            padx=10,
            pady=4,
        )
        btn_actuary.pack(side=tk.LEFT, padx=(0, 6))

        btn_deep_risk = tk.Button(
            bottom_bar,
            text=t("btn_deep_risk_audit"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#1a73e8",
            relief="solid",
            bd=1,
            command=self._show_deep_risk_dialog,
            padx=10,
            pady=4,
        )
        btn_deep_risk.pack(side=tk.LEFT, padx=(0, 6))

        btn_crisis_stress = tk.Button(
            bottom_bar,
            text=t("btn_crisis_stress_test"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#c5221f",
            relief="solid",
            bd=1,
            command=self._show_crisis_stress_test_dialog,
            padx=10,
            pady=4,
        )
        btn_crisis_stress.pack(side=tk.LEFT, padx=(0, 6))

        btn_tax_drag = tk.Button(
            bottom_bar,
            text=t("btn_fee_tax_drag"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#b06000",
            relief="solid",
            bd=1,
            command=self._show_fee_tax_drag_dialog,
            padx=10,
            pady=4,
        )
        btn_tax_drag.pack(side=tk.LEFT, padx=(0, 6))

        btn_reb_5_25 = tk.Button(
            bottom_bar,
            text=t("btn_rebalance_5_25"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#137333",
            relief="solid",
            bd=1,
            command=self._show_rebalancing_5_25_dialog,
            padx=10,
            pady=4,
        )
        btn_reb_5_25.pack(side=tk.LEFT, padx=(0, 6))

        btn_simplicity = tk.Button(
            bottom_bar,
            text=t("btn_simplicity_index"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff" if not self.dark_mode else "#2d3342",
            fg="#681da8",
            relief="solid",
            bd=1,
            command=self._show_simplicity_index_dialog,
            padx=10,
            pady=4,
        )
        btn_simplicity.pack(side=tk.LEFT, padx=(0, 6))

        btn_calc = tk.Button(
            bottom_bar,
            text=f"🔄 {t('btn_calc_fire')}",
            font=("Segoe UI", 9, "bold"),
            bg="#e37400",
            fg="#ffffff",
            relief="solid",
            bd=1,
            command=calc_fire,
            padx=14,
            pady=4,
        )
        btn_calc.pack(side=tk.RIGHT)

        btn_close = tk.Button(
            bottom_bar,
            text=t("btn_close") if "btn_close" in TRANSLATIONS.get(get_current_language(), {}) else "Close",
            font=("Segoe UI", 9),
            command=dlg.destroy,
            padx=10,
            pady=4,
        )
        btn_close.pack(side=tk.RIGHT, padx=(0, 8))

        calc_fire()

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 780, 740
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _open_feature_guide_dialog(self):
        """
        Interactive in-app User Guide & Tips modal dialog explaining all 10 core features
        with detailed step-by-step instructions, operational tips, and investment wisdom.
        """
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_feature_guide_title"))
        dlg.geometry("820x660")
        dlg.minsize(760, 560)
        dlg.transient(self.root)

        main_box = ttk.Frame(dlg, padding=12)
        main_box.pack(fill=tk.BOTH, expand=True)

        # Header
        top_hdr = tk.Frame(main_box)
        top_hdr.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            top_hdr,
            text=t("guide_header_title"),
            font=("Segoe UI", 13, "bold"),
            fg="#e37400",
        ).pack(anchor="w")

        tk.Label(
            top_hdr,
            text=t("guide_header_subtitle"),
            font=("Segoe UI", 9),
            fg="#5f6368" if not self.dark_mode else "#9aa0a6",
        ).pack(anchor="w", pady=(1, 0))

        # Split Pane: Left topics listbox, Right rich content area
        split_pane = tk.PanedWindow(main_box, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=4)
        split_pane.pack(fill=tk.BOTH, expand=True)

        left_side = ttk.Frame(split_pane, width=220)
        split_pane.add(left_side, minsize=180)

        right_side = ttk.Frame(split_pane)
        split_pane.add(right_side, minsize=400)

        # Topics Listbox
        tk.Label(left_side, text=t("guide_topics_title"), font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        topic_listbox = tk.Listbox(
            left_side,
            font=("Segoe UI", 9),
            selectmode=tk.SINGLE,
            activestyle="none",
            bd=1,
            relief="solid",
            highlightthickness=0,
        )
        topic_listbox.pack(fill=tk.BOTH, expand=True)

        # Right Text Area with scrollbar
        text_scroll = ttk.Scrollbar(right_side, orient="vertical")
        guide_text = tk.Text(
            right_side,
            font=("Segoe UI", 10),
            wrap=tk.WORD,
            yscrollcommand=text_scroll.set,
            padx=12,
            pady=10,
            bd=1,
            relief="solid",
            bg="#ffffff" if not self.dark_mode else "#202124",
            fg="#202124" if not self.dark_mode else "#e8eaed",
        )
        text_scroll.config(command=guide_text.yview)
        guide_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Text styles
        guide_text.tag_config("h1", font=("Segoe UI", 13, "bold"), foreground="#1a73e8" if not self.dark_mode else "#8ab4f8", spacing3=6)
        guide_text.tag_config("h2", font=("Segoe UI", 10, "bold"), foreground="#e37400", spacing1=8, spacing3=4)
        guide_text.tag_config("bold", font=("Segoe UI", 9, "bold"))
        guide_text.tag_config("bullet", lmargin1=16, lmargin2=28, spacing2=3)
        guide_text.tag_config("quote", font=("Segoe UI", 9, "italic"), foreground="#188038", lmargin1=20, lmargin2=20, spacing1=6, spacing3=6)
        guide_text.tag_config("code", font=("Consolas", 9), background="#f1f3f4" if not self.dark_mode else "#303134")

        # Multilingual content definitions for the 10 features
        is_zh = get_current_language() in ("zh_TW", "zh_CN")
        topics = [
            ("overview", "📖 系統總覽與快速上手" if is_zh else "📖 Overview & Quick Start"),
            ("rebalance", "⚖️ 1. 資產再平衡與目標權重" if is_zh else "⚖️ 1. Portfolio Rebalancing"),
            ("benchmark", "📊 2. 大盤基準對比 (SPY / TSX 60)" if is_zh else "📊 2. Benchmark Comparison"),
            ("fx_exposure", "💱 3. 多幣種匯率與幣種曝險" if is_zh else "💱 3. Multi-Currency & FX"),
            ("fire_model", "🔥 4. 伯恩斯坦退休自由雙軌模型" if is_zh else "🔥 4. Bernstein FIRE Model"),
            ("stop_loss", "🎯 5. 停損與目標獲利警示" if is_zh else "🎯 5. Stop-Loss & Target"),
            ("watchlist_tags", "🏷️ 6. 自選股標籤與分類過濾" if is_zh else "🏷️ 6. Watchlist Tags & Filter"),
            ("what_if", "💡 7. 買入前 'What-If' 情景模擬" if is_zh else "💡 7. Pre-Trade What-If Simulator"),
            ("data_health", "🩺 8. 資料健康檢查與自動修復" if is_zh else "🩺 8. Data Health & Repair"),
            ("quick_picks", "⚡ 9. 熱門代碼快捷鍵" if is_zh else "⚡ 9. Quick-Picks Shortcuts"),
            ("network_diag", "⚠️ 10. 行情網路診斷與備援" if is_zh else "⚠️ 10. Network Diagnostics"),
        ]

        for _, title in topics:
            topic_listbox.insert(tk.END, title)

        def display_topic(key):
            guide_text.config(state=tk.NORMAL)
            guide_text.delete("1.0", tk.END)

            if key == "overview":
                if is_zh:
                    guide_text.insert(tk.END, "Google 財經投資組合追蹤器與計算器 — 完整功能導覽\n", "h1")
                    guide_text.insert(tk.END, "本系統專為穩健投資者、股息現金流族群與 FIRE 退休規劃者打造，整合了即時報價、多幣種即時匯率、大盤基準回測對比、以及威廉·伯恩斯坦 (William J. Bernstein) 的《投資金律》資產配置與雙軌退休模型。\n\n")
                    guide_text.insert(tk.END, "快速入門核心操作：\n", "h2")
                    guide_text.insert(tk.END, "• 1. 新增股票：點擊上方 '➕ 新增股票'，支援一鍵點選熱門 ETF 與藍籌代碼 (SPY, VDY.TO, 0005.HK)。\n", "bullet")
                    guide_text.insert(tk.END, "• 2. 匯率切換：在右上角 '💱 Summary In' 切換 CAD / USD / HKD，全投資組合即時無損換算。\n", "bullet")
                    guide_text.insert(tk.END, "• 3. 雙軌退休規劃：點擊左側 '🔥 FIRE 財務自由進度跑道'，評估待攤生活費 (RLE) 與燒錢率 (Burn Rate)。\n", "bullet")
                    guide_text.insert(tk.END, "• 4. 資料庫維護：點擊頂部 '🩺 資料完整度檢查'，可一鍵自動掃描並修復重複代碼與貨幣缺失。\n", "bullet")
                else:
                    guide_text.insert(tk.END, "Google Finance Tracker & Calculator — Feature Tour\n", "h1")
                    guide_text.insert(tk.END, "Designed for long-term dividend investors, asset allocators, and FIRE retirement planners. Integrates live market quotes, real-time multi-currency FX conversions, S&P 500 / TSX 60 benchmarks, and William J. Bernstein's ('The Four Pillars of Investing') dual-engine retirement framework.\n\n")
                    guide_text.insert(tk.END, "Quick Start Essentials:\n", "h2")
                    guide_text.insert(tk.END, "• 1. Add Stock: Click '➕ Add Stock' on the top bar. Use Quick-Pick buttons for instant regional ticker formatting.\n", "bullet")
                    guide_text.insert(tk.END, "• 2. Currency Switcher: Use '💱 Summary In' in the portfolio bar to switch CAD / USD / HKD instantaneously.\n", "bullet")
                    guide_text.insert(tk.END, "• 3. Dual-Engine FIRE: Click '🔥 FIRE & Financial Freedom Runway' to analyze RLE and Burn Rate zones.\n", "bullet")
                    guide_text.insert(tk.END, "• 4. Data Scanner: Click '🩺 Data Health Check' to audit and auto-repair CSV files with 1 click.\n", "bullet")

            elif key == "rebalance":
                if is_zh:
                    guide_text.insert(tk.END, "⚖️ 功能 1：資產再平衡與目標權重 (Portfolio Rebalancing)\n", "h1")
                    guide_text.insert(tk.END, "【功能目的】防止投資組合因部分股票過度上漲導致風險過度集中，透過機械化規則強迫落實「買低賣高」。\n\n")
                    guide_text.insert(tk.END, "【操作步驟】\n", "h2")
                    guide_text.insert(tk.END, "1. 點擊頂部工具列 '⚖️ 資產再平衡' 按鈕。\n", "bullet")
                    guide_text.insert(tk.END, "2. 在彈出視窗的表格中，輸入每檔持股的 '目標權重 %'（系統會自動檢查總和是否為 100%）。\n", "bullet")
                    guide_text.insert(tk.END, "3. 選擇再平衡模式：\n", "bullet")
                    guide_text.insert(tk.END, "   • 完整再平衡 (Full Rebalance)：計算賣出超配股票並買入低配股票。\n", "bullet")
                    guide_text.insert(tk.END, "   • 僅投入新資金 (Cash Injection Only)：輸入可用現金，只買不賣，避免觸發資本利得稅與手續費！\n", "bullet")
                    guide_text.insert(tk.END, "4. 點擊 '計算再平衡訂單'，取得精確的建議買賣股數與金額。\n\n", "bullet")
                    guide_text.insert(tk.END, "【投資大師技巧】伯恩斯坦指出：投資者應定期（例如每年一次或偏離超過5%時）進行再平衡，排除人為貪婪與恐懼，鎖定市場波動利潤。\n", "quote")
                else:
                    guide_text.insert(tk.END, "⚖️ Feature 1: Portfolio Rebalancing & Target Allocation\n", "h1")
                    guide_text.insert(tk.END, "Purpose: Prevents your portfolio from taking on unintended risk when certain stocks outgrow their allocation, enforcing a disciplined buy-low-sell-high regime.\n\n")
                    guide_text.insert(tk.END, "Operational Steps:\n", "h2")
                    guide_text.insert(tk.END, "1. Click '⚖️ Rebalance Portfolio' on the top bar.\n", "bullet")
                    guide_text.insert(tk.END, "2. Enter your Target % for each position (system verifies sum equals 100%).\n", "bullet")
                    guide_text.insert(tk.END, "3. Select Rebalance Mode:\n", "bullet")
                    guide_text.insert(tk.END, "   • Full Rebalance: Generates both BUY orders for underweighted stocks and SELL orders for overweighted stocks.\n", "bullet")
                    guide_text.insert(tk.END, "   • Cash Injection Only (Buy Only): Allocates newly injected cash without selling existing shares, avoiding taxable capital gains and broker fees!\n", "bullet")
                    guide_text.insert(tk.END, "4. Click 'Calculate Rebalance Orders' to review exact order sizes.\n\n", "bullet")
                    guide_text.insert(tk.END, "Bernstein Wisdom: Rebalance on a calendar schedule (e.g. annually) or when assets drift beyond 5% tolerance bands to systematically harness the rebalancing premium.\n", "quote")

            elif key == "benchmark":
                if is_zh:
                    guide_text.insert(tk.END, "📊 功能 2：大盤基準對比 SPY / TSX 60 (Benchmark Comparison)\n", "h1")
                    guide_text.insert(tk.END, "【功能目的】客觀衡量個人投資組合表現是否超越被動大盤指數，避免承擔了高風險卻跑輸指數。\n\n")
                    guide_text.insert(tk.END, "【操作步驟】\n", "h2")
                    guide_text.insert(tk.END, "1. 前往 '📉 互動式圖表' 分頁。\n", "bullet")
                    guide_text.insert(tk.END, "2. 點擊頂部對比按鈕：\n", "bullet")
                    guide_text.insert(tk.END, "   • '對比 標普500 (SPY)'：疊加美股標普500指數 ETF 走勢。\n", "bullet")
                    guide_text.insert(tk.END, "   • '對比 加拿大TSX 60 (XIU)'：疊加加拿大60大權值指數走勢。\n", "bullet")
                    guide_text.insert(tk.END, "   • '大盤對比: 關閉'：隱藏基準線，專注單一持股。\n", "bullet")
                    guide_text.insert(tk.END, "3. 在分析分頁中，可直接查看投資組合的 Alpha（超額報酬）與 Beta（市場波動相關度）。\n\n", "bullet")
                    guide_text.insert(tk.END, "【投資大師技巧】超過85%的主動投資人在長期無法戰勝大盤。定期將績效與 SPY/XIU 基準對比，能幫助你維持理性並及時檢視持股品質。\n", "quote")
                else:
                    guide_text.insert(tk.END, "📊 Feature 2: Benchmark Comparison (SPY & TSX 60 XIU)\n", "h1")
                    guide_text.insert(tk.END, "Purpose: Objectively measure whether your stock picks are beating the market and evaluate your portfolio's risk-adjusted return.\n\n")
                    guide_text.insert(tk.END, "Operational Steps:\n", "h2")
                    guide_text.insert(tk.END, "1. Navigate to the '📉 Interactive Chart' tab.\n", "bullet")
                    guide_text.insert(tk.END, "2. Click the benchmark toggle buttons:\n", "bullet")
                    guide_text.insert(tk.END, "   • 'vs S&P 500 (SPY)': Overlays normalized SPY return curve.\n", "bullet")
                    guide_text.insert(tk.END, "   • 'vs TSX 60 (XIU)': Overlays normalized Canadian blue-chip XIU return curve.\n", "bullet")
                    guide_text.insert(tk.END, "   • 'Benchmark: Off': Resets to solitary stock view.\n", "bullet")
                    guide_text.insert(tk.END, "3. Review Portfolio Alpha and Beta metrics in the Analytics tab.\n\n", "bullet")
                    guide_text.insert(tk.END, "Bernstein Wisdom: Over 15+ year horizons, passive low-cost indexing outperforms the vast majority of active stock pickers. Benchmarking keeps expectations grounded.\n", "quote")

            elif key == "fx_exposure":
                if is_zh:
                    guide_text.insert(tk.END, "💱 功能 3：多幣種匯率與幣種曝險 (Multi-Currency & FX Exposure)\n", "h1")
                    guide_text.insert(tk.END, "【功能目的】支援跨國投資（美股 USD、加股 CAD、港股 HKD），消除跨幣別資產統計的匯率障礙，並監控匯率風險。\n\n")
                    guide_text.insert(tk.END, "【操作步驟】\n", "h2")
                    guide_text.insert(tk.END, "1. 彙總貨幣切換：在主視窗左上方 '💱 Summary In' 下拉選單選擇 CAD 或 USD。\n", "bullet")
                    guide_text.insert(tk.END, "2. 即時匯率換算：全投資組合總市值、未實現損益、年度股息將自動按即時銀行間匯率精確折算，不破壞每檔持股原始幣別。\n", "bullet")
                    guide_text.insert(tk.END, "3. 幣種曝險圓餅圖：切換至 '📊 資產配置與分析' 分頁，在視圖選單選擇 '幣別資產分佈'，可清楚掌握美元與加幣資產比例。\n\n", "bullet")
                    guide_text.insert(tk.END, "【投資大師技巧】非本國貨幣資產過多會面臨匯率波動風險。善用幣別資產分佈圖，確保匯率曝險符合你的個人退休居住地與開銷需求。\n", "quote")
                else:
                    guide_text.insert(tk.END, "💱 Feature 3: Multi-Currency FX Conversion & Currency Exposure\n", "h1")
                    guide_text.insert(tk.END, "Purpose: Seamless cross-border tracking across USD, CAD, HKD, and other currencies, preventing currency risk blindness.\n\n")
                    guide_text.insert(tk.END, "Operational Steps:\n", "h2")
                    guide_text.insert(tk.END, "1. Summary Currency Switcher: Use the '💱 Summary In' dropdown in the portfolio bar to toggle between USD and CAD.\n", "bullet")
                    guide_text.insert(tk.END, "2. Non-Destructive Conversion: All cards, totals, and tables convert instantly while preserving each stock's native currency.\n", "bullet")
                    guide_text.insert(tk.END, "3. Currency Exposure Pie: In the '📊 Allocation & Analytics' tab, set View to 'Currency Exposure' to monitor your domestic vs foreign currency split.\n\n", "bullet")
                    guide_text.insert(tk.END, "Bernstein Wisdom: Retirees should match their asset currencies with their spending liabilities. Avoid excessive foreign currency risk in retirement.\n", "quote")

            elif key == "fire_model":
                if is_zh:
                    guide_text.insert(tk.END, "🔥 功能 4：伯恩斯坦退休自由雙軌模型 (William J. Bernstein FIRE Model)\n", "h1")
                    guide_text.insert(tk.END, "【核心理論源自《投資金律》William J. Bernstein 第6、7、16、17章】\n\n")
                    guide_text.insert(tk.END, "四大核心支柱：\n", "h2")
                    guide_text.insert(tk.END, "1. 待攤生活費用 (Residual Living Expenses, RLE)：\n", "bullet")
                    guide_text.insert(tk.END, "   RLE = 總生活開銷 - 每年保證年金/公積金。保證年金直接吸收生活底線，降低本金提取壓力。\n", "bullet")
                    guide_text.insert(tk.END, "2. 燒錢率 (Burn Rate % = RLE / 投資組合本金)：\n", "bullet")
                    guide_text.insert(tk.END, "   • 🟢 < 2.0% (自由充裕區 / Frank): 贏得退休賽局！極其安全，股息足以直接覆蓋日常開銷，本金完全無虞。\n", "bullet")
                    guide_text.insert(tk.END, "   • 🟡 2.0% - 3.5% (穩健可持續區): 伯恩斯坦推薦黃金區間，建議延後領取社會年金至70歲，維持穩健平衡配置。\n", "bullet")
                    guide_text.insert(tk.END, "   • 🔴 > 3.5% (順序風險警戒區 / Fritz): 退休前5年若遇股市大跌恐發生毀滅性本金縮水，切忌過度冒險！\n", "bullet")
                    guide_text.insert(tk.END, "3. 負債配合組合 (Liability Matching) vs. 風險投資組合 (Risk Portfolio)：\n", "bullet")
                    guide_text.insert(tk.END, "   伯恩斯坦強烈建議：提撥 20-25 年的 RLE 於無風險資產（TIPS、短期公債、定存）；超出的盈餘部分才投入風險投資組合追求成長或傳承！\n", "bullet")
                    guide_text.insert(tk.END, "4. 雙軌退休跑道：\n", "bullet")
                    guide_text.insert(tk.END, "   • 軌道A (資本提取): 伯恩斯坦 3.2% 守則 (本金需為 RLE 的 31.25倍)。\n", "bullet")
                    guide_text.insert(tk.END, "   • 軌道B (被動股息現金流): 當每年股息收入達到 100% RLE 時，完全不需要賣出任何一股股票即可安穩退休！\n\n", "bullet")
                    guide_text.insert(tk.END, "【投資大師名言】「當你已經贏得了比賽，就該適可而止。」不要再為了貪圖額外報酬而把已贏得的退休安寧拿去冒險。\n", "quote")
                else:
                    guide_text.insert(tk.END, "🔥 Feature 4: William J. Bernstein FIRE & Freedom Model\n", "h1")
                    guide_text.insert(tk.END, "Core framework derived from 'The Four Pillars of Investing' (William J. Bernstein, Chapters 6, 7, 16, 17):\n\n")
                    guide_text.insert(tk.END, "The 4 Pillars of the Model:\n", "h2")
                    guide_text.insert(tk.END, "1. Residual Living Expenses (RLE):\n", "bullet")
                    guide_text.insert(tk.END, "   RLE = Total Living Expenses - Guaranteed Pension/Social Security. Guaranteed annuities absorb baseline needs and drastically reduce withdrawal stress.\n", "bullet")
                    guide_text.insert(tk.END, "2. Burn Rate (%) = RLE / Portfolio Value:\n", "bullet")
                    guide_text.insert(tk.END, "   • 🟢 < 2.0% (Safe & Abundant / Frank Zone): You have won the game! Dividends can pay for life without touching principal.\n", "bullet")
                    guide_text.insert(tk.END, "   • 🟡 2.0% - 3.5% (Sustainable Safe Zone): Bernstein's optimal corridor. Delay pension to age 70 and maintain 20-25 years in safe assets.\n", "bullet")
                    guide_text.insert(tk.END, "   • 🔴 > 3.5% (High Sequence-of-Returns Risk / Fritz Zone): Extreme vulnerability to early retirement bear markets.\n", "bullet")
                    guide_text.insert(tk.END, "3. Liability Matching Portfolio vs. Risk Portfolio:\n", "bullet")
                    guide_text.insert(tk.END, "   Bernstein's golden rule: Allocate 20-25 years of RLE into safe debt assets (TIPS, short Treasuries, CDs). Only surplus capital goes into the Risk Portfolio for equity growth and legacy!\n", "bullet")
                    guide_text.insert(tk.END, "4. Dual-Engine Model:\n", "bullet")
                    guide_text.insert(tk.END, "   • Engine A (Capital Target): Bernstein 3.2% Rule (31.25x RLE) vs. 4.0% Rule.\n", "bullet")
                    guide_text.insert(tk.END, "   • Engine B (Dividend Cashflow): When dividends cover 100% of RLE, you never have to liquidate shares in a crash!\n\n", "bullet")
                    guide_text.insert(tk.END, "Bernstein Quote: 'When you have won the game, stop playing.' Do not take risks with money you need for money you do not need.\n", "quote")

            elif key == "stop_loss":
                if is_zh:
                    guide_text.insert(tk.END, "🎯 功能 5：停損與目標獲利警示 (Stop-Loss & Target-Sell Alerts)\n", "h1")
                    guide_text.insert(tk.END, "【功能目的】建立機械化風險控管與停利紀律，杜絕抱上抱下與捨不得停損的人性盲點。\n\n")
                    guide_text.insert(tk.END, "【操作步驟】\n", "h2")
                    guide_text.insert(tk.END, "1. 在 '📈 持股與報價' 或 '👁️ 監控名單' 中，雙擊任意持股或點擊 '✏️ 編輯'。\n", "bullet")
                    guide_text.insert(tk.END, "2. 設定 '停損價' (Stop-Loss) 與 '目標賣出價' (Target-Sell)。\n", "bullet")
                    guide_text.insert(tk.END, "3. 當市場價格跌破停損價時，表格會以醒目紅色標註 🚨 停損警示；當達到目標賣出價時，則以綠色標註 🎯 停利觸發。\n\n", "bullet")
                    guide_text.insert(tk.END, "【投資大師技巧】嚴格的停損能保證投資者在看錯時將損失限制在可控範圍，避免單一重倉股重創本金。\n", "quote")
                else:
                    guide_text.insert(tk.END, "🎯 Feature 5: Stop-Loss & Target-Sell Price Triggers\n", "h1")
                    guide_text.insert(tk.END, "Purpose: Automates trading discipline, enforcing risk management and profit-taking without emotional hesitation.\n\n")
                    guide_text.insert(tk.END, "Operational Steps:\n", "h2")
                    guide_text.insert(tk.END, "1. In Holdings or Watchlist, select a stock and click '✏️ Edit'.\n", "bullet")
                    guide_text.insert(tk.END, "2. Enter your Stop-Loss price and Target-Sell exit price.\n", "bullet")
                    guide_text.insert(tk.END, "3. Real-time alerts: If current price breaches Stop-Loss, the table highlights in red (🚨 STOP TRIGGERED). If Target-Sell is hit, it displays in green (🎯 TARGET HIT).\n\n", "bullet")
                    guide_text.insert(tk.END, "Pro Tip: Setting clear exit targets beforehand protects you from panic-selling at bottoms and greed-driven round-trips at tops.\n", "quote")

            elif key == "watchlist_tags":
                if is_zh:
                    guide_text.insert(tk.END, "🏷️ 功能 6：自選股標籤與分類過濾 (Watchlist Tags & Smart Filters)\n", "h1")
                    guide_text.insert(tk.END, "【功能目的】將自選股按策略主題分類（如高股息、成長、科技、加拿大銀行、美股大盤），快速聚焦當下分析重點。\n\n")
                    guide_text.insert(tk.END, "【操作步驟】\n", "h2")
                    guide_text.insert(tk.END, "1. 前往 '👁️ 監控名單' 分頁。\n", "bullet")
                    guide_text.insert(tk.END, "2. 新增或編輯自選股時，在 '標籤 / 分類' 欄位輸入標籤（例如：'Dividend', 'Tech', 'ETF'）。\n", "bullet")
                    guide_text.insert(tk.END, "3. 頂部會自動生成標籤按鈕，點擊特定標籤（例如 'Dividend'）即可即時篩選該分類的追蹤股票。\n\n", "bullet")
                    guide_text.insert(tk.END, "【投資大師技巧】將潛在買入標的依照「防禦股」與「成長股」分類，在市場大跌時即可第一時間切換防禦標的迅速低接。\n", "quote")
                else:
                    guide_text.insert(tk.END, "🏷️ Feature 6: Watchlist Tags & Categorical Smart Filters\n", "h1")
                    guide_text.insert(tk.END, "Purpose: Organize your prospective investment ideas by strategy (e.g. Dividend, Tech, Energy, Canadian-Bank, ETF) for instant filtering.\n\n")
                    guide_text.insert(tk.END, "Operational Steps:\n", "h2")
                    guide_text.insert(tk.END, "1. Open the '👁️ Monitoring List' tab.\n", "bullet")
                    guide_text.insert(tk.END, "2. When adding or editing a watchlist item, enter comma-separated tags in the 'Tags / Category' field.\n", "bullet")
                    guide_text.insert(tk.END, "3. Click on the dynamically generated tag buttons at the top of the tab to filter the view instantly.\n\n", "bullet")
                    guide_text.insert(tk.END, "Pro Tip: Combine tags with Target Buy Prices to quickly spot bargain entry points when specific sectors pull back.\n", "quote")

            elif key == "what_if":
                if is_zh:
                    guide_text.insert(tk.END, "💡 功能 7：買入前 'What-If' 情景模擬器 (Pre-Trade Simulator)\n", "h1")
                    guide_text.insert(tk.END, "【功能目的】在實際下單前，預先沙盤推演一筆新交易對整體投資組合的具體影響。\n\n")
                    guide_text.insert(tk.END, "【操作步驟】\n", "h2")
                    guide_text.insert(tk.END, "1. 點擊頂部工具列 '💡 假設情境模擬'。\n", "bullet")
                    guide_text.insert(tk.END, "2. 輸入擬買入股票代碼（如 TD.TO）與預計投入資金（如 $10,000）。\n", "bullet")
                    guide_text.insert(tk.END, "3. 點擊 '執行情境模擬'，系統將立即展示：\n", "bullet")
                    guide_text.insert(tk.END, "   • 模擬後的總市值與增幅\n", "bullet")
                    guide_text.insert(tk.END, "   • 投資組合平均殖利率的變化 (增加或稀釋)\n", "bullet")
                    guide_text.insert(tk.END, "   • 每年預計新增的被動股息現金流金額\n", "bullet")
                    guide_text.insert(tk.END, "   • 該標的在整體組合中的權重占比\n\n", "bullet")
                    guide_text.insert(tk.END, "【投資大師技巧】避免因為盲目追求高殖利率單一股票，而無意間大幅提高該檔股票的曝險比例。\n", "quote")
                else:
                    guide_text.insert(tk.END, "💡 Feature 7: Pre-Trade 'What-If' Portfolio Simulator\n", "h1")
                    guide_text.insert(tk.END, "Purpose: Test prospective trades before execution to see exact impact on portfolio yield, annual dividend income, and concentration risk.\n\n")
                    guide_text.insert(tk.END, "Operational Steps:\n", "h2")
                    guide_text.insert(tk.END, "1. Click '💡 What-If Simulator' on the top bar.\n", "bullet")
                    guide_text.insert(tk.END, "2. Enter ticker symbol (e.g. TD.TO) and hypothetical purchase amount (e.g. $10,000).\n", "bullet")
                    guide_text.insert(tk.END, "3. Click 'Run Simulation' to immediately see:\n", "bullet")
                    guide_text.insert(tk.END, "   • New total portfolio valuation\n", "bullet")
                    guide_text.insert(tk.END, "   • Yield shift: whether the purchase increases or dilutes portfolio dividend yield\n", "bullet")
                    guide_text.insert(tk.END, "   • Incremental annual passive dividend dollars added\n", "bullet")
                    guide_text.insert(tk.END, "   • Post-trade holding weight percentage\n\n", "bullet")
                    guide_text.insert(tk.END, "Pro Tip: Always verify that a high-yield purchase does not push single-stock concentration beyond 5-10% of total wealth.\n", "quote")

            elif key == "data_health":
                if is_zh:
                    guide_text.insert(tk.END, "🩺 功能 8：資料健康度檢測與自動修復 (Data Health Scanner)\n", "h1")
                    guide_text.insert(tk.END, "【功能目的】診斷並自動修正 CSV 資料庫中可能存在的格式異常、缺少貨幣、重複代碼或損壞數值。\n\n")
                    guide_text.insert(tk.END, "【操作步驟】\n", "h2")
                    guide_text.insert(tk.END, "1. 點擊頂部工具列 '🩺 資料完整度檢查'。\n", "bullet")
                    guide_text.insert(tk.END, "2. 系統會自動對持股表與監控名單進行多達 8 項完整性校驗：\n", "bullet")
                    guide_text.insert(tk.END, "   • 檢查是否有缺失 Currency 欄位\n", "bullet")
                    guide_text.insert(tk.END, "   • 檢查是否有重疊代碼（如 0005 與 0005.HK）\n", "bullet")
                    guide_text.insert(tk.END, "   • 檢查股數、買入價、現價是否為合法非負浮點數\n", "bullet")
                    guide_text.insert(tk.END, "3. 若發現異常，點擊 '🔧 一鍵自動修復所有問題'，系統會先自動建立安全備份，再一鍵標準化與修復所有欄位！\n\n", "bullet")
                    guide_text.insert(tk.END, "【投資大師技巧】乾淨無誤的底層資料是精確計算財務自由跑道與再平衡權重的基石。\n", "quote")
                else:
                    guide_text.insert(tk.END, "🩺 Feature 8: Automated Data Health Scanner & Auto-Repair\n", "h1")
                    guide_text.insert(tk.END, "Purpose: Automatically scans and corrects CSV formatting errors, missing currency fields, ticker duplicates, and corrupted values.\n\n")
                    guide_text.insert(tk.END, "Operational Steps:\n", "h2")
                    guide_text.insert(tk.END, "1. Click '🩺 Data Health Check' on the top bar.\n", "bullet")
                    guide_text.insert(tk.END, "2. The engine performs an 8-point integrity audit:\n", "bullet")
                    guide_text.insert(tk.END, "   • Detects missing or blank Currency attributes\n", "bullet")
                    guide_text.insert(tk.END, "   • Identifies orphan duplicate symbols (e.g. 0005 vs 0005.HK)\n", "bullet")
                    guide_text.insert(tk.END, "   • Validates numerical non-negative constraints on shares and prices\n", "bullet")
                    guide_text.insert(tk.END, "3. If issues are detected, click '🔧 Auto-Fix All Issues'. The scanner creates an atomic backup before executing safe repairs!\n\n", "bullet")
                    guide_text.insert(tk.END, "Pro Tip: Run a Data Health Check periodically to ensure your portfolio database remains spotless.\n", "quote")

            elif key == "quick_picks":
                if is_zh:
                    guide_text.insert(tk.END, "⚡ 功能 9：熱門代碼快捷鍵 (Quick-Picks Ticker Shortcuts)\n", "h1")
                    guide_text.insert(tk.END, "【功能目的】一鍵代入常用熱門標的，包含標準交易所後綴，避免手動輸入錯誤導致 404 查無行情。\n\n")
                    guide_text.insert(tk.END, "【操作步驟】\n", "h2")
                    guide_text.insert(tk.END, "1. 在 '➕ 新增股票' 或 '新增自選股' 對話框中。\n", "bullet")
                    guide_text.insert(tk.END, "2. 頂部設有熱門快捷按鈕群：\n", "bullet")
                    guide_text.insert(tk.END, "   • 美股指數與科技藍籌：SPY, VOO, SCHD, AAPL, MSFT\n", "bullet")
                    guide_text.insert(tk.END, "   • 加拿大高股息與權值：VDY.TO, XIU.TO, TD.TO, ENB.TO\n", "bullet")
                    guide_text.insert(tk.END, "   • 港股藍籌股息：0005.HK (匯豐控股), 0941.HK (中國移動)\n", "bullet")
                    guide_text.insert(tk.END, "3. 單擊任意代碼按鈕，系統將自動填入正確代碼、名稱與對應貨幣！\n\n", "bullet")
                    guide_text.insert(tk.END, "【投資大師技巧】各交易所對代碼有不同後綴規則（加股為 .TO，港股為 4位數.HK）。快捷鍵能確保輸入零錯誤。\n", "quote")
                else:
                    guide_text.insert(tk.END, "⚡ Feature 9: Quick-Picks Regional Ticker Shortcuts\n", "h1")
                    guide_text.insert(tk.END, "Purpose: One-click population of popular index ETFs and blue-chip dividend stalwarts with exact regional exchange suffixes.\n\n")
                    guide_text.insert(tk.END, "Operational Steps:\n", "h2")
                    guide_text.insert(tk.END, "1. In '➕ Add Stock' or 'Add Watchlist' dialogs.\n", "bullet")
                    guide_text.insert(tk.END, "2. Click any of the Quick-Pick buttons:\n", "bullet")
                    guide_text.insert(tk.END, "   • US: SPY, VOO, SCHD, AAPL, MSFT\n", "bullet")
                    guide_text.insert(tk.END, "   • Canada: VDY.TO, XIU.TO, TD.TO, ENB.TO\n", "bullet")
                    guide_text.insert(tk.END, "   • Hong Kong: 0005.HK (HSBC), 0941.HK (China Mobile)\n", "bullet")
                    guide_text.insert(tk.END, "3. Auto-fills ticker, friendly name, and matching currency instantly.\n\n", "bullet")
                    guide_text.insert(tk.END, "Pro Tip: Regional suffixes (.TO for Toronto, .HK for Hong Kong) prevent 404 quote lookup errors.\n", "quote")

            elif key == "network_diag":
                if is_zh:
                    guide_text.insert(tk.END, "⚠️ 功能 10：行情網路診斷與備援 (Network Diagnostics & Fallbacks)\n", "h1")
                    guide_text.insert(tk.END, "【功能目的】診斷即時行情連線狀態，並具備多重備援引擎，確保在主要數據源斷線或限速時仍能正常運作。\n\n")
                    guide_text.insert(tk.END, "【操作步驟】\n", "h2")
                    guide_text.insert(tk.END, "1. 點擊頂部工具列 '⚠️ 網路診斷詳情'。\n", "bullet")
                    guide_text.insert(tk.END, "2. 檢視目前對 Yahoo Finance 及 Stooq 備援伺服器的連線延遲 (ms)、HTTP 狀態代碼與快取命中率。\n", "bullet")
                    guide_text.insert(tk.END, "3. 當主數據源遇到 HTTP 404 或 429 速率限制時，系統會自動切換至備援引擎並嘗試後綴補正（如 0005 -> 0005.HK）。\n\n", "bullet")
                    guide_text.insert(tk.END, "【投資大師技巧】高可用性架構能保證即使在市場劇烈波動、單一公共 API 塞車時，你的投資儀表板依然穩定更新。\n", "quote")
                else:
                    guide_text.insert(tk.END, "⚠️ Feature 10: Market Data Network Diagnostics & Multi-Source Failover\n", "h1")
                    guide_text.insert(tk.END, "Purpose: Real-time health monitoring of upstream financial data feeds with automated multi-tier fallback architecture.\n\n")
                    guide_text.insert(tk.END, "Operational Steps:\n", "h2")
                    guide_text.insert(tk.END, "1. Click '⚠️ Network Diagnostics' on the top bar.\n", "bullet")
                    guide_text.insert(tk.END, "2. Inspect upstream latency, HTTP response codes, and rate-limiting status across Yahoo Finance and Stooq fallback.\n", "bullet")
                    guide_text.insert(tk.END, "3. On 404 or 429 rate limits, the fallback engine automatically retries with alternative exchange suffixes and secondary providers.\n\n", "bullet")
                    guide_text.insert(tk.END, "Pro Tip: The built-in memory cache minimizes redundant web requests, keeping the UI snappy and resilient.\n", "quote")

            guide_text.config(state=tk.DISABLED)

        def _on_topic_select(event):
            selection = topic_listbox.curselection()
            if selection:
                idx = selection[0]
                display_topic(topics[idx][0])

        topic_listbox.bind("<<ListboxSelect>>", _on_topic_select)
        topic_listbox.selection_set(0)
        display_topic("overview")

        # Bottom Close Button
        btn_box = tk.Frame(main_box)
        btn_box.pack(fill=tk.X, pady=(8, 0))

        btn_close = tk.Button(
            btn_box,
            text=t("btn_close") if "btn_close" in TRANSLATIONS.get(get_current_language(), {}) else "Close",
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="solid",
            bd=1,
            padx=14,
            pady=4,
            command=dlg.destroy,
        )
        btn_close.pack(side=tk.RIGHT)

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 820, 660
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _open_what_if_dialog(self, initial_symbol: str = "", initial_amount: float = 0.0):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_what_if_title"))
        dlg.geometry("540x520")
        dlg.resizable(False, False)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text=t("dlg_what_if_title"), font=("Segoe UI", 12, "bold"), fg=self.primary_color).pack(anchor="w", pady=(0, 8))

        # Quick picks row
        qp_row = ttk.Frame(frame)
        qp_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(qp_row, text=t("lbl_quick_picks"), font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        qp_cb = ttk.Combobox(qp_row, values=[p[0] for p in POPULAR_TICKERS], state="readonly", width=36)
        qp_cb.current(0)
        qp_cb.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Symbol & Verify
        sym_box = ttk.Frame(frame)
        sym_box.pack(fill=tk.X, pady=(2, 6))
        tk.Label(sym_box, text=t("lbl_what_if_simulate"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
        sym_row = ttk.Frame(sym_box)
        sym_row.pack(fill=tk.X, pady=(2, 0))
        sym_entry = tk.Entry(sym_row, font=("Segoe UI", 10, "bold"), bd=1, relief="solid")
        if initial_symbol:
            sym_entry.insert(0, initial_symbol)
        sym_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        lbl_verified = tk.Label(frame, text="", font=("Segoe UI", 8))
        cached_info = {"price": 0.0, "yield": 0.0, "currency": "USD", "name": ""}

        def on_lookup():
            s = sym_entry.get().strip().upper()
            if not s:
                return
            lbl_verified.config(text=t("lbl_what_if_searching"), fg=self.primary_color)
            dlg.update()
            res = self.fetcher.search_or_verify_symbol(s)
            if res.get("valid"):
                p = res.get("price", 0.0)
                y = res.get("dividend_yield", 0.0)
                c = res.get("currency", "USD")
                n = res.get("name", s)
                cached_info.update({"price": p, "yield": y, "currency": c, "name": n})
                lbl_verified.config(text=t("lbl_verified_stock_info", name=n, price=f"{p:.2f}", yield_val=f"{y:.2f}", curr=c), fg=self.green_color)
            else:
                lbl_verified.config(text=f"⚠️ {res.get('error', 'Not found')}", fg=self.red_color)

        btn_lookup = tk.Button(sym_row, text=t("btn_lookup"), command=on_lookup, padx=6)
        btn_lookup.pack(side=tk.RIGHT)
        lbl_verified.pack(anchor="w", pady=(0, 6))

        def on_qp_selected(e=None):
            idx = qp_cb.current()
            if idx > 0:
                _, s, _ = POPULAR_TICKERS[idx]
                sym_entry.delete(0, tk.END)
                sym_entry.insert(0, s)
                on_lookup()

        qp_cb.bind("<<ComboboxSelected>>", on_qp_selected)

        # Investment Amount
        tk.Label(frame, text=t("lbl_what_if_invest"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
        invest_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        if initial_amount > 0:
            invest_entry.insert(0, f"{initial_amount:.2f}")
        else:
            invest_entry.insert(0, "5000.0")
        invest_entry.pack(fill=tk.X, pady=(2, 10))

        if initial_symbol:
            dlg.after(100, on_lookup)

        # Results Box
        res_box = tk.LabelFrame(frame, text=f" {t('lbl_what_if_impact')} ", font=("Segoe UI", 9, "bold"), padx=10, pady=10)
        res_box.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        lbl_res_total = tk.Label(res_box, text=f"{t('lbl_what_if_cur_tot')} $0.00 → $0.00", font=("Segoe UI", 9, "bold"), fg=self.text_dark)
        lbl_res_total.pack(anchor="w", pady=2)

        lbl_res_shares = tk.Label(res_box, text=f"{t('lbl_what_if_new_shares')} 0.0", font=("Segoe UI", 9), fg=self.text_dark)
        lbl_res_shares.pack(anchor="w", pady=2)

        lbl_res_alloc = tk.Label(res_box, text=f"{t('lbl_what_if_alloc_change')} 0.0% → 0.0%", font=("Segoe UI", 9, "bold"), fg=self.primary_color)
        lbl_res_alloc.pack(anchor="w", pady=2)

        lbl_res_div = tk.Label(res_box, text=f"{t('lbl_what_if_proj_div')} $0.00 → $0.00", font=("Segoe UI", 9, "bold"), fg=self.green_color)
        lbl_res_div.pack(anchor="w", pady=2)

        def simulate():
            s = sym_entry.get().strip().upper()
            if not s:
                return
            if cached_info["price"] <= 0:
                on_lookup()
            p = cached_info["price"]
            if p <= 0:
                p = 100.0
            try:
                amt = float(invest_entry.get().strip() or "0.0")
            except ValueError:
                amt = 0.0

            target_curr = self.summary_currency
            cur_tot_val = 0.0
            cur_ann_div = 0.0
            cur_pos_val = 0.0

            for h in self.holdings:
                c = (h.get("currency") or "USD").strip().upper()
                mv = float(h.get("shares", 0.0)) * float(h.get("current_price", h.get("price", 0.0)))
                ad = float(h.get("annual_dividend", 0.0))
                cur_tot_val += self.converter.convert(mv, c, target_curr)
                cur_ann_div += self.converter.convert(ad, c, target_curr)
                if str(h.get("symbol", "")).strip().upper() == s:
                    cur_pos_val += self.converter.convert(mv, c, target_curr)

            h_curr = cached_info["currency"]
            amt_in_target = self.converter.convert(amt, h_curr, target_curr)
            new_tot_val = cur_tot_val + amt_in_target
            new_pos_val = cur_pos_val + amt_in_target

            cur_weight = (cur_pos_val / cur_tot_val * 100.0) if cur_tot_val > 0 else 0.0
            new_weight = (new_pos_val / new_tot_val * 100.0) if new_tot_val > 0 else 0.0

            shares_acquired = (amt / p) if p > 0 else 0.0
            div_gain = amt * (cached_info["yield"] / 100.0)
            div_gain_in_target = self.converter.convert(div_gain, h_curr, target_curr)
            new_ann_div = cur_ann_div + div_gain_in_target

            lbl_res_total.config(text=f"{t('lbl_what_if_cur_tot')} {self.converter.format_money(cur_tot_val, target_curr)} → {self.converter.format_money(new_tot_val, target_curr)} (+{self.converter.format_money(amt_in_target, target_curr)})")
            lbl_res_shares.config(text=f"{t('lbl_what_if_new_shares')} {shares_acquired:.4g} shs @ ${p:.2f}")
            lbl_res_alloc.config(text=f"{s} {t('lbl_what_if_alloc_change')} {cur_weight:.1f}% → {new_weight:.1f}%")
            lbl_res_div.config(text=f"{t('lbl_what_if_proj_div')} {self.converter.format_money(cur_ann_div, target_curr)} → {self.converter.format_money(new_ann_div, target_curr)} (+{self.converter.format_money(div_gain_in_target, target_curr)}/yr)")

        btn_run = tk.Button(
            frame,
            text=t("btn_run_simulation"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            command=simulate,
            padx=12,
            pady=4,
        )
        btn_run.pack(side=tk.RIGHT)

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 540, 520
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def _open_data_health_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(t("dlg_data_health_title"))
        dlg.geometry("560x440")
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text=t("dlg_data_health_title"), font=("Segoe UI", 12, "bold"), fg=self.primary_color).pack(anchor="w", pady=(0, 6))

        status_box = tk.Text(frame, font=("Consolas", 9), height=14, bd=1, relief="solid", wrap=tk.WORD)
        status_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        def refresh_scan():
            status_box.delete("1.0", tk.END)
            res = scan_data_integrity(PORTFOLIO_CSV, WATCHLIST_CSV)
            issues = res.get("issues", []) if isinstance(res, dict) else res
            if not issues:
                status_box.insert(tk.END, t("msg_data_healthy") + "\n\n")
                status_box.insert(tk.END, t("lbl_health_clean") + "\n")
            else:
                status_box.insert(tk.END, t("lbl_health_issues_found", count=len(issues)))
                for i, iss in enumerate(issues, 1):
                    status_box.insert(tk.END, f"{i}. [{iss.get('type', 'ISSUE')}] {iss.get('desc', '')}\n")

        refresh_scan()

        btn_box = ttk.Frame(frame)
        btn_box.pack(fill=tk.X)

        def do_repair():
            res = repair_data_integrity(PORTFOLIO_CSV, WATCHLIST_CSV)
            self.all_holdings = load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
            self.holdings = list(self.all_holdings)
            self._refresh_holdings_table()
            self._refresh_watchlist_tab()
            self._update_metric_cards()
            refresh_scan()
            repaired_count = len(res.get("repaired", []))
            messagebox.showinfo(t("dlg_data_health_title"), t("msg_health_repaired", count=repaired_count), parent=dlg)

        tk.Button(
            btn_box,
            text=t("btn_repair_data"),
            font=("Segoe UI", 9, "bold"),
            bg="#188038",
            fg="#ffffff",
            command=do_repair,
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT)

        tk.Button(btn_box, text=t("btn_cancel"), command=dlg.destroy, padx=8, pady=4).pack(side=tk.RIGHT)

        dlg.update_idletasks()
        try:
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 560, 440
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        dlg.deiconify()
        dlg.lift()
        dlg.focus_set()
        try:
            dlg.grab_set()
        except Exception:
            pass

    def on_close(self):
        self.is_running = False
        try:
            if hasattr(self, "tab_fire"):
                self._refresh_fire_tab()
        except Exception:
            pass
        try:
            web_server.stop_server()
        except Exception:
            pass
        try:
            get_currency_converter().is_running = False
        except Exception:
            pass

        if hasattr(self, "chart_view"):
            try:
                self.chart_view.cleanup()
            except Exception:
                pass

        if getattr(self, "queue_job", None):
            try:
                self.root.after_cancel(self.queue_job)
            except Exception:
                pass
            self.queue_job = None

        if getattr(self, "auto_refresh_job", None):
            try:
                self.root.after_cancel(self.auto_refresh_job)
            except Exception:
                pass
            self.auto_refresh_job = None

        try:
            self.root.quit()
        except Exception:
            pass

        try:
            self.root.destroy()
        except Exception:
            pass


def launch_app():
    root = tk.Tk()
    app = ModernPortfolioApp(root)
    try:
        root.mainloop()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            app.on_close()
        except Exception:
            pass
        # Force immediate exit of Python CLI process to prevent hanging on background sockets/threads
        os._exit(0)


if __name__ == "__main__":
    launch_app()
