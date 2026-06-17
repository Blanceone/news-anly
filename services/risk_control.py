"""风控引擎 — PRD 第六章红线检查

Spec 4.6: 每日盘后跑批
  risk_type: chasing_high / no_event_support / low_volume

风控红线:
  1. 追高风险: 主线刚启动可参与，高位放量滞涨不追
  2. 事件支撑: 无公开事件支撑的异动一律过滤
  3. 大盘量能: 两市<8000亿 → 题材极易一日游
"""
import sqlite3
from datetime import datetime
from config import Config


class RiskControl:
    def __init__(self, concept_db=None):
        self.concept_db = concept_db or Config.CONCEPT_DB

    def check_all(self, concept_id: int, trade_date: str = None) -> dict:
        """执行全部风控检查"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        checks = {}
        checks["no_event_support"] = self._check_event_support(concept_id)
        checks["low_volume"] = self._check_market_volume()
        checks["chasing_high"] = self._check_chase_high(concept_id)

        passed = sum(1 for c in checks.values() if c["is_passed"])
        total = len(checks)
        is_safe = passed == total

        self._save_checks(concept_id, trade_date, checks)

        return {
            "concept_id": concept_id,
            "trade_date": trade_date,
            "checks": checks,
            "passed_count": passed,
            "total_checks": total,
            "is_safe": is_safe,
            "risk_level": "low" if is_safe else ("medium" if passed >= 2 else "high"),
            "summary": self._build_summary(checks),
        }

    # ──────────────────────────────────────────
    # 风控检查项
    # ──────────────────────────────────────────

    def _check_event_support(self, concept_id: int) -> dict:
        """检查: 事件支撑 — 是否有公开事件支持"""
        with sqlite3.connect(self.concept_db) as conn:
            event_count = conn.execute(
                "SELECT COUNT(*) FROM concept_event WHERE concept_id=?",
                (concept_id,)
            ).fetchone()[0]
        is_passed = event_count >= 1
        detail = f"有{event_count}个事件支撑" if event_count else "无事件支撑(纯情绪波动)"
        return {"is_passed": is_passed, "detail": detail}

    def _check_market_volume(self) -> dict:
        """检查: 大盘量能 — 两市成交额是否>8000亿"""
        try:
            from services.market_monitor import MarketMonitor
            mm = MarketMonitor()
            vol_info = mm.get_market_volume()
            is_healthy = vol_info.get("is_healthy", False)
            detail = vol_info.get("detail", "无数据")
            return {"is_passed": is_healthy, "detail": detail}
        except Exception:
            return {"is_passed": True, "detail": "无量能数据, 跳过检查"}

    def _check_chase_high(self, concept_id: int) -> dict:
        """检查: 追高风险 — 概念验证结果是否降级"""
        with sqlite3.connect(self.concept_db) as conn:
            # 查看最近的 concept_score verdict
            row = conn.execute("""
                SELECT verdict FROM concept_score
                WHERE concept_id=?
                ORDER BY trade_date DESC LIMIT 1
            """, (concept_id,)).fetchone()

        if not row:
            return {"is_passed": True, "detail": "无历史评分, 默认通过"}

        verdict = row[0]
        # 如果从 main_concept 降级为 uncertain → 追高预警
        if verdict == "one_day_wonder":
            return {"is_passed": False, "detail": "概念已被判定为一日游, 不追高"}
        if verdict == "uncertain":
            return {"is_passed": False, "detail": "概念存疑(uncertain), 追高风险"}
        return {"is_passed": True, "detail": f"概念verdict={verdict}, 可参与"}

    # ──────────────────────────────────────────
    # 持久化
    # ──────────────────────────────────────────

    def _save_checks(self, concept_id: int, trade_date: str, checks: dict):
        with sqlite3.connect(self.concept_db) as conn:
            for risk_type, result in checks.items():
                conn.execute("""
                    INSERT INTO risk_check
                        (concept_id, trade_date, risk_type, detail)
                    VALUES (?, ?, ?, ?)
                """, (concept_id, trade_date, risk_type,
                      result.get("detail", "")))
            conn.commit()

    def _build_summary(self, checks: dict) -> str:
        parts = []
        for name, result in checks.items():
            status = "OK" if result["is_passed"] else "FAIL"
            parts.append(f"{name}:{status}")
        return " | ".join(parts)

    def get_recent_checks(self, days=1) -> list:
        """获取最近风控检查结果"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM risk_check
                WHERE trade_date >= date('now', ? || ' days')
                ORDER BY trade_date DESC
            """, (str(-days),)).fetchall()
            return [dict(r) for r in rows]

    def get_risk_summary(self) -> list:
        """获取当前风控总览"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT rc.concept_id, cc.standard_name,
                       COUNT(*) as total
                FROM risk_check rc
                JOIN concept_candidate cc ON rc.concept_id = cc.id
                WHERE rc.trade_date >= date('now', '-1 day')
                GROUP BY rc.concept_id
                ORDER BY rc.concept_id
            """).fetchall()
            results = []
            for r in rows:
                # 统计该概念通过的检查数
                passed = conn.execute("""
                    SELECT COUNT(*) FROM risk_check
                    WHERE concept_id=? AND trade_date >= date('now', '-1 day')
                    AND detail NOT LIKE '%不%' AND detail NOT LIKE '%FAIL%'
                """, (r["concept_id"],)).fetchone()[0]
                total = r["total"]
                results.append({
                    "concept_id": r["concept_id"],
                    "standard_name": r["standard_name"],
                    "passed": passed,
                    "total": total,
                    "risk_level": "low" if passed == total
                                  else ("medium" if passed >= total // 2
                                        else "high"),
                })
            return results
