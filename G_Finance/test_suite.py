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
    calc_holding_earned_already,
    calc_future_dividend_milestones,
    calc_split_future_projections,
    parse_date_to_days_held,
)
from csv_manager import (
    save_portfolio,
    load_portfolio,
    save_sales_history,
    load_sales_history,
    append_sale_record,
    save_transactions,
    load_transactions,
    append_transaction,
    TRANSACTION_HISTORY_CSV,
    rotate_file_backups,
    get_backup_files,
    restore_backup,
    parse_day_change_string,
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

    def test_day_change_persistence_and_parsing(self):
        # 1. Test parsing of various string formats
        # Positive change
        d_val, d_pct = parse_day_change_string("+1.85 (+1.70%)")
        self.assertEqual(d_val, 1.85)
        self.assertEqual(d_pct, 1.70)

        # Negative change with standard ASCII minus
        d_val, d_pct = parse_day_change_string("-0.26 (-1.45%)")
        self.assertEqual(d_val, -0.26)
        self.assertEqual(d_pct, -1.45)

        # Negative change with Google Finance Unicode minus (\u2212)
        d_val, d_pct = parse_day_change_string("−0.26 (−1.45%)")
        self.assertEqual(d_val, -0.26)
        self.assertEqual(d_pct, -1.45)

        # Cross calculation from dollar change only
        d_val, d_pct = parse_day_change_string("+10.00", current_price=110.0)
        self.assertEqual(d_val, 10.00)
        self.assertEqual(d_pct, 10.00)  # 10 / (110 - 10) * 100 = 10.0%

        # Empty / dash format
        self.assertEqual(parse_day_change_string("-"), (None, None))
        self.assertEqual(parse_day_change_string(""), (None, None))

        # 2. Test roundtrip persistence in portfolio CSV
        holdings = [
            {
                "symbol": "GOOGL",
                "name": "Alphabet Inc",
                "shares": 10.0,
                "buy_price": 100.0,
                "current_price": 150.0,
                "change": -2.50,
                "change_percent": -1.64,
                "currency": "USD",
            },
            {
                "symbol": "NVDA",
                "name": "NVIDIA Corp",
                "shares": 5.0,
                "buy_price": 100.0,
                "current_price": 120.0,
                "change": 3.75,
                "change_percent": 3.23,
                "currency": "USD",
            },
        ]
        self.assertTrue(save_portfolio(holdings, self.test_port_csv))
        loaded = load_portfolio(self.test_port_csv)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["symbol"], "GOOGL")
        self.assertEqual(loaded[0]["change"], -2.50)
        self.assertEqual(loaded[0]["change_percent"], -1.64)
        self.assertEqual(loaded[1]["symbol"], "NVDA")
        self.assertEqual(loaded[1]["change"], 3.75)
        self.assertEqual(loaded[1]["change_percent"], 3.23)

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


from financial_calc import calc_portfolio_metrics
from report_generator import generate_html_report
from chart_canvas import draw_donut_chart, draw_drip_growth_chart


