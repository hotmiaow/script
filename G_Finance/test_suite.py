"""
Automated Test Suite for Google Finance Portfolio & Calculator
Tests calculation engines, CSV persistence, Google Account Sync, and data fetching.
"""

import os
import unittest
from financial_calc import (
    calc_holding_summary,
    calc_dividend_projection,
    calc_drip_simulation,
    calc_stock_split,
    calc_selling_proceeds,
    calc_breakeven_sell_price,
    calc_target_profit_sell_price,
)
from csv_manager import (
    save_portfolio,
    load_portfolio,
    save_sales_history,
    load_sales_history,
    append_sale_record,
)
from google_finance_fetcher import GoogleFinanceFetcher
from google_account_sync import (
    GoogleAccountSync,
    load_sync_config,
    save_sync_config,
)


class TestFinancialCalculations(unittest.TestCase):
    def test_holding_summary(self):
        # 10 shares bought at $100, current price $150, div yield 2%
        res = calc_holding_summary(shares=10, buy_price=100, current_price=150, div_yield=2.0)
        self.assertEqual(res["cost_basis"], 1000.0)
        self.assertEqual(res["market_value"], 1500.0)
        self.assertEqual(res["unrealized_gain"], 500.0)
        self.assertEqual(res["unrealized_gain_pct"], 50.0)
        # Annual div per share = 150 * 0.02 = 3.0
        self.assertEqual(res["annual_dividend"], 30.0)
        self.assertEqual(res["quarterly_dividend"], 7.5)
        # Yield on cost = 3.0 / 100 = 3.0%
        self.assertEqual(res["yield_on_cost"], 3.0)

    def test_dividend_projection(self):
        res = calc_dividend_projection(shares=100, current_price=50, div_yield=4.0, buy_price=40)
        self.assertEqual(res["annual_div_per_share"], 2.0)
        self.assertEqual(res["annual_total"], 200.0)
        self.assertEqual(res["quarterly_total"], 50.0)
        self.assertAlmostEqual(res["monthly_total"], 16.67, places=1)
        self.assertEqual(res["yield_on_cost"], 5.0)  # 2.0 / 40 = 5%

    def test_drip_simulation(self):
        history = calc_drip_simulation(
            initial_shares=100,
            initial_price=50,
            div_yield_pct=4.0,
            div_growth_pct=5.0,
            price_growth_pct=5.0,
            years=5,
        )
        self.assertEqual(len(history), 5)
        self.assertGreater(history[0]["shares"], 100)
        self.assertGreater(history[4]["shares"], history[0]["shares"])
        self.assertGreater(history[4]["portfolio_value"], 5000)

    def test_stock_split(self):
        split = calc_stock_split(shares=100, buy_price=200, ratio_from=1, ratio_to=4)
        self.assertEqual(split["new_shares"], 400.0)
        self.assertEqual(split["new_buy_price"], 50.0)
        self.assertEqual(split["original_basis"], split["new_basis"])

        rev_split = calc_stock_split(shares=500, buy_price=2, ratio_from=5, ratio_to=1)
        self.assertEqual(rev_split["new_shares"], 100.0)
        self.assertEqual(rev_split["new_buy_price"], 10.0)
        self.assertEqual(rev_split["original_basis"], rev_split["new_basis"])

    def test_selling_proceeds(self):
        res = calc_selling_proceeds(
            shares_to_sell=50,
            buy_price=100,
            sell_price=150,
            commission_flat=10,
            commission_pct=0.1,
            tax_rate_pct=20,
        )
        self.assertEqual(res["gross_proceeds"], 7500.0)
        self.assertEqual(res["cost_basis"], 5000.0)
        self.assertEqual(res["commission_fee"], 17.50)
        self.assertEqual(res["gross_gain"], 2482.50)
        self.assertEqual(res["estimated_tax"], 496.50)
        self.assertEqual(res["net_proceeds"], 6986.0)
        self.assertEqual(res["net_profit"], 1986.0)
        self.assertAlmostEqual(res["net_roi_pct"], 39.72, places=1)

    def test_breakeven_sell_price(self):
        be = calc_breakeven_sell_price(shares=100, buy_price=50, commission_flat=10)
        self.assertEqual(be, 50.10)

    def test_target_profit_sell_price(self):
        tp = calc_target_profit_sell_price(shares=100, buy_price=50, target_profit_dollars=1000)
        self.assertEqual(tp["target_sell_price"], 60.0)


