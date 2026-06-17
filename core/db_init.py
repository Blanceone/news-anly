"""双数据库初始化 — news.db + concept.db

严格按 V3 Final Spec 表结构设计。
"""
import sqlite3
from config import Config


# ─────────────────────────────────────────────
# news.db: 新闻 + 事件分析
# ─────────────────────────────────────────────

def init_news_db():
    with sqlite3.connect(Config.NEWS_DB) as conn:
        # news 表 — Spec 2.1 + 兼容采集器所需字段
        conn.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id TEXT PRIMARY KEY,
                source TEXT,
                source_name TEXT,
                url TEXT,
                title TEXT,
                content TEXT,
                publish_time TEXT,
                is_processed INTEGER DEFAULT 0,
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
        # 兼容迁移: 旧表可能缺少的列
        for col, ddl in (
            ("freshness", "ALTER TABLE news ADD COLUMN freshness TEXT"),
            ("analyzed", "ALTER TABLE news ADD COLUMN analyzed INTEGER DEFAULT 0"),
            ("is_processed", "ALTER TABLE news ADD COLUMN is_processed INTEGER DEFAULT 0"),
            ("source_name", "ALTER TABLE news ADD COLUMN source_name TEXT"),
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                pass

        # reports 表 (保留)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                title TEXT,
                content TEXT,
                created_at TIMESTAMP
            )
        """)

        # event_analysis — Spec 2.1
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id TEXT,
                event_type TEXT,
                entities TEXT,
                summary TEXT,
                sentiment TEXT,
                raw_concepts TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        _repair_cninfo_timestamps(conn)


# ─────────────────────────────────────────────
# concept.db: 概念发现与验证系统
# ─────────────────────────────────────────────

def init_concept_db():
    with sqlite3.connect(Config.CONCEPT_DB) as conn:

        # ── 域A: 概念基础 (Spec 2.2) ────────────────────────

        # A1. 概念词典 (标准概念名 + 别名)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_dictionary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                standard_name TEXT UNIQUE NOT NULL,
                aliases TEXT,
                category TEXT,
                status TEXT DEFAULT 'active'
            )
        """)

        # A2. 概念候选池
        # status: candidate / observing / validated
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_candidate (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                standard_name TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'candidate',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                mention_count INTEGER DEFAULT 0,
                last_mention_date DATE
            )
        """)

        # ── 域B: 关联关系 (Spec 2.2) ────────────────────────

        # B1. 概念→股票映射
        # role: leader / member / upstream / downstream
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_stock (
                concept_id INTEGER,
                stock_code TEXT,
                role TEXT,
                is_target INTEGER DEFAULT 0,
                PRIMARY KEY (concept_id, stock_code)
            )
        """)

        # B2. 概念→事件关联
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_event (
                concept_id INTEGER,
                event_id INTEGER,
                trade_date DATE,
                PRIMARY KEY (concept_id, event_id)
            )
        """)

        # ── 域C: 市场与资金数据 (Spec 2.2) ──────────────────

        # C1. 涨停统计 (按概念+日期聚合)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS limitup_stats (
                trade_date DATE,
                concept_id INTEGER,
                limitup_count INTEGER,
                max_consecutive_boards INTEGER,
                PRIMARY KEY (trade_date, concept_id)
            )
        """)

        # C2. 资金异动
        # anomaly_type: volume_breakout / early_morning_rush
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capital_anomaly (
                stock_code TEXT,
                trade_date DATE,
                anomaly_type TEXT,
                detail TEXT,
                PRIMARY KEY (stock_code, trade_date, anomaly_type)
            )
        """)

        # C3. 龙虎榜
        # buyer_type: institution / hot_money / retail
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dragon_tiger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date DATE,
                stock_code TEXT,
                buyer_name TEXT,
                net_buy REAL,
                buyer_type TEXT
            )
        """)

        # C4. 北向资金 (按个股+日期)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS northbound_flow (
                trade_date DATE,
                stock_code TEXT,
                net_buy REAL,
                PRIMARY KEY (trade_date, stock_code)
            )
        """)

        # ── 域D: 验证与决策 (Spec 2.2) ──────────────────────

        # D1. 7信号验证
        # signal_no: 1-7
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_validation (
                concept_id INTEGER,
                trade_date DATE,
                signal_no INTEGER,
                is_met INTEGER,
                evidence TEXT,
                PRIMARY KEY (concept_id, trade_date, signal_no)
            )
        """)

        # D2. 个股3步验证 (单行: relevance/announce_check/report_check)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_validation (
                stock_code TEXT,
                concept_id INTEGER,
                trade_date DATE,
                relevance TEXT,
                announce_check TEXT,
                report_check TEXT,
                PRIMARY KEY (stock_code, concept_id, trade_date)
            )
        """)

        # D3. 风控检查
        # risk_type: chasing_high / no_event_support / low_volume
        conn.execute("""
            CREATE TABLE IF NOT EXISTS risk_check (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_id INTEGER,
                trade_date DATE,
                risk_type TEXT,
                detail TEXT
            )
        """)

        # D4. 综合评分
        # verdict: main_concept / uncertain / one_day_wonder
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_score (
                concept_id INTEGER,
                trade_date DATE,
                signal_count INTEGER,
                verdict TEXT,
                PRIMARY KEY (concept_id, trade_date)
            )
        """)

        # ── SOP日志 (调度器运行记录) ──────────────────────────
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
            "CREATE INDEX IF NOT EXISTS idx_cs_concept ON concept_stock(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_cs_stock ON concept_stock(stock_code)",
            "CREATE INDEX IF NOT EXISTS idx_ce_concept ON concept_event(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_ce_event ON concept_event(event_id)",
            "CREATE INDEX IF NOT EXISTS idx_ls_concept ON limitup_stats(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_ls_date ON limitup_stats(trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_ca_stock ON capital_anomaly(stock_code)",
            "CREATE INDEX IF NOT EXISTS idx_ca_date ON capital_anomaly(trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_dt_date ON dragon_tiger(trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_dt_stock ON dragon_tiger(stock_code)",
            "CREATE INDEX IF NOT EXISTS idx_nf_date ON northbound_flow(trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_nf_stock ON northbound_flow(stock_code)",
            "CREATE INDEX IF NOT EXISTS idx_cv_concept ON concept_validation(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_sv_stock ON stock_validation(stock_code)",
            "CREATE INDEX IF NOT EXISTS idx_rc_concept ON risk_check(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_csc_concept ON concept_score(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_csc_verdict ON concept_score(verdict)",
            "CREATE INDEX IF NOT EXISTS idx_sl_phase ON sop_log(phase)",
            "CREATE INDEX IF NOT EXISTS idx_cd_name ON concept_dictionary(standard_name)",
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
