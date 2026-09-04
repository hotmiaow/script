#!/usr/bin/env python3
"""
Cisco Network Traceroute Mapper - Enhanced Hop-by-Hop Display with Zone Information

This script reads the CSV file with device interface information,
performs traceroute between devices, and displays the network path
hop-by-hop with real-time device names, interface names, IP addresses, and zones.
"""

import csv
import subprocess
import platform
import re
import ipaddress
import sys
import json
import time
from datetime import datetime


class CiscoTracerouteMapper:
    def __init__(self, csv_file='cisco_interfaces.csv'):
        self.csv_file = csv_file
        self.device_inventory = {}  # {device_name: [(interface, ip, zone), ...]}
        self.ip_to_device_map = {}  # {ip: (device_name, interface, zone)}
        self.device_ips = {}  # {device_name: [ip1, ip2, ...]}
        self.device_zones = {}  # {device_name: zone}

    def load_csv_data(self):
        """Load device and interface data from CSV file"""
        print(f"Loading network inventory from {self.csv_file}...")

        try:
            with open(self.csv_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)

                for row in reader:
                    device_name = row['Device Name'].strip()
                    interface_name = row['Interface Name'].strip()
                    ip_subnet = row['IP Address/Subnet'].strip()
                    zone = row.get('Zone', 'Unknown').strip()  # Get zone, default to 'Unknown'

                    # Skip DHCP and invalid entries
                    if ip_subnet.upper() == 'DHCP' or not ip_subnet:
                        continue

                    # Extract IP address (remove CIDR notation)
                    ip_address = ip_subnet.split('/')[0] if '/' in ip_subnet else ip_subnet

                    # Validate IP address
                    try:
                        ipaddress.ip_address(ip_address)
                    except ValueError:
                        print(f"Warning: Invalid IP address '{ip_address}' for {device_name}")
                        continue

                    # Build inventory
                    if device_name not in self.device_inventory:
                        self.device_inventory[device_name] = []
                        self.device_ips[device_name] = []
                        self.device_zones[device_name] = zone

                    self.device_inventory[device_name].append((interface_name, ip_address, zone))
                    self.device_ips[device_name].append(ip_address)
                    self.ip_to_device_map[ip_address] = (device_name, interface_name, zone)

                print(f"✓ Loaded {len(self.device_inventory)} devices")
                print(f"✓ Total interfaces: {len(self.ip_to_device_map)}")

                # Display zone summary
                zones = set(self.device_zones.values())
                print(f"✓ Network zones found: {', '.join(sorted(zones))}")
                return True

        except FileNotFoundError:
            print(f"Error: CSV file '{self.csv_file}' not found")
            return False
        except Exception as e:
            print(f"Error loading CSV: {e}")
            return False

    def execute_traceroute_streaming(self, target_ip, source_ip=None):
        """Execute traceroute command and yield hop results as they arrive"""
        try:
            # Build traceroute command based on OS
            system = platform.system().lower()

            if system == 'windows':
                cmd = ['tracert', '-h', '20', '-w', '3000', target_ip]
            else:
                cmd = ['traceroute', '-m', '20', '-w', '3', target_ip]
                if source_ip:
                    cmd.extend(['-s', source_ip])

            # Execute traceroute with streaming output
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore',
                bufsize=1,
                universal_newlines=True
            )

            hop_number = 0
            while True:
                line = process.stdout.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                # Parse hop information from the line
                hop_info = self.parse_traceroute_line(line, system)
                if hop_info:
                    hop_number, ip_address = hop_info
                    yield hop_number, ip_address

            process.wait()

        except FileNotFoundError:
            print(f"    Traceroute command not available on this system")
            return
        except Exception as e:
            print(f"    Traceroute error: {e}")
            return

    def parse_traceroute_line(self, line, system):
        """Parse a single line of traceroute output"""
        if system == 'windows':
            # Windows tracert: "  1    <1 ms    <1 ms    <1 ms  192.168.1.1"
            match = re.search(r'^\s*(\d+)\s+.*?(\d+\.\d+\.\d+\.\d+)', line)
        else:
            # Linux/Unix traceroute: " 1  192.168.1.1 (192.168.1.1)  0.123 ms"
            match = re.search(r'^\s*(\d+)\s+.*?(\d+\.\d+\.\d+\.\d+)', line)

        if match:
            hop_number = int(match.group(1))
            ip_address = match.group(2)

            # Validate IP
            try:
                ipaddress.ip_address(ip_address)
                return hop_number, ip_address
            except ValueError:
                pass

        return None

    def get_device_interface_info(self, ip_address):
        """Get device, interface, and zone information for an IP address"""
        return self.ip_to_device_map.get(ip_address, (None, None, None))

    def display_hop_details(self, hop_number, ip_address, show_extra_info=True):
        """Display detailed information for a single hop"""
        device_name, interface_name, zone = self.get_device_interface_info(ip_address)

        print(f"\n┌─ HOP {hop_number}")
        print(f"├─ IP Address: {ip_address}")

        if device_name and interface_name:
            print(f"├─ Device: {device_name}")
            print(f"├─ Interface: {interface_name}")
            print(f"├─ Zone: {zone}")
            print(f"├─ Status: ✓ KNOWN CISCO DEVICE")

            if show_extra_info and device_name in self.device_inventory:
                # Show additional interfaces on this device
                other_interfaces = [(intf, ip, z) for intf, ip, z in self.device_inventory[device_name]
                                    if ip != ip_address]
                if other_interfaces:
                    print(f"├─ Other interfaces on this device:")
                    for i, (intf, ip, z) in enumerate(other_interfaces[:3]):
                        prefix = "├─   " if i < len(other_interfaces[:3]) - 1 else "└─   "
                        print(f"{prefix}├─ {intf}: {ip} (Zone: {z})")
                    if len(other_interfaces) > 3:
                        print(f"└─   └─ ... and {len(other_interfaces) - 3} more interfaces")
                else:
                    print(f"└─ (This is the only known interface)")
            else:
                print(f"└─")
        else:
            print(f"├─ Device: Unknown/External")
            print(f"├─ Interface: Unknown")
            print(f"├─ Zone: Unknown")
            print(f"├─ Status: ? EXTERNAL/UNKNOWN HOP")
            print(f"└─ (Not in Cisco device inventory)")

    def display_device_inventory(self):
        """Display all devices and their interfaces with zones"""
        print(f"\n{'=' * 100}")
        print("NETWORK DEVICE INVENTORY")
        print(f"{'=' * 100}")

        # Group by zone for better organization
        zones = {}
        for device_name, interfaces in self.device_inventory.items():
            zone = self.device_zones.get(device_name, 'Unknown')
            if zone not in zones:
                zones[zone] = []
            zones[zone].append((device_name, interfaces))

        for zone in sorted(zones.keys()):
            print(f"\n🌐 ZONE: {zone}")
            print("=" * 60)

            for device_name, interfaces in zones[zone]:
                print(f"\n📍 {device_name}")
                print("-" * 50)
                print(f"{'Interface':<25} {'IP Address':<16} {'Zone'}")
                print("-" * 50)
                for interface, ip, zone_info in interfaces:
                    print(f"{interface:<25} {ip:<16} {zone_info}")

    def trace_to_destination_streaming(self, target_ip, description=""):
        """Trace path with real-time hop-by-hop display"""
        try:
            ipaddress.ip_address(target_ip)
        except ValueError:
            print(f"Error: Invalid IP address '{target_ip}'")
            return

        print(f"\n{'=' * 80}")
        if description:
            print(f"TRACING PATH FROM LOCAL PC TO {target_ip} ({description})")
        else:
            print(f"TRACING PATH FROM LOCAL PC TO {target_ip}")
        print(f"{'=' * 80}")

        # Check if target is in our database
        target_device, target_interface, target_zone = self.get_device_interface_info(target_ip)
        if target_device:
            print(f"🎯 TARGET: {target_device} ({target_interface}) - Zone: {target_zone}")
            print(f"   Destination is a known Cisco device from inventory")
        else:
            print(f"🎯 TARGET: {target_ip}")
            print(f"   Destination not found in device inventory")

        # Get local PC information
        try:
            import socket
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            print(f"\n💻 SOURCE: {hostname} ({local_ip})")
        except:
            print(f"\n💻 SOURCE: Local PC")

        print(f"\n🔍 Starting traceroute... (Press Ctrl+C to stop)")
        print(f"{'=' * 60}")

        # Perform streaming traceroute
        hops_data = []
        known_devices_count = 0
        unknown_hops_count = 0
        zones_traversed = set()

        try:
            for hop_number, ip_address in self.execute_traceroute_streaming(target_ip):
                # Store hop data
                hops_data.append((hop_number, ip_address))

                # Display hop details immediately
                device_name, interface_name, zone = self.get_device_interface_info(ip_address)

                if device_name:
                    known_devices_count += 1
                    zones_traversed.add(zone)
                else:
                    unknown_hops_count += 1

                self.display_hop_details(hop_number, ip_address)

                # Small delay for readability (optional)
                time.sleep(0.5)

                # Check if we've reached the destination
                if ip_address == target_ip:
                    print(f"\n🎯 DESTINATION REACHED!")
                    break

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Traceroute interrupted by user")

        # Final summary
        total_hops = len(hops_data)
        if total_hops > 0:
            print(f"\n{'=' * 80}")
            print(f"📊 TRACEROUTE SUMMARY")
            print(f"{'=' * 80}")
            print(f"Total hops: {total_hops}")
            print(f"Known Cisco devices: {known_devices_count}")
            print(f"Unknown/External hops: {unknown_hops_count}")
            print(f"Zones traversed: {', '.join(sorted(zones_traversed)) if zones_traversed else 'None'}")

            if known_devices_count > 0:
                success_rate = (known_devices_count / total_hops) * 100
                print(f"Known device ratio: {success_rate:.1f}%")
                print(f"Status: ✓ Path includes Cisco infrastructure")
            else:
                print(f"Status: ⚠️ No known Cisco devices in path")

            # Display complete path in table format
            print(f"\n📋 COMPLETE NETWORK PATH TABLE")
            print("-" * 110)
            print(f"{'Hop':<4} {'IP Address':<16} {'Device Name':<20} {'Interface Name':<25} {'Zone':<15} {'Status'}")
            print("-" * 110)

            discovered_devices = []
            for hop_num, ip_addr in hops_data:
                device_name, interface_name, zone = self.get_device_interface_info(ip_addr)

                if device_name and interface_name:
                    status = "✓ Known Device"
                    device_display = device_name
                    interface_display = interface_name
                    zone_display = zone
                    discovered_devices.append((hop_num, device_name, interface_name, ip_addr, zone))
                else:
                    status = "? External/Unknown"
                    device_display = "Unknown Device"
                    interface_display = "Unknown Interface"
                    zone_display = "Unknown"

                print(
                    f"{hop_num:<4} {ip_addr:<16} {device_display:<20} {interface_display:<25} {zone_display:<15} {status}")

            if discovered_devices:
                print(f"\n🔍 CISCO DEVICES IN PATH (detailed):")
                for hop_num, device_name, interface_name, ip_addr, zone in discovered_devices:
                    print(f"   Hop {hop_num}: {device_name} (Zone: {zone})")
                    print(f"            Interface: {interface_name} ({ip_addr})")
        else:
            print(f"\n❌ No traceroute data available")
            print(f"This could be due to:")
            print(f"   - Firewall blocking traceroute")
            print(f"   - Network connectivity issues")
            print(f"   - Target host not responding")

        return hops_data

    def trace_to_destination(self, target_ip, description=""):
        """Wrapper for backward compatibility"""
        return self.trace_to_destination_streaming(target_ip, description)

    def trace_to_ip(self, target_ip):
        """Legacy method - now calls trace_to_destination_streaming"""
        self.trace_to_destination_streaming(target_ip)

    def bulk_trace_to_multiple_destinations(self):
        """Trace to multiple destinations with hop-by-hop display"""
        print(f"\n{'=' * 60}")
        print("🎯 BULK TRACEROUTE TO MULTIPLE DESTINATIONS")
        print(f"{'=' * 60}")

        destinations = []

        print("Enter destination IP addresses (press Enter with empty line to finish):")
        while True:
            ip_input = input("IP Address: ").strip()
            if not ip_input:
                break

            try:
                ipaddress.ip_address(ip_input)
                description = input(f"Description for {ip_input} (optional): ").strip()
                destinations.append((ip_input, description))
            except ValueError:
                print(f"Invalid IP address: {ip_input}")

        if not destinations:
            print("No valid destinations entered")
            return

        print(f"\n🔄 Will trace to {len(destinations)} destinations...")
        input("Press Enter to start or Ctrl+C to cancel...")

        all_results = {}
        for i, (target_ip, description) in enumerate(destinations, 1):
            print(f"\n{'=' * 20} TRACE {i}/{len(destinations)} {'=' * 20}")
            hops = self.trace_to_destination_streaming(target_ip, description)
            all_results[target_ip] = hops

            if i < len(destinations):
                print(f"\n⏱️  Waiting 3 seconds before next trace...")
                time.sleep(3)

        # Final summary of all traces
        print(f"\n{'=' * 100}")
        print("📋 BULK TRACEROUTE FINAL SUMMARY")
        print(f"{'=' * 100}")

        print(f"{'Destination':<16} {'Hops':<6} {'Known':<6} {'Zones':<20} {'Status'}")
        print("-" * 70)

        for target_ip, hops in all_results.items():
            known_count = sum(1 for _, ip in (hops or []) if ip in self.ip_to_device_map)
            total_hops = len(hops) if hops else 0

            # Get zones for this trace
            zones_in_trace = set()
            for _, ip in (hops or []):
                _, _, zone = self.get_device_interface_info(ip)
                if zone:
                    zones_in_trace.add(zone)

            zones_str = ', '.join(sorted(zones_in_trace)) if zones_in_trace else 'None'
            if len(zones_str) > 18:
                zones_str = zones_str[:15] + "..."

            if total_hops > 0:
                status = "✓ Reachable"
            else:
                status = "✗ Unreachable"

            print(f"{target_ip:<16} {total_hops:<6} {known_count:<6} {zones_str:<20} {status}")

    def trace_to_known_devices(self):
        """Trace from local PC to all known devices with hop-by-hop display"""
        print(f"\n{'=' * 80}")
        print("🌐 TRACING FROM LOCAL PC TO ALL KNOWN DEVICES")
        print(f"{'=' * 80}")

        device_count = len(self.device_inventory)
        print(f"Will trace to {device_count} devices from inventory...")

        confirm = input(f"This will perform {device_count} traceroute operations. Continue? (y/N): ").strip().lower()
        if confirm != 'y':
            print("Operation cancelled")
            return

        results_summary = []

        for i, (device_name, interfaces) in enumerate(self.device_inventory.items(), 1):
            # Use first IP of device as target
            target_ip = interfaces[0][1]  # (interface, ip, zone) tuple
            target_zone = interfaces[0][2]

            print(f"\n{'=' * 20} DEVICE {i}/{device_count} {'=' * 20}")
            hops = self.trace_to_destination_streaming(target_ip, f"Device: {device_name} (Zone: {target_zone})")

            # Collect summary data
            if hops:
                known_count = sum(1 for _, ip in hops if ip in self.ip_to_device_map)
                results_summary.append((device_name, target_ip, len(hops), known_count, target_zone))
            else:
                results_summary.append((device_name, target_ip, 0, 0, target_zone))

            # Small delay between traces
            if i < device_count:
                print(f"\n⏱️  Waiting 3 seconds before next trace...")
                time.sleep(3)

        # Final summary of all device traces
        print(f"\n{'=' * 120}")
        print("📋 TRACE TO ALL DEVICES - FINAL SUMMARY")
        print(f"{'=' * 120}")

        print(f"{'Device Name':<25} {'Target IP':<16} {'Zone':<15} {'Hops':<6} {'Known':<6} {'Status'}")
        print("-" * 85)

        for device_name, target_ip, total_hops, known_count, zone in results_summary:
            if total_hops > 0:
                status = "✓ Reachable"
            else:
                status = "✗ Unreachable"

            print(f"{device_name:<25} {target_ip:<16} {zone:<15} {total_hops:<6} {known_count:<6} {status}")

    def interactive_menu(self):
        """Interactive menu for the traceroute mapper"""
        while True:
            print(f"\n{'=' * 80}")
            print("🌐 CISCO NETWORK TRACEROUTE MAPPER WITH ZONE INFORMATION")
            print(f"{'=' * 80}")
            print("1. Display Device Inventory (by Zone)")
            print("2. Trace to Single Destination")
            print("3. Trace to Multiple Destinations (Bulk)")
            print("4. Trace to All Known Devices")
            print("5. Exit")
            print("-" * 80)

            choice = input("Select option (1-5): ").strip()

            if choice == '1':
                self.display_device_inventory()

            elif choice == '2':
                target_ip = input("\nEnter target IP address: ").strip()
                if target_ip:
                    description = input("Enter description (optional): ").strip()
                    self.trace_to_destination_streaming(target_ip, description)

            elif choice == '3':
                self.bulk_trace_to_multiple_destinations()

            elif choice == '4':
                self.trace_to_known_devices()

            elif choice == '5':
                print("Goodbye!")
                break

            else:
                print("Invalid choice. Please select 1-5.")

            input("\nPress Enter to continue...")


def main():
    """Main function to run the traceroute mapper"""
    print("🌐 Cisco Network Traceroute Mapper with Zone Information")
    print("=" * 60)

    # Initialize the mapper
    mapper = CiscoTracerouteMapper()

    # Load CSV data
    if not mapper.load_csv_data():
        print("Failed to load CSV data. Exiting.")
        sys.exit(1)

    # Start interactive menu
    mapper.interactive_menu()


if __name__ == "__main__":
    main()