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

    def extract_hostname_fortigate(self, content: str) -> str:
        """Extract hostname from Fortigate configuration"""
        # Look for set hostname command
        hostname_match = re.search(r'set hostname\s+"?([^"\n]+)"?', content, re.IGNORECASE)
        if hostname_match:
            return hostname_match.group(1).strip('"')

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

    def extract_fortigate_zones(self, content: str) -> Dict[str, str]:
        """
        Extract interface-to-zone mappings from FortiGate config,
        including zones defined inside each VDOM.
        Returns a dictionary mapping 'vdom::interface' -> zone name.
        """
        zones = {}

        # Step 1: Extract all VDOM definitions using config vdom / edit / next structure
        vdom_pattern = r'config\s+vdom\s*\n(.*?)(?=^config\s+(?!system)|^\s*end\s*$|\Z)'
        vdom_section_match = re.search(vdom_pattern, content, flags=re.DOTALL | re.IGNORECASE | re.MULTILINE)

        if not vdom_section_match:
            print("    Debug: No VDOM section found, checking for global zones")
            # If no VDOM section, check for global zone configuration
            return self.extract_global_zones(content)

        vdom_section = vdom_section_match.group(1)

        # Extract individual VDOM blocks
        vdom_blocks = re.findall(
            r'edit\s+"?([^\s"\n]+)"?\s*\n(.*?)\n\s*next',
            vdom_section,
            flags=re.DOTALL | re.IGNORECASE
        )

        for vdom_name, vdom_content in vdom_blocks:
            print(f"    Debug: Parsing VDOM '{vdom_name}'")

            # Step 2: Look for config system zone in the current VDOM block
            zone_section_match = re.search(
                r'config\s+system\s+zone\s*\n(.*?)\n\s*end',
                vdom_content,
                flags=re.DOTALL | re.IGNORECASE
            )
            if not zone_section_match:
                print(f"      Debug: No zones found in VDOM '{vdom_name}'")
                continue

            zone_section = zone_section_match.group(1)

            # Step 3: Extract individual zone entries
            zone_blocks = re.findall(
                r'edit\s+"?([^\s"\n]+)"?\s*\n(.*?)\n\s*next',
                zone_section,
                flags=re.DOTALL | re.IGNORECASE
            )

            for zone_name, zone_body in zone_blocks:
                print(f"      Debug: Processing zone '{zone_name}' in VDOM '{vdom_name}'")

                # Step 4: Find set interface lines and parse interfaces
                interface_lines = re.findall(
                    r'set\s+interface\s+(.+)',
                    zone_body,
                    flags=re.IGNORECASE
                )

                for line in interface_lines:
                    interfaces = self.parse_interface_list(line)
                    for iface in interfaces:
                        iface_clean = iface.strip('"')
                        zone_key = f"{vdom_name}::{iface_clean}"
                        zones[zone_key] = zone_name
                        print(f"        Debug: {zone_key} -> {zone_name}")

        print(f"    Debug: Total interface-to-zone mappings: {len(zones)}")
        return zones


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
                interfaces.append(interface_name)

        return interfaces

    def parse_fortigate_interfaces(self, content: str, hostname: str) -> List[Dict]:
        """Parse Fortigate interface configurations with VDOM and zone support"""
        interfaces = []

        # Extract zones from the entire config
        zones = self.extract_fortigate_zones(content)

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

            # Extract VDOM from interface config
            vdom_match = re.search(r'^\s*set\s+vdom\s+"?([^"\n\s]+)"?', interface_config, re.MULTILINE | re.IGNORECASE)
            vdom_name = vdom_match.group(1).strip('"') if vdom_match else "root"

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

                    # Get zone for this interface
                    zone_key = f"{vdom_name}::{interface_name}"
                    zone_name = zones.get(zone_key, "No Zone")

                    # Create device name with VDOM
                    if vdom_name != "root":
                        device_name = f"{hostname} (VDOM: {vdom_name})"
                    else:
                        device_name = hostname

                    interfaces.append({
                        'device_name': device_name,
                        'interface_name': interface_name,
                        'ip_address': ip_with_cidr,
                        'zone': zone_name
                    })

                    print(
                        f"        Found IP: {ip_with_cidr} on {interface_name} (Zone: {zone_name}, VDOM: {vdom_name})")
                    ip_found = True

            if not ip_found:
                # Check for DHCP configuration
                dhcp_match = re.search(r'^\s*set\s+mode\s+dhcp', interface_config, re.MULTILINE | re.IGNORECASE)
                if dhcp_match:
                    zone_name = zones.get(interface_name, "No Zone")
                    device_name = f"{hostname} (VDOM: {vdom_name})" if vdom_name != "root" else hostname

                    interfaces.append({
                        'device_name': device_name,
                        'interface_name': interface_name,
                        'ip_address': "DHCP",
                        'zone': zone_name
                    })

                    print(f"        Found DHCP mode on {interface_name} (Zone: {zone_name}, VDOM: {vdom_name})")
                    ip_found = True

                # Check for PPPoE configuration
                if not ip_found:
                    pppoe_match = re.search(r'^\s*set\s+mode\s+pppoe', interface_config, re.MULTILINE | re.IGNORECASE)
                    if pppoe_match:
                        zone_name = zones.get(interface_name, "No Zone")
                        device_name = f"{hostname} (VDOM: {vdom_name})" if vdom_name != "root" else hostname

                        interfaces.append({
                            'device_name': device_name,
                            'interface_name': interface_name,
                            'ip_address': "PPPoE",
                            'zone': zone_name
                        })

                        print(f"        Found PPPoE mode on {interface_name} (Zone: {zone_name}, VDOM: {vdom_name})")
                        ip_found = True

                if not ip_found:
                    print(f"        No IP configuration found for {interface_name}")

        return interfaces

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
                        'zone': "N/A"  # Cisco doesn't use zones like FortiGate
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
                    'zone': "N/A"
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

                        # Extract additional info
                        additional_info = []

                        # Look for VRF membership
                        vrf_match = re.search(r'vrf\s+member\s+(\S+)', vlan_config, re.IGNORECASE)
                        if vrf_match:
                            additional_info.append(f"VRF:{vrf_match.group(1)}")

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
                            'zone': "N/A"
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

                        # Extract additional information
                        additional_info = []

                        vrf_match = re.search(r'vrf\s+member\s+(\S+)', interface_config, re.IGNORECASE)
                        if vrf_match:
                            additional_info.append(f"VRF:{vrf_match.group(1)}")

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
                            'zone': "N/A"
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
                        'zone': "N/A"
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
                            'zone': "N/A"
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

    def detect_device_type(self, content: str) -> str:
        """Detect device type based on configuration content"""
        content_lower = content.lower()

        if 'fortigate' in content_lower or 'config system interface' in content_lower or 'config vdom' in content_lower:
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

        device_type = self.detect_device_type(content)
        interfaces = []

        if device_type == 'fortigate':
            hostname = self.extract_hostname_fortigate(content)
            interfaces.extend(self.parse_fortigate_interfaces(content, hostname))
        else:  # Cisco
            hostname = self.extract_hostname_cisco(content)
            interfaces.extend(self.parse_cisco_interfaces(content, hostname))
            interfaces.extend(self.parse_cisco_evpn(content, hostname))

        # Add filename as fallback if hostname is unknown
        if hostname == "Unknown":
            hostname = os.path.splitext(os.path.basename(filepath))[0]
            for interface in interfaces:
                interface['device_name'] = hostname

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

    def process_directory(self, directory_path: str = ".") -> None:
        """Process all text-based files in the specified directory"""
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
            response = input(f"Do you want to process these {len(text_files)} files? (y/n): ").lower().strip()
            if response in ['y', 'yes']:
                break
            elif response in ['n', 'no']:
                print("Operation cancelled by user.")
                return
            else:
                print("Please enter 'y' for yes or 'n' for no.")

        print("\nProcessing files...")
        print("=" * 30)

        for i, filepath in enumerate(text_files, 1):
            print(f"[{i}/{len(text_files)}] Processing: {os.path.basename(filepath)}")
            interfaces = self.parse_file(filepath)
            self.interface_data.extend(interfaces)

        print(f"\nCompleted processing {len(text_files)} files.")

    def export_to_csv(self, output_file: str = "network_interfaces.csv") -> None:
        """Export collected interface data to CSV file"""
        if not self.interface_data:
            print("No interface data to export")
            return

        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['device_name', 'interface_name', 'ip_address','zone']
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

    args = parser.parse_args()

    print("Network Device Interface Extractor")
    print("=" * 40)
    print(f"Processing directory: {args.directory}")
    print(f"Output file: {args.output}")
    print()

    config_parser = NetworkConfigParser()
    config_parser.process_directory(args.directory)
    config_parser.export_to_csv(args.output)

    print("\nProcessing complete!")


if __name__ == "__main__":
    main()