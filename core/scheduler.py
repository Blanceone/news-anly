import time
from datetime import datetime

from config import Config
from collectors import NewsCollector
from core.analyzer import NewsAnalyzer
from core.feishu_pusher import FeishuPusher
from services.event_service import EventService
from services.stock_service import StockService
from services.knowledge_graph import KnowledgeGraph


class NewsScheduler:
    def __init__(self):
        self.collector = NewsCollector()
        self.analyzer = NewsAnalyzer()
        self.pusher = FeishuPusher()
        self.event_service = EventService()
        self.stock_service = StockService()
        self.knowledge_graph = KnowledgeGraph()

    def _tick(self) -> bool:
        now = datetime.now()
        print(f"\n{'='*50}")
        print(f"[{now.strftime('%H:%M:%S')}] 开始增量采集...")
        print(f"{'='*50}")

        last_fetch = self.collector.get_last_fetch_time()
        print(f"  上次采集时间: {last_fetch.strftime('%Y-%m-%d %H:%M:%S')}")

        new_news = self.collector.collect_since(last_fetch)
        print(f"  新增 {len(new_news)} 条新闻")

        unanalyzed = self.collector.get_unanalyzed_news(limit=50)
        if unanalyzed:
            print(f"  待分析 {len(unanalyzed)} 条新闻")
            for item in unanalyzed:
                event = self.event_service.process_news_item(item)
                event_id = self._get_last_event_id()
                if event_id:
                    self.stock_service.process_event_stocks(event_id, event)
                    kg_result = self.knowledge_graph.reason(
                        event.get("keywords", []),
                        event.get("industry", ""),
                    )
                    self._save_kg_result(event_id, kg_result)
            self.collector.mark_analyzed([item["id"] for item in unanalyzed])
        else:
            print("  无待分析新闻")

        if new_news:
            self.pusher.push_news(new_news[:10])
            kg_top = self.knowledge_graph.get_top_stocks(limit=10)
            summary = self.analyzer.summarize_news(
                self.collector.get_recent_news(hours=24, limit=100)
            )
            if summary:
                self.pusher.push_report(summary)
            if kg_top:
                self._print_kg_top(kg_top)
        else:
            print("  无新新闻，跳过推送")

        print(f"  [完成] 本次采集")
        return bool(new_news)

    def _get_last_event_id(self):
        import sqlite3
        try:
            with sqlite3.connect("news.db") as conn:
                row = conn.execute("SELECT MAX(event_id) FROM event_analysis").fetchone()
                return row[0]
        except Exception:
            return None

    def _save_kg_result(self, event_id: int, stocks: list):
        if not stocks:
            return
        import sqlite3
        benefit_scores = {1: 95, 2: 80, 3: 60}
        with sqlite3.connect("news.db") as conn:
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

    def _print_kg_top(self, stocks: list):
        print(f"\n  ── 知识图谱 TOP10 受益股 ──")
        for s in stocks:
            themes_str = (s.get("themes") or "")[:30]
            print(f"    {s['stock_code']} {s['stock_name']:6s}  评分{s['score']:.0f}  {themes_str}")
        print()

    def run(self):
        self._tick()

    def run_loop(self, interval=None):
        if interval is None:
            interval = Config.FETCH_INTERVAL_SECONDS
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
