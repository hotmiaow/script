# -*- coding: utf-8 -*-
"""
kaf-cli 轉換引擎模組：負責執行檔定位、參數封裝、簡繁轉換串接、子行程控制與即時日誌串流
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from .zh_converter import convert_file, convert_text
from .regex_tester import auto_detect_best_rule, test_chapter_match
from .gemma_engine import process_novel_with_gemma
from .text_cleaner import clean_file_hard_breaks
from .pdf_extractor import is_pdf_file, extract_pdf_to_text, extract_pdf_metadata, extract_pdf_outline
from .cover_generator import generate_orly_cover
from .direct_pdf_converter import convert_pdf_to_epub_direct, check_direct_converter_dependencies

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
            return os.path.abspath(custom_path)
        if custom_path and sys.platform.startswith("win") and os.path.isfile(custom_path):
            return os.path.abspath(custom_path)

        # 2. 檢查目前指令碼目錄與工作目錄
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bin_names = ["kaf-cli.exe", "kaf-cli"] if sys.platform.startswith("win") else ["kaf-cli", "kaf-cli.exe"]

        for b in bin_names:
            p = os.path.join(script_dir, b)
            if os.path.isfile(p):
                return os.path.abspath(p)
            p_cwd = os.path.join(os.getcwd(), b)
            if os.path.isfile(p_cwd):
                return os.path.abspath(p_cwd)

        # 3. 檢查系統 PATH
        for b in bin_names:
            found = shutil.which(b)
            if found:
                return os.path.abspath(found)

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
        gen_cover = options.get("generated_cover_path", "").strip()
        cover_mode = options.get("cover_mode", "auto")
        if gen_cover and os.path.exists(gen_cover):
            args.extend(["-cover", gen_cover])
        elif cover_mode == "custom":
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

        # 確保保留原小說書名，避免暫存檔名稱影響生成的電子書檔案命名與元資料
        orig_bookname = options.get("bookname", "").strip()
        if not orig_bookname:
            options["bookname"] = Path(input_file).stem

        temp_files_to_clean = []
        actual_input_file = input_file

        try:
            # =========================================================================
            # [預處理] 📄 PDF 格式檢測與智慧文字抽取 / 伴生元資料大綱載入
            # =========================================================================
            if is_pdf_file(input_file):
                if progress_callback:
                    progress_callback(0.04, "[預處理] 📄 檢測到 PDF 文件，正在智慧抽取文字並解析大綱目錄...")
                if log_callback:
                    log_callback(f"[PDF] 📄 檢測到輸入為 PDF 格式: {input_file}")
                    log_callback("[PDF] 正在抽取文字內容並解析內嵌大綱、過濾頁首頁尾與跨頁斷行...")

                pdf_meta = extract_pdf_metadata(input_file)
                if not orig_bookname and pdf_meta.get("title"):
                    options["bookname"] = pdf_meta["title"]
                if not options.get("author") and pdf_meta.get("author"):
                    options["author"] = pdf_meta["author"]

                # 檢查是否啟用 PDF 直轉 EPUB 高保真模式
                pdf_mode = options.get("pdf_mode", "auto")
                is_direct_candidate = (
                    pdf_mode == "direct_epub" or
                    (pdf_mode == "auto" and options.get("book_type", "auto") in ["auto", "technical", "general"] and options.get("format") in ["epub", "all"])
                )
                has_html, has_pandoc, _ = check_direct_converter_dependencies()
                if is_direct_candidate and has_html and has_pandoc and options.get("format") in ["epub", "all"]:
                    if log_callback:
                        log_callback("[PDF] 🚀 啟用 PDF 直轉 EPUB 高保真排版模式（完整保留代碼/表格/插圖）...")
                    out_dir = options.get("output_dir") or os.path.dirname(os.path.abspath(input_file))
                    book_title = options.get("bookname") or Path(input_file).stem
                    target_epub = os.path.join(out_dir, f"{book_title}.epub")
                    direct_res = convert_pdf_to_epub_direct(
                        pdf_path=input_file,
                        output_epub_path=target_epub,
                        options=options,
                        log_callback=log_callback,
                        progress_callback=progress_callback
                    )
                    if direct_res.get("success"):
                        return direct_res
                    elif log_callback:
                        log_callback(f"[WARN] PDF 直轉模式未完成，降級為小說文字精排模式: {direct_res.get('error')}")

                # 準備持久化 metadata.json 輸出路徑（置於 PDF 來源資料夾中）
                pdf_dir = os.path.dirname(os.path.abspath(input_file))
                pdf_stem = os.path.splitext(os.path.basename(input_file))[0]
                companion_meta_path = os.path.join(pdf_dir, f"{pdf_stem}_metadata.json")

                fd_pdf, temp_pdf_txt = tempfile.mkstemp(suffix="_pdf_extracted.txt", prefix="kaf_pdf_")
                os.close(fd_pdf)
                temp_files_to_clean.append(temp_pdf_txt)

                pdf_res = extract_pdf_to_text(input_file, temp_pdf_txt)
                if not pdf_res.get("success"):
                    msg = f"PDF 抽取失敗: {pdf_res.get('error', '未知錯誤')}"
                    if log_callback: log_callback(f"[ERROR] {msg}")
                    return {"success": False, "message": msg}

                actual_input_file = temp_pdf_txt

                # 複製 metadata.json 至來源目錄，供持久保存與後續離線轉換使用
                if pdf_res.get("metadata_path") and os.path.exists(pdf_res["metadata_path"]):
                    try:
                        shutil.copy2(pdf_res["metadata_path"], companion_meta_path)
                    except Exception:
                        pass

                # 若 PDF 包含大綱，自動套用大綱推薦正則與標題最大長度
                outline_data = pdf_res.get("outline", {})
                if outline_data.get("has_outline"):
                    if not options.get("match_regex") or options["match_regex"] == "auto":
                        options["match_regex"] = outline_data["recommended_match_regex"]
                    options["max_title_len"] = max(int(options.get("max_title_len", 35)), outline_data.get("recommended_max_title_len", 65))
                    if not options.get("exclude_regex") and outline_data.get("recommended_exclude_regex"):
                        options["exclude_regex"] = outline_data["recommended_exclude_regex"]
                    # 避免在扁平多章節書籍中誤啟用預設分卷
                    if not options.get("volume_regex"):
                        options["enable_volume"] = False

                    if log_callback:
                        log_callback(f"[PDF] 📑 成功提取 PDF 內嵌大綱目錄 (共 {outline_data.get('total_items', 0)} 個節點，{len(outline_data.get('chapters', []))} 個核心章節)！")
                        log_callback(f"[PDF] 🧭 已自動套用大綱對齊章節規則，並輸出元資料檔: {os.path.basename(companion_meta_path)}")

                if log_callback:
                    log_callback(f"[PDF] ✨ 抽取完成！頁數: {pdf_res.get('pages', 0)} 頁，文字量: {pdf_res.get('characters', 0)} 字 (抽取方法: {pdf_res.get('method')})")
            else:
                # 檢測非 PDF 文件（如 TXT 小說）旁是否存在伴生元資料檔 (_metadata.json)
                input_stem = os.path.splitext(os.path.basename(input_file))[0]
                input_dir = os.path.dirname(os.path.abspath(input_file))
                possible_meta_paths = [
                    os.path.join(input_dir, f"{input_stem}_metadata.json"),
                    os.path.join(input_dir, f"{input_stem}.meta.json")
                ]
                for mp in possible_meta_paths:
                    if os.path.isfile(mp):
                        try:
                            with open(mp, "r", encoding="utf-8") as f_meta:
                                meta_data = json.load(f_meta)
                            if meta_data.get("recommended_match_regex"):
                                if not options.get("match_regex") or options["match_regex"] == "auto":
                                    options["match_regex"] = meta_data["recommended_match_regex"]
                                options["max_title_len"] = max(int(options.get("max_title_len", 35)), meta_data.get("recommended_max_title_len", 65))
                                if not options.get("exclude_regex") and meta_data.get("recommended_exclude_regex"):
                                    options["exclude_regex"] = meta_data["recommended_exclude_regex"]
                                if not orig_bookname and meta_data.get("title"):
                                    options["bookname"] = meta_data["title"]
                                if not options.get("author") and meta_data.get("author"):
                                    options["author"] = meta_data["author"]
                                if not options.get("volume_regex"):
                                    options["enable_volume"] = False
                                if log_callback:
                                    log_callback(f"[INFO] 📑 偵測到書籍元資料檔 ({os.path.basename(mp)})，已自動套用原 PDF 大綱章節規則: {options.get('bookname', '')}")
                                break
                        except Exception:
                            pass

            # =========================================================================
            # [步驟 1/4] 第一階段：🧹 文本排版預處理（短行硬換行修復、段落重組、字間空格清除）
            # =========================================================================
            if options.get("remove_hard_breaks", True):
                if progress_callback:
                    progress_callback(0.08, "[步驟 1/4] 🧹 正在修復短行硬換行與破碎段落...")
                if log_callback:
                    log_callback("[PIPELINE 1/4] 🧹 啟動短行硬換行修復（自動拼接斷句、修復每行過短與破碎段落）...")
                try:
                    fd_unw, temp_unw_txt = tempfile.mkstemp(suffix="_unwrap.txt", prefix="kaf_unw_")
                    os.close(fd_unw)
                    temp_files_to_clean.append(temp_unw_txt)
                    unw_res = clean_file_hard_breaks(
                        actual_input_file,
                        temp_unw_txt,
                        header_regex_str=options.get("match_regex", "")
                    )
                    if unw_res.get("success"):
                        actual_input_file = temp_unw_txt
                        if log_callback:
                            log_callback(f"[INFO] ✨ {unw_res['summary']}")
                except Exception as ex:
                    if log_callback:
                        log_callback(f"[WARN] 硬換行修復過程發生警告: {ex}")
            else:
                if log_callback:
                    log_callback("[PIPELINE 1/4] 🧹 短行硬換行修復已略過 (維持原文換行)")

            # =========================================================================
            # [步驟 2/4] 第二階段：🤖 Embedding Gemma 2 AI 語意增強與導讀生成（小說人物 / 通用書籍概念）
            # =========================================================================
            use_gemma = options.get("use_gemma_pipeline", True)
            if use_gemma:
                if progress_callback:
                    progress_callback(0.18, "[步驟 2/4] 🤖 Gemma 2: 正在執行語意分析、去重重排與導讀萃取...")
                if log_callback:
                    log_callback("[PIPELINE 2/4] 🤖 啟動 Embedding Gemma 2 AI 語意最佳化與知識導讀...")

                try:
                    fd_gem, temp_gemma_txt = tempfile.mkstemp(suffix="_gemma_opt.txt", prefix="kaf_gemma_")
                    os.close(fd_gem)
                    temp_files_to_clean.append(temp_gemma_txt)

                    gemma_res = process_novel_with_gemma(
                        input_filepath=actual_input_file,
                        output_filepath=temp_gemma_txt,
                        backend=options.get("gemma_backend", "fast_local"),
                        model_name=options.get("gemma_model", "google/embeddinggemma-2"),
                        ollama_url=options.get("gemma_ollama_url", "http://localhost:11434"),
                        dedup=options.get("gemma_dedup", True),
                        clean_noise=options.get("gemma_clean_noise", True),
                        rearrange=options.get("gemma_rearrange", True),
                        auto_titles=options.get("gemma_auto_titles", True),
                        inject_character_guide=options.get("gemma_inject_guide", True),
                        max_characters=options.get("gemma_max_characters", 10),
                        unwrap_hard_breaks=False,  # 步驟 1 已先行完成清洗
                        book_type=options.get("book_type", "auto"),
                        section_regex=options.get("match_regex", ""),
                        progress_callback=lambda r, m: progress_callback(0.18 + r * 0.12, f"[步驟 2/4] Gemma 2: {m}") if progress_callback else None
                    )
                    if gemma_res.get("success"):
                        actual_input_file = temp_gemma_txt
                        if log_callback:
                            log_callback(f"[INFO] ✨ Gemma 2 最佳化完成 ({gemma_res.get('book_type', '書籍')}): {gemma_res['report']['summary_text']}")
                            if gemma_res.get("book_type") == "story":
                                chars_summary = ", ".join([f"{c['name']}({c['role']})" for c in gemma_res.get('characters', [])[:6]])
                                if chars_summary:
                                    log_callback(f"[INFO] 👥 登場角色萃取: {chars_summary}")
                            else:
                                domain_info = gemma_res.get("thesis_info", {})
                                if domain_info:
                                    log_callback(f"[INFO] 📚 領域主旨: 【{domain_info.get('domain')}】{domain_info.get('thesis', '')[:55]}...")
                                concepts_summary = ", ".join([f"{c['concept']}({c['importance']})" for c in gemma_res.get('concepts', [])[:6]])
                                if concepts_summary:
                                    log_callback(f"[INFO] 💡 核心概念萃取: {concepts_summary}")
                except Exception as ex:
                    if log_callback:
                        log_callback(f"[WARN] Gemma 2 最佳化過程發生警告，使用上一階段文本繼續: {ex}")
            else:
                if log_callback:
                    log_callback("[PIPELINE 2/4] 🤖 Gemma 2 語意最佳化已略過")

            # =========================================================================
            # [步驟 3/4] 第三階段：🔍 章節匹配檢驗與目錄規則融合
            # =========================================================================
            if progress_callback:
                progress_callback(0.32, "[步驟 3/4] 🔍 正在檢驗並融合最佳章節匹配規則...")
            if log_callback:
                log_callback("[PIPELINE 3/4] 🔍 執行章節匹配與目錄檢驗 (Matching Chapters)...")

            current_match = options.get("match_regex", "").strip()
            guide_match_pattern = r"^\s*第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節集]"
            if not current_match:
                det = auto_detect_best_rule(actual_input_file)
                if det.get("regex"):
                    current_match = det["regex"]
                    options["match_regex"] = current_match
                    options["max_title_len"] = max(int(options.get("max_title_len", 35)), int(det.get("max_len", 35)))

            if current_match and "第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節" not in current_match:
                options["match_regex"] = f"(?:{current_match}|{guide_match_pattern})"
                options["max_title_len"] = max(int(options.get("max_title_len", 35)), 65)

            # 若啟用繁簡轉換，將 match_regex 同步繁體化並融合成雙向匹配正則，確保轉換後章節可被 kaf-cli 命中
            zh_mode = options.get("zh_conversion", "s2tw")
            if zh_mode in ["s2tw", "s2hk", "s2t"] and options.get("match_regex"):
                tw_regex = convert_text(options["match_regex"], mode=zh_mode)
                if tw_regex != options["match_regex"]:
                    options["match_regex"] = f"(?:{options['match_regex']}|{tw_regex})"

            # 檢驗章節匹配數量
            test_res = test_chapter_match(
                filepath=actual_input_file,
                match_regex=options.get("match_regex", ""),
                volume_regex=options.get("volume_regex", ""),
                exclude_regex=options.get("exclude_regex", ""),
                max_len=options.get("max_title_len", 65),
                scan_lines=5000
            )
            found_chapters = test_res.get("chapters_found", 0)
            if log_callback:
                log_callback(f"[INFO] 成功匹配 {found_chapters} 個章節 (規則: {options.get('match_regex') or '自動識別'}, 標題上限: {options.get('max_title_len')} 字)")

            # =========================================================================
            # [步驟 4/4] 第四階段：📖 簡繁轉換處理與 kaf-cli 電子書編譯
            # =========================================================================
            zh_mode = options.get("zh_conversion", "s2tw")
            if zh_mode in ["s2tw", "s2hk", "s2t"]:
                if progress_callback:
                    progress_callback(0.42, f"[步驟 4/4] 📖 正在將小說內文轉為臺灣正體 ({zh_mode})...")
                if log_callback:
                    log_callback(f"[PIPELINE 4/4] 📖 正在將小說內文簡體轉為臺灣繁體 ({zh_mode})...")

                # 同步將書名與作者繁體化
                if options.get("bookname"):
                    options["bookname"] = convert_text(options["bookname"], mode=zh_mode)
                if options.get("author"):
                    options["author"] = convert_text(options["author"], mode=zh_mode)

                # 建立臨時繁體 txt 檔案
                fd, temp_txt = tempfile.mkstemp(suffix="_traditional.txt", prefix="kaf_tw_")
                os.close(fd)
                temp_files_to_clean.append(temp_txt)

                convert_file(actual_input_file, temp_txt, mode=zh_mode)
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

            # 2.5 封面處理：若指定 orly 模式，使用本地智慧自適應排版引擎產生封面（徹底解決標題過長被截斷問題）
            cover_mode = options.get("cover_mode", "auto")
            if cover_mode == "orly":
                try:
                    fd_cov, temp_cov = tempfile.mkstemp(suffix="_orly_cover.png", prefix="kaf_cov_")
                    os.close(fd_cov)
                    temp_files_to_clean.append(temp_cov)

                    cov_title = options.get("bookname") or Path(input_file).stem
                    cov_author = options.get("author", "")
                    cov_color = options.get("orly_color", "")
                    cov_idx = options.get("orly_idx", -1)

                    generate_orly_cover(
                        book_title=cov_title,
                        author=cov_author,
                        color=cov_color,
                        animal_idx=cov_idx,
                        output_path=temp_cov
                    )
                    options["generated_cover_path"] = temp_cov
                    if log_callback:
                        log_callback(f"[COVER] 🎨 本地智慧自適應封面生成完成（標題全文字級保護）: {temp_cov}")
                except Exception as ex_cov:
                    if log_callback:
                        log_callback(f"[WARN] 本地封面生成異常，將嘗試使用 kaf-cli 預設機制: {ex_cov}")

            # 3. 構建命令列
            cmd = self.build_command_args(actual_input_file, options, temp_css_path=temp_css_path)
            cmd_str = " ".join([f'"{c}"' if " " in c else c for c in cmd])
            
            if log_callback:
                log_callback(f"[CMD] 執行指令: {cmd_str}")

            if progress_callback:
                progress_callback(0.55, "[步驟 4/4] 📖 正在呼叫 kaf-cli 編譯生成電子書...")

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
                        progress_callback(0.70, "[步驟 4/4] 📖 正在生成 EPUB 電子書...")
                    elif "正在生成azw3" in stripped and progress_callback:
                        progress_callback(0.85, "[步驟 4/4] 📖 正在生成 AZW3 電子書...")
                    elif "正在生成mobi" in stripped and progress_callback:
                        progress_callback(0.90, "[步驟 4/4] 📖 正在生成 MOBI 電子書...")
                    elif "转换完成" in stripped and progress_callback:
                        progress_callback(1.0, "[步驟 4/4] ✓ 電子書轉換完成！")

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
