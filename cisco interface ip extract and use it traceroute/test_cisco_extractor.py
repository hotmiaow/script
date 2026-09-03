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
4. Cisco interface extraction:
   - Hostname, primary IP, CIDR conversion, and VRF detection
"""

import sys
import unittest
from pathlib import Path

# Add current directory to import path
CURRENT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(CURRENT_DIR))

# Import the extractor module dynamically due to filename with spaces
import importlib.util
script_path = CURRENT_DIR / "Cisco Interface Information Extractor.py"
spec = importlib.util.spec_from_file_location("cisco_extractor", str(script_path))
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
