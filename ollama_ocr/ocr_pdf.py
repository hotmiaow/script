import os
import json
import threading
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import fitz  # PyMuPDF
from PIL import Image
import io
import ollama

class DeepSeekOCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DeepSeek-OCR PDF Toolkit")
        self.root.geometry("850x720")
        self.root.minsize(700, 550)

        self.pdf_path = ""
        self.is_processing = False

        self.setup_ui()
        self.update_prompt_preset() # Initialize prompt

    def setup_ui(self):
        # File Selection Area
        file_frame = ttk.LabelFrame(self.root, text=" 1. Select Document ", padding=10)
        file_frame.pack(fill="x", padx=15, pady=10)

        self.btn_browse = ttk.Button(file_frame, text="Browse PDF...", command=self.browse_pdf)
        self.btn_browse.pack(side="left", padx=5)

        self.lbl_file = ttk.Label(file_frame, text="No PDF file selected", wraplength=600)
        self.lbl_file.pack(side="left", fill="x", expand=True, padx=10)

        # Options and Settings Area
        options_frame = ttk.LabelFrame(self.root, text=" 2. Extraction Configurations ", padding=10)
        options_frame.pack(fill="x", padx=15, pady=5)

        # Language Config Row
        lang_frame = ttk.Frame(options_frame)
        lang_frame.pack(fill="x", pady=5)

        ttk.Label(lang_frame, text="Input Language:").pack(side="left", padx=5)
        self.input_lang_var = tk.StringVar(value="Mixed/Auto Detect")
        self.combo_input_lang = ttk.Combobox(lang_frame, textvariable=self.input_lang_var,
                                             values=["Mixed/Auto Detect", "Mainly Traditional Chinese", "Mainly Simplified Chinese", "Mainly English"],
                                             state="readonly", width=22)
        self.combo_input_lang.pack(side="left", padx=5)
        self.combo_input_lang.bind("<<ComboboxSelected>>", lambda e: self.update_prompt_preset())

        ttk.Label(lang_frame, text="Output Language:").pack(side="left", padx=15)
        self.output_lang_var = tk.StringVar(value="Keep Original")
        self.combo_output_lang = ttk.Combobox(lang_frame, textvariable=self.output_lang_var,
                                              values=["Keep Original", "Convert to Traditional Chinese", "Convert to Simplified Chinese"],
                                              state="readonly", width=25)
        self.combo_output_lang.pack(side="left", padx=5)
        self.combo_output_lang.bind("<<ComboboxSelected>>", lambda e: self.update_prompt_preset())

        # Prompt Editor
        ttk.Label(options_frame, text="System Directive / Prompt (You can manually edit this):").pack(anchor="w", pady=(10, 2))
        self.txt_prompt = tk.Text(options_frame, height=3, wrap="word")
        self.txt_prompt.pack(fill="x", pady=5)

        # Output Format Selector & Run Button Row
        control_subframe = ttk.Frame(options_frame)
        control_subframe.pack(fill="x", pady=(5, 0))

        ttk.Label(control_subframe, text="Output Format:").pack(side="left", padx=5)
        self.format_var = tk.StringVar(value="Markdown (.md)")
        combo_format = ttk.Combobox(control_subframe, textvariable=self.format_var,
                                     values=["Markdown (.md)", "HTML (.html)", "JSON (.json)"],
                                     state="readonly", width=15)
        combo_format.pack(side="left", padx=5)

        self.btn_run = ttk.Button(control_subframe, text="Execute Batch OCR", command=self.start_ocr_thread, state="disabled")
        self.btn_run.pack(side="right", padx=5)

        # Status Monitoring
        self.progress = ttk.Progressbar(self.root, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=15, pady=10)

        # Interactive Results Area
        results_frame = ttk.LabelFrame(self.root, text=" 3. Live OCR Transcripts ", padding=10)
        results_frame.pack(fill="both", expand=True, padx=15, pady=5)

        # Scrollable output log
        self.txt_output = tk.Text(results_frame, wrap="word", background="#f8f9fa")
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.txt_output.yview)
        self.txt_output.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.txt_output.pack(side="left", fill="both", expand=True)

    def update_prompt_preset(self):
        """Dynamically builds the base system prompt based on language constraints."""
        in_lang = self.input_lang_var.get()
        out_lang = self.output_lang_var.get()

        base_prompt = "Convert the document to clean text without any spatial layout coordinates, bounding boxes, or structure labels."

        if in_lang == "Mainly Traditional Chinese":
            base_prompt += " Note that the input text is primarily in Traditional Chinese."
        elif in_lang == "Mainly Simplified Chinese":
            base_prompt += " Note that the input text is primarily in Simplified Chinese."
        elif in_lang == "Mainly English":
            base_prompt += " Note that the input text is primarily in English."

        if out_lang == "Convert to Traditional Chinese":
            base_prompt += " Strictly render the final text output in Traditional Chinese (繁體中文)."
        elif out_lang == "Convert to Simplified Chinese":
            base_prompt += " Strictly render the final text output in Simplified Chinese (簡體中文)."
        else:
            base_prompt += " Keep the output text in its original language formatting."

        self.txt_prompt.delete("1.0", tk.END)
        self.txt_prompt.insert("1.0", base_prompt)

    def browse_pdf(self):
        file_selected = filedialog.askopenfilename(
            title="Select Source Document",
            filetypes=[("PDF Documents", "*.pdf")]
        )
        if file_selected:
            self.pdf_path = file_selected
            self.lbl_file.config(text=os.path.basename(file_selected))
            self.btn_run.config(state="normal")
            self.log_message(f"[System] Target loaded: {file_selected}\nReady to process.")

    def log_message(self, text):
        self.txt_output.insert(tk.END, text + "\n")
        self.txt_output.see(tk.END)

    def start_ocr_thread(self):
        if not self.pdf_path or self.is_processing:
            return

        self.is_processing = True
        self.btn_browse.config(state="disabled")
        self.btn_run.config(state="disabled")
        self.txt_output.delete("1.0", tk.END)

        threading.Thread(target=self.process_pdf, daemon=True).start()

    def process_pdf(self):
        try:
            doc = fitz.open(self.pdf_path)
            total_pages = len(doc)
            self.progress["maximum"] = total_pages

            prompt_str = self.txt_prompt.get("1.0", "end-1c").strip()
            output_format = self.format_var.get()

            self.log_message(f"[Processing] Parsing {total_pages} total pages using deepseek-ocr...\n")

            extracted_data = []
            compiled_text = ""

            for index, page in enumerate(doc):
                page_num = index + 1
                self.log_message(f"--- Processing Page {page_num}/{total_pages} ---")

                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes("png")

                response = ollama.generate(
                    model="deepseek-ocr",
                    prompt=prompt_str,
                    images=[img_data],
                    stream=False
                )

                page_text = response.get("response", "").strip()

                # Clean up bounding box anomalies if leaked by the model
                page_text = re.sub(r'\[\[\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\]\]', '', page_text)
                page_text = re.sub(r'(text|title|heading|table)\s*(?=\n|$)', '', page_text, flags=re.IGNORECASE)
                page_text = re.sub(r'\n{3,}', '\n\n', page_text)

                self.log_message(page_text + "\n")

                extracted_data.append({
                    "page": page_num,
                    "content": page_text
                })

                compiled_text += f"## Page {page_num}\n\n{page_text}\n\n"

                self.root.after(0, self.update_progress, page_num)

            # Save Output
            base_name, _ = os.path.splitext(self.pdf_path)

            if "JSON" in output_format:
                save_path = base_name + "_ocr.json"
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(extracted_data, f, indent=2, ensure_ascii=False)
            elif "HTML" in output_format:
                save_path = base_name + "_ocr.html"
                html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>OCR Output Document</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.7; max-width: 850px; margin: 40px auto; padding: 0 20px; color: #2c3e50; background-color: #fafafa; }
        h1, h2 { color: #1a252f; border-bottom: 2px solid #eef2f3; padding-bottom: 8px; margin-top: 30px; }
        .page-block { margin-bottom: 30px; padding: 25px; border: 1px solid #e1e8ed; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
        .page-num { font-weight: 700; color: #3498db; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 1px; margin-bottom: 15px; border-bottom: 1px dashed #e1e8ed; padding-bottom: 5px; }
        p { margin-bottom: 1.2em; text-align: justify; }
    </style>
</head>
<body>
"""
                for item in extracted_data:
                    # Escape HTML specific characters safely
                    safe_content = item['content'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    # Convert paragraph gaps and line-breaks elegantly
                    formatted_content = safe_content.replace('\n\n', '</p><p>').replace('\n', '<br>')
                    html_content += f'<div class="page-block">\n<div class="page-num">Page {item["page"]}</div>\n<p>{formatted_content}</p>\n</div>\n'
                html_content += "</body>\n</html>"

                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
            else:
                save_path = base_name + "_ocr.md"
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(compiled_text)

            self.log_message(f"[Finished] File export complete: {save_path}")
            messagebox.showinfo("Success", f"OCR process finished successfully!\nExported to: {os.path.basename(save_path)}")

        except Exception as e:
            self.log_message(f"\n[Fatal Error] Operation halted: {str(e)}")
            messagebox.showerror("Execution Failure", f"An error occurred during extraction:\n{str(e)}")

        finally:
            self.is_processing = False
            self.btn_browse.config(state="normal")
            self.btn_run.config(state="normal")
            self.progress["value"] = 0

    def update_progress(self, val):
        self.progress["value"] = val

if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()
    if 'aqua' in style.theme_names():
        style.theme_use('aqua')

    app = DeepSeekOCRApp(root)
    root.mainloop()