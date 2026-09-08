#!/usr/bin/env python3
"""
Automated Test Suite for Money Pro Bank Importer (HSBC & CIBC)
==============================================================
Tests all parsing, extraction, category inference, deduplication,
and Money Pro iOS CSV formatting logic across all supported bank export styles.
"""

import sys
import os
import unittest
import tempfile
import csv
from pathlib import Path

# Add script directory to sys.path
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

import moneypro_importer as mpi


class TestHelperFunctions(unittest.TestCase):
    """Tests amount cleaning, date parsing, payee extraction, and auto-categorization."""

    def test_clean_amount(self):
        self.assertEqual(mpi.clean_amount("123.45"), 123.45)
        self.assertEqual(mpi.clean_amount("-45.20"), -45.20)
        self.assertEqual(mpi.clean_amount("$1,234.56"), 1234.56)
        self.assertEqual(mpi.clean_amount("(50.00)"), -50.00)
        self.assertEqual(mpi.clean_amount("£25.50"), 25.50)
        self.assertEqual(mpi.clean_amount("€100.00"), 100.00)
        self.assertEqual(mpi.clean_amount("HK$ 500.00"), 500.00)
        self.assertEqual(mpi.clean_amount("1.234,56"), 1234.56)
        self.assertIsNone(mpi.clean_amount(""))
        self.assertIsNone(mpi.clean_amount("N/A"))
        self.assertIsNone(mpi.clean_amount(None))

    def test_parse_date_string(self):
        # ISO formats
        self.assertEqual(mpi.parse_date_string("2024-02-15"), "2024-02-15")
        self.assertEqual(mpi.parse_date_string("2024/02/15"), "2024-02-15")

        # DD/MM/YYYY
        self.assertEqual(mpi.parse_date_string("25/12/2023"), "2023-12-25")
        self.assertEqual(mpi.parse_date_string("15/02/2024", prefer_day_first=True), "2024-02-15")

        # DD-Mon-YYYY & textual dates
        self.assertEqual(mpi.parse_date_string("15-Feb-2024"), "2024-02-15")
        self.assertEqual(mpi.parse_date_string("15 Feb 2024"), "2024-02-15")
        self.assertEqual(mpi.parse_date_string("Feb 15, 2024"), "2024-02-15")

        # Compact YYYYMMDD
        self.assertEqual(mpi.parse_date_string("20240215"), "2024-02-15")

        # Invalid
        self.assertIsNone(mpi.parse_date_string("not_a_date"))
        self.assertIsNone(mpi.parse_date_string(""))

    def test_extract_payee_and_check(self):
        # Location stripping
        payee1, chk1 = mpi.extract_payee_and_check("TIM HORTONS #1234 TORONTO ON")
        self.assertEqual(payee1, "TIM HORTONS")
        self.assertEqual(chk1, "")

        # Prefix stripping
        payee2, chk2 = mpi.extract_payee_and_check("POS PURCHASE - COSTCO WHOLESALE #541 VANCOUVER BC CA")
        self.assertEqual(payee2, "COSTCO WHOLESALE")

        # Check extraction
        payee3, chk3 = mpi.extract_payee_and_check("CHEQUE #004523 DEPOSIT")
        self.assertEqual(chk3, "004523")

    def test_infer_category(self):
        self.assertEqual(mpi.infer_category("Loblaws Supermarket", "Loblaws"), "Groceries")
        self.assertEqual(mpi.infer_category("Starbucks Coffee", "Starbucks"), "Dining")
        self.assertEqual(mpi.infer_category("Shell Gas Station", "Shell"), "Transportation")
        self.assertEqual(mpi.infer_category("Toronto Hydro Bill", "Toronto Hydro"), "Utilities")
        self.assertEqual(mpi.infer_category("Amazon.ca Marketplace", "Amazon.ca"), "Shopping")
        self.assertEqual(mpi.infer_category("Netflix Monthly", "Netflix"), "Entertainment")
        self.assertEqual(mpi.infer_category("Shoppers Drug Mart", "Shoppers"), "Healthcare")
        self.assertEqual(mpi.infer_category("Payroll Direct Deposit ACME Corp", "Payroll"), "Income")

    def test_mcdonalds_and_custom_category_mapping(self):
        """Specifically verifies that 'McDonalds' and variants match 'Dining' category."""
        # Standard McDonalds in description
        self.assertEqual(mpi.infer_category("McDonalds #4321 Toronto ON", "McDonalds"), "Dining")
        self.assertEqual(mpi.infer_category("MCDONALDS", "MCDONALDS"), "Dining")
        self.assertEqual(mpi.infer_category("MCDONALD'S RESTAURANT", "MCDONALD'S"), "Dining")
        self.assertEqual(mpi.infer_category("PURCHASE - MCDONALDS", "MCDONALDS"), "Dining")

        # Custom mapping dictionary / file override
        custom_mapping = {
            "Dining:Fast Food": ["mcdonalds", "subway"],
            "Coffee": ["starbucks", "tim hortons"]
        }
        self.assertEqual(mpi.infer_category("McDonalds #4321", "McDonalds", mappings=custom_mapping), "Dining:Fast Food")
    def test_csv_category_mapping_file(self):
        """Verifies loading category rules directly from CSV file format."""
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("Keyword,Category\n")
            f.write("mcdonalds,Dining\n")
            f.write("mcdonald's,Dining\n")
            f.write("esso,Transportation\n")
            temp_csv = f.name

        try:
            mappings = mpi.load_category_mappings(temp_csv)
            self.assertIn("Dining", mappings)
            self.assertIn("Transportation", mappings)
            self.assertEqual(mpi.infer_category("MCDONALD'S RESTAURANT #102", "MCDONALD'S", mappings=mappings), "Dining")
            self.assertEqual(mpi.infer_category("ESSO GAS TORONTO", "ESSO", mappings=mappings), "Transportation")

            # Test saving back to CSV and reloading
            new_csv = temp_csv + ".re_saved.csv"
            mpi.save_category_mappings(mappings, new_csv)
            reloaded = mpi.load_category_mappings(new_csv)
            self.assertIn("Dining", reloaded)
            self.assertIn("mcdonalds", reloaded["Dining"])
            if os.path.exists(new_csv):
                os.remove(new_csv)
        finally:
            if os.path.exists(temp_csv):
                os.remove(temp_csv)

    def test_account_mapping_and_resolution(self):
        """Verifies loading account rules from CSV and resolving bank card/account names to Money Pro accounts."""
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("BankPattern,MoneyProAccount\n")
            f.write("4500********1234,My Primary Visa\n")
            f.write("9999,CIBC Joint Account\n")
            f.write("cibc_chequing,CIBC Smart Chequing\n")
            f.write("40-00-00 12345678,HSBC Premier Global\n")
            temp_csv = f.name

        try:
            mappings = mpi.load_account_mappings(temp_csv)
            self.assertEqual(len(mappings), 4)

            # Test 1: Full card pattern match
            acc1 = mpi.resolve_account_name(account_info="4500********1234", mappings=mappings)
            self.assertEqual(acc1, "My Primary Visa")

            # Test 2: Suffix match (9999)
            acc2 = mpi.resolve_account_name(raw_account="CIBC (...9999)", account_info="4500********9999", mappings=mappings)
            self.assertEqual(acc2, "CIBC Joint Account")

            # Test 3: Filename stem match
            acc3 = mpi.resolve_account_name(filename="cibc_chequing_statement", mappings=mappings)
            self.assertEqual(acc3, "CIBC Smart Chequing")

            # Test 4: HSBC preamble full pattern match
            acc4 = mpi.resolve_account_name(account_info="40-00-00 12345678", mappings=mappings)
            self.assertEqual(acc4, "HSBC Premier Global")

            # Test 5: User explicit override when no rule alias matches
            acc5 = mpi.resolve_account_name(default_account="Custom Savings Account", mappings=mappings)
            self.assertEqual(acc5, "Custom Savings Account")

            # Test 6: Save and reload account mappings CSV
            resaved_csv = temp_csv + ".resaved.csv"
            mpi.save_account_mappings(mappings, resaved_csv)
            reloaded_acc = mpi.load_account_mappings(resaved_csv)
            self.assertEqual(len(reloaded_acc), 4)
            self.assertEqual(reloaded_acc[0], ("4500********1234", "My Primary Visa"))
            if os.path.exists(resaved_csv):
                os.remove(resaved_csv)
        finally:
            if os.path.exists(temp_csv):
                os.remove(temp_csv)


