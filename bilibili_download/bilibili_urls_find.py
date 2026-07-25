import requests
import json
import re
import time
from urllib.parse import urlparse, urlunparse
import random

def get_bilibili_dynamic_urls_manual(text_content):
    """
    Extract Bilibili URLs from manually saved content
    
    Args:
        text_content (str): Content from the dynamic page (manually copied)
    
    Returns:
        list: List of cleaned Bilibili video URLs
    """
    # More comprehensive regex patterns for Bilibili URLs
    patterns = [
        r'https://www\.bilibili\.com/video/BV[a-zA-Z0-9]+/?[^?\s"\']*',
        r'bilibili\.com/video/BV[a-zA-Z0-9]+/?[^?\s"\']*',
        r'BV[a-zA-Z0-9]{10}',  # Just the BVID
        r'/video/BV[a-zA-Z0-9]+/?[^?\s"\']*'
    ]
    
    all_urls = []
    
    for pattern in patterns:
        matches = re.findall(pattern, text_content, re.IGNORECASE)
        for match in matches:
            # Normalize the URL
            if match.startswith('BV'):
                url = f'https://www.bilibili.com/video/{match}'
            elif match.startswith('/video/'):
                url = f'https://www.bilibili.com{match}'
            elif not match.startswith('http'):
                url = f'https://{match}'
            else:
                url = match
            
            # Clean the URL (remove query parameters)
            parsed_url = urlparse(url)
            clean_url = urlunparse((
                parsed_url.scheme or 'https',
                parsed_url.netloc or 'www.bilibili.com',
                parsed_url.path.rstrip('/'),
                '', '', ''
            ))
            
            # Validate it's a proper Bilibili video URL
            if 'bilibili.com/video/BV' in clean_url and clean_url not in all_urls:
                all_urls.append(clean_url)
    
    return all_urls

def create_bilibili_url_extractor_script():
    """
    Creates a complete script file for Bilibili URL extraction
    """
    script_content = '''#!/usr/bin/env python3
"""
Bilibili Dynamic URL Extractor
Extracts video URLs from Bilibili dynamic page content
"""

import re
import os
from urllib.parse import urlparse, urlunparse

def extract_bilibili_urls(text_content):
    """
    Extract and clean Bilibili video URLs from text content
    
    Args:
        text_content (str): Content containing Bilibili URLs
    
    Returns:
        list: List of cleaned Bilibili video URLs
    """
    # Multiple patterns to catch different URL formats
    patterns = [
        r'https://www\\.bilibili\\.com/video/BV[a-zA-Z0-9]+/?[^?\\s"\\\']*',
        r'bilibili\\.com/video/BV[a-zA-Z0-9]+/?[^?\\s"\\\']*',
        r'BV[a-zA-Z0-9]{10}',  # Just the BVID
        r'/video/BV[a-zA-Z0-9]+/?[^?\\s"\\\']*'
    ]
    
    all_urls = []
    
    for pattern in patterns:
        matches = re.findall(pattern, text_content, re.IGNORECASE)
        for match in matches:
            # Normalize the URL
            if match.startswith('BV'):
                url = f'https://www.bilibili.com/video/{match}'
            elif match.startswith('/video/'):
                url = f'https://www.bilibili.com{match}'
            elif not match.startswith('http'):
                url = f'https://{match}'
            else:
                url = match
            
            # Clean the URL (remove query parameters)
            parsed_url = urlparse(url)
            clean_url = urlunparse((
                parsed_url.scheme or 'https',
                parsed_url.netloc or 'www.bilibili.com',
                parsed_url.path.rstrip('/'),
                '', '', ''
            ))
            
            # Validate and deduplicate
            if 'bilibili.com/video/BV' in clean_url and clean_url not in all_urls:
                all_urls.append(clean_url)
    
    return all_urls

def process_file(input_file, output_file=None):
    """
    Process a text file and extract Bilibili URLs
    
    Args:
        input_file (str): Path to input text file
        output_file (str): Path to output file (optional)
    
    Returns:
        list: List of extracted URLs
    """
    try:
        # Read input file with multiple encoding attempts
        encodings = ['utf-8', 'gbk', 'utf-16', 'latin-1']
        content = None
        
        for encoding in encodings:
            try:
                with open(input_file, 'r', encoding=encoding) as file:
                    content = file.read()
                print(f"Successfully read file with {encoding} encoding")
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            raise ValueError("Could not read file with any supported encoding")
        
        # Extract URLs
        urls = extract_bilibili_urls(content)
        
        # Display results
        print(f"\\nFound {len(urls)} unique Bilibili video URLs:")
        print("-" * 60)
        for i, url in enumerate(urls, 1):
            print(f"{i:3d}. {url}")
        
        # Save to output file if specified
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as file:
                for url in urls:
                    file.write(url + '\\n')
            print(f"\\nURLs saved to: {output_file}")
        
        return urls
        
    except FileNotFoundError:
        print(f"Error: File '{input_file}' not found")
        return []
    except Exception as e:
        print(f"Error: {str(e)}")
        return []

def main():
    """
    Main interactive function
    """
    print("Bilibili Dynamic URL Extractor")
    print("=" * 50)
    print("Instructions:")
    print("1. Go to https://space.bilibili.com/81305729/dynamic")
    print("2. Save the page content to a text file (Ctrl+S or copy content)")
    print("3. Use this script to extract video URLs")
    print()
    
    input_file = input("Enter the path to your text file: ").strip()
    
    if not os.path.exists(input_file):
        print(f"Error: File '{input_file}' does not exist")
        return
    
    output_choice = input("Save URLs to file? (y/n): ").strip().lower()
    output_file = None
    
    if output_choice == 'y':
        output_file = input("Enter output filename (default: bilibili_urls.txt): ").strip()
        if not output_file:
            output_file = "bilibili_urls.txt"
    
    # Process the file
    urls = process_file(input_file, output_file)
    
    if urls:
        print(f"\\nExtraction completed! Found {len(urls)} URLs")
    else:
        print("\\nNo URLs found. Make sure the file contains Bilibili dynamic content.")

if __name__ == "__main__":
    main()
'''
    
    # Save the script to a file
    with open('bilibili_url_extractor.py', 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print("Complete script saved as 'bilibili_url_extractor.py'")
    return script_content

# Test the function with sample content
sample_content = """
这里是一些动态内容
https://www.bilibili.com/video/BV1h6bWz5EdU/?spm_id_from=333.1387.0.0
更多文本内容
https://www.bilibili.com/video/BV1PabFzYEWC/?spm_id_from=333.1387.0.0
BV1okt2z7EZk
/video/BV1abc123def/
"""

# Test extraction
urls = get_bilibili_dynamic_urls_manual(sample_content)
print("Test extraction results:")
for i, url in enumerate(urls, 1):
    print(f"{i}. {url}")

# Create the complete script file
create_bilibili_url_extractor_script()
