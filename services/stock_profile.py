"""Stock Profile 引擎 — Phase 3 (V3)

建立股票画像，区分龙头股和跟风股。
指标：流动性(20%) + 活跃度(30%) + 题材数(20%) + 涨停历史(30%)
"""
import sqlite3
from datetime import datetime, timedelta


class StockProfile:
    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self._init_table()

    def _init_table(self):
        with sqlite3.connect(self.db_path) as conn:
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
            conn.commit()

    def _last_trade_date(self):
        d = datetime.today()
        while True:
            if d.weekday() < 5:
                return d.strftime("%Y%m%d")
            d -= timedelta(days=1)

    def calculate(self):
        """计算所有股票的画像和龙头评分"""
        import tushare as ts
        from config import Config
        pro = ts.pro_api(Config.TUSHARE_TOKEN)

        # 1. 获取全部股票基础信息
        sb = pro.stock_basic(fields='ts_code,name,industry')
        stock_map = {}
        for _, row in sb.iterrows():
            code = str(row["ts_code"])
            stock_map[code] = {"name": str(row.get("name", "")),
                               "industry": str(row.get("industry", "") or "")}

        # 2. 近20日行情 — 获取最近一个交易日后向前拉取
        tdate = self._last_trade_date()
        daily = pro.daily(trade_date=tdate)
        if daily.empty:
            for _ in range(10):
                td = datetime.strptime(tdate, "%Y%m%d") - timedelta(days=1)
                tdate = td.strftime("%Y%m%d")
                daily = pro.daily(trade_date=tdate)
                if not daily.empty:
                    break

        chg_map = {}
        if not daily.empty:
            for _, row in daily.iterrows():
                code = str(row["ts_code"])
                if code not in chg_map:
                    chg_map[code] = {}
                chg_map[code]["amount"] = float(row.get("amount", 0) or 0)
                chg_map[code]["pct_chg"] = float(row.get("pct_chg", 0) or 0)

        # 近20日daily_basic (换手率)
        turnover_map = {}
        db20 = pro.daily_basic(trade_date=tdate, fields='ts_code,turnover_rate,total_mv')
        if not db20.empty:
            for _, row in db20.iterrows():
                code = str(row["ts_code"])
                turnover_map[code] = {
                    "turnover": float(row.get("turnover_rate", 0) or 0),
                    "market_value": float(row.get("total_mv", 0) or 0) / 1e8,
                }

        # 3. 涨停历史
        limitup = {}
        try:
            year_ago = (datetime.strptime(tdate, "%Y%m%d") - timedelta(days=365)).strftime("%Y%m%d")
            lu = pro.limit_list(start_date=year_ago, end_date=tdate)
            if not lu.empty:
                for _, row in lu.iterrows():
                    code = str(row["ts_code"])
                    limitup[code] = limitup.get(code, 0) + 1
        except Exception:
            pass

        # 4. 主题计数
        theme_counts = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT stock_code, COUNT(*) as cnt FROM theme_stock_mapping GROUP BY stock_code"
                ).fetchall()
                theme_counts = {r[0]: r[1] for r in rows}
        except Exception:
            pass

        # 5. 计算龙头评分
        records = []
        for code, info in stock_map.items():
            if not code.startswith(("0", "3", "6")) or code.endswith(".BJ"):
                continue
            d = chg_map.get(code, {})
            t = turnover_map.get(code, {})
            liquidity = t.get("market_value", d.get("amount", 0) / 1e8)
            turnover = t.get("turnover", 0)
            vol = abs(d.get("pct_chg", 0))
            lu_count = limitup.get(code, 0)
            tc = theme_counts.get(code, 0)

            records.append({
                "stock_code": code,
                "stock_name": info["name"],
                "industry": info["industry"],
                "market_cap": round(liquidity, 2),
                "turnover_rate": round(turnover, 2),
                "theme_count": tc,
                "volatility": round(vol, 2),
                "limitup_history": lu_count,
            })

        if not records:
            for code, info in stock_map.items():
                if not code.startswith(("0", "3", "6")) or code.endswith(".BJ"):
                    continue
                tc = theme_counts.get(code, 0)
                records.append({
                    "stock_code": code, "stock_name": info["name"],
                    "industry": info["industry"],
                    "market_cap": 0, "turnover_rate": 0,
                    "theme_count": tc, "volatility": 0, "limitup_history": 0,
                })

        max_vals = {}
        for key in ("market_cap", "turnover_rate", "theme_count", "limitup_history"):
            vals = [r[key] for r in records]
            max_vals[key] = max(vals) if vals else 1

        for r in records:
            liq = (min(r["market_cap"], max_vals["market_cap"]) / max_vals["market_cap"]) * 20
            act = (min(r["turnover_rate"], max_vals["turnover_rate"]) / max_vals["turnover_rate"]) * 30
            tc = (min(r["theme_count"], max_vals["theme_count"]) / max_vals["theme_count"]) * 20
            lu = (min(r["limitup_history"], max_vals["limitup_history"]) / max_vals["limitup_history"]) * 30
            r["leader_score"] = round(liq + act + tc + lu)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM stock_profile")
            for r in records:
                conn.execute("""
                    INSERT INTO stock_profile
                        (stock_code, stock_name, market_cap, turnover_rate, theme_count,
                         industry, volatility, limitup_history, leader_score, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (r["stock_code"], r["stock_name"], r["market_cap"],
                      r["turnover_rate"], r["theme_count"], r["industry"],
                      r["volatility"], r["limitup_history"], r["leader_score"],
                      datetime.now().isoformat()))
            conn.commit()
        return records

    def get_leader_score(self, stock_code: str) -> float:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT leader_score FROM stock_profile WHERE stock_code=?",
                    (stock_code,)
                ).fetchone()
                return row[0] if row else 0
        except Exception:
            return 0
