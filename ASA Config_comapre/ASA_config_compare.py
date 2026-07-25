import os
import csv
from pathlib import Path
import re
from collections import defaultdict


def normalize_section_content(content, sections_order):
    """Normalize content by adding placeholders for missing sections and ensuring order."""
    normalized = []
    section_markers = {}
    current_section = None
    current_content = []

    # First pass: identify existing sections and their content
    for line in content:
        if line.startswith('!--- ') and line.endswith(' CONFIGURATION ---'):
            if current_section and current_content:
                section_markers[current_section] = current_content
            current_section = line.replace('!--- ', '').replace(' CONFIGURATION ---', '').lower()
            current_content = [line]
        elif current_section:
            current_content.append(line)
        else:
            normalized.append(line)

    if current_section and current_content:
        section_markers[current_section] = current_content

    # Second pass: add all sections in order with placeholders for missing ones
    for section in sections_order:
        if section in section_markers:
            normalized.extend(section_markers[section])
        else:
            # Add placeholder for missing section
            normalized.append(f"!--- {section.upper()} CONFIGURATION ---")
            normalized.append(f"! No {section} configuration present")
            normalized.append("!")

    return normalized

def find_segment_boundaries(content):
    """Find the start and end lines of each configuration segment."""
    segments = []
    current_segment = None
    start_line = 0

    for i, line in enumerate(content):
        if line.startswith('!--- ') and line.endswith(' CONFIGURATION ---'):
            if current_segment:
                segments.append((current_segment, start_line, i - 1))
            current_segment = line.replace('!--- ', '').replace(' CONFIGURATION ---', '').lower()
            start_line = i
        elif i == len(content) - 1 and current_segment:
            segments.append((current_segment, start_line, i))

    return segments

import os
import csv
from pathlib import Path
import re
from collections import defaultdict

class ASAConfigParser:
    def __init__(self, sections):
        self.sections = sections
        self.section_patterns = {
            section: re.compile(rf'^{section}(?:\s|$)', re.IGNORECASE)
            for section in self.sections
        }

    def get_command_key(self, line):
        """Extract a key for sorting and matching similar commands."""
        line = line.strip().strip('!')

        if not line:
            return ''

        words = line.split()
        if not words:
            return ''

        if words[0].lower() == 'interface':
            return f"interface_{words[1]}" if len(words) > 1 else 'interface'

        if words[0].lower() == 'access-list':
            return f"access-list_{words[1]}" if len(words) > 1 else 'access-list'

        if words[0].lower() == 'object':
            key_parts = words[:3] if len(words) > 2 else words
            return '_'.join(key_parts)

        key = words[0]
        numbers = re.findall(r'\d+', line)
        if numbers:
            key = f"{key}_{'_'.join(numbers)}"

        return key.lower()

    def parse_config(self, content):
        """Parse ASA config into organized sections with command matching."""
        sections = defaultdict(list)
        current_section = None
        current_block = []

        for line in content:
            line = line.rstrip()
            if not line:
                continue

            new_section = None
            for section, pattern in self.section_patterns.items():
                if pattern.match(line):
                    new_section = section
                    break

            if new_section:
                if current_section and current_block:
                    sections[current_section].append(current_block)
                current_section = new_section
                current_block = [line]
            elif line.startswith(' ') and current_block:
                current_block.append(line)
            else:
                if current_block:
                    if current_section:
                        sections[current_section].append(current_block)
                    current_block = []
                if current_section:
                    current_block = [line]
                else:
                    sections['global'].append([line])

        if current_block:
            if current_section:
                sections[current_section].append(current_block)
            else:
                sections['global'].append(current_block)

        return sections

def read_file_content(file_path):
    """Read and return file content as a list of lines."""
    encodings = ['utf-8', 'latin-1', 'utf-16']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                return [line.rstrip() for line in file.readlines()]
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Unable to read file {file_path} with supported encodings")

def load_sections_from_csv(csv_file):
    """Load sections from a CSV file."""
    sections = []
    try:
        with open(csv_file, 'r', encoding='utf-8-sig') as file:
            reader = csv.reader(file)
            for row in reader:
                if row:
                    sections.append(row[0].strip().lower())
    except Exception as e:
        raise ValueError(f"Error reading CSV file: {e}")

    if not sections:
        raise ValueError("The CSV file does not contain any valid sections.")

    return sections

