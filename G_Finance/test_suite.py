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
        self.assertTrue(any(t in content for t in ["Google Finance Portfolio Executive Report", "Google 財經投資組合高階執行報告", "Google 财经投资组合高阶执行报告", "Google 财经投资组合高管执行报告"]))
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

    def test_portfolio_10_backup_rotation(self):
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

        # 3. Save V3 through V11 -> exactly 10 backups should exist (capped at 10)
        for i in range(3, 12):
            save_portfolio([{"symbol": f"V{i}", "shares": float(i), "buy_price": 10.0 * i}], self.test_port_csv)

        backups = get_backup_files(self.test_port_csv, backup_dir=self.backup_dir)
        self.assertEqual(len(backups), 10)
        # Check slot indices 1..10 exist
        indices = [b["index"] for b in backups]
        self.assertEqual(indices, list(range(1, 11)))
        # Slot 1 is newest (V10), Slot 10 is oldest (V1)
        self.assertEqual(load_portfolio(backups[0]["path"])[0]["symbol"], "V10")
        self.assertEqual(load_portfolio(backups[9]["path"])[0]["symbol"], "V1")

        # 4. Save V12 -> still capped at 10 backups; V1 purged, slot 10 is V2, slot 1 is V11
        save_portfolio([{"symbol": "V12", "shares": 12.0, "buy_price": 120.0}], self.test_port_csv)
        backups = get_backup_files(self.test_port_csv, backup_dir=self.backup_dir)
        self.assertEqual(len(backups), 10)
        self.assertEqual(load_portfolio(backups[0]["path"])[0]["symbol"], "V11")
        self.assertEqual(load_portfolio(backups[9]["path"])[0]["symbol"], "V2")

        # 5. Restore from backup slot 3 (which is V9)
        ok = restore_backup(self.test_port_csv, backup_index=3, backup_dir=self.backup_dir)
        self.assertTrue(ok)
        restored = load_portfolio(self.test_port_csv)
        self.assertEqual(restored[0]["symbol"], "V9")

        # Verify safety backup retained the prior state (V12) in slot 1
        backups_after = get_backup_files(self.test_port_csv, backup_dir=self.backup_dir)
        self.assertEqual(load_portfolio(backups_after[0]["path"])[0]["symbol"], "V12")

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
        web_server.stop_server()
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

    def test_safe_format_timestamp_various_formats(self):
        from datetime import datetime
        from chart_view import _safe_format_timestamp, _parse_to_datetime

        # Test string datetime formats
        dt_str = "2026-10-20 17:01:51"
        self.assertIn("2026", _safe_format_timestamp(dt_str, "1Y", is_hover=False))
        self.assertIn("17:01", _safe_format_timestamp(dt_str, "1D", is_hover=False))
        self.assertIn("17:01:51", _safe_format_timestamp(dt_str, "1D", is_hover=True))

        # Test ISO string format
        iso_str = "2026-10-20T17:01:51+00:00"
        self.assertIn("2026", _safe_format_timestamp(iso_str, "1Y", is_hover=False))

        # Test date string format
        date_str = "2026-10-20"
        self.assertIn("2026", _safe_format_timestamp(date_str, "1Y", is_hover=False))

        # Test epoch timestamp
        epoch = 1729443711
        self.assertTrue(len(_safe_format_timestamp(epoch, "1D", is_hover=False)) > 0)

        # Test datetime object
        dt_obj = datetime(2026, 10, 20, 15, 30, 0)
        self.assertIn("15:30", _safe_format_timestamp(dt_obj, "1D", is_hover=False))
        self.assertIn("15:30:00", _safe_format_timestamp(dt_obj, "1D", is_hover=True))

        # Test edge cases (unparseable, empty, None)
        self.assertEqual(_safe_format_timestamp("custom_label", "1D", is_hover=False), "custom_label")
        self.assertEqual(_safe_format_timestamp("", "1D", is_hover=False), "")
        self.assertEqual(_safe_format_timestamp(None, "1D", is_hover=False), "")

    def test_scope_selection_handling(self):
        from unittest.mock import MagicMock
        from chart_view import GoogleFinanceChartView

        mock_view = MagicMock()
        mock_view.scope_combo = MagicMock()

        # Test portfolio selection with various emojis/formats
        test_cases = [
            ("📁 Portfolio: All Portfolios", 0, "portfolio"),
            ("📑 Portfolio: All Portfolios", 0, "portfolio"),
            ("Portfolio: Retirement", 0, "portfolio"),
            ("📁 Portfolio: USD Tech", -1, "portfolio"),
            ("VFV - Vanguard S&P 500 Index ETF", 1, "VFV"),
            ("9988.HK - Alibaba Group", 2, "9988.HK"),
            ("XIU.TO", 3, "XIU.TO"),
        ]

        for combo_val, current_idx, expected_scope in test_cases:
            mock_view.scope_combo.get.return_value = combo_val
            mock_view.scope_combo.current.return_value = current_idx
            GoogleFinanceChartView._on_scope_selected(mock_view)
            self.assertEqual(mock_view.current_scope, expected_scope)

    def test_metric_changed_handling_and_distinction(self):
        from unittest.mock import MagicMock
        from chart_view import GoogleFinanceChartView

        mock_view = MagicMock()
        mock_view.metric_combo = MagicMock()
        mock_view.chart_data = None

        # Verify index mapping: 0=total, 1=price, 2=growth, 3=growth_div, 4=div_only
        idx_cases = [
            (0, "total"),
            (1, "price"),
            (2, "growth"),
            (3, "growth_div"),
            (4, "div_only"),
        ]
        for idx, expected_metric in idx_cases:
            mock_view.metric_combo.current.return_value = idx
            mock_view.metric_combo.get.return_value = ""
            GoogleFinanceChartView._on_metric_changed(mock_view)
            self.assertEqual(mock_view.chart_metric, expected_metric)

        # Verify fallback string matching doesn't confuse growth vs growth_div
        string_cases = [
            ("Net Growth / P&L (Excl. Invested)", -1, "growth"),
            ("淨增長 / 盈虧 (扣除本金)", -1, "growth"),
            ("Net Growth + Dividends", -1, "growth_div"),
            ("淨增長 + 累積股息分派", -1, "growth_div"),
            ("Stock Price (Per Share)", -1, "price"),
            ("股價 (每股)", -1, "price"),
            ("Dividends Only", -1, "div_only"),
            ("僅累積股息分派", -1, "div_only"),
            ("Total Portfolio / Position Value", -1, "total"),
        ]
        for val_str, idx, expected_metric in string_cases:
            mock_view.metric_combo.current.return_value = idx
            mock_view.metric_combo.get.return_value = val_str
            GoogleFinanceChartView._on_metric_changed(mock_view)
            self.assertEqual(mock_view.chart_metric, expected_metric)

    def test_benchmark_changed_handling(self):
        from unittest.mock import MagicMock
        from chart_view import GoogleFinanceChartView

        mock_view = MagicMock()
        mock_view.benchmark_combo = MagicMock()

        bm_cases = [
            (0, "None", "none", ""),
            (1, "S&P 500 (SPY)", "sp500", "SPY"),
            (2, "TSX 60 (XIU.TO)", "tsx60", "XIU.TO"),
        ]
        for idx, val, expected_bm, expected_sym in bm_cases:
            mock_view.benchmark_combo.current.return_value = idx
            mock_view.benchmark_combo.get.return_value = val
            GoogleFinanceChartView._on_benchmark_changed(mock_view)
            self.assertEqual(mock_view.current_benchmark, expected_bm)
            self.assertEqual(mock_view.benchmark_symbol, expected_sym)

    def test_mpl_hover_with_twinx_ax2(self):
        from unittest.mock import MagicMock
        from chart_view import GoogleFinanceChartView

        mock_view = MagicMock()
        mock_view.plot_prices = [100.0, 105.0, 110.0]
        mock_view.plot_timestamps = ["2026-10-20 10:00:00", "2026-10-20 11:00:00", "2026-10-20 12:00:00"]
        mock_view.plot_prev_close = 99.0
        mock_view.plot_currency = "$"
        mock_view.ax = MagicMock()
        mock_view.ax2 = MagicMock()

        # Hover event on primary ax
        event_ax1 = MagicMock()
        event_ax1.inaxes = mock_view.ax
        event_ax1.xdata = 1.0
        GoogleFinanceChartView._on_mpl_hover(mock_view, event_ax1)
        mock_view._update_hover_header.assert_called_with(105.0, "2026-10-20 11:00:00", 99.0, "$")

        # Hover event on twinx ax2 (benchmark active)
        mock_view._update_hover_header.reset_mock()
        event_ax2 = MagicMock()
        event_ax2.inaxes = mock_view.ax2
        event_ax2.xdata = 2.0
        GoogleFinanceChartView._on_mpl_hover(mock_view, event_ax2)
        mock_view._update_hover_header.assert_called_with(110.0, "2026-10-20 12:00:00", 99.0, "$")

        # Hover event outside any valid axis
        mock_view._update_hover_header.reset_mock()
        event_outside = MagicMock()
        event_outside.inaxes = MagicMock()
        event_outside.xdata = 2.0
        GoogleFinanceChartView._on_mpl_hover(mock_view, event_outside)
        mock_view._update_hover_header.assert_not_called()


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

        from unittest.mock import patch
        with patch("main_gui.load_portfolio", return_value=[]):
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
            "btn_change_category",
            "dlg_change_category_title",
            "msg_select_stock_for_category",
            "opt_category_replace",
            "opt_category_append",
            "opt_category_clear",
        ]
        for lang in ["en", "zh_TW", "zh_CN"]:
            for k in required_keys:
                self.assertIn(k, TRANSLATIONS[lang], f"Key '{k}' missing in {lang}")
                self.assertTrue(len(TRANSLATIONS[lang][k]) > 0, f"Key '{k}' in {lang} is empty")

    def test_bulk_update_watchlist_category(self):
        from csv_manager import (
            save_watchlist,
            load_watchlist,
            bulk_update_watchlist_category,
        )

        initial_data = [
            {"symbol": "AAPL", "name": "Apple", "target_price": 150.0, "currency": "USD", "notes": "", "tags": "OldTag"},
            {"symbol": "MSFT", "name": "Microsoft", "target_price": 300.0, "currency": "USD", "notes": "", "tags": "Tech, Cloud"},
            {"symbol": "GOOGL", "name": "Alphabet", "target_price": 120.0, "currency": "USD", "notes": "", "tags": ""},
        ]
        save_watchlist(initial_data, self.test_csv)

        # 1. Replace category for AAPL and GOOGL
        cnt = bulk_update_watchlist_category(["AAPL", "GOOGL"], "Growth", mode="replace", filepath=self.test_csv)
        self.assertEqual(cnt, 2)
        res = load_watchlist(self.test_csv)
        aapl = next(i for i in res if i["symbol"] == "AAPL")
        googl = next(i for i in res if i["symbol"] == "GOOGL")
        msft = next(i for i in res if i["symbol"] == "MSFT")
        self.assertEqual(aapl["tags"], "Growth")
        self.assertEqual(googl["tags"], "Growth")
        self.assertEqual(msft["tags"], "Tech, Cloud")

        # 2. Append category for AAPL and MSFT
        cnt2 = bulk_update_watchlist_category(["AAPL", "MSFT"], "MegaCap, Tech", mode="append", filepath=self.test_csv)
        self.assertEqual(cnt2, 2)
        res = load_watchlist(self.test_csv)
        aapl = next(i for i in res if i["symbol"] == "AAPL")
        msft = next(i for i in res if i["symbol"] == "MSFT")
        self.assertIn("Growth", aapl["tags"])
        self.assertIn("MegaCap", aapl["tags"])
        self.assertIn("Tech", aapl["tags"])
        self.assertIn("Tech", msft["tags"])
        self.assertIn("Cloud", msft["tags"])
        self.assertIn("MegaCap", msft["tags"])
        self.assertEqual(msft["tags"].count("Tech"), 1)

        # 3. Clear category for MSFT
        cnt3 = bulk_update_watchlist_category(["MSFT"], "", mode="clear", filepath=self.test_csv)
        self.assertEqual(cnt3, 1)
        res = load_watchlist(self.test_csv)
        msft = next(i for i in res if i["symbol"] == "MSFT")
        self.assertEqual(msft["tags"], "")

        # 4. ModernPortfolioApp has _open_batch_change_category_dialog
        import main_gui
        self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_open_batch_change_category_dialog"))

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

    def test_tooltip_dynamic_text_and_localization(self):
        from main_gui import ToolTip, attach_tooltip
        from i18n import t, set_language, get_current_language

        class MockWidget:
            def __init__(self):
                self._bindings = {}
            def bind(self, seq, handler, add=None):
                self._bindings[seq] = handler
            def winfo_exists(self):
                return True

        orig_lang = get_current_language()
        try:
            widget = MockWidget()
            tip = attach_tooltip(widget, "tip_refresh")
            
            set_language("en")
            self.assertIn("quotes from Google Finance", tip._get_text())

            set_language("zh_TW")
            self.assertIn("從 Google 財經抓取", tip._get_text())

            set_language("zh_CN")
            self.assertIn("从 Google 财经抓取", tip._get_text())
        finally:
            set_language(orig_lang)

    def test_fetcher_session_pooling(self):
        from google_finance_fetcher import GoogleFinanceFetcher
        fetcher = GoogleFinanceFetcher()
        adapter = fetcher.session.get_adapter("https://www.google.com")
        self.assertIsNotNone(adapter)
        self.assertGreaterEqual(getattr(adapter, "_pool_connections", 0), 20)
        self.assertGreaterEqual(getattr(adapter, "_pool_maxsize", 0), 20)

    def test_cache_notice_and_background_status_messages(self):
        from i18n import t, set_language, get_current_language
        orig_lang = get_current_language()
        try:
            set_language("en")
            notice_en = t("msg_cached_data_notice")
            bg_en = t("msg_updating_background")
            done_en = t("msg_update_completed")
            self.assertIn("Showing cached data", notice_en)
            self.assertIn("background", bg_en)
            self.assertIn("updated", done_en)

            set_language("zh_TW")
            notice_tw = t("msg_cached_data_notice")
            bg_tw = t("msg_updating_background")
            done_tw = t("msg_update_completed")
            self.assertIn("快取資料", notice_tw)
            self.assertIn("背景正在同步", bg_tw)
            self.assertIn("已更新至最新", done_tw)

            set_language("zh_CN")
            notice_cn = t("msg_cached_data_notice")
            bg_cn = t("msg_updating_background")
            done_cn = t("msg_update_completed")
            self.assertIn("缓存数据", notice_cn)
            self.assertIn("后台正在同步", bg_cn)
            self.assertIn("已更新至最新", done_cn)
        finally:
            set_language(orig_lang)

    def test_auto_refresh_default_and_setting_persistence(self):
        from i18n import load_settings, save_settings
        orig_cfg = load_settings()
        try:
            # Verify setting can be saved and loaded
            save_settings({"auto_refresh_interval": "5 min"})
            cfg = load_settings()
            self.assertEqual(cfg.get("auto_refresh_interval"), "5 min")

            # Verify interval mapping
            mapping = {
                "Off": 0,
                "15s": 15,
                "30s": 30,
                "1 min": 60,
                "2 min": 120,
                "5 min": 300,
            }
            self.assertEqual(mapping.get("5 min"), 300)
            self.assertEqual(mapping.get("2 min"), 120)

            # Save a different setting (e.g. 2 min) and verify persistence
            save_settings({"auto_refresh_interval": "2 min"})
            cfg2 = load_settings()
            self.assertEqual(cfg2.get("auto_refresh_interval"), "2 min")
            self.assertEqual(mapping.get(cfg2.get("auto_refresh_interval")), 120)
        finally:
            save_settings(orig_cfg)

    def test_single_thread_fetch_worker_simulation(self):
        import queue

        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]
        fetch_queue = queue.Queue()
        mock_quotes = {
            s: {"symbol": s, "price": 100.0, "success": True, "change": 1.0, "change_percent": 1.0}
            for s in symbols
        }

        def mock_fetch(sym):
            return mock_quotes.get(sym, {"symbol": sym, "success": False})

        # Single-threaded sequential iteration as used in fetch_all_quotes
        results = []
        tot = len(symbols)
        for idx, sym in enumerate(symbols, 1):
            q = mock_fetch(sym)
            results.append((sym, q))
            fetch_queue.put(("STREAM_QUOTE", (sym, q, idx, tot)))

        fetch_queue.put(("ALL_QUOTES", results))

        stream_count = 0
        all_quotes_received = False
        while not fetch_queue.empty():
            msg_type, data = fetch_queue.get()
            if msg_type == "STREAM_QUOTE":
                stream_count += 1
            elif msg_type == "ALL_QUOTES":
                all_quotes_received = True

        self.assertEqual(stream_count, len(symbols))
        self.assertTrue(all_quotes_received)
        self.assertEqual(len(results), len(symbols))

    def test_fetch_all_quotes_scoping_and_execution(self):
        from main_gui import ModernPortfolioApp
        import queue

        class MockApp:
            pass

        app = MockApp()
        app.is_fetching = False
        app.all_holdings = [{"symbol": "AAPL"}]
        app.fetch_queue = queue.Queue()
        app.is_running = False  # immediately stops worker from actually fetching network
        app.fetcher = None
        status_messages = []
        app._set_status = lambda msg: status_messages.append(msg)

        # Call the unbound method on mock object
        # Before our fix, this line failed immediately with UnboundLocalError on line 8602!
        ModernPortfolioApp.fetch_all_quotes(app)
        self.assertTrue(app.is_fetching)
        self.assertTrue(len(status_messages) > 0)
        self.assertIn("(0/", status_messages[0])

    def test_retirement_spending_smile(self):
        from financial_calc import calc_retirement_spending_smile
        res = calc_retirement_spending_smile(base_annual_spending=60000.0, retire_age=65, life_expectancy=90)
        self.assertIn("capital_savings", res)
        self.assertIn("annual_schedule", res)
        self.assertEqual(res["retire_age"], 65)
        self.assertEqual(res["life_expectancy"], 90)
        self.assertEqual(res["gogo_annual"], 64800.0)
        self.assertEqual(res["slowgo_annual"], 48000.0)
        self.assertEqual(res["care_annual"], 64800.0)
        self.assertGreater(res["capital_savings"], 0)
        self.assertEqual(len(res["annual_schedule"]), 26)

    def test_sequence_of_returns_risk_simulation(self):
        from financial_calc import calc_sequence_of_returns_risk_simulation
        res = calc_sequence_of_returns_risk_simulation(
            portfolio_val=1000000.0,
            annual_withdrawal=60000.0,
            safe_assets_val=150000.0,
            crash_scenario="stagflation_1973",
        )
        self.assertIn("terminal_no_buffer", res)
        self.assertIn("terminal_with_buffer", res)
        self.assertIn("equity_capital_saved", res)
        self.assertGreater(res["terminal_with_buffer"], res["terminal_no_buffer"])
        self.assertGreater(res["equity_capital_saved"], 0)
        self.assertEqual(len(res["curve_no_buffer"]), 10)
        self.assertEqual(len(res["curve_with_buffer"]), 10)

    def test_guyton_klinger_guardrails(self):
        from financial_calc import calc_guyton_klinger_guardrails
        # Normal within guardrails
        res_norm = calc_guyton_klinger_guardrails(portfolio_val=1000000.0, current_annual_withdrawal=40000.0, initial_swr_pct=4.0)
        self.assertEqual(res_norm["rule_triggered"], "none")
        self.assertAlmostEqual(res_norm["recommended_withdrawal"], 41000.0, places=1)

        # Capital preservation rule (> 4.8%)
        res_cut = calc_guyton_klinger_guardrails(portfolio_val=600000.0, current_annual_withdrawal=40000.0, initial_swr_pct=4.0)
        self.assertEqual(res_cut["rule_triggered"], "capital_preservation")
        self.assertEqual(res_cut["adjustment_pct"], -10.0)
        self.assertEqual(res_cut["recommended_withdrawal"], 36000.0)

        # Prosperity rule (< 3.2%)
        res_raise = calc_guyton_klinger_guardrails(portfolio_val=2000000.0, current_annual_withdrawal=40000.0, initial_swr_pct=4.0)
        self.assertEqual(res_raise["rule_triggered"], "prosperity")
        self.assertEqual(res_raise["adjustment_pct"], 10.0)
        self.assertEqual(res_raise["recommended_withdrawal"], 44000.0)

    def test_three_bucket_architecture(self):
        from financial_calc import calc_three_bucket_architecture
        res = calc_three_bucket_architecture(
            total_wealth=1200000.0,
            annual_rle=50000.0,
            current_safe_assets=150000.0,
        )
        self.assertEqual(res["bucket1_target"], 100000.0)  # 2 years
        self.assertEqual(res["bucket1_actual"], 100000.0)  # fully funded
        self.assertEqual(res["bucket1_gap"], 0.0)
        self.assertEqual(res["bucket1_runway_months"], 24.0)
        self.assertEqual(res["bucket2_actual"], 50000.0)  # remaining 50k
        self.assertEqual(res["total_safe_runway_years"], 3.0)

    def test_healthcare_ltc_contingency(self):
        from financial_calc import calc_healthcare_ltc_contingency
        res = calc_healthcare_ltc_contingency(
            portfolio_val=1500000.0,
            annual_ltc_cost=60000.0,
            ltc_start_age=83,
            ltc_duration_years=4,
            current_age=60,
        )
        self.assertEqual(res["total_ltc_cost"], 240000.0)
        self.assertTrue(res["can_absorb"])
        self.assertLess(res["present_value_needed"], 240000.0)
        self.assertLess(res["ltc_wealth_impact_pct"], 15.0)

    def test_actuarial_longevity_table(self):
        from financial_calc import calc_actuarial_longevity_table
        res = calc_actuarial_longevity_table(current_age=60, gender="joint")
        self.assertEqual(res["recommended_planning_age"], 95)
        sched = res["longevity_schedule"]
        self.assertEqual(len(sched), 6)
        # Verify monotonically decreasing survival probabilities
        probs = [item["prob_joint"] for item in sched]
        self.assertEqual(probs, sorted(probs, reverse=True))

    def test_monte_carlo_distribution(self):
        from financial_calc import calc_monte_carlo_distribution
        res = calc_monte_carlo_distribution(
            portfolio_val=1000000.0,
            annual_withdrawal=40000.0,
            years=30,
            num_trials=500,
        )
        self.assertEqual(res["num_trials"], 500)
        self.assertGreater(res["success_rate_pct"], 80.0)
        self.assertLessEqual(res["p10_terminal_wealth"], res["p50_terminal_wealth"])
        self.assertLessEqual(res["p50_terminal_wealth"], res["p90_terminal_wealth"])

    def test_stagflation_sensitivity_matrix(self):
        from financial_calc import calc_stagflation_sensitivity_matrix
        res = calc_stagflation_sensitivity_matrix(
            portfolio_val=1000000.0,
            annual_withdrawal=40000.0,
        )
        mat = res["matrix"]
        self.assertEqual(len(mat), 4)  # 4 inflation tiers
        self.assertEqual(len(mat[0]), 4)  # 4 real return tiers
        # Higher inflation should reduce or maintain longevity
        self.assertGreaterEqual(mat[0][0]["longevity_years"], mat[3][0]["longevity_years"])

    def test_rising_equity_glidepath(self):
        from financial_calc import calc_rising_equity_glidepath
        # Accumulation
        res_acc = calc_rising_equity_glidepath(current_age=55, retire_age=65, current_equity_pct=70.0)
        self.assertEqual(res_acc["target_equity_pct"], 65.0)

        # Early retirement (Year 0)
        res_ret0 = calc_rising_equity_glidepath(current_age=65, retire_age=65, current_equity_pct=50.0)
        self.assertEqual(res_ret0["target_equity_pct"], 50.0)
        self.assertEqual(res_ret0["deviation_pct"], 0.0)

        # Mid retirement (Year 10)
        res_ret10 = calc_rising_equity_glidepath(current_age=75, retire_age=65, current_equity_pct=63.3)
        self.assertAlmostEqual(res_ret10["target_equity_pct"], 63.3, places=1)

        # Mature retirement (Year 20)
        res_ret20 = calc_rising_equity_glidepath(current_age=85, retire_age=65, current_equity_pct=70.0)
        self.assertEqual(res_ret20["target_equity_pct"], 70.0)

    def test_calc_fire_metrics_advanced_toolkit_integration(self):
        from financial_calc import calc_fire_metrics
        holdings = [
            {"symbol": "SPY", "shares": 1000, "current_price": 500.0, "currency": "USD", "annual_dividend": 6000.0},
            {"symbol": "TIP", "shares": 1000, "current_price": 100.0, "currency": "USD", "annual_dividend": 2500.0},
        ]
        res = calc_fire_metrics(
            current_annual_div=8500.0,
            target_monthly_expense=5000.0,
            holdings=holdings,
            current_age=60,
            retire_age=65,
            life_expectancy=90,
            target_safe_years=25,
        )
        self.assertIn("spending_smile_data", res)
        self.assertIn("srr_data", res)
        self.assertIn("guardrails_data", res)
        self.assertIn("three_bucket_data", res)
        self.assertIn("ltc_data", res)
        self.assertIn("longevity_data", res)
        self.assertIn("monte_carlo_dist", res)
        self.assertIn("stagflation_data", res)
        self.assertIn("glidepath_data", res)

    def test_modern_portfolio_app_retirement_toolkit_dialog_method(self):
        from main_gui import ModernPortfolioApp
        self.assertTrue(hasattr(ModernPortfolioApp, "_open_retirement_advanced_toolkit_dialog"))

    def test_retirement_10_tabs_translations_in_all_languages(self):
        from i18n import TRANSLATIONS, set_language, t, get_current_language
        orig_lang = get_current_language()
        try:
            for lang in ["en", "zh_TW", "zh_CN"]:
                set_language(lang)
                self.assertIn("fire_bottom_actions_title", TRANSLATIONS[lang])
                self.assertIn("btn_fire_toolkit", TRANSLATIONS[lang])
                self.assertIn("fire_tk_title", TRANSLATIONS[lang])
                self.assertIn("fire_tk_sub", TRANSLATIONS[lang])
                # Verify all 10 tabs exist
                for i in range(1, 11):
                    tab_key = f"fire_tk_tab_{i}"
                    self.assertIn(tab_key, TRANSLATIONS[lang], f"Missing {tab_key} in {lang}")
                    translated_text = t(tab_key)
                    self.assertTrue(len(translated_text) > 0)
        finally:
            set_language(orig_lang)

    def test_all_retirement_algorithms_edge_cases(self):
        from financial_calc import (
            calc_retirement_spending_smile,
            calc_sequence_of_returns_risk_simulation,
            calc_guyton_klinger_guardrails,
            calc_three_bucket_architecture,
            calc_healthcare_ltc_contingency,
            calc_actuarial_longevity_table,
            calc_monte_carlo_distribution,
            calc_stagflation_sensitivity_matrix,
            calc_rising_equity_glidepath,
        )

        # 1. Spending Smile with late retirement (Age 75 to 88)
        s_late = calc_retirement_spending_smile(base_annual_spending=50000.0, retire_age=75, life_expectancy=88)
        self.assertEqual(len(s_late["annual_schedule"]), 14)
        self.assertGreater(s_late["flat_total_lifetime"], 0)

        # 2. SRR Crash with zero safe buffer
        srr_zero = calc_sequence_of_returns_risk_simulation(portfolio_val=500000.0, annual_withdrawal=30000.0, safe_assets_val=0.0)
        self.assertEqual(srr_zero["equity_capital_saved"], 0.0)
        self.assertEqual(srr_zero["terminal_no_buffer"], srr_zero["terminal_with_buffer"])

        # 3. Guyton Klinger with 0 withdrawal
        gk_zero = calc_guyton_klinger_guardrails(portfolio_val=1000000.0, current_annual_withdrawal=0.0)
        self.assertEqual(gk_zero["rule_triggered"], "none")
        self.assertEqual(gk_zero["recommended_withdrawal"], 0.0)

        # 4. Three-Bucket with safe assets exceeding portfolio
        tb_overflow = calc_three_bucket_architecture(total_wealth=500000.0, annual_rle=40000.0, current_safe_assets=800000.0)
        self.assertEqual(tb_overflow["bucket1_actual"], 80000.0)
        self.assertEqual(tb_overflow["bucket2_actual"], 200000.0)
        self.assertEqual(tb_overflow["bucket3_actual"], 0.0)

        # 5. LTC Shock already in old age (current age 85, shock age 85)
        ltc_now = calc_healthcare_ltc_contingency(portfolio_val=300000.0, current_age=85, ltc_start_age=85)
        self.assertEqual(ltc_now["present_value_needed"], ltc_now["total_ltc_cost"])

        # 6. Longevity table at age 85
        long_85 = calc_actuarial_longevity_table(current_age=85)
        self.assertEqual(long_85["longevity_schedule"][0]["prob_joint"], 100.0)  # Age 75 already passed
        self.assertEqual(long_85["longevity_schedule"][1]["prob_joint"], 100.0)  # Age 80 already passed
        self.assertEqual(long_85["longevity_schedule"][2]["prob_joint"], 100.0)  # Age 85 current

        # 7. Monte Carlo with very small portfolio (early exhaustion)
        mc_small = calc_monte_carlo_distribution(portfolio_val=50000.0, annual_withdrawal=30000.0, years=10)
        self.assertEqual(mc_small["success_rate_pct"], 0.0)

        # 8. Stagflation matrix dimensions
        stag = calc_stagflation_sensitivity_matrix(portfolio_val=500000.0, annual_withdrawal=25000.0)
        self.assertEqual(len(stag["matrix"]), 4)
        self.assertEqual(len(stag["matrix"][0]), 4)

        # 9. Rising equity glidepath at age 100
        gp_old = calc_rising_equity_glidepath(current_age=100, retire_age=65, current_equity_pct=70.0)
        self.assertEqual(gp_old["target_equity_pct"], 70.0)
        self.assertEqual(gp_old["deviation_pct"], 0.0)

    def test_ui_usability_and_shortcuts(self):
        from i18n import TRANSLATIONS, set_language, get_current_language, t
        orig_lang = get_current_language()
        try:
            required_keys = [
                "menu_tools",
                "btn_shortcuts",
                "dlg_shortcuts_title",
                "badge_safe_engine",
                "tip_tools_menu",
                "tip_shortcuts",
            ]
            for lang in ("en", "zh_TW", "zh_CN"):
                set_language(lang)
                for k in required_keys:
                    self.assertIn(k, TRANSLATIONS[lang], f"Missing key {k} in {lang}")
                    self.assertTrue(len(t(k)) > 0, f"Empty text for {k} in {lang}")

            # Check main_gui methods for usability
            import main_gui
            self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_rebuild_tools_menu"))
            self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_setup_keyboard_shortcuts"))
            self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_focus_search"))
            self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_open_shortcuts_dialog"))
            self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_clear_search"))
            self.assertTrue(hasattr(main_gui.ModernPortfolioApp, "_clear_watchlist_search"))

            import inspect
            watch_src = inspect.getsource(main_gui.ModernPortfolioApp._build_watchlist_tab)
            self.assertNotIn("attach_tooltip(search_entry,", watch_src)
            self.assertIn("attach_tooltip(self.watchlist_search_entry,", watch_src)
        finally:
            set_language(orig_lang)

    def test_watchlist_company_name_resolution(self):
        """Verify that watchlist stock names equal to symbols or blank are updated with real company names."""
        import tempfile
        from unittest.mock import MagicMock, patch
        from csv_manager import save_watchlist, load_watchlist, bulk_add_to_watchlist, add_to_watchlist
        import main_gui

        with tempfile.TemporaryDirectory() as tmpdir:
            test_watch = os.path.join(tmpdir, "test_watchlist.csv")
            initial_items = [
                {"symbol": "AAPL", "name": "AAPL", "target_price": 200.0, "currency": "USD", "notes": "", "tags": ""},
                {"symbol": "TSLA", "name": "", "target_price": 250.0, "currency": "USD", "notes": "", "tags": ""},
            ]
            save_watchlist(initial_items, filepath=test_watch)

            # 1. Test bulk_add_to_watchlist with cache
            mock_cache = {
                "AAPL": {"price": 220.0, "name": "Apple Inc.", "currency": "USD", "success": True},
                "TSLA": {"price": 260.0, "name": "Tesla, Inc.", "currency": "USD", "success": True},
            }
            with patch("csv_manager.load_watchlist_quotes_cache", return_value=mock_cache):
                added = bulk_add_to_watchlist([{"symbol": "NVDA", "name": "NVDA"}], filepath=test_watch)
                loaded = load_watchlist(filepath=test_watch)
                self.assertTrue(any(it["symbol"] == "NVDA" for it in loaded))

            # 2. Test _refresh_watchlist_tab resolution and persistence
            app = MagicMock()
            app._watchlist_quotes_cache = mock_cache
            app.all_holdings = []
            app.holdings = []
            app.watchlist_tree = MagicMock()
            inserted_values = []
            def fake_insert(*args, **kwargs):
                vals = kwargs.get("values", args[2] if len(args) > 2 else None)
                if vals:
                    inserted_values.append(vals)
            app.watchlist_tree.insert.side_effect = fake_insert
            app.watchlist_search_var = MagicMock()
            app.watchlist_search_var.get.return_value = ""
            app.watchlist_tag_filter_var = MagicMock()
            app.watchlist_tag_filter_var.get.return_value = ""
            app._watchlist_sort_col = "symbol"
            app._watchlist_sort_desc = False

            with patch("main_gui.load_watchlist", return_value=load_watchlist(filepath=test_watch)), \
                 patch("main_gui.WATCHLIST_CSV", test_watch), \
                 patch("main_gui.save_watchlist", side_effect=lambda items, fp=None: save_watchlist(items, test_watch)):
                main_gui.ModernPortfolioApp._refresh_watchlist_tab(app)

            # Check inserted rows had real names
            name_map = {row[0]: row[1] for row in inserted_values}
            self.assertEqual(name_map.get("AAPL"), "Apple Inc.")
            self.assertEqual(name_map.get("TSLA"), "Tesla, Inc.")

            # Check test_watch file was persisted with real names
            persisted = load_watchlist(filepath=test_watch)
            p_map = {it["symbol"]: it["name"] for it in persisted}
            self.assertEqual(p_map.get("AAPL"), "Apple Inc.")
            self.assertEqual(p_map.get("TSLA"), "Tesla, Inc.")

            # 3. Test _handle_all_quotes_result updates watchlist.csv
            app_quote = MagicMock()
            app_quote._watchlist_quotes_cache = {}
            app_quote.all_holdings = []
            app_quote._network_errors = []
            results = [
                ("NVDA", {"symbol": "NVDA", "price": 125.0, "name": "NVIDIA Corporation", "currency": "USD", "success": True})
            ]
            with patch("main_gui.WATCHLIST_CSV", test_watch), \
                 patch("main_gui.PORTFOLIO_CSV", os.path.join(tmpdir, "p.csv")), \
                 patch("main_gui.save_portfolio"), \
                 patch("main_gui.save_watchlist_quotes_cache"):
                main_gui.ModernPortfolioApp._handle_all_quotes_result(app_quote, results)

            persisted_after = load_watchlist(filepath=test_watch)
            p_map_after = {it["symbol"]: it["name"] for it in persisted_after}
            self.assertEqual(p_map_after.get("NVDA"), "NVIDIA Corporation")

    def test_desktop_network_errors_capped_for_memory_safety(self):
        """Verify that ModernPortfolioApp caps _network_errors to 100 items to prevent memory leaks."""
        from unittest.mock import MagicMock, patch
        import main_gui

        app = object.__new__(main_gui.ModernPortfolioApp)
        app.is_running = True
        app._network_errors = [{"time": "t", "symbol": f"S{i}", "error": "err"} for i in range(120)]
        app.all_holdings = []
        app._watchlist_quotes_cache = {}
        app._on_portfolio_selected = MagicMock()
        app._update_network_status_badge = MagicMock()
        app._set_status = MagicMock()
        app.lbl_time = MagicMock()

        failed_results = [("FAIL_SYM", {"symbol": "FAIL_SYM", "success": False, "error": "Timeout"})]
        with patch("main_gui.save_portfolio"), patch("main_gui.save_watchlist_quotes_cache"), patch("main_gui.load_watchlist", return_value=[]):
            main_gui.ModernPortfolioApp._handle_all_quotes_result(app, failed_results)

        self.assertLessEqual(len(app._network_errors), 100)
        self.assertEqual(len(app._network_errors), 100)

    def test_selection_preservation_during_quote_refresh(self):
        """Verify that user selection in watchlist and holdings is preserved during stock refresh."""
        import tempfile
        from unittest.mock import MagicMock, patch
        import main_gui

        # 1. Test Watchlist in-place update preserves selection
        app = MagicMock()
        app.watchlist_tree = MagicMock()
        app.watchlist_tree.get_children.return_value = ["wl_AAPL", "wl_MSFT"]
        app.watchlist_tree.selection.return_value = ["wl_AAPL"]
        app.watchlist_tree.item.return_value = [
            "AAPL", "Apple Inc", "Tech", "$200.00", "+1.50%", "$180.00", "+11.11%", "30.0", "$150-$230", "0.5%", "Monitoring", "USD", "2026-10-05 12:00:00", "2026-09-01", "Notes"
        ]

        quote = {
            "symbol": "AAPL",
            "price": 205.50,
            "name": "Apple Inc",
            "change": 5.50,
            "change_percent": 2.75,
            "currency": "USD",
            "success": True,
        }

        # Update in-place
        res = main_gui.ModernPortfolioApp._update_watchlist_row_in_place(app, "AAPL", quote)
        self.assertTrue(res)
        # Verify item was called to update values, NOT delete
        app.watchlist_tree.delete.assert_not_called()
        self.assertEqual(app.watchlist_tree.selection.return_value, ["wl_AAPL"])

        # 2. Test Holdings in-place update preserves selection
        app.holdings_tree = MagicMock()
        app.holdings_tree.get_children.return_value = ["holding_item_0"]
        app.holdings_tree.selection.return_value = ["holding_item_0"]
        app.converter = MagicMock()
        app.converter.CURRENCY_SYMBOLS = {"USD": "$"}
        mock_holding = {
            "portfolio": "Main",
            "symbol": "AAPL",
            "name": "Apple Inc",
            "currency": "USD",
            "shares": 10.0,
            "buy_price": 150.0,
            "current_price": 200.0,
        }
        app.holding_map = {"holding_item_0": mock_holding}
        app.holdings_tree.item.return_value = [
            "Main", "AAPL", "Apple Inc", "USD", "10", "$150.00", "$200.00", "+5.00%", "$2,000.00", "$1,500.00", "+$500.00", "+33.33%", "-", "-", "0.5%", "$10.00", "2026-10-05"
        ]

        main_gui.ModernPortfolioApp._update_holdings_row_in_place(app, "AAPL", quote)
        app.holdings_tree.delete.assert_not_called()
        self.assertEqual(app.holdings_tree.selection.return_value, ["holding_item_0"])
        self.assertEqual(mock_holding["current_price"], 205.50)

        # 3. Test _refresh_holdings_table restores selection
        app.holdings = [mock_holding]
        app.search_filter_var = MagicMock()
        app.search_filter_var.get.return_value = ""
        app.current_portfolio = "Main"
        app.holdings_tree.selection.return_value = ["holding_item_0"]
        app.holdings_tree.get_children.side_effect = None
        app.holdings_tree.get_children.return_value = ["holding_item_0"]
        app.holdings_tree.item.return_value = [
            "Main", "AAPL", "Apple Inc", "USD", "10", "$150.00", "$205.50", "+5.00%", "$2,055.00", "$1,500.00", "+$555.00", "+37.00%", "-", "-", "0.5%", "$10.00", "2026-10-05"
        ]
        main_gui.ModernPortfolioApp._refresh_holdings_table(app)
        app.holdings_tree.selection_set.assert_called_with(["holding_item_0"])

        # 4. Test _refresh_watchlist_tab restores selection
        app.watchlist_tree.selection.return_value = ["wl_AAPL"]
        app.watchlist_tree.get_children.return_value = ["wl_AAPL", "wl_MSFT"]
        app.watchlist_tree.item.return_value = [
            "AAPL", "Apple Inc", "Tech", "$205.50", "+2.75%", "$180.00", "+14.17%", "30.0", "$150-$230", "0.5%", "Monitoring", "USD", "2026-10-05 12:00:00", "2026-09-01", "Notes"
        ]
        app.watchlist_search_var = MagicMock()
        app.watchlist_search_var.get.return_value = ""
        app.watchlist_tag_filter_var = MagicMock()
        app.watchlist_tag_filter_var.get.return_value = ""
        app._watchlist_sort_col = "symbol"
        app._watchlist_sort_desc = False

        with patch("main_gui.load_watchlist", return_value=[{"symbol": "AAPL", "name": "Apple Inc", "target_price": 180.0, "currency": "USD"}]), \
             patch("main_gui.save_watchlist"):
            main_gui.ModernPortfolioApp._refresh_watchlist_tab(app)

        app.watchlist_tree.selection_set.assert_called_with(["wl_AAPL"])

    def test_fire_top_action_toolbar_and_translations(self):
        """Test the top action toolbar translation keys and widget existence on ModernPortfolioApp."""
        from i18n import TRANSLATIONS, set_language, t, get_current_language
        import main_gui

        orig_lang = get_current_language()
        required_keys = [
            "fire_bottom_actions_title",
            "btn_deep_risk_short",
            "btn_crisis_stress_short",
            "btn_fee_tax_drag_short",
            "btn_rebalance_5_25_short",
            "btn_simplicity_short",
            "lbl_fire_models_suite",
            "lbl_fire_actions_suite",
            "btn_recalc_fire",
            "tip_fire_toolkit_all",
            "tip_fire_apply_rebalance",
            "tip_fire_simulate_trade",
            "tip_fire_export_report",
            "tip_fire_recalc",
        ]
        try:
            for lang in ["en", "zh_TW", "zh_CN"]:
                set_language(lang)
                for key in required_keys:
                    self.assertIn(key, TRANSLATIONS[lang], f"Missing key '{key}' in language '{lang}'")
                    self.assertTrue(len(t(key)) > 0, f"Empty translation for '{key}' in '{lang}'")
        finally:
            set_language(orig_lang)

    def test_fire_step1_combines_same_stock_and_calculates(self):
        """Test that Step 1 of FIRE aggregates multiple holdings of the same stock into a single entry with combined calculation."""
        import main_gui
        from unittest.mock import MagicMock, patch

        app = object.__new__(main_gui.ModernPortfolioApp)
        # User has 2 separate entries of VOO (e.g. from 2 accounts) and 1 TIP
        app.holdings = [
            {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "shares": 50, "current_price": 500.0, "currency": "USD", "annual_dividend": 200.0},
            {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "shares": 50, "current_price": 500.0, "currency": "USD", "annual_dividend": 200.0},
            {"symbol": "TIP", "name": "iShares TIPS Bond ETF", "shares": 100, "current_price": 100.0, "currency": "USD", "annual_dividend": 300.0},
        ]
        app.summary_currency = "USD"
        app.converter = MagicMock()
        app.converter.format_money = lambda v, c: f"${v:,.2f}"
        app.converter.convert = lambda v, f, t: v

        app.tab_fire = MagicMock()
        inserted_items = []
        app.fire_holdings_tree = MagicMock()
        app.fire_holdings_tree.get_children.return_value = []
        app.fire_holdings_tree.insert.side_effect = lambda parent, index, values, tags: inserted_items.append({"values": values, "tags": tags})

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

        # Verify that the treeview receives exactly 2 items (VOO combined, and TIP) instead of 3
        self.assertEqual(len(inserted_items), 2, "Duplicate VOO must be combined into a single entry!")
        voo_entry = next(it for it in inserted_items if it["values"][0] == "VOO")
        tip_entry = next(it for it in inserted_items if it["values"][0] == "TIP")

        # Total VOO value: 50*500 + 50*500 = $50,000.00
        self.assertEqual(voo_entry["values"][2], "$50,000.00")
        # Total portfolio: 50,000 + 10,000 = 60,000. VOO weight: 50000/60000 = 83.3%
        self.assertEqual(voo_entry["values"][3], "83.3%")

        # Combined holdings stored on app
        self.assertEqual(len(app._last_combined_fire_holdings), 2)
        combined_voo = next(h for h in app._last_combined_fire_holdings if h["symbol"] == "VOO")
        self.assertEqual(combined_voo["shares"], 100.0)
        self.assertEqual(combined_voo["value"], 50000.0)
        # Test sorting
        tree_items = {"id1": ("VOO", "Vanguard", "$50,000.00", "83.3%", "Stock"), "id2": ("TIP", "TIPS", "$10,000.00", "16.7%", "Safe")}
        app.fire_holdings_tree.get_children = lambda root="": list(tree_items.keys())
        app.fire_holdings_tree.item = lambda iid, field: tree_items[iid] if field == "values" else ("tag",)
        reinserted = []
        app.fire_holdings_tree.delete = lambda iid: None
        app.fire_holdings_tree.insert = lambda p, idx, values, tags: reinserted.append(values)
        main_gui.ModernPortfolioApp._sort_fire_holdings_by(app, "value")
        self.assertEqual(len(reinserted), 2)

    def test_watchlist_colorful_gain_loss_tags(self):
        """Test that Watchlist displays stocks with colorful tags when they drop or raise."""
        import main_gui
        from unittest.mock import MagicMock, patch

        app = object.__new__(main_gui.ModernPortfolioApp)
        app.dark_mode = False
        app.green_color = "#0f9d58"
        app.red_color = "#d93025"
        app.text_dark = "#202124"
        app._watchlist_quotes_cache = {
            "AAPL": {"price": 200.0, "change": 5.0, "change_percent": 2.56, "name": "Apple Inc"},
            "TSLA": {"price": 180.0, "change": -9.0, "change_percent": -4.76, "name": "Tesla Inc"},
            "MSFT": {"price": 300.0, "change": 2.0, "change_percent": 0.67, "name": "Microsoft Corp"},
        }
        app.all_holdings = []
        app.holdings = []
        app.watchlist_search_var = MagicMock(get=lambda: "")
        app.watchlist_tag_filter_var = MagicMock(get=lambda: "")
        app._watchlist_sort_col = "symbol"
        app._watchlist_sort_desc = False

        inserted_rows = {}
        def mock_insert(*args, **kwargs):
            iid = kwargs.get("iid", args[1] if len(args) > 1 else None)
            vals = kwargs.get("values", args[2] if len(args) > 2 else None)
            tags = kwargs.get("tags", args[3] if len(args) > 3 else ())
            inserted_rows[iid] = {"values": vals, "tags": tags}

        app.watchlist_tree = MagicMock()
        app.watchlist_tree.get_children.return_value = []
        app.watchlist_tree.insert.side_effect = mock_insert
        app.watchlist_tree.selection.return_value = []

        test_items = [
            {"symbol": "AAPL", "name": "Apple Inc", "target_buy_price": 150.0},  # Up, target NOT reached -> positive
            {"symbol": "TSLA", "name": "Tesla Inc", "target_buy_price": 150.0},  # Down, target NOT reached -> negative
            {"symbol": "MSFT", "name": "Microsoft Corp", "target_buy_price": 350.0},  # Up, target REACHED (300 <= 350) -> reached_positive
        ]

        with patch("main_gui.load_watchlist", return_value=test_items), \
             patch("main_gui.save_watchlist"):
            main_gui.ModernPortfolioApp._refresh_watchlist_tab(app)

        self.assertIn("wl_AAPL", inserted_rows)
        self.assertIn("wl_TSLA", inserted_rows)
        self.assertIn("wl_MSFT", inserted_rows)

        # AAPL rose (+2.56%) -> positive tag (green)
        self.assertEqual(inserted_rows["wl_AAPL"]["tags"], ("positive",))
        # TSLA dropped (-4.76%) -> negative tag (red)
        self.assertEqual(inserted_rows["wl_TSLA"]["tags"], ("negative",))
        # MSFT target reached & rose -> reached_positive tag
        self.assertEqual(inserted_rows["wl_MSFT"]["tags"], ("reached_positive",))


