# kaf-cli 繁體中文電子書轉換器 (專業 GUI 版)

基於 [ystyle/kaf-cli](https://github.com/ystyle/kaf-cli) 所開發的現代化 **正體中文 / 繁體中文** 圖形使用者介面（GUI）。  
專為電子書愛好者量身打造，將 TXT 文字小說一鍵轉換為排版精美的 **EPUB**、**MOBI**、**AZW3** 電子書！

---

## ✨ 核心特色

- 🇹🇼 **道地正體中文介面**：介面詞彙全面依據臺灣與香港繁體中文使用習慣設計（檔案、資料夾、設定、預設、排版、正則表達式等），非機械式簡轉繁。
- 🔄 **內建高品質簡轉繁（零依賴）**：
  - 支援在轉換為電子書時，**同步將簡體小說內文轉換為臺灣正體或香港繁體**。
  - 內建在地化詞彙庫（如：網絡➔網路、軟件➔軟體、內存➔記憶體、屏幕➔螢幕、數據庫➔資料庫等）。
  - 純 Python 標準庫實現，**不需額外安裝 OpenCC 即可高速轉換**。
- 📚 **檔案拖曳與批次佇列**：
  - 支援直接拖曳單檔或多個 `.txt` 檔案至視窗中。
  - 智慧檔名解析：自動從《書名》作者：某某.txt 等格式中提取正確書名與作者，並即時繁體化。
- 🔍 **章節正則即時測試器（目錄預覽）**：
  - 解決小說章節匹配不到的痛點！轉換前點擊「**即時測試章節匹配**」，即可預覽分析前數千行之章節、分卷與排除數量，確保目錄正確。
- 📐 **完整排版與版面設定**：
  - 支援標題對齊（居中/靠左/靠右）、章節序號單獨成行、首行縮排字數（0~8字）、段落間距（em/px）、行高（line-height）設定。
  - 支援自訂內嵌字型（.ttf / .otf，如思源宋體、思源黑體）。
  - 支援語言標籤設定（zh-TW、zh-HK、zh、en、ja 等）。
- 🎨 **豐富的封面設定模式**：
  - **自動偵測**：自動套用小說同目錄下之 `cover.png` 或 `cover.jpg`。
  - **自訂圖片**：自訂選取本機 JPG、PNG、WebP 圖片，並提供縮圖預覽。
  - **Orly 經典動物封面**：支援自訂 16 色系或 HEX 色碼主題色，以及 0~41 種動物圖案索引。
- 🖋️ **精選正體中文 CSS 樣式庫與即時編輯器**：
  - 內建多組精選排版：
    1. **臺灣典雅實體書**（仿古風雙線卷名、大字標題、精準字距行高）
    2. **護眼柔和深色模式**（夜間閱讀低藍光）
    3. **文青直排直書排版**（支援直排 EPUB 閱讀器，傳統右至左直書）
    4. **極簡無襯線現代風**（清爽黑體、卡片式卷名）
    5. **原版 kaf-cli 預設**
  - 內建語法高亮編輯器，可隨時微調並儲存為 CSS 檔案。
- 🖥️ **雙模式執行（Desktop + Web）**：
  - **桌面視窗模式**：以 PyQt5 打造，流暢多線程執行，即時日誌輸出，轉換不卡死。
  - **Web 瀏覽器模式**：適合無桌面環境、遠端主機、NAS 或手機/平板區域網路內開啟轉換。
- ⚙️ **多方案預設管理**：
  - 預載「臺灣典雅實體書」、「Kindle 最佳化」、「護眼深色」、「文青直排」等預設配置。
  - 支援使用者自行儲存個人常用的客製化預設方案。

---

## 🚀 快速啟動指南

本工具已預先內建 Linux 與 Windows 版本的 `kaf-cli`（v1.3.16）與 `kindlegen.exe`。

### 1. Linux / macOS

```bash
# 啟動桌面版 GUI
./launch.sh

# 或啟動 Web 瀏覽器版 (瀏覽器開啟 http://localhost:8080)
./launch_web.sh
```

亦可雙擊 `kaf-gui.desktop` 建立桌面啟動捷徑。

### 2. Windows

- **桌面視窗模式**：直接雙擊執行 `launch.bat`
- **Web 瀏覽器模式**：雙擊執行 `launch_web.bat`，或在瀏覽器造訪 `http://localhost:8080`

### 3. 命令列直接執行

```bash
# 預設桌面模式
python3 gui.py

# 指定 Web 模式與連接埠
python3 gui.py --web --port 8080
```

---

## 🛠️ kaf-cli 命令列參數對應說明

| kaf-cli 參數 | GUI 介面對應位置 | 說明 |
| :--- | :--- | :--- |
| `-filename` | 檔案與佇列清單 | 支援單檔、多選與拖曳加入 |
| `-bookname` | 佇列清單 / 書名設定 | 預設自動提取書名並繁體化 |
| `-author` | 佇列清單 / 作者設定 | 預設自動提取作者名 |
| `-format` | 輸出格式下拉選單 | `all`, `epub`, `mobi`, `azw3` |
| `-out` | 自訂輸出目錄 | 自訂目錄路徑（留空則與 txt 相同） |
| `-lang` | 書籍語言標籤 | 預設 `zh-TW`（臺灣正體） |
| `-align` | 標題對齊方式 | `center` (居中), `left` (靠左), `right` (靠右) |
| `-indent` | 段落首行縮排字數 | 預設 2 字（可自訂 0~8 字） |
| `-bottom` | 段落間距 | 預設 `1em`，提供 0.5em/1em/1.5em 快捷選擇 |
| `-line-height`| 行高 / 行間距 | 預設 `1.85`（寬鬆舒適），亦可設 `1.5rem` 等 |
| `-separate-chapter-number` | 章節序號單獨成行 | 核取方塊開關（序號與標題分行） |
| `-tips` | 附帶說明教學頁 | 核取方塊開關（可勾選或取消） |
| `-font` | 內嵌字型檔 | 支援選取本機 `.ttf` 或 `.otf` 字型 |
| `-custom-css-file` | 自訂 CSS 樣式 | 內建模板選擇、匯入與即時編輯 |
| `-cover` | 封面設定模式 | 自動偵測 / 本機圖片 / Orly 動物封面 |
| `-cover-orly-color` | Orly 主題顏色 | 支援調色盤選取與 1-16 / HEX 色碼 |
| `-cover-orly-idx` | Orly 動物索引 | 0~41 或 -1（隨機圖案） |
| `-match` | 章節正則表達式 | 內建常見中文、英文與特殊正則下拉範本 |
| `-volume-match` | 分卷正則表達式 | 支援一鍵停用或自訂分卷規則 |
| `-exclude` | 排除無效正則 | 排除如「第X部隊」、「第X部門」等非小說章節 |
| `-max` | 標題最大字數 | 預設 35 字 |
| `-unknow-title` | 未知章節名稱 | 預設「章節正文」 |

---

## 📁 檔案結構說明

```
kaf-cli/
├── gui.py                  # 主要啟動入口 (自動判定桌面或 Web 模式)
├── launch.sh               # Linux / macOS 一鍵啟動腳本
├── launch.bat              # Windows 一鍵啟動腳本
├── launch_web.sh           # Web 模式一鍵啟動腳本
├── launch_web.bat          # Windows Web 模式啟動腳本
├── kaf-gui.desktop         # Linux 桌面應用程式捷徑
├── kaf-cli                 # kaf-cli Linux 64位元核心執行檔
├── kaf-cli.exe             # kaf-cli Windows 64位元核心執行檔
├── kindlegen.exe           # Amazon mobi 產生工具 (Windows)
├── kaf_gui/                # GUI 核心套件模組
│   ├── __init__.py
│   ├── app.py              # PyQt5 桌面版主介面與背景執行緒
│   ├── converter_engine.py # kaf-cli 呼叫與參數組裝引擎
│   ├── zh_converter.py     # 零依賴繁簡轉換引擎 (含臺灣在地化詞彙庫)
│   ├── regex_tester.py     # txt 檔名解析與章節目錄測試工具
│   ├── css_presets.py      # 正體中文電子書精選 CSS 模板
│   ├── config_manager.py   # 設定與多方案持久化管理 (JSON)
│   ├── styles.py           # 現代化深色/淺色 QSS 樣式主題
│   ├── web_server.py       # 內建輕量 Web GUI 伺服器
│   └── data/               # 繁簡對照詞庫資料 (Gzip 壓縮格式)
└── templates/              # Web 模式前端單頁應用
    └── index.html
```

---

## 📜 授權與感謝

- kaf-cli 核心工具原作者：[ystyle](https://github.com/ystyle/kaf-cli)
- 遵循 MIT License 開源協議。
