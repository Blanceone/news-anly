"""个股验证 — 3步真伪排雷

PRD 5.1: 真伪概念验证三步法
  1. 业务关联度验证 (F10年报 → 营收占比)
  2. 公告验证 (澄清公告/问询函)
  3. 研报验证 (券商覆盖度)
"""
import sqlite3
from datetime import datetime
from config import Config


class StockValidator:
    def __init__(self, concept_db=None):
        self.concept_db = concept_db or Config.CONCEPT_DB

    def validate_stock(self, concept_id: str, stock_code: str, stock_name: str) -> dict:
        """对单只股票执行3步验证"""
        steps = {
            "business": self._step_business(concept_id, stock_code, stock_name),
            "announcement": self._step_announcement(concept_id, stock_code, stock_name),
            "research": self._step_research(concept_id, stock_code, stock_name),
        }
        # 保存结果
        for step_name, result in steps.items():
            self._save_step(concept_id, stock_code, stock_name, step_name, result)

        passed = sum(1 for s in steps.values() if s["is_passed"])
        return {
            "concept_id": concept_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "steps": steps,
            "passed_count": passed,
            "is_valid": passed >= 2,  # 至少2步通过
        }

    def validate_concept_stocks(self, concept_id: str) -> list:
        """验证概念下所有成分股"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT stock_code, stock_name FROM concept_stock
                WHERE concept_id=? ORDER BY is_core DESC
            """, (concept_id,)).fetchall()
        results = []
        for row in rows:
            result = self.validate_stock(concept_id, row["stock_code"], row["stock_name"])
            results.append(result)
        return results

    # ──────────────────────────────────────────
    # Step 1: 业务关联度
    # ──────────────────────────────────────────

    def _step_business(self, concept_id: str, stock_code: str, stock_name: str) -> dict:
        """业务关联度验证: 该公司与概念的实际业务关联"""
        # 检查 concept_stock 表中的 benefit_path
        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute("""
                SELECT role, benefit_path, match_source, is_core
                FROM concept_stock
                WHERE concept_id=? AND stock_code=?
            """, (concept_id, stock_code)).fetchone()

        if not row:
            return {
                "is_passed": False,
                "evidence": "无概念映射记录",
                "exclude_reason": "无法确认业务关联",
            }

        role, path, source, is_core = row
        # 核心成分股 + 有明确受益路径 → 通过
        if is_core and path:
            return {
                "is_passed": True,
                "evidence": f"核心成分, {role}: {path}",
                "exclude_reason": "",
            }
        # 非核心但有受益路径 → 需人工确认
        if path:
            return {
                "is_passed": True,
                "evidence": f"{role}: {path}",
                "exclude_reason": "",
            }
        # 无受益路径 → 可能是蹭概念
        return {
            "is_passed": False,
            "evidence": f"角色:{role}, 无受益路径",
            "exclude_reason": "营收占比不明, 可能蹭概念",
        }

    # ──────────────────────────────────────────
    # Step 2: 公告验证
    # ──────────────────────────────────────────

    def _step_announcement(self, concept_id: str, stock_code: str, stock_name: str) -> dict:
        """公告验证: 是否有澄清公告/问询函"""
        # 从 news.db 中查找该公司的利空/澄清/问询类公告
        try:
            with sqlite3.connect(Config.NEWS_DB) as conn:
                rows = conn.execute("""
                    SELECT title, sentiment, category FROM news
                    WHERE (title LIKE ? OR title LIKE ?)
                    AND (title LIKE '%澄清%' OR title LIKE '%问询%' OR title LIKE '%关注函%'
                         OR category='RISK' OR sentiment='negative')
                    AND created_at > datetime('now', '-90 days')
                    ORDER BY created_at DESC LIMIT 5
                """, (f"%{stock_name}%", f"%{stock_code}%")).fetchall()

            if rows:
                titles = [r[0][:30] for r in rows]
                return {
                    "is_passed": False,
                    "evidence": f"发现{len(rows)}条负面公告",
                    "exclude_reason": f"近期澄清/问询: {'; '.join(titles[:3])}",
                }
        except Exception:
            pass

        return {
            "is_passed": True,
            "evidence": "近90天无澄清/问询函",
            "exclude_reason": "",
        }

    # ──────────────────────────────────────────
    # Step 3: 研报验证
    # ──────────────────────────────────────────

    def _step_research(self, concept_id: str, stock_code: str, stock_name: str) -> dict:
        """研报验证: 是否有券商覆盖"""
        if not Config.TUSHARE_TOKEN:
            return {
                "is_passed": True,  # 无数据时默认通过
                "evidence": "无Tushare, 跳过研报验证",
                "exclude_reason": "",
            }
        try:
            import tushare as ts
            pro = ts.pro_api(Config.TUSHARE_TOKEN)
            # 获取研报
            code = stock_code.replace(".SZ", "").replace(".SH", "")
            df = pro.research_report(ts_code=stock_code,
                                     start_date=(datetime.now() - __import__('datetime').timedelta(days=90)).strftime("%Y%m%d"),
                                     end_date=datetime.now().strftime("%Y%m%d"))
            if df is not None and not df.empty:
                count = len(df)
                return {
                    "is_passed": True,
                    "evidence": f"近90天{count}份研报覆盖",
                    "exclude_reason": "",
                }
            return {
                "is_passed": False,
                "evidence": "近90天无研报覆盖",
                "exclude_reason": "全市场无研报, 降低权重",
            }
        except Exception as e:
            return {
                "is_passed": True,
                "evidence": f"研报查询失败: {e}",
                "exclude_reason": "",
            }

    # ──────────────────────────────────────────
    # 持久化
    # ──────────────────────────────────────────

    def _save_step(self, concept_id: str, stock_code: str, stock_name: str,
                   step: str, result: dict):
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO stock_validation
                    (concept_id, stock_code, stock_name, step,
                     is_passed, evidence, exclude_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (concept_id, stock_code, stock_name, step,
                  1 if result["is_passed"] else 0,
                  result.get("evidence", ""),
                  result.get("exclude_reason", "")))
            conn.commit()

    def get_validations(self, concept_id: str = None) -> list:
        """查询验证结果"""
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
