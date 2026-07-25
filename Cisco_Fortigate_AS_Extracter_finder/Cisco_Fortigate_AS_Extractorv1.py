#!/usr/bin/env python3
import os
import re
import csv
from typing import List, Tuple, Optional, Dict

# ---------------------------
# Heuristics and regex helpers
# ---------------------------

ASPLAIN_RE = r'([1-9]\d{0,9})'
ASDOT_RE = r'([1-9]\d{0,4})\.([0-9]{1,5})'  # simple asdot match (upper.lower)
IP_RE = r'(?:\d{1,3}\.){3}\d{1,3}'

# Binary extensions to skip quickly
BINARY_EXT_DENYLIST = {
    '.zip', '.gz', '.tgz', '.bz2', '.xz', '.7z',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.ppt', '.pptx', '.jpg', '.jpeg', '.png', '.gif',
    '.pcap', '.pcapng', '.bin', '.img', '.iso', '.dmg', '.exe'
}

# Magic bytes that usually indicate binary files
BINARY_MAGIC_PREFIXES = [
    b'\x7fELF',              # ELF binary
    b'\x89PNG\r\n\x1a\n',    # PNG
    b'GIF87a', b'GIF89a',    # GIF
    b'\xff\xd8\xff',         # JPEG
    b'PK\x03\x04',           # ZIP (also docx/xlsx)
    b'%PDF-',                # PDF
]

CONTROL_BYTES = set(range(0x00, 0x20)) - {0x09, 0x0A, 0x0D}  # allow TAB, LF, CR

# ---------------------------
# Text detection (handles no-extension files)
# ---------------------------

def is_probably_text_file(path: str, sniff_bytes: int = 4096) -> Tuple[bool, str, str]:
    """
    Decide if a file is plain text.
    Returns (is_text, charset_detected, skip_reason_if_not_text)
    """
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
        # Empty file: treat as text but will produce no rows (and we won't write to CSV)
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
    encodings = []
    if charset_hint and charset_hint != 'unknown':
        encodings.append(charset_hint)
    encodings += ['utf-8', 'latin-1']
    for enc in encodings:
        try:
            with open(path, 'r', encoding=enc, errors='strict') as f:
                return f.read()
        except Exception:
            continue
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

# ---------------------------
# Parsing helpers
# ---------------------------

def asdot_to_asplain(upper: int, lower: int) -> Optional[int]:
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

def guess_device_type(text: str) -> str:
    t = text
    if re.search(r'^\s*set\s+hostname\s+', t, re.MULTILINE) or \
       re.search(r'^\s*config\s+system\s+global', t, re.MULTILINE) or \
       re.search(r'^\s*config\s+router\s+bgp', t, re.MULTILINE):
        return 'FortiGate'
    if re.search(r'^\s*feature\s+bgp', t, re.MULTILINE) or \
       re.search(r'^\s*switchname\s+', t, re.MULTILINE) or \
       re.search(r'^\s*interface\s+Ethernet\d+/\d+', t, re.MULTILINE):
        return 'Cisco NX-OS'
    if re.search(r'^\s*router\s+bgp\s+\S+', t, re.MULTILINE) and \
       re.search(r'^\s*(route-policy|router static|interface [A-Za-z]+Ethernet\d+/\d+/\d+)', t, re.MULTILINE):
        return 'Cisco IOS-XR'
    if re.search(r'^\s*router\s+bgp\s+', t, re.MULTILINE):
        return 'Cisco IOS/IOS-XE'
    return 'Unknown'

