"""
CSV Data Manager
Handles saving and loading portfolio holdings, trade/sale logs, and financial reports.
Includes automatic backups, formatting, and file integrity checks.
"""

import os
import csv
import re
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_CSV = os.path.join(BASE_DIR, "portfolio.csv")
SALES_HISTORY_CSV = os.path.join(BASE_DIR, "sales_history.csv")
TRANSACTION_HISTORY_CSV = os.path.join(BASE_DIR, "transaction_history.csv")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
DEFAULT_MAX_BACKUPS = 5


def parse_day_change_string(raw_chg: Optional[str], current_price: float = 0.0) -> Tuple[Optional[float], Optional[float]]:
    """
    Parses a Day Change string from CSV or web e.g.:
      '+1.25 (+1.50%)' -> (1.25, 1.50)
      '−0.26 (−1.45%)' -> (-0.26, -1.45)
      '+0.11'          -> (0.11, calculated_pct)
      '-2.5%'          -> (calculated_dollar, -2.5)
      '-' or ''        -> (None, None)
    """
    if not raw_chg:
        return None, None
    raw_str = str(raw_chg).strip()
    if raw_str in ("-", "", "N/A", "None", "nan"):
        return None, None

    norm = (
        raw_str.replace("\u2212", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("&minus;", "-")
        .strip()
    )

    chg_val = None
    chg_pct_val = None

    # Check percentage
    m_pct = re.search(r"([+\-]?\s*[\d,]+\.?\d*)\s*%", norm)
    if m_pct:
        try:
            chg_pct_val = float(m_pct.group(1).replace(" ", "").replace(",", ""))
        except ValueError:
            pass

    # Check dollar change
    t_no_pct = re.sub(r"[+\-]?\s*[\d,]+\.?\d*\s*%", "", norm).strip()
    m_chg = re.search(r"([+\-]\s*[$€£¥]?\s*[\d,]+\.?\d+)|([$€£¥]?\s*[+\-]\s*[\d,]+\.?\d+)", t_no_pct)
    if m_chg:
        s = m_chg.group(1) or m_chg.group(2)
        s = re.sub(r"[$€£¥\s,]", "", s)
        try:
            chg_val = float(s)
        except ValueError:
            pass
    elif not m_pct:
        try:
            cleaned = re.sub(r"[^\d.\-+]", "", norm)
            if cleaned:
                chg_val = float(cleaned)
        except ValueError:
            pass

    # Cross calculate if one is present and other is missing
    if chg_val is not None and chg_pct_val is None and current_price > 0 and (current_price - chg_val) > 0:
        chg_pct_val = round((chg_val / (current_price - chg_val)) * 100, 2)
    elif chg_pct_val is not None and chg_val is None and current_price > 0:
        pct_dec = chg_pct_val / 100.0
        prev_p = current_price / (1.0 + pct_dec) if (1.0 + pct_dec) != 0 else current_price
        chg_val = round(current_price - prev_p, 2)

    return chg_val, chg_pct_val


def ensure_workspace_files():
    """Ensure default CSV files exist if not present."""
    if not os.path.exists(PORTFOLIO_CSV):
        save_portfolio([], PORTFOLIO_CSV)
    if not os.path.exists(TRANSACTION_HISTORY_CSV):
        if os.path.exists(SALES_HISTORY_CSV):
            load_transactions(TRANSACTION_HISTORY_CSV)
        else:
            save_transactions([], TRANSACTION_HISTORY_CSV)
    if not os.path.exists(SALES_HISTORY_CSV):
        save_sales_history([], SALES_HISTORY_CSV)


DEFAULT_PORTFOLIO_NAME = "USD HSBC"


def rotate_file_backups(
    filepath: str,
    max_backups: int = DEFAULT_MAX_BACKUPS,
    backup_dir: Optional[str] = None,
) -> bool:
    """
    Creates a rolling backup of the given CSV file before modification, rotating up to max_backups.
    Backups are saved as: <backup_dir>/<filename>.1 ... <filename>.<max_backups>
    where .1 is the newest backup and .<max_backups> is the oldest.
    Returns True if a backup was created, False otherwise.
    """
    if not filepath or not os.path.exists(filepath):
        return False
    try:
        if os.path.getsize(filepath) == 0:
            return False
    except OSError:
        return False

    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(filepath)), "backups")

    try:
        os.makedirs(backup_dir, exist_ok=True)
        basename = os.path.basename(filepath)

        # 1. Purge the oldest backup if it exists at or beyond max_backups
        oldest_backup = os.path.join(backup_dir, f"{basename}.{max_backups}")
        if os.path.exists(oldest_backup):
            try:
                os.remove(oldest_backup)
            except OSError:
                pass

        # 2. Shift existing backups down: (max_backups - 1) -> max_backups, ..., 1 -> 2
        for i in range(max_backups - 1, 0, -1):
            src = os.path.join(backup_dir, f"{basename}.{i}")
            dst = os.path.join(backup_dir, f"{basename}.{i + 1}")
            if os.path.exists(src):
                try:
                    os.replace(src, dst)
                except OSError:
                    pass

        # 3. Copy current file to .1
        newest_backup = os.path.join(backup_dir, f"{basename}.1")
        shutil.copy2(filepath, newest_backup)
        return True
    except Exception as e:
        print(f"Warning: Failed to rotate backup for {filepath}: {e}")
        return False


