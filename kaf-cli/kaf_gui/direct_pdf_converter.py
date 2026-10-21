# -*- coding: utf-8 -*-
"""
PDF 直轉 EPUB 高保真排版轉換引擎 (Direct PDF to EPUB Converter)
利用 pdftohtml (Poppler) 與 Pandoc 實現架構高保真直接轉換：
- 完整保留程式碼區塊、終端機命令 (> head(day1)) 與等寬排版
- 完整保留數值表格、對齊欄位與矩陣輸出
- 完整保留書籍中的圖表、插圖、架構圖與數學公式
- 依據 PDF 內嵌大綱標題結構生成標準 EPUB 導航目錄 (TOC)
- 支援內文標籤安全之繁簡中文轉換 (s2tw / s2hk / s2t)
- 注入現代化響應式電子書排版 CSS
"""

import os
import re
import shutil
import tempfile
import subprocess
from typing import Dict, Any, List, Optional, Callable, Tuple
from bs4 import BeautifulSoup, NavigableString, Comment

from .pdf_extractor import extract_pdf_metadata, extract_pdf_outline
from .zh_converter import convert_text
from .cover_generator import generate_orly_cover


def check_direct_converter_dependencies() -> Tuple[bool, bool, str]:
    """
    檢查系統是否安裝 pdftohtml 與 pandoc
    回傳: (has_pdftohtml, has_pandoc, message)
    """
    has_pdftohtml = bool(shutil.which("pdftohtml"))
    has_pandoc = bool(shutil.which("pandoc"))
    
    missing = []
    if not has_pdftohtml:
        missing.append("pdftohtml (poppler-utils)")
    if not has_pandoc:
        missing.append("pandoc")
        
    if missing:
        msg = f"未安裝必備工具: {', '.join(missing)}"
        return has_pdftohtml, has_pandoc, msg
    return True, True, "所有依賴工具已就緒 (pdftohtml, pandoc)"


# 預設現代化高保真 EPUB CSS 樣式
DEFAULT_DIRECT_EPUB_CSS = """
@charset "UTF-8";

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang TC", "Microsoft JhengHei", "Noto Sans CJK TC", sans-serif;
    line-height: 1.85;
    color: #24292f;
    margin: 5% 7%;
    padding: 0;
    text-align: justify;
}

h1, h2, h3, h4, h5, h6 {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
    color: #0f172a;
    line-height: 1.4;
    margin-top: 1.8em;
    margin-bottom: 0.8em;
    font-weight: 700;
    page-break-after: avoid;
}

h1 { font-size: 1.75em; text-align: center; margin-top: 2em; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.3em; }
h2 { font-size: 1.45em; border-bottom: 1px solid #f1f5f9; padding-bottom: 0.25em; }
h3 { font-size: 1.22em; }
h4 { font-size: 1.08em; }

p {
    margin: 0.7em 0;
    line-height: 1.85;
    text-indent: 0;
}

/* 程式碼與終端機輸出區塊：等寬字體、語法背景、水平捲動保護 */
pre, code, kbd, samp {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, "Courier New", monospace;
    font-size: 0.88em;
}

pre {
    background-color: #f6f8fa;
    border: 1px solid #e1e4e8;
    border-radius: 6px;
    padding: 12px 16px;
    overflow-x: auto;
    white-space: pre;
    line-height: 1.5;
    margin: 1.2em 0;
    color: #1f2328;
    box-shadow: inset 0 1px 2px rgba(0,0,0,0.03);
}

code {
    background-color: #f1f5f9;
    padding: 2px 5px;
    border-radius: 4px;
    color: #0284c7;
}

pre code {
    background: transparent;
    padding: 0;
    color: inherit;
    border: none;
    font-size: 1em;
}

/* 數據表格與矩陣 */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 1.4em 0;
    font-size: 0.9em;
    page-break-inside: avoid;
}

th, td {
    border: 1px solid #cbd5e1;
    padding: 7px 12px;
    text-align: left;
}

th {
    background-color: #f8fafc;
    font-weight: 600;
}

tr:nth-child(even) {
    background-color: #f8fafc;
}

/* 插圖與圖表自適應 */
img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1.5em auto;
    border-radius: 4px;
}

figure {
    margin: 1.5em 0;
    text-align: center;
}

figcaption {
    font-size: 0.88em;
    color: #64748b;
    margin-top: 0.5em;
}

blockquote {
    border-left: 4px solid #3b82f6;
    background-color: #f8fafc;
    margin: 1.2em 0;
    padding: 0.6em 1.2em;
    color: #475569;
}

hr {
    border: 0;
    height: 1px;
    background: #e2e8f0;
    margin: 2em 0;
}

/* MathML 與 LaTeX 數學公式優化 (EPUB 3 原生標準) */
math {
    font-family: "Latin Modern Math", "STIX Two Math", "Cambria Math", "DejaVu Math TeX Gyre", serif;
    font-size: 1.05em;
    line-height: 1.2;
}

math[display="block"] {
    margin: 1.2em 0;
    overflow-x: auto;
    overflow-y: hidden;
    padding: 0.5em 0;
    text-align: center;
}

.katex-display, .math.display {
    margin: 1.2em 0;
    text-align: center;
    overflow-x: auto;
}
"""


def convert_text_preserving_math(text: str, mode: str = "s2tw") -> str:
    r"""
    繁簡中文轉換時保護 LaTeX 數學公式 ($...$, $$...$$, \(...\), \[...\])
    避免公式語法或符號被 OpenCC 誤轉換
    """
    if not text or not mode or mode.lower() == "none":
        return text

    math_tokens: List[str] = []

    def save_math(match: re.Match) -> str:
        math_tokens.append(match.group(0))
        return f"___KAF_MATH_{len(math_tokens)-1}___"

    # 匹配 LaTeX 行內與行間公式
    math_pattern = re.compile(r'(\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]|\\\(.*?\\\))', re.DOTALL)
    placeholder_text = math_pattern.sub(save_math, text)

    # 執行中文繁簡轉換
    converted_text = convert_text(placeholder_text, mode=mode)

    # 還原原始 LaTeX 公式
    for idx, token in enumerate(math_tokens):
        converted_text = converted_text.replace(f"___KAF_MATH_{idx}___", token)

    return converted_text


