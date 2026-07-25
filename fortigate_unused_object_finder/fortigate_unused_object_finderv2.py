import os
import re
import ipaddress
import sys
import glob

class IpObject:
    def __init__(self, name, obj_type, raw_lines, subnets):
        self.name = name
        self.obj_type = obj_type
        self.raw_lines = raw_lines
        self.subnets = subnets # list of ipaddress.IPv4Network

    def overlaps_with_any(self, target_subnets):
        for s1 in self.subnets:
            for s2 in target_subnets:
                if s1.overlaps(s2):
                    return True
        return False

def parse_target(target_str):
    target_str = target_str.strip()
    try:
        if '-' in target_str:
            s, e = target_str.split('-')
            return list(ipaddress.summarize_address_range(
                ipaddress.IPv4Address(s.strip()), 
                ipaddress.IPv4Address(e.strip())
            ))
        elif '/' in target_str:
            return [ipaddress.IPv4Network(target_str, strict=False)]
        else:
            return [ipaddress.IPv4Network(f"{target_str}/32", strict=False)]
    except ValueError as e:
        print(f"Error parsing target '{target_str}': {e}")
        return []

def process_edit_block(config_type, name, lines):
    text = "\n".join(lines)
    subnets = []
    try:
        if config_type == 'address':
            m_sub = re.search(r'set\s+subnet\s+([\d\.]+)\s+([\d\.]+)', text)
            if m_sub:
                subnets.append(ipaddress.IPv4Network(f"{m_sub.group(1)}/{m_sub.group(2)}", strict=False))
            
            m_s = re.search(r'set\s+start-ip\s+([\d\.]+)', text)
            m_e = re.search(r'set\s+end-ip\s+([\d\.]+)', text)
            if m_s and m_e:
                subnets.extend(list(ipaddress.summarize_address_range(
                    ipaddress.IPv4Address(m_s.group(1)),
                    ipaddress.IPv4Address(m_e.group(1))
                )))
                
        elif config_type == 'vip':
            m_ext = re.search(r'set\s+extip\s+([\d\.\-\~]+)', text)
            m_map = re.search(r'set\s+mappedip\s+([\d\.\-\~]+)', text)
            for val in [m_ext, m_map]:
                if val:
                    ip_str = val.group(1).replace('~', '-')
                    if '-' in ip_str:
                        start, end = ip_str.split('-')
                        subnets.extend(list(ipaddress.summarize_address_range(
                            ipaddress.IPv4Address(start.strip()),
                            ipaddress.IPv4Address(end.strip())
                        )))
                    else:
                        subnets.append(ipaddress.IPv4Network(f"{ip_str.strip()}/32", strict=False))
                        
        elif config_type == 'ippool':
            m_s = re.search(r'set\s+startip\s+([\d\.]+)', text)
            m_e = re.search(r'set\s+endip\s+([\d\.]+)', text)
            if m_s and m_e:
                subnets.extend(list(ipaddress.summarize_address_range(
                    ipaddress.IPv4Address(m_s.group(1)),
                    ipaddress.IPv4Address(m_e.group(1))
                )))
    except ValueError:
        pass
        
    if subnets:
        return IpObject(name, config_type, lines, subnets)
    return None

def parse_fortigate_objects(filepath):
    ip_objects = []
    
    with open(filepath, 'r', encoding='utf-8-sig', errors='ignore') as f:
        lines = f.readlines()
        
    current_config = None
    current_edit = None
    current_lines = []
    
    re_config = re.compile(r'^\s*config\s+firewall\s+(address|vip|ippool)', re.IGNORECASE)
    re_edit = re.compile(r'^\s*edit\s+"?([^"]+?)"?\s*$', re.IGNORECASE)
    re_next = re.compile(r'^\s*next\s*$', re.IGNORECASE)
    re_end = re.compile(r'^\s*end\s*$', re.IGNORECASE)
    
    for line in lines:
        m_config = re_config.search(line)
        if m_config:
            current_config = m_config.group(1).lower()
            continue
            
        if current_config:
            if re_end.search(line):
                current_config = None
                continue
                
            m_edit = re_edit.search(line)
            if m_edit:
                current_edit = m_edit.group(1)
                current_lines = [line.rstrip()]
                continue
                
            if current_edit:
                current_lines.append(line.rstrip())
                if re_next.search(line):
                    obj = process_edit_block(current_config, current_edit, current_lines)
                    if obj:
                        ip_objects.append(obj)
                    current_edit = None
                    current_lines = []

    return ip_objects

def collapse_ips(ip_list):
    if not ip_list:
        return []
    ranges = []
    start = ip_list[0]
    prev = ip_list[0]
    
    for ip in ip_list[1:]:
        if int(ip) == int(prev) + 1:
            prev = ip
        else:
            if start == prev:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{prev}")
            start = ip
            prev = ip
            
    if start == prev:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{prev}")
    return ranges

