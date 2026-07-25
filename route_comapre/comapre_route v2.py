#!/usr/bin/env python3
"""
Cisco Route Comparison Script (Enhanced with Device Connection and Automation)

This script provides three operational modes:
1. Create "before" folder and capture device outputs
2. Create "after" folder and capture device outputs  
3. Compare before/after outputs and generate reports

Usage:
    python3 cisco_route_compare.py --mode <1|2|3> [options]

Modes:
    1: Capture "before" state from devices listed in input.csv
    2: Capture "after" state from devices listed in input.csv
    3: Compare before/after states and generate comparison reports

Examples:
    python3 cisco_route_compare.py --mode 1 --input devices.csv
    python3 cisco_route_compare.py --mode 2 --input devices.csv
    python3 cisco_route_compare.py --mode 3
"""

import re
import csv
import sys
import os
import argparse
import ipaddress
import datetime
import shutil
import glob
from collections import defaultdict
from pathlib import Path

# Try to import netmiko for device connections
try:
    from netmiko import ConnectHandler
    NETMIKO_AVAILABLE = True
except ImportError:
    print("Warning: netmiko not available. Install with: pip install netmiko")
    NETMIKO_AVAILABLE = False

# Enhanced Administrative Distances to Protocol Mapping
ADMINISTRATIVE_DISTANCES = {
    0: "Connected",
    1: "Static",
    2: "EIGRP Summary",
    5: "BGP Summary/Aggregate",
    10: "EIGRP Internal",
    20: "eBGP",
    70: "EIGRP (IGRP)",
    90: "EIGRP Internal",
    100: "IGRP",
    105: "EIGRP (XOS)",
    110: "OSPF",
    115: "IS-IS",
    120: "RIP",
    130: "PIM",
    140: "ODR",
    150: "EIGRP External (XOS)",
    160: "BGP Local (XOS)",
    170: "EIGRP External",
    180: "mVPN",
    190: "OSPFV3",
    200: "iBGP",
    220: "IS-IS L2",
    254: "DHCP",
    255: "Unreachable"
}

# Protocol Codes to Normalized Names Mapping
PROTOCOL_CODE_MAP = {
    "B": "BGP", "B*": "BGP",
    "O": "OSPF", "O*": "OSPF",
    "O IA": "OSPF Inter-area", "O*IA": "OSPF Inter-area",
    "O E1": "OSPF External Type 1", "O*E1": "OSPF External Type 1",
    "O E2": "OSPF External Type 2", "O*E2": "OSPF External Type 2",
    "O N1": "OSPF NSSA Type 1", "O*N1": "OSPF NSSA Type 1",
    "O N2": "OSPF NSSA Type 2", "O*N2": "OSPF NSSA Type 2",
    "D": "EIGRP", "D*": "EIGRP",
    "D EX": "EIGRP External", "D*EX": "EIGRP External",
    "S": "Static", "S*": "Static",
    "C": "Connected", "C*": "Connected",
    "L": "Local", "L*": "Local",
    "R": "RIP", "R*": "RIP",
    "EX": "EIGRP External",
    "IA": "OSPF Inter-area",
    "i": "IS-IS", "i*": "IS-IS",
    "i SU": "IS-IS Summary", "i*SU": "IS-IS Summary",
    "i L1": "IS-IS Level 1", "i*L1": "IS-IS Level 1",
    "i L2": "IS-IS Level 2", "i*L2": "IS-IS Level 2",
    "E": "EGP",
    "U": "Unknown/Per-user Static",
    "H": "NHRP",
    "ND": "ND",
    "NDp": "ND Prefix",
    "ND D": "ND Default",
    "m": "Mobile",
    "P": "PIM",
    "M": "mVPN",
    "V": "VPN",
    "bgp": "BGP", "eigrp": "EIGRP", "ospf": "OSPF", "static": "Static", "connected": "Connected",
    "isis": "IS-IS", "rip": "RIP", "local": "Local", "direct": "Connected",
}

# Add these functions after the device connection functions and before main():

def extract_path_attributes(line):
    """
    Extracts the next hop IP (or status like "Connected") and uptime from a route line.
    """
    original_line = line
    next_hop_ip_val = "N/A"
    uptime_val = "N/A"

    # Enhanced uptime pattern to match various formats
    uptime_pattern_regex = r'\b(\d{1,2}:\d{2}:\d{2}|\d+w\d+d|\d+d\d+h|\d+[hms]|\d+y\d+w|\d+[wd]|never(?:-active)?)\b'
    best_uptime_match_obj = None
    for match_obj in re.finditer(uptime_pattern_regex, original_line):
        is_valid_candidate = True
        if match_obj.start() > 0:
            char_before = original_line[match_obj.start() - 1]
            if char_before.isdigit() or char_before in '.:/':
                is_valid_candidate = False
        if match_obj.end() < len(original_line):
            char_after = original_line[match_obj.end()]
            if char_after.isdigit() or char_after == ':':
                is_valid_candidate = False
        if is_valid_candidate:
            best_uptime_match_obj = match_obj
    if best_uptime_match_obj:
        uptime_val = best_uptime_match_obj.group(1)

    # Enhanced next hop detection for various formats
    via_ip_interface_match = re.search(r'via\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*,\s*([\w/\-\.:]+)', original_line,
                                       re.IGNORECASE)
    if via_ip_interface_match:
        next_hop_ip_val = via_ip_interface_match.group(1)
    else:
        via_ip_match = re.search(r'via\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', original_line, re.IGNORECASE)
        if via_ip_match:
            next_hop_ip_val = via_ip_match.group(1)

    if next_hop_ip_val == "N/A":
        # Check for connected route indicators
        connected_match = re.search(r'(?:is\s+)?directly\s+connected(?:,\s*([\w/\-\.:]+))?', original_line,
                                    re.IGNORECASE)
        attached_match = re.search(r',\s*attached(?:,\s*([\w/\-\.:]+))?', original_line, re.IGNORECASE)
        local_match = re.search(r',\s*local(?:,\s*([\w/\-\.:]+))?', original_line, re.IGNORECASE)
        if connected_match or attached_match:
            next_hop_ip_val = "Connected"
        elif local_match:
            next_hop_ip_val = "Local"

    recursive_match = re.search(r'recursive\s+(?:next\s+hop\s+is|via)\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
                                original_line, re.IGNORECASE)
    if recursive_match:
        next_hop_ip_val = recursive_match.group(1)

    null_route_match = re.search(r'(Null0|reject|unreachable|discard)', original_line, re.IGNORECASE)
    if null_route_match:
        next_hop_ip_val = null_route_match.group(1).capitalize()

    return next_hop_ip_val, uptime_val

