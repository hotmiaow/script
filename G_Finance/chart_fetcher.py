"""
Chart Data Fetcher for Google Finance Style Charts.
Fetches historical prices for individual stocks and calculates aggregate portfolio curves.
Supports standard timeframes: 1D, 5D, 1M, 6M, YTD, 1Y, 5Y, MAX.

Fallback Support:
- Tries yfinance and pandas first if installed.
- Automatically falls back to built-in urllib + json (standard library, zero external packages)
  if yfinance or pandas is not installed on the system.
"""

import time
import json
import urllib.request
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone

# Check package availability
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    yf = None
    YFINANCE_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    pd = None
    PANDAS_AVAILABLE = False


TIMEFRAME_CONFIGS = {
    "1D": {"period": "1d", "interval": "5m", "ttl": 60},
    "5D": {"period": "5d", "interval": "15m", "ttl": 120},
    "1M": {"period": "1mo", "interval": "1d", "ttl": 900},
    "6M": {"period": "6mo", "interval": "1d", "ttl": 3600},
    "YTD": {"period": "ytd", "interval": "1d", "ttl": 3600},
    "1Y": {"period": "1y", "interval": "1d", "ttl": 3600},
    "5Y": {"period": "5y", "interval": "1wk", "ttl": 86400},
    "MAX": {"period": "max", "interval": "1mo", "ttl": 86400},
}


def to_yfinance_symbol(symbol: str) -> str:
    """Convert a stock symbol (like VFV:TSE or 9988:HKG) to standard ticker format."""
    s = symbol.strip().upper()
    if ":" in s:
        parts = s.split(":")
        ticker, exchange = parts[0].strip(), parts[1].strip()
        if exchange in ("TSE", "TSX", "TO", "CDN", "CA"):
            return f"{ticker}.TO"
        elif exchange in ("HKG", "HK", "HKEX"):
            if ticker.isdigit():
                ticker = f"{int(ticker):04d}"
            return f"{ticker}.HK"
        elif exchange in ("LON", "LSE"):
            return f"{ticker}.L"
        return ticker
    if s.endswith(".HK") or s.endswith(".HKG"):
        prefix = s.split(".")[0].strip()
        if prefix.isdigit():
            return f"{int(prefix):04d}.HK"
        return f"{prefix}.HK"
    if s.endswith(".TO") or s.endswith(".TSE") or s.endswith(".CDN") or s.endswith(".CA") or s.endswith(".TSX"):
        prefix = s.split(".")[0].strip()
        return f"{prefix}.TO"
    if s.isdigit() and len(s) in (4, 5):
        return f"{int(s):04d}.HK"
    if s in ("VFV", "VGRO", "ZAG", "XEF", "XEQT", "VEQT"):
        return f"{s}.TO"
    return s


