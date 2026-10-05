#!/usr/bin/env python3
"""
Regression Test Suite for Cisco & FortiGate Interface Extractor
===============================================================
Tests:
1. FortiGate inline / chained zone configuration commands:
   - config vdom edit App config system zone edit "AAA-Zone" set interface VL1.1234
   - config vdom edit App config system zone edit "AAA-Zone" set interface "LAG1.1111"
   - Multiple interfaces in a single set interface command
   - Global inline zone commands (without config vdom)
2. FortiGate multi-line nested VDOM and Zone blocks:
   - Multiple VDOMs with independent zones
   - Multiple zones within the same VDOM
   - Zone fallback to root VDOM
   - Case-insensitive interface and zone matching
3. End-to-end interface and IP extraction:
   - FortiGate IP mask vs CIDR format
   - Description, VDOM, and zone mapping in final output dictionary
4. Cross-File FortiGate Interface and Zone correlation:
   - Separate files for same device: e.g. hk1-aaa_AWS.set and hk1-aaa_root.set
   - root file has interface IP, AWS file has zone configuration
   - Batch directory pre-scan resolution
   - Order-independent retroactive resolution (root first vs AWS first)
   - Filename parsing for device name and VDOM context
5. Cisco interface extraction:
   - Hostname, primary IP, CIDR conversion, and VRF detection
"""

import sys
import os
import tempfile
import shutil
import unittest
from pathlib import Path

# Add current directory to import path
CURRENT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(CURRENT_DIR))

# Import the extractor module dynamically
import importlib.util
script_path = CURRENT_DIR / "InterfaceExtractor.py"
if not script_path.exists():
    script_path = CURRENT_DIR / "Cisco Interface Information Extractor.py"

spec = importlib.util.spec_from_file_location("interface_extractor", str(script_path))
extractor_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor_mod)
NetworkConfigParser = extractor_mod.NetworkConfigParser


class TestFortigateZoneExtraction(unittest.TestCase):
    """Unit tests for FortiGate VDOM and Zone extraction."""

    def setUp(self):
        self.parser = NetworkConfigParser()

    def test_inline_vdom_zone_unquoted_interface(self):
        """Test: config vdom edit App config system zone edit "AAA-Zone" set interface VL1.1234"""
        cmd = 'config vdom edit App config system zone edit "AAA-Zone" set interface VL1.1234'
        zones = self.parser.extract_fortigate_zones(cmd)
        self.assertIn("App::VL1.1234", zones)
        self.assertEqual(zones["App::VL1.1234"], "AAA-Zone")

    def test_inline_vdom_zone_quoted_interface(self):
        """Test: config vdom edit App config system zone edit "AAA-Zone" set interface "LAG1.1111" """
        cmd = 'config vdom edit App config system zone edit "AAA-Zone" set interface "LAG1.1111"'
        zones = self.parser.extract_fortigate_zones(cmd)
        self.assertIn("App::LAG1.1111", zones)
        self.assertEqual(zones["App::LAG1.1111"], "AAA-Zone")

    def test_inline_vdom_multiple_interfaces(self):
        """Test: multiple interfaces on a single set interface command"""
        cmd = 'config vdom edit App config system zone edit "AAA-Zone" set interface "LAG1.1111" VL1.1234'
        zones = self.parser.extract_fortigate_zones(cmd)
        self.assertEqual(zones.get("App::LAG1.1111"), "AAA-Zone")
        self.assertEqual(zones.get("App::VL1.1234"), "AAA-Zone")

    def test_inline_global_zone(self):
        """Test: config system zone edit "Global-Zone" set interface port1 "port2" """
        cmd = 'config system zone edit "Global-Zone" set interface port1 "port2"'
        zones = self.parser.extract_fortigate_zones(cmd)
        self.assertEqual(zones.get("root::port1"), "Global-Zone")
        self.assertEqual(zones.get("root::port2"), "Global-Zone")

    def test_multiline_nested_vdom_and_zones(self):
        """Test: standard FortiGate hierarchical blocks with multiple VDOMs and zones."""
        config = """
        config vdom
            edit App
                config system zone
                    edit "AAA-Zone"
                        set interface VL1.1234
                    next
                    edit "BBB-Zone"
                        set interface "LAG1.1111"
                    next
                end
            next
            edit App2
                config system zone
                    edit "CCC-Zone"
                        set interface "port2"
                    next
                end
            next
        end
        """
        zones = self.parser.extract_fortigate_zones(config)
        self.assertEqual(zones.get("App::VL1.1234"), "AAA-Zone")
        self.assertEqual(zones.get("App::LAG1.1111"), "BBB-Zone")
        self.assertEqual(zones.get("App2::port2"), "CCC-Zone")

    def test_zone_lookup_exact_and_fallback(self):
        """Test get_zone_for_interface priority: exact VDOM -> root fallback -> case-insensitive."""
        zones = {
            "App::VL1.1234": "AAA-Zone",
            "root::port1": "Shared-Zone",
            "App::LAG1.1111": "LAG-Zone"
        }
        # Exact match
        self.assertEqual(self.parser.get_zone_for_interface("VL1.1234", "App", zones), "AAA-Zone")
        # Root fallback
        self.assertEqual(self.parser.get_zone_for_interface("port1", "OtherVDOM", zones), "Shared-Zone")
        # Case-insensitive match
        self.assertEqual(self.parser.get_zone_for_interface("lag1.1111", "App", zones), "LAG-Zone")
        # No zone match
        self.assertEqual(self.parser.get_zone_for_interface("unassigned_port", "App", zones), "No Zone")


