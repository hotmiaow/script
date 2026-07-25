#!/usr/bin/env python3
import os
import re
import csv
import sys
from typing import List, Tuple, Optional, Dict

# ---------------------------
# Heuristics and regex helpers
# ---------------------------

ASPLAIN_RE = r'([1-9]\d{0,9})'
ASDOT_RE = r'([1-9]\d{0,4})\.([0-9]{1,5})'
IP_RE = r'(?:\d{1,3}\.){3}\d{1,3}'

# Precompiled core regexes (multiline-friendly where needed)
RE_ASPLAIN = re.compile(ASPLAIN_RE)
RE_ASDOT = re.compile(ASDOT_RE)

RE_ROUTER_BGP = re.compile(r'^\s*router\s+bgp\s+(\S+)\s*$', re.IGNORECASE | re.MULTILINE)
RE_NEIGH_LOCAL_AS = re.compile(r'^\s*neighbor\s+(?:' + IP_RE + r'|\S+)\s+local-as\s+(\S+)\s*$', re.IGNORECASE | re.MULTILINE)
RE_LOCAL_AS = re.compile(r'^\s*local-as\s+(\S+)\s*$', re.IGNORECASE | re.MULTILINE)

# FortiGate multi-line block delimiters
RE_FGT_BGP_BLOCK = re.compile(r'^\s*config\s+router\s+bgp\b(.*?)(?:^\s*end\s*$)', re.IGNORECASE | re.MULTILINE | re.DOTALL)
RE_FGT_SET_AS = re.compile(r'^\s*set\s+as\s+(\S+)\s*$', re.IGNORECASE | re.MULTILINE)
RE_FGT_SET_LOCAL_AS = re.compile(r'^\s*set\s+local-as\s+(\S+)\s*$', re.IGNORECASE | re.MULTILINE)

# FortiGate inline patterns (optimized):
# 1) Fast line-oriented single-line matches (most common)
RE_FGT_INLINE_GLOBAL_AS_LINE = re.compile(r'\bconfig\s+router\s+bgp\b.*?\bset\s+as\s+(\S+)', re.IGNORECASE)
RE_FGT_INLINE_LOCAL_AS_LINE = re.compile(r'\bset\s+local-as\s+(\S+)', re.IGNORECASE)
# 2) Bounded-span inline matches to catch “config vdom edit ... config router bgp ... set as X”
# Limit the distance between tokens to avoid scanning entire large files.
# We use a tempered dot that won’t cross extremely long gaps: up to 500 non-newline characters between tokens.
# Adjust 500 to 300/800 based on real configs if needed.
SPAN = 500
RE_FGT_INLINE_GLOBAL_AS_SPAN = re.compile(
    rf'config\s+vdom\b(?:[^\n]{{0,{SPAN}}})?\bedit\b(?:[^\n]{{0,{SPAN}}})?\bconfig\s+router\s+bgp\b(?:[^\n]{{0,{SPAN}}})?\bset\s+as\s+(\S+)',
    re.IGNORECASE
)
RE_FGT_INLINE_LOCAL_AS_SPAN = re.compile(
    rf'config\s+vdom\b(?:[^\n]{{0,{SPAN}}})?\bedit\b(?:[^\n]{{0,{SPAN}}})?\bconfig\s+router\s+bgp\b(?:[^\n]{{0,{SPAN}}})?\bset\s+local-as\s+(\S+)',
    re.IGNORECASE
)

# Hostname patterns
RE_FGT_HOSTNAME_INLINE = re.compile(r'\bset\s+hostname\s+(\S+)\b', re.IGNORECASE)
RE_CISCO_HOSTNAME = re.compile(r'^\s*hostname\s+([A-Za-z0-9._\-]+)\s*$', re.MULTILINE)
RE_NXOS_SWITCHNAME = re.compile(r'^\s*switchname\s+(\S+)', re.MULTILINE)

# Binary detection setup
BINARY_EXT_DENYLIST = {
    '.zip', '.gz', '.tgz', '.bz2', '.xz', '.7z',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.ppt', '.pptx', '.jpg', '.jpeg', '.png', '.gif',
    '.pcap', '.pcapng', '.bin', '.img', '.iso', '.dmg', '.exe'
}
BINARY_MAGIC_PREFIXES = [
    b'\x7fELF', b'\x89PNG\r\n\x1a\n', b'GIF87a', b'GIF89a', b'\xff\xd8\xff', b'PK\x03\x04', b'%PDF-',
]
CONTROL_BYTES = set(range(0x00, 0x20)) - {0x09, 0x0A, 0x0D}

