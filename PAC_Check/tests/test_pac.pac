function FindProxyForURL(url, host) {

    // --- Scenario 1: Same Proxy for Wildcard & Specific Domain (Should PASS: No warning) ---
    if (shExpMatch(host, "*.apple.com")) {
        return "PROXY proxy.apple:8080";
    }
    if (dnsDomainIs(host, "mail.apple.com")) {
        return "PROXY proxy.apple:8080";
    }

    // --- Scenario 2: Different Proxy for Wildcard & Specific Domain (Should FAIL: Warning) ---
    if (shExpMatch(host, "*.google.com")) {
        return "DIRECT";
    }
    if (dnsDomainIs(host, "mail.google.com")) {
        return "PROXY proxy.google:8080";
    }

    // --- Scenario 3: Same Proxy for Large & Small Subnet (Should PASS: No warning) ---
    if (isInNet(host, "10.0.0.0", "255.0.0.0")) {
        return "DIRECT";
    }
    if (isInNet(host, "10.1.2.0", "255.255.255.0")) return "DIRECT";

    // --- Scenario 4: Different Proxy for Large & Small Subnet (Should FAIL: Warning) ---
    if (isInNet(host, "192.168.0.0", "255.255.0.0")) {
        return "PROXY a";
    }
    if (isInNet(host, "192.168.1.0", "255.255.255.0")) {
        return "PROXY b";
    }

    // --- Scenario 5: Multi-line nested returns resolving differently (Should FAIL: Warning) ---
    if (shExpMatch(host, "*.microsoft.com")) {
        // some comment
        return "PROXY micro:80";
    }
    if (dnsDomainIs(host, "update.microsoft.com")) {
        return "DIRECT";
    }

    return "DIRECT";
}
