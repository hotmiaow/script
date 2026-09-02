#!/usr/bin/env python3
"""
QSearch - Instant CSV & Text Quick Search Application
=====================================================
Zero-dependency instant search engine for CSV and text files using
Python Tkinter GUI / Curses TUI / Interactive CLI REPL + SQLite FTS5 Trigram Engine.

Features:
- Advanced query support: AND / OR / NOT operators (e.g. 'server OR user', 'sw01 AND vlan10')
- Regular expression pattern matching with regex match highlighting
- Matched keyword, regex, and fuzzy pattern highlighting & bolding
- Match percentage formatted in front of lines (e.g. '[90%] ...')
- Column-specific and file-filter syntax (e.g. 'file:vlan')
- Custom directory selection via CLI or GUI
- Large log/text file context window slicing (±50 lines)
- Right-click context menus, clipboard actions, and keyboard navigation
- Direct CLI output in terminal, JSON, or CSV
"""

from __future__ import annotations

import os
import sys
import csv
import json
import time
import datetime
import queue
import sqlite3
import threading
import subprocess
import difflib
import re
import argparse
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Union, Set
import ipaddress



# Windows ANSI terminal & UTF-8 output setup
if sys.platform == "win32":
    try:
        os.system("")  # Enables Virtual Terminal / ANSI colors in Windows cmd & PowerShell
    except Exception:
        pass
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Increase CSV field size limit to max (sys.maxsize overflows the C `long`
# used internally on platforms where long is 32-bit, e.g. Windows — halve
# and retry until a value the platform accepts is found).
_field_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_field_limit)
        break
    except OverflowError:
        _field_limit //= 2
        if _field_limit < 2**20:
            break
    except Exception:
        break

# Try importing Tkinter safely for GUI mode
HAS_TKINTER = False
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

# Try importing curses for TUI mode
HAS_CURSES = False
try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False


# ================= Configuration & Defaults =================

SCRIPT_DIR = Path(__file__).parent.resolve()
DEFAULT_CONTENT_DIR = SCRIPT_DIR / "content"
DEFAULT_DB_PATH = SCRIPT_DIR / "qs_index.db"

# Ensure default content directory exists
DEFAULT_CONTENT_DIR.mkdir(parents=True, exist_ok=True)


# ================= Helper & String Functions =================

def format_timestamp(ts: Optional[float], format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Formats epoch float timestamp into local readable string."""
    if not ts or ts <= 0:
        return "Never"
    try:
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime(format_str)
    except Exception:
        return "Unknown"


def format_relative_time(ts: Optional[float]) -> str:
    """Formats epoch float timestamp into relative 'X mins ago' human-readable string."""
    if not ts or ts <= 0:
        return "Never"
    try:
        diff = max(0, time.time() - ts)
        if diff < 2:
            return "just now"
        if diff < 60:
            return f"{int(diff)}s ago"
        if diff < 3600:
            return f"{int(diff // 60)}m ago"
        if diff < 86400:
            return f"{int(diff // 3600)}h ago"
        return f"{int(diff // 86400)}d ago"
    except Exception:
        return "Unknown"


def _fuzzy_score(query, text):
    """Calculates fuzzy similarity ratio (0-100) between query and text line."""
    if not query or not text:
        return 0
    q = query.lower().strip()
    t = text.lower().strip()

    if q in t:
        return 100

    words = [w for w in re.split(r'[\s|,;:]+', t) if len(w) >= 2]
    best_score = 0
    for w in words:
        ratio = difflib.SequenceMatcher(None, q, w).ratio()
        score = int(ratio * 100)
        if score > best_score:
            best_score = score
    return best_score


def _sqlite_regexp(pattern, text):
    """Custom SQLite function for regular expression matching."""
    if not pattern or not text:
        return 0
    try:
        return 1 if re.search(pattern, text, re.IGNORECASE) else 0
    except Exception:
        return 0


# ================= MAC & IP Address Helpers =================

def is_mac_address(query: str) -> bool:
    """
    Determines if a query string represents a full or partial MAC address
    (4, 6, 8, 10, 12, or 16 hex characters with common separators or standard full MAC).
    Strictly excludes IP addresses and decimal numbers (e.g. 192.147.55).
    """
    if not query:
        return False
    q = query.strip()

    # Reject if dot-separated parts have length 3 (e.g. 192.147.55 is IP octets, not MAC)
    if "." in q:
        parts = [p for p in q.split(".") if p]
        if any(len(p) == 3 for p in parts):
            return False
        if not all(len(p) in (2, 4) for p in parts):
            return False

    # For colons or hyphens, parts must be 2 (IEEE) or 4 (Cisco quad)
    for sep in (":", "-"):
        if sep in q:
            parts = [p for p in q.split(sep) if p]
            if not all(len(p) in (2, 4) for p in parts):
                return False

    # Explicit MAC formats with separators (e.g. '11:11', 'aa:bb:cc', '1111.1111', etc.)
    has_separator = any(sep in q for sep in (":", "-", "."))
    clean = re.sub(r'[:.\-_\s]', '', q)
    if not (len(clean) in (4, 6, 8, 10, 12, 16) and all(c in "0123456789abcdefABCDEF" for c in clean)):
        return False
    # If 12 or 16 chars, it's always a full MAC. If shorter, auto-detect if it has MAC delimiters or even length in (4, 6, 8, 10)
    if len(clean) in (12, 16):
        return True
    return has_separator or len(clean) in (4, 6, 8, 10)


def normalize_mac(query: str) -> Optional[str]:
    """Extracts clean lowercase hex string from full or partial MAC address candidate."""
    if not query:
        return None
    clean = re.sub(r'[:.\-_\s]', '', query.strip()).lower()
    if len(clean) in (4, 6, 8, 10, 12, 16) and all(c in "0123456789abcdef" for c in clean):
        return clean
    return None


def generate_mac_variants(raw_query: str) -> List[str]:
    """
    Generates all standard MAC address notation formats for full or partial MAC addresses:
    - 4 chars (e.g. last 4 'eeff'): eeff, ee:ff, ee-ff, ee.ff, ee ff
    - 6 chars (e.g. 'ddeeff'): dd:ee:ff, dd-ee-ff, dd.ee.ff, dd ee ff, ddeeff, dd.eeff
    - 8 chars (e.g. 'ccddeeff'): ccdd.eeff, cc:dd:ee:ff, cc-dd-ee-ff, cc.dd.ee.ff, cc dd ee ff, ccddeeff
    - 12 chars (full MAC): Cisco . triplets, IEEE : pairs, - pairs, . pairs, spaces, flat hex
    """
    h = normalize_mac(raw_query)
    if not h:
        return [raw_query.strip()]

    raw_variants = []

    if len(h) == 4: # Last 4 characters / 2 octets (e.g. 'eeff' or 'ee:ff')
        raw_variants = [
            h,                                              # eeff (Cisco 4-char chunk / raw)
            f"{h[0:2]}:{h[2:4]}",                           # ee:ff (Colon pair)
            f"{h[0:2]}-{h[2:4]}",                           # ee-ff (Hyphen pair)
            f"{h[0:2]}.{h[2:4]}",                           # ee.ff (Dotted pair)
            f"{h[0:2]} {h[2:4]}",                           # ee ff (Space pair)
            f".{h}",                                        # .eeff (Cisco end of MAC)
        ]
    elif len(h) == 6: # 3 octets / OUI prefix (e.g. 'ddeeff')
        raw_variants = [
            ":".join(h[i:i+2] for i in range(0, 6, 2)),     # dd:ee:ff
            "-".join(h[i:i+2] for i in range(0, 6, 2)),     # dd-ee-ff
            ".".join(h[i:i+2] for i in range(0, 6, 2)),     # dd.ee.ff
            " ".join(h[i:i+2] for i in range(0, 6, 2)),     # dd ee ff
            f"{h[0:2]}.{h[2:6]}",                           # dd.eeff (Cisco suffix)
            f"{h[0:4]}.{h[4:6]}",                           # ddee.ff (Cisco prefix)
            h                                               # ddeeff
        ]
    elif len(h) == 8: # 4 octets (e.g. 'ccddeeff')
        raw_variants = [
            f"{h[0:4]}.{h[4:8]}",                           # ccdd.eeff
            ":".join(h[i:i+2] for i in range(0, 8, 2)),     # cc:dd:ee:ff
            "-".join(h[i:i+2] for i in range(0, 8, 2)),     # cc-dd-ee-ff
            ".".join(h[i:i+2] for i in range(0, 8, 2)),     # cc.dd.ee.ff
            f"{h[0:4]}:{h[4:8]}",                           # ccdd:eeff
            f"{h[0:4]}-{h[4:8]}",                           # ccdd-eeff
            " ".join(h[i:i+2] for i in range(0, 8, 2)),     # cc dd ee ff
            f"{h[0:4]} {h[4:8]}",                           # ccdd eeff
            h                                               # ccddeeff
        ]
    elif len(h) == 10: # 5 octets
        raw_variants = [
            ":".join(h[i:i+2] for i in range(0, 10, 2)),    # bb:cc:dd:ee:ff
            "-".join(h[i:i+2] for i in range(0, 10, 2)),    # bb-cc-dd-ee-ff
            ".".join(h[i:i+2] for i in range(0, 10, 2)),    # bb.cc.dd.ee.ff
            " ".join(h[i:i+2] for i in range(0, 10, 2)),    # bb cc dd ee ff
            h
        ]
    elif len(h) == 12: # Standard 12-char Full MAC
        raw_variants = [
            f"{h[0:4]}.{h[4:8]}.{h[8:12]}",                # 1111.1111.1111
            ":".join(h[i:i+2] for i in range(0, 12, 2)),   # 11:11:11:11:11:11
            ".".join(h[i:i+2] for i in range(0, 12, 2)),   # 11.11.11.11.11.11
            f"{h[0:4]}:{h[4:8]}:{h[8:12]}",                # 1111:1111:1111
            "-".join(h[i:i+2] for i in range(0, 12, 2)),   # 11-11-11-11-11-11
            f"{h[0:4]}-{h[4:8]}-{h[8:12]}",                # 1111-1111-1111
            " ".join(h[i:i+2] for i in range(0, 12, 2)),   # 11 11 11 11 11 11
            f"{h[0:4]} {h[4:8]} {h[8:12]}",                # 1111 1111 1111
            h                                               # 111111111111
        ]
    else: # 16 hex characters (EUI-64)
        raw_variants = [
            ":".join(h[i:i+2] for i in range(0, 16, 2)),
            "-".join(h[i:i+2] for i in range(0, 16, 2)),
            ".".join(h[i:i+4] for i in range(0, 16, 4)),
            h
        ]

    # Deduplicate while preserving order
    seen = set()
    result = []
    for v in raw_variants:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def parse_ip_or_subnet(query: str) -> Optional[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]:
    """
    Parses a string into an IPv4 or IPv6 network object if it is a valid IP or CIDR subnet
    (e.g., '1.0.0.0/8', '192.168.1.0/24', '10.1.1.1').
    """
    if not query:
        return None
    clean = query.strip()
    try:
        return ipaddress.ip_network(clean, strict=False)
    except ValueError:
        return None


def extract_subnets_from_query(query: str, is_ip_mode: bool = False) -> List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]:
    """Extracts all valid CIDR subnets (or IPs if is_ip_mode) from a query string."""
    subnets = []
    if not query:
        return subnets
    clean = re.sub(r'\b(file|f):[^\s]+', '', query, flags=re.IGNORECASE)
    tokens = re.findall(r'"[^"]+"|\S+', clean)
    for tok in tokens:
        t_clean = tok.strip('"\'(),')
        if not t_clean or t_clean.upper() in ("AND", "OR", "NOT", "&&", "||", "|", "&"):
            continue
        if "/" in t_clean or is_ip_mode:
            net = parse_ip_or_subnet(t_clean)
            if net is not None and net not in subnets:
                subnets.append(net)
    return subnets


def is_ip_or_cidr_query(query: str, is_ip_mode: bool = False) -> bool:
    """Checks if query represents or contains at least one valid CIDR subnet (e.g. '1.0.0.0/8', '192.168.1.0/24') or IP."""
    return len(extract_subnets_from_query(query, is_ip_mode=is_ip_mode)) > 0


_IP_CANDIDATE_REGEX = re.compile(
    r'\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:/\d{1,2})?\b|'
    r'(?:::1\b|(?:::|(?:\b[0-9a-fA-F]{1,4}:+)+)(?:[0-9a-fA-F]{1,4}(?::+[0-9a-fA-F]{1,4})*)?(?:/\d{1,3})?\b)'
)

def extract_matching_ips_in_text(target_net: Union[ipaddress.IPv4Network, ipaddress.IPv6Network], text: str) -> List[str]:
    """
    Finds and returns all IP addresses or subnets in the given text line that fall inside target_net.
    """
    if not text:
        return []
    
    matched = []
    candidates = [m.group(0) for m in _IP_CANDIDATE_REGEX.finditer(text)]
    for cand in candidates:
        try:
            if "/" in cand:
                cand_net = ipaddress.ip_network(cand, strict=False)
                if cand_net.version == target_net.version:
                    if cand_net.network_address in target_net and cand_net.broadcast_address in target_net:
                        matched.append(cand)
            else:
                cand_ip = ipaddress.ip_address(cand)
                if cand_ip.version == target_net.version:
                    if cand_ip in target_net:
                        matched.append(cand)
        except ValueError:
            continue
    return matched


def _sqlite_ip_in_network(target_net_str: str, text: str) -> int:
    """Custom SQLite function to check if text contains any IP/subnet within target_net_str."""
    if not target_net_str or not text:
        return 0
    try:
        target_net = ipaddress.ip_network(target_net_str.strip(), strict=False)
        matched = extract_matching_ips_in_text(target_net, text)
        return 1 if matched else 0
    except Exception:
        return 0


def strip_file_filter(raw_query: str) -> Tuple[Optional[str], str]:
    """
    Extracts an inline 'file:name' or 'f:name' filter token from a raw query
    string and returns (file_filter, effective_query) where effective_query
    has the filter token(s) removed. Shared by SearchEngine.search() and any
    UI code that needs to reason about the same query the engine actually
    matched against (e.g. MAC/IP detection for highlighting or hint text).
    """
    if not raw_query:
        return None, ""
    file_filter = None
    cleaned_tokens = []
    for token in raw_query.split():
        if token.lower().startswith("file:") or token.lower().startswith("f:"):
            parts = token.split(":", 1)
            if len(parts) == 2 and parts[1]:
                file_filter = parts[1].strip()
        else:
            cleaned_tokens.append(token)
    return file_filter, " ".join(cleaned_tokens).strip()


def extract_search_keywords(raw_query: str) -> List[str]:
    """
    Extracts individual search tokens/keywords from a query string,
    omitting logical operators like AND, OR, NOT, and file filters.
    """
    if not raw_query:
        return []
    
    # Strip file filter prefixes
    clean_q = re.sub(r'\b(file|f):[^\s]+', '', raw_query, flags=re.IGNORECASE)

    # Extract quoted phrases first
    phrases = re.findall(r'"([^"]+)"', clean_q)
    unquoted = re.sub(r'"[^"]+"', ' ', clean_q)

    # Extract unquoted words, dropping operators and the term(s) excluded by NOT
    tokens = []
    negate_next = False
    for token in re.split(r'[\s|,;]+', unquoted):
        token_clean = token.strip().strip("()").strip()
        if not token_clean:
            continue
        upper = token_clean.upper()
        if upper == "NOT":
            negate_next = True
            continue
        if upper in ("AND", "OR", "&&", "||", "|", "&"):
            negate_next = False
            continue
        if negate_next:
            negate_next = False
            continue
        tokens.append(token_clean)

    all_keywords = phrases + tokens
    return [k for k in all_keywords if len(k) >= 1]


def get_fuzzy_matched_words(query: str, text: str) -> List[str]:
    """Finds the best matching word(s) in text for a fuzzy query."""
    if not query or not text:
        return []
    q_clean = query.lower().strip()
    words = [w for w in re.split(r'[\s|,;:]+', text) if len(w) >= 2]
    matched = []
    best_score = 0
    best_word = None
    for w in words:
        ratio = difflib.SequenceMatcher(None, q_clean, w.lower()).ratio() * 100
        if ratio > best_score:
            best_score = ratio
            best_word = w
    if best_word and best_score >= 50:
        matched.append(best_word)
    return matched


def format_record_multiline(headers, line_text):
    """Formats CSV row fields into separate key-value lines with column names."""
    if " | " in line_text:
        fields = [f.strip() for f in line_text.split(" | ")]
    else:
        fields = [f.strip() for f in line_text.split(",")]

    lines = []
    for idx, val in enumerate(fields):
        if headers and idx < len(headers) and str(headers[idx]).strip():
            col_name = str(headers[idx]).strip()
        else:
            col_name = f"Column {idx + 1}"
        lines.append(f"  • {col_name}: {val}")
    return lines


def open_file_in_default_app(filename, content_dir=DEFAULT_CONTENT_DIR):
    """Opens a file using the operating system's default viewer."""
    if not filename:
        return False

    target_path = Path(filename)
    if not target_path.is_absolute() or not target_path.exists():
        direct = Path(content_dir) / filename
        if direct.exists():
            target_path = direct
        else:
            fallback = Path(content_dir) / os.path.basename(filename)
            if fallback.exists():
                target_path = fallback
            else:
                matches = list(Path(content_dir).rglob(os.path.basename(filename)))
                if matches:
                    target_path = matches[0]

    if not target_path.exists():
        return False

    filepath_str = str(target_path.resolve())
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", filepath_str])
        elif sys.platform == "win32":
            os.startfile(filepath_str)
        else:
            subprocess.Popen(["xdg-open", filepath_str])
        return True
    except Exception as e:
        print(f"[Open Error] {e}", file=sys.stderr)
        return False


def open_containing_folder(filename, content_dir=DEFAULT_CONTENT_DIR):
    """Opens the directory containing the file in file explorer."""
    if not filename:
        return False

    target_path = Path(filename)
    if not target_path.is_absolute() or not target_path.exists():
        direct = Path(content_dir) / filename
        if direct.exists():
            target_path = direct
        else:
            fallback = Path(content_dir) / os.path.basename(filename)
            if fallback.exists():
                target_path = fallback
            else:
                matches = list(Path(content_dir).rglob(os.path.basename(filename)))
                if matches:
                    target_path = matches[0]

    folder = target_path.parent if target_path.exists() else Path(content_dir)
    folder_str = str(folder.resolve())

    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", folder_str])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", folder_str])
        else:
            subprocess.Popen(["xdg-open", folder_str])
        return True
    except Exception as e:
        print(f"[Folder Open Error] {e}", file=sys.stderr)
        return False