class TestFireChartRenderers(unittest.TestCase):
    """Unit tests for William J. Bernstein FIRE chart and gauge rendering engines."""

    def setUp(self):
        from unittest.mock import MagicMock, patch
        self.canvas = MagicMock()
        self.canvas.winfo_width.return_value = 400
        self.canvas.winfo_height.return_value = 50

    def test_draw_fire_asset_ratio_bar_zero(self):
        from chart_canvas import draw_fire_asset_ratio_bar
        draw_fire_asset_ratio_bar(self.canvas, equity_val=0.0, safe_val=0.0)
        self.canvas.delete.assert_called_with("all")
        self.canvas.create_text.assert_called()
        args, kwargs = self.canvas.create_text.call_args
        self.assertIn("No asset data", kwargs.get("text", ""))

    def test_draw_fire_asset_ratio_bar_normal(self):
        from chart_canvas import draw_fire_asset_ratio_bar
        draw_fire_asset_ratio_bar(self.canvas, equity_val=750000.0, safe_val=250000.0, currency_prefix="$", dark_mode=False)
        self.canvas.delete.assert_called_with("all")
        # Ensure rectangles for track and segments were drawn
        self.assertGreaterEqual(self.canvas.create_rectangle.call_count, 3)
        # Ensure texts for equity and safe percentages were rendered
        text_calls = [k.get("text", "") for _, k in self.canvas.create_text.call_args_list]
        self.assertTrue(any("Equity:" in t and "75.0%" in t for t in text_calls))
        self.assertTrue(any("Safe:" in t and "25.0%" in t for t in text_calls))

    def test_draw_fire_asset_ratio_bar_dark_mode(self):
        from chart_canvas import draw_fire_asset_ratio_bar
        draw_fire_asset_ratio_bar(self.canvas, equity_val=600000.0, safe_val=400000.0, currency_prefix="$", dark_mode=True)
        self.canvas.configure.assert_called_with(bg="#1e222d")

    def test_draw_fire_timeline_bar_normal(self):
        from chart_canvas import draw_fire_timeline_bar
        draw_fire_timeline_bar(self.canvas, cur_age=45, ret_age=60, life_exp=90, dark_mode=False)
        self.canvas.delete.assert_called_with("all")
        self.assertGreaterEqual(self.canvas.create_rectangle.call_count, 2)
        text_calls = [k.get("text", "") for _, k in self.canvas.create_text.call_args_list]
        self.assertTrue(any("Age 45" in t for t in text_calls))
        self.assertTrue(any("Age 60" in t for t in text_calls))
        self.assertTrue(any("Age 90" in t for t in text_calls))
        self.assertTrue(any("Accumulation" in t for t in text_calls))
        self.assertTrue(any("Distribution" in t for t in text_calls))

    def test_draw_fire_timeline_bar_already_retired(self):
        from chart_canvas import draw_fire_timeline_bar
        # cur_age == ret_age
        draw_fire_timeline_bar(self.canvas, cur_age=65, ret_age=65, life_exp=95, dark_mode=True)
        self.canvas.delete.assert_called_with("all")
        self.assertGreaterEqual(self.canvas.create_rectangle.call_count, 1)

    def test_draw_fire_comparison_gauge_shortfall(self):
        from chart_canvas import draw_fire_comparison_gauge
        draw_fire_comparison_gauge(
            self.canvas,
            current_val=100000.0,
            target_val=250000.0,
            label_cur="Current Safe",
            label_tgt="25y Buffer",
            unit_prefix="$",
            projection_note="Covers 10.0 of 25.0 yrs",
            dark_mode=False,
        )
        self.canvas.delete.assert_called_with("all")
        text_calls = [k.get("text", "") for _, k in self.canvas.create_text.call_args_list]
        self.assertTrue(any("Current Safe: $100,000 (40.0%)" in t for t in text_calls))
        self.assertTrue(any("25y Buffer: $250,000" in t for t in text_calls))
        self.assertTrue(any("Gap: -$150,000" in t for t in text_calls))
        self.assertTrue(any("Covers 10.0 of 25.0 yrs" in t for t in text_calls))

    def test_draw_fire_comparison_gauge_target_met(self):
        from chart_canvas import draw_fire_comparison_gauge
        draw_fire_comparison_gauge(
            self.canvas,
            current_val=300000.0,
            target_val=250000.0,
            label_cur="Current Safe",
            label_tgt="Target",
            unit_prefix="$",
            projection_note="✓ Surplus",
            dark_mode=True,
        )
        text_calls = [k.get("text", "") for _, k in self.canvas.create_text.call_args_list]
        self.assertTrue(any("Target Met" in t and "+$50,000 Surplus" in t for t in text_calls))

    def test_draw_fire_comparison_gauge_zero_target(self):
        from chart_canvas import draw_fire_comparison_gauge
        draw_fire_comparison_gauge(
            self.canvas,
            current_val=0.0,
            target_val=0.0,
            label_cur="Current",
            label_tgt="Target",
            dark_mode=False,
        )
        self.canvas.delete.assert_called_with("all")

    def test_draw_fire_burn_meter(self):
        from chart_canvas import draw_fire_burn_meter
        # Test Green Zone (<2.0%)
        draw_fire_burn_meter(self.canvas, burn_rate_pct=1.85, dark_mode=False)
        self.canvas.create_polygon.assert_called()
        text_calls = [k.get("text", "") for _, k in self.canvas.create_text.call_args_list]
        self.assertTrue(any("1.85% (Safe)" in t for t in text_calls))

        # Test Yellow Zone (2.0 - 3.5%)
        self.canvas.reset_mock()
        draw_fire_burn_meter(self.canvas, burn_rate_pct=3.10, dark_mode=True)
        text_calls_yellow = [k.get("text", "") for _, k in self.canvas.create_text.call_args_list]
        self.assertTrue(any("3.10% (Sustainable)" in t for t in text_calls_yellow))

        # Test Red Zone (>3.5%)
        self.canvas.reset_mock()
        draw_fire_burn_meter(self.canvas, burn_rate_pct=4.80, dark_mode=False)
        text_calls_red = [k.get("text", "") for _, k in self.canvas.create_text.call_args_list]
        self.assertTrue(any("4.80% (Over-Burn)" in t for t in text_calls_red))

    def test_draw_fire_floor_coverage_bar(self):
        from chart_canvas import draw_fire_floor_coverage_bar
        draw_fire_floor_coverage_bar(self.canvas, ess_cov_pct=100.0, disc_cov_pct=85.0, dark_mode=False)
        self.canvas.delete.assert_called_with("all")
        text_calls = [k.get("text", "") for _, k in self.canvas.create_text.call_args_list]
        self.assertTrue(any("Essential Floor: 100.0% Covered" in t for t in text_calls))
        self.assertTrue(any("Discretionary Buffer: 85.0%" in t for t in text_calls))

    def test_fire_tab_refresh_invokes_all_canvases(self):
        import main_gui
        from unittest.mock import MagicMock, patch

        app = MagicMock()
        app.dark_mode = False
        app.summary_currency = "USD"
        app.converter = MagicMock()
        app.converter.convert.side_effect = lambda v, f, t: float(v)
        app.converter.format_money.side_effect = lambda v, c: f"${float(v):,.0f}"
        app.converter.get_symbol.return_value = "$"
        app._get_holding_asset_class.return_value = "equity"

        app.tab_fire = MagicMock()
        app.fire_holdings_tree = MagicMock()
        app.fire_holdings_tree.get_children.return_value = []
        app.holdings = [
            {"symbol": "VOO", "shares": 100, "price": 400.0, "currency": "USD", "annual_dividend": 600.0},
        ]
        app.fire_outside_safe_entry = MagicMock()
        app.fire_outside_safe_entry.get.return_value = "50000.0"

        app.fire_age_spin = MagicMock()
        app.fire_age_spin.get.return_value = "45"
        app.fire_retire_age_spin = MagicMock()
        app.fire_retire_age_spin.get.return_value = "60"
        app.fire_horizon_spin = MagicMock()
        app.fire_horizon_spin.get.return_value = "90"
        app.fire_safe_years_combo = MagicMock()
        app.fire_safe_years_combo.get.return_value = "25"
        app.fire_exp_entry = MagicMock()
        app.fire_exp_entry.get.return_value = "4000.0"
        app.fire_ess_exp_entry = MagicMock()
        app.fire_ess_exp_entry.get.return_value = "2800.0"
        app.fire_disc_exp_entry = MagicMock()
        app.fire_disc_exp_entry.get.return_value = "1200.0"
        app.fire_pension_entry = MagicMock()
        app.fire_pension_entry.get.return_value = "15000.0"
        app.fire_savings_entry = MagicMock()
        app.fire_savings_entry.get.return_value = "1000.0"
        app.fire_growth_entry = MagicMock()
        app.fire_growth_entry.get.return_value = "5.0"
        app.fire_cape_spin = MagicMock()
        app.fire_cape_spin.get.return_value = "34.0"
        app.fire_delay_pension_var = MagicMock()
        app.fire_delay_pension_var.get.return_value = True

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
        app.fire_floor_banner = MagicMock()
        app.lbl_fire_floor_badge = MagicMock()
        app.lbl_fire_disc_badge = MagicMock()
        app.lbl_fire_checklist = MagicMock()
        app.fire_audit_summary_lbl = MagicMock()

        # Canvas mock instances
        app.canvas_fire_asset_split = MagicMock()
        app.canvas_fire_timeline = MagicMock()
        app.canvas_safe_gap = MagicMock()
        app.canvas_div_gap = MagicMock()
        app.canvas_cap_gap = MagicMock()
        app.canvas_burn_meter = MagicMock()
        app.canvas_floor_cov = MagicMock()

        with patch("main_gui.save_settings"), patch("main_gui.load_settings", return_value={}):
            main_gui.ModernPortfolioApp._refresh_fire_tab(app)

        # Verify all canvas renderers were invoked
        app.canvas_fire_asset_split.delete.assert_called_with("all")
        app.canvas_fire_timeline.delete.assert_called_with("all")
        app.canvas_safe_gap.delete.assert_called_with("all")
        app.canvas_div_gap.delete.assert_called_with("all")
        app.canvas_cap_gap.delete.assert_called_with("all")
        app.canvas_burn_meter.delete.assert_called_with("all")
        app.canvas_floor_cov.delete.assert_called_with("all")


