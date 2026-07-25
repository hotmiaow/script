
import sys
import os

# Add the script to path so we can import it
sys.path.append(os.getcwd())

# Import the class. We might need to handle the filename if it's not a valid module name
# but since I renamed it to cisco_extractor.py, it should be fine.
try:
    from cisco_extractor import NetworkConfigParser
except ImportError:
    # If the rename failed or wasn't done, we might need to load by path
    import importlib.util
    spec = importlib.util.spec_from_file_location("cisco_extractor", "./Cisco Interface Information Extractor1.10.py")
    if spec is None:
         spec = importlib.util.spec_from_file_location("cisco_extractor", "./cisco_extractor.py")
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    NetworkConfigParser = module.NetworkConfigParser

def test_flat_zones():
    content = """
config global config system interface edit "LAG1.333" set interface "outside_zone"
config global config system interface edit "LAG1.334" set interface "inside_zone"

# Let's add an IP configuration in a standard block to see if it picks up the zone from the flat config
config system interface
    edit "LAG1.333"
        set vdom "root"
        set ip 10.1.1.1 255.255.255.0
    next
    edit "LAG1.334"
        set vdom "root"
        set ip 10.2.2.1 255.255.255.0
    next
end
    """
    
    print("Testing content with mixed flat zone config and standard interface block:")
    print("-" * 20)
    
    parser = NetworkConfigParser()
    
    # We expect LAG1.333 -> outside_zone, LAG1.334 -> inside_zone
    interfaces = parser.parse_fortigate_interfaces(content, "TestDevice", "test.conf")
    
    print("\nExtracted Interfaces:")
    found_zones = {}
    for iface in interfaces:
        name = iface['interface_name']
        zone = iface['zone']
        ip = iface['ip_address']
        print(f"Interface: {name}, Zone: {zone}, IP: {ip}")
        found_zones[name] = zone

    # Verification
    if found_zones.get("LAG1.333") == "outside_zone" and found_zones.get("LAG1.334") == "inside_zone":
        print("\nSUCCESS: Zones correctly extracted from flat config!")
    else:
        print("\nFAILURE: Zones NOT extracted correctly.")
        print(f"Expected: LAG1.333: outside_zone, LAG1.334: inside_zone")
        print(f"Got:      LAG1.333: {found_zones.get('LAG1.333')}, LAG1.334: {found_zones.get('LAG1.334')}")

if __name__ == "__main__":
    test_flat_zones()
