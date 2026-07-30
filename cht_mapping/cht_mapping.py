import os
import re
import csv
from pathlib import Path

def get_col_value(row, possible_names, default=""):
    """
    Find value from a CSV row dictionary matching any of the possible column names (case-insensitive).
    """
    row_keys_lower = {str(k).strip().lower(): k for k in row.keys() if k is not None}
    for name in possible_names:
        name_lower = name.strip().lower()
        if name_lower in row_keys_lower:
            actual_key = row_keys_lower[name_lower]
            val = row[actual_key]
            return val.strip() if val is not None else ""
    return default

def main():
    script_dir = Path(__file__).parent.resolve()
    policy_file = script_dir / "policy.csv"
    change_file = script_dir / "change.csv"
    result_file = script_dir / "result.csv"

    print(f"Script Directory: {script_dir}")
    print(f"Reading policy file: {policy_file}")
    print(f"Reading change file: {change_file}")

    if not policy_file.exists():
        print(f"Error: {policy_file.name} not found in {script_dir}")
        return

    if not change_file.exists():
        print(f"Error: {change_file.name} not found in {script_dir}")
        return

    # Step 1: Load change.csv into lookup dictionary
    # Key: Upper-cased Change Number (e.g. CHT1234567) -> Value: dict of requester and requester_group
    change_lookup = {}
    with open(change_file, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cht_no = get_col_value(row, ["change number", "change_number", "cht", "cht number", "change ticket"])
            if cht_no:
                cht_key = cht_no.upper()
                requester = get_col_value(row, ["requester", "requster", "requested_by", "requested by"])
                requester_group = get_col_value(row, ["requester_group", "requester group", "requster_group", "request_group", "assignment group"])
                short_desc = get_col_value(row, ["short description", "short_description", "description", "summary"])
                
                change_lookup[cht_key] = {
                    "requester": requester,
                    "requester_group": requester_group,
                    "short_description": short_desc
                }

    print(f"Loaded {len(change_lookup)} change records from {change_file.name}")

    # Step 2: Read policy.csv, extract CHT numbers, and map details
    # CHT format: "CHT" followed by 7 or 8 digits (e.g., CHT1234567 or CHT12345678)
    cht_pattern = re.compile(r'\bCHT\d{7,8}\b', re.IGNORECASE)

    output_rows = []
    total_policy_rows = 0
    extracted_cht_count = 0

    with open(policy_file, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_policy_rows += 1
            
            policy_name = get_col_value(row, ["policy name", "policy_name", "policy", "device name", "device"])
            rule_id = get_col_value(row, ["securetrack rule id", "rule id", "rule_id", "securetrack_rule_id", "rule number"])
            rule_name = get_col_value(row, ["rule name", "rule_name", "rule"])
            comment = get_col_value(row, ["comment", "comments", "description", "note", "notes"])

            # Extract all CHT numbers from comment
            cht_matches = cht_pattern.findall(comment)
            
            if cht_matches:
                # Deduplicate CHT numbers in the same comment while maintaining order
                seen_chts = set()
                for cht in cht_matches:
                    cht_formatted = cht.upper()
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

    # Step 3: Output results to result.csv
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

    print(f"Processed {total_policy_rows} rows from {policy_file.name}.")
    print(f"Extracted {extracted_cht_count} CHT entries.")
    print(f"Successfully generated {result_file.name} with {len(output_rows)} result rows.")

if __name__ == "__main__":
    main()
