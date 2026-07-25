#!/usr/bin/env python3

"""
FortiGate Config Splitter

Split a FortiGate full configuration into categorized files.

Output example:
001_lag_config.conf
002_interface_config.conf
003_zone_config.conf
004_address_part1.conf
005_address_group.conf
006_service.conf
007_service_group.conf
008_routing.conf
009_ippool_dnat.conf
010_vip.conf
011_snat.conf
012_policy.conf
999_others.txt

Usage:
    python3 fortigate_splitter.py full.conf output_dir/

"""

import os
import re
import sys
from pathlib import Path

MAX_LINES_PER_FILE = 3000


SECTIONS = [
    {
        "name": "001_lag_config",
        "patterns": [
            r"^config system interface$",
        ],
        "filter": "lag_only"
    },
    {
        "name": "002_interface_config",
        "patterns": [
            r"^config system interface$",
        ],
        "filter": "interface_only"
    },
    {
        "name": "003_zone_config",
        "patterns": [
            r"^config system zone$",
        ],
    },
    {
        "name": "004_address",
        "patterns": [
            r"^config firewall address$",
        ],
        "split_large": True,
    },
    {
        "name": "005_address_group",
        "patterns": [
            r"^config firewall addrgrp$",
        ],
    },
    {
        "name": "006_service",
        "patterns": [
            r"^config firewall service custom$",
        ],
    },
    {
        "name": "007_service_group",
        "patterns": [
            r"^config firewall service group$",
        ],
    },
    {
        "name": "008_routing",
        "patterns": [
            r"^config router static$",
            r"^config router policy$",
            r"^config router bgp$",
            r"^config router ospf$",
            r"^config router rip$",
            r"^config router isis$",
            r"^config router prefix-list$",
            r"^config router route-map$",
            r"^config router community-list$",
            r"^config system sdwan$",
            r"^config vpn ipsec phase1-interface$",
            r"^config vpn ipsec phase2-interface$",
        ],
    },
    {
        "name": "009_ippool_dnat",
        "patterns": [
            r"^config firewall ippool$",
        ],
    },
    {
        "name": "010_vip",
        "patterns": [
            r"^config firewall vip$",
            r"^config firewall vipgrp$",
        ],
    },
    {
        "name": "011_snat",
        "patterns": [
            r"^config firewall central-snat-map$",
        ],
    },
    {
        "name": "012_policy",
        "patterns": [
            r"^config firewall policy$",
            r"^config firewall proxy-policy$",
            r"^config firewall local-in-policy$",
            r"^config firewall multicast-policy$",
        ],
    },
]


def read_config(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.readlines()


def extract_blocks(lines):
    blocks = []
    current_block = []
    depth = 0
    inside = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("config "):
            if not inside:
                current_block = []
                inside = True
                depth = 0

            depth += 1

        if inside:
            current_block.append(line)

        if stripped == "end":
            depth -= 1

            if depth == 0 and inside:
                blocks.append(current_block)
                current_block = []
                inside = False

    return blocks


def match_section(block, patterns):
    first_line = block[0].strip()

    for pattern in patterns:
        if re.match(pattern, first_line):
            return True

    return False


def is_lag_block(block):
    text = "".join(block)

    return (
        'set type aggregate' in text
        or 'set member ' in text
    )


def is_interface_block(block):
    text = "".join(block)

    return not (
        'set type aggregate' in text
        or 'set member ' in text
    )


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(content)


def split_large_file(base_path, content):
    chunks = []

    for i in range(0, len(content), MAX_LINES_PER_FILE):
        chunks.append(content[i:i + MAX_LINES_PER_FILE])

    for idx, chunk in enumerate(chunks, start=1):
        filename = f"{base_path}_part{idx}.conf"
        write_file(filename, chunk)


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 fortigate_splitter.py <config.conf> <output_dir>")
        sys.exit(1)

    config_path = sys.argv[1]
    output_dir = Path(sys.argv[2])

    output_dir.mkdir(parents=True, exist_ok=True)

    lines = read_config(config_path)
    blocks = extract_blocks(lines)

    collected = {}
    matched_blocks = set()

    for section in SECTIONS:
        collected[section["name"]] = []

    others = []

    for idx, block in enumerate(blocks):

        matched = False

        for section in SECTIONS:

            if match_section(block, section["patterns"]):

                if section.get("filter") == "lag_only":
                    if not is_lag_block(block):
                        continue

                if section.get("filter") == "interface_only":
                    if not is_interface_block(block):
                        continue

                collected[section["name"]].extend(block)
                collected[section["name"]].append("\n")

                matched = True

        if not matched:
            others.extend(block)
            others.append("\n")

    for section in SECTIONS:

        content = collected[section["name"]]

        if not content:
            continue

        output_base = output_dir / section["name"]

        if section.get("split_large"):
            split_large_file(str(output_base), content)
        else:
            write_file(f"{output_base}.conf", content)

    if others:
        write_file(output_dir / "999_others.txt", others)

    print(f"Done. Files written to: {output_dir}")


if __name__ == "__main__":
    main()