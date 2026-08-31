import pacparser
import sys

pac_code = """
function FindProxyForURL(url, host) {
    if (ShEXPMatch(host, "hkf1.aaa.com")) {
        return "DIRECT";
    }
    return "PROXY proxy:8080";
}
"""

with open("test.pac", "w") as f:
    f.write(pac_code)

try:
    pacparser.init()
    pacparser.parse_pac_file("test.pac")
    ans = pacparser.find_proxy("http://hkf1.aaa.com", "hkf1.aaa.com")
    print("Proxy:", ans)
    pacparser.cleanup()
except Exception as e:
    print("ERROR:", e)
