#!/usr/bin/env python3
"""
Unit tests for CiscoTracerouteMapper (TraceINT.py)
Tests:
1. IP & Subnet parsing (CIDR, space-separated mask, secondary, DHCP, etc.)
2. Device inventory and interface loading
3. Subnet-based interface matching between consecutive hops
4. End-to-end path resolution for Inbound and Outbound interfaces
5. Inbound/Outbound resolution when hop IP is ingress vs egress
6. Intermediate timeout hop handling
7. Target subnet containment for last hop
8. Source subnet containment for first hop
9. Zone transition detection (e.g. Trust -> Untrust)
10. Path flow diagram formatting
"""

import io
import ipaddress
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from TraceINT import (
    CiscoTracerouteMapper,
    parse_ip_and_network,
    parse_transit_subnets,
    TraceINTGUI,
    TKINTER_AVAILABLE,
)


class TestTraceINTHelpers(unittest.TestCase):
    def test_parse_transit_subnets(self):
        # 1. Comma separated
        self.assertEqual(parse_transit_subnets("30, 31, 29, 28"), {28, 29, 30, 31})
        self.assertEqual(parse_transit_subnets("/30, /31, /29, /28"), {28, 29, 30, 31})

        # 2. Range notation
        self.assertEqual(parse_transit_subnets("28-31"), {28, 29, 30, 31})
        self.assertEqual(parse_transit_subnets("/28-/31"), {28, 29, 30, 31})

        # 3. Custom selection
        self.assertEqual(parse_transit_subnets("30, 31"), {30, 31})
        self.assertEqual(parse_transit_subnets("/29 /30"), {29, 30})

        # 4. Iterables
        self.assertEqual(parse_transit_subnets([30, 31]), {30, 31})
        self.assertEqual(parse_transit_subnets({28, 29}), {28, 29})

        # 5. Invalid input falls back to default {28, 29, 30, 31}
        self.assertEqual(parse_transit_subnets(""), {28, 29, 30, 31})
        self.assertEqual(parse_transit_subnets("invalid"), {28, 29, 30, 31})

    def test_parse_ip_and_network(self):
        # 1. Standard CIDR
        ip, net = parse_ip_and_network("10.1.1.1/24")
        self.assertEqual(ip, "10.1.1.1")
        self.assertEqual(net, ipaddress.ip_network("10.1.1.0/24"))

        # 2. Point-to-point /30
        ip, net = parse_ip_and_network("192.168.1.1/30")
        self.assertEqual(ip, "192.168.1.1")
        self.assertEqual(net, ipaddress.ip_network("192.168.1.0/30"))

        # 3. Space separated netmask
        ip, net = parse_ip_and_network("172.16.0.1 255.255.255.0")
        self.assertEqual(ip, "172.16.0.1")
        self.assertEqual(net, ipaddress.ip_network("172.16.0.0/24"))

        # 4. Netmask with slash
        ip, net = parse_ip_and_network("10.0.0.1/255.255.255.252")
        self.assertEqual(ip, "10.0.0.1")
        self.assertEqual(net, ipaddress.ip_network("10.0.0.0/30"))

        # 5. Secondary IP annotation
        ip, net = parse_ip_and_network("10.2.2.1/24 (secondary)")
        self.assertEqual(ip, "10.2.2.1")
        self.assertEqual(net, ipaddress.ip_network("10.2.2.0/24"))

        # 6. Plain IP
        ip, net = parse_ip_and_network("8.8.8.8")
        self.assertEqual(ip, "8.8.8.8")
        self.assertIsNone(net)

        # 7. Dynamic / unassigned
        for val in ["DHCP", "PPPoE", "unassigned", "SOURCE: LOOPBACK1", ""]:
            ip, net = parse_ip_and_network(val)
            self.assertIsNone(ip)
            self.assertIsNone(net)


