---
name: reflow-ebook
description: >
  Reflows text layouts, merges broken paragraphs, removes unnecessary hard line breaks, and tidies formatting for plain text (.txt), EPUB (.epub), and MOBI (.mobi) books, outputting the result in the same format.
  Use when user wants to clean up, formatting-fix, or reflow a text or ebook file, or when they mention bad line breaks, OCR errors, or epub/mobi paragraph issues. Triggers: reflow, tidy format, remove line breaks, merge newlines, epub reflow, mobi format, format txt.
---

# Reflow Ebook

A utility to clean up hard newlines and tidy formatting in ebooks and text files without losing the original file format.

## Quick start

Reflow a text file:
```bash
/home/keith/.gemini/skills/reflow-ebook/scripts/reflow.py input.txt
```

Reflow an EPUB file:
```bash
/home/keith/.gemini/skills/reflow-ebook/scripts/reflow.py input.epub -o output.epub
```

Reflow a MOBI file (requires `ebook-convert` from Calibre):
```bash
/home/keith/.gemini/skills/reflow-ebook/scripts/reflow.py input.mobi -o output.mobi
```

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `input_file` | (Required) | Path to the `.txt`, `.epub`, or `.mobi` file |
| `-o`, `--output` | `[basename]_reflowed.[ext]` | Destination path for the reflowed file |
| `--no-merge` | `False` | Disable automatic paragraph-merging (keeps consecutive `<p>` blocks separate) |

## Workflows

### Step 1: Detect File Format and System Tools
Check if the file is `.txt`, `.epub`, or `.mobi`. If it is `.mobi`, ensure `ebook-convert` is available:
```bash
which ebook-convert
```
If not installed, warn the user that Calibre (specifically the `ebook-convert` CLI) is required to parse MOBI files.

### Step 2: Run the Reflow Tool
Run the reflow script on the file:
```bash
/home/keith/.gemini/skills/reflow-ebook/scripts/reflow.py <input_file> [-o <output_file>] [--no-merge]
```

### Step 3: Present Results
Report the path of the successfully reflowed file and print a small snippet of the cleaned text to confirm formatting quality.
