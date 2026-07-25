import csv
import subprocess
import tempfile
import os
import shutil
import datetime
import re
import ipaddress
import platform
import json
import pacparser  # Requires: pip install pacparser


PAC_LIST = "all_pac.csv"
BACKUP_DIR = "backup"
OLD_PAC_DIR = "old_PAC"
UPDATED_PAC_DIR = "updated_PAC"
MAX_BACKUPS = 10
TIMEOUT = 10
DNS_CONFIG_FILE = "dns_config.json"

def get_default_dns_config():
    """Return default DNS configuration if JSON file not found."""
    custom_mappings = {
        "apple.com": "10.0.1.1",
        "apple2.com": "10.0.1.2",
        "apple3.com": "10.0.1.3",
        "microsoft.com": "10.0.2.1",
        "google.com": "10.0.3.1",
    }
    
    pattern_mappings = [
        (r'\.zpp$', "10.0.1.1", r'\.zpp$'),
        (r'\.apple\.com$', "10.0.1.1", r'\.apple\.com$'),
        (r'(\.internal\.|intranet|local|corp)', "10.1.1.1", r'\.internal\.|intranet|local|corp'),
        (r'(\.cn|\.hk|asia)', "202.1.1.1", r'\.cn$|\.hk$|asia'),
        (r'(\.gov|\.mil)', "192.1.1.1", r'\.gov$|\.mil$'),
    ]
    
    default_ip = "8.8.8.8"
    
    return custom_mappings, pattern_mappings, default_ip


def create_default_dns_config_file(config_file=DNS_CONFIG_FILE):
    """Create a default dns_config.json file."""
    default_config = {
        "exact_mappings": {
            "apple.com": "10.0.1.1",
            "apple2.com": "10.0.1.2",
            "apple3.com": "10.0.1.3",
            "microsoft.com": "10.0.2.1",
            "google.com": "10.0.3.1"
        },
        "pattern_mappings": [
            {
                "python_pattern": "\\.zpp$",
                "js_pattern": "\\.zpp$",
                "ip": "10.0.1.1",
                "description": "Domains ending with .zpp"
            },
            {
                "python_pattern": "\\.apple\\.com$",
                "js_pattern": "\\.apple\\.com$",
                "ip": "10.0.1.1",
                "description": "Any subdomain of apple.com"
            },
            {
                "python_pattern": "(\\.internal\\.|intranet|local|corp)",
                "js_pattern": "\\.internal\\.|intranet|local|corp",
                "ip": "10.1.1.1",
                "description": "Internal corporate domains"
            },
            {
                "python_pattern": "(\\.cn|\\.hk|asia)",
                "js_pattern": "\\.cn$|\\.hk$|asia",
                "ip": "202.1.1.1",
                "description": "Asian domains"
            },
            {
                "python_pattern": "(\\.gov|\\.mil)",
                "js_pattern": "\\.gov$|\\.mil$",
                "ip": "192.1.1.1",
                "description": "Government domains"
            }
        ],
        "default_public_ip": "8.8.8.8"
    }
    
    try:
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        print(f"✓ Created default DNS config file: {config_file}")
        return True
    except Exception as e:
        print(f"⚠ Could not create {config_file}: {e}")
        return False

# DNS MAPPING CONFIGURATION
# Load from JSON file or use defaults


def load_dns_config(config_file=DNS_CONFIG_FILE):
    """Load DNS mappings from JSON configuration file."""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        custom_mappings = config.get("exact_mappings", {})
        pattern_mappings = [
            (item["python_pattern"], item["ip"], item["js_pattern"])
            for item in config.get("pattern_mappings", [])
        ]
        default_ip = config.get("default_public_ip", "8.8.8.8")
        
        print(f"✓ Loaded DNS config from {config_file}")
        print(f"  - {len(custom_mappings)} exact mappings")
        print(f"  - {len(pattern_mappings)} pattern mappings")
        
        return custom_mappings, pattern_mappings, default_ip
        
    except FileNotFoundError:
        print(f"⚠ DNS config file '{config_file}' not found.")
        
        # Ask user if they want to create the default file
        create_file = input(f"  Create default {config_file}? (y/n) [y]: ").strip().lower() or 'y'
        
        if create_file == 'y':
            if create_default_dns_config_file(config_file):
                print(f"  You can now edit {config_file} to customize DNS mappings.")
                # Load the newly created file
                return load_dns_config(config_file)
        
        print("  Using in-memory defaults.")
        return get_default_dns_config()
        
    except json.JSONDecodeError as e:
        print(f"⚠ Error parsing '{config_file}': {e}")
        print("  Using in-memory defaults.")
        return get_default_dns_config()



# Load DNS configuration at startup
CUSTOM_DNS_MAPPINGS, DNS_PATTERN_MAPPINGS, DEFAULT_PUBLIC_IP = load_dns_config()


def run(cmd):
    return subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )


def get_os_type():
    """Detect the operating system."""
    system = platform.system()
    if system == "Windows":
        return "windows"
    elif system in ["Linux", "Darwin"]:  # Darwin is macOS
        return "unix"
    else:
        return "unknown"


