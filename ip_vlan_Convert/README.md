# IP VLAN Converter & Device Classifier

A Python utility with GUI and CLI modes to convert network IP VLAN spreadsheets, classify VLAN types using device naming rules and customizable priority sequence matching against `mapping.csv`, filter out P2P/Loopback subnets, and manage device function mappings with pre-defined types from `vlan_type.csv`.

For complete specifications, see [REQUIREMENTS.md](file:///home/keith/OneDrive/script/ip_vlan_Convert/REQUIREMENTS.md).

## Features
- **Configurable Search Sequence**: Adjust the device matching sequence (default: `user` $\rightarrow$ `root_bridge` $\rightarrow$ `standby` $\rightarrow$ `non_active`). Reorder or add any column from your CSV.
- **P2P & Loopback Subnet Exclusion**: Option to filter out `/30`, `/31`, and `/32` subnets from the converted output and preview.
- **Pre-defined VLAN Types (`vlan_type.csv`)**: Loads predefined types for all dropdowns/batch editors. Automatically auto-generates `vlan_type.csv` if not present.
- **Mapping Helper & Batch Editor**: Cross-checks missing functions and batch-assigns VLAN types.
- **Column Customization**: Select which columns to output.
- **Dual GUI / CLI Mode**: Tkinter interface with automatic fallback to interactive/batch CLI.

## Quick Start

### 1. Run in GUI Mode
```bash
python3 ip_vlan_convert.py
```

### 2. Run in Interactive CLI Mode
```bash
python3 ip_vlan_convert.py --cli
```

### 3. Run in Non-Interactive / Batch Mode (with Custom Sequence & P2P Exclusion)
```bash
python3 ip_vlan_convert.py --cli -y \
  --input ip_vlan.csv \
  --mapping mapping.csv \
  --types vlan_type.csv \
  --sequence user,root_bridge,active,standby,non_active \
  --exclude-p2p \
  --output ip_vlan_converted.csv \
  --columns vlan_type,subnet,vlan,root_bridge,user,non_active
```
