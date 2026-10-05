"""
CSV Data Manager
Handles saving and loading portfolio holdings, trade/sale logs, and financial reports.
Includes automatic backups, formatting, and file integrity checks.
"""

import os
import csv
import json
import re
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_CSV = os.path.join(BASE_DIR, "portfolio.csv")
SALES_HISTORY_CSV = os.path.join(BASE_DIR, "sales_history.csv")
TRANSACTION_HISTORY_CSV = os.path.join(BASE_DIR, "transaction_history.csv")
WATCHLIST_CSV = os.path.join(BASE_DIR, "watchlist.csv")
PORTFOLIOS_JSON = os.path.join(BASE_DIR, "portfolios.json")
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
        "Sector",
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
                    "Sector": h.get("sector", ""),
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
                    "sector": (row.get("Sector") or row.get("sector") or "").strip(),
                })
        return holdings
    except Exception as e:
        print(f"Error loading portfolio CSV: {e}")
        return []


def load_registered_portfolios(filepath: str = PORTFOLIOS_JSON) -> List[str]:
    """Loads distinct registered portfolio names from JSON."""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [str(p).strip() for p in data if str(p).strip()]
            elif isinstance(data, dict):
                return [str(p).strip() for p in data.keys() if str(p).strip()]
    except Exception as e:
        print(f"Error loading portfolios JSON: {e}")
    return []


def save_registered_portfolios(names: List[str], filepath: str = PORTFOLIOS_JSON) -> bool:
    """Saves distinct registered portfolio names to JSON."""
    clean = sorted(list(set(str(n).strip() for n in names if str(n).strip() and str(n).strip() != "All Portfolios (Consolidated)")))
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving portfolios JSON: {e}")
        return False


def add_portfolio(portfolio_name: str, filepath: str = PORTFOLIO_CSV) -> List[str]:
    """
    Registers a new portfolio name permanently so it appears in all dropdowns
    even before any holdings are added.
    """
    name = str(portfolio_name).strip()
    if not name or name in ("All Portfolios (Consolidated)", "All Portfolios", "All"):
        return get_portfolio_names(filepath)

    registered = set(load_registered_portfolios(PORTFOLIOS_JSON))
    registered.add(name)
    save_registered_portfolios(list(registered), PORTFOLIOS_JSON)
    return get_portfolio_names(filepath)


