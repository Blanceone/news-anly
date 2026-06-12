import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Optional

import feedparser
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
        if source_type == "rss":
            return self._collect_rss(source_id, config)
        elif source_type == "api":
            return self._collect_api(source_id, config)
        elif source_type == "api_json":
            return self._collect_api_json(source_id, config)
        return []

    def _collect_rss(self, source_id: str, config: dict) -> list:
        url = config.get("rss_url", config.get("url", ""))
        if not url:
            return []
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:30]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            content = entry.get("summary", entry.get("description", ""))
            pub_time = entry.get("published_parsed")
            items.append({
                "title": title,
                "content": BeautifulSoup(content, "html.parser").get_text() if content else "",
                "url": link,
                "source": source_id,
                "source_name": config["name"],
                "created_at": datetime(*pub_time[:6]) if pub_time else datetime.now(),
            })
        return items

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
        cookies = config.get("cookies", {})
        try:
            resp = requests.get(api_url, headers=headers, cookies=cookies, timeout=15)
            resp.encoding = "utf-8"
            data = resp.json()
        except Exception:
            return []
        items = []

        if source_id == "wallstreetcn":
            for item in data.get("data", {}).get("items", []):
                title = item.get("title", "") or item.get("content_text", "")[:80]
                items.append({
                    "title": title,
                    "content": item.get("content_text", ""),
                    "url": f"https://wallstreetcn.com/live/global/{item.get('id')}",
                    "source": source_id,
                    "source_name": config["name"],
                    "created_at": datetime.now(),
                })

        elif source_id == "cls":
            data = data.get("data", {})
            if isinstance(data, dict):
                items_list = data.get("roll_list", data.get("list", data.get("data", [])))
            elif isinstance(data, list):
                items_list = data
            else:
                items_list = []
            for item in items_list:
                if isinstance(item, dict):
                    title = item.get("title", "") or item.get("content", "")[:80]
                    items.append({
                        "title": title,
                        "content": BeautifulSoup(item.get("content", ""), "html.parser").get_text(),
                        "url": f"https://www.cls.cn/detail/{item.get('id')}",
                        "source": source_id,
                        "source_name": config["name"],
                        "created_at": datetime.now(),
                    })

        elif source_id == "xueqiu":
            items_list = data.get("data", {}).get("items", data.get("list", data.get("data", [])))
            for item in items_list:
                if isinstance(item, dict):
                    title = item.get("title", "") or item.get("name", "")
                    items.append({
                        "title": title,
                        "content": item.get("text", "") or item.get("description", ""),
                        "url": f"https://xueqiu.com/{item.get('user_id', item.get('userId', ''))}/{item.get('id', '')}",
                        "source": source_id,
                        "source_name": config["name"],
                        "created_at": datetime.now(),
                    })

        return items

    def _collect_api_json(self, source_id: str, config: dict) -> list:
        api_url = config.get("api_url", "")
        if not api_url:
            return []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": config.get("url", ""),
        }
        try:
            resp = requests.get(api_url, headers=headers, timeout=15)
            resp.encoding = "utf-8"
            data = resp.json()
        except Exception:
            return []
        items = []
        return items

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
