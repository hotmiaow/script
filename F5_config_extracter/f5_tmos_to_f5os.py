#!/usr/bin/env python3
"""
F5 TMOS to F5OS Network Configuration Converter
------------------------------------------------
This script parses an F5 TMOS 'bigip_base.conf' file (extracted from a UCS archive)
and extracts Trunk (LAG) and VLAN definitions, then translates them into F5OS CLI commands
suitable for F5 rSeries (e.g., R4000 series) appliances.

Usage:
    python3 f5_tmos_to_f5os.py -i bigip_base.conf -o f5os_config.cli [--interface-map map.json]
"""

import re
import argparse
import sys
import json

def parse_tmos_base_conf(conf_text):
    """
    Parses bigip_base.conf text and extracts trunks and vlans.
    """
    trunks = {}
    vlans = {}

    # Extract net trunk blocks
    trunk_pattern = re.compile(r'net\s+trunk\s+([^\s{]+)\s*\{', re.MULTILINE)
    for match in trunk_pattern.finditer(conf_text):
        name_raw = match.group(1)
        name = name_raw.split('/')[-1]
        start_idx = match.end()
        
        brace_count = 1
        end_idx = start_idx
        while end_idx < len(conf_text) and brace_count > 0:
            if conf_text[end_idx] == '{':
                brace_count += 1
            elif conf_text[end_idx] == '}':
                brace_count -= 1
            end_idx += 1
            
        body = conf_text[start_idx:end_idx-1]

        # Extract member interfaces
        interfaces = []
        iface_match = re.search(r'interfaces\s*\{([^}]+)\}', body)
        if iface_match:
            iface_text = iface_match.group(1)
            interfaces = re.findall(r'(\d+\.\d+)', iface_text)

        # Extract LACP mode
        lacp_mode = "active" # default
        lacp_mode_match = re.search(r'lacp-mode\s+([^\s;]+)', body)
        if lacp_mode_match:
            lacp_mode = lacp_mode_match.group(1).lower()

        trunks[name] = {
            "name": name,
            "interfaces": interfaces,
            "lacp_mode": lacp_mode
        }

    # Extract net vlan blocks
    vlan_pattern = re.compile(r'net\s+vlan\s+([^\s{]+)\s*\{', re.MULTILINE)
    
    for match in vlan_pattern.finditer(conf_text):
        name_raw = match.group(1)
        name = name_raw.split('/')[-1]
        start_idx = match.end()
        
        brace_count = 1
        end_idx = start_idx
        while end_idx < len(conf_text) and brace_count > 0:
            if conf_text[end_idx] == '{':
                brace_count += 1
            elif conf_text[end_idx] == '}':
                brace_count -= 1
            end_idx += 1
            
        body = conf_text[start_idx:end_idx-1]
        
        # Extract Tag ID
        tag_match = re.search(r'tag\s+(\d+)', body)
        tag = int(tag_match.group(1)) if tag_match else None
        
        # Extract interface/trunk assignments
        bindings = []
        iface_block = re.search(r'interfaces\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', body)
        if iface_block:
            ibody = iface_block.group(1)
            items = re.findall(r'([^\s{]+)\s*\{([^}]*)\}', ibody)
            for item_name_raw, item_body in items:
                item_name = item_name_raw.split('/')[-1]
                is_tagged = 'tagged' in item_body and 'untagged' not in item_body
                bindings.append({
                    "target": item_name,
                    "tagged": is_tagged
                })

        if tag is not None:
            vlans[name] = {
                "name": name,
                "tag": tag,
                "bindings": bindings
            }

    return trunks, vlans


