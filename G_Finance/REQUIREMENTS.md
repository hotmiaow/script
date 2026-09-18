# Software Requirements Document (SRD)
## Google Finance Portfolio Tracker & Financial Calculator Suite

**Document Version:** 2.0.0  
**Status:** Completed & Implemented  
**Date:** 2026-09-18  
**System Type:** Desktop Financial Management & Analytics Application  
**Runtime:** Python 3.10+ (Tkinter / Native Canvas / Requests / BeautifulSoup)  

---

## 1. Executive Summary & Purpose

The **Google Finance Portfolio Tracker & Financial Calculator Suite** is a high-performance desktop investment platform designed to manage multi-asset, multi-currency portfolios with live market data synchronization from Google Finance. The application eliminates dependencies on expensive closed-source financial platforms or database backends by utilizing transparent, user-auditable local CSV and JSON storage.

The suite provides:
1. Real-time quote streaming from international exchanges (US, SSE, TSE, etc.) and foreign exchange (FX) rates.
2. Comprehensive multi-portfolio management and cross-account consolidated analytics.
3. Interactive Google Finance-style visual charting and dynamic asset allocation donut charts.
4. Mathematical financial modeling tools: Dividend & DRIP compounding simulators, stock split calculators, and capital gains selling simulators.
5. Complete transaction history tracking for all BUY and SELL activities with multi-criteria filtering.
6. Automatic rolling 5-version file backup and rotation engine.
7. Tri-lingual Internationalization (i18n) supporting English, Traditional Chinese (`繁體中文`), and Simplified Chinese (`简体中文`) with real-time UI switching.
8. Instant, cooperative termination lifecycle management.

---

## 2. Core Functional Requirements (FR)

### FR-1: Real-Time Market Data Auto-Receiver & Google Scraper
- **FR-1.1**: The system shall automatically fetch live quotes, daily price changes, percent changes, ex-dividend dates, annual dividends, dividend yields, and P/E ratios directly from Google Finance without third-party API keys.
- **FR-1.2**: The scraper shall support global asset tickers across major exchanges, including NASDAQ, NYSE, NYSEARCA, BATS, and the Shanghai Stock Exchange (SSE / `SHA:` in Chinese Yuan `CNY`).
- **FR-1.3**: The system shall support background polling at user-configurable intervals (`Off`, `15s`, `30s`, `1 min`, `2 min`, `5 min`) as well as manual on-demand refresh.
- **FR-1.4**: All network quote operations must execute asynchronously on worker threads so that the user interface never freezes or stutters during network requests.
- **FR-1.5**: Real-time quotes shall be cached in memory to minimize redundant HTTP traffic.

### FR-2: Multi-Portfolio Management & Account Segmentation
- **FR-2.1**: The system shall allow users to create, rename, and delete custom portfolios (e.g., `USD HSBC`, `CAD TSFA`, `CAD RRSP`, `USD RRSP`, `USD TSFA`).
- **FR-2.2**: The portfolio selector shall provide an `All Portfolios (Consolidated)` view that aggregates holdings and transaction histories across all user accounts.
- **FR-2.3**: Switching portfolios shall immediately re-filter the active holdings table, refresh metric cards, update financial calculators, and trigger an automatic redrawing of the allocation chart.

### FR-3: Stock Holdings & Asset Inventory Management
- **FR-3.1**: Users can add holdings by specifying Symbol, Company Name, Portfolio, Currency, Shares, Buy Price, Dividend Yield, Target Sell Price, and Stop-Loss Price.
- **FR-3.2**: The "Add Stock" modal shall include a live **🔍 Lookup** button that queries Google Finance in real time to verify the symbol and auto-populate company name, current price, currency, and dividend yield.
- **FR-3.3**: The modal shall feature a **⚡ Use Live Price** button to quickly adopt the current market quote as the purchase price.
- **FR-3.4 (Duplicate Merge)**: If a user adds shares of a stock that already exists in the selected portfolio, the system shall prompt the user to merge the lots, computing the exact weighted-average cost basis and new combined share total.
- **FR-3.5**: Users can edit existing holdings with pre-populated dialogs. Modal dialogs must construct and position all UI controls prior to grabbing focus to eliminate blank window rendering.
- **FR-3.6**: Holdings can be deleted individually, via multi-selection (batch delete), context menu, or keyboard shortcuts (`Delete`/`Backspace`), accompanied by confirmation prompts.
- **FR-3.7 (Threshold Alerts)**: Holdings meeting or exceeding target prices shall display a `🎯 Target Hit!` visual badge; positions falling below the stop-loss threshold shall display a `⚠️ Stop Loss!` alert.