class TestPortfolioMetrics(unittest.TestCase):
    def test_metrics_calculation(self):
        holdings = [
            {
                "symbol": "AAPL",
                "name": "Apple Inc",
                "shares": 10.0,
                "buy_price": 150.0,
                "current_price": 200.0,
                "currency": "USD",
                "annual_dividend": 25.0,
                "change": 2.50,
                "unrealized_gain_pct": 33.33,
            },
            {
                "symbol": "600519",
                "name": "Kweichow Moutai",
                "shares": 100.0,
                "buy_price": 1600.0,
                "current_price": 1800.0,
                "currency": "CNY",
                "annual_dividend": 3000.0,
                "change": 15.0,
                "unrealized_gain_pct": 12.50,
            },
        ]
        # 1 CNY = 0.14 USD
        fx_rates = {"CNY": 0.14}
        metrics = calc_portfolio_metrics(holdings, base_currency="USD", fx_rates=fx_rates)

        self.assertEqual(metrics["base_currency"], "USD")
        # AAPL val = 10 * 200 = 2000 USD
        # Moutai val = 100 * 1800 * 0.14 = 25200 USD
        # Total val = 27200 USD
        self.assertEqual(metrics["total_value"], 27200.0)
        # Cost: AAPL 1500 + Moutai 160000 * 0.14 = 22400 -> 23900 USD
        self.assertEqual(metrics["total_cost"], 23900.0)
        self.assertAlmostEqual(metrics["total_gain"], 3300.0, places=1)
        self.assertGreater(metrics["top_concentration_pct"], 90.0)
        self.assertEqual(metrics["best_performer"]["symbol"], "AAPL")
        self.assertEqual(metrics["worst_performer"]["symbol"], "600519")

    def test_combined_duplicate_holdings_in_analytics(self):
        # Multiple holdings of VOO across different accounts/portfolios
        holdings = [
            {
                "symbol": "VOO",
                "name": "Vanguard S&P 500 ETF",
                "shares": 50.0,
                "buy_price": 400.0,
                "current_price": 500.0,
                "currency": "USD",
                "annual_dividend": 200.0,
                "change": 5.0,
                "portfolio": "USD HSBC",
            },
            {
                "symbol": "VOO",
                "name": "Vanguard S&P 500 ETF",
                "shares": 30.0,
                "buy_price": 420.0,
                "current_price": 500.0,
                "currency": "USD",
                "annual_dividend": 120.0,
                "change": 5.0,
                "portfolio": "CAD RRSP",
            },
            {
                "symbol": "VOO",
                "name": "Vanguard S&P 500 ETF",
                "shares": 20.0,
                "buy_price": 450.0,
                "current_price": 500.0,
                "currency": "USD",
                "annual_dividend": 80.0,
                "change": 5.0,
                "portfolio": "USD TSFA",
            },
            {
                "symbol": "AAPL",
                "name": "Apple Inc",
                "shares": 10.0,
                "buy_price": 150.0,
                "current_price": 200.0,
                "currency": "USD",
                "annual_dividend": 25.0,
                "change": 2.0,
                "portfolio": "USD HSBC",
            },
        ]
        metrics = calc_portfolio_metrics(holdings, base_currency="USD")
        allocs = metrics["allocations"]

        # 4 total holdings, but only 2 unique tickers: VOO and AAPL
        self.assertEqual(len(allocs), 2)

        voo = next(a for a in allocs if a["symbol"] == "VOO")
        # Total shares = 50 + 30 + 20 = 100
        self.assertEqual(voo["shares"], 100.0)
        # Total market value = 100 * 500 = 50,000 USD
        self.assertEqual(voo["value_base"], 50000.0)
        # Total cost basis = 50*400 (20k) + 30*420 (12.6k) + 20*450 (9k) = 41,600 USD
        self.assertEqual(voo["cost_basis"], 41600.0)
        # Total portfolio value = 50,000 (VOO) + 2,000 (AAPL) = 52,000 USD
        self.assertEqual(metrics["total_value"], 52000.0)
        # VOO weight = 50,000 / 52,000 * 100 = 96.15%
        self.assertAlmostEqual(voo["weight_pct"], 96.15, places=1)
        self.assertEqual(metrics["top_concentration_pct"], voo["weight_pct"])
        self.assertEqual(metrics["best_performer"]["symbol"], "AAPL")  # 33.33% vs 20.19%



