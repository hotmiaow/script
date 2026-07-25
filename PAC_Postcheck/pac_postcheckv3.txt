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
try:
    import pacparser  # Requires: pip install pacparser
except ImportError:
    pacparser = None
    print("⚠ Warning: 'pacparser' module not found. Logic testing features will fail.")
    print("  To install: pip install pacparser (Requires C compiler and javascript/pacparser headers)")

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    requests = None
    print("⚠ Warning: 'requests' module not found. Header testing features will fail.")
    print("  To install: pip install requests")

PAC_LIST = "all_pac.csv"
BACKUP_DIR = "backup"
OLD_PAC_DIR = "old_PAC"
UPDATED_PAC_DIR = "updated_PAC"
MAX_BACKUPS = 10
TIMEOUT = 10
DNS_CONFIG_FILE = "dns_config.json"
HEADER_TEST_URLS_CSV = "supplement_test.csv"

def extract_html_title(resp):
    """
    Extract the <title> tag from the response.
    To avoid downloading large files, we only read a small chunk of the body.
    """
    try:
        # Check content type if available to ensure it's HTML
        content_type = resp.headers.get('Content-Type', '').lower()
        if 'html' not in content_type and content_type != '':
            if any(t in content_type for t in ['image/', 'application/json', 'application/pdf', 'application/javascript', 'text/css']):
                return "N/A (Non-HTML)"
        
        # Read the first chunk (up to 50KB) of the response content
        chunks = []
        bytes_read = 0
        max_bytes = 50 * 1024  # 50 KB
        
        for chunk in resp.iter_content(chunk_size=4096):
            if not chunk:
                break
            chunks.append(chunk)
            bytes_read += len(chunk)
            if bytes_read >= max_bytes:
                break
                
        if not chunks:
            return "No Content"
            
        # Decode the content
        html_bytes = b"".join(chunks)
        try:
            html_text = html_bytes.decode('utf-8', errors='replace')
        except Exception:
            html_text = html_bytes.decode('latin-1', errors='replace')
            
        # Extract title using regex
        match = re.search(r'<title[^>]*>(.*?)</title>', html_text, re.IGNORECASE | re.DOTALL)
        if match:
            title = match.group(1).strip()
            title = re.sub(r'\s+', ' ', title)
            return title
        return "No Title"
    except Exception as e:
        return f"Error: {type(e).__name__}"