class TestFortigateInterfaceParsing(unittest.TestCase):
    """End-to-end tests for parse_fortigate_interfaces."""

    def setUp(self):
        self.parser = NetworkConfigParser()

    def test_end_to_end_inline_zone_and_interfaces(self):
        """Verify full interface row extraction with inline zone commands."""
        config = """
        config vdom edit App config system zone edit "AAA-Zone" set interface VL1.1234
        config vdom edit App config system zone edit "AAA-Zone" set interface "LAG1.1111"
        config system interface
            edit "VL1.1234"
                set vdom "App"
                set ip 10.1.2.3 255.255.255.0
                set description "Application Gateway"
            next
            edit "LAG1.1111"
                set vdom "App"
                set ip 10.2.3.4/24
                set description "Uplink LAG"
            next
        end
        """
        interfaces = self.parser.parse_fortigate_interfaces(config, "FW-EDGE-01")
        self.assertEqual(len(interfaces), 2)

        vl_entry = next((i for i in interfaces if i["interface_name"] == "VL1.1234"), None)
        self.assertIsNotNone(vl_entry)
        self.assertEqual(vl_entry["device_name"], "FW-EDGE-01 (VDOM: App)")
        self.assertEqual(vl_entry["ip_address"], "10.1.2.3/24")
        self.assertEqual(vl_entry["zone"], "AAA-Zone")
        self.assertEqual(vl_entry["description"], "Application Gateway")

        lag_entry = next((i for i in interfaces if i["interface_name"] == "LAG1.1111"), None)
        self.assertIsNotNone(lag_entry)
        self.assertEqual(lag_entry["device_name"], "FW-EDGE-01 (VDOM: App)")
        self.assertEqual(lag_entry["ip_address"], "10.2.3.4/24")
        self.assertEqual(lag_entry["zone"], "AAA-Zone")
        self.assertEqual(lag_entry["description"], "Uplink LAG")