class TestReportGenerator(unittest.TestCase):
    def setUp(self):
        self.report_file = "test_exec_report.html"

    def tearDown(self):
        if os.path.exists(self.report_file):
            os.remove(self.report_file)

    def test_html_report_generation(self):
        holdings = [
            {
                "symbol": "MSFT",
                "name": "Microsoft Corporation",
                "shares": 15.0,
                "buy_price": 350.0,
                "current_price": 420.0,
                "market_value": 6300.0,
                "cost_basis": 5250.0,
                "unrealized_gain": 1050.0,
                "unrealized_gain_pct": 20.0,
                "change": 3.20,
                "change_percent": 0.77,
                "dividend_yield": 0.8,
                "annual_dividend": 45.0,
                "currency": "USD",
                "portfolio": "USD HSBC",
            }
        ]
        metrics = calc_portfolio_metrics(holdings, base_currency="USD")
        ok = generate_html_report(
            holdings=holdings,
            portfolio_metrics=metrics,
            sales_history=[],
            filepath=self.report_file,
        )
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(self.report_file))

        with open(self.report_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Microsoft Corporation", content)
        self.assertIn("MSFT", content)
        self.assertIn("Google Finance Portfolio Executive Report", content)
        self.assertIn("$6,300.00", content)


class TestChartViewScopeDeduplication(unittest.TestCase):
    def test_scope_deduplication(self):
        # Simulate holdings with duplicate symbols across multiple portfolios
        holdings = [
            {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "portfolio": "USD HSBC"},
            {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "portfolio": "CAD RRSP"},
            {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "portfolio": "USD RRSP"},
            {"symbol": "VFV:TSE", "name": "Vanguard S&P 500 Index ETF", "portfolio": "CAD RRSP"},
            {"symbol": "VFV:TSE", "name": "Vanguard S&P 500 Index ETF", "portfolio": "USD TSFA"},
            {"symbol": "NOK", "name": "Nokia Oyj", "portfolio": "USD HSBC"},
        ]
        port_name = "All Portfolios (Consolidated)"
        values = [f"📁 Portfolio: {port_name}"]
        seen_syms = set()
        for h in holdings:
            sym = str(h.get("symbol", "")).strip()
            if not sym:
                continue
            sym_key = sym.upper()
            if sym_key in seen_syms:
                continue
            seen_syms.add(sym_key)
            name = h.get("name", "")
            display = f"{sym} - {name}" if name else sym
            values.append(display)

        # Ensure VOO appears exactly once
        voo_entries = [v for v in values if v.startswith("VOO")]
        self.assertEqual(len(voo_entries), 1)
        self.assertEqual(voo_entries[0], "VOO - Vanguard S&P 500 ETF")

        # Ensure VFV:TSE appears exactly once
        vfv_entries = [v for v in values if v.startswith("VFV:TSE")]
        self.assertEqual(len(vfv_entries), 1)
        self.assertEqual(vfv_entries[0], "VFV:TSE - Vanguard S&P 500 Index ETF")

        # Ensure total unique options is 1 (portfolio) + 3 (unique symbols)
        self.assertEqual(len(values), 4)

    def test_holding_selection_symbol_lookup(self):
        # Tests resolving symbol with or without alert indicators
        test_rows = [
            (["USD HSBC", "NOK", "Nokia Oyj"], "NOK"),
            (["USD HSBC", "🎯 NOK", "Nokia Oyj"], "NOK"),
            (["USD HSBC", "⚠️ TSLA", "Tesla Inc"], "TSLA"),
            (["NOK"], "NOK"),
        ]
        for row_vals, expected in test_rows:
            raw_sym = ""
            if len(row_vals) > 1:
                raw_sym = str(row_vals[1]).replace("🎯 ", "").replace("⚠️ ", "").strip().upper()
            elif len(row_vals) == 1:
                raw_sym = str(row_vals[0]).strip().upper()
            self.assertEqual(raw_sym, expected)


class TestTransactionHistory(unittest.TestCase):
    def setUp(self):
        self.test_tx_file = "test_tx_history_suite.csv"
        if os.path.exists(self.test_tx_file):
            os.remove(self.test_tx_file)

    def tearDown(self):
        if os.path.exists(self.test_tx_file):
            os.remove(self.test_tx_file)

    def test_transactions_roundtrip_and_filtering(self):
        tx_buy = {
            "type": "BUY",
            "portfolio": "USD HSBC",
            "symbol": "VOO",
            "shares": 10.0,
            "price": 500.0,
            "total_amount": 5000.0,
            "currency": "USD",
            "notes": "Initial purchase",
        }
        tx_sell = {
            "type": "SELL",
            "portfolio": "USD HSBC",
            "symbol": "VOO",
            "shares": 5.0,
            "price": 550.0,
            "total_amount": 2750.0,
            "cost_basis": 2500.0,
            "commission_fee": 10.0,
            "estimated_tax": 30.0,
            "net_amount": 2710.0,
            "net_profit": 210.0,
            "net_roi_pct": 8.4,
            "currency": "USD",
            "notes": "Partial profit taking",
        }
        tx_cad_buy = {
            "type": "BUY",
            "portfolio": "CAD RRSP",
            "symbol": "VFV:TSE",
            "shares": 25.0,
            "price": 120.0,
            "total_amount": 3000.0,
            "currency": "CAD",
            "notes": "RRSP contribution",
        }

        # Save all 3 transactions
        save_transactions([tx_buy, tx_sell, tx_cad_buy], self.test_tx_file)

        # 1. Load All
        all_tx = load_transactions(self.test_tx_file, portfolio_name=None, tx_type=None)
        self.assertEqual(len(all_tx), 3)

        # 2. Filter by Type: BUY
        buys = load_transactions(self.test_tx_file, portfolio_name=None, tx_type="BUY")
        self.assertEqual(len(buys), 2)
        self.assertTrue(all(b["type"] == "BUY" for b in buys))

        # 3. Filter by Type: SELL
        sells = load_transactions(self.test_tx_file, portfolio_name=None, tx_type="SELL")
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0]["type"], "SELL")
        self.assertEqual(sells[0]["symbol"], "VOO")
        self.assertEqual(sells[0]["net_profit"], 210.0)

        # 4. Filter by Portfolio: "CAD RRSP"
        cad_tx = load_transactions(self.test_tx_file, portfolio_name="CAD RRSP", tx_type=None)
        self.assertEqual(len(cad_tx), 1)
        self.assertEqual(cad_tx[0]["symbol"], "VFV:TSE")

        # 5. Dual Filter: Portfolio "USD HSBC" + Type "BUY"
        hsbc_buys = load_transactions(self.test_tx_file, portfolio_name="USD HSBC", tx_type="BUY")
        self.assertEqual(len(hsbc_buys), 1)
        self.assertEqual(hsbc_buys[0]["symbol"], "VOO")

        # 6. Append new transaction
        new_buy = {
            "type": "BUY",
            "portfolio": "USD TSFA",
            "symbol": "AAPL",
            "shares": 15.0,
            "price": 220.0,
            "total_amount": 3300.0,
            "currency": "USD",
        }
        self.assertTrue(append_transaction(new_buy, self.test_tx_file))
        updated_all = load_transactions(self.test_tx_file, portfolio_name=None, tx_type=None)
        self.assertEqual(len(updated_all), 4)
        self.assertEqual(updated_all[0]["symbol"], "AAPL")