def save_markdown_table(filepath, headers, rows):
    """Save table data to a markdown file."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            title = os.path.basename(filepath).replace(".md", "").replace("_", " ").title()
            f.write(f"# {title}\n\n")
            
            f.write("| " + " | ".join(headers) + " |\n")
            f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
            for row in rows:
                escaped_row = [str(cell).replace("|", "\\|") for cell in row]
                f.write("| " + " | ".join(escaped_row) + " |\n")
        return True
    except Exception as e:
        print(f"  ⚠ Failed to write markdown table to {filepath}: {e}")
        return False


def write_csv_and_md(csv_path, headers, rows):
    """
    Writes both CSV and Markdown table versions of the data.
    Uses safe_write_file to write the CSV, then writes the MD file.
    """
    def write_csv(filename):
        with open(filename, "w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out)
            writer.writerow(headers)
            writer.writerows(rows)
            
    success, final_csv = safe_write_file(csv_path, write_csv)
    if success:
        md_path = csv_path.replace(".csv", ".md")
        save_markdown_table(md_path, headers, rows)
    return success


def get_run_folder():
    """Create a unique timestamped folder for the current run under test_result/."""
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H%M")
    run_dir = os.path.join("test_result", timestamp)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def find_latest_baseline_file(filename):
    """
    Search in test_result/ for the latest subfolder (by timestamp)
    that contains the specified baseline file.
    Also falls back to the current directory if it exists there.
    """
    if os.path.exists(filename):
        return filename
        
    if not os.path.exists("test_result"):
        return None
        
    subfolders = []
    for d in os.listdir("test_result"):
        full_path = os.path.join("test_result", d)
        if os.path.isdir(full_path):
            subfolders.append(d)
            
    subfolders.sort(reverse=True)
    
    for folder in subfolders:
        target_path = os.path.join("test_result", folder, filename)
        if os.path.exists(target_path):
            return target_path
            
    return None


def find_latest_directory(dir_name):
    """
    Search in test_result/ for the latest subfolder (by timestamp)
    that contains the specified directory name.
    Also falls back to the current directory if it exists there.
    """
    if os.path.exists(dir_name) and os.path.isdir(dir_name):
        return dir_name
        
    if not os.path.exists("test_result"):
        return dir_name
        
    subfolders = []
    for d in os.listdir("test_result"):
        full_path = os.path.join("test_result", d)
        if os.path.isdir(full_path):
            subfolders.append(d)
            
    subfolders.sort(reverse=True)
    
    for folder in subfolders:
        target_path = os.path.join("test_result", folder, dir_name)
        if os.path.exists(target_path) and os.path.isdir(target_path):
            return target_path
            
    return dir_name


def ask_region_selection(pac_list_path=PAC_LIST):
    """
    Prompt the user to select which region they want to test.
    Returns:
        - list of pac rows (dicts) matching the selected region, or
        - list of all pac rows if 'all' is selected.
        - None if cancelled or error.
    """
    if not os.path.exists(pac_list_path):
        print(f"Error: {pac_list_path} not found.")
        return None
        
    all_rows = []
    regions = set()
    try:
        with open(pac_list_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                all_rows.append(row)
                reg = (row.get("region") or "").strip().lower()
                if reg:
                    regions.add(reg)
    except Exception as e:
        print(f"❌ Error reading {pac_list_path}: {e}")
        return None
        
    sorted_regions = sorted(list(regions))
    
    print("\n🌐 Region Selection:")
    print("  0) All Regions")
    for idx, r in enumerate(sorted_regions, start=1):
        print(f"  {idx}) {r.upper()}")
    print("  q) Cancel/Back")
    
    while True:
        choice = input("\nSelect region to test [0]: ").strip().lower() or "0"
        if choice == "0" or choice == "all":
            print("  -> Testing ALL regions.")
            return all_rows
        elif choice == "q":
            return None
        else:
            try:
                val = int(choice)
                if 1 <= val <= len(sorted_regions):
                    selected_region = sorted_regions[val - 1]
                    filtered_rows = [
                        row for row in all_rows
                        if (row.get("region") or "").strip().lower() == selected_region
                    ]
                    print(f"  -> Selected region: {selected_region.upper()} ({len(filtered_rows)} PAC files)")
                    return filtered_rows
            except ValueError:
                if choice in sorted_regions:
                    selected_region = choice
                    filtered_rows = [
                        row for row in all_rows
                        if (row.get("region") or "").strip().lower() == selected_region
                    ]
                    print(f"  -> Selected region: {selected_region.upper()} ({len(filtered_rows)} PAC files)")
                    return filtered_rows
                    
        print("❌ Invalid selection. Please try again.")


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
                    s_url = (s_row.get("test_url") or s_row.get("url") or "").strip()
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


def generate_test_logic_csv_from_folder(pac_folder, output_file, pac_rows=None):
    """
    Generate test logic CSV from PAC files in specified folder.
    Includes ALL domains including subnets (can be tested for routing logic).
    """
    rows = []

    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False

    if pac_rows is None:
        if not os.path.exists(PAC_LIST):
            print(f"Error: {PAC_LIST} not found.")
            return False
        try:
            with open(PAC_LIST, encoding="utf-8-sig") as f:
                pac_rows = list(csv.DictReader(f))
        except Exception as e:
            print(f"Error reading {PAC_LIST}: {e}")
            return False

    print(f"\n[Step] Generating {output_file} from {pac_folder}/...")

    supplied_urls = load_supplement_urls()

    for row in pac_rows:
        pac_name = row["pac_name"]
        pac_url  = row["pac_path"]
        pac_file = os.path.join(pac_folder, f"{pac_name}.pac")

        print(f"  Processing {pac_name}...")

        if os.path.exists(pac_file):
            domains = extract_domains_from_pac(pac_file, skip_subnets=False)
            for d in domains:
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', d):
                    rows.append([pac_name, pac_url, f"http://{d}"])
                else:
                    rows.append([pac_name, pac_url, f"https://{d}"])
        else:
            print(f"    ⚠ Warning: {pac_name}.pac not found in {pac_folder} "
                  f"— domain rows skipped, supplement URLs still added.")

        already_in_rows = {r[2] for r in rows if r[0] == pac_name}
        for s_url in supplied_urls:
            if s_url not in already_in_rows:
                rows.append([pac_name, pac_url, s_url])
                already_in_rows.add(s_url)

    if not rows:
        print("  No testable domains found in PAC files or supplement_test.csv.")
        return False

    headers = ["pac_name", "pac_path", "test_url"]
    success = write_csv_and_md(output_file, headers, rows)
    if success:
        supp_count = sum(1 for r in rows if r[2] in supplied_urls)
        print(f"  ✓ {output_file} created ({len(rows)} test cases, "
              f"{supp_count} from supplement_test.csv)")
    return success


def generate_test_reachability_csv_from_folder(pac_folder, output_file, pac_rows=None):
    """
    Generate test reachability CSV from PAC files in specified folder.
    Excludes subnet patterns (10.0.0.0) that cannot be tested for connectivity.
    """
    rows = []

    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False

    if pac_rows is None:
        if not os.path.exists(PAC_LIST):
            print(f"Error: {PAC_LIST} not found.")
            return False
        try:
            with open(PAC_LIST, encoding="utf-8-sig") as f:
                pac_rows = list(csv.DictReader(f))
        except Exception as e:
            print(f"Error reading {PAC_LIST}: {e}")
            return False

    print(f"\n[Step] Generating {output_file} from {pac_folder}/...")

    supplied_urls = load_supplement_urls()

    for row in pac_rows:
        pac_name = row["pac_name"]
        pac_url  = row["pac_path"]
        pac_file = os.path.join(pac_folder, f"{pac_name}.pac")

        print(f"  Processing {pac_name}...")

        if os.path.exists(pac_file):
            domains = extract_domains_from_pac(pac_file, skip_subnets=True)
            for d in domains:
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', d):
                    rows.append([pac_name, pac_url, f"http://{d}"])
                else:
                    rows.append([pac_name, pac_url, f"https://{d}"])
        else:
            print(f"    ⚠ Warning: {pac_name}.pac not found in {pac_folder} "
                  f"— domain rows skipped, supplement URLs still added.")

        already_in_rows = {r[2] for r in rows if r[0] == pac_name}
        for s_url in supplied_urls:
            if s_url not in already_in_rows:
                rows.append([pac_name, pac_url, s_url])
                already_in_rows.add(s_url)

    if not rows:
        print("  No domains found in PAC files or supplement_test.csv.")
        return False

    headers = ["pac_name", "pac_path", "test_url"]
    success = write_csv_and_md(output_file, headers, rows)
    if success:
        supp_count = sum(1 for r in rows if r[2] in supplied_urls)
        print(f"  ✓ {output_file} created ({len(rows)} test cases, "
              f"{supp_count} from supplement_test.csv)")
    return success
def backup_pac_files(pac_rows=None):
    """Backup current PAC files with timestamp."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if pac_rows is None:
        if not os.path.exists(PAC_LIST):
            print(f"Error: {PAC_LIST} not found.")
            return False
        try:
            with open(PAC_LIST, encoding="utf-8-sig") as f:
                pac_rows = list(csv.DictReader(f))
        except Exception as e:
            print(f"Error reading {PAC_LIST}: {e}")
            return False

    print("\n[Step] Backing up PAC files...")
    for row in pac_rows:
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


def download_pac_files_to_folder(target_folder, pac_rows=None):
    """Download PAC files from all_pac.csv into the specified folder."""
    os.makedirs(target_folder, exist_ok=True)
    
    if pac_rows is None:
        if not os.path.exists(PAC_LIST):
            print(f"Error: {PAC_LIST} not found.")
            return False
        try:
            with open(PAC_LIST, encoding="utf-8-sig") as f:
                pac_rows = list(csv.DictReader(f))
        except Exception as e:
            print(f"Error reading {PAC_LIST}: {e}")
            return False

    print(f"\n[Step] Downloading PAC files to {target_folder}/...")
    for row in pac_rows:
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
    if pacparser is None:
        return "ERROR: pacparser module not installed"
        
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


