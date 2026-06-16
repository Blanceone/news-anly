"""全市场基本面数据服务 — Phase V4

从 Tushare 获取全市场股票的:
  - 基础信息 (代码/名称/行业)
  - 估值指标 (PE/PB/市值)
  - 交易指标 (换手率/收盘价/涨跌幅)
  - 公司基本面 (主营业务/ROE/毛利率)

写入 stock_fundamentals 表。
"""
import sqlite3
import time
from datetime import datetime, timedelta


class FundamentalsService:
    def __init__(self, db_path=None):
        from config import Config
        self.db_path = db_path or Config.STOCKS_DB
        self._init_tables()

    def _init_tables(self):
        from core.db_init import init_stocks_db
        init_stocks_db()

    def _last_trade_date(self) -> str:
        d = datetime.today()
        while True:
            if d.weekday() < 5:
                return d.strftime("%Y%m%d")
            d -= timedelta(days=1)

    # ─── 全量刷新 ──────────────────────────────────────

    def refresh_all(self) -> int:
        """获取全市场基本面数据，写入 stock_fundamentals"""
        import tushare as ts
        from config import Config
        pro = ts.pro_api(Config.TUSHARE_TOKEN)

        tdate = self._last_trade_date()

        # 1. 全市场基础信息
        print("  [基本面] 获取股票基础信息...")
        sb = pro.stock_basic(fields='ts_code,name,industry')
        if sb.empty:
            print("  [基本面] stock_basic 返回空，跳过")
            return 0
        stock_map = {}
        for _, row in sb.iterrows():
            code = self._normalize_ts_code(str(row["ts_code"]))
            if not code:
                continue
            stock_map[code] = {
                "name": str(row.get("name", "")),
                "industry": str(row.get("industry", "") or ""),
            }
        print(f"  [基本面] 获取 {len(stock_map)} 只股票基础信息")

        # 2. 估值+交易指标 (daily_basic)
        print("  [基本面] 获取估值指标...")
        basic = {}
        try:
            db = pro.daily_basic(trade_date=tdate,
                                 fields='ts_code,pe_ttm,pb,total_mv,circ_mv,turnover_rate')
            if not db.empty:
                for _, row in db.iterrows():
                    code = self._normalize_ts_code(str(row["ts_code"]))
                    if not code:
                        continue
                    basic[code] = {
                        "pe_ttm": float(row.get("pe_ttm", 0) or 0),
                        "pb": float(row.get("pb", 0) or 0),
                        "total_mv": round(float(row.get("total_mv", 0) or 0) / 1e4, 2),  # 万元→亿元
                        "circ_mv": round(float(row.get("circ_mv", 0) or 0) / 1e4, 2),
                        "turnover_rate": float(row.get("turnover_rate", 0) or 0),
                    }
        except Exception as e:
            print(f"  [基本面] daily_basic 获取失败: {e}")

        # 3. 收盘价+涨跌幅 (daily)
        print("  [基本面] 获取行情数据...")
        daily_data = {}
        try:
            daily = pro.daily(trade_date=tdate, fields='ts_code,close,pct_chg')
            if not daily.empty:
                for _, row in daily.iterrows():
                    code = self._normalize_ts_code(str(row["ts_code"]))
                    if not code:
                        continue
                    daily_data[code] = {
                        "close_price": float(row.get("close", 0) or 0),
                        "pct_chg": float(row.get("pct_chg", 0) or 0),
                    }
        except Exception as e:
            print(f"  [基本面] daily 获取失败: {e}")

        # 4. 写入 DB
        now = datetime.now().isoformat()
        count = 0
        with sqlite3.connect(self.db_path) as conn:
            for code, info in stock_map.items():
                b = basic.get(code, {})
                d = daily_data.get(code, {})
                conn.execute("""
                    INSERT OR REPLACE INTO stock_fundamentals
                        (stock_code, stock_name, industry,
                         pe_ttm, pb, total_mv, circ_mv,
                         turnover_rate, close_price, pct_chg,
                         updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (code, info["name"], info["industry"],
                      b.get("pe_ttm", 0), b.get("pb", 0),
                      b.get("total_mv", 0), b.get("circ_mv", 0),
                      b.get("turnover_rate", 0),
                      d.get("close_price", 0), d.get("pct_chg", 0),
                      now))
                count += 1
            conn.commit()
        print(f"  [基本面] 写入 {count} 只股票基本面数据")

        # 5. 批量获取ROE等财务指标（市值TOP500）
        self._refresh_roe_batch(pro, top_n=500)

        return count

    # ─── 批量ROE获取 ────────────────────────────────────

    def _refresh_roe_batch(self, pro, top_n: int = 500) -> int:
        """批量获取市值TOP N股票的ROE/毛利率/营收同比
        
        使用 fina_indicator 逐只获取，每只间隔0.15s防限流。
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT stock_code FROM stock_fundamentals
                WHERE roe IS NULL OR roe = 0
                ORDER BY total_mv DESC
                LIMIT ?
            """, (top_n,)).fetchall()
        
        if not rows:
            print("  [基本面] ROE数据已是最新")
            return 0
        
        codes = [r[0] for r in rows]
        print(f"  [基本面] 批量获取 {len(codes)} 只股票的ROE/毛利率...")
        updated = 0
        for i, code in enumerate(codes):
            try:
                ts_code = self._to_ts_code(code)
                fina = pro.fina_indicator(ts_code=ts_code,
                                          fields='ts_code,roe_dt,grossprofit_margin,revenue_yoy')
                if not fina.empty:
                    row = fina.iloc[0]
                    roe = float(row.get("roe_dt", 0) or row.get("roe", 0) or 0)
                    margin = float(row.get("grossprofit_margin", 0) or 0)
                    rev_yoy = float(row.get("revenue_yoy", 0) or 0)
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute("""
                            UPDATE stock_fundamentals
                            SET roe=?, gross_margin=?, revenue_yoy=?, updated_at=?
                            WHERE stock_code=?
                        """, (roe, margin, rev_yoy, datetime.now().isoformat(), code))
                        updated += 1
            except Exception:
                pass
            time.sleep(0.15)
            if (i + 1) % 100 == 0:
                print(f"  [基本面] ROE进度: {i+1}/{len(codes)}, 已更新{updated}")
        
        print(f"  [基本面] 更新 {updated} 只股票的ROE/毛利率")
        return updated

    # ─── 公司业务描述 ─────────────────────────────────

    def refresh_company_business(self, stock_codes: list = None, batch_size: int = 50) -> int:
        """获取公司主营业务描述，更新 stock_fundamentals.company_business
        
        stock_codes: 指定股票列表。None=全市场。
        """
        import tushare as ts
        from config import Config
        pro = ts.pro_api(Config.TUSHARE_TOKEN)

        if stock_codes is None:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT stock_code FROM stock_fundamentals WHERE company_business=''"
                ).fetchall()
                stock_codes = [r[0] for r in rows]

        if not stock_codes:
            return 0

        print(f"  [基本面] 获取 {len(stock_codes)} 只股票的主营业务...")
        updated = 0
        for i in range(0, len(stock_codes), batch_size):
            batch = stock_codes[i:i + batch_size]
            for code in batch:
                try:
                    ts_code = self._to_ts_code(code)
                    # 获取公司基本信息
                    company = pro.stock_company(ts_code=ts_code,
                                                fields='ts_code,business_scope,chairman,manager')
                    if not company.empty:
                        row = company.iloc[0]
                        business = str(row.get("business_scope", "") or "")[:500]
                        if business:
                            with sqlite3.connect(self.db_path) as conn:
                                conn.execute("""
                                    UPDATE stock_fundamentals
                                    SET company_business=?, updated_at=?
                                    WHERE stock_code=?
                                """, (business, datetime.now().isoformat(), code))
                                updated += 1
                except Exception:
                    pass
                time.sleep(0.3)  # Tushare 限流
            if i + batch_size < len(stock_codes):
                time.sleep(1)
            if (i // batch_size + 1) % 5 == 0:
                print(f"  [基本面] 业务描述进度: {min(i + batch_size, len(stock_codes))}/{len(stock_codes)}")

        print(f"  [基本面] 更新 {updated} 只股票的主营业务描述")
        return updated

    # ─── ROE / 毛利率 ────────────────────────────────

    def refresh_financial_indicators(self, stock_codes: list = None) -> int:
        """获取 ROE、毛利率等财务指标"""
        import tushare as ts
        from config import Config
        pro = ts.pro_api(Config.TUSHARE_TOKEN)

        if stock_codes is None:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT stock_code FROM stock_fundamentals"
                ).fetchall()
                stock_codes = [r[0] for r in rows]

        if not stock_codes:
            return 0

        updated = 0
        for code in stock_codes:
            try:
                ts_code = self._to_ts_code(code)
                fina = pro.fina_indicator(ts_code=ts_code,
                                          fields='ts_code,roe,grossprofit_margin,revenue_yoy')
                if not fina.empty:
                    # 取最近一期
                    row = fina.iloc[0]
                    roe = float(row.get("roe", 0) or 0)
                    margin = float(row.get("grossprofit_margin", 0) or 0)
                    rev_yoy = float(row.get("revenue_yoy", 0) or 0)
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute("""
                            UPDATE stock_fundamentals
                            SET roe=?, gross_margin=?, revenue_yoy=?, updated_at=?
                            WHERE stock_code=?
                        """, (roe, margin, rev_yoy, datetime.now().isoformat(), code))
                        updated += 1
            except Exception:
                pass
            time.sleep(0.2)

        print(f"  [基本面] 更新 {updated} 只股票的财务指标")
        return updated

    # ─── 查询接口 ──────────────────────────────────────

    def get_stock_fundamentals(self, stock_code: str) -> dict:
        """获取单只股票的基本面"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM stock_fundamentals WHERE stock_code=?",
                (stock_code,)
            ).fetchone()
            return dict(row) if row else {}

    def get_concept_stocks_fundamentals(self, concept_id: str) -> list:
        """获取某概念所有成分股的基本面数据"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT sf.*, csm.concept_name
                FROM concept_stock_member csm
                JOIN stock_fundamentals sf ON csm.stock_code = sf.stock_code
                WHERE csm.concept_id=?
                ORDER BY sf.total_mv DESC
            """, (concept_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_industry_avg_pe(self, industry: str) -> float:
        """获取行业平均 PE"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("""
                    SELECT AVG(pe_ttm) FROM stock_fundamentals
                    WHERE industry=? AND pe_ttm > 0 AND pe_ttm < 1000
                """, (industry,)).fetchone()
                return float(row[0]) if row and row[0] else 30.0
        except Exception:
            return 30.0

    # ─── 内部方法 ──────────────────────────────────────

    @staticmethod
    def _normalize_ts_code(ts_code: str) -> str:
        """将 002230.SZ 转为 002230"""
        import re
        ts_code = ts_code.strip()
        m = re.match(r'^(\d{6})\.(SZ|SH|BJ)$', ts_code, re.IGNORECASE)
        if m:
            return m.group(1)
        if re.match(r'^\d{6}$', ts_code):
            return ts_code
        return ""

    @staticmethod
    def _to_ts_code(code: str) -> str:
        """将 002230 转为 002230.SZ"""
        code = code.strip()
        if "." in code:
            return code
        if code.startswith("6"):
            return f"{code}.SH"
        elif code.startswith(("0", "3")):
            return f"{code}.SZ"
        elif code.startswith(("4", "8")):
            return f"{code}.BJ"
        return f"{code}.SZ"
