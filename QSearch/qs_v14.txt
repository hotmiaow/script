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

import os
import sys
import csv
import json
import time
import queue
import sqlite3
import threading
import subprocess
import difflib
import re
import argparse
from pathlib import Path

# Increase CSV field size limit to max
try:
    csv.field_size_limit(sys.maxsize)
except Exception:
    pass

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

    # Extract unquoted words
    tokens = []
    for token in re.split(r'[\s|,;]+', unquoted):
        token_clean = token.strip().strip("()").strip()
        if not token_clean:
            continue
        if token_clean.upper() in ("AND", "OR", "NOT", "&&", "||", "|", "&"):
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
        target_path = Path(content_dir) / os.path.basename(filename)
        if not target_path.exists():
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
        target_path = Path(content_dir) / os.path.basename(filename)
        if not target_path.exists():
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
                headers TEXT
            );
        """)
        try:
            cur.execute("ALTER TABLE file_meta ADD COLUMN headers TEXT;")
        except sqlite3.OperationalError:
            pass

        # Check existing fts_idx definition
        try:
            cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='fts_idx';")
            row = cur.fetchone()
            if row:
                sql_def = row[0].lower()
                if "trigram" not in sql_def or "file_name unindexed" not in sql_def:
                    cur.execute("DROP TABLE fts_idx;")
                    cur.execute("DELETE FROM file_meta;")
        except Exception:
            pass

        # Create FTS5 virtual table
        try:
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_idx USING fts5(
                    file_name UNINDEXED,
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

    def _parse_boolean_query_sql(self, query_str: str) -> Tuple[Optional[str], Optional[str], List[str]]:
        """
        Parses query containing 'AND', 'OR', 'NOT', '|', '&' into:
        - FTS5 MATCH expression
        - Standard SQL LIKE WHERE expression
        - List of extracted keywords (for highlighting)
        """
        keywords = extract_search_keywords(query_str)
        if not keywords:
            return None, None, []

        # Split into OR branches
        or_parts = re.split(r'\s+(?:OR|or|\|)\s+', query_str)
        
        fts_or_clauses = []
        like_or_clauses = []
        like_params = []

        for or_branch in or_parts:
            and_tokens = [t.strip().strip('"').strip("'") for t in re.split(r'\s+(?:AND|and|&&|&)\s+|\s+', or_branch) if t.strip()]
            valid_and = [t for t in and_tokens if t.upper() not in ("AND", "OR", "NOT", "&&", "||", "|", "&") and not t.lower().startswith(("file:", "f:"))]
            
            if not valid_and:
                continue

            # FTS clause for this branch
            fts_tokens_branch = [f'"{t.replace(chr(34), chr(34)*2)}"' for t in valid_and if len(t) >= 3]
            if fts_tokens_branch:
                fts_or_clauses.append("(" + " AND ".join(fts_tokens_branch) + ")")

            # LIKE clause for this branch
            branch_likes = ["line_text LIKE ?" for _ in valid_and]
            like_or_clauses.append("(" + " AND ".join(branch_likes) + ")")
            like_params.extend([f"%{t}%" for t in valid_and])

        fts_query = " OR ".join(fts_or_clauses) if fts_or_clauses else None
        like_sql = "(" + " OR ".join(like_or_clauses) + ")" if like_or_clauses else None

        return fts_query, (like_sql, like_params), keywords

    def search(self, query_str, limit=300, file_type="csv", is_regex=False):
        """
        Performs multi-stage search:
        - Boolean AND / OR / NOT search (e.g. 'server OR user', 'sw01 AND 10.1')
        - Regular expression pattern matching
        - File-specific filtering (e.g. 'file:switch')
        - Multi-token LIKE fallback
        - Bounded Fuzzy search fallback
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
        file_filter = None
        cleaned_tokens = []
        for token in raw_query.split():
            if token.lower().startswith("file:") or token.lower().startswith("f:"):
                parts = token.split(":", 1)
                if len(parts) == 2 and parts[1]:
                    file_filter = parts[1].strip()
            else:
                cleaned_tokens.append(token)

        effective_query = " ".join(cleaned_tokens).strip()

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

        try:
            # Mode A: Regex Search
            if is_regex and effective_query:
                match_type = "regex"
                try:
                    cur.execute(f"""
                        SELECT file_name, row_num, line_text
                        FROM {table_name}
                        WHERE regexp(?, line_text){base_filter_sql}
                        LIMIT ?;
                    """, (effective_query, limit))
                    raw_rows = cur.fetchall()
                    results = [(r[0], r[1], r[2], 100) for r in raw_rows]
                except sqlite3.OperationalError as e:
                    print(f"[Regex Error] {e}", file=sys.stderr)
                    results = []

            # Mode B: Boolean & Multi-Token Search
            elif effective_query:
                fts_expr, (like_sql, like_params), keywords = self._parse_boolean_query_sql(effective_query)
                is_phrase = effective_query.startswith('"') and effective_query.endswith('"') and len(effective_query) >= 2

                # Stage 1: FTS5 Trigram Search
                if self.use_fts and fts_expr:
                    try:
                        cur.execute(f"""
                            SELECT file_name, row_num, line_text
                            FROM fts_idx
                            WHERE fts_idx MATCH ?{base_filter_sql}
                            LIMIT ?;
                        """, (fts_expr, limit))
                        raw = cur.fetchall()
                        # Validate short tokens (<3 chars)
                        short_keywords = [k.lower() for k in keywords if len(k) < 3]
                        if short_keywords and not (" OR " in effective_query.upper() or "|" in effective_query):
                            filtered = []
                            for r in raw:
                                l_low = r[2].lower()
                                if all(st in l_low for st in short_keywords):
                                    filtered.append((r[0], r[1], r[2], 100))
                            results = filtered[:limit]
                        else:
                            results = [(r[0], r[1], r[2], 100) for r in raw]
                    except sqlite3.Error:
                        results = []

                # Stage 2: Fast Multi-LIKE Fallback
                if not results and like_sql:
                    sql_stmt = f"SELECT file_name, row_num, line_text FROM {table_name} WHERE {like_sql}{base_filter_sql} LIMIT ?;"
                    cur.execute(sql_stmt, (*like_params, limit))
                    raw = cur.fetchall()
                    results = [(r[0], r[1], r[2], 100) for r in raw]

                # Stage 3: Bounded Fuzzy Search Fallback (only for single word queries >= 4 chars without boolean operators)
                has_boolean_ops = any(op in effective_query.upper() for op in ("OR", "AND", "NOT", "|", "&"))
                if not results and len(keywords) == 1 and len(keywords[0]) >= 4 and not is_phrase and not has_boolean_ops:
                    match_type = "fuzzy"
                    cur.execute(f"""
                        SELECT file_name, row_num, line_text, score FROM (
                            SELECT file_name, row_num, line_text, fuzzy_score(?, line_text) as score
                            FROM {table_name}
                            LIMIT 3000
                        )
                        WHERE score >= 60{base_filter_sql}
                        ORDER BY score DESC
                        LIMIT ?;
                    """, (keywords[0], limit))
                    fuzzy_raw = cur.fetchall()
                    results = [(r[0], r[1], r[2], int(r[3])) for r in fuzzy_raw]

            # If only file filter was provided with no keywords
            elif file_filter:
                cur.execute(f"""
                    SELECT file_name, row_num, line_text
                    FROM {table_name}
                    WHERE 1=1{base_filter_sql}
                    LIMIT ?;
                """, (limit,))
                raw = cur.fetchall()
                results = [(r[0], r[1], r[2], 100) for r in raw]

        except sqlite3.Error as e:
            print(f"[Search Engine Error] {e}", file=sys.stderr)
            results = []
        finally:
            conn.close()

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return results, elapsed_ms, match_type

    def get_stats(self):
        """Returns total files and total rows indexed."""
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), COALESCE(SUM(row_count), 0) FROM file_meta;")
        file_cnt, row_cnt = cur.fetchone()
        conn.close()
        return file_cnt, row_cnt


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

