#!/usr/bin/env python3

import argparse
import os
import glob
import re
import sys
import csv

def normalize_name(name):
    """Strips leading slash and partition prefixes (e.g. '/Common/my_vs' -> 'my_vs') for loose matching."""
    if not name:
        return ""
    clean = name.strip()
    if clean.startswith('/'):
        return clean.split('/')[-1]
    return clean


def find_ltm_virtual(ltm_virtuals, vs_name):
    """Finds an LTM virtual server object handling strict and partition-agnostic matching."""
    if vs_name in ltm_virtuals:
        return ltm_virtuals[vs_name]
    clean_vs = normalize_name(vs_name)
    for k, v in ltm_virtuals.items():
        if k == vs_name or normalize_name(k) == clean_vs:
            return v
    return None


def find_gtm_pool(gtm_pools, pool_name):
    """Finds a GTM pool object handling strict and partition-agnostic matching."""
    if pool_name in gtm_pools:
        return gtm_pools[pool_name]
    clean_pool = normalize_name(pool_name)
    for k, v in gtm_pools.items():
        if k == pool_name or normalize_name(k) == clean_pool:
            return v
    return None


def find_node_ip(parser, node_name):
    """Finds IP address of an LTM node by checking ltm_nodes dictionary or checking if name is an IP."""
    if not node_name:
        return ""
    
    clean_name = normalize_name(node_name)
    
    # 1. Direct lookup in ltm_nodes
    if node_name in parser.ltm_nodes:
        node_obj = parser.ltm_nodes[node_name]
        if isinstance(node_obj, dict) and node_obj.get('address'):
            return node_obj['address']
            
    # 2. Normalized lookup in ltm_nodes
    for k, v in parser.ltm_nodes.items():
        if k == node_name or normalize_name(k) == clean_name:
            if isinstance(v, dict) and v.get('address'):
                return v['address']
                
    # 3. Check if clean_name is itself an IP address (IPv4 or IPv6)
    ip_pattern = r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$|^[0-9a-fA-F:]+$'
    if re.match(ip_pattern, clean_name):
        return clean_name
        
    return ""


def get_ltm_member_details(parser, member_key, member_data=None):
    """
    Extracts member name, node name, server IP, port, and formatted string for an LTM pool member.
    """
    if not member_key:
        return {
            'raw': '', 'node': '', 'ip': '-', 'port': '-', 
            'formatted': '-'
        }
    
    if ':' in member_key:
        node_name, port = member_key.rsplit(':', 1)
    else:
        node_name = member_key
        port = '-'
        
    server_ip = ""
    if isinstance(member_data, dict):
        server_ip = member_data.get('address', '')
        if not port or port == '-':
            port = member_data.get('port', port)
            
    if not server_ip:
        server_ip = find_node_ip(parser, node_name)
        
    if not server_ip:
        server_ip = '-'
        
    if server_ip != '-':
        formatted = f"{member_key} (IP: {server_ip}, Port: {port})"
    else:
        formatted = f"{member_key} (Port: {port})" if port != '-' else member_key

    return {
        'raw': member_key,
        'node': node_name,
        'ip': server_ip,
        'port': port,
        'formatted': formatted
    }


def extract_vs_details(ltm_vs_obj):
    """Extracts SNAT, iRules, Profiles, Persistence, and Description from an LTM Virtual Server config dict."""
    # Extract SNAT
    snat = '-'
    sat = ltm_vs_obj.get('source-address-translation', {})
    if isinstance(sat, dict) and sat:
        stype = sat.get('type', '')
        spool = sat.get('pool', '')
        if stype and spool:
            snat = f"{stype} ({spool})"
        elif stype:
            snat = stype
        elif spool:
            snat = f"pool ({spool})"
        else:
            snat = "enabled"
    elif 'snat' in ltm_vs_obj:
        snat_val = ltm_vs_obj['snat']
        if snat_val:
            snat = str(snat_val)
        else:
            snat = "enabled"
            
    # Extract iRules
    irules_obj = ltm_vs_obj.get('rules', {})
    if isinstance(irules_obj, dict):
        irules = list(irules_obj.keys())
    elif isinstance(irules_obj, str):
        irules = [irules_obj] if irules_obj else []
    else:
        irules = []

    # Extract Profiles (e.g. SSL, HTTP)
    profiles_obj = ltm_vs_obj.get('profiles', {})
    profiles = []
    if isinstance(profiles_obj, dict):
        profiles = list(profiles_obj.keys())
    elif isinstance(profiles_obj, str):
        profiles = [profiles_obj] if profiles_obj else []

    # Extract Persistence
    persist_obj = ltm_vs_obj.get('persist', {})
    persist = '-'
    if isinstance(persist_obj, dict) and persist_obj:
        persist = ", ".join(persist_obj.keys())
    elif isinstance(persist_obj, str) and persist_obj:
        persist = persist_obj

    # Extract Description
    description = ltm_vs_obj.get('description', '-')
        
    return {
        'snat': snat,
        'irules': irules,
        'profiles': profiles,
        'persist': persist,
        'description': description
    }


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
        print(f"Warning: Config directory '{config_dir}' not found.")
        return parser
        
    files = glob.glob(os.path.join(config_dir, '**', '*.conf'), recursive=True)
    if not files:
        files = [os.path.join(config_dir, f) for f in os.listdir(config_dir) if os.path.isfile(os.path.join(config_dir, f))]
        
    if not files:
        print(f"Warning: No configuration files found in {config_dir}")
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
        if query_fqdn and query_fqdn.lower() not in fqdn.lower():
            continue
            
        wip_pools = wideip_data.get('pools', {})
        if not wip_pools:
            results.append({
                'fqdn': fqdn, 'gtm_pool': '-', 'gtm_member': '-', 
                'ltm_vs': '-', 'vs_dest': '-', 'ltm_pool': '-', 'ltm_members': [],
                'snat': '-', 'irules': [], 'profiles': [], 'persist': '-', 'description': '-'
            })
            continue
            
        for gtm_pool_name, gtm_pool_data in wip_pools.items():
            pool_obj = find_gtm_pool(parser.gtm_pools, gtm_pool_name) or {}
            pool_members = pool_obj.get('members', {})
            
            if not pool_members:
                results.append({
                    'fqdn': fqdn, 'gtm_pool': gtm_pool_name, 'gtm_member': '-', 
                    'ltm_vs': '-', 'vs_dest': '-', 'ltm_pool': '-', 'ltm_members': [],
                    'snat': '-', 'irules': [], 'profiles': [], 'persist': '-', 'description': '-'
                })
                continue
                
            for gtm_member_name, gtm_member_data in pool_members.items():
                if ':' in gtm_member_name:
                    parts = gtm_member_name.split(':')
                    server_name = parts[0]
                    vs_name = parts[1]
                else:
                    vs_name = gtm_member_name
                    
                seen_ltm_vs.add(vs_name)
                seen_ltm_vs.add(normalize_name(vs_name))
                
                ltm_vs_obj = find_ltm_virtual(parser.ltm_virtuals, vs_name)
                
                if not ltm_vs_obj:
                    results.append({
                        'fqdn': fqdn, 'gtm_pool': gtm_pool_name, 'gtm_member': gtm_member_name, 
                        'ltm_vs': vs_name + " (Not Found in Config)", 'vs_dest': '-', 'ltm_pool': '-', 'ltm_members': [],
                        'snat': '-', 'irules': [], 'profiles': [], 'persist': '-', 'description': '-'
                    })
                    continue
                    
                vs_dest = ltm_vs_obj.get('destination', '-')
                ltm_pool_name = ltm_vs_obj.get('pool', '-')
                
                ltm_pool_obj = parser.ltm_pools.get(ltm_pool_name, {}) or parser.ltm_pools.get(normalize_name(ltm_pool_name), {})
                ltm_members_dict = ltm_pool_obj.get('members', {}) if isinstance(ltm_pool_obj, dict) else {}
                ltm_members = []
                if isinstance(ltm_members_dict, dict):
                    for m_key, m_val in ltm_members_dict.items():
                        m_details = get_ltm_member_details(parser, m_key, m_val)
                        ltm_members.append(m_details['formatted'])
                elif isinstance(ltm_members_dict, list):
                    for m_key in ltm_members_dict:
                        m_details = get_ltm_member_details(parser, str(m_key))
                        ltm_members.append(m_details['formatted'])
                
                details = extract_vs_details(ltm_vs_obj)
                
                results.append({
                    'fqdn': fqdn, 'gtm_pool': gtm_pool_name, 'gtm_member': gtm_member_name,
                    'ltm_vs': vs_name, 'vs_dest': vs_dest, 'ltm_pool': ltm_pool_name, 'ltm_members': ltm_members,
                    'snat': details['snat'], 'irules': details['irules'], 'profiles': details['profiles'],
                    'persist': details['persist'], 'description': details['description']
                })

    # Add unassociated LTM virtual servers (No GTM WideIP found for them)
    if not query_fqdn:
        for vs_name, ltm_vs_obj in parser.ltm_virtuals.items():
            if vs_name not in seen_ltm_vs and normalize_name(vs_name) not in seen_ltm_vs:
                vs_dest = ltm_vs_obj.get('destination', '-')
                ltm_pool_name = ltm_vs_obj.get('pool', '-')
                ltm_pool_obj = parser.ltm_pools.get(ltm_pool_name, {}) or parser.ltm_pools.get(normalize_name(ltm_pool_name), {})
                ltm_members_dict = ltm_pool_obj.get('members', {}) if isinstance(ltm_pool_obj, dict) else {}
                ltm_members = []
                if isinstance(ltm_members_dict, dict):
                    for m_key, m_val in ltm_members_dict.items():
                        m_details = get_ltm_member_details(parser, m_key, m_val)
                        ltm_members.append(m_details['formatted'])
                elif isinstance(ltm_members_dict, list):
                    for m_key in ltm_members_dict:
                        m_details = get_ltm_member_details(parser, str(m_key))
                        ltm_members.append(m_details['formatted'])
                
                details = extract_vs_details(ltm_vs_obj)
                
                results.append({
                    'fqdn': '-', 'gtm_pool': '-', 'gtm_member': '-',
                    'ltm_vs': vs_name, 'vs_dest': vs_dest, 'ltm_pool': ltm_pool_name, 'ltm_members': ltm_members,
                    'snat': details['snat'], 'irules': details['irules'], 'profiles': details['profiles'],
                    'persist': details['persist'], 'description': details['description']
                })

    # Filter by IP if provided (case-insensitive substring match)
    if query_ip:
        q_ip = query_ip.lower()
        filtered_results = []
        for r in results:
            if q_ip in r['vs_dest'].lower() or any(q_ip in m.lower() for m in r['ltm_members']):
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
                
                vs_children = []
                if r.get('snat') and r['snat'] != '-':
                    vs_children.append({'type': 'snat', 'value': r['snat']})
                for irule in r.get('irules', []):
                    vs_children.append({'type': 'irule', 'value': irule})
                if r.get('profiles'):
                    vs_children.append({'type': 'profile', 'value': ", ".join(r['profiles'])})
                if r['ltm_pool'] != '-':
                    vs_children.append({'type': 'pool', 'value': r['ltm_pool'], 'members': r['ltm_members']})
                
                for c_idx, child in enumerate(vs_children):
                    is_last_child = (c_idx == len(vs_children) - 1)
                    c_prefix = "│   └── " if is_last_child else "│   ├── "
                    c_child_prefix = "│       " if is_last_child else "│   │   "
                    
                    if child['type'] == 'snat':
                        print(f"{c_prefix}SNAT: {child['value']}")
                    elif child['type'] == 'irule':
                        print(f"{c_prefix}iRule: {child['value']}")
                    elif child['type'] == 'profile':
                        print(f"{c_prefix}Profiles: {child['value']}")
                    elif child['type'] == 'pool':
                        print(f"{c_prefix}LTM Pool: {child['value']}")
                        members = child['members']
                        for m_idx, member in enumerate(members):
                            m_prefix = c_child_prefix + ("└── " if m_idx == len(members) - 1 else "├── ")
                            print(f"{m_prefix}LTM Node Member: {member}")
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
                    
                    vs_children = []
                    if r.get('snat') and r['snat'] != '-':
                        vs_children.append({'type': 'snat', 'value': r['snat']})
                    for irule in r.get('irules', []):
                        vs_children.append({'type': 'irule', 'value': irule})
                    if r.get('profiles'):
                        vs_children.append({'type': 'profile', 'value': ", ".join(r['profiles'])})
                    if r['ltm_pool'] != '-':
                        vs_children.append({'type': 'pool', 'value': r['ltm_pool'], 'members': r['ltm_members']})
                        
                    for c_idx, child in enumerate(vs_children):
                        is_last_child = (c_idx == len(vs_children) - 1)
                        c_prefix = vs_child_prefix + ("└── " if is_last_child else "├── ")
                        c_child_prefix = vs_child_prefix + ("    " if is_last_child else "│   ")
                        
                        if child['type'] == 'snat':
                            print(f"{c_prefix}SNAT: {child['value']}")
                        elif child['type'] == 'irule':
                            print(f"{c_prefix}iRule: {child['value']}")
                        elif child['type'] == 'profile':
                            print(f"{c_prefix}Profiles: {child['value']}")
                        elif child['type'] == 'pool':
                            print(f"{c_prefix}LTM Pool: {child['value']}")
                            members = child['members']
                            for m_idx, member in enumerate(members):
                                m_prefix = c_child_prefix + ("└── " if m_idx == len(members) - 1 else "├── ")
                                print(f"{m_prefix}LTM Node Member: {member}")
        print("")


