#!/usr/bin/env python3

import argparse
import os
import glob
import re
import sys
import csv
import subprocess
import platform
import threading


def clean_target_address(target_str):
    """
    Strips F5 partition prefix (e.g. '/Common/'), route domain (%1), and port (:80, :443, :http)
    from a WIP hostname or VIP destination IP/name.
    """
    if not target_str or target_str == '-':
        return ""
    clean = target_str.strip()
    if clean.startswith('/'):
        clean = clean.split('/')[-1]
    
    if clean.startswith('['):
        end_bracket = clean.find(']')
        if end_bracket != -1:
            clean = clean[1:end_bracket]
    else:
        if '%' in clean:
            clean = re.sub(r'%\d+', '', clean)
        if ':' in clean:
            clean = clean.split(':')[0]
            
    return clean.strip()


def ping_target(target, count=2, timeout_sec=2):
    """
    Pings a WIP hostname or VIP address and returns (success: bool, target: str, summary: str, details: str).
    """
    cleaned = clean_target_address(target)
    if not cleaned:
        return False, target, "Invalid target address", "Address is empty or invalid."
    
    is_win = platform.system().lower() == 'windows'
    param_n = '-n' if is_win else '-c'
    param_w = '-w' if is_win else ('-W' if platform.system().lower() == 'darwin' else '-w')
    timeout_val = str(timeout_sec * 1000) if is_win else str(timeout_sec)
    
    cmd = ['ping', param_n, str(count), param_w, timeout_val, cleaned]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_sec + 3)
        output = res.stdout or res.stderr or ""
        if res.returncode == 0:
            rtt_match = re.search(r'(?:Average|avg|rtt)[^=]*=\s*([0-9\.\/]+)', output, re.IGNORECASE)
            avg_str = f" ({rtt_match.group(1)} ms)" if rtt_match else ""
            return True, cleaned, f"SUCCESS: {cleaned} is reachable{avg_str}", output
        else:
            return False, cleaned, f"FAILED: {cleaned} is unreachable", output
    except subprocess.TimeoutExpired:
        return False, cleaned, f"TIMEOUT: {cleaned} ping request timed out", "Ping command timed out."
    except Exception as e:
        return False, cleaned, f"ERROR: {e}", str(e)


def normalize_name(name):
    """
    Strips leading slash, partition prefixes (e.g. '/Common/my_vs' -> 'my_vs'),
    and route domain suffixes (e.g. 'my_vs%1' -> 'my_vs', '10.1.1.1%2' -> '10.1.1.1') for loose matching.
    """
    if not name:
        return ""
    clean = str(name).strip()
    if clean.startswith('/'):
        clean = clean.split('/')[-1]
    clean = re.sub(r'%\d+', '', clean)
    return clean.strip()


def find_ltm_virtual(ltm_virtuals, vs_name):
    """
    Finds an LTM virtual server object handling strict, partition-agnostic, route-domain-agnostic (%1, %2),
    and destination IP matching. Returns (matched_key, ltm_vs_obj) or (None, None).
    """
    if not vs_name:
        return None, None
        
    # 1. Direct key lookup
    if vs_name in ltm_virtuals:
        return vs_name, ltm_virtuals[vs_name]
        
    clean_vs = normalize_name(vs_name)
    
    # 2. Normalized name lookup (partition & route domain agnostic)
    for k, v in ltm_virtuals.items():
        if k == vs_name or normalize_name(k) == clean_vs:
            return k, v

    # 3. Destination IP / target address lookup
    target_ip = clean_target_address(vs_name)
    if target_ip:
        for k, v in ltm_virtuals.items():
            if isinstance(v, dict) and 'destination' in v:
                dest_ip = clean_target_address(v['destination'])
                if dest_ip and dest_ip == target_ip:
                    return k, v
                    
    return None, None


def find_gtm_pool(gtm_pools, pool_name):
    """Finds a GTM pool object handling strict, partition-agnostic, and route-domain-agnostic matching."""
    if not pool_name:
        return None
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
            return clean_target_address(node_obj['address']) or node_obj['address']
            
    # 2. Normalized lookup in ltm_nodes
    for k, v in parser.ltm_nodes.items():
        if k == node_name or normalize_name(k) == clean_name:
            if isinstance(v, dict) and v.get('address'):
                return clean_target_address(v['address']) or v['address']
                
    # 3. Check if clean_name is itself an IP address (IPv4 or IPv6)
    target_ip = clean_target_address(clean_name)
    ip_pattern = r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$|^[0-9a-fA-F:]+$'
    if target_ip and re.match(ip_pattern, target_ip):
        return target_ip
        
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
        self.files_scanned = 0
        self.ltm_files_count = 0
        self.gtm_files_count = 0
        # Track source filename and hostname for every named object
        self.object_source_file = {}   # object_name -> source filename
        self.object_hostname = {}      # object_name -> hostname from config
        
    def parse_text(self, text, source_file=None, hostname=None):
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
                key_clean = key.strip()
                tokens = key_clean.split()
                if not tokens: continue

                obj_name = None

                # GTM WideIP: 'gtm wideip ...' or 'wideip ...'
                if (key_clean.startswith("gtm wideip ") or key_clean.startswith("wideip ")) and len(tokens) >= 2:
                    fqdn = tokens[-1]
                    self.gtm_wideips[fqdn] = item
                    obj_name = fqdn
                # GTM Pool: 'gtm pool ...'
                elif key_clean.startswith("gtm pool ") and len(tokens) >= 2:
                    pool_name = tokens[-1]
                    self.gtm_pools[pool_name] = item
                    obj_name = pool_name
                # GTM Server: 'gtm server ...'
                elif key_clean.startswith("gtm server "):
                    server_name = key_clean[len("gtm server "):].strip()
                    self.gtm_servers[server_name] = item
                    obj_name = server_name
                # LTM Virtual: 'ltm virtual ...' or 'virtual ...' (excluding virtual-address)
                elif (key_clean.startswith("ltm virtual ") or key_clean.startswith("virtual ")) and not ("virtual-address" in key_clean):
                    if key_clean.startswith("ltm virtual "):
                        vs_name = key_clean[len("ltm virtual "):].strip()
                    else:
                        vs_name = key_clean[len("virtual "):].strip()
                    self.ltm_virtuals[vs_name] = item
                    obj_name = vs_name
                # LTM Pool: 'ltm pool ...' or 'pool ...'
                elif key_clean.startswith("ltm pool ") or (key_clean.startswith("pool ") and not key_clean.startswith("gtm pool ")):
                    if key_clean.startswith("ltm pool "):
                        pool_name = key_clean[len("ltm pool "):].strip()
                    else:
                        pool_name = key_clean[len("pool "):].strip()
                    self.ltm_pools[pool_name] = item
                    obj_name = pool_name
                # LTM Node: 'ltm node ...' or 'node ...'
                elif key_clean.startswith("ltm node ") or key_clean.startswith("node "):
                    if key_clean.startswith("ltm node "):
                        node_name = key_clean[len("ltm node "):].strip()
                    else:
                        node_name = key_clean[len("node "):].strip()
                    self.ltm_nodes[node_name] = item
                    obj_name = node_name

                if obj_name:
                    if source_file:
                        self.object_source_file[obj_name] = source_file
                    if hostname:
                        self.object_hostname[obj_name] = hostname