def download_file(url, output_path):
    """
    Download file using OS-appropriate built-in tools.
    Windows: PowerShell Invoke-WebRequest
    Unix/Linux: curl or wget
    """
    os_type = get_os_type()
    
    if os_type == "windows":
        # Use PowerShell on Windows
        cmd = [
            "powershell", "-Command",
            f"Invoke-WebRequest -Uri '{url}' -OutFile '{output_path}' -TimeoutSec {TIMEOUT}"
        ]
    else:
        # Try curl first, fall back to wget
        if shutil.which("curl"):
            cmd = ["curl", "-fsSL", "-m", str(TIMEOUT), url, "-o", output_path]
        elif shutil.which("wget"):
            cmd = ["wget", "-q", "-T", str(TIMEOUT), "-O", output_path, url]
        else:
            return False, "Neither curl nor wget available"
    
    r = run(cmd)
    return r.returncode == 0, r.stderr


def check_connectivity(proxy_decision, url):
    """
    Test connectivity based on PAC decision using OS built-in tools.
    Windows: Test-NetConnection (PowerShell) or telnet
    Unix/Linux: nc (netcat), telnet, or /dev/tcp
    """
    os_type = get_os_type()
    
    # Parse the URL to get host and port
    url_match = re.match(r'https?://([^:/]+)(?::(\d+))?', url)
    if not url_match:
        return "INVALID_URL"
    
    target_host = url_match.group(1)
    target_port = url_match.group(2) or ("443" if url.startswith("https") else "80")
    
    # Determine if we should use a proxy
    proxy_host = None
    proxy_port = None
    
    if "PROXY" in proxy_decision:
        proxy_match = re.search(r"PROXY\s+([a-zA-Z0-9.-]+):(\d+)", proxy_decision)
        if proxy_match:
            proxy_host = proxy_match.group(1)
            proxy_port = proxy_match.group(2)
        else:
            return "PARSE_ERROR"
    elif "DIRECT" in proxy_decision:
        # Direct connection
        pass
    else:
        return "UNSUPPORTED_TYPE"
    
    # Test connectivity to proxy if needed, otherwise to target
    test_host = proxy_host if proxy_host else target_host
    test_port = proxy_port if proxy_port else target_port
    
    # Perform connectivity test
    if os_type == "windows":
        return check_connectivity_windows(test_host, test_port)
    else:
        return check_connectivity_unix(test_host, test_port)


def check_connectivity_windows(host, port):
    """
    Test connectivity on Windows using Test-NetConnection (PowerShell).
    Falls back to basic socket test if Test-NetConnection not available.
    """
    # Try Test-NetConnection first (Windows PowerShell 4.0+)
    cmd = [
        "powershell", "-Command",
        f"$result = Test-NetConnection -ComputerName '{host}' -Port {port} -WarningAction SilentlyContinue -InformationLevel Quiet; if ($result) {{ exit 0 }} else {{ exit 1 }}"
    ]
    
    r = run(cmd)
    if r.returncode == 0:
        return "YES"
    
    # Fallback: Try using .NET Socket
    cmd_fallback = [
        "powershell", "-Command",
        f"try {{ $client = New-Object System.Net.Sockets.TcpClient('{host}', {port}); $client.Close(); exit 0 }} catch {{ exit 1 }}"
    ]
    
    r = run(cmd_fallback)
    return "YES" if r.returncode == 0 else "NO"


def check_connectivity_unix(host, port):
    """
    Test connectivity on Unix/Linux using available tools.
    Priority: nc (netcat) > /dev/tcp > telnet
    """
    # Try netcat first (most common)
    if shutil.which("nc"):
        # Use -z for port scan mode, -w for timeout
        cmd = ["nc", "-z", "-w", str(TIMEOUT), host, port]
        r = run(cmd)
        return "YES" if r.returncode == 0 else "NO"
    
    # Try /dev/tcp (bash built-in)
    cmd = [
        "bash", "-c",
        f"timeout {TIMEOUT} bash -c 'cat < /dev/null > /dev/tcp/{host}/{port}' 2>/dev/null"
    ]
    r = run(cmd)
    if r.returncode == 0:
        return "YES"
    
    # Try timeout with /dev/tcp without external timeout command
    cmd = [
        "bash", "-c",
        f"(echo > /dev/tcp/{host}/{port}) 2>/dev/null && echo 'success' || echo 'fail'"
    ]
    r = run(cmd)
    if "success" in r.stdout:
        return "YES"
    
    # Last resort: telnet (if available)
    if shutil.which("telnet"):
        cmd = ["bash", "-c", f"timeout {TIMEOUT} telnet {host} {port} 2>&1 | grep -q 'Connected'"]
        r = run(cmd)
        return "YES" if r.returncode == 0 else "NO"
    
    return "NO_TOOL_AVAILABLE"


