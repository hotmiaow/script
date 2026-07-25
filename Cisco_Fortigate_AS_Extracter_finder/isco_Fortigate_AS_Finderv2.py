#!/usr/bin/env python3
import csv
import argparse
import re
import sys
from typing import Set, List, Optional, Tuple, Dict, DefaultDict
from collections import defaultdict

# Accept both asplain (e.g., 65000) and asdot (e.g., 1.10)
ASPLAIN_RE = r'([1-9]\d{0,9})'
ASDOT_RE = r'([1-9]\d{0,4})\.([0-9]{1,5})'

def asdot_to_asplain(upper: int, lower: int) -> Optional[int]:
    # RFC4893: asplain = upper * 65536 + lower
    if upper < 0 or lower < 0 or upper > 0xFFFF or lower > 0xFFFF:
        return None
    return upper * 65536 + lower

def normalize_asn(token: str) -> Optional[str]:
    token = token.strip()
    m = re.fullmatch(ASDOT_RE, token)
    if m:
        upper = int(m.group(1)); lower = int(m.group(2))
        v = asdot_to_asplain(upper, lower)
        return str(v) if v is not None else None
    m = re.fullmatch(ASPLAIN_RE, token)
    if m:
        return m.group(1)
    return None

def load_csv_generic(path: str,
                     device_col: str = 'device_name',
                     asn_col: str = 'asn',
                     filename_col: Optional[str] = 'filename',
                     dtype_col: Optional[str] = 'device_type') -> List[dict]:
    """
    Load rows from a CSV with at least (device_name, asn).
    Optional columns: filename, device_type. Missing cols will be blank.
    Returns normalized dicts with keys: device_name, asn, filename, device_type
    """
    rows: List[dict] = []
    try:
        with open(path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for r in reader:
                device = (r.get(device_col) or '').strip()
                asn_raw = (r.get(asn_col) or '').strip()
                if not device or not asn_raw:
                    continue
                asn = normalize_asn(asn_raw)
                if not asn:
                    continue
                rows.append({
                    'device_name': device,
                    'asn': asn,
                    'filename': (r.get(filename_col) or '').strip() if filename_col else '',
                    'device_type': (r.get(dtype_col) or '').strip() if dtype_col else '',
                })
    except FileNotFoundError:
        # Silently skip if file not present
        return []
    except Exception as e:
        print(f"Warning: failed to read {path}: {e}", file=sys.stderr)
        return []
    return rows

def load_all_sources(scanner_csv: str,
                     fortigate_csv: str = 'fortigate_as.csv',
                     addon_csv: str = 'addon.csv') -> List[dict]:
    # bgp_asn_map.csv expected columns: filename, device_name, device_type, matched_context, asn
    scanner_rows: List[dict] = load_csv_generic(scanner_csv,
                                                device_col='device_name',
                                                asn_col='asn',
                                                filename_col='filename',
                                                dtype_col='device_type')
    fortigate_rows: List[dict] = load_csv_generic(fortigate_csv,
                                                  device_col='device_name',
                                                  asn_col='asn',
                                                  filename_col='filename',
                                                  dtype_col='device_type')
    addon_rows: List[dict] = load_csv_generic(addon_csv,
                                              device_col='device_name',
                                              asn_col='asn',
                                              filename_col='filename',
                                              dtype_col='device_type')
    return scanner_rows + fortigate_rows + addon_rows

def build_index(rows: List[dict]) -> Dict[str, List[dict]]:
    """
    Build ASN -> list of row dicts (each row has device_name, asn, filename, device_type)
    Maintain insertion order per ASN to keep stable device ordering from sources.
    """
    by_asn: Dict[str, List[dict]] = defaultdict(list)
    seen_pairs: Set[Tuple[str, str]] = set()  # (asn, device_name) to avoid duplicates
    for r in rows:
        asn = r['asn']
        dev = r['device_name']
        key = (asn, dev)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        by_asn[asn].append(r)
    return by_asn

def main():
    parser = argparse.ArgumentParser(
        description="Query devices by ASN from bgp_asn_map.csv + fortigate_as.csv + addon.csv. "
                    "Outputs ASNs in reverse of input order; prints 'unknown device' when no match."
    )
    parser.add_argument('asns', nargs='+', help='One or more AS numbers (asplain or asdot, e.g., 65000 or 1.10)')
    parser.add_argument('--csv', dest='csv_path', default='bgp_asn_map.csv',
                        help='Primary scanner CSV (default: bgp_asn_map.csv)')
    parser.add_argument('--fortigate-csv', dest='fortigate_csv', default='fortigate_as.csv',
                        help='FortiGate supplemental CSV (default: fortigate_as.csv)')
    parser.add_argument('--addon-csv', dest='addon_csv', default='addon.csv',
                        help='Additional supplemental CSV (default: addon.csv)')
    parser.add_argument('--show-details', dest='show_details', action='store_true',
                        help='Show device(filename|type) per ASN line')
    args = parser.parse_args()

    # Preserve the exact input tokens for display; also compute normalized equivalents for matching
    input_tokens: List[str] = args.asns[:]
    normalized_inputs: List[Tuple[str, Optional[str]]] = [(tok, normalize_asn(tok)) for tok in input_tokens]

    # Load sources and build index
    rows = load_all_sources(args.csv_path, args.fortigate_csv, args.addon_csv)
    if not rows:
        print("No data rows found from any source.", file=sys.stderr)
        sys.exit(2)

    by_asn = build_index(rows)

    # Print one line per input ASN in REVERSED order
    # Use original token for label; match by normalized value; print unknown device if no matches
    for original, normalized in reversed(normalized_inputs):
        if not normalized:
            print(f"{original}: unknown device")
            continue
        hits = by_asn.get(normalized, [])
        if not hits:
            print(f"{original}: unknown device")
            continue
        if args.show_details:
            parts: List[str] = []
            for r in hits:
                dev = r['device_name']
                fn = r.get('filename', '')
                dt = r.get('device_type', '')
                parts.append(f"{dev} ({fn}|{dt})" if (fn or dt) else dev)
            print(f"{original}: " + ", ".join(parts))
        else:
            devices = [r['device_name'] for r in hits]
            print(f"{original}: " + ", ".join(devices))

if __name__ == '__main__':
    main()
