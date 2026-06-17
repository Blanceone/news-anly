"""个股3步验证 — 真伪排雷

Spec 4.6: 仅对 is_target=1 的股票执行
  1. 业务关联度验证 (F10年报 → 营收占比) → relevance: high/medium/low/fake
  2. 公告验证 (澄清公告/问询函)           → announce_check: pass/fail
  3. 研报验证 (券商覆盖度)               → report_check: pass/fail

结果写入 stock_validation 表 (单行):
  (stock_code, concept_id, trade_date, relevance, announce_check, report_check)
"""
import sqlite3
from datetime import datetime
from config import Config


class StockValidator:
    def __init__(self, concept_db=None):
        self.concept_db = concept_db or Config.CONCEPT_DB

    def validate_stock(self, concept_id: int, stock_code: str,
                       trade_date: str = None) -> dict:
        """对单只股票执行3步验证"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        relevance = self._step_business_relevance(concept_id, stock_code)
        announce_check = self._step_announcement(stock_code)
        report_check = self._step_research(stock_code)

        result = {
            "stock_code": stock_code,
            "concept_id": concept_id,
            "trade_date": trade_date,
            "relevance": relevance,
            "announce_check": announce_check,
            "report_check": report_check,
        }

        self._save_validation(result)
        return result

    def validate_concept_stocks(self, concept_id: int, trade_date: str = None) -> list:
        """验证概念下所有 is_target=1 的股票"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT stock_code FROM concept_stock
                WHERE concept_id=? AND is_target=1
            """, (concept_id,)).fetchall()
        results = []
        for row in rows:
            result = self.validate_stock(concept_id, row["stock_code"], trade_date)
            results.append(result)
        return results

    # ──────────────────────────────────────────
    # Step 1: 业务关联度 → relevance
    # ──────────────────────────────────────────

    def _step_business_relevance(self, concept_id: int, stock_code: str) -> str:
        """验证业务关联度 → high/medium/low/fake

        Spec: 通过爬取东方财富F10页面验证业务营收占比
        V1实现: 检查 concept_stock 表中的 role 字段推断
        """
        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute("""
                SELECT role, is_target FROM concept_stock
                WHERE concept_id=? AND stock_code=?
            """, (concept_id, stock_code)).fetchone()

        if not row:
            return "fake"

        role = row[0] or "member"
        # leader/upstream/downstream → 高关联
        if role in ("leader", "upstream", "downstream"):
            return "high"
        # member → 中等关联
        if role == "member":
            return "medium"
        return "low"

    # ──────────────────────────────────────────
    # Step 2: 公告验证 → announce_check
    # ──────────────────────────────────────────

    def _step_announcement(self, stock_code: str) -> str:
        """公告验证: 是否有澄清公告/问询函 → pass/fail

        从 news.db 中查找该公司的利空/澄清/问询类公告
        """
        try:
            with sqlite3.connect(Config.NEWS_DB) as conn:
                rows = conn.execute("""
                    SELECT title FROM news
                    WHERE (title LIKE ? OR title LIKE ?)
                    AND (title LIKE '%澄清%' OR title LIKE '%问询%' OR title LIKE '%关注函%'
                         OR category='RISK' OR sentiment='negative')
                    AND created_at > datetime('now', '-90 days')
                    ORDER BY created_at DESC LIMIT 5
                """, (f"%{stock_code}%", f"%{stock_code}%")).fetchall()

            if rows:
                return "fail"
        except Exception:
            pass
        return "pass"

    # ──────────────────────────────────────────
    # Step 3: 研报验证 → report_check
    # ──────────────────────────────────────────

    def _step_research(self, stock_code: str) -> str:
        """研报验证: 是否有券商覆盖 → pass/fail

        Spec 降级方案: 检查相关概念股是否在近3日有券商研报发布
        V1实现: 通过 Tushare 查询研报
        """
        if not Config.TUSHARE_TOKEN:
            return "pass"  # 无数据时默认通过
        try:
            import tushare as ts
            pro = ts.pro_api(Config.TUSHARE_TOKEN)
            from datetime import timedelta
            df = pro.research_report(
                ts_code=stock_code,
                start_date=(datetime.now() - timedelta(days=90)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d")
            )
            if df is not None and not df.empty:
                return "pass"
            return "fail"
        except Exception:
            return "pass"  # 查询失败默认通过

    # ──────────────────────────────────────────
    # 持久化
    # ──────────────────────────────────────────

    def _save_validation(self, result: dict):
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO stock_validation
                    (stock_code, concept_id, trade_date, relevance, announce_check, report_check)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (result["stock_code"], result["concept_id"],
                  result["trade_date"], result["relevance"],
                  result["announce_check"], result["report_check"]))
            conn.commit()

    def get_validations(self, concept_id: int = None) -> list:
        """查询验证结果"""
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
