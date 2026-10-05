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
from typing import Dict, List, Optional, Tuple, Set

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
# Core class
# ──────────────────────────────────────────────────────────────────────────────
class CiscoTracerouteMapper:
    # ───── initialisation ────────────────────────────────────────────────────
    def __init__(self, csv_file: str = "network_interfaces.csv") -> None:
        self.csv_file: str = csv_file
        # (iface, ip, zone, vrf, description)
        self.device_inventory: Dict[str, List[Tuple[str, str, str, str, str]]] = {}
        self.ip_to_device_map: Dict[str, Tuple[str, str, str, str, str]] = {}
        self.device_zones: Dict[str, str] = {}
        # traceroute settings
        self.resolve_dns: bool = False  # Default to False for speed
        self.max_hops: int = 20         # Default limited to 20 for speed
        self.timeout_base: int = 3
        self.max_retries: int = 2
        # Device-name keyword identifying WAN routers (case-insensitive)
        self.wan_keyword: str = "wanr"
        # Addon subnets: list of (network_obj, behind_device_str, info_str)
        self.addon_subnets: List[Tuple[ipaddress.IPv4Network, str, str]] = []
        # Additional interface info (same columns as inventory + 'info')
        self.extra_info_by_ip: Dict[str, List[str]] = {}
        self.extra_info_by_iface: Dict[Tuple[str, str], List[str]] = {}

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

                    if ip_sub.upper() in {"DHCP", "PPPOE", "SOURCE: LOOPBACK1"} or not ip_sub:
                        continue                     # skip dynamic or empty

                    ip = ip_sub.split("/")[0]
                    try:
                        ipaddress.ip_address(ip)
                    except ValueError:
                        print(f"Warning: invalid IP '{ip}' for {device}")
                        continue

                    self.device_inventory.setdefault(device, []).append(
                        (iface, ip, zone, vrf, description)
                    )
                    self.ip_to_device_map[ip] = (device, iface, zone, vrf, description)
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
        self, target_ip: str, source_ip: Optional[str] = None
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
        except FileNotFoundError:
            print("Traceroute executable not found on this system.")
            return
        except Exception as exc:
            print(f"Unable to launch traceroute: {exc}")
            return

        while True:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break  # process finished
                continue  # still running

            parsed = self._parse_traceroute_line(line.rstrip(), system)
            if parsed:
                hop_no, ip, _ = parsed
                yield hop_no, ip

        proc.wait(timeout=10)

    # ───── display helpers ────────────────────────────────────────────────────
    def _display_hop(self, hop_no: int, ip: Optional[str]) -> None:
        """Prints one hop line with PTR + inventory info."""
        if ip is None:
            print(f"{hop_no:>2}   * * *  (timeout)")
            return

        ptr = None
        if self.resolve_dns:
            ptr = get_reverse_dns(ip)

        device, iface, zone, vrf, description = self.ip_to_device_map.get(ip, (None, None, None, None, None))
        show_ip = f"{ip} ({ptr})" if ptr else ip

        if device:
            # Check for addon subnet match to append as extra info
            addons = self.check_addon_subnet(ip)
            extra = ""
            if addons:
                 # Join multiple matches if any
                 # Format: [Sub: Dev1, Dev2]
                 devs = sorted(list(set(d for _, d, _ in addons)))
                 dev_str = ", ".join(devs)
                 extra = f" [Sub: {dev_str}]"
                 
            info = self.get_extra_info(ip, device, iface)
            if info:
                extra += f" [Info: {info}]"
            print(
                f"{hop_no:>2}   {show_ip:<40}  {device:<20} {iface:<20} {zone:<15} {vrf:<15} {description}{extra}"
            )
        else:
            # Check for addon subnet match if no device found
            addons = self.check_addon_subnet(ip)
            if addons:
                for _net, dev_name, info in addons:
                    # Format: Matches 10.x.x.x/24 (Behind dev) [Info]
                    match_str = f"Matches {str(_net)} (Behind {dev_name}) [{info}]"
                    print(f"{hop_no:>2}   {show_ip:<40}  {match_str}")
            else:
                print(f"{hop_no:>2}   {show_ip:<40}  External/Unknown")

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

        print("-" * 80)
        print("-" * 80)
        print(f"{'No':>2}   {'IP Address':<40}  {'Device Name':<20} {'Interface':<20} {'Zone':<15} {'VRF':<15} {'Description'}")
        print("-" * 80)


        hops: List[Tuple[int, Optional[str]]] = []
        destination_reached = False

        try:
            for hop_no, ip in self.execute_traceroute_streaming(target_ip):
                hops.append((hop_no, ip))
                self._display_hop(hop_no, ip)
                if ip == target_ip:
                    destination_reached = True
                    break
                time.sleep(0.3)  # small pacing for readability
        except KeyboardInterrupt:
            print("\nInterrupted by user.")

        # summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Hops recorded: {len(hops)}")
        print(f"Destination reached: {'Yes' if destination_reached else 'No'}")

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

                    if device:
                        cell_text = f"{hop_ip} [{device} - {iface}]"
                        info = self.get_extra_info(hop_ip, device, iface)
                        if info:
                            cell_text = f"{hop_ip} ℹ [{device} - {iface}]"
                            info_legend.setdefault(hop_ip, (device, iface, info))
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

                # Truncate to col_width - 1
                row_str += f"{cell_text[:col_width-1]:<{col_width}} "

            if is_common:
                 row_str += " (MATCH)"

            print(row_str)

        if info_legend:
            print("\nℹ  Additional interface info:")
            for hop_ip, (device, iface, info) in info_legend.items():
                print(f"   {hop_ip:<16} {device} - {iface}: {info}")

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
            
            # A. Verification Status
            matches = match_details.get(orig_target, [])
            if matches:
                print(f"  ✓ VERIFIED: Found {len(matches)} monitored hop(s):")
                for h, ip_str, dev, mtype in matches:
                    info = self.get_extra_info(ip_str)
                    info_s = f"  [Info: {info}]" if info else ""
                    print(f"    - Hop {h:<2}: {dev:<20} ({ip_str}){info_s}")
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
                    info = self.get_extra_info(ip_str)
                    info_s = f"  [Info: {info}]" if info else ""
                    print(f"    - Hop {h:<2}: {dev:<20} ({ip_str}){is_ver}{info_s}")

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
        """Prints stitched path rows: (segment, ip_or_None, note)."""
        print("-" * 120)
        print(f"{'#':>3}  {'Segment':<10} {'IP Address':<16} {'Device Name':<25} "
              f"{'Interface':<22} {'Zone':<15} Note")
        print("-" * 120)
        n = 0
        for seg, ip, note in path:
            if seg == "WAN":
                print(f"{'':>3}  {'':<10} {'≈' * 18}  {note}  {'≈' * 18}")
                continue
            n += 1
            if ip is None:
                print(f"{n:>3}  {seg:<10} {'*':<16} {'(timeout)':<25}")
                continue
            dev, iface, zone = self._hop_info(ip)
            if self._is_wan_router(self._hop_device(ip)):
                note = (note + " " if note else "") + "🌐 WAN router"
            info = self.get_extra_info(ip)
            if info:
                note = (note + " " if note else "") + f"[Info: {info}]"
            print(f"{n:>3}  {seg:<10} {ip:<16} {dev[:25]:<25} {iface[:22]:<22} "
                  f"{zone[:15]:<15} {note}")
        print("-" * 120)

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
        except ValueError:
            print("Invalid entry – settings unchanged.")
        print("Settings now:")
        print(f"  max_hops = {self.max_hops}")
        print(f"  timeout  = {self.timeout_base}s")
        print(f"  retries  = {self.max_retries}")
        print(f"  wan kw   = {self.wan_keyword}")

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
            print("8. Exit")
            print("-" * 80)
            choice = input("Select option (1-8): ").strip()

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
                print("Good-bye!")
                break
            else:
                print("Invalid selection.")
            input("\nPress Enter to continue…")


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

    # 1. Instantiate & Load Data
    mapper = CiscoTracerouteMapper(csv_file=args.csv)
    if not mapper.load_csv_data():
        sys.exit(1)
    mapper.load_addon_subnets()
    mapper.load_additional_int_info(args.extra_info)

    # 2. Check Arguments
    mapper.resolve_dns = args.resolve_dns  # Apply argument
    mapper.wan_keyword = args.wan_keyword

    if args.source and args.destination:
        mapper.trace_source_destination(args.source, args.destination)
    elif args.targets:  # non-interactive

        if args.compare and len(args.targets) > 1:
            mapper.compare_traces(args.targets)
        elif len(args.targets) > 1:
            # Default behavior for multiple targets: Verification Mode
            # Use targets as both Destinations and Manual IPs
            destinations = args.targets
            monitored_devices = set()
            manual_ips = set(args.targets)
            manual_subnets = []
            
            print(f"Running batch verification for {len(destinations)} targets...")
            mapper.run_verification_batch(destinations, monitored_devices, manual_ips, manual_subnets)
        else:
            # Single target
            if args.compare:
                 print("Info: --compare requires multiple targets. Running standard trace.")

            for tgt in args.targets:
                print("\n" + "=" * 100)
                mapper.trace_to_destination(tgt)
    else:
        mapper.interactive_menu()


if __name__ == "__main__":
    main()