def extract_ad_from_line(line):
    """
    Extracts Administrative Distance from route line.
    """
    ad_metric_match = re.search(r'\[(\d{1,3})/([^\]]+)\]', line)
    if ad_metric_match:
        try:
            ad = int(ad_metric_match.group(1))
            return ad
        except ValueError:
            pass
    return None

def extract_protocol_instance(line):
    """
    Extracts protocol instance name like "eigrp-6666" or "bgp-65023".
    """
    protocol_instance_match = re.search(r',\s*([a-zA-Z]+-\d+)(?:,\s*(internal|external))?$', line)
    if protocol_instance_match:
        return protocol_instance_match.group(1)

    alt_protocol_match = re.search(r'\b([a-zA-Z]+)-(\d+)\b', line)
    if alt_protocol_match:
        proto = alt_protocol_match.group(1).lower()
        if proto in ('bgp', 'eigrp', 'ospf', 'isis', 'rip'):
            return f"{proto}-{alt_protocol_match.group(2)}"

    return None

def determine_protocol(line_str, initial_text_code=None):
    """
    Determines the routing protocol from a line string, using AD, text codes, and specific names.
    """
    # First, check for explicit protocol instance name (like eigrp-6666)
    protocol_instance = extract_protocol_instance(line_str)
    if protocol_instance:
        # If we have a specific instance, use it as our primary identifier
        proto_base = protocol_instance.split('-')[0].lower()
        if proto_base in PROTOCOL_CODE_MAP:
            mapped_name = PROTOCOL_CODE_MAP[proto_base]
            return f"{mapped_name} ({protocol_instance})"
        return protocol_instance  # Return as-is if not in our map

    # Check administrative distance to determine protocol
    ad = extract_ad_from_line(line_str)
    ad_protocol = None
    if ad is not None:
        ad_protocol = ADMINISTRATIVE_DISTANCES.get(ad)

    # Check for NX-OS style protocol name at the end of the line
    specific_name_p = None
    nxos_style_name_match = re.search(r',\s*([a-zA-Z][a-zA-Z0-9_-]+)(?:,\s*(internal|external))?$', line_str)
    if nxos_style_name_match:
        proto_candidate = nxos_style_name_match.group(1).strip()
        if proto_candidate.lower() in PROTOCOL_CODE_MAP:
            proto_type = nxos_style_name_match.group(2) if nxos_style_name_match.group(2) else ""
            specific_name_p = PROTOCOL_CODE_MAP[proto_candidate.lower()]
            if proto_type:
                specific_name_p += f" {proto_type.capitalize()}"

    # Process traditional protocol code
    normalized_code_p = None
    if initial_text_code:
        # Process NX-OS style codes differently if needed
        if re.match(r'^[a-zA-Z]+-\d+', initial_text_code):
            return initial_text_code  # Return protocol-ASN format directly

        normalized_code_p = PROTOCOL_CODE_MAP.get(initial_text_code,
                                                  PROTOCOL_CODE_MAP.get(initial_text_code.lower(),
                                                                        initial_text_code))

    # Prioritize and refine protocol identification
    if specific_name_p:
        # If we have a specific name and AD, combine them if they're different types
        if ad_protocol and ad_protocol != specific_name_p and (
                (specific_name_p == "BGP" and (ad_protocol == "eBGP" or ad_protocol == "iBGP")) or
                (specific_name_p == "EIGRP" and (ad_protocol == "EIGRP External" or ad_protocol == "EIGRP Internal"))
        ):
            return ad_protocol
        return specific_name_p

    if normalized_code_p:
        # If we have a normalized code and AD, refine it with AD if possible
        if ad_protocol:
            if normalized_code_p == "BGP" and (ad_protocol == "eBGP" or ad_protocol == "iBGP"):
                return ad_protocol
            elif normalized_code_p == "EIGRP" and (
                    ad_protocol == "EIGRP External" or
                    ad_protocol == "EIGRP Internal" or
                    ad_protocol == "EIGRP Summary"
            ):
                return ad_protocol
        return normalized_code_p

    if ad_protocol:
        return ad_protocol

    # Fallback guessing for lines without clear protocol identifiers
    if not initial_text_code:
        for keyword, protocol in [
            ("bgp", "BGP"),
            ("ospf", "OSPF"),
            ("eigrp", "EIGRP"),
            ("isis", "IS-IS"),
            ("is-is", "IS-IS"),
            ("rip", "RIP"),
            ("static", "Static"),
            ("direct", "Connected"),
            ("local", "Local")
        ]:
            if keyword in line_str.lower():
                return f"{protocol} (detected)"

        # Additional check for lines with AD but no protocol code
        if ad is not None and "[" in line_str and "]" in line_str:
            return f"AD {ad}" if not ad_protocol else ad_protocol

    return initial_text_code if initial_text_code else "Unknown"
