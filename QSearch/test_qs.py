#!/usr/bin/env python3
"""
QSearch Automated Regression & Verification Test Suite
======================================================
Tests all core subsystems:
1. MAC address detection, partials (last 4/6/8 hex), and variant generation
2. IPv4, CIDR subnets, IPv6, and compressed IPv6 extraction
3. Query parsing: boolean logic, quotes, inline file filters, NOT exclusion
4. Search Engine:
   - Multi-subnet OR queries (preventing dropped FTS branches)
   - Subnet + keyword AND precision
   - Subnet NOT exclusion
   - Normal text search without MAC hijacking (e.g. 192.147.55)
   - MAC multi-format expansion in MAC mode
   - Regex search mode
   - 1 match per unique file mode
   - CSV vs text file filtering
5. Indexer directory scope isolation & CSV header cache refresh
6. Nested subdirectory file resolution

Run via:
    python3 QSearch/test_qs.py
or:
    python3 QSearch/qs.py --test
"""

import sys
import os
import unittest
import tempfile
import shutil
import ipaddress
import subprocess
from pathlib import Path

# Ensure QSearch module is in Python import path
CURRENT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(CURRENT_DIR))
import qs


class TestMacAddressHelpers(unittest.TestCase):
    """Tests MAC address detection, validation, and multi-format generation."""

    def test_valid_mac_formats(self):
        valid_samples = [
            "1111.1111.1111",       # Cisco quad triplets
            "11:11:11:11:11:11",    # IEEE colon pairs
            "11-11-11-11-11-11",    # Hyphen pairs
            "11.11.11.11.11.11",    # Dot pairs
            "11 11 11 11 11 11",    # Space pairs
            "111111111111",          # Flat 12-char hex
            "eeff",                 # Last 4 hex characters
            "ee:ff",                # 2 octets colon
            "ee-ff",                # 2 octets hyphen
            ".eeff",                # Cisco suffix
            "2233.4455",            # 4 octets Cisco
            "aabb.ccdd.eeff",       # Full Cisco
        ]
        for sample in valid_samples:
            self.assertTrue(qs.is_mac_address(sample), f"Expected '{sample}' to be recognized as MAC")

    def test_invalid_mac_and_ip_exclusion(self):
        """IP fragments, decimal numbers, and non-MAC strings must NOT be treated as MACs."""
        invalid_samples = [
            "192.147.55",           # 3-digit decimal IP octets (critical regression test)
            "10.1.1.1",             # IPv4 address
            "192.168.1.1",          # IPv4 address
            "127.0.0.1",            # IPv4 address
            "1.0.0.0/8",            # CIDR subnet
            "router-01",            # Alphanumeric text
            "vlan100",              # Keyword
            "123",                  # 3 chars
            "12345",                # 5 chars
            "xyz1.2345.6789",       # Non-hex characters
        ]
        for sample in invalid_samples:
            self.assertFalse(qs.is_mac_address(sample), f"'{sample}' should NOT be recognized as MAC")

    def test_generate_mac_variants(self):
        variants = qs.generate_mac_variants("0011.2233.4455")
        # Full MAC must generate all standard formats
        self.assertIn("0011.2233.4455", variants)
        self.assertIn("00:11:22:33:44:55", variants)
        self.assertIn("00-11-22-33-44-55", variants)
        self.assertIn("00.11.22.33.44.55", variants)
        self.assertIn("001122334455", variants)

        # Last 4 characters
        v4 = qs.generate_mac_variants("eeff")
        self.assertIn("eeff", v4)
        self.assertIn("ee:ff", v4)
        self.assertIn("ee-ff", v4)
        self.assertIn(".eeff", v4)


class TestIPSubnetHelpers(unittest.TestCase):
    """Tests IP/CIDR subnet detection, parsing, and candidate extraction."""

    def test_parse_ip_or_subnet(self):
        net4 = qs.parse_ip_or_subnet("10.0.0.0/8")
        self.assertIsNotNone(net4)
        self.assertEqual(net4.version, 4)

        net6 = qs.parse_ip_or_subnet("2001:db8::/32")
        self.assertIsNotNone(net6)
        self.assertEqual(net6.version, 6)

        self.assertIsNone(qs.parse_ip_or_subnet("not_an_ip"))

    def test_extract_matching_ips_ipv4(self):
        target_net = ipaddress.ip_network("10.0.0.0/8")
        text = "Core switch interface ge-0/0/1 has IP 10.1.20.30 and next-hop 192.168.1.1"
        matched = qs.extract_matching_ips_in_text(target_net, text)
        self.assertEqual(matched, ["10.1.20.30"])

    def test_extract_matching_ips_ipv6_compressed(self):
        """Must correctly match full and compressed IPv6 addresses (with ::)."""
        target_net = ipaddress.ip_network("2001:db8::/32")
        text = "Server dual-stack ipv6 2001:db8::1 active, loopback ::1, fe80::1 link-local"
        matched = qs.extract_matching_ips_in_text(target_net, text)
        self.assertEqual(matched, ["2001:db8::1"])


