"""概念发现引擎 — 管理概念候选池生命周期

Spec 4.3: 概念发现引擎
  check_upgrades():
    candidate → observing: mention_count >= 3 且 last_mention_date 在最近2天内
    observing → validated: 进入当日7信号验证流程 (由 Validator 触发)
"""
import sqlite3
from datetime import datetime, timedelta
from config import Config


class ConceptDiscovery:
    def __init__(self, concept_db=None):
        self.concept_db = concept_db or Config.CONCEPT_DB

    def check_upgrades(self) -> list:
        """遍历 concept_candidate 表，检查状态升级条件:
        - candidate → observing: mention_count >= 3 且 last_mention_date 在最近2天内
        """
        upgrades = []
        cutoff_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row

            # candidate → observing
            candidates = conn.execute("""
                SELECT id, standard_name, mention_count, last_mention_date
                FROM concept_candidate
                WHERE status='candidate'
                  AND mention_count >= 3
                  AND last_mention_date >= ?
            """, (cutoff_date,)).fetchall()

            for row in candidates:
                conn.execute("""
                    UPDATE concept_candidate SET status='observing'
                    WHERE id=?
                """, (row["id"],))
                upgrades.append({
                    "id": row["id"],
                    "standard_name": row["standard_name"],
                    "old_status": "candidate",
                    "new_status": "observing",
                    "mention_count": row["mention_count"],
                })

            conn.commit()
        return upgrades

    def get_concepts(self, status=None, limit=100) -> list:
        """查询概念候选池"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute("""
                    SELECT * FROM concept_candidate
                    WHERE status=?
                    ORDER BY mention_count DESC LIMIT ?
                """, (status, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM concept_candidate
                    ORDER BY mention_count DESC LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_concept_by_id(self, concept_id: int) -> dict:
        """获取单个概念详情"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM concept_candidate WHERE id=?",
                (concept_id,)
            ).fetchone()
            return dict(row) if row else {}

    def get_concept_events(self, concept_id: int) -> list:
        """获取概念关联的事件"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT ce.*, ea.event_type, ea.summary
                FROM concept_event ce
                JOIN event_analysis ea ON ce.event_id = ea.id
                WHERE ce.concept_id=?
                ORDER BY ce.trade_date DESC
            """, (concept_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_concept_stocks(self, concept_id: int) -> list:
        """获取概念关联的股票"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM concept_stock
                WHERE concept_id=?
                ORDER BY is_target DESC, role ASC
            """, (concept_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_dictionary(self) -> list:
        """获取概念词典"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM concept_dictionary WHERE status='active' ORDER BY standard_name"
            ).fetchall()
            return [dict(r) for r in rows]

    def add_to_dictionary(self, standard_name: str, aliases: list = None,
                          category: str = "") -> int:
        """添加概念到词典"""
        import json
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT OR IGNORE INTO concept_dictionary
                    (standard_name, aliases, category, status)
                VALUES (?, ?, ?, 'active')
            """, (standard_name,
                  json.dumps(aliases or [], ensure_ascii=False),
                  category))
            conn.commit()
            row = conn.execute(
                "SELECT id FROM concept_dictionary WHERE standard_name=?",
                (standard_name,)
            ).fetchone()
            return row[0] if row else 0