def asdot_to_asplain(upper: int, lower: int) -> Optional[int]:
    if upper < 0 or lower < 0 or upper > 0xFFFF or lower > 0xFFFF:
        return None
    return upper * 65536 + lower

def normalize_asn(token: str) -> Optional[str]:
    token = token.strip()
    m = RE_ASDOT.fullmatch(token)
    if m:
        upper = int(m.group(1)); lower = int(m.group(2))
        v = asdot_to_asplain(upper, lower)
        return str(v) if v is not None else None
    m = RE_ASPLAIN.fullmatch(token)
    if m:
        return m.group(1)
    return None

# ---------------------------
# Text detection
# ---------------------------

def is_probably_text_file(path: str, sniff_bytes: int = 4096) -> Tuple[bool, str, str]:
    base = os.path.basename(path)
    _, ext = os.path.splitext(base)
    ext = ext.lower()

    if ext in BINARY_EXT_DENYLIST:
        return False, '', f'skipped_binary_extension:{ext}'

    try:
        with open(path, 'rb') as f:
            chunk = f.read(sniff_bytes)
    except Exception as e:
        return False, '', f'open_error:{e}'

    if not chunk:
        return True, 'unknown', ''

    for magic in BINARY_MAGIC_PREFIXES:
        if chunk.startswith(magic):
            return False, '', f'binary_magic:{magic[:8]!r}'

    if b'\x00' in chunk:
        return False, '', 'contains_null_bytes'

    try:
        chunk.decode('utf-8')
        return True, 'utf-8', ''
    except UnicodeDecodeError:
        pass

    try:
        chunk.decode('latin-1')
        ctrl_count = sum(b in CONTROL_BYTES for b in chunk)
        ratio = ctrl_count / max(1, len(chunk))
        if ratio > 0.01:
            return False, '', f'high_control_density:{ratio:.3f}'
        return True, 'latin-1', ''
    except Exception:
        return False, '', 'decode_failed'

def read_text_file(path: str, charset_hint: Optional[str]) -> str:
    encs = [charset_hint] if charset_hint and charset_hint != 'unknown' else []
    encs += ['utf-8', 'latin-1']
    for enc in encs:
        try:
            with open(path, 'r', encoding=enc, errors='strict') as f:
                return f.read()
        except Exception:
            continue
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

# ---------------------------
# Device detection and hostname
# ---------------------------

def guess_device_type(text: str) -> str:
    if re.search(r'^\s*set\s+hostname\s+', text, re.MULTILINE) or \
       re.search(r'^\s*config\s+system\s+global', text, re.MULTILINE) or \
       re.search(r'^\s*config\s+router\s+bgp', text, re.MULTILINE):
        return 'FortiGate'
    if re.search(r'^\s*feature\s+bgp', text, re.MULTILINE) or \
       re.search(r'^\s*switchname\s+', text, re.MULTILINE) or \
       re.search(r'^\s*interface\s+Ethernet\d+/\d+', text, re.MULTILINE):
        return 'Cisco NX-OS'
    if re.search(r'^\s*router\s+bgp\s+\S+', text, re.MULTILINE) and \
       re.search(r'^\s*(route-policy|router static|interface [A-Za-z]+Ethernet\d+/\d+/\d+)', text, re.MULTILINE):
        return 'Cisco IOS-XR'
    if re.search(r'^\s*router\s+bgp\s+', text, re.MULTILINE):
        return 'Cisco IOS/IOS-XE'
    return 'Unknown'

def extract_hostname(text: str, device_type: str) -> Optional[str]:
    if device_type == 'FortiGate':
        m = RE_FGT_HOSTNAME_INLINE.search(text)
        if m:
            return m.group(1)
    m = RE_CISCO_HOSTNAME.search(text)
    if m:
        return m.group(1)
    if device_type == 'Cisco NX-OS':
        m = RE_NXOS_SWITCHNAME.search(text)
        if m:
            return m.group(1)
    return None

# ---------------------------
# ASN extraction (optimized)
# ---------------------------