class TestCSVManager(unittest.TestCase):
    def setUp(self):
        self.test_port_csv = "test_portfolio.csv"
        self.test_sales_csv = "test_sales.csv"

    def tearDown(self):
        if os.path.exists(self.test_port_csv):
            os.remove(self.test_port_csv)
        if os.path.exists(self.test_sales_csv):
            os.remove(self.test_sales_csv)

    def test_portfolio_roundtrip(self):
        holdings = [
            {
                "symbol": "AAPL",
                "name": "Apple Inc",
                "shares": 25.0,
                "buy_price": 150.0,
                "current_price": 220.0,
                "cost_basis": 3750.0,
                "market_value": 5500.0,
                "unrealized_gain": 1750.0,
                "unrealized_gain_pct": 46.67,
                "dividend_yield": 0.5,
                "annual_div_per_share": 1.10,
                "annual_dividend": 27.50,
                "currency": "USD",
                "last_updated": "2026-09-15 12:00:00",
            }
        ]
        self.assertTrue(save_portfolio(holdings, self.test_port_csv))
        loaded = load_portfolio(self.test_port_csv)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["symbol"], "AAPL")
        self.assertEqual(loaded[0]["shares"], 25.0)
        self.assertEqual(loaded[0]["buy_price"], 150.0)
        self.assertEqual(loaded[0]["current_price"], 220.0)

    def test_sales_history_roundtrip(self):
        sale = {
            "symbol": "MSFT",
            "shares_to_sell": 10.0,
            "buy_price": 300.0,
            "sell_price": 420.0,
            "gross_proceeds": 4200.0,
            "cost_basis": 3000.0,
            "commission_fee": 5.0,
            "gross_gain": 1195.0,
            "tax_rate_pct": 15.0,
            "estimated_tax": 179.25,
            "net_proceeds": 4015.75,
            "net_profit": 1015.75,
            "net_roi_pct": 33.86,
        }
        self.assertTrue(append_sale_record(sale, self.test_sales_csv))
        loaded = load_sales_history(self.test_sales_csv)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["symbol"], "MSFT")
        self.assertEqual(loaded[0]["net_profit"], 1015.75)


class TestGoogleAccountSync(unittest.TestCase):
    def setUp(self):
        self.test_gf_csv = "test_gf_export.csv"

    def tearDown(self):
        if os.path.exists(self.test_gf_csv):
            os.remove(self.test_gf_csv)

    def test_parse_and_export_google_finance_csv(self):
        # Sample holdings to export in Google Finance format
        holdings = [
            {"symbol": "GOOGL", "name": "Alphabet Inc", "shares": 15.0, "buy_price": 180.50, "currency": "USD"},
            {"symbol": "AMZN", "name": "Amazon.com Inc", "shares": 25.0, "buy_price": 195.00, "currency": "USD"},
        ]
        sync = GoogleAccountSync()
        self.assertTrue(sync.export_to_google_finance_csv(self.test_gf_csv, holdings))

        parsed = sync.parse_google_finance_csv(self.test_gf_csv)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["symbol"], "GOOGL")
        self.assertEqual(parsed[0]["shares"], 15.0)
        self.assertEqual(parsed[0]["buy_price"], 180.50)
        self.assertEqual(parsed[1]["symbol"], "AMZN")
        self.assertEqual(parsed[1]["shares"], 25.0)

    def test_sync_config(self):
        cfg = {"cookie": "test_cookie_123", "portfolio_url": "https://www.google.com/finance/portfolio/watchlist", "last_sync": "now"}
        self.assertTrue(save_sync_config(cfg))
        loaded = load_sync_config()
        self.assertEqual(loaded.get("cookie"), "test_cookie_123")


