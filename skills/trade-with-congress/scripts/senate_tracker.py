#!/usr/bin/env python3
"""
Senate Trading Analyzer
Fetches recent Congressional stock trading disclosures and compares them with stock data
to analyze trading performance, popularity trends, portfolios, and holding periods.
"""

import os
import sys
import json
import datetime
import argparse
import logging
import urllib.request
import requests
from bs4 import BeautifulSoup
import pandas as pd
import yfinance as yf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("senate_trading_analyzer")

ROOT_URL = 'https://efdsearch.senate.gov'
LANDING_PAGE_URL = f'{ROOT_URL}/search/home/'
SEARCH_PAGE_URL = f'{ROOT_URL}/search/'
REPORTS_URL = f'{ROOT_URL}/search/report/data/'
FALLBACK_DATA_URL = 'https://raw.githubusercontent.com/kadoa-org/congress-trading-monitor/main/public/data/trades.json'

def scrape_senate_direct(start_date: datetime.date) -> list:
    """
    Attempts to scrape recent reports directly from efdsearch.senate.gov.
    Returns a list of raw report entries.
    """
    logger.info("Attempting direct scrape from efdsearch.senate.gov...")
    client = requests.Session()
    client.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    
    # 1. Access landing page to get CSRF token
    try:
        res = client.get(LANDING_PAGE_URL, timeout=10)
    except Exception as e:
        logger.warning(f"Failed to access landing page: {e}")
        return []
        
    if res.status_code == 403:
        logger.warning("Access denied (403) by Akamai bot protection on efdsearch.senate.gov.")
        return []
        
    soup = BeautifulSoup(res.text, 'lxml')
    csrf_input = soup.find('input', attrs={'name': 'csrfmiddlewaretoken'})
    if not csrf_input:
        logger.warning("CSRF token not found on landing page.")
        return []
    token = csrf_input['value']
    
    # 2. Accept terms of service
    agreement_payload = {
        'csrfmiddlewaretoken': token,
        'prohibition_agreement': '1'
    }
    try:
        post_res = client.post(LANDING_PAGE_URL, data=agreement_payload, headers={'Referer': LANDING_PAGE_URL}, timeout=10)
    except Exception as e:
        logger.warning(f"Failed to post terms acceptance: {e}")
        return []
        
    # 3. Query reports from DataTables API endpoint
    csrf_cookie = client.cookies.get('csrftoken') or client.cookies.get('csrf')
    headers = {
        'Referer': SEARCH_PAGE_URL,
        'X-CSRFToken': csrf_cookie
    }
    
    start_date_str = start_date.strftime('%m/%d/%Y 00:00:00')
    query_data = {
        'start': '0',
        'length': '100',
        'report_types': '[11]',  # 11 = Periodic Transaction Report (PTR)
        'filer_types': '[]',
        'submitted_start_date': start_date_str,
        'submitted_end_date': '',
        'candidate_state': '',
        'senator_state': '',
        'office_id': '',
        'first_name': '',
        'last_name': '',
        'csrfmiddlewaretoken': token
    }
    
    logger.info(f"Querying reports filed since {start_date_str}...")
    try:
        res = client.post(REPORTS_URL, data=query_data, headers=headers, timeout=15)
    except Exception as e:
        logger.warning(f"Failed to query reports API: {e}")
        return []
        
    if res.status_code != 200:
        logger.warning(f"Reports API returned status code {res.status_code}")
        return []
        
    try:
        report_data = res.json().get('data', [])
        logger.info(f"Successfully retrieved {len(report_data)} report metadata entries.")
    except Exception as e:
        logger.warning(f"Failed to parse reports JSON: {e}")
        return []
        
    # Now parse individual reports (PTRs) to extract stock transactions
    all_txs = []
    for idx, report in enumerate(report_data):
        first, last, office, link_html, date_received = report
        name = f"{first} {last}".strip()
        link_soup = BeautifulSoup(link_html, 'html.parser')
        link_tag = link_soup.a
        if not link_tag:
            continue
        link_href = link_tag.get('href')
        
        # Skip scanned paper PDFs as they cannot be parsed easily without OCR
        if link_href.startswith('/search/view/paper/'):
            continue
            
        detail_url = f"{ROOT_URL}{link_href}"
        logger.info(f"Parsing report details ({idx+1}/{len(report_data)}): {name} - {date_received}")
        try:
            detail_res = client.get(detail_url, timeout=10)
            if detail_res.url == LANDING_PAGE_URL:
                # Session expired, re-accept agreement
                res = client.get(LANDING_PAGE_URL, timeout=10)
                soup = BeautifulSoup(res.text, 'lxml')
                token = soup.find('input', attrs={'name': 'csrfmiddlewaretoken'})['value']
                client.post(LANDING_PAGE_URL, data={'csrfmiddlewaretoken': token, 'prohibition_agreement': '1'}, headers={'Referer': LANDING_PAGE_URL})
                detail_res = client.get(detail_url, timeout=10)
                
            detail_soup = BeautifulSoup(detail_res.text, 'lxml')
            tbody = detail_soup.find('tbody')
            if not tbody:
                continue
                
            for row in tbody.find_all('tr'):
                cols = [td.get_text().strip() for td in row.find_all('td')]
                if len(cols) < 8:
                    continue
                # cols indices: 0: #, 1: tx_date, 2: Owner, 3: Ticker, 4: Asset Name, 5: Asset Type, 6: Type, 7: Amount, 8: Comment
                tx_date_str, owner, ticker, asset_name, asset_type, tx_type, amount_label = cols[1], cols[2], cols[3], cols[4], cols[5], cols[6], cols[7]
                
                if asset_type != 'Stock' or ticker.strip() in ('--', ''):
                    continue
                    
                # Format dates
                try:
                    tx_date = datetime.datetime.strptime(tx_date_str, '%m/%d/%Y').date()
                    filing_date = datetime.datetime.strptime(date_received, '%m/%d/%Y').date()
                except ValueError:
                    continue
                    
                # Standardize transaction type
                clean_type = "Purchase" if "Purchase" in tx_type else "Sale"
                if "Partial" in tx_type:
                    clean_type = f"{clean_type} (Partial)"
                elif "Full" in tx_type:
                    clean_type = f"{clean_type} (Full)"
                
                # Estimate amount bounds
                amount_low, amount_high = parse_amount_range(amount_label)
                
                all_txs.append({
                    "id": f"scraped_{ticker}_{tx_date.strftime('%Y%m%d')}",
                    "filer_name": name,
                    "chamber": "senate",
                    "transaction_date": tx_date.strftime('%Y-%m-%d'),
                    "filing_date": filing_date.strftime('%Y-%m-%d'),
                    "owner": owner,
                    "ticker": ticker.strip().upper(),
                    "asset_name": asset_name,
                    "asset_type": "Stock",
                    "transaction_type": clean_type,
                    "amount_range_low": amount_low,
                    "amount_range_high": amount_high,
                    "amount_range_label": amount_label,
                    "doc_url": detail_url
                })
        except Exception as e:
            logger.warning(f"Error parsing report detail at {detail_url}: {e}")
            continue
            
    return all_txs