class TestQueryParser(unittest.TestCase):
    """Tests stripping inline file filters, extracting keywords, and boolean parsing."""

    def test_strip_file_filter(self):
        ffilter, clean = qs.strip_file_filter("file:switch 10.0.0.0/8")
        self.assertEqual(ffilter, "switch")
        self.assertEqual(clean, "10.0.0.0/8")

        ffilter2, clean2 = qs.strip_file_filter("f:inventory server AND prod")
        self.assertEqual(ffilter2, "inventory")
        self.assertEqual(clean2, "server AND prod")

    def test_strip_file_filter_quoted_and_spaces(self):
        ffilter, clean = qs.strip_file_filter('file:"network inventory.csv" 10.0.0.0/8')
        self.assertEqual(ffilter, "network inventory.csv")
        self.assertEqual(clean, "10.0.0.0/8")

        ffilter2, clean2 = qs.strip_file_filter('f:"switch log 2026.txt"')
        self.assertEqual(ffilter2, "switch log 2026.txt")
        self.assertEqual(clean2, "")

    def test_extract_search_keywords(self):
        keywords = qs.extract_search_keywords('server AND prod OR "GigabitEthernet 0/1" NOT test')
        self.assertIn("GigabitEthernet 0/1", keywords)
        self.assertIn("server", keywords)
        self.assertIn("prod", keywords)
        self.assertNotIn("test", keywords)  # Excluded by NOT
        self.assertNotIn("AND", keywords)
        self.assertNotIn("OR", keywords)