class TestCsvBackupRotation(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_backup_sandbox")
        os.makedirs(self.test_dir, exist_ok=True)
        self.test_port_csv = os.path.join(self.test_dir, "test_portfolio.csv")
        self.test_tx_csv = os.path.join(self.test_dir, "test_transactions.csv")
        self.backup_dir = os.path.join(self.test_dir, "backups")

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_portfolio_5_backup_rotation(self):
        # 1. Save initial version (Save 1) -> No backups yet
        save_portfolio([{"symbol": "V1", "shares": 1.0, "buy_price": 10.0}], self.test_port_csv)
        self.assertTrue(os.path.exists(self.test_port_csv))
        backups = get_backup_files(self.test_port_csv, backup_dir=self.backup_dir)
        self.assertEqual(len(backups), 0)

        # 2. Save V2 -> 1 backup created (contains V1)
        save_portfolio([{"symbol": "V2", "shares": 2.0, "buy_price": 20.0}], self.test_port_csv)
        backups = get_backup_files(self.test_port_csv, backup_dir=self.backup_dir)
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0]["index"], 1)
        b1_holdings = load_portfolio(backups[0]["path"], portfolio_name=None)
        self.assertEqual(b1_holdings[0]["symbol"], "V1")

        # 3. Save V3, V4, V5, V6 -> exactly 5 backups should exist
        for i in range(3, 7):
            save_portfolio([{"symbol": f"V{i}", "shares": float(i), "buy_price": 10.0 * i}], self.test_port_csv)

        backups = get_backup_files(self.test_port_csv, backup_dir=self.backup_dir)
        self.assertEqual(len(backups), 5)
        # Check slot indices 1..5 exist
        indices = [b["index"] for b in backups]
        self.assertEqual(indices, [1, 2, 3, 4, 5])
        # Slot 1 is newest (V5), Slot 5 is oldest (V1)
        self.assertEqual(load_portfolio(backups[0]["path"])[0]["symbol"], "V5")
        self.assertEqual(load_portfolio(backups[4]["path"])[0]["symbol"], "V1")

        # 4. Save V7 -> still capped at 5 backups; V1 purged, slot 5 is V2, slot 1 is V6
        save_portfolio([{"symbol": "V7", "shares": 7.0, "buy_price": 70.0}], self.test_port_csv)
        backups = get_backup_files(self.test_port_csv, backup_dir=self.backup_dir)
        self.assertEqual(len(backups), 5)
        self.assertEqual(load_portfolio(backups[0]["path"])[0]["symbol"], "V6")
        self.assertEqual(load_portfolio(backups[4]["path"])[0]["symbol"], "V2")

        # 5. Restore from backup slot 3 (which is V4)
        ok = restore_backup(self.test_port_csv, backup_index=3, backup_dir=self.backup_dir)
        self.assertTrue(ok)
        restored = load_portfolio(self.test_port_csv)
        self.assertEqual(restored[0]["symbol"], "V4")

        # Verify safety backup retained the prior state (V7) in slot 1
        backups_after = get_backup_files(self.test_port_csv, backup_dir=self.backup_dir)
        self.assertEqual(load_portfolio(backups_after[0]["path"])[0]["symbol"], "V7")

    def test_transaction_history_rotation(self):
        # Save transactions 3 times
        for i in range(1, 4):
            tx = {
                "type": "BUY",
                "portfolio": "USD HSBC",
                "symbol": f"TX{i}",
                "shares": 10.0,
                "price": 100.0,
                "total_amount": 1000.0,
            }
            save_transactions([tx], self.test_tx_csv)

        backups = get_backup_files(self.test_tx_csv, backup_dir=self.backup_dir)
        # Save 1: 0 backups; Save 2: 1 backup (TX1); Save 3: 2 backups (.1 has TX2, .2 has TX1)
        self.assertEqual(len(backups), 2)
        tx_b1 = load_transactions(backups[0]["path"])
        self.assertEqual(tx_b1[0]["symbol"], "TX2")
        tx_b2 = load_transactions(backups[1]["path"])
        self.assertEqual(tx_b2[0]["symbol"], "TX1")


