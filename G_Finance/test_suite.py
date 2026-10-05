"""
Automated Test Suite for Google Finance Portfolio & Calculator
Tests calculation engines, CSV persistence, Google Account Sync, and data fetching.
"""

import os
import unittest
import tempfile
from datetime import date, timedelta
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
    parse_tx_date,
    calc_period_earnings,
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
    update_transaction,
    delete_transaction,
    TRANSACTION_HISTORY_CSV,
    rotate_file_backups,
    get_backup_files,
    restore_backup,
    parse_day_change_string,
)
from report_generator import generate_period_earnings_report_html
from fee_manager import (
    BROKER_PRESETS,
    load_all_portfolio_fees,
    save_all_portfolio_fees,
    get_portfolio_fee_config,
    save_portfolio_fee_config,
    delete_portfolio_fee_config,
    rename_portfolio_fee_config,
    calc_estimated_commission,
    log_storage_fee_transaction,
    PORTFOLIO_FEES_FILE,
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
        self.assertTrue(any(t in content for t in ["Google Finance Portfolio Executive Report", "Google 財經投資組合高階執行報告", "Google 财经投资组合高阶执行报告"]))
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
        from i18n import set_language, SETTINGS_FILE, load_settings, get_current_language

        orig_lang = get_current_language()
        try:
            set_language("zh_TW")
            settings = load_settings()
            self.assertEqual(settings.get("language"), "zh_TW")

            set_language("en")
            settings = load_settings()
            self.assertEqual(settings.get("language"), "en")
        finally:
            set_language(orig_lang)


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

    def test_parse_tx_date(self):
        # ISO formats
        self.assertEqual(parse_tx_date("2026-05-18"), date(2026, 5, 18))
        self.assertEqual(parse_tx_date("2026-05-18 14:30:00"), date(2026, 5, 18))
        # Colloquial formats
        self.assertEqual(parse_tx_date("7 May 2026"), date(2026, 5, 7))
        self.assertEqual(parse_tx_date("07 May 2026"), date(2026, 5, 7))
        self.assertEqual(parse_tx_date("May 7, 2026"), date(2026, 5, 7))
        # Slash formats
        self.assertEqual(parse_tx_date("2026/05/07"), date(2026, 5, 7))
        # None and invalid
        self.assertIsNone(parse_tx_date(None))
        self.assertIsNone(parse_tx_date(""))
        self.assertIsNone(parse_tx_date("invalid-date-string"))

    def test_calc_period_earnings(self):
        sample_txs = [
            # Week of May 18, 2026 (Mon May 18 - Sun May 24)
            {
                "date": "2026-05-19 10:00:00",
                "type": "SELL",
                "portfolio": "Growth",
                "symbol": "NVDA",
                "shares": 10.0,
                "price": 130.0,
                "total_amount": 1300.0,
                "cost_basis": 1000.0,
                "commission_fee": 5.0,
                "estimated_tax": 0.0,
                "net_amount": 1295.0,
                "net_profit": 295.0,
                "net_roi_pct": 29.5,
                "currency": "USD",
            },
            {
                "date": "2026-05-20 11:00:00",
                "type": "BUY",
                "portfolio": "Growth",
                "symbol": "AAPL",
                "shares": 5.0,
                "price": 200.0,
                "total_amount": 1000.0,
                "cost_basis": 1000.0,
                "commission_fee": 0.0,
                "estimated_tax": 0.0,
                "net_amount": 1000.0,
                "net_profit": 0.0,
                "net_roi_pct": 0.0,
                "currency": "USD",
            },
            # Earlier in May 2026 (May 05)
            {
                "date": "2026-05-05",
                "type": "SELL",
                "portfolio": "Growth",
                "symbol": "MSFT",
                "shares": 10.0,
                "price": 420.0,
                "total_amount": 4200.0,
                "cost_basis": 3800.0,
                "commission_fee": 10.0,
                "estimated_tax": 0.0,
                "net_amount": 4190.0,
                "net_profit": 390.0,
                "net_roi_pct": 10.26,
                "currency": "USD",
            },
            # In April 2026
            {
                "date": "2026-04-15",
                "type": "SELL",
                "portfolio": "Growth",
                "symbol": "GOOGL",
                "shares": 20.0,
                "price": 180.0,
                "total_amount": 3600.0,
                "cost_basis": 3000.0,
                "commission_fee": 0.0,
                "estimated_tax": 0.0,
                "net_amount": 3600.0,
                "net_profit": 600.0,
                "net_roi_pct": 20.0,
                "currency": "USD",
            },
        ]

        ref_date = date(2026, 5, 20)  # Wednesday of May 18-24

        # Test this_week
        res_week = calc_period_earnings(sample_txs, period_mode="this_week", today_override=ref_date)
        self.assertEqual(res_week["summary"]["total_realized_profit"], 295.0)
        self.assertEqual(res_week["summary"]["total_buy_volume"], 1000.0)
        self.assertEqual(res_week["summary"]["sell_count"], 1)
        self.assertEqual(res_week["summary"]["buy_count"], 1)
        self.assertEqual(len(res_week["records"]), 2)

        # Test this_month (May 2026)
        res_month = calc_period_earnings(sample_txs, period_mode="this_month", today_override=ref_date)
        self.assertEqual(res_month["summary"]["total_realized_profit"], 685.0)  # 295 + 390
        self.assertEqual(res_month["summary"]["sell_count"], 2)
        self.assertEqual(res_month["summary"]["buy_count"], 1)
        self.assertEqual(len(res_month["records"]), 3)

        # Test in_months (Monthly breakdown)
        res_in_months = calc_period_earnings(sample_txs, period_mode="in_months", today_override=ref_date)
        bd = res_in_months["breakdown"]
        self.assertEqual(len(bd), 2)  # 2026-05 and 2026-04
        self.assertEqual(bd[0]["period_label"], "2026-05")
        self.assertEqual(bd[0]["total_realized_profit"], 685.0)
        self.assertEqual(bd[1]["period_label"], "2026-04")
        self.assertEqual(bd[1]["total_realized_profit"], 600.0)

        # Test in_weeks (Weekly breakdown)
        res_in_weeks = calc_period_earnings(sample_txs, period_mode="in_weeks", today_override=ref_date)
        self.assertGreater(len(res_in_weeks["breakdown"]), 1)

        # Test custom date range (2026-04-01 to 2026-04-30)
        res_custom = calc_period_earnings(
            sample_txs,
            period_mode="custom",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
        )
        self.assertEqual(len(res_custom["records"]), 1)
        self.assertEqual(res_custom["summary"]["total_realized_profit"], 600.0)

    def test_update_and_delete_transaction(self):
        temp_csv = "temp_test_tx_update.csv"
        try:
            sample = [
                {
                    "date": "2026-05-01 10:00:00",
                    "type": "BUY",
                    "portfolio": "Default",
                    "symbol": "VOO",
                    "shares": 10.0,
                    "price": 500.0,
                    "total_amount": 5000.0,
                    "cost_basis": 5000.0,
                    "commission_fee": 0.0,
                    "estimated_tax": 0.0,
                    "net_amount": 5000.0,
                    "net_profit": 0.0,
                    "net_roi_pct": 0.0,
                    "currency": "USD",
                    "notes": "Original note",
                },
                {
                    "date": "2026-05-02 11:00:00",
                    "type": "SELL",
                    "portfolio": "Default",
                    "symbol": "VOO",
                    "shares": 5.0,
                    "price": 520.0,
                    "total_amount": 2600.0,
                    "cost_basis": 2500.0,
                    "commission_fee": 5.0,
                    "estimated_tax": 0.0,
                    "net_amount": 2595.0,
                    "net_profit": 95.0,
                    "net_roi_pct": 3.8,
                    "currency": "USD",
                    "notes": "",
                },
            ]
            save_transactions(sample, temp_csv)
            loaded = load_transactions(temp_csv)
            self.assertEqual(len(loaded), 2)

            # Update index 0
            updated_tx = dict(loaded[0])
            updated_tx["shares"] = 15.0
            updated_tx["total_amount"] = 7500.0
            updated_tx["notes"] = "Updated note"

            ok_up = update_transaction(0, updated_tx, temp_csv)
            self.assertTrue(ok_up)
            loaded_after_up = load_transactions(temp_csv)
            self.assertEqual(loaded_after_up[0]["shares"], 15.0)
            self.assertEqual(loaded_after_up[0]["notes"], "Updated note")

            # Delete index 1
            ok_del = delete_transaction(1, temp_csv)
            self.assertTrue(ok_del)
            loaded_after_del = load_transactions(temp_csv)
            self.assertEqual(len(loaded_after_del), 1)
            self.assertEqual(loaded_after_del[0]["symbol"], "VOO")
        finally:
            if os.path.exists(temp_csv):
                os.remove(temp_csv)

    def test_generate_period_earnings_report_html(self):
        temp_report = "temp_period_report.html"
        try:
            period_data = {
                "period_mode": "this_month",
                "portfolio": "Growth",
                "summary": {
                    "total_realized_profit": 1250.50,
                    "total_cost_basis": 10000.0,
                    "total_sell_proceeds": 11250.50,
                    "total_buy_volume": 5000.0,
                    "total_dividend": 50.0,
                    "net_roi_pct": 12.51,
                    "buy_count": 2,
                    "sell_count": 3,
                    "dividend_count": 1,
                    "total_transactions": 6,
                },
                "breakdown": [
                    {
                        "period_label": "2026-05",
                        "total_transactions": 6,
                        "total_buy_volume": 5000.0,
                        "total_sell_proceeds": 11250.50,
                        "total_cost_basis": 10000.0,
                        "total_realized_profit": 1250.50,
                        "net_roi_pct": 12.51,
                    }
                ],
                "records": [
                    {
                        "date": "2026-05-10",
                        "type": "SELL",
                        "portfolio": "Growth",
                        "symbol": "AAPL",
                        "shares": 10.0,
                        "price": 200.0,
                        "total_amount": 2000.0,
                        "cost_basis": 1500.0,
                        "net_profit": 500.0,
                        "net_roi_pct": 33.33,
                        "notes": "Profit taking",
                    }
                ],
            }
            ok = generate_period_earnings_report_html(period_data, temp_report)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(temp_report))
            with open(temp_report, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Period Earnings & Performance Report", content)
            self.assertIn("1,250.50", content)
            self.assertIn("AAPL", content)
        finally:
            if os.path.exists(temp_report):
                os.remove(temp_report)



class TestPortfolioFeeManagerAndCustody(unittest.TestCase):
    def setUp(self):
        self.temp_tx_csv = "test_fee_tx_temp.csv"
        self.temp_fees_json = "test_portfolio_fees_temp.json"
        if os.path.exists(self.temp_tx_csv):
            os.remove(self.temp_tx_csv)
        if os.path.exists(self.temp_fees_json):
            os.remove(self.temp_fees_json)

    def tearDown(self):
        for f in [self.temp_tx_csv, self.temp_fees_json]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        for i in range(1, 6):
            bak = f"{self.temp_tx_csv}.bak{i}"
            if os.path.exists(bak):
                try:
                    os.remove(bak)
                except Exception:
                    pass

    def test_broker_presets_structure(self):
        expected_keys = [
            "ZERO_COMMISSION",
            "HSBC_STANDARD",
            "HSBC_TRADE25",
            "CIBC_INVESTOR",
            "IBKR_FIXED",
            "CUSTOM",
        ]
        for k in expected_keys:
            self.assertIn(k, BROKER_PRESETS)
            preset = BROKER_PRESETS[k]
            self.assertIn("commission_type", preset)
            self.assertIn("commission_flat", preset)
            self.assertIn("commission_pct", preset)
            self.assertIn("commission_min", preset)
            self.assertIn("storage_fee_amount", preset)
            self.assertIn("storage_fee_frequency", preset)

    def test_calc_estimated_commission_logic(self):
        # 1. Zero commission
        save_portfolio_fee_config("ZeroTest", BROKER_PRESETS["ZERO_COMMISSION"], filepath=self.temp_fees_json)
        comm = calc_estimated_commission("ZeroTest", 100, 50.0, "BUY", filepath=self.temp_fees_json)
        self.assertEqual(comm, 0.0)

        # 2. HSBC Standard: 0.25%, min $15.00
        save_portfolio_fee_config("HSBCTest", BROKER_PRESETS["HSBC_STANDARD"], filepath=self.temp_fees_json)
        # Small trade: 10 shares @ $10 = $100 -> 0.25% is $0.25 -> minimum $15.00 applies
        comm_small = calc_estimated_commission("HSBCTest", 10, 10.0, "BUY", filepath=self.temp_fees_json)
        self.assertEqual(comm_small, 15.0)

        # Large trade: 100 shares @ $200 = $20,000 -> 0.25% is $50.00
        comm_large = calc_estimated_commission("HSBCTest", 100, 200.0, "SELL", filepath=self.temp_fees_json)
        self.assertEqual(comm_large, 50.0)

        # 3. CIBC Investor: Flat $6.95
        save_portfolio_fee_config("CIBCTest", BROKER_PRESETS["CIBC_INVESTOR"], filepath=self.temp_fees_json)
        comm_cibc = calc_estimated_commission("CIBCTest", 50, 120.0, "BUY", filepath=self.temp_fees_json)
        self.assertEqual(comm_cibc, 6.95)

        # 4. IBKR Fixed: flat $1.00 min
        save_portfolio_fee_config("IBKRTest", BROKER_PRESETS["IBKR_FIXED"], filepath=self.temp_fees_json)
        comm_ibkr = calc_estimated_commission("IBKRTest", 20, 100.0, "BUY", filepath=self.temp_fees_json)
        self.assertEqual(comm_ibkr, 1.0)

    def test_portfolio_fee_persistence_and_crud(self):
        cfg = {
            "name": "My Growth",
            "commission_type": "percent_with_min",
            "commission_flat": 0.0,
            "commission_pct": 0.15,
            "commission_min": 9.99,
            "storage_fee_amount": 5.0,
            "storage_fee_frequency": "monthly",
            "default_tax_rate_pct": 15.0,
            "notes": "Custom tariff",
        }
        # Save
        self.assertTrue(save_portfolio_fee_config("My Growth", cfg, filepath=self.temp_fees_json))
        read_cfg = get_portfolio_fee_config("My Growth", filepath=self.temp_fees_json)
        self.assertEqual(read_cfg["commission_min"], 9.99)
        self.assertEqual(read_cfg["storage_fee_amount"], 5.0)

        # Rename
        self.assertTrue(rename_portfolio_fee_config("My Growth", "My Growth Renamed", filepath=self.temp_fees_json))
        renamed_cfg = get_portfolio_fee_config("My Growth Renamed", filepath=self.temp_fees_json)
        self.assertEqual(renamed_cfg["commission_min"], 9.99)

        # Delete
        self.assertTrue(delete_portfolio_fee_config("My Growth Renamed", filepath=self.temp_fees_json))
        # After delete, should return fallback default
        fallback = get_portfolio_fee_config("My Growth Renamed", filepath=self.temp_fees_json)
        self.assertEqual(fallback["commission_flat"], 0.0)

    def test_selling_proceeds_with_min_commission(self):
        # Sell 10 shares bought at $50, selling at $60 (proceeds $600)
        # With commission_pct = 0.25% (which is $1.50) and commission_min = $15.00
        # Commission should be $15.00, not $1.50
        res = calc_selling_proceeds(
            shares_to_sell=10,
            buy_price=50.0,
            sell_price=60.0,
            commission_flat=0.0,
            commission_pct=0.25,
            tax_rate_pct=0.0,
            commission_min=15.0,
        )
        self.assertEqual(res["gross_proceeds"], 600.0)
        self.assertEqual(res["cost_basis"], 500.0)
        self.assertEqual(res["commission_fee"], 15.0)
        self.assertEqual(res["net_profit"], 85.0)  # 600 - 500 - 15 = 85.0

    def test_safe_custody_fee_logging_and_period_earnings_deduction(self):
        # 1. Log a storage fee
        ok = log_storage_fee_transaction(
            portfolio_name="HSBC Account",
            amount=5.0,
            fee_date="2026-06-15 10:00:00",
            notes="HSBC monthly safe custody fee",
            currency="USD",
            filepath_tx=self.temp_tx_csv,
        )
        self.assertTrue(ok)
        loaded_fee_txs = load_transactions(self.temp_tx_csv)
        self.assertEqual(len(loaded_fee_txs), 1)
        self.assertEqual(loaded_fee_txs[0]["type"], "FEE")
        self.assertEqual(float(loaded_fee_txs[0]["total_amount"]), 5.0)

        # 2. Add a profitable SELL transaction to the same CSV
        txs = load_transactions(self.temp_tx_csv)
        txs.append({
            "date": "2026-06-20 14:00:00",
            "type": "SELL",
            "portfolio": "HSBC Account",
            "symbol": "NVDA",
            "shares": 10.0,
            "price": 120.0,
            "total_amount": 1200.0,
            "cost_basis": 1000.0,
            "net_profit": 200.0,
            "net_roi_pct": 20.0,
            "commission": 15.0,
            "tax": 0.0,
            "notes": "Profit sale",
        })
        save_transactions(txs, self.temp_tx_csv)

        # 3. Calculate period earnings
        earnings = calc_period_earnings(
            transactions=load_transactions(self.temp_tx_csv),
            portfolio_name="HSBC Account",
            period_mode="this_month",
            today_override=date(2026, 6, 25),
        )
        # Realized profit was $200 from sell, minus $5 storage fee -> $195.00
        summary = earnings["summary"]
        self.assertEqual(summary["total_realized_profit"], 195.0)
        self.assertEqual(summary["total_fees"], 5.0)
        self.assertEqual(summary["fee_count"], 1)
        self.assertEqual(summary["sell_count"], 1)


class TestChartMetricsAndReportTab(unittest.TestCase):
    def test_chart_metric_series_modes(self):
        from chart_view import GoogleFinanceChartView
        # Create a mock or instance for helper testing
        class MockChartView:
            chart_metric = "total"
            get_portfolio_func = None
            get_converter = None
            current_scope = "portfolio"
            current_timeframe = "1Y"
            timeframe_multipliers = {
                "1D": 1.0 / 252.0,
                "5D": 5.0 / 252.0,
                "1M": 1.0 / 12.0,
                "6M": 0.5,
                "YTD": 0.5,
                "1Y": 1.0,
                "5Y": 5.0,
                "MAX": 5.0,
            }
            _get_scope_invested_and_div = GoogleFinanceChartView._get_scope_invested_and_div
            _prepare_metric_series = GoogleFinanceChartView._prepare_metric_series

        mock = MockChartView()
        # Mock _get_scope_invested_and_div to return $1,000 cost basis and $100 annual dividend
        mock._get_scope_invested_and_div = lambda: (1000.0, 100.0)

        data = {
            "prices": [1000.0, 1100.0, 1250.0],
            "timestamps": ["T1", "T2", "T3"],
            "previous_close": 980.0,
            "currency": "USD",
        }

        # 1. Mode: Total
        mock.chart_metric = "total"
        prices, ts, pc, change, pct, lc, fc, is_growth, ref, cb, div = mock._prepare_metric_series(data)
        self.assertEqual(prices, [1000.0, 1100.0, 1250.0])
        self.assertEqual(pc, 980.0)
        self.assertFalse(is_growth)
        self.assertEqual(cb, 1000.0)

        # 2. Mode: Net Growth (Excl. Invested) -> [1000-1000, 1100-1000, 1250-1000] = [0.0, 100.0, 250.0]
        mock.chart_metric = "growth"
        prices, ts, pc, curr_val, pct, lc, fc, is_growth, ref, cb, div = mock._prepare_metric_series(data)
        self.assertEqual(prices, [0.0, 100.0, 250.0])
        self.assertEqual(curr_val, 250.0)
        self.assertEqual(pct, 25.0)  # 250 / 1000 * 100%
        self.assertTrue(is_growth)
        self.assertIn("$1,000.00", ref)

        # 3. Mode: Net Growth + Dividends -> [0+0, 100+50, 250+100] = [0.0, 150.0, 350.0]
        mock.chart_metric = "growth_div"
        prices, ts, pc, curr_val, pct, lc, fc, is_growth, ref, cb, div = mock._prepare_metric_series(data)
        self.assertEqual(prices, [0.0, 150.0, 350.0])
        self.assertEqual(curr_val, 350.0)
        self.assertEqual(pct, 35.0)  # 350 / 1000 * 100%
        self.assertTrue(is_growth)

        # 4. Mode: Dividends Only -> [0.0, 50.0, 100.0]
        mock.chart_metric = "div_only"
        prices, ts, pc, curr_val, pct, lc, fc, is_growth, ref, cb, div = mock._prepare_metric_series(data)
        self.assertEqual(prices, [0.0, 50.0, 100.0])
        self.assertEqual(curr_val, 100.0)
        self.assertEqual(pct, 10.0)

    def test_chart_metric_single_stock_position_scaling(self):
        from chart_view import GoogleFinanceChartView
        class MockSingleStockChart:
            chart_metric = "growth"
            current_scope = "ALB"
            current_timeframe = "1Y"
            _get_scope_invested_and_div = GoogleFinanceChartView._get_scope_invested_and_div
            _prepare_metric_series = GoogleFinanceChartView._prepare_metric_series

        mock = MockSingleStockChart()
        # 30 shares of ALB @ $86.39 buy price = $2,591.70 cost basis
        # Mock returns (total_cb, total_div, total_shares, total_rate)
        mock._get_scope_invested_and_div = lambda: (2591.70, 48.0, 30.0, 1.0)

        # Raw stock prices for ALB (per-share)
        data = {
            "prices": [86.39, 100.0, 112.56],
            "timestamps": ["T1", "T2", "T3"],
            "previous_close": 110.0,
            "currency": "USD",
        }

        # 1. Net Growth mode should scale by 30 shares:
        # Market value = 112.56 * 30 = 3376.80
        # Net growth = 3376.80 - 2591.70 = +785.10 (+30.29%)
        mock.chart_metric = "growth"
        prices, ts, pc, curr_val, pct, lc, fc, is_growth, ref, cb, div = mock._prepare_metric_series(data)
        self.assertEqual(prices, [0.0, 408.30, 785.10])
        self.assertAlmostEqual(curr_val, 785.10, places=2)
        self.assertAlmostEqual(pct, 30.29, places=2)
        self.assertEqual(lc, "#188038")  # Green for profit
        self.assertTrue(is_growth)

        # 2. Total Value mode should scale to holding value: 3376.80
        mock.chart_metric = "total"
        prices, ts, pc, change, pct, lc, fc, is_growth, ref, cb, div = mock._prepare_metric_series(data)
        self.assertEqual(prices, [2591.70, 3000.0, 3376.80])
        self.assertAlmostEqual(prices[-1], 3376.80, places=2)
        self.assertFalse(is_growth)

    def test_chart_metric_zag_currency_and_dividend_events(self):
        from chart_view import GoogleFinanceChartView
        from datetime import datetime, timezone

        class MockZAGChart:
            chart_metric = "growth_div"
            current_scope = "ZAG:TSE"
            current_timeframe = "6M"
            current_currency = "USD"  # app default is USD
            current_portfolio_name = "CAD RRSP"
            get_converter = lambda self: None

            def get_holdings(self, port):
                return [{
                    "portfolio": "CAD RRSP",
                    "symbol": "ZAG:TSE",
                    "shares": 397.0,
                    "buy_price": 13.86,
                    "cost_basis": 5502.42,
                    "currency": "CAD",
                    "annual_dividend": 0.0,  # was 0.0 in user's CSV
                }]

            _get_scope_invested_and_div = GoogleFinanceChartView._get_scope_invested_and_div
            _prepare_metric_series = GoogleFinanceChartView._prepare_metric_series

        mock = MockZAGChart()

        # Data from chart fetcher for ZAG:TSE in CAD with 3 monthly dividend events
        t1 = datetime(2026, 4, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 5, 1, tzinfo=timezone.utc)
        t3 = datetime(2026, 6, 1, tzinfo=timezone.utc)

        data = {
            "prices": [13.86, 13.60, 13.46],
            "timestamps": [t1, t2, t3],
            "previous_close": 13.50,
            "currency": "CAD",
            "dividend_events": [
                (t1, 0.038),
                (t2, 0.038),
                (t3, 0.039),
            ],
            "period_div_per_share": 0.115,
            "annual_dividend_per_share": 0.46,
        }

        # 1. Total Value: 397 * 13.46 = 5343.62 CAD (native currency, not converted to USD)
        mock.chart_metric = "total"
        prices, ts, pc, change, pct, lc, fc, is_growth, ref, cb, div = mock._prepare_metric_series(data)
        self.assertAlmostEqual(prices[-1], 5343.62, places=2)
        self.assertEqual(cb, 5502.42)
        self.assertEqual(mock.current_scope_currency, "CAD")

        # 2. Net Growth (Excl. Invested): 5343.62 - 5502.42 = -158.80 CAD (-2.89%)
        mock.chart_metric = "growth"
        prices, ts, pc, curr_val, pct, lc, fc, is_growth, ref, cb, div = mock._prepare_metric_series(data)
        self.assertAlmostEqual(curr_val, -158.80, places=2)
        self.assertAlmostEqual(pct, -2.89, places=2)
        self.assertIn("5,502.42", ref)

        # 3. Accrued Dividends Only: 397 * 0.115 = 45.655 -> 45.65 CAD (round-to-even)
        mock.chart_metric = "div_only"
        prices, ts, pc, curr_val, pct, lc, fc, is_growth, ref, cb, div = mock._prepare_metric_series(data)
        self.assertAlmostEqual(curr_val, 45.65, places=2)
        self.assertGreater(curr_val, 0)

        # 4. Net Growth + Dividends: -158.80 + 45.65 = -113.15 CAD
        mock.chart_metric = "growth_div"
        prices, ts, pc, curr_val, pct, lc, fc, is_growth, ref, cb, div = mock._prepare_metric_series(data)
        self.assertAlmostEqual(curr_val, -113.15, places=2)
        self.assertAlmostEqual(pct, (-113.15 / 5502.42 * 100), places=2)

        # 5. Verify older dividends before timeframe start are excluded
        data_with_old_divs = dict(data)
        data_with_old_divs["dividend_events"] = [
            (datetime(2024, 1, 1, tzinfo=timezone.utc), 1.50),  # Old 2024 div
            (datetime(2025, 12, 1, tzinfo=timezone.utc), 2.00), # Old 2025 div
            (t1, 0.038),
            (t2, 0.038),
            (t3, 0.039),
        ]
        mock.chart_metric = "div_only"
        prices, ts, pc, curr_val, pct, lc, fc, is_growth, ref, cb, div = mock._prepare_metric_series(data_with_old_divs)
        # Must still be only 45.65 CAD (from t1, t2, t3), NOT 1,435.15 CAD from old years
        self.assertAlmostEqual(curr_val, 45.65, places=2)

    def test_chart_metric_combo_switching_and_no_shadowing(self):
        from chart_view import GoogleFinanceChartView

        class DummyCombo:
            def __init__(self, val):
                self.val = val
            def get(self):
                return self.val

        class MockChartObj:
            chart_metric = "total"
            chart_data = None
            _on_metric_changed = GoogleFinanceChartView._on_metric_changed

        mock_obj = MockChartObj()

        # Test Traditional Chinese
        mock_obj.metric_combo = DummyCombo("僅累積股息分派")
        mock_obj._on_metric_changed()
        self.assertEqual(mock_obj.chart_metric, "div_only", "僅累積股息分派 must select div_only, not growth_div")

        mock_obj.metric_combo = DummyCombo("淨增長 + 累積股息分派")
        mock_obj._on_metric_changed()
        self.assertEqual(mock_obj.chart_metric, "growth_div")

        # Test English
        mock_obj.metric_combo = DummyCombo("Dividends Only")
        mock_obj._on_metric_changed()
        self.assertEqual(mock_obj.chart_metric, "div_only", "Dividends Only must select div_only, not growth_div")

        mock_obj.metric_combo = DummyCombo("Net Growth + Dividends")
        mock_obj._on_metric_changed()
        self.assertEqual(mock_obj.chart_metric, "growth_div")

        # Test Simplified Chinese
        mock_obj.metric_combo = DummyCombo("仅累积股息分派")
        mock_obj._on_metric_changed()
        self.assertEqual(mock_obj.chart_metric, "div_only")

    def test_main_gui_report_tab_and_timedelta_import(self):
        # Verify timedelta is imported in main_gui
        import main_gui
        self.assertTrue(hasattr(main_gui, "timedelta"))

        # Verify ModernPortfolioApp has the expected report tab methods
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_build_report_tab"))
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_refresh_report_tab"))
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_export_report_tab_html"))
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_switch_to_report_tab"))

    def test_fee_settings_dialog_presets_and_keys(self):
        from fee_manager import BROKER_PRESETS, get_preset_display_name
        from i18n import t, set_language, TRANSLATIONS

        # 1. Verify BROKER_PRESETS keys
        for pk, pdata in BROKER_PRESETS.items():
            self.assertIn("name", pdata, f"Missing 'name' in preset {pk}")
            self.assertIn("name_key", pdata, f"Missing 'name_key' in preset {pk}")
            self.assertIn("default_name", pdata, f"Missing 'default_name' in preset {pk}")
            self.assertIn("min_commission", pdata, f"Missing 'min_commission' in preset {pk}")
            self.assertIn("commission_min", pdata, f"Missing 'commission_min' in preset {pk}")
            self.assertIn("storage_fee_freq", pdata, f"Missing 'storage_fee_freq' in preset {pk}")
            self.assertIn("storage_fee_frequency", pdata, f"Missing 'storage_fee_frequency' in preset {pk}")
            self.assertIn("tax_rate", pdata, f"Missing 'tax_rate' in preset {pk}")
            self.assertIn("notes", pdata, f"Missing 'notes' in preset {pk}")
            self.assertIn("description", pdata, f"Missing 'description' in preset {pk}")

            # Verify display name in all languages
            from i18n import get_current_language
            orig_lang_cur = get_current_language()
            try:
                for lang in ["en", "zh_TW", "zh_CN"]:
                    set_language(lang)
                    dname = get_preset_display_name(pk)
                    self.assertTrue(len(dname) > 0, f"Empty display name for {pk} in {lang}")
            finally:
                set_language(orig_lang_cur)

        # 2. Verify all fee dialog keys exist in all languages
        fee_keys = [
            "dlg_fee_settings_title",
            "lbl_fee_preset",
            "grp_comm_settings",
            "lbl_comm_type",
            "lbl_flat_fee",
            "lbl_pct_rate",
            "lbl_min_comm",
            "grp_custody_settings",
            "lbl_storage_fee",
            "lbl_fee_frequency",
            "lbl_default_tax",
            "lbl_memo",
            "col_notes",
            "btn_save_fees",
            "btn_cancel",
            "msg_fees_saved",
            "dlg_log_storage_fee_title",
            "btn_log_storage_fee",
        ]
        for lang in ["en", "zh_TW", "zh_CN"]:
            for k in fee_keys:
                self.assertIn(k, TRANSLATIONS[lang], f"Key '{k}' missing from language '{lang}'")

        # 3. Verify GUI methods exist
        import main_gui
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_open_portfolio_fee_settings_dialog"))
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_quick_log_storage_fee"))

    def test_chart_view_cjk_font_support(self):
        import chart_view
        self.assertTrue(hasattr(chart_view, "GoogleFinanceChartView"))
        # Verify CJK_FONTS list is configured if matplotlib is available
        if chart_view.MATPLOTLIB_AVAILABLE:
            import matplotlib
            sans = matplotlib.rcParams.get("font.sans-serif", [])
            self.assertTrue(any("CJK" in f or "Droid" in f or "Hei" in f for f in sans))


class TestEnhancementsAndImprovements(unittest.TestCase):
    def test_currency_allocations_calculation(self):
        from financial_calc import calc_portfolio_metrics
        holdings = [
            {"symbol": "VOO", "shares": 10.0, "current_price": 500.0, "currency": "USD", "buy_price": 400.0},
            {"symbol": "ZAG:TSE", "shares": 100.0, "current_price": 13.50, "currency": "CAD", "buy_price": 13.0},
        ]
        # Base USD, with 1 CAD = 0.75 USD
        fx_rates = {"CAD": 0.75}
        metrics = calc_portfolio_metrics(holdings, base_currency="USD", fx_rates=fx_rates)
        curr_allocs = metrics.get("currency_allocations", [])
        self.assertEqual(len(curr_allocs), 2)
        # USD: 10 * 500 = 5000 USD
        # CAD: 100 * 13.50 * 0.75 = 1012.50 USD
        # Total: 6012.50 USD
        usd_item = next(c for c in curr_allocs if c["currency"] == "USD")
        cad_item = next(c for c in curr_allocs if c["currency"] == "CAD")
        self.assertAlmostEqual(usd_item["value_base"], 5000.0, places=1)
        self.assertAlmostEqual(cad_item["value_base"], 1012.5, places=1)
        self.assertAlmostEqual(usd_item["weight_pct"] + cad_item["weight_pct"], 100.0, places=0)

    def test_dividend_frequency_classifier(self):
        from financial_calc import calc_dividend_frequency
        from datetime import datetime, timezone, timedelta

        # 12 monthly events
        now = datetime.now(timezone.utc)
        monthly_events = [(now - timedelta(days=30 * i), 0.15) for i in range(12)]
        self.assertEqual(calc_dividend_frequency(monthly_events), "Monthly")

        # 4 quarterly events
        quarterly_events = [(now - timedelta(days=90 * i), 0.50) for i in range(4)]
        self.assertEqual(calc_dividend_frequency(quarterly_events), "Quarterly")

        # 2 semi-annual events
        semiannual_events = [(now - timedelta(days=180 * i), 1.00) for i in range(2)]
        self.assertEqual(calc_dividend_frequency(semiannual_events), "Semi-Annually")

        # 1 annual event
        annual_events = [(now, 2.00)]
        self.assertEqual(calc_dividend_frequency(annual_events), "Annually")

        # Empty
        self.assertEqual(calc_dividend_frequency([]), "None")

    def test_export_period_report_to_csv(self):
        import os
        from csv_manager import export_period_report_to_csv
        test_csv_path = "test_export_period_report.csv"
        if os.path.exists(test_csv_path):
            os.remove(test_csv_path)

        mock_report = {
            "period_label": "This Month",
            "portfolio_name": "USD HSBC",
            "summary": {
                "total_realized_profit": 1500.50,
                "net_roi_pct": 12.5,
                "total_sell_proceeds": 12000.0,
                "total_cost_basis": 10499.50,
                "total_buy_volume": 5000.0,
                "total_fees_paid": 30.0,
                "buy_count": 2,
                "sell_count": 1,
                "dividend_count": 1,
            },
            "breakdown": [
                {
                    "period_label": "2026-09",
                    "total_transactions": 4,
                    "total_buy_volume": 5000.0,
                    "total_sell_proceeds": 12000.0,
                    "total_cost_basis": 10499.50,
                    "total_realized_profit": 1500.50,
                    "net_roi_pct": 12.5,
                }
            ],
            "records": [
                {
                    "date": "2026-09-15",
                    "type": "SELL",
                    "portfolio": "USD HSBC",
                    "symbol": "VOO",
                    "currency": "USD",
                    "shares": 10.0,
                    "price": 500.0,
                    "total_amount": 5000.0,
                    "commission_fee": 15.0,
                    "estimated_tax": 0.0,
                    "net_profit": 500.0,
                    "net_roi_pct": 11.1,
                    "notes": "Profit take",
                }
            ],
        }

        try:
            ok = export_period_report_to_csv(mock_report, test_csv_path)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(test_csv_path))
            with open(test_csv_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("# PERIOD EARNINGS REPORT", content)
            self.assertIn("USD HSBC", content)
            self.assertIn("1500.50", content)
            self.assertIn("Profit take", content)
        finally:
            if os.path.exists(test_csv_path):
                os.remove(test_csv_path)

    def test_chart_view_price_metric_mode(self):
        import chart_view
        self.assertTrue(hasattr(chart_view.GoogleFinanceChartView, "_prepare_metric_series"))
        self.assertTrue(hasattr(chart_view.GoogleFinanceChartView, "_on_metric_changed"))

    def test_new_i18n_keys_parity(self):
        from i18n import TRANSLATIONS
        new_keys = [
            "chart_metric_price",
            "lbl_alloc_view_mode",
            "alloc_view_assets",
            "alloc_view_currency",
            "alloc_view_sector",
            "grp_dividend_calendar",
            "btn_book_drip",
            "lbl_tax_lot_method",
            "lbl_benchmark",
            "metric_sharpe",
            "metric_max_drawdown",
            "btn_watchlist",
            "btn_column_selector",
            "btn_web_dashboard",
        ]
        for lang in ["en", "zh_TW", "zh_CN"]:
            for k in new_keys:
                self.assertIn(k, TRANSLATIONS[lang], f"Missing key {k} in {lang}")

    def test_calculator_i18n_keys_and_switching(self):
        from i18n import t, set_language, get_current_language, TRANSLATIONS

        calc_keys = [
            # Dividend & DRIP Tab
            "div_param_box", "lbl_select_from_portfolio", "lbl_div_per_share", "btn_calc_div",
            "lbl_drip_settings", "lbl_drip_monthly", "lbl_holding_days_fmt", "div_sec_earned_already",
            "lbl_purchase_date", "lbl_holding_period", "lbl_cost_basis_invested", "lbl_capital_gain_so_far",
            "lbl_past_divs_earned", "lbl_total_earned_already", "lbl_cagr", "div_sec_future_earnings",
            "lbl_milestone_1yr", "lbl_milestone_3yr", "lbl_milestone_5yr", "lbl_milestone_10yr",
            "lbl_future_new_profit", "lbl_future_total_profit", "div_sec_projections", "div_proj_annual",
            "div_proj_quarterly", "div_proj_monthly", "div_proj_yoc", "div_sec_drip",
            # Split Tab
            "split_param_box", "lbl_split_holding", "lbl_split_ratio", "lbl_split_current_price",
            "lbl_split_target_price", "lbl_split_presplit_recovery", "lbl_ratio_to", "lbl_ratio_for_every",
            "btn_calc_split", "btn_apply_split", "split_sec_earned_already", "split_sec_comparison",
            "split_sec_future", "split_sec_before", "split_sec_after", "lbl_split_cost_basis_per_share",
            "lbl_split_cur_price_per_share", "lbl_split_total_cost_basis", "lbl_split_after_effective_price",
            "lbl_future_scenarios", "msg_confirm_split_title", "msg_confirm_split_text", "msg_split_success",
            "lbl_pill_val", "lbl_pill_total", "lbl_pill_new",
            # Selling Tab
            "sell_order_box", "sell_res_card", "sell_target_card", "lbl_sell_shares",
            "lbl_sell_buy_price", "lbl_sell_price", "lbl_sell_commission", "lbl_sell_commission_flat",
            "lbl_sell_commission_pct", "lbl_sell_tax_bracket", "lbl_sell_custom_tax", "btn_calc_sell",
            "btn_execute_sell", "lbl_sell_gross", "lbl_sell_cost", "lbl_sell_gross_gain",
            "lbl_sell_estimated_tax", "lbl_sell_net_proceeds", "lbl_sell_profit", "lbl_sell_roi",
            "lbl_breakeven_price", "lbl_target_profit_input", "btn_find_target_price", "lbl_need_to_sell_at",
            "msg_confirm_sale_title", "msg_confirm_sale_text", "msg_cannot_sell_more",
            "msg_sale_recorded_title", "msg_sale_recorded_text",
        ]

        orig_lang = get_current_language()
        try:
            for lang in ["en", "zh_TW", "zh_CN"]:
                set_language(lang)
                for k in calc_keys:
                    self.assertIn(k, TRANSLATIONS[lang], f"Key '{k}' missing from {lang}")
                    val = t(k)
                    self.assertTrue(len(val) > 0, f"Translation for '{k}' in {lang} is empty")

            # Check interpolation in all languages
            for lang in ["en", "zh_TW", "zh_CN"]:
                set_language(lang)
                days_txt = t("lbl_holding_days_fmt", days=100, years=0.27)
                self.assertIn("100", days_txt)
                self.assertIn("0.27", days_txt)

                target_txt = t("lbl_need_to_sell_at", price=123.45, proceeds=5000.0)
                self.assertIn("123.45", target_txt)
                self.assertIn("5,000.00", target_txt)
        finally:
            set_language(orig_lang)

    def test_sector_inference_and_allocation(self):
        from financial_calc import infer_holding_sector, calc_portfolio_metrics
        self.assertEqual(infer_holding_sector("AAPL", "Apple Inc"), "Technology")
        self.assertEqual(infer_holding_sector("RY.TO", "Royal Bank of Canada"), "Financial Services")
        self.assertEqual(infer_holding_sector("ZAG.TO", "BMO Aggregate Bond Index ETF"), "Fixed Income / Bond")
        self.assertEqual(infer_holding_sector("SPY", "SPDR S&P 500 ETF Trust"), "Index ETF")

        holdings = [
            {"symbol": "AAPL", "name": "Apple", "shares": 10, "current_price": 200, "buy_price": 150, "currency": "USD", "dividend_yield": 0.5, "annual_dividend": 10},
            {"symbol": "ZAG.TO", "name": "BMO Bond", "shares": 100, "current_price": 14, "buy_price": 14, "currency": "CAD", "dividend_yield": 3.5, "annual_dividend": 49},
        ]
        metrics = calc_portfolio_metrics(holdings, base_currency="CAD", fx_rates={"USD": 1.35, "CAD": 1.0})
        sec_alloc = metrics.get("sector_allocations", [])
        sec_names = [s["sector"] for s in sec_alloc] if isinstance(sec_alloc, list) else list(sec_alloc.keys())
        self.assertIn("Technology", sec_names)
        self.assertIn("Fixed Income / Bond", sec_names)
        tot_wt = sum(s["weight_pct"] for s in sec_alloc) if isinstance(sec_alloc, list) else sum(s["weight_pct"] for s in sec_alloc.values())
        self.assertAlmostEqual(tot_wt, 100.0, places=1)

    def test_12_month_dividend_calendar(self):
        from financial_calc import calc_dividend_calendar
        holdings = [
            {"symbol": "AAPL", "name": "Apple", "shares": 10, "current_price": 200, "annual_dividend": 24.0, "currency": "USD"},
            {"symbol": "ZAG", "name": "ZAG Bond", "shares": 100, "current_price": 14, "annual_dividend": 48.0, "currency": "CAD"},
        ]
        cal = calc_dividend_calendar(holdings, base_currency="CAD", fx_rates={"USD": 1.30, "CAD": 1.0}, months_ahead=12)
        schedule = cal.get("schedule", [])
        self.assertEqual(len(schedule), 12)
        total_cf = sum(m["cashflow"] for m in schedule)
        self.assertGreater(total_cf, 0.0)
        self.assertAlmostEqual(total_cf, cal["annual_total"], places=2)

    def test_risk_and_return_metrics(self):
        from financial_calc import calc_risk_and_return_metrics
        # Monotonically increasing prices
        prices = [100.0, 102.0, 105.0, 107.0, 110.0, 115.0]
        metrics = calc_risk_and_return_metrics(prices)
        self.assertGreater(metrics["cagr_pct"], 0.0)
        self.assertEqual(metrics["max_drawdown_pct"], 0.0)
        self.assertGreater(metrics["sharpe_ratio"], 0.0)

        # Volatile series with drawdown
        vol_prices = [100.0, 120.0, 90.0, 110.0]
        vol_metrics = calc_risk_and_return_metrics(vol_prices)
        self.assertGreater(vol_metrics["max_drawdown_pct"], 20.0)
        self.assertGreater(vol_metrics["volatility_pct"], 0.0)

    def test_tax_lot_proceeds_accounting(self):
        from financial_calc import calc_tax_lot_proceeds
        buy_lots = [
            {"shares": 10, "price": 100.0, "date": "2024-01-01"},
            {"shares": 10, "price": 150.0, "date": "2024-06-01"},
        ]
        # Sell 10 shares at $200
        # Under FIFO: sells the first lot (cost 100). Cost basis = 1000, realized gain = 2000 - 1000 = 1000
        res_fifo = calc_tax_lot_proceeds(sale_shares=10, sale_price=200, buy_lots=buy_lots, method="FIFO")
        self.assertEqual(res_fifo["cost_basis_sold"], 1000.0)
        self.assertEqual(res_fifo["realized_gain"], 1000.0)

        # Under Specific (highest cost): sells the second lot (cost 150). Cost basis = 1500, realized gain = 500
        res_spec = calc_tax_lot_proceeds(sale_shares=10, sale_price=200, buy_lots=buy_lots, method="SPECIFIC")
        self.assertEqual(res_spec["cost_basis_sold"], 1500.0)
        self.assertEqual(res_spec["realized_gain"], 500.0)

        # Under ACB (average cost = 125): cost basis = 1250, realized gain = 750
        res_acb = calc_tax_lot_proceeds(sale_shares=10, sale_price=200, buy_lots=buy_lots, method="ACB")
        self.assertEqual(res_acb["cost_basis_sold"], 1250.0)
        self.assertEqual(res_acb["realized_gain"], 750.0)

    def test_drip_transaction_booking(self):
        import csv_manager
        temp_port = os.path.join(os.path.dirname(__file__), "test_temp_port.csv")
        temp_tx = os.path.join(os.path.dirname(__file__), "test_temp_tx.csv")
        try:
            # Seed initial holding
            init_holding = [{"symbol": "ZAG", "name": "BMO Bond", "portfolio": "Retirement", "shares": 100.0, "buy_price": 15.0, "cost_basis": 1500.0, "current_price": 15.0}]
            csv_manager.save_portfolio(init_holding, temp_port)
            csv_manager.save_transactions([], temp_tx)

            success, msg, new_shares = csv_manager.book_drip_transaction(
                symbol="ZAG",
                dividend_amount=150.0,
                reinvest_price=15.0,
                tx_date="2026-09-25",
                portfolio="Retirement",
                portfolio_file=temp_port,
                tx_file=temp_tx,
            )
            self.assertTrue(success)
            self.assertEqual(new_shares, 10.0)

            # Verify portfolio shares and basis were updated
            updated_p = csv_manager.load_portfolio(temp_port)
            self.assertEqual(len(updated_p), 1)
            self.assertEqual(updated_p[0]["shares"], 110.0)
            self.assertEqual(updated_p[0]["cost_basis"], 1650.0)

            # Verify transaction record was added
            txs = csv_manager.load_transactions(temp_tx)
            self.assertEqual(len(txs), 1)
            self.assertEqual(txs[0]["type"], "DRIP")
            self.assertEqual(float(txs[0]["shares"]), 10.0)
        finally:
            if os.path.exists(temp_port):
                os.remove(temp_port)
            if os.path.exists(temp_tx):
                os.remove(temp_tx)

    def test_watchlist_crud(self):
        import csv_manager
        temp_watch = os.path.join(os.path.dirname(__file__), "test_temp_watch.csv")
        try:
            csv_manager.save_watchlist([], temp_watch)
            self.assertTrue(csv_manager.add_to_watchlist("NVDA", "Nvidia Corp", 110.0, filepath=temp_watch))
            self.assertTrue(csv_manager.add_to_watchlist("MSFT", "Microsoft", 400.0, filepath=temp_watch))
            items = csv_manager.load_watchlist(temp_watch)
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]["symbol"], "NVDA")

            # Remove NVDA
            self.assertTrue(csv_manager.remove_from_watchlist("NVDA", temp_watch))
            items_after = csv_manager.load_watchlist(temp_watch)
            self.assertEqual(len(items_after), 1)
            self.assertEqual(items_after[0]["symbol"], "MSFT")
        finally:
            if os.path.exists(temp_watch):
                os.remove(temp_watch)

    def test_web_server_embedded(self):
        import web_server
        port = web_server.start_server(port=9876)
        self.assertTrue(web_server.is_running())
    def test_holding_edit_and_currency_preservation(self):
        import csv_manager
        temp_csv = os.path.join(os.path.dirname(__file__), "test_temp_edit_port.csv")
        try:
            # 1. Initial holding with CAD
            holdings = [
                {
                    "portfolio": "USD RRSP",
                    "symbol": "DRAM",
                    "name": "Global X AI Memory Index ETF",
                    "shares": 10.0,
                    "buy_price": 48.68,
                    "current_price": 21.38,
                    "currency": "CAD",
                }
            ]
            csv_manager.save_portfolio(holdings, temp_csv)
            loaded = csv_manager.load_portfolio(temp_csv, portfolio_name=None)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["currency"], "CAD")

            # 2. Simulate user editing holding: switch CAD -> USD and change shares
            matched = loaded[0]
            matched["currency"] = "USD"
            matched["shares"] = 25.0
            matched["buy_price"] = 40.0
            csv_manager.save_portfolio(loaded, temp_csv)

            # 3. Reload and verify edit persisted
            reloaded = csv_manager.load_portfolio(temp_csv, portfolio_name=None)
            self.assertEqual(reloaded[0]["currency"], "USD")
            self.assertEqual(reloaded[0]["shares"], 25.0)
            self.assertEqual(reloaded[0]["buy_price"], 40.0)

            # 4. Simulate quote fetcher response returning CAD for DRAM
            quote_results = [
                ("DRAM", {
                    "success": True,
                    "price": 22.50,
                    "name": "Global X AI Memory Index ETF",
                    "change": 1.12,
                    "change_percent": 5.24,
                    "currency": "CAD",  # Ticker on TSX is CAD, but user configured USD
                })
            ]
            for sym, q in quote_results:
                if q.get("success"):
                    for h in reloaded:
                        if h["symbol"] == sym:
                            h["current_price"] = q["price"]
                            # Must NOT overwrite user-set currency
                            if q.get("currency") and not h.get("currency"):
                                h["currency"] = q["currency"]

            # 5. Verify holding currency remains USD
            self.assertEqual(reloaded[0]["currency"], "USD")
            self.assertEqual(reloaded[0]["current_price"], 22.50)
            csv_manager.save_portfolio(reloaded, temp_csv)

            # 6. Verify persisted CSV still contains USD
            final_loaded = csv_manager.load_portfolio(temp_csv, portfolio_name=None)
            self.assertEqual(final_loaded[0]["currency"], "USD")
        finally:
            if os.path.exists(temp_csv):
                os.remove(temp_csv)


