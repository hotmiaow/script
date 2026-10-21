# -*- coding: utf-8 -*-
"""
內建輕量 Web GUI 伺服器 (基於 Python 標準庫，零額外依賴，相容 Python 3.8 ~ 3.14+)
"""

import os
import sys
import json
import tempfile
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default

from .converter_engine import KafCliEngine
from .regex_tester import test_chapter_match, parse_filename_meta, auto_detect_best_rule
from .css_presets import CSS_PRESETS
from .config_manager import ConfigManager
from .gemma_engine import (
    GemmaEmbeddingClient, process_novel_with_gemma,
    NovelTextOrganizer, NovelCharacterExtractor
)
from .text_cleaner import remove_hard_breaks, clean_file_hard_breaks

_HTML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "index.html")

class KafWebHandler(BaseHTTPRequestHandler):
    engine = KafCliEngine()
    cfg_mgr = ConfigManager()

    def log_message(self, format, *args):
        # 簡化伺服器控制台 log
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ["/", "/index.html"]:
            if os.path.exists(_HTML_PATH):
                with open(_HTML_PATH, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "HTML template not found")
            return

        elif path == "/api/status":
            ver = self.engine.get_version()
            self.send_json({
                "ready": "已就緒" in ver,
                "version": ver,
                "cli_path": self.engine.cli_path
            })
            return

        elif path == "/api/css_presets":
            self.send_json(CSS_PRESETS)
            return

        elif path == "/api/download":
            qs = urllib.parse.parse_qs(parsed.query)
            target = qs.get("file", [""])[0]
            if target and os.path.isfile(target):
                filename = os.path.basename(target)
                size = os.path.getsize(target)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename*=UTF-8\'\'{urllib.parse.quote(filename)}')
                self.send_header("Content-Length", str(size))
                self.end_headers()
                with open(target, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                return
            else:
                self.send_error(404, "File not found")
                return

        elif path == "/api/gemma/status":
            query = urllib.parse.parse_qs(parsed.query)
            backend = query.get("backend", ["fast_local"])[0]
            model = query.get("model", ["google/embeddinggemma-2"])[0]
            url = query.get("url", ["http://localhost:11434"])[0]
            client = GemmaEmbeddingClient(backend=backend, model_name=model, ollama_url=url)
            self.send_json(client.check_status())
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/gemma/analyze":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))

            sample_text = data.get("sample_text", "")
            backend = data.get("backend", "fast_local")
            model = data.get("model_name", "google/embeddinggemma-2")
            url = data.get("ollama_url", "http://localhost:11434")
            max_chars = int(data.get("max_characters", 8))

            client = GemmaEmbeddingClient(backend=backend, model_name=model, ollama_url=url)
            organizer = NovelTextOrganizer(client)
            extractor = NovelCharacterExtractor(client)

            org_res = organizer.check_and_rearrange_text(
                sample_text,
                dedup_similarity_threshold=0.92,
                filter_noise=True,
                rearrange_chronological=True,
                auto_chapter_titles=True
            )
            char_res = extractor.extract_characters_and_worldview(
                org_res["cleaned_text"],
                max_characters=max_chars,
                book_title=data.get("book_title", "")
            )
            self.send_json({
                "success": True,
                "report": org_res["report"],
                "worldview": char_res["worldview"],
                "characters": char_res["characters"],
                "guide_html": char_res["guide_html"]
            })
            return

        elif path == "/api/auto_detect":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))

            sample_text = data.get("sample_text", "")
            fd, temp_p = tempfile.mkstemp(suffix=".txt", prefix="kaf_detect_")
            os.close(fd)
            try:
                with open(temp_p, "w", encoding="utf-8") as f:
                    f.write(sample_text)
                res = auto_detect_best_rule(filepath=temp_p)
                self.send_json(res)
            finally:
                if os.path.exists(temp_p):
                    os.remove(temp_p)
            return

        elif path == "/api/test_regex":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))

            sample_text = data.get("sample_text", "")
            # 寫入臨時檔案進行測試
            fd, temp_p = tempfile.mkstemp(suffix=".txt", prefix="kaf_test_")
            os.close(fd)
            try:
                with open(temp_p, "w", encoding="utf-8") as f:
                    f.write(sample_text)
                res = test_chapter_match(
                    filepath=temp_p,
                    match_regex=data.get("match_regex", ""),
                    volume_regex=data.get("volume_regex", ""),
                    exclude_regex=data.get("exclude_regex", ""),
                    max_len=data.get("max_len", 35),
                    scan_lines=3000
                )
                self.send_json(res)
            finally:
                if os.path.exists(temp_p):
                    os.remove(temp_p)
            return

        elif path == "/api/unwrap_preview":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))

            sample_text = data.get("text", "")
            match_regex = data.get("match_regex", "")
            orig_lines = len(sample_text.splitlines())
            cleaned = remove_hard_breaks(sample_text, header_regex_str=match_regex)
            new_lines = len(cleaned.splitlines())
            paragraphs_count = len([p for p in cleaned.split("\n\n") if p.strip()])
            self.send_json({
                "success": True,
                "cleaned_text": cleaned,
                "orig_lines": orig_lines,
                "new_lines": new_lines,
                "paragraphs_count": paragraphs_count,
                "summary": f"短行硬換行修復完成：原 {orig_lines} 行縮減為 {paragraphs_count} 個自然段落。"
            })
            return

        elif path == "/api/convert":
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                self.send_error(400, "Expected multipart/form-data")
                return

            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length)
            header_bytes = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
            msg = BytesParser(policy=default).parsebytes(header_bytes + raw_body)

            fields = {}
            file_data = b""
            upload_filename = "小說.txt"

            for part in msg.iter_parts():
                name = part.get_param("name", header="content-disposition")
                fn = part.get_filename()
                payload = part.get_payload(decode=True)
                if fn or name == "file":
                    file_data = payload
                    if fn:
                        upload_filename = fn
                elif name:
                    fields[name] = payload.decode("utf-8", "replace") if payload else ""

            if not file_data:
                self.send_json({"success": False, "message": "未收到小說檔案內容"}, code=400)
                return

            # 暫存書籍檔案於獨立臨時資料夾
            temp_dir = tempfile.mkdtemp(prefix="kaf_convert_")
            bookname = fields.get("bookname", "").strip()
            if not bookname:
                bookname = os.path.splitext(os.path.basename(upload_filename))[0]

            author = fields.get("author", "YSTYLE").strip() or "YSTYLE"

            upload_ext = os.path.splitext(upload_filename)[1].lower()
            if upload_ext not in [".txt", ".pdf"]:
                upload_ext = ".txt"
            novel_path = os.path.join(temp_dir, f"{bookname}{upload_ext}")
            with open(novel_path, "wb") as f:
                f.write(file_data)

            fmt = fields.get("format", "epub").strip()
            zh_conv = fields.get("zh_conversion", "s2tw").strip()
            book_type = fields.get("book_type", "auto").strip()
            pdf_mode = fields.get("pdf_mode", "auto").strip()
            align = fields.get("align", "center").strip()
            lang = fields.get("lang", "zh-TW").strip()
            try:
                indent = int(fields.get("indent", "2"))
            except ValueError:
                indent = 2

            bottom = fields.get("bottom", "1em").strip()
            line_height = fields.get("line_height", "1.85").strip()
            sep_chap = fields.get("separate_chapter_number") in ["true", "1", "True"]
            tips = fields.get("tips") in ["true", "1", "True"]
            match_regex = fields.get("match_regex", "").strip()
            vol_regex = fields.get("volume_regex", "").strip()
            excl_regex = fields.get("exclude_regex", "").strip()
            try:
                max_len = int(fields.get("max_title_len", "35"))
            except ValueError:
                max_len = 35
            unknow_t = fields.get("unknow_title", "章節正文").strip()
            cover_m = fields.get("cover_mode", "auto").strip()
            orly_col = fields.get("orly_color", "").strip()
            try:
                orly_i = int(fields.get("orly_idx", "-1"))
            except ValueError:
                orly_i = -1
            css_content = fields.get("custom_css_content", "").strip()

            opts = {
                "bookname": bookname,
                "author": author,
                "book_type": book_type,
                "pdf_mode": pdf_mode,
                "format": fmt,
                "zh_conversion": zh_conv,
                "align": align,
                "lang": lang,
                "indent": indent,
                "bottom": bottom,
                "line_height": line_height,
                "separate_chapter_number": sep_chap,
                "tips": tips,
                "match_regex": match_regex,
                "enable_volume": vol_regex != "false",
                "volume_regex": vol_regex,
                "exclude_regex": excl_regex,
                "max_title_len": max_len,
                "unknow_title": unknow_t,
                "cover_mode": cover_m,
                "orly_color": orly_col,
                "orly_idx": orly_i,
                "custom_css_content": css_content,
                "output_dir": temp_dir,
                "remove_hard_breaks": fields.get("remove_hard_breaks", "true") in ["true", "1", "True", True],
                "use_gemma_pipeline": fields.get("use_gemma_pipeline") in ["true", "1", "True", True],
                "enable_math": fields.get("enable_math", "true") in ["true", "1", "True", True],
                "gemma_backend": fields.get("gemma_backend", "fast_local"),
                "gemma_model": fields.get("gemma_model", "google/embeddinggemma-2"),
                "gemma_ollama_url": fields.get("gemma_ollama_url", "http://localhost:11434"),
                "gemma_dedup": True,
                "gemma_clean_noise": True,
                "gemma_rearrange": True,
                "gemma_auto_titles": True,
                "gemma_inject_guide": True,
                "gemma_max_characters": 8
            }

            logs = []
            def log_cb(msg):
                logs.append(msg)

            res = self.engine.run_conversion(
                input_file=novel_path,
                options=opts,
                log_callback=log_cb
            )

            # 搜尋生成之電子書檔案
            gen_files = []
            for fname in os.listdir(temp_dir):
                if any(fname.lower().endswith(ext) for ext in [".epub", ".mobi", ".azw3"]):
                    p = os.path.join(temp_dir, fname)
                    gen_files.append({
                        "filename": fname,
                        "path": p,
                        "size": os.path.getsize(p)
                    })

            res["logs"] = logs
            res["generated_files"] = gen_files
            self.send_json(res)
            return

        self.send_error(404, "Not Found")


def run_web_server(port: int = 8080, host: str = "0.0.0.0"):
    server = HTTPServer((host, port), KafWebHandler)
    url = f"http://localhost:{port}" if host == "0.0.0.0" else f"http://{host}:{port}"
    print(f"==================================================")
    print(f"kaf-cli 繁體中文 Web GUI 服務已啟動！")
    print(f"請在瀏覽器中開啟: {url}")
    print(f"==================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在關閉 Web 伺服器...")
        server.server_close()