class TestI18nSupport(unittest.TestCase):
    """Unit tests for multi-language (i18n) support across en, zh_TW, and zh_CN."""

    def setUp(self):
        from i18n import get_current_language
        self.orig_lang = get_current_language()

    def tearDown(self):
        from i18n import set_language
        set_language(self.orig_lang)

    def test_key_parity_across_languages(self):
        from i18n import TRANSLATIONS
        en_keys = set(TRANSLATIONS["en"].keys())
        tw_keys = set(TRANSLATIONS["zh_TW"].keys())
        cn_keys = set(TRANSLATIONS["zh_CN"].keys())

        missing_in_tw = en_keys - tw_keys
        missing_in_cn = en_keys - cn_keys

        self.assertEqual(missing_in_tw, set(), f"zh_TW missing keys: {missing_in_tw}")
        self.assertEqual(missing_in_cn, set(), f"zh_CN missing keys: {missing_in_cn}")
        self.assertGreater(len(en_keys), 100, "Should have rich dictionary coverage")

    def test_translation_retrieval_and_switching(self):
        from i18n import t, set_language, get_current_language

        set_language("en")
        self.assertEqual(get_current_language(), "en")
        self.assertEqual(t("app_title"), "Google Finance Portfolio Tracker & Calculator")
        self.assertEqual(t("btn_add_stock"), "➕ Add Stock")

        set_language("zh_TW")
        self.assertEqual(get_current_language(), "zh_TW")
        self.assertEqual(t("app_title"), "Google 財經投資組合追蹤與計算器")
        self.assertEqual(t("btn_add_stock"), "➕ 新增股票")

        set_language("zh_CN")
        self.assertEqual(get_current_language(), "zh_CN")
        self.assertEqual(t("app_title"), "Google 财经投资组合跟踪与计算器")
        self.assertEqual(t("btn_add_stock"), "➕ 添加股票")

    def test_string_interpolation(self):
        from i18n import t, set_language

        set_language("en")
        self.assertEqual(t("showing_holdings", shown=3, total=10), "Showing 3 of 10 holdings")
        self.assertEqual(t("confirm_delete_holding", sym="MSFT"), "Are you sure you want to remove MSFT from your portfolio?")

        set_language("zh_TW")
        self.assertEqual(t("showing_holdings", shown=3, total=10), "顯示 3 / 10 隻持倉股票")
        self.assertEqual(t("confirm_delete_holding", sym="MSFT"), "確定要從投資組合中移除 MSFT 嗎？")

        set_language("zh_CN")
        self.assertEqual(t("showing_holdings", shown=3, total=10), "显示 3 / 10 只持仓股票")
        self.assertEqual(t("confirm_delete_holding", sym="MSFT"), "确定要从投资组合中移除 MSFT 吗？")

    def test_fallback_behavior(self):
        from i18n import t, set_language

        set_language("zh_TW")
        # Nonexistent key returns the key itself
        self.assertEqual(t("non_existent_key_xyz"), "non_existent_key_xyz")

    def test_available_languages_list(self):
        from i18n import get_available_languages
        langs = get_available_languages()
        codes = [c for c, _ in langs]
        self.assertIn("en", codes)
        self.assertIn("zh_TW", codes)
        self.assertIn("zh_CN", codes)

    def test_settings_persistence(self):
        import json
        from i18n import set_language, SETTINGS_FILE, load_settings

        set_language("zh_TW")
        settings = load_settings()
        self.assertEqual(settings.get("language"), "zh_TW")

        set_language("en")
        settings = load_settings()
        self.assertEqual(settings.get("language"), "en")


