import csv
import subprocess
import tempfile
import os
import shutil
import datetime
import re
import ipaddress
import pacparser  # Requires: pip install pacparser


PAC_LIST = "all_pac.csv"
BACKUP_DIR = "backup"
OLD_PAC_DIR = "old_PAC"
UPDATED_PAC_DIR = "updated_PAC"
MAX_BACKUPS = 10
TIMEOUT = 10


def run(cmd):
    return subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )


def is_subnet_or_range(domain):
    """
    Check if the domain is actually a subnet/IP range (e.g., 10.0.0.0, 172.16.0.0)
    Returns True if it's a subnet pattern that can't be tested for connectivity.
    Keeps individual IPs like 10.2.2.3 for testing.
    """
    ip_pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
    match = re.match(ip_pattern, domain)
    
    if match:
        try:
            ip = ipaddress.ip_address(domain)
            octets = [int(x) for x in domain.split('.')]
            
            if octets[3] == 0:
                return True
            
            if octets[1] == 0 and octets[2] == 0 and octets[3] == 0:
                return True
                
            return False
        except ValueError:
            return False
    
    return False


def extract_domains_from_pac(pac_file, skip_subnets=False):
    """
    Extract domains/IPs from PAC file.
    If skip_subnets=True, filter out subnet patterns like 10.0.0.0
    """
    domains = set()
    try:
        with open(pac_file, "r", errors="ignore") as f:
            content = f.read()
            
        pattern = re.compile(r"""['"]([a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+)['"]""")
        
        for match in pattern.findall(content):
            domain = match.lower()
            if domain.startswith(".") or domain.startswith("*") or "*." in domain:
                continue
            if domain.count(".") >= 1:
                if skip_subnets and is_subnet_or_range(domain):
                    continue
                domains.add(domain)
    except Exception as e:
        print(f"Error reading PAC file {pac_file}: {e}")
        
    return sorted(domains)


