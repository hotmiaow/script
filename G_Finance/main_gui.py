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
)
from currency_converter import get_currency_converter
from chart_view import GoogleFinanceChartView
from csv_manager import (
    PORTFOLIO_CSV,
    SALES_HISTORY_CSV,
    DEFAULT_PORTFOLIO_NAME,
    save_portfolio,
    load_portfolio,
    get_portfolio_names,
    delete_portfolio,
    rename_portfolio,
    save_sales_history,
    load_sales_history,
    append_sale_record,
    ensure_workspace_files,
)
from tkinter import simpledialog


class ModernPortfolioApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Google Finance Portfolio Tracker & Calculator")
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
        self.sales_history: List[Dict[str, Any]] = load_sales_history(SALES_HISTORY_CSV, portfolio_name=None)
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

        # Color palette
        self.bg_main = "#f4f6f9"
        self.card_bg = "#ffffff"
        self.primary_color = "#1a73e8"
        self.text_dark = "#202124"
        self.text_muted = "#5f6368"
        self.green_color = "#0f9d58"
        self.red_color = "#d93025"

        self.root.configure(bg=self.bg_main)
        self.style.configure(".", background=self.bg_main, foreground=self.text_dark)
        self.style.configure("TFrame", background=self.bg_main)
        self.style.configure("Card.TFrame", background=self.card_bg, relief="solid", borderwidth=1)

        # Notebook / Tabs style
        self.style.configure("TNotebook", background=self.bg_main, tabmargins=[6, 5, 2, 0])
        self.style.configure(
            "TNotebook.Tab",
            background="#e0e4e9",
            foreground=self.text_dark,
            padding=[16, 8],
            font=("Segoe UI", 10, "bold"),
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", self.primary_color)],
            foreground=[("selected", "#ffffff")],
        )

        # Treeview styling
        self.style.configure(
            "Treeview",
            background="#ffffff",
            foreground=self.text_dark,
            fieldbackground="#ffffff",
            rowheight=28,
            font=("Segoe UI", 9),
        )
        self.style.configure(
            "Treeview.Heading",
            background="#e8eaed",
            foreground=self.text_dark,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        self.style.map("Treeview", background=[("selected", "#d2e3fc")], foreground=[("selected", "#174ea6")])

    # -------------------------------------------------------------
    # Top Bar with Google Sync, Add/Remove, and Auto-Refresh
    # -------------------------------------------------------------
    def _build_top_bar(self):
        top_frame = ttk.Frame(self.root, padding="12 8 12 4")
        top_frame.pack(fill=tk.X)

        # Title
        title_box = ttk.Frame(top_frame)
        title_box.pack(side=tk.LEFT)
        lbl_title = tk.Label(
            title_box,
            text="📈 Google Finance Portfolio Tracker",
            font=("Segoe UI", 14, "bold"),
            bg=self.bg_main,
            fg=self.primary_color,
        )
        lbl_title.pack(anchor="w")

        # Action and control buttons on right
        ctrl_box = ttk.Frame(top_frame)
        ctrl_box.pack(side=tk.RIGHT)

        # Google Account Sync button
        btn_sync = tk.Button(
            ctrl_box,
            text="🌐 Google Account Sync",
            font=("Segoe UI", 9, "bold"),
            bg="#fbbc04",
            fg="#202124",
            activebackground="#f9ab00",
            relief="flat",
            padx=10,
            pady=3,
            command=self._open_sync_dialog,
        )
        btn_sync.pack(side=tk.LEFT, padx=(0, 10))

        # Add Stock button
        btn_add = tk.Button(
            ctrl_box,
            text="➕ Add Stock",
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            activebackground="#1557b0",
            relief="flat",
            padx=10,
            pady=3,
            command=self._open_add_dialog,
        )
        btn_add.pack(side=tk.LEFT, padx=(0, 4))

        # Remove Stock button
        btn_remove = tk.Button(
            ctrl_box,
            text="➖ Remove Stock",
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
        btn_remove.pack(side=tk.LEFT, padx=(0, 10))

        # Auto-Refresh controls
        tk.Label(ctrl_box, text="Auto-Receive:", font=("Segoe UI", 9, "bold"), bg=self.bg_main).pack(
            side=tk.LEFT, padx=(0, 4)
        )

        self.interval_var = tk.StringVar(value="30s")
        interval_menu = ttk.Combobox(
            ctrl_box,
            textvariable=self.interval_var,
            values=["Off", "15s", "30s", "1 min", "2 min", "5 min"],
            width=7,
            state="readonly",
        )
        interval_menu.pack(side=tk.LEFT, padx=(0, 6))
        interval_menu.bind("<<ComboboxSelected>>", self._on_interval_changed)

        btn_refresh = tk.Button(
            ctrl_box,
            text="🔄 Refresh Now",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg=self.primary_color,
            activebackground="#e8f0fe",
            relief="solid",
            bd=1,
            padx=8,
            pady=3,
            command=self.fetch_all_quotes,
        )
        btn_refresh.pack(side=tk.LEFT, padx=(0, 6))

        btn_import = tk.Button(
            ctrl_box,
            text="📂 Import CSV",
            font=("Segoe UI", 9),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=6,
            pady=3,
            command=self._import_csv_dialog,
        )
        btn_import.pack(side=tk.LEFT, padx=(0, 4))

        btn_export = tk.Button(
            ctrl_box,
            text="💾 Export CSV",
            font=("Segoe UI", 9),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=6,
            pady=3,
            command=self._export_csv_dialog,
        )
        btn_export.pack(side=tk.LEFT)

    def _build_portfolio_bar(self):
        bar = ttk.Frame(self.root, padding="12 2 12 4")
        bar.pack(fill=tk.X)

        # Portfolio selector on left
        p_box = ttk.Frame(bar)
        p_box.pack(side=tk.LEFT)

        tk.Label(p_box, text="📁 Portfolio:", font=("Segoe UI", 9, "bold"), bg=self.bg_main).pack(side=tk.LEFT, padx=(0, 6))

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

        btn_new_p = tk.Button(
            p_box,
            text="➕ New",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            command=self._create_new_portfolio,
        )
        btn_new_p.pack(side=tk.LEFT, padx=(0, 4))

        btn_ren_p = tk.Button(
            p_box,
            text="✏️ Rename",
            font=("Segoe UI", 8),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            command=self._rename_current_portfolio,
        )
        btn_ren_p.pack(side=tk.LEFT, padx=(0, 4))

        btn_del_p = tk.Button(
            p_box,
            text="🗑️ Delete",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg=self.red_color,
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            command=self._delete_current_portfolio,
        )
        btn_del_p.pack(side=tk.LEFT, padx=(0, 16))

        # Currency summary selector on right
        curr_box = ttk.Frame(bar)
        curr_box.pack(side=tk.RIGHT)

        tk.Label(curr_box, text="💱 Summary In:", font=("Segoe UI", 9, "bold"), bg=self.bg_main).pack(side=tk.LEFT, padx=(0, 6))

        self.summary_curr_var = tk.StringVar(value=self.summary_currency)
        self.curr_combo = ttk.Combobox(
            curr_box,
            textvariable=self.summary_curr_var,
            values=["USD", "CAD", "HKD", "Native"],
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

    def _on_portfolio_selected(self, event=None):
        sel = self.portfolio_var.get()
        self.current_portfolio = sel
        self.all_holdings = load_portfolio(PORTFOLIO_CSV, portfolio_name=None)
        if sel in ("All Portfolios (Consolidated)", "All Portfolios", "All"):
            self.holdings = list(self.all_holdings)
            self.root.title("Google Finance Portfolio Tracker - All Portfolios (Consolidated)")
            self.sales_history = load_sales_history(SALES_HISTORY_CSV, portfolio_name=None)
        else:
            self.holdings = [h for h in self.all_holdings if h.get("portfolio") == sel]
            self.root.title(f"Google Finance Portfolio Tracker - {sel}")
            self.sales_history = load_sales_history(SALES_HISTORY_CSV, portfolio_name=sel)

        self._refresh_holdings_table()
        self._refresh_sales_table()
        self._update_metric_cards()
        self._refresh_dropdowns()
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
        self._set_status(f"Updated live exchange rates.")

    def _build_metric_cards(self):
        cards_frame = ttk.Frame(self.root, padding="12 4 12 8")
        cards_frame.pack(fill=tk.X)

        self.cards = {}
        self.card_titles = {}
        metrics = [
            ("total_value", "Portfolio Value (USD)", "$0.00", self.text_dark),
            ("total_cost", "Total Cost Basis (USD)", "$0.00", self.text_muted),
            ("total_gain", "Total Unrealized P/L (USD)", "$0.00 (+0.00%)", self.green_color),
            ("annual_dividend", "Projected Annual Div (USD)", "$0.00", self.primary_color),
            ("monthly_dividend", "Monthly Div Avg (USD)", "$0.00", self.primary_color),
        ]

        for i, (key, title, default_val, default_color) in enumerate(metrics):
            card = tk.Frame(cards_frame, bg="#ffffff", bd=1, relief="solid", padx=12, pady=8)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4 if i > 0 else (0, 4))

            lbl_title = tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), bg="#ffffff", fg=self.text_muted)
            lbl_title.pack(anchor="w")
            self.card_titles[key] = lbl_title

            lbl_val = tk.Label(card, text=default_val, font=("Segoe UI", 12, "bold"), bg="#ffffff", fg=default_color)
            lbl_val.pack(anchor="w", pady=(2, 0))

            self.cards[key] = lbl_val

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))

        # Tab 1: Portfolio Holdings
        self.tab_holdings = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_holdings, text=" 📊 Portfolio Holdings ")
        self._build_holdings_tab()

        # Tab 2: Interactive Chart (Google Finance style)
        self.tab_chart = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_chart, text=" 📈 Interactive Chart ")
        self._build_chart_tab()

        # Tab 3: Dividend & DRIP Calculator
        self.tab_dividend = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_dividend, text=" 💵 Dividend & DRIP Calculator ")
        self._build_dividend_tab()

        # Tab 4: Stock Division / Split
        self.tab_split = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_split, text=" ✂️ Stock Division (Split) ")
        self._build_split_tab()

        # Tab 5: Selling Calculator
        self.tab_sell = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_sell, text=" 🏷️ Selling & Profit Calculator ")
        self._build_selling_tab()

        # Tab 6: Trade History
        self.tab_history = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_history, text=" 📜 Sales History ")
        self._build_history_tab()

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
    def _build_holdings_tab(self):
        tab = self.tab_holdings

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
            ("portfolio", "Portfolio", 100),
            ("symbol", "Symbol", 75),
            ("name", "Company Name", 150),
            ("currency", "Curr", 55),
            ("shares", "Shares", 70),
            ("buy_price", "Buy Price", 85),
            ("current_price", "Live Price", 85),
            ("change", "Day Change", 90),
            ("market_value", "Market Value", 105),
            ("cost_basis", "Cost Basis", 100),
            ("unrealized_gain", "Profit/Loss", 105),
            ("unrealized_gain_pct", "P/L (%)", 75),
            ("div_yield", "Div Yield", 75),
            ("annual_div", "Est. Ann Div", 90),
            ("updated", "Last Updated", 130),
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
        self.holdings_tree.bind("<Double-1>", lambda e: self._open_edit_dialog())
        self.holdings_tree.bind("<Button-3>", self._show_context_menu)
        self.holdings_tree.bind("<Delete>", lambda e: self._delete_selected_holding())
        self.holdings_tree.bind("<BackSpace>", lambda e: self._delete_selected_holding())

        # Buttons below table
        btn_bar = ttk.Frame(tab, padding="8 4 8 8")
        btn_bar.pack(fill=tk.X)

        tk.Button(
            btn_bar,
            text="➕ Add Stock",
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            padx=10,
            command=self._open_add_dialog,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            btn_bar,
            text="➖ Remove Stock",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg=self.red_color,
            relief="solid",
            bd=1,
            padx=8,
            command=self._delete_selected_holding,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            btn_bar,
            text="📈 View Chart",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg=self.primary_color,
            relief="solid",
            bd=1,
            padx=8,
            command=self._send_selected_to_chart,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            btn_bar,
            text="✏️ Edit Selected",
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            command=self._open_edit_dialog,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            btn_bar,
            text="💵 Send to Dividend Calc",
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            command=self._send_selected_to_dividend_calc,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            btn_bar,
            text="✂️ Send to Stock Split",
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            command=self._send_selected_to_split_calc,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            btn_bar,
            text="🏷️ Send to Selling Calc",
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            command=self._send_selected_to_selling_calc,
        ).pack(side=tk.LEFT, padx=4)

    # -------------------------------------------------------------
    # Tab 2: Dividend & DRIP Calculator
    # -------------------------------------------------------------
    def _build_dividend_tab(self):
        tab = self.tab_dividend

        container = ttk.Frame(tab, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        left_frame = tk.LabelFrame(container, text=" Dividend Parameters ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=12, pady=12)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        tk.Label(left_frame, text="Select from Portfolio:", font=("Segoe UI", 9, "bold"), bg="#ffffff").pack(anchor="w", pady=(0, 2))
        self.div_holding_var = tk.StringVar()
        self.div_holding_cb = ttk.Combobox(left_frame, textvariable=self.div_holding_var, state="readonly", width=22)
        self.div_holding_cb.pack(fill=tk.X, pady=(0, 10))
        self.div_holding_cb.bind("<<ComboboxSelected>>", self._on_div_holding_selected)

        self.div_inputs = {}
        fields = [
            ("ticker", "Ticker / Symbol:", "AAPL"),
            ("shares", "Number of Shares:", "50"),
            ("current_price", "Current Share Price ($):", "220.00"),
            ("buy_price", "Buy Price / Cost Basis ($):", "180.00"),
            ("div_yield", "Dividend Yield (%):", "2.5"),
            ("div_per_share", "Annual Div/Share ($):", ""),
        ]

        for key, lbl, default in fields:
            tk.Label(left_frame, text=lbl, font=("Segoe UI", 9), bg="#ffffff").pack(anchor="w", pady=(2, 0))
            entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
            entry.insert(0, default)
            entry.pack(fill=tk.X, pady=(0, 6))
            self.div_inputs[key] = entry

        btn_calc_div = tk.Button(
            left_frame,
            text="Calculate Dividends",
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=4,
            command=self._calc_dividend_results,
        )
        btn_calc_div.pack(fill=tk.X, pady=(8, 12))

        tk.Label(left_frame, text="DRIP Simulation Settings", font=("Segoe UI", 9, "bold"), bg="#ffffff").pack(anchor="w", pady=(6, 2))
        
        tk.Label(left_frame, text="Years to Simulate:", font=("Segoe UI", 8), bg="#ffffff").pack(anchor="w")
        self.drip_years_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_years_entry.insert(0, "10")
        self.drip_years_entry.pack(fill=tk.X, pady=(0, 4))

        tk.Label(left_frame, text="Annual Dividend Growth (%):", font=("Segoe UI", 8), bg="#ffffff").pack(anchor="w")
        self.drip_div_growth_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_div_growth_entry.insert(0, "5.0")
        self.drip_div_growth_entry.pack(fill=tk.X, pady=(0, 4))

        tk.Label(left_frame, text="Annual Stock Price Growth (%):", font=("Segoe UI", 8), bg="#ffffff").pack(anchor="w")
        self.drip_price_growth_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_price_growth_entry.insert(0, "6.0")
        self.drip_price_growth_entry.pack(fill=tk.X, pady=(0, 4))

        tk.Label(left_frame, text="Monthly Contribution ($):", font=("Segoe UI", 8), bg="#ffffff").pack(anchor="w")
        self.drip_monthly_entry = tk.Entry(left_frame, font=("Segoe UI", 9), bd=1, relief="solid")
        self.drip_monthly_entry.insert(0, "0.0")
        self.drip_monthly_entry.pack(fill=tk.X, pady=(0, 8))

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

        sum_box = tk.LabelFrame(right_frame, text=" Dividend Projection Summary ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=10, pady=8)
        sum_box.pack(fill=tk.X, pady=(0, 8))

        self.div_results = {}
        disp_fields = [
            ("annual_total", "Annual Income ($):", "$0.00"),
            ("quarterly_total", "Quarterly Payout ($):", "$0.00"),
            ("monthly_total", "Monthly Average ($):", "$0.00"),
            ("yield_on_cost", "Yield on Cost (YoC):", "0.00%"),
            ("div_per_share", "Div / Share:", "$0.00"),
            ("total_value", "Current Position Value:", "$0.00"),
        ]

        for i, (k, label, default) in enumerate(disp_fields):
            r = i // 3
            c = (i % 3) * 2
            tk.Label(sum_box, text=label, font=("Segoe UI", 8, "bold"), bg="#ffffff", fg=self.text_muted).grid(row=r * 2, column=c, sticky="w", padx=6)
            val_lbl = tk.Label(sum_box, text=default, font=("Segoe UI", 11, "bold"), bg="#ffffff", fg=self.primary_color)
            val_lbl.grid(row=r * 2 + 1, column=c, sticky="w", padx=6, pady=(0, 4))
            self.div_results[k] = val_lbl

        drip_box = tk.LabelFrame(right_frame, text=" Dividend Reinvestment Plan (DRIP) Compounding Projection ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=8, pady=8)
        drip_box.pack(fill=tk.BOTH, expand=True)

        cols = ("year", "shares", "price", "annual_div", "portfolio_val", "invested", "profit")
        self.drip_tree = ttk.Treeview(drip_box, columns=cols, show="headings")
        drip_headers = [
            ("year", "Year", 50),
            ("shares", "Shares Owned", 90),
            ("price", "Est. Share Price", 100),
            ("annual_div", "Annual Dividend", 100),
            ("portfolio_val", "Portfolio Value", 110),
            ("invested", "Total Invested", 100),
            ("profit", "Total Gain / Profit", 110),
        ]
        for col, h, w in drip_headers:
            self.drip_tree.heading(col, text=h)
            self.drip_tree.column(col, width=w, anchor="e" if col != "year" else "center")

        drip_scroll = ttk.Scrollbar(drip_box, orient=tk.VERTICAL, command=self.drip_tree.yview)
        self.drip_tree.configure(yscrollcommand=drip_scroll.set)
        drip_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.drip_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # -------------------------------------------------------------
    # Tab 3: Stock Division (Split) Calculator
    # -------------------------------------------------------------
    def _build_split_tab(self):
        tab = self.tab_split
        container = ttk.Frame(tab, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        left_card = tk.LabelFrame(container, text=" Stock Split / Division Parameters ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=14, pady=14)
        left_card.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))

        tk.Label(left_card, text="Select Holding to Split:", font=("Segoe UI", 9, "bold"), bg="#ffffff").pack(anchor="w", pady=(0, 2))
        self.split_holding_var = tk.StringVar()
        self.split_holding_cb = ttk.Combobox(left_card, textvariable=self.split_holding_var, state="readonly", width=22)
        self.split_holding_cb.pack(fill=tk.X, pady=(0, 10))
        self.split_holding_cb.bind("<<ComboboxSelected>>", self._on_split_holding_selected)

        tk.Label(left_card, text="Stock Symbol:", font=("Segoe UI", 9), bg="#ffffff").pack(anchor="w")
        self.split_sym_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_sym_entry.pack(fill=tk.X, pady=(0, 6))

        tk.Label(left_card, text="Current Shares Owned:", font=("Segoe UI", 9), bg="#ffffff").pack(anchor="w")
        self.split_shares_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_shares_entry.pack(fill=tk.X, pady=(0, 6))

        tk.Label(left_card, text="Current Buy Price / Cost Basis ($):", font=("Segoe UI", 9), bg="#ffffff").pack(anchor="w")
        self.split_price_entry = tk.Entry(left_card, font=("Segoe UI", 9), bd=1, relief="solid")
        self.split_price_entry.pack(fill=tk.X, pady=(0, 10))

        tk.Label(left_card, text="Split Ratio Preset:", font=("Segoe UI", 9, "bold"), bg="#ffffff").pack(anchor="w")
        self.split_preset_var = tk.StringVar(value="2:1")
        presets = ["2:1 Split", "3:1 Split", "4:1 Split", "5:1 Split", "10:1 Split", "1:5 Reverse Split", "1:10 Reverse Split", "Custom"]
        preset_cb = ttk.Combobox(left_card, textvariable=self.split_preset_var, values=presets, state="readonly")
        preset_cb.pack(fill=tk.X, pady=(0, 6))
        preset_cb.bind("<<ComboboxSelected>>", self._on_split_preset_selected)

        ratio_frame = ttk.Frame(left_card)
        ratio_frame.pack(fill=tk.X, pady=(0, 12))
        tk.Label(ratio_frame, text="Ratio To:", font=("Segoe UI", 8), bg=self.bg_main).pack(side=tk.LEFT)
        self.split_to_entry = tk.Entry(ratio_frame, width=6, bd=1, relief="solid")
        self.split_to_entry.insert(0, "2")
        self.split_to_entry.pack(side=tk.LEFT, padx=4)

        tk.Label(ratio_frame, text="for Every:", font=("Segoe UI", 8), bg=self.bg_main).pack(side=tk.LEFT, padx=4)
        self.split_from_entry = tk.Entry(ratio_frame, width=6, bd=1, relief="solid")
        self.split_from_entry.insert(0, "1")
        self.split_from_entry.pack(side=tk.LEFT, padx=4)

        tk.Button(
            left_card,
            text="Calculate Split",
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=4,
            command=self._calc_split_results,
        ).pack(fill=tk.X, pady=(0, 8))

        self.btn_apply_split = tk.Button(
            left_card,
            text="✅ Apply Split to Portfolio",
            font=("Segoe UI", 9, "bold"),
            bg="#0f9d58",
            fg="#ffffff",
            relief="flat",
            pady=6,
            command=self._apply_split_to_portfolio,
        )
        self.btn_apply_split.pack(fill=tk.X)

        right_card = tk.LabelFrame(container, text=" Stock Split Comparison Results ", font=("Segoe UI", 10, "bold"), bg="#ffffff", padx=16, pady=16)
        right_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        comp_frame = ttk.Frame(right_card)
        comp_frame.pack(fill=tk.X, pady=8)

        before_box = tk.LabelFrame(comp_frame, text=" ⏪ Before Split ", font=("Segoe UI", 9, "bold"), bg="#f8f9fa", padx=12, pady=12)
        before_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        self.split_before_labels = {}
        for k, lbl in [("shares", "Shares:"), ("price", "Cost Basis / Share:"), ("total", "Total Cost Basis:")]:
            tk.Label(before_box, text=lbl, font=("Segoe UI", 8, "bold"), bg="#f8f9fa", fg=self.text_muted).pack(anchor="w")
            v = tk.Label(before_box, text="-", font=("Segoe UI", 11, "bold"), bg="#f8f9fa", fg=self.text_dark)
            v.pack(anchor="w", pady=(0, 4))
            self.split_before_labels[k] = v

        after_box = tk.LabelFrame(comp_frame, text=" ⏩ After Split ", font=("Segoe UI", 9, "bold"), bg="#e8f0fe", padx=12, pady=12)
        after_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.split_after_labels = {}
        for k, lbl in [("shares", "New Shares:"), ("price", "New Cost Basis / Share:"), ("total", "Total Cost Basis:")]:
            tk.Label(after_box, text=lbl, font=("Segoe UI", 8, "bold"), bg="#e8f0fe", fg=self.text_muted).pack(anchor="w")
            v = tk.Label(after_box, text="-", font=("Segoe UI", 11, "bold"), bg="#e8f0fe", fg=self.primary_color)
            v.pack(anchor="w", pady=(0, 4))
            self.split_after_labels[k] = v

        info_box = tk.Label(
            right_card,
            text="ℹ️ Note: Stock splits / divisions divide or multiply the number of shares while proportionally adjusting the cost basis per share. The total invested capital and overall value remain identical.",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg=self.text_muted,
            wraplength=450,
            justify="left",
        )
        info_box.pack(anchor="w", pady=(16, 0))

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

        # Top Filter Bar inside Sales History Tab
        filter_bar = ttk.Frame(tab, padding="8 6 8 2")
        filter_bar.pack(fill=tk.X)

        tk.Label(filter_bar, text="📁 Filter by Portfolio:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))

        self.sales_filter_var = tk.StringVar(value="All Portfolios (Consolidated)")
        self.sales_filter_cb = ttk.Combobox(
            filter_bar,
            textvariable=self.sales_filter_var,
            values=self._get_portfolio_dropdown_values(),
            state="readonly",
            width=26,
            font=("Segoe UI", 9)
        )
        self.sales_filter_cb.pack(side=tk.LEFT, padx=(0, 8))
        self.sales_filter_cb.bind("<<ComboboxSelected>>", self._on_sales_filter_changed)

        btn_show_all_sales = tk.Button(
            filter_bar,
            text="🌐 Show All Sales",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            pady=1,
            command=self._show_all_sales_clicked,
        )
        btn_show_all_sales.pack(side=tk.LEFT, padx=(0, 8))

        btn_match_active = tk.Button(
            filter_bar,
            text="🎯 Match Active Portfolio",
            font=("Segoe UI", 8),
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            pady=1,
            command=self._match_active_portfolio_sales,
        )
        btn_match_active.pack(side=tk.LEFT, padx=(0, 8))

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
            "portfolio",
            "symbol",
            "currency",
            "shares",
            "buy_price",
            "sell_price",
            "gross_proceeds",
            "cost_basis",
            "commission",
            "tax",
            "net_proceeds",
            "net_profit",
            "roi",
        )
        self.history_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        hist_headers = [
            ("date", "Date & Time", 120),
            ("portfolio", "Portfolio", 95),
            ("symbol", "Symbol", 65),
            ("currency", "Curr", 50),
            ("shares", "Shares", 65),
            ("buy_price", "Buy Price", 75),
            ("sell_price", "Sell Price", 75),
            ("gross_proceeds", "Gross Sale", 85),
            ("cost_basis", "Cost Basis", 85),
            ("commission", "Fees", 55),
            ("tax", "Tax", 55),
            ("net_proceeds", "Net Proceeds", 90),
            ("net_profit", "Net Profit", 90),
            ("roi", "ROI (%)", 70),
        ]

        for col, h, w in hist_headers:
            self.history_tree.heading(col, text=h)
            self.history_tree.column(col, width=w, anchor="e" if col not in ("symbol", "portfolio", "currency", "date") else "center")

        v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.history_tree.tag_configure("positive", foreground=self.green_color)
        self.history_tree.tag_configure("negative", foreground=self.red_color)

        btn_bar = ttk.Frame(tab, padding="8 4 8 8")
        btn_bar.pack(fill=tk.X)

        tk.Button(
            btn_bar,
            text="💾 Export History to CSV",
            bg="#ffffff",
            relief="solid",
            bd=1,
            padx=8,
            command=self._export_sales_csv,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            btn_bar,
            text="🗑️ Clear History",
            bg="#ffffff",
            fg=self.red_color,
            relief="solid",
            bd=1,
            padx=8,
            command=self._clear_sales_history,
        ).pack(side=tk.LEFT, padx=4)

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
        dlg.grab_set()

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

    # -------------------------------------------------------------
    # Enhanced Add Stock / Asset Dialog
    # -------------------------------------------------------------
    def _open_add_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Add New Stock / Asset")
        dlg.geometry("460x490")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

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
        price_entry.pack(fill=tk.X, pady=(0, 14))

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
            self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
            if self.current_portfolio not in ("All Portfolios (Consolidated)", target_port):
                self.current_portfolio = target_port
                self.portfolio_var.set(target_port)
            self._on_portfolio_selected()
            dlg.destroy()
            self._set_status(f"Added {sym} to {target_port} ({curr}) and saved to portfolio.csv.")

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

    # -------------------------------------------------------------
    # Edit / Delete Selected Holding(s)
    # -------------------------------------------------------------
    def _open_edit_dialog(self):
        selected = self.holdings_tree.selection()
        if not selected:
            messagebox.showwarning("Notice", "Please select a holding from the table to edit.")
            return

        item_id = selected[0]
        holding = self.holding_map.get(item_id) if hasattr(self, "holding_map") else None
        if not holding:
            raw_sym = str(self.holdings_tree.item(item_id)["values"][0]).strip().upper()
            holding = next((h for h in self.holdings if str(h.get("symbol", "")).strip().upper() == raw_sym or str(h.get("symbol", "")).split(":")[0].strip().upper() == raw_sym), None)

        if not holding:
            return

        sym = holding.get("symbol", "")
        cur_port = holding.get("portfolio", DEFAULT_PORTFOLIO_NAME)
        cur_curr = holding.get("currency", "USD")

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Edit Holding: {sym}")
        dlg.geometry("420x370")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text=f"Symbol: {sym} ({holding.get('name', '')})", font=("Segoe UI", 10, "bold"), fg=self.primary_color).pack(anchor="w", pady=(0, 8))

        # Portfolio selection
        port_row = ttk.Frame(frame)
        port_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(port_row, text="Portfolio:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        available_ports = [p for p in get_portfolio_names(PORTFOLIO_CSV) if p != "All Portfolios (Consolidated)"]
        if cur_port not in available_ports:
            available_ports.append(cur_port)
        port_edit_cb = ttk.Combobox(port_row, values=available_ports, width=16)
        port_edit_cb.set(cur_port)
        port_edit_cb.pack(side=tk.LEFT, padx=(0, 10))

        # Currency selection
        tk.Label(port_row, text="Currency:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        curr_edit_cb = ttk.Combobox(port_row, values=["USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY"], state="readonly", width=8)
        curr_edit_cb.set(cur_curr)
        curr_edit_cb.pack(side=tk.LEFT)

        tk.Label(frame, text="Number of Shares:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        shares_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid")
        shares_entry.insert(0, str(holding["shares"]))
        shares_entry.pack(fill=tk.X, pady=(2, 8))

        tk.Label(frame, text="Buy Price / Cost Basis ($):", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        price_entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid")
        price_entry.insert(0, str(holding["buy_price"]))
        price_entry.pack(fill=tk.X, pady=(2, 14))

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

            holding["portfolio"] = new_port
            holding["currency"] = new_curr
            holding["shares"] = shares
            holding["buy_price"] = buy_price
            summary = calc_holding_summary(
                shares,
                buy_price,
                holding["current_price"],
                holding.get("dividend_yield", 0.0),
                holding.get("annual_div_per_share", 0.0),
            )
            holding.update(summary)

            save_portfolio(self.all_holdings, PORTFOLIO_CSV)
            self.portfolio_combo.config(values=self._get_portfolio_dropdown_values())
            self._on_portfolio_selected()
            dlg.destroy()
            self._set_status(f"Updated holding {sym} ({new_port}, {new_curr}).")

        tk.Button(
            frame,
            text="Save Changes",
            font=("Segoe UI", 9, "bold"),
            bg=self.primary_color,
            fg="#ffffff",
            relief="flat",
            pady=6,
            command=on_save_edit,
        ).pack(fill=tk.X)

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
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numeric values for dividend calculation.")
            return

        res = calc_dividend_projection(shares, price, div_yield, ann_div, buy_price)

        self.div_results["annual_total"].config(text=f"${res['annual_total']:,.2f}")
        self.div_results["quarterly_total"].config(text=f"${res['quarterly_total']:,.2f}")
        self.div_results["monthly_total"].config(text=f"${res['monthly_total']:,.2f}")
        self.div_results["yield_on_cost"].config(text=f"{res['yield_on_cost']:.2f}%")
        self.div_results["div_per_share"].config(text=f"${res['annual_div_per_share']:.4f}")
        self.div_results["total_value"].config(text=f"${shares * price:,.2f}")

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
            ratio_to = float(self.split_to_entry.get().strip())
            ratio_from = float(self.split_from_entry.get().strip())
        except ValueError:
            return

        res = calc_stock_split(shares, buy_price, ratio_from, ratio_to)
        self.last_split_result = res

        self.split_before_labels["shares"].config(text=f"{res['original_shares']:.4g}")
        self.split_before_labels["price"].config(text=f"${res['original_buy_price']:.2f}")
        self.split_before_labels["total"].config(text=f"${res['original_basis']:,.2f}")

        self.split_after_labels["shares"].config(text=f"{res['new_shares']:.4g}")
        self.split_after_labels["price"].config(text=f"${res['new_buy_price']:.4f}")
        self.split_after_labels["total"].config(text=f"${res['new_basis']:,.2f}")

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

        append_sale_record(res, SALES_HISTORY_CSV)
        self.sales_history = load_sales_history(SALES_HISTORY_CSV, portfolio_name=self.current_portfolio)
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
                quote = self.fetcher.fetch_quote(sym)
                results.append((sym, quote))
                time.sleep(0.3)
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

        self.holding_map = {}
        for idx, h in enumerate(self.holdings):
            item_id = f"holding_item_{idx}"
            self.holding_map[item_id] = h

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

            tag = "positive" if unrealized > 0 else ("negative" if unrealized < 0 else "neutral")

            chg = h.get("change")
            chg_pct = h.get("change_percent")
            if chg is not None and chg_pct is not None:
                chg_str = f"{chg:+.2f} ({chg_pct:+.2f}%)"
            elif chg_pct is not None:
                chg_str = f"{chg_pct:+.2f}%"
            else:
                chg_str = "-"

            port = h.get("portfolio", self.current_portfolio)
            curr = h.get("currency", "USD").strip().upper() or "USD"
            sym_char = self.converter.CURRENCY_SYMBOLS.get(curr, "$")
            unreal_sign = "+" if unrealized >= 0 else "-"

            self.holdings_tree.insert(
                "",
                tk.END,
                iid=item_id,
                values=(
                    port,
                    str(h.get("symbol", "")),
                    h.get("name", h.get("symbol", "")),
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

    def _refresh_sales_table(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        filter_sel = self.sales_filter_var.get() if hasattr(self, "sales_filter_var") else "All Portfolios (Consolidated)"
        target_curr = self.summary_currency if hasattr(self, "summary_currency") else "USD"

        # Load sales for filter_sel
        if filter_sel in ("All Portfolios (Consolidated)", "All Portfolios", "All", "*"):
            displayed_sales = load_sales_history(SALES_HISTORY_CSV, portfolio_name=None)
        else:
            displayed_sales = load_sales_history(SALES_HISTORY_CSV, portfolio_name=filter_sel)

        total_profit_target = 0.0

        if not displayed_sales:
            all_sales = load_sales_history(SALES_HISTORY_CSV, portfolio_name=None)
            total_across = len(all_sales)
            self.history_tree.insert(
                "",
                tk.END,
                values=(
                    "-",
                    filter_sel,
                    f"No sales recorded in '{filter_sel}' ({total_across} trades in other portfolios — click 'Show All Sales')",
                    "-",
                    "-",
                    "-",
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
                self.lbl_sales_stats.config(text=f"0 trade(s) in {filter_sel} ({total_across} total across accounts)")
        else:
            for s in displayed_sales:
                profit = s.get("net_profit", 0.0)
                s_curr = s.get("currency", "USD").strip().upper() or "USD"
                total_profit_target += self.converter.convert(profit, s_curr, target_curr)
                tag = "positive" if profit >= 0 else "negative"
                c_sym = "C$" if s_curr == "CAD" else "$"

                self.history_tree.insert(
                    "",
                    tk.END,
                    values=(
                        s.get("date", ""),
                        s.get("portfolio", "USD HSBC"),
                        s.get("symbol", ""),
                        s_curr,
                        f"{s.get('shares_to_sell', 0.0):.4g}",
                        f"{c_sym}{s.get('buy_price', 0.0):.2f}",
                        f"{c_sym}{s.get('sell_price', 0.0):.2f}",
                        f"{c_sym}{s.get('gross_proceeds', 0.0):,.2f}",
                        f"{c_sym}{s.get('cost_basis', 0.0):,.2f}",
                        f"{c_sym}{s.get('commission_fee', 0.0):.2f}",
                        f"{c_sym}{s.get('estimated_tax', 0.0):.2f}",
                        f"{c_sym}{s.get('net_proceeds', 0.0):,.2f}",
                        f"{c_sym}{profit:+,.2f}",
                        f"{s.get('net_roi_pct', 0.0):+.2f}%",
                    ),
                    tags=(tag,),
                )

            if hasattr(self, "lbl_sales_stats"):
                self.lbl_sales_stats.config(text=f"Showing {len(displayed_sales)} completed trade(s)")

        color = self.green_color if total_profit_target >= 0 else self.red_color
        formatted_profit = self.converter.format_money(total_profit_target, target_curr)
        filter_label = "All Accounts" if filter_sel in ("All Portfolios (Consolidated)", "All Portfolios", "All") else filter_sel
        self.lbl_total_realized.config(text=f"Realized Profit [{filter_label}] ({target_curr}): {formatted_profit}", fg=color)

    def _on_sales_filter_changed(self, event=None):
        self._refresh_sales_table()

    def _show_all_sales_clicked(self):
        if hasattr(self, "sales_filter_var"):
            self.sales_filter_var.set("All Portfolios (Consolidated)")
        self._refresh_sales_table()

    def _match_active_portfolio_sales(self):
        if hasattr(self, "sales_filter_var"):
            self.sales_filter_var.set(self.current_portfolio)
        self._refresh_sales_table()

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
            self.card_titles["total_value"].config(text=f"Portfolio Value ({curr_label})")
            self.card_titles["total_cost"].config(text=f"Total Cost Basis ({curr_label})")
            self.card_titles["total_gain"].config(text=f"Total Unrealized P/L ({curr_label})")
            self.card_titles["annual_dividend"].config(text=f"Projected Annual Div ({curr_label})")
            self.card_titles["monthly_dividend"].config(text=f"Monthly Div Avg ({curr_label})")

    def _refresh_dropdowns(self):
        syms = [f"{h['symbol']} ({h.get('name', '')})" for h in self.holdings]
        self.div_holding_cb["values"] = syms
        self.split_holding_cb["values"] = syms
        self.sell_holding_cb["values"] = syms

    def _sort_holdings_by(self, col: str):
        def key_func(h):
            return h.get(col, 0)
        self.holdings.sort(key=key_func, reverse=True)
        self._refresh_holdings_table()

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
            title="Export Sales History to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="my_sales_history_export.csv",
        )
        if filename:
            if save_sales_history(self.sales_history, filename):
                messagebox.showinfo("Success", f"Sales history exported to:\n{filename}")
            else:
                messagebox.showerror("Error", "Failed to export sales history.")

    def _clear_sales_history(self):
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to clear all sales transaction history?"):
            self.sales_history = []
            save_sales_history([], SALES_HISTORY_CSV)
            self._refresh_sales_table()
            self._set_status("Cleared sales history.")

    def on_close(self):
        self.is_running = False
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
            self.root.destroy()
        except Exception:
            pass


def launch_app():
    root = tk.Tk()
    app = ModernPortfolioApp(root)
    try:
        root.mainloop()
    except (KeyboardInterrupt, SystemExit):
        app.on_close()


if __name__ == "__main__":
    launch_app()
