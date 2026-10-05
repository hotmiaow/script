"""
Empty Folder Manager
====================
A GUI tool to find, move, and restore empty folders.

Features:
- Scan any directory for empty folders (recursively)
- Summary panel showing count and stats
- Move all/selected empty folders to a quarantine/archive folder
- Restore moved folders to their original locations
- JSON-based restore manifest for reliable recovery
- Dark UI theme
"""

import os
import json
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────────
APP_TITLE         = "Empty Folder Manager"
MANIFEST_FILENAME = ".empty_folder_manifest.json"
ACCENT    = "#4A90D9"
BG_DARK   = "#1E1E2E"
BG_MID    = "#2A2A3E"
BG_LIGHT  = "#313149"
FG_MAIN   = "#CDD6F4"
FG_DIM    = "#6C7086"
FG_GREEN  = "#A6E3A1"
FG_RED    = "#F38BA8"
FG_YELLOW = "#F9E2AF"


# ── Helpers ────────────────────────────────────────────────────────────────────

def is_truly_empty(path: Path) -> bool:
    """Return True if the directory contains no files recursively."""
    for entry in path.rglob("*"):
        if entry.is_file():
            return False
    return True


def find_empty_folders(root: Path, status_cb=None) -> list:
    """Walk *root* and collect directories that are truly empty."""
    empty = []
    try:
        all_dirs = [p for p in root.rglob("*") if p.is_dir()]
    except PermissionError:
        return empty

    for idx, d in enumerate(all_dirs):
        if status_cb:
            status_cb(f"Scanning … ({idx + 1}/{len(all_dirs)})  {d.name}")
        try:
            if is_truly_empty(d):
                # Only add top-most empty ancestor (skip children already covered)
                if not any(d.is_relative_to(e) for e in empty):
                    empty.append(d)
        except (PermissionError, ValueError):
            continue
    return empty


# ── Main Application ───────────────────────────────────────────────────────────

class EmptyFolderManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1020x700")
        self.minsize(820, 560)
        self.configure(bg=BG_DARK)

        self._scan_root = None      # Path
        self._found     = []        # list of Path
        self._scan_thread = None    # threading.Thread

        self._build_ui()
        self._apply_styles()

    # ── UI Construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar: scan directory ────────────────────────────────────────────
        top = tk.Frame(self, bg=BG_DARK, pady=10, padx=14)
        top.pack(fill="x")

        tk.Label(top, text="📁  Scan Directory:", bg=BG_DARK, fg=FG_MAIN,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")
        self.scan_entry = tk.Entry(top, bg=BG_MID, fg=FG_MAIN,
                                    insertbackground=FG_MAIN, relief="flat",
                                    font=("Segoe UI", 10), width=55)
        self.scan_entry.grid(row=0, column=1, padx=(8, 4), ipady=4, sticky="ew")
        top.columnconfigure(1, weight=1)

        self._btn(top, "Browse…", self._pick_scan_dir).grid(row=0, column=2, padx=4)
        self._btn(top, "🔍  Scan", self._start_scan, accent=True).grid(row=0, column=3, padx=4)

        # ── Summary bar ───────────────────────────────────────────────────────
        summary = tk.Frame(self, bg=BG_MID, pady=8, padx=14)
        summary.pack(fill="x")

        self.lbl_count = self._stat_label(summary, "Empty folders found", "0")
        self.lbl_count.pack(side="left", padx=(0, 30))

        self.lbl_status = tk.Label(summary, text="Ready — choose a directory and scan.",
                                    bg=BG_MID, fg=FG_DIM, font=("Segoe UI", 9))
        self.lbl_status.pack(side="left")

        self.progress = ttk.Progressbar(summary, mode="indeterminate", length=140)
        self.progress.pack(side="right", padx=6)

        # ── Split pane: list (left) + actions (right) ─────────────────────────
        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                               sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=10, pady=6)

        # Left — folder tree list ──────────────────────────────────────────────
        left = tk.Frame(pane, bg=BG_DARK)
        pane.add(left, minsize=440)

        hdr = tk.Frame(left, bg=BG_DARK)
        hdr.pack(fill="x", pady=(0, 4))
        tk.Label(hdr, text="Found Empty Folders", bg=BG_DARK, fg=FG_MAIN,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        self._btn(hdr, "Select All",  self._select_all).pack(side="right", padx=2)
        self._btn(hdr, "Select None", self._select_none).pack(side="right", padx=2)

        cols = ("path", "depth", "siblings")
        self.tree = ttk.Treeview(left, columns=cols, show="headings",
                                   selectmode="extended")
        self.tree.heading("path",     text="Path",    anchor="w")
        self.tree.heading("depth",    text="Depth",   anchor="center")
        self.tree.heading("siblings", text="Siblings", anchor="center")
        self.tree.column("path",      width=340, stretch=True)
        self.tree.column("depth",     width=55,  stretch=False, anchor="center")
        self.tree.column("siblings",  width=65,  stretch=False, anchor="center")

        vsb = ttk.Scrollbar(left, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(left, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")

        # Right — action panel ─────────────────────────────────────────────────
        right = tk.Frame(pane, bg=BG_DARK)
        pane.add(right, minsize=280)

        # Move section
        self._section(right, "📦  Move Empty Folders")

        tk.Label(right, text="Destination folder:", bg=BG_DARK, fg=FG_MAIN,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=10)
        dest_row = tk.Frame(right, bg=BG_DARK)
        dest_row.pack(fill="x", padx=10, pady=(2, 6))
        self.dest_entry = tk.Entry(dest_row, bg=BG_MID, fg=FG_MAIN,
                                    insertbackground=FG_MAIN, relief="flat",
                                    font=("Segoe UI", 9))
        self.dest_entry.pack(side="left", fill="x", expand=True, ipady=3)
        self._btn(dest_row, "…", self._pick_dest_dir, width=3).pack(side="right", padx=(4, 0))

        self._btn(right, "⬆  Move Selected Folders",
                  self._move_selected, accent=True, width=26).pack(padx=10, pady=4, fill="x")

        ttk.Separator(right, orient="horizontal").pack(fill="x", padx=10, pady=10)

        # Restore section
        self._section(right, "♻  Restore")

        tk.Label(right, text="Manifest file (.json):", bg=BG_DARK, fg=FG_MAIN,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=10)
        rest_row = tk.Frame(right, bg=BG_DARK)
        rest_row.pack(fill="x", padx=10, pady=(2, 6))
        self.rest_entry = tk.Entry(rest_row, bg=BG_MID, fg=FG_MAIN,
                                    insertbackground=FG_MAIN, relief="flat",
                                    font=("Segoe UI", 9))
        self.rest_entry.pack(side="left", fill="x", expand=True, ipady=3)
        self._btn(rest_row, "…", self._pick_manifest, width=3).pack(side="right", padx=(4, 0))

        self._btn(right, "♻  Restore from Manifest",
                  self._restore, width=26).pack(padx=10, pady=4, fill="x")

        ttk.Separator(right, orient="horizontal").pack(fill="x", padx=10, pady=10)

        # Activity Log
        self._section(right, "📋  Activity Log")
        log_frame = tk.Frame(right, bg=BG_DARK)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_box = tk.Text(log_frame, bg=BG_LIGHT, fg=FG_DIM,
                                font=("Consolas", 8), relief="flat",
                                state="disabled", wrap="word")
        log_vs = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=log_vs.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        log_vs.pack(side="right", fill="y")

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom = tk.Frame(self, bg=BG_DARK, pady=8, padx=14)
        bottom.pack(fill="x")
        self._btn(bottom, "🗑  Delete Selected (permanent!)",
                  self._delete_selected, danger=True).pack(side="left")
        self._btn(bottom, "Clear List", self._clear_list).pack(side="left", padx=8)
        tk.Label(bottom, text="Tip: use Move first — restore is always possible.",
                 bg=BG_DARK, fg=FG_DIM, font=("Segoe UI", 8)).pack(side="right")

    # ── Widget factories ───────────────────────────────────────────────────────

    def _btn(self, parent, text, command, accent=False, danger=False, width=None):
        kw = dict(font=("Segoe UI", 9), relief="flat", cursor="hand2",
                  activeforeground="white", padx=10, pady=4)
        if accent:
            kw.update(bg=ACCENT, fg="white", activebackground="#3a7bc8")
        elif danger:
            kw.update(bg=FG_RED, fg=BG_DARK, activebackground="#c0305a")
        else:
            kw.update(bg=BG_LIGHT, fg=FG_MAIN, activebackground="#404060")
        if width:
            kw["width"] = width
        return tk.Button(parent, text=text, command=command, **kw)

    def _stat_label(self, parent, label, value):
        frame = tk.Frame(parent, bg=BG_MID)
        tk.Label(frame, text=label, bg=BG_MID, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w")
        v = tk.Label(frame, text=value, bg=BG_MID, fg=FG_YELLOW,
                     font=("Segoe UI", 14, "bold"))
        v.pack(anchor="w")
        frame._value_label = v
        return frame

    def _section(self, parent, title):
        tk.Label(parent, text=title, bg=BG_DARK, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(6, 2))

    def _apply_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview",
                     background=BG_MID, foreground=FG_MAIN,
                     fieldbackground=BG_MID, rowheight=22,
                     font=("Segoe UI", 9))
        s.configure("Treeview.Heading",
                     background=BG_LIGHT, foreground=FG_MAIN,
                     font=("Segoe UI", 9, "bold"), relief="flat")
        s.map("Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "white")])
        s.configure("Vertical.TScrollbar",
                     background=BG_LIGHT, troughcolor=BG_MID,
                     arrowcolor=FG_DIM, borderwidth=0)
        s.configure("Horizontal.TScrollbar",
                     background=BG_LIGHT, troughcolor=BG_MID,
                     arrowcolor=FG_DIM, borderwidth=0)
        s.configure("TProgressbar", background=ACCENT, troughcolor=BG_LIGHT)

    # ── Pickers ────────────────────────────────────────────────────────────────

    def _pick_scan_dir(self):
        d = filedialog.askdirectory(title="Select directory to scan")
        if d:
            self.scan_entry.delete(0, "end")
            self.scan_entry.insert(0, d)

    def _pick_dest_dir(self):
        d = filedialog.askdirectory(title="Select destination for empty folders")
        if d:
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, d)

    def _pick_manifest(self):
        f = filedialog.askopenfilename(
            title="Select manifest file",
            filetypes=[("JSON manifest", "*.json"), ("All files", "*.*")])
        if f:
            self.rest_entry.delete(0, "end")
            self.rest_entry.insert(0, f)

    # ── Scan ───────────────────────────────────────────────────────────────────

    def _start_scan(self):
        raw = self.scan_entry.get().strip()
        if not raw:
            messagebox.showwarning("No directory", "Please enter or browse a scan directory.")
            return
        root = Path(raw)
        if not root.is_dir():
            messagebox.showerror("Not found", f"Directory not found:\n{root}")
            return

        self._scan_root = root
        self._found.clear()
        self._clear_tree()
        self.progress.start(12)
        self._set_status("Scanning …", FG_DIM)

        def worker():
            results = find_empty_folders(root, status_cb=lambda m: self._set_status(m, FG_DIM))
            self.after(0, lambda: self._scan_done(results))

        self._scan_thread = threading.Thread(target=worker, daemon=True)
        self._scan_thread.start()

    def _scan_done(self, results):
        self.progress.stop()
        self._found = sorted(results)
        count = len(self._found)
        self.lbl_count._value_label.config(text=str(count))

        if count == 0:
            self._set_status("✅  No empty folders found.", FG_GREEN)
            self._log("Scan complete — no empty folders found.")
            return

        self._set_status(f"Found {count} empty folder(s).", FG_YELLOW)
        self._log(f"Scan complete — {count} empty folder(s) found under: {self._scan_root}")

        for p in self._found:
            try:
                depth    = len(p.relative_to(self._scan_root).parts)
                siblings = len([x for x in p.parent.iterdir() if x.is_dir()])
            except Exception:
                depth, siblings = 0, 0
            self.tree.insert("", "end", iid=str(p),
                              values=(str(p), depth, siblings))

        self._select_all()

    # ── Tree helpers ───────────────────────────────────────────────────────────

    def _clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _clear_list(self):
        self._found.clear()
        self._clear_tree()
        self.lbl_count._value_label.config(text="0")
        self._set_status("List cleared.", FG_DIM)
        self._log("List cleared.")

    def _select_all(self):
        self.tree.selection_set(self.tree.get_children())

    def _select_none(self):
        self.tree.selection_remove(self.tree.get_children())

    def _selected_paths(self):
        return [Path(iid) for iid in self.tree.selection()]

    # ── Move ───────────────────────────────────────────────────────────────────

    def _move_selected(self):
        paths = self._selected_paths()
        if not paths:
            messagebox.showwarning("Nothing selected", "Select at least one folder to move.")
            return

        dest_raw = self.dest_entry.get().strip()
        if not dest_raw:
            messagebox.showwarning("No destination", "Enter or browse a destination folder.")
            return

        dest = Path(dest_raw)
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Cannot create destination", str(e))
            return

        manifest_path = dest / MANIFEST_FILENAME
        manifest = {}
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
            except Exception:
                manifest = {}

        moved, skipped = 0, 0
        timestamp = datetime.now().isoformat(timespec="seconds")

        for src in paths:
            if not src.exists():
                self._log(f"  SKIP (gone): {src}")
                skipped += 1
                continue

            # Build a unique name under dest
            rel_name = src.name
            target = dest / rel_name
            counter = 1
            while target.exists():
                target = dest / f"{rel_name}_{counter}"
                counter += 1

            try:
                shutil.move(str(src), str(target))
                manifest[str(target)] = {
                    "original": str(src),
                    "moved_at": timestamp,
                }
                self.tree.delete(str(src))
                self._log(f"  MOVED: {src.name}  →  {target}")
                moved += 1
            except Exception as e:
                self._log(f"  ERROR moving {src}: {e}")
                skipped += 1

        # Persist manifest
        try:
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
        except Exception as e:
            self._log(f"  WARNING: could not save manifest — {e}")

        # Refresh found list
        self._found = [p for p in self._found if self.tree.exists(str(p))]
        self.lbl_count._value_label.config(text=str(len(self._found)))

        summary = f"Move complete: {moved} moved, {skipped} skipped."
        self._set_status(summary, FG_GREEN if not skipped else FG_YELLOW)
        self._log(summary)

        if moved:
            self._log(f"  Manifest: {manifest_path}")
            self.rest_entry.delete(0, "end")
            self.rest_entry.insert(0, str(manifest_path))
            messagebox.showinfo("Done",
                f"{summary}\n\nManifest saved at:\n{manifest_path}\n\n"
                "Use 'Restore from Manifest' to undo this operation.")

    # ── Restore ────────────────────────────────────────────────────────────────

    def _restore(self):
        manifest_raw = self.rest_entry.get().strip()
        if not manifest_raw:
            messagebox.showwarning("No manifest", "Enter or browse a manifest file path.")
            return

        manifest_path = Path(manifest_raw)
        if not manifest_path.exists():
            messagebox.showerror("Not found", f"Manifest not found:\n{manifest_path}")
            return

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except Exception as e:
            messagebox.showerror("Bad manifest", f"Cannot read manifest:\n{e}")
            return

        if not manifest:
            messagebox.showinfo("Empty manifest", "The manifest contains no entries.")
            return

        confirmed = messagebox.askyesno(
            "Confirm Restore",
            f"Restore {len(manifest)} folder(s) to their original locations?\n\n"
            "This will move folders back from the quarantine directory.",
        )
        if not confirmed:
            return

        restored, skipped = 0, 0
        failed_entries = {}

        for current_str, info in manifest.items():
            current  = Path(current_str)
            original = Path(info["original"])

            if not current.exists():
                self._log(f"  SKIP (missing): {current.name}")
                skipped += 1
                failed_entries[current_str] = info
                continue

            try:
                original.parent.mkdir(parents=True, exist_ok=True)
                dest_path = original
                if dest_path.exists():
                    ts = datetime.now().strftime("%H%M%S")
                    dest_path = original.parent / f"{original.name}_restored_{ts}"
                shutil.move(str(current), str(dest_path))
                self._log(f"  RESTORED: {current.name}  →  {dest_path}")
                restored += 1
            except Exception as e:
                self._log(f"  ERROR restoring {current.name}: {e}")
                skipped += 1
                failed_entries[current_str] = info

        # Update / remove manifest
        try:
            if failed_entries:
                with open(manifest_path, "w") as f:
                    json.dump(failed_entries, f, indent=2)
                self._log(f"  Manifest updated ({len(failed_entries)} entries remain).")
            else:
                manifest_path.unlink()
                self._log(f"  Manifest removed (all entries restored).")
        except Exception as e:
            self._log(f"  WARNING: could not update manifest — {e}")

        summary = f"Restore complete: {restored} restored, {skipped} skipped."
        self._set_status(summary, FG_GREEN if not skipped else FG_YELLOW)
        self._log(summary)
        messagebox.showinfo("Restore Done", summary)

    # ── Delete ─────────────────────────────────────────────────────────────────

    def _delete_selected(self):
        paths = self._selected_paths()
        if not paths:
            messagebox.showwarning("Nothing selected", "Select folders to delete.")
            return

        confirmed = messagebox.askyesno(
            "⚠  Permanent Delete",
            f"Permanently delete {len(paths)} folder(s)?\n\n"
            "This CANNOT be undone. Consider using Move instead.",
            icon="warning",
        )
        if not confirmed:
            return

        deleted, skipped = 0, 0
        for p in paths:
            try:
                if p.exists():
                    shutil.rmtree(str(p))
                    self.tree.delete(str(p))
                    self._log(f"  DELETED: {p}")
                    deleted += 1
                else:
                    skipped += 1
            except Exception as e:
                self._log(f"  ERROR deleting {p}: {e}")
                skipped += 1

        self._found = [p for p in self._found if self.tree.exists(str(p))]
        self.lbl_count._value_label.config(text=str(len(self._found)))
        summary = f"Deleted {deleted}, skipped {skipped}."
        self._set_status(summary, FG_RED)
        self._log(summary)

    # ── Status / log ──────────────────────────────────────────────────────────

    def _set_status(self, msg, color=FG_DIM):
        self.lbl_status.config(text=msg, fg=color)
        self.update_idletasks()

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = EmptyFolderManager()
    app.mainloop()
