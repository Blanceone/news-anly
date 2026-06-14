import json
import time
from datetime import datetime

from config import Config
from collectors import NewsCollector
from core.analyzer import NewsAnalyzer
from core.feishu_pusher import FeishuPusher
from services.event_service import EventService
from services.stock_service import StockService
from services.knowledge_graph import KnowledgeGraph
from services.scoring_engine import ScoringEngine
from services.market_verifier import MarketVerifier


class NewsScheduler:
    def __init__(self):
        self.collector = NewsCollector()
        self.analyzer = NewsAnalyzer()
        self.pusher = FeishuPusher()
        self.event_service = EventService()
        self.stock_service = StockService()
        self.knowledge_graph = KnowledgeGraph()
        self.scoring_engine = ScoringEngine()
        self.market_verifier = MarketVerifier()

    def _tick(self) -> bool:
        now = datetime.now()
        print(f"\n{'='*50}")
        print(f"[{now.strftime('%H:%M:%S')}] 开始增量采集...")
        print(f"{'='*50}")

        last_fetch = self.collector.get_last_fetch_time()
        print(f"  上次采集时间: {last_fetch.strftime('%Y-%m-%d %H:%M:%S')}")

        new_news = self.collector.collect_since(last_fetch)
        print(f"  新增 {len(new_news)} 条新闻")

        # 采集后立刻分析每一条新新闻
        analyzed_ids = []
        for item in new_news:
            try:
                event = self.event_service.process_news_item(item)
                analyzed_ids.append(item["id"])
                event_id = self._get_last_event_id()
                if event_id:
                    self.stock_service.process_event_stocks(event_id, event)
                    kg_result = self.knowledge_graph.reason(
                        event.get("keywords", []),
                        event.get("industry", ""),
                        companies=event.get("companies", []),
                    )
                    self._save_kg_result(event_id, kg_result)
                    self.market_verifier.verify_event(
                        event_id,
                        event.get("industry", ""),
                        event.get("keywords", []),
                    )
            except Exception as e:
                print(f"  [分析失败] {item.get('title', '')[:30]}: {e}")
        if analyzed_ids:
            self.collector.mark_analyzed(analyzed_ids)
            print(f"  已分析 {len(analyzed_ids)} 条新闻")
        else:
            print("  无待分析新闻")

        if new_news:
            self.pusher.push_news(new_news[:10])
            summary = self.analyzer.summarize_news(
                self.collector.get_recent_news(hours=24, limit=100)
            )
            if summary:
                self.pusher.push_report(summary)

        ranked = self.scoring_engine.calculate(hours=24)
        if ranked:
            self._print_ranking(ranked[:10])
        else:
            print("  无评分数据")

        print(f"  [完成] 本次采集")
        return bool(new_news)

    def _get_last_event_id(self):
        import sqlite3
        from config import Config
        try:
            with sqlite3.connect(Config.NEWS_DB) as conn:
                row = conn.execute("SELECT MAX(event_id) FROM event_analysis").fetchone()
                return row[0]
        except Exception:
            return None

    def _save_kg_result(self, event_id: int, stocks: list):
        if not stocks:
            return
        import sqlite3
        from config import Config
        benefit_scores = {1: 95, 2: 80, 3: 60}
        with sqlite3.connect(Config.STOCKS_DB) as conn:
            for stock in stocks[:10]:
                level = 1 if stock["score"] >= 85 else (2 if stock["score"] >= 60 else 3)
                conn.execute("""
                    INSERT OR IGNORE INTO event_stock_mapping
                        (event_id, stock_code, stock_name, benefit_level, benefit_score, match_reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (event_id, stock["stock_code"], stock["stock_name"],
                      level, benefit_scores.get(level, 40),
                      f"图谱推理(路径{stock['path_count']}条,最大权重{stock['score']})"))
            conn.commit()

    def _repair_stock_mappings(self):
        """修补已分析但缺少股票映射的事件"""
        import sqlite3
        from config import Config
        from services.theme_discovery import ThemeDiscovery
        with sqlite3.connect(Config.STOCKS_DB) as sconn:
            mapped = {r[0] for r in sconn.execute("SELECT DISTINCT event_id FROM event_stock_mapping").fetchall()}
        with sqlite3.connect(Config.NEWS_DB) as nconn:
            nconn.row_factory = sqlite3.Row
            rows = nconn.execute("""
                SELECT e.*, n.title, n.content
                FROM event_analysis e
                JOIN news n ON e.source_id = n.id
                ORDER BY e.event_id
            """).fetchall()
        unmapped = [dict(r) for r in rows if r["event_id"] not in mapped]
        if not unmapped:
            return
        print(f"  [修复] 发现 {len(unmapped)} 个事件缺少股票映射，正在处理...")
        td = ThemeDiscovery()
        for i, event in enumerate(unmapped, 1):
            try:
                eid = event["event_id"]
                keywords = json.loads(event.get("keywords_json") or "[]")
                industry = event.get("industry") or ""
                evt_dict = {"keywords": keywords, "industry": industry}
                self.stock_service.process_event_stocks(eid, evt_dict)
                kg_result = self.knowledge_graph.reason(keywords, industry)
                self._save_kg_result(eid, kg_result)
                self.market_verifier.verify_event(eid, industry, keywords)
                td.discover(keywords, industry)
                if i % 20 == 0:
                    print(f"  [修复] {i}/{len(unmapped)}")
            except Exception as e:
                print(f"  [修复失败] event_id={event['event_id']}: {e}")
        self.scoring_engine.calculate(hours=72)
        print(f"  [修复] 完成 {len(unmapped)} 个事件")

    def _analyze_backlog(self):
        """启动时检查并处理所有未分析新闻"""
        backlog = self.collector.get_unanalyzed_news(limit=200)
        if not backlog:
            self._repair_stock_mappings()
            return
        print(f"  [启动] 发现 {len(backlog)} 条未分析新闻，开始分析...")
        analyzed_ids = []
        for item in backlog:
            try:
                event = self.event_service.process_news_item(item)
                analyzed_ids.append(item["id"])
                event_id = self._get_last_event_id()
                if event_id:
                    self.stock_service.process_event_stocks(event_id, event)
                    kg_result = self.knowledge_graph.reason(
                        event.get("keywords", []),
                        event.get("industry", ""),
                        companies=event.get("companies", []),
                    )
                    self._save_kg_result(event_id, kg_result)
                    self.market_verifier.verify_event(
                        event_id,
                        event.get("industry", ""),
                        event.get("keywords", []),
                    )
            except Exception as e:
                print(f"  [分析失败] {item.get('title', '')[:30]}: {e}")
        if analyzed_ids:
            self.collector.mark_analyzed(analyzed_ids)
            self.scoring_engine.calculate(hours=72)
            print(f"  [启动] 已完成 {len(analyzed_ids)} 条分析")
        self._repair_stock_mappings()

    def _print_ranking(self, stocks: list):
        print(f"\n  ── TOP 推荐榜 ──")
        print(f"  {'#':3s} {'代码':7s} {'名称':7s} {'总分':5s} {'事件':5s} {'受益':5s} {'市场':5s}")
        for s in stocks:
            print(f"  {s['rank']:3d} {s['stock_code']:7s} {s['stock_name']:6s}  "
                  f"{s['total_score']:4d}  {s['event_score']:4d}  {s['benefit_score']:4d}  {s['market_score']:4d}")
        print()

    def run(self):
        self._analyze_backlog()
        self._tick()

    def run_loop(self, interval=None):
        if interval is None:
            interval = Config.FETCH_INTERVAL_SECONDS
        self._analyze_backlog()
        print(f"\n  [循环模式] 间隔 {interval}s，按 Ctrl+C 停止")
        while True:
            try:
                self._tick()
            except KeyboardInterrupt:
                print("\n  [停止] 用户中断")
                break
            except Exception as e:
                print(f"  [错误] {e}")
            print(f"\n  [等待] {interval} 秒后下一轮...")
            time.sleep(interval)
