import test_extract

content = """if (
 (shExpMatch(host, "hkf1.aaa.com")) ||
  (shExpMatch(resolved_ip, "10.1.1.1")) ||
   (shExpMatch(host, "hkf2.aaa.com")) ||
    (shExpMatch(resolved_ip, "10.1.1.2")))
    {
    return "DIRECT";
    }"""

with open("test_pac.pac", "w") as f:
    f.write(content)

domains = test_extract.extract_domains_from_pac("test_pac.pac", skip_subnets=False)
print("Domains (subnets=False):", domains)

domains_skip = test_extract.extract_domains_from_pac("test_pac.pac", skip_subnets=True)
print("Domains (subnets=True):", domains_skip)
