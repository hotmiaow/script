#!/usr/bin/env python3
"""
EPUB Text Alignment Converter (epub_v2h)
Converts EPUB books between Vertical (縦書き / 直排) and Horizontal (横書き / 橫排) layouts.

Supports:
- Selective folder conversion:
  * Only convert Vertical to Horizontal (skipping already horizontal books).
  * Only convert Horizontal to Vertical (skipping already vertical books).
  * Auto-toggle all books (or force all to horizontal/vertical).
- Recursive subfolder scanning.
- Graphical User Interface (Tkinter) with folder & file selection, options, and progress.
- Command-line interface and interactive terminal fallback with drag-and-drop support.
- Optional CJK quotation mark translation (“ ” / ‘ ’ ⟷ 「 」 / 『 』).
- Strict EPUB container compliance (uncompressed mimetype first).
"""

import os
import sys
import re
import io
import shutil
import zipfile
import argparse
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Callable


# ----------------------------------------------------------------------
# Core Converter Engine
# ----------------------------------------------------------------------

class EpubConverter:
    """Handles EPUB inspection and conversion between vertical and horizontal layouts."""

    V_CSS_MODE = "vertical-rl"
    H_CSS_MODE = "horizontal-tb"

    # Punctuation translation tables
    PUNC_H2V = {
        '“': '「',
        '”': '」',
        '‘': '『',
        '’': '』',
    }
    PUNC_V2H = {
        '「': '“',
        '」': '”',
        '『': '‘',
        '』': '’',
    }

    def __init__(self, epub_path: str):
        self.epub_path = Path(epub_path).resolve()
        if not self.epub_path.is_file():
            raise FileNotFoundError(f"EPUB file not found: {self.epub_path}")
        if not zipfile.is_zipfile(self.epub_path):
            raise ValueError(f"File is not a valid zip/epub archive: {self.epub_path}")

        self.title = self.epub_path.stem
        self.author = ""
        self.opf_path = ""
        self.current_layout = "unknown"
        self._inspect()

    def _inspect(self):
        """Reads OPF path, metadata, and determines current layout."""
        with zipfile.ZipFile(self.epub_path, 'r') as zf:
            self.opf_path = self._find_opf_path(zf)
            if self.opf_path and self.opf_path in zf.namelist():
                opf_data = zf.read(self.opf_path).decode('utf-8', errors='ignore')
                # Title
                m_title = re.search(r'<dc:title[^>]*>(.*?)</dc:title>', opf_data, re.IGNORECASE | re.DOTALL)
                if m_title:
                    clean_title = re.sub(r'<[^>]+>', '', m_title.group(1)).strip()
                    if clean_title:
                        self.title = clean_title
                # Author
                m_auth = re.search(r'<dc:creator[^>]*>(.*?)</dc:creator>', opf_data, re.IGNORECASE | re.DOTALL)
                if m_auth:
                    clean_auth = re.sub(r'<[^>]+>', '', m_auth.group(1)).strip()
                    if clean_auth:
                        self.author = clean_auth

            self.current_layout = self._detect_layout(zf)

    def _find_opf_path(self, zf: zipfile.ZipFile) -> str:
        try:
            container_xml = zf.read('META-INF/container.xml').decode('utf-8', errors='ignore')
            m = re.search(r'<rootfile\s+[^>]*full-path\s*=\s*["\']([^"\']+)["\']', container_xml, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        except Exception:
            pass

        for name in zf.namelist():
            if name.lower().endswith('.opf'):
                return name
        return 'OEBPS/content.opf'

    def _detect_layout(self, zf: zipfile.ZipFile) -> str:
        score_v = 0
        score_h = 0

        # Check spine progression
        if self.opf_path and self.opf_path in zf.namelist():
            try:
                opf_data = zf.read(self.opf_path).decode('utf-8', errors='ignore')
                m = re.search(r'<spine\b[^>]*page-progression-direction\s*=\s*["\'](rtl|ltr)["\']', opf_data, re.IGNORECASE)
                if m:
                    direction = m.group(1).lower()
                    if direction == 'rtl':
                        score_v += 4
                    elif direction == 'ltr':
                        score_h += 4
            except Exception:
                pass

        # Check CSS and XHTML indicators
        v_patterns = [
            re.compile(r'-webkit-writing-mode\s*:\s*vertical-(?:rl|lr)', re.I),
            re.compile(r'-epub-writing-mode\s*:\s*vertical-(?:rl|lr)', re.I),
            re.compile(r'(?<![-a-zA-Z0-9])writing-mode\s*:\s*vertical-(?:rl|lr)', re.I),
            re.compile(r'writing-mode\s*:\s*tb-rl', re.I),
        ]
        h_patterns = [
            re.compile(r'-webkit-writing-mode\s*:\s*horizontal-tb', re.I),
            re.compile(r'-epub-writing-mode\s*:\s*horizontal-tb', re.I),
            re.compile(r'(?<![-a-zA-Z0-9])writing-mode\s*:\s*horizontal-tb', re.I),
            re.compile(r'writing-mode\s*:\s*lr-tb', re.I),
        ]

        for fname in zf.namelist():
            ext = fname.lower()
            if ext.endswith(('.css', '.xhtml', '.html', '.htm')):
                try:
                    content = zf.read(fname).decode('utf-8', errors='ignore')
                    for p in v_patterns:
                        if p.search(content):
                            score_v += 2
                    for p in h_patterns:
                        if p.search(content):
                            score_h += 2
                except Exception:
                    continue

        return 'vertical' if score_v > score_h else 'horizontal'

    def get_opposite_layout(self) -> str:
        return 'horizontal' if self.current_layout == 'vertical' else 'vertical'

    def convert(self, target_layout: str, output_path: Optional[str] = None, convert_punctuation: bool = False, progress_callback = None) -> str:
        """
        Converts the EPUB to target_layout ('horizontal' or 'vertical').
        Returns the output file path.
        """
        target_layout = target_layout.lower().strip()
        if target_layout not in ('horizontal', 'vertical'):
            raise ValueError(f"Invalid target layout: {target_layout}. Must be 'horizontal' or 'vertical'.")

        if output_path is None:
            suffix = f"_{target_layout}"
            output_path = self.epub_path.with_name(f"{self.epub_path.stem}{suffix}{self.epub_path.suffix}")
        else:
            output_path = Path(output_path).resolve()

        output_path.parent.mkdir(parents=True, exist_ok=True)

        modified_files: Dict[str, bytes] = {}

        with zipfile.ZipFile(self.epub_path, 'r') as in_zf:
            all_names = in_zf.namelist()
            total_files = len(all_names)
            css_files_found = False

            # Check if any CSS files exist
            for name in all_names:
                if name.lower().endswith('.css'):
                    css_files_found = True
                    break

            for idx, name in enumerate(all_names):
                if progress_callback:
                    progress_callback(idx + 1, total_files, name)

                lower_name = name.lower()

                # Process OPF
                if name == self.opf_path or lower_name.endswith('.opf'):
                    content = in_zf.read(name).decode('utf-8', errors='ignore')
                    content = self._modify_opf(content, target_layout)
                    modified_files[name] = content.encode('utf-8')

                # Process CSS
                elif lower_name.endswith('.css'):
                    content = in_zf.read(name).decode('utf-8', errors='ignore')
                    content = self._modify_css(content, target_layout)
                    modified_files[name] = content.encode('utf-8')

                # Process XHTML / HTML
                elif lower_name.endswith(('.xhtml', '.html', '.htm')):
                    content = in_zf.read(name).decode('utf-8', errors='ignore')
                    content = self._modify_xhtml(content, target_layout, convert_punctuation, inject_css=(not css_files_found))
                    modified_files[name] = content.encode('utf-8')

            # Write out to new EPUB
            self._write_epub(in_zf, modified_files, str(output_path))

        return str(output_path)

    def _modify_opf(self, opf_content: str, target_layout: str) -> str:
        target_dir = "rtl" if target_layout == "vertical" else "ltr"

        def repl(match):
            attrs = match.group(1) or ""
            if re.search(r'page-progression-direction\s*=\s*["\'][^"\']*["\']', attrs, re.I):
                new_attrs = re.sub(
                    r'page-progression-direction\s*=\s*["\'][^"\']*["\']',
                    f'page-progression-direction="{target_dir}"',
                    attrs,
                    flags=re.I
                )
            else:
                new_attrs = f' page-progression-direction="{target_dir}"' + attrs
            return f'<spine{new_attrs}>'

        return re.sub(r'<spine(\s+[^>]*)?>', repl, opf_content, count=1, flags=re.I)

    def _modify_css(self, css_content: str, target_layout: str) -> str:
        if target_layout == 'horizontal':
            # Replace vertical writing-modes (both vendor-prefixed and standard)
            css = re.sub(r'-webkit-writing-mode\s*:\s*(?:vertical-rl|vertical-lr|tb-rl)[^;]*;?', '-webkit-writing-mode: horizontal-tb;', css_content, flags=re.I)
            css = re.sub(r'-epub-writing-mode\s*:\s*(?:vertical-rl|vertical-lr|tb-rl)[^;]*;?', '-epub-writing-mode: horizontal-tb;', css, flags=re.I)
            css = re.sub(r'(?<![-a-zA-Z0-9])writing-mode\s*:\s*(?:vertical-rl|vertical-lr|tb-rl)[^;]*;?', 'writing-mode: horizontal-tb;', css, flags=re.I)

            # Neutralize text-orientation: upright/sideways
            css = re.sub(r'text-orientation\s*:\s*(?:upright|sideways)[^;]*;?', 'text-orientation: mixed;', css, flags=re.I)
            # Neutralize text-combine-upright: all
            css = re.sub(r'(?:-webkit-|-epub-)?text-combine(?:-upright)?\s*:\s*all[^;]*;?', 'text-combine-upright: none;', css, flags=re.I)

            # Append override
            css += (
                "\n\n/* epub_v2h: horizontal layout override */\n"
                "html, body {\n"
                "  writing-mode: horizontal-tb !important;\n"
                "  -webkit-writing-mode: horizontal-tb !important;\n"
                "  -epub-writing-mode: horizontal-tb !important;\n"
                "}\n"
            )
            return css
        else:
            # Replace horizontal writing-modes
            css = re.sub(r'-webkit-writing-mode\s*:\s*(?:horizontal-tb|lr-tb)[^;]*;?', '-webkit-writing-mode: vertical-rl;', css_content, flags=re.I)
            css = re.sub(r'-epub-writing-mode\s*:\s*(?:horizontal-tb|lr-tb)[^;]*;?', '-epub-writing-mode: vertical-rl;', css, flags=re.I)
            css = re.sub(r'(?<![-a-zA-Z0-9])writing-mode\s*:\s*(?:horizontal-tb|lr-tb)[^;]*;?', 'writing-mode: vertical-rl;', css, flags=re.I)

            # Append override
            css += (
                "\n\n/* epub_v2h: vertical layout override */\n"
                "html, body {\n"
                "  writing-mode: vertical-rl !important;\n"
                "  -webkit-writing-mode: vertical-rl !important;\n"
                "  -epub-writing-mode: vertical-rl !important;\n"
                "}\n"
            )
            return css

    def _modify_xhtml(self, xhtml_content: str, target_layout: str, convert_punc: bool, inject_css: bool) -> str:
        content = xhtml_content

        if target_layout == 'horizontal':
            # If dir="rtl" is placed on <html> or <body>, change to dir="ltr"
            content = re.sub(r'(<(?:html|body)\b[^>]*)\bdir\s*=\s*["\']rtl["\']', r'\1dir="ltr"', content, flags=re.I)

            # Modify inline style="..." attributes
            def repl_style_h(m):
                style_val = m.group(2)
                style_val = re.sub(r'-webkit-writing-mode\s*:\s*(?:vertical-rl|vertical-lr|tb-rl)[^;]*;?', '-webkit-writing-mode: horizontal-tb;', style_val, flags=re.I)
                style_val = re.sub(r'-epub-writing-mode\s*:\s*(?:vertical-rl|vertical-lr|tb-rl)[^;]*;?', '-epub-writing-mode: horizontal-tb;', style_val, flags=re.I)
                style_val = re.sub(r'(?<![-a-zA-Z0-9])writing-mode\s*:\s*(?:vertical-rl|vertical-lr|tb-rl)[^;]*;?', 'writing-mode: horizontal-tb;', style_val, flags=re.I)
                return f'{m.group(1)}{style_val}{m.group(3)}'
            content = re.sub(r'(style\s*=\s*["\'])([^"\']*)(["\'])', repl_style_h, content, flags=re.I)

            # Modify <style>...</style> blocks
            def repl_style_block_h(m):
                return f"{m.group(1)}{self._modify_css(m.group(2), 'horizontal')}{m.group(3)}"
            content = re.sub(r'(<style\b[^>]*>)(.*?)(</style>)', repl_style_block_h, content, flags=re.I | re.DOTALL)

        else:
            # Vertical layout
            def repl_style_v(m):
                style_val = m.group(2)
                style_val = re.sub(r'-webkit-writing-mode\s*:\s*(?:horizontal-tb|lr-tb)[^;]*;?', '-webkit-writing-mode: vertical-rl;', style_val, flags=re.I)
                style_val = re.sub(r'-epub-writing-mode\s*:\s*(?:horizontal-tb|lr-tb)[^;]*;?', '-epub-writing-mode: vertical-rl;', style_val, flags=re.I)
                style_val = re.sub(r'(?<![-a-zA-Z0-9])writing-mode\s*:\s*(?:horizontal-tb|lr-tb)[^;]*;?', 'writing-mode: vertical-rl;', style_val, flags=re.I)
                return f'{m.group(1)}{style_val}{m.group(3)}'
            content = re.sub(r'(style\s*=\s*["\'])([^"\']*)(["\'])', repl_style_v, content, flags=re.I)

            def repl_style_block_v(m):
                return f"{m.group(1)}{self._modify_css(m.group(2), 'vertical')}{m.group(3)}"
            content = re.sub(r'(<style\b[^>]*>)(.*?)(</style>)', repl_style_block_v, content, flags=re.I | re.DOTALL)

        # Inject stylesheet rule if EPUB has no .css files
        if inject_css:
            wm = "horizontal-tb" if target_layout == "horizontal" else "vertical-rl"
            override_style = (
                f'\n<style type="text/css">\n'
                f'/* epub_v2h injected override */\n'
                f'html, body {{\n'
                f'  writing-mode: {wm} !important;\n'
                f'  -webkit-writing-mode: {wm} !important;\n'
                f'  -epub-writing-mode: {wm} !important;\n'
                f'}}\n'
                f'</style>\n'
            )
            if re.search(r'</head>', content, re.I):
                content = re.sub(r'</head>', f'{override_style}</head>', content, count=1, flags=re.I)
            elif re.search(r'<body\b[^>]*>', content, re.I):
                content = re.sub(r'(<body\b[^>]*>)', rf'\1{override_style}', content, count=1, flags=re.I)

        # Punctuation replacement if requested
        if convert_punc:
            mapping = self.PUNC_V2H if target_layout == 'horizontal' else self.PUNC_H2V
            content = self._replace_text_nodes_punc(content, mapping)

        return content

    def _replace_text_nodes_punc(self, xhtml_content: str, mapping: Dict[str, str]) -> str:
        """Transforms punctuation strictly inside text nodes without affecting HTML tags or code."""
        tag_regex = re.compile(
            r'(<!--.*?-->|<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>|<[^>]+>)',
            re.DOTALL | re.IGNORECASE
        )
        parts = tag_regex.split(xhtml_content)
        for i in range(0, len(parts), 2):
            if parts[i]:
                text = parts[i]
                for src_char, tgt_char in mapping.items():
                    text = text.replace(src_char, tgt_char)
                parts[i] = text
        return ''.join(parts)

    def _write_epub(self, in_zf: zipfile.ZipFile, modified_files: Dict[str, bytes], output_path: str):
        with zipfile.ZipFile(output_path, 'w') as out_zf:
            # 1. mimetype MUST be uncompressed and the first entry
            if 'mimetype' in modified_files:
                mime_bytes = modified_files['mimetype']
            elif 'mimetype' in in_zf.namelist():
                mime_bytes = in_zf.read('mimetype')
            else:
                mime_bytes = b'application/epub+zip'

            out_zf.writestr('mimetype', mime_bytes, compress_type=zipfile.ZIP_STORED)

            # 2. Write all remaining files
            all_names = set(in_zf.namelist()) | set(modified_files.keys())
            for name in all_names:
                if name == 'mimetype':
                    continue
                data = modified_files[name] if name in modified_files else in_zf.read(name)
                out_zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)


