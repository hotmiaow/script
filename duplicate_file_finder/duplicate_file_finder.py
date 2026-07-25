import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import re
import subprocess
import sys
from pathlib import Path
from collections import defaultdict
import threading

class MP4DuplicateFinder:
    def __init__(self, root):
        self.root = root
        self.root.title("MP4 Duplicate File Finder")
        self.root.geometry("1000x700")
        
        # Variables
        self.scan_paths = []
        self.duplicate_groups = {}
        
        self.setup_gui()
        
        # Add current directory by default
        current_dir = os.getcwd()
        self.scan_paths.append(current_dir)
        self.update_paths_display()
    
    def setup_gui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        # Directory selection section
        ttk.Label(main_frame, text="Scan Directories:", font=("Arial", 12, "bold")).grid(
            row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 10)
        )
        
        # Paths listbox with scrollbar
        paths_frame = ttk.Frame(main_frame)
        paths_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        paths_frame.columnconfigure(0, weight=1)
        paths_frame.rowconfigure(0, weight=1)
        
        self.paths_listbox = tk.Listbox(paths_frame, height=4)
        self.paths_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        paths_scrollbar = ttk.Scrollbar(paths_frame, orient=tk.VERTICAL, command=self.paths_listbox.yview)
        paths_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.paths_listbox.configure(yscrollcommand=paths_scrollbar.set)
        
        # Buttons for directory management
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        
        ttk.Button(button_frame, text="Add Directory", command=self.add_directory).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Remove Selected", command=self.remove_directory).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Clear All", command=self.clear_directories).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Scan for Duplicates", command=self.scan_duplicates, 
                  style="Accent.TButton").pack(side=tk.LEFT)
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Results section
        ttk.Label(main_frame, text="Potential Duplicate Groups:", font=("Arial", 12, "bold")).grid(
            row=4, column=0, columnspan=3, sticky=tk.W, pady=(10, 5)
        )
        
        # Results treeview with scrollbars
        results_frame = ttk.Frame(main_frame)
        results_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        # Configure treeview
        columns = ('Pattern', 'Files', 'Size', 'Path')
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show='tree headings', height=15)
        
        # Configure column headings and widths
        self.results_tree.heading('#0', text='Group')
        self.results_tree.heading('Pattern', text='Pattern')
        self.results_tree.heading('Files', text='File Count')
        self.results_tree.heading('Size', text='Size (MB)')
        self.results_tree.heading('Path', text='Full Path')
        
        self.results_tree.column('#0', width=100, minwidth=50)
        self.results_tree.column('Pattern', width=150, minwidth=100)
        self.results_tree.column('Files', width=80, minwidth=50)
        self.results_tree.column('Size', width=100, minwidth=80)
        self.results_tree.column('Path', width=400, minwidth=200)
        
        self.results_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbars for treeview
        v_scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        v_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.results_tree.configure(yscrollcommand=v_scrollbar.set)
        
        h_scrollbar = ttk.Scrollbar(results_frame, orient=tk.HORIZONTAL, command=self.results_tree.xview)
        h_scrollbar.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.results_tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Bind double-click to open file
        self.results_tree.bind('<Double-1>', self.open_file)
        
        # Action buttons frame
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=(10, 5))
        
        ttk.Button(action_frame, text="Open Selected File", command=self.open_selected_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(action_frame, text="Open File Folder", command=self.open_file_folder).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(action_frame, text="Move Selected to Delete Folder", command=self.move_to_delete, 
                  style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(action_frame, text="Move All in Group to Delete Folder", command=self.move_group_to_delete).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(action_frame, text="Select Smaller Files", command=self.select_smaller_files).pack(side=tk.LEFT)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready - Add directories and click 'Scan for Duplicates'")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
    
    def update_paths_display(self):
        """Update the paths listbox display"""
        self.paths_listbox.delete(0, tk.END)
        for path in self.scan_paths:
            self.paths_listbox.insert(tk.END, path)
    
    def add_directory(self):
        """Add a directory to scan"""
        directory = filedialog.askdirectory(title="Select Directory to Scan")
        if directory and directory not in self.scan_paths:
            self.scan_paths.append(directory)
            self.update_paths_display()
            self.status_var.set(f"Added directory: {directory}")
    
    def remove_directory(self):
        """Remove selected directory from scan list"""
        selection = self.paths_listbox.curselection()
        if selection:
            index = selection[0]
            removed_path = self.scan_paths.pop(index)
            self.update_paths_display()
            self.status_var.set(f"Removed directory: {removed_path}")
    
    def clear_directories(self):
        """Clear all directories from scan list"""
        self.scan_paths.clear()
        self.update_paths_display()
        self.status_var.set("Cleared all directories")
    
    def extract_pattern(self, filename):
        """Extract potential identifying patterns from filename"""
        # Remove file extension
        name = os.path.splitext(filename)[0]
        
        # Common patterns to look for
        patterns = []
        
        # Pattern 1: Complete Letter-Number combinations (like AAA-212, PZCC-343)
        # This treats the entire combination as one pattern
        pattern1 = re.findall(r'[A-Z]{2,4}-\d{2,4}', name.upper())
        patterns.extend(pattern1)
        
        # Pattern 2: Word-Number combinations (like Movie123, Series456)
        pattern2 = re.findall(r'[A-Z][a-z]+\d{2,4}', name)
        patterns.extend(pattern2)
        
        # Pattern 3: Standalone number sequences that are likely unique identifiers
        # Only include numbers that are not part of letter-number combinations
        # and are likely to be unique (4+ digits or 3 digits with specific context)
        temp_name = name.upper()
        # Remove already found letter-number patterns to avoid double counting
        for p in pattern1:
            temp_name = temp_name.replace(p, '')
        
        # Find standalone number sequences
        pattern3 = re.findall(r'\b\d{4,8}\b', temp_name)
        patterns.extend(pattern3)
        
        # Pattern 4: Three digit numbers only if they appear to be series/episode numbers
        # Look for patterns like "001", "123" but be more selective
        pattern4 = re.findall(r'\b(?:0\d{2}|\d{3})\b', temp_name)
        # Only add 3-digit numbers if they're likely identifiers (not years, resolutions, etc.)
        for num in pattern4:
            # Skip common non-identifier numbers
            if not (num.startswith('19') or num.startswith('20') or  # years
                   num in ['720', '480', '360', '240', '144'] or     # resolutions
                   num in ['100', '200', '300', '400', '500']):      # common round numbers
                patterns.append(num)
        
        # Return unique patterns
        return list(set(patterns))
    
    def find_mp4_files(self, directory):
        """Recursively find all MP4 files in directory and subdirectories"""
        mp4_files = []
        try:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith('.mp4'):
                        full_path = os.path.join(root, file)
                        mp4_files.append(full_path)
        except Exception as e:
            print(f"Error scanning {directory}: {e}")
        return mp4_files
    
    def get_file_size_mb(self, filepath):
        """Get file size in MB"""
        try:
            size_bytes = os.path.getsize(filepath)
            return round(size_bytes / (1024 * 1024), 2)
        except:
            return 0
    
    def scan_duplicates_thread(self):
        """Thread function to scan for duplicates"""
        try:
            if not self.scan_paths:
                self.status_var.set("No directories to scan")
                self.progress.stop()
                return
            
            # Find all MP4 files
            all_files = []
            for path in self.scan_paths:
                if os.path.exists(path):
                    files = self.find_mp4_files(path)
                    all_files.extend(files)
                    self.status_var.set(f"Scanning {path}...")
                else:
                    self.status_var.set(f"Warning: Path does not exist: {path}")
            
            if not all_files:
                self.status_var.set("No MP4 files found in selected directories")
                self.progress.stop()
                return
            
            self.status_var.set(f"Found {len(all_files)} MP4 files. Analyzing patterns...")
            
            # Group files by patterns
            pattern_groups = defaultdict(list)
            
            for file_path in all_files:
                filename = os.path.basename(file_path)
                patterns = self.extract_pattern(filename)
                
                for pattern in patterns:
                    pattern_groups[pattern].append(file_path)
            
            # Filter groups with more than one file (potential duplicates)
            self.duplicate_groups = {
                pattern: files for pattern, files in pattern_groups.items() 
                if len(files) > 1
            }
            
            # Update GUI in main thread
            self.root.after(0, self.update_results)
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Error during scan: {e}"))
        finally:
            self.root.after(0, lambda: self.progress.stop())
    
    def scan_duplicates(self):
        """Start scanning for duplicates in a separate thread"""
        # Clear previous results
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        self.progress.start()
        self.status_var.set("Scanning for duplicates...")
        
        # Start scanning in separate thread
        thread = threading.Thread(target=self.scan_duplicates_thread)
        thread.daemon = True
        thread.start()
    
    def update_results(self):
        """Update the results treeview"""
        # Clear existing items
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        if not self.duplicate_groups:
            self.status_var.set("No potential duplicates found")
            return
        
        group_num = 1
        total_duplicates = 0
        
        for pattern, files in self.duplicate_groups.items():
            # Create parent node for the group
            group_id = self.results_tree.insert('', 'end', text=f'Group {group_num}', 
                                              values=(pattern, len(files), '', ''))
            
            # Add child nodes for each file
            for file_path in files:
                filename = os.path.basename(file_path)
                size_mb = self.get_file_size_mb(file_path)
                
                self.results_tree.insert(group_id, 'end', text=filename,
                                       values=('', '', f'{size_mb}', file_path))
            
            total_duplicates += len(files)
            group_num += 1
        
        self.status_var.set(f"Found {len(self.duplicate_groups)} potential duplicate groups "
                           f"containing {total_duplicates} files")
        
        # Expand all groups
        for item in self.results_tree.get_children():
            self.results_tree.item(item, open=True)
    
    def open_file(self, event):
        """Open the selected file or folder"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        values = self.results_tree.item(item, 'values')
        
        # Check if it's a file (has a path in the last column)
        if len(values) > 3 and values[3]:
            file_path = values[3]
            self.open_file_with_default_app(file_path)
    
    def open_selected_file(self):
        """Open the currently selected file"""
        selection = self.results_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a file to open")
            return
        
        item = selection[0]
        values = self.results_tree.item(item, 'values')
        
        # Check if it's a file (has a path in the last column)
        if len(values) > 3 and values[3]:
            file_path = values[3]
            self.open_file_with_default_app(file_path)
        else:
            messagebox.showwarning("Invalid Selection", "Please select a file, not a group header")
    
    def open_file_folder(self):
        """Open the folder containing the selected file"""
        selection = self.results_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a file to open its folder")
            return
        
        item = selection[0]
        values = self.results_tree.item(item, 'values')
        
        # Check if it's a file (has a path in the last column)
        if len(values) > 3 and values[3]:
            file_path = values[3]
            if os.path.exists(file_path):
                folder_path = os.path.dirname(file_path)
                try:
                    # Open folder with file manager
                    if sys.platform == "win32":
                        # Windows - open folder and select the file
                        subprocess.run(['explorer', '/select,', file_path])
                    elif sys.platform == "darwin":  # macOS
                        # macOS - reveal file in Finder
                        subprocess.call(["open", "-R", file_path])
                    else:  # Linux
                        # Linux - open folder
                        subprocess.call(["xdg-open", folder_path])
                    self.status_var.set(f"Opened folder: {folder_path}")
                except Exception as e:
                    messagebox.showerror("Error", f"Could not open folder: {e}")
            else:
                messagebox.showerror("Error", "File not found")
        else:
            messagebox.showwarning("Invalid Selection", "Please select a file, not a group header")
    
    def select_smaller_files(self):
        """Auto-select the smaller file in each duplicate group"""
        selected_count = 0
        
        # Clear current selection
        self.results_tree.selection_set([])
        
        # Go through each group
        for group_item in self.results_tree.get_children():
            children = self.results_tree.get_children(group_item)
            if len(children) < 2:
                continue
            
            # Find the smallest file in this group
            smallest_item = None
            smallest_size = float('inf')
            
            for child in children:
                child_values = self.results_tree.item(child, 'values')
                if len(child_values) > 2 and child_values[2]:
                    try:
                        # Get size from the Size column (index 2)
                        size_str = child_values[2]
                        if size_str and size_str != '':
                            size = float(size_str)
                            if size < smallest_size:
                                smallest_size = size
                                smallest_item = child
                    except (ValueError, TypeError):
                        continue
            
            # Select the smallest file (add to current selection)
            if smallest_item:
                current_selection = list(self.results_tree.selection())
                current_selection.append(smallest_item)
                self.results_tree.selection_set(current_selection)
                selected_count += 1
        
        if selected_count > 0:
            self.status_var.set(f"Selected {selected_count} smaller files from duplicate groups")
        else:
            self.status_var.set("No duplicate groups found or unable to determine file sizes")
        """Open file with default application"""
        if os.path.exists(file_path):
            try:
                # Open file with default application
                if sys.platform == "win32":
                    os.startfile(file_path)
                elif sys.platform == "darwin":  # macOS
                    subprocess.call(["open", file_path])
                else:  # Linux
                    subprocess.call(["xdg-open", file_path])
                self.status_var.set(f"Opened: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not open file: {e}")
        else:
            messagebox.showerror("Error", "File not found")
    
    def move_to_delete(self):
        """Move selected file to pending_to_delete folder"""
        selection = self.results_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a file to move")
            return
        
        item = selection[0]
        values = self.results_tree.item(item, 'values')
        
        # Check if it's a file (has a path in the last column)
        if not (len(values) > 3 and values[3]):
            messagebox.showwarning("Invalid Selection", "Please select a file, not a group header")
            return
        
        file_path = values[3]
        self.move_file_to_delete_folder(file_path, item)
    
    def move_group_to_delete(self):
        """Move all files in the selected group to pending_to_delete folder"""
        selection = self.results_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a group or file")
            return
        
        item = selection[0]
        values = self.results_tree.item(item, 'values')
        
        # If it's a file, get its parent group
        if len(values) > 3 and values[3]:
            # It's a file, get the parent group
            parent = self.results_tree.parent(item)
            if parent:
                group_item = parent
            else:
                messagebox.showwarning("Error", "Could not find parent group")
                return
        else:
            # It's a group header
            group_item = item
        
        # Get all children (files) in the group
        children = self.results_tree.get_children(group_item)
        if not children:
            messagebox.showwarning("No Files", "No files found in the selected group")
            return
        
        # Ask for confirmation
        group_text = self.results_tree.item(group_item, 'text')
        pattern = self.results_tree.item(group_item, 'values')[0]
        
        confirm = messagebox.askyesno("Confirm Move", 
                                     f"Move all {len(children)} files from {group_text} (pattern: {pattern}) to delete folder?")
        if not confirm:
            return
        
        moved_count = 0
        for child in children:
            child_values = self.results_tree.item(child, 'values')
            if len(child_values) > 3 and child_values[3]:
                file_path = child_values[3]
                if self.move_file_to_delete_folder(file_path, child):
                    moved_count += 1
        
        if moved_count > 0:
            self.status_var.set(f"Moved {moved_count} files from group to delete folder")
        
    def move_file_to_delete_folder(self, file_path, tree_item):
        """Move a single file to pending_to_delete folder and update the tree"""
        if not os.path.exists(file_path):
            messagebox.showerror("Error", "File not found")
            return False
        
        try:
            # Create pending_to_delete folder in the same directory as the file
            file_dir = os.path.dirname(file_path)
            delete_folder = os.path.join(file_dir, "pending_to_delete")
            
            # Create the folder if it doesn't exist
            os.makedirs(delete_folder, exist_ok=True)
            
            # Get filename and create destination path
            filename = os.path.basename(file_path)
            dest_path = os.path.join(delete_folder, filename)
            
            # Handle duplicate filenames in delete folder
            counter = 1
            original_dest = dest_path
            while os.path.exists(dest_path):
                name, ext = os.path.splitext(original_dest)
                dest_path = f"{name}_{counter}{ext}"
                counter += 1
            
            # Move the file
            import shutil
            shutil.move(file_path, dest_path)
            
            # Update the tree item to show it's been moved
            current_text = self.results_tree.item(tree_item, 'text')
            new_text = f"[MOVED] {current_text}"
            self.results_tree.item(tree_item, text=new_text)
            
            # Update the path to show new location
            current_values = list(self.results_tree.item(tree_item, 'values'))
            current_values[3] = dest_path
            self.results_tree.item(tree_item, values=current_values)
            
            self.status_var.set(f"Moved {filename} to pending_to_delete folder")
            return True
            
        except Exception as e:
            messagebox.showerror("Error", f"Could not move file: {e}")
            return False

def main():
    root = tk.Tk()
    app = MP4DuplicateFinder(root)
    root.mainloop()

if __name__ == "__main__":
    main()