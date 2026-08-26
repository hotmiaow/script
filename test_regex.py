import re

content = """if (
 (ShEXPMatch(host, "hkf1.aaa.com")) ||
  (ShEXPMatch(resloved_ip, "10.1.1.1")) ||
   (ShEXPMatch(host, "hkf2.aaa.com")) ||
    (ShEXPMatch(resloved_ip, "10.1.1.2")))
    {
    return "DIRECT"
    }"""

pattern_quoted = re.compile(r"""['"]([a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+)['"]""")
pattern_dnsDomainIs = re.compile(r"""dnsDomainIs\s*\(\s*[^,]+,\s*['"]\.?([a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+)['"]\s*\)""", re.IGNORECASE)
pattern_shExpMatch = re.compile(r"""shExpMatch\s*\([^,]+,\s*['"][*]?\.?([a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+)[*]?['"]\s*\)""", re.IGNORECASE)

print("Q:", pattern_quoted.findall(content))
print("D:", pattern_dnsDomainIs.findall(content))
print("S:", pattern_shExpMatch.findall(content))