# ----------------------------------------------------------------------
# File and Batch Processing Helpers
# ----------------------------------------------------------------------

def find_epub_files(path: Path, recursive: bool = False) -> List[Path]:
    """Finds all EPUB files in a file or directory path."""
    resolved = path.resolve()
    if resolved.is_file():
        if resolved.suffix.lower() == '.epub' or zipfile.is_zipfile(resolved):
            return [resolved]
        return []
    elif resolved.is_dir():
        pattern = '**/*.epub' if recursive else '*.epub'
        files = [p.resolve() for p in resolved.glob(pattern) if p.is_file()]
        return sorted(files)
    return []


def determine_conversion_action(current_layout: str, mode: str) -> Tuple[bool, str, str]:
    """
    Decides whether an EPUB should be converted based on layout and selected mode.
    Modes:
      - 'only_v2h' / 'v2h': Convert only vertical to horizontal (skip horizontal).
      - 'only_h2v' / 'h2v': Convert only horizontal to vertical (skip vertical).
      - 'auto': Toggle to opposite orientation.
      - 'horizontal': Convert to horizontal (force).
      - 'vertical': Convert to vertical (force).

    Returns: (should_convert: bool, target_layout: str, status_description: str)
    """
    mode = mode.lower().strip()
    if mode in ('only_v2h', 'v2h'):
        if current_layout == 'vertical':
            return True, 'horizontal', 'Vertical ➔ Horizontal'
        else:
            return False, '', 'Skipped (already Horizontal)'

    elif mode in ('only_h2v', 'h2v'):
        if current_layout == 'horizontal':
            return True, 'vertical', 'Horizontal ➔ Vertical'
        else:
            return False, '', 'Skipped (already Vertical)'

    elif mode == 'auto':
        target = 'horizontal' if current_layout == 'vertical' else 'vertical'
        return True, target, f'{current_layout.capitalize()} ➔ {target.capitalize()}'

    elif mode == 'horizontal':
        return True, 'horizontal', 'Force Horizontal'

    elif mode == 'vertical':
        return True, 'vertical', 'Force Vertical'

    # Fallback
    target = 'horizontal' if current_layout == 'vertical' else 'vertical'
    return True, target, f'{current_layout.capitalize()} ➔ {target.capitalize()}'