def generate_test_logic_csv_from_folder(pac_folder):
    """
    Generate test_logic.csv from PAC files in specified folder.
    Skips subnet patterns like 10.0.0.0, 172.16.0.0 that can't be tested.
    """
    output_file = "test_logic.csv"
    rows = []

    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False

    if not os.path.exists(PAC_LIST):
        print(f"Error: {PAC_LIST} not found.")
        return False

    print(f"\n[Step] Generating test_logic.csv from {pac_folder}/...")
    
    with open(PAC_LIST, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pac_name = row["pac_name"]
            pac_url = row["pac_path"]
            
            pac_file = os.path.join(pac_folder, f"{pac_name}.pac")
            
            if not os.path.exists(pac_file):
                print(f"  Warning: {pac_name}.pac not found in {pac_folder}, skipping")
                continue

            print(f"  Processing {pac_name}...")
            domains = extract_domains_from_pac(pac_file, skip_subnets=True)
            for d in domains:
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', d):
                    rows.append([pac_name, pac_url, f"http://{d}"])
                else:
                    rows.append([pac_name, pac_url, f"https://{d}"])

    if not rows:
        print("  No testable domains found in PAC files.")
        return False

    with open(output_file, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["pac_name", "pac_path", "test_url"])
        writer.writerows(rows)

    print(f"  ✓ {output_file} created ({len(rows)} test cases)")
    return True


def generate_test_reachability_csv_from_folder(pac_folder):
    """
    Generate test_reachability.csv from PAC files in specified folder.
    Includes ALL domains (with subnets).
    """
    output_file = "test_reachability.csv"
    rows = []

    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False

    if not os.path.exists(PAC_LIST):
        print(f"Error: {PAC_LIST} not found.")
        return False

    print(f"\n[Step] Generating test_reachability.csv from {pac_folder}/...")
    
    with open(PAC_LIST, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pac_name = row["pac_name"]
            pac_url = row["pac_path"]
            
            pac_file = os.path.join(pac_folder, f"{pac_name}.pac")
            
            if not os.path.exists(pac_file):
                print(f"  Warning: {pac_name}.pac not found in {pac_folder}, skipping")
                continue

            print(f"  Processing {pac_name}...")
            domains = extract_domains_from_pac(pac_file, skip_subnets=False)
            for d in domains:
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', d):
                    rows.append([pac_name, pac_url, f"http://{d}"])
                else:
                    rows.append([pac_name, pac_url, f"https://{d}"])

    if not rows:
        print("  No domains found in PAC files.")
        return False

    with open(output_file, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["pac_name", "pac_path", "test_url"])
        writer.writerows(rows)

    print(f"  ✓ {output_file} created ({len(rows)} test cases)")
    return True


def backup_pac_files():
    """Backup current PAC files with timestamp."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if not os.path.exists(PAC_LIST):
        print(f"Error: {PAC_LIST} not found.")
        return False

    print("\n[Step] Backing up PAC files...")
    with open(PAC_LIST, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pac_name = row["pac_name"]
            pac_url = row["pac_path"]

            name_dir = os.path.join(BACKUP_DIR, pac_name)
            os.makedirs(name_dir, exist_ok=True)

            filename = f"{pac_name}_{timestamp}.pac"
            filepath = os.path.join(name_dir, filename)

            print(f"  Backing up {pac_name}...")
            r = run(["curl", "-fsSL", pac_url, "-o", filepath])
            if r.returncode != 0:
                print(f"    FAILED to download {pac_url}")
                continue

            backups = sorted(os.listdir(name_dir))
            while len(backups) > MAX_BACKUPS:
                os.remove(os.path.join(name_dir, backups.pop(0)))

    print("  ✓ Backup completed")
    return True


def download_pac_files_to_folder(target_folder):
    """Download PAC files from all_pac.csv into the specified folder."""
    os.makedirs(target_folder, exist_ok=True)
    
    if not os.path.exists(PAC_LIST):
        print(f"Error: {PAC_LIST} not found.")
        return False

    print(f"\n[Step] Downloading PAC files to {target_folder}/...")
    with open(PAC_LIST, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pac_name = row["pac_name"]
            pac_url = row["pac_path"]

            filepath = os.path.join(target_folder, f"{pac_name}.pac")

            print(f"  Downloading {pac_name}...")
            r = run(["curl", "-fsSL", pac_url, "-o", filepath])
            if r.returncode != 0:
                print(f"    FAILED to download {pac_url}")
                continue

    print(f"  ✓ Download to {target_folder}/ completed")
    return True


def evaluate_pac(pac_file, url):
    """Uses pacparser to evaluate the PAC file logic against the URL."""
    try:
        pacparser.init()
        pacparser.parse_pac_file(pac_file)
        proxy_string = pacparser.find_proxy(url)
        pacparser.cleanup()
        return proxy_string
    except Exception as e:
        return f"ERROR: {str(e)}"


def check_connectivity(proxy_decision, url):
    """Test connectivity based on PAC decision."""
    cmd = ["curl", "-I", "-s", "--connect-timeout", str(TIMEOUT), "--max-time", str(TIMEOUT), url]
    
    if "DIRECT" in proxy_decision:
        pass
    elif "PROXY" in proxy_decision:
        match = re.search(r"PROXY\s+([a-zA-Z0-9.-]+:\d+)", proxy_decision)
        if match:
            proxy_address = match.group(1)
            cmd.extend(["-x", f"http://{proxy_address}"])
        else:
            return "PARSE_ERROR"
    else:
        return "UNSUPPORTED_TYPE"

    r = run(cmd)
    return "YES" if r.returncode == 0 else "NO"


def run_logic_test(test_csv, pac_folder, output_file):
    """Test PAC logic only (no connectivity test)."""
    if not os.path.exists(test_csv):
        print(f"Error: {test_csv} not found.")
        return False

    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False

    print(f"\n[Step] Running logic test from {pac_folder}/...")
    with open(output_file, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["pac_name", "test_url", "pac_decision"])

        with open(test_csv, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pac_name = row["pac_name"]
                test_url = row["test_url"]

                pac_file = os.path.join(pac_folder, f"{pac_name}.pac")
                
                if not os.path.exists(pac_file):
                    writer.writerow([pac_name, test_url, "PAC_FILE_NOT_FOUND"])
                    continue

                decision = evaluate_pac(pac_file, test_url)
                writer.writerow([pac_name, test_url, decision])
                print(f"  {pac_name}: {test_url} -> {decision}")

    print(f"  ✓ Logic test completed → {output_file}")
    return True


def run_reachability_test(output_file):
    """Test actual connectivity based on test_reachability.csv (downloads live PAC files)."""
    test_csv = "test_reachability.csv"
    pac_cache = {}
    
    if not os.path.exists(test_csv):
        print(f"Error: {test_csv} not found.")
        return False

    print("\n[Step] Running reachability test (downloading live PAC files)...")
    with open(output_file, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["pac_name", "pac_path", "test_url", "pac_decision", "reachable"])

        with open(test_csv, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pac_path = row["pac_path"]
                pac_name = row["pac_name"]
                test_url = row["test_url"]

                if pac_path not in pac_cache:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pac")
                    tmp.close()
                    r = run(["curl", "-fsSL", pac_path, "-o", tmp.name])
                    pac_cache[pac_path] = tmp.name if r.returncode == 0 else None

                pac_file = pac_cache[pac_path]
                if not pac_file:
                    writer.writerow([pac_name, pac_path, test_url, "PAC_DOWNLOAD_FAILED", "NO"])
                    continue

                decision = evaluate_pac(pac_file, test_url)
                reachable = check_connectivity(decision, test_url)

                writer.writerow([pac_name, pac_path, test_url, decision, reachable])
                print(f"  {pac_name}: {test_url} -> {decision} [{reachable}]")

    # Cleanup
    for f in pac_cache.values():
        if f and os.path.exists(f):
            os.unlink(f)

    print(f"  ✓ Reachability test completed → {output_file}")
    return True


def run_reachability_test_from_folder(pac_folder, output_file):
    """Test actual connectivity using PAC files from local folder."""
    test_csv = "test_reachability.csv"
    
    if not os.path.exists(test_csv):
        print(f"Error: {test_csv} not found.")
        return False

    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False

    print(f"\n[Step] Running reachability test from {pac_folder}/...")
    with open(output_file, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["pac_name", "pac_path", "test_url", "pac_decision", "reachable"])

        with open(test_csv, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pac_path = row["pac_path"]
                pac_name = row["pac_name"]
                test_url = row["test_url"]

                pac_file = os.path.join(pac_folder, f"{pac_name}.pac")
                
                if not os.path.exists(pac_file):
                    writer.writerow([pac_name, pac_path, test_url, "PAC_FILE_NOT_FOUND", "NO"])
                    continue

                decision = evaluate_pac(pac_file, test_url)
                reachable = check_connectivity(decision, test_url)

                writer.writerow([pac_name, pac_path, test_url, decision, reachable])
                print(f"  {pac_name}: {test_url} -> {decision} [{reachable}]")

    print(f"  ✓ Reachability test completed → {output_file}")
    return True


def compare_logic_results(before, after, output_full, output_summary):
    """
    Compare BEFORE and AFTER PAC logic test results.
    Generates two files:
    - Full report with all test cases
    - Summary report with changed items only
    """
    if not os.path.exists(before) or not os.path.exists(after):
        print("Error: Missing before/after result files.")
        return False

    print("\n[Step] Comparing logic test results...")
    before_map = {}
    with open(before) as f:
        for r in csv.DictReader(f):
            key = (r["pac_name"], r["test_url"])
            before_map[key] = r

    changes_count = 0
    new_count = 0
    no_change_count = 0
    changed_rows = []
    
    # Generate full report
    with open(output_full, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow([
            "pac_name", "test_url",
            "before_decision", "after_decision",
            "change"
        ])

        with open(after) as f:
            for r in csv.DictReader(f):
                key = (r["pac_name"], r["test_url"])
                b = before_map.get(key)

                if not b:
                    change = "NEW_ENTRY"
                    changes_count += 1
                    new_count += 1
                elif b["pac_decision"] != r["pac_decision"]:
                    change = "CHANGED"
                    changes_count += 1
                else:
                    change = "NO_CHANGE"
                    no_change_count += 1

                row_data = [
                    r["pac_name"], r["test_url"],
                    b["pac_decision"] if b else "N/A",
                    r["pac_decision"],
                    change
                ]
                
                writer.writerow(row_data)
                
                # Collect changed items for summary report
                if change != "NO_CHANGE":
                    changed_rows.append(row_data)

    # Generate summary report (changed items only)
    with open(output_summary, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow([
            "pac_name", "test_url",
            "before_decision", "after_decision",
            "change"
        ])
        writer.writerows(changed_rows)

    print(f"  ✓ Full comparison → {output_full}")
    print(f"  ✓ Summary (changes only) → {output_summary}")
    print(f"\n  Statistics:")
    print(f"    • Total test cases: {changes_count + no_change_count}")
    print(f"    • Changed: {changes_count - new_count}")
    print(f"    • New entries: {new_count}")
    print(f"    • No change: {no_change_count}")
    return True


def compare_reachability_results(before, after, output_full, output_summary):
    """
    Compare BEFORE and AFTER reachability test results.
    Generates two files:
    - Full report with all test cases
    - Summary report with changed items only
    """
    if not os.path.exists(before) or not os.path.exists(after):
        print("Error: Missing before/after reachability result files.")
        return False

    print("\n[Step] Comparing reachability test results...")
    before_map = {}
    with open(before) as f:
        for r in csv.DictReader(f):
            key = (r["pac_name"], r["test_url"])
            before_map[key] = r

    changes_count = 0
    new_count = 0
    no_change_count = 0
    changed_rows = []
    
    # Generate full report
    with open(output_full, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow([
            "pac_name", "test_url",
            "before_decision", "after_decision",
            "before_reachable", "after_reachable",
            "change"
        ])

        with open(after) as f:
            for r in csv.DictReader(f):
                key = (r["pac_name"], r["test_url"])
                b = before_map.get(key)

                if not b:
                    change = "NEW_ENTRY"
                    changes_count += 1
                    new_count += 1
                elif (b["pac_decision"] != r["pac_decision"]) or (b["reachable"] != r["reachable"]):
                    change = "CHANGED"
                    changes_count += 1
                else:
                    change = "NO_CHANGE"
                    no_change_count += 1

                row_data = [
                    r["pac_name"], r["test_url"],
                    b["pac_decision"] if b else "N/A",
                    r["pac_decision"],
                    b["reachable"] if b else "N/A",
                    r["reachable"],
                    change
                ]
                
                writer.writerow(row_data)
                
                # Collect changed items for summary report
                if change != "NO_CHANGE":
                    changed_rows.append(row_data)

    # Generate summary report (changed items only)
    with open(output_summary, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow([
            "pac_name", "test_url",
            "before_decision", "after_decision",
            "before_reachable", "after_reachable",
            "change"
        ])
        writer.writerows(changed_rows)

    print(f"  ✓ Full comparison → {output_full}")
    print(f"  ✓ Summary (changes only) → {output_summary}")
    print(f"\n  Statistics:")
    print(f"    • Total test cases: {changes_count + no_change_count}")
    print(f"    • Changed: {changes_count - new_count}")
    print(f"    • New entries: {new_count}")
    print(f"    • No change: {no_change_count}")
    return True


# ---------- WORKFLOW FUNCTIONS ----------
def workflow_setup_baseline():
    """
    Workflow 1: Setup baseline testing environment
    - Download PAC files to old_PAC/
    - Generate test_logic.csv from old_PAC/
    - Generate test_reachability.csv from old_PAC/
    - Run BEFORE logic test
    - Run BEFORE reachability test
    """
    print("\n" + "="*60)
    print("  WORKFLOW: Setup Baseline Testing Environment")
    print("="*60)
    
    # Step 1: Download to old_PAC
    if not download_pac_files_to_folder(OLD_PAC_DIR):
        print("\n❌ Workflow failed at download step")
        return
    
    # Step 2: Generate test_logic.csv from local files
    if not generate_test_logic_csv_from_folder(OLD_PAC_DIR):
        print("\n❌ Workflow failed at test_logic.csv generation")
        return
    
    # Step 3: Generate test_reachability.csv from local files
    if not generate_test_reachability_csv_from_folder(OLD_PAC_DIR):
        print("\n❌ Workflow failed at test_reachability.csv generation")
        return
    
    # Step 4: Run BEFORE logic test
    if not run_logic_test("test_logic.csv", OLD_PAC_DIR, "before_logic_result.csv"):
        print("\n❌ Workflow failed at BEFORE logic test")
        return
    
    # Step 5: Run BEFORE reachability test
    if not run_reachability_test("before_reachability_result.csv"):
        print("\n❌ Workflow failed at BEFORE reachability test")
        return
    
    print("\n" + "="*60)
    print("  ✓ BASELINE SETUP COMPLETE")
    print("="*60)
    print("\n  Files created:")
    print("    - old_PAC/                       (original PAC files)")
    print("    - test_logic.csv                 (logic test cases)")
    print("    - test_reachability.csv          (reachability test cases)")
    print("    - before_logic_result.csv        (baseline logic results)")
    print("    - before_reachability_result.csv (baseline reachability results)")
    print("\n  Next step: Make your PAC file changes, then run Workflow 2")
    print("="*60 + "\n")


def workflow_test_and_compare():
    """
    Workflow 2: Test updated PAC files and compare
    - Download updated PAC files to updated_PAC/
    - Run AFTER logic test
    - Run AFTER reachability test
    - Compare with baseline results (both logic and reachability)
    """
    print("\n" + "="*60)
    print("  WORKFLOW: Test Updated PAC Files & Compare")
    print("="*60)
    
    # Check if baseline exists
    if not os.path.exists("before_logic_result.csv"):
        print("\n❌ Baseline logic results not found!")
        print("  Please run Workflow 1 (Setup Baseline) first.")
        return
    
    if not os.path.exists("before_reachability_result.csv"):
        print("\n❌ Baseline reachability results not found!")
        print("  Please run Workflow 1 (Setup Baseline) first.")
        return
    
    # Step 1: Download to updated_PAC
    if not download_pac_files_to_folder(UPDATED_PAC_DIR):
        print("\n❌ Workflow failed at download step")
        return
    
    # Step 2: Run AFTER logic test (uses existing test_logic.csv)
    if not run_logic_test("test_logic.csv", UPDATED_PAC_DIR, "after_logic_result.csv"):
        print("\n❌ Workflow failed at AFTER logic test")
        return
    
    # Step 3: Run AFTER reachability test (uses existing test_reachability.csv)
    if not run_reachability_test("after_reachability_result.csv"):
        print("\n❌ Workflow failed at AFTER reachability test")
        return
    
    # Step 4: Compare logic results (full + summary)
    if not compare_logic_results(
        "before_logic_result.csv",
        "after_logic_result.csv",
        "pac_logic_comparison_full.csv",
        "pac_logic_comparison_summary.csv"
    ):
        print("\n❌ Workflow failed at logic comparison step")
        return
    
    # Step 5: Compare reachability results (full + summary)
    if not compare_reachability_results(
        "before_reachability_result.csv",
        "after_reachability_result.csv",
        "pac_reachability_comparison_full.csv",
        "pac_reachability_comparison_summary.csv"
    ):
        print("\n❌ Workflow failed at reachability comparison step")
        return
    
    print("\n" + "="*60)
    print("  ✓ TESTING & COMPARISON COMPLETE")
    print("="*60)
    print("\n  Files created:")
    print("    - updated_PAC/                              (updated PAC files)")
    print("    - after_logic_result.csv                    (updated logic results)")
    print("    - after_reachability_result.csv             (updated reachability results)")
    print("\n  Comparison Reports:")
    print("    Logic Testing:")
    print("      • pac_logic_comparison_full.csv           (all test cases)")
    print("      • pac_logic_comparison_summary.csv        (changes only)")
    print("    Reachability Testing:")
    print("      • pac_reachability_comparison_full.csv    (all test cases)")
    print("      • pac_reachability_comparison_summary.csv (changes only)")
    print("\n  📊 Review summary reports for quick impact assessment")
    print("="*60 + "\n")


# ---------- MENU ----------
def menu():
    while True:
        print("""
╔═══════════════════════════════════════════════════════════╗
║            PAC File Testing & Validation Tool             ║
╚═══════════════════════════════════════════════════════════╝

┌─ WORKFLOWS (Recommended) ──────────────────────────────────┐
│                                                             │
│  1) Setup Baseline Testing Environment                     │
│     • Download PAC files to old_PAC/                       │
│     • Generate test CSVs from local files                  │
│     • Run BEFORE logic & reachability tests                │
│                                                             │
│  2) Test Updated PAC Files & Compare                       │
│     • Download updated PAC files to updated_PAC/           │
│     • Run AFTER logic & reachability tests                 │
│     • Generate full + summary comparison reports           │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─ INDIVIDUAL OPERATIONS ────────────────────────────────────┐
│                                                             │
│  3) Backup current PAC files (to backup/)                  │
│  4) Generate test_logic.csv from old_PAC/                  │
│  5) Generate test_reachability.csv from old_PAC/           │
│                                                             │
│  6) Run logic test on old_PAC/                             │
│  7) Run logic test on updated_PAC/                         │
│                                                             │
│  8) Run reachability test (downloads live PAC files)       │
│  9) Run reachability test on old_PAC/ (local files)        │
│ 10) Run reachability test on updated_PAC/ (local files)    │
│                                                             │
└─────────────────────────────────────────────────────────────┘

  0) Exit

