# EPUB Text Alignment Converter (epub_v2h)

A Python tool to convert EPUB eBooks between **Vertical (直排 / 縦書き)** and **Horizontal (橫排 / 横書き)** text layouts.

---

## Key Features

- **Selective Folder Conversion**:
  - **Only Vertical ➔ Horizontal (`--v2h`)**: Scans a folder and converts only vertical books; books already horizontal are safely skipped.
  - **Only Horizontal ➔ Vertical (`--h2v`)**: Scans a folder and converts only horizontal books; books already vertical are safely skipped.
  - **Auto-Toggle All (`--mode auto`)**: Converts every book to its respective opposite layout.
- **Recursive Subfolder Scanning (`-r` / `--recursive`)**: Process whole library directories with multiple subdirectories.
- **Dual Interface**:
  - **Graphical UI (Tkinter)**: Click "Choose Folder..." or "Choose File(s)...", select your filter radio button, and watch progress in the activity log.
  - **Command Line & Interactive Terminal**: Convert directly via CLI flags or interactive prompt with drag-and-drop path support.
- **Punctuation Adaptation (Optional, `-p`)**:
  - Converts CJK quotation marks between horizontal (`“ ”` / `‘ ’`) and vertical (`「 」` / `『 』`) in text nodes without touching HTML markup.
- **EPUB Standards Compliant**:
  - Keeps uncompressed `mimetype` as the first ZIP entry (`ZIP_STORED`).
  - Cleans up legacy `dir="rtl"` attributes on HTML elements.
  - Adjusts OPF spine `page-progression-direction` and CSS writing modes.

---

## Requirements

- Python 3.7+ (standard library only; no pip dependencies required).
- Tkinter (included by default with standard Python installations).

---

## Usage Guide

### 1. Graphical User Interface (GUI)

Launch the interface by running:

```bash
python epub_v2h.py
```
*(or explicitly `python epub_v2h.py --gui`)*

In the GUI window:
1. Click **"Choose Folder..."** to select a folder of EPUB books (check **"Include subfolders (Recursive)"** if desired), OR click **"Choose File(s)..."** to pick individual files.
2. Under **"Conversion Filter & Direction"**, choose:
   - **Only convert Vertical ➔ Horizontal** (skips books already horizontal)
   - **Only convert Horizontal ➔ Vertical** (skips books already vertical)
   - **Auto-Toggle All** (converts each book to its opposite layout)
3. Optionally check **"Convert quotation marks"** (recommended for Chinese novels).
4. Specify an output folder (optional; defaults to saving next to the originals or in a `converted/` subfolder).
5. Click **"Start Conversion"**.

---

### 2. Command Line Interface (CLI)

#### Folder Processing

- **Convert ONLY Vertical EPUBs to Horizontal in a folder**:
  ```bash
  python epub_v2h.py /path/to/my_books/ --v2h
  ```
  *(Any books that are already horizontal will be skipped automatically)*

- **Convert ONLY Horizontal EPUBs to Vertical in a folder**:
  ```bash
  python epub_v2h.py /path/to/my_books/ --h2v
  ```
  *(Any books that are already vertical will be skipped automatically)*

- **Include all subdirectories recursively (`-r`)**:
  ```bash
  python epub_v2h.py -d /path/to/library/ --v2h -r
  ```

- **Specify a dedicated output directory (`-o`)**:
  ```bash
  python epub_v2h.py -d /path/to/my_books/ --v2h -o /path/to/converted_books/
  ```

- **Enable quotation mark conversion (`-p`)**:
  ```bash
  python epub_v2h.py -d /path/to/my_books/ --v2h -p
  ```

#### Single File Processing

- **Auto-convert a single book to opposite layout**:
  ```bash
  python epub_v2h.py book.epub
  ```
- **Force a specific direction**:
  ```bash
  python epub_v2h.py book.epub --to horizontal
  python epub_v2h.py book.epub --to vertical
  ```

---

### 3. Interactive Terminal Mode

If run in a terminal without arguments (or with `--cli`):

```bash
python epub_v2h.py --cli
```

You can drag-and-drop any file or folder into the terminal, select your conversion filter from the interactive menu, and convert with real-time progress.

---

## Running Tests

Run the test suite to verify all features:

```bash
python -m unittest test_epub_v2h.py
```
