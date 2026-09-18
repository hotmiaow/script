"""
Google Finance Account Sync Module (Google Finance Beta Compatible)
Handles:
- Fetching user's personal portfolio/watchlist from Google Finance Beta (https://www.google.com/finance/beta/).
- Automatic URL normalization for beta endpoints.
- Parsing table rows, cards, share quantities, purchase prices, and live quotes.
- Enriching synced holdings with Google Finance live quotes and dividend data.
- Importing native Google Finance exported CSV files (Beta and standard formats).
- Exporting local portfolios in Google Finance format.
- Storing local configuration (session cookies, portfolio URLs) in config.json.
"""

import os
import json
import csv
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import requests
from bs4 import BeautifulSoup

from google_finance_fetcher import GoogleFinanceFetcher
from financial_calc import calc_holding_summary

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DEFAULT_BETA_URL = "https://www.google.com/finance/beta/portfolio/c58e567d-3b90-41d3-92fa-6b200333ec17"


def load_sync_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        return {
            "cookie": "",
            "portfolio_url": DEFAULT_BETA_URL,
            "last_sync": "",
        }
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure URL points to beta
            url = data.get("portfolio_url", "")
            if not url or "google.com/finance/portfolio" in url:
                data["portfolio_url"] = normalize_google_finance_url(url or DEFAULT_BETA_URL)
            return data
    except Exception:
        return {"cookie": "", "portfolio_url": DEFAULT_BETA_URL, "last_sync": ""}


def save_sync_config(cfg: Dict[str, Any]) -> bool:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def normalize_google_finance_url(url_or_id: str) -> str:
    """
    Normalizes any portfolio URL or ID to Google Finance Beta format:
    e.g.:
    - 'https://www.google.com/finance/beta/' -> 'https://www.google.com/finance/beta/'
    - 'https://www.google.com/finance/portfolio/watchlist' -> 'https://www.google.com/finance/beta/portfolio/watchlist'
    - 'https://www.google.com/finance/portfolio/12345' -> 'https://www.google.com/finance/beta/portfolio/12345'
    - 'watchlist' -> 'https://www.google.com/finance/beta/portfolio/watchlist'
    - '12345' -> 'https://www.google.com/finance/beta/portfolio/12345'
    """
    u = url_or_id.strip()
    if not u:
        return DEFAULT_BETA_URL

    if not u.startswith("http"):
        if u.lower() == "watchlist":
            return DEFAULT_BETA_URL
        return f"https://www.google.com/finance/beta/portfolio/{u}"

    # If it has google.com/finance/ but missing /beta/
    if "google.com/finance/" in u and "google.com/finance/beta/" not in u:
        u = u.replace("google.com/finance/", "google.com/finance/beta/")

    return u


