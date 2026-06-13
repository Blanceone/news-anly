import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict


class TuiDB:
    def __init__(self, db_path="news.db"):
        self.db_path = db_path

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def recent_news(self, hours=72, limit=50):
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT id, title, source_name, category, sentiment, created_at
                FROM news WHERE created_at > ? ORDER BY created_at DESC LIMIT ?
            """, (since, limit)).fetchall()
            return [dict(r) for r in rows]

    def top_stocks(self, limit=20):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT stock_code, stock_name, total_score, event_score,
                       benefit_score, market_score, event_count, top_events
                FROM stock_score WHERE score_date = date('now')
                ORDER BY total_score DESC LIMIT ?
            """, (limit,)).fetchall()

            if not rows:
                rows = conn.execute("""
                    SELECT stock_code, stock_name, total_score, event_score,
                           benefit_score, market_score, event_count, top_events
                    FROM stock_score ORDER BY id DESC LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def hot_themes(self):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT theme_key, theme_name, COUNT(DISTINCT stock_code) as stock_count
                FROM theme_stock_mapping GROUP BY theme_key ORDER BY stock_count DESC
            """).fetchall()
            themes = [dict(r) for r in rows]

        with self._conn() as conn:
            event_rows = conn.execute("""
                SELECT e.industry, COUNT(*) as cnt
                FROM event_analysis e
                WHERE e.created_at > datetime('now', '-24 hours')
                GROUP BY e.industry ORDER BY cnt DESC
            """).fetchall()
            for r in event_rows:
                d = dict(r)
                name = d["industry"] or "其他"
                if not any(t["theme_name"] == name for t in themes):
                    themes.append({"theme_key": name, "theme_name": name,
                                   "stock_count": d["cnt"]})
            return themes

    def stock_detail(self, stock_code):
        with self._conn() as conn:
            score = conn.execute("""
                SELECT * FROM stock_score WHERE stock_code = ?
                ORDER BY id DESC LIMIT 1
            """, (stock_code,)).fetchone()
            events = conn.execute("""
                SELECT e.event_type, e.industry, e.importance, e.sentiment,
                       e.event_score, e.ai_summary, e.created_at,
                       es.benefit_level, es.benefit_score, es.match_reason
                FROM event_stock_mapping es
                JOIN event_analysis e ON es.event_id = e.event_id
                WHERE es.stock_code = ?
                ORDER BY e.created_at DESC LIMIT 20
            """, (stock_code,)).fetchall()
            themes = conn.execute("""
                SELECT theme_name, benefit_level, benefit_reason
                FROM theme_stock_mapping WHERE stock_code = ?
            """, (stock_code,)).fetchall()
            return {
                "score": dict(score) if score else None,
                "events": [dict(r) for r in events],
                "themes": [dict(r) for r in themes],
            }

    def all_stocks_summary(self):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT s.stock_code, s.stock_name, s.total_score, s.event_count,
                       COALESCE(t.theme_count, 0) as theme_count
                FROM stock_score s
                LEFT JOIN (
                    SELECT stock_code, COUNT(*) as theme_count
                    FROM theme_stock_mapping GROUP BY stock_code
                ) t ON s.stock_code = t.stock_code
                WHERE s.score_date = date('now')
                ORDER BY s.total_score DESC
            """).fetchall()
            if not rows:
                rows = conn.execute("""
                    SELECT s.stock_code, s.stock_name, s.total_score, s.event_count,
                           COALESCE(t.theme_count, 0) as theme_count
                    FROM stock_score s
                    LEFT JOIN (
                        SELECT stock_code, COUNT(*) as theme_count
                        FROM theme_stock_mapping GROUP BY stock_code
                    ) t ON s.stock_code = t.stock_code
                    ORDER BY s.id DESC LIMIT 50
                """).fetchall()
            return [dict(r) for r in rows]

    def event_list(self, hours=72, limit=50):
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT e.*, COALESCE(mc.confirmation_score, 0) as market_score
                FROM event_analysis e
                LEFT JOIN market_confirmation mc ON e.event_id = mc.event_id
                WHERE e.created_at > ? ORDER BY e.created_at DESC LIMIT ?
            """, (since, limit)).fetchall()
            return [dict(r) for r in rows]

    def event_stocks(self, event_id):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT es.* FROM event_stock_mapping es
                WHERE es.event_id = ?
            """, (event_id,)).fetchall()
            return [dict(r) for r in rows]

    def theme_stocks(self, theme_key):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM theme_stock_mapping WHERE theme_key = ?
            """, (theme_key,)).fetchall()
            return [dict(r) for r in rows]

    def stats(self):
        with self._conn() as conn:
            news_count = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
            event_count = conn.execute("SELECT COUNT(*) FROM event_analysis").fetchone()[0]
            stock_count = conn.execute("SELECT COUNT(DISTINCT stock_code) FROM stock_score").fetchone()[0]
            return {"news": news_count, "events": event_count, "stocks": stock_count}
