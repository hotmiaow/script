import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
import sys
import textwrap
import threading
import json
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter
import fitz
from PIL import Image, ImageTk
from datetime import datetime
import platform
import subprocess

# ================= Translations =================

TRANSLATIONS = {
    "en": {
        "title": "Secure Watermark Pro v2.9",
        "step1": "STEP 1: File Selection",
        "btn_select": "Open PDF / Image",
        "lbl_file": "No file selected",
        "step2": "STEP 2: Edit Content",
        "step3": "STEP 3: Adjust Style",
        "alpha": "Opacity (Alpha):",
        "size": "Font Size (Size):",
        "step_x": "Horizontal Spacing (X):",
        "step_y": "Vertical Spacing (Y):",
        "btn_suggest": "Auto Optimize Spacing",
        "btn_run": "Run Flattening & Save",
        "preview_sync": "Syncing preview...",
        "status_ready": "Ready",
        "status_file_loaded": "File loaded successfully",
        "status_error": "Error: ",
        "export_tmpl": "Export Templates",
        "import_tmpl": "Import Templates",
        "lang_switch": "切換至繁體中文",
        "preview_text": "[ Preview ]",
        "btn_run_processing": "Processing...",
        "msg_done": "Document completely flattened.",
        "msg_done_title": "Done"
    },
    "zh": {
        "title": "Secure Watermark Pro v2.9",
        "step1": "STEP 1: 檔案選擇",
        "btn_select": "開啟 PDF / 圖片",
        "lbl_file": "尚未選取文件",
        "step2": "STEP 2: 編輯內容",
        "step3": "STEP 3: 樣式調整",
        "alpha": "透明度 (Alpha):",
        "size": "字體大小 (Size):",
        "step_x": "橫向間距 (X spacing):",
        "step_y": "縱向間距 (Y spacing):",
        "btn_suggest": "自動優化間距 (防重疊)",
        "btn_run": "執行扁平化儲存",
        "preview_sync": "預覽比例同步中...",
        "status_ready": "準備就緒",
        "status_file_loaded": "檔案載入成功",
        "status_error": "讀取失敗: ",
        "export_tmpl": "匯出範本",
        "import_tmpl": "匯入範本",
        "lang_switch": "Switch to English",
        "preview_text": "[ 文件內容預覽 ]",
        "btn_run_processing": "處理中...",
        "msg_done": "文件已完成扁平化。",
        "msg_done_title": "完成"
    }
}

DEFAULT_TEMPLATES = {
    "Rental App": {"text": "FOR RENTAL APPLICATION PURPOSE ONLY\nNO OTHER USE AUTHORIZED\nDATE: " + datetime.now().strftime("%Y-%m-%d"), "alpha": 0.10, "size": 10},
    "ID Copy": {"text": "僅供身分驗證使用\n他用無效\nVOID IF COPIED", "alpha": 0.15, "size": 12},
    "Confidential": {"text": "STRICTLY CONFIDENTIAL\nINTERNAL USE ONLY", "alpha": 0.08, "size": 11},
    "Custom": {"text": "For Rental Application Only\n[" + datetime.now().strftime("%Y-%m-%d") + "]", "alpha": 0.12, "size": 11}
}

# ================= 系統與字型設置 =================
try:
    if platform.system() == "Darwin":
        # macOS: 優先使用「黑體-繁」或「蘋方」
        pdfmetrics.registerFont(TTFont('CJK-Font', '/System/Library/Fonts/PingFang.ttc'))
    elif platform.system() == "Windows":
        # Windows: 微軟正黑體
        pdfmetrics.registerFont(TTFont('CJK-Font', 'msjh.ttc'))
    else:
        pdfmetrics.registerFont(TTFont('CJK-Font', 'simhei.ttf'))
    DEFAULT_FONT = 'CJK-Font'
except Exception:
    DEFAULT_FONT = 'Helvetica-Bold'


# ================= 核心渲染邏輯 =================

def get_suggested_steps(text, font_size):
    chars_per_line = 20
    wrapped = textwrap.wrap(text, width=chars_per_line)
    if not wrapped: return 250, 250
    max_chars = max([len(l) for l in wrapped])
    line_h = font_size * 1.5 # 提高行高緩衝

    text_w = max_chars * (font_size * 0.75)
    text_h = len(wrapped) * line_h

    # 旋轉補償間距
    s_x = (text_w + text_h) * 0.85 + (1.2 * inch)
    s_y = (text_w + text_h) * 0.55 + (1.5 * inch)
    return s_x, s_y

