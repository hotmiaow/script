import os
import sys
import glob
from urllib.parse import urlparse
import pacparser


def test_pac_file(pac_path, target_url):
    """Use pacparser to verify the local PAC file routing for a specific URL."""
    # Check if the PAC file exists
    if not os.path.exists(pac_path):
        print(f"\n[-] Error: PAC file not found, please check the path: {pac_path}")
        return

    # Automatically extract the host from the URL
    parsed_url = urlparse(target_url)
    target_host = parsed_url.hostname
    if not target_host:
        print(
            f"\n[-] Error: Cannot parse Hostname from the URL. Please check the URL format (must include http:// or https://)."
        )
        return

    print(f"\n[+] Initializing PAC engine...")
    pacparser.init()

    try:
        print(f"[+] Loading PAC file: {pac_path}")
        pacparser.parse_pac_file(pac_path)

        print(f"[+] Starting route matching...")
        print(f"    Target URL: {target_url}")
        print(f"    Target Host: {target_host}")
        print("-" * 60)

        # Execute FindProxyForURL logic inside the PAC file
        result = pacparser.find_proxy(target_url, target_host)

        # Print the parsing result highlighted in green
        print(f"[+] Parsing Result: \033[92m{result}\033[0m")

        # Attempt to find which line(s) match the result
        try:
            with open(pac_path, 'r', encoding='utf-8', errors='ignore') as f:
                pac_lines = f.readlines()
                
            matched_lines = []
            for i, line in enumerate(pac_lines, 1):
                if result in line:
                    matched_lines.append((i, line.strip()))
                    
            if matched_lines:
                print(f"[+] Possible matching line(s) in the PAC file for this result:")
                for line_num, line_content in matched_lines:
                    print(f"    Line {line_num}: {line_content}")
            else:
                print("[-] Could not find exact match for the result string in the PAC file.")
        except Exception as file_e:
            pass

        print("-" * 60)

    except Exception as e:
        print(f"\n[-] Error occurred during parsing: {e}")
        print(
            "[-] This usually indicates a JavaScript syntax error inside the PAC file, or the use of unsupported functions."
        )

    finally:
        # Release memory resources occupied by pacparser
        pacparser.cleanup()


def select_pac_file():
    """Find .pac files in the script's directory and prompt user to select one or enter path."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pac_files = glob.glob(os.path.join(script_dir, "*.pac"))
    
    print("\n[+] Please select a PAC file:")
    print("    1. Manual enter path")
    
    for idx, file_path in enumerate(pac_files, 2):
        print(f"    {idx}. {os.path.basename(file_path)}")
        
    while True:
        try:
            choice = input(f"Enter the number of your choice (1-{len(pac_files) + 1}): ").strip()
            choice_idx = int(choice)
            
            if choice_idx == 1:
                manual_path = input("Please enter the full path to the PAC file: ").strip()
                manual_path = manual_path.strip('"')
                if os.path.exists(manual_path):
                    return manual_path
                else:
                    print("[-] Error: The specified file does not exist. Please try again.")
            elif 2 <= choice_idx <= len(pac_files) + 1:
                selected_file = pac_files[choice_idx - 2]
                print(f"[+] Selected: {os.path.basename(selected_file)}")
                return selected_file
            else:
                print("[-] Invalid selection, please try again.")
        except ValueError:
            print("[-] Please enter a valid number.")


if __name__ == "__main__":
    DEFAULT_URL = "https://nomuracmdbqa.service-now.com/now/nav/ui/home"

    print("=" * 60)
    print(" PAC File Path and Routing Test Tool ")
    print("=" * 60)

    while True:
        # Select PAC file
        user_pac = select_pac_file()
        if not user_pac:
            input("\nPress any key to exit...")
            sys.exit(1)

        while True:
            # Prompt for test URL
            user_url = input(f"\nPlease enter the URL to test (or type 'back' to change PAC, 'exit' to quit) [{DEFAULT_URL}]: ").strip()
            
            if user_url.lower() == 'exit':
                print("\nExiting...")
                sys.exit(0)
            elif user_url.lower() == 'back':
                print("\n" + "=" * 60)
                break
                
            if not user_url:
                user_url = DEFAULT_URL
            user_url = user_url.strip('"')

            # Execute test
            test_pac_file(user_pac, user_url)