### FR-4: Multi-Currency Support & Live FX Conversion Engine
- **FR-4.1**: Holdings may be individually denominated in `USD`, `EUR`, `GBP`, `CAD`, `CNY` (Shanghai/SSE stocks), `HKD`, `JPY`, or `Native`.
- **FR-4.2**: The system shall scrape live FX exchange rates directly from Google Finance (e.g., `CNY-USD`, `CAD-USD`, `EUR-USD`, `GBP-USD`, `HKD-USD`, `JPY-USD`) and cache them locally.
- **FR-4.3**: A global **💱 Summary In** dropdown selector shall dynamically convert all total valuation metrics, cost basis, unrealized P/L, and projected dividends into the chosen target currency in real time while preserving native historical purchase prices.
- **FR-4.4**: An on-screen FX badge shall display the active conversion rate pair, and a manual `🔄 FX` button shall allow immediate rate refreshing.

### FR-5: Visual Analytics & Asset Allocation Engine
- **FR-5.1**: The system shall feature a dedicated `📊 Allocation & Analytics` tab.
- **FR-5.2 (Native Donut Chart)**: Renders a vector-drawn donut allocation chart on a native Tkinter canvas displaying color-coded slices for all assets by market value, center total valuation, and interactive slice legend with percentage weights.
- **FR-5.3 (100% Single Asset Handling)**: In portfolios with only one holding or where one asset occupies 100% weight, the chart engine shall draw a complete 360° ring without zero-division errors.
- **FR-5.4 (Duplicate Asset Consolidation)**: In consolidated views, identical ticker symbols held across multiple portfolios (e.g., `VOO` held in both `USD HSBC` and `USD RRSP`) shall be mathematically combined into a single aggregated position showing true portfolio-wide concentration.
- **FR-5.5 (Portfolio Health & Concentration KPIs)**: Displays real-time metrics for:
  - Top Position Symbol & Weight (%)
  - Portfolio Concentration (%)
  - Portfolio Yield on Cost (YoC %)
  - Overall Dividend Yield (%)
  - Best Performing Asset (Symbol & Gain %)
  - Worst Performing Asset (Symbol & Loss %)
- **FR-5.6 (Ranked Position Table)**: Displays a ranked breakdown of all holdings sorted descending by portfolio weight.

### FR-6: Interactive Google Finance Historical Chart
- **FR-6.1**: The system shall feature a dedicated `📉 Interactive Chart` tab replicating the Google Finance interactive experience.
- **FR-6.2**: The chart scope shall support charting either the entire consolidated portfolio, a specific sub-portfolio, or any individual holding.
- **FR-6.3 (Scope Deduplication)**: When "All Portfolios" is selected, the ticker scope dropdown must deduplicate symbols so that each unique stock/ETF appears only once.
- **FR-6.4**: Support multiple time horizons: `1D`, `5D`, `1M`, `6M`, `YTD`, `1Y`, `5Y`, and `MAX`.
- **FR-6.5**: Support multiple visual rendering styles: `Area` (gradient fill), `Line`, and `Candle`.

### FR-7: Financial Calculators Suite
- **FR-7.1 (Dividend & DRIP Calculator)**:
  - Calculates Annual Dividend, Quarterly Dividend, Monthly Cash Flow, and Yield on Cost (YoC %).
  - Simulates DRIP (Dividend Reinvestment Plan) compounding over 1 to 30 years with adjustable annual dividend growth rate, stock price growth rate, and optional recurring cash injections.
  - Features an embedded visual compounding chart comparing Principal Invested vs. Reinvested Dividend Wealth.
