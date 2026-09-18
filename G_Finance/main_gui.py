"""
Google Finance Portfolio & Financial Calculator GUI
Desktop application for tracking live Google Finance quotes,
syncing with user's Google Finance account, performing dividend,
division/split, and selling calculations, and saving data in CSV.
"""

import os
import sys
import time
import threading
import queue
from datetime import datetime
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
)
from chart_canvas import draw_donut_chart, draw_drip_growth_chart, ChartTheme
from report_generator import generate_html_report
from currency_converter import get_currency_converter
from chart_view import GoogleFinanceChartView
from csv_manager import (
    PORTFOLIO_CSV,
    SALES_HISTORY_CSV,
    TRANSACTION_HISTORY_CSV,
    BACKUP_DIR,
    DEFAULT_PORTFOLIO_NAME,
    save_portfolio,
    load_portfolio,
    get_portfolio_names,
    delete_portfolio,
    rename_portfolio,
    save_sales_history,
    load_sales_history,
    append_sale_record,
    save_transactions,
    load_transactions,
    append_transaction,
    ensure_workspace_files,
    get_backup_files,
    restore_backup,
)
from tkinter import simpledialog
from i18n import (
    t,
    get_current_language,
    set_language,
    get_available_languages,
)


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
        self.refresh_interval_sec: int = 30
        self.auto_refresh_enabled: bool = True

        # Theme, Search & Filter state
        self.dark_mode: bool = False
        self.search_filter_var = tk.StringVar()
        self.filter_performance: str = "All"
        self.sort_col: Optional[str] = None
        self.sort_reverse: bool = False

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Configure style
        self._setup_style()

        # Build UI layout
        self._build_top_bar()
        self._build_portfolio_bar()
        self._build_metric_cards()
        self._build_tabs()
        self._build_status_bar()

        # Context Menu
        self._build_context_menu()

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

        # Start initial auto-refresh
        if self.holdings:
            self.root.after(1000, self.fetch_all_quotes)
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
                text="☀️ Light" if self.dark_mode else "🌙 Dark",
                bg="#3c4043" if self.dark_mode else "#ffffff",
                fg="#fbbc04" if self.dark_mode else "#202124",
            )
        if hasattr(self, "lbl_title"):
            self.lbl_title.config(bg=self.bg_main, fg=self.primary_color)
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
        for tree in [getattr(self, "holdings_tree", None), getattr(self, "history_tree", None), getattr(self, "alloc_tree", None), getattr(self, "drip_tree", None)]:
            if tree:
                tree.tag_configure("positive", foreground=self.green_color)
                tree.tag_configure("negative", foreground=self.red_color)
                tree.tag_configure("neutral", foreground=self.tree_fg)
        self._update_filter_button_styles()
        self._refresh_holdings_table()
        self._refresh_analytics_tab()
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

        # Title
        title_box = ttk.Frame(top_frame)
        title_box.pack(side=tk.LEFT)
        self.lbl_title = tk.Label(
            title_box,
            text=t("app_header"),
            font=("Segoe UI", 14, "bold"),
            bg=self.bg_main,
            fg=self.primary_color,
        )
        self.lbl_title.pack(anchor="w")

        # Action and control buttons on right
        ctrl_box = ttk.Frame(top_frame)
        ctrl_box.pack(side=tk.RIGHT)

        # Google Account Sync button
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
            command=self._open_sync_dialog,
        )
        self.btn_sync.pack(side=tk.LEFT, padx=(0, 8))

        # Add Stock button
        self.btn_add = tk.Button(
            ctrl_box,
            text=t("btn_add_stock"),
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            activebackground="#1557b0",
            relief="flat",
            padx=8,
            pady=3,
            command=self._open_add_dialog,
        )
        self.btn_add.pack(side=tk.LEFT, padx=(0, 4))

        # Remove Stock button
        self.btn_remove = tk.Button(
            ctrl_box,
            text=t("btn_tbl_remove"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg=self.red_color,
            activebackground="#fce8e6",
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            command=self._delete_selected_holding,
        )
        self.btn_remove.pack(side=tk.LEFT, padx=(0, 8))

        # Export Executive HTML Report
        self.btn_report = tk.Button(
            ctrl_box,
            text=t("btn_report"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg=self.primary_color,
            activebackground="#e8f0fe",
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            command=self._export_html_report_dialog,
        )
        self.btn_report.pack(side=tk.LEFT, padx=(0, 6))

        # Theme toggle button
        self.btn_theme_toggle = tk.Button(
            ctrl_box,
            text=t("btn_theme_light") if self.dark_mode else t("btn_theme_dark"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#202124",
            relief="solid",
            bd=1,
            padx=6,
            pady=3,
            command=self._toggle_theme,
        )
        self.btn_theme_toggle.pack(side=tk.LEFT, padx=(0, 6))

        # Language Selector combobox
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
        self.lang_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_language_changed)

        # Auto-Refresh controls
        self.lbl_auto = tk.Label(ctrl_box, text="Auto:", font=("Segoe UI", 9, "bold"), bg=self.bg_main)
        self.lbl_auto.pack(side=tk.LEFT, padx=(0, 4))

        self.interval_var = tk.StringVar(value="30s")
        interval_menu = ttk.Combobox(
            ctrl_box,
            textvariable=self.interval_var,
            values=["Off", "15s", "30s", "1 min", "2 min", "5 min"],
            width=6,
            state="readonly",
        )
        interval_menu.pack(side=tk.LEFT, padx=(0, 6))
        interval_menu.bind("<<ComboboxSelected>>", self._on_interval_changed)

        self.btn_refresh = tk.Button(
            ctrl_box,
            text=t("btn_refresh"),
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg=self.primary_color,
            activebackground="#e8f0fe",
            relief="solid",
            bd=1,
            padx=6,
            pady=3,
            command=self.fetch_all_quotes,
        )
        self.btn_refresh.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_import = tk.Button(
            ctrl_box,
            text=t("btn_import_csv"),
            font=("Segoe UI", 8),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=4,
            pady=3,
            command=self._import_csv_dialog,
        )
        self.btn_import.pack(side=tk.LEFT, padx=(0, 2))

        self.btn_export = tk.Button(
            ctrl_box,
            text=t("btn_export_csv"),
            font=("Segoe UI", 8),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=4,
            pady=3,
            command=self._export_csv_dialog,
        )
        self.btn_export.pack(side=tk.LEFT, padx=(0, 2))

        self.btn_backups = tk.Button(
            ctrl_box,
            text=t("btn_backups"),
            font=("Segoe UI", 8),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=4,
            pady=3,
            command=self._open_backups_dialog,
        )
        self.btn_backups.pack(side=tk.LEFT)

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
        if hasattr(self, "btn_sync"):
            self.btn_sync.config(text=t("btn_google_sync"))
        if hasattr(self, "btn_add"):
            self.btn_add.config(text=t("btn_add_stock"))
        if hasattr(self, "btn_remove"):
            self.btn_remove.config(text=t("btn_tbl_remove"))
        if hasattr(self, "btn_report"):
            self.btn_report.config(text=t("btn_report"))
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
        if hasattr(self, "lbl_summary_in"):
            self.lbl_summary_in.config(text=t("lbl_summary_in"))

        # 4. Update Notebook tab titles
        if hasattr(self, "notebook"):
            tab_map = [
                (getattr(self, "tab_holdings", None), t("tab_holdings")),
                (getattr(self, "tab_analytics", None), t("tab_analytics")),
                (getattr(self, "tab_chart", None), t("tab_chart")),
                (getattr(self, "tab_dividend", None), t("tab_dividend")),
                (getattr(self, "tab_split", None), t("tab_split")),
                (getattr(self, "tab_sell", None), t("tab_selling")),
                (getattr(self, "tab_history", None), t("tab_transactions")),
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
            }
            for k, lbl in kpi_labels.items():
                if k in self.analytics_kpis:
                    try:
                        self.analytics_kpis[k][1].config(text=lbl)
                    except Exception:
                        pass
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

        # 8. Update Dividend & DRIP Tab
        if hasattr(self, "div_earned_box"):
            self.div_earned_box.config(text=f" {t('div_sec_earned_already')} ")
        if hasattr(self, "div_future_box"):
            self.div_future_box.config(text=f" {t('div_sec_future_earnings')} ")
        if hasattr(self, "div_income_box"):
            self.div_income_box.config(text=f" {t('div_sec_projections')} ")

        # 9. Update Split Tab
        if hasattr(self, "split_earned_box"):
            self.split_earned_box.config(text=f" {t('split_sec_earned_already')} ")
        if hasattr(self, "split_comp_box"):
            self.split_comp_box.config(text=f" {t('split_sec_comparison')} ")
        if hasattr(self, "split_future_box"):
            self.split_future_box.config(text=f" {t('split_sec_future')} ")
        if hasattr(self, "btn_apply_split"):
            self.btn_apply_split.config(text="✅ " + t("btn_apply_split"))
        if hasattr(self, "btn_split_recov"):
            self.btn_split_recov.config(text="🎯 " + t("lbl_split_presplit_recovery"))

        # 10. Refresh views
        self._update_filter_button_styles()
        self._update_metric_cards()
        self._refresh_holdings_table()
        self._refresh_sales_table()
        self._refresh_analytics_tab()
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
        self.btn_delete_portfolio.pack(side=tk.LEFT, padx=(0, 16))

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

    def _get_portfolio_dropdown_values(self) -> List[str]:
        all_p = get_portfolio_names(PORTFOLIO_CSV)
        common = ["USD HSBC", "CAD TSFA", "CAD RRSP", "USD RRSP", "USD TSFA"]
        for c in common:
            if c not in all_p and any(h.get("portfolio") == c for h in self.all_holdings):
                all_p.append(c)
        res = list(all_p)
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
        self._set_status(f"Switched to {sel} ({len(self.holdings)} holdings, {len(self.sales_history)} sales).")

    def _create_new_portfolio(self):
        name = simpledialog.askstring("New Portfolio", "Enter name for new portfolio (e.g. CAD TSFA, CAD RRSP):", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        vals = self._get_portfolio_dropdown_values()
        if name in vals:
            messagebox.showinfo("Exists", f"Portfolio '{name}' already exists.", parent=self.root)
            self.portfolio_var.set(name)
            self._on_portfolio_selected()
            return

        self.current_portfolio = name
        self.holdings = []
        vals.insert(max(0, len(vals) - 1), name)
        self.portfolio_combo.config(values=vals)
        self.portfolio_var.set(name)
        self._refresh_holdings_table()
        self._update_metric_cards()
        self._refresh_dropdowns()
        self._refresh_analytics_tab()
        self._set_status(f"Created new empty portfolio: {name}")

    def _rename_current_portfolio(self):
        if self.current_portfolio == "All Portfolios (Consolidated)":
            messagebox.showwarning("Notice", "Cannot rename consolidated view.", parent=self.root)
            return
        new_name = simpledialog.askstring("Rename Portfolio", f"Enter new name for '{self.current_portfolio}':", initialvalue=self.current_portfolio, parent=self.root)
        if not new_name or not new_name.strip() or new_name.strip() == self.current_portfolio:
            return
        new_name = new_name.strip()
        old_name = self.current_portfolio
        rename_portfolio(old_name, new_name, PORTFOLIO_CSV)
        self.all_holdings = load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
        self.current_portfolio = new_name
        self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
        self.portfolio_var.set(new_name)
        self._on_portfolio_selected()
        messagebox.showinfo("Success", f"Renamed portfolio to '{new_name}'.", parent=self.root)

    def _delete_current_portfolio(self):
        if self.current_portfolio == "All Portfolios (Consolidated)":
            messagebox.showwarning("Notice", "Cannot delete consolidated view.", parent=self.root)
            return
        ans = messagebox.askyesno("Delete Portfolio", f"Are you sure you want to delete portfolio '{self.current_portfolio}' and all its {len(self.holdings)} holdings?", parent=self.root)
        if not ans:
            return
        delete_portfolio(self.current_portfolio, PORTFOLIO_CSV)
        self.all_holdings = load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
        p_names = get_portfolio_names(PORTFOLIO_CSV)
        self.current_portfolio = p_names[0] if p_names else DEFAULT_PORTFOLIO_NAME
        self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
        self.portfolio_var.set(self.current_portfolio)
        self._on_portfolio_selected()

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
        metrics = [
            ("total_value", "Portfolio Value (USD)", "$0.00", self.text_dark),
            ("total_cost", "Total Cost Basis (USD)", "$0.00", self.text_muted),
            ("total_gain", "Total Unrealized P/L (USD)", "$0.00 (+0.00%)", self.green_color),
            ("annual_dividend", "Projected Annual Div (USD)", "$0.00", self.primary_color),
            ("monthly_dividend", "Monthly Div Avg (USD)", "$0.00", self.primary_color),
        ]

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

        # Tab 5: Stock Division / Split
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

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

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

        # KPI mini cards in 2x3 grid
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
        ]

        for idx, (k, label, def_val, col) in enumerate(items):
            r = idx // 2
            c = idx % 2
            cell = tk.Frame(kpi_grid, bg=self.card_bg, bd=1, relief="solid", padx=8, pady=6)
            cell.grid(row=r, column=c, sticky="nsew", padx=3, pady=3)
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

    def _draw_donut(self):
        if not hasattr(self, "donut_canvas"):
            return
        base_curr = self.summary_currency if hasattr(self, "summary_currency") else "USD"
        fx_rates = getattr(self.fetcher, "fx_cache", {})
        metrics = calc_portfolio_metrics(self.holdings, base_curr, fx_rates)
        allocs = metrics.get("allocations", [])

        labels = [a["symbol"] for a in allocs]
        values = [a["value_base"] for a in allocs]
        tot = metrics.get("total_value", 0.0)
        sym_char = self.converter.CURRENCY_SYMBOLS.get(base_curr, "$")
        center_str = f"{sym_char}{tot:,.2f}"
        port_name_display = t("portfolio_all_consolidated") if self.current_portfolio in ("All Portfolios (Consolidated)", "All Portfolios", "All") else self.current_portfolio
        port_title = f"{t('alloc_chart_title')} ({base_curr}) - {port_name_display}"
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

        for item in self.alloc_tree.get_children():
            self.alloc_tree.delete(item)

        sym_char = self.converter.CURRENCY_SYMBOLS.get(base_curr, "$")
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
        self.status_frame = tk.Frame(self.root, bg="#e8eaed", height=24)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_status = tk.Label(
            self.status_frame,
            text="Ready. Holdings auto-saved to portfolio.csv",
            font=("Segoe UI", 8),
            bg="#e8eaed",
            fg=self.text_muted,
            anchor="w",
            padx=8,
        )
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_time = tk.Label(
            self.status_frame,
            text="",
            font=("Segoe UI", 8),
            bg="#e8eaed",
            fg=self.text_muted,
            padx=8,
        )
        self.lbl_time.pack(side=tk.RIGHT)

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

        self.lbl_search = tk.Label(sf_bar, text="🔍 Search:", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark)
        self.lbl_search.pack(side=tk.LEFT, padx=(0, 4))
        self.search_entry = tk.Entry(sf_bar, textvariable=self.search_filter_var, font=("Segoe UI", 9), width=22, bd=1, relief="solid")
        self.search_entry.pack(side=tk.LEFT, padx=(0, 4))
        self.search_entry.bind("<KeyRelease>", lambda e: self._refresh_holdings_table())

        btn_clear = tk.Button(sf_bar, text="✕", font=("Segoe UI", 8), bg="#ffffff", relief="solid", bd=1, padx=4, pady=1, command=self._clear_search)
        btn_clear.pack(side=tk.LEFT, padx=(0, 12))

        self.lbl_filter = tk.Label(sf_bar, text="Filter:", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark)
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
            ("div_yield", t("col_dividend_yield"), 75),
            ("annual_div", t("col_annual_div"), 90),
            ("updated", t("col_last_updated"), 130),
        ]

        for col, heading, width in headers:
            self.holdings_tree.heading(col, text=heading, command=lambda c=col: self._sort_holdings_by(c))
            self.holdings_tree.column(col, width=width, anchor="center" if col in ("symbol", "shares") else "e")
        self.holdings_tree.column("name", anchor="w")

        v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.holdings_tree.yview)
        h_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.holdings_tree.xview)
        self.holdings_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.holdings_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.holdings_tree.tag_configure("positive", foreground=self.green_color)
        self.holdings_tree.tag_configure("negative", foreground=self.red_color)
        self.holdings_tree.tag_configure("neutral", foreground=self.text_dark)

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

        left_frame = tk.LabelFrame(container, text=" Dividend Parameters ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=10)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        tk.Label(left_frame, text="Select from Portfolio:", font=("Segoe UI", 9, "bold"), bg="#ffffff").pack(anchor="w", pady=(0, 2))
        self.div_holding_var = tk.StringVar()
        self.div_holding_cb = ttk.Combobox(left_frame, textvariable=self.div_holding_var, state="readonly", width=22)
        self.div_holding_cb.pack(fill=tk.X, pady=(0, 6))
        self.div_holding_cb.bind("<<ComboboxSelected>>", self._on_div_holding_selected)

        self.div_inputs = {}
        fields = [
            ("ticker", "Ticker / Symbol:", "AAPL"),
            ("shares", "Number of Shares:", "50"),
            ("current_price", "Current Share Price ($):", "220.00"),
            ("buy_price", "Buy Price / Cost Basis ($):", "180.00"),
            ("purchase_date", "Purchase Date (YYYY-MM-DD):", ""),
            ("div_yield", "Dividend Yield (%):", "2.5"),
            ("div_per_share", "Annual Div/Share ($):", ""),
        ]

        from datetime import date, timedelta
        def_date = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")

        for key, lbl, default in fields:
            tk.Label(left_frame, text=lbl, font=("Segoe UI", 8, "bold" if "Price" in lbl or "Shares" in lbl or "Date" in lbl else "normal"), bg="#ffffff").pack(anchor="w", pady=(2, 0))
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
                self.div_holding_days_lbl = tk.Label(left_frame, text="Holding: 365 days (1.00 yrs)", font=("Segoe UI", 8, "italic"), bg="#ffffff", fg=self.text_muted)
                self.div_holding_days_lbl.pack(anchor="w", pady=(0, 2))

        btn_calc_div = tk.Button(
            left_frame,
            text="Calculate Dividends & Returns",
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=4,
            command=self._calc_dividend_results,
        )
        btn_calc_div.pack(fill=tk.X, pady=(6, 8))

        tk.Label(left_frame, text="DRIP Simulation Settings", font=("Segoe UI", 9, "bold"), bg="#ffffff").pack(anchor="w", pady=(4, 2))
        
        tk.Label(left_frame, text="Years to Simulate:", font=("Segoe UI", 8), bg="#ffffff").pack(anchor="w")
        self.drip_years_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_years_entry.insert(0, "10")
        self.drip_years_entry.pack(fill=tk.X, pady=(0, 2))

        tk.Label(left_frame, text="Annual Dividend Growth (%):", font=("Segoe UI", 8), bg="#ffffff").pack(anchor="w")
        self.drip_div_growth_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_div_growth_entry.insert(0, "5.0")
        self.drip_div_growth_entry.pack(fill=tk.X, pady=(0, 2))

        tk.Label(left_frame, text="Annual Stock Price Growth (%):", font=("Segoe UI", 8), bg="#ffffff").pack(anchor="w")
        self.drip_price_growth_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_price_growth_entry.insert(0, "6.0")
        self.drip_price_growth_entry.pack(fill=tk.X, pady=(0, 2))

        tk.Label(left_frame, text="Monthly Contribution ($):", font=("Segoe UI", 8), bg="#ffffff").pack(anchor="w")
        self.drip_monthly_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_monthly_entry.insert(0, "0.0")
        self.drip_monthly_entry.pack(fill=tk.X, pady=(0, 6))

        tk.Button(
            left_frame,
            text="Run DRIP Simulation",
            font=("Segoe UI", 9, "bold"),
            bg="#34a853",
            fg="#ffffff",
            relief="flat",
            pady=4,
            command=self._calc_drip_results,
        ).pack(fill=tk.X)

        right_frame = ttk.Frame(container)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 1. Earned Already Box (From Purchase Day Till Today)
        self.div_earned_box = tk.LabelFrame(right_frame, text=f" {t('div_sec_earned_already')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=6)
        self.div_earned_box.pack(fill=tk.X, pady=(0, 6))

        self.div_earned_labels = {}
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
            tk.Label(self.div_earned_box, text=label, font=("Segoe UI", 8, "bold"), bg="#ffffff", fg=self.text_muted).grid(row=r * 2, column=c, sticky="w", padx=6)
            val_lbl = tk.Label(self.div_earned_box, text=default, font=("Segoe UI", 10, "bold"), bg="#ffffff", fg=self.primary_color)
            val_lbl.grid(row=r * 2 + 1, column=c, sticky="w", padx=6, pady=(0, 2))
            self.div_earned_labels[k] = val_lbl

        # 2. Future Growth & Compounding Milestones Box (Till Later How Much You Can Earn)
        self.div_future_box = tk.LabelFrame(right_frame, text=f" {t('div_sec_future_earnings')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=6)
        self.div_future_box.pack(fill=tk.X, pady=(0, 6))

        self.div_milestone_labels = {}
        milestone_defs = [
            (1, t("lbl_milestone_1yr")),
            (3, t("lbl_milestone_3yr")),
            (5, t("lbl_milestone_5yr")),
            (10, t("lbl_milestone_10yr")),
        ]
        for idx, (yr, title) in enumerate(milestone_defs):
            cell = tk.Frame(self.div_future_box, bg="#f8f9fa", bd=1, relief="solid", padx=6, pady=4)
            cell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            tk.Label(cell, text=title, font=("Segoe UI", 8, "bold"), bg="#f8f9fa", fg=self.primary_color).pack(anchor="w")
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
        disp_fields = [
            ("annual_total", t("div_proj_annual") + " ($):", "$0.00"),
            ("quarterly_total", t("div_proj_quarterly") + " ($):", "$0.00"),
            ("monthly_total", t("div_proj_monthly") + " ($):", "$0.00"),
            ("yield_on_cost", t("div_proj_yoc") + ":", "0.00%"),
            ("div_per_share", "Div / Share:", "$0.00"),
        ]
        for i, (k, label, default) in enumerate(disp_fields):
            tk.Label(self.div_income_box, text=label, font=("Segoe UI", 8), bg="#ffffff", fg=self.text_muted).grid(row=0, column=i, sticky="w", padx=6)
            val_lbl = tk.Label(self.div_income_box, text=default, font=("Segoe UI", 10, "bold"), bg="#ffffff", fg=self.primary_color)
            val_lbl.grid(row=1, column=i, sticky="w", padx=6, pady=(0, 2))
            self.div_results[k] = val_lbl

        # 4. DRIP Box (Table + Chart)
        drip_box = tk.LabelFrame(right_frame, text=f" {t('div_sec_drip')} ", font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.primary_color, padx=8, pady=4)
        drip_box.pack(fill=tk.BOTH, expand=True)

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

    def _set_div_purchase_date_days_ago(self, days: int):
        from datetime import date, timedelta
        target_d = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        if "purchase_date" in getattr(self, "div_inputs", {}):
            self.div_inputs["purchase_date"].delete(0, tk.END)
            self.div_inputs["purchase_date"].insert(0, target_d)
            self._calc_dividend_results()

    # -------------------------------------------------------------
    # Tab 3: Stock Division (Split) Calculator
    # -------------------------------------------------------------
    def _build_split_tab(self):
        tab = self.tab_split
        container = ttk.Frame(tab, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        left_card = tk.LabelFrame(container, text=" Stock Split / Division Parameters ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=10)
        left_card.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))

        tk.Label(left_card, text=t("lbl_split_holding"), font=("Segoe UI", 9, "bold"), bg="#ffffff").pack(anchor="w", pady=(0, 2))
        self.split_holding_var = tk.StringVar()
        self.split_holding_cb = ttk.Combobox(left_card, textvariable=self.split_holding_var, state="readonly", width=22)
        self.split_holding_cb.pack(fill=tk.X, pady=(0, 6))
        self.split_holding_cb.bind("<<ComboboxSelected>>", self._on_split_holding_selected)

        tk.Label(left_card, text=t("col_symbol") + ":", font=("Segoe UI", 8, "bold"), bg="#ffffff").pack(anchor="w")
        self.split_sym_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_sym_entry.pack(fill=tk.X, pady=(0, 4))

        tk.Label(left_card, text=t("col_shares") + ":", font=("Segoe UI", 8, "bold"), bg="#ffffff").pack(anchor="w")
        self.split_shares_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_shares_entry.pack(fill=tk.X, pady=(0, 4))

        tk.Label(left_card, text=t("lbl_split_before_price"), font=("Segoe UI", 8, "bold"), bg="#ffffff").pack(anchor="w")
        self.split_price_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_price_entry.pack(fill=tk.X, pady=(0, 4))

        tk.Label(left_card, text=t("lbl_split_current_price"), font=("Segoe UI", 8, "bold"), bg="#ffffff").pack(anchor="w")
        self.split_cur_price_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_cur_price_entry.pack(fill=tk.X, pady=(0, 4))

        tk.Label(left_card, text=t("lbl_purchase_date"), font=("Segoe UI", 8), bg="#ffffff").pack(anchor="w")
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
        self.split_holding_days_lbl = tk.Label(left_card, text="Holding: 365 days (1.00 yrs)", font=("Segoe UI", 8, "italic"), bg="#ffffff", fg=self.text_muted)
        self.split_holding_days_lbl.pack(anchor="w", pady=(0, 4))

        tk.Label(left_card, text=t("lbl_split_target_price"), font=("Segoe UI", 8, "bold"), bg="#ffffff").pack(anchor="w")
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

        tk.Label(left_card, text=t("lbl_split_ratio"), font=("Segoe UI", 8, "bold"), bg="#ffffff").pack(anchor="w")
        self.split_preset_var = tk.StringVar(value="2:1")
        presets = ["2:1 Split", "3:1 Split", "4:1 Split", "5:1 Split", "10:1 Split", "1:5 Reverse Split", "1:10 Reverse Split", "Custom"]
        preset_cb = ttk.Combobox(left_card, textvariable=self.split_preset_var, values=presets, state="readonly")
        preset_cb.pack(fill=tk.X, pady=(0, 4))
        preset_cb.bind("<<ComboboxSelected>>", self._on_split_preset_selected)

        ratio_frame = ttk.Frame(left_card)
        ratio_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(ratio_frame, text="Ratio To:", font=("Segoe UI", 8), bg=self.bg_main).pack(side=tk.LEFT)
        self.split_to_entry = tk.Entry(ratio_frame, width=5, bd=1, relief="solid")
        self.split_to_entry.insert(0, "2")
        self.split_to_entry.pack(side=tk.LEFT, padx=3)

        tk.Label(ratio_frame, text="for Every:", font=("Segoe UI", 8), bg=self.bg_main).pack(side=tk.LEFT, padx=3)
        self.split_from_entry = tk.Entry(ratio_frame, width=5, bd=1, relief="solid")
        self.split_from_entry.insert(0, "1")
        self.split_from_entry.pack(side=tk.LEFT, padx=3)

        tk.Button(
            left_card,
            text="Calculate Split & Returns",
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=4,
            command=self._calc_split_results,
        ).pack(fill=tk.X, pady=(0, 6))

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
        split_earned_fields = [
            ("cost_basis", t("lbl_cost_basis_invested")),
            ("market_value", t("card_total_value")),
            ("capital_gain", t("lbl_capital_gain_so_far")),
            ("holding_period", t("lbl_holding_period")),
        ]
        for i, (k, lbl) in enumerate(split_earned_fields):
            r = i // 2
            c = (i % 2) * 2
            tk.Label(self.split_earned_box, text=lbl, font=("Segoe UI", 8, "bold"), bg="#ffffff", fg=self.text_muted).grid(row=r * 2, column=c, sticky="w", padx=8)
            v = tk.Label(self.split_earned_box, text="-", font=("Segoe UI", 10, "bold"), bg="#ffffff", fg=self.text_dark)
            v.grid(row=r * 2 + 1, column=c, sticky="w", padx=8, pady=(0, 4))
            self.split_earned_labels[k] = v

        # 2. Before / After Split Comparison Card
        self.split_comp_box = tk.LabelFrame(right_card, text=f" {t('split_sec_comparison')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=8)
        self.split_comp_box.pack(fill=tk.X, pady=(0, 8))

        comp_frame = ttk.Frame(self.split_comp_box)
        comp_frame.pack(fill=tk.X)

        before_box = tk.LabelFrame(comp_frame, text=" ⏪ Before Split ", font=("Segoe UI", 9, "bold"), bg="#f8f9fa", padx=10, pady=8)
        before_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        self.split_before_labels = {}
        for k, lbl in [("shares", "Shares:"), ("price", "Cost Basis / Share:"), ("cur_price", "Current Share Price:"), ("total", "Total Cost Basis:"), ("val", "Market Value:")]:
            tk.Label(before_box, text=lbl, font=("Segoe UI", 8, "bold"), bg="#f8f9fa", fg=self.text_muted).pack(anchor="w")
            v = tk.Label(before_box, text="-", font=("Segoe UI", 10, "bold"), bg="#f8f9fa", fg=self.text_dark)
            v.pack(anchor="w", pady=(0, 2))
            self.split_before_labels[k] = v

        after_box = tk.LabelFrame(comp_frame, text=" ⏩ After Split ", font=("Segoe UI", 9, "bold"), bg="#e8f0fe", padx=10, pady=8)
        after_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.split_after_labels = {}
        for k, lbl in [("shares", "New Shares:"), ("price", "New Cost Basis / Share:"), ("cur_price", "New Effective Price:"), ("total", "Total Cost Basis:"), ("val", "Market Value:")]:
            tk.Label(after_box, text=lbl, font=("Segoe UI", 8, "bold"), bg="#e8f0fe", fg=self.text_muted).pack(anchor="w")
            v = tk.Label(after_box, text="-", font=("Segoe UI", 10, "bold"), bg="#e8f0fe", fg=self.primary_color)
            v.pack(anchor="w", pady=(0, 2))
            self.split_after_labels[k] = v

        # 3. Future Potential Earnings Card ("Till later how much you can earn")
        self.split_future_box = tk.LabelFrame(right_card, text=f" {t('split_sec_future')} ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=12, pady=8)
        self.split_future_box.pack(fill=tk.BOTH, expand=True)

        self.split_future_labels = {}
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
            tk.Label(cell, text=lbl, font=("Segoe UI", 8, "bold"), bg="#f8f9fa", fg=self.text_muted).pack(anchor="w")
            v = tk.Label(cell, text="-", font=("Segoe UI", 11, "bold"), bg="#f8f9fa", fg=self.primary_color)
            v.pack(anchor="w")
            self.split_future_labels[k] = v

        tk.Label(self.split_future_box, text="Future Growth Milestone Scenarios:", font=("Segoe UI", 8, "bold"), bg="#ffffff", fg=self.text_muted).pack(anchor="w", pady=(4, 2))
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

        left_box = tk.LabelFrame(container, text=" Sell Order Simulator ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=12, pady=12)
        left_box.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        tk.Label(left_box, text="Select from Portfolio:", font=("Segoe UI", 9, "bold"), bg="#ffffff").pack(anchor="w", pady=(0, 2))
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
        fields = [
            ("symbol", "Symbol:", "AAPL"),
            ("shares_to_sell", "Shares to Sell:", "25"),
            ("buy_price", "Buy Price / Share ($):", "150.00"),
            ("sell_price", "Target Sell Price / Share ($):", "220.00"),
            ("commission_flat", "Flat Commission / Fee ($):", "0.00"),
            ("commission_pct", "Commission Rate (%):", "0.00"),
        ]

        for k, lbl, default in fields:
            tk.Label(left_box, text=lbl, font=("Segoe UI", 8), bg="#ffffff").pack(anchor="w")
            entry = tk.Entry(left_box, font=("Segoe UI", 9), bd=1, relief="solid")
            entry.insert(0, default)
            entry.pack(fill=tk.X, pady=(0, 4))
            self.sell_inputs[k] = entry

        tk.Label(left_box, text="Capital Gains Tax Bracket:", font=("Segoe UI", 8, "bold"), bg="#ffffff").pack(anchor="w", pady=(4, 0))
        self.tax_bracket_var = tk.StringVar(value="15% Long-Term")
        tax_cb = ttk.Combobox(
            left_box,
            textvariable=self.tax_bracket_var,
            values=["0% (Tax-Exempt / IRA)", "15% Long-Term", "20% Long-Term (High)", "28% Short-Term", "Custom %"],
            state="readonly",
        )
        tax_cb.pack(fill=tk.X, pady=(0, 4))
        tax_cb.bind("<<ComboboxSelected>>", self._on_tax_preset_changed)

        tk.Label(left_box, text="Custom Tax Rate (%):", font=("Segoe UI", 8), bg="#ffffff").pack(anchor="w")
        self.sell_tax_entry = tk.Entry(left_box, font=("Segoe UI", 9), bd=1, relief="solid")
        self.sell_tax_entry.insert(0, "15.0")
        self.sell_tax_entry.pack(fill=tk.X, pady=(0, 8))

        tk.Button(
            left_box,
            text="Calculate Selling Proceeds",
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=4,
            command=self._calc_selling_results,
        ).pack(fill=tk.X, pady=(0, 6))

        tk.Button(
            left_box,
            text="💰 Record Sale & Deduct Shares",
            font=("Segoe UI", 9, "bold"),
            bg="#0f9d58",
            fg="#ffffff",
            relief="flat",
            pady=6,
            command=self._execute_and_record_sale,
        ).pack(fill=tk.X)

        right_box = ttk.Frame(container)
        right_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        res_card = tk.LabelFrame(right_box, text=" Selling Proceeds & Profit Breakdown ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=12, pady=10)
        res_card.pack(fill=tk.X, pady=(0, 8))

        self.sell_results = {}
        sell_res_fields = [
            ("gross_proceeds", "Gross Sale Proceeds:", "$0.00", self.text_dark),
            ("cost_basis", "Cost Basis Sold:", "$0.00", self.text_muted),
            ("commission_fee", "Broker Commission:", "$0.00", self.red_color),
            ("gross_gain", "Realized Gain (Pre-tax):", "$0.00", self.text_dark),
            ("estimated_tax", "Estimated Capital Gains Tax:", "$0.00", self.red_color),
            ("net_proceeds", "Net Cash Received:", "$0.00", self.primary_color),
            ("net_profit", "Net Profit (After Tax/Fees):", "$0.00", self.green_color),
            ("net_roi_pct", "Net Return on Investment (ROI):", "0.00%", self.green_color),
        ]

        for i, (k, lbl, default, col) in enumerate(sell_res_fields):
            r = i // 2
            c = (i % 2) * 2
            tk.Label(res_card, text=lbl, font=("Segoe UI", 8, "bold"), bg="#ffffff", fg=self.text_muted).grid(row=r * 2, column=c, sticky="w", padx=8)
            val_l = tk.Label(res_card, text=default, font=("Segoe UI", 11, "bold"), bg="#ffffff", fg=col)
            val_l.grid(row=r * 2 + 1, column=c, sticky="w", padx=8, pady=(0, 4))
            self.sell_results[k] = val_l

        target_card = tk.LabelFrame(right_box, text=" Breakeven & Target Price Analyzer ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=12, pady=10)
        target_card.pack(fill=tk.BOTH, expand=True)

        be_row = ttk.Frame(target_card)
        be_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(be_row, text="Breakeven Sell Price (After Fees):", font=("Segoe UI", 9, "bold"), bg=self.bg_main).pack(side=tk.LEFT)
        self.lbl_breakeven = tk.Label(be_row, text="$0.00", font=("Segoe UI", 11, "bold"), bg=self.bg_main, fg=self.primary_color)
        self.lbl_breakeven.pack(side=tk.LEFT, padx=8)

        tp_frame = ttk.Frame(target_card)
        tp_frame.pack(fill=tk.X, pady=(6, 0))
        tk.Label(tp_frame, text="Target Profit ($):", font=("Segoe UI", 8, "bold"), bg=self.bg_main).pack(side=tk.LEFT)
        self.target_profit_entry = tk.Entry(tp_frame, width=10, bd=1, relief="solid")
        self.target_profit_entry.insert(0, "500.00")
        self.target_profit_entry.pack(side=tk.LEFT, padx=6)

        tk.Button(
            tp_frame,
            text="Find Required Sell Price",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=6,
            command=self._calc_target_sell_price,
        ).pack(side=tk.LEFT, padx=4)

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
        self.btn_tx_record.pack(side=tk.LEFT, padx=(0, 8))

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
            self.history_tree.heading(col, text=h)
            self.history_tree.column(col, width=w, anchor="e" if col not in ("type", "symbol", "portfolio", "currency", "date") else "center")

        v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.history_tree.tag_configure("positive", foreground=self.green_color)
        self.history_tree.tag_configure("negative", foreground=self.red_color)
        self.history_tree.tag_configure("buy", foreground="#00897b")
        self.history_tree.tag_configure("neutral", foreground=self.text_dark)

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
            text="Total Realized Profit: $0.00",
            font=("Segoe UI", 10, "bold"),
            bg=self.bg_main,
            fg=self.green_color,
        )
        self.lbl_total_realized.pack(side=tk.RIGHT, padx=12)

    # -------------------------------------------------------------
    # Google Account Sync Dialog
    # -------------------------------------------------------------
    def _open_sync_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("🌐 Google Finance Account Synchronization")
        dlg.geometry("640x520")
        dlg.minsize(560, 460)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        sync_notebook = ttk.Notebook(dlg)
        sync_notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Tab A: Live Account / Session Cookie Sync
        tab_live = ttk.Frame(sync_notebook, padding=12)
        sync_notebook.add(tab_live, text=" ⚡ Live Account Sync ")

        tk.Label(
            tab_live,
            text="Synchronize with your Personal Google Finance Account",
            font=("Segoe UI", 11, "bold"),
            fg=self.primary_color,
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            tab_live,
            text="Enter your Google Finance Watchlist/Portfolio URL and your Google Session Cookie to automatically pull your personalized stock lists and purchase prices.",
            font=("Segoe UI", 8),
            fg=self.text_muted,
            wraplength=580,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(tab_live, text="Portfolio / Watchlist URL:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        url_entry = tk.Entry(tab_live, font=("Segoe UI", 9), bd=1, relief="solid")
        curr_cfg = load_sync_config()
        default_url = curr_cfg.get("portfolio_url") or "https://www.google.com/finance/beta/portfolio/c58e567d-3b90-41d3-92fa-6b200333ec17"
        url_entry.insert(0, default_url)
        url_entry.pack(fill=tk.X, pady=(2, 8))

        tk.Label(tab_live, text="Google Session Cookie (from DevTools / browser):", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        cookie_text = tk.Text(tab_live, height=4, font=("Courier", 8), bd=1, relief="solid")
        if curr_cfg.get("cookie"):
            cookie_text.insert("1.0", curr_cfg.get("cookie"))
        cookie_text.pack(fill=tk.X, pady=(2, 8))

        status_test_lbl = tk.Label(tab_live, text="", font=("Segoe UI", 8, "bold"), wraplength=580)
        status_test_lbl.pack(anchor="w", pady=(0, 6))

        def test_conn():
            cookie = cookie_text.get("1.0", tk.END).strip()
            status_test_lbl.config(text="Testing connection to Google Finance...", fg=self.primary_color)
            dlg.update()
            success, msg = self.account_sync.test_connection(cookie)
            color = self.green_color if success else self.red_color
            status_test_lbl.config(text=msg, fg=color)

        def sync_live():
            url = url_entry.get().strip()
            cookie = cookie_text.get("1.0", tk.END).strip()
            status_test_lbl.config(text="Fetching portfolio from Google Finance...", fg=self.primary_color)
            dlg.update()

            res = self.account_sync.fetch_user_portfolio(url, cookie)
            if not res.get("success"):
                err_msg = res.get("error", "Failed to fetch portfolio.")
                status_test_lbl.config(text=f"Sync failed: {err_msg}", fg=self.red_color)
                messagebox.showwarning(
                    "Sync Notice",
                    f"{err_msg}\n\nTip: You can export your portfolio from Google Finance using the 'Download list' button, then switch to the '📥 Google Finance CSV' tab here to import it with 100% accuracy.",
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
                "Sync Portfolio",
                f"Retrieved {len(new_holdings)} stocks from Google Finance for '{target_p}'!\n\n"
                f"Click 'Yes' to MERGE with '{target_p}'.\n"
                f"Click 'No' to REPLACE '{target_p}'.\n"
                f"Click 'Cancel' to abort.",
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
                text=f"Sync successful! Loaded {len(new_holdings)} stocks at {datetime.now().strftime('%H:%M:%S')}",
                fg=self.green_color,
            )
            messagebox.showinfo("Sync Success", f"Successfully synced {len(new_holdings)} stocks from your Google Finance account!", parent=dlg)

        btn_test = tk.Button(tab_live, text="🔍 Test Connection", font=("Segoe UI", 9), bg="#ffffff", relief="solid", bd=1, padx=8, command=test_conn)
        btn_test.pack(side=tk.LEFT, padx=(0, 6))

        btn_do_sync = tk.Button(tab_live, text="⚡ Sync Account Now", font=("Segoe UI", 9, "bold"), bg=self.primary_color, fg="#ffffff", relief="flat", padx=12, command=sync_live)
        btn_do_sync.pack(side=tk.LEFT)

        # Tab B: Google Finance CSV Import
        tab_csv = ttk.Frame(sync_notebook, padding=12)
        sync_notebook.add(tab_csv, text=" 📥 Google Finance CSV ")

        tk.Label(tab_csv, text="Import Downloaded Google Finance List", font=("Segoe UI", 11, "bold"), fg=self.primary_color).pack(anchor="w", pady=(0, 4))
        tk.Label(
            tab_csv,
            text="Google Finance allows downloading your watchlist or portfolio as a CSV via the 'Download list' button. You can directly import that file here:",
            font=("Segoe UI", 8),
            fg=self.text_muted,
            wraplength=580,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        target_port_frame = ttk.Frame(tab_csv)
        target_port_frame.pack(anchor="w", pady=(0, 12))
        tk.Label(target_port_frame, text="Target Portfolio for Imported Stocks:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        port_list = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        if not port_list:
            port_list = [DEFAULT_PORTFOLIO_NAME]
        default_sync_port = self.current_portfolio if self.current_portfolio != "All Portfolios (Consolidated)" else port_list[0]
        import_port_var = tk.StringVar(value=default_sync_port)
        import_port_combo = ttk.Combobox(target_port_frame, textvariable=import_port_var, values=port_list, width=18)
        import_port_combo.pack(side=tk.LEFT)

        def import_gf_csv():
            target_p = import_port_var.get().strip() or DEFAULT_PORTFOLIO_NAME
            fn = filedialog.askopenfilename(
                title=f"Select Google Finance Downloaded CSV for '{target_p}'",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                parent=dlg,
            )
            if fn:
                loaded = self.account_sync.parse_google_finance_csv(fn, target_portfolio=target_p)
                if not loaded:
                    messagebox.showerror("Error", "Could not parse Google Finance CSV. Make sure it contains Symbol and Price columns.", parent=dlg)
                    return

                ans = messagebox.askyesno(
                    "Import Google Finance List",
                    f"Found {len(loaded)} stocks in the file for portfolio '{target_p}':\n"
                    f"{', '.join([h['symbol'] for h in loaded[:6]])}{'...' if len(loaded) > 6 else ''}\n\n"
                    f"Would you like to import these stocks into portfolio '{target_p}'?",
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
                    messagebox.showinfo("Success", f"Imported {len(loaded)} stocks into '{target_p}'!", parent=dlg)

        tk.Button(
            tab_csv,
            text="📂 Choose Google Finance CSV...",
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
        sync_notebook.add(tab_export, text=" 📤 Export for Google ")

        tk.Label(tab_export, text="Export Portfolio in Google Finance Format", font=("Segoe UI", 11, "bold"), fg=self.primary_color).pack(anchor="w", pady=(0, 4))
        tk.Label(
            tab_export,
            text="Generate a clean CSV compatible with Google Finance (Symbol, Name, Shares, Purchase price, Currency).",
            font=("Segoe UI", 8),
            fg=self.text_muted,
            wraplength=580,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        def export_gf_format():
            fn = filedialog.asksaveasfilename(
                title="Export for Google Finance",
                defaultextension=".csv",
                initialfile="google_finance_portfolio.csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                parent=dlg,
            )
            if fn:
                if self.account_sync.export_to_google_finance_csv(fn, self.holdings):
                    messagebox.showinfo("Success", f"Exported successfully to:\n{fn}", parent=dlg)
                else:
                    messagebox.showerror("Error", "Failed to export file.", parent=dlg)

        tk.Button(
            tab_export,
            text="💾 Export to Google Finance CSV",
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
        sync_notebook.add(tab_help, text=" ❓ How To Sync ")

        help_text = (
            "How to Sync with Your Google Finance Account:\n\n"
            "Method 1: Direct CSV Download (Easiest)\n"
            "1. Open https://www.google.com/finance in your browser.\n"
            "2. Navigate to your Watchlist or Portfolio.\n"
            "3. Click the 'Download list' button (CSV icon next to your watchlist).\n"
            "4. In this app, click 'Choose Google Finance CSV' in the 'Google Finance CSV' tab.\n\n"
            "Method 2: Live Session Sync (Automatic)\n"
            "1. In Chrome/Firefox, visit your Google Finance portfolio.\n"
            "2. Press F12 to open Developer Tools -> Network tab.\n"
            "3. Refresh the page, click on any 'finance' network request.\n"
            "4. In Request Headers, right-click 'Cookie' -> 'Copy Value'.\n"
            "5. Paste the cookie in the 'Live Account Sync' tab and click 'Sync Account Now'.\n"
            "6. The app securely saves the cookie locally in config.json to auto-sync."
        )
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
    def _open_add_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Add New Stock / Asset")
        dlg.geometry("460x560")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        # Header
        tk.Label(frame, text="Add New Stock / Asset", font=("Segoe UI", 12, "bold"), fg=self.primary_color).pack(anchor="w", pady=(0, 4))

        # Target Portfolio & Currency
        port_curr_row = ttk.Frame(frame)
        port_curr_row.pack(fill=tk.X, pady=(4, 6))

        tk.Label(port_curr_row, text="Portfolio:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        available_ports = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        if not available_ports:
            available_ports = [DEFAULT_PORTFOLIO_NAME]
        default_add_port = self.current_portfolio if self.current_portfolio != "All Portfolios (Consolidated)" else available_ports[0]
        port_add_cb = ttk.Combobox(port_curr_row, values=available_ports, width=16)
        port_add_cb.set(default_add_port)
        port_add_cb.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(port_curr_row, text="Currency:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        curr_add_cb = ttk.Combobox(port_curr_row, values=["USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY"], state="readonly", width=8)
        def_curr = "USD"
        if "CAD" in default_add_port.upper():
            def_curr = "CAD"
        elif "HKD" in default_add_port.upper():
            def_curr = "HKD"
        curr_add_cb.set(def_curr)
        curr_add_cb.pack(side=tk.LEFT)

        # Symbol entry + live verify button
        sym_box = ttk.Frame(frame)
        sym_box.pack(fill=tk.X, pady=(4, 6))

        tk.Label(sym_box, text="Symbol / Ticker:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
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
            verify_status_lbl.config(text=f"Searching Google Finance for '{sym}'...", fg=self.primary_color)
            dlg.update()

            res = self.fetcher.search_or_verify_symbol(sym)
            if res.get("valid"):
                live_data_box["price"] = res["price"]
                live_data_box["name"] = res["name"]
                live_data_box["yield"] = res["dividend_yield"]
                live_data_box["div_share"] = res.get("annual_dividend_per_share", 0.0)
                live_data_box["currency"] = res.get("currency", "USD")

                name_entry.delete(0, tk.END)
                name_entry.insert(0, res["name"])

                if res.get("currency") and res["currency"] in curr_add_cb["values"]:
                    curr_add_cb.set(res["currency"])

                verify_status_lbl.config(
                    text=f"✅ Found: {res['name']} — Live Price: ${res['price']:.2f} {res.get('currency', 'USD')}",
                    fg=self.green_color,
                )
            else:
                verify_status_lbl.config(text=f"⚠️ {res.get('error')}", fg=self.red_color)

        btn_verify = tk.Button(input_row, text="🔍 Lookup", font=("Segoe UI", 9), bg="#ffffff", relief="solid", bd=1, padx=8, command=on_verify)
        btn_verify.pack(side=tk.RIGHT)

        verify_status_lbl.pack(anchor="w", pady=(0, 6))

        # Asset Type
        type_row = ttk.Frame(frame)
        type_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(type_row, text="Asset Type:", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 6))
        asset_type_cb = ttk.Combobox(type_row, values=["Stock", "ETF", "Crypto", "Mutual Fund", "Index", "Other"], state="readonly", width=12)
        asset_type_cb.set("Stock")
        asset_type_cb.pack(side=tk.LEFT)

        # Company / Asset Name
        tk.Label(frame, text="Company / Asset Name:", font=("Segoe UI", 8)).pack(anchor="w")
        name_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        name_entry.pack(fill=tk.X, pady=(2, 6))

        # Shares
        tk.Label(frame, text="Number of Shares:", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        shares_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        shares_entry.insert(0, "10")
        shares_entry.pack(fill=tk.X, pady=(2, 6))

        # Buy Price with quick "Use Live Price" button
        price_row = ttk.Frame(frame)
        price_row.pack(fill=tk.X, pady=(2, 10))

        tk.Label(price_row, text="Buy Price per Share ($):", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)

        def use_live_price():
            if live_data_box["price"] > 0:
                price_entry.delete(0, tk.END)
                price_entry.insert(0, f"{live_data_box['price']:.2f}")
            else:
                on_verify()
                if live_data_box["price"] > 0:
                    price_entry.delete(0, tk.END)
                    price_entry.insert(0, f"{live_data_box['price']:.2f}")

        btn_use_live = tk.Button(price_row, text="⚡ Use Live Price", font=("Segoe UI", 8), bg="#ffffff", relief="solid", bd=1, padx=4, command=use_live_price)
        btn_use_live.pack(side=tk.RIGHT)

        price_entry = tk.Entry(frame, font=("Segoe UI", 9), bd=1, relief="solid")
        price_entry.insert(0, "100.00")
        price_entry.pack(fill=tk.X, pady=(0, 8))

        # Optional Price Alerts: Target Price and Stop Loss
        add_alert_row = ttk.Frame(frame)
        add_alert_row.pack(fill=tk.X, pady=(0, 12))

        t_sub = ttk.Frame(add_alert_row)
        t_sub.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Label(t_sub, text="🎯 Target Sell ($):", font=("Segoe UI", 8)).pack(anchor="w")
        target_add_entry = tk.Entry(t_sub, font=("Segoe UI", 9), bd=1, relief="solid")
        target_add_entry.pack(fill=tk.X, pady=(2, 0))

        s_sub = ttk.Frame(add_alert_row)
        s_sub.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(s_sub, text="⚠️ Stop Loss ($):", font=("Segoe UI", 8)).pack(anchor="w")
        stop_add_entry = tk.Entry(s_sub, font=("Segoe UI", 9), bd=1, relief="solid")
        stop_add_entry.pack(fill=tk.X, pady=(2, 0))

        def on_save():
            sym = sym_entry.get().strip().upper()
            if not sym:
                messagebox.showerror("Error", "Please enter a symbol.", parent=dlg)
                return

            try:
                shares = float(shares_entry.get().strip())
                buy_price = float(price_entry.get().strip())
                if shares <= 0 or buy_price < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "Please enter valid positive numbers.", parent=dlg)
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
                ans = messagebox.askyesno(
                    "Holding Exists",
                    f"You already hold {sym} in {target_port}. Merge these {shares} shares into your position? (Weighted average cost basis will be calculated)",
                    parent=dlg,
                )
                if ans:
                    tot_shares = existing["shares"] + shares
                    avg_p = (existing["shares"] * existing["buy_price"] + shares * buy_price) / tot_shares
                    existing["shares"] = tot_shares
                    existing["buy_price"] = avg_p
                    existing["currency"] = curr
                    existing.update(calc_holding_summary(tot_shares, avg_p, cur_price, div_yield, ann_div))
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
            text="➕ Save Stock to Portfolio",
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
    def _on_tree_double_click(self, event):
        item_id = self.holdings_tree.identify_row(event.y)
        if item_id:
            self.holdings_tree.selection_set(item_id)
            self.holdings_tree.focus(item_id)
            self._open_edit_dialog()

    def _open_edit_dialog(self):
        selected = self.holdings_tree.selection()
        if not selected:
            messagebox.showwarning("Notice", "Please select a holding from the table to edit.")
            return

        item_id = selected[0]
        holding = self.holding_map.get(item_id) if hasattr(self, "holding_map") else None
        if not holding:
            try:
                row_vals = self.holdings_tree.item(item_id).get("values", [])
                raw_sym = ""
                if len(row_vals) > 1:
                    raw_sym = str(row_vals[1]).replace("🎯 ", "").replace("⚠️ ", "").strip().upper()
                elif len(row_vals) == 1:
                    raw_sym = str(row_vals[0]).strip().upper()
                holding = next((h for h in self.holdings if str(h.get("symbol", "")).strip().upper() == raw_sym or str(h.get("symbol", "")).split(":")[0].strip().upper() == raw_sym), None)
            except Exception:
                holding = None

        if not holding:
            return

        sym = holding.get("symbol", "")
        cur_port = holding.get("portfolio", DEFAULT_PORTFOLIO_NAME)
        cur_curr = holding.get("currency", "USD")

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Edit Holding: {sym}")
        dlg.geometry("440x480")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text=f"Symbol: {sym} ({holding.get('name', '')})",
            font=("Segoe UI", 10, "bold"),
            fg=self.primary_color,
            bg=self.bg_main,
        ).pack(anchor="w", pady=(0, 8))

        # Portfolio selection
        port_row = ttk.Frame(frame)
        port_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(port_row, text="Portfolio:", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        available_ports = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        if cur_port not in available_ports:
            available_ports.append(cur_port)
        port_edit_cb = ttk.Combobox(port_row, values=available_ports, width=16)
        port_edit_cb.set(cur_port)
        port_edit_cb.pack(side=tk.LEFT, padx=(0, 10))

        # Currency selection
        tk.Label(port_row, text="Currency:", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        curr_edit_cb = ttk.Combobox(port_row, values=["USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY"], state="readonly", width=8)
        curr_edit_cb.set(cur_curr)
        curr_edit_cb.pack(side=tk.LEFT)

        tk.Label(frame, text="Number of Shares:", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        shares_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, insertbackground=self.text_dark)
        shares_entry.insert(0, str(holding.get("shares", 0)))
        shares_entry.pack(fill=tk.X, pady=(2, 8))

        tk.Label(frame, text="Buy Price / Cost Basis ($):", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        price_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, insertbackground=self.text_dark)
        price_entry.insert(0, str(holding.get("buy_price", 0)))
        price_entry.pack(fill=tk.X, pady=(2, 10))

        # Alert thresholds: Target Price and Stop Loss
        alert_row = ttk.Frame(frame)
        alert_row.pack(fill=tk.X, pady=(0, 12))

        target_sub = ttk.Frame(alert_row)
        target_sub.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Label(target_sub, text="🎯 Target Sell ($):", font=("Segoe UI", 8, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        target_entry = tk.Entry(target_sub, font=("Segoe UI", 9), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, insertbackground=self.text_dark)
        target_entry.insert(0, str(holding.get("target_sell_price") or ""))
        target_entry.pack(fill=tk.X, pady=(2, 0))

        stop_sub = ttk.Frame(alert_row)
        stop_sub.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(stop_sub, text="⚠️ Stop Loss ($):", font=("Segoe UI", 8, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
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
                messagebox.showerror("Error", "Please enter valid positive numbers.", parent=dlg)
                return

            new_port = port_edit_cb.get().strip() or cur_port
            new_curr = curr_edit_cb.get().strip().upper() or cur_curr

            t_str = target_entry.get().strip()
            s_str = stop_entry.get().strip()
            try:
                holding["target_sell_price"] = float(t_str) if t_str else 0.0
            except ValueError:
                holding["target_sell_price"] = 0.0
            try:
                holding["stop_loss_price"] = float(s_str) if s_str else 0.0
            except ValueError:
                holding["stop_loss_price"] = 0.0

            holding["portfolio"] = new_port
            holding["currency"] = new_curr
            holding["shares"] = shares
            holding["buy_price"] = buy_price
            summary = calc_holding_summary(
                shares,
                buy_price,
                holding.get("current_price", buy_price),
                holding.get("dividend_yield", 0.0),
                holding.get("annual_div_per_share", 0.0),
            )
            holding.update(summary)

            save_portfolio(self.all_holdings, PORTFOLIO_CSV)
            self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
            self._on_portfolio_selected()
            dlg.destroy()
            self._set_status(f"Updated holding {sym} ({new_port}, {new_curr}).")

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(10, 0))

        tk.Button(
            btn_row,
            text="Save Changes",
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=6,
            command=on_save_edit,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        tk.Button(
            btn_row,
            text="Cancel",
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
            messagebox.showwarning("Notice", "Please select at least one holding to delete.")
            return

        to_remove = []
        if hasattr(self, "holding_map"):
            for item_id in selected:
                if item_id in self.holding_map:
                    to_remove.append(self.holding_map[item_id])

        # Fallback to robust symbol & SSE numeric matching
        if not to_remove:
            selected_syms = set()
            for item_id in selected:
                val = self.holdings_tree.item(item_id)["values"][0]
                s_str = str(val).strip().upper()
                selected_syms.add(s_str)
                if s_str.isdigit():
                    selected_syms.add(f"{int(s_str):06d}")

            for h in self.holdings:
                h_sym = str(h.get("symbol", "")).strip().upper()
                h_raw = h_sym.split(":")[0]
                if (h_sym in selected_syms or h_raw in selected_syms
                    or (h_raw.isdigit() and (str(int(h_raw)) in selected_syms or f"{int(h_raw):06d}" in selected_syms))):
                    to_remove.append(h)

        count = len(to_remove)
        if count == 0:
            return

        names_display = [f"{h.get('symbol')} ({h.get('name', '')})" for h in to_remove]
        msg = f"Are you sure you want to remove {', '.join(names_display)} from your portfolio?" if count <= 3 else f"Are you sure you want to remove {count} selected stocks from your portfolio?"

        if messagebox.askyesno("Confirm Deletion", msg):
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
        holding = self.holding_map.get(item_id) if hasattr(self, "holding_map") else None
        if not holding:
            raw_sym = str(self.holdings_tree.item(item_id)["values"][0]).strip().upper()
            holding = next((h for h in self.holdings if str(h.get("symbol", "")).strip().upper() == raw_sym or str(h.get("symbol", "")).split(":")[0].strip().upper() == raw_sym), None)

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
            messagebox.showwarning("Notice", "Please select a holding first.")
            return

        item_id = selected[0]
        holding = self.holding_map.get(item_id) if hasattr(self, "holding_map") else None
        if not holding:
            raw_sym = str(self.holdings_tree.item(item_id)["values"][0]).strip().upper()
            holding = next((h for h in self.holdings if str(h.get("symbol", "")).strip().upper() == raw_sym or str(h.get("symbol", "")).split(":")[0].strip().upper() == raw_sym), None)

        if not holding:
            return

        self.notebook.select(self.tab_dividend)
        self._load_holding_into_dividend_calc(holding)

    def _send_selected_to_split_calc(self):
        selected = self.holdings_tree.selection()
        if not selected:
            messagebox.showwarning("Notice", "Please select a holding first.")
            return

        item_id = selected[0]
        holding = self.holding_map.get(item_id) if hasattr(self, "holding_map") else None
        if not holding:
            raw_sym = str(self.holdings_tree.item(item_id)["values"][0]).strip().upper()
            holding = next((h for h in self.holdings if str(h.get("symbol", "")).strip().upper() == raw_sym or str(h.get("symbol", "")).split(":")[0].strip().upper() == raw_sym), None)

        if not holding:
            return

        self.notebook.select(self.tab_split)
        self._load_holding_into_split_calc(holding)

    def _send_selected_to_selling_calc(self):
        selected = self.holdings_tree.selection()
        if not selected:
            messagebox.showwarning("Notice", "Please select a holding first.")
            return

        item_id = selected[0]
        holding = self.holding_map.get(item_id) if hasattr(self, "holding_map") else None
        if not holding:
            raw_sym = str(self.holdings_tree.item(item_id)["values"][0]).strip().upper()
            holding = next((h for h in self.holdings if str(h.get("symbol", "")).strip().upper() == raw_sym or str(h.get("symbol", "")).split(":")[0].strip().upper() == raw_sym), None)

        if not holding:
            return

        self.notebook.select(self.tab_sell)
        self._load_holding_into_selling_calc(holding)

    def _send_selected_to_chart(self):
        selected = self.holdings_tree.selection()
        if not selected:
            messagebox.showwarning("Notice", "Please select a holding first.")
            return

        item_id = selected[0]
        holding = self.holding_map.get(item_id) if hasattr(self, "holding_map") else None
        if not holding:
            raw_sym = str(self.holdings_tree.item(item_id)["values"][0]).strip().upper()
            holding = next((h for h in self.holdings if str(h.get("symbol", "")).strip().upper() == raw_sym or str(h.get("symbol", "")).split(":")[0].strip().upper() == raw_sym), None)

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
            messagebox.showerror("Error", "Please enter valid numeric values for dividend calculation.")
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
            self.div_holding_days_lbl.config(text=f"Holding: {past['days_held']} days ({past['years_held']:.2f} yrs)")

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
            messagebox.showerror("Error", "Please check numbers in DRIP settings.")
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
                text=f"{res['days_held']} days ({res['years_held']:.2f} yrs)"
            )
            if hasattr(self, "split_holding_days_lbl"):
                self.split_holding_days_lbl.config(text=f"Holding: {res['days_held']} days ({res['years_held']:.2f} yrs)")

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
                tk.Label(pill, text=f"Val: ${sc['future_value']:,.2f}", font=("Segoe UI", 8), bg="#f8f9fa").pack(anchor="w")
                tot_s = "+" if sc["total_profit_from_start"] >= 0 else ""
                tk.Label(pill, text=f"Total: {tot_s}${sc['total_profit_from_start']:,.2f}", font=("Segoe UI", 7), bg="#f8f9fa", fg=self.green_color).pack(anchor="w")
                new_s = "+" if sc["new_profit_from_today"] >= 0 else ""
                tk.Label(pill, text=f"New: {new_s}${sc['new_profit_from_today']:,.2f}", font=("Segoe UI", 7), bg="#f8f9fa", fg=self.text_muted).pack(anchor="w")

    def _apply_split_to_portfolio(self):
        sym = self.split_sym_entry.get().strip().upper()
        holding = next((h for h in self.holdings if h["symbol"] == sym), None)
        if not holding:
            messagebox.showwarning("Notice", f"Symbol {sym} is not in your current portfolio.")
            return

        self._calc_split_results()
        if not hasattr(self, "last_split_result"):
            return

        res = self.last_split_result
        msg = (
            f"Apply {res['split_ratio']} stock split to {sym}?\n\n"
            f"Old Position: {res['original_shares']:.4g} shares @ ${res['original_buy_price']:.2f}\n"
            f"New Position: {res['new_shares']:.4g} shares @ ${res['new_buy_price']:.4f}\n\n"
            "This will permanently update your portfolio.csv."
        )
        if messagebox.askyesno("Confirm Stock Split", msg):
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
            messagebox.showinfo("Success", f"Stock split applied successfully to {sym}!")
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

        res = calc_selling_proceeds(shares, buy_p, sell_p, comm_flat, comm_pct, tax_rate)
        res["symbol"] = sym
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
            messagebox.showerror("Error", "Please check your numbers.")
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
            text=f"🎯 Need to sell at: ${res['target_sell_price']:.2f} / share (Total proceeds: ${res['gross_proceeds_at_target']:,.2f})"
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
            messagebox.showerror("Error", f"Cannot sell {shares_to_sell} shares; you only hold {holding['shares']}.")
            return

        confirm_msg = (
            f"Record Sale for {shares_to_sell} shares of {sym} at ${res['sell_price']:.2f}?\n\n"
            f"Gross Proceeds: ${res['gross_proceeds']:,.2f}\n"
            f"Commission: ${res['commission_fee']:,.2f}\n"
            f"Estimated Tax: ${res['estimated_tax']:,.2f}\n"
            f"Net Profit: ${res['net_profit']:+,.2f} ({res['net_roi_pct']:+.2f}% ROI)\n\n"
            "This will append to sales_history.csv and deduct shares from portfolio.csv."
        )
        if not messagebox.askyesno("Confirm Sale Execution", confirm_msg):
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

        messagebox.showinfo("Sale Recorded", "Sale transaction logged and portfolio updated successfully!")

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

        if self.auto_refresh_enabled and not self.is_fetching and self.holdings:
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
        sec = mapping.get(val, 30)
        if sec == 0:
            self.auto_refresh_enabled = False
            self.refresh_interval_sec = 0
            self._set_status("Auto-receive paused.")
        else:
            self.auto_refresh_enabled = True
            self.refresh_interval_sec = sec
            self._set_status(f"Auto-receive active ({val} interval).")
        self._schedule_auto_refresh()

    def fetch_all_quotes(self):
        if self.is_fetching:
            return

        symbols = sorted(list({h["symbol"] for h in self.all_holdings if h.get("symbol")}))
        if not symbols:
            return

        self.is_fetching = True
        self._set_status(f"Fetching live quotes from Google Finance for {len(symbols)} symbol(s)...")

        def worker():
            results = []
            for sym in symbols:
                if not getattr(self, "is_running", True):
                    return
                quote = self.fetcher.fetch_quote(sym)
                if not getattr(self, "is_running", True):
                    return
                results.append((sym, quote))
                time.sleep(0.3)
            if getattr(self, "is_running", True):
                self.fetch_queue.put(("ALL_QUOTES", results))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

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
                if msg_type == "ALL_QUOTES":
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

    def _handle_all_quotes_result(self, results):
        if not getattr(self, "is_running", True):
            return
        self.is_fetching = False
        updated_count = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for sym, quote in results:
            if quote.get("success"):
                updated_count += 1
                for h in self.all_holdings:
                    if h["symbol"] == sym:
                        price = quote["price"]
                        h["current_price"] = price
                        h["name"] = quote.get("name") or h.get("name", sym)
                        h["change"] = quote.get("change")
                        h["change_percent"] = quote.get("change_percent")
                        h["dividend_yield"] = quote.get("dividend_yield", 0.0)
                        h["annual_div_per_share"] = quote.get("annual_dividend_per_share", 0.0)
                        if quote.get("currency") and (not h.get("currency") or h.get("currency") == "USD"):
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

        save_portfolio(self.all_holdings, PORTFOLIO_CSV)
        self._on_portfolio_selected()

        self._set_status(f"Updated {updated_count}/{len(results)} quotes from Google Finance at {now_str}")
        self.lbl_time.config(text=f"Last sync: {now_str}")

    def _set_status(self, text: str):
        self.lbl_status.config(text=text)

    # -------------------------------------------------------------
    # Tables and Dropdowns Sync
    # -------------------------------------------------------------
    def _refresh_holdings_table(self):
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

            # Target alert indicators
            target_p = float(h.get("target_sell_price") or 0.0)
            stop_loss = float(h.get("stop_loss_price") or 0.0)
            alert_prefix = ""
            if target_p > 0 and current_price >= target_p:
                alert_prefix = "🎯 "
            elif stop_loss > 0 and current_price <= stop_loss:
                alert_prefix = "⚠️ "

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
                    f"{float(h.get('dividend_yield', 0.0)):.2f}%",
                    f"{sym_char}{float(h.get('annual_dividend', 0.0)):,.2f}",
                    h.get("last_updated", ""),
                ),
                tags=(tag,),
            )

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

        displayed_txs = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=port_param, tx_type=type_param)
        self.transactions = displayed_txs
        self.sales_history = [t for t in displayed_txs if t.get("type", "BUY") == "SELL"]

        total_profit_target = 0.0
        buy_count = 0
        sell_count = 0

        if not displayed_txs:
            all_txs = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=None, tx_type=None)
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
                self.lbl_sales_stats.config(text=f"0 transaction(s) found ({total_across} total across accounts)")
        else:
            for tx in displayed_txs:
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
                    text=f"Showing {len(displayed_txs)} transaction(s) ({buy_count} BUY, {sell_count} SELL)"
                )

        color = self.green_color if total_profit_target >= 0 else self.red_color
        formatted_profit = self.converter.format_money(total_profit_target, target_curr)
        filter_label = "All Accounts" if filter_sel in ("All Portfolios (Consolidated)", "All Portfolios", "All") else filter_sel
        self.lbl_total_realized.config(text=f"Realized Profit [{filter_label}] ({target_curr}): {formatted_profit}", fg=color)

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
        dlg.title("Record Transaction (BUY / SELL)")
        dlg.geometry("460x540")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.configure(bg=self.bg_main)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text="Record Buy / Sell Transaction",
            font=("Segoe UI", 12, "bold"),
            fg=self.primary_color,
            bg=self.bg_main,
        ).pack(anchor="w", pady=(0, 10))

        # Row 1: Type & Portfolio
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row1, text="Type:", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        type_cb = ttk.Combobox(row1, values=["BUY", "SELL"], state="readonly", width=8)
        type_cb.set("BUY")
        type_cb.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(row1, text="Portfolio:", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        available_ports = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        if not available_ports:
            available_ports = [DEFAULT_PORTFOLIO_NAME]
        default_port = self.current_portfolio if self.current_portfolio in available_ports else available_ports[0]
        port_cb = ttk.Combobox(row1, values=available_ports, width=16)
        port_cb.set(default_port)
        port_cb.pack(side=tk.LEFT)

        # Row 2: Symbol & Currency
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row2, text="Symbol:", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        sym_entry = tk.Entry(row2, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=12)
        sym_entry.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(row2, text="Currency:", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        curr_cb = ttk.Combobox(row2, values=["USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY"], state="readonly", width=8)
        curr_cb.set("USD")
        curr_cb.pack(side=tk.LEFT)

        # Row 3: Shares & Price
        row3 = ttk.Frame(frame)
        row3.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row3, text="Shares:", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        shares_entry = tk.Entry(row3, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=12)
        shares_entry.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(row3, text="Price ($):", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        price_entry = tk.Entry(row3, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=12)
        price_entry.pack(side=tk.LEFT)

        # Row 4: Fees / Commission
        row4 = ttk.Frame(frame)
        row4.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row4, text="Commission / Fees ($):", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(side=tk.LEFT, padx=(0, 6))
        comm_entry = tk.Entry(row4, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark, width=12)
        comm_entry.insert(0, "0.00")
        comm_entry.pack(side=tk.LEFT)

        # Row 5: Date
        tk.Label(frame, text="Date & Time (YYYY-MM-DD HH:MM):", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        date_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark)
        date_entry.insert(0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        date_entry.pack(fill=tk.X, pady=(2, 8))

        # Row 6: Notes
        tk.Label(frame, text="Notes / Memo (optional):", font=("Segoe UI", 9, "bold"), bg=self.bg_main, fg=self.text_dark).pack(anchor="w")
        notes_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid", bg=self.card_bg, fg=self.text_dark)
        notes_entry.pack(fill=tk.X, pady=(2, 12))

        # Checkbox: Update portfolio holdings
        update_holdings_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            frame,
            text="Also update active Portfolio Holdings (add shares for BUY / deduct for SELL)",
            variable=update_holdings_var,
            bg=self.bg_main,
            fg=self.text_dark,
            font=("Segoe UI", 8),
            activebackground=self.bg_main,
        ).pack(anchor="w", pady=(0, 12))

        def on_save_manual_tx():
            t_type = type_cb.get().strip().upper()
            target_port = port_cb.get().strip() or DEFAULT_PORTFOLIO_NAME
            sym = sym_entry.get().strip().upper()
            curr = curr_cb.get().strip().upper() or "USD"
            if not sym:
                messagebox.showerror("Error", "Please enter a valid ticker symbol.", parent=dlg)
                return

            try:
                shares = float(shares_entry.get().strip())
                price = float(price_entry.get().strip())
                comm = float(comm_entry.get().strip() or "0.0")
                if shares <= 0 or price < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "Please enter positive numeric values for Shares and Price.", parent=dlg)
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
                if t_type == "BUY":
                    if existing:
                        tot_sh = existing["shares"] + shares
                        avg_p = (existing["shares"] * existing["buy_price"] + shares * price) / tot_sh
                        existing["shares"] = tot_sh
                        existing["buy_price"] = avg_p
                        existing.update(calc_holding_summary(tot_sh, avg_p, existing.get("current_price", avg_p), existing.get("dividend_yield", 0.0), existing.get("annual_div_per_share", 0.0)))
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
            self._set_status(f"Recorded {t_type} transaction for {shares} shares of {sym}.")

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(10, 0))

        tk.Button(
            btn_row,
            text="💾 Save Transaction",
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=6,
            command=on_save_manual_tx,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        tk.Button(
            btn_row,
            text="Cancel",
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
                    text=f"{t('card_total_value')} ({curr_label}) • Day: {day_sign}{sym}{abs(total_day_chg):,.2f} ({day_chg_pct:+.2f}%)"
                )
            else:
                self.card_titles["total_value"].config(text=f"{t('card_total_value')} ({curr_label})")
            self.card_titles["total_cost"].config(text=f"{t('col_cost_basis')} ({curr_label})")
            self.card_titles["total_gain"].config(text=f"{t('card_unrealized_pl')} ({curr_label})")
            self.card_titles["annual_dividend"].config(text=f"{t('card_annual_dividend')} ({curr_label})")
            self.card_titles["monthly_dividend"].config(text=f"{t('div_proj_monthly')} ({curr_label})")

    def _refresh_dropdowns(self):
        syms = [f"{h['symbol']} ({h.get('name', '')})" for h in self.holdings]
        self.div_holding_cb["values"] = syms
        self.split_holding_cb["values"] = syms
        self.sell_holding_cb["values"] = syms

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
            title="Export Executive Portfolio Report",
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
                "Report Generated",
                f"Executive report successfully generated:\n{filename}\n\nWould you like to open it in your web browser now?",
                parent=self.root,
            )
            if ans:
                try:
                    webbrowser.open(f"file://{os.path.abspath(filename)}")
                except Exception as e:
                    messagebox.showinfo("Report Ready", f"Report saved at:\n{filename}\n\nOpen this file in your browser to view.", parent=self.root)
            self._set_status(f"Exported HTML report: {os.path.basename(filename)}")
        else:
            messagebox.showerror("Error", "Failed to generate report.", parent=self.root)

    # -------------------------------------------------------------
    # CSV Import / Export
    # -------------------------------------------------------------
    def _import_csv_dialog(self):
        filename = filedialog.askopenfilename(
            title="Import Portfolio CSV",
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
                messagebox.showerror("Import Error", "Could not read valid portfolio records from file.")
                return

            ans = messagebox.askyesnocancel(
                "Import Option",
                f"Loaded {len(imported)} holdings.\n\nClick 'Yes' to append to current portfolio.\nClick 'No' to replace holdings in this portfolio.\nClick 'Cancel' to abort.",
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
            messagebox.showinfo("Success", f"Imported {len(imported)} holdings successfully.")

    def _export_csv_dialog(self):
        filename = filedialog.asksaveasfilename(
            title="Export Portfolio to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="my_portfolio_export.csv",
        )
        if filename:
            if save_portfolio(self.holdings, filename):
                messagebox.showinfo("Success", f"Portfolio saved to:\n{filename}")
            else:
                messagebox.showerror("Error", "Failed to export portfolio.")

    def _export_sales_csv(self):
        filename = filedialog.asksaveasfilename(
            title="Export Transaction History to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="my_transactions_export.csv",
        )
        if filename:
            txs_to_export = getattr(self, "transactions", self.sales_history)
            if save_transactions(txs_to_export, filename):
                messagebox.showinfo("Success", f"Transaction history exported to:\n{filename}")
            else:
                messagebox.showerror("Error", "Failed to export transaction history.")

    def _clear_sales_history(self):
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to clear all transaction history?"):
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
            "Portfolio Holdings (portfolio.csv)": PORTFOLIO_CSV,
            "Transaction History (transaction_history.csv)": TRANSACTION_HISTORY_CSV,
            "Sales History (sales_history.csv)": SALES_HISTORY_CSV,
        }
        file_var = tk.StringVar(value="Portfolio Holdings (portfolio.csv)")
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
                tree.insert("", "end", values=("-", "No backups available yet", "-", "-"))
                return
            for b in backups:
                slot_label = f"#{b['index']} (Newest)" if b['index'] == 1 else (f"#{b['index']} (Oldest)" if b['index'] == 5 else f"#{b['index']}")
                tree.insert("", "end", iid=str(b['index']), values=(slot_label, b['filename'], b['modified_str'], f"{b['size_bytes']} B"))

        combo.bind("<<ComboboxSelected>>", lambda e: populate_tree())
        populate_tree()

        # Action buttons
        btn_frame = ttk.Frame(dlg, padding="16 8 16 16")
        btn_frame.pack(fill=tk.X)

        def restore_selected():
            sel = tree.selection()
            if not sel or sel[0] not in [str(i) for i in range(1, 6)]:
                messagebox.showwarning("Select Backup", "Please select a valid backup row from the list.", parent=dlg)
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
                messagebox.showinfo(t("msg_success"), f"Successfully restored backup #{idx}!", parent=dlg)
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
                messagebox.showerror(t("msg_error"), "Failed to restore backup.", parent=dlg)

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

    def on_close(self):
        self.is_running = False
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
