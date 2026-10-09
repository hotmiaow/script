#!/usr/bin/env python3
"""
Enhanced Cisco Network Traceroute Mapper
• Runs on Python 3.8
• Accepts hostname *or* IP from the command line (non-interactive)  
  $ python3 CiscoTracerouteMapper.py 10.1.1.10
  $ python3 CiscoTracerouteMapper.py core-switch-01
• Falls back to the interactive menu when no target is supplied
• Performs forward (A) and reverse (PTR) DNS look-ups
• Groups inventory by security zone
• Source ↔ Destination mode (WAN aware)
  $ python3 TraceINT.py -s 10.1.1.10 -d 10.2.2.20
  Traces to both endpoints; if both paths contain a WAN router (device name
  contains 'wanr', configurable via --wan-keyword) the two traces are
  stitched together into one end-to-end path across the WAN.
"""

import argparse
import csv
import functools
import ipaddress
import os
import platform
import re
import socket
import subprocess
import sys
import time
import concurrent.futures
import queue
import threading
from typing import Dict, List, Optional, Tuple, Set, Any

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    import tkinter.font as tkfont
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

# ──────────────────────────────────────────────────────────────────────────────
# DNS helpers
# ──────────────────────────────────────────────────────────────────────────────
def resolve_target(target: str) -> str:
    """
    Accepts 'host.example.com' or '10.1.1.1'.
    Returns a validated IPv4 address ready for traceroute,
    raises ValueError if resolution fails.
    """
    try:                                   # already an IP?
        ipaddress.IPv4Address(target)
        return target
    except ipaddress.AddressValueError:
        pass

    try:                                   # hostname → IP
        ip = socket.gethostbyname(target)
        ipaddress.IPv4Address(ip)          # validate resolver output
        print(f"✓ Resolved {target} → {ip}")
        return ip
    except Exception as exc:
        raise ValueError(f"DNS resolution failed for '{target}': {exc}") from None


@functools.lru_cache(maxsize=4096)
def get_reverse_dns(ip: str) -> Optional[str]:
    """Best-effort PTR lookup – returns hostname or None."""
    try:
        hostname, _aliases, _ips = socket.gethostbyaddr(ip)
        return hostname
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# IP & Subnet helpers
# ──────────────────────────────────────────────────────────────────────────────
def parse_ip_and_network(
    ip_sub: str,
) -> Tuple[Optional[str], Optional[ipaddress.IPv4Network]]:
    """
    Parses IP string (e.g. '10.1.1.1/24', '10.1.1.1 255.255.255.0', '10.1.1.1/24 (secondary)')
    into (ip_str, network_obj). Returns (None, None) if dynamic or invalid.
    """
    clean = re.sub(r"\(.*?\)", "", ip_sub).strip()
    if (
        not clean
        or clean.upper() in {"DHCP", "PPPOE", "UNASSIGNED", "NONE"}
        or clean.upper().startswith("SOURCE:")
    ):
        return None, None
    if " " in clean:
        parts = clean.split()
        if len(parts) >= 2:
            clean = f"{parts[0]}/{parts[1]}"
        else:
            clean = parts[0]
    try:
        if "/" in clean:
            iface_obj = ipaddress.ip_interface(clean)
            return str(iface_obj.ip), iface_obj.network
        else:
            ip_obj = ipaddress.ip_address(clean)
            return str(ip_obj), None
    except ValueError:
        ip_part = clean.split("/")[0].strip()
        try:
            ip_obj = ipaddress.ip_address(ip_part)
            return str(ip_obj), None
        except ValueError:
            return None, None


def parse_transit_subnets(spec: Any) -> Set[int]:
    """
    Parses prefix lengths from string, list, or set.
    Supports formats like:
      - '30, 31, 29, 28'
      - '/30, /31, /29, /28'
      - '28-31' or '/28-/31'
      - [28, 29, 30, 31]
    Returns a set of integers, e.g. {28, 29, 30, 31}.
    """
    if isinstance(spec, (set, list, tuple)):
        result = set()
        for x in spec:
            try:
                v = int(str(x).strip().lstrip("/"))
                if 1 <= v <= 32:
                    result.add(v)
            except ValueError:
                pass
        return result or {28, 29, 30, 31}

    if not isinstance(spec, str):
        return {28, 29, 30, 31}

    result = set()
    cleaned = spec.strip()
    range_match = re.match(r"^/?(\d+)\s*-\s*/?(\d+)$", cleaned)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        if start > end:
            start, end = end, start
        for v in range(start, end + 1):
            if 1 <= v <= 32:
                result.add(v)
        return result or {28, 29, 30, 31}

    tokens = re.split(r"[,;\s]+", cleaned)
    for token in tokens:
        token = token.strip().lstrip("/")
        if not token:
            continue
        sub_range = re.match(r"^(\d+)-(\d+)$", token)
        if sub_range:
            start, end = int(sub_range.group(1)), int(sub_range.group(2))
            if start > end:
                start, end = end, start
            for v in range(start, end + 1):
                if 1 <= v <= 32:
                    result.add(v)
            continue
        try:
            val = int(token)
            if 1 <= val <= 32:
                result.add(val)
        except ValueError:
            pass

    return result or {28, 29, 30, 31}


