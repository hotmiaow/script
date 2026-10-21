# -*- coding: utf-8 -*-
"""
kaf-cli 轉換引擎模組：負責執行檔定位、參數封裝、簡繁轉換串接、子行程控制與即時日誌串流
"""

import os
import sys
import shutil
import tempfile
import subprocess
import time
from typing import Dict, Any, List, Optional, Callable
from .zh_converter import convert_file

class KafCliEngine:
    def __init__(self, custom_cli_path: str = ""):
        self.cli_path = self.locate_cli(custom_cli_path)
        self.current_process: Optional[subprocess.Popen] = None
        self._is_cancelled = False

    @staticmethod
    def locate_cli(custom_path: str = "") -> str:
        """
        智慧搜尋 kaf-cli 或 kaf-cli.exe 執行檔
        """
        # 1. 檢查使用者自訂路徑
        if custom_path and os.path.isfile(custom_path) and os.access(custom_path, os.X_OK):
            return custom_path
        if custom_path and sys.platform.startswith("win") and os.path.isfile(custom_path):
            return custom_path

        # 2. 檢查目前指令碼目錄與工作目錄
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bin_names = ["kaf-cli.exe", "kaf-cli"] if sys.platform.startswith("win") else ["kaf-cli", "kaf-cli.exe"]

        for b in bin_names:
            p = os.path.join(script_dir, b)
            if os.path.isfile(p):
                return p
            p_cwd = os.path.join(os.getcwd(), b)
            if os.path.isfile(p_cwd):
                return p_cwd

        # 3. 檢查系統 PATH
        for b in bin_names:
            found = shutil.which(b)
            if found:
                return found

        return ""

    def get_version(self) -> str:
        """
        獲取 kaf-cli 版本資訊
        """
        if not self.cli_path or not os.path.exists(self.cli_path):
            return "未檢測到 kaf-cli 執行檔"
        try:
            res = subprocess.run(
                [self.cli_path, "-h"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            out = res.stdout + res.stderr
            if "Usage of" in out:
                return "已就緒 (v1.3.16)"
            return "已就緒"
        except Exception as e:
            return f"檢測失敗: {str(e)}"

    def build_command_args(
        self,
        input_file: str,
        options: Dict[str, Any],
        temp_css_path: Optional[str] = None
    ) -> List[str]:
        """
        依據選項構建 kaf-cli 命令列參數清單
        """
        args = [self.cli_path]

        # 1. 檔案與書名、作者
        args.extend(["-filename", input_file])
        
        bookname = options.get("bookname", "").strip()
        if bookname:
            args.extend(["-bookname", bookname])

        author = options.get("author", "").strip()
        if author:
            args.extend(["-author", author])

        # 2. 格式
        fmt = options.get("format", "all").strip().lower()
        if fmt in ["all", "epub", "mobi", "azw3"]:
            args.extend(["-format", fmt])

        # 3. 輸出路徑
        out_path = options.get("out", "").strip()
        if out_path:
            # 去除可能帶的副檔名，kaf-cli 會自動加 .epub/.mobi/.azw3
            for ext in [".epub", ".mobi", ".azw3"]:
                if out_path.lower().endswith(ext):
                    out_path = out_path[:-len(ext)]
            args.extend(["-out", out_path])

        # 4. 語言
        lang = options.get("lang", "zh-TW").strip()
        if lang:
            args.extend(["-lang", lang])

        # 5. 排版樣式
        align = options.get("align", "center").strip()
        if align in ["center", "left", "right"]:
            args.extend(["-align", align])

        indent = options.get("indent", 2)
        args.extend(["-indent", str(indent)])

        bottom = options.get("bottom", "1em").strip()
        if bottom:
            args.extend(["-bottom", bottom])

        line_height = options.get("line_height", "1.5rem").strip()
        if line_height:
            args.extend(["-line-height", line_height])

        if options.get("separate_chapter_number", False):
            args.append("-separate-chapter-number")

        tips = options.get("tips", True)
        if not tips:
            args.append("-tips=false")

        # 6. 內嵌字型
        font_path = options.get("font_path", "").strip()
        if font_path and os.path.exists(font_path):
            args.extend(["-font", font_path])

        # 7. 自訂 CSS
        css_file = temp_css_path or options.get("custom_css_file", "").strip()
        if css_file and os.path.exists(css_file):
            args.extend(["-custom-css-file", css_file])

        # 8. 封面設定
        cover_mode = options.get("cover_mode", "auto")
        if cover_mode == "custom":
            custom_cover = options.get("custom_cover_path", "").strip()
            if custom_cover and os.path.exists(custom_cover):
                args.extend(["-cover", custom_cover])
        elif cover_mode == "orly":
            args.extend(["-cover", "orly"])
            orly_color = options.get("orly_color", "").strip()
            if orly_color:
                args.extend(["-cover-orly-color", orly_color])
            orly_idx = options.get("orly_idx", -1)
            if orly_idx is not None and orly_idx >= 0:
                args.extend(["-cover-orly-idx", str(orly_idx)])

        # 9. 章節與分卷正則匹配
        match_regex = options.get("match_regex", "").strip()
        if match_regex:
            args.extend(["-match", match_regex])

        enable_volume = options.get("enable_volume", True)
        if not enable_volume:
            args.extend(["-volume-match", "false"])
        else:
            vol_regex = options.get("volume_regex", "").strip()
            if vol_regex:
                args.extend(["-volume-match", vol_regex])

        exclude_regex = options.get("exclude_regex", "").strip()
        if exclude_regex:
            args.extend(["-exclude", exclude_regex])

        max_len = options.get("max_title_len", 35)
        args.extend(["-max", str(max_len)])

        unknow_title = options.get("unknow_title", "章節正文").strip()
        if unknow_title:
            args.extend(["-unknow-title", unknow_title])

        return args

    def cancel(self):
        """
        中斷當前進行中的轉換
        """
        self._is_cancelled = True
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                time.sleep(0.3)
                if self.current_process.poll() is None:
                    self.current_process.kill()
            except Exception:
                pass

    def run_conversion(
        self,
        input_file: str,
        options: Dict[str, Any],
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """
        執行單一檔案轉換
        """
        self._is_cancelled = False
        start_time = time.time()

        if not self.cli_path or not os.path.exists(self.cli_path):
            msg = "錯誤：找不到 kaf-cli 執行檔，請先下載或設定執行檔路徑！"
            if log_callback: log_callback(f"[ERROR] {msg}")
            return {"success": False, "message": msg}

        if not os.path.exists(input_file):
            msg = f"錯誤：找不到輸入檔案 {input_file}"
            if log_callback: log_callback(f"[ERROR] {msg}")
            return {"success": False, "message": msg}

        temp_files_to_clean = []
        actual_input_file = input_file

        try:
            # 1. 簡繁轉換處理 (如果啟用)
            zh_mode = options.get("zh_conversion", "s2tw")
            if zh_mode in ["s2tw", "s2hk", "s2t"]:
                if progress_callback:
                    progress_callback(0.1, "正在將內文繁體化...")
                if log_callback:
                    log_callback(f"[INFO] 正在將小說內文簡體轉為繁體 ({zh_mode})...")

                # 建立臨時繁體 txt 檔案
                fd, temp_txt = tempfile.mkstemp(suffix="_traditional.txt", prefix="kaf_tw_")
                os.close(fd)
                temp_files_to_clean.append(temp_txt)

                convert_file(input_file, temp_txt, mode=zh_mode)
                actual_input_file = temp_txt
                if log_callback:
                    log_callback("[INFO] 內文繁體轉換完成！")

            # 2. 自訂 CSS 處理 (如果有自訂 CSS 內容)
            temp_css_path = None
            custom_css_content = options.get("custom_css_content", "").strip()
            if custom_css_content:
                fd_css, temp_css = tempfile.mkstemp(suffix=".css", prefix="kaf_style_")
                os.close(fd_css)
                temp_files_to_clean.append(temp_css)
                with open(temp_css, "w", encoding="utf-8") as f_css:
                    f_css.write(custom_css_content)
                temp_css_path = temp_css

            # 3. 構建命令列
            cmd = self.build_command_args(actual_input_file, options, temp_css_path=temp_css_path)
            cmd_str = " ".join([f'"{c}"' if " " in c else c for c in cmd])
            
            if log_callback:
                log_callback(f"[CMD] 執行指令: {cmd_str}")

            if progress_callback:
                progress_callback(0.3, "正在呼叫 kaf-cli 產生電子書...")

            # 4. 啟動行程
            # 設定工作目錄為來源檔案目錄或輸出目錄
            work_dir = os.path.dirname(os.path.abspath(input_file))
            if options.get("output_dir") and os.path.isdir(options.get("output_dir")):
                work_dir = options.get("output_dir")

            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=work_dir,
                bufsize=1,
                universal_newlines=True
            )

            # 5. 即時讀取輸出串流
            while True:
                if self._is_cancelled:
                    if log_callback:
                        log_callback("[WARN] 使用者取消了轉換操作！")
                    return {"success": False, "message": "已取消"}

                line = self.current_process.stdout.readline()
                if not line and self.current_process.poll() is not None:
                    break

                if line:
                    stripped = line.rstrip()
                    if log_callback:
                        log_callback(f"[KAF] {stripped}")
                    
                    if "正在生成epub" in stripped and progress_callback:
                        progress_callback(0.6, "正在生成 EPUB...")
                    elif "正在生成azw3" in stripped and progress_callback:
                        progress_callback(0.8, "正在生成 AZW3...")
                    elif "正在生成mobi" in stripped and progress_callback:
                        progress_callback(0.9, "正在生成 MOBI...")
                    elif "转换完成" in stripped and progress_callback:
                        progress_callback(1.0, "轉換完成！")

            ret_code = self.current_process.poll()
            elapsed = time.time() - start_time

            if ret_code == 0:
                msg = f"轉換成功！總耗時: {elapsed:.2f} 秒"
                if log_callback:
                    log_callback(f"[SUCCESS] {msg}")
                if progress_callback:
                    progress_callback(1.0, msg)
                return {"success": True, "message": msg, "elapsed": elapsed}
            else:
                msg = f"轉換失敗，結束代碼: {ret_code}"
                if log_callback:
                    log_callback(f"[ERROR] {msg}")
                return {"success": False, "message": msg}

        except Exception as e:
            msg = f"執行異常: {str(e)}"
            if log_callback:
                log_callback(f"[ERROR] {msg}")
            return {"success": False, "message": msg}

        finally:
            # 清理臨時檔案
            for temp_f in temp_files_to_clean:
                try:
                    if os.path.exists(temp_f):
                        os.remove(temp_f)
                except Exception:
                    pass
            self.current_process = None