def find_unused_ips(target_subnets, ip_objects):
    target_ip_count = sum(net.num_addresses for net in target_subnets)
    if target_ip_count > 65536:
        print(f"Target range is large ({target_ip_count} IPs). Calculating unused IPs might take a moment...")

    # Filter strictly for overlapping networks to avoid processing irrelevant objects
    # This specifically prevents the script from looping through 0.0.0.0/0 (4 billion IPs)
    overlapping_nets = []
    for obj in ip_objects:
        for net in obj.subnets:
            for target_net in target_subnets:
                if net.overlaps(target_net):
                    overlapping_nets.append(net)
                    break 

    # Gather all target IPs
    target_ips = set()
    for net in target_subnets:
        for ip in net:
            target_ips.add(ip)
            
    if not target_ips:
        return []
        
    used_ips = set()
    # It takes millions of times less work to mathematically check if target ip is inside a network block
    for ip in target_ips:
        for net in overlapping_nets:
            if ip in net:
                used_ips.add(ip)
                break
                
    unused = target_ips - used_ips
    
    # Sort IPs
    sorted_unused = sorted(list(unused), key=lambda x: int(x))
    return collapse_ips(sorted_unused)

def main():
    print("=== Fortigate Unused Object Finder ===")
    
    # Find config files
    conf_files = glob.glob("*.conf") + glob.glob("*.txt")
    if not conf_files:
        print("No .conf or .txt files found in the current directory.")
        filepath = input("Please enter the full path to a Fortigate config file: ").strip()
        if not os.path.exists(filepath):
            print("File not found. Exiting.")
            sys.exit(1)
    elif len(conf_files) == 1:
        ans = input(f"Check this file: '{conf_files[0]}'? (y/n): ").strip().lower()
        if ans in ['y', 'yes', '']:
            filepath = conf_files[0]
        else:
            filepath = input("Please enter the path to the config file: ").strip()
    else:
        print("Found multiple config files:")
        for i, f in enumerate(conf_files, 1):
            print(f"  {i}. {f}")
        idx = input("Select a file number (or type full path): ").strip()
        try:
            filepath = conf_files[int(idx)-1]
        except (ValueError, IndexError):
            filepath = idx
            
    if not os.path.exists(filepath):
        print(f"File '{filepath}' not found. Exiting.")
        sys.exit(1)
        
    target_str = input("\nEnter subnet, IP range, or single IP to check (e.g., 10.0.0.0/24 or 10.0.0.10-10.0.0.20): ").strip()
    target_subnets = parse_target(target_str)
    
    if not target_subnets:
        print("Invalid target format. Exiting.")
        sys.exit(1)
        
    print(f"\nParsing {filepath}...")
    ip_objects = parse_fortigate_objects(filepath)
    print(f"Successfully parsed {len(ip_objects)} IP-based objects (address, vip, ippool).\n")
    
    overlapping_objects = []
    for obj in ip_objects:
        if obj.overlaps_with_any(target_subnets):
            overlapping_objects.append(obj)
            
    if not overlapping_objects:
        print(f"No objects found overlapping with {target_str}.")
    else:
        print(f"--- Found {len(overlapping_objects)} Related Objects ---")
        
        # Summary for Console
        summary_info = {'address': [], 'ippool': [], 'vip': []}
        for obj in overlapping_objects:
            if obj.obj_type in summary_info:
                summary_info[obj.obj_type].append(obj.name)
                
        if summary_info['address']:
            print("\nfirewall address :")
            for name in summary_info['address']:
                print(name)
                
        if summary_info['ippool']:
            print("\nsource NAT :")
            for name in summary_info['ippool']:
                print(name)
                
        if summary_info['vip']:
            print("\ndestination NAT :")
            for name in summary_info['vip']:
                print(name)
                
        # Write details to file
        with open("detail.txt", 'w', encoding='utf-8') as f:
            f.write(f"=== Detail Configuration for target: {target_str} ===\n")
            for obj in overlapping_objects:
                f.write(f"\nconfig firewall {obj.obj_type}\n")
                for line in obj.raw_lines:
                    f.write(f"    {line}\n")
                f.write("end\n")
        print("\n(Full configuration blocks have been saved to detail.txt)")
                
    # Calculate Unused IPs
    print("\n--- Unused IPs in Target Range ---")
    
    unused_ranges = find_unused_ips(target_subnets, ip_objects)
    if not unused_ranges:
        print(f"All IPs within {target_str} are CURRENTLY IN USE natively.")
    else:
        print(f"The following IP(s) within {target_str} are NOT natively in use yet:")
        for r in unused_ranges:
            print(f"  - {r}")
            
    print("\nDone.")

if __name__ == "__main__":
    main()
