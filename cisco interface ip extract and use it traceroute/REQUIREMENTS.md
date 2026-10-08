# Requirements & Test Specifications: Cisco & FortiGate Interface Information Extractor

## 1. Overview
The **Cisco & FortiGate Interface Information Extractor** (`InterfaceExtractor.py`) parses network device configurations (Cisco IOS, IOS-XE, NX-OS, and Fortinet FortiOS) to extract:
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
3. **Cross-VDOM Match**: Checks across all VDOMs for that device if the interface is mapped to a zone in another VDOM (e.g. `AWS::LAG1.1111 -> AAA-Zone`).
4. **Unknown VDOM Fallback**: `f"unknown::{interface_name}"`
5. **Case-Insensitive Match**: Matches case variations (e.g. `lag1.1111` vs `LAG1.1111`).
6. **Default**: Returns `"No Zone"` if no mapping exists.

---

### Requirement 4: Cross-File FortiGate Interface & Zone Correlation
When configuration for a firewall device is split across multiple files (for example, `hk1-aaa_root.set` containing interface IP configurations and `hk1-aaa_AWS.set` containing zone configurations for the `AWS` VDOM):

1. **Filename Convention Parsing**:
   - Files matching `<hostname>_<vdom>.<ext>` (e.g. `hk1-aaa_AWS.set`, `hk1-aaa_root.set`) are automatically parsed into:
     - Device Hostname: `hk1-aaa`
     - Default VDOM Context: `AWS` or `root`
   - Generic terms like `firewall`, `router`, `switch` are preserved as part of the hostname rather than treated as VDOMs.
2. **Batch Pre-Scanning (`process_directory`)**:
   - Pass 1: Scans all FortiGate files to construct device-wide zone tables (`device_zones[hostname]`).
   - Pass 2: Parses all files with full cross-file zone knowledge available immediately.
3. **Order-Independent Retroactive Resolution (`parse_file`)**:
   - If `hk1-aaa_root.set` is parsed before `hk1-aaa_AWS.set`, previously collected interface entries are automatically updated when the zone file is processed.
   - If `hk1-aaa_AWS.set` is parsed before `hk1-aaa_root.set`, the zone information is already in `device_zones[hostname]` and mapped on the fly.
4. **Interface Deduplication**:
   - Merges identical interfaces across files while retaining the richest zone and description data.

---

## 3. Automated Test Suite

A dedicated regression test suite is located at:
`cisco interface ip extract and use it traceroute/test_cisco_extractor.py`

### Test Cases Included (12 Tests):
| Test Method | Category | Verified Behavior |
| :--- | :--- | :--- |
| `test_inline_vdom_zone_unquoted_interface` | FortiGate Inline | Extracts `App::VL1.1234 -> AAA-Zone` from single-line command |
| `test_inline_vdom_zone_quoted_interface` | FortiGate Inline | Extracts `App::LAG1.1111 -> AAA-Zone` from single-line command |
| `test_inline_vdom_multiple_interfaces` | FortiGate Inline | Extracts multiple interfaces from a single `set interface` |
| `test_inline_global_zone` | FortiGate Inline | Extracts global zone mappings to `root::<iface>` |
| `test_multiline_nested_vdom_and_zones` | FortiGate Nested | Multi-VDOM, multi-zone block state machine integrity |
| `test_zone_lookup_exact_and_fallback` | FortiGate Lookup | Exact VDOM match, root fallback, case-insensitivity |
| `test_end_to_end_inline_zone_and_interfaces` | End-to-End | Full CSV record output with IP, VDOM, and zone |
| `test_filename_parsing` | Cross-File | Extracts device and VDOM from filenames like `hk1-aaa_AWS.set` |
| `test_cross_file_directory_processing` | Cross-File | Directory pre-scan correlates `hk1-aaa_root.set` IP and `hk1-aaa_AWS.set` Zone |
| `test_cross_file_root_before_aws` | Cross-File | Retroactive zone resolution when root file parsed before AWS zone file |
| `test_cross_file_aws_before_root` | Cross-File | Direct zone resolution when AWS zone file parsed before root file |
| `test_cisco_hostname_and_interfaces` | Cisco IOS/NXOS | Hostname, IP address conversion, and description extraction |

