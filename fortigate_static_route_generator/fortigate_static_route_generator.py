import csv
import ipaddress
import os
import sys

def parse_network(ip_str, mask_str):
    ip_str = ip_str.strip()
    mask_str = mask_str.strip() if mask_str else ""
    
    try:
        if '/' in ip_str:
            net = ipaddress.ip_network(ip_str, strict=False)
            return str(net.network_address), str(net.netmask), net.prefixlen
        else:
            if not mask_str:
                # Default to /32 if no mask provided and no CIDR
                mask_str = "255.255.255.255"
            net = ipaddress.ip_network(f"{ip_str}/{mask_str}", strict=False)
            return str(net.network_address), str(net.netmask), net.prefixlen
    except ValueError as e:
        print(f"Error parsing IP/Mask: {ip_str} {mask_str} - {e}")
        # fallback to returning original components
        return ip_str, mask_str, "32"

def generate_example_csv(filename):
    with open(filename, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['subnet', 'subnet_mask', 'interface', 'gateway', 'comment'])
        writer.writerow(['113.12.11.0', '255.255.255.0', 'LAG2.200', '10.0.0.1', 'ZCC'])
        writer.writerow(['113.12.12.0/24', '', 'LAG2.200', '', 'MS_Teams'])
    print(f"Example file '{filename}' has been generated. Please fill it with your data and run the script again.")

