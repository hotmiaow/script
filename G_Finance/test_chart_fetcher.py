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
        self.assertEqual(to_yfinance_symbol("VGRO"), "VGRO.TO")
        self.assertEqual(to_yfinance_symbol("VFV:CDN"), "VFV.TO")
        self.assertEqual(to_yfinance_symbol("VGRO:CDN"), "VGRO.TO")
        self.assertEqual(to_yfinance_symbol("VGRO:CA"), "VGRO.TO")
        self.assertEqual(to_yfinance_symbol("VFV.CDN"), "VFV.TO")

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

    def test_safe_format_timestamp_various_types(self):
        from chart_view import _safe_format_timestamp
        from datetime import datetime, date

        # 1. datetime object
        dt = datetime(2026, 4, 11, 14, 30)
        self.assertEqual(_safe_format_timestamp(dt, "1D", False), "14:30")
        self.assertEqual(_safe_format_timestamp(dt, "6M", False), "Apr 11")
        self.assertEqual(_safe_format_timestamp(dt, "1Y", False), "Apr 2026")
        self.assertEqual(_safe_format_timestamp(dt, "1D", True), "11 Apr, 14:30:00")
        self.assertEqual(_safe_format_timestamp(dt, "6M", True), "11 Apr 2026")

        # 2. date object
        d = date(2026, 4, 11)
        self.assertEqual(_safe_format_timestamp(d, "6M", False), "Apr 11")
        self.assertEqual(_safe_format_timestamp(d, "1Y", False), "Apr 2026")

        # 3. String date "YYYY-MM-DD"
        s_date = "2026-04-11"
        self.assertEqual(_safe_format_timestamp(s_date, "6M", False), "Apr 11")
        self.assertEqual(_safe_format_timestamp(s_date, "1Y", False), "Apr 2026")
        self.assertEqual(_safe_format_timestamp(s_date, "6M", True), "11 Apr 2026")

        # 4. String time "HH:MM"
        s_time = "14:30"
        self.assertEqual(_safe_format_timestamp(s_time, "1D", False), "14:30")

        # 5. String ISO datetime
        s_iso = "2026-04-11T14:30:00Z"
        self.assertEqual(_safe_format_timestamp(s_iso, "1D", False), "14:30")
        self.assertEqual(_safe_format_timestamp(s_iso, "6M", False), "Apr 11")

        # 6. Fallback string
        s_custom = "CustomLabel"
        self.assertEqual(_safe_format_timestamp(s_custom, "1D", False), "CustomLabel")
        self.assertEqual(_safe_format_timestamp(None, "1D", False), "")

    def test_portfolio_history_returns_datetime_timestamps(self):
        from datetime import datetime
        fetcher = get_chart_fetcher()
        mock_dt1 = datetime(2026, 4, 10, 16, 0)
        mock_dt2 = datetime(2026, 4, 11, 16, 0)
        fetcher._set_cache("sym:VOO:6M", {
            "symbol": "VOO",
            "timeframe": "6M",
            "prices": [500.0, 510.0],
            "timestamps": [mock_dt1, mock_dt2],
            "prev_close": 495.0,
            "currency": "USD",
            "current_price": 510.0,
            "change": 15.0,
            "change_pct": 3.03,
        })
        holdings = [{"symbol": "VOO", "shares": 10.0, "currency": "USD", "current_price": 510.0}]
        res = fetcher.fetch_portfolio_history(holdings, "TestPort", "6M")
        self.assertIsNotNone(res)
        self.assertIn("timestamps", res)
        self.assertEqual(len(res["timestamps"]), 2)
        # Verify timestamps are datetime objects with strftime attribute
        for ts in res["timestamps"]:
            self.assertTrue(hasattr(ts, "strftime"))
            self.assertTrue(isinstance(ts, datetime))


if __name__ == "__main__":
    unittest.main()
