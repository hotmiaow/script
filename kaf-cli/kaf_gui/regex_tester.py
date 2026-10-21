# -*- coding: utf-8 -*-
"""
文字小說檔名解析與章節正則表達式即時測試模組
"""

import os
import re
import json
import tempfile
from typing import Dict, List, Tuple, Any
from .zh_converter import detect_encoding, convert_text
from .pdf_extractor import is_pdf_file, extract_pdf_metadata, extract_pdf_to_text, extract_pdf_outline

# 常見書名與作者正則表達式
_PATTERNS = [
    # 《書名》（版本）作者：作者名.txt
    re.compile(r"《(?P<title>[^》]+)》.*?作者[：:\s]+(?P<author>[^\s\.\(\)\[\]_]+)", re.I),
    # 書名 作者：作者名.txt
    re.compile(r"^(?P<title>[^《》\[\]\(\)]+?)[\s_]+作者[：:\s]+(?P<author>[^\s\.\(\)\[\]_]+)", re.I),
    # [分類] 書名 (作者).txt
    re.compile(r"^(?:\[[^\]]+\]\s*)?(?P<title>[^\(\)\[\]]+?)\s*[\(（](?P<author>[^\)）]+)[\)）]", re.I),
    # 書名 by 作者.txt
    re.compile(r"^(?P<title>.+?)\s+by\s+(?P<author>[^\s\.]+)", re.I),
    # 《書名》.txt
    re.compile(r"《(?P<title>[^》]+)》", re.I),
]

# 預設自動章節正則
DEFAULT_CHAPTER_REGEX = r"^第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節集]"
DEFAULT_VOLUME_REGEX = r"^第[0-9一二三四五六七八九十零〇百千两 ]+[卷部篇輯]"
DEFAULT_EXCLUDE_REGEX = r"^第[0-9一二三四五六七八九十零〇百千两 ]+(部門|部队|部属|部分|部件|部落|部.*：$)"

# 常見預設規則選項清單（供 GUI 下拉選單使用，涵蓋小說與通用書籍）
REGEX_PRESETS = [
    ("自動智慧識別 (預設)", ""),
    ("標準中文章節 (行首 第X章/回/節/集)", r"^第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節集]"),
    ("全能綜合匹配 (小說 + 通用非小說書籍 + 技術手冊)", r"^\s*(?:第[0-9一二三四五六七八九十百千零〇两 ]+[篇部輯章回节節集]|(?:[一二三四五六七八九十]+[、\.]\s*)|(?:Chapter|Part|Section)\s+[0-9IVXLCDM]+|[0-9]{1,3}\.[0-9]{1,2}(?:\.[0-9]{1,2})?[\s：:]+|(?:前言|序言|導論|引言|導讀|結語|後記|附錄|參考文獻|致謝))\b.*"),
    ("通用書籍：中式大綱 (篇/章/節/一、二、/前言/導論/結語)", r"^\s*(?:第[0-9一二三四五六七八九十百千]+[篇部輯章節]|(?:[一二三四五六七八九十]+[、\.]\s*)|(?:前言|序言|導論|引言|導讀|結語|後記|附錄|參考文獻|致謝)).*"),
    ("通用書籍：數字章節與層級小節 (1. / 1.1 / 1.1.1)", r"^\s*(?:[0-9]{1,3}\.[0-9]{1,2}(?:\.[0-9]{1,2})?[\s：:]+[\u4e00-\u9fa5A-Za-z]|[0-9]{1,3}[\s：:]+[\u4e00-\u9fa5A-Za-z]).*"),
    ("英文通用書籍 (Chapter / Part / Section / Introduction)", r"^\s*(?:Chapter\s+[0-9IVXLCDM]+|Part\s+[0-9IVXLCDM]+|Section\s+[0-9IVXLCDM]+|Introduction|Conclusion|Appendix\s*[A-Z0-9]?|Preface|Foreword)\b.*"),
    ("彈性中文章節 (第與章之間1-8字)", r"第.{1,8}[章回节節]"),
    ("行內包含第X章 (天涯帶作者/不限行首)", r"第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節]"),
    ("中文大寫序號主題 (一、二、三、)", r"^[一二三四五六七八九十]+[、\.]"),
    ("英文 Chapter (Chapter 1...)", r"Chapter\s+\d+"),
    ("英文 Section (Section 1...)", r"Section\s+\d+"),
    ("中文純數字序號 (1. 標題 或 1、標題)", r"^\s*\d+[\.、\s]"),
    ("特殊括號章節 (【第X章】)", r"【第?[0-9一二三四五六七八九十]+[章節回]】"),
    ("天涯/貼吧樓層 (1 樓、2 樓...)", r"^[0-9]+\s*楼"),
    ("天涯論壇發帖 (作者:某某 日期:...)", r"^作者:.+?日期:"),
]