MAX_LINE_LENGTH = 1200


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
            if b"\x00" in chunk:
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
        self.is_indexing = False
        self.total_files = 0
        self.files_left = 0
        self.percent = 100

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
        """Checks for new, updated, or removed text files."""
        conn = self.engine.get_connection()
        cur = conn.cursor()

        cur.execute("SELECT file_path, round(mtime, 3), size FROM file_meta;")
        db_files = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

        disk_files = {}
        if self.content_dir.exists():
            for entry in self.content_dir.rglob("*"):
                if entry.is_file() and is_text_file(entry):
                    try:
                        stat = entry.stat()
                        disk_files[str(entry)] = (round(stat.st_mtime, 3), stat.st_size)
                    except OSError:
                        continue

        removed_files = set(db_files.keys()) - set(disk_files.keys())
        for rfile in removed_files:
            rel_name = os.path.relpath(rfile, self.content_dir) if str(rfile).startswith(str(self.content_dir)) else os.path.basename(rfile)
            cur.execute("DELETE FROM file_meta WHERE file_path = ?;", (rfile,))
            if self.engine.use_fts:
                cur.execute("DELETE FROM fts_idx WHERE file_name = ? OR file_name = ?;", (rel_name, os.path.basename(rfile)))
            else:
                cur.execute("DELETE FROM std_idx WHERE file_name = ? OR file_name = ?;", (rel_name, os.path.basename(rfile)))
            conn.commit()

        changed_files = [
            filepath for filepath, (mtime, size) in disk_files.items()
            if filepath not in db_files or db_files[filepath] != (mtime, size)
        ]

        has_changes = bool(changed_files or removed_files)

        if has_changes:
            total_changed = len(changed_files)
            self.total_files = total_changed
            self.files_left = total_changed
            self.is_indexing = True if total_changed > 0 else False
            self.percent = 0 if total_changed > 0 else 100

            for idx, filepath in enumerate(changed_files, start=1):
                self.index_single_file(conn, filepath)
                self.files_left = total_changed - idx
                self.percent = int((idx / total_changed) * 100)

                if self.status_callback:
                    file_cnt, row_cnt = self.engine.get_stats()
                    try:
                        self.status_callback(file_cnt, row_cnt, self.total_files, self.files_left, self.percent, self.is_indexing)
                    except TypeError:
                        self.status_callback(file_cnt, row_cnt)

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

            if self.status_callback:
                file_cnt, row_cnt = self.engine.get_stats()
                try:
                    self.status_callback(file_cnt, row_cnt, 0, 0, 100, False)
                except TypeError:
                    self.status_callback(file_cnt, row_cnt)

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

        try:
            encoding_to_try = "utf-8-sig" if ext == ".csv" else "utf-8"
            try:
                with open(filepath, "r", encoding=encoding_to_try, errors="replace") as f:
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
            except Exception:
                parsed_batch.clear()
                total_rows = 0
                headers_json = None
                with open(filepath, "r", encoding="latin-1", errors="replace") as f:
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
        except Exception as e:
            print(f"[Indexer Error] Failed to read {filepath}: {e}", file=sys.stderr)
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
                "INSERT OR REPLACE INTO file_meta (file_path, mtime, size, row_count, headers) VALUES (?, ?, ?, ?, ?);",
                (filepath, round(stat.st_mtime, 3), stat.st_size, total_rows, headers_json)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[Indexer DB Error] Failed to update DB for {filepath}: {e}", file=sys.stderr)