def process_batch(
    files: List[Path],
    mode: str,
    output_dir: Optional[Path] = None,
    base_folder: Optional[Path] = None,
    convert_punctuation: bool = False,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None
) -> Tuple[int, int, int]:
    """
    Batch processes a list of EPUB files.
    Returns: (converted_count, skipped_count, failed_count)
    """
    def log(msg: str):
        if log_cb:
            log_cb(msg)
        else:
            print(msg)

    converted_count = 0
    skipped_count = 0
    failed_count = 0
    total = len(files)

    for idx, fpath in enumerate(files):
        if progress_cb:
            progress_cb(idx + 1, total, fpath.name)

        try:
            conv = EpubConverter(str(fpath))
            should_convert, target, action_desc = determine_conversion_action(conv.current_layout, mode)

            if not should_convert:
                log(f"[{idx+1}/{total}] SKIP: {fpath.name} ({action_desc})")
                skipped_count += 1
                continue

            # Determine output destination
            if output_dir:
                if base_folder:
                    try:
                        rel = fpath.relative_to(base_folder)
                        out_file = output_dir / rel.parent / f"{fpath.stem}_{target}.epub"
                    except ValueError:
                        out_file = output_dir / f"{fpath.stem}_{target}.epub"
                else:
                    out_file = output_dir / f"{fpath.stem}_{target}.epub"
            else:
                out_file = fpath.with_name(f"{fpath.stem}_{target}.epub")

            log(f"[{idx+1}/{total}] CONVERT: {fpath.name} [{conv.current_layout} ➔ {target}]")
            out_file_str = conv.convert(
                target_layout=target,
                output_path=str(out_file),
                convert_punctuation=convert_punctuation
            )
            log(f"       Saved: {out_file_str}")
            converted_count += 1

        except Exception as e:
            log(f"[{idx+1}/{total}] ERROR: {fpath.name} - {e}")
            failed_count += 1

    return converted_count, skipped_count, failed_count