# 記憶體快取避免重複解碼 PDF
_PDF_SAMPLE_CACHE: Dict[str, Tuple[float, str]] = {}


def sanitize_regex_for_python(pat_str: str) -> str:
    """
    將非 Python 內建標準的正則語法（如 Go RE2 / PCRE 之 \\p{Han}、\\p{L}）
    安全轉換為 Python re 模組相容的等效字符類，防止拋出 bad escape \\p 錯誤。
    """
    if not pat_str:
        return pat_str
    s = pat_str.replace(r"\p{Han}", "[一-鿿]")
    s = s.replace(r"\p{L}", "[a-zA-Z一-鿿]")
    return s


def get_file_lines_for_analysis(filepath: str, max_lines: int = 15000) -> Tuple[List[str], str]:
    """透明獲取文本分析之行清單（自動相容 TXT 與 PDF）"""
    actual_path = filepath
    if is_pdf_file(filepath):
        try:
            mtime = os.path.getmtime(filepath)
            if filepath in _PDF_SAMPLE_CACHE and _PDF_SAMPLE_CACHE[filepath][0] == mtime:
                actual_path = _PDF_SAMPLE_CACHE[filepath][1]
            else:
                fd, tmp_txt = tempfile.mkstemp(suffix=".txt", prefix="kaf_pdf_scan_")
                os.close(fd)
                res = extract_pdf_to_text(filepath, tmp_txt)
                if res.get("success"):
                    _PDF_SAMPLE_CACHE[filepath] = (mtime, tmp_txt)
                    actual_path = tmp_txt
        except Exception:
            pass

    encoding = detect_encoding(actual_path)
    lines = []
    try:
        with open(actual_path, "r", encoding=encoding, errors="replace") as f:
            for idx, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if line:
                    lines.append(line)
                if max_lines > 0 and idx >= max_lines:
                    break
    except Exception:
        pass

    return lines, encoding


def parse_filename_meta(filepath: str, auto_to_tw: bool = True) -> Dict[str, str]:
    """
    從檔案名稱或 PDF 內部元資料自動擷取書名與作者，並支援轉為正體中文
    """
    basename = os.path.basename(filepath)
    name_no_ext, _ = os.path.splitext(basename)

    title = name_no_ext
    author = "YSTYLE"

    # 若為 PDF，優先讀取 PDF 內嵌 Title / Author
    if is_pdf_file(filepath):
        try:
            meta = extract_pdf_metadata(filepath)
            if meta.get("title") and len(meta["title"].strip()) >= 2:
                t = meta["title"].strip()
                if not re.search(r'(?:Microsoft Word|WPS|Untitled|未命名|Print)', t, re.I):
                    title = t
            if meta.get("author") and len(meta["author"].strip()) >= 2:
                a = meta["author"].strip()
                if not re.search(r'(?:Administrator|User|Windows|Macintosh|Microsoft)', a, re.I):
                    author = a
        except Exception:
            pass

    for pattern in _PATTERNS:
        match = pattern.search(name_no_ext)
        if match:
            group_dict = match.groupdict()
            if "title" in group_dict and group_dict["title"]:
                title = group_dict["title"].strip()
            if "author" in group_dict and group_dict["author"]:
                author = group_dict["author"].strip()
            break

    # 清除多餘的綴詞（如：校對版全本、精校版等）
    title = re.sub(r"[\(（].*?(?:校對|精校|完本|全本|精修|無錯).*?[\)）]", "", title).strip()

    if auto_to_tw:
        title = convert_text(title, mode="s2tw")
        author = convert_text(author, mode="s2tw")

    return {
        "title": title,
        "author": author,
        "original_filename": basename
    }