def main():
    input_file = 'route.csv'
    
    # Check if route.csv exists, fallback to route.txt since both were mentioned
    if not os.path.exists(input_file):
        if os.path.exists('route.txt'):
            input_file = 'route.txt'
        else:
            print(f"File '{input_file}' or 'route.txt' not found.")
            generate_example_csv('route.csv')
            sys.exit(0)

    routes = []
    
    # utf-8-sig automatically handles BOM (Byte Order Mark) from Excel CSVs
    with open(input_file, mode='r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header_skipped = False
        for row in reader:
            if not row or not "".join(row).strip():
                continue
            
            # Pad row to have at least 5 columns
            while len(row) < 5:
                row.append("")
                
            ip_col = row[0].strip()
            mask_col = row[1].strip()
            intf_col = row[2].strip()
            gw_col = row[3].strip()
            comment_col = row[4].strip()
            
            # Skip the header row if it exists (check first valid row for header keywords)
            if not header_skipped:
                header_skipped = True
                if ip_col.lower() == 'subnet' or comment_col.lower() == 'comment':
                    continue
            
            net_ip, net_mask, net_cidr = parse_network(ip_col, mask_col)
            routes.append({
                'ip': net_ip,
                'mask': net_mask,
                'cidr': net_cidr,
                'interface': intf_col,
                'gateway': gw_col,
                'comment': comment_col
            })

    if not routes:
        print("No routes found in the input file.")
        sys.exit(1)

    print(f"Loaded {len(routes)} routes from {input_file}.")
    
    gen_fg_prefix_ans = input("Question 1: Generate Fortigate prefix list? (y/n): ").strip().lower()
    generate_fg_prefix = gen_fg_prefix_ans in ['y', 'yes']
    
    gen_cisco_prefix_ans = input("Question 2: Generate Cisco prefix list? (y/n): ").strip().lower()
    generate_cisco_prefix = gen_cisco_prefix_ans in ['y', 'yes']
    
    prefix_lists = [] # list of tuples: (name, list_of_routes)
    
    # Request the name/grouping suggestion if EITHER Fortigate or Cisco prefix list is selected
    if generate_fg_prefix or generate_cisco_prefix:
        # Group by comment
        groups = {}
        for r in routes:
            c = r['comment'].strip()
            if not c:
                c = "Unnamed_Prefix"
            if c not in groups:
                groups[c] = []
            groups[c].append(r)
        
        print("\nSuggested prefix lists based on comments:")
        suggested = []
        for c, rlist in groups.items():
            chunks = len(rlist) // 20 + (1 if len(rlist) % 20 != 0 else 0)
            if chunks == 1:
                suggested.append(f" - {c}: {len(rlist)} routes -> {c}")
            else:
                suggested.append(f" - {c}: {len(rlist)} routes -> {c}_1 to {c}_{chunks}")
                
        for s in suggested:
            print(s)
            
        use_suggestions = input("Use these suggestions? (y/n): ").strip().lower()
        if use_suggestions in ['y', 'yes']:
            for c, rlist in groups.items():
                chunks = [rlist[i:i + 20] for i in range(0, len(rlist), 20)]
                for idx, chunk in enumerate(chunks):
                    name = c if len(chunks) == 1 else f"{c}_{idx + 1}"
                    prefix_lists.append((name, chunk))
        else:
            prefix_name = input("Enter a single prefix list name for all routes: ").strip()
            chunks = [routes[i:i + 20] for i in range(0, len(routes), 20)]
            for idx, chunk in enumerate(chunks):
                name = prefix_name if len(chunks) == 1 else f"{prefix_name}_{idx + 1}"
                prefix_lists.append((name, chunk))
        
    gen_static_ans = input("\nQuestion 3: Generate Fortigate static route? (y/n): ").strip().lower()
    generate_static = gen_static_ans in ['y', 'yes']
    
    seq_start = 0
    if generate_static:
        while True:
            try:
                seq_start = int(input("Enter sequence number to start from: ").strip())
                break
            except ValueError:
                print("Please enter a valid integer.")

    output_lines = []

    if generate_fg_prefix:
        output_lines.append("! --- Fortigate Prefix Lists ---")
        output_lines.append("config router prefix-list")
        for name, chunk in prefix_lists:
            output_lines.append(f"edit \"{name}\"")
            output_lines.append(f"config rule")
            for r_idx, route in enumerate(chunk, 1):
                output_lines.append(f"edit {r_idx}")
                output_lines.append(f"set prefix {route['ip']} {route['mask']}")
                output_lines.append(f"unset ge")
                output_lines.append(f"unset le")
                output_lines.append(f"next")
            output_lines.append(f"end")
            output_lines.append(f"next")
        output_lines.append("end")
        output_lines.append("")

    if generate_cisco_prefix:
        output_lines.append("! --- Cisco Prefix Lists ---")
        for name, chunk in prefix_lists:
            for r_idx, route in enumerate(chunk, 1):
                # Cisco uses CIDR notation
                output_lines.append(f"ip prefix-list {name} seq {r_idx * 5} permit {route['ip']}/{route['cidr']}")
        output_lines.append("")

    if generate_static:
        output_lines.append("! --- Fortigate Static Routes ---")
        output_lines.append("config router static")
        seq = seq_start
        for route in routes:
            output_lines.append(f"edit {seq}")
            output_lines.append(f"set dst {route['ip']} {route['mask']}")
            
            if route['gateway']:
                output_lines.append(f"set gateway {route['gateway']}")
                
            if route['interface']:
                output_lines.append(f"set device \"{route['interface']}\"")
                    
            if route['comment']:
                output_lines.append(f"set comment \"{route['comment']}\"")
                
            output_lines.append(f"next")
            seq += 1
        output_lines.append("end")

    if not generate_fg_prefix and not generate_cisco_prefix and not generate_static:
        print("No output selected to generate.")
        sys.exit(0)

    # Output to output.csv as requested
    output_filename = 'output.csv'
    with open(output_filename, mode='w', encoding='utf-8', newline='') as f:
        # Writing as a single column CSV avoids issues if comments contain commas
        writer = csv.writer(f)
        for line in output_lines:
            writer.writerow([line])
            
    # Outputting a plain output.txt makes it easier to copy and paste to the router
    with open('output.txt', mode='w', encoding='utf-8') as f:
        for line in output_lines:
            f.write(line + "\n")

    print(f"\nConfiguration has been saved successfully to '{output_filename}' and 'output.txt'.")

if __name__ == "__main__":
    main()
