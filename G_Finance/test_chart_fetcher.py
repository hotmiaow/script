import unittest
from chart_fetcher import to_yfinance_symbol, get_chart_fetcher, TIMEFRAME_CONFIGS


class TestChartFetcher(unittest.TestCase):
    def test_symbol_resolution(self):
        self.assertEqual(to_yfinance_symbol("VFV:TSE"), "VFV.TO")
        self.assertEqual(to_yfinance_symbol("VGRO:TSX"), "VGRO.TO")
        self.assertEqual(to_yfinance_symbol("9988:HKG"), "9988.HK")
        self.assertEqual(to_yfinance_symbol("700:HKG"), "0700.HK")
        self.assertEqual(to_yfinance_symbol("VOO"), "VOO")
        self.assertEqual(to_yfinance_symbol("INTC"), "INTC")
        self.assertEqual(to_yfinance_symbol("VFV"), "VFV.TO")

    def test_timeframe_configs(self):
        for tf in ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"]:
            self.assertIn(tf, TIMEFRAME_CONFIGS)
            self.assertIn("period", TIMEFRAME_CONFIGS[tf])
            self.assertIn("interval", TIMEFRAME_CONFIGS[tf])

    def test_fetch_symbol_caching(self):
        fetcher = get_chart_fetcher()
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