def test_chapter_match(
    filepath: str,
    match_regex: str = "",
    volume_regex: str = DEFAULT_VOLUME_REGEX,
    exclude_regex: str = DEFAULT_EXCLUDE_REGEX,
    max_len: int = 45,
    scan_lines: int = 5000
) -> Dict[str, Any]:
    """
    掃描 txt 或 PDF 檔案前 N 行，測試章節正則與分卷正則匹配效果
    """
    if not os.path.exists(filepath):
        return {"error": "檔案不存在"}

    if is_pdf_file(filepath):
        try:
            outline = extract_pdf_outline(filepath)
            if outline.get("has_outline"):
                rec_regex = sanitize_regex_for_python(outline.get("recommended_match_regex", ""))
                # 若無指定正則或正則為 PDF 大綱推薦規則，直接呈現階層式大綱書籤
                if not match_regex or match_regex.strip() == rec_regex.strip():
                    flat = outline.get("flat_outline", [])
                    if flat:
                        preview_items = []
                        for it in flat[:100]:
                            lvl = it.get("level", 1)
                            prefix = "  " * (lvl - 1)
                            display_title = (prefix + ("└ " if lvl > 1 else "") + it.get("title", "")).strip()
                            preview_items.append({
                                "line_no": f"頁 {it.get('page', 1)}",
                                "type": f"H{lvl}",
                                "title": display_title
                            })
                        return {
                            "success": True,
                            "encoding": "PDF Outline",
                            "total_lines_scanned": outline.get("total_items", len(flat)),
                            "chapters_found": len(flat),
                            "volumes_found": 0,
                            "excluded_count": 0,
                            "preview_items": preview_items,
                            "sample_chapters": flat[:30],
                            "sample_volumes": [],
                            "stats_summary": f"PDF 內建大綱書籤目錄（共識別 {len(flat)} 個層級章節標題）"
                        }
        except Exception:
            pass

    lines, encoding = get_file_lines_for_analysis(filepath, max_lines=scan_lines)
    
    # 編譯正則表達式
    compiled_match = None
    if match_regex and match_regex.strip():
        try:
            compiled_match = re.compile(sanitize_regex_for_python(match_regex.strip()))
        except re.error as e:
            return {"error": f"章節正則表達式語法錯誤: {str(e)}"}
    else:
        compiled_match = re.compile(DEFAULT_CHAPTER_REGEX)

    compiled_volume = None
    if volume_regex and volume_regex.strip() and volume_regex.strip().lower() != "false":
        try:
            compiled_volume = re.compile(sanitize_regex_for_python(volume_regex.strip()))
        except re.error as e:
            return {"error": f"分卷正則表達式語法錯誤: {str(e)}"}

    compiled_exclude = None
    if exclude_regex and exclude_regex.strip():
        try:
            compiled_exclude = re.compile(sanitize_regex_for_python(exclude_regex.strip()))
        except re.error as e:
            return {"error": f"排除正則表達式語法錯誤: {str(e)}"}

    chapters = []
    volumes = []
    excluded_count = 0
    total_lines = len(lines)

    for line_no, line in enumerate(lines, start=1):
        # 排除檢查
        if compiled_exclude and compiled_exclude.search(line):
            excluded_count += 1
            continue

        # 分卷檢查
        if compiled_volume and compiled_volume.search(line):
            if len(line) <= max_len:
                volumes.append({
                    "line_no": line_no,
                    "type": "卷",
                    "title": line
                })
                continue

        # 章節檢查
        if compiled_match and compiled_match.search(line):
            if len(line) <= max_len:
                chapters.append({
                    "line_no": line_no,
                    "type": "章節",
                    "title": line
                })

    return {
        "success": True,
        "encoding": encoding,
        "total_lines_scanned": total_lines,
        "chapters_found": len(chapters),
        "volumes_found": len(volumes),
        "excluded_count": excluded_count,
        "preview_items": (volumes + chapters)[:100],
        "sample_chapters": chapters[:30],
        "sample_volumes": volumes[:10]
    }


