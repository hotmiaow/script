# Requirements & Test Specifications: Cisco & FortiGate Interface Information Extractor

## 1. Overview
The **Cisco & FortiGate Interface Information Extractor** (`Cisco Interface Information Extractor.py`) parses network device configurations (Cisco IOS, IOS-XE, NX-OS, and Fortinet FortiOS) to extract:
- Hostname / Device Name (with VDOM context when applicable)
- Interface Name
- IP Address & Subnet (in CIDR notation)
- VRF (for Cisco)
- Security Zone (for FortiGate)
- Description

---

## 2. Requirements

### Requirement 1: FortiGate Inline & Chained Zone Commands
The parser **must** accurately extract the VDOM, Zone name, and Interface names from single-line / chained CLI commands without requiring multi-line indentation or trailing `next`/`end` statements.

#### Supported Syntaxes:
1. **Unquoted interface name with VDOM**:
   ```fortios
   config vdom edit App config system zone edit "AAA-Zone" set interface VL1.1234
   ```
   - **Expected Mapping**: `App::VL1.1234 -> AAA-Zone`
   - **Output Row**: `device_name: "<Device> (VDOM: App)"`, `interface_name: "VL1.1234"`, `zone: "AAA-Zone"`

2. **Quoted interface name with VDOM**:
   ```fortios
   config vdom edit App config system zone edit "AAA-Zone" set interface "LAG1.1111"
   ```
   - **Expected Mapping**: `App::LAG1.1111 -> AAA-Zone`
   - **Output Row**: `device_name: "<Device> (VDOM: App)"`, `interface_name: "LAG1.1111"`, `zone: "AAA-Zone"`

3. **Multiple interfaces per zone command**:
   ```fortios
   config vdom edit App config system zone edit "AAA-Zone" set interface "LAG1.1111" VL1.1234 "port3"
   ```
   - **Expected Mapping**:
     - `App::LAG1.1111 -> AAA-Zone`
     - `App::VL1.1234 -> AAA-Zone`
     - `App::port3 -> AAA-Zone`

4. **Global inline zone commands (outside of VDOM)**:
   ```fortios
   config system zone edit "Global-Zone" set interface port1 "port2"
   ```
   - **Expected Mapping**:
     - `root::port1 -> Global-Zone`
     - `root::port2 -> Global-Zone`

---

### Requirement 2: Hierarchical Multi-Line VDOM and Zone Scope Isolation
When parsing standard multi-line FortiGate configurations, inner `end` or `next` statements (such as the end of a zone or address section) **must not** truncate the parsing of outer VDOM blocks.

```fortios
config vdom
    edit App
        config system zone
            edit "AAA-Zone"
                set interface VL1.1234
            next
            edit "BBB-Zone"
                set interface "LAG1.1111"
            next
        end
    next
    edit App2
        config system zone
            edit "CCC-Zone"
                set interface "port2"
            next
        end
    next
end
```
- **App** contains both `AAA-Zone` (`VL1.1234`) and `BBB-Zone` (`LAG1.1111`).
- **App2** contains `CCC-Zone` (`port2`).
- Zone names (`AAA-Zone`, `BBB-Zone`, `CCC-Zone`) must never be misclassified as VDOM names.

---

### Requirement 3: Zone Lookup Resolution Priority
When associating an interface to its security zone, `get_zone_for_interface()` must evaluate candidates in the following strict priority:
1. **Exact VDOM Match**: `f"{vdom_name}::{interface_name}"`
2. **Root VDOM Fallback**: `f"root::{interface_name}"`
3. **Unknown VDOM Fallback**: `f"unknown::{interface_name}"`
4. **Case-Insensitive Match**: Matches case variations (e.g. `lag1.1111` vs `LAG1.1111`).
5. **Default**: Returns `"No Zone"` if no mapping exists.

---

## 3. Automated Test Suite

A dedicated regression test suite is located at:
`cisco interface ip extract and use it traceroute/test_cisco_extractor.py`

### Test Cases Included:
| Test Method | Category | Verified Behavior |
| :--- | :--- | :--- |
| `test_inline_vdom_zone_unquoted_interface` | FortiGate Inline | Extracts `App::VL1.1234 -> AAA-Zone` from single-line command |
| `test_inline_vdom_zone_quoted_interface` | FortiGate Inline | Extracts `App::LAG1.1111 -> AAA-Zone` from single-line command |
| `test_inline_vdom_multiple_interfaces` | FortiGate Inline | Extracts multiple interfaces from a single `set interface` |
| `test_inline_global_zone` | FortiGate Inline | Extracts global zone mappings to `root::<iface>` |
| `test_multiline_nested_vdom_and_zones` | FortiGate Nested | Multi-VDOM, multi-zone block state machine integrity |
| `test_zone_lookup_exact_and_fallback` | FortiGate Lookup | Exact VDOM match, root fallback, case-insensitivity |
| `test_end_to_end_inline_zone_and_interfaces`| End-to-End | Full CSV record output with IP, VDOM, and zone |
| `test_cisco_hostname_and_interfaces` | Cisco IOS/NXOS | Hostname, IP address conversion, and description extraction |

### How to Run the Tests:
```bash
python3 "cisco interface ip extract and use it traceroute/test_cisco_extractor.py"
```
Or via unittest:
```bash
python3 -m unittest "cisco interface ip extract and use it traceroute/test_cisco_extractor.py"
```
