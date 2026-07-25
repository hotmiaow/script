#!/usr/bin/env python3
"""
Cisco Route Comparison Script (Enhanced)

This script reads two Cisco 'show ip route' outputs (IOS/NX-OS), extracts subnets,
next hop IP (or status), route uptime/age, and routing protocol, compares them,
and outputs a CSV file showing the differences.

Usage:
    python3 cisco_route_compare.py <file1> <file2> <output_csv>

Example:
    python3 cisco_route_compare.py router1_routes.txt router2_routes.txt route_diff.csv
"""

import re
import csv
import sys
import ipaddress
from collections import defaultdict

# Enhanced Administrative Distances to Protocol Mapping
# Reference: https://www.cisco.com/c/en/us/support/docs/ip/border-gateway-protocol-bgp/15986-admin-distance.html
ADMINISTRATIVE_DISTANCES = {
    0: "Connected",
    1: "Static",
    2: "EIGRP Summary",
    5: "BGP Summary/Aggregate",  # Used for aggregate addresses
    10: "EIGRP Internal",  # Some versions use this
    20: "eBGP",
    70: "EIGRP (IGRP)",  # Older IGRP converted to EIGRP
    90: "EIGRP Internal",  # Most common AD for internal EIGRP
    100: "IGRP",
    105: "EIGRP (XOS)",  # Some NX-OS use this value for EIGRP
    110: "OSPF",
    115: "IS-IS",
    120: "RIP",
    130: "PIM",  # Protocol Independent Multicast
    140: "ODR",  # On-Demand Routing
    150: "EIGRP External (XOS)",  # Some NX-OS use this value
    160: "BGP Local (XOS)",  # Some NX-OS variants
    170: "EIGRP External",  # Common AD for external EIGRP routes
    180: "mVPN",  # Multicast VPN
    190: "OSPFV3",  # OSPFv3 for IPv6
    200: "iBGP",
    220: "IS-IS L2",  # IS-IS Level 2
    254: "DHCP",  # DHCP-installed routes
    255: "Unreachable"  # Usually means "do not use"
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
    "EX": "EIGRP External",  # Often follows 'D'
    "IA": "OSPF Inter-area",  # Often follows 'O'
    "i": "IS-IS", "i*": "IS-IS",
    "i SU": "IS-IS Summary", "i*SU": "IS-IS Summary",
    "i L1": "IS-IS Level 1", "i*L1": "IS-IS Level 1",
    "i L2": "IS-IS Level 2", "i*L2": "IS-IS Level 2",
    "E": "EGP",
    "U": "Unknown/Per-user Static",
    "H": "NHRP",
    "ND": "ND",  # IPv6 Neighbor Discovery
    "NDp": "ND Prefix",
    "ND D": "ND Default",
    "m": "Mobile",  # Mobile routes
    "P": "PIM",  # Protocol Independent Multicast
    "M": "mVPN",  # Multicast VPN
    "V": "VPN",  # VPN routes
    # Entries for specific named protocols that might appear as codes
    "bgp": "BGP", "eigrp": "EIGRP", "ospf": "OSPF", "static": "Static", "connected": "Connected",
    "isis": "IS-IS", "rip": "RIP", "local": "Local", "direct": "Connected",
}


