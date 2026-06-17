"""TUI 数据查询层 — 连接 news.db + concept.db

适配 V3 Final Spec 表结构。
"""
import sqlite3
from datetime import datetime, timedelta
from config import Config


class TuiDB:
    def __init__(self):
        self.news_db = Config.NEWS_DB
        self.concept_db = Config.CONCEPT_DB

    # ──────────────────────────────────────────
    # Dashboard (Tab 1)
    # Spec 6.1: 当前时间、SOP阶段、大盘量能状态
    #           main_concept概念列表+最高连板龙头
    #           风控预警信号
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
                    "SELECT COUNT(*) FROM concept_candidate"
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
                    LEFT JOIN news n ON e.news_id = n.id
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

    def main_concepts_today(self, trade_date: str = None) -> list:
        """今日 main_concept 概念列表 + 最高连板龙头"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT cs.*, cc.standard_name,
                           ls.max_consecutive_boards, ls.limitup_count
                    FROM concept_score cs
                    JOIN concept_candidate cc ON cs.concept_id = cc.id
                    LEFT JOIN limitup_stats ls ON cs.concept_id = ls.concept_id
                        AND cs.trade_date = ls.trade_date
                    WHERE cs.trade_date = ? AND cs.verdict = 'main_concept'
                    ORDER BY cs.signal_count DESC
                """, (trade_date,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # ──────────────────────────────────────────
    # Concepts (Tab 2)
    # Spec 6.2: 标准概念名、状态、提及次数、最新验证结果、信号达成数
    # ──────────────────────────────────────────

    def concepts(self, status=None, limit=100) -> list:
        """概念候选池"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                if status:
                    rows = conn.execute("""
                        SELECT cc.*,
                               (SELECT verdict FROM concept_score
                                WHERE concept_id=cc.id ORDER BY trade_date DESC LIMIT 1) as latest_verdict,
                               (SELECT signal_count FROM concept_score
                                WHERE concept_id=cc.id ORDER BY trade_date DESC LIMIT 1) as latest_signals
                        FROM concept_candidate cc
                        WHERE cc.status=?
                        ORDER BY cc.mention_count DESC LIMIT ?
                    """, (status, limit)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT cc.*,
                               (SELECT verdict FROM concept_score
                                WHERE concept_id=cc.id ORDER BY trade_date DESC LIMIT 1) as latest_verdict,
                               (SELECT signal_count FROM concept_score
                                WHERE concept_id=cc.id ORDER BY trade_date DESC LIMIT 1) as latest_signals
                        FROM concept_candidate cc
                        ORDER BY cc.mention_count DESC LIMIT ?
                    """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def concept_detail(self, concept_id: int) -> dict:
        """概念详情"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM concept_candidate WHERE id=?",
                    (concept_id,)
                ).fetchone()
                return dict(row) if row else {}
        except Exception:
            return {}

    def concept_events(self, concept_id: int) -> list:
        """概念关联事件"""
        try:
            with sqlite3.connect(self.news_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT ea.*, ce.trade_date
                    FROM event_analysis ea
                    JOIN concept_event ce ON ea.id = ce.event_id
                    WHERE ce.concept_id=?
                    ORDER BY ce.trade_date DESC
                """, (concept_id,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def concept_stocks(self, concept_id: int) -> list:
        """概念成分股"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM concept_stock
                    WHERE concept_id=?
                    ORDER BY is_target DESC, role ASC
                """, (concept_id,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # ──────────────────────────────────────────
    # Validation (Tab 3)
    # Spec 6.3: 左侧7信号状态+evidence, 右侧个股3步验证
    # ──────────────────────────────────────────

    def concept_validations(self, concept_id: int = None,
                            trade_date: str = None) -> list:
        """7信号验证结果"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                if concept_id:
                    rows = conn.execute("""
                        SELECT cv.*, cc.standard_name
                        FROM concept_validation cv
                        JOIN concept_candidate cc ON cv.concept_id = cc.id
                        WHERE cv.concept_id=?
                        ORDER BY cv.trade_date DESC, cv.signal_no
                    """, (concept_id,)).fetchall()
                elif trade_date:
                    rows = conn.execute("""
                        SELECT cv.*, cc.standard_name
                        FROM concept_validation cv
                        JOIN concept_candidate cc ON cv.concept_id = cc.id
                        WHERE cv.trade_date=?
                        ORDER BY cv.concept_id, cv.signal_no
                    """, (trade_date,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT cv.*, cc.standard_name
                        FROM concept_validation cv
                        JOIN concept_candidate cc ON cv.concept_id = cc.id
                        ORDER BY cv.trade_date DESC, cv.concept_id
                        LIMIT 200
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
                    SELECT cs.*, cc.standard_name
                    FROM concept_score cs
                    JOIN concept_candidate cc ON cs.concept_id = cc.id
                    ORDER BY cs.trade_date DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def stock_validations(self, concept_id: int = None) -> list:
        """个股3步验证"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                if concept_id:
                    rows = conn.execute("""
                        SELECT * FROM stock_validation
                        WHERE concept_id=? ORDER BY stock_code
                    """, (concept_id,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM stock_validation
                        ORDER BY trade_date DESC LIMIT 200
                    """).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # ──────────────────────────────────────────
    # Capital (Tab 4)
    # Spec 6.4: 涨停梯队(按概念聚合)、龙虎榜知名游资、北向TOP10
    # ──────────────────────────────────────────

    def capital_anomalies(self, days=2) -> list:
        """资金异动"""
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM capital_anomaly
                    WHERE trade_date >= date('now', ? || ' days')
                    ORDER BY trade_date DESC LIMIT 200
                """, (str(-days),)).fetchall()
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
                        SELECT ls.*, cc.standard_name as concept_name
                        FROM limitup_stats ls
                        JOIN concept_candidate cc ON ls.concept_id = cc.id
                        WHERE ls.trade_date=?
                        ORDER BY ls.limitup_count DESC
                    """, (trade_date,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT ls.*, cc.standard_name as concept_name
                        FROM limitup_stats ls
                        JOIN concept_candidate cc ON ls.concept_id = cc.id
                        ORDER BY ls.trade_date DESC, ls.limitup_count DESC
                        LIMIT ?
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
                        WHERE trade_date=? ORDER BY net_buy DESC
                    """, (trade_date,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM dragon_tiger
                        ORDER BY trade_date DESC, net_buy DESC LIMIT ?
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
                    SELECT trade_date, SUM(net_buy) as total_net_buy, COUNT(*) as stock_count
                    FROM northbound_flow
                    GROUP BY trade_date
                    ORDER BY trade_date DESC LIMIT ?
                """, (days,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def northbound_top10(self, trade_date: str = None) -> list:
        """北向净买入TOP10"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")
        try:
            with sqlite3.connect(self.concept_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM northbound_flow
                    WHERE trade_date=?
                    ORDER BY net_buy DESC LIMIT 10
                """, (trade_date,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # ──────────────────────────────────────────
    # Sources (Tab 5)
    # Spec 6.5: 各Tier最后运行时间、今日采集条数、最新3条源头标题
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
                    SELECT rc.concept_id, cc.standard_name, rc.risk_type, rc.detail
                    FROM risk_check rc
                    JOIN concept_candidate cc ON rc.concept_id = cc.id
                    WHERE rc.trade_date >= date('now', '-1 day')
                    ORDER BY rc.concept_id, rc.risk_type
                """).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []
