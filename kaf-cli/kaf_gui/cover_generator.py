# -*- coding: utf-8 -*-
"""
電子書封面生成器模組 (Cover Generator)
提供經典 O'RLY 惡搞動物封面與現代圖書封面之本地離線向量/高畫質點陣圖繪製。
具備智慧標題與副標題解析、自動字級縮放 (Auto-fit Font Scaling) 與斷行包裝 (Line Wrapping)，
徹底解決標題過長被截斷、超出封面方塊的問題。
"""

import os
import re
from typing import Tuple, List, Optional, Any
from PIL import Image, ImageDraw, ImageFont

# 預設 16 款 O'RLY 經典配色 (1-16)
ORLY_PALETTE = {
    1: (43, 87, 154),    # #2b579a 經典湛藍
    2: (117, 165, 1),    # #75a501 經典橄欖綠 (Olive Green)
    3: (216, 59, 1),     # #d83b01 磚紅橙
    4: (168, 0, 0),      # #a80000 深緋紅
    5: (92, 45, 145),    # #5c2d91 典雅紫
    6: (0, 130, 114),    # #008272 藍綠松石
    7: (16, 124, 65),    # #107c41 森林深綠
    8: (0, 120, 212),    # #0078d4 鈷藍
    9: (180, 0, 158),    # #b4009e 品紅洋紅
    10: (232, 17, 35),   # #e81123 鮮豔紅
    11: (0, 78, 140),    # #004e8c 海軍藍
    12: (58, 58, 56),    # #3a3a38 炭黑灰
    13: (73, 130, 5),    # #498205 草木綠
    14: (0, 32, 80),     # #002050 午夜深藍
    15: (136, 23, 152),  # #881798 羅蘭紫
    16: (107, 105, 214)  # #6b69d6 鳶尾靛紫
}

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "animals")
_DEFAULT_ANIMAL_PATH = os.path.join(_ASSETS_DIR, "0.png")


def parse_orly_color(color_spec: Any) -> Tuple[int, int, int]:
    """
    解析顏色參數，支援：
    1. 數字字串或整數 1-16：對應 ORLY_PALETTE
    2. 16 進位 HEX 字串，如 #75a501, 75a501, #2b579a
    3. RGB 元組
    預設為經典橄欖綠 (117, 165, 1)
    """
    if isinstance(color_spec, (tuple, list)) and len(color_spec) >= 3:
        return (int(color_spec[0]), int(color_spec[1]), int(color_spec[2]))

    s = str(color_spec or "").strip()
    if not s:
        return ORLY_PALETTE[2]

    # 檢查 1-16 序號
    if s.isdigit():
        idx = int(s)
        if 1 <= idx <= 16:
            return ORLY_PALETTE[idx]

    # 檢查 Hex
    s_hex = s.lstrip("#")
    if len(s_hex) == 6:
        try:
            r = int(s_hex[0:2], 16)
            g = int(s_hex[2:4], 16)
            b = int(s_hex[4:6], 16)
            return (r, g, b)
        except ValueError:
            pass
    elif len(s_hex) == 3:
        try:
            r = int(s_hex[0] * 2, 16)
            g = int(s_hex[1] * 2, 16)
            b = int(s_hex[2] * 2, 16)
            return (r, g, b)
        except ValueError:
            pass

    return ORLY_PALETTE[2]


def split_title_subtitle(raw_title: str) -> Tuple[str, str]:
    """
    智慧拆分主標題與副標題：
    例如：
    《方案：人体操作手册》——卷首至注释结束·第七章起第二轮逐段精校版
    -> ("方案：人体操作手册", "卷首至注释结束·第七章起第二轮逐段精校版")
    """
    title = str(raw_title or "").strip()
    if not title:
        return "未知書籍", ""

    # 1. 匹配書名號 《...》 或 〈...〉
    m = re.match(r"^[《〈](.+?)[》〉]\s*(?:[—\-_:：\s]+)?(.*)$", title)
    if m:
        main_t = m.group(1).strip()
        sub_t = m.group(2).strip()
        sub_t = re.sub(r"^[—\-_:：\s]+", "", sub_t).strip()
        return main_t, sub_t

    # 2. 匹配分隔符 ——, —, - , ：, :
    for sep in ["——", " — ", " - ", "：", ": "]:
        if sep in title:
            parts = title.split(sep, 1)
            main_t = parts[0].strip()
            sub_t = parts[1].strip()
            # 避免把短前綴當作主標題 (例如 "卷一：..." 還是把完整或後半部當主標題)
            if len(main_t) >= 2:
                return main_t, sub_t

    # 3. 匹配末尾括號 （...） 或 (...)
    m2 = re.match(r"^(.+?)[（\(](.+?)[）\)]$", title)
    if m2:
        return m2.group(1).strip(), m2.group(2).strip()

    return title, ""


