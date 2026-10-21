# -*- coding: utf-8 -*-
"""
文字小說檔名解析與章節正則表達式即時測試模組
"""

import os
import re
from typing import Dict, List, Tuple, Any
from .zh_converter import detect_encoding, convert_text

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
DEFAULT_VOLUME_REGEX = r"^第[0-9一二三四五六七八九十零〇百千两 ]+[卷部]"
DEFAULT_EXCLUDE_REGEX = r"^第[0-9一二三四五六七八九十零〇百千两 ]+(部門|部队|部属|部分|部件|部落|部.*：$)"

# 常見預設規則選項清單（供 GUI 下拉選單使用）
REGEX_PRESETS = [
    ("自動智慧識別 (預設)", ""),
    ("標準中文章節 (行首 第X章/回/節/集)", r"^第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節集]"),
    ("彈性中文章節 (第與章之間1-8字)", r"第.{1,8}[章回节節]"),
    ("行內包含第X章 (天涯帶作者/不限行首)", r"第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節]"),
    ("天涯/貼吧樓層 (1 樓、2 樓...)", r"^[0-9]+\s*楼"),
    ("天涯論壇發帖 (作者:某某 日期:...)", r"^作者:.+?日期:"),
    ("天涯樓主時間標籤 ([--樓主:...--])", r"^\[--楼主"),
    ("中文大寫序號主題 (一、二、三、)", r"^[一二三四五六七八九十]+[、\.]"),
    ("英文 Chapter (Chapter 1...)", r"Chapter\s+\d+"),
    ("英文 Section (Section 1...)", r"Section\s+\d+"),
    ("中文純數字序號 (1. 標題 或 1、標題)", r"^\s*\d+[\.、\s]"),
    ("特殊括號章節 (【第X章】)", r"【第?[0-9一二三四五六七八九十]+[章節回]】"),
]

def parse_filename_meta(filepath: str, auto_to_tw: bool = True) -> Dict[str, str]:
    """
    從檔案名稱自動擷取書名與作者，並支援轉為正體中文
    """
    basename = os.path.basename(filepath)
    name_no_ext, _ = os.path.splitext(basename)

    title = name_no_ext
    author = "YSTYLE"

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
    max_len: int = 35,
    scan_lines: int = 5000
) -> Dict[str, Any]:
    """
    掃描 txt 檔案前 N 行，測試章節正則與分卷正則匹配效果
    """
    if not os.path.exists(filepath):
        return {"error": "檔案不存在"}

    encoding = detect_encoding(filepath)
    
    # 編譯正則表達式
    compiled_match = None
    if match_regex and match_regex.strip():
        try:
            compiled_match = re.compile(match_regex.strip())
        except re.error as e:
            return {"error": f"章節正則表達式語法錯誤: {str(e)}"}
    else:
        compiled_match = re.compile(DEFAULT_CHAPTER_REGEX)

    compiled_volume = None
    if volume_regex and volume_regex.strip() and volume_regex.strip().lower() != "false":
        try:
            compiled_volume = re.compile(volume_regex.strip())
        except re.error as e:
            return {"error": f"分卷正則表達式語法錯誤: {str(e)}"}

    compiled_exclude = None
    if exclude_regex and exclude_regex.strip():
        try:
            compiled_exclude = re.compile(exclude_regex.strip())
        except re.error as e:
            return {"error": f"排除正則表達式語法錯誤: {str(e)}"}

    chapters = []
    volumes = []
    excluded_count = 0
    total_lines = 0

    try:
        with open(filepath, "r", encoding=encoding, errors="replace") as f:
            for line_no, raw_line in enumerate(f, start=1):
                total_lines += 1
                line = raw_line.strip()
                if not line:
                    continue

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

                if scan_lines > 0 and total_lines >= scan_lines:
                    break

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

    except Exception as e:
        return {"error": f"讀取或解析失敗: {str(e)}"}


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
        "id": "inline_chapter",
        "name": "行內包含第X章 (天涯帶作者/不限行首)",
        "regex": r"第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節]",
        "max_len": 60,
        "priority": 90,
        "min_cnt": 5,
        "max_cnt": 4000
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
        "id": "chapter_en",
        "name": "英文 Chapter (Chapter 1...)",
        "regex": r"^\s*Chapter\s+\d+",
        "max_len": 40,
        "priority": 80,
        "min_cnt": 3,
        "max_cnt": 3000
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
    智慧自動分析文字小說結構，推斷最合適的章節匹配規則
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

    encoding = detect_encoding(filepath)
    lines = []
    try:
        with open(filepath, "r", encoding=encoding, errors="replace") as f:
            for idx, raw_line in enumerate(f):
                line = raw_line.strip()
                if line:
                    lines.append(line)
                if max_scan_lines > 0 and idx >= max_scan_lines:
                    break
    except Exception:
        pass

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
            # 針對常見小說合理章節數 (10 ~ 600) 給予加分權重
            if 10 <= cnt <= 600:
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