def export_csv(results, filepath, mode='both'):
    """Exports results to CSV. Mode can be 'detail', 'summary', or 'both'."""
    headers = ["FQDN", "GTM Pool", "GTM Member", "LTM VS", "VS Dest", "SNAT", "iRules", "Profiles", "LTM Pool", "LTM Members"]
    
    # Detail Export
    if mode in ['detail', 'both']:
        detail_path = filepath if mode == 'detail' else (filepath[:-4] + "_detail.csv" if filepath.endswith(".csv") else filepath + "_detail.csv")
        try:
            with open(detail_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in results:
                    irules_str = ", ".join(r.get('irules', [])) if r.get('irules') else "-"
                    profiles_str = ", ".join(r.get('profiles', [])) if r.get('profiles') else "-"
                    members_str = ", ".join(r['ltm_members']) if r['ltm_members'] else "-"
                    writer.writerow([
                        r['fqdn'], r['gtm_pool'], r['gtm_member'], r['ltm_vs'], 
                        r['vs_dest'], r.get('snat', '-'), irules_str, profiles_str, r['ltm_pool'], members_str
                    ])
            print(f"\nDetailed Flow CSV exported to: {detail_path}")
        except Exception as e:
            print(f"\nError exporting Detail CSV to {detail_path}: {e}")

    # Summary Export
    if mode in ['summary', 'both']:
        summary_path = filepath if mode == 'summary' else (filepath[:-4] + "_summary.csv" if filepath.endswith(".csv") else filepath + "_summary.csv")
        summary = {}
        for r in results:
            fqdn = r['fqdn']
            vip = r['vs_dest']
            key = (fqdn, vip)
            if key not in summary:
                summary[key] = set()
            for member in r['ltm_members']:
                summary[key].add(member)
        try:
            with open(summary_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Wide IP (WIP)", "Virtual IP (VIP)", "Servers (Nodes)"])
                for (fqdn, vip), servers_set in sorted(summary.items(), key=lambda x: (x[0][0], x[0][1])):
                    servers_str = ", ".join(sorted(servers_set)) if servers_set else "-"
                    writer.writerow([fqdn, vip, servers_str])
            print(f"Summary Table CSV exported to: {summary_path}")
        except Exception as e:
            print(f"\nError exporting Summary CSV to {summary_path}: {e}")


def print_table(results):
    print("--- Detailed Flow Table ---")
    headers = ["FQDN", "GTM Pool", "GTM Member", "LTM VS", "VS Dest", "SNAT", "iRules", "LTM Pool", "LTM Members"]
    widths = [len(h) for h in headers]
    for r in results:
        widths[0] = max(widths[0], len(r['fqdn']))
        widths[1] = max(widths[1], len(r['gtm_pool']))
        widths[2] = max(widths[2], len(r['gtm_member']))
        widths[3] = max(widths[3], len(r['ltm_vs']))
        widths[4] = max(widths[4], len(r['vs_dest']))
        widths[5] = max(widths[5], len(r.get('snat', '-')))
        irules_str = ", ".join(r.get('irules', [])) if r.get('irules') else "-"
        widths[6] = max(widths[6], len(irules_str))
        widths[7] = max(widths[7], len(r['ltm_pool']))
        members_str = ", ".join(r['ltm_members']) if r['ltm_members'] else "-"
        widths[8] = max(widths[8], len(members_str))
        
    format_str = " | ".join([f"{{:<{w}}}" for w in widths])
    separator = "-+-".join(["-" * w for w in widths])
    
    print(format_str.format(*headers))
    print(separator)
    for r in results:
        irules_str = ", ".join(r.get('irules', [])) if r.get('irules') else "-"
        members_str = ", ".join(r['ltm_members']) if r['ltm_members'] else "-"
        print(format_str.format(
            r['fqdn'], r['gtm_pool'], r['gtm_member'], r['ltm_vs'], 
            r['vs_dest'], r.get('snat', '-'), irules_str, r['ltm_pool'], members_str
        ))
        
    print("\n--- Deduplicated Summary Table (WIP -> VIP -> Servers) ---")
    summary = {}
    for r in results:
        fqdn = r['fqdn']
        vip = r['vs_dest']
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
    for row in sorted(summary_rows, key=lambda x: (x[0], x[1])):
        print(s_format_str.format(*row))


def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    class F5QueryApp(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title("F5 GTM/LTM Configuration Parser & Visualizer")
            self.geometry("1150x720")

            self.f5_parser = None
            self.current_results = []
            self.search_timer = None

            self._create_widgets()

        def _create_widgets(self):
            # Top Control Panel
            ctrl_frame = ttk.LabelFrame(self, text=" Configuration & Search ")
            ctrl_frame.pack(fill=tk.X, padx=10, pady=5)

            # Row 1: Folder Selection
            ttk.Label(ctrl_frame, text="Config Dir:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
            self.dir_var = tk.StringVar(value="config")
            dir_entry = ttk.Entry(ctrl_frame, textvariable=self.dir_var, width=50)
            dir_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)

            browse_btn = ttk.Button(ctrl_frame, text="Browse...", command=self.browse_dir)
            browse_btn.grid(row=0, column=2, padx=5, pady=5)

            load_btn = ttk.Button(ctrl_frame, text="Load & Parse Configs", command=self.load_configs_gui)
            load_btn.grid(row=0, column=3, padx=5, pady=5)

            # Row 2: Filter Options
            ttk.Label(ctrl_frame, text="Filter FQDN:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
            self.fqdn_var = tk.StringVar()
            fqdn_entry = ttk.Entry(ctrl_frame, textvariable=self.fqdn_var, width=25)
            fqdn_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
            fqdn_entry.bind("<KeyRelease>", self.on_filter_key)
            fqdn_entry.bind("<Return>", lambda e: self.apply_filter())

            ttk.Label(ctrl_frame, text="Filter IP:").grid(row=1, column=2, padx=5, pady=5, sticky=tk.E)
            self.ip_var = tk.StringVar()
            ip_entry = ttk.Entry(ctrl_frame, textvariable=self.ip_var, width=20)
            ip_entry.grid(row=1, column=3, padx=5, pady=5, sticky=tk.W)
            ip_entry.bind("<KeyRelease>", self.on_filter_key)
            ip_entry.bind("<Return>", lambda e: self.apply_filter())

            btn_subframe = ttk.Frame(ctrl_frame)
            btn_subframe.grid(row=1, column=4, padx=5, pady=5, sticky=tk.E)

            filter_btn = ttk.Button(btn_subframe, text="Search", command=self.apply_filter)
            filter_btn.pack(side=tk.LEFT, padx=2)

            clear_btn = ttk.Button(btn_subframe, text="Reset", command=self.reset_filter)
            clear_btn.pack(side=tk.LEFT, padx=2)

            export_btn = ttk.Button(btn_subframe, text="Export CSV", command=self.export_csv_gui)
            export_btn.pack(side=tk.LEFT, padx=5)

            ctrl_frame.columnconfigure(1, weight=1)

            # Notebook Tabs
            self.notebook = ttk.Notebook(self)
            self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

            # Tab 1: Tree View
            self.tree_tab = ttk.Frame(self.notebook)
            self.notebook.add(self.tree_tab, text="Visual Tree Mapping")
            self._setup_tree_tab()

            # Tab 2: Detailed Flow Table View
            self.detail_tab = ttk.Frame(self.notebook)
            self.notebook.add(self.detail_tab, text="Detailed Flow Table")
            self._setup_detail_tab()

            # Tab 3: Deduplicated Summary View
            self.summary_tab = ttk.Frame(self.notebook)
            self.notebook.add(self.summary_tab, text="Summary Table (WIP -> VIP -> Servers)")
            self._setup_summary_tab()

            # Status Bar
            self.status_var = tk.StringVar(value="Ready. Select config directory and click 'Load & Parse Configs'.")
            status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=3)
            status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        def browse_dir(self):
            selected = filedialog.askdirectory(initialdir=self.dir_var.get() or ".")
            if selected:
                self.dir_var.set(selected)

        def on_filter_key(self, event=None):
            if self.search_timer:
                self.after_cancel(self.search_timer)
            self.search_timer = self.after(350, self.apply_filter)

        def load_configs_gui(self):
            config_dir = self.dir_var.get().strip()
            if not os.path.exists(config_dir):
                messagebox.showerror("Error", f"Directory '{config_dir}' does not exist.")
                return

            self.f5_parser = load_configs(config_dir)
            wips_count = len(self.f5_parser.gtm_wideips)
            gpools_count = len(self.f5_parser.gtm_pools)
            vss_count = len(self.f5_parser.ltm_virtuals)

            self.status_var.set(f"Loaded: {wips_count} WideIPs, {gpools_count} GTM Pools, {vss_count} LTM Virtual Servers from '{config_dir}'")
            self.apply_filter()

        def apply_filter(self):
            if not self.f5_parser:
                config_dir = self.dir_var.get().strip()
                if os.path.exists(config_dir):
                    self.load_configs_gui()
                if not self.f5_parser:
                    return

            fqdn = self.fqdn_var.get().strip() or None
            ip = self.ip_var.get().strip() or None

            self.current_results = walk_relationships(self.f5_parser, query_fqdn=fqdn, query_ip=ip)
            self.populate_views()

        def reset_filter(self):
            self.fqdn_var.set("")
            self.ip_var.set("")
            self.apply_filter()

        def populate_views(self):
            self.populate_tree_view()
            self.populate_detail_view()
            self.populate_summary_view()
            self.status_var.set(f"Displaying {len(self.current_results)} mapped relationship entries.")

        def _setup_tree_tab(self):
            frame = ttk.Frame(self.tree_tab)
            frame.pack(fill=tk.BOTH, expand=True)

            toolbar = ttk.Frame(frame)
            toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(2, 4), padx=2)
            ttk.Button(toolbar, text="➕ Expand All", command=self.expand_all_tree).pack(side=tk.LEFT, padx=2)
            ttk.Button(toolbar, text="➖ Collapse All", command=self.collapse_all_tree).pack(side=tk.LEFT, padx=2)

            self.visual_tree = ttk.Treeview(frame, columns=("info",), selectmode="browse")
            self.visual_tree.heading("#0", text="F5 Hierarchy Element", anchor=tk.W)
            self.visual_tree.heading("info", text="Details / Destination", anchor=tk.W)
            self.visual_tree.column("#0", width=480, stretch=True)
            self.visual_tree.column("info", width=550, stretch=True)

            # Style tag colors
            self.visual_tree.tag_configure("wip", foreground="#0275d8")
            self.visual_tree.tag_configure("vs", foreground="#2e7d32")
            self.visual_tree.tag_configure("not_found", foreground="#d9534f")
            self.visual_tree.tag_configure("snat", foreground="#d97706")
            self.visual_tree.tag_configure("irule", foreground="#6b21a8")
            self.visual_tree.tag_configure("profile", foreground="#4b5563")

            vsb = ttk.Scrollbar(frame, orient="vertical", command=self.visual_tree.yview)
            hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.visual_tree.xview)
            self.visual_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

            self.visual_tree.grid(row=1, column=0, sticky="nsew")
            vsb.grid(row=1, column=1, sticky="ns")
            hsb.grid(row=2, column=0, sticky="ew")

            frame.rowconfigure(1, weight=1)
            frame.columnconfigure(0, weight=1)

        def expand_all_tree(self):
            def _expand(item=""):
                for child in self.visual_tree.get_children(item):
                    self.visual_tree.item(child, open=True)
                    _expand(child)
            _expand()

        def collapse_all_tree(self):
            def _collapse(item=""):
                for child in self.visual_tree.get_children(item):
                    self.visual_tree.item(child, open=False)
                    _collapse(child)
            _collapse()

        def populate_tree_view(self):
            for item in self.visual_tree.get_children():
                self.visual_tree.delete(item)

            grouped = {}
            for r in self.current_results:
                wip = r['fqdn']
                if wip not in grouped: grouped[wip] = {}
                gpool = r['gtm_pool']
                if gpool not in grouped[wip]: grouped[wip][gpool] = {}
                gmem = r['gtm_member']
                if gmem not in grouped[wip][gpool]: grouped[wip][gpool][gmem] = []
                grouped[wip][gpool][gmem].append(r)

            for wip, gpools in grouped.items():
                if wip == "-":
                    unassoc_node = self.visual_tree.insert("", tk.END, text="Unassociated LTM Virtual Servers", values=("No GTM WideIP matching",), open=True, tags=("not_found",))
                    for r in gpools.get('-', {}).get('-', []):
                        vs_node = self.visual_tree.insert(unassoc_node, tk.END, text=f"LTM VS: {r['ltm_vs']}", values=(f"Dest: {r['vs_dest']}",), open=True, tags=("vs",))
                        if r.get('snat') and r['snat'] != '-':
                            self.visual_tree.insert(vs_node, tk.END, text="SNAT", values=(r['snat'],), tags=("snat",))
                        for irule in r.get('irules', []):
                            self.visual_tree.insert(vs_node, tk.END, text="iRule", values=(irule,), tags=("irule",))
                        if r.get('profiles'):
                            self.visual_tree.insert(vs_node, tk.END, text="Profiles", values=(", ".join(r['profiles']),), tags=("profile",))
                        if r['ltm_pool'] != '-':
                            pool_node = self.visual_tree.insert(vs_node, tk.END, text=f"LTM Pool: {r['ltm_pool']}", values=("",), open=True)
                            for member in r['ltm_members']:
                                self.visual_tree.insert(pool_node, tk.END, text=f"Member: {member}", values=("",))
                    continue

                wip_node = self.visual_tree.insert("", tk.END, text=f"WideIP (FQDN): {wip}", values=("",), open=True, tags=("wip",))
                for gpool, gmems in gpools.items():
                    gpool_node = self.visual_tree.insert(wip_node, tk.END, text=f"GTM Pool: {gpool}", values=("",), open=True)
                    for gmem, rows in gmems.items():
                        gmem_node = self.visual_tree.insert(gpool_node, tk.END, text=f"GTM Member: {gmem}", values=("",), open=True)
                        for r in rows:
                            is_not_found = "Not Found" in r['ltm_vs']
                            vs_tag = "not_found" if is_not_found else "vs"
                            vs_node = self.visual_tree.insert(gmem_node, tk.END, text=f"LTM VS: {r['ltm_vs']}", values=(f"Dest: {r['vs_dest']}",), open=True, tags=(vs_tag,))
                            if r.get('snat') and r['snat'] != '-':
                                self.visual_tree.insert(vs_node, tk.END, text="SNAT", values=(r['snat'],), tags=("snat",))
                            for irule in r.get('irules', []):
                                self.visual_tree.insert(vs_node, tk.END, text="iRule", values=(irule,), tags=("irule",))
                            if r.get('profiles'):
                                self.visual_tree.insert(vs_node, tk.END, text="Profiles", values=(", ".join(r['profiles']),), tags=("profile",))
                            if r['ltm_pool'] != '-':
                                pool_node = self.visual_tree.insert(vs_node, tk.END, text=f"LTM Pool: {r['ltm_pool']}", values=("",), open=True)
                                for member in r['ltm_members']:
                                    self.visual_tree.insert(pool_node, tk.END, text=f"Member: {member}", values=("",))

        def _setup_detail_tab(self):
            frame = ttk.Frame(self.detail_tab)
            frame.pack(fill=tk.BOTH, expand=True)

            headers = ["FQDN", "GTM Pool", "GTM Member", "LTM VS", "VS Dest", "SNAT", "iRules", "Profiles", "LTM Pool", "LTM Members"]
            self.detail_tree = ttk.Treeview(frame, columns=headers, show="headings", selectmode="browse")

            for h in headers:
                self.detail_tree.heading(h, text=h, anchor=tk.W, command=lambda _h=h: self.sort_column(self.detail_tree, _h, False))
                self.detail_tree.column(h, width=105, stretch=True)

            vsb = ttk.Scrollbar(frame, orient="vertical", command=self.detail_tree.yview)
            hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.detail_tree.xview)
            self.detail_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

            self.detail_tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")

            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)

        def populate_detail_view(self):
            for item in self.detail_tree.get_children():
                self.detail_tree.delete(item)

            for r in self.current_results:
                irules_str = ", ".join(r.get('irules', [])) if r.get('irules') else "-"
                profiles_str = ", ".join(r.get('profiles', [])) if r.get('profiles') else "-"
                members_str = ", ".join(r['ltm_members']) if r['ltm_members'] else "-"
                self.detail_tree.insert("", tk.END, values=(
                    r['fqdn'], r['gtm_pool'], r['gtm_member'], r['ltm_vs'], 
                    r['vs_dest'], r.get('snat', '-'), irules_str, profiles_str, r['ltm_pool'], members_str
                ))

        def _setup_summary_tab(self):
            frame = ttk.Frame(self.summary_tab)
            frame.pack(fill=tk.BOTH, expand=True)

            headers = ["Wide IP (WIP)", "Virtual IP (VIP)", "Servers (Nodes)"]
            self.summary_tree = ttk.Treeview(frame, columns=headers, show="headings", selectmode="browse")

            for h in headers:
                self.summary_tree.heading(h, text=h, anchor=tk.W, command=lambda _h=h: self.sort_column(self.summary_tree, _h, False))
                self.summary_tree.column(h, width=300, stretch=True)

            vsb = ttk.Scrollbar(frame, orient="vertical", command=self.summary_tree.yview)
            hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.summary_tree.xview)
            self.summary_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

            self.summary_tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")

            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)

        def populate_summary_view(self):
            for item in self.summary_tree.get_children():
                self.summary_tree.delete(item)

            summary = {}
            for r in self.current_results:
                fqdn = r['fqdn']
                vip = r['vs_dest']
                key = (fqdn, vip)
                if key not in summary:
                    summary[key] = set()
                for member in r['ltm_members']:
                    summary[key].add(member)

            summary_rows = []
            for (fqdn, vip), servers_set in summary.items():
                servers_str = ", ".join(sorted(servers_set)) if servers_set else "-"
                summary_rows.append((fqdn, vip, servers_str))

            for row in sorted(summary_rows, key=lambda x: (x[0], x[1])):
                self.summary_tree.insert("", tk.END, values=row)

        def sort_column(self, tree, col, reverse):
            l = [(tree.set(k, col), k) for k in tree.get_children('')]
            l.sort(key=lambda x: x[0].lower(), reverse=reverse)
            for index, (val, k) in enumerate(l):
                tree.move(k, '', index)
            tree.heading(col, command=lambda: self.sort_column(tree, col, not reverse))

        def export_csv_gui(self):
            if not self.current_results:
                messagebox.showwarning("Warning", "No results to export.")
                return

            filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
            if filepath:
                export_csv(self.current_results, filepath, mode='both')
                messagebox.showinfo("Export Successful", f"Both Detailed & Summary CSV tables exported to:\n{filepath}")

    app = F5QueryApp()
    app.mainloop()


