#!/usr/bin/env python3

import argparse
import os
import glob
import re
import sys


class F5Parser:
    def __init__(self):
        self.gtm_wideips = {}
        self.gtm_pools = {}
        self.gtm_servers = {}
        self.ltm_virtuals = {}
        self.ltm_pools = {}
        self.ltm_nodes = {}
        
    def parse_text(self, text):
        root = {}
        stack = [root]
        
        lines = text.splitlines()
        for raw_line in lines:
            line = raw_line.split('#')[0].strip()
            if not line: continue
            
            # Match quoted strings (handling escaped quotes), braces, or non-whitespace
            tokens = re.findall(r'"(?:\\.|[^"\\])*"|\{|\}|[^\s{}]+', line)
            
            i = 0
            current_cmd = []
            while i < len(tokens):
                token = tokens[i]
                if token == '{':
                    key = " ".join(current_cmd)
                    new_node = {}
                    if key not in stack[-1]:
                        stack[-1][key] = new_node
                    else:
                        existing = stack[-1][key]
                        if isinstance(existing, list):
                            existing.append(new_node)
                        else:
                            stack[-1][key] = [existing, new_node]
                    stack.append(new_node)
                    current_cmd = []
                elif token == '}':
                    if current_cmd:
                        if len(current_cmd) == 1:
                            stack[-1][current_cmd[0]] = ""
                        else:
                            stack[-1][current_cmd[0]] = " ".join(current_cmd[1:])
                        current_cmd = []
                    if len(stack) > 1:
                        stack.pop()
                else:
                    if token.startswith('"') and token.endswith('"'):
                        token = token[1:-1]
                    current_cmd.append(token)
                i += 1
                
            if current_cmd:
                if len(current_cmd) == 1:
                    stack[-1][current_cmd[0]] = ""
                else:
                    stack[-1][current_cmd[0]] = " ".join(current_cmd[1:])
                    
        # Extract parsed objects
        for key, value in root.items():
            items = value if isinstance(value, list) else [value]
            for item in items:
                if key.startswith("gtm wideip "):
                    fqdn = key.split()[-1]
                    self.gtm_wideips[fqdn] = item
                elif key.startswith("gtm pool "):
                    pool_name = key.split()[-1]
                    self.gtm_pools[pool_name] = item
                elif key.startswith("gtm server "):
                    server_name = key[len("gtm server "):].strip()
                    self.gtm_servers[server_name] = item
                elif key.startswith("ltm virtual "):
                    vs_name = key[len("ltm virtual "):].strip()
                    self.ltm_virtuals[vs_name] = item
                elif key.startswith("ltm pool "):
                    pool_name = key[len("ltm pool "):].strip()
                    self.ltm_pools[pool_name] = item
                elif key.startswith("ltm node "):
                    node_name = key[len("ltm node "):].strip()
                    self.ltm_nodes[node_name] = item


def load_configs(config_dir):
    parser = F5Parser()
    if not os.path.exists(config_dir):
        print(f"Error: Config directory '{config_dir}' not found. Please create it and place your F5 configs there.")
        sys.exit(1)
        
    files = glob.glob(os.path.join(config_dir, '**', '*.conf'), recursive=True)
    if not files:
        # Fallback to any file if no .conf is found
        files = [os.path.join(config_dir, f) for f in os.listdir(config_dir) if os.path.isfile(os.path.join(config_dir, f))]
        
    if not files:
        print(f"Warning: No files found in {config_dir}")
        return parser

    for filepath in files:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            parser.parse_text(content)
            
    return parser