def parse_amount_range(label: str) -> tuple:
    """Parses amount range labels like '$1,001 - $15,000' to numerical values."""
    label = label.replace('$', '').replace(',', '').strip()
    if '-' in label:
        parts = label.split('-')
        try:
            return int(parts[0].strip()), int(parts[1].strip())
        except ValueError:
            return 0, 0
    elif 'Over' in label or 'over' in label:
        try:
            val = int(label.lower().replace('over', '').strip())
            return val, val * 10
        except ValueError:
            return 0, 0
    return 0, 0

LOCAL_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resources')
LOCAL_DB_PATH = os.path.join(LOCAL_DB_DIR, 'trades_historical.json')

def fetch_fallback_data_direct() -> list:
    """Helper to download raw trades.json directly from fallback URL."""
    try:
        req = urllib.request.Request(FALLBACK_DATA_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to fetch fallback dataset directly: {e}")
        return []

def fetch_fallback_data() -> list:
    """
    Loads historical trades from local JSON file.
    If the file does not exist, performs initial bootstrap by downloading
    individual filer JSON files since 2015-01-01 concurrently.
    If the file exists, updates it by pulling the latest trades.json
    and merging any missing transactions.
    """
    os.makedirs(LOCAL_DB_DIR, exist_ok=True)
    
    # 1. Bootstrapping if local file does not exist
    if not os.path.exists(LOCAL_DB_PATH):
        logger.info("Local database not found. Initializing bootstrap since 2015 Jan...")
        try:
            # Download filers list
            filers_url = 'https://raw.githubusercontent.com/kadoa-org/congress-trading-monitor/main/public/data/filers.json'
            logger.info(f"Downloading filers index from {filers_url}...")
            req = urllib.request.Request(filers_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as res:
                filers = json.loads(res.read().decode('utf-8'))
                
            filer_url_template = 'https://raw.githubusercontent.com/kadoa-org/congress-trading-monitor/main/public/data/filer/{}.json'
            all_trades = {}
            
            def process_filer(filer):
                filer_id = filer.get('id')
                if not filer_id:
                    return []
                url = filer_url_template.format(filer_id)
                try:
                    req_f = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req_f, timeout=15) as res_f:
                        data = json.loads(res_f.read().decode('utf-8'))
                        trades = data.get('trades', [])
                        # Normalize trades with filer metadata
                        for t in trades:
                            t['filer_name'] = data.get('filer', {}).get('full_name', filer.get('full_name'))
                            t['chamber'] = data.get('filer', {}).get('chamber', filer.get('chamber'))
                        return trades
                except Exception:
                    return []

            from concurrent.futures import ThreadPoolExecutor, as_completed
            logger.info(f"Fetching trades for {len(filers)} filers in parallel...")
            with ThreadPoolExecutor(max_workers=30) as executor:
                futures = {executor.submit(process_filer, f): f for f in filers}
                for idx, future in enumerate(as_completed(futures)):
                    trades = future.result()
                    for t in trades:
                        tx_id = t.get('id')
                        tx_date = t.get('transaction_date')
                        if tx_id and tx_date and isinstance(tx_date, str) and tx_date >= '2015-01-01':
                            all_trades[tx_id] = t
                            
            trades_list = list(all_trades.values())
            logger.info(f"Bootstrapped {len(trades_list)} trades since 2015-01-01.")
            
            # Save to local file
            with open(LOCAL_DB_PATH, 'w') as f:
                json.dump(trades_list, f, indent=2)
            logger.info(f"Local database saved to {LOCAL_DB_PATH}")
            return trades_list
        except Exception as e:
            logger.error(f"Error during database bootstrap: {e}")
            return fetch_fallback_data_direct()
            
    # 2. Loading and updating local file if it exists
    else:
        logger.info(f"Loading local database from {LOCAL_DB_PATH}...")
        try:
            with open(LOCAL_DB_PATH, 'r') as f:
                local_trades = json.load(f)
            logger.info(f"Loaded {len(local_trades)} trades from local database.")
            
            # Build set of local trade IDs for quick lookup
            local_ids = {t.get('id') for t in local_trades if t.get('id')}
            
            # Fetch recent trades from fallback URL
            logger.info("Checking for new trades online...")
            recent_trades = fetch_fallback_data_direct()
            
            new_trades = []
            for t in recent_trades:
                tx_id = t.get('id')
                tx_date = t.get('transaction_date')
                if tx_id and tx_date and isinstance(tx_date, str) and tx_date >= '2015-01-01':
                    if tx_id not in local_ids:
                        new_trades.append(t)
                        
            if new_trades:
                logger.info(f"Found {len(new_trades)} new trades. Appending to local database...")
                local_trades.extend(new_trades)
                with open(LOCAL_DB_PATH, 'w') as f:
                    json.dump(local_trades, f, indent=2)
                logger.info(f"Local database updated and saved to {LOCAL_DB_PATH}")
            else:
                logger.info("No new trades found online. Database is up to date.")
                
            return local_trades
        except Exception as e:
            logger.error(f"Error loading or updating local database: {e}")
            return fetch_fallback_data_direct()

def get_closest_price(prices_df: pd.DataFrame, ticker: str, target_date: pd.Timestamp) -> tuple:
    """
    Finds the stock closing price on or shortly after target_date.
    Returns (matched_date, price) or (None, None).
    """
    if ticker not in prices_df.columns:
        return None, None
        
    ticker_series = prices_df[ticker].dropna()
    if ticker_series.empty:
        return None, None
        
    # Get all trading dates on or after target_date
    valid_dates = ticker_series.index[ticker_series.index >= target_date]
    if len(valid_dates) == 0:
        # If the target date is after the last available price, check if it matches the last day closely
        last_date = ticker_series.index[-1]
        if (target_date - last_date).days <= 4:
            return last_date, ticker_series.iloc[-1]
        return None, None
        
    matched_date = valid_dates[0]
    # Check if the matched trading date is too far from target (e.g., > 7 days)
    if (matched_date - target_date).days > 7:
        return None, None
        
    return matched_date, ticker_series.loc[matched_date]

def df_to_markdown(df: pd.DataFrame) -> str:
    """Converts a pandas DataFrame to a markdown table string without requiring tabulate."""
    if df.empty:
        return ""
    headers = [str(c) for c in df.columns]
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for _, row in df.iterrows():
        cols = [str(val).replace('\n', '<br>').replace('|', '\\|') for val in row]
        lines.append("| " + " | ".join(cols) + " |")
    return "\n".join(lines)

def analyze_trades(trades: list, start_date: datetime.date) -> pd.DataFrame:
    """
    Compares trade dates to historical stock price performance.
    """
    df = pd.DataFrame(trades)
    if df.empty:
        return df
        
    # Filter by date range
    df['parsed_date'] = pd.to_datetime(df['transaction_date'])
    df = df[df['parsed_date'].dt.date >= start_date]
    
    if df.empty:
        logger.info("No trades found in the specified date range.")
        return df
        
    # Clean tickers
    df['ticker'] = df['ticker'].str.strip().str.upper()
    df = df[df['ticker'].str.isalnum() & (df['ticker'] != '--')]
    
    unique_tickers = df['ticker'].unique().tolist()
    logger.info(f"Found {len(df)} transactions covering {len(unique_tickers)} unique stock tickers.")
    
    # Download historical price data in bulk using yfinance
    logger.info(f"Downloading historical stock prices for {len(unique_tickers)} tickers...")
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    start_str = (start_date - datetime.timedelta(days=10)).strftime('%Y-%m-%d') # add padding for holidays
    
    try:
        market_data = yf.download(unique_tickers, start=start_str, end=today_str, group_by='ticker', progress=False)
    except Exception as e:
        logger.error(f"Error downloading stock prices from yfinance: {e}")
        return pd.DataFrame()
        
    # Standardize columns to get Close prices easily
    close_prices = pd.DataFrame()
    if isinstance(market_data.columns, pd.MultiIndex):
        if market_data.columns.names[0] == 'Price' or 'Close' in market_data.columns.levels[0]:
            close_prices = market_data['Close']
        else:
            close_prices = market_data.xs('Close', axis=1, level=1)
    else:
        ticker_name = unique_tickers[0]
        close_prices = pd.DataFrame({ticker_name: market_data['Close']})
        
    # Ensure index is timezone-naive to avoid comparisons error
    if close_prices.index.tz is not None:
        close_prices.index = close_prices.index.tz_localize(None)
        
    logger.info("Comparing transactions with stock data...")
    results = []
    
    for idx, row in df.iterrows():
        ticker = row['ticker']
        trade_date = row['parsed_date']
        tx_type = row['transaction_type']
        
        # 1. Price at transaction
        match_date, p_trade = get_closest_price(close_prices, ticker, trade_date)
        if p_trade is None or pd.isna(p_trade):
            continue
            
        # 2. Calculate return offsets
        intervals = {
            '30d': trade_date + datetime.timedelta(days=30),
            '90d': trade_date + datetime.timedelta(days=90),
            '180d': trade_date + datetime.timedelta(days=180),
            'current': pd.to_datetime(datetime.date.today())
        }
        
        perf = {}
        for name, target_date in intervals.items():
            _, p_later = get_closest_price(close_prices, ticker, target_date)
            if p_later is not None and not pd.isna(p_later):
                # Calculate return depending on Purchase vs Sale
                if "Purchase" in tx_type or "Buy" in tx_type:
                    # Purchase: positive if stock goes up
                    perf[name] = ((p_later - p_trade) / p_trade) * 100
                else:
                    # Sale: positive if stock goes down (avoided loss/locked in profit before drop)
                    perf[name] = ((p_trade - p_later) / p_trade) * 100
            else:
                perf[name] = None
                
        # Calculate midpoint value for earnings estimation
        low_val = row.get('amount_range_low')
        high_val = row.get('amount_range_high')
        if low_val is None or high_val is None:
            low_val, high_val = parse_amount_range(row.get('amount_range_label', ''))
            
        low_val = float(low_val or 0)
        high_val = float(high_val or 0)
        midpoint = low_val if high_val == 0 else (low_val + high_val) / 2.0
        
        perf_current = perf['current']
        est_profit = midpoint * (perf_current / 100.0) if perf_current is not None else 0.0
        
        results.append({
            'TxID': row.get('id', f"tx_{idx}"),
            'Senator': row['filer_name'],
            'Ticker': ticker,
            'Company': row['asset_name'],
            'Action': tx_type,
            'Date': row['transaction_date'],
            'Low Amount': low_val,
            'High Amount': high_val,
            'Amount Label': row['amount_range_label'],
            'Midpoint Amount': midpoint,
            'Trade Price': round(p_trade, 2),
            'Latest Price': round(close_prices[ticker].dropna().iloc[-1], 2) if ticker in close_prices.columns and not close_prices[ticker].dropna().empty else None,
            'Perf 30D %': round(perf['30d'], 2) if perf['30d'] is not None else None,
            'Perf 90D %': round(perf['90d'], 2) if perf['90d'] is not None else None,
            'Perf 180D %': round(perf['180d'], 2) if perf['180d'] is not None else None,
            'Current Perf %': round(perf['current'], 2) if perf['current'] is not None else None,
            'Estimated Profit': round(est_profit, 2),
            'Link': row['doc_url']
        })
        
    return pd.DataFrame(results)

def get_top_n_stocks(df: pd.DataFrame, days_back: int, tx_filter: str, limit: int = 20) -> pd.DataFrame:
    """
    Finds the top N most traded stocks (buys or sells) in a given timeframe.
    Calculates transaction counts and total estimated volume.
    """
    start_date = pd.to_datetime(datetime.date.today() - datetime.timedelta(days=days_back))
    sub_df = df[
        (df['parsed_date'] >= start_date) & 
        (df['ticker'].str.isalnum()) & 
        (df['ticker'] != '--') & 
        (df['transaction_type'].str.contains(tx_filter, case=False, na=False))
    ]
    if sub_df.empty:
        return pd.DataFrame(columns=['Rank', 'Ticker', 'Company', 'Trade Count', 'Est Volume'])
        
    counts = sub_df['ticker'].value_counts()
    results = []
    
    for rank_idx, ticker in enumerate(counts.index[:limit]):
        count = counts.loc[ticker]
        ticker_group = sub_df[sub_df['ticker'] == ticker]
        company = ticker_group['asset_name'].dropna().iloc[0] if not ticker_group['asset_name'].dropna().empty else "Unknown"
        if len(company) > 35:
            company = company[:32] + "..."
            
        midpoints = []
        for _, row in ticker_group.iterrows():
            low_val = row.get('amount_range_low')
            high_val = row.get('amount_range_high')
            if low_val is None or high_val is None:
                low_val, high_val = parse_amount_range(row.get('amount_range_label', ''))
            low_val = float(low_val or 0)
            high_val = float(high_val or 0)
            midpoints.append(low_val if high_val == 0 else (low_val + high_val) / 2.0)
            
        est_vol = sum(midpoints)
        results.append({
            'Rank': rank_idx + 1,
            'Ticker': ticker,
            'Company': company,
            'Trade Count': count,
            'Est Volume': f"${est_vol:,.0f}"
        })
        
    return pd.DataFrame(results)

def compute_stock_trends(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes trading popularity trends for stocks over 3, 6, 9, and 12-month timeframes.
    """
    intervals = [
        ("Last 3 Months", 90),
        ("Last 6 Months", 180),
        ("Last 9 Months", 270),
        ("Last 1 Year", 365)
    ]
    
    trends = []
    today = datetime.date.today()
    
    for label, days in intervals:
        start_date = pd.to_datetime(today - datetime.timedelta(days=days))
        sub_df = df[df['parsed_date'] >= start_date]
        
        if sub_df.empty:
            trends.append({
                "Timeframe": label,
                "Most Popular Stock": "N/A",
                "Most Bought Stock": "N/A",
                "Most Sold Stock": "N/A"
            })
            continue
            
        # Clean tickers
        sub_df = sub_df[sub_df['ticker'].str.isalnum() & (sub_df['ticker'] != '--')]
        if sub_df.empty:
            trends.append({
                "Timeframe": label,
                "Most Popular Stock": "N/A",
                "Most Bought Stock": "N/A",
                "Most Sold Stock": "N/A"
            })
            continue
            
        def get_formatted_ticker(counts_series):
            if counts_series.empty:
                return "N/A"
            tick = counts_series.index[0]
            count = counts_series.iloc[0]
            company_matches = sub_df[sub_df['ticker'] == tick]['asset_name'].dropna()
            company_name = company_matches.iloc[0] if not company_matches.empty else ""
            if len(company_name) > 30:
                company_name = company_name[:27] + "..."
            return f"**{tick}** ({company_name}) [{count} trades]" if company_name else f"**{tick}** [{count} trades]"
            
        # Most popular (buys + sells)
        popularity = sub_df['ticker'].value_counts()
        most_popular = get_formatted_ticker(popularity)
        
        # Most bought
        buys = sub_df[sub_df['transaction_type'].str.contains('Purchase|Buy', case=False, na=False)]
        buy_counts = buys['ticker'].value_counts()
        most_bought = get_formatted_ticker(buy_counts).replace("trades", "buys")
        
        # Most sold
        sells = sub_df[sub_df['transaction_type'].str.contains('Sale|Sell', case=False, na=False)]
        sell_counts = sells['ticker'].value_counts()
        most_sold = get_formatted_ticker(sell_counts).replace("trades", "sells")
        
        trends.append({
            "Timeframe": label,
            "Most Popular Stock": most_popular,
            "Most Bought Stock": most_bought,
            "Most Sold Stock": most_sold
        })
        
    return pd.DataFrame(trends)

def compute_conviction_buys(analysis_df: pd.DataFrame, leaderboard_df: pd.DataFrame) -> pd.DataFrame:
    """
    Finds stocks bought by successful Senators (with positive overall estimated earnings).
    Ranks them by the number of unique successful buyers and total estimated purchase volume.
    """
    successful_senators = leaderboard_df[leaderboard_df['Numerical Earnings'] > 0]['Senator'].tolist()
    
    # Filter transactions to Purchases by successful senators in the last 1 year
    one_year_ago = (datetime.date.today() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    purchases = analysis_df[
        analysis_df['Senator'].isin(successful_senators) & 
        analysis_df['Action'].str.contains('Purchase|Buy', case=False, na=False) &
        (analysis_df['Date'] >= one_year_ago)
    ]
    
    if purchases.empty:
        return pd.DataFrame()
        
    conv_list = []
    for ticker, group in purchases.groupby('Ticker'):
        unique_buyers = group['Senator'].nunique()
        total_vol = group['Midpoint Amount'].sum()
        avg_return = group['Current Perf %'].mean()
        company = group['Company'].iloc[0]
        
        conv_list.append({
            'Ticker': ticker,
            'Company': company,
            'Successful Buyers Count': unique_buyers,
            'Total Buy Volume Est': total_vol,
            'Avg Return Since Trade %': round(avg_return, 2) if not pd.isna(avg_return) else 0.0
        })
        
    conv_df = pd.DataFrame(conv_list)
    if not conv_df.empty:
        conv_df = conv_df.sort_values(by=['Successful Buyers Count', 'Total Buy Volume Est'], ascending=[False, False])
    return conv_df

def compute_portfolios_and_holdings(analysis_df: pd.DataFrame) -> tuple:
    """
    Performs chronological FIFO lot matching of Purchases and Sales for each filer and stock.
    Returns:
        holding_records_df: DataFrame of matched (closed) trades
        current_holdings_df: DataFrame of open (held) positions
        purchases_registry: Dict mapping TxID to its tracking dict (with remaining amount and matched sales)
        sells_registry: Dict mapping TxID to its tracking dict (with matched buys)
    """
    if analysis_df.empty:
        return pd.DataFrame(), pd.DataFrame(), {}, {}
        
    # Sort chronologically (oldest to newest) to process trades in order of occurrence
    df_sorted = analysis_df.copy()
    df_sorted['parsed_date'] = pd.to_datetime(df_sorted['Date'])
    df_sorted = df_sorted.sort_values(by='parsed_date')
    
    from collections import defaultdict
    queues = defaultdict(list)  # (filer, ticker) -> list of buy lots
    purchases_registry = {}
    sells_registry = {}
    
    matched_records = []
    
    for _, row in df_sorted.iterrows():
        tx_id = row.get('TxID', f"tx_{row.name}")
        filer = row['Senator']
        ticker = row['Ticker']
        tx_date = row['parsed_date']
        action = row['Action']
        midpoint = row['Midpoint Amount']
        price = row['Trade Price']
        label = row['Amount Label']
        company = row['Company']
        
        is_purchase = 'Purchase' in action or 'Buy' in action
        is_sale = 'Sale' in action or 'Sell' in action
        
        if is_purchase:
            buy_lot = {
                'tx_id': tx_id,
                'filer': filer,
                'ticker': ticker,
                'company': company,
                'date': tx_date,
                'price': price,
                'amount_total': midpoint,
                'amount_remaining': midpoint,
                'label': label,
                'latest_price': row['Latest Price'],
                'sales_matched': [],
                'link': row.get('Link', '')
            }
            queues[(filer, ticker)].append(buy_lot)
            purchases_registry[tx_id] = buy_lot
            
        elif is_sale:
            sale_lot = {
                'tx_id': tx_id,
                'filer': filer,
                'ticker': ticker,
                'company': company,
                'date': tx_date,
                'price': price,
                'amount_total': midpoint,
                'amount_remaining': midpoint,
                'label': label,
                'buys_matched': [],
                'link': row.get('Link', '')
            }
            sells_registry[tx_id] = sale_lot
            
            # Match against the active buy queue for this filer and ticker
            active_buys = queues[(filer, ticker)]
            sale_rem = midpoint
            
            while sale_rem > 0 and active_buys:
                buy_lot = active_buys[0]
                matched_amount = min(buy_lot['amount_remaining'], sale_rem)
                
                hold_days = (tx_date - buy_lot['date']).days
                
                # Realized return calculation
                if buy_lot['price'] > 0:
                    ret_pct = ((price - buy_lot['price']) / buy_lot['price']) * 100
                else:
                    ret_pct = 0.0
                    
                est_earnings = matched_amount * (ret_pct / 100.0)
                
                match_info = {
                    'buy_tx_id': buy_lot['tx_id'],
                    'sell_tx_id': tx_id,
                    'buy_date': buy_lot['date'].strftime('%Y-%m-%d'),
                    'sell_date': tx_date.strftime('%Y-%m-%d'),
                    'hold_days': hold_days,
                    'buy_price': buy_lot['price'],
                    'sell_price': price,
                    'matched_amount': matched_amount,
                    'est_earnings': est_earnings,
                    'ret_pct': ret_pct
                }
                
                buy_lot['sales_matched'].append(match_info)
                sale_lot['buys_matched'].append(match_info)
                
                # Record this matched lot for return
                outcome = 'Earning 🟢' if est_earnings > 0 else ('Losing 🔴' if est_earnings < 0 else 'Neutral ⚪')
                matched_records.append({
                    'Senator': filer,
                    'Ticker': ticker,
                    'Company': company,
                    'Buy Date': buy_lot['date'].strftime('%Y-%m-%d'),
                    'Sell Date': tx_date.strftime('%Y-%m-%d'),
                    'Hold Days': hold_days,
                    'Buy Price': buy_lot['price'],
                    'Sell Price': price,
                    'Matched Amount': matched_amount,
                    'Perf %': round(ret_pct, 2),
                    'Estimated Earnings': round(est_earnings, 2),
                    'Sell Amount Label': label,
                    'Outcome': outcome,
                    'Buy TxID': buy_lot['tx_id'],
                    'Sell TxID': tx_id
                })
                
                buy_lot['amount_remaining'] -= matched_amount
                sale_rem -= matched_amount
                
                if buy_lot['amount_remaining'] <= 0.01:
                    active_buys.pop(0)
                    
            if sale_rem > 0:
                sale_lot['unmatched_amount'] = sale_rem

    # Collect all outstanding (open) holdings
    current_holdings = []
    for (filer, ticker), active_buys in queues.items():
        for buy in active_buys:
            if buy['amount_remaining'] <= 0.01:
                continue
                
            latest_price = buy['latest_price']
            days_held = (pd.to_datetime(datetime.date.today()) - buy['date']).days
            
            if buy['price'] > 0 and latest_price is not None:
                unrealized_return = ((latest_price - buy['price']) / buy['price']) * 100
            else:
                unrealized_return = 0.0
                
            unrealized_earnings = buy['amount_remaining'] * (unrealized_return / 100.0)
            
            status = 'Holding 🔵' if buy['amount_remaining'] == buy['amount_total'] else 'Holding (Partial) 🟡'
            est_val_label = f"${buy['amount_remaining']:,.0f}" if buy['amount_remaining'] != buy['amount_total'] else buy['label']
            
            current_holdings.append({
                'Senator': filer,
                'Ticker': ticker,
                'Company': buy['company'],
                'Purchase Date': buy['date'].strftime('%Y-%m-%d'),
                'Days Held': days_held,
                'Purchase Price': buy['price'],
                'Latest Price': latest_price,
                'Remaining Amount': buy['amount_remaining'],
                'Original Amount': buy['amount_total'],
                'Est Value': est_val_label,
                'Current Perf %': round(unrealized_return, 2) if latest_price is not None else 0.0,
                'Status': status,
                'Unrealized Earnings': round(unrealized_earnings, 2) if latest_price is not None else 0.0,
                'Purchase TxID': buy['tx_id']
            })
            
    if not matched_records:
        holding_periods_df = pd.DataFrame(columns=['Senator', 'Ticker', 'Company', 'Buy Date', 'Sell Date', 'Hold Days', 'Buy Price', 'Sell Price', 'Matched Amount', 'Perf %', 'Estimated Earnings', 'Sell Amount Label', 'Outcome', 'Buy TxID', 'Sell TxID'])
    else:
        holding_periods_df = pd.DataFrame(matched_records)
        
    if not current_holdings:
        portfolios_df = pd.DataFrame(columns=['Senator', 'Ticker', 'Company', 'Purchase Date', 'Days Held', 'Purchase Price', 'Latest Price', 'Remaining Amount', 'Original Amount', 'Est Value', 'Current Perf %', 'Status', 'Unrealized Earnings', 'Purchase TxID'])
    else:
        portfolios_df = pd.DataFrame(current_holdings)
    
    return holding_periods_df, portfolios_df, purchases_registry, sells_registry

def main():
    parser = argparse.ArgumentParser(description="Analyze Senate Stock Trades Performance")
    parser.add_argument('--years', type=float, default=None, help="Number of years of trading history to analyze (default: since 2015 Jan)")
    parser.add_argument('--senator', type=str, default=None, help="Filter results by Senator name (partial match, case-insensitive)")
    parser.add_argument('--ticker', type=str, default=None, help="Filter results by stock ticker symbol")
    parser.add_argument('--chamber', type=str, choices=['senate', 'house', 'both'], default='senate', help="Chamber to analyze (default: senate)")
    parser.add_argument('--output-dir', type=str, default='.', help="Directory to save the markdown or JSON output reports")
    parser.add_argument('--force-scrape', action='store_true', help="Force direct scraping of efdsearch.senate.gov instead of using the fallback API")
    args = parser.parse_args()
    
    # Calculate starting date
    if args.years is not None:
        start_date = datetime.date.today() - datetime.timedelta(days=int(args.years * 365))
        years_label = f"Last {args.years} Years"
    else:
        start_date = datetime.date(2015, 1, 1)
        years_label = "Since Jan 2015"
        
    logger.info(f"Analyzing trades since {start_date.strftime('%Y-%m-%d')} ({years_label})...")
    
    raw_trades = []
    if args.force_scrape:
        raw_trades = scrape_senate_direct(start_date)
        if not raw_trades:
            logger.warning("Scraping returned zero records. Falling back to the database URL.")
            raw_trades = fetch_fallback_data()
    else:
        raw_trades = fetch_fallback_data()
        
    if not raw_trades:
        logger.error("No trading data retrieved. Exiting.")
        sys.exit(1)
        
    if args.chamber != 'both':
        raw_trades = [t for t in raw_trades if t.get('chamber') == args.chamber]
        
    logger.info(f"Loaded {len(raw_trades)} raw trades for {args.chamber}.")
    
    # Parse trade dates for trends computations
    raw_df = pd.DataFrame(raw_trades)
    raw_df['parsed_date'] = pd.to_datetime(raw_df['transaction_date'])
    raw_df['ticker'] = raw_df['ticker'].str.strip().str.upper()
    
    # Compute stock popularity trends
    trends_df = compute_stock_trends(raw_df)
    
    # Pre-compute top buying and selling lists for intervals (now Top 20)
    timeframes = [
        ("Last 3 Months", 90),
        ("Last 6 Months", 180),
        ("Last 9 Months", 270),
        ("Last 1 Year", 365)
    ]
    timeframe_top_stocks = {}
    for label, days in timeframes:
        timeframe_top_stocks[label] = {
            "buy": get_top_n_stocks(raw_df, days, 'Purchase|Buy', limit=20),
            "sell": get_top_n_stocks(raw_df, days, 'Sale|Sell', limit=20)
        }
    
    # Run performance analysis
    analysis_df = analyze_trades(raw_trades, start_date)
    if analysis_df.empty:
        logger.error("No trades analyzed successfully. Exiting.")
        sys.exit(1)
        
    # Apply CLI filters
    if args.senator:
        analysis_df = analysis_df[analysis_df['Senator'].str.contains(args.senator, case=False, na=False)]
    if args.ticker:
        analysis_df = analysis_df[analysis_df['Ticker'] == args.ticker.upper()]
        
    if analysis_df.empty:
        logger.warning("No records matched the filters.")
        sys.exit(0)
        
    analysis_df['Outcome'] = analysis_df['Current Perf %'].apply(
        lambda x: 'Earning 🟢' if x > 0 else ('Losing 🔴' if x < 0 else 'Neutral ⚪') if not pd.isna(x) else 'N/A'
    )
    
    analysis_df = analysis_df.sort_values(by='Date', ascending=False)
    
    # Print Console Summary
    print("\n" + "="*80)
    print(f" CONGRESSIONAL TRADING PERFORMANCE ANALYSIS ({years_label.upper()}) ")
    print("="*80)
    print(f"Total Analyzed Trades: {len(analysis_df)}")
    earning_count = sum(analysis_df['Current Perf %'] > 0)
    losing_count = sum(analysis_df['Current Perf %'] < 0)
    total_valid = earning_count + losing_count
    win_rate = (earning_count / total_valid * 100) if total_valid > 0 else 0
    print(f"Win Rate (Earning Trades / Total Evaluated): {win_rate:.1f}% ({earning_count} Earning, {losing_count} Losing)")
    
    # Senator Performance Leaderboard
    leaderboard = []
    for senator, group in analysis_df.groupby('Senator'):
        group_valid = group.dropna(subset=['Current Perf %'])
        if group_valid.empty:
            continue
        avg_perf = group_valid['Current Perf %'].mean()
        win_count = sum(group_valid['Current Perf %'] > 0)
        tot_count = len(group_valid)
        sen_win_rate = (win_count / tot_count * 100)
        
        tot_earnings = group_valid['Estimated Profit'].sum()
        vol_est = group['Midpoint Amount'].sum()
        
        leaderboard.append({
            'Senator': senator,
            'Total Trades': len(group),
            'Evaluated': tot_count,
            'Win Rate %': round(sen_win_rate, 1),
            'Avg Return %': round(avg_perf, 2),
            'Est Volume': f"${vol_est:,.0f}",
            'Numerical Earnings': tot_earnings,
            'Est Earnings': f"${tot_earnings:,.2f}" if tot_earnings >= 0 else f"-${abs(tot_earnings):,.2f}"
        })
        
    leaderboard_df = pd.DataFrame(leaderboard).sort_values(by='Numerical Earnings', ascending=False)
    disp_leaderboard_cols = ['Senator', 'Total Trades', 'Evaluated', 'Win Rate %', 'Avg Return %', 'Est Volume', 'Est Earnings']
    print("\nSENATOR LEADERBOARD (Ranked by Est Earnings - High to Low):")
    print(leaderboard_df[disp_leaderboard_cols].to_string(index=False))
    
    # Compute conviction buys
    conv_df = compute_conviction_buys(analysis_df, leaderboard_df)
    print("\nCONGRESSIONAL CONVICTION BUY SIGNALS (Stocks bought by successful Senators in the last 1 year):")
    if not conv_df.empty:
        disp_conv_df = conv_df.copy()
        disp_conv_df['Est Purchase Vol'] = disp_conv_df['Total Buy Volume Est'].apply(lambda x: f"${x:,.0f}")
        disp_conv_df = disp_conv_df.drop(columns=['Total Buy Volume Est'])
        print(disp_conv_df.to_string(index=False))
    else:
        print("No conviction buy signals found.")
        
    # Track holdings and portfolios
    holding_periods_df, portfolios_df, purchases_registry, sells_registry = compute_portfolios_and_holdings(analysis_df)
    
    print("\nHOLDING ANALYSIS SUMMARY:")
    if not holding_periods_df.empty:
        avg_hold = holding_periods_df['Hold Days'].mean()
        print(f"Total Matched Sales (Liquidated Lots): {len(holding_periods_df)}")
        print(f"Average Filer Stock Holding Period: {avg_hold:.1f} Days")
    else:
        print("No matched holdings found.")
        
    print(f"Active Outstanding Positions (Current Holdings): {len(portfolios_df)}")
    
    # Print popularity lists preview to console
    print("\nRECENT TOP 3 BOUGHT STOCKS PREVIEW (Last 1 Year):")
    print(timeframe_top_stocks["Last 1 Year"]["buy"].head(3).to_string(index=False))
    print("\nRECENT TOP 3 SOLD STOCKS PREVIEW (Last 1 Year):")
    print(timeframe_top_stocks["Last 1 Year"]["sell"].head(3).to_string(index=False))
    
    # Save Report files
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    md_report_path = os.path.join(args.output_dir, f"senate_trading_report_{timestamp}.md")
    
    # Generate Top 20 Detailed Purchases Report
    purchases_df = analysis_df[analysis_df['Action'].str.contains('Purchase|Buy', case=False, na=False)].copy()
    purchases_df = purchases_df.sort_values(by='Midpoint Amount', ascending=False).head(20)
    
    top_buys_report = []
    for rank, (_, row) in enumerate(purchases_df.iterrows()):
        tx_id = row['TxID']
        buy_detail = purchases_registry.get(tx_id)
        if buy_detail:
            rem_amount = buy_detail['amount_remaining']
            tot_amount = buy_detail['amount_total']
            sold_amount = tot_amount - rem_amount
            status = "Fully Sold 🟢" if rem_amount <= 0.01 else "Holding 🔵" if rem_amount == tot_amount else "Partially Sold 🟡"
            
            matches = buy_detail['sales_matched']
            if matches:
                hold_days_list = [str(m['hold_days']) for m in matches]
                hold_str = ", ".join(hold_days_list) + " days"
                sell_details = []
                for m in matches:
                    sell_details.append(f"${m['matched_amount']:,.0f} sold on {m['sell_date']} @ ${m['sell_price']:.2f}")
                sell_str = "; ".join(sell_details)
            else:
                days_held = (pd.to_datetime(datetime.date.today()) - buy_detail['date']).days
                hold_str = f"{days_held} days"
                sell_str = "None"
                
            top_buys_report.append({
                'Rank': rank + 1,
                'Filer': row['Senator'],
                'Ticker': row['Ticker'],
                'Purchase Date': row['Date'],
                'Purchase Price': f"${row['Trade Price']:.2f}",
                'Value Range': row['Amount Label'],
                'Status': status,
                'Hold Duration': hold_str,
                'Amount Sold (Est)': f"${sold_amount:,.0f}" if sold_amount > 0 else "$0",
                'Remaining (Est)': f"${rem_amount:,.0f}",
                'Matching Sells / Action Details': sell_str
            })
    top_buys_report_df = pd.DataFrame(top_buys_report)

    # Generate Top 20 Detailed Sells Report
    sells_df = analysis_df[analysis_df['Action'].str.contains('Sale|Sell', case=False, na=False)].copy()
    sells_df = sells_df.sort_values(by='Midpoint Amount', ascending=False).head(20)
    
    top_sells_report = []
    for rank, (_, row) in enumerate(sells_df.iterrows()):
        tx_id = row['TxID']
        sell_detail = sells_registry.get(tx_id)
        if sell_detail:
            matches = sell_detail['buys_matched']
            if matches:
                buy_dates = [m['buy_date'] for m in matches]
                buy_prices = [f"${m['buy_price']:.2f}" for m in matches]
                hold_days_list = [str(m['hold_days']) for m in matches]
                buy_date_str = ", ".join(buy_dates)
                buy_price_str = ", ".join(buy_prices)
                hold_str = ", ".join(hold_days_list) + " days"
                gain_pcts = [f"{m['ret_pct']:.1f}%" for m in matches]
                gain_pct_str = ", ".join(gain_pcts)
                tot_gain = sum(m['est_earnings'] for m in matches)
                gain_val_str = f"${tot_gain:,.2f}" if tot_gain >= 0 else f"-${abs(tot_gain):,.2f}"
            else:
                buy_date_str = "Unknown (Pre-window)"
                buy_price_str = "N/A"
                hold_str = "N/A"
                gain_pct_str = "N/A"
                gain_val_str = "N/A"
                
            # Calculate remaining holdings of this ticker for this Senator
            senator = row['Senator']
            ticker = row['Ticker']
            sen_holdings = portfolios_df[(portfolios_df['Senator'] == senator) & (portfolios_df['Ticker'] == ticker)]
            if not sen_holdings.empty:
                tot_held = sen_holdings['Remaining Amount'].sum()
                held_str = f"${tot_held:,.0f} remaining"
            else:
                held_str = "$0 remaining"
                
            top_sells_report.append({
                'Rank': rank + 1,
                'Filer': row['Senator'],
                'Ticker': row['Ticker'],
                'Sell Date': row['Date'],
                'Sell Price': f"${row['Trade Price']:.2f}",
                'Value Range': row['Amount Label'],
                'Matched Buy Date': buy_date_str,
                'Matched Buy Price': buy_price_str,
                'Hold Duration': hold_str,
                'Realized Return': gain_pct_str,
                'Realized Earnings (Est)': gain_val_str,
                'Remaining Holding (Est)': held_str
            })
    top_sells_report_df = pd.DataFrame(top_sells_report)

    # Generate Markdown Artifact Report
    with open(md_report_path, 'w') as f:
        f.write(f"# Congressional Stock Trading Performance, Trends & Buy Signals\n\n")
        f.write(f"**Generated on:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Analysis Window:** {years_label} (since {start_date.strftime('%Y-%m-%d')})\n")
        f.write(f"**Total Trades Analyzed:** {len(analysis_df)}\n")
        f.write(f"**Average Win Rate (Earning Trades):** {win_rate:.1f}% ({earning_count} Earning, {losing_count} Losing)\n\n")
        
        f.write(f"## 📈 Congressional Conviction Buy Signals\n")
        f.write(f"The table below shows stock tickers purchased in the **last 1 year** by successful Senators (those with positive overall trading returns). This represents strong insider conviction signals that may be worth checking out.\n\n")
        if not conv_df.empty:
            disp_conv_df = conv_df.copy()
            disp_conv_df['Est Purchase Vol'] = disp_conv_df['Total Buy Volume Est'].apply(lambda x: f"${x:,.0f}")
            disp_conv_df = disp_conv_df.drop(columns=['Total Buy Volume Est'])
            f.write(df_to_markdown(disp_conv_df) + "\n\n")
        else:
            f.write("No conviction buy signals found.\n\n")
            
        f.write(f"## 💼 Estimated Outstanding Positions (Current Holdings)\n")
        f.write(f"List of stocks currently held by members of Congress based on purchase transactions that haven't been followed by matching full sales.\n\n")
        if not portfolios_df.empty:
            disp_portfolios = portfolios_df.copy()
            # Clean display
            disp_portfolios['Purchase Price'] = disp_portfolios['Purchase Price'].apply(lambda x: f"${x:,.2f}" if x else "N/A")
            disp_portfolios['Latest Price'] = disp_portfolios['Latest Price'].apply(lambda x: f"${x:,.2f}" if x else "N/A")
            disp_portfolios['Current Perf %'] = disp_portfolios['Current Perf %'].apply(lambda x: f"{x:.2f}%" if x is not None else "N/A")
            disp_portfolios['Unrealized Earnings'] = disp_portfolios['Unrealized Earnings'].apply(lambda x: f"${x:,.2f}" if x >= 0 else f"-${abs(x):,.2f}")
            disp_portfolios = disp_portfolios.sort_values(by='Days Held', ascending=False)
            port_disp_cols = ['Senator', 'Ticker', 'Company', 'Purchase Date', 'Days Held', 'Purchase Price', 'Latest Price', 'Est Value', 'Current Perf %', 'Status', 'Unrealized Earnings']
            f.write(df_to_markdown(disp_portfolios[port_disp_cols]) + "\n\n")
        else:
            f.write("No active holdings found.\n\n")
            
        f.write(f"## ⏱️ Matched Trades & Holding Periods\n")
        f.write(f"Shows historical buy-sell pairs representing liquidated stock lots. Measures **how long they held** the stock and the outcome of the sale.\n\n")
        if not holding_periods_df.empty:
            disp_holdings = holding_periods_df.copy()
            disp_holdings['Buy Price'] = disp_holdings['Buy Price'].apply(lambda x: f"${x:,.2f}")
            disp_holdings['Sell Price'] = disp_holdings['Sell Price'].apply(lambda x: f"${x:,.2f}")
            disp_holdings['Perf %'] = disp_holdings['Perf %'].apply(lambda x: f"{x:.2f}%" if x is not None else "N/A")
            disp_holdings['Estimated Earnings'] = disp_holdings['Estimated Earnings'].apply(lambda x: f"${x:,.2f}" if x >= 0 else f"-${abs(x):,.2f}")
            disp_holdings = disp_holdings.sort_values(by='Hold Days', ascending=False)
            hold_disp_cols = ['Senator', 'Ticker', 'Company', 'Buy Date', 'Sell Date', 'Hold Days', 'Buy Price', 'Sell Price', 'Perf %', 'Estimated Earnings', 'Outcome']
            f.write(df_to_markdown(disp_holdings[hold_disp_cols]) + "\n\n")
        else:
            f.write("No matched holding periods found.\n\n")

        f.write(f"## 🏆 Top 20 Largest Purchases Detailed Tracking\n")
        f.write(f"Tracks the top 20 largest individual purchase transactions by dollar volume, showing their current status (Holding, Partially Sold, or Fully Sold), how long they held (or have held to date), how much they have sold, and remaining value.\n\n")
        if not top_buys_report_df.empty:
            f.write(df_to_markdown(top_buys_report_df) + "\n\n")
        else:
            f.write("No purchase data available.\n\n")

        f.write(f"## 🏆 Top 20 Largest Sells Detailed Tracking\n")
        f.write(f"Tracks the top 20 largest individual sell transactions by dollar volume, showing how long the stock was held before selling, realized returns, and current outstanding holdings for the stock.\n\n")
        if not top_sells_report_df.empty:
            f.write(df_to_markdown(top_sells_report_df) + "\n\n")
        else:
            f.write("No sale data available.\n\n")
            
        f.write(f"## 📊 Stock Trading Activity & Popularity Trends\n")
        f.write(f"Shows the most transacted, bought, and sold stock tickers in Congress across multiple timeframes.\n\n")
        f.write(df_to_markdown(trends_df) + "\n\n")
        
        # Top 20 Buying and Selling breakdown for each timeframe
        f.write(f"## 🏆 Top 20 Buying & Selling Stocks Breakdown\n")
        f.write(f"Lists the top 20 most heavily traded stocks by volume and trade count across intervals.\n\n")
        
        for label, _ in timeframes:
            f.write(f"### {label}\n\n")
            f.write(f"#### Top 20 Most Bought Stocks\n")
            buy_df = timeframe_top_stocks[label]["buy"]
            if not buy_df.empty:
                f.write(df_to_markdown(buy_df) + "\n\n")
            else:
                f.write("No buy transactions recorded in this timeframe.\n\n")
                
            f.write(f"#### Top 20 Most Sold Stocks\n")
            sell_df = timeframe_top_stocks[label]["sell"]
            if not sell_df.empty:
                f.write(df_to_markdown(sell_df) + "\n\n")
            else:
                f.write("No sell transactions recorded in this timeframe.\n\n")
        
        f.write(f"## 🥇 Senator Performance Leaderboard\n")
        f.write(f"**Ranked by Total Estimated Earnings** (Gains on Buys + Losses Avoided on Sells) from high to low. Volume and earnings calculations are estimated based on trade range midpoints.\n\n")
        f.write(df_to_markdown(leaderboard_df[disp_leaderboard_cols]) + "\n\n")
        
        f.write(f"## 📝 Detailed Transaction Logs\n")
        f.write(f"Below is a complete log of transactions showing trade price when bought/sold, current price, performance return %, and estimated dollar earnings.\n\n")
        
        # Format transaction list to Markdown
        md_cols = ['Senator', 'Ticker', 'Company', 'Action', 'Date', 'Amount Label', 'Trade Price', 'Latest Price', 'Current Perf %', 'Estimated Profit', 'Outcome', 'Link']
        tx_display_df = analysis_df.copy()
        tx_display_df['Link'] = tx_display_df.apply(lambda r: f"[Original filing]({r['Link']})" if r['Link'] else "N/A", axis=1)
        tx_display_df['Estimated Profit'] = tx_display_df['Estimated Profit'].apply(lambda v: f"${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}")
        f.write(df_to_markdown(tx_display_df[md_cols]) + "\n")
        
    logger.info(f"Markdown report generated successfully at: {md_report_path}")

if __name__ == '__main__':
    main()