class GoogleAccountSync:
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def __init__(self):
        self.config = load_sync_config()
        self.fetcher = GoogleFinanceFetcher()

    def get_session(self, cookie: Optional[str] = None) -> requests.Session:
        s = requests.Session()
        s.headers.update(self.DEFAULT_HEADERS)
        c = cookie if cookie is not None else self.config.get("cookie", "")
        if c:
            s.headers["Cookie"] = c.strip()
        return s

    def test_connection(self, cookie: str) -> Tuple[bool, str]:
        """
        Tests whether the provided session cookie or headers can access Google Finance Beta.
        """
        try:
            s = self.get_session(cookie)
            resp = s.get("https://www.google.com/finance/beta/", timeout=10)
            if resp.status_code != 200:
                return False, f"Server returned HTTP {resp.status_code}"

            text = resp.text
            is_signed_in = (
                "Sign out" in text
                or "accounts.google.com/SignOutOptions" in text
            ) and ("Sign in" not in text)

            if is_signed_in:
                return True, "Successfully connected to Google Finance Beta with active user session!"
            else:
                return False, "Google session is unauthenticated or expired ('Sign in' required). Google blocks server-side scraping of private portfolios. Use the 'Google Finance CSV' tab to import."
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def fetch_user_portfolio(
        self, portfolio_url_or_id: str, cookie: Optional[str] = None, enrich_quotes: bool = True
    ) -> Dict[str, Any]:
        """
        Fetches user's portfolio or watchlist from Google Finance Beta.
        Extracts holdings and enriches with live quotes and dividend statistics.
        """
        target = normalize_google_finance_url(portfolio_url_or_id)
        s = self.get_session(cookie)

        try:
            resp = s.get(target, timeout=14, allow_redirects=True)
            if resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to fetch portfolio: HTTP {resp.status_code}",
                }

            # Check if Google returned an unauthenticated / sign-in page
            if "Sign in" in resp.text and ("Sign out" not in resp.text and "SignOutOptions" not in resp.text):
                is_private_uuid = bool(re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", target))
                if is_private_uuid:
                    return {
                        "success": False,
                        "error": (
                            "Google Finance requires active browser sign-in for this private portfolio. "
                            "Direct scraping is blocked by Google. "
                            "Please click 'Download list' on Google Finance and import the file under the 'Google Finance CSV' tab."
                        ),
                    }

            soup = BeautifulSoup(resp.text, "html.parser")
            raw_holdings = self._parse_beta_html(soup)

            if not raw_holdings:
                # Fallback: check if the page has quote links in any structure
                raw_holdings = self._parse_fallback_html(soup)

            if not raw_holdings:
                return {
                    "success": False,
                    "error": (
                        "No holdings found on this Google Finance page. "
                        "Google Finance renders private portfolios via client-side JavaScript. "
                        "Please use the 'Google Finance CSV' tab to import via 'Download list'."
                    ),
                }

            # Enrich holdings with real-time quote data (price, dividend yield, annual dividend)
            enriched_holdings = []
            for h in raw_holdings:
                if enrich_quotes:
                    lookup_sym = h.get("full_symbol") or h.get("symbol")
                    q = self.fetcher.fetch_quote(lookup_sym)
                    if q.get("success"):
                        h["current_price"] = q["price"]
                        h["name"] = q.get("name") or h.get("name", h["symbol"])
                        h["dividend_yield"] = q.get("dividend_yield", 0.0)
                        h["annual_div_per_share"] = q.get("annual_dividend_per_share", 0.0)
                        h["currency"] = q.get("currency", "USD")
                        h["change"] = q.get("change")
                        h["change_percent"] = q.get("change_percent")
                        if h.get("buy_price", 0.0) <= 0:
                            h["buy_price"] = q["price"]
                summary = calc_holding_summary(
                    h.get("shares", 0.0),
                    h.get("buy_price", 0.0),
                    h.get("current_price", 0.0),
                    h.get("dividend_yield", 0.0),
                    h.get("annual_div_per_share", 0.0),
                )
                h.update(summary)
                enriched_holdings.append(h)

            # Update configuration
            self.config["portfolio_url"] = target
            if cookie:
                self.config["cookie"] = cookie
            self.config["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_sync_config(self.config)

            return {
                "success": True,
                "portfolio_url": target,
                "holdings": enriched_holdings,
                "count": len(enriched_holdings),
            }
        except Exception as e:
            return {"success": False, "error": f"Error fetching portfolio: {str(e)}"}

    SECTOR_SYMBOLS = {"SIXB", "SIXC", "SIXE", "SIXI", "SIXM", "SIXR", "SIXRE", "SIXT", "SIXU", "SIXV", "SIXY"}

    def _parse_beta_html(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Parses Google Finance Beta tables and rows (tr.z0htKf, span.y9ljXe, div.sdnoWe, span[jsname="Pdsbrc"]).
        Ignores public market trend and sector index tables.
        """
        holdings = []
        seen = set()

        # 1. Map columns if table header is present
        col_map = {}
        tables = soup.find_all("table")
        target_table = None
        for tbl in tables:
            tbl_classes = tbl.get("class") or []
            if "p2sNke" in tbl_classes:
                continue  # Skip public sector index table
            header_tr = tbl.find("tr")
            if header_tr:
                headers_list = [re.sub(r"\s+", " ", th.get_text(strip=True)).lower() for th in header_tr.find_all(["th", "td"])]
                if any("trend" in h for h in headers_list) and any("mkt cap" in h or "prev close" in h for h in headers_list):
                    continue  # Skip sector trends table
                for idx, h in enumerate(headers_list):
                    if "symbol" in h:
                        col_map["symbol"] = idx
                    elif "share" in h or "quantity" in h or "units" in h:
                        col_map["shares"] = idx
                    elif "purchase" in h or "cost" in h or "avg" in h:
                        col_map["buy_price"] = idx
                    elif "price" in h and "purchase" not in h and "prev" not in h:
                        if "price" not in col_map:
                            col_map["price"] = idx
                target_table = tbl
                break

        # 2. Extract rows
        rows = soup.find_all("tr", class_=re.compile(r"z0htKf|row", re.I))
        if not rows and target_table:
            rows = target_table.find_all("tr")[1:]

        for tr in rows:
            a_el = tr.find("a", href=re.compile(r"quote/([A-Z0-9_.\-]+:[A-Z0-9_.\-]+)"))
            if not a_el:
                continue

            href = a_el.get("href", "")
            m = re.search(r"quote/([A-Z0-9_.\-]+:[A-Z0-9_.\-]+)", href)
            full_sym = m.group(1) if m else ""
            sym = full_sym.split(":")[0]

            # Symbol element in Beta
            sym_el = tr.find("span", class_="y9ljXe") or tr.find("div", class_="xh20qf")
            if sym_el:
                sym = sym_el.get_text(strip=True)

            if not sym or sym in seen or sym in self.SECTOR_SYMBOLS:
                continue
            seen.add(sym)

            # Company name in Beta
            name_el = tr.find("div", class_="sdnoWe") or a_el.get("aria-label")
            name = name_el.get_text(strip=True) if hasattr(name_el, "get_text") else (name_el or sym)

            # Current price in Beta
            price = 0.0
            price_el = tr.find("span", attrs={"jsname": "Pdsbrc"})
            if price_el:
                cleaned = re.sub(r"[^\d.]", "", price_el.get_text(strip=True))
                try:
                    price = float(cleaned)
                except ValueError:
                    pass

            # Shares and Buy Price from table columns (if user logged a portfolio)
            cells = tr.find_all("td")
            shares = 10.0
            buy_price = price if price > 0 else 100.0

            if "shares" in col_map and col_map["shares"] < len(cells):
                s_txt = re.sub(r"[^\d.]", "", cells[col_map["shares"]].get_text(strip=True))
                try:
                    if float(s_txt) > 0:
                        shares = float(s_txt)
                except ValueError:
                    pass

            if "buy_price" in col_map and col_map["buy_price"] < len(cells):
                bp_txt = re.sub(r"[^\d.]", "", cells[col_map["buy_price"]].get_text(strip=True))
                try:
                    if float(bp_txt) > 0:
                        buy_price = float(bp_txt)
                except ValueError:
                    pass

            holdings.append({
                "symbol": sym,
                "full_symbol": full_sym,
                "name": name,
                "shares": shares,
                "buy_price": buy_price,
                "current_price": price if price > 0 else buy_price,
                "currency": "USD",
                "dividend_yield": 0.0,
                "annual_div_per_share": 0.0,
            })

        return holdings

    def _parse_fallback_html(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Generalized fallback parser that scans for all anchor tags with quote links.
        """
        holdings = []
        seen = set()

        quote_links = soup.find_all("a", href=re.compile(r"quote/([A-Z0-9_.\-]+:[A-Z0-9_.\-]+)"))
        for a in quote_links:
            # Skip if inside nav, aside, or footer
            if a.find_parent(["nav", "aside", "footer"]):
                continue

            href = a.get("href", "")
            m = re.search(r"quote/([A-Z0-9_.\-]+:[A-Z0-9_.\-]+)", href)
            if not m:
                continue

            full_sym = m.group(1)
            raw_ticker = full_sym.split(":")[0]

            if raw_ticker in seen or raw_ticker in self.SECTOR_SYMBOLS:
                continue
            seen.add(raw_ticker)

            name = a.get("aria-label") or raw_ticker
            price = 0.0

            # Scan parent container
            container = a.find_parent(["div", "li", "tr", "section"]) or a.parent
            if container:
                strings = list(container.stripped_strings)
                for s in strings:
                    if re.match(r"^[$]?[\d,]+\.\d{2}$", s) and price == 0.0:
                        try:
                            price = float(re.sub(r"[^\d.]", "", s))
                        except ValueError:
                            pass
                    elif name == raw_ticker and len(s) > 2 and s not in (raw_ticker, full_sym, "Today", "1D", "1W", "1M", "1Y") and not re.match(r"^[+\-%0-9.,$—\s]+$", s):
                        name = s

            holdings.append({
                "symbol": raw_ticker,
                "full_symbol": full_sym,
                "name": name,
                "shares": 10.0,
                "buy_price": price if price > 0 else 100.0,
                "current_price": price if price > 0 else 100.0,
                "currency": "USD",
                "dividend_yield": 0.0,
                "annual_div_per_share": 0.0,
            })

        return holdings

    @staticmethod
    def parse_google_finance_csv(filepath: str, target_portfolio: str = "USD HSBC") -> List[Dict[str, Any]]:
        """
        Parses CSV files exported directly from Google Finance (Beta & standard versions).
        Handles various column headers: Symbol, Name, Price, Shares, Purchase price, etc.
        Assigns holdings to `target_portfolio`.
        """
        if not os.path.exists(filepath):
            return []

        holdings = []
        with open(filepath, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = None
            for line in reader:
                if not line:
                    continue
                upper_line = [c.strip().upper() for c in line]
                if "SYMBOL" in upper_line or "TICKER" in upper_line:
                    header = [c.strip() for c in line]
                    break

            if not header:
                return []

            dict_reader = csv.DictReader(f, fieldnames=header)
            for row in dict_reader:
                sym = None
                for col in ["Symbol", "symbol", "SYMBOL", "Ticker", "ticker"]:
                    if col in row and row[col]:
                        sym = row[col].strip()
                        break

                if not sym or sym.upper() in ("SYMBOL", "TICKER"):
                    continue

                clean_sym = sym.split(":")[-1] if ":" in sym and len(sym.split(":")[0]) > 4 else sym.split(":")[0]
                clean_sym = clean_sym.strip().upper()

                name = clean_sym
                for col in ["Name", "name", "NAME", "Company Name", "Description"]:
                    if col in row and row[col]:
                        name = row[col].strip()
                        break

                def _parse_num(candidates, default=0.0):
                    for c in candidates:
                        if c in row and row[c]:
                            val = re.sub(r"[^\d.]", "", row[c])
                            try:
                                return float(val)
                            except ValueError:
                                pass
                    return default

                shares = _parse_num(["Shares", "shares", "Quantity", "Holdings", "shares_owned", "Units"], default=10.0)
                buy_price = _parse_num(["Purchase price", "Purchase Price", "Buy Price", "Cost Basis / Share", "Average Cost", "buy_price"], default=0.0)
                current_price = _parse_num(["Current price", "Current Price", "Price", "Last Price", "current_price"], default=0.0)
                div_yield = _parse_num(["Dividend Yield", "Dividend Yield (%)", "Yield", "div_yield"], default=0.0)

                if buy_price <= 0 and current_price > 0:
                    buy_price = current_price

                s_shares = max(0.0001, shares)
                s_buy = max(0.0, buy_price)
                s_cur = max(0.0, current_price if current_price > 0 else buy_price)
                curr = row.get("Currency", "USD").strip().upper() or "USD"
                holding_dict = {
                    "portfolio": target_portfolio,
                    "symbol": clean_sym,
                    "name": name,
                    "shares": s_shares,
                    "buy_price": s_buy,
                    "current_price": s_cur,
                    "dividend_yield": div_yield,
                    "currency": curr,
                }
                summary = calc_holding_summary(s_shares, s_buy, s_cur, div_yield)
                holding_dict.update(summary)
                holdings.append(holding_dict)

        return holdings

    @staticmethod
    def export_to_google_finance_csv(filepath: str, holdings: List[Dict[str, Any]]) -> bool:
        fieldnames = ["Symbol", "Name", "Shares", "Purchase price", "Currency"]
        try:
            with open(filepath, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for h in holdings:
                    writer.writerow({
                        "Symbol": h.get("symbol", ""),
                        "Name": h.get("name", h.get("symbol", "")),
                        "Shares": f"{float(h.get('shares', 0.0)):.4f}",
                        "Purchase price": f"{float(h.get('buy_price', 0.0)):.2f}",
                        "Currency": h.get("currency", "USD"),
                    })
            return True
        except Exception as e:
            print(f"Error exporting to Google Finance CSV: {e}")
            return False
