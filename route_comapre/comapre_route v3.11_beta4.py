#!/usr/bin/env python3

## update route cover logic

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


"""
    v3.11 beta3
    in  capture_device_outputs
    IMPROVEMENTS:
    - Uses 'cisco_nxos' for correct prompt/pager handling on Nexus devices.
    - Removes loose expect_string matching to prevent premature output truncation.
    - Enables cmd_verify to ensure the session stays synchronized with the device.
    - Removed manual time.sleep() and read_channel() for a cleaner, more reliable wait mechanism.
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
from typing import List
from typing import Union, Iterable
from typing import Dict, Tuple, Set, Optional
from typing import Dict, List, Tuple, Set


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

def detect_vrf_header(line: str) -> Tuple[bool, str]:
    """
    NX-OS VRF header detector.
    Matches e.g.:
      IP Route Table for VRF "RED"
      IP Route Table for VRF BLUE
      vrf context red
    """
    patterns = [
        r'ip\s+route\s+table\s+for\s+vrf\s+"([^"]+)"',
        r'ip\s+route\s+table\s+for\s+vrf\s+(\S+)',
        r'vrf\s+context\s+(\S+)',
    ]
    for pat in patterns:
        m = re.search(pat, line, re.IGNORECASE)
        if m:
            vrf = m.group(1).strip().lower()          # normalise case
            if vrf in {"global", "default"}:
                vrf = "default"
            return True, vrf
    return False, None

def parse_nxos_route_line(line: str) -> Tuple[str, Optional[str], str,
                                              Optional[str], str, str]:
    """
    Return:
      (type,   network, protocol, next-hop, uptime, interface)
      type = 'main_route' | 'path' | 'unknown'
    """
    line = line.strip()

    # ───── main route (prefix) ──────────────────────────────────────────────
    m = re.match(r'^(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}),\s*ubest/mbest:\s*\d+/\d+(?:,\s*(.+))?$',
                 line, re.I)
    if m:
        net, flags = m.group(1), (m.group(2) or "")
        proto = "Connected" if "attached" in flags.lower() else "Unknown"
        return "main_route", net, proto, None, "N/A", ""

    # ───── child path ( *via … ) – three flavours ──────────────────────────
    patterns = [
        # *via 10.0.0.1, Eth1/1, [1/0], 01:23:45, eigrp-1, internal
        r'^\*\s*via\s+(\d{1,3}(?:\.\d{1,3}){3}),\s*([^,\[]+),\s*\[(\d+)/([^\]]+)\],\s*([^,]+),\s*(.+)$',
        # *via 10.0.0.1, [110/20], 00:00:05, ospf-1, intra
        r'^\*\s*via\s+(\d{1,3}(?:\.\d{1,3}){3}),\s*\[(\d+)/([^\]]+)\],\s*([^,]+),\s*(.+)$',
        # *via 10.0.0.1,  static           (rare truncated form)
        r'^\*\s*via\s+(\d{1,3}(?:\.\d{1,3}){3}),\s*(\S+)$',
    ]
    for idx, pat in enumerate(patterns):
        m = re.match(pat, line, re.I)
        if m:
            if idx == 0:
                ip, intf, ad, _, up, info = m.groups()
            elif idx == 1:
                ip, ad, _, up, info = m.groups()
                intf = ""
            else:
                ip, info = m.groups()
                ad, up, intf = 1, "N/A", ""
            proto = determine_nxos_protocol(int(ad), info)
            return "path", None, proto, ip, up, intf

    # ───── directly-connected child without “via” ───────────────────────────
    m = re.match(r'^\*\s*(directly\s+connected|attached)(?:,\s*(.+))?$', line, re.I)
    if m:
        intf = m.group(2).strip() if m.group(2) else ""
        return "path", None, "Connected", "Connected", "N/A", intf

    return "unknown", None, "", None, "", ""

def determine_nxos_protocol(ad: int, info: str) -> str:
    info = (info or "").lower()

    # protocol with instance number
    for prefix, name in [('ospf-', 'OSPF'), ('bgp-', 'BGP'),
                         ('eigrp-', 'EIGRP'), ('isis-', 'IS-IS'),
                         ('rip-', 'RIP')]:
        if prefix in info:
            inst = re.search(rf'{prefix}(\\d+)', info)
            return f"{name} ({prefix}{inst.group(1)})" if inst else name

    if "static" in info:
        return "Static"
    if any(k in info for k in ["direct", "attached", "am"]):
        return "Connected"
    if "local" in info:
        return "Local"

    # fall back to admin-distance table
    return ADMINISTRATIVE_DISTANCES.get(ad, f"Unknown (AD:{ad})")


# ---------------------------------------------------------------------------
# UPDATED extract_routes   (IOS + NX-OS, multi-VRF, multipath aware)
# ---------------------------------------------------------------------------
from collections import defaultdict
from pathlib import Path
from typing import Union, Iterable, List
import ipaddress, re

def extract_routes(source: Union[str, Path, Iterable[str]]):
    """
    Return { "prefix[/len][@vrf]" : [(protocol, next-hop, uptime), …] }

    • Auto-detects IOS vs NX-OS.
    • Handles “show ip route vrf all | no-more” with unlimited VRFs.
    • Normalises VRF names to lower-case (“RED” == “red”).
    • Preserves multipath information (all protocols / next-hops / uptimes).
    """
    routes = defaultdict(list)

    # -------------------------------------------------------------------- #
    # 1.  load text lines                                                  #
    # -------------------------------------------------------------------- #
    if isinstance(source, (str, Path)):
        try:
            lines = Path(source).read_text(encoding="utf-8",
                                           errors="ignore").splitlines()
        except FileNotFoundError:
            print(f"ERROR: file {source} not found")
            return routes
    else:
        lines = list(source)

    # -------------------------------------------------------------------- #
    # 2.  state variables                                                  #
    # -------------------------------------------------------------------- #
    current_vrf = "default"            # always lower-case
    is_nxos = False
    current_main_route = None          # only for NX-OS parsing

    # -------------------------------------------------------------------- #
    # 3.  helpers                                                          #
    # -------------------------------------------------------------------- #
    ADMINISTRATIVE_DISTANCES = {       # abridged
        0: "Connected", 1: "Static", 20: "eBGP", 110: "OSPF", 115: "IS-IS",
        120: "RIP", 200: "iBGP"
    }

    def detect_vrf_header(line: str):
        pats = [
            r'ip\s+route\s+table\s+for\s+vrf\s+"([^"]+)"',
            r'ip\s+route\s+table\s+for\s+vrf\s+(\S+)',
            r'vrf\s+context\s+(\S+)',
        ]
        for p in pats:
            m = re.search(p, line, re.I)
            if m:
                name = m.group(1).strip().lower()
                return True, "default" if name in {"global", "default"} else name
        return False, None

    def determine_nxos_protocol(ad: int, info: str) -> str:
        info = (info or "").lower()
        for pre, n in [('ospf-', 'OSPF'), ('bgp-', 'BGP'),
                       ('eigrp-', 'EIGRP'), ('isis-', 'IS-IS'),
                       ('rip-', 'RIP')]:
            if pre in info:
                m = re.search(rf'{pre}(\d+)', info)
                return f"{n} ({pre}{m.group(1)})" if m else n
        if "static" in info:
            return "Static"
        if any(k in info for k in ["direct", "attached", "am"]):
            return "Connected"
        if "local" in info:
            return "Local"
        return ADMINISTRATIVE_DISTANCES.get(ad, f"Unknown (AD:{ad})")

    def parse_nxos_route_line(line: str):
        line = line.strip()

        # main route line
        m = re.match(r'^(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}),\s*ubest/mbest:\s*\d+/\d+(?:,\s*(.+))?$',
                     line, re.I)
        if m:
            flags = (m.group(2) or "").lower()
            proto = "Connected" if "attached" in flags else "Unknown"
            return "main_route", m.group(1), proto, None, "N/A", ""

        # path lines (three flavours)
        pats = [
            r'^\*\s*via\s+(\d{1,3}(?:\.\d{1,3}){3}),\s*([^,\[]+),\s*\[(\d+)/[^\]]+\],\s*([^,]+),\s*(.+)$',
            r'^\*\s*via\s+(\d{1,3}(?:\.\d{1,3}){3}),\s*\[(\d+)/[^\]]+\],\s*([^,]+),\s*(.+)$',
            r'^\*\s*via\s+(\d{1,3}(?:\.\d{1,3}){3})(?:,\s*(\S+))?$',
        ]
        for i, p in enumerate(pats):
            m = re.match(p, line, re.I)
            if m:
                if i == 0:
                    ip, intf, ad, up, info = m.groups()
                elif i == 1:
                    ip, ad, up, info = m.groups(); intf = ""
                else:
                    ip, info = m.groups(); ad, up, intf = 1, "N/A", ""
                proto = determine_nxos_protocol(int(ad), info)
                return "path", None, proto, ip, up.strip(), intf

        # directly connected path without "via"
        m = re.match(r'^\*\s*(directly\s+connected|attached)(?:,\s*(.+))?$', line, re.I)
        if m:
            intf = m.group(2).strip() if m.group(2) else ""
            return "path", None, "Connected", "Connected", "N/A", intf

        return "unknown", None, "", None, "", ""

    def normalize_subnet(s: str):
        try:
            return str(ipaddress.ip_network(s, strict=False))
        except Exception:
            return s

    # -------------------------------------------------------------------- #
    # 4.  main loop                                                        #
    # -------------------------------------------------------------------- #
    for raw in lines:
        txt = raw.strip()

        # ignore banners / legends
        if not txt or txt.startswith(("Codes:", "Gateway of last resort",
                                      "'*' denotes", "'**' denotes", "'[x/y]'")):
            continue

        # VRF header?
        is_vrf, vrf = detect_vrf_header(txt)
        if is_vrf:
            current_vrf = vrf
            continue

        # detect NX-OS once
        if "ubest/mbest:" in txt or "*via" in txt:
            is_nxos = True

        # ───────── NX-OS parsing ─────────────────────────────────────────
        if is_nxos:
            kind, net, proto, nhop, up, intf = parse_nxos_route_line(txt)

            if kind == "main_route":
                current_main_route = net
                if proto == "Connected":
                    key = f"{net}@{current_vrf}" if current_vrf != "default" else net
                    routes[key].append((proto, "Connected", up))

            elif kind == "path" and current_main_route:
                key = f"{current_main_route}@{current_vrf}" if current_vrf != "default" else current_main_route
                routes[key].append((proto, nhop, up))

            continue    # skip IOS parsing for this line

        # ───────── IOS parsing (existing logic unchanged) ───────────────
        m = re.match(r"^\s*([A-Za-z\*][A-Za-z0-9\*\+\-\s]*)\s+(\d{1,3}(?:\.\d{1,3}){3})", txt)
        if not m:
            continue
        text_proto, ip_part = m.groups()
        cidr = "/32"
        rest = txt[m.end(2):]
        c = re.match(r"/(\d{1,2})", rest)
        if c:
            cidr = f"/{c.group(1)}"
        key = normalize_subnet(f"{ip_part}{cidr}")
        if current_vrf != "default":
            key = f"{key}@{current_vrf}"
        routes[key].append((text_proto.strip(), *("N/A",)*2))

    return routes


def detect_vrf_header(line):
    """
    Detect VRF header lines in NX-OS output.
    Returns: (is_vrf_header, vrf_name)
    """
    # Enhanced patterns for VRF detection
    vrf_patterns = [
        # Standard pattern: IP Route Table for VRF "vrf_name"
        r'IP\s+Route\s+Table\s+for\s+VRF\s+"([^"]+)"',
        # Alternative pattern without quotes
        r'IP\s+Route\s+Table\s+for\s+VRF\s+(\w+)',
        # Context switch pattern
        r'vrf\s+context\s+(\w+)',
    ]
    
    for pattern in vrf_patterns:
        vrf_match = re.search(pattern, line, re.IGNORECASE)
        if vrf_match:
            vrf_name = vrf_match.group(1).strip()
            # Handle default VRF variations
            if vrf_name.lower() in ['default', 'global']:
                vrf_name = 'default'
            return True, vrf_name
    
    return False, None



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
    """
    if not paths:
        return "N/A", "N/A", "N/A"

    # Sort and deduplicate protocols while preserving order
    seen_protocols = []
    for p in paths:
        if p and p[0] is not None and p[0] not in seen_protocols:
            seen_protocols.append(p[0])
    
    protocol_str = ", ".join(seen_protocols) if seen_protocols else "N/A"

    # Sort and deduplicate next hops
    seen_nexthops = []
    for p in paths:
        if p and p[1] is not None and p[1] not in seen_nexthops:
            seen_nexthops.append(p[1])
    
    next_hop_ip_str = " | ".join(sorted(seen_nexthops)) if seen_nexthops else "N/A"

    # Sort and deduplicate uptimes
    seen_uptimes = []
    for p in paths:
        if p and len(p) > 2 and p[2] is not None and p[2] not in seen_uptimes:
            seen_uptimes.append(p[2])
    
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



