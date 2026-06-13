"""双数据库初始化 — news.db + stocks.db"""
import sqlite3
from config import Config


def init_news_db():
    with sqlite3.connect(Config.NEWS_DB) as conn:
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


def init_stocks_db():
    with sqlite3.connect(Config.STOCKS_DB) as conn:
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
            CREATE TABLE IF NOT EXISTS sector_cache (
                name TEXT PRIMARY KEY,
                change REAL,
                up INTEGER,
                down INTEGER,
                volume REAL,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kg_entity (
                entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                UNIQUE(entity_type, name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kg_relation (
                relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_name TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_name TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                weight REAL DEFAULT 0,
                UNIQUE(source_type, source_name, target_type, target_name, relation_type)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kg_direct_benefit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_name TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                weight REAL NOT NULL,
                reason TEXT,
                UNIQUE(source_type, source_name, stock_code)
            )
        """)
        conn.commit()
