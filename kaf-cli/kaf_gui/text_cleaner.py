# -*- coding: utf-8 -*-
"""
text_cleaner.py: 智慧文字排版清洗器
專門解決論壇轉貼、OCR、TXT 小說中常見的「硬換行（Hard Line Break）」、「短行截斷」、
「斷句殘留」與「中文字間不自然半形空格」等排版缺陷，還原完整自然段落與流暢閱讀體驗。
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple

# 中文/英文常用句子終止標點
TERMINAL_PUNCTUATION = set('。！？!?…；;')

# 常見段落引導/結構標籤（獨立成行，不與前後文合併）
STRUCTURAL_PREFIX_REGEX = re.compile(
    r'^\s*(?:[—\-]{2,}\s*)?(?:开篇|開篇|引子|序章|序言|楔子|尾声|尾聲|后记|後記|内容简介|內容簡介|题记|題記|正文开始|正文開始|前言|導言|導論|引言|緒論|自序|結語|附錄)[—\-：:\s]*',
    re.IGNORECASE
)

# 編號小節正則（如「1，没有实力替人出头」、「一、古廟驚魂」）
NUMBERED_SUBSECTION_REGEX = re.compile(
    r'^\s*(?:[0-9]+|[一二三四五六七八九十百]+)[，,、.．\s]+.+',
    re.UNICODE
)

# 括號小節正則（如「(1)」、「（一）」）
BRACKET_SUBSECTION_REGEX = re.compile(
    r'^\s*[(（][0-9一二三四五六七八九十]+[)）]',
    re.UNICODE
)

# 中文接續助詞與方位字（若行首出現且無段落縮排，必然為跨行折斷接續）
CONTINUATION_START_CHARS = set('的得地了着著过過等之处處里裡边邊面頭头')

# 標點符號不應出現在行首（若出現，必然為折行殘留）
CLOSING_PUNCTUATION = set('”」』"\'）)]》>，。、！？；：:,')

# 常見段落論述起始引導語（若前一句已句末標點終止，強烈提示為新段落起點）
DISCOURSE_PARAGRAPH_STARTERS = re.compile(
    r'^(?:'
    r'[一-龥]{2,8}(?:也好|也罷|而言|來說)|'
    r'科學研究|科学研究|研究表明|研究指出|實驗顯示|数据显示|調查發現|'
    r'換句話說|换句话说|換言之|简而言之|總結來說|总的来说|總而言之|'
    r'事實上|事实上|實際上|不仅如此|不難看出|'
    r'與此同時|与此同时|在此背景下|'
    r'值得注意|不可否認|顯而易見|無庸置疑|'
    r'今天[，,]|如今[，,]|回顧歷史|'
    r'首先|其次|第一[，,、]|第二[，,、]|第三[，,、]|此外|另外|'
    r'根據|正如|依照'
    r')'
)

def is_discourse_paragraph_starter(line: str) -> bool:
    """判斷行首是否為強烈的段落/論述起點詞"""
    stripped = line.strip()
    return bool(DISCOURSE_PARAGRAPH_STARTERS.match(stripped))


def clean_stray_spaces_chinese(text: str) -> str:
    """
    清除中文字之間因 PDF/OCR 或論壇等寬換行產生的多餘半形空格。
    保留英文字與數字之間合理的空格（例如 "W 公司", "1990 年", "iPhone 15"）。
    """
    # 1. 漢字 + 空格 + 漢字 -> 消除空格
    text = re.sub(r'([\u4e00-\u9fa5]) +([\u4e00-\u9fa5])', r'\1\2', text)
    # 連續執行一次以消除多空格情況如「中 文 字」
    text = re.sub(r'([\u4e00-\u9fa5]) +([\u4e00-\u9fa5])', r'\1\2', text)
    # 2. 漢字 + 空格 + 中文/全形標點 -> 消除空格
    text = re.sub(r'([\u4e00-\u9fa5]) +([，。！？；：”』）》、])', r'\1\2', text)
    # 3. 中文/全形開引號 + 空格 + 漢字 -> 消除空格
    text = re.sub(r'([“『（《]) +([\u4e00-\u9fa5])', r'\1\2', text)
    return text


def is_terminal_punct(char: str) -> bool:
    """判斷字符是否為句子終結標點"""
    return char in TERMINAL_PUNCTUATION


def ends_with_sentence_terminator(line: str) -> bool:
    """
    判斷行尾是否以句末終止標點結尾（支援標點後跟右引號或括號）。
    例如「好。」、「真的嗎？」、「“快走！”」
    """
    line = line.rstrip()
    if not line:
        return False
    # 結尾為引號或括號，檢查其前一個字
    if line[-1] in '”」』"\'）)]':
        if len(line) >= 2 and is_terminal_punct(line[-2]):
            return True
        return False
    return is_terminal_punct(line[-1])


def starts_with_continuation(line: str) -> bool:
    """判斷行首是否為明顯的跨行接續字（不能作為新段落開頭）"""
    line = line.lstrip()
    if not line:
        return False
    first_char = line[0]
    if first_char in CLOSING_PUNCTUATION:
        return True
    if first_char in CONTINUATION_START_CHARS:
        return True
    return False


def starts_with_indent(raw_line: str) -> bool:
    """檢查行首是否有作者明確的段落縮排（全形空格、4個半形空格或2個半形空格）"""
    return raw_line.startswith('　') or raw_line.startswith('    ') or raw_line.startswith('  ')


def is_chapter_header(line: str, header_regex: Optional[re.Pattern] = None) -> bool:
    """是否為章節標題行（例如：第一章、作者:xxx 日期:xxx 第一章、第12节、Chapter 1、1.1 等）"""
    stripped = line.strip()
    if not stripped:
        return False

    # 標題不應包含強烈之正文敘事/列舉/轉折特徵 (如 等—, 等等, 例如, 比如, 以及) 或以句末標點結尾
    if re.search(r'等[—–\-,，、]|等等|例如|比如|以及|并且|而且|可以通过|可以通過|不仅|但是', stripped):
        return False
    if stripped.endswith(('。', '；', ';', '”', '」', '』')):
        # 標題通常不以句號、分號結尾，若引號前為句號亦排除
        if len(stripped) >= 2 and stripped[-2] in '。；;':
            return False
        if stripped.endswith(('。', '；', ';')):
            return False

    if header_regex and header_regex.match(stripped):
        return True
    if re.search(r'^\s*第[0-9一二三四五六七八九十百千零〇两兩 ]+[章回节節集卷部篇步讲講课課幕场場辑輯]', stripped):
        return True
    if re.search(r'^\s*(?:Chapter|Part|Section)\s+[0-9IVXLCDM]+', stripped, re.IGNORECASE):
        return True
    if re.search(r'^\s*(?:前言|導言|導論|引言|緒論|自序|代序|推薦序|推荐序|結語|後記|跋|參考文獻|附錄)\b', stripped):
        return True
    if re.search(r'^\s*\d+(?:\.\d+)+\s+', stripped):  # 1.1 或 1.1.1
        return True
    if re.match(r'^\s*([0-9]+\s*楼|\[--楼主:.+?--\]|作者:.+?日期:)', stripped):
        return True
    return False


def is_code_or_prompt_line(text: str) -> bool:
    """
    判斷文字行是否為程式命令提示字元、R/Python/Shell 代碼或輸出表格數據，
    此類行必須獨立成行，絕不可被自動拼接合併進正文段落。
    """
    s = text.strip()
    if not s:
        return False
    # 1. 帶有終端機或直譯器命令提示字元者 (如 > data(day1), > head(day1), $ pip install, >>>, [1] 731)
    if re.match(r'^(?:[>$#]\s+|>>>\s+|\.\.\.\s+|\+\s+|\[\d+\]\s+|\[\d+,\s*\])', s):
        return True
    # 2. 若該行包含中文字且不以代碼關鍵字開頭，則為正常中文敘述段落 (例如: 一種方法是使用R語言的head()函數...)
    has_cjk = bool(re.search(r'[\u4e00-\u9fa5]', s))
    if has_cjk:
        return False
    # 3. 無中文字且具備程式語言語法特徵 (如 <-, ==, !=, library(), predict(), function())
    if re.search(r'<-|==|!=|library\(|head\(|tail\(|summary\(|plot\(|data\(|as\.factor|read\.csv|predict\(|import\s+[a-z]|def\s+[a-z]|function\s*\(', s):
        return True
    # 4. 無中文字且為多欄等寬數值表格特徵 (例如 3 個以上數字或日期)
    num_matches = len(re.findall(r'\b\d{4}-\d{2}-\d{2}\b|\b[-+]?\d+(?:\.\d+)?\b', s))
    if num_matches >= 3:
        return True
    return False


def is_standalone_label_or_heading(line: str, header_regex: Optional[re.Pattern] = None) -> bool:
    """
    判斷該行是否為獨立結構標題、章節、題記、標籤、程式碼或編號小節，
    此類行絕不可被拼接進正文段落中。
    """
    stripped = line.strip()
    if not stripped:
        return False

    if is_chapter_header(stripped, header_regex):
        return True

    # 程式碼、終端機命令、REPL提示字元或表格數據行 (絕不可被拼接進正文段落)
    if is_code_or_prompt_line(stripped):
        return True

    # 題記、引子、序章、尾聲、開篇、後記等
    if STRUCTURAL_PREFIX_REGEX.match(stripped):
        return True

    # 編號小節，例如：1，没有实力替人出头 或 一、一个该死的项目
    if NUMBERED_SUBSECTION_REGEX.match(stripped) and len(stripped) <= 40:
        return True

    # 括號小節，例如：（一）、(1)
    if BRACKET_SUBSECTION_REGEX.match(stripped) and len(stripped) <= 40:
        return True

    # 書名、作者、簡介等結構元資訊標籤（如：書名：、作者：、內容簡介：）
    if re.match(r'^\s*(?:书名|書籍|作者|原著|简介|簡介|来源|來源|备注|備註|译者|譯者|时间|時間|地点|地點|说明|說明|正文|出版|编辑|標籤|标签|目錄|目录)[:：]', stripped):
        return True

    # 簡短純元資訊標籤行（<=10個字，末尾為冒號，且不含逗號、句號、問號、嘆號、引號等敘事標點）
    if re.match(r'^[^\s，,。！？!?…；;]{1,10}[：:]$', stripped):
        return True

    # 分隔線
    if re.match(r'^[=\-~*#]{3,}$', stripped):
        return True

    return False


def is_title_continuation(prev_header: str, line: str) -> bool:
    """
    判斷 line 是否為上一行章節標題折行的後半段副標題或未完結標題延續
    例如：上一行「第1章西方传说中的“青春之泉”里会有什么」，下一行「样的微生物」
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 30:
        return False
    # 副標題不應以句末標點或逗點結尾，亦不可含有子句逗號
    if any(p in stripped for p in '，,。！？!?…；;'):
        return False
    # 主標題若已達到完整長度（超過 40 字），不應再貪婪接續
    if len(prev_header) > 40:
        return False
    # 正文代名詞（我、我們、你、他、她、它、這、那等）開頭，必為正文而非標題折行
    if re.match(r'^(?:我们|我們|我|你|你們|他|他們|她|她們|它|它們|這|這裏|这里|那|那裏|那里)\b', stripped):
        return False
    # 上一行必須是章節標題，且上一行結尾不能已有結束標點
    if not is_chapter_header(prev_header) or ends_with_sentence_terminator(prev_header):
        return False
    # 若下一行是新的章節或獨立結構標籤，不可接續
    if is_standalone_label_or_heading(stripped):
        return False
    return True


