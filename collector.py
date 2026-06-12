import hashlib
import sqlite3
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from config import Config


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
            try:
                items = self._collect_source(source_id, source_config)
                news.extend(items)
                print(f"  [{source_config['name']}] 获取 {len(items)} 条")
            except Exception as e:
                print(f"  [{source_config['name']}] 失败: {e}")
            time.sleep(1)
        news = self._deduplicate(news)
        self._save_news(news)
        return news

    def _collect_source(self, source_id: str, config: dict) -> list:
        source_type = config.get("type", "rss")
        if source_type == "api":
            return self._collect_api(source_id, config)
        return []

    def _collect_api(self, source_id: str, config: dict) -> list:
        api_url = config.get("api_url", "")
        if not api_url:
            return []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": config.get("url", ""),
        }
        custom_headers = config.get("headers", {})
        headers.update(custom_headers)
        params = config.get("params", {}).copy()
        items = []

        if source_id == "cls":
            ts = int(time.time())
            params["last_time"] = str(ts)
            input_str = "&".join(f"{k}={params[k]}" for k in sorted(params))
            sign = hashlib.md5(hashlib.sha1(input_str.encode()).hexdigest().encode()).hexdigest()
            params["sign"] = sign
            try:
                resp = requests.get(api_url, params=params, headers=headers, timeout=15)
                resp.encoding = "utf-8"
                data = resp.json()
            except Exception:
                return []
            roll_data = data.get("data", {}).get("roll_data", [])
            for item in roll_data:
                title = item.get("title", "") or BeautifulSoup(item.get("content", ""), "html.parser").get_text()[:80]
                items.append({
                    "title": title,
                    "content": BeautifulSoup(item.get("content", ""), "html.parser").get_text(),
                    "url": f"https://www.cls.cn/detail/{item.get('id')}",
                    "source": source_id,
                    "source_name": config["name"],
                    "created_at": datetime.fromtimestamp(item.get("ctime", time.time())),
                })

        elif source_id == "cninfo":
            try:
                resp = requests.post(api_url, data=params, headers=headers, timeout=15)
                resp.encoding = "utf-8"
                data = resp.json()
            except Exception:
                return []
            for ann in data.get("announcements", []):
                title = ann.get("announcementTitle", "")
                sec_name = ann.get("secName", "")
                sec_code = ann.get("secCode", "")
                adjunct_url = ann.get("adjunctUrl", "")
                items.append({
                    "title": f"[{sec_code} {sec_name}] {title}",
                    "content": f"{sec_name}({sec_code}) 发布公告: {title}",
                    "url": f"http://static.cninfo.com.cn/{adjunct_url}" if adjunct_url else "",
                    "source": source_id,
                    "source_name": config["name"],
                    "created_at": self._parse_cninfo_time(ann.get("announcementTime")),
                    "stock_code": sec_code,
                })

        return items

    def _parse_cninfo_time(self, t):
        if isinstance(t, str):
            try:
                return datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        if isinstance(t, (int, float)):
            return datetime.fromtimestamp(t / 1000 if t > 1e10 else t)
        return datetime.now()

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
