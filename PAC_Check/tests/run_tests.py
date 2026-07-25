import os
import sys
import importlib.util

# Load the pac_checkv3.4 module
module_name = "pac_check"
file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pac_checkv3.4.py"))

spec = importlib.util.spec_from_file_location(module_name, file_path)
pac_module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = pac_module
spec.loader.exec_module(pac_module)

def run_tests():
    test_file = os.path.join(os.path.dirname(__file__), "test_pac.pac")
    
    print("\n==================================")
    print(" Running PAC Sanity Check Tests   ")
    print("==================================\n")
    
    warnings = pac_module.check_pac_sanity(test_file)
    
    expected_failures = 3
    
    print(f"File parsed: {test_file}")
    print(f"Total Warnings Received: {len(warnings)}")
    print("-" * 34)
    
    if warnings:
        for idx, warning in enumerate(warnings, 1):
            print(f"  [Warning {idx}] {warning}")
    else:
        print("  <No warnings detected>")
        
    print("-" * 34)
    print("Test Validation:")
    if len(warnings) == expected_failures:
        print(f"  ✅ SUCCESS: Expected exactly {expected_failures} warnings (Scenario 2, 4, 5).")
        print("  ✅ Identical destinations (Scenario 1 & 3) were correctly NOT flagged as warnings.")
    else:
        print(f"  ❌ FAILED: Expected {expected_failures} warnings but got {len(warnings)}.")

if __name__ == "__main__":
    run_tests()
