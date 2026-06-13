import os
from datetime import datetime

from collectors import NewsCollector
from core.analyzer import NewsAnalyzer
from core.web_generator import WebGenerator
from core.feishu_pusher import FeishuPusher


class NewsScheduler:
    def __init__(self):
        self.collector = NewsCollector()
        self.analyzer = NewsAnalyzer()
        self.web = WebGenerator("output")
        self.pusher = FeishuPusher()
        self.reports = []

    def pre_market(self):
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%H:%M')}] 执行盘前汇总...")
        print(f"{'='*50}")
        news = self.collector.collect_all()
        weekday = datetime.now().weekday()
        window = 72 if weekday == 0 else 18
        self._filter_recent(news, hours=window)
        summary = self.analyzer.summarize_news(news)
        report_title = f"盘前必读 ({datetime.now().strftime('%m-%d')})"
        filepath = self.web.generate_report("pre_market", report_title, summary, news)
        self._save_report("pre_market", report_title, summary, filepath)
        self.pusher.push_report("pre_market", report_title, summary)
        self.pusher.push_news(news[:8], "pre_market")
        print(f"  [完成] 盘前汇总")

    def intraday(self):
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%H:%M')}] 执行盘中采集...")
        print(f"{'='*50}")
        news = self.collector.collect_all()
        self._filter_recent(news, hours=2)
        if not news:
            print("  无新新闻")
            return
        self.pusher.push_news(news[:10], "intraday")

    def post_market(self):
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%H:%M')}] 执行盘后复盘...")
        print(f"{'='*50}")
        news = self.collector.get_recent_news(hours=12, limit=200)
        summary = self.analyzer.summarize_news(news)
        report_title = f"盘后复盘 ({datetime.now().strftime('%m-%d')})"
        filepath = self.web.generate_report("post_market", report_title, summary, news)
        self._save_report("post_market", report_title, summary, filepath)
        self.pusher.push_report("post_market", report_title, summary)
        print(f"  [完成] 盘后复盘")

    def generate_site(self):
        self.web.generate_index(self.reports)

    def _filter_recent(self, news, hours=24):
        cutoff = datetime.now().timestamp() - hours * 3600
        news[:] = [n for n in news if _ts(n) > cutoff]

    def _save_report(self, report_type, title, content, html_path):
        import sqlite3
        try:
            with sqlite3.connect("news.db") as conn:
                conn.execute("""
                    INSERT INTO reports (type, title, content, html_path, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (report_type, title, content, html_path, datetime.now().isoformat()))
            self.reports = self._load_reports()
        except Exception:
            self.reports = [{"type": report_type, "title": title, "html_path": html_path,
                           "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}]

    def _load_reports(self):
        import sqlite3
        try:
            with sqlite3.connect("news.db") as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT type, title, html_path, created_at FROM reports ORDER BY id DESC LIMIT 20"
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []


def _ts(item):
    t = item.get("created_at", "")
    if isinstance(t, str):
        try:
            return datetime.fromisoformat(t).timestamp()
        except Exception:
            return 0
    if isinstance(t, datetime):
        return t.timestamp()
    return 0