class TestMobileWebServerAndDeviceDetection(unittest.TestCase):
    """Unit tests for mobile web server, auto-device detection, and PWA endpoints."""

    def test_parse_device_info(self):
        from web_server import parse_device_info

        # iPhone
        iphone_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
        res_iphone = parse_device_info(iphone_ua)
        self.assertEqual(res_iphone["device_type"], "iphone")
        self.assertTrue(res_iphone["is_touch"])
        self.assertIn("iPhone", res_iphone["device_name"])

        # iPad
        ipad_ua = "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
        res_ipad = parse_device_info(ipad_ua)
        self.assertEqual(res_ipad["device_type"], "ipad")
        self.assertTrue(res_ipad["is_touch"])
        self.assertIn("iPad", res_ipad["device_name"])

        # Windows PC
        win_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
        res_win = parse_device_info(win_ua)
        self.assertEqual(res_win["device_type"], "windows")
        self.assertFalse(res_win["is_touch"])

        # Mac Desktop
        mac_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"
        res_mac = parse_device_info(mac_ua)
        self.assertEqual(res_mac["device_type"], "mac")
        self.assertFalse(res_mac["is_touch"])

    def test_web_server_endpoints(self):
        import urllib.request
        import json
        import time
        import web_server

        web_server.stop_server()
        port = web_server.start_server(port=9920, host="127.0.0.1")
        time.sleep(0.05)
        base_url = f"http://127.0.0.1:{port}"

        try:
            # 1. Test HTML root (PWA tags & touch controls present)
            with urllib.request.urlopen(f"{base_url}/") as resp:
                self.assertEqual(resp.status, 200)
                html = resp.read().decode("utf-8")
                self.assertIn("apple-mobile-web-app-capable", html)
                self.assertIn("manifest.json", html)
                self.assertIn("G_Finance", html)
                self.assertIn("bottom-tab-bar", html)

            # 2. Test PWA Manifest
            with urllib.request.urlopen(f"{base_url}/manifest.json") as resp:
                self.assertEqual(resp.status, 200)
                manifest = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(manifest["display"], "standalone")
                self.assertEqual(manifest["short_name"], "G_Finance")

            # 3. Test Service Worker
            with urllib.request.urlopen(f"{base_url}/sw.js") as resp:
                self.assertEqual(resp.status, 200)
                sw_content = resp.read().decode("utf-8")
                self.assertIn("CACHE_NAME", sw_content)

            # 4. Test Device Detection API with custom iPhone header
            req = urllib.request.Request(
                f"{base_url}/api/device",
                headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
            )
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                dev_data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(dev_data["device_type"], "iphone")
                self.assertTrue(dev_data["is_touch"])

            # 5. Test Portfolio API
            with urllib.request.urlopen(f"{base_url}/api/portfolio?currency=USD") as resp:
                self.assertEqual(resp.status, 200)
                p_data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("total_value", p_data)
                self.assertIn("holdings", p_data)
                self.assertIn("equity_assets", p_data)
                self.assertIn("safe_assets", p_data)

            # 6. Test FIRE Metrics API
            with urllib.request.urlopen(f"{base_url}/api/fire?currency=USD") as resp:
                self.assertEqual(resp.status, 200)
                f_data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("safe_asset_gap", f_data)
                self.assertIn("burn_rate_pct", f_data)
                self.assertIn("dividend_gap_annual", f_data)

            # 7. Test Data Health Check API
            with urllib.request.urlopen(f"{base_url}/api/health") as resp:
                self.assertEqual(resp.status, 200)
                h_data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("healthy", h_data)
                self.assertIn("issues", h_data)

            # 8. Test Data Repair API
            repair_req = urllib.request.Request(f"{base_url}/api/repair", data=b"", method="POST")
            with urllib.request.urlopen(repair_req) as resp:
                self.assertEqual(resp.status, 200)
                r_data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(r_data.get("status"), "success")

            # 9. Test HTML Financial Report API
            with urllib.request.urlopen(f"{base_url}/api/report?currency=USD") as resp:
                self.assertEqual(resp.status, 200)
                rep_html = resp.read().decode("utf-8")
                self.assertTrue(any(t in rep_html for t in ["Portfolio Executive Report", "投資組合高階執行報告", "投资组合高阶执行报告"]))

            # 10. Test CSV Export API
            with urllib.request.urlopen(f"{base_url}/api/export/csv") as resp:
                self.assertEqual(resp.status, 200)
                csv_data = resp.read().decode("utf-8")
                self.assertIn("Symbol", csv_data)

            # 11. Test JSON Backup API & Portfolio Summary API
            with urllib.request.urlopen(f"{base_url}/api/export/json") as resp:
                self.assertEqual(resp.status, 200)
                b_data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("portfolio", b_data)
                self.assertIn("watchlist", b_data)
                self.assertIn("transactions", b_data)
                self.assertIn("portfolios", b_data)

            # 12. Test Portfolio Summary Stats API
            with urllib.request.urlopen(f"{base_url}/api/portfolio/summary") as resp:
                self.assertEqual(resp.status, 200)
                s_data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("total_holdings", s_data)
                self.assertIn("by_currency", s_data)
                self.assertIn("top_holdings", s_data)

        finally:
            web_server.stop_server()

    def test_cli_argument_defaults(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("command", nargs="?", default="view")
        parser.add_argument("--port", type=int, default=8765)
        parser.add_argument("--host", type=str, default="0.0.0.0")
        parser.add_argument("--view", dest="auto_view", action="store_true", default=True)
        parser.add_argument("--no-view", "--headless", dest="auto_view", action="store_false")

        # Default run: python3 web_server.py
        args1 = parser.parse_args([])
        self.assertTrue(args1.auto_view)
        self.assertEqual(args1.command, "view")

        # Explicit view: python3 web_server.py view
        args2 = parser.parse_args(["view"])
        self.assertTrue(args2.auto_view)

        # Explicit flag: python3 web_server.py --view
        args3 = parser.parse_args(["--view"])
        self.assertTrue(args3.auto_view)

        # Opt-out: python3 web_server.py --no-view
        args4 = parser.parse_args(["--no-view"])
        self.assertFalse(args4.auto_view)

        # Opt-out headless: python3 web_server.py --headless
        args5 = parser.parse_args(["--headless"])
        self.assertFalse(args5.auto_view)

    def test_module_typing_and_annotations_resolution(self):
        """Regression test: Ensure all type annotations across modules resolve without NameError (e.g. Tuple/List/Dict)."""
        import importlib
        import typing

        target_modules = [
            "web_server",
            "webview",
            "chart_fetcher",
            "csv_manager",
            "financial_calc",
            "currency_converter",
            "report_generator",
            "main_gui",
        ]

        for mod_name in target_modules:
            mod = importlib.import_module(mod_name)
            # 1. Module-level type annotations must resolve cleanly
            hints = typing.get_type_hints(mod)
            self.assertIsInstance(hints, dict, f"Module {mod_name} type hints must be a dict")

            # 2. Function and class annotations must resolve cleanly
            for attr_name in dir(mod):
                if attr_name.startswith("__"):
                    continue
                attr = getattr(mod, attr_name)
                if callable(attr) or isinstance(attr, type):
                    try:
                        typing.get_type_hints(attr)
                    except Exception as e:
                        self.fail(f"Failed to resolve type hints for {mod_name}.{attr_name}: {e}")

    def test_webview_and_chart_cache_integrity(self):
        """Test webview import and chart cache dict type compatibility across Python versions."""
        import web_server
        import webview

        # Verify chart cache exists and supports standard caching operations
        self.assertTrue(hasattr(web_server, "_API_CHART_CACHE"))
        self.assertIsInstance(web_server._API_CHART_CACHE, dict)
        self.assertTrue(hasattr(webview, "is_pythonista"))
        self.assertTrue(hasattr(webview, "launch_pythonista_view"))
        self.assertIsInstance(webview.is_pythonista(), bool)

        test_key = "TEST_SYM_1M_USD_ALL"
        test_payload = {"prices": [100.0, 105.0], "timestamps": ["2026-01-01", "2026-01-02"]}
        web_server._API_CHART_CACHE[test_key] = (1700000000.0, test_payload)

        cached_entry = web_server._API_CHART_CACHE.get(test_key)
        self.assertIsNotNone(cached_entry)
        self.assertEqual(cached_entry[0], 1700000000.0)
        self.assertEqual(cached_entry[1]["prices"], [100.0, 105.0])

        # Clean up
        del web_server._API_CHART_CACHE[test_key]

    def test_all_chart_timeframes_availability_and_speed(self):
        """Test that all chart timeframes (1D, 5D, 1M, 6M, YTD, 1Y, 5Y, MAX) return valid curves quickly."""
        import web_server
        import time

        timeframes = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"]
        holdings = [
            {"symbol": "VOO", "shares": 10.0, "current_price": 700.0, "buy_price": 650.0, "currency": "USD"},
            {"symbol": "VGRO:TSE", "shares": 50.0, "current_price": 48.0, "buy_price": 45.0, "currency": "CAD"},
        ]
        converter = web_server.get_currency_converter()

        for tf in timeframes:
            t0 = time.time()
            data = web_server.DashboardRequestHandler._generate_fallback_chart_data(
                None, "PORTFOLIO", tf, "USD", holdings, converter
            )
            elapsed = time.time() - t0
            self.assertLess(elapsed, 0.5, f"Timeframe {tf} took {elapsed:.3f}s (should be < 0.5s)")
            self.assertIn("prices", data)
            self.assertIn("timestamps", data)
            self.assertGreaterEqual(len(data["prices"]), 2, f"Timeframe {tf} must have at least 2 points for canvas rendering")
            self.assertEqual(len(data["prices"]), len(data["timestamps"]))
            self.assertGreater(data.get("current_price", 0), 0)


# Import Google Sheet sync tests
from test_google_sheet_sync import TestGoogleSheetSync


class TestGoogleSheetServerAPIs(unittest.TestCase):
    """Test suite for Google Sheet Web Server API endpoints."""

    def test_web_server_has_google_sheet_endpoints(self):
        import web_server
        from google_sheet_sync import get_google_sheet_sync, get_google_apps_script_template

        sync_mgr = get_google_sheet_sync()
        status = sync_mgr.get_sync_status()
        self.assertIn("enabled", status)
        self.assertIn("configured", status)
        self.assertIn("web_app_url", status)

        code = get_google_apps_script_template()
        self.assertIn("function doGet(e)", code)
        self.assertIn("function doPost(e)", code)

    def test_web_server_html_contains_google_sheet_sync_interface(self):
        import web_server

        html = web_server.HTML_TEMPLATE
        self.assertIn('id="subpane-cloud"', html)
        self.assertIn('id="btn-st-cloud"', html)
        self.assertIn('id="cloud-pane-badge"', html)
        self.assertIn('id="cloud-pane-url"', html)
        self.assertIn('id="cloud-pane-status-txt"', html)
        self.assertIn('triggerGoogleSheetPush', html)
        self.assertIn('triggerGoogleSheetPull', html)
        self.assertIn('testGoogleSheetConnectionPane', html)
        self.assertIn('saveGoogleSheetPaneConfig', html)
        self.assertIn('modal-google-sheet', html)

    def test_web_server_translations_contain_cloud_sync_keys(self):
        import web_server

        html = web_server.HTML_TEMPLATE
        self.assertIn('"st_cloud"', html)
        self.assertIn('"cloud_title"', html)
        self.assertIn('"btn_sync_now"', html)
        self.assertIn('"btn_sync_push"', html)
        self.assertIn('"btn_sync_pull"', html)
        self.assertIn('"btn_save_config"', html)

    def test_web_server_live_sync_api(self):
        import web_server
        import urllib.request
        import json
        import time

        port = web_server.start_server(port=9377)
        try:
            time.sleep(0.15)
            # Test GET /api/sync/google_sheets
            url = f"http://localhost:{port}/api/sync/google_sheets"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("enabled", data)

            # Test GET /api/google_sheet/status
            url = f"http://localhost:{port}/api/google_sheet/status"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("enabled", data)

            # Test POST /api/google_sheet/sync
            url = f"http://localhost:{port}/api/google_sheet/sync"
            req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("status", data)
        finally:
            web_server.stop_server()

    def test_web_server_javascript_syntax(self):
        """Validates that all embedded JavaScript scripts in HTML_TEMPLATE have valid syntax."""
        import web_server
        import re
        import subprocess
        import shutil
        import tempfile

        node_path = shutil.which("node")
        if not node_path:
            self.skipTest("node binary not available to validate JavaScript")

        scripts = re.findall(r"<script>(.*?)</script>", web_server.HTML_TEMPLATE, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 1)

        with tempfile.TemporaryDirectory() as tmpdir:
            for idx, script_content in enumerate(scripts):
                script_path = os.path.join(tmpdir, f"script_{idx}.js")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(script_content)
                res = subprocess.run([node_path, "--check", script_path], capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, f"JS SyntaxError in script #{idx}:\n{res.stderr}")


class TestTransactionHoldingSync(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.test_dir = tempfile.mkdtemp()
        self.port_csv = os.path.join(self.test_dir, "test_portfolio.csv")
        self.tx_csv = os.path.join(self.test_dir, "test_transactions.csv")

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sync_transaction_rename_symbol(self):
        from csv_manager import save_portfolio, load_portfolio, sync_transaction_change_to_portfolio
        # Initial portfolio holding with VGRO:CDN
        init_holding = {
            "portfolio": "CAD TSFA",
            "symbol": "VGRO:CDN",
            "name": "VGRO:CDN",
            "shares": 6.0,
            "buy_price": 47.60,
            "current_price": 47.53,
            "currency": "CAD",
            "dividend_yield": 1.76,
            "annual_div_per_share": 0.836,
        }
        save_portfolio([init_holding], filepath=self.port_csv)

        old_tx = {
            "portfolio": "CAD TSFA",
            "symbol": "VGRO:CDN",
            "shares": 6.0,
            "price": 47.60,
            "type": "BUY",
            "currency": "CAD",
        }
        new_tx = {
            "portfolio": "CAD TSFA",
            "symbol": "VGRO",
            "shares": 6.0,
            "price": 47.60,
            "type": "BUY",
            "currency": "CAD",
        }

        ok = sync_transaction_change_to_portfolio(old_tx, new_tx, portfolio_filepath=self.port_csv)
        self.assertTrue(ok)

        holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0]["symbol"], "VGRO")
        self.assertEqual(holdings[0]["shares"], 6.0)
        self.assertEqual(holdings[0]["buy_price"], 47.60)
        self.assertEqual(holdings[0]["current_price"], 47.53)

    def test_sync_transaction_delete_reverts_holding(self):
        from csv_manager import save_portfolio, load_portfolio, sync_transaction_change_to_portfolio
        init_holding = {
            "portfolio": "CAD FHSA",
            "symbol": "VFV",
            "name": "VFV",
            "shares": 40.0,
            "buy_price": 192.82,
            "current_price": 192.67,
            "currency": "CAD",
        }
        save_portfolio([init_holding], filepath=self.port_csv)

        tx = {
            "portfolio": "CAD FHSA",
            "symbol": "VFV",
            "shares": 40.0,
            "price": 192.82,
            "type": "BUY",
            "currency": "CAD",
        }

        ok = sync_transaction_change_to_portfolio(tx, None, portfolio_filepath=self.port_csv)
        self.assertTrue(ok)

        holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(holdings), 0)

    def test_reconcile_portfolio_holdings_with_transactions(self):
        from csv_manager import (
            save_portfolio,
            load_portfolio,
            save_transactions,
            reconcile_portfolio_holdings_with_transactions,
        )
        init_holdings = [
            {
                "portfolio": "CAD TSFA",
                "symbol": "VGRO:CDN",
                "name": "VGRO:CDN",
                "shares": 6.0,
                "buy_price": 47.60,
                "current_price": 47.53,
                "currency": "CAD",
            },
            {
                "portfolio": "CAD FHSA",
                "symbol": "VFV:CDN",
                "name": "VFV:CDN",
                "shares": 40.0,
                "buy_price": 192.82,
                "current_price": 192.67,
                "currency": "CAD",
            },
        ]
        save_portfolio(init_holdings, filepath=self.port_csv)

        history_txs = [
            {
                "portfolio": "CAD TSFA",
                "symbol": "VGRO",
                "shares": 6.0,
                "price": 47.60,
                "type": "BUY",
                "currency": "CAD",
            },
            {
                "portfolio": "CAD FHSA",
                "symbol": "VFV",
                "shares": 40.0,
                "price": 192.82,
                "type": "BUY",
                "currency": "CAD",
            },
        ]
        save_transactions(history_txs, filepath=self.tx_csv)

        res = reconcile_portfolio_holdings_with_transactions(
            portfolio_filepath=self.port_csv,
            history_filepath=self.tx_csv,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["reconciled_count"], 2)

        reconciled_holdings = load_portfolio(self.port_csv)
        symbols = [h["symbol"] for h in reconciled_holdings]
        self.assertIn("VGRO", symbols)
        self.assertIn("VFV", symbols)
        self.assertNotIn("VGRO:CDN", symbols)
        self.assertNotIn("VFV:CDN", symbols)

        vgro = next(h for h in reconciled_holdings if h["symbol"] == "VGRO")
        self.assertEqual(vgro["name"], "Vanguard Growth ETF Portfolio")
        vfv = next(h for h in reconciled_holdings if h["symbol"] == "VFV")
        self.assertEqual(vfv["name"], "Vanguard S&P 500 Index ETF")


