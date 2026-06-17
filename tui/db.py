"""TUI 数据查询层 — 连接 news.db + concept.db"""
import sqlite3
from datetime import datetime, timedelta
from config import Config


class TuiDB:
    def __init__(self):
        self.news_db = Config.NEWS_DB
        self.concept_db = Config.CONCEPT_DB

    # ──────────────────────────────────────────
    # Dashboard (Tab 1)
    # ──────────────────────────────────────────

    def dashboard_stats(self) -> dict:
        """仪表盘统计"""
        stats = {}
        try:
            with sqlite3.connect(self.news_db) as conn:
                stats["news_total"] = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
                stats["news_today"] = conn.execute(
                    "SELECT COUNT(*) FROM news WHERE created_at > datetime('now', '-24 hours')"
                ).fetchone()[0]
                stats["events_total"] = conn.execute(
                    "SELECT COUNT(*) FROM event_analysis"
                ).fetchone()[0]
                stats["unanalyzed"] = conn.execute(
                    "SELECT COUNT(*) FROM news WHERE analyzed=0"
                ).fetchone()[0]
        except Exception:
            stats = {"news_total": 0, "news_today": 0, "events_total": 0, "unanalyzed": 0}

        try:
            with sqlite3.connect(self.concept_db) as conn:
                stats["concepts_total"] = conn.execute(
                    "SELECT COUNT(*) FROM concept_candidate WHERE lifecycle != 'DEAD'"
                ).fetchone()[0]
                stats["concepts_validated"] = conn.execute(
                    "SELECT COUNT(*) FROM concept_candidate WHERE status='validated'"
                ).fetchone()[0]
                stats["concepts_observing"] = conn.execute(
                    "SELECT COUNT(*) FROM concept_candidate WHERE status='observing'"
                ).fetchone()[0]
                stats["concepts_candidate"] = conn.execute(
                    "SELECT COUNT(*) FROM concept_candidate WHERE status='candidate'"
                ).fetchone()[0]
        except Exception:
            stats.update({"concepts_total": 0, "concepts_validated": 0,
                          "concepts_observing": 0, "concepts_candidate": 0})
        return stats

    def recent_news(self, limit=50) -> list:
        """最近新闻"""
        try:
            with sqlite3.connect(self.news_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT id, title, source_name, category, sentiment,
                           impact, freshness, analyzed, created_at
                    FROM news ORDER BY created_at DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def recent_events(self, limit=30) -> list:
        """最近事件"""
        try:
            with sqlite3.connect(self.news_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT e.*, n.title as news_title
                    FROM event_analysis e
                    LEFT JOIN news n ON e.source_id = n.id
                    ORDER BY e.created_at DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def sop_logs(self, limit=20) -> list:
        """SOP执行日志"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM sop_log ORDER BY started_at DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # ──────────────────────────────────────────
    # Concepts (Tab 2)
    # ──────────────────────────────────────────

    def concepts(self, status=None, limit=100) -> list:
        """概念候选池"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                if status:
                    rows = conn.execute("""
                        SELECT * FROM concept_candidate
                        WHERE status=? ORDER BY mention_count DESC LIMIT ?
                    """, (status, limit)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM concept_candidate
                        WHERE lifecycle != 'DEAD'
                        ORDER BY mention_count DESC LIMIT ?
                    """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def concept_detail(self, concept_id: str) -> dict:
        """概念详情"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM concept_candidate WHERE concept_id=?",
                    (concept_id,)
                ).fetchone()
                return dict(row) if row else {}
        except Exception:
            return {}

    def concept_events(self, concept_id: str) -> list:
        """概念关联事件"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM concept_event
                    WHERE concept_id=? ORDER BY created_at DESC
                """, (concept_id,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def concept_stocks(self, concept_id: str) -> list:
        """概念成分股"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM concept_stock
                    WHERE concept_id=? ORDER BY is_core DESC, role ASC
                """, (concept_id,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # ──────────────────────────────────────────
    # Validation (Tab 3)
    # ──────────────────────────────────────────

    def concept_validations(self, concept_id: str = None) -> list:
        """7信号验证结果"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                if concept_id:
                    rows = conn.execute("""
                        SELECT * FROM concept_validation
                        WHERE concept_id=? ORDER BY checked_at DESC
                    """, (concept_id,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT cv.*, cc.concept_name
                        FROM concept_validation cv
                        JOIN concept_candidate cc ON cv.concept_id = cc.concept_id
                        ORDER BY cv.checked_at DESC LIMIT 200
                    """).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def concept_scores(self, limit=50) -> list:
        """概念评分历史"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM concept_score
                    ORDER BY scored_at DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def stock_validations(self, concept_id: str = None) -> list:
        """个股3步验证"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                if concept_id:
                    rows = conn.execute("""
                        SELECT * FROM stock_validation
                        WHERE concept_id=? ORDER BY stock_code, step
                    """, (concept_id,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM stock_validation
                        ORDER BY checked_at DESC LIMIT 200
                    """).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # ──────────────────────────────────────────
    # Capital (Tab 4)
    # ──────────────────────────────────────────

    def capital_anomalies(self, hours=48) -> list:
        """资金异动"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM capital_anomaly
                    WHERE created_at > datetime('now', ? || ' hours')
                    ORDER BY created_at DESC LIMIT 200
                """, (str(hours),)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def limitup_stats(self, trade_date: str = None, limit=50) -> list:
        """涨停统计"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                if trade_date:
                    rows = conn.execute("""
                        SELECT * FROM limitup_stats
                        WHERE trade_date=? ORDER BY limitup_count DESC
                    """, (trade_date,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM limitup_stats
                        ORDER BY trade_date DESC, limitup_count DESC LIMIT ?
                    """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def dragon_tiger(self, trade_date: str = None, limit=50) -> list:
        """龙虎榜"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                if trade_date:
                    rows = conn.execute("""
                        SELECT * FROM dragon_tiger
                        WHERE trade_date=? ORDER BY net_amount DESC
                    """, (trade_date,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM dragon_tiger
                        ORDER BY trade_date DESC, net_amount DESC LIMIT ?
                    """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def northbound_flow(self, days=30) -> list:
        """北向资金"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM northbound_flow
                    ORDER BY trade_date DESC LIMIT ?
                """, (days,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # ──────────────────────────────────────────
    # Sources (Tab 5)
    # ──────────────────────────────────────────

    def source_stats(self) -> dict:
        """信息源统计"""
        try:
            with sqlite3.connect(self.news_db) as conn:
                rows = conn.execute("""
                    SELECT source, source_name, COUNT(*) as total,
                           SUM(CASE WHEN analyzed=1 THEN 1 ELSE 0 END) as analyzed,
                           MAX(created_at) as last_fetch
                    FROM news GROUP BY source
                """).fetchall()
                return {r[0]: {"name": r[1], "total": r[2], "analyzed": r[3],
                               "last_fetch": r[4]} for r in rows}
        except Exception:
            return {}

    def risk_summary(self) -> list:
        """风控总览"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT rc.concept_id, cc.concept_name,
                           SUM(rc.is_passed) as passed, COUNT(*) as total
                    FROM risk_check rc
                    JOIN concept_candidate cc ON rc.concept_id = cc.concept_id
                    WHERE rc.checked_at > datetime('now', '-1 day')
                    GROUP BY rc.concept_id
                    ORDER BY passed DESC
                """).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []
