# $language = "python"
# $interface = "1.0"

import os
import sys
import csv
import datetime
import difflib

# Setup dummy crt if running outside of SecureCRT environment
if 'crt' not in globals():
    class Dummy(object):
        pass
    crt = Dummy()

# Constants
HOSTS_CSV = "hosts.csv"
COMMAND_CSV = "command.csv"


def check_or_create_csv():
    """
    Check if the required CSV files exist.
    If not, prompt the user to generate example templates.
    Returns True if files exist, False otherwise.
    """
    # Check hosts.csv
    if not os.path.exists(HOSTS_CSV):
        res = crt.Dialog.MessageBox(
            "File '%s' not found. Would you like to generate an example template?" % HOSTS_CSV,
            "hosts.csv Missing",
            4  # Yes/No buttons
        )
        if res == 6:  # Yes
            try:
                with open(HOSTS_CSV, "wb") as f:
                    writer = csv.writer(f)
                    writer.writerow(["hostname", "ip"])
                    writer.writerow(["router1", "192.168.1.1"])
                    writer.writerow(["switch1", "192.168.1.2"])
                crt.Dialog.MessageBox(
                    "Generated example '%s'. Please edit it and run the script again." % HOSTS_CSV,
                    "Template Created"
                )
            except Exception as e:
                crt.Dialog.MessageBox("Failed to create '%s': %s" % (HOSTS_CSV, str(e)), "Error")
        return False

    # Check command.csv
    if not os.path.exists(COMMAND_CSV):
        res = crt.Dialog.MessageBox(
            "File '%s' not found. Would you like to generate an example template?" % COMMAND_CSV,
            "command.csv Missing",
            4  # Yes/No buttons
        )
        if res == 6:  # Yes
            try:
                with open(COMMAND_CSV, "wb") as f:
                    writer = csv.writer(f)
                    writer.writerow(["command"])
                    writer.writerow(["terminal length 0"])
                    writer.writerow(["show version"])
                    writer.writerow(["show ip interface brief"])
                crt.Dialog.MessageBox(
                    "Generated example '%s'. Please edit it and run the script again." % COMMAND_CSV,
                    "Template Created"
                )
            except Exception as e:
                crt.Dialog.MessageBox("Failed to create '%s': %s" % (COMMAND_CSV, str(e)), "Error")
        return False

    return True


def read_hosts():
    """
    Read hosts from hosts.csv.
    Returns a list of dicts: [{'hostname': name, 'ip': ip}]
    """
    hosts = []
    try:
        with open(HOSTS_CSV, "rb") as f:
            reader = csv.DictReader(f)
            # Normalize headers
            headers = [h.strip().lower() for h in reader.fieldnames] if reader.fieldnames else []
            
            # Find matching headers
            host_header = None
            ip_header = None
            for h in reader.fieldnames:
                h_norm = h.strip().lower()
                if h_norm in ["hostname", "host_name", "host"]:
                    host_header = h
                if h_norm in ["ip", "ip_address", "address"]:
                    ip_header = h

            if not host_header or not ip_header:
                crt.Dialog.MessageBox(
                    "Invalid hosts.csv format. Headers must include 'hostname' and 'ip'.\nFound headers: %s" % str(reader.fieldnames),
                    "CSV Format Error"
                )
                return []

            for row in reader:
                hostname = row.get(host_header, "").strip()
                ip = row.get(ip_header, "").strip()
                if hostname and ip:
                    hosts.append({"hostname": hostname, "ip": ip})
    except Exception as e:
        crt.Dialog.MessageBox("Error reading %s: %s" % (HOSTS_CSV, str(e)), "Error")
    return hosts


def read_commands():
    """
    Read commands from command.csv.
    Returns a list of command strings.
    """
    commands = []
    try:
        with open(COMMAND_CSV, "rb") as f:
            reader = csv.DictReader(f)
            # Find command column
            cmd_header = None
            if reader.fieldnames:
                for h in reader.fieldnames:
                    if h.strip().lower() in ["command", "cmd", "commands"]:
                        cmd_header = h
                        break
            
            if not cmd_header:
                # If no explicit header, use the first column name
                if reader.fieldnames:
                    cmd_header = reader.fieldnames[0]
                else:
                    crt.Dialog.MessageBox("command.csv has no columns or headers.", "CSV Format Error")
                    return []

            for row in reader:
                cmd = row.get(cmd_header, "").strip()
                if cmd:
                    commands.append(cmd)
    except Exception as e:
        crt.Dialog.MessageBox("Error reading %s: %s" % (COMMAND_CSV, str(e)), "Error")
    return commands


