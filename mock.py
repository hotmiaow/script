import sys
sys.path.append("/home/keith/OneDrive/script/PAC_Check")
from pac_checkv2_92 import extract_domains_from_pac

content = '''if (
 (shExpMatch(host, "hkf1.aaa.com")) ||
  (shExpMatch(resolved_ip, "10.1.1.1")) ||
   (shExpMatch(host, "hkf2.aaa.com")) ||
    (shExpMatch(resolved_ip, "10.1.1.2")))
    {
    return "DIRECT";
    }'''

with open("test_mock.pac", "w") as f:
    f.write(content)

ext = extract_domains_from_pac("test_mock.pac")
print("EXTRACTED:", ext)
