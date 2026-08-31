#!/usr/bin/env python3
"""
IP VLAN Converter & Device Mapping Tool
======================================
Processes network subnet/VLAN CSV data, extracts device names/functions,
identifies VLAN types based on configurable priority device sequence matching against mapping.csv,
provides a Mapping Manager interface for cross-checking and batch editing missing mappings,
loads/generates pre-defined VLAN types from vlan_type.csv,
supports filtering out P2P and Loopback subnets (/30, /31, /32),
supports custom search sequence configuration,
and supports column selection for output.

Modes:
- GUI Mode: Built with Tkinter (Modern ttk styled interface)
- CLI Mode: Interactive command-line interface (auto-fallback if no GUI display)
"""

import os
import sys
import csv
import re
import argparse
from typing import List, Dict, Tuple, Set, Optional, Any

# ==============================================================================
# Helper / Core Business Logic
# ==============================================================================

# Default priority order for identifying VLAN Type
DEFAULT_PRIORITY_COLUMNS = ["user", "root_bridge", "standby", "non_active"]

# Standard expected device columns
KNOWN_DEVICE_COLUMNS = [
    "user", "root_bridge", "standby", "non_active", "active", "edge", "bridge"
]

EXCLUDED_COLUMN_KEYWORDS = [
    "interface", "intf", "port", "subnet", "network", "mask", "cidr", "ip",
    "vdc", "vrf", "vlan", "description", "remark", "status"
]

# Standard default pre-defined VLAN types to write if vlan_type.csv does not exist
DEFAULT_VLAN_TYPES = [
    "server vlan",
    "user vlan",
    "management vlan",
    "voice vlan",
    "dmz vlan",
    "transit vlan",
    "storage vlan",
    "wireless vlan",
    "native vlan",
    "backup vlan"
]


