# $language = "python"
# $interface = "1.0"

import os
import sys
import csv

# Setup dummy crt if running outside of SecureCRT environment
try:
    crt
except NameError:
    class DummyDialog(object):
        def Prompt(self, message, title, default):
            print("%s: %s" % (title, message))
            return default
        def MessageBox(self, message, title, icon=0):
            print("[%s] %s" % (title, message))
            return 1
    class Dummy(object):
        def __init__(self):
            self.Dialog = DummyDialog()
    crt = Dummy()


def escape_xml(text):
    """
    Escape special XML characters in text.
    """
    if not text:
        return ""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


def main():
    """
    Read a CSV file with region, hostname, and login name columns,
    and output a SecureCRT importable XML file.
    """
    # Prompt for CSV file
    csv_file = crt.Dialog.Prompt(
        "Enter the path to the CSV file containing region, hostname, and login name:",
        "Import CSV to XML",
        "hosts.csv"
    )
    if not csv_file:
        return

    if not os.path.exists(csv_file):
        crt.Dialog.MessageBox("File '%s' not found." % csv_file, "Error")
        return

    # Prompt for output XML file
    default_xml = os.path.splitext(csv_file)[0] + "_sessions.xml"
    xml_file = crt.Dialog.Prompt(
        "Enter the path to save the SecureCRT XML import file:",
        "Export XML",
        default_xml
    )
    if not xml_file:
        return

    try:
        # Read CSV file (handling Python 2/3 differences)
        if sys.version_info[0] >= 3:
            with open(csv_file, "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
        else:
            with open(csv_file, "rb") as f:
                reader = csv.reader(f)
                rows = list(reader)
            
        if not rows:
            crt.Dialog.MessageBox("CSV file is empty.", "Error")
            return

        headers = [h.strip().lower() for h in rows[0]]
        
        # Find column indices
        region_idx = -1
        host_idx = -1
        login_idx = -1
        
        for i, h in enumerate(headers):
            if h in ["region", "folder", "group", "location", "zone", "area"]:
                region_idx = i
            elif h in ["hostname", "host", "ip", "address", "ip_address", "host_name"]:
                host_idx = i
            elif h in ["login name", "loginname", "login_name", "username", "user", "login"]:
                login_idx = i

        if host_idx == -1 or login_idx == -1 or region_idx == -1:
            missing = []
            if region_idx == -1: missing.append("region")
            if host_idx == -1: missing.append("hostname")
            if login_idx == -1: missing.append("login name")
            
            crt.Dialog.MessageBox(
                "Could not auto-detect columns: %s.\nHeaders found: %s\nPlease ensure CSV contains headers matching these fields." % (", ".join(missing), str(rows[0])),
                "Column Mapping Error"
            )
            return

        # Group hosts by region
        regions = {}
        for row in rows[1:]:
            if not row or len(row) <= max(region_idx, host_idx, login_idx):
                continue
            region = row[region_idx].strip()
            hostname = row[host_idx].strip()
            login = row[login_idx].strip()
            
            if not hostname:
                continue
            if not region:
                region = "Default"
                
            if region not in regions:
                regions[region] = []
            regions[region].append((hostname, login))

        # Construct the XML settings backup/import format
        xml_lines = []
        xml_lines.append('<?xml version="1.0" encoding="UTF-8"?>')
        xml_lines.append('<VanDyke version="1.0">')
        xml_lines.append('\t<key name="Sessions">')
        
        session_count = 0
        for region, hosts_list in sorted(regions.items()):
            xml_lines.append('\t\t<key name="%s">' % escape_xml(region))
            for hostname, login in hosts_list:
                xml_lines.append('\t\t\t<key name="%s">' % escape_xml(hostname))
                xml_lines.append('\t\t\t\t<dword name="Is Session">1</dword>')
                xml_lines.append('\t\t\t\t<string name="Protocol Name">SSH2</string>')
                xml_lines.append('\t\t\t\t<string name="Hostname">%s</string>' % escape_xml(hostname))
                xml_lines.append('\t\t\t\t<string name="Username">%s</string>' % escape_xml(login))
                xml_lines.append('\t\t\t</key>')
                session_count += 1
            xml_lines.append('\t\t</key>')
            
        xml_lines.append('\t</key>')
        xml_lines.append('</VanDyke>')
        
        xml_content = "\r\n".join(xml_lines)
        if sys.version_info[0] >= 3:
            xml_data = xml_content.encode("utf-8")
        else:
            xml_data = xml_content
            
        with open(xml_file, "wb") as f:
            f.write(xml_data)
            
        crt.Dialog.MessageBox(
            "Successfully generated SecureCRT XML session configuration!\n\n"
            "Total sessions: %d\n"
            "Saved to: %s\n\n"
            "To import this into SecureCRT, go to Tools -> Import Settings..." % (session_count, xml_file),
            "Export Complete"
        )
        
    except Exception as e:
        crt.Dialog.MessageBox("An error occurred during CSV parsing/XML generation:\n%s" % str(e), "Error")


if __name__ == "__main__":
    main()