def extract_routes(filename):
    """
    Parse a Cisco IOS/​NX-OS routing-table text file and return

        defaultdict(list)  → { subnet(str): [ (protocol, next_hop, uptime), … ] }

    Key points
    ----------
    • Subnet-group lines     ← “A.B.C.D/nn is (variably) subnetted …”
    • Every child route      ← inherits /nn when it has no explicit mask.
    • A group stays “open”   ← until a new grouping line *or* the first route
                                whose IP is not contained in the group network.
    • Indentation is *ignored* – only real network-containment is trusted.
    """
    routes = defaultdict(list)

    try:
        with open(filename, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        print(f"ERROR: file {filename} not found")
        return routes

    # ---------- state holders -------------------------------------------------
    in_group = False
    group_net_obj = None           # ip_network('33.0.0.0/8')
    group_mask = None              # '8' (str)
    variably_sub = False           # True ⇢ “variably subnetted”

    cur_proto_for_block = "Unknown"
    cur_subnet_for_mpath = None    # remember subnet while reading its multipaths

    # ---------- helpers -------------------------------------------------------
    def belongs_to_group(ip_str: str) -> bool:
        """True if ip_str is inside the currently-open grouping network."""
        if not in_group or group_net_obj is None:
            return False
        try:
            return ipaddress.ip_address(ip_str) in group_net_obj
        except ValueError:
            return False

    # --------------------------------------------------------------------------
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        # skip banners / code blocks
        if not line or line.startswith(("Codes:", "Gateway of last resort")):
            i += 1
            continue

        # ------------------------------------------------------------------ #
        # 1) SUBNET-GROUPING LINES                                           #
        # ------------------------------------------------------------------ #
        grp_match = re.match(
            r"^\s*("                     # leading spaces
            r"\d{1,3}(?:\.\d{1,3}){3}"   #   network IP
            r"/\d{1,2})"                 #   /mask
            r"\s+is\s+"
            r"((?:variably\s+)?)subnetted",  # flag group type
            line,
        )
        if grp_match:
            grp_cidr = grp_match.group(1)        # e.g. "33.0.0.0/8"
            variably_sub = bool(grp_match.group(2))
            try:
                group_net_obj = ipaddress.ip_network(grp_cidr, strict=False)
                group_mask = grp_cidr.split("/")[-1]
                in_group = True
            except ValueError:
                # bad grouping line – ignore it
                in_group = False
                group_net_obj = None
                group_mask = None
            i += 1
            continue  # → next line

        # ------------------------------------------------------------------ #
        # 2) REGULAR ROUTE LINES (protocol + destination)                    #
        # ------------------------------------------------------------------ #
        proto_match = re.match(
            r"^\s*([A-Za-z\*][A-Za-z0-9\*\+\-]*)\s+"     # protocol code
            r"(\d{1,3}(?:\.\d{1,3}){3})",                # dest IP
            line,
        )
        if proto_match:
            text_proto = proto_match.group(1).strip()
            dest_ip = proto_match.group(2)

            cur_proto_for_block = determine_protocol(line, text_proto)

            # ----------------------------------------------------------------
            # Extract mask if explicitly present
            # ----------------------------------------------------------------
            rest = line[proto_match.end(2):]
            mask_cidr = None
            mask_dotted = None
            m = re.match(
                r"(?:/(\d{1,2})|"
                r"\s+(\d{1,3}(?:\.\d{1,3}){3}))",  # dotted mask
                rest,
            )
            if m:
                mask_cidr = m.group(1)
                mask_dotted = m.group(2)

            if mask_cidr:
                subnet_str = f"{dest_ip}/{mask_cidr}"
            elif mask_dotted:
                subnet_str = f"{dest_ip} {mask_dotted}"
            else:
                # ------ inherit grouping mask if we belong to the group ------
                if belongs_to_group(dest_ip) and group_mask:
                    subnet_str = f"{dest_ip}/{group_mask}"
                else:
                    subnet_str = dest_ip  # will normalise to /32

            norm_subnet = normalize_subnet(subnet_str)

            # next-hop + uptime
            nhop, up = extract_path_attributes(line)
            if nhop != "N/A":
                routes[norm_subnet].append((cur_proto_for_block, nhop, up))
            cur_subnet_for_mpath = norm_subnet

            # ----------------------------------------------------------------
            # handle multipath continuation lines immediately below
            # ----------------------------------------------------------------
            k = i + 1
            while k < len(lines) and lines[k].startswith(" "):
                mline = lines[k].strip()
                if not mline or "is subnetted" in mline:
                    k += 1
                    continue

                # a brand-new route (protocol + ip) → break out
                if re.match(r"^[A-Za-z\*][A-Za-z0-9\*\+\-]*\s+\d", mline):
                    break

                # accept only real path lines
                if not any(key in mline.lower() for key in ("via", "connected", "[")):
                    break

                mp_proto = cur_proto_for_block
                # refine protocol from AD if present
                ad_val = extract_ad_from_line(mline)
                if ad_val in ADMINISTRATIVE_DISTANCES:
                    mp_proto = ADMINISTRATIVE_DISTANCES[ad_val]

                mp_nhop, mp_up = extract_path_attributes(mline)
                if mp_nhop != "N/A":
                    routes[cur_subnet_for_mpath].append((mp_proto, mp_nhop, mp_up))

                k += 1
            i = k
            continue  # processed a full route block

        # ------------------------------------------------------------------ #
        # 3) LEAVE THE CURRENT GROUP IF ROUTE NOT INSIDE NETWORK             #
        # ------------------------------------------------------------------ #
        if in_group:
            # Any line that starts with protocol + dest IP but IP isn’t in group
            leave_match = re.match(
                r"^\s*([A-Za-z\*][A-Za-z0-9\*\+\-]*)\s+"
                r"(\d{1,3}(?:\.\d{1,3}){3})",
                line,
            )
            if leave_match:
                cand_ip = leave_match.group(2)
                if not belongs_to_group(cand_ip):
                    in_group = False
                    group_net_obj = None
                    group_mask = None

        i += 1  # next raw line
    # ----------------------------------------------------------------------

    return routes


def sort_ip_networks(subnets):
    """
    Sort IP networks properly.
    """
    networks = []
    invalid_subnets = []
    for subnet_str in subnets:
        try:
            networks.append(ipaddress.ip_network(subnet_str, strict=False))
        except ValueError:
            invalid_subnets.append(subnet_str)
    sorted_valid_networks = sorted(networks)
    return [str(net) for net in sorted_valid_networks] + sorted(invalid_subnets)

def format_multipath(paths):
    """
    Format multipath route information.
    """
    if not paths:
        return "N/A", "N/A", "N/A"

    unique_protocols = sorted(list(set(p[0] for p in paths if p and p[0] is not None)))
    protocol_str = ", ".join(unique_protocols) if unique_protocols else "N/A"

    next_hops_list = sorted(list(set(p[1] for p in paths if p and p[1] is not None)))
    next_hop_ip_str = " | ".join(next_hops_list) if next_hops_list else "N/A"

    uptimes_list = sorted(list(set(p[2] for p in paths if p and len(p) > 2 and p[2] is not None)))
    uptime_str = " | ".join(uptimes_list) if uptimes_list else "N/A"

    return protocol_str, next_hop_ip_str, uptime_str

def display_menu():
    """
    Display the main menu and get user selection.
    """
    print("\n" + "="*60)
    print("  CISCO ROUTE COMPARISON TOOL")
    print("="*60)
    print("1. Capture BEFORE state from devices")
    print("2. Capture AFTER state from devices") 
    print("3. Compare BEFORE/AFTER and generate reports")
    print("4. Exit")
    print("="*60)
    
    while True:
        try:
            choice = input("Select option (1-4): ").strip()
            if choice in ['1', '2', '3', '4']:
                return int(choice)
            else:
                print("Invalid choice. Please select 1, 2, 3, or 4.")
        except (ValueError, KeyboardInterrupt):
            print("\nExiting...")
            return 4
        
def format_covering_routes(covering_routes):
    """
    Format covering routes for display in CSV.
    """
    if not covering_routes:
        return "No covering route found"
    
    formatted = []
    for subnet, route_info in covering_routes[:3]:  # Show up to 3 covering routes
        protocols = sorted(list(set(p[0] for p in route_info if p and p[0] is not None)))
        protocol_str = ", ".join(protocols) if protocols else "Unknown"
        formatted.append(f"{subnet} ({protocol_str})")
    
    result = " | ".join(formatted)
    if len(covering_routes) > 3:
        result += f" [+{len(covering_routes) - 3} more]"
    
    return result

def compare_and_output(routes1, routes2, output_file, file1_name, file2_name):
    """
    Compare routes from two files and output the differences to a CSV file.
    Enhanced with subnet coverage analysis.
    """
    try:
        all_subnets = set(list(routes1.keys()) + list(routes2.keys()))
        sorted_subnets = sort_ip_networks(list(all_subnets))

        with open(output_file, 'w', newline='') as csvfile:
            fieldnames = ['Subnet',
                          f'{file1_name}_Protocol', f'{file1_name}_NextHop_IP', f'{file1_name}_Uptime',
                          f'{file2_name}_Protocol', f'{file2_name}_NextHop_IP', f'{file2_name}_Uptime',
                          'Status', 'Coverage_Analysis']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for subnet in sorted_subnets:
                in_file1 = subnet in routes1
                in_file2 = subnet in routes2

                # paths are (protocol, next_hop_ip_or_status, uptime)
                paths_file1 = routes1.get(subnet, [])
                paths_file2 = routes2.get(subnet, [])

                f1_protocol, f1_nexthop_ip_str, f1_uptime_str = format_multipath(paths_file1)
                f2_protocol, f2_nexthop_ip_str, f2_uptime_str = format_multipath(paths_file2)

                status_parts = []
                status = ""
                coverage_analysis = ""

                if in_file1 and in_file2:
                    # Use set of full path tuples (proto, hop_ip, time) for exact comparison
                    exact_paths1 = set(paths_file1)
                    exact_paths2 = set(paths_file2)

                    if exact_paths1 == exact_paths2:
                        status = "Same"
                    else:
                        if f1_protocol != f2_protocol:  # Compares summary string of protocols
                            status_parts.append("Protocol")
                        if f1_nexthop_ip_str != f2_nexthop_ip_str:  # Compares summary string of NextHop IPs/statuses
                            status_parts.append("NextHop_IP")
                        if f1_uptime_str != f2_uptime_str:  # Compares summary string of uptimes
                            status_parts.append("Uptime")

                        if not status_parts:  # Summaries are same, but exact (proto,hop,time) tuples differ
                            if len(exact_paths1) != len(exact_paths2):
                                status_parts.append("Path Count / Combination Details")  # More general
                            else:
                                status_parts.append("Path Attribute Combination")

                        status = "Different: " + ", ".join(
                            status_parts) if status_parts else "Different (Undetermined Detail)"

                elif in_file1:  # Route only in file1
                    status = f"Missing in {file2_name}"
                    # Check for covering routes in file2
                    covering_routes = find_covering_routes(subnet, routes2)
                    if covering_routes:
                        coverage_analysis = f"Covered by: {format_covering_routes(covering_routes)}"
                    else:
                        coverage_analysis = "No covering route found"
                        
                else:  # Route only in file2
                    status = f"Missing in {file1_name}"
                    # Check for covering routes in file1
                    covering_routes = find_covering_routes(subnet, routes1)
                    if covering_routes:
                        coverage_analysis = f"Covered by: {format_covering_routes(covering_routes)}"
                    else:
                        coverage_analysis = "No covering route found"

                row = {
                    'Subnet': subnet,
                    f'{file1_name}_Protocol': f1_protocol,
                    f'{file1_name}_NextHop_IP': f1_nexthop_ip_str,  # Updated column name
                    f'{file1_name}_Uptime': f1_uptime_str,
                    f'{file2_name}_Protocol': f2_protocol,
                    f'{file2_name}_NextHop_IP': f2_nexthop_ip_str,  # Updated column name
                    f'{file2_name}_Uptime': f2_uptime_str,
                    'Status': status,
                    'Coverage_Analysis': coverage_analysis
                }
                writer.writerow(row)

        print(f"\nComparison complete. Results saved to {output_file}")

        # Enhanced statistics
        diff_counts = defaultdict(int)
        missing_f1_count = 0
        missing_f2_count = 0
        missing_f1_covered = 0
        missing_f2_covered = 0
        same_count = 0

        with open(output_file, 'r', newline='') as csvfile_read:
            reader = csv.DictReader(csvfile_read)
            for row_read in reader:
                s = row_read['Status']
                coverage = row_read.get('Coverage_Analysis', '')
                
                if s == "Same":
                    same_count += 1
                elif f"Missing in {file1_name}" in s:
                    missing_f1_count += 1
                    if coverage and "Covered by:" in coverage:
                        missing_f1_covered += 1
                elif f"Missing in {file2_name}" in s:
                    missing_f2_count += 1
                    if coverage and "Covered by:" in coverage:
                        missing_f2_covered += 1
                elif s.startswith("Different: "):
                    parts = s.replace("Different: ", "").split(', ')
                    for part in parts:
                        diff_counts[part.strip()] += 1

        print(f"Total unique subnets processed: {len(all_subnets)}")
        print(f"Routes that are the Same: {same_count}")
        print(f"Routes found only in {file1_name} (Missing in {file2_name}): {missing_f2_count}")
        if missing_f2_count > 0:
            print(f"  - Missing routes with covering route: {missing_f2_covered}")
            print(f"  - Missing routes without covering route: {missing_f2_count - missing_f2_covered}")
        print(f"Routes found only in {file2_name} (Missing in {file1_name}): {missing_f1_count}")
        if missing_f1_count > 0:
            print(f"  - Missing routes with covering route: {missing_f1_covered}")
            print(f"  - Missing routes without covering route: {missing_f1_count - missing_f1_covered}")
        
        if diff_counts:
            print("Count of routes with specific differences (a route can have multiple types of differences):")
            for diff_type, count_val in sorted(diff_counts.items()):
                print(f"  - {diff_type}: {count_val}")

    except FileNotFoundError:
        print(f"Error: Output file {output_file} could not be written.")
        sys.exit(1)
    except Exception as e:
        print(f"Error during comparison or writing CSV {output_file}: {type(e).__name__} {e}")
        sys.exit(1)



def create_folder_structure(folder_name):
    """
    Create folder structure and handle existing files by moving them to backup.
    """
    folder_path = Path(folder_name)
    backup_path = folder_path / "backup"
    
    if folder_path.exists():
        print(f"Folder {folder_name} already exists.")
        
        # Get list of existing files
        existing_files = [f for f in folder_path.iterdir() if f.is_file()]
        
        if existing_files:
            print(f"Moving {len(existing_files)} existing files to backup folder...")
            backup_path.mkdir(exist_ok=True)
            
            # Add timestamp to backup subfolder
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            timestamped_backup = backup_path / f"backup_{timestamp}"
            timestamped_backup.mkdir(exist_ok=True)
            
            for file_path in existing_files:
                shutil.move(str(file_path), str(timestamped_backup / file_path.name))
            
            print(f"Existing files moved to {timestamped_backup}")
    else:
        folder_path.mkdir(parents=True)
        print(f"Created folder: {folder_name}")
    
    return folder_path

def read_device_list(csv_file):
    """
    Read device list from CSV file.
    Expected format: device_name, command
    """
    devices = []
    try:
        with open(csv_file, 'r', newline='') as file:
            reader = csv.reader(file)
            # Skip header if it exists
            first_row = next(reader, None)
            if first_row and (first_row[0].lower() in ['device', 'hostname', 'device_name']):
                pass  # Skip header
            else:
                devices.append(first_row)  # Add first row as data
            
            for row in reader:
                if len(row) >= 2 and row[0].strip():  # Ensure we have at least device name and command
                    devices.append([col.strip() for col in row])
        
        print(f"Found {len(devices)} devices in {csv_file}")
        return devices
    
    except FileNotFoundError:
        print(f"Error: Input file {csv_file} not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading {csv_file}: {e}")
        sys.exit(1)

def connect_to_device(device_name, command, username=None, password=None, device_type='cisco_ios'):
    """
    Connect to device and execute command with enhanced timing and buffer handling.
    Returns the command output or None if failed.
    """
    if not NETMIKO_AVAILABLE:
        print(f"Error: netmiko not available for connecting to {device_name}")
        return None
    
    # Prompt for credentials if not provided
    if not username:
        username = input(f"Username for {device_name}: ")
    if not password:
        import getpass
        password = getpass.getpass(f"Password for {device_name}: ")
    
    device_params = {
        'device_type': device_type,
        'host': device_name,
        'username': username,
        'password': password,
        'timeout': 300,  # Increased from 120 to 300 seconds
        'session_timeout': 600,  # Increased from 300 to 600 seconds
        'conn_timeout': 60,  # Increased from 30 to 60 seconds
        'read_timeout_override': 300,  # Add explicit read timeout
        'fast_cli': False,  # Disable fast CLI for better reliability
        'global_delay_factor': 2,  # Add global delay factor
    }
    
    try:
        print(f"Connecting to {device_name}...")
        with ConnectHandler(**device_params) as connection:
            print(f"Connected to {device_name}. Executing command: {command}")
            
            # Clear any existing output in buffer
            connection.clear_buffer()
            
            # Send command with enhanced parameters for large outputs
            print(f"Sending command and waiting for output completion...")
            output = connection.send_command(
                command, 
                expect_string=r'#',
                delay_factor=4,  # Increased from 2 to 4
                max_loops=2000,  # Increased from 1000 to 2000
                strip_prompt=False,
                strip_command=False,
                read_timeout=300,  # Explicit read timeout
                cmd_verify=False  # Disable command verification for speed
            )
            
            # Additional wait to ensure all data is received
            print(f"Command sent. Waiting additional time for output completion...")
            import time
            time.sleep(5)  # Wait 5 seconds for any remaining output
            
            # Try to read any additional output that might still be coming
            try:
                additional_output = connection.read_channel()
                if additional_output.strip():
                    output += additional_output
                    print(f"Captured additional output: {len(additional_output)} characters")
            except:
                pass  # No additional output available
            
            print(f"Command completed on {device_name}. Total output: {len(output)} characters")
            return output
            
    except Exception as e:
        print(f"Error connecting to {device_name}: {e}")
        return None

def validate_large_output(output, expected_keywords=None):
    """
    Validate that the output appears complete for large route tables.
    """
    if not output:
        return False, "No output received"
    
    lines = output.strip().split('\n')
    if len(lines) < 10:  # Very short output might be incomplete
        return False, f"Output too short ({len(lines)} lines)"
    
    # Check for common indicators of incomplete output
    incomplete_indicators = [
        "More --",
        "-- More --", 
        "Output truncated",
        "Buffer overflow"
    ]
    
    last_few_lines = '\n'.join(lines[-5:]).lower()
    for indicator in incomplete_indicators:
        if indicator.lower() in last_few_lines:
            return False, f"Output appears incomplete: found '{indicator}'"
    
    # Check for expected keywords if provided
    if expected_keywords:
        output_lower = output.lower()
        missing_keywords = [kw for kw in expected_keywords if kw.lower() not in output_lower]
        if missing_keywords:
            return False, f"Missing expected content: {missing_keywords}"
    
    return True, "Output appears complete"


def verify_command_completion(output, device_name):
    """
    Enhanced verification for command completion with large output handling.
    """
    if not output:
        return False, "No output received"
    
    lines = output.strip().split('\n')
    if not lines:
        return False, "Empty output"
    
    # Check last several lines for prompt (sometimes output has extra newlines)
    prompt_found = False
    for i in range(min(5, len(lines))):  # Check last 5 lines
        line = lines[-(i+1)].strip()
        if not line:  # Skip empty lines
            continue
            
        # Check if line ends with device prompt
        prompt_patterns = [
            f"{device_name}#",
            f"{device_name.upper()}#",
            f"{device_name.lower()}#",
            r".*#\s*$"  # Generic prompt ending with #
        ]
        
        for pattern in prompt_patterns:
            if re.search(pattern, line):
                prompt_found = True
                break
        
        if prompt_found:
            break
    
    if not prompt_found:
        return False, "Device prompt not found in output"
    
    # Additional validation for large outputs
    is_valid, message = validate_large_output(output, expected_keywords=["route", "network"])
    
    return is_valid, message


def save_device_output(device_name, command, output, folder_path):
    """
    Save device output to a log file with enhanced metadata and validation.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{device_name}_{timestamp}.txt"
    filepath = folder_path / filename
    
    try:
        # Analyze output before saving
        line_count = len(output.split('\n')) if output else 0
        char_count = len(output) if output else 0
        
        with open(filepath, 'w') as file:
            file.write(f"Device: {device_name}\n")
            file.write(f"Command: {command}\n")
            file.write(f"Timestamp: {timestamp}\n")
            file.write(f"Output Statistics: {line_count} lines, {char_count} characters\n")
            file.write("=" * 80 + "\n")
            
            if output:
                file.write(output)
            else:
                file.write("[NO OUTPUT RECEIVED]\n")
            
            file.write("\n")
            file.write("=" * 80 + "\n")
            file.write(f"Capture completed at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        print(f"Output saved to {filepath} ({line_count} lines, {char_count} chars)")
        return filepath
    
    except Exception as e:
        print(f"Error saving output for {device_name}: {e}")
        return None


def capture_device_outputs(mode, input_csv, username=None, password=None):
    """
    Capture outputs from all devices with enhanced timing and validation.
    Mode 1: Save to 'before' folder
    Mode 2: Save to 'after' folder
    """
    folder_name = "before" if mode == 1 else "after"
    folder_path = create_folder_structure(folder_name)
    
    devices = read_device_list(input_csv)
    
    if not devices:
        print("No devices found in input file.")
        return
    
    # Get credentials once for all devices
    if not username:
        username = input("Username for device connections: ")
    if not password:
        import getpass
        password = getpass.getpass("Password for device connections: ")
    
    successful_captures = 0
    failed_captures = 0
    warnings = 0
    
    print(f"\nStarting capture from {len(devices)} devices...")
    print("Note: Using enhanced timing for large outputs - this may take longer than usual.\n")
    
    for i, device_info in enumerate(devices, 1):
        device_name = device_info[0]
        command = device_info[1] if len(device_info) > 1 else "show ip route"
        
        print(f"[{i}/{len(devices)}] Processing device: {device_name}")
        print(f"Command: {command}")
        
        # Connect and execute command with enhanced timing
        start_time = datetime.datetime.now()
        output = connect_to_device(device_name, command, username, password)
        end_time = datetime.datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        print(f"Command execution time: {duration:.1f} seconds")
        
        if output:
            # Enhanced verification for command completion
            is_complete, validation_message = verify_command_completion(output, device_name)
            
            if is_complete:
                print(f"✓ Command completed successfully on {device_name}")
                print(f"  Validation: {validation_message}")
                
                # Save output
                filepath = save_device_output(device_name, command, output, folder_path)
                if filepath:
                    successful_captures += 1
                else:
                    failed_captures += 1
            else:
                print(f"⚠ Command completed with warnings on {device_name}")
                print(f"  Issue: {validation_message}")
                
                # Save anyway but mark as potentially incomplete
                warning_note = f"\n[WARNING: {validation_message}]\n[Capture time: {duration:.1f}s]\n"
                filepath = save_device_output(device_name, command, output + warning_note, folder_path)
                if filepath:
                    warnings += 1
                    successful_captures += 1
                else:
                    failed_captures += 1
        else:
            print(f"✗ Failed to get output from {device_name}")
            failed_captures += 1
        
        print(f"{'='*60}")
    
    print(f"\nCapture Summary:")
    print(f"Successful captures: {successful_captures}")
    print(f"Captures with warnings: {warnings}")
    print(f"Failed captures: {failed_captures}")
    print(f"Outputs saved in: {folder_path}")
    
    if warnings > 0:
        print(f"\nNote: {warnings} captures completed with warnings.")
        print("Please review the output files for completeness.")


def normalize_subnet(subnet_str):
    """
    Normalize subnet format to ensure consistent comparison.
    Updated to preserve explicit subnet masks and handle grouping properly.
    """
    if not subnet_str:
        return "InvalidSubnet"
    subnet_str = subnet_str.strip()

    # Handle subnet mask in dotted decimal format (e.g., "192.168.1.0 255.255.255.0")
    if ' ' in subnet_str and re.match(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
                                      subnet_str):
        ip, mask = subnet_str.split(' ', 1)
        try:
            cidr = sum(bin(int(x)).count('1') for x in mask.split('.'))
            return f"{ip}/{cidr}"
        except ValueError:
            return f"{ip}/{mask}"

    # UPDATED: If subnet already has CIDR notation, preserve it as-is
    if '/' in subnet_str:
        try:
            # Validate and normalize the CIDR notation
            network = ipaddress.ip_network(subnet_str, strict=False)
            return str(network)
        except ValueError:
            return subnet_str

    # UPDATED: Only apply /32 if this is truly a single host IP (not part of subnet grouping)
    # This should only happen for standalone IP addresses outside of subnet groups
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', subnet_str):
        try:
            ipaddress.ip_address(subnet_str)
            # Note: The calling function should handle subnet grouping logic
            # This function will only add /32 for truly standalone IPs
            return f"{subnet_str}/32"
        except ValueError:
            pass

    try:
        return str(ipaddress.ip_network(subnet_str, strict=False))
    except ValueError:
        return subnet_str


def find_covering_routes(missing_subnet, available_routes):
    """
    Find routes that could cover the missing subnet.
    Returns a list of tuples: (covering_subnet, route_info)
    """
    try:
        missing_network = ipaddress.ip_network(missing_subnet, strict=False)
    except ValueError:
        return []
    
    covering_routes = []
    
    for available_subnet, route_info in available_routes.items():
        try:
            available_network = ipaddress.ip_network(available_subnet, strict=False)
            if str(available_network) =="0.0.0.0/0":
                continue
            # Check if the available network covers the missing network
            if missing_network.subnet_of(available_network):
                covering_routes.append((available_subnet, route_info))
        except ValueError:
            continue
    
    # Sort by prefix length (more specific first)
    covering_routes.sort(key=lambda x: ipaddress.ip_network(x[0], strict=False).prefixlen, reverse=True)
    
    return covering_routes

# [Include all other route analysis functions from the previous script here]
# extract_path_attributes, extract_ad_from_line, extract_protocol_instance, 
# determine_protocol, extract_routes, sort_ip_networks, format_multipath, etc.

def compare_device_outputs():
    """
    Compare before and after outputs for each device and generate reports.
    """
    before_folder = Path("before")
    after_folder = Path("after")
    output_folder = Path("output")
    
    # Check if required folders exist
    if not before_folder.exists():
        print("Error: 'before' folder not found. Run mode 1 first.")
        return
    
    if not after_folder.exists():
        print("Error: 'after' folder not found. Run mode 2 first.")
        return
    
    # Create output folder
    output_folder.mkdir(exist_ok=True)
    
    # Get device files from both folders - FIXED: Extract device name properly
    before_files = {}
    after_files = {}
    
    # Process before folder files
    for f in before_folder.glob("*.txt"):
        # Extract device name from filename (format: devicename_timestamp.txt)
        device_name = f.stem.split('_')[0]  # Split by underscore and take first part
        before_files[device_name] = f
    
    # Process after folder files  
    for f in after_folder.glob("*.txt"):
        # Extract device name from filename (format: devicename_timestamp.txt)
        device_name = f.stem.split('_')[0]  # Split by underscore and take first part
        after_files[device_name] = f
    
    all_devices = set(before_files.keys()) | set(after_files.keys())
    
    if not all_devices:
        print("No device files found for comparison.")
        return
    
    print(f"Found {len(all_devices)} devices for comparison")
    print(f"Before files: {list(before_files.keys())}")
    print(f"After files: {list(after_files.keys())}")
    
    combined_results = []
    successful_comparisons = 0
    
    for device_name in sorted(all_devices):
        print(f"\nProcessing device: {device_name}")
        
        before_file = before_files.get(device_name)
        after_file = after_files.get(device_name)
        
        if not before_file:
            print(f"  Warning: No 'before' file found for {device_name}")
            continue
        
        if not after_file:
            print(f"  Warning: No 'after' file found for {device_name}")
            continue
        
        # Generate comparison for this device
        output_csv = output_folder / f"{device_name}_comparison.csv"
        
        try:
            # FIXED: Pass the actual file paths, not just device names
            print(f"  Extracting routes from {before_file.name}...")
            routes1 = extract_routes(str(before_file))  # Convert Path to string
            
            print(f"  Extracting routes from {after_file.name}...")
            routes2 = extract_routes(str(after_file))   # Convert Path to string
            
            print(f"  Found {len(routes1)} routes in before file, {len(routes2)} routes in after file")
            
            # Compare and generate output
            print(f"  Comparing routes and generating {output_csv.name}...")
            compare_and_output(routes1, routes2, str(output_csv), "before", "after")
            
            # Read the generated CSV to add to combined results
            with open(output_csv, 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    row['Device'] = device_name
                    row['Source_File'] = output_csv.name
                    combined_results.append(row)
            
            successful_comparisons += 1
            print(f"  ✓ Comparison completed for {device_name}")
        
        except Exception as e:
            print(f"  ✗ Error comparing {device_name}: {e}")
            print(f"    Before file: {before_file}")
            print(f"    After file: {after_file}")
    
    # Generate combined CSV
    if combined_results:
        combined_csv = output_folder / "combined_comparison.csv"
        print(f"\nGenerating combined report: {combined_csv}")
        
        # Get all unique fieldnames
        all_fieldnames = set()
        for row in combined_results:
            all_fieldnames.update(row.keys())
        
        # Ensure Device and Source_File are first columns
        fieldnames = ['Device', 'Source_File']
        remaining_fields = sorted(all_fieldnames - set(fieldnames))
        fieldnames.extend(remaining_fields)
        
        with open(combined_csv, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            # Sort by device name and then by subnet
            combined_results.sort(key=lambda x: (x.get('Device', ''), x.get('Subnet', '')))
            writer.writerows(combined_results)
        
        print(f"Combined report saved with {len(combined_results)} route comparisons")
    
    print(f"\nComparison Summary:")
    print(f"Successful device comparisons: {successful_comparisons}")
    print(f"Individual reports saved in: {output_folder}")
    if combined_results:
        print(f"Combined report: {output_folder / 'combined_comparison.csv'}")


def main():
    """
    Main function with menu-driven interface.
    """
    print("Cisco Route Comparison Script - Menu Mode")
    
    # Check if netmiko is available at startup
    if not NETMIKO_AVAILABLE:
        print("Warning: netmiko not available. Install with: pip install netmiko")
        print("Device connection features will not work.\n")
    
    while True:
        choice = display_menu()
        
        if choice == 1:
            print("\n--- CAPTURING BEFORE STATE ---")
            input_file = input("Enter CSV file path (default: devices.csv): ").strip()
            if not input_file:
                input_file = "devices.csv"
            
            if not os.path.exists(input_file):
                print(f"Error: Input file {input_file} not found")
                input("Press Enter to continue...")
                continue
            
            username = input("Username for device connections (optional): ").strip() or None
            
            try:
                capture_device_outputs(1, input_file, username, None)
                print("\n✓ BEFORE state capture completed!")
            except Exception as e:
                print(f"\n✗ Error during BEFORE state capture: {e}")
            
            input("Press Enter to return to menu...")
        
        elif choice == 2:
            print("\n--- CAPTURING AFTER STATE ---")
            input_file = input("Enter CSV file path (default: devices.csv): ").strip()
            if not input_file:
                input_file = "devices.csv"
            
            if not os.path.exists(input_file):
                print(f"Error: Input file {input_file} not found")
                input("Press Enter to continue...")
                continue
            
            username = input("Username for device connections (optional): ").strip() or None
            
            try:
                capture_device_outputs(2, input_file, username, None)
                print("\n✓ AFTER state capture completed!")
            except Exception as e:
                print(f"\n✗ Error during AFTER state capture: {e}")
            
            input("Press Enter to return to menu...")
        
        elif choice == 3:
            print("\n--- COMPARING BEFORE/AFTER STATES ---")
            try:
                compare_device_outputs()
                print("\n✓ Comparison completed!")
            except Exception as e:
                print(f"\n✗ Error during comparison: {e}")
            
            input("Press Enter to return to menu...")
        
        elif choice == 4:
            print("\nThank you for using Cisco Route Comparison Tool!")
            print("Goodbye!")
            break


if __name__ == "__main__":
    main()