def pad_contents_for_alignment(all_contents, sections_order):
    """Add padding to align sections while handling missing sections."""
    normalized_contents = [normalize_section_content(content, sections_order) for content in all_contents]

    section_sizes = defaultdict(int)
    for content in normalized_contents:
        for segment, start, end in find_segment_boundaries(content):
            section_sizes[segment] = max(section_sizes[segment], end - start + 1)

    padded_contents = []
    for content in normalized_contents:
        new_content = []
        current_pos = 0

        for segment, start, end in find_segment_boundaries(content):
            if start > current_pos:
                new_content.extend(content[current_pos:start])

            segment_content = content[start:end + 1]
            new_content.extend(segment_content)

            padding_needed = section_sizes[segment] - (end - start + 1)
            if padding_needed > 0:
                new_content.extend([''] * padding_needed)

            current_pos = end + 1

        if current_pos < len(content):
            new_content.extend(content[current_pos:])

        padded_contents.append(new_content)

    max_length = max(len(content) for content in padded_contents)
    for content in padded_contents:
        while len(content) < max_length:
            content.append('')

    return padded_contents

def compare_configs(directory_path, sections_csv, baseline_file=None):
    """Compare all configuration files and generate CSV output with section alignment."""
    sections_order = load_sections_from_csv(sections_csv)

    config_files = []
    for file in Path(directory_path).glob('*'):
        if file.suffix.lower() in ['.txt', '.log']:
            config_files.append(str(file))

    if not config_files:
        print("No configuration files found in the directory.")
        return

    if baseline_file is None:
        print("\nAvailable configuration files:")
        for idx, file in enumerate(config_files, 1):
            print(f"{idx}. {os.path.basename(file)}")

        while True:
            try:
                choice = input("\nSelect baseline file number (default is 1): ").strip()
                if not choice:
                    baseline_file = config_files[0]
                    break
                choice = int(choice)
                if 1 <= choice <= len(config_files):
                    baseline_file = config_files[choice - 1]
                    break
                print("Invalid selection. Please try again.")
            except ValueError:
                print("Please enter a valid number.")

    parser = ASAConfigParser(sections_order)
    print(f"\nProcessing baseline file: {os.path.basename(baseline_file)}")

    all_contents = []
    headers = []

    for file in config_files:
        print(f"Processing: {os.path.basename(file)}")
        content = read_file_content(file)
        sections = parser.parse_config(content)

        formatted_content = []
        for section in sections_order:
            if section in sections and sections[section]:
                formatted_content.append(f"!--- {section.upper()} CONFIGURATION ---")
                for block in sections[section]:
                    formatted_content.extend(block)
                formatted_content.append('!')

        all_contents.append(formatted_content)
        headers.append(os.path.basename(file))

    print("\nAligning configurations...")
    aligned_contents = pad_contents_for_alignment(all_contents, sections_order)

    output_file = os.path.join(directory_path, 'asa_config_comparison.csv')
    print("\nWriting comparison to CSV...")

    with open(output_file, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(headers)

        total_rows = len(aligned_contents[0])
        for idx, row in enumerate(zip(*aligned_contents)):
            writer.writerow(row)
            if (idx + 1) % 1000 == 0:
                print(f"Progress: {idx + 1}/{total_rows} lines processed")

    print(f"\nComparison complete. Results saved to: {output_file}")
    print(f"Baseline file used: {os.path.basename(baseline_file)}")
    print(f"Number of files compared: {len(config_files)}")

def main():
    print("Cisco ASA Configuration Comparison Tool")
    print("======================================")

    directory = input("\nEnter the directory path (press Enter for current directory): ").strip()
    if not directory:
        directory = os.getcwd()
        print(f"Using current directory: {directory}")

    if not os.path.isdir(directory):
        print("Invalid directory path. Using current directory instead.")
        directory = os.getcwd()

    sections_csv = input("\nEnter the path to the CSV file with section names:(enter for section.csv) ").strip()
    if not os.path.isfile(sections_csv):
        print("Invalid CSV file path.")
        return

    compare_configs(directory, sections_csv)

if __name__ == "__main__":
    main()