def balance_results_by_file(results: List[Tuple[Any, ...]], limit: int = 1000, unique_files: bool = False) -> List[Tuple[Any, ...]]:
    """
    Interleaves search result rows across different files so that all matching files
    are represented in top search results instead of a single file monopolizing all result slots.
    If unique_files is True, only the first/highest-scoring match for each unique file is included.
    """
    if not results:
        return []

    score_groups: Dict[int, List[Tuple[Any, ...]]] = {}
    for r in results:
        score = r[3] if len(r) > 3 else 100
        score_groups.setdefault(score, []).append(r)

    final_results = []
    seen = set()
    seen_files = set()

    for score in sorted(score_groups.keys(), reverse=True):
        group = score_groups[score]
        file_groups: Dict[str, List[Tuple[Any, ...]]] = {}
        for r in group:
            file_groups.setdefault(str(r[0]), []).append(r)

        max_rows = max(len(g) for g in file_groups.values())
        for i in range(max_rows):
            for fname, f_rows in file_groups.items():
                if unique_files and fname in seen_files:
                    continue
                if i < len(f_rows):
                    row_key = (f_rows[i][0], f_rows[i][1])
                    if row_key not in seen:
                        seen.add(row_key)
                        seen_files.add(fname)
                        final_results.append(f_rows[i])
                        if len(final_results) >= limit:
                            return final_results

    return final_results[:limit]


# ================= Database & Search Engine =================

class SearchEngine:
    """Manages SQLite database index, FTS5 trigram queries, boolean parsing, and metadata cache."""

    def __init__(self, db_path=DEFAULT_DB_PATH, content_dir=DEFAULT_CONTENT_DIR):
        self.db_path = str(db_path)
        self.content_dir = Path(content_dir).resolve()
        self.use_fts = True
        self._headers_cache = {}
        self._init_db()
        self.refresh_headers_cache()

    def set_content_dir(self, new_dir):
        """Updates content directory."""
        self.content_dir = Path(new_dir).resolve()
        self.refresh_headers_cache()

    def refresh_headers_cache(self):
        """Loads CSV column headers into memory cache for instant lookup."""
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT file_path, headers FROM file_meta WHERE headers IS NOT NULL;")
            cache = {}
            for fpath, hdrs in cur.fetchall():
                if hdrs:
                    try:
                        rel_name = os.path.relpath(fpath, self.content_dir) if str(fpath).startswith(str(self.content_dir)) else os.path.basename(fpath)
                        parsed = json.loads(hdrs)
                        cache[rel_name] = parsed
                        cache[os.path.basename(fpath)] = parsed
                        cache[fpath] = parsed
                    except Exception:
                        pass
            self._headers_cache = cache
            conn.close()
        except Exception:
            pass

    def get_connection(self):
        """Returns a thread-safe connection to SQLite with registered custom functions."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.create_function("fuzzy_score", 2, _fuzzy_score)
        conn.create_function("regexp", 2, _sqlite_regexp)
        conn.create_function("ip_in_network", 2, _sqlite_ip_in_network)
        return conn

    def _init_db(self):
        """Initializes database schema with FTS5 trigram support or standard fallback."""
        conn = self.get_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS file_meta (
                file_path TEXT PRIMARY KEY,
                mtime REAL,
                size INTEGER,
                row_count INTEGER,
                headers TEXT,
                indexed_at REAL
            );
        """)
        try:
            cur.execute("ALTER TABLE file_meta ADD COLUMN headers TEXT;")
        except sqlite3.OperationalError:
            pass
        try:
            cur.execute("ALTER TABLE file_meta ADD COLUMN indexed_at REAL;")
        except sqlite3.OperationalError:
            pass

        cur.execute("""
            CREATE TABLE IF NOT EXISTS db_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        # Check existing fts_idx definition
        try:
            cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='fts_idx';")
            row = cur.fetchone()
            if row:
                sql_def = row[0].lower()
                if "trigram" not in sql_def or "file_name unindexed" in sql_def:
                    cur.execute("DROP TABLE fts_idx;")
                    cur.execute("DELETE FROM file_meta;")
        except Exception:
            pass

        # Create FTS5 virtual table
        try:
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_idx USING fts5(
                    file_name,
                    row_num UNINDEXED,
                    line_text,
                    tokenize='trigram'
                );
            """)
            self.use_fts = True
        except sqlite3.OperationalError:
            self.use_fts = False
            cur.execute("""
                CREATE TABLE IF NOT EXISTS std_idx (
                    file_name TEXT,
                    row_num INTEGER,
                    line_text TEXT
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_std_text ON std_idx(line_text);")

        conn.commit()
        conn.close()

    def get_file_headers(self, file_name):
        """Retrieves column header names for a CSV file from memory cache or DB."""
        if file_name in self._headers_cache:
            return self._headers_cache[file_name]
        
        base_name = os.path.basename(file_name)
        if base_name in self._headers_cache:
            return self._headers_cache[base_name]

        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT headers FROM file_meta WHERE file_path LIKE ?;", (f"%{file_name}",))
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            try:
                headers = json.loads(row[0])
                self._headers_cache[file_name] = headers
                return headers
            except Exception:
                pass
        return []

    def set_db_meta(self, key: str, value: str):
        """Sets a key-value pair in db_meta."""
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO db_meta (key, value) VALUES (?, ?);", (key, str(value)))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_db_meta(self, key: str, default=None):
        """Gets a value by key from db_meta."""
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT value FROM db_meta WHERE key = ? LIMIT 1;", (key,))
            row = cur.fetchone()
            conn.close()
            return row[0] if row else default
        except Exception:
            return default

    def get_file_info(self, file_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves detailed file metadata (mtime, size, row_count, headers, indexed_at) from file_meta."""
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            base = os.path.basename(file_name)
            cur.execute(
                "SELECT mtime, size, row_count, headers, indexed_at, file_path FROM file_meta WHERE file_path = ? OR file_path LIKE ? OR file_path LIKE ? LIMIT 1;",
                (file_name, f"%{file_name}", f"%{base}")
            )
            row = cur.fetchone()
            conn.close()
            if row:
                headers = []
                if row[3]:
                    try:
                        headers = json.loads(row[3])
                    except Exception:
                        headers = []
                return {
                    "mtime": row[0],
                    "size": row[1],
                    "row_count": row[2],
                    "headers": headers,
                    "indexed_at": row[4],
                    "file_path": row[5]
                }
        except Exception:
            pass
        return None

    def _parse_boolean_query_sql(self, query_str: str, is_mac: bool = False, is_ip: bool = False) -> Tuple[Optional[str], Tuple[Optional[str], List[Any]], List[str], List[Any], bool]:
        """
        Parses query containing 'AND', 'OR', 'NOT', '|', '&', subnets, and MAC tokens into:
        - FTS5 MATCH expression
        - Standard SQL LIKE/ip_in_network WHERE expression
        - List of extracted keywords (for text highlighting)
        - List of extracted CIDR networks (for IP highlighting)
        - has_mac_term boolean
        """
        keywords = extract_search_keywords(query_str)
        extracted_subnets = []
        has_mac_term = False

        # Split into non-empty OR branches
        or_parts = [p.strip() for p in re.split(r'\s+(?:OR|or|\|)\s+', query_str) if p.strip()]

        fts_or_clauses = []
        like_or_clauses = []
        like_params = []

        for or_branch in or_parts:
            # Tokenize while keeping "quoted phrases" intact as a single atomic term
            raw_tokens = re.findall(r'"[^"]+"|\S+', or_branch.strip())

            positive_terms = []
            negative_terms = []
            negate_next = False
            for tok in raw_tokens:
                t_clean = tok.strip('"').strip("'")
                upper = t_clean.upper()
                if upper in ("AND", "&&", "&"):
                    continue
                if upper == "NOT":
                    negate_next = True
                    continue
                if upper == "OR":
                    negate_next = False
                    continue
                if not t_clean or t_clean.lower().startswith(("file:", "f:")):
                    negate_next = False
                    continue
                if negate_next:
                    negative_terms.append(t_clean)
                else:
                    positive_terms.append(t_clean)
                negate_next = False

            if not positive_terms and not negative_terms:
                continue

            branch_fts_pos = []
            branch_fts_neg = []
            branch_like_parts = []

            for t in positive_terms:
                is_subnet_token = ("/" in t or is_ip) and parse_ip_or_subnet(t) is not None
                if is_subnet_token:
                    net = parse_ip_or_subnet(t)
                    if net not in extracted_subnets:
                        extracted_subnets.append(net)
                    # Prefilter for IPv4 to accelerate sqlite evaluation
                    pfx = None
                    if net.version == 4:
                        if net.prefixlen >= 24:
                            pfx = str(net.network_address).rsplit('.', 1)[0] + '.'
                        elif net.prefixlen >= 16:
                            octs = str(net.network_address).split('.')
                            pfx = f"{octs[0]}.{octs[1]}."
                        elif net.prefixlen >= 8:
                            octs = str(net.network_address).split('.')
                            pfx = f"{octs[0]}."

                    if pfx:
                        branch_like_parts.append("(ip_in_network(?, line_text) AND line_text LIKE ?)")
                        like_params.extend([str(net), f"%{pfx}%"])
                        if len(pfx) >= 3:
                            branch_fts_pos.append(f'"{pfx}"')
                    else:
                        branch_like_parts.append("ip_in_network(?, line_text)")
                        like_params.append(str(net))

                elif is_mac and is_mac_address(t):
                    has_mac_term = True
                    variants = generate_mac_variants(t)
                    mac_subclauses = ["(line_text LIKE ? OR file_name LIKE ?)" for _ in variants]
                    branch_like_parts.append("(" + " OR ".join(mac_subclauses) + ")")
                    for v in variants:
                        like_params.extend([f"%{v}%", f"%{v}%"])
                    fts_v = [f'"{v}"' for v in variants if len(v) >= 3]
                    if fts_v:
                        branch_fts_pos.append("(" + " OR ".join(fts_v) + ")")

                else:
                    branch_like_parts.append("(line_text LIKE ? OR file_name LIKE ?)")
                    like_params.extend([f"%{t}%", f"%{t}%"])
                    if len(t) >= 3:
                        branch_fts_pos.append(f'"{t.replace(chr(34), chr(34) * 2)}"')

            for t in negative_terms:
                is_subnet_token = ("/" in t or is_ip) and parse_ip_or_subnet(t) is not None
                if is_subnet_token:
                    net = parse_ip_or_subnet(t)
                    branch_like_parts.append("NOT ip_in_network(?, line_text)")
                    like_params.append(str(net))
                elif is_mac and is_mac_address(t):
                    variants = generate_mac_variants(t)
                    mac_subclauses = ["(line_text LIKE ? OR file_name LIKE ?)" for _ in variants]
                    branch_like_parts.append("NOT (" + " OR ".join(mac_subclauses) + ")")
                    for v in variants:
                        like_params.extend([f"%{v}%", f"%{v}%"])
                else:
                    branch_like_parts.append("NOT (line_text LIKE ? OR file_name LIKE ?)")
                    like_params.extend([f"%{t}%", f"%{t}%"])
                    if len(t) >= 3:
                        branch_fts_neg.append(f'"{t.replace(chr(34), chr(34) * 2)}"')

            if branch_fts_pos:
                branch_fts = " AND ".join(branch_fts_pos)
                for neg in branch_fts_neg:
                    branch_fts += f" NOT {neg}"
                fts_or_clauses.append("(" + branch_fts + ")")

            if branch_like_parts:
                like_or_clauses.append("(" + " AND ".join(branch_like_parts) + ")")

        # Only use FTS if EVERY branch has a valid positive FTS representation;
        # otherwise a partial FTS query would permanently drop the unindexed branch(es).
        fts_query = " OR ".join(fts_or_clauses) if (len(fts_or_clauses) == len(or_parts)) else None
        like_sql = "(" + " OR ".join(like_or_clauses) + ")" if like_or_clauses else None

        return fts_query, (like_sql, like_params), keywords, extracted_subnets, has_mac_term

    def search(self, query_str, limit=1000, file_type="all", is_regex=False, unique_files=False, is_mac=False, is_ip=False):
        """
        Performs multi-stage search across all files:
        - MAC address multi-format search (e.g. '1111.1111.1111', '11:11:11:11:11:11', etc.)
        - IP / CIDR Subnet range containment search (e.g. '1.0.0.0/8', '192.168.1.0/24')
        - Boolean AND / OR / NOT search (e.g. 'server OR user', '1.0.0.0/8 AND server', '10.0.0.0/8 OR 192.168.0.0/16')
        - Regular expression pattern matching
        - File-specific filtering (e.g. 'file:switch')
        - Multi-token LIKE fallback (checking both content and file path)
        - Bounded Fuzzy search fallback
        - Unique files deduplication when unique_files=True
        """
        raw_query = query_str.strip()
        if not raw_query:
            return [], 0.0, "exact"

        start_time = time.perf_counter()
        conn = self.get_connection()
        cur = conn.cursor()

        results = []
        match_type = "exact"

        # Parse inline file filter syntax like 'file:ip_vlan' or 'f:sw'
        file_filter, effective_query = strip_file_filter(raw_query)

        # Build file extension clause
        type_clauses = []
        if file_type == "csv":
            type_clauses.append("(CAST(file_name AS TEXT) LIKE '%.csv' OR CAST(file_name AS TEXT) LIKE '%.CSV')")
        elif file_type == "text":
            type_clauses.append("NOT (CAST(file_name AS TEXT) LIKE '%.csv' OR CAST(file_name AS TEXT) LIKE '%.CSV')")

        if file_filter:
            type_clauses.append(f"CAST(file_name AS TEXT) LIKE '%{file_filter}%'")

        base_filter_sql = (" AND " + " AND ".join(type_clauses)) if type_clauses else ""
        table_name = "fts_idx" if self.use_fts else "std_idx"

        # Determine mode: MAC mode only applies when is_mac is explicitly enabled
        is_mac_mode = bool(is_mac)
        is_ip_mode = bool(is_ip)

        try:
            # Mode A: Regex Search
            if is_regex and effective_query:
                match_type = "regex"
                try:
                    re.compile(effective_query)
                except re.error as e:
                    print(f"[Regex Error] Invalid pattern '{effective_query}': {e}", file=sys.stderr)
                    results = []
                else:
                    try:
                        cur.execute(f"""
                            SELECT file_name, row_num, line_text
                            FROM {table_name}
                            WHERE (regexp(?, line_text) OR regexp(?, file_name)){base_filter_sql}
                            LIMIT ?;
                        """, (effective_query, effective_query, limit * 2))
                        raw_rows = cur.fetchall()
                        results = [(r[0], r[1], r[2], 100) for r in raw_rows]
                    except sqlite3.OperationalError as e:
                        print(f"[Regex Error] {e}", file=sys.stderr)
                        results = []

            # Mode B: Unified Boolean, Multi-Token, Subnet / CIDR & MAC Search
            elif effective_query:
                fts_expr, (like_sql, like_params), keywords, extracted_subnets, has_mac_term = self._parse_boolean_query_sql(
                    effective_query, is_mac=is_mac_mode, is_ip=is_ip_mode
                )

                if extracted_subnets:
                    match_type = "ip_subnet"
                elif is_mac_mode or has_mac_term:
                    match_type = "mac"
                else:
                    match_type = "exact"

                is_phrase = effective_query.startswith('"') and effective_query.endswith('"') and len(effective_query) >= 2

                # Stage 1: FTS5 Trigram Indexed Search with Subquery Constraint Verification
                if self.use_fts and fts_expr:
                    try:
                        if like_sql:
                            sql_stmt = f"""
                                SELECT file_name, row_num, line_text
                                FROM fts_idx
                                WHERE rowid IN (SELECT rowid FROM fts_idx WHERE fts_idx MATCH ?)
                                  AND {like_sql}{base_filter_sql}
                                LIMIT ?;
                            """
                            cur.execute(sql_stmt, (fts_expr, *like_params, limit * 2))
                        else:
                            cur.execute(f"""
                                SELECT file_name, row_num, line_text
                                FROM fts_idx
                                WHERE fts_idx MATCH ?{base_filter_sql}
                                LIMIT ?;
                            """, (fts_expr, limit * 2))
                        raw = cur.fetchall()
                        results = [(r[0], r[1], r[2], 100) for r in raw]
                    except sqlite3.Error:
                        results = []

                # Stage 2: Fast LIKE & ip_in_network Fallback / Supplemental Search
                if (not results or len(results) < limit) and like_sql:
                    try:
                        sql_stmt = f"SELECT file_name, row_num, line_text FROM {table_name} WHERE {like_sql}{base_filter_sql} LIMIT ?;"
                        cur.execute(sql_stmt, (*like_params, limit * 2))
                        raw_like = cur.fetchall()
                        existing_keys = {(r[0], r[1]) for r in results}
                        for r in raw_like:
                            if (r[0], r[1]) not in existing_keys:
                                results.append((r[0], r[1], r[2], 100))
                                existing_keys.add((r[0], r[1]))
                    except sqlite3.Error:
                        pass

                # Stage 3: Bounded Fuzzy Search Fallback (only for single word queries >= 4 chars without boolean operators/subnets)
                has_boolean_ops = any(op in effective_query.upper() for op in ("OR", "AND", "NOT", "|", "&"))
                if not results and len(keywords) == 1 and len(keywords[0]) >= 4 and not is_phrase and not has_boolean_ops and not extracted_subnets and not is_mac_mode:
                    match_type = "fuzzy"
                    cur.execute(f"""
                        SELECT file_name, row_num, line_text, score FROM (
                            SELECT file_name, row_num, line_text, max(fuzzy_score(?, line_text), fuzzy_score(?, file_name)) as score
                            FROM {table_name}
                            LIMIT 5000
                        )
                        WHERE score >= 60{base_filter_sql}
                        ORDER BY score DESC
                        LIMIT ?;
                    """, (keywords[0], keywords[0], limit * 2))
                    fuzzy_raw = cur.fetchall()
                    results = [(r[0], r[1], r[2], int(r[3])) for r in fuzzy_raw]

            # If only file filter was provided with no keywords
            elif file_filter:
                cur.execute(f"""
                    SELECT file_name, row_num, line_text
                    FROM {table_name}
                    WHERE 1=1{base_filter_sql}
                    LIMIT ?;
                """, (limit * 2,))
                raw = cur.fetchall()
                results = [(r[0], r[1], r[2], 100) for r in raw]

        except sqlite3.Error as e:
            print(f"[Search Engine Error] {e}", file=sys.stderr)
            results = []
        finally:
            conn.close()

        balanced_results = balance_results_by_file(results, limit=limit, unique_files=unique_files)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return balanced_results, elapsed_ms, match_type

    def get_stats(self):
        """Returns total files, total rows, last db update timestamp, and last scan timestamp."""
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), COALESCE(SUM(row_count), 0), MAX(indexed_at), MAX(mtime) FROM file_meta;")
            row = cur.fetchone()
            file_cnt = row[0] if row else 0
            row_cnt = row[1] if row else 0
            last_db_update = row[2] if (row and row[2]) else (row[3] if (row and row[3]) else None)

            cur.execute("SELECT value FROM db_meta WHERE key = 'last_scan_time' LIMIT 1;")
            s_row = cur.fetchone()
            last_scan_ts = float(s_row[0]) if s_row and s_row[0] else None

            conn.close()
            return file_cnt, row_cnt, last_db_update, last_scan_ts
        except Exception:
            return 0, 0, None, None