class TestChartViewHeaderUpdate(unittest.TestCase):
    """Test chart view header update logic and metric mode switches."""

    def test_update_header_all_modes_and_fallbacks(self):
        from unittest.mock import MagicMock
        from chart_view import GoogleFinanceChartView

        mock_view = MagicMock()
        mock_view.current_scope = "DRAM:TSE"
        mock_view.current_portfolio_name = "Tech"
        mock_view.current_timeframe = "1M"
        mock_view.chart_data = {
            "annual_dividend_per_share": 1.20,
            "dividend_events": [("2026-08-01", 0.10)],
        }

        modes = ["total", "price", "growth", "growth_div", "div_only"]
        for m in modes:
            mock_view.chart_metric = m
            # Should not raise NameError or TypeError when data=None
            GoogleFinanceChartView._update_header(
                mock_view,
                curr_price=10.0,
                change=0.5,
                change_pct=5.0,
                curr_sym="$",
                currency="CAD",
                is_growth_mode=False,
                total_cb=100.0,
                total_div=5.0,
                total_shares=10.0,
                scale_factor=1.0,
                data=None,
            )
            # Should not raise NameError or TypeError when data is explicitly passed
            GoogleFinanceChartView._update_header(
                mock_view,
                curr_price=10.0,
                change=0.5,
                change_pct=5.0,
                curr_sym="$",
                currency="CAD",
                is_growth_mode=False,
                total_cb=100.0,
                total_div=5.0,
                total_shares=10.0,
                scale_factor=1.0,
                data={"annual_dividend_per_share": 2.50, "dividend_events": []},
            )