# ================= GUI Mode (Tkinter) =================

if HAS_TKINTER:
    class QSearchGUIApp:
        """Tkinter Application for Instant Search."""

        def __init__(self, root, initial_dir=DEFAULT_CONTENT_DIR):
            self.root = root
            self.root.title("QSearch - Instant CSV & Text Search Engine")
            self.root.geometry("980x660")
            self.minsize(720, 460)

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
            self._setup_indexer()
            self._poll_queue()

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
            self.lbl_folder_path = ttk.Label(folder_frame, text=str(self.content_dir), font=("Helvetica", 9), foreground="#333")
            self.lbl_folder_path.pack(side="left", padx=(5, 10))

            btn_browse_dir = ttk.Button(folder_frame, text="Browse Folder...", command=self._on_browse_directory)
            btn_browse_dir.pack(side="left")

            btn_open_folder = ttk.Button(folder_frame, text="Open Folder ↗", command=lambda: open_containing_folder(str(self.content_dir)))
            btn_open_folder.pack(side="left", padx=(4, 0))

            btn_save = ttk.Button(folder_frame, text="Save Results (.csv) 💾", command=self._save_results_to_csv)
            btn_save.pack(side="right")

            # Search row
            search_row = ttk.Frame(top_bar)
            search_row.pack(fill="x")

            lbl_search = ttk.Label(search_row, text="🔍 Search:", font=("Helvetica", 11, "bold"))
            lbl_search.pack(side="left", padx=(0, 6))

            self.search_var = tk.StringVar()
            self.search_entry = ttk.Entry(search_row, textvariable=self.search_var, font=("Helvetica", 12))
            self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.search_entry.focus_set()
            self.search_entry.bind("<KeyRelease>", self._on_key_release)
            self.search_entry.bind("<Down>", self._on_search_down_arrow)

            # Regex toggle
            self.regex_var = tk.BooleanVar(value=False)
            regex_cb = ttk.Checkbutton(search_row, text="Regex Mode", variable=self.regex_var, command=self._perform_search)
            regex_cb.pack(side="left", padx=(0, 8))

            # Filter mode
            self.filter_var = tk.StringVar(value="CSV Files Only")
            self.filter_cb = ttk.Combobox(
                search_row,
                textvariable=self.filter_var,
                values=["CSV Files Only", "Text Files Only", "All Indexed Files"],
                state="readonly",
                width=15
            )
            self.filter_cb.pack(side="left", padx=(0, 6))
            self.filter_cb.bind("<<ComboboxSelected>>", lambda e: self._perform_search())

            btn_clear = ttk.Button(search_row, text="Clear", command=self._clear_search)
            btn_clear.pack(side="left")

            # Main Split PanedWindow
            self.paned = ttk.PanedWindow(self.root, orient="vertical")
            self.paned.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 4))

            # Top Pane: Master Results Table
            table_frame = ttk.Frame(self.paned)
            self.paned.add(table_frame, weight=3)

            columns = ("file", "row", "content")
            self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

            self.tree.heading("file", text="File Path")
            self.tree.heading("row", text="Row #")
            self.tree.heading("content", text="Matched Content (Score In Front)")

            self.tree.column("file", width=180, minwidth=110, anchor="w")
            self.tree.column("row", width=65, minwidth=50, anchor="center")
            self.tree.column("content", width=680, minwidth=300, anchor="w")

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

            btn_copy_detail = ttk.Button(detail_top, text="Copy All Fields", command=self._copy_detail_text)
            btn_copy_detail.pack(side="right")

            txt_scroll = ttk.Scrollbar(detail_frame, orient="vertical")
            self.txt_detail = tk.Text(detail_frame, height=8, font=("Courier", 11), wrap="word", yscrollcommand=txt_scroll.set, bd=1, relief="solid")
            txt_scroll.config(command=self.txt_detail.yview)

            # Highlighting and bold tags
            self.txt_detail.tag_config("match_line", background="#FFF3CD", font=("Courier", 11, "bold"))
            self.txt_detail.tag_config("match_query", background="#FFD54F", foreground="#000000", font=("Courier", 11, "bold"))
            self.txt_detail.tag_config("fuzzy_match", background="#FFAB40", foreground="#000000", font=("Courier", 11, "bold"))
            self.txt_detail.tag_config("regex_match", background="#80D8FF", foreground="#000000", font=("Courier", 11, "bold"))

            self.txt_detail.pack(side="left", fill="both", expand=True)
            txt_scroll.pack(side="right", fill="y")

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
            self.root.bind("<Escape>", self._on_escape_pressed)

            # Right-click context menu
            self._create_context_menu()

            # Status bar
            self.status_frame = ttk.Frame(self.root, padding=6, relief="groove")
            self.status_frame.pack(side="bottom", fill="x")

            self.lbl_status = ttk.Label(self.status_frame, text="Ready | Supports 'AND', 'OR', Regex, and Fuzzy search...", font=("Helvetica", 9))
            self.lbl_status.pack(side="left", padx=5)

            self.lbl_index_stats = ttk.Label(self.status_frame, text="Index: 0 files (0 rows)", font=("Helvetica", 9), foreground="#666666")
            self.lbl_index_stats.pack(side="right", padx=5)

        def _create_context_menu(self):
            self.context_menu = tk.Menu(self.root, tearoff=0)
            self.context_menu.add_command(label="📋 Copy Matched Row", command=self._copy_selected_row)
            self.context_menu.add_command(label="📑 Copy Column Breakdown", command=self._copy_detail_text)
            self.context_menu.add_separator()
            self.context_menu.add_command(label="🖥️ Open File in Default App", command=self._open_selected_file)
            self.context_menu.add_command(label="📂 Open Containing Folder", command=self._open_selected_folder)

            self.tree.bind("<Button-3>", self._show_context_menu)
            self.tree.bind("<Button-2>", self._show_context_menu)

        def _show_context_menu(self, event):
            row_id = self.tree.identify_row(event.y)
            if row_id:
                self.tree.selection_set(row_id)
                self.context_menu.post(event.x_root, event.y_root)

        def _setup_indexer(self):
            def on_stats_update(file_cnt, row_cnt, total_files=0, files_left=0, percent=100, is_indexing=False):
                self._msg_queue.put(("stats", (file_cnt, row_cnt, total_files, files_left, percent, is_indexing)))

            self.indexer = BackgroundIndexer(self.engine, content_dir=self.content_dir, status_callback=on_stats_update)
            self.indexer.start()

            fc, rc = self.engine.get_stats()
            self._update_stats_display(fc, rc)

        def _on_browse_directory(self):
            path = filedialog.askdirectory(initialdir=str(self.content_dir), title="Select Folder to Index & Search")
            if path:
                self.content_dir = Path(path).resolve()
                self.lbl_folder_path.config(text=str(self.content_dir))
                self.indexer.update_content_dir(self.content_dir)
                self.lbl_status.config(text=f"Switched directory to: {self.content_dir}. Re-indexing...")
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

        def _update_stats_display(self, file_cnt, row_cnt, total_files=0, files_left=0, percent=100, is_indexing=False):
            filter_mode = self.filter_var.get() if hasattr(self, 'filter_var') else "CSV Files Only"
            if is_indexing and files_left > 0:
                self.lbl_index_stats.config(
                    text=f"⚡ Indexing: {percent}% ({files_left} file(s) left) | {file_cnt} indexed ({row_cnt:,} rows)",
                    foreground="#D97706"
                )
            else:
                self.lbl_index_stats.config(
                    text=f"Indexed: {file_cnt} file(s), {row_cnt:,} rows | Filter: {filter_mode}",
                    foreground="#666666"
                )

        def _on_key_release(self, event):
            if event.keysym in ("Up", "Down", "Left", "Right", "Return", "Escape", "Control_L", "Control_R"):
                return
            if self._debounce_job:
                self.root.after_cancel(self._debounce_job)
            
            q_len = len(self.search_var.get().strip())
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
                self.txt_detail.config(state="normal")
                self.txt_detail.delete("1.0", tk.END)
                self._current_results = []
                self.lbl_status.config(text="Ready | Type keywords...")
                self.btn_load_full.pack_forget()
                return

            filter_mode = self.filter_var.get() if hasattr(self, 'filter_var') else "CSV Files Only"
            if filter_mode == "Text Files Only":
                file_type = "text"
            elif filter_mode == "All Indexed Files":
                file_type = "all"
            else:
                file_type = "csv"

            is_regex = self.regex_var.get()

            with self._search_lock:
                self._search_counter += 1
                current_counter = self._search_counter

            self.lbl_status.config(text=f"Searching for '{query}'...")

            def search_worker(q, ftype, regex_flag, counter):
                results, elapsed_ms, match_type = self.engine.search(q, limit=300, file_type=ftype, is_regex=regex_flag)
                self._msg_queue.put(("search_results", (results, elapsed_ms, match_type, q, counter)))

            threading.Thread(target=search_worker, args=(query, file_type, is_regex, current_counter), daemon=True).start()

        def _apply_search_results(self, results, elapsed_ms, match_type, query):
            for item in self.tree.get_children():
                self.tree.delete(item)

            self.txt_detail.config(state="normal")
            self.txt_detail.delete("1.0", tk.END)
            self._current_results = results
            self._active_match_type = match_type

            # Insert results putting matching percentage in front of the line
            for fname, rnum, ltext, score in results:
                disp_text = f"[{score}%] {ltext}"
                self.tree.insert("", "end", values=(fname, rnum, disp_text))

            count = len(results)
            limit_notice = " (showing top 300)" if count >= 300 else ""
            tag = " (Regex Matches)" if match_type == "regex" else (" (Fuzzy Matches)" if match_type == "fuzzy" else "")
            self.lbl_status.config(text=f"Found {count} match(es){tag}{limit_notice} in {elapsed_ms:.1f} ms for '{query}'")

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

            # Case C: Exact / Multi-token / Boolean Search Highlighting
            keywords = extract_search_keywords(query)
            for kw in keywords:
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
                        self.lbl_detail_header.config(text=f"[{score}%] 📄 {fname} (Line #{rnum})")

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
                            self.lbl_status.config(text=f"Match Score: {score}% | {fname}:L{rnum}")
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
                self.lbl_status.config(text="Copied row content to clipboard!")

        def _copy_detail_text(self):
            content = self.txt_detail.get("1.0", "end-1c").strip()
            if content:
                self.root.clipboard_clear()
                self.root.clipboard_append(content)
                self.lbl_status.config(text="Copied column breakdown to clipboard!")

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
                self.lbl_status.config(text=f"Successfully saved {len(self._current_results)} results to '{filename_only}'")
                messagebox.showinfo("Save Complete", f"Successfully saved {len(self._current_results)} search results to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save results:\n{e}")

        def _on_escape_pressed(self, event=None):
            self._clear_search()


