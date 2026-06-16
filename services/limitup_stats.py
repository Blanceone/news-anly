"""涨停热度系统 — Phase 4 (V3)

每日统计各主题涨停/连板/炸板数据。
集成到 ThemeHeat 公式: 新闻40% + 板块45% + 涨停15%（资金热度暂无独立数据源）
"""
import sqlite3
from collections import defaultdict
from datetime import datetime


class LimitupStats:
    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self._init_table()

    def _init_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS theme_limitup_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    theme_name TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    limitup_count INTEGER DEFAULT 0,
                    consecutive_count INTEGER DEFAULT 0,
                    broken_count INTEGER DEFAULT 0,
                    first_limitup_count INTEGER DEFAULT 0,
                    UNIQUE(theme_name, trade_date)
                )
            """)
            # 确保 first_limitup_count 列存在
            try:
                conn.execute("ALTER TABLE theme_limitup_stats ADD COLUMN first_limitup_count INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def calculate(self):
        """获取每日涨停数据并按主题聚合"""
        import tushare as ts
        from config import Config
        pro = ts.pro_api(Config.TUSHARE_TOKEN)
        tdate = self._last_trade_date()

        limit_list = pro.limit_list(trade_date=tdate)
        if limit_list.empty:
            # 非交易日回退前一天
            from datetime import timedelta
            td = datetime.strptime(tdate, "%Y%m%d") - timedelta(days=1)
            tdate = td.strftime("%Y%m%d")
            limit_list = pro.limit_list(trade_date=tdate)
        if limit_list.empty:
            return {}

        # 获取前一交易日涨停股票，用于判断连板/首板 (PRD: first_limitup_count)
        prev_limitup_codes = set()
        try:
            from datetime import timedelta
            prev_date = (datetime.strptime(tdate, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
            prev_list = pro.limit_list(trade_date=prev_date)
            if not prev_list.empty:
                for _, row in prev_list.iterrows():
                    if str(row.get("limit_type", "")) == 'U':
                        prev_limitup_codes.add(str(row["ts_code"]))
        except Exception:
            pass

        # 获取 theme_stock_mapping 中每只股票对应的主题
        stock_themes = defaultdict(set)
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT stock_code, theme_name FROM theme_stock_mapping"
                ).fetchall()
                for r in rows:
                    stock_themes[r[0]].add(r[1])
        except Exception:
            pass

        # 统计各主题的涨停数据
        theme_stats = defaultdict(lambda: {"limitup": 0, "consecutive": 0, "broken": 0, "first": 0})
        for _, row in limit_list.iterrows():
            code = str(row["ts_code"])
            limit_type = str(row.get("limit_type", "") or "")
            for theme in stock_themes.get(code, set()):
                if limit_type == 'U':
                    theme_stats[theme]["limitup"] += 1
                    if code in prev_limitup_codes:
                        theme_stats[theme]["consecutive"] += 1
                    else:
                        theme_stats[theme]["first"] += 1
                elif limit_type == 'D':
                    theme_stats[theme]["broken"] += 1
                else:
                    theme_stats[theme]["limitup"] += 1
                    theme_stats[theme]["first"] += 1

        # 写入 DB
        with sqlite3.connect(self.db_path) as conn:
            for theme, stats in theme_stats.items():
                conn.execute("""
                    INSERT OR REPLACE INTO theme_limitup_stats
                        (theme_name, trade_date, limitup_count, consecutive_count,
                         broken_count, first_limitup_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (theme, tdate, stats["limitup"], stats["consecutive"],
                      stats["broken"], stats["first"]))
            conn.commit()

        return dict(theme_stats)

    def _last_trade_date(self):
        d = datetime.today()
        from datetime import timedelta
        while True:
            if d.weekday() < 5:
                return d.strftime("%Y%m%d")
            d -= timedelta(days=1)

    def get_theme_limitup_heat(self) -> dict:
        """获取各主题涨停热度 score (0-100)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute("""
                    SELECT theme_name, limitup_count, consecutive_count, broken_count
                    FROM theme_limitup_stats ORDER BY trade_date DESC LIMIT 50
                """).fetchall()
                result = {}
                for r in rows:
                    score = r[1] * 10 + r[2] * 20 - r[3] * 5
                    result[r[0]] = max(0, score)
                if result:
                    max_s = max(result.values()) or 1
                    return {k: min(100, v * 100 / max_s) for k, v in result.items()}
                return {}
        except Exception:
            return {}
