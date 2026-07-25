#!/usr/bin/env python3
import subprocess
import sys
import re
import time

DOWNLOAD_LIST_FILE = "download_list.txt"
TDL_PATH = "./tdl"
DELAY_SEC = 0.0

URL_RE = re.compile(r"(https?://t\.me/[^/]+/)(\d+)/?$")

def read_urls_from_file(filepath: str):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {filepath}")
    
    # Clean and filter lines
    urls = []
    for i, line in enumerate(lines, 1):
        clean_line = line.strip()
        if clean_line and not clean_line.startswith('#'):
            urls.append(clean_line)
            print(f"Read line {i}: {clean_line}")
    
    if len(urls) < 2:
        raise ValueError(f"{filepath} must contain at least 2 URLs")
    
    return urls[0], urls[1]

def extract_info(url: str):
    m = URL_RE.match(url.strip())
    if not m:
        raise ValueError(f"Invalid Telegram URL format: {url}")
    return m.group(1), int(m.group(2))

def download_range(start_url: str, end_url: str):
    base_start, start_id = extract_info(start_url)
    base_end, end_id = extract_info(end_url)

    if base_start != base_end:
        raise ValueError("Start and end links must be from the same channel/group.")
    if end_id < start_id:
        raise ValueError(f"End ID ({end_id}) must be >= Start ID ({start_id}).")

    print(f"Will download from {start_id} to {end_id} (total: {end_id - start_id + 1} items)")

    for msg_id in range(start_id, end_id + 1):
        url = f"{base_start}{msg_id}"
        cmd = [TDL_PATH, "dl", "-u", url]
        print(f"Running: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            print(f"[ERROR] '{TDL_PATH}' not found. Ensure it exists and is executable.")
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print(f"[WARN] Download failed for {url}: {e}. Continuing...")
        
        if DELAY_SEC > 0:
            time.sleep(DELAY_SEC)

def main():
    try:
        start_url, end_url = read_urls_from_file(DOWNLOAD_LIST_FILE)
        print(f"Start URL: {start_url}")
        print(f"End URL: {end_url}")
        download_range(start_url, end_url)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