class TestMultiplePortfolioCreationAndSelection(unittest.TestCase):
    """Test creation of multiple portfolios, ensuring they don't replace each other and are selectable."""

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_json = os.path.join(self.temp_dir.name, "portfolios.json")
        self.test_csv = os.path.join(self.temp_dir.name, "portfolio.csv")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_multiple_portfolios_persistence(self):
        from csv_manager import (
            load_registered_portfolios,
            save_registered_portfolios,
        )
        # 1. Initialize registered portfolios
        save_registered_portfolios(["CAD RRSP", "USD HSBC"], self.test_json)
        self.assertIn("CAD RRSP", load_registered_portfolios(self.test_json))

        # Add "CAD CIBC Investment"
        ports = load_registered_portfolios(self.test_json)
        ports.append("CAD CIBC Investment")
        save_registered_portfolios(ports, self.test_json)
        self.assertIn("CAD CIBC Investment", load_registered_portfolios(self.test_json))

        # 2. Add second portfolio "USD CIBC Investment" - must NOT replace the first!
        ports = load_registered_portfolios(self.test_json)
        ports.append("USD CIBC Investment")
        save_registered_portfolios(ports, self.test_json)

        loaded = load_registered_portfolios(self.test_json)
        self.assertIn("CAD CIBC Investment", loaded, "First newly added portfolio must not be replaced!")
        self.assertIn("USD CIBC Investment", loaded, "Second newly added portfolio must be present!")
        self.assertIn("CAD RRSP", loaded)
        self.assertIn("USD HSBC", loaded)

    def test_gui_portfolio_dropdown_values_and_selection(self):
        from unittest.mock import MagicMock
        from main_gui import ModernPortfolioApp
        from csv_manager import add_portfolio, get_portfolio_names, PORTFOLIO_CSV

        # Add both test portfolios
        add_portfolio("CAD CIBC Investment")
        add_portfolio("USD CIBC Investment")

        mock_app = MagicMock()
        mock_app.current_portfolio = "CAD CIBC Investment"
        mock_app.all_holdings = []

        dropdown_vals = ModernPortfolioApp._get_portfolio_dropdown_values(mock_app)
        self.assertIn("CAD CIBC Investment", dropdown_vals, "CAD CIBC Investment must be selectable in dropdown!")
        self.assertIn("USD CIBC Investment", dropdown_vals, "USD CIBC Investment must be selectable in dropdown!")
        self.assertIn("All Portfolios (Consolidated)", dropdown_vals)

        # Verify switching to newly added empty portfolio
        mock_app.portfolio_var = MagicMock()
        mock_app.portfolio_var.get.return_value = "USD CIBC Investment"
        mock_app.cards = {k: MagicMock() for k in ["total_value", "total_gain", "annual_dividend", "monthly_dividend"]}
        mock_app.analytics_kpis = {k: (MagicMock(), MagicMock(), MagicMock()) for k in ["top_asset", "concentration", "portfolio_yoc", "div_yield", "best_performer", "worst_performer"]}
        mock_app.summary_currency = "USD"
        mock_app.fetcher = MagicMock()
        mock_app.fetcher.fx_cache = {}

        ModernPortfolioApp._on_portfolio_selected(mock_app)
        self.assertEqual(mock_app.current_portfolio, "USD CIBC Investment")
        self.assertEqual(len(mock_app.holdings), 0)