def get_available_font(size: int, preferred_font_path: str = "") -> ImageFont.FreeTypeFont:
    """尋找本機可用的中英文字型"""
    candidates = []
    if preferred_font_path and os.path.exists(preferred_font_path):
        candidates.append(preferred_font_path)

    # 專案內建繁體字型
    project_font = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "PingFangHK-Medium-CHS2CHT.ttf")
    if os.path.exists(project_font):
        candidates.append(project_font)

    # 系統常用 CJK 字型
    sys_fonts = [
        "/usr/share/fonts/google-noto-serif-cjk-vf-fonts/NotoSerifCJK-VF.ttc",
        "/usr/share/fonts/google-noto-sans-mono-cjk-vf-fonts/NotoSansMonoCJK-VF.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "C:\\Windows\\Fonts\\msyh.ttc",
        "C:\\Windows\\Fonts\\simsun.ttc"
    ]
    candidates.extend(sys_fonts)

    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue

    return ImageFont.load_default()


def wrap_text_to_width(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    """依據實際畫素寬度將文字折行，兼顧 CJK 與英數單字排版"""
    text = str(text or "").strip()
    if not text:
        return []

    # 檢查是否為純拉丁文字
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in text)
    lines = []
    current_line = ""

    if not has_cjk and " " in text:
        # 西文按單字斷行
        words = text.split(" ")
        for w in words:
            test = (current_line + " " + w).strip() if current_line else w
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width and current_line:
                lines.append(current_line)
                current_line = w
            else:
                current_line = test
        if current_line:
            lines.append(current_line)
    else:
        # 中文/混合逐字排版
        for ch in text:
            test = current_line + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width and current_line:
                lines.append(current_line)
                current_line = ch
            else:
                current_line = test
        if current_line:
            lines.append(current_line)

    return lines


