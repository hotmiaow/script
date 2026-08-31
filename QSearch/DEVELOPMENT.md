# QSearch Development Guide & Future Improvement Roadmap

## 1. Project Overview & Architecture
**QSearch** is an instant search engine designed for CSV and plain text log files. It offers multiple interfaces (Tkinter GUI, Curses TUI, Interactive REPL CLI, and direct one-shot CLI commands) backed by an embedded SQLite FTS5 Trigram index with custom fuzzy score matching.

### Core Stack
- **Language**: Python 3.8+ (Fully compatible with Python 3.12+)
- **Runtime Dependency Philosophy**: Zero mandatory external dependencies (uses standard library `sqlite3`, `tkinter`, `curses`, `csv`, `threading`, `queue`, `re`, `difflib`).
- **Storage Engine**: SQLite with FTS5 Trigram extension (`tokenize='trigram'`) and WAL mode for concurrent indexing and searching.

---

## 2. Requirements Specification

### Runtime Requirements (`requirements.txt`)
- Standard Python 3.8+ environment with `sqlite3` built with FTS5 support.
- `tkinter` (bundled by standard CPython installers on macOS/Windows; `python3-tk` on Linux distributions).
- `windows-curses>=2.3.0` *(optional, for running Curses TUI mode on Windows)*.

### Development & Improvement Requirements (`requirements-dev.txt`)
```text
mypy>=1.10.0          # Static type analysis
ruff>=0.4.0           # Linting and auto-formatting
pytest>=8.0.0         # Unit & functional test runner
pyinstaller>=6.5.0    # Standalone binary compiler
rapidfuzz>=3.8.0      # High-performance fuzzy matching accelerator (optional)
watchdog>=4.0.0       # OS-level native filesystem change events (optional)
openpyxl>=3.1.2       # Excel (.xlsx) format parsing (optional)
```

---

## 3. Future Improvements & Development Roadmap

### A. Performance & Indexing Optimizations
1. **Accelerated Fuzzy Matching**:
   - Integrate `rapidfuzz` with fallback to standard library `difflib` to boost fuzzy scoring speed on large result sets.
2. **Native Filesystem Event Watching**:
   - Optional `watchdog` integration for real-time filesystem events (`FSEvents` on macOS, `ReadDirectoryChangesW` on Windows, `inotify` on Linux) to replace polling intervals.
3. **Chunked Memory-Mapped Reading**:
   - Use `mmap` or buffered binary scanning for gigabyte-scale log files.

### B. Extended File Format Support
1. **Excel Spreadsheets (`.xlsx`, `.xls`)**:
   - Extract sheets and table rows into indexed records with column metadata.
2. **Tabular JSON / JSONL & Parquet**:
   - Parse newline-delimited JSON log streams and Parquet datasets.
3. **Compressed Archive Searching**:
   - Transparently index `.csv.gz` and `.log.gz` archives without full manual decompression.

### C. Search & Query Capabilities
1. **Column-Specific Targeting**:
   - Enhanced query parsing for header targeting (e.g. `ip:192.168.1.1 AND status:error`).
2. **Numeric & Date Range Filtering**:
   - Filter rows by numerical thresholds (e.g. `latency > 500ms`) or timestamps.
3. **FTS Rank Weighting & Relevance Tuning**:
   - Tunable trigram BM25 weights combined with exact prefix boosts.

### D. User Interface Enhancements
1. **Tkinter GUI Modernization**:
   - Dark mode toggle with custom Tkinter styling.
   - Column sorting and drag-and-drop file/directory support.
   - Export filtered subsets directly into Excel or formatted Markdown tables.
2. **Modern TUI Interface**:
   - Optional `rich` / `textual` terminal dashboard for rich mouse support and themes in CLI environments.

---

## 4. Development Workflow

### Running Tests & Type Checks
```bash
# Type checking
mypy QSearch/qs.py

# Linting
ruff check QSearch/

# Running QSearch CLI
python3 QSearch/qs.py --repl
```

### Packaging Standalone Executables
```bash
pyinstaller --onefile --windowed --name qsearch QSearch/qs.py
```