class TestCIBCStatements(unittest.TestCase):
    """Tests CIBC parsing across headerless and header-based statement exports."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cibc_headerless_5_column(self):
        """Standard CIBC online banking download with 5 columns without headers."""
        csv_path = Path(self.temp_dir) / "cibc_credit_card.csv"
        content = (
            '"2024-02-10","TIM HORTONS #4321 TORONTO ON","4.50","","4500********1234"\n'
            '"2024-02-12","PAYMENT - THANK YOU / PAIEMENT MERCI","","250.00","4500********1234"\n'
            '"2024-02-14","AMAZON.CA","32.15","","4500********1234"\n'
        )
        csv_path.write_text(content, encoding="utf-8")

        parser = mpi.detect_parser(str(csv_path))
        self.assertIsInstance(parser, mpi.CIBCParser)

        txs = parser.parse(str(csv_path), auto_categorize=True)
        self.assertEqual(len(txs), 3)

        # First row: debit $4.50 -> Money Pro expense -4.50
        self.assertEqual(txs[0].date, "2024-02-10")
        self.assertEqual(txs[0].amount, -4.50)
        self.assertEqual(txs[0].payee, "TIM HORTONS")
        self.assertEqual(txs[0].category, "Dining")
        self.assertIn("1234", txs[0].account)

        # Second row: credit $250.00 -> Money Pro income +250.00
        self.assertEqual(txs[1].date, "2024-02-12")
        self.assertEqual(txs[1].amount, 250.00)

        # Third row: Amazon -> Shopping
        self.assertEqual(txs[2].amount, -32.15)
        self.assertEqual(txs[2].category, "Shopping")

    def test_cibc_with_headers(self):
        """CIBC CSV containing standard headers."""
        csv_path = Path(self.temp_dir) / "cibc_chequing.csv"
        content = (
            "Date,Description,Debit,Credit,Card Number\n"
            "2024-03-01,INTERAC E-TRANSFER RECEIVED,,100.00,00012345678\n"
            "2024-03-02,METRO GROCERY STORE,85.40,,00012345678\n"
        )
        csv_path.write_text(content, encoding="utf-8")

        parser = mpi.detect_parser(str(csv_path))
        self.assertIsInstance(parser, mpi.CIBCParser)

        txs = parser.parse(str(csv_path), default_account="CIBC Chequing")
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].amount, 100.00)
        self.assertEqual(txs[0].account, "CIBC Chequing")
        self.assertEqual(txs[1].amount, -85.40)
    def test_cibc_headerless_4_column(self):
        """CIBC 4-column headerless statement (Date, Description, Debit, Credit)."""
        csv_path = Path(self.temp_dir) / "cibc_4col.csv"
        content = (
            '"2024-03-10","TIM HORTONS","3.80",""\n'
            '"2024-03-11","PAYROLL DEPOSIT","","1850.00"\n'
        )
        csv_path.write_text(content, encoding="utf-8")
        parser = mpi.detect_parser(str(csv_path))
        self.assertIsInstance(parser, mpi.CIBCParser)
        txs = parser.parse(str(csv_path))
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].amount, -3.80)
        self.assertEqual(txs[1].amount, 1850.00)

    def test_cibc_single_amount_header(self):
        """CIBC statement with single signed amount column."""
        csv_path = Path(self.temp_dir) / "cibc_single_amt.csv"
        content = (
            "Date,Description,Amount\n"
            "2024-04-01,AMAZON.CA,-45.00\n"
            "2024-04-02,REFUND,20.00\n"
        )
        csv_path.write_text(content, encoding="utf-8")
        txs = mpi.CIBCParser().parse(str(csv_path))
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].amount, -45.00)
        self.assertEqual(txs[1].amount, 20.00)


class TestHSBCStatements(unittest.TestCase):
    """Tests HSBC parsing across UK, Global, and Canada/US exports."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_hsbc_uk_global_format(self):
        """HSBC UK / Global: Date, Payment Type, Details, Paid Out, Paid In, Balance."""
        csv_path = Path(self.temp_dir) / "hsbc_uk.csv"
        content = (
            "Date,Payment Type,Details,Paid Out,Paid In,Balance\n"
            "15/02/2024,VIS,TESCO STORES,45.20,,1250.00\n"
            "18/02/2024,CR,SALARY ACME LTD,,3200.00,4450.00\n"
            "20/02/2024,DD,BRITISH GAS,65.00,,4385.00\n"
        )
        csv_path.write_text(content, encoding="utf-8")

        parser = mpi.detect_parser(str(csv_path))
        self.assertIsInstance(parser, mpi.HSBCParser)

        txs = parser.parse(str(csv_path), default_account="HSBC UK Premier")
        self.assertEqual(len(txs), 3)

        # 15/02/2024 -> 2024-02-15
        self.assertEqual(txs[0].date, "2024-02-15")
        self.assertEqual(txs[0].amount, -45.20)
        self.assertEqual(txs[0].category, "Groceries")
        self.assertEqual(txs[0].account, "HSBC UK Premier")

        # Salary credit
        self.assertEqual(txs[1].date, "2024-02-18")
        self.assertEqual(txs[1].amount, 3200.00)
        self.assertEqual(txs[1].category, "Income")

        # British Gas DD
        self.assertEqual(txs[2].amount, -65.00)
        self.assertEqual(txs[2].category, "Utilities")

    def test_hsbc_hk_format(self):
        """HSBC Hong Kong: Date, Details, Withdrawal(HKD), Deposit(HKD), Balance(HKD)."""
        csv_path = Path(self.temp_dir) / "hsbc_hk.csv"
        content = (
            "Date,Details,Withdrawal(HKD),Deposit(HKD),Balance(HKD)\n"
            "05/03/2024,PARKnSHOP SUPERMARKET,320.50,,45000.00\n"
            "06/03/2024,SALARY,,28000.00,73000.00\n"
        )
        csv_path.write_text(content, encoding="utf-8")
        parser = mpi.detect_parser(str(csv_path))
        self.assertIsInstance(parser, mpi.HSBCParser)
        txs = parser.parse(str(csv_path))
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].amount, -320.50)
        self.assertEqual(txs[0].category, "Groceries")
        self.assertEqual(txs[1].amount, 28000.00)
        self.assertEqual(txs[1].category, "Income")

    def test_hsbc_with_metadata_preamble(self):
        """HSBC file with account metadata rows before the actual transaction table."""
        csv_path = Path(self.temp_dir) / "hsbc_preamble.csv"
        content = (
            "Account Name: JOHN DOE\n"
            "Account Number: 40-00-00 12345678\n"
            "Currency: CAD\n"
            "\n"
            "Date,Description,Amount,Balance\n"
            "2024-01-10,UBER TRIP,-24.50,1500.00\n"
            "2024-01-11,COFFEE SHOP,-5.25,1494.75\n"
        )
        csv_path.write_text(content, encoding="utf-8")

        parser = mpi.detect_parser(str(csv_path))
        self.assertIsInstance(parser, mpi.HSBCParser)

        txs = parser.parse(str(csv_path))
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].amount, -24.50)
        self.assertEqual(txs[0].category, "Transportation")
        self.assertIn("5678", txs[0].account)