# ================= Background Indexer Service =================

EXCLUDED_BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tiff", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz", ".tgz",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".db", ".sqlite", ".sqlite3",
    ".pyc", ".pyo", ".o", ".obj", ".a", ".lib", ".class", ".jar", ".war", ".ear",
    ".mp3", ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wav", ".aac", ".ogg", ".flac",
    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".iso", ".dmg", ".pkg", ".deb", ".rpm"
}

EXCLUDED_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock", "cargo.lock", "gemfile.lock"
}
EXCLUDED_SUFFIXES = (
    ".min.js", ".min.css", ".map", ".bundle.js"
)
EXCLUDED_DIRS = {
    ".git", ".idea", ".vscode", "__pycache__", "node_modules", "dist", "build",
    ".gemini", ".venv", "venv", "env", ".next", ".cache", ".pytest_cache"
}

MAX_LINE_LENGTH = 10000


def is_text_file(filepath):
    """Determines whether a file is text-based by checking extension and content bytes."""
    path = Path(filepath)
    name_lower = path.name.lower()
    if name_lower in EXCLUDED_FILENAMES or name_lower.endswith(EXCLUDED_SUFFIXES):
        return False

    ext = path.suffix.lower()
    if ext in EXCLUDED_BINARY_EXTENSIONS:
        return False

    try:
        if path.stat().st_size == 0:
            return True
        with open(path, "rb") as f:
            chunk = f.read(2048)
            if chunk.startswith((b'\xff\xfe', b'\xfe\xff')):
                return True
            if b"\x00" in chunk:
                try:
                    chunk.decode("utf-16")
                    return True
                except Exception:
                    return False
            try:
                chunk.decode("utf-8")
                return True
            except UnicodeDecodeError:
                try:
                    chunk.decode("latin-1")
                    return True
                except Exception:
                    return False
    except Exception:
        return False


