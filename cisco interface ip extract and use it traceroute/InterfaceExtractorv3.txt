#!/usr/bin/env python3
"""
Network Device Interface Extractor
Extracts interface information from Cisco (IOS/NXOS/IOSXE/EVPN) and Fortigate configuration files
Outputs results to CSV format with device name, interface name, IP address/subnet, and zone
Enhanced with FortiGate VDOM and Zone support with improved zone parsing
Fixed to handle quoted interface names, multiple interfaces per line, and proper whitespace handling
"""

import os
import re
import csv
from typing import List, Dict, Optional


class NetworkConfigParser:
    def __init__(self):
        self.interface_data = []
        self.device_zones = {}  # device_name -> { "vdom::interface": zone_name }

    def parse_device_and_vdom_from_filename(self, filepath: str) -> tuple:
        """
        Extract device name and VDOM name from filename convention:
        e.g. 'hk1-aaa_AWS.set' -> ('hk1-aaa', 'AWS')
             'hk1-aaa_root.set' -> ('hk1-aaa', 'root')
             'standalone_firewall.txt' -> ('standalone_firewall', 'root')
        """
        base = os.path.splitext(os.path.basename(filepath))[0]
        non_vdom_words = {'firewall', 'switch', 'router', 'backup', 'config', 'cfg', 'extractor', 'network'}
        if "_" in base:
            parts = base.rsplit("_", 1)
            if parts[0] and parts[1] and parts[1].lower() not in non_vdom_words:
                return parts[0].strip(), parts[1].strip()
        return base.strip(), "root"

    def extract_hostname_cisco(self, content: str) -> str:
        """Extract hostname from Cisco configuration"""
        # Look for hostname command (most common)
        hostname_patterns = [
            r'^hostname\s+(\S+)',
            r'^\s*hostname\s+(\S+)',
            # Also look for it in show commands output
            r'^(\S+)#\s*show',
            r'^(\S+)>\s*show',
            # From configuration mode prompts
            r'^(\S+)\(config\)#',
            # From show version output
            r'(\S+)\s+uptime\s+is',
        ]

        for pattern in hostname_patterns:
            hostname_match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if hostname_match:
                hostname = hostname_match.group(1)
                # Clean up common suffixes
                hostname = re.sub(r'[>#]$', '', hostname)
                if hostname and hostname != 'Router' and hostname != 'Switch':
                    return hostname

        return "Unknown"

    def extract_hostname_fortigate(self, content: str, filepath: Optional[str] = None) -> str:
        """Extract hostname from Fortigate configuration with filename fallback"""
        # Look for set hostname command
        hostname_match = re.search(r'set hostname\s+"?([^"\n]+)"?', content, re.IGNORECASE)
        if hostname_match:
            return hostname_match.group(1).strip('"')

        # Fallback to filename prefix before _ (e.g. hk1-aaa_AWS.set -> hk1-aaa)
        if filepath:
            dev_name, _ = self.parse_device_and_vdom_from_filename(filepath)
            if dev_name and dev_name != "Unknown":
                return dev_name

        return "Unknown"

    def extract_global_zones(self, content: str) -> Dict[str, str]:
        """
        Extract interface-to-zone mappings from global FortiGate config (non-VDOM).
        Returns a dictionary mapping 'root::interface' -> zone name.
        """
        zones = {}

        # Look for global config system zone (outside of VDOM)
        zone_section_match = re.search(
            r'config\s+system\s+zone\s*\n(.*?)\n\s*end',
            content,
            flags=re.DOTALL | re.IGNORECASE
        )

        if not zone_section_match:
            print("    Debug: No global zones found")
            return zones

        zone_section = zone_section_match.group(1)
        print("    Debug: Processing global zones")

        # Extract individual zone entries
        zone_blocks = re.findall(
            r'edit\s+"?([^\s"\n]+)"?\s*\n(.*?)\n\s*next',
            zone_section,
            flags=re.DOTALL | re.IGNORECASE
        )

        for zone_name, zone_body in zone_blocks:
            print(f"      Debug: Processing global zone '{zone_name}'")

            # Find set interface lines and parse interfaces
            interface_lines = re.findall(
                r'set\s+interface\s+(.+)',
                zone_body,
                flags=re.IGNORECASE
            )

            for line in interface_lines:
                interfaces = self.parse_interface_list(line)
                for iface in interfaces:
                    iface_clean = iface.strip('"')
                    zone_key = f"root::{iface_clean}"
                    zones[zone_key] = zone_name
                    print(f"        Debug: {zone_key} -> {zone_name}")

        return zones

    def extract_zones_from_content(self, content: str, vdom_name: str, zones: Dict[str, str]) -> bool:
        """Extract zones from a content block with flexible whitespace handling"""
        found_zones = False

        # Find all 'config system zone' blocks with flexible whitespace
        zone_config_pattern = r'^\s*config\s+system\s+zone\s*$'
        zone_matches = list(re.finditer(zone_config_pattern, content, re.MULTILINE | re.IGNORECASE))

        for zone_match in zone_matches:
            zone_start = zone_match.end()
            remaining_content = content[zone_start:]

            # Find the 'end' for this zone config
            end_pattern = r'^\s*end\s*$'
            end_match = re.search(end_pattern, remaining_content, re.MULTILINE | re.IGNORECASE)

            if end_match:
                zone_section = remaining_content[:end_match.start()]
            else:
                zone_section = remaining_content

            print(f"      Debug: Found zone config section in VDOM '{vdom_name}' (length: {len(zone_section)})")

            # Extract individual zone entries
            zone_edit_pattern = r'^\s*edit\s+"?([^\s"\n\r]+)"?\s*$'
            zone_entries = re.finditer(zone_edit_pattern, zone_section, re.MULTILINE | re.IGNORECASE)

            for zone_entry in zone_entries:
                zone_name = zone_entry.group(1).strip('"')
                zone_content_start = zone_entry.end()

                # Find the end of this zone entry
                remaining_zone = zone_section[zone_content_start:]
                next_pattern = r'^\s*next\s*$'
                next_match = re.search(next_pattern, remaining_zone, re.MULTILINE | re.IGNORECASE)

                if next_match:
                    zone_content = remaining_zone[:next_match.start()]
                else:
                    zone_content = remaining_zone

                print(f"        Debug: Processing zone '{zone_name}' in VDOM '{vdom_name}'")

                # Find interface assignments with flexible whitespace
                interface_pattern = r'^\s*set\s+interface\s+(.+)$'
                interface_matches = re.findall(interface_pattern, zone_content, re.MULTILINE | re.IGNORECASE)

                for interface_line in interface_matches:
                    interfaces = self.parse_interface_list(interface_line)
                    for iface in interfaces:
                        iface_clean = iface.strip('"').strip()
                        zone_key = f"{vdom_name}::{iface_clean}"
                        zones[zone_key] = zone_name
                        print(f"          Debug: {zone_key} -> {zone_name}")
                        found_zones = True

        return found_zones

    def extract_vdom_zones(self, content: str, zones: Dict[str, str]) -> bool:
        """Extract zones from VDOM configurations with flexible whitespace handling"""
        found_vdom_zones = False

        # Find all VDOM blocks with flexible whitespace
        # Look for: config vdom (with any whitespace)
        vdom_start_pattern = r'^\s*config\s+vdom\s*$'
        vdom_matches = list(re.finditer(vdom_start_pattern, content, re.MULTILINE | re.IGNORECASE))

        if not vdom_matches:
            print("    Debug: No 'config vdom' sections found")
            return False

        for vdom_match in vdom_matches:
            vdom_start = vdom_match.end()

            # Find the end of this VDOM section (next 'config' at same level or end of file)
            remaining_content = content[vdom_start:]

            # Find end pattern - either 'end' or next config at root level
            end_pattern = r'^\s*end\s*$'
            end_match = re.search(end_pattern, remaining_content, re.MULTILINE | re.IGNORECASE)

            if end_match:
                vdom_section = remaining_content[:end_match.start()]
            else:
                vdom_section = remaining_content

            print(f"    Debug: Processing VDOM section (length: {len(vdom_section)})")

            # Find individual VDOM entries with flexible whitespace
            vdom_edit_pattern = r'^\s*edit\s+"?([^\s"\n\r]+)"?\s*$'
            vdom_entries = re.finditer(vdom_edit_pattern, vdom_section, re.MULTILINE | re.IGNORECASE)

            for vdom_entry in vdom_entries:
                vdom_name = vdom_entry.group(1).strip('"')
                vdom_content_start = vdom_entry.end()

                # Find the end of this VDOM entry (next 'next' at same indentation level)
                remaining_vdom = vdom_section[vdom_content_start:]

                # Find next 'next' or end of section
                next_pattern = r'^\s*next\s*$'
                next_match = re.search(next_pattern, remaining_vdom, re.MULTILINE | re.IGNORECASE)

                if next_match:
                    vdom_content = remaining_vdom[:next_match.start()]
                else:
                    vdom_content = remaining_vdom

                print(f"    Debug: Processing VDOM '{vdom_name}' (content length: {len(vdom_content)})")

                # Extract zones from this VDOM content
                if self.extract_zones_from_content(vdom_content, vdom_name, zones):
                    found_vdom_zones = True

        return found_vdom_zones

    def extract_global_zones_flexible(self, content: str, zones: Dict[str, str]) -> bool:
        """Extract global zones (outside VDOMs) with flexible whitespace handling"""
        found_global_zones = False

        # Look for config system zone that's not inside a VDOM
        # This is more complex - we need to find zones that are at root level

        # Split content into lines for analysis
        lines = content.split('\n')
        in_vdom = False
        vdom_depth = 0

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            line_lower = line.lower()

            # Track VDOM depth
            if re.match(r'config\s+vdom\s*$', line, re.IGNORECASE):
                in_vdom = True
                vdom_depth = 1
            elif in_vdom and line_lower == 'end':
                vdom_depth -= 1
                if vdom_depth <= 0:
                    in_vdom = False
            elif in_vdom and line_lower.startswith('config'):
                vdom_depth += 1

            # Look for zone config outside VDOM
            if not in_vdom and re.match(r'config\s+system\s+zone\s*$', line, re.IGNORECASE):
                print("      Debug: Found global zone configuration")

                # Extract this zone section
                zone_start = i + 1
                zone_end = zone_start
                zone_depth = 1

                # Find the end of this zone config
                j = zone_start
                while j < len(lines) and zone_depth > 0:
                    zone_line = lines[j].strip().lower()
                    if zone_line == 'end':
                        zone_depth -= 1
                    elif zone_line.startswith('config'):
                        zone_depth += 1
                    j += 1
                    if zone_depth == 0:
                        zone_end = j - 1
                        break

                # Process the zone section
                zone_content = '\n'.join(lines[zone_start:zone_end])
                if self.extract_zones_from_content(zone_content, "root", zones):
                    found_global_zones = True

                i = zone_end
            else:
                i += 1

        return found_global_zones

    def extract_all_zone_configs(self, content: str, zones: Dict[str, str]) -> None:
        """Fallback method to find any missed zone configurations"""
        # Look specifically inside zone contexts to avoid capturing VDOM edit blocks
        zone_sections = re.findall(
            r'config\s+system\s+zone\s*\n?(.*?)(?=\n\s*(?:config\s+(?!system\s+zone)|end\s*$|\Z))',
            content,
            re.DOTALL | re.IGNORECASE
        )
        for section in zone_sections:
            entries = re.finditer(
                r'edit\s+"?([^"\r\n]+?)"?\s*(?:set\s+.*?)*?set\s+interface\s+([^\r\n]+)',
                section,
                re.IGNORECASE
            )
            for entry in entries:
                zone_name = entry.group(1).strip('"\'').strip()
                iface_line = entry.group(2)
                iface_line = re.split(r'\s+(?:next|end|config|edit|set)\b|;', iface_line, flags=re.IGNORECASE)[0]
                interfaces = self.parse_interface_list(iface_line)
                for iface in interfaces:
                    iface_clean = iface.strip('"\'').strip()
                    zone_key = f"unknown::{iface_clean}"
                    if zone_key not in zones and not any(k.endswith(f"::{iface_clean}") for k in zones):
                        zones[zone_key] = zone_name
                        print(f"          Debug: Fallback found: {zone_key} -> {zone_name}")

    def parse_interface_list(self, interface_line: str) -> List[str]:
        """Parse a line containing one or more interfaces, handling quotes properly"""
        interfaces = []

        # Remove extra whitespace
        interface_line = interface_line.strip()

        # Pattern to match quoted and unquoted interface names
        # This handles: "LAG1.101" "LAG1.201" "LAG1.301" or LAG1.101 LAG1.201 LAG1.301
        interface_pattern = r'"([^"]+)"|(\S+)'

        matches = re.findall(interface_pattern, interface_line)

        for match in matches:
            # match is a tuple: (quoted_content, unquoted_content)
            interface_name = match[0] if match[0] else match[1]
            if interface_name:
                interfaces.append(interface_name.strip('"\'').strip())

        return interfaces

    def get_zone_for_interface(self, interface_name: str, vdom_name: str, zones: Dict[str, str], return_vdom: bool = False):
        """
        Get zone for interface with fallback to root VDOM and cross-VDOM resolution
        (supports configurations where IP is in root and zones are in another VDOM).
        Supports case-insensitive lookup.
        """
        # Priority order for zone lookup:
        # 1. Exact VDOM match
        # 2. Root VDOM (fallback)
        # 3. Cross-VDOM match (find any VDOM that maps this interface to a zone)
        # 4. Unknown VDOM (last resort)

        possible_keys = [
            f"{vdom_name}::{interface_name}",  # Exact VDOM match
            f"root::{interface_name}",          # Root VDOM fallback
            f"unknown::{interface_name}"       # Last resort fallback
        ]

        print(f"        Debug: Looking for zone mapping for interface '{interface_name}' in VDOM '{vdom_name}'")
        print(f"        Debug: Available zone mappings: {list(zones.keys())}")

        # 1. Exact match check
        for i, key in enumerate(possible_keys):
            if key in zones:
                zone_name = zones[key]
                fallback_info = ""
                resolved_v = vdom_name
                if i == 1:  # Root VDOM fallback was used
                    fallback_info = " (fallback from root)"
                    resolved_v = "root"
                elif i == 2:  # Unknown fallback was used
                    fallback_info = " (unknown fallback)"

                print(f"        Debug: Found zone mapping {key} -> {zone_name}{fallback_info}")
                return (zone_name, resolved_v) if return_vdom else zone_name

        # 2. Cross-VDOM match: check if interface is mapped to a zone in any other VDOM for this firewall
        for k, z_val in zones.items():
            if "::" in k:
                kvdom, kiface = k.split("::", 1)
                if kiface.lower() == interface_name.lower():
                    print(f"        Debug: Found cross-file/cross-VDOM zone mapping {k} -> {z_val}")
                    return (z_val, kvdom) if return_vdom else z_val

        # 3. Case-insensitive match fallback
        for i, key in enumerate(possible_keys):
            key_lower = key.lower()
            for z_key, z_val in zones.items():
                if z_key.lower() == key_lower:
                    fallback_info = f" (case-insensitive from {z_key})"
                    print(f"        Debug: Found zone mapping {key} -> {z_val}{fallback_info}")
                    resolved_v = "root" if i == 1 else vdom_name
                    return (z_val, resolved_v) if return_vdom else z_val

        print(f"        Debug: Interface '{interface_name}' not found in zones for VDOM '{vdom_name}'")
        return ("No Zone", vdom_name) if return_vdom else "No Zone"

    def _retroactive_zone_resolution(self, hostname: str) -> None:
        """Updates previously extracted interface records if their zone is now known from another file."""
        if hostname not in self.device_zones:
            return
        device_zones = self.device_zones[hostname]

        for item in self.interface_data:
            dev_name = item.get("device_name", "")
            if dev_name == hostname or dev_name.startswith(f"{hostname} (VDOM:"):
                if item.get("zone") in ("No Zone", "N/A", ""):
                    iface_name = item.get("interface_name", "")
                    vdom = "root"
                    vdom_m = re.search(r'\(VDOM:\s*([^)]+)\)', dev_name)
                    if vdom_m:
                        vdom = vdom_m.group(1).strip()

                    new_zone, resolved_vdom = self.get_zone_for_interface(iface_name, vdom, device_zones, return_vdom=True)
                    if new_zone != "No Zone":
                        item["zone"] = new_zone
                        if resolved_vdom != "root":
                            item["device_name"] = f"{hostname} (VDOM: {resolved_vdom})"
                        print(f"        Debug: Retroactive cross-file resolution: {iface_name} -> {new_zone} (VDOM: {resolved_vdom})")

    def parse_fortigate_interfaces(self, content: str, hostname: str, default_vdom: str = "root", filepath: Optional[str] = None) -> List[Dict]:
        """Parse Fortigate interface configurations with cross-file VDOM and zone support"""
        interfaces = []

        # Extract zones from this config with default_vdom context
        file_zones = self.extract_fortigate_zones(content, default_vdom=default_vdom)

        # Record in device_zones for cross-file correlation
        if hostname not in self.device_zones:
            self.device_zones[hostname] = {}
        self.device_zones[hostname].update(file_zones)

        zones = self.device_zones[hostname]

        # Find interface configurations - improved pattern to handle the entire config structure
        interface_pattern = r'config\s+system\s+interface\s*\n(.*?)(?=^config\s+(?!system\s+interface)|\Z)'
        interface_match = re.search(interface_pattern, content, re.MULTILINE | re.DOTALL | re.IGNORECASE)

        if not interface_match:
            print("    No 'config system interface' section found")
            return interfaces

        interface_section = interface_match.group(1)
        print(f"    Debug: Interface section length: {len(interface_section)} characters")

        # Split by 'next' to get individual interface blocks
        parts = re.split(r'^\s*next\s*$', interface_section, flags=re.MULTILINE)

        interface_blocks = []
        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Look for edit command at the beginning of the block - handle whitespace
            edit_match = re.match(r'^\s*edit\s+"?([^"\n\s]+)"?\s*\n(.*)', part, re.DOTALL | re.IGNORECASE)
            if edit_match:
                interface_name = edit_match.group(1).strip('"')
                interface_config = edit_match.group(2)
                interface_blocks.append((interface_name, interface_config))

        print(f"    Debug: Found {len(interface_blocks)} interface blocks")

        for interface_name, interface_config in interface_blocks:
            print(f"      Debug: Processing interface '{interface_name}'")

            # Extract VDOM from interface config, falling back to default_vdom
            vdom_match = re.search(r'^\s*set\s+vdom\s+"?([^"\n\s]+)"?', interface_config, re.MULTILINE | re.IGNORECASE)
            vdom_name = vdom_match.group(1).strip('"') if vdom_match else default_vdom

            # Look for IP configuration - improved patterns
            ip_patterns = [
                r'^\s*set\s+ip\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)',  # Standard format
                r'^\s*set\s+ip\s+(\d+\.\d+\.\d+\.\d+)/(\d+)',  # CIDR format
            ]

            ip_found = False
            for pattern in ip_patterns:
                ip_matches = re.findall(pattern, interface_config, re.MULTILINE | re.IGNORECASE)

                for match in ip_matches:
                    ip, mask_or_cidr = match

                    # Skip if IP address is 0.0.0.0 (unassigned/invalid)
                    if ip == "0.0.0.0":
                        print(f"        Skipping unassigned IP 0.0.0.0 on {interface_name}")
                        continue

                    # Check if it's CIDR or netmask
                    if mask_or_cidr.isdigit() and int(mask_or_cidr) <= 32:
                        # It's CIDR
                        ip_with_cidr = f"{ip}/{mask_or_cidr}"
                    else:
                        # It's netmask
                        cidr = self.netmask_to_cidr(mask_or_cidr)
                        ip_with_cidr = f"{ip}/{cidr}"

                    # Extract description
                    description = "N/A"
                    desc_match = re.search(r'^\s*set\s+description\s+"?([^"\n]+)"?', interface_config, re.MULTILINE | re.IGNORECASE)
                    if desc_match:
                        description = desc_match.group(1).strip()

                    # Get zone for this interface using enhanced lookup with cross-VDOM support
                    zone_name, resolved_vdom = self.get_zone_for_interface(interface_name, vdom_name, zones, return_vdom=True)
                    active_vdom = resolved_vdom if (resolved_vdom and resolved_vdom != "root") else vdom_name

                    # Create device name with VDOM
                    if active_vdom != "root":
                        device_name = f"{hostname} (VDOM: {active_vdom})"
                    else:
                        device_name = hostname

                    interfaces.append({
                        'device_name': device_name,
                        'interface_name': interface_name,
                        'ip_address': ip_with_cidr,
                        'vrf': "N/A",  # Fortigate uses VDOMs, not VRFs in the same way
                        'zone': zone_name,
                        'description': description
                    })

                    print(
                        f"        Found IP: {ip_with_cidr} on {interface_name} (Zone: {zone_name}, VDOM: {vdom_name})")
                    ip_found = True

            if not ip_found:
                # Check for DHCP configuration
                dhcp_match = re.search(r'^\s*set\s+mode\s+dhcp', interface_config, re.MULTILINE | re.IGNORECASE)
                if dhcp_match:
                    # Get zone for this interface using enhanced lookup with fallback
                    zone_name = self.get_zone_for_interface(interface_name, vdom_name, zones)

                    device_name = f"{hostname} (VDOM: {vdom_name})" if vdom_name != "root" else hostname

                    # Extract description
                    description = "N/A"
                    desc_match = re.search(r'^\s*set\s+description\s+"?([^"\n]+)"?', interface_config, re.MULTILINE | re.IGNORECASE)
                    if desc_match:
                        description = desc_match.group(1).strip()

                    interfaces.append({
                        'device_name': device_name,
                        'interface_name': interface_name,
                        'ip_address': "DHCP",
                        'vrf': "N/A",
                        'zone': zone_name,
                        'description': description
                    })

                    print(f"        Found DHCP mode on {interface_name} (Zone: {zone_name}, VDOM: {vdom_name})")
                    ip_found = True

                # Check for PPPoE configuration
                if not ip_found:
                    pppoe_match = re.search(r'^\s*set\s+mode\s+pppoe', interface_config, re.MULTILINE | re.IGNORECASE)
                    if pppoe_match:
                        # Get zone for this interface using enhanced lookup with fallback
                        zone_name = self.get_zone_for_interface(interface_name, vdom_name, zones)

                        device_name = f"{hostname} (VDOM: {vdom_name})" if vdom_name != "root" else hostname

                        # Extract description
                        description = "N/A"
                        desc_match = re.search(r'^\s*set\s+description\s+"?([^"\n]+)"?', interface_config, re.MULTILINE | re.IGNORECASE)
                        if desc_match:
                            description = desc_match.group(1).strip()

                        interfaces.append({
                            'device_name': device_name,
                            'interface_name': interface_name,
                            'ip_address': "PPPoE",
                            'vrf': "N/A",
                            'zone': zone_name,
                            'description': description
                        })

                        print(f"        Found PPPoE mode on {interface_name} (Zone: {zone_name}, VDOM: {vdom_name})")
                        ip_found = True

                if not ip_found:
                    print(f"        No IP configuration found for {interface_name}")

        return interfaces

    def extract_fortigate_zones(self, content: str, default_vdom: str = "root") -> Dict[str, str]:
        """
        Extract interface-to-zone mappings from FortiGate config,
        including zones defined inside each VDOM and inline / single-line commands.
        Returns a dictionary mapping 'vdom::interface' -> zone name.
        Handles commands such as:
          - config vdom edit App config system zone edit "AAA-Zone" set interface VL1.1234
          - config vdom edit App config system zone edit "AAA-Zone" set interface "LAG1.1111"
        as well as standard multi-line nested FortiGate configurations and file-level VDOM defaults.
        """
        zones = {}

        # 1. Check line-by-line for inline / chained commands
        for line in content.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith('#') or line_str.startswith('!'):
                continue

            # Inline command with VDOM and Zone
            vdom_match = re.search(
                r'config\s+vdom\s+edit\s+"?([^"\s]+)"?.*?'
                r'config\s+system\s+zone\s+edit\s+"?([^"\r\n]+?)"?\s+'
                r'set\s+interface\s+(.+)',
                line_str, re.IGNORECASE
            )
            if vdom_match:
                vdom_name = vdom_match.group(1).strip('"\'').strip()
                zone_name = vdom_match.group(2).strip('"\'').strip()
                iface_part = vdom_match.group(3)
                iface_part = re.split(r'\s+(?:next|end|config|edit|set)\b|;', iface_part, flags=re.IGNORECASE)[0]
                interfaces = self.parse_interface_list(iface_part)
                for iface in interfaces:
                    if iface:
                        zone_key = f"{vdom_name}::{iface}"
                        zones[zone_key] = zone_name
                        print(f"      Debug: Inline VDOM zone found: {zone_key} -> {zone_name}")
                continue

            # Inline command for global zone (uses default_vdom from file context if provided)
            global_match = re.search(
                r'config\s+system\s+zone\s+edit\s+"?([^"\r\n]+?)"?\s+'
                r'set\s+interface\s+(.+)',
                line_str, re.IGNORECASE
            )
            if global_match:
                zone_name = global_match.group(1).strip('"\'').strip()
                iface_part = global_match.group(2)
                iface_part = re.split(r'\s+(?:next|end|config|edit|set)\b|;', iface_part, flags=re.IGNORECASE)[0]
                interfaces = self.parse_interface_list(iface_part)
                for iface in interfaces:
                    if iface:
                        zone_key = f"{default_vdom}::{iface}"
                        if zone_key not in zones:
                            zones[zone_key] = zone_name
                            print(f"      Debug: Inline Global zone found: {zone_key} -> {zone_name}")
                continue

        # 2. Tokenized state machine for structured / multi-line nested blocks
        tokens = re.findall(r'"[^"]*"|\'[^\']*\'|\S+', content)
        current_vdom = default_vdom
        config_stack = []
        current_zone = None

        i = 0
        n = len(tokens)
        while i < n:
            tok = tokens[i].lower()

            if tok == "config":
                i += 1
                if i < n:
                    sec_parts = [tokens[i]]
                    i += 1
                    while i < n and tokens[i].lower() not in ("edit", "set", "unset", "config", "next", "end"):
                        sec_parts.append(tokens[i])
                        i += 1
                    sec_name = " ".join(sec_parts).lower()
                    if sec_name == "vdom" and "vdom" in config_stack:
                        while config_stack and config_stack[-1] != "vdom":
                            config_stack.pop()
                    config_stack.append(sec_name)
                    continue

            elif tok == "edit":
                i += 1
                if i < n:
                    name = tokens[i].strip("\"'")
                    i += 1
                    current_section = config_stack[-1] if config_stack else ""
                    if current_section == "vdom":
                        current_vdom = name
                    elif "zone" in current_section:
                        current_zone = name
                    continue

            elif tok == "set":
                i += 1
                if i < n:
                    field = tokens[i].lower()
                    i += 1
                    vals = []
                    while i < n and tokens[i].lower() not in ("set", "unset", "edit", "config", "next", "end"):
                        vals.append(tokens[i].strip("\"'"))
                        i += 1
                    current_section = config_stack[-1] if config_stack else ""
                    if "zone" in current_section and current_zone and field == "interface":
                        for iface in vals:
                            if iface:
                                zone_key = f"{current_vdom}::{iface}"
                                if zone_key not in zones:
                                    zones[zone_key] = current_zone
                                    print(f"      Debug: State machine zone found: {zone_key} -> {current_zone}")
                    continue

            elif tok == "next":
                i += 1
                current_section = config_stack[-1] if config_stack else ""
                if "zone" in current_section:
                    current_zone = None
                elif current_section == "vdom":
                    current_vdom = default_vdom
                continue

            elif tok == "end":
                i += 1
                if config_stack:
                    popped = config_stack.pop()
                    if "zone" in popped:
                        current_zone = None
                    elif popped == "vdom":
                        current_vdom = default_vdom
                continue

            else:
                i += 1

        # 3. Fallback search for any missed zone configurations
        self.extract_all_zone_configs(content, zones)

        print(f"    Debug: Total interface-to-zone mappings: {len(zones)}")
        return zones
    def parse_cisco_interfaces(self, content: str, hostname: str) -> List[Dict]:
        """Parse Cisco interface configurations"""
        interfaces = []

        # Enhanced regex to capture interface blocks more accurately
        interface_pattern = r'^interface\s+([^\r\n]+)\r?\n((?:(?!^interface\s+|^!).*\r?\n?)*)'
        interface_blocks = re.findall(interface_pattern, content, re.MULTILINE | re.IGNORECASE)

        print(f"    Debug: Found {len(interface_blocks)} interface blocks")

        for interface_line, block_content in interface_blocks:
            # Clean up interface name
            interface_name = interface_line.strip()
            interface_name = re.sub(r'\s+', '', interface_name)

            print(f"    Debug: Processing interface '{interface_name}'")

            # Combine interface line with block content for IP search
            full_block = interface_line + '\n' + block_content

            # Extract description
            description = "N/A"
            desc_match = re.search(r'^\s*description\s+(.+)$', block_content, re.MULTILINE | re.IGNORECASE)
            if desc_match:
                description = desc_match.group(1).strip()

            # Extract VRF
            vrf = "Global"
            vrf_match = re.search(r'^\s*(?:ip\s+)?vrf\s+(?:forwarding|member)\s+(\S+)', block_content, re.MULTILINE | re.IGNORECASE)
            if vrf_match:
                vrf = vrf_match.group(1).strip()

            # Multiple IP address patterns
            ip_patterns = [
                r'ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)(?!\s+secondary)',
                r'ip\s+address\s+(\d+\.\d+\.\d+\.\d+)/(\d+)',
                r'ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s*$'
            ]

            # Secondary IP pattern
            secondary_pattern = r'ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+secondary'

            # Search for primary IP addresses
            found_ip = False
            for pattern in ip_patterns:
                matches = re.findall(pattern, full_block, re.MULTILINE | re.IGNORECASE)
                for match in matches:
                    ip, mask_or_cidr = match

                    if ip == "0.0.0.0":
                        continue

                    # Check if it's CIDR or netmask
                    if mask_or_cidr.isdigit() and int(mask_or_cidr) <= 32:
                        ip_with_cidr = f"{ip}/{mask_or_cidr}"
                    else:
                        cidr = self.netmask_to_cidr(mask_or_cidr)
                        ip_with_cidr = f"{ip}/{cidr}"

                    interfaces.append({
                        'device_name': hostname,
                        'interface_name': interface_name,
                        'ip_address': ip_with_cidr,
                        'vrf': vrf,
                        'zone': "N/A",  # Cisco doesn't use zones like FortiGate
                        'description': description
                    })
                    found_ip = True

            # Search for secondary IP addresses
            secondary_matches = re.findall(secondary_pattern, full_block, re.MULTILINE | re.IGNORECASE)
            for ip, mask in secondary_matches:
                if ip == "0.0.0.0":
                    continue

                cidr = self.netmask_to_cidr(mask)
                interfaces.append({
                    'device_name': hostname,
                    'interface_name': interface_name,
                    'ip_address': f"{ip}/{cidr} (secondary)",
                    'vrf': vrf,
                    'zone': "N/A",
                    'description': description
                })
                found_ip = True

            if found_ip:
                print(f"    Debug: Interface {interface_name} has IP configuration")

        return interfaces

    def parse_cisco_evpn(self, content: str, hostname: str) -> List[Dict]:
        """Parse Cisco EVPN and additional interface configurations"""
        interfaces = []

        # EVPN Configuration Profile Pattern
        evpn_profile_pattern = r'configure\s+profile\s+([^\r\n]+)\r?\n(.*?)(?=^configure\s+profile|^interface\s+|^!\s*$|\Z)'
        evpn_profiles = re.findall(evpn_profile_pattern, content, re.MULTILINE | re.DOTALL | re.IGNORECASE)

        print(f"    Debug: Found {len(evpn_profiles)} EVPN configuration profiles")

        for profile_name, profile_content in evpn_profiles:
            print(f"    Debug: Processing EVPN profile '{profile_name.strip()}'")

            # Look for VLAN number in the profile
            vlan_match = re.search(r'vlan\s+(\d+)', profile_content, re.IGNORECASE)
            if not vlan_match:
                continue

            vlan_num = vlan_match.group(1)

            # Look for interface vlan configuration within the profile
            vlan_interface_pattern = r'interface\s+vlan\s*(\d+)\s*\r?\n(.*?)(?=\s*interface\s+|\s*evpn\s*$|\Z)'
            vlan_interfaces = re.findall(vlan_interface_pattern, profile_content,
                                         re.MULTILINE | re.DOTALL | re.IGNORECASE)

            for vlan_interface_num, vlan_config in vlan_interfaces:
                # Extract IP address from VLAN interface config
                ip_patterns = [
                    r'ip\s+address\s+(\d+\.\d+\.\d+\.\d+)/(\d+)',
                    r'ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)',
                ]

                found_ip = False
                for pattern in ip_patterns:
                    ip_matches = re.findall(pattern, vlan_config, re.MULTILINE | re.IGNORECASE)

                    for match in ip_matches:
                        ip, mask_or_cidr = match

                        if ip == "0.0.0.0":
                            continue

                        # Check if it's CIDR or netmask
                        if mask_or_cidr.isdigit() and int(mask_or_cidr) <= 32:
                            ip_with_cidr = f"{ip}/{mask_or_cidr}"
                        else:
                            cidr = self.netmask_to_cidr(mask_or_cidr)
                            ip_with_cidr = f"{ip}/{cidr}"

                        # Extract description
                        description = "N/A"
                        desc_match = re.search(r'^\s*description\s+(.+)$', vlan_config, re.MULTILINE | re.IGNORECASE)
                        if desc_match:
                            description = desc_match.group(1).strip()

                        # Extract additional info
                        additional_info = []

                        vrf = "Global"
                        vrf_match = re.search(r'vrf\s+member\s+(\S+)', vlan_config, re.IGNORECASE)
                        if vrf_match:
                            vrf = vrf_match.group(1)
                            # additional_info.append(f"VRF:{vrf_match.group(1)}") # Moved to dedicated field

                        # Look for IP tags
                        tag_match = re.search(r'tag\s+(\d+)', vlan_config, re.IGNORECASE)
                        if tag_match:
                            additional_info.append(f"Tag:{tag_match.group(1)}")

                        # Look for VN-segment from the profile
                        vn_segment_match = re.search(r'vn-segment\s+(\d+)', profile_content, re.IGNORECASE)
                        if vn_segment_match:
                            additional_info.append(f"VNI:{vn_segment_match.group(1)}")

                        # Build interface name with additional info
                        interface_name = f"Vlan{vlan_interface_num}"
                        if additional_info:
                            interface_name += f" ({', '.join(additional_info)})"

                        interfaces.append({
                            'device_name': hostname,
                            'interface_name': interface_name,
                            'ip_address': ip_with_cidr,
                            'vrf': vrf,
                            'zone': "N/A",
                            'description': description
                        })

                        found_ip = True

        # Additional patterns for standalone interfaces
        additional_interface_patterns = [
            (r'interface\s+[Vv]lan\s*(\d+)\s*\r?\n(.*?)(?=^interface\s+|^!\s*$|\Z)', 'Vlan'),
            (r'interface\s+[Tt]unnel\s*(\d+)\s*\r?\n(.*?)(?=^interface\s+|^!\s*$|\Z)', 'Tunnel'),
            (r'interface\s+[Pp]ort-channel\s*(\d+)\s*\r?\n(.*?)(?=^interface\s+|^!\s*$|\Z)', 'Port-channel'),
            (r'interface\s+[Mm]anagement\s*(\d+)\s*\r?\n(.*?)(?=^interface\s+|^!\s*$|\Z)', 'Management'),
            (r'interface\s+[Mm]gmt\s*(\d+)\s*\r?\n(.*?)(?=^interface\s+|^!\s*$|\Z)', 'Mgmt'),
            (r'interface\s+[Bb][Vv][Ii]\s*(\d+)\s*\r?\n(.*?)(?=^interface\s+|^!\s*$|\Z)', 'BVI'),
            (r'interface\s+[Ll]oopback\s*(\d+)\s*\r?\n(.*?)(?=^interface\s+|^!\s*$|\Z)', 'Loopback'),
            (r'interface\s+[Nn][Vv][Ee]\s*(\d+)\s*\r?\n(.*?)(?=^interface\s+|^!\s*$|\Z)', 'NVE'),
        ]

        for pattern, interface_type in additional_interface_patterns:
            matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL | re.IGNORECASE)

            for interface_num, interface_config in matches:
                interface_name = f"{interface_type}{interface_num}"

                # Skip if already processed
                already_processed = any(iface['interface_name'] == interface_name for iface in interfaces)
                if already_processed:
                    continue

                # Look for IP addresses
                ip_patterns = [
                    r'ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)(?!\s+secondary)',
                    r'ip\s+address\s+(\d+\.\d+\.\d+\.\d+)/(\d+)',
                ]

                secondary_pattern = r'ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+secondary'

                found_ip = False

                # Search for primary IP addresses
                for ip_pattern in ip_patterns:
                    ip_matches = re.findall(ip_pattern, interface_config, re.MULTILINE | re.IGNORECASE)
                    for ip, mask_or_cidr in ip_matches:
                        if ip == "0.0.0.0":
                            continue

                        if mask_or_cidr.isdigit() and int(mask_or_cidr) <= 32:
                            ip_with_cidr = f"{ip}/{mask_or_cidr}"
                        else:
                            cidr = self.netmask_to_cidr(mask_or_cidr)
                            ip_with_cidr = f"{ip}/{cidr}"

                        # Extract description
                        description = "N/A"
                        desc_match = re.search(r'^\s*description\s+(.+)$', interface_config, re.MULTILINE | re.IGNORECASE)
                        if desc_match:
                            description = desc_match.group(1).strip()

                        # Extract additional information
                        additional_info = []

                        vrf = "Global"
                        vrf_match = re.search(r'vrf\s+member\s+(\S+)', interface_config, re.IGNORECASE)
                        if not vrf_match:
                             # Try ip vrf forwarding
                             vrf_match = re.search(r'(?:ip\s+)?vrf\s+forwarding\s+(\S+)', interface_config, re.IGNORECASE)

                        if vrf_match:
                            vrf = vrf_match.group(1)
                            # additional_info.append(f"VRF:{vrf_match.group(1)}") # Moved to dedicated field

                        tag_match = re.search(r'tag\s+(\d+)', interface_config, re.IGNORECASE)
                        if tag_match:
                            additional_info.append(f"Tag:{tag_match.group(1)}")

                        final_interface_name = interface_name
                        if additional_info:
                            final_interface_name += f" ({', '.join(additional_info)})"

                        interfaces.append({
                            'device_name': hostname,
                            'interface_name': final_interface_name,
                            'ip_address': ip_with_cidr,
                            'vrf': vrf,
                            'zone': "N/A",
                            'description': description
                        })

                        found_ip = True

                # Search for secondary IP addresses
                secondary_matches = re.findall(secondary_pattern, interface_config, re.MULTILINE | re.IGNORECASE)
                for ip, mask in secondary_matches:
                    if ip == "0.0.0.0":
                        continue

                    cidr = self.netmask_to_cidr(mask)
                    interfaces.append({
                        'device_name': hostname,
                        'interface_name': interface_name,
                        'ip_address': f"{ip}/{cidr} (secondary)",
                        'vrf': vrf,
                        'zone': "N/A",
                        'description': description
                    })
                    found_ip = True

                # Special handling for NVE interfaces
                if interface_type == 'NVE' and not found_ip:
                    source_match = re.search(r'source-interface\s+([^\r\n]+)', interface_config, re.IGNORECASE)
                    if source_match:
                        interfaces.append({
                            'device_name': hostname,
                            'interface_name': interface_name,
                            'ip_address': f"Source: {source_match.group(1).strip()}",
                            'vrf': "Global",
                            'zone': "N/A",
                            'description': "N/A"
                        })
                        found_ip = True

        return interfaces

    def netmask_to_cidr(self, netmask: str) -> str:
        """Convert subnet mask to CIDR notation"""
        try:
            octets = netmask.split('.')
            binary = ''.join([bin(int(octet))[2:].zfill(8) for octet in octets])
            cidr = binary.count('1')
            return str(cidr)
        except:
            return "24"

    def detect_device_type(self, content: str, filepath: Optional[str] = None) -> str:
        """Detect device type based on configuration content and filename"""
        content_lower = content.lower()

        # Check file extension
        if filepath:
            ext = os.path.splitext(filepath)[1].lower()
            if ext == '.set':
                return 'fortigate'

        fortigate_indicators = [
            'fortigate',
            'fortios',
            'config system',
            'config vdom',
            'config firewall',
            'config router',
            'config switch-controller',
            'config wireless-controller',
            'config user',
            'config vpn',
            'config log',
            'config system zone',
            'config system interface'
        ]
        if any(ind in content_lower for ind in fortigate_indicators):
            return 'fortigate'
        elif any(keyword in content_lower for keyword in ['cisco', 'ios', 'nxos', 'interface', 'hostname']):
            return 'cisco'
        else:
            return 'cisco'

    def is_text_file(self, filepath: str) -> bool:
        """Check if a file is a text-based file"""
        try:
            with open(filepath, 'rb') as f:
                chunk = f.read(1024)
                if not chunk:
                    return True

                if b'\x00' in chunk:
                    return False

                try:
                    chunk.decode('utf-8')
                    return True
                except UnicodeDecodeError:
                    try:
                        chunk.decode('latin-1')
                        return True
                    except UnicodeDecodeError:
                        return False
        except Exception:
            return False

    def find_all_files(self, directory_path: str = ".") -> List[str]:
        """Find all files in directory and filter for text-based files"""
        all_files = []

        try:
            for item in os.listdir(directory_path):
                filepath = os.path.join(directory_path, item)
                if os.path.isfile(filepath):
                    all_files.append(filepath)
        except Exception as e:
            print(f"Error accessing directory {directory_path}: {e}")
            return []

        text_files = []
        print("Checking files for text content...")

        for filepath in all_files:
            if self.is_text_file(filepath):
                text_files.append(filepath)
                print(f"✓ {os.path.basename(filepath)} - Text file")
            else:
                print(f"✗ {os.path.basename(filepath)} - Binary file (skipped)")

        return text_files

    def parse_file(self, filepath: str) -> List[Dict]:
        """Parse a single configuration file"""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading file {filepath}: {e}")
            return []

        device_type = self.detect_device_type(content, filepath=filepath)
        interfaces = []
        parsed_device, parsed_vdom = self.parse_device_and_vdom_from_filename(filepath)
        default_vdom = parsed_vdom if parsed_vdom else "root"

        if device_type == 'fortigate':
            hostname = self.extract_hostname_fortigate(content, filepath=filepath)
            if hostname == "Unknown" and parsed_device:
                hostname = parsed_device
            interfaces.extend(self.parse_fortigate_interfaces(content, hostname, default_vdom=default_vdom, filepath=filepath))
        else:  # Cisco
            hostname = self.extract_hostname_cisco(content)
            if hostname == "Unknown" and parsed_device:
                hostname = parsed_device
            interfaces.extend(self.parse_cisco_interfaces(content, hostname))
            interfaces.extend(self.parse_cisco_evpn(content, hostname))

        # Add filename as fallback if hostname is unknown
        if hostname == "Unknown":
            hostname = parsed_device if parsed_device else os.path.splitext(os.path.basename(filepath))[0]
            for interface in interfaces:
                interface['device_name'] = hostname

        # Retroactively resolve any previously parsed interfaces that now have known zones
        if device_type == 'fortigate':
            self._retroactive_zone_resolution(hostname)

        if interfaces:
            print(f"    → Found {len(interfaces)} interfaces on {hostname}")
            for interface in interfaces[-3:]:
                zone_info = f" (Zone: {interface['zone']})" if interface['zone'] != "N/A" else ""
                print(f"      • {interface['interface_name']}: {interface['ip_address']}{zone_info}")
            if len(interfaces) > 3:
                print(f"      ... and {len(interfaces) - 3} more")
        else:
            print(f"    → No interfaces with IP addresses found")

        return interfaces

    def process_directory(self, directory_path: str = ".", auto_yes: bool = False) -> None:
        """Process all text-based files in the specified directory"""
        print(f"DEBUG: auto_yes={auto_yes}")
        print(f"Scanning directory: {os.path.abspath(directory_path)}")
        print("=" * 50)

        text_files = self.find_all_files(directory_path)

        if not text_files:
            print(f"No text-based files found in {directory_path}")
            return

        print(f"\nFound {len(text_files)} text-based files:")
        for i, filepath in enumerate(text_files, 1):
            file_size = os.path.getsize(filepath)
            size_str = f"{file_size:,} bytes"
            if file_size > 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"

            print(f"  {i:2d}. {os.path.basename(filepath)} ({size_str})")

        print("\n" + "=" * 50)

        # Ask user for confirmation
        while True:
            if auto_yes:
                print(f"Auto-confirming processing of {len(text_files)} files.")
                break

            response = input(f"Do you want to process these {len(text_files)} files? (y/n): ").lower().strip()
            if response in ['y', 'yes']:
                break
            elif response in ['n', 'no']:
                print("Operation cancelled by user.")
                return
            else:
                print("Please enter 'y' for yes or 'n' for no.")

        # Pass 1: Pre-scan FortiGate files to discover device zones across all files
        print("\nPre-scanning FortiGate files for cross-file zone mappings...")
        for filepath in text_files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                if self.detect_device_type(content, filepath=filepath) == 'fortigate':
                    p_dev, p_vdom = self.parse_device_and_vdom_from_filename(filepath)
                    hname = self.extract_hostname_fortigate(content, filepath=filepath)
                    if hname == "Unknown" and p_dev:
                        hname = p_dev
                    def_vdom = p_vdom if p_vdom else "root"
                    f_zones = self.extract_fortigate_zones(content, default_vdom=def_vdom)
                    if hname not in self.device_zones:
                        self.device_zones[hname] = {}
                    self.device_zones[hname].update(f_zones)
            except Exception:
                pass

        print("\nProcessing files...")
        print("=" * 30)

        for i, filepath in enumerate(text_files, 1):
            print(f"[{i}/{len(text_files)}] Processing: {os.path.basename(filepath)}")
            interfaces = self.parse_file(filepath)
            for iface in interfaces:
                # Deduplicate by interface_name, ip_address, and base device name
                dev_base = iface['device_name'].split()[0]
                existing = next(
                    (item for item in self.interface_data
                     if item['interface_name'] == iface['interface_name']
                     and item['ip_address'] == iface['ip_address']
                     and item['device_name'].split()[0] == dev_base),
                    None
                )
                if existing:
                    if (existing['zone'] in ("No Zone", "N/A") or not existing['zone']) and iface['zone'] not in ("No Zone", "N/A"):
                        existing['zone'] = iface['zone']
                        existing['device_name'] = iface['device_name']
                    if existing['description'] in ("N/A", "") and iface['description'] not in ("N/A", ""):
                        existing['description'] = iface['description']
                else:
                    self.interface_data.append(iface)

        print(f"\nCompleted processing {len(text_files)} files.")

    def export_to_csv(self, output_file: str = "network_interfaces.csv") -> None:
        """Export collected interface data to CSV file"""
        if not self.interface_data:
            print("No interface data to export")
            return

        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['device_name', 'interface_name', 'ip_address', 'vrf', 'zone', 'description']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for interface in self.interface_data:
                    writer.writerow(interface)

            print(f"Successfully exported {len(self.interface_data)} interface records to {output_file}")

        except Exception as e:
            print(f"Error writing CSV file: {e}")


def main():
    """Main function to run the interface extractor"""
    import argparse

    parser = argparse.ArgumentParser(description='Extract interface information from network device configurations')
    parser.add_argument('-d', '--directory', default='.',
                        help='Directory containing configuration files (default: current directory)')
    parser.add_argument('-o', '--output', default='network_interfaces.csv',
                        help='Output CSV file name (default: network_interfaces.csv)')
    parser.add_argument('-y', '--yes', action='store_true',
                        help='Automatically answer "yes" to all prompts')

    args = parser.parse_args()

    print("Network Device Interface Extractor")
    print("=" * 40)
    print(f"Processing directory: {args.directory}")
    print(f"Output file: {args.output}")
    print()

    config_parser = NetworkConfigParser()
    config_parser.process_directory(args.directory, auto_yes=args.yes)
    config_parser.export_to_csv(args.output)

    print("\nProcessing complete!")


if __name__ == "__main__":
    main()
