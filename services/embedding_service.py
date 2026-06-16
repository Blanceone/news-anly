"""Embedding Theme Match — Phase 9

为每个主题生成 TF-IDF 向量，用 cosine similarity 匹配新闻与主题，
解决"玻璃基板≈先进封装"但关键词不一致导致的漏匹配。

使用 sklearn TfidfVectorizer（本地计算，无需网络下载模型）。
"""
import sqlite3
import pickle
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

# 模块级单例缓存，避免每次调用重建 vectorizer
_singleton = None


def get_embedding_service(db_path=None):
    """获取 EmbeddingService 单例"""
    global _singleton
    if _singleton is None:
        _singleton = EmbeddingService(db_path)
    return _singleton


class EmbeddingService:
    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self._vectorizer = TfidfVectorizer(
            analyzer='char_wb',
            ngram_range=(2, 4),
            max_features=5000,
            sublinear_tf=True,
        )
        self._is_seeded = False

    def _build_theme_texts(self) -> list:
        """从 concept_board 表构建主题文本（优先），fallback 到旧 theme_stock_mapping"""
        result = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT concept_name, keywords FROM concept_board WHERE status='active'"
                ).fetchall()
                for r in rows:
                    name = r["concept_name"]
                    kws = r["keywords"] or ""
                    text = f"{name} {kws}"
                    result.append({"key": name, "name": name, "text": text})
        except Exception:
            pass
        # 如果概念树为空，从 theme_stock_mapping 构建
        if not result:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("""
                        SELECT DISTINCT theme_name FROM theme_stock_mapping
                    """).fetchall()
                    for r in rows:
                        name = r["theme_name"]
                        result.append({"key": name, "name": name, "text": name})
            except Exception:
                pass
        return result

    def seed_embeddings(self):
        """TF-IDF fit + 持久化向量到 theme_embedding 表"""
        themes = self._build_theme_texts()
        texts = [t["text"] for t in themes]
        vecs = self._vectorizer.fit_transform(texts).toarray()
        with sqlite3.connect(self.db_path) as conn:
            for t, vec in zip(themes, vecs):
                conn.execute("""
                    INSERT OR REPLACE INTO theme_embedding (theme_name, description, embedding)
                    VALUES (?, ?, ?)
                """, (t["name"], t["text"], pickle.dumps(vec)))
            conn.commit()
        self._is_seeded = True
        print(f"  [Embedding] 已生成 {len(themes)} 个主题的 TF-IDF 向量")

    def match(self, text: str, top_k: int = 5, threshold: float = 0.15) -> list:
        """计算文本与所有主题的 cosine similarity"""
        rows = self._load_embeddings()
        if not rows:
            return []
        if not self._is_seeded:
            self._vectorizer.fit([r[1] for r in rows])
            self._is_seeded = True
        text_vec = self._vectorizer.transform([text]).toarray()[0]
        norm_t = np.linalg.norm(text_vec)
        if norm_t == 0:
            return []
        text_vec = text_vec / norm_t
        results = []
        for theme_name, desc, blob in rows:
            theme_vec = pickle.loads(blob)
            norm_s = np.linalg.norm(theme_vec)
            if norm_s == 0:
                continue
            theme_vec = theme_vec / norm_s
            sim = float(np.dot(text_vec, theme_vec))
            if sim >= threshold:
                results.append({"theme_name": theme_name, "similarity": round(sim, 4)})
        results.sort(key=lambda x: -x["similarity"])
        return results[:top_k]

    def _load_embeddings(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT theme_name, description, embedding FROM theme_embedding"
                ).fetchall()
                return rows
        except Exception:
            return []

    def match_event(self, keywords: list, industry: str = "", sub_industry: str = "") -> list:
        """将事件的关键词+行业拼接为文本，匹配最相似的主题"""
        text = f"{industry} {sub_industry} {' '.join(keywords)}".strip()
        if not text:
            return []
        return self.match(text, top_k=3, threshold=0.15)
