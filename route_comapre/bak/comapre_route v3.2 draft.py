#!/usr/bin/env python3
# updated route coverage logic, both  when do the subnet coverage check , make sure it covering route ( bigger subnet ) is exiting in both before and after and both before and after next hop ip is the same.

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
    python3 cisco_route_compare.py --mode 1 --input input.csv
    python3 cisco_route_compare.py --mode 2 --input input.csv
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

def get_unique_nexthops(route_info):
    """
    Given a list of path tuples (protocol, next_hop, uptime),
    return a sorted list of unique next-hop IP strings (filtering out non-IP placeholders).
    """
    ips = set()
    for p in route_info:
        if not p or len(p) < 2:
            continue
        nh = p[1] or ""
        # Keep only IPv4-like next-hop IPs
        if re.match(r'^\d{1,3}(?:\.\d{1,3}){3}$', nh):
            ips.add(nh)
    return sorted(ips)

def find_valid_covering_routes_in_both(missing_subnet, routes_before, routes_after):
    """
    Find covering routes present in BOTH before and after, and whose next-hop IP sets match across both.
    Returns:
      valid: list of (covering_subnet, before_route_info, after_route_info)
      invalid: list of dicts with keys:
         covering_subnet, in_before, in_after, before_nexthops, after_nexthops, reason
    """
    try:
        missing_network = ipaddress.ip_network(missing_subnet, strict=False)
    except ValueError:
        return [], []

    valid = []
    invalid = []

    # Collect all candidates that cover the missing subnet from either dict
    candidates = set()
    for candidate_dict in (routes_before, routes_after):
        for sub in candidate_dict.keys():
            try:
                cand_net = ipaddress.ip_network(sub, strict=False)
            except ValueError:
                continue
            if str(cand_net) == "0.0.0.0/0":
                continue
            if missing_network.subnet_of(cand_net):
                candidates.add(str(cand_net))

    # Evaluate candidates across both before and after
    for cov in sorted(candidates, key=lambda s: ipaddress.ip_network(s, strict=False).prefixlen, reverse=True):
        in_before = cov in routes_before
        in_after = cov in routes_after
        if not in_before or not in_after:
            invalid.append({
                'covering_subnet': cov,
                'in_before': in_before,
                'in_after': in_after,
                'before_nexthops': [],
                'after_nexthops': [],
                'reason': 'Covering route not present in both'
            })
            continue

        before_info = routes_before[cov]
        after_info = routes_after[cov]
        b_nh = get_unique_nexthops(before_info)
        a_nh = get_unique_nexthops(after_info)

        if b_nh == a_nh and b_nh:
            valid.append((cov, before_info, after_info))
        else:
            invalid.append({
                'covering_subnet': cov,
                'in_before': True,
                'in_after': True,
                'before_nexthops': b_nh,
                'after_nexthops': a_nh,
                'reason': 'Next-hop mismatch between before and after'
            })

    return valid, invalid