def is_code_or_prompt_line(text: str) -> bool:
    """判斷文字行是否為程式命令提示字元、R/Python/Shell 代碼或輸出表格數據"""
    s = text.strip()
    if not s:
        return False
    # 0. 若該行包含 LaTeX 數學公式標記 ($...$, $$...$$, \(...\))，優先視為數學段落而非程式碼區塊
    if re.search(r'\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]|\\\(.*?\\\)', s):
        return False
    # 1. 帶有終端機或直譯器命令提示字元者 (如 > data(day1), > head(day1), $ pip install, >>>, [1] 731)
    if re.match(r'^(?:[>#]\s+|\$\s+[a-zA-Z]|>>>\s+|\.\.\.\s+|\+\s+|\[\d+\]\s+|\[\d+,\s*\])', s):
        return True
    # 2. 若該行包含中文字，則為正常中文敘述段落 (不屬於純代碼區塊)
    if re.search(r'[\u4e00-\u9fa5]', s):
        return False
    # 3. 無中文字且具備程式語言語法特徵 (如 <-, ==, !=, library(), predict(), function())
    if re.search(r'<-|==|!=|library\(|head\(|tail\(|summary\(|plot\(|data\(|as\.factor|read\.csv|predict\(|import\s+[a-z]|def\s+[a-z]|function\s*\(', s):
        return True
    # 4. 無中文字且為多欄等寬數值表格特徵 (例如 3 個以上數字或日期)
    num_matches = len(re.findall(r'\b\d{4}-\d{2}-\d{2}\b|\b[-+]?\d+(?:\.\d+)?\b', s))
    if num_matches >= 3:
        return True
    return False


def is_heading_candidate(text: str, outline_titles: set) -> Tuple[bool, int]:
    """
    判斷該行是否為章節標題，並回傳標題等級 (1: h1, 2: h2, 3: h3)
    """
    s = text.strip()
    if not s:
        return False, 0
    if len(s) > 60:
        return False, 0

    # 1. 精確符合 PDF 內嵌大綱標題
    if s in outline_titles or s.replace(" ", "") in {t.replace(" ", "") for t in outline_titles}:
        if re.search(r'^[0-9]+(?:\.[0-9]+){2,}', s):
            return True, 3
        elif re.search(r'^[0-9]+\.[0-9]+', s):
            return True, 2
        elif re.search(r'^第[0-9一二三四五六七八九十]+[篇部]', s):
            return True, 1
        return True, 2

    # 2. 正則比對：第X篇、第X章、Chapter X
    if re.match(r'^第[0-9一二三四五六七八九十百千零〇两兩 ]+[篇部輯]', s):
        return True, 1
    if re.match(r'^第[0-9一二三四五六七八九十百千零〇两兩 ]+[章回节節集]', s):
        return True, 2
    if re.match(r'^(?:Chapter|Part)\s+[0-9IVXLCDM]+', s, re.I):
        return True, 2
    if re.match(r'^(?:Section)\s+[0-9IVXLCDM]+', s, re.I):
        return True, 3

    # 3. 數字小節層級：1.1, 1.1.1 等
    if re.match(r'^[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?[\s：:]+[^\n。！？!?]{1,40}$', s):
        return True, 3
    if re.match(r'^[0-9]+\.[0-9]+[\s：:]+[^\n。！？!?]{1,40}$', s):
        return True, 2

    # 4. 固定結構標題
    if re.match(r'^(?:版权信息|版權資訊|版权声明|版權聲明|内容提要|內容提要|关于作者|關於作者|致谢|致謝|前言|序言|导言|導讀|结语|後記|附录)\b', s):
        return True, 2

    return False, 0


def check_calibre_available() -> Tuple[bool, str]:
    """檢查系統是否安裝 Calibre ebook-convert 轉換工具"""
    calibre_bin = shutil.which("ebook-convert")
    if calibre_bin:
        return True, calibre_bin
    return False, ""