def safe_write_file(output_file, write_function, max_retries=3):
    """
    Safely write to a file with permission error handling.
    
    Args:
        output_file: Target filename
        write_function: Function that takes filename and writes to it
        max_retries: Maximum retry attempts
    
    Returns:
        (success: bool, final_filename: str)
    """
    attempt = 0
    current_file = output_file
    
    while attempt < max_retries:
        try:
            write_function(current_file)
            return True, current_file
        except PermissionError:
            print(f"\n❌ Permission denied: Cannot write to '{current_file}'")
            print(f"   The file may be open in another application (Excel, editor, etc.)")
            
            choice = input("\n  Options:\n    1) Retry (close the file and press Enter)\n    2) Use different filename\n    3) Skip this operation\n  Select [1]: ").strip() or "1"
            
            if choice == "1":
                attempt += 1
                print(f"  Retrying... (attempt {attempt}/{max_retries})")
                continue
            elif choice == "2":
                new_name = input(f"  Enter new filename [{current_file}]: ").strip()
                if new_name:
                    current_file = new_name
                    attempt = 0  # Reset attempts for new filename
                continue
            else:
                print("  Operation skipped.")
                return False, current_file
        except Exception as e:
            print(f"\n❌ Error writing to '{current_file}': {e}")
            return False, current_file
    
    print(f"\n❌ Failed to write to '{current_file}' after {max_retries} attempts.")
    return False, current_file


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
    Includes domains from:
    - Quoted strings (general patterns)
    - dnsDomainIs() function calls
    - shExpMatch() with domain patterns
    
    If skip_subnets=True, filter out subnet patterns like 10.0.0.0
    """
    domains = set()
    try:
        with open(pac_file, "r", errors="ignore") as f:
            content = f.read()
        
        # Pattern 1: Match quoted domains like "apple.com" or 'www.apple.com'
        pattern_quoted = re.compile(r"""['"]([a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+)['"]""")
        
        # Pattern 2: Extract from dnsDomainIs(host, ".example.com") or dnsDomainIs(host, "example.com")
        pattern_dnsDomainIs = re.compile(r"""dnsDomainIs\s*\(\s*[^,]+,\s*['"]\.?([a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+)['"]\s*\)""", re.IGNORECASE)
        
        # Pattern 3: Extract from shExpMatch with domain patterns
        pattern_shExpMatch = re.compile(r"""shExpMatch\s*\([^,]+,\s*['"][*]?\.?([a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+)[*]?['"]\s*\)""", re.IGNORECASE)
        
        # Extract from general quoted strings
        for match in pattern_quoted.findall(content):
            domain = match.lower()
            if domain.startswith(".") or domain.startswith("*") or "*." in domain:
                continue
            if domain.count(".") >= 1:
                if skip_subnets and is_subnet_or_range(domain):
                    continue
                domains.add(domain)
        
        # Extract from dnsDomainIs() calls
        for match in pattern_dnsDomainIs.findall(content):
            domain = match.lower().lstrip('.')
            if domain and domain.count(".") >= 1:
                if skip_subnets and is_subnet_or_range(domain):
                    continue
                domains.add(domain)
        
        # Extract from shExpMatch() calls
        for match in pattern_shExpMatch.findall(content):
            domain = match.lower().lstrip('.')
            if domain and domain.count(".") >= 1:
                if skip_subnets and is_subnet_or_range(domain):
                    continue
                domains.add(domain)
                
    except Exception as e:
        print(f"Error reading PAC file {pac_file}: {e}")
        
    return sorted(domains)


def load_supplement_urls(suppress_print=False):
    """
    Load supplemental test URLs from supplement_test.csv.
    Creates an empty template if the file doesn't exist.
    Returns a list of URLs (may be empty).

    BUG FIX: Previously this logic was duplicated inside each generate_*
    function, meaning supplement URLs were silently skipped for any PAC
    whose local .pac file was missing (the `continue` statement jumped past
    the supplement URL append block).  Centralising it here makes the
    behaviour explicit and easier to audit.
    """
    SUPPLY_TEST_FILE = "supplement_test.csv"
    supplied_urls = []

    # Create empty template so the user knows the file exists
    if not os.path.exists(SUPPLY_TEST_FILE):
        print(f"  [+] Creating template {SUPPLY_TEST_FILE}...")
        try:
            with open(SUPPLY_TEST_FILE, "w", newline="") as sf:
                writer = csv.writer(sf)
                writer.writerow(["test_url"])
        except Exception as e:
            print(f"  ⚠ Failed to create {SUPPLY_TEST_FILE}: {e}")

    # Read URLs from the file (empty list if file only has the header)
    if os.path.exists(SUPPLY_TEST_FILE):
        try:
            with open(SUPPLY_TEST_FILE, encoding="utf-8-sig") as sf:
                s_reader = csv.DictReader(sf)
                for s_row in s_reader:
                    s_url = s_row.get("test_url", "").strip()
                    if s_url and s_url not in supplied_urls:
                        supplied_urls.append(s_url)
        except Exception as e:
            print(f"  ⚠ Failed to read {SUPPLY_TEST_FILE}: {e}")

    if not suppress_print:
        if supplied_urls:
            print(f"  [+] Loaded {len(supplied_urls)} supplemental test URL(s) from {SUPPLY_TEST_FILE}:")
            for u in supplied_urls:
                print(f"        • {u}")
        else:
            print(f"  [i] No supplemental URLs found in {SUPPLY_TEST_FILE}.")

    return supplied_urls