class TestWatchlistMonitoringTabAndImport(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_csv = os.path.join(self.test_dir, "test_watchlist.csv")

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_parse_symbols_text_newlines_and_tabs(self):
        from csv_manager import parse_symbols_text

        # 1. Plain newlines
        txt1 = "AAPL\nMSFT\nGOOG:NASDAQ\n"
        res1 = parse_symbols_text(txt1)
        self.assertEqual(len(res1), 3)
        self.assertEqual(res1[0]["symbol"], "AAPL")
        self.assertEqual(res1[1]["symbol"], "MSFT")
        self.assertEqual(res1[2]["symbol"], "GOOG:NASDAQ")

        # 2. Tabs from Excel/Google Sheets: Symbol \t Target
        txt2 = "AAPL\t175.50\nMSFT\t380.00"
        res2 = parse_symbols_text(txt2)
        self.assertEqual(len(res2), 2)
        self.assertEqual(res2[0]["symbol"], "AAPL")
        self.assertEqual(res2[0]["target_buy_price"], 175.50)
        self.assertEqual(res2[1]["symbol"], "MSFT")
        self.assertEqual(res2[1]["target_buy_price"], 380.00)

        # 3. Tabs with Symbol \t Name \t Target \t Currency \t Notes
        txt3 = "TD:TSE\tToronto-Dominion Bank\t78.50\tCAD\tDividend core"
        res3 = parse_symbols_text(txt3)
        self.assertEqual(len(res3), 1)
        self.assertEqual(res3[0]["symbol"], "TD:TSE")
        self.assertEqual(res3[0]["name"], "Toronto-Dominion Bank")
        self.assertEqual(res3[0]["target_buy_price"], 78.50)
        self.assertEqual(res3[0]["currency"], "CAD")
        self.assertEqual(res3[0]["notes"], "Dividend core")

        # 4. Mixed commas, spaces, tabs
        txt4 = "NVDA, AMD, INTC\t100\nAMZN"
        res4 = parse_symbols_text(txt4)
        syms4 = [r["symbol"] for r in res4]
        self.assertIn("NVDA", syms4)
        self.assertIn("AMD", syms4)
        self.assertIn("INTC", syms4)
        self.assertIn("AMZN", syms4)

    def test_bulk_add_to_watchlist(self):
        from csv_manager import bulk_add_to_watchlist, load_watchlist

        records = [
            {"symbol": "AAPL", "name": "Apple", "target_buy_price": 180.0, "currency": "USD", "notes": "Tech"},
            {"symbol": "MSFT", "name": "Microsoft", "target_buy_price": 350.0, "currency": "USD", "notes": "Cloud"},
        ]
        added = bulk_add_to_watchlist(records, filepath=self.test_csv)
        self.assertEqual(added, 2)

        items = load_watchlist(filepath=self.test_csv)
        self.assertEqual(len(items), 2)
        sym_map = {it["symbol"]: it for it in items}
        self.assertIn("AAPL", sym_map)
        self.assertIn("MSFT", sym_map)
        self.assertEqual(sym_map["AAPL"]["target_buy_price"], 180.0)

        # Update existing and add new
        update_records = [
            {"symbol": "AAPL", "target_buy_price": 195.0, "notes": "Updated note"},
            {"symbol": "GOOG", "name": "Alphabet", "target_buy_price": 160.0},
        ]
        bulk_add_to_watchlist(update_records, filepath=self.test_csv)
        items2 = load_watchlist(filepath=self.test_csv)
        self.assertEqual(len(items2), 3)
        sym_map2 = {it["symbol"]: it for it in items2}
        self.assertEqual(sym_map2["AAPL"]["target_buy_price"], 195.0)
        self.assertEqual(sym_map2["AAPL"]["notes"], "Updated note")
        self.assertIn("GOOG", sym_map2)

    def test_import_watchlist_from_csv(self):
        from csv_manager import import_watchlist_from_csv, load_watchlist

        # Create sample standard CSV
        csv_file = os.path.join(self.test_dir, "input.csv")
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write("Symbol,Name,Target Price,Currency,Notes\n")
            f.write("BNS:TSE,Bank of Nova Scotia,65.50,CAD,Banking\n")
            f.write("ENB:TSE,Enbridge Inc,48.20,CAD,Energy\n")

        res = import_watchlist_from_csv(csv_file, target_filepath=self.test_csv)
        count = res[0] if isinstance(res, tuple) else res
        self.assertEqual(count, 2)

        items = load_watchlist(filepath=self.test_csv)
        self.assertEqual(len(items), 2)
        bns = next(it for it in items if it["symbol"] == "BNS:TSE")
        self.assertEqual(bns["target_buy_price"], 65.50)
        self.assertEqual(bns["currency"], "CAD")

    def test_update_watchlist_item_symbol_and_currency(self):
        from csv_manager import add_to_watchlist, update_watchlist_item, load_watchlist

        # Add initial item with incorrect symbol and wrong currency
        add_to_watchlist("0005.HK", "HSBC Holdings", 60.0, currency="USD", notes="Original note", filepath=self.test_csv)
        items = load_watchlist(filepath=self.test_csv)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["symbol"], "0005.HK")
        self.assertEqual(items[0]["currency"], "USD")

        # User edits incorrect symbol 0005.HK -> 0005:HKG and currency USD -> HKD
        ok = update_watchlist_item(
            old_symbol="0005.HK",
            new_symbol="0005:HKG",
            name="HSBC Holdings plc",
            target_price=68.50,
            currency="HKD",
            notes="Updated to Hong Kong market",
            filepath=self.test_csv,
        )
        self.assertTrue(ok)

        # Verify old symbol is replaced, not duplicated
        items2 = load_watchlist(filepath=self.test_csv)
        self.assertEqual(len(items2), 1, "Must not duplicate records when symbol is edited!")
        self.assertEqual(items2[0]["symbol"], "0005:HKG")
        self.assertEqual(items2[0]["name"], "HSBC Holdings plc")
        self.assertEqual(items2[0]["target_price"], 68.50)
        self.assertEqual(items2[0]["target_buy_price"], 68.50)
        self.assertEqual(items2[0]["currency"], "HKD")
        self.assertEqual(items2[0]["notes"], "Updated to Hong Kong market")

    def test_tab_order_persistence_and_reordering(self):
        from main_gui import ModernPortfolioApp
        from unittest.mock import MagicMock

        mock_app = MagicMock()
        mock_app.notebook = MagicMock()
        mock_app.tab_holdings = "tab_w_holdings"
        mock_app.tab_analytics = "tab_w_analytics"
        mock_app.tab_chart = "tab_w_chart"
        mock_app.tab_dividend = "tab_w_dividend"
        mock_app.tab_split = "tab_w_split"
        mock_app.tab_sell = "tab_w_sell"
        mock_app.tab_history = "tab_w_history"
        mock_app.tab_report = "tab_w_report"
        mock_app.tab_watchlist = "tab_w_watchlist"

        widget_map, key_map = ModernPortfolioApp._get_tab_key_maps(mock_app)
        self.assertEqual(key_map["tab_w_holdings"], "holdings")
        self.assertEqual(key_map["tab_w_watchlist"], "watchlist")

        # Test move tab
        mock_app.notebook.tabs.return_value = ["tab_w_holdings", "tab_w_analytics", "tab_w_watchlist"]
        ModernPortfolioApp._move_tab_by_index(mock_app, current_idx=2, direction=-1)
        mock_app.notebook.insert.assert_called_with(1, "tab_w_watchlist")

    def test_monitoring_tab_i18n_keys(self):
        from i18n import TRANSLATIONS
        required_keys = [
            "tab_monitoring",
            "btn_batch_import",
            "btn_paste_import",
            "btn_csv_import",
            "btn_buy_into_portfolio",
            "col_watch_status",
            "dlg_add_asset_title",
            "dlg_edit_watchlist_title",
            "lbl_asset_type",
            "btn_lookup",
            "lbl_shares_count",
            "lbl_buy_price_share",
            "btn_use_live_price",
            "lbl_target_sell",
            "lbl_stop_loss",
            "btn_save_stock_to_portfolio",
            "btn_save_changes",
            "menu_move_tab_left",
            "menu_move_tab_right",
            "menu_reset_tab_order",
            "lbl_watch_search",
            "btn_edit_watchlist",
        ]
        for lang in ["en", "zh_TW", "zh_CN"]:
            for k in required_keys:
                self.assertIn(k, TRANSLATIONS[lang], f"Key '{k}' missing in {lang}")
                self.assertTrue(len(TRANSLATIONS[lang][k]) > 0, f"Key '{k}' in {lang} is empty")

    def test_watchlist_double_click_opens_edit_dialog(self):
        """Verify that double clicking on watchlist items opens Edit dialog, not Buy dialog."""
        class MockApp:
            def __init__(self):
                self.edit_opened = False
                self.buy_opened = False
                self.watchlist_tree = self

            def selection(self):
                return ["item1"]

            def _open_edit_watchlist_dialog(self):
                self.edit_opened = True

            def _buy_from_watchlist_into_portfolio(self):
                self.buy_opened = True

        app = MockApp()
        from main_gui import ModernPortfolioApp
        ModernPortfolioApp._on_watchlist_double_click(app)
        self.assertTrue(app.edit_opened)
        self.assertFalse(app.buy_opened)

    def test_google_finance_symbol_normalization(self):
        """Verify that .HK, .TO, and numeric tickers are routed to the proper exchange URL."""
        from google_finance_fetcher import GoogleFinanceFetcher
        fetcher = GoogleFinanceFetcher()
        called_urls = []
        fetcher._fetch_url = lambda url, sym: called_urls.append((url, sym)) or {"success": True, "symbol": sym, "price": 10.0}

        # 1. 0005.HK -> 0005:HKG
        fetcher.fetch_quote("0005.HK")
        self.assertIn("https://www.google.com/finance/quote/0005:HKG", [u[0] for u in called_urls])

        # 2. 1137 -> 1137:HKG
        called_urls.clear()
        fetcher.fetch_quote("1137")
        self.assertIn("https://www.google.com/finance/quote/1137:HKG", [u[0] for u in called_urls])

        # 3. VFV.TO -> VFV:TSE
        called_urls.clear()
        fetcher.fetch_quote("VFV.TO")
    def test_calc_portfolio_rebalance_full(self):
        """Test portfolio rebalance calculator in full mode (buy & sell)."""
        from financial_calc import calc_portfolio_rebalance
        holdings = [
            {"symbol": "AAPL", "name": "Apple", "shares": 10, "current_price": 100.0, "currency": "USD"}, # $1000
            {"symbol": "MSFT", "name": "Microsoft", "shares": 10, "current_price": 100.0, "currency": "USD"}, # $1000
        ] # Total = $2000
        # Target: AAPL 70% ($1400), MSFT 30% ($600)
        targets = {"AAPL": 70.0, "MSFT": 30.0}
        res = calc_portfolio_rebalance(holdings, targets, new_cash=0.0, mode="full")
        self.assertEqual(res["total_portfolio_value"], 2000.0)
        self.assertEqual(res["new_total_value"], 2000.0)
        orders = {o["symbol"]: o for o in res["orders"]}
        self.assertEqual(orders["AAPL"]["action"], "BUY")
        self.assertEqual(orders["AAPL"]["shares_diff"], 4) # +4 shares = +$400 -> $1400 (70%)
        self.assertEqual(orders["MSFT"]["action"], "SELL")
        self.assertEqual(orders["MSFT"]["shares_diff"], -4) # -4 shares = -$400 -> $600 (30%)

    def test_calc_portfolio_rebalance_cash_only(self):
        """Test portfolio rebalance calculator in cash injection only mode (no selling)."""
        from financial_calc import calc_portfolio_rebalance
        holdings = [
            {"symbol": "AAPL", "name": "Apple", "shares": 10, "current_price": 100.0, "currency": "USD"}, # $1000
            {"symbol": "MSFT", "name": "Microsoft", "shares": 5, "current_price": 100.0, "currency": "USD"}, # $500
        ] # Total = $1500 + $500 cash = $2000
        # Target: 50% each ($1000 each)
        targets = {"AAPL": 50.0, "MSFT": 50.0}
        res = calc_portfolio_rebalance(holdings, targets, new_cash=500.0, mode="cash_only")
        self.assertEqual(res["new_total_value"], 2000.0)
        orders = {o["symbol"]: o for o in res["orders"]}
        # In cash only mode, AAPL is already at $1000 (50%), so MSFT gets all $500 (+5 shares)
        self.assertEqual(orders["AAPL"]["action"], "HOLD")
        self.assertEqual(orders["MSFT"]["action"], "BUY")
        self.assertEqual(orders["MSFT"]["shares_diff"], 5)

    def test_calc_fire_metrics(self):
        """Test FIRE / Financial Freedom calculator."""
        from financial_calc import calc_fire_metrics
        # Annual div: $12,000 ($1,000/mo), monthly expense: $4,000 ($48,000/yr)
        # 4% rule target capital: 48,000 * 25 = $1,200,000
        res = calc_fire_metrics(
            current_annual_div=12000.0,
            target_monthly_expense=4000.0,
            expected_div_growth=0.05,
            current_portfolio_val=300000.0,
            monthly_savings=2000.0,
        )
        self.assertEqual(res["target_annual_expense"], 48000.0)
        self.assertEqual(res["freedom_coverage_pct"], 25.0) # 12k / 48k = 25% (Coast FIRE)
        self.assertEqual(res["fire_number_4pct"], 1200000.0)
        self.assertIn("milestones", res)
        self.assertEqual(res["milestones"]["coast"], 12000.0)
        self.assertEqual(res["milestones"]["barista"], 24000.0)
        self.assertEqual(res["milestones"]["lean"], 36000.0)
        self.assertEqual(res["milestones"]["full"], 48000.0)
        self.assertGreater(res["years_to_crossover"], 0.0)
        self.assertLess(res["years_to_crossover"], 50.0)

    def test_calc_fire_metrics_bernstein_framework(self):
        """Test William Bernstein's RLE, Burn Rate Zones, and Liability Matching Portfolio."""
        from financial_calc import calc_fire_metrics
        # Fritz case: $750k portfolio, $4k/mo ($48k/yr) exp, $18k/yr pension -> RLE = $30k/yr
        fritz = calc_fire_metrics(
            current_annual_div=15000.0,
            target_monthly_expense=4000.0,
            guaranteed_annual_pension=18000.0,
            target_safe_years=25.0,
            current_portfolio_val=750000.0,
            monthly_savings=0.0,
        )
        self.assertEqual(fritz["rle_annual"], 30000.0)
        self.assertEqual(fritz["rle_monthly"], 2500.0)
        self.assertEqual(fritz["burn_rate_pct"], 4.0)
        self.assertEqual(fritz["burn_zone"], "red") # > 3.5%
        self.assertEqual(fritz["liability_matching_target"], 750000.0) # 25 * 30k
        self.assertEqual(fritz["liability_coverage_pct"], 100.0)
        self.assertEqual(fritz["risk_portfolio_surplus"], 0.0)
        self.assertEqual(fritz["bernstein_swr_32_target"], 937500.0) # 30,000 * 31.25

        # Frank case: $3M portfolio, $5k/mo ($60k/yr) exp, $20k/yr pension -> RLE = $40k/yr
        frank = calc_fire_metrics(
            current_annual_div=50000.0,
            target_monthly_expense=5000.0,
            guaranteed_annual_pension=20000.0,
            target_safe_years=25.0,
            current_portfolio_val=3000000.0,
            monthly_savings=0.0,
        )
        self.assertEqual(frank["rle_annual"], 40000.0)
        self.assertEqual(frank["burn_rate_pct"], 1.33)
        self.assertEqual(frank["burn_zone"], "green") # < 2.0%
        self.assertEqual(frank["liability_matching_target"], 1000000.0)
        self.assertEqual(frank["risk_portfolio_surplus"], 2000000.0) # $2M can be invested in Risk Portfolio!
        self.assertEqual(frank["dividend_rle_coverage_pct"], 125.0) # 50k / 40k = 125%

    def test_data_integrity_scan_and_repair(self):
        """Test Automated Data Health & Integrity Scanner and Auto-Fix."""
        from csv_manager import scan_data_integrity, repair_data_integrity
        with tempfile.TemporaryDirectory() as tmpdir:
            p_file = os.path.join(tmpdir, "test_portfolio.csv")
            w_file = os.path.join(tmpdir, "test_watchlist.csv")

            from csv_manager import save_portfolio, save_watchlist
            save_portfolio([
                {"portfolio": "Tech", "symbol": "AAPL", "name": "Apple", "shares": 10.0, "buy_price": 150.0, "current_price": 180.0, "currency": ""},
                {"portfolio": "Tech", "symbol": "AAPL", "name": "Apple", "shares": 10.0, "buy_price": 160.0, "current_price": 180.0, "currency": "USD"},
            ], filepath=p_file)

            save_watchlist([
                {"symbol": "0005", "name": "HSBC", "target_buy_price": 60.0, "currency": "HKD", "notes": "", "added_date": "2026-01-01", "tags": "Div"},
                {"symbol": "0005:HKG", "name": "HSBC", "target_buy_price": 60.0, "currency": "HKD", "notes": "", "added_date": "2026-01-01", "tags": "Banking"},
            ], filepath=w_file)

            # Scan should detect issues
            scan_res = scan_data_integrity(p_file, w_file)
            self.assertFalse(scan_res["healthy"])
            self.assertGreater(len(scan_res["issues"]), 0)

            # Repair
            rep = repair_data_integrity(p_file, w_file)
            self.assertGreater(len(rep["repaired"]), 0)

            # Re-scan should find 0 issues
            remaining = scan_data_integrity(p_file, w_file)
            self.assertTrue(remaining["healthy"])
            self.assertEqual(remaining["total_issues"], 0)

            # Verify AAPL was merged to 20 shares with weighted average price $155.0 and USD currency
            from csv_manager import load_portfolio
            holdings = load_portfolio(p_file, portfolio_name=None)
            self.assertEqual(len(holdings), 1)
            self.assertEqual(holdings[0]["symbol"], "AAPL")
            self.assertEqual(holdings[0]["shares"], 20.0)
            self.assertEqual(holdings[0]["buy_price"], 155.0)
            self.assertEqual(holdings[0]["currency"], "USD")

    def test_watchlist_tags_persistence(self):
        """Test watchlist category tags support in save, load, add, update."""
        from csv_manager import load_watchlist, save_watchlist, add_to_watchlist, update_watchlist_item
        with tempfile.TemporaryDirectory() as tmpdir:
            w_file = os.path.join(tmpdir, "watchlist.csv")
            add_to_watchlist("VOO", "Vanguard S&P 500", 450.0, currency="USD", notes="Core ETF", tags="Index,US", filepath=w_file)
            items = load_watchlist(w_file)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["tags"], "Index,US")

            # Update item
            update_watchlist_item("VOO", "VOO", "Vanguard S&P 500", 440.0, currency="USD", notes="Core ETF", tags="Core,Dividend", filepath=w_file)
            items2 = load_watchlist(w_file)
            self.assertEqual(items2[0]["tags"], "Core,Dividend")
            self.assertEqual(items2[0]["target_buy_price"], 440.0)

    def test_fire_dialog_and_guide_support(self):
        """Test existence of enhanced FIRE dialog and feature guide dialog methods."""
        import main_gui
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_show_fire_dialog"))
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_open_feature_guide_dialog"))

    def test_i18n_guide_and_fire_keys(self):
        """Test that all new i18n keys for Bernstein FIRE and Feature Guide exist across all supported languages."""
        from i18n import TRANSLATIONS
        required_keys = [
            "btn_feature_guide", "dlg_feature_guide_title", "lbl_guaranteed_pension",
            "lbl_safe_years", "lbl_rle", "lbl_burn_rate", "lbl_liability_matching",
            "lbl_risk_portfolio", "lbl_bernstein_swr", "lbl_preset_profiles",
            "preset_young", "preset_transition", "preset_fritz", "preset_frank",
            "lbl_quick_exp", "zone_green", "zone_yellow", "zone_red"
        ]
        for lang in ("en", "zh_TW", "zh_CN"):
            self.assertIn(lang, TRANSLATIONS)
            for k in required_keys:
                self.assertIn(k, TRANSLATIONS[lang], f"Missing key '{k}' in language '{lang}'")

    def test_fire_step_by_step_metrics(self):
        """Test Step-by-Step age, retirement timeline, gap analysis, and pension boost."""
        from financial_calc import calc_fire_metrics
        # Age 45, retire at 60 (15 yrs to accumulate), 90 life expectancy (30 yrs in retirement)
        # Monthly exp $4000 ($48k/yr), Pension $12,000/yr
        # Safe assets held = $100,000, Total portfolio = $500,000, Annual div = $15,000
        res = calc_fire_metrics(
            current_annual_div=15000.0,
            target_monthly_expense=4000.0,
            expected_div_growth=0.05,
            current_portfolio_val=500000.0,
            monthly_savings=2000.0,
            guaranteed_annual_pension=12000.0,
            target_safe_years=25.0,
            current_age=45,
            retire_age=60,
            life_expectancy=90,
            current_safe_assets=100000.0,
            delay_pension_to_70=False,
        )
        self.assertEqual(res["years_to_retire"], 15)
        self.assertEqual(res["retirement_duration_years"], 30)
        self.assertEqual(res["rle_annual"], 36000.0) # 48k - 12k
        self.assertEqual(res["liability_matching_target"], 900000.0) # 36k * 25
        self.assertEqual(res["safe_asset_gap"], 800000.0) # 900k - 100k
        self.assertEqual(res["dividend_gap_annual"], 21000.0) # 36k - 15k
        self.assertGreater(res["capital_gap_bernstein"], 0.0)
        self.assertGreater(res["monthly_savings_needed"], 0.0)
        self.assertIn("recommended_safe_instruments", res)
        self.assertGreater(len(res["recommended_safe_instruments"]), 0)

        # Test Delay Pension to 70 boost (+28% annuity)
        res_delayed = calc_fire_metrics(
            current_annual_div=15000.0,
            target_monthly_expense=4000.0,
            guaranteed_annual_pension=12000.0,
            target_safe_years=25.0,
            current_age=45,
            retire_age=60,
            life_expectancy=90,
            current_safe_assets=100000.0,
            delay_pension_to_70=True,
        )
        # Pension 12,000 * 1.28 = 15,360
        self.assertEqual(res_delayed["guaranteed_annual_pension"], 15360.0)
        self.assertEqual(res_delayed["rle_annual"], 32640.0) # 48,000 - 15,360 = 32,640 (RLE reduced!)
        self.assertLess(res_delayed["safe_asset_gap"], res["safe_asset_gap"]) # Less safe assets needed!

    def test_fire_tab_methods_exist(self):
        """Test existence of tab_fire methods and asset classification on ModernPortfolioApp."""
        import main_gui
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_build_fire_tab"))
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_refresh_fire_tab"))
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_switch_to_fire_tab"))
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_get_holding_asset_class"))
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_apply_fire_to_rebalance"))
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_export_fire_report_action"))

        # Test asset classifier logic
        dummy_app = object.__new__(main_gui.ModernPortfolioApp)
        self.assertEqual(main_gui.ModernPortfolioApp._get_holding_asset_class(dummy_app, {"symbol": "TIP", "name": "iShares TIPS"}), "safe")
        self.assertEqual(main_gui.ModernPortfolioApp._get_holding_asset_class(dummy_app, {"symbol": "XSB.TO", "name": "Canadian Short Bond"}), "safe")
        self.assertEqual(main_gui.ModernPortfolioApp._get_holding_asset_class(dummy_app, {"symbol": "SPY", "name": "SPDR S&P 500"}), "equity")
        self.assertEqual(main_gui.ModernPortfolioApp._get_holding_asset_class(dummy_app, {"symbol": "0005.HK", "name": "HSBC Holdings"}), "equity")

    def test_refresh_fire_tab_execution(self):
        """Test that _refresh_fire_tab executes cleanly with all widget bindings without NameError."""
        import main_gui
        from unittest.mock import MagicMock, patch

        app = object.__new__(main_gui.ModernPortfolioApp)
        app.holdings = [{"symbol": "VOO", "shares": 100, "current_price": 500.0, "currency": "USD"}]
        app.summary_currency = "USD"
        app.converter = MagicMock()
        app.converter.format_money = lambda v, c: f"${v:,.2f}"
        app.converter.convert = lambda v, f, t: v
        app.tab_fire = MagicMock()
        app.fire_holdings_tree = MagicMock()
        app.fire_audit_summary_lbl = MagicMock()
        app.fire_outside_safe_entry = MagicMock(get=lambda: "0.0")
        app.fire_age_spin = MagicMock(get=lambda: "45")
        app.fire_retire_age_spin = MagicMock(get=lambda: "60")
        app.fire_horizon_spin = MagicMock(get=lambda: "90")
        app.fire_safe_years_combo = MagicMock(get=lambda: "25")
        app.fire_exp_entry = MagicMock(get=lambda: "3500")
        app.fire_pension_entry = MagicMock(get=lambda: "15000")
        app.fire_savings_entry = MagicMock(get=lambda: "500")
        app.fire_growth_entry = MagicMock(get=lambda: "5.0")
        app.fire_ess_exp_entry = MagicMock(get=lambda: "2000")
        app.fire_disc_exp_entry = MagicMock(get=lambda: "1500")
        app.fire_cape_spin = MagicMock(get=lambda: "34.0")
        app.fire_delay_pension_var = MagicMock(get=lambda: True)
        app.fire_timeline_lbl = MagicMock()
        app.lbl_safe_gap_val = MagicMock()
        app.lbl_safe_gap_status = MagicMock()
        app.lbl_div_gap_val = MagicMock()
        app.lbl_div_gap_status = MagicMock()
        app.lbl_cap_gap_val = MagicMock()
        app.lbl_cap_gap_status = MagicMock()
        app.fire_burn_banner = MagicMock()
        app.lbl_fire_burn_badge = MagicMock()
        app.lbl_fire_rle_summary = MagicMock()
        app.card_cape_swr = MagicMock()
        app.lbl_cape_swr_val = MagicMock()
        app.lbl_cape_zone_badge = MagicMock()
        app.lbl_cape_swr_status = MagicMock()
        app.lbl_fire_checklist = MagicMock()
        app.dark_mode = False
        app.text_dark = "#202124"

        with patch("main_gui.save_settings"):
            main_gui.ModernPortfolioApp._refresh_fire_tab(app)
        self.assertTrue(hasattr(app, "_last_fire_res"))

    def test_export_fire_report_action(self):
        """Test _export_fire_report_action generates a markdown report and saves via filedialog."""
        import main_gui, tempfile
        from unittest.mock import MagicMock, patch

        app = object.__new__(main_gui.ModernPortfolioApp)
        app.root = MagicMock()
        app.summary_currency = "USD"
        app._last_fire_res = {
            "current_age": 45,
            "retire_age": 60,
            "life_expectancy": 90,
            "years_to_retire": 15,
            "retirement_duration_years": 30,
            "delay_pension_to_70": True,
            "burn_rate_pct": 2.8,
            "burn_zone_desc": "Safe",
            "bernstein_tip": "Stay the course.",
        }

        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tf:
            temp_out = tf.name

        try:
            with patch("main_gui.filedialog.asksaveasfilename", return_value=temp_out), \
                 patch("main_gui.messagebox.showinfo") as mock_info:
                main_gui.ModernPortfolioApp._export_fire_report_action(app)
                mock_info.assert_called_once()

            with open(temp_out, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("威廉·伯恩斯坦 退休自由與資產配置診斷報告", content)
            self.assertIn("目前年齡: 45 歲", content)
        finally:
            if os.path.exists(temp_out):
                os.remove(temp_out)

    def test_i18n_fire_tab_step_keys(self):
        """Test all step-by-step fire tab i18n keys across all supported languages."""
        from i18n import TRANSLATIONS
        step_keys = [
            "tab_fire", "fire_step1_title", "fire_step2_title", "fire_step3_title",
            "fire_step4_title", "fire_step5_title", "lbl_current_age", "lbl_retire_age",
            "lbl_life_expectancy", "lbl_delay_pension", "lbl_outside_safe_assets",
            "lbl_safe_asset_gap", "lbl_dividend_gap", "lbl_capital_gap",
            "btn_apply_to_rebalance", "btn_simulate_trade", "btn_export_fire_report",
            "lbl_holding_asset_class", "col_class_equity", "col_class_safe"
        ]
        for lang in ("en", "zh_TW", "zh_CN"):
            for k in step_keys:
                self.assertIn(k, TRANSLATIONS[lang], f"Missing key '{k}' in language '{lang}'")
    def test_weighted_average_cost_basis_merging(self):
        """Test weighted-average cost basis merging for multi-lot purchases (e.g. VGRO 21 @ $47.83 + 251 @ $47.90)."""
        from financial_calc import calc_holding_summary

        sh1, p1 = 21.0, 47.83
        sh2, p2 = 251.0, 47.90
        
        cost1 = round(sh1 * p1, 2) # 1004.43
        cost2 = round(sh2 * p2, 2) # 12022.90
        tot_shares = round(sh1 + sh2, 4) # 272.0
        tot_cost = round(cost1 + cost2, 2) # 13027.33
        weighted_avg_p = round((cost1 + cost2) / tot_shares, 4) # 47.8946

        self.assertEqual(tot_shares, 272.0)
        self.assertEqual(cost1, 1004.43)
        self.assertEqual(cost2, 12022.90)
        self.assertEqual(tot_cost, 13027.33)
        self.assertAlmostEqual(weighted_avg_p, 47.8946, places=4)
        self.assertNotEqual(round(weighted_avg_p, 2), 95.97, "Weighted average must not be $95.97!")

        # Verify holding summary at live price 47.85
        cur_price = 47.85
        summary = calc_holding_summary(tot_shares, weighted_avg_p, cur_price, div_yield=1.73, annual_div_per_share=0.828)
        self.assertEqual(summary["market_value"], 13015.20)
        self.assertAlmostEqual(summary["cost_basis"], 13027.33, delta=0.5)
        self.assertAlmostEqual(summary["unrealized_gain"], -12.13, delta=0.5)
        self.assertAlmostEqual(summary["unrealized_gain_pct"], -0.09, delta=0.1)

    def test_data_integrity_vgro_in_portfolio_csv(self):
        """Verify data integrity merger logic handles VGRO:TSE 21@47.83 and 251@47.90 correctly."""
        from csv_manager import save_portfolio, load_portfolio, repair_data_integrity
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            test_csv = os.path.join(tmpdir, "test_portfolio.csv")
            test_watch = os.path.join(tmpdir, "test_watchlist.csv")
            # Save 2 separate lots of VGRO:TSE
            save_portfolio([
                {"portfolio": "CAD CIBC Investment", "symbol": "VGRO:TSE", "name": "Vanguard Growth ETF", "shares": 21.0, "buy_price": 47.83, "current_price": 47.85, "currency": "CAD"},
                {"portfolio": "CAD CIBC Investment", "symbol": "VGRO:TSE", "name": "Vanguard Growth ETF", "shares": 251.0, "buy_price": 47.90, "current_price": 47.85, "currency": "CAD"},
            ], filepath=test_csv)

            # Run repair data integrity
            repair_data_integrity(portfolio_filepath=test_csv, watchlist_filepath=test_watch)

            # Load repaired portfolio
            holdings = load_portfolio(test_csv, portfolio_name="CAD CIBC Investment")
            self.assertEqual(len(holdings), 1)
            vgro = holdings[0]
            self.assertEqual(float(vgro["shares"]), 272.0)
            self.assertAlmostEqual(float(vgro["buy_price"]), 47.89, delta=0.05)
            self.assertLess(float(vgro["buy_price"]), 50.0) # Confirmed not $95.97
            self.assertAlmostEqual(float(vgro["cost_basis"]), 13027.33, delta=1.5)
    def test_suggested_etfs_and_rebalance_presets(self):
        """Test the 20+ suggested allocation ETFs, model presets, and rebalance calculations with non-held ETFs."""
        from financial_calc import SUGGESTED_ALLOCATION_ETFS, ALLOCATION_PRESETS, calc_portfolio_rebalance

        # 1. Verify 20+ suggested ETFs exist with all metadata
        self.assertGreaterEqual(len(SUGGESTED_ALLOCATION_ETFS), 20)
        symbols = [e["symbol"] for e in SUGGESTED_ALLOCATION_ETFS]
        for key_sym in ("VOO", "VTI", "QQQ", "SCHD", "VXUS", "VGRO:TSE", "XEQT:TSE", "ZAG:TSE", "BND", "TIP", "GLD"):
            self.assertIn(key_sym, symbols)

        for e in SUGGESTED_ALLOCATION_ETFS:
            self.assertTrue(len(e["symbol"]) > 0)
            self.assertTrue(len(e["name"]) > 0)
            self.assertTrue(len(e["asset_class"]) > 0)
            self.assertIn(e["currency"], ("USD", "CAD", "HKD"))
            self.assertGreater(float(e["typical_price"]), 0.0)

        # 2. Verify Allocation Presets sum to 100%
        self.assertGreaterEqual(len(ALLOCATION_PRESETS), 5)
        preset_ids = [p["id"] for p in ALLOCATION_PRESETS]
        self.assertIn("bogle_3fund", preset_ids)
        self.assertIn("bernstein_fire", preset_ids)
        self.assertIn("all_weather", preset_ids)
        for p in ALLOCATION_PRESETS:
            weights_sum = sum(p["weights"].values())
            self.assertAlmostEqual(weights_sum, 100.0, places=1, msg=f"Preset {p['id']} does not sum to 100%")

        # 3. Test rebalance with a newly added non-held ETF (e.g. BND with 0 shares)
        current_holdings = [
            {"symbol": "VOO", "name": "Vanguard S&P 500", "shares": 20.0, "current_price": 500.0, "currency": "USD"},
            {"symbol": "NVDA", "name": "NVIDIA", "shares": 100.0, "current_price": 120.0, "currency": "USD"},
        ] # Total current = 10,000 + 12,000 = 22,000.
        # Add new non-held BND: target 20%, VOO 40%, NVDA 40%. Cash added = $8,000. Total target = $30,000.
        target_weights = {"VOO": 40.0, "NVDA": 40.0, "BND": 20.0}
        
        # In Full Rebalance mode:
        reb_full = calc_portfolio_rebalance(
            holdings=current_holdings + [{"symbol": "BND", "name": "Vanguard Total Bond", "shares": 0.0, "current_price": 75.0, "currency": "USD"}],
            target_weights=target_weights,
            new_cash=8000.0,
            mode="full"
        )
        self.assertEqual(reb_full["total_target_value"], 30000.0)
        bnd_order = next((o for o in reb_full["orders"] if o["symbol"] == "BND"), None)
        self.assertIsNotNone(bnd_order)
        self.assertEqual(bnd_order["action"], "BUY")
        self.assertEqual(bnd_order["target_value"], 6000.0) # 20% of 30,000
        self.assertEqual(bnd_order["shares_diff"], 80) # 6000 / 75 = 80 shares
        self.assertEqual(bnd_order["amount_diff"], 6000.0)

        # In Cash-Only mode (Deposit rebalancing):
        reb_cash = calc_portfolio_rebalance(
            holdings=current_holdings + [{"symbol": "BND", "name": "Vanguard Total Bond", "shares": 0.0, "current_price": 75.0, "currency": "USD"}],
            target_weights=target_weights,
            new_cash=8000.0,
            mode="cash_only"
        )
        bnd_order_cash = next((o for o in reb_cash["orders"] if o["symbol"] == "BND"), None)
        self.assertIsNotNone(bnd_order_cash)
        self.assertEqual(bnd_order_cash["action"], "BUY")
        self.assertGreater(bnd_order_cash["shares_diff"], 0)

    def test_suggested_etf_i18n_keys(self):
        """Test all suggested ETF and preset i18n keys across all languages."""
        from i18n import TRANSLATIONS
        required_keys = [
            "lbl_suggested_etfs", "btn_add_to_plan", "lbl_preset_models",
            "btn_apply_preset", "btn_remove_from_plan", "lbl_custom_ticker",
            "summary_rebalance_bar", "msg_etf_already_in_plan"
        ]
        for lang in ("en", "zh_TW", "zh_CN"):
            for k in required_keys:
                self.assertIn(k, TRANSLATIONS[lang], f"Missing key '{k}' in language '{lang}'")

    def test_rebalance_exclude_zero_share_zero_target_items(self):
        """Verify calc_portfolio_rebalance does not output 0-share, 0-target, HOLD clutter."""
        from financial_calc import calc_portfolio_rebalance
        holdings = [
            {"symbol": "VGRO:TSE", "name": "Vanguard Growth", "shares": 272.0, "current_price": 47.90, "currency": "CAD"},
            {"symbol": "VXUS", "name": "Total Intl", "shares": 0.0, "current_price": 60.0, "currency": "USD"},
            {"symbol": "BND", "name": "Total Bond", "shares": 0.0, "current_price": 75.0, "currency": "USD"},
            {"symbol": "VTI", "name": "Total Stock", "shares": 0.0, "current_price": 260.0, "currency": "USD"},
        ]
        # User switched template to only target VGRO and VTI (VXUS and BND targets are 0)
        target_weights = {
            "VGRO:TSE": 50.0,
            "VTI": 50.0,
            "VXUS": 0.0,
            "BND": 0.0,
        }
        res = calc_portfolio_rebalance(holdings, target_weights, new_cash=1000.0, mode="cash_only")
        order_symbols = [o["symbol"] for o in res["orders"]]
        self.assertIn("VGRO:TSE", order_symbols)
        self.assertIn("VTI", order_symbols)
        # 0-share, 0-target HOLD items must NOT appear in orders/items
        self.assertNotIn("VXUS", order_symbols)
        self.assertNotIn("BND", order_symbols)

    def test_status_bar_pack_order(self):
        """Verify _build_status_bar is called before _build_tabs in main_gui.py to avoid bottom clipping."""
        import inspect
        import main_gui
        source = inspect.getsource(main_gui.ModernPortfolioApp.__init__)
        status_bar_pos = source.find("self._build_status_bar()")
        tabs_pos = source.find("self._build_tabs()")
        self.assertGreater(status_bar_pos, 0, "_build_status_bar not found in __init__")
        self.assertGreater(tabs_pos, 0, "_build_tabs not found in __init__")
        self.assertLess(status_bar_pos, tabs_pos, "self._build_status_bar() must be called before self._build_tabs()")


class TestWatchlistQuotesRefresh(unittest.TestCase):
    """Test suite for watchlist quote caching, persistence, and refresh symbol union."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.json_path = os.path.join(self.test_dir, "test_watchlist_quotes.json")

    def tearDown(self):
        if os.path.exists(self.json_path):
            os.remove(self.json_path)
        if os.path.exists(self.test_dir):
            os.rmdir(self.test_dir)

    def test_save_and_load_watchlist_quotes_cache(self):
        from csv_manager import save_watchlist_quotes_cache, load_watchlist_quotes_cache
        sample_cache = {
            "AAPL": {"symbol": "AAPL", "price": 182.5, "change_pct": "+1.25%", "currency": "USD"},
            "0005": {"symbol": "0005", "price": 68.2, "change_pct": "-0.50%", "currency": "HKD"},
        }
        # Save
        self.assertTrue(save_watchlist_quotes_cache(sample_cache, filepath=self.json_path))
        self.assertTrue(os.path.exists(self.json_path))

        # Load
        loaded = load_watchlist_quotes_cache(filepath=self.json_path)
        self.assertEqual(len(loaded), 2)
        self.assertIn("AAPL", loaded)
        self.assertIn("0005", loaded)
        self.assertEqual(loaded["AAPL"]["price"], 182.5)
        self.assertEqual(loaded["0005"]["currency"], "HKD")

    def test_load_cache_nonexistent_and_invalid(self):
        from csv_manager import load_watchlist_quotes_cache
        # Non-existent
        res = load_watchlist_quotes_cache(filepath=os.path.join(self.test_dir, "nonexistent.json"))
        self.assertEqual(res, {})

        # Corrupt file
        bad_path = os.path.join(self.test_dir, "bad.json")
        with open(bad_path, "w") as f:
            f.write("{invalid json content")
        res_bad = load_watchlist_quotes_cache(filepath=bad_path)
        self.assertEqual(res_bad, {})
        os.remove(bad_path)

    def test_symbols_union_includes_holdings_and_watchlist(self):
        """Verify symbols union merges holdings and watchlist symbols correctly."""
        holdings = [
            {"symbol": "AMD"},
            {"symbol": "GOOGL"},
            {"symbol": "CRWV"},
        ]
        watchlist = [
            {"symbol": "AAPL"},
            {"symbol": "0005"},
            {"symbol": "AMD"},  # overlap
        ]
        hold_symbols = {h["symbol"].strip().upper() for h in holdings if h.get("symbol")}
        watch_symbols = {w.get("symbol", "").strip().upper() for w in watchlist if w.get("symbol")}
        merged = sorted(list(hold_symbols | watch_symbols))
        self.assertEqual(merged, ["0005", "AAPL", "AMD", "CRWV", "GOOGL"])

    def test_google_finance_parse_html_isolated_from_market_index_carousel(self):
        """Verify that _parse_html extracts the stock's actual price and change, ignoring market index carousels."""
        from google_finance_fetcher import GoogleFinanceFetcher
        from bs4 import BeautifulSoup

        mock_html = """
        <html>
        <head><title>Apple Inc (AAPL) Stock Price - Google Finance</title></head>
        <body>
            <!-- Market Overview Ribbon at top of page -->
            <div class="market-carousel">
                <span class="vY9t3b"><span class="ymyBi">-0.83%</span></span>
                <span class="xnruHf"><span class="ymyBi">-42.10</span></span>
            </div>

            <!-- Main Stock Hero Section -->
            <div class="ujg0He">
                <div class="zzDege">Apple Inc</div>
                <div class="N6SYTe"><span>$333.02</span></div>
                <div class="DAicsd">
                    <i class="google-material-icons">arrow_upward</i>
                    <span jsname="vY9t3b"><span class="ougHge">+1.10%</span></span>
                    <div><span class="wBomed">(<span jsname="xnruHf"><span>+3.62</span></span>) Today</span></div>
                </div>
            </div>
            <div class="jZZ2de">Closed: Sep 30, 4:00 PM GMT-4 · USD</div>
            <div class="KxsRFb"><div class="SwQK7">P/E ratio</div><div class="dO6ijd">38.18</div></div>
            <div class="KxsRFb"><div class="SwQK7">52-wk high</div><div class="dO6ijd">$345.34</div></div>
            <div class="KxsRFb"><div class="SwQK7">52-wk low</div><div class="dO6ijd">$243.42</div></div>
            <div class="KxsRFb"><div class="SwQK7">Dividend yield</div><div class="dO6ijd">0.32%</div></div>
        </body>
        </html>
        """
        fetcher = GoogleFinanceFetcher()
        soup = BeautifulSoup(mock_html, "html.parser")
        res = fetcher._parse_html(soup, "AAPL:NASDAQ", "https://google.com/finance/quote/AAPL:NASDAQ")

        self.assertTrue(res["success"])
        self.assertEqual(res["price"], 333.02)
        self.assertEqual(res["change"], 3.62)
        self.assertEqual(res["change_percent"], 1.10)
        self.assertNotEqual(res["change_percent"], -0.83)
        self.assertEqual(res["pe_ratio"], 38.18)
        self.assertEqual(res["52_week_high"], 345.34)
        self.assertEqual(res["52_week_low"], 243.42)
        self.assertEqual(res["dividend_yield"], 0.32)
        self.assertIn("last_updated", res)

    def test_watchlist_stats_panel_and_direct_buy(self):
        """Verify watchlist stats panel formatting and direct buy lookup."""
        import main_gui
        from unittest.mock import MagicMock, patch

        app = object.__new__(main_gui.ModernPortfolioApp)
        app.root = MagicMock()
        app.card_bg = "#ffffff"
        app.text_dark = "#202124"
        app.text_muted = "#5f6368"
        app.primary_color = "#1a73e8"
        app._watchlist_quotes_cache = {
            "AAPL": {
                "symbol": "AAPL:NASDAQ",
                "name": "Apple Inc",
                "price": 333.02,
                "change": 3.62,
                "change_percent": 1.10,
                "currency": "USD",
                "pe_ratio": 38.18,
                "52_week_high": 345.34,
                "52_week_low": 243.42,
                "market_cap": "4.86T",
                "volume": "41.60M",
                "annual_dividend_per_share": 1.08,
                "dividend_yield": 0.32,
                "last_updated": "2026-10-01 01:26:43",
            }
        }
        app.watch_stats_frame = MagicMock()
        app.lbl_watch_metrics_content = MagicMock()
        app.watchlist_tree = MagicMock()
        app.watchlist_tree.selection.return_value = ["item1"]
        app.watchlist_tree.item.return_value = (
            "AAPL", "Apple Inc", "Tech", "$333.02", "+1.10%", "$300.00", "+11.01%",
            "38.2", "$243.42 - $345.34", "0.32%", "監控中", "USD", "2026-10-01 01:26:43", "2026-09-29", "Core"
        )

        main_gui.ModernPortfolioApp._update_watchlist_stats_panel(app)
        app.lbl_watch_metrics_content.config.assert_called_once()
        formatted_call = app.lbl_watch_metrics_content.config.call_args[1]["text"]
        self.assertIn("AAPL", formatted_call)
        self.assertIn("333.02", formatted_call)
        self.assertIn("38.18", formatted_call)
        self.assertIn("2026-10-01 01:26:43", formatted_call)

        # Test direct buy
        with patch.object(app, "_open_add_dialog") as mock_open_add, \
             patch("main_gui.load_watchlist", return_value=[{"symbol": "AAPL", "target_buy_price": 300.0, "currency": "USD"}]):
            main_gui.ModernPortfolioApp._buy_from_watchlist_into_portfolio(app)
            mock_open_add.assert_called_once_with(initial_symbol="AAPL", initial_name="Apple Inc", initial_price=333.02, initial_currency="USD")


class TestBernsteinPhase1Upgrades(unittest.TestCase):
    """Test suite for Phase 1 Bernstein retirement upgrades: bond ladder, pension actuary, and two-tier expenses."""

    def test_calc_bond_ladder_schedule(self):
        from financial_calc import calc_bond_ladder_schedule
        # $30,000 annual RLE, 25 years, start age 60, $150,000 safe assets
        ladder = calc_bond_ladder_schedule(
            rle_annual=30000.0,
            safe_years=25.0,
            start_age=60,
            current_safe_assets=150000.0,
            annual_inflation=0.025,
        )
        schedule = ladder["schedule"]
        self.assertEqual(len(schedule), 25)
        self.assertEqual(ladder["years"], 25)
        self.assertEqual(ladder["start_age"], 60)
        self.assertEqual(ladder["end_age"], 84)
        self.assertEqual(ladder["total_real_needed"], 750000.0)

        # $150k covers 5 full years @ $30k/yr
        self.assertEqual(ladder["fully_funded_years"], 5)
        self.assertEqual(ladder["fractional_years"], 5.0)
        self.assertEqual(ladder["coverage_pct"], 20.0)
        self.assertEqual(ladder["overall_gap"], 600000.0)

        # Year 1 (Age 60)
        yr1 = schedule[0]
        self.assertEqual(yr1["year_index"], 1)
        self.assertEqual(yr1["age"], 60)
        self.assertEqual(yr1["real_liability"], 30000.0)
        self.assertEqual(yr1["nominal_liability"], 30000.0)
        self.assertEqual(yr1["status"], "fully_funded")
        self.assertEqual(yr1["bucket_key"], "cash_short_treasury")
        self.assertIn("VGSH", yr1["recommended_ticker"])

        # Year 5 (Age 64) - last fully funded
        yr5 = schedule[4]
        self.assertEqual(yr5["status"], "fully_funded")
        self.assertEqual(yr5["bucket_key"], "short_tips")
        self.assertIn("VTIP", yr5["recommended_ticker"])

        # Year 6 (Age 65) - unfunded
        yr6 = schedule[5]
        self.assertEqual(yr6["status"], "unfunded")
        self.assertEqual(yr6["gap_amount"], 30000.0)

        # Year 15 (Age 74) - intermediate TIPS bucket
        yr15 = schedule[14]
        self.assertEqual(yr15["bucket_key"], "inter_tips")
        self.assertIn("TIP", yr15["recommended_ticker"])
        self.assertGreater(yr15["nominal_liability"], yr15["real_liability"])

    def test_calc_pension_actuarial_comparison(self):
        from financial_calc import calc_pension_actuarial_comparison
        # Base annual pension of $20,000 at age 65
        p_act = calc_pension_actuarial_comparison(
            base_annual_pension_at_65=20000.0,
            current_age=50,
            life_expectancy=90,
        )
        self.assertEqual(p_act["base_annual_at_65"], 20000.0)
        self.assertEqual(p_act["claim_60"]["annual"], 12800.0)  # 20000 * 0.64
        self.assertEqual(p_act["claim_65"]["annual"], 20000.0)  # 20000 * 1.00
        self.assertEqual(p_act["claim_70"]["annual"], 25600.0)  # 20000 * 1.28

        # Break-even age checks
        be_70_65 = p_act["breakeven_age_70_vs_65"]
        be_65_60 = p_act["breakeven_age_65_vs_60"]
        self.assertTrue(80 <= be_70_65 <= 88, f"Unexpected break-even age 70 vs 65: {be_70_65}")
        self.assertTrue(72 <= be_65_60 <= 76, f"Unexpected break-even age 65 vs 60: {be_65_60}")

        # Longevity gain at age 90 should be positive
        self.assertGreater(p_act["gain_at_life_exp_vs_65"], 0)
        self.assertGreater(p_act["gain_at_life_exp_vs_60"], 0)

        # Milestone payouts exist
        self.assertIn(85, p_act["milestones"])
        self.assertIn(90, p_act["milestones"])

    def test_calc_fire_metrics_two_tier_expenses(self):
        from financial_calc import calc_fire_metrics
        # Explicit essential and discretionary expenses
        res = calc_fire_metrics(
            current_annual_div=12000.0,
            target_monthly_expense=4000.0,
            essential_monthly_expense=2500.0,
            discretionary_monthly_expense=1500.0,
            current_portfolio_val=500000.0,
            guaranteed_annual_pension=18000.0,
            current_safe_assets=150000.0,
            target_safe_years=25.0,
        )
        self.assertEqual(res["target_monthly_expense"], 4000.0)
        self.assertEqual(res["essential_monthly_expense"], 2500.0)
        self.assertEqual(res["discretionary_monthly_expense"], 1500.0)
        self.assertEqual(res["essential_annual_expense"], 30000.0)
        self.assertEqual(res["discretionary_annual_expense"], 18000.0)

        # Essential floor coverage: Pension ($18k) + Safe Annuity ($150k/25 = $6k) = $24k / $30k = 80%
        self.assertEqual(res["essential_floor_coverage_pct"], 80.0)
        self.assertFalse(res["essential_floor_is_safe"])

        # Discretionary coverage: Dividends ($12k) / $18k = 66.7%
        self.assertEqual(res["discretionary_buffer_pct"], 66.7)

        # Precomputed ladder and pension actuary exist in return dict
        self.assertIn("ladder_data", res)
        self.assertIn("pension_actuary_data", res)
        self.assertEqual(len(res["ladder_data"]["schedule"]), 25)

        # Default 70/30 split when not explicitly passed
        res_default = calc_fire_metrics(
            current_annual_div=10000.0,
            target_monthly_expense=5000.0,
        )
        self.assertEqual(res_default["essential_monthly_expense"], 3500.0)
        self.assertEqual(res_default["discretionary_monthly_expense"], 1500.0)


class TestBernsteinPhase2Upgrades(unittest.TestCase):
    """
    Unit tests for William J. Bernstein Phase 2 Risk Defense Retirement Frameworks:
    1. Bernstein's 4 Deep Risks Audit & Resilience Diagnostic (Severe Inflation, Deflation, Confiscation, Devastation).
    2. Historical Crisis Sequence-of-Returns Stress Simulator (1929, 1973, 2000, 2008).
    3. Shiller CAPE-Adjusted Dynamic Safe Withdrawal Rate (SWR) Corridor (2.0% - 3.8%).
    """

    def test_calc_deep_risk_diagnostic(self):
        from financial_calc import calc_deep_risk_diagnostic

        # 1. Fortified portfolio: US Equities + International + TIPS + Cash
        holdings_fortified = [
            {"symbol": "VOO", "name": "Vanguard S&P 500", "shares": 100, "current_price": 500.0, "currency": "USD"},
            {"symbol": "VXUS", "name": "Vanguard Total International", "shares": 500, "current_price": 60.0, "currency": "USD"},
            {"symbol": "TIP", "name": "iShares TIPS Bond", "shares": 200, "current_price": 105.0, "currency": "USD"},
            {"symbol": "VGSH", "name": "Vanguard Short-Term Treasury", "shares": 300, "current_price": 58.0, "currency": "USD"},
        ]
        diag_a = calc_deep_risk_diagnostic(
            holdings=holdings_fortified,
            safe_assets_val=38400.0,
            total_portfolio_val=118400.0,
        )
        self.assertIn(diag_a["overall_grade"], ["A", "B"])
        self.assertGreaterEqual(diag_a["overall_score"], 70.0)
        self.assertGreaterEqual(diag_a["inflation_score"], 70.0)
        self.assertGreaterEqual(diag_a["deflation_score"], 70.0)
        self.assertGreaterEqual(diag_a["confiscation_score"], 70.0)
        self.assertGreaterEqual(diag_a["devastation_score"], 70.0)
        self.assertTrue(len(diag_a["strengths"]) > 0)
        self.assertIn("William J. Bernstein", diag_a["bernstein_thesis"])

        # 2. Vulnerable portfolio: 100% Single Domestic Stock, 0 Safe Assets
        holdings_vulnerable = [
            {"symbol": "TSLA", "name": "Tesla Inc", "shares": 1000, "current_price": 200.0, "currency": "USD"},
        ]
        diag_b = calc_deep_risk_diagnostic(
            holdings=holdings_vulnerable,
            safe_assets_val=0.0,
            total_portfolio_val=200000.0,
        )
        self.assertIn(diag_b["overall_grade"], ["C", "D"])
        self.assertLess(diag_b["deflation_score"], 50.0)
        self.assertLess(diag_b["confiscation_score"], 50.0)
        self.assertTrue(len(diag_b["weaknesses"]) > 0)
        self.assertTrue(len(diag_b["recommendations"]) > 0)

    def test_calc_historical_crisis_stress_test(self):
        from financial_calc import calc_historical_crisis_stress_test

        res = calc_historical_crisis_stress_test(
            portfolio_val=1000000.0,
            rle_annual=40000.0,
            safe_assets_val=300000.0,
            safe_years=25.0,
        )

        self.assertEqual(res["portfolio_initial"], 1000000.0)
        self.assertEqual(res["rle_annual"], 40000.0)
        self.assertIn("1929", res["results_by_crisis"])
        self.assertIn("1973", res["results_by_crisis"])
        self.assertIn("2000", res["results_by_crisis"])
        self.assertIn("2008", res["results_by_crisis"])

        # Compare 1929 Great Crash
        c1929 = res["results_by_crisis"]["1929"]
        self.assertEqual(len(c1929["unhedged_history"]), 10)
        self.assertEqual(len(c1929["hedged_history"]), 10)
        # Hedging prevents equity liquidation at market bottom; terminal hedged should exceed unhedged
        self.assertGreater(c1929["terminal_hedged"], c1929["terminal_unhedged"])
        self.assertGreater(c1929["capital_preserved"], 0)

        # Average preserved capital across all 4 crises must be significantly positive
        self.assertGreater(res["avg_capital_preserved"], 0)
        self.assertIn("William J. Bernstein", res["bernstein_stress_thesis"])

    def test_calc_cape_dynamic_swr(self):
        from financial_calc import calc_cape_dynamic_swr

        # 1. Bubble Valuation: High CAPE = 34.0
        swr_bubble = calc_cape_dynamic_swr(current_cape=34.0, portfolio_val=1000000.0)
        self.assertEqual(swr_bubble["zone"], "extreme_bubble")
        self.assertAlmostEqual(swr_bubble["dynamic_swr_pct"], 2.27, places=1)
        self.assertEqual(swr_bubble["annual_withdrawal_cap"], 22700.0)
        self.assertEqual(swr_bubble["monthly_withdrawal_cap"], 1891.67)
        self.assertLess(swr_bubble["annual_withdrawal_delta"], 0)  # less than static 4% ($40k)

        # 2. Historical Fair Value: CAPE = 16.5
        swr_fair = calc_cape_dynamic_swr(current_cape=16.5, portfolio_val=1000000.0)
        self.assertEqual(swr_fair["zone"], "fair")
        self.assertEqual(swr_fair["dynamic_swr_pct"], 3.20)
        self.assertEqual(swr_fair["annual_withdrawal_cap"], 32000.0)

        # 3. Undervalued Bargain: Low CAPE = 10.0
        swr_cheap = calc_cape_dynamic_swr(current_cape=10.0, portfolio_val=1000000.0)
        self.assertEqual(swr_cheap["zone"], "bargain")
        self.assertAlmostEqual(swr_cheap["dynamic_swr_pct"], 3.55, places=1)
        self.assertGreater(swr_cheap["annual_withdrawal_cap"], 35000.0)

        # 4. Clamping bounds check:
        # Extreme bubble (CAPE 75) must clamp at minimum 2.0%
        swr_clamped_low = calc_cape_dynamic_swr(current_cape=75.0)
        self.assertEqual(swr_clamped_low["dynamic_swr_pct"], 2.0)

        # Extreme crash (CAPE 5) must clamp at maximum 3.8%
        swr_clamped_high = calc_cape_dynamic_swr(current_cape=5.0)
        self.assertEqual(swr_clamped_high["dynamic_swr_pct"], 3.8)

    def test_calc_fire_metrics_phase2_integration(self):
        from financial_calc import calc_fire_metrics

        res = calc_fire_metrics(
            current_annual_div=15000.0,
            target_monthly_expense=4000.0,
            current_portfolio_val=800000.0,
            current_safe_assets=250000.0,
            current_cape=28.0,
            holdings=[
                {"symbol": "VOO", "shares": 500, "current_price": 500.0, "currency": "USD"},
                {"symbol": "VXUS", "shares": 1000, "current_price": 60.0, "currency": "USD"},
                {"symbol": "TIP", "shares": 1000, "current_price": 105.0, "currency": "USD"},
            ],
        )

        self.assertIn("deep_risk_data", res)
        self.assertIn("crisis_stress_test_data", res)
        self.assertIn("cape_swr_data", res)

        # Check deep risk data populated
        self.assertIn("overall_score", res["deep_risk_data"])
        self.assertIn("inflation_score", res["deep_risk_data"])

        # Check crisis stress data populated
        self.assertIn("results_by_crisis", res["crisis_stress_test_data"])
        self.assertEqual(len(res["crisis_stress_test_data"]["results_by_crisis"]), 4)

        # Check CAPE SWR data populated with current_cape=28.0
        self.assertEqual(res["cape_swr_data"]["current_cape"], 28.0)
        self.assertEqual(res["cape_swr_data"]["zone"], "elevated")


class TestBernsteinPhase3Upgrades(unittest.TestCase):
    """
    Unit tests for William J. Bernstein Phase 3 Optimization & Friction Cost Frameworks:
    1. Item 18: 30-Year Investment Fee & Multi-Regional Tax Drag Autopsy (Canada, Non-Treaty, US).
    2. Item 14: 5/25 Rebalancing Tolerance Bands & Rebalancing Bonus (+0.50%/yr).
    3. Item 20: Cognitive Decline Protection & Portfolio Simplicity Index (Age >= 70 alerts, 2/3 fund blueprints).
    4. Integration with calc_fire_metrics and main_gui methods.
    """

    def test_fee_and_tax_drag_canada_accounts(self):
        from financial_calc import calc_fee_and_tax_drag_autopsy

        holdings = [
            {"symbol": "VOO", "name": "Vanguard S&P 500", "shares": 1000, "current_price": 500.0, "currency": "USD"},
            {"symbol": "ZAG", "name": "BMO Aggregate Bond", "shares": 5000, "current_price": 14.0, "currency": "CAD"},
        ]

        # 1. Canada Taxable account
        res_taxable = calc_fee_and_tax_drag_autopsy(
            holdings=holdings,
            portfolio_val=570000.0,
            annual_dividend=12000.0,
            region="Canada",
            account_type="Taxable",
            summary_currency="CAD",
        )
        self.assertAlmostEqual(res_taxable["us_dividend_wht_pct"], 13.2, places=1)
        self.assertAlmostEqual(res_taxable["capital_gains_tax_pct"], 19.0, places=1)
        self.assertGreater(res_taxable["thirty_year_total_loss"], 0.0)
        self.assertGreater(res_taxable["thirty_year_wht_loss"], 0.0)
        self.assertGreater(res_taxable["thirty_year_cgt_loss"], 0.0)
        self.assertGreater(res_taxable["thirty_year_fee_loss"], 0.0)
        self.assertEqual(len(res_taxable["trajectories"]), 30)

        # 2. Canada RRSP account (Article XXI exemption: 0% WHT, 0% CGT)
        res_rrsp = calc_fee_and_tax_drag_autopsy(
            holdings=holdings,
            portfolio_val=570000.0,
            annual_dividend=12000.0,
            region="Canada",
            account_type="RRSP",
            summary_currency="CAD",
        )
        self.assertEqual(res_rrsp["us_dividend_wht_pct"], 0.0)
        self.assertEqual(res_rrsp["capital_gains_tax_pct"], 0.0)
        self.assertEqual(res_rrsp["thirty_year_wht_loss"], 0.0)
        self.assertEqual(res_rrsp["thirty_year_cgt_loss"], 0.0)
        self.assertGreater(res_rrsp["thirty_year_fee_loss"], 0.0)
        self.assertLess(res_rrsp["thirty_year_total_loss"], res_taxable["thirty_year_total_loss"])

        # 3. Canada TFSA account (0% CGT, but 15% US Dividend WHT persists on US holdings)
        res_tfsa = calc_fee_and_tax_drag_autopsy(
            holdings=holdings,
            portfolio_val=570000.0,
            annual_dividend=12000.0,
            region="Canada",
            account_type="TFSA",
            summary_currency="CAD",
        )
        self.assertAlmostEqual(res_tfsa["us_dividend_wht_pct"], 13.2, places=1)
        self.assertEqual(res_tfsa["capital_gains_tax_pct"], 0.0)
        self.assertGreater(res_tfsa["thirty_year_wht_loss"], 0.0)
        self.assertEqual(res_tfsa["thirty_year_cgt_loss"], 0.0)

    def test_fee_and_tax_drag_non_treaty_and_us(self):
        from financial_calc import calc_fee_and_tax_drag_autopsy

        holdings = [
            {"symbol": "VOO", "name": "Vanguard S&P 500", "shares": 1000, "current_price": 500.0, "currency": "USD"},
        ]

        # 1. Non-Treaty (Taiwan, HK, Singapore): 30% WHT, 0% CGT
        res_non_treaty = calc_fee_and_tax_drag_autopsy(
            holdings=holdings,
            portfolio_val=500000.0,
            annual_dividend=10000.0,
            region="Non-Treaty",
            account_type="Taxable",
        )
        self.assertEqual(res_non_treaty["us_dividend_wht_pct"], 30.0)
        self.assertEqual(res_non_treaty["capital_gains_tax_pct"], 0.0)
        self.assertGreater(res_non_treaty["thirty_year_wht_loss"], 0.0)
        advice_txt = " ".join(res_non_treaty["asset_location_tips"])
        self.assertTrue("UCITS" in advice_txt or "愛爾蘭" in advice_txt or "Ireland" in advice_txt)

        # 2. US Resident: 0% WHT, 15% long-term CGT
        res_us = calc_fee_and_tax_drag_autopsy(
            holdings=holdings,
            portfolio_val=500000.0,
            annual_dividend=10000.0,
            region="US",
            account_type="Taxable",
        )
        self.assertEqual(res_us["us_dividend_wht_pct"], 0.0)
        self.assertEqual(res_us["capital_gains_tax_pct"], 15.0)

    def test_rebalancing_5_25_bands(self):
        from financial_calc import calc_rebalancing_5_25_bands

        holdings = [
            {"symbol": "VOO", "shares": 600, "current_price": 1000.0, "currency": "USD"},
            {"symbol": "BND", "shares": 300, "current_price": 1000.0, "currency": "USD"},
            {"symbol": "TIP", "shares": 100, "current_price": 1000.0, "currency": "USD"},
        ]
        target_weights = {"VOO": 50.0, "BND": 40.0, "TIP": 10.0}

        reb = calc_rebalancing_5_25_bands(
            holdings=holdings,
            portfolio_val=1000000.0,
            target_weights=target_weights,
        )

        self.assertEqual(reb["total_assets"], 3)
        self.assertGreaterEqual(reb["triggered_count"], 2)
        self.assertAlmostEqual(reb["rebalancing_bonus_pct"], 0.50, places=2)
        self.assertEqual(reb["estimated_annual_rebalance_bonus"], 5000.0)
        self.assertIn("William J. Bernstein", reb["bernstein_rebalance_thesis"])

        drifts_map = {d["symbol"]: d for d in reb["asset_drifts"]}
        self.assertEqual(drifts_map["VOO"]["status"], "triggered")
        self.assertEqual(drifts_map["VOO"]["action"], "trim")
        self.assertEqual(drifts_map["BND"]["status"], "triggered")
        self.assertEqual(drifts_map["BND"]["action"], "add")
        self.assertEqual(drifts_map["TIP"]["status"], "in_band")
        self.assertEqual(drifts_map["TIP"]["action"], "hold")

    def test_calc_simplicity_index(self):
        from financial_calc import calc_simplicity_index

        # 1. Simple 2-Fund indexed portfolio (Age 65)
        holdings_simple = [
            {"symbol": "VOO", "shares": 600, "current_price": 100.0, "currency": "USD"},
            {"symbol": "BND", "shares": 400, "current_price": 100.0, "currency": "USD"},
        ]
        simp_a = calc_simplicity_index(holdings_simple, current_age=65)
        self.assertGreaterEqual(simp_a["simplicity_score"], 85)
        self.assertEqual(simp_a["rating"], "A")
        self.assertFalse(simp_a["cognitive_alert"])
        self.assertEqual(simp_a["holding_count"], 2)

        # 2. Complex individual stock portfolio (Age 75 -> Cognitive Alert!)
        holdings_complex = [
            {"symbol": f"STK{i}", "shares": 10, "current_price": 50.0, "currency": "USD"}
            for i in range(20)
        ]
        simp_b = calc_simplicity_index(holdings_complex, current_age=75)
        self.assertLess(simp_b["simplicity_score"], 60)
        self.assertIn(simp_b["rating"], ["C", "D", "F"])
        self.assertTrue(simp_b["cognitive_alert"])
        self.assertTrue(len(simp_b["recommendations"]) > 0)
        self.assertIn("70", simp_b["cognitive_warning"])

    def test_calc_fire_metrics_phase3_integration(self):
        from financial_calc import calc_fire_metrics

        res = calc_fire_metrics(
            current_annual_div=20000.0,
            target_monthly_expense=5000.0,
            current_portfolio_val=1200000.0,
            current_safe_assets=300000.0,
            current_cape=25.0,
            current_age=72,
            holdings=[
                {"symbol": "VOO", "shares": 1000, "current_price": 500.0, "currency": "USD"},
                {"symbol": "BND", "shares": 5000, "current_price": 75.0, "currency": "USD"},
                {"symbol": "ZAG", "shares": 10000, "current_price": 14.0, "currency": "CAD"},
            ],
            tax_region="Canada",
            account_type="Taxable",
        )

        self.assertIn("fee_tax_data", res)
        self.assertIn("rebalance_5_25_data", res)
        self.assertIn("simplicity_data", res)

        # Verify fee_tax_data
        self.assertGreater(res["fee_tax_data"]["thirty_year_total_loss"], 0.0)
        self.assertAlmostEqual(res["fee_tax_data"]["us_dividend_wht_pct"], 10.9, places=1)

        # Verify rebalance_5_25_data
        self.assertIn("asset_drifts", res["rebalance_5_25_data"])
        self.assertEqual(res["rebalance_5_25_data"]["rebalancing_bonus_pct"], 0.50)

        # Verify simplicity_data with clean 3-Fund portfolio
        self.assertFalse(res["simplicity_data"]["cognitive_alert"])
        self.assertGreaterEqual(res["simplicity_data"]["simplicity_score"], 80)
        self.assertEqual(res["simplicity_data"]["rating"], "B")

    def test_gui_dialog_methods_exist(self):
        from main_gui import ModernPortfolioApp

        self.assertTrue(hasattr(ModernPortfolioApp, "_show_fee_tax_drag_dialog"))
        self.assertTrue(hasattr(ModernPortfolioApp, "_show_rebalancing_5_25_dialog"))
        self.assertTrue(hasattr(ModernPortfolioApp, "_show_simplicity_index_dialog"))
        self.assertTrue(hasattr(ModernPortfolioApp, "_show_preset_blueprint_dialog"))
        self.assertTrue(hasattr(ModernPortfolioApp, "_open_rebalance_dialog"))

    def test_rebalance_dialog_preset_imports_and_naming(self):
        """Verify allocation preset names and broker preset names do not collide or throw TypeError."""
        import main_gui
        from financial_calc import ALLOCATION_PRESETS
        from fee_manager import BROKER_PRESETS

        # 1. Allocation presets require (dict, lang)
        for p in ALLOCATION_PRESETS:
            dname_en = main_gui.get_allocation_preset_display_name(p, "en")
            dname_tw = main_gui.get_allocation_preset_display_name(p, "zh_TW")
            self.assertTrue(len(dname_en) > 0)
            self.assertTrue(len(dname_tw) > 0)

        # 2. Broker presets require (str)
        for k in BROKER_PRESETS:
            bname = main_gui.get_broker_preset_display_name(k)
            self.assertTrue(len(bname) > 0)

    def test_fee_tax_trajectory_keys_and_canvas_chart(self):
        from financial_calc import calc_fee_and_tax_drag_autopsy
        from chart_canvas import draw_fee_tax_trajectory_chart
        from unittest.mock import MagicMock

        res = calc_fee_and_tax_drag_autopsy(
            portfolio_val=1000000.0,
            region="Canada",
            account_type="Taxable",
        )
        traj = res.get("trajectories", [])
        self.assertEqual(len(traj), 30)

        # Ensure all required keys exist in every trajectory row
        for row in traj:
            self.assertIn("year", row)
            self.assertIn("gross_wealth", row)
            self.assertIn("benchmark_wealth", row)
            self.assertIn("portfolio_wealth", row)
            self.assertIn("total_drag", row)
            self.assertIn("drag_pct", row)
            self.assertIn("dollars_lost", row)
            self.assertIn("pct_wealth_lost", row)
            self.assertEqual(row["total_drag"], row["dollars_lost"])
            self.assertEqual(row["drag_pct"], row["pct_wealth_lost"])

        # Test native canvas trajectory rendering in both light and dark mode
        mock_canvas = MagicMock()
        mock_canvas.winfo_width.return_value = 750
        mock_canvas.winfo_height.return_value = 220
        draw_fee_tax_trajectory_chart(mock_canvas, traj, dark_mode=False)
        self.assertTrue(mock_canvas.create_line.called)
        self.assertTrue(mock_canvas.create_polygon.called)

        mock_canvas_dark = MagicMock()
        mock_canvas_dark.winfo_width.return_value = 750
        mock_canvas_dark.winfo_height.return_value = 220
        draw_fee_tax_trajectory_chart(mock_canvas_dark, traj, dark_mode=True)
        self.assertTrue(mock_canvas_dark.create_line.called)

    def test_fire_user_parameters_persistence_and_no_hardcoded_overrides(self):
        from financial_calc import calc_fire_metrics
        from i18n import load_settings, save_settings

        # 1. Verify calc_fire_metrics returns current_portfolio_val and custom age
        res = calc_fire_metrics(
            current_annual_div=3000.0,
            target_monthly_expense=4000.0,
            current_portfolio_val=250000.0,
            current_age=58,
            retire_age=65,
            life_expectancy=95,
        )
        self.assertEqual(res["current_age"], 58)
        self.assertEqual(res["retire_age"], 65)
        self.assertEqual(res["life_expectancy"], 95)
        self.assertEqual(res["current_portfolio_val"], 250000.0)
        self.assertEqual(res["total_effective_wealth"], 250000.0)

        # 2. Verify fire_params persistence to settings.json
        orig_settings = load_settings()
        try:
            test_params = {
                "current_age": "58",
                "retire_age": "65",
                "life_expectancy": "95",
                "target_safe_years": "25",
                "target_monthly_expense": "4200.0",
                "outside_safe_assets": "120000.0",
            }
            save_settings({"fire_params": test_params})
            loaded = load_settings().get("fire_params", {})
            self.assertEqual(loaded.get("current_age"), "58")
            self.assertEqual(loaded.get("retire_age"), "65")
            self.assertEqual(loaded.get("target_monthly_expense"), "4200.0")
            self.assertEqual(loaded.get("outside_safe_assets"), "120000.0")
        finally:
            save_settings(orig_settings)


if __name__ == "__main__":
    unittest.main()





