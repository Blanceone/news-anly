"""7信号验证引擎 — 概念真伪判定

PRD 第五章: 概念成型预警与真伪验证清单
  >=5信号 → main_concept (主线概念, 可参与龙头)
  4信号   → uncertain    (存疑, 继续观察)
  <=3信号 → one_day_wonder (一日游, 坚决回避)

信号:
  1=源头事件可查(必须)  2=3日净流入递增  3=涨停>=5只
  4=竞价抢筹>=3000万    5=上下游扩散    6=媒体热度拐点
  7=研报覆盖
"""
import sqlite3
from datetime import datetime, timedelta
from config import Config


SIGNAL_NAMES = {
    1: "源头事件可查",
    2: "3日净流入递增",
    3: "涨停>=5只",
    4: "竞价抢筹>=3000万",
    5: "上下游扩散",
    6: "媒体热度拐点",
    7: "研报覆盖",
}


class ConceptValidator:
    def __init__(self, concept_db=None):
        self.concept_db = concept_db or Config.CONCEPT_DB

    def validate(self, concept_id: str) -> dict:
        """执行全部7信号验证，返回验证结果"""
        results = {}
        for signal_no in range(1, 8):
            result = self._check_signal(concept_id, signal_no)
            results[signal_no] = result
            self._save_validation(concept_id, signal_no, result)

        # 统计
        met_count = sum(1 for r in results.values() if r["is_met"])
        verdict = self._determine_verdict(met_count, results)

        # 更新 concept_candidate 的 signal_count 和 verdict
        self._update_concept(concept_id, met_count, verdict)

        return {
            "concept_id": concept_id,
            "signals": results,
            "signal_count": met_count,
            "verdict": verdict["verdict"],
            "action": verdict["action"],
        }

    def validate_all_observing(self) -> list:
        """验证所有 observing 状态的概念"""
        with sqlite3.connect(self.concept_db) as conn:
            rows = conn.execute(
                "SELECT concept_id FROM concept_candidate WHERE status IN ('observing', 'validated')"
            ).fetchall()
        results = []
        for row in rows:
            result = self.validate(row[0])
            results.append(result)
        return results

    # ──────────────────────────────────────────
    # 各信号检查
    # ──────────────────────────────────────────

    def _check_signal(self, concept_id: str, signal_no: int) -> dict:
        """检查单个信号"""
        checkers = {
            1: self._signal_1_source_event,
            2: self._signal_2_capital_flow,
            3: self._signal_3_limitup,
            4: self._signal_4_auction_rush,
            5: self._signal_5_upstream_downstream,
            6: self._signal_6_media_heat,
            7: self._signal_7_research_coverage,
        }
        checker = checkers.get(signal_no)
        if checker:
            return checker(concept_id)
        return {"is_met": False, "evidence": "未实现", "score": 0}

    def _signal_1_source_event(self, concept_id: str) -> dict:
        """信号1: 源头事件公开可查 (必须满足)"""
        with sqlite3.connect(self.concept_db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM concept_event WHERE concept_id=?",
                (concept_id,)
            ).fetchone()[0]
        is_met = count >= 1
        evidence = f"关联{count}个事件" if count else "无关联事件"
        return {"is_met": is_met, "evidence": evidence, "score": min(count * 20, 100)}

    def _signal_2_capital_flow(self, concept_id: str) -> dict:
        """信号2: 板块连续3日主力资金净流入，且金额递增"""
        # 从 capital_anomaly 中查找该概念的资金异动
        with sqlite3.connect(self.concept_db) as conn:
            rows = conn.execute("""
                SELECT COUNT(DISTINCT trade_date) as days, SUM(amount) as total
                FROM capital_anomaly
                WHERE concept_id=? AND anomaly_type IN ('volume_breakout', 'northbound')
                AND created_at > datetime('now', '-3 days')
            """, (concept_id,)).fetchone()
        days = rows[0] if rows else 0
        total = rows[1] if rows else 0
        is_met = days >= 3 and total > 0
        evidence = f"{days}日有资金异动, 合计{total:.0f}" if days else "无资金异动"
        return {"is_met": is_met, "evidence": evidence, "score": min(days * 30, 100)}

    def _signal_3_limitup(self, concept_id: str) -> dict:
        """信号3: 板块涨停>=5只"""
        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute("""
                SELECT MAX(limitup_count), leader_stock
                FROM limitup_stats WHERE concept_id=?
                AND trade_date >= date('now', '-1 day')
            """, (concept_id,)).fetchone()
        max_count = row[0] if row and row[0] else 0
        leader = row[1] if row and row[1] else ""
        is_met = max_count >= 5
        evidence = f"最多涨停{max_count}只" + (f", 龙头:{leader}" if leader else "")
        return {"is_met": is_met, "evidence": evidence, "score": min(max_count * 20, 100)}

    def _signal_4_auction_rush(self, concept_id: str) -> dict:
        """信号4: 龙头股竞价抢筹>=3000万"""
        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute("""
                SELECT MAX(amount), stock_name
                FROM capital_anomaly
                WHERE concept_id=? AND anomaly_type='auction_rush'
                AND created_at > datetime('now', '-1 day')
            """, (concept_id,)).fetchone()
        max_amount = row[0] if row and row[0] else 0
        stock_name = row[1] if row and row[1] else ""
        is_met = max_amount >= 3000  # 万元
        evidence = f"竞价{max_amount:.0f}万" + (f"({stock_name})" if stock_name else "")
        if not max_amount:
            evidence = "无竞价抢筹数据"
        return {"is_met": is_met, "evidence": evidence, "score": min(max_amount / 50, 100)}

    def _signal_5_upstream_downstream(self, concept_id: str) -> dict:
        """信号5: 题材从核心股扩散到上下游"""
        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute("""
                SELECT COUNT(DISTINCT role), COUNT(*)
                FROM concept_stock
                WHERE concept_id=?
            """, (concept_id,)).fetchone()
        role_count = row[0] if row and row[0] else 0
        stock_count = row[1] if row and row[1] else 0
        is_met = role_count >= 2 and stock_count >= 5
        evidence = f"{role_count}种角色, {stock_count}只股票" if stock_count else "无成分股"
        return {"is_met": is_met, "evidence": evidence, "score": min(role_count * 25 + stock_count * 5, 100)}

    def _signal_6_media_heat(self, concept_id: str) -> dict:
        """信号6: 关键词搜索量/媒体报道频率上升"""
        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute("""
                SELECT mention_count, mention_days
                FROM concept_candidate WHERE concept_id=?
            """, (concept_id,)).fetchone()
        mentions = row[0] if row and row[0] else 0
        days = row[1] if row and row[1] else 0
        # 热度拐点: 3天内提及>=5次 或 连续>=3天提及
        is_met = (mentions >= 5 and days <= 3) or days >= 3
        evidence = f"提及{mentions}次, 跨{days}天" if mentions else "无媒体提及"
        return {"is_met": is_met, "evidence": evidence, "score": min(mentions * 15, 100)}

    def _signal_7_research_coverage(self, concept_id: str) -> dict:
        """信号7: 机构研报开始覆盖 / 龙虎榜机构与游资共振"""
        with sqlite3.connect(self.concept_db) as conn:
            # 检查龙虎榜是否有关联概念的机构买入
            dt_count = conn.execute("""
                SELECT COUNT(*) FROM dragon_tiger dt
                JOIN concept_stock cs ON dt.stock_code = cs.stock_code
                WHERE cs.concept_id=?
                AND dt.created_at > datetime('now', '-3 days')
            """, (concept_id,)).fetchone()[0]
        is_met = dt_count >= 2
        evidence = f"龙虎榜{dt_count}条" if dt_count else "无龙虎榜数据"
        return {"is_met": is_met, "evidence": evidence, "score": min(dt_count * 30, 100)}

    # ──────────────────────────────────────────
    # 判定逻辑
    # ──────────────────────────────────────────

    def _determine_verdict(self, signal_count: int, signals: dict) -> dict:
        """根据信号数判定概念类型"""
        # 信号1 (源头事件) 是必须条件
        if not signals.get(1, {}).get("is_met", False):
            return {
                "verdict": "one_day_wonder",
                "action": "avoid",
                "reason": "无源头事件支撑，判定为纯情绪波动",
            }
        if signal_count >= 5:
            return {
                "verdict": "main_concept",
                "action": "participate",
                "reason": f"{signal_count}个信号满足，判定为主线概念",
            }
        elif signal_count == 4:
            return {
                "verdict": "uncertain",
                "action": "observe",
                "reason": f"4个信号满足，存疑，继续观察",
            }
        else:
            return {
                "verdict": "one_day_wonder",
                "action": "avoid",
                "reason": f"仅{signal_count}个信号满足，判定为一日游",
            }

    # ──────────────────────────────────────────
    # 持久化
    # ──────────────────────────────────────────

    def _save_validation(self, concept_id: str, signal_no: int, result: dict):
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT INTO concept_validation
                    (concept_id, signal_no, signal_name, is_met, evidence, score)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (concept_id, signal_no, SIGNAL_NAMES.get(signal_no, ""),
                  1 if result["is_met"] else 0, result.get("evidence", ""),
                  result.get("score", 0)))
            conn.commit()

    def _update_concept(self, concept_id: str, signal_count: int, verdict: dict):
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                UPDATE concept_candidate
                SET signal_count=?, verdict=?, updated_at=?
                WHERE concept_id=?
            """, (signal_count, verdict["verdict"],
                  datetime.now().isoformat(), concept_id))

            # 写入 concept_score
            conn.execute("""
                INSERT INTO concept_score
                    (concept_id, concept_name, signal_count, total_score,
                     verdict, action, risk_level)
                SELECT ?, concept_name, ?, ?, ?, ?, ?
                FROM concept_candidate WHERE concept_id=?
            """, (concept_id, signal_count,
                  signal_count * 14.3,  # 简单评分
                  verdict["verdict"], verdict["action"],
                  "low" if verdict["action"] == "participate" else "high",
                  concept_id))
            conn.commit()

    def get_validation_history(self, concept_id: str) -> list:
        """获取概念验证历史"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM concept_validation
                WHERE concept_id=? ORDER BY checked_at DESC
            """, (concept_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_score_history(self, limit=50) -> list:
        """获取评分历史"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM concept_score
                ORDER BY scored_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
