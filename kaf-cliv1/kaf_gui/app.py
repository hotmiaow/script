# -*- coding: utf-8 -*-
"""
kaf-cli 繁體中文桌面圖形介面 (PyQt5)
"""

import os
import sys
import subprocess
from typing import List, Dict, Any, Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox,
    QCheckBox, QRadioButton, QButtonGroup, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextEdit, QProgressBar, QFileDialog,
    QMessageBox, QSplitter, QDialog, QTreeWidget, QTreeWidgetItem,
    QFrame, QColorDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QColor

from .converter_engine import KafCliEngine
from .regex_tester import (
    parse_filename_meta, test_chapter_match, REGEX_PRESETS,
    DEFAULT_VOLUME_REGEX, DEFAULT_EXCLUDE_REGEX,
    auto_detect_best_rule, AUTO_RULE_CANDIDATES
)
from .css_presets import CSS_PRESETS
from .config_manager import ConfigManager, SYSTEM_PRESETS
from .styles import DARK_THEME, LIGHT_THEME


class ConversionWorker(QThread):
    """背景執行轉換任務的工作線程"""
    log_signal = pyqtSignal(str)
    file_progress_signal = pyqtSignal(int, float, str)  # file_index, progress (0.0~1.0), status_text
    file_finished_signal = pyqtSignal(int, bool, str)   # file_index, success, message
    all_finished_signal = pyqtSignal()

    def __init__(self, engine: KafCliEngine, tasks: List[Dict[str, Any]], common_options: Dict[str, Any]):
        super().__init__()
        self.engine = engine
        self.tasks = tasks
        self.common_options = common_options
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True
        self.engine.cancel()

    def run(self):
        total = len(self.tasks)
        for idx, task in enumerate(self.tasks):
            if self._is_cancelled:
                break

            filepath = task["filepath"]
            opts = dict(self.common_options)
            # 個別小說專屬選項 (書名、作者、獨立輸出檔名)
            if task.get("bookname"):
                opts["bookname"] = task["bookname"]
            if task.get("author"):
                opts["author"] = task["author"]
            if task.get("out"):
                opts["out"] = task["out"]

            # 每本小說獨立專屬的章節規則與最大標題字數
            if "match_regex" in task and task["match_regex"] is not None:
                opts["match_regex"] = task["match_regex"]
            if "max_title_len" in task and task["max_title_len"] is not None:
                opts["max_title_len"] = task["max_title_len"]

            self.file_progress_signal.emit(idx, 0.0, f"正在處理 ({idx+1}/{total})...")
            self.log_signal.emit(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.log_signal.emit(f"▶ 開始轉換 [{idx+1}/{total}]: {os.path.basename(filepath)}")

            def progress_cb(ratio, msg):
                self.file_progress_signal.emit(idx, ratio, msg)

            def log_cb(msg):
                self.log_signal.emit(msg)

            res = self.engine.run_conversion(
                input_file=filepath,
                options=opts,
                log_callback=log_cb,
                progress_callback=progress_cb
            )

            success = res.get("success", False)
            msg = res.get("message", "")
            self.file_finished_signal.emit(idx, success, msg)

        self.all_finished_signal.emit()


class ChapterPreviewDialog(QDialog):
    """章節匹配即時測試與預覽視窗"""
    def __init__(self, result: Dict[str, Any], filepath: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"章節目錄匹配預覽 - {os.path.basename(filepath)}")
        self.resize(750, 520)

        layout = QVBoxLayout(self)

        # 頂部摘要卡片
        summary_group = QGroupBox("掃描統計摘要")
        sum_layout = QHBoxLayout(summary_group)
        
        enc = result.get("encoding", "未知")
        lines = result.get("total_lines_scanned", 0)
        chap_cnt = result.get("chapters_found", 0)
        vol_cnt = result.get("volumes_found", 0)
        excl_cnt = result.get("excluded_count", 0)

        sum_layout.addWidget(QLabel(f"<b>編碼:</b> {enc.upper()}"))
        sum_layout.addWidget(QLabel(f"<b>掃描行數:</b> {lines} 行"))
        sum_layout.addWidget(QLabel(f"<b>匹配章節:</b> <span style='color:#3b82f6;font-size:14px;font-weight:bold;'>{chap_cnt}</span> 章"))
        sum_layout.addWidget(QLabel(f"<b>匹配分卷:</b> <span style='color:#10b981;font-weight:bold;'>{vol_cnt}</span> 卷"))
        sum_layout.addWidget(QLabel(f"<b>排除無效行:</b> {excl_cnt} 處"))
        layout.addWidget(summary_group)

        # 目錄列表
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["行號", "類型", "標題內容"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)

        items = result.get("preview_items", [])
        self.table.setRowCount(len(items))
        for row, it in enumerate(items):
            item_line = QTableWidgetItem(str(it.get("line_no", "")))
            item_line.setTextAlignment(Qt.AlignCenter)
            item_type = QTableWidgetItem(it.get("type", ""))
            item_type.setTextAlignment(Qt.AlignCenter)
            if it.get("type") == "卷":
                item_type.setForeground(QColor("#10b981"))
            else:
                item_type.setForeground(QColor("#3b82f6"))

            item_title = QTableWidgetItem(it.get("title", ""))
            self.table.setItem(row, 0, item_line)
            self.table.setItem(row, 1, item_type)
            self.table.setItem(row, 2, item_title)

        layout.addWidget(self.table)

        btn_box = QHBoxLayout()
        tip_label = QLabel("提示：僅展示前 100 處匹配項目。若無章節或遺漏，請調整正則規則。")
        tip_label.setStyleSheet("color: #888; font-size: 12px;")
        btn_box.addWidget(tip_label)
        btn_box.addStretch()
        btn_close = QPushButton("關閉")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)


class KafMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg_mgr = ConfigManager()
        self.engine = KafCliEngine(self.cfg_mgr.get("kaf_cli_path", ""))
        self.worker: Optional[ConversionWorker] = None
        self.tasks: List[Dict[str, Any]] = []

        self.init_ui()
        self.load_settings_to_ui()
        self.update_cli_status()
        self.setAcceptDrops(True)

    def init_ui(self):
        self.setWindowTitle("kaf-cli 繁體中文電子書轉換器 (專業 GUI 版)")
        self.resize(1000, 780)

        # 套用主題
        self.apply_theme(self.cfg_mgr.get("theme", "dark"))

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(12)

        # 頂部狀態與操作欄
        top_bar = QHBoxLayout()
        
        # 標題與版本
        title_box = QVBoxLayout()
        title_label = QLabel("<span style='font-size:18px; font-weight:bold; color:#3b82f6;'>kaf-cli</span> <span style='font-size:16px; font-weight:bold;'>電子書轉換器</span>")
        self.lbl_cli_status = QLabel("正在檢測 kaf-cli 狀態...")
        self.lbl_cli_status.setStyleSheet("font-size: 12px; color: #888;")
        title_box.addWidget(title_label)
        title_box.addWidget(self.lbl_cli_status)
        top_bar.addLayout(title_box)

        top_bar.addStretch()

        # 預設方案下拉
        top_bar.addWidget(QLabel("快速預設方案:"))
        self.combo_presets = QComboBox()
        self.refresh_presets_combo()
        self.combo_presets.currentIndexChanged.connect(self.on_preset_selected)
        top_bar.addWidget(self.combo_presets)

        btn_save_preset = QPushButton("另存方案")
        btn_save_preset.clicked.connect(self.on_save_preset_clicked)
        top_bar.addWidget(btn_save_preset)

        # 核心執行檔設定
        btn_cli_locate = QPushButton("核心執行檔設定")
        btn_cli_locate.clicked.connect(self.on_locate_cli_clicked)
        top_bar.addWidget(btn_cli_locate)

        # 主題切換
        self.btn_theme_toggle = QPushButton("切換淺色" if self.cfg_mgr.get("theme") == "dark" else "切換深色")
        self.btn_theme_toggle.clicked.connect(self.toggle_theme)
        top_bar.addWidget(self.btn_theme_toggle)

        main_layout.addLayout(top_bar)

        # 分頁控制項
        self.tabs = QTabWidget()
        
        # 建立分頁
        self.tab_files = QWidget()
        self.tab_typography = QWidget()
        self.tab_rules = QWidget()
        self.tab_cover = QWidget()
        self.tab_css = QWidget()
        self.tab_logs = QWidget()

        self.setup_tab_files()
        self.setup_tab_typography()
        self.setup_tab_rules()
        self.setup_tab_cover()
        self.setup_tab_css()
        self.setup_tab_logs()

        self.tabs.addTab(self.tab_files, "📚 檔案與佇列")
        self.tabs.addTab(self.tab_typography, "📐 排版與版面")
        self.tabs.addTab(self.tab_rules, "🔍 章節與分卷匹配")
        self.tabs.addTab(self.tab_cover, "🎨 封面設定")
        self.tabs.addTab(self.tab_css, "🖋️ 自訂 CSS 樣式")
        self.tabs.addTab(self.tab_logs, "💻 即時日誌與終端")

        main_layout.addWidget(self.tabs)

        # 底部轉換控制區
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet("background: rgba(30, 34, 42, 0.4); border-radius: 8px; padding: 6px;")
        bottom_layout = QVBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(10, 8, 10, 8)

        # 命令列即時預覽
        cmd_preview_box = QHBoxLayout()
        cmd_preview_box.addWidget(QLabel("<b>即時指令預覽:</b>"))
        self.edit_cmd_preview = QLineEdit()
        self.edit_cmd_preview.setReadOnly(True)
        self.edit_cmd_preview.setStyleSheet("color: #79c0ff; font-family: monospace; font-size: 12px;")
        cmd_preview_box.addWidget(self.edit_cmd_preview)
        btn_copy_cmd = QPushButton("複製指令")
        btn_copy_cmd.clicked.connect(self.copy_command_preview)
        cmd_preview_box.addWidget(btn_copy_cmd)
        bottom_layout.addLayout(cmd_preview_box)

        # 進度條與狀態文字
        prog_box = QHBoxLayout()
        self.lbl_status = QLabel("就緒：請拖入或新增小說 txt 檔案以開始。")
        prog_box.addWidget(self.lbl_status)
        prog_box.addStretch()
        self.lbl_progress_percent = QLabel("0%")
        prog_box.addWidget(self.lbl_progress_percent)
        bottom_layout.addLayout(prog_box)

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        bottom_layout.addWidget(self.prog_bar)

        # 操作按鈕
        btn_action_box = QHBoxLayout()
        self.chk_auto_open = QCheckBox("轉換完成後自動開啟輸出資料夾")
        self.chk_auto_open.setChecked(self.cfg_mgr.get("auto_open_folder", True))
        btn_action_box.addWidget(self.chk_auto_open)

        btn_action_box.addStretch()

        self.btn_cancel = QPushButton("⏹ 取消轉換")
        self.btn_cancel.setObjectName("btn_danger")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_conversion)
        btn_action_box.addWidget(self.btn_cancel)

        self.btn_start = QPushButton("🚀 開始轉換電子書")
        self.btn_start.setObjectName("btn_primary")
        self.btn_start.clicked.connect(self.start_conversion)
        btn_action_box.addWidget(self.btn_start)

        bottom_layout.addLayout(btn_action_box)
        main_layout.addWidget(bottom_frame)

    # ================= 分頁 1：檔案與佇列 =================
    def setup_tab_files(self):
        layout = QVBoxLayout(self.tab_files)

        # 工具按鈕列
        btn_bar = QHBoxLayout()
        btn_add_file = QPushButton("＋ 新增 txt 小說檔案")
        btn_add_file.clicked.connect(self.add_txt_files_dialog)
        btn_bar.addWidget(btn_add_file)

        btn_add_dir = QPushButton("📁 新增資料夾 (批次掃描)")
        btn_add_dir.clicked.connect(self.add_directory_dialog)
        btn_bar.addWidget(btn_add_dir)

        btn_auto_detect = QPushButton("⚡ 一鍵自動偵測所有小說最佳規則")
        btn_auto_detect.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 6px 12px; border-radius: 6px;")
        btn_auto_detect.clicked.connect(self.auto_detect_all_tasks)
        btn_bar.addWidget(btn_auto_detect)

        btn_remove_sel = QPushButton("✕ 移除所選")
        btn_remove_sel.clicked.connect(self.remove_selected_task)
        btn_bar.addWidget(btn_remove_sel)

        btn_clear = QPushButton("🗑️ 清空清單")
        btn_clear.clicked.connect(self.clear_tasks)
        btn_bar.addWidget(btn_clear)

        btn_bar.addStretch()
        tip_drag = QLabel("💡 支援將 txt 檔案直接拖入視窗")
        tip_drag.setStyleSheet("color: #888; font-size: 12px;")
        btn_bar.addWidget(tip_drag)

        layout.addLayout(btn_bar)

        # 任務表格 (支援每本小說獨立指定規則與預估章節)
        self.table_tasks = QTableWidget()
        self.table_tasks.setColumnCount(9)
        self.table_tasks.setHorizontalHeaderLabels([
            "#", "檔案名稱", "書籍名稱", "作者", "章節匹配規則 (每本獨立)", "預估章節", "輸出格式", "狀態", "操作"
        ])
        self.table_tasks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_tasks.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeToContents)
        self.table_tasks.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_tasks.setAlternatingRowColors(True)
        self.table_tasks.itemSelectionChanged.connect(self.update_command_preview)
        layout.addWidget(self.table_tasks)

        # 全域輸出與格式選項
        opt_group = QGroupBox("輸出與語言核心選項")
        opt_layout = QVBoxLayout(opt_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("輸出格式:"))
        self.combo_format = QComboBox()
        self.combo_format.addItem("全部生成 (ALL: EPUB + MOBI + AZW3)", "all")
        self.combo_format.addItem("僅 EPUB (.epub)", "epub")
        self.combo_format.addItem("僅 MOBI (.mobi - 需 kindlegen)", "mobi")
        self.combo_format.addItem("僅 AZW3 (.azw3)", "azw3")
        self.combo_format.currentIndexChanged.connect(self.update_command_preview)
        row1.addWidget(self.combo_format)

        row1.addSpacing(20)

        row1.addWidget(QLabel("內文簡繁轉換:"))
        self.combo_zh = QComboBox()
        self.combo_zh.addItem("簡體轉臺灣正體 (s2tw, 推薦)", "s2tw")
        self.combo_zh.addItem("簡體轉香港繁體 (s2hk)", "s2hk")
        self.combo_zh.addItem("簡體轉標準繁體 (s2t)", "s2t")
        self.combo_zh.addItem("不轉換 (保持原始檔案內容)", "none")
        self.combo_zh.currentIndexChanged.connect(self.update_command_preview)
        row1.addWidget(self.combo_zh)

        opt_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("自訂輸出目錄:"))
        self.edit_output_dir = QLineEdit()
        self.edit_output_dir.setPlaceholderText("留空則預設輸出至各小說 txt 所在資料夾")
        self.edit_output_dir.textChanged.connect(self.update_command_preview)
        row2.addWidget(self.edit_output_dir)

        btn_browse_out = QPushButton("瀏覽...")
        btn_browse_out.clicked.connect(self.browse_output_dir)
        row2.addWidget(btn_browse_out)

        btn_clear_out = QPushButton("重設")
        btn_clear_out.clicked.connect(lambda: self.edit_output_dir.setText(""))
        row2.addWidget(btn_clear_out)

        opt_layout.addLayout(row2)
        layout.addWidget(opt_group)

    # ================= 分頁 2：排版與版面 =================
    def setup_tab_typography(self):
        layout = QVBoxLayout(self.tab_typography)

        group = QGroupBox("文字與版面樣式參數")
        g_layout = QVBoxLayout(group)

        # 對齊方式
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("標題對齊方式 (-align):"))
        self.combo_align = QComboBox()
        self.combo_align.addItem("居中 (center)", "center")
        self.combo_align.addItem("靠左 (left)", "left")
        self.combo_align.addItem("靠右 (right)", "right")
        self.combo_align.currentIndexChanged.connect(self.update_command_preview)
        row1.addWidget(self.combo_align)

        row1.addSpacing(20)

        row1.addWidget(QLabel("書籍語言標籤 (-lang):"))
        self.combo_lang = QComboBox()
        self.combo_lang.addItem("zh-TW (臺灣正體)", "zh-TW")
        self.combo_lang.addItem("zh-HK (香港繁體)", "zh-HK")
        self.combo_lang.addItem("zh (中文)", "zh")
        self.combo_lang.addItem("en (English)", "en")
        self.combo_lang.addItem("ja (日本語)", "ja")
        self.combo_lang.setEditable(True)
        self.combo_lang.currentTextChanged.connect(self.update_command_preview)
        row1.addWidget(self.combo_lang)
        g_layout.addLayout(row1)

        # 首行縮排與章節分離
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("段落首行縮排字數 (-indent):"))
        self.spin_indent = QSpinBox()
        self.spin_indent.setRange(0, 8)
        self.spin_indent.setValue(2)
        self.spin_indent.valueChanged.connect(self.update_command_preview)
        row2.addWidget(self.spin_indent)

        row2.addSpacing(20)

        self.chk_sep_chap = QCheckBox("章節序號與標題分離顯示 (-separate-chapter-number)")
        self.chk_sep_chap.setChecked(True)
        self.chk_sep_chap.toggled.connect(self.update_command_preview)
        row2.addWidget(self.chk_sep_chap)
        g_layout.addLayout(row2)

        # 段落間距與行距
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("段落間距 (-bottom):"))
        self.edit_bottom = QLineEdit("1em")
        self.edit_bottom.setFixedWidth(100)
        self.edit_bottom.textChanged.connect(self.update_command_preview)
        row3.addWidget(self.edit_bottom)
        for val in ["0.5em", "1em", "1.5em"]:
            btn = QPushButton(val)
            btn.setFixedWidth(50)
            btn.clicked.connect(lambda _, v=val: self.edit_bottom.setText(v))
            row3.addWidget(btn)

        row3.addSpacing(20)

        row3.addWidget(QLabel("行間距/行高 (-line-height):"))
        self.edit_line_height = QLineEdit("1.85")
        self.edit_line_height.setFixedWidth(100)
        self.edit_line_height.textChanged.connect(self.update_command_preview)
        row3.addWidget(self.edit_line_height)
        for val in ["1.5rem", "1.75", "1.85", "2.0"]:
            btn = QPushButton(val)
            btn.setFixedWidth(50)
            btn.clicked.connect(lambda _, v=val: self.edit_line_height.setText(v))
            row3.addWidget(btn)

        g_layout.addLayout(row3)

        # 內嵌字型
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("內嵌字型檔 (-font):"))
        self.edit_font = QLineEdit()
        self.edit_font.setPlaceholderText("留空則使用閱讀器預設字型，支援 .ttf / .otf 檔")
        self.edit_font.textChanged.connect(self.update_command_preview)
        row4.addWidget(self.edit_font)

        btn_browse_font = QPushButton("瀏覽字型...")
        btn_browse_font.clicked.connect(self.browse_font_file)
        row4.addWidget(btn_browse_font)

        btn_clear_font = QPushButton("清除")
        btn_clear_font.clicked.connect(lambda: self.edit_font.setText(""))
        row4.addWidget(btn_clear_font)
        g_layout.addLayout(row4)

        # 軟體教學結尾頁
        row5 = QHBoxLayout()
        self.chk_tips = QCheckBox("在電子書結尾添加本軟體說明與教程 (-tips)")
        self.chk_tips.setChecked(False)
        self.chk_tips.toggled.connect(self.update_command_preview)
        row5.addWidget(self.chk_tips)
        row5.addStretch()
        g_layout.addLayout(row5)

        layout.addWidget(group)
        layout.addStretch()

    # ================= 分頁 3：章節與分卷匹配 =================
    def setup_tab_rules(self):
        layout = QVBoxLayout(self.tab_rules)

        group = QGroupBox("章節標題識別正則表達式 (-match)")
        g_layout = QVBoxLayout(group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("常用正則預設:"))
        self.combo_match_preset = QComboBox()
        for label, pat in REGEX_PRESETS:
            self.combo_match_preset.addItem(label, pat)
        self.combo_match_preset.currentIndexChanged.connect(self.on_match_preset_changed)
        row1.addWidget(self.combo_match_preset)
        g_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("章節正則表達式:"))
        self.edit_match = QLineEdit()
        self.edit_match.setPlaceholderText("留空由 kaf-cli 自動識別；例: 第.{1,8}[章節回]")
        self.edit_match.textChanged.connect(self.update_command_preview)
        row2.addWidget(self.edit_match)
        g_layout.addLayout(row2)
        layout.addWidget(group)

        # 分卷規則
        vol_group = QGroupBox("分卷識別規則 (-volume-match)")
        vol_layout = QVBoxLayout(vol_group)

        self.chk_volume = QCheckBox("啟用分卷識別 (若取消勾選則禁用卷識別)")
        self.chk_volume.setChecked(True)
        self.chk_volume.toggled.connect(self.on_volume_toggled)
        vol_layout.addWidget(self.chk_volume)

        row_vol = QHBoxLayout()
        row_vol.addWidget(QLabel("分卷正則表達式:"))
        self.edit_volume = QLineEdit(DEFAULT_VOLUME_REGEX)
        self.edit_volume.textChanged.connect(self.update_command_preview)
        row_vol.addWidget(self.edit_volume)
        vol_layout.addLayout(row_vol)
        layout.addWidget(vol_group)

        # 排除無效章節
        excl_group = QGroupBox("排除無效章節與輔助規則 (-exclude, -max, -unknow-title)")
        excl_layout = QVBoxLayout(excl_group)

        row_excl = QHBoxLayout()
        row_excl.addWidget(QLabel("排除無效章節正則:"))
        self.edit_exclude = QLineEdit(DEFAULT_EXCLUDE_REGEX)
        self.edit_exclude.textChanged.connect(self.update_command_preview)
        row_excl.addWidget(self.edit_exclude)
        excl_layout.addLayout(row_excl)

        row_misc = QHBoxLayout()
        row_misc.addWidget(QLabel("標題最大字數 (-max):"))
        self.spin_max_len = QSpinBox()
        self.spin_max_len.setRange(10, 100)
        self.spin_max_len.setValue(35)
        self.spin_max_len.valueChanged.connect(self.update_command_preview)
        row_misc.addWidget(self.spin_max_len)

        row_misc.addSpacing(20)

        row_misc.addWidget(QLabel("未知章節預設名稱 (-unknow-title):"))
        self.edit_unknow_title = QLineEdit("章節正文")
        self.edit_unknow_title.textChanged.connect(self.update_command_preview)
        row_misc.addWidget(self.edit_unknow_title)
        excl_layout.addLayout(row_misc)
        layout.addWidget(excl_group)

        # 測試按鈕
        btn_box = QHBoxLayout()
        self.btn_test_regex = QPushButton("🔍 即時測試章節匹配 (目錄預覽)")
        self.btn_test_regex.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 8px 18px;")
        self.btn_test_regex.clicked.connect(self.run_regex_test)
        btn_box.addWidget(self.btn_test_regex)
        btn_box.addWidget(QLabel("提示：選取佇列中的小說並點擊測試，可即時查看章節目錄識別是否正確。"))
        btn_box.addStretch()
        layout.addLayout(btn_box)

        layout.addStretch()

    # ================= 分頁 4：封面設定 =================
    def setup_tab_cover(self):
        layout = QHBoxLayout(self.tab_cover)

        # 左側控制區
        left_box = QVBoxLayout()
        
        mode_group = QGroupBox("封面設定模式 (-cover)")
        mode_layout = QVBoxLayout(mode_group)

        self.radio_cover_auto = QRadioButton("自動偵測：使用小說目錄下的 cover.png 或 cover.jpg")
        self.radio_cover_auto.setChecked(True)
        self.radio_cover_auto.toggled.connect(self.on_cover_mode_changed)
        mode_layout.addWidget(self.radio_cover_auto)

        self.radio_cover_custom = QRadioButton("自訂本地圖片")
        self.radio_cover_custom.toggled.connect(self.on_cover_mode_changed)
        mode_layout.addWidget(self.radio_cover_custom)

        custom_row = QHBoxLayout()
        self.edit_cover_path = QLineEdit()
        self.edit_cover_path.setPlaceholderText("請選擇封面圖片檔案 (.jpg, .png, .webp)...")
        self.edit_cover_path.textChanged.connect(self.on_custom_cover_changed)
        custom_row.addWidget(self.edit_cover_path)
        btn_browse_cover = QPushButton("瀏覽圖片...")
        btn_browse_cover.clicked.connect(self.browse_cover_image)
        custom_row.addWidget(btn_browse_cover)
        mode_layout.addLayout(custom_row)

        mode_layout.addSpacing(10)

        self.radio_cover_orly = QRadioButton("Orly 經典動物封面 (需連接網路)")
        self.radio_cover_orly.toggled.connect(self.on_cover_mode_changed)
        mode_layout.addWidget(self.radio_cover_orly)

        orly_row1 = QHBoxLayout()
        orly_row1.addWidget(QLabel("Orly 主題顏色:"))
        self.edit_orly_color = QLineEdit()
        self.edit_orly_color.setPlaceholderText("例如: #2b579a 或 1-16 (留空隨機)")
        self.edit_orly_color.textChanged.connect(self.update_command_preview)
        orly_row1.addWidget(self.edit_orly_color)
        btn_pick_color = QPushButton("選擇顏色...")
        btn_pick_color.clicked.connect(self.pick_orly_color)
        orly_row1.addWidget(btn_pick_color)
        mode_layout.addLayout(orly_row1)

        orly_row2 = QHBoxLayout()
        orly_row2.addWidget(QLabel("Orly 動物圖案 (0-41):"))
        self.spin_orly_idx = QSpinBox()
        self.spin_orly_idx.setRange(-1, 41)
        self.spin_orly_idx.setValue(-1)
        self.spin_orly_idx.setSpecialValueText("隨機圖案 (-1)")
        self.spin_orly_idx.valueChanged.connect(self.update_command_preview)
        orly_row2.addWidget(self.spin_orly_idx)
        orly_row2.addStretch()
        mode_layout.addLayout(orly_row2)

        left_box.addWidget(mode_group)
        left_box.addStretch()
        layout.addLayout(left_box, 3)

        # 右側縮圖預覽區
        right_group = QGroupBox("封面預覽")
        right_layout = QVBoxLayout(right_group)
        self.lbl_cover_preview = QLabel("尚未載入封面預覽")
        self.lbl_cover_preview.setAlignment(Qt.AlignCenter)
        self.lbl_cover_preview.setMinimumSize(220, 310)
        self.lbl_cover_preview.setStyleSheet("border: 2px dashed #444; border-radius: 8px; background: #16181d; color: #888;")
        right_layout.addWidget(self.lbl_cover_preview)
        layout.addWidget(right_group, 2)

    # ================= 分頁 5：自訂 CSS =================
    def setup_tab_css(self):
        layout = QVBoxLayout(self.tab_css)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("樣式範本快速套用:"))
        self.combo_css_preset = QComboBox()
        for name in CSS_PRESETS.keys():
            self.combo_css_preset.addItem(name)
        self.combo_css_preset.setCurrentText("臺灣典雅實體書 (Classic Book)")
        self.combo_css_preset.currentIndexChanged.connect(self.on_css_preset_changed)
        top_row.addWidget(self.combo_css_preset)

        btn_load_css = QPushButton("載入外部 CSS 檔案...")
        btn_load_css.clicked.connect(self.load_external_css)
        top_row.addWidget(btn_load_css)

        btn_export_css = QPushButton("匯出為 CSS 檔案...")
        btn_export_css.clicked.connect(self.export_current_css)
        top_row.addWidget(btn_export_css)

        top_row.addStretch()
        layout.addLayout(top_row)

        self.edit_css_content = QTextEdit()
        self.edit_css_content.setStyleSheet("font-family: monospace; font-size: 13px; line-height: 1.4;")
        self.edit_css_content.textChanged.connect(self.update_command_preview)
        layout.addWidget(self.edit_css_content)

        # 預設載入臺灣典雅實體書 CSS
        self.edit_css_content.setPlainText(CSS_PRESETS["臺灣典雅實體書 (Classic Book)"]["css"])

    # ================= 分頁 6：即時日誌 =================
    def setup_tab_logs(self):
        layout = QVBoxLayout(self.tab_logs)

        btn_bar = QHBoxLayout()
        btn_clear_log = QPushButton("清空日誌記錄")
        btn_clear_log.clicked.connect(lambda: self.txt_log.clear())
        btn_bar.addWidget(btn_clear_log)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background-color: #111317; color: #00ff66; font-family: monospace; font-size: 12px;")
        layout.addWidget(self.txt_log)

    # ================= 事件與輔助邏輯 =================
    def append_log(self, text: str):
        self.txt_log.append(text)
        self.txt_log.verticalScrollBar().setValue(self.txt_log.verticalScrollBar().maximum())

    def update_cli_status(self):
        ver = self.engine.get_version()
        if "已就緒" in ver:
            self.lbl_cli_status.setText(f"<span style='color:#10b981; font-weight:bold;'>● kaf-cli 狀態:</span> {ver} ({self.engine.cli_path})")
        else:
            self.lbl_cli_status.setText(f"<span style='color:#ef4444; font-weight:bold;'>● kaf-cli 狀態:</span> {ver}")

    def on_locate_cli_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "選取 kaf-cli 執行檔 (kaf-cli 或 kaf-cli.exe)",
            os.path.dirname(self.engine.cli_path) if self.engine.cli_path else os.getcwd(),
            "可執行檔 (* kaf-cli kaf-cli.exe);;所有檔案 (*)"
        )
        if path:
            self.engine.cli_path = path
            self.cfg_mgr.set("kaf_cli_path", path)
            self.cfg_mgr.save()
            self.update_cli_status()
            self.update_command_preview()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isfile(p) and p.lower().endswith(".txt"):
                paths.append(p)
            elif os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        if f.lower().endswith(".txt"):
                            paths.append(os.path.join(root, f))
        if paths:
            self.add_files(paths)

    def add_txt_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "選取小說 txt 檔案", os.getcwd(), "文字小說 (*.txt);;所有檔案 (*)"
        )
        if files:
            self.add_files(files)

    def add_directory_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "選取小說所在資料夾", os.getcwd())
        if d:
            found = []
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith(".txt"):
                        found.append(os.path.join(root, f))
            if found:
                self.add_files(found)
            else:
                QMessageBox.information(self, "提示", "該資料夾內未發現 .txt 文字小說檔案。")

    def add_files(self, paths: List[str]):
        existing = {t["filepath"] for t in self.tasks}
        added_count = 0
        for p in paths:
            if p in existing:
                continue
            meta = parse_filename_meta(p, auto_to_tw=True)
            # 自動智慧偵測該檔案之最佳章節匹配規則
            det = auto_detect_best_rule(p)
            self.tasks.append({
                "filepath": p,
                "bookname": meta["title"],
                "author": meta["author"],
                "rule_name": det["rule_name"],
                "match_regex": det["regex"],
                "max_title_len": det["max_len"],
                "chapter_count": det["chapter_count"],
                "candidates": det.get("candidates", []),
                "status": "等待中"
            })
            added_count += 1
        self.refresh_task_table()
        self.lbl_status.setText(f"已加入 {added_count} 本小說至佇列並自動偵測最佳規則，共 {len(self.tasks)} 本。")
        self.update_command_preview()

    def refresh_task_table(self):
        self.table_tasks.blockSignals(True)
        self.table_tasks.setRowCount(len(self.tasks))
        fmt = self.combo_format.currentData() or "all"

        for row, t in enumerate(self.tasks):
            # Col 0: #
            it_idx = QTableWidgetItem(str(row + 1))
            it_idx.setTextAlignment(Qt.AlignCenter)
            self.table_tasks.setItem(row, 0, it_idx)

            # Col 1: 檔案名稱
            it_name = QTableWidgetItem(os.path.basename(t["filepath"]))
            it_name.setToolTip(t["filepath"])
            self.table_tasks.setItem(row, 1, it_name)

            # Col 2: 書籍名稱
            it_title = QTableWidgetItem(t.get("bookname", ""))
            self.table_tasks.setItem(row, 2, it_title)

            # Col 3: 作者
            it_author = QTableWidgetItem(t.get("author", ""))
            self.table_tasks.setItem(row, 3, it_author)

            # Col 4: 每本小說獨立專屬的章節規則下拉選單 (QComboBox)
            combo_rule = QComboBox()
            combo_rule.setStyleSheet("padding: 2px 6px; font-size: 12px;")
            for r in AUTO_RULE_CANDIDATES:
                combo_rule.addItem(r["name"], r["regex"])

            cur_rule_name = t.get("rule_name", "自動智慧識別 (預設)")
            c_idx = combo_rule.findText(cur_rule_name)
            if c_idx >= 0:
                combo_rule.setCurrentIndex(c_idx)

            # 當使用者手動切換特定小說之規則時即時更新
            combo_rule.currentIndexChanged.connect(
                lambda idx, task_ref=t, r_idx=row: self.on_task_rule_changed(task_ref, idx, r_idx)
            )
            self.table_tasks.setCellWidget(row, 4, combo_rule)

            # Col 5: 預估章節數
            cnt = t.get("chapter_count", 0)
            cnt_str = f"{cnt} 章" if cnt > 0 else "—"
            it_cnt = QTableWidgetItem(cnt_str)
            it_cnt.setTextAlignment(Qt.AlignCenter)
            if cnt > 0:
                it_cnt.setForeground(QColor("#3b82f6"))
            self.table_tasks.setItem(row, 5, it_cnt)

            # Col 6: 輸出格式
            it_fmt = QTableWidgetItem(fmt.upper())
            it_fmt.setTextAlignment(Qt.AlignCenter)
            self.table_tasks.setItem(row, 6, it_fmt)

            # Col 7: 狀態
            it_status = QTableWidgetItem(t.get("status", "等待中"))
            it_status.setTextAlignment(Qt.AlignCenter)
            if t.get("status") == "完成":
                it_status.setForeground(QColor("#10b981"))
            elif "失敗" in t.get("status", "") or "錯誤" in t.get("status", ""):
                it_status.setForeground(QColor("#ef4444"))
            elif "處理中" in t.get("status", ""):
                it_status.setForeground(QColor("#3b82f6"))
            self.table_tasks.setItem(row, 7, it_status)

            # Col 8: 單本快速目錄預覽按鈕
            btn_prev = QPushButton("🔍 預覽")
            btn_prev.setStyleSheet("padding: 3px 8px; font-size: 11px;")
            btn_prev.clicked.connect(lambda _, task_ref=t: self.preview_single_task(task_ref))
            self.table_tasks.setCellWidget(row, 8, btn_prev)

        self.table_tasks.blockSignals(False)

    def on_task_rule_changed(self, task_ref: Dict[str, Any], idx: int, row_idx: int):
        if 0 <= idx < len(AUTO_RULE_CANDIDATES):
            r = AUTO_RULE_CANDIDATES[idx]
            task_ref["rule_name"] = r["name"]
            task_ref["match_regex"] = r["regex"]
            task_ref["max_title_len"] = r["max_len"]

            # 若該小說已有測試候選快取，直接套用計數；否則即時快測前 5000 行
            cnt = 0
            found_cached = False
            for c in task_ref.get("candidates", []):
                if c.get("id") == r.get("id") or c.get("name") == r.get("name"):
                    cnt = c.get("count", 0)
                    found_cached = True
                    break

            if not found_cached and r["regex"]:
                res = test_chapter_match(
                    filepath=task_ref["filepath"],
                    match_regex=r["regex"],
                    volume_regex="false",
                    max_len=r["max_len"],
                    scan_lines=5000
                )
                cnt = res.get("chapters_found", 0)

            task_ref["chapter_count"] = cnt
            it_cnt = QTableWidgetItem(f"{cnt} 章" if cnt > 0 else "—")
            it_cnt.setTextAlignment(Qt.AlignCenter)
            if cnt > 0:
                it_cnt.setForeground(QColor("#3b82f6"))
            self.table_tasks.setItem(row_idx, 5, it_cnt)
            self.update_command_preview()

    def auto_detect_all_tasks(self):
        """一鍵為佇列中所有小說自動重新推斷最佳規則"""
        if not self.tasks:
            QMessageBox.information(self, "提示", "目前佇列中尚無小說檔案！")
            return

        self.lbl_status.setText("正在智慧偵測所有小說的最佳章節規則...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for t in self.tasks:
                det = auto_detect_best_rule(t["filepath"])
                t["rule_name"] = det["rule_name"]
                t["match_regex"] = det["regex"]
                t["max_title_len"] = det["max_len"]
                t["chapter_count"] = det["chapter_count"]
                t["candidates"] = det.get("candidates", [])
            self.refresh_task_table()
            self.lbl_status.setText(f"✨ 已完成全數 {len(self.tasks)} 本小說之最佳規則自動判定！")
            self.update_command_preview()
            QMessageBox.information(
                self, "分析完成",
                f"已成功為 {len(self.tasks)} 本小說自動推薦專屬的最佳章節規則！\n"
                "您可在表格「章節匹配規則」欄位直接查看推薦結果，亦可隨時為特定小說手動微調。"
            )
        finally:
            QApplication.restoreOverrideCursor()

    def preview_single_task(self, task_ref: Dict[str, Any]):
        """針對單一小說與其專屬規則進行目錄預覽"""
        filepath = task_ref["filepath"]
        if not os.path.exists(filepath):
            QMessageBox.warning(self, "錯誤", "該小說檔案不存在！")
            return
        res = test_chapter_match(
            filepath=filepath,
            match_regex=task_ref.get("match_regex", ""),
            volume_regex="false",
            exclude_regex=self.edit_exclude.text().strip(),
            max_len=task_ref.get("max_title_len", 35),
            scan_lines=8000
        )
        if "error" in res:
            QMessageBox.critical(self, "測試出錯", res["error"])
        else:
            dlg = ChapterPreviewDialog(res, filepath, self)
            dlg.exec_()

    def remove_selected_task(self):
        rows = sorted({idx.row() for idx in self.table_tasks.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.tasks):
                del self.tasks[r]
        self.refresh_task_table()
        self.update_command_preview()

    def clear_tasks(self):
        self.tasks.clear()
        self.refresh_task_table()
        self.lbl_status.setText("就緒：請新增小說檔案。")
        self.update_command_preview()

    def browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "選取輸出目錄", os.getcwd())
        if d:
            self.edit_output_dir.setText(d)

    def browse_font_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "選取字型檔", os.getcwd(), "字型檔案 (*.ttf *.otf);;所有檔案 (*)")
        if f:
            self.edit_font.setText(f)

    def browse_cover_image(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "選取封面圖片", os.getcwd(), "圖片檔案 (*.jpg *.jpeg *.png *.webp);;所有檔案 (*)"
        )
        if f:
            self.edit_cover_path.setText(f)
            self.radio_cover_custom.setChecked(True)

    def on_custom_cover_changed(self, path: str):
        self.update_cover_preview(path)
        self.update_command_preview()

    def update_cover_preview(self, img_path: str):
        if img_path and os.path.exists(img_path):
            pix = QPixmap(img_path)
            if not pix.isNull():
                scaled = pix.scaled(200, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.lbl_cover_preview.setPixmap(scaled)
                return
        self.lbl_cover_preview.clear()
        self.lbl_cover_preview.setText("無封面預覽")

    def pick_orly_color(self):
        c = QColorDialog.getColor(QColor("#2b579a"), self, "選擇 Orly 封面主題顏色")
        if c.isValid():
            self.edit_orly_color.setText(c.name())

    def on_cover_mode_changed(self):
        if self.radio_cover_custom.isChecked():
            self.update_cover_preview(self.edit_cover_path.text())
        elif self.radio_cover_orly.isChecked():
            self.lbl_cover_preview.clear()
            self.lbl_cover_preview.setText("Orly 經典動物封面\n(轉換時自動自線上產生)")
        else:
            self.lbl_cover_preview.clear()
            self.lbl_cover_preview.setText("自動模式:\n偵測小說目錄下之 cover.png")
        self.update_command_preview()

    def on_match_preset_changed(self, idx: int):
        val = self.combo_match_preset.itemData(idx)
        if val is not None:
            self.edit_match.setText(val)
            # 若選取包含發帖日期或行內標題之規則，自動適度提升標題最大字數
            if any(k in val for k in ["日期", "作者", "第["]):
                if self.spin_max_len.value() < 60:
                    self.spin_max_len.setValue(60)

    def on_volume_toggled(self, checked: bool):
        self.edit_volume.setEnabled(checked)
        self.update_command_preview()

    def on_css_preset_changed(self):
        name = self.combo_css_preset.currentText()
        if name in CSS_PRESETS:
            self.edit_css_content.setPlainText(CSS_PRESETS[name]["css"])

    def load_external_css(self):
        f, _ = QFileDialog.getOpenFileName(self, "選取 CSS 樣式檔", os.getcwd(), "CSS 樣式 (*.css);;所有檔案 (*)")
        if f and os.path.exists(f):
            with open(f, "r", encoding="utf-8", errors="replace") as fin:
                self.edit_css_content.setPlainText(fin.read())

    def export_current_css(self):
        f, _ = QFileDialog.getSaveFileName(self, "匯出 CSS 樣式", os.getcwd(), "CSS 樣式 (*.css)")
        if f:
            with open(f, "w", encoding="utf-8") as fout:
                fout.write(self.edit_css_content.toPlainText())
            QMessageBox.information(self, "成功", f"樣式已成功匯出至：\n{f}")

    def run_regex_test(self):
        """執行章節正則即時測試與預覽"""
        sel_indexes = self.table_tasks.selectedIndexes()
        target_path = None
        if sel_indexes:
            row = sel_indexes[0].row()
            if 0 <= row < len(self.tasks):
                target_path = self.tasks[row]["filepath"]
        elif self.tasks:
            target_path = self.tasks[0]["filepath"]

        if not target_path or not os.path.exists(target_path):
            QMessageBox.warning(self, "提示", "請先加入小說檔案並在佇列中選取一項以進行章節測試！")
            return

        res = test_chapter_match(
            filepath=target_path,
            match_regex=self.edit_match.text().strip(),
            volume_regex=self.edit_volume.text().strip() if self.chk_volume.isChecked() else "false",
            exclude_regex=self.edit_exclude.text().strip(),
            max_len=self.spin_max_len.value(),
            scan_lines=5000
        )

        if "error" in res:
            QMessageBox.critical(self, "測試出錯", res["error"])
        else:
            dlg = ChapterPreviewDialog(res, target_path, self)
            dlg.exec_()

    def collect_options(self) -> Dict[str, Any]:
        """從介面收集當前所有參數選項"""
        cover_mode = "auto"
        if self.radio_cover_custom.isChecked():
            cover_mode = "custom"
        elif self.radio_cover_orly.isChecked():
            cover_mode = "orly"

        opts = {
            "format": self.combo_format.currentData() or "all",
            "zh_conversion": self.combo_zh.currentData() or "s2tw",
            "output_dir": self.edit_output_dir.text().strip(),
            "align": self.combo_align.currentData() or "center",
            "lang": self.combo_lang.currentText().strip() or "zh-TW",
            "indent": self.spin_indent.value(),
            "separate_chapter_number": self.chk_sep_chap.isChecked(),
            "bottom": self.edit_bottom.text().strip() or "1em",
            "line_height": self.edit_line_height.text().strip() or "1.5rem",
            "font_path": self.edit_font.text().strip(),
            "tips": self.chk_tips.isChecked(),
            "match_regex": self.edit_match.text().strip(),
            "enable_volume": self.chk_volume.isChecked(),
            "volume_regex": self.edit_volume.text().strip(),
            "exclude_regex": self.edit_exclude.text().strip(),
            "max_title_len": self.spin_max_len.value(),
            "unknow_title": self.edit_unknow_title.text().strip(),
            "cover_mode": cover_mode,
            "custom_cover_path": self.edit_cover_path.text().strip(),
            "orly_color": self.edit_orly_color.text().strip(),
            "orly_idx": self.spin_orly_idx.value(),
            "custom_css_content": self.edit_css_content.toPlainText().strip()
        }
        return opts

    def update_command_preview(self):
        """根據當前選取的小說或第一本小說即時產生對應指令字串"""
        if not hasattr(self, "edit_cmd_preview") or self.edit_cmd_preview is None:
            return
        opts = self.collect_options()
        sample_path = "小說.txt"
        sel_indexes = self.table_tasks.selectedIndexes()
        selected_task = None
        if sel_indexes:
            row = sel_indexes[0].row()
            if 0 <= row < len(self.tasks):
                selected_task = self.tasks[row]
        elif self.tasks:
            selected_task = self.tasks[0]

        if selected_task:
            sample_path = selected_task["filepath"]
            if selected_task.get("bookname"):
                opts["bookname"] = selected_task["bookname"]
            if selected_task.get("author"):
                opts["author"] = selected_task["author"]
            if "match_regex" in selected_task and selected_task["match_regex"] is not None:
                opts["match_regex"] = selected_task["match_regex"]
            if "max_title_len" in selected_task and selected_task["max_title_len"] is not None:
                opts["max_title_len"] = selected_task["max_title_len"]

        cmd_args = self.engine.build_command_args(sample_path, opts)
        cmd_str = " ".join([f'"{c}"' if " " in c else c for c in cmd_args])
        self.edit_cmd_preview.setText(cmd_str)

    def copy_command_preview(self):
        QApplication.clipboard().setText(self.edit_cmd_preview.text())
        self.lbl_status.setText("已複製當前預覽指令至剪貼簿！")

    def start_conversion(self):
        if not self.tasks:
            QMessageBox.information(self, "提示", "請先加入至少一本小說 txt 檔案！")
            return

        if not self.engine.cli_path or not os.path.exists(self.engine.cli_path):
            QMessageBox.critical(self, "錯誤", "未找到 kaf-cli 執行檔，請點擊上方「核心執行檔設定」指定路徑！")
            return

        # 儲存當前設定
        self.save_ui_to_settings()

        # 切換到日誌分頁以供即時觀看
        self.tabs.setCurrentWidget(self.tab_logs)
        self.append_log("\n════════════════════════════════════════════════════")
        self.append_log(f"🚀 開始批次轉換任務，共 {len(self.tasks)} 個檔案...")

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.prog_bar.setValue(0)
        self.lbl_status.setText("正在轉換中...")

        opts = self.collect_options()

        self.worker = ConversionWorker(self.engine, self.tasks, opts)
        self.worker.log_signal.connect(self.append_log)
        self.worker.file_progress_signal.connect(self.on_worker_file_progress)
        self.worker.file_finished_signal.connect(self.on_worker_file_finished)
        self.worker.all_finished_signal.connect(self.on_worker_all_finished)
        self.worker.start()

    def on_worker_file_progress(self, idx: int, ratio: float, status_text: str):
        if 0 <= idx < len(self.tasks):
            self.tasks[idx]["status"] = "處理中..."
            self.refresh_task_table()
        
        total_tasks = len(self.tasks)
        overall_pct = int(((idx + ratio) / total_tasks) * 100)
        self.prog_bar.setValue(min(100, max(0, overall_pct)))
        self.lbl_progress_percent.setText(f"{self.prog_bar.value()}%")
        self.lbl_status.setText(status_text)

    def on_worker_file_finished(self, idx: int, success: bool, msg: str):
        if 0 <= idx < len(self.tasks):
            self.tasks[idx]["status"] = "完成" if success else "失敗"
            self.refresh_task_table()

    def on_worker_all_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.prog_bar.setValue(100)
        self.lbl_progress_percent.setText("100%")
        self.lbl_status.setText("全部轉換任務完成！")
        self.append_log("════════════════════════════════════════════════════")
        self.append_log("✨ 全部轉換作業已結束！")

        # 自動開啟資料夾
        if self.chk_auto_open.isChecked() and self.tasks:
            target_dir = self.edit_output_dir.text().strip()
            if not target_dir or not os.path.isdir(target_dir):
                target_dir = os.path.dirname(os.path.abspath(self.tasks[0]["filepath"]))
            self.open_folder(target_dir)

    def cancel_conversion(self):
        if self.worker and self.worker.isRunning():
            self.lbl_status.setText("正在取消轉換...")
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)

    def open_folder(self, folder_path: str):
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder_path)
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])
        except Exception:
            pass

    def toggle_theme(self):
        cur = self.cfg_mgr.get("theme", "dark")
        new_theme = "light" if cur == "dark" else "dark"
        self.cfg_mgr.set("theme", new_theme)
        self.cfg_mgr.save()
        self.apply_theme(new_theme)
        self.btn_theme_toggle.setText("切換淺色" if new_theme == "dark" else "切換深色")

    def apply_theme(self, theme_name: str):
        if theme_name == "light":
            self.setStyleSheet(LIGHT_THEME)
        else:
            self.setStyleSheet(DARK_THEME)

    def refresh_presets_combo(self):
        self.combo_presets.blockSignals(True)
        self.combo_presets.clear()
        presets = self.cfg_mgr.get_all_presets()
        for name in presets.keys():
            self.combo_presets.addItem(name)
        self.combo_presets.blockSignals(False)

    def on_preset_selected(self):
        name = self.combo_presets.currentText()
        presets = self.cfg_mgr.get_all_presets()
        if name in presets:
            p = presets[name]
            # 套用設定至 UI
            if "format" in p:
                idx = self.combo_format.findData(p["format"])
                if idx >= 0: self.combo_format.setCurrentIndex(idx)
            if "zh_conversion" in p:
                idx = self.combo_zh.findData(p["zh_conversion"])
                if idx >= 0: self.combo_zh.setCurrentIndex(idx)
            if "align" in p:
                idx = self.combo_align.findData(p["align"])
                if idx >= 0: self.combo_align.setCurrentIndex(idx)
            if "lang" in p:
                self.combo_lang.setCurrentText(p["lang"])
            if "indent" in p:
                self.spin_indent.setValue(p["indent"])
            if "bottom" in p:
                self.edit_bottom.setText(p["bottom"])
            if "line_height" in p:
                self.edit_line_height.setText(p["line_height"])
            if "separate_chapter_number" in p:
                self.chk_sep_chap.setChecked(p["separate_chapter_number"])
            if "tips" in p:
                self.chk_tips.setChecked(p["tips"])
            if "css_preset" in p:
                self.combo_css_preset.setCurrentText(p["css_preset"])
            if "volume_regex" in p:
                self.edit_volume.setText(p["volume_regex"])
            if "match_regex" in p:
                self.edit_match.setText(p["match_regex"])
            if "enable_volume" in p:
                self.chk_volume.setChecked(p["enable_volume"])
            self.update_command_preview()

    def on_save_preset_clicked(self):
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "另存預設方案", "請輸入方案名稱:")
        if ok and name.strip():
            opts = self.collect_options()
            preset_data = {
                "format": opts["format"],
                "zh_conversion": opts["zh_conversion"],
                "align": opts["align"],
                "lang": opts["lang"],
                "indent": opts["indent"],
                "bottom": opts["bottom"],
                "line_height": opts["line_height"],
                "separate_chapter_number": opts["separate_chapter_number"],
                "tips": opts["tips"],
                "css_preset": self.combo_css_preset.currentText(),
                "volume_regex": opts["volume_regex"],
                "match_regex": opts["match_regex"],
                "enable_volume": opts["enable_volume"]
            }
            self.cfg_mgr.save_user_preset(name.strip(), preset_data)
            self.refresh_presets_combo()
            self.combo_presets.setCurrentText(name.strip())
            QMessageBox.information(self, "成功", f"方案「{name.strip()}」已儲存！")

    def save_ui_to_settings(self):
        opts = self.collect_options()
        self.cfg_mgr.set("format", opts["format"])
        self.cfg_mgr.set("zh_conversion", opts["zh_conversion"])
        self.cfg_mgr.set("output_dir", opts["output_dir"])
        self.cfg_mgr.set("align", opts["align"])
        self.cfg_mgr.set("lang", opts["lang"])
        self.cfg_mgr.set("indent", opts["indent"])
        self.cfg_mgr.set("bottom", opts["bottom"])
        self.cfg_mgr.set("line_height", opts["line_height"])
        self.cfg_mgr.set("separate_chapter_number", opts["separate_chapter_number"])
        self.cfg_mgr.set("tips", opts["tips"])
        self.cfg_mgr.set("font_path", opts["font_path"])
        self.cfg_mgr.set("match_regex", opts["match_regex"])
        self.cfg_mgr.set("enable_volume", opts["enable_volume"])
        self.cfg_mgr.set("volume_regex", opts["volume_regex"])
        self.cfg_mgr.set("exclude_regex", opts["exclude_regex"])
        self.cfg_mgr.set("max_title_len", opts["max_title_len"])
        self.cfg_mgr.set("unknow_title", opts["unknow_title"])
        self.cfg_mgr.set("cover_mode", opts["cover_mode"])
        self.cfg_mgr.set("custom_cover_path", opts["custom_cover_path"])
        self.cfg_mgr.set("orly_color", opts["orly_color"])
        self.cfg_mgr.set("orly_idx", opts["orly_idx"])
        self.cfg_mgr.set("css_preset", self.combo_css_preset.currentText())
        self.cfg_mgr.set("auto_open_folder", self.chk_auto_open.isChecked())
        self.cfg_mgr.save()

    def load_settings_to_ui(self):
        c = self.cfg_mgr.config
        idx = self.combo_format.findData(c.get("format", "all"))
        if idx >= 0: self.combo_format.setCurrentIndex(idx)

        idx_zh = self.combo_zh.findData(c.get("zh_conversion", "s2tw"))
        if idx_zh >= 0: self.combo_zh.setCurrentIndex(idx_zh)

        self.edit_output_dir.setText(c.get("output_dir", ""))
        
        idx_al = self.combo_align.findData(c.get("align", "center"))
        if idx_al >= 0: self.combo_align.setCurrentIndex(idx_al)

        self.combo_lang.setCurrentText(c.get("lang", "zh-TW"))
        self.spin_indent.setValue(c.get("indent", 2))
        self.edit_bottom.setText(c.get("bottom", "1em"))
        self.edit_line_height.setText(c.get("line_height", "1.85"))
        self.chk_sep_chap.setChecked(c.get("separate_chapter_number", True))
        self.chk_tips.setChecked(c.get("tips", False))
        self.edit_font.setText(c.get("font_path", ""))
        self.edit_match.setText(c.get("match_regex", ""))
        self.chk_volume.setChecked(c.get("enable_volume", True))
        self.edit_volume.setText(c.get("volume_regex", DEFAULT_VOLUME_REGEX))
        self.edit_exclude.setText(c.get("exclude_regex", DEFAULT_EXCLUDE_REGEX))
        self.spin_max_len.setValue(c.get("max_title_len", 35))
        self.edit_unknow_title.setText(c.get("unknow_title", "章節正文"))

        cover_m = c.get("cover_mode", "auto")
        if cover_m == "custom":
            self.radio_cover_custom.setChecked(True)
        elif cover_m == "orly":
            self.radio_cover_orly.setChecked(True)
        else:
            self.radio_cover_auto.setChecked(True)

        self.edit_cover_path.setText(c.get("custom_cover_path", ""))
        self.edit_orly_color.setText(c.get("orly_color", ""))
        self.spin_orly_idx.setValue(c.get("orly_idx", -1))

        css_p = c.get("css_preset", "臺灣典雅實體書 (Classic Book)")
        self.combo_css_preset.setCurrentText(css_p)
        if css_p in CSS_PRESETS:
            self.edit_css_content.setPlainText(CSS_PRESETS[css_p]["css"])

        self.chk_auto_open.setChecked(c.get("auto_open_folder", True))
        self.update_command_preview()


def run_desktop_app():
    app = QApplication(sys.argv)
    app.setApplicationName("kaf-cli GUI (繁體中文專業版)")
    win = KafMainWindow()
    win.show()
    sys.exit(app.exec_())