# Coverage analysis helper functions for enhanced route comparison
from typing import Dict, List, Tuple, Set

def _nexthops(path_list: List[Tuple]) -> Set[str]:
    """Return a set of normalized next-hops (ignores Connected/Local/N/A)."""
    return {p[1] for p in path_list
            if p and p[1] not in {"Connected", "Local", "N/A"}}

def _best_covering(missing: str,
                   routes: Dict[str, List]) -> Tuple[Optional[str], List]:
    """
    Return the *most specific* covering subnet and its path list
    or (None, []) if nothing covers the missing prefix.
    """
    cov = find_covering_routes(missing, routes)
    return cov[0] if cov else (None, [])


def evaluate_coverage(missing_subnet: str,
                      vrf_routes_before: Dict[str, List],
                      vrf_routes_after: Dict[str, List]) -> Tuple[bool, str]:
    """
    Decide if missing_subnet is really covered.
    Returns (is_covered, explanation).
    """
    cov_b_pref, cov_b_paths = _best_covering(missing_subnet, vrf_routes_before)
    cov_a_pref, cov_a_paths = _best_covering(missing_subnet, vrf_routes_after)

    # Nothing covers at all
    if not cov_b_pref and not cov_a_pref:
        return False, "No covering route found"

    # Covering only exists on one side
    if cov_b_pref and not cov_a_pref:
        return False, "Covering route only in before"
    if cov_a_pref and not cov_b_pref:
        return False, "Covering route only in after"

    # Same prefix must be the covering route on both sides
    if cov_b_pref != cov_a_pref:
        return False, "Different covering prefixes"

    # Compare next-hop sets
    if _nexthops(cov_b_paths) == _nexthops(cov_a_paths):
        # Covered – return short summary
        proto = ", ".join(sorted({p[0] for p in cov_b_paths if p and p}))
        return True, f"Covered by {cov_b_pref} ({proto})"
    else:
        return False, "Covering route next-hop mismatch"