def convert_pdf_with_calibre(
    pdf_path: str,
    output_epub_path: str,
    options: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Dict[str, Any]:
    """
    使用外部開源工具 Calibre ebook-convert 進行 PDF 直轉 EPUB：
    - 啟用啟發式排版修復 (--enable-heuristics, --unwrap-factor=0.45)
    - 啟用智慧標點轉換 (--smarten-punctuation)
    - 注入中繼資料、作者與繁簡語言標籤
    """
    has_calibre, calibre_bin = check_calibre_available()
    if not has_calibre:
        return {"success": False, "error": "系統未安裝 Calibre (找不到 ebook-convert 工具)"}

    opts = options or {}
    meta = extract_pdf_metadata(pdf_path)
    book_title = opts.get("bookname") or meta.get("title") or os.path.splitext(os.path.basename(pdf_path))[0]
    author_name = opts.get("author") or meta.get("author") or "YSTYLE"
    zh_mode = opts.get("zh_mode") or opts.get("zh") or "s2tw"

    if log_callback:
        log_callback(f"[CALIBRE] 啟動 Calibre ebook-convert 轉換: {os.path.basename(pdf_path)}")
        log_callback(f"[CALIBRE] 書名: 《{book_title}》, 作者: {author_name}, 語言模式: {zh_mode}")

    if progress_callback:
        progress_callback(0.15, "[Calibre] 正在使用 Calibre 解析 PDF 並啟動啟發式排版重構...")

    cmd = [
        calibre_bin,
        pdf_path,
        output_epub_path,
        "--enable-heuristics",
        "--unwrap-factor=0.45",
        "--smarten-punctuation",
        f"--title={book_title}",
        f"--authors={author_name}",
        f"--language={'zh-TW' if zh_mode in ['s2tw', 's2hk', 's2t'] else 'zh-CN'}"
    ]

    cover_path = opts.get("cover")
    if cover_path and os.path.exists(cover_path):
        cmd.extend([f"--cover={cover_path}"])

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        if proc.stdout:
            for line in proc.stdout:
                line_str = line.strip()
                if not line_str:
                    continue
                pct_m = re.search(r'(\d+)%', line_str)
                if pct_m and progress_callback:
                    pct = int(pct_m.group(1))
                    progress_callback(0.15 + (pct / 100.0) * 0.80, f"[Calibre] 正在轉換 ({pct}%): {line_str[:50]}")
                if log_callback and any(k in line_str for k in ["Converting", "EPUB", "Saved", "paragraph"]):
                    log_callback(f"[CALIBRE] {line_str}")

        proc.wait(timeout=300)
        if proc.returncode != 0 or not os.path.exists(output_epub_path):
            return {"success": False, "error": f"Calibre 轉換失敗 (退出代碼 {proc.returncode})"}

        file_sz = os.path.getsize(output_epub_path)
        msg = f"✓ Calibre 直轉 EPUB 成功！檔案大小: {file_sz / 1024:.1f} KB"
        if log_callback:
            log_callback(f"[SUCCESS] {msg} -> {output_epub_path}")
        if progress_callback:
            progress_callback(1.0, msg)

        return {
            "success": True,
            "output_path": output_epub_path,
            "output_files": [output_epub_path],
            "size": file_sz,
            "message": msg
        }
    except Exception as e:
        return {"success": False, "error": f"Calibre 執行異常: {str(e)}"}


def parse_font_classes(soup: BeautifulSoup) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """
    從 HTML <style> 標籤中解析 Poppler 輸出的 .ftXX 字型規則：
    處理 Poppler 僅在首頁輸出樣式宣告，後續頁面以 ft<頁碼><字型索引> 引用之特性。
    回傳: (font_map, body_font_size)
    """
    font_map: Dict[str, Dict[str, Any]] = {}
    font_by_index: List[Dict[str, Any]] = []

    for style_tag in soup.find_all("style"):
        style_text = style_tag.get_text()
        for m in re.finditer(r'\.([a-zA-Z0-9_-]+)\s*\{([^}]+)\}', style_text):
            cls, rules = m.group(1), m.group(2)
            fs_m = re.search(r'font-size:\s*(\d+)px', rules)
            ff_m = re.search(r'font-family:\s*([^;]+)', rules)
            fw_m = re.search(r'font-weight:\s*bold', rules, re.I)
            fam = ff_m.group(1).strip() if ff_m else ""
            is_bold = bool(fw_m) or ("bold" in fam.lower())
            is_mono = any(k in fam.lower() for k in [
                "courier", "mono", "consolas", "menlo", "fixed", "terminal", 
                "source code", "fira code", "dejavu sans mono"
            ])
            info = {
                "size": int(fs_m.group(1)) if fs_m else 14,
                "family": fam,
                "is_mono": is_mono,
                "is_bold": is_bold
            }
            font_map[cls] = info
            if cls.startswith("ft"):
                font_by_index.append(info)

    # 填補 Poppler 在後續頁面中產生的 ft<page_num><font_idx> 缺失樣式
    for pdiv in soup.find_all("div", id=re.compile(r'page\d+-div')):
        m = re.search(r'page(\d+)-div', pdiv.get("id", ""))
        pnum = m.group(1) if m else ""
        for p in pdiv.find_all("p"):
            cls = p.get("class", [""])[0] if p.get("class") else ""
            if cls and cls not in font_map:
                if cls.startswith("ft" + pnum):
                    fidx_str = cls[len("ft" + pnum):]
                    if fidx_str.isdigit():
                        idx = int(fidx_str)
                        if idx < len(font_by_index):
                            font_map[cls] = font_by_index[idx]
                elif re.match(r'^ft\d+$', cls):
                    for fidx in range(len(font_by_index) - 1, -1, -1):
                        if cls.endswith(str(fidx)):
                            font_map[cls] = font_by_index[fidx]
                            break

    # 計算正文基準字號 (以出現字元數最多之非等寬字型大小為準)
    from collections import Counter
    char_counts: Counter = Counter()
    for p in soup.find_all("p"):
        cls = p.get("class", [""])[0] if p.get("class") else ""
        if cls in font_map and not font_map[cls]["is_mono"]:
            char_counts[font_map[cls]["size"]] += len(p.get_text().strip())
    body_size = char_counts.most_common(1)[0][0] if char_counts else 14
    return font_map, body_size


def filter_running_headers_footers(soup: BeautifulSoup, outline_titles: set):
    """
    清除出現在頁面邊界頂部 (top <= 8%) 或底部 (top >= 90%) 的頁首頁尾與純頁碼
    避免頁首頁尾穿插於段落中間阻斷閱讀流
    """
    page_num_pat = re.compile(
        r'^\s*[-—·~_\[\(]?\s*(?:(?:Page|page|PAGE|P\.|p\.|第)\s*[-—·~_]*\s*)?(?:\d+|[ivx]{2,5}|[IVX]{2,5})(?:\s*(?:/|of|之)\s*(?:\d+|[ivx]+|[IVX]+)|\s*[頁页])?\s*[-—·~_\]\)]?\s*$',
        re.I
    )
    page_divs = soup.find_all("div", id=re.compile(r'page\d+-div'))
    for pdiv in page_divs:
        # 取得頁面高度
        st = pdiv.get("style", "")
        h_m = re.search(r'height:\s*(\d+)px', st)
        page_h = int(h_m.group(1)) if h_m else 1188

        for p in pdiv.find_all("p"):
            p_st = p.get("style", "")
            tm = re.search(r'top:\s*(\d+)px', p_st)
            if not tm:
                continue
            top_y = int(tm.group(1))
            txt = p.get_text().strip()

            # 任何位置的純頁碼與 Page X 標籤
            if page_num_pat.match(txt):
                p.decompose()
                continue

            # 底部頁碼與頁尾
            if top_y >= page_h * 0.90:
                if len(txt) <= 30:
                    p.decompose()
                    continue

            # 頂部頁首 (Running Header)
            if top_y <= page_h * 0.08:
                if txt in outline_titles or re.match(r'^(?:Chapter|Part|第[0-9一二三四五六七八九十]+[章卷回]|內容提要)\b', txt, re.I) or len(txt) <= 45:
                    p.decompose()
                    continue


def calc_span_width(text: str, f_size: int) -> float:
    """估算文字在 PDF 頁面中佔用的像素寬度 (中文字元約 1.0 em，英數約 0.55 em)"""
    cjk_count = len(re.findall(r'[\u4e00-\u9fa5，。！？、；：“”‘’（）《》【】—]', text))
    ascii_count = len(text) - cjk_count
    return cjk_count * f_size + ascii_count * (f_size * 0.55)


def merge_horizontal_spans(soup: BeautifulSoup, font_map: Optional[Dict[str, Dict[str, Any]]] = None):
    """
    將同一行中因字元間距、字型微調或 PDF 排版運算元拆散的多個水平相鄰 <p> 標籤，
    由左至右平滑拼接為單一完整的標籤。
    採用實體物理右邊界追蹤 (Physical Right-Edge Tracking)，精確計算跨片段間距，
    避免將標題（如「一」「粒大」「豆的史詩」）或同一行正文誤判為多欄表格。
    """
    font_map = font_map or {}
    page_divs = soup.find_all("div", id=re.compile(r'page\d+-div'))
    if not page_divs:
        page_divs = [soup]

    for pdiv in page_divs:
        p_list = list(pdiv.find_all("p"))
        if not p_list:
            continue

        items = []
        for p in p_list:
            st = p.get("style", "")
            tm = re.search(r'top:\s*(\d+)px', st)
            lm = re.search(r'left:\s*(\d+)px', st)
            if tm and lm:
                cls = p.get("class", [""])[0] if p.get("class") else ""
                f_size = font_map.get(cls, {}).get("size", 16)
                items.append({
                    "node": p,
                    "top": int(tm.group(1)),
                    "left": int(lm.group(1)),
                    "font_size": f_size,
                    "text": p.get_text()
                })

        if len(items) <= 1:
            continue

        # 依 Y 軸 (top) 分群為行 (容許約 15px 的標點/上下標微小偏移)
        items.sort(key=lambda x: x["top"])
        line_clusters: List[List[Dict[str, Any]]] = []
        for it in items:
            placed = False
            for cl in line_clusters:
                avg_top = sum(x["top"] for x in cl) / len(cl)
                if abs(it["top"] - avg_top) <= 15:
                    cl.append(it)
                    placed = True
                    break
            if not placed:
                line_clusters.append([it])

        for cl in line_clusters:
            if len(cl) <= 1:
                continue
            # 同一行群集內，嚴格按照 X 軸 (left) 由左向右排序
            cl.sort(key=lambda x: x["left"])

            merged_chain = [cl[0]]
            curr_right = cl[0]["left"] + calc_span_width(cl[0]["text"], cl[0]["font_size"])

            for next_it in cl[1:]:
                prev_it = merged_chain[-1]
                f_size = max(prev_it["font_size"], next_it["font_size"])
                next_w = calc_span_width(next_it["text"], next_it["font_size"])

                # 以當前已拼接片段的實體右邊界計算真實間隙
                gap = next_it["left"] - curr_right

                # 若兩塊文字水平緊鄰 (gap < 55px 或小於 2.5 個字符寬度)，說明為同一句中的連續字詞而非分欄
                if gap < max(f_size * 2.5, 55):
                    p_char = prev_it["text"][-1] if prev_it["text"] else ""
                    n_char = next_it["text"][0] if next_it["text"] else ""
                    if p_char.isascii() and p_char.isalnum() and n_char.isascii() and n_char.isalnum():
                        prev_it["text"] += " " + next_it["text"]
                    else:
                        prev_it["text"] += next_it["text"]

                    prev_it["node"].string = prev_it["text"]
                    curr_right = max(curr_right, next_it["left"] + next_w)
                    if next_it["node"].parent:
                        next_it["node"].decompose()
                else:
                    merged_chain.append(next_it)
                    curr_right = next_it["left"] + next_w


def is_narrative_sentence_cell(text: str) -> bool:
    """判斷單元格文字是否為普通流式句子碎片而非表格資料格"""
    s = text.strip()
    if not s:
        return False
    # 若以逗點、句號、冒號、分號或句子未完結助詞結尾，絕非表格欄位
    if re.search(r'[，、；：。！？!?,]$|[的在和與与及或有等而且]$', s):
        return True
    # 若單元格內包含多個句讀標點符號，為長段落敘事
    if len(re.findall(r'[，。！？；]', s)) >= 2:
        return True
    return False


def reconstruct_tables_in_soup(soup: BeautifulSoup, font_map: Optional[Dict[str, Dict[str, Any]]] = None):
    """
    依據 Poppler 原生輸出的 top 與 left 幾何座標，自動辨識並熔合多欄數據表格：
    - 嚴格要求至少 2 列以上的網格結構 (len(tbl_rows) >= 2)
    - 欄位之間必須有顯著的物理水平間距 (gap >= 40px)
    - 各列的欄數與水平起始座標必須垂直對齊
    - 排除普通敘事句子被誤判為表格的情況 (禁止逗號/句讀結尾與連續語意分欄)
    """
    font_map = font_map or {}
    page_divs = soup.find_all("div", id=re.compile(r'page\d+-div'))
    if not page_divs:
        page_divs = [soup]

    for pdiv in page_divs:
        p_list = list(pdiv.find_all("p"))
        if not p_list:
            continue

        items = []
        for p in p_list:
            st = p.get("style", "")
            tm = re.search(r'top:\s*(\d+)px', st)
            lm = re.search(r'left:\s*(\d+)px', st)
            if tm and lm:
                cls = p.get("class", [""])[0] if p.get("class") else ""
                f_size = font_map.get(cls, {}).get("size", 16)
                items.append({
                    "node": p,
                    "top": int(tm.group(1)),
                    "left": int(lm.group(1)),
                    "font_size": f_size,
                    "text": p.get_text().strip()
                })

        i = 0
        while i < len(items):
            # 探測第一列：相鄰欄位 |top1 - top2| <= 5px，且欄位之間有實質水平間隙 (gap >= 40px)
            row1 = [items[i]]
            j = i + 1
            while j < len(items) and abs(items[j]["top"] - row1[0]["top"]) <= 5 and items[j]["left"] > row1[-1]["left"]:
                prev_w = calc_span_width(row1[-1]["text"], row1[-1]["font_size"])
                gap = items[j]["left"] - (row1[-1]["left"] + prev_w)
                if gap >= 40:
                    row1.append(items[j])
                    j += 1
                else:
                    break

            # 嚴格規則：橫向具有 >= 2 欄，單元格文字長度適合表格 (< 35 字元)，且非流水敘事句子
            if len(row1) >= 2 and all(len(c["text"]) < 35 and not is_narrative_sentence_cell(c["text"]) for c in row1):
                tbl_rows = [row1]
                curr_j = j
                while curr_j < len(items):
                    next_row = [items[curr_j]]
                    k = curr_j + 1
                    while k < len(items) and abs(items[k]["top"] - next_row[0]["top"]) <= 5 and items[k]["left"] > next_row[-1]["left"]:
                        prev_w = calc_span_width(next_row[-1]["text"], next_row[-1]["font_size"])
                        gap = items[k]["left"] - (next_row[-1]["left"] + prev_w)
                        if gap >= 40:
                            next_row.append(items[k])
                            k += 1
                        else:
                            break

                    # 必須具備相同的欄數，且欄位起始位置基本垂直對齊 (|col_x - col0_x| <= 35px)
                    if len(next_row) == len(row1) and abs(next_row[0]["top"] - tbl_rows[-1][0]["top"]) <= 50:
                        aligned = all(abs(next_row[c_idx]["left"] - tbl_rows[0][c_idx]["left"]) <= 35 for c_idx in range(len(row1)))
                        valid_cells = all(len(c["text"]) < 35 and not is_narrative_sentence_cell(c["text"]) for c in next_row)
                        if aligned and valid_cells:
                            tbl_rows.append(next_row)
                            curr_j = k
                        else:
                            break
                    else:
                        break

                # 關鍵：必須至少 2 列且欄位對齊才建立 HTML <table>（絕不生成 1 列的偽表格）
                if len(tbl_rows) >= 2:
                    tbl_tag = soup.new_tag("table")
                    thead = soup.new_tag("thead")
                    tr_head = soup.new_tag("tr")
                    for cell in tbl_rows[0]:
                        th = soup.new_tag("th")
                        th.string = cell["text"]
                        tr_head.append(th)
                    thead.append(tr_head)
                    tbl_tag.append(thead)

                    tbody = soup.new_tag("tbody")
                    for row_cells in tbl_rows[1:]:
                        tr_body = soup.new_tag("tr")
                        for cell in row_cells:
                            td = soup.new_tag("td")
                            td.string = cell["text"]
                            tr_body.append(td)
                        tbody.append(tr_body)
                    tbl_tag.append(tbody)

                    first_node = tbl_rows[0][0]["node"]
                    first_node.insert_before(tbl_tag)
                    for r in tbl_rows:
                        for cell in r:
                            if cell["node"].parent:
                                cell["node"].decompose()
                    i = curr_j
                    continue
            i += 1


def fuse_figures_and_captions(soup: BeautifulSoup):
    """
    將提取出之獨立圖片與緊隨其後之圖表標註 (Figure 1-1, 圖 1-1 等) 融合為 <figure><figcaption>
    """
    caption_pat = re.compile(r'^(?:Figure|Fig\.|圖|表|Illustration|Image)\s*[\d\.\-一二三四五六七八九十]+[\s：:]', re.I)
    for img in soup.find_all("img"):
        if not img.parent:
            continue
        next_sib = img.find_next_sibling()
        if next_sib and next_sib.name == "p":
            txt = next_sib.get_text().strip()
            if caption_pat.match(txt) or (len(txt) < 80 and any(k in txt for k in ["圖", "表", "Figure", "Fig."])):
                fig_tag = soup.new_tag("figure")
                img.wrap(fig_tag)
                cap_tag = soup.new_tag("figcaption")
                cap_tag.string = txt
                fig_tag.append(cap_tag)
                next_sib.decompose()


def clean_and_restructure_html(
    html_content: str,
    outline_info: Optional[Dict[str, Any]] = None,
    zh_mode: str = "s2tw",
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    次世代幾何座標與字體語意高保真重構引擎：
    1. 解析 Poppler 原生 CSS 字型映射 (字號大小、等寬字型判定)
    2. 自動辨識並清除頁面邊界處的重複頁首頁尾 (Running Headers/Footers)
    3. 幾何座標空間融合多欄數據表格 (Reconstruct <table>)
    4. 字型與語法雙軌保護程式碼區塊 (<pre class="code-block"><code>)
    5. 多級大綱與相對字號標題提升 (<h1>, <h2>, <h3>)
    6. 斷字修復與平滑流式重排 (De-hyphenation & Line-unwrap)
    7. 插圖與圖說關聯融合 (<figure><figcaption>)
    8. 安全繁簡中文轉換 (保護 LaTeX 數學公式與標籤)
    """
    soup = BeautifulSoup(html_content, "html.parser")
    outline_titles = {it["title"] for it in outline_info.get("flat_outline", [])} if outline_info else set()

    # 0. 移除所有 HTML 註解 (如 <!-- Page 1 -->、<!-- Page 2 --> 等)
    # 避免後續節點替換或 Pandoc 解析時被誤當作正文段落輸出
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # 清除 pdftohtml 在文末產生的冗餘 Document Outline 錨點及其章節清單 (避免 Pandoc 產生重複目錄頁)
    outline_anchor = soup.find("a", attrs={"name": "outline"})
    if outline_anchor:
        curr = outline_anchor.next_sibling
        while curr:
            nxt = curr.next_sibling
            curr.extract()
            curr = nxt
        outline_anchor.extract()

    # 清除 pdftohtml 輸出的空白頁面錨點標籤 (如 <a name="1"></a>)
    for a_tag in soup.find_all("a", attrs={"name": re.compile(r'^\d+$')}):
        if not a_tag.get_text().strip():
            a_tag.decompose()

    # 1. 解析字型樣式表
    font_map, body_size = parse_font_classes(soup)
    if log_callback:
        log_callback(f"[LAYOUT] 字型分析完成：共識別 {len(font_map)} 組字型樣式，文件正文基準字號: {body_size}px")

    # 2. 清除背景大圖與水平雜訊
    for hr in soup.find_all("hr"):
        hr.decompose()
    for img in soup.find_all("img"):
        if img.get("alt") == "background image" or (img.get("width") == "918" and img.get("height") == "1188"):
            img.decompose()

    # 3. 清除頁首頁尾雜訊
    filter_running_headers_footers(soup, outline_titles)

    # 4. 水平相鄰文字碎片平滑拼接 (消除同一行標題/正文因字距或運算元產生的碎片)
    merge_horizontal_spans(soup, font_map)

    # 5. 幾何座標數據表格熔合
    reconstruct_tables_in_soup(soup, font_map)

    # 6. 插圖與圖說融合
    fuse_figures_and_captions(soup)

    # 7. 遍歷處理段落、代碼區塊與標題
    p_tags = list(soup.find_all("p"))
    i = 0
    total_p = len(p_tags)
    page_num_pat = re.compile(
        r'^\s*[-—·~_\[\(]?\s*(?:(?:Page|page|PAGE|P\.|p\.|第)\s*[-—·~_]*\s*)?(?:\d+|[ivx]{2,5}|[IVX]{2,5})(?:\s*(?:/|of|之)\s*(?:\d+|[ivx]+|[IVX]+)|\s*[頁页])?\s*[-—·~_\]\)]?\s*$',
        re.I
    )

    while i < total_p:
        if progress_callback and total_p > 0 and (i % 80 == 0 or i == total_p - 1):
            ratio = i / total_p
            progress_callback(0.40 + 0.15 * ratio, f"[步驟 3/4] 🧹 幾何語意重排中 (段落 {i}/{total_p})...")

        p = p_tags[i]
        if not p.parent:
            i += 1
            continue

        raw_txt = p.get_text()
        stripped = raw_txt.strip()

        # 過濾空行或純頁碼
        if not stripped or page_num_pat.match(stripped):
            p.decompose()
            i += 1
            continue

        cls = p.get("class", [""])[0] if p.get("class") else ""
        f_info = font_map.get(cls, {"size": body_size, "is_mono": False, "is_bold": False})

        # 標題識別 (結合大綱、正則與相對字號)
        is_hd, level = is_heading_candidate(stripped, outline_titles)
        if not is_hd and not f_info["is_mono"]:
            if f_info["size"] >= body_size * 1.45 and len(stripped) < 70:
                is_hd, level = True, 1
            elif f_info["size"] >= body_size * 1.22 and len(stripped) < 60 and not stripped.endswith((".", "。", "！", "？")):
                is_hd, level = True, 2
            elif f_info["size"] >= body_size * 1.10 and f_info["is_bold"] and len(stripped) < 50:
                is_hd, level = True, 3

        if is_hd:
            hd_tag = soup.new_tag(f"h{level}")
            hd_tag.string = stripped
            p.replace_with(hd_tag)
            i += 1
            continue

        # 程式碼區塊識別 (等寬字型或命令提示字元)
        if f_info["is_mono"] or is_code_or_prompt_line(stripped):
            code_lines = [p.get_text()]
            curr_idx = i + 1
            nodes_to_remove = []

            while curr_idx < total_p:
                next_p = p_tags[curr_idx]
                if not next_p.parent:
                    curr_idx += 1
                    continue
                next_txt = next_p.get_text().strip()
                if not next_txt:
                    nodes_to_remove.append(next_p)
                    curr_idx += 1
                    continue

                n_cls = next_p.get("class", [""])[0] if next_p.get("class") else ""
                n_info = font_map.get(n_cls, {"size": body_size, "is_mono": False})

                # 若下一行仍為等寬字型或程式碼特徵
                if n_info["is_mono"] or is_code_or_prompt_line(next_txt):
                    code_lines.append(next_p.get_text())
                    nodes_to_remove.append(next_p)
                    curr_idx += 1
                else:
                    break

            pre_tag = soup.new_tag("pre", **{"class": "code-block"})
            code_tag = soup.new_tag("code")
            code_tag.string = "\n".join(code_lines)
            pre_tag.append(code_tag)

            p.replace_with(pre_tag)
            for rm_n in nodes_to_remove:
                rm_n.decompose()

            i = curr_idx
            continue

        # 段落自然拼接與英文斷字修復 (De-hyphenation & Soft-wrap Unrolling)
        curr_merged_text = stripped
        curr_idx = i + 1
        nodes_to_remove = []

        while curr_idx < total_p:
            next_p = p_tags[curr_idx]
            if not next_p.parent:
                curr_idx += 1
                continue
            next_txt = next_p.get_text().strip()
            if not next_txt:
                curr_idx += 1
                continue

            n_cls = next_p.get("class", [""])[0] if next_p.get("class") else ""
            n_info = font_map.get(n_cls, {"size": body_size, "is_mono": False, "is_bold": False})

            # 若下一行為程式碼、標題或字型顯著改變，則停止拼接
            if n_info["is_mono"] or is_code_or_prompt_line(next_txt):
                break
            n_is_hd, _ = is_heading_candidate(next_txt, outline_titles)
            if n_is_hd or n_info["size"] >= body_size * 1.2:
                break

            # 英文行尾連字號修復 (e.g. "confor-" + "mity" -> "conformity")
            if curr_merged_text.endswith("-") and len(curr_merged_text) > 1 and curr_merged_text[-2].isalpha() and next_txt[0].isalpha():
                curr_merged_text = curr_merged_text[:-1] + next_txt
                nodes_to_remove.append(next_p)
                curr_idx += 1
            # 中文連續行拼接 (非句末標點符號則直接相接無空格)
            elif curr_merged_text[-1] not in "。！？!?":
                is_cjk_curr = '\u4e00' <= curr_merged_text[-1] <= '\u9fa5' or curr_merged_text[-1] in "，、；："
                is_cjk_next = '\u4e00' <= next_txt[0] <= '\u9fa5'
                if is_cjk_curr and is_cjk_next:
                    curr_merged_text += next_txt
                else:
                    curr_merged_text += " " + next_txt
                nodes_to_remove.append(next_p)
                curr_idx += 1
            else:
                break

        p.string = curr_merged_text
        for rm_n in nodes_to_remove:
            rm_n.decompose()

        i = curr_idx

    # 7. 清理非表格標籤的絕對定位樣式，還原為標準流式排版
    for tag in soup.find_all(True):
        if tag.name not in ["table", "thead", "tbody", "tr", "th", "td", "img", "pre", "code"]:
            tag.attrs.pop("style", None)
            tag.attrs.pop("class", None)

    # 8. 內文簡繁轉換 (僅轉換文字節點，完全保護 HTML 標籤、圖片路徑與 LaTeX 數學公式)
    if zh_mode and zh_mode.lower() != "none":
        if progress_callback:
            progress_callback(0.55, f"[步驟 3/4] 🌏 正在執行安全繁簡轉換 ({zh_mode}，保護數學公式)...")
        for text_node in soup.find_all(string=True):
            if isinstance(text_node, Comment):
                continue
            if isinstance(text_node, NavigableString):
                if text_node.parent and text_node.parent.name in ["code", "pre", "math", "annotation", "svg"]:
                    continue
                orig = str(text_node)
                if orig.strip():
                    text_node.replace_with(convert_text_preserving_math(orig, mode=zh_mode))

    if progress_callback:
        progress_callback(0.65, "[步驟 3/4] ✓ 次世代幾何語意排版重構完成")

    return str(soup)


def convert_pdf_to_epub_direct(
    pdf_path: str,
    output_epub_path: str,
    options: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Dict[str, Any]:
    """
    主要入口：直接將 PDF 轉換為高畫質 EPUB 電子書 (Pandoc + pdftohtml 核心)
    """
    if not os.path.exists(pdf_path):
        return {"success": False, "error": f"找不到 PDF 檔案: {pdf_path}"}

    opts = options or {}
    engine = opts.get("direct_engine", "smart")

    # 若指定使用 Calibre 引擎且系統已安裝
    if engine == "calibre":
        has_calibre, _ = check_calibre_available()
        if has_calibre:
            return convert_pdf_with_calibre(
                pdf_path=pdf_path,
                output_epub_path=output_epub_path,
                options=options,
                log_callback=log_callback,
                progress_callback=progress_callback
            )
        else:
            if log_callback:
                log_callback("[DIRECT-PDF] ⚠️ 系統未安裝 Calibre (ebook-convert)，自動切換至內建 Smart Poppler + Pandoc 高保真引擎...")

    has_html, has_pandoc, err_msg = check_direct_converter_dependencies()
    if not (has_html and has_pandoc):
        return {"success": False, "error": err_msg}

    # 1. 擷取元資料與大綱目錄
    if progress_callback:
        progress_callback(0.05, "[步驟 1/4] 📄 正在讀取 PDF 內嵌大綱書籤與中繼資料...")
    if log_callback:
        log_callback(f"[DIRECT-PDF] 啟動高保真直接轉換: {os.path.basename(pdf_path)}")

    meta = extract_pdf_metadata(pdf_path)
    outline = extract_pdf_outline(pdf_path)

    book_title = opts.get("bookname") or meta.get("title") or os.path.splitext(os.path.basename(pdf_path))[0]
    author_name = opts.get("author") or meta.get("author") or "YSTYLE"
    zh_mode = opts.get("zh_mode") or opts.get("zh") or "s2tw"

    if log_callback:
        log_callback(f"[DIRECT-PDF] 書名: 《{book_title}》, 作者: {author_name}, 繁簡模式: {zh_mode}")
        if outline.get("has_outline"):
            log_callback(f"[DIRECT-PDF] 📑 成功提取 PDF 內嵌大綱目錄 (共 {outline.get('total_items', 0)} 個節點)")

    # 2. 建立臨時工作目錄並探測總頁數
    total_pages = meta.get("pages") or 0
    if not total_pages:
        try:
            p_info = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True, timeout=5)
            m_p = re.search(r'Pages:\s+(\d+)', p_info.stdout)
            if m_p:
                total_pages = int(m_p.group(1))
        except Exception:
            pass

    tmp_work_dir = tempfile.mkdtemp(prefix="kaf_direct_pdf_")
    try:
        raw_html_path = os.path.join(tmp_work_dir, "book_raw.html")
        cleaned_html_path = os.path.join(tmp_work_dir, "book_cleaned.html")
        custom_css_path = os.path.join(tmp_work_dir, "custom.css")

        page_info_str = f" (共 {total_pages} 頁)" if total_pages > 0 else ""
        if progress_callback:
            progress_callback(0.10, f"[步驟 2/4] 🖼️ 正在啟動 pdftohtml 抽取版面結構與插圖{page_info_str}...")
        if log_callback:
            log_callback(f"[DIRECT-PDF] 正在抽取 PDF 幾何排版、文字、圖表與插圖 (pdftohtml -s -noframes){page_info_str}...")

        # 執行 pdftohtml (逐頁解析進度輸出)
        cmd_html = ["pdftohtml", "-s", "-noframes", pdf_path, raw_html_path]
        proc = subprocess.Popen(
            cmd_html,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=tmp_work_dir,
            bufsize=1
        )

        cur_p = 0
        if proc.stdout:
            for line in proc.stdout:
                m_pg = re.search(r'Page-(\d+)', line)
                if m_pg:
                    cur_p = int(m_pg.group(1))
                    if total_pages > 0:
                        ratio = min(cur_p / total_pages, 1.0)
                        prog_val = 0.10 + 0.30 * ratio
                        pct_text = f"{int(ratio * 100)}%"
                        msg = f"[步驟 2/4] 🖼️ 抽取版面結構與插圖中 (第 {cur_p}/{total_pages} 頁，{pct_text})..."
                    else:
                        prog_val = min(0.10 + 0.005 * cur_p, 0.38)
                        msg = f"[步驟 2/4] 🖼️ 抽取版面結構與插圖中 (已完成第 {cur_p} 頁)..."

                    if progress_callback:
                        progress_callback(prog_val, msg)
                    if log_callback and (cur_p == 1 or cur_p % 20 == 0 or (total_pages and cur_p == total_pages)):
                        log_callback(f"[DIRECT-PDF] 正在抽取頁面 {cur_p}/{total_pages or '未知'} ({int(ratio * 100) if total_pages else ''}%)")

        proc.wait(timeout=300)
        stderr_out = proc.stderr.read() if proc.stderr else ""
        if proc.returncode != 0 or not os.path.exists(raw_html_path):
            return {"success": False, "error": f"pdftohtml 提取失敗: {stderr_out}"}

        # 3. 語意化清理、代碼區塊封裝與繁簡轉換 (保護 LaTeX 數學公式)
        if progress_callback:
            progress_callback(0.40, "[步驟 3/4] 🧹 正在執行 HTML 語意重構、代碼區塊保護與繁體轉換...")
        if log_callback:
            log_callback("[DIRECT-PDF] 正在執行語意結構重整（標題對齊、代碼與數據表格保護、數學公式保護、繁簡轉換）...")

        with open(raw_html_path, "r", encoding="utf-8", errors="replace") as f_in:
            raw_html_str = f_in.read()

        structured_html = clean_and_restructure_html(
            raw_html_str,
            outline_info=outline,
            zh_mode=zh_mode,
            log_callback=log_callback,
            progress_callback=progress_callback
        )

        with open(cleaned_html_path, "w", encoding="utf-8") as f_out:
            f_out.write(structured_html)

        # 寫入專用 CSS (含 MathML 與代碼高保真樣式)
        with open(custom_css_path, "w", encoding="utf-8") as f_css:
            f_css.write(DEFAULT_DIRECT_EPUB_CSS)

        # 4. 準備封面
        cover_image_path = None
        cover_mode = opts.get("cover_mode", "auto")
        if cover_mode == "orly":
            orly_color = opts.get("orly_color", "")
            orly_idx = int(opts.get("orly_idx", -1))
            temp_cov = os.path.join(tmp_work_dir, "cover.png")
            generate_orly_cover(book_title, author_name, temp_cov, orly_color, orly_idx)
            if os.path.exists(temp_cov):
                cover_image_path = temp_cov
        elif opts.get("cover") and os.path.exists(opts["cover"]):
            cover_image_path = opts["cover"]

        # 5. 呼叫 Pandoc 編譯生成 EPUB (支援 MathML LaTeX 數學公式渲染)
        if progress_callback:
            progress_callback(0.70, "[步驟 4/4] 📚 正在呼叫 Pandoc 編譯生成標準 EPUB 3 電子書...")
        if log_callback:
            log_callback("[DIRECT-PDF] 正在呼叫 Pandoc 封裝 EPUB 3 (含嵌入式目錄、插圖媒體與 MathML 數學公式)...")

        final_epub_tmp = os.path.join(tmp_work_dir, "output.epub")
        enable_math = opts.get("enable_math", True)
        cmd_pandoc = [
            "pandoc", cleaned_html_path,
            "-f", "html+tex_math_dollars+tex_math_single_backslash+raw_tex",
            "-o", final_epub_tmp,
            "--split-level=2",
            "--css", custom_css_path,
            "--metadata", f"title={book_title}",
            "--metadata", f"author={author_name}",
            "--metadata", "lang=zh-TW" if zh_mode in ["s2tw", "s2hk", "s2t"] else "zh-CN"
        ]
        if enable_math:
            cmd_pandoc.append("--mathml")
        if cover_image_path and os.path.exists(cover_image_path):
            cmd_pandoc.extend(["--epub-cover-image", cover_image_path])

        res_pandoc = subprocess.run(cmd_pandoc, capture_output=True, text=True, cwd=tmp_work_dir, timeout=180)
        if res_pandoc.returncode != 0 or not os.path.exists(final_epub_tmp):
            return {"success": False, "error": f"Pandoc 編譯 EPUB 失敗: {res_pandoc.stderr}"}

        # 搬移至目標路徑
        out_dir = os.path.dirname(os.path.abspath(output_epub_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        shutil.copy2(final_epub_tmp, output_epub_path)

        file_sz = os.path.getsize(output_epub_path)
        success_msg = f"✓ PDF 高保真直轉 EPUB 成功！檔案大小: {file_sz / 1024:.1f} KB"
        if log_callback:
            log_callback(f"[SUCCESS] {success_msg} -> {output_epub_path}")
        if progress_callback:
            progress_callback(1.0, success_msg)

        return {
            "success": True,
            "output_path": output_epub_path,
            "output_files": [output_epub_path],
            "size": file_sz,
            "message": success_msg
        }

    except Exception as e:
        return {"success": False, "error": f"轉換過程發生異常: {str(e)}"}
    finally:
        shutil.rmtree(tmp_work_dir, ignore_errors=True)