def get_portfolio_names(filepath: str = PORTFOLIO_CSV, include_registered: Optional[bool] = None) -> List[str]:
    """
    Returns sorted list of distinct portfolio names present in the CSV file,
    merged with registered portfolios, transaction history, and fee configurations.
    """
    if include_registered is None:
        try:
            include_registered = (os.path.abspath(filepath) == os.path.abspath(PORTFOLIO_CSV))
        except Exception:
            include_registered = False

    names = set()

    # Read from portfolio holdings CSV
    if os.path.exists(filepath):
        try:
            with open(filepath, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    p = row.get("Portfolio", "").strip()
                    if p and p != "All Portfolios (Consolidated)":
                        names.add(p)
        except Exception:
            pass

    if include_registered:
        # Load from registered portfolios.json
        for p in load_registered_portfolios(PORTFOLIOS_JSON):
            if p and p != "All Portfolios (Consolidated)":
                names.add(p)

        # Read from transaction history CSV
        if os.path.exists(TRANSACTION_HISTORY_CSV):
            try:
                with open(TRANSACTION_HISTORY_CSV, mode="r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        p = row.get("Portfolio", "").strip()
                        if p and p != "All Portfolios (Consolidated)":
                            names.add(p)
            except Exception:
                pass

        # Read from portfolio_fees.json
        fee_file = os.path.join(BASE_DIR, "portfolio_fees.json")
        if os.path.exists(fee_file):
            try:
                with open(fee_file, "r", encoding="utf-8") as f:
                    fees_data = json.load(f)
                    if isinstance(fees_data, dict):
                        for k in fees_data.keys():
                            k_str = str(k).strip()
                            if k_str and k_str != "All Portfolios (Consolidated)":
                                names.add(k_str)
            except Exception:
                pass

        if not names:
            names.add(DEFAULT_PORTFOLIO_NAME)

        sorted_names = sorted(list(names))
        save_registered_portfolios(sorted_names, PORTFOLIOS_JSON)
        return sorted_names

    if not names:
        names.add(DEFAULT_PORTFOLIO_NAME)
    return sorted(list(names))


def delete_portfolio(portfolio_name: str, filepath: str = PORTFOLIO_CSV) -> bool:
    """
    Deletes all holdings belonging to a specific portfolio and removes it from registry and fee settings.
    """
    try:
        is_default_file = (os.path.abspath(filepath) == os.path.abspath(PORTFOLIO_CSV))
    except Exception:
        is_default_file = False

    if is_default_file:
        current_names = [p for p in load_registered_portfolios(PORTFOLIOS_JSON) if p != portfolio_name]
        save_registered_portfolios(current_names, PORTFOLIOS_JSON)

        fee_file = os.path.join(BASE_DIR, "portfolio_fees.json")
        if os.path.exists(fee_file):
            try:
                with open(fee_file, "r", encoding="utf-8") as f:
                    fees_data = json.load(f)
                if portfolio_name in fees_data:
                    del fees_data[portfolio_name]
                    with open(fee_file, "w", encoding="utf-8") as f:
                        json.dump(fees_data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    all_holdings = load_portfolio(filepath, portfolio_name=None)
    remaining = [h for h in all_holdings if h.get("portfolio") != portfolio_name]
    return save_portfolio(remaining, filepath)


def rename_portfolio(old_name: str, new_name: str, filepath: str = PORTFOLIO_CSV) -> bool:
    """
    Renames a portfolio across registered portfolios, holdings, transactions, and fees.
    """
    try:
        is_default_file = (os.path.abspath(filepath) == os.path.abspath(PORTFOLIO_CSV))
    except Exception:
        is_default_file = False

    if is_default_file:
        current_names = load_registered_portfolios(PORTFOLIOS_JSON)
        new_names = [new_name if p == old_name else p for p in current_names]
        if new_name not in new_names:
            new_names.append(new_name)
        save_registered_portfolios(new_names, PORTFOLIOS_JSON)

        if os.path.exists(TRANSACTION_HISTORY_CSV):
            all_tx = load_transactions(TRANSACTION_HISTORY_CSV, portfolio_name=None)
            tx_changed = False
            for tx in all_tx:
                if tx.get("portfolio") == old_name:
                    tx["portfolio"] = new_name
                    tx_changed = True
            if tx_changed:
                save_transactions(all_tx, TRANSACTION_HISTORY_CSV)

        fee_file = os.path.join(BASE_DIR, "portfolio_fees.json")
        if os.path.exists(fee_file):
            try:
                with open(fee_file, "r", encoding="utf-8") as f:
                    fees_data = json.load(f)
                if old_name in fees_data:
                    fees_data[new_name] = fees_data.pop(old_name)
                    with open(fee_file, "w", encoding="utf-8") as f:
                        json.dump(fees_data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

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


def update_transaction(index: int, updated_tx: Dict[str, Any], filepath: str = TRANSACTION_HISTORY_CSV) -> bool:
    """
    Updates an existing transaction at the specified index in transaction_history.csv.
    Automatically creates rotating backups before saving.
    """
    txs = load_transactions(filepath, portfolio_name=None, tx_type=None)
    if index < 0 or index >= len(txs):
        return False
    txs[index] = updated_tx
    return save_transactions(txs, filepath)


def delete_transaction(index: int, filepath: str = TRANSACTION_HISTORY_CSV) -> bool:
    """
    Deletes an existing transaction at the specified index in transaction_history.csv.
    Automatically creates rotating backups before saving.
    """
    txs = load_transactions(filepath, portfolio_name=None, tx_type=None)
    if index < 0 or index >= len(txs):
        return False
    txs.pop(index)
    return save_transactions(txs, filepath)


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


def export_period_report_to_csv(report_data: Dict[str, Any], filepath: str) -> bool:
    """
    Exports period earnings report data (summary KPIs, breakdown intervals, and transaction records)
    to a structured CSV format.
    """
    try:
        summ = report_data.get("summary", {})
        breakdown = report_data.get("breakdown", [])
        records = report_data.get("records", [])
        period_label = report_data.get("period_label", report_data.get("period_mode", "All Time"))
        port_name = report_data.get("portfolio_name", "All Portfolios")

        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # 1. Report Metadata
            writer.writerow(["# PERIOD EARNINGS REPORT"])
            writer.writerow(["Portfolio", port_name])
            writer.writerow(["Timeframe", period_label])
            writer.writerow(["Exported At", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            writer.writerow([])

            # 2. KPI Summary
            writer.writerow(["# SUMMARY KPIS"])
            writer.writerow(["Metric", "Value"])
            writer.writerow(["Total Realized Profit ($)", f"{float(summ.get('total_realized_profit', 0.0)):.2f}"])
            writer.writerow(["Net ROI (%)", f"{float(summ.get('net_roi_pct', 0.0)):.2f}%"])
            writer.writerow(["Total Sell Proceeds ($)", f"{float(summ.get('total_sell_proceeds', 0.0)):.2f}"])
            writer.writerow(["Total Cost Basis Sold ($)", f"{float(summ.get('total_cost_basis', 0.0)):.2f}"])
            writer.writerow(["Total Buy Volume ($)", f"{float(summ.get('total_buy_volume', 0.0)):.2f}"])
            writer.writerow(["Total Commission Fees ($)", f"{float(summ.get('total_fees_paid', 0.0)):.2f}"])
            writer.writerow(["Buy Trades Count", summ.get("buy_count", 0)])
            writer.writerow(["Sell Trades Count", summ.get("sell_count", 0)])
            writer.writerow(["Dividend Count", summ.get("dividend_count", 0)])
            writer.writerow([])

            # 3. Breakdown by Interval
            if breakdown:
                writer.writerow(["# PERIOD INTERVALS BREAKDOWN"])
                writer.writerow(["Interval", "Transactions", "Buy Volume ($)", "Sell Proceeds ($)", "Cost Sold ($)", "Realized Profit ($)", "ROI (%)"])
                for b in breakdown:
                    writer.writerow([
                        b.get("period_label", ""),
                        b.get("total_transactions", 0),
                        f"{float(b.get('total_buy_volume', 0.0)):.2f}",
                        f"{float(b.get('total_sell_proceeds', 0.0)):.2f}",
                        f"{float(b.get('total_cost_basis', 0.0)):.2f}",
                        f"{float(b.get('total_realized_profit', 0.0)):.2f}",
                        f"{float(b.get('net_roi_pct', 0.0)):.2f}%",
                    ])
                writer.writerow([])

            # 4. Individual Transaction Records
            writer.writerow(["# INDIVIDUAL TRANSACTION RECORDS"])
            rec_headers = [
                "Date", "Type", "Portfolio", "Symbol", "Currency",
                "Shares", "Price ($)", "Total Amount ($)", "Commission ($)",
                "Tax ($)", "Net Profit ($)", "ROI (%)", "Notes"
            ]
            writer.writerow(rec_headers)
            for r in records:
                writer.writerow([
                    r.get("date", ""),
                    r.get("type", "BUY"),
                    r.get("portfolio", ""),
                    r.get("symbol", ""),
                    r.get("currency", "USD"),
                    f"{float(r.get('shares', 0.0)):.4g}",
                    f"{float(r.get('price', 0.0)):.2f}",
                    f"{float(r.get('total_amount', 0.0)):.2f}",
                    f"{float(r.get('commission_fee', 0.0)):.2f}",
                    f"{float(r.get('estimated_tax', 0.0)):.2f}",
                    f"{float(r.get('net_profit', 0.0)):.2f}",
                    f"{float(r.get('net_roi_pct', 0.0)):.2f}%" if r.get("type") == "SELL" else "—",
                    r.get("notes", ""),
                ])
        return True
    except Exception as e:
        print(f"Error exporting period report to CSV: {e}")
        return False


def load_watchlist(filepath: str = WATCHLIST_CSV) -> List[Dict[str, Any]]:
    """Loads monitored watchlist items from CSV."""
    if not os.path.exists(filepath):
        return []

    items = []
    try:
        with open(filepath, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                try:
                    tp = float(row.get("Target Price") or row.get("target_price") or 0.0)
                except (ValueError, TypeError):
                    tp = 0.0

                items.append({
                    "symbol": sym,
                    "name": (row.get("Name") or row.get("name") or sym).strip(),
                    "target_price": tp,
                    "target_buy_price": tp,
                    "currency": (row.get("Currency") or row.get("currency") or "USD").strip().upper(),
                    "notes": (row.get("Notes") or row.get("notes") or "").strip(),
                    "tags": (row.get("Tags") or row.get("tags") or "").strip(),
                    "added_date": (row.get("Added Date") or row.get("added_date") or "").strip(),
                })
        return items
    except Exception as e:
        print(f"Error loading watchlist CSV: {e}")
        return []


def save_watchlist(watchlist: List[Dict[str, Any]], filepath: str = WATCHLIST_CSV) -> bool:
    """Saves watchlist items to CSV file with automatic rotating backup."""
    rotate_file_backups(filepath, max_backups=DEFAULT_MAX_BACKUPS)
    fieldnames = ["Symbol", "Name", "Target Price", "Currency", "Notes", "Tags", "Added Date"]
    try:
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for w in watchlist:
                sym = (w.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                writer.writerow({
                    "Symbol": sym,
                    "Name": w.get("name", sym),
                    "Target Price": f"{float(w.get('target_price') or w.get('target_buy_price') or 0.0):.2f}",
                    "Currency": (w.get("currency") or "USD").strip().upper(),
                    "Notes": w.get("notes", ""),
                    "Tags": w.get("tags", ""),
                    "Added Date": w.get("added_date", datetime.now().strftime("%Y-%m-%d")),
                })
        return True
    except Exception as e:
        print(f"Error saving watchlist CSV: {e}")
        return False


WATCHLIST_QUOTES_JSON = os.path.join(BASE_DIR, "watchlist_quotes.json")


def load_watchlist_quotes_cache(filepath: str = WATCHLIST_QUOTES_JSON) -> Dict[str, Any]:
    """Loads cached quotes for watchlist stocks from disk JSON."""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_watchlist_quotes_cache(cache: Dict[str, Any], filepath: str = WATCHLIST_QUOTES_JSON) -> bool:
    """Saves cached quotes for watchlist stocks to disk JSON."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving watchlist quotes cache: {e}")
        return False


def add_to_watchlist(
    symbol: str,
    name: str = "",
    target_price: float = 0.0,
    currency: str = "USD",
    notes: str = "",
    tags: str = "",
    filepath: str = WATCHLIST_CSV,
) -> bool:
    """Adds or updates a ticker symbol in the watchlist."""
    if currency.endswith(".csv") or "/" in currency or "\\" in currency:
        filepath = currency
        currency = "USD"
    items = load_watchlist(filepath)
    clean_sym = symbol.strip().upper()
    existing = next((i for i in items if i["symbol"] == clean_sym), None)
    if existing:
        existing["name"] = name or existing["name"]
        existing["target_price"] = target_price
        existing["target_buy_price"] = target_price
        existing["currency"] = currency
        existing["notes"] = notes
        if tags:
            existing["tags"] = tags
    else:
        items.append({
            "symbol": clean_sym,
            "name": name or clean_sym,
            "target_price": target_price,
            "target_buy_price": target_price,
            "currency": currency,
            "notes": notes,
            "tags": tags,
            "added_date": datetime.now().strftime("%Y-%m-%d"),
        })
    return save_watchlist(items, filepath)


def update_watchlist_item(
    old_symbol: str,
    new_symbol: str,
    name: str = "",
    target_price: float = 0.0,
    currency: str = "USD",
    notes: str = "",
    tags: str = "",
    filepath: str = WATCHLIST_CSV,
) -> bool:
    """Updates an existing watchlist item, cleanly replacing the symbol/currency/target/notes/tags."""
    items = load_watchlist(filepath)
    old_clean = old_symbol.strip().upper()
    new_clean = new_symbol.strip().upper() if new_symbol else old_clean
    if not old_clean:
        return False

    existing = next((i for i in items if i["symbol"] == old_clean), None)
    if existing:
        existing["symbol"] = new_clean
        if name:
            existing["name"] = name
        existing["target_price"] = max(0.0, float(target_price or 0.0))
        existing["target_buy_price"] = existing["target_price"]
        existing["currency"] = currency.strip().upper() if currency else "USD"
        existing["notes"] = notes.strip()
        if tags is not None and tags != "":
            existing["tags"] = tags.strip()
    else:
        items.append({
            "symbol": new_clean,
            "name": name or new_clean,
            "target_price": max(0.0, float(target_price or 0.0)),
            "target_buy_price": max(0.0, float(target_price or 0.0)),
            "currency": currency.strip().upper() if currency else "USD",
            "notes": notes.strip(),
            "tags": tags.strip() if tags else "",
            "added_date": datetime.now().strftime("%Y-%m-%d"),
        })
    return save_watchlist(items, filepath)


def scan_data_integrity(
    portfolio_filepath: str = PORTFOLIO_CSV,
    watchlist_filepath: str = WATCHLIST_CSV,
) -> Dict[str, Any]:
    """
    Scans portfolio and watchlist data files for anomalies:
    - Duplicate symbols in same portfolio
    - Blank or invalid symbols
    - Negative or zero shares
    - Missing currency code
    - Watchlist duplicate symbols
    """
    issues = []
    portfolio_rows = []
    watchlist_rows = []

    # 1. Scan Portfolio
    if os.path.exists(portfolio_filepath):
        try:
            with open(portfolio_filepath, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                seen_port_syms = set()
                for idx, row in enumerate(reader, start=2):
                    sym = (row.get("Symbol") or "").strip().upper()
                    port = (row.get("Portfolio") or DEFAULT_PORTFOLIO_NAME).strip()
                    curr = (row.get("Currency") or "").strip().upper()

                    if not sym:
                        issues.append({
                            "type": "PORTFOLIO_BLANK_SYMBOL",
                            "severity": "high",
                            "line": idx,
                            "desc": f"Line {idx}: Blank or missing stock symbol in portfolio '{port}'.",
                        })
                        continue

                    key = (port, sym)
                    if key in seen_port_syms:
                        issues.append({
                            "type": "PORTFOLIO_DUPLICATE_SYMBOL",
                            "severity": "medium",
                            "line": idx,
                            "symbol": sym,
                            "portfolio": port,
                            "desc": f"Duplicate symbol '{sym}' found in portfolio '{port}'.",
                        })
                    seen_port_syms.add(key)

                    try:
                        sh = float(row.get("Shares") or 0.0)
                        if sh <= 0:
                            issues.append({
                                "type": "PORTFOLIO_INVALID_SHARES",
                                "severity": "medium",
                                "line": idx,
                                "symbol": sym,
                                "desc": f"Line {idx} ({sym}): Non-positive shares count ({sh}).",
                            })
                    except (ValueError, TypeError):
                        issues.append({
                            "type": "PORTFOLIO_CORRUPTED_NUMBER",
                            "severity": "high",
                            "line": idx,
                            "symbol": sym,
                            "desc": f"Line {idx} ({sym}): Invalid number in Shares column.",
                        })

                    if not curr or curr not in ("USD", "CAD", "HKD", "EUR", "GBP", "JPY", "AUD", "CNY"):
                        issues.append({
                            "type": "PORTFOLIO_INVALID_CURRENCY",
                            "severity": "low",
                            "line": idx,
                            "symbol": sym,
                            "desc": f"Line {idx} ({sym}): Missing or unknown currency '{curr}'.",
                        })
        except Exception as e:
            issues.append({"type": "PORTFOLIO_READ_ERROR", "severity": "critical", "desc": str(e)})

    # 2. Scan Watchlist
    if os.path.exists(watchlist_filepath):
        try:
            with open(watchlist_filepath, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                seen_watch = set()
                for idx, row in enumerate(reader, start=2):
                    sym = (row.get("Symbol") or "").strip().upper()
                    if not sym:
                        issues.append({
                            "type": "WATCHLIST_BLANK_SYMBOL",
                            "severity": "high",
                            "line": idx,
                            "desc": f"Watchlist Line {idx}: Blank symbol.",
                        })
                        continue
                    if sym in seen_watch:
                        issues.append({
                            "type": "WATCHLIST_DUPLICATE",
                            "severity": "medium",
                            "line": idx,
                            "symbol": sym,
                            "desc": f"Watchlist has duplicate entry for '{sym}'.",
                        })
                    seen_watch.add(sym)
        except Exception as e:
            issues.append({"type": "WATCHLIST_READ_ERROR", "severity": "critical", "desc": str(e)})

    return {
        "healthy": len(issues) == 0,
        "total_issues": len(issues),
        "issues": issues,
    }


def repair_data_integrity(
    portfolio_filepath: str = PORTFOLIO_CSV,
    watchlist_filepath: str = WATCHLIST_CSV,
) -> Dict[str, Any]:
    """
    Automatically fixes detected issues:
    - Merges duplicate portfolio holdings (combines shares & computes weighted average cost basis)
    - Normalizes missing currencies to USD or CAD
    - Removes duplicate watchlist rows
    - Creates auto-backup before modifying files
    """
    fixes = []

    # 1. Repair Portfolio
    if os.path.exists(portfolio_filepath):
        holdings = load_portfolio(portfolio_filepath)
        merged_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for h in holdings:
            sym = h.get("symbol", "").strip().upper()
            port = h.get("portfolio", DEFAULT_PORTFOLIO_NAME).strip()
            if not sym:
                fixes.append("Removed entry with blank symbol.")
                continue

            curr = h.get("currency", "USD").strip().upper() or "USD"
            if curr not in ("USD", "CAD", "HKD", "EUR", "GBP", "JPY", "AUD", "CNY"):
                curr = "CAD" if sym.endswith(":TSE") or sym.endswith(".TO") else ("HKD" if sym.endswith(":HKG") or sym.endswith(".HK") else "USD")
                h["currency"] = curr
                fixes.append(f"Auto-assigned currency '{curr}' to {sym}.")

            key = (port, sym)
            if key in merged_map:
                prev = merged_map[key]
                sh1 = float(prev.get("shares", 0.0) or 0.0)
                bp1 = float(prev.get("buy_price", 0.0) or 0.0)
                sh2 = float(h.get("shares", 0.0) or 0.0)
                bp2 = float(h.get("buy_price", 0.0) or 0.0)
                tot_shares = sh1 + sh2
                avg_bp = ((sh1 * bp1) + (sh2 * bp2)) / tot_shares if tot_shares > 0 else bp1

                prev["shares"] = tot_shares
                prev["buy_price"] = round(avg_bp, 4)
                prev["cost_basis"] = round(tot_shares * avg_bp, 2)
                fixes.append(f"Merged duplicate holding '{sym}' in '{port}': total {tot_shares:.2f} shares at avg ${avg_bp:.2f}.")
            else:
                merged_map[key] = h

        save_portfolio(list(merged_map.values()), filepath=portfolio_filepath)

    # 2. Repair Watchlist
    if os.path.exists(watchlist_filepath):
        watch_items = load_watchlist(watchlist_filepath)
        unique_watch = {}
        for w in watch_items:
            sym = w.get("symbol", "").strip().upper()
            if not sym:
                fixes.append("Removed blank watchlist row.")
                continue
            if sym not in unique_watch:
                unique_watch[sym] = w
            else:
                fixes.append(f"Deduplicated watchlist symbol '{sym}'.")
        save_watchlist(list(unique_watch.values()), filepath=watchlist_filepath)

    return {
        "success": True,
        "fixes_count": len(fixes),
        "fixes": fixes,
        "repaired": fixes,
    }



def parse_symbols_text(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parses pasted text containing multiple stock symbols.
    Supports symbols separated by newlines, tabs (e.g. from Excel/Sheets),
    commas, or semicolons. Intelligently extracts symbol, name, and target price.
    """
    if not raw_text or not raw_text.strip():
        return []

    lines = [line.strip() for line in raw_text.strip().splitlines() if line.strip()]
    results: List[Dict[str, Any]] = []
    seen = set()

    CURRENCY_CODES = {"USD", "CAD", "HKD", "EUR", "GBP", "AUD", "JPY", "CNY", "CHF"}

    def _clean_num(val_str: str) -> Optional[float]:
        try:
            cleaned = re.sub(r"[^\d.-]", "", val_str)
            return float(cleaned) if cleaned else None
        except (ValueError, TypeError):
            return None

    def _add_record(sym: str, name: str = "", target: float = 0.0, curr: str = "USD", notes: str = ""):
        sym = sym.strip().upper().replace('"', '').replace("'", "")
        if not sym or sym in ("SYMBOL", "TICKER", "CODE", "代碼", "代码", "NAME", "名稱"):
            return
        if sym in seen:
            return
        seen.add(sym)
        tgt_val = max(0.0, float(target or 0.0))
        results.append({
            "symbol": sym,
            "name": name.strip(),
            "target_price": tgt_val,
            "target_buy_price": tgt_val,
            "currency": curr.strip().upper() if curr.strip().upper() in CURRENCY_CODES else "USD",
            "notes": notes.strip(),
            "added_date": datetime.now().strftime("%Y-%m-%d"),
        })

    for line in lines:
        # Check tab-delimited (copy-paste from Excel / Google Sheets)
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t") if p.strip()]
            if not parts:
                continue
            sym = parts[0]
            name = ""
            tgt = 0.0
            curr = "USD"
            notes = ""

            for p in parts[1:]:
                p_num = _clean_num(p)
                p_up = p.upper()
                if p_up in CURRENCY_CODES:
                    curr = p_up
                elif p_num is not None and tgt == 0.0:
                    tgt = p_num
                elif not name:
                    name = p
                else:
                    notes = (notes + " " + p).strip()

            if "," in sym:
                for sub_s in sym.split(","):
                    sub_s = sub_s.strip()
                    if sub_s:
                        _add_record(sub_s, name, tgt, curr, notes)
            else:
                _add_record(sym, name, tgt, curr, notes)
            continue

        # Check comma or semicolon separated list
        if "," in line or ";" in line:
            sep = "," if "," in line else ";"
            tokens = [t.strip() for t in line.split(sep) if t.strip()]
            # If line is like: "AAPL, Apple Inc, 150.00"
            if len(tokens) >= 2:
                num_cnt = sum(1 for tok in tokens[1:] if _clean_num(tok) is not None)
                if num_cnt > 0:
                    sym = tokens[0]
                    name = ""
                    tgt = 0.0
                    curr = "USD"
                    notes = ""
                    for p in tokens[1:]:
                        p_num = _clean_num(p)
                        p_up = p.upper()
                        if p_up in CURRENCY_CODES:
                            curr = p_up
                        elif p_num is not None and tgt == 0.0:
                            tgt = p_num
                        elif not name:
                            name = p
                        else:
                            notes = (notes + " " + p).strip()
                    _add_record(sym, name, tgt, curr, notes)
                    continue

            # Otherwise treat tokens as multiple symbols
            for tok in tokens:
                _add_record(tok)
            continue

        # Check space-separated multiple symbols (e.g. "AAPL MSFT NVDA")
        space_tokens = line.split()
        if len(space_tokens) > 1 and all(len(t) <= 12 and not t.isdigit() for t in space_tokens):
            for t in space_tokens:
                _add_record(t)
            continue

        # Single symbol per line
        _add_record(line)

    return results


def bulk_add_to_watchlist(records: List[Dict[str, Any]], filepath: str = WATCHLIST_CSV) -> int:
    """Adds or updates multiple ticker symbols in the watchlist in a single batch."""
    if not records:
        return 0
    items = load_watchlist(filepath)
    count = 0
    now_date = datetime.now().strftime("%Y-%m-%d")

    for rec in records:
        clean_sym = str(rec.get("symbol", "")).strip().upper()
        if not clean_sym:
            continue
        existing = next((i for i in items if i["symbol"] == clean_sym), None)
        tgt = float(rec.get("target_price") or rec.get("target_buy_price") or 0.0)
        curr = str(rec.get("currency", "USD")).strip().upper() or "USD"
        name = str(rec.get("name", "")).strip()
        notes = str(rec.get("notes", "")).strip()

        if existing:
            if name:
                existing["name"] = name
            if tgt > 0:
                existing["target_price"] = tgt
                existing["target_buy_price"] = tgt
            if curr:
                existing["currency"] = curr
            if notes:
                existing["notes"] = notes
        else:
            items.append({
                "symbol": clean_sym,
                "name": name or clean_sym,
                "target_price": tgt,
                "target_buy_price": tgt,
                "currency": curr,
                "notes": notes,
                "added_date": rec.get("added_date", now_date),
            })
        count += 1

    save_watchlist(items, filepath)
    return count


def import_watchlist_from_csv(csv_filepath: str, target_filepath: str = WATCHLIST_CSV) -> Tuple[int, List[str]]:
    """
    Imports watchlist symbols from a CSV file.
    Supports standard headers (Symbol, Name, Target Price, Currency, Notes)
    as well as Google Finance Watchlist CSV exports.
    Returns (count_imported, list_of_symbols).
    """
    if not os.path.exists(csv_filepath):
        return 0, []

    records: List[Dict[str, Any]] = []
    try:
        with open(csv_filepath, mode="r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header_row = next(reader, None)
            if not header_row:
                return 0, []

            # Map header columns
            col_map: Dict[str, int] = {}
            for idx, h in enumerate(header_row):
                clean_h = str(h).strip().lower().replace("_", " ")
                if any(k in clean_h for k in ("symbol", "ticker", "代碼", "代码")):
                    col_map["symbol"] = idx
                elif any(k in clean_h for k in ("company", "name", "名稱", "名称")):
                    col_map["name"] = idx
                elif any(k in clean_h for k in ("target", "目標價", "目标价")):
                    col_map["target"] = idx
                elif any(k in clean_h for k in ("currency", "curr", "幣種", "币种")):
                    col_map["currency"] = idx
                elif any(k in clean_h for k in ("note", "備註", "备注")):
                    col_map["notes"] = idx

            # If no symbol column found, assume column 0
            if "symbol" not in col_map and len(header_row) > 0:
                col_map["symbol"] = 0
                if len(header_row) > 1:
                    col_map["name"] = 1

            for row in reader:
                if not row or not any(row):
                    continue
                sym_idx = col_map.get("symbol", 0)
                if sym_idx >= len(row):
                    continue
                sym = str(row[sym_idx]).strip().upper()
                if not sym or sym in ("SYMBOL", "TICKER", "代碼", "代码"):
                    continue

                name = str(row[col_map["name"]]).strip() if "name" in col_map and col_map["name"] < len(row) else ""
                tgt = 0.0
                if "target" in col_map and col_map["target"] < len(row):
                    try:
                        clean_t = re.sub(r"[^\d.-]", "", str(row[col_map["target"]]))
                        tgt = float(clean_t) if clean_t else 0.0
                    except (ValueError, TypeError):
                        tgt = 0.0

                curr = str(row[col_map["currency"]]).strip().upper() if "currency" in col_map and col_map["currency"] < len(row) else "USD"
                notes = str(row[col_map["notes"]]).strip() if "notes" in col_map and col_map["notes"] < len(row) else ""

                records.append({
                    "symbol": sym,
                    "name": name,
                    "target_price": tgt,
                    "currency": curr,
                    "notes": notes,
                })

        count = bulk_add_to_watchlist(records, target_filepath)
        return count, [r["symbol"] for r in records]
    except Exception as e:
        print(f"Error importing watchlist from CSV: {e}")
        return 0, []


def remove_from_watchlist(symbol: str, filepath: str = WATCHLIST_CSV) -> bool:
    """Removes a ticker symbol from the watchlist."""
    items = load_watchlist(filepath)
    clean_sym = symbol.strip().upper()
    remaining = [i for i in items if i["symbol"] != clean_sym]
    return save_watchlist(remaining, filepath)


def book_drip_transaction(
    symbol: str,
    dividend_amount: Any,
    reinvest_price: float = 0.0,
    tx_date: Optional[str] = None,
    portfolio: str = "All",
    notes: str = "Automated DRIP Reinvestment",
    portfolio_filepath: str = PORTFOLIO_CSV,
    history_filepath: str = TRANSACTION_HISTORY_CSV,
    **kwargs,
) -> Tuple[bool, str, float]:
    """
    Automates booking of a Dividend Reinvestment (DRIP) event:
    1. Computes shares purchased = dividend_amount / reinvest_price.
    2. Logs a DRIP record in transaction_history.csv.
    3. Updates the active holding in portfolio.csv (adds shares, adjusts cost basis).
    Returns (success, message, new_shares).
    """
    # Support alias kwarg names
    if "portfolio_file" in kwargs:
        portfolio_filepath = kwargs["portfolio_file"]
    if "tx_file" in kwargs:
        history_filepath = kwargs["tx_file"]
    if "tx_filepath" in kwargs:
        history_filepath = kwargs["tx_filepath"]

    # Support swapped (portfolio, symbol, dividend_amount, reinvest_price) positional order
    if isinstance(dividend_amount, str) and not isinstance(reinvest_price, (int, float)):
        # signature was (portfolio, symbol, dividend_amount, reinvest_price)
        portfolio, symbol = symbol, dividend_amount
        dividend_amount = reinvest_price
        reinvest_price = float(tx_date) if tx_date else 0.0
        tx_date = None

    try:
        dividend_amount = float(dividend_amount)
        reinvest_price = float(reinvest_price)
    except (ValueError, TypeError):
        return False, "Dividend amount and reinvestment price must be numeric.", 0.0

    if dividend_amount <= 0 or reinvest_price <= 0:
        return False, "Dividend amount and reinvestment price must both be greater than 0.", 0.0

    new_shares = dividend_amount / reinvest_price
    if tx_date is None:
        tx_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    all_holdings = load_portfolio(portfolio_filepath, portfolio_name=None)
    holding = next(
        (h for h in all_holdings if (portfolio in ("All", "All Portfolios", "All Portfolios (Consolidated)") or h.get("portfolio") == portfolio) and h.get("symbol") == symbol.strip().upper()),
        None
    )
    if not holding and all_holdings:
        holding = next((h for h in all_holdings if h.get("symbol") == symbol.strip().upper()), None)

    h_curr = holding.get("currency", "USD") if holding else "USD"
    actual_port = holding.get("portfolio", portfolio) if holding else portfolio

    drip_record = {
        "date": tx_date,
        "type": "DRIP",
        "portfolio": actual_port,
        "symbol": symbol.strip().upper(),
        "currency": h_curr,
        "shares": round(new_shares, 4),
        "price": round(reinvest_price, 4),
        "total_amount": round(dividend_amount, 2),
        "commission_fee": 0.0,
        "estimated_tax": 0.0,
        "net_profit": 0.0,
        "net_roi_pct": 0.0,
        "notes": notes,
    }

    tx_ok = append_transaction(drip_record, history_filepath)
    if not tx_ok:
        return False, "Failed to append DRIP record to transaction history.", 0.0

    if holding:
        old_shares = float(holding.get("shares", 0.0))
        old_cost = float(holding.get("cost_basis", 0.0))
        combined_shares = old_shares + new_shares
        combined_cost = old_cost + dividend_amount
        holding["shares"] = round(combined_shares, 4)
        holding["cost_basis"] = round(combined_cost, 2)
        if combined_shares > 0:
            holding["buy_price"] = round(combined_cost / combined_shares, 4)
        save_portfolio(all_holdings, portfolio_filepath)
    else:
        all_holdings.append({
            "portfolio": actual_port,
            "symbol": symbol.strip().upper(),
            "name": symbol.strip().upper(),
            "shares": round(new_shares, 4),
            "buy_price": round(reinvest_price, 4),
            "current_price": round(reinvest_price, 4),
            "cost_basis": round(dividend_amount, 2),
            "market_value": round(dividend_amount, 2),
            "currency": h_curr,
            "last_updated": tx_date,
        })
        save_portfolio(all_holdings, portfolio_filepath)

    return True, f"Successfully booked {new_shares:.4f} DRIP shares for {symbol}.", round(new_shares, 4)
