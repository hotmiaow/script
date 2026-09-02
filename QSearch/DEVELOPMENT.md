# QSearch Development Guide & Future Improvement Roadmap

## 1. Project Overview & Architecture
**QSearch** is an instant search engine designed for CSV and plain text log files. It offers multiple interfaces (Tkinter GUI, Curses TUI, Interactive REPL CLI, and direct one-shot CLI commands) backed by an embedded SQLite FTS5 Trigram index with custom fuzzy score matching.

### Core Stack
- **Language**: Python 3.8+ (Fully compatible with Python 3.12+)
- **Runtime Dependency Philosophy**: Zero mandatory external dependencies (uses standard library `sqlite3`, `ipaddress`, `tkinter`, `curses`, `csv`, `threading`, `queue`, `re`, `difflib`).
- **Storage Engine**: SQLite with FTS5 Trigram extension (`tokenize='trigram'`) and WAL mode for concurrent indexing and searching.
- **Search Capabilities**:
  - Full & Partial MAC Address search across all 9 notation formats (`1111.1111.1111`, `11:11:11:11:11:11`, `11.11.11.11.11.11`, `11-11-11-11-11-11`, `11 11 11 11 11 11`, `111111111111`, and last 4/6/8 hex characters like `eeff` or `ee:ff`).
  - IP & CIDR Subnet range containment search (e.g. `1.0.0.0/8`, `192.168.1.0/24`, `10.0.0.0/16`) matching all host IPs and subnets contained within the network range.
  - Full Boolean `AND`, `OR`, `NOT`, `&&`, `||`, `|`, `&` support across Subnets, MAC addresses, exact phrases, keywords, inline file filters (`file:name`), regex mode, and bounded fuzzy match scoring.

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

## 4. Development Workflow & Automated Regression Testing

> [!IMPORTANT]
> **Mandatory Pre-Commit Rule**: Run the automated test suite each time `qs.py` is updated before committing or releasing any code change.

### Running the Test Suite
You can run the full automated test suite using either:
```bash
# Direct runner via QSearch flag:
python3 QSearch/qs.py --test

# Or running the standalone test suite:
python3 QSearch/test_qs.py

# Or via pytest (if installed in your environment):
pytest QSearch/test_qs.py
```

### Test Coverage Checklist
The test suite in `QSearch/test_qs.py` covers 17 critical test cases:
1. **MAC Detection**: Validates all 9 MAC formats (`1111.1111.1111`, `11:11:...`, `11-11-...`, `11.11-...`, `11 11...`, flat hex) and partial MACs (`eeff`, `ee:ff`, `2233.4455`).
2. **False Positive Guard**: Verifies that IP addresses (like `10.1.1.1`) and IP fragments (like `192.147.55`) are strictly excluded from MAC detection and never hijacked.
3. **IPv4 & IPv6 Extraction**: Tests IPv4, CIDR ranges, full IPv6, and compressed IPv6 (`2001:db8::1`, `::1`).
4. **Boolean & Multi-Subnet Searches**:
   - `1.0.0.0/8 OR 10.0.0.0/8`: Verifies no OR branch is dropped even across large datasets.
   - `10.0.0.0/8 AND sw`: Verifies exact constraint satisfaction (no false positive rows).
   - `192.168.1.0/24 NOT 192.168.1.50`: Verifies exclusion logic.
5. **Cross-Format Matching in MAC Mode**: Ensures searching `11:22:33:44:55:66` finds `1122.3344.5566` in the database.
6. **Cross-Directory Persistence**: Guarantees that indexing a folder does not purge files from previously indexed external folders.
7. **File Filters & Deduplication**: Tests `file_type="csv"`, `file_type="text"`, and `unique_files=True`.

---

## 5. Additional Tools & Build Commands

```bash
# Type checking
mypy QSearch/qs.py

# Linting
ruff check QSearch/

# Interactive REPL
python3 QSearch/qs.py --repl

# Packaging Standalone Executables
pyinstaller --onefile --windowed --name qsearch QSearch/qs.py
```
