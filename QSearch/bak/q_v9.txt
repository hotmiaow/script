#!/usr/bin/env python3
"""
QSearch - Instant CSV Quick Search Application
Zero-dependency instant search engine for CSV files using Python Tkinter / Curses CLI + SQLite FTS5.
Supports automatic fallback to Interactive Terminal CLI if Tkinter or display is unavailable.
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
from pathlib import Path

# Try importing Tkinter safely for GUI mode
HAS_TKINTER = False
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

# Try importing curses for CLI mode
HAS_CURSES = False
try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False


# ================= Configuration & Paths =================

SCRIPT_DIR = Path(__file__).parent.resolve()
CONTENT_DIR = SCRIPT_DIR / "content"
DB_PATH = SCRIPT_DIR / "qs_index.db"

# Ensure content directory exists
CONTENT_DIR.mkdir(parents=True, exist_ok=True)


def _fuzzy_score(query, text):
    """Calculates fuzzy similarity ratio (0-100) between query and text line."""
    if not query or not text:
        return 0
    q = query.lower().strip()
    t = text.lower().strip()

    if q in t:
        return 100

    words = [w for w in t.replace('|', ' ').replace(',', ' ').replace(';', ' ').split() if len(w) >= 2]
    best_score = 0
    for w in words:
        ratio = difflib.SequenceMatcher(None, q, w).ratio()
        score = int(ratio * 100)
        if score > best_score:
            best_score = score
    return best_score


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


def open_file_in_default_app(filename):
    """Opens a file using the operating system's default viewer."""
    if not filename:
        return False

    target_path = Path(filename)
    if not target_path.is_absolute() or not target_path.exists():
        target_path = CONTENT_DIR / os.path.basename(filename)

    if not target_path.exists():
        return False

    filepath_str = str(target_path.resolve())
    try:
        if sys.platform == "darwin":  # macOS
            subprocess.Popen(["open", filepath_str])
        elif sys.platform == "win32":  # Windows
            os.startfile(filepath_str)
        else:  # Linux/Unix
            subprocess.Popen(["xdg-open", filepath_str])
        return True
    except Exception as e:
        print(f"[Open Error] {e}", file=sys.stderr)
        return False


# ================= Database & Indexer Engine =================

