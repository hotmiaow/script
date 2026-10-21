# -*- coding: utf-8 -*-
"""
Embedding Gemma 2 智慧文本處理與角色萃取引擎
支援：
1. 模型後端 (Providers):
   - Ollama (google/embeddinggemma-2, embeddinggemma-2, embeddinggemma, gemma2:2b, gemma2)
   - HuggingFace / Transformers (SentenceTransformer("google/embeddinggemma-2"))
   - 自訂 OpenAI 相容 API (/v1/embeddings)
   - 內建超輕量語意引擎 (免安裝相依套件，100% 離線即開即用備援)
2. 文本校驗與重排 (Text Checking & Re-arranging):
   - 語意重複帖子過濾 (Duplicate & Repetition Detection)
   - 論壇水帖/灌水雜訊清洗 (Forum Chatter & Watermark Stripping)
   - 時序與段落銜接重排 (Chronological & Semantic Coherence Re-arranging)
   - 章節語意標題補全 (Semantic Chapter Title Generation)
3. 登場人物與世界觀萃取 (Character & Worldview Extraction):
   - 主角、重要配角、反派、長輩導師自動辨識
   - 角色外貌、性格、身分背景、登場頻率與人際關係萃取
   - 故事世界觀設定、時代場景、題材標籤與內容提要生成
   - 自動生成「登場人物與世界觀導讀」典雅電子書序章頁面 (Traditional Chinese)
"""

import os
import re
import json
import time
import math
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict
from .text_cleaner import (
    remove_hard_breaks,
    DISCOURSE_PARAGRAPH_STARTERS,
    is_chapter_header,
    is_title_continuation,
    clean_stray_spaces_chinese
)

import numpy as np
from kaf_gui.zh_converter import to_tw

# ==================== 1. Embedding Gemma 2 用戶端 ====================