def remove_hard_breaks(
    text: str,
    header_regex_str: str = "",
    keep_empty_lines_between_paragraphs: bool = True,
    indent_paragraphs: bool = True
) -> str:
    """
    智慧移除文本中因 PDF、論壇、排版或 OCR 造成的強制換行（硬換行），
    還原自然段落與流暢語句。
    
    規則：
    1. 清理中文字之間的異常斷行殘留空格。
    2. 保護章節標題、小節編號、題記與對話開頭。
    3. 自動合併未結束之跨行句子、逗號結尾行與接續助詞行。
    4. 智慧識別並合併被折行的章節標題與副標題（中文字元間不補多餘半形空格）。
    5. 依據標點符號、行尾長度（排版未滿行）、段落縮排與論述引導詞，精確重建段落邊界。
    6. 正文段落添加標準中文全形縮排（　　），段落間以標準空行區隔，格式化為符合 EPUB / TXT 典雅標準之書籍文本。
    """
    if not text:
        return ""

    header_pat = re.compile(header_regex_str, re.MULTILINE) if header_regex_str else None

    raw_lines = text.splitlines()
    if not raw_lines:
        return ""

    # 計算排版正文行的典型長度（排版行寬基準）
    candidate_lengths = [len(l.strip()) for l in raw_lines if len(l.strip()) >= 15]
    typical_line_len = max(candidate_lengths) if candidate_lengths else 35

    paragraphs: List[str] = []
    current_para: List[str] = []
    prev_had_blank = False
    last_was_header = False

    for line in raw_lines:
        stripped = line.strip()

        # 空行：標記前置有空行
        if not stripped:
            prev_had_blank = True
            continue

        # 關鍵防護：若前一行正處於未完成之句子中間（未終止且兩行間無空行）
        # 除非本行具有「第X章」等極強章節前綴，否則絕不可被誤判為獨立標題或中斷段落
        if current_para and not ends_with_sentence_terminator(current_para[-1]) and not prev_had_blank:
            is_strong_header = bool(
                re.match(r'^\s*第[0-9一二三四五六七八九十百千零〇两兩 ]+[章回节節集卷部篇步讲講课課幕场場辑輯]', stripped) or
                re.match(r'^\s*(?:Chapter|Part)\s+[0-9IVXLCDM]+', stripped, re.I)
            )
            if not is_strong_header:
                stripped = clean_stray_spaces_chinese(stripped)
                last_text = current_para[-1]
                prev_char = last_text[-1] if last_text else ""
                curr_char = stripped[0] if stripped else ""
                if prev_char.isascii() and prev_char.isalnum() and curr_char.isascii() and curr_char.isalnum():
                    current_para.append(" " + stripped)
                else:
                    current_para.append(stripped)
                prev_had_blank = False
                continue

        # 檢查是否為獨立結構標題、章節或小節線（標題保持其原有間距格式）
        if is_standalone_label_or_heading(stripped, header_pat):
            if current_para:
                paragraphs.append("".join(current_para))
                current_para = []
            paragraphs.append(stripped)
            prev_had_blank = True
            last_was_header = is_chapter_header(stripped, header_pat)
            continue

        # 正文內容清理中文字間不正常斷行殘留空格
        stripped = clean_stray_spaces_chinese(stripped)

        # 如果上一行是章節標題，且本行看起來是章節標題折行後半段（副標題或延續）
        if last_was_header and paragraphs and is_title_continuation(paragraphs[-1], stripped):
            prev_t = paragraphs[-1]
            # 若前行結尾與本行開頭皆為中文，無縫拼接（不加空格，避免「什麼 樣」缺陷）
            if prev_t and prev_t[-1] >= '\u4e00' and stripped and stripped[0] >= '\u4e00':
                joined_title = f"{prev_t}{stripped}"
            else:
                joined_title = f"{prev_t} {stripped}"
            # 規範章節前綴空格 (如 第1章 西方...)
            joined_title = re.sub(r'^(第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節集卷部篇])([^\s])', r'\1 \2', joined_title)
            paragraphs[-1] = joined_title
            last_was_header = False
            prev_had_blank = True
            continue

        last_was_header = False

        # 如果當前累積為空，直接作為段落開頭
        if not current_para:
            current_para.append(stripped)
            prev_had_blank = False
            continue

        last_text = current_para[-1]

        # 核心判斷：是否應與上一行合併？
        should_merge = False

        # 情況 A：上一行結尾「不是」句子終止符號（上一行以中文字、逗點、頓號、連接號結尾）
        if not ends_with_sentence_terminator(last_text):
            should_merge = True

        # 情況 B：本行開頭是接續字（例如本行開頭為「的」、「了」或右括號/右引號/逗點）
        elif starts_with_continuation(stripped):
            should_merge = True

        # 情況 C：上一行已句末終止（句號、問號、嘆號、感嘆號引號）
        else:
            # 1. 若兩行間本來就有空行 -> 必為新段落 (不合併)
            if prev_had_blank:
                should_merge = False
            # 2. 若本行原始有縮排 (全形空格/2個以上半形空格/tab) -> 必為新段落 (不合併)
            elif starts_with_indent(line):
                should_merge = False
            # 3. 若本行以引號開頭 (對話/專利引言) -> 必為新段落 (不合併)
            elif stripped and stripped[0] in '“「『"':
                should_merge = False
            # 4. 若前一行明顯未滿行 (排版物理段尾：長度 <= 典型行長的 82%) -> 必為新段落 (不合併)
            elif len(last_text) <= typical_line_len * 0.82:
                should_merge = False
            # 5. 若本行具備顯著段落引導詞 (例如「廣告也好」、「科學研究指出」、「總結來說」、「換句話說」) -> 必為新段落 (不合併)
            elif is_discourse_paragraph_starter(stripped):
                should_merge = False
            else:
                # 僅在排版滿行且完全無縮排/無標記時，才視為同段落折行續句
                should_merge = True

        if should_merge:
            # 僅當兩側皆為 ASCII 英數字時才補半形空格，中文字直接拼接
            prev_char = last_text[-1] if last_text else ""
            curr_char = stripped[0] if stripped else ""
            if prev_char.isascii() and prev_char.isalnum() and curr_char.isascii() and curr_char.isalnum():
                current_para.append(" " + stripped)
            else:
                current_para.append(stripped)
        else:
            # 視為新段落
            paragraphs.append("".join(current_para))
            current_para = [stripped]

        prev_had_blank = False

    if current_para:
        paragraphs.append("".join(current_para))

    # 格式化輸出：為正文段落添加標準中文正體縮排
    formatted_paras = []
    for p in paragraphs:
        p_clean = p.strip()
        if not p_clean:
            continue
        # 若為章節標題、結構標籤或分隔線，不加縮排
        if is_standalone_label_or_heading(p_clean, header_pat):
            formatted_paras.append(p_clean)
        else:
            if indent_paragraphs and not p_clean.startswith(('　', '    ')):
                formatted_paras.append('　　' + p_clean)
            else:
                formatted_paras.append(p_clean)

    separator = "\n\n" if keep_empty_lines_between_paragraphs else "\n"
    return separator.join(formatted_paras)


