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
                    freshness TEXT DEFAULT 'medium',
                    analyzed INTEGER DEFAULT 0,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)
            for col in ("freshness", "analyzed"):
                try:
                    conn.execute(f"ALTER TABLE news ADD COLUMN {col} TEXT" if col == "freshness"
                                 else f"ALTER TABLE news ADD COLUMN {col} INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT,
                    title TEXT,
                    content TEXT,
                    created_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_basic (
                    stock_code TEXT PRIMARY KEY,
                    stock_name TEXT NOT NULL,
                    industry TEXT,
                    market_value REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS theme_stock_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    theme_key TEXT NOT NULL,
                    theme_name TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    benefit_level INTEGER,
                    benefit_reason TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_stock_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    benefit_level INTEGER,
                    benefit_score INTEGER,
                    match_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_confirmation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    board_name TEXT,
                    sector_change REAL,
                    volume_amount REAL,
                    up_count INTEGER,
                    down_count INTEGER,
                    confirmation_score INTEGER,
                    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_score (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    score_date TEXT NOT NULL,
                    event_score REAL DEFAULT 0,
                    benefit_score REAL DEFAULT 0,
                    market_score REAL DEFAULT 0,
                    financial_score REAL DEFAULT 0,
                    technical_score REAL DEFAULT 0,
                    capital_score REAL DEFAULT 0,
                    total_score REAL DEFAULT 0,
                    event_count INTEGER DEFAULT 0,
                    top_events TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recommendation_result (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    strategy_type TEXT NOT NULL,
                    rank_no INTEGER,
                    score REAL,
                    recommendation_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_analysis (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT,
                    source_id TEXT,
                    event_type TEXT,
                    event_subtype TEXT,
                    industry TEXT,
                    sub_industry TEXT,
                    sentiment TEXT,
                    importance TEXT,
                    novelty_score INTEGER,
                    event_score INTEGER,
                    entities_json TEXT,
                    amount REAL,
                    amount_unit TEXT,
                    keywords_json TEXT,
                    ai_summary TEXT,
                    reason TEXT,
                    raw_response TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get_last_fetch_time(self) -> datetime:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT MAX(created_at) FROM news").fetchone()
            if row and row[0]:
                try:
                    return datetime.fromisoformat(row[0])
                except Exception:
                    pass
            return datetime.now() - timedelta(hours=24)

    def collect_since(self, since: datetime) -> list:
        news = []
        for source_id, source_config in Config.NEWS_SOURCES.items():
            handler = _HANDLERS.get(source_id)
            if not handler:
                print(f"  [{source_config['name']}] 未找到采集模块")
                continue
            try:
                items = handler.collect(source_config, since)
                news.extend(items)
                print(f"  [{source_config['name']}] 获取 {len(items)} 条")
            except Exception as e:
                print(f"  [{source_config['name']}] 失败: {e}")
            time.sleep(1)
        news = self._deduplicate(news)
        self._save_news(news)
        self._update_freshness()
        self._cleanup_old_news()
        return news

    def _update_freshness(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE news SET freshness = CASE
                    WHEN created_at > datetime('now', '-1 hour') THEN 'high'
                    WHEN created_at > datetime('now', '-24 hours') THEN 'medium'
                    ELSE 'low'
                END
            """)
            conn.commit()
        print("  [新鲜度] 已更新")

    def _cleanup_old_news(self):
        hours = Config.DATA_RETENTION_HOURS
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            deleted = conn.execute("DELETE FROM news WHERE created_at < ?", (cutoff,)).rowcount
            if deleted:
                print(f"  [清理] 已删除 {deleted} 条超过 {hours} 小时的旧数据")

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

    def get_unanalyzed_news(self, limit=50) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM news WHERE analyzed = 0 ORDER BY created_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(row) for row in rows]

    def mark_analyzed(self, news_ids: list):
        if not news_ids:
            return
        placeholders = ",".join("?" for _ in news_ids)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"UPDATE news SET analyzed = 1 WHERE id IN ({placeholders})", news_ids)
            conn.commit()
        print(f"  [标记] 已标记 {len(news_ids)} 条新闻为已分析")

    def get_recent_news(self, hours=72, limit=200) -> list:
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