AUTO_RULE_CANDIDATES = [
    {
        "id": "standard_chapter",
        "name": "標準中文章節 (行首 第X章/回/節/集)",
        "regex": r"^\s*第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節集]",
        "max_len": 35,
        "priority": 100,
        "min_cnt": 5,
        "max_cnt": 4000
    },
    {
        "id": "general_cn",
        "name": "通用書籍：中式大綱 (篇/章/節/一、二、/前言/導論/結語)",
        "regex": r"^\s*(?:第[0-9一二三四五六七八九十百千]+[篇部輯章節]|(?:[一二三四五六七八九十]+[、\.]\s*)|(?:前言|序言|導論|引言|導讀|結語|後記|附錄|參考文獻|致謝)).*",
        "max_len": 50,
        "priority": 95,
        "min_cnt": 3,
        "max_cnt": 2000
    },
    {
        "id": "general_sections",
        "name": "通用書籍：數字章節與層級小節 (1. / 1.1 / 1.1.1)",
        "regex": r"^\s*(?:[0-9]{1,3}\.[0-9]{1,2}(?:\.[0-9]{1,2})?\s+[\u4e00-\u9fa5A-Za-z]|[0-9]{1,3}\s+[\u4e00-\u9fa5A-Za-z]).*",
        "max_len": 50,
        "priority": 92,
        "min_cnt": 3,
        "max_cnt": 2000
    },
    {
        "id": "inline_chapter",
        "name": "行內包含第X章 (天涯帶作者/不限行首)",
        "regex": r"第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節]",
        "max_len": 60,
        "priority": 90,
        "min_cnt": 5,
        "max_cnt": 4000
    },
    {
        "id": "general_en",
        "name": "英文通用書籍 (Chapter / Part / Section / Introduction)",
        "regex": r"^\s*(?:Chapter\s+[0-9IVXLCDM]+|Part\s+[0-9IVXLCDM]+|Section\s+[0-9IVXLCDM]+|Introduction|Conclusion|Appendix\s*[A-Z0-9]?|Preface|Foreword)\b.*",
        "max_len": 50,
        "priority": 88,
        "min_cnt": 2,
        "max_cnt": 2000
    },
    {
        "id": "chinese_num",
        "name": "中文大寫序號主題 (一、二、三、)",
        "regex": r"^\s*[一二三四五六七八九十]+[、\.]",
        "max_len": 50,
        "priority": 85,
        "min_cnt": 5,
        "max_cnt": 500
    },
    {
        "id": "general_hybrid",
        "name": "全能綜合匹配 (小說 + 通用非小說書籍 + 技術手冊)",
        "regex": r"^\s*(?:第[0-9一二三四五六七八九十百千零〇两 ]+[篇部輯章回节節集]|(?:[一二三四五六七八九十]+[、\.]\s*)|(?:Chapter|Part|Section)\s+[0-9IVXLCDM]+|[0-9]{1,3}\.[0-9]{1,2}(?:\.[0-9]{1,2})?\s+|(?:前言|序言|導論|引言|導讀|結語|後記|附錄|參考文獻|致謝))\b.*",
        "max_len": 50,
        "priority": 80,
        "min_cnt": 3,
        "max_cnt": 4000
    },
    {
        "id": "chapter_en",
        "name": "英文 Chapter (Chapter 1...)",
        "regex": r"^\s*Chapter\s+\d+",
        "max_len": 40,
        "priority": 80,
        "min_cnt": 3,
        "max_cnt": 3000
    },
    {
        "id": "tianya_floor",
        "name": "天涯/貼吧樓層 (1 樓、2 樓...)",
        "regex": r"^\s*[0-9]+\s*楼",
        "max_len": 35,
        "priority": 75,
        "min_cnt": 5,
        "max_cnt": 6000
    },
    {
        "id": "tianya_host",
        "name": "天涯樓主時間標籤 ([--樓主:...--])",
        "regex": r"^\s*\[--楼主",
        "max_len": 50,
        "priority": 70,
        "min_cnt": 5,
        "max_cnt": 6000
    },
    {
        "id": "tianya_post",
        "name": "天涯論壇發帖 (作者:某某 日期:...)",
        "regex": r"^\s*作者:.+?日期:",
        "max_len": 60,
        "priority": 65,
        "min_cnt": 5,
        "max_cnt": 6000
    },
    {
        "id": "arabic_num",
        "name": "中文純數字序號 (1. 標題 或 1、標題)",
        "regex": r"^\s*\d+[\.、]\s*[\u4e00-\u9fa5A-Za-z]",
        "max_len": 40,
        "priority": 50,
        "min_cnt": 5,
        "max_cnt": 500
    },
    {
        "id": "auto_default",
        "name": "自動智慧識別 (預設)",
        "regex": "",
        "max_len": 35,
        "priority": 10,
        "min_cnt": 0,
        "max_cnt": 999999
    }
]