- **FR-7.2 (Stock Split & Reverse Split Tool)**:
  - Evaluates forward splits (`2:1`, `3:1`, `4:1`, etc.) and reverse splits (`1:5`, `1:10`, etc.).
  - Calculates post-split shares and adjusted buy price while guaranteeing total cost basis preservation.
  - Provides a 1-click "Apply Split to Portfolio" button that commits adjustments to CSV immediately.
- **FR-7.3 (Selling Calculator & Profit Simulator)**:
  - Simulates gross proceeds, broker commissions (flat + percentage), and capital gains tax liabilities (custom rates or preset tax brackets: `0%`, `15%`, `20%`, `28%`).
  - Computes net proceeds, net realized capital gain/loss, and net ROI (%).
  - Provides Breakeven Sell Price solver and Target Profit solver (calculates required selling price per share).
  - Executing a sale automatically deducts shares from active inventory and appends a `SELL` record to the transaction history.

### FR-8: Full Transaction History System
- **FR-8.1**: The system shall log both **BUY** (purchases) and **SELL** (sales) trades in `transaction_history.csv`.
- **FR-8.2**: Stock additions via `➕ Add Stock` or lot merges shall automatically generate a `BUY` record. Executed sales shall automatically generate a `SELL` record.
- **FR-8.3 (Dual Dynamic Filtering)**: Users can filter transaction records simultaneously by:
  - **Portfolio**: Specific account or `All Portfolios (Consolidated)`.
  - **Transaction Type**: `All Types`, `🟢 BUY (Purchases)`, or `🔴 SELL (Sales)`.
- **FR-8.4**: Filtering updates table rows instantly and recalculates total realized sales profit and transaction counts.
- **FR-8.5 (Manual Transaction Entry)**: Users can manually record trades with an optional checkbox to adjust active portfolio inventory accordingly.
- **FR-8.6 (Seamless Migration)**: Legacy `sales_history.csv` records shall automatically import as `SELL` records upon first launch with zero data loss.

### FR-9: Google Finance Account Sync & CSV Interoperability
- **FR-9.1 (Session Cookie Sync)**: Allows synchronization with a user's personal Google Finance account via portfolio URL and browser session cookie.
- **FR-9.2 (CSV Import/Export)**:
  - Import Google Finance CSV downloads ("Download list") with automatic column mapping.
  - Export CSVs formatted specifically for re-upload to Google Finance (`Symbol`, `Name`, `Shares`, `Purchase price`, `Currency`).
  - Export standard application CSV backups anytime.
- **FR-9.3 (Executive HTML Reports)**: Generates printable, self-contained executive HTML reports (`portfolio_report.html`) complete with valuation summaries, KPI cards, holdings tables, and sales histories.

### FR-10: Automatic 5-File CSV Rolling Backup & Rotation System
- **FR-10.1**: Every time a CSV file (`portfolio.csv`, `transaction_history.csv`, or `sales_history.csv`) is modified or saved, the system shall maintain a rolling sequence of exactly **5 backups** stored in a `backups/` directory.
- **FR-10.2**: Backups shall follow the standard rotating log nomenclature:
  - `<filename>.1`: Most recent prior version.
  - `<filename>.2` through `<filename>.4`: Intermediate prior versions.
  - `<filename>.5`: Oldest retained version.
- **FR-10.3**: On the 6th save event, `<filename>.5` is automatically deleted, slots shift (`4` -> `5`, `3` -> `4`, `2` -> `3`, `1` -> `2`), and the current version becomes slot `1`.
- **FR-10.4**: Empty (0 byte) or newly initialized files shall not generate redundant empty backups.
- **FR-10.5 (Restoration Engine)**: Users can restore any CSV file to any of its 5 prior backup states via a GUI dialog. An automatic safety backup of the current state must be created prior to applying the restore.
- **FR-10.6 (GUI Backups Manager)**: Top bar button `🔄 Backups` provides a visual list of backup slots, timestamps, file sizes, a 1-click restore button, and an "Open Folder" button.

### FR-11: Multi-Language Internationalization (i18n)
- **FR-11.1**: The system shall support three core languages:
  - **English (`en`)**: Default international standard.
  - **Traditional Chinese (`zh_TW` - 繁體中文)**: Hong Kong & Taiwan financial terminology standard.
  - **Simplified Chinese (`zh_CN` - 简体中文)**: Mainland China financial terminology standard.
