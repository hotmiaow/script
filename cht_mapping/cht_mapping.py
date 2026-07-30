import os
import re
import csv
from pathlib import Path

def detect_delimiter_and_encoding(file_path):
    """
    Detect encoding and delimiter (comma, semicolon, tab, pipe) of a CSV file.
    """
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "utf-16"]
    
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc, errors="strict") as f:
                sample = f.read(8192)
                if not sample:
                    return enc, ","
                
                # Check line break sample
                first_line = sample.splitlines()[0] if sample.splitlines() else ""
                
                # Try csv.Sniffer
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
                    return enc, dialect.delimiter
                except Exception:
                    # Count delimiter occurrences in first line
                    counts = {d: first_line.count(d) for d in [",", ";", "\t", "|"]}
                    best_delim = max(counts, key=counts.get)
                    return enc, best_delim if counts[best_delim] > 0 else ","
        except (UnicodeDecodeError, Exception):
            continue
            
    return "utf-8-sig", ","

def get_col_value(row, possible_names, default=""):
    """
    Find value from a CSV row dictionary matching any of the possible column names (case-insensitive).
    Tries exact match first, then substring match.
    """
    row_keys_lower = {str(k).strip().lower(): k for k in row.keys() if k is not None}
    
    # 1. Exact match (case insensitive, stripped)
    for name in possible_names:
        name_lower = name.strip().lower()
        if name_lower in row_keys_lower:
            actual_key = row_keys_lower[name_lower]
            val = row[actual_key]
            return val.strip() if val is not None else ""

    # 2. Substring match (e.g. "Rule Comment (CHT)" matches "comment")
    for key_lower, actual_key in row_keys_lower.items():
        for name in possible_names:
            if name.strip().lower() in key_lower:
                val = row[actual_key]
                return val.strip() if val is not None else ""
                
    return default

