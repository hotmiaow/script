import unittest
from chart_fetcher import to_yfinance_symbol, get_chart_fetcher, TIMEFRAME_CONFIGS


class TestChartFetcher(unittest.TestCase):
    def test_symbol_resolution(self):
        self.assertEqual(to_yfinance_symbol("VFV:TSE"), "VFV.TO")
        self.assertEqual(to_yfinance_symbol("VGRO:TSX"), "VGRO.TO")
        self.assertEqual(to_yfinance_symbol("9988:HKG"), "9988.HK")
        self.assertEqual(to_yfinance_symbol("700:HKG"), "0700.HK")
        self.assertEqual(to_yfinance_symbol("0005"), "0005.HK")
        self.assertEqual(to_yfinance_symbol("0005.HK"), "0005.HK")
        self.assertEqual(to_yfinance_symbol("1137"), "1137.HK")
        self.assertEqual(to_yfinance_symbol("1137.HK"), "1137.HK")
        self.assertEqual(to_yfinance_symbol("VOO"), "VOO")
        self.assertEqual(to_yfinance_symbol("INTC"), "INTC")
        self.assertEqual(to_yfinance_symbol("VFV"), "VFV.TO")

    def test_timeframe_configs(self):
        for tf in ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"]:
            self.assertIn(tf, TIMEFRAME_CONFIGS)
            self.assertIn("period", TIMEFRAME_CONFIGS[tf])
            self.assertIn("interval", TIMEFRAME_CONFIGS[tf])

    def test_fetch_symbol_caching(self):
        from datetime import datetime
        fetcher = get_chart_fetcher()
        mock_data = {
            "symbol": "VOO",
            "timeframe": "1D",
            "prices": [450.0, 452.0],
            "timestamps": [datetime.now(), datetime.now()],
            "prev_close": 448.0,
            "currency": "USD",
            "current_price": 452.0,
            "change": 4.0,
            "change_pct": 0.89,
        }
        fetcher._set_cache("sym:VOO:1D", mock_data)
        res1 = fetcher.fetch_symbol_history("VOO", "1D")
        self.assertIsNotNone(res1)
        self.assertIn("prices", res1)
        self.assertGreater(len(res1["prices"]), 0)
        self.assertEqual(res1["symbol"], "VOO")

        # Second call should come from cache immediately
        res2 = fetcher.fetch_symbol_history("VOO", "1D")
        self.assertEqual(res1["current_price"], res2["current_price"])


if __name__ == "__main__":
    unittest.main()
