"""Event Clustering Engine — Phase 10

同一事件的多次报道（如"华为发布韬定律"→"机构解读"→"市场关注"）
通过 jieba 分词 + TF-IDF + cosine similarity 聚类，防止重复加分。
"""
import re
import sqlite3
from datetime import datetime

import jieba
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


def _tokenize(text):
    """jieba 分词 + 过滤单字"""
    return " ".join(w for w in jieba.cut(text) if len(w.strip()) > 1)


class EventClustering:
    _vectorizer = TfidfVectorizer(analyzer='word', max_features=2000,
                                   sublinear_tf=True, token_pattern=r'(?u)\b\w+\b')

    def __init__(self, news_db=None, stocks_db=None):
        from config import Config
        self.news_db = news_db or Config.NEWS_DB
        self.stocks_db = stocks_db or Config.STOCKS_DB
        from core.db_init import init_stocks_db
        init_stocks_db()
        # lazy load jieba dict
        jieba.initialize()

    def cluster_event(self, event_id: int, title: str, content: str = ""):
        """为新事件寻找匹配的簇，若未匹配则创建新簇"""
        text = f"{title} {content}"[:500]
        if not text.strip():
            return None
        recent = self._get_recent_events(hours=48)
        if recent:
            texts = [r["text"] for r in recent]
            tok_texts = [_tokenize(t) for t in texts]
            tok_text = _tokenize(text)
            try:
                vecs = self._vectorizer.fit_transform(tok_texts + [tok_text]).toarray()
                new_vec = vecs[-1]
                norm = np.linalg.norm(new_vec)
                if norm > 0:
                    new_vec = new_vec / norm
                    for i, r in enumerate(recent):
                        old_vec = vecs[i]
                        onorm = np.linalg.norm(old_vec)
                        if onorm == 0:
                            continue
                        sim = float(np.dot(new_vec, old_vec / onorm))
                        if sim >= 0.3:
                            self._add_to_cluster(r["cluster_id"], event_id)
                            return r["cluster_id"]
            except Exception:
                pass
        return self._create_cluster(event_id)

    def _get_recent_events(self, hours=48):
        try:
            with sqlite3.connect(self.news_db) as conn:
                conn.row_factory = sqlite3.Row
                since = (datetime.now().timestamp() - hours * 3600)
                rows = conn.execute("""
                    SELECT e.event_id, n.title, n.content,
                           COALESCE(ec.cluster_id, 0) as cluster_id
                    FROM event_analysis e
                    JOIN news n ON e.source_id = n.id
                    LEFT JOIN event_cluster_map ec ON e.event_id = ec.event_id
                    WHERE e.created_at > datetime(?, 'unixepoch')
                    ORDER BY e.created_at DESC LIMIT 100
                """, (since,)).fetchall()
                return [{"event_id": r["event_id"],
                         "text": f"{r['title']} {r.get('content','')}",
                         "cluster_id": r["cluster_id"] or 0}
                        for r in rows]
        except Exception:
            return []

    def _create_cluster(self, event_id):
        with sqlite3.connect(self.stocks_db) as conn:
            conn.execute("""
                INSERT INTO event_cluster (main_event_id, event_count, first_seen, last_seen)
                VALUES (?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (event_id,))
            cluster_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("""
                INSERT INTO event_cluster_map (cluster_id, event_id) VALUES (?, ?)
            """, (cluster_id, event_id))
            conn.commit()
            return cluster_id

    def _add_to_cluster(self, cluster_id, event_id):
        with sqlite3.connect(self.stocks_db) as conn:
            conn.execute("""
                INSERT OR IGNORE INTO event_cluster_map (cluster_id, event_id) VALUES (?, ?)
            """, (cluster_id, event_id))
            conn.execute("""
                UPDATE event_cluster
                SET event_count = event_count + 1, last_seen = CURRENT_TIMESTAMP
                WHERE cluster_id = ?
            """, (cluster_id,))
            conn.commit()

    def get_cluster_score(self, event_id):
        """获取事件所在簇的最高事件评分（去重用）"""
        try:
            with sqlite3.connect(self.stocks_db) as conn:
                row = conn.execute("""
                    SELECT MAX(e.event_score) as max_score
                    FROM event_cluster_map m
                    JOIN event_analysis e ON m.event_id = e.event_id
                    WHERE m.cluster_id = (
                        SELECT cluster_id FROM event_cluster_map WHERE event_id = ?
                    )
                """, (event_id,)).fetchone()
                return row[0] if row else None
        except Exception:
            return None
