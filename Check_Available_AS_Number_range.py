import os
import re
import csv
import argparse

def list_log_files():
    """List .log and .txt files in the current directory."""
    return [f for f in os.listdir('.') if f.endswith('.log') or f.endswith('.txt')]

def parse_bgp_output(bgp_output):
    """Extract AS numbers from the BGP output."""
    as_numbers = set()
    for line in bgp_output.splitlines():
        matches = re.findall(r'\s(?:\d+\s)+', line)
        for m in matches:
            numbers = re.findall(r'\d+', m)
            as_numbers.update(int(num) for num in numbers)
    return as_numbers

def check_as_across_logs(log_outputs, start, end):
    """Check which AS numbers are found across which log files."""
    results = []
    for asn in range(start, end + 1):
        found_in = [log_file for log_file, asns in log_outputs.items() if asn in asns]
        results.append({
            "AS Number": asn,
            "Found": "Yes" if found_in else "No",
            "Found In": ", ".join(found_in) if found_in else "Not Found"
        })
    return results

def write_csv(data, output_file):
    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ["AS Number", "Found", "Found In"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)

def main():
    parser = argparse.ArgumentParser(description="Parse local BGP output files and analyze AS numbers.")
    parser.add_argument("range", help="AS number range (e.g. 66666-67777)")
    parser.add_argument("--output", default="as_range_report.csv", help="CSV output filename")

    args = parser.parse_args()
    start, end = map(int, args.range.split('-'))

    log_files = list_log_files()
    if not log_files:
        print("❌ No .log or .txt files found in the current directory.")
        return

    print("\n📄 Found the following log files:")
    for f in log_files:
        print(f"  - {f}")
    choice = input("\nDo you want to use these log files for AS analysis? (y/n): ").strip().lower()
    if choice != 'y':
        print("Aborted by user.")
        return

    log_outputs = {}
    for filename in log_files:
        with open(filename, 'r') as f:
            content = f.read()
            as_numbers = parse_bgp_output(content)
            log_outputs[filename] = as_numbers

    results = check_as_across_logs(log_outputs, start, end)
    write_csv(results, args.output)

    print(f"\n✅ Completed. Results written to: {args.output}")
    print(f"Analyzed ASNs from {start} to {end} across {len(log_outputs)} file(s).")

if __name__ == "__main__":
    main()