def walk_relationships(parser, query_fqdn=None, query_ip=None):
    results = []
    seen_ltm_vs = set()
    
    for fqdn, wideip_data in parser.gtm_wideips.items():
        if query_fqdn and query_fqdn not in fqdn:
            continue
            
        wip_pools = wideip_data.get('pools', {})
        if not wip_pools:
            results.append({
                'fqdn': fqdn, 'gtm_pool': '-', 'gtm_member': '-', 
                'ltm_vs': '-', 'vs_dest': '-', 'ltm_pool': '-', 'ltm_members': []
            })
            continue
            
        for gtm_pool_name, gtm_pool_data in wip_pools.items():
            pool_obj = parser.gtm_pools.get(gtm_pool_name, {})
            pool_members = pool_obj.get('members', {})
            
            if not pool_members:
                results.append({
                    'fqdn': fqdn, 'gtm_pool': gtm_pool_name, 'gtm_member': '-', 
                    'ltm_vs': '-', 'vs_dest': '-', 'ltm_pool': '-', 'ltm_members': []
                })
                continue
                
            for gtm_member_name, gtm_member_data in pool_members.items():
                parts = gtm_member_name.split(':')
                if len(parts) == 2:
                    server_name, vs_name = parts
                else:
                    vs_name = gtm_member_name
                    
                seen_ltm_vs.add(vs_name)
                ltm_vs_obj = parser.ltm_virtuals.get(vs_name, {})
                
                if not ltm_vs_obj:
                    results.append({
                        'fqdn': fqdn, 'gtm_pool': gtm_pool_name, 'gtm_member': gtm_member_name, 
                        'ltm_vs': vs_name + " (Not Found in Config)", 'vs_dest': '-', 'ltm_pool': '-', 'ltm_members': []
                    })
                    continue
                    
                vs_dest = ltm_vs_obj.get('destination', '-')
                ltm_pool_name = ltm_vs_obj.get('pool', '-')
                
                ltm_pool_obj = parser.ltm_pools.get(ltm_pool_name, {})
                ltm_members_dict = ltm_pool_obj.get('members', {})
                ltm_members = list(ltm_members_dict.keys())
                
                results.append({
                    'fqdn': fqdn, 'gtm_pool': gtm_pool_name, 'gtm_member': gtm_member_name,
                    'ltm_vs': vs_name, 'vs_dest': vs_dest, 'ltm_pool': ltm_pool_name, 'ltm_members': ltm_members
                })

    # Add unassociated LTM virtual servers (No GTM WideIP found for them)
    if not query_fqdn:
        for vs_name, ltm_vs_obj in parser.ltm_virtuals.items():
            if vs_name not in seen_ltm_vs:
                vs_dest = ltm_vs_obj.get('destination', '-')
                ltm_pool_name = ltm_vs_obj.get('pool', '-')
                ltm_pool_obj = parser.ltm_pools.get(ltm_pool_name, {})
                ltm_members_dict = ltm_pool_obj.get('members', {})
                ltm_members = list(ltm_members_dict.keys())
                
                results.append({
                    'fqdn': '-', 'gtm_pool': '-', 'gtm_member': '-',
                    'ltm_vs': vs_name, 'vs_dest': vs_dest, 'ltm_pool': ltm_pool_name, 'ltm_members': ltm_members
                })

    # Filter by IP if provided
    if query_ip:
        filtered_results = []
        for r in results:
            if query_ip in r['vs_dest'] or any(query_ip in m for m in r['ltm_members']):
                filtered_results.append(r)
        results = filtered_results
        
    return results


def print_tree(results):
    grouped = {}
    for r in results:
        wip = r['fqdn']
        if wip not in grouped: grouped[wip] = {}
        gpool = r['gtm_pool']
        if gpool not in grouped[wip]: grouped[wip][gpool] = {}
        gmem = r['gtm_member']
        if gmem not in grouped[wip][gpool]: grouped[wip][gpool][gmem] = []
        grouped[wip][gpool][gmem].append(r)
        
    for wip, gpools in grouped.items():
        if wip == "-":
            print(f"Unassociated LTM Virtual Servers (No GTM WideIP matching):")
            for r in gpools.get('-', {}).get('-', []):
                print(f"├── LTM Virtual Server: {r['ltm_vs']} (Destination: {r['vs_dest']})")
                if r['ltm_pool'] != '-':
                    print(f"│   └── LTM Pool: {r['ltm_pool']}")
                    for m_idx, member in enumerate(r['ltm_members']):
                        prefix = "│       └── " if m_idx == len(r['ltm_members']) - 1 else "│       ├── "
                        print(f"{prefix}LTM Node Member: {member}")
            print("")
            continue
            
        print(f"WideIP (FQDN): {wip}")
        gpool_keys = list(gpools.keys())
        for i, gpool in enumerate(gpool_keys):
            gpool_prefix = "└── " if i == len(gpool_keys) - 1 else "├── "
            gpool_child_prefix = "    " if i == len(gpool_keys) - 1 else "│   "
            print(f"{gpool_prefix}GTM Pool: {gpool}")
            
            gmem_keys = list(gpools[gpool].keys())
            for j, gmem in enumerate(gmem_keys):
                gmem_prefix = gpool_child_prefix + ("└── " if j == len(gmem_keys) - 1 else "├── ")
                gmem_child_prefix = gpool_child_prefix + ("    " if j == len(gmem_keys) - 1 else "│   ")
                print(f"{gmem_prefix}GTM Member: {gmem}")
                
                rows = gpools[gpool][gmem]
                for k, r in enumerate(rows):
                    vs_prefix = gmem_child_prefix + ("└── " if k == len(rows) - 1 else "├── ")
                    vs_child_prefix = gmem_child_prefix + ("    " if k == len(rows) - 1 else "│   ")
                    print(f"{vs_prefix}LTM Virtual Server: {r['ltm_vs']} (Destination: {r['vs_dest']})")
                    
                    if r['ltm_pool'] != '-':
                        pool_prefix = vs_child_prefix + "└── "
                        pool_child_prefix = vs_child_prefix + "    "
                        print(f"{pool_prefix}LTM Pool: {r['ltm_pool']}")
                        
                        members = r['ltm_members']
                        for m_idx, member in enumerate(members):
                            m_prefix = pool_child_prefix + ("└── " if m_idx == len(members) - 1 else "├── ")
                            print(f"{m_prefix}LTM Node Member: {member}")
        print("")