def is_valid_command(cmd):
    """
    Check security policy: only allow show and terminal commands.
    """
    cmd_clean = cmd.strip().lower()
    return cmd_clean.startswith("show") or cmd_clean.startswith("terminal")


def detect_prompt(tab):
    """
    Detect the device's prompt by sending a carriage return and waiting for common prompt endings.
    """
    tab.Screen.Synchronous = True
    tab.Screen.Send("\r")
    
    # Wait for common prompt endings: #, >, $, ]
    match_idx = tab.Screen.WaitForStrings(["#", ">", "$", "]"], 5)
    if match_idx > 0:
        row = tab.Screen.CurrentRow
        col = tab.Screen.CurrentColumn
        # Read the prompt line from column 1 up to current cursor position
        prompt = tab.Screen.Get(row, 1, row, col).strip()
        if prompt:
            return prompt
    return "#"  # Default fallback


def connect_and_capture(is_before=True):
    """
    Perform login sequence, ask for log folder path, execute commands and save logs.
    """
    if not check_or_create_csv():
        return

    hosts = read_hosts()
    if not hosts:
        return

    commands = read_commands()
    if not commands:
        return

    # Ask username and password once
    username = crt.Dialog.Prompt("Enter username for all devices:", "Login Credentials", "", False)
    if not username:
        return
    password = crt.Dialog.Prompt("Enter password for all devices:", "Login Credentials", "", True)
    if not password:
        return

    connected_tabs = []
    host_tab_mapping = []

    try:
        for host in hosts:
            hostname = host["hostname"]
            ip = host["ip"]

            # Prompt to confirm connection (MFA warning / pacing)
            confirm_msg = (
                "Ready to connect to '%s' (%s)?\n"
                "Please confirm if you have approved or are ready to confirm on other devices."
                % (hostname, ip)
            )
            res = crt.Dialog.MessageBox(confirm_msg, "Login Confirmation", 1)  # OK/Cancel
            if res != 1:
                crt.Dialog.MessageBox("Skipping remaining devices as requested.", "Operation Interrupted")
                break

            crt.Session.SetStatusText("Connecting to %s (%s)..." % (hostname, ip))
            cmd = "/SSH2 /L %s /PASSWORD %s %s" % (username, password, ip)

            try:
                # Connect in a new tab. Set Wait For Auth = True, Silent Error = True
                tab = crt.Session.ConnectInTab(cmd, True, True)
                if tab.Connected:
                    tab.Screen.Synchronous = True
                    connected_tabs.append(tab)
                    host_tab_mapping.append({"hostname": hostname, "tab": tab})
                    crt.Session.SetStatusText("Connected to %s." % hostname)
                else:
                    crt.Dialog.MessageBox("Failed to connect to '%s' (%s)." % (hostname, ip), "Connection Error")
                    # Prompt whether to continue or abort
                    cont = crt.Dialog.MessageBox(
                        "Failed to connect to '%s'. Do you want to continue connecting to other devices?" % hostname,
                        "Continue?",
                        4  # Yes/No
                    )
                    if cont != 6:  # No
                        break
            except Exception as e:
                crt.Dialog.MessageBox("Error connecting to '%s': %s" % (hostname, str(e)), "Connection Error")
                cont = crt.Dialog.MessageBox(
                    "Error connecting to '%s'. Do you want to continue connecting to other devices?" % hostname,
                    "Continue?",
                    4  # Yes/No
                )
                if cont != 6:
                    break

        if not connected_tabs:
            crt.Dialog.MessageBox("No active device connections. Aborting capture.", "Operation Failed")
            return

        # Prompt for output directory
        default_dir_name = datetime.datetime.now().strftime("%Y_%m_%d_%H%M")
        script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
        default_output_path = os.path.join(script_dir, default_dir_name)

        output_path = crt.Dialog.Prompt(
            "Please specify the folder path where the captured logs should be saved:",
            "Select Output Directory",
            default_output_path
        )

        if not output_path:
            crt.Dialog.MessageBox("No output directory specified. Closing tabs and aborting.", "Cancelled")
            for tab in connected_tabs:
                tab.Close()
            return

        # Create output folder
        if not os.path.exists(output_path):
            try:
                os.makedirs(output_path)
            except Exception as e:
                crt.Dialog.MessageBox("Failed to create directory '%s': %s" % (output_path, str(e)), "Error")
                for tab in connected_tabs:
                    tab.Close()
                return

        # Execute commands and capture logs on each tab
        for mapping in host_tab_mapping:
            hostname = mapping["hostname"]
            tab = mapping["tab"]

            tab.Activate()
            crt.Session.SetStatusText("Capturing logs on %s..." % hostname)

            # Determine prompt
            prompt = detect_prompt(tab)

            # Build log file path
            prefix = "Before" if is_before else "after"
            log_filename = "%s_%s.log" % (prefix, hostname)
            log_filepath = os.path.join(output_path, log_filename)

            # Start SecureCRT native logging
            tab.Session.LogFileName = log_filepath
            tab.Session.Log(True)

            # Execute commands
            for cmd in commands:
                if not is_valid_command(cmd):
                    # Write security skip log inside session (comment)
                    tab.Screen.Send("\r# COMMAND BLOCK: '%s' violates security policy (only show/terminal commands allowed)\r" % cmd)
                    continue

                # Send command
                tab.Screen.Send(cmd + "\r")

                # Wait for prompt while handling pagination
                while True:
                    match_idx = tab.Screen.WaitForStrings([prompt, "--More--", "more", "--- More ---"], 10)
                    if match_idx == 1:
                        # Prompt matched, command finished
                        break
                    elif match_idx in [2, 3, 4]:
                        # Send space to page down
                        tab.Screen.Send(" ")
                    else:
                        # Timeout or error
                        break

            # Turn off logging for this tab
            tab.Session.Log(False)

            # Close tab
            tab.Close()

        crt.Session.SetStatusText("")
        crt.Dialog.MessageBox("Log capture completed successfully.\nLogs saved to: %s" % output_path, "Success")

    finally:
        # Cleanup any remaining opened tabs
        for tab in connected_tabs:
            try:
                if tab.Connected:
                    tab.Close()
            except:
                pass
        crt.Session.SetStatusText("")