class BackgroundIndexer(threading.Thread):
    """Background worker thread to continuously track and index CSV and text files with adaptive throttling."""

    def __init__(self, engine, content_dir=DEFAULT_CONTENT_DIR, status_callback=None, poll_interval=2.0):
        super().__init__(daemon=True)
        self.engine = engine
        self.content_dir = Path(content_dir).resolve()
        self.status_callback = status_callback
        self.poll_interval = poll_interval
        self._running = True
        self._sync_lock = threading.Lock()
        self.is_indexing = False
        self.total_files = 0
        self.files_left = 0
        self.percent = 100
        self.last_scan_time = None
        self.last_db_update_time = None

    def update_content_dir(self, new_dir):
        """Changes watched content folder."""
        self.content_dir = Path(new_dir).resolve()
        self.engine.set_content_dir(self.content_dir)

    def run(self):
        while self._running:
            try:
                has_changes = self.sync_content_directory()
                sleep_time = self.poll_interval if has_changes else min(self.poll_interval * 2.5, 6.0)
            except Exception as e:
                print(f"[BackgroundIndexer Error] {e}", file=sys.stderr)
                sleep_time = self.poll_interval
            time.sleep(sleep_time)

    def sync_content_directory(self):
        """Checks for new, updated, or removed text files with directory pruning."""
        with self._sync_lock:
            conn = self.engine.get_connection()
            cur = conn.cursor()

            cur.execute("SELECT file_path, round(mtime, 3), size FROM file_meta;")
            db_files = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

            disk_files = {}
            if self.content_dir.exists():
                for root, dirs, files in os.walk(str(self.content_dir)):
                    # Prune hidden and build/cache folders early
                    dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
                    for fname in files:
                        if fname.startswith(".") or fname in EXCLUDED_FILENAMES:
                            continue
                        full_path = Path(root) / fname
                        if is_text_file(full_path):
                            try:
                                stat = full_path.stat()
                                disk_files[str(full_path)] = (round(stat.st_mtime, 3), stat.st_size)
                            except OSError:
                                continue

            # Only remove files that belong to the watched directory scope
            content_dir_str = str(self.content_dir)
            removed_files = [
                rfile for rfile in db_files
                if (str(rfile) == content_dir_str or str(rfile).startswith(content_dir_str + os.sep))
                and rfile not in disk_files
            ]
            for rfile in removed_files:
                rel_name = os.path.relpath(rfile, self.content_dir) if str(rfile).startswith(str(self.content_dir)) else os.path.basename(rfile)
                cur.execute("DELETE FROM file_meta WHERE file_path = ?;", (rfile,))
                if self.engine.use_fts:
                    cur.execute("DELETE FROM fts_idx WHERE file_name = ? OR file_name = ?;", (rel_name, os.path.basename(rfile)))
                else:
                    cur.execute("DELETE FROM std_idx WHERE file_name = ? OR file_name = ?;", (rel_name, os.path.basename(rfile)))
            if removed_files:
                conn.commit()

            changed_files = [
                filepath for filepath, (mtime, size) in disk_files.items()
                if filepath not in db_files or db_files[filepath] != (mtime, size)
            ]

            has_changes = bool(changed_files or removed_files)
            now_ts = time.time()
            self.last_scan_time = now_ts
            self.engine.set_db_meta("last_scan_time", str(now_ts))

            if has_changes:
                self.last_db_update_time = now_ts
                self.engine.set_db_meta("last_db_update_time", str(now_ts))
                total_changed = len(changed_files)
                self.total_files = total_changed
                self.files_left = total_changed
                self.is_indexing = True if total_changed > 0 else False
                self.percent = 0 if total_changed > 0 else 100

                for idx, filepath in enumerate(changed_files, start=1):
                    self.index_single_file(conn, filepath)
                    self.files_left = total_changed - idx
                    self.percent = int((idx / total_changed) * 100)

                    if self.status_callback and (idx % 10 == 0 or idx == total_changed):
                        try:
                            self.status_callback(
                                len(disk_files), 0, self.total_files, self.files_left, self.percent, self.is_indexing,
                                self.last_scan_time, self.last_db_update_time
                            )
                        except Exception:
                            pass

                if self.engine.use_fts:
                    try:
                        cur.execute("INSERT INTO fts_idx(fts_idx) VALUES('optimize');")
                        conn.commit()
                    except Exception:
                        pass
                cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")

                self.is_indexing = False
                self.files_left = 0
                self.percent = 100

                # Refresh in-memory column headers cache for newly indexed CSVs
                self.engine.refresh_headers_cache()

                file_cnt, row_cnt, l_update, l_scan = self.engine.get_stats()
                if self.status_callback:
                    try:
                        self.status_callback(
                            file_cnt, row_cnt, self.total_files, 0, 100, False,
                            self.last_scan_time, self.last_db_update_time or l_update
                        )
                    except Exception:
                        pass
            else:
                if self.status_callback:
                    file_cnt, row_cnt, l_update, l_scan = self.engine.get_stats()
                    try:
                        self.status_callback(
                            file_cnt, row_cnt, 0, 0, 100, False,
                            self.last_scan_time, l_update
                        )
                    except Exception:
                        pass

            conn.close()
            return has_changes

    def index_single_file(self, conn, filepath):
        """Reads and indexes a single text file cleanly into SQLite."""
        rel_name = os.path.relpath(filepath, self.content_dir) if str(filepath).startswith(str(self.content_dir)) else os.path.basename(filepath)
        stat = os.stat(filepath)
        ext = os.path.splitext(filepath)[1].lower()

        parsed_batch = []
        batch_size = 5000
        total_rows = 0
        headers_json = None

        encodings_to_try = ["utf-8-sig", "utf-8", "utf-16", "latin-1"]
        read_ok = False
        last_error = None
        for enc in encodings_to_try:
            parsed_batch.clear()
            total_rows = 0
            headers_json = None
            try:
                # newline='' is required for csv.reader to correctly handle
                # embedded newlines / CRLF sequences inside quoted fields;
                # harmless for the plain-text branch since lines are
                # .strip()'d immediately after.
                with open(filepath, "r", encoding=enc, newline="", errors="replace") as f:
                    if ext == ".csv":
                        reader = csv.reader(f)
                        for line_idx, row in enumerate(reader, start=1):
                            if line_idx == 1:
                                headers_json = json.dumps(row)
                            line_str = " | ".join(row).strip()
                            if line_str:
                                if len(line_str) > MAX_LINE_LENGTH:
                                    line_str = line_str[:MAX_LINE_LENGTH]
                                parsed_batch.append((rel_name, line_idx, line_str))
                                total_rows += 1
                    else:
                        for line_idx, line in enumerate(f, start=1):
                            line_str = line.strip()
                            if line_str:
                                if len(line_str) > MAX_LINE_LENGTH:
                                    line_str = line_str[:MAX_LINE_LENGTH]
                                parsed_batch.append((rel_name, line_idx, line_str))
                                total_rows += 1
                read_ok = True
                if parsed_batch or total_rows == 0:
                    break
            except Exception as e:
                last_error = e
                continue

        if not read_ok:
            print(f"[Indexer Error] Failed to read {filepath}: {last_error}", file=sys.stderr)
            return

        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM file_meta WHERE file_path = ?;", (filepath,))
            if self.engine.use_fts:
                cur.execute("DELETE FROM fts_idx WHERE file_name = ? OR file_name = ?;", (rel_name, os.path.basename(filepath)))
            else:
                cur.execute("DELETE FROM std_idx WHERE file_name = ? OR file_name = ?;", (rel_name, os.path.basename(filepath)))

            for i in range(0, len(parsed_batch), batch_size):
                chunk = parsed_batch[i:i + batch_size]
                if self.engine.use_fts:
                    cur.executemany("INSERT INTO fts_idx (file_name, row_num, line_text) VALUES (?, ?, ?);", chunk)
                else:
                    cur.executemany("INSERT INTO std_idx (file_name, row_num, line_text) VALUES (?, ?, ?);", chunk)

            cur.execute(
                "INSERT OR REPLACE INTO file_meta (file_path, mtime, size, row_count, headers, indexed_at) VALUES (?, ?, ?, ?, ?, ?);",
                (filepath, round(stat.st_mtime, 3), stat.st_size, total_rows, headers_json, time.time())
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[Indexer DB Error] Failed to update DB for {filepath}: {e}", file=sys.stderr)





# ================= GUI Mode (Tkinter) =================

if HAS_TKINTER:
    class ToolTip:
        """Provides lightweight hover tooltip hints on Tkinter widgets."""

        def __init__(self, widget, text, delay=350):
            self.widget = widget
            self.text = text
            self.delay = delay
            self.tip_window = None
            self.id = None
            self.widget.bind("<Enter>", self.schedule_tip)
            self.widget.bind("<Leave>", self.hide_tip)
            self.widget.bind("<ButtonPress>", self.hide_tip)

        def schedule_tip(self, event=None):
            self.unschedule()
            self.id = self.widget.after(self.delay, self.show_tip)

        def unschedule(self):
            if self.id:
                self.widget.after_cancel(self.id)
                self.id = None

        def show_tip(self, event=None):
            if self.tip_window or not self.text:
                return
            x = self.widget.winfo_rootx() + 15
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            try:
                tw.wm_attributes("-topmost", True)
            except Exception:
                pass
            label = tk.Label(
                tw,
                text=self.text,
                justify="left",
                background="#1E293B",
                foreground="#F8FAFC",
                relief="flat",
                font=("Helvetica", 9),
                padx=8,
                pady=4,
                borderwidth=0
            )
            label.pack()

        def hide_tip(self, event=None):
            self.unschedule()
            if self.tip_window:
                self.tip_window.destroy()
                self.tip_window = None


    class QSearchGUIApp:
        """Tkinter Application for Instant Search with Rich UI Hints and Guides."""

        def __init__(self, root, initial_dir=DEFAULT_CONTENT_DIR):
            self.root = root
            self.root.title("QSearch - Instant CSV & Text Search Engine")
            self.root.geometry("1020x690")
            self.root.minsize(760, 480)

            self.content_dir = Path(initial_dir).resolve()
            self.engine = SearchEngine(content_dir=self.content_dir)

            self._debounce_job = None
            self._msg_queue = queue.Queue()
            self._current_results = []
            self._search_counter = 0
            self._search_lock = threading.Lock()
            self._active_file_path = None
            self._active_match_rnum = None
            self._active_match_type = "exact"

            self._setup_ui()
            self._poll_queue()
            self.root.after(50, self._setup_indexer)

        def _setup_ui(self):
            style = ttk.Style()
            try:
                if "clam" in style.theme_names():
                    style.theme_use("clam")
            except Exception:
                pass

            # Top Toolbar Frame
            top_bar = ttk.Frame(self.root, padding=(10, 8))
            top_bar.pack(side="top", fill="x")

            # Folder selection bar
            folder_frame = ttk.Frame(top_bar)
            folder_frame.pack(fill="x", pady=(0, 6))

            ttk.Label(folder_frame, text="📁 Directory:", font=("Helvetica", 9, "bold")).pack(side="left")
            self.lbl_folder_path = ttk.Label(folder_frame, text=str(self.content_dir), font=("Helvetica", 9), foreground="#1E293B")
            self.lbl_folder_path.pack(side="left", padx=(5, 8))
            ToolTip(self.lbl_folder_path, f"Currently watched root directory:\n{self.content_dir}")

            btn_browse_dir = ttk.Button(folder_frame, text="Browse Folder...", command=self._on_browse_directory)
            btn_browse_dir.pack(side="left")
            ToolTip(btn_browse_dir, "Choose a custom directory on your disk to index and search")

            btn_open_folder = ttk.Button(folder_frame, text="Open Folder ↗", command=lambda: open_containing_folder(str(self.content_dir)))
            btn_open_folder.pack(side="left", padx=(4, 0))
            ToolTip(btn_open_folder, "Open this directory in macOS Finder / File Explorer")

            btn_help = ttk.Button(folder_frame, text="❓ Help & Shortcuts (F1)", command=self._show_help_dialog)
            btn_help.pack(side="right", padx=(4, 0))
            ToolTip(btn_help, "Open complete search syntax cheat sheet and keyboard shortcuts guide [F1]")

            btn_save = ttk.Button(folder_frame, text="Save Results (.csv) 💾", command=self._save_results_to_csv)
            btn_save.pack(side="right")
            ToolTip(btn_save, "Export all current search results to a .CSV spreadsheet")

            # Search row
            search_row = ttk.Frame(top_bar)
            search_row.pack(fill="x", pady=(0, 4))

            lbl_search = ttk.Label(search_row, text="🔍 Search:", font=("Helvetica", 11, "bold"))
            lbl_search.pack(side="left", padx=(0, 6))

            self.search_var = tk.StringVar()
            self.search_entry = ttk.Entry(search_row, textvariable=self.search_var, font=("Helvetica", 12))
            self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.search_entry.focus_set()
            self.search_entry.bind("<KeyRelease>", self._on_key_release)
            self.search_entry.bind("<Down>", self._on_search_down_arrow)
            ToolTip(self.search_entry, "Type keywords to search. Supports 'AND', 'OR', exact \"quotes\", 'file:name' filters, or Regex. Press Ctrl+F / Cmd+F to focus.")

            # Regex toggle
            self.regex_var = tk.BooleanVar(value=False)
            regex_cb = ttk.Checkbutton(search_row, text="Regex Mode", variable=self.regex_var, command=self._on_regex_toggle)
            regex_cb.pack(side="left", padx=(0, 6))
            ToolTip(regex_cb, "Enable regular expression pattern matching (e.g. ^10\\.\\d+\\.\\d+ or (error|fail)) [Ctrl+R]")

            # MAC Mode toggle
            self.mac_var = tk.BooleanVar(value=False)
            mac_cb = ttk.Checkbutton(search_row, text="🏷️ MAC Mode", variable=self.mac_var, command=self._on_mac_toggle)
            mac_cb.pack(side="left", padx=(0, 6))
            ToolTip(mac_cb, "Enable dedicated MAC search mode: expands MAC address (full or last 4/6/8 characters) across all 9 notation formats (Cisco, colon, hyphen, dot, etc.) [Ctrl+M]")

            # Unique file toggle
            self.unique_var = tk.BooleanVar(value=False)
            unique_cb = ttk.Checkbutton(search_row, text="1 Match/File", variable=self.unique_var, command=self._perform_search)
            unique_cb.pack(side="left", padx=(0, 8))
            ToolTip(unique_cb, "Show each unique file only once in search results, even if multiple lines match in that file [Ctrl+U]")

            # Filter mode
            self.filter_var = tk.StringVar(value="All Indexed Files")
            self.filter_cb = ttk.Combobox(
                search_row,
                textvariable=self.filter_var,
                values=["All Indexed Files", "CSV Files Only", "Text Files Only"],
                state="readonly",
                width=15
            )
            self.filter_cb.pack(side="left", padx=(0, 6))
            self.filter_cb.bind("<<ComboboxSelected>>", lambda e: self._perform_search())
            ToolTip(self.filter_cb, "Filter search results by file type (CSV tables, non-CSV text/logs, or all files)")

            btn_clear = ttk.Button(search_row, text="Clear", command=self._clear_search)
            btn_clear.pack(side="left")
            ToolTip(btn_clear, "Clear current search query and reset view [Esc]")

            # Quick Syntax & Hints Toolbar
            hints_bar = ttk.Frame(top_bar)
            hints_bar.pack(fill="x", pady=(2, 0))

            ttk.Label(hints_bar, text="💡 Quick Syntax:", font=("Helvetica", 8, "bold"), foreground="#475569").pack(side="left", padx=(0, 4))

            def insert_syntax_sample(template):
                cur = self.search_var.get().strip()
                new_val = f"{cur} {template}".strip() if cur else template
                self.search_var.set(new_val)
                self.search_entry.focus_set()
                self.search_entry.icursor(tk.END)
                self._perform_search()

            # Syntax chip buttons
            btn_chip_and = ttk.Button(hints_bar, text="AND", width=5, command=lambda: insert_syntax_sample("AND "))
            btn_chip_and.pack(side="left", padx=2)
            ToolTip(btn_chip_and, "Click to append AND operator: requires both keywords (e.g. 'server AND prod')")

            btn_chip_or = ttk.Button(hints_bar, text="OR", width=4, command=lambda: insert_syntax_sample("OR "))
            btn_chip_or.pack(side="left", padx=2)
            ToolTip(btn_chip_or, "Click to append OR operator: matches either keyword (e.g. 'switch OR router')")

            btn_chip_quote = ttk.Button(hints_bar, text='"Phrase"', width=8, command=lambda: insert_syntax_sample('"exact phrase"'))
            btn_chip_quote.pack(side="left", padx=2)
            ToolTip(btn_chip_quote, 'Click to insert exact phrase quotes: matches word sequence verbatim (e.g. "Vlan 100")')

            btn_chip_ip = ttk.Button(hints_bar, text="🌐 Subnet", width=9, command=lambda: insert_syntax_sample("1.0.0.0/8"))
            btn_chip_ip.pack(side="left", padx=2)
            ToolTip(btn_chip_ip, "Click to insert IP Subnet/CIDR search: matches any IP or subnet inside the range (e.g. '1.0.0.0/8' or '192.168.1.0/24')")

            btn_chip_mac = ttk.Button(hints_bar, text="🏷️ MAC Mode", width=11, command=self._toggle_mac_mode)
            btn_chip_mac.pack(side="left", padx=2)
            ToolTip(btn_chip_mac, "Click to toggle dedicated MAC Address search mode on/off [Ctrl+M]")

            btn_chip_file = ttk.Button(hints_bar, text="file:filter", width=9, command=lambda: insert_syntax_sample("file:log"))
            btn_chip_file.pack(side="left", padx=2)
            ToolTip(btn_chip_file, "Click to insert file filter: restricts results to files matching pattern (e.g. 'file:inventory')")

            btn_chip_regex = ttk.Button(hints_bar, text=".* Regex", width=8, command=self._toggle_regex_mode)
            btn_chip_regex.pack(side="left", padx=2)
            ToolTip(btn_chip_regex, "Click to toggle Regex Mode on/off [Ctrl+R]")

            btn_chip_unique = ttk.Button(hints_bar, text="📄 Unique Files", width=12, command=self._toggle_unique_mode)
            btn_chip_unique.pack(side="left", padx=2)
            ToolTip(btn_chip_unique, "Click to toggle Unique Files mode (show each matching file only once) [Ctrl+U]")

            lbl_hint_guide = ttk.Label(
                hints_bar,
                text="Press [F1] for Cheat Sheet  •  [Ctrl/Cmd+F] Focus  •  [↑/↓] Navigate  •  [Enter] Open File  •  [Esc] Clear",
                font=("Helvetica", 8),
                foreground="#64748B"
            )
            lbl_hint_guide.pack(side="right")

            # Main Split PanedWindow
            self.paned = ttk.PanedWindow(self.root, orient="vertical")
            self.paned.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 4))

            # Top Pane: Master Results Table
            table_frame = ttk.Frame(self.paned)
            self.paned.add(table_frame, weight=3)

            columns = ("file", "row", "content")
            self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

            self.tree.heading("file", text="File Path (Double-click to open)")
            self.tree.heading("row", text="Row #")
            self.tree.heading("content", text="Matched Content (Score In Front)")

            self.tree.column("file", width=190, minwidth=110, anchor="w")
            self.tree.column("row", width=65, minwidth=50, anchor="center")
            self.tree.column("content", width=700, minwidth=300, anchor="w")

            scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=scrollbar.set)

            self.tree.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            # Bottom Pane: Detail View Panel
            detail_frame = ttk.LabelFrame(self.paned, text=" 📄 Record Breakdown & Context Window (Highlighted & Bolded) ", padding=8)
            self.paned.add(detail_frame, weight=2)

            detail_top = ttk.Frame(detail_frame)
            detail_top.pack(fill="x", pady=(0, 4))

            self.lbl_detail_header = ttk.Label(detail_top, text="Select a record above to view highlighted breakdown", font=("Helvetica", 10, "bold"))
            self.lbl_detail_header.pack(side="left")

            self.btn_load_full = ttk.Button(detail_top, text="Load Full File", command=self._load_full_text_file)
            self.btn_load_full.pack(side="right", padx=(4, 0))
            self.btn_load_full.pack_forget()
            ToolTip(self.btn_load_full, "Load the entire text file (default shows ±50 lines context slice)")

            btn_copy_detail = ttk.Button(detail_top, text="Copy All Fields", command=self._copy_detail_text)
            btn_copy_detail.pack(side="right")
            ToolTip(btn_copy_detail, "Copy formatted breakdown text to clipboard")

            txt_scroll = ttk.Scrollbar(detail_frame, orient="vertical")
            self.txt_detail = tk.Text(detail_frame, height=8, font=("Courier", 11), wrap="word", yscrollcommand=txt_scroll.set, bd=1, relief="solid")
            txt_scroll.config(command=self.txt_detail.yview)

            # Highlighting and bold tags
            self.txt_detail.tag_config("match_line", background="#FFF3CD", font=("Courier", 11, "bold"))
            self.txt_detail.tag_config("match_query", background="#FFD54F", foreground="#000000", font=("Courier", 11, "bold"))
            self.txt_detail.tag_config("fuzzy_match", background="#FFAB40", foreground="#000000", font=("Courier", 11, "bold"))
            self.txt_detail.tag_config("regex_match", background="#80D8FF", foreground="#000000", font=("Courier", 11, "bold"))

            # Help & guide formatting tags
            self.txt_detail.tag_config("guide_h1", font=("Helvetica", 12, "bold"), foreground="#0F172A")
            self.txt_detail.tag_config("guide_h2", font=("Helvetica", 10, "bold"), foreground="#1E293B")
            self.txt_detail.tag_config("guide_code", font=("Courier", 10, "bold"), background="#E2E8F0", foreground="#0F172A")
            self.txt_detail.tag_config("guide_tag", font=("Helvetica", 9, "bold"), background="#DBEAFE", foreground="#1E40AF")
            self.txt_detail.tag_config("guide_dim", font=("Helvetica", 9), foreground="#64748B")
            self.txt_detail.tag_config("guide_tip", font=("Helvetica", 9, "italic"), foreground="#047857")

            self.txt_detail.pack(side="left", fill="both", expand=True)
            txt_scroll.pack(side="right", fill="y")

            # Show initial welcome guide in detail panel
            self._render_welcome_guide()

            # Bindings & Shortcuts
            self.tree.bind("<Double-1>", self._on_row_double_click)
            self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
            self.tree.bind("<Return>", self._on_enter_pressed)
            self.tree.bind("<Escape>", self._on_escape_pressed)
            self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
            self.tree.bind("<Control-c>", lambda e: self._copy_selected_row())
            self.tree.bind("<Command-c>", lambda e: self._copy_selected_row())
            self.tree.bind("<Up>", self._on_tree_up_arrow)

            # Global Shortcuts
            self.root.bind("<Control-f>", lambda e: self._focus_search())
            self.root.bind("<Command-f>", lambda e: self._focus_search())
            self.root.bind("<Control-m>", lambda e: self._toggle_mac_mode())
            self.root.bind("<Command-m>", lambda e: self._toggle_mac_mode())
            self.root.bind("<Control-u>", lambda e: self._toggle_unique_mode())
            self.root.bind("<Command-u>", lambda e: self._toggle_unique_mode())
            self.root.bind("<F1>", lambda e: self._show_help_dialog())
            self.root.bind("<Control-h>", lambda e: self._show_help_dialog())
            self.root.bind("<Command-h>", lambda e: self._show_help_dialog())
            self.root.bind("<Escape>", self._on_escape_pressed)

            # Right-click context menu
            self._create_context_menu()

            # Quick Shortcuts Strip
            shortcuts_strip = ttk.Frame(self.root, padding=(8, 2))
            shortcuts_strip.pack(side="bottom", fill="x")
            lbl_strip = ttk.Label(
                shortcuts_strip,
                text="⌨️  [Ctrl/Cmd+F] Search   [Ctrl/Cmd+M] MAC Mode   [Ctrl/Cmd+U] 1 Match/File   [↑/↓] Navigate   [Enter] Open File   [Ctrl/Cmd+C] Copy Row   [Esc] Clear   [F1] Help Guide",
                font=("Helvetica", 8),
                foreground="#475569"
            )
            lbl_strip.pack(side="left")

            # Status bar with Real-Time Dynamic Action Colors
            self.status_frame = tk.Frame(self.root, bg="#F1F5F9", pady=4, padx=10, relief="solid", bd=1, highlightthickness=1, highlightbackground="#CBD5E1")
            self.status_frame.pack(side="bottom", fill="x")

            self.lbl_status = tk.Label(
                self.status_frame,
                text="🔍 Ready | Type keywords, MAC address (full/last 4), or Subnet (1.0.0.0/8) to search",
                font=("Helvetica", 9, "bold"),
                bg="#F1F5F9",
                fg="#475569"
            )
            self.lbl_status.pack(side="left", padx=5)

            self.lbl_index_stats = tk.Label(
                self.status_frame,
                text="Index: 0 files (0 rows)",
                font=("Helvetica", 9),
                bg="#F1F5F9",
                fg="#64748B"
            )
            self.lbl_index_stats.pack(side="right", padx=5)

        def _on_regex_toggle(self):
            """Ensures mutually clean toggling for regex mode."""
            if self.regex_var.get():
                self.mac_var.set(False)
            self._perform_search()

        def _on_mac_toggle(self):
            """Ensures mutually clean toggling for MAC search mode."""
            if self.mac_var.get():
                self.regex_var.set(False)
            self._perform_search()

        def _toggle_mac_mode(self):
            """Toggles MAC search mode on/off."""
            self.mac_var.set(not self.mac_var.get())
            self._on_mac_toggle()

        def _toggle_regex_mode(self):
            """Toggles regex mode checkbox and re-executes search."""
            self.regex_var.set(not self.regex_var.get())
            self._on_regex_toggle()

        def _toggle_unique_mode(self):
            """Toggles unique file mode checkbox and re-executes search."""
            self.unique_var.set(not self.unique_var.get())
            self._perform_search()

        def _render_welcome_guide(self):
            """Renders a formatted welcome & syntax cheat sheet in the detail text widget."""
            self.lbl_detail_header.config(text="💡 Quick Start & Search Syntax Guide")
            self.btn_load_full.pack_forget()

            self.txt_detail.config(state="normal")
            self.txt_detail.delete("1.0", tk.END)

            self.txt_detail.insert(tk.END, "🔍 Welcome to QSearch Instant Search Engine\n", "guide_h1")
            self.txt_detail.insert(tk.END, "Zero-delay trigram index search for CSV spreadsheets and plain text logs.\n\n", "guide_dim")

            self.txt_detail.insert(tk.END, "Query Syntax Examples:\n", "guide_h2")

            self.txt_detail.insert(tk.END, "  • ")
            self.txt_detail.insert(tk.END, "IP / Subnet:    ", "guide_tag")
            self.txt_detail.insert(tk.END, "  1.0.0.0/8  or  192.168.1.0/24", "guide_code")
            self.txt_detail.insert(tk.END, "  ➔ Matches all IP addresses / subnets contained inside the range\n")

            self.txt_detail.insert(tk.END, "  • ")
            self.txt_detail.insert(tk.END, "MAC Address:    ", "guide_tag")
            self.txt_detail.insert(tk.END, "  1111.1111.1111  or  11:11:11:11:11:11", "guide_code")
            self.txt_detail.insert(tk.END, "  ➔ Automatically searches all 9 MAC formats in DB (., :, -, spaces, flat)\n")

            self.txt_detail.insert(tk.END, "  • ")
            self.txt_detail.insert(tk.END, "AND Search:     ", "guide_tag")
            self.txt_detail.insert(tk.END, "  sw01 AND vlan10", "guide_code")
            self.txt_detail.insert(tk.END, "  ➔ Matches rows containing both keywords\n")

            self.txt_detail.insert(tk.END, "  • ")
            self.txt_detail.insert(tk.END, "OR Search:      ", "guide_tag")
            self.txt_detail.insert(tk.END, "  server OR database", "guide_code")
            self.txt_detail.insert(tk.END, "  ➔ Matches rows containing either keyword\n")

            self.txt_detail.insert(tk.END, "  • ")
            self.txt_detail.insert(tk.END, "Exact Phrase:   ", "guide_tag")
            self.txt_detail.insert(tk.END, '  "GigabitEthernet 0/1"', "guide_code")
            self.txt_detail.insert(tk.END, "  ➔ Matches exact multi-word sequence\n")

            self.txt_detail.insert(tk.END, "  • ")
            self.txt_detail.insert(tk.END, "File Filter:    ", "guide_tag")
            self.txt_detail.insert(tk.END, "  file:switch 192.168", "guide_code")
            self.txt_detail.insert(tk.END, "  ➔ Restricts search to files matching 'switch'\n")

            self.txt_detail.insert(tk.END, "  • ")
            self.txt_detail.insert(tk.END, "Regex Mode:     ", "guide_tag")
            self.txt_detail.insert(tk.END, "  ^10\\.\\d+\\.\\d+", "guide_code")
            self.txt_detail.insert(tk.END, "  ➔ Check 'Regex Mode' to use full regular expressions\n")

            self.txt_detail.insert(tk.END, "  • ")
            self.txt_detail.insert(tk.END, "Fuzzy Fallback: ", "guide_tag")
            self.txt_detail.insert(tk.END, "  admnistrator", "guide_code")
            self.txt_detail.insert(tk.END, "  ➔ Single words automatically match typos with [%] score\n\n")

            self.txt_detail.insert(tk.END, "Keyboard Shortcuts:\n", "guide_h2")
            self.txt_detail.insert(tk.END, "  [Ctrl+F / Cmd+F] Focus Search   |   [↑ / ↓] Navigate Table   |   [Enter] Open File\n", "guide_dim")
            self.txt_detail.insert(tk.END, "  [Double-Click / Ctrl+C] Copy Row |   [Esc] Clear Query        |   [F1] Help Modal\n\n", "guide_dim")
            self.txt_detail.insert(tk.END, "👉 Start typing in the search box above to instantly search all files.", "guide_tip")

        def _render_no_results_hints(self, query: str, is_regex: bool, filter_mode: str):
            """Renders helpful troubleshooting hints when no matches are found."""
            self.lbl_detail_header.config(text=f"⚠️ No matches found for '{query}'")
            self.btn_load_full.pack_forget()

            self.txt_detail.config(state="normal")
            self.txt_detail.delete("1.0", tk.END)

            self.txt_detail.insert(tk.END, f"No matches found for: '{query}'\n\n", "guide_h2")
            self.txt_detail.insert(tk.END, "💡 Suggestions & Troubleshooting Tips:\n", "guide_h1")

            # Detect MAC/IP/regex patterns against the filter-stripped query,
            # matching what SearchEngine.search() actually evaluated (a
            # 'file:xxx' prefix would otherwise make these checks miss).
            _, effective_q = strip_file_filter(query)

            # Check if query looks like regex but regex mode is off
            if not is_regex and any(c in effective_q for c in (r"\d", r"\w", r"\s", ".*", "^", "$", "[", "]", "(", ")")):
                self.txt_detail.insert(tk.END, "  • ")
                self.txt_detail.insert(tk.END, "Regex Detected: ", "guide_tag")
                self.txt_detail.insert(tk.END, " Your query looks like a regular expression pattern. Try checking ")
                self.txt_detail.insert(tk.END, "'Regex Mode'", "guide_code")
                self.txt_detail.insert(tk.END, " above.\n")

            # Check if query looks like MAC
            if is_mac_address(effective_q):
                self.txt_detail.insert(tk.END, "  • ")
                self.txt_detail.insert(tk.END, "MAC Search:     ", "guide_tag")
                self.txt_detail.insert(tk.END, f" Searched all 9 notation variants for MAC '{effective_q}'. Ensure the target files contain this MAC address.\n")

            # Check if query looks like IP/CIDR
            if is_ip_or_cidr_query(effective_q):
                self.txt_detail.insert(tk.END, "  • ")
                self.txt_detail.insert(tk.END, "Subnet Search:  ", "guide_tag")
                self.txt_detail.insert(tk.END, f" Searched for any IP address or subnet inside '{effective_q}'. Check if the IP range covers your target.\n")

            # Check if query uses quotes
            if '"' in query:
                self.txt_detail.insert(tk.END, "  • ")
                self.txt_detail.insert(tk.END, "Quotes Filter:  ", "guide_tag")
                self.txt_detail.insert(tk.END, " You are searching for an exact quoted phrase. Try removing the quotes to search for separate keywords.\n")

            # Check file filter
            if "file:" in query.lower() or "f:" in query.lower():
                self.txt_detail.insert(tk.END, "  • ")
                self.txt_detail.insert(tk.END, "File Filter:    ", "guide_tag")
                self.txt_detail.insert(tk.END, " Verify that the filename in 'file:...' exists in your watched directory.\n")

            # Filter combobox tip
            if filter_mode != "All Indexed Files":
                self.txt_detail.insert(tk.END, "  • ")
                self.txt_detail.insert(tk.END, "File Mode:      ", "guide_tag")
                self.txt_detail.insert(tk.END, f" Currently filtering by '{filter_mode}'. Try switching the dropdown to ")
                self.txt_detail.insert(tk.END, "'All Indexed Files'", "guide_code")
                self.txt_detail.insert(tk.END, ".\n")

            # General boolean tips
            if len(query.split()) > 1 and "OR" not in query.upper():
                self.txt_detail.insert(tk.END, "  • ")
                self.txt_detail.insert(tk.END, "Boolean OR:     ", "guide_tag")
                self.txt_detail.insert(tk.END, " Default search requires all words (AND). Try using ")
                self.txt_detail.insert(tk.END, "OR", "guide_code")
                self.txt_detail.insert(tk.END, " (e.g. 'word1 OR word2') to broaden results.\n")

            self.txt_detail.insert(tk.END, "  • ")
            self.txt_detail.insert(tk.END, "Check Spelling: ", "guide_tag")
            self.txt_detail.insert(tk.END, " Ensure words are spelled correctly or try shorter 3+ letter stems.\n")

        def _show_help_dialog(self):
            """Displays a modal help & shortcuts cheat sheet."""
            dialog = tk.Toplevel(self.root)
            dialog.title("QSearch - Search Syntax & Shortcuts Help")
            dialog.geometry("640x520")
            dialog.minsize(540, 400)
            dialog.transient(self.root)

            # Center dialog on parent window
            try:
                x = self.root.winfo_rootx() + (self.root.winfo_width() // 2) - 320
                y = self.root.winfo_rooty() + (self.root.winfo_height() // 2) - 260
                dialog.geometry(f"+{max(10, x)}+{max(10, y)}")
            except Exception:
                pass

            main_frame = ttk.Frame(dialog, padding=16)
            main_frame.pack(fill="both", expand=True)

            ttk.Label(main_frame, text="📖 QSearch Search Syntax & Shortcuts Guide", font=("Helvetica", 13, "bold")).pack(anchor="w", pady=(0, 10))

            help_scroll = ttk.Scrollbar(main_frame, orient="vertical")
            help_text = tk.Text(main_frame, wrap="word", yscrollcommand=help_scroll.set, font=("Courier", 10), padx=8, pady=8)
            help_scroll.config(command=help_text.yview)

            help_text.tag_config("h1", font=("Helvetica", 11, "bold"), foreground="#0F172A")
            help_text.tag_config("code", font=("Courier", 10, "bold"), background="#E2E8F0", foreground="#0F172A")
            help_text.tag_config("bold", font=("Helvetica", 9, "bold"), foreground="#1E293B")
            help_text.tag_config("desc", font=("Helvetica", 9), foreground="#334155")

            content_sections = [
                ("1. ADVANCED QUERY SYNTAX", [
                    ("IP Subnet Search", "1.0.0.0/8 (or '192.168.1.0/24')", "Searches and matches any IP or subnet contained inside the CIDR range."),
                    ("MAC Address Search", "1111.1111.1111 (or 11:11:11:11:11:11)", "Searches all 9 formats (Cisco, IEEE colon, dot, hyphen, space, flat raw hex)."),
                    ("AND Operator", "server AND prod (or 'server && prod')", "Matches rows that contain ALL specified terms."),
                    ("OR Operator", "sw01 OR sw02 (or 'sw01 | sw02')", "Matches rows that contain AT LEAST ONE of the terms."),
                    ("Exact Phrases", '"GigabitEthernet 0/1"', "Surround in quotes to match exact words with spaces."),
                    ("Unique Files", "1 Match/File checkbox or '📄 Unique Files' chip", "Show each matching file only once even if multiple lines match in that file."),
                    ("File Filters", "file:switch vlan10 (or 'f:sw')", "Filters matched lines to files containing 'switch'."),
                    ("Regex Mode", "^10\\.1\\.\\d+\\.\\d+", "Enable 'Regex Mode' checkbox for full regex patterns."),
                    ("Fuzzy Fallback", "misspelled_word", "Single words without operators match typos with % similarity score.")
                ]),
                ("2. KEYBOARD SHORTCUTS", [
                    ("Ctrl+F / Cmd+F", "Focus search input bar", "Quickly jump to the search box from anywhere."),
                    ("Ctrl+U / Cmd+U", "Toggle Unique Files (1 Match/File)", "Toggles showing each unique file only once in results."),
                    ("Down Arrow (↓)", "Move from search box to results table", "Navigate directly to search results."),
                    ("Up Arrow (↑)", "Move from top row back to search box", "Jump back to editing your search query."),
                    ("Enter", "Open selected file in default app", "Opens file in Notepad, VSCode, TextEdit, etc."),
                    ("Ctrl+C / Cmd+C", "Copy selected matched row", "Copies full content line to clipboard."),
                    ("Double-Click", "Copy row / inspect", "Copies row and highlights breakdown in bottom pane."),
                    ("Right-Click", "Context menu", "Opens clipboard and folder explorer actions."),
                    ("Esc", "Clear search", "Clears search box and restores initial guide view."),
                    ("F1 / Ctrl+H", "Open this Help Guide", "Opens this reference cheat sheet.")
                ]),
                ("3. FILE & PERFORMANCE TIPS", [
                    ("Directory Tracking", "Automatic background indexer", "Changes in the watched folder are indexed in real time."),
                    ("Large Log Files", "±50 Lines Context Window", "Non-CSV log files show a 50-line window around matches."),
                    ("Full File View", "Click 'Load Full File'", "Displays entire file on demand when needed."),
                    ("CSV Export", "Save Results (.csv) 💾", "Exports all filtered results with match scores.")
                ])
            ]

            for header, items in content_sections:
                help_text.insert(tk.END, f"{header}\n", "h1")
                help_text.insert(tk.END, "─" * 60 + "\n")
                for title, example, explanation in items:
                    help_text.insert(tk.END, f" • {title:<18} ", "bold")
                    help_text.insert(tk.END, f"{example}\n", "code")
                    help_text.insert(tk.END, f"   {explanation}\n\n", "desc")
                help_text.insert(tk.END, "\n")

            help_text.config(state="disabled")
            help_text.pack(side="left", fill="both", expand=True)
            help_scroll.pack(side="right", fill="y")

            btn_close = ttk.Button(main_frame, text="Close [Esc]", command=dialog.destroy)
            btn_close.pack(anchor="e", pady=(8, 0))
            dialog.bind("<Escape>", lambda e: dialog.destroy())

        def _create_context_menu(self):
            self.context_menu = tk.Menu(self.root, tearoff=0)
            self.context_menu.add_command(label="📋 Copy Matched Row (Ctrl+C)", command=self._copy_selected_row)
            self.context_menu.add_command(label="📑 Copy Column Breakdown", command=self._copy_detail_text)
            self.context_menu.add_separator()
            self.context_menu.add_command(label="🖥️ Open File in Default App (Enter)", command=self._open_selected_file)
            self.context_menu.add_command(label="📂 Open Containing Folder", command=self._open_selected_folder)
            self.context_menu.add_separator()
            self.context_menu.add_command(label="❓ Search Syntax & Shortcuts Guide (F1)", command=self._show_help_dialog)

            self.tree.bind("<Button-3>", self._show_context_menu)
            self.tree.bind("<Button-2>", self._show_context_menu)

        def _show_context_menu(self, event):
            row_id = self.tree.identify_row(event.y)
            if row_id:
                self.tree.selection_set(row_id)
                self.context_menu.post(event.x_root, event.y_root)

        def _setup_indexer(self):
            def on_stats_update(file_cnt, row_cnt, total_files=0, files_left=0, percent=100, is_indexing=False, last_scan=None, last_update=None):
                self._msg_queue.put(("stats", (file_cnt, row_cnt, total_files, files_left, percent, is_indexing, last_scan, last_update)))

            self.indexer = BackgroundIndexer(self.engine, content_dir=self.content_dir, status_callback=on_stats_update)
            self.indexer.start()

            fc, rc, l_update, l_scan = self.engine.get_stats()
            self._update_stats_display(fc, rc, last_scan=l_scan, last_update=l_update)

        def _on_browse_directory(self):
            path = filedialog.askdirectory(initialdir=str(self.content_dir), title="Select Folder to Index & Search")
            if path:
                self.content_dir = Path(path).resolve()
                self.lbl_folder_path.config(text=str(self.content_dir))
                self.indexer.update_content_dir(self.content_dir)
                self._set_action_status("indexing", f"🔄 Switched directory to: {self.content_dir}. Re-indexing...")
                threading.Thread(target=self.indexer.sync_content_directory, daemon=True).start()

        def _poll_queue(self):
            try:
                while True:
                    msg_type, data = self._msg_queue.get_nowait()
                    if msg_type == "stats":
                        self._update_stats_display(*data)
                    elif msg_type == "search_results":
                        results, elapsed_ms, match_type, query, counter = data
                        with self._search_lock:
                            is_latest = (counter == self._search_counter)
                        if is_latest and self.search_var.get().strip() == query:
                            self._apply_search_results(results, elapsed_ms, match_type, query)
            except queue.Empty:
                pass
            self.root.after(50, self._poll_queue)

        def _update_stats_display(self, file_cnt, row_cnt, total_files=0, files_left=0, percent=100, is_indexing=False, last_scan=None, last_update=None):
            filter_mode = self.filter_var.get() if hasattr(self, 'filter_var') else "All Indexed Files"

            scan_str = format_timestamp(last_scan, "%H:%M:%S") if last_scan else "Scanning..."
            scan_rel = format_relative_time(last_scan)

            update_str = format_timestamp(last_update, "%H:%M:%S") if last_update else "Never"
            update_rel = format_relative_time(last_update)

            if is_indexing and files_left > 0:
                self.lbl_index_stats.config(
                    text=f"⚡ Indexing: {percent}% ({files_left} left) | {file_cnt} files ({row_cnt:,} rows)"
                )
            else:
                self.lbl_index_stats.config(
                    text=f"Files: {file_cnt} ({row_cnt:,} rows) | DB Updated: {update_str} ({update_rel}) | Scanned: {scan_str} ({scan_rel})"
                )

            # Update tooltip with full date/time details
            scan_full = format_timestamp(last_scan, "%Y-%m-%d %H:%M:%S")
            update_full = format_timestamp(last_update, "%Y-%m-%d %H:%M:%S")
            ToolTip(
                self.lbl_index_stats,
                f"📊 Index & Sync Timestamps:\n"
                f"• Total Files Indexed: {file_cnt} ({row_cnt:,} rows)\n"
                f"• Last Filesystem Scan: {scan_full} ({scan_rel})\n"
                f"• Last Database Sync:  {update_full} ({update_rel})\n"
                f"• Active Filter: {filter_mode}\n"
                f"• Watched Directory: {self.content_dir}"
            )

            if is_indexing and files_left > 0 and not self.search_var.get().strip():
                self._set_action_status("indexing", f"🔄 Background Indexing: {percent}% ({files_left} files left)...")

        def _set_action_status(self, state: str, message: str):
            """
            Updates the bottom status bar with real-time dynamic action status and color patterns:
            - 'typing': Amber / Warm Yellow (waiting for user to finish typing)
            - 'searching': Blue / Cyan (executing search query in database)
            - 'success': Emerald Green (matches found / active selection)
            - 'no_results': Rose / Soft Red (no matches found)
            - 'indexing': Golden Yellow (background indexing)
            - 'ready': Slate / Neutral (idle ready)
            """
            styles = {
                "typing": {"bg": "#FEF3C7", "fg": "#92400E", "border": "#FCD34D", "stats_fg": "#B45309"},
                "searching": {"bg": "#DBEAFE", "fg": "#1E40AF", "border": "#93C5FD", "stats_fg": "#1D4ED8"},
                "success": {"bg": "#D1FAE5", "fg": "#065F46", "border": "#6EE7B7", "stats_fg": "#047857"},
                "no_results": {"bg": "#FEE2E2", "fg": "#991B1B", "border": "#FCA5A5", "stats_fg": "#B91C1C"},
                "indexing": {"bg": "#FEF9C3", "fg": "#854D0E", "border": "#FDE047", "stats_fg": "#A16207"},
                "ready": {"bg": "#F1F5F9", "fg": "#475569", "border": "#CBD5E1", "stats_fg": "#64748B"},
            }
            theme = styles.get(state, styles["ready"])
            try:
                self.status_frame.config(bg=theme["bg"], highlightbackground=theme["border"], highlightcolor=theme["border"])
                self.lbl_status.config(text=message, bg=theme["bg"], fg=theme["fg"])
                self.lbl_index_stats.config(bg=theme["bg"], fg=theme["stats_fg"])
            except Exception:
                pass

        def _on_key_release(self, event):
            if event.keysym in ("Up", "Down", "Left", "Right", "Return", "Escape", "Control_L", "Control_R", "F1"):
                return
            if self._debounce_job:
                self.root.after_cancel(self._debounce_job)

            q = self.search_var.get().strip()
            if q:
                self._set_action_status("typing", f"⏳ Pending user to finish typing... ('{q}')")
            else:
                self._set_action_status("ready", "🔍 Ready | Type keywords, MAC address (full/last 4), or Subnet (1.0.0.0/8) to search")

            q_len = len(q)
            delay_ms = 180 if q_len < 3 else 90
            self._debounce_job = self.root.after(delay_ms, self._perform_search)

        def _on_search_down_arrow(self, event):
            children = self.tree.get_children()
            if children:
                self.tree.focus_set()
                if not self.tree.selection():
                    self.tree.selection_set(children[0])
                    self.tree.focus(children[0])
                return "break"

        def _on_tree_up_arrow(self, event):
            selected = self.tree.selection()
            children = self.tree.get_children()
            if selected and children and selected[0] == children[0]:
                self.search_entry.focus_set()
                return "break"

        def _focus_search(self):
            self.search_entry.focus_set()
            self.search_entry.select_range(0, tk.END)

        def _perform_search(self):
            query = self.search_var.get().strip()

            if not query:
                for item in self.tree.get_children():
                    self.tree.delete(item)
                self._render_welcome_guide()
                self._current_results = []
                self.lbl_status.config(text="Ready | Type keywords or click quick syntax chips above...")
                self._set_action_status("ready", "🔍 Ready | Type keywords, MAC address (full/last 4), or Subnet (1.0.0.0/8) to search")
                self.btn_load_full.pack_forget()
                return

            filter_mode = self.filter_var.get() if hasattr(self, 'filter_var') else "All Indexed Files"
            if filter_mode == "Text Files Only":
                file_type = "text"
            elif filter_mode == "CSV Files Only":
                file_type = "csv"
            else:
                file_type = "all"

            is_regex = self.regex_var.get()
            is_unique = self.unique_var.get()
            is_mac = self.mac_var.get()

            with self._search_lock:
                self._search_counter += 1
                current_counter = self._search_counter

            self.lbl_status.config(text=f"Searching for '{query}'...")
            self._set_action_status("searching", f"⚡ Searching database for '{query}'...")

            def search_worker(q, ftype, regex_flag, unique_flag, mac_flag, counter):
                results, elapsed_ms, match_type = self.engine.search(
                    q,
                    limit=1000,
                    file_type=ftype,
                    is_regex=regex_flag,
                    unique_files=unique_flag,
                    is_mac=mac_flag
                )
                self._msg_queue.put(("search_results", (results, elapsed_ms, match_type, q, counter)))

            threading.Thread(target=search_worker, args=(query, file_type, is_regex, is_unique, is_mac, current_counter), daemon=True).start()

        def _apply_search_results(self, results, elapsed_ms, match_type, query):
            for item in self.tree.get_children():
                self.tree.delete(item)

            self._current_results = results
            self._active_match_type = match_type

            if not results:
                filter_mode = self.filter_var.get() if hasattr(self, 'filter_var') else "All Indexed Files"
                self._render_no_results_hints(query, self.regex_var.get(), filter_mode)
                self.lbl_status.config(text=f"No matches found for '{query}' in {elapsed_ms:.1f} ms. See troubleshooting hints below.")
                self._set_action_status("no_results", f"⚠️ No matches found for '{query}' ({elapsed_ms:.1f} ms)")
                return

            self.txt_detail.config(state="normal")
            self.txt_detail.delete("1.0", tk.END)

            # Insert results putting matching percentage in front of the line
            for fname, rnum, ltext, score in results:
                disp_text = f"[{score}%] {ltext}"
                self.tree.insert("", "end", values=(fname, rnum, disp_text))

            count = len(results)
            limit_notice = " (showing top 1000)" if count >= 1000 else ""
            if match_type == "regex":
                tag = " (Regex Matches)"
            elif match_type == "mac":
                tag = " (MAC Address Matches - All Formats)"
            elif match_type == "ip_subnet":
                tag = " (IP / Subnet Containment Matches)"
            elif match_type == "fuzzy":
                tag = " (Fuzzy Matches)"
            else:
                tag = ""
            uniq_tag = " (1 Match/File)" if self.unique_var.get() else ""
            self.lbl_status.config(text=f"Found {count} match(es){tag}{uniq_tag}{limit_notice} in {elapsed_ms:.1f} ms for '{query}'")
            self._set_action_status("success", f"✅ Found {count} match(es){tag}{uniq_tag} in {elapsed_ms:.1f} ms")

            children = self.tree.get_children()
            if children:
                self.tree.selection_set(children[0])
                self.tree.focus(children[0])

        def _highlight_matches_in_text(self, query: str, match_type: str, is_regex: bool):
            """Highlights and bolds all matched search patterns in the detail text widget."""
            if not query:
                return

            full_text = self.txt_detail.get("1.0", "end-1c")
            if not full_text:
                return

            # Match against the filter-stripped query — the same text
            # SearchEngine.search() actually evaluated — so a 'file:xxx'
            # prefix doesn't break MAC/IP/regex highlighting.
            _, query = strip_file_filter(query)
            if not query:
                return

            # Case A: Regex Highlighting
            if is_regex or match_type == "regex":
                try:
                    for match in re.finditer(query, full_text, re.IGNORECASE):
                        s_idx, e_idx = match.span()
                        start_pos = f"1.0 + {s_idx} chars"
                        end_pos = f"1.0 + {e_idx} chars"
                        self.txt_detail.tag_add("regex_match", start_pos, end_pos)
                except Exception:
                    pass
                return

            # Case B: Fuzzy Search Highlighting
            if match_type == "fuzzy":
                fuzzy_words = get_fuzzy_matched_words(query, full_text)
                for fword in fuzzy_words:
                    start_pos = "1.0"
                    while True:
                        start_pos = self.txt_detail.search(fword, start_pos, stopindex=tk.END, nocase=True)
                        if not start_pos:
                            break
                        end_pos = f"{start_pos}+{len(fword)}c"
                        self.txt_detail.tag_add("fuzzy_match", start_pos, end_pos)
                        start_pos = end_pos
                return

            # Case C: Subnets Highlighting (supports multi-subnet OR / AND queries)
            subnets = extract_subnets_from_query(query)
            if subnets:
                for target_net in subnets:
                    matched_ips = extract_matching_ips_in_text(target_net, full_text)
                    for mip in matched_ips:
                        start_pos = "1.0"
                        while True:
                            start_pos = self.txt_detail.search(mip, start_pos, stopindex=tk.END, nocase=False)
                            if not start_pos:
                                break
                            end_pos = f"{start_pos}+{len(mip)}c"
                            self.txt_detail.tag_add("match_query", start_pos, end_pos)
                            start_pos = end_pos

            # Case D: MAC Address Highlighting (if in MAC mode)
            if match_type == "mac" or self.mac_var.get():
                tokens = re.findall(r'"[^"]+"|\S+', query)
                for tok in tokens:
                    t_clean = tok.strip('"\',()')
                    if is_mac_address(t_clean):
                        variants = generate_mac_variants(t_clean)
                        for v in variants:
                            start_pos = "1.0"
                            while True:
                                start_pos = self.txt_detail.search(v, start_pos, stopindex=tk.END, nocase=True)
                                if not start_pos:
                                    break
                                end_pos = f"{start_pos}+{len(v)}c"
                                self.txt_detail.tag_add("match_query", start_pos, end_pos)
                                start_pos = end_pos

            # Case E: Exact / Multi-token / Boolean Search Highlighting
            keywords = extract_search_keywords(query)
            for kw in keywords:
                if "/" in kw and parse_ip_or_subnet(kw) is not None:
                    continue
                if (match_type == "mac" or self.mac_var.get()) and is_mac_address(kw):
                    continue
                if not kw:
                    continue
                start_pos = "1.0"
                while True:
                    start_pos = self.txt_detail.search(kw, start_pos, stopindex=tk.END, nocase=True)
                    if not start_pos:
                        break
                    end_pos = f"{start_pos}+{len(kw)}c"
                    self.txt_detail.tag_add("match_query", start_pos, end_pos)
                    start_pos = end_pos

        def _on_tree_select(self, event=None):
            selected = self.tree.selection()
            if selected:
                try:
                    idx = self.tree.index(selected[0])
                    if 0 <= idx < len(self._current_results):
                        fname, rnum, ltext, score = self._current_results[idx]
                        query = self.search_var.get().strip()
                        headers = self.engine.get_file_headers(fname)
                        is_regex = self.regex_var.get()

                        target_path = Path(fname)
                        if not target_path.is_absolute() or not target_path.exists():
                            target_path = self.content_dir / fname
                            if not target_path.exists():
                                matches = list(self.content_dir.rglob(os.path.basename(fname)))
                                if matches:
                                    target_path = matches[0]

                        self._active_file_path = target_path
                        self._active_match_rnum = rnum

                        ext = target_path.suffix.lower()

                        # Retrieve detailed file metadata
                        info = self.engine.get_file_info(fname)
                        mod_str = format_timestamp(info["mtime"], "%Y-%m-%d %H:%M:%S") if (info and info.get("mtime")) else "Unknown"
                        mod_rel = format_relative_time(info["mtime"]) if (info and info.get("mtime")) else ""
                        idx_str = format_timestamp(info["indexed_at"], "%H:%M:%S") if (info and info.get("indexed_at")) else ""
                        size_kb = f"{info['size'] / 1024:.1f} KB" if (info and info.get("size")) else ""
                        rows_cnt = f"{info['row_count']:,} rows" if (info and info.get("row_count")) else ""

                        time_hint = f"  •  Modified: {mod_str} ({mod_rel})" if mod_rel else ""
                        idx_hint = f"  •  DB Indexed: {idx_str}" if idx_str else ""
                        self.lbl_detail_header.config(text=f"[{score}%] 📄 {fname} (Line #{rnum}){time_hint}{idx_hint}")

                        ToolTip(
                            self.lbl_detail_header,
                            f"📄 File Metadata & Timestamps:\n"
                            f"• File Name: {fname}\n"
                            f"• Full Path: {target_path}\n"
                            f"• File Modified on Disk: {mod_str} ({mod_rel})\n"
                            f"• Last Indexed in DB:   {format_timestamp(info.get('indexed_at') if info else None, '%Y-%m-%d %H:%M:%S')}\n"
                            f"• File Size: {size_kb} | Total File Rows: {rows_cnt}"
                        )

                        self.txt_detail.config(state="normal")
                        self.txt_detail.delete("1.0", tk.END)

                        # Non-CSV text file -> Render bounded window context
                        if ext != ".csv" and target_path.exists():
                            self._render_text_context_window(target_path, rnum, query, is_regex)
                        else:
                            self.btn_load_full.pack_forget()
                            col_lines = format_record_multiline(headers, ltext)
                            self.txt_detail.insert(tk.END, "\n".join(col_lines))
                            self._highlight_matches_in_text(query, self._active_match_type, is_regex)

                        if score < 100:
                            self.lbl_status.config(text=f"Match Score: {score}% | {fname}:L{rnum} | Modified: {mod_str} ({mod_rel})")
                        self._set_action_status("success", f"📄 Selected: {fname} (Line #{rnum}) | Score: {score}%")
                except Exception as e:
                    print(f"[Select Error] {e}", file=sys.stderr)

        def _render_text_context_window(self, target_path, rnum, query, is_regex):
            """Renders a sliced context window (±50 lines) to prevent UI freezing on large files."""
            try:
                window_size = 50
                start_l = max(1, rnum - window_size)
                end_l = rnum + window_size

                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = []
                    total_lines = 0
                    for cur_idx, line in enumerate(f, start=1):
                        total_lines = cur_idx
                        if start_l <= cur_idx <= end_l:
                            lines.append((cur_idx, line))

                if total_lines > 120:
                    self.btn_load_full.pack(side="right", padx=(4, 0))
                else:
                    self.btn_load_full.pack_forget()

                target_pos = None
                if start_l > 1:
                    self.txt_detail.insert(tk.END, f"--- [Skipped lines 1 to {start_l-1}] ---\n")

                for cur_idx, line in lines:
                    l_start = self.txt_detail.index("end-1c")
                    self.txt_detail.insert(tk.END, f"L{cur_idx:<5d} │ {line}")
                    l_end = self.txt_detail.index("end-1c")
                    if cur_idx == rnum:
                        target_pos = l_start
                        self.txt_detail.tag_add("match_line", l_start, l_end)

                if end_l < total_lines:
                    self.txt_detail.insert(tk.END, f"--- [Remaining lines {end_l+1} to {total_lines} hidden. Click 'Load Full File' above] ---\n")

                self._highlight_matches_in_text(query, self._active_match_type, is_regex)

                if target_pos:
                    self.txt_detail.see(target_pos)

            except Exception as e:
                self.txt_detail.insert(tk.END, f"Error loading file: {e}")

        def _load_full_text_file(self):
            """Loads full file upon user request."""
            if not self._active_file_path or not self._active_file_path.exists():
                return
            try:
                self.btn_load_full.pack_forget()
                self.txt_detail.config(state="normal")
                self.txt_detail.delete("1.0", tk.END)

                query = self.search_var.get().strip()
                rnum = self._active_match_rnum
                is_regex = self.regex_var.get()

                with open(self._active_file_path, "r", encoding="utf-8", errors="replace") as f:
                    target_pos = None
                    for cur_idx, line in enumerate(f, start=1):
                        l_start = self.txt_detail.index("end-1c")
                        self.txt_detail.insert(tk.END, f"L{cur_idx:<5d} │ {line}")
                        l_end = self.txt_detail.index("end-1c")
                        if cur_idx == rnum:
                            target_pos = l_start
                            self.txt_detail.tag_add("match_line", l_start, l_end)

                self._highlight_matches_in_text(query, self._active_match_type, is_regex)

                if target_pos:
                    self.txt_detail.see(target_pos)

            except Exception as e:
                self.txt_detail.insert(tk.END, f"Error: {e}")

        def _on_tree_click(self, event):
            self.root.after(10, self._on_tree_select)

        def _copy_selected_row(self):
            selected = self.tree.selection()
            if selected:
                item = self.tree.item(selected[0])
                content = item["values"][2]
                self.root.clipboard_clear()
                self.root.clipboard_append(str(content))
                self._set_action_status("success", "📋 Copied row content to clipboard!")

        def _copy_detail_text(self):
            content = self.txt_detail.get("1.0", "end-1c").strip()
            if content:
                self.root.clipboard_clear()
                self.root.clipboard_append(content)
                self._set_action_status("success", "📑 Copied column breakdown to clipboard!")

        def _open_selected_file(self):
            selected = self.tree.selection()
            if selected:
                fname = self.tree.item(selected[0])["values"][0]
                open_file_in_default_app(fname, content_dir=self.content_dir)

        def _open_selected_folder(self):
            selected = self.tree.selection()
            if selected:
                fname = self.tree.item(selected[0])["values"][0]
                open_containing_folder(fname, content_dir=self.content_dir)

        def _clear_search(self):
            self.search_var.set("")
            self._set_action_status("ready", "🔍 Ready | Type keywords, MAC address (full/last 4), or Subnet (1.0.0.0/8) to search")
            self._perform_search()
            self.search_entry.focus_set()

        def _on_row_double_click(self, event):
            self._copy_selected_row()

        def _on_enter_pressed(self, event):
            self._open_selected_file()

        def _save_results_to_csv(self):
            if not self._current_results:
                messagebox.showwarning("Save Results", "No search results available to save.")
                return

            query = self.search_var.get().strip()
            safe_query = "".join(c for c in query if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
            default_filename = f"search_results_{safe_query}.csv" if safe_query else "search_results.csv"

            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV Files (*.csv)", "*.csv"), ("All Files (*.*)", "*.*")],
                initialfile=default_filename,
                title="Save Search Results as CSV File"
            )

            if not file_path:
                return

            try:
                with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Score", "File Name", "Line Number", "Matched Content"])
                    for fname, rnum, ltext, score in self._current_results:
                        writer.writerow([f"{score}%", fname, rnum, ltext])

                filename_only = os.path.basename(file_path)
                self._set_action_status("success", f"💾 Successfully saved {len(self._current_results)} results to '{filename_only}'")
                messagebox.showinfo("Save Complete", f"Successfully saved {len(self._current_results)} search results to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save results:\n{e}")

        def _on_escape_pressed(self, event=None):
            self._clear_search()

def colorize_cli_match(text: str, query: str, match_type: str, is_regex: bool) -> str:
    """Highlights and bolds matched keywords or patterns in terminal output with ANSI colors."""
    if not query or not text:
        return text

    # Strip file filter tokens if present
    _, query = strip_file_filter(query)
    if not query:
        return text

    if is_regex or match_type == "regex":
        try:
            return re.sub(query, r"\033[1;93;4m\g<0>\033[0m", text, flags=re.IGNORECASE)
        except Exception:
            return text

    if match_type == "fuzzy":
        fwords = get_fuzzy_matched_words(query, text)
        result = text
        for fw in fwords:
            pattern = re.escape(fw)
            result = re.sub(f"({pattern})", r"\033[1;91;4m\1\033[0m", result, flags=re.IGNORECASE)
        return result

    result = text

    # 1. Highlight all matching IP addresses across all subnets in the query
    subnets = extract_subnets_from_query(query)
    if subnets:
        for target_net in subnets:
            matched_ips = extract_matching_ips_in_text(target_net, result)
            for mip in matched_ips:
                pat = re.escape(mip)
                result = re.sub(f"({pat})", r"\033[1;93;1m\1\033[0m", result)

    # 2. Highlight MAC variants if in MAC mode
    if match_type == "mac":
        tokens = re.findall(r'"[^"]+"|\S+', query)
        for tok in tokens:
            t_clean = tok.strip('"\',()')
            if is_mac_address(t_clean):
                variants = generate_mac_variants(t_clean)
                for v in variants:
                    pat = re.escape(v)
                    result = re.sub(f"({pat})", r"\033[1;93;1m\1\033[0m", result, flags=re.IGNORECASE)

    # 3. Standard text keywords (omitting CIDR subnets and MAC tokens)
    keywords = extract_search_keywords(query)
    for kw in keywords:
        if "/" in kw and parse_ip_or_subnet(kw) is not None:
            continue
        if match_type == "mac" and is_mac_address(kw):
            continue
        pattern = re.escape(kw)
        result = re.sub(f"({pattern})", r"\033[1;93;1m\1\033[0m", result, flags=re.IGNORECASE)

    return result


def run_interactive_cli(stdscr, content_dir=DEFAULT_CONTENT_DIR):
    """Interactive Curses TUI search interface."""
    curses.curs_set(1)
    stdscr.nodelay(True)
    stdscr.timeout(100)

    engine = SearchEngine(content_dir=content_dir)
    indexer = BackgroundIndexer(engine, content_dir=content_dir)
    indexer.start()

    filter_modes = ["all", "csv", "text"]
    filter_idx = 0

    query = ""
    selected_idx = 0
    results = []
    elapsed_ms = 0.0
    match_type = "exact"
    is_regex = False
    is_unique = False
    is_mac = False

    while True:
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        header = f" QSearch TUI [{content_dir}] "
        stdscr.addstr(0, 0, header.center(max_x), curses.A_REVERSE | curses.A_BOLD)

        prompt = "🔍 Search > "
        stdscr.addstr(2, 2, prompt, curses.A_BOLD)
        stdscr.addstr(2, 2 + len(prompt), query)

        fc, rc, l_update, l_scan = engine.get_stats()
        scan_t = format_timestamp(l_scan, "%H:%M:%S") if l_scan else "Scanning..."
        update_t = format_timestamp(l_update, "%H:%M:%S") if l_update else "Never"

        if indexer.is_indexing and indexer.files_left > 0:
            idx_str = f"Indexing: {indexer.percent}% ({indexer.files_left} left)"
        else:
            idx_str = f"Index: {fc} files ({rc:,} rows) | DB: {update_t} | Scan: {scan_t}"

        mode_label = {"csv": "CSV Only", "text": "Text Only", "all": "All Files"}[filter_modes[filter_idx]]
        reg_label = " [Regex: ON]" if is_regex else ""
        mac_label = " [MAC: ON]" if is_mac else ""
        uniq_label = " [Unique: ON]" if is_unique else ""

        if results and 0 <= selected_idx < len(results):
            sel_score = results[selected_idx][3]
            type_str = f" [Score: {sel_score}%]"
        else:
            if match_type == "regex":
                type_str = " (Regex)"
            elif match_type == "mac":
                type_str = " (MAC Formats)"
            elif match_type == "ip_subnet":
                type_str = " (IP/Subnet)"
            elif match_type == "fuzzy":
                type_str = " (Fuzzy)"
            else:
                type_str = ""

        info_str = f" Matches: {len(results)}{type_str}{reg_label}{mac_label}{uniq_label} | Time: {elapsed_ms:.1f}ms | Filter: {mode_label} [Tab] | {idx_str} "
        stdscr.addstr(3, 2, info_str[:max_x - 4], getattr(curses, 'A_DIM', curses.A_NORMAL))

        stdscr.addstr(4, 0, "─" * max_x)

        start_row = 5
        max_results_rows = max_y - start_row - 2

        if results and max_results_rows > 0:
            visible_results = results[:max_results_rows]
            selected_idx = min(selected_idx, len(visible_results) - 1)
            selected_idx = max(0, selected_idx)

            for idx, (fname, rnum, ltext, score) in enumerate(visible_results):
                row_y = start_row + idx
                line_disp = f"[{score}%] [{fname}:L{rnum}] {ltext}"
                line_disp = line_disp[:max_x - 4]

                if idx == selected_idx:
                    stdscr.addstr(row_y, 2, line_disp, curses.A_STANDOUT | curses.A_BOLD)
                else:
                    stdscr.addstr(row_y, 2, line_disp)

        footer = " [Esc: Clear | Enter: Open | Tab: Filter | F2/Ctrl+O: MAC | F3/Ctrl+R: Regex | F4: Unique | F5: Save | ↑/↓: Select] "
        try:
            stdscr.addstr(max_y - 1, 0, footer.center(max_x), curses.A_REVERSE)
        except curses.error:
            pass

        stdscr.move(2, 2 + len(prompt) + len(query))
        stdscr.refresh()

        try:
            ch = stdscr.getch()
        except Exception:
            ch = -1

        if ch == -1:
            time.sleep(0.03)
            continue

        if ch in (3, 27): # ESC or Ctrl+C
            if query:
                query = ""
                results = []
                selected_idx = 0
            else:
                break
        elif ch in (getattr(curses, 'KEY_F2', 266), 15): # F2 or Ctrl+O -> Toggle MAC mode
            is_mac = not is_mac
            if is_mac:
                is_regex = False
            if query:
                results, elapsed_ms, match_type = engine.search(query, file_type=filter_modes[filter_idx], is_regex=is_regex, unique_files=is_unique, is_mac=is_mac)
                selected_idx = 0
        elif ch in (getattr(curses, 'KEY_F3', 267), 18): # F3 or Ctrl+R -> Toggle Regex
            is_regex = not is_regex
            if is_regex:
                is_mac = False
            if query:
                results, elapsed_ms, match_type = engine.search(query, file_type=filter_modes[filter_idx], is_regex=is_regex, unique_files=is_unique, is_mac=is_mac)
                selected_idx = 0
        elif ch in (getattr(curses, 'KEY_F4', 268), 21): # F4 or Ctrl+U -> Toggle Unique Files mode
            is_unique = not is_unique
            if query:
                results, elapsed_ms, match_type = engine.search(query, file_type=filter_modes[filter_idx], is_regex=is_regex, unique_files=is_unique, is_mac=is_mac)
                selected_idx = 0
        elif ch in (9, ord('\t')): # Tab key toggles file filter
            filter_idx = (filter_idx + 1) % len(filter_modes)
            if query:
                results, elapsed_ms, match_type = engine.search(query, file_type=filter_modes[filter_idx], is_regex=is_regex, unique_files=is_unique, is_mac=is_mac)
                selected_idx = 0
        elif ch in (10, 13, getattr(curses, "KEY_ENTER", 10)): # Enter opens file
            if results and 0 <= selected_idx < len(results):
                fname = results[selected_idx][0]
                open_file_in_default_app(fname, content_dir=content_dir)
        elif ch in (getattr(curses, 'KEY_F6', 270), 25, 11): # F6 or Ctrl+Y -> Copy record
            if results and 0 <= selected_idx < len(results):
                fname, rnum, ltext, score = results[selected_idx]
                if fname.lower().endswith(".csv"):
                    headers = engine.get_file_headers(fname)
                    col_lines = format_record_multiline(headers, ltext)
                    formatted_text = f"[{score}%] 📄 {fname} (Row #{rnum})\n" + "\n".join(col_lines)
                else:
                    formatted_text = f"[{score}%] 📄 {fname} (Line #{rnum})\n  {ltext}"
                try:
                    if HAS_TKINTER:
                        r = tk.Tk()
                        r.withdraw()
                        r.clipboard_clear()
                        r.clipboard_append(formatted_text)
                        r.update()
                        r.destroy()
                except Exception:
                    pass
        elif ch in (getattr(curses, 'KEY_F5', 269), 19): # F5 or Ctrl+S -> Save to CSV
            if results:
                safe_query = "".join(c for c in query if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
                filename = f"search_results_{safe_query}.csv" if safe_query else "search_results.csv"
                out_path = Path(content_dir) / filename
                try:
                    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Score", "File Name", "Line Number", "Matched Content"])
                        for fname, rnum, ltext, score in results:
                            writer.writerow([f"{score}%", fname, rnum, ltext])
                except Exception:
                    pass
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if query:
                query = query[:-1]
                results, elapsed_ms, match_type = engine.search(query, file_type=filter_modes[filter_idx], is_regex=is_regex, unique_files=is_unique, is_mac=is_mac)
                selected_idx = 0
        elif ch == curses.KEY_UP:
            if selected_idx > 0:
                selected_idx -= 1
        elif ch == curses.KEY_DOWN:
            if selected_idx < len(results) - 1:
                selected_idx += 1
        elif 32 <= ch <= 126:
            query += chr(ch)
            results, elapsed_ms, match_type = engine.search(query, file_type=filter_modes[filter_idx], is_regex=is_regex, unique_files=is_unique, is_mac=is_mac)
            selected_idx = 0


def run_interactive_repl(content_dir=DEFAULT_CONTENT_DIR, file_type="all", unique_files=False, is_mac=False, is_ip=False):
    """Continuous REPL prompt for terminal users without curses."""
    engine = SearchEngine(content_dir=content_dir)
    indexer = BackgroundIndexer(engine, content_dir=content_dir)
    indexer.sync_content_directory()

    fc, rc, l_update, l_scan = engine.get_stats()
    scan_t = format_timestamp(l_scan, "%Y-%m-%d %H:%M:%S")
    update_t = format_timestamp(l_update, "%Y-%m-%d %H:%M:%S")

    print("=" * 75)
    print(f"  🔍 QSearch Interactive CLI REPL (Directory: {content_dir})")
    print(f"  📊 Index: {fc} files ({rc:,} rows) | Last DB Sync: {update_t}")
    print(f"  📁 Last Scan: {scan_t} ({format_relative_time(l_scan)})")
    print("  Commands: :help | :info | :filter [csv|text|all] | :mac | :ip | :regex | :unique | :open <row> | :quit")
    print("  Syntax:   1.0.0.0/8 | 1111.1111.1111 | server AND prod | word1 OR word2 | file:name")
    print("=" * 75)

    last_results = []
    current_ftype = file_type
    regex_mode = False
    unique_mode = unique_files
    mac_mode = is_mac
    ip_mode = is_ip

    while True:
        try:
            flags = []
            if regex_mode:
                flags.append("Regex")
            if mac_mode:
                flags.append("MAC")
            if ip_mode:
                flags.append("IP")
            if unique_mode:
                flags.append("Unique")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            cmd = input(f"\nqs ({current_ftype}){flag_str}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting QSearch.")
            break

        if not cmd:
            continue
        if cmd in (":info", ":stats", ":status"):
            fc, rc, l_update, l_scan = engine.get_stats()
            print("\n📊 Database Index Status & Timestamps:")
            print(f"  • Watched Directory:   {content_dir}")
            print(f"  • Total Indexed Files: {fc}")
            print(f"  • Total Indexed Rows:  {rc:,}")
            print(f"  • Last Filesystem Scan: {format_timestamp(l_scan)} ({format_relative_time(l_scan)})")
            print(f"  • Last Database Update: {format_timestamp(l_update)} ({format_relative_time(l_update)})")
            continue
        if cmd in (":help", ":h", ":?"):
            print("\n📖 QSearch CLI REPL Commands & Query Syntax:")
            print("  :info / :stats          Show database sync & filesystem scan timestamps")
            print("  :filter [csv|text|all]  Change active file filter")
            print("  :mac                    Toggle forced MAC address search mode")
            print("  :ip                     Toggle forced IP / Subnet search mode")
            print("  :regex                  Toggle regular expression search mode")
            print("  :unique / :u            Toggle unique files mode (1 match per file)")
            print("  :open <num>             Open matched file in default application")
            print("  :quit / :q / exit       Exit QSearch")
            print("\n💡 Search Syntax Examples:")
            print("  • IP Subnet:     1.0.0.0/8             (matches any IP/subnet inside 1.0.0.0/8)")
            print("  • MAC Address:   1111.1111.1111        (searches all 9 formats: ., :, -, space, flat)")
            print("  • AND Search:    server AND prod       (requires both terms)")
            print("  • OR Search:     vlan10 OR vlan20      (matches either term)")
            print("  • Exact Phrase:  \"GigabitEthernet\"     (matches verbatim)")
            print("  • File Filter:   file:switch 192.168   (matches files containing 'switch')")
            print("  • Regex:         ^10\\.\\d+\\.\\d+         (when :regex is ON)")
            print("  • Fuzzy:         typo_word             (fuzzy matches with % score)")
            continue
        if cmd in (":quit", ":q", "exit", "quit"):
            break
        if cmd == ":mac":
            mac_mode = not mac_mode
            if mac_mode:
                ip_mode = False
                regex_mode = False
            print(f"[MAC address mode: {'ON' if mac_mode else 'OFF'}]")
            continue
        if cmd == ":ip":
            ip_mode = not ip_mode
            if ip_mode:
                mac_mode = False
                regex_mode = False
            print(f"[IP / Subnet mode: {'ON' if ip_mode else 'OFF'}]")
            continue
        if cmd == ":regex":
            regex_mode = not regex_mode
            if regex_mode:
                mac_mode = False
                ip_mode = False
            print(f"[Regex mode: {'ON' if regex_mode else 'OFF'}]")
            continue
        if cmd in (":unique", ":u"):
            unique_mode = not unique_mode
            print(f"[Unique files mode: {'ON (1 match/file)' if unique_mode else 'OFF (all matches)'}]")
            continue
        if cmd.startswith(":filter") or cmd.startswith(":f"):
            parts = cmd.split()
            if len(parts) > 1 and parts[1] in ("csv", "text", "all"):
                current_ftype = parts[1]
                print(f"[Filter updated] Active filter: {current_ftype}")
            else:
                print("Usage: :filter csv | :filter text | :filter all")
            continue
        if cmd.startswith(":open") or cmd.startswith(":o"):
            parts = cmd.split()
            if len(parts) > 1 and parts[1].isdigit():
                idx = int(parts[1]) - 1
                if 0 <= idx < len(last_results):
                    open_file_in_default_app(last_results[idx][0], content_dir=content_dir)
                    print(f"[Opened] {last_results[idx][0]}")
                else:
                    print("Invalid result index.")
            continue

        results, elapsed_ms, match_type = engine.search(
            cmd,
            limit=500,
            file_type=current_ftype,
            is_regex=regex_mode,
            unique_files=unique_mode,
            is_mac=mac_mode,
            is_ip=ip_mode
        )
        last_results = results

        if match_type == "regex":
            tag_str = " (Regex)"
        elif match_type == "mac":
            tag_str = " (MAC Formats)"
        elif match_type == "ip_subnet":
            tag_str = " (IP / Subnet)"
        elif match_type == "fuzzy":
            tag_str = " (Fuzzy)"
        else:
            tag_str = ""

        uniq_tag = " (Unique Files)" if unique_mode else ""
        print(f"\n🔍 Found {len(results)} match(es){tag_str}{uniq_tag} in {elapsed_ms:.1f} ms:")
        print("─" * 70)
        if not results:
            print("No matches found.")
        else:
            for i, (fname, rnum, ltext, score) in enumerate(results[:25], 1):
                highlighted_text = colorize_cli_match(ltext, cmd, match_type, regex_mode)
                print(f"[\033[1;32m{score}%\033[0m] [{i}] \033[1;34m{fname}\033[0m:L\033[33m{rnum}\033[0m ➔ {highlighted_text}")
            if len(results) > 25:
                print(f"... and {len(results) - 25} more matches.")
        print("─" * 70)


def run_direct_cli_search(query, content_dir=DEFAULT_CONTENT_DIR, file_type="all", is_regex=False, unique_files=False, is_mac=False, is_ip=False, output_format="text", csv_out_path=None):
    """Executes single search query directly from terminal arguments with front percentage & keyword highlighting."""
    engine = SearchEngine(content_dir=content_dir)

    indexer = BackgroundIndexer(engine, content_dir=content_dir)
    indexer.sync_content_directory()

    results, elapsed_ms, match_type = engine.search(
        query,
        limit=1000,
        file_type=file_type,
        is_regex=is_regex,
        unique_files=unique_files,
        is_mac=is_mac,
        is_ip=is_ip
    )

    # Format 1: JSON Output
    if output_format == "json":
        json_data = {
            "query": query,
            "count": len(results),
            "elapsed_ms": round(elapsed_ms, 2),
            "match_type": match_type,
            "unique_files": unique_files,
            "results": [
                {
                    "match_score": f"{r[3]}%",
                    "file": r[0],
                    "row": r[1],
                    "content": r[2]
                }
                for r in results
            ]
        }
        print(json.dumps(json_data, indent=2))
        return

    # Format 2: CSV Export
    if csv_out_path or output_format == "csv":
        out_file = csv_out_path or "qsearch_results.csv"
        try:
            with open(out_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Score", "File Name", "Line Number", "Matched Content"])
                for fname, rnum, ltext, score in results:
                    writer.writerow([f"{score}%", fname, rnum, ltext])
            print(f"[Success] Saved {len(results)} search results to: {out_file}")
        except Exception as e:
            print(f"[Error] Failed to write CSV: {e}", file=sys.stderr)
        return

    # Format 3: Standard Formatted Terminal Output with Front Score & Bold Highlights
    if match_type == "regex":
        tag_str = " (Regex Matches)"
    elif match_type == "mac":
        tag_str = " (MAC Address Matches - All Formats)"
    elif match_type == "ip_subnet":
        tag_str = " (IP / Subnet Containment Matches)"
    elif match_type == "fuzzy":
        tag_str = " (Fuzzy Matches)"
    else:
        tag_str = ""

    uniq_tag = " (Unique Files Only)" if unique_files else ""
    print(f"\n🔍 QSearch Results for '{query}' ({len(results)} matched{tag_str}{uniq_tag} in {elapsed_ms:.1f} ms):\n" + "─" * 70)
    if not results:
        print("No matches found.")
    else:
        for fname, rnum, ltext, score in results:
            print(f"[\033[1;32m{score}%\033[0m] 📄 \033[1;34m{fname}\033[0m (Row #\033[33m{rnum}\033[0m):")
            if fname.lower().endswith(".csv"):
                headers = engine.get_file_headers(fname)
                col_lines = format_record_multiline(headers, ltext)
                for cline in col_lines:
                    highlighted_cline = colorize_cli_match(cline, query, match_type, is_regex)
                    print(f"  \033[36m{highlighted_cline}\033[0m")
            else:
                highlighted_line = colorize_cli_match(ltext, query, match_type, is_regex)
                print(f"  \033[36m{highlighted_line}\033[0m")
            print()
    print("─" * 70 + "\n")


# ================= Main Entry Point =================

def main():
    parser = argparse.ArgumentParser(description="QSearch - Instant CSV & Text Search Engine")
    parser.add_argument("query", nargs="*", help="Search query keywords, MAC address (all formats), CIDR subnet (e.g. 1.0.0.0/8), or Regex")
    parser.add_argument("-d", "--dir", dest="dir", default=DEFAULT_CONTENT_DIR, help="Target directory to index and search")
    parser.add_argument("-c", "--csv", action="store_true", help="Search only CSV files")
    parser.add_argument("-t", "--text", action="store_true", help="Search only non-CSV text files (.txt, .log, etc.)")
    parser.add_argument("-a", "--all", action="store_true", help="Search all indexed text and CSV files (default)")
    parser.add_argument("-m", "--mac", action="store_true", help="Force MAC address search across all formats (1111.1111.1111, 11:11:11:11:11:11, etc.)")
    parser.add_argument("-i", "--ip", "--net", dest="ip", action="store_true", help="Force IP / Subnet search matching all IPs/subnets inside CIDR range (e.g. 1.0.0.0/8)")
    parser.add_argument("-r", "--regex", action="store_true", help="Enable regular expression matching")
    parser.add_argument("-u", "--unique", action="store_true", help="Show each matching file only once (1 match per file)")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--csv-out", dest="csv_out", help="Save search results directly to specified CSV file")
    parser.add_argument("--repl", action="store_true", help="Start continuous interactive CLI prompt")
    parser.add_argument("--cli", action="store_true", help="Force Curses/CLI mode even if GUI is available")
    parser.add_argument("--test", action="store_true", help="Run automated test suite and regression checks")

    args = parser.parse_args()

    # Case 0: Run automated test suite
    if args.test:
        test_file = SCRIPT_DIR / "test_qs.py"
        if test_file.exists():
            import runpy
            runpy.run_path(str(test_file), run_name="__main__")
            return
        else:
            print("[Error] test_qs.py not found.", file=sys.stderr)
            sys.exit(1)

    content_dir = Path(args.dir).resolve()
    content_dir.mkdir(parents=True, exist_ok=True)

    file_type = "all"
    if args.csv:
        file_type = "csv"
    elif args.text:
        file_type = "text"
    if args.all:
        # Explicit '-a/--all' takes precedence over '-c/-t' so the flag
        # actually does something instead of being a documented no-op.
        file_type = "all"

    # Case 1: Direct one-shot search
    if args.query:
        search_query = " ".join(args.query)
        out_fmt = "json" if args.json else ("csv" if args.csv_out else "text")
        run_direct_cli_search(
            query=search_query,
            content_dir=content_dir,
            file_type=file_type,
            is_regex=args.regex,
            unique_files=args.unique,
            is_mac=args.mac,
            is_ip=args.ip,
            output_format=out_fmt,
            csv_out_path=args.csv_out
        )
        return

    # Case 2: REPL prompt
    if args.repl:
        run_interactive_repl(content_dir=content_dir, file_type=file_type, unique_files=args.unique, is_mac=args.mac, is_ip=args.ip)
        return

    # Case 3: GUI Mode
    gui_launched = False
    if HAS_TKINTER and not args.cli:
        try:
            root = tk.Tk()
            app = QSearchGUIApp(root, initial_dir=content_dir)
            if args.unique:
                app.unique_var.set(True)
            if args.regex:
                app.regex_var.set(True)
            if args.mac:
                app.mac_var.set(True)
            if file_type == "csv":
                app.filter_var.set("CSV Files Only")
            elif file_type == "text":
                app.filter_var.set("Text Files Only")
            root.update_idletasks()
            root.lift()
            gui_launched = True
            root.mainloop()
        except Exception:
            gui_launched = False

    # Case 4: Curses TUI or REPL Fallback
    if not gui_launched:
        if HAS_CURSES and sys.stdin.isatty():
            try:
                curses.wrapper(lambda stdscr: run_interactive_cli(stdscr, content_dir=content_dir))
            except KeyboardInterrupt:
                sys.exit(0)
        else:
            run_interactive_repl(content_dir=content_dir, file_type=file_type, unique_files=args.unique, is_mac=args.mac, is_ip=args.ip)


if __name__ == "__main__":
    main()