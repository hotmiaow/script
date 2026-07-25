#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import shutil
import zipfile
import tempfile
import argparse
from bs4 import BeautifulSoup, NavigableString

PARAGRAPH_ENDERS = set([
    '。', '！', '？', '；', '”', '』', '」', '〉', '》', '）', ']', '}',
    '.', '!', '?', ';', '"', "'", ')', ']'
])

def is_cjk_or_punctuation(char):
    if not char:
        return False
    o = ord(char)
    # CJK Unified Ideographs, CJK Symbols and Punctuation, Halfwidth and Fullwidth Forms
    if (0x4E00 <= o <= 0x9FFF) or (0x3000 <= o <= 0x303F) or (0xFF00 <= o <= 0xFFEF):
        return True
    if char in '“”‘’—…':
        return True
    return False

def reflow_text_block(block):
    """Reflow plain text block (paragraph) by joining lines intelligently."""
    lines = [line.strip() for line in block.split('\n')]
    if not lines:
        return ""
    
    result = []
    for line in lines:
        if not line:
            continue
        if not result:
            result.append(line)
            continue
        
        last_line = result[-1]
        if not last_line:
            result.append(line)
            continue
            
        last_char = last_line[-1]
        next_char = line[0]
        
        if is_cjk_or_punctuation(last_char) or is_cjk_or_punctuation(next_char):
            result[-1] = last_line + line
        else:
            result[-1] = last_line + " " + line
            
    return "\n".join(result)

def reflow_txt(input_path, output_path):
    """Process plain text files."""
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [line.rstrip('\r\n') for line in f]
        
    blank_lines = sum(1 for line in lines if not line.strip())
    total_lines = len(lines)
    
    # If the file already uses blank lines to separate paragraphs,
    # we can use the original block-based logic.
    if blank_lines >= total_lines * 0.02:
        content = "\n".join(lines)
        paragraphs = re.split(r'\n\s*\n+', content)
        reflowed_paragraphs = []
        for p in paragraphs:
            p_strip = p.strip()
            if p_strip:
                reflowed_paragraphs.append(reflow_text_block(p_strip))
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n\n".join(reflowed_paragraphs) + "\n")
        return

    # For text files with sparse blank lines, use the visual-width heuristic.
    # A line width threshold of 66 corresponds to ~33 CJK characters or ~66 English chars.
    threshold = 66
    reflowed_paragraphs = []
    current_para = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_para:
                reflowed_paragraphs.append(''.join(current_para))
                current_para = []
            continue
            
        # Compute visual width where CJK and smart punctuation count as 2
        w = sum(2 if is_cjk_or_punctuation(c) else 1 for c in line)
        last_char = stripped[-1] if stripped else ''
        ends_with_ender = last_char in PARAGRAPH_ENDERS
        
        if current_para:
            last_line = current_para[-1]
            if last_line and (is_cjk_or_punctuation(last_line[-1]) or is_cjk_or_punctuation(stripped[0])):
                current_para.append(stripped)
            else:
                current_para.append(' ' + stripped)
        else:
            current_para.append(stripped)
            
        # If visual width is less than threshold and it ends with a paragraph-ending punctuation,
        # it marks the end of a paragraph.
        if w < threshold and ends_with_ender:
            reflowed_paragraphs.append(''.join(current_para))
            current_para = []
            
    if current_para:
        reflowed_paragraphs.append(''.join(current_para))
        
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n\n".join(reflowed_paragraphs) + "\n")

def reflow_html_text(text):
    """Replace newlines and formatting spaces within HTML text nodes."""
    def repl(match):
        start_idx = match.start()
        end_idx = match.end()
        char_before = text[start_idx - 1] if start_idx > 0 else ""
        char_after = text[end_idx] if end_idx < len(text) else ""
        if is_cjk_or_punctuation(char_before) or is_cjk_or_punctuation(char_after):
            return ""
        else:
            return " "
    return re.sub(r'[ \t]*\r?\n[ \t\r\n]*', repl, text)

def reflow_html_element(elem):
    """Recursively reflow all text nodes inside an HTML element."""
    for child in list(elem.descendants):
        if isinstance(child, NavigableString) and child.string:
            reflowed = reflow_html_text(child.string)
            child.replace_with(reflowed)

def merge_consecutive_p_tags(soup):
    """Merge broken paragraph tags that belong to the same sentence."""
    p_tags = soup.find_all('p')
    i = 0
    while i < len(p_tags) - 1:
        p1 = p_tags[i]
        p2 = p_tags[i+1]
        
        if p1.parent != p2.parent:
            i += 1
            continue
            
        p1_text = p1.get_text().strip()
        p2_text = p2.get_text().strip()
        
        if not p1_text or not p2_text:
            i += 1
            continue
            
        last_char = p1_text[-1]
        
        # Merge if the first paragraph does not end with standard ending punctuation
        if last_char not in PARAGRAPH_ENDERS:
            first_char_p2 = p2_text[0]
            # If joining non-CJK text, insert a space node
            if not (is_cjk_or_punctuation(last_char) or is_cjk_or_punctuation(first_char_p2)):
                p1.append(" ")
            for child in list(p2.contents):
                p1.append(child)
            p2.decompose()
            p_tags.pop(i+1)
        else:
            i += 1

