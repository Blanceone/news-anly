"""SOP 调度器 — 三阶段标准作业程序

PRD 第三章: 每日信息监测SOP
  1. Pre-market (7:00-9:15):  采集→事件抽取→概念发现→输出题材预判
  2. Intraday   (9:15-15:00): 增量采集→资金异动→涨停监控→触发验证→风控
  3. Post-market(15:00-22:00): 涨停复盘→龙虎榜→北向→全量验证→评分→风控终检
"""
import time
from datetime import datetime

from collectors import NewsCollector
from core.db_init import init_news_db, init_concept_db
from services.event_service import EventService
from services.concept_discovery import ConceptDiscovery
from services.capital_detector import CapitalDetector
from services.market_monitor import MarketMonitor
from services.concept_validator import ConceptValidator
from services.stock_validator import StockValidator
from services.risk_control import RiskControl


class NewsScheduler:
    def __init__(self):
        init_news_db()
        init_concept_db()
        self.collector = NewsCollector()
        self.event_svc = EventService()
        self.concept_disc = ConceptDiscovery()
        self.capital_det = CapitalDetector()
        self.market_mon = MarketMonitor()
        self.concept_val = ConceptValidator()
        self.stock_val = StockValidator()
        self.risk_ctrl = RiskControl()

    # ──────────────────────────────────────────
    # 主入口
    # ──────────────────────────────────────────

    def run(self):
        """单次运行: 根据当前时间自动选择SOP阶段"""
        phase = self._detect_phase()
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
              f"SOP阶段: {phase}")
        self._log_sop(phase, "run", "running")

        if phase == "pre_market":
            self._run_pre_market()
        elif phase == "intraday":
            self._run_intraday()
        else:
            self._run_post_market()

        self._log_sop(phase, "run", "done")
        print(f"  完成！")

    def run_all(self):
        """依次执行全部三个阶段"""
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 全阶段执行")
        self._run_pre_market()
        self._run_intraday()
        self._run_post_market()
        print(f"\n  全阶段完成！")

    def run_loop(self, interval=None):
        """持续循环采集"""
        from config import Config
        interval = interval or Config.FETCH_INTERVAL_SECONDS
        print(f"循环模式: 每 {interval} 秒采集一次 (Ctrl+C 退出)")
        while True:
            try:
                self.run()
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n已停止")
                break
            except Exception as e:
                print(f"运行异常: {e}")
                time.sleep(interval)

    # ──────────────────────────────────────────
    # Phase 1: 盘前准备 (7:00 - 9:15)
    # ──────────────────────────────────────────

    def _run_pre_market(self):
        """盘前: 采集新闻 → 事件抽取 → 概念发现 → 题材预判"""
        print(f"\n  --- 盘前准备阶段 ---")

        # 1. 采集新闻
        since = self.collector.get_last_fetch_time()
        news = self.collector.collect_since(since)
        print(f"  采集: {len(news)} 条新闻")

        # 2. AI事件抽取
        unanalyzed = self.collector.get_unanalyzed_news()
        if unanalyzed:
            print(f"  分析: {len(unanalyzed)} 条未分析新闻...")
            analyzed_ids = []
            for item in unanalyzed:
                try:
                    result = self.event_svc.process_news_item(item)
                    analyzed_ids.append(item["id"])
                    evt_type = result.get("event_type", "OTHER")
                    importance = result.get("importance", "C")
                    concepts = result.get("concept_keywords", [])
                    print(f"    [{evt_type}/{importance}] {item['title'][:40]}")
                    if concepts:
                        print(f"      概念: {', '.join(concepts[:5])}")
                except Exception as e:
                    print(f"    分析失败: {e}")
                time.sleep(0.5)
            self.collector.mark_analyzed(analyzed_ids)

            # 3. 概念发现
            discovered = self.concept_disc.discover_from_analyzed_news(analyzed_ids)
            if discovered:
                print(f"\n  概念发现: {len(discovered)} 个新概念候选")

            # 4. 检查升级
            upgrades = self.concept_disc.check_upgrades()
            if upgrades:
                print(f"  概念升级: {len(upgrades)} 个")
                for u in upgrades:
                    print(f"    [{u['status']}] {u['concept_name']} "
                          f"(提及{u['mention_count']}次)")

        # 5. 输出题材预判清单
        self._output_predictions()

    # ──────────────────────────────────────────
    # Phase 2: 盘中验证 (9:15 - 15:00)
    # ──────────────────────────────────────────

    def _run_intraday(self):
        """盘中: 增量采集 → 资金异动 → 涨停监控 → 验证 → 风控"""
        print(f"\n  --- 盘中验证阶段 ---")

        # 1. 增量采集
        since = self.collector.get_last_fetch_time()
        news = self.collector.collect_since(since)
        if news:
            print(f"  增量采集: {len(news)} 条")
            unanalyzed = self.collector.get_unanalyzed_news()
            if unanalyzed:
                analyzed_ids = []
                for item in unanalyzed:
                    try:
                        result = self.event_svc.process_news_item(item)
                        analyzed_ids.append(item["id"])
                    except Exception:
                        pass
                    time.sleep(0.3)
                self.collector.mark_analyzed(analyzed_ids)
                self.concept_disc.discover_from_analyzed_news(analyzed_ids)

        # 2. 涨停监控
        trade_date = datetime.now().strftime("%Y%m%d")
        limitup_results = self.capital_det.aggregate_limitup_by_concept(trade_date)
        if limitup_results:
            print(f"  涨停聚合: {len(limitup_results)} 个概念有涨停")
            for r in limitup_results:
                if r["limitup_count"] >= 5:
                    print(f"    [!] {r['concept_name']}: {r['limitup_count']}只涨停")

        # 3. 资金异动
        anomalies = self.capital_det.detect_anomalies()
        if anomalies:
            print(f"  资金异动: {len(anomalies)} 条")

        # 4. 对 observing/validated 概念触发验证
        self._trigger_validation()

        # 5. 风控检查
        self._run_risk_checks()

    # ──────────────────────────────────────────
    # Phase 3: 盘后复盘 (15:00 - 22:00)
    # ──────────────────────────────────────────

    def _run_post_market(self):
        """盘后: 涨停复盘 → 龙虎榜 → 北向 → 全量验证 → 风控终检"""
        print(f"\n  --- 盘后复盘阶段 ---")

        # 1. 最终采集
        since = self.collector.get_last_fetch_time()
        news = self.collector.collect_since(since)
        if news:
            unanalyzed = self.collector.get_unanalyzed_news()
            if unanalyzed:
                analyzed_ids = []
                for item in unanalyzed:
                    try:
                        self.event_svc.process_news_item(item)
                        analyzed_ids.append(item["id"])
                    except Exception:
                        pass
                    time.sleep(0.3)
                self.collector.mark_analyzed(analyzed_ids)
                self.concept_disc.discover_from_analyzed_news(analyzed_ids)
                self.concept_disc.check_upgrades()

        trade_date = datetime.now().strftime("%Y%m%d")

        # 2. 涨停复盘
        limitup_results = self.capital_det.aggregate_limitup_by_concept(trade_date)
        print(f"  涨停复盘: {len(limitup_results)} 个概念")

        # 3. 龙虎榜
        dt_results = self.capital_det.fetch_dragon_tiger(trade_date)
        print(f"  龙虎榜: {len(dt_results)} 条")

        # 4. 北向资金
        nb = self.capital_det.fetch_northbound(trade_date)
        if nb:
            north = nb.get("north_money", 0)
            print(f"  北向资金: {north/100:.1f}亿")

        # 5. 大盘量能
        market = self.market_mon.assess_market(trade_date)
        print(f"  市场评估: {market.get('summary', '')}")

        # 6. 全量7信号验证
        validations = self.concept_val.validate_all_observing()
        if validations:
            print(f"\n  7信号验证: {len(validations)} 个概念")
            for v in validations:
                print(f"    [{v['verdict']}] {v['concept_id']}: "
                      f"{v['signal_count']}/7 信号 → {v['action']}")

        # 7. 风控终检
        self._run_risk_checks()
        risk_summary = self.risk_ctrl.get_risk_summary()
        if risk_summary:
            print(f"\n  风控总览: {len(risk_summary)} 个概念")
            for r in risk_summary:
                print(f"    [{r['risk_level']}] {r['concept_name']}: "
                      f"{r['passed']}/{r['total']} 通过")

    # ──────────────────────────────────────────
    # 辅助方法
    # ──────────────────────────────────────────

    def _detect_phase(self) -> str:
        """根据当前时间判断SOP阶段"""
        now = datetime.now()
        t = now.hour * 100 + now.minute
        if t < 925:
            return "pre_market"
        elif t < 1500:
            return "intraday"
        else:
            return "post_market"

    def _output_predictions(self):
        """输出题材预判清单"""
        concepts = self.concept_disc.get_concepts(status="observing", limit=5)
        if not concepts:
            concepts = self.concept_disc.get_concepts(limit=5)
        if concepts:
            print(f"\n  === 题材预判清单 (Top {len(concepts)}) ===")
            for i, c in enumerate(concepts, 1):
                print(f"    {i}. [{c['status']}/{c['lifecycle']}] "
                      f"{c['concept_name']} "
                      f"(提及{c['mention_count']}次, {c['mention_days']}天)")

    def _trigger_validation(self):
        """对符合条件的概念触发验证"""
        concepts = self.concept_disc.get_concepts(status="observing", limit=10)
        validated = self.concept_disc.get_concepts(status="validated", limit=10)
        all_concepts = concepts + validated
        if all_concepts:
            for c in all_concepts[:5]:  # 最多验证5个
                try:
                    result = self.concept_val.validate(c["concept_id"])
                    print(f"    [{result['verdict']}] {c['concept_name']}: "
                          f"{result['signal_count']}/7 → {result['action']}")
                except Exception as e:
                    print(f"    验证异常: {e}")

    def _run_risk_checks(self):
        """对 validated 概念执行风控检查"""
        concepts = self.concept_disc.get_concepts(status="validated", limit=10)
        for c in concepts:
            try:
                result = self.risk_ctrl.check_all(c["concept_id"])
                if not result["is_safe"]:
                    print(f"    [风控] {c['concept_name']}: {result['risk_level']} "
                          f"- {result['summary']}")
            except Exception:
                pass

    def _log_sop(self, phase: str, task_name: str, status: str):
        """记录SOP执行日志"""
        import sqlite3
        from config import Config
        try:
            with sqlite3.connect(Config.CONCEPT_DB) as conn:
                if status == "running":
                    conn.execute("""
                        INSERT INTO sop_log (phase, task_name, status)
                        VALUES (?, ?, ?)
                    """, (phase, task_name, status))
                else:
                    conn.execute("""
                        UPDATE sop_log SET status=?, finished_at=?
                        WHERE phase=? AND task_name=? AND status='running'
                    """, (status, datetime.now().isoformat(), phase, task_name))
                conn.commit()
        except Exception:
            pass