from currency_converter import CurrencyConverter
from csv_manager import get_portfolio_names, rename_portfolio, delete_portfolio


class TestCurrencyConverter(unittest.TestCase):
    def setUp(self):
        self.conv = CurrencyConverter()

    def test_conversions(self):
        # Default USD to USD is 1:1
        self.assertEqual(self.conv.convert(100.0, "USD", "USD"), 100.0)
        # USD to CAD with positive rate
        cad = self.conv.convert(100.0, "USD", "CAD")
        self.assertGreater(cad, 100.0)
        # USD to HKD with positive rate
        hkd = self.conv.convert(100.0, "USD", "HKD")
        self.assertGreater(hkd, 700.0)
        # Round trip
        usd_back = self.conv.convert(cad, "CAD", "USD")
        self.assertAlmostEqual(usd_back, 100.0, places=2)

    def test_formatting(self):
        self.assertEqual(self.conv.format_money(1234.5, "USD"), "$1,234.50")
        self.assertEqual(self.conv.format_money(1234.5, "CAD"), "C$1,234.50")
        self.assertEqual(self.conv.format_money(1234.5, "HKD"), "HK$1,234.50")

    def test_summary_string(self):
        summary = self.conv.get_rates_summary("USD")
        self.assertIn("CAD", summary)
        self.assertIn("HKD", summary)


class TestMultiPortfolio(unittest.TestCase):
    def setUp(self):
        self.test_csv = "test_multi_port.csv"

    def tearDown(self):
        if os.path.exists(self.test_csv):
            os.remove(self.test_csv)

    def test_multi_portfolio_lifecycle(self):
        holdings = [
            {"portfolio": "USD HSBC", "symbol": "AAPL", "shares": 10.0, "buy_price": 150.0, "current_price": 200.0, "currency": "USD"},
            {"portfolio": "USD HSBC", "symbol": "GOOGL", "shares": 5.0, "buy_price": 100.0, "current_price": 180.0, "currency": "USD"},
            {"portfolio": "CAD TSFA", "symbol": "SHOP", "shares": 20.0, "buy_price": 80.0, "current_price": 100.0, "currency": "CAD"},
        ]
        self.assertTrue(save_portfolio(holdings, self.test_csv))

        # Check get_portfolio_names
        names = get_portfolio_names(self.test_csv)
        self.assertIn("USD HSBC", names)
        self.assertIn("CAD TSFA", names)
        self.assertEqual(len(names), 2)

        # Check filtering by portfolio
        cad_holdings = load_portfolio(self.test_csv, portfolio_name="CAD TSFA")
        self.assertEqual(len(cad_holdings), 1)
        self.assertEqual(cad_holdings[0]["symbol"], "SHOP")
        self.assertEqual(cad_holdings[0]["currency"], "CAD")

        usd_holdings = load_portfolio(self.test_csv, portfolio_name="USD HSBC")
        self.assertEqual(len(usd_holdings), 2)

        # Rename portfolio
        self.assertTrue(rename_portfolio("CAD TSFA", "CAD RRSP", self.test_csv))
        renamed_names = get_portfolio_names(self.test_csv)
        self.assertIn("CAD RRSP", renamed_names)
        self.assertNotIn("CAD TSFA", renamed_names)

        # Delete portfolio
        self.assertTrue(delete_portfolio("CAD RRSP", self.test_csv))
        final_names = get_portfolio_names(self.test_csv)
        self.assertEqual(final_names, ["USD HSBC"])
        all_left = load_portfolio(self.test_csv)
        self.assertEqual(len(all_left), 2)


if __name__ == "__main__":
    unittest.main()
