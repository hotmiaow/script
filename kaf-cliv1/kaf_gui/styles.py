# -*- coding: utf-8 -*-
"""
現代化深色與淺色 QSS 樣式主題
"""

DARK_THEME = """
QWidget {
    background-color: #1e1e24;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", "Noto Sans TC", sans-serif;
    font-size: 13px;
}

/* 標題與分組框 */
QGroupBox {
    border: 1px solid #333842;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 16px;
    font-weight: bold;
    color: #4daafc;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background-color: #1e1e24;
}

/* 分頁控制項 */
QTabWidget::pane {
    border: 1px solid #2d3139;
    border-radius: 8px;
    background: #23272e;
    top: -1px;
}

QTabBar::tab {
    background: #1a1c22;
    color: #9da5b4;
    border: 1px solid #282c34;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 9px 18px;
    margin-right: 3px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background: #23272e;
    color: #ffffff;
    border-bottom: 2px solid #3b82f6;
    font-weight: bold;
}

QTabBar::tab:hover:!selected {
    background: #282c34;
    color: #d7dae0;
}

/* 輸入框、下拉選單、數字輸入框 */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {
    background-color: #1a1c22;
    border: 1px solid #3b4048;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f0f0f0;
    selection-background-color: #2563eb;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #3b82f6;
    background-color: #20242c;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #3b4048;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}

QComboBox QAbstractItemView {
    background-color: #1e222a;
    border: 1px solid #3b4048;
    selection-background-color: #2563eb;
    color: #f0f0f0;
    padding: 4px;
}

/* 按鈕樣式 */
QPushButton {
    background-color: #2c313a;
    color: #e0e6ed;
    border: 1px solid #3e4451;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #353b45;
    border-color: #4b5263;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #21252b;
}

QPushButton:disabled {
    background-color: #181a1f;
    border-color: #282c34;
    color: #5c6370;
}

/* 主要操作大按鈕 */
QPushButton#btn_primary {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #1d4ed8;
    font-weight: bold;
    font-size: 14px;
    padding: 10px 24px;
    border-radius: 8px;
}

QPushButton#btn_primary:hover {
    background-color: #3b82f6;
    border-color: #2563eb;
}

QPushButton#btn_primary:pressed {
    background-color: #1d4ed8;
}

/* 危險/取消按鈕 */
QPushButton#btn_danger {
    background-color: #991b1b;
    color: #ffffff;
    border: 1px solid #7f1d1d;
    font-weight: bold;
    padding: 9px 18px;
    border-radius: 8px;
}

QPushButton#btn_danger:hover {
    background-color: #b91c1c;
}

/* 表格樣式 */
QTableWidget {
    background-color: #1a1c22;
    alternate-background-color: #21242b;
    border: 1px solid #2d3139;
    border-radius: 6px;
    gridline-color: #2d3139;
    color: #e0e0e0;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background-color: #1e3a5f;
    color: #ffffff;
}

QHeaderView::section {
    background-color: #242830;
    color: #abb2bf;
    padding: 6px 10px;
    border: none;
    border-right: 1px solid #2d3139;
    border-bottom: 1px solid #2d3139;
    font-weight: bold;
}

/* 進度條 */
QProgressBar {
    background-color: #1a1c22;
    border: 1px solid #333842;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
    height: 18px;
}

QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 5px;
}

/* 核取方塊與單選紐 */
QCheckBox, QRadioButton {
    spacing: 8px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
}

/* 滾動條 */
QScrollBar:vertical {
    background: #1a1c22;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #3b4048;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #4b5263;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""

LIGHT_THEME = """
QWidget {
    background-color: #f8fafc;
    color: #1e293b;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", "Noto Sans TC", sans-serif;
    font-size: 13px;
}

QGroupBox {
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 16px;
    font-weight: bold;
    color: #0284c7;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background-color: #f8fafc;
}

QTabWidget::pane {
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    background: #ffffff;
    top: -1px;
}

QTabBar::tab {
    background: #f1f5f9;
    color: #64748b;
    border: 1px solid #cbd5e1;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 9px 18px;
    margin-right: 3px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background: #ffffff;
    color: #0f172a;
    border-bottom: 2px solid #2563eb;
    font-weight: bold;
}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 10px;
    color: #0f172a;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #2563eb;
    background-color: #f8fafc;
}

QPushButton {
    background-color: #ffffff;
    color: #334155;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #f1f5f9;
    border-color: #94a3b8;
    color: #0f172a;
}

QPushButton#btn_primary {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #1d4ed8;
    font-weight: bold;
    font-size: 14px;
    padding: 10px 24px;
    border-radius: 8px;
}

QPushButton#btn_primary:hover {
    background-color: #1d4ed8;
}

QPushButton#btn_danger {
    background-color: #dc2626;
    color: #ffffff;
    border: 1px solid #b91c1c;
    font-weight: bold;
    padding: 9px 18px;
    border-radius: 8px;
}

QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    gridline-color: #f1f5f9;
}

QHeaderView::section {
    background-color: #f1f5f9;
    color: #475569;
    padding: 6px 10px;
    border: none;
    border-right: 1px solid #e2e8f0;
    border-bottom: 1px solid #e2e8f0;
    font-weight: bold;
}

QProgressBar {
    background-color: #e2e8f0;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    text-align: center;
    color: #0f172a;
    font-weight: bold;
    height: 18px;
}

QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 5px;
}
"""
