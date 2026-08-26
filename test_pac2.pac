if (
 (shExpMatch(host, "hkf1.aaa.com")) ||
  (shExpMatch(resolved_ip, "10.1.1.*")) ||
   (shExpMatch(host, "*.hkf2.aaa.com")) ||
    (shExpMatch(resolved_ip, "10.1.1.0/24")))
    {
    return "DIRECT";
    }