# ----------------------------------------------------------------------
# Graphical User Interface (Tkinter)
# ----------------------------------------------------------------------

def launch_gui(initial_path: Optional[str] = None):
    """Launches the Tkinter GUI application."""
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    class EpubV2HApp:
        def __init__(self, root: tk.Tk):
            self.root = root
            self.root.title("EPUB Text Alignment Converter (Vertical ⟷ Horizontal)")
            self.root.geometry("720x620")
            self.root.minsize(620, 520)

            self.file_list: List[Path] = []
            self.selected_folder: Optional[Path] = None
            self.active_converter: Optional[EpubConverter] = None

            # Variables
            self.mode_var = tk.StringVar(value="only_v2h")
            self.recursive_var = tk.BooleanVar(value=False)
            self.convert_punc_var = tk.BooleanVar(value=False)
            self.output_dir_var = tk.StringVar(value="")

            self._build_ui()

            if initial_path:
                self._handle_input_path(Path(initial_path))

        def _build_ui(self):
            main_frame = ttk.Frame(self.root, padding="15")
            main_frame.pack(fill=tk.BOTH, expand=True)

            # Header
            header_frame = ttk.Frame(main_frame)
            header_frame.pack(fill=tk.X, pady=(0, 10))

            title_lbl = ttk.Label(header_frame, text="EPUB Text Alignment Converter", font=("Helvetica", 14, "bold"))
            title_lbl.pack(anchor=tk.W)
            desc_lbl = ttk.Label(
                header_frame,
                text="Convert EPUB files between Vertical (直排 / 縦書き) and Horizontal (橫排 / 横書き) layouts.",
                foreground="#555555"
            )
            desc_lbl.pack(anchor=tk.W, pady=(2, 0))

            # Selection Frame
            sel_frame = ttk.LabelFrame(main_frame, text=" EPUB Selection ", padding="10")
            sel_frame.pack(fill=tk.X, pady=(0, 10))

            btn_box = ttk.Frame(sel_frame)
            btn_box.pack(fill=tk.X)

            ttk.Button(btn_box, text="Choose File(s)...", command=self._on_choose_files).pack(side=tk.LEFT, padx=(0, 6))
            ttk.Button(btn_box, text="Choose Folder...", command=self._on_choose_folder).pack(side=tk.LEFT, padx=(0, 10))

            self.cb_recursive = ttk.Checkbutton(
                btn_box,
                text="Include subfolders (Recursive)",
                variable=self.recursive_var,
                command=self._on_toggle_recursive
            )
            self.cb_recursive.pack(side=tk.LEFT)

            # Selection status label
            self.file_info_lbl = ttk.Label(sel_frame, text="No files or folder selected", font=("Helvetica", 9, "italic"), foreground="#666666")
            self.file_info_lbl.pack(anchor=tk.W, pady=(8, 0))

            self.book_details_lbl = ttk.Label(sel_frame, text="", foreground="#1a5fb4")
            self.book_details_lbl.pack(anchor=tk.W, pady=(2, 0))

            # Conversion Mode / Filter Frame
            filter_frame = ttk.LabelFrame(main_frame, text=" Conversion Filter & Direction ", padding="10")
            filter_frame.pack(fill=tk.X, pady=(0, 10))

            ttk.Radiobutton(
                filter_frame,
                text="Only convert Vertical ➔ Horizontal  (Skip books already horizontal)",
                variable=self.mode_var,
                value="only_v2h"
            ).pack(anchor=tk.W, pady=2)

            ttk.Radiobutton(
                filter_frame,
                text="Only convert Horizontal ➔ Vertical  (Skip books already vertical)",
                variable=self.mode_var,
                value="only_h2v"
            ).pack(anchor=tk.W, pady=2)

            ttk.Radiobutton(
                filter_frame,
                text="Auto-Toggle All  (Convert each book to its opposite orientation)",
                variable=self.mode_var,
                value="auto"
            ).pack(anchor=tk.W, pady=2)

            ttk.Radiobutton(
                filter_frame,
                text="Force All to Horizontal  (Re-process or force horizontal)",
                variable=self.mode_var,
                value="horizontal"
            ).pack(anchor=tk.W, pady=2)

            ttk.Radiobutton(
                filter_frame,
                text="Force All to Vertical  (Re-process or force vertical)",
                variable=self.mode_var,
                value="vertical"
            ).pack(anchor=tk.W, pady=2)

            # Options Frame
            opts_frame = ttk.LabelFrame(main_frame, text=" Options & Output ", padding="10")
            opts_frame.pack(fill=tk.X, pady=(0, 10))

            ttk.Checkbutton(
                opts_frame,
                text="Convert quotation marks (“ ” / ‘ ’  ⟷  「 」 / 『 』)",
                variable=self.convert_punc_var
            ).pack(anchor=tk.W)
            ttk.Label(
                opts_frame,
                text="  (Converts text nodes only; recommended for Chinese; leave unchecked for Japanese)",
                font=("Helvetica", 8),
                foreground="#666666"
            ).pack(anchor=tk.W, pady=(0, 6))

            out_box = ttk.Frame(opts_frame)
            out_box.pack(fill=tk.X, pady=(4, 0))
            ttk.Label(out_box, text="Output Folder:").pack(side=tk.LEFT, padx=(0, 5))
            self.out_entry = ttk.Entry(out_box, textvariable=self.output_dir_var)
            self.out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
            ttk.Button(out_box, text="Browse...", command=self._on_choose_out_dir).pack(side=tk.LEFT)

            # Action Frame
            action_frame = ttk.Frame(main_frame)
            action_frame.pack(fill=tk.X, pady=(5, 5))

            self.convert_btn = ttk.Button(action_frame, text="Start Conversion", command=self._on_convert)
            self.convert_btn.pack(side=tk.RIGHT)

            self.open_dir_btn = ttk.Button(action_frame, text="Open Output Folder", command=self._on_open_folder, state=tk.DISABLED)
            self.open_dir_btn.pack(side=tk.RIGHT, padx=(0, 8))

            self.progress_bar = ttk.Progressbar(action_frame, mode='determinate')
            self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

            # Log Area
            log_frame = ttk.LabelFrame(main_frame, text=" Activity Log ", padding="5")
            log_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

            self.log_text = tk.Text(log_frame, wrap=tk.WORD, height=8, font=("Monospace", 9))
            self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.log_text.config(yscrollcommand=scrollbar.set)

            self._log("Ready. Select EPUB file(s) or a folder to convert.")

        def _log(self, msg: str):
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.root.update_idletasks()

        def _on_choose_files(self):
            files = filedialog.askopenfilenames(
                title="Select EPUB File(s)",
                filetypes=[("EPUB Files", "*.epub"), ("All Files", "*.*")]
            )
            if files:
                self.selected_folder = None
                self._load_file_list([Path(f) for f in files])

        def _on_choose_folder(self):
            folder = filedialog.askdirectory(title="Select Folder Containing EPUBs")
            if folder:
                folder_path = Path(folder)
                self.selected_folder = folder_path
                self._rescan_folder()

        def _on_toggle_recursive(self):
            if self.selected_folder:
                self._rescan_folder()

        def _rescan_folder(self):
            if not self.selected_folder:
                return
            epubs = find_epub_files(self.selected_folder, recursive=self.recursive_var.get())
            self._load_file_list(epubs, from_folder=self.selected_folder)

        def _handle_input_path(self, p: Path):
            if p.is_dir():
                self.selected_folder = p
                self._rescan_folder()
            else:
                self.selected_folder = None
                self._load_file_list([p])

        def _load_file_list(self, files: List[Path], from_folder: Optional[Path] = None):
            self.file_list = [f for f in files if f.suffix.lower() == '.epub' or zipfile.is_zipfile(f)]
            if not self.file_list:
                self.file_info_lbl.config(text="No EPUB files found.", foreground="red")
                self.book_details_lbl.config(text="")
                return

            if from_folder:
                sub_txt = " (including subfolders)" if self.recursive_var.get() else ""
                self.file_info_lbl.config(
                    text=f"Folder: {from_folder.name}{sub_txt} — Found {len(self.file_list)} EPUB file(s)",
                    foreground="#000000"
                )
                self.book_details_lbl.config(text=str(from_folder))
                self._log(f"Scanned folder '{from_folder}': found {len(self.file_list)} EPUB file(s).")
            elif len(self.file_list) == 1:
                single = self.file_list[0]
                self.file_info_lbl.config(text=f"File: {single.name}", foreground="#000000")
                try:
                    conv = EpubConverter(str(single))
                    layout_display = "VERTICAL (直排 / 縦書き)" if conv.current_layout == "vertical" else "HORIZONTAL (橫排 / 横書き)"
                    self.book_details_lbl.config(
                        text=f"Title: {conv.title} | Current Layout: {layout_display}"
                    )
                    # Automatically select matching filter
                    if conv.current_layout == "vertical":
                        self.mode_var.set("only_v2h")
                    else:
                        self.mode_var.set("only_h2v")
                    self._log(f"Loaded '{single.name}': Detected {conv.current_layout.upper()}")
                except Exception as e:
                    self.book_details_lbl.config(text=f"Error inspecting file: {e}", foreground="red")
            else:
                self.file_info_lbl.config(text=f"{len(self.file_list)} EPUB files selected", foreground="#000000")
                self.book_details_lbl.config(text="Batch mode: Multiple files selected.")
                self._log(f"Loaded {len(self.file_list)} EPUB files for batch processing.")

            # Default output directory
            if not self.output_dir_var.get():
                if from_folder:
                    self.output_dir_var.set(str(from_folder / "converted"))
                elif self.file_list:
                    self.output_dir_var.set(str(self.file_list[0].parent))

        def _on_choose_out_dir(self):
            folder = filedialog.askdirectory(title="Select Output Folder")
            if folder:
                self.output_dir_var.set(folder)

        def _on_convert(self):
            if not self.file_list:
                messagebox.showwarning("Notice", "Please select EPUB file(s) or a folder first.")
                return

            self.convert_btn.config(state=tk.DISABLED)
            self.open_dir_btn.config(state=tk.DISABLED)
            self.progress_bar['value'] = 0

            mode = self.mode_var.get()
            convert_punc = self.convert_punc_var.get()
            out_dir_str = self.output_dir_var.get().strip()
            out_dir = Path(out_dir_str) if out_dir_str else None

            self._log(f"\n=== Starting Batch Conversion (Filter Mode: {mode.upper()}) ===")

            def progress_update(curr, tot, name):
                pct = int((curr / tot) * 100)
                self.progress_bar['value'] = pct
                self.root.update_idletasks()

            conv_count, skip_count, fail_count = process_batch(
                files=self.file_list,
                mode=mode,
                output_dir=out_dir,
                base_folder=self.selected_folder,
                convert_punctuation=convert_punc,
                progress_cb=progress_update,
                log_cb=self._log
            )

            self.progress_bar['value'] = 100
            self.convert_btn.config(state=tk.NORMAL)
            self.open_dir_btn.config(state=tk.NORMAL)

            summary_msg = f"Conversion finished!\n\nConverted: {conv_count}\nSkipped: {skip_count}\nFailed: {fail_count}"
            self._log(f"\n=== Summary: {conv_count} converted, {skip_count} skipped, {fail_count} failed ===")
            messagebox.showinfo("Done", summary_msg)

        def _on_open_folder(self):
            folder = self.output_dir_var.get()
            if not folder or not Path(folder).exists():
                folder = str(self.selected_folder) if self.selected_folder else str(Path.home())
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", folder])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])

    root = tk.Tk()
    app = EpubV2HApp(root)
    root.mainloop()


