#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import shutil
import datetime
import subprocess

def backup_list_file(list_file):
    """
    Create a timestamped backup of the list file and keep only the last 10 backups.
    """
    if not os.path.exists(list_file):
        return
    
    script_dir = os.path.dirname(os.path.abspath(list_file))
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = "list.txt.%s.bak" % timestamp
    backup_path = os.path.join(script_dir, backup_filename)
    
    try:
        shutil.copy2(list_file, backup_path)
        print("Backup created: %s" % backup_filename)
    except Exception as e:
        print("Error creating backup: %s" % str(e))
        return
        
    # Get all backups in the script directory matching list.txt.*.bak
    backups = []
    for f in os.listdir(script_dir):
        if f.startswith("list.txt.") and f.endswith(".bak"):
            backups.append(os.path.join(script_dir, f))
            
    # Sort alphabetically (since the timestamp format is YYYYMMDD_HHMMSS, this sorts by date ascending)
    backups.sort()
    
    # If there are more than 10 backups, delete the oldest ones
    if len(backups) > 10:
        old_backups = backups[:-10]
        for ob in old_backups:
            try:
                os.remove(ob)
                print("Deleted old backup: %s" % os.path.basename(ob))
            except Exception as e:
                print("Error deleting old backup %s: %s" % (os.path.basename(ob), str(e)))


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    list_file = os.path.join(script_dir, "list.txt")
    finish_file = os.path.join(script_dir, "finish.txt")
    
    # Determine the path of the BBdown app (look in script folder first, default to ./BBdown)
    bbdown_path = os.path.join(script_dir, "BBdown")
    if not os.path.exists(bbdown_path):
        bbdown_path = "./BBdown"
        
    # Check if list.txt exists and is not empty
    if not os.path.exists(list_file):
        print("Error: list.txt not found at %s" % list_file)
        return
        
    # Read the pending list
    with open(list_file, "r") as f:
        lines = [line.strip() for line in f if line.strip()]
        
    if not lines:
        print("list.txt is empty. No videos to download.")
        return
        
    # Perform backup before starting downloads
    backup_list_file(list_file)
    
    remaining_lines = list(lines)
    success_count = 0
    fail_count = 0
    
    for line in lines:
        print("========================================")
        print("Processing: %s" % line)
        print("========================================")
        
        # Call BBdown
        try:
            # Using subprocess.call is compatible with both Python 2 and Python 3
            # Shell=False is safer, so we pass command as list
            ret = subprocess.call([bbdown_path, line])
        except Exception as e:
            print("Error executing %s: %s" % (bbdown_path, str(e)))
            ret = -1
            
        if ret == 0:
            print("Download successful for: %s" % line)
            success_count += 1
            
            # Append successful URL/ID to finish.txt
            try:
                with open(finish_file, "a") as ff:
                    ff.write(line + "\n")
            except Exception as e:
                print("Error writing to finish.txt: %s" % str(e))
                
            # Remove from remaining list
            if line in remaining_lines:
                remaining_lines.remove(line)
                
            # Rewrite list.txt immediately to save progress in real-time
            try:
                with open(list_file, "w") as lf:
                    for rem in remaining_lines:
                        lf.write(rem + "\n")
            except Exception as e:
                print("Error updating list.txt: %s" % str(e))
        else:
            print("Download failed (exit code %d) for: %s" % (ret, line))
            fail_count += 1

    print("========================================")
    print("Download process completed.")
    print("Success: %d, Failed: %d, Remaining in queue: %d" % (success_count, fail_count, len(remaining_lines)))


if __name__ == "__main__":
    main()
