#!/usr/bin/env python3
import csv
import argparse
import re
import sys
from typing import Set, List, Optional, Tuple, Dict, DefaultDict
from collections import defaultdict, OrderedDict

# Accept both asplain and asdot
ASPLAIN_RE = r'([1-9]\d{0,9})'
ASDOT_RE = r'([1-9]\d{0,4})\.([0-9]{1,5})'

# Liberal AS-path extraction patterns. We’ll parse:
# - "set as-path prepend <asn> [<asn> ...]" (Cisco/Juniper style in route-map/policy)
# - "as-path prepend <asn> [<asn> ...]" (variants)
# - "set aspath prepend <asn> [<asn> ...]" (typo/alt)
# Note: We’re extracting the sequence of ASNs that appear to be prepended; this is
# not necessarily the full end-to-end AS_PATH learned from BGP, but the configured
# prepend sequence in the device’s policy. We normalize each ASN from asdot to asplain.
ASPATH_CANDIDATE_PATTERNS = [
    r'\bset\s+as-?path\s+prepend\s+([0-9\. ]+)',
    r'\bas-?path\s+prepend\s+([0-9\. ]+)',
]

def asdot_to_asplain(upper: int, lower: int) -> Optional[int]:
    if upper < 0 or lower < 0 or upper > 0xFFFF or lower > 0xFFFF:
        return None
    return upper * 65536 + lower

def normalize_asn(token: str) -> Optional[str]:
    token = token.strip()
    m = re.fullmatch(ASDOT_RE, token)
    if m:
        upper = int(m.group(1))
        lower = int(m.group(2))
        v = asdot_to_asplain(upper, lower)
        return str(v) if v is not None else None
    m = re.fullmatch(ASPLAIN_RE, token)
    if m:
        return m.group(1)
    return None

def normalize_asn_list(tokens: List[str]) -> List[str]:
    out: List[str] = []
    for t in tokens:
        n = normalize_asn(t)
        if n:
            out.append(n)
    return out

def unique_preserve_order(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def load_csv(csv_path: str) -> List[dict]:
    rows: List[dict] = []
    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        # Expected columns from scanner: filename, device_name, device_type, matched_context, asn
        for r in reader:
            # Only rows with an ASN present (scanner already limited to matches)
            if not r.get('asn'):
                continue
            rows.append(r)
    return rows

def build_indexes(rows: List[dict]) -> Tuple[
    DefaultDict[str, Set[str]],
    DefaultDict[str, Set[str]],
    DefaultDict[str, List[List[str]]],
    Dict[str, List[dict]]
]:
    """
    Returns:
    - devices_by_asn: ASN -> set(device_name)
    - asns_by_device: device_name -> set(ASN)
    - aspaths_by_device: device_name -> list of AS-path lists (each path is ordered list of ASNs)
    - rows_by_device: device_name -> list of original row dicts (for details if needed)
    """
    devices_by_asn: DefaultDict[str, Set[str]] = defaultdict(set)
    asns_by_device: DefaultDict[str, Set[str]] = defaultdict(set)
    aspaths_by_device: DefaultDict[str, List[List[str]]] = defaultdict(list)
    rows_by_device: Dict[str, List[dict]] = defaultdict(list)

    for r in rows:
        device = (r.get('device_name') or '').strip()
        asn = (r.get('asn') or '').strip()
        if not device or not asn:
            continue
        devices_by_asn[asn].add(device)
        asns_by_device[device].add(asn)
        rows_by_device[device].append(r)

    return devices_by_asn, asns_by_device, aspaths_by_device, rows_by_device

def enrich_aspaths_for_devices(aspaths_by_device: DefaultDict[str, List[List[str]]],
                               rows_by_device: Dict[str, List[dict]],
                               csv_path: str) -> None:
    """
    To extract configured AS-path prepend sequences, we need the raw config text.
    However, the CSV does not contain raw text. The simplest practical approach:
      - Re-open the original config files (filename column) found alongside the CSV.
      - Extract any "set as-path prepend ..." sequences per device.
    This assumes the CSV was generated in the same directory where the configs still exist.
    If a file is not present, we skip AS-path extraction for that device.
    """
    # We’ll scan each referenced filename once and cache findings per device.
    scanned_cache: Dict[str, List[List[str]]] = {}
    for device, rows in rows_by_device.items():
        # Find unique filenames for this device
        fnames = unique_preserve_order([ (r.get('filename') or '').strip() for r in rows if r.get('filename') ])
        aspaths_accum: List[List[str]] = []
        for fn in fnames:
            if not fn:
                continue
            if fn in scanned_cache:
                aspaths_accum.extend(scanned_cache[fn])
                continue
            # Attempt to read the file in current directory
            try:
                with open(fn, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except Exception:
                # If not accessible, skip silently
                continue
            # Find all candidate AS-path lines and parse numbers
            device_paths: List[List[str]] = []
            for pat in ASPATH_CANDIDATE_PATTERNS:
                for m in re.finditer(pat, text, flags=re.IGNORECASE):
                    blob = m.group(1)
                    # Split by whitespace, normalize each token, keep order, remove dups in-sequence
                    tokens = [t for t in re.split(r'\s+', blob.strip()) if t]
                    norm = normalize_asn_list(tokens)
                    if norm:
                        # Do not collapse duplicates here; repeated ASNs are meaningful in prepend
                        device_paths.append(norm)
            scanned_cache[fn] = device_paths
            aspaths_accum.extend(device_paths)
        if aspaths_accum:
            aspaths_by_device[device].extend(aspaths_accum)

def main():
    parser = argparse.ArgumentParser(
        description="Group devices by ASN and show per-device ASNs and AS-path sequences."
    )
    parser.add_argument('asns', nargs='+', help='One or more AS numbers (asplain or asdot, e.g., 65000 or 1.10)')
    parser.add_argument('--csv', dest='csv_path', default='bgp_asn_map.csv',
                        help='Path to the CSV produced by the scanner (default: bgp_asn_map.csv)')
    parser.add_argument('--show-details', dest='show_details', action='store_true',
                        help='In the per-ASN section, include filename and device_type next to device names')
    parser.add_argument('--no-aspath', action='store_true',
                        help='Skip scanning original config files for AS-path prepend sequences')
    args = parser.parse_args()

    # Normalize query ASNs
    query_asns: Set[str] = set()
    for a in args.asns:
        na = normalize_asn(a)
        if not na:
            print(f"Warning: invalid ASN format skipped: {a}", file=sys.stderr)
            continue
        query_asns.add(na)

    if not query_asns:
        print("No valid ASNs provided.", file=sys.stderr)
        sys.exit(1)

    # Load CSV rows
    try:
        rows = load_csv(args.csv_path)
    except FileNotFoundError:
        print(f"CSV not found: {args.csv_path}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error reading CSV: {e}", file=sys.stderr)
        sys.exit(3)

    # Build indexes and per-device rollups
    devices_by_asn, asns_by_device, aspaths_by_device, rows_by_device = build_indexes(rows)

    # For the devices that match the queried ASNs, optionally extract AS-path sequences from their config files
    matched_devices: Set[str] = set()
    for q in query_asns:
        matched_devices |= devices_by_asn.get(q, set())

    if not args.no_aspath and matched_devices:
        enrich_aspaths_for_devices(aspaths_by_device, rows_by_device, args.csv_path)

    # Section 1: Devices per ASN (one line per ASN)
    # If --show-details, print device(name|filename|type). Otherwise just device names.
    print("== Devices per ASN ==")
    for q in sorted(query_asns, key=lambda x: int(x) if x.isdigit() else x):
        devs = sorted(devices_by_asn.get(q, set()))
        if not devs:
            print(f"{q}:")
            continue
        if args.show_details:
            # Build per-device details using the first row per device
            details_strings: List[str] = []
            for d in devs:
                sample = next((r for r in rows_by_device.get(d, []) if (r.get('asn') or '').strip() == q), None)
                if sample:
                    fn = (sample.get('filename') or '').strip()
                    dt = (sample.get('device_type') or '').strip()
                    details_strings.append(f"{d} ({fn}|{dt})")
                else:
                    details_strings.append(d)
            print(f"{q}: " + ", ".join(details_strings))
        else:
            print(f"{q}: " + ", ".join(devs))

    # Section 2: Per-device rollup for all matched devices
    # Show: DeviceName | ASNs: a,b,c | AS-paths: [a a a],[b b],[c d e]
    if matched_devices:
        print("\n== Per-device ASNs and AS-path sequences (for matched devices) ==")
        for d in sorted(matched_devices):
            dev_asns = sorted(asns_by_device.get(d, set()), key=lambda x: int(x) if x.isdigit() else x)
            # Build AS-path display: each path as "[asn asn asn]" preserving repeats and order
            paths = aspaths_by_device.get(d, [])
            paths_disp = []
            for p in paths:
                # Display in sequence; repeats matter in prepend
                paths_disp.append("[" + " ".join(p) + "]")
            asns_str = ",".join(dev_asns) if dev_asns else ""
            paths_str = ", ".join(paths_disp) if paths_disp else ""
            if paths_str:
                print(f"{d} | ASNs: {asns_str} | AS-paths: {paths_str}")
            else:
                print(f"{d} | ASNs: {asns_str}")

if __name__ == '__main__':
    main()
