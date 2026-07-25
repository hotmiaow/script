---
name: trade-with-congress
description: Analyze stock trading performance of U.S. Senators and Representatives by retrieving Congressional stock disclosures and comparing trade dates with historical price data. Use when the user asks to analyze Congressional stock trades, check whether Senators are earning or losing money on their stock transactions, track recent political trades, or compare politician stock trades with market data.
---

# Trade with Congress

This skill fetches disclosures of Congressional stock trades (both Senate and House) and compares them with historical stock closing prices from Yahoo Finance to determine the performance of individual trades (earning or losing).

## Quick Start

To run a default analysis on Senate stock trades from the last 2 years, use the following command:

```bash
python3 /home/keith/.agents/skills/trade-with-congress/scripts/senate_tracker.py --years 2 --chamber senate
```

This will:
1. Fetch recent Senate transactions.
2. Download corresponding historical closing prices from Yahoo Finance.
3. Classify each trade:
   - **Purchases** are "Earning" if the stock price increased since the trade date.
   - **Sales** are "Earning" if the stock price decreased after the trade date (indicating losses avoided or profit locked in at a high point).
4. Run a **First-In-First-Out (FIFO) lot-matching engine** to track portfolios, holding durations, and matching sales.
5. Save a detailed Markdown report (`senate_trading_report_YYYYMMDD_HHMMSS.md`) in the current directory.

## Workflows

### 1. General Analysis
- [ ] Run the analyzer for the default period of 2 years:
  ```bash
  python3 /home/keith/.agents/skills/trade-with-congress/scripts/senate_tracker.py --years 2 --chamber both
  ```
- [ ] Inspect the console output for overall win rate and the Senator leaderboard.
- [ ] Open the generated `.md` report for a complete detailed transaction log.

### 2. Filter by Senator
- [ ] Check performance for a specific Senator (e.g., "Tuberville"):
  ```bash
  python3 /home/keith/.agents/skills/trade-with-congress/scripts/senate_tracker.py --senator "Tuberville"
  ```

### 3. Filter by Ticker
- [ ] Check trades and performance for a specific stock (e.g., "Nvidia" / "NVDA"):
  ```bash
  python3 /home/keith/.agents/skills/trade-with-congress/scripts/senate_tracker.py --ticker NVDA
  ```

### 4. Custom Chamber Analysis
- [ ] Target either `senate`, `house`, or `both` using the `--chamber` argument:
  ```bash
  python3 /home/keith/.agents/skills/trade-with-congress/scripts/senate_tracker.py --chamber both --years 1.5
  ```

## Advanced Features & Performance Details

### Earning vs. Losing Formula
The performance metrics evaluate whether a trade was advantageous based on transaction type:
- **Purchase (Buy):**
  $$\text{Return \%} = \frac{P_{\text{latest}} - P_{\text{trade}}}{P_{\text{trade}}} \times 100$$
  *Positive return $\rightarrow$ Earning 🟢; Negative return $\rightarrow$ Losing 🔴*
- **Sale (Sell):**
  $$\text{Return \%} = \frac{P_{\text{trade}} - P_{\text{latest}}}{P_{\text{trade}}} \times 100$$
  *Positive return $\rightarrow$ Earning 🟢 (successfully sold before a decline); Negative return $\rightarrow$ Losing 🔴 (stock continued to rise after selling)*

### FIFO Lot Matching & Portfolio Tracking
The tracker runs a chronological FIFO ledger to pair purchases and sales:
- **Holding Period:** Measures the exact duration (in days) between matching buy and sell transaction lots.
- **Current Holdings:** Open buy lots that haven't been offset by a corresponding sale are tracked to show exactly what filers currently hold according to the public record.
- **Top 20 Transactions Detailed Tracking:** The report lists the top 20 largest purchases and sells by estimated midpoint value, showing:
  - For Purchases: Status (Holding, Partially Sold, Fully Sold), days held, matching sales, and remaining estimated value.
  - For Sells: Matched buy dates/prices, hold durations, realized gains, and remaining filer portfolio holdings in that stock.

### Local Database Storage & Incremental Syncing
To support fast bootstrap analysis and bypass remote query limits, the skill maintains a local database file `resources/trades_historical.json`.
- **Bootstrapping:** On its initial run, the script automatically pulls individual history files for all 400+ filers in parallel, consolidating over 50,000 trades dating back to **January 2015**.
- **Incremental Updates:** On subsequent runs, it queries the local database and performs a fast incremental sync to download only new/missing trades from the online feed.

### Error Resilience
- **Akamai Firewall Bypass:** The script automatically attempts to scrape live data directly from `efdsearch.senate.gov/search/report/data/` using cookies and terms-acceptance handshakes. If blocked by the Akamai bot protection system (returning a 403 Forbidden), it seamlessly falls back to a clean, daily-updated, pre-compiled Congress trading JSON dataset.
- **Weekend/Holiday Matching:** If a trade occurred on a weekend or public holiday, the analyzer automatically locates and matches the closing price of the next closest active trading business day.
