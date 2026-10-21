# -*- coding: utf-8 -*-
"""
繁簡中文轉換模組 (Zero-dependency Simplified to Traditional Chinese converter)
支援：
- s2t: 簡體轉通用繁體
- s2tw: 簡體轉臺灣正體 (含常用詞彙臺灣在地化)
- s2hk: 簡體轉香港繁體
"""

import os
import gzip
import json
import re

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_DICT_FILE = os.path.join(_DATA_DIR, "dict.json.gz")

_LOADED = False
_CHARS = {}
_PHRASES = {}
_TW_PHRASES = {}
_CHAR_TRANS = None
_PHRASE_REGEX = None
_TW_REGEX = None

# 臺灣常用詞彙對照表（確保臺灣正體閱讀體驗最佳）
_EXTRA_TW_PHRASES = {
    "默认": "預設",
    "设置": "設定",
    "软件": "軟體",
    "硬件": "硬體",
    "内存": "記憶體",
    "硬盘": "硬碟",
    "屏幕": "螢幕",
    "网络": "網路",
    "鼠标": "滑鼠",
    "算法": "演算法",
    "数据库": "資料庫",
    "文件": "檔案",
    "文件夹": "資料夾",
    "代码": "程式碼",
    "程序": "程式",
    "编程": "程式設計",
    "服务器": "伺服器",
    "客户端": "用戶端",
    "高清": "高畫質",
    "界面": "介面",
    "支持": "支援",
    "连接": "連線",
    "刷新": "重新整理",
    "链接": "連結",
    "信息": "資訊",
    "创建": "建立",
    "项目": "專案",
    "重启": "重新啟動",
    "注销": "登出",
    "登录": "登入",
    "打印": "列印",
    "在线": "線上",
    "视频": "影片",
    "音频": "音訊",
    "用户": "使用者",
    "光盘": "光碟",
}

def _init_dict():
    global _LOADED, _CHARS, _PHRASES, _TW_PHRASES, _CHAR_TRANS, _PHRASE_REGEX, _TW_REGEX
    if _LOADED:
        return
    
    if os.path.exists(_DICT_FILE):
        try:
            with gzip.open(_DICT_FILE, "rt", encoding="utf-8") as f:
                data = json.load(f)
                _CHARS = data.get("chars", {})
                _PHRASES = data.get("phrases", {})
                _TW_PHRASES = data.get("tw", {})
        except Exception:
            _CHARS = {}
            _PHRASES = {}
            _TW_PHRASES = {}
    
    # 合併額外臺灣詞彙
    _TW_PHRASES.update(_EXTRA_TW_PHRASES)

    _CHAR_TRANS = str.maketrans(_CHARS)

    # 構建詞組正則表達式（長詞優先）
    if _PHRASES:
        sorted_phrases = sorted(_PHRASES.keys(), key=len, reverse=True)
        # 為避免過長正則，篩選 2~4 字的常見詞組
        selected = [p for p in sorted_phrases if 2 <= len(p) <= 4][:20000]
        if selected:
            _PHRASE_REGEX = re.compile("|".join(re.escape(k) for k in selected))

    if _TW_PHRASES:
        sorted_tw = sorted(_TW_PHRASES.keys(), key=len, reverse=True)
        _TW_REGEX = re.compile("|".join(re.escape(k) for k in sorted_tw))

    _LOADED = True

def convert_text(text: str, mode: str = "s2tw") -> str:
    """
    將文字從簡體轉為繁體
    mode: 'none', 's2t', 's2tw', 's2hk'
    """
    if not text or mode == "none":
        return text

    _init_dict()

    if not _CHARS:
        return text

    result = text

    # 1. 如果是臺灣正體模式，優先替換在地化詞組
    if mode == "s2tw" and _TW_REGEX:
        result = _TW_REGEX.sub(lambda m: _TW_PHRASES[m.group(0)], result)

    # 2. 替換常用詞組
    if _PHRASE_REGEX:
        result = _PHRASE_REGEX.sub(lambda m: _PHRASES[m.group(0)], result)

    # 3. 逐字對照表轉換
    if _CHAR_TRANS:
        result = result.translate(_CHAR_TRANS)

    return result

def to_tw(text: str) -> str:
    """簡便函式：直接轉換為臺灣正體"""
    return convert_text(text, mode="s2tw")

def convert_file(input_path: str, output_path: str, mode: str = "s2tw", progress_cb=None) -> bool:
    """
    讀取檔案，轉換為 UTF-8 繁體中文並輸出
    """
    if mode == "none":
        return True

    # 檢測編碼
    encoding = detect_encoding(input_path)
    
    total_size = os.path.getsize(input_path)
    processed = 0

    with open(input_path, "r", encoding=encoding, errors="replace") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        
        chunk = []
        for line in fin:
            chunk.append(line)
            if len(chunk) >= 500:
                converted = convert_text("".join(chunk), mode=mode)
                fout.write(converted)
                processed += sum(len(l.encode("utf-8", "ignore")) for l in chunk)
                if progress_cb and total_size > 0:
                    progress_cb(min(1.0, processed / total_size))
                chunk = []

        if chunk:
            converted = convert_text("".join(chunk), mode=mode)
            fout.write(converted)
            if progress_cb:
                progress_cb(1.0)

    return True

def detect_encoding(file_path: str) -> str:
    """
    智慧探測文字檔案編碼 (UTF-8, GB18030/GBK, Big5)
    """
    try:
        with open(file_path, "rb") as f:
            raw = f.read(4096)
        
        # 檢查 UTF-8 BOM
        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        
        # 嘗試 UTF-8
        try:
            raw.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            pass

        # 嘗試 GB18030 (涵蓋 GBK / GB2312)
        try:
            raw.decode("gb18030")
            return "gb18030"
        except UnicodeDecodeError:
            pass

        # 嘗試 Big5
        try:
            raw.decode("big5")
            return "big5"
        except UnicodeDecodeError:
            pass

        return "utf-8"
    except Exception:
        return "utf-8"