class TestSubnetInterfaceResolution(unittest.TestCase):
    def setUp(self):
        self.mapper = CiscoTracerouteMapper(csv_file="nonexistent.csv")
        # Populate mock inventory:
        # R1:
        #   Gi0/0: 192.168.1.1/24 (LAN)
        #   Gi0/1: 10.0.0.1/30 (Transit to R2)
        # R2:
        #   Gi0/1: 10.0.0.2/30 (Transit from R1)
        #   Gi0/2: 10.0.1.1/30 (Transit to R3)
        # R3 (Firewall):
        #   port1: 10.0.1.2/30 (Trust - from R2)
        #   port2: 172.16.0.1/24 (Untrust - towards Target)
        self._add_iface("R1", "Gi0/0", "192.168.1.1/24", "LAN", "default", "User LAN")
        self._add_iface("R1", "Gi0/1", "10.0.0.1/30", "Transit", "default", "Link to R2")
        self._add_iface("R2", "Gi0/1", "10.0.0.2/30", "Transit", "default", "Link to R1")
        self._add_iface("R2", "Gi0/2", "10.0.1.1/30", "WAN", "default", "Link to R3")
        self._add_iface("R3", "port1", "10.0.1.2/30", "Trust", "root", "Ingress from R2")
        self._add_iface("R3", "port2", "172.16.0.1/24", "Untrust", "root", "Egress to Server Farm")

    def _add_iface(self, dev, iface, ip_sub, zone="Trust", vrf="default", desc=""):
        ip, net = parse_ip_and_network(ip_sub)
        self.mapper.device_inventory.setdefault(dev, []).append((iface, ip, zone, vrf, desc))
        self.mapper.device_interfaces.setdefault(dev, []).append({
            "device": dev,
            "iface": iface,
            "ip": ip,
            "network": net,
            "zone": zone,
            "vrf": vrf,
            "description": desc,
            "raw_ip": ip_sub,
        })
        self.mapper.ip_to_device_map[ip] = (dev, iface, zone, vrf, desc)
        self.mapper.ip_to_network_map[ip] = net
        self.mapper.device_zones.setdefault(dev, zone)

    def test_find_matching_subnet_interfaces(self):
        # Match R1 -> R2
        match_12 = self.mapper.find_matching_subnet_interfaces("R1", "R2")
        self.assertIsNotNone(match_12)
        if1, if2 = match_12
        self.assertEqual(if1["iface"], "Gi0/1")
        self.assertEqual(if2["iface"], "Gi0/1")
        self.assertEqual(if1["ip"], "10.0.0.1")
        self.assertEqual(if2["ip"], "10.0.0.2")

        # Match R2 -> R3
        match_23 = self.mapper.find_matching_subnet_interfaces("R2", "R3")
        self.assertIsNotNone(match_23)
        if2, if3 = match_23
        self.assertEqual(if2["iface"], "Gi0/2")
        self.assertEqual(if3["iface"], "port1")

        # No direct link between R1 and R3
        match_13 = self.mapper.find_matching_subnet_interfaces("R1", "R3")
        self.assertIsNone(match_13)

    def test_transit_subnets_focus_and_configurability(self):
        # 1. Verify default transit subnets
        self.assertEqual(self.mapper.transit_subnets, {28, 29, 30, 31})
        self.assertEqual(self.mapper.get_transit_subnets_display(), "/28, /29, /30, /31")

        # 2. Add devices D_A and D_B that only share a /24 subnet (e.g. Management LAN)
        self._add_iface("D_A", "mgmt0", "10.88.88.1/24", "Mgmt", "default", "Management")
        self._add_iface("D_B", "mgmt0", "10.88.88.2/24", "Mgmt", "default", "Management")

        # Under default settings (focus on /30, /31, /29, /28), /24 is ignored for transit matching
        match_ab_default = self.mapper.find_matching_subnet_interfaces("D_A", "D_B")
        self.assertIsNone(match_ab_default)

        # 3. Add a /30 link between D_A and D_B
        self._add_iface("D_A", "Gi0/1", "10.77.77.1/30", "Transit", "default", "Transit link")
        self._add_iface("D_B", "Gi0/1", "10.77.77.2/30", "Transit", "default", "Transit link")

        # Now it must match the /30 link Gi0/1, NOT the /24 mgmt0 link
        match_ab_with_p2p = self.mapper.find_matching_subnet_interfaces("D_A", "D_B")
        self.assertIsNotNone(match_ab_with_p2p)
        if_a, if_b = match_ab_with_p2p
        self.assertEqual(if_a["iface"], "Gi0/1")
        self.assertEqual(if_b["iface"], "Gi0/1")

        # 4. Reconfigure transit subnets to allow /24
        self.mapper.set_transit_subnets("24, 30")
        self.assertEqual(self.mapper.transit_subnets, {24, 30})
        self.assertEqual(self.mapper.get_transit_subnets_display(), "/24, /30")

        # Remove the /30 link and verify /24 is now matched
        self.mapper.device_interfaces["D_A"] = [
            i for i in self.mapper.device_interfaces["D_A"] if i["iface"] != "Gi0/1"
        ]
        self.mapper.device_interfaces["D_B"] = [
            i for i in self.mapper.device_interfaces["D_B"] if i["iface"] != "Gi0/1"
        ]
        match_ab_reconfig = self.mapper.find_matching_subnet_interfaces("D_A", "D_B")
        self.assertIsNotNone(match_ab_reconfig)
        if_a2, if_b2 = match_ab_reconfig
        self.assertEqual(if_a2["iface"], "mgmt0")
        self.assertEqual(if_b2["iface"], "mgmt0")

    def test_find_interface_by_ip(self):
        # Target in R3's port2 subnet (172.16.0.0/24)
        iface = self.mapper.find_interface_by_ip("R3", "172.16.0.50")
        self.assertIsNotNone(iface)
        self.assertEqual(iface["iface"], "port2")

        # Source in R1's Gi0/0 subnet (192.168.1.0/24)
        iface = self.mapper.find_interface_by_ip("R1", "192.168.1.100")
        self.assertIsNotNone(iface)
        self.assertEqual(iface["iface"], "Gi0/0")

    def test_full_path_resolution(self):
        # Simulated traceroute hops:
        # Hop 1: 10.0.0.1 (R1 Gi0/1)
        # Hop 2: 10.0.1.1 (R2 Gi0/2)
        # Hop 3: 172.16.0.1 (R3 port2)
        # Hop 4: 172.16.0.50 (Target host)
        hops = [
            (1, "10.0.0.1"),
            (2, "10.0.1.1"),
            (3, "172.16.0.1"),
            (4, "172.16.0.50"),
        ]
        resolved = self.mapper.resolve_path_interfaces(
            hops, target_ip="172.16.0.50", source_ip="192.168.1.100"
        )
        self.assertEqual(len(resolved), 4)

        # Hop 1 (R1): Inbound Gi0/0 from source, Outbound Gi0/1 to R2
        h1 = resolved[0]
        self.assertEqual(h1["device"], "R1")
        self.assertEqual(h1["in_iface"], "Gi0/0")
        self.assertEqual(h1["out_iface"], "Gi0/1")
        self.assertEqual(h1["next_in_iface"], "R2:Gi0/1")

        # Hop 2 (R2): Inbound Gi0/1 from R1, Outbound Gi0/2 to R3
        h2 = resolved[1]
        self.assertEqual(h2["device"], "R2")
        self.assertEqual(h2["in_iface"], "Gi0/1")
        self.assertEqual(h2["out_iface"], "Gi0/2")
        self.assertEqual(h2["next_in_iface"], "R3:port1")

        # Hop 3 (R3 Firewall): Inbound port1 from R2, Outbound port2 towards Target
        h3 = resolved[2]
        self.assertEqual(h3["device"], "R3")
        self.assertEqual(h3["in_iface"], "port1")
        self.assertEqual(h3["out_iface"], "port2")
        self.assertEqual(h3["zone"], "Trust -> Untrust")

        # Hop 4 (Target)
        h4 = resolved[3]
        self.assertEqual(h4["out_iface"], "Connected / Target")

    def test_resolution_when_hop_ip_is_ingress_interface(self):
        # In this scenario, each router responds with its incoming interface:
        # Hop 1: 192.168.1.1 (R1 Gi0/0 - Inbound)
        # Hop 2: 10.0.0.2 (R2 Gi0/1 - Inbound)
        # Hop 3: 10.0.1.2 (R3 port1 - Inbound)
        hops = [
            (1, "192.168.1.1"),
            (2, "10.0.0.2"),
            (3, "10.0.1.2"),
            (4, "172.16.0.50"),
        ]
        resolved = self.mapper.resolve_path_interfaces(
            hops, target_ip="172.16.0.50", source_ip="192.168.1.100"
        )
        # Even though hop 2 IP was 10.0.0.2 (Gi0/1), R2's outbound interface
        # must still be identified as Gi0/2 (connecting to R3's port1)!
        h2 = resolved[1]
        self.assertEqual(h2["device"], "R2")
        self.assertEqual(h2["in_iface"], "Gi0/1")
        self.assertEqual(h2["out_iface"], "Gi0/2")

        # And R3's outbound must still be identified as port2!
        h3 = resolved[2]
        self.assertEqual(h3["device"], "R3")
        self.assertEqual(h3["in_iface"], "port1")
        self.assertEqual(h3["out_iface"], "port2")

    def test_resolution_with_timeout_hop(self):
        # Hop 2 is a timeout
        hops = [
            (1, "10.0.0.1"),
            (2, None),
            (3, "10.0.1.2"),
        ]
        resolved = self.mapper.resolve_path_interfaces(hops, target_ip="172.16.0.50")
        self.assertEqual(len(resolved), 3)
        self.assertTrue(resolved[1]["is_timeout"])
        self.assertEqual(resolved[0]["device"], "R1")
        self.assertEqual(resolved[2]["device"], "R3")

    def test_format_path_flow(self):
        hops = [
            (1, "10.0.0.1"),
            (2, "10.0.1.1"),
            (3, "172.16.0.1"),
            (4, "172.16.0.50"),
        ]
        resolved = self.mapper.resolve_path_interfaces(
            hops, target_ip="172.16.0.50", source_ip="192.168.1.100"
        )
        flow_lines = self.mapper.format_path_flow(resolved)
        flow_text = "\n".join(flow_lines)

        self.assertIn("R1:Gi0/1 ⇄ R2:Gi0/1", flow_text)
        self.assertIn("R2:Gi0/2 ⇄ R3:port1", flow_text)
        self.assertIn("R3 (IP: 172.16.0.1)", flow_text)
        self.assertIn("[In: port1 | Out: port2]", flow_text)
        self.assertIn("Destination Reached", flow_text)

    def test_two_line_hop_descriptions(self):
        # Verify that each hop has both in_desc and out_desc populated
        hops = [
            (1, "10.0.0.1"),
            (2, "10.0.1.1"),
            (3, "172.16.0.1"),
            (4, "172.16.0.50"),
        ]
        resolved = self.mapper.resolve_path_interfaces(
            hops, target_ip="172.16.0.50", source_ip="192.168.1.100"
        )
        # Hop 1: R1
        self.assertEqual(resolved[0]["in_desc"], "User LAN")
        self.assertEqual(resolved[0]["out_desc"], "Link to R2")
        # Hop 2: R2
        self.assertEqual(resolved[1]["in_desc"], "Link to R1")
        self.assertEqual(resolved[1]["out_desc"], "Link to R3")
        # Hop 3: R3
        self.assertEqual(resolved[2]["in_desc"], "Ingress from R2")
        self.assertEqual(resolved[2]["out_desc"], "Egress to Server Farm")

    def test_streaming_output_display(self):
        # Test trace_to_destination_streaming with mocked execute_traceroute_streaming
        mock_hops = [
            (1, "10.0.0.1"),
            (2, "10.0.1.1"),
            (3, "172.16.0.1"),
            (4, "172.16.0.50"),
        ]
        with patch.object(
            self.mapper, "execute_traceroute_streaming", return_value=iter(mock_hops)
        ), patch.object(self.mapper, "_test_connectivity", return_value=True):
            f = io.StringIO()
            with redirect_stdout(f):
                self.mapper.trace_to_destination_streaming("172.16.0.50")
            output = f.getvalue()

            # Ensure 2-line columns are present in table header
            self.assertIn("Dir", output)
            self.assertIn("Interface", output)
            self.assertIn("Next Hop (In Int)", output)

            # Ensure IN and OUT lines appear for each device hop
            self.assertIn("IN", output)
            self.assertIn("OUT", output)

            # Ensure inbound and outbound descriptions appear
            self.assertIn("(ingress from source)", output)
            self.assertIn("Link to R2", output)
            self.assertIn("Link to R1", output)
            self.assertIn("Link to R3", output)
            self.assertIn("Ingress from R2", output)
            self.assertIn("Egress to Server Farm", output)
            self.assertIn("Destination Endpoint", output)

            # Ensure summary and path flow appear
            self.assertIn("FULL END-TO-END PATH", output)
            self.assertIn("PATH FLOW:", output)

    def test_exact_path_flow_format(self):
        sample_hops = [
            {
                "hop_no": 1,
                "ip": "10.0.0.1",
                "device": "Core-SW",
                "in_iface": "Vlan100",
                "out_iface": "Gi1/0/1",
                "zone": "Trust",
                "next_hop": "Edge-FW:port1",
            },
            {
                "hop_no": 2,
                "ip": "10.0.0.2",
                "device": "Edge-FW",
                "in_iface": "port1",
                "out_iface": "port2",
                "in_zone": "Trust",
                "out_zone": "Untrust",
                "next_hop": "ISP-RTR:Gi0/0",
            },
            {
                "hop_no": 3,
                "ip": "172.16.1.2",
                "device": "ISP-RTR",
                "in_iface": "Gi0/0",
                "out_iface": "Gi0/1",
                "zone": "WAN",
                "next_hop": "Target:172.16.0.50",
            },
            {
                "hop_no": 4,
                "ip": "172.16.0.50",
                "device": "Target",
                "in_iface": "-",
                "out_iface": "Connected/Target",
                "zone": "Server",
                "next_hop": "Destination Reached",
            },
        ]
        lines = self.mapper.format_path_flow(sample_hops)
        flow_output = "\n".join(lines)
        expected = (
            "  [1] Core-SW (IP: 10.0.0.1) [Trust] [In: Vlan100 | Out: Gi1/0/1]\n"
            "       ↳ Link: Core-SW:Gi1/0/1 ⇄ Edge-FW:port1\n"
            "  [2] Edge-FW (IP: 10.0.0.2) [Trust -> Untrust] [In: port1 | Out: port2]\n"
            "       ↳ Link: Edge-FW:port2 ⇄ ISP-RTR:Gi0/0\n"
            "  [3] ISP-RTR (IP: 172.16.1.2) [WAN] [In: Gi0/0 | Out: Gi0/1]\n"
            "       ↳ Link: ISP-RTR:Gi0/1 ⇄ Target:172.16.0.50\n"
            "  [4] Target (IP: 172.16.0.50) [Server] [In: - | Out: Connected/Target]\n"
            "       ↳ Destination Reached (172.16.0.50)"
        )
        self.assertEqual(flow_output, expected)


