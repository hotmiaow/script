# Google Finance Portfolio Tracker & Financial Calculator

A Python desktop GUI application that auto-receives live stock and market information directly from Google Finance, provides dividend & DRIP projections, stock division/split calculators, selling proceeds & profit simulations, and saves all data to CSV.

---

## Features

### 1. Google Finance Account Sync
- **Live Session Sync**: Synchronize directly with your personal Google Finance account using your session cookie and portfolio/watchlist URL.
- **Google Finance CSV Import**: One-click import of watchlist or portfolio lists downloaded from Google Finance ("Download list").
- **Google Finance CSV Export**: Generate CSV files specifically formatted for Google Finance (`Symbol`, `Name`, `Shares`, `Purchase price`, `Currency`).
- **Connection Diagnostics**: Built-in connection tester to check session validity.
- **Built-in Guide**: Step-by-step instructions on copying your portfolio URL and cookies or downloading CSV files from Google Finance.

### 2. Streamlined Stock & Asset Management
- **Add Stock / Asset**:
  - Live **🔍 Lookup** button: verifies symbol on Google Finance in real time and retrieves company name, live price, currency, and dividend metrics.
  - **⚡ Use Live Price** button: instantly populates buy price with the current market quote.
  - Asset Classification: Stock, ETF, Crypto, Mutual Fund, Index, Other.
  - Smart Duplicate Handling: Automatically prompts to merge additional shares into existing positions with weighted average cost basis calculations.
- **Remove Stock / Asset**:
  - Prominent **➖ Remove Stock** button in the top action bar.
  - Multi-select support: delete single or multiple holdings simultaneously.
  - **Right-Click Context Menu**: Edit, Remove, Refresh Quote, or Send directly to Dividend/Split/Selling calculators.
  - Keyboard Shortcuts: Press `Delete` or `Backspace` to quickly remove selected stocks.

### 3. Live Google Finance Auto-Receiver
- **Real-Time Data**: Fetches current share prices, day changes, percentage changes, company names, dividend yields (%), quarterly & annual dividends, ex-dividend dates, and P/E ratios directly from Google Finance.
- **Exchange Detection**: Automatically detects symbols across NASDAQ, NYSE, NYSEARCA, BATS, etc. (e.g. `AAPL`, `MSFT:NASDAQ`, `KO:NYSE`, `SPY`).
- **Configurable Auto-Refresh**: Background daemon thread polls live quotes at your preferred interval (`Off`, `15s`, `30s`, `1 min`, `2 min`, `5 min`) or via instant manual refresh without freezing the user interface.

### 2. Live Portfolio Holdings & Watchlist
- Responsive summary metric cards:
  - **Portfolio Value**: Total current value of all holdings.
  - **Cost Basis**: Total invested capital.
  - **Unrealized P/L**: Dollar and percentage profit/loss with dynamic green/red indicators.
  - **Projected Annual Dividend**: Total expected dividend income.
  - **Monthly Dividend Average**: Average monthly dividend cashflow.
- Add, Edit, and Delete holdings with an automatic duplicate merge option (weighted average buy price).
- One-click transfer buttons to send any holding into the Dividend, Split, or Selling calculators.

### 3. Dividend & DRIP Calculator ("Division")
- Computes:
  - **Annual Dividend Total ($)**
  - **Quarterly Dividend ($)**
  - **Monthly Cashflow ($)**
  - **Yield on Cost (YoC %)** based on purchase price vs current yield.
- **DRIP (Dividend Reinvestment Plan) Simulator**:
  - Compounding simulation across 1 to 30 years.
  - Configurable dividend growth rate (%/yr) and stock price appreciation (%/yr).
  - Optional recurring monthly contributions.
  - Generates year-by-year projections of share accumulation and portfolio compounding.

### 4. Stock Division / Split Tool
- Evaluates stock splits (forward splits e.g. `2:1`, `3:1`, `4:1`, `10:1` or reverse splits e.g. `1:5`, `1:10`) and custom split ratios.
- Compares pre-split vs. post-split share count and cost basis per share while verifying total value preservation.
- **Apply Split to Portfolio** button: Automatically adjusts the holding in your portfolio and saves to CSV with a single click.

### 5. Selling Calculator & Profit Simulator
- Simulates selling orders:
  - Quick share sizing buttons: `25%`, `50%`, `75%`, `100%` of holding.
  - Broker commissions (flat fee and/or percentage fee).
  - Capital gains tax estimation (supports tax-exempt `0%`, `15% Long-Term`, `20% High Bracket`, `28% Short-Term`, or custom `%`).
  - Calculates Gross Proceeds, Net Proceeds, Realized Capital Gain, Tax Liability, Net Profit, and Net ROI (%).
- **Breakeven & Target Profit Tools**:
  - Automatically calculates the exact sell price required to break even after all broker fees.
  - Target Profit solver: finds required selling price per share to achieve a desired net dollar profit.
- **Record Sale & Deduct Shares**:
  - Appends the executed transaction to `sales_history.csv`.
  - Automatically deducts the sold shares from `portfolio.csv` (or removes the holding if completely closed).

### 6. CSV Persistence & Import/Export
- **`portfolio.csv`**: Auto-saves your active portfolio holdings after every edit, split, sale, or quote refresh.
- **`sales_history.csv`**: Automatically maintains a transaction log of all recorded sales with dates, proceeds, and realized profits.
- **Import / Export**: Dedicated UI buttons to import custom portfolio CSV files or export timestamped CSV copies anytime.

---

## File Structure

```
/home/keith/gemini/G_Finance/
├── app.py                      # Application launcher entrypoint
├── main_gui.py                 # Main Tkinter desktop GUI (5 tabs, cards, auto-updater)
├── google_finance_fetcher.py   # Google Finance live parser & exchange resolver
├── financial_calc.py           # Financial calculation engine (dividends, splits, sales, DRIP)
├── csv_manager.py              # CSV save/load/append manager
├── test_suite.py               # Unit tests verifying calculations and CSV operations
├── portfolio.csv               # Live portfolio holdings data
└── sales_history.csv           # Sales & trade history log
```

---

## Quick Start

To launch the application:
```bash
python3 app.py
```
or
```bash
python3 main_gui.py
```

To run the automated tests:
```bash
python3 test_suite.py
```