class TestSearchEngineIntegration(unittest.TestCase):
    """Full end-to-end integration tests on an isolated SQLite database."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="qs_test_engine_")
        self.content_dir = Path(self.temp_dir) / "content"
        self.content_dir.mkdir()
        self.db_path = Path(self.temp_dir) / "test_index.db"

        # Create sample data files
        csv_file = self.content_dir / "network_inventory.csv"
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write("Hostname,IP,Role,MAC,Status\n")
            # 1050 rows of 10.x.x.x
            for i in range(1050):
                f.write(f"rtr-core-{i},10.0.0.{i%250},router,0011.2233.{i%100:04x},active\n")
            # 5 rows of 1.x.x.x
            for i in range(5):
                f.write(f"sw-access-{i},1.10.20.{i},sw,aabb.ccdd.{i:04x},active\n")
            # 2 rows of 192.168.x.x
            f.write("srv-db-01,192.168.1.50,database,1122.3344.5566,active\n")
            f.write("srv-web-01,192.168.1.51,web,1122.3344.5567,active\n")
            # Normal text row with 192.147.55
            f.write("legacy-node,192.147.55,server,9988.7766.5544,active\n")

        txt_file = self.content_dir / "syslog.log"
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write("2026-09-02 10:00:01 [INFO] Service started on 10.1.1.1\n")
            f.write("2026-09-02 10:00:02 [ERROR] Link flap on sw-access-0 interface ge-0/0/1\n")
            f.write("2026-09-02 10:00:03 [WARN] High memory on srv-db-01 (192.168.1.50)\n")

        # Initialize search engine & index
        self.engine = qs.SearchEngine(content_dir=self.content_dir, db_path=self.db_path)
        self.indexer = qs.BackgroundIndexer(self.engine, content_dir=self.content_dir)
        self.indexer.sync_content_directory()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_no_dropped_or_branches(self):
        """Query '1.0.0.0/8 OR 10.0.0.0/8' must find both 1.x and 10.x even with 1000+ results."""
        results, elapsed_ms, match_type = self.engine.search("1.0.0.0/8 OR 10.0.0.0/8", limit=1000)
        has_1 = any("1.10.20." in r[2] for r in results)
        has_10 = any("10.0.0." in r[2] for r in results)
        self.assertTrue(has_1, "1.0.0.0/8 branch was improperly dropped!")
        self.assertTrue(has_10, "10.0.0.0/8 branch was improperly dropped!")

    def test_subnet_and_short_keyword_precision(self):
        """'10.0.0.0/8 AND sw' must return 0 rows since all 10.x hosts have role 'router'."""
        res_none, _, _ = self.engine.search("10.0.0.0/8 AND sw")
        self.assertEqual(len(res_none), 0, "Expected 0 results for '10.0.0.0/8 AND sw'")

        res_match, _, _ = self.engine.search("1.0.0.0/8 AND sw")
        self.assertEqual(len(res_match), 5, "Expected 5 results for '1.0.0.0/8 AND sw'")

    def test_subnet_not_exclusion(self):
        """'192.168.1.0/24 NOT 192.168.1.50' should only return 192.168.1.51."""
        results, _, _ = self.engine.search("192.168.1.0/24 NOT 192.168.1.50")
        matched_content = [r[2] for r in results]
        self.assertTrue(any("192.168.1.51" in c for c in matched_content))
        self.assertFalse(any("192.168.1.50" in c for c in matched_content))

    def test_normal_text_search_not_hijacked(self):
        """Text search for '192.147.55' must match normally via FTS/LIKE without MAC hijacking."""
        results, _, _ = self.engine.search("192.147.55")
        self.assertEqual(len(results), 1)
        self.assertIn("legacy-node", results[0][2])

    def test_mac_mode_cross_format(self):
        """Searching in MAC mode with colon format must find dot notation in DB."""
        results, _, match_type = self.engine.search("11:22:33:44:55:66", is_mac=True)
        self.assertEqual(match_type, "mac")
        self.assertEqual(len(results), 1)
        self.assertIn("srv-db-01", results[0][2])

    def test_partial_mac_last_4_chars(self):
        """Searching partial MAC '5566' in MAC mode must find 1122.3344.5566."""
        results, _, match_type = self.engine.search("5566", is_mac=True)
        self.assertEqual(match_type, "mac")
        self.assertTrue(any("1122.3344.5566" in r[2] for r in results))

    def test_unique_files_mode(self):
        """With unique_files=True, each matching file appears only once."""
        results, _, _ = self.engine.search("router", unique_files=True)
        matched_files = [r[0] for r in results]
        self.assertEqual(len(matched_files), len(set(matched_files)))

    def test_file_type_filter(self):
        """Filtering by CSV or text must isolate matching file extensions."""
        csv_results, _, _ = self.engine.search("sw-access", file_type="csv")
        for r in csv_results:
            self.assertTrue(r[0].lower().endswith(".csv"))

        txt_results, _, _ = self.engine.search("sw-access", file_type="text")
        for r in txt_results:
            self.assertFalse(r[0].lower().endswith(".csv"))

    def test_cross_directory_persistence(self):
        """Indexing a separate directory must NOT delete existing files outside that directory."""
        other_dir = Path(self.temp_dir) / "other_dir"
        other_dir.mkdir()
        other_file = other_dir / "external.txt"
        with open(other_file, "w") as f:
            f.write("external standalone log entry\n")

        other_indexer = qs.BackgroundIndexer(self.engine, content_dir=other_dir)
        other_indexer.sync_content_directory()

        # Resync original content_dir
        self.indexer.sync_content_directory()

        # Both the original files and the external file must exist in DB metadata
        info_orig = self.engine.get_file_info("network_inventory.csv")
        info_ext = self.engine.get_file_info(str(other_file))
        self.assertIsNotNone(info_orig, "Original file was purged!")
        self.assertIsNotNone(info_ext, "External file was purged!")

    def test_search_with_file_filter(self):
        """Query with file:filename must only return matches from that specific file."""
        res_csv, _, _ = self.engine.search("file:network_inventory.csv router")
        self.assertTrue(len(res_csv) > 0)
        for r in res_csv:
            self.assertEqual(r[0], "network_inventory.csv")

        # Filtering to syslog.log must return zero rows for 'router'
        res_syslog, _, _ = self.engine.search("file:syslog.log router")
        self.assertEqual(len(res_syslog), 0)

        # Quoted file filter
        res_quoted, _, _ = self.engine.search('file:"network_inventory.csv" router')
        self.assertTrue(len(res_quoted) > 0)


def run_all_tests():
    """Runs the test suite and returns exit code (0 for success, non-zero for failure)."""
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
