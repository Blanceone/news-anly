"""风控引擎 — PRD 第六章红线检查

风控红线:
  1. 追高风险: 主线刚启动可参与，高位放量滞涨不追
  2. 事件支撑: 无公开事件支撑的异动一律过滤
  3. 大盘量能: 两市<8000亿 → 题材极易一日游
  4. 止损规则: 跌破5日/10日均线 或 固定5%止损
"""
import sqlite3
from datetime import datetime
from config import Config


class RiskControl:
    def __init__(self, concept_db=None):
        self.concept_db = concept_db or Config.CONCEPT_DB

    def check_all(self, concept_id: str) -> dict:
        """执行全部风控检查"""
        checks = {
            "event_support": self._check_event_support(concept_id),
            "volume": self._check_market_volume(),
            "chase_high": self._check_chase_high(concept_id),
            "stop_loss": self._check_stop_loss(concept_id),
        }
        passed = sum(1 for c in checks.values() if c["is_passed"])
        is_safe = passed == len(checks)

        self._save_checks(concept_id, checks)

        return {
            "concept_id": concept_id,
            "checks": checks,
            "passed_count": passed,
            "total_checks": len(checks),
            "is_safe": is_safe,
            "risk_level": "low" if is_safe else ("medium" if passed >= 2 else "high"),
            "summary": self._build_summary(checks),
        }

    # ──────────────────────────────────────────
    # 风控检查项
    # ──────────────────────────────────────────

    def _check_event_support(self, concept_id: str) -> dict:
        """检查1: 事件支撑 — 是否有公开事件支持"""
        with sqlite3.connect(self.concept_db) as conn:
            event_count = conn.execute(
                "SELECT COUNT(*) FROM concept_event WHERE concept_id=?",
                (concept_id,)
            ).fetchone()[0]
        is_passed = event_count >= 1
        detail = f"有{event_count}个事件支撑" if event_count else "无事件支撑(纯情绪波动)"
        return {"is_passed": is_passed, "detail": detail}

    def _check_market_volume(self) -> dict:
        """检查2: 大盘量能 — 两市成交额是否>8000亿"""
        try:
            from services.market_monitor import MarketMonitor
            mm = MarketMonitor()
            vol_info = mm.get_market_volume()
            total = vol_info.get("total_volume", 0)
            is_healthy = vol_info.get("is_healthy", False)
            detail = vol_info.get("detail", "无数据")
            return {"is_passed": is_healthy, "detail": detail, "market_volume": total}
        except Exception:
            return {"is_passed": True, "detail": "无Tushare, 跳过量能检查", "market_volume": 0}

    def _check_chase_high(self, concept_id: str) -> dict:
        """检查3: 追高风险 — 概念生命周期阶段"""
        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute("""
                SELECT lifecycle, mention_count, mention_days, signal_count
                FROM concept_candidate WHERE concept_id=?
            """, (concept_id,)).fetchone()
        if not row:
            return {"is_passed": False, "detail": "概念不存在"}

        lifecycle, mentions, days, signals = row
        # BIRTH/GROWING + 低提及 → 启动早期, 可参与
        # PEAK + 高提及 → 可能已经扩散, 需警惕
        # DECLINING/DEAD → 不追
        if lifecycle in ("DECLINING", "DEAD"):
            return {"is_passed": False, "detail": f"概念已{lifecycle}, 不追高"}
        if lifecycle == "PEAK" and mentions > 10:
            return {"is_passed": False, "detail": "概念已PEAK且高提及, 追高风险"}
        return {"is_passed": True, "detail": f"概念{lifecycle}, {mentions}次提及, 尚在早期"}

    def _check_stop_loss(self, concept_id: str) -> dict:
        """检查4: 止损规则 — 确认止损位设定"""
        # 这是一个规则确认, 始终通过 (提醒用户设置止损)
        return {
            "is_passed": True,
            "detail": "建议止损: 跌破5日均线或-5%固定止损",
        }

    # ──────────────────────────────────────────
    # 持久化
    # ──────────────────────────────────────────

    def _save_checks(self, concept_id: str, checks: dict):
        with sqlite3.connect(self.concept_db) as conn:
            now = datetime.now().isoformat()
            for check_type, result in checks.items():
                conn.execute("""
                    INSERT INTO risk_check
                        (concept_id, check_type, is_passed, detail, market_volume, checked_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (concept_id, check_type,
                      1 if result["is_passed"] else 0,
                      result.get("detail", ""),
                      result.get("market_volume", 0),
                      now))
            conn.commit()

    def _build_summary(self, checks: dict) -> str:
        parts = []
        for name, result in checks.items():
            status = "OK" if result["is_passed"] else "FAIL"
            parts.append(f"{name}:{status}")
        return " | ".join(parts)

    def get_recent_checks(self, hours=24) -> list:
        """获取最近风控检查结果"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM risk_check
                WHERE checked_at > datetime('now', ? || ' hours')
                ORDER BY checked_at DESC
            """, (str(hours),)).fetchall()
            return [dict(r) for r in rows]

    def get_risk_summary(self) -> dict:
        """获取当前风控总览"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            # 最近一次每个概念的风控结果
            rows = conn.execute("""
                SELECT rc.concept_id, cc.concept_name,
                       SUM(rc.is_passed) as passed, COUNT(*) as total
                FROM risk_check rc
                JOIN concept_candidate cc ON rc.concept_id = cc.concept_id
                WHERE rc.checked_at > datetime('now', '-1 day')
                GROUP BY rc.concept_id
                ORDER BY passed DESC
            """).fetchall()
            results = []
            for r in rows:
                results.append({
                    "concept_id": r["concept_id"],
                    "concept_name": r["concept_name"],
                    "passed": r["passed"],
                    "total": r["total"],
                    "risk_level": "low" if r["passed"] == r["total"]
                                  else ("medium" if r["passed"] >= r["total"] // 2
                                        else "high"),
                })
            return results