def load_or_create_vlan_types(filepath: str = "vlan_type.csv") -> List[str]:
    """
    Loads pre-defined VLAN types from vlan_type.csv.
    If the file does not exist, automatically creates it with standard default VLAN types.
    """
    if not filepath:
        filepath = "vlan_type.csv"

    if not os.path.exists(filepath):
        try:
            with open(filepath, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["vlan_type"])
                for vt in DEFAULT_VLAN_TYPES:
                    writer.writerow([vt])
            print(f"[Info] '{filepath}' not found. Auto-generated with {len(DEFAULT_VLAN_TYPES)} default VLAN types.")
            return list(DEFAULT_VLAN_TYPES)
        except Exception as e:
            print(f"[Warning] Could not create '{filepath}': {e}")
            return list(DEFAULT_VLAN_TYPES)

    # File exists, load and clean entries
    vlan_types = []
    try:
        with open(filepath, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                val = row[0].strip()
                if not val or val.lower() in ["vlan_type", "type", "vlan type", "name"]:
                    continue
                if val not in vlan_types:
                    vlan_types.append(val)
    except Exception as e:
        print(f"[Warning] Error reading '{filepath}': {e}")

    if not vlan_types:
        return list(DEFAULT_VLAN_TYPES)

    return vlan_types


def is_p2p_or_loopback_subnet(val: str) -> bool:
    """
    Checks if a subnet string indicates a Point-to-Point (/30, /31) or Loopback/Host (/32) subnet.
    Supports CIDR notation (/30, /31, /32) and dotted decimal netmasks (255.255.255.252, 255.255.255.254, 255.255.255.255).
    """
    if not val or not isinstance(val, str):
        return False
    val = val.strip()
    
    # Check CIDR prefix e.g. /30, /31, /32
    if re.search(r'/(30|31|32)\b', val):
        return True
    
    # Check dotted decimal netmask strings
    if any(mask in val for mask in ["255.255.255.252", "255.255.255.254", "255.255.255.255"]):
        return True
        
    return False


def is_p2p_or_loopback_row(row: Dict[str, str], headers: List[str]) -> bool:
    """
    Checks if any subnet/network/mask column in a row contains a /30, /31, or /32 subnet.
    """
    for col in headers:
        col_norm = col.strip().lower().replace(" ", "_")
        if any(keyword in col_norm for keyword in ["subnet", "network", "mask", "cidr", "ip_address", "ip"]):
            cell_val = row.get(col, "")
            if is_p2p_or_loopback_subnet(cell_val):
                return True
    return False


def is_device_column(col_name: str) -> bool:
    """
    Determines if a CSV column represents network devices.
    """
    col_norm = col_name.strip().lower().replace(" ", "_")
    # Disqualify interface or network/ip columns
    if any(ex in col_norm for ex in EXCLUDED_COLUMN_KEYWORDS):
        return False
    # Check against known device columns or containing device
    if any(col_norm == d or col_norm.endswith(f"_{d}") or col_norm.startswith(f"{d}_") for d in KNOWN_DEVICE_COLUMNS):
        return True
    if "device" in col_norm or "switch" in col_norm or "router" in col_norm:
        return True
    return False


def is_valid_device_token(token: str) -> bool:
    """
    Validates if a string token is a plausible device name,
    filtering out IP addresses, interfaces, subnet masks, and empty strings.
    """
    if not token or len(token) < 2:
        return False
    
    token_lower = token.lower()
    if token_lower in ["none", "n/a", "null", "-", "na", "nil", "unknown"]:
        return False

    # Filter out IP addresses or CIDR (e.g. 10.1.1.0, 192.168.1.1/24)
    if re.match(r'^\d+\.\d+\.\d+\.\d+(/\d+)?$', token):
        return False

    # Filter out interface names (e.g. Eth1/1, Gi0/0/1, Te1/1/1, Po10)
    if re.match(r'^(eth|gi|te|twe|fo|fa|hu|mgmt|po|vlan|port-channel|loopback|serial|tu)\d', token_lower):
        return False

    return True


def clean_device_token(token: str) -> str:
    """
    Cleans a single device name token.
    - Strips whitespace
    - Removes notations like (1), (2), [1], #1, (primary), etc.
    """
    token = token.strip()
    if not token:
        return ""
    # Remove parenthetical notations: (1), (2), [1], etc.
    token = re.sub(r'[\(\[\{].*?[\)\]\}]', '', token)
    # Remove trailing/leading notations
    token = re.sub(r'#\d+', '', token)
    token = token.strip().strip(',').strip(';').strip()
    return token


def parse_device_names(cell_value: str) -> List[str]:
    """
    Splits cell content by comma, semicolon, newline, or pipe,
    and returns a list of cleaned, valid device names.
    """
    if not cell_value or not isinstance(cell_value, str):
        return []
    
    raw_tokens = re.split(r'[,;\n\r|]+', cell_value)
    devices = []
    for raw in raw_tokens:
        cleaned = clean_device_token(raw)
        if cleaned and is_valid_device_token(cleaned):
            devices.append(cleaned)
    return devices


def parse_device_parts(device_name: str) -> Tuple[str, str, str]:
    """
    Parses a device name into (location, function, numbering).
    Example:
      'asdasd-svrx001' -> ('asdasd', 'svrx', '001')
      'sdasds-usrs'    -> ('sdasds', 'usrs', '')
      'core1-sw01'     -> ('core1', 'sw', '01')
      'device1'        -> ('', 'device', '1')
    """
    device_name = clean_device_token(device_name)
    if not device_name:
        return ("", "", "")

    if "-" in device_name:
        parts = device_name.split("-", 1)
        location = parts[0].strip()
        second_part = parts[1].strip()
    else:
        location = ""
        second_part = device_name

    # Split second_part into function letters/prefix and trailing numbering
    match = re.match(r'^([a-zA-Z_\-]+?)(\d*)$', second_part)
    if match:
        function = match.group(1).strip()
        numbering = match.group(2).strip()
    else:
        # Fallback split
        match_digits = re.search(r'(\d+)$', second_part)
        if match_digits:
            numbering = match_digits.group(1)
            function = second_part[:match_digits.start()].strip()
        else:
            function = second_part
            numbering = ""

    return (location, function.lower(), numbering)


def load_mapping_file(filepath: str) -> Dict[str, str]:
    """
    Loads mapping.csv. Supports two-column CSV:
    <key>,<vlan_type>
    Key can be full device name (e.g. 'asdasd-svrx001') or function code (e.g. 'svrx').
    Returns a dictionary of normalized keys (lowercase, trimmed) -> vlan_type.
    """
    mapping = {}
    if not filepath or not os.path.exists(filepath):
        return mapping

    try:
        with open(filepath, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 2:
                    continue
                key = clean_device_token(row[0]).lower()
                vlan_type = row[1].strip()
                # Skip header
                if key in ["device", "device_name", "function", "key", "name", "device_or_function"] and vlan_type.lower() in ["vlan_type", "type", "vlan type"]:
                    continue
                if key:
                    mapping[key] = vlan_type
    except Exception as e:
        print(f"[Warning] Error reading mapping file {filepath}: {e}")
    return mapping


def save_mapping_file(filepath: str, mapping: Dict[str, str]) -> bool:
    """
    Saves mapping dictionary to mapping.csv.
    """
    try:
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["device_or_function", "vlan_type"])
            for key in sorted(mapping.keys()):
                writer.writerow([key, mapping[key]])
        return True
    except Exception as e:
        print(f"[Error] Failed to save mapping file {filepath}: {e}")
        return False


def find_column_key(headers: List[str], target_name: str) -> Optional[str]:
    """
    Case-insensitive exact matching for column header names.
    """
    target_norm = target_name.strip().lower().replace(" ", "_")
    for h in headers:
        if h.strip().lower().replace(" ", "_") == target_norm:
            return h
    return None


def match_vlan_type(row: Dict[str, str], headers: List[str], mapping: Dict[str, str],
                    priority_columns: Optional[List[str]] = None) -> Tuple[str, str, str]:
    """
    Identifies VLAN type for a row by matching according to the given priority sequence.
    Defaults to ["user", "root_bridge", "standby", "non_active"] if not specified.

    Returns (vlan_type, matched_device, matched_column).
    If no match found, returns ("Unmapped", "", "").
    """
    columns_to_check = priority_columns if priority_columns else DEFAULT_PRIORITY_COLUMNS

    for col_name in columns_to_check:
        actual_col = find_column_key(headers, col_name)
        if not actual_col:
            continue
        
        cell_val = row.get(actual_col, "")
        devices = parse_device_names(cell_val)
        
        for dev in devices:
            dev_lower = dev.lower()
            loc, func, num = parse_device_parts(dev)
            
            # Check 1: Exact full device match in mapping
            if dev_lower in mapping and mapping[dev_lower]:
                return (mapping[dev_lower], dev, col_name)
            
            # Check 2: Function match in mapping (e.g. 'svrx')
            if func and func in mapping and mapping[func]:
                return (mapping[func], dev, col_name)

    return ("Unmapped", "", "")


def scan_devices_and_functions(csv_filepath: str) -> Tuple[List[str], List[Dict[str, str]], Set[str], Set[str], Dict[str, List[str]]]:
    """
    Reads the input CSV and extracts:
    - headers
    - rows
    - unique_devices (set of cleaned device names)
    - unique_functions (set of function codes)
    - function_to_devices (map of function -> list of sample device names)
    """
    if not os.path.exists(csv_filepath):
        raise FileNotFoundError(f"Input file not found: {csv_filepath}")

    with open(csv_filepath, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)

    unique_devices = set()
    unique_functions = set()
    function_to_devices = {}

    for row in rows:
        for col in headers:
            if is_device_column(col):
                cell_val = row.get(col, "")
                devs = parse_device_names(cell_val)
                for d in devs:
                    unique_devices.add(d)
                    loc, func, num = parse_device_parts(d)
                    if func:
                        unique_functions.add(func)
                        if func not in function_to_devices:
                            function_to_devices[func] = []
                        if d not in function_to_devices[func]:
                            function_to_devices[func].append(d)

    return (headers, rows, unique_devices, unique_functions, function_to_devices)


def cross_check_missing_mappings(
    unique_functions: Set[str],
    unique_devices: Set[str],
    mapping: Dict[str, str]
) -> List[str]:
    """
    Identifies functions present in the data that are not mapped in mapping.csv.
    """
    missing_functions = []
    for func in sorted(unique_functions):
        if func not in mapping or not mapping[func].strip():
            has_device_map = any(d.lower() in mapping and mapping[d.lower()].strip() for d in unique_devices if parse_device_parts(d)[1] == func)
            if not has_device_map:
                missing_functions.append(func)
    return missing_functions


# ==============================================================================
# GUI Mode (Tkinter)
# ==============================================================================

HAS_TKINTER = False
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    if "DISPLAY" in os.environ or sys.platform in ["win32", "darwin"]:
        HAS_TKINTER = True
except Exception:
    HAS_TKINTER = False


if HAS_TKINTER:
    class SequenceConfigDialog(tk.Toplevel):
        """
        Dialog window for configuring and reordering the device search / priority sequence.
        """
        def __init__(self, parent, current_sequence: List[str], available_headers: List[str], on_apply_callback=None):
            super().__init__(parent)
            self.title("Adjust Matching Priority Sequence")
            self.geometry("540x480")
            self.minsize(460, 380)
            self.transient(parent)
            self.grab_set()

            self.current_sequence = list(current_sequence)
            self.available_headers = list(available_headers)
            self.on_apply_callback = on_apply_callback

            self._create_widgets()
            self._populate_listbox()

        def _create_widgets(self):
            header_frame = ttk.Frame(self, padding=(12, 10))
            header_frame.pack(fill=tk.X)

            ttk.Label(header_frame, text="Configure VLAN Type Search Sequence", font=("Helvetica", 11, "bold")).pack(anchor=tk.W)
            ttk.Label(header_frame, text="The script checks device columns in the order listed below to identify VLAN type.", foreground="#555").pack(anchor=tk.W, pady=(2, 0))

            main_frame = ttk.Frame(self, padding=(12, 5))
            main_frame.pack(fill=tk.BOTH, expand=True)

            # Left side: Ordered Listbox
            list_frame = ttk.Frame(main_frame)
            list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            ttk.Label(list_frame, text="Active Sequence Order (Top = Highest Priority):").pack(anchor=tk.W, pady=(0, 2))
            
            box_frame = ttk.Frame(list_frame)
            box_frame.pack(fill=tk.BOTH, expand=True)

            self.listbox = tk.Listbox(box_frame, selectmode=tk.SINGLE, font=("Helvetica", 10), height=10)
            scroll = ttk.Scrollbar(box_frame, orient=tk.VERTICAL, command=self.listbox.yview)
            self.listbox.configure(yscrollcommand=scroll.set)

            self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)

            # Right side: Order Control Buttons
            btn_frame = ttk.Frame(main_frame, padding=(10, 0))
            btn_frame.pack(side=tk.RIGHT, fill=tk.Y)

            ttk.Button(btn_frame, text="▲ Move Up", command=self._move_up, width=14).pack(pady=4)
            ttk.Button(btn_frame, text="▼ Move Down", command=self._move_down, width=14).pack(pady=4)
            ttk.Button(btn_frame, text="➖ Remove", command=self._remove_column, width=14).pack(pady=4)
            ttk.Button(btn_frame, text="↺ Reset Default", command=self._reset_default, width=14).pack(pady=10)

            # Add Column Bar
            add_bar = ttk.LabelFrame(self, text="Add Column to Sequence", padding=(10, 8))
            add_bar.pack(fill=tk.X, padx=12, pady=5)

            ttk.Label(add_bar, text="Available Columns:").pack(side=tk.LEFT, padx=(0, 5))
            
            # Filter candidates from headers
            self.add_cb_var = tk.StringVar()
            self.add_cb = ttk.Combobox(add_bar, textvariable=self.add_cb_var, values=self.available_headers, state="readonly", width=22)
            self.add_cb.pack(side=tk.LEFT, padx=(0, 10))

            ttk.Button(add_bar, text="➕ Add to End", command=self._add_column).pack(side=tk.LEFT)

            # Bottom Action Bar
            bottom_frame = ttk.Frame(self, padding=(12, 10))
            bottom_frame.pack(fill=tk.X)

            ttk.Button(bottom_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=(5, 0))
            ttk.Button(bottom_frame, text="Apply Sequence", command=self._apply_sequence).pack(side=tk.RIGHT, padx=5)

        def _populate_listbox(self):
            self.listbox.delete(0, tk.END)
            for idx, col in enumerate(self.current_sequence, 1):
                self.listbox.insert(tk.END, f"{idx}. {col}")

        def _move_up(self):
            sel = self.listbox.curselection()
            if not sel or sel[0] == 0:
                return
            idx = sel[0]
            self.current_sequence[idx - 1], self.current_sequence[idx] = self.current_sequence[idx], self.current_sequence[idx - 1]
            self._populate_listbox()
            self.listbox.selection_set(idx - 1)

        def _move_down(self):
            sel = self.listbox.curselection()
            if not sel or sel[0] == len(self.current_sequence) - 1:
                return
            idx = sel[0]
            self.current_sequence[idx + 1], self.current_sequence[idx] = self.current_sequence[idx], self.current_sequence[idx + 1]
            self._populate_listbox()
            self.listbox.selection_set(idx + 1)

        def _remove_column(self):
            sel = self.listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            del self.current_sequence[idx]
            self._populate_listbox()

        def _reset_default(self):
            self.current_sequence = list(DEFAULT_PRIORITY_COLUMNS)
            self._populate_listbox()

        def _add_column(self):
            val = self.add_cb_var.get().strip()
            if not val:
                return
            if val.lower() in [c.lower() for c in self.current_sequence]:
                messagebox.showinfo("Already Added", f"'{val}' is already in the search sequence.", parent=self)
                return
            self.current_sequence.append(val)
            self._populate_listbox()
            self.listbox.selection_set(len(self.current_sequence) - 1)

        def _apply_sequence(self):
            if not self.current_sequence:
                messagebox.showwarning("Empty Sequence", "Please include at least one column in the sequence.", parent=self)
                return
            if self.on_apply_callback:
                self.on_apply_callback(self.current_sequence)
            self.destroy()


    class MappingHelperDialog(tk.Toplevel):
        """
        Dialog window for cross-checking and batch editing missing device functions / mappings.
        """
        def __init__(self, parent, mapping_file: str, mapping_data: Dict[str, str],
                     unique_functions: Set[str], function_to_devices: Dict[str, List[str]],
                     vlan_types: List[str], on_save_callback=None):
            super().__init__(parent)
            self.title("Device Function Mapping Manager & Batch Editor")
            self.geometry("880x600")
            self.minsize(720, 480)
            self.transient(parent)
            self.grab_set()

            self.mapping_file = mapping_file
            self.mapping_data = dict(mapping_data)
            self.unique_functions = unique_functions
            self.function_to_devices = function_to_devices
            self.vlan_types = vlan_types
            self.on_save_callback = on_save_callback

            self._create_widgets()
            self._populate_table()

        def _create_widgets(self):
            # Header banner
            header_frame = ttk.Frame(self, padding=(12, 10))
            header_frame.pack(fill=tk.X)

            title_lbl = ttk.Label(header_frame, text="Cross-Check Device Functions with mapping.csv", font=("Helvetica", 12, "bold"))
            title_lbl.pack(anchor=tk.W)
            desc_lbl = ttk.Label(header_frame, text="Device names are parsed as <location>-<function><numbering>. Select pre-defined VLAN types from vlan_type.csv.", foreground="#555")
            desc_lbl.pack(anchor=tk.W, pady=(2, 0))

            # Batch edit toolbar
            tool_frame = ttk.LabelFrame(self, text="Batch Operations & Filter", padding=(10, 8))
            tool_frame.pack(fill=tk.X, padx=12, pady=5)

            ttk.Label(tool_frame, text="Show:").pack(side=tk.LEFT, padx=(0, 5))
            self.filter_var = tk.StringVar(value="All")
            filter_cb = ttk.Combobox(tool_frame, textvariable=self.filter_var, values=["All", "Missing / Unmapped Only", "Mapped Only"], state="readonly", width=22)
            filter_cb.pack(side=tk.LEFT, padx=(0, 15))
            filter_cb.bind("<<ComboboxSelected>>", lambda e: self._populate_table())

            ttk.Label(tool_frame, text="Batch Set Selected to:").pack(side=tk.LEFT, padx=(0, 5))
            self.batch_vlan_var = tk.StringVar()
            self.batch_entry = ttk.Combobox(tool_frame, textvariable=self.batch_vlan_var, values=self.vlan_types, width=20)
            self.batch_entry.pack(side=tk.LEFT, padx=(0, 5))

            apply_btn = ttk.Button(tool_frame, text="Apply to Selected", command=self._apply_batch)
            apply_btn.pack(side=tk.LEFT, padx=(0, 5))

            # Table
            table_frame = ttk.Frame(self, padding=(12, 5))
            table_frame.pack(fill=tk.BOTH, expand=True)

            columns = ("function", "status", "vlan_type", "sample_devices")
            self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
            self.tree.heading("function", text="Function Code / Key")
            self.tree.heading("status", text="Status")
            self.tree.heading("vlan_type", text="VLAN Type (Mapping)")
            self.tree.heading("sample_devices", text="Sample Devices Found in CSV")

            self.tree.column("function", width=140, anchor=tk.W)
            self.tree.column("status", width=110, anchor=tk.CENTER)
            self.tree.column("vlan_type", width=200, anchor=tk.W)
            self.tree.column("sample_devices", width=360, anchor=tk.W)

            scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
            scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
            self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

            self.tree.grid(row=0, column=0, sticky="nsew")
            scroll_y.grid(row=0, column=1, sticky="ns")
            scroll_x.grid(row=1, column=0, sticky="ew")

            table_frame.grid_rowconfigure(0, weight=1)
            table_frame.grid_columnconfigure(0, weight=1)

            self.tree.bind("<Double-1>", self._on_double_click)

            # Bottom bar
            bottom_frame = ttk.Frame(self, padding=(12, 10))
            bottom_frame.pack(fill=tk.X)

            add_btn = ttk.Button(bottom_frame, text="+ Add New Function/Key", command=self._add_custom_key)
            add_btn.pack(side=tk.LEFT, padx=(0, 10))

            self.status_lbl = ttk.Label(bottom_frame, text="", foreground="#333")
            self.status_lbl.pack(side=tk.LEFT, padx=10)

            close_btn = ttk.Button(bottom_frame, text="Cancel", command=self.destroy)
            close_btn.pack(side=tk.RIGHT, padx=(5, 0))

            save_btn = ttk.Button(bottom_frame, text="Save to mapping.csv", command=self._save_mappings)
            save_btn.pack(side=tk.RIGHT, padx=5)

        def _populate_table(self):
            self.tree.delete(*self.tree.get_children())
            filter_mode = self.filter_var.get()

            all_keys = sorted(set(list(self.unique_functions) + list(self.mapping_data.keys())))

            missing_count = 0
            mapped_count = 0

            for key in all_keys:
                current_type = self.mapping_data.get(key, "").strip()
                is_missing = not bool(current_type)
                
                if is_missing:
                    missing_count += 1
                    status_text = "MISSING ⚠️"
                else:
                    mapped_count += 1
                    status_text = "Mapped ✅"

                if filter_mode == "Missing / Unmapped Only" and not is_missing:
                    continue
                if filter_mode == "Mapped Only" and is_missing:
                    continue

                samples = ", ".join(self.function_to_devices.get(key, []))
                if not samples and key in self.mapping_data:
                    samples = "(From existing mapping.csv)"

                item_id = self.tree.insert("", tk.END, values=(key, status_text, current_type, samples))
                if is_missing:
                    self.tree.item(item_id, tags=("missing_tag",))

            self.tree.tag_configure("missing_tag", background="#ffebee")
            self.status_lbl.config(text=f"Total: {len(all_keys)} | Mapped: {mapped_count} | Missing: {missing_count}")

        def _on_double_click(self, event):
            item_id = self.tree.identify_row(event.y)
            col = self.tree.identify_column(event.x)
            if not item_id or col != "#3":
                return

            x, y, width, height = self.tree.bbox(item_id, col)
            current_val = self.tree.item(item_id, "values")[2]
            key = self.tree.item(item_id, "values")[0]

            entry = ttk.Combobox(self.tree, values=self.vlan_types)
            entry.set(current_val)
            entry.place(x=x, y=y, width=width, height=height)
            entry.focus_set()

            def _save_edit(e=None):
                new_val = entry.get().strip()
                self.mapping_data[key] = new_val
                entry.destroy()
                self._populate_table()

            entry.bind("<Return>", _save_edit)
            entry.bind("<FocusOut>", lambda e: _save_edit())

        def _apply_batch(self):
            selected_items = self.tree.selection()
            vlan_type = self.batch_vlan_var.get().strip()
            if not vlan_type:
                messagebox.showwarning("Input Required", "Please enter or select a VLAN type to apply.", parent=self)
                return
            if not selected_items:
                messagebox.showinfo("No Selection", "Please select one or more rows from the table.", parent=self)
                return

            for item_id in selected_items:
                key = self.tree.item(item_id, "values")[0]
                self.mapping_data[key] = vlan_type

            self._populate_table()

        def _add_custom_key(self):
            top = tk.Toplevel(self)
            top.title("Add New Function/Key")
            top.geometry("380x180")
            top.transient(self)
            top.grab_set()

            ttk.Label(top, text="Function Code / Device Name:").pack(anchor=tk.W, padx=15, pady=(15, 2))
            key_var = tk.StringVar()
            key_entry = ttk.Entry(top, textvariable=key_var, width=30)
            key_entry.pack(fill=tk.X, padx=15)
            key_entry.focus_set()

            ttk.Label(top, text="VLAN Type:").pack(anchor=tk.W, padx=15, pady=(10, 2))
            type_var = tk.StringVar()
            type_entry = ttk.Combobox(top, textvariable=type_var, values=self.vlan_types)
            type_entry.pack(fill=tk.X, padx=15)

            def _save():
                k = clean_device_token(key_var.get()).lower()
                v = type_var.get().strip()
                if not k or not v:
                    messagebox.showwarning("Missing Data", "Both Key and VLAN Type are required.", parent=top)
                    return
                self.mapping_data[k] = v
                top.destroy()
                self._populate_table()

            btn_frame = ttk.Frame(top)
            btn_frame.pack(fill=tk.X, padx=15, pady=15)
            ttk.Button(btn_frame, text="Add", command=_save).pack(side=tk.RIGHT)
            ttk.Button(btn_frame, text="Cancel", command=top.destroy).pack(side=tk.RIGHT, padx=5)

        def _save_mappings(self):
            cleaned_mapping = {k: v for k, v in self.mapping_data.items() if v.strip()}
            success = save_mapping_file(self.mapping_file, cleaned_mapping)
            if success:
                messagebox.showinfo("Saved", f"Successfully saved {len(cleaned_mapping)} mappings to {self.mapping_file}!", parent=self)
                if self.on_save_callback:
                    self.on_save_callback(cleaned_mapping)
                self.destroy()
            else:
                messagebox.showerror("Error", f"Failed to save {self.mapping_file}.", parent=self)


    class AppGUI(tk.Tk):
        """
        Main Tkinter Application for IP VLAN Converter.
        """
        def __init__(self, default_csv="ip_vlan.csv", default_mapping="mapping.csv", default_types="vlan_type.csv"):
            super().__init__()
            self.title("IP VLAN Converter & Device Classifier")
            self.geometry("1120x760")
            self.minsize(900, 620)

            self.csv_path_var = tk.StringVar(value=default_csv if os.path.exists(default_csv) else "")
            self.mapping_path_var = tk.StringVar(value=default_mapping if os.path.exists(default_mapping) else ("mapping.csv" if os.path.exists("mapping.csv") else ""))
            self.vlan_type_path_var = tk.StringVar(value=default_types)
            self.output_path_var = tk.StringVar(value="ip_vlan_converted.csv")
            self.exclude_p2p_var = tk.BooleanVar(value=False)
            self.priority_columns = list(DEFAULT_PRIORITY_COLUMNS)

            self.vlan_types: List[str] = load_or_create_vlan_types(self.vlan_type_path_var.get())

            self.headers: List[str] = []
            self.raw_rows: List[Dict[str, str]] = []
            self.converted_rows: List[Dict[str, str]] = []
            self.unique_devices: Set[str] = set()
            self.unique_functions: Set[str] = set()
            self.function_to_devices: Dict[str, List[str]] = {}
            self.mapping_data: Dict[str, str] = {}
            self.column_vars: Dict[str, tk.BooleanVar] = {}

            self._setup_style()
            self._create_ui()

            if self.csv_path_var.get() and os.path.exists(self.csv_path_var.get()):
                self._load_input_file(auto_process=True)

        def _setup_style(self):
            style = ttk.Style(self)
            try:
                style.theme_use("clam")
            except Exception:
                pass
            style.configure("Treeview.Heading", font=("Helvetica", 9, "bold"))
            style.configure("Treeview", rowheight=24)

        def _create_ui(self):
            # File Configuration panel
            file_panel = ttk.LabelFrame(self, text="File Configuration", padding=(12, 10))
            file_panel.pack(fill=tk.X, padx=12, pady=(10, 5))

            # Input CSV Row
            ttk.Label(file_panel, text="Input CSV File:").grid(row=0, column=0, sticky=tk.W, pady=3)
            ttk.Entry(file_panel, textvariable=self.csv_path_var, width=50).grid(row=0, column=1, sticky=tk.EW, padx=8, pady=3)
            ttk.Button(file_panel, text="Browse...", command=self._browse_input_file).grid(row=0, column=2, padx=3, pady=3)
            ttk.Button(file_panel, text="Load / Refresh", command=self._load_input_file).grid(row=0, column=3, padx=3, pady=3)

            # Mapping CSV Row
            ttk.Label(file_panel, text="Mapping File:").grid(row=1, column=0, sticky=tk.W, pady=3)
            ttk.Entry(file_panel, textvariable=self.mapping_path_var, width=50).grid(row=1, column=1, sticky=tk.EW, padx=8, pady=3)
            ttk.Button(file_panel, text="Browse...", command=self._browse_mapping_file).grid(row=1, column=2, padx=3, pady=3)
            ttk.Button(file_panel, text="Manage Mappings ⚙️", command=self._open_mapping_manager).grid(row=1, column=3, padx=3, pady=3)

            # VLAN Types File Row
            ttk.Label(file_panel, text="VLAN Types List:").grid(row=2, column=0, sticky=tk.W, pady=3)
            ttk.Entry(file_panel, textvariable=self.vlan_type_path_var, width=50).grid(row=2, column=1, sticky=tk.EW, padx=8, pady=3)
            ttk.Button(file_panel, text="Browse...", command=self._browse_vlan_type_file).grid(row=2, column=2, padx=3, pady=3)
            ttk.Button(file_panel, text="Reload Types 🔄", command=self._reload_vlan_types).grid(row=2, column=3, padx=3, pady=3)

            file_panel.grid_columnconfigure(1, weight=1)

            # Middle Container: Split Pane
            paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
            paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

            # Left Frame: Output Column Selection
            left_frame = ttk.LabelFrame(paned, text="Output Columns", padding=(8, 8), width=230)
            paned.add(left_frame, weight=1)

            col_btn_bar = ttk.Frame(left_frame)
            col_btn_bar.pack(fill=tk.X, pady=(0, 5))
            ttk.Button(col_btn_bar, text="Select All", width=9, command=lambda: self._set_all_columns(True)).pack(side=tk.LEFT, padx=1)
            ttk.Button(col_btn_bar, text="Deselect All", width=10, command=lambda: self._set_all_columns(False)).pack(side=tk.LEFT, padx=1)

            self.col_canvas = tk.Canvas(left_frame, borderwidth=0, highlightthickness=0)
            self.col_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.col_canvas.yview)
            self.col_inner_frame = ttk.Frame(self.col_canvas)

            self.col_inner_frame.bind("<Configure>", lambda e: self.col_canvas.configure(scrollregion=self.col_canvas.bbox("all")))
            self.col_canvas.create_window((0, 0), window=self.col_inner_frame, anchor="nw")
            self.col_canvas.configure(yscrollcommand=self.col_scroll.set)

            self.col_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.col_scroll.pack(side=tk.RIGHT, fill=tk.Y)

            # Right Frame: Data Preview
            right_frame = ttk.LabelFrame(paned, text="Data Preview (Identified VLAN Type)", padding=(8, 8))
            paned.add(right_frame, weight=4)

            # Header info, Sequence button, and Subnet Filter row
            info_bar = ttk.Frame(right_frame)
            info_bar.pack(fill=tk.X, pady=(0, 4))

            self.seq_lbl = ttk.Label(info_bar, text=self._format_sequence_text(), foreground="#2c3e50", font=("Helvetica", 9, "italic"))
            self.seq_lbl.pack(side=tk.LEFT)

            seq_cfg_btn = ttk.Button(info_bar, text="Adjust Sequence ↕️", command=self._open_sequence_config)
            seq_cfg_btn.pack(side=tk.LEFT, padx=(8, 0))

            p2p_cb = ttk.Checkbutton(info_bar, text="Exclude P2P / Loopback (/30, /31, /32)", variable=self.exclude_p2p_var, command=self._process_and_preview)
            p2p_cb.pack(side=tk.RIGHT, padx=5)

            preview_container = ttk.Frame(right_frame)
            preview_container.pack(fill=tk.BOTH, expand=True)

            self.preview_tree = ttk.Treeview(preview_container, show="headings", selectmode="browse")
            preview_scrolly = ttk.Scrollbar(preview_container, orient=tk.VERTICAL, command=self.preview_tree.yview)
            preview_scrollx = ttk.Scrollbar(preview_container, orient=tk.HORIZONTAL, command=self.preview_tree.xview)
            self.preview_tree.configure(yscrollcommand=preview_scrolly.set, xscrollcommand=preview_scrollx.set)

            self.preview_tree.grid(row=0, column=0, sticky="nsew")
            preview_scrolly.grid(row=0, column=1, sticky="ns")
            preview_scrollx.grid(row=1, column=0, sticky="ew")

            preview_container.grid_rowconfigure(0, weight=1)
            preview_container.grid_columnconfigure(0, weight=1)

            # Bottom Export Panel
            bottom_panel = ttk.LabelFrame(self, text="Export Converted Data", padding=(12, 10))
            bottom_panel.pack(fill=tk.X, padx=12, pady=(5, 10))

            ttk.Label(bottom_panel, text="Output CSV File:").grid(row=0, column=0, sticky=tk.W, pady=3)
            ttk.Entry(bottom_panel, textvariable=self.output_path_var, width=50).grid(row=0, column=1, sticky=tk.EW, padx=8, pady=3)
            ttk.Button(bottom_panel, text="Browse...", command=self._browse_output_file).grid(row=0, column=2, padx=3, pady=3)

            export_btn = ttk.Button(bottom_panel, text="Convert & Export CSV 💾", command=self._export_csv)
            export_btn.grid(row=0, column=3, padx=10, pady=3)

            bottom_panel.grid_columnconfigure(1, weight=1)

            # Status bar
            self.statusbar = ttk.Label(self, text="Ready.", relief=tk.SUNKEN, anchor=tk.W, padding=(6, 3))
            self.statusbar.pack(fill=tk.X, side=tk.BOTTOM)

        def _format_sequence_text(self) -> str:
            steps = [f"{i}. {c}" for i, c in enumerate(self.priority_columns, 1)]
            return "Sequence: " + " ➔ ".join(steps)

        def _open_sequence_config(self):
            def _on_sequence_applied(new_sequence):
                self.priority_columns = new_sequence
                self.seq_lbl.config(text=self._format_sequence_text())
                self._process_and_preview()

            # Include available headers and standard columns
            avail = sorted(set(self.headers + KNOWN_DEVICE_COLUMNS))
            SequenceConfigDialog(
                self,
                current_sequence=self.priority_columns,
                available_headers=avail,
                on_apply_callback=_on_sequence_applied
            )

        def _browse_input_file(self):
            path = filedialog.askopenfilename(title="Select Input CSV (e.g. ip_vlan.csv)", filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
            if path:
                self.csv_path_var.set(path)
                self._load_input_file(auto_process=True)

        def _browse_mapping_file(self):
            path = filedialog.askopenfilename(title="Select mapping.csv", filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
            if path:
                self.mapping_path_var.set(path)
                self._reload_mappings()
                self._process_and_preview()

        def _browse_vlan_type_file(self):
            path = filedialog.askopenfilename(title="Select vlan_type.csv", filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
            if path:
                self.vlan_type_path_var.set(path)
                self._reload_vlan_types()

        def _reload_vlan_types(self):
            path = self.vlan_type_path_var.get().strip() or "vlan_type.csv"
            self.vlan_types = load_or_create_vlan_types(path)
            self.statusbar.config(text=f"Loaded {len(self.vlan_types)} pre-defined VLAN types from {path}.")

        def _browse_output_file(self):
            path = filedialog.asksaveasfilename(title="Select Output CSV Destination", defaultextension=".csv", filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
            if path:
                self.output_path_var.set(path)

        def _reload_mappings(self):
            mapping_path = self.mapping_path_var.get().strip() or "mapping.csv"
            self.mapping_data = load_mapping_file(mapping_path)

        def _load_input_file(self, auto_process=True):
            csv_path = self.csv_path_var.get().strip()
            if not csv_path or not os.path.exists(csv_path):
                messagebox.showerror("File Error", f"Cannot find input file: {csv_path}")
                return

            try:
                self.headers, self.raw_rows, self.unique_devices, self.unique_functions, self.function_to_devices = scan_devices_and_functions(csv_path)
                self._reload_mappings()
                self._reload_vlan_types()
                self._build_column_selector()

                if auto_process:
                    self._process_and_preview()

                missing = cross_check_missing_mappings(self.unique_functions, self.unique_devices, self.mapping_data)
                if missing:
                    self.statusbar.config(text=f"Loaded {len(self.raw_rows)} rows. ⚠️ {len(missing)} function(s) missing in mapping.csv: {', '.join(missing[:5])}...")
                else:
                    self.statusbar.config(text=f"Loaded {len(self.raw_rows)} rows. All device functions mapped.")

            except Exception as e:
                messagebox.showerror("Error Reading CSV", str(e))

        def _build_column_selector(self):
            for widget in self.col_inner_frame.winfo_children():
                widget.destroy()
            self.column_vars.clear()

            display_cols = ["vlan_type", "matched_device", "matched_source"] + [h for h in self.headers if h not in ["vlan_type", "matched_device", "matched_source"]]

            for col in display_cols:
                var = tk.BooleanVar(value=True)
                self.column_vars[col] = var
                cb = ttk.Checkbutton(self.col_inner_frame, text=col, variable=var, command=self._on_column_toggle)
                cb.pack(anchor=tk.W, pady=1)

        def _set_all_columns(self, select: bool):
            for var in self.column_vars.values():
                var.set(select)
            self._process_and_preview()

        def _on_column_toggle(self):
            self._process_and_preview()

        def _process_and_preview(self):
            if not self.raw_rows:
                return

            self.converted_rows = []
            excluded_p2p_count = 0
            for row in self.raw_rows:
                if self.exclude_p2p_var.get() and is_p2p_or_loopback_row(row, self.headers):
                    excluded_p2p_count += 1
                    continue
                vtype, mdev, mcol = match_vlan_type(row, self.headers, self.mapping_data, priority_columns=self.priority_columns)
                row_copy = dict(row)
                row_copy["vlan_type"] = vtype
                row_copy["matched_device"] = mdev
                row_copy["matched_source"] = mcol
                self.converted_rows.append(row_copy)

            active_cols = [c for c, var in self.column_vars.items() if var.get()]
            if not active_cols:
                active_cols = ["vlan_type"] + self.headers

            self.preview_tree.delete(*self.preview_tree.get_children())
            self.preview_tree["columns"] = active_cols

            for col in active_cols:
                self.preview_tree.heading(col, text=col)
                self.preview_tree.column(col, width=120, anchor=tk.W)

            for row in self.converted_rows[:500]:
                vals = [row.get(col, "") for col in active_cols]
                self.preview_tree.insert("", tk.END, values=vals)

            if self.exclude_p2p_var.get() and excluded_p2p_count > 0:
                self.statusbar.config(text=f"Showing {len(self.converted_rows)} rows (Excluded {excluded_p2p_count} P2P/Loopback /30-/32 rows).")

        def _open_mapping_manager(self):
            mapping_path = self.mapping_path_var.get().strip() or "mapping.csv"
            
            def _on_save(new_mapping):
                self.mapping_data = new_mapping
                self.mapping_path_var.set(mapping_path)
                self._process_and_preview()

            MappingHelperDialog(
                self,
                mapping_file=mapping_path,
                mapping_data=self.mapping_data,
                unique_functions=self.unique_functions,
                function_to_devices=self.function_to_devices,
                vlan_types=self.vlan_types,
                on_save_callback=_on_save
            )

        def _export_csv(self):
            if not self.converted_rows:
                messagebox.showwarning("No Data", "Please load an input CSV first.")
                return

            out_path = self.output_path_var.get().strip()
            if not out_path:
                messagebox.showwarning("Invalid Path", "Please specify a valid output CSV filename.")
                return

            active_cols = [c for c, var in self.column_vars.items() if var.get()]
            if not active_cols:
                messagebox.showwarning("No Columns", "Please select at least one column to output.")
                return

            try:
                with open(out_path, mode="w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=active_cols, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(self.converted_rows)

                messagebox.showinfo("Export Successful", f"Exported {len(self.converted_rows)} rows to:\n{out_path}")
                self.statusbar.config(text=f"Export completed: {out_path}")
            except Exception as e:
                messagebox.showerror("Export Failed", str(e))


# ==============================================================================
# CLI Mode (Fallback / Terminal Interactive & Non-Interactive)
# ==============================================================================

def run_cli_mapping_manager(mapping_path: str, mapping_data: Dict[str, str],
                            unique_functions: Set[str], function_to_devices: Dict[str, List[str]],
                            vlan_types: List[str]) -> Dict[str, str]:
    """
    Interactive CLI tool for cross-checking device functions and batch editing missing mappings.
    """
    print("\n" + "=" * 65)
    print("      DEVICE FUNCTION MAPPING HELPER & BATCH EDITOR")
    print("=" * 65)

    all_keys = sorted(set(list(unique_functions) + list(mapping_data.keys())))
    missing_keys = [k for k in all_keys if not mapping_data.get(k, "").strip()]

    print(f"\nTotal Functions/Keys Found: {len(all_keys)}")
    print(f"Mapped: {len(all_keys) - len(missing_keys)} | Missing: {len(missing_keys)}")
    print(f"Pre-defined VLAN Types Available ({len(vlan_types)}): {', '.join(vlan_types[:6])}...")

    while True:
        print("\nOptions:")
        print("  1. List all functions & current mappings")
        print("  2. List missing/unmapped functions only")
        print("  3. Batch edit / assign VLAN type to missing functions")
        print("  4. Edit / add a specific function mapping")
        print("  5. Save to mapping.csv and return")
        print("  6. Return without saving")
        
        choice = input("\nEnter option (1-6): ").strip()

        if choice == "1":
            print("\n" + "-" * 75)
            print(f"{'Key / Function':<18} | {'Status':<10} | {'VLAN Type':<20} | {'Sample Devices'}")
            print("-" * 75)
            for k in all_keys:
                vtype = mapping_data.get(k, "")
                status = "Mapped" if vtype else "MISSING"
                samples = ", ".join(function_to_devices.get(k, []))[:30]
                print(f"{k:<18} | {status:<10} | {vtype:<20} | {samples}")
            print("-" * 75)

        elif choice == "2":
            missing_keys = [k for k in all_keys if not mapping_data.get(k, "").strip()]
            if not missing_keys:
                print("\n[OK] Great! No missing functions found. All functions are mapped.")
            else:
                print("\n" + "-" * 75)
                print(f"{'Missing Function':<18} | {'Sample Devices Found in CSV'}")
                print("-" * 75)
                for k in missing_keys:
                    samples = ", ".join(function_to_devices.get(k, []))
                    print(f"{k:<18} | {samples}")
                print("-" * 75)

        elif choice == "3":
            missing_keys = [k for k in all_keys if not mapping_data.get(k, "").strip()]
            if not missing_keys:
                print("\nNo missing functions to edit.")
                continue

            print(f"\nFound {len(missing_keys)} missing functions:")
            for idx, k in enumerate(missing_keys, 1):
                samples = ", ".join(function_to_devices.get(k, []))[:35]
                print(f"  [{idx}] {k} (samples: {samples})")

            print("\nPre-defined VLAN Type Options (from vlan_type.csv):")
            for i, vt in enumerate(vlan_types, 1):
                print(f"  [{i}] {vt}")
            print("  [c] Custom text input | [s] Skip item")

            for k in list(missing_keys):
                samples = ", ".join(function_to_devices.get(k, []))
                ans = input(f"\nEnter choice for '{k}' (samples: {samples}) [1-{len(vlan_types)}/custom/s]: ").strip()
                if ans.lower() == "s" or not ans:
                    continue
                elif ans.isdigit():
                    num = int(ans)
                    if 1 <= num <= len(vlan_types):
                        mapping_data[k] = vlan_types[num - 1]
                    else:
                        print(f"Invalid selection number. Skipping '{k}'.")
                elif ans.lower() == "c":
                    custom_vt = input(f"Enter custom VLAN type for '{k}': ").strip()
                    if custom_vt:
                        mapping_data[k] = custom_vt
                else:
                    mapping_data[k] = ans

            print("\nBatch update complete.")

        elif choice == "4":
            key = input("\nEnter function code or device name (e.g. svrx or asdasd-svrx001): ").strip().lower()
            if key:
                print(f"\nSelect VLAN type for '{key}':")
                for i, vt in enumerate(vlan_types, 1):
                    print(f"  [{i}] {vt}")
                val_in = input("Enter number or custom VLAN type name: ").strip()
                if val_in.isdigit() and 1 <= int(val_in) <= len(vlan_types):
                    vtype = vlan_types[int(val_in) - 1]
                else:
                    vtype = val_in

                if vtype:
                    mapping_data[key] = vtype
                    if key not in all_keys:
                        all_keys.append(key)
                    print(f"[OK] Set '{key}' -> '{vtype}'")

        elif choice == "5":
            save_mapping_file(mapping_path, mapping_data)
            print(f"\n[Saved] Successfully wrote mappings to {mapping_path}")
            break

        elif choice == "6":
            print("\nExiting mapping helper without saving.")
            break

    return mapping_data


def run_cli_mode(input_file: Optional[str] = None,
                 mapping_file: Optional[str] = None,
                 vlan_type_file: Optional[str] = None,
                 output_file: Optional[str] = None,
                 selected_cols: Optional[List[str]] = None,
                 priority_sequence: Optional[List[str]] = None,
                 exclude_p2p: bool = False,
                 interactive: bool = True):
    """
    Executes the conversion in CLI mode with optional interactive prompts.
    """
    print("=" * 65)
    print("      IP VLAN Converter & Classifier (CLI Mode)")
    print("=" * 65)

    # 1. Resolve Input File
    if not input_file:
        default_csv = "ip_vlan.csv"
        if os.path.exists(default_csv):
            if interactive and sys.stdin.isatty():
                use_default = input(f"Default input file '{default_csv}' found. Use it? [Y/n]: ").strip().lower()
                if use_default in ["", "y", "yes"]:
                    input_file = default_csv
            else:
                input_file = default_csv
        
        if not input_file:
            if interactive and sys.stdin.isatty():
                while True:
                    input_file = input("Enter path to input CSV file: ").strip()
                    if os.path.exists(input_file):
                        break
                    print(f"[Error] File not found: {input_file}. Please try again.")
            else:
                input_file = "ip_vlan.csv"

    # 2. Resolve Mapping File
    if not mapping_file:
        default_map = "mapping.csv"
        if os.path.exists(default_map) or not (interactive and sys.stdin.isatty()):
            mapping_file = default_map
        else:
            mapping_file = input(f"Enter path to mapping.csv [default: {default_map}]: ").strip() or default_map

    # 3. Resolve VLAN Types File
    if not vlan_type_file:
        vlan_type_file = "vlan_type.csv"

    vlan_types = load_or_create_vlan_types(vlan_type_file)

    # 4. Resolve Output File
    if not output_file:
        default_out = "ip_vlan_converted.csv"
        if interactive and sys.stdin.isatty():
            output_file = input(f"Enter path for output CSV [default: {default_out}]: ").strip() or default_out
        else:
            output_file = default_out

    # 5. Resolve Exclude P2P / Loopback
    if interactive and sys.stdin.isatty() and not exclude_p2p:
        p2p_ans = input("Exclude P2P and Loopback subnets (/30, /31, /32)? [y/N]: ").strip().lower()
        if p2p_ans in ["y", "yes"]:
            exclude_p2p = True

    print(f"\nLoading input CSV: {input_file} ...")
    headers, rows, unique_devices, unique_functions, function_to_devices = scan_devices_and_functions(input_file)
    mapping_data = load_mapping_file(mapping_file)

    print(f"Total Rows: {len(rows)}")
    print(f"Unique Devices: {len(unique_devices)} | Unique Functions: {len(unique_functions)}")

    # Filter out P2P/Loopback rows if enabled
    if exclude_p2p:
        initial_len = len(rows)
        rows = [r for r in rows if not is_p2p_or_loopback_row(r, headers)]
        print(f"[Filter] Excluded {initial_len - len(rows)} P2P/Loopback rows (/30, /31, /32). Remaining: {len(rows)} rows.")

    # Resolve search priority sequence
    sequence = priority_sequence or list(DEFAULT_PRIORITY_COLUMNS)
    if interactive and sys.stdin.isatty() and not priority_sequence:
        seq_str = " ➔ ".join([f"{i}. {c}" for i, c in enumerate(sequence, 1)])
        print(f"\nCurrent Matching Sequence: {seq_str}")
        adjust_seq = input("Would you like to adjust the search sequence? [y/N]: ").strip().lower()
        if adjust_seq in ["y", "yes"]:
            print(f"Available columns: {', '.join(headers)}")
            custom_seq = input("Enter comma-separated column names in priority order: ").strip()
            if custom_seq:
                sequence = [c.strip() for c in custom_seq.split(",") if c.strip()]
                print(f"[OK] Updated sequence: {' ➔ '.join(sequence)}")

    missing = cross_check_missing_mappings(unique_functions, unique_devices, mapping_data)
    if missing:
        print(f"\n[Warning] {len(missing)} device function(s) missing in {mapping_file}:")
        print(f"  Missing: {', '.join(missing)}")
        if interactive and sys.stdin.isatty():
            manage = input("\nWould you like to open the Mapping Helper to edit/fill missing mappings? [Y/n]: ").strip().lower()
            if manage in ["", "y", "yes"]:
                mapping_data = run_cli_mapping_manager(mapping_file, mapping_data, unique_functions, function_to_devices, vlan_types)
    else:
        print(f"\n[OK] All {len(unique_functions)} device functions are mapped in {mapping_file}.")

    # 6. Perform Matching & Conversion
    print(f"\nProcessing VLAN Types according to sequence ({' -> '.join(sequence)})...")
    converted_rows = []
    vlan_type_counts: Dict[str, int] = {}

    for row in rows:
        vtype, mdev, mcol = match_vlan_type(row, headers, mapping_data, priority_columns=sequence)
        row_copy = dict(row)
        row_copy["vlan_type"] = vtype
        row_copy["matched_device"] = mdev
        row_copy["matched_source"] = mcol
        converted_rows.append(row_copy)
        vlan_type_counts[vtype] = vlan_type_counts.get(vtype, 0) + 1

    # 7. Output Column Selection
    all_available_cols = ["vlan_type", "matched_device", "matched_source"] + [h for h in headers if h not in ["vlan_type", "matched_device", "matched_source"]]
    final_cols = selected_cols

    if not final_cols:
        if interactive and sys.stdin.isatty():
            print("\nAvailable Output Columns:")
            for i, col in enumerate(all_available_cols, 1):
                print(f"  [{i}] {col}")
            col_choice = input("\nEnter column numbers to include (comma-separated, e.g. '1,2,4,5') or press ENTER for ALL: ").strip()
            if col_choice:
                try:
                    indices = [int(idx.strip()) - 1 for idx in col_choice.split(",") if idx.strip().isdigit()]
                    final_cols = [all_available_cols[i] for i in indices if 0 <= i < len(all_available_cols)]
                except Exception:
                    final_cols = all_available_cols
            else:
                final_cols = all_available_cols
        else:
            final_cols = all_available_cols

    # 8. Write Output File
    try:
        with open(output_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=final_cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(converted_rows)
        print(f"\n[Success] Processed {len(converted_rows)} rows -> {output_file}")
        print("\nVLAN Type Summary:")
        for vt, cnt in sorted(vlan_type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {vt}: {cnt}")
    except Exception as e:
        print(f"[Error] Failed to write output file {output_file}: {e}")


# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="IP VLAN Converter & Device Classifier (GUI with CLI fallback)")
    parser.add_argument("-i", "--input", help="Path to input ip_vlan.csv", default=None)
    parser.add_argument("-m", "--mapping", help="Path to mapping.csv", default=None)
    parser.add_argument("-t", "--types", "--vlan-types", dest="types", help="Path to vlan_type.csv", default="vlan_type.csv")
    parser.add_argument("-s", "--sequence", "--priority", dest="sequence", help="Comma-separated column search sequence (e.g. user,root_bridge,standby,non_active)", default=None)
    parser.add_argument("-o", "--output", help="Path to output CSV", default=None)
    parser.add_argument("-c", "--columns", help="Comma-separated list of columns to output", default=None)
    parser.add_argument("--exclude-p2p", action="store_true", help="Exclude Point-to-Point (/30, /31) and Loopback (/32) subnets from output")
    parser.add_argument("--cli", action="store_true", help="Force CLI mode even if GUI/Tkinter is available")
    parser.add_argument("-y", "--yes", action="store_true", help="Non-interactive batch mode (accept all defaults)")

    args = parser.parse_args()

    selected_cols = [c.strip() for c in args.columns.split(",")] if args.columns else None
    sequence_cols = [c.strip() for c in args.sequence.split(",")] if args.sequence else None

    # Determine execution mode: CLI forced or no GUI available
    if args.cli or not HAS_TKINTER:
        if not HAS_TKINTER and not args.cli:
            print("[Info] No graphical display / Tkinter environment detected. Falling back to CLI mode.")
        run_cli_mode(
            input_file=args.input,
            mapping_file=args.mapping,
            vlan_type_file=args.types,
            output_file=args.output,
            selected_cols=selected_cols,
            priority_sequence=sequence_cols,
            exclude_p2p=args.exclude_p2p,
            interactive=not args.yes
        )
    else:
        # Launch Tkinter GUI
        default_in = args.input or ("ip_vlan.csv" if os.path.exists("ip_vlan.csv") else "")
        default_map = args.mapping or ("mapping.csv" if os.path.exists("mapping.csv") else "")
        app = AppGUI(default_csv=default_in, default_mapping=default_map, default_types=args.types)
        if sequence_cols:
            app.priority_columns = sequence_cols
            app.seq_lbl.config(text=app._format_sequence_text())
        if args.exclude_p2p:
            app.exclude_p2p_var.set(True)
        if default_in:
            app._process_and_preview()
        app.mainloop()


if __name__ == "__main__":
    main()