def extract_path_attributes(line):
    """
    Enhanced extraction with better multipath support for EIGRP routes.
    """
    original_line = line
    next_hop_ip_val = "N/A"
    uptime_val = "N/A"

    # Enhanced uptime patterns (same as before)
    uptime_patterns = [
        r'\b(\d{1,2}:\d{2}:\d{2})\b',
        r'\b(\d+w\d+d)\b',
        r'\b(\d+d\d+h)\b',
        r'\b(\d+[dhms])\b',
        r'\b(\d+y\d+w)\b',
        r'\b(never(?:-active)?)\b',
        r'\b(\d{2}:\d{2}:\d{2})\b',
    ]
    
    # Find uptime
    best_uptime_match = None
    for pattern in uptime_patterns:
        for match_obj in re.finditer(pattern, original_line, re.IGNORECASE):
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
                best_uptime_match = match_obj
                break
        if best_uptime_match:
            break
    
    if best_uptime_match:
        uptime_val = best_uptime_match.group(1)

    # ENHANCED: Better next-hop detection for multipath EIGRP routes
    next_hop_patterns = [
        # Standard via IP
        r'via\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
        # Through (alternative to via)
        r'through\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
        # ENHANCED: IP address anywhere in the line (for EIGRP multipath)
        r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?!\.\d)',  # IP not followed by another digit
        # Recursive next hop
        r'recursive\s+(?:next\s+hop\s+is|via)\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
    ]
    
    for pattern in next_hop_patterns:
        matches = re.findall(pattern, original_line, re.IGNORECASE)
        if matches:
            # Take the first IP address found
            next_hop_ip_val = matches[0]
            # Validate it's a proper IP address
            try:
                ipaddress.ip_address(next_hop_ip_val)
                break
            except ValueError:
                continue

    # Check for connected routes if no IP found
    if next_hop_ip_val == "N/A":
        connected_patterns = [
            r'(?:is\s+)?directly\s+connected(?:,\s*([\w/\-\.:]+))?',
            r',\s*attached(?:,\s*([\w/\-\.:]+))?',
            r',\s*local(?:,\s*([\w/\-\.:]+))?',
        ]
        
        for i, pattern in enumerate(connected_patterns):
            match = re.search(pattern, original_line, re.IGNORECASE)
            if match:
                if i == 0 or i == 1:
                    next_hop_ip_val = "Connected"
                elif i == 2:
                    next_hop_ip_val = "Local"
                break

    # Check for null routes
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
    Enhanced protocol determination with better support for multi-word codes like "D EX".
    """
    # First, check for explicit protocol instance name (like eigrp-6666)
    protocol_instance = extract_protocol_instance(line_str)
    if protocol_instance:
        proto_base = protocol_instance.split('-')[0].lower()
        if proto_base in PROTOCOL_CODE_MAP:
            mapped_name = PROTOCOL_CODE_MAP[proto_base]
            return f"{mapped_name} ({protocol_instance})"
        return protocol_instance

    # Check administrative distance to determine protocol
    ad = extract_ad_from_line(line_str)
    ad_protocol = None
    if ad is not None:
        ad_protocol = ADMINISTRATIVE_DISTANCES.get(ad)

    # Enhanced protocol code processing for multi-word codes
    if initial_text_code:
        # Handle multi-word protocol codes like "D EX", "O IA", etc.
        code_normalized = initial_text_code.strip().upper()
        
        # Direct mapping for multi-word codes
        multi_word_mappings = {
            "D EX": "EIGRP External",
            "D*EX": "EIGRP External", 
            "O IA": "OSPF Inter-area",
            "O*IA": "OSPF Inter-area",
            "O E1": "OSPF External Type 1",
            "O*E1": "OSPF External Type 1",
            "O E2": "OSPF External Type 2", 
            "O*E2": "OSPF External Type 2",
            "O N1": "OSPF NSSA Type 1",
            "O*N1": "OSPF NSSA Type 1",
            "O N2": "OSPF NSSA Type 2",
            "O*N2": "OSPF NSSA Type 2",
            "i SU": "IS-IS Summary",
            "i*SU": "IS-IS Summary",
            "i L1": "IS-IS Level 1",
            "i*L1": "IS-IS Level 1", 
            "i L2": "IS-IS Level 2",
            "i*L2": "IS-IS Level 2"
        }
        
        if code_normalized in multi_word_mappings:
            protocol_name = multi_word_mappings[code_normalized]
            # Refine with AD if available and more specific
            if ad_protocol and ad_protocol in protocol_name:
                return ad_protocol
            return protocol_name
        
        # Handle single character codes
        single_char_mappings = {
            "B": "BGP", "B*": "BGP",
            "D": "EIGRP Internal", "D*": "EIGRP Internal",
            "O": "OSPF", "O*": "OSPF",
            "S": "Static", "S*": "Static",
            "C": "Connected", "C*": "Connected",
            "L": "Local", "L*": "Local",
            "R": "RIP", "R*": "RIP",
            "i": "IS-IS", "i*": "IS-IS"
        }
        
        if code_normalized in single_char_mappings:
            protocol_name = single_char_mappings[code_normalized]
            # Refine with AD information
            if ad_protocol:
                if protocol_name == "BGP" and ad_protocol in ["eBGP", "iBGP"]:
                    return ad_protocol
                elif protocol_name == "EIGRP Internal" and ad_protocol in ["EIGRP External", "EIGRP Internal", "EIGRP Summary"]:
                    return ad_protocol
            return protocol_name
        
        # Fallback to original mapping
        normalized_code = PROTOCOL_CODE_MAP.get(code_normalized, 
                                              PROTOCOL_CODE_MAP.get(code_normalized.lower(), 
                                                                  initial_text_code))
        if normalized_code:
            return normalized_code

    # Use AD-based detection if available
    if ad_protocol:
        return ad_protocol

    # Fallback to keyword detection
    protocol_keywords = {
        "eigrp": "EIGRP",
        "ospf": "OSPF", 
        "bgp": "BGP",
        "isis": "IS-IS",
        "is-is": "IS-IS",
        "rip": "RIP",
        "static": "Static",
        "connected": "Connected",
        "direct": "Connected",
        "local": "Local"
    }
    
    line_lower = line_str.lower()
    for keyword, protocol in protocol_keywords.items():
        if keyword in line_lower:
            return f"{protocol} (detected)"

    return initial_text_code if initial_text_code else "Unknown"

def detect_subnet_group(line):
    """
    Detect subnet group headers with flexible pattern matching.
    Uses multiple regex patterns with different levels of flexibility.
    Returns: (is_group, base_network, cidr_mask, is_variably_subnetted, expected_count)
    """
    # Clean the line but preserve original for pattern matching
    clean_line = line.strip()
    original_line = line  # Keep original with whitespace for flexible matching
    
    # Comprehensive patterns for subnet grouping - ordered from most specific to most flexible
    patterns = [
        # Pattern 1: Standard CIDR format - "133.0.0.0/16 is subnetted, 2 subnets"
        {
            'regex': r'(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})\s+is\s+subnetted,\s+(\d+)\s+subnets?',
            'variably': False,
            'has_cidr': True,
            'line_type': 'clean'
        },
        
        # Pattern 2: Variably subnetted with CIDR - "132.16.0.0/16 is variably subnetted, 2 subnets, 2 masks"
        {
            'regex': r'(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})\s+is\s+variably\s+subnetted,\s+(\d+)\s+subnets?,\s+(\d+)\s+masks?',
            'variably': True,
            'has_cidr': True,
            'line_type': 'clean'
        },
        
        # Pattern 3: Base network variably subnetted - "171.69.0.0 is variably subnetted, 2 subnets, 2 masks"
        {
            'regex': r'(\d{1,3}(?:\.\d{1,3}){3})\s+is\s+variably\s+subnetted,\s+(\d+)\s+subnets?,\s+(\d+)\s+masks?',
            'variably': True,
            'has_cidr': False,
            'line_type': 'clean'
        },
        
        # Pattern 4: Flexible - handles any amount of leading whitespace (original line)
        {
            'regex': r'^\s*(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})\s+is\s+subnetted,\s+(\d+)\s+subnets?',
            'variably': False,
            'has_cidr': True,
            'line_type': 'original'
        },
        
        # Pattern 5: Flexible variably subnetted with CIDR (original line)
        {
            'regex': r'^\s*(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})\s+is\s+variably\s+subnetted,\s+(\d+)\s+subnets?,\s+(\d+)\s+masks?',
            'variably': True,
            'has_cidr': True,
            'line_type': 'original'
        },
        
        # Pattern 6: Very flexible - any whitespace, optional "variably"
        {
            'regex': r'^\s*(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?\s+is\s+(variably\s+)?subnetted,\s+(\d+)\s+subnets?(?:,\s+(\d+)\s+masks?)?',
            'variably': None,  # Determined by capture group
            'has_cidr': None,  # Determined by capture group
            'line_type': 'original'
        },
        
        # Pattern 7: Ultra-flexible - handles various spacing and formatting issues
        {
            'regex': r'.*?(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?\s+is\s+(variably\s+)?subnetted.*?(\d+)\s+subnets?',
            'variably': None,  # Determined by capture group
            'has_cidr': None,  # Determined by capture group
            'line_type': 'original'
        }
    ]
    
    for pattern_info in patterns:
        # Choose which line version to use
        test_line = clean_line if pattern_info['line_type'] == 'clean' else original_line
        
        match = re.search(pattern_info['regex'], test_line, re.IGNORECASE)
        if match:
            # Handle different group configurations based on pattern
            if pattern_info['regex'] == patterns[5]['regex']:  # Pattern 6 - flexible
                base_network = match.group(1)
                cidr_mask = match.group(2) if match.group(2) else None
                is_variably = bool(match.group(3)) if match.group(3) else False
                expected_count = int(match.group(4))
                has_cidr = bool(cidr_mask)
                
            elif pattern_info['regex'] == patterns[6]['regex']:  # Pattern 7 - ultra-flexible
                base_network = match.group(1)
                cidr_mask = match.group(2) if match.group(2) else None
                is_variably = bool(match.group(3)) if match.group(3) else False
                expected_count = int(match.group(4))
                has_cidr = bool(cidr_mask)
                
            elif pattern_info['has_cidr'] and not pattern_info['variably']:
                # Standard CIDR format
                base_network = match.group(1)
                cidr_mask = match.group(2)
                expected_count = int(match.group(3))
                is_variably = False
                has_cidr = True
                
            elif pattern_info['has_cidr'] and pattern_info['variably']:
                # Variably subnetted with CIDR
                base_network = match.group(1)
                cidr_mask = match.group(2)
                expected_count = int(match.group(3))
                is_variably = True
                has_cidr = True
                
            else:
                # Base network format (no CIDR in header)
                base_network = match.group(1)
                cidr_mask = None
                expected_count = int(match.group(2))
                is_variably = pattern_info['variably']
                has_cidr = False
            
            return True, base_network, cidr_mask, is_variably, expected_count
    
    return False, None, None, False, 0

def detect_subnet_group(line):
    """
    Detect subnet group headers with flexible pattern matching.
    Uses multiple regex patterns with different levels of flexibility.
    Returns: (is_group, base_network, cidr_mask, is_variably_subnetted, expected_count)
    """
    # Clean the line but preserve original for pattern matching
    clean_line = line.strip()
    original_line = line  # Keep original with whitespace for flexible matching
   
    # Comprehensive patterns for subnet grouping - ordered from most specific to most flexible
    patterns = [
        # Pattern 1: Standard CIDR format - "133.0.0.0/16 is subnetted, 2 subnets"
        {
            'regex': r'(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})\s+is\s+subnetted,\s+(\d+)\s+subnets?',
            'variably': False,
            'has_cidr': True,
            'line_type': 'clean'
        },
       
        # Pattern 2: Variably subnetted with CIDR - "132.16.0.0/16 is variably subnetted, 2 subnets, 2 masks"
        {
            'regex': r'(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})\s+is\s+variably\s+subnetted,\s+(\d+)\s+subnets?,\s+(\d+)\s+masks?',
            'variably': True,
            'has_cidr': True,
            'line_type': 'clean'
        },
       
        # Pattern 3: Base network variably subnetted - "171.69.0.0 is variably subnetted, 2 subnets, 2 masks"
        {
            'regex': r'(\d{1,3}(?:\.\d{1,3}){3})\s+is\s+variably\s+subnetted,\s+(\d+)\s+subnets?,\s+(\d+)\s+masks?',
            'variably': True,
            'has_cidr': False,
            'line_type': 'clean'
        },
       
        # Pattern 4: Flexible - handles any amount of leading whitespace (original line)
        {
            'regex': r'^\s*(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})\s+is\s+subnetted,\s+(\d+)\s+subnets?',
            'variably': False,
            'has_cidr': True,
            'line_type': 'original'
        },
       
        # Pattern 5: Flexible variably subnetted with CIDR (original line)
        {
            'regex': r'^\s*(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})\s+is\s+variably\s+subnetted,\s+(\d+)\s+subnets?,\s+(\d+)\s+masks?',
            'variably': True,
            'has_cidr': True,
            'line_type': 'original'
        },
       
        # Pattern 6: Very flexible - any whitespace, optional "variably"
        {
            'regex': r'^\s*(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?\s+is\s+(variably\s+)?subnetted,\s+(\d+)\s+subnets?(?:,\s+(\d+)\s+masks?)?',
            'variably': None,  # Determined by capture group
            'has_cidr': None,  # Determined by capture group
            'line_type': 'original'
        },
       
        # Pattern 7: Ultra-flexible - handles various spacing and formatting issues
        {
            'regex': r'.*?(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?\s+is\s+(variably\s+)?subnetted.*?(\d+)\s+subnets?',
            'variably': None,  # Determined by capture group
            'has_cidr': None,  # Determined by capture group
            'line_type': 'original'
        }
    ]
   
    for pattern_info in patterns:
        # Choose which line version to use
        test_line = clean_line if pattern_info['line_type'] == 'clean' else original_line
       
        match = re.search(pattern_info['regex'], test_line, re.IGNORECASE)
        if match:
            # Handle different group configurations based on pattern
            if pattern_info['regex'] == patterns[5]['regex']:  # Pattern 6 - flexible
                base_network = match.group(1)
                cidr_mask = match.group(2) if match.group(2) else None
                is_variably = bool(match.group(3)) if match.group(3) else False
                expected_count = int(match.group(4))
                has_cidr = bool(cidr_mask)
               
            elif pattern_info['regex'] == patterns[6]['regex']:  # Pattern 7 - ultra-flexible
                base_network = match.group(1)
                cidr_mask = match.group(2) if match.group(2) else None
                is_variably = bool(match.group(3)) if match.group(3) else False
                expected_count = int(match.group(4))
                has_cidr = bool(cidr_mask)
               
            elif pattern_info['has_cidr'] and not pattern_info['variably']:
                # Standard CIDR format
                base_network = match.group(1)
                cidr_mask = match.group(2)
                expected_count = int(match.group(3))
                is_variably = False
                has_cidr = True
               
            elif pattern_info['has_cidr'] and pattern_info['variably']:
                # Variably subnetted with CIDR
                base_network = match.group(1)
                cidr_mask = match.group(2)
                expected_count = int(match.group(3))
                is_variably = True
                has_cidr = True
               
            else:
                # Base network format (no CIDR in header)
                base_network = match.group(1)
                cidr_mask = None
                expected_count = int(match.group(2))
                is_variably = pattern_info['variably']
                has_cidr = False
           
            return True, base_network, cidr_mask, is_variably, expected_count
   
    return False, None, None, False, 0

def extract_routes(filename):
    """
    Enhanced route extraction with comprehensive error handling.
    """
    routes = defaultdict(list)
    
    # Validate input
    if not filename:
        print("Error: No filename provided for route extraction")
        return routes
        
    if not os.path.exists(filename):
        print(f"Error: Route file '{filename}' not found")
        return routes
        
    if not os.path.isfile(filename):
        print(f"Error: '{filename}' is not a regular file")
        return routes

    try:
        # Check file size
        file_size = os.path.getsize(filename)
        if file_size == 0:
            print(f"Warning: Route file '{filename}' is empty")
            return routes
        elif file_size > 100 * 1024 * 1024:  # 100MB
            print(f"Warning: Route file '{filename}' is very large ({file_size/1024/1024:.1f}MB)")

        with open(filename, "r", encoding="utf-8", errors="replace") as fh:
            try:
                lines = fh.readlines()
            except Exception as e:
                print(f"Error reading lines from '{filename}': {e}")
                return routes
                
        if not lines:
            print(f"Warning: No lines read from '{filename}'")
            return routes

        print(f"Processing {len(lines)} lines from '{filename}'...")

        # Enhanced state tracking with error recovery
        in_group = False
        group_mask = None
        variably_sub = False
        expected_routes_in_group = 0
        processed_routes_in_group = 0
        cur_proto_for_block = "Unknown"
        
        # Debug flag - set to False for production
        DEBUG_SUBNET_GROUPS = False
        parse_errors = 0
        routes_parsed = 0

        def log_debug(message):
            if DEBUG_SUBNET_GROUPS:
                print(f"DEBUG: {message}")

        def convert_dotted_mask_to_cidr(dotted_mask):
            """Convert dotted decimal mask to CIDR notation with error handling."""
            try:
                if not dotted_mask or not isinstance(dotted_mask, str):
                    return None
                octets = dotted_mask.split('.')
                if len(octets) != 4:
                    return None
                return sum(bin(int(octet)).count('1') for octet in octets if octet.isdigit())
            except (ValueError, AttributeError):
                return None

        i = 0
        while i < len(lines):
            try:
                raw = lines[i]
                line = raw.strip() if raw else ""

                # Skip empty lines and banners
                if not line or line.startswith(("Codes:", "Gateway of last resort")):
                    i += 1
                    continue

                # Subnet group detection with error handling
                if "subnetted" in line.lower():
                    try:
                        is_group, base_network, cidr_mask, is_variably, expected_count = detect_subnet_group(raw)
                        
                        if is_group:
                            log_debug(f"✓ MATCHED subnet group: {base_network}/{cidr_mask if cidr_mask else 'variable'}")
                            in_group = True
                            group_mask = cidr_mask if not is_variably else None
                            processed_routes_in_group = 0
                            variably_sub = is_variably
                            expected_routes_in_group = expected_count
                    except Exception as e:
                        log_debug(f"Error parsing subnet group line {i+1}: {e}")
                        parse_errors += 1
                    
                    i += 1
                    continue

                # Route line processing with error handling
                try:
                    proto_match = re.match(
                        r"^\s*([A-Za-z\*][A-Za-z0-9\*\+\-\s]*)\s+"
                        r"(\d{1,3}(?:\.\d{1,3}){3})",
                        line
                    )
                    
                    if proto_match:
                        text_proto = proto_match.group(1).strip()
                        dest_ip = proto_match.group(2)
                        
                        # Validate IP address
                        try:
                            ipaddress.ip_address(dest_ip)
                        except ValueError:
                            log_debug(f"Invalid IP address '{dest_ip}' on line {i+1}")
                            i += 1
                            continue

                        cur_proto_for_block = determine_protocol(line, text_proto)
                        rest = line[proto_match.end(2):]
                        subnet_str = None
                        
                        # Parse subnet mask with error handling
                        try:
                            # Look for explicit CIDR mask
                            cidr_match = re.match(r"/(\d{1,2})", rest)
                            if cidr_match:
                                explicit_cidr = int(cidr_match.group(1))
                                if 0 <= explicit_cidr <= 32:
                                    subnet_str = f"{dest_ip}/{explicit_cidr}"
                                else:
                                    log_debug(f"Invalid CIDR mask /{explicit_cidr} on line {i+1}")
                            
                            # Look for dotted decimal mask
                            elif not subnet_str:
                                dotted_match = re.match(r"\s+(\d{1,3}(?:\.\d{1,3}){3})", rest)
                                if dotted_match:
                                    dotted_mask = dotted_match.group(1)
                                    cidr_equivalent = convert_dotted_mask_to_cidr(dotted_mask)
                                    if cidr_equivalent is not None:
                                        subnet_str = f"{dest_ip}/{cidr_equivalent}"
                                    else:
                                        subnet_str = f"{dest_ip} {dotted_mask}"
                            
                            # Use group inheritance or default
                            if not subnet_str:
                                if in_group and processed_routes_in_group < expected_routes_in_group:
                                    if variably_sub:
                                        subnet_str = f"{dest_ip}/32"
                                    else:
                                        subnet_str = f"{dest_ip}/{group_mask}" if group_mask else f"{dest_ip}/32"
                                    processed_routes_in_group += 1
                                    
                                    if processed_routes_in_group >= expected_routes_in_group:
                                        in_group = False
                                        group_mask = None
                                        variably_sub = False
                                else:
                                    subnet_str = f"{dest_ip}/32"

                            # Normalize and store route
                            norm_subnet = normalize_subnet(subnet_str)
                            nhop, up = extract_path_attributes(line)
                            
                            if nhop != "N/A":
                                routes[norm_subnet].append((cur_proto_for_block, nhop, up))
                                routes_parsed += 1
                                
                        except Exception as e:
                            log_debug(f"Error processing route on line {i+1}: {e}")
                            parse_errors += 1

                except Exception as e:
                    log_debug(f"Error parsing line {i+1}: {e}")
                    parse_errors += 1

                i += 1
                
            except Exception as e:
                print(f"Critical error processing line {i+1} in '{filename}': {e}")
                parse_errors += 1
                i += 1
                continue

        print(f"✓ Route extraction completed: {routes_parsed} routes parsed, {parse_errors} errors")
        if parse_errors > 0:
            print(f"Warning: {parse_errors} parsing errors encountered. Check file format.")
            
        return routes
        
    except UnicodeDecodeError as e:
        print(f"Error: '{filename}' contains invalid characters: {e}")
        print("Try saving the file with UTF-8 encoding.")
        return routes
    except PermissionError:
        print(f"Error: Permission denied reading '{filename}'")
        return routes
    except MemoryError:
        print(f"Error: Not enough memory to process '{filename}'. File too large.")
        return routes
    except Exception as e:
        print(f"Error extracting routes from '{filename}': {type(e).__name__}: {e}")
        return routes

def safe_compare_and_output(routes1, routes2, output_file, file1_name, file2_name):
    """
    Wrapper for compare_and_output with comprehensive error handling.
    """
    try:
        # Validate inputs
        if not isinstance(routes1, dict) or not isinstance(routes2, dict):
            raise ValueError("Route data must be dictionaries")
            
        if not output_file or not isinstance(output_file, str):
            raise ValueError("Output file path must be a valid string")
            
        # Check if we can write to the output location
        output_dir = os.path.dirname(output_file) or '.'
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
                print(f"Created output directory: {output_dir}")
            except Exception as e:
                raise PermissionError(f"Cannot create output directory '{output_dir}': {e}")
                
        if not os.access(output_dir, os.W_OK):
            raise PermissionError(f"No write permission for directory '{output_dir}'")

        # Test write access by creating a temporary file
        temp_file = output_file + ".tmp"
        try:
            with open(temp_file, 'w') as f:
                f.write("test")
            os.remove(temp_file)
        except Exception as e:
            raise PermissionError(f"Cannot write to '{output_file}': {e}")

        print(f"Comparing {len(routes1)} routes from {file1_name} vs {len(routes2)} routes from {file2_name}")
        
        # Call the actual comparison function
        return compare_and_output(routes1, routes2, output_file, file1_name, file2_name)
        
    except MemoryError:
        print(f"Error: Not enough memory to compare route tables")
        print("Try comparing smaller route sets or increase system memory")
        return False
    except PermissionError as e:
        print(f"Permission Error: {e}")
        return False
    except ValueError as e:
        print(f"Input Error: {e}")
        return False
    except Exception as e:
        print(f"Comparison Error: {type(e).__name__}: {e}")
        return False

# Update your compare_device_outputs function to use this wrapper:
# Replace the line:
# compare_and_output(routes1, routes2, str(output_csv), "before", "after")
# With:
# if not safe_compare_and_output(routes1, routes2, str(output_csv), "before", "after"):
#     print(f"  ✗ Failed to generate comparison for {device_name}")
#     continue



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
    Format multipath route information with enhanced protocol tracking.
    Fixed to handle tuples properly.
    """
    if not paths:
        return "N/A", "N/A", "N/A"

    # Sort and deduplicate protocols while preserving order
    seen_protocols = []
    for p in paths:
        if p and len(p) >= 1 and p[0] is not None and p not in seen_protocols:
            # Ensure we're working with strings
            protocol = str(p) if p is not None else "Unknown"
            seen_protocols.append(protocol)
    
    protocol_str = ", ".join(seen_protocols) if seen_protocols else "N/A"

    # Sort and deduplicate next hops
    seen_nexthops = []
    for p in paths:
        if p and len(p) >= 2 and p[1] is not None and p[1] not in seen_nexthops:
            # Ensure we're working with strings
            nexthop = str(p[1]) if p[1] is not None else "N/A"
            seen_nexthops.append(nexthop)
    
    next_hop_ip_str = " | ".join(sorted(seen_nexthops)) if seen_nexthops else "N/A"

    # Sort and deduplicate uptimes
    seen_uptimes = []
    for p in paths:
        if p and len(p) >= 3 and p[2] is not None and p[2] not in seen_uptimes:
            # Ensure we're working with strings
            uptime = str(p[2]) if p[2] is not None else "N/A"
            seen_uptimes.append(uptime)
    
    uptime_str = " | ".join(sorted(seen_uptimes)) if seen_uptimes else "N/A"

    return protocol_str, next_hop_ip_str, uptime_str