def create_final_watermark(text, page_width, page_height, font_size, opacity, step_x, step_y):
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))
    c.setFillAlpha(opacity)
    c.setFont(DEFAULT_FONT, font_size)
    wrapped_text = textwrap.wrap(text, width=20)
    line_height = font_size * 1.5

    c.saveState()
    c.translate(page_width / 2, page_height / 2)
    c.rotate(45)
    limit = max(page_width, page_height) * 2.0

    for x in range(int(-limit), int(limit), int(step_x)):
        for y in range(int(-limit), int(limit), int(step_y)):
            for i, line in enumerate(wrapped_text):
                c.drawString(x, y - (i * line_height), line)
    c.restoreState()
    c.save()
    packet.seek(0)
    return packet

# ================= UI 介面邏輯 =================

class WatermarkApp:
    def __init__(self, root):
        self.root = root
        self.lang = "en"
        self.templates = DEFAULT_TEMPLATES.copy()
        self.t = TRANSLATIONS[self.lang]
        
        self.root.title(self.t["title"])
        self.root.geometry("1300x950")
        self.input_paths = []
        self.doc_width, self.doc_height = 595.0, 842.0
        self.setup_ui()
        self.update_ui_strings()
        self.reset_to_suggested()

        if platform.system() == "Darwin":
            self.root.after(50, self.fix_macos_blank_window)

    def switch_language(self):
        self.lang = "zh" if self.lang == "en" else "en"
        self.t = TRANSLATIONS[self.lang]
        self.update_ui_strings()

    def update_ui_strings(self):
        self.root.title(self.t["title"])
        self.lbl_step1.config(text=self.t["step1"])
        self.btn_select.config(text=self.t["btn_select"])
        if not getattr(self, "input_paths", []):
            self.lbl_file.config(text=self.t["lbl_file"])
        self.lbl_step2.config(text=self.t["step2"])
        self.lbl_step3.config(text=self.t["step3"])
        
        self.lbl_alpha.config(text=self.t["alpha"])
        self.lbl_size.config(text=self.t["size"])
        self.lbl_step_x.config(text=self.t["step_x"])
        self.lbl_step_y.config(text=self.t["step_y"])
        
        self.btn_suggest.config(text=self.t["btn_suggest"])
        self.btn_run.config(text=self.t["btn_run"])
        
        self.btn_import.config(text=self.t["import_tmpl"])
        self.btn_export.config(text=self.t["export_tmpl"])
        self.btn_lang.config(text=self.t["lang_switch"])
        self.status_label.config(text=self.t["status_ready"])
        self.preview_label.config(text=self.t["preview_sync"])
        
        self.update_preview()

    def import_templates(self):
        path = filedialog.askopenfilename(filetypes=[("Text/JSON Files", "*.txt *.json"), ("All Files", "*.*")])
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.templates.update(data)
                self.combo.config(values=list(self.templates.keys()))
                self.set_status(f"Imported from {os.path.basename(path)}", "green")
            except Exception as e:
                messagebox.showerror("Import Error", f"Failed to import:\n{e}")

    def export_templates(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text File", "*.txt"), ("JSON File", "*.json")])
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(self.templates, f, ensure_ascii=False, indent=4)
                self.set_status(f"Exported to {os.path.basename(path)}", "green")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export:\n{e}")

    def fix_macos_blank_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        if w <= 1 or h <= 1:
            w, h = 1300, 950
        self.root.geometry(f"{w}x{h+1}")
        self.root.update_idletasks()
        self.root.geometry(f"{w}x{h}")

    def setup_ui(self):
        try:
            ttk.Style().theme_use('aqua')
        except Exception:
            pass
            
        self.main_container = ttk.Frame(self.root)
        self.main_container.pack(side="top", expand=True, fill="both")

        sidebar = ttk.Frame(self.main_container, width=420, padding=25)
        sidebar.pack(side="left", fill="y")

        # Top Bar (Lang Switch)
        top_bar = ttk.Frame(sidebar)
        top_bar.pack(fill="x", pady=(0, 10))
        self.btn_lang = ttk.Button(top_bar, text="Lang", command=self.switch_language)
        self.btn_lang.pack(side="right")

        self.lbl_step1 = ttk.Label(sidebar, text="STEP 1", font=("Arial", 10, "bold"))
        self.lbl_step1.pack(anchor="w")
        self.btn_select = ttk.Button(sidebar, text="Select File", command=self.select_file)
        self.btn_select.pack(fill="x", pady=5)
        self.lbl_file = ttk.Label(sidebar, text="None", foreground="gray", font=("Arial", 9))
        self.lbl_file.pack(pady=(0, 10))

        tmpl_frame = ttk.Frame(sidebar)
        tmpl_frame.pack(fill="x", pady=5)
        self.template_var = tk.StringVar(value=list(self.templates.keys())[0])
        self.combo = ttk.Combobox(tmpl_frame, textvariable=self.template_var, values=list(self.templates.keys()), state="readonly")
        self.combo.pack(side="left", fill="x", expand=True)
        self.combo.bind("<<ComboboxSelected>>", self.apply_template)
        
        btn_tmpl_opts = ttk.Frame(sidebar)
        btn_tmpl_opts.pack(fill="x", pady=2)
        self.btn_import = ttk.Button(btn_tmpl_opts, text="Import", command=self.import_templates)
        self.btn_import.pack(side="left", expand=True, fill="x", padx=(0, 2))
        self.btn_export = ttk.Button(btn_tmpl_opts, text="Export", command=self.export_templates)
        self.btn_export.pack(side="left", expand=True, fill="x", padx=(2, 0))

        self.lbl_step2 = ttk.Label(sidebar, text="STEP 2", font=("Arial", 10, "bold"))
        self.lbl_step2.pack(anchor="w", pady=(10, 0))
        self.txt_content = tk.Text(sidebar, height=4, width=40, font=("Arial", 10), bd=1, relief="solid", bg="white", fg="black", insertbackground="black")
        self.txt_content.insert("1.0", self.templates[self.template_var.get()]["text"])
        self.txt_content.pack(pady=5)
        self.txt_content.bind("<KeyRelease>", lambda e: self.update_preview())

        self.lbl_step3 = ttk.Label(sidebar, text="STEP 3", font=("Arial", 10, "bold"))
        self.lbl_step3.pack(anchor="w", pady=(15, 5))
        self.alpha_scale, self.lbl_alpha = self.create_slider(sidebar, "alpha", 0.0, 1.0, 0.12, 0.01)
        self.size_scale, self.lbl_size = self.create_slider(sidebar, "size", 6, 50, 11, 1)

        ttk.Frame(sidebar, height=1).pack(fill="x", pady=15)
        self.step_x_scale, self.lbl_step_x = self.create_slider(sidebar, "step_x", 80, 1500, 300, 1)
        self.step_y_scale, self.lbl_step_y = self.create_slider(sidebar, "step_y", 80, 1500, 300, 1)

        self.btn_suggest = ttk.Button(sidebar, text="Suggest", command=self.reset_to_suggested)
        self.btn_suggest.pack(fill="x", pady=15)

        self.btn_run = ttk.Button(sidebar, text="Run", command=self.start_processing_thread)
        self.btn_run.pack(side="bottom", fill="x")

        self.preview_area = ttk.Frame(self.main_container)
        self.preview_area.pack(side="right", expand=True, fill="both")
        self.preview_label = ttk.Label(self.preview_area, text="Sync...", font=("Arial", 10))
        self.preview_label.pack(pady=10)
        
        self.canvas_preview = tk.Canvas(self.preview_area, width=500, height=750, bg="white", highlightthickness=1)
        self.canvas_preview.pack(pady=10)

        self.status_frame = ttk.Frame(self.root, height=30, relief="sunken")
        self.status_frame.pack(side="bottom", fill="x")
        self.status_label = ttk.Label(self.status_frame, text="Ready", font=("Arial", 9))
        self.status_label.pack(side="left", padx=10)

    def create_slider(self, parent, key, start, end, default, res):
        lbl = ttk.Label(parent, text=self.t[key])
        lbl.pack(anchor="w")
        scale = tk.Scale(parent, from_=start, to=end, resolution=res, orient="horizontal", command=lambda e: self.update_preview())
        scale.set(default); scale.pack(fill="x", pady=(0, 5))
        return scale, lbl

    def set_status(self, message, color="black"):
        colors = {"red": "#e74c3c", "green": "#27ae60", "blue": "#3498db", "black": "#2c3e50"}
        self.status_label.config(text=f"{message}", foreground=colors.get(color, color))
        self.root.update_idletasks()

    def select_file(self, paths=None):
        if not paths: paths = filedialog.askopenfilenames()
        if paths:
            if isinstance(paths, str): paths = [paths]
            self.input_paths = list(paths)
            if not self.input_paths: return
            
            first_path = self.input_paths[0]
            if len(self.input_paths) == 1:
                self.lbl_file.config(text=f"{os.path.basename(first_path)}", foreground="#2ecc71")
            else:
                self.lbl_file.config(text=f"{os.path.basename(first_path)} + {len(self.input_paths)-1} more", foreground="#2ecc71")
                
            try:
                if first_path.lower().endswith(".pdf"):
                    reader = PdfReader(first_path); page = reader.pages[0]
                    self.doc_width, self.doc_height = float(page.mediabox.width), float(page.mediabox.height)
                else:
                    with Image.open(first_path) as img: self.doc_width, self.doc_height = img.size
                self.update_canvas_ratio(); self.update_preview()
                self.set_status(f'{self.t["status_file_loaded"]} ({int(self.doc_width)}x{int(self.doc_height)})', "green")
            except Exception as e: self.set_status(f'{self.t["status_error"]}{str(e)}', "red")

    def update_canvas_ratio(self):
        max_h = 750; ratio = self.doc_width / self.doc_height
        new_h, new_w = max_h, max_h * ratio
        if new_w > 650: new_w, new_h = 650, 650 / ratio
        self.canvas_preview.config(width=int(new_w), height=int(new_h))
        self.preview_label.config(text=f"{int(self.doc_width)} x {int(self.doc_height)}")

    def apply_template(self, event):
        tmpl = self.templates[self.template_var.get()]
        self.txt_content.delete("1.0", tk.END); self.txt_content.insert("1.0", tmpl["text"])
        self.alpha_scale.set(tmpl["alpha"]); self.size_scale.set(tmpl["size"])
        self.reset_to_suggested()

    def reset_to_suggested(self):
        text, size = self.txt_content.get("1.0", "end-1c"), self.size_scale.get()
        sx, sy = get_suggested_steps(text, size)
        self.step_x_scale.set(int(sx)); self.step_y_scale.set(int(sy)); self.update_preview()

    def update_preview(self):
        """【最終修正】同步座標系統與縮放比，徹底解決預覽重疊"""
        self.canvas_preview.delete("all")
        text = self.txt_content.get("1.0", "end-1c")
        if not text.strip(): return

        alpha, size = self.alpha_scale.get(), self.size_scale.get()
        sx, sy = self.step_x_scale.get(), self.step_y_scale.get()
        cw, ch = int(self.canvas_preview.cget("width")), int(self.canvas_preview.cget("height"))

        # 繪製畫布底色
        self.canvas_preview.create_rectangle(0, 0, cw, ch, fill="white", outline="#dddddd")
        self.canvas_preview.create_text(cw/2, ch/2, text=self.t["preview_text"], fill="#a0a0a0", font=("Arial", 26, "bold"))

        scale_ratio = ch / self.doc_height
        preview_font_size = max(1, int(size * scale_ratio))
        line_h = preview_font_size * 1.5 # 嚴格同步 1.5 倍行高

        gray = int(255-(255*alpha))
        color = f"#{gray:02x}{gray:02x}{gray:02x}"
        wrapped = textwrap.wrap(text, width=20)

        render_sx, render_sy = sx * scale_ratio, sy * scale_ratio

        # 檢測當前 Tkinter 版本是否支援 angle 參數 (舊版 macOS 系統 Python 預設為 Tk 8.5)
        supports_angle = True
        try:
            test_id = self.canvas_preview.create_text(0, 0, text="", angle=45)
            self.canvas_preview.delete(test_id)
        except tk.TclError:
            supports_angle = False

        # 計算偏移量以確保填滿旋轉後的畫布
        offset = max(cw, ch) * 0.8
        for x in range(int(-offset), int(cw + offset), int(render_sx)):
            for y in range(int(-offset), int(ch + offset), int(render_sy)):
                for i, line in enumerate(wrapped):
                    if supports_angle:
                        self.canvas_preview.create_text(
                            x, y + (i * line_h),
                            text=line, fill=color,
                            font=("Arial", preview_font_size, "bold"),
                            angle=45, anchor="nw"
                        )
                    else:
                        self.canvas_preview.create_text(
                            x, y + (i * line_h),
                            text=line, fill=color,
                            font=("Arial", preview_font_size, "bold"),
                            anchor="nw"
                        )

    def start_processing_thread(self):
        if not getattr(self, "input_paths", None): 
            self.set_status(self.t["status_error"], "red")
            return
            
        out_paths = []
        # If user selected multiple files, just append _marked
        if len(self.input_paths) > 1:
            for p in self.input_paths:
                base, ext = os.path.splitext(p)
                out_paths.append(f"{base}_marked.pdf")
        else:
            # Single file: still ask where to save
            out = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f"{os.path.splitext(os.path.basename(self.input_paths[0]))[0]}_marked.pdf")
            if not out: return
            out_paths = [out]
            
        self.btn_run.config(state="disabled", text=self.t["btn_run_processing"])
        threading.Thread(target=self.process_file, args=(self.input_paths, out_paths), daemon=True).start()

    def process_file(self, in_paths, out_paths):
        text, alpha, size = self.txt_content.get("1.0", "end-1c"), self.alpha_scale.get(), self.size_scale.get()
        sx, sy = self.step_x_scale.get(), self.step_y_scale.get()
        
        errors = []
        for idx, (in_path, out_path) in enumerate(zip(in_paths, out_paths)):
            temp = f"temp_render_{idx}.pdf"
            try:
                writer = PdfWriter()
                msg = f'{self.t["btn_run_processing"]} ({idx+1}/{len(in_paths)})'
                self.set_status(msg, "blue")
                
                if in_path.lower().endswith(".pdf"):
                    reader = PdfReader(in_path); total = len(reader.pages)
                    for i, page in enumerate(reader.pages):
                        self.set_status(f'{msg} - P{i+1}/{total}', "blue")
                        w, h = float(page.mediabox.width), float(page.mediabox.height)
                        wm = create_final_watermark(text, w, h, size, alpha, sx, sy)
                        page.merge_page(PdfReader(wm).pages[0]); writer.add_page(page)
                else:
                    img_pdf, w, h = self.image_to_pdf_buffer(in_path)
                    page = PdfReader(img_pdf).pages[0]
                    wm = create_final_watermark(text, w, h, size, alpha, sx, sy)
                    page.merge_page(PdfReader(wm).pages[0]); writer.add_page(page)
                    
                with open(temp, "wb") as f: writer.write(f)
                
                self.set_status(f'{msg} - Saving...', "blue")
                doc = fitz.open(temp)
                images = []
                for page in doc:
                    pix = page.get_pixmap(dpi=300)
                    img_data = pix.tobytes("png")
                    img = Image.open(BytesIO(img_data))
                    images.append(img.convert('RGB'))
                doc.close()
                images[0].save(out_path, save_all=True, append_images=images[1:], resolution=300.0, quality=85)
                
            except Exception as e: 
                errors.append(f"{os.path.basename(in_path)}: {str(e)}")
            finally:
                if os.path.exists(temp): 
                    try: os.remove(temp)
                    except: pass
                    
        if errors:
            self.set_status(f"Completed with {len(errors)} errors", "red")
            messagebox.showerror("Error", "\n".join(errors))
        else:
            self.set_status(f"Success: {len(in_paths)} file(s) processed", "green")
            messagebox.showinfo(self.t["msg_done_title"], self.t["msg_done"])
            
        self.btn_run.config(state="normal", text=self.t["btn_run"])

    def image_to_pdf_buffer(self, path):
        img = Image.open(path).convert('RGB'); w, h = img.size; buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h)); c.drawImage(path, 0, 0, w, h); c.showPage(); c.save(); buf.seek(0)
        return buf, w, h

if __name__ == "__main__":
    root = tk.Tk(); app = WatermarkApp(root)
    if len(sys.argv) > 1:
        import urllib.parse
        paths = []
        for arg in sys.argv[1:]:
            if arg.startswith("-psn"):
                continue
            p = arg.strip('\r\n')
            if p.startswith("file://"): p = urllib.parse.unquote(p[7:])
            paths.append(p)
        if paths:
            app.select_file(paths)
    root.mainloop()