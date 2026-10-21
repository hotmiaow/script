# -*- coding: utf-8 -*-
"""
kaf-cli 繁體中文桌面圖形介面 (PyQt5)
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox,
    QCheckBox, QRadioButton, QButtonGroup, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextEdit, QTextBrowser, QProgressBar, QFileDialog,
    QMessageBox, QSplitter, QDialog, QTreeWidget, QTreeWidgetItem,
    QFrame, QColorDialog, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, qInstallMessageHandler, QTimer
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
from .gemma_engine import (
    GemmaEmbeddingClient, process_novel_with_gemma,
    NovelTextOrganizer, NovelCharacterExtractor
)


class GemmaAnalysisWorker(QThread):
    """背景執行 Embedding Gemma 2 語意分析、去重重排與角色萃取的工作線程"""
    progress_signal = pyqtSignal(float, str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, filepath: str, options: Dict[str, Any]):
        super().__init__()
        self.filepath = filepath
        self.options = options

    def run(self):
        try:
            res = process_novel_with_gemma(
                input_filepath=self.filepath,
                backend=self.options.get("backend", "fast_local"),
                model_name=self.options.get("model_name", "google/embeddinggemma-2"),
                ollama_url=self.options.get("ollama_url", "http://localhost:11434"),
                dedup=self.options.get("dedup", True),
                clean_noise=self.options.get("clean_noise", True),
                rearrange=self.options.get("rearrange", True),
                auto_titles=self.options.get("auto_titles", True),
                inject_character_guide=self.options.get("inject_character_guide", True),
                max_characters=self.options.get("max_characters", 10),
                progress_callback=lambda r, m: self.progress_signal.emit(r, m)
            )
            if res.get("success"):
                self.finished_signal.emit(res)
            else:
                self.error_signal.emit(res.get("error", "未知錯誤"))
        except Exception as e:
            self.error_signal.emit(str(e))


class FileScanWorker(QThread):
    """
    背景非同步掃描並分析書籍檔案之章節規則與中繼資料，避免拖曳加入時阻塞 GUI 主執行緒
    """
    file_progress_signal = pyqtSignal(int, int, str, float)  # current_idx, total_count, filename, percent
    file_analyzed_signal = pyqtSignal(str, dict)             # filepath, {meta, det}
    all_finished_signal = pyqtSignal(int)                    # total_analyzed

    def __init__(self, paths: Optional[List[str]] = None):
        super().__init__()
        self._queue = list(paths or [])
        self._is_cancelled = False

    def add_paths(self, new_paths: List[str]):
        """支援在背景掃描進行中動態追加新拖入的書籍檔案"""
        self._queue.extend(new_paths)

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        analyzed_count = 0
        idx = 0
        while idx < len(self._queue):
            if self._is_cancelled:
                break
            p = self._queue[idx]
            filename = os.path.basename(p)
            total = len(self._queue)
            pct = ((idx + 1) / max(total, 1)) * 100.0

            # 發送進度通知
            self.file_progress_signal.emit(idx + 1, total, filename, pct)

            try:
                # 1. 擷取書名與作者元資料 (包含 PDF 內建 Title / Author 讀取)
                meta = parse_filename_meta(p, auto_to_tw=True)
                # 2. 自動偵測最合適之章節匹配規則 (在背景執行緒中安全執行)
                det = auto_detect_best_rule(p)
                result_payload = {
                    "filepath": p,
                    "meta": meta,
                    "det": det
                }
                self.file_analyzed_signal.emit(p, result_payload)
                analyzed_count += 1
            except Exception as e:
                # 發生異常時回傳預設資訊，避免中斷整體佇列
                fallback = {
                    "filepath": p,
                    "meta": {"title": os.path.splitext(filename)[0], "author": "YSTYLE"},
                    "det": {
                        "rule_name": "自動智慧識別 (預設)",
                        "regex": "",
                        "max_len": 35,
                        "chapter_count": 0,
                        "candidates": []
                    }
                }
                self.file_analyzed_signal.emit(p, fallback)

            idx += 1

        self.all_finished_signal.emit(analyzed_count)


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
            if success and res.get("output_files"):
                task["output_files"] = res.get("output_files")
            self.file_finished_signal.emit(idx, success, msg)

        self.all_finished_signal.emit()


class ProcessStepperWidget(QFrame):
    """可視化 4 階段 Pipeline 流程導引與即時指示器（緊湊自適應版）"""
    STEPS = [
        ("1", "文本排版預處理", "短行硬換行拼接 / 斷句還原"),
        ("2", "AI 語意增強", "Gemma 2 去重 / 時序重排 / 人物導讀"),
        ("3", "章節匹配檢驗", "自動正則探測 / 多層目錄熔合"),
        ("4", "正體與電子書編譯", "s2tw 正體化 / kaf-cli 編譯生成"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.step_cards = []
        self.step_icons = []
        self.step_titles = []
        self.step_descs = []
        self.current_step = 0
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QFrame#stepperContainer {
                background: rgba(18, 22, 30, 0.6);
                border: 1px solid rgba(59, 130, 246, 0.25);
                border-radius: 6px;
            }
        """)
        self.setObjectName("stepperContainer")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(6)

        for idx, (num_str, title, desc) in enumerate(self.STEPS, start=1):
            card = QFrame()
            card.setToolTip(f"步驟 {idx}/4: {title}\n{desc}")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6, 3, 6, 3)
            card_layout.setSpacing(1)

            header_row = QHBoxLayout()
            header_row.setSpacing(4)
            lbl_num = QLabel(f"<b>{num_str}.</b>")
            lbl_num.setStyleSheet("font-size: 11px; color: #64748b;")
            lbl_icon = QLabel("⚪")
            lbl_icon.setStyleSheet("font-size: 11px;")
            lbl_title = QLabel(title)
            lbl_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #94a3b8;")
            header_row.addWidget(lbl_num)
            header_row.addWidget(lbl_title)
            header_row.addStretch()
            header_row.addWidget(lbl_icon)
            card_layout.addLayout(header_row)

            lbl_desc = QLabel(desc)
            lbl_desc.setStyleSheet("font-size: 9px; color: #64748b;")
            lbl_desc.setMaximumHeight(14)
            card_layout.addWidget(lbl_desc)

            self._set_card_style(card, "pending")

            layout.addWidget(card)
            self.step_cards.append(card)
            self.step_icons.append(lbl_icon)
            self.step_titles.append(lbl_title)
            self.step_descs.append(lbl_desc)

    def _set_card_style(self, card: QFrame, state: str):
        if state == "active":
            card.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(59, 130, 246, 0.25), stop:1 rgba(37, 99, 235, 0.1));
                    border: 1px solid #3b82f6;
                    border-radius: 4px;
                }
            """)
        elif state == "completed":
            card.setStyleSheet("""
                QFrame {
                    background: rgba(16, 185, 129, 0.12);
                    border: 1px solid #10b981;
                    border-radius: 4px;
                }
            """)
        elif state == "failed":
            card.setStyleSheet("""
                QFrame {
                    background: rgba(239, 68, 68, 0.12);
                    border: 1px solid #ef4444;
                    border-radius: 4px;
                }
            """)
        else:  # pending
            card.setStyleSheet("""
                QFrame {
                    background: rgba(30, 41, 59, 0.35);
                    border: 1px solid rgba(71, 85, 105, 0.3);
                    border-radius: 4px;
                }
            """)

    def reset(self):
        self.current_step = 0
        for i, card in enumerate(self.step_cards):
            self._set_card_style(card, "pending")
            self.step_icons[i].setText("⚪")
            self.step_titles[i].setStyleSheet("font-size: 11px; font-weight: bold; color: #94a3b8;")

    def set_active_step(self, step_idx: int, detail: str = ""):
        self.current_step = step_idx
        for i in range(len(self.step_cards)):
            idx_1based = i + 1
            if idx_1based < step_idx:
                self._set_card_style(self.step_cards[i], "completed")
                self.step_icons[i].setText("✅")
                self.step_titles[i].setStyleSheet("font-size: 11px; font-weight: bold; color: #10b981;")
            elif idx_1based == step_idx:
                self._set_card_style(self.step_cards[i], "active")
                self.step_icons[i].setText("⚡")
                self.step_titles[i].setStyleSheet("font-size: 11px; font-weight: bold; color: #60a5fa;")
                if detail:
                    self.step_descs[i].setText(detail)
            else:
                self._set_card_style(self.step_cards[i], "pending")
                self.step_icons[i].setText("⚪")
                self.step_titles[i].setStyleSheet("font-size: 11px; font-weight: bold; color: #64748b;")

    def set_all_completed(self):
        for i in range(len(self.step_cards)):
            self._set_card_style(self.step_cards[i], "completed")
            self.step_icons[i].setText("✅")
            self.step_titles[i].setStyleSheet("font-size: 11px; font-weight: bold; color: #10b981;")


def make_scrollable(widget: QWidget) -> QScrollArea:
    """將分頁包裝於自動滾動區域中，確保任何解析度下皆可自適應調整縮放而不裁切"""
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(widget)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    return sa


class ChapterPreviewDialog(QDialog):
    """章節匹配即時測試與預覽視窗"""
    def __init__(self, result: Dict[str, Any], filepath: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"章節目錄匹配預覽 - {os.path.basename(filepath)}")
        self.resize(750, 520)

        layout = QVBoxLayout(self)

        # 頂部摘要卡片
        summary_group = QGroupBox("統計摘要")
        sum_layout = QHBoxLayout(summary_group)
        
        if "stats_summary" in result:
            sum_layout.addWidget(QLabel(f"<span style='color:#a3e635;font-weight:bold;'>{result['stats_summary']}</span>"))
        else:
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
        self.scan_worker: Optional[FileScanWorker] = None
        self.tasks: List[Dict[str, Any]] = []

        self._is_loading_settings = True
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._do_save_settings)

        self.init_ui()
        self.load_settings_to_ui()
        self.bind_settings_auto_save()
        self._is_loading_settings = False

        self.update_cli_status()
        self.setAcceptDrops(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not getattr(self, "_is_loading_settings", False):
            self.schedule_save_settings()

    def closeEvent(self, event):
        try:
            self.save_ui_to_settings()
        except Exception:
            pass

        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1000)

        event.accept()

    def init_ui(self):
        self.setWindowTitle("kaf-cli 繁體中文電子書轉換器 (專業 GUI 版)")

        # 套用主題
        self.apply_theme(self.cfg_mgr.get("theme", "dark"))

        # 自適應螢幕解析度調整初始視窗大小 (依螢幕比例縮放，避免過大超出螢幕，並支援記憶前次視窗大小)
        screen = QApplication.primaryScreen()
        saved_w = self.cfg_mgr.get("window_width")
        saved_h = self.cfg_mgr.get("window_height")

        if screen:
            avail = screen.availableGeometry()
            if saved_w and saved_h and int(saved_w) >= 640 and int(saved_h) >= 440:
                init_w = min(int(saved_w), avail.width())
                init_h = min(int(saved_h), avail.height())
                self.resize(init_w, init_h)
            else:
                init_w = min(880, max(680, int(avail.width() * 0.85)))
                init_h = min(640, max(460, int(avail.height() * 0.82)))
                self.resize(init_w, init_h)
            geo = self.geometry()
            geo.moveCenter(avail.center())
            self.setGeometry(geo)
        else:
            if saved_w and saved_h and int(saved_w) >= 640 and int(saved_h) >= 440:
                self.resize(int(saved_w), int(saved_h))
            else:
                self.resize(850, 580)

        # 允許視窗自由縮放至小螢幕尺寸
        self.setMinimumSize(640, 440)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # 頂部狀態與操作欄 (緊湊自適應)
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        
        # 標題與版本
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title_label = QLabel("<span style='font-size:16px; font-weight:bold; color:#3b82f6;'>kaf-cli</span> <span style='font-size:14px; font-weight:bold;'>電子書轉換器</span>")
        self.lbl_cli_status = QLabel("正在檢測 kaf-cli 狀態...")
        self.lbl_cli_status.setStyleSheet("font-size: 11px; color: #888;")
        title_box.addWidget(title_label)
        title_box.addWidget(self.lbl_cli_status)
        top_bar.addLayout(title_box)

        top_bar.addStretch()

        # 預設方案下拉
        lbl_preset = QLabel("方案:")
        lbl_preset.setStyleSheet("font-size: 12px;")
        top_bar.addWidget(lbl_preset)
        self.combo_presets = QComboBox()
        self.combo_presets.setMaximumWidth(180)
        self.refresh_presets_combo()
        self.combo_presets.currentIndexChanged.connect(self.on_preset_selected)
        top_bar.addWidget(self.combo_presets)

        btn_save_preset = QPushButton("另存")
        btn_save_preset.setToolTip("另存當前參數為快速預設方案")
        btn_save_preset.setFixedWidth(50)
        btn_save_preset.clicked.connect(self.on_save_preset_clicked)
        top_bar.addWidget(btn_save_preset)

        # 核心執行檔設定
        btn_cli_locate = QPushButton("核心設定")
        btn_cli_locate.setToolTip("指定 kaf-cli 核心執行檔路徑")
        btn_cli_locate.clicked.connect(self.on_locate_cli_clicked)
        top_bar.addWidget(btn_cli_locate)

        # 主題切換
        self.btn_theme_toggle = QPushButton("切換淺色" if self.cfg_mgr.get("theme") == "dark" else "切換深色")
        self.btn_theme_toggle.clicked.connect(self.toggle_theme)
        top_bar.addWidget(self.btn_theme_toggle)

        main_layout.addLayout(top_bar)

        # 分頁控制項
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideRight)
        
        # 建立分頁
        self.tab_files = QWidget()
        self.tab_typography = QWidget()
        self.tab_rules = QWidget()
        self.tab_cover = QWidget()
        self.tab_css = QWidget()
        self.tab_gemma = QWidget()
        self.tab_logs = QWidget()

        self.setup_tab_files()
        self.setup_tab_typography()
        self.setup_tab_rules()
        self.setup_tab_cover()
        self.setup_tab_css()
        self.setup_tab_gemma()
        self.setup_tab_logs()

        self.tabs.addTab(make_scrollable(self.tab_files), "📚 檔案與佇列")
        self.tabs.addTab(make_scrollable(self.tab_typography), "📐 排版與版面")
        self.tabs.addTab(make_scrollable(self.tab_rules), "🔍 章節與分卷匹配")
        self.tabs.addTab(make_scrollable(self.tab_cover), "🎨 封面設定")
        self.tabs.addTab(make_scrollable(self.tab_css), "🖋️ 自訂 CSS 樣式")
        self.tabs.addTab(make_scrollable(self.tab_gemma), "🤖 Gemma 2 文本與角色")
        self.tabs.addTab(self.tab_logs, "💻 即時日誌與終端")

        main_layout.addWidget(self.tabs)

        # 底部轉換控制區 (緊湊版)
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet("background: rgba(30, 34, 42, 0.4); border-radius: 6px; padding: 4px;")
        bottom_layout = QVBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(8, 4, 8, 4)
        bottom_layout.setSpacing(4)

        # 4 階段流程導引指示列
        self.stepper = ProcessStepperWidget()
        bottom_layout.addWidget(self.stepper)

        # 命令列即時預覽
        cmd_preview_box = QHBoxLayout()
        cmd_preview_box.setSpacing(6)
        cmd_preview_box.addWidget(QLabel("<b>指令:</b>"))
        self.edit_cmd_preview = QLineEdit()
        self.edit_cmd_preview.setReadOnly(True)
        self.edit_cmd_preview.setStyleSheet("color: #79c0ff; font-family: monospace; font-size: 11px;")
        cmd_preview_box.addWidget(self.edit_cmd_preview)
        btn_copy_cmd = QPushButton("複製")
        btn_copy_cmd.setFixedWidth(50)
        btn_copy_cmd.clicked.connect(self.copy_command_preview)
        cmd_preview_box.addWidget(btn_copy_cmd)
        bottom_layout.addLayout(cmd_preview_box)

        # 進度條與狀態文字
        prog_box = QHBoxLayout()
        prog_box.setSpacing(6)
        self.lbl_status = QLabel("就緒：請拖入或新增小說 txt 檔案以開始。")
        self.lbl_status.setStyleSheet("font-size: 11px;")
        prog_box.addWidget(self.lbl_status)
        prog_box.addStretch()
        self.lbl_progress_percent = QLabel("0%")
        self.lbl_progress_percent.setStyleSheet("font-size: 11px; font-weight: bold;")
        prog_box.addWidget(self.lbl_progress_percent)
        bottom_layout.addLayout(prog_box)

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setMaximumHeight(14)
        bottom_layout.addWidget(self.prog_bar)

        # 操作按鈕
        btn_action_box = QHBoxLayout()
        self.chk_auto_open = QCheckBox("完成後開啟目錄")
        self.chk_auto_open.setStyleSheet("font-size: 11px;")
        self.chk_auto_open.setChecked(self.cfg_mgr.get("auto_open_folder", True))
        btn_action_box.addWidget(self.chk_auto_open)

        btn_action_box.addStretch()

        self.btn_cancel = QPushButton("⏹ 取消")
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
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 🚀 3 步極速使用指南 Banner (自適應折行)
        guide_banner = QFrame()
        guide_banner.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(14, 165, 233, 0.12), stop:1 rgba(99, 102, 241, 0.08));
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 6px;
            }
        """)
        guide_layout = QHBoxLayout(guide_banner)
        guide_layout.setContentsMargins(8, 4, 8, 4)
        guide_lbl = QLabel(
            "<b>🚀 極速 3 步:</b> "
            "<span style='color:#60a5fa; font-weight:bold;'>① 拖入/新增小說 TXT</span> ➜ "
            "<span style='color:#a3e635; font-weight:bold;'>② 一鍵自動偵測最佳規則</span> ➜ "
            "<span style='color:#f472b6; font-weight:bold;'>③ 點擊開始轉換</span>"
        )
        guide_lbl.setWordWrap(True)
        guide_lbl.setStyleSheet("font-size: 11px; color: #cbd5e1;")
        guide_layout.addWidget(guide_lbl)
        layout.addWidget(guide_banner)

        # 工具按鈕列 (拆為雙排緊湊排版，避免小螢幕寬度溢出)
        btn_box = QVBoxLayout()
        btn_box.setSpacing(4)

        row_btn1 = QHBoxLayout()
        row_btn1.setSpacing(6)
        btn_add_file = QPushButton("＋ 新增書籍 (TXT / PDF)")
        btn_add_file.clicked.connect(self.add_txt_files_dialog)
        row_btn1.addWidget(btn_add_file)

        btn_add_dir = QPushButton("📁 新增資料夾 (批次掃描)")
        btn_add_dir.clicked.connect(self.add_directory_dialog)
        row_btn1.addWidget(btn_add_dir)

        btn_auto_detect = QPushButton("⚡ 一鍵自動偵測最佳規則")
        btn_auto_detect.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 4px 10px; border-radius: 4px;")
        btn_auto_detect.clicked.connect(self.auto_detect_all_tasks)
        row_btn1.addWidget(btn_auto_detect)
        row_btn1.addStretch()
        btn_box.addLayout(row_btn1)

        row_btn2 = QHBoxLayout()
        row_btn2.setSpacing(6)
        btn_remove_sel = QPushButton("✕ 移除所選")
        btn_remove_sel.clicked.connect(self.remove_selected_task)
        row_btn2.addWidget(btn_remove_sel)

        btn_clear = QPushButton("🗑️ 清空清單")
        btn_clear.clicked.connect(self.clear_tasks)
        row_btn2.addWidget(btn_clear)

        row_btn2.addStretch()
        tip_drag = QLabel("💡 支援將 TXT / PDF 檔案直接拖入視窗")
        tip_drag.setStyleSheet("color: #888; font-size: 11px;")
        row_btn2.addWidget(tip_drag)
        btn_box.addLayout(row_btn2)

        layout.addLayout(btn_box)

        # 背景非同步掃描與規則分析即時進度列 (平時隱藏，拖入/新增檔案時顯示)
        self.scan_progress_frame = QFrame()
        self.scan_progress_frame.setStyleSheet("""
            QFrame {
                background: rgba(14, 165, 233, 0.12);
                border: 1px solid rgba(56, 189, 248, 0.4);
                border-radius: 6px;
                padding: 4px;
            }
        """)
        scan_layout = QVBoxLayout(self.scan_progress_frame)
        scan_layout.setContentsMargins(6, 4, 6, 4)
        scan_layout.setSpacing(3)

        scan_info_box = QHBoxLayout()
        self.lbl_scan_status = QLabel("🔍 正在背景分析書籍章節結構...")
        self.lbl_scan_status.setStyleSheet("font-size: 11px; font-weight: bold; color: #38bdf8;")
        scan_info_box.addWidget(self.lbl_scan_status)
        scan_info_box.addStretch()
        self.lbl_scan_percent = QLabel("0%")
        self.lbl_scan_percent.setStyleSheet("font-size: 11px; font-weight: bold; color: #38bdf8;")
        scan_info_box.addWidget(self.lbl_scan_percent)
        scan_layout.addLayout(scan_info_box)

        self.scan_progress_bar = QProgressBar()
        self.scan_progress_bar.setRange(0, 100)
        self.scan_progress_bar.setValue(0)
        self.scan_progress_bar.setMaximumHeight(8)
        self.scan_progress_bar.setTextVisible(False)
        self.scan_progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: rgba(255, 255, 255, 0.1);
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
                border-radius: 4px;
            }
        """)
        scan_layout.addWidget(self.scan_progress_bar)
        self.scan_progress_frame.hide()
        layout.addWidget(self.scan_progress_frame)

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
        self.table_tasks.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table_tasks.itemSelectionChanged.connect(self.update_command_preview)
        layout.addWidget(self.table_tasks)

        # 全域輸出與格式選項
        opt_group = QGroupBox("輸出與語言核心選項")
        opt_layout = QVBoxLayout(opt_group)
        opt_layout.setContentsMargins(8, 6, 8, 6)
        opt_layout.setSpacing(4)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("書籍類型:"))
        self.combo_book_type = QComboBox()
        self.combo_book_type.addItem("自動識別 (推薦)", "auto")
        self.combo_book_type.addItem("小說 / 故事 (Story)", "story")
        self.combo_book_type.addItem("通用書籍 / 人文社科 (General)", "general")
        self.combo_book_type.addItem("技術手冊 / 學術文檔 (Technical)", "technical")
        self.combo_book_type.currentIndexChanged.connect(self.update_command_preview)
        row1.addWidget(self.combo_book_type)

        row1.addSpacing(10)

        row1.addWidget(QLabel("PDF 處理模式:"))
        self.combo_pdf_mode = QComboBox()
        self.combo_pdf_mode.addItem("自動推薦 (技術書直轉高保真，小說重排)", "auto")
        self.combo_pdf_mode.addItem("直轉 EPUB (高保真排版，完整保留代碼/表格/插圖)", "direct_epub")
        self.combo_pdf_mode.addItem("小說文字精排 (轉純文字後以 kaf-cli 重排)", "novel_txt")
        self.combo_pdf_mode.currentIndexChanged.connect(self.update_command_preview)
        row1.addWidget(self.combo_pdf_mode)
        opt_layout.addLayout(row1)

        row1_fmt = QHBoxLayout()
        row1_fmt.addWidget(QLabel("輸出格式:"))
        self.combo_format = QComboBox()
        self.combo_format.addItem("全部生成 (EPUB + MOBI + AZW3)", "all")
        self.combo_format.addItem("僅 EPUB (.epub)", "epub")
        self.combo_format.addItem("僅 MOBI (.mobi)", "mobi")
        self.combo_format.addItem("僅 AZW3 (.azw3)", "azw3")
        self.combo_format.currentIndexChanged.connect(self.update_command_preview)
        row1_fmt.addWidget(self.combo_format)

        row1_fmt.addSpacing(10)

        row1_fmt.addWidget(QLabel("內文簡繁:"))
        self.combo_zh = QComboBox()
        self.combo_zh.addItem("轉臺灣正體 (s2tw, 推薦)", "s2tw")
        self.combo_zh.addItem("轉香港繁體 (s2hk)", "s2hk")
        self.combo_zh.addItem("轉標準繁體 (s2t)", "s2t")
        self.combo_zh.addItem("不轉換 (保持原文)", "none")
        self.combo_zh.currentIndexChanged.connect(self.update_command_preview)
        row1_fmt.addWidget(self.combo_zh)
        opt_layout.addLayout(row1_fmt)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("輸出目錄:"))
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

        self.chk_remove_hard_breaks = QCheckBox("🧹 智慧修復短行硬換行（自動拼接斷句、修復每行過短破碎段落）")
        self.chk_remove_hard_breaks.setChecked(True)
        self.chk_remove_hard_breaks.setStyleSheet("font-weight: bold; color: #a3e635; font-size: 11px;")
        opt_layout.addWidget(self.chk_remove_hard_breaks)

        self.chk_enable_gemma_pipeline = QCheckBox("🤖 啟用 Embedding Gemma 2 文本重排與角色/世界觀導讀")
        self.chk_enable_gemma_pipeline.setChecked(True)
        self.chk_enable_gemma_pipeline.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 11px;")
        opt_layout.addWidget(self.chk_enable_gemma_pipeline)

        self.chk_enable_math = QCheckBox("📐 支援 LaTeX 數學公式 (Pandoc MathML 矢量渲染，直轉技術書/論文專用)")
        self.chk_enable_math.setChecked(True)
        self.chk_enable_math.setStyleSheet("font-weight: bold; color: #c084fc; font-size: 11px;")
        opt_layout.addWidget(self.chk_enable_math)

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

        # 段落間距
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("段落間距 (-bottom):"))
        self.edit_bottom = QLineEdit("1em")
        self.edit_bottom.setFixedWidth(80)
        self.edit_bottom.textChanged.connect(self.update_command_preview)
        row3.addWidget(self.edit_bottom)
        for val in ["0.5em", "1em", "1.5em"]:
            btn = QPushButton(val)
            btn.setFixedWidth(46)
            btn.clicked.connect(lambda _, v=val: self.edit_bottom.setText(v))
            row3.addWidget(btn)
        row3.addStretch()
        g_layout.addLayout(row3)

        # 行間距
        row3_2 = QHBoxLayout()
        row3_2.addWidget(QLabel("行間距/行高 (-line-height):"))
        self.edit_line_height = QLineEdit("1.85")
        self.edit_line_height.setFixedWidth(80)
        self.edit_line_height.textChanged.connect(self.update_command_preview)
        row3_2.addWidget(self.edit_line_height)
        for val in ["1.5", "1.75", "1.85", "2.0"]:
            btn = QPushButton(val)
            btn.setFixedWidth(42)
            btn.clicked.connect(lambda _, v=val: self.edit_line_height.setText(v))
            row3_2.addWidget(btn)
        row3_2.addStretch()
        g_layout.addLayout(row3_2)

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

        self.btn_test_unwrap = QPushButton("🧹 測試短行硬換行修復 (段落預覽)")
        self.btn_test_unwrap.setStyleSheet("background-color: #4d7c0f; color: white; font-weight: bold; padding: 8px 18px;")
        self.btn_test_unwrap.clicked.connect(self.run_unwrap_test)
        btn_box.addWidget(self.btn_test_unwrap)

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

        self.radio_cover_orly = QRadioButton("Orly 經典動物封面（本地智慧排版、長標題自動縮放與換行）")
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

    # ================= 分頁：Embedding Gemma 2 智慧文本與角色 =================
    def setup_tab_gemma(self):
        layout = QVBoxLayout(self.tab_gemma)

        # 頂部說明橫幅
        top_banner = QFrame()
        top_banner.setStyleSheet("background: rgba(14, 165, 233, 0.08); border: 1px solid rgba(14, 165, 233, 0.25); border-radius: 8px; padding: 10px;")
        banner_layout = QVBoxLayout(top_banner)
        lbl_title = QLabel("<b>🤖 Embedding Gemma 2 智慧文本重排與登場人物／世界觀導讀系統</b>")
        lbl_title.setStyleSheet("font-size: 15px; color: #38bdf8;")
        banner_layout.addWidget(lbl_title)
        lbl_desc = QLabel(
            "基於 Google DeepMind 開源之 Embedding Gemma 2 (740M 參數 / 768 維向量空間) 深度語意演算法，"
            "自動檢測並剔除論壇重複貼文、過濾水帖雜訊、依敘事時序重排錯位段落，並深度萃取主角、配角、反派與世界觀，"
            "於電子書產出時自動注入典雅的「登場人物與世界觀導讀」序章！"
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.4;")
        banner_layout.addWidget(lbl_desc)
        layout.addWidget(top_banner)

        # 左右分割面板
        splitter = QSplitter(Qt.Horizontal)

        # 左側面板：後端與參數設定
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 1. 後端與模型配置
        group_backend = QGroupBox("1. 向量模型與後端配置")
        gb_layout = QVBoxLayout(group_backend)

        row_be = QHBoxLayout()
        row_be.addWidget(QLabel("向量運算後端:"))
        self.combo_gemma_backend = QComboBox()
        self.combo_gemma_backend.addItem("內建繁簡感知語意引擎 (免設定、離線即開即用)", "fast_local")
        self.combo_gemma_backend.addItem("Ollama 本機服務 (google/embeddinggemma-2)", "ollama")
        self.combo_gemma_backend.addItem("HuggingFace (SentenceTransformers)", "transformers")
        self.combo_gemma_backend.addItem("自訂 OpenAI 相容 API (/v1/embeddings)", "api")
        self.combo_gemma_backend.currentIndexChanged.connect(self.on_gemma_backend_changed)
        row_be.addWidget(self.combo_gemma_backend)
        gb_layout.addLayout(row_be)

        # Ollama 網址與模型名稱
        self.row_gemma_ollama = QHBoxLayout()
        self.row_gemma_ollama.addWidget(QLabel("服務網址:"))
        self.edit_gemma_url = QLineEdit("http://localhost:11434")
        self.row_gemma_ollama.addWidget(self.edit_gemma_url)
        gb_layout.addLayout(self.row_gemma_ollama)

        row_model = QHBoxLayout()
        row_model.addWidget(QLabel("模型名稱:"))
        self.edit_gemma_model = QLineEdit("google/embeddinggemma-2")
        self.edit_gemma_model.setPlaceholderText("google/embeddinggemma-2, embeddinggemma-2, gemma2")
        row_model.addWidget(self.edit_gemma_model)
        gb_layout.addLayout(row_model)

        row_conn = QHBoxLayout()
        btn_test_conn = QPushButton("⚡ 測試後端連線狀態")
        btn_test_conn.clicked.connect(self.test_gemma_connection)
        row_conn.addWidget(btn_test_conn)

        self.lbl_gemma_status = QLabel("狀態: 內建語意引擎已就緒")
        self.lbl_gemma_status.setStyleSheet("color: #10b981; font-size: 12px;")
        row_conn.addWidget(self.lbl_gemma_status)
        row_conn.addStretch()
        gb_layout.addLayout(row_conn)

        left_layout.addWidget(group_backend)

        # 2. 智慧功能開關
        group_features = QGroupBox("2. 文本校驗、重排與萃取選項")
        gf_layout = QVBoxLayout(group_features)

        self.chk_gemma_dedup = QCheckBox("語意去重 (自動比對並剔除論壇重複發帖與引言覆誦，相似度 ≥ 0.92)")
        self.chk_gemma_dedup.setChecked(True)
        gf_layout.addWidget(self.chk_gemma_dedup)

        self.chk_gemma_noise = QCheckBox("水帖與雜訊清洗 (過濾「頂樓主、沙发、求更新、脫水廣告」等灌水內容)")
        self.chk_gemma_noise.setChecked(True)
        gf_layout.addWidget(self.chk_gemma_noise)

        self.chk_gemma_rearrange = QCheckBox("時序與段落銜接重排 (依發帖時間戳與語意連貫度自動修復錯亂段落)")
        self.chk_gemma_rearrange.setChecked(True)
        gf_layout.addWidget(self.chk_gemma_rearrange)

        self.chk_gemma_titles = QCheckBox("章節標題語意補全 (為純日期或純樓層章節提煉 4~8 字精煉中文章節標題)")
        self.chk_gemma_titles.setChecked(True)
        gf_layout.addWidget(self.chk_gemma_titles)

        self.chk_gemma_inject = QCheckBox("生成並在電子書第 1 章前自動注入「登場人物與世界觀導讀」序章")
        self.chk_gemma_inject.setChecked(True)
        gf_layout.addWidget(self.chk_gemma_inject)

        row_chars = QHBoxLayout()
        row_chars.addWidget(QLabel("最多深度萃取人物數量:"))
        self.spin_gemma_chars = QSpinBox()
        self.spin_gemma_chars.setRange(2, 30)
        self.spin_gemma_chars.setValue(8)
        row_chars.addWidget(self.spin_gemma_chars)
        row_chars.addStretch()
        gf_layout.addLayout(row_chars)

        left_layout.addWidget(group_features)

        # 3. 執行動作與進度
        group_actions = QGroupBox("3. 執行與分析")
        ga_layout = QVBoxLayout(group_actions)

        self.btn_run_gemma = QPushButton("⚡ 對目前選取小說執行 Gemma 2 深度分析與重排")
        self.btn_run_gemma.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 10px; font-size: 13px; border-radius: 6px;")
        self.btn_run_gemma.clicked.connect(self.run_gemma_analysis_selected)
        ga_layout.addWidget(self.btn_run_gemma)

        self.progress_gemma = QProgressBar()
        self.progress_gemma.setRange(0, 100)
        self.progress_gemma.setValue(0)
        self.progress_gemma.setTextVisible(True)
        ga_layout.addWidget(self.progress_gemma)

        row_export = QHBoxLayout()
        self.btn_export_gemma = QPushButton("📥 匯出分析報告 JSON 與最佳化 TXT")
        self.btn_export_gemma.setEnabled(False)
        self.btn_export_gemma.clicked.connect(self.export_gemma_result)
        row_export.addWidget(self.btn_export_gemma)
        ga_layout.addLayout(row_export)

        left_layout.addWidget(group_actions)
        left_layout.addStretch()
        splitter.addWidget(left_widget)

        # 右側面板：結果視覺化展示
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.gemma_tabs = QTabWidget()

        # 分頁 A: 登場人物清單
        tab_chars = QWidget()
        tc_layout = QVBoxLayout(tab_chars)
        self.table_gemma_chars = QTableWidget()
        self.table_gemma_chars.setColumnCount(5)
        self.table_gemma_chars.setHorizontalHeaderLabels(["人物姓名", "定位角色", "身分背景", "性格特質", "重要事蹟/關係"])
        self.table_gemma_chars.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_gemma_chars.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_gemma_chars.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_gemma_chars.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_gemma_chars.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table_gemma_chars.setAlternatingRowColors(True)
        tc_layout.addWidget(self.table_gemma_chars)
        self.gemma_tabs.addTab(tab_chars, "👥 登場人物清單")

        # 分頁 B: 故事世界觀與大綱
        tab_world = QWidget()
        tw_layout = QVBoxLayout(tab_world)
        self.txt_gemma_worldview = QTextEdit()
        self.txt_gemma_worldview.setReadOnly(True)
        self.txt_gemma_worldview.setStyleSheet("font-size: 13px; line-height: 1.6;")
        tw_layout.addWidget(self.txt_gemma_worldview)
        self.gemma_tabs.addTab(tab_world, "📖 世界觀與大綱")

        # 分頁 C: 文本校驗與重排報告
        tab_report = QWidget()
        tr_layout = QVBoxLayout(tab_report)
        self.txt_gemma_report = QTextEdit()
        self.txt_gemma_report.setReadOnly(True)
        self.txt_gemma_report.setStyleSheet("font-family: monospace; font-size: 12px; line-height: 1.5; background: #0f172a; color: #38bdf8;")
        tr_layout.addWidget(self.txt_gemma_report)
        self.gemma_tabs.addTab(tab_report, "📊 文本校驗報告")

        # 分頁 D: 導讀序章 HTML 效果預覽
        tab_preview = QWidget()
        tp_layout = QVBoxLayout(tab_preview)
        self.browser_gemma_preview = QTextBrowser()
        self.browser_gemma_preview.setOpenExternalLinks(True)
        tp_layout.addWidget(self.browser_gemma_preview)
        self.gemma_tabs.addTab(tab_preview, "👁️ 導讀序章預覽 (HTML)")

        right_layout.addWidget(self.gemma_tabs)
        splitter.addWidget(right_widget)

        splitter.setSizes([380, 560])
        layout.addWidget(splitter)
        self.last_gemma_result = None

    def on_gemma_backend_changed(self):
        backend = self.combo_gemma_backend.currentData()
        if backend == "ollama":
            self.edit_gemma_url.setEnabled(True)
            self.edit_gemma_model.setText("google/embeddinggemma-2")
            self.lbl_gemma_status.setText("請點擊測試連線確認本機 Ollama 狀態")
            self.lbl_gemma_status.setStyleSheet("color: #f59e0b; font-size: 12px;")
        elif backend == "transformers":
            self.edit_gemma_url.setEnabled(False)
            self.edit_gemma_model.setText("google/embeddinggemma-2")
            self.lbl_gemma_status.setText("本機 HuggingFace / Transformers 模式")
            self.lbl_gemma_status.setStyleSheet("color: #3b82f6; font-size: 12px;")
        elif backend == "api":
            self.edit_gemma_url.setEnabled(True)
            self.edit_gemma_url.setPlaceholderText("http://localhost:8000/v1")
            self.lbl_gemma_status.setText("自訂 API 模式")
            self.lbl_gemma_status.setStyleSheet("color: #8b5cf6; font-size: 12px;")
        else:
            self.edit_gemma_url.setEnabled(False)
            self.lbl_gemma_status.setText("狀態: 內建語意引擎已就緒 (零相依、離線即開即用)")
            self.lbl_gemma_status.setStyleSheet("color: #10b981; font-size: 12px;")

    def test_gemma_connection(self):
        backend = self.combo_gemma_backend.currentData()
        url = self.edit_gemma_url.text().strip()
        model = self.edit_gemma_model.text().strip()
        client = GemmaEmbeddingClient(backend=backend, model_name=model, ollama_url=url)
        st = client.check_status()
        if st.get("ready"):
            self.lbl_gemma_status.setText(f"✓ {st.get('message')}")
            self.lbl_gemma_status.setStyleSheet("color: #10b981; font-weight: bold; font-size: 12px;")
            QMessageBox.information(self, "連線成功", f"{st.get('message')}")
        else:
            self.lbl_gemma_status.setText(f"✕ {st.get('message')}")
            self.lbl_gemma_status.setStyleSheet("color: #ef4444; font-size: 12px;")
            QMessageBox.warning(self, "連線提示", f"{st.get('message')}\n\n系統將自動回退至內建語意引擎繼續為您處理。")

    def run_gemma_analysis_selected(self):
        sel_indexes = self.table_tasks.selectedIndexes()
        task = None
        if sel_indexes:
            row = sel_indexes[0].row()
            if 0 <= row < len(self.tasks):
                task = self.tasks[row]
        elif self.tasks:
            task = self.tasks[0]

        if not task:
            QMessageBox.warning(self, "提示", "請先在「檔案與佇列」中選取或加入一本小說！")
            return

        filepath = task["filepath"]
        self.btn_run_gemma.setEnabled(False)
        self.progress_gemma.setValue(5)
        self.lbl_status.setText(f"正在對《{os.path.basename(filepath)}》執行 Gemma 2 深度語意分析與重排...")

        opts = {
            "backend": self.combo_gemma_backend.currentData(),
            "model_name": self.edit_gemma_model.text().strip(),
            "ollama_url": self.edit_gemma_url.text().strip(),
            "dedup": self.chk_gemma_dedup.isChecked(),
            "clean_noise": self.chk_gemma_noise.isChecked(),
            "rearrange": self.chk_gemma_rearrange.isChecked(),
            "auto_titles": self.chk_gemma_titles.isChecked(),
            "inject_character_guide": self.chk_gemma_inject.isChecked(),
            "max_characters": self.spin_gemma_chars.value()
        }

        self.gemma_worker = GemmaAnalysisWorker(filepath, opts)
        self.gemma_worker.progress_signal.connect(self.on_gemma_worker_progress)
        self.gemma_worker.finished_signal.connect(self.on_gemma_worker_finished)
        self.gemma_worker.error_signal.connect(self.on_gemma_worker_error)
        self.gemma_worker.start()

    def on_gemma_worker_progress(self, ratio: float, msg: str):
        self.progress_gemma.setValue(int(ratio * 100))
        self.progress_gemma.setFormat(f"%p% - {msg}")
        self.lbl_status.setText(f"Gemma 2: {msg}")

    def on_gemma_worker_finished(self, result: Dict[str, Any]):
        self.btn_run_gemma.setEnabled(True)
        self.btn_export_gemma.setEnabled(True)
        self.progress_gemma.setValue(100)
        self.progress_gemma.setFormat("100% - 分析重排完成！")
        self.last_gemma_result = result

        # 1. 填充登場角色表格
        chars = result.get("characters", [])
        self.table_gemma_chars.setRowCount(len(chars))
        for row, c in enumerate(chars):
            self.table_gemma_chars.setItem(row, 0, QTableWidgetItem(c.get("name", "")))
            self.table_gemma_chars.setItem(row, 1, QTableWidgetItem(c.get("role", "")))
            self.table_gemma_chars.setItem(row, 2, QTableWidgetItem(c.get("identity", "")))
            self.table_gemma_chars.setItem(row, 3, QTableWidgetItem(c.get("personality", "")))
            self.table_gemma_chars.setItem(row, 4, QTableWidgetItem(c.get("key_actions", "")))

        # 2. 填充世界觀
        wv = result.get("worldview", {})
        wv_text = (
            f"【故事背景與時代】：{wv.get('era', '未知')}\n"
            f"【作品題材標籤】：{'、'.join(wv.get('genres', []))}\n\n"
            f"【故事內容提要】：\n{wv.get('synopsis', '')}\n"
        )
        self.txt_gemma_worldview.setPlainText(wv_text)

        # 3. 填充校驗報告
        rep = result.get("report", {})
        rep_text = (
            f"=== Embedding Gemma 2 文本校驗與重排統計報告 ===\n"
            f"狀態：{rep.get('status')}\n"
            f"原始段落總數：{rep.get('original_sections')} 個\n"
            f"保留段落總數：{rep.get('remaining_sections')} 個\n"
            f"語意去重剔除：{rep.get('duplicates_removed')} 處\n"
            f"灌水雜訊清洗：{rep.get('noise_filtered')} 則\n"
            f"錯亂段落重排：{rep.get('rearranged_count')} 處\n"
            f"補全章節標題：{rep.get('generated_titles')} 篇\n\n"
            f"摘要說明：\n{rep.get('summary_text')}\n"
        )
        self.txt_gemma_report.setPlainText(rep_text)

        # 4. 填充導讀預覽
        guide_html = result.get("guide_html", "")
        self.browser_gemma_preview.setHtml(guide_html)

        self.lbl_status.setText("Gemma 2 分析完成！已為小說提煉登場人物與世界觀導讀。")
        QMessageBox.information(
            self,
            "分析重排完成",
            f"已成功完成小說語意校驗與人物萃取！\n\n"
            f"{rep.get('summary_text')}\n"
            f"共萃取出 {len(chars)} 位登場人物與世界觀導讀。"
        )

    def on_gemma_worker_error(self, err_msg: str):
        self.btn_run_gemma.setEnabled(True)
        self.progress_gemma.setValue(0)
        self.progress_gemma.setFormat("處理失敗")
        QMessageBox.critical(self, "錯誤", f"Gemma 2 處理失敗: {err_msg}")

    def export_gemma_result(self):
        if not self.last_gemma_result:
            return
        out_file = self.last_gemma_result.get("output_file", "")
        meta_file = self.last_gemma_result.get("metadata_file", "")
        QMessageBox.information(
            self,
            "匯出完成",
            f"最佳化檔案已生成：\n\n"
            f"小說本體：\n{out_file}\n\n"
            f"結構化中繼資料：\n{meta_file}"
        )

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
            self.lbl_cli_status.setText(f"<span style='color:#10b981; font-weight:bold;'>● kaf-cli:</span> {ver}")
            self.lbl_cli_status.setToolTip(f"執行檔路徑: {self.engine.cli_path}")
        else:
            self.lbl_cli_status.setText(f"<span style='color:#ef4444; font-weight:bold;'>● kaf-cli:</span> {ver}")
            self.lbl_cli_status.setToolTip("未找到有效的 kaf-cli 執行檔")

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

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isfile(p) and p.lower().endswith((".txt", ".pdf")):
                paths.append(p)
            elif os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        if f.lower().endswith((".txt", ".pdf")):
                            paths.append(os.path.join(root, f))
        if paths:
            self.add_files(paths)

    def add_txt_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "選取書籍檔案 (TXT / PDF)", os.getcwd(), "支援書籍檔案 (*.txt *.pdf);;純文字檔案 (*.txt);;PDF 文件 (*.pdf);;所有檔案 (*)"
        )
        if files:
            self.add_files(files)

    def add_directory_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "選取書籍所在資料夾", os.getcwd())
        if d:
            found = []
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".txt", ".pdf")):
                        found.append(os.path.join(root, f))
            if found:
                self.add_files(found)
            else:
                QMessageBox.information(self, "提示", "該資料夾內未發現 .txt 或 .pdf 書籍檔案。")

    def add_files(self, paths: List[str]):
        """
        立即載入檔案至任務佇列並即時刷新介面，隨後啟動背景線程分析章節規則，杜絕任何畫面凍結
        """
        existing = {t["filepath"] for t in self.tasks}
        new_paths = []
        for p in paths:
            if p in existing:
                continue
            new_paths.append(p)
            existing.add(p)

            # 極速提取預設書名，主執行緒零等待
            b_name = os.path.basename(p)
            raw_title, _ = os.path.splitext(b_name)
            self.tasks.append({
                "filepath": p,
                "bookname": raw_title,
                "author": "YSTYLE",
                "rule_name": "分析中...",
                "match_regex": "",
                "max_title_len": 35,
                "chapter_count": 0,
                "candidates": [],
                "status": "⏳ 掃描章節中..."
            })

        if not new_paths:
            return

        # 立即在表格中呈現所有剛拖入的檔案，使用者畫面完全不卡頓！
        self.refresh_task_table()
        self.lbl_status.setText(f"已加入 {len(new_paths)} 本書籍，正在背景智慧分析章節規則...")
        self.update_command_preview()

        # 啟動非同步背景掃描工作線程
        self.start_background_scan(new_paths)

    def start_background_scan(self, paths: List[str]):
        """在背景非同步執行書籍章節結構與規則偵測，保證拖入與操作時 GUI 絕不凍結"""
        if not paths:
            return

        self.scan_progress_frame.show()
        self.scan_progress_bar.setValue(0)
        self.lbl_scan_percent.setText("0%")
        self.lbl_scan_status.setText(f"🔍 正在準備分析 {len(paths)} 本書籍之章節結構與元資料...")

        if self.scan_worker is not None and self.scan_worker.isRunning():
            self.scan_worker.add_paths(paths)
        else:
            self.scan_worker = FileScanWorker(paths)
            self.scan_worker.file_progress_signal.connect(self.on_file_scan_progress)
            self.scan_worker.file_analyzed_signal.connect(self.on_file_analyzed)
            self.scan_worker.all_finished_signal.connect(self.on_all_files_analyzed)
            self.scan_worker.start()

    def on_file_scan_progress(self, curr: int, total: int, filename: str, pct: float):
        self.scan_progress_frame.show()
        self.scan_progress_bar.setValue(int(pct))
        self.lbl_scan_percent.setText(f"{int(pct)}%")
        trunc_name = filename if len(filename) <= 28 else filename[:25] + "..."
        self.lbl_scan_status.setText(f"🔍 正在智慧分析結構 ({curr}/{total}): {trunc_name}")
        self.lbl_status.setText(f"正在背景分析書籍章節結構 ({curr}/{total}): {trunc_name} ({int(pct)}%)")

    def on_file_analyzed(self, filepath: str, data: Dict[str, Any]):
        found_row = -1
        target_task = None
        for r, t in enumerate(self.tasks):
            if t["filepath"] == filepath:
                found_row = r
                target_task = t
                break

        if not target_task:
            return

        meta = data.get("meta", {})
        det = data.get("det", {})

        if meta.get("title"):
            target_task["bookname"] = meta["title"]
        if meta.get("author"):
            target_task["author"] = meta["author"]

        target_task["rule_name"] = det.get("rule_name", "自動智慧識別 (預設)")
        target_task["match_regex"] = det.get("regex", "")
        target_task["exclude_regex"] = det.get("exclude_regex", "")
        target_task["max_title_len"] = det.get("max_len", 35)
        target_task["chapter_count"] = det.get("chapter_count", 0)
        target_task["candidates"] = det.get("candidates", [])
        target_task["status"] = "等待中"

        # 即時更新對應 row 的視圖項目
        if 0 <= found_row < self.table_tasks.rowCount():
            it_title = self.table_tasks.item(found_row, 2)
            if it_title:
                it_title.setText(target_task["bookname"])

            it_author = self.table_tasks.item(found_row, 3)
            if it_author:
                it_author.setText(target_task["author"])

            combo = self.table_tasks.cellWidget(found_row, 4)
            if isinstance(combo, QComboBox):
                combo.blockSignals(True)
                found_idx = -1
                for c_idx in range(combo.count()):
                    if combo.itemText(c_idx) == target_task["rule_name"] or (target_task["match_regex"] and combo.itemData(c_idx) == target_task["match_regex"]):
                        found_idx = c_idx
                        break
                if found_idx == -1 and target_task["match_regex"]:
                    combo.insertItem(1, f"📑 {target_task['rule_name']}", target_task["match_regex"])
                    found_idx = 1
                combo.setCurrentIndex(max(0, found_idx))
                combo.blockSignals(False)

            cnt = target_task["chapter_count"]
            it_cnt = self.table_tasks.item(found_row, 5)
            if it_cnt:
                if "大綱" in target_task.get("rule_name", ""):
                    it_cnt.setText(f"📑 大綱 {cnt} 章")
                elif cnt > 0:
                    it_cnt.setText(f"{cnt} 章")
                else:
                    it_cnt.setText("—")
                if cnt > 0:
                    it_cnt.setForeground(QColor("#38bdf8"))

            it_status = self.table_tasks.item(found_row, 7)
            if it_status:
                it_status.setText("等待中")
                it_status.setForeground(QColor("#94a3b8"))

        self.update_command_preview()

    def on_all_files_analyzed(self, total: int):
        self.lbl_scan_status.setText(f"✨ 已完成全數 {total} 本書籍之章節結構分析與最佳規則匹配！")
        self.scan_progress_bar.setValue(100)
        self.lbl_scan_percent.setText("100%")
        self.lbl_status.setText(f"已就緒：共 {len(self.tasks)} 本書籍已就緒，隨時可開始轉換。")
        QTimer.singleShot(2500, self.scan_progress_frame.hide)

    def refresh_task_table(self):
        self.table_tasks.blockSignals(True)
        self.table_tasks.setRowCount(len(self.tasks))
        fmt = self.combo_format.currentData() or "all"

        for row, t in enumerate(self.tasks):
            # Col 0: #
            it_idx = QTableWidgetItem(str(row + 1))
            it_idx.setTextAlignment(Qt.AlignCenter)
            self.table_tasks.setItem(row, 0, it_idx)

            # Col 1: 檔案名稱 (標註 [PDF] / [TXT])
            is_pdf = t["filepath"].lower().endswith(".pdf")
            badge = "[PDF] " if is_pdf else "[TXT] "
            it_name = QTableWidgetItem(f"{badge}{os.path.basename(t['filepath'])}")
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
            st_text = t.get("status", "等待中")
            it_status = QTableWidgetItem(st_text)
            it_status.setTextAlignment(Qt.AlignCenter)
            if "完成" in st_text:
                it_status.setForeground(QColor("#10b981"))
            elif "失敗" in st_text or "錯誤" in st_text:
                it_status.setForeground(QColor("#ef4444"))
            elif "處理" in st_text or "步驟" in st_text or "[" in st_text:
                it_status.setForeground(QColor("#38bdf8"))
            self.table_tasks.setItem(row, 7, it_status)

            # Col 8: 操作按鈕 (若已完成，提供「📂 開啟」；未完成時提供「🔍 預覽」)
            if "完成" in st_text:
                btn_act = QPushButton("📂 開啟")
                btn_act.setStyleSheet("padding: 3px 8px; font-size: 11px; background-color: #059669; color: white; font-weight: bold; border-radius: 4px;")
                btn_act.clicked.connect(lambda _, task_ref=t: self.open_single_task_output(task_ref))
                self.table_tasks.setCellWidget(row, 8, btn_act)
            else:
                btn_act = QPushButton("🔍 預覽")
                btn_act.setStyleSheet("padding: 3px 8px; font-size: 11px;")
                btn_act.clicked.connect(lambda _, task_ref=t: self.preview_single_task(task_ref))
                self.table_tasks.setCellWidget(row, 8, btn_act)

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
        """一鍵為佇列中所有書籍背景非同步重新推斷最佳規則，保證介面流暢"""
        if not self.tasks:
            QMessageBox.information(self, "提示", "目前佇列中尚無書籍檔案！")
            return

        for r, t in enumerate(self.tasks):
            t["status"] = "⏳ 重新分析中..."
            it_status = self.table_tasks.item(r, 7)
            if it_status:
                it_status.setText("⏳ 重新分析中...")
                it_status.setForeground(QColor("#38bdf8"))

        all_paths = [t["filepath"] for t in self.tasks]
        self.start_background_scan(all_paths)

    def preview_single_task(self, task_ref: Dict[str, Any]):
        """針對單一小說與其專屬規則進行目錄預覽"""
        filepath = task_ref["filepath"]
        if not os.path.exists(filepath):
            QMessageBox.warning(self, "錯誤", "該小說檔案不存在！")
            return

        exclude_pat = self.edit_exclude.text().strip()
        if (not exclude_pat or exclude_pat == DEFAULT_EXCLUDE_REGEX) and task_ref and task_ref.get("exclude_regex"):
            exclude_pat = task_ref["exclude_regex"]

        max_len_val = task_ref.get("max_title_len", 35)
        if hasattr(self, "spin_max_len") and self.spin_max_len.value() > max_len_val:
            max_len_val = self.spin_max_len.value()

        res = test_chapter_match(
            filepath=filepath,
            match_regex=task_ref.get("match_regex", ""),
            volume_regex="false",
            exclude_regex=exclude_pat,
            max_len=max_len_val,
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
        if hasattr(self, "scan_worker") and self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.cancel()
        if hasattr(self, "scan_progress_frame"):
            self.scan_progress_frame.hide()
        self.tasks.clear()
        self.refresh_task_table()
        self.lbl_status.setText("就緒：請新增書籍檔案。")
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
            self.refresh_orly_cover_preview()

    def refresh_orly_cover_preview(self):
        """根據當前選取之書籍標題、作者與自訂色彩即時生成 Orly 封面預覽"""
        try:
            import io
            from .cover_generator import generate_orly_cover

            book_title = "方案：人體操作手冊"
            author = "Andrew D. Huberman；Jessica Wapner (原著)"

            selected_idx = self.table_tasks.currentRow()
            if 0 <= selected_idx < len(self.tasks):
                t = self.tasks[selected_idx]
                book_title = t.get("bookname") or (t.get("filepath") and Path(t["filepath"]).stem) or book_title
                if t.get("author"):
                    author = t["author"]
            elif self.tasks:
                t = self.tasks[0]
                book_title = t.get("bookname") or (t.get("filepath") and Path(t["filepath"]).stem) or book_title
                if t.get("author"):
                    author = t["author"]

            color_str = self.edit_orly_color.text().strip()
            animal_i = self.spin_orly_idx.value()

            pil_img = generate_orly_cover(
                book_title=book_title,
                author=author,
                color=color_str,
                animal_idx=animal_i
            )

            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            buf.seek(0)
            pix = QPixmap()
            if pix.loadFromData(buf.getvalue()):
                scaled = pix.scaled(200, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.lbl_cover_preview.setPixmap(scaled)
        except Exception as e:
            self.lbl_cover_preview.clear()
            self.lbl_cover_preview.setText(f"Orly 預覽生成失敗:\n{e}")

    def on_cover_mode_changed(self):
        if self.radio_cover_custom.isChecked():
            self.update_cover_preview(self.edit_cover_path.text())
        elif self.radio_cover_orly.isChecked():
            self.refresh_orly_cover_preview()
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
        target_task = None
        if sel_indexes:
            row = sel_indexes[0].row()
            if 0 <= row < len(self.tasks):
                target_task = self.tasks[row]
                target_path = target_task["filepath"]
        elif self.tasks:
            target_task = self.tasks[0]
            target_path = target_task["filepath"]

        if not target_path or not os.path.exists(target_path):
            QMessageBox.warning(self, "提示", "請先加入小說檔案並在佇列中選取一項以進行章節測試！")
            return

        match_pat = self.edit_match.text().strip()
        if not match_pat and target_task and target_task.get("match_regex"):
            match_pat = target_task["match_regex"]

        exclude_pat = self.edit_exclude.text().strip()
        if (not exclude_pat or exclude_pat == DEFAULT_EXCLUDE_REGEX) and target_task and target_task.get("exclude_regex"):
            exclude_pat = target_task["exclude_regex"]

        max_len_val = self.spin_max_len.value()
        if target_task and target_task.get("max_title_len") and target_task["max_title_len"] > max_len_val:
            max_len_val = target_task["max_title_len"]

        res = test_chapter_match(
            filepath=target_path,
            match_regex=match_pat,
            volume_regex=self.edit_volume.text().strip() if self.chk_volume.isChecked() else "false",
            exclude_regex=exclude_pat,
            max_len=max_len_val,
            scan_lines=15000
        )

        if "error" in res:
            QMessageBox.critical(self, "測試出錯", res["error"])
        else:
            dlg = ChapterPreviewDialog(res, target_path, self)
            dlg.exec_()

    def run_unwrap_test(self):
        """針對選取之小說測試短行硬換行修復效果並彈窗預覽"""
        sel_indexes = self.table_tasks.selectedIndexes()
        target_path = ""
        if sel_indexes:
            row = sel_indexes[0].row()
            if 0 <= row < len(self.tasks):
                target_path = self.tasks[row]["filepath"]
        elif self.tasks:
            target_path = self.tasks[0]["filepath"]

        if not target_path or not os.path.exists(target_path):
            QMessageBox.warning(self, "提示", "請先加入小說檔案並在佇列中選取一項以進行硬換行修復測試！")
            return

        from .zh_converter import detect_encoding
        from .text_cleaner import remove_hard_breaks
        enc = detect_encoding(target_path)
        with open(target_path, "r", encoding=enc, errors="ignore") as f:
            lines = [f.readline() for _ in range(300)]
        sample_text = "".join(lines)
        orig_lines = len(sample_text.splitlines())
        cleaned = remove_hard_breaks(sample_text, header_regex_str=self.edit_match.text().strip())
        paras = [p.strip() for p in cleaned.split("\n\n") if p.strip()]

        items = [{"line_no": idx + 1, "type": "自然段落", "title": p[:140] + ("..." if len(p) > 140 else "")} for idx, p in enumerate(paras[:30])]
        res = {
            "encoding": enc,
            "total_lines_scanned": orig_lines,
            "chapters_found": len(paras),
            "volumes_found": 0,
            "excluded_count": orig_lines - len(paras),
            "preview_items": items,
            "stats_summary": f"硬換行修復預覽（前 300 行）：原 {orig_lines} 行已合併還原為 {len(paras)} 個完整自然段落。"
        }
        dlg = ChapterPreviewDialog(res, target_path, self)
        dlg.setWindowTitle(f"短行硬換行修復效果預覽 (段落對比) - {os.path.basename(target_path)}")
        dlg.exec_()

    def collect_options(self) -> Dict[str, Any]:
        """從介面收集當前所有參數選項"""
        cover_mode = "auto"
        if self.radio_cover_custom.isChecked():
            cover_mode = "custom"
        elif self.radio_cover_orly.isChecked():
            cover_mode = "orly"

        opts = {
            "book_type": self.combo_book_type.currentData() if hasattr(self, "combo_book_type") else "auto",
            "pdf_mode": self.combo_pdf_mode.currentData() if hasattr(self, "combo_pdf_mode") else "auto",
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
            "custom_css_content": self.edit_css_content.toPlainText().strip(),
            "remove_hard_breaks": self.chk_remove_hard_breaks.isChecked() if hasattr(self, "chk_remove_hard_breaks") else True,
            "use_gemma_pipeline": self.chk_enable_gemma_pipeline.isChecked() if hasattr(self, "chk_enable_gemma_pipeline") else False,
            "enable_math": self.chk_enable_math.isChecked() if hasattr(self, "chk_enable_math") else True,
            "gemma_backend": self.combo_gemma_backend.currentData() if hasattr(self, "combo_gemma_backend") else "fast_local",
            "gemma_model": self.edit_gemma_model.text().strip() if hasattr(self, "edit_gemma_model") else "google/embeddinggemma-2",
            "gemma_ollama_url": self.edit_gemma_url.text().strip() if hasattr(self, "edit_gemma_url") else "http://localhost:11434",
            "gemma_dedup": self.chk_gemma_dedup.isChecked() if hasattr(self, "chk_gemma_dedup") else True,
            "gemma_clean_noise": self.chk_gemma_noise.isChecked() if hasattr(self, "chk_gemma_noise") else True,
            "gemma_rearrange": self.chk_gemma_rearrange.isChecked() if hasattr(self, "chk_gemma_rearrange") else True,
            "gemma_auto_titles": self.chk_gemma_titles.isChecked() if hasattr(self, "chk_gemma_titles") else True,
            "gemma_inject_guide": self.chk_gemma_inject.isChecked() if hasattr(self, "chk_gemma_inject") else True,
            "gemma_max_characters": self.spin_gemma_chars.value() if hasattr(self, "spin_gemma_chars") else 10
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

        if sample_path.lower().endswith(".pdf") and (
            opts.get("pdf_mode") == "direct_epub" or
            (opts.get("pdf_mode") == "auto" and opts.get("book_type") in ["technical", "general"])
        ):
            stem = Path(sample_path).stem
            cmd_str = f"pdftohtml -s -noframes \"{sample_path}\" && pandoc -o \"{stem}.epub\" --toc (直轉高保真 EPUB 模式)"
        else:
            cmd_args = self.engine.build_command_args(sample_path, opts)
            cmd_str = " ".join([f'"{c}"' if " " in c else c for c in cmd_args])
        self.edit_cmd_preview.setText(cmd_str)
        if hasattr(self, "radio_cover_orly") and self.radio_cover_orly.isChecked():
            self.refresh_orly_cover_preview()

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
        self.tabs.setCurrentIndex(6)
        self.append_log("\n════════════════════════════════════════════════════")
        self.append_log(f"🚀 開始批次轉換任務，共 {len(self.tasks)} 個檔案...")

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.prog_bar.setValue(0)
        self.lbl_status.setText("正在轉換中...")
        self.stepper.reset()
        self.stepper.set_active_step(1, "準備執行轉換流程...")

        opts = self.collect_options()

        self.worker = ConversionWorker(self.engine, self.tasks, opts)
        self.worker.log_signal.connect(self.append_log)
        self.worker.file_progress_signal.connect(self.on_worker_file_progress)
        self.worker.file_finished_signal.connect(self.on_worker_file_finished)
        self.worker.all_finished_signal.connect(self.on_worker_all_finished)
        self.worker.start()

    def on_worker_file_progress(self, idx: int, ratio: float, status_text: str):
        # 辨識當前所處步驟 1~4
        stage = 0
        if "1/4" in status_text or "短行" in status_text:
            stage = 1
        elif "2/4" in status_text or "Gemma" in status_text:
            stage = 2
        elif "3/4" in status_text or "匹配章節" in status_text:
            stage = 3
        elif "4/4" in status_text or "編譯" in status_text or "正體" in status_text:
            stage = 4

        if stage > 0:
            self.stepper.set_active_step(stage, status_text)

        if 0 <= idx < len(self.tasks):
            stage_badge = f"[{stage}/4 處理中]" if stage > 0 else "處理中..."
            self.tasks[idx]["status"] = stage_badge
            item_status = self.table_tasks.item(idx, 7)
            if item_status:
                item_status.setText(stage_badge)
                item_status.setForeground(QColor("#38bdf8"))
        
        total_tasks = len(self.tasks)
        overall_pct = int(((idx + ratio) / total_tasks) * 100)
        self.prog_bar.setValue(min(100, max(0, overall_pct)))
        self.lbl_progress_percent.setText(f"{self.prog_bar.value()}%")
        self.lbl_status.setText(status_text)

    def on_worker_file_finished(self, idx: int, success: bool, msg: str):
        if 0 <= idx < len(self.tasks):
            self.tasks[idx]["status"] = "✓ 完成" if success else "✕ 失敗"
            self.refresh_task_table()

    def on_worker_all_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.prog_bar.setValue(100)
        self.lbl_progress_percent.setText("100%")
        self.lbl_status.setText("全部轉換任務完成！")
        self.stepper.set_all_completed()
        self.append_log("════════════════════════════════════════════════════")
        self.append_log("✨ 全部轉換作業已結束！")

        # 自動開啟資料夾
        if self.chk_auto_open.isChecked() and self.tasks:
            target_dir = self.edit_output_dir.text().strip()
            if not target_dir or not os.path.isdir(target_dir):
                target_dir = os.path.dirname(os.path.abspath(self.tasks[0]["filepath"]))
            self.open_folder(target_dir)

        QMessageBox.information(
            self, "轉換完成",
            f"恭喜！佇列中 {len(self.tasks)} 本小說已全部轉換完成！\n\n"
            "您可在表格點擊「📂 開啟」直接閱讀生成的電子書。"
        )

    def open_single_task_output(self, task_ref: Dict[str, Any]):
        """直接開啟轉換完成的小說電子書檔案或其目錄"""
        out_files = task_ref.get("output_files", [])
        if out_files and os.path.exists(out_files[0]):
            self.open_file_or_folder(out_files[0])
            return

        # 降級尋找：同目錄下符合名稱的 epub/azw3/mobi
        base_dir = self.edit_output_dir.text().strip()
        if not base_dir or not os.path.isdir(base_dir):
            base_dir = os.path.dirname(os.path.abspath(task_ref["filepath"]))
        
        name = task_ref.get("bookname") or os.path.splitext(os.path.basename(task_ref["filepath"]))[0]
        for ext in [".epub", ".azw3", ".mobi"]:
            cand = os.path.join(base_dir, name + ext)
            if os.path.exists(cand):
                self.open_file_or_folder(cand)
                return
        
        # 若無具體檔案則直接開啟輸出目錄
        self.open_folder(base_dir)

    def open_file_or_folder(self, target_path: str):
        try:
            if sys.platform.startswith("win"):
                os.startfile(target_path)
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", target_path])
            else:
                subprocess.Popen(["xdg-open", target_path])
        except Exception as e:
            QMessageBox.information(self, "開啟檔案", f"路徑：{target_path}\n({str(e)})")

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
            self._is_loading_settings = True
            try:
                if "book_type" in p and hasattr(self, "combo_book_type"):
                    idx = self.combo_book_type.findData(p["book_type"])
                    if idx >= 0: self.combo_book_type.setCurrentIndex(idx)
                if "pdf_mode" in p and hasattr(self, "combo_pdf_mode"):
                    idx = self.combo_pdf_mode.findData(p["pdf_mode"])
                    if idx >= 0: self.combo_pdf_mode.setCurrentIndex(idx)
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
            finally:
                self._is_loading_settings = False
            self.save_ui_to_settings()

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

    def schedule_save_settings(self):
        """排程延遲儲存設定，避免頻繁寫入硬碟"""
        if getattr(self, "_is_loading_settings", False):
            return
        if hasattr(self, "_save_timer"):
            self._save_timer.start()

    def _do_save_settings(self):
        self.save_ui_to_settings()

    def bind_settings_auto_save(self):
        """綁定所有控制項變更事件，於使用者操作時即時排程儲存設定"""
        # 下拉選單
        for cb in [
            getattr(self, "combo_book_type", None),
            getattr(self, "combo_pdf_mode", None),
            getattr(self, "combo_format", None),
            getattr(self, "combo_zh", None),
            getattr(self, "combo_align", None),
            getattr(self, "combo_css_preset", None),
            getattr(self, "combo_gemma_backend", None),
        ]:
            if cb:
                cb.currentIndexChanged.connect(lambda _: self.schedule_save_settings())

        if hasattr(self, "combo_lang"):
            self.combo_lang.currentTextChanged.connect(lambda _: self.schedule_save_settings())

        # 數值微調 (SpinBox)
        for sb in [
            getattr(self, "spin_indent", None),
            getattr(self, "spin_max_len", None),
            getattr(self, "spin_orly_idx", None),
            getattr(self, "spin_gemma_chars", None),
        ]:
            if sb:
                sb.valueChanged.connect(lambda _: self.schedule_save_settings())

        # 核取方塊 (CheckBox)
        for chk in [
            getattr(self, "chk_sep_chap", None),
            getattr(self, "chk_tips", None),
            getattr(self, "chk_volume", None),
            getattr(self, "chk_auto_open", None),
            getattr(self, "chk_remove_hard_breaks", None),
            getattr(self, "chk_enable_gemma_pipeline", None),
            getattr(self, "chk_enable_math", None),
            getattr(self, "chk_gemma_dedup", None),
            getattr(self, "chk_gemma_noise", None),
            getattr(self, "chk_gemma_rearrange", None),
            getattr(self, "chk_gemma_titles", None),
            getattr(self, "chk_gemma_inject", None),
        ]:
            if chk:
                chk.toggled.connect(lambda _: self.schedule_save_settings())

        # 單選按鈕 (RadioButton)
        for rb in [
            getattr(self, "radio_cover_auto", None),
            getattr(self, "radio_cover_custom", None),
            getattr(self, "radio_cover_orly", None),
        ]:
            if rb:
                rb.toggled.connect(lambda _: self.schedule_save_settings())

        # 輸入框 (QLineEdit & QTextEdit)
        for edit in [
            getattr(self, "edit_output_dir", None),
            getattr(self, "edit_bottom", None),
            getattr(self, "edit_line_height", None),
            getattr(self, "edit_font", None),
            getattr(self, "edit_match", None),
            getattr(self, "edit_volume", None),
            getattr(self, "edit_exclude", None),
            getattr(self, "edit_unknow_title", None),
            getattr(self, "edit_cover_path", None),
            getattr(self, "edit_orly_color", None),
            getattr(self, "edit_gemma_url", None),
            getattr(self, "edit_gemma_model", None),
            getattr(self, "edit_css_content", None),
        ]:
            if edit:
                if hasattr(edit, "textChanged"):
                    edit.textChanged.connect(self.schedule_save_settings)

    def save_ui_to_settings(self):
        if getattr(self, "_is_loading_settings", False):
            return

        if hasattr(self, "_save_timer") and self._save_timer.isActive():
            self._save_timer.stop()

        opts = self.collect_options()
        self.cfg_mgr.set("book_type", opts.get("book_type", "auto"))
        self.cfg_mgr.set("pdf_mode", opts.get("pdf_mode", "auto"))
        self.cfg_mgr.set("format", opts.get("format", "all"))
        self.cfg_mgr.set("zh_conversion", opts.get("zh_conversion", "s2tw"))
        self.cfg_mgr.set("output_dir", opts.get("output_dir", ""))
        self.cfg_mgr.set("remove_hard_breaks", opts.get("remove_hard_breaks", True))
        self.cfg_mgr.set("use_gemma_pipeline", opts.get("use_gemma_pipeline", True))
        self.cfg_mgr.set("enable_math", opts.get("enable_math", True))
        self.cfg_mgr.set("align", opts.get("align", "center"))
        self.cfg_mgr.set("lang", opts.get("lang", "zh-TW"))
        self.cfg_mgr.set("indent", opts.get("indent", 2))
        self.cfg_mgr.set("bottom", opts.get("bottom", "1em"))
        self.cfg_mgr.set("line_height", opts.get("line_height", "1.85"))
        self.cfg_mgr.set("separate_chapter_number", opts.get("separate_chapter_number", True))
        self.cfg_mgr.set("tips", opts.get("tips", False))
        self.cfg_mgr.set("font_path", opts.get("font_path", ""))
        self.cfg_mgr.set("match_regex", opts.get("match_regex", ""))
        self.cfg_mgr.set("enable_volume", opts.get("enable_volume", True))
        self.cfg_mgr.set("volume_regex", opts.get("volume_regex", DEFAULT_VOLUME_REGEX))
        self.cfg_mgr.set("exclude_regex", opts.get("exclude_regex", DEFAULT_EXCLUDE_REGEX))
        self.cfg_mgr.set("max_title_len", opts.get("max_title_len", 35))
        self.cfg_mgr.set("unknow_title", opts.get("unknow_title", "章節正文"))
        self.cfg_mgr.set("cover_mode", opts.get("cover_mode", "auto"))
        self.cfg_mgr.set("custom_cover_path", opts.get("custom_cover_path", ""))
        self.cfg_mgr.set("orly_color", opts.get("orly_color", ""))
        self.cfg_mgr.set("orly_idx", opts.get("orly_idx", -1))
        self.cfg_mgr.set("css_preset", self.combo_css_preset.currentText())
        self.cfg_mgr.set("custom_css_content", opts.get("custom_css_content", ""))
        self.cfg_mgr.set("auto_open_folder", self.chk_auto_open.isChecked())

        # Gemma 2 參數儲存
        self.cfg_mgr.set("gemma_backend", opts.get("gemma_backend", "fast_local"))
        self.cfg_mgr.set("gemma_model", opts.get("gemma_model", "google/embeddinggemma-2"))
        self.cfg_mgr.set("gemma_ollama_url", opts.get("gemma_ollama_url", "http://localhost:11434"))
        self.cfg_mgr.set("gemma_dedup", opts.get("gemma_dedup", True))
        self.cfg_mgr.set("gemma_clean_noise", opts.get("gemma_clean_noise", True))
        self.cfg_mgr.set("gemma_rearrange", opts.get("gemma_rearrange", True))
        self.cfg_mgr.set("gemma_auto_titles", opts.get("gemma_auto_titles", True))
        self.cfg_mgr.set("gemma_inject_guide", opts.get("gemma_inject_guide", True))
        self.cfg_mgr.set("gemma_max_characters", opts.get("gemma_max_characters", 10))

        # 視窗狀態與大小記錄
        if not self.isMaximized():
            w = self.width()
            h = self.height()
            if w >= 640 and h >= 440:
                self.cfg_mgr.set("window_width", w)
                self.cfg_mgr.set("window_height", h)
        self.cfg_mgr.set("window_maximized", self.isMaximized())

        self.cfg_mgr.save()

    def load_settings_to_ui(self):
        self._is_loading_settings = True
        try:
            c = self.cfg_mgr.config
            if hasattr(self, "combo_book_type"):
                b_idx = self.combo_book_type.findData(c.get("book_type", "auto"))
                if b_idx >= 0: self.combo_book_type.setCurrentIndex(b_idx)

            if hasattr(self, "combo_pdf_mode"):
                p_idx = self.combo_pdf_mode.findData(c.get("pdf_mode", "auto"))
                if p_idx >= 0: self.combo_pdf_mode.setCurrentIndex(p_idx)

            idx = self.combo_format.findData(c.get("format", "all"))
            if idx >= 0: self.combo_format.setCurrentIndex(idx)

            idx_zh = self.combo_zh.findData(c.get("zh_conversion", "s2tw"))
            if idx_zh >= 0: self.combo_zh.setCurrentIndex(idx_zh)

            self.edit_output_dir.setText(c.get("output_dir", ""))

            if hasattr(self, "chk_remove_hard_breaks"):
                self.chk_remove_hard_breaks.setChecked(c.get("remove_hard_breaks", True))

            if hasattr(self, "chk_enable_gemma_pipeline"):
                self.chk_enable_gemma_pipeline.setChecked(c.get("use_gemma_pipeline", True))

            if hasattr(self, "chk_enable_math"):
                self.chk_enable_math.setChecked(c.get("enable_math", True))

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
            custom_css = c.get("custom_css_content", "")
            if custom_css:
                self.edit_css_content.setPlainText(custom_css)
            elif css_p in CSS_PRESETS:
                self.edit_css_content.setPlainText(CSS_PRESETS[css_p]["css"])

            self.chk_auto_open.setChecked(c.get("auto_open_folder", True))

            # Gemma 2 參數載入
            if hasattr(self, "combo_gemma_backend"):
                gb_idx = self.combo_gemma_backend.findData(c.get("gemma_backend", "fast_local"))
                if gb_idx >= 0: self.combo_gemma_backend.setCurrentIndex(gb_idx)
            if hasattr(self, "edit_gemma_url"):
                self.edit_gemma_url.setText(c.get("gemma_ollama_url", "http://localhost:11434"))
            if hasattr(self, "edit_gemma_model"):
                self.edit_gemma_model.setText(c.get("gemma_model", "google/embeddinggemma-2"))
            if hasattr(self, "chk_gemma_dedup"):
                self.chk_gemma_dedup.setChecked(c.get("gemma_dedup", True))
            if hasattr(self, "chk_gemma_noise"):
                self.chk_gemma_noise.setChecked(c.get("gemma_clean_noise", True))
            if hasattr(self, "chk_gemma_rearrange"):
                self.chk_gemma_rearrange.setChecked(c.get("gemma_rearrange", True))
            if hasattr(self, "chk_gemma_titles"):
                self.chk_gemma_titles.setChecked(c.get("gemma_auto_titles", True))
            if hasattr(self, "chk_gemma_inject"):
                self.chk_gemma_inject.setChecked(c.get("gemma_inject_guide", True))
            if hasattr(self, "spin_gemma_chars"):
                self.spin_gemma_chars.setValue(c.get("gemma_max_characters", 10))

            self.update_command_preview()
        finally:
            self._is_loading_settings = False


def suppress_qt_wayland_warnings(mode, context, message):
    """
    過濾 Linux Wayland 與 Python 執行緒常見的非致命 Qt 底層警告：
    1. Wayland does not support QWindow::requestActivate()
    2. QSocketNotifier: Can only be used with threads started with QThread
    3. QStandardPaths: error creating runtime directory
    """
    msg = str(message)
    msg_lower = msg.lower()
    if "requestactivate" in msg_lower or ("wayland" in msg_lower and "activate" in msg_lower):
        return
    if "qsocketnotifier" in msg_lower:
        return
    if "error creating runtime directory" in msg_lower:
        return
    sys.stderr.write(f"{msg}\n")


def run_desktop_app():
    # 預設抑制 Wayland QPA 除錯警告
    if "QT_LOGGING_RULES" not in os.environ:
        os.environ["QT_LOGGING_RULES"] = "qt.qpa.wayland=false;qt.qpa.plugin=false"

    try:
        qInstallMessageHandler(suppress_qt_wayland_warnings)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("kaf-cli GUI (繁體中文專業版)")
    win = KafMainWindow()
    if win.cfg_mgr.get("window_maximized", False):
        win.showMaximized()
    else:
        win.show()
    sys.exit(app.exec_())