### How to Run the Tests:
```bash
python3 "cisco interface ip extract and use it traceroute/test_cisco_extractor.py"
```
Or via unittest:
```bash
python3 -m unittest "cisco interface ip extract and use it traceroute/test_cisco_extractor.py"
```

---

## 4. Requirements & Specifications: TraceINT Subnet-Based Inbound & Outbound Interface Traceroute Mapping (`TraceINT.py`)

### Overview
In traceroute results, previous versions only displayed a single interface column matching whichever IP responded to the probe (typically either the ingress or egress interface). 

The enhanced engine (`TraceINT.py` / `TraceINTv3.11.py`) resolves and displays **both Inbound and Outbound interfaces** for each hop across the network path, connecting consecutive devices into an end-to-end full path.

### Core Logic & Rules
1. **Subnet-Based Interface Correlation**:
   - Outbound interface on Device $N$ and Inbound interface on Device $N+1$ share the same point-to-point / transit subnet (e.g. `/30`, `/31`, `/29`, `/24`).
   - The engine searches all interfaces of Device $N$ and Device $N+1$ to find the pair $(if_{out}, if_{in})$ residing in the same IP network.
2. **Hop IP Ambiguity Resolution**:
   - Whether a hop IP in traceroute responds with its ingress interface or egress interface, the opposite interface is automatically disambiguated by matching against adjacent hop links.
3. **Target & Source Subnet Containment**:
   - The first hop's Inbound interface is resolved by testing containment of the source IP.
   - The last hop's Outbound interface is resolved by testing containment of the destination target IP.
4. **Intermediate Timeout Resilience**:
   - If a hop times out (`* * *`), adjacent devices are still evaluated for direct or transit link relationships.
5. **Security Zone Transition Visibility**:
   - If the Inbound interface and Outbound interface reside in different security zones (e.g. `Trust` and `Untrust`), the zone is clearly presented as `Trust -> Untrust`.
6. **Live Lookahead Streaming**:
   - During live traceroute execution, a 1-hop lookahead buffer resolves and displays both interfaces in real time as probes complete.
7. **Full Path Flow Diagram**:
   - At the completion of the trace, a visual flow diagram details every link, interface pair, and subnet along the end-to-end trajectory.
8. **2-Line Hop Presentation (Individual Inbound & Outbound Descriptions)**:
   - Each hop row is rendered across **2 distinct lines**:
     - **Line 1 (IN)**: Displays `Dir=IN`, inbound interface name, inbound security zone, inbound VRF, and the inbound interface's description/info.
     - **Line 2 (OUT)**: Displays `Dir=OUT`, outbound interface name, next-hop device/interface link, outbound security zone, outbound VRF, and the outbound interface's description/info.

### Test Suite (`test_trace_int.py`)
| Test Method | Description |
| :--- | :--- |
| `test_parse_ip_and_network` | Validates CIDR, space-separated masks, secondary IPs, plain IPs, and unassigned/dynamic strings |
| `test_find_matching_subnet_interfaces` | Verifies point-to-point subnet matching between devices |
| `test_find_interface_by_ip` | Verifies IP and subnet containment search on device interfaces |
| `test_full_path_resolution` | Verifies end-to-end resolution of Inbound, Outbound, Next Hop, and Zone transitions |
| `test_resolution_when_hop_ip_is_ingress_interface` | Verifies resolution when hop IP responds as ingress rather than egress |
| `test_resolution_with_timeout_hop` | Verifies stability and resolution when intermediate hops time out |
| `test_two_line_hop_descriptions` | Verifies individual inbound and outbound interface description extraction per hop |
| `test_format_path_flow` | Verifies formatting of the visual link flow diagram |
| `test_streaming_output_display` | Verifies 2-line streaming output headers, columns, and full path summary |

Run via:
```bash
python3 -m unittest "cisco interface ip extract and use it traceroute/test_trace_int.py" -v
```