class TestHoldingPastAndFutureCalculations(unittest.TestCase):
    def test_parse_date_to_days_held(self):
        from datetime import date, timedelta
        today = date.today()
        d_100_ago = (today - timedelta(days=100)).strftime("%Y-%m-%d")
        days, years = parse_date_to_days_held(d_100_ago)
        self.assertEqual(days, 100)
        self.assertAlmostEqual(years, 100 / 365.25, places=3)

        # Colloquial format
        d_may = "7 May 2024"
        days_may, _ = parse_date_to_days_held(d_may)
        self.assertGreater(days_may, 0)

        # None / invalid fallback to 365 days / 1 yr
        d_fallback, y_fallback = parse_date_to_days_held(None)
        self.assertEqual(d_fallback, 365)
        self.assertEqual(y_fallback, 1.0)

        d_invalid, y_invalid = parse_date_to_days_held("invalid-date")
        self.assertEqual(d_invalid, 365)
        self.assertEqual(y_invalid, 1.0)

    def test_calc_holding_earned_already(self):
        # 50 shares bought at $100, current price $150, held for 1 year, $2.00 annual div
        from datetime import date, timedelta
        d_1yr = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")
        res = calc_holding_earned_already(
            shares=50,
            buy_price=100.0,
            current_price=150.0,
            purchase_date_str=d_1yr,
            annual_div_per_share=2.0,
        )
        self.assertEqual(res["cost_basis"], 5000.0)
        self.assertEqual(res["market_value"], 7500.0)
        self.assertEqual(res["capital_gain"], 2500.0)
        self.assertEqual(res["capital_gain_pct"], 50.0)
        # Past dividends = 50 * 2.0 * (365/365.25) ~= 100.0
        self.assertAlmostEqual(res["past_dividends"], 100.0, delta=1.0)
        # Total earned already = 2500 + past_dividends ~= 2600.0
        self.assertAlmostEqual(res["total_earned_already"], 2600.0, delta=1.0)
        self.assertAlmostEqual(res["total_roi_pct"], 52.0, delta=0.5)
        self.assertGreater(res["cagr_pct"], 45.0)

    def test_calc_future_dividend_milestones(self):
        # 100 shares @ $50, bought at $40, 4% yield, 5% div growth, 6% price growth
        res = calc_future_dividend_milestones(
            shares=100,
            current_price=50.0,
            buy_price=40.0,
            div_yield_pct=4.0,
            annual_div_per_share=2.0,
            div_growth_pct=5.0,
            price_growth_pct=6.0,
            monthly_contribution=0.0,
            horizons=[1, 3, 5, 10],
        )
        self.assertEqual(res["initial_cost_basis"], 4000.0)
        self.assertEqual(res["initial_market_value"], 5000.0)
        milestones = res["milestones"]
        self.assertIn(1, milestones)
        self.assertIn(3, milestones)
        self.assertIn(5, milestones)
        self.assertIn(10, milestones)

        # Portfolio value grows with compounding DRIP
        self.assertGreater(milestones[1]["portfolio_value"], 5000.0)
        self.assertGreater(milestones[3]["portfolio_value"], milestones[1]["portfolio_value"])
        self.assertGreater(milestones[5]["portfolio_value"], milestones[3]["portfolio_value"])
        self.assertGreater(milestones[10]["portfolio_value"], milestones[5]["portfolio_value"])

        # Total profit from start and new profit from today
        self.assertGreater(milestones[5]["new_profit_from_today"], 0.0)
        self.assertGreater(milestones[5]["total_profit_from_start"], milestones[5]["new_profit_from_today"])
        self.assertGreater(milestones[5]["cumulative_dividends"], 0.0)

    def test_calc_split_future_projections(self):
        # 100 shares bought at $80, current price $120, 2:1 split
        res = calc_split_future_projections(
            shares=100,
            buy_price=80.0,
            current_price=120.0,
            ratio_from=1.0,
            ratio_to=2.0,
            target_price=80.0,
        )
        # Earned already
        self.assertEqual(res["cost_basis"], 8000.0)
        self.assertEqual(res["market_value"], 12000.0)
        self.assertEqual(res["earned_already"], 4000.0)
        self.assertEqual(res["earned_already_pct"], 50.0)

        # Post-split adjustments
        self.assertEqual(res["multiplier"], 2.0)
        self.assertEqual(res["new_shares"], 200.0)
        self.assertEqual(res["new_buy_price"], 40.0)
        self.assertEqual(res["new_current_price"], 60.0)
        self.assertEqual(res["new_cost_basis"], 8000.0)
        self.assertEqual(res["new_market_value"], 12000.0)

        # Scenarios
        scenarios = res["scenarios"]
        self.assertEqual(len(scenarios), 4)  # +10%, +25%, +50%, +100%
        self.assertEqual(scenarios[0]["growth_pct"], 10.0)
        self.assertEqual(scenarios[0]["future_price"], 66.0)
        self.assertEqual(scenarios[0]["future_value"], 13200.0)
        self.assertEqual(scenarios[0]["new_profit_from_today"], 1200.0)
        self.assertEqual(scenarios[0]["total_profit_from_start"], 5200.0)

        # Pre-split recovery (reaching $120 again)
        recov = res["pre_split_recovery"]
        self.assertEqual(recov["target_price"], 120.0)
        self.assertEqual(recov["future_value"], 24000.0)
        self.assertEqual(recov["total_profit_from_start"], 16000.0)
        self.assertEqual(recov["new_profit_from_today"], 12000.0)

        # Custom target price ($80)
        custom = res["custom_target"]
        self.assertIsNotNone(custom)
        self.assertEqual(custom["target_price"], 80.0)
        self.assertEqual(custom["future_value"], 16000.0)
        self.assertEqual(custom["total_profit_from_start"], 8000.0)
        self.assertEqual(custom["new_profit_from_today"], 4000.0)


if __name__ == "__main__":
    unittest.main()


