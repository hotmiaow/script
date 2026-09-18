"""
Google Finance Fetcher Module
Fetches real-time market data, company details, dividends, and metrics from Google Finance.
Supports automatic exchange detection (NASDAQ, NYSE, NYSEARCA, etc.).
"""

import re
import urllib.parse
from typing import Dict, Any, Optional
import requests
from bs4 import BeautifulSoup


class GoogleFinanceFetcher:
    COMMON_EXCHANGES = ["NASDAQ", "NYSE", "NYSEARCA", "TSE", "TSX", "HKG", "BATS", "INDEXDJX", "INDEXSP"]
    
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def __init__(self, timeout: int = 10):
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.timeout = timeout
        self.fx_cache: Dict[str, float] = {}

    def fetch_fx_rate(self, from_curr: str, to_curr: str) -> float:
        """
        Fetches live currency conversion rate (e.g. from CNY to USD).
        Uses memory cache and queries Google Finance FX pair (e.g. CNY-USD).
        """
        f = from_curr.strip().upper()
        t = to_curr.strip().upper()
        if f == t or not f or not t:
            return 1.0

        pair_key = f"{f}_{t}"
        if pair_key in self.fx_cache:
            return self.fx_cache[pair_key]

        baselines = {
            "CNY_USD": 0.14,
            "USD_CNY": 7.15,
            "EUR_USD": 1.08,
            "USD_EUR": 0.92,
            "GBP_USD": 1.30,
            "USD_GBP": 0.77,
            "CAD_USD": 0.74,
            "USD_CAD": 1.36,
            "JPY_USD": 0.0068,
            "USD_JPY": 147.0,
            "HKD_USD": 0.128,
            "USD_HKD": 7.80,
        }

        quote_pair = f"{f}-{t}"
        quote = self.fetch_quote(quote_pair)
        if quote.get("success") and quote.get("price", 0.0) > 0:
            rate = float(quote["price"])
            self.fx_cache[pair_key] = rate
            if rate > 0:
                self.fx_cache[f"{t}_{f}"] = round(1.0 / rate, 6)
            return rate

        inv_pair = f"{t}-{f}"
        inv_quote = self.fetch_quote(inv_pair)
        if inv_quote.get("success") and inv_quote.get("price", 0.0) > 0:
            rate = round(1.0 / float(inv_quote["price"]), 6)
            self.fx_cache[pair_key] = rate
            return rate

        fallback = baselines.get(pair_key, 1.0)
        self.fx_cache[pair_key] = fallback
        return fallback

    def _clean_number(self, text: Optional[str]) -> Optional[float]:
        if not text:
            return None
        cleaned = re.sub(r"[^\d.\-+]", "", text)
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    def _clean_price(self, text: Optional[str]) -> Optional[float]:
        if not text:
            return None
        match = re.search(r"[\$€£¥]?\s*([\d,]+\.?\d*)", text)
        if match:
            num_str = match.group(1).replace(",", "")
            try:
                return float(num_str)
            except ValueError:
                return None
        return None

    def _clean_percent(self, text: Optional[str]) -> Optional[float]:
        if not text:
            return None
        match = re.search(r"([+-]?[\d,]+\.?\d*)\s*%", text)
        if match:
            num_str = match.group(1).replace(",", "")
            try:
                return float(num_str)
            except ValueError:
                return None
        return None

    def fetch_quote(self, symbol_or_query: str) -> Dict[str, Any]:
        """
        Fetch quote from Google Finance.
        symbol_or_query can be:
          - 'AAPL'
          - 'AAPL:NASDAQ'
          - 'KO:NYSE'
          - 'SPY:NYSEARCA'
        """
        sym = symbol_or_query.strip().upper()
        if not sym:
            return {"success": False, "error": "Empty ticker provided"}

        # If exchange is explicitly specified
        if ":" in sym:
            return self._fetch_url(f"https://www.google.com/finance/quote/{sym}", sym)

        # Try direct symbol first
        res = self._fetch_url(f"https://www.google.com/finance/quote/{sym}", sym)
        if res.get("success"):
            return res

        # Try common exchanges
        for ex in self.COMMON_EXCHANGES:
            attempt_sym = f"{sym}:{ex}"
            url = f"https://www.google.com/finance/quote/{attempt_sym}"
            res = self._fetch_url(url, attempt_sym)
            if res.get("success"):
                return res

        return {
            "success": False,
            "symbol": sym,
            "error": f"Could not find quote for symbol '{sym}' on Google Finance."
        }

    def search_or_verify_symbol(self, query: str) -> Dict[str, Any]:
        """
        Quickly verifies a symbol or company ticker and retrieves current quote and metadata.
        """
        quote = self.fetch_quote(query)
        if quote.get("success"):
            return {
                "valid": True,
                "symbol": quote["symbol"].split(":")[0],
                "full_symbol": quote["symbol"],
                "name": quote["name"],
                "price": quote["price"],
                "currency": quote.get("currency", "USD"),
                "dividend_yield": quote.get("dividend_yield", 0.0),
                "annual_dividend_per_share": quote.get("annual_dividend_per_share", 0.0),
                "change_percent": quote.get("change_percent"),
            }
        return {
            "valid": False,
            "symbol": query.strip().upper(),
            "error": quote.get("error", "Symbol could not be verified on Google Finance."),
        }

    def _fetch_url(self, url: str, symbol: str) -> Dict[str, Any]:
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if resp.status_code != 200:
                return {"success": False, "symbol": symbol, "error": f"HTTP {resp.status_code}"}

            soup = BeautifulSoup(resp.text, "html.parser")
            return self._parse_html(soup, symbol, url)
        except requests.exceptions.RequestException as e:
            return {"success": False, "symbol": symbol, "error": f"Network error: {str(e)}"}
        except Exception as e:
            return {"success": False, "symbol": symbol, "error": f"Parsing error: {str(e)}"}

    def _parse_html(self, soup: BeautifulSoup, symbol: str, url: str) -> Dict[str, Any]:
        title = soup.title.get_text() if soup.title else ""
        if "Google Finance - Stock Market Prices, Real-time Quotes & Business News" == title.strip():
            return {"success": False, "symbol": symbol, "error": "Ticker not found"}

        # 1. Company Name
        name_el = (
            soup.find("div", class_="gO24Ff")
            or soup.find("div", class_="zzDege")
            or soup.find("div", class_="e1Du2d")
        )
        name = name_el.get_text(strip=True) if name_el else symbol.split(":")[0]

        # 2. Current Price
        price_el = (
            soup.find("div", class_="N6SYTe")
            or soup.find("div", class_="YMlKec fxKbKc")
            or soup.find("div", class_=re.compile(r"YMlKec"))
        )
        price_text = price_el.get_text(strip=True) if price_el else None
        current_price = self._clean_price(price_text)

        if current_price is None:
            hero = soup.find("div", class_="JZvoCc")
            if hero:
                for span in hero.find_all(["span", "div"]):
                    t = span.get_text(strip=True)
                    if re.match(r"^\$[\d,]+\.\d{2}$", t):
                        current_price = self._clean_price(t)
                        price_text = t
                        break

        if current_price is None:
            return {"success": False, "symbol": symbol, "error": "Price element not found on page"}

        # 3. Price Change and Percent Change
        change_text = None
        pct_change_text = None
        change_val = None
        pct_change_val = None

        pct_el = (
            soup.find("span", class_="ymyBi")
            or soup.find("div", class_=re.compile(r"JwB6zf"))
            or soup.find("span", class_=re.compile(r"JwB6zf"))
        )
        if pct_el:
            pct_change_text = pct_el.get_text(strip=True)
            pct_change_val = self._clean_percent(pct_change_text)

        hero = soup.find("div", class_="JZvoCc")
        if hero:
            for span in hero.find_all(["span", "div"]):
                t = span.get_text(strip=True)
                if "%" in t and pct_change_val is None:
                    pct_change_val = self._clean_percent(t)
                    pct_change_text = t
                elif (t.startswith("+") or t.startswith("-") or (t.startswith("(") and t.endswith(")"))) and change_val is None:
                    c = self._clean_number(t)
                    if c is not None and abs(c) < current_price:
                        change_val = c
                        change_text = t

        # 4. Currency and Timestamp
        currency = "USD"
        meta_sub = soup.find("div", class_="jZZ2de") or soup.find("div", class_="ygUjEc")
        timestamp = ""
        if meta_sub:
            sub_text = meta_sub.get_text(strip=True)
            parts = sub_text.split("·")
            if len(parts) >= 2:
                timestamp = parts[0].strip()
                currency = parts[-1].strip()
            else:
                timestamp = sub_text

        # 5. Extract Key Stats
        stats = {}
        for item in soup.find_all("div", class_="KxsRFb"):
            lbl = item.find("div", class_="SwQK7")
            val = item.find("div", class_="dO6ijd")
            if lbl and val:
                stats[lbl.get_text(strip=True)] = val.get_text(strip=True)

        for item in soup.find_all("div", class_="gyFHrc"):
            lbl = item.find("div", class_="mfs7Fc")
            val = item.find("div", class_="P6K39c")
            if lbl and val:
                stats[lbl.get_text(strip=True)] = val.get_text(strip=True)

        # 6. Parse Dividend Info
        div_yield_text = stats.get("Dividend") or stats.get("Dividend yield") or "0.00%"
        div_yield = self._clean_percent(div_yield_text) or 0.0

        quarterly_div_text = stats.get("Quarterly dividend")
        quarterly_div = self._clean_price(quarterly_div_text) if quarterly_div_text else None

        if quarterly_div is not None and quarterly_div > 0:
            annual_div_per_share = round(quarterly_div * 4, 4)
            if div_yield == 0.0 and current_price > 0:
                div_yield = round((annual_div_per_share / current_price) * 100, 2)
        elif div_yield > 0 and current_price > 0:
            annual_div_per_share = round(current_price * (div_yield / 100.0), 4)
            quarterly_div = round(annual_div_per_share / 4.0, 4)
        else:
            annual_div_per_share = 0.0
            quarterly_div = 0.0

        ex_div_date = stats.get("Ex-dividend date", "N/A")
        pe_ratio = self._clean_number(stats.get("P/E ratio"))
        high_52w = self._clean_price(stats.get("52-wk high"))
        low_52w = self._clean_price(stats.get("52-wk low"))
        market_cap = stats.get("Mkt. cap") or stats.get("Market cap") or "N/A"
        volume = stats.get("Volume") or "N/A"

        return {
            "success": True,
            "symbol": symbol,
            "name": name,
            "price": current_price,
            "price_text": price_text or f"${current_price:.2f}",
            "change": change_val,
            "change_percent": pct_change_val,
            "currency": currency,
            "timestamp": timestamp,
            "dividend_yield": div_yield,
            "quarterly_dividend": quarterly_div,
            "annual_dividend_per_share": annual_div_per_share,
            "ex_dividend_date": ex_div_date,
            "pe_ratio": pe_ratio,
            "52_week_high": high_52w,
            "52_week_low": low_52w,
            "market_cap": market_cap,
            "volume": volume,
            "url": url,
            "raw_stats": stats,
        }
