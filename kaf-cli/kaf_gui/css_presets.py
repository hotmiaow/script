# -*- coding: utf-8 -*-
"""
內建精美正體中文電子書 CSS 樣式預設模板
"""

CSS_PRESETS = {
    "預設樣式 (Kaf 預設)": {
        "description": "kaf-cli 預設的排版樣式",
        "css": """/* kaf-cli 預設樣式 */
body {
    margin: 1.5em;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang TC", "Microsoft JhengHei", "Noto Sans TC", sans-serif;
}

h2.volume {
    text-align: center;
    border-top: 3px double #555;
    border-bottom: 3px double #555;
    padding: 10px 0;
    margin: 2em 0 1.5em 0;
    color: #333;
}

h3.title {
    text-align: center;
    font-size: 1.35em;
    margin: 1.8em 0 1em 0;
    font-weight: bold;
}

h3.title span.chapter-number {
    color: #666;
    margin-right: 0.5em;
}

.content {
    text-indent: 2em;
    line-height: 1.6;
    margin-bottom: 0.8em;
    text-align: justify;
    word-break: break-all;
}
"""
    },

    "臺灣典雅實體書 (Classic Book)": {
        "description": "經典實體小說風格，襯線明體字型、雅緻雙線分卷邊框與大氣章節標題",
        "css": """/* 臺灣典雅實體書風格 */
body {
    margin: 1.8em 1.2em;
    font-family: "Source Han Serif TC", "Noto Serif CJK TC", "Songti TC", "MingLiU", serif;
    color: #222222;
    background-color: #fdfdfd;
}

/* 卷名雙線邊框與古典色澤 */
h2.volume {
    text-align: center;
    border-top: 3px double #8b1d1d;
    border-bottom: 3px double #8b1d1d;
    padding: 14px 0;
    margin: 2.5em 0 2em 0;
    color: #701010;
    font-weight: bold;
    letter-spacing: 2px;
}

/* 章節標題 */
h3.title {
    text-align: center;
    font-size: 1.4em;
    margin: 2.2em 0 1.2em 0;
    color: #1a1a1a;
    letter-spacing: 1px;
}

/* 序號樣式 */
h3.title span.chapter-number {
    display: block;
    font-size: 0.85em;
    color: #888888;
    margin-bottom: 6px;
    font-weight: normal;
}

/* 正文段落縮排與優美行距 */
.content {
    text-indent: 2em;
    line-height: 1.85;
    margin-bottom: 0.9em;
    text-align: justify;
    text-justify: inter-ideograph;
    word-break: break-all;
}
"""
    },

    "護眼柔和深色模式 (Dark / Night Mode)": {
        "description": "黑底護眼模式，夜間低藍光閱讀不傷眼",
        "css": """/* 護眼柔和深色模式 */
body {
    margin: 1.5em;
    background-color: #1a1c1e;
    color: #c9d1d9;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang TC", "Microsoft JhengHei", "Noto Sans TC", sans-serif;
}

h2.volume {
    text-align: center;
    border-top: 2px solid #30363d;
    border-bottom: 2px solid #30363d;
    padding: 12px 0;
    margin: 2em 0;
    color: #58a6ff;
}

h3.title {
    text-align: center;
    font-size: 1.35em;
    margin: 1.8em 0 1em 0;
    color: #f0f6fc;
}

h3.title span.chapter-number {
    color: #8b949e;
}

.content {
    text-indent: 2em;
    line-height: 1.75;
    margin-bottom: 0.85em;
    color: #c9d1d9;
    text-align: justify;
}
"""
    },

    "文青直排直書 (Vertical Reading)": {
        "description": "傳統中文直排閱讀模式 (由上而下、由右至左)，適合支援直排的電子書閱讀器",
        "css": """/* 文青直排直書排版 */
html, body {
    writing-mode: vertical-rl;
    -webkit-writing-mode: vertical-rl;
    margin: 1.5em 1.2em;
    font-family: "Source Han Serif TC", "Songti TC", "MingLiU", serif;
    color: #2b2b2b;
}

h2.volume {
    border-right: 3px double #733d3d;
    border-left: 3px double #733d3d;
    padding: 0 10px;
    margin: 0 2em;
    color: #632b2b;
    letter-spacing: 3px;
}

h3.title {
    font-size: 1.3em;
    margin: 0 1.8em;
    letter-spacing: 2px;
}

h3.title span.chapter-number {
    display: inline-block;
    color: #777;
    margin-left: 8px;
}

.content {
    text-indent: 2em;
    line-height: 1.9;
    margin-left: 0.8em;
    letter-spacing: 0.5px;
}
"""
    },

    "極簡無襯線現代風 (Modern Clean)": {
        "description": "簡約清爽的黑體排版，適合手機與高解析度螢幕閱讀",
        "css": """/* 極簡無襯線現代風 */
body {
    margin: 1.5em;
    font-family: "PingFang TC", "Helvetica Neue", "Microsoft JhengHei", "Noto Sans TC", sans-serif;
    color: #333333;
}

h2.volume {
    text-align: center;
    background: #f0f3f6;
    padding: 10px 0;
    margin: 2em 0 1.5em 0;
    border-radius: 6px;
    color: #24292f;
    font-size: 1.25em;
}

h3.title {
    text-align: left;
    font-size: 1.3em;
    margin: 1.6em 0 0.8em 0;
    color: #0969da;
    border-left: 4px solid #0969da;
    padding-left: 10px;
}

h3.title span.chapter-number {
    color: #57606a;
    font-size: 0.9em;
}

.content {
    text-indent: 2em;
    line-height: 1.7;
    margin-bottom: 0.8em;
    text-align: justify;
}
"""
    }
}