def generate_orly_cover(
    book_title: str,
    author: str = "",
    top_text: str = "kaf",
    color: str = "",
    animal_idx: int = -1,
    output_path: Optional[str] = None,
    font_path: str = "",
    width: int = 699,
    height: int = 994
) -> Image.Image:
    """
    生成經典 O'RLY 風格惡搞書皮封面：
    1. 頂部細色條 (Height: 10px) 與上方小標籤 (預設 'kaf')
    2. 中間精細雕版動物手繪插圖 (支援自適應置中)
    3. 下方主題色塊標題橫幅 (Title Banner)：
       - 具備自動縮放 (Auto-fit) 與自動折行，保證 100% 容納於色塊內，絕不溢出或被裁切
       - 自動分離主標題與副標題
    4. 底部 O'RLY? 經典商標與作者資訊
    """
    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    theme_rgb = parse_orly_color(color)
    theme_rgba = theme_rgb + (255,)

    # 1. 頂部橫條
    top_bar_height = max(8, int(height * 0.01))
    draw.rectangle([(0, 0), (width, top_bar_height)], fill=theme_rgba)

    # 2. 頂部標籤文字
    tag_text = (top_text or "kaf").strip()
    f_tag = get_available_font(max(18, int(height * 0.022)), font_path)
    tag_bbox = draw.textbbox((0, 0), tag_text, font=f_tag)
    tag_w = tag_bbox[2] - tag_bbox[0]
    tag_x = (width - tag_w) / 2
    tag_y = top_bar_height + 4
    draw.text((tag_x, tag_y), tag_text, fill=(0, 0, 0, 255), font=f_tag)

    # 3. 中間動物插圖
    animal_img = None
    target_animal_file = os.path.join(_ASSETS_DIR, f"{animal_idx}.png")
    if animal_idx >= 0 and os.path.exists(target_animal_file):
        try:
            animal_img = Image.open(target_animal_file).convert("RGBA")
        except Exception:
            animal_img = None

    if animal_img is None and os.path.exists(_DEFAULT_ANIMAL_PATH):
        try:
            animal_img = Image.open(_DEFAULT_ANIMAL_PATH).convert("RGBA")
        except Exception:
            animal_img = None

    if animal_img:
        # 計算動物圖案尺寸與置中貼附
        aw, ah = animal_img.size
        # 動物區域預設介於 y=220 到 y=450
        max_aw = int(width * 0.94)
        max_ah = int(height * 0.22)
        scale = min(max_aw / aw, max_ah / ah, 1.0)
        new_w = int(aw * scale)
        new_h = int(ah * scale)
        if new_w != aw or new_h != ah:
            animal_img = animal_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        ax = (width - new_w) // 2
        ay = int(height * 0.24) + (max_ah - new_h) // 2
        img.alpha_composite(animal_img, (ax, ay))

    # 4. 主題色塊標題橫幅 (Title Banner)
    box_y0 = int(height * 0.577)  # 約 574px
    box_y1 = int(height * 0.770)  # 約 765px
    box_h = box_y1 - box_y0
    draw.rectangle([(0, box_y0), (width, box_y1)], fill=theme_rgba)

    # 5. 標題與副標題排版演算法 (Auto-fit Scaling)
    main_title, subtitle = split_title_subtitle(book_title)
    padding_x = int(width * 0.04)  # 左右留白
    max_text_w = width - (padding_x * 2)
    max_text_h = box_h - 18

    # 動態縮小字級直到完全容納
    t_font_size = 44 if not subtitle else 38
    s_font_size = 22 if subtitle else 0

    best_t_lines: List[str] = []
    best_s_lines: List[str] = []
    best_f_title = None
    best_f_sub = None
    best_total_h = 0
    best_t_line_gap = 0
    best_s_line_gap = 0
    best_section_gap = 0
    best_t_bboxes = []
    best_s_bboxes = []

    while t_font_size >= 18:
        f_title = get_available_font(t_font_size, font_path)
        f_sub = get_available_font(s_font_size, font_path) if subtitle else None

        t_lines = wrap_text_to_width(main_title, f_title, max_text_w, draw)
        s_lines = wrap_text_to_width(subtitle, f_sub, max_text_w, draw) if (subtitle and f_sub) else []

        t_line_gap = int(t_font_size * 0.22)
        s_line_gap = int(s_font_size * 0.22) if s_font_size else 0
        section_gap = 12 if (t_lines and s_lines) else 0

        t_bboxes = [draw.textbbox((0, 0), l, font=f_title) for l in t_lines]
        t_heights = [(b[3] - b[1]) for b in t_bboxes]
        total_t_h = sum(t_heights) + max(0, len(t_lines) - 1) * t_line_gap

        s_bboxes = [draw.textbbox((0, 0), l, font=f_sub) for l in s_lines]
        s_heights = [(b[3] - b[1]) for b in s_bboxes]
        total_s_h = sum(s_heights) + max(0, len(s_lines) - 1) * s_line_gap

        total_h = total_t_h + section_gap + total_s_h

        if total_h <= max_text_h and len(t_lines) <= 3 and len(s_lines) <= 2:
            best_t_lines = t_lines
            best_s_lines = s_lines
            best_f_title = f_title
            best_f_sub = f_sub
            best_total_h = total_h
            best_t_line_gap = t_line_gap
            best_s_line_gap = s_line_gap
            best_section_gap = section_gap
            best_t_bboxes = t_bboxes
            best_s_bboxes = s_bboxes
            break

        t_font_size -= 2
        if subtitle and s_font_size > 14:
            s_font_size -= 1

    # 繪製標題與副標題 (上下左右完全置中)
    if best_f_title:
        start_y = box_y0 + (box_h - best_total_h) / 2
        cur_y = start_y

        for l, bbox in zip(best_t_lines, best_t_bboxes):
            lw = bbox[2] - bbox[0]
            lh = bbox[3] - bbox[1]
            lx = (width - lw) / 2
            draw.text((lx, cur_y), l, fill=(255, 255, 255, 255), font=best_f_title)
            cur_y += lh + best_t_line_gap

        if best_s_lines and best_f_sub:
            cur_y += best_section_gap - best_t_line_gap
            for l, bbox in zip(best_s_lines, best_s_bboxes):
                lw = bbox[2] - bbox[0]
                lh = bbox[3] - bbox[1]
                lx = (width - lw) / 2
                draw.text((lx, cur_y), l, fill=(245, 248, 252, 255), font=best_f_sub)
                cur_y += lh + best_s_line_gap

    # 6. 底部經典 O'RLY? 標誌與作者排版
    logo_text = "O'RLY?"
    f_logo = get_available_font(max(24, int(height * 0.028)), font_path)
    logo_bbox = draw.textbbox((0, 0), logo_text, font=f_logo)
    logo_w = logo_bbox[2] - logo_bbox[0]
    logo_x = int(width * 0.035)
    bottom_y = int(height * 0.942)
    draw.text((logo_x, bottom_y), logo_text, fill=(0, 0, 0, 255), font=f_logo)

    # 作者排版 (保證與 O'RLY? 保持寬裕安全距離，自適應縮小避免重疊)
    clean_author = str(author or "").strip()
    if clean_author:
        auth_avail_w = width - (logo_x + logo_w + 36) - int(width * 0.03)
        a_size = max(18, int(height * 0.021))
        f_auth = get_available_font(a_size, font_path)
        while a_size >= 12:
            f_auth = get_available_font(a_size, font_path)
            a_bbox = draw.textbbox((0, 0), clean_author, font=f_auth)
            if a_bbox[2] - a_bbox[0] <= auth_avail_w:
                break
            a_size -= 1

        auth_bbox = draw.textbbox((0, 0), clean_author, font=f_auth)
        auth_x = logo_x + logo_w + 28
        auth_y = bottom_y + (logo_bbox[3] - logo_bbox[1] - (auth_bbox[3] - auth_bbox[1])) / 2 + 2
        draw.text((auth_x, auth_y), clean_author, fill=(17, 24, 39, 255), font=f_auth)

    # 儲存圖片
    if output_path:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        img.save(output_path, format="PNG")

    return img