def compare_logs():
    """
    Compare before and after logs and generate CSV report outputs.
    """
    hosts = read_hosts()
    if not hosts:
        return

    # Prompt user for Before logs folder
    script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
    before_folder = crt.Dialog.Prompt(
        "Enter the path to the folder containing the 'Before' logs:",
        "Compare Logs - Before Folder",
        script_dir
    )
    if not before_folder:
        return

    # Prompt user for After logs folder (defaults to same folder if combined)
    after_folder = crt.Dialog.Prompt(
        "Enter the path to the folder containing the 'After' logs:",
        "Compare Logs - After Folder",
        before_folder
    )
    if not after_folder:
        return

    # Prompt user where to save comparison CSV reports
    report_output_folder = crt.Dialog.Prompt(
        "Enter the folder path where the comparison CSV files should be saved:",
        "Select Report Output Folder",
        after_folder
    )
    if not report_output_folder:
        return

    if not os.path.exists(report_output_folder):
        try:
            os.makedirs(report_output_folder)
        except Exception as e:
            crt.Dialog.MessageBox("Failed to create report directory '%s': %s" % (report_output_folder, str(e)), "Error")
            return

    all_differences = []
    comparison_summary = []

    for host in hosts:
        hostname = host["hostname"]
        before_log_path = os.path.join(before_folder, "Before_%s.log" % hostname)
        after_log_path = os.path.join(after_folder, "after_%s.log" % hostname)

        if not os.path.exists(before_log_path) or not os.path.exists(after_log_path):
            # Check for lowercase before or capital after just in case
            alt_before = os.path.join(before_folder, "before_%s.log" % hostname)
            alt_after = os.path.join(after_folder, "After_%s.log" % hostname)
            
            if os.path.exists(alt_before):
                before_log_path = alt_before
            if os.path.exists(alt_after):
                after_log_path = alt_after

        # Validate existence
        if not os.path.exists(before_log_path):
            comparison_summary.append("Host %s: Skipping (Missing Before log at %s)" % (hostname, before_log_path))
            continue
        if not os.path.exists(after_log_path):
            comparison_summary.append("Host %s: Skipping (Missing After log at %s)" % (hostname, after_log_path))
            continue

        # Load file contents
        try:
            with open(before_log_path, "r") as bf:
                before_lines = [l.rstrip("\r\n") for l in bf.readlines()]
            with open(after_log_path, "r") as af:
                after_lines = [l.rstrip("\r\n") for l in af.readlines()]
        except Exception as e:
            comparison_summary.append("Host %s: Error reading logs (%s)" % (hostname, str(e)))
            continue

        # Perform line-by-line diff using difflib.ndiff
        diff = list(difflib.ndiff(before_lines, after_lines))
        device_differences = []
        line_before = 0
        line_after = 0

        for line in diff:
            prefix = line[:2]
            content = line[2:]

            if prefix == "  ":
                line_before += 1
                line_after += 1
            elif prefix == "- ":
                line_before += 1
                device_differences.append({
                    "change_type": "REMOVED",
                    "line_before": line_before,
                    "line_after": "",
                    "content_before": content,
                    "content_after": ""
                })
            elif prefix == "+ ":
                line_after += 1
                device_differences.append({
                    "change_type": "ADDED",
                    "line_before": "",
                    "line_after": line_after,
                    "content_before": "",
                    "content_after": content
                })
            elif prefix == "? ":
                # Eye guide line from ndiff, ignore
                pass

        # Write individual device comparison CSV
        ind_csv_filename = "comparison_%s.csv" % hostname
        ind_csv_filepath = os.path.join(report_output_folder, ind_csv_filename)

        try:
            with open(ind_csv_filepath, "wb") as f:
                writer = csv.writer(f)
                writer.writerow(["change_type", "line_before", "line_after", "content_before", "content_after"])
                for row in device_differences:
                    writer.writerow([
                        row["change_type"],
                        row["line_before"],
                        row["line_after"],
                        row["content_before"],
                        row["content_after"]
                    ])
            comparison_summary.append("Host %s: Completed (%d differences found) -> %s" % (hostname, len(device_differences), ind_csv_filename))
        except Exception as e:
            comparison_summary.append("Host %s: Error writing CSV (%s)" % (hostname, str(e)))

        # Append to unified differences list
        for row in device_differences:
            all_differences.append({
                "hostname": hostname,
                "change_type": row["change_type"],
                "line_before": row["line_before"],
                "line_after": row["line_after"],
                "content_before": row["content_before"],
                "content_after": row["content_after"]
            })

    # Write unified devices comparison CSV
    unified_csv_filepath = os.path.join(report_output_folder, "all_devices_comparison.csv")
    try:
        with open(unified_csv_filepath, "wb") as f:
            writer = csv.writer(f)
            writer.writerow(["hostname", "change_type", "line_before", "line_after", "content_before", "content_after"])
            for row in all_differences:
                writer.writerow([
                    row["hostname"],
                    row["change_type"],
                    row["line_before"],
                    row["line_after"],
                    row["content_before"],
                    row["content_after"]
                ])
        comparison_summary.append("\nUnified Report: Generated -> all_devices_comparison.csv")
    except Exception as e:
        comparison_summary.append("\nUnified Report: Error writing CSV (%s)" % str(e))

    # Display final execution summary
    summary_message = "Comparison Process Finished!\n\n" + "\n".join(comparison_summary)
    crt.Dialog.MessageBox(summary_message, "Comparison Report Summary")


def main():
    """
    Main loop implementation of the SecureCRT command menu.
    """
    while True:
        menu_text = (
            "Select an Option:\n\n"
            "1) Capture Before Log\n"
            "2) Capture After Log\n"
            "3) Compare Logs\n"
            "0) Exit\n"
        )
        choice = crt.Dialog.Prompt(menu_text, "SecureCRT Script Menu", "1")
        
        # If user cancels the prompt dialog, choice will be empty
        if choice == "" or choice == "0":
            break
        elif choice == "1":
            connect_and_capture(is_before=True)
        elif choice == "2":
            connect_and_capture(is_before=False)
        elif choice == "3":
            compare_logs()
        else:
            crt.Dialog.MessageBox("Invalid selection: '%s'. Please select 1, 2, 3, or 0." % choice, "Selection Error")


if __name__ == "__main__":
    main()
