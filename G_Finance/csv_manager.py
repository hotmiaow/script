"""
CSV Data Manager
Handles saving and loading portfolio holdings, trade/sale logs, and financial reports.
Includes automatic backups, formatting, and file integrity checks.
"""

import os
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_CSV = os.path.join(BASE_DIR, "portfolio.csv")
SALES_HISTORY_CSV = os.path.join(BASE_DIR, "sales_history.csv")


def ensure_workspace_files():
    """Ensure default CSV files exist if not present."""
    if not os.path.exists(PORTFOLIO_CSV):
        save_portfolio([], PORTFOLIO_CSV)
    if not os.path.exists(SALES_HISTORY_CSV):
        save_sales_history([], SALES_HISTORY_CSV)


DEFAULT_PORTFOLIO_NAME = "USD HSBC"


def save_portfolio(holdings: List[Dict[str, Any]], filepath: str = PORTFOLIO_CSV) -> bool:
    """
    Saves current portfolio holdings to CSV file.
    Ensures portfolio tag, cost_basis, market_value, and unrealized metrics are calculated.
    """
    fieldnames = [
        "Portfolio",
        "Symbol",
        "Name",
        "Shares",
        "Buy Price",
        "Current Price",
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

                writer.writerow({
                    "Portfolio": port_name,
                    "Symbol": h.get("symbol", ""),
                    "Name": h.get("name", h.get("symbol", "")),
                    "Shares": f"{shares:.4f}",
                    "Buy Price": f"{buy_price:.2f}",
                    "Current Price": f"{current_price:.2f}",
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

                holdings.append({
                    "portfolio": port,
                    "symbol": symbol,
                    "name": row.get("Name", symbol),
                    "shares": shares,
                    "buy_price": buy_price,
                    "current_price": current_price,
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


def save_sales_history(sales: List[Dict[str, Any]], filepath: str = SALES_HISTORY_CSV) -> bool:
    """
    Saves sales transactions to CSV.
    """
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
                    "Shares Sold": f"{float(s.get('shares_to_sell', 0.0)):.4f}",
                    "Buy Price ($)": f"{float(s.get('buy_price', 0.0)):.2f}",
                    "Sell Price ($)": f"{float(s.get('sell_price', 0.0)):.2f}",
                    "Gross Proceeds ($)": f"{float(s.get('gross_proceeds', 0.0)):.2f}",
                    "Cost Basis ($)": f"{float(s.get('cost_basis', 0.0)):.2f}",
                    "Commission ($)": f"{float(s.get('commission_fee', 0.0)):.2f}",
                    "Gross Gain ($)": f"{float(s.get('gross_gain', 0.0)):+.2f}",
                    "Tax Rate (%)": f"{float(s.get('tax_rate_pct', 0.0)):.2f}%",
                    "Estimated Tax ($)": f"{float(s.get('estimated_tax', 0.0)):.2f}",
                    "Net Proceeds ($)": f"{float(s.get('net_proceeds', 0.0)):.2f}",
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
                    "shares_to_sell": _parse(row.get("Shares Sold")),
                    "buy_price": _parse(row.get("Buy Price ($)")),
                    "sell_price": _parse(row.get("Sell Price ($)")),
                    "gross_proceeds": _parse(row.get("Gross Proceeds ($)")),
                    "cost_basis": _parse(row.get("Cost Basis ($)")),
                    "commission_fee": _parse(row.get("Commission ($)")),
                    "gross_gain": _parse(row.get("Gross Gain ($)")),
                    "tax_rate_pct": _parse(row.get("Tax Rate (%)")),
                    "estimated_tax": _parse(row.get("Estimated Tax ($)")),
                    "net_proceeds": _parse(row.get("Net Proceeds ($)")),
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