def main():
    script_dir = Path(__file__).parent.resolve()
    policy_file = script_dir / "policy.csv"
    change_file = script_dir / "change.csv"
    result_file = script_dir / "result.csv"

    print("=" * 60)
    print(f"CHT Mapping Tool")
    print(f"Working Directory: {script_dir}")
    print("=" * 60)

    if not policy_file.exists():
        print(f"\n[ERROR] '{policy_file.name}' not found in {script_dir}")
        print("Please make sure policy.csv is located in the same directory as this script.")
        return

    if not change_file.exists():
        print(f"\n[ERROR] '{change_file.name}' not found in {script_dir}")
        print("Please make sure change.csv is located in the same directory as this script.")
        return

    # ----------------------------------------------------
    # Step 1: Load change.csv
    # ----------------------------------------------------
    enc_change, delim_change = detect_delimiter_and_encoding(change_file)
    print(f"\n[INFO] Loading {change_file.name} (Encoding: {enc_change}, Delimiter: {repr(delim_change)})")
    
    change_lookup = {}
    with open(change_file, mode="r", encoding=enc_change, errors="replace") as f:
        reader = csv.DictReader(f, delimiter=delim_change)
        
        # Print detected headers for diagnostic aid
        headers = reader.fieldnames or []
        print(f"       Detected headers in change.csv: {headers}")

        for row in reader:
            cht_no = get_col_value(row, ["change number", "change_number", "cht", "cht number", "change ticket", "number", "ticket"])
            if cht_no:
                # Extract CHT pattern from ticket number if it contains extra text
                cht_match = re.search(r'CHT\d{7,8}', cht_no, re.IGNORECASE)
                cht_key = cht_match.group(0).upper() if cht_match else cht_no.upper()
                
                requester = get_col_value(row, ["requester", "requster", "requested_by", "requested by", "opened_by", "opened by", "author"])
                requester_group = get_col_value(row, ["requester_group", "requester group", "requster_group", "request_group", "assignment group", "group"])
                short_desc = get_col_value(row, ["short description", "short_description", "description", "summary"])
                
                change_lookup[cht_key] = {
                    "requester": requester,
                    "requester_group": requester_group,
                    "short_description": short_desc
                }

    print(f"       Loaded {len(change_lookup)} change records.")

    # ----------------------------------------------------
    # Step 2: Process policy.csv
    # ----------------------------------------------------
    enc_policy, delim_policy = detect_delimiter_and_encoding(policy_file)
    print(f"\n[INFO] Reading {policy_file.name} (Encoding: {enc_policy}, Delimiter: {repr(delim_policy)})")

    # Match "CHT" followed by 7 or 8 digits (or format like CHT1234567, CHT-1234567, CHT12345678)
    cht_pattern = re.compile(r'\bCHT-?\d{7,8}\b', re.IGNORECASE)

    output_rows = []
    total_policy_rows = 0
    extracted_cht_count = 0
    rows_with_comments = 0

    with open(policy_file, mode="r", encoding=enc_policy, errors="replace") as f:
        reader = csv.DictReader(f, delimiter=delim_policy)
        headers = reader.fieldnames or []
        print(f"       Detected headers in policy.csv: {headers}")

        # Diagnostic check for comment column
        comment_col_found = any(get_col_value({h: h}, ["comment", "comments", "description", "note", "notes", "remark", "remarks", "cht"]) for h in headers)
        if not comment_col_found:
            print(f"\n[WARNING] Could not automatically match a 'comment' header in policy.csv!")
            print(f"          Available headers are: {headers}")
            print(f"          The script will check all columns in each row for CHT patterns as fallback.\n")

        for row in reader:
            total_policy_rows += 1
            
            policy_name = get_col_value(row, ["policy name", "policy_name", "policy", "device name", "device"])
            rule_id = get_col_value(row, ["securetrack rule id", "rule id", "rule_id", "securetrack_rule_id", "rule number"])
            rule_name = get_col_value(row, ["rule name", "rule_name", "rule"])
            
            # Try to get comment from known column names first
            comment = get_col_value(row, ["comment", "comments", "description", "note", "notes", "remark", "remarks", "cht"])

            # Fallback: If comment column wasn't explicitly found, join all row values to search for CHT numbers
            search_text = comment if comment else " ".join(str(v) for v in row.values() if v)
            if comment:
                rows_with_comments += 1

            # Extract all CHT numbers
            cht_matches = cht_pattern.findall(search_text)
            
            if cht_matches:
                seen_chts = set()
                for cht in cht_matches:
                    # Clean up hyphens if present (e.g. CHT-1234567 -> CHT1234567)
                    cht_formatted = cht.upper().replace("-", "")
                    if cht_formatted not in seen_chts:
                        seen_chts.add(cht_formatted)
                        extracted_cht_count += 1

                        # Query change lookup
                        change_info = change_lookup.get(cht_formatted, {})
                        requester = change_info.get("requester", "")
                        requester_group = change_info.get("requester_group", "")

                        output_rows.append({
                            "Policy Name": policy_name,
                            "SecureTrack Rule ID": rule_id,
                            "Rule Name": rule_name,
                            "Change Number": cht_formatted,
                            "Requester": requester,
                            "Requester Group": requester_group
                        })

    # ----------------------------------------------------
    # Step 3: Write result.csv
    # ----------------------------------------------------
    fieldnames = [
        "Policy Name",
        "SecureTrack Rule ID",
        "Rule Name",
        "Change Number",
        "Requester",
        "Requester Group"
    ]

    with open(result_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print("\n" + "=" * 60)
    print("SUMMARY RESULTS")
    print("=" * 60)
    print(f"Total policy rows processed: {total_policy_rows}")
    print(f"Total CHT numbers extracted: {extracted_cht_count}")
    print(f"Matched & output rows written to {result_file.name}: {len(output_rows)}")
    print("=" * 60)

if __name__ == "__main__":
    main()
