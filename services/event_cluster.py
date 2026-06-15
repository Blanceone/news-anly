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
    def __init__(self, news_db=None, stocks_db=None):
        from config import Config
        self.news_db = news_db or Config.NEWS_DB
        self.stocks_db = stocks_db or Config.STOCKS_DB
        from core.db_init import init_stocks_db
        init_stocks_db()
        # 实例级 vectorizer，避免类级别共享导致状态污染
        self._vectorizer = TfidfVectorizer(analyzer='word', max_features=2000,
                                            sublinear_tf=True, token_pattern=r'(?u)\b\w+\b')
        # lazy load jieba dict
        jieba.initialize()

    def cluster_event(self, event_id: int, title: str, content: str = ""):
        """为新事件寻找匹配的簇，若未匹配则创建新簇（含生命周期管理）"""
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
                            cid = self._add_to_cluster(int(r["cluster_id"]), event_id)
                            if cid:
                                self._update_lifecycle(cid)
                            return cid
            except Exception:
                pass
        cid = self._create_cluster(event_id)
        if cid:
            self._set_birth(cid)
        return cid

    def _set_birth(self, cluster_id):
        with sqlite3.connect(self.stocks_db) as conn:
            conn.execute("""
                UPDATE event_cluster SET birth_time=CURRENT_TIMESTAMP, status='BIRTH'
                WHERE cluster_id=?
            """, (cluster_id,))
            conn.commit()
        self._set_cluster_heat(cluster_id)

    def _update_lifecycle(self, cluster_id):
        """根据event_count和时间更新生命周期状态"""
        import datetime
        now = datetime.datetime.now()
        with sqlite3.connect(self.stocks_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT event_count, first_seen, last_seen, status
                FROM event_cluster WHERE cluster_id=?
            """, (cluster_id,)).fetchone()
            if not row:
                return
            cnt = row["event_count"]
            first = datetime.datetime.fromisoformat(row["first_seen"]) if row["first_seen"] else now
            last = datetime.datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else now
            status = row["status"] or "BIRTH"
            hours_since_last = (now - last).total_seconds() / 3600
            hours_since_birth = (now - first).total_seconds() / 3600

            if cnt >= 10 and status in ("BIRTH", "GROWING", "PEAK"):
                new_status = "PEAK"
            elif cnt >= 3 and status in ("BIRTH", "GROWING"):
                new_status = "GROWING"
            elif hours_since_last > 72:
                new_status = "DEAD"
            elif hours_since_last > 24 and status not in ("DEAD",):
                new_status = "DECLINING"
            elif cnt >= 3 and status == "BIRTH":
                new_status = "GROWING"
            else:
                new_status = status

            updates = {"status": new_status}
            if new_status == "GROWING" and status == "BIRTH":
                pass  # growing starts from birth
            if new_status == "DECLINING" and status != "DECLINING":
                updates["decline_time"] = now.isoformat()

            if updates:
                set_clause = ", ".join(f"{k}=?" for k in updates)
                vals = list(updates.values()) + [cluster_id]
                conn.execute(f"UPDATE event_cluster SET {set_clause} WHERE cluster_id=?", vals)
                conn.commit()

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

    def _set_cluster_heat(self, cluster_id):
        """根据簇内事件评分更新 heat_score"""
        try:
            with sqlite3.connect(self.stocks_db) as conn:
                row = conn.execute("""
                    SELECT COALESCE(MAX(e.event_score), 0) as max_score,
                           COUNT(*) as cnt
                    FROM event_cluster_map m
                    JOIN event_analysis e ON m.event_id = e.event_id
                    WHERE m.cluster_id=?
                """, (cluster_id,)).fetchone()
                if row:
                    max_score = float(row[0]) if row[0] else 0
                    cnt = int(row[1]) if row[1] else 0
                    heat = min(100, max_score + cnt * 5)
                    conn.execute("UPDATE event_cluster SET heat_score=? WHERE cluster_id=?", (heat, cluster_id))
                    conn.commit()
        except Exception:
            pass

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
        self._set_cluster_heat(cluster_id)
        return cluster_id

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
