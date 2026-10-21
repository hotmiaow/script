# -*- coding: utf-8 -*-
"""
pdf_extractor.py: PDF 文字書籍擷取與排版預處理模組
支援：
1. 自動檢測與解析包含純文字之 PDF 文件
2. 提取 PDF 書名、作者、頁數等元資料 (Metadata)
3. 提取 PDF 內部目錄大綱 (Outline / Bookmarks)
4. 多層後端文字提取：
   - Poppler pdftotext (優先，高品質、完美編碼與排版保持)
   - pypdf (次選，Python 原生套件)
   - 內建純 Python PDF 文字串流解析器 (零相依備援，離線即開即用)
5. 智慧 PDF 排版缺陷修復：
   - 跨頁重複頁眉 (Running Headers) 與頁腳 (Running Footers) 自動過濾
   - 獨立孤立頁碼 (Page Numbers) 清除
   - 英文跨行連字號 (Hyphenation) 拼接修復
   - 跨頁換頁符 (Form Feed \\f) 與自然段落平滑接續
"""

import os
import re
import sys
import zlib
import json
import shutil
import tempfile
import binascii
import subprocess
from typing import Dict, Any, List, Optional, Tuple, Set
from collections import Counter


def is_pdf_file(filepath: str) -> bool:
    """判斷給定路徑是否為 PDF 文件 (副檔名或檔案頭特徵檢驗)"""
    if not filepath or not os.path.isfile(filepath):
        return False
    if filepath.lower().endswith(".pdf"):
        return True
    try:
        with open(filepath, "rb") as f:
            header = f.read(1024)
            return b"%PDF-" in header
    except Exception:
        return False


def _decode_pdf_value(raw_bytes: bytes) -> str:
    """解碼 PDF 字面量字串或十六進制字串 (包含 UTF-16BE BOM、Hex 與 Octal 轉義)"""
    if not raw_bytes:
        return ""
    b = raw_bytes.strip()
    # 1. 處理十六進制字串 <feff0041...>
    if b.startswith(b"<") and b.endswith(b">"):
        hex_str = b[1:-1].strip().replace(b" ", b"").replace(b"\n", b"").replace(b"\r", b"")
        try:
            raw = binascii.unhexlify(hex_str)
            if raw.startswith(b"\xfe\xff"):
                return raw[2:].decode("utf-16-be", errors="replace").strip()
            return raw.decode("utf-8", errors="replace").strip()
        except Exception:
            pass
    if b.startswith(b"(") and b.endswith(b")"):
        b = b[1:-1]
    # 2. 處理 octal 轉義如 \376\377 或 \344\275\240
    def octal_repl(m):
        return bytes([int(m.group(1), 8)])
    try:
        b = re.sub(rb"\\([0-7]{1,3})", octal_repl, b)
    except Exception:
        pass
    b = b.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")

    # 3. 檢查 UTF-16BE BOM
    if b.startswith(b"\xfe\xff"):
        try:
            return b[2:].decode("utf-16-be", errors="replace").strip()
        except Exception:
            pass
    try:
        return b.decode("utf-8", errors="replace").strip()
    except Exception:
        return b.decode("latin1", errors="replace").strip()


def _decode_pdf_literal_str(raw_bytes: bytes) -> str:
    """向後相容包裝函式"""
    return _decode_pdf_value(raw_bytes)