""")
        choice = input("Select: ").strip()

        if choice == "1":
            workflow_setup_baseline()
            
        elif choice == "2":
            workflow_test_and_compare()
            
        elif choice == "3":
            backup_pac_files()
            
        elif choice == "4":
            generate_test_logic_csv_from_folder(OLD_PAC_DIR)
            
        elif choice == "5":
            generate_test_reachability_csv_from_folder(OLD_PAC_DIR)
            
        elif choice == "6":
            # Run logic test on old_PAC
            if not os.path.exists("test_logic.csv"):
                print("\n❌ test_logic.csv not found. Generate it first (option 4).")
            else:
                run_logic_test("test_logic.csv", OLD_PAC_DIR, "manual_old_logic_result.csv")
            
        elif choice == "7":
            # Run logic test on updated_PAC
            if not os.path.exists("test_logic.csv"):
                print("\n❌ test_logic.csv not found. Generate it first (option 4).")
            else:
                run_logic_test("test_logic.csv", UPDATED_PAC_DIR, "manual_updated_logic_result.csv")
            
        elif choice == "8":
            # Run reachability test (downloads live PAC files)
            if not os.path.exists("test_reachability.csv"):
                print("\n❌ test_reachability.csv not found. Generate it first (option 5).")
            else:
                run_reachability_test("manual_reachability_result.csv")
            
        elif choice == "9":
            # Run reachability test on old_PAC folder
            if not os.path.exists("test_reachability.csv"):
                print("\n❌ test_reachability.csv not found. Generate it first (option 5).")
            else:
                run_reachability_test_from_folder(OLD_PAC_DIR, "manual_old_reachability_result.csv")
            
        elif choice == "10":
            # Run reachability test on updated_PAC folder
            if not os.path.exists("test_reachability.csv"):
                print("\n❌ test_reachability.csv not found. Generate it first (option 5).")
            else:
                run_reachability_test_from_folder(UPDATED_PAC_DIR, "manual_updated_reachability_result.csv")
            
        elif choice == "0":
            print("\nExiting...\n")
            break
        else:
            print("\n❌ Invalid selection\n")


if __name__ == "__main__":
    menu()
