# Requirements: IP VLAN Converter & Device Classifier

## 1. Objective
A Python utility designed to process network subnet/VLAN data from a CSV file (`ip_vlan.csv`), extract and clean network device names, determine VLAN types by matching against a lookup file (`mapping.csv`) using a customizable priority sequence, provide a Mapping Helper interface to cross-check and batch-edit missing device functions using pre-defined VLAN types from `vlan_type.csv`, provide options to filter out Point-to-Point and Loopback subnets (`/30`, `/31`, `/32`), and allow customizable column selection for output export.

---

## 2. Input Specifications

### 2.1 Main Input CSV (`ip_vlan.csv`)
- **Default Filename**: `ip_vlan.csv` (if not found, prompt the user or open file dialog).
- **Dynamic Headers**: Column names are read dynamically from the CSV file.
- **Expected / Common Columns**:
  - `subnet`
  - `vlan`
  - `root_bridge`
  - `vdc`
  - `vrf`
  - `active`
  - `active_interface`
  - `standby`
  - `standby_interface`
  - `non_active`
  - `edge`
  - `network`
  - `user`
  - `bridge`

### 2.2 Mapping File (`mapping.csv`)
- **Format**: CSV containing 2 columns: `<device_or_function>,<vlan_type>`
- **Examples**:
  ```csv
  asdasd-svrx001,server vlan
  sdasds-usrs,user vlan
  svrx,server vlan
  usrs,user vlan
  dmz,dmz vlan
  ```

### 2.3 Pre-defined VLAN Types File (`vlan_type.csv`)
- **Purpose**: Stores pre-defined VLAN types (e.g. `server vlan`, `user vlan`, `management vlan`, `voice vlan`, `dmz vlan`, etc.) used to populate dropdowns, quick selections, and batch editors in the Mapping Helper.
- **Auto-Generation**: If `vlan_type.csv` is not found, the script automatically generates a standard `vlan_type.csv` file with default types.
- **Format**: Single-column CSV with header `vlan_type`.

---

## 3. Device Name Parsing & Cleaning Rules

1. **Multiple Devices in One Cell**:
   - Device names in a cell may be separated by commas (`,`), semicolons (`;`), pipes (`|`), or newlines.
   - The script splits these into individual device tokens.

2. **Annotation / Notation Removal**:
   - Strip parenthetical/bracketed notations such as `(1)`, `(2)`, `[1]`, `(primary)`, `#1`, etc.
   - Strip leading/trailing whitespace and punctuation.

3. **Device Name Structure**:
   - Format: `<location>-<function><numbering>` (separated by `-`).
   - **Example 1**: `asdasd-svrx001`
     - **Location**: `asdasd`
     - **Function**: `svrx` (e.g. server)
     - **Numbering**: `001`
   - **Example 2**: `sdasds-usrs`
     - **Location**: `sdasds`
     - **Function**: `usrs` (e.g. user)
     - **Numbering**: *(none)*

---

## 4. Configurable VLAN Type Priority Matching Sequence

### 4.1 Default Priority Order
$$\mathbf{1.\text{ } user} \longrightarrow \mathbf{2.\text{ } root\_bridge} \longrightarrow \mathbf{3.\text{ } standby} \longrightarrow \mathbf{4.\text{ } non\_active}$$

### 4.2 Sequence Customization
- **GUI Mode**: Click **`Adjust Sequence ↕️`** to open the sequence configuration dialog. Users can reorder columns with `Move Up` / `Move Down`, add any column from the CSV header list, remove columns, or reset to default.
- **CLI Mode**: Interactive prompt to reorder sequence, or CLI flag `-s / --sequence` (e.g. `--sequence user,root_bridge,active,standby`).

### 4.3 Lookup Rules for Each Candidate Device:
1. **Exact Device Match**: Check if full device name exists in `mapping.csv` (e.g., `asdasd-svrx001`).
2. **Function Match**: If no full device match, check if the extracted function code exists in `mapping.csv` (e.g., `svrx`).
3. The first matched candidate determines the `vlan_type` for that row.
4. If no device in the configured sequence columns matches, label as `Unmapped`.

---

## 5. Subnet Filtering (P2P & Loopback Exclusion)

- **Option to Exclude Point-to-Point and Loopback / Host subnets**:
  - Filter out subnets with masks `/30`, `/31`, and `/32` (or dotted decimal masks `255.255.255.252`, `255.255.255.254`, `255.255.255.255`).
- **GUI**: Interactive checkbutton `Exclude P2P / Loopback (/30, /31, /32)` with instant preview update.
- **CLI**: Prompt in interactive mode and flag `--exclude-p2p` in batch/CLI mode.

---

## 6. Mapping Helper Interface (Cross-Check & Batch Editor)

1. **Scan & Cross-Check**:
   - Scan all device columns in `ip_vlan.csv` (`user`, `root_bridge`, `standby`, `non_active`, `active`, `edge`, `bridge`).
   - Extract all unique device functions and device names.
   - Cross-check against `mapping.csv` to find all functions missing from the mapping file.

2. **Batch Editing & Management**:
   - Display a list/table of all functions with mapping status (`Mapped` vs `MISSING`).
   - Populate dropdowns/options using pre-defined types loaded from `vlan_type.csv`.
   - Allow user to batch assign VLAN types to missing functions (e.g., select multiple rows $\rightarrow$ set to `server vlan`, `user vlan`, `dmz vlan`, etc.).
   - Allow adding custom function/device entries.
   - Save updated mappings directly back to `mapping.csv`.

---

## 7. Output & Export Customization

1. **Output Column Selection**:
   - Allow the user to select which columns to include in the exported CSV.
   - Option to include `vlan_type`, `matched_device`, `matched_source`, alongside any subset of original columns from `ip_vlan.csv`.
2. **Export File**:
   - Save converted data to user-specified output CSV (default: `ip_vlan_converted.csv`).

---

## 8. Dual Mode Architecture (GUI & CLI)

- **GUI Mode**:
  - Built with Python standard `tkinter` / `ttk`.
  - Visual file selectors, live preview table, sequence adjuster dialog, P2P/loopback filter toggle, column checklist, and Mapping Manager modal.
- **CLI Mode**:
  - Automatic fallback when no GUI / display environment is available, or when `--cli` is passed.
  - Interactive prompts for sequence reordering, choices from `vlan_type.csv`, P2P filter option, plus `-y` / `--yes` flag for automated headless batch scripting.