- **FR-11.2**: Translation dictionary must maintain 100% key parity across all languages (all keys defined in `en` must exist in `zh_TW` and `zh_CN`).
- **FR-11.3 (Dynamic Real-Time UI Switching)**: Changing the language selector in the top bar must immediately translate the entire UI without restarting the application:
  - Window title, headers, and top control buttons.
  - Portfolio bar labels and buttons.
  - All 7 tab titles in the main notebook.
  - Holdings table columns, search labels, filter buttons, table actions, and context menu.
  - Analytics titles, KPI mini cards, and ranked weight table columns.
  - Transaction History filter labels, combobox values, table headers, and action buttons.
  - Backups dialog titles, table headers, and confirmation dialogs.
- **FR-11.4 (Persistent Language Preference)**: Selected language preference must be persisted to `settings.json` and restored on subsequent application launches.
- **FR-11.5 (Multilingual Filter Normalization)**: Portfolio dropdown selections and transaction type filters must gracefully recognize translated strings (e.g. `所有投資組合 (合併匯總)`, `買入`, `賣出`) to prevent data filtering dropouts.

### FR-12: Instant Clean Exit & Process Termination
- **FR-12.1**: When the GUI window is closed by clicking `✕`, the application and terminal CLI process must terminate **instantly**.
- **FR-12.2**: All background workers (quote scrapers, FX converters, chart fetchers) must check a thread-safe cooperative cancellation flag (`self.is_running`) and terminate loops immediately upon shutdown.
- **FR-12.3**: `on_close` must break Tkinter's `mainloop()` using `root.quit()` and release widget resources with `root.destroy()`.
- **FR-12.4**: Background thread pools and unclosed HTTP connections must be explicitly unblocked, followed by `os._exit(0)` to prevent the Python interpreter from hanging in terminal sessions.

---

## 3. Non-Functional Requirements (NFR)

### NFR-1: Performance & Responsiveness
- All network interactions, web scraping, and long-running mathematical simulations must run in background daemon threads.
- The UI thread must maintain 60 FPS responsiveness during data refreshes and user interactions.
- Full test suite execution across all modules must complete in under 1 second.

### NFR-2: Zero Cloud Lock-In & Local-First Architecture
- 100% of user data (holdings, transactions, settings) must reside locally in standard CSV and JSON files.
- No external database servers (SQLite, MySQL, Postgres) or cloud databases are required.
- The application must operate with full calculation and simulation capabilities even when offline.

### NFR-3: Reliability, Data Integrity & Safety
- All CSV write operations must employ rolling backup protection before overwriting files on disk.
- Restoration operations must always create a safety backup of current data first.
- Exception handlers must catch network timeouts, Google Finance layout changes, and invalid symbols without crashing the application.

