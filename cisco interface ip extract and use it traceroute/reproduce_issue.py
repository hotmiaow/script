
import sys
import os
from cisco_extractor import NetworkConfigParser

def test_flat_config():
    content = """
config global config system interface edit "LAG1.333" set interface "outside_zone"
config global config system interface edit "LAG1.334" set interface "inside_zone"
    """
    
    print("Testing content:")
    print(content)
    print("-" * 20)
    
    parser = NetworkConfigParser()
    # We need to simulate the environment or just call the method
    # parse_fortigate_interfaces takes (content, hostname, filename)
    
    interfaces = parser.parse_fortigate_interfaces(content, "TestDevice", "test.conf")
    
    print("\nExtracted Interfaces:")
    for iface in interfaces:
        print(f"Interface: {iface['interface_name']}, Zone: {iface['zone']}, IP: {iface.get('ip_address')}")

if __name__ == "__main__":
    test_flat_config()