# ----------------------------------------------------------------------
# Interactive Terminal & CLI
# ----------------------------------------------------------------------

def run_interactive_cli():
    """Interactive terminal prompt with folder and file selection support."""
    print("=" * 68)
    print("   EPUB Text Alignment Converter (Vertical ⟷ Horizontal)")
    print("=" * 68)

    while True:
        raw_input = input("\nEnter path to EPUB file or Folder (drag & drop here, 'q' to quit): ").strip()
        if not raw_input or raw_input.lower() in ('q', 'quit', 'exit'):
            print("Exiting.")
            return

        clean_path = Path(raw_input.strip("\"'").strip())
        if not clean_path.exists():
            print(f"Error: Path not found: '{clean_path}'")
            continue

        if clean_path.is_dir():
            # Directory mode
            rec_prompt = input("Include subfolders recursively? [y/N]: ").strip().lower()
            recursive = rec_prompt in ('y', 'yes')
            epubs = find_epub_files(clean_path, recursive=recursive)
            if not epubs:
                print(f"No .epub files found in '{clean_path}'.")
                continue

            print(f"\nFound {len(epubs)} EPUB file(s) in folder.")
            print("\nSelect conversion filter:")
            print("  [1] ONLY convert Vertical ➔ Horizontal (Skip books already horizontal) [Default]")
            print("  [2] ONLY convert Horizontal ➔ Vertical (Skip books already vertical)")
            print("  [3] Auto-Toggle ALL books to opposite layout")
            print("  [4] Force ALL books to Horizontal")
            print("  [5] Force ALL books to Vertical")
            choice = input("Choice [1-5] (default: 1): ").strip()

            mode_map = {
                '1': 'only_v2h',
                '2': 'only_h2v',
                '3': 'auto',
                '4': 'horizontal',
                '5': 'vertical'
            }
            mode = mode_map.get(choice, 'only_v2h')

            punc_choice = input("Convert quotation marks (“ ” ⟷ 「 」)? [y/N]: ").strip().lower()
            convert_punc = punc_choice in ('y', 'yes')

            out_prompt = input(f"Output folder (leave empty to save next to original files): ").strip().strip("\"'")
            out_dir = Path(out_prompt).resolve() if out_prompt else None

            print(f"\nProcessing {len(epubs)} file(s) in mode '{mode}'...")
            conv_cnt, skip_cnt, fail_cnt = process_batch(
                files=epubs,
                mode=mode,
                output_dir=out_dir,
                base_folder=clean_path,
                convert_punctuation=convert_punc
            )
            print(f"\nDone! Converted: {conv_cnt}, Skipped: {skip_cnt}, Failed: {fail_cnt}\n")

        else:
            # Single file mode
            try:
                conv = EpubConverter(str(clean_path))
                layout_str = "VERTICAL (直排 / 縦書き)" if conv.current_layout == "vertical" else "HORIZONTAL (橫排 / 横書き)"
                opp_layout = conv.get_opposite_layout()

                print(f"\n  Title:          {conv.title}")
                if conv.author:
                    print(f"  Author:         {conv.author}")
                print(f"  Current Layout: {layout_str}")
                print(f"  Suggested:      Convert to {opp_layout.upper()}")

                print("\nSelect target layout:")
                print(f"  [1] Convert to {opp_layout.upper()} (Recommended default)")
                print("  [2] Force HORIZONTAL")
                print("  [3] Force VERTICAL")
                choice = input("Choice [1/2/3] (default: 1): ").strip()

                target = "horizontal" if choice == "2" else ("vertical" if choice == "3" else opp_layout)

                punc_choice = input("Convert quotation marks (“ ” ⟷ 「 」)? [y/N]: ").strip().lower()
                convert_punc = punc_choice in ('y', 'yes')

                default_out = clean_path.with_name(f"{clean_path.stem}_{target}.epub")
                out_prompt = input(f"Output path (default: {default_out.name}): ").strip().strip("\"'")
                output_path = out_prompt if out_prompt else str(default_out)

                print(f"\nConverting to {target.upper()}...")
                result = conv.convert(
                    target_layout=target,
                    output_path=output_path,
                    convert_punctuation=convert_punc
                )
                print(f"Success! Saved to:\n  -> {result}\n")

            except Exception as e:
                print(f"Error processing EPUB: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert EPUB files between Vertical (直排) and Horizontal (橫排) layouts."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="One or more EPUB file paths or folder paths."
    )
    parser.add_argument(
        "-d", "--dir",
        help="Directory containing EPUB files to convert."
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recursively scan folders for EPUB files."
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["only_v2h", "only_h2v", "v2h", "h2v", "auto", "horizontal", "vertical"],
        default=None,
        help="Filter mode: 'only_v2h' (only convert vertical to horizontal, skip horizontal), "
             "'only_h2v' (only convert horizontal to vertical, skip vertical), "
             "'auto' (toggle opposite), 'horizontal', 'vertical'."
    )
    parser.add_argument(
        "--v2h", "--only-v2h",
        dest="flag_v2h",
        action="store_true",
        help="Shortcut to only convert vertical EPUBs to horizontal (skips already horizontal books)."
    )
    parser.add_argument(
        "--h2v", "--only-h2v",
        dest="flag_h2v",
        action="store_true",
        help="Shortcut to only convert horizontal EPUBs to vertical (skips already vertical books)."
    )
    parser.add_argument(
        "-t", "--to",
        choices=["horizontal", "vertical", "auto"],
        default=None,
        help="Target text layout: 'horizontal', 'vertical', or 'auto'."
    )
    parser.add_argument(
        "-p", "--punctuation",
        action="store_true",
        help="Convert quotation marks between (“ ” / ‘ ’) and (「 」 / 『 』)."
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (single file) or destination directory (batch mode)."
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Force graphical user interface (GUI) mode."
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Force command-line interface (CLI) mode."
    )

    args = parser.parse_args()

    # Determine mode priority
    mode = "auto"
    if args.flag_v2h:
        mode = "only_v2h"
    elif args.flag_h2v:
        mode = "only_h2v"
    elif args.mode:
        mode = args.mode
    elif args.to:
        mode = args.to

    # Check GUI capability
    can_gui = False
    if not args.cli:
        if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
            try:
                import tkinter as tk
                test_root = tk.Tk()
                test_root.withdraw()
                test_root.destroy()
                can_gui = True
            except Exception:
                can_gui = False

    # 1. Explicit GUI request
    if args.gui:
        if can_gui:
            init_path = args.dir if args.dir else (args.inputs[0] if args.inputs else None)
            launch_gui(initial_path=init_path)
            return
        else:
            print("Warning: Graphical display is unavailable. Falling back to CLI mode.", file=sys.stderr)

    # 2. Gather input paths
    all_targets: List[Path] = []
    if args.dir:
        all_targets.append(Path(args.dir))
    for item in args.inputs:
        all_targets.append(Path(item))

    # If input paths were given in CLI
    if all_targets:
        collected_epubs: List[Path] = []
        base_folder = None

        if len(all_targets) == 1 and all_targets[0].is_dir():
            base_folder = all_targets[0]
            collected_epubs = find_epub_files(base_folder, recursive=args.recursive)
        else:
            for target in all_targets:
                if target.is_dir():
                    collected_epubs.extend(find_epub_files(target, recursive=args.recursive))
                elif target.is_file():
                    collected_epubs.append(target.resolve())

        if not collected_epubs:
            print("No EPUB files found to process.", file=sys.stderr)
            sys.exit(1)

        out_dest = Path(args.output).resolve() if args.output else None

        print(f"Processing {len(collected_epubs)} EPUB file(s) with mode '{mode}'...")
        conv_c, skip_c, fail_c = process_batch(
            files=collected_epubs,
            mode=mode,
            output_dir=out_dest,
            base_folder=base_folder,
            convert_punctuation=args.punctuation
        )
        print(f"\nFinished: {conv_c} converted, {skip_c} skipped, {fail_c} failed.")
        return

    # 3. No inputs provided: launch GUI if available, else interactive CLI
    if can_gui:
        launch_gui()
        return

    run_interactive_cli()


if __name__ == "__main__":
    main()