### NFR-4: User Experience & Design Consistency
- Support both **Modern Light Mode** (clean Google-style aesthetic) and **High-Contrast Dark Mode** (charcoal #202124 background).
- Visual color coding for financial metrics: Emerald Green (`#0d904f`) for gains, Crimson Red (`#d93025`) for losses, Royal Blue (`#1a73e8`) for primary actions.
- Bi-directional sorting on all table columns with visual indicators (`▲`/`▼`).
- Keyboard shortcuts: `Delete`/`Backspace` to remove holdings, `<Escape>` to dismiss modals.

### NFR-5: Modular Code Architecture
- Strict separation of concerns across dedicated modules:
  - `main_gui.py`: Presentation layer, Tkinter UI layout, event handling, dynamic i18n switching.
  - `i18n.py`: Internationalization dictionary, locale state management, interpolation, persistence.
  - `financial_calc.py`: Pure mathematical engines for financial calculations, DRIP simulations, and asset aggregation.
  - `csv_manager.py`: File I/O, multi-portfolio filtering, transaction history management, and rolling backup rotation.
  - `currency_converter.py`: Live FX rate fetching, caching, and currency conversion logic.
  - `chart_canvas.py`: Native Tkinter canvas drawing routines (donut charts, DRIP compounding charts).
  - `chart_view.py`: Google Finance historical interactive chart viewer.
  - `google_finance_fetcher.py`: Web scraping and quote retrieval engine.
  - `google_account_sync.py`: Live Google Finance portfolio and session sync.
  - `report_generator.py`: Executive HTML and print-to-PDF report generator.

### NFR-6: Test Automation & Verification
- Unit test suite (`test_suite.py`) must validate:
  - Holding valuation and dividend calculations.
  - DRIP compounding simulations.
  - Stock split ratio math and basis preservation.
  - Selling proceeds, capital gains taxes, and breakeven prices.
  - Multi-portfolio CSV persistence and lot merging.
  - Google Account Sync HTML parsing and symbol extraction.
  - Currency conversion and multi-currency metrics.
  - Multi-lot asset aggregation across portfolios.
  - Transaction history BUY/SELL roundtrip logging and filtering.
  - 5-file rolling backup rotation and 1-click restoration.
  - Tri-lingual translation key parity, retrieval, interpolation, and settings persistence.

---

## 4. Data Models & File Schemas

### 4.1. `portfolio.csv`
Active investment inventory.
```csv
portfolio,symbol,name,currency,shares,buy_price,current_price,change,market_value,cost_basis,unrealized_gain,unrealized_gain_pct,div_yield,annual_dividend,last_updated,target_price,stop_loss
```

### 4.2. `transaction_history.csv`
Complete ledger of all BUY and SELL transactions.
```csv
date,type,portfolio,symbol,currency,shares,price,total_amount,commission,tax,net_profit,roi,notes
```

### 4.3. `settings.json`
Application user preferences and locale.
```json
{
  "language": "en"
}
```

### 4.4. `config.json`
Google Finance live synchronization configuration.
```json
{
  "portfolio_url": "https://www.google.com/finance/beta/portfolio/...",
  "cookie": "SID=...; HSID=...;"
}
```

---

## 5. Traceability Matrix & Implementation Verification

| Requirement ID | Description | Source Module(s) | Verification Test | Status |
| :--- | :--- | :--- | :--- | :--- |
| **FR-1** | Real-Time Market Data Receiver | `google_finance_fetcher.py` | Unit & Live Fetch Tests | **Verified** |
| **FR-2** | Multi-Portfolio Segmentation | `csv_manager.py`, `main_gui.py` | `TestCSVManager` | **Verified** |
| **FR-3** | Stock Inventory & Merging | `main_gui.py`, `financial_calc.py` | `TestFinancialCalculations` | **Verified** |
| **FR-4** | Multi-Currency & Live FX | `currency_converter.py` | `TestCurrencyConverter` | **Verified** |
| **FR-5** | Allocation Analytics & Donut | `chart_canvas.py`, `financial_calc.py` | `TestPortfolioAnalytics` | **Verified** |
| **FR-6** | Interactive Historical Chart | `chart_view.py`, `chart_fetcher.py` | `TestChartScopeDeduplication` | **Verified** |
| **FR-7.1** | Dividend & DRIP Simulator | `financial_calc.py` | `test_drip_simulation` | **Verified** |
| **FR-7.2** | Stock Split & Basis Math | `financial_calc.py` | `test_stock_split` | **Verified** |
| **FR-7.3** | Selling Proceeds & Tax Solver | `financial_calc.py` | `test_selling_proceeds` | **Verified** |
| **FR-8** | Transaction History (BUY/SELL) | `csv_manager.py`, `main_gui.py` | `TestTransactionHistory` | **Verified** |
| **FR-9** | Google Sync & HTML Reports | `google_account_sync.py`, `report_generator.py` | `TestGoogleAccountSync` | **Verified** |
| **FR-10** | 5-File Rolling Backups | `csv_manager.py`, `main_gui.py` | `TestRollingBackups` | **Verified** |
| **FR-11** | Tri-Lingual i18n Engine | `i18n.py`, `main_gui.py` | `TestI18nSupport` | **Verified** |
| **FR-12** | Clean Process Termination | `app.py`, `main_gui.py`, `chart_view.py` | Process Exit Audit | **Verified** |

---
*End of Software Requirements Document.*
