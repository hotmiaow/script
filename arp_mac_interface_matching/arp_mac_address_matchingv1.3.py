#!/usr/bin/env python3
"""
Cisco Network Analysis Script
Analyzes Cisco device output files to match ARP, MAC address, and interface information.
Supports IOS, NXOS, and IOS XE platforms.
Handles multiple MAC addresses per interface in additional columns.
Enhanced with comprehensive ARP parsing and guaranteed MAC entry inclusion.
"""


import os
import re
import csv
import socket
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ArpEntry:
    device_name: str
    ip: str
    mac: str
    interface: str
    age: str = ""
    protocol: str = ""


@dataclass
class MacEntry:
    device_name: str
    mac: str
    vlan: str
    port: str
    entry_type: str = ""


@dataclass
class InterfaceEntry:
    device_name: str
    port: str
    name: str = ""
    status: str = ""
    vlan: str = ""
    duplex: str = ""
    speed: str = ""
    interface_type: str = ""


@dataclass
class CdpNeighborEntry:
    device_name: str
    local_interface: str
    neighbor_device_id: str
    holdtime: str = ""
    capability: str = ""
    platform: str = ""
    neighbor_port_id: str = ""


class CiscoNetworkAnalyzer:
    def __init__(self):
        # Interface abbreviation mappings
        self.interface_mappings = {
            'Fa': 'FastEthernet',
            'Fe': 'FastEthernet',
            'Gi': 'GigabitEthernet',
            'Gig': 'GigabitEthernet',
            'Te': 'TenGigabitEthernet',
            'Eth': 'Ethernet',
            'Po': 'Port-channel',
            'Vl': 'Vlan',
            'Lo': 'Loopback',
            'Se': 'Serial',
            'Ser': 'Serial',
            'Tu': 'Tunnel',
            'Br': 'Bridge',
            'Nv': 'nve',
            'Mg': 'mgmt'
        }


    def get_device_name_from_filename(self, filename: str) -> str:
        """Extract device name from filename."""
        # Remove file extension
        name = os.path.splitext(filename)[0]
        # Clean up common suffixes/prefixes
        name = re.sub(r'[-_](config|cfg|show|output|log)$', '', name, flags=re.IGNORECASE)
        return name


    def normalize_interface_name(self, interface: str) -> str:
        """Normalize interface names to handle abbreviations."""
        # Handle special cases and clean up the interface name first
        interface = interface.strip()
        
        # Extract the abbreviation and number part
        match = re.match(r'([A-Za-z]+)(\d+(?:/\d+)*(?:\.\d+)?)', interface)
        if match:
            abbrev, number = match.groups()
            # Check if abbreviation exists in our mapping
            for short, full in self.interface_mappings.items():
                if abbrev.lower().startswith(short.lower()):
                    return f"{full}{number}"
        return interface


    def find_command_output(self, content: str, commands: List[str]) -> List[str]:
        """Find command output sections in the file content with improved detection."""
        lines = content.split('\n')
        output_lines = []
        
        # Try to find command output sections more comprehensively
        for command in commands:
            capturing = False
            command_lines = []
            
            for line in lines:
                line_stripped = line.strip()
                
                # Check if line contains the target command (more flexible matching)
                if command.lower() in line_stripped.lower():
                    capturing = True
                    print(f"DEBUG: Found command '{command}' in line: '{line_stripped}'")
                    continue
                
                # If we're capturing, collect lines until we hit a new command or prompt
                if capturing:
                    # Stop at command prompts or new commands
                    if re.match(r'^[A-Za-z0-9\-_]+[#>]', line_stripped):
                        if not any(cmd.lower() in line_stripped.lower() for cmd in commands):
                            print(f"DEBUG: Stopped capture at prompt: '{line_stripped}'")
                            break
                    
                    command_lines.append(line_stripped)
            
            if command_lines:
                print(f"DEBUG: Found {len(command_lines)} lines for command '{command}'")
                output_lines.extend(command_lines)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_lines = []
        for line in output_lines:
            if line not in seen:
                seen.add(line)
                unique_lines.append(line)
        
        print(f"DEBUG: Total unique output lines: {len(unique_lines)}")
        return unique_lines


    def parse_arp_entries(self, content: str, device_name: str) -> List[ArpEntry]:
        """Enhanced ARP parsing to catch all possible ARP entries."""
        # Expanded list of ARP commands and variations
        arp_commands = [
            'show ip arp', 'sh ip arp', 'show arp', 'sh arp',
            'show ip arp vrf', 'show arp detail', 'show ip arp brief',
            'show ip arp summary', 'show arp table', 'show ip arp interface'
        ]
        
        # Get all lines that might contain ARP information
        arp_lines = self.find_command_output(content, arp_commands)
        
        # Also search through the entire content for lines that look like ARP entries
        all_lines = content.split('\n')
        potential_arp_lines = []
        
        for line in all_lines:
            line = line.strip()
            # Look for lines that contain IP addresses and MAC addresses together
            if re.search(r'\d+\.\d+\.\d+\.\d+', line) and re.search(r'[a-fA-F0-9]{4}\.[a-fA-F0-9]{4}\.[a-fA-F0-9]{4}', line):
                potential_arp_lines.append(line)
        
        # Combine both sets of lines
        all_arp_lines = list(set(arp_lines + potential_arp_lines))
        
        arp_entries = []
        print(f"DEBUG: Processing {len(all_arp_lines)} potential ARP lines for {device_name}")
        
        for line in all_arp_lines:
            if not line.strip():
                continue
                
            # Skip header lines
            if any(header in line.lower() for header in ['protocol', 'address', 'hardware', 'interface', 'type', '----']):
                continue
            
            # Pattern 1: Standard IOS ARP format
            match = re.search(r'Internet\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+|\-)\s+([a-fA-F0-9]{4}\.[a-fA-F0-9]{4}\.[a-fA-F0-9]{4})\s+\w+\s+(\S+)', line)
            if match:
                ip = match.group(1)
                age = match.group(2)
                mac = match.group(3)
                interface = match.group(4)
                
                arp_entry = ArpEntry(
                    device_name=device_name,
                    ip=ip,
                    mac=mac.lower(),
                    interface=self.normalize_interface_name(interface),
                    age=age,
                    protocol="Internet"
                )
                arp_entries.append(arp_entry)
                print(f"DEBUG: ARP Entry (Internet) - Device: {device_name}, MAC: {mac.lower()}, IP: {ip}")
                continue
            
            # Pattern 2: NXOS/Alternative format
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+(\d+:\d+:\d+|\-)\s+([a-fA-F0-9]{4}\.[a-fA-F0-9]{4}\.[a-fA-F0-9]{4})\s+(\S+)', line)
            if match:
                ip = match.group(1)
                age = match.group(2)
                mac = match.group(3)
                interface = match.group(4)
                
                arp_entry = ArpEntry(
                    device_name=device_name,
                    ip=ip,
                    mac=mac.lower(),
                    interface=self.normalize_interface_name(interface),
                    age=age
                )
                arp_entries.append(arp_entry)
                print(f"DEBUG: ARP Entry (NXOS) - Device: {device_name}, MAC: {mac.lower()}, IP: {ip}")
                continue
            
            # Pattern 3: Simplified format (IP and MAC)
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+([a-fA-F0-9]{4}\.[a-fA-F0-9]{4}\.[a-fA-F0-9]{4})', line)
            if match:
                ip = match.group(1)
                mac = match.group(2)
                
                arp_entry = ArpEntry(
                    device_name=device_name,
                    ip=ip,
                    mac=mac.lower(),
                    interface="",  # No interface specified
                    age=""
                )
                arp_entries.append(arp_entry)
                print(f"DEBUG: ARP Entry (Simple) - Device: {device_name}, MAC: {mac.lower()}, IP: {ip}")
                continue
        
        print(f"DEBUG: Found {len(arp_entries)} total ARP entries for {device_name}")
        return arp_entries


    def parse_cdp_neighbors(self, content: str, device_name: str) -> List[CdpNeighborEntry]:
        """Parse CDP neighbor entries from command output with improved parsing."""
        cdp_commands = [
            'show cdp neighbors', 'show cdp neighbor', 'sh cdp neighbors', 'sh cdp neighbor'
        ]
        
        cdp_lines = self.find_command_output(content, cdp_commands)
        cdp_entries = []
        
        print(f"DEBUG: Starting CDP parsing for {device_name} with {len(cdp_lines)} lines")
        
        # Variables to handle multi-line entries
        pending_device_id = None
        
        for i, line in enumerate(cdp_lines):
            if not line.strip():
                continue
                
            # Skip header lines and separators
            if any(keyword in line.lower() for keyword in [
                'device id', 'local intrfce', 'local interface', 'holdtme', 'holdtime', 
                'capability', 'platform', 'port id', '----', 'capability codes'
            ]):
                continue
            
            print(f"DEBUG: Processing CDP line {i}: '{line}'")
            
            # Method 1: Try to parse a complete single-line entry
            parts = line.split()
            if len(parts) >= 6:
                # Try to identify where the interface starts (contains numbers and slashes)
                interface_idx = -1
                for j, part in enumerate(parts[1:], 1):  # Skip first part (device ID)
                    if re.match(r'[A-Za-z]+\s*\d+(?:/\d+)*', part):
                        interface_idx = j
                        break
                
                if interface_idx > 0 and interface_idx < len(parts) - 3:  # Need at least 4 more fields after interface
                    device_id = ' '.join(parts[:interface_idx])
                    local_interface = parts[interface_idx]
                    
                    # Rest of the fields
                    remaining = parts[interface_idx + 1:]
                    if len(remaining) >= 4:
                        holdtime = remaining[0]
                        
                        # Find platform (usually a number or model)
                        platform_idx = -1
                        for k, part in enumerate(remaining[1:], 1):
                            if re.match(r'\d+|[A-Z]+-\w+|WS-\w+', part):
                                platform_idx = k
                                break
                        
                        if platform_idx > 0:
                            capability = ' '.join(remaining[1:platform_idx])
                            platform = remaining[platform_idx]
                            port_id = ' '.join(remaining[platform_idx + 1:]) if len(remaining) > platform_idx + 1 else ""
                            
                            cdp_entry = CdpNeighborEntry(
                                device_name=device_name,
                                local_interface=self.normalize_interface_name(local_interface),
                                neighbor_device_id=device_id.strip(),
                                holdtime=holdtime,
                                capability=capability.strip(),
                                platform=platform,
                                neighbor_port_id=port_id.strip()
                            )
                            cdp_entries.append(cdp_entry)
                            print(f"DEBUG: Single-line CDP parsed - {local_interface} -> {device_id}")
                            continue
            
            # Method 2: Check if this is a standalone device ID (long hostname)
            if len(parts) == 1 and (
                '.' in line or len(line) > 15 or 
                line.lower().endswith('.com') or line.lower().endswith('.local')
            ):
                pending_device_id = line.strip()
                print(f"DEBUG: Found potential device ID: '{pending_device_id}'")
                continue
            
            # Method 3: If we have a pending device ID, try to parse the continuation
            if pending_device_id and len(parts) >= 5:
                local_interface = parts[0]
                holdtime = parts[1] if parts[1].isdigit() else parts[2]
                
                # Find holdtime position
                holdtime_idx = -1
                for j, part in enumerate(parts):
                    if part.isdigit() and int(part) > 0 and int(part) < 1000:  # Reasonable holdtime range
                        holdtime_idx = j
                        holdtime = part
                        break
                
                if holdtime_idx >= 1:
                    local_interface = ' '.join(parts[:holdtime_idx])
                    remaining = parts[holdtime_idx + 1:]
                    
                    if len(remaining) >= 2:
                        # Find platform in remaining parts
                        platform_idx = -1
                        for k, part in enumerate(remaining):
                            if re.match(r'\d+|[A-Z]+-\w+|WS-\w+', part):
                                platform_idx = k
                                break
                        
                        if platform_idx >= 0:
                            capability = ' '.join(remaining[:platform_idx]) if platform_idx > 0 else ""
                            platform = remaining[platform_idx]
                            port_id = ' '.join(remaining[platform_idx + 1:]) if len(remaining) > platform_idx + 1 else ""
                            
                            cdp_entry = CdpNeighborEntry(
                                device_name=device_name,
                                local_interface=self.normalize_interface_name(local_interface.split()[0]),
                                neighbor_device_id=pending_device_id,
                                holdtime=holdtime,
                                capability=capability.strip(),
                                platform=platform,
                                neighbor_port_id=port_id.strip()
                            )
                            cdp_entries.append(cdp_entry)
                            print(f"DEBUG: Multi-line CDP parsed - {local_interface} -> {pending_device_id}")
                            pending_device_id = None
                            continue
        
        print(f"DEBUG: Found {len(cdp_entries)} CDP neighbor entries for {device_name}")
        return cdp_entries


    def parse_interface_descriptions_from_running_config(self, content: str, device_name: str) -> Dict[str, str]:
        """Parse interface descriptions from show running-config."""
        run_commands = ['show running-config', 'show run', 'sh run', 'show startup-config']
        
        run_lines = self.find_command_output(content, run_commands)
        interface_descriptions = {}
        
        current_interface = None
        current_description = None
        
        for line in run_lines:
            line = line.strip()
            
            # Check for interface line
            interface_match = re.match(r'^interface\s+([A-Za-z]+[\d/\.]+)', line, re.IGNORECASE)
            if interface_match:
                # Save previous interface description if we have one
                if current_interface and current_description:
                    normalized_int = self.normalize_interface_name(current_interface)
                    interface_descriptions[f"{device_name}_{normalized_int}"] = current_description
                    print(f"DEBUG: Found interface config - {device_name} {normalized_int}: {current_description}")
                
                # Start new interface
                current_interface = interface_match.group(1)
                current_description = None
                continue
            
            # Check for description line within interface config
            if current_interface:
                desc_match = re.match(r'^\s*description\s+(.+)', line, re.IGNORECASE)
                if desc_match:
                    current_description = desc_match.group(1).strip()
                    continue
                
                # If we hit another top-level command or interface, we're done with current interface
                if line and not line.startswith(' ') and not line.startswith('!'):
                    if current_interface and current_description:
                        normalized_int = self.normalize_interface_name(current_interface)
                        interface_descriptions[f"{device_name}_{normalized_int}"] = current_description
                        print(f"DEBUG: Found interface config - {device_name} {normalized_int}: {current_description}")
                    current_interface = None
                    current_description = None
        
        # Don't forget the last interface if file ends
        if current_interface and current_description:
            normalized_int = self.normalize_interface_name(current_interface)
            interface_descriptions[f"{device_name}_{normalized_int}"] = current_description
            print(f"DEBUG: Found interface config - {device_name} {normalized_int}: {current_description}")
        
        return interface_descriptions


    def parse_mac_entries(self, content: str, device_name: str) -> List[MacEntry]:
        """Parse MAC address table entries."""
        mac_commands = [
            'show mac address-table', 'show mac-address-table', 'sh mac address-table',
            'show mac address', 'sh mac address', 'show mac-address',
            'sh mac address-table dynamic', 'show mac address-table dynamic'
        ]
       
        mac_lines = self.find_command_output(content, mac_commands)
        mac_entries = []
       
        for line in mac_lines:
            # Skip header lines and separators
            if ('vlan' in line.lower() and 'mac address' in line.lower()) or \
               ('----' in line) or \
               ('total mac address' in line.lower()) or \
               ('mac address table' in line.lower()):
                continue
            
            # Try pattern 1: Standard MAC address table format
            # Format: VLAN    MAC_ADDRESS    TYPE    PORT
            match = re.search(r'^\s*(\d+)\s+([a-fA-F0-9]{4}\.[a-fA-F0-9]{4}\.[a-fA-F0-9]{4})\s+(\w+)\s+(\S+)', line)
            if match:
                vlan = match.group(1)
                mac = match.group(2)
                entry_type = match.group(3)
                port = match.group(4)
                
                mac_entry = MacEntry(
                    device_name=device_name,
                    mac=mac.lower(),
                    vlan=vlan,
                    port=self.normalize_interface_name(port),
                    entry_type=entry_type
                )
                mac_entries.append(mac_entry)
                print(f"DEBUG: MAC Entry - Device: {device_name}, MAC: {mac.lower()}, Port: {self.normalize_interface_name(port)}")
                continue
            
            # Try pattern 2: Alternative format with different spacing
            match = re.search(r'^\s*(\d+)\s+([a-fA-F0-9]{4}\.[a-fA-F0-9]{4}\.[a-fA-F0-9]{4})\s+(\w+)\s+\d+\s+[FM]\s+[FM]\s+(\S+)', line)
            if match:
                vlan = match.group(1)
                mac = match.group(2)
                entry_type = match.group(3)
                port = match.group(4)
                
                mac_entry = MacEntry(
                    device_name=device_name,
                    mac=mac.lower(),
                    vlan=vlan,
                    port=self.normalize_interface_name(port),
                    entry_type=entry_type
                )
                mac_entries.append(mac_entry)
                print(f"DEBUG: MAC Entry - Device: {device_name}, MAC: {mac.lower()}, Port: {self.normalize_interface_name(port)}")
                continue
                   
        return mac_entries


    def parse_interface_entries(self, content: str, device_name: str) -> List[InterfaceEntry]:
        """Parse interface status entries with fixed field structure."""
        int_commands = [
            'show interface status', 'show int status', 'sh int status',
            'show interfaces status', 'show interface brief',
            'show ip interface brief'
        ]
       
        int_lines = self.find_command_output(content, int_commands)
        interface_entries = []

        # First, get interface descriptions from running config
        interface_descriptions = self.parse_interface_descriptions_from_running_config(content, device_name)

        for line in int_lines:
            # Skip header lines and separators
            if ('port' in line.lower() and 'name' in line.lower() and 'status' in line.lower()) or \
               ('----' in line) or \
               ('interface' in line.lower() and 'status' in line.lower() and 'protocol' in line.lower()):
                continue
            
            # Skip empty lines and comments
            if not line.strip() or line.strip().startswith('#'):
                continue

            print(f"DEBUG: Processing interface line: '{line}'")
            
            # Define all possible status values
            status_values = ['connected', 'notconnect', 'disabled', 'err-disabled', 'down', 'up', 'monitor', 'xcvrAbsent']
            
            # Use a more precise regex pattern that handles the exact format
            # Pattern matches: Interface [Description] Status VLAN Duplex Speed [Type]
            # The key insight is that Status is always one of our known keywords
            
            # Create a regex pattern that captures the structure properly
            status_pattern = '(' + '|'.join(status_values) + ')'
            
            # This pattern captures:
            # Group 1: Interface name
            # Group 2: Everything before status (description, could be empty/whitespace)
            # Group 3: Status
            # Group 4: Everything after status
            pattern = r'^(\S+)\s+(.*?)\s+' + status_pattern + r'\s+(.+)$'
            
            match = re.match(pattern, line)
            if match:
                interface_name = match.group(1)
                description_raw = match.group(2)
                status = match.group(3)
                after_status = match.group(4)
                
                # Clean up description (remove extra whitespace)
                description = ' '.join(description_raw.split()) if description_raw and description_raw.strip() else ""
                
                # Parse the fields after status: VLAN Duplex Speed [Type]
                after_status_parts = after_status.split()
                
                if len(after_status_parts) < 3:
                    print(f"DEBUG: Insufficient fields after status. Expected at least VLAN, Duplex, Speed. Got: {after_status_parts}")
                    continue
                
                vlan = after_status_parts[0]
                duplex = after_status_parts[1]
                speed = after_status_parts[2]
                interface_type = ' '.join(after_status_parts[3:]) if len(after_status_parts) > 3 else ""
                
                print(f"DEBUG: Parsed - Interface: '{interface_name}', Desc: '{description}', Status: '{status}', VLAN: '{vlan}', Duplex: '{duplex}', Speed: '{speed}', Type: '{interface_type}'")
                
                # Normalize interface name
                port = self.normalize_interface_name(interface_name)
                
                # Check for running config description (takes priority)
                config_key = f"{device_name}_{port}"
                if config_key in interface_descriptions:
                    final_name = interface_descriptions[config_key]
                    print(f"DEBUG: Using config description for {port}: '{final_name}'")
                elif description:
                    final_name = description
                    print(f"DEBUG: Using inline description for {port}: '{final_name}'")
                else:
                    final_name = ""
                    print(f"DEBUG: No description found for {port}")
                
                # Create interface entry
                interface_entry = InterfaceEntry(
                    device_name=device_name,
                    port=port,
                    name=final_name,
                    status=status,
                    vlan=vlan,
                    duplex=duplex,
                    speed=speed,
                    interface_type=interface_type
                )
                interface_entries.append(interface_entry)
                print(f"DEBUG: Successfully parsed - {port}: '{final_name}' | Status: {status} | VLAN: {vlan} | Duplex: {duplex} | Speed: {speed} | Type: '{interface_type}'")
                
            else:
                print(f"DEBUG: Failed to match line: '{line}'")
                   
        return interface_entries


    def resolve_hostname(self, ip: str) -> str:
        """Attempt to resolve IP address to hostname."""
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            return hostname
        except (socket.herror, socket.gaierror, OSError):
            return ip


    def analyze_files(self) -> Tuple[Dict[str, List], Dict[str, List], Dict[str, List], Dict[str, List]]:
        """Analyze all text files in Layer2 and Layer3 directories."""
        arp_files = {}
        mac_files = {}
        interface_files = {}
        cdp_files = {}
        
        # Check Layer3 directory for ARP files ONLY
        layer3_dir = 'Layer3'
        if os.path.exists(layer3_dir) and os.path.isdir(layer3_dir):
            layer3_files = [f for f in os.listdir(layer3_dir) if f.endswith(('.txt', '.log', '.cfg', '.conf'))]
            print(f"Found {len(layer3_files)} files in Layer3 directory...")
            
            for filename in layer3_files:
                filepath = os.path.join(layer3_dir, filename)
                device_name = self.get_device_name_from_filename(filename)
                
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    print(f"DEBUG: Processing Layer3 file {filename} (size: {len(content)} chars)")
                    
                    # Parse ONLY ARP information from Layer3 files
                    arp_entries = self.parse_arp_entries(content, device_name)
                    
                    if arp_entries:
                        arp_files[filename] = arp_entries
                        print(f"  Layer3/{filename}: Found {len(arp_entries)} ARP entries")
                    else:
                        print(f"  Layer3/{filename}: No ARP entries found")
                        
                except Exception as e:
                    print(f"Error reading Layer3/{filename}: {e}")
        else:
            print("Layer3 directory not found or not accessible")
        
        # Check Layer2 directory for MAC, Interface, and CDP files
        layer2_dir = 'Layer2'
        if os.path.exists(layer2_dir) and os.path.isdir(layer2_dir):
            layer2_files = [f for f in os.listdir(layer2_dir) if f.endswith(('.txt', '.log', '.cfg', '.conf'))]
            print(f"Found {len(layer2_files)} files in Layer2 directory...")
            
            for filename in layer2_files:
                filepath = os.path.join(layer2_dir, filename)
                device_name = self.get_device_name_from_filename(filename)
                
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    # Parse MAC, interface, and CDP information from Layer2 files
                    mac_entries = self.parse_mac_entries(content, device_name)
                    interface_entries = self.parse_interface_entries(content, device_name)
                    cdp_entries = self.parse_cdp_neighbors(content, device_name)
                    
                    if mac_entries:
                        mac_files[filename] = mac_entries
                        print(f"  Layer2/{filename}: Found {len(mac_entries)} MAC entries")
                    
                    if interface_entries:
                        interface_files[filename] = interface_entries
                        print(f"  Layer2/{filename}: Found {len(interface_entries)} interface entries")
                    
                    if cdp_entries:
                        cdp_files[filename] = cdp_entries
                        print(f"  Layer2/{filename}: Found {len(cdp_entries)} CDP neighbor entries")
                        
                except Exception as e:
                    print(f"Error reading Layer2/{filename}: {e}")
        else:
            print("Layer2 directory not found or not accessible")
               
        return arp_files, mac_files, interface_files, cdp_files


    def create_combined_report(self, arp_files: Dict, mac_files: Dict, interface_files: Dict, cdp_files: Dict) -> None:
        """Create a combined CSV report with multiple MAC addresses in additional columns per interface."""
       
        # Combine all entries from different files
        all_arp = []
        all_mac = []
        all_interfaces = []
        all_cdp = []
       
        for entries in arp_files.values():
            all_arp.extend(entries)
        for entries in mac_files.values():
            all_mac.extend(entries)
        for entries in interface_files.values():
            all_interfaces.extend(entries)
        for entries in cdp_files.values():
            all_cdp.extend(entries)
       
        print(f"Total ARP entries: {len(all_arp)}")
        print(f"Total MAC entries: {len(all_mac)}")
        print(f"Total Interface entries: {len(all_interfaces)}")
        print(f"Total CDP entries: {len(all_cdp)}")
       
        # Group MAC entries by device and port for multiple MAC handling
        mac_by_device_port = {}
        for mac_entry in all_mac:
            key = f"{mac_entry.device_name}_{mac_entry.port}"
            if key not in mac_by_device_port:
                mac_by_device_port[key] = []
            mac_by_device_port[key].append(mac_entry)
        
        # Create CDP lookup by device and local interface
        cdp_by_device_port = {}
        for cdp_entry in all_cdp:
            key = f"{cdp_entry.device_name}_{cdp_entry.local_interface}"
            cdp_by_device_port[key] = cdp_entry
       
        # Create lookup dictionaries - both device-specific and global MAC lookups
        mac_to_arp_device_specific = {}  # Device-specific matching
        mac_to_arp_global = {}          # Global MAC matching across devices
        port_to_interface = {}
        
        # Build ARP lookups
        for entry in all_arp:
            device_key = f"{entry.device_name}_{entry.mac}"
            mac_to_arp_device_specific[device_key] = entry
            mac_to_arp_global[entry.mac] = entry  # Global lookup by MAC only
            
        for entry in all_interfaces:
            key = f"{entry.device_name}_{entry.port}"
            port_to_interface[key] = entry
       
        print(f"Device-specific ARP lookups: {len(mac_to_arp_device_specific)}")
        print(f"Global ARP lookups: {len(mac_to_arp_global)}")
        print(f"CDP neighbor lookups: {len(cdp_by_device_port)}")
        
        # Determine the maximum number of MAC addresses per interface
        max_macs_per_interface = max([len(macs) for macs in mac_by_device_port.values()]) if mac_by_device_port else 1
        print(f"DEBUG: Maximum MAC addresses per interface: {max_macs_per_interface}")
        
        # Create combined report with dynamic columns for multiple MACs
        report_data = []
        processed_mac_entries = set()  # Track which MAC entries we've processed
       
        # Process each interface and all its associated MAC addresses in one row
        for interface in all_interfaces:
            interface_key = f"{interface.device_name}_{interface.port}"
            
            # Get CDP neighbor info for this interface
            cdp_entry = cdp_by_device_port.get(interface_key)
            
            # Get all MAC addresses for this interface
            port_mac_entries = mac_by_device_port.get(interface_key, [])
            
            # Create single row for this interface
            row = {
                'Device_Name': interface.device_name,
                'Port': interface.port,
                'Port_Name': interface.name,
                'Status': interface.status,
                'VLAN': interface.vlan,
                'Duplex': interface.duplex,
                'Speed': interface.speed,
                'Type': interface.interface_type,
                'CDP_Neighbor_Device': cdp_entry.neighbor_device_id if cdp_entry else '',
                'CDP_Neighbor_Port': cdp_entry.neighbor_port_id if cdp_entry else '',
                'CDP_Platform': cdp_entry.platform if cdp_entry else '',
                'CDP_Capability': cdp_entry.capability if cdp_entry else ''
            }
            
            # Add MAC addresses as additional columns
            for i, mac_entry in enumerate(port_mac_entries, 1):
                # Mark this MAC entry as processed
                mac_key = f"{mac_entry.device_name}_{mac_entry.port}_{mac_entry.mac}"
                processed_mac_entries.add(mac_key)
                
                # Add MAC-specific columns
                row[f'MAC_Address_{i}'] = mac_entry.mac
                row[f'MAC_Type_{i}'] = mac_entry.entry_type
                row[f'MAC_VLAN_{i}'] = mac_entry.vlan
                
                # Try to find ARP entry for this MAC
                arp_key = f"{interface.device_name}_{mac_entry.mac}"
                arp_entry = None
                
                if arp_key in mac_to_arp_device_specific:
                    arp_entry = mac_to_arp_device_specific[arp_key]
                    print(f"DEBUG: Device-specific ARP match found for {arp_key}")
                elif mac_entry.mac in mac_to_arp_global:
                    arp_entry = mac_to_arp_global[mac_entry.mac]
                    print(f"DEBUG: Global ARP match found for MAC {mac_entry.mac}")
                else:
                    print(f"DEBUG: No ARP match found for MAC {mac_entry.mac}")
                
                if arp_entry:
                    row[f'IP_Address_{i}'] = arp_entry.ip
                    row[f'Hostname_{i}'] = self.resolve_hostname(arp_entry.ip)
                    row[f'ARP_Age_{i}'] = arp_entry.age
                else:
                    row[f'IP_Address_{i}'] = ''
                    row[f'Hostname_{i}'] = ''
                    row[f'ARP_Age_{i}'] = ''
            
            # Fill empty columns for interfaces with fewer MACs
            for i in range(len(port_mac_entries) + 1, max_macs_per_interface + 1):
                row[f'MAC_Address_{i}'] = ''
                row[f'MAC_Type_{i}'] = ''
                row[f'MAC_VLAN_{i}'] = ''
                row[f'IP_Address_{i}'] = ''
                row[f'Hostname_{i}'] = ''
                row[f'ARP_Age_{i}'] = ''
            
            report_data.append(row)
       
        # Add any MAC entries that don't have corresponding interface entries
        orphan_macs_by_port = {}
        for mac_entry in all_mac:
            mac_key = f"{mac_entry.device_name}_{mac_entry.port}_{mac_entry.mac}"
            if mac_key not in processed_mac_entries:
                port_key = f"{mac_entry.device_name}_{mac_entry.port}"
                if port_key not in orphan_macs_by_port:
                    orphan_macs_by_port[port_key] = []
                orphan_macs_by_port[port_key].append(mac_entry)
        
        # Process orphan MAC entries (those without interface entries)
        for port_key, mac_entries in orphan_macs_by_port.items():
            print(f"DEBUG: Processing orphan MACs for port: {port_key}")
            
            # Extract device name and port from key
            device_name, port = port_key.split('_', 1)
            cdp_entry = cdp_by_device_port.get(port_key)
            
            row = {
                'Device_Name': device_name,
                'Port': port,
                'Port_Name': '',
                'Status': '',
                'VLAN': '',
                'Duplex': '',
                'Speed': '',
                'Type': '',
                'CDP_Neighbor_Device': cdp_entry.neighbor_device_id if cdp_entry else '',
                'CDP_Neighbor_Port': cdp_entry.neighbor_port_id if cdp_entry else '',
                'CDP_Platform': cdp_entry.platform if cdp_entry else '',
                'CDP_Capability': cdp_entry.capability if cdp_entry else ''
            }
            
            # Add MAC addresses as additional columns
            for i, mac_entry in enumerate(mac_entries, 1):
                row[f'MAC_Address_{i}'] = mac_entry.mac
                row[f'MAC_Type_{i}'] = mac_entry.entry_type
                row[f'MAC_VLAN_{i}'] = mac_entry.vlan
                
                # Try to find ARP entry for this MAC
                arp_key = f"{device_name}_{mac_entry.mac}"
                arp_entry = None
                
                if arp_key in mac_to_arp_device_specific:
                    arp_entry = mac_to_arp_device_specific[arp_key]
                elif mac_entry.mac in mac_to_arp_global:
                    arp_entry = mac_to_arp_global[mac_entry.mac]
                
                if arp_entry:
                    row[f'IP_Address_{i}'] = arp_entry.ip
                    row[f'Hostname_{i}'] = self.resolve_hostname(arp_entry.ip)
                    row[f'ARP_Age_{i}'] = arp_entry.age
                else:
                    row[f'IP_Address_{i}'] = ''
                    row[f'Hostname_{i}'] = ''
                    row[f'ARP_Age_{i}'] = ''
            
            # Fill empty columns for orphan ports with fewer MACs
            for i in range(len(mac_entries) + 1, max_macs_per_interface + 1):
                row[f'MAC_Address_{i}'] = ''
                row[f'MAC_Type_{i}'] = ''
                row[f'MAC_VLAN_{i}'] = ''
                row[f'IP_Address_{i}'] = ''
                row[f'Hostname_{i}'] = ''
                row[f'ARP_Age_{i}'] = ''
            
            report_data.append(row)
       
        # Create dynamic fieldnames based on maximum MAC addresses found
        fieldnames = [
            'Device_Name', 'Port', 'Port_Name', 'Status', 'VLAN', 'Duplex', 'Speed', 'Type',
            'CDP_Neighbor_Device', 'CDP_Neighbor_Port', 'CDP_Platform', 'CDP_Capability'
        ]
        
        # Add MAC-related columns for each possible MAC address
        for i in range(1, max_macs_per_interface + 1):
            fieldnames.extend([
                f'MAC_Address_{i}', f'MAC_Type_{i}', f'MAC_VLAN_{i}',
                f'IP_Address_{i}', f'Hostname_{i}', f'ARP_Age_{i}'
            ])
        
        # Write to CSV
        output_file = 'cisco_network_analysis.csv'
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(report_data)
       
        print(f"\nReport saved to: {output_file}")
        print(f"Total interface entries in report: {len(report_data)}")
        print(f"Maximum MAC addresses per interface: {max_macs_per_interface}")
        
        # Verification: Check that all MAC entries are included
        total_mac_fields_in_report = sum([
            len([val for key, val in row.items() if key.startswith('MAC_Address_') and val])
            for row in report_data
        ])
        print(f"Total MAC entries in report: {total_mac_fields_in_report}")
        print(f"Total MAC entries found: {len(all_mac)}")
        
        if total_mac_fields_in_report != len(all_mac):
            print(f"WARNING: Some MAC entries may be missing! Expected {len(all_mac)}, got {total_mac_fields_in_report}")
        else:
            print("✓ All MAC entries successfully included in report")
        
        # Summary statistics
        total_interfaces = len(all_interfaces)
        interfaces_with_macs = len([row for row in report_data if any(row.get(f'MAC_Address_{i}', '') for i in range(1, max_macs_per_interface + 1))])
        interfaces_with_multiple_macs = len([row for row in report_data if sum(1 for i in range(1, max_macs_per_interface + 1) if row.get(f'MAC_Address_{i}', '')) > 1])
        interfaces_with_cdp = len([row for row in report_data if row.get('CDP_Neighbor_Device', '')])
        mac_entries_without_arp = sum([
            len([i for i in range(1, max_macs_per_interface + 1) 
                 if row.get(f'MAC_Address_{i}', '') and not row.get(f'IP_Address_{i}', '')])
            for row in report_data
        ])
        
        print(f"\nSummary Statistics:")
        print(f"Total interfaces/ports: {len(report_data)}")
        print(f"Interfaces with MAC addresses: {interfaces_with_macs}")
        print(f"Interfaces with multiple MAC addresses: {interfaces_with_multiple_macs}")
        print(f"Interfaces with CDP neighbors: {interfaces_with_cdp}")
        print(f"MAC entries without corresponding ARP: {mac_entries_without_arp}")


    def run(self):
        """Main execution function."""
        print("Cisco Network Analysis Script")
        print("=" * 40)
       
        # Analyze files
        arp_files, mac_files, interface_files, cdp_files = self.analyze_files()
       
        # Display summary
        print("\nSummary:")
        print(f"Files with ARP information: {len(arp_files)}")
        for filename in arp_files:
            print(f"  - {filename}")
       
        print(f"Files with MAC address information: {len(mac_files)}")
        for filename in mac_files:
            print(f"  - {filename}")
       
        print(f"Files with interface information: {len(interface_files)}")
        for filename in interface_files:
            print(f"  - {filename}")
            
        print(f"Files with CDP neighbor information: {len(cdp_files)}")
        for filename in cdp_files:
            print(f"  - {filename}")
       
        if not any([arp_files, mac_files, interface_files, cdp_files]):
            print("\nNo relevant information found in any files.")
            return
       
        # Ask user confirmation
        response = input("\nProceed with creating the combined analysis report? (y/n): ")
        if response.lower().startswith('y'):
            self.create_combined_report(arp_files, mac_files, interface_files, cdp_files)
            print("\nAnalysis complete!")
        else:
            print("Analysis cancelled.")


if __name__ == "__main__":
    analyzer = CiscoNetworkAnalyzer()
    analyzer.run()