# ──────────────────────────────────────────────────────────────────────────────
# Core class
# ──────────────────────────────────────────────────────────────────────────────
class CiscoTracerouteMapper:
    # ───── initialisation ────────────────────────────────────────────────────
    def __init__(self, csv_file: str = "network_interfaces.csv") -> None:
        self.csv_file: str = csv_file
        # (iface, ip, zone, vrf, description)
        self.device_inventory: Dict[str, List[Tuple[str, str, str, str, str]]] = {}
        # Structured interface records: device -> list of dicts with net, ip, iface, etc.
        self.device_interfaces: Dict[str, List[dict]] = {}
        self.ip_to_device_map: Dict[str, Tuple[str, str, str, str, str]] = {}
        self.ip_to_network_map: Dict[str, Optional[ipaddress.IPv4Network]] = {}
        self.device_zones: Dict[str, str] = {}
        # traceroute settings
        self.resolve_dns: bool = False  # Default to False for speed
        self.max_hops: int = 20         # Default limited to 20 for speed
        self.timeout_base: int = 3
        self.max_retries: int = 2
        # Device-name keyword identifying WAN routers (case-insensitive)
        self.wan_keyword: str = "wanr"
        # Allowed transit subnet prefix lengths for inter-device link matching (default: /30, /31, /29, /28)
        self.transit_subnets: Set[int] = {28, 29, 30, 31}
        # Addon subnets: list of (network_obj, behind_device_str, info_str)
        self.addon_subnets: List[Tuple[ipaddress.IPv4Network, str, str]] = []
        # Additional interface info (same columns as inventory + 'info')
        self.extra_info_by_ip: Dict[str, List[str]] = {}
        self.extra_info_by_iface: Dict[Tuple[str, str], List[str]] = {}

    def set_transit_subnets(self, spec: Any) -> None:
        """Configures allowed subnet prefix lengths for inter-device link matching."""
        self.transit_subnets = parse_transit_subnets(spec)

    def get_transit_subnets_display(self) -> str:
        """Returns readable string of transit subnets, e.g. '/28, /29, /30, /31'."""
        if not self.transit_subnets:
            return "(none)"
        return ", ".join(f"/{p}" for p in sorted(self.transit_subnets))

    # ───── CSV loader ────────────────────────────────────────────────────────
    def load_csv_data(self) -> bool:
        print(f"Loading network inventory from {self.csv_file}…")
        try:
            with open(self.csv_file, encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    device = row["device_name"].strip()
                    iface = row["interface_name"].strip()
                    ip_sub = row["ip_address"].strip()
                    zone = row.get("zone", row.get("Zone", "Unknown")).strip()
                    vrf = row.get("vrf", "N/A").strip()
                    description = row.get("description", "").strip()

                    parsed_ip, net_obj = parse_ip_and_network(ip_sub)
                    if not parsed_ip:
                        continue                     # skip dynamic or empty

                    ip = parsed_ip
                    self.device_inventory.setdefault(device, []).append(
                        (iface, ip, zone, vrf, description)
                    )
                    self.device_interfaces.setdefault(device, []).append({
                        "device": device,
                        "iface": iface,
                        "ip": ip,
                        "network": net_obj,
                        "zone": zone,
                        "vrf": vrf,
                        "description": description,
                        "raw_ip": ip_sub,
                    })
                    self.ip_to_device_map[ip] = (device, iface, zone, vrf, description)
                    self.ip_to_network_map[ip] = net_obj
                    self.device_zones.setdefault(device, zone)

            print(f"✓ Loaded {len(self.device_inventory)} devices")
            print(f"✓ Total interfaces: {len(self.ip_to_device_map)}")
            return True

        except FileNotFoundError:
            print(f"Error: '{self.csv_file}' not found")
            return False
        except Exception as exc:
            return False

    def load_addon_subnets(self, filename: str = "addon_subnet.csv") -> None:
        """Loads additional subnet info from CSV."""
        if not os.path.exists(filename):
            return
        
        print(f"Loading addon subnets from {filename}…")
        count = 0
        try:
            with open(filename, encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    s_net = row.get("subnet", "").strip()
                    b_dev = row.get("behind_device", "").strip()
                    info = row.get("info", "").strip()
                    
                    if not s_net: continue
                    try:
                        net = ipaddress.ip_network(s_net, strict=False)
                        self.addon_subnets.append((net, b_dev, info))
                        count += 1
                    except ValueError:
                        pass
            print(f"✓ Loaded {count} addon subnets")
        except Exception as e:
            print(f"⚠️  Error loading {filename}: {e}")

    def check_addon_subnet(self, ip_str: str) -> List[Tuple[ipaddress.IPv4Network, str, str]]:
        """
        Checks if IP is in any addon subnet. 
        Returns list of (network_obj, behind_device, info_str) for ALL matches.
        """
        matches = []
        try:
            ip = ipaddress.ip_address(ip_str)
            for net, dev, info in self.addon_subnets:
                if ip in net:
                    matches.append((net, dev, info))
            
            if len(matches) > 0:
                return matches
        except ValueError:
            pass
        return []

    # ───── additional interface info ──────────────────────────────────────────
    def load_additional_int_info(self, filename: Optional[str] = None) -> None:
        """
        Loads an optional CSV with the same columns as network_interfaces.csv
        plus an extra 'info' column. Rows are matched to inventory interfaces
        by IP address, or by (device_name, interface_name) when no IP is given.
        """
        if filename:
            candidates = [filename]
        else:
            base = os.path.dirname(os.path.abspath(self.csv_file))
            names = ["additional_int_info.csv", "additiaon_int_info.csv"]
            candidates = names + [os.path.join(base, n) for n in names]
        path = next((c for c in candidates if os.path.exists(c)), None)
        if not path:
            if filename:
                print(f"⚠️  Additional info file '{filename}' not found")
            return

        print(f"Loading additional interface info from {path}…")
        count = 0
        try:
            with open(path, encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                # case-insensitive column lookup
                for raw in reader:
                    row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
                    info = row.get("info", "")
                    if not info:
                        continue
                    device = row.get("device_name", "")
                    iface = row.get("interface_name", "")
                    ip = row.get("ip_address", "").split("/")[0]

                    matched = False
                    try:
                        ipaddress.ip_address(ip)
                        self.extra_info_by_ip.setdefault(ip, []).append(info)
                        matched = True
                    except ValueError:
                        pass
                    if device and iface:
                        key = (device.lower(), iface.lower())
                        self.extra_info_by_iface.setdefault(key, []).append(info)
                        matched = True
                    count += matched
            print(f"✓ Loaded {count} additional interface info rows")
        except Exception as exc:
            print(f"⚠️  Error loading {path}: {exc}")

    def get_extra_info(
        self, ip: Optional[str], device: Optional[str] = None, iface: Optional[str] = None
    ) -> str:
        """
        Returns the 'info' text for an interface that matched the inventory.
        Lookup order: IP address, then (device, interface). Empty string if none.
        """
        if not ip and not (device and iface):
            return ""
        if ip and (device is None or iface is None):
            inv = self.ip_to_device_map.get(ip)
            if not inv:
                return ""           # only enrich interfaces found in inventory
            device, iface = inv[0], inv[1]
        infos = self.extra_info_by_ip.get(ip or "", [])
        if not infos and device and iface:
            infos = self.extra_info_by_iface.get((device.lower(), iface.lower()), [])
        # de-duplicate while preserving order
        return "; ".join(dict.fromkeys(infos))

    def get_iface_description(self, ip: Optional[str]) -> str:
        """Interface description from the inventory CSV ('' if none / N/A)."""
        if not ip:
            return ""
        desc = self.ip_to_device_map.get(ip, (None, None, None, None, ""))[4] or ""
        return "" if desc.strip().upper() in {"", "N/A", "NA", "NONE"} else desc.strip()

    def _details_suffix(self, ip: Optional[str]) -> str:
        """'  Desc: … [Info: …]' suffix for list-style output."""
        desc = self.get_iface_description(ip)
        info = self.get_extra_info(ip)
        s = f"  Desc: {desc}" if desc else ""
        if info:
            s += f"  [Info: {info}]"
        return s

    # ───── low-level traceroute helpers ──────────────────────────────────────
    def _test_connectivity(self, ip: str) -> bool:
        """Single-echo ping to confirm reachability (non-fatal)."""
        try:
            if platform.system().lower() == "windows":
                cmd = ["ping", "-n", "1", "-w", "3000", ip]
            else:
                cmd = ["ping", "-c", "1", "-W", "3", ip]
            return subprocess.run(cmd, capture_output=True).returncode == 0
        except Exception:
            return False

    def _parse_traceroute_line(
        self, line: str, system: str
    ) -> Optional[Tuple[int, Optional[str], bool]]:
        """
        Returns (hop_no, ip_or_None, is_timeout)
        or None if the line does not contain hop data.
        """
        if system == "windows":
            # timeout line
            if re.search(r"^\s*\d+.*\*", line) and "timed out" in line.lower():
                hop = int(re.findall(r"^\s*(\d+)", line)[0])
                return hop, None, True
            # success line
            m = re.search(r"^\s*(\d+)\s+.*?(\d+\.\d+\.\d+\.\d+)", line)
            if m:
                return int(m.group(1)), m.group(2), False
        else:  # unix
            if re.match(r"^\s*\d+\s+\*\s+\*\s+\*", line):
                hop = int(re.findall(r"^\s*(\d+)", line)[0])
                return hop, None, True
            pats = [
                r"^\s*(\d+)\s+(\d+\.\d+\.\d+\.\d+)",                       # plain IP
                r"^\s*(\d+)\s+\S+\s+\((\d+\.\d+\.\d+\.\d+)\)",              # host (IP)
                r"^\s*(\d+)\s+\S+\s+(\d+\.\d+\.\d+\.\d+)\s",                # host IP
            ]
            for p in pats:
                m = re.search(p, line)
                if m:
                    return int(m.group(1)), m.group(2), False
        return None

    def execute_traceroute_streaming(
        self,
        target_ip: str,
        source_ip: Optional[str] = None,
        stop_event: Optional[threading.Event] = None,
        proc_callback: Optional[Any] = None,
    ):
        """
        Generator yielding (hop_no, ip_or_None) in real time.
        Compatible with Unix 'traceroute' or Windows 'tracert'.
        """
        system = platform.system().lower()
        if system == "windows":
            cmd = ["tracert", "-h", str(self.max_hops), "-w", "5000", target_ip]
        else:
            cmd = [
                "traceroute",
                "-m",
                str(self.max_hops),
                "-w",
                str(self.timeout_base),
                "-q",
                "3",
                target_ip,
            ]
            if source_ip:
                cmd.extend(["-s", source_ip])

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                universal_newlines=True,
            )
            if proc_callback:
                proc_callback(proc)
        except FileNotFoundError:
            print("Traceroute executable not found on this system.")
            return
        except Exception as exc:
            print(f"Unable to launch traceroute: {exc}")
            return

        while True:
            if stop_event and stop_event.is_set():
                try:
                    proc.terminate()
                except Exception:
                    pass
                break

            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break  # process finished
                continue  # still running

            parsed = self._parse_traceroute_line(line.rstrip(), system)
            if parsed:
                hop_no, ip, _ = parsed
                yield hop_no, ip

        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # ───── subnet-based path interface resolution ─────────────────────────────
    def find_matching_subnet_interfaces(
        self, dev1: str, dev2: str
    ) -> Optional[Tuple[dict, dict]]:
        """
        Finds an interface on dev1 (outbound) and an interface on dev2 (inbound)
        that reside in the same subnet / IP network.
        Focuses on configured transit subnets (default: /30, /31, /29, /28).
        Returns (iface_dev1_dict, iface_dev2_dict) or None.
        """
        if not dev1 or not dev2 or dev1 == dev2:
            return None

        ifs1 = self.device_interfaces.get(dev1, [])
        ifs2 = self.device_interfaces.get(dev2, [])
        if not ifs1 or not ifs2:
            return None

        allowed_prefixes = self.transit_subnets or {28, 29, 30, 31}
        best_match = None
        best_score = -1

        for if1 in ifs1:
            net1 = if1.get("network")
            if net1 and net1.prefixlen not in allowed_prefixes and net1.prefixlen != 32:
                # if1 is explicitly in a non-transit subnet (e.g. /24, /16)
                continue

            ip1_str = if1.get("ip")
            try:
                ip1_obj = ipaddress.ip_address(ip1_str) if ip1_str else None
            except ValueError:
                ip1_obj = None

            for if2 in ifs2:
                net2 = if2.get("network")
                if net2 and net2.prefixlen not in allowed_prefixes and net2.prefixlen != 32:
                    # if2 is explicitly in a non-transit subnet (e.g. /24, /16)
                    continue

                ip2_str = if2.get("ip")
                try:
                    ip2_obj = ipaddress.ip_address(ip2_str) if ip2_str else None
                except ValueError:
                    ip2_obj = None

                score = -1

                # 1. Exact network match (both have network, prefixlen in allowed transit subnets)
                if (
                    net1
                    and net2
                    and net1.prefixlen in allowed_prefixes
                    and net2.prefixlen in allowed_prefixes
                ):
                    if net1 == net2:
                        score = 200 + net1.prefixlen
                    elif ip2_obj and ip2_obj in net1:
                        score = 150 + net1.prefixlen
                    elif ip1_obj and ip1_obj in net2:
                        score = 150 + net2.prefixlen

                # 2. One has network in allowed transit subnets, one has IP
                elif net1 and net1.prefixlen in allowed_prefixes and ip2_obj:
                    if ip2_obj in net1:
                        score = 150 + net1.prefixlen
                elif net2 and net2.prefixlen in allowed_prefixes and ip1_obj:
                    if ip1_obj in net2:
                        score = 150 + net2.prefixlen

                # 3. Neither has network or networks don't match, test point-to-point subnets in allowed prefixes
                elif ip1_obj and ip2_obj:
                    for prefix in sorted(allowed_prefixes, reverse=True):
                        try:
                            test_net = ipaddress.ip_network(f"{ip1_str}/{prefix}", strict=False)
                            if ip2_obj in test_net:
                                score = 50 + prefix
                                break
                        except ValueError:
                            pass

                if score > best_score:
                    best_score = score
                    best_match = (if1, if2)

        return best_match

    def find_interface_by_ip(
        self, device: str, target_ip_str: str
    ) -> Optional[dict]:
        """
        Finds an interface on device that directly owns target_ip_str or
        whose subnet contains target_ip_str.
        """
        if not device or not target_ip_str:
            return None
        ifs = self.device_interfaces.get(device, [])
        if not ifs:
            return None

        try:
            target_ip_obj = ipaddress.ip_address(target_ip_str)
        except ValueError:
            return None

        best_match = None
        best_score = -1

        for item in ifs:
            ip_str = item.get("ip")
            net = item.get("network")

            # Exact IP match
            if ip_str == target_ip_str:
                return item

            score = -1
            if net and 0 < net.prefixlen < 32:
                if target_ip_obj in net:
                    score = 100 + net.prefixlen
            elif ip_str:
                for prefix in [31, 30, 29, 28, 24]:
                    try:
                        test_net = ipaddress.ip_network(f"{ip_str}/{prefix}", strict=False)
                        if target_ip_obj in test_net:
                            score = 20 + prefix
                            break
                    except ValueError:
                        pass

            if score > best_score:
                best_score = score
                best_match = item

        return best_match

    def get_interface_record(
        self, device: Optional[str], iface: Optional[str]
    ) -> Optional[dict]:
        """Looks up the interface dictionary for a device and interface name."""
        if not device or not iface:
            return None
        ifs = self.device_interfaces.get(device, [])
        for item in ifs:
            if item.get("iface", "").strip().lower() == iface.strip().lower():
                return item
        return None

    def resolve_path_interfaces(
        self,
        hops: List[Tuple[int, Optional[str]]],
        target_ip: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> List[dict]:
        """
        Resolves Inbound and Outbound interfaces for every hop in the path by:
        1. Subnet matching between Device N (outbound) and Device N+1 (inbound).
        2. Interface subnet containment for source IP (ingress) and target IP (egress).
        3. Fallback to matched interface on hop IP if direction cannot be disambiguated.
        Populates individual metadata (vrf, zone, desc) for both IN and OUT interfaces.
        """
        resolved_hops: List[dict] = []
        for h_no, ip in hops:
            if ip is None:
                resolved_hops.append({
                    "hop_no": h_no,
                    "ip": None,
                    "device": None,
                    "matched_iface": None,
                    "in_iface": None,
                    "in_ip": None,
                    "in_zone": "-",
                    "in_vrf": "-",
                    "in_desc": "",
                    "out_iface": None,
                    "out_ip": None,
                    "out_zone": "-",
                    "out_vrf": "-",
                    "out_desc": "",
                    "next_hop": "* (timeout)",
                    "next_in_iface": None,
                    "zone": "-",
                    "vrf": "-",
                    "desc": "",
                    "is_timeout": True,
                })
            else:
                dev, iface, zone, vrf, desc = self.ip_to_device_map.get(
                    ip, (None, None, None, None, "")
                )
                if not dev and self.resolve_dns:
                    ptr = get_reverse_dns(ip)
                    if ptr:
                        dev = ptr.split(".")[0]
                resolved_hops.append({
                    "hop_no": h_no,
                    "ip": ip,
                    "device": dev,
                    "matched_iface": iface,
                    "in_iface": None,
                    "in_ip": None,
                    "in_zone": zone or "-",
                    "in_vrf": vrf or "-",
                    "in_desc": "",
                    "out_iface": None,
                    "out_ip": None,
                    "out_zone": zone or "-",
                    "out_vrf": vrf or "-",
                    "out_desc": "",
                    "next_hop": None,
                    "next_in_iface": None,
                    "zone": zone or "-",
                    "vrf": vrf or "-",
                    "desc": desc or "",
                    "is_timeout": False,
                })

        valid_indices = [
            idx for idx, h in enumerate(resolved_hops) if not h["is_timeout"]
        ]

        # Link consecutive valid hops
        for i in range(len(valid_indices) - 1):
            idx_curr = valid_indices[i]
            idx_next = valid_indices[i + 1]
            curr = resolved_hops[idx_curr]
            next_h = resolved_hops[idx_next]
            dev_curr = curr["device"]
            dev_next = next_h["device"]
            ip_curr = curr["ip"]
            ip_next = next_h["ip"]

            if dev_curr and dev_next and dev_curr != dev_next:
                match = self.find_matching_subnet_interfaces(dev_curr, dev_next)
                if match:
                    if_out, if_in = match
                    curr["out_iface"] = if_out["iface"]
                    curr["out_ip"] = if_out["ip"]
                    curr["out_zone"] = if_out["zone"]
                    curr["out_vrf"] = if_out.get("vrf", "-")
                    curr["out_desc"] = if_out.get("description", "")
                    next_h["in_iface"] = if_in["iface"]
                    next_h["in_ip"] = if_in["ip"]
                    next_h["in_zone"] = if_in["zone"]
                    next_h["in_vrf"] = if_in.get("vrf", "-")
                    next_h["in_desc"] = if_in.get("description", "")
                    curr["next_hop"] = f"{dev_next} ({if_in['iface']})"
                    curr["next_in_iface"] = f"{dev_next}:{if_in['iface']}"
                else:
                    if_out = self.find_interface_by_ip(dev_curr, ip_next)
                    if if_out:
                        curr["out_iface"] = if_out["iface"]
                        curr["out_ip"] = if_out["ip"]
                        curr["out_zone"] = if_out["zone"]
                        curr["out_vrf"] = if_out.get("vrf", "-")
                        curr["out_desc"] = if_out.get("description", "")
                    if_in = self.find_interface_by_ip(dev_next, ip_curr)
                    if if_in:
                        next_h["in_iface"] = if_in["iface"]
                        next_h["in_ip"] = if_in["ip"]
                        next_h["in_zone"] = if_in["zone"]
                        next_h["in_vrf"] = if_in.get("vrf", "-")
                        next_h["in_desc"] = if_in.get("description", "")
                    next_in_label = next_h["in_iface"] or ip_next
                    curr["next_hop"] = f"{dev_next} ({next_in_label})"
                    curr["next_in_iface"] = f"{dev_next}:{next_in_label}"
            elif dev_curr and not dev_next:
                if_out = self.find_interface_by_ip(dev_curr, ip_next)
                if if_out:
                    curr["out_iface"] = if_out["iface"]
                    curr["out_ip"] = if_out["ip"]
                    curr["out_zone"] = if_out["zone"]
                    curr["out_vrf"] = if_out.get("vrf", "-")
                    curr["out_desc"] = if_out.get("description", "")
                curr["next_hop"] = ip_next
                curr["next_in_iface"] = ip_next
            elif not dev_curr and dev_next:
                if_in = self.find_interface_by_ip(dev_next, ip_curr)
                if if_in:
                    next_h["in_iface"] = if_in["iface"]
                    next_h["in_ip"] = if_in["ip"]
                    next_h["in_zone"] = if_in["zone"]
                    next_h["in_vrf"] = if_in.get("vrf", "-")
                    next_h["in_desc"] = if_in.get("description", "")
                next_in_label = next_h["in_iface"] or ip_next
                curr["next_hop"] = f"{dev_next} ({next_in_label})"
                curr["next_in_iface"] = f"{dev_next}:{next_in_label}"
            else:
                curr["next_hop"] = ip_next
                curr["next_in_iface"] = ip_next

        # Inbound on first valid hop
        if valid_indices:
            first_h = resolved_hops[valid_indices[0]]
            if first_h["in_iface"] is None and first_h["device"]:
                if source_ip:
                    if_in = self.find_interface_by_ip(first_h["device"], source_ip)
                    if if_in:
                        first_h["in_iface"] = if_in["iface"]
                        first_h["in_ip"] = if_in["ip"]
                        first_h["in_zone"] = if_in["zone"]
                        first_h["in_vrf"] = if_in.get("vrf", "-")
                        first_h["in_desc"] = if_in.get("description", "")
                if first_h["in_iface"] is None:
                    if first_h["matched_iface"] and first_h["matched_iface"] != first_h["out_iface"]:
                        first_h["in_iface"] = first_h["matched_iface"]
                    elif first_h["out_iface"] is None and first_h["matched_iface"]:
                        first_h["out_iface"] = first_h["matched_iface"]
                        first_h["in_iface"] = "(ingress)"
                    else:
                        first_h["in_iface"] = "(ingress)"

        # Outbound on last valid hop
        if valid_indices:
            last_h = resolved_hops[valid_indices[-1]]
            if target_ip:
                if last_h["ip"] == target_ip:
                    last_h["out_iface"] = "Connected / Target"
                    last_h["next_hop"] = "Destination Reached"
                    last_h["next_in_iface"] = "Target Reached"
                    last_h["out_desc"] = "Destination Endpoint"
                elif last_h["device"]:
                    if_out = self.find_interface_by_ip(last_h["device"], target_ip)
                    if if_out:
                        last_h["out_iface"] = if_out["iface"]
                        last_h["out_ip"] = if_out["ip"]
                        last_h["out_zone"] = if_out["zone"]
                        last_h["out_vrf"] = if_out.get("vrf", "-")
                        last_h["out_desc"] = if_out.get("description", "")
                        last_h["next_hop"] = f"Target ({target_ip})"
                        last_h["next_in_iface"] = f"Target:{target_ip}"
                    else:
                        last_h["next_hop"] = f"Target ({target_ip})"
                        last_h["next_in_iface"] = f"Target:{target_ip}"
            if last_h["out_iface"] is None:
                if last_h["matched_iface"] and last_h["matched_iface"] != last_h["in_iface"]:
                    last_h["out_iface"] = last_h["matched_iface"]
                else:
                    last_h["out_iface"] = last_h["matched_iface"] or "-"

        # Fill remaining fallbacks and lookup descriptions for both interfaces
        for h in resolved_hops:
            if not h["is_timeout"]:
                if not h["out_iface"]:
                    h["out_iface"] = h["matched_iface"] or "-"
                if not h["in_iface"]:
                    if h["matched_iface"] and h["matched_iface"] != h["out_iface"]:
                        h["in_iface"] = h["matched_iface"]
                    else:
                        h["in_iface"] = "-"

                dev = h.get("device")
                # Inbound interface metadata
                in_if = h.get("in_iface")
                if in_if and in_if not in {"-", "(ingress)"} and dev:
                    rec_in = self.get_interface_record(dev, in_if)
                    if rec_in:
                        if not h.get("in_desc"):
                            h["in_desc"] = rec_in.get("description", "")
                        if not h.get("in_zone") or h["in_zone"] == "-":
                            h["in_zone"] = rec_in.get("zone", "-")
                        if not h.get("in_vrf") or h["in_vrf"] == "-":
                            h["in_vrf"] = rec_in.get("vrf", "-")
                        if not h.get("in_ip"):
                            h["in_ip"] = rec_in.get("ip")
                elif in_if == "(ingress)":
                    if not h.get("in_desc"):
                        h["in_desc"] = "(ingress from source)"

                # Outbound interface metadata
                out_if = h.get("out_iface")
                if out_if and out_if not in {"-", "Connected / Target"} and dev:
                    rec_out = self.get_interface_record(dev, out_if)
                    if rec_out:
                        if not h.get("out_desc"):
                            h["out_desc"] = rec_out.get("description", "")
                        if not h.get("out_zone") or h["out_zone"] == "-":
                            h["out_zone"] = rec_out.get("zone", "-")
                        if not h.get("out_vrf") or h["out_vrf"] == "-":
                            h["out_vrf"] = rec_out.get("vrf", "-")
                        if not h.get("out_ip"):
                            h["out_ip"] = rec_out.get("ip")
                elif out_if == "Connected / Target":
                    if not h.get("out_desc"):
                        h["out_desc"] = "Destination Endpoint"

                # Direct IP lookup fallback for description
                if h.get("ip"):
                    desc = self.get_iface_description(h["ip"])
                    if desc:
                        if h.get("matched_iface") == in_if and not h.get("in_desc"):
                            h["in_desc"] = desc
                        if h.get("matched_iface") == out_if and not h.get("out_desc"):
                            h["out_desc"] = desc

                in_z = h.get("in_zone")
                out_z = h.get("out_zone")
                if (
                    in_z
                    and out_z
                    and in_z != out_z
                    and in_z != "Unknown"
                    and out_z != "Unknown"
                    and in_z != "-"
                    and out_z != "-"
                ):
                    h["zone"] = f"{in_z} -> {out_z}"
                elif out_z and out_z not in {"Unknown", "-"}:
                    h["zone"] = out_z
                elif in_z and in_z not in {"Unknown", "-"}:
                    h["zone"] = in_z

        return resolved_hops

    def format_path_flow(self, resolved_hops: List[dict]) -> List[str]:
        """Generates formatted lines showing end-to-end device/link path flow."""
        lines = []
        valid_hops = [h for h in resolved_hops if not h.get("is_timeout")]
        if not valid_hops:
            return ["  (No responsive hops recorded)"]

        for idx, h in enumerate(valid_hops):
            dev = h.get("device") or h.get("ip") or "Unknown"
            in_if = h.get("in_iface") or "-"
            out_if = h.get("out_iface") or "-"
            ip_str = h.get("ip", "")

            # Zone formatting: prefer zone, or infer from in_zone -> out_zone
            zone = h.get("zone")
            if not zone or zone == "-":
                in_z = h.get("in_zone")
                out_z = h.get("out_zone")
                if (
                    in_z
                    and out_z
                    and in_z != out_z
                    and in_z not in {"-", "Unknown"}
                    and out_z not in {"-", "Unknown"}
                ):
                    zone = f"{in_z} -> {out_z}"
                elif out_z and out_z not in {"-", "Unknown"}:
                    zone = out_z
                elif in_z and in_z not in {"-", "Unknown"}:
                    zone = in_z
            zone_str = f" [{zone}]" if zone and zone != "-" else ""

            node_str = f"  [{idx + 1}] {dev} (IP: {ip_str}){zone_str} [In: {in_if} | Out: {out_if}]"
            lines.append(node_str)

            # Link connecting to next hop
            if idx < len(valid_hops) - 1:
                next_h = valid_hops[idx + 1]
                next_dev = next_h.get("device") or next_h.get("ip") or "Unknown"
                next_in = next_h.get("in_iface") or "-"
                if next_in == "-" and next_h.get("ip"):
                    next_target = f"{next_dev}:{next_h.get('ip')}"
                else:
                    next_target = f"{next_dev}:{next_in}"

                if out_if == "-" and ip_str:
                    src_target = f"{dev}:{ip_str}"
                else:
                    src_target = f"{dev}:{out_if}"

                link_desc = f"{src_target} ⇄ {next_target}"
                lines.append(f"       ↳ Link: {link_desc}")
            elif h.get("next_hop") and "Destination Reached" in h.get("next_hop", ""):
                lines.append(f"       ↳ Destination Reached ({ip_str})")
            elif h.get("next_hop") and "Connected" in h.get("next_hop", ""):
                lines.append(f"       ↳ Destination Reached ({ip_str})")
            elif h.get("next_hop"):
                lines.append(f"       ↳ Towards: {h['next_hop']}")
            else:
                lines.append(f"       ↳ Destination Reached ({ip_str})")

        return lines

    # ───── display helpers ────────────────────────────────────────────────────
    def _display_resolved_hop(self, rec: dict) -> None:
        """Prints one hop across 2 lines: line 1 for INBOUND, line 2 for OUTBOUND."""
        hop_no = rec.get("hop_no", 0)
        ip = rec.get("ip")
        if ip is None or rec.get("is_timeout"):
            print(f"{hop_no:>2}   {'* * * (timeout)':<20}")
            return

        ptr = None
        if self.resolve_dns:
            ptr = get_reverse_dns(ip)

        show_ip = f"{ip} ({ptr})" if ptr else ip
        device = rec.get("device") or "External/Unknown"

        in_iface = rec.get("in_iface") or "-"
        out_iface = rec.get("out_iface") or "-"
        next_hop = rec.get("next_hop") or "-"

        in_zone = rec.get("in_zone") or "-"
        out_zone = rec.get("out_zone") or "-"
        in_vrf = rec.get("in_vrf") or "-"
        out_vrf = rec.get("out_vrf") or "-"

        in_desc = rec.get("in_desc") or ""
        out_desc = rec.get("out_desc") or ""

        # Extra info per interface
        dev_for_info = device if device != "External/Unknown" else None
        in_info = self.get_extra_info(
            rec.get("in_ip"),
            dev_for_info,
            in_iface if in_iface not in {"-", "(ingress)"} else None,
        )
        out_info = self.get_extra_info(
            rec.get("out_ip"),
            dev_for_info,
            out_iface if out_iface not in {"-", "Connected / Target"} else None,
        )

        if in_info:
            in_desc = f"{in_desc} [Info: {in_info}]" if in_desc else f"[Info: {in_info}]"
        if out_info:
            out_desc = f"{out_desc} [Info: {out_info}]" if out_desc else f"[Info: {out_info}]"

        # Check addon subnet match on hop IP
        addons = self.check_addon_subnet(ip)
        if addons:
            devs = sorted(list(set(d for _, d, _ in addons)))
            dev_str = ", ".join(devs)
            in_desc = f"{in_desc} [Sub: {dev_str}]" if in_desc else f"[Sub: {dev_str}]"

        in_desc_show = in_desc or "-"
        out_desc_show = out_desc or "-"

        # Line 1: INBOUND interface
        print(
            f"{hop_no:>2}   {show_ip:<20} {device[:18]:<18} {'IN':<4} {in_iface[:18]:<18} "
            f"{'-':<24} {in_zone[:14]:<14} {in_vrf[:10]:<10} {in_desc_show}"
        )
        # Line 2: OUTBOUND interface
        print(
            f"{'':>2}   {'':<20} {'':<18} {'OUT':<4} {out_iface[:18]:<18} "
            f"{next_hop[:24]:<24} {out_zone[:14]:<14} {out_vrf[:10]:<10} {out_desc_show}"
        )

    def _display_hop(self, hop_no: int, ip: Optional[str]) -> None:
        """Fallback single-hop display."""
        if ip is None:
            print(f"{hop_no:>2}   {'* * * (timeout)':<20}")
            return
        rec = self.resolve_path_interfaces([(hop_no, ip)])[0]
        self._display_resolved_hop(rec)

    def display_full_path_summary(
        self,
        resolved_hops: List[dict],
        hops: List[Tuple[int, Optional[str]]],
        destination_reached: bool,
    ) -> None:
        """Displays full path table, path flow, and traceroute summary."""
        print("\n" + "=" * 150)
        print("FULL END-TO-END PATH (INBOUND & OUTBOUND INTERFACES)")
        print("=" * 150)
        print(
            f"{'No':>2}   {'IP Address':<20} {'Device Name':<18} {'Dir':<4} {'Interface':<18} "
            f"{'Next Hop (In Int)':<24} {'Zone':<14} {'VRF':<10} {'Description'}"
        )
        print("-" * 150)
        for rec in resolved_hops:
            self._display_resolved_hop(rec)
        print("-" * 150)

        # Flow Diagram
        print("\nPATH FLOW:")
        flow_lines = self.format_path_flow(resolved_hops)
        for line in flow_lines:
            print(line)

        print("\n" + "=" * 150)
        print("SUMMARY")
        print("=" * 150)
        print(f"Hops recorded: {len(hops)}")
        print(f"Destination reached: {'Yes' if destination_reached else 'No'}")

    # ───── main trace routine ────────────────────────────────────────────────
    def trace_to_destination_streaming(
        self, target_ip: str, description: str = ""
    ):
        print("\n" + "=" * 80)
        title = f"TRACING PATH TO {target_ip}"
        if description:
            title += f"  ({description})"
        print(title)

        # Check addon info
        addon_data_list = self.check_addon_subnet(target_ip)
        if addon_data_list:
            for _net, dev, info in addon_data_list:
                print(f"ℹ️  ADDON INFO: Matches {str(_net)} (Behind {dev}) [{info}]")

        print("=" * 80)

        # pre-flight ping
        if self._test_connectivity(target_ip):
            print("✓ Ping reachable, continuing with traceroute…")
        else:
            print("⚠️  Ping unreachable, continuing anyway…")

        print("-" * 150)
        print(
            f"{'No':>2}   {'IP Address':<20} {'Device Name':<18} {'Dir':<4} {'Interface':<18} "
            f"{'Next Hop (In Int)':<24} {'Zone':<14} {'VRF':<10} {'Description'}"
        )
        print("-" * 150)

        hops: List[Tuple[int, Optional[str]]] = []
        destination_reached = False
        buffered_hop: Optional[Tuple[int, Optional[str]]] = None
        prev_valid_hop: Optional[Tuple[int, str]] = None

        try:
            for hop_no, ip in self.execute_traceroute_streaming(target_ip):
                hops.append((hop_no, ip))

                if buffered_hop is not None:
                    # Resolve buffered_hop using lookahead context
                    sub_hops = []
                    if prev_valid_hop:
                        sub_hops.append(prev_valid_hop)
                    sub_hops.append(buffered_hop)
                    if ip is not None:
                        sub_hops.append((hop_no, ip))

                    resolved = self.resolve_path_interfaces(
                        sub_hops, target_ip=target_ip
                    )
                    target_rec = next(
                        (r for r in resolved if r["hop_no"] == buffered_hop[0]), None
                    )
                    if target_rec:
                        self._display_resolved_hop(target_rec)
                    if buffered_hop[1] is not None:
                        prev_valid_hop = (buffered_hop[0], buffered_hop[1])

                if ip is None:
                    # Timeout hop: print immediately
                    self._display_hop(hop_no, None)
                    buffered_hop = None
                else:
                    buffered_hop = (hop_no, ip)

                if ip == target_ip:
                    destination_reached = True
                    break
                time.sleep(0.3)  # small pacing for readability

            # Flush remaining buffered hop
            if buffered_hop is not None:
                sub_hops = []
                if prev_valid_hop:
                    sub_hops.append(prev_valid_hop)
                sub_hops.append(buffered_hop)
                resolved = self.resolve_path_interfaces(
                    sub_hops, target_ip=target_ip
                )
                target_rec = next(
                    (r for r in resolved if r["hop_no"] == buffered_hop[0]), None
                )
                if target_rec:
                    self._display_resolved_hop(target_rec)

        except KeyboardInterrupt:
            print("\nInterrupted by user.")
            if buffered_hop is not None:
                self._display_hop(buffered_hop[0], buffered_hop[1])

        # Full end-to-end path resolution & summary
        full_resolved = self.resolve_path_interfaces(hops, target_ip=target_ip)
        self.display_full_path_summary(full_resolved, hops, destination_reached)

    # ───── wrappers for hostname/IP ───────────────────────────────────────────
    def trace_to_destination(self, target: str, description: str = "") -> None:
        try:
            ip = resolve_target(target)
        except ValueError as err:
            print(err)
            return

        if not description and target != ip:
            description = target  # preserve original hostname
        self.trace_to_destination_streaming(ip, description)

    def trace_to_ip(self, ip: str) -> None:  # legacy alias
        self.trace_to_destination(ip)

    # ───── inventory display ─────────────────────────────────────────────────
    def display_device_inventory(self) -> None:
        print("\n" + "=" * 100)
        print("NETWORK DEVICE INVENTORY (grouped by zone)")
        print("=" * 100)

        zones: Dict[str, List[str]] = {}
        for dev, _ifs in self.device_inventory.items():
            zones.setdefault(self.device_zones.get(dev, "Unknown"), []).append(dev)

        for zone in sorted(zones):
            print(f"\n🌐 ZONE: {zone}")
            print("-" * 60)
            for dev in sorted(zones[zone]):
                print(f"\n📍 {dev}")
                print(f"{'Interface':<25} {'IP Address':<16} {'Zone':<15} {'VRF':<15} {'Description':<30} {'Info'}")
                print("-" * 130)
                for iface, ip, z, v, d in self.device_inventory[dev]:
                    info = self.get_extra_info(ip, dev, iface)
                    print(f"{iface:<25} {ip:<16} {z:<15} {v:<15} {d:<30} {info}")

    # ───── comparison features ───────────────────────────────────────────────
    def collect_trace(
        self, target_ip: str, silent: bool = False
    ) -> List[Tuple[int, Optional[str]]]:
        """Runs traceroute to target and returns list of (hop, ip)."""
        if not silent:
            print(f"   ► Tracing to {target_ip}...")
        hops = []
        try:
            for hop_no, ip in self.execute_traceroute_streaming(target_ip):
                hops.append((hop_no, ip))
                if not silent:
                    # Simple progress indicator
                    if ip:
                        print(f"     Hop {hop_no}: {ip}")
                    else:
                        print(f"     Hop {hop_no}: *")
        except KeyboardInterrupt:
            if not silent:
                print("     (Interrupted)")
        return hops

    def _display_comparison_grid(
        self,
        resolved_targets: List[Tuple[str, str]],
        trace_results: Dict[str, Dict[int, str]],
        max_hop: int,
        highlight_ips: Optional[Set[str]] = None
    ) -> None:
        """Displays side-by-side comparison of multiple traces."""
        print("\n" + "=" * 180)  # Widened header separator
        print("TRACE COMPARISON")
        print("Format: IP Address [Device Name - Interface Name] or [Sub: Subnet Description]")
        print("=" * 180)

        # Header
        header = f"{'Hop':<4}"
        col_width = 60  # Increased column width
        for orig_target, ip in resolved_targets:
            header += f"{orig_target[:col_width]:<{col_width}} "
        print(header)
        print("-" * len(header))

        info_legend: Dict[str, Tuple[str, str, str]] = {}  # hop_ip -> (dev, iface, info)

        for h in range(1, max_hop + 1):
            row_str = f"{h:<4}"

            # Check if all valid IPs at this hop are the same
            ips_at_hop = []
            for _, ip in resolved_targets:
                if ip in trace_results and h in trace_results[ip]:
                    ips_at_hop.append(trace_results[ip][h])
                else:
                    ips_at_hop.append(None)

            # Check distinct non-None IPs
            distinct_set = set(ips_at_hop)
            
            # Strict Matching: All must be identical and NOT None
            is_common = (len(distinct_set) == 1) and (None not in distinct_set)

            # Build the row string
            for i, (_, target_ip) in enumerate(resolved_targets):
                hop_ip = ips_at_hop[i]
                if hop_ip is None:
                    cell_text = "*"
                else:
                    # Enrich with device info
                    ptr = None
                    if self.resolve_dns:
                        ptr = get_reverse_dns(hop_ip)

                    device, iface, _, _, _ = self.ip_to_device_map.get(hop_ip, (None, None, None, None, None))

                    desc_suffix = ""
                    if device:
                        cell_text = f"{hop_ip} [{device} - {iface}]"
                        info = self.get_extra_info(hop_ip, device, iface)
                        desc = self.get_iface_description(hop_ip)
                        if info:
                            cell_text = f"{hop_ip} ℹ [{device} - {iface}]"
                        if desc:
                            desc_suffix = f" {desc}"
                        if info or desc:
                            info_legend.setdefault(hop_ip, (device, iface, desc, info))
                    else:
                        # Check addon
                        addons = self.check_addon_subnet(hop_ip)
                        if addons:
                            # Short format: IP [Sub: dev_name1, dev_name2]
                            devs = sorted(list(set(d for _, d, _ in addons)))
                            dev_str = ", ".join(devs)
                            cell_text = f"{hop_ip} [Sub: {dev_str}]"
                        elif ptr:
                            # Shorten PTR if too long
                            short_ptr = ptr.split('.')[0]
                            if len(short_ptr) > 25: # Increased length allowance
                                 short_ptr = short_ptr[:22] + "..."
                            cell_text = f"{hop_ip} ({short_ptr})"
                        else:
                            cell_text = hop_ip
                    
                    # Add highlight if applicable
                    if highlight_ips and hop_ip in highlight_ips:
                        cell_text += " ✅"
                    cell_text += desc_suffix

                # Truncate to col_width - 1
                row_str += f"{cell_text[:col_width-1]:<{col_width}} "

            if is_common:
                 row_str += " (MATCH)"

            print(row_str)

        if info_legend:
            print("\nℹ  Interface details (description / additional info):")
            for hop_ip, (device, iface, desc, info) in info_legend.items():
                parts = []
                if desc:
                    parts.append(f"Desc: {desc}")
                if info:
                    parts.append(f"Info: {info}")
                print(f"   {hop_ip:<16} {device} - {iface}: {' | '.join(parts)}")

    def compare_traces(self, targets: List[str]) -> None:
        """
        Traces multiple targets and displays a side-by-side comparison.
        """
        # 1. Resolve all targets
        resolved_targets = []
        print("\n" + "=" * 80)
        print("PREPARING TRACES")
        print("=" * 80)
        for t in targets:
            t = t.strip()
            if not t: continue
            try:
                ip = resolve_target(t)
                resolved_targets.append((t, ip))
            except ValueError as e:
                print(f"⚠️  Skipping {t}: {e}")

        if not resolved_targets:
            print("No valid targets to trace.")
            return

        # Display Addon Info
        for orig_t, ip in resolved_targets:
            addon_data_list = self.check_addon_subnet(ip)
            if addon_data_list:
                 for _net, dev, info in addon_data_list:
                     print(f"ℹ️  ADDON INFO for {orig_t} ({ip}): Matches {str(_net)} (Behind {dev}) [{info}]")

        # 2. Collect traces in parallel
        trace_results: Dict[str, Dict[int, str]] = {}  # ip -> {hop: ip_at_hop}
        max_hop_seen = 0

        print("\n" + "=" * 80)
        print(f"COLLECTING TRACE DATA (Max 5 parallel sessions)")
        print("=" * 80)
        
        # Pre-check connectivity sequentially (fast enough, avoids ping flood issues)
        for orig_target, ip in resolved_targets:
            if not self._test_connectivity(ip):
                print(f"⚠️  {orig_target} ({ip}) might be unreachable (ping failed).")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Map future to original IP
            future_to_ip = {
                executor.submit(self.collect_trace, ip, silent=True): ip 
                for _, ip in resolved_targets
            }
            
            completed_count = 0
            total_count = len(resolved_targets)
            
            for future in concurrent.futures.as_completed(future_to_ip):
                ip = future_to_ip[future]
                completed_count += 1
                try:
                    hops = future.result()
                    print(f"[{completed_count}/{total_count}] Trace completed for {ip}")
                    
                    # Convert list of tuples to dict
                    hop_map = {}
                    for h_no, h_ip in hops:
                        if h_ip:
                            hop_map[h_no] = h_ip
                            max_hop_seen = max(max_hop_seen, h_no)
                    trace_results[ip] = hop_map
                    
                except Exception as exc:
                    print(f"[{completed_count}/{total_count}] Trace failed for {ip}: {exc}")

        # 3. Compare and Display
        self._display_comparison_grid(resolved_targets, trace_results, max_hop_seen)

    # ───── troubleshooting mode ──────────────────────────────────────────────
    def find_nodes_by_query(self, query: str) -> Dict[str, List[str]]:
        """
        Finds devices/IPs matching the user query (Name/IP/Subnet).
        Returns dict {device: [matching_ips]}.
        """
        query = query.strip()
        matches: Dict[str, List[str]] = {}
        
        # 1. Direct device name match
        if query in self.device_inventory:
            for _, ip, _, _, _ in self.device_inventory[query]:
                matches.setdefault(query, []).append(ip)

        # 2. IP match
        if query in self.ip_to_device_map:
            dev, _, _, _, _ = self.ip_to_device_map[query]
            matches.setdefault(dev, []).append(query)
            
        # 3. Subnet match (only if looks like CIDR or IP)
        try:
            # Check if valid network string
            if "/" in query:
                net = ipaddress.ip_network(query, strict=False)
                # Scan all known IPs
                for ip_str in self.ip_to_device_map:
                    try:
                        if ipaddress.ip_address(ip_str) in net:
                            dev, _, _, _, _ = self.ip_to_device_map[ip_str]
                            matches.setdefault(dev, []).append(ip_str)
                    except ValueError:
                        continue
        except ValueError:
            pass

        return matches
        
    def troubleshooting_mode(self) -> None:
        """Interactive workflow to verify traffic through specific network elements."""
        monitored_devices: Set[str] = set()
        manual_ips: Set[str] = set()
        manual_subnets: List[ipaddress.IPv4Network] = []
        destinations: List[str] = []

        while True:
            # Display current state
            print("\n" + "=" * 80)
            print("🕵️  TROUBLESHOOTING MODE")
            print("=" * 80)
            
            # Helper to format lists
            def fmt_list(items):
                s = ", ".join(sorted([str(x) for x in items]))
                if len(s) > 60: s = s[:57] + "..."
                return s if s else "(None)"
            
            print(f"  • Monitored Devices: {fmt_list(monitored_devices)}")
            print(f"  • Manual IPs:        {fmt_list(manual_ips)}")
            print(f"  • Manual Subnets:    {fmt_list(manual_subnets)}")
            print(f"  • Destinations:      {fmt_list(destinations)}")
            print("-" * 80)
            print("1. Set Monitored Device/IP/Subnet")
            print("2. Set Destination IP(s)")
            print("3. Run Verification Trace")
            print("4. Return to Main Menu")
            print("-" * 80)
            
            choice = input("Select option (1-4): ").strip()

            if choice == "1":
                print("\nEnter a Device Name, IP Address, or Subnet that you expect traffic to pass through.")
                query = input("Search Query: ").strip()
                if not query: continue
                
                # 1. Search Inventory
                matches = self.find_nodes_by_query(query)
                if matches:
                    print(f"\n✓ Found {len(matches)} device(s) matching your query:")
                    for dev in sorted(matches):
                        ips = matches[dev]
                        print(f"  • {dev} (IPs: {', '.join(ips)})")
                    monitored_devices.update(matches.keys())
                    print(f"Updated monitored devices.")
                else:
                    # 2. Try Manual IP/Subnet
                    print("No directory match found. Checking as manual network entry...")
                    try:
                        # Try Subnet first (if it has /)
                        if "/" in query:
                            net = ipaddress.ip_network(query, strict=False)
                            manual_subnets.append(net)
                            print(f"✓ Added manual subnet monitor: {net}")
                        else:
                            # Try IP
                            ip = ipaddress.ip_address(query)
                            manual_ips.add(str(ip))
                            print(f"✓ Added manual IP monitor: {ip}")
                    except ValueError:
                         print("❌ Invalid input. Not a device name, valid IP, or valid subnet.")

            
            elif choice == "2":
                print("\nEnter destination IP(s) to trace to.")
                dest_input = input("Destination IP(s) (comma-separated): ").strip()
                if dest_input:
                    destinations = [t.strip() for t in dest_input.split(',') if t.strip()]
                    print(f"Updated destinations: {destinations}")

            elif choice == "3":
                if not destinations:
                    print("⚠️  Please set destinations first (Option 2).")
                    input("Press Enter...")
                    continue

                self.run_verification_batch(destinations, monitored_devices, manual_ips, manual_subnets)
                input("\nVerification complete. Press Enter to continue...")



            elif choice == "4":
                break
            else:
                print("Invalid selection.")

    def run_verification_batch(
        self,
        destinations: List[str],
        monitored_devices: Set[str],
        manual_ips: Set[str],
        manual_subnets: List[ipaddress.IPv4Network],
    ) -> None:
        """Executes the verification logic for a batch of destinations."""
        print(f"\nRunning traces to {len(destinations)} destinations...")

        # Store results for display and analysis
        resolved_targets = []
        trace_results: Dict[str, Dict[int, str]] = {}
        max_hop_seen = 0
        
        for tgt in destinations:
            try:
                dest_ip = resolve_target(tgt)
                resolved_targets.append((tgt, dest_ip))
            except ValueError:
                print(f"Skipping invalid target {tgt}")
                continue
        
        if not resolved_targets:
            return
        
        # Display Addon Info
        for orig_t, ip in resolved_targets:
            addon_data_list = self.check_addon_subnet(ip)
            if addon_data_list:
                for _net, dev, info in addon_data_list:
                    print(f"ℹ️  ADDON INFO for {orig_t} ({ip}): Matches {str(_net)} (Behind {dev}) [{info}]")

        # Collection Phase
        print(f"COLLECTING TRACE DATA (Max 5 parallel sessions)")
        print("=" * 80)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_ip = {
                executor.submit(self.collect_trace, ip, silent=True): ip 
                for _, ip in resolved_targets
            }
            
            completed_count = 0
            total_count = len(resolved_targets)
            
            for future in concurrent.futures.as_completed(future_to_ip):
                ip = future_to_ip[future]
                completed_count += 1
                try:
                    hops = future.result()
                    print(f"[{completed_count}/{total_count}] Trace completed for {ip}")
                    
                    # Convert list of tuples to dict
                    hop_map = {}
                    for h_no, h_ip in hops:
                        if h_ip:
                            hop_map[h_no] = h_ip
                            max_hop_seen = max(max_hop_seen, h_no)
                    trace_results[ip] = hop_map
                    
                except Exception as exc:
                    print(f"[{completed_count}/{total_count}] Trace failed for {ip}: {exc}")

        # Analysis Phase
        print("\n" + "=" * 80)
        print("PATH VERIFICATION ANALYSIS")
        print("=" * 80)

        # 1. Identify Common Path Elements
        common_ips = None
        for ip in trace_results:
            # distinct IPs in this trace
            trace_unique_ips = set(trace_results[ip].values())
            if common_ips is None:
                common_ips = trace_unique_ips
            else:
                common_ips = common_ips.intersection(trace_unique_ips)
        
        if common_ips:
            print("\n🔗 COMMON PATH ELEMENTS (Present in all traces):")
            # We want to sort them roughly by hop order. A bit tricky since hop IDs vary.
            # Heuristic: find the lowest hop ID this IP appears at in any trace.
            ip_sort_key = {}
            for ip in common_ips:
                min_h = 999
                for T_ip in trace_results:
                    for h, val in trace_results[T_ip].items():
                        if val == ip:
                            min_h = min(min_h, h)
                ip_sort_key[ip] = min_h
                
            for ip in sorted(common_ips, key=lambda x: ip_sort_key.get(x, 999)):
                dev, _, _, _, _ = self.ip_to_device_map.get(ip, (None, None, None, None, None))
                label = f"[{dev}]" if dev else ""
                print(f"  - {ip:<15} {label}")
            print("-" * 80)

        # 2. Per-Target Analysis
        verified_ips: Set[str] = set()
        # Store full match details: target -> list of (hop, ip, dev_name, type)
        match_details: Dict[str, List[Tuple[int, str, str, str]]] = {}
        # Store all inventory/device sightings: target -> list of (hop, ip, dev_name)
        all_inventory_sightings: Dict[str, List[Tuple[int, str, str]]] = {}

        for orig_target, ip in resolved_targets:
            hop_map = trace_results.get(ip, {})
            matches_for_target = []
            sightings_for_target = []
            
            for h in sorted(hop_map.keys()):
                h_ip_str = hop_map[h]
                matched_dev = None
                m_type = ""

                # 1. Inventory Check
                dev_at_hop, _, _, _, _ = self.ip_to_device_map.get(h_ip_str, (None, None, None, None, None))
                if dev_at_hop:
                    sightings_for_target.append((h, h_ip_str, dev_at_hop))
                    if dev_at_hop in monitored_devices:
                        matched_dev = dev_at_hop
                        m_type = "Inventory"

                # 2. Manual IP Check
                if not matched_dev and h_ip_str in manual_ips:
                    matched_dev = "Manual IP"
                    m_type = "Manual IP"
                
                # 3. Manual Subnet Check
                if not matched_dev:
                    try:
                        h_ip_obj = ipaddress.ip_address(h_ip_str)
                        for net in manual_subnets:
                            if h_ip_obj in net:
                                matched_dev = f"Subnet {net}"
                                m_type = "Manual Subnet"
                                break
                    except ValueError:
                        pass
                
                if matched_dev:
                    verified_ips.add(h_ip_str)
                    matches_for_target.append((h, h_ip_str, matched_dev, m_type))
            
            match_details[orig_target] = matches_for_target
            all_inventory_sightings[orig_target] = sightings_for_target

        self._display_comparison_grid(resolved_targets, trace_results, max_hop_seen, highlight_ips=verified_ips)

        print("\nPath Verification per Target:")
        
        for orig_target, ip in resolved_targets:
            print(f"\n► Target: {orig_target}")
            hop_map = trace_results.get(ip, {})
            target_hops = [(h, hop_map[h]) for h in sorted(hop_map.keys())]
            target_resolved = {
                r["hop_no"]: r for r in self.resolve_path_interfaces(target_hops, target_ip=ip)
            }

            # A. Verification Status
            matches = match_details.get(orig_target, [])
            if matches:
                print(f"  ✓ VERIFIED: Found {len(matches)} monitored hop(s):")
                for h, ip_str, dev, mtype in matches:
                    r = target_resolved.get(h)
                    in_out = f" [In: {r['in_iface']} | Out: {r['out_iface']}]" if r else ""
                    info_s = self._details_suffix(ip_str)
                    print(f"    - Hop {h:<2}: {dev:<20}{in_out} ({ip_str}){info_s}")
            else:
                if monitored_devices or manual_ips or manual_subnets:
                    print(f"  ❌ FAILURE: Did NOT pass through expected devices.")
                else:
                    print(f"  ℹ️  No monitored devices set - skipping verification.")

            # B. All Inventory Sightings
            sightings = all_inventory_sightings.get(orig_target, [])
            if sightings:
                print(f"  ℹ️  Inventory Devices on path:")
                for h, ip_str, dev in sightings:
                    # Mark if this was one of the verified ones
                    is_ver = " (Verified)" if any(m[1] == ip_str for m in matches) else ""
                    r = target_resolved.get(h)
                    in_out = f" [In: {r['in_iface']} | Out: {r['out_iface']}]" if r else ""
                    info_s = self._details_suffix(ip_str)
                    print(f"    - Hop {h:<2}: {dev:<20}{in_out} ({ip_str}){is_ver}{info_s}")

    # ───── source ↔ destination (WAN aware) ──────────────────────────────────
    def _hop_device(self, ip: Optional[str]) -> Optional[str]:
        """Device name for a hop IP (inventory first, PTR short-name fallback)."""
        if not ip:
            return None
        dev = self.ip_to_device_map.get(ip, (None, None, None, None, None))[0]
        if dev:
            return dev
        if self.resolve_dns:
            ptr = get_reverse_dns(ip)
            if ptr:
                return ptr.split(".")[0]
        return None

    def _is_wan_router(self, device: Optional[str]) -> bool:
        return bool(device) and self.wan_keyword.lower() in device.lower()

    def _last_wan_index(self, hops: List[Tuple[int, Optional[str]]]) -> Optional[int]:
        """Index of the WAN router closest to the traced endpoint (last one seen)."""
        for i in range(len(hops) - 1, -1, -1):
            if self._is_wan_router(self._hop_device(hops[i][1])):
                return i
        return None

    @staticmethod
    def _trim_trace(
        hops: List[Tuple[int, Optional[str]]], target_ip: str
    ) -> List[Tuple[int, Optional[str]]]:
        """Cut the trace at the target and drop trailing timeouts."""
        out: List[Tuple[int, Optional[str]]] = []
        for h, ip in hops:
            out.append((h, ip))
            if ip == target_ip:
                break
        while out and out[-1][1] is None:
            out.pop()
        return out

    def _hop_info(self, ip: str) -> Tuple[str, str, str]:
        """Returns (device_label, interface, zone) for display."""
        device, iface, zone, _vrf, _desc = self.ip_to_device_map.get(
            ip, (None, None, None, None, None)
        )
        if device:
            return device, iface or "", zone or ""
        addons = self.check_addon_subnet(ip)
        if addons:
            devs = ", ".join(sorted({d for _, d, _ in addons}))
            return f"[Sub: {devs}]", "", ""
        ptr_dev = self._hop_device(ip)
        if ptr_dev:
            return f"({ptr_dev})", "", ""
        return "External/Unknown", "", ""

    def _print_combined_path(
        self, path: List[Tuple[str, Optional[str], str]]
    ) -> None:
        """Prints stitched path rows with Inbound and Outbound interfaces."""
        hop_items = [(idx + 1, ip) for idx, (_, ip, _) in enumerate(path) if ip is not None]
        resolved_map = {}
        if hop_items:
            resolved_list = self.resolve_path_interfaces(hop_items)
            for r in resolved_list:
                resolved_map[r["hop_no"]] = r

        print("-" * 150)
        print(
            f"{'#':>3}  {'Segment':<10} {'IP Address':<16} {'Device Name':<18} {'Dir':<4} "
            f"{'Interface':<18} {'Next Hop (In Int)':<22} {'Zone':<12} {'VRF':<8} {'Description':<25} Note"
        )
        print("-" * 150)
        n = 0
        resolved_for_flow = []
        for seg, ip, note in path:
            if seg == "WAN":
                print(f"{'':>3}  {'':<10} {'≈' * 18}  {note}  {'≈' * 18}")
                continue
            n += 1
            if ip is None:
                print(f"{n:>3}  {seg:<10} {'*':<16} {'(timeout)':<18}")
                continue
            r = resolved_map.get(n)
            dev, matched_iface, zone = self._hop_info(ip)
            in_iface = r.get("in_iface") if r else "-"
            out_iface = r.get("out_iface") if r else (matched_iface or "-")
            next_hop = r.get("next_hop") if r else "-"

            in_zone = r.get("in_zone") if r and r.get("in_zone") and r["in_zone"] != "-" else zone
            out_zone = r.get("out_zone") if r and r.get("out_zone") and r["out_zone"] != "-" else zone
            in_vrf = r.get("in_vrf", "-") if r else "-"
            out_vrf = r.get("out_vrf", "-") if r else "-"

            in_desc = r.get("in_desc") if r and r.get("in_desc") else self.get_iface_description(ip)
            out_desc = r.get("out_desc") if r and r.get("out_desc") else self.get_iface_description(ip)

            wan_note = "🌐 WAN router" if self._is_wan_router(self._hop_device(ip)) else ""
            full_note = f"{note} {wan_note}".strip() if note else wan_note

            # Line 1: INBOUND
            print(
                f"{n:>3}  {seg:<10} {ip:<16} {dev[:18]:<18} {'IN':<4} "
                f"{in_iface[:18]:<18} {'-':<22} {in_zone[:12]:<12} {in_vrf[:8]:<8} {in_desc[:25]:<25} {full_note}"
            )
            # Line 2: OUTBOUND
            print(
                f"{'':>3}  {'':<10} {'':<16} {'':<18} {'OUT':<4} "
                f"{out_iface[:18]:<18} {next_hop[:22]:<22} {out_zone[:12]:<12} {out_vrf[:8]:<8} {out_desc[:25]:<25}"
            )
            if r:
                resolved_for_flow.append(r)
        print("-" * 150)

        # Flow Diagram
        if resolved_for_flow:
            print("\nPATH FLOW:")
            for line in self.format_path_flow(resolved_for_flow):
                print(line)
            print("-" * 150)

    def trace_source_destination(self, source: str, destination: str) -> None:
        """
        Traces from this host to SOURCE and to DESTINATION. If both traces pass
        through a WAN router (device name contains self.wan_keyword) the two
        sites are considered connected over the WAN and the paths are stitched:

            SOURCE → … → src-site WANR ≈≈ WAN ≈≈ dst-site WANR → … → DESTINATION

        The source-side segment is the reverse of the trace to SOURCE, so it is
        an inferred path (actual return routing may differ).
        """
        print("\n" + "=" * 80)
        print(f"SOURCE ↔ DESTINATION PATH   ({source}  →  {destination})")
        print(f"WAN router keyword: '{self.wan_keyword}'")
        print("=" * 80)

        try:
            src_ip = resolve_target(source)
            dst_ip = resolve_target(destination)
        except ValueError as err:
            print(err)
            return
        if src_ip == dst_ip:
            print("Source and destination resolve to the same IP – nothing to do.")
            return

        for label, orig, ip in (("Source", source, src_ip), ("Destination", destination, dst_ip)):
            for _net, dev, info in self.check_addon_subnet(ip):
                print(f"ℹ️  ADDON INFO for {label} {orig} ({ip}): Matches {_net} (Behind {dev}) [{info}]")
            if not self._test_connectivity(ip):
                print(f"⚠️  {label} {orig} ({ip}) might be unreachable (ping failed).")

        print("\nCollecting traces to source and destination in parallel…")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f_src = ex.submit(self.collect_trace, src_ip, True)
            f_dst = ex.submit(self.collect_trace, dst_ip, True)
            src_hops = self._trim_trace(f_src.result(), src_ip)
            dst_hops = self._trim_trace(f_dst.result(), dst_ip)

        # Side-by-side view of the raw traces
        resolved = [(f"SRC: {source}", src_ip), (f"DST: {destination}", dst_ip)]
        results = {
            src_ip: {h: ip for h, ip in src_hops if ip},
            dst_ip: {h: ip for h, ip in dst_hops if ip},
        }
        max_hop = max([h for h, _ in src_hops + dst_hops] or [0])
        self._display_comparison_grid(resolved, results, max_hop)

        def seg(ip: Optional[str], default: str) -> str:
            if ip == src_ip:
                return "SOURCE"
            if ip == dst_ip:
                return "DEST"
            return default

        src_reached = bool(src_hops) and src_hops[-1][1] == src_ip
        dst_reached = bool(dst_hops) and dst_hops[-1][1] == dst_ip

        ia = self._last_wan_index(src_hops)
        ib = self._last_wan_index(dst_hops)
        path: List[Tuple[str, Optional[str], str]] = []

        print("\n" + "=" * 80)
        print("COMBINED END-TO-END PATH")
        print("=" * 80)

        if ia is not None and ib is not None:
            wan_a_ip, wan_b_ip = src_hops[ia][1], dst_hops[ib][1]
            dev_a, dev_b = self._hop_device(wan_a_ip), self._hop_device(wan_b_ip)

            if not src_reached:
                path.append(("SOURCE", src_ip, "not reached by traceroute"))
            for _, ip in reversed(src_hops[ia + 1:]):
                path.append((seg(ip, "SRC-SITE"), ip, ""))

            if dev_a == dev_b:
                print(f"✓ Both paths converge at WAN router {dev_a} (same site / hub).")
                path.append(("WAN-RTR", wan_a_ip, ""))
                if wan_b_ip != wan_a_ip:
                    path.append(("WAN-RTR", wan_b_ip, ""))
            else:
                print(f"✓ Sites are connected via WAN: {dev_a}  ≈≈ WAN ≈≈  {dev_b}")
                path.append(("SRC-WAN", wan_a_ip, ""))
                path.append(("WAN", None, f"WAN  {dev_a} ⇄ {dev_b}"))
                path.append(("DST-WAN", wan_b_ip, ""))

            for _, ip in dst_hops[ib + 1:]:
                path.append((seg(ip, "DST-SITE"), ip, ""))
            if not dst_reached:
                path.append(("DEST", dst_ip, "not reached by traceroute"))

            self._print_combined_path(path)
            print("ℹ️  Source-side segment is the reverse of the trace to the source (inferred).")
        else:
            missing = []
            if ia is None:
                missing.append("source")
            if ib is None:
                missing.append("destination")
            print(f"⚠️  No '{self.wan_keyword}' WAN router found in the trace to the "
                  f"{' and '.join(missing)} – sites are not linked via WAN.")

            # Fallback: pivot on the last hop common to both traces (same site)
            common = -1
            for i in range(min(len(src_hops), len(dst_hops))):
                a_ip, b_ip = src_hops[i][1], dst_hops[i][1]
                if a_ip and a_ip == b_ip:
                    common = i
                elif a_ip != b_ip:
                    break
            if common < 0:
                print("   No common hop either – unable to build a combined path.")
                return

            pivot_ip = src_hops[common][1]
            print(f"   Building local path via last common hop {pivot_ip}.")
            if not src_reached:
                path.append(("SOURCE", src_ip, "not reached by traceroute"))
            for _, ip in reversed(src_hops[common + 1:]):
                path.append((seg(ip, "SRC-SIDE"), ip, ""))
            path.append(("PIVOT", pivot_ip, "last common hop"))
            for _, ip in dst_hops[common + 1:]:
                path.append((seg(ip, "DST-SIDE"), ip, ""))
            if not dst_reached:
                path.append(("DEST", dst_ip, "not reached by traceroute"))
            self._print_combined_path(path)

    # ───── interactive menu ──────────────────────────────────────────────────
    def _configure_settings(self) -> None:
        """Change max_hops / timeout_base / max_retries interactively."""
        print("\n" + "=" * 60)
        print("⚙️  TRACEROUTE SETTINGS")
        print("=" * 60)
        try:
            new_hops = input(f"Max hops [{self.max_hops}]: ").strip()
            if new_hops:
                self.max_hops = max(1, min(255, int(new_hops)))

            new_timeout = input(f"Hop timeout seconds [{self.timeout_base}]: ").strip()
            if new_timeout:
                self.timeout_base = max(1, min(30, int(new_timeout)))

            new_retry = input(f"Max retries (unused) [{self.max_retries}]: ").strip()
            if new_retry:
                self.max_retries = max(0, min(5, int(new_retry)))

            new_kw = input(f"WAN router keyword [{self.wan_keyword}]: ").strip()
            if new_kw:
                self.wan_keyword = new_kw

            new_subnets = input(
                f"Transit subnets (e.g. 30,31,29,28 or 28-31) [{self.get_transit_subnets_display()}]: "
            ).strip()
            if new_subnets:
                self.set_transit_subnets(new_subnets)
        except ValueError:
            print("Invalid entry – settings unchanged.")
        print("Settings now:")
        print(f"  max_hops = {self.max_hops}")
        print(f"  timeout  = {self.timeout_base}s")
        print(f"  retries  = {self.max_retries}")
        print(f"  wan kw   = {self.wan_keyword}")
        print(f"  transit  = {self.get_transit_subnets_display()}")

    def interactive_menu(self) -> None:
        while True:
            dns_state = "ON" if self.resolve_dns else "OFF"
            print("\n" + "=" * 80)
            print("🌐 ENHANCED CISCO NETWORK TRACEROUTE MAPPER")
            print("=" * 80)
            print("1. Display Device Inventory")
            print("2. Trace to Single Destination")
            print("3. Trace & Compare Multiple Destinations")
            print("4. Troubleshooting Mode (Verify Path)")
            print("5. Trace Source ↔ Destination (WAN-aware combined path)")
            print("6. Configure Traceroute Settings")
            print(f"7. Toggle DNS Resolution (Current: {dns_state})")
            print("8. Launch GUI Interface")
            print("9. Exit")
            print("-" * 80)
            choice = input("Select option (1-9): ").strip()

            if choice == "1":
                self.display_device_inventory()
            elif choice == "2":
                target = input("Enter IP or hostname: ").strip()
                if target:
                    self.trace_to_destination(target)
            elif choice == "3":
                targets_str = input("Enter comma-separated IPs/hostnames: ").strip()
                if targets_str:
                    targets = [t.strip() for t in targets_str.split(',')]
                    self.compare_traces(targets)
            elif choice == "4":
                self.troubleshooting_mode()
            elif choice == "5":
                src = input("Enter SOURCE IP or hostname: ").strip()
                dst = input("Enter DESTINATION IP or hostname: ").strip()
                if src and dst:
                    self.trace_source_destination(src, dst)
                else:
                    print("Both source and destination are required.")
            elif choice == "6":
                self._configure_settings()
            elif choice == "7":
                self.resolve_dns = not self.resolve_dns
                print(f"DNS Resolution is now { 'ON' if self.resolve_dns else 'OFF' }")
            elif choice == "8":
                launch_gui(mapper=self)
            elif choice == "9":
                print("Good-bye!")
                break
            else:
                print("Invalid selection.")
            input("\nPress Enter to continue…")


# ──────────────────────────────────────────────────────────────────────────────
# GUI Interface (Tkinter & TTK - Standard Library Only)
# ──────────────────────────────────────────────────────────────────────────────
class TraceINTGUI:
    """
    Graphical User Interface for Cisco Network Traceroute Mapper.
    Uses Python standard library (tkinter & ttk) with zero external dependencies.
    Provides resizable columns, live updates, 2-line hop tables, and PATH FLOW diagrams.
    """

    def __init__(self, root: Any, mapper: Optional[CiscoTracerouteMapper] = None):
        if not TKINTER_AVAILABLE:
            raise RuntimeError("Tkinter is not available in this Python installation.")

        self.root = root
        self.root.title("Cisco Network Traceroute Mapper (TraceINT GUI)")
        self.root.geometry("1240x820")
        self.root.minsize(920, 600)

        # Apply ttk theme if available
        style = ttk.Style(self.root)
        available_themes = style.theme_names()
        for preferred in ("clam", "vista", "alt", "default"):
            if preferred in available_themes:
                try:
                    style.theme_use(preferred)
                except Exception:
                    pass
                break

        self.mapper = mapper if mapper is not None else CiscoTracerouteMapper()
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self.is_tracing = False
        self.active_proc = None
        self.last_resolved_hops = []

        self._init_variables()
        self._build_ui()
        self._bind_events()
        self.load_inventory()

        # Start periodic queue polling
        self.root.after(50, self._process_queue)

    def _init_variables(self) -> None:
        self.target_var = tk.StringVar()
        self.source_var = tk.StringVar()
        self.csv_var = tk.StringVar(value=self.mapper.csv_file or "network_interfaces.csv")
        self.extra_info_var = tk.StringVar(value="additional_int_info.csv")
        self.wan_var = tk.StringVar(value=self.mapper.wan_keyword or "wanr")
        self.max_hops_var = tk.StringVar(value=str(self.mapper.max_hops or 30))
        self.timeout_var = tk.StringVar(value=str(self.mapper.timeout_base or 2))
        self.dns_var = tk.BooleanVar(value=self.mapper.resolve_dns)
        self.transit_subnets_var = tk.StringVar(value=self.mapper.get_transit_subnets_display())
        self.status_var = tk.StringVar(value="Ready")
        self.stats_var = tk.StringVar(value="Inventory: 0 devices")

        # Column definitions: (default_width, min_width, stretch_boolean)
        self.columns = (
            "hop",
            "ip",
            "device",
            "dir",
            "interface",
            "next_hop",
            "zone",
            "vrf",
            "description",
            "extra_info",
        )
        self.col_titles = {
            "hop": "No",
            "ip": "IP Address",
            "device": "Device Name",
            "dir": "Dir",
            "interface": "Interface",
            "next_hop": "Next Hop (In Int)",
            "zone": "Zone",
            "vrf": "VRF",
            "description": "Description",
            "extra_info": "Extra Info",
        }
        self.default_col_widths = {
            "hop": (50, 35, False),
            "ip": (145, 80, False),
            "device": (150, 80, False),
            "dir": (55, 40, False),
            "interface": (130, 70, False),
            "next_hop": (180, 90, False),
            "zone": (120, 60, False),
            "vrf": (80, 50, False),
            "description": (280, 100, True),
            "extra_info": (180, 80, False),
        }

    def _build_ui(self) -> None:
        main_container = ttk.Frame(self.root, padding="8 8 8 6")
        main_container.pack(fill="both", expand=True)

        # Top Control & Settings Panel
        self._build_input_panel(main_container)

        # Center Notebook: Table, Path Flow, Console Log
        self._build_notebook(main_container)

        # Bottom Status Bar
        self._build_status_bar(main_container)

    def _build_input_panel(self, parent: ttk.Frame) -> None:
        input_frame = ttk.LabelFrame(parent, text=" Traceroute Target & Settings ", padding="10 8 10 8")
        input_frame.pack(fill="x", padx=2, pady=(0, 6))

        # Row 1: Target and Source inputs
        row1 = ttk.Frame(input_frame)
        row1.pack(fill="x", pady=2)

        ttk.Label(row1, text="Target (IP / Host):", font=("TkDefaultFont", 9, "bold")).pack(side="left", padx=(0, 4))
        self.target_entry = ttk.Entry(row1, textvariable=self.target_var, width=24)
        self.target_entry.pack(side="left", padx=(0, 16))
        self.target_entry.focus_set()

        ttk.Label(row1, text="Source (Optional / WAN):").pack(side="left", padx=(0, 4))
        self.source_entry = ttk.Entry(row1, textvariable=self.source_var, width=22)
        self.source_entry.pack(side="left", padx=(0, 16))

        ttk.Label(row1, text="WAN Keyword:").pack(side="left", padx=(0, 4))
        ttk.Entry(row1, textvariable=self.wan_var, width=8).pack(side="left", padx=(0, 16))

        ttk.Label(row1, text="Max Hops:").pack(side="left", padx=(0, 4))
        ttk.Spinbox(row1, from_=1, to=255, textvariable=self.max_hops_var, width=4).pack(side="left", padx=(0, 12))

        ttk.Label(row1, text="Timeout (s):").pack(side="left", padx=(0, 4))
        ttk.Spinbox(row1, from_=1, to=30, textvariable=self.timeout_var, width=4).pack(side="left", padx=(0, 12))

        ttk.Checkbutton(row1, text="Resolve DNS", variable=self.dns_var).pack(side="left")

        # Row 2: CSV Paths & Transit Subnets
        row2 = ttk.Frame(input_frame)
        row2.pack(fill="x", pady=(6, 2))

        ttk.Label(row2, text="Inventory CSV:").pack(side="left", padx=(0, 4))
        ttk.Entry(row2, textvariable=self.csv_var, width=26).pack(side="left", padx=(0, 4))
        ttk.Button(row2, text="Browse…", width=8, command=self.browse_inventory_csv).pack(side="left", padx=(0, 12))

        ttk.Label(row2, text="Extra Info CSV:").pack(side="left", padx=(0, 4))
        ttk.Entry(row2, textvariable=self.extra_info_var, width=26).pack(side="left", padx=(0, 4))
        ttk.Button(row2, text="Browse…", width=8, command=self.browse_extra_info_csv).pack(side="left", padx=(0, 12))

        ttk.Label(row2, text="Transit Subnets:").pack(side="left", padx=(0, 4))
        ttk.Entry(row2, textvariable=self.transit_subnets_var, width=16).pack(side="left", padx=(0, 12))

        ttk.Button(row2, text="🔄 Reload CSV", command=self.load_inventory).pack(side="left")

        # Row 3: Action Buttons
        row3 = ttk.Frame(input_frame)
        row3.pack(fill="x", pady=(8, 2))

        self.btn_start = ttk.Button(row3, text="▶ Start Trace", width=14, command=self.start_trace)
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_wan = ttk.Button(
            row3, text="⇄ Source ↔ Dest WAN Trace", width=26, command=self.start_wan_trace
        )
        self.btn_wan.pack(side="left", padx=(0, 8))

        self.btn_stop = ttk.Button(row3, text="⏹ Stop", width=10, command=self.stop_trace, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 8))

        ttk.Button(row3, text="🧹 Clear Results", width=14, command=self.clear_results).pack(side="left", padx=(0, 8))

    def _build_notebook(self, parent: ttk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True, padx=2, pady=2)

        # Tab 1: Full Path Table
        self.tab_table = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(self.tab_table, text=" 📊 Full Path Table (In/Out Interfaces) ")
        self._build_table_tab(self.tab_table)

        # Tab 2: Path Flow Diagram
        self.tab_flow = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(self.tab_flow, text=" 🗺️ Path Flow Diagram ")
        self._build_flow_tab(self.tab_flow)

        # Tab 3: Console Log
        self.tab_log = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(self.tab_log, text=" 📝 Live Console Log ")
        self._build_console_tab(self.tab_log)

    def _build_table_tab(self, parent: ttk.Frame) -> None:
        # Table Toolbar with column adjustment controls
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(2, 4))

        ttk.Button(toolbar, text="↔ Auto-fit Column Widths", command=self.autofit_columns).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="↺ Reset Column Widths", command=self.reset_column_widths).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="📋 Copy Selected Rows", command=self.copy_selected_rows).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="💾 Export Table to CSV…", command=self.export_table_csv).pack(side="left", padx=(0, 12))

        ttk.Label(
            toolbar,
            text="💡 Tip: Drag column headers to adjust widths manually. Double-click a header to auto-fit.",
            foreground="#555555",
            font=("TkDefaultFont", 8),
        ).pack(side="left")

        # Treeview Container
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=self.columns,
            show="headings",
            selectmode="extended",
        )

        # Configure columns with resizable/draggable widths
        for col in self.columns:
            w, min_w, stretch = self.default_col_widths[col]
            title = self.col_titles[col]
            self.tree.heading(col, text=title)
            self.tree.column(col, width=w, minwidth=min_w, stretch=stretch)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Tags styling
        self.tree.tag_configure("in_row", background="#f5f7fa")
        self.tree.tag_configure("out_row", background="#ffffff")
        self.tree.tag_configure("timeout_row", background="#fff9db", foreground="#856404")
        self.tree.tag_configure("target_row", background="#e6fcf5", foreground="#0b7285")

    def _build_flow_tab(self, parent: ttk.Frame) -> None:
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(2, 4))

        ttk.Button(toolbar, text="📋 Copy PATH FLOW", command=self.copy_path_flow).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="💾 Save Flow as Text…", command=self.save_path_flow).pack(side="left")

        flow_frame = ttk.Frame(parent)
        flow_frame.pack(fill="both", expand=True)

        self.flow_text = tk.Text(
            flow_frame,
            wrap="none",
            font=("TkFixedFont", 10),
            bg="#fcfdfe",
            fg="#212529",
            padx=10,
            pady=8,
        )
        flow_vsb = ttk.Scrollbar(flow_frame, orient="vertical", command=self.flow_text.yview)
        flow_hsb = ttk.Scrollbar(flow_frame, orient="horizontal", command=self.flow_text.xview)
        self.flow_text.configure(yscrollcommand=flow_vsb.set, xscrollcommand=flow_hsb.set)

        self.flow_text.grid(row=0, column=0, sticky="nsew")
        flow_vsb.grid(row=0, column=1, sticky="ns")
        flow_hsb.grid(row=1, column=0, sticky="ew")

        flow_frame.grid_rowconfigure(0, weight=1)
        flow_frame.grid_columnconfigure(0, weight=1)

        self.flow_text.insert("end", "(No traceroute run yet. Enter a target and click Start Trace)\n")

    def _build_console_tab(self, parent: ttk.Frame) -> None:
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(2, 4))

        ttk.Button(toolbar, text="📋 Copy Log", command=self.copy_log).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="🧹 Clear Log", command=self.clear_log).pack(side="left")

        log_frame = ttk.Frame(parent)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame,
            wrap="none",
            font=("TkFixedFont", 9),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="#ffffff",
            padx=8,
            pady=6,
        )
        log_vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_hsb = ttk.Scrollbar(log_frame, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=log_vsb.set, xscrollcommand=log_hsb.set)

        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_vsb.grid(row=0, column=1, sticky="ns")
        log_hsb.grid(row=1, column=0, sticky="ew")

        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        status_frame = ttk.Frame(parent, padding="2 4 2 2")
        status_frame.pack(fill="x", pady=(4, 0))

        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, relief="sunken", anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.progress = ttk.Progressbar(status_frame, orient="horizontal", length=180)
        self.progress.pack(side="left", padx=(0, 6))

        self.stats_label = ttk.Label(status_frame, textvariable=self.stats_var, relief="sunken", anchor="e", width=36)
        self.stats_label.pack(side="right")

    def _bind_events(self) -> None:
        self.target_entry.bind("<Return>", lambda _e: self.start_trace())
        self.source_entry.bind("<Return>", lambda _e: self.start_wan_trace())

        # Header double click to auto-fit clicked column
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        # Context menu on right click
        self.tree.bind("<Button-3>", self._show_tree_context_menu)

    def _on_tree_double_click(self, event: Any) -> None:
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            col_id = self.tree.identify_column(event.x)
            if col_id:
                try:
                    idx = int(col_id.replace("#", "")) - 1
                    if 0 <= idx < len(self.columns):
                        self.autofit_single_column(self.columns[idx])
                except ValueError:
                    pass

    def _show_tree_context_menu(self, event: Any) -> None:
        menu = tk.Menu(self.root, tearoff=0)
        col_id = self.tree.identify_column(event.x)
        if col_id:
            try:
                idx = int(col_id.replace("#", "")) - 1
                if 0 <= idx < len(self.columns):
                    target_col = self.columns[idx]
                    col_title = self.col_titles.get(target_col, target_col)
                    menu.add_command(
                        label=f"Auto-fit Column '{col_title}'",
                        command=lambda: self.autofit_single_column(target_col),
                    )
            except ValueError:
                pass

        menu.add_command(label="Auto-fit All Column Widths", command=self.autofit_columns)
        menu.add_command(label="Reset Column Widths", command=self.reset_column_widths)
        menu.add_separator()
        menu.add_command(label="Copy Selected Rows", command=self.copy_selected_rows)
        menu.add_command(label="Export Table to CSV…", command=self.export_table_csv)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ───── Column Width Adjustments ───────────────────────────────────────────
    def autofit_single_column(self, col: str) -> None:
        """Measures heading and cell text to auto-fit a specific column width."""
        try:
            font = tkfont.nametofont("TkDefaultFont")
        except Exception:
            font = tkfont.Font(family="TkDefaultFont")

        heading_text = self.tree.heading(col, "text")
        max_w = font.measure(heading_text) + 28
        min_w = self.default_col_widths.get(col, (100, 40, False))[1]

        for item in self.tree.get_children():
            val = str(self.tree.set(item, col))
            if val:
                w = font.measure(val) + 20
                if w > max_w:
                    max_w = w

        max_w = min(max_w, 650)
        self.tree.column(col, width=max(max_w, min_w))

    def autofit_columns(self) -> None:
        """Automatically adjusts every column's width to fit contents and headings."""
        for col in self.columns:
            self.autofit_single_column(col)

    def reset_column_widths(self) -> None:
        """Resets all column widths to their initial default values."""
        for col, (w, min_w, stretch) in self.default_col_widths.items():
            self.tree.column(col, width=w, minwidth=min_w, stretch=stretch)

    # ───── CSV / Inventory Loading ───────────────────────────────────────────
    def browse_inventory_csv(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select Network Interfaces CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if filename:
            self.csv_var.set(filename)
            self.load_inventory()

    def browse_extra_info_csv(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select Additional Interface Info CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if filename:
            self.extra_info_var.set(filename)
            self.load_inventory()

    def load_inventory(self) -> None:
        csv_path = self.csv_var.get().strip()
        extra_path = self.extra_info_var.get().strip() or None

        self.mapper.csv_file = csv_path
        if not os.path.exists(csv_path):
            self.stats_var.set(f"Inventory file not found: {os.path.basename(csv_path)}")
            self.log_message(f"⚠️ Inventory file not found: {csv_path}")
            return

        loaded = self.mapper.load_csv_data()
        self.mapper.load_addon_subnets()
        self.mapper.load_additional_int_info(extra_path)

        dev_count = len(self.mapper.device_interfaces)
        iface_count = sum(len(ifs) for ifs in self.mapper.device_interfaces.values())

        if loaded:
            self.stats_var.set(f"Inventory: {dev_count} devices, {iface_count} interfaces")
            self.log_message(f"✓ Inventory loaded: {dev_count} devices, {iface_count} interfaces from {csv_path}")
        else:
            self.stats_var.set("Failed to load inventory CSV")
            self.log_message(f"❌ Failed to parse inventory CSV: {csv_path}")

    def _apply_settings_to_mapper(self) -> None:
        try:
            self.mapper.max_hops = max(1, int(self.max_hops_var.get().strip()))
        except ValueError:
            self.mapper.max_hops = 30

        try:
            self.mapper.timeout_base = max(1, int(self.timeout_var.get().strip()))
        except ValueError:
            self.mapper.timeout_base = 2

        self.mapper.wan_keyword = self.wan_var.get().strip() or "wanr"
        self.mapper.resolve_dns = bool(self.dns_var.get())

        subnets_spec = self.transit_subnets_var.get().strip()
        if subnets_spec:
            self.mapper.set_transit_subnets(subnets_spec)
            self.transit_subnets_var.set(self.mapper.get_transit_subnets_display())

    # ───── Tracing Execution ──────────────────────────────────────────────────
    def start_trace(self) -> None:
        target = self.target_var.get().strip()
        if not target:
            messagebox.showwarning("Missing Target", "Please enter a Destination IP or Hostname.")
            return

        source = self.source_var.get().strip() or None
        self._apply_settings_to_mapper()

        self.is_tracing = True
        self.stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_wan.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        self.status_var.set(f"Starting traceroute to {target}…")

        self.clear_results(keep_inputs=True)
        self.log_message(f"=== Starting Traceroute to {target} ===")
        if source:
            self.log_message(f"Source specified: {source}")

        t = threading.Thread(
            target=self._worker_single_trace,
            args=(target, source),
            daemon=True,
        )
        t.start()

    def start_wan_trace(self) -> None:
        src = self.source_var.get().strip()
        dst = self.target_var.get().strip()
        if not src or not dst:
            messagebox.showwarning(
                "Source and Destination Required",
                "Both Source and Destination must be entered for WAN-aware trace.",
            )
            return

        self._apply_settings_to_mapper()

        self.is_tracing = True
        self.stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_wan.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        self.status_var.set(f"Starting WAN-aware trace: {src} ↔ {dst}…")

        self.clear_results(keep_inputs=True)
        self.log_message(f"=== Starting WAN-Aware Trace: {src} ↔ {dst} ===")

        t = threading.Thread(
            target=self._worker_wan_trace,
            args=(src, dst),
            daemon=True,
        )
        t.start()

    def stop_trace(self) -> None:
        if self.is_tracing:
            self.stop_event.set()
            if self.active_proc and self.active_proc.poll() is None:
                try:
                    self.active_proc.terminate()
                except Exception:
                    pass
            self.status_var.set("Stopping trace…")
            self.log_message("⏹ Trace stop requested by user.")

    def clear_results(self, keep_inputs: bool = False) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.flow_text.delete("1.0", "end")
        self.flow_text.insert("end", "(No traceroute run yet. Enter a target and click Start Trace)\n")

        if not keep_inputs:
            self.target_var.set("")
            self.source_var.set("")
            self.clear_log()
            self.status_var.set("Ready")
            self.progress.stop()
            self.progress.config(mode="determinate", value=0)

    # ───── Worker Threads ────────────────────────────────────────────────────
    def _worker_single_trace(self, target: str, source: Optional[str]) -> None:
        start_time = time.time()
        try:
            self.queue.put(("status", f"Resolving target {target}…"))
            target_ip = resolve_target(target)
            self.queue.put(("log", f"✓ Resolved target {target} → {target_ip}"))

            source_ip = None
            if source:
                self.queue.put(("status", f"Resolving source {source}…"))
                source_ip = resolve_target(source)
                self.queue.put(("log", f"✓ Resolved source {source} → {source_ip}"))

            # Addon subnet notification
            for _net, dev, info in self.mapper.check_addon_subnet(target_ip):
                self.queue.put(("log", f"ℹ️ ADDON INFO: Matches {str(_net)} (Behind {dev}) [{info}]"))

            # Connectivity ping
            self.queue.put(("status", f"Testing ping reachability to {target_ip}…"))
            if self.mapper._test_connectivity(target_ip):
                self.queue.put(("log", f"✓ Ping reachable to {target_ip}"))
            else:
                self.queue.put(("log", f"⚠️ Ping unreachable to {target_ip}, continuing anyway…"))

            # Streaming trace
            self.queue.put(("status", f"Tracing hops to {target_ip}…"))
            hops: List[Tuple[int, Optional[str]]] = []
            dest_reached = False

            def proc_cb(p: Any) -> None:
                self.active_proc = p

            for hop_no, ip in self.mapper.execute_traceroute_streaming(
                target_ip,
                source_ip=source_ip,
                stop_event=self.stop_event,
                proc_callback=proc_cb,
            ):
                if self.stop_event.is_set():
                    break
                hops.append((hop_no, ip))
                self.queue.put(("hop_streaming", hop_no, ip))
                if ip == target_ip:
                    dest_reached = True
                    break

            elapsed = time.time() - start_time
            if self.stop_event.is_set():
                self.queue.put(("log", f"⏹ Traceroute stopped by user after {elapsed:.1f}s."))
            else:
                self.queue.put(("log", f"✓ Traceroute complete in {elapsed:.1f}s ({len(hops)} hops)."))

            # Resolve full path interfaces & subnets
            self.queue.put(("status", "Resolving interfaces and subnets…"))
            resolved = self.mapper.resolve_path_interfaces(
                hops, target_ip=target_ip, source_ip=source_ip
            )
            self.queue.put(("trace_done", resolved, target_ip, dest_reached, elapsed))

        except Exception as exc:
            self.queue.put(("error", str(exc)))
        finally:
            self.active_proc = None

    def _worker_wan_trace(self, source: str, destination: str) -> None:
        start_time = time.time()
        try:
            self.queue.put(("status", f"Resolving source {source} & target {destination}…"))
            src_ip = resolve_target(source)
            dst_ip = resolve_target(destination)
            self.queue.put(("log", f"✓ Source {source} → {src_ip}"))
            self.queue.put(("log", f"✓ Destination {destination} → {dst_ip}"))

            if src_ip == dst_ip:
                self.queue.put(("error", "Source and Destination resolve to the same IP."))
                return

            def proc_cb(p: Any) -> None:
                self.active_proc = p

            self.queue.put(("status", f"Tracing path to source {src_ip}…"))
            src_hops: List[Tuple[int, Optional[str]]] = []
            for hop_no, ip in self.mapper.execute_traceroute_streaming(
                src_ip, stop_event=self.stop_event, proc_callback=proc_cb
            ):
                if self.stop_event.is_set():
                    break
                src_hops.append((hop_no, ip))
                self.queue.put(("log", f"Src Hop {hop_no}: {ip or '* * *'}"))

            self.queue.put(("status", f"Tracing path to destination {dst_ip}…"))
            dst_hops: List[Tuple[int, Optional[str]]] = []
            for hop_no, ip in self.mapper.execute_traceroute_streaming(
                dst_ip, stop_event=self.stop_event, proc_callback=proc_cb
            ):
                if self.stop_event.is_set():
                    break
                dst_hops.append((hop_no, ip))
                self.queue.put(("log", f"Dst Hop {hop_no}: {ip or '* * *'}"))

            # WAN router stitch
            resolved_src = self.mapper.resolve_path_interfaces(src_hops, target_ip=src_ip)
            resolved_dst = self.mapper.resolve_path_interfaces(dst_hops, target_ip=dst_ip)

            wan_kw = self.mapper.wan_keyword.lower()
            src_wan_idx = None
            for idx, r in enumerate(resolved_src):
                dev = (r.get("device") or "").lower()
                if wan_kw in dev:
                    src_wan_idx = idx
                    break

            dst_wan_idx = None
            for idx, r in enumerate(resolved_dst):
                dev = (r.get("device") or "").lower()
                if wan_kw in dev:
                    dst_wan_idx = idx
                    break

            stitched_hops = []
            if src_wan_idx is not None and dst_wan_idx is not None:
                self.queue.put(("log", f"✓ Found WAN routers on both traces. Stitching paths…"))
                # Reverse source side up to wan router
                src_segment = list(reversed(resolved_src[: src_wan_idx + 1]))
                dst_segment = resolved_dst[dst_wan_idx:]
                for s in src_segment:
                    stitched_hops.append((len(stitched_hops) + 1, s.get("ip")))
                for d in dst_segment:
                    stitched_hops.append((len(stitched_hops) + 1, d.get("ip")))
            else:
                self.queue.put(("log", "ℹ️ WAN router keyword not found on both paths; showing destination trace."))
                stitched_hops = dst_hops

            resolved = self.mapper.resolve_path_interfaces(
                stitched_hops, target_ip=dst_ip, source_ip=src_ip
            )
            elapsed = time.time() - start_time
            self.queue.put(("wan_done", resolved, dst_ip, elapsed))

        except Exception as exc:
            self.queue.put(("error", str(exc)))
        finally:
            self.active_proc = None

    # ───── Queue Processing & UI Updates ─────────────────────────────────────
    def _process_queue(self) -> None:
        try:
            while True:
                msg = self.queue.get_nowait()
                msg_type = msg[0]

                if msg_type == "status":
                    self.status_var.set(msg[1])

                elif msg_type == "log":
                    self.log_message(msg[1])

                elif msg_type == "hop_streaming":
                    hop_no, ip = msg[1], msg[2]
                    ip_disp = ip if ip else "* * * (timeout)"
                    self.status_var.set(f"Hop {hop_no}: {ip_disp}")
                    self.log_message(f"Hop {hop_no:>2}: {ip_disp}")

                elif msg_type == "trace_done":
                    resolved, target_ip, dest_reached, elapsed = msg[1], msg[2], msg[3], msg[4]
                    self.last_resolved_hops = resolved
                    self._render_resolved_table(resolved, target_ip)
                    self._render_path_flow(resolved)
                    dest_str = "Yes" if dest_reached else "No"
                    self.status_var.set(
                        f"Finished in {elapsed:.1f}s | Hops: {len(resolved)} | Destination reached: {dest_str}"
                    )
                    self.log_message(f"=== Path resolution complete. Destination reached: {dest_str} ===")
                    self._finish_tracing()

                elif msg_type == "wan_done":
                    resolved, target_ip, elapsed = msg[1], msg[2], msg[3]
                    self.last_resolved_hops = resolved
                    self._render_resolved_table(resolved, target_ip)
                    self._render_path_flow(resolved)
                    self.status_var.set(f"WAN path finished in {elapsed:.1f}s | Hops: {len(resolved)}")
                    self.log_message("=== WAN Source ↔ Destination path complete ===")
                    self._finish_tracing()

                elif msg_type == "error":
                    err_msg = msg[1]
                    self.log_message(f"❌ Error: {err_msg}")
                    self.status_var.set(f"Error: {err_msg}")
                    messagebox.showerror("Traceroute Error", err_msg)
                    self._finish_tracing()

        except queue.Empty:
            pass

        self.root.after(50, self._process_queue)

    def _finish_tracing(self) -> None:
        self.is_tracing = False
        self.progress.stop()
        self.progress.config(mode="determinate", value=100)
        self.btn_start.config(state="normal")
        self.btn_wan.config(state="normal")
        self.btn_stop.config(state="disabled")

    def _render_resolved_table(self, resolved_hops: List[dict], target_ip: str) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        for rec in resolved_hops:
            hop_no = rec.get("hop_no", "")
            ip = rec.get("ip", "")
            is_timeout = rec.get("is_timeout", False)

            if is_timeout or not ip:
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        hop_no,
                        "* * * (timeout)",
                        "-",
                        "-",
                        "-",
                        "-",
                        "-",
                        "-",
                        "Request timed out",
                        "-",
                    ),
                    tags=("timeout_row",),
                )
                continue

            ptr = get_reverse_dns(ip) if self.mapper.resolve_dns else None
            show_ip = f"{ip} ({ptr})" if ptr else ip
            dev = rec.get("device") or "External/Unknown"
            in_if = rec.get("in_iface") or "-"
            out_if = rec.get("out_iface") or "-"
            next_hop = rec.get("next_hop") or "-"
            in_zone = rec.get("in_zone") or "-"
            out_zone = rec.get("out_zone") or "-"
            in_vrf = rec.get("in_vrf") or "-"
            out_vrf = rec.get("out_vrf") or "-"
            in_desc = rec.get("in_desc") or ""
            out_desc = rec.get("out_desc") or ""

            dev_for_info = dev if dev != "External/Unknown" else None
            in_info = self.mapper.get_extra_info(rec.get("in_ip"), dev_for_info, in_if)
            out_info = self.mapper.get_extra_info(rec.get("out_ip"), dev_for_info, out_if)

            # Line 1: INBOUND
            self.tree.insert(
                "",
                "end",
                values=(
                    hop_no,
                    show_ip,
                    dev,
                    "IN",
                    in_if,
                    "-",
                    in_zone,
                    in_vrf,
                    in_desc,
                    in_info,
                ),
                tags=("in_row",),
            )

            # Line 2: OUTBOUND
            is_dest = (
                "Destination Reached" in next_hop
                or ip == target_ip
                or out_if in {"Connected / Target", "Connected/Target"}
            )
            out_tags = ("target_row", "out_row") if is_dest else ("out_row",)
            self.tree.insert(
                "",
                "end",
                values=(
                    "",
                    "",
                    "",
                    "OUT",
                    out_if,
                    next_hop,
                    out_zone,
                    out_vrf,
                    out_desc,
                    out_info,
                ),
                tags=out_tags,
            )

        # Auto-fit columns to newly loaded data
        self.autofit_columns()

    def _render_path_flow(self, resolved_hops: List[dict]) -> None:
        self.flow_text.delete("1.0", "end")
        flow_lines = self.mapper.format_path_flow(resolved_hops)
        self.flow_text.insert("end", "PATH FLOW:\n")
        for line in flow_lines:
            self.flow_text.insert("end", line + "\n")

    # ───── Clipboard & Export Helpers ─────────────────────────────────────────
    def copy_selected_rows(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Selection Required", "Please select one or more rows to copy.")
            return

        rows = []
        for item in selected:
            vals = [str(self.tree.set(item, col)) for col in self.columns]
            rows.append("\t".join(vals))

        text_to_copy = "\n".join(rows)
        self.root.clipboard_clear()
        self.root.clipboard_append(text_to_copy)
        self.status_var.set(f"Copied {len(selected)} row(s) to clipboard.")

    def export_table_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Traceroute Table to CSV",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                headers = [self.col_titles[c] for c in self.columns]
                writer.writerow(headers)
                for item in self.tree.get_children():
                    writer.writerow([self.tree.set(item, col) for col in self.columns])
            messagebox.showinfo("Export Successful", f"Table exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Failed", f"Could not write CSV file:\n{exc}")

    def copy_path_flow(self) -> None:
        text = self.flow_text.get("1.0", "end-1c")
        if text.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.status_var.set("PATH FLOW copied to clipboard.")
            messagebox.showinfo("Copied", "PATH FLOW diagram copied to clipboard!")

    def save_path_flow(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Save PATH FLOW as Text",
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.flow_text.get("1.0", "end-1c"))
            messagebox.showinfo("Saved", f"PATH FLOW saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Save Failed", f"Could not save file:\n{exc}")

    def copy_log(self) -> None:
        log_content = self.log_text.get("1.0", "end-1c")
        if log_content.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(log_content)
            messagebox.showinfo("Copied", "Log content copied to clipboard!")

    def clear_log(self) -> None:
        self.log_text.delete("1.0", "end")

    def log_message(self, msg: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {msg}\n")
        self.log_text.see("end")


def launch_gui(
    csv_file: str = "network_interfaces.csv",
    extra_info: Optional[str] = None,
    wan_keyword: str = "wanr",
    resolve_dns: bool = False,
    transit_subnets: Optional[str] = None,
    mapper: Optional[CiscoTracerouteMapper] = None,
) -> None:
    """Launches the Tkinter Graphical User Interface."""
    if not TKINTER_AVAILABLE:
        print("Error: Tkinter is not installed or not available in this Python environment.")
        return

    root = tk.Tk()
    app = TraceINTGUI(root, mapper=mapper)
    if mapper is None:
        app.csv_var.set(csv_file)
        if extra_info:
            app.extra_info_var.set(extra_info)
        app.wan_var.set(wan_keyword)
        app.dns_var.set(resolve_dns)
        if transit_subnets:
            app.transit_subnets_var.set(transit_subnets)
            app.mapper.set_transit_subnets(transit_subnets)
        app.load_inventory()
    elif transit_subnets:
        app.transit_subnets_var.set(transit_subnets)
        app.mapper.set_transit_subnets(transit_subnets)
    root.mainloop()


# ──────────────────────────────────────────────────────────────────────────────
# main()
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cisco Network Traceroute Mapper – runs on Python 3.8"
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="Destination IP(s) or hostname(s). If omitted the interactive menu starts.",
    )
    parser.add_argument(
        "-g",
        "--gui",
        action="store_true",
        help="Launch Graphical User Interface (Tkinter)",
    )
    parser.add_argument(
        "-p",
        "--transit-subnets",
        default="30,31,29,28",
        help="Allowed prefix lengths for inter-device transit/link matching (default: %(default)s, e.g. '30,31,29,28' or '28-31')",
    )
    parser.add_argument(
        "-f",
        "--csv",
        default="network_interfaces.csv",
        help="Inventory CSV file (default: %(default)s)",
    )
    parser.add_argument(
        "-c",
        "--compare",
        action="store_true",
        help="Compare traceroutes to multiple targets (requires >1 targets)",
    )
    parser.add_argument(
        "--resolve-dns",
        action="store_true",
        help="Enable DNS resolution for hops (default: False)",
    )
    parser.add_argument(
        "-s",
        "--source",
        help="Source IP/hostname for Source ↔ Destination WAN-aware path (use with -d)",
    )
    parser.add_argument(
        "-d",
        "--destination",
        help="Destination IP/hostname for Source ↔ Destination WAN-aware path (use with -s)",
    )
    parser.add_argument(
        "--wan-keyword",
        default="wanr",
        help="Device-name keyword identifying WAN routers (default: %(default)s)",
    )
    parser.add_argument(
        "--extra-info",
        default=None,
        help="Additional interface info CSV (inventory columns + 'info'). "
             "Default: additional_int_info.csv / additiaon_int_info.csv if present",
    )
    args = parser.parse_args()

    if bool(args.source) != bool(args.destination):
        parser.error("--source and --destination must be used together")

    # Check GUI flag first
    if args.gui:
        launch_gui(
            csv_file=args.csv,
            extra_info=args.extra_info,
            wan_keyword=args.wan_keyword,
            resolve_dns=args.resolve_dns,
            transit_subnets=args.transit_subnets,
        )
        return

    # 1. Instantiate & Load Data
    mapper = CiscoTracerouteMapper(csv_file=args.csv)
    if not mapper.load_csv_data():
        sys.exit(1)
    mapper.load_addon_subnets()
    mapper.load_additional_int_info(args.extra_info)

    # 2. Check Arguments
    mapper.resolve_dns = args.resolve_dns  # Apply argument
    mapper.wan_keyword = args.wan_keyword
    mapper.set_transit_subnets(args.transit_subnets)

    if args.source and args.destination:
        mapper.trace_source_destination(args.source, args.destination)
    elif args.targets:  # non-interactive
        if args.compare and len(args.targets) > 1:
            mapper.compare_traces(args.targets)
        elif len(args.targets) > 1:
            destinations = args.targets
            monitored_devices = set()
            manual_ips = set(args.targets)
            manual_subnets = []
            print(f"Running batch verification for {len(destinations)} targets...")
            mapper.run_verification_batch(destinations, monitored_devices, manual_ips, manual_subnets)
        else:
            if args.compare:
                 print("Info: --compare requires multiple targets. Running standard trace.")
            for tgt in args.targets:
                print("\n" + "=" * 100)
                mapper.trace_to_destination(tgt)
    else:
        mapper.interactive_menu()


if __name__ == "__main__":
    main()