def normalize_subnet(subnet_str):
    """
    Normalize subnet format to ensure consistent comparison.
    """
    if not subnet_str:
        return "InvalidSubnet"
    subnet_str = subnet_str.strip()

    if ' ' in subnet_str and re.match(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
                                      subnet_str):
        ip, mask = subnet_str.split(' ', 1)
        try:
            cidr = sum(bin(int(x)).count('1') for x in mask.split('.'))
            return f"{ip}/{cidr}"
        except ValueError:
            return f"{ip}/{mask}"

    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', subnet_str):
        try:
            ipaddress.ip_address(subnet_str)
            return f"{subnet_str}/32"
        except ValueError:
            pass

    try:
        return str(ipaddress.ip_network(subnet_str, strict=False))
    except ValueError:
        return subnet_str


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
    # Look for AD/metric pattern like [20/0] or [110/41] or [90/156160]
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
    # Pattern to match protocol-ASN format at the end of the line
    protocol_instance_match = re.search(r',\s*([a-zA-Z]+-\d+)(?:,\s*(internal|external))?$', line)
    if protocol_instance_match:
        return protocol_instance_match.group(1)

    # Alternative pattern that might occur elsewhere in the line
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
    routes = defaultdict(list)
    try:
        with open(filename, 'r') as file:
            content = file.readlines()

        current_protocol_for_block = "Unknown"  # Initialize
        current_subnet_for_multipath = None

        i = 0
        while i < len(content):
            line_stripped = content[i].strip()
            original_line_content = content[i]

            if not line_stripped or line_stripped.startswith("Codes:") or \
                    line_stripped.startswith("Gateway of last resort is"):
                i += 1
                continue

            # Regex to capture initial protocol code/name and the start of an IP address
            # Protocol part can be complex, e.g., "D*EX", "OSPF IA", "bgp-65000"
            protocol_line_match = re.match(
                r'^\s*((?!Codes:)[A-Za-z\*][A-Za-z0-9\*\+\-\s\/\(\)\._]*?)\s+([0-9]{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
                line_stripped)

            nxos_ip_start_match = None
            if not protocol_line_match:
                nxos_ip_start_match = re.match(
                    r'^\s*([0-9]{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2}|(?:\s+\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})))',
                    line_stripped)

            parsed_this_line_as_primary = False
            line_protocol = "Unknown"

            if protocol_line_match:
                parsed_this_line_as_primary = True
                text_protocol_candidate = protocol_line_match.group(1).strip()
                line_protocol = determine_protocol(line_stripped, text_protocol_candidate)
                current_protocol_for_block = line_protocol  # Update context for subsequent multipaths

                line_for_subnet_extraction = line_stripped[protocol_line_match.start(2):]
                subnet_str_match = re.match(
                    r'([0-9]{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2}|(?:\s+\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})))',
                    line_for_subnet_extraction)
                if not subnet_str_match:
                    i += 1
                    continue

                subnet_str = subnet_str_match.group(1)
                normalized_subnet = normalize_subnet(subnet_str)
                next_hop_ip_or_status, uptime = extract_path_attributes(line_stripped)

                if "is subnetted" in line_stripped or "variably subnetted" in line_stripped:
                    current_subnet_for_multipath = None
                elif next_hop_ip_or_status != "N/A":
                    routes[normalized_subnet].append((line_protocol, next_hop_ip_or_status, uptime))
                    current_subnet_for_multipath = normalized_subnet
                else:
                    current_subnet_for_multipath = normalized_subnet

                k = i + 1  # Start multipath check from next line
                while k < len(content) and content[k].startswith(' '):
                    multipath_line_stripped = content[k].strip()
                    if not multipath_line_stripped:
                        k += 1
                        continue

                    is_new_indented_subnet_decl = re.match(
                        r'^(?:[A-Za-z\*][A-Za-z0-9\*\+\-\s\/\(\)\._]*?\s+)?([0-9]{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
                        multipath_line_stripped)
                    if is_new_indented_subnet_decl and not (
                            "via" in multipath_line_stripped.lower() or "connected" in multipath_line_stripped.lower()):
                        break

                        # Check if multipath line contains its own protocol information
                    multipath_protocol = current_protocol_for_block  # Default to primary route's protocol

                    # Extract AD from multipath line if present
                    multipath_ad = extract_ad_from_line(multipath_line_stripped)
                    if multipath_ad is not None:
                        ad_protocol = ADMINISTRATIVE_DISTANCES.get(multipath_ad)
                        if ad_protocol:
                            multipath_protocol = ad_protocol

                    # Look for protocol instance in multipath line
                    mp_protocol_instance = extract_protocol_instance(multipath_line_stripped)
                    if mp_protocol_instance:
                        proto_base = mp_protocol_instance.split('-')[0].lower()
                        if proto_base in PROTOCOL_CODE_MAP:
                            multipath_protocol = f"{PROTOCOL_CODE_MAP[proto_base]} ({mp_protocol_instance})"
                        else:
                            multipath_protocol = mp_protocol_instance

                    mp_next_hop_ip_or_status, mp_uptime = extract_path_attributes(multipath_line_stripped)
                    if mp_next_hop_ip_or_status != "N/A" and current_subnet_for_multipath:
                        routes[current_subnet_for_multipath].append(
                            (multipath_protocol, mp_next_hop_ip_or_status, mp_uptime))
                    else:
                        break
                    k += 1
                i = k - 1

            elif nxos_ip_start_match:
                parsed_this_line_as_primary = True
                # For NX-OS outputs, prioritize AD and protocol instance
                protocol_instance = extract_protocol_instance(line_stripped)
                ad = extract_ad_from_line(line_stripped)

                if protocol_instance:
                    proto_base = protocol_instance.split('-')[0].lower()
                    if proto_base in PROTOCOL_CODE_MAP:
                        line_protocol = f"{PROTOCOL_CODE_MAP[proto_base]} ({protocol_instance})"
                    else:
                        line_protocol = protocol_instance
                elif ad is not None and ad in ADMINISTRATIVE_DISTANCES:
                    line_protocol = ADMINISTRATIVE_DISTANCES[ad]
                else:
                    line_protocol = determine_protocol(line_stripped, None)

                current_protocol_for_block = line_protocol  # Update context

                subnet_str = nxos_ip_start_match.group(1)
                normalized_subnet = normalize_subnet(subnet_str)
                next_hop_ip_or_status, uptime = extract_path_attributes(line_stripped)

                if "is subnetted" in line_stripped or "variably subnetted" in line_stripped:
                    current_subnet_for_multipath = None
                elif next_hop_ip_or_status != "N/A":
                    routes[normalized_subnet].append((line_protocol, next_hop_ip_or_status, uptime))
                    current_subnet_for_multipath = normalized_subnet
                else:
                    current_subnet_for_multipath = normalized_subnet

                k = i + 1
                while k < len(content) and content[k].startswith(' '):
                    multipath_line_stripped = content[k].strip()
                    if not multipath_line_stripped:
                        k += 1
                        continue

                    is_new_indented_subnet_decl = re.match(
                        r'^(?:[A-Za-z\*][A-Za-z0-9\*\+\-\s\/\(\)\._]*?\s+)?([0-9]{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
                        multipath_line_stripped)
                    if is_new_indented_subnet_decl and not (
                            "via" in multipath_line_stripped.lower() or "connected" in multipath_line_stripped.lower()):
                        break

                    # Check if multipath line contains its own protocol information
                    multipath_protocol = current_protocol_for_block  # Default

                    # Check for protocol instance in multipath line
                    mp_protocol_instance = extract_protocol_instance(multipath_line_stripped)
                    if mp_protocol_instance:
                        proto_base = mp_protocol_instance.split('-')[0].lower()
                        if proto_base in PROTOCOL_CODE_MAP:
                            multipath_protocol = f"{PROTOCOL_CODE_MAP[proto_base]} ({mp_protocol_instance})"
                        else:
                            multipath_protocol = mp_protocol_instance

                    # Check for AD in multipath line
                    mp_ad = extract_ad_from_line(multipath_line_stripped)
                    if mp_ad is not None and mp_ad in ADMINISTRATIVE_DISTANCES and not mp_protocol_instance:
                        multipath_protocol = ADMINISTRATIVE_DISTANCES[mp_ad]

                    mp_next_hop_ip_or_status, mp_uptime = extract_path_attributes(multipath_line_stripped)
                    if mp_next_hop_ip_or_status != "N/A" and current_subnet_for_multipath:
                        routes[current_subnet_for_multipath].append(
                            (multipath_protocol, mp_next_hop_ip_or_status, mp_uptime))
                    else:
                        break
                    k += 1
                i = k - 1

            elif original_line_content.startswith(' ') and current_subnet_for_multipath:
                if not parsed_this_line_as_primary:
                    # Check if this indented line contains its own protocol information
                    multipath_protocol = current_protocol_for_block  # Default

                    # Extract AD from multipath line if present
                    multipath_ad = extract_ad_from_line(line_stripped)
                    if multipath_ad is not None:
                        ad_protocol = ADMINISTRATIVE_DISTANCES.get(multipath_ad)
                        if ad_protocol:
                            multipath_protocol = ad_protocol

                    # Extract protocol instance if present
                    mp_protocol_instance = extract_protocol_instance(line_stripped)
                    if mp_protocol_instance:
                        proto_base = mp_protocol_instance.split('-')[0].lower()
                        if proto_base in PROTOCOL_CODE_MAP:
                            multipath_protocol = f"{PROTOCOL_CODE_MAP[proto_base]} ({mp_protocol_instance})"
                        else:
                            multipath_protocol = mp_protocol_instance

                    mp_next_hop_ip_or_status, mp_uptime = extract_path_attributes(line_stripped)
                    if mp_next_hop_ip_or_status != "N/A":
                        routes[current_subnet_for_multipath].append(
                            (multipath_protocol, mp_next_hop_ip_or_status, mp_uptime))
            i += 1
        return routes
    except FileNotFoundError:
        print(f"Error: File {filename} not found.")
        sys.exit(1)
    except Exception as e:
        print(
            f"Error processing file {filename}: {type(e).__name__} {e} on line {i + 1 if 'i' in locals() else 'unknown'}")
        sys.exit(1)