def extract_pdf_metadata(filepath: str) -> Dict[str, Any]:
    """
    自 PDF 文件擷取標題、作者、頁數、主旨等元資料
    優先自 PDF 內部 /Info 物件字典直接精確解析（支援 UTF-16BE / Hex），
    並以 pdfinfo、qpdf 與檔名作為多層備援。
    """
    meta = {
        "title": "",
        "author": "",
        "pages": 0,
        "subject": "",
        "keywords": "",
        "producer": "",
        "creator": ""
    }
    if not os.path.exists(filepath):
        return meta

    file_size = os.path.getsize(filepath)

    # 1. 優先從 PDF 內部物件字典讀取 /Info 參照（最完整、原生編碼精確解碼）
    try:
        with open(filepath, "rb") as f:
            head = f.read(262144)
            if file_size > 262144:
                f.seek(max(0, file_size - 262144))
                tail = f.read(262144)
            else:
                tail = b""
            data_sample = head + tail

        # 找 /Info X Y R
        info_ref = re.search(rb'/Info\s+(\d+)\s+(\d+)\s+R', data_sample)
        info_bytes = b""
        if info_ref:
            obj_num = info_ref.group(1)
            gen_num = info_ref.group(2)
            obj_pattern = re.compile(rb'^(?:' + obj_num + rb')\s+' + gen_num + rb'\s+obj\s*(.*?)endobj', re.DOTALL | re.MULTILINE)
            m_obj = obj_pattern.search(data_sample)
            if not m_obj and file_size <= 25 * 1024 * 1024:
                with open(filepath, "rb") as f:
                    full_data = f.read()
                m_obj = obj_pattern.search(full_data)
            if m_obj:
                info_bytes = m_obj.group(1)

        if info_bytes:
            for key in ["Title", "Author", "Subject", "Keywords", "Creator", "Producer"]:
                m_val = re.search(rb'/' + key.encode() + rb'\s*(\(.*?\)|<[0-9a-fA-F\s]+>)', info_bytes, re.DOTALL)
                if m_val:
                    val_str = _decode_pdf_value(m_val.group(1))
                    if val_str:
                        meta[key.lower()] = val_str

        # 頁數讀取：從 /Type /Pages /Count 讀取
        m_pages = re.search(rb'/Type\s*/Pages.*?/Count\s+(\d+)', data_sample, re.DOTALL)
        if m_pages:
            try:
                meta["pages"] = int(m_pages.group(1).decode("ascii"))
            except Exception:
                pass
    except Exception:
        pass

    # 2. 備援：使用 pdfinfo 工具
    if not meta["title"] or not meta["author"] or not meta["pages"]:
        pdfinfo_path = shutil.which("pdfinfo")
        if pdfinfo_path:
            try:
                res = subprocess.run([pdfinfo_path, "-enc", "UTF-8", filepath], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            k = k.strip().lower()
                            v = v.strip()
                            if k == "title" and v and not meta["title"]:
                                meta["title"] = v
                            elif k == "author" and v and not meta["author"]:
                                meta["author"] = v
                            elif k == "pages" and v and not meta["pages"]:
                                try:
                                    meta["pages"] = int(v)
                                except ValueError:
                                    pass
            except Exception:
                pass

    # 3. 備援：若仍缺少頁數，檢查 qpdf --show-npages
    if not meta["pages"]:
        qpdf_path = shutil.which("qpdf")
        if qpdf_path:
            try:
                res = subprocess.run([qpdf_path, "--show-npages", filepath], capture_output=True, text=True, timeout=5)
                if res.returncode == 0 and res.stdout.strip().isdigit():
                    meta["pages"] = int(res.stdout.strip())
            except Exception:
                pass

    # 4. 若標題依然為空，從檔名推算 (去除 .pdf)
    if not meta["title"]:
        base = os.path.splitext(os.path.basename(filepath))[0]
        meta["title"] = base

    return meta


def extract_pdf_outline(filepath: str) -> Dict[str, Any]:
    """
    自 PDF 擷取內嵌書籤大綱目錄 (Outline / Bookmarks Tree)
    回傳字典包含：
    - has_outline: 是否包含目錄大綱
    - total_items: 大綱節點總數
    - outline_tree: 樹狀階層目錄 [{"title": str, "page": int, "level": int, "kids": [...]}]
    - flat_outline: 扁平清單 [{"title": str, "page": int, "level": int}]
    - chapters: 核心章節清單 (第 1、2 階層重要標題)
    - page_to_chapters: 頁碼對應之標題清單 {page_num: [title1, title2, ...]}
    - recommended_match_regex: 依據大綱結構推薦之 kaf-cli 章節匹配正則表達式
    - recommended_max_title_len: 建議之章節標題最大字數 (-max)
    """
    default_res = {
        "has_outline": False,
        "total_items": 0,
        "outline_tree": [],
        "flat_outline": [],
        "chapters": [],
        "page_to_chapters": {},
        "recommended_match_regex": "",
        "recommended_max_title_len": 35
    }
    if not os.path.exists(filepath):
        return default_res

    raw_tree = []

    # 1. 優先使用 qpdf 工具（極速 <40ms，原生效能穩定且支援任意複雜階層）
    qpdf_path = shutil.which("qpdf")
    if qpdf_path:
        try:
            res = subprocess.run([qpdf_path, "--json", "--json-key=outlines", filepath], capture_output=True, text=True, timeout=20)
            if res.returncode == 0 and res.stdout:
                data = json.loads(res.stdout)
                raw_outlines = data.get("outlines", [])
                if raw_outlines:
                    def parse_qpdf_node(node, level=1):
                        t = (node.get("title") or "").strip()
                        p = node.get("destpageposfrom1")
                        kids = [parse_qpdf_node(k, level + 1) for k in node.get("kids", [])]
                        return {"title": t, "page": p, "level": level, "kids": kids}
                    raw_tree = [parse_qpdf_node(n, 1) for n in raw_outlines]
        except Exception:
            pass

    # 2. 備援：若無 qpdf，使用純 Python 解析 /Outlines 物件
    if not raw_tree:
        try:
            with open(filepath, "rb") as f:
                content = f.read()

            page_objs = re.findall(rb'(\d+)\s+(\d+)\s+obj\s*<<[^>]*?/Type\s*/Page\b', content)
            page_map = {f"{m[0].decode()} {m[1].decode()} R": idx + 1 for idx, m in enumerate(page_objs)}

            root_m = re.search(rb'/Root\s+(\d+)\s+(\d+)\s+R', content)
            if root_m:
                r_num, r_gen = root_m.group(1), root_m.group(2)
                r_obj = re.search(rb'^' + r_num + rb'\s+' + r_gen + rb'\s+obj\s*(.*?)endobj', content, re.DOTALL | re.MULTILINE)
                if r_obj:
                    outlines_m = re.search(rb'/Outlines\s+(\d+)\s+(\d+)\s+R', r_obj.group(1))
                    if outlines_m:
                        out_num, out_gen = outlines_m.group(1), outlines_m.group(2)
                        out_obj = re.search(rb'^' + out_num + rb'\s+' + out_gen + rb'\s+obj\s*(.*?)endobj', content, re.DOTALL | re.MULTILINE)
                        if out_obj:
                            first_m = re.search(rb'/First\s+(\d+)\s+(\d+)\s+R', out_obj.group(1))
                            if first_m:
                                def parse_py_node(item_num, item_gen, level=1, visited=None):
                                    if visited is None: visited = set()
                                    ref_key = f"{item_num} {item_gen} R"
                                    if ref_key in visited: return None
                                    visited.add(ref_key)

                                    item_pattern = re.compile(rb'^' + item_num.encode() + rb'\s+' + item_gen.encode() + rb'\s+obj\s*(.*?)endobj', re.DOTALL | re.MULTILINE)
                                    m_item = item_pattern.search(content)
                                    if not m_item: return None
                                    idata = m_item.group(1)

                                    title = ""
                                    m_t = re.search(rb'/Title\s*(\(.*?\)|<[0-9a-fA-F\s]+>)', idata, re.DOTALL)
                                    if m_t:
                                        title = _decode_pdf_value(m_t.group(1))

                                    dest_page = None
                                    m_dest = re.search(rb'/Dest\s*\[\s*(\d+\s+\d+\s+R)', idata)
                                    if m_dest:
                                        d_ref = m_dest.group(1).decode("ascii")
                                        dest_page = page_map.get(d_ref)

                                    kids = []
                                    m_first = re.search(rb'/First\s+(\d+)\s+(\d+)\s+R', idata)
                                    if m_first:
                                        curr_k_num, curr_k_gen = m_first.group(1).decode("ascii"), m_first.group(2).decode("ascii")
                                        while curr_k_num:
                                            kn = parse_py_node(curr_k_num, curr_k_gen, level + 1, visited)
                                            if kn: kids.append(kn)
                                            k_pattern = re.compile(rb'^' + curr_k_num.encode() + rb'\s+' + curr_k_gen.encode() + rb'\s+obj\s*(.*?)endobj', re.DOTALL | re.MULTILINE)
                                            m_kobj = k_pattern.search(content)
                                            if m_kobj:
                                                m_next = re.search(rb'/Next\s+(\d+)\s+(\d+)\s+R', m_kobj.group(1))
                                                if m_next:
                                                    curr_k_num, curr_k_gen = m_next.group(1).decode("ascii"), m_next.group(2).decode("ascii")
                                                else:
                                                    break
                                            else:
                                                break

                                    return {"title": title, "page": dest_page, "level": level, "kids": kids}

                                curr_n, curr_g = first_m.group(1).decode("ascii"), first_m.group(2).decode("ascii")
                                while curr_n:
                                    node = parse_py_node(curr_n, curr_g, 1)
                                    if node: raw_tree.append(node)
                                    curr_pat = re.compile(rb'^' + curr_n.encode() + rb'\s+' + curr_g.encode() + rb'\s+obj\s*(.*?)endobj', re.DOTALL | re.MULTILINE)
                                    m_curr = curr_pat.search(content)
                                    if m_curr:
                                        m_next = re.search(rb'/Next\s+(\d+)\s+(\d+)\s+R', m_curr.group(1))
                                        if m_next:
                                            curr_n, curr_g = m_next.group(1).decode("ascii"), m_next.group(2).decode("ascii")
                                        else:
                                            break
                                    else:
                                        break
        except Exception:
            pass

    if not raw_tree:
        return default_res

    # 扁平化目錄
    def flatten_tree(nodes):
        res = []
        for n in nodes:
            res.append({"title": n["title"], "page": n["page"], "level": n["level"]})
            if n.get("kids"):
                res.extend(flatten_tree(n["kids"]))
        return res

    flat = flatten_tree(raw_tree)

    # 建立 page_to_chapters 字典
    page_to_chapters: Dict[int, List[str]] = {}
    for item in flat:
        p = item["page"]
        if p:
            page_to_chapters.setdefault(int(p), []).append(item["title"])

    # 擷取關鍵大章節（Level 1 和 Level 2）
    chapters = [it for it in flat if it["level"] <= 2]

    # 構建兼顧簡繁之最佳化 kaf-cli 匹配正則表達式
    # 1. 自動從大綱中提取非數字編號的結構型標題（如 版權信息、內容提要、推薦序、前言、後記、致謝等）
    detected_structural_titles = set()
    for it in flat:
        t = it["title"].strip()
        # 排除數字編號標題或過長標題
        if not re.search(r'^[0-9]+(?:\.[0-9]+)*|^第[0-9一二三四五六七八九十百千零〇两兩 ]+[章回节節卷部篇步讲講课課集幕场場辑輯]', t):
            if 2 <= len(t) <= 15:
                if any(k in t for k in ["版权", "版權", "提要", "序", "前言", "导言", "導言", "导读", "導讀", "致谢", "致謝", "后记", "後記", "结语", "結語", "附录", "附錄", "引言", "作者", "跋", "题记", "題記", "楔子", "尾声", "尾聲", "提示", "声明", "聲明"]):
                    detected_structural_titles.add(t)

    # 補充通用固定結構標題清單（當且僅當大綱中存在完整精確匹配時加入）
    common_fixed = [
        "版权信息", "版權信息", "内容提要", "內容提要", "导读", "導讀", "推荐序", "推薦序", "编者序", "自序", "原序", "序言", "跋", "目录", "目錄",
        "电子书提示", "電子書提示", "免责声明", "免責聲明", "献词", "獻詞", "引言",
        "致谢", "致謝", "关于作者", "關於作者", "注释", "註釋", "注釋",
        "前言", "导言", "導言", "后记", "後記", "结语", "結語", "附录", "附錄"
    ]
    for h in common_fixed:
        if any(h == it["title"].strip() for it in flat):
            detected_structural_titles.add(h)

    # 若大綱完全為空時之基礎降級
    if not detected_structural_titles:
        for h in ["版权信息", "版權信息", "内容提要", "內容提要", "前言", "序言", "导言", "致谢", "后记"]:
            if any(h in it["title"] for it in flat):
                detected_structural_titles.add(h)

    present_fixed = sorted(list(detected_structural_titles), key=lambda x: len(x), reverse=True)

    # 搜尋大綱中出現的方案類型名稱 (如 睡眠方案、運動方案等，並包含繁簡對應，相容 Go 正則語法)
    protocol_types = set()
    for it in flat:
        m = re.search(r'([^\s（(]{2,6}方案)\s*[0-9]+', it["title"])
        if m:
            protocol_types.add(m.group(1))

    if protocol_types:
        all_proto = set(protocol_types)
        for pt in list(protocol_types):
            all_proto.add(pt.replace("运动", "運動").replace("压力控制", "壓力控制").replace("营养", "營養").replace("学习", "學習").replace("个人成长", "個人成長"))
        proto_pattern = "|".join(sorted(all_proto))
        protocol_part = rf"(?:(?:{proto_pattern})\s*[0-9]+(?:\s*[^\n。！？!?]{{0,40}})?)"
    else:
        protocol_part = ""

    # 搜尋大綱中是否包含數字層級小節 (如 1.1, 1.2, 2.1 等)
    has_decimal_sections = any(re.search(r'^\s*[0-9]+(?:\.[0-9]+)+', it["title"]) for it in flat)
    num_section_part = r"[0-9]+(?:\.[0-9]+)+[\s：:][^\n。！？!?]{0,50}" if has_decimal_sections else ""

    # 支援常見出版物之「步、講、課、集、輯」等大章節計量詞
    standard_part = r"第\s*[0-9一二三四五六七八九十百千零〇两兩 ]+\s*[章回节節卷部篇步讲講课課集幕场場辑輯][：:\s]*[^\n。！？!?]{0,50}"

    parts = [standard_part]
    if num_section_part:
        parts.append(num_section_part)
    if protocol_part:
        parts.append(protocol_part)
    if present_fixed:
        fixed_joined = "|".join(re.escape(h) for h in present_fixed)
        # 關鍵修正：結構標題後方必須接續行尾 ($)，或接空格/冒號/破折號，絕不可直接接續頓號（、）或普通正文字元
        fixed_part = rf"(?:(?:{fixed_joined})(?:$|[\s：:][^\n。！？!?]{{0,50}}))"
        parts.append(fixed_part)
    else:
        parts.append(r"(?:(?:引言|致谢|致謝|关于作者|關於作者|注释|註釋)(?:$|[\s：:][^\n。！？!?]{0,50}))")

    recommended_regex = "^(?:" + "|".join(parts) + ")"
    # 擴充排除規則：排除帶有列舉/轉折/敘述標記之行（如 等—、等等、例如、比如、以及、可以通过等）
    recommended_exclude = r"(?:[。！？!?]|等[—–\-,，、]|等等|例如|比如|以及|并且|而且|可以通过|可通過|不仅|但是|说的那样|說的那樣|讲过|講過|还会|還會|讨论|討論|提到|专门回答|專門回答|指的是|出现过|出現過|已经|已經|前前面|正如|”中|中，|中、)"

    # 計算建議最大標題長度
    title_lengths = [len(it["title"]) for it in chapters if it.get("title")]
    max_len = max(title_lengths + [35]) + 15
    max_len = max(min(max_len, 85), 65)

    return {
        "has_outline": True,
        "total_items": len(flat),
        "outline_tree": raw_tree,
        "flat_outline": flat,
        "chapters": chapters,
        "page_to_chapters": page_to_chapters,
        "recommended_match_regex": recommended_regex,
        "recommended_exclude_regex": recommended_exclude,
        "recommended_max_title_len": max_len
    }


def extract_raw_text_poppler(filepath: str) -> Optional[List[str]]:
    """
    透過 poppler 之 pdftotext 提取各頁文字
    回傳：頁面字串清單 (每頁一個字串)
    """
    pdftotext_path = shutil.which("pdftotext")
    if not pdftotext_path:
        return None

    try:
        # 1. 優先使用 -layout 模式，完整保留 PDF 原始段落視覺縮排、空行間距與排版幾何結構
        cmd = [pdftotext_path, "-layout", "-enc", "UTF-8", filepath, "-"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0 and res.stdout and len(res.stdout.strip()) > 30:
            pages = res.stdout.split("\x0c")
            if pages and not pages[-1].strip():
                pages.pop()
            return pages
    except Exception:
        pass

    try:
        # 2. 備援：若 -layout 異常則使用一般模式
        cmd = [pdftotext_path, "-enc", "UTF-8", filepath, "-"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0 and res.stdout:
            pages = res.stdout.split("\x0c")
            if pages and not pages[-1].strip():
                pages.pop()
            return pages
    except Exception:
        pass
    return None


def extract_raw_text_pypdf(filepath: str) -> Optional[List[str]]:
    """透過 pypdf 套件提取各頁文字 (若已安裝)"""
    try:
        import pypdf
        reader = pypdf.PdfReader(filepath)
        pages = []
        for p in reader.pages:
            t = p.extract_text() or ""
            pages.append(t)
        if pages:
            return pages
    except Exception:
        pass
    return None


def extract_raw_text_pure_python(filepath: str) -> List[str]:
    """
    內建純 Python PDF 串流文字解碼器 (零相依備援引擎)
    遍歷 PDF 中的 /Filter /FlateDecode 串流，解出文字指令 (Tj / TJ)
    """
    pages = []
    try:
        with open(filepath, "rb") as f:
            data = f.read()

        stream_pattern = re.compile(b'stream[\r\n]+(.*?)[\r\n]+endstream', re.DOTALL)
        current_page_lines = []

        for m in stream_pattern.finditer(data):
            raw_stream = m.group(1)
            try:
                decomp = zlib.decompress(raw_stream)
            except Exception:
                decomp = raw_stream

            if b'BT' not in decomp:
                continue

            # 搜尋 (string) Tj
            for tj in re.finditer(rb'\((.*?)\)\s*Tj', decomp):
                s = _decode_pdf_literal_str(tj.group(1))
                if s:
                    current_page_lines.append(s)

            # 搜尋 [(part1) kern (part2)] TJ
            for tarr in re.finditer(rb'\[(.*?)\]\s*TJ', decomp):
                parts = re.findall(rb'\((.*?)\)', tarr.group(1))
                joined = "".join(_decode_pdf_literal_str(p) for p in parts)
                if joined:
                    current_page_lines.append(joined)

            # 當頁面文字累積到一定量，視為一頁
            if len(current_page_lines) > 25:
                pages.append("\n".join(current_page_lines))
                current_page_lines = []

        if current_page_lines:
            pages.append("\n".join(current_page_lines))
    except Exception:
        pass

    return pages


def clean_pdf_pages_artifacts(
    pages: List[str],
    outline_info: Optional[Dict[str, Any]] = None
) -> str:
    """
    清洗 PDF 文字常見之排版缺陷，並依據大綱目錄將章節標題對齊嵌入精確頁面位置：
    1. 統計並移除出現在多數頁面頂端之「重複頁眉 (Running Headers)」
    2. 移除出現在頁首或頁尾之「頁碼 (Page Numbers)」
    3. 依據大綱將分散在兩行的章節標號與副標題進行標準合併 (如「第一章」+「睡眠」->「第一章 睡眠」)
    4. 確保章節大綱標題獨立成行且帶標準間距 (前後空行)，確保後續轉換引擎精確辨識
    5. 修復跨行英文連字號 (Hyphenation)
    6. 消除中文字元間不自然的半形空格
    7. 平滑銜接跨頁段落
    """
    if not pages:
        return ""

    total_pages = len(pages)
    page_to_chapters = outline_info.get("page_to_chapters", {}) if outline_info else {}
    outline_title_strings = {it["title"] for it in outline_info.get("flat_outline", [])} if outline_info else set()

    # 1. 統計可能之重複頁眉 (檢查前兩行)
    header_counter = Counter()
    for p in pages:
        lines = [l.strip() for l in p.splitlines() if l.strip()]
        for cand in lines[:2]:
            # 長度在 3~45 字且非純數字
            if 3 <= len(cand) <= 45 and not re.match(r'^\d+$', cand):
                header_counter[cand] += 1

    # 若出現頻率大於 25% 頁面，視為重複頁眉標題
    suspected_headers = {h for h, cnt in header_counter.items() if cnt >= max(3, int(total_pages * 0.25))}

    cleaned_pages = []
    page_num_regex = re.compile(
        r'^\s*[-—·~_\[\(]?\s*(?:(?:Page|page|PAGE|P\.|p\.|第)\s*[-—·~_]*\s*)?(?:\d+|[ivx]{2,5}|[IVX]{2,5})(?:\s*(?:/|of|之)\s*(?:\d+|[ivx]+|[IVX]+)|\s*[頁页])?\s*[-—·~_\]\)]?\s*$',
        re.I
    )

    for p_idx, p in enumerate(pages):
        page_no = p_idx + 1  # 1-based page number
        raw_lines = p.splitlines()
        page_lines = []

        # 檢查該頁是否有大綱章節
        chapters_on_this_page = page_to_chapters.get(page_no, [])

        for l in raw_lines:
            stripped = l.strip()
            if not stripped:
                page_lines.append("")
                continue

            # 過濾重複頁眉 (若該行非本頁大綱章節)
            if stripped in suspected_headers and stripped not in chapters_on_this_page:
                continue

            # 過濾純頁碼
            if page_num_regex.match(stripped):
                continue

            page_lines.append(l)

        # 處理章節標題對齊與折行副標題合併 (相容單行、跨行標題與層級小節)
        non_empty = [(i, line.strip()) for i, line in enumerate(page_lines) if line.strip()]
        skip_indices = set()

        # 優先：若本頁包含大綱章節，對齊 1~4 行跨行標題
        for o_title in chapters_on_this_page:
            norm_target = o_title.replace(" ", "")
            matched = False
            for span_len in (1, 2, 3, 4):
                for k in range(len(non_empty) - span_len + 1):
                    span = non_empty[k : k + span_len]
                    if any(idx in skip_indices for idx, _ in span):
                        continue
                    combined_norm = "".join(l for _, l in span)
                    if combined_norm.startswith(norm_target):
                        first_idx = span[0][0]
                        last_idx = span[-1][0]
                        trailing = combined_norm[len(norm_target):].strip()
                        page_lines[first_idx] = f"\n\n{o_title}\n\n"
                        for idx_del, _ in span[1:]:
                            page_lines[idx_del] = ""
                            skip_indices.add(idx_del)
                        skip_indices.add(first_idx)
                        if trailing:
                            page_lines[last_idx] = trailing
                            if last_idx in skip_indices:
                                skip_indices.remove(last_idx)
                        matched = True
                        break
                if matched:
                    break

        # 次之：對未在大綱中明確標注或未對齊的純章節號與折行副標題進行合併
        non_empty_remaining = [(i, line.strip()) for i, line in enumerate(page_lines) if line.strip() and i not in skip_indices]
        for k in range(len(non_empty_remaining) - 1):
            i0, l0 = non_empty_remaining[k]
            i1, l1 = non_empty_remaining[k + 1]
            if i0 in skip_indices or i1 in skip_indices:
                continue

            is_chap_num = bool(
                re.match(r'^第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節卷部篇]$', l0) or
                re.match(r'^[0-9]+(?:\.[0-9]+)+$', l0) or
                re.match(r'^.+?方案\s*[0-9]+$', l0)
            )
            if is_chap_num:
                combined_title = f"{l0} {l1}"
                is_subtitle = (
                    combined_title in outline_title_strings or
                    l1 in outline_title_strings or
                    (len(l1) <= 45 and not any(c in l1 for c in "。！？；;…"))
                )
                if is_subtitle:
                    page_lines[i0] = f"\n\n{combined_title}\n\n"
                    page_lines[i1] = ""
                    skip_indices.add(i0)
                    skip_indices.add(i1)

        cleaned_pages.append("\n".join(page_lines))

    # 2. 跨頁拼接
    full_text = ""
    for i, p_text in enumerate(cleaned_pages):
        p_text = p_text.strip("\r\n")
        if not p_text.strip():
            continue

        if not full_text:
            full_text = p_text
            continue

        # 檢查上一頁結尾與當前頁開頭是否為自然斷句
        last_line = full_text.splitlines()[-1].rstrip() if full_text.splitlines() else ""
        first_line = p_text.splitlines()[0].lstrip() if p_text.splitlines() else ""

        # 若上一行以連字號 - 結尾，去除連字號直接接續
        if last_line.endswith("-") and len(last_line) > 1 and last_line[-2].isalpha() and first_line and first_line[0].isalpha():
            full_text = full_text[:-1] + p_text
        # 若上一行結尾並非句末標點（如中文句號、問號、嘆號）且非章節標題，以單換行連接
        elif last_line and last_line[-1] not in "。！？!?…；;”」』" and not re.search(r'第[0-9一二三四五六七八九十]+[章節回]', last_line):
            full_text += "\n" + p_text
        else:
            full_text += "\n\n" + p_text

    # 3. 清理中文字間多餘半形空格 (中文字 + 空格 + 中文字 -> 合併)
    full_text = re.sub(r'([\u4e00-\u9fa5]) +([\u4e00-\u9fa5])', r'\1\2', full_text)
    full_text = re.sub(r'([\u4e00-\u9fa5]) +([\u4e00-\u9fa5])', r'\1\2', full_text)

    return full_text


def extract_pdf_to_text(
    filepath: str,
    output_txt_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    主要入口：將文字型 PDF 自動轉換為高畫質 TXT 純文字書籍，並自動產生相應之元資料檔案 (_metadata.json)
    包含元資料萃取、大綱目錄解析、多層後端擷取、排版雜訊清洗與大綱章節精確對齊。
    """
    if not os.path.exists(filepath):
        return {"success": False, "error": f"找不到 PDF 檔案: {filepath}"}

    meta = extract_pdf_metadata(filepath)
    outline = extract_pdf_outline(filepath)

    # 1. 嘗試 poppler pdftotext
    pages = extract_raw_text_poppler(filepath)
    method_used = "pdftotext (Poppler)"

    # 2. 備援：pypdf
    if not pages or sum(len(p.strip()) for p in pages) < 50:
        p_pages = extract_raw_text_pypdf(filepath)
        if p_pages and sum(len(p.strip()) for p in p_pages) > 50:
            pages = p_pages
            method_used = "pypdf"

    # 3. 備援：純 Python 串流解析
    if not pages or sum(len(p.strip()) for p in pages) < 50:
        py_pages = extract_raw_text_pure_python(filepath)
        if py_pages and sum(len(p.strip()) for p in py_pages) > 50:
            pages = py_pages
            method_used = "pure_python (內建解碼器)"

    if not pages or sum(len(p.strip()) for p in pages) < 30:
        return {
            "success": False,
            "error": "未能從該 PDF 擷取出有效文字內容。該檔案可能為純掃描圖片型 PDF（需 OCR 光學文字辨識）或具有加密保護。",
            "metadata": meta,
            "outline": outline,
            "pages": len(pages) if pages else 0
        }

    # 依據大綱對齊進行排版清洗
    cleaned_text = clean_pdf_pages_artifacts(pages, outline_info=outline)

    if not output_txt_path:
        base_dir = os.path.dirname(os.path.abspath(filepath))
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        output_txt_path = os.path.join(base_dir, f"{base_name}.txt")

    try:
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write(cleaned_text)
    except Exception as e:
        return {"success": False, "error": f"寫入 TXT 暫存檔失敗: {str(e)}"}

    # 4. 生成並寫入伴生元資料 JSON 檔案 (<bookname>_metadata.json)
    base_stem = os.path.splitext(output_txt_path)[0]
    metadata_json_path = f"{base_stem}_metadata.json"

    meta_payload = {
        "title": meta.get("title", ""),
        "bookname": meta.get("title", ""),
        "author": meta.get("author", ""),
        "subject": meta.get("subject", ""),
        "creator": meta.get("creator", ""),
        "producer": meta.get("producer", ""),
        "pages": len(pages),
        "characters": len(cleaned_text),
        "has_outline": outline.get("has_outline", False),
        "total_outline_items": outline.get("total_items", 0),
        "recommended_match_regex": outline.get("recommended_match_regex", ""),
        "recommended_exclude_regex": outline.get("recommended_exclude_regex", ""),
        "recommended_max_title_len": outline.get("recommended_max_title_len", 65),
        "chapters": outline.get("chapters", []),
        "outline_tree": outline.get("outline_tree", []),
        "flat_outline": outline.get("flat_outline", []),
        "page_to_chapters": outline.get("page_to_chapters", {}),
        "extracted_method": method_used,
        "source_pdf": filepath
    }

    try:
        with open(metadata_json_path, "w", encoding="utf-8") as f_meta:
            json.dump(meta_payload, f_meta, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return {
        "success": True,
        "txt_path": output_txt_path,
        "metadata_path": metadata_json_path,
        "metadata": meta,
        "outline": outline,
        "pages": len(pages),
        "pages_count": len(pages),
        "characters": len(cleaned_text),
        "char_count": len(cleaned_text),
        "method": method_used,
        "sample_preview": cleaned_text[:300]
    }