def compare_and_output(routes1, routes2, output_file, file1_name, file2_name):
    """
    Compare routes from two files and output the differences to a CSV file.
    Enhanced with VRF support, subnet coverage analysis and protocol change detection.
    """
    try:
        all_subnets = set(list(routes1.keys()) + list(routes2.keys()))
        
        # Separate VRF and non-VRF routes for better sorting
        vrf_subnets = []
        regular_subnets = []
        
        for subnet in all_subnets:
            if '@' in subnet:
                vrf_subnets.append(subnet)
            else:
                regular_subnets.append(subnet)
        
        # Sort each group separately
        sorted_regular = sort_ip_networks(regular_subnets)
        sorted_vrf = sorted(vrf_subnets, key=lambda x: (x.split('@')[1], x.split('@')))
        
        # Combine: regular routes first, then VRF routes grouped by VRF
        sorted_subnets = sorted_regular + sorted_vrf

        with open(output_file, 'w', newline='') as csvfile:
            fieldnames = ['VRF', 'Subnet',
                          f'{file1_name}_Protocol', f'{file1_name}_NextHop_IP', f'{file1_name}_Uptime',
                          f'{file2_name}_Protocol', f'{file2_name}_NextHop_IP', f'{file2_name}_Uptime',
                          'Status', 'Coverage_Analysis', 'Change_Details']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for subnet in sorted_subnets:
                # Extract VRF and actual subnet
                if '@' in subnet:
                    actual_subnet, vrf_name = subnet.split('@', 1)
                else:
                    actual_subnet = subnet
                    vrf_name = "default"
                
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
                    exact_paths1 = set(paths_file1)
                    exact_paths2 = set(paths_file2)
                    
                    if exact_paths1 == exact_paths2:
                        status = "Same"
                    else:
                        # [Rest of comparison logic remains the same...]
                        # Detailed analysis of what changed
                        protocol_changed = f1_protocol != f2_protocol
                        nexthop_changed = f1_nexthop_ip_str != f2_nexthop_ip_str
                        uptime_changed = f1_uptime_str != f2_uptime_str
                        
                        # Extract unique protocols for comparison
                        protocols1 = set(p[0] for p in paths_file1 if p and p)
                        protocols2 = set(p for p in paths_file2 if p and p)
                        nexthops1 = set(p[1] for p in paths_file1 if p and p[1])
                        nexthops2 = set(p[1] for p in paths_file2 if p and p[1])
                        
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

                # elif in_file1:  # Route only in file1
                #     status = f"Missing in {file2_name}"
                #     # Check for covering routes in file2 (within same VRF)
                #     same_vrf_routes2 = {k: v for k, v in routes2.items() if k.endswith(f"@{vrf_name}") or (vrf_name == "default" and '@' not in k)}
                #     covering_routes = find_covering_routes(actual_subnet, same_vrf_routes2)
                #     if covering_routes:
                #         coverage_analysis = f"Covered by: {format_covering_routes(covering_routes)}"
                #     else:
                #         coverage_analysis = "No covering route found"
                        
                # else:  # Route only in file2
                #     status = f"Missing in {file1_name}"
                #     # Check for covering routes in file1 (within same VRF)
                #     same_vrf_routes1 = {k: v for k, v in routes1.items() if k.endswith(f"@{vrf_name}") or (vrf_name == "default" and '@' not in k)}
                #     covering_routes = find_covering_routes(actual_subnet, same_vrf_routes1)
                #     if covering_routes:
                #         coverage_analysis = f"Covered by: {format_covering_routes(covering_routes)}"
                #     else:
                #         coverage_analysis = "No covering route found"
                # elif in_file1:          # present only in BEFORE
                #     status = f"Missing in {file2_name}"
                #     covered, explanation = evaluate_coverage(
                #         actual_subnet,
                #         {k: v for k, v in routes1.items()
                #         if k.endswith(f'@{vrf_name}') or (vrf_name == "default" and '@' not in k)},
                #         {k: v for k, v in routes2.items()
                #         if k.endswith(f'@{vrf_name}') or (vrf_name == "default" and '@' not in k)}
                #     )
                #     coverage_analysis = explanation if covered else explanation

                # else:                    # present only in AFTER
                #     status = f"Missing in {file1_name}"
                #     covered, explanation = evaluate_coverage(
                #         actual_subnet,
                #         {k: v for k, v in routes1.items()
                #         if k.endswith(f'@{vrf_name}') or (vrf_name == "default" and '@' not in k)},
                #         {k: v for k, v in routes2.items()
                #         if k.endswith(f'@{vrf_name}') or (vrf_name == "default" and '@' not in k)}
                #     )
                #     coverage_analysis = explanation if covered else explanation
                elif in_file1:          # present only in BEFORE
                    status = f"Missing in {file2_name}"
                    covered, explanation = evaluate_coverage(
                        actual_subnet,
                        {k: v for k, v in routes1.items()
                        if k.endswith(f'@{vrf_name}') or (vrf_name == "default" and '@' not in k)},
                        {k: v for k, v in routes2.items()
                        if k.endswith(f'@{vrf_name}') or (vrf_name == "default" and '@' not in k)}
                    )
                    coverage_analysis = explanation
                else:                    # present only in AFTER
                    status = f"Missing in {file1_name}"
                    covered, explanation = evaluate_coverage(
                        actual_subnet,
                        {k: v for k, v in routes1.items()
                        if k.endswith(f'@{vrf_name}') or (vrf_name == "default" and '@' not in k)},
                        {k: v for k, v in routes2.items()
                        if k.endswith(f'@{vrf_name}') or (vrf_name == "default" and '@' not in k)}
                    )
                    coverage_analysis = explanation

                row = {
                    'VRF': vrf_name,
                    'Subnet': actual_subnet,
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

        # Enhanced statistics with VRF tracking
        vrf_stats = defaultdict(lambda: {'same': 0, 'different': 0, 'missing_1': 0, 'missing_2': 0})
        
        with open(output_file, 'r', newline='') as csvfile_read:
            reader = csv.DictReader(csvfile_read)
            for row_read in reader:
                vrf = row_read.get('VRF', 'default')
                status = row_read['Status']
                
                if status == "Same":
                    vrf_stats[vrf]['same'] += 1
                elif f"Missing in {file1_name}" in status:
                    vrf_stats[vrf]['missing_1'] += 1
                elif f"Missing in {file2_name}" in status:
                    vrf_stats[vrf]['missing_2'] += 1
                elif status.startswith("Different"):
                    vrf_stats[vrf]['different'] += 1

        print(f"Total unique subnets processed: {len(all_subnets)}")
        
        # Print statistics by VRF
        for vrf_name in sorted(vrf_stats.keys()):
            stats = vrf_stats[vrf_name]
            total_routes = sum(stats.values())
            print(f"\nVRF '{vrf_name}' ({total_routes} routes):")
            print(f"  Same routes: {stats['same']}")
            print(f"  Different routes: {stats['different']}")
            print(f"  Missing in {file1_name}: {stats['missing_1']}")
            print(f"  Missing in {file2_name}: {stats['missing_2']}")

    except FileNotFoundError:
        print(f"Error: Output file {output_file} could not be written.")
        sys.exit(1)
    except Exception as e:
        print(f"Error during comparison or writing CSV {output_file}: {type(e).__name__} {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# REPLACEMENT 3 : create_folder_structure
# (only the very last two lines change to pre-create <folder>/commands)
# ---------------------------------------------------------------------------
def create_folder_structure(folder_name):
    """
    Create main folder and a ‘commands’ sub-folder, backing up any existing
    files in the main folder (excluding existing backups).
    """
    folder_path = Path(folder_name)
    backup_path = folder_path / "backup"

    if folder_path.exists():
        existing_files = [f for f in folder_path.iterdir()
                          if f.is_file() and f.parent == folder_path]
        if existing_files:
            print(f"Moving {len(existing_files)} existing files to backup …")
            backup_path.mkdir(exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = backup_path / f"backup_{ts}"
            dest.mkdir()
            for f in existing_files:
                shutil.move(str(f), str(dest / f.name))
            print(f"Existing files moved to {dest}")
    else:
        folder_path.mkdir(parents=True)

    # ALWAYS ensure the sub-folder exists
    (folder_path / "commands").mkdir(exist_ok=True)
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

# ---------------------------------------------------------------------------
# REPLACEMENT 1 : save_device_output
# ---------------------------------------------------------------------------
def save_device_output(device_name, command, output, folder_path):
    """
    Save a single-command output under <folder>/commands/.

    A filesystem-safe tag derived from the command is inserted in the filename
    so multiple commands never overwrite each other.
    """
    import datetime, re
    # Ensure subfolder <folder>/commands exists
    commands_path = folder_path / "commands"
    commands_path.mkdir(exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_cmd = re.sub(r"[^A-Za-z0-9._-]+", "_", command).strip("_")[:50] or "cmd"
    filename = f"{device_name}_{safe_cmd}_{timestamp}.txt"
    filepath = commands_path / filename

    try:
        line_count = len(output.splitlines()) if output else 0
        char_count = len(output) if output else 0

        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(f"Device: {device_name}\n")
            fh.write(f"Command: {command}\n")
            fh.write(f"Timestamp: {timestamp}\n")
            fh.write(f"Output Statistics: {line_count} lines, {char_count} characters\n")
            fh.write("=" * 80 + "\n")
            fh.write(output if output else "[NO OUTPUT RECEIVED]\n")
            fh.write("\n" + "=" * 80 + "\n")
            fh.write("Capture completed at: "
                     f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        print(f"  ↳ saved to {filepath.name} ({line_count} lines)")
        return filepath

    except Exception as exc:
        print(f"Error saving output for {device_name}: {exc}")
        return None

# ---------------------------------------------------------------------------
# CREDENTIAL CACHE (prompt once, reuse forever)
# ---------------------------------------------------------------------------
_CACHED_USERNAME = None
_CACHED_PASSWORD = None

def get_credentials():
    """Prompt once per program run, then reuse cached credentials."""
    global _CACHED_USERNAME, _CACHED_PASSWORD
    if _CACHED_USERNAME and _CACHED_PASSWORD:
        return _CACHED_USERNAME, _CACHED_PASSWORD

    _CACHED_USERNAME = input("Username for device connections: ")
    import getpass
    _CACHED_PASSWORD = getpass.getpass("Password: ")
    return _CACHED_USERNAME, _CACHED_PASSWORD


# ---------------------------------------------------------------------------
# REPLACEMENT 2 : capture_device_outputs
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# REPLACEMENT : capture_device_outputs
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# NEW capture_device_outputs : single netmiko session per device
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# NEW capture_device_outputs – one SSH session per device
# ---------------------------------------------------------------------------

def capture_device_outputs(mode: int, input_csv: str):
    """
    Mode 1 -> "before" • Mode 2 -> "after"
    
    Improvements:
    - Uses 'cisco_nxos' for correct prompt/pager handling.
    - Removes loose expect_string matching (fixes early termination).
    - Enables cmd_verify to ensure command echo before reading.
    """
    import datetime, re
    # Patterns for housekeeping commands to skip saving
    _IGNORE_PATTERNS = [
        r"ter\s+le\s+0$",  r"terminal\s+length\s+0$",
        r"ter\s+page\s+0$",  r"terminal\s+page\s+0$",
    ]
    _IGNORE_REGEX = re.compile("|".join(_IGNORE_PATTERNS), re.IGNORECASE)
    
    def _skip_individual(cmd: str) -> bool:
        return bool(_IGNORE_REGEX.match(cmd.strip()))

    folder_name = "before" if mode == 1 else "after"
    folder_path = create_folder_structure(folder_name)
    devices = read_device_list(input_csv)
    if not devices:
        print("No devices found in input file.")
        return

    username, password = get_credentials()
    ok = warn = fail = 0
    print(f"\nCapturing from {len(devices)} devices ...\n")

    for idx_dev, dev in enumerate(devices, 1):
        device_name = dev[0]
        raw_field = dev[1] if len(dev) > 1 else ""
        cmds = [c.strip() for c in re.split(r"\r?\n", raw_field) if c.strip()] or ["show ip route"]
        print(f"[{idx_dev}/{len(devices)}] {device_name}: {len(cmds)} command(s)")

        if not NETMIKO_AVAILABLE:
            print("   x Netmiko not installed - skipping device")
            fail += len(cmds)
            continue

        # CHANGED: Use 'cisco_nxos' instead of 'cisco_ios'
        params = {
            'device_type': 'cisco_nxos',  
            'host': device_name,
            'username': username,
            'password': password,
            'timeout': 300,
            'session_timeout': 600,
            'conn_timeout': 60,
            # Increased read_timeout for large routing tables
            'read_timeout_override': 300, 
            'global_delay_factor': 2, 
        }

        combined_chunks = []
        try:
            from netmiko import ConnectHandler
            print("   Connecting ...")
            with ConnectHandler(**params) as conn:
                # Ensure terminal length is 0 (NX-OS driver usually does this, but explicit is safe)
                conn.send_command("terminal length 0", cmd_verify=False)
                conn.send_command("terminal width 511", cmd_verify=False)
                conn.clear_buffer()

                for idx_cmd, cmd in enumerate(cmds, 1):
                    print(f"   -> ({idx_cmd}/{len(cmds)}) {cmd}")
                    t0 = datetime.datetime.now()
                    
                    # IMPROVED SEND COMMAND
                    # 1. Removed expect_string=r'#' (let Netmiko find exact prompt)
                    # 2. Enabled cmd_verify=True (waits for echo, prevents race conditions)
                    output = conn.send_command(
                        cmd, 
                        # delay_factor increases the wait time between read operations
                        delay_factor=2, 
                        # max_loops handles very long outputs
                        max_loops=5000,
                        strip_prompt=False, 
                        strip_command=False,
                        # read_timeout ensures we wait long enough for the device to start sending
                        read_timeout=300,
                        cmd_verify=True
                    )
                    
                    elapsed = (datetime.datetime.now() - t0).total_seconds()
                    
                    # Verify output validity
                    good, msg = verify_command_completion(output, device_name)
                    
                    # Add header for combined file
                    hdr = f"\n{cmd}\n" + "-"*len(cmd) + "\n"
                    combined_chunks.append(hdr + (output or "") + "\n")

                    if good:
                        print(f"      OK ({elapsed:.1f}s)")
                        ok += 1
                    else:
                        print(f"      WARNING: {msg} ({elapsed:.1f}s)")
                        output += f"\n[WARNING: {msg}]\n"
                        warn += 1

                    if not _skip_individual(cmd):
                        save_device_output(device_name, cmd, output, folder_path)
                    else:
                        print("      -> individual file suppressed (housekeeping cmd)")

            print("   Session closed")

        except Exception as exc:
            print(f"   x Connection error: {exc}")
            fail += len(cmds)
            continue

        # Write combined file
        if combined_chunks:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            cf = folder_path / f"{device_name}_combined_{ts}.txt"
            with open(cf, "w", encoding="utf-8") as fh:
                fh.write(("\n" + "="*80 + "\n").join(combined_chunks))
            print(f"   -> combined file: {cf.name}")

        print("-" * 70)

    # Summary
    print("\nCapture Summary")
    print(f"  Successful captures : {ok}")
    print(f"  Captures with warn  : {warn}")
    print(f"  Failed captures     : {fail}")
    print(f"  Command files dir   : {folder_path/'commands'}")
    print(f"  Combined files dir  : {folder_path}")


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

# ---------------------------------------------------------------------------
# UPDATED compare_device_outputs   (smart block-finder, per-VRF stats)
# ---------------------------------------------------------------------------
import csv, sys
from pathlib import Path
from collections import defaultdict
from typing import List

def compare_device_outputs():
    """
    Walks through every device file in ./before and ./after,
    compares the route tables, and writes per-device and combined CSVs.
    """
    before_folder = Path("before")
    after_folder  = Path("after")
    out_folder    = Path("output")

    if not before_folder.exists() or not after_folder.exists():
        print("Error: run modes 1 & 2 first.")
        return
    out_folder.mkdir(exist_ok=True)

    # map(devicename → Path)
    def _collect(folder: Path):
        d = {}
        for f in folder.glob("*.txt"):
            d[f.stem.split('_')[0]] = f
        return d

    before_files = _collect(before_folder)
    after_files  = _collect(after_folder)
    devices      = sorted(set(before_files) | set(after_files))

    print(f"Found {len(devices)} devices for comparison")

    # helper ─ pick the first route-command block that exists
    from typing import Tuple
    def _get_route_block(path: str) -> List[str]:
        cmds = ["show ip route vrf all | no-more",
                "show ip route vrf all",
                "show ip route"]
        for cmd in cmds:
            blk = extract_command_block(path, cmd)
            if blk:
                return blk
        return []

    combined_rows = []

    for dev in devices:
        bf, af = before_files.get(dev), after_files.get(dev)
        if not bf or not af:
            print(f"{dev}: missing before or after file – skipped")
            continue

        print(f"\n{dev}: extracting routes …")
        before_routes = extract_routes(_get_route_block(str(bf)))
        after_routes  = extract_routes(_get_route_block(str(af)))

        csv_path = out_folder / f"{dev}_comparison.csv"
        compare_and_output(before_routes, after_routes, str(csv_path),
                           "before", "after")

        # stash rows for combined CSV
        with csv_path.open(newline='') as fh:
            rdr = csv.DictReader(fh)
            for r in rdr:
                r["Device"] = dev
                combined_rows.append(r)

    # build combined report
    if combined_rows:
        comb = out_folder / "combined_comparison.csv"
        hdrs = ["Device"] + sorted({h for row in combined_rows for h in row if h != "Device"})
        with comb.open("w", newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=hdrs)
            w.writeheader()
            combined_rows.sort(key=lambda x: (x["Device"], x.get("VRF",""), x.get("Subnet","")))
            w.writerows(combined_rows)
        print(f"\nCombined report: {comb}")

# ---------------------------------------------------------------------------
# HELPERS ── extract only the wanted command from a combined file
# ---------------------------------------------------------------------------
def extract_command_block(path: str, wanted_cmd: str = "show ip route") -> List[str]:
    """
    Return *only* the lines that belong to the first command whose header line
    exactly matches *wanted_cmd* (case-insensitive) inside a combined capture
    file.  Header lines were written by capture_device_outputs() like this:

        show ip route
        -------------
        <command output …>
        …
        show ip bgp
        -----------        <-- next header → stop collecting

    If the command is not found, an empty list is returned.
    """
    wanted_cmd = wanted_cmd.strip().lower()
    lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()

    inside = False
    block: List[str] = []          # ← List[str] works on Python 3.8

    i = 0
    while i < len(lines):
        ln = lines[i].rstrip("\n")

        if not inside:
            # Header line?
            if ln.strip().lower() == wanted_cmd:
                inside = True      # start capturing
                i += 2             # skip the dashed underline
                continue
        else:
            # A new header starts → stop
            if (re.match(r"^\s*[a-z].*$", ln)
                    and i + 1 < len(lines)
                    and set(lines[i + 1].strip()) == {"-"}):
                break
            block.append(ln)
        i += 1

    return block


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
            input_file = input("Enter CSV file path (default: devices.csv): ").strip() or "devices.csv"
            if not os.path.exists(input_file):
                print(f"Error: Input file {input_file} not found")
                input("Press Enter to continue...")
                continue

            try:
                capture_device_outputs(1, input_file)   # ← no username/password
                print("\n✓ BEFORE state capture completed!")
            except Exception as e:
                print(f"\n✗ Error during BEFORE state capture: {e}")
            input("Press Enter to return to menu...")

        elif choice == 2:
            print("\n--- CAPTURING AFTER STATE ---")
            input_file = input("Enter CSV file path (default: devices.csv): ").strip() or "devices.csv"
            if not os.path.exists(input_file):
                print(f"Error: Input file {input_file} not found")
                input("Press Enter to continue...")
                continue

            try:
                capture_device_outputs(2, input_file)   # ← no username/password
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