class TestMoneyProExport(unittest.TestCase):
    """Verifies end-to-end processing and validation of Money Pro output CSV."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_pipeline_and_moneypro_csv_spec(self):
        # Create input CIBC file
        input_csv = Path(self.temp_dir) / "cibc_sample.csv"
        content = (
            "2024-02-20,ESSO GAS STATION,65.00,,4500********9999\n"
            "2024-02-15,WALMART SUPERSTORE,120.50,,4500********9999\n"
            "2024-02-15,WALMART SUPERSTORE,120.50,,4500********9999\n"  # Duplicate
        )
        input_csv.write_text(content, encoding="utf-8")

        output_csv = Path(self.temp_dir) / "moneypro_result.csv"

        count, bname, out_p = mpi.process_statement_file(
            input_path=str(input_csv),
            output_path=str(output_csv),
            bank="cibc",
            account="CIBC Visa Dividend",
            auto_categorize=True,
            dedup=True
        )

        # One duplicate dropped -> 2 unique transactions
        self.assertEqual(count, 2)
        self.assertEqual(bname, "CIBC")
        self.assertTrue(Path(out_p).exists())

        # Inspect resulting CSV file
        with open(out_p, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Check required Money Pro headers
        for h in mpi.MONEYPRO_HEADERS:
            self.assertIn(h, reader.fieldnames)

        # Transactions sorted chronologically (2024-02-15 before 2024-02-20)
        self.assertEqual(rows[0]["Date"], "2024-02-15")
        self.assertEqual(rows[0]["Amount"], "-120.50")
        self.assertEqual(rows[0]["Account"], "CIBC Visa Dividend")
        self.assertEqual(rows[0]["Category"], "Groceries")

        self.assertEqual(rows[1]["Date"], "2024-02-20")
        self.assertEqual(rows[1]["Amount"], "-65.00")
        self.assertEqual(rows[1]["Category"], "Transportation")


class TestIncomingAndTransferReview(unittest.TestCase):
    """Tests detection, keyword suggestion, rule saving, and review of incoming/transfer transactions."""

    def test_get_uncategorized_incoming_transactions(self):
        tx1 = mpi.Transaction("2026-03-01", 500.0, "E-TRANSFER FROM ALICE", account="CIBC Chequing", category="")
        tx2 = mpi.Transaction("2026-03-02", 1250.0, "PAYROLL ACME", account="CIBC Chequing", category="Salary")
        tx3 = mpi.Transaction("2026-03-03", -45.0, "MCDONALDS", account="CIBC Visa", category="")
        tx4 = mpi.Transaction("2026-03-04", 0.0, "FEE REVERSAL", account="CIBC Chequing", category="")
        tx5 = mpi.Transaction("2026-03-05", 25.50, "REFUND STORE", account="CIBC Visa", category="   ")

        uncat = mpi.get_uncategorized_incoming_transactions([tx1, tx2, tx3, tx4, tx5])
        # Only tx1 and tx5 are positive amounts with empty categories
        self.assertEqual(len(uncat), 2)
        self.assertIn(tx1, uncat)
        self.assertIn(tx5, uncat)
        self.assertNotIn(tx2, uncat)  # has category 'Salary'
        self.assertNotIn(tx3, uncat)  # negative amount (expense)
        self.assertNotIn(tx4, uncat)  # zero amount

    def test_suggest_rule_keyword(self):
        tx1 = mpi.Transaction("2026-03-01", 500.0, "Internet Banking E-TRANSFER 011388881438 Choi yin Li", payee="Choi yin Li")
        self.assertEqual(mpi.suggest_rule_keyword(tx1), "Choi yin Li")

        tx2 = mpi.Transaction("2026-03-02", 200.0, "Internet Banking INTERNET TRANSFER 000000108199", payee="Transaction")
        self.assertEqual(mpi.suggest_rule_keyword(tx2), "INTERNET TRANSFER")

        tx3 = mpi.Transaction("2026-03-03", 3000.0, "EMPLOYER PAYROLL DIRECT DEPOSIT", payee="")
        self.assertEqual(mpi.suggest_rule_keyword(tx3), "EMPLOYER PAYROLL DIRECT DEPOSIT")

    def test_add_category_rule_and_persistence(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("Keyword,Category\nmcdonalds,Dining\n")
            f_path = f.name

        try:
            mem_mappings = {"Dining": ["mcdonalds"]}
            mpi.add_category_rule("Choi yin Li", "Income: Transfer", mapping_path=f_path, category_mappings=mem_mappings)

            # Check in-memory update
            self.assertIn("Choi yin Li", mem_mappings["Income: Transfer"])

            # Check file update
            reloaded = mpi.load_category_mappings(f_path)
            self.assertIn("Income: Transfer", reloaded)
            self.assertIn("choi yin li", [k.lower() for k in reloaded["Income: Transfer"]])

            # Test duplicate prevention
            mpi.add_category_rule("Choi yin Li", "Income: Transfer", mapping_path=f_path, category_mappings=mem_mappings)
            with open(f_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
            self.assertEqual(content.count("Choi yin Li"), 1)
        finally:
            if os.path.exists(f_path):
                os.unlink(f_path)

    def test_category_suggestions_list(self):
        suggestions = mpi.get_all_category_suggestions({"Dining": ["mcdonalds"], "Groceries": ["loblaws"]})
        self.assertIn("Salary", suggestions)
        self.assertIn("Transfer", suggestions)
        self.assertIn("Interact", suggestions)
        self.assertIn("Dining", suggestions)
        self.assertIn("Groceries", suggestions)


def run_all_tests():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
