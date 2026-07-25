import os
import sys
import requests
import tiktoken
from tqdm import tqdm
import google.generativeai as genai   # Google Gemini API

# ========== 配置 ==========
INPUT_FILE = "ocr_book.txt"         # 原始 OCR 書
OUTPUT_FILE = "clean_book.md"       # 輸出檔案
TOC_FILE = "book_toc.md"            # 自動生成的目錄檔
TEMP_FOLDER = "temp_chunks"         # 暫存資料夾

# 選擇 LLM 來源: "ollama" 或 "gemini"
LLM_BACKEND = "gemini"   # 預設用本地 Ollama，可改成 "gemini"

# Ollama 配置
OLLAMA_MODEL = "hf.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF:IQ2_M"
OLLAMA_URL = "http://192.168.2.69:11434/api/chat"

# Gemini 配置
GEMINI_MODEL = "gemini-2.5-flash"
#GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")  # 從環境變數取得你的 API Key
GEMINI_API_KEY = "AIzaSyDmda6fQVGekEVU5XVVCtvukWMVBrM9J2I"  # 從環境變數取得你的 API Key


CHUNK_SIZE = 8000  # 每段 token 限制 (根據顯存或 API 限制可調)

# ========== 工具函數 ==========
def num_tokens(text, model="gpt-4o-mini"):
    """用 tiktoken 粗略估算 token 數"""
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

def split_text(text, max_tokens=CHUNK_SIZE):
    """把大文件拆成小塊"""
    words = text.split()
    chunks, chunk = [], []
    tokens = 0
    for word in words:
        t = num_tokens(word)
        if tokens + t > max_tokens:
            chunks.append(" ".join(chunk))
            chunk, tokens = [], 0
        chunk.append(word)
        tokens += t
    if chunk:
        chunks.append(" ".join(chunk))
    return chunks

# ========== LLM 呼叫 ==========
def query_ollama(prompt):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    resp = requests.post(OLLAMA_URL, json=payload)
    resp.raise_for_status()
    return resp.json()["message"]["content"]

def query_gemini(prompt):
    if not GEMINI_API_KEY:
        raise RuntimeError("請先設定環境變數 GEMINI_API_KEY")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(prompt)
    return response.text.strip()

def run_llm(prompt):
    """根據指定 backend 呼叫 LLM"""
    if LLM_BACKEND == "ollama":
        return query_ollama(prompt)
    elif LLM_BACKEND == "gemini":
        return query_gemini(prompt)
    else:
        raise ValueError(f"未知的 backend: {LLM_BACKEND}")

# ========== 清理與目錄 ==========
def clean_chunk(chunk):
    """LLM 清理文字"""
    prompt = f"""
你是一個文字排版助手。以下文字來自 OCR，請幫我：

1. 合理斷句，刪掉不正常換行。
2. 保留並標準化章節標題，使用 Markdown 格式：
   - 大章節用 "# "，例如 "# 第一章 風雲再起"
   - 小節用 "## "，例如 "## 小節一"
3. 僅改正錯別字，不要刪減或評論內容。

輸出乾淨的 Markdown：

--- 文字開始 ---
{chunk}
--- 文字結束 ---
"""
    return run_llm(prompt).strip()

def extract_toc(text):
    """LLM 提取章節目錄"""
    prompt = f"""
以下是一本書的 Markdown 內容，請幫我提取出清晰的目錄結構：

- 只保留章節與小節標題
- 使用 Markdown 列表輸出
例如：
- 第一章 XXX
  - 小節一
  - 小節二
- 第二章 YYY

--- 文字開始 ---
{text[:15000]}
--- 文字結束 ---
"""
    return run_llm(prompt).strip()

# ========== 主程序 ==========
if __name__ == "__main__":
    resume_mode = "--resume" in sys.argv

    # 建立 temp 資料夾
    if not os.path.exists(TEMP_FOLDER):
        os.makedirs(TEMP_FOLDER)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw_text = f.read()

    chunks = split_text(raw_text)
    print(f"總共 {len(chunks)} 段，要處理... (模式: {'resume模式' if resume_mode else '全新處理'})")
    print(f"使用 LLM: {LLM_BACKEND} ({'本地 Ollama' if LLM_BACKEND=='ollama' else 'Google Gemini'})")

    for i in tqdm(range(1, len(chunks)+1), desc="處理中", unit="段"):
        chunk = chunks[i-1]
        temp_path = os.path.join(TEMP_FOLDER, f"chunk_{i:04d}.md")

        if resume_mode and os.path.exists(temp_path):
            tqdm.write(f"略過第 {i} 段（已存在 temp file）")
            continue

        cleaned = clean_chunk(chunk)
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(cleaned)
        tqdm.write(f"已完成第 {i} 段 → {temp_path}")

    # 合併
    print("\n正在合併全部段落...")
    all_parts = []
    for i in range(1, len(chunks)+1):
        temp_path = os.path.join(TEMP_FOLDER, f"chunk_{i:04d}.md")
        with open(temp_path, "r", encoding="utf-8") as f:
            all_parts.append(f.read())
    full_text = "\n\n".join(all_parts)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(full_text)

    # 生成目錄
    print("正在提取章節目錄...")
    toc = extract_toc(full_text)
    with open(TOC_FILE, "w", encoding="utf-8") as f:
        f.write("# 目錄\n\n" + toc)

    print(f"\n✅ 完成！")
    print(f"- 正文： {OUTPUT_FILE}")
    print(f"- 目錄： {TOC_FILE}")
    print(f"- 暫存檔案： {TEMP_FOLDER}/")