def display_protocol_change_summary(output_file):
    """
    Display detailed summary of protocol changes found in the comparison.
    """
    try:
        protocol_changes = []
        with open(output_file, 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if "Protocol" in row.get('Status', '') and row.get('Change_Details', ''):
                    protocol_changes.append({
                        'subnet': row['Subnet'],
                        'before_protocol': row.get('before_Protocol', 'N/A'),
                        'after_protocol': row.get('after_Protocol', 'N/A'),
                        'change_details': row.get('Change_Details', ''),
                        'status': row.get('Status', '')
                    })
        
        if protocol_changes:
            print(f"\nProtocol Changes Detected ({len(protocol_changes)} subnets):")
            print("-" * 80)
            for change in protocol_changes[:10]:  # Show first 10
                print(f"Subnet: {change['subnet']}")
                print(f"  Before: {change['before_protocol']}")
                print(f"  After:  {change['after_protocol']}")
                print(f"  Details: {change['change_details']}")
                print()
            
            if len(protocol_changes) > 10:
                print(f"... and {len(protocol_changes) - 10} more protocol changes")
                print("Check the CSV file for complete details.")
        else:
            print("No protocol changes detected.")
            
    except Exception as e:
        print(f"Error reading protocol change summary: {e}")


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
    Enhanced with subnet coverage analysis (requiring covering route in BOTH before/after
    with identical next-hop IPs) and protocol change detection.
    """
    try:
        all_subnets = set(list(routes1.keys()) + list(routes2.keys()))
        sorted_subnets = sort_ip_networks(list(all_subnets))

        with open(output_file, 'w', newline='') as csvfile:
            fieldnames = ['Subnet',
                          f'{file1_name}_Protocol', f'{file1_name}_NextHop_IP', f'{file1_name}_Uptime',
                          f'{file2_name}_Protocol', f'{file2_name}_NextHop_IP', f'{file2_name}_Uptime',
                          'Status', 'Coverage_Analysis', 'Change_Details']
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
                change_details = ""

                if in_file1 and in_file2:
                    # Enhanced comparison for protocol changes
                    exact_paths1 = set(tuple(p) if isinstance(p, (list, tuple)) else p for p in paths_file1)
                    exact_paths2 = set(tuple(p) if isinstance(p, (list, tuple)) else p for p in paths_file2)
                    
                    if exact_paths1 == exact_paths2:
                        status = "Same"
                    else:
                        # Detailed analysis of what changed
                        protocol_changed = f1_protocol != f2_protocol
                        nexthop_changed = f1_nexthop_ip_str != f2_nexthop_ip_str
                        uptime_changed = f1_uptime_str != f2_uptime_str
                        
                        # Extract unique protocols for comparison - FIXED
                        protocols1 = set()
                        for p in paths_file1:
                            if p and len(p) >= 1 and p[0]:
                                protocols1.add(str(p))
                        
                        protocols2 = set()
                        for p in paths_file2:
                            if p and len(p) >= 1 and p:
                                protocols2.add(str(p))
                        
                        nexthops1 = set()
                        for p in paths_file1:
                            if p and len(p) >= 2 and p[1]:
                                nexthops1.add(str(p[1]))
                        
                        nexthops2 = set()
                        for p in paths_file2:
                            if p and len(p) >= 2 and p[1]:
                                nexthops2.add(str(p[1]))
                        
                        # Determine type of change
                        if protocol_changed:
                            status_parts.append("Protocol")
                            # Detailed protocol change analysis
                            added_protocols = protocols2 - protocols1
                            removed_protocols = protocols1 - protocols2
                            
                            change_detail_parts = []
                            if removed_protocols:
                                change_detail_parts.append(f"Removed: {', '.join(sorted(removed_protocols))}")
                            if added_protocols:
                                change_detail_parts.append(f"Added: {', '.join(sorted(added_protocols))}")
                            
                            # Check if it's a complete protocol change (all paths changed protocol)
                            if not protocols1.intersection(protocols2):
                                change_detail_parts.append("Complete protocol change")
                            elif protocols1.intersection(protocols2):
                                change_detail_parts.append("Partial protocol change")
                                
                            change_details = "; ".join(change_detail_parts)
                        
                        if nexthop_changed:
                            status_parts.append("NextHop_IP")
                            # Detailed next-hop change analysis
                            added_nexthops = nexthops2 - nexthops1
                            removed_nexthops = nexthops1 - nexthops2
                            
                            if not change_details:
                                change_details = ""
                            else:
                                change_details += " | "
                                
                            nexthop_detail_parts = []
                            if removed_nexthops:
                                nexthop_detail_parts.append(f"NH Removed: {', '.join(sorted(removed_nexthops))}")
                            if added_nexthops:
                                nexthop_detail_parts.append(f"NH Added: {', '.join(sorted(added_nexthops))}")
                                
                            change_details += "; ".join(nexthop_detail_parts)
                        
                        if uptime_changed:
                            status_parts.append("Uptime")
                        
                        # Check for path count changes
                        if len(paths_file1) != len(paths_file2):
                            status_parts.append("Path Count")
                            if not change_details:
                                change_details = ""
                            else:
                                change_details += " | "
                            change_details += f"Paths: {len(paths_file1)} -> {len(paths_file2)}"

                        if not status_parts:
                            status_parts.append("Path Attribute Combination")

                        status = "Different: " + ", ".join(status_parts)

                elif in_file1:  # Route only in file1 (before)
                    status = f"Missing in {file2_name}"
                    # Only consider covering routes valid if present in BOTH before and after with identical next-hop IPs
                    valid_cov, invalid_cov = find_valid_covering_routes_in_both(subnet, routes1, routes2)
                    if valid_cov:
                        formatted = []
                        for cov_subnet, before_info, after_info in valid_cov[:3]:
                            # FIXED: Extract protocol strings properly
                            before_protos = set()
                            for p in before_info:
                                if p and len(p) >= 1 and p[0]:
                                    before_protos.add(str(p))
                            
                            after_protos = set()
                            for p in after_info:
                                if p and len(p) >= 1 and p:
                                    after_protos.add(str(p))
                            
                            protos = sorted(list(before_protos | after_protos))
                            proto_str = ", ".join(protos) if protos else "Unknown"
                            formatted.append(f"{cov_subnet} ({proto_str})")
                        more = f" [+{len(valid_cov)-3} more]" if len(valid_cov) > 3 else ""
                        coverage_analysis = "Covered by (present in both, same next-hop): " + " | ".join(formatted) + more
                    else:
                        if invalid_cov:
                            reasons = []
                            for item in invalid_cov[:3]:
                                cov = item['covering_subnet']
                                if not (item['in_before'] and item['in_after']):
                                    where = []
                                    if not item['in_before']:
                                        where.append('before')
                                    if not item['in_after']:
                                        where.append('after')
                                    reasons.append(f"{cov} missing in {', '.join(where)}")
                                else:
                                    before_nh = [str(nh) for nh in item['before_nexthops']]
                                    after_nh = [str(nh) for nh in item['after_nexthops']]
                                    reasons.append(f"{cov} NH mismatch (before={before_nh}, after={after_nh})")
                            more = f" [+{len(invalid_cov)-3} more]" if len(invalid_cov) > 3 else ""
                            coverage_analysis = "Covering route found but NOT valid: " + " | ".join(reasons) + more
                        else:
                            coverage_analysis = "No covering route found in either file"

                else:  # Route only in file2 (after)
                    status = f"Missing in {file1_name}"
                    valid_cov, invalid_cov = find_valid_covering_routes_in_both(subnet, routes1, routes2)
                    if valid_cov:
                        formatted = []
                        for cov_subnet, before_info, after_info in valid_cov[:3]:
                            # FIXED: Extract protocol strings properly
                            before_protos = set()
                            for p in before_info:
                                if p and len(p) >= 1 and p[0]:
                                    before_protos.add(str(p))
                            
                            after_protos = set()
                            for p in after_info:
                                if p and len(p) >= 1 and p:
                                    after_protos.add(str(p))
                            
                            protos = sorted(list(before_protos | after_protos))
                            proto_str = ", ".join(protos) if protos else "Unknown"
                            formatted.append(f"{cov_subnet} ({proto_str})")
                        more = f" [+{len(valid_cov)-3} more]" if len(valid_cov) > 3 else ""
                        coverage_analysis = "Covered by (present in both, same next-hop): " + " | ".join(formatted) + more
                    else:
                        if invalid_cov:
                            reasons = []
                            for item in invalid_cov[:3]:
                                cov = item['covering_subnet']
                                if not (item['in_before'] and item['in_after']):
                                    where = []
                                    if not item['in_before']:
                                        where.append('before')
                                    if not item['in_after']:
                                        where.append('after')
                                    reasons.append(f"{cov} missing in {', '.join(where)}")
                                else:
                                    before_nh = [str(nh) for nh in item['before_nexthops']]
                                    after_nh = [str(nh) for nh in item['after_nexthops']]
                                    reasons.append(f"{cov} NH mismatch (before={before_nh}, after={after_nh})")
                            more = f" [+{len(invalid_cov)-3} more]" if len(invalid_cov) > 3 else ""
                            coverage_analysis = "Covering route found but NOT valid: " + " | ".join(reasons) + more
                        else:
                            coverage_analysis = "No covering route found in either file"

                row = {
                    'Subnet': subnet,
                    f'{file1_name}_Protocol': f1_protocol,
                    f'{file1_name}_NextHop_IP': f1_nexthop_ip_str,
                    f'{file1_name}_Uptime': f1_uptime_str,
                    f'{file2_name}_Protocol': f2_protocol,
                    f'{file2_name}_NextHop_IP': f2_nexthop_ip_str,
                    f'{file2_name}_Uptime': f2_uptime_str,
                    'Status': status,
                    'Coverage_Analysis': coverage_analysis,
                    'Change_Details': change_details
                }
                writer.writerow(row)

        print(f"\nComparison complete. Results saved to {output_file}")

        # Enhanced statistics with protocol change tracking
        diff_counts = defaultdict(int)
        protocol_change_count = 0
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
                change_detail = row_read.get('Change_Details', '')
                
                if s == "Same":
                    same_count += 1
                elif f"Missing in {file1_name}" in s:
                    missing_f1_count += 1
                    if coverage and "Covered by (present in both, same next-hop)" in coverage:
                        missing_f1_covered += 1
                elif f"Missing in {file2_name}" in s:
                    missing_f2_count += 1
                    if coverage and "Covered by (present in both, same next-hop)" in coverage:
                        missing_f2_covered += 1
                elif s.startswith("Different: "):
                    parts = s.replace("Different: ", "").split(', ')
                    for part in parts:
                        diff_counts[part.strip()] += 1
                    
                    # Count protocol changes specifically
                    if "Protocol" in s:
                        protocol_change_count += 1

        print(f"Total unique subnets processed: {len(all_subnets)}")
        print(f"Routes that are the Same: {same_count}")
        print(f"Routes with Protocol Changes: {protocol_change_count}")
        print(f"Routes found only in {file1_name} (Missing in {file2_name}): {missing_f2_count}")
        if missing_f2_count > 0:
            print(f"  - Missing routes with valid covering route: {missing_f2_covered}")
            print(f"  - Missing routes without valid covering route: {missing_f2_count - missing_f2_covered}")
        print(f"Routes found only in {file2_name} (Missing in {file1_name}): {missing_f1_count}")
        if missing_f1_count > 0:
            print(f"  - Missing routes with valid covering route: {missing_f1_covered}")
            print(f"  - Missing routes without valid covering route: {missing_f1_count - missing_f1_covered}")
        
        if diff_counts:
            print("Count of routes with specific differences:")
            for diff_type, count_val in sorted(diff_counts.items()):
                print(f"  - {diff_type}: {count_val}")

    except FileNotFoundError:
        print(f"Error: Output file {output_file} could not be written.")
        sys.exit(1)
    except Exception as e:
        print(f"Error during comparison or writing CSV {output_file}: {type(e).__name__} {e}")
        import traceback
        traceback.print_exc()
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
    Read device list from CSV file with comprehensive error handling.
    Expected formats:
      - With header: device|hostname|device_name[, command]
      - Without header: device[, command]
    Returns list of [device_name, command] rows.
    """
    devices = []
    
    # Input validation
    if not csv_file or not isinstance(csv_file, str):
        print("Error: CSV file path is invalid or empty.")
        sys.exit(1)

    if not os.path.exists(csv_file):
        print(f"Error: Input file '{csv_file}' not found.")
        print("Please ensure the file exists and the path is correct.")
        sys.exit(1)
        
    if not os.path.isfile(csv_file):
        print(f"Error: '{csv_file}' is not a regular file.")
        sys.exit(1)

    try:
        # Check file size and readability
        file_size = os.path.getsize(csv_file)
        if file_size == 0:
            print(f"Error: CSV file '{csv_file}' is empty.")
            sys.exit(1)
        elif file_size > 10 * 1024 * 1024:  # 10MB limit
            print(f"Warning: CSV file '{csv_file}' is quite large ({file_size/1024/1024:.1f}MB)")
            
        with open(csv_file, 'r', newline='', encoding='utf-8') as file:
            try:
                reader = csv.reader(file)
            except Exception as e:
                print(f"Error: Failed to parse CSV file '{csv_file}': {e}")
                sys.exit(1)

            row_count = 0
            first_row = None
            
            try:
                first_row = next(reader, None)
                row_count += 1
            except Exception as e:
                print(f"Error: Failed to read first row from '{csv_file}': {e}")
                sys.exit(1)
                
            if first_row is None:
                print(f"Error: CSV file '{csv_file}' appears to be empty.")
                sys.exit(1)

            # Determine if first row is header
            header_indicators = ['device', 'hostname', 'device_name', 'host', 'ip']
            first_row_clean = [str(c).strip().lower() for c in first_row if c is not None]
            is_header = any(indicator in ' '.join(first_row_clean) for indicator in header_indicators)

            def validate_and_normalize_row(row, line_num):
                """Validate and normalize a CSV row"""
                if not row:
                    return None, f"Row {line_num}: Empty row"
                    
                # Clean up the row
                cleaned_row = []
                for item in row:
                    if item is None:
                        cleaned_row.append('')
                    else:
                        cleaned_row.append(str(item).strip())
                
                # Extract device name (first non-empty column)
                device_name = ''
                for item in cleaned_row:
                    if item:
                        device_name = item
                        break
                        
                if not device_name:
                    return None, f"Row {line_num}: No device name found"
                    
                # Validate device name format
                if not re.match(r'^[a-zA-Z0-9\.\-_]+$', device_name):
                    return None, f"Row {line_num}: Invalid device name format '{device_name}'"
                    
                # Extract command (second column or default)
                command = cleaned_row[1] if len(cleaned_row) > 1 and cleaned_row[1] else 'show ip route'
                
                return [device_name, command], None

            # Process first row if it's not a header
            if not is_header:
                device_row, error = validate_and_normalize_row(first_row, 1)
                if device_row:
                    devices.append(device_row)
                elif error:
                    print(f"Warning: {error}")

            # Process remaining rows
            for row in reader:
                row_count += 1
                device_row, error = validate_and_normalize_row(row, row_count)
                if device_row:
                    devices.append(device_row)
                elif error:
                    print(f"Warning: {error}")

        if not devices:
            print(f"Error: No valid device entries found in '{csv_file}'.")
            print("Expected format: device_name[, command]")
            print("Example:")
            print("  router1.example.com, show ip route")
            print("  switch2.example.com")
            sys.exit(1)

        # Check for duplicate device names
        device_names = [d[0] for d in devices]
        duplicates = [name for name in set(device_names) if device_names.count(name) > 1]
        if duplicates:
            print(f"Warning: Duplicate device names found: {', '.join(duplicates)}")
            print("Only the first occurrence of each device will be processed.")
            seen = set()
            devices = [d for d in devices if not (d[0] in seen or seen.add(d))]

        print(f"Successfully loaded {len(devices)} devices from '{csv_file}'")
        return devices

    except UnicodeDecodeError as e:
        print(f"Error: '{csv_file}' contains invalid characters. Please save as UTF-8.")
        print(f"Details: {e}")
        sys.exit(1)
    except PermissionError:
        print(f"Error: Permission denied reading '{csv_file}'.")
        print("Please check file permissions.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading '{csv_file}': {type(e).__name__}: {e}")
        sys.exit(1)

def connect_to_device(device_name, command, username=None, password=None, device_type='cisco_ios', retries=2):
    """
    Connect to device with comprehensive error handling and retry logic.
    """
    if not NETMIKO_AVAILABLE:
        print(f"Error: netmiko library not available for connecting to {device_name}")
        print("Install with: pip install netmiko")
        return None
    
    # Input validation
    if not device_name or not isinstance(device_name, str):
        print("Error: Invalid device name provided")
        return None
    if not command or not isinstance(command, str):
        print(f"Error: Invalid command provided for {device_name}")
        return None

    # Prompt for credentials with error handling
    if not username:
        try:
            username = input(f"Username for {device_name}: ").strip()
            if not username:
                print("Error: Username cannot be empty")
                return None
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled by user")
            return None

    if not password:
        try:
            import getpass
            password = getpass.getpass(f"Password for {device_name}: ")
            if not password:
                print("Error: Password cannot be empty")
                return None
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled by user")
            return None

    device_params = {
        'device_type': device_type,
        'host': device_name,
        'username': username,
        'password': password,
        'timeout': 300,
        'session_timeout': 600,
        'conn_timeout': 60,
        'read_timeout_override': 300,
        'fast_cli': False,
        'global_delay_factor': 2,
    }

    last_error = None
    
    for attempt in range(1, retries + 1):
        try:
            attempt_msg = f" (attempt {attempt}/{retries})" if retries > 1 else ""
            print(f"Connecting to {device_name}{attempt_msg}...")
            
            with ConnectHandler(**device_params) as connection:
                print(f"✓ Connected to {device_name}")
                
                try:
                    # Clear buffer
                    connection.clear_buffer()
                except Exception as e:
                    print(f"Warning: Could not clear buffer on {device_name}: {e}")

                print(f"Executing command: {command}")
                
                try:
                    output = connection.send_command(
                        command,
                        expect_string=r'#',
                        delay_factor=4,
                        max_loops=2000,
                        strip_prompt=False,
                        strip_command=False,
                        read_timeout=300,
                        cmd_verify=False
                    )
                    
                    # Wait for any remaining output
                    import time
                    time.sleep(2)
                    
                    try:
                        additional_output = connection.read_channel()
                        if additional_output and additional_output.strip():
                            output += additional_output
                    except Exception:
                        pass  # Additional output not critical

                    if output:
                        print(f"✓ Command executed successfully on {device_name} ({len(output)} characters)")
                        return output
                    else:
                        print(f"Warning: No output received from {device_name}")
                        return ""
                        
                except Exception as e:
                    print(f"✗ Command execution failed on {device_name}: {e}")
                    last_error = f"Command execution error: {e}"
                    
        except KeyboardInterrupt:
            print(f"\n✗ Connection to {device_name} cancelled by user")
            return None
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Categorize common errors
            if 'authentication' in error_msg or 'auth' in error_msg:
                print(f"✗ Authentication failed for {device_name}")
                print("  Please check username and password")
                return None  # Don't retry auth failures
                
            elif 'timeout' in error_msg or 'timed out' in error_msg:
                print(f"✗ Connection timeout to {device_name}: {e}")
                last_error = f"Connection timeout: {e}"
                
            elif 'unreachable' in error_msg or 'no route' in error_msg:
                print(f"✗ Network unreachable to {device_name}: {e}")
                last_error = f"Network unreachable: {e}"
                
            elif 'refused' in error_msg or 'connection refused' in error_msg:
                print(f"✗ Connection refused by {device_name}: {e}")
                last_error = f"Connection refused: {e}"
                
            elif 'name resolution' in error_msg or 'getaddrinfo' in error_msg:
                print(f"✗ Cannot resolve hostname {device_name}: {e}")
                return None  # Don't retry DNS failures
                
            else:
                print(f"✗ Connection failed to {device_name}: {e}")
                last_error = f"Connection error: {e}"

        # Wait before retry
        if attempt < retries:
            retry_delay = min(5, attempt * 2)  # Progressive delay: 2s, 4s, etc.
            print(f"Waiting {retry_delay}s before retry...")
            import time
            time.sleep(retry_delay)

    print(f"✗ Failed to connect to {device_name} after {retries} attempts")
    if last_error:
        print(f"  Last error: {last_error}")
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
    Main function with comprehensive error handling.
    """
    print("Cisco Route Comparison Script - Enhanced Version")
    print("=" * 60)
    
    # Check dependencies
    if not NETMIKO_AVAILABLE:
        print("⚠ Warning: netmiko library not available")
        print("  Device connection features will not work")
        print("  Install with: pip install netmiko")
        print()

    try:
        while True:
            try:
                choice = display_menu()
                
                if choice == 1:
                    print("\n--- CAPTURING BEFORE STATE ---")
                    try:
                        input_file = input("Enter CSV file path (default: input.csv): ").strip()
                        if not input_file:
                            input_file = "input.csv"
                        
                        if not os.path.exists(input_file):
                            print(f"✗ Error: Input file '{input_file}' not found")
                            input("Press Enter to continue...")
                            continue
                        
                        username = input("Username for device connections (optional): ").strip() or None
                        
                        capture_device_outputs(1, input_file, username, None)
                        print("\n✓ BEFORE state capture completed!")
                        
                    except KeyboardInterrupt:
                        print("\n✗ Capture cancelled by user")
                    except Exception as e:
                        print(f"\n✗ Error during BEFORE state capture: {type(e).__name__}: {e}")
                    
                    input("Press Enter to return to menu...")
                
                elif choice == 2:
                    print("\n--- CAPTURING AFTER STATE ---")
                    try:
                        input_file = input("Enter CSV file path (default: input.csv): ").strip()
                        if not input_file:
                            input_file = "input.csv"
                        
                        if not os.path.exists(input_file):
                            print(f"✗ Error: Input file '{input_file}' not found")
                            input("Press Enter to continue...")
                            continue
                        
                        username = input("Username for device connections (optional): ").strip() or None
                        
                        capture_device_outputs(2, input_file, username, None)
                        print("\n✓ AFTER state capture completed!")
                        
                    except KeyboardInterrupt:
                        print("\n✗ Capture cancelled by user")
                    except Exception as e:
                        print(f"\n✗ Error during AFTER state capture: {type(e).__name__}: {e}")
                    
                    input("Press Enter to return to menu...")
                
                elif choice == 3:
                    print("\n--- COMPARING BEFORE/AFTER STATES ---")
                    try:
                        compare_device_outputs()
                        print("\n✓ Comparison completed!")
                    except KeyboardInterrupt:
                        print("\n✗ Comparison cancelled by user")
                    except Exception as e:
                        print(f"\n✗ Error during comparison: {type(e).__name__}: {e}")
                        import traceback
                        print("Full error details:")
                        traceback.print_exc()
                    
                    input("Press Enter to return to menu...")
                
                elif choice == 4:
                    print("\nThank you for using Cisco Route Comparison Tool!")
                    print("Goodbye!")
                    break
                    
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user")
                confirm = input("Do you want to exit the program? (y/n): ").strip().lower()
                if confirm in ['y', 'yes']:
                    break
            except Exception as e:
                print(f"\n✗ Unexpected error in menu system: {type(e).__name__}: {e}")
                input("Press Enter to continue...")

    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user. Goodbye!")
    except Exception as e:
        print(f"\n✗ Critical error: {type(e).__name__}: {e}")
        print("Program will exit.")
        sys.exit(1)


if __name__ == "__main__":
    main()
