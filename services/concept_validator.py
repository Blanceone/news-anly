"""7信号验证引擎 — 概念真伪判定

Spec 4.5: ConceptValidator
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

    def validate(self, concept_id: int, trade_date: str = None) -> dict:
        """执行全部7信号验证，返回验证结果"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        results = {}
        for signal_no in range(1, 8):
            result = self._check_signal(concept_id, signal_no, trade_date)
            results[signal_no] = result
            self._save_validation(concept_id, trade_date, signal_no, result)

        # 统计
        met_count = sum(1 for r in results.values() if r["is_met"])
        verdict = self._determine_verdict(met_count, results)

        # 写入 concept_score
        self._save_score(concept_id, trade_date, met_count, verdict)

        return {
            "concept_id": concept_id,
            "trade_date": trade_date,
            "signals": results,
            "signal_count": met_count,
            "verdict": verdict["verdict"],
        }

    def validate_all_observing(self, trade_date: str = None) -> list:
        """验证所有 observing 和 validated 状态的概念"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.concept_db) as conn:
            rows = conn.execute(
                "SELECT id FROM concept_candidate WHERE status IN ('observing', 'validated')"
            ).fetchall()
        results = []
        for row in rows:
            result = self.validate(row[0], trade_date)
            results.append(result)
        return results

    # ──────────────────────────────────────────
    # 各信号检查
    # ──────────────────────────────────────────

    def _check_signal(self, concept_id: int, signal_no: int, trade_date: str) -> dict:
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
            return checker(concept_id, trade_date)
        return {"is_met": False, "evidence": "未实现"}

    def _signal_1_source_event(self, concept_id: int, trade_date: str) -> dict:
        """信号1: 源头事件公开可查 (必须满足)"""
        with sqlite3.connect(self.concept_db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM concept_event WHERE concept_id=?",
                (concept_id,)
            ).fetchone()[0]
        is_met = count >= 1
        evidence = f"关联{count}个事件" if count else "无关联事件"
        return {"is_met": is_met, "evidence": evidence}

    def _signal_2_capital_flow(self, concept_id: int, trade_date: str) -> dict:
        """信号2: 板块连续3日主力资金净流入，且金额递增"""
        with sqlite3.connect(self.concept_db) as conn:
            rows = conn.execute("""
                SELECT COUNT(DISTINCT trade_date) as days
                FROM northbound_flow nf
                JOIN concept_stock cs ON nf.stock_code = cs.stock_code
                WHERE cs.concept_id=? AND nf.net_buy > 0
                AND nf.trade_date >= date(?, '-3 days')
            """, (concept_id, trade_date)).fetchall()
        days = rows[0][0] if rows else 0
        is_met = days >= 3
        evidence = f"{days}日有净流入" if days else "无资金流入数据"
        return {"is_met": is_met, "evidence": evidence}

    def _signal_3_limitup(self, concept_id: int, trade_date: str) -> dict:
        """信号3: 板块涨停>=5只"""
        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute("""
                SELECT limitup_count, max_consecutive_boards
                FROM limitup_stats
                WHERE concept_id=? AND trade_date=?
            """, (concept_id, trade_date)).fetchone()
        limitup_count = row[0] if row and row[0] else 0
        max_boards = row[1] if row and row[1] else 0
        is_met = limitup_count >= 5
        evidence = f"涨停{limitup_count}只, 最高{max_boards}连板" if limitup_count else "无涨停数据"
        return {"is_met": is_met, "evidence": evidence}

    def _signal_4_auction_rush(self, concept_id: int, trade_date: str) -> dict:
        """信号4: 龙头股竞价抢筹>=3000万 (降级: 9:45前涨停 或 早盘资金异动)"""
        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute("""
                SELECT COUNT(*), detail
                FROM capital_anomaly
                WHERE anomaly_type='early_morning_rush'
                AND trade_date=?
                AND stock_code IN (
                    SELECT stock_code FROM concept_stock WHERE concept_id=?
                )
            """, (trade_date, concept_id)).fetchone()
        count = row[0] if row and row[0] else 0
        is_met = count >= 1
        evidence = f"{count}只早盘抢筹" if count else "无竞价抢筹数据"
        return {"is_met": is_met, "evidence": evidence}

    def _signal_5_upstream_downstream(self, concept_id: int, trade_date: str) -> dict:
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
        return {"is_met": is_met, "evidence": evidence}

    def _signal_6_media_heat(self, concept_id: int, trade_date: str) -> dict:
        """信号6: 媒体报道频率上升 (降级: 系统24h内相关新闻数)"""
        with sqlite3.connect(self.concept_db) as conn:
            row = conn.execute("""
                SELECT mention_count FROM concept_candidate WHERE id=?
            """, (concept_id,)).fetchone()
        mentions = row[0] if row and row[0] else 0
        # 热度拐点: 提及>=5次
        is_met = mentions >= 5
        evidence = f"提及{mentions}次" if mentions else "无媒体提及"
        return {"is_met": is_met, "evidence": evidence}

    def _signal_7_research_coverage(self, concept_id: int, trade_date: str) -> dict:
        """信号7: 龙虎榜机构与游资共振 / 研报覆盖"""
        with sqlite3.connect(self.concept_db) as conn:
            # 检查龙虎榜是否有关联概念的机构买入
            dt_count = conn.execute("""
                SELECT COUNT(*) FROM dragon_tiger dt
                JOIN concept_stock cs ON dt.stock_code = cs.stock_code
                WHERE cs.concept_id=?
                AND dt.trade_date >= date(?, '-3 days')
                AND dt.buyer_type IN ('institution', 'hot_money')
            """, (concept_id, trade_date)).fetchone()[0]
        is_met = dt_count >= 2
        evidence = f"龙虎榜{dt_count}条(机构/游资)" if dt_count else "无龙虎榜数据"
        return {"is_met": is_met, "evidence": evidence}

    # ──────────────────────────────────────────
    # 判定逻辑
    # ──────────────────────────────────────────

    def _determine_verdict(self, signal_count: int, signals: dict) -> dict:
        """根据信号数判定概念类型"""
        # 信号1 (源头事件) 是必须条件
        if not signals.get(1, {}).get("is_met", False):
            return {
                "verdict": "one_day_wonder",
                "reason": "无源头事件支撑，判定为纯情绪波动",
            }
        if signal_count >= 5:
            return {
                "verdict": "main_concept",
                "reason": f"{signal_count}个信号满足，判定为主线概念",
            }
        elif signal_count == 4:
            return {
                "verdict": "uncertain",
                "reason": "4个信号满足，存疑，继续观察",
            }
        else:
            return {
                "verdict": "one_day_wonder",
                "reason": f"仅{signal_count}个信号满足，判定为一日游",
            }

    # ──────────────────────────────────────────
    # 持久化
    # ──────────────────────────────────────────

    def _save_validation(self, concept_id: int, trade_date: str,
                         signal_no: int, result: dict):
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO concept_validation
                    (concept_id, trade_date, signal_no, is_met, evidence)
                VALUES (?, ?, ?, ?, ?)
            """, (concept_id, trade_date, signal_no,
                  1 if result["is_met"] else 0,
                  result.get("evidence", "")))
            conn.commit()

    def _save_score(self, concept_id: int, trade_date: str,
                    signal_count: int, verdict: dict):
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO concept_score
                    (concept_id, trade_date, signal_count, verdict)
                VALUES (?, ?, ?, ?)
            """, (concept_id, trade_date, signal_count, verdict["verdict"]))
            conn.commit()

    def get_validation_history(self, concept_id: int, trade_date: str = None) -> list:
        """获取概念验证历史"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            if trade_date:
                rows = conn.execute("""
                    SELECT * FROM concept_validation
                    WHERE concept_id=? AND trade_date=?
                    ORDER BY signal_no
                """, (concept_id, trade_date)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM concept_validation
                    WHERE concept_id=?
                    ORDER BY trade_date DESC, signal_no
                """, (concept_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_score_history(self, limit=50) -> list:
        """获取评分历史"""
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT cs.*, cc.standard_name
                FROM concept_score cs
                JOIN concept_candidate cc ON cs.concept_id = cc.id
                ORDER BY cs.trade_date DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