# ================= CLI Mode (Curses TUI & Interactive REPL) =================

def colorize_cli_match(text: str, query: str, match_type: str, is_regex: bool) -> str:
    """Highlights and bolds matched keywords or patterns in terminal output with ANSI colors."""
    if not query or not text:
        return text

    if is_regex or match_type == "regex":
        try:
            return re.sub(f"({query})", r"\033[1;93;4m\1\033[0m", text, flags=re.IGNORECASE)
        except Exception:
            return text

    if match_type == "fuzzy":
        fwords = get_fuzzy_matched_words(query, text)
        result = text
        for fw in fwords:
            pattern = re.escape(fw)
            result = re.sub(f"({pattern})", r"\033[1;91;4m\1\033[0m", result, flags=re.IGNORECASE)
        return result

    keywords = extract_search_keywords(query)
    result = text
    for kw in keywords:
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

    filter_modes = ["csv", "text", "all"]
    filter_idx = 0

    query = ""
    selected_idx = 0
    results = []
    elapsed_ms = 0.0
    match_type = "exact"
    is_regex = False

    while True:
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        header = f" QSearch TUI [{content_dir}] "
        stdscr.addstr(0, 0, header.center(max_x), curses.A_REVERSE | curses.A_BOLD)

        prompt = "🔍 Search > "
        stdscr.addstr(2, 2, prompt, curses.A_BOLD)
        stdscr.addstr(2, 2 + len(prompt), query)

        fc, rc = engine.get_stats()
        if indexer.is_indexing and indexer.files_left > 0:
            idx_str = f"Indexing: {indexer.percent}% ({indexer.files_left} left)"
        else:
            idx_str = f"Index: {fc} files ({rc:,} rows)"

        mode_label = {"csv": "CSV Only", "text": "Text Only", "all": "All Files"}[filter_modes[filter_idx]]
        reg_label = " [Regex: ON]" if is_regex else ""

        if results and 0 <= selected_idx < len(results):
            sel_score = results[selected_idx][3]
            type_str = f" [Score: {sel_score}%]"
        else:
            type_str = " (Regex)" if match_type == "regex" else (" (Fuzzy)" if match_type == "fuzzy" else "")

        info_str = f" Matches: {len(results)}{type_str}{reg_label} | Time: {elapsed_ms:.1f}ms | Filter: {mode_label} [Tab/f] | {idx_str} "
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
                # Put matching percentage in front of the line
                line_disp = f"[{score}%] [{fname}:L{rnum}] {ltext}"
                line_disp = line_disp[:max_x - 4]

                if idx == selected_idx:
                    stdscr.addstr(row_y, 2, line_disp, curses.A_STANDOUT | curses.A_BOLD)
                else:
                    stdscr.addstr(row_y, 2, line_disp)

        footer = " [Esc: Clear | Enter: Open | r: Regex | Tab/f: Filter | c: Copy | s: Save | Up/Down: Select] "
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
        elif ch in (ord('r'), ord('R')): # Toggle Regex
            is_regex = not is_regex
            if query:
                results, elapsed_ms, match_type = engine.search(query, file_type=filter_modes[filter_idx], is_regex=is_regex)
                selected_idx = 0
        elif ch in (9, ord('\t'), ord('f'), ord('F')): # Tab or 'f' key toggles file filter
            filter_idx = (filter_idx + 1) % len(filter_modes)
            if query:
                results, elapsed_ms, match_type = engine.search(query, file_type=filter_modes[filter_idx], is_regex=is_regex)
                selected_idx = 0
        elif ch in (10, 13, getattr(curses, "KEY_ENTER", 10)): # Enter opens file
            if results and 0 <= selected_idx < len(results):
                fname = results[selected_idx][0]
                open_file_in_default_app(fname, content_dir=content_dir)
        elif ch in (ord('c'), ord('C')): # Copy record
            if results and 0 <= selected_idx < len(results):
                fname, rnum, ltext, score = results[selected_idx]
                headers = engine.get_file_headers(fname)
                col_lines = format_record_multiline(headers, ltext)
                formatted_text = f"[{score}%] 📄 {fname} (Row #{rnum})\n" + "\n".join(col_lines)
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
        elif ch in (ord('s'), ord('S')): # Save to CSV
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
                results, elapsed_ms, match_type = engine.search(query, file_type=filter_modes[filter_idx], is_regex=is_regex)
                selected_idx = 0
        elif ch == curses.KEY_UP:
            if selected_idx > 0:
                selected_idx -= 1
        elif ch == curses.KEY_DOWN:
            if selected_idx < len(results) - 1:
                selected_idx += 1
        elif 32 <= ch <= 126:
            query += chr(ch)
            results, elapsed_ms, match_type = engine.search(query, file_type=filter_modes[filter_idx], is_regex=is_regex)
            selected_idx = 0


