import time
from datetime import datetime

from config import Config
from collectors import NewsCollector
from core.analyzer import NewsAnalyzer
from core.feishu_pusher import FeishuPusher
from services.event_service import EventService


class NewsScheduler:
    def __init__(self):
        self.collector = NewsCollector()
        self.analyzer = NewsAnalyzer()
        self.pusher = FeishuPusher()
        self.event_service = EventService()

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
                self.event_service.process_news_item(item)
            self.collector.mark_analyzed([item["id"] for item in unanalyzed])
        else:
            print("  无待分析新闻")

        if new_news:
            self.pusher.push_news(new_news[:10])
            summary = self.analyzer.summarize_news(self.collector.get_recent_news(hours=24, limit=100))
            if summary:
                self.pusher.push_report(summary)
        else:
            print("  无新新闻，跳过推送")

        print(f"  [完成] 本次采集")
        return bool(new_news)

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