def get_backup_files(
    filepath: str,
    max_backups: int = DEFAULT_MAX_BACKUPS,
    backup_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Returns existing backups for the given file, ordered 1 (newest) to max_backups (oldest).
    Each entry contains: 'index', 'path', 'filename', 'size_bytes', 'modified_time', 'modified_str'.
    """
    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(filepath)), "backups")
    basename = os.path.basename(filepath)
    results = []
    for i in range(1, max_backups + 1):
        bp = os.path.join(backup_dir, f"{basename}.{i}")
        if os.path.exists(bp):
            try:
                st = os.stat(bp)
                mtime = datetime.fromtimestamp(st.st_mtime)
                results.append({
                    "index": i,
                    "path": bp,
                    "filename": f"{basename}.{i}",
                    "size_bytes": st.st_size,
                    "modified_time": mtime,
                    "modified_str": mtime.strftime("%Y-%m-%d %H:%M:%S"),
                })
            except OSError:
                pass
    return results


def restore_backup(
    filepath: str,
    backup_index: int = 1,
    backup_dir: Optional[str] = None,
    create_safety_backup: bool = True,
) -> bool:
    """
    Restores the specified CSV file from a backup index (1 = newest, 5 = oldest).
    Before restoring, creates a rolling safety backup of the current file if create_safety_backup is True.
    """
    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(filepath)), "backups")
    basename = os.path.basename(filepath)
    src_backup = os.path.join(backup_dir, f"{basename}.{backup_index}")
    if not os.path.exists(src_backup):
        print(f"Backup file {src_backup} not found.")
        return False

    try:
        # Read the backup content first before any rotation modifies backup slots
        with open(src_backup, "rb") as f:
            content = f.read()

        if create_safety_backup:
            rotate_file_backups(filepath, backup_dir=backup_dir)

        with open(filepath, "wb") as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error restoring backup from {src_backup}: {e}")
        return False


def save_portfolio(holdings: List[Dict[str, Any]], filepath: str = PORTFOLIO_CSV) -> bool:
    """
    Saves current portfolio holdings to CSV file.
    Ensures portfolio tag, cost_basis, market_value, and unrealized metrics are calculated.
    Automatically creates rotating backup copies (up to 5) before overwriting.
    """
    rotate_file_backups(filepath, max_backups=DEFAULT_MAX_BACKUPS)
    fieldnames = [
        "Portfolio",
        "Symbol",
        "Name",
        "Shares",
        "Buy Price",
        "Current Price",
        "Day Change",
        "Cost Basis",
        "Market Value",
        "Unrealized P/L ($)",
        "Unrealized P/L (%)",
        "Dividend Yield (%)",
        "Annual Div/Share ($)",
        "Est Annual Div ($)",
        "Currency",
        "Last Updated",
    ]

    try:
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for h in holdings:
                shares = float(h.get("shares", 0.0))
                buy_price = float(h.get("buy_price", 0.0))
                current_price = float(h.get("current_price", buy_price))
                div_yield = float(h.get("dividend_yield", 0.0))
                annual_div_share = float(h.get("annual_div_per_share", 0.0))
                port_name = str(h.get("portfolio", "")).strip() or DEFAULT_PORTFOLIO_NAME

                cost_basis = float(h.get("cost_basis", 0.0))
                if cost_basis <= 0.0 and shares > 0 and buy_price > 0:
                    cost_basis = round(shares * buy_price, 2)
                    h["cost_basis"] = cost_basis

                market_value = float(h.get("market_value", 0.0))
                if market_value <= 0.0 and shares > 0 and current_price > 0:
                    market_value = round(shares * current_price, 2)
                    h["market_value"] = market_value

                unrealized_gain = float(h.get("unrealized_gain", 0.0))
                if unrealized_gain == 0.0 and market_value != cost_basis:
                    unrealized_gain = round(market_value - cost_basis, 2)
                    h["unrealized_gain"] = unrealized_gain

                unrealized_gain_pct = float(h.get("unrealized_gain_pct", 0.0))
                if unrealized_gain_pct == 0.0 and cost_basis > 0 and unrealized_gain != 0.0:
                    unrealized_gain_pct = round((unrealized_gain / cost_basis * 100), 2)
                    h["unrealized_gain_pct"] = unrealized_gain_pct

                if annual_div_share <= 0.0 and div_yield > 0 and current_price > 0:
                    annual_div_share = current_price * (div_yield / 100.0)
                    h["annual_div_per_share"] = annual_div_share

                annual_dividend = float(h.get("annual_dividend", 0.0))
                if annual_dividend <= 0.0 and shares > 0 and annual_div_share > 0:
                    annual_dividend = round(shares * annual_div_share, 2)
                    h["annual_dividend"] = annual_dividend

                chg = h.get("change")
                chg_pct = h.get("change_percent")
                if chg is not None and chg_pct is not None:
                    chg_str = f"{float(chg):+.2f} ({float(chg_pct):+.2f}%)"
                elif chg is not None:
                    chg_str = f"{float(chg):+.2f}"
                elif chg_pct is not None:
                    chg_str = f"{float(chg_pct):+.2f}%"
                else:
                    chg_str = "-"

                writer.writerow({
                    "Portfolio": port_name,
                    "Symbol": h.get("symbol", ""),
                    "Name": h.get("name", h.get("symbol", "")),
                    "Shares": f"{shares:.4f}",
                    "Buy Price": f"{buy_price:.2f}",
                    "Current Price": f"{current_price:.2f}",
                    "Day Change": chg_str,
                    "Cost Basis": f"{cost_basis:.2f}",
                    "Market Value": f"{market_value:.2f}",
                    "Unrealized P/L ($)": f"{unrealized_gain:+.2f}",
                    "Unrealized P/L (%)": f"{unrealized_gain_pct:+.2f}%",
                    "Dividend Yield (%)": f"{div_yield:.2f}%",
                    "Annual Div/Share ($)": f"{annual_div_share:.4f}",
                    "Est Annual Div ($)": f"{annual_dividend:.2f}",
                    "Currency": h.get("currency", "USD").strip().upper() or "USD",
                    "Last Updated": h.get("last_updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                })
        return True
    except Exception as e:
        print(f"Error saving portfolio CSV: {e}")
        return False


def load_portfolio(filepath: str = PORTFOLIO_CSV, portfolio_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Loads portfolio holdings from CSV. Optionally filters by portfolio_name.
    If portfolio_name is None or 'All Portfolios', returns all holdings.
    """
    if not os.path.exists(filepath):
        return []

    holdings = []
    try:
        with open(filepath, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row.get("Symbol", "").strip()
                if not symbol:
                    continue

                port = row.get("Portfolio", "").strip() or DEFAULT_PORTFOLIO_NAME
                is_all = (
                    not portfolio_name
                    or portfolio_name in ("All Portfolios", "All", "*", "All Portfolios (Consolidated)")
                    or "consolidated" in portfolio_name.lower()
                )
                if not is_all and port != portfolio_name:
                    continue

                def _parse_float(val: Optional[str], default: float = 0.0) -> float:
                    if not val:
                        return default
                    cleaned = val.replace("$", "").replace("%", "").replace(",", "").strip()
                    try:
                        return float(cleaned)
                    except ValueError:
                        return default

                shares = _parse_float(row.get("Shares"))
                buy_price = _parse_float(row.get("Buy Price"))
                current_price = _parse_float(row.get("Current Price"), buy_price)
                div_yield = _parse_float(row.get("Dividend Yield (%)"))
                annual_div_share = _parse_float(row.get("Annual Div/Share ($)"))

                cost_basis = round(shares * buy_price, 2)
                market_value = round(shares * current_price, 2)
                unrealized_gain = round(market_value - cost_basis, 2)
                unrealized_gain_pct = round((unrealized_gain / cost_basis * 100), 2) if cost_basis > 0 else 0.0

                if annual_div_share <= 0 and div_yield > 0 and current_price > 0:
                    annual_div_share = current_price * (div_yield / 100.0)
                annual_div = round(shares * annual_div_share, 2)

                raw_chg = row.get("Day Change") or row.get("Change") or row.get("Day Change ($)") or ""
                chg_val, chg_pct_val = parse_day_change_string(raw_chg, current_price)

                holdings.append({
                    "portfolio": port,
                    "symbol": symbol,
                    "name": row.get("Name", symbol),
                    "shares": shares,
                    "buy_price": buy_price,
                    "current_price": current_price,
                    "change": chg_val,
                    "change_percent": chg_pct_val,
                    "cost_basis": cost_basis,
                    "market_value": market_value,
                    "unrealized_gain": unrealized_gain,
                    "unrealized_gain_pct": unrealized_gain_pct,
                    "dividend_yield": div_yield,
                    "annual_div_per_share": annual_div_share,
                    "annual_dividend": annual_div,
                    "currency": row.get("Currency", "USD").strip().upper() or "USD",
                    "last_updated": row.get("Last Updated", ""),
                })
        return holdings
    except Exception as e:
        print(f"Error loading portfolio CSV: {e}")
        return []


def get_portfolio_names(filepath: str = PORTFOLIO_CSV) -> List[str]:
    """
    Returns sorted list of distinct portfolio names present in the CSV file.
    """
    if not os.path.exists(filepath):
        return [DEFAULT_PORTFOLIO_NAME]

    names = set()
    try:
        with open(filepath, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p = row.get("Portfolio", "").strip()
                if p:
                    names.add(p)
    except Exception:
        pass

    if not names:
        names.add(DEFAULT_PORTFOLIO_NAME)
    return sorted(list(names))


def delete_portfolio(portfolio_name: str, filepath: str = PORTFOLIO_CSV) -> bool:
    """
    Deletes all holdings belonging to a specific portfolio.
    """
    all_holdings = load_portfolio(filepath, portfolio_name=None)
    remaining = [h for h in all_holdings if h.get("portfolio") != portfolio_name]
    return save_portfolio(remaining, filepath)


def rename_portfolio(old_name: str, new_name: str, filepath: str = PORTFOLIO_CSV) -> bool:
    """
    Renames a portfolio across all its holdings.
    """
    all_holdings = load_portfolio(filepath, portfolio_name=None)
    for h in all_holdings:
        if h.get("portfolio") == old_name:
            h["portfolio"] = new_name
    return save_portfolio(all_holdings, filepath)


TRANSACTION_FIELDNAMES = [
    "Date",
    "Type",
    "Portfolio",
    "Symbol",
    "Shares",
    "Price ($)",
    "Total Amount ($)",
    "Cost Basis ($)",
    "Commission ($)",
    "Estimated Tax ($)",
    "Net Amount ($)",
    "Net Profit ($)",
    "Net ROI (%)",
    "Currency",
    "Notes",
]


def save_transactions(transactions: List[Dict[str, Any]], filepath: str = TRANSACTION_HISTORY_CSV) -> bool:
    """
    Saves transactions (BUY, SELL, etc.) to CSV file.
    Automatically creates rotating backup copies (up to 5) before overwriting.
    """
    rotate_file_backups(filepath, max_backups=DEFAULT_MAX_BACKUPS)
    try:
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=TRANSACTION_FIELDNAMES)
            writer.writeheader()
            for tx in transactions:
                t_type = str(tx.get("type", "BUY")).strip().upper() or "BUY"
                writer.writerow({
                    "Date": tx.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    "Type": t_type,
                    "Portfolio": tx.get("portfolio", DEFAULT_PORTFOLIO_NAME),
                    "Symbol": str(tx.get("symbol", "")).strip().upper(),
                    "Shares": f"{float(tx.get('shares', 0.0)):.4f}",
                    "Price ($)": f"{float(tx.get('price', 0.0)):.2f}",
                    "Total Amount ($)": f"{float(tx.get('total_amount', 0.0)):.2f}",
                    "Cost Basis ($)": f"{float(tx.get('cost_basis', 0.0)):.2f}",
                    "Commission ($)": f"{float(tx.get('commission_fee', 0.0)):.2f}",
                    "Estimated Tax ($)": f"{float(tx.get('estimated_tax', 0.0)):.2f}",
                    "Net Amount ($)": f"{float(tx.get('net_amount', 0.0)):.2f}",
                    "Net Profit ($)": f"{float(tx.get('net_profit', 0.0)):+.2f}" if t_type == "SELL" else "",
                    "Net ROI (%)": f"{float(tx.get('net_roi_pct', 0.0)):+.2f}%" if t_type == "SELL" else "",
                    "Currency": tx.get("currency", "USD").strip().upper() or "USD",
                    "Notes": tx.get("notes", ""),
                })
        return True
    except Exception as e:
        print(f"Error saving transaction history CSV: {e}")
        return False


def load_transactions(
    filepath: str = TRANSACTION_HISTORY_CSV,
    portfolio_name: Optional[str] = None,
    tx_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Loads transactions from CSV, supporting portfolio and transaction type filtering.
    Automatically migrates existing sales_history.csv if transaction_history.csv is not yet created.
    """
    # Auto-migration if transaction_history.csv does not exist yet
    if filepath == TRANSACTION_HISTORY_CSV and not os.path.exists(filepath):
        if os.path.exists(SALES_HISTORY_CSV):
            sales = load_sales_history(SALES_HISTORY_CSV, portfolio_name=None)
            migrated = []
            for s in sales:
                migrated.append({
                    "date": s.get("date", ""),
                    "type": "SELL",
                    "portfolio": s.get("portfolio", DEFAULT_PORTFOLIO_NAME),
                    "symbol": s.get("symbol", ""),
                    "shares": s.get("shares_to_sell", 0.0),
                    "price": s.get("sell_price", 0.0),
                    "total_amount": s.get("gross_proceeds", 0.0),
                    "cost_basis": s.get("cost_basis", 0.0),
                    "commission_fee": s.get("commission_fee", 0.0),
                    "estimated_tax": s.get("estimated_tax", 0.0),
                    "net_amount": s.get("net_proceeds", 0.0),
                    "net_profit": s.get("net_profit", 0.0),
                    "net_roi_pct": s.get("net_roi_pct", 0.0),
                    "currency": s.get("currency", "USD"),
                    "notes": "Migrated from sales history",
                })
            save_transactions(migrated, filepath)
        else:
            return []

    if not os.path.exists(filepath):
        return []

    def _parse(val: Optional[str], default: float = 0.0) -> float:
        if not val:
            return default
        c = str(val).replace("$", "").replace("%", "").replace(",", "").strip()
        try:
            return float(c)
        except ValueError:
            return default

    transactions = []
    try:
        with open(filepath, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = row.get("Symbol", "").strip().upper()
                if not sym:
                    continue

                port = row.get("Portfolio", "").strip() or DEFAULT_PORTFOLIO_NAME
                is_all_port = (
                    not portfolio_name
                    or portfolio_name in ("All Portfolios", "All", "*", "All Portfolios (Consolidated)")
                    or "consolidated" in str(portfolio_name).lower()
                )
                if not is_all_port and port != portfolio_name:
                    continue

                t_type = row.get("Type", "SELL").strip().upper() or "SELL"
                if tx_type and str(tx_type).upper() not in ("ALL", "ALL TYPES"):
                    # Check matching e.g. "BUY" or "SELL"
                    if str(tx_type).upper() not in t_type:
                        continue

                shares = _parse(row.get("Shares", row.get("Shares Sold")))
                price = _parse(row.get("Price ($)", row.get("Sell Price ($)")))
                tot_amt = _parse(row.get("Total Amount ($)", row.get("Gross Proceeds ($)")))
                if tot_amt == 0.0 and shares > 0 and price > 0:
                    tot_amt = round(shares * price, 2)

                c_basis = _parse(row.get("Cost Basis ($)"))
                if c_basis == 0.0 and t_type == "BUY":
                    c_basis = tot_amt

                comm = _parse(row.get("Commission ($)"))
                tax = _parse(row.get("Estimated Tax ($)"))
                net_amt = _parse(row.get("Net Amount ($)", row.get("Net Proceeds ($)")))
                if net_amt == 0.0:
                    net_amt = (tot_amt - comm - tax) if t_type == "SELL" else (tot_amt + comm)

                net_prof = _parse(row.get("Net Profit ($)"))
                net_roi = _parse(row.get("Net ROI (%)"))
                curr = row.get("Currency", "USD").strip().upper() or "USD"
                notes = row.get("Notes", "").strip()

                transactions.append({
                    "date": row.get("Date", ""),
                    "type": t_type,
                    "portfolio": port,
                    "symbol": sym,
                    "shares": shares,
                    "price": price,
                    "total_amount": tot_amt,
                    "cost_basis": c_basis,
                    "commission_fee": comm,
                    "estimated_tax": tax,
                    "net_amount": net_amt,
                    "net_profit": net_prof,
                    "net_roi_pct": net_roi,
                    "currency": curr,
                    "notes": notes,
                    # Backward compatibility for sales table views
                    "shares_to_sell": shares,
                    "buy_price": round(c_basis / shares, 2) if (shares > 0 and c_basis > 0) else price,
                    "sell_price": price if t_type == "SELL" else 0.0,
                    "gross_proceeds": tot_amt if t_type == "SELL" else 0.0,
                    "net_proceeds": net_amt if t_type == "SELL" else 0.0,
                })
        return transactions
    except Exception as e:
        print(f"Error loading transactions CSV: {e}")
        return []


def append_transaction(tx_data: Dict[str, Any], filepath: str = TRANSACTION_HISTORY_CSV) -> bool:
    """
    Appends a new transaction (BUY or SELL) to transaction_history.csv.
    """
    txs = load_transactions(filepath, portfolio_name=None, tx_type=None)
    if "date" not in tx_data:
        tx_data["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    txs.insert(0, tx_data)
    ok = save_transactions(txs, filepath)

    # If it is a SELL record, also mirror to sales_history.csv for backward compatibility
    if str(tx_data.get("type", "")).upper() == "SELL" and filepath == TRANSACTION_HISTORY_CSV:
        try:
            append_sale_record(tx_data, SALES_HISTORY_CSV)
        except Exception:
            pass

    return ok


def save_sales_history(sales: List[Dict[str, Any]], filepath: str = SALES_HISTORY_CSV) -> bool:
    """
    Saves sales transactions to CSV.
    Automatically creates rotating backup copies (up to 5) before overwriting.
    """
    rotate_file_backups(filepath, max_backups=DEFAULT_MAX_BACKUPS)
    fieldnames = [
        "Date",
        "Portfolio",
        "Symbol",
        "Shares Sold",
        "Buy Price ($)",
        "Sell Price ($)",
        "Gross Proceeds ($)",
        "Cost Basis ($)",
        "Commission ($)",
        "Gross Gain ($)",
        "Tax Rate (%)",
        "Estimated Tax ($)",
        "Net Proceeds ($)",
        "Net Profit ($)",
        "Net ROI (%)",
        "Currency",
    ]

    try:
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for s in sales:
                writer.writerow({
                    "Date": s.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    "Portfolio": s.get("portfolio", DEFAULT_PORTFOLIO_NAME),
                    "Symbol": s.get("symbol", ""),
                    "Shares Sold": f"{float(s.get('shares_to_sell', s.get('shares', 0.0))):.4f}",
                    "Buy Price ($)": f"{float(s.get('buy_price', 0.0)):.2f}",
                    "Sell Price ($)": f"{float(s.get('sell_price', s.get('price', 0.0))):.2f}",
                    "Gross Proceeds ($)": f"{float(s.get('gross_proceeds', s.get('total_amount', 0.0))):.2f}",
                    "Cost Basis ($)": f"{float(s.get('cost_basis', 0.0)):.2f}",
                    "Commission ($)": f"{float(s.get('commission_fee', 0.0)):.2f}",
                    "Gross Gain ($)": f"{float(s.get('gross_gain', 0.0)):+.2f}",
                    "Tax Rate (%)": f"{float(s.get('tax_rate_pct', 0.0)):.2f}%",
                    "Estimated Tax ($)": f"{float(s.get('estimated_tax', 0.0)):.2f}",
                    "Net Proceeds ($)": f"{float(s.get('net_proceeds', s.get('net_amount', 0.0))):.2f}",
                    "Net Profit ($)": f"{float(s.get('net_profit', 0.0)):+.2f}",
                    "Net ROI (%)": f"{float(s.get('net_roi_pct', 0.0)):+.2f}%",
                    "Currency": s.get("currency", "USD").strip().upper() or "USD",
                })
        return True
    except Exception as e:
        print(f"Error saving sales history CSV: {e}")
        return False


def load_sales_history(filepath: str = SALES_HISTORY_CSV, portfolio_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Loads sales transaction history from CSV.
    """
    if not os.path.exists(filepath):
        return []

    sales = []
    try:
        with open(filepath, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = row.get("Symbol", "").strip()
                if not sym:
                    continue

                port = row.get("Portfolio", "").strip() or DEFAULT_PORTFOLIO_NAME
                is_all = (
                    not portfolio_name
                    or portfolio_name in ("All Portfolios", "All", "*", "All Portfolios (Consolidated)")
                    or "consolidated" in portfolio_name.lower()
                )
                if not is_all and port != portfolio_name:
                    continue

                def _parse(val: Optional[str], default: float = 0.0) -> float:
                    if not val:
                        return default
                    c = val.replace("$", "").replace("%", "").replace(",", "").strip()
                    try:
                        return float(c)
                    except ValueError:
                        return default

                sales.append({
                    "date": row.get("Date", ""),
                    "portfolio": port,
                    "symbol": sym,
                    "shares_to_sell": _parse(row.get("Shares Sold", row.get("Shares"))),
                    "buy_price": _parse(row.get("Buy Price ($)")),
                    "sell_price": _parse(row.get("Sell Price ($)", row.get("Price ($)"))),
                    "gross_proceeds": _parse(row.get("Gross Proceeds ($)", row.get("Total Amount ($)"))),
                    "cost_basis": _parse(row.get("Cost Basis ($)")),
                    "commission_fee": _parse(row.get("Commission ($)")),
                    "gross_gain": _parse(row.get("Gross Gain ($)")),
                    "tax_rate_pct": _parse(row.get("Tax Rate (%)")),
                    "estimated_tax": _parse(row.get("Estimated Tax ($)")),
                    "net_proceeds": _parse(row.get("Net Proceeds ($)", row.get("Net Amount ($)"))),
                    "net_profit": _parse(row.get("Net Profit ($)")),
                    "net_roi_pct": _parse(row.get("Net ROI (%)")),
                    "currency": row.get("Currency", "USD").strip().upper() or "USD",
                })
        return sales
    except Exception as e:
        print(f"Error loading sales history CSV: {e}")
        return []


def append_sale_record(sale_data: Dict[str, Any], filepath: str = SALES_HISTORY_CSV) -> bool:
    """
    Appends a new completed sale transaction to sales_history.csv.
    """
    sales = load_sales_history(filepath)
    if "date" not in sale_data:
        sale_data["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sales.insert(0, sale_data)
    return save_sales_history(sales, filepath)