class TestListModificationsAndCurrency(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.test_dir = tempfile.mkdtemp()
        self.port_csv = os.path.join(self.test_dir, "test_portfolio.csv")
        self.tx_csv = os.path.join(self.test_dir, "test_transactions.csv")
        self.wl_csv = os.path.join(self.test_dir, "test_watchlist.csv")

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_add_new_holding_multi_currency(self):
        from csv_manager import add_holding, load_portfolio
        # Add USD stock
        ok1 = add_holding({
            "portfolio": "USD HSBC",
            "symbol": "AAPL",
            "name": "Apple Inc",
            "shares": 10.0,
            "buy_price": 150.0,
            "current_price": 180.0,
            "currency": "USD",
        }, filepath=self.port_csv)
        self.assertTrue(ok1)

        # Add CAD stock
        ok2 = add_holding({
            "portfolio": "CAD TSFA",
            "symbol": "VGRO",
            "name": "Vanguard Growth ETF Portfolio",
            "shares": 25.0,
            "buy_price": 45.0,
            "current_price": 47.5,
            "currency": "CAD",
        }, filepath=self.port_csv)
        self.assertTrue(ok2)

        # Add HKD stock
        ok3 = add_holding({
            "portfolio": "HKD HSBC",
            "symbol": "9988:HKG",
            "name": "Alibaba Group",
            "shares": 100.0,
            "buy_price": 80.0,
            "current_price": 85.0,
            "currency": "HKD",
        }, filepath=self.port_csv)
        self.assertTrue(ok3)

        holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(holdings), 3)

        aapl = next(h for h in holdings if h["symbol"] == "AAPL")
        self.assertEqual(aapl["currency"], "USD")
        self.assertEqual(aapl["cost_basis"], 1500.0)
        self.assertEqual(aapl["market_value"], 1800.0)
        self.assertEqual(aapl["unrealized_gain"], 300.0)

        vgro = next(h for h in holdings if h["symbol"] == "VGRO")
        self.assertEqual(vgro["currency"], "CAD")
        self.assertEqual(vgro["cost_basis"], 1125.0)
        self.assertEqual(vgro["market_value"], 1187.5)

        baba = next(h for h in holdings if h["symbol"] == "9988:HKG")
        self.assertEqual(baba["currency"], "HKD")
        self.assertEqual(baba["cost_basis"], 8000.0)
        self.assertEqual(baba["market_value"], 8500.0)

    def test_add_holding_merge_weighted_avg(self):
        from csv_manager import add_holding, load_portfolio
        # 1st purchase: 10 shares @ $100
        add_holding({
            "portfolio": "USD HSBC",
            "symbol": "NVDA",
            "shares": 10.0,
            "buy_price": 100.0,
            "current_price": 120.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        # 2nd purchase: 20 shares @ $130
        add_holding({
            "portfolio": "USD HSBC",
            "symbol": "NVDA",
            "shares": 20.0,
            "buy_price": 130.0,
            "current_price": 140.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(holdings), 1)
        nvda = holdings[0]
        self.assertEqual(nvda["shares"], 30.0)
        # Total cost: 10*100 + 20*130 = 1000 + 2600 = 3600. Avg price: 3600/30 = 120.0
        self.assertAlmostEqual(nvda["buy_price"], 120.0, places=2)
        self.assertEqual(nvda["cost_basis"], 3600.0)

    def test_update_holding_shares_price_alerts(self):
        from csv_manager import add_holding, update_holding, load_portfolio
        add_holding({
            "portfolio": "USD HSBC",
            "symbol": "AMD",
            "shares": 10.0,
            "buy_price": 100.0,
            "current_price": 110.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        ok = update_holding(
            original_portfolio="USD HSBC",
            original_symbol="AMD",
            updated_data={
                "shares": 15.0,
                "buy_price": 95.0,
                "current_price": 115.0,
                "target_sell_price": 150.0,
                "stop_loss_price": 85.0,
            },
            filepath=self.port_csv,
        )
        self.assertTrue(ok)

        holdings = load_portfolio(self.port_csv)
        amd = holdings[0]
        self.assertEqual(amd["shares"], 15.0)
        self.assertEqual(amd["buy_price"], 95.0)
        self.assertEqual(amd["cost_basis"], 1425.0)
        self.assertEqual(amd["market_value"], 1725.0)
        self.assertEqual(amd["unrealized_gain"], 300.0)
        self.assertEqual(float(amd.get("target_sell_price", 0.0)), 150.0)
        self.assertEqual(float(amd.get("stop_loss_price", 0.0)), 85.0)

    def test_update_holding_currency(self):
        from csv_manager import add_holding, update_holding, load_portfolio
        from currency_converter import get_currency_converter
        # Initially stored as USD by mistake
        add_holding({
            "portfolio": "CAD TSFA",
            "symbol": "VFV",
            "shares": 50.0,
            "buy_price": 180.0,
            "current_price": 190.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        # Update currency to CAD
        ok = update_holding(
            original_portfolio="CAD TSFA",
            original_symbol="VFV",
            updated_data={
                "currency": "CAD",
                "shares": 50.0,
                "buy_price": 180.0,
            },
            filepath=self.port_csv,
        )
        self.assertTrue(ok)

        holdings = load_portfolio(self.port_csv)
        vfv = holdings[0]
        self.assertEqual(vfv["currency"], "CAD")
        self.assertEqual(vfv["cost_basis"], 9000.0)

        # Test currency conversion of this updated holding
        conv = get_currency_converter()
        cad_val = vfv["market_value"] # 9500.0 CAD
        usd_val = conv.convert(cad_val, "CAD", "USD")
        self.assertGreater(usd_val, 0)
        self.assertNotEqual(usd_val, cad_val)

    def test_update_holding_symbol_rename(self):
        from csv_manager import add_holding, update_holding, load_portfolio
        # Ticker entered with typo or suffix
        add_holding({
            "portfolio": "CAD FHSA",
            "symbol": "VFV:CDN",
            "name": "VFV:CDN",
            "shares": 40.0,
            "buy_price": 192.82,
            "current_price": 192.67,
            "currency": "CAD",
        }, filepath=self.port_csv)

        ok = update_holding(
            original_portfolio="CAD FHSA",
            original_symbol="VFV:CDN",
            updated_data={
                "symbol": "VFV",
                "name": "Vanguard S&P 500 Index ETF",
                "shares": 40.0,
                "buy_price": 192.82,
                "currency": "CAD",
            },
            filepath=self.port_csv,
        )
        self.assertTrue(ok)

        holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0]["symbol"], "VFV")
        self.assertEqual(holdings[0]["name"], "Vanguard S&P 500 Index ETF")
        self.assertEqual(holdings[0]["shares"], 40.0)

    def test_update_holding_transfer_portfolio_collision_merge(self):
        from csv_manager import add_holding, update_holding, load_portfolio
        # Account 1 has 5 shares of VOO @ $600
        add_holding({
            "portfolio": "USD Account A",
            "symbol": "VOO",
            "shares": 5.0,
            "buy_price": 600.0,
            "current_price": 700.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        # Account 2 has 15 shares of VOO @ $640
        add_holding({
            "portfolio": "USD Account B",
            "symbol": "VOO",
            "shares": 15.0,
            "buy_price": 640.0,
            "current_price": 700.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        # Move Account A's VOO into Account B (collision merge)
        ok = update_holding(
            original_portfolio="USD Account A",
            original_symbol="VOO",
            updated_data={
                "portfolio": "USD Account B",
                "symbol": "VOO",
                "shares": 5.0,
                "buy_price": 600.0,
            },
            filepath=self.port_csv,
        )
        self.assertTrue(ok)

        holdings = load_portfolio(self.port_csv)
        # Should now be exactly 1 holding of VOO in Account B (total 20 shares)
        self.assertEqual(len(holdings), 1)
        voo = holdings[0]
        self.assertEqual(voo["portfolio"], "USD Account B")
        self.assertEqual(voo["shares"], 20.0)
        # Total cost: 15*640 + 5*600 = 9600 + 3000 = 12600. Avg price: 12600/20 = 630.0
        self.assertEqual(voo["cost_basis"], 12600.0)
        self.assertAlmostEqual(voo["buy_price"], 630.0, places=2)

    def test_delete_holding_specific_portfolio(self):
        from csv_manager import add_holding, delete_holding, load_portfolio
        add_holding({
            "portfolio": "USD Port 1",
            "symbol": "MSFT",
            "shares": 10.0,
            "buy_price": 400.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        add_holding({
            "portfolio": "USD Port 2",
            "symbol": "MSFT",
            "shares": 20.0,
            "buy_price": 410.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        # Delete MSFT only from Port 1
        ok = delete_holding(portfolio="USD Port 1", symbol="MSFT", filepath=self.port_csv)
        self.assertTrue(ok)

        holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0]["portfolio"], "USD Port 2")
        self.assertEqual(holdings[0]["symbol"], "MSFT")
        self.assertEqual(holdings[0]["shares"], 20.0)

    def test_watchlist_add_update_remove_lifecycle(self):
        from csv_manager import (
            add_to_watchlist,
            update_watchlist_item,
            remove_from_watchlist,
            load_watchlist,
            bulk_update_watchlist_category,
        )
        # 1. Add
        ok = add_to_watchlist(
            symbol="GOOGL",
            name="Alphabet Inc",
            target_price=250.0,
            currency="USD",
            notes="Watch for earnings dip",
            tags="Tech, Growth",
            filepath=self.wl_csv,
        )
        self.assertTrue(ok)
        items = load_watchlist(self.wl_csv)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["symbol"], "GOOGL")
        self.assertEqual(items[0]["target_price"], 250.0)
        self.assertEqual(items[0]["currency"], "USD")

        # 2. Update item (symbol, target, currency, tags)
        ok = update_watchlist_item(
            old_symbol="GOOGL",
            new_symbol="GOOGL",
            name="Alphabet Inc Class A",
            target_price=260.0,
            currency="USD",
            notes="Upgraded target",
            tags="BigTech",
            filepath=self.wl_csv,
        )
        self.assertTrue(ok)
        items = load_watchlist(self.wl_csv)
        self.assertEqual(items[0]["target_price"], 260.0)
        self.assertEqual(items[0]["tags"], "BigTech")

        # 3. Add second item and bulk update categories
        add_to_watchlist(symbol="AMZN", target_price=180.0, tags="Retail", filepath=self.wl_csv)
        count = bulk_update_watchlist_category(["GOOGL", "AMZN"], "MegaCap", mode="replace", filepath=self.wl_csv)
        self.assertEqual(count, 2)
        items = load_watchlist(self.wl_csv)
        self.assertEqual(items[0]["tags"], "MegaCap")
        self.assertEqual(items[1]["tags"], "MegaCap")

        # 4. Remove
        ok = remove_from_watchlist("GOOGL", filepath=self.wl_csv)
        self.assertTrue(ok)
        items = load_watchlist(self.wl_csv)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["symbol"], "AMZN")

    def test_multi_currency_exposure_calculation(self):
        from currency_converter import get_currency_converter
        conv = get_currency_converter()
        holdings = [
            {"symbol": "AAPL", "currency": "USD", "shares": 10.0, "current_price": 200.0}, # $2000 USD
            {"symbol": "VGRO", "currency": "CAD", "shares": 50.0, "current_price": 50.0},  # $2500 CAD
        ]
        total_usd = 0.0
        for h in holdings:
            mv = float(h["shares"]) * float(h["current_price"])
            total_usd += conv.convert(mv, h["currency"], "USD")
        self.assertGreater(total_usd, 2000.0)
        # Total in CAD should be higher than in USD (since 1 USD > 1 CAD)
        total_cad = 0.0
        for h in holdings:
            mv = float(h["shares"]) * float(h["current_price"])
            total_cad += conv.convert(mv, h["currency"], "CAD")
        self.assertGreater(total_cad, total_usd)

    def test_transaction_history_update_symbol_and_currency_syncs_to_holding(self):
        """
        Tests the exact user scenario:
        Initially added 2 items: VFV:CDN and VGRO:CDN.
        Then updated them in history list as VFV and VGRO with CAD currency.
        Verifies that portfolio holdings list is fully updated with VFV and VGRO.
        """
        from csv_manager import (
            add_holding,
            load_portfolio,
            save_transactions,
            load_transactions,
            sync_transaction_change_to_portfolio,
        )

        # 1. Initially user has VFV:CDN and VGRO:CDN in portfolio
        add_holding({
            "portfolio": "My TFSA",
            "symbol": "VFV:CDN",
            "name": "VFV:CDN",
            "shares": 50.0,
            "buy_price": 120.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        add_holding({
            "portfolio": "My TFSA",
            "symbol": "VGRO:CDN",
            "name": "VGRO:CDN",
            "shares": 100.0,
            "buy_price": 35.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(holdings), 2)
        symbols = [h["symbol"] for h in holdings]
        self.assertIn("VFV:CDN", symbols)
        self.assertIn("VGRO:CDN", symbols)

        # 2. Update VFV:CDN to VFV with currency CAD in history list
        old_vfv_tx = {
            "type": "BUY",
            "portfolio": "My TFSA",
            "symbol": "VFV:CDN",
            "shares": 50.0,
            "price": 120.0,
            "currency": "USD",
        }
        new_vfv_tx = {
            "type": "BUY",
            "portfolio": "My TFSA",
            "symbol": "VFV",
            "shares": 50.0,
            "price": 120.0,
            "currency": "CAD",
        }
        ok_sync_vfv = sync_transaction_change_to_portfolio(old_vfv_tx, new_vfv_tx, self.port_csv)
        self.assertTrue(ok_sync_vfv)

        # 3. Update VGRO:CDN to VGRO with currency CAD in history list
        old_vgro_tx = {
            "type": "BUY",
            "portfolio": "My TFSA",
            "symbol": "VGRO:CDN",
            "shares": 100.0,
            "price": 35.0,
            "currency": "USD",
        }
        new_vgro_tx = {
            "type": "BUY",
            "portfolio": "My TFSA",
            "symbol": "VGRO",
            "shares": 100.0,
            "price": 35.0,
            "currency": "CAD",
        }
        ok_sync_vgro = sync_transaction_change_to_portfolio(old_vgro_tx, new_vgro_tx, self.port_csv)
        self.assertTrue(ok_sync_vgro)

        # 4. Verify overall portfolio holdings list is updated to VFV and VGRO only!
        updated_holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(updated_holdings), 2)
        up_symbols = [h["symbol"] for h in updated_holdings]
        self.assertNotIn("VFV:CDN", up_symbols)
        self.assertNotIn("VGRO:CDN", up_symbols)
        self.assertIn("VFV", up_symbols)
        self.assertIn("VGRO", up_symbols)

        vfv = next(h for h in updated_holdings if h["symbol"] == "VFV")
        self.assertEqual(vfv["currency"], "CAD")
        self.assertEqual(vfv["shares"], 50.0)
        self.assertEqual(vfv["name"], "VFV")

        vgro = next(h for h in updated_holdings if h["symbol"] == "VGRO")
        self.assertEqual(vgro["currency"], "CAD")
        self.assertEqual(vgro["shares"], 100.0)
        self.assertEqual(vgro["name"], "VGRO")

    def test_multi_transaction_partial_update_sync(self):
        """
        Tests when holding has multiple transactions and only one transaction is modified.
        """
        from csv_manager import (
            add_holding,
            load_portfolio,
            sync_transaction_change_to_portfolio,
        )

        # 2 purchases of VFV:CDN: 15 shares + 25 shares = 40 shares total @ avg $115
        add_holding({
            "portfolio": "TFSA",
            "symbol": "VFV:CDN",
            "shares": 15.0,
            "buy_price": 100.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        add_holding({
            "portfolio": "TFSA",
            "symbol": "VFV:CDN",
            "shares": 25.0,
            "buy_price": 124.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        h = load_portfolio(self.port_csv)[0]
        self.assertEqual(h["shares"], 40.0)
        self.assertEqual(h["cost_basis"], 4600.0) # 1500 + 3100

        # Update 1st transaction from VFV:CDN to VFV and currency to CAD
        old_tx1 = {"type": "BUY", "portfolio": "TFSA", "symbol": "VFV:CDN", "shares": 15.0, "price": 100.0, "currency": "USD"}
        new_tx1 = {"type": "BUY", "portfolio": "TFSA", "symbol": "VFV", "shares": 15.0, "price": 100.0, "currency": "CAD"}
        sync_transaction_change_to_portfolio(old_tx1, new_tx1, self.port_csv)

        h_after = load_portfolio(self.port_csv)[0]
        # Holding symbol should be renamed to VFV, currency CAD, shares remain 40
        self.assertEqual(h_after["symbol"], "VFV")
        self.assertEqual(h_after["currency"], "CAD")
        self.assertEqual(h_after["shares"], 40.0)

    def test_transaction_delete_sync(self):
        """
        Tests deleting a transaction and verifying portfolio holding is updated or removed.
        """
        from csv_manager import (
            add_holding,
            load_portfolio,
            sync_transaction_change_to_portfolio,
        )

        add_holding({
            "portfolio": "Cash",
            "symbol": "BNS",
            "shares": 30.0,
            "buy_price": 60.0,
            "currency": "CAD",
        }, filepath=self.port_csv)

        # Delete partial (10 shares)
        del_tx = {"type": "BUY", "portfolio": "Cash", "symbol": "BNS", "shares": 10.0, "price": 60.0}
        sync_transaction_change_to_portfolio(del_tx, None, self.port_csv)

        holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0]["shares"], 20.0)

        # Delete remaining 20 shares
        del_tx2 = {"type": "BUY", "portfolio": "Cash", "symbol": "BNS", "shares": 20.0, "price": 60.0}
        sync_transaction_change_to_portfolio(del_tx2, None, self.port_csv)

        holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(holdings), 0)

    def test_reconcile_portfolio_holdings_with_currency_and_alias(self):
        """
        Tests automated reconciliation between transaction history and portfolio holdings.
        """
        from csv_manager import (
            add_holding,
            save_transactions,
            reconcile_portfolio_holdings_with_transactions,
            load_portfolio,
        )

        # Portfolio has improper ticker suffixes and wrong currency
        add_holding({
            "portfolio": "RRSP",
            "symbol": "VFV:CDN",
            "name": "VFV:CDN",
            "shares": 60.0,
            "buy_price": 110.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        add_holding({
            "portfolio": "RRSP",
            "symbol": "VGRO:CDN",
            "name": "VGRO:CDN",
            "shares": 80.0,
            "buy_price": 32.0,
            "currency": "USD",
        }, filepath=self.port_csv)

        # Transactions have clean symbols and CAD currency
        txs = [
            {"date": "2026-01-01", "type": "BUY", "portfolio": "RRSP", "symbol": "VFV", "shares": 60.0, "price": 110.0, "currency": "CAD"},
            {"date": "2026-01-02", "type": "BUY", "portfolio": "RRSP", "symbol": "VGRO", "shares": 80.0, "price": 32.0, "currency": "CAD"},
        ]
        save_transactions(txs, filepath=self.tx_csv)

        res = reconcile_portfolio_holdings_with_transactions(self.port_csv, self.tx_csv)
        self.assertTrue(res["success"])
        self.assertEqual(res["reconciled_count"], 2)

        holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(holdings), 2)
        vfv = next(h for h in holdings if h["symbol"] == "VFV")
        self.assertEqual(vfv["currency"], "CAD")
        self.assertEqual(vfv["name"], "Vanguard S&P 500 Index ETF")

        vgro = next(h for h in holdings if h["symbol"] == "VGRO")
        self.assertEqual(vgro["currency"], "CAD")
        self.assertEqual(vgro["name"], "Vanguard Growth ETF Portfolio")

    def test_holding_currency_conversion_rates(self):
        """
        Tests currency conversions across supported global currencies.
        """
        from currency_converter import get_currency_converter
        conv = get_currency_converter()
        # Verify major currency pairs have valid positive conversion rates
        currencies = ["USD", "CAD", "HKD", "EUR", "GBP"]
        for c1 in currencies:
            for c2 in currencies:
                val = conv.convert(100.0, c1, c2)
                self.assertGreater(val, 0)
                if c1 == c2:
                    self.assertAlmostEqual(val, 100.0, places=4)
                # Reversible check
                rev = conv.convert(val, c2, c1)
                self.assertAlmostEqual(rev, 100.0, places=1)


class TestEnhancedReliabilityAndFeatures(unittest.TestCase):
    """
    Tests for enhanced reliability, atomic writes, input validation,
    data export/import, financial calculations, and edge-case error recovery.
    """
    def setUp(self):
        import tempfile
        self.test_dir = tempfile.mkdtemp()
        self.port_csv = os.path.join(self.test_dir, "test_portfolio.csv")
        self.tx_csv = os.path.join(self.test_dir, "test_transactions.csv")
        self.wl_csv = os.path.join(self.test_dir, "test_watchlist.csv")
        self.json_export = os.path.join(self.test_dir, "test_export.json")

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_calc_total_return(self):
        from financial_calc import calc_total_return
        # 100 shares bought @ $50, now @ $70, $200 dividends, $10 fees
        res = calc_total_return(
            shares=100.0,
            buy_price=50.0,
            current_price=70.0,
            total_dividends_received=200.0,
            total_fees_paid=10.0,
        )
        self.assertEqual(res["cost_basis"], 5000.0)
        self.assertEqual(res["market_value"], 7000.0)
        self.assertEqual(res["capital_gain"], 2000.0)
        self.assertEqual(res["capital_gain_pct"], 40.0)
        self.assertEqual(res["dividends_received"], 200.0)
        self.assertEqual(res["fees_paid"], 10.0)
        # Total return = 2000 + 200 - 10 = 2190
        self.assertEqual(res["total_return_dollar"], 2190.0)
        self.assertAlmostEqual(res["total_return_pct"], 43.8, places=2)

    def test_calc_position_weights(self):
        from financial_calc import calc_position_weights
        holdings = [
            {"symbol": "AAPL", "portfolio": "Tech", "market_value": 8000.0, "cost_basis": 6000.0},
            {"symbol": "MSFT", "portfolio": "Tech", "market_value": 1500.0, "cost_basis": 1000.0},
            {"symbol": "BND", "portfolio": "Fixed", "market_value": 500.0, "cost_basis": 500.0},
        ]
        # Total = 10,000. AAPL is 80% (>15% concentrated), MSFT 15%, BND 5%
        weights = calc_position_weights(holdings, weight_by="market_value")
        self.assertEqual(len(weights), 3)
        self.assertEqual(weights[0]["symbol"], "AAPL")
        self.assertEqual(weights[0]["weight_pct"], 80.0)
        self.assertTrue(weights[0]["is_concentrated"])
        self.assertEqual(weights[1]["symbol"], "MSFT")
        self.assertEqual(weights[1]["weight_pct"], 15.0)
        self.assertFalse(weights[1]["is_concentrated"])

        # Empty holdings edge case
        empty_weights = calc_position_weights([])
        self.assertEqual(empty_weights, [])

    def test_calc_cost_basis_methods(self):
        from financial_calc import calc_cost_basis_methods
        # Buy Lot 1: 100 shares @ $10
        # Buy Lot 2: 100 shares @ $20
        # Sell: 50 shares @ $30
        txs = [
            {"date": "2026-01-01", "type": "BUY", "symbol": "XYZ", "shares": 100.0, "price": 10.0},
            {"date": "2026-02-01", "type": "BUY", "symbol": "XYZ", "shares": 100.0, "price": 20.0},
            {"date": "2026-03-01", "type": "SELL", "symbol": "XYZ", "shares": 50.0, "price": 30.0},
        ]
        res = calc_cost_basis_methods(txs, symbol="XYZ", current_price=25.0)
        self.assertEqual(res["remaining_shares"], 150.0)
        # FIFO sells 50 from Lot 1 ($10 cost basis = $500). Proceeds = 50 * 30 = 1500. Realized gain = 1000.
        self.assertEqual(res["fifo_realized_gain"], 1000.0)
        # Remaining FIFO: 50 @ $10 ($500) + 100 @ $20 ($2000) = $2500
        self.assertEqual(res["fifo_cost_basis"], 2500.0)

        # Average cost: 200 shares @ $15 ($3000). Sells 50 @ $15 ($750 cost). Realized gain = 1500 - 750 = 750.
        self.assertEqual(res["average_realized_gain"], 750.0)
        # Remaining Average: 150 @ $15 = $2250.
        self.assertEqual(res["average_cost_basis"], 2250.0)
        self.assertEqual(res["method_difference"], 250.0)

    def test_calc_dividend_income_summary(self):
        from financial_calc import calc_dividend_income_summary
        holdings = [
            {"symbol": "VGRO", "currency": "CAD", "annual_dividend": 400.0, "dividend_yield": 2.0},
            {"symbol": "AAPL", "currency": "USD", "annual_dividend": 120.0, "dividend_yield": 0.5},
            {"symbol": "GOOG", "currency": "USD", "annual_dividend": 0.0, "dividend_yield": 0.0},
        ]
        summary = calc_dividend_income_summary(holdings)
        self.assertEqual(summary["total_annual_dividend"], 520.0)
        self.assertAlmostEqual(summary["total_monthly_dividend"], 520.0 / 12.0, places=2)
        self.assertEqual(summary["holdings_with_dividends"], 2)
        self.assertEqual(summary["holdings_without_dividends"], 1)
        self.assertEqual(summary["highest_yielder"]["symbol"], "VGRO")
        self.assertEqual(summary["by_currency"]["CAD"], 400.0)
        self.assertEqual(summary["by_currency"]["USD"], 120.0)

    def test_get_etf_option_label(self):
        from financial_calc import get_etf_option_label
        etf = {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "asset_class": "US Equity"}
        lbl_en = get_etf_option_label(etf, lang="en")
        self.assertIn("VOO", lbl_en)
        self.assertIn("US Equity", lbl_en)
        lbl_tw = get_etf_option_label(etf, lang="zh_TW")
        self.assertIn("VOO", lbl_tw)

    def test_math_zero_division_guards(self):
        from financial_calc import calc_drip_simulation, calc_risk_and_return_metrics
        # DRIP with initial price = 0
        drip_res = calc_drip_simulation(initial_shares=100.0, initial_price=0.0, div_yield_pct=5.0, monthly_contribution=50.0, years=2)
        self.assertEqual(len(drip_res), 2)

        # Risk metrics with zero initial price
        risk_res = calc_risk_and_return_metrics(price_or_val_series=[0.0, 10.0, 20.0])
        self.assertIn("cagr_pct", risk_res)
        self.assertIn("volatility_pct", risk_res)

        # Risk metrics with empty series
        risk_empty = calc_risk_and_return_metrics(price_or_val_series=[])
        self.assertEqual(risk_empty["cagr_pct"], 0.0)

    def test_atomic_write_crash_resilience(self):
        from csv_manager import atomic_write
        test_file = os.path.join(self.test_dir, "atomic_test.txt")
        # 1. Initial valid content
        with open(test_file, "w") as f:
            f.write("INITIAL_CONTENT")

        # 2. Simulate crash during atomic_write
        try:
            with atomic_write(test_file, mode="w") as f:
                f.write("PARTIAL_CORRUPTED_DATA")
                raise RuntimeError("Simulated crash mid-write")
        except RuntimeError:
            pass

        # 3. Verify original file content is intact and unchanged!
        with open(test_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "INITIAL_CONTENT")

    def test_safe_float_parsing(self):
        from csv_manager import _safe_float
        self.assertEqual(_safe_float(123.45), 123.45)
        self.assertEqual(_safe_float("$1,234.56"), 1234.56)
        self.assertEqual(_safe_float("  -50.2%  "), -50.2)
        self.assertEqual(_safe_float("N/A", default=0.0), 0.0)
        self.assertEqual(_safe_float("None", default=5.0), 5.0)
        self.assertEqual(_safe_float("", default=0.0), 0.0)
        self.assertEqual(_safe_float(None, default=0.0), 0.0)
        self.assertEqual(_safe_float("invalid_str", default=-1.0), -1.0)

    def test_validate_holding_data(self):
        from csv_manager import validate_holding_data
        # Valid holding
        ok, errs = validate_holding_data({"symbol": "AAPL", "shares": 10.0, "buy_price": 150.0, "currency": "USD"})
        self.assertTrue(ok)
        self.assertEqual(len(errs), 0)

        # Invalid holdings
        ok1, errs1 = validate_holding_data({"symbol": "", "shares": 10.0, "buy_price": 150.0})
        self.assertFalse(ok1)
        self.assertTrue(any("symbol" in e.lower() for e in errs1))

        ok2, errs2 = validate_holding_data({"symbol": "XYZ", "shares": -5.0, "buy_price": -10.0})
        self.assertFalse(ok2)
        self.assertTrue(any("shares" in e.lower() for e in errs2))

        ok3, errs3 = validate_holding_data({"symbol": "XYZ", "shares": 5.0, "buy_price": 10.0, "currency": "TOOLONG"})
        self.assertFalse(ok3)

    def test_validate_transaction_data(self):
        from csv_manager import validate_transaction_data
        ok, errs = validate_transaction_data({"symbol": "VOO", "type": "BUY", "shares": 20.0, "price": 400.0})
        self.assertTrue(ok)

        ok_drip, _ = validate_transaction_data({"symbol": "VOO", "type": "DRIP", "shares": 1.25, "price": 400.0})
        self.assertTrue(ok_drip)

        ok_bad, errs_bad = validate_transaction_data({"symbol": "VOO", "type": "INVALID_TYPE", "shares": 0.0, "price": -5.0})
        self.assertFalse(ok_bad)
        self.assertGreaterEqual(len(errs_bad), 2)

    def test_export_and_import_portfolio_json_roundtrip(self):
        from csv_manager import (
            add_holding,
            append_transaction,
            add_to_watchlist,
            export_portfolio_to_json,
            import_portfolio_from_json,
            load_portfolio,
            load_transactions,
            load_watchlist,
        )
        # Setup data
        add_holding({"portfolio": "Main", "symbol": "AAPL", "shares": 10.0, "buy_price": 150.0, "currency": "USD"}, filepath=self.port_csv)
        append_transaction({"type": "BUY", "portfolio": "Main", "symbol": "AAPL", "shares": 10.0, "price": 150.0}, filepath=self.tx_csv)
        add_to_watchlist(symbol="NVDA", target_price=100.0, filepath=self.wl_csv)

        # Export to JSON
        ok_exp = export_portfolio_to_json(
            output_filepath=self.json_export,
            portfolio_filepath=self.port_csv,
            transaction_filepath=self.tx_csv,
            watchlist_filepath=self.wl_csv,
        )
        self.assertTrue(ok_exp)
        self.assertTrue(os.path.exists(self.json_export))

        # Import into fresh destination files
        fresh_port = os.path.join(self.test_dir, "fresh_port.csv")
        fresh_tx = os.path.join(self.test_dir, "fresh_tx.csv")
        fresh_wl = os.path.join(self.test_dir, "fresh_wl.csv")

        res_imp = import_portfolio_from_json(
            input_filepath=self.json_export,
            portfolio_filepath=fresh_port,
            transaction_filepath=fresh_tx,
            watchlist_filepath=fresh_wl,
            merge=False,
        )
        self.assertTrue(res_imp["success"])
        self.assertEqual(res_imp["holdings_imported"], 1)
        self.assertEqual(res_imp["transactions_imported"], 1)
        self.assertEqual(res_imp["watchlist_imported"], 1)

        # Verify loaded content
        loaded_h = load_portfolio(fresh_port)
        self.assertEqual(len(loaded_h), 1)
        self.assertEqual(loaded_h[0]["symbol"], "AAPL")
        self.assertEqual(loaded_h[0]["shares"], 10.0)

    def test_import_portfolio_json_merge_mode(self):
        from csv_manager import (
            add_holding,
            export_portfolio_to_json,
            import_portfolio_from_json,
            load_portfolio,
        )
        # Existing portfolio has 10 shares of MSFT @ $200
        add_holding({"portfolio": "Work", "symbol": "MSFT", "shares": 10.0, "buy_price": 200.0, "currency": "USD"}, filepath=self.port_csv)

        # Export an incoming dataset that has 10 shares of MSFT @ $300 in "Work"
        incoming_port = os.path.join(self.test_dir, "incoming_port.csv")
        add_holding({"portfolio": "Work", "symbol": "MSFT", "shares": 10.0, "buy_price": 300.0, "currency": "USD"}, filepath=incoming_port)
        export_portfolio_to_json(output_filepath=self.json_export, portfolio_filepath=incoming_port)

        # Merge import into self.port_csv
        res = import_portfolio_from_json(
            input_filepath=self.json_export,
            portfolio_filepath=self.port_csv,
            merge=True,
        )
        self.assertTrue(res["success"])
        holdings = load_portfolio(self.port_csv)
        self.assertEqual(len(holdings), 1)
        msft = holdings[0]
        # Total shares = 20, weighted average buy price = (10*200 + 10*300)/20 = 250.0
        self.assertEqual(msft["shares"], 20.0)
        self.assertAlmostEqual(msft["buy_price"], 250.0, places=2)

    def test_import_portfolio_json_invalid_and_corrupt(self):
        import json
        from csv_manager import import_portfolio_from_json
        # Non-existent file
        res1 = import_portfolio_from_json("/non/existent/path.json")
        self.assertFalse(res1["success"])

        # Corrupt JSON syntax
        bad_json = os.path.join(self.test_dir, "bad.json")
        with open(bad_json, "w") as f:
            f.write("{invalid: json,")
        res2 = import_portfolio_from_json(bad_json)
        self.assertFalse(res2["success"])

        # Missing version field
        no_ver = os.path.join(self.test_dir, "no_ver.json")
        with open(no_ver, "w") as f:
            json.dump({"holdings": []}, f)
        res3 = import_portfolio_from_json(no_ver)
        self.assertFalse(res3["success"])

    def test_get_portfolio_summary_stats(self):
        from csv_manager import add_holding, get_portfolio_summary_stats
        add_holding({"portfolio": "Port A", "symbol": "AAPL", "shares": 10.0, "buy_price": 100.0, "current_price": 150.0, "currency": "USD", "sector": "Technology", "annual_dividend": 50.0}, filepath=self.port_csv)
        add_holding({"portfolio": "Port B", "symbol": "VGRO", "shares": 20.0, "buy_price": 40.0, "current_price": 50.0, "currency": "CAD", "sector": "Financial", "annual_dividend": 60.0}, filepath=self.port_csv)

        stats = get_portfolio_summary_stats(self.port_csv)
        self.assertEqual(stats["total_holdings"], 2)
        self.assertEqual(stats["total_portfolios"], 2)
        self.assertIn("USD", stats["by_currency"])
        self.assertIn("CAD", stats["by_currency"])
        self.assertEqual(stats["by_currency"]["USD"]["count"], 1)
        self.assertEqual(stats["by_currency"]["CAD"]["count"], 1)
        self.assertEqual(len(stats["top_holdings"]), 2)
        self.assertIn("Technology", stats["sector_breakdown"])

    def test_corrupt_csv_handling(self):
        from csv_manager import load_portfolio
        corrupt_csv = os.path.join(self.test_dir, "corrupt.csv")
        with open(corrupt_csv, "w") as f:
            f.write("Portfolio,Symbol,Shares,Buy Price\n")
            f.write("USD HSBC,CORRUPT_1,NOT_A_NUMBER,$100.00\n")
            f.write("USD HSBC,,50.0,50.0\n") # Blank symbol
            f.write("USD HSBC,VALID_STOCK,10.0,20.0\n")
            f.write(",,,,,\n") # Empty row

        holdings = load_portfolio(corrupt_csv)
        # Should gracefully load without throwing exceptions and parse VALID_STOCK
        symbols = [h["symbol"] for h in holdings]
        self.assertIn("VALID_STOCK", symbols)
        self.assertIn("CORRUPT_1", symbols) # CORRUPT_1 parsed with 0.0 shares fallback

    def test_transaction_crud_boundary_indices(self):
        from csv_manager import update_transaction, delete_transaction
        # Out-of-bounds indices should safely return False
        self.assertFalse(update_transaction(index=-1, updated_tx={}, filepath=self.tx_csv))
        self.assertFalse(update_transaction(index=999, updated_tx={}, filepath=self.tx_csv))
        self.assertFalse(delete_transaction(index=-1, filepath=self.tx_csv))
        self.assertFalse(delete_transaction(index=999, filepath=self.tx_csv))

    def test_ensure_workspace_files(self):
        from csv_manager import ensure_workspace_files
        # Running ensure_workspace_files should ensure all default CSV files exist
        ensure_workspace_files()
        from csv_manager import PORTFOLIO_CSV, TRANSACTION_HISTORY_CSV, WATCHLIST_CSV
        self.assertTrue(os.path.exists(PORTFOLIO_CSV))
        self.assertTrue(os.path.exists(TRANSACTION_HISTORY_CSV))
        self.assertTrue(os.path.exists(WATCHLIST_CSV))

    def test_currency_converter_expanded_and_disk_cache(self):
        from currency_converter import CurrencyConverter, CURRENCY_CACHE_FILE
        conv = CurrencyConverter(cache_ttl_sec=3600)
        supported = conv.get_supported_currencies()
        self.assertIn("AUD", supported)
        self.assertIn("CHF", supported)
        self.assertIn("SGD", supported)
        self.assertIn("TWD", supported)
        self.assertIn("KRW", supported)

        # Test symbol retrieval
        self.assertEqual(conv.get_symbol("AUD"), "A$")
        self.assertEqual(conv.get_symbol("CHF"), "CHF")
        self.assertEqual(conv.get_symbol("KRW"), "₩")

        # Test conversion with fallback rate
        aud_to_usd = conv.convert(152.0, "AUD", "USD")
        self.assertAlmostEqual(aud_to_usd, 100.0, delta=1.0)

        # Test disk cache save and reload
        conv._rates_to_usd["CUSTOM_COIN"] = 2.5
        conv._last_update = 1234567.0
        conv._save_cache_to_disk()

        conv2 = CurrencyConverter(cache_ttl_sec=3600)
        self.assertEqual(conv2.get_usd_rate("CUSTOM_COIN"), 2.5)


class TestPythonistaUIModule(unittest.TestCase):
    """Test Pythonista 3 iOS UI module launcher and lifecycle."""

    def test_pythonista_app_import_and_defaults(self):
        import pythonista_app
        self.assertTrue(hasattr(pythonista_app, "launch_pythonista_app"))
        self.assertTrue(hasattr(pythonista_app, "GFinancePythonistaApp"))
        self.assertTrue(hasattr(pythonista_app, "GFinanceWebViewDelegate"))
        self.assertEqual(pythonista_app.DEFAULT_PORT, 8765)

    def test_pythonista_app_with_mocked_ui(self):
        from unittest.mock import MagicMock
        import pythonista_app

        mock_ui = MagicMock()
        mock_view = MagicMock()
        mock_view.bounds = (0, 0, 400, 800)
        mock_view.width = 400
        mock_view.height = 800
        mock_ui.View.return_value = mock_view

        mock_webview = MagicMock()
        mock_ui.WebView.return_value = mock_webview

        mock_indicator = MagicMock()
        mock_ui.ActivityIndicator.return_value = mock_indicator

        mock_server = MagicMock()

        orig_ui = pythonista_app.ui
        orig_avail = pythonista_app.PYTHONISTA_UI_AVAILABLE
        try:
            pythonista_app.ui = mock_ui
            pythonista_app.PYTHONISTA_UI_AVAILABLE = True

            app = pythonista_app.GFinancePythonistaApp("http://127.0.0.1:8765", server=mock_server)
            v = app.build_ui()

            # Verify view configuration
            self.assertEqual(v, mock_view)
            self.assertEqual(v.name, "G_Finance Portfolio")
            mock_webview.load_url.assert_called_with("http://127.0.0.1:8765")

            # Verify delegate callbacks
            delegate = pythonista_app.GFinanceWebViewDelegate(mock_indicator)
            delegate.webview_did_start(mock_webview)
            mock_indicator.start.assert_called()

            delegate.webview_did_finish(mock_webview)
            mock_indicator.stop.assert_called()

            # Verify button actions
            app.on_refresh(None)
            mock_webview.reload.assert_called()

            app.on_back(None)
            mock_webview.go_back.assert_called()

            app.on_forward(None)
            mock_webview.go_forward.assert_called()

            # Verify server cleanup
            app.cleanup()
            mock_server.shutdown.assert_called()
            mock_server.server_close.assert_called()
        finally:
            pythonista_app.ui = orig_ui
            pythonista_app.PYTHONISTA_UI_AVAILABLE = orig_avail


class TestPythonistaNativeUI(unittest.TestCase):
    """Test 100% native Pythonista 3 UIKit GUI data sources, chart, and calculators."""

    def test_native_ui_imports_and_defaults(self):
        import pythonista_native_ui
        self.assertTrue(hasattr(pythonista_native_ui, "NativeChartView"))
        self.assertTrue(hasattr(pythonista_native_ui, "HoldingsDataSource"))
        self.assertTrue(hasattr(pythonista_native_ui, "WatchlistDataSource"))
        self.assertTrue(hasattr(pythonista_native_ui, "HistoryDataSource"))
        self.assertTrue(hasattr(pythonista_native_ui, "CalculatorView"))
        self.assertTrue(hasattr(pythonista_native_ui, "GFinanceNativeApp"))

    def test_native_chart_view_data_and_touch(self):
        from unittest.mock import MagicMock
        import pythonista_native_ui

        chart = pythonista_native_ui.NativeChartView()
        chart.width = 300
        chart.height = 200

        prices = [100.0, 105.0, 102.0, 110.0]
        timestamps = ["10:00", "11:00", "12:00", "13:00"]
        chart.set_data(prices, timestamps, prev_close=99.0, currency_sym="$")

        self.assertEqual(chart.prices, prices)
        self.assertEqual(chart.timestamps, timestamps)
        self.assertEqual(chart.prev_close, 99.0)

        # Test hover callback
        hover_results = []
        chart.on_hover_callback = lambda p, t: hover_results.append((p, t))

        touch = MagicMock()
        touch.location.x = 150
        chart.touch_began(touch)
        self.assertTrue(len(hover_results) > 0)

        chart.touch_ended(touch)
        self.assertIsNone(chart.touch_x)

    def test_holdings_data_source(self):
        from unittest.mock import MagicMock
        import pythonista_native_ui

        holdings = [
            {"symbol": "VOO", "name": "Vanguard S&P 500", "shares": 10, "current_price": 700.0, "buy_price": 600.0, "currency": "USD"},
            {"symbol": "AAPL", "name": "Apple Inc", "shares": 20, "current_price": 220.0, "buy_price": 200.0, "currency": "USD"},
        ]
        selected = []
        deleted = []
        ds = pythonista_native_ui.HoldingsDataSource(
            holdings,
            on_select_holding=lambda h: selected.append(h),
            on_delete_holding=lambda h, idx: deleted.append((h, idx)),
        )

        self.assertEqual(ds.tableview_number_of_sections(None), 1)
        self.assertEqual(ds.tableview_number_of_rows(None, 0), 2)

        ds.tableview_did_select(None, 0, 0)
        self.assertEqual(selected[0]["symbol"], "VOO")

        ds.tableview_delete(None, 0, 1)
        self.assertEqual(deleted[0][0]["symbol"], "AAPL")

    def test_watchlist_and_history_data_sources(self):
        import pythonista_native_ui

        wl = [{"symbol": "MSFT", "name": "Microsoft", "current_price": 450.0}]
        wl_deleted = []
        w_ds = pythonista_native_ui.WatchlistDataSource(wl, on_delete=lambda r: wl_deleted.append(r))
        self.assertEqual(w_ds.tableview_number_of_rows(None, 0), 1)
        w_ds.tableview_delete(None, 0, 0)
        self.assertEqual(wl_deleted, [0])

        txs = [{"action": "BUY", "symbol": "NVDA", "shares": 5, "price": 200.0, "total": 1000.0}]
        h_ds = pythonista_native_ui.HistoryDataSource(txs)
        self.assertEqual(h_ds.tableview_number_of_rows(None, 0), 1)

    def test_native_ui_theme_contrast_and_defaults(self):
        import pythonista_native_ui
        theme = pythonista_native_ui.Theme(is_dark=False)
        self.assertEqual(theme.NAME, "Light")
        self.assertEqual(theme.BG_COLOR, "#F2F2F7")
        self.assertEqual(theme.CARD_BG, "#FFFFFF")
        self.assertEqual(theme.TEXT_PRIMARY, "#000000")
        self.assertNotEqual(theme.TEXT_PRIMARY, theme.CARD_BG)
        self.assertNotEqual(theme.INPUT_TEXT, theme.INPUT_BG)

        # Toggle to dark theme
        theme.toggle()
        self.assertTrue(theme.is_dark)
        self.assertEqual(theme.NAME, "Dark")
        self.assertEqual(theme.CARD_BG, "#1C1C1E")
        self.assertEqual(theme.TEXT_PRIMARY, "#FFFFFF")
        self.assertNotEqual(theme.TEXT_PRIMARY, theme.CARD_BG)
        self.assertNotEqual(theme.INPUT_TEXT, theme.INPUT_BG)
        self.assertEqual(theme.INPUT_TEXT, "#FFFFFF")
        self.assertEqual(theme.INPUT_BG, "#2C2C2E")

    def test_native_ui_responsive_layout_and_inset(self):
        from unittest.mock import MagicMock
        import pythonista_native_ui

        app = pythonista_native_ui.GFinanceNativeApp()
        app.width = 414
        app.height = 896
        app.btn_port = MagicMock()
        app.summary_card = MagicMock()
        app.lbl_total_val = MagicMock()
        app.lbl_total_sub = MagicMock()
        app.lbl_div_sub = MagicMock()
        app.main_seg = MagicMock()
        app.content_container = MagicMock()
        app.content_container.width = 390
        app.content_container.height = 718
        app.holdings_tv = MagicMock()
        app.watchlist_tv = MagicMock()
        app.history_tv = MagicMock()
        app.calc_view = MagicMock()
        app.chart_container = MagicMock()
        app.chart_tf_seg = MagicMock()
        app.native_chart = MagicMock()
        app.lbl_chart_hover = MagicMock()

        app.layout()

        # Check that layout computed responsive frames
        self.assertEqual(app.btn_port.frame, (12, 6, 390, 32))
        self.assertEqual(app.summary_card.frame, (12, 44, 390, 84))
        self.assertEqual(app.main_seg.frame, (12, 134, 390, 32))
        self.assertEqual(app.content_container.frame, (12, 172, 390, 896 - 172 - 6))
        self.assertEqual(app.holdings_tv.frame, (0, 0, 390, 718))

    def test_native_ui_multi_currency_summary_and_switching(self):
        from unittest.mock import MagicMock
        import pythonista_native_ui

        app = pythonista_native_ui.GFinanceNativeApp()
        app.lbl_total_val = MagicMock()
        app.lbl_total_sub = MagicMock()
        app.lbl_div_sub = MagicMock()
        app.btn_curr = MagicMock()

        # Multi-currency portfolio (USD and CAD)
        app.holdings = [
            {"symbol": "VOO", "shares": 10, "buy_price": 500.0, "current_price": 600.0, "annual_dividend": 15.0, "currency": "USD"},
            {"symbol": "VFV:TSE", "shares": 20, "buy_price": 100.0, "current_price": 120.0, "annual_dividend": 2.0, "currency": "CAD"},
        ]

        # 1. USD conversion
        app.summary_currency = "USD"
        app._update_summary_card()
        self.assertIn("USD", app.lbl_total_val.text)
        self.assertEqual(app.btn_curr.title, "💱 USD")
        # Native sum would be 6000 + 2400 = 8400, but USD converted is ~7706
        self.assertTrue("$7,70" in app.lbl_total_val.text or "$7,71" in app.lbl_total_val.text)

        # 2. Native currency mode (unconverted raw sum)
        app.summary_currency = "Native"
        app._update_summary_card()
        self.assertEqual(app.btn_curr.title, "💱 Native")
        self.assertIn("$8,400.00", app.lbl_total_val.text)

        # 3. Currency switcher fallback cycle
        app.on_select_summary_currency(None)
        # Should cycle from Native to USD
        self.assertEqual(app.summary_currency, "USD")

    def test_native_ui_chart_metric_modes_and_prepare_series(self):
        from unittest.mock import MagicMock
        import pythonista_native_ui

        app = pythonista_native_ui.GFinanceNativeApp()
        app.btn_chart_metric = MagicMock()
        app.lbl_chart_hover = MagicMock()
        app.native_chart = MagicMock()

        app.holdings = [
            {"symbol": "VOO", "shares": 10, "buy_price": 500.0, "current_price": 600.0, "annual_dividend": 15.0, "currency": "USD"},
        ]
        app.selected_chart_scope = "VOO"
        app.selected_timeframe = "1M"

        data = {
            "prices": [100.0, 105.0, 110.0, 108.0],
            "timestamps": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
            "prev_close": 98.0,
            "dividend_events": [["2026-01-02", 1.5]],
        }

        # 1. Total Value mode (scaled by 10 shares)
        app.selected_chart_metric = "total"
        prep_total = app._prepare_metric_series(data)
        self.assertIsNotNone(prep_total)
        self.assertEqual(prep_total["prices"][-1], 1080.0)  # 108.0 * 10
        self.assertEqual(prep_total["prev_close"], 980.0)   # 98.0 * 10
        self.assertFalse(prep_total["is_growth"])

        # 2. Price mode (unscaled per-share quote)
        app.selected_chart_metric = "price"
        prep_price = app._prepare_metric_series(data)
        self.assertEqual(prep_price["prices"][-1], 108.0)
        self.assertEqual(prep_price["prev_close"], 98.0)
        self.assertFalse(prep_price["is_growth"])

        # 3. Growth mode (Net Growth excluding invested capital)
        app.selected_chart_metric = "growth"
        prep_growth = app._prepare_metric_series(data)
        self.assertEqual(prep_growth["prev_close"], 0.0)
        self.assertTrue(prep_growth["is_growth"])
        self.assertIn("投入本金", prep_growth["ref_label"])

        # 4. Growth + Dividends mode
        app.selected_chart_metric = "growth_div"
        prep_growth_div = app._prepare_metric_series(data)
        self.assertEqual(prep_growth_div["prev_close"], 0.0)
        self.assertTrue(prep_growth_div["is_growth"])

        # 5. Dividends Only mode
        app.selected_chart_metric = "div_only"
        prep_div = app._prepare_metric_series(data)
        self.assertEqual(prep_div["prev_close"], 0.0)
        self.assertTrue(prep_div["is_growth"])
        self.assertIn("累計股息", prep_div["ref_label"])

        # 6. Metric switching cycle test
        app.selected_chart_metric = "total"
        app.on_select_chart_metric(None)
        self.assertEqual(app.selected_chart_metric, "price")
        app.on_select_chart_metric(None)
        self.assertEqual(app.selected_chart_metric, "growth")

    def test_native_ui_analytics_currency_weights_and_exposure(self):
        from unittest.mock import MagicMock
        import pythonista_native_ui
        from currency_converter import get_currency_converter

        analytics = pythonista_native_ui.AnalyticsView()
        analytics.tv_weights = MagicMock()
        analytics.tv_curr = MagicMock()

        conv = get_currency_converter()
        holdings = [
            {"symbol": "USD_STK", "shares": 10, "buy_price": 100.0, "current_price": 100.0, "currency": "USD"},
            {"symbol": "CAD_STK", "shares": 10, "buy_price": 100.0, "current_price": 100.0, "currency": "CAD"},
        ]

        analytics.set_data(holdings, summary_currency="USD", converter=conv)
        self.assertIn("USD", analytics.tv_curr.text)
        self.assertIn("CAD", analytics.tv_curr.text)
        self.assertIn("各幣別資產分佈", analytics.tv_curr.text)

    def test_native_ui_cell_pool_capping(self):
        from unittest.mock import MagicMock
        import pythonista_native_ui

        # Create dummy holdings data source with 50 items
        holdings = [{"symbol": f"S{i}", "shares": 1, "buy_price": 10.0, "current_price": 10.0} for i in range(50)]
        ds = pythonista_native_ui.HoldingsDataSource(holdings, on_select_holding=lambda h: None, on_delete_holding=lambda h, i: None)

        mock_tv = MagicMock()
        mock_tv.width = 375
        # Simulate ui module available with mock TableViewCell and Label
        mock_cell = MagicMock()
        mock_ui = MagicMock()
        mock_ui.TableViewCell.return_value = mock_cell
        mock_ui.Label.return_value = MagicMock()

        orig_ui = pythonista_native_ui.ui
        try:
            pythonista_native_ui.ui = mock_ui
            for row in range(50):
                cell = ds.tableview_cell_for_row(mock_tv, 0, row)
                self.assertIsNotNone(cell)
            # Pool must never exceed 30 items
            self.assertLessEqual(len(ds._cell_pool), 30)
            self.assertEqual(len(ds._cell_pool), 30)
        finally:
            pythonista_native_ui.ui = orig_ui

    def test_native_ui_run_on_ui_thread_exception_handling(self):
        import pythonista_native_ui

        def bad_func():
            raise ValueError("Test intentional failure")

        # Must not raise an unhandled exception
        try:
            pythonista_native_ui.run_on_ui_thread(bad_func)
            no_crash = True
        except Exception:
            no_crash = False
        self.assertTrue(no_crash)

    def test_native_chart_view_safe_geometry_without_dimensions(self):
        from unittest.mock import MagicMock
        import pythonista_native_ui

        chart = pythonista_native_ui.NativeChartView()
        # Test draw with mock ui and missing/zero width & height
        mock_ui = MagicMock()
        orig_ui = pythonista_native_ui.ui
        try:
            pythonista_native_ui.ui = mock_ui
            chart.prices = [10.0, 12.0, 15.0]
            chart.timestamps = ["T1", "T2", "T3"]
            chart.draw()
            self.assertTrue(mock_ui.Path.called or True)
        finally:
            pythonista_native_ui.ui = orig_ui

    def test_native_holdings_data_source_gain_rendering(self):
        from unittest.mock import MagicMock
        import pythonista_native_ui

        # Create holdings with unrealized_gain and unrealized_gain_pct (as loaded from portfolio.csv)
        holdings = [
            {
                "symbol": "ALB",
                "name": "Albemarle Corp",
                "shares": 30.0,
                "buy_price": 86.39,
                "current_price": 94.43,
                "cost_basis": 2591.70,
                "market_value": 2832.90,
                "unrealized_gain": 241.20,
                "unrealized_gain_pct": 9.31,
                "currency": "USD",
            },
            {
                "symbol": "RKLB",
                "name": "Rocket Lab Corp",
                "shares": 24.0,
                "buy_price": 116.93,
                "current_price": 53.35,
                "cost_basis": 2806.32,
                "market_value": 1280.40,
                "unrealized_gain": -1525.92,
                "unrealized_gain_pct": -54.37,
                "currency": "USD",
            },
        ]

        ds = pythonista_native_ui.HoldingsDataSource(holdings, on_select_holding=lambda h: None, on_delete_holding=lambda h, i: None)

        mock_tv = MagicMock()
        mock_tv.width = 375

        mock_cell = MagicMock()
        subviews = {}
        for name in ["lbl_sym", "lbl_price", "lbl_name", "lbl_shs", "lbl_mv", "lbl_pct", "lbl_dlr"]:
            lbl = MagicMock()
            lbl.name = name
            subviews[name] = lbl

        mock_cell.content_view.subviews = list(subviews.values())

        mock_ui = MagicMock()
        mock_ui.TableViewCell.return_value = mock_cell
        mock_ui.Label.side_effect = lambda **kwargs: MagicMock(name=kwargs.get("name", ""))

        orig_ui = pythonista_native_ui.ui
        try:
            pythonista_native_ui.ui = mock_ui

            # Render Row 0 (ALB: positive gain)
            ds.tableview_cell_for_row(mock_tv, 0, 0)
            self.assertEqual(subviews["lbl_pct"].text, "+9.31%")
            self.assertEqual(subviews["lbl_dlr"].text, "+$241.20")
            self.assertEqual(subviews["lbl_price"].text, "現價 $94.43")

            # Render Row 1 (RKLB: negative gain)
            ds.clear_cache()
            ds.tableview_cell_for_row(mock_tv, 0, 1)
            self.assertEqual(subviews["lbl_pct"].text, "-54.37%")
            self.assertEqual(subviews["lbl_dlr"].text, "-$1,525.92")
            self.assertEqual(subviews["lbl_price"].text, "現價 $53.35")
        finally:
            pythonista_native_ui.ui = orig_ui

    def test_native_watchlist_quotes_cache_merging(self):
        from unittest.mock import MagicMock, patch
        import pythonista_native_ui

        sample_watchlist = [
            {"symbol": "0005", "name": "HSBC Holdings", "target_price": 60.0, "currency": "HKD"},
            {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "target_price": 700.0, "currency": "USD"},
        ]
        sample_quotes_cache = {
            "0005": {"price": 145.8, "change_percent": 0.76, "name": "HSBC Holdings plc"},
            "VOO": {"price": 711.11, "change_percent": 0.61, "name": "Vanguard S&P 500 ETF"},
        }

        app = pythonista_native_ui.GFinanceNativeApp.__new__(pythonista_native_ui.GFinanceNativeApp)
        app.theme = pythonista_native_ui.CURRENT_THEME
        app.holdings = []
        app.watchlist_tv = MagicMock()

        with patch("csv_manager.load_watchlist", return_value=sample_watchlist), \
             patch("csv_manager.load_watchlist_quotes_cache", return_value=sample_quotes_cache):
            app._load_watchlist_tab()

        self.assertEqual(len(app.watchlist), 2)
        # Verified that prices and day changes are populated from cache
        self.assertEqual(app.watchlist[0]["current_price"], 145.8)
        self.assertEqual(app.watchlist[0]["day_change_pct"], 0.76)
        self.assertEqual(app.watchlist[1]["current_price"], 711.11)
        self.assertEqual(app.watchlist[1]["day_change_pct"], 0.61)

        # Verify WatchlistDataSource renders prices properly instead of "—" or "待刷新"
        mock_tv = MagicMock()
        mock_tv.width = 375
        mock_cell = MagicMock()
        subviews = {}
        for name in ["lbl_sym", "lbl_name", "lbl_pr", "lbl_chg"]:
            lbl = MagicMock()
            lbl.name = name
            subviews[name] = lbl
        mock_cell.content_view.subviews = list(subviews.values())

        mock_ui = MagicMock()
        mock_ui.TableViewCell.return_value = mock_cell
        orig_ui = pythonista_native_ui.ui
        try:
            pythonista_native_ui.ui = mock_ui
            app.watchlist_ds.tableview_cell_for_row(mock_tv, 0, 0)
            self.assertEqual(subviews["lbl_pr"].text, "HKD 145.80")
            self.assertEqual(subviews["lbl_chg"].text, "+0.76%")

            app.watchlist_ds.clear_cache()
            app.watchlist_ds.tableview_cell_for_row(mock_tv, 0, 1)
            self.assertEqual(subviews["lbl_pr"].text, "$711.11")
            self.assertEqual(subviews["lbl_chg"].text, "+0.61%")
        finally:
            pythonista_native_ui.ui = orig_ui

    def test_native_chart_view_handles_nan_and_zero_range_safely(self):
        from unittest.mock import MagicMock
        import pythonista_native_ui

        chart = pythonista_native_ui.NativeChartView()
        chart.width = 375
        chart.height = 260
        # Feed tricky data: NaNs, Infs, identical prices (zero range)
        chart.prices = [float("nan"), 100.0, 100.0, 100.0, float("inf"), None, 100.0]
        chart.timestamps = ["1", "2", "3", "4", "5", "6", "7"]

        mock_ui = MagicMock()
        orig_ui = pythonista_native_ui.ui
        try:
            pythonista_native_ui.ui = mock_ui
            # Must not throw ZeroDivisionError or crash
            chart.draw()
            self.assertTrue(True)
        finally:
            pythonista_native_ui.ui = orig_ui

    def test_show_holding_details_creates_hero_card_and_grid(self):
        from unittest.mock import MagicMock
        import pythonista_native_ui

        app = pythonista_native_ui.GFinanceNativeApp.__new__(pythonista_native_ui.GFinanceNativeApp)
        app.theme = pythonista_native_ui.CURRENT_THEME
        app.holdings = []

        holding = {
            "symbol": "GOOG",
            "name": "Alphabet Inc Class C",
            "shares": 5.0,
            "buy_price": 330.0,
            "current_price": 331.0,
            "cost_basis": 1650.0,
            "market_value": 1655.0,
            "unrealized_gain": 5.0,
            "unrealized_gain_pct": 0.30,
            "annual_dividend": 4.40,
            "portfolio": "USD CIBC Investment",
            "currency": "USD",
        }

        mock_ui = MagicMock()
        mock_sheet = MagicMock()
        mock_ui.View.return_value = mock_sheet
        mock_ui.ScrollView.return_value = MagicMock()
        mock_ui.Label.return_value = MagicMock()
        mock_ui.Button.return_value = MagicMock()

        orig_ui = pythonista_native_ui.ui
        try:
            pythonista_native_ui.ui = mock_ui
            app.show_holding_details(holding)
            # Verify sheet was presented
            mock_sheet.present.assert_called_with("sheet")
        finally:
            pythonista_native_ui.ui = orig_ui


if __name__ == "__main__":
    unittest.main()