def generate_f5os_commands(trunks, vlans, interface_map=None):
    """
    Generates F5OS CLI commands for LAGs, VLANs, and tenant VLAN assignments.
    """
    if interface_map is None:
        interface_map = {}

    cli_output = []
    cli_output.append("! " + "="*75)
    cli_output.append("! F5OS CLI Migration Script generated for F5 rSeries Platform")
    cli_output.append("! Note: Verify physical interface mappings before applying in production.")
    cli_output.append("! " + "="*75 + "\n")

    cli_output.append("config\n")

    # 1. Generate VLAN Creation
    cli_output.append("! --- 1. Create VLANs ---")
    vlan_ids = []
    for vlan_name, vdata in sorted(vlans.items(), key=lambda x: x[1]['tag']):
        cli_output.append(f"network vlans vlan {vlan_name} config vlan-id {vdata['tag']}")
        vlan_ids.append(vdata['tag'])
    cli_output.append("commit\n")

    # 2. Generate LAG (Trunk) Creation and VLAN Binding
    cli_output.append("! --- 2. Create LAGs (Trunks) and Assign VLANs ---")
    for tname, tdata in trunks.items():
        # Map old interfaces (e.g., 1.1, 1.2) to rSeries interfaces (e.g., 1.0, 2.0)
        mapped_ifaces = [interface_map.get(iface, iface) for iface in tdata['interfaces']]
        ifaces_str = " ".join(mapped_ifaces) if mapped_ifaces else "1.0 2.0"
        
        mode = tdata['lacp_mode'] if tdata['lacp_mode'] in ['active', 'passive'] else 'active'
        
        cli_output.append(f"! Config LAG: {tname}")
        cli_output.append(f"system lags lag {tname} config name {tname} mode {mode} interfaces [ {ifaces_str} ]")
        
        # Collect VLAN tags associated with this trunk
        trunk_vlans = []
        for vname, vdata in vlans.items():
            for binding in vdata['bindings']:
                if binding['target'] == tname:
                    trunk_vlans.append(str(vdata['tag']))
        
        if trunk_vlans:
            vlans_str = " ".join(sorted(trunk_vlans, key=int))
            cli_output.append(f"system lags lag {tname} config trunk-vlan-ids [ {vlans_str} ]")
        
        cli_output.append("")

    cli_output.append("commit\n")

    # 3. Summary of VLAN IDs to assign to Tenant Deployment
    cli_output.append("! --- 3. Summary for BIG-IP Tenant Deployment ---")
    cli_output.append("! Copy the list below into F5OS Tenant Management > Tenant Deployments > VLANs:")
    cli_output.append(f"! Assigned VLAN IDs: {', '.join(map(str, sorted(vlan_ids)))}")
    cli_output.append("!\n")

    return "\n".join(cli_output)


def main():
    parser = argparse.ArgumentParser(description="Parse TMOS bigip_base.conf and generate F5OS CLI commands.")
    parser.add_argument("-i", "--input", required=True, help="Path to bigip_base.conf file")
    parser.add_argument("-o", "--output", default="f5os_network_config.cli", help="Output path for generated F5OS CLI script")
    parser.add_argument("-m", "--map", help="Optional JSON file mapping old interfaces to new rSeries interfaces")

    args = parser.parse_args()

    interface_map = {}
    if args.map:
        try:
            with open(args.map, 'r') as f:
                interface_map = json.load(f)
        except Exception as e:
            print(f"[!] Warning: Could not load interface map file: {e}", file=sys.stderr)

    try:
        with open(args.input, 'r') as f:
            conf_text = f.read()
    except Exception as e:
        print(f"[!] Error opening input file: {e}", file=sys.stderr)
        sys.exit(1)

    trunks, vlans = parse_tmos_base_conf(conf_text)

    print(f"[+] Successfully extracted {len(trunks)} Trunk(s) and {len(vlans)} VLAN(s).")
    for tname, tdata in trunks.items():
        print(f"    - Trunk: {tname} | Members: {tdata['interfaces']} | Mode: {tdata['lacp_mode']}")
    for vname, vdata in vlans.items():
        print(f"    - VLAN: {vname} (Tag: {vdata['tag']})")

    f5os_cli = generate_f5os_commands(trunks, vlans, interface_map)

    with open(args.output, 'w') as f:
        f.write(f5os_cli)

    print(f"\n[+] Generated F5OS CLI script written to: {args.output}")

if __name__ == '__main__':
    main()