def print_table(results):
    print("--- Detailed Flow Table ---")
    headers = ["FQDN", "GTM Pool", "GTM Member", "LTM VS", "VS Dest", "LTM Pool", "LTM Members"]
    widths = [len(h) for h in headers]
    for r in results:
        widths[0] = max(widths[0], len(r['fqdn']))
        widths[1] = max(widths[1], len(r['gtm_pool']))
        widths[2] = max(widths[2], len(r['gtm_member']))
        widths[3] = max(widths[3], len(r['ltm_vs']))
        widths[4] = max(widths[4], len(r['vs_dest']))
        widths[5] = max(widths[5], len(r['ltm_pool']))
        widths[6] = max(widths[6], len(", ".join(r['ltm_members'])))
        
    format_str = " | ".join([f"{{:<{w}}}" for w in widths])
    separator = "-+-".join(["-" * w for w in widths])
    
    print(format_str.format(*headers))
    print(separator)
    for r in results:
        print(format_str.format(
            r['fqdn'], r['gtm_pool'], r['gtm_member'], r['ltm_vs'], 
            r['vs_dest'], r['ltm_pool'], ", ".join(r['ltm_members'])
        ))
        
    print("\n--- Deduplicated Summary Table (WIP -> VIP -> Servers) ---")
    summary = {}
    for r in results:
        fqdn = r['fqdn']
        vip = r['vs_dest']
        # Extract unique servers for this FQDN + VIP pair
        key = (fqdn, vip)
        if key not in summary:
            summary[key] = set()
        for member in r['ltm_members']:
            summary[key].add(member)

    summary_headers = ["Wide IP (WIP)", "Virtual IP (VIP)", "Servers (Nodes)"]
    summary_widths = [len(h) for h in summary_headers]
    summary_rows = []
    
    for (fqdn, vip), servers_set in summary.items():
        servers_str = ", ".join(sorted(servers_set)) if servers_set else "-"
        summary_rows.append((fqdn, vip, servers_str))
        summary_widths[0] = max(summary_widths[0], len(fqdn))
        summary_widths[1] = max(summary_widths[1], len(vip))
        summary_widths[2] = max(summary_widths[2], len(servers_str))

    s_format_str = " | ".join([f"{{:<{w}}}" for w in summary_widths])
    s_separator = "-+-".join(["-" * w for w in summary_widths])

    print(s_format_str.format(*summary_headers))
    print(s_separator)
    # Sort by FQDN, then VIP
    for row in sorted(summary_rows, key=lambda x: (x[0], x[1])):
        print(s_format_str.format(*row))


def main():
    parser = argparse.ArgumentParser(description="F5 GTM/LTM Configuration Parser")
    parser.add_argument("-c", "--config-dir", default="config", help="Directory containing F5 configuration files")
    parser.add_argument("-q", "--query-fqdn", help="Query specific FQDN (substring match)")
    parser.add_argument("-i", "--query-ip", help="Query specific IP (substring match)")
    parser.add_argument("--format", choices=['both', 'tree', 'table'], default='table', help="Output format (default: table)")
    
    args = parser.parse_args()
    
    print(f"Loading F5 configurations from: {args.config_dir}")
    f5_parser = load_configs(args.config_dir)
    
    print(f"Parsed {len(f5_parser.gtm_wideips)} WideIPs, {len(f5_parser.gtm_pools)} GTM Pools, {len(f5_parser.ltm_virtuals)} LTM Virtual Servers")
    
    results = walk_relationships(f5_parser, args.query_fqdn, args.query_ip)
    
    if not results:
        print("No matching configurations found.")
        return
        
    if args.format in ['both', 'tree']:
        print("\n=== Tree View ===")
        print_tree(results)
            
    if args.format in ['both', 'table']:
        print("\n=== Table View ===")
        print_table(results)

if __name__ == "__main__":
    main()
