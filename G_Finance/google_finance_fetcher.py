"""
Google Finance Fetcher Module
Fetches real-time market data, company details, dividends, and metrics from Google Finance.
Supports automatic exchange detection (NASDAQ, NYSE, NYSEARCA, etc.).
"""

import re
import urllib.parse
from typing import Dict, Any, Optional, Tuple
import requests
from bs4 import BeautifulSoup
import time
import json
from datetime import datetime


class GoogleFinanceFetcher:
    COMMON_EXCHANGES = ["NASDAQ", "NYSE", "NYSEARCA", "BATS", "TSX", "TSE", "HKG", "INDEXDJX", "INDEXSP"]
    
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

    def _normalize_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        return (
            text.replace("\u2212", "-")
            .replace("\u2013", "-")
            .replace("\u2014", "-")
            .replace("&minus;", "-")
            .strip()
        )

    def _clean_number(self, text: Optional[str]) -> Optional[float]:
        if not text:
            return None
        norm = self._normalize_text(text)
        cleaned = re.sub(r"[^\d.\-+]", "", norm)
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    def _clean_price(self, text: Optional[str]) -> Optional[float]:
        if not text:
            return None
        norm = self._normalize_text(text)
        match = re.search(r"[$€£¥]?\s*([\d,]+\.?\d*)", norm)
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
        norm = self._normalize_text(text)
        match = re.search(r"([+-]?[\d,]+\.?\d*)\s*%", norm)
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

        # Handle Yahoo / Canadian / Hong Kong style suffixes
        if sym.endswith(".HK") or sym.endswith(".HKG"):
            prefix = sym.split(".")[0].strip()
            if prefix.isdigit():
                prefix = f"{int(prefix):04d}"
            hk_sym = f"{prefix}:HKG"
            res = self._fetch_url(f"https://www.google.com/finance/quote/{hk_sym}", hk_sym)
            if res.get("success"):
                return res

        if sym.endswith(".TO") or sym.endswith(".TSE"):
            prefix = sym.split(".")[0].strip()
            to_sym = f"{prefix}:TSE"
            res = self._fetch_url(f"https://www.google.com/finance/quote/{to_sym}", to_sym)
            if res.get("success"):
                return res

        if sym.isdigit() and len(sym) in (4, 5):
            hk_sym = f"{int(sym):04d}:HKG"
            res = self._fetch_url(f"https://www.google.com/finance/quote/{hk_sym}", hk_sym)
            if res.get("success"):
                return res

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
        direction = 1.0

        # Scope search to the price container / hero first to avoid catching the top market indices carousel
        hero = None
        if price_el:
            hero = price_el.parent
        if not hero:
            hero = soup.find("div", class_="JZvoCc") or soup.find("c-wiz")

        if hero:
            # Check arrow direction (arrow_upward vs arrow_downward)
            arrow_node = hero.find("i", class_=re.compile(r"google-material-icons"))
            if arrow_node:
                arr_text = arrow_node.get_text(strip=True).lower()
                if "down" in arr_text:
                    direction = -1.0
                elif "up" in arr_text:
                    direction = 1.0

            # 1. Percent node: jsname="vY9t3b" (Standard Google Finance percentage change)
            pct_node = hero.find(attrs={"jsname": "vY9t3b"})
            if pct_node:
                raw_p_text = self._normalize_text(pct_node.get_text(strip=True))
                raw_p = self._clean_percent(raw_p_text)
                if raw_p is not None:
                    if raw_p_text.startswith("-"):
                        pct_change_val = -abs(raw_p)
                    elif raw_p_text.startswith("+"):
                        pct_change_val = abs(raw_p)
                    else:
                        pct_change_val = round(direction * abs(raw_p), 2)

            # 2. Currency change node: jsname="xnruHf" (Standard Google Finance amount change)
            chg_node = hero.find(attrs={"jsname": "xnruHf"})
            if chg_node:
                raw_c_text = self._normalize_text(chg_node.get_text(strip=True))
                raw_c = self._clean_number(raw_c_text)
                if raw_c is not None and abs(raw_c) < current_price:
                    if raw_c_text.startswith("-"):
                        change_val = -abs(raw_c)
                    elif raw_c_text.startswith("+"):
                        change_val = abs(raw_c)
                    else:
                        change_val = round(direction * abs(raw_c), 2)

            # 3. Check aria-labels scoped ONLY within hero/price container
            if change_val is None or pct_change_val is None:
                for el in hero.find_all(attrs={"aria-label": True}):
                    aria = self._normalize_text(el.get("aria-label", ""))
                    m_aria = re.search(r"(Up|Down|Increased|Decreased|dropped|gained)\s*(?:by\s*)?([$€£¥]?\s*[\d,]+\.?\d+)\s*(?:\((?:by\s*)?([$€£¥]?\s*[\d,]+\.?\d+)\s*%\))?", aria, re.I)
                    if m_aria:
                        d = -1.0 if m_aria.group(1).lower() in ("down", "decreased", "dropped") else 1.0
                        if m_aria.group(2) and change_val is None:
                            try:
                                raw_c = float(re.sub(r"[$€£¥\s,]", "", m_aria.group(2)))
                                if raw_c < current_price:
                                    change_val = round(d * raw_c, 2)
                            except ValueError:
                                pass
                        if m_aria.group(3) and pct_change_val is None:
                            try:
                                raw_p = float(re.sub(r"[$€£¥\s,]", "", m_aria.group(3)))
                                pct_change_val = round(d * raw_p, 2)
                            except ValueError:
                                pass

            # 4. Check JwB6zf or other change elements inside hero
            if pct_change_val is None or change_val is None:
                for jw in hero.find_all(class_=re.compile(r"JwB6zf")):
                    t = self._normalize_text(jw.get_text(strip=True))
                    if "%" in t and pct_change_val is None:
                        pct_change_val = self._clean_percent(t)
                    elif any(t.startswith(x) for x in ["+", "-", "("]) and change_val is None:
                        c = self._clean_number(t)
                        if c is not None and abs(c) < current_price:
                            change_val = c

        # Fallback to JwB6zf across soup (excluding ymyBi market index chips)
        if pct_change_val is None:
            pct_el = (
                soup.find("div", class_=re.compile(r"JwB6zf"))
                or soup.find("span", class_=re.compile(r"JwB6zf"))
                or soup.find(class_=re.compile(r"(NydbP|V55Du|BAA5Fd)"))
            )
            if pct_el:
                pct_change_text = self._normalize_text(pct_el.get_text(strip=True))
                pct_change_val = self._clean_percent(pct_change_text)

        # Cross-calculate if one is found and the other is missing
        if change_val is not None and pct_change_val is None and current_price > 0 and (current_price - change_val) > 0:
            pct_change_val = round((change_val / (current_price - change_val)) * 100, 2)
        elif pct_change_val is not None and change_val is None and current_price > 0:
            pct_dec = pct_change_val / 100.0
            prev_p = current_price / (1.0 + pct_dec) if (1.0 + pct_dec) != 0 else current_price
            change_val = round(current_price - prev_p, 2)

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

        # Fallback to Previous close if change_val is still None
        if change_val is None:
            prev_close_text = stats.get("Previous close") or stats.get("Prev close")
            prev_close = self._clean_price(prev_close_text) if prev_close_text else None
            if prev_close and prev_close > 0 and current_price > 0:
                change_val = round(current_price - prev_close, 2)
                if pct_change_val is None:
                    pct_change_val = round((change_val / prev_close) * 100, 2)

        # 6. Parse Dividend Info
        div_yield_text = (
            stats.get("Dividend")
            or stats.get("Dividend yield")
            or stats.get("Yield")
            or stats.get("Trailing 12-month dividend yield")
            or stats.get("Trailing 12-month distribution yield")
            or stats.get("Distribution yield")
            or stats.get("30-day SEC yield")
            or stats.get("SEC yield")
            or "0.00%"
        )
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

        # Automatic fallback for ETFs and dividend payers if Google Finance omitted yield
        if (div_yield <= 0.0 or annual_div_per_share <= 0.0) and current_price > 0:
            fb = self._fetch_dividend_fallback(symbol, current_price)
            if fb:
                div_yield, annual_div_per_share = fb
                quarterly_div = round(annual_div_per_share / 4.0, 4)

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
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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

    def _fetch_dividend_fallback(self, raw_symbol: str, current_price: float) -> Optional[Tuple[float, float]]:
        """
        Lightweight fallback to query Yahoo Finance dividend events when Google Finance omits dividend yield (common for ETFs).
        """
        try:
            import urllib.request
            from chart_fetcher import to_yfinance_symbol
            yf_sym = to_yfinance_symbol(raw_symbol)
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?range=1y&interval=1mo&events=div"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode())
                res = data.get("chart", {}).get("result", [])
                if res:
                    events = res[0].get("events", {}).get("dividends", {})
                    if events:
                        now = time.time()
                        one_year_ago = now - 365 * 86400
                        recent_divs = [float(v["amount"]) for v in events.values() if v.get("date", 0) >= one_year_ago]
                        if not recent_divs:
                            recent_divs = [float(v["amount"]) for v in events.values()]
                        total_annual_div = round(sum(recent_divs), 4)
                        if total_annual_div > 0 and current_price > 0:
                            div_yield = round((total_annual_div / current_price) * 100, 2)
                            return div_yield, total_annual_div
        except Exception:
            pass
        return None