def extract_hostname(text: str, device_type: str) -> Optional[str]:
    if device_type == 'FortiGate':
        for pat in [
            r'^\s*set\s+hostname\s+(\S+)\s*$',
            r'^\s*config\s+system\s+global\b.*?^\s*set\s+hostname\s+(\S+)\s*$',
        ]:
            m = re.search(pat, text, re.MULTILINE | re.DOTALL)
            if m:
                return m.group(1)
    else:
        m = re.search(r'^\s*hostname\s+([A-Za-z0-9._\-]+)\s*$', text, re.MULTILINE)
        if m:
            return m.group(1)
        if device_type == 'Cisco NX-OS':
            m = re.search(r'^\s*switchname\s+(\S+)', text, re.MULTILINE)
            if m:
                return m.group(1)
    return None

def find_bgp_asns(text: str, device_type: str) -> List[Tuple[str, str]]:
    matches: List[Tuple[str,str]] = []

    # router bgp <asn> (IOS/NX-OS/IOS-XR)
    for m in re.finditer(r'^\s*router\s+bgp\s+(\S+)\s*$', text, re.MULTILINE | re.IGNORECASE):
        asn = normalize_asn(m.group(1))
        if asn:
            matches.append(('router bgp', asn))

    # neighbor <id> local-as <asn> (IOS/NX-OS/XR)
    for m in re.finditer(r'^\s*neighbor\s+(?:' + IP_RE + r'|\S+)\s+local-as\s+(\S+)\s*$', text, re.MULTILINE | re.IGNORECASE):
        asn = normalize_asn(m.group(1))
        if asn:
            matches.append(('neighbor local-as', asn))

    # local-as <asn> (generic within BGP context)
    for m in re.finditer(r'^\s*local-as\s+(\S+)\s*$', text, re.MULTILINE | re.IGNORECASE):
        asn = normalize_asn(m.group(1))
        if asn:
            matches.append(('local-as', asn))

    # FortiGate: config router bgp ... set as <asn> / set local-as <asn>
    if device_type == 'FortiGate' or re.search(r'^\s*config\s+router\s+bgp', text, re.MULTILINE | re.IGNORECASE):
        for block_m in re.finditer(r'^\s*config\s+router\s+bgp\b(.*?)(?:^\s*end\s*$)', text, re.MULTILINE | re.DOTALL | re.IGNORECASE):
            block = block_m.group(1)
            for m in re.finditer(r'^\s*set\s+as\s+(\S+)\s*$', block, re.MULTILINE | re.IGNORECASE):
                asn = normalize_asn(m.group(1))
                if asn:
                    matches.append(('fortigate set as', asn))
            for m in re.finditer(r'^\s*set\s+local-as\s+(\S+)\s*$', block, re.MULTILINE | re.IGNORECASE):
                asn = normalize_asn(m.group(1))
                if asn:
                    matches.append(('fortigate neighbor local-as', asn))

    # Deduplicate
    seen = set()
    uniq: List[Tuple[str,str]] = []
    for ctx, asn in matches:
        key = (ctx, asn)
        if key not in seen:
            seen.add(key)
            uniq.append((ctx, asn))
    return uniq

# ---------------------------
# Scanning logic
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
    return rows  # Note: returns empty list when no ASN found

def main():
    candidates = [f for f in os.listdir('.') if os.path.isfile(f)]
    positive_rows: List[Dict] = []

    for f in sorted(candidates):
        is_text, charset, reason = is_probably_text_file(f)
        if not is_text:
            # Skip silently from CSV (as requested), but print reason to console for awareness
            print(f"Skipped non-text file: {f} ({reason})")
            continue

        try:
            rows = scan_text_file(f, charset)
            # Only add rows if at least one AS number was found
            if rows:
                positive_rows.extend(rows)
        except Exception as e:
            # Do not write errors to CSV per new requirement; just notify on console
            print(f"Error reading/parsing {f}: {e}")

    out = 'bgp_asn_map.csv'
    fieldnames = ['filename', 'device_name', 'device_type', 'matched_context', 'asn']
    with open(out, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in positive_rows:
            writer.writerow(r)

    print(f"CSV rows written (only files with ASNs): {len(positive_rows)}")
    print(f"Output: {out}")

if __name__ == '__main__':
    main()