def generate_test_logic_csv_from_folder(pac_folder, output_file):
    """
    Generate test logic CSV from PAC files in specified folder.
    Includes ALL domains including subnets (can be tested for routing logic).

    BUG FIX 1: Supplement URLs are now loaded once before the PAC loop and
    appended for every PAC regardless of whether the local .pac file exists.
    Previously, a missing .pac file triggered `continue` which skipped the
    supplement URL append block entirely.

    BUG FIX 2: Supplement URLs that duplicate a domain already extracted
    from the PAC are deduplicated per-PAC to avoid redundant rows.
    """
    rows = []

    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False

    if not os.path.exists(PAC_LIST):
        print(f"Error: {PAC_LIST} not found.")
        return False

    print(f"\n[Step] Generating {output_file} from {pac_folder}/...")

    # ── Load supplement URLs ONCE, before the PAC loop ──────────────────
    supplied_urls = load_supplement_urls()
    # ────────────────────────────────────────────────────────────────────

    with open(PAC_LIST, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pac_name = row["pac_name"]
            pac_url  = row["pac_path"]
            pac_file = os.path.join(pac_folder, f"{pac_name}.pac")

            print(f"  Processing {pac_name}...")

            # ── Domain rows from PAC file ────────────────────────────────
            if os.path.exists(pac_file):
                # skip_subnets=False for logic testing
                domains = extract_domains_from_pac(pac_file, skip_subnets=False)
                for d in domains:
                    if re.match(r'^\d+\.\d+\.\d+\.\d+$', d):
                        rows.append([pac_name, pac_url, f"http://{d}"])
                    else:
                        rows.append([pac_name, pac_url, f"https://{d}"])
            else:
                # BUG FIX: warn but do NOT skip — supplement URLs must still
                # be added for this PAC so they appear in the test output.
                print(f"    ⚠ Warning: {pac_name}.pac not found in {pac_folder} "
                      f"— domain rows skipped, supplement URLs still added.")

            # ── Supplement rows (always appended, even if PAC missing) ───
            # BUG FIX: this block is now OUTSIDE any `continue` / `if`
            # that could prevent it from running.
            already_in_rows = {r[2] for r in rows if r[0] == pac_name}
            for s_url in supplied_urls:
                if s_url not in already_in_rows:
                    rows.append([pac_name, pac_url, s_url])
                    already_in_rows.add(s_url)
            # ────────────────────────────────────────────────────────────

    if not rows:
        print("  No testable domains found in PAC files or supplement_test.csv.")
        return False

    def write_csv(filename):
        with open(filename, "w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["pac_name", "pac_path", "test_url"])
            writer.writerows(rows)

    success, final_file = safe_write_file(output_file, write_csv)
    if success:
        # Count how many rows come from supplement URLs for transparency
        supp_count = sum(
            1 for r in rows if r[2] in supplied_urls
        )
        print(f"  ✓ {final_file} created ({len(rows)} test cases, "
              f"{supp_count} from supplement_test.csv)")
    return success


def generate_test_reachability_csv_from_folder(pac_folder, output_file):
    """
    Generate test reachability CSV from PAC files in specified folder.
    Excludes subnet patterns (10.0.0.0) that cannot be tested for connectivity.

    BUG FIX 1: Same fix as generate_test_logic_csv_from_folder — supplement
    URLs are loaded once and appended outside any conditional/continue path.

    BUG FIX 2: Supplement URLs deduplicated per-PAC.
    """
    rows = []

    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False

    if not os.path.exists(PAC_LIST):
        print(f"Error: {PAC_LIST} not found.")
        return False

    print(f"\n[Step] Generating {output_file} from {pac_folder}/...")

    # ── Load supplement URLs ONCE, before the PAC loop ──────────────────
    supplied_urls = load_supplement_urls()
    # ────────────────────────────────────────────────────────────────────

    with open(PAC_LIST, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pac_name = row["pac_name"]
            pac_url  = row["pac_path"]
            pac_file = os.path.join(pac_folder, f"{pac_name}.pac")

            print(f"  Processing {pac_name}...")

            # ── Domain rows from PAC file ────────────────────────────────
            if os.path.exists(pac_file):
                # skip_subnets=True for reachability testing
                domains = extract_domains_from_pac(pac_file, skip_subnets=True)
                for d in domains:
                    if re.match(r'^\d+\.\d+\.\d+\.\d+$', d):
                        rows.append([pac_name, pac_url, f"http://{d}"])
                    else:
                        rows.append([pac_name, pac_url, f"https://{d}"])
            else:
                print(f"    ⚠ Warning: {pac_name}.pac not found in {pac_folder} "
                      f"— domain rows skipped, supplement URLs still added.")

            # ── Supplement rows (always appended, even if PAC missing) ───
            already_in_rows = {r[2] for r in rows if r[0] == pac_name}
            for s_url in supplied_urls:
                if s_url not in already_in_rows:
                    rows.append([pac_name, pac_url, s_url])
                    already_in_rows.add(s_url)
            # ────────────────────────────────────────────────────────────

    if not rows:
        print("  No domains found in PAC files or supplement_test.csv.")
        return False

    def write_csv(filename):
        with open(filename, "w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["pac_name", "pac_path", "test_url"])
            writer.writerows(rows)

    success, final_file = safe_write_file(output_file, write_csv)
    if success:
        supp_count = sum(
            1 for r in rows if r[2] in supplied_urls
        )
        print(f"  ✓ {final_file} created ({len(rows)} test cases, "
              f"{supp_count} from supplement_test.csv)")
    return success


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
            success, error = download_file(pac_url, filepath)
            if not success:
                print(f"    FAILED to download {pac_url}: {error}")
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
            success, error = download_file(pac_url, filepath)
            if not success:
                print(f"    FAILED to download {pac_url}: {error}")
                continue

    print(f"  ✓ Download to {target_folder}/ completed")
    return True


def create_smart_dns_pac(original_pac_file, test_url):
    """
    Create a modified PAC file with context-aware DNS mocking.
    Returns IPs based on the URL being tested and configuration.
    Dynamically generates JavaScript patterns from Python configuration.
    """
    try:
        with open(original_pac_file, "r", errors="ignore") as f:
            content = f.read()
        
        # Extract host from test URL
        url_match = re.match(r'https?://([^:/]+)', test_url)
        test_host = url_match.group(1) if url_match else ""
        
        # Determine appropriate IP based on hostname (Python side)
        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', test_host):
            resolved_ip = test_host
        elif test_host.lower() in CUSTOM_DNS_MAPPINGS:
            resolved_ip = CUSTOM_DNS_MAPPINGS[test_host.lower()]
        else:
            # Check pattern mappings
            resolved_ip = DEFAULT_PUBLIC_IP
            for python_pattern, ip, _ in DNS_PATTERN_MAPPINGS:
                if re.search(python_pattern, test_host, re.IGNORECASE):
                    resolved_ip = ip
                    break
        
        # Build JavaScript object for custom mappings
        js_mappings = "{\n"
        for domain, ip in CUSTOM_DNS_MAPPINGS.items():
            js_mappings += f'        "{domain.lower()}": "{ip}",\n'
        js_mappings += "    }"
        
        # Build JavaScript pattern checks dynamically from DNS_PATTERN_MAPPINGS
        js_pattern_checks = ""
        for python_pattern, ip, js_pattern in DNS_PATTERN_MAPPINGS:
            js_pattern_checks += f"""    // Pattern: {python_pattern} -> {ip}
    if (hostLower.match(/{js_pattern}/i)) {{
        return "{ip}";
    }}
"""
        
        dns_mocks = f"""
// Context-aware DNS mocking for: {test_url}
var TEST_HOST = "{test_host}";
var RESOLVED_IP = "{resolved_ip}";

// Custom DNS mappings configuration (exact matches)
var CUSTOM_DNS_MAP = {js_mappings};

function dnsResolve(host) {{
    // Return actual IP if URL is an IP address
    if (/^\\d{{1,3}}\\.\\d{{1,3}}\\.\\d{{1,3}}\\.\\d{{1,3}}$/.test(host)) {{
        return host;
    }}
    
    var hostLower = host.toLowerCase();
    
    // Check custom mappings first (exact match)
    if (CUSTOM_DNS_MAP[hostLower]) {{
        return CUSTOM_DNS_MAP[hostLower];
    }}
    
    // For the specific test host, return the resolved IP
    if (hostLower === TEST_HOST.toLowerCase()) {{
        return RESOLVED_IP;
    }}
    
    // Dynamically generated pattern checks from dns_config.json
{js_pattern_checks}
    
    // Default to public IP
    return "{DEFAULT_PUBLIC_IP}";
}}

function dnsResolveEx(host) {{
    return dnsResolve(host);
}}

function isResolvable(host) {{
    return true;
}}

function isResolvableEx(host) {{
    return true;
}}

function myIpAddress() {{
    return "192.168.1.100";
}}

function myIpAddressEx() {{
    return "192.168.1.100";
}}

// Original PAC file content follows:
"""
        
        modified_content = dns_mocks + content
        
        temp_pac = tempfile.NamedTemporaryFile(mode='w', suffix='.pac', delete=False)
        temp_pac.write(modified_content)
        temp_pac.close()
        
        return temp_pac.name
    except Exception as e:
        print(f"Error creating smart DNS PAC file: {e}")
        return None


def evaluate_pac(pac_file, url, skip_dns=True):
    """
    Uses pacparser to evaluate the PAC file logic.
    If skip_dns=True, creates a modified PAC file with smart DNS mocking.
    """
    actual_pac_file = pac_file
    
    try:
        if skip_dns:
            actual_pac_file = create_smart_dns_pac(pac_file, url)
            if not actual_pac_file:
                return "ERROR: Failed to create smart DNS PAC"
        
        pacparser.init()
        pacparser.parse_pac_file(actual_pac_file)
        proxy_string = pacparser.find_proxy(url)
        pacparser.cleanup()
        
        if skip_dns and actual_pac_file != pac_file:
            os.unlink(actual_pac_file)
        
        return proxy_string
    except Exception as e:
        if skip_dns and actual_pac_file and actual_pac_file != pac_file and os.path.exists(actual_pac_file):
            os.unlink(actual_pac_file)
        return f"ERROR: {str(e)}"


def run_logic_test(test_csv, pac_folder, output_file, skip_dns=True):
    """
    Test PAC logic only (no connectivity test).
    Set skip_dns=True to avoid slow DNS lookups.
    """
    if not os.path.exists(test_csv):
        print(f"Error: {test_csv} not found.")
        return False

    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False

    mode_desc = "without DNS lookups" if skip_dns else "with DNS lookups"
    print(f"\n[Step] Running logic test from {pac_folder}/ ({mode_desc})...")
    
    # Collect all results first
    results = []
    with open(test_csv, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pac_name = row["pac_name"]
            test_url = row["test_url"]

            pac_file = os.path.join(pac_folder, f"{pac_name}.pac")
            
            if not os.path.exists(pac_file):
                results.append([pac_name, test_url, "PAC_FILE_NOT_FOUND"])
                continue

            decision = evaluate_pac(pac_file, test_url, skip_dns=skip_dns)
            results.append([pac_name, test_url, decision])
            print(f"  {pac_name}: {test_url} -> {decision}")

    # Write results with permission handling
    def write_csv(filename):
        with open(filename, "w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["pac_name", "test_url", "pac_decision"])
            writer.writerows(results)

    success, final_file = safe_write_file(output_file, write_csv)
    if success:
        print(f"  ✓ Logic test completed → {final_file}")
    return success


def run_reachability_test_from_folder(pac_folder, test_csv, output_file):
    """Test actual connectivity using PAC files from local folder."""
    
    if not os.path.exists(test_csv):
        print(f"Error: {test_csv} not found.")
        return False

    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False

    os_type = get_os_type()
    print(f"\n[Step] Running reachability test from {pac_folder}/ (OS: {os_type})...")
    
    # Collect all results first
    results = []
    with open(test_csv, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pac_path = row["pac_path"]
            pac_name = row["pac_name"]
            test_url = row["test_url"]

            pac_file = os.path.join(pac_folder, f"{pac_name}.pac")
            
            if not os.path.exists(pac_file):
                results.append([pac_name, pac_path, test_url, "PAC_FILE_NOT_FOUND", "NO"])
                continue

            decision = evaluate_pac(pac_file, test_url, skip_dns=True)
            reachable = check_connectivity(decision, test_url)

            results.append([pac_name, pac_path, test_url, decision, reachable])
            print(f"  {pac_name}: {test_url} -> {decision} [{reachable}]")

    # Write results with permission handling
    def write_csv(filename):
        with open(filename, "w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["pac_name", "pac_path", "test_url", "pac_decision", "reachable"])
            writer.writerows(results)

    success, final_file = safe_write_file(output_file, write_csv)
    if success:
        print(f"  ✓ Reachability test completed → {final_file}")
    return success


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
    removed_count = 0
    no_change_count = 0
    changed_rows = []
    all_rows = []
    
    # Track URLs in after for removed detection
    after_keys = set()
    
    with open(after) as f:
        for r in csv.DictReader(f):
            key = (r["pac_name"], r["test_url"])
            after_keys.add(key)
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
            
            all_rows.append(row_data)
            
            if change != "NO_CHANGE":
                changed_rows.append(row_data)
    
    # Check for removed entries
    for key, b in before_map.items():
        if key not in after_keys:
            row_data = [
                b["pac_name"], b["test_url"],
                b["pac_decision"],
                "N/A",
                "REMOVED"
            ]
            all_rows.append(row_data)
            changed_rows.append(row_data)
            removed_count += 1

    # Write full report with permission handling
    def write_full(filename):
        with open(filename, "w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["pac_name", "test_url", "before_decision", "after_decision", "change"])
            writer.writerows(all_rows)

    success_full, final_full = safe_write_file(output_full, write_full)
    
    # Write summary report with permission handling
    def write_summary(filename):
        with open(filename, "w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["pac_name", "test_url", "before_decision", "after_decision", "change"])
            writer.writerows(changed_rows)

    success_summary, final_summary = safe_write_file(output_summary, write_summary)
    
    if success_full and success_summary:
        print(f"  ✓ Full comparison → {final_full}")
        print(f"  ✓ Summary (changes only) → {final_summary}")
        print(f"\n  Statistics:")
        print(f"    • Total test cases: {len(all_rows)}")
        print(f"    • Changed: {changes_count - new_count}")
        print(f"    • New entries: {new_count}")
        print(f"    • Removed entries: {removed_count}")
        print(f"    • No change: {no_change_count}")
        return True
    return False


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
    removed_count = 0
    no_change_count = 0
    changed_rows = []
    all_rows = []
    
    # Track URLs in after for removed detection
    after_keys = set()
    
    with open(after) as f:
        for r in csv.DictReader(f):
            key = (r["pac_name"], r["test_url"])
            after_keys.add(key)
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
            
            all_rows.append(row_data)
            
            if change != "NO_CHANGE":
                changed_rows.append(row_data)
    
    # Check for removed entries
    for key, b in before_map.items():
        if key not in after_keys:
            row_data = [
                b["pac_name"], b["test_url"],
                b["pac_decision"],
                "N/A",
                b["reachable"],
                "N/A",
                "REMOVED"
            ]
            all_rows.append(row_data)
            changed_rows.append(row_data)
            removed_count += 1

    # Write full report with permission handling
    def write_full(filename):
        with open(filename, "w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["pac_name", "test_url", "before_decision", "after_decision", 
                           "before_reachable", "after_reachable", "change"])
            writer.writerows(all_rows)

    success_full, final_full = safe_write_file(output_full, write_full)
    
    # Write summary report with permission handling
    def write_summary(filename):
        with open(filename, "w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["pac_name", "test_url", "before_decision", "after_decision",
                           "before_reachable", "after_reachable", "change"])
            writer.writerows(changed_rows)

    success_summary, final_summary = safe_write_file(output_summary, write_summary)
    
    if success_full and success_summary:
        print(f"  ✓ Full comparison → {final_full}")
        print(f"  ✓ Summary (changes only) → {final_summary}")
        print(f"\n  Statistics:")
        print(f"    • Total test cases: {len(all_rows)}")
        print(f"    • Changed: {changes_count - new_count}")
        print(f"    • New entries: {new_count}")
        print(f"    • Removed entries: {removed_count}")
        print(f"    • No change: {no_change_count}")
        return True
    return False


# ---------- WORKFLOW FUNCTIONS ----------
def workflow_setup_baseline():
    """
    Workflow 1: Setup baseline testing environment (FULL - with reachability)
    """
    print("\n" + "="*60)
    print("  WORKFLOW 1: Setup Baseline (Full Testing)")
    print("="*60)
    
    if not download_pac_files_to_folder(OLD_PAC_DIR):
        print("\n❌ Workflow failed at download step")
        return
    
    if not generate_test_logic_csv_from_folder(OLD_PAC_DIR, "old_test_logic.csv"):
        print("\n❌ Workflow failed at test_logic.csv generation")
        return
    
    if not generate_test_reachability_csv_from_folder(OLD_PAC_DIR, "old_test_reachability.csv"):
        print("\n❌ Workflow failed at test_reachability.csv generation")
        return
    
    if not run_logic_test("old_test_logic.csv", OLD_PAC_DIR, "before_logic_result.csv", skip_dns=True):
        print("\n❌ Workflow failed at BEFORE logic test")
        return
    
    if not run_reachability_test_from_folder(OLD_PAC_DIR, "old_test_reachability.csv", "before_reachability_result.csv"):
        print("\n❌ Workflow failed at BEFORE reachability test")
        return
    
    print("\n" + "="*60)
    print("  ✓ BASELINE SETUP COMPLETE (FULL)")
    print("="*60)
    print("\n  Files created:")
    print("    - old_PAC/                        (original PAC files)")
    print("    - old_test_logic.csv              (logic test cases - includes subnets)")
    print("    - old_test_reachability.csv       (reachability test cases - excludes subnets)")
    print("    - before_logic_result.csv         (baseline logic results)")
    print("    - before_reachability_result.csv  (baseline reachability results)")
    print("\n  Next step: Make your PAC file changes, then run Workflow 2")
    print("="*60 + "\n")


def workflow_test_and_compare():
    """
    Workflow 2: Test updated PAC files and compare (FULL - with reachability)
    """
    print("\n" + "="*60)
    print("  WORKFLOW 2: Test Updated PAC Files & Compare (Full)")
    print("="*60)
    
    if not os.path.exists("before_logic_result.csv"):
        print("\n❌ Baseline logic results not found!")
        print("  Please run Workflow 1 (Setup Baseline) first.")
        return
    
    if not os.path.exists("before_reachability_result.csv"):
        print("\n❌ Baseline reachability results not found!")
        print("  Please run Workflow 1 (Setup Baseline) first.")
        return
    
    if not download_pac_files_to_folder(UPDATED_PAC_DIR):
        print("\n❌ Workflow failed at download step")
        return
    
    if not generate_test_logic_csv_from_folder(UPDATED_PAC_DIR, "updated_test_logic.csv"):
        print("\n❌ Workflow failed at test_logic.csv generation")
        return
    
    if not generate_test_reachability_csv_from_folder(UPDATED_PAC_DIR, "updated_test_reachability.csv"):
        print("\n❌ Workflow failed at test_reachability.csv generation")
        return
    
    if not run_logic_test("updated_test_logic.csv", UPDATED_PAC_DIR, "after_logic_result.csv", skip_dns=True):
        print("\n❌ Workflow failed at AFTER logic test")
        return
    
    if not run_reachability_test_from_folder(UPDATED_PAC_DIR, "updated_test_reachability.csv", "after_reachability_result.csv"):
        print("\n❌ Workflow failed at AFTER reachability test")
        return
    
    if not compare_logic_results(
        "before_logic_result.csv",
        "after_logic_result.csv",
        "pac_logic_comparison_full.csv",
        "pac_logic_comparison_summary.csv"
    ):
        print("\n❌ Workflow failed at logic comparison step")
        return
    
    if not compare_reachability_results(
        "before_reachability_result.csv",
        "after_reachability_result.csv",
        "pac_reachability_comparison_full.csv",
        "pac_reachability_comparison_summary.csv"
    ):
        print("\n❌ Workflow failed at reachability comparison step")
        return
    
    print("\n" + "="*60)
    print("  ✓ TESTING & COMPARISON COMPLETE (FULL)")
    print("="*60)
    print("\n  Files created:")
    print("    - updated_PAC/                              (updated PAC files)")
    print("    - updated_test_logic.csv                    (logic test cases - includes subnets)")
    print("    - updated_test_reachability.csv             (reachability test cases - excludes subnets)")
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


def workflow_setup_baseline_logic_only():
    """
    Workflow 3: Setup baseline testing environment (LOGIC ONLY - faster)
    """
    print("\n" + "="*60)
    print("  WORKFLOW 3: Setup Baseline (Logic Testing Only)")
    print("="*60)
    
    if not download_pac_files_to_folder(OLD_PAC_DIR):
        print("\n❌ Workflow failed at download step")
        return
    
    if not generate_test_logic_csv_from_folder(OLD_PAC_DIR, "old_test_logic.csv"):
        print("\n❌ Workflow failed at test_logic.csv generation")
        return
    
    if not run_logic_test("old_test_logic.csv", OLD_PAC_DIR, "before_logic_result.csv", skip_dns=True):
        print("\n❌ Workflow failed at BEFORE logic test")
        return
    
    print("\n" + "="*60)
    print("  ✓ BASELINE SETUP COMPLETE (LOGIC ONLY)")
    print("="*60)
    print("\n  Files created:")
    print("    - old_PAC/                 (original PAC files)")
    print("    - old_test_logic.csv       (logic test cases - includes subnets)")
    print("    - before_logic_result.csv  (baseline logic results)")
    print("\n  Next step: Make your PAC file changes, then run Workflow 4")
    print("  Note: Reachability tests skipped for faster execution")
    print("="*60 + "\n")


def workflow_test_and_compare_logic_only():
    """
    Workflow 4: Test updated PAC files and compare (LOGIC ONLY - faster)
    """
    print("\n" + "="*60)
    print("  WORKFLOW 4: Test Updated PAC Files & Compare (Logic Only)")
    print("="*60)
    
    if not os.path.exists("before_logic_result.csv"):
        print("\n❌ Baseline logic results not found!")
        print("  Please run Workflow 3 (Setup Baseline - Logic Only) first.")
        return
    
    if not download_pac_files_to_folder(UPDATED_PAC_DIR):
        print("\n❌ Workflow failed at download step")
        return
    
    if not generate_test_logic_csv_from_folder(UPDATED_PAC_DIR, "updated_test_logic.csv"):
        print("\n❌ Workflow failed at test_logic.csv generation")
        return
    
    if not run_logic_test("updated_test_logic.csv", UPDATED_PAC_DIR, "after_logic_result.csv", skip_dns=True):
        print("\n❌ Workflow failed at AFTER logic test")
        return
    
    if not compare_logic_results(
        "before_logic_result.csv",
        "after_logic_result.csv",
        "pac_logic_comparison_full.csv",
        "pac_logic_comparison_summary.csv"
    ):
        print("\n❌ Workflow failed at logic comparison step")
        return
    
    print("\n" + "="*60)
    print("  ✓ TESTING & COMPARISON COMPLETE (LOGIC ONLY)")
    print("="*60)
    print("\n  Files created:")
    print("    - updated_PAC/                          (updated PAC files)")
    print("    - updated_test_logic.csv                (logic test cases - includes subnets)")
    print("    - after_logic_result.csv                (updated logic results)")
    print("\n  Comparison Reports:")
    print("    • pac_logic_comparison_full.csv         (all test cases)")
    print("    • pac_logic_comparison_summary.csv      (changes only)")
    print("\n  ⚡ Fast execution: Reachability tests skipped")
    print("  📊 Review summary report for routing logic changes")
    print("="*60 + "\n")


# ---------- MENU ----------
def menu():
    while True:
        print("""
╔═══════════════════════════════════════════════════════════╗
║            PAC File Testing & Validation Tool             ║
║              (with JSON DNS Configuration)                ║
╚═══════════════════════════════════════════════════════════╝

┌─ WORKFLOWS (Recommended) ──────────────────────────────────┐
│                                                             │
│  1) Setup Baseline (Full: Logic + Reachability)            │
│  2) Test Updated PAC & Compare (Full)                      │
│  3) Setup Baseline (Logic Only - Fast)                     │
│  4) Test Updated PAC & Compare (Logic Only - Fast)         │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─ INDIVIDUAL OPERATIONS ────────────────────────────────────┐
│                                                             │
│  5) Backup current PAC files (to backup/)                  │
│  6) Generate test_logic.csv from old_PAC/                  │
│  7) Generate test_logic.csv from updated_PAC/              │
│  8) Generate test_reachability.csv from old_PAC/           │
│  9) Generate test_reachability.csv from updated_PAC/       │
│ 10) Run logic test on old_PAC/                             │
│ 11) Run logic test on updated_PAC/                         │
│ 12) Run reachability test on old_PAC/                      │
│ 13) Run reachability test on updated_PAC/                  │
│ 14) Reload DNS configuration from dns_config.json          │
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
            workflow_setup_baseline_logic_only()
        elif choice == "4":
            workflow_test_and_compare_logic_only()
        elif choice == "5":
            backup_pac_files()
        elif choice == "6":
            generate_test_logic_csv_from_folder(OLD_PAC_DIR, "old_test_logic.csv")
        elif choice == "7":
            generate_test_logic_csv_from_folder(UPDATED_PAC_DIR, "updated_test_logic.csv")
        elif choice == "8":
            generate_test_reachability_csv_from_folder(OLD_PAC_DIR, "old_test_reachability.csv")
        elif choice == "9":
            generate_test_reachability_csv_from_folder(UPDATED_PAC_DIR, "updated_test_reachability.csv")
        elif choice == "10":
            if not os.path.exists("old_test_logic.csv"):
                print("\n❌ old_test_logic.csv not found. Generate it first (option 6).")
            else:
                run_logic_test("old_test_logic.csv", OLD_PAC_DIR, "manual_old_logic_result.csv", skip_dns=True)
        elif choice == "11":
            if not os.path.exists("updated_test_logic.csv"):
                print("\n❌ updated_test_logic.csv not found. Generate it first (option 7).")
            else:
                success = run_logic_test("updated_test_logic.csv", UPDATED_PAC_DIR, "manual_updated_logic_result.csv", skip_dns=True)
                if success:
                    before_file = "manual_old_logic_result.csv"
                    if not os.path.exists(before_file) and os.path.exists("before_logic_result.csv"):
                        before_file = "before_logic_result.csv"
                        
                    if os.path.exists(before_file):
                        compare_logic_results(
                            before_file,
                            "manual_updated_logic_result.csv",
                            "manual_logic_comparison_full.csv",
                            "manual_logic_comparison_summary.csv"
                        )
                    else:
                        print("\nℹ️ Could not find 'manual_old_logic_result.csv' to compare against.")
                        print("  Run Option 10 first to generate the comparison files.")
        elif choice == "12":
            if not os.path.exists("old_test_reachability.csv"):
                print("\n❌ old_test_reachability.csv not found. Generate it first (option 8).")
            else:
                run_reachability_test_from_folder(OLD_PAC_DIR, "old_test_reachability.csv", "manual_old_reachability_result.csv")
        elif choice == "13":
            if not os.path.exists("updated_test_reachability.csv"):
                print("\n❌ updated_test_reachability.csv not found. Generate it first (option 9).")
            else:
                run_reachability_test_from_folder(UPDATED_PAC_DIR, "updated_test_reachability.csv", "manual_updated_reachability_result.csv")
        elif choice == "14":
            global CUSTOM_DNS_MAPPINGS, DNS_PATTERN_MAPPINGS, DEFAULT_PUBLIC_IP
            CUSTOM_DNS_MAPPINGS, DNS_PATTERN_MAPPINGS, DEFAULT_PUBLIC_IP = load_dns_config()
            print("\n✓ DNS configuration reloaded\n")
        elif choice == "0":
            print("\nExiting...\n")
            break
        else:
            print("\n❌ Invalid selection\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  PAC File Testing & Validation Tool")
    print("="*60)
    menu()