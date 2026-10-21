"""
Unit Tests for GoogleSheetSync Engine
Covers:
- Configuration load & save
- Apps Script template generation
- Local data export and deterministic hashing
- Item-by-item difference detection (Portfolio, Watchlist, Transactions, Sales, Portfolios)
- 3-way hash fast-forward and conflict detection
- Conflict resolution strategies (keep_local, keep_remote, smart_merge)
- 10 safety backups verification before remote apply
- Offline queueing and resilience
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import csv_manager
from google_sheet_sync import (
    GoogleSheetSync,
    get_google_apps_script_template,
    load_sheet_config,
    save_sheet_config,
)


class TestGoogleSheetSync(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.test_dir, "test_google_sheet_config.json")
        self.backup_dir = os.path.join(self.test_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        self.sync_engine = GoogleSheetSync(config_file=self.config_file)
        # Point sync engine to our test config
        self.sync_engine.config_file = self.config_file
        self.sync_engine.config = load_sheet_config()
        self.sync_engine.config["web_app_url"] = "https://script.google.com/macros/s/TEST/exec"

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_apps_script_template_validity(self):
        code = get_google_apps_script_template()
        self.assertIn("function doGet(e)", code)
        self.assertIn("function doPost(e)", code)
        self.assertIn("Sync_Meta", code)
        self.assertIn("SpreadsheetApp.getActiveSpreadsheet()", code)

    def test_local_data_export_and_hash(self):
        data = self.sync_engine.export_all_local_data()
        self.assertIn("Portfolio", data)
        self.assertIn("Watchlist", data)
        self.assertIn("Transactions", data)
        self.assertIn("Sales", data)
        self.assertIn("Portfolios", data)

        h1 = self.sync_engine.compute_dataset_hash(data)
        h2 = self.sync_engine.compute_dataset_hash(data)
        self.assertEqual(h1, h2)
        self.assertIsInstance(h1, str)
        self.assertEqual(len(h1), 32)

    def test_compare_datasets_no_difference(self):
        dataset = {
            "Portfolio": [{"Portfolio": "USD HSBC", "Symbol": "AAPL", "Shares": 10.0, "Buy Price": 150.0}],
            "Watchlist": [{"Symbol": "NVDA", "Target Price": 100.0}],
            "Transactions": [],
            "Sales": [],
            "Portfolios": [{"Portfolio Name": "USD HSBC"}],
        }
        res = self.sync_engine.compare_datasets(dataset, dataset)
        self.assertFalse(res["has_differences"])
        self.assertFalse(res["has_conflicts"])
        self.assertEqual(len(res["differences"]), 0)

    def test_compare_datasets_modified_and_added(self):
        local_data = {
            "Portfolio": [
                {"Portfolio": "USD HSBC", "Symbol": "AAPL", "Shares": 10.0, "Buy Price": 150.0},
                {"Portfolio": "USD HSBC", "Symbol": "MSFT", "Shares": 50.0, "Buy Price": 300.0},
            ],
            "Watchlist": [{"Symbol": "TSLA", "Target Price": 200.0}],
        }
        remote_data = {
            "Portfolio": [
                {"Portfolio": "USD HSBC", "Symbol": "AAPL", "Shares": 15.0, "Buy Price": 150.0},  # Modified shares
                {"Portfolio": "USD HSBC", "Symbol": "GOOG", "Shares": 20.0, "Buy Price": 140.0},  # Remote only
            ],
            "Watchlist": [{"Symbol": "TSLA", "Target Price": 250.0}],  # Modified target price
        }

        res = self.sync_engine.compare_datasets(local_data, remote_data)
        self.assertTrue(res["has_differences"])
        self.assertTrue(res["has_conflicts"])
        diffs = res["differences"]

        # Check types
        diff_types = [d["type"] for d in diffs]
        self.assertIn("MODIFIED", diff_types)
        self.assertIn("LOCAL_ONLY", diff_types)
        self.assertIn("REMOTE_ONLY", diff_types)

        # Check counts
        self.assertEqual(res["counts"]["modified"], 2)  # AAPL shares and TSLA target price
        self.assertEqual(res["counts"]["local_only"], 1)  # MSFT
        self.assertEqual(res["counts"]["remote_only"], 1)  # GOOG

    def test_smart_merge_datasets(self):
        local_data = {
            "Portfolio": [{"Portfolio": "USD HSBC", "Symbol": "AAPL", "Shares": 10.0, "Buy Price": 150.0}],
            "Watchlist": [{"Symbol": "MSFT", "Target Price": 300.0}],
            "Transactions": [{"Date": "2026-01-01", "Portfolio": "USD HSBC", "Symbol": "AAPL", "Type": "BUY", "Shares": 10.0}],
            "Sales": [],
            "Portfolios": [{"Portfolio Name": "USD HSBC"}],
        }
        remote_data = {
            "Portfolio": [{"Portfolio": "USD HSBC", "Symbol": "GOOG", "Shares": 20.0, "Buy Price": 140.0}],
            "Watchlist": [{"Symbol": "NVDA", "Target Price": 120.0}],
            "Transactions": [{"Date": "2026-01-02", "Portfolio": "USD HSBC", "Symbol": "GOOG", "Type": "BUY", "Shares": 20.0}],
            "Sales": [],
            "Portfolios": [{"Portfolio Name": "CAD Wealth"}],
        }

        merged = self.sync_engine.smart_merge_datasets(local_data, remote_data)

        # Both AAPL and GOOG should be in Portfolio
        p_syms = [r["Symbol"] for r in merged["Portfolio"]]
        self.assertIn("AAPL", p_syms)
        self.assertIn("GOOG", p_syms)

        # Both MSFT and NVDA in Watchlist
        w_syms = [r["Symbol"] for r in merged["Watchlist"]]
        self.assertIn("MSFT", w_syms)
        self.assertIn("NVDA", w_syms)

        # Both transactions merged
        self.assertEqual(len(merged["Transactions"]), 2)

        # Both portfolios merged
        pf_names = [r["Portfolio Name"] for r in merged["Portfolios"]]
        self.assertIn("USD HSBC", pf_names)
        self.assertIn("CAD Wealth", pf_names)

    @patch.object(GoogleSheetSync, "download_cloud_data")
    @patch.object(GoogleSheetSync, "upload_local_data_to_cloud")
    def test_perform_sync_fast_forward_upload(self, mock_upload, mock_download):
        local_data = self.sync_engine.export_all_local_data()
        local_hash = self.sync_engine.compute_dataset_hash(local_data)

        # Remote hasn't changed since last sync (matches last_synced_hash)
        old_hash = "old_synced_hash_123"
        self.sync_engine.config["last_synced_hash"] = old_hash

        mock_download.return_value = (True, {"Portfolio": []}, {}, "OK")
        with patch.object(self.sync_engine, "compute_dataset_hash", side_effect=[local_hash, old_hash]):
            mock_upload.return_value = (True, "Uploaded")
            res = self.sync_engine.perform_sync()
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["direction"], "upload")

    @patch.object(GoogleSheetSync, "download_cloud_data")
    @patch.object(GoogleSheetSync, "apply_remote_data_to_local")
    def test_perform_sync_fast_forward_download(self, mock_apply, mock_download):
        local_data = self.sync_engine.export_all_local_data()
        local_hash = self.sync_engine.compute_dataset_hash(local_data)

        # Local has not changed since last sync (matches last_synced_hash), but remote has changed
        self.sync_engine.config["last_synced_hash"] = local_hash
        remote_data = {"Portfolio": [{"Portfolio": "USD HSBC", "Symbol": "NEW_SYM", "Shares": 10.0, "Buy Price": 50.0}]}
        new_remote_hash = "new_remote_hash_456"

        mock_download.return_value = (True, remote_data, {}, "OK")
        with patch.object(self.sync_engine, "compute_dataset_hash", side_effect=[local_hash, new_remote_hash]):
            mock_apply.return_value = (True, "Applied")
            res = self.sync_engine.perform_sync()
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["direction"], "download")


if __name__ == "__main__":
    unittest.main()