def run_logic_test(test_csv, pac_folder, output_file, skip_dns=True, pac_rows=None):
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
    
    valid_pacs = {row["pac_name"] for row in pac_rows} if pac_rows else None
    
    # Collect all results first
    results = []
    with open(test_csv, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pac_name = row["pac_name"]
            if valid_pacs and pac_name not in valid_pacs:
                continue
            test_url = row["test_url"]

            pac_file = os.path.join(pac_folder, f"{pac_name}.pac")
            
            if not os.path.exists(pac_file):
                results.append([pac_name, test_url, "PAC_FILE_NOT_FOUND"])
                continue

            decision = evaluate_pac(pac_file, test_url, skip_dns=skip_dns)
            results.append([pac_name, test_url, decision])
            print(f"  {pac_name}: {test_url} -> {decision}")

    headers = ["pac_name", "test_url", "pac_decision"]
    success = write_csv_and_md(output_file, headers, results)
    if success:
        print(f"  ✓ Logic test completed → {output_file} (and markdown)")
    return success


def run_reachability_test_from_folder(pac_folder, test_csv, output_file, pac_rows=None):
    """Test actual connectivity using PAC files from local folder."""
    
    if not os.path.exists(test_csv):
        print(f"Error: {test_csv} not found.")
        return False

    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False

    os_type = get_os_type()
    print(f"\n[Step] Running reachability test from {pac_folder}/ (OS: {os_type})...")
    
    valid_pacs = {row["pac_name"] for row in pac_rows} if pac_rows else None
    
    # Collect all results first
    results = []
    with open(test_csv, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pac_name = row["pac_name"]
            if valid_pacs and pac_name not in valid_pacs:
                continue
            pac_path = row["pac_path"]
            test_url = row["test_url"]

            pac_file = os.path.join(pac_folder, f"{pac_name}.pac")
            
            if not os.path.exists(pac_file):
                results.append([pac_name, pac_path, test_url, "PAC_FILE_NOT_FOUND", "NO"])
                continue

            decision = evaluate_pac(pac_file, test_url, skip_dns=True)
            reachable = check_connectivity(decision, test_url)

            results.append([pac_name, pac_path, test_url, decision, reachable])
            print(f"  {pac_name}: {test_url} -> {decision} [{reachable}]")

    headers = ["pac_name", "pac_path", "test_url", "pac_decision", "reachable"]
    success = write_csv_and_md(output_file, headers, results)
    if success:
        print(f"  ✓ Reachability test completed → {output_file} (and markdown)")
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

    headers = ["pac_name", "test_url", "before_decision", "after_decision", "change"]
    success_full = write_csv_and_md(output_full, headers, all_rows)
    success_summary = write_csv_and_md(output_summary, headers, changed_rows)
    
    if success_full and success_summary:
        print(f"  ✓ Full comparison → {output_full} (and markdown)")
        print(f"  ✓ Summary (changes only) → {output_summary} (and markdown)")
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

    headers = ["pac_name", "test_url", "before_decision", "after_decision", "before_reachable", "after_reachable", "change"]
    success_full = write_csv_and_md(output_full, headers, all_rows)
    success_summary = write_csv_and_md(output_summary, headers, changed_rows)
    
    if success_full and success_summary:
        print(f"  ✓ Full comparison → {output_full} (and markdown)")
        print(f"  ✓ Summary (changes only) → {output_summary} (and markdown)")
        print(f"\n  Statistics:")
        print(f"    • Total test cases: {len(all_rows)}")
        print(f"    • Changed: {changes_count - new_count}")
        print(f"    • New entries: {new_count}")
        print(f"    • Removed entries: {removed_count}")
        print(f"    • No change: {no_change_count}")
        return True
    return False


def is_subnet_of(child, parent):
    """Fallback manual check for child subnet_of parent"""
    if hasattr(child, 'subnet_of'):
        return child.subnet_of(parent)
    return parent.network_address <= child.network_address and parent.broadcast_address >= child.broadcast_address


def extract_return_val(lines, start_idx):
    """
    Look ahead to find the return statement belonging to the condition at start_idx.
    """
    for i in range(start_idx, len(lines)):
        line = lines[i]
        m = re.search(r'return\s+["\']([^"\']+)["\']', line)
        if m:
            return m.group(1).strip()
        # if another 'if' statement comes up after the starting line, stop looking
        if i > start_idx and re.search(r'\bif\s*\(', line):
            break
    return "UNKNOWN"


def check_pac_sanity(pac_file):
    """
    Checks if a PAC file has specific domains/subnets appearing AFTER 
    more general wildcard domains or larger subnets, ONLY IF they 
    route to different destinations.
    Returns a list of warning strings.
    """
    warnings = []
    try:
        with open(pac_file, 'r', errors='ignore') as f:
            lines = f.readlines()
            
        seen_domains = [] # list of (domain, base_domain, is_wildcard, line_num, return_val)
        seen_subnets = [] # list of (ip_network, line_num, return_val)
        
        # Matches: dnsDomainIs(host, "domain.com") or shExpMatch(host, "*.domain.com")
        domain_pattern = re.compile(r'(?:dnsDomainIs\s*\([^,]+,\s*[\'"](.*?)[\'"]\s*\)|shExpMatch\s*\([^,]+,\s*[\'"](.*?)[\'"]\s*\))')
        subnet_pattern = re.compile(r'isInNet\s*\([^,]+,\s*[\'"](.*?)[\'"]\s*,\s*[\'"](.*?)[\'"]\s*\)')
        
        for i, line in enumerate(lines, 0):
            line_clean = line.strip()
            if line_clean.startswith('//') or line_clean.startswith('*'):
                continue
                
            return_val = extract_return_val(lines, i)
                
            # Check domains
            for match in domain_pattern.findall(line):
                domain = (match[0] or match[1]).lower()
                if not domain:
                    continue
                    
                is_wildcard = False
                base_domain = domain
                if domain.startswith('*.'):
                    is_wildcard = True
                    base_domain = domain[2:]
                elif domain.startswith('.'):
                    is_wildcard = True
                    base_domain = domain[1:]
                elif domain.startswith('*'):
                    is_wildcard = True
                    base_domain = domain[1:]
                    
                for seen_dom, seen_base, seen_is_wild, seen_line, seen_ret in seen_domains:
                    if seen_is_wild:
                        if (base_domain != seen_base and base_domain.endswith("." + seen_base)) or (base_domain == seen_base and not is_wildcard):
                            if return_val == "UNKNOWN" or seen_ret == "UNKNOWN" or return_val != seen_ret:
                                warnings.append(f"Line {i+1}: Specific domain '{domain}' -> '{return_val}' appears after broader '{seen_dom}' -> '{seen_ret}' (Line {seen_line})")
                            
                seen_domains.append((domain, base_domain, is_wildcard, i+1, return_val))
                
            # Check subnets
            for match in subnet_pattern.findall(line):
                ip_str = match[0]
                mask_str = match[1]
                try:
                    net = ipaddress.IPv4Network(f"{ip_str}/{mask_str}", strict=False)
                    for seen_net, seen_line, seen_ret in seen_subnets:
                        if is_subnet_of(net, seen_net) and net != seen_net:
                            if return_val == "UNKNOWN" or seen_ret == "UNKNOWN" or return_val != seen_ret:
                                warnings.append(f"Line {i+1}: Specific subnet '{net}' -> '{return_val}' appears after broader '{seen_net}' -> '{seen_ret}' (Line {seen_line})")
                    seen_subnets.append((net, i+1, return_val))
                except Exception:
                    pass
                    
    except Exception as e:
        warnings.append(f"Error reading {pac_file} for sanity check: {e}")
        
    return warnings


def run_sanity_check_on_folder(pac_folder, output_csv, pac_rows=None):
    """
    Run the PAC logic sanity check to catch specific rules placed under wildcard rules.
    """
    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False
        
    if pac_rows is None:
        if not os.path.exists(PAC_LIST):
            print(f"Error: {PAC_LIST} not found.")
            return False
        try:
            with open(PAC_LIST, encoding="utf-8-sig") as f:
                pac_rows = list(csv.DictReader(f))
        except Exception as e:
            print(f"Error reading {PAC_LIST}: {e}")
            return False
        
    print(f"\n[Step] Running logic sanity checks on {pac_folder}/...")
    
    results = []
    
    for row in pac_rows:
        pac_name = row["pac_name"]
        pac_file = os.path.join(pac_folder, f"{pac_name}.pac")
        
        if not os.path.exists(pac_file):
            continue
            
        warnings = check_pac_sanity(pac_file)
        if not warnings:
            results.append([pac_name, "OK", "No logic order anomalies detected."])
        else:
            for w in warnings:
                results.append([pac_name, "WARNING", w])
                print(f"  ⚠ {pac_name}: {w}")
                
    headers = ["pac_name", "status", "message"]
    success = write_csv_and_md(output_csv, headers, results)
    if success:
        print(f"  ✓ Sanity check completed → {output_csv} (and markdown)")
    return success


def compare_sanity_results(before, after, output_summary):
    """
    Compare BEFORE and AFTER sanity checks.
    """
    if not os.path.exists(before) or not os.path.exists(after):
        return False
        
    print("\n[Step] Comparing sanity check results...")
    
    before_warns = set()
    with open(before) as f:
        for r in csv.DictReader(f):
            if r["status"] == "WARNING":
                before_warns.add((r["pac_name"], r["message"]))
                
    after_warns = set()
    with open(after) as f:
        for r in csv.DictReader(f):
            if r["status"] == "WARNING":
                after_warns.add((r["pac_name"], r["message"]))
                
    new_warnings = after_warns - before_warns
    fixed_warnings = before_warns - after_warns
    
    results = []
    for pac, msg in new_warnings:
        results.append([pac, "NEW_WARNING", msg])
    for pac, msg in fixed_warnings:
        results.append([pac, "FIXED", msg])
        
    if not results:
        results.append(["ALL", "NO_CHANGE", "Sanity warnings are identical before and after."])
        
    headers = ["pac_name", "change_type", "message"]
    success = write_csv_and_md(output_summary, headers, results)
    if success:
        print(f"  ✓ Sanity comparison completed → {output_summary} (and markdown)")
        print(f"    • New warnings: {len(new_warnings)}")
        print(f"    • Fixed warnings: {len(fixed_warnings)}")
    return success


def load_header_test_urls():
    """Load URLs for header testing from CSV."""
    urls = []
    if not os.path.exists(HEADER_TEST_URLS_CSV):
        print(f"  [+] Creating template {HEADER_TEST_URLS_CSV}...")
        try:
            with open(HEADER_TEST_URLS_CSV, "w", newline="") as sf:
                writer = csv.writer(sf)
                writer.writerow(["test_url"])
                writer.writerow(["https://www.google.com"])
                writer.writerow(["https://www.microsoft.com"])
        except Exception as e:
            print(f"  ⚠ Failed to create {HEADER_TEST_URLS_CSV}: {e}")
            
    if os.path.exists(HEADER_TEST_URLS_CSV):
        with open(HEADER_TEST_URLS_CSV, encoding="utf-8-sig") as sf:
            reader = csv.DictReader(sf)
            for row in reader:
                # Support both 'test_url' (new format matching supplement_test.csv) and 'url' (old format)
                url = (row.get("test_url") or row.get("url") or "").strip()
                if url and url not in urls:
                    urls.append(url)
    return urls

def parse_proxy_for_requests(proxy_decision):
    """
    Convert PAC return string (e.g., 'PROXY 1.2.3.4:80; DIRECT')
    to requests proxy dict format.
    """
    if "PROXY" in proxy_decision:
        proxy_match = re.search(r"PROXY\s+([a-zA-Z0-9.-]+):(\d+)", proxy_decision)
        if proxy_match:
            proxy_str = f"http://{proxy_match.group(1)}:{proxy_match.group(2)}"
            return {"http": proxy_str, "https": proxy_str}
    return None

def run_header_test_from_folder(pac_folder, output_file, pac_rows=None):
    """
    Test header accessibility by simulating a browser and using PAC files.
    Passes Zscaler auth first.
    """
    if not requests:
        print("Error: 'requests' module not installed. Cannot run header tests.")
        return False
        
    urls = load_header_test_urls()
    if not urls:
        print(f"Error: No URLs found in {HEADER_TEST_URLS_CSV}.")
        return False
        
    if not os.path.exists(pac_folder):
        print(f"Error: {pac_folder} not found.")
        return False
        
    if pac_rows is None:
        if not os.path.exists(PAC_LIST):
            print(f"Error: {PAC_LIST} not found.")
            return False
        try:
            with open(PAC_LIST, encoding="utf-8-sig") as f:
                pac_rows = list(csv.DictReader(f))
        except Exception as e:
            print(f"Error reading {PAC_LIST}: {e}")
            return False
            
    print(f"\n[Step] Running header tests from {pac_folder}/...")
    
    results = []
    
    for row in pac_rows:
        pac_name = row["pac_name"]
        pac_file = os.path.join(pac_folder, f"{pac_name}.pac")
        
        if not os.path.exists(pac_file):
            print(f"  ⚠ Skipping {pac_name} (file not found)")
            for url in urls:
                results.append([pac_name, url, "PAC_FILE_NOT_FOUND", "N/A", "N/A"])
            continue
            
        print(f"  Processing {pac_name}...")
        
        # Setup session to simulate browser
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Pass Zscaler Web Auth first
        auth_url = "https://www.microsoft.com" # Use a reliable site to trigger auth
        auth_decision = evaluate_pac(pac_file, auth_url, skip_dns=True)
        auth_proxies = parse_proxy_for_requests(auth_decision)
        
        print("    Passing Zscaler web authentication...")
        try:
            session.get(auth_url, proxies=auth_proxies, timeout=10, verify=False)
        except Exception as e:
            print(f"    ⚠ Initial auth request had an issue, continuing anyway: {type(e).__name__}")
            
        # Test each URL
        for url in urls:
            decision = evaluate_pac(pac_file, url, skip_dns=True)
            proxies = parse_proxy_for_requests(decision)
            
            try:
                # Use GET with stream=True and close immediately to just get headers and save time
                resp = session.get(url, proxies=proxies, timeout=10, verify=False, stream=True)
                status = f"{resp.status_code} {resp.reason}"
                title = extract_html_title(resp)
                resp.close()
            except requests.exceptions.RequestException as e:
                status = f"ERROR: {type(e).__name__}"
                title = "N/A"
            except Exception as e:
                status = f"ERROR: {str(e)}"
                title = "N/A"
                
            results.append([pac_name, url, decision, status, title])
            print(f"    {url} -> {status} ({title})")
            
    headers = ["pac_name", "test_url", "pac_decision", "http_status", "website_title"]
    success = write_csv_and_md(output_file, headers, results)
    if success:
        print(f"  ✓ Header test completed → {output_file} (and markdown)")
    return success

def compare_header_results(before, after, output_full, output_summary):
    if not os.path.exists(before) or not os.path.exists(after):
        print("Error: Missing before/after header result files.")
        return False
        
    print("\n[Step] Comparing header test results...")
    before_map = {}
    with open(before, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            key = (r.get("pac_name"), r.get("test_url"))
            before_map[key] = r
            
    changes_count = 0
    changed_rows = []
    all_rows = []
    
    with open(after, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            key = (r.get("pac_name"), r.get("test_url"))
            b = before_map.get(key)
            
            b_dec = b.get("pac_decision", "N/A") if b else "N/A"
            b_status = b.get("http_status", "N/A") if b else "N/A"
            b_title = b.get("website_title", "N/A") if b else "N/A"

            r_dec = r.get("pac_decision", "N/A")
            r_status = r.get("http_status", "N/A")
            r_title = r.get("website_title", "N/A")

            if not b:
                change = "NEW_ENTRY"
                changes_count += 1
            elif (b_dec != r_dec) or (b_status != r_status):
                change = "CHANGED"
                changes_count += 1
            else:
                change = "NO_CHANGE"
                
            row_data = [
                r.get("pac_name", ""), r.get("test_url", ""),
                b_dec, r_dec,
                b_status, r_status,
                b_title, r_title,
                change
            ]
            all_rows.append(row_data)
            if change != "NO_CHANGE":
                changed_rows.append(row_data)
                
    headers = ["pac_name", "test_url", "before_decision", "after_decision", "before_status", "after_status", "before_title", "after_title", "change"]
    success_full = write_csv_and_md(output_full, headers, all_rows)
    success_summary = write_csv_and_md(output_summary, headers, changed_rows)
    
    if success_full and success_summary:
        print(f"  ✓ Full comparison → {output_full} (and markdown)")
        print(f"  ✓ Summary (changes only) → {output_summary} (and markdown)")
        return True
    return False


def workflow_setup_baseline():
    """
    Workflow 1: Setup baseline testing environment (FULL - with reachability)
    """
    pac_rows = ask_region_selection()
    if pac_rows is None:
        print("\n❌ Cancelled region selection. Aborting workflow.")
        return

    print("\n" + "="*60)
    print("  WORKFLOW 1: Setup Baseline (Full Testing)")
    print("="*60)
    
    run_dir = get_run_folder()
    old_pac_dir = os.path.join(run_dir, OLD_PAC_DIR)
    
    if not download_pac_files_to_folder(old_pac_dir, pac_rows=pac_rows):
        print("\n❌ Workflow failed at download step")
        return
    
    if not generate_test_logic_csv_from_folder(old_pac_dir, os.path.join(run_dir, "old_test_logic.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at test_logic.csv generation")
        return
    
    if not generate_test_reachability_csv_from_folder(old_pac_dir, os.path.join(run_dir, "old_test_reachability.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at test_reachability.csv generation")
        return
    
    if not run_logic_test(os.path.join(run_dir, "old_test_logic.csv"), old_pac_dir, os.path.join(run_dir, "before_logic_result.csv"), skip_dns=True):
        print("\n❌ Workflow failed at BEFORE logic test")
        return
    
    if not run_reachability_test_from_folder(old_pac_dir, os.path.join(run_dir, "old_test_reachability.csv"), os.path.join(run_dir, "before_reachability_result.csv")):
        print("\n❌ Workflow failed at BEFORE reachability test")
        return
        
    if not run_sanity_check_on_folder(old_pac_dir, os.path.join(run_dir, "before_sanity_check.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at BEFORE sanity test")
        return
    
    print("\n" + "="*60)
    print("  ✓ BASELINE SETUP COMPLETE (FULL)")
    print("="*60)
    print("\n  Files created inside run folder:")
    print(f"    Run directory: {run_dir}/")
    print(f"    - {OLD_PAC_DIR}/                    (original PAC files)")
    print("    - old_test_logic.csv              (logic test cases - includes subnets)")
    print("    - old_test_reachability.csv       (reachability test cases - excludes subnets)")
    print("    - before_logic_result.csv         (baseline logic results)")
    print("    - before_reachability_result.csv  (baseline reachability results)")
    print("    - before_sanity_check.csv         (baseline sanity results)")
    print("\n  Next step: Make your PAC file changes, then run Workflow 2")
    print("="*60 + "\n")


def workflow_test_and_compare():
    """
    Workflow 2: Test updated PAC files and compare (FULL - with reachability)
    """
    pac_rows = ask_region_selection()
    if pac_rows is None:
        print("\n❌ Cancelled region selection. Aborting workflow.")
        return

    print("\n" + "="*60)
    print("  WORKFLOW 2: Test Updated PAC Files & Compare (Full)")
    print("="*60)
    
    before_logic = find_latest_baseline_file("before_logic_result.csv")
    before_reach = find_latest_baseline_file("before_reachability_result.csv")
    before_sanity = find_latest_baseline_file("before_sanity_check.csv")
    
    if not before_logic:
        print("\n❌ Baseline logic results (before_logic_result.csv) not found!")
        print("  Please run Workflow 1 (Setup Baseline) first.")
        return
    
    if not before_reach:
        print("\n❌ Baseline reachability results (before_reachability_result.csv) not found!")
        print("  Please run Workflow 1 (Setup Baseline) first.")
        return
        
    if not before_sanity:
        print("\n❌ Baseline sanity results (before_sanity_check.csv) not found!")
        print("  Please run Workflow 1 (Setup Baseline) first.")
        return
        
    print(f"  [i] Using baseline files found:")
    print(f"      • Logic: {before_logic}")
    print(f"      • Reachability: {before_reach}")
    print(f"      • Sanity: {before_sanity}")
    
    run_dir = get_run_folder()
    updated_pac_dir = os.path.join(run_dir, UPDATED_PAC_DIR)
    
    if not download_pac_files_to_folder(updated_pac_dir, pac_rows=pac_rows):
        print("\n❌ Workflow failed at download step")
        return
    
    if not generate_test_logic_csv_from_folder(updated_pac_dir, os.path.join(run_dir, "updated_test_logic.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at test_logic.csv generation")
        return
    
    if not generate_test_reachability_csv_from_folder(updated_pac_dir, os.path.join(run_dir, "updated_test_reachability.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at test_reachability.csv generation")
        return
    
    if not run_logic_test(os.path.join(run_dir, "updated_test_logic.csv"), updated_pac_dir, os.path.join(run_dir, "after_logic_result.csv"), skip_dns=True):
        print("\n❌ Workflow failed at AFTER logic test")
        return
    
    if not run_reachability_test_from_folder(updated_pac_dir, os.path.join(run_dir, "updated_test_reachability.csv"), os.path.join(run_dir, "after_reachability_result.csv")):
        print("\n❌ Workflow failed at AFTER reachability test")
        return
    
    if not compare_logic_results(
        before_logic,
        os.path.join(run_dir, "after_logic_result.csv"),
        os.path.join(run_dir, "pac_logic_comparison_full.csv"),
        os.path.join(run_dir, "pac_logic_comparison_summary.csv")
    ):
        print("\n❌ Workflow failed at logic comparison step")
        return
    
    if not compare_reachability_results(
        before_reach,
        os.path.join(run_dir, "after_reachability_result.csv"),
        os.path.join(run_dir, "pac_reachability_comparison_full.csv"),
        os.path.join(run_dir, "pac_reachability_comparison_summary.csv")
    ):
        print("\n❌ Workflow failed at reachability comparison step")
        return
        
    if not run_sanity_check_on_folder(updated_pac_dir, os.path.join(run_dir, "after_sanity_check.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at AFTER sanity test")
        return
        
    if not compare_sanity_results(before_sanity, os.path.join(run_dir, "after_sanity_check.csv"), os.path.join(run_dir, "pac_sanity_comparison_summary.csv")):
        print("\n❌ Workflow failed at sanity comparison step")
        return
    
    print("\n" + "="*60)
    print("  ✓ TESTING & COMPARISON COMPLETE (FULL)")
    print("="*60)
    print("\n  Files created inside run folder:")
    print(f"    Run directory: {run_dir}/")
    print(f"    - {UPDATED_PAC_DIR}/                          (updated PAC files)")
    print("    - updated_test_logic.csv                    (logic test cases - includes subnets)")
    print("    - updated_test_reachability.csv             (reachability test cases - excludes subnets)")
    print("    - after_logic_result.csv                    (updated logic results)")
    print("    - after_reachability_result.csv             (updated reachability results)")
    print("    - after_sanity_check.csv                    (updated sanity results)")
    print("\n  Comparison Reports in folder:")
    print("    Logic Testing:")
    print("      • pac_logic_comparison_full.csv           (all test cases)")
    print("      • pac_logic_comparison_summary.csv        (changes only)")
    print("    Reachability Testing:")
    print("      • pac_reachability_comparison_full.csv    (all test cases)")
    print("      • pac_reachability_comparison_summary.csv (changes only)")
    print("    Sanity Checking:")
    print("      • pac_sanity_comparison_summary.csv       (sanity warning changes)")
    print("\n  📊 Review summary reports for quick impact assessment")
    print("="*60 + "\n")


def workflow_setup_baseline_logic_only():
    """
    Workflow 3: Setup baseline testing environment (LOGIC ONLY - faster)
    """
    pac_rows = ask_region_selection()
    if pac_rows is None:
        print("\n❌ Cancelled region selection. Aborting workflow.")
        return

    print("\n" + "="*60)
    print("  WORKFLOW 3: Setup Baseline (Logic Testing Only)")
    print("="*60)
    
    run_dir = get_run_folder()
    old_pac_dir = os.path.join(run_dir, OLD_PAC_DIR)
    
    if not download_pac_files_to_folder(old_pac_dir, pac_rows=pac_rows):
        print("\n❌ Workflow failed at download step")
        return
    
    if not generate_test_logic_csv_from_folder(old_pac_dir, os.path.join(run_dir, "old_test_logic.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at test_logic.csv generation")
        return
    
    if not run_logic_test(os.path.join(run_dir, "old_test_logic.csv"), old_pac_dir, os.path.join(run_dir, "before_logic_result.csv"), skip_dns=True):
        print("\n❌ Workflow failed at BEFORE logic test")
        return
        
    if not run_sanity_check_on_folder(old_pac_dir, os.path.join(run_dir, "before_sanity_check.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at BEFORE sanity test")
        return
    
    print("\n" + "="*60)
    print("  ✓ BASELINE SETUP COMPLETE (LOGIC ONLY)")
    print("="*60)
    print("\n  Files created inside run folder:")
    print(f"    Run directory: {run_dir}/")
    print(f"    - {OLD_PAC_DIR}/                 (original PAC files)")
    print("    - old_test_logic.csv       (logic test cases - includes subnets)")
    print("    - before_logic_result.csv  (baseline logic results)")
    print("    - before_sanity_check.csv  (baseline sanity results)")
    print("\n  Next step: Make your PAC file changes, then run Workflow 4")
    print("  Note: Reachability tests skipped for faster execution")
    print("="*60 + "\n")


def workflow_test_and_compare_logic_only():
    """
    Workflow 4: Test updated PAC files and compare (LOGIC ONLY - faster)
    """
    pac_rows = ask_region_selection()
    if pac_rows is None:
        print("\n❌ Cancelled region selection. Aborting workflow.")
        return

    print("\n" + "="*60)
    print("  WORKFLOW 4: Test Updated PAC Files & Compare (Logic Only)")
    print("="*60)
    
    before_logic = find_latest_baseline_file("before_logic_result.csv")
    before_sanity = find_latest_baseline_file("before_sanity_check.csv")
    
    if not before_logic:
        print("\n❌ Baseline logic results (before_logic_result.csv) not found!")
        print("  Please run Workflow 3 (Setup Baseline - Logic Only) first.")
        return
        
    if not before_sanity:
        print("\n❌ Baseline sanity results (before_sanity_check.csv) not found!")
        print("  Please run Workflow 3 (Setup Baseline - Logic Only) first.")
        return
        
    print(f"  [i] Using baseline files found:")
    print(f"      • Logic: {before_logic}")
    print(f"      • Sanity: {before_sanity}")
    
    run_dir = get_run_folder()
    updated_pac_dir = os.path.join(run_dir, UPDATED_PAC_DIR)
    
    if not download_pac_files_to_folder(updated_pac_dir, pac_rows=pac_rows):
        print("\n❌ Workflow failed at download step")
        return
    
    if not generate_test_logic_csv_from_folder(updated_pac_dir, os.path.join(run_dir, "updated_test_logic.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at test_logic.csv generation")
        return
    
    if not run_logic_test(os.path.join(run_dir, "updated_test_logic.csv"), updated_pac_dir, os.path.join(run_dir, "after_logic_result.csv"), skip_dns=True):
        print("\n❌ Workflow failed at AFTER logic test")
        return
    
    if not compare_logic_results(
        before_logic,
        os.path.join(run_dir, "after_logic_result.csv"),
        os.path.join(run_dir, "pac_logic_comparison_full.csv"),
        os.path.join(run_dir, "pac_logic_comparison_summary.csv")
    ):
        print("\n❌ Workflow failed at logic comparison step")
        return
        
    if not run_sanity_check_on_folder(updated_pac_dir, os.path.join(run_dir, "after_sanity_check.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at AFTER sanity test")
        return
        
    if not compare_sanity_results(before_sanity, os.path.join(run_dir, "after_sanity_check.csv"), os.path.join(run_dir, "pac_sanity_comparison_summary.csv")):
        print("\n❌ Workflow failed at sanity comparison step")
        return
    
    print("\n" + "="*60)
    print("  ✓ TESTING & COMPARISON COMPLETE (LOGIC ONLY)")
    print("="*60)
    print("\n  Files created inside run folder:")
    print(f"    Run directory: {run_dir}/")
    print(f"    - {UPDATED_PAC_DIR}/                          (updated PAC files)")
    print("    - updated_test_logic.csv                (logic test cases - includes subnets)")
    print("    - after_logic_result.csv                (updated logic results)")
    print("    - after_sanity_check.csv                (updated sanity results)")
    print("\n  Comparison Reports:")
    print("    • pac_logic_comparison_full.csv         (all test cases)")
    print("    • pac_logic_comparison_summary.csv      (changes only)")
    print("    • pac_sanity_comparison_summary.csv     (sanity warning changes)")
    print("\n  ⚡ Fast execution: Reachability tests skipped")
    print("  📊 Review summary report for routing logic changes")
    print("="*60 + "\n")


def workflow_setup_baseline_header_only():
    """
    Workflow 5: Setup baseline testing environment (HEADER ONLY)
    """
    pac_rows = ask_region_selection()
    if pac_rows is None:
        print("\n❌ Cancelled region selection. Aborting workflow.")
        return

    print("\n" + "="*60)
    print("  WORKFLOW 5: Setup Baseline (Header Testing Only)")
    print("="*60)
    
    run_dir = get_run_folder()
    old_pac_dir = os.path.join(run_dir, OLD_PAC_DIR)
    
    if not download_pac_files_to_folder(old_pac_dir, pac_rows=pac_rows):
        print("\n❌ Workflow failed at download step")
        return
        
    if not run_header_test_from_folder(old_pac_dir, os.path.join(run_dir, "before_header_result.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at BEFORE header test")
        return
        
    print("\n" + "="*60)
    print("  ✓ BASELINE SETUP COMPLETE (HEADER ONLY)")
    print("="*60)
    print("\n  Files created inside run folder:")
    print(f"    Run directory: {run_dir}/")
    print(f"    - {OLD_PAC_DIR}/                   (original PAC files)")
    print(f"    - {HEADER_TEST_URLS_CSV}     (input URLs for testing)")
    print("    - before_header_result.csv   (baseline header results)")
    print("\n  Next step: Make your PAC file changes, then run Workflow 6")
    print("="*60 + "\n")


def workflow_test_and_compare_header_only():
    """
    Workflow 6: Test updated PAC files and compare (HEADER ONLY)
    """
    pac_rows = ask_region_selection()
    if pac_rows is None:
        print("\n❌ Cancelled region selection. Aborting workflow.")
        return

    print("\n" + "="*60)
    print("  WORKFLOW 6: Test Updated PAC Files & Compare (Header Only)")
    print("="*60)
    
    before_header = find_latest_baseline_file("before_header_result.csv")
    if not before_header:
        print("\n❌ Baseline header results (before_header_result.csv) not found!")
        print("  Please run Workflow 5 (Setup Baseline - Header Only) first.")
        return
        
    print(f"  [i] Using baseline file found: {before_header}")
    
    run_dir = get_run_folder()
    updated_pac_dir = os.path.join(run_dir, UPDATED_PAC_DIR)
    
    if not download_pac_files_to_folder(updated_pac_dir, pac_rows=pac_rows):
        print("\n❌ Workflow failed at download step")
        return
        
    if not run_header_test_from_folder(updated_pac_dir, os.path.join(run_dir, "after_header_result.csv"), pac_rows=pac_rows):
        print("\n❌ Workflow failed at AFTER header test")
        return
        
    if not compare_header_results(
        before_header,
        os.path.join(run_dir, "after_header_result.csv"),
        os.path.join(run_dir, "pac_header_comparison_full.csv"),
        os.path.join(run_dir, "pac_header_comparison_summary.csv")
    ):
        print("\n❌ Workflow failed at header comparison step")
        return
        
    print("\n" + "="*60)
    print("  ✓ TESTING & COMPARISON COMPLETE (HEADER ONLY)")
    print("="*60)
    print("\n  Files created inside run folder:")
    print(f"    Run directory: {run_dir}/")
    print(f"    - {UPDATED_PAC_DIR}/                        (updated PAC files)")
    print("    - after_header_result.csv             (updated header results)")
    print("\n  Comparison Reports in folder:")
    print("    • pac_header_comparison_full.csv      (all test cases)")
    print("    • pac_header_comparison_summary.csv   (changes only)")
    print("="*60 + "\n")


def check_csv_files_at_startup():
    """Check existence and format of CSV files, prompting for creation of examples if missing."""
    print("\n🔍 Checking CSV configuration files...")
    
    files_to_check = [
        {
            "name": PAC_LIST,
            "required": True,
            "expected_headers": ["pac_name", "pac_path", "region"],
            "description": "list of PAC files to download and validate",
            "example_rows": [
                ["example_pac", "https://example.com/proxy.pac", "hk"]
            ]
        },
        {
            "name": "supplement_test.csv",
            "required": False,
            "expected_headers": ["test_url"],
            "description": "supplemental test URLs for logic, reachability, and header status testing",
            "example_rows": [
                ["https://www.google.com"],
                ["https://www.microsoft.com"]
            ]
        }
    ]

    for item in files_to_check:
        filename = item["name"]
        
        if not os.path.exists(filename):
            print(f"  ⚠ '{filename}' ({item['description']}) not found.")
            create_choice = input(f"    Generate an example '{filename}'? (y/n) [y]: ").strip().lower() or 'y'
            if create_choice == 'y':
                try:
                    with open(filename, "w", newline="", encoding="utf-8") as sf:
                        writer = csv.writer(sf)
                        writer.writerow(item["expected_headers"])
                        writer.writerows(item["example_rows"])
                    print(f"    ✓ Example template created: '{filename}'")
                except Exception as e:
                    print(f"    ❌ Failed to create '{filename}': {e}")
            else:
                if item["required"]:
                    print(f"    ⚠ Warning: '{filename}' is required. Some features will fail without it.")
        else:
            # File exists, check format
            try:
                with open(filename, "r", encoding="utf-8-sig") as sf:
                    reader = csv.reader(sf)
                    headers = next(reader, None)
                    if not headers:
                        print(f"  ❌ Format check failed: '{filename}' is empty or invalid.")
                    else:
                        # Clean headers (strip spaces, lower case, remove BOM)
                        headers_clean = [h.strip().lower() for h in headers]
                        if filename == "supplement_test.csv":
                            if not ("test_url" in headers_clean or "url" in headers_clean):
                                print(f"  ❌ Format check failed: '{filename}' header must contain 'test_url' or 'url' (found: {headers})")
                            else:
                                print(f"  ✓ Found '{filename}' (Format: Valid)")
                        else:
                            # region is optional but recommended
                            missing_headers = [h for h in item["expected_headers"] if h.strip().lower() not in headers_clean]
                            if missing_headers:
                                if "region" in missing_headers:
                                    print(f"  ⚠ Note: '{filename}' is missing the optional 'region' column. All PACs will default to no region.")
                                    other_missing = [h for h in missing_headers if h != "region"]
                                    if other_missing:
                                        print(f"  ❌ Format check failed: '{filename}' is missing required expected header(s): {other_missing} (found: {headers})")
                                    else:
                                        print(f"  ✓ Found '{filename}' (Format: Valid, without region column)")
                                else:
                                    print(f"  ❌ Format check failed: '{filename}' is missing expected header(s): {missing_headers} (found: {headers})")
                            else:
                                print(f"  ✓ Found '{filename}' (Format: Valid)")
            except Exception as e:
                print(f"  ❌ Error checking '{filename}': {e}")
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
│  5) Setup Baseline (Header Testing - Browser Simulation)   │
│  6) Test Updated PAC & Compare (Header Testing)            │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─ INDIVIDUAL OPERATIONS ────────────────────────────────────┐
│                                                             │
│  7) Backup current PAC files (to backup/)                  │
│  8) Generate test_logic.csv from old_PAC/                  │
│  9) Generate test_logic.csv from updated_PAC/              │
│ 10) Generate test_reachability.csv from old_PAC/           │
│ 11) Generate test_reachability.csv from updated_PAC/       │
│ 12) Run logic test on old_PAC/                             │
│ 13) Run logic test on updated_PAC/                         │
│ 14) Run reachability test on old_PAC/                      │
│ 15) Run reachability test on updated_PAC/                  │
│ 16) Reload DNS configuration from dns_config.json          │
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
            workflow_setup_baseline_header_only()
        elif choice == "6":
            workflow_test_and_compare_header_only()
        elif choice == "7":
            backup_pac_files()
        elif choice == "8":
            pac_rows = ask_region_selection()
            if pac_rows is not None:
                run_dir = get_run_folder()
                old_pac_dir = find_latest_directory(OLD_PAC_DIR)
                generate_test_logic_csv_from_folder(old_pac_dir, os.path.join(run_dir, "old_test_logic.csv"), pac_rows=pac_rows)
        elif choice == "9":
            pac_rows = ask_region_selection()
            if pac_rows is not None:
                run_dir = get_run_folder()
                updated_pac_dir = find_latest_directory(UPDATED_PAC_DIR)
                generate_test_logic_csv_from_folder(updated_pac_dir, os.path.join(run_dir, "updated_test_logic.csv"), pac_rows=pac_rows)
        elif choice == "10":
            pac_rows = ask_region_selection()
            if pac_rows is not None:
                run_dir = get_run_folder()
                old_pac_dir = find_latest_directory(OLD_PAC_DIR)
                generate_test_reachability_csv_from_folder(old_pac_dir, os.path.join(run_dir, "old_test_reachability.csv"), pac_rows=pac_rows)
        elif choice == "11":
            pac_rows = ask_region_selection()
            if pac_rows is not None:
                run_dir = get_run_folder()
                updated_pac_dir = find_latest_directory(UPDATED_PAC_DIR)
                generate_test_reachability_csv_from_folder(updated_pac_dir, os.path.join(run_dir, "updated_test_reachability.csv"), pac_rows=pac_rows)
        elif choice == "12":
            pac_rows = ask_region_selection()
            if pac_rows is not None:
                test_csv = find_latest_baseline_file("old_test_logic.csv")
                if not test_csv:
                    print("\n❌ old_test_logic.csv not found. Generate it first (option 8).")
                else:
                    run_dir = get_run_folder()
                    old_pac_dir = find_latest_directory(OLD_PAC_DIR)
                    run_logic_test(test_csv, old_pac_dir, os.path.join(run_dir, "manual_old_logic_result.csv"), skip_dns=True, pac_rows=pac_rows)
        elif choice == "13":
            pac_rows = ask_region_selection()
            if pac_rows is not None:
                test_csv = find_latest_baseline_file("updated_test_logic.csv")
                if not test_csv:
                    print("\n❌ updated_test_logic.csv not found. Generate it first (option 9).")
                else:
                    run_dir = get_run_folder()
                    updated_pac_dir = find_latest_directory(UPDATED_PAC_DIR)
                    success = run_logic_test(test_csv, updated_pac_dir, os.path.join(run_dir, "manual_updated_logic_result.csv"), skip_dns=True, pac_rows=pac_rows)
                    if success:
                        before_file = find_latest_baseline_file("manual_old_logic_result.csv")
                        if not before_file:
                            before_file = find_latest_baseline_file("before_logic_result.csv")
                            
                        if before_file:
                            compare_logic_results(
                                before_file,
                                os.path.join(run_dir, "manual_updated_logic_result.csv"),
                                os.path.join(run_dir, "manual_logic_comparison_full.csv"),
                                os.path.join(run_dir, "manual_logic_comparison_summary.csv")
                            )
                        else:
                            print("\nℹ️ Could not find 'manual_old_logic_result.csv' or 'before_logic_result.csv' to compare against.")
                            print("  Run Option 12 or Workflow first to generate the comparison files.")
        elif choice == "14":
            pac_rows = ask_region_selection()
            if pac_rows is not None:
                test_csv = find_latest_baseline_file("old_test_reachability.csv")
                if not test_csv:
                    print("\n❌ old_test_reachability.csv not found. Generate it first (option 10).")
                else:
                    run_dir = get_run_folder()
                    old_pac_dir = find_latest_directory(OLD_PAC_DIR)
                    run_reachability_test_from_folder(old_pac_dir, test_csv, os.path.join(run_dir, "manual_old_reachability_result.csv"), pac_rows=pac_rows)
        elif choice == "15":
            pac_rows = ask_region_selection()
            if pac_rows is not None:
                test_csv = find_latest_baseline_file("updated_test_reachability.csv")
                if not test_csv:
                    print("\n❌ updated_test_reachability.csv not found. Generate it first (option 11).")
                else:
                    run_dir = get_run_folder()
                    updated_pac_dir = find_latest_directory(UPDATED_PAC_DIR)
                    run_reachability_test_from_folder(updated_pac_dir, test_csv, os.path.join(run_dir, "manual_updated_reachability_result.csv"), pac_rows=pac_rows)
        elif choice == "16":
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
    check_csv_files_at_startup()
    menu()