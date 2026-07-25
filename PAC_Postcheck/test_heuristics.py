import re

def get_return_val(lines, start_idx):
    for i in range(start_idx, len(lines)):
        line = lines[i]
        # check return
        m = re.search(r'return\s+["\']([^"\']+)["\']', line)
        if m:
            return m.group(1).strip()
        # if another if comes up after the starting line, stop (unless it's same line)
        if i > start_idx and re.search(r'\bif\b', line):
            break
    return None

pac = """
if (shExpMatch(host, "*.example.com")) return "PROXY; DIRECT";
    
if (dnsDomainIs(host, "mail.example.com")) {
    return "DIRECT";
}
"""
lines = pac.split("\n")
print("1:", get_return_val(lines, 1))
print("2:", get_return_val(lines, 3))
