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
        if exchange in ("TSE", "TSX", "TO"):
            return f"{ticker}.TO"
        elif exchange in ("HKG", "HK", "HKEX"):
            if ticker.isdigit():
                ticker = f"{int(ticker):04d}"
            return f"{ticker}.HK"
        elif exchange in ("LON", "LSE"):
            return f"{ticker}.L"
        return ticker
    if s in ("VFV", "VGRO", "ZAG", "XEF"):
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
        # Try yfinance first if available
        if YFINANCE_AVAILABLE:
            try:
                result = self._fetch_via_yfinance(raw_symbol, tf, cfg)
            except Exception as e:
                print(f"yfinance fetch failed for {raw_symbol}: {e}, falling back to direct API")

        # Zero-dependency fallback via built-in urllib
        if not result:
            result = self._fetch_via_urllib(raw_symbol, tf, cfg)

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
            "source": "yfinance",
        }

    def _fetch_via_urllib(self, raw_symbol: str, tf: str, cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        yf_sym = to_yfinance_symbol(raw_symbol)
        rng = cfg["period"]
        interval = cfg["interval"]
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?range={rng}&interval={interval}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
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
                for ts, c in zip(timestamps_raw, closes_raw):
                    if c is not None and ts is not None:
                        timestamps.append(datetime.fromtimestamp(ts, tz=timezone.utc))
                        prices.append(float(c))

                if not prices:
                    return None

                prev_close = meta.get("previousClose") or meta.get("chartPreviousClose") or prices[0]
                curr_price = prices[-1]
                change = curr_price - prev_close
                change_pct = (change / prev_close * 100) if prev_close > 0 else 0.0

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
                    "source": "urllib_fallback",
                }
        except Exception as e:
            print(f"urllib chart fetch error for {raw_symbol}: {e}")
            return None

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

        # Fetch series for each holding
        holding_series: List[Dict[datetime, float]] = []
        prev_closes_total = 0.0

        for h in holdings:
            sym = h.get("symbol", "")
            shares = float(h.get("shares", 0.0))
            if shares <= 0:
                continue

            hold_curr = h.get("currency", "USD").strip().upper() or "USD"
            rate = 1.0
            if converter and hold_curr != target_currency:
                rate = converter.convert(1.0, hold_curr, target_currency)

            h_data = self.fetch_symbol_history(sym, tf)
            if not h_data or not h_data.get("prices"):
                continue

            ts_list = h_data["timestamps"]
            pr_list = h_data["prices"]
            h_prev = h_data.get("prev_close", pr_list[0])
            prev_closes_total += (h_prev * shares * rate)

            series_dict = {}
            for t, p in zip(ts_list, pr_list):
                series_dict[t] = p * shares * rate
            holding_series.append(series_dict)

        if not holding_series:
            return None

        # Align timestamps across all holdings
        # If pandas is available, use fast concat
        timestamps = []
        prices = []

        if PANDAS_AVAILABLE:
            try:
                dfs = [pd.Series(s) for s in holding_series]
                combined = pd.concat(dfs, axis=1, sort=False).ffill().dropna()
                if not combined.empty:
                    tot_series = combined.sum(axis=1)
                    timestamps = [t.to_pydatetime() if hasattr(t, "to_pydatetime") else t for t in tot_series.index]
                    prices = tot_series.tolist()
            except Exception as e:
                print(f"Pandas portfolio alignment error: {e}, falling back to pure Python")

        # Pure Python fallback alignment (zero-dependencies)
        if not prices:
            all_ts = set()
            for s in holding_series:
                all_ts.update(s.keys())
            sorted_ts = sorted(all_ts)

            # Last known values for forward-fill
            last_known = [0.0] * len(holding_series)
            for t in sorted_ts:
                t_total = 0.0
                all_present = True
                for idx, s in enumerate(holding_series):
                    if t in s:
                        last_known[idx] = s[t]
                    if last_known[idx] <= 0:
                        all_present = False
                    t_total += last_known[idx]
                if all_present:
                    timestamps.append(t)
                    prices.append(t_total)

        if not prices:
            return None

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