def sort_ip_networks(subnets):
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
    if not paths:
        return "N/A", "N/A", "N/A"

    unique_protocols = sorted(list(set(p[0] for p in paths if p and p[0] is not None)))
    protocol_str = ", ".join(unique_protocols) if unique_protocols else "N/A"

    next_hops_list = sorted(list(set(p[1] for p in paths if p and p[1] is not None)))
    next_hop_ip_str = " | ".join(next_hops_list) if next_hops_list else "N/A"

    uptimes_list = sorted(list(set(p[2] for p in paths if p and len(p) > 2 and p[2] is not None)))
    uptime_str = " | ".join(uptimes_list) if uptimes_list else "N/A"

    return protocol_str, next_hop_ip_str, uptime_str


def compare_and_output(routes1, routes2, output_file, file1_name, file2_name):
    """
    Compare routes from two files and output the differences to a CSV file.
    """
    try:
        all_subnets = set(list(routes1.keys()) + list(routes2.keys()))
        sorted_subnets = sort_ip_networks(list(all_subnets))

        with open(output_file, 'w', newline='') as csvfile:
            fieldnames = ['Subnet',
                          f'{file1_name}_Protocol', f'{file1_name}_NextHop_IP', f'{file1_name}_Uptime',
                          f'{file2_name}_Protocol', f'{file2_name}_NextHop_IP', f'{file2_name}_Uptime',
                          'Status']
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
                else:  # Route only in file2
                    status = f"Missing in {file1_name}"

                row = {
                    'Subnet': subnet,
                    f'{file1_name}_Protocol': f1_protocol,
                    f'{file1_name}_NextHop_IP': f1_nexthop_ip_str,  # Updated column name
                    f'{file1_name}_Uptime': f1_uptime_str,
                    f'{file2_name}_Protocol': f2_protocol,
                    f'{file2_name}_NextHop_IP': f2_nexthop_ip_str,  # Updated column name
                    f'{file2_name}_Uptime': f2_uptime_str,
                    'Status': status
                }
                writer.writerow(row)

        print(f"\nComparison complete. Results saved to {output_file}")

        diff_counts = defaultdict(int)
        missing_f1_count = 0
        missing_f2_count = 0
        same_count = 0

        with open(output_file, 'r', newline='') as csvfile_read:
            reader = csv.DictReader(csvfile_read)
            for row_read in reader:
                s = row_read['Status']
                if s == "Same":
                    same_count += 1
                elif f"Missing in {file1_name}" in s:
                    missing_f1_count += 1
                elif f"Missing in {file2_name}" in s:
                    missing_f2_count += 1
                elif s.startswith("Different: "):
                    parts = s.replace("Different: ", "").split(', ')
                    for part in parts:
                        diff_counts[part.strip()] += 1

        print(f"Total unique subnets processed: {len(all_subnets)}")
        print(f"Routes that are the Same: {same_count}")
        print(f"Routes found only in {file1_name} (Missing in {file2_name}): {missing_f2_count}")
        print(f"Routes found only in {file2_name} (Missing in {file1_name}): {missing_f1_count}")
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