def load_configs(config_dir):
    parser = F5Parser()
    if not config_dir or not os.path.exists(config_dir):
        print(f"Warning: Config path '{config_dir}' not found.")
        return parser
        
    files = []
    if os.path.isfile(config_dir):
        files = [config_dir]
    else:
        for root, dirs, filenames in os.walk(config_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for f in filenames:
                if f.startswith('.') or f.endswith('.py') or f.endswith('.pyc') or f.endswith('.csv'):
                    continue
                files.append(os.path.join(root, f))
        files.sort()

    if not files:
        print(f"Warning: No configuration files found in {config_dir}")
        return parser

    parser.files_scanned = len(files)
    parser.ltm_files_count = 0
    parser.gtm_files_count = 0

    for filepath in files:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Extract hostname from config file (sys global-settings or sys management-ip hostname)
            hostname = None
            hm = re.search(r'sys\s+global-settings\s*\{[^}]*hostname\s+(\S+)', content, re.IGNORECASE | re.DOTALL)
            if hm:
                hostname = hm.group(1).strip()
            if not hostname:
                hm2 = re.search(r'sys\s+management-ip\s+\S+\s*\{[^}]*hostname\s+(\S+)', content, re.IGNORECASE | re.DOTALL)
                if hm2:
                    hostname = hm2.group(1).strip()
            if not hostname:
                # Try 'hostname <value>' as a top-level standalone directive
                hm3 = re.search(r'^\s*hostname\s+(\S+)', content, re.IGNORECASE | re.MULTILINE)
                if hm3:
                    hostname = hm3.group(1).strip()

            source_file = os.path.basename(filepath)

            prev_gtm = len(parser.gtm_wideips) + len(parser.gtm_pools) + len(parser.gtm_servers)
            prev_ltm = len(parser.ltm_virtuals) + len(parser.ltm_pools) + len(parser.ltm_nodes)

            parser.parse_text(content, source_file=source_file, hostname=hostname)

            new_gtm = len(parser.gtm_wideips) + len(parser.gtm_pools) + len(parser.gtm_servers)
            new_ltm = len(parser.ltm_virtuals) + len(parser.ltm_pools) + len(parser.ltm_nodes)

            is_gtm = (new_gtm > prev_gtm) or bool(re.search(r'\bgtm\b|\bwideip\b', content, re.IGNORECASE))
            is_ltm = (new_ltm > prev_ltm) or bool(re.search(r'\bltm\b|\bvirtual\b', content, re.IGNORECASE))

            if is_gtm:
                parser.gtm_files_count += 1
            if is_ltm:
                parser.ltm_files_count += 1
        except Exception as e:
            print(f"Error loading file {filepath}: {e}")

    return parser


def extract_name_dict(data):
    """
    Safely converts dict, str, list, or None objects into a dict mapping of {item_name: item_data_dict_or_str}.
    Handles inline F5 config syntax (e.g. pools /Common/pool_gtm or pools { /Common/pool_gtm { } }).
    """
    if not data:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        clean = data.strip()
        if not clean:
            return {}
        items = clean.split()
        return {item: {} for item in items}
    if isinstance(data, list):
        result = {}
        for elem in data:
            if isinstance(elem, dict):
                result.update(elem)
            elif isinstance(elem, str):
                for item in elem.strip().split():
                    result[item] = {}
        return result
    return {}


def _get_obj_source(parser, *names):
    """Returns (source_file, hostname) for the first name found in object_source_file."""
    for name in names:
        if name and name in parser.object_source_file:
            sf = parser.object_source_file.get(name, '-')
            hn = parser.object_hostname.get(name, '-')
            return sf or '-', hn or '-'
        norm = normalize_name(name) if name else ''
        if norm and norm in parser.object_source_file:
            sf = parser.object_source_file.get(norm, '-')
            hn = parser.object_hostname.get(norm, '-')
            return sf or '-', hn or '-'
    return '-', '-'


def walk_relationships(parser, query_fqdn=None, query_ip=None, query_file=None, query_host=None):
    results = []
    seen_ltm_vs = set()
    
    for fqdn, wideip_data in parser.gtm_wideips.items():
        wip_pools_raw = wideip_data.get('pools') or wideip_data.get('pool') if isinstance(wideip_data, dict) else wideip_data
        wip_pools = extract_name_dict(wip_pools_raw)
        
        wip_src, wip_host = _get_obj_source(parser, fqdn)
        if not wip_pools:
            results.append({
                'fqdn': fqdn, 'gtm_pool': '-', 'gtm_member': '-',
                'ltm_vs': '-', 'vs_dest': '-', 'ltm_pool': '-', 'ltm_members': [],
                'snat': '-', 'irules': [], 'profiles': [], 'persist': '-', 'description': '-',
                'gtm_source_file': wip_src, 'gtm_hostname': wip_host,
                'ltm_source_file': '-', 'ltm_hostname': '-',
                'source_file': wip_src, 'hostname': wip_host,
                'ltm_status': 'LTM Config Pending/Unavailable'
            })
            continue
            
        for gtm_pool_name, gtm_pool_data in wip_pools.items():
            pool_obj = find_gtm_pool(parser.gtm_pools, gtm_pool_name) or {}
            pool_members_raw = pool_obj.get('members') or pool_obj.get('member') if isinstance(pool_obj, dict) else pool_obj
            pool_members = extract_name_dict(pool_members_raw)
            
            if not pool_members:
                results.append({
                    'fqdn': fqdn, 'gtm_pool': gtm_pool_name, 'gtm_member': '-',
                    'ltm_vs': '-', 'vs_dest': '-', 'ltm_pool': '-', 'ltm_members': [],
                    'snat': '-', 'irules': [], 'profiles': [], 'persist': '-', 'description': '-',
                    'gtm_source_file': wip_src, 'gtm_hostname': wip_host,
                    'ltm_source_file': '-', 'ltm_hostname': '-',
                    'source_file': wip_src, 'hostname': wip_host,
                    'ltm_status': 'LTM Config Pending/Unavailable'
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
                
                vs_key, ltm_vs_obj = find_ltm_virtual(parser.ltm_virtuals, vs_name)
                if vs_key:
                    seen_ltm_vs.add(vs_key)
                    seen_ltm_vs.add(normalize_name(vs_key))
                
                if not ltm_vs_obj:
                    results.append({
                        'fqdn': fqdn, 'gtm_pool': gtm_pool_name, 'gtm_member': gtm_member_name,
                        'ltm_vs': vs_name, 'vs_dest': '-', 'ltm_pool': '-', 'ltm_members': [],
                        'snat': '-', 'irules': [], 'profiles': [], 'persist': '-', 'description': '-',
                        'gtm_source_file': wip_src, 'gtm_hostname': wip_host,
                        'ltm_source_file': '-', 'ltm_hostname': '-',
                        'source_file': wip_src, 'hostname': wip_host,
                        'ltm_status': 'LTM Config Pending/Unavailable'
                    })
                    continue
                    
                vs_dest = ltm_vs_obj.get('destination', '-') if isinstance(ltm_vs_obj, dict) else '-'
                ltm_pool_name = ltm_vs_obj.get('pool', '-') if isinstance(ltm_vs_obj, dict) else '-'
                if isinstance(ltm_pool_name, dict):
                    ltm_pool_name = list(ltm_pool_name.keys())[0] if ltm_pool_name else '-'
                
                ltm_pool_obj = parser.ltm_pools.get(ltm_pool_name, {}) or parser.ltm_pools.get(normalize_name(ltm_pool_name), {})
                ltm_members_raw = ltm_pool_obj.get('members') or ltm_pool_obj.get('member') if isinstance(ltm_pool_obj, dict) else ltm_pool_obj
                ltm_members_dict = extract_name_dict(ltm_members_raw)
                
                ltm_members = []
                for m_key, m_val in ltm_members_dict.items():
                    m_details = get_ltm_member_details(parser, m_key, m_val)
                    ltm_members.append(m_details)
                
                details = extract_vs_details(ltm_vs_obj)
                
                vs_src, vs_host = _get_obj_source(parser, vs_key, vs_name)
                results.append({
                    'fqdn': fqdn, 'gtm_pool': gtm_pool_name, 'gtm_member': gtm_member_name,
                    'ltm_vs': vs_key if vs_key else vs_name, 'vs_dest': vs_dest, 'ltm_pool': ltm_pool_name, 'ltm_members': ltm_members,
                    'snat': details['snat'], 'irules': details['irules'], 'profiles': details['profiles'],
                    'persist': details['persist'], 'description': details['description'],
                    'gtm_source_file': wip_src, 'gtm_hostname': wip_host,
                    'ltm_source_file': vs_src, 'ltm_hostname': vs_host,
                    'source_file': wip_src, 'hostname': wip_host,
                    'ltm_status': 'OK'
                })

    # Add unassociated LTM virtual servers (No GTM WideIP found for them)
    for vs_name, ltm_vs_obj in parser.ltm_virtuals.items():
        if vs_name not in seen_ltm_vs and normalize_name(vs_name) not in seen_ltm_vs:
            vs_dest = ltm_vs_obj.get('destination', '-') if isinstance(ltm_vs_obj, dict) else '-'
            ltm_pool_name = ltm_vs_obj.get('pool', '-') if isinstance(ltm_vs_obj, dict) else '-'
            if isinstance(ltm_pool_name, dict):
                ltm_pool_name = list(ltm_pool_name.keys())[0] if ltm_pool_name else '-'

            ltm_pool_obj = parser.ltm_pools.get(ltm_pool_name, {}) or parser.ltm_pools.get(normalize_name(ltm_pool_name), {})
            ltm_members_raw = ltm_pool_obj.get('members') or ltm_pool_obj.get('member') if isinstance(ltm_pool_obj, dict) else ltm_pool_obj
            ltm_members_dict = extract_name_dict(ltm_members_raw)

            ltm_members = []
            for m_key, m_val in ltm_members_dict.items():
                m_details = get_ltm_member_details(parser, m_key, m_val)
                ltm_members.append(m_details)

            details = extract_vs_details(ltm_vs_obj)
            vs_src, vs_host = _get_obj_source(parser, vs_name)

            results.append({
                'fqdn': '-', 'gtm_pool': '-', 'gtm_member': '-',
                'ltm_vs': vs_name, 'vs_dest': vs_dest, 'ltm_pool': ltm_pool_name, 'ltm_members': ltm_members,
                'snat': details['snat'], 'irules': details['irules'], 'profiles': details['profiles'],
                'persist': details['persist'], 'description': details['description'],
                'gtm_source_file': '-', 'gtm_hostname': '-',
                'ltm_source_file': vs_src, 'ltm_hostname': vs_host,
                'source_file': vs_src, 'hostname': vs_host,
                'ltm_status': 'OK (No GTM WideIP)'
            })

    # Apply search filters (q_fqdn, q_ip, q_file, q_host)
    q_fqdn = query_fqdn.strip().lower() if query_fqdn else None
    q_ip = query_ip.strip().lower() if query_ip else None
    q_file = query_file.strip().lower() if query_file else None
    q_host = query_host.strip().lower() if query_host else None

    if not q_fqdn and not q_ip and not q_file and not q_host:
        return results

    filtered_results = []
    for r in results:
        match_fqdn = True
        match_ip = True
        match_file = True
        match_host = True

        if q_fqdn:
            match_fqdn = False
            searchable_text = " ".join([
                r['fqdn'], r['gtm_pool'], r['gtm_member'], r['ltm_vs'],
                r['ltm_pool'], r.get('description', ''),
                " ".join(r.get('irules', [])), " ".join(r.get('profiles', []))
            ]).lower()
            if q_fqdn in searchable_text:
                match_fqdn = True

        if q_ip:
            match_ip = False
            vs_dest_str = r['vs_dest'].lower()
            clean_vs = clean_target_address(r['vs_dest']).lower()
            gtm_mem_str = r['gtm_member'].lower()

            if q_ip in vs_dest_str or (clean_vs and q_ip in clean_vs) or q_ip in gtm_mem_str:
                match_ip = True
            else:
                for m in r['ltm_members']:
                    if isinstance(m, dict):
                        m_raw = m.get('raw', '').lower()
                        m_ip = m.get('ip', '').lower()
                        m_node = m.get('node', '').lower()
                        m_fmt = m.get('formatted', '').lower()
                        if q_ip in m_raw or q_ip in m_ip or q_ip in m_node or q_ip in m_fmt:
                            match_ip = True
                            break
                    elif q_ip in str(m).lower():
                        match_ip = True
                        break

        if q_file:
            gtm_sf = r.get('gtm_source_file', r.get('source_file', '')).lower()
            ltm_sf = r.get('ltm_source_file', '').lower()
            if (q_file not in gtm_sf) and (q_file not in ltm_sf):
                match_file = False

        if q_host:
            gtm_hn = r.get('gtm_hostname', r.get('hostname', '')).lower()
            ltm_hn = r.get('ltm_hostname', '').lower()
            if (q_host not in gtm_hn) and (q_host not in ltm_hn):
                match_host = False

        if match_fqdn and match_ip and match_file and match_host:
            filtered_results.append(r)

    return filtered_results


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
                if r.get('description') and r['description'] != '-':
                    vs_children.append({'type': 'description', 'value': r['description']})
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
                    
                    if child['type'] == 'description':
                        print(f"{c_prefix}Description: {child['value']}")
                    elif child['type'] == 'snat':
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
                            m_str = member['formatted'] if isinstance(member, dict) else str(member)
                            print(f"{m_prefix}LTM Node Member: {m_str}")
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
                    if r.get('description') and r['description'] != '-':
                        vs_children.append({'type': 'description', 'value': r['description']})
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
                        
                        if child['type'] == 'description':
                            print(f"{c_prefix}Description: {child['value']}")
                        elif child['type'] == 'snat':
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
                                m_str = member['formatted'] if isinstance(member, dict) else str(member)
                                print(f"{m_prefix}LTM Node Member: {m_str}")
        print("")


def export_csv(results, filepath, mode='both'):
    """Exports results to CSV. Mode can be 'detail', 'summary', or 'both'."""
    headers = [
        "LTM Status",
        "GTM Source File", "GTM Hostname",
        "LTM Source File", "LTM Hostname",
        "FQDN", "GTM Pool", "GTM Member", "LTM VS", "VS Dest",
        "Description", "SNAT", "iRules", "Profiles",
        "LTM Pool", "LTM Member", "Member IP"
    ]
    
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
                    members = r.get('ltm_members', [])
                    if members:
                        for member in members:
                            if isinstance(member, dict):
                                m_name = member.get('raw', '-')
                                m_ip = member.get('ip', '-')
                            else:
                                m_name = str(member)
                                m_ip = '-'
                            writer.writerow([
                                r.get('ltm_status', '-'),
                                r.get('gtm_source_file', r.get('source_file', '-')), r.get('gtm_hostname', r.get('hostname', '-')),
                                r.get('ltm_source_file', '-'), r.get('ltm_hostname', '-'),
                                r['fqdn'], r['gtm_pool'], r['gtm_member'], r['ltm_vs'],
                                r['vs_dest'], r.get('description', '-'), r.get('snat', '-'), irules_str, profiles_str, r['ltm_pool'], m_name, m_ip
                            ])
                    else:
                        writer.writerow([
                            r.get('ltm_status', '-'),
                            r.get('gtm_source_file', r.get('source_file', '-')), r.get('gtm_hostname', r.get('hostname', '-')),
                            r.get('ltm_source_file', '-'), r.get('ltm_hostname', '-'),
                            r['fqdn'], r['gtm_pool'], r['gtm_member'], r['ltm_vs'],
                            r['vs_dest'], r.get('description', '-'), r.get('snat', '-'), irules_str, profiles_str, r['ltm_pool'], '-', '-'
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
                m_str = member['formatted'] if isinstance(member, dict) else str(member)
                summary[key].add(m_str)
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
    headers = ["Source File", "Hostname", "FQDN", "GTM Pool", "GTM Member", "LTM VS", "VS Dest", "Description", "SNAT", "iRules", "LTM Pool", "LTM Member", "Member IP"]
    widths = [len(h) for h in headers]
    for r in results:
        widths[0] = max(widths[0], len(r.get('source_file', '-')))
        widths[1] = max(widths[1], len(r.get('hostname', '-')))
        widths[2] = max(widths[2], len(r['fqdn']))
        widths[3] = max(widths[3], len(r['gtm_pool']))
        widths[4] = max(widths[4], len(r['gtm_member']))
        widths[5] = max(widths[5], len(r['ltm_vs']))
        widths[6] = max(widths[6], len(r['vs_dest']))
        widths[7] = max(widths[7], len(r.get('description', '-')))
        widths[8] = max(widths[8], len(r.get('snat', '-')))
        irules_str = ", ".join(r.get('irules', [])) if r.get('irules') else "-"
        widths[9] = max(widths[9], len(irules_str))
        widths[10] = max(widths[10], len(r['ltm_pool']))
        members_str = ", ".join(m['raw'] if isinstance(m, dict) else str(m) for m in r['ltm_members']) if r['ltm_members'] else "-"
        ips_str = ", ".join(m['ip'] if isinstance(m, dict) else "-" for m in r['ltm_members']) if r['ltm_members'] else "-"
        widths[11] = max(widths[11], len(members_str))
        widths[12] = max(widths[12], len(ips_str))

    format_str = " | ".join([f"{{:<{w}}}" for w in widths])
    separator = "-+-".join(["-" * w for w in widths])

    print(format_str.format(*headers))
    print(separator)
    for r in results:
        irules_str = ", ".join(r.get('irules', [])) if r.get('irules') else "-"
        members_str = ", ".join(m['raw'] if isinstance(m, dict) else str(m) for m in r['ltm_members']) if r['ltm_members'] else "-"
        ips_str = ", ".join(m['ip'] if isinstance(m, dict) else "-" for m in r['ltm_members']) if r['ltm_members'] else "-"
        print(format_str.format(
            r.get('source_file', '-'), r.get('hostname', '-'),
            r['fqdn'], r['gtm_pool'], r['gtm_member'], r['ltm_vs'],
            r['vs_dest'], r.get('description', '-'), r.get('snat', '-'), irules_str, r['ltm_pool'], members_str, ips_str
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
            self.geometry("1180x760")

            self.f5_parser = None
            self.current_results = []
            self.search_timer = None

            self._create_widgets()

        def _create_widgets(self):
            # Top Control Panel
            ctrl_frame = ttk.LabelFrame(self, text=" Configuration & Search ")
            ctrl_frame.pack(fill=tk.X, padx=10, pady=5)

            # Row 0: Folder Selection
            ttk.Label(ctrl_frame, text="Config Dir:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
            self.dir_var = tk.StringVar(value="config")
            dir_entry = ttk.Entry(ctrl_frame, textvariable=self.dir_var, width=45)
            dir_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)

            browse_dir_btn = ttk.Button(ctrl_frame, text="Browse Folder...", command=self.browse_dir)
            browse_dir_btn.grid(row=0, column=2, padx=2, pady=5)

            browse_file_btn = ttk.Button(ctrl_frame, text="Browse File...", command=self.browse_file)
            browse_file_btn.grid(row=0, column=3, padx=2, pady=5)

            load_btn = ttk.Button(ctrl_frame, text="Load & Parse Configs", command=self.load_configs_gui)
            load_btn.grid(row=0, column=4, padx=5, pady=5)

            # Row 1: Statistics Counters Banner
            stats_frame = ttk.Frame(ctrl_frame)
            stats_frame.grid(row=1, column=0, columnspan=5, padx=5, pady=4, sticky=tk.EW)

            self.stat_files_var = tk.StringVar(value="📁 Files Identified: 0 (LTM: 0 | GTM: 0)")
            self.stat_wips_var = tk.StringVar(value="🌐 WIPs Found: 0")
            self.stat_vips_var = tk.StringVar(value="🎯 VIPs Found: 0")

            lbl_files = ttk.Label(stats_frame, textvariable=self.stat_files_var, font=("TkDefaultFont", 9, "bold"), foreground="#0275d8")
            lbl_files.pack(side=tk.LEFT, padx=(5, 20))

            lbl_wips = ttk.Label(stats_frame, textvariable=self.stat_wips_var, font=("TkDefaultFont", 9, "bold"), foreground="#2e7d32")
            lbl_wips.pack(side=tk.LEFT, padx=20)

            lbl_vips = ttk.Label(stats_frame, textvariable=self.stat_vips_var, font=("TkDefaultFont", 9, "bold"), foreground="#6b21a8")
            lbl_vips.pack(side=tk.LEFT, padx=20)

            # Row 2: Filter Options — FQDN & IP
            ttk.Label(ctrl_frame, text="Filter FQDN:").grid(row=2, column=0, padx=5, pady=3, sticky=tk.W)
            self.fqdn_var = tk.StringVar()
            fqdn_entry = ttk.Entry(ctrl_frame, textvariable=self.fqdn_var, width=22)
            fqdn_entry.grid(row=2, column=1, padx=5, pady=3, sticky=tk.W)
            fqdn_entry.bind("<KeyRelease>", self.on_filter_key)
            fqdn_entry.bind("<Return>", lambda e: self.apply_filter())

            ttk.Label(ctrl_frame, text="Filter IP:").grid(row=2, column=2, padx=5, pady=3, sticky=tk.E)
            self.ip_var = tk.StringVar()
            ip_entry = ttk.Entry(ctrl_frame, textvariable=self.ip_var, width=18)
            ip_entry.grid(row=2, column=3, padx=5, pady=3, sticky=tk.W)
            ip_entry.bind("<KeyRelease>", self.on_filter_key)
            ip_entry.bind("<Return>", lambda e: self.apply_filter())

            # Row 3: Filter Options — Filename & Hostname
            ttk.Label(ctrl_frame, text="Filter File:").grid(row=3, column=0, padx=5, pady=3, sticky=tk.W)
            self.filter_file_var = tk.StringVar()
            self.file_combo = ttk.Combobox(ctrl_frame, textvariable=self.filter_file_var, width=21, state="normal")
            self.file_combo.grid(row=3, column=1, padx=5, pady=3, sticky=tk.W)
            self.file_combo.bind("<KeyRelease>", self.on_filter_key)
            self.file_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())

            ttk.Label(ctrl_frame, text="Filter Host:").grid(row=3, column=2, padx=5, pady=3, sticky=tk.E)
            self.filter_host_var = tk.StringVar()
            self.host_combo = ttk.Combobox(ctrl_frame, textvariable=self.filter_host_var, width=17, state="normal")
            self.host_combo.grid(row=3, column=3, padx=5, pady=3, sticky=tk.W)
            self.host_combo.bind("<KeyRelease>", self.on_filter_key)
            self.host_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())

            btn_subframe = ttk.Frame(ctrl_frame)
            btn_subframe.grid(row=2, column=4, rowspan=2, padx=5, pady=3, sticky=tk.NE)

            filter_btn = ttk.Button(btn_subframe, text="Search", command=self.apply_filter)
            filter_btn.pack(side=tk.LEFT, padx=2)

            clear_btn = ttk.Button(btn_subframe, text="Reset", command=self.reset_filter)
            clear_btn.pack(side=tk.LEFT, padx=2)

            ping_btn = ttk.Button(btn_subframe, text="📶 Ping Target", command=self.ping_selected_gui)
            ping_btn.pack(side=tk.LEFT, padx=4)

            export_btn = ttk.Button(btn_subframe, text="💾 Export Displayed Entries", command=self.export_displayed_entries_gui)
            export_btn.pack(side=tk.LEFT, padx=2)

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

            # Tab 4: F5 Device Map (big-picture cross-device view)
            self.device_map_tab = ttk.Frame(self.notebook)
            self.notebook.add(self.device_map_tab, text="🗺 F5 Device Map")
            self._setup_device_map_tab()

            # Status Bar
            self.status_var = tk.StringVar(value="Ready. Select config directory and click 'Load & Parse Configs'.")
            status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=3)
            status_bar.pack(side=tk.BOTTOM, fill=tk.X)

            # Context Menus
            self._setup_context_menus()

        def browse_dir(self):
            selected = filedialog.askdirectory(initialdir=self.dir_var.get() or ".")
            if selected:
                self.dir_var.set(selected)

        def browse_file(self):
            selected = filedialog.askopenfilename(
                title="Select F5 Configuration File",
                filetypes=[("Config Files", "*.conf *.txt *.cfg *.scf *.log"), ("All Files", "*.*")]
            )
            if selected:
                self.dir_var.set(selected)
                self.load_configs_gui()

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
            files_total = getattr(self.f5_parser, 'files_scanned', 0)
            ltm_files = getattr(self.f5_parser, 'ltm_files_count', 0)
            gtm_files = getattr(self.f5_parser, 'gtm_files_count', 0)
            wips_count = len(self.f5_parser.gtm_wideips)
            vss_count = len(self.f5_parser.ltm_virtuals)

            self.stat_files_var.set(f"📁 Files Identified: {files_total} (LTM: {ltm_files} | GTM: {gtm_files})")
            self.stat_wips_var.set(f"🌐 WIPs Found: {wips_count}")
            self.stat_vips_var.set(f"🎯 VIPs Found: {vss_count}")

            self.status_var.set(f"Loaded: {files_total} files ({ltm_files} LTM, {gtm_files} GTM), {wips_count} WideIPs (WIP), {vss_count} Virtual Servers (VIP) from '{config_dir}'")
            self._refresh_combo_values()
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
            q_file = self.filter_file_var.get().strip() or None
            q_host = self.filter_host_var.get().strip() or None

            self.current_results = walk_relationships(
                self.f5_parser, query_fqdn=fqdn, query_ip=ip, query_file=q_file, query_host=q_host
            )
            self.populate_views()

        def reset_filter(self):
            self.fqdn_var.set("")
            self.ip_var.set("")
            self.filter_file_var.set("")
            self.filter_host_var.set("")
            self.apply_filter()

        def populate_views(self):
            self.populate_tree_view()
            self.populate_detail_view()
            self.populate_summary_view()
            self.populate_device_map_view()
            self.status_var.set(f"Displaying {len(self.current_results)} mapped relationship entries.")

        def _refresh_combo_values(self):
            """Refresh file/host combo dropdown lists after loading configs."""
            if not self.f5_parser:
                return
            files = sorted(set(v for v in self.f5_parser.object_source_file.values() if v))
            hosts = sorted(set(v for v in self.f5_parser.object_hostname.values() if v))
            self.file_combo['values'] = files
            self.host_combo['values'] = hosts

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
                        ltm_src = r.get('ltm_source_file', r.get('source_file', '-'))
                        ltm_hn  = r.get('ltm_hostname',    r.get('hostname', '-'))
                        src_info = f"LTM File: {ltm_src}  Host: {ltm_hn}"
                        vs_node = self.visual_tree.insert(unassoc_node, tk.END, text=f"LTM VS: {r['ltm_vs']}", values=(f"Dest: {r['vs_dest']}  |  {src_info}",), open=True, tags=("vs",))
                        if r.get('description') and r['description'] != '-':
                            self.visual_tree.insert(vs_node, tk.END, text="Description", values=(r['description'],))
                        if r.get('snat') and r['snat'] != '-':
                            self.visual_tree.insert(vs_node, tk.END, text="SNAT", values=(r['snat'],), tags=("snat",))
                        for irule in r.get('irules', []):
                            self.visual_tree.insert(vs_node, tk.END, text="iRule", values=(irule,), tags=("irule",))
                        if r.get('profiles'):
                            self.visual_tree.insert(vs_node, tk.END, text="Profiles", values=(", ".join(r['profiles']),), tags=("profile",))
                        if r['ltm_pool'] != '-':
                            pool_node = self.visual_tree.insert(vs_node, tk.END, text=f"LTM Pool: {r['ltm_pool']}", values=("",), open=True)
                            for member in r['ltm_members']:
                                m_str = member['formatted'] if isinstance(member, dict) else str(member)
                                self.visual_tree.insert(pool_node, tk.END, text=f"Member: {m_str}", values=("",))
                    continue

                # Get source info from first result for this WIP
                first_r = next((r for pool_d in gpools.values() for mem_d in pool_d.values() for r in mem_d), None)
                wip_src_info = ""
                if first_r:
                    g_file = first_r.get('gtm_source_file', first_r.get('source_file', '-'))
                    g_host = first_r.get('gtm_hostname',    first_r.get('hostname', '-'))
                    wip_src_info = f"GTM File: {g_file}  Host: {g_host}"
                wip_node = self.visual_tree.insert("", tk.END, text=f"WideIP (FQDN): {wip}", values=(wip_src_info,), open=True, tags=("wip",))
                for gpool, gmems in gpools.items():
                    gpool_node = self.visual_tree.insert(wip_node, tk.END, text=f"GTM Pool: {gpool}", values=("",), open=True)
                    for gmem, rows in gmems.items():
                        gmem_node = self.visual_tree.insert(gpool_node, tk.END, text=f"GTM Member: {gmem}", values=("",), open=True)
                        for r in rows:
                            ltm_status = r.get('ltm_status', '')
                            is_pending = 'Pending' in ltm_status or 'Unavailable' in ltm_status
                            is_not_found = 'Not Found' in r['ltm_vs']
                            if is_pending:
                                vs_tag = "not_found"
                                vs_label = f"⚠ LTM Config Pending/Unavailable: {r['ltm_vs']}"
                                ltm_file = r.get('ltm_source_file', '-')
                                ltm_host = r.get('ltm_hostname', '-')
                                vs_detail = f"LTM not loaded | GTM File: {r.get('gtm_source_file', '-')}  Host: {r.get('gtm_hostname', '-')}"
                            else:
                                vs_tag = "not_found" if is_not_found else "vs"
                                vs_label = f"LTM VS: {r['ltm_vs']}"
                                ltm_file = r.get('ltm_source_file', '-')
                                ltm_host = r.get('ltm_hostname', '-')
                                vs_detail = f"Dest: {r['vs_dest']}  |  LTM File: {ltm_file}  Host: {ltm_host}"
                            vs_node = self.visual_tree.insert(gmem_node, tk.END, text=vs_label, values=(vs_detail,), open=True, tags=(vs_tag,))
                            if r.get('description') and r['description'] != '-':
                                self.visual_tree.insert(vs_node, tk.END, text="Description", values=(r['description'],))
                            if r.get('snat') and r['snat'] != '-':
                                self.visual_tree.insert(vs_node, tk.END, text="SNAT", values=(r['snat'],), tags=("snat",))
                            for irule in r.get('irules', []):
                                self.visual_tree.insert(vs_node, tk.END, text="iRule", values=(irule,), tags=("irule",))
                            if r.get('profiles'):
                                self.visual_tree.insert(vs_node, tk.END, text="Profiles", values=(", ".join(r['profiles']),), tags=("profile",))
                            if r['ltm_pool'] != '-':
                                pool_node = self.visual_tree.insert(vs_node, tk.END, text=f"LTM Pool: {r['ltm_pool']}", values=("",), open=True)
                                for member in r['ltm_members']:
                                    m_str = member['formatted'] if isinstance(member, dict) else str(member)
                                    self.visual_tree.insert(pool_node, tk.END, text=f"Member: {m_str}", values=("",))

        def _setup_detail_tab(self):
            frame = ttk.Frame(self.detail_tab)
            frame.pack(fill=tk.BOTH, expand=True)

            headers = [
                "LTM Status",
                "GTM File", "GTM Host",
                "LTM File", "LTM Host",
                "FQDN", "GTM Pool", "GTM Member", "LTM VS", "VS Dest",
                "Description", "SNAT", "iRules", "Profiles",
                "LTM Pool", "LTM Member", "Member IP"
            ]
            self.detail_tree = ttk.Treeview(frame, columns=headers, show="headings", selectmode="browse")

            col_widths = {
                "LTM Status": 160, "GTM File": 110, "GTM Host": 140,
                "LTM File": 110, "LTM Host": 140, "FQDN": 160,
                "GTM Pool": 120, "GTM Member": 120, "LTM VS": 130, "VS Dest": 130,
                "Description": 110, "SNAT": 90, "iRules": 90, "Profiles": 90,
                "LTM Pool": 120, "LTM Member": 120, "Member IP": 110
            }
            for h in headers:
                self.detail_tree.heading(h, text=h, anchor=tk.W, command=lambda _h=h: self.sort_column(self.detail_tree, _h, False))
                self.detail_tree.column(h, width=col_widths.get(h, 105), stretch=True)

            # Row colour tags
            self.detail_tree.tag_configure("pending", foreground="#c0392b", background="#fff5f5")
            self.detail_tree.tag_configure("ok",      foreground="#1a5c2a")

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
                members_str = ", ".join(m['raw'] if isinstance(m, dict) else str(m) for m in r['ltm_members']) if r['ltm_members'] else "-"
                ips_str = ", ".join(m['ip'] if isinstance(m, dict) else "-" for m in r['ltm_members']) if r['ltm_members'] else "-"
                ltm_status = r.get('ltm_status', '-')
                tag = "pending" if 'Pending' in ltm_status or 'Unavailable' in ltm_status else "ok"
                self.detail_tree.insert("", tk.END, tags=(tag,), values=(
                    ltm_status,
                    r.get('gtm_source_file', r.get('source_file', '-')), r.get('gtm_hostname', r.get('hostname', '-')),
                    r.get('ltm_source_file', '-'), r.get('ltm_hostname', '-'),
                    r['fqdn'], r['gtm_pool'], r['gtm_member'], r['ltm_vs'],
                    r['vs_dest'], r.get('description', '-'), r.get('snat', '-'), irules_str, profiles_str, r['ltm_pool'], members_str, ips_str
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
                    m_str = member['formatted'] if isinstance(member, dict) else str(member)
                    summary[key].add(m_str)

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

        # ─────────────────────────────────────────────────────────
        # Tab 4: F5 Device Map
        # ─────────────────────────────────────────────────────────
        def _setup_device_map_tab(self):
            frame = ttk.Frame(self.device_map_tab)
            frame.pack(fill=tk.BOTH, expand=True)

            # Toolbar
            toolbar = ttk.Frame(frame)
            toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 2))

            ttk.Label(toolbar, text="F5 Device Map — which GTM device links to which LTM device via WideIP→VS flows",
                      font=("TkDefaultFont", 9, "bold")).pack(side=tk.LEFT, padx=6)
            ttk.Button(toolbar, text="➕ Expand All", command=lambda: self._expand_tree(self.device_map_tree)).pack(side=tk.RIGHT, padx=2)
            ttk.Button(toolbar, text="➖ Collapse All", command=lambda: self._collapse_tree(self.device_map_tree)).pack(side=tk.RIGHT, padx=2)

            # Treeview
            cols = ("role", "file", "hostname", "wips", "vips", "notes")
            self.device_map_tree = ttk.Treeview(frame, columns=cols, show="tree headings", selectmode="browse")
            self.device_map_tree.heading("#0",    text="GTM Device / Link Target", anchor=tk.W)
            self.device_map_tree.heading("role",  text="Role", anchor=tk.W)
            self.device_map_tree.heading("file",  text="Source File", anchor=tk.W)
            self.device_map_tree.heading("hostname", text="Hostname", anchor=tk.W)
            self.device_map_tree.heading("wips",  text="WIPs", anchor=tk.CENTER)
            self.device_map_tree.heading("vips",  text="VIPs / VSs", anchor=tk.CENTER)
            self.device_map_tree.heading("notes", text="Notes", anchor=tk.W)

            self.device_map_tree.column("#0",      width=260, stretch=True)
            self.device_map_tree.column("role",    width=70,  stretch=False)
            self.device_map_tree.column("file",    width=160, stretch=True)
            self.device_map_tree.column("hostname",width=180, stretch=True)
            self.device_map_tree.column("wips",    width=55,  stretch=False, anchor=tk.CENTER)
            self.device_map_tree.column("vips",    width=70,  stretch=False, anchor=tk.CENTER)
            self.device_map_tree.column("notes",   width=220, stretch=True)

            # Tags / colours
            self.device_map_tree.tag_configure("gtm",  foreground="#0275d8", font=("TkDefaultFont", 9, "bold"))
            self.device_map_tree.tag_configure("ltm",  foreground="#2e7d32", font=("TkDefaultFont", 9, "bold"))
            self.device_map_tree.tag_configure("link", foreground="#d97706")
            self.device_map_tree.tag_configure("wip_row",  foreground="#4b5563")
            self.device_map_tree.tag_configure("unlinked", foreground="#9ca3af", font=("TkDefaultFont", 9, "italic"))

            vsb = ttk.Scrollbar(frame, orient="vertical",   command=self.device_map_tree.yview)
            hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.device_map_tree.xview)
            self.device_map_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

            self.device_map_tree.grid(row=1, column=0, sticky="nsew")
            vsb.grid(row=1, column=1, sticky="ns")
            hsb.grid(row=2, column=0, sticky="ew")

            frame.rowconfigure(1, weight=1)
            frame.columnconfigure(0, weight=1)

            # Double-click: set file filter and jump to other tabs
            self.device_map_tree.bind("<Double-1>", self._device_map_dblclick)

        def _expand_tree(self, tree, item=""):
            for child in tree.get_children(item):
                tree.item(child, open=True)
                self._expand_tree(tree, child)

        def _collapse_tree(self, tree, item=""):
            for child in tree.get_children(item):
                tree.item(child, open=False)
                self._collapse_tree(tree, child)

        def _device_map_dblclick(self, event):
            """Double-clicking a device row sets the file/host filter and refreshes other tabs."""
            sel = self.device_map_tree.focus()
            if not sel:
                return
            vals = self.device_map_tree.item(sel, "values")
            if not vals or len(vals) < 3:
                return
            file_val = vals[1] if vals[1] not in ('-', '') else ''
            host_val = vals[2] if vals[2] not in ('-', '') else ''
            self.filter_file_var.set(file_val)
            self.filter_host_var.set(host_val)
            self.apply_filter()
            # Switch to detailed tab
            self.notebook.select(1)

        def populate_device_map_view(self):
            for item in self.device_map_tree.get_children():
                self.device_map_tree.delete(item)

            if not self.f5_parser:
                return

            # Build the cross-device map from currently displayed/filtered results
            map_results = self.current_results if (self.current_results is not None) else walk_relationships(self.f5_parser)

            # Structures:
            #   gtm_devices[gtm_key] = {'file': ..., 'host': ..., 'wips': set(), 'pending_wips': set()}
            #   ltm_devices[ltm_key] = {'file': ..., 'host': ..., 'vss': set()}
            gtm_devices = {}
            ltm_devices = {}
            links = {}   # (gtm_key, ltm_key) -> {'wips': set(), 'vss': set(), 'pools': set()}

            for r in map_results:
                # Use the properly split GTM source fields
                g_file = r.get('gtm_source_file', r.get('source_file', '-'))
                g_host = r.get('gtm_hostname',    r.get('hostname', '-'))
                # Skip unassociated LTM-only rows from GTM device listing
                fqdn = r.get('fqdn', '-')
                if fqdn == '-':
                    # This is an LTM-only VS; track it as standalone LTM device
                    l_file = r.get('ltm_source_file', r.get('source_file', '-'))
                    l_host = r.get('ltm_hostname',    r.get('hostname', '-'))
                    ltm_key = f"{l_host}|{l_file}"
                    vs_name = r.get('ltm_vs', '-')
                    if ltm_key not in ltm_devices:
                        ltm_devices[ltm_key] = {'file': l_file, 'host': l_host, 'vss': set()}
                    ltm_devices[ltm_key]['vss'].add(vs_name)
                    continue

                gtm_key = f"{g_host}|{g_file}"

                # LTM side: use split fields directly
                l_file = r.get('ltm_source_file', '-')
                l_host = r.get('ltm_hostname', '-')
                ltm_key = f"{l_host}|{l_file}"

                ltm_status = r.get('ltm_status', '')
                is_pending = 'Pending' in ltm_status or 'Unavailable' in ltm_status

                # Register GTM device
                if gtm_key not in gtm_devices:
                    gtm_devices[gtm_key] = {'file': g_file, 'host': g_host, 'wips': set(), 'pending_wips': set()}
                gtm_devices[gtm_key]['wips'].add(fqdn)
                if is_pending:
                    gtm_devices[gtm_key]['pending_wips'].add(fqdn)

                vs_name = r.get('ltm_vs', '-')

                # Register LTM device and link (only for matched, non-pending entries)
                if not is_pending and vs_name not in ('-', ''):
                    if ltm_key not in ltm_devices:
                        ltm_devices[ltm_key] = {'file': l_file, 'host': l_host, 'vss': set()}
                    ltm_devices[ltm_key]['vss'].add(vs_name)

                    # Link GTM -> LTM
                    link_key = (gtm_key, ltm_key)
                    if link_key not in links:
                        links[link_key] = {'wips': set(), 'vss': set(), 'pools': set()}
                    links[link_key]['wips'].add(fqdn)
                    links[link_key]['vss'].add(vs_name)
                    if r.get('gtm_pool', '-') != '-':
                        links[link_key]['pools'].add(r['gtm_pool'])

            # ── Render GTM devices as top-level nodes ──
            for gtm_key, gdata in sorted(gtm_devices.items(), key=lambda x: x[0]):
                g_file     = gdata['file']
                g_host     = gdata['host']
                n_wips     = len(gdata['wips'])
                n_pending  = len(gdata.get('pending_wips', set()))
                display    = g_host if g_host != '-' else g_file
                pending_note = f"  ⚠ {n_pending} WIP(s) LTM Config Pending/Unavailable" if n_pending else ""
                gtm_node = self.device_map_tree.insert(
                    "", tk.END,
                    text=f"🌐 GTM: {display}",
                    values=("GTM", g_file, g_host, n_wips, "-", f"{n_wips} WideIP(s){pending_note}"),
                    open=True, tags=("gtm",)
                )

                # WideIPs list under GTM device node
                pending_wips = gdata.get('pending_wips', set())
                for wip in sorted(gdata['wips']):
                    is_wip_pending = wip in pending_wips
                    wip_tag = "not_found" if is_wip_pending else "wip_row"
                    wip_note = "⚠ LTM Config Pending/Unavailable" if is_wip_pending else ""
                    self.device_map_tree.insert(
                        gtm_node, tk.END,
                        text=f"  ↳ WideIP: {wip}",
                        values=("WideIP", g_file, g_host, "-", "-", wip_note),
                        open=False, tags=(wip_tag,)
                    )

                # ── Pending / Unavailable LTM section ──
                if pending_wips:
                    pending_node = self.device_map_tree.insert(
                        gtm_node, tk.END,
                        text=f"  ⚠ LTM Config Pending/Unavailable ({n_pending} WIP(s))",
                        values=("", g_file, g_host, n_pending, "-", "LTM config not loaded for these WIPs"),
                        open=True, tags=("not_found",)
                    )
                    for wip in sorted(pending_wips):
                        self.device_map_tree.insert(
                            pending_node, tk.END,
                            text=f"    ↳ WideIP: {wip}",
                            values=("WideIP", g_file, g_host, "-", "-", "No LTM VS found in loaded configs"),
                            open=False, tags=("unlinked",)
                        )

                # ── LTM devices linked from this GTM ──
                linked_ltm_keys = {lk for (gk, lk) in links if gk == gtm_key}
                if linked_ltm_keys:
                    links_node = self.device_map_tree.insert(
                        gtm_node, tk.END,
                        text=f"  → Linked LTM Devices ({len(linked_ltm_keys)})",
                        values=("", "", "", "-", "-", ""),
                        open=True, tags=("link",)
                    )
                    for ltm_key in sorted(linked_ltm_keys):
                        ldata = ltm_devices.get(ltm_key, {})
                        l_file  = ldata.get('file', '-')
                        l_host  = ldata.get('host', '-')
                        lk_data = links.get((gtm_key, ltm_key), {})
                        n_vss   = len(lk_data.get('vss', set()))
                        n_wip_l = len(lk_data.get('wips', set()))
                        n_pools = len(lk_data.get('pools', set()))
                        l_display = l_host if l_host != '-' else l_file

                        is_self = (gtm_key == ltm_key)
                        note = "⚠ Same device (GTM+LTM co-located)" if is_self else f"{n_wip_l} WIP→VS flows | {n_pools} GTM pool(s)"

                        ltm_node = self.device_map_tree.insert(
                            links_node, tk.END,
                            text=f"    🎯 LTM: {l_display}",
                            values=("LTM", l_file, l_host, n_wip_l, n_vss, note),
                            open=True, tags=("ltm",)
                        )
                        # VS list under LTM node
                        for vs in sorted(lk_data.get('vss', set())):
                            self.device_map_tree.insert(
                                ltm_node, tk.END,
                                text=f"      ↳ VS: {vs}",
                                values=("VS", l_file, l_host, "-", "-", ""),
                                open=False, tags=("wip_row",)
                            )
                elif not pending_wips:
                    # GTM with no linked LTM VSs and no pending
                    self.device_map_tree.insert(
                        gtm_node, tk.END,
                        text="  (No linked LTM Virtual Servers found)",
                        values=("", "-", "-", "-", "-", "Check GTM pool members match LTM VS names"),
                        open=False, tags=("unlinked",)
                    )

            # ── Unlinked LTM devices (LTM-only files, not referenced by any GTM) ──
            linked_all_ltm = {lk for (_, lk) in links}
            standalone_ltm = {k: v for k, v in ltm_devices.items() if k not in linked_all_ltm}
            if standalone_ltm:
                unlinked_root = self.device_map_tree.insert(
                    "", tk.END,
                    text="📦 Standalone LTM Devices (not linked from any GTM WideIP)",
                    values=("LTM", "-", "-", "-", len(standalone_ltm), ""),
                    open=True, tags=("unlinked",)
                )
                for ltm_key, ldata in sorted(standalone_ltm.items(), key=lambda x: x[0]):
                    l_file = ldata.get('file', '-')
                    l_host = ldata.get('host', '-')
                    l_vss  = len(ldata.get('vss', set()))
                    l_display = l_host if l_host != '-' else l_file
                    self.device_map_tree.insert(
                        unlinked_root, tk.END,
                        text=f"  🎯 LTM: {l_display}",
                        values=("LTM", l_file, l_host, "-", l_vss, "No GTM WideIP references this device"),
                        open=False, tags=("ltm",)
                    )



        def export_displayed_entries_gui(self):
            """Export the currently displayed (filtered) entries to CSV or Text formats."""
            if not self.current_results:
                messagebox.showwarning("Warning", "No displayed entries to export.")
                return

            filepath = filedialog.asksaveasfilename(
                title="Export Displayed Entries",
                defaultextension=".csv",
                filetypes=[("CSV Files (*.csv)", "*.csv"), ("Text Report (*.txt)", "*.txt"), ("All Files", "*.*")]
            )
            if not filepath:
                return

            if filepath.lower().endswith(".txt"):
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(f"F5 Query - Displayed Entries Flow Report ({len(self.current_results)} entries)\n")
                        f.write("=" * 90 + "\n\n")
                        for idx, r in enumerate(self.current_results, 1):
                            f.write(f"Entry #{idx}\n")
                            f.write(f"  FQDN (WideIP):    {r['fqdn']}\n")
                            f.write(f"  LTM Status:       {r.get('ltm_status', '-')}\n")
                            f.write(f"  GTM Source:       File: {r.get('gtm_source_file', '-')} | Host: {r.get('gtm_hostname', '-')}\n")
                            f.write(f"  GTM Pool:         {r['gtm_pool']} (Member: {r['gtm_member']})\n")
                            f.write(f"  LTM VS:           {r['ltm_vs']} (Destination: {r['vs_dest']})\n")
                            f.write(f"  LTM Source:       File: {r.get('ltm_source_file', '-')} | Host: {r.get('ltm_hostname', '-')}\n")
                            f.write(f"  Description:      {r.get('description', '-')}\n")
                            f.write(f"  SNAT:             {r.get('snat', '-')}\n")
                            f.write(f"  iRules:           {', '.join(r.get('irules', [])) if r.get('irules') else '-'}\n")
                            f.write(f"  Profiles:         {', '.join(r.get('profiles', [])) if r.get('profiles') else '-'}\n")
                            f.write(f"  LTM Pool:         {r['ltm_pool']}\n")
                            members_str = ", ".join(m['raw'] if isinstance(m, dict) else str(m) for m in r['ltm_members']) if r['ltm_members'] else "-"
                            f.write(f"  LTM Pool Members: {members_str}\n")
                            f.write("-" * 90 + "\n\n")
                    messagebox.showinfo("Export Successful", f"Successfully exported {len(self.current_results)} displayed entries to:\n{filepath}")
                    self.status_var.set(f"Exported {len(self.current_results)} displayed entries to '{os.path.basename(filepath)}'.")
                except Exception as e:
                    messagebox.showerror("Export Error", f"Failed to export text report: {e}")
            else:
                export_csv(self.current_results, filepath, mode='both')
                messagebox.showinfo("Export Successful", f"Successfully exported {len(self.current_results)} displayed entries to CSV:\n{filepath}")
                self.status_var.set(f"Exported {len(self.current_results)} displayed entries to CSV.")

        def export_csv_gui(self):
            self.export_displayed_entries_gui()

        def _setup_context_menus(self):
            self.context_menu = tk.Menu(self, tearoff=0)
            self.context_menu.add_command(label="📶 Ping Selected Target", command=self.ping_selected_gui)
            self.context_menu.add_command(label="💾 Export Displayed Entries...", command=self.export_displayed_entries_gui)
            
            for tree in [self.visual_tree, self.detail_tree, self.summary_tree, self.device_map_tree]:
                tree.bind("<Button-3>", self._show_context_menu)
                tree.bind("<Button-2>", self._show_context_menu)

        def _show_context_menu(self, event):
            tree = event.widget
            item = tree.identify_row(event.y)
            if item:
                tree.selection_set(item)
                self.context_menu.post(event.x_root, event.y_root)

        def _get_selected_target(self):
            current_tab = self.notebook.index(self.notebook.select())
            target = ""
            
            if current_tab == 0:
                sel = self.visual_tree.selection()
                if sel:
                    item_text = self.visual_tree.item(sel[0], "text")
                    item_vals = self.visual_tree.item(sel[0], "values")
                    val_str = item_vals[0] if item_vals else ""
                    
                    if "WideIP (FQDN):" in item_text:
                        target = item_text.split("WideIP (FQDN):")[-1].strip()
                    elif "LTM VS:" in item_text:
                        if "Dest:" in val_str:
                            target = val_str.split("Dest:")[-1].strip()
                        else:
                            target = item_text.split("LTM VS:")[-1].strip()
                    elif "Member:" in item_text:
                        target = item_text.split("Member:")[-1].strip()
                    else:
                        target = val_str or item_text
            elif current_tab == 1:
                sel = self.detail_tree.selection()
                if sel:
                    vals = self.detail_tree.item(sel[0], "values")
                    if vals:
                        target = vals[4] if vals[4] != '-' else vals[0]
            elif current_tab == 2:
                sel = self.summary_tree.selection()
                if sel:
                    vals = self.summary_tree.item(sel[0], "values")
                    if vals:
                        target = vals[1] if vals[1] != '-' else vals[0]
                        
            return clean_target_address(target)

        def ping_selected_gui(self):
            target = self._get_selected_target()
            if not target:
                messagebox.showwarning("Ping Target", "Please select a valid WIP FQDN, VIP IP, or Node Member row to ping.")
                return

            self.status_var.set(f"Pinging {target}... Please wait...")
            
            def run_ping_thread():
                success, clean_tgt, summary, details = ping_target(target, count=2, timeout_sec=3)
                self.after(0, lambda: self._show_ping_result(target, success, summary, details))
                
            threading.Thread(target=run_ping_thread, daemon=True).start()

        def _show_ping_result(self, target, success, summary, details):
            self.status_var.set(summary)
            if success:
                messagebox.showinfo(f"Ping Result: {target}", f"{summary}\n\n=== Details ===\n{details}")
            else:
                messagebox.showerror(f"Ping Result: {target}", f"{summary}\n\n=== Details ===\n{details}")

    app = F5QueryApp()
    app.mainloop()


def main_cli(args=None):
    parser = argparse.ArgumentParser(description="F5 GTM/LTM Configuration Parser")
    parser.add_argument("-c", "--config-dir", default="config", help="Directory containing F5 configuration files")
    parser.add_argument("-q", "--query-fqdn", help="Query specific FQDN (substring match)")
    parser.add_argument("-i", "--query-ip", help="Query specific IP (substring match)")
    parser.add_argument("--format", choices=['both', 'tree', 'table'], default='table', help="Output format (default: table)")
    parser.add_argument("--csv", help="Export CSV tables to this file path prefix (e.g. output.csv)")
    parser.add_argument("--ping", action="store_true", help="Ping matching WIPs and VIPs")
    parser.add_argument("--cli", action="store_true", help="Force CLI mode")
    parser.add_argument("--gui", action="store_true", help="Force GUI mode")
    
    parsed_args = parser.parse_args(args)
    
    print(f"Loading F5 configurations from: {parsed_args.config_dir}")
    f5_parser = load_configs(parsed_args.config_dir)
    
    files_scanned = getattr(f5_parser, 'files_scanned', 0)
    ltm_files = getattr(f5_parser, 'ltm_files_count', 0)
    gtm_files = getattr(f5_parser, 'gtm_files_count', 0)
    
    print(f"Identified {files_scanned} configuration files ({ltm_files} LTM config files, {gtm_files} GTM config files)")
    print(f"Parsed {len(f5_parser.gtm_wideips)} WideIPs (WIP), {len(f5_parser.gtm_pools)} GTM Pools, {len(f5_parser.ltm_virtuals)} LTM Virtual Servers (VIP)")
    
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

    if parsed_args.ping:
        print("\n=== Ping Tests ===")
        targets_to_ping = set()
        for r in results:
            if r['fqdn'] and r['fqdn'] != '-':
                targets_to_ping.add(r['fqdn'])
            if r['vs_dest'] and r['vs_dest'] != '-':
                targets_to_ping.add(r['vs_dest'])
        
        for tgt in sorted(targets_to_ping):
            cleaned = clean_target_address(tgt)
            if not cleaned: continue
            print(f"Pinging {tgt} ({cleaned})... ", end="", flush=True)
            success, clean_tgt, summary, details = ping_target(cleaned)
            print(summary)


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