def run_interactive_repl(content_dir=DEFAULT_CONTENT_DIR, file_type="csv"):
    """Continuous REPL prompt for terminal users without curses."""
    engine = SearchEngine(content_dir=content_dir)
    indexer = BackgroundIndexer(engine, content_dir=content_dir)
    indexer.sync_content_directory()

    print("=" * 65)
    print(f"  QSearch Interactive CLI REPL (Directory: {content_dir})")
    print("  Type query (supports 'AND', 'OR', Regex) | :filter [csv|text|all] | :open <row> | :quit")
    print("=" * 65)

    last_results = []
    current_ftype = file_type
    is_regex = False

    while True:
        try:
            reg_status = " [Regex]" if is_regex else ""
            cmd = input(f"\nqs ({current_ftype}){reg_status}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting QSearch.")
            break

        if not cmd:
            continue
        if cmd in (":quit", ":q", "exit", "quit"):
            break
        if cmd == ":regex":
            is_regex = not is_regex
            print(f"[Regex mode: {'ON' if is_regex else 'OFF'}]")
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

        results, elapsed_ms, match_type = engine.search(cmd, limit=50, file_type=current_ftype, is_regex=is_regex)
        last_results = results

        tag_str = " (Regex)" if match_type == "regex" else (" (Fuzzy)" if match_type == "fuzzy" else "")
        print(f"\n🔍 Found {len(results)} match(es){tag_str} in {elapsed_ms:.1f} ms:")
        print("─" * 70)
        if not results:
            print("No matches found.")
        else:
            for i, (fname, rnum, ltext, score) in enumerate(results[:25], 1):
                highlighted_text = colorize_cli_match(ltext, cmd, match_type, is_regex)
                print(f"[\033[1;32m{score}%\033[0m] [{i}] \033[1;34m{fname}\033[0m:L\033[33m{rnum}\033[0m ➔ {highlighted_text}")
            if len(results) > 25:
                print(f"... and {len(results) - 25} more matches.")
        print("─" * 70)


