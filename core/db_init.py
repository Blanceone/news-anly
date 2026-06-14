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
                benefit_type TEXT DEFAULT 'DIRECT',
                benefit_path TEXT,
                match_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for col in ("benefit_type", "benefit_path"):
            try:
                conn.execute(f"ALTER TABLE event_stock_mapping ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        # 确保唯一约束防止重复映射
        try:
            # 先清理已存在的重复记录（保留 id 最小的那条）
            conn.execute("""
                DELETE FROM event_stock_mapping WHERE id NOT IN (
                    SELECT MIN(id) FROM event_stock_mapping
                    GROUP BY event_id, stock_code
                )
            """)
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_esm_event_stock ON event_stock_mapping(event_id, stock_code)")
        except (sqlite3.OperationalError, sqlite3.IntegrityError):
            pass
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS theme_candidate (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                theme_name TEXT NOT NULL UNIQUE,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                mention_count INTEGER DEFAULT 1,
                heat_score REAL DEFAULT 0,
                status TEXT DEFAULT 'candidate'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS theme_embedding (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                theme_name TEXT NOT NULL UNIQUE,
                description TEXT,
                embedding BLOB
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_cluster (
                cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
                main_event_id INTEGER,
                event_count INTEGER DEFAULT 1,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                heat_score REAL DEFAULT 0,
                birth_time TIMESTAMP,
                peak_time TIMESTAMP,
                decline_time TIMESTAMP,
                status TEXT DEFAULT 'BIRTH'
            )
        """)
        for col in ("birth_time", "peak_time", "decline_time", "status"):
            try:
                conn.execute(f"ALTER TABLE event_cluster ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_cluster_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS theme_heat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                theme_name TEXT NOT NULL,
                heat_score REAL DEFAULT 0,
                decay_heat REAL DEFAULT 0,
                mention_count INTEGER DEFAULT 0,
                board_change REAL DEFAULT 0,
                board_volume REAL DEFAULT 0,
                last_active_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Fix TEXT→REAL for decay_heat (early version used TEXT)
        try:
            col_info = conn.execute("PRAGMA table_info(theme_heat)").fetchall()
            dhtype = next((r[2] for r in col_info if r[1] == "decay_heat"), "")
            if dhtype and dhtype.upper() == "TEXT":
                conn.execute("DROP TABLE IF EXISTS theme_heat_tmp")
                conn.execute("CREATE TABLE theme_heat_tmp AS SELECT * FROM theme_heat")
                conn.execute("DROP TABLE theme_heat")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS theme_heat (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        theme_name TEXT NOT NULL,
                        heat_score REAL DEFAULT 0,
                        decay_heat REAL DEFAULT 0,
                        mention_count INTEGER DEFAULT 0,
                        board_change REAL DEFAULT 0,
                        board_volume REAL DEFAULT 0,
                        last_active_time TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("INSERT OR IGNORE INTO theme_heat(theme_name,heat_score,decay_heat,mention_count,board_change,board_volume,last_active_time) SELECT theme_name,heat_score,CAST(decay_heat AS REAL),mention_count,board_change,board_volume,last_active_time FROM theme_heat_tmp")
                conn.execute("DROP TABLE theme_heat_tmp")
        except Exception:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_profile (
                stock_code TEXT PRIMARY KEY,
                stock_name TEXT NOT NULL,
                market_cap REAL DEFAULT 0,
                turnover_rate REAL DEFAULT 0,
                theme_count INTEGER DEFAULT 0,
                industry TEXT DEFAULT '',
                volatility REAL DEFAULT 0,
                limitup_history INTEGER DEFAULT 0,
                leader_score REAL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS theme_limitup_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                theme_name TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                limitup_count INTEGER DEFAULT 0,
                consecutive_count INTEGER DEFAULT 0,
                broken_count INTEGER DEFAULT 0,
                UNIQUE(theme_name, trade_date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_result (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_type TEXT,
                start_date TEXT,
                end_date TEXT,
                holding_days INTEGER,
                win_rate REAL,
                avg_return REAL,
                max_drawdown REAL,
                sharpe_ratio REAL,
                excess_return REAL,
                total_trades INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backtest_id INTEGER,
                trade_date TEXT,
                stock_code TEXT,
                stock_name TEXT,
                buy_price REAL,
                sell_price REAL,
                holding_days INTEGER,
                return_rate REAL,
                strategy_type TEXT
            )
        """)
        conn.commit()
