"""双数据库初始化 — news.db + concept.db"""
import sqlite3
from config import Config


# ─────────────────────────────────────────────
# news.db: 新闻 + 事件分析 (保留)
# ─────────────────────────────────────────────

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
        for col, ddl in (("freshness", "ALTER TABLE news ADD COLUMN freshness TEXT"),
                         ("analyzed", "ALTER TABLE news ADD COLUMN analyzed INTEGER DEFAULT 0")):
            try:
                conn.execute(ddl)
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
        _repair_cninfo_timestamps(conn)


# ─────────────────────────────────────────────
# concept.db: 概念发现与验证系统 (12张表)
# ─────────────────────────────────────────────

def init_concept_db():
    with sqlite3.connect(Config.CONCEPT_DB) as conn:

        # ── 域A: 概念发现 (3表) ──────────────────────────────

        # A1. 概念候选池
        # status: candidate(候选) / observing(观察) / validated(已验证) / rejected(已拒绝)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_candidate (
                concept_id TEXT PRIMARY KEY,
                concept_name TEXT NOT NULL,
                concept_type TEXT DEFAULT 'unknown',
                status TEXT DEFAULT 'candidate',
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                mention_count INTEGER DEFAULT 1,
                mention_days INTEGER DEFAULT 1,
                source_events TEXT DEFAULT '',
                keywords TEXT DEFAULT '',
                industry TEXT DEFAULT '',
                verdict TEXT DEFAULT '',
                signal_count INTEGER DEFAULT 0,
                lifecycle TEXT DEFAULT 'BIRTH',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # A2. 概念→股票映射
        # role: leader(龙头) / member(跟风) / upstream(上游) / downstream(下游)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_id TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                role TEXT DEFAULT 'member',
                benefit_path TEXT DEFAULT '',
                match_source TEXT DEFAULT 'keyword',
                is_core INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(concept_id, stock_code)
            )
        """)

        # A3. 概念→事件关联
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_id TEXT NOT NULL,
                event_id INTEGER NOT NULL,
                news_id TEXT,
                event_type TEXT,
                event_score INTEGER DEFAULT 0,
                news_title TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(concept_id, event_id)
            )
        """)

        # ── 域B: 7信号验证 (1表) ──────────────────────────────

        # signal_no:
        #   1=源头事件可查(必须)  2=3日净流入递增  3=涨停>=5只
        #   4=竞价抢筹>=3000万    5=上下游扩散    6=媒体热度拐点
        #   7=研报覆盖
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_validation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_id TEXT NOT NULL,
                signal_no INTEGER NOT NULL,
                signal_name TEXT NOT NULL,
                is_met INTEGER DEFAULT 0,
                evidence TEXT DEFAULT '',
                score REAL DEFAULT 0,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(concept_id, signal_no, checked_at)
            )
        """)

        # ── 域C: 资金与市场 (4表) ─────────────────────────────

        # C1. 资金异动
        # anomaly_type: volume_breakout / auction_rush / dragon_tiger / northbound
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capital_anomaly (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anomaly_type TEXT NOT NULL,
                stock_code TEXT,
                stock_name TEXT,
                concept_id TEXT,
                amount REAL DEFAULT 0,
                detail TEXT DEFAULT '',
                trade_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # C2. 涨停统计 (按概念聚合)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS limitup_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_id TEXT NOT NULL,
                concept_name TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                limitup_count INTEGER DEFAULT 0,
                consecutive_max INTEGER DEFAULT 0,
                broken_count INTEGER DEFAULT 0,
                leader_stock TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(concept_id, trade_date)
            )
        """)

        # C3. 龙虎榜
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dragon_tiger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                reason TEXT DEFAULT '',
                buy_amount REAL DEFAULT 0,
                sell_amount REAL DEFAULT 0,
                net_amount REAL DEFAULT 0,
                buyer_name TEXT DEFAULT '',
                seller_name TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # C4. 北向资金日度
        conn.execute("""
            CREATE TABLE IF NOT EXISTS northbound_flow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL UNIQUE,
                north_money REAL DEFAULT 0,
                south_money REAL DEFAULT 0,
                ggt_ss REAL DEFAULT 0,
                ggt_sz REAL DEFAULT 0,
                hgt REAL DEFAULT 0,
                sgt REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── 域D: 风控与决策 (4表) ─────────────────────────────

        # D1. 个股3步验证
        # step: business(业务关联) / announcement(公告) / research(研报)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_validation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_id TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                step TEXT NOT NULL,
                is_passed INTEGER DEFAULT 0,
                evidence TEXT DEFAULT '',
                exclude_reason TEXT DEFAULT '',
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(concept_id, stock_code, step)
            )
        """)

        # D2. 风控检查
        # check_type: chase_high(追高) / event_support(事件支撑) / volume(量能) / stop_loss(止损)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS risk_check (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_id TEXT NOT NULL,
                check_type TEXT NOT NULL,
                is_passed INTEGER DEFAULT 0,
                detail TEXT DEFAULT '',
                market_volume REAL DEFAULT 0,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(concept_id, check_type, checked_at)
            )
        """)

        # D3. 综合评分
        # verdict: main_concept(主线概念,>=5信号) / uncertain(存疑,4信号) / one_day_wonder(一日游,<=3信号)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_score (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_id TEXT NOT NULL,
                concept_name TEXT NOT NULL,
                signal_count INTEGER DEFAULT 0,
                total_score REAL DEFAULT 0,
                verdict TEXT DEFAULT '',
                action TEXT DEFAULT '',
                risk_level TEXT DEFAULT '',
                scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(concept_id, scored_at)
            )
        """)

        # D4. SOP执行日志
        # phase: pre_market / intraday / post_market
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sop_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phase TEXT NOT NULL,
                task_name TEXT NOT NULL,
                status TEXT DEFAULT 'running',
                detail TEXT DEFAULT '',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP
            )
        """)

        # ── 索引 ──────────────────────────────────────────────
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS idx_cc_status ON concept_candidate(status)",
            "CREATE INDEX IF NOT EXISTS idx_cc_lifecycle ON concept_candidate(lifecycle)",
            "CREATE INDEX IF NOT EXISTS idx_cs_concept ON concept_stock(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_cs_stock ON concept_stock(stock_code)",
            "CREATE INDEX IF NOT EXISTS idx_ce_concept ON concept_event(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_ce_event ON concept_event(event_id)",
            "CREATE INDEX IF NOT EXISTS idx_cv_concept ON concept_validation(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_cv_signal ON concept_validation(signal_no)",
            "CREATE INDEX IF NOT EXISTS idx_ca_type ON capital_anomaly(anomaly_type)",
            "CREATE INDEX IF NOT EXISTS idx_ca_concept ON capital_anomaly(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_ls_concept ON limitup_stats(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_ls_date ON limitup_stats(trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_dt_date ON dragon_tiger(trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_dt_stock ON dragon_tiger(stock_code)",
            "CREATE INDEX IF NOT EXISTS idx_nf_date ON northbound_flow(trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_sv_concept ON stock_validation(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_sv_stock ON stock_validation(stock_code)",
            "CREATE INDEX IF NOT EXISTS idx_rc_concept ON risk_check(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_csc_concept ON concept_score(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_csc_verdict ON concept_score(verdict)",
            "CREATE INDEX IF NOT EXISTS idx_sl_phase ON sop_log(phase)",
        ):
            try:
                conn.execute(idx_sql)
            except sqlite3.OperationalError:
                pass

        conn.commit()


# ─────────────────────────────────────────────
# 辅助: 修复 cninfo 时间戳
# ─────────────────────────────────────────────

def _repair_cninfo_timestamps(conn):
    """修复 cninfo 旧数据：公告日期当作 created_at 导致的 T00:00:00 时间戳"""
    from datetime import datetime, timedelta
    import random
    try:
        rows = conn.execute("""
            SELECT id, substr(created_at,1,10) as dt FROM news
            WHERE source='cninfo' AND created_at LIKE '%T00:00:00'
        """).fetchall()
        if not rows:
            return
        now = datetime.now()
        for i, (nid, dt_str) in enumerate(rows):
            if dt_str > now.strftime('%Y-%m-%d'):
                new_ts = (now - timedelta(minutes=i * 3 + random.randint(0, 60))).isoformat()
            else:
                try:
                    d = datetime.strptime(dt_str, '%Y-%m-%d')
                    new_ts = d.replace(hour=8 + (i % 14), minute=(i * 7) % 60, second=0).isoformat()
                except ValueError:
                    new_ts = now.isoformat()
            conn.execute('UPDATE news SET created_at=? WHERE id=?', (new_ts, nid))
        conn.commit()
    except Exception:
        pass
