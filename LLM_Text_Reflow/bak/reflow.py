import os
import requests
import tiktoken

# ========== 配置 ==========
INPUT_FILE = "ocr_book.txt"     # 原始 OCR 書
OUTPUT_FILE = "clean_book.md"   # 輸出檔案
TOC_FILE = "book_toc.md"        # 自動生成的目錄檔
MODEL = "hf.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF:IQ2_M"                # 你在 ollama 裡安裝的模型名字
CHUNK_SIZE = 8000               # 每段 token 數限制 (根據顯存可調)

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

def query_ollama(prompt):
    """呼叫本地 Ollama"""
    url = "http://192.168.2.69:11434/api/chat"
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    resp = requests.post(url, json=payload)
    resp.raise_for_status()
    return resp.json()["message"]["content"]

def clean_chunk(chunk):
    """LLM 清理文字"""
    prompt = f"""
你是一個文字排版助手。以下文字來自 OCR，請幫我：

1. 合理斷句，刪掉不正常換行。
2. 保留並標準化章節標題，使用 Markdown 格式：
   - 大章節用 "# "，例如 "# 第一章 風雲再起"
   - 小節用 "## "，例如 "## 小節一"
3. 內容不要改變，不要刪減或添加。
4.仅仅是改正错别字，不要评论和改变內容

輸出乾淨的 Markdown 格式：

--- 文字開始 ---
{chunk}
--- 文字結束 ---
"""
    return query_ollama(prompt).strip()

def extract_toc(text):
    """LLM 提取章節目錄"""
    prompt = f"""
以下是一本書的 Markdown 內容，請幫我提取出清晰的目錄結構：

- 只保留章節與小節標題
- 使用 Markdown 列表輸出
- 例如：
  - 第一章 XXX
    - 小節一
    - 小節二
  - 第二章 YYY

--- 文字開始 ---
{text[:15000]}
--- 文字結束 ---
"""
    return query_ollama(prompt).strip()

# ========== 主程序 ==========
if __name__ == "__main__":
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw_text = f.read()

    chunks = split_text(raw_text)
    print(f"總共 {len(chunks)} 段，要處理...")

    cleaned_parts = []
    for i, chunk in enumerate(chunks, 1):
        print(f"處理第 {i}/{len(chunks)} 段...")
        cleaned = clean_chunk(chunk)
        cleaned_parts.append(cleaned)

    full_text = "\n\n".join(cleaned_parts)

    # 儲存完整排版後的書
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(full_text)

    # 生成目錄
    print("正在提取章節目錄...")
    toc = extract_toc(full_text)
    with open(TOC_FILE, "w", encoding="utf-8") as f:
        f.write("# 目錄\n\n" + toc)

    print(f"完成！\n已輸出正文：{OUTPUT_FILE}\n已輸出目錄：{TOC_FILE}")