def process_html_file(file_path, merge_paragraphs):
    """Parse, reflow, and save an individual HTML/XHTML file."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    try:
        soup = BeautifulSoup(content, 'lxml')
    except Exception:
        soup = BeautifulSoup(content, 'html.parser')
        
    if merge_paragraphs:
        merge_consecutive_p_tags(soup)
        
    # Reflow text inside paragraphs, list items, headers, and table cells
    for tag in ['p', 'li', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div']:
        for elem in soup.find_all(tag):
            # Skip nested divs if we already processed them or if they contain other processed elements
            reflow_html_element(elem)
            
    with open(file_path, 'w', encoding='utf-8') as f:
        # Avoid pretty printing as it adds undesired linebreaks
        f.write(str(soup))

def reflow_epub(input_path, output_path, merge_paragraphs):
    """Extract, reflow all HTML files, and repackage an EPUB file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract EPUB (zip format)
        with zipfile.ZipFile(input_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
            
        # Process all HTML and XHTML files
        for root, _, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(('.html', '.xhtml', '.htm')):
                    file_path = os.path.join(root, file)
                    process_html_file(file_path, merge_paragraphs)
                    
        # Re-pack EPUB
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as epub:
            # 1. mimetype must be the first file and uncompressed
            mimetype_path = os.path.join(temp_dir, 'mimetype')
            if os.path.exists(mimetype_path):
                epub.write(mimetype_path, 'mimetype', compress_type=zipfile.ZIP_STORED)
                
            # 2. Write all other files
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, temp_dir)
                    if rel_path == 'mimetype':
                        continue
                    epub.write(full_path, rel_path)

def reflow_mobi(input_path, output_path, merge_paragraphs):
    """Convert MOBI to EPUB, reflow the EPUB, and convert it back to MOBI using ebook-convert."""
    # Find ebook-convert
    ebook_convert = shutil.which('ebook-convert')
    if not ebook_convert:
        print("Error: 'ebook-convert' is required to process MOBI files, but it was not found in PATH.", file=sys.stderr)
        sys.exit(1)
        
    temp_epub_in = tempfile.mktemp(suffix='.epub')
    temp_epub_out = tempfile.mktemp(suffix='.epub')
    
    try:
        # Convert MOBI to EPUB
        print("Converting MOBI to EPUB...")
        os.system(f'"{ebook_convert}" "{input_path}" "{temp_epub_in}" >/dev/null 2>&1')
        if not os.path.exists(temp_epub_in):
            print("Error: Failed to convert MOBI to EPUB.", file=sys.stderr)
            sys.exit(1)
            
        # Reflow the temporary EPUB
        print("Reflowing EPUB contents...")
        reflow_epub(temp_epub_in, temp_epub_out, merge_paragraphs)
        
        # Convert EPUB back to MOBI
        print("Converting EPUB back to MOBI...")
        os.system(f'"{ebook_convert}" "{temp_epub_out}" "{output_path}" >/dev/null 2>&1')
        if not os.path.exists(output_path):
            print("Error: Failed to convert EPUB back to MOBI.", file=sys.stderr)
            sys.exit(1)
            
    finally:
        # Clean up temp files
        for temp_file in [temp_epub_in, temp_epub_out]:
            if os.path.exists(temp_file):
                os.remove(temp_file)

def main():
    parser = argparse.ArgumentParser(description="Smart reflow tool for TXT, EPUB, and MOBI files.")
    parser.path_args = parser.add_argument("input_file", help="Path to the input file (.txt, .epub, .mobi)")
    parser.add_argument("-o", "--output", help="Path to the output file (optional)")
    parser.add_argument("--no-merge", action="store_true", help="Do not merge consecutive broken paragraphs")
    
    args = parser.parse_args()
    
    input_path = os.path.abspath(args.input_file)
    if not os.path.exists(input_path):
        print(f"Error: Input file '{args.input_file}' does not exist.", file=sys.stderr)
        sys.exit(1)
        
    # Determine extension
    _, ext = os.path.splitext(input_path.lower())
    if ext not in ['.txt', '.epub', '.mobi']:
        print(f"Error: Unsupported file format '{ext}'. Only .txt, .epub, and .mobi are supported.", file=sys.stderr)
        sys.exit(1)
        
    # Determine output path
    if args.output:
        output_path = os.path.abspath(args.output)
    else:
        base, extension = os.path.splitext(input_path)
        output_path = f"{base}_reflowed{extension}"
        
    merge_paragraphs = not args.no_merge
    
    print(f"Processing '{input_path}'...")
    if ext == '.txt':
        reflow_txt(input_path, output_path)
    elif ext == '.epub':
        reflow_epub(input_path, output_path, merge_paragraphs)
    elif ext == '.mobi':
        reflow_mobi(input_path, output_path, merge_paragraphs)
        
    print(f"Successfully reflowed ebook saved to: {output_path}")

if __name__ == '__main__':
    main()