def auto_detect_best_rule(filepath: str, max_scan_lines: int = 15000) -> Dict[str, Any]:
    """
    智慧自動分析文字或 PDF 書籍結構，推斷最合適的章節匹配規則（兼顧小說與一般通用書籍）
    優先採用 PDF 內嵌大綱目錄或相應伴生元資料 (_metadata.json) 規則。
    """
    if not os.path.exists(filepath):
        return {
            "rule_name": "自動智慧識別 (預設)",
            "regex": "",
            "max_len": 35,
            "chapter_count": 0,
            "sample_chapters": [],
            "candidates": []
        }

    # 1. 若為 PDF 文件，優先讀取內建書籤大綱目錄
    if is_pdf_file(filepath):
        try:
            outline = extract_pdf_outline(filepath)
            if outline.get("has_outline") and outline.get("recommended_match_regex"):
                sample_titles = [c["title"] for c in outline.get("chapters", [])[:10]]
                return {
                    "rule_name": f"PDF 內嵌大綱目錄 (共 {outline.get('total_items', 0)} 項)",
                    "regex": sanitize_regex_for_python(outline["recommended_match_regex"]),
                    "exclude_regex": sanitize_regex_for_python(outline.get("recommended_exclude_regex", "")),
                    "max_len": outline.get("recommended_max_title_len", 65),
                    "chapter_count": len(outline.get("chapters", [])),
                    "sample_chapters": sample_titles,
                    "candidates": []
                }
        except Exception:
            pass
    else:
        # 2. 若為 TXT 文件，檢查是否存在伴生元資料檔 (_metadata.json)
        input_stem = os.path.splitext(os.path.basename(filepath))[0]
        input_dir = os.path.dirname(os.path.abspath(filepath))
        for mp in [os.path.join(input_dir, f"{input_stem}_metadata.json"), os.path.join(input_dir, f"{input_stem}.meta.json")]:
            if os.path.isfile(mp):
                try:
                    with open(mp, "r", encoding="utf-8") as f_meta:
                        meta_data = json.load(f_meta)
                    if meta_data.get("recommended_match_regex"):
                        sample_titles = [c["title"] for c in meta_data.get("chapters", [])[:10]]
                        return {
                            "rule_name": f"伴生元資料大綱 (共 {meta_data.get('total_outline_items', len(meta_data.get('chapters', [])))} 項)",
                            "regex": sanitize_regex_for_python(meta_data["recommended_match_regex"]),
                            "exclude_regex": sanitize_regex_for_python(meta_data.get("recommended_exclude_regex", "")),
                            "max_len": meta_data.get("recommended_max_title_len", 65),
                            "chapter_count": len(meta_data.get("chapters", [])),
                            "sample_chapters": sample_titles,
                            "candidates": []
                        }
                except Exception:
                    pass

    lines, _ = get_file_lines_for_analysis(filepath, max_lines=max_scan_lines)

    evaluated = []
    for r in AUTO_RULE_CANDIDATES:
        if not r["regex"]:
            continue
        try:
            pat = re.compile(r["regex"])
        except Exception:
            continue

        matches = [l for l in lines if pat.search(l) and len(l) <= r["max_len"]]
        cnt = len(matches)

        score = 0
        if r["min_cnt"] <= cnt <= r["max_cnt"]:
            score = r["priority"]
            # 針對常見書籍合理章節數 (5 ~ 600) 給予加分權重
            if 5 <= cnt <= 600:
                score += 15

        evaluated.append({
            "id": r["id"],
            "name": r["name"],
            "regex": r["regex"],
            "max_len": r["max_len"],
            "count": cnt,
            "score": score,
            "samples": matches[:5]
        })

    # 排序：以得分最高為首選，得分相同時以匹配章節數較多者為優先
    evaluated.sort(key=lambda x: (x["score"], x["count"]), reverse=True)

    if evaluated and evaluated[0]["score"] > 0:
        best = evaluated[0]
        return {
            "rule_name": best["name"],
            "regex": best["regex"],
            "max_len": best["max_len"],
            "chapter_count": best["count"],
            "sample_chapters": best["samples"],
            "candidates": evaluated
        }
    else:
        return {
            "rule_name": "自動智慧識別 (預設)",
            "regex": "",
            "max_len": 35,
            "chapter_count": 0,
            "sample_chapters": [],
            "candidates": evaluated
        }