def find_bgp_asns(text: str, device_type: str) -> List[Tuple[str, str]]:
    matches: List[Tuple[str, str]] = []

    # Fast Cisco-family matches (line-oriented)
    for m in RE_ROUTER_BGP.finditer(text):
        asn = normalize_asn(m.group(1))
        if asn:
            matches.append(('router bgp', asn))
    for m in RE_NEIGH_LOCAL_AS.finditer(text):
        asn = normalize_asn(m.group(1))
        if asn:
            matches.append(('neighbor local-as', asn))
    for m in RE_LOCAL_AS.finditer(text):
        asn = normalize_asn(m.group(1))
        if asn:
            matches.append(('local-as', asn))

    # FortiGate paths
    if device_type == 'FortiGate' or 'config router bgp' in text or 'set local-as' in text or 'set as ' in text:
        # 1) Multi-line blocks (fast if present)
        for block_m in RE_FGT_BGP_BLOCK.finditer(text):
            block = block_m.group(1)
            for m in RE_FGT_SET_AS.finditer(block):
                asn = normalize_asn(m.group(1))
                if asn:
                    matches.append(('fortigate set as', asn))
            for m in RE_FGT_SET_LOCAL_AS.finditer(block):
                asn = normalize_asn(m.group(1))
                if asn:
                    matches.append(('fortigate neighbor local-as', asn))

        # 2) Inline single-line forms (very common)
        # Scan once line-by-line to avoid DOTALL cost across the whole text
        # Use a cheap pre-check to avoid regex if token absent in the line
        for line in text.splitlines():
            ln = line.strip()
            if not ln:
                continue
            if 'set as ' in ln and 'config router bgp' in ln:
                m = RE_FGT_INLINE_GLOBAL_AS_LINE.search(ln)
                if m:
                    asn = normalize_asn(m.group(1))
                    if asn:
                        matches.append(('fortigate inline set as', asn))
            if 'set local-as' in ln:
                m2 = RE_FGT_INLINE_LOCAL_AS_LINE.search(ln)
                if m2:
                    asn = normalize_asn(m2.group(1))
                    if asn:
                        matches.append(('fortigate inline local-as', asn))

        # 3) Rare inline spanning tokens on one physical line but with long spaces/tokens in between
        # Only run these bounded-span regexes if hints suggest a vdom/inline sequence.
        if ('config vdom' in text and 'config router bgp' in text and ('set as ' in text or 'set local-as' in text)):
            for m in RE_FGT_INLINE_GLOBAL_AS_SPAN.finditer(text):
                asn = normalize_asn(m.group(1))
                if asn:
                    matches.append(('fortigate inline set as', asn))
            for m in RE_FGT_INLINE_LOCAL_AS_SPAN.finditer(text):
                asn = normalize_asn(m.group(1))
                if asn:
                    matches.append(('fortigate inline local-as', asn))

    # Deduplicate (context,asn)
    seen = set()
    uniq: List[Tuple[str, str]] = []
    for ctx, asn in matches:
        key = (ctx, asn)
        if key not in seen:
            seen.add(key)
            uniq.append((ctx, asn))
    return uniq

# ---------------------------
# Scanning logic with progress
# ---------------------------

def scan_text_file(path: str, charset: str) -> List[Dict]:
    text = read_text_file(path, charset)
    device_type = guess_device_type(text)
    hostname = extract_hostname(text, device_type) or ''
    asns = find_bgp_asns(text, device_type)
    rows = []
    for ctx, asn in asns:
        rows.append({
            'filename': os.path.basename(path),
            'device_name': hostname,
            'device_type': device_type,
            'matched_context': ctx,
            'asn': asn,
        })
    return rows

def main():
    candidates = [f for f in os.listdir('.') if os.path.isfile(f)]
    candidates.sort()
    total = len(candidates)
    if total == 0:
        print("No files found in current directory.")
        return

    positive_rows: List[Dict] = []

    print(f"Starting scan: {total} files")
    for idx, f in enumerate(candidates, start=1):
        left = total - idx
        print(f"[{idx}/{total}] Processing: {f}  ({left} left)")

        is_text, charset, reason = is_probably_text_file(f)
        if not is_text:
            print(f"  -> Skipped non-text: {reason}")
            continue

        try:
            rows = scan_text_file(f, charset)
            if rows:
                positive_rows.extend(rows)
                print(f"  -> Found ASNs: {len(rows)}")
            else:
                print("  -> No ASN found")
        except Exception as e:
            print(f"  -> Error: {e}")

    out = 'bgp_asn_map.csv'
    fieldnames = ['filename', 'device_name', 'device_type', 'matched_context', 'asn']
    with open(out, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(positive_rows)

    print(f"Completed. Files processed: {total}/{total}")
    print(f"CSV rows written (only files with ASNs): {len(positive_rows)}")
    print(f"Output: {out}")

if __name__ == '__main__':
    main()
