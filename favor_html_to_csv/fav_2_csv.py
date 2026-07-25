#!/usr/bin/env python3
"""
Chrome & Edge Bookmarks (Favorites) HTML to CSV Converter
Converts exported Netscape bookmark HTML files from Chrome, Edge, Firefox, or Safari to CSV.
Produces 3 columns: Folder, Title, URL.
"""

import sys
import os
import csv
from html.parser import HTMLParser
from pathlib import Path


class BookmarkHTMLParser(HTMLParser):
    """Parses Netscape Bookmark HTML format exported by Chrome/Edge/Firefox."""

    def __init__(self):
        super().__init__()
        self.folder_stack = []
        self.pending_folder = ""
        self.in_h3 = False
        self.in_a = False
        self.current_h3 = ""
        self.current_a_text = ""
        self.current_url = ""
        self.bookmarks = []

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()

        if tag_lower == "h3":
            self.in_h3 = True
            self.current_h3 = ""
        elif tag_lower == "dl":
            # Push pending folder to stack when a new DL (folder container) starts
            folder_name = self.pending_folder.strip()
            self.folder_stack.append(folder_name)
            self.pending_folder = ""
        elif tag_lower == "a":
            self.in_a = True
            self.current_a_text = ""
            attr_dict = dict(attrs)
            self.current_url = attr_dict.get("href", "").strip()

    def handle_endtag(self, tag):
        tag_lower = tag.lower()

        if tag_lower == "h3":
            self.in_h3 = False
            self.pending_folder = self.current_h3.strip()
        elif tag_lower == "dl":
            if self.folder_stack:
                self.folder_stack.pop()
        elif tag_lower == "a":
            self.in_a = False
            # Clean folder path (join hierarchy with ' / ')
            active_folders = [f for f in self.folder_stack if f]
            folder_path = " / ".join(active_folders) if active_folders else "Root"
            title = self.current_a_text.strip() or self.current_url

            if self.current_url:
                self.bookmarks.append({
                    "folder": folder_path,
                    "title": title,
                    "url": self.current_url
                })

    def handle_data(self, data):
        if self.in_h3:
            self.current_h3 += data
        elif self.in_a:
            self.current_a_text += data


def parse_bookmarks_html(html_content):
    """Parses bookmark HTML string and returns a list of dictionaries with folder, title, url."""
    parser = BookmarkHTMLParser()
    parser.feed(html_content)
    return parser.bookmarks


def convert_html_to_csv(input_path, output_path=None):
    """Converts a Netscape Bookmark HTML file to CSV format."""
    input_file = Path(input_path).resolve()
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    if not output_path:
        output_file = input_file.with_suffix(".csv")
    else:
        output_file = Path(output_path).resolve()

    # Read HTML content with utf-8 or replace errors
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            html_content = f.read()
    except UnicodeDecodeError:
        with open(input_file, "r", encoding="utf-8", errors="replace") as f:
            html_content = f.read()

    bookmarks = parse_bookmarks_html(html_content)

    # Write to CSV with utf-8 encoding (sig BOM for Excel compatibility)
    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["folder", "title", "url"])
        writer.writeheader()
        writer.writerows(bookmarks)

    return output_file, len(bookmarks)


def select_files_via_gui():
    """Opens Tkinter file dialogs to select input HTML and output CSV."""
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    input_path = filedialog.askopenfilename(
        title="Select Chrome/Edge Exported Favorites HTML File",
        filetypes=[("HTML Files", "*.html *.htm"), ("All Files", "*.*")]
    )

    if not input_path:
        print("No input file selected.")
        return

    default_output = str(Path(input_path).with_suffix(".csv"))
    output_path = filedialog.asksaveasfilename(
        title="Save CSV Output As",
        initialfile=Path(default_output).name,
        defaultextension=".csv",
        filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
    )

    if not output_path:
        output_path = default_output

    try:
        out_file, count = convert_html_to_csv(input_path, output_path)
        messagebox.showinfo("Success", f"Successfully converted {count} bookmarks to:\n{out_file}")
        print(f"[Success] Converted {count} bookmarks to: {out_file}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to convert file:\n{e}")
        print(f"[Error] {e}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        in_path = sys.argv[1]
        out_path = sys.argv[2] if len(sys.argv) > 2 else None
        try:
            res_file, total_count = convert_html_to_csv(in_path, out_path)
            print(f"[Success] Converted {total_count} bookmarks -> {res_file}")
        except Exception as err:
            print(f"[Error] {err}", file=sys.stderr)
            sys.exit(1)
    else:
        select_files_via_gui()