@unittest.skipUnless(TKINTER_AVAILABLE, "Tkinter is required for GUI tests")
class TestTraceINTGUI(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.mapper = CiscoTracerouteMapper()
        self.gui = TraceINTGUI(self.root, mapper=self.mapper)

    def tearDown(self):
        self.root.destroy()

    def test_gui_columns_and_treeview(self):
        expected_cols = (
            "hop",
            "ip",
            "device",
            "dir",
            "interface",
            "next_hop",
            "zone",
            "vrf",
            "description",
            "extra_info",
        )
        self.assertEqual(self.gui.columns, expected_cols)
        # Verify columns exist on the treeview
        for col in expected_cols:
            self.assertIn(col, self.gui.tree["columns"])

    def test_column_width_adjustability(self):
        # Test manual column width adjustment (dragging column separator)
        self.gui.tree.column("description", width=450)
        self.assertEqual(self.gui.tree.column("description", "width"), 450)

        # Test reset column widths
        self.gui.reset_column_widths()
        self.assertEqual(self.gui.tree.column("description", "width"), 280)

        # Test auto-fit columns with sample data
        sample_hops = [
            {
                "hop_no": 1,
                "ip": "10.0.0.1",
                "device": "Core-SW",
                "in_iface": "Vlan100",
                "out_iface": "Gi1/0/1",
                "zone": "Trust",
                "next_hop": "Edge-FW:port1",
                "in_desc": "User Access Segment with a particularly long text description",
                "out_desc": "Uplink to Edge Firewall",
            }
        ]
        self.gui._render_resolved_table(sample_hops, target_ip="10.0.0.2")
        # Auto-fit should have adjusted the description column wider
        w = self.gui.tree.column("description", "width")
        self.assertGreater(w, 200)

    def test_two_line_hop_rendering_in_table(self):
        sample_hops = [
            {
                "hop_no": 1,
                "ip": "10.0.0.1",
                "device": "Core-SW",
                "in_iface": "Vlan100",
                "out_iface": "Gi1/0/1",
                "zone": "Trust",
                "next_hop": "Edge-FW:port1",
                "in_desc": "User Access Segment",
                "out_desc": "Uplink to Edge Firewall",
            }
        ]
        self.gui._render_resolved_table(sample_hops, target_ip="10.0.0.1")
        items = self.gui.tree.get_children()
        # Should have 2 items (rows) for this hop: 1 IN, 1 OUT
        self.assertEqual(len(items), 2)

        # Row 1: IN
        row1_vals = self.gui.tree.item(items[0], "values")
        self.assertEqual(row1_vals[0], "1")
        self.assertEqual(row1_vals[1], "10.0.0.1")
        self.assertEqual(row1_vals[2], "Core-SW")
        self.assertEqual(row1_vals[3], "IN")
        self.assertEqual(row1_vals[4], "Vlan100")
        self.assertEqual(row1_vals[8], "User Access Segment")

        # Row 2: OUT
        row2_vals = self.gui.tree.item(items[1], "values")
        self.assertEqual(row2_vals[0], "")
        self.assertEqual(row2_vals[3], "OUT")
        self.assertEqual(row2_vals[4], "Gi1/0/1")
        self.assertEqual(row2_vals[5], "Edge-FW:port1")
        self.assertEqual(row2_vals[8], "Uplink to Edge Firewall")

    def test_path_flow_rendering_in_gui(self):
        sample_hops = [
            {
                "hop_no": 1,
                "ip": "10.0.0.1",
                "device": "Core-SW",
                "in_iface": "Vlan100",
                "out_iface": "Gi1/0/1",
                "zone": "Trust",
                "next_hop": "Edge-FW:port1",
            },
            {
                "hop_no": 2,
                "ip": "10.0.0.2",
                "device": "Edge-FW",
                "in_iface": "port1",
                "out_iface": "Connected/Target",
                "zone": "Untrust",
                "next_hop": "Destination Reached",
            },
        ]
        self.gui._render_path_flow(sample_hops)
        flow_text = self.gui.flow_text.get("1.0", "end")
        self.assertIn("PATH FLOW:", flow_text)
        self.assertIn("Core-SW:Gi1/0/1 ⇄ Edge-FW:port1", flow_text)
        self.assertIn("Destination Reached", flow_text)

    def test_gui_transit_subnets_field(self):
        # 1. Default transit subnets displayed
        self.assertEqual(self.gui.transit_subnets_var.get(), "/28, /29, /30, /31")

        # 2. Reconfigure via GUI variable and apply
        self.gui.transit_subnets_var.set("30, 31")
        self.gui._apply_settings_to_mapper()
        self.assertEqual(self.gui.mapper.transit_subnets, {30, 31})
        self.assertEqual(self.gui.transit_subnets_var.get(), "/30, /31")


if __name__ == "__main__":
    unittest.main()