class SearchEngine:
    """Manages SQLite database index and queries."""

    def __init__(self, db_path=DB_PATH):
        self.db_path = str(db_path)
        self.use_fts = True
        self._init_db()

    def get_connection(self):
        """Returns a thread-safe connection to SQLite with registered fuzzy functions."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.create_function("fuzzy_score", 2, _fuzzy_score)
        return conn

    def _init_db(self):
        """Initializes database schema with FTS5 trigram support or fallback."""
        conn = self.get_connection()
        cur = conn.cursor()

        # Metadata table to track file modifications and headers
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

        # Check if existing fts_idx table uses trigram tokenizer and file_name UNINDEXED; if not, recreate it
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

        # Try creating FTS5 table with trigram tokenizer for middle substring search
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
            # Fallback to standard indexed table if FTS5 is unavailable
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
        """Retrieves column header names for a CSV file."""
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT headers FROM file_meta WHERE file_path LIKE ?;", (f"%{file_name}",))
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except Exception:
                pass
        return []

    def search(self, query_str, limit=300):
        """Performs multi-stage search (Exact/Substring + Fast SQL LIKE Fallback + Bounded Fuzzy)."""
        query_str = query_str.strip()
        if not query_str:
            return [], 0.0, "exact"

        start_time = time.perf_counter()
        conn = self.get_connection()
        cur = conn.cursor()

        results = []
        match_type = "exact"
        words = query_str.split()

        try:
            # Stage 1: Exact FTS5 Trigram Substring/Phrase Search (requires len >= 3)
            if self.use_fts and len(query_str) >= 3:
                try:
                    safe_q = query_str.replace('"', '""')
                    trigram_query = f'"{safe_q}"'

                    cur.execute("""
                        SELECT file_name, row_num, line_text 
                        FROM fts_idx 
                        WHERE fts_idx MATCH ? 
                        LIMIT ?;
                    """, (trigram_query, limit))
                    raw_exact = cur.fetchall()
                    results = [(r[0], r[1], r[2], 100) for r in raw_exact]
                except sqlite3.Error:
                    results = []

            # Stage 2: Fast SQL LIKE Fallback (handles <3 char queries, dots, symbols, or FTS misses)
            if not results:
                table_name = "fts_idx" if self.use_fts else "std_idx"
                cur.execute(f"""
                    SELECT file_name, row_num, line_text 
                    FROM {table_name} 
                    WHERE line_text LIKE ? 
                    LIMIT ?;
                """, (f"%{query_str}%", limit))
                raw_exact = cur.fetchall()
                results = [(r[0], r[1], r[2], 100) for r in raw_exact]

            # Stage 3: Bounded Fuzzy Search Fallback (only for single-word queries >= 4 chars with sample cap)
            if not results and len(words) == 1 and len(query_str) >= 4:
                match_type = "fuzzy"
                table_name = "fts_idx" if self.use_fts else "std_idx"
                cur.execute(f"""
                    SELECT file_name, row_num, line_text, score FROM (
                        SELECT file_name, row_num, line_text, fuzzy_score(?, line_text) as score
                        FROM {table_name}
                        LIMIT 2000
                    )
                    WHERE score >= 60
                    ORDER BY score DESC
                    LIMIT ?;
                """, (query_str, limit))
                fuzzy_raw = cur.fetchall()
                results = [(r[0], r[1], r[2], int(r[3])) for r in fuzzy_raw]

        except sqlite3.Error:
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

    def rebuild_and_vacuum(self):
        """Forces full FTS index optimization and compacts database file via VACUUM."""
        conn = self.get_connection()
        cur = conn.cursor()
        if self.use_fts:
            try:
                cur.execute("INSERT INTO fts_idx(fts_idx) VALUES('optimize');")
                conn.commit()
            except Exception:
                pass
        cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        cur.execute("VACUUM;")
        conn.commit()
        conn.close()


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

MAX_LINE_LENGTH = 1000


def is_text_file(filepath):
    """Determines whether a file is a text-based file by checking extension and content bytes."""
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
    """Background worker thread to continuously track and index CSV, TXT, and LOG files."""

    def __init__(self, engine, status_callback=None, poll_interval=2.0):
        super().__init__(daemon=True)
        self.engine = engine
        self.status_callback = status_callback
        self.poll_interval = poll_interval
        self._running = True
        self.is_indexing = False
        self.total_files = 0
        self.files_left = 0
        self.percent = 100

    def run(self):
        while self._running:
            try:
                self.sync_content_directory()
            except Exception as e:
                print(f"[BackgroundIndexer Error] {e}", file=sys.stderr)
            time.sleep(self.poll_interval)

    def sync_content_directory(self):
        """Checks for new, updated, or removed text files."""
        conn = self.engine.get_connection()
        cur = conn.cursor()

        # Get existing index metadata
        cur.execute("SELECT file_path, mtime, size FROM file_meta;")
        db_files = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

        # Scan filesystem recursively
        disk_files = {}
        if CONTENT_DIR.exists():
            for entry in CONTENT_DIR.rglob("*"):
                if entry.is_file() and is_text_file(entry):
                    try:
                        stat = entry.stat()
                        disk_files[str(entry)] = (stat.st_mtime, stat.st_size)
                    except OSError:
                        continue

        # Files to remove
        removed_files = set(db_files.keys()) - set(disk_files.keys())
        for rfile in removed_files:
            rel_name = os.path.relpath(rfile, CONTENT_DIR) if str(rfile).startswith(str(CONTENT_DIR)) else os.path.basename(rfile)
            cur.execute("DELETE FROM file_meta WHERE file_path = ?;", (rfile,))
            if self.engine.use_fts:
                cur.execute("DELETE FROM fts_idx WHERE file_name = ?;", (rel_name,))
                cur.execute("DELETE FROM fts_idx WHERE file_name = ?;", (os.path.basename(rfile),))
            else:
                cur.execute("DELETE FROM std_idx WHERE file_name = ?;", (rel_name,))
                cur.execute("DELETE FROM std_idx WHERE file_name = ?;", (os.path.basename(rfile),))
            conn.commit()

        # Files to add/update
        changed_files = [
            filepath for filepath, (mtime, size) in disk_files.items()
            if filepath not in db_files or db_files[filepath] != (mtime, size)
        ]

        if changed_files or removed_files:
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

            # Optimize FTS5 index segments and truncate WAL checkpoint
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

    def index_single_file(self, conn, filepath):
        """Reads and indexes a single text file into SQLite."""
        rel_name = os.path.relpath(filepath, CONTENT_DIR) if str(filepath).startswith(str(CONTENT_DIR)) else os.path.basename(filepath)
        stat = os.stat(filepath)
        ext = os.path.splitext(filepath)[1].lower()

        cur = conn.cursor()
        cur.execute("DELETE FROM file_meta WHERE file_path = ?;", (filepath,))
        if self.engine.use_fts:
            cur.execute("DELETE FROM fts_idx WHERE file_name = ?;", (rel_name,))
            cur.execute("DELETE FROM fts_idx WHERE file_name = ?;", (os.path.basename(filepath),))
        else:
            cur.execute("DELETE FROM std_idx WHERE file_name = ?;", (rel_name,))
            cur.execute("DELETE FROM std_idx WHERE file_name = ?;", (os.path.basename(filepath),))

        batch = []
        batch_size = 5000
        total_rows = 0
        headers_json = None

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                if ext == ".csv":
                    reader = csv.reader(f)
                    for line_idx, row in enumerate(reader, start=1):
                        if line_idx == 1:
                            headers_json = json.dumps(row)
                        line_str = " | ".join(row).strip()
                        if line_str:
                            if len(line_str) > MAX_LINE_LENGTH:
                                line_str = line_str[:MAX_LINE_LENGTH]
                            batch.append((rel_name, line_idx, line_str))
                            total_rows += 1

                        if len(batch) >= batch_size:
                            self._insert_batch(cur, batch)
                            batch.clear()
                else:  # .txt or .log
                    for line_idx, line in enumerate(f, start=1):
                        line_str = line.strip()
                        if line_str:
                            if len(line_str) > MAX_LINE_LENGTH:
                                line_str = line_str[:MAX_LINE_LENGTH]
                            batch.append((rel_name, line_idx, line_str))
                            total_rows += 1

                        if len(batch) >= batch_size:
                            self._insert_batch(cur, batch)
                            batch.clear()

                if batch:
                    self._insert_batch(cur, batch)

            cur.execute(
                "INSERT OR REPLACE INTO file_meta (file_path, mtime, size, row_count, headers) VALUES (?, ?, ?, ?, ?);",
                (filepath, stat.st_mtime, stat.st_size, total_rows, headers_json)
            )
            conn.commit()

        except Exception as e:
            print(f"[Indexer Error] Failed to index {filepath}: {e}", file=sys.stderr)

    def _insert_batch(self, cur, batch):
        if self.engine.use_fts:
            cur.executemany("INSERT INTO fts_idx (file_name, row_num, line_text) VALUES (?, ?, ?);", batch)
        else:
            cur.executemany("INSERT INTO std_idx (file_name, row_num, line_text) VALUES (?, ?, ?);", batch)


# ================= GUI Mode (Tkinter) =================

if HAS_TKINTER:
    class QSearchGUIApp:
        """Tkinter Application for Real-Time Search."""

        def __init__(self, root):
            self.root = root
            self.root.title("QSearch - Instant CSV Search")
            self.root.geometry("900x600")
            self.root.minsize(650, 400)

            self.engine = SearchEngine()
            self._debounce_job = None
            self._msg_queue = queue.Queue()
            self._current_results = []

            self._setup_ui()
            self._setup_indexer()
            self._poll_queue()

        def _setup_ui(self):
            style = ttk.Style()
            if "aqua" in style.theme_names():
                style.theme_use("aqua")

            top_frame = ttk.Frame(self.root, padding=12)
            top_frame.pack(side="top", fill="x")

            lbl_search = ttk.Label(top_frame, text="🔍 Search:", font=("System", 12, "bold"))
            lbl_search.pack(side="left", padx=(0, 8))

            self.search_var = tk.StringVar()
            self.search_entry = ttk.Entry(top_frame, textvariable=self.search_var, font=("System", 13))
            self.search_entry.pack(side="left", fill="x", expand=True)
            self.search_entry.focus_set()
            self.search_entry.bind("<KeyRelease>", self._on_key_release)

            btn_save = ttk.Button(top_frame, text="Save Results (.csv)", command=self._save_results_to_csv)
            btn_save.pack(side="right", padx=(6, 0))

            btn_clear = ttk.Button(top_frame, text="Clear", command=self._clear_search)
            btn_clear.pack(side="right", padx=(4, 0))

            # Main Split PanedWindow (Top: Master List, Bottom: Detail Panel)
            self.paned = ttk.PanedWindow(self.root, orient="vertical")
            self.paned.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 6))

            # Top Pane: Master List Table
            table_frame = ttk.Frame(self.paned)
            self.paned.add(table_frame, weight=3)

            columns = ("file", "row", "content")
            self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

            self.tree.heading("file", text="File Path")
            self.tree.heading("row", text="Row #")
            self.tree.heading("content", text="Matched Record")

            self.tree.column("file", width=160, minwidth=100, anchor="w")
            self.tree.column("row", width=60, minwidth=50, anchor="center")
            self.tree.column("content", width=650, minwidth=300, anchor="w")

            scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=scrollbar.set)

            self.tree.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            # Bottom Pane: Detail View (Multi-Line Column Breakdown)
            detail_frame = ttk.LabelFrame(self.paned, text=" 📄 Record Details & Column Breakdown (Selectable & Copyable) ", padding=8)
            self.paned.add(detail_frame, weight=2)

            detail_top = ttk.Frame(detail_frame)
            detail_top.pack(fill="x", pady=(0, 4))
            self.lbl_detail_header = ttk.Label(detail_top, text="Select a record above to view columns line-by-line", font=("System", 11, "bold"))
            self.lbl_detail_header.pack(side="left")

            btn_copy_detail = ttk.Button(detail_top, text="Copy All Fields", command=self._copy_detail_text)
            btn_copy_detail.pack(side="right")

            txt_scroll = ttk.Scrollbar(detail_frame, orient="vertical")
            self.txt_detail = tk.Text(detail_frame, height=8, font=("Courier", 12), wrap="word", yscrollcommand=txt_scroll.set, bd=1, relief="solid")
            txt_scroll.config(command=self.txt_detail.yview)

            self.txt_detail.tag_config("match_line", background="#FFF3CD", font=("Courier", 12, "bold"))
            self.txt_detail.tag_config("match_query", background="#FFD54F", foreground="#000000", font=("Courier", 12, "bold"))

            self.txt_detail.pack(side="left", fill="both", expand=True)
            txt_scroll.pack(side="right", fill="y")

            self.tree.bind("<Double-1>", self._on_row_double_click)
            self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
            self.tree.bind("<Return>", self._on_enter_pressed)
            self.tree.bind("<Escape>", self._on_escape_pressed)
            self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
            self.search_entry.bind("<Return>", self._on_enter_pressed)
            self.search_entry.bind("<Escape>", self._on_escape_pressed)
            self.root.bind("<Escape>", self._on_escape_pressed)

            self.status_frame = ttk.Frame(self.root, padding=6, relief="groove")
            self.status_frame.pack(side="bottom", fill="x")

            self.lbl_status = ttk.Label(self.status_frame, text="Ready | Type to search... (Press Enter to open file)", font=("System", 10))
            self.lbl_status.pack(side="left", padx=5)

            self.lbl_index_stats = ttk.Label(self.status_frame, text="Index: 0 files (0 rows)", font=("System", 10), foreground="#666666")
            self.lbl_index_stats.pack(side="right", padx=5)

        def _setup_indexer(self):
            def on_stats_update(file_cnt, row_cnt, total_files=0, files_left=0, percent=100, is_indexing=False):
                self._msg_queue.put(("stats", (file_cnt, row_cnt, total_files, files_left, percent, is_indexing)))

            self.indexer = BackgroundIndexer(self.engine, status_callback=on_stats_update)
            self.indexer.start()

            fc, rc = self.engine.get_stats()
            self._update_stats_display(fc, rc)

        def _poll_queue(self):
            try:
                while True:
                    msg_type, data = self._msg_queue.get_nowait()
                    if msg_type == "stats":
                        self._update_stats_display(*data)
            except queue.Empty:
                pass
            self.root.after(150, self._poll_queue)

        def _update_stats_display(self, file_cnt, row_cnt, total_files=0, files_left=0, percent=100, is_indexing=False):
            if is_indexing and files_left > 0:
                self.lbl_index_stats.config(
                    text=f"⚡ Indexing: {percent}% ({files_left} file(s) left) | {file_cnt} indexed ({row_cnt:,} rows)",
                    foreground="#D97706"
                )
            else:
                self.lbl_index_stats.config(
                    text=f"Indexed: {file_cnt} file(s), {row_cnt:,} rows | Folder: ./content",
                    foreground="#666666"
                )

        def _on_key_release(self, event):
            if event.keysym in ("Up", "Down", "Left", "Right", "Return", "Escape"):
                return
            if self._debounce_job:
                self.root.after_cancel(self._debounce_job)
            self._debounce_job = self.root.after(30, self._perform_search)

        def _perform_search(self):
            query = self.search_var.get().strip()
            for item in self.tree.get_children():
                self.tree.delete(item)

            self.txt_detail.config(state="normal")
            self.txt_detail.delete("1.0", tk.END)

            if not query:
                self._current_results = []
                self.lbl_status.config(text="Ready | Type to search...")
                return

            results, elapsed_ms, match_type = self.engine.search(query, limit=300)
            self._current_results = results

            for fname, rnum, ltext, score in results:
                disp_text = f"{ltext} ({score}% match)" if score < 100 else ltext
                self.tree.insert("", "end", values=(fname, rnum, disp_text))

            count = len(results)
            limit_notice = " (showing top 300)" if count >= 300 else ""
            tag = " (Fuzzy Matches)" if match_type == "fuzzy" else ""
            self.lbl_status.config(text=f"Found {count} match(es){tag}{limit_notice} in {elapsed_ms:.1f} ms for '{query}'")

            # Select first item automatically
            children = self.tree.get_children()
            if children:
                self.tree.selection_set(children[0])
                self.tree.focus(children[0])

        def _highlight_text_query(self, query):
            if not query:
                return
            tokens = [query.lower()] if " " in query else [t.strip().lower() for t in query.split() if len(t.strip()) >= 2]
            if not tokens:
                tokens = [query.lower()]

            for token in tokens:
                start_pos = "1.0"
                while True:
                    start_pos = self.txt_detail.search(token, start_pos, stopindex=tk.END, nocase=True)
                    if not start_pos:
                        break
                    end_pos = f"{start_pos}+{len(token)}c"
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

                        # Locate target file path on disk
                        target_path = Path(fname)
                        if not target_path.is_absolute() or not target_path.exists():
                            target_path = CONTENT_DIR / fname
                            if not target_path.exists():
                                matches = list(CONTENT_DIR.rglob(os.path.basename(fname)))
                                if matches:
                                    target_path = matches[0]

                        ext = target_path.suffix.lower()
                        score_info = f" ({score}% Match)" if score < 100 else ""
                        self.lbl_detail_header.config(text=f"📄 {fname} (Line #{rnum}){score_info}")

                        self.txt_detail.config(state="normal")
                        self.txt_detail.delete("1.0", tk.END)

                        if ext != ".csv" and target_path.exists():
                            try:
                                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                                    lines = f.readlines()

                                target_line_idx = None
                                for l_idx, line in enumerate(lines, start=1):
                                    line_prefix = f"L{l_idx:<4d} │ "
                                    l_start = self.txt_detail.index("end-1c")
                                    self.txt_detail.insert(tk.END, f"{line_prefix}{line}")
                                    l_end = self.txt_detail.index("end-1c")

                                    if l_idx == rnum:
                                        target_line_idx = l_start
                                        self.txt_detail.tag_add("match_line", l_start, l_end)

                                if query:
                                    self._highlight_text_query(query)

                                # Auto-scroll / jump to matched line
                                if target_line_idx:
                                    self.txt_detail.see(target_line_idx)
                                else:
                                    self.txt_detail.see(f"{rnum}.0")

                            except Exception as e:
                                self.txt_detail.insert(tk.END, f"Error reading text file: {e}")
                        else:
                            # CSV format
                            col_lines = format_record_multiline(headers, ltext)
                            self.txt_detail.insert(tk.END, "\n".join(col_lines))
                            if query:
                                self._highlight_text_query(query)

                        if score < 100:
                            self.lbl_status.config(text=f"Fuzzy Match Confidence: {score}% | {fname}:L{rnum}")
                except Exception as e:
                    print(f"[Select Error] {e}", file=sys.stderr)

        def _on_tree_click(self, event):
            self.root.after(10, self._on_tree_select)

        def _copy_detail_text(self):
            content = self.txt_detail.get("1.0", "end-1c").strip()
            if content:
                self.root.clipboard_clear()
                self.root.clipboard_append(content)
                self.lbl_status.config(text="Copied column details to clipboard!")

        def _clear_search(self):
            self.search_var.set("")
            self._perform_search()
            self.search_entry.focus_set()

        def _on_row_double_click(self, event):
            selected = self.tree.selection()
            if selected:
                item = self.tree.item(selected[0])
                content = item["values"][2]
                self.root.clipboard_clear()
                self.root.clipboard_append(str(content))
                self.lbl_status.config(text="Copied row content to clipboard!")

        def _on_enter_pressed(self, event):
            selected = self.tree.selection()
            if not selected:
                children = self.tree.get_children()
                if children:
                    selected = [children[0]]

            if selected:
                item = self.tree.item(selected[0])
                fname = item["values"][0]
                if open_file_in_default_app(fname):
                    self.lbl_status.config(text=f"Opened file: {fname}")
                else:
                    self.lbl_status.config(text=f"Could not open file: {fname}")

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
                    writer.writerow(["File Name", "Line Number", "Matched Record"])
                    for fname, rnum, ltext, score in self._current_results:
                        disp_text = f"{ltext} ({score}% match)" if score < 100 else ltext
                        writer.writerow([fname, rnum, disp_text])

                filename_only = os.path.basename(file_path)
                self.lbl_status.config(text=f"Successfully saved {len(self._current_results)} results to '{filename_only}'")
                messagebox.showinfo("Save Complete", f"Successfully saved {len(self._current_results)} search results to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save results:\n{e}")

        def _on_escape_pressed(self, event=None):
            # Pressing ESC clears search input & results (does not exit application)
            self._clear_search()


# ================= CLI Mode (Interactive Terminal Curses / Line Prompt) =================

def run_interactive_cli(stdscr):
    """Interactive Curses TUI search interface."""
    curses.curs_set(1)
    stdscr.nodelay(True)
    stdscr.timeout(100)

    engine = SearchEngine()
    indexer = BackgroundIndexer(engine)
    indexer.start()

    query = ""
    selected_idx = 0
    results = []
    elapsed_ms = 0.0
    match_type = "exact"
    status_msg = "Ready | Type to search..."

    while True:
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        # Header
        header = " QSearch (Interactive CLI Mode) "
        stdscr.addstr(0, 0, header.center(max_x), curses.A_REVERSE | curses.A_BOLD)

        # Search Bar Input
        prompt = "🔍 Search > "
        stdscr.addstr(2, 2, prompt, curses.A_BOLD)
        stdscr.addstr(2, 2 + len(prompt), query)

        # Results Info
        fc, rc = engine.get_stats()
        if indexer.is_indexing and indexer.files_left > 0:
            idx_str = f"Indexing: {indexer.percent}% ({indexer.files_left} left)"
        else:
            idx_str = f"Index: {fc} files ({rc:,} rows)"

        if results and 0 <= selected_idx < len(results):
            sel_score = results[selected_idx][3]
            type_str = f" [Fuzzy: {sel_score}% Match]" if sel_score < 100 else ""
        else:
            type_str = " (Fuzzy)" if match_type == "fuzzy" else ""

        info_str = f" Matches: {len(results)}{type_str} | Time: {elapsed_ms:.1f}ms | {idx_str} "
        stdscr.addstr(3, 2, info_str[:max_x - 4], getattr(curses, 'A_DIM', curses.A_NORMAL))

        # Separator Line
        stdscr.addstr(4, 0, "─" * max_x)

        # Results Table Area
        start_row = 5
        max_results_rows = max_y - start_row - 2

        if results and max_results_rows > 0:
            visible_results = results[:max_results_rows]
            selected_idx = min(selected_idx, len(visible_results) - 1)
            selected_idx = max(0, selected_idx)

            for idx, (fname, rnum, ltext, score) in enumerate(visible_results):
                row_y = start_row + idx
                disp_text = f"{ltext} ({score}% match)" if score < 100 else ltext
                line_disp = f"[{fname}:L{rnum}] {disp_text}"
                line_disp = line_disp[:max_x - 4]

                if idx == selected_idx:
                    stdscr.addstr(row_y, 2, line_disp, curses.A_STANDOUT)
                else:
                    stdscr.addstr(row_y, 2, line_disp)

        # Footer Status
        footer = " [Esc: Clear Search | Enter: Open File | c: Copy | s: Save CSV | Up/Down: Select] "
        try:
            stdscr.addstr(max_y - 1, 0, footer.center(max_x), curses.A_REVERSE)
        except curses.error:
            pass

        stdscr.move(2, 2 + len(prompt) + len(query))
        stdscr.refresh()

        # Key Input Handling
        try:
            ch = stdscr.getch()
        except Exception:
            ch = -1

        if ch == -1:
            time.sleep(0.03)
            continue

        if ch == 3: # Ctrl+C -> Exit
            break
        elif ch == 27: # ESC key: clears search query & results
            query = ""
            results = []
            selected_idx = 0
            elapsed_ms = 0.0
            match_type = "exact"
        elif ch in (10, 13, getattr(curses, "KEY_ENTER", 10)): # Enter key opens file
            if results and 0 <= selected_idx < len(results):
                fname = results[selected_idx][0]
                open_file_in_default_app(fname)
        elif ch in (ord('c'), ord('C')): # Press 'c' to copy record details to clipboard
            if results and 0 <= selected_idx < len(results):
                fname, rnum, ltext, score = results[selected_idx]
                headers = engine.get_file_headers(fname)
                col_lines = format_record_multiline(headers, ltext)
                formatted_text = f"📄 {fname} (Row #{rnum})\n" + "\n".join(col_lines)
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
        elif ch in (ord('s'), ord('S')): # Press 's' to save overall results to CSV file
            if results:
                safe_query = "".join(c for c in query if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
                filename = f"search_results_{safe_query}.csv" if safe_query else "search_results.csv"
                out_path = CONTENT_DIR / filename
                try:
                    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.writer(f)
                        writer.writerow(["File Name", "Line Number", "Matched Record"])
                        for fname, rnum, ltext, score in results:
                            disp_text = f"{ltext} ({score}% match)" if score < 100 else ltext
                            writer.writerow([fname, rnum, disp_text])
                except Exception:
                    pass
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if query:
                query = query[:-1]
                results, elapsed_ms, match_type = engine.search(query)
                selected_idx = 0
        elif ch == curses.KEY_UP:
            if selected_idx > 0:
                selected_idx -= 1
        elif ch == curses.KEY_DOWN:
            if selected_idx < len(results) - 1:
                selected_idx += 1
        elif 32 <= ch <= 126: # Printable characters
            query += chr(ch)
            results, elapsed_ms, match_type = engine.search(query)
            selected_idx = 0


def run_direct_cli_search(query):
    """Executes a single search query directly in terminal with multi-line column breakdown."""
    engine = SearchEngine()

    def on_cli_progress(file_cnt, row_cnt, total_files=0, files_left=0, percent=100, is_indexing=False):
        if is_indexing and files_left > 0:
            print(f"\r⏳ Indexing files... {percent}% complete ({files_left} file(s) left)", end="", flush=True)

    # Sync content folder once synchronously before returning result
    indexer = BackgroundIndexer(engine, status_callback=on_cli_progress)
    indexer.sync_content_directory()
    print("\r" + " " * 65 + "\r", end="", flush=True)

    results, elapsed_ms, match_type = engine.search(query, limit=100)

    tag_str = " (Fuzzy Matches)" if match_type == "fuzzy" else ""
    print(f"\n🔍 QSearch Results for '{query}' ({len(results)} matched{tag_str} in {elapsed_ms:.1f} ms):\n" + "─" * 70)
    if not results:
        print("No matches found.")
    else:
        for fname, rnum, ltext, score in results:
            headers = engine.get_file_headers(fname)
            col_lines = format_record_multiline(headers, ltext)
            score_str = f" \033[1;35m({score}% match)\033[0m" if score < 100 else ""
            print(f"📄 \033[1;34m{fname}\033[0m (Row #\033[33m{rnum}\033[0m){score_str}:")
            for cline in col_lines:
                print(f"  \033[36m{cline}\033[0m")
            print()
    print("─" * 70 + "\n")


# ================= Main Entry Point =================

if __name__ == "__main__":
    # Case 1: Direct search term passed in command line arguments
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        search_query = " ".join(sys.argv[1:])
        run_direct_cli_search(search_query)
        sys.exit(0)

    # Case 2: Interactive GUI with Fallback to CLI
    gui_launched = False

    if HAS_TKINTER:
        try:
            root = tk.Tk()
            # Verify if display environment is active
            root.withdraw()
            root.deiconify()
            app = QSearchGUIApp(root)
            gui_launched = True
            root.mainloop()
        except Exception:
            gui_launched = False

    if not gui_launched:
        # Fallback to Terminal CLI
        if HAS_CURSES and sys.stdin.isatty():
            try:
                curses.wrapper(run_interactive_cli)
            except KeyboardInterrupt:
                sys.exit(0)
        else:
            print("QSearch CLI Fallback: Interactive terminal not supported or non-TTY input.")
            print("Usage: python3 qs.py <search_term>")