def clean_file_hard_breaks(
    input_filepath: str,
    output_filepath: str,
    header_regex_str: str = "",
    indent_paragraphs: bool = True
) -> Dict[str, Any]:
    """
    對指定檔案執行硬換行清洗並將最佳化結果寫入目標檔案。
    回傳清洗統計報告（行數變更、段落數、清理成果）。
    """
    if not os.path.exists(input_filepath):
        return {"success": False, "message": f"找不到輸入檔案: {input_filepath}"}

    with open(input_filepath, "r", encoding="utf-8", errors="ignore") as f:
        raw_text = f.read()

    orig_lines = len(raw_text.splitlines())

    cleaned_text = remove_hard_breaks(
        raw_text,
        header_regex_str=header_regex_str,
        indent_paragraphs=indent_paragraphs
    )
    new_lines = len(cleaned_text.splitlines())
    paragraphs_count = len([p for p in cleaned_text.split("\n\n") if p.strip()])

    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(cleaned_text)

    reduction = ((orig_lines - new_lines) / max(orig_lines, 1)) * 100

    report = {
        "success": True,
        "input_file": input_filepath,
        "output_file": output_filepath,
        "original_lines": orig_lines,
        "cleaned_lines": new_lines,
        "paragraphs_count": paragraphs_count,
        "line_reduction_percent": round(reduction, 1),
        "summary": f"硬換行修復完成：原 {orig_lines} 行縮減為 {paragraphs_count} 個自然段落（行數減少 {reduction:.1f}%）。"
    }
    return report
