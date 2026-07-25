import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
import sys
import textwrap
import threading
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from pypdf import PdfReader, PdfWriter
import fitz
from PIL import Image, ImageTk

# ================= 預設範本設定 =================

WATERMARK_TEMPLATES = {
    "租屋申請 (Rental App)": {"text": "FOR RENTAL APPLICATION PURPOSE ONLY\nNO OTHER USE AUTHORIZED\nDATE: 2026-03-24", "alpha": 0.10, "size": 10},
    "證件專用 (ID Copy)": {"text": "僅供身分驗證使用\n他用無效\nVOID IF COPIED", "alpha": 0.15, "size": 12},
    "機密文件 (Confidential)": {"text": "STRICTLY CONFIDENTIAL\nINTERNAL USE ONLY", "alpha": 0.08, "size": 11},
    "自定義 (Custom)": {"text": "NG ZHENG\nFor Rental Application Only\n[2026-Mar-24]", "alpha": 0.12, "size": 11}
}

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
    c.setFont("Helvetica-Bold", font_size)
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
        self.root.title("Secure Watermark Pro v2.8")
        self.root.geometry("1300x950")
        self.input_path = ""
        self.doc_width, self.doc_height = 595.0, 842.0
        self.setup_ui()
        self.reset_to_suggested()
        
    def setup_ui(self):
        self.main_container = tk.Frame(self.root)
        self.main_container.pack(side="top", expand=True, fill="both")

        sidebar = tk.Frame(self.main_container, width=420, bg="#ffffff", padx=25, pady=20)
        sidebar.pack(side="left", fill="y")

        tk.Label(sidebar, text="STEP 1: 檔案選擇", font=("Arial", 10, "bold"), bg="#ffffff").pack(anchor="w")
        self.btn_select = tk.Button(sidebar, text="開啟 PDF / 圖片", command=self.select_file, bg="#4a90e2", fg="white", relief="flat", pady=6)
        self.btn_select.pack(fill="x", pady=5)
        self.lbl_file = tk.Label(sidebar, text="尚未選取文件", bg="#ffffff", fg="gray", font=("Arial", 9))
        self.lbl_file.pack(pady=(0, 10))

        self.template_var = tk.StringVar(value="租屋申請 (Rental App)")
        combo = ttk.Combobox(sidebar, textvariable=self.template_var, values=list(WATERMARK_TEMPLATES.keys()), state="readonly")
        combo.pack(fill="x", pady=5)
        combo.bind("<<ComboboxSelected>>", self.apply_template)

        tk.Label(sidebar, text="STEP 2: 編輯內容", font=("Arial", 10, "bold"), bg="#ffffff").pack(anchor="w", pady=(10, 0))
        self.txt_content = tk.Text(sidebar, height=4, width=40, font=("Arial", 10), bd=1, relief="solid")
        self.txt_content.insert("1.0", WATERMARK_TEMPLATES["租屋申請 (Rental App)"]["text"])
        self.txt_content.pack(pady=5)
        self.txt_content.bind("<KeyRelease>", lambda e: self.update_preview())

        tk.Label(sidebar, text="STEP 3: 樣式調整", font=("Arial", 10, "bold"), bg="#ffffff").pack(anchor="w", pady=(15, 5))
        self.alpha_scale = self.create_slider(sidebar, "透明度 (Alpha):", 0.0, 1.0, 0.12, 0.01)
        self.size_scale = self.create_slider(sidebar, "字體大小 (Size):", 6, 50, 11, 1)
        
        tk.Frame(sidebar, height=1, bg="#eeeeee").pack(fill="x", pady=15)
        self.step_x_scale = self.create_slider(sidebar, "橫向間距 (X spacing):", 80, 1500, 300, 1)
        self.step_y_scale = self.create_slider(sidebar, "縱向間距 (Y spacing):", 80, 1500, 300, 1)

        self.btn_suggest = tk.Button(sidebar, text="自動優化間距 (防重疊)", command=self.reset_to_suggested, bg="#f39c12", fg="white", relief="flat", pady=8)
        self.btn_suggest.pack(fill="x", pady=15)

        self.btn_run = tk.Button(sidebar, text="執行扁平化儲存", command=self.start_processing_thread, bg="#27ae60", fg="white", font=("Arial", 12, "bold"), relief="flat", pady=12)
        self.btn_run.pack(side="bottom", fill="x")

        self.preview_area = tk.Frame(self.main_container, bg="#f5f6fa")
        self.preview_area.pack(side="right", expand=True, fill="both")
        self.preview_label = tk.Label(self.preview_area, text="預覽比例同步中...", bg="#f5f6fa", font=("Arial", 10))
        self.preview_label.pack(pady=10)
        self.canvas_preview = tk.Canvas(self.preview_area, width=500, height=750, bg="white", highlightthickness=1)
        self.canvas_preview.pack(pady=10)

        self.status_frame = tk.Frame(self.root, height=30, bg="#ecf0f1", bd=1, relief="sunken")
        self.status_frame.pack(side="bottom", fill="x")
        self.status_label = tk.Label(self.status_frame, text="準備就緒", bg="#ecf0f1", font=("Arial", 9))
        self.status_label.pack(side="left", padx=10)

    def create_slider(self, parent, label, start, end, default, res):
        tk.Label(parent, text=label, bg="#ffffff").pack(anchor="w")
        scale = tk.Scale(parent, from_=start, to=end, resolution=res, orient="horizontal", bg="#ffffff", command=lambda e: self.update_preview())
        scale.set(default); scale.pack(fill="x", pady=(0, 5))
        return scale

    def set_status(self, message, color="black"):
        colors = {"red": "#e74c3c", "green": "#27ae60", "blue": "#3498db", "black": "#2c3e50"}
        self.status_label.config(text=f"狀態: {message}", fg=colors.get(color, color))
        self.root.update_idletasks()

    def select_file(self, path=None):
        if not path: path = filedialog.askopenfilename()
        if path:
            self.input_path = path
            self.lbl_file.config(text=f"已選：{os.path.basename(path)}", fg="#2ecc71")
            try:
                if path.lower().endswith(".pdf"):
                    reader = PdfReader(path); page = reader.pages[0]
                    self.doc_width, self.doc_height = float(page.mediabox.width), float(page.mediabox.height)
                else:
                    with Image.open(path) as img: self.doc_width, self.doc_height = img.size
                self.update_canvas_ratio(); self.update_preview()
                self.set_status(f"檔案載入成功 ({int(self.doc_width)}x{int(self.doc_height)})", "green")
            except Exception as e: self.set_status(f"讀取失敗: {str(e)}", "red")

    def update_canvas_ratio(self):
        max_h = 750; ratio = self.doc_width / self.doc_height
        new_h, new_w = max_h, max_h * ratio
        if new_w > 650: new_w, new_h = 650, 650 / ratio
        self.canvas_preview.config(width=int(new_w), height=int(new_h))
        self.preview_label.config(text=f"同步比例：{int(self.doc_width)} x {int(self.doc_height)}")

    def apply_template(self, event):
        tmpl = WATERMARK_TEMPLATES[self.template_var.get()]
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
        self.canvas_preview.create_text(cw/2, ch/2, text="[ 文件內容預覽 ]", fill="#f5f5f5", font=("Arial", 26, "bold"))

        scale_ratio = ch / self.doc_height
        preview_font_size = max(1, int(size * scale_ratio))
        line_h = preview_font_size * 1.5 # 嚴格同步 1.5 倍行高
        
        gray = int(255-(255*alpha))
        color = f"#{gray:02x}{gray:02x}{gray:02x}"
        wrapped = textwrap.wrap(text, width=20)
        
        render_sx, render_sy = sx * scale_ratio, sy * scale_ratio
        
        # 計算偏移量以確保填滿旋轉後的畫布
        offset = max(cw, ch) * 0.8
        for x in range(int(-offset), int(cw + offset), int(render_sx)):
            for y in range(int(-offset), int(ch + offset), int(render_sy)):
                # 模擬 45 度分佈與 Anchor NW (與 PDF 座標對齊)
                for i, line in enumerate(wrapped):
                    self.canvas_preview.create_text(
                        x, y + (i * line_h), 
                        text=line, fill=color, 
                        font=("Arial", preview_font_size, "bold"), 
                        angle=45, anchor="nw"
                    )

    def start_processing_thread(self):
        if not self.input_path: self.set_status("錯誤: 未選檔案", "red"); return
        out = filedialog.asksaveasfilename(defaultextension=".pdf")
        if not out: return
        self.btn_run.config(state="disabled", text="處理中..."); threading.Thread(target=self.process_file, args=(out,), daemon=True).start()

    def process_file(self, out):
        text, alpha, size = self.txt_content.get("1.0", "end-1c"), self.alpha_scale.get(), self.size_scale.get()
        sx, sy = self.step_x_scale.get(), self.step_y_scale.get(); temp = "temp_render.pdf"
        try:
            writer = PdfWriter(); self.set_status("正在生成向量圖層...", "blue")
            if self.input_path.lower().endswith(".pdf"):
                reader = PdfReader(self.input_path); total = len(reader.pages)
                for i, page in enumerate(reader.pages):
                    self.set_status(f"處理中: {i+1}/{total}", "blue")
                    w, h = float(page.mediabox.width), float(page.mediabox.height)
                    wm = create_final_watermark(text, w, h, size, alpha, sx, sy)
                    page.merge_page(PdfReader(wm).pages[0]); writer.add_page(page)
            else:
                img_pdf, w, h = self.image_to_pdf_buffer(self.input_path)
                page = PdfReader(img_pdf).pages[0]
                wm = create_final_watermark(text, w, h, size, alpha, sx, sy)
                page.merge_page(PdfReader(wm).pages[0]); writer.add_page(page)
            with open(temp, "wb") as f: writer.write(f)
            self.set_status("正在進行 300 DPI 點陣化...", "blue")
            doc = fitz.open(temp)
            final = []
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                mode = "RGBA" if pix.alpha else "RGB"
                img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                final.append(img.convert('RGB'))
            doc.close()
            final[0].save(out, save_all=True, append_images=final[1:], resolution=300.0, quality=85)
            if os.path.exists(temp): os.remove(temp); self.set_status(f"成功: {os.path.basename(out)}", "green")
            messagebox.showinfo("完成", "文件已完成扁平化。")
        except Exception as e: self.set_status(f"錯誤: {str(e)}", "red")
        finally: self.btn_run.config(state="normal", text="執行扁平化儲存")

    def image_to_pdf_buffer(self, path):
        img = Image.open(path).convert('RGB'); w, h = img.size; buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h)); c.drawImage(path, 0, 0, w, h); c.showPage(); c.save(); buf.seek(0)
        return buf, w, h

if __name__ == "__main__":
    root = tk.Tk(); app = WatermarkApp(root)
    if len(sys.argv) > 1: app.select_file(sys.argv[1])
    root.mainloop()
