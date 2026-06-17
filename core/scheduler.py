"""SOP 调度器 — 三阶段标准作业程序

Spec 第5章: SOP调度器逻辑设计
  1. Pre-market  (7:00-9:15):  采集Tier1/3 → 事件抽取与归一化 → 概念发现升级 → 题材预判
  2. Intraday    (9:15-15:00): 增量采集Tier5 → 涨停监控 → 大盘量能 → 触发验证
  3. Post-market (15:00-22:00): 涨停复盘 → 龙虎榜/北向 → 全量7信号验证 → 个股验证 → 风控
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
    # Spec: 采集Tier1(政策)+Tier3(海外) → EventService → ConceptDiscovery → 题材预判
    # ──────────────────────────────────────────

    def _run_pre_market(self):
        """盘前: 采集新闻 → 事件抽取与归一化 → 概念发现升级 → 题材预判"""
        print(f"\n  --- 盘前准备阶段 ---")

        # 1. 采集新闻 (Tier 5: 财联社/巨潮)
        since = self.collector.get_last_fetch_time()
        news = self.collector.collect_since(since)
        print(f"  采集: {len(news)} 条新闻")

        # 2. AI事件抽取与概念归一化 (Spec 4.2)
        unanalyzed = self.collector.get_unanalyzed_news()
        if unanalyzed:
            print(f"  事件抽取: {len(unanalyzed)} 条未分析新闻...")
            analyzed_ids = []
            for item in unanalyzed:
                try:
                    result = self.event_svc.process_news_item(item)
                    analyzed_ids.append(item["id"])
                    evt_type = result.get("event_type", "")
                    concepts = result.get("potential_concepts", [])
                    print(f"    [{evt_type}] {item['title'][:40]}")
                    if concepts:
                        print(f"      概念: {', '.join(concepts[:5])}")
                except Exception as e:
                    print(f"    分析失败: {e}")
                time.sleep(0.5)
            self.collector.mark_analyzed(analyzed_ids)

        # 3. 概念发现: 检查升级 (Spec 4.3)
        upgrades = self.concept_disc.check_upgrades()
        if upgrades:
            print(f"  概念升级: {len(upgrades)} 个")
            for u in upgrades:
                print(f"    [{u['new_status']}] {u['standard_name']} "
                      f"(提及{u['mention_count']}次)")

        # 4. 输出题材预判清单
        self._output_predictions()

    # ──────────────────────────────────────────
    # Phase 2: 盘中验证 (9:15 - 15:00)
    # Spec: 增量采集Tier5 → 涨停监控 → 大盘量能(10:30后) → 触发验证
    # ──────────────────────────────────────────

    def _run_intraday(self):
        """盘中: 增量采集 → 涨停监控 → 大盘量能 → 触发验证"""
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
                        self.event_svc.process_news_item(item)
                        analyzed_ids.append(item["id"])
                    except Exception:
                        pass
                    time.sleep(0.3)
                self.collector.mark_analyzed(analyzed_ids)

        # 2. 涨停监控 (Spec: 拉取涨停池数据，更新limitup_stats)
        trade_date = datetime.now().strftime("%Y%m%d")
        limitup_results = self.capital_det.aggregate_limitup_by_concept(trade_date)
        if limitup_results:
            print(f"  涨停聚合: {len(limitup_results)} 个概念有涨停")
            for r in limitup_results:
                if r["limitup_count"] >= 5:
                    print(f"    [!] {r['concept_name']}: {r['limitup_count']}只涨停")

        # 3. 大盘量能 (Spec: 10:30后开始检查)
        now = datetime.now()
        if now.hour >= 10 and now.minute >= 30:
            market = self.market_mon.assess_market(trade_date)
            print(f"  市场评估: {market.get('summary', '')}")

        # 4. 若某概念涨停数突变(>=5)，触发 ConceptValidator.validate()
        self._trigger_validation(trade_date)

    # ──────────────────────────────────────────
    # Phase 3: 盘后复盘 (15:00 - 22:00)
    # Spec:
    #   15:30 - 拉取完整涨停池，复盘归档
    #   17:00 - 拉取龙虎榜数据、北向资金数据
    #   18:00 - 对所有observing和validated概念执行全量7信号验证
    #   19:00 - 对is_target=1的个股执行StockValidator 3步验证
    #   20:00 - 执行RiskControl风控扫描，生成最终concept_score与预警记录
    # ──────────────────────────────────────────

    def _run_post_market(self):
        """盘后: 涨停复盘 → 龙虎榜 → 北向 → 全量验证 → 个股验证 → 风控"""
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
                self.concept_disc.check_upgrades()

        trade_date = datetime.now().strftime("%Y-%m-%d")
        trade_date_short = datetime.now().strftime("%Y%m%d")

        # 2. (15:30) 涨停复盘
        limitup_results = self.capital_det.aggregate_limitup_by_concept(trade_date_short)
        print(f"  涨停复盘: {len(limitup_results)} 个概念")

        # 3. (17:00) 龙虎榜
        dt_results = self.capital_det.get_dragon_tiger(trade_date_short)
        print(f"  龙虎榜: {len(dt_results)} 条")

        # 4. (17:00) 北向资金
        nb_results = self.capital_det.get_northbound_flow(trade_date_short)
        print(f"  北向资金: {len(nb_results)} 只个股")

        # 5. (18:00) 大盘量能
        market = self.market_mon.assess_market(trade_date_short)
        print(f"  市场评估: {market.get('summary', '')}")

        # 6. (18:00) 全量7信号验证
        validations = self.concept_val.validate_all_observing(trade_date)
        if validations:
            print(f"\n  7信号验证: {len(validations)} 个概念")
            for v in validations:
                print(f"    [{v['verdict']}] concept#{v['concept_id']}: "
                      f"{v['signal_count']}/7 信号")

        # 7. (19:00) 个股3步验证 (is_target=1)
        self._run_stock_validation(trade_date)

        # 8. (20:00) 风控扫描
        self._run_risk_checks(trade_date)
        risk_summary = self.risk_ctrl.get_risk_summary()
        if risk_summary:
            print(f"\n  风控总览: {len(risk_summary)} 个概念")
            for r in risk_summary:
                print(f"    [{r['risk_level']}] {r['standard_name']}: "
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
                print(f"    {i}. [{c['status']}] "
                      f"{c['standard_name']} "
                      f"(提及{c['mention_count']}次)")

    def _trigger_validation(self, trade_date: str):
        """对涨停>=5的概念触发验证"""
        concepts = self.concept_disc.get_concepts(status="observing", limit=10)
        validated = self.concept_disc.get_concepts(status="validated", limit=10)
        all_concepts = concepts + validated
        if all_concepts:
            today = datetime.now().strftime("%Y-%m-%d")
            for c in all_concepts[:5]:
                try:
                    result = self.concept_val.validate(c["id"], today)
                    print(f"    [{result['verdict']}] {c['standard_name']}: "
                          f"{result['signal_count']}/7")
                except Exception as e:
                    print(f"    验证异常: {e}")

    def _run_stock_validation(self, trade_date: str):
        """对 is_target=1 的个股执行3步验证"""
        concepts = self.concept_disc.get_concepts(status="validated", limit=10)
        for c in concepts:
            try:
                results = self.stock_val.validate_concept_stocks(c["id"], trade_date)
                if results:
                    print(f"  个股验证 {c['standard_name']}: {len(results)} 只")
                    for r in results:
                        print(f"    {r['stock_code']}: "
                              f"关联={r['relevance']} "
                              f"公告={r['announce_check']} "
                              f"研报={r['report_check']}")
            except Exception:
                pass

    def _run_risk_checks(self, trade_date: str):
        """对 validated 概念执行风控检查"""
        concepts = self.concept_disc.get_concepts(status="validated", limit=10)
        for c in concepts:
            try:
                result = self.risk_ctrl.check_all(c["id"], trade_date)
                if not result["is_safe"]:
                    print(f"    [风控] {c.get('standard_name', c['id'])}: "
                          f"{result['risk_level']} - {result['summary']}")
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