class TestCrossFileFortigateCorrelation(unittest.TestCase):
    """Tests for cross-file FortiGate correlation (e.g. hk1-aaa_AWS.set and hk1-aaa_root.set)."""

    def setUp(self):
        self.parser = NetworkConfigParser()
        self.temp_dir = tempfile.mkdtemp(prefix="test_fg_cross_")

        self.aws_file = os.path.join(self.temp_dir, "hk1-aaa_AWS.set")
        self.root_file = os.path.join(self.temp_dir, "hk1-aaa_root.set")

        # AWS file contains the zone configuration for AAA-Zone
        with open(self.aws_file, "w") as f:
            f.write("""
config system zone
    edit "AAA-Zone"
        set interface "LAG1.1111" VL1.1234
    next
end
""")

        # root file contains the interfaces with IP configurations
        with open(self.root_file, "w") as f:
            f.write("""
config system interface
    edit "VL1.1234"
        set ip 10.1.2.3 255.255.255.0
        set description "App Web Gateway"
    next
    edit "LAG1.1111"
        set ip 10.2.3.4 255.255.255.0
        set description "App DB Uplink"
    next
end
""")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_filename_parsing(self):
        """Test device name and VDOM extraction from filename."""
        dev, vdom = self.parser.parse_device_and_vdom_from_filename("hk1-aaa_AWS.set")
        self.assertEqual(dev, "hk1-aaa")
        self.assertEqual(vdom, "AWS")

        dev, vdom = self.parser.parse_device_and_vdom_from_filename("/path/to/hk1-aaa_root.set")
        self.assertEqual(dev, "hk1-aaa")
        self.assertEqual(vdom, "root")

        dev, vdom = self.parser.parse_device_and_vdom_from_filename("standalone_firewall.txt")
        self.assertEqual(dev, "standalone_firewall")
        self.assertEqual(vdom, "root")

    def test_cross_file_directory_processing(self):
        """Test process_directory pre-scan and cross-file zone resolution."""
        self.parser.process_directory(self.temp_dir, auto_yes=True)
        self.assertEqual(len(self.parser.interface_data), 2)

        vl = next((i for i in self.parser.interface_data if i["interface_name"] == "VL1.1234"), None)
        self.assertIsNotNone(vl)
        self.assertEqual(vl["device_name"], "hk1-aaa (VDOM: AWS)")
        self.assertEqual(vl["ip_address"], "10.1.2.3/24")
        self.assertEqual(vl["zone"], "AAA-Zone")
        self.assertEqual(vl["description"], "App Web Gateway")

        lag = next((i for i in self.parser.interface_data if i["interface_name"] == "LAG1.1111"), None)
        self.assertIsNotNone(lag)
        self.assertEqual(lag["device_name"], "hk1-aaa (VDOM: AWS)")
        self.assertEqual(lag["ip_address"], "10.2.3.4/24")
        self.assertEqual(lag["zone"], "AAA-Zone")
        self.assertEqual(lag["description"], "App DB Uplink")

    def test_cross_file_root_before_aws(self):
        """Test parsing root file first, then AWS file (retroactive resolution)."""
        root_res = self.parser.parse_file(self.root_file)
        self.parser.interface_data.extend(root_res)

        aws_res = self.parser.parse_file(self.aws_file)
        self.parser.interface_data.extend(aws_res)

        for item in self.parser.interface_data:
            self.assertEqual(item["zone"], "AAA-Zone")
            self.assertIn("AWS", item["device_name"])

    def test_cross_file_aws_before_root(self):
        """Test parsing AWS file first, then root file."""
        aws_res = self.parser.parse_file(self.aws_file)
        self.parser.interface_data.extend(aws_res)

        root_res = self.parser.parse_file(self.root_file)
        self.parser.interface_data.extend(root_res)

        for item in self.parser.interface_data:
            self.assertEqual(item["zone"], "AAA-Zone")
            self.assertIn("AWS", item["device_name"])


class TestCiscoInterfaceParsing(unittest.TestCase):
    """Tests for Cisco IOS/NXOS interface extraction."""

    def setUp(self):
        self.parser = NetworkConfigParser()

    def test_cisco_hostname_and_interfaces(self):
        import textwrap
        config = textwrap.dedent("""
        hostname Core-Rtr-01
        !
        interface GigabitEthernet0/0/1
         description Uplink to ISP
         ip address 198.51.100.2 255.255.255.252
        !
        """)
        hostname = self.parser.extract_hostname_cisco(config)
        self.assertEqual(hostname, "Core-Rtr-01")

        interfaces = self.parser.parse_cisco_interfaces(config, hostname)
        self.assertTrue(len(interfaces) >= 1)
        entry = interfaces[0]
        self.assertEqual(entry["device_name"], "Core-Rtr-01")
        self.assertEqual(entry["interface_name"], "GigabitEthernet0/0/1")
        self.assertEqual(entry["ip_address"], "198.51.100.2/30")
        self.assertEqual(entry["description"], "Uplink to ISP")


def run_tests():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
