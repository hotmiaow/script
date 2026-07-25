#!/usr/bin/env python3
import sys
import os
import re
import argparse

CATEGORIES = {
    "03_zone": [r"^config system zone$"],
    "04_address": [r"^config firewall address$", r"^config firewall address6$"],
    "05_address_group": [r"^config firewall addrgrp$", r"^config firewall addrgrp6$"],
    "06_service": [r"^config firewall service custom$", r"^config firewall service category$"],
    "07_service_group": [r"^config firewall service group$"],
    "08_routing": [r"^config router "],
    "09_IP_pool": [r"^config firewall ippool", r"^config firewall ippool6"],
    "10_VIP": [r"^config firewall vip", r"^config firewall vip6", r"^config firewall vipgrp", r"^config firewall vipgrp6", r"^config firewall vip46", r"^config firewall vip64"],
    "11_source_NAT": [r"^config firewall central-snat-map", r"^config firewall central-snat-map6"],
    "12_policy": [r"^config firewall policy", r"^config firewall policy6", r"^config firewall multicast-policy"],
}

def split_block_into_edits(lines):
    header = []
    edits = []
    footer = []
    
    depth = 0
    in_edit = False
    current_edit = []
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith("config "):
            depth += 1
            
        if depth == 1 and stripped.startswith("edit "):
            in_edit = True
            current_edit = [line]
        elif depth == 1 and stripped == "next" and in_edit:
            current_edit.append(line)
            edits.append(current_edit)
            in_edit = False
            current_edit = []
        else:
            if in_edit:
                current_edit.append(line)
            else:
                if len(edits) == 0:
                    header.append(line)
                else:
                    footer.append(line)
                    
        if stripped == "end":
            depth -= 1
            
    return header, edits, footer

def is_lag_edit(edit_lines):
    for line in edit_lines:
        stripped = line.strip()
        if stripped in ("set type aggregate", "set type redundant"):
            return True
    return False

def get_category(block_name):
    for cat_name, patterns in CATEGORIES.items():
        for p in patterns:
            if re.match(p, block_name):
                return cat_name
    return None

def write_category(output_dir, cat_prefix, blocks, max_lines=3000):
    for block_lines in blocks:
        if not block_lines:
            continue
            
        first_line = block_lines[0].strip()
        name = first_line.replace("config ", "").strip().replace(" ", "_")
        
        header, edits, footer = split_block_into_edits(block_lines)
        
        if not edits or len(block_lines) <= max_lines:
            filename = f"{cat_prefix}_{name}.txt"
            with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
                f.writelines(block_lines)
        else:
            chunks = []
            current_chunk = []
            current_lines = 0
            
            for edit in edits:
                edit_len = len(edit)
                if current_lines + edit_len > max_lines and current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_lines = 0
                current_chunk.append(edit)
                current_lines += edit_len
            if current_chunk:
                chunks.append(current_chunk)
                
            for i, chunk in enumerate(chunks):
                filename = f"{cat_prefix}_{name}_part{i+1}.txt"
                with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
                    f.writelines(header)
                    for edit in chunk:
                        f.writelines(edit)
                    f.writelines(footer)

def split_fortigate_config(input_file: str, max_lines: int):
    output_dir = "splited_config"
    os.makedirs(output_dir, exist_ok=True)

    with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    blocks_to_write = {
        "01_LAG": [],
        "02_interface": [],
    }
    for cat in CATEGORIES:
        blocks_to_write[cat] = []

    interface_blocks = []
    others_lines = []
    capture_target = None
    capture_lines = []
    capture_depth = 0

    for line in lines:
        stripped = line.strip()
        
        if capture_target:
            capture_lines.append(line)
            if stripped.startswith("config "):
                capture_depth += 1
            elif stripped == "end":
                capture_depth -= 1
                if capture_depth == 0:
                    if capture_target == "interface_split":
                        interface_blocks.append(capture_lines)
                    else:
                        blocks_to_write[capture_target].append(capture_lines)
                    capture_target = None
                    capture_lines = []
            continue

        if stripped.startswith("config "):
            if stripped in ("config system interface", "config system virtual-switch"):
                capture_target = "interface_split"
            else:
                cat = get_category(stripped)
                if cat:
                    capture_target = cat
                    
            if capture_target:
                capture_lines = [line]
                capture_depth = 1
                continue
                
        others_lines.append(line)

    for block_lines in interface_blocks:
        header, edits, footer = split_block_into_edits(block_lines)
        lag_edits = []
        iface_edits = []
        for e in edits:
            if is_lag_edit(e):
                lag_edits.append(e)
            else:
                iface_edits.append(e)
                
        if lag_edits:
            flat_lag = [l for e in lag_edits for l in e]
            blocks_to_write["01_LAG"].append(header + flat_lag + footer)
            
        if iface_edits:
            flat_iface = [l for e in iface_edits for l in e]
            blocks_to_write["02_interface"].append(header + flat_iface + footer)
            
        if not lag_edits and not iface_edits:
            blocks_to_write["02_interface"].append(block_lines)

    for prefix, blocks in blocks_to_write.items():
        if blocks:
            write_category(output_dir, prefix, blocks, max_lines)

    if others_lines:
        with open(os.path.join(output_dir, "others.txt"), "w", encoding="utf-8") as f:
            f.writelines(others_lines)

    print(f"Split completed. Check the '{output_dir}' directory for extracted files.")

def main():
    parser = argparse.ArgumentParser(
        description="Extract specific FortiGate config parts and split large blocks."
    )
    parser.add_argument("config", help="FortiGate config text file")
    parser.add_argument("--max-lines", type=int, default=3000, 
                        help="Maximum lines per file for large blocks (default: 3000)")

    args = parser.parse_args()
    split_fortigate_config(args.config, args.max_lines)

if __name__ == "__main__":
    main()
