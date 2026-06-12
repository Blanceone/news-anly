import os
from datetime import datetime
from collector import NewsCollector
from analyzer import NewsAnalyzer
from web_generator import WebGenerator
from feishu_pusher import FeishuPusher


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
        news = [n for n in news if self._is_recent(n, hours=18)]
        print(f"  获取到 {len(news)} 条隔夜/盘前新闻")
        summary = self.analyzer.summarize_news(news)
        report_title = f"盘前必读 ({datetime.now().strftime('%m-%d')})"
        filepath = self.web.generate_report("pre_market", report_title, summary, news)
        self._save_report("pre_market", report_title, summary, filepath)
        self.pusher.push_report("pre_market", report_title, summary,
                                web_url=self._get_page_url(filepath))
        self.pusher.push_news(news[:8], "pre_market")
        print(f"  [完成] 盘前汇总")

    def intraday(self):
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%H:%M')}] 执行盘中采集...")
        print(f"{'='*50}")
        news = self.collector.collect_all()
        news = [n for n in news if self._is_recent(n, hours=2)]
        if not news:
            print("  无新新闻")
            return
        print(f"  新增 {len(news)} 条新闻")
        self.pusher.push_news(news[:10], "intraday")
        print(f"  [完成] 盘中推送")

    def post_market(self):
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%H:%M')}] 执行盘后复盘...")
        print(f"{'='*50}")
        news = self.collector.get_recent_news(hours=12, limit=200)
        print(f"  今日共 {len(news)} 条新闻")
        summary = self.analyzer.summarize_news(news)
        report_title = f"盘后复盘 ({datetime.now().strftime('%m-%d')})"
        filepath = self.web.generate_report("post_market", report_title, summary, news)
        self._save_report("post_market", report_title, summary, filepath)
        self.pusher.push_report("post_market", report_title, summary,
                                web_url=self._get_page_url(filepath))
        print(f"  [完成] 盘后复盘")

    def generate_site(self):
        self.web.generate_index(self.reports)

    def _is_recent(self, item, hours=24):
        try:
            t = datetime.fromisoformat(item["created_at"]) if isinstance(item["created_at"], str) else item["created_at"]
            return (datetime.now() - t).total_seconds() < hours * 3600
        except Exception:
            return True

    def _save_report(self, report_type, title, content, html_path):
        from datetime import datetime
        import sqlite3
        try:
            with sqlite3.connect("news.db") as conn:
                conn.execute("""
                    INSERT INTO reports (type, title, content, html_path, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (report_type, title, content, html_path, datetime.now().isoformat()))
            self.reports = self._get_reports()
        except Exception:
            self.reports = [{"type": report_type, "title": title, "html_path": html_path,
                           "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}]

    def _get_reports(self):
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

    def _get_page_url(self, filepath):
        filename = os.path.basename(filepath)
        return f"https://你的github用户名.github.io/仓库名/{filename}"
