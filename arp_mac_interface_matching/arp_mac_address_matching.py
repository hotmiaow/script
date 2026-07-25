#!/usr/bin/env python3
"""
Cisco Network Analysis Script
Analyzes Cisco device output files to match ARP, MAC address, and interface information.
Supports IOS, NXOS, and IOS XE platforms.
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
        """Find command output sections in the file content."""
        lines = content.split('\n')
        output_lines = []
        capturing = False
       
        for line in lines:
            line = line.strip()
            if not line:
                continue
               
            # Check if line contains any of the target commands
            line_lower = line.lower()
            if any(cmd.lower() in line_lower for cmd in commands):
                capturing = True
                continue
               
            # Stop capturing at next command prompt or empty section
            if capturing:
                if re.match(r'^[A-Za-z0-9\-_]+[#>]', line):
                    if not any(cmd.lower() in line.lower() for cmd in commands):
                        break
                output_lines.append(line)
               
        return output_lines

    def parse_arp_entries(self, content: str, device_name: str) -> List[ArpEntry]:
        """Parse ARP entries from command output."""
        arp_commands = [
            'show ip arp', 'sh ip arp', 'show arp', 'sh arp',
            'show ip arp vrf', 'show arp detail'
        ]
       
        arp_lines = self.find_command_output(content, arp_commands)
        arp_entries = []
       
        for line in arp_lines:
            # Try pattern 1: Standard IOS ARP pattern
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
                    age=age
                )
                arp_entries.append(arp_entry)
                print(f"DEBUG: ARP Entry - Device: {device_name}, MAC: {mac.lower()}, IP: {ip}")
                continue
            
            # Try pattern 2: NXOS ARP pattern
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
                print(f"DEBUG: ARP Entry - Device: {device_name}, MAC: {mac.lower()}, IP: {ip}")
                continue
                   
        return arp_entries

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
        """Parse interface status entries."""
        int_commands = [
            'show interface status', 'show int status', 'sh int status',
            'show interfaces status', 'show interface brief',
            'show ip interface brief'
        ]
       
        int_lines = self.find_command_output(content, int_commands)
        interface_entries = []

        for line in int_lines:
            # Try pattern 1: Standard interface status pattern (7 groups)
            match = re.search(r'(\S+)\s+(\S*)\s+(connected|notconnect|disabled|err-disabled|down|up)\s+(\d+|trunk|\S+)\s+(\S+)\s+(\S+)\s+(\S+)', line)
            if match:
                port = self.normalize_interface_name(match.group(1))
                name = match.group(2) if match.group(2) else ""
                status = match.group(3)
                vlan = match.group(4)
                duplex = match.group(5)
                speed = match.group(6)
                interface_type = match.group(7)

                interface_entry = InterfaceEntry(
                    device_name=device_name,
                    port=port, 
                    name=name, 
                    status=status, 
                    vlan=vlan,
                    duplex=duplex, 
                    speed=speed, 
                    interface_type=interface_type
                )
                interface_entries.append(interface_entry)
                continue
            
            # Try pattern 2: NXOS format (7 groups)
            match = re.search(r'(\S+)\s+(\S*)\s+(connected|notconnect|disabled|xcvrAbsent|down|up)\s+(\d+|trunk|\S+)\s+(\S+)\s+(\S+)\s+(\S+)', line)
            if match:
                port = self.normalize_interface_name(match.group(1))
                name = match.group(2) if match.group(2) else ""
                status = match.group(3)
                vlan = match.group(4)
                duplex = match.group(5)
                speed = match.group(6)
                interface_type = match.group(7)

                interface_entry = InterfaceEntry(
                    device_name=device_name,
                    port=port, 
                    name=name, 
                    status=status, 
                    vlan=vlan,
                    duplex=duplex, 
                    speed=speed, 
                    interface_type=interface_type
                )
                interface_entries.append(interface_entry)
                continue
            
            # Try pattern 3: Simplified format (4 groups)
            match = re.search(r'(\S+)\s+(\S*)\s+(connected|notconnect|disabled|down|up)\s+(\S+)', line)
            if match:
                port = self.normalize_interface_name(match.group(1))
                name = match.group(2) if match.group(2) else ""
                status = match.group(3)
                vlan = match.group(4)

                interface_entry = InterfaceEntry(
                    device_name=device_name,
                    port=port, 
                    name=name, 
                    status=status, 
                    vlan=vlan,
                    duplex="", 
                    speed="", 
                    interface_type=""
                )
                interface_entries.append(interface_entry)
                continue
                   
        return interface_entries

    def resolve_hostname(self, ip: str) -> str:
        """Attempt to resolve IP address to hostname."""
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            return hostname
        except (socket.herror, socket.gaierror, OSError):
            return ip

    def analyze_files(self) -> Tuple[Dict[str, List], Dict[str, List], Dict[str, List]]:
        """Analyze all text files in Layer2 and Layer3 directories."""
        arp_files = {}
        mac_files = {}
        interface_files = {}
        
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
                    
                    # Parse ONLY ARP information from Layer3 files
                    arp_entries = self.parse_arp_entries(content, device_name)
                    
                    if arp_entries:
                        arp_files[filename] = arp_entries
                        print(f"  Layer3/{filename}: Found {len(arp_entries)} ARP entries")
                        
                except Exception as e:
                    print(f"Error reading Layer3/{filename}: {e}")
        else:
            print("Layer3 directory not found or not accessible")
        
        # Check Layer2 directory for MAC and Interface files ONLY
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
                    
                    # Parse ONLY MAC and interface information from Layer2 files
                    mac_entries = self.parse_mac_entries(content, device_name)
                    interface_entries = self.parse_interface_entries(content, device_name)
                    
                    if mac_entries:
                        mac_files[filename] = mac_entries
                        print(f"  Layer2/{filename}: Found {len(mac_entries)} MAC entries")
                    
                    if interface_entries:
                        interface_files[filename] = interface_entries
                        print(f"  Layer2/{filename}: Found {len(interface_entries)} interface entries")
                        
                except Exception as e:
                    print(f"Error reading Layer2/{filename}: {e}")
        else:
            print("Layer2 directory not found or not accessible")
               
        return arp_files, mac_files, interface_files

    def create_combined_report(self, arp_files: Dict, mac_files: Dict, interface_files: Dict) -> None:
        """Create a combined CSV report with matched information."""
       
        # Combine all entries from different files
        all_arp = []
        all_mac = []
        all_interfaces = []
       
        for entries in arp_files.values():
            all_arp.extend(entries)
        for entries in mac_files.values():
            all_mac.extend(entries)
        for entries in interface_files.values():
            all_interfaces.extend(entries)
       
        print(f"Total ARP entries: {len(all_arp)}")
        print(f"Total MAC entries: {len(all_mac)}")
        print(f"Total Interface entries: {len(all_interfaces)}")
       
        # Create lookup dictionaries - both device-specific and global MAC lookups
        mac_to_arp_device_specific = {}  # Device-specific matching
        mac_to_arp_global = {}          # Global MAC matching across devices
        mac_to_port = {}
        port_to_interface = {}
        
        # Build ARP lookups
        for entry in all_arp:
            device_key = f"{entry.device_name}_{entry.mac}"
            mac_to_arp_device_specific[device_key] = entry
            mac_to_arp_global[entry.mac] = entry  # Global lookup by MAC only
            
        for entry in all_mac:
            key = f"{entry.device_name}_{entry.mac}"
            mac_to_port[key] = entry
            
        for entry in all_interfaces:
            key = f"{entry.device_name}_{entry.port}"
            port_to_interface[key] = entry
       
        print("\nDEBUG: Matching Analysis")
        print(f"Device-specific ARP lookups: {len(mac_to_arp_device_specific)}")
        print(f"Global ARP lookups: {len(mac_to_arp_global)}")
        
        # Create combined report
        report_data = []
       
        # Start with interface information as base
        for interface in all_interfaces:
            row = {
                'Device_Name': interface.device_name,
                'Port': interface.port,
                'Port_Name': interface.name,
                'Status': interface.status,
                'VLAN': interface.vlan,
                'Duplex': interface.duplex,
                'Speed': interface.speed,
                'Type': interface.interface_type,
                'MAC_Address': '',
                'MAC_Type': '',
                'IP_Address': '',
                'Hostname': '',
                'ARP_Age': ''
            }
           
            # Find MAC address for this port on the same device
            port_mac_entries = [mac for mac in all_mac if mac.device_name == interface.device_name and mac.port == interface.port]
           
            for mac_entry in port_mac_entries:
                row_copy = row.copy()
                row_copy['MAC_Address'] = mac_entry.mac
                row_copy['MAC_Type'] = mac_entry.entry_type
               
                # Try device-specific ARP match first
                arp_key = f"{interface.device_name}_{mac_entry.mac}"
                arp_entry = None
                
                if arp_key in mac_to_arp_device_specific:
                    arp_entry = mac_to_arp_device_specific[arp_key]
                    print(f"DEBUG: Device-specific match found for {arp_key}")
                elif mac_entry.mac in mac_to_arp_global:
                    arp_entry = mac_to_arp_global[mac_entry.mac]
                    print(f"DEBUG: Global match found for MAC {mac_entry.mac}")
                
                if arp_entry:
                    row_copy['IP_Address'] = arp_entry.ip
                    row_copy['Hostname'] = self.resolve_hostname(arp_entry.ip)
                    row_copy['ARP_Age'] = arp_entry.age
               
                report_data.append(row_copy)
           
            # If no MAC entries found for this port, still include the port info
            if not port_mac_entries:
                report_data.append(row)
       
        # Add any MAC entries that don't have corresponding interface entries
        for mac_entry in all_mac:
            interface_key = f"{mac_entry.device_name}_{mac_entry.port}"
            if interface_key not in port_to_interface:
                row = {
                    'Device_Name': mac_entry.device_name,
                    'Port': mac_entry.port,
                    'Port_Name': '',
                    'Status': '',
                    'VLAN': mac_entry.vlan,
                    'Duplex': '',
                    'Speed': '',
                    'Type': '',
                    'MAC_Address': mac_entry.mac,
                    'MAC_Type': mac_entry.entry_type,
                    'IP_Address': '',
                    'Hostname': '',
                    'ARP_Age': ''
                }
               
                # Try device-specific ARP match first, then global
                arp_key = f"{mac_entry.device_name}_{mac_entry.mac}"
                arp_entry = None
                
                if arp_key in mac_to_arp_device_specific:
                    arp_entry = mac_to_arp_device_specific[arp_key]
                elif mac_entry.mac in mac_to_arp_global:
                    arp_entry = mac_to_arp_global[mac_entry.mac]
                
                if arp_entry:
                    row['IP_Address'] = arp_entry.ip
                    row['Hostname'] = self.resolve_hostname(arp_entry.ip)
                    row['ARP_Age'] = arp_entry.age
               
                report_data.append(row)
       
        # Write to CSV
        output_file = 'cisco_network_analysis.csv'
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'Device_Name', 'Port', 'Port_Name', 'Status', 'VLAN', 'Duplex', 'Speed', 'Type',
                'MAC_Address', 'MAC_Type', 'IP_Address', 'Hostname', 'ARP_Age'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(report_data)
       
        print(f"\nReport saved to: {output_file}")
        print(f"Total entries: {len(report_data)}")

    def run(self):
        """Main execution function."""
        print("Cisco Network Analysis Script")
        print("=" * 40)
       
        # Analyze files
        arp_files, mac_files, interface_files = self.analyze_files()
       
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
       
        if not any([arp_files, mac_files, interface_files]):
            print("\nNo relevant information found in any files.")
            return
       
        # Ask user confirmation
        response = input("\nProceed with creating the combined analysis report? (y/n): ")
        if response.lower().startswith('y'):
            self.create_combined_report(arp_files, mac_files, interface_files)
            print("\nAnalysis complete!")
        else:
            print("Analysis cancelled.")

if __name__ == "__main__":
    analyzer = CiscoNetworkAnalyzer()
    analyzer.run()