def main_cli(args=None):
    parser = argparse.ArgumentParser(description="F5 GTM/LTM Configuration Parser")
    parser.add_argument("-c", "--config-dir", default="config", help="Directory containing F5 configuration files")
    parser.add_argument("-q", "--query-fqdn", help="Query specific FQDN (substring match)")
    parser.add_argument("-i", "--query-ip", help="Query specific IP (substring match)")
    parser.add_argument("--format", choices=['both', 'tree', 'table'], default='table', help="Output format (default: table)")
    parser.add_argument("--csv", help="Export CSV tables to this file path prefix (e.g. output.csv)")
    parser.add_argument("--cli", action="store_true", help="Force CLI mode")
    parser.add_argument("--gui", action="store_true", help="Force GUI mode")
    
    parsed_args = parser.parse_args(args)
    
    print(f"Loading F5 configurations from: {parsed_args.config_dir}")
    f5_parser = load_configs(parsed_args.config_dir)
    
    print(f"Parsed {len(f5_parser.gtm_wideips)} WideIPs, {len(f5_parser.gtm_pools)} GTM Pools, {len(f5_parser.ltm_virtuals)} LTM Virtual Servers")
    
    results = walk_relationships(f5_parser, parsed_args.query_fqdn, parsed_args.query_ip)
    
    if not results:
        print("No matching configurations found.")
        return
        
    if parsed_args.format in ['both', 'tree']:
        print("\n=== Tree View ===")
        print_tree(results)
            
    if parsed_args.format in ['both', 'table']:
        print("\n=== Table View ===")
        print_table(results)

    if parsed_args.csv:
        export_csv(results, parsed_args.csv, mode='both')


def main():
    force_cli = "--cli" in sys.argv or "-h" in sys.argv or "--help" in sys.argv
    has_cli_args = any(arg in sys.argv for arg in ["-c", "--config-dir", "-q", "--query-fqdn", "-i", "--query-ip", "--format", "--csv"])
    force_gui = "--gui" in sys.argv

    if force_cli or (has_cli_args and not force_gui):
        main_cli()
    else:
        try:
            run_gui()
        except Exception as e:
            print(f"[Fallback to CLI] Unable to start GUI interface: {e}")
            print("Running in CLI mode instead...\n")
            main_cli()


if __name__ == "__main__":
    main()