def main():
    if len(sys.argv) != 4:
        print("Usage: python3 cisco_route_compare.py <file1> <file2> <output_csv>")
        sys.exit(1)

    file1 = sys.argv[1]
    file2 = sys.argv[2]
    output_csv = sys.argv[3]

    print(f"Extracting routes from {file1}...")
    routes1 = extract_routes(file1)
    print(f"Found {len(routes1)} unique subnets in {file1}")
    total_paths1 = sum(len(paths) for paths in routes1.values())
    print(f"Total paths (including multipaths) in {file1}: {total_paths1}")

    print(f"\nExtracting routes from {file2}...")
    routes2 = extract_routes(file2)
    print(f"Found {len(routes2)} unique subnets in {file2}")
    total_paths2 = sum(len(paths) for paths in routes2.values())
    print(f"Total paths (including multipaths) in {file2}: {total_paths2}")

    print("\nSample routes from first file (first 3):")
    sample_routes1 = list(routes1.items())[:min(3, len(routes1))]
    for subnet, paths_data in sample_routes1:
        # paths_data is list of (protocol, next_hop_ip_or_status, uptime)
        path_str_list = [f"({p[0]} via {p[1]}, age {p[2]})" for p in paths_data]
        print(f"  {subnet}: {' | '.join(path_str_list)}")

    print("\nSample routes from second file (first 3):")
    sample_routes2 = list(routes2.items())[:min(3, len(routes2))]
    for subnet, paths_data in sample_routes2:
        path_str_list = [f"({p[0]} via {p[1]}, age {p[2]})" for p in paths_data]
        print(f"  {subnet}: {' | '.join(path_str_list)}")

    file1_basename = file1.split('/')[-1].split('\\')[-1]
    file2_basename = file2.split('/')[-1].split('\\')[-1]

    # Update column names in the compare function if they are derived from file names
    f1_name_for_column = re.sub(r'\.txt$', '', file1_basename, flags=re.IGNORECASE)
    f2_name_for_column = re.sub(r'\.txt$', '', file2_basename, flags=re.IGNORECASE)

    compare_and_output(routes1, routes2, output_csv,
                       file1_name=f1_name_for_column,
                       file2_name=f2_name_for_column)


if __name__ == "__main__":
    main()