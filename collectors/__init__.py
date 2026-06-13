"""采集器 - 数据源注册 + 采集管道"""
import hashlib
import sqlite3
import time
from datetime import datetime, timedelta

from config import Config

from . import cls as source_cls
from . import cninfo as source_cninfo


_HANDLERS = {
    "cls": source_cls,
    "cninfo": source_cninfo,
}


class NewsCollector:
    def __init__(self, db_path="news.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    content TEXT,
                    summary TEXT,
                    source TEXT,
                    source_name TEXT,
                    url TEXT,
                    category TEXT,
                    sentiment TEXT,
                    impact REAL,
                    related_stocks TEXT,
                    ai_analysis TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT,
                    title TEXT,
                    content TEXT,
                    html_path TEXT,
                    created_at TIMESTAMP
                )
            """)
            conn.commit()

    def collect_all(self) -> list:
        news = []
        for source_id, source_config in Config.NEWS_SOURCES.items():
            handler = _HANDLERS.get(source_id)
            if not handler:
                print(f"  [{source_config['name']}] 未找到采集模块")
                continue
            try:
                items = handler.collect(source_config)
                news.extend(items)
                print(f"  [{source_config['name']}] 获取 {len(items)} 条")
            except Exception as e:
                print(f"  [{source_config['name']}] 失败: {e}")
            time.sleep(1)
        news = self._deduplicate(news)
        self._save_news(news)
        self._cleanup_old_news()
        return news

    def _cleanup_old_news(self):
        days = Config.DATA_RETENTION_DAYS
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            deleted = conn.execute("DELETE FROM news WHERE created_at < ?", (cutoff,)).rowcount
            if deleted:
                print(f"  [清理] 已删除 {deleted} 条超过 {days} 天的旧数据")

    def _deduplicate(self, news: list) -> list:
        seen = set()
        result = []
        for item in news:
            key = hashlib.md5(item["title"].encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                item["id"] = key
                result.append(item)
        return result

    def _save_news(self, news: list):
        with sqlite3.connect(self.db_path) as conn:
            for item in news:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO news (id, title, content, source, source_name, url, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        item["id"], item["title"], item["content"],
                        item["source"], item["source_name"], item["url"],
                        item["created_at"].isoformat(), datetime.now().isoformat(),
                    ))
                except Exception:
                    pass

    def get_recent_news(self, hours=24, limit=100) -> list:
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM news WHERE created_at > ? ORDER BY created_at DESC LIMIT ?
            """, (since, limit)).fetchall()
            return [dict(row) for row in rows]

    def get_news_by_stock(self, stock_code: str, hours=72, limit=30) -> list:
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM news WHERE created_at > ?
                AND (title LIKE ? OR content LIKE ?)
                ORDER BY created_at DESC LIMIT ?
            """, (since, f"%{stock_code}%", f"%{stock_code}%", limit)).fetchall()
            return [dict(row) for row in rows]

    def categorize_news(self, news: list) -> dict:
        categorized = {}
        for item in news:
            text = f"{item['title']} {item.get('content', '')}"
            found = False
            for cat, keywords in Config.NEWS_CATEGORIES.items():
                for kw in keywords:
                    if kw in text:
                        if cat not in categorized:
                            categorized[cat] = []
                        categorized[cat].append(item)
                        found = True
                        break
                if found:
                    break
            if not found:
                if "其他" not in categorized:
                    categorized["其他"] = []
                categorized["其他"].append(item)
        return categorized
