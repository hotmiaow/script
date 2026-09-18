"""
Currency Converter Module
Provides real-time exchange rates (e.g. USD, CAD, HKD) from Google Finance with caching,
offline fallback rates, and automatic currency conversion for portfolio summaries.
"""

import threading
import time
from typing import Dict, Optional, Tuple
from google_finance_fetcher import GoogleFinanceFetcher


class CurrencyConverter:
    """
    Manages exchange rates between major currencies (USD, CAD, HKD, EUR, GBP).
    Uses Google Finance quote queries (e.g. 'USD-CAD', 'USD-HKD') with thread-safe caching.
    """

    # Baseline fallback rates relative to 1 USD
    DEFAULT_USD_RATES: Dict[str, float] = {
        "USD": 1.0,
        "CAD": 1.399,
        "HKD": 7.845,
        "EUR": 0.925,
        "GBP": 0.775,
        "JPY": 155.0,
        "CNY": 7.25,
    }

    CURRENCY_SYMBOLS: Dict[str, str] = {
        "USD": "$",
        "CAD": "C$",
        "HKD": "HK$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
        "CNY": "¥",
    }

    def __init__(self, fetcher: Optional[GoogleFinanceFetcher] = None, cache_ttl_sec: int = 1800):
        self.fetcher = fetcher or GoogleFinanceFetcher()
        self.cache_ttl_sec = cache_ttl_sec
        self._rates_to_usd: Dict[str, float] = dict(self.DEFAULT_USD_RATES)
        self._last_update: float = 0.0
        self._lock = threading.Lock()
        self._is_refreshing = False

    def get_usd_rate(self, currency: str) -> float:
        """
        Returns how many units of `currency` equal 1 USD.
        e.g. for CAD: 1.399 (meaning 1 USD = 1.399 CAD).
        """
        curr = currency.upper().strip()
        with self._lock:
            return self._rates_to_usd.get(curr, 1.0)

    def get_rate(self, from_curr: str, to_curr: str) -> float:
        """
        Returns conversion multiplier from `from_curr` to `to_curr`.
        multiplier = rate(to_curr) / rate(from_curr) relative to USD base.
        e.g., 1 CAD in USD = 1.0 / 1.399 = ~0.7148 USD.
        """
        f = from_curr.upper().strip()
        t = to_curr.upper().strip()
        if f == t:
            return 1.0

        r_from = self.get_usd_rate(f)
        r_to = self.get_usd_rate(t)

        if r_from <= 0:
            return 1.0
        return r_to / r_from

    def convert(self, amount: float, from_curr: str, to_curr: str) -> float:
        """
        Converts an amount from `from_curr` to `to_curr`.
        """
        rate = self.get_rate(from_curr, to_curr)
        return round(amount * rate, 2)

    def format_money(self, amount: float, currency: str) -> str:
        """
        Formats money with appropriate currency symbol and commas.
        e.g. US$1,234.56, C$1,234.56, HK$1,234.56.
        """
        curr = currency.upper().strip()
        sym = self.CURRENCY_SYMBOLS.get(curr, "$")
        sign = "-" if amount < 0 else ""
        abs_amt = abs(amount)
        return f"{sign}{sym}{abs_amt:,.2f}"

    def get_rates_summary(self, base_currency: str = "USD") -> str:
        """
        Returns a concise string of active exchange rates for UI badges.
        e.g., '1 USD = 1.40 CAD | 7.85 HKD'
        """
        b = base_currency.upper().strip()
        r_cad = self.get_rate(b, "CAD")
        r_usd = self.get_rate(b, "USD")
        r_hkd = self.get_rate(b, "HKD")

        if b == "USD":
            return f"1 USD = {r_cad:.3f} CAD | {r_hkd:.3f} HKD"
        elif b == "CAD":
            return f"1 CAD = {r_usd:.3f} USD | {r_hkd:.3f} HKD"
        elif b == "HKD":
            return f"1 HKD = {r_usd:.4f} USD | {r_cad:.4f} CAD"
        return f"Rates relative to {b}"

    def refresh_rates_async(self):
        """
        Spawns a background thread to fetch current live FX rates from Google Finance.
        """
        with self._lock:
            if self._is_refreshing:
                return
            if (time.time() - self._last_update) < self.cache_ttl_sec:
                return
            self._is_refreshing = True

        def worker():
            try:
                pairs = [
                    ("USD-CAD", "CAD"),
                    ("USD-HKD", "HKD"),
                    ("EUR-USD", "EUR"),
                    ("GBP-USD", "GBP"),
                    ("USD-CNY", "CNY"),
                    ("USD-JPY", "JPY"),
                ]
                new_rates = {}
                for pair, curr in pairs:
                    quote = self.fetcher.fetch_quote(pair)
                    if quote.get("success") and quote.get("price", 0) > 0:
                        p = float(quote["price"])
                        if pair.startswith("USD-"):
                            new_rates[curr] = p
                        else:
                            # e.g. EUR-USD gives USD per EUR -> invert for EUR per USD
                            new_rates[curr] = 1.0 / p

                with self._lock:
                    self._rates_to_usd.update(new_rates)
                    self._last_update = time.time()
            except Exception as e:
                print(f"Failed to refresh currency rates: {e}")
            finally:
                with self._lock:
                    self._is_refreshing = False

        t = threading.Thread(target=worker, daemon=True)
        t.start()


# Global singleton instance
_GLOBAL_CONVERTER = CurrencyConverter()


def get_currency_converter() -> CurrencyConverter:
    return _GLOBAL_CONVERTER