class ChartFetcher:
    def __init__(self):
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def _get_cache(self, key: str, ttl: float) -> Optional[Dict[str, Any]]:
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time.time() - timestamp < ttl:
                return data
        return None

    def _set_cache(self, key: str, data: Dict[str, Any]):
        self._cache[key] = (time.time(), data)

    def clear_cache(self):
        self._cache.clear()

    def fetch_symbol_history(self, raw_symbol: str, timeframe: str = "1D") -> Optional[Dict[str, Any]]:
        tf = timeframe.upper()
        if tf not in TIMEFRAME_CONFIGS:
            tf = "1D"
        cfg = TIMEFRAME_CONFIGS[tf]
        cache_key = f"sym:{raw_symbol}:{tf}"
        cached = self._get_cache(cache_key, cfg["ttl"])
        if cached:
            return cached

        result = None
        # Fast path: built-in lightweight urllib query (0.1s, zero external dependencies, 0MB RAM)
        try:
            result = self._fetch_via_urllib(raw_symbol, tf, cfg)
        except Exception:
            pass

        # Fallback to yfinance only if urllib failed and yfinance is installed
        if not result and YFINANCE_AVAILABLE:
            try:
                result = self._fetch_via_yfinance(raw_symbol, tf, cfg)
            except Exception:
                pass

        if result:
            self._set_cache(cache_key, result)
        return result

    def _fetch_via_yfinance(self, raw_symbol: str, tf: str, cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        yf_sym = to_yfinance_symbol(raw_symbol)
        ticker = yf.Ticker(yf_sym)
        df = ticker.history(period=cfg["period"], interval=cfg["interval"])
        if df.empty or "Close" not in df:
            return None

        closes = df["Close"].dropna()
        if closes.empty:
            return None

        timestamps = [ts.to_pydatetime() for ts in closes.index]
        prices = closes.tolist()

        prev_close = None
        try:
            prev_close = ticker.fast_info.get("previous_close", None)
        except Exception:
            pass

        if not prev_close or prev_close <= 0:
            prev_close = prices[0]

        curr_price = prices[-1]
        change = curr_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0.0

        div_events = []
        try:
            divs = ticker.dividends
            if divs is not None and not divs.empty:
                for dt, amt in divs.items():
                    if float(amt) > 0:
                        div_events.append((dt.to_pydatetime().astimezone(timezone.utc), float(amt)))
        except Exception:
            pass
        div_events.sort(key=lambda x: x[0])
        start_ts_val = timestamps[0].timestamp() if timestamps else 0.0
        end_ts_val = timestamps[-1].timestamp() if timestamps else time.time()
        period_div = sum(amt for dt, amt in div_events if start_ts_val <= dt.timestamp() <= end_ts_val)
        now_ts = time.time()
        one_yr_divs = [amt for dt, amt in div_events if dt.timestamp() >= (now_ts - 365 * 86400)]
        annual_div = sum(one_yr_divs) if one_yr_divs else (period_div if div_events else 0.0)

        return {
            "label": raw_symbol,
            "symbol": yf_sym,
            "timeframe": tf,
            "timestamps": timestamps,
            "prices": prices,
            "prev_close": float(prev_close),
            "current_price": float(curr_price),
            "change": float(change),
            "change_pct": float(change_pct),
            "currency": "USD" if not yf_sym.endswith(".TO") else "CAD",
            "dividend_events": div_events,
            "period_div_per_share": period_div,
            "annual_dividend_per_share": annual_div,
            "source": "yfinance",
        }

    def _fetch_via_urllib(self, raw_symbol: str, tf: str, cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        yf_sym = to_yfinance_symbol(raw_symbol)
        rng = cfg["period"]
        interval = cfg["interval"]

        def _do_query(host: str, q_rng: str, q_int: str) -> Optional[dict]:
            url = f"https://{host}/v8/finance/chart/{yf_sym}?range={q_rng}&interval={q_int}&events=div%7Csplit"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            try:
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    return json.loads(resp.read().decode())
            except Exception:
                return None

        data = _do_query("query1.finance.yahoo.com", rng, interval)
        if not data:
            data = _do_query("query2.finance.yahoo.com", rng, interval)

        # Special fallback for YTD: if range=ytd fails, try range=1y and filter from Jan 1
        is_ytd = (tf == "YTD")
        if not data and is_ytd:
            data = _do_query("query1.finance.yahoo.com", "1y", "1d") or _do_query("query2.finance.yahoo.com", "1y", "1d")

        if not data:
            return None

        chart_res = data.get("chart", {}).get("result")
        if not chart_res:
            return None
        res0 = chart_res[0]
        meta = res0.get("meta", {})
        timestamps_raw = res0.get("timestamp", [])
        indicators = res0.get("indicators", {}).get("quote", [{}])[0]
        closes_raw = indicators.get("close", [])

        timestamps = []
        prices = []
        now_dt = datetime.now(timezone.utc)
        jan1_dt = datetime(now_dt.year, 1, 1, tzinfo=timezone.utc) if is_ytd else None

        for ts, c in zip(timestamps_raw, closes_raw):
            if c is not None and ts is not None:
                dt_obj = datetime.fromtimestamp(ts, tz=timezone.utc)
                if is_ytd and dt_obj < jan1_dt:
                    continue
                timestamps.append(dt_obj)
                prices.append(float(c))

        if not prices:
            return None

        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose") or prices[0]
        curr_price = prices[-1]
        change = curr_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0.0

        div_events = []
        events = res0.get("events", {}).get("dividends", {})
        if events:
            for d_info in events.values():
                d_amount = float(d_info.get("amount", 0.0) or 0.0)
                d_ts = d_info.get("date")
                if d_amount > 0 and d_ts:
                    div_events.append((datetime.fromtimestamp(d_ts, tz=timezone.utc), d_amount))
        div_events.sort(key=lambda x: x[0])
        start_ts_val = timestamps[0].timestamp() if timestamps else 0.0
        end_ts_val = timestamps[-1].timestamp() if timestamps else time.time()
        period_div = sum(amt for dt, amt in div_events if start_ts_val <= dt.timestamp() <= end_ts_val)
        now_ts = time.time()
        one_yr_divs = [amt for dt, amt in div_events if dt.timestamp() >= (now_ts - 365 * 86400)]
        annual_div = sum(one_yr_divs) if one_yr_divs else (period_div if div_events else 0.0)

        return {
            "label": raw_symbol,
            "symbol": yf_sym,
            "timeframe": tf,
            "timestamps": timestamps,
            "prices": prices,
            "prev_close": float(prev_close),
            "current_price": float(curr_price),
            "change": float(change),
            "change_pct": float(change_pct),
            "currency": meta.get("currency", "USD" if not yf_sym.endswith(".TO") else "CAD"),
            "dividend_events": div_events,
            "period_div_per_share": period_div,
            "annual_dividend_per_share": annual_div,
            "source": "urllib_fallback",
        }

    def fetch_portfolio_history(
        self,
        holdings: List[Dict[str, Any]],
        portfolio_name: str,
        timeframe: str = "1D",
        converter=None,
        target_currency: str = "USD",
    ) -> Optional[Dict[str, Any]]:
        tf = timeframe.upper()
        if tf not in TIMEFRAME_CONFIGS:
            tf = "1D"
        cfg = TIMEFRAME_CONFIGS[tf]

        if not holdings:
            return None

        cache_key = f"port:{portfolio_name}:{target_currency}:{tf}:{len(holdings)}"
        cached = self._get_cache(cache_key, cfg["ttl"])
        if cached:
            return cached

        # Collect valid holdings and unique symbols
        valid_holdings = [h for h in holdings if float(h.get("shares", 0.0) or 0.0) > 0 and (h.get("symbol") or "").strip()]
        if not valid_holdings:
            return None

        unique_symbols = list({h.get("symbol", "").strip().upper() for h in valid_holdings})

        # Fetch missing symbols in parallel with fast timeout
        symbol_data_map: Dict[str, Dict[str, Any]] = {}
        missing_symbols = []
        for sym in unique_symbols:
            cached_sym = self._get_cache(f"sym:{sym}:{tf}", cfg["ttl"])
            if cached_sym:
                symbol_data_map[sym] = cached_sym
            else:
                missing_symbols.append(sym)

        if missing_symbols:
            import concurrent.futures
            max_workers = min(4, len(missing_symbols))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_sym = {executor.submit(self.fetch_symbol_history, sym, tf): sym for sym in missing_symbols}
                try:
                    for future in concurrent.futures.as_completed(future_to_sym, timeout=3.0):
                        sym = future_to_sym[future]
                        try:
                            res = future.result()
                            if res and res.get("prices"):
                                symbol_data_map[sym] = res
                        except Exception:
                            pass
                except concurrent.futures.TimeoutError:
                    pass

        # Assemble holding series with normalized date keys
        holding_series: List[Dict[str, float]] = []
        prev_closes_total = 0.0
        date_to_dt: Dict[str, Any] = {}

        for h in valid_holdings:
            sym = (h.get("symbol") or "").strip().upper()
            shares = float(h.get("shares", 0.0))
            hold_curr = (h.get("currency") or "USD").strip().upper() or "USD"
            rate = 1.0
            if converter and hold_curr != target_currency:
                rate = converter.convert(1.0, hold_curr, target_currency)

            h_data = symbol_data_map.get(sym)
            if not h_data or not h_data.get("prices"):
                continue

            ts_list = h_data["timestamps"]
            pr_list = h_data["prices"]
            h_prev = h_data.get("prev_close", pr_list[0])
            prev_closes_total += (h_prev * shares * rate)

            series_dict = {}
            for t, p in zip(ts_list, pr_list):
                if hasattr(t, "strftime"):
                    date_key = t.strftime("%H:%M") if tf == "1D" else t.strftime("%Y-%m-%d")
                    date_to_dt[date_key] = t
                else:
                    date_key = str(t)[:10]
                    date_to_dt[date_key] = t
                series_dict[date_key] = p * shares * rate
            if series_dict:
                holding_series.append(series_dict)

        if not holding_series:
            return None

        # Robust Alignment: Normalized date keys, forward-fill & backward-fill
        all_dates = sorted(list({k for s in holding_series for k in s.keys()}))
        if not all_dates:
            return None

        # Pre-seed last_known with earliest price of each holding so earlier dates are preserved
        last_known = []
        for s in holding_series:
            first_key = min(s.keys())
            last_known.append(s[first_key])

        timestamps = []
        prices = []
        for d in all_dates:
            for idx, s in enumerate(holding_series):
                if d in s:
                    last_known[idx] = s[d]
            t_total = sum(last_known)
            if t_total > 0:
                dt_obj = date_to_dt.get(d)
                if dt_obj is None or not hasattr(dt_obj, "strftime"):
                    try:
                        if tf == "1D" and ":" in str(d):
                            now_d = datetime.now(timezone.utc).date()
                            parsed_t = datetime.strptime(str(d), "%H:%M").time()
                            dt_obj = datetime.combine(now_d, parsed_t, tzinfo=timezone.utc)
                        elif "-" in str(d):
                            dt_obj = datetime.strptime(str(d)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        else:
                            dt_obj = d
                    except Exception:
                        dt_obj = d
                timestamps.append(dt_obj)
                prices.append(round(t_total, 2))

        if len(prices) < 2:
            return None

        # Calculate expected total current value for valid holdings and scale if partial
        tot_curr_val = 0.0
        for h in valid_holdings:
            shs = float(h.get("shares", 0.0) or 0.0)
            cp = float(h.get("current_price", h.get("price", 0.0)) or 0.0)
            c = (h.get("currency") or "USD").strip().upper()
            rate = converter.convert(1.0, c, target_currency) if (converter and c != target_currency) else 1.0
            tot_curr_val += (shs * cp * rate)

        if tot_curr_val > 0 and len(prices) > 0 and prices[-1] > 0 and len(holding_series) < len(valid_holdings):
            scale = tot_curr_val / prices[-1]
            prices = [round(p * scale, 2) for p in prices]
            prev_closes_total = prev_closes_total * scale

        if tot_curr_val > 0 and prices:
            prices[-1] = round(tot_curr_val, 2)

        curr_price = prices[-1]
        if prev_closes_total <= 0:
            prev_closes_total = prices[0]

        change = curr_price - prev_closes_total
        change_pct = (change / prev_closes_total * 100) if prev_closes_total > 0 else 0.0

        result = {
            "label": portfolio_name,
            "portfolio": portfolio_name,
            "timeframe": tf,
            "timestamps": timestamps,
            "prices": prices,
            "prev_close": float(prev_closes_total),
            "current_price": float(curr_price),
            "change": float(change),
            "change_pct": float(change_pct),
            "currency": target_currency,
        }
        self._set_cache(cache_key, result)
        return result


_fetcher_instance = None

def get_chart_fetcher() -> ChartFetcher:
    global _fetcher_instance
    if _fetcher_instance is None:
        _fetcher_instance = ChartFetcher()
    return _fetcher_instance
