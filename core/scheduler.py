from datetime import datetime

from collectors import NewsCollector
from core.analyzer import NewsAnalyzer
from core.feishu_pusher import FeishuPusher


class NewsScheduler:
    def __init__(self):
        self.collector = NewsCollector()
        self.analyzer = NewsAnalyzer()
        self.pusher = FeishuPusher()

    def run(self):
        now = datetime.now()
        print(f"\n{'='*50}")
        print(f"[{now.strftime('%H:%M')}] 开始增量采集...")
        print(f"{'='*50}")

        last_fetch = self.collector.get_last_fetch_time()
        print(f"  上次采集时间: {last_fetch.strftime('%Y-%m-%d %H:%M')}")

        new_news = self.collector.collect_since(last_fetch)
        print(f"  新增 {len(new_news)} 条新闻")

        unanalyzed = self.collector.get_unanalyzed_news(limit=50)
        if unanalyzed:
            print(f"  待分析 {len(unanalyzed)} 条新闻")
            analyzed_ids = self.analyzer.analyze_batch(unanalyzed)
            self.collector.mark_analyzed(analyzed_ids)
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
