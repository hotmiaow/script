import fitz
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import uuid

class FileItem:
    def __init__(self, path):
        self.path = path
        self.filename = os.path.basename(path)
        self.doc = fitz.open(path)
        # Convert image formats to PDF directly in memory
        if not path.lower().endswith('.pdf'):
            pdfbytes = self.doc.convert_to_pdf()
            self.doc.close()
            self.doc = fitz.open("pdf", pdfbytes)
        self.num_pages = len(self.doc)
        self.covers = {i: [] for i in range(self.num_pages)}

class PdfHeadCutterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF / Image Redactor Pro")
        self.root.geometry("1400x900")
        
        self.files = []
        self.current_file_idx = -1
        self.current_page_idx = 0
        
        self.zoom_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.canvas_image = None
        
        self.selected_cover_idx = -1
        self.drag_mode = None
        self.start_x = 0
        self.start_y = 0
        self.resize_timer = None
        
        self.setup_ui()
        
    def setup_ui(self):
        # LEFT FRAME: Files
        list_frame = tk.Frame(self.root, width=300, bg="#ecf0f1", padx=10, pady=10)
        list_frame.pack(side=tk.LEFT, fill=tk.Y)
        list_frame.pack_propagate(False)
        
        tk.Label(list_frame, text="Document Queue", bg="#ecf0f1", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 10))
        
        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE, font=("Arial", 10))
        self.file_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)
        
        tk.Button(list_frame, text="Add PDF/Image(s)", command=self.add_files).pack(fill=tk.X, pady=2)
        tk.Button(list_frame, text="Remove Selected", command=self.remove_file).pack(fill=tk.X, pady=2)
        tk.Button(list_frame, text="Move Up", command=self.move_up).pack(fill=tk.X, pady=2)
        tk.Button(list_frame, text="Move Down", command=self.move_down).pack(fill=tk.X, pady=2)
        tk.Button(list_frame, text="EXPORT SINGLE PDF", command=self.export_pdf, bg="#27ae60", fg="white", font=("Arial", 12, "bold"), pady=10).pack(fill=tk.X, pady=20)
        
        # RIGHT FRAME: Controls
        control_frame = tk.Frame(self.root, width=300, bg="#ecf0f1", padx=10, pady=10)
        control_frame.pack(side=tk.RIGHT, fill=tk.Y)
        control_frame.pack_propagate(False)
        
        self.lbl_page_info = tk.Label(control_frame, text="No active file", bg="#ecf0f1", font=("Arial", 14, "bold"))
        self.lbl_page_info.pack(pady=5)
        
        nav_frame = tk.Frame(control_frame, bg="#ecf0f1")
        nav_frame.pack(pady=10)
        tk.Button(nav_frame, text="< Prev", command=self.prev_page, width=8).pack(side=tk.LEFT, padx=2)
        tk.Button(nav_frame, text="Next >", command=self.next_page, width=8).pack(side=tk.LEFT, padx=2)
        
        # Instructions
        instr = tk.Label(control_frame, text="Click & drag on image\nto draw black covers.", bg="#ecf0f1", fg="#333", justify=tk.LEFT)
        instr.pack(pady=10)
        
        tk.Label(control_frame, text="Cover Options", bg="#ecf0f1", font=("Arial", 12, "bold")).pack(pady=(20, 10))
        tk.Button(control_frame, text="Delete Selected Cover (Del)", command=self.delete_cover, fg="red").pack(fill=tk.X, pady=2)
        
        tk.Label(control_frame, text="Update / Duplicate Selected To:", bg="#ecf0f1", font=("Arial", 10, "italic")).pack(pady=(20, 5))
        tk.Button(control_frame, text="All Pages (This File)", command=self.dup_all_pages_this_file).pack(fill=tk.X, pady=2)
        tk.Button(control_frame, text="All Pages (All Files)", command=self.dup_all_pages_all_files).pack(fill=tk.X, pady=2)
        tk.Button(control_frame, text="1st Page (All Files)", command=self.dup_first_page_all_files).pack(fill=tk.X, pady=2)
        tk.Button(control_frame, text="2nd Page (All Files)", command=self.dup_second_page_all_files).pack(fill=tk.X, pady=2)
        tk.Button(control_frame, text="Custom Range (This File)...", command=self.dup_custom_this_file).pack(fill=tk.X, pady=2)
        tk.Button(control_frame, text="Custom Range (All Files)...", command=self.dup_custom_all_files).pack(fill=tk.X, pady=2)

        # MIDDLE FRAME: Canvas
        canvas_frame = tk.Frame(self.root, bg="#bdc3c7", bd=2, relief=tk.SUNKEN)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.canvas = tk.Canvas(canvas_frame, bg="#34495e")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<Configure>", self.on_configure)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.root.bind("<Delete>", lambda e: self.delete_cover())
        self.root.bind("<BackSpace>", lambda e: self.delete_cover())

    # --- LISTBOX & NAVIGATION ---
    def update_listbox(self):
        self.file_listbox.delete(0, tk.END)
        for f in self.files:
            self.file_listbox.insert(tk.END, f.filename)
        if self.files and self.current_file_idx >= 0:
            self.file_listbox.selection_set(self.current_file_idx)
    
    def add_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("PDF & Images", "*.pdf *.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")])
        for p in paths:
            try:
                self.files.append(FileItem(p))
            except Exception as e:
                messagebox.showerror("Error", f"Could not open {os.path.basename(p)}\n{e}")
        self.update_listbox()
        if self.files and self.current_file_idx < 0:
            self.current_file_idx = len(self.files) - len(paths)
            self.current_page_idx = 0
            self.update_canvas_debounced()

    def remove_file(self):
        sel = self.file_listbox.curselection()
        if not sel: return
        idx = sel[0]
        self.files.pop(idx)
        if self.current_file_idx == idx:
            self.current_file_idx = -1
            self.current_page_idx = 0
        elif self.current_file_idx > idx:
            self.current_file_idx -= 1
        self.update_listbox()
        if self.files and self.current_file_idx < 0:
            self.current_file_idx = 0
        self.update_canvas_debounced()
        
    def move_up(self):
        sel = self.file_listbox.curselection()
        if not sel: return
        idx = sel[0]
        if idx > 0:
            self.files[idx], self.files[idx-1] = self.files[idx-1], self.files[idx]
            if self.current_file_idx == idx: self.current_file_idx -= 1
            elif self.current_file_idx == idx - 1: self.current_file_idx += 1
            self.update_listbox()
            self.file_listbox.selection_set(idx - 1)

    def move_down(self):
        sel = self.file_listbox.curselection()
        if not sel: return
        idx = sel[0]
        if idx < len(self.files) - 1:
            self.files[idx], self.files[idx+1] = self.files[idx+1], self.files[idx]
            if self.current_file_idx == idx: self.current_file_idx += 1
            elif self.current_file_idx == idx + 1: self.current_file_idx -= 1
            self.update_listbox()
            self.file_listbox.selection_set(idx + 1)

    def on_file_select(self, event):
        sel = self.file_listbox.curselection()
        if sel:
            idx = sel[0]
            if idx != self.current_file_idx:
                self.current_file_idx = idx
                self.current_page_idx = 0
                self.selected_cover_idx = -1
                self.update_canvas_debounced()

    def prev_page(self):
        if self.current_file_idx >= 0:
            if self.current_page_idx > 0:
                self.current_page_idx -= 1
                self.selected_cover_idx = -1
                self.update_canvas_debounced()

    def next_page(self):
        if self.current_file_idx >= 0:
            f = self.files[self.current_file_idx]
            if self.current_page_idx < f.num_pages - 1:
                self.current_page_idx += 1
                self.selected_cover_idx = -1
                self.update_canvas_debounced()

    # --- CANVAS & RENDERING ---
    def on_configure(self, event):
        self.update_canvas_debounced()
        
    def update_canvas_debounced(self):
        if self.resize_timer:
            self.root.after_cancel(self.resize_timer)
        self.resize_timer = self.root.after(100, self.update_canvas)

    def update_canvas(self):
        if self.current_file_idx < 0 or not self.files:
            self.canvas.delete("all")
            self.lbl_page_info.config(text="No active file")
            self.canvas_image = None
            return
            
        f = self.files[self.current_file_idx]
        if self.current_page_idx >= f.num_pages:
            self.current_page_idx = 0
            
        page = f.doc[self.current_page_idx]
        
        c_w = self.canvas.winfo_width()
        c_h = self.canvas.winfo_height()
        if c_w <= 1 or c_h <= 1:
            c_w, c_h = 800, 600
            
        p_rect = page.rect
        if p_rect.width == 0 or p_rect.height == 0:
            return
            
        zoom_x = c_w / p_rect.width
        zoom_y = c_h / p_rect.height
        self.zoom_factor = min(zoom_x, zoom_y) * 0.95
        if self.zoom_factor <= 0: self.zoom_factor = 1.0
        
        mat = fitz.Matrix(self.zoom_factor, self.zoom_factor)
        pix = page.get_pixmap(matrix=mat)
        
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.canvas_image = ImageTk.PhotoImage(img)
        
        self.canvas.delete("all")
        self.offset_x = (c_w - pix.width) / 2
        self.offset_y = (c_h - pix.height) / 2
        
        self.canvas.create_image(self.offset_x, self.offset_y, image=self.canvas_image, anchor=tk.NW)
        
        self.lbl_page_info.config(text=f"Page {self.current_page_idx + 1} / {f.num_pages}")
        self.draw_covers()

    def doc_to_can(self, p):
        return (p[0] * self.zoom_factor + self.offset_x, p[1] * self.zoom_factor + self.offset_y)

    def can_to_doc(self, p):
        return ((p[0] - self.offset_x) / self.zoom_factor, (p[1] - self.offset_y) / self.zoom_factor)

    def draw_covers(self):
        self.canvas.delete("cover")
        if self.current_file_idx < 0: return
        f = self.files[self.current_file_idx]
        covers = f.covers.get(self.current_page_idx, [])
        
        for i, c in enumerate(covers):
            x0, y0 = self.doc_to_can((c[0], c[1]))
            x1, y1 = self.doc_to_can((c[2], c[3]))
            
            fill_color = "black"
            outline_color = "red" if i == self.selected_cover_idx else "white"
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill_color, outline=outline_color, width=2, tags=("cover", f"cover_{i}", "rect"))
            
            if i == self.selected_cover_idx:
                s = 5
                self.canvas.create_rectangle(x0-s, y0-s, x0+s, y0+s, fill="red", tags=("cover", "handle", "tl"))
                self.canvas.create_rectangle(x1-s, y0-s, x1+s, y0+s, fill="red", tags=("cover", "handle", "tr"))
                self.canvas.create_rectangle(x0-s, y1-s, x0+s, y1+s, fill="red", tags=("cover", "handle", "bl"))
                self.canvas.create_rectangle(x1-s, y1-s, x1+s, y1+s, fill="red", tags=("cover", "handle", "br"))

    # --- MOUSE INTERACTIONS ---
    def on_canvas_press(self, event):
        self.canvas.focus_set()
        if self.current_file_idx < 0: return
        f = self.files[self.current_file_idx]
        covers = f.covers.get(self.current_page_idx, [])
        
        cx, cy = event.x, event.y
        dx, dy = self.can_to_doc((cx, cy))
        
        item = self.canvas.find_withtag("current")
        if item:
            tags = self.canvas.gettags(item[0])
            if "handle" in tags:
                if "tl" in tags: self.drag_mode = "tl"
                elif "tr" in tags: self.drag_mode = "tr"
                elif "bl" in tags: self.drag_mode = "bl"
                elif "br" in tags: self.drag_mode = "br"
                self.start_x, self.start_y = dx, dy
                return

            if "rect" in tags:
                for t in tags:
                    if t.startswith("cover_"):
                        idx = int(t.split("_")[1])
                        self.selected_cover_idx = idx
                        self.drag_mode = "move"
                        self.start_x, self.start_y = dx, dy
                        self.draw_covers()
                        return

        # Start a new cover if empty space clicked - Give it a unique ID
        self.selected_cover_idx = len(covers)
        c_id = str(uuid.uuid4())
        covers.append([dx, dy, dx, dy, c_id])
        self.drag_mode = "new"
        self.start_x, self.start_y = dx, dy
        self.draw_covers()

    def on_canvas_drag(self, event):
        if self.current_file_idx < 0: return
        if self.selected_cover_idx < 0:
            messagebox.showwarning("No Cover Selected", "Please select a cover first by clicking on it.")
            return
        if not self.drag_mode: return
        f = self.files[self.current_file_idx]
        covers = f.covers.get(self.current_page_idx, [])
        if self.selected_cover_idx >= len(covers): return
        
        c = covers[self.selected_cover_idx]
        dx, dy = self.can_to_doc((event.x, event.y))
        
        if self.drag_mode == "new":
            c[2], c[3] = dx, dy
        elif self.drag_mode == "move":
            diff_x = dx - self.start_x
            diff_y = dy - self.start_y
            c[0] += diff_x; c[2] += diff_x
            c[1] += diff_y; c[3] += diff_y
            self.start_x, self.start_y = dx, dy
        elif self.drag_mode == "tl":
            c[0], c[1] = dx, dy
        elif self.drag_mode == "tr":
            c[2], c[1] = dx, dy
        elif self.drag_mode == "bl":
            c[0], c[3] = dx, dy
        elif self.drag_mode == "br":
            c[2], c[3] = dx, dy
            
        self.draw_covers()

    def on_canvas_release(self, event):
        if self.current_file_idx < 0: return
        if self.selected_cover_idx < 0:
            messagebox.showwarning("No Cover Selected", "Please select a cover first by clicking on it.")
            return
        f = self.files[self.current_file_idx]
        covers = f.covers.get(self.current_page_idx, [])
        if self.selected_cover_idx < len(covers):
            c = covers[self.selected_cover_idx]
            x0, x1 = min(c[0], c[2]), max(c[0], c[2])
            y0, y1 = min(c[1], c[3]), max(c[1], c[3])
            
            c_w = (x1 - x0) * self.zoom_factor
            c_h = (y1 - y0) * self.zoom_factor
            
            if c_w < 5 or c_h < 5:
                covers.pop(self.selected_cover_idx)
                self.selected_cover_idx = -1
            else:
                 covers[self.selected_cover_idx] = [x0, y0, x1, y1, c[4]]
                
        self.drag_mode = None
        self.draw_covers()

    def delete_cover(self):
        if self.current_file_idx < 0: return
        if self.selected_cover_idx < 0:
            messagebox.showwarning("No Cover Selected", "Please select a cover first by clicking on it.")
            return
        f = self.files[self.current_file_idx]
        covers = f.covers.get(self.current_page_idx, [])
        if self.selected_cover_idx < len(covers):
            covers.pop(self.selected_cover_idx)
            self.selected_cover_idx = -1
            self.draw_covers()

    # --- UPDATE / DUPLICATE LOGIC ---
    def _apply_cover_to_page(self, c, target_f, page_i, src_w, src_h):
        tgt_rect = target_f.doc[page_i].rect
        tw, th = tgt_rect.width, tgt_rect.height
        sx = tw / src_w if src_w > 0 else 1.0
        sy = th / src_h if src_h > 0 else 1.0
        
        # Calculate new coordinates but keep the matching ID
        new_c = [c[0]*sx, c[1]*sy, c[2]*sx, c[3]*sy, c[4]]
        
        existing_covers = target_f.covers[page_i]
        for existing in existing_covers:
            # If the IDs match, UPDATE the existing cover!
            if len(existing) > 4 and existing[4] == c[4]:
                existing[0:4] = new_c[0:4]
                return
                
        # If not already present on page, add it as a new duplicate
        existing_covers.append(new_c)

    def dup_all_pages_this_file(self):
        if self.current_file_idx < 0: return
        if self.selected_cover_idx < 0:
            messagebox.showwarning("No Cover Selected", "Please select a cover first by clicking on it.")
            return
        f = self.files[self.current_file_idx]
        c = f.covers[self.current_page_idx][self.selected_cover_idx]
        
        src_rect = f.doc[self.current_page_idx].rect
        sw, sh = src_rect.width, src_rect.height
        
        for i in range(f.num_pages):
            if i != self.current_page_idx:
                self._apply_cover_to_page(c, f, i, sw, sh)
        messagebox.showinfo("Success", f"Updated/Duplicated to {f.num_pages - 1} other pages in this file.")
                
    def dup_all_pages_all_files(self):
        if self.current_file_idx < 0: return
        if self.selected_cover_idx < 0:
            messagebox.showwarning("No Cover Selected", "Please select a cover first by clicking on it.")
            return
        f = self.files[self.current_file_idx]
        c = f.covers[self.current_page_idx][self.selected_cover_idx]
        
        src_rect = f.doc[self.current_page_idx].rect
        sw, sh = src_rect.width, src_rect.height
        
        count = 0
        for other_f in self.files:
            for i in range(other_f.num_pages):
                if other_f == f and i == self.current_page_idx: continue
                self._apply_cover_to_page(c, other_f, i, sw, sh)
                count += 1
        messagebox.showinfo("Success", f"Updated/Duplicated to {count} other pages across all files.")
                
    def dup_first_page_all_files(self):
        if self.current_file_idx < 0: return
        if self.selected_cover_idx < 0:
            messagebox.showwarning("No Cover Selected", "Please select a cover first by clicking on it.")
            return
        f = self.files[self.current_file_idx]
        c = f.covers[self.current_page_idx][self.selected_cover_idx]
        
        src_rect = f.doc[self.current_page_idx].rect
        sw, sh = src_rect.width, src_rect.height
        
        count = 0
        for other_f in self.files:
            if other_f.num_pages > 0:
                if other_f == f and self.current_page_idx == 0: continue
                self._apply_cover_to_page(c, other_f, 0, sw, sh)
                count += 1
        messagebox.showinfo("Success", f"Updated/Duplicated to 1st page of {count} other files.")

    def dup_second_page_all_files(self):
        if self.current_file_idx < 0: return
        if self.selected_cover_idx < 0:
            messagebox.showwarning("No Cover Selected", "Please select a cover first by clicking on it.")
            return
        f = self.files[self.current_file_idx]
        c = f.covers[self.current_page_idx][self.selected_cover_idx]
        
        src_rect = f.doc[self.current_page_idx].rect
        sw, sh = src_rect.width, src_rect.height
        
        count = 0
        for other_f in self.files:
            if other_f.num_pages > 1:
                if other_f == f and self.current_page_idx == 1: continue
                self._apply_cover_to_page(c, other_f, 1, sw, sh)
                count += 1
        messagebox.showinfo("Success", f"Updated/Duplicated to 2nd page of {count} other files.")

    def parse_page_range(self, range_str, total_pages):
        pages = set()
        parts = range_str.split(',')
        for part in parts:
            part = part.strip().lower()
            if not part: continue
            if part == 'all':
                 return set(range(total_pages))
            if '-' in part:
                bounds = part.split('-')
                if len(bounds) == 2:
                    start_str, end_str = bounds[0].strip(), bounds[1].strip()
                    try:
                        start = int(start_str)
                        if end_str == 'end':
                            end = total_pages
                        else:
                            end = int(end_str)
                        
                        if 1 <= start <= total_pages and 1 <= end <= total_pages:
                            if start <= end:
                                for i in range(start, end + 1):
                                    pages.add(i - 1)
                    except ValueError:
                        pass
            else:
                try:
                    num = int(part)
                    if 1 <= num <= total_pages:
                        pages.add(num - 1)
                except ValueError:
                    pass
        return list(pages)

    def dup_custom_this_file(self):
        if self.current_file_idx < 0: return
        if self.selected_cover_idx < 0:
            messagebox.showwarning("No Cover Selected", "Please select a cover first by clicking on it.")
            return
            
        f = self.files[self.current_file_idx]
        from tkinter import simpledialog
        range_str = simpledialog.askstring("Custom Range", f"Enter target pages for '{f.filename}'\n(Examples: '1, 3', '2-5', '2-end', 'all'):")
        if not range_str: return
        
        target_pages = self.parse_page_range(range_str, f.num_pages)
        if not target_pages:
            messagebox.showwarning("Invalid Output", "No valid pages parsed from your input.")
            return

        c = f.covers[self.current_page_idx][self.selected_cover_idx]
        src_rect = f.doc[self.current_page_idx].rect
        sw, sh = src_rect.width, src_rect.height
        
        count = 0
        for i in target_pages:
            if i != self.current_page_idx:
                self._apply_cover_to_page(c, f, i, sw, sh)
                count += 1
        messagebox.showinfo("Success", f"Updated/Duplicated to {count} specified pages.")
        self.draw_covers()

    def dup_custom_all_files(self):
        if self.current_file_idx < 0: return
        if self.selected_cover_idx < 0:
            messagebox.showwarning("No Cover Selected", "Please select a cover first by clicking on it.")
            return
            
        from tkinter import simpledialog
        range_str = simpledialog.askstring("Custom Range", "Enter target pages across MULTIPLE files\n(Examples: '1, 3', '2-5', '2-end', 'all'):")
        if not range_str: return
        
        f = self.files[self.current_file_idx]
        c = f.covers[self.current_page_idx][self.selected_cover_idx]
        src_rect = f.doc[self.current_page_idx].rect
        sw, sh = src_rect.width, src_rect.height
        
        count = 0
        for other_f in self.files:
            target_pages = self.parse_page_range(range_str, other_f.num_pages)
            for i in target_pages:
                if other_f == f and i == self.current_page_idx: continue
                self._apply_cover_to_page(c, other_f, i, sw, sh)
                count += 1
                
        messagebox.showinfo("Success", f"Updated/Duplicated to {count} matching pages across all files.")
        self.draw_covers()

    def export_pdf(self):
        if not self.files:
            messagebox.showwarning("No Files", "Please add some files to the queue first.")
            return
            
        save_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not save_path: return
        
        merged_doc = fitz.open()
        
        for f in self.files:
            temp_doc = fitz.open("pdf", f.doc.tobytes())
            for page_idx in range(len(temp_doc)):
                page = temp_doc[page_idx]
                covers = f.covers.get(page_idx, [])
                for c in covers:
                    rect = fitz.Rect(c[0], c[1], c[2], c[3])
                    page.add_redact_annot(rect, fill=(0,0,0))
                if covers:
                    page.apply_redactions()
                    
            merged_doc.insert_pdf(temp_doc)
            temp_doc.close()
            
        try:
            merged_doc.save(save_path)
            merged_doc.close()
            messagebox.showinfo("Export Successful", f"Saved flattened PDF to:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to save PDF:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = PdfHeadCutterApp(root)
    root.mainloop()
