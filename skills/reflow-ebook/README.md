# Reflow Ebook Skill

This skill is designed for agentic coding environments (such as Antigravity, Claude Code, etc.) to automatically format and reflow `.txt`, `.epub`, and `.mobi` files that suffer from bad formatting (like hard line breaks within paragraphs, OCR scans conversion layout issues, or double-spacing bugs).

## File Structure

```
reflow-ebook/
├── SKILL.md           # Agentic instructions and triggers
├── README.md          # User documentation
└── scripts/
    └── reflow.py      # Executable formatting script (Python 3)
```

## Setup Requirements

- **Python 3** with `beautifulsoup4` and `lxml` (for parsing and editing XHTML/HTML files in EPUB/MOBI).
- **Calibre** (specifically the `ebook-convert` CLI) is required only if processing `.mobi` files.

## CLI Usage

To run the script directly:

```bash
python3 scripts/reflow.py input.epub -o output.epub
```

To turn off paragraph-merging (which merges adjacent `<p>` elements if the preceding one does not end in standard paragraph punctuation):

```bash
python3 scripts/reflow.py input.txt --no-merge
```