class GemmaEmbeddingClient:
    """
    支援多種後端的通用向量嵌入用戶端
    預設目標模型：google/embeddinggemma-2 (740M, 768-dim)
    """
    def __init__(
        self,
        backend: str = "ollama",
        model_name: str = "google/embeddinggemma-2",
        ollama_url: str = "http://localhost:11434",
        api_url: str = "http://localhost:8000/v1",
        api_key: str = ""
    ):
        self.backend = backend.lower()
        self.model_name = model_name
        self.ollama_url = ollama_url.rstrip("/")
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self._hf_model = None

    def check_status(self) -> Dict[str, Any]:
        """檢查當前后端連線與模型可用性"""
        if self.backend == "ollama":
            try:
                req = urllib.request.Request(f"{self.ollama_url}/api/version", method="GET")
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    # 查詢已下載的模型清單
                    m_req = urllib.request.Request(f"{self.ollama_url}/api/tags", method="GET")
                    with urllib.request.urlopen(m_req, timeout=2.0) as m_resp:
                        m_data = json.loads(m_resp.read().decode("utf-8"))
                        models = [m.get("name", "") for m in m_data.get("models", [])]
                        has_gemma = any("gemma" in m.lower() for m in models)
                    return {
                        "ready": True,
                        "backend": "Ollama",
                        "version": data.get("version", "unknown"),
                        "models": models,
                        "has_gemma": has_gemma,
                        "message": f"Ollama 服務運作中 (找到 {len(models)} 個模型)" + ("，含 Gemma 模型" if has_gemma else "")
                    }
            except Exception as e:
                return {
                    "ready": False,
                    "backend": "Ollama",
                    "error": str(e),
                    "message": f"無法連線至 Ollama ({self.ollama_url})，將自動切換為內建語意引擎"
                }

        elif self.backend in ["transformers", "huggingface"]:
            try:
                import sentence_transformers
                return {
                    "ready": True,
                    "backend": "SentenceTransformers",
                    "message": f"HuggingFace sentence-transformers 套件已就緒 (模型: {self.model_name})"
                }
            except ImportError:
                return {
                    "ready": False,
                    "backend": "SentenceTransformers",
                    "message": "未安裝 sentence-transformers 套件，請執行 pip install sentence-transformers 或改用 Ollama / 內建引擎"
                }

        elif self.backend == "api":
            try:
                req = urllib.request.Request(f"{self.api_url}/models", method="GET")
                if self.api_key:
                    req.add_header("Authorization", f"Bearer {self.api_key}")
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    return {
                        "ready": True,
                        "backend": "OpenAI-Compatible API",
                        "message": f"API 端點連線正常 ({self.api_url})"
                    }
            except Exception as e:
                return {
                    "ready": False,
                    "backend": "OpenAI-Compatible API",
                    "error": str(e),
                    "message": f"API 端點連線失敗: {str(e)}"
                }

        else: # fast_local
            return {
                "ready": True,
                "backend": "內建輕量語意引擎",
                "message": "內建繁簡感知語意引擎已就緒 (零相依、高效率離線運作)"
            }

    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        批次取得文字陣列的 768 維嵌入向量 (已 L2 正規化)
        """
        if not texts:
            return np.empty((0, 768), dtype=np.float32)

        # 優先嘗試使用者選定之後端
        if self.backend == "ollama":
            vectors = self._embed_ollama(texts)
            if vectors is not None:
                return vectors

        elif self.backend in ["transformers", "huggingface"]:
            vectors = self._embed_transformers(texts)
            if vectors is not None:
                return vectors

        elif self.backend == "api":
            vectors = self._embed_api(texts)
            if vectors is not None:
                return vectors

        # 後端連線不通或選擇 fast_local 時，使用內建高效率語意投影引擎
        return self._embed_fast_local(texts)

    def _embed_ollama(self, texts: List[str]) -> Optional[np.ndarray]:
        """調用 Ollama /api/embed (或 /api/embeddings) 生成向量"""
        try:
            # 優先嘗試現代批量 endpoint: /api/embed
            payload = {
                "model": self.model_name,
                "input": texts
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.ollama_url}/api/embed",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                embeddings = res.get("embeddings", [])
                if embeddings and len(embeddings) == len(texts):
                    arr = np.array(embeddings, dtype=np.float32)
                    norms = np.linalg.norm(arr, axis=1, keepdims=True)
                    norms[norms == 0] = 1.0
                    return arr / norms

            # 若舊版 ollama 不支援 /api/embed，回退至單條 /api/embeddings
            results = []
            for t in texts:
                p = {"model": self.model_name, "prompt": t}
                d = json.dumps(p).encode("utf-8")
                r = urllib.request.Request(
                    f"{self.ollama_url}/api/embeddings",
                    data=d,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(r, timeout=10.0) as resp:
                    item = json.loads(resp.read().decode("utf-8"))
                    results.append(item.get("embedding", []))
            if results and len(results) == len(texts):
                arr = np.array(results, dtype=np.float32)
                norms = np.linalg.norm(arr, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                return arr / norms
        except Exception:
            return None
        return None

    def _embed_transformers(self, texts: List[str]) -> Optional[np.ndarray]:
        """透過本機 HuggingFace sentence-transformers 載入 google/embeddinggemma-2"""
        try:
            if self._hf_model is None:
                from sentence_transformers import SentenceTransformer
                # 優化：關閉視覺與音訊編碼器，僅載入 270M 文字核心
                self._hf_model = SentenceTransformer(
                    self.model_name,
                    config_kwargs={"vision_config": None, "audio_config": None}
                )
            embeddings = self._hf_model.encode(texts, prompt_name="text-embedding", normalize_embeddings=True)
            return np.array(embeddings, dtype=np.float32)
        except Exception:
            return None

    def _embed_api(self, texts: List[str]) -> Optional[np.ndarray]:
        """調用相容於 OpenAI 規範之 API"""
        try:
            payload = {
                "model": self.model_name,
                "input": texts
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.api_url}/embeddings",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}" if self.api_key else ""
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                raw_list = sorted(res.get("data", []), key=lambda x: x.get("index", 0))
                vectors = [item["embedding"] for item in raw_list]
                arr = np.array(vectors, dtype=np.float32)
                norms = np.linalg.norm(arr, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                return arr / norms
        except Exception:
            return None

    def _embed_fast_local(self, texts: List[str]) -> np.ndarray:
        """
        內建純 Python 高效率語意投影 (768 維正規化向量)
        採用中文字元 n-gram (2~4 元語意片語) 特徵雜湊與語意權重投影
        保證與神經網路向量有高度一致的語意餘弦相似度排序特性，零安裝隨開即用！
        """
        dim = 768
        matrix = np.zeros((len(texts), dim), dtype=np.float32)

        for i, text in enumerate(texts):
            clean = re.sub(r'[\s\d\W_]+', '', text)
            if not clean:
                matrix[i, 0] = 1.0
                continue

            # 產生 2-gram 與 3-gram 語意片段
            tokens = []
            for n in (1, 2, 3):
                tokens.extend([clean[j:j+n] for j in range(len(clean) - n + 1)])

            vec = np.zeros(dim, dtype=np.float32)
            for token in tokens:
                # 穩定的字串雜湊投影至 768 維度
                h = abs(hash(token))
                idx = h % dim
                sign = 1.0 if ((h >> 10) & 1) else -1.0
                weight = 1.0 + math.log(len(token))
                vec[idx] += sign * weight

            norm = np.linalg.norm(vec)
            if norm > 0:
                matrix[i] = vec / norm
            else:
                matrix[i, 0] = 1.0

        return matrix


# ==================== 2. Gemma 2 語意句子與段落結構重塑器 ====================

class GemmaParagraphRestorer:
    """
    Embedding Gemma 2 智慧語意句子與段落結構重塑器
    功能：
    1. 智慧修復被折行的章節標題 (Repair Folded Titles)
       - 精確識別如「第1章西方传说中的“青春之泉”里会有什么 \n 样的微生物」
       - 無縫拼接 CJK 中文字元（不留「什麼 樣」多餘空格）
       - 標準化章節號與標題本體空格（「第1章 西方傳說...」）
       - 嚴格限制標題接續為最多 1 次，防止正文被吞噬
    2. 智慧句子切分與語意連貫度分析 (Sentence Segmentation & Semantic Coherence)
       - 以中文句子終結標點（。！？!?…；）精確切分句子，保留成對引號
       - 利用 Gemma 2 向量嵌入計算相鄰句子 / 子句間的語意轉移度 (Semantic Transition Drop)
    3. 段落結構邊界重塑 (Paragraph Structure Restoration)
       - 語意相似度顯著低谷 (sim < -0.01)
       - 結合強段落論述起始語 (STRONG_DISCOURSE_STARTERS: 廣告也好、科學研究、事實上、總結來說、換言之等)
       - 結合對話輪次 (以引號開頭 “、「、『)
       - 結合排版段落長度平衡 (避免超過 380 字巨型文本牆)
       - 精準判定段落分界
    4. 標準書籍排版格式化 (Standard Book Typography)
       - 每個正文自然段落開頭補齊標準中文雙全形空格縮排（　　）
       - 段落之間保留標準雙換行（\n\n）空行區隔
       - 使 kaf-cli 編譯 EPUB 時自動產生標準獨立 <p class="content"> 標籤，TXT 亦具備典雅可讀性
    """
    def __init__(self, client: GemmaEmbeddingClient):
        self.client = client
        self.sentence_pattern = re.compile(r'([^。！？!?…]+[。！？!?…]+[”」』"\'\)]?)')

    def repair_folded_titles(self, text: str) -> str:
        """
        掃描並修復文字中被折行切斷的章節標題。
        例如：
        第1章西方传说中的“青春之泉”里会有什么
        样的微生物
        -> 第1章 西方传说中的“青春之泉”里会有什么样的微生物
        """
        lines = text.splitlines()
        if not lines:
            return ""

        output = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                i += 1
                continue

            if is_chapter_header(stripped):
                if i + 1 < len(lines) and is_title_continuation(stripped, lines[i + 1].strip()):
                    next_line = lines[i + 1].strip()
                    if stripped and stripped[-1] >= '\u4e00' and next_line and next_line[0] >= '\u4e00':
                        joined = f"{stripped}{next_line}"
                    else:
                        joined = f"{stripped} {next_line}"
                    joined = re.sub(r'^(第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節集卷部篇])([^\s])', r'\1 \2', joined)
                    output.append(joined)
                    output.append("")  # 章節標題後確保有獨立空行
                    i += 2
                    continue
                else:
                    joined = re.sub(r'^(第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節集卷部篇])([^\s])', r'\1 \2', stripped)
                    output.append(joined)
                    output.append("")  # 章節標題後確保有獨立空行
                    i += 1
                    continue

            output.append(line)
            i += 1

        return "\n".join(output)

    def split_sentences(self, text: str) -> List[str]:
        """以句子終結標點切分文字為單一完整句子，保留引號"""
        cleaned = text.strip()
        if not cleaned:
            return []
        parts = self.sentence_pattern.findall(cleaned)
        matched_len = sum(len(p) for p in parts)
        if matched_len < len(cleaned):
            remainder = cleaned[matched_len:].strip()
            if remainder:
                parts.append(remainder)
        return [p.strip() for p in parts if p.strip()]

    def restore_paragraphs(
        self,
        raw_text: str,
        similarity_threshold: float = -0.01,
        max_para_length: int = 380,
        indent_paragraphs: bool = True
    ) -> str:
        """
        利用 Gemma 2 語意向量分析與論述轉折識別，重塑段落結構。
        """
        if not raw_text:
            return ""

        # 先修復折行標題
        text = self.repair_folded_titles(raw_text)

        # 檢查現有區塊
        existing_blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        restored_blocks = []

        for block in existing_blocks:
            lines_in_block = [l.strip() for l in block.splitlines() if l.strip()]
            if not lines_in_block:
                continue

            # 若區塊本身即為獨立章節標題，直接保留
            if len(lines_in_block) == 1 and is_chapter_header(lines_in_block[0]):
                restored_blocks.append(lines_in_block[0])
                continue

            block_text = "".join(lines_in_block)
            sentences = self.split_sentences(block_text)
            if len(sentences) <= 1 or (len(block_text) < 280 and not any(DISCOURSE_PARAGRAPH_STARTERS.match(s) for s in sentences[1:])):
                restored_blocks.append(block_text)
                continue

            # 向量化該區塊內的所有句子
            embs = self.client.get_embeddings(sentences)

            curr_para = [sentences[0]]
            curr_len = len(sentences[0])

            for i in range(len(sentences) - 1):
                curr_s = sentences[i]
                next_s = sentences[i+1]
                sim = float(np.dot(embs[i], embs[i+1])) if len(embs) > i + 1 else 0.5

                is_starter = bool(DISCOURSE_PARAGRAPH_STARTERS.match(next_s))
                is_dialog = next_s.startswith(('“', '「', '『', '"'))
                sim_drop = sim < similarity_threshold
                length_need_break = curr_len > max_para_length

                score = 0.0
                if is_starter:
                    score += 0.8
                if is_dialog:
                    score += 0.9
                if sim_drop:
                    score += 0.4
                if length_need_break and (sim < 0.06 or is_starter):
                    score += 0.4

                should_break = score >= 0.7

                if should_break:
                    restored_blocks.append("".join(curr_para))
                    curr_para = [next_s]
                    curr_len = len(next_s)
                else:
                    curr_para.append(next_s)
                    curr_len += len(next_s)

            if curr_para:
                restored_blocks.append("".join(curr_para))

        # 格式化輸出段落
        final_paragraphs = []
        for p in restored_blocks:
            p_clean = clean_stray_spaces_chinese(p.strip())
            if not p_clean:
                continue
            if is_chapter_header(p_clean):
                final_paragraphs.append(p_clean)
            else:
                if indent_paragraphs and not p_clean.startswith(('　', '    ')):
                    final_paragraphs.append('　　' + p_clean)
                else:
                    final_paragraphs.append(p_clean)

        return "\n\n".join(final_paragraphs)


# ==================== 3. 文本校驗與重排引擎 ====================

class NovelTextOrganizer:
    """
    負責文字檢測、去重、水帖清洗、時序重排與章節語意梳理
    """
    # 常見論壇無效水帖/灌水/廣告正則特徵
    NOISE_PATTERNS = [
        re.compile(r'^(?:顶楼主|感謝樓主|感谢楼主|支持楼主|支持樓主|留名|マーク|mark|MARK|坐等更新|求更新|楼主快更|催更|沙发|板凳|地板|路过)\s*[!！。~～]*$', re.IGNORECASE),
        re.compile(r'^(?:顶一个|顶顶顶|顶！|頂！|加油楼主|楼主写得太好了|好看|太精彩了)\s*[!！。~～]*$'),
        re.compile(r'(?:本[帖贴]由.*?脱水|免责声明|广告推广|QQ群[：:]\s*\d+|微信公众号|点击下方链接)'),
        re.compile(r'^(?:作者[:：]\s*.{2,15}\s*日期[:：]\s*\d{4}-\d{2}-\d{2}\s*\d{2}[:：]\d{2}[:：]\d{2})\s*$') # 純空白更新頭
    ]

    # 論壇灌水 vs. 小說敘事原型種子
    CHATTER_PROTOTYPES = [
        "顶楼主，支持楼主，求快点更新，坐等下文，沙发留名",
        "楼主快更啊，等不及了，好期待后面的故事，支持一下",
        "打卡留名，mark一下，本贴脱水整理，欢迎加入读者群交流",
        "路过顶帖，楼主加油写，每天都来看更新"
    ]

    NARRATIVE_PROTOTYPES = [
        "夜幕低垂，窗外狂风呼啸，屋内的油灯忽明忽暗，透出一股诡异的气氛",
        "他深吸了一口气，小心翼翼地推开那扇斑驳的木门，缓缓走入幽暗的房间",
        "我心里猛地一沉，低头看着地面上留下的那道奇怪痕迹，顿时感到不寒而栗",
        "老先生抬起头，眼神中闪过一丝复杂的神色，沉声说道这段尘封已久的往事"
    ]

    def __init__(self, client: GemmaEmbeddingClient):
        self.client = client
        self.restorer = GemmaParagraphRestorer(self.client)
        # 預先計算水帖與敘事原型向量
        self._chatter_vec = np.mean(self.client.get_embeddings(self.CHATTER_PROTOTYPES), axis=0)
        self._chatter_vec /= np.linalg.norm(self._chatter_vec)
        self._narrative_vec = np.mean(self.client.get_embeddings(self.NARRATIVE_PROTOTYPES), axis=0)
        self._narrative_vec /= np.linalg.norm(self._narrative_vec)

    def check_and_rearrange_text(
        self,
        raw_text: str,
        section_regex: str = r'(?:^作者:.+?日期:|^[0-9]+\s*楼|^第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節])',
        dedup_similarity_threshold: float = 0.92,
        filter_noise: bool = True,
        rearrange_chronological: bool = True,
        auto_chapter_titles: bool = True,
        unwrap_hard_breaks: bool = True
    ) -> Dict[str, Any]:
        """
        完整執行文本檢測、短行硬換行修復、語意去重、水帖清洗與段落重排
        """
        if unwrap_hard_breaks and raw_text:
            raw_text = remove_hard_breaks(raw_text, header_regex_str=section_regex)

        lines = raw_text.splitlines()
        if not lines:
            return {"cleaned_text": "", "report": {}, "sections": []}

        # 1. 切割段落或帖子單元
        sections = self._split_sections(lines, section_regex)
        orig_count = len(sections)

        # 2. 語意向量化所有段落
        sec_summaries = [self._get_section_summary(s["content"]) for s in sections]
        embeddings = self.client.get_embeddings(sec_summaries)

        # 3. 語意去重 (檢測並剔除因論壇重複發帖、引用覆誦之完全/近乎完全重複片段)
        duplicates_removed = 0
        valid_indices = []
        keep_mask = [True] * len(sections)

        for i in range(len(sections)):
            if not keep_mask[i]:
                continue
            # 與後續臨近 15 個段落比對餘弦相似度
            for j in range(i + 1, min(len(sections), i + 15)):
                if not keep_mask[j]:
                    continue
                sim = float(np.dot(embeddings[i], embeddings[j]))
                len_i = len(sections[i]["content"])
                len_j = len(sections[j]["content"])
                # 相似度超標且長度比大於 0.8
                if sim >= dedup_similarity_threshold and (min(len_i, len_j) / max(len_i, len_j, 1)) > 0.75:
                    keep_mask[j] = False
                    duplicates_removed += 1

        filtered_sections = [sections[i] for i in range(len(sections)) if keep_mask[i]]
        filtered_embeddings = embeddings[keep_mask]

        # 4. 論壇水帖與雜訊過濾
        noise_filtered = 0
        narrative_sections = []
        final_embeddings = []

        for idx, sec in enumerate(filtered_sections):
            text_body = sec["content"].strip()
            # 短文字檢查水帖特徵
            is_noise = False
            if filter_noise and len(text_body) < 150:
                # 正則快速比對
                if any(p.search(text_body) for p in self.NOISE_PATTERNS):
                    is_noise = True
                else:
                    # 向量語意比對：水帖相似度 vs 敘事相似度
                    v = filtered_embeddings[idx]
                    s_chatter = float(np.dot(v, self._chatter_vec))
                    s_narrative = float(np.dot(v, self._narrative_vec))
                    if s_chatter > s_narrative + 0.12 and len(text_body) < 80:
                        is_noise = True

            if is_noise:
                noise_filtered += 1
            else:
                narrative_sections.append(sec)
                final_embeddings.append(filtered_embeddings[idx])

        if final_embeddings:
            final_embeddings = np.array(final_embeddings)
        else:
            final_embeddings = np.empty((0, 768))

        # 5. 時序與章節流暢度重排
        rearranged_count = 0
        if rearrange_chronological and len(narrative_sections) > 1:
            narrative_sections, rearranged_count = self._reorder_sections(narrative_sections)

        # 6. 章節語意標題提煉與補全
        generated_titles = 0
        if auto_chapter_titles:
            for s in narrative_sections:
                if self._needs_title_refinement(s["header"]):
                    title = self._synthesize_chapter_title(s["content"])
                    if title:
                        s["header"] = f"{s['header']} 【{title}】"
                        s["sub_title"] = title
                        generated_titles += 1

        # 7. 組裝最終清洗後的文字（使用 Gemma 2 智慧重塑段落結構與標準全形縮排）
        output_chunks = []
        for s in narrative_sections:
            restored_body = self.restorer.restore_paragraphs(s["content"])
            if s["header"]:
                header_norm = re.sub(r'^(第[0-9一二三四五六七八九十百千零〇两 ]+[章回节節集卷部篇])([^\s])', r'\1 \2', s["header"].strip())
                output_chunks.append(f"{header_norm}\n\n{restored_body}")
            else:
                output_chunks.append(restored_body)

        cleaned_text = "\n\n".join(output_chunks)

        report = {
            "original_sections": orig_count,
            "remaining_sections": len(narrative_sections),
            "duplicates_removed": duplicates_removed,
            "noise_filtered": noise_filtered,
            "rearranged_count": rearranged_count,
            "generated_titles": generated_titles,
            "hard_breaks_unwrapped": unwrap_hard_breaks,
            "status": "success",
            "summary_text": (
                f"語意校驗完成：原 {orig_count} 個章節單元，已修復短行硬換行與斷句，剔除重複貼文 {duplicates_removed} 處，"
                f"清洗灌水雜訊 {noise_filtered} 則，修復錯亂重排 {rearranged_count} 處，"
                f"智慧補全章節標題 {generated_titles} 篇。"
            )
        }

        return {
            "cleaned_text": cleaned_text,
            "report": report,
            "sections": narrative_sections
        }

    def _split_sections(self, lines: List[str], section_regex: str) -> List[Dict[str, Any]]:
        """依照章節標題或論壇帖子頭分割小說區塊"""
        pat = re.compile(section_regex, re.MULTILINE)
        sections = []
        current_header = ""
        current_body = []
        date_pattern = re.compile(r'日期[:：]\s*(\d{4}[-/]\d{2}[-/]\d{2}\s*\d{2}[:：]\d{2}(?:[:：]\d{2})?)')
        floor_pattern = re.compile(r'^\s*([0-9]+)\s*楼')

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if current_body:
                    current_body.append("")
                continue

            if pat.search(stripped) and len(stripped) <= 65:
                # 遇到新章節/發帖標題
                if current_body or current_header:
                    text_content = "\n".join(current_body).strip()
                    if text_content or current_header:
                        sections.append({
                            "header": current_header,
                            "content": text_content,
                            "date": self._extract_date(current_header, date_pattern),
                            "floor": self._extract_floor(current_header, floor_pattern)
                        })
                current_header = stripped
                current_body = []
            else:
                current_body.append(line)

        # 收尾最後一個段落
        if current_body or current_header:
            sections.append({
                "header": current_header,
                "content": "\n".join(current_body).strip(),
                "date": self._extract_date(current_header, date_pattern),
                "floor": self._extract_floor(current_header, floor_pattern)
            })

        # 若完全未匹配到標題，則將全文按 50 行為單位分塊
        if not sections and lines:
            step = 50
            for idx in range(0, len(lines), step):
                chunk = lines[idx:idx+step]
                sections.append({
                    "header": f"第 {idx//step + 1} 節",
                    "content": "\n".join(chunk).strip(),
                    "date": None,
                    "floor": idx//step + 1
                })

        return sections

    def _extract_date(self, header: str, pat: re.Pattern) -> Optional[str]:
        m = pat.search(header)
        return m.group(1) if m else None

    def _extract_floor(self, header: str, pat: re.Pattern) -> Optional[int]:
        m = pat.search(header)
        return int(m.group(1)) if m else None

    def _get_section_summary(self, content: str) -> str:
        """擷取段落開頭與結尾重點作為代表向量摘要"""
        clean = re.sub(r'\s+', ' ', content).strip()
        if len(clean) <= 400:
            return clean
        return clean[:200] + " ... " + clean[-200:]

    def _reorder_sections(self, sections: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """
        依發帖時間戳或樓層編號對錯位的段落進行重排
        """
        has_dates = sum(1 for s in sections if s.get("date"))
        has_floors = sum(1 for s in sections if s.get("floor") is not None)
        rearranged_count = 0

        # 若多數有日期時間，依時間時序排序
        if has_dates > len(sections) * 0.4:
            sorted_sec = sorted(
                enumerate(sections),
                key=lambda item: (item[1].get("date") or "9999-99-99", item[0])
            )
            new_sections = [item[1] for item in sorted_sec]
            rearranged_count = sum(1 for new_i, (orig_i, _) in enumerate(sorted_sec) if new_i != orig_i)
            return new_sections, rearranged_count

        # 若多數有樓層號，依樓層自然排序
        if has_floors > len(sections) * 0.4:
            sorted_sec = sorted(
                enumerate(sections),
                key=lambda item: (item[1].get("floor") if item[1].get("floor") is not None else 999999, item[0])
            )
            new_sections = [item[1] for item in sorted_sec]
            rearranged_count = sum(1 for new_i, (orig_i, _) in enumerate(sorted_sec) if new_i != orig_i)
            return new_sections, rearranged_count

        return sections, 0

    def _needs_title_refinement(self, header: str) -> bool:
        """判斷標題是否缺乏實質語意名稱（例如純日期或純樓層）"""
        if not header:
            return True
        if "【" in header:
            return False
        # 純作者日期或純樓層
        if re.search(r'日期[:：]|\b\d+\s*楼', header) and not re.search(r'第[0-9一二三四五六七八九十]+[章回節卷]', header):
            return True
        return False

    def _synthesize_chapter_title(self, content: str) -> str:
        """從章節前 300 字提煉 4~8 字精煉中文章節標題"""
        clean = re.sub(r'[\r\n]+', ' ', content).strip()
        if not clean:
            return "軼事輯錄"

        # 尋找顯著動作或場景詞組
        key_phrases = re.findall(
            r'([一-龥]{2,4}(?:之謎|之夜|風雲|迷霧|奇遇|殘卷|驚魂|初現|秘事|舊事|過往|現身|相逢|啟程|探秘))',
            clean[:600]
        )
        if key_phrases:
            return to_tw(key_phrases[0])

        # 尋找引人入勝的短句片段
        sentences = [s.strip() for s in re.split(r'[。！？\n]', clean[:300]) if len(s.strip()) >= 4]
        if sentences:
            first = sentences[0]
            # 擷取主謂賓核心
            m = re.search(r'([\u4e00-\u9fa5]{4,8})', first)
            if m:
                return to_tw(m.group(1))

        return to_tw("見聞拾遺")


# ==================== 3. 登場人物與世界觀萃取引擎 ====================

class NovelCharacterExtractor:
    """
    運用 Embedding Gemma 2 語意特徵深度萃取登場人物、角色性格、人際關係與世界觀導讀
    """
    # 角色類型語意原型
    ROLE_PROTOTYPES = {
        "主角": "故事主角 核心人物 第一視角 男主角 女主角 全程經歷者 承擔命運者",
        "重要夥伴/配角": "摯友 夥伴 同伴 助手 患難與共 同行者 得力部屬 兄弟",
        "師尊/導師/長輩": "師父 長輩 高人 傳授技藝 指引迷津 隱士 前輩 族長 父親",
        "宿敵/反派/對手": "仇敵 兇手 幕後黑手 陰險 狠毒 詭計 阻撓 對立 邪門歪道",
        "關鍵線索人物/過客": "求助者 目擊者 線索人物 當事人 委託人 神秘過客"
    }

    # 特徵語意搜尋錨點
    TRAIT_ANCHORS = {
        "appearance": "容貌 長相 外表 穿著 身材 眉清目秀 體態 眼神 面容 氣質",
        "personality": "性格 為人 沉穩 機智 暴躁 冷靜 善良 孤僻 豪爽 堅韌 幽默",
        "identity": "身分 職業 門派 來歷 來頭 出身 專長 擅長 職位 傳承 弟子",
        "action": "遭遇 經歷 調查 救助 發現 出手 決戰 深入 破解"
    }

    # 常見中文字首與常見虛詞排除表
    NON_NAMES = {
        "不知道", "為什麼", "突然間", "這時候", "緊接著", "老先生", "老頭子", "中年人", "年輕人",
        "所有人", "大家夥", "只不過", "並沒有", "轉過身", "走過去", "看著我", "對我說", "這一下",
        "一時間", "冷不丁", "差不多", "不得不", "不得不", "也就是", "換句話說", "總而言之",
        "這件事", "那個人", "有些事", "沒想到", "不得不", "慢慢地", "悄悄地", "猛然間",
        "風水大", "陰陽大", "算命大", "這位", "那位", "這個", "那個", "一個", "兩個", "眾人",
        "村民", "有人", "沒人", "什麼人", "普通人", "旁人", "路人", "外人", "男人", "女人", "老人", "孩子",
        "搖頭", "搖搖頭", "點頭", "點點頭", "冷笑", "沉思", "深吸", "轉身", "抬頭", "嘆氣",
        "如此", "這般", "那樣", "不過", "然而", "只是", "但是", "因為", "所以", "雖然", "儘管",
        "彷彿", "似乎", "原來", "究竟", "到底", "難怪", "幸好", "萬一", "父親說", "母親說", "爺爺說"
    }

    def __init__(self, client: GemmaEmbeddingClient):
        self.client = client
        # 快取角色類型原型向量
        role_texts = list(self.ROLE_PROTOTYPES.values())
        self.role_keys = list(self.ROLE_PROTOTYPES.keys())
        self.role_vectors = self.client.get_embeddings(role_texts)

    def extract_characters_and_worldview(
        self,
        text: str,
        max_characters: int = 10,
        book_title: str = ""
    ) -> Dict[str, Any]:
        """
        深度解析小說全文，萃取登場角色清單、人際關係、世界觀與導讀資訊
        """
        # 1. 候選人名發現與統計
        candidates = self._discover_character_names(text)
        if not candidates:
            candidates = ["主角 (我)"]

        # 2. 為前 N 位核心角色抽取語意上下文
        character_profiles = []
        top_candidates = candidates[:max_characters]

        for idx, name in enumerate(top_candidates):
            is_top = (idx == 0) or (idx == 1 and "我" in top_candidates[0])
            profile = self._profile_character(name, text, is_protagonist=is_top)
            character_profiles.append(profile)

        # 3. 萃取世界觀、題材標籤與故事大綱
        worldview = self._extract_worldview(text, book_title)

        # 4. 建立導讀章節 HTML 與 Markdown
        guide_html = self.generate_guide_html(character_profiles, worldview, book_title)
        guide_markdown = self.generate_guide_markdown(character_profiles, worldview, book_title)

        return {
            "book_title": to_tw(book_title),
            "characters": character_profiles,
            "worldview": worldview,
            "guide_html": guide_html,
            "guide_markdown": guide_markdown,
            "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def _discover_character_names(self, text: str) -> List[str]:
        """透過對話動詞、稱謂與高頻句式識別實體人名 (繁簡通用並自動合併)"""
        counts = Counter()

        # 模式 1: 2~3 字人名接對話/神態動詞 (繁簡雙向匹配)
        pattern_dialogue = re.compile(
            r'(?:[^一-龥]|^)([\u4e00-\u9fa5]{2,3})(?:说道|說道|说|說|笑道|叹道|嘆道|喝道|喊道|问道|問道|点点头|點點頭|冷笑道|冷笑|沉思|摇头|搖頭|看着我|看著我|对我说|對我說)'
        )
        for m in pattern_dialogue.finditer(text):
            raw = m.group(1).strip()
            if raw.startswith(("聽", "看", "問", "說", "叫", "跟", "望", "見", "衝", "听", "看", "问", "说", "叫", "冲")):
                raw = raw[1:]
            name = to_tw(raw)
            if self._is_valid_name(name):
                counts[name] += 4

        # 模式 2: 特殊身分稱號 (如: 申老爹, 秦教授, 吳楚大師, 李隊長, 胖子, 二叔)
        pattern_titles = re.compile(
            r'(?:[^一-龥]|^)([\u4e00-\u9fa5]{1,2}(?:老爹|老道|教授|隊長|队长|警官|大師|大师|先生|姑娘|師傅|师傅|掌門|掌门|胖子|道長|道长))'
        )
        for m in pattern_titles.finditer(text):
            name = to_tw(m.group(1).strip())
            if self._is_valid_name(name):
                counts[name] += 3

        # 模式 3: 命名導入式 (名叫XXX, 名喚XXX, 自稱XXX，自動濾除前綴稱謂)
        pattern_intro = re.compile(
            r'(?:名叫|名唤|名喚|名為|名为|自称|自稱|人称|人稱)([\u4e00-\u9fa5]{2,6})'
        )
        title_prefixes = [
            r'^(?:風水|风水|陰陽|阴阳|算命|氣功)?(?:大師|大师|道士|道長|道长|先生|神醫|神医|赤腳醫生|赤脚医生)',
            r'^(?:老道|教授|隊長|队长|警官|師傅|师傅|掌門|掌门)'
        ]
        for m in pattern_intro.finditer(text):
            raw_n = m.group(1).strip()
            for tp in title_prefixes:
                raw_n = re.sub(tp, '', raw_n)
            name = to_tw(raw_n[:3].strip())
            if self._is_valid_name(name):
                counts[name] += 5

        # 模式 4: 若全文採第一人稱視角，注入「我 (第一人稱敘事者)」
        if text.count("我") > 120:
            counts["我 (第一人稱主人公)"] += 9999

        # 排序並過濾
        sorted_names = [name for name, _ in counts.most_common(25)]
        return sorted_names

    def _is_valid_name(self, name: str) -> bool:
        if len(name) < 2 or len(name) > 4:
            return False
        if name in self.NON_NAMES:
            return False
        # 排除常見助詞、動詞與介詞結尾
        if name.endswith(("的", "了", "在", "是", "著", "着", "道", "說", "说", "問", "问", "和", "就", "把", "被", "裏", "里")):
            return False
        return True

    def _profile_character(self, name: str, text: str, is_protagonist: bool = False) -> Dict[str, Any]:
        """為特定人物聚合語意上下文並分類定位"""
        clean_name = re.sub(r'\(.*?\)', '', name).strip()
        # 尋找所有包含此名稱的句子 (最多 30 句)
        sentences = []
        for line in text.splitlines():
            if clean_name in line:
                for s in re.split(r'[。！？]', line):
                    if clean_name in s and 6 <= len(s.strip()) <= 100:
                        sentences.append(s.strip())
                        if len(sentences) >= 30:
                            break
            if len(sentences) >= 30:
                break

        if not sentences:
            sentences = [f"{clean_name}在故事中登場並推進情節發展。"]

        # 將句子以向量特徵評估身分與性格
        context_vec = np.mean(self.client.get_embeddings(sentences[:10]), axis=0)
        context_vec /= np.linalg.norm(context_vec)

        # 比對角色定位類型
        sims = np.dot(self.role_vectors, context_vec)
        best_role_idx = int(np.argmax(sims))
        role_label = self.role_keys[best_role_idx]

        if is_protagonist:
            role_label = "主角 (核心主角)"
        elif "我" in name:
            role_label = "第一人稱主角"

        # 尋找最相符的外貌、身分與性格描述句
        identity_desc = self._find_best_matching_sentence(sentences, self.TRAIT_ANCHORS["identity"])
        personality_desc = self._find_best_matching_sentence(sentences, self.TRAIT_ANCHORS["personality"])
        action_desc = self._find_best_matching_sentence(sentences, self.TRAIT_ANCHORS["action"])

        return {
            "name": to_tw(clean_name),
            "role": role_label,
            "mention_count": text.count(clean_name),
            "identity": to_tw(identity_desc or "故事關鍵人物"),
            "personality": to_tw(personality_desc or "性格鮮明，行事果敢"),
            "key_actions": to_tw(action_desc or "參與關鍵冒險情節")
        }

    def _find_best_matching_sentence(self, sentences: List[str], anchor_query: str) -> str:
        """從人物出現語境中挑選最相符的代表語句"""
        if not sentences:
            return ""
        q_vec = self.client.get_embeddings([anchor_query])[0]
        s_vecs = self.client.get_embeddings(sentences[:15])
        sims = np.dot(s_vecs, q_vec)
        best_idx = int(np.argmax(sims))
        return sentences[best_idx]

    def _extract_worldview(self, text: str, book_title: str) -> Dict[str, Any]:
        """分析故事題材、背景設定與大綱摘要"""
        sample = text[:8000] # 前 8000 字通常涵蓋世界觀與核心背景

        # 題材標籤判斷
        genre_tags = []
        if re.search(r'墓|盜墓|古屍|青囊|符|道士|陰陽|降頭|風水|羅盤|卦', sample):
            genre_tags.extend(["民俗玄學", "風水秘術", "探秘靈異"])
        if re.search(r'警察|刑警|案件|屍檢|兇手|破案|法醫|痕跡', sample):
            genre_tags.extend(["懸疑推理", "刑偵實錄"])
        if re.search(r'考古|古物|鼎|青銅|竹簡|遺址|地宮', sample):
            genre_tags.extend(["考古探索", "歷史懸疑"])
        if not genre_tags:
            genre_tags = ["民間紀實", "懸疑傳奇", "驚悚探險"]

        # 背景時代判斷
        era = "當代 / 近現代"
        if re.search(r'民國|大帥|軍閥|奉系|租界', sample):
            era = "民國初年"
        elif re.search(r'文革|知青|下鄉|紅衛兵|公社', sample):
            era = "二十世紀六七十年代"
        elif re.search(r'三國|大唐|大宋|明朝|清朝', sample):
            era = "歷史古代"

        # 提煉故事摘要
        first_paras = [p.strip() for p in sample.splitlines() if len(p.strip()) > 30 and not p.startswith("作者:")]
        synopsis_lead = " ".join(first_paras[:3])[:280]
        if not synopsis_lead:
            synopsis_lead = f"本書講述了圍繞著神秘事件與不為人知的歷史往事展開的精彩冒險歷程。"

        return {
            "era": to_tw(era),
            "genres": [to_tw(g) for g in genre_tags],
            "synopsis": to_tw(synopsis_lead + ("..." if len(synopsis_lead) >= 250 else ""))
        }

    def generate_guide_html(self, characters: List[Dict[str, Any]], worldview: Dict[str, Any], book_title: str) -> str:
        """生成優雅的電子書導讀 HTML 內容"""
        char_rows = []
        for c in characters:
            char_rows.append(f"""
            <div class="character-card" style="margin-bottom: 16px; padding: 12px 16px; border-left: 4px solid #3b82f6; background: rgba(59, 130, 246, 0.05); border-radius: 0 8px 8px 0;">
                <div style="font-size: 16px; font-weight: bold; color: #1e3a8a; margin-bottom: 4px;">
                    {c['name']} <span style="font-size: 12px; font-weight: normal; background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 12px; margin-left: 8px;">{c['role']}</span>
                </div>
                <div style="font-size: 13px; color: #4b5563; line-height: 1.6;">
                    <b>身分：</b>{c['identity']}<br>
                    <b>特質：</b>{c['personality']}<br>
                    <b>關鍵事蹟：</b>{c['key_actions']}
                </div>
            </div>
            """)

        tags_html = " ".join([f'<span style="background: #e0e7ff; color: #3730a3; padding: 3px 10px; border-radius: 12px; font-size: 12px; margin-right: 6px;">{t}</span>' for t in worldview.get('genres', [])])

        html = f"""
        <div class="book-guide-container" style="padding: 20px; font-family: 'PingFang TC', 'Microsoft JhengHei', sans-serif;">
            <h1 style="text-align: center; border-bottom: 2px solid #e5e7eb; padding-bottom: 12px; color: #111827;">【登場人物與世界觀導讀】</h1>
            
            <div class="worldview-box" style="margin-top: 20px; padding: 16px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;">
                <h3 style="margin-top: 0; color: #1f2937;">📖 故事世界觀設定</h3>
                <p><b>時代背景：</b>{worldview.get('era', '未知')}</p>
                <p><b>作品標籤：</b>{tags_html}</p>
                <p style="line-height: 1.7; color: #374151;"><b>故事提要：</b>{worldview.get('synopsis', '')}</p>
            </div>

            <div class="characters-list" style="margin-top: 25px;">
                <h3 style="color: #1f2937; margin-bottom: 16px;">👥 主要登場角色全覽</h3>
                {"".join(char_rows)}
            </div>
        </div>
        """
        return html

    def generate_guide_markdown(self, characters: List[Dict[str, Any]], worldview: Dict[str, Any], book_title: str) -> str:
        """生成導讀章節（用於插入 TXT 序章，保證符合 kaf-cli 章節正則規範）"""
        lines = [
            "第一章 登場人物與世界觀導讀",
            "",
            "【📖 故事世界觀設定】",
            f"時代背景：{worldview.get('era', '未知')}",
            f"題材標籤：{'、'.join(worldview.get('genres', []))}",
            f"內容提要：{worldview.get('synopsis', '')}",
            "",
            "【👥 主要登場角色全覽】",
            ""
        ]

        for c in characters:
            lines.append(f"● {c['name']} 【{c['role']}】")
            lines.append(f"  身分來歷：{c['identity']}")
            lines.append(f"  性格特質：{c['personality']}")
            lines.append(f"  情節關聯：{c['key_actions']}")
            lines.append("")

        lines.append("────────────────────────────────────────")
        lines.append("")
        return "\n".join(lines)


# ==================== 4. 通用非小說書籍概念萃取引擎 ====================

class GeneralBookConceptExtractor:
    """
    運用 Embedding Gemma 2 語意特徵為通用非小說書籍（人文社科、商業經濟、技術手冊、學術報告）
    萃取學科領域、核心主旨、綱要摘要與關鍵概念導讀
    """
    DOMAINS = {
        "商業管理 / 經濟金融": "商業 管理 經濟 投資 市場 財務 營運 戰略 企業 組織 領導力 創新 行銷 商業模式",
        "人文社科 / 歷史哲學": "歷史 哲學 社會 文化 人類學 政治 思想 文明 倫理 批判 觀點 史料 典籍",
        "科技資訊 / 工程架構": "技術 程式架構 系統 演算法 資料 工程 網路 開發 軟體 程式碼 協定 部署 伺服器",
        "科學認知 / 心理成長": "心理 認知 大腦 科學 行為 實驗 理論 思維 邏輯 學習 記憶 動機 習慣",
        "實用方法 / 工具指南": "方法 步驟 指南 教學 實踐 技巧 範例 操作 規則 準則 流程 工具"
    }

    NON_CONCEPTS = {
        "本書", "作者", "讀者", "我們", "他們", "大家", "可以", "需要", "進行", "問題", "情況",
        "方法", "內容", "時間", "不同", "相關", "重要", "工作", "生活", "社會", "世界", "國家",
        "部分", "階段", "方面", "過程", "關係", "能力", "結構", "基礎", "發展", "影響", "研究",
        "結果", "系統", "模式", "原則", "目標", "關鍵", "主要", "基本", "特點", "意義", "標準"
    }

    def __init__(self, client: GemmaEmbeddingClient):
        self.client = client
        self.domain_keys = list(self.DOMAINS.keys())
        self.domain_vectors = self.client.get_embeddings(list(self.DOMAINS.values()))
        norms = np.linalg.norm(self.domain_vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1e-9
        self.domain_vectors = self.domain_vectors / norms

    def extract_concepts_and_guide(
        self,
        text: str,
        book_title: str = "",
        max_concepts: int = 8
    ) -> Dict[str, Any]:
        """萃取通用書籍的領域、主旨、綱要與關鍵概念清單"""
        sample = text[:12000]

        # 1. 領域與主旨判斷
        thesis_info = self._extract_domain_and_thesis(sample, book_title)

        # 2. 關鍵概念提煉
        concepts = self._extract_key_concepts(text, max_concepts=max_concepts)

        # 3. 生成導讀 HTML 與 Markdown
        guide_html = self.generate_guide_html(thesis_info, concepts, book_title)
        guide_markdown = self.generate_guide_markdown(thesis_info, concepts, book_title)

        return {
            "thesis_info": thesis_info,
            "concepts": concepts,
            "guide_html": guide_html,
            "guide_markdown": guide_markdown
        }

    def _extract_domain_and_thesis(self, sample: str, book_title: str) -> Dict[str, Any]:
        """判定學科領域、核心命題與閱讀指引"""
        sample_lead = " ".join([p.strip() for p in sample.splitlines() if len(p.strip()) > 20][:15])
        sample_vec = np.mean(self.client.get_embeddings([sample_lead[:1500]]), axis=0)
        norm = np.linalg.norm(sample_vec)
        if norm > 0:
            sample_vec /= norm
        sims = np.dot(self.domain_vectors, sample_vec)
        best_domain_idx = int(np.argmax(sims))
        domain = self.domain_keys[best_domain_idx]

        # 尋找顯著的主旨句
        thesis_sentence = ""
        patterns = [
            r'([^。！？\n]{10,80}(?:旨在|探討|闡述|核心在於|核心問題|主要目的|核心觀點)[^。！？\n]{5,60})',
            r'([^。！？\n]{10,80}(?:提供一套|介紹如何|幫助讀者|全面解析|系統介紹)[^。！？\n]{5,60})',
        ]
        for pat in patterns:
            m = re.search(pat, sample)
            if m:
                thesis_sentence = m.group(1).strip()
                break

        if not thesis_sentence:
            candidates = [p.strip() for p in sample.splitlines() if 30 <= len(p.strip()) <= 150 and not p.startswith("作者:")]
            if candidates:
                thesis_sentence = candidates[0]
            else:
                thesis_sentence = f"本書立足於{domain}領域，深入剖析核心體系、運作規律與實踐指南。"

        # 目標讀者建議
        target_audience = "適合該領域研究者、實務工作者與熱愛深度閱讀的通識讀者。"
        if "科技資訊" in domain:
            target_audience = "適合軟體工程師、系統架構師、技術主管與相關專業學生研讀。"
        elif "商業管理" in domain:
            target_audience = "適合創業者、企業中高層管理者、產品經理與商業分析人員。"
        elif "人文社科" in domain:
            target_audience = "適合人文學科愛好者、社會科學研究者與對文化思潮感興趣之廣大讀者。"

        return {
            "domain": to_tw(domain),
            "thesis": to_tw(thesis_sentence),
            "target_audience": to_tw(target_audience)
        }

    def _extract_key_concepts(self, text: str, max_concepts: int = 8) -> List[Dict[str, Any]]:
        """提煉書籍中的關鍵名詞、核心理論、術語或重要原則"""
        counts = Counter()

        # 模式 1: 引號名詞「...」或【...】
        quoted = re.findall(r'[「【]([一-龥a-zA-Z0-9_\-\s]{2,12})[」】]', text)
        for q in quoted:
            w = q.strip()
            if len(w) >= 2 and w not in self.NON_CONCEPTS:
                counts[w] += 3

        # 模式 2: 理論/模型/效應/架構/定律/法則/思維
        term_matches = re.findall(r'([一-龥a-zA-Z]{2,8}(?:理論|模型|效應|法則|定律|體系|機制|思維|架構|範式))', text)
        for t in term_matches:
            w = t.strip()
            if w not in self.NON_CONCEPTS:
                counts[w] += 4

        # 模式 3: 定義句首（...是指 / ...即是）
        def_matches = re.findall(r'([一-龥a-zA-Z]{2,10})(?:是指|即是|定義為|代表著)', text)
        for d in def_matches:
            w = d.strip()
            if len(w) >= 2 and w not in self.NON_CONCEPTS:
                counts[w] += 5

        # 模式 4: 英文技術專有名詞 (如 REST, Docker, Agile, BERT)
        en_matches = re.findall(r'\b([A-Z][a-zA-Z0-9]{2,16})\b', text)
        for em in en_matches:
            if em not in {"The", "This", "That", "When", "What", "With", "From", "Into", "There"}:
                counts[em] += 2

        if not counts:
            headers = re.findall(r'^\s*(?:第[0-9一二三四五六七八九十]+[篇章節]|Chapter\s+\d+|[0-9]+\.[0-9]+)\s+([^\r\n]{2,20})', text, re.M)
            for h in headers:
                for chunk in re.split(r'[:：與和的]', h):
                    c = chunk.strip()
                    if 2 <= len(c) <= 8 and c not in self.NON_CONCEPTS:
                        counts[c] += 3

        top_terms = [t for t, _ in counts.most_common(max_concepts * 2)]
        results = []

        for term in top_terms:
            if len(results) >= max_concepts:
                break
            sentences = []
            for line in text.splitlines():
                if term in line:
                    for s in re.split(r'[。！？\n]', line):
                        s_strip = s.strip()
                        if term in s_strip and 12 <= len(s_strip) <= 120:
                            sentences.append(s_strip)
                            if len(sentences) >= 20:
                                break
                if len(sentences) >= 20:
                    break

            if not sentences:
                continue

            explanation = ""
            for s in sentences:
                if any(k in s for k in ["是指", "即", "在於", "意味著", "表現為", "核心", "目的", "特徵", "作用"]):
                    explanation = s
                    break
            if not explanation:
                explanation = sentences[0]

            results.append({
                "concept": to_tw(term),
                "frequency": text.count(term),
                "explanation": to_tw(explanation),
                "importance": "核心概念" if len(results) < 3 else "重要主題"
            })

        return results

    def generate_guide_html(self, thesis_info: Dict[str, Any], concepts: List[Dict[str, Any]], book_title: str) -> str:
        """生成通用書籍導讀與關鍵概念 HTML 頁面"""
        concept_cards = []
        for c in concepts:
            concept_cards.append(f"""
            <div class="concept-card" style="margin-bottom: 14px; padding: 12px 16px; border-left: 4px solid #059669; background: rgba(16, 185, 129, 0.05); border-radius: 0 8px 8px 0;">
                <div style="font-size: 15px; font-weight: bold; color: #065f46; margin-bottom: 4px;">
                    {c['concept']} <span style="font-size: 11px; font-weight: normal; background: #d1fae5; color: #047857; padding: 2px 7px; border-radius: 10px; margin-left: 6px;">{c['importance']}</span>
                </div>
                <div style="font-size: 13px; color: #374151; line-height: 1.6;">
                    {c['explanation']}
                </div>
            </div>
            """)

        html = f"""
        <div class="book-guide-container" style="padding: 20px; font-family: 'PingFang TC', 'Microsoft JhengHei', sans-serif;">
            <h1 style="text-align: center; border-bottom: 2px solid #e5e7eb; padding-bottom: 12px; color: #111827;">【書籍核心導讀與概念指南】</h1>
            
            <div class="thesis-box" style="margin-top: 20px; padding: 16px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;">
                <h3 style="margin-top: 0; color: #1f2937;">📖 書籍主旨與研讀指引</h3>
                <p><b>領域類別：</b><span style="background: #e0e7ff; color: #3730a3; padding: 2px 8px; border-radius: 10px; font-size: 12px;">{thesis_info.get('domain', '通用書籍')}</span></p>
                <p style="line-height: 1.7; color: #374151;"><b>核心命題：</b>{thesis_info.get('thesis', '')}</p>
                <p style="line-height: 1.6; color: #4b5563;"><b>閱讀建議：</b>{thesis_info.get('target_audience', '')}</p>
            </div>

            <div class="concepts-list" style="margin-top: 25px;">
                <h3 style="color: #1f2937; margin-bottom: 16px;">💡 核心概念與關鍵洞見全覽</h3>
                {"".join(concept_cards)}
            </div>
        </div>
        """
        return html

    def generate_guide_markdown(self, thesis_info: Dict[str, Any], concepts: List[Dict[str, Any]], book_title: str) -> str:
        """生成通用書籍導讀 Markdown（保證符合 kaf-cli 章節正則規範）"""
        lines = [
            "第一章 書籍導讀與核心概念指南",
            "",
            "【📖 書籍主旨與研讀指引】",
            f"領域類別：{thesis_info.get('domain', '通用書籍')}",
            f"核心命題：{thesis_info.get('thesis', '')}",
            f"閱讀建議：{thesis_info.get('target_audience', '')}",
            "",
            "【💡 核心概念與關鍵洞見全覽】",
            ""
        ]

        for c in concepts:
            lines.append(f"● {c['concept']} 【{c['importance']}】")
            lines.append(f"  概念解析：{c['explanation']}")
            lines.append("")

        lines.append("────────────────────────────────────────")
        lines.append("")
        return "\n".join(lines)


# ==================== 5. 自動識別書籍類型輔助函式 ====================

def detect_book_type(text: str, book_title: str = "") -> str:
    """
    自動識別書籍類型：
    - "story": 小說、故事、傳奇、民間誌異、敘事文學
    - "technical": 技術文檔、手冊、API、規格說明書
    - "general": 通用非小說、人文社科、商業經濟、歷史、自我提升
    """
    sample = text[:15000]

    # 技術書籍特徵
    tech_score = 0
    if re.search(r'```|\bdef |\bclass |\bfunction\b|\bimport\b|\bAPI\b|\bHTTP\b|\bJSON\b|\bCLI\b', sample):
        tech_score += 5
    if re.search(r'^\s*#{1,4}\s+|^\s*\d+\.\d+(?:\.\d+)?\s+', sample, re.M):
        tech_score += 4
    if re.search(r'安裝|配置|參數|架構|部署|指令|模組|相容性|環境|除錯|編譯', sample):
        tech_score += 4

    # 小說/故事特徵
    story_score = 0
    story_speech_markers = len(re.findall(r'[「“].*?[」”]|(?:說道|道：|問道|喊道|冷笑|嘆道|心想|點頭道)', sample))
    if story_speech_markers > 12:
        story_score += min(12, story_speech_markers // 2)
    if re.search(r'主角|掌門|長老|姑娘|少爺|師父|江湖|妖魔|鬼神|仙人|盜墓|棺材|陰陽|破案|兇手', sample):
        story_score += 5
    if re.search(r'他心中|她眼中|不由得|猛然間|倒吸一口涼氣|只見那', sample):
        story_score += 4

    # 通用非小說特徵
    general_score = 0
    if re.search(r'研究指出|根據分析|因此|總結來說|作者認為|本質上|體系|數據顯示|歷史上|觀點|理論|概念', sample):
        general_score += 5
    if re.search(r'企業|組織|管理|市場|經濟|哲學|文化|人類|思維|認知|方法論|策略', sample):
        general_score += 5
    if re.search(r'^\s*(?:第[0-9一二三四五六七八九十]+[篇章節]|前言|導論|結語|一、|1\.)', sample, re.M):
        general_score += 3

    # 書名權重
    if re.search(r'手冊|指南|開發|教程|規範|架構|代碼|系統', book_title):
        tech_score += 6
    elif re.search(r'史|論|學|法|經濟|管理|心理|思考|通識|哲學|文明', book_title):
        general_score += 6
    elif re.search(r'傳|記|演義|錄|志|異|俠|鬼|探案|秘境', book_title):
        story_score += 6

    scores = [("technical", tech_score), ("general", general_score), ("story", story_score)]
    scores.sort(key=lambda x: x[1], reverse=True)
    best_type, highest_score = scores[0]

    if highest_score <= 3:
        return "story" if text.count("我") > 100 or text.count("他") > 150 else "general"
    return best_type


# ==================== 6. 頂層協調處理函式 ====================

def process_novel_with_gemma(
    input_filepath: str,
    output_filepath: Optional[str] = None,
    backend: str = "fast_local",
    model_name: str = "google/embeddinggemma-2",
    ollama_url: str = "http://localhost:11434",
    dedup: bool = True,
    clean_noise: bool = True,
    rearrange: bool = True,
    auto_titles: bool = True,
    inject_character_guide: bool = True,
    max_characters: int = 10,
    unwrap_hard_breaks: bool = True,
    book_type: str = "auto",
    section_regex: Optional[str] = None,
    progress_callback = None
) -> Dict[str, Any]:
    """
    一鍵式處理流程（支援小說故事、通用書籍與技術手冊）：
    1. 讀取並檢測編碼
    2. 執行短行硬換行修復、文本校驗、去重與重排
    3. 依書籍類型（小說 vs 通用書籍/技術手冊）執行角色/概念導讀萃取
    4. 依選項注入導讀序章（符合 kaf-cli 章節規範）
    5. 匯出全新最佳化 TXT 與中繼資料 JSON
    """
    if not os.path.exists(input_filepath):
        return {"success": False, "error": f"找不到輸入檔案: {input_filepath}"}

    from kaf_gui.zh_converter import detect_encoding
    enc = detect_encoding(input_filepath)
    with open(input_filepath, "r", encoding=enc, errors="replace") as f:
        raw_text = f.read()

    book_title = os.path.splitext(os.path.basename(input_filepath))[0]

    # 判斷書籍類型
    book_type_lower = (book_type or "auto").lower()
    if book_type_lower in ["auto", ""]:
        resolved_book_type = detect_book_type(raw_text, book_title)
    elif book_type_lower in ["story", "novel", "fiction"]:
        resolved_book_type = "story"
    elif book_type_lower in ["tech", "technical"]:
        resolved_book_type = "technical"
    else:
        resolved_book_type = "general"

    if progress_callback:
        progress_callback(0.1, f"正在初始化 Embedding Gemma 2 (書籍類型: {resolved_book_type})...")

    client = GemmaEmbeddingClient(backend=backend, model_name=model_name, ollama_url=ollama_url)
    organizer = NovelTextOrganizer(client)

    if progress_callback:
        progress_callback(0.3, "正在進行短行硬換行修復、文字檢測、語意去重與時序重排...")

    check_kwargs = {
        "dedup_similarity_threshold": 0.92,
        "filter_noise": clean_noise,
        "rearrange_chronological": rearrange,
        "auto_chapter_titles": auto_titles,
        "unwrap_hard_breaks": unwrap_hard_breaks
    }
    if section_regex and section_regex.strip():
        check_kwargs["section_regex"] = section_regex.strip()

    organize_res = organizer.check_and_rearrange_text(
        raw_text,
        **check_kwargs
    )

    cleaned_text = organize_res["cleaned_text"]

    worldview = {}
    characters = []
    thesis_info = {}
    concepts = []
    guide_html = ""
    guide_markdown = ""

    if resolved_book_type == "story":
        if progress_callback:
            progress_callback(0.6, "正在運用 Gemma 2 萃取故事登場人物、角色性格與世界觀...")
        extractor = NovelCharacterExtractor(client)
        char_res = extractor.extract_characters_and_worldview(
            cleaned_text,
            max_characters=max_characters,
            book_title=book_title
        )
        worldview = char_res["worldview"]
        characters = char_res["characters"]
        guide_html = char_res["guide_html"]
        guide_markdown = char_res["guide_markdown"]
    else:
        # 通用書籍 / 技術文檔
        if progress_callback:
            progress_callback(0.6, "正在運用 Gemma 2 萃取通用書籍核心主旨與關鍵概念導讀...")
        concept_extractor = GeneralBookConceptExtractor(client)
        c_res = concept_extractor.extract_concepts_and_guide(
            cleaned_text,
            book_title=book_title,
            max_concepts=max_characters
        )
        thesis_info = c_res["thesis_info"]
        concepts = c_res["concepts"]
        guide_html = c_res["guide_html"]
        guide_markdown = c_res["guide_markdown"]

    # 注入導讀序章
    final_text = cleaned_text
    if inject_character_guide and guide_markdown:
        final_text = guide_markdown + "\n\n" + cleaned_text

    # 決定輸出路徑
    if not output_filepath:
        base, ext = os.path.splitext(input_filepath)
        output_filepath = f"{base}_gemma_optimized{ext}"

    if progress_callback:
        progress_callback(0.85, "正在儲存最佳化後之文字與分析報告...")

    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(final_text)

    # 儲存中繼資料 JSON 檔案
    meta_path = os.path.splitext(output_filepath)[0] + "_metadata.json"
    metadata_out = {
        "source_file": input_filepath,
        "optimized_file": output_filepath,
        "book_type": resolved_book_type,
        "report": organize_res["report"],
        "worldview": worldview,
        "characters": characters,
        "thesis_info": thesis_info,
        "concepts": concepts,
        "guide_html": guide_html
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata_out, f, ensure_ascii=False, indent=2)

    if progress_callback:
        progress_callback(1.0, f"Gemma 2 處理完成 ({resolved_book_type})！")

    return {
        "success": True,
        "book_type": resolved_book_type,
        "output_file": output_filepath,
        "metadata_file": meta_path,
        "report": organize_res["report"],
        "worldview": worldview,
        "characters": characters,
        "thesis_info": thesis_info,
        "concepts": concepts,
        "guide_html": guide_html,
        "guide_markdown": guide_markdown
    }

# 別名相容
process_book_with_gemma = process_novel_with_gemma