def run_direct_cli_search(query, content_dir=DEFAULT_CONTENT_DIR, file_type="csv", is_regex=False, output_format="text", csv_out_path=None):
    """Executes single search query directly from terminal arguments with front percentage & keyword highlighting."""
    engine = SearchEngine(content_dir=content_dir)

    indexer = BackgroundIndexer(engine, content_dir=content_dir)
    indexer.sync_content_directory()

    results, elapsed_ms, match_type = engine.search(query, limit=100, file_type=file_type, is_regex=is_regex)

    # Format 1: JSON Output
    if output_format == "json":
        json_data = {
            "query": query,
            "count": len(results),
            "elapsed_ms": round(elapsed_ms, 2),
            "match_type": match_type,
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
    tag_str = " (Regex Matches)" if match_type == "regex" else (" (Fuzzy Matches)" if match_type == "fuzzy" else "")
    print(f"\n🔍 QSearch Results for '{query}' ({len(results)} matched{tag_str} in {elapsed_ms:.1f} ms):\n" + "─" * 70)
    if not results:
        print("No matches found.")
    else:
        for fname, rnum, ltext, score in results:
            headers = engine.get_file_headers(fname)
            col_lines = format_record_multiline(headers, ltext)
            print(f"[\033[1;32m{score}%\033[0m] 📄 \033[1;34m{fname}\033[0m (Row #\033[33m{rnum}\033[0m):")
            for cline in col_lines:
                highlighted_cline = colorize_cli_match(cline, query, match_type, is_regex)
                print(f"  \033[36m{highlighted_cline}\033[0m")
            print()
    print("─" * 70 + "\n")


# ================= Main Entry Point =================

def main():
    parser = argparse.ArgumentParser(description="QSearch - Instant CSV & Text Search Engine")
    parser.add_argument("query", nargs="*", help="Search query keywords or pattern (supports 'AND', 'OR', Regex)")
    parser.add_argument("-d", "--dir", dest="dir", default=DEFAULT_CONTENT_DIR, help="Target directory to index and search")
    parser.add_argument("-c", "--csv", action="store_true", help="Search only CSV files (default)")
    parser.add_argument("-t", "--text", action="store_true", help="Search only non-CSV text files (.txt, .log, etc.)")
    parser.add_argument("-a", "--all", action="store_true", help="Search all indexed text and CSV files")
    parser.add_argument("-r", "--regex", action="store_true", help="Enable regular expression matching")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--csv-out", dest="csv_out", help="Save search results directly to specified CSV file")
    parser.add_argument("--repl", action="store_true", help="Start continuous interactive CLI prompt")
    parser.add_argument("--cli", action="store_true", help="Force Curses/CLI mode even if GUI is available")

    args = parser.parse_args()

    content_dir = Path(args.dir).resolve()
    content_dir.mkdir(parents=True, exist_ok=True)

    file_type = "csv"
    if args.text:
        file_type = "text"
    elif args.all:
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
            output_format=out_fmt,
            csv_out_path=args.csv_out
        )
        return

    # Case 2: REPL prompt
    if args.repl:
        run_interactive_repl(content_dir=content_dir, file_type=file_type)
        return

    # Case 3: GUI Mode
    gui_launched = False
    if HAS_TKINTER and not args.cli:
        try:
            root = tk.Tk()
            root.withdraw()
            root.deiconify()
            app = QSearchGUIApp(root, initial_dir=content_dir)
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
            run_interactive_repl(content_dir=content_dir, file_type=file_type)


if __name__ == "__main__":
    main()
