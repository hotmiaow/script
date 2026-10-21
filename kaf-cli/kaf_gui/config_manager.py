# -*- coding: utf-8 -*-
"""
設定檔與使用者預設方案管理模組
"""

import os
import json
from typing import Dict, Any

_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "kaf_cli_path": "",
    "output_dir": "",
    "format": "all",
    "book_type": "auto",
    "pdf_mode": "auto",  # 'auto', 'direct_epub', 'novel_txt'
    "lang": "zh-TW",
    "align": "center",
    "indent": 2,
    "bottom": "1em",
    "line_height": "1.85",
    "separate_chapter_number": True,
    "tips": False,
    "zh_conversion": "s2tw",
    "theme": "dark",
    "auto_open_folder": True,
    "cover_mode": "auto",  # 'auto', 'custom', 'orly'
    "custom_cover_path": "",
    "orly_color": "",
    "orly_idx": -1,
    "css_preset": "臺灣典雅實體書 (Classic Book)",
    "custom_css_file": "",
    "custom_css_content": "",
    "font_path": "",
    "match_regex": "",
    "enable_volume": True,
    "volume_regex": r"^第[0-9一二三四五六七八九十零〇百千两 ]+[卷部]",
    "exclude_regex": r"^第[0-9一二三四五六七八九十零〇百千两 ]+(部門|部队|部属|部分|部件|部落|部.*：$)",
    "max_title_len": 35,
    "unknow_title": "章節正文",
    "remove_hard_breaks": True,
    "use_gemma_pipeline": True,
    "gemma_backend": "fast_local",
    "gemma_model": "google/embeddinggemma-2",
    "gemma_ollama_url": "http://localhost:11434",
    "gemma_dedup": True,
    "gemma_clean_noise": True,
    "gemma_rearrange": True,
    "gemma_auto_titles": True,
    "gemma_inject_guide": True,
    "gemma_max_characters": 10,
    "window_width": 1000,
    "window_height": 720,
    "window_maximized": False,
    "user_presets": {}
}

SYSTEM_PRESETS = {
    "【預設】臺灣典雅實體書 (推薦)": {
        "format": "all",
        "lang": "zh-TW",
        "align": "center",
        "indent": 2,
        "bottom": "1em",
        "line_height": "1.85",
        "separate_chapter_number": True,
        "tips": False,
        "zh_conversion": "s2tw",
        "css_preset": "臺灣典雅實體書 (Classic Book)",
        "enable_volume": True,
        "volume_regex": r"^第[0-9一二三四五六七八九十零〇百千两 ]+[卷部]",
        "match_regex": "",
        "unknow_title": "章節正文"
    },
    "【預設】Kindle / Paperwhite 最佳化": {
        "format": "all",
        "lang": "zh-TW",
        "align": "center",
        "indent": 2,
        "bottom": "0.8em",
        "line_height": "1.6",
        "separate_chapter_number": False,
        "tips": False,
        "zh_conversion": "s2tw",
        "css_preset": "臺灣典雅實體書 (Classic Book)",
        "enable_volume": True,
        "volume_regex": r"^第[0-9一二三四五六七八九十零〇百千两 ]+[卷部]",
        "match_regex": "",
        "unknow_title": "章節正文"
    },
    "【預設】夜間護眼深色模式": {
        "format": "epub",
        "lang": "zh-TW",
        "align": "center",
        "indent": 2,
        "bottom": "1em",
        "line_height": "1.75",
        "separate_chapter_number": True,
        "tips": False,
        "zh_conversion": "s2tw",
        "css_preset": "護眼柔和深色模式 (Dark / Night Mode)",
        "enable_volume": True,
        "volume_regex": r"^第[0-9一二三四五六七八九十零〇百千两 ]+[卷部]",
        "match_regex": "",
        "unknow_title": "章節正文"
    },
    "【預設】文青直排直書排版": {
        "format": "epub",
        "lang": "zh-TW",
        "align": "center",
        "indent": 2,
        "bottom": "1em",
        "line_height": "1.9",
        "separate_chapter_number": False,
        "tips": False,
        "zh_conversion": "s2tw",
        "css_preset": "文青直排直書 (Vertical Reading)",
        "enable_volume": True,
        "volume_regex": r"^第[0-9一二三四五六七八九十零〇百千两 ]+[卷部]",
        "match_regex": "",
        "unknow_title": "章節正文"
    },
    "【預設】原版 kaf-cli 預設": {
        "format": "all",
        "lang": "zh",
        "align": "center",
        "indent": 2,
        "bottom": "1em",
        "line_height": "1.5rem",
        "separate_chapter_number": False,
        "tips": True,
        "zh_conversion": "none",
        "css_preset": "預設樣式 (Kaf 預設)",
        "enable_volume": True,
        "volume_regex": r"^第[0-9一二三四五六七八九十零〇百千两 ]+[卷部]",
        "match_regex": "",
        "unknow_title": "章节正文"
    }
}

class ConfigManager:
    def __init__(self, config_path: str = _CONFIG_FILE):
        self.config_path = config_path
        self.config = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.config.update(data)
            except Exception:
                pass
        return self.config

    def save(self) -> bool:
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value

    def reset(self):
        self.config = dict(DEFAULT_CONFIG)
        self.save()

    def save_user_preset(self, name: str, preset_dict: Dict[str, Any]):
        if "user_presets" not in self.config:
            self.config["user_presets"] = {}
        self.config["user_presets"][name] = preset_dict
        self.save()

    def delete_user_preset(self, name: str):
        if "user_presets" in self.config and name in self.config["user_presets"]:
            del self.config["user_presets"][name]
            self.save()

    def get_all_presets(self) -> Dict[str, Dict[str, Any]]:
        combined = dict(SYSTEM_PRESETS)
        if "user_presets" in self.config:
            combined.update(self.config["user_presets"])
        return combined
