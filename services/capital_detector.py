"""资金异动检测器

PRD 第四章: 主力资金埋伏与异动识别
- 涨停统计 (信号3: 涨停>=5只)
- 龙虎榜 (信号7: 机构与游资共振)
- 北向资金 (信号2: 资金验证)
- 竞价抢筹 (信号4: 竞价>=3000万)
"""
import sqlite3
from datetime import datetime
from config import Config


class CapitalDetector:
    def __init__(self, concept_db=None):
        self.concept_db = concept_db or Config.CONCEPT_DB
        self._ts = None

    def _get_tushare(self):
        if self._ts is None:
            import tushare as ts
            self._ts = ts.pro_api(Config.TUSHARE_TOKEN)
        return self._ts

    # ──────────────────────────────────────────
    # 涨停统计 (信号3)
    # ──────────────────────────────────────────

    def fetch_limitup(self, trade_date: str = None) -> list:
        """获取当日涨停股列表"""
        if not Config.TUSHARE_TOKEN:
            return []
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            pro = self._get_tushare()
            df = pro.limit_list_d(trade_date=trade_date, limit_type='U')
            if df is None or df.empty:
                return []
            records = []
            for _, row in df.iterrows():
                records.append({
                    "stock_code": row.get("ts_code", ""),
                    "stock_name": row.get("name", ""),
                    "industry": row.get("industry", ""),
                    "limit_type": row.get("limit_type", ""),
                    "first_time": row.get("first_time", ""),
                    "last_time": row.get("last_time", ""),
                    "trade_date": trade_date,
                })
            return records
        except Exception as e:
            print(f"  [涨停] 获取失败: {e}")
            return []

    def aggregate_limitup_by_concept(self, trade_date: str = None) -> list:
        """按概念聚合涨停统计 → 写入 limitup_stats"""
        limitups = self.fetch_limitup(trade_date)
        if not limitups:
            return []

        # 查询 concept_stock 表，将涨停股映射到概念
        concept_map = {}  # concept_id -> {count, stocks, leader}
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            for stock in limitups:
                code = stock["stock_code"]
                rows = conn.execute("""
                    SELECT cs.concept_id, cc.concept_name
                    FROM concept_stock cs
                    JOIN concept_candidate cc ON cs.concept_id = cc.concept_id
                    WHERE cs.stock_code = ?
                """, (code,)).fetchall()
                for r in rows:
                    cid = r["concept_id"]
                    if cid not in concept_map:
                        concept_map[cid] = {
                            "concept_name": r["concept_name"],
                            "count": 0, "stocks": [], "leader": ""
                        }
                    concept_map[cid]["count"] += 1
                    concept_map[cid]["stocks"].append(stock["stock_name"])
                    if not concept_map[cid]["leader"]:
                        concept_map[cid]["leader"] = stock["stock_name"]

        # 写入 limitup_stats
        results = []
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        with sqlite3.connect(self.concept_db) as conn:
            for cid, info in concept_map.items():
                conn.execute("""
                    INSERT OR REPLACE INTO limitup_stats
                        (concept_id, concept_name, trade_date,
                         limitup_count, leader_stock)
                    VALUES (?, ?, ?, ?, ?)
                """, (cid, info["concept_name"], trade_date,
                      info["count"], info["leader"]))
                results.append({
                    "concept_id": cid,
                    "concept_name": info["concept_name"],
                    "limitup_count": info["count"],
                    "leader": info["leader"],
                })
            conn.commit()
        return results

    # ──────────────────────────────────────────
    # 龙虎榜 (信号7)
    # ──────────────────────────────────────────

    def fetch_dragon_tiger(self, trade_date: str = None) -> list:
        """获取龙虎榜数据"""
        if not Config.TUSHARE_TOKEN:
            return []
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            pro = self._get_tushare()
            df = pro.top_list(trade_date=trade_date)
            if df is None or df.empty:
                return []
            records = []
            for _, row in df.iterrows():
                records.append({
                    "trade_date": trade_date,
                    "stock_code": row.get("ts_code", ""),
                    "stock_name": row.get("name", ""),
                    "reason": row.get("reason", ""),
                    "buy_amount": float(row.get("buy", 0) or 0),
                    "sell_amount": float(row.get("sell", 0) or 0),
                    "net_amount": float(row.get("net_buy", 0) or 0),
                })
            self._save_dragon_tiger(records)
            return records
        except Exception as e:
            print(f"  [龙虎榜] 获取失败: {e}")
            return []

    def _save_dragon_tiger(self, records: list):
        if not records:
            return
        with sqlite3.connect(self.concept_db) as conn:
            for r in records:
                conn.execute("""
                    INSERT INTO dragon_tiger
                        (trade_date, stock_code, stock_name, reason,
                         buy_amount, sell_amount, net_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (r["trade_date"], r["stock_code"], r["stock_name"],
                      r["reason"], r["buy_amount"], r["sell_amount"],
                      r["net_amount"]))
            conn.commit()

    # ──────────────────────────────────────────
    # 北向资金 (信号2)
    # ──────────────────────────────────────────

    def fetch_northbound(self, trade_date: str = None) -> dict:
        """获取北向资金日度数据"""
        if not Config.TUSHARE_TOKEN:
            return {}
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            pro = self._get_tushare()
            df = pro.moneyflow_hsgt(start_date=trade_date, end_date=trade_date)
            if df is None or df.empty:
                return {}
            row = df.iloc[0]
            data = {
                "trade_date": trade_date,
                "north_money": float(row.get("north_money", 0) or 0),
                "south_money": float(row.get("south_money", 0) or 0),
                "ggt_ss": float(row.get("ggt_ss", 0) or 0),
                "ggt_sz": float(row.get("ggt_sz", 0) or 0),
                "hgt": float(row.get("hgt", 0) or 0),
                "sgt": float(row.get("sgt", 0) or 0),
            }
            self._save_northbound(data)
            return data
        except Exception as e:
            print(f"  [北向] 获取失败: {e}")
            return {}

    def _save_northbound(self, data: dict):
        if not data:
            return
        with sqlite3.connect(self.concept_db) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO northbound_flow
                    (trade_date, north_money, south_money,
                     ggt_ss, ggt_sz, hgt, sgt)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (data["trade_date"], data["north_money"], data["south_money"],
                  data["ggt_ss"], data["ggt_sz"], data["hgt"], data["sgt"]))
            conn.commit()

    # ──────────────────────────────────────────
    # 资金异动汇总
    # ──────────────────────────────────────────

    def detect_anomalies(self, concept_id: str = None) -> list:
        """检测资金异动 (涨停扩散/龙虎榜/北向)"""
        anomalies = []
        trade_date = datetime.now().strftime("%Y%m%d")

        # 1. 涨停扩散: 某概念涨停>=5只
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM limitup_stats
                WHERE trade_date=? AND limitup_count >= 5
            """, (trade_date,)).fetchall()
            for r in rows:
                anomalies.append({
                    "anomaly_type": "volume_breakout",
                    "concept_id": r["concept_id"],
                    "detail": f"涨停{r['limitup_count']}只, 龙头:{r['leader_stock']}",
                    "amount": r["limitup_count"],
                    "trade_date": trade_date,
                })

            # 2. 龙虎榜: 关联概念的龙虎榜
            if concept_id:
                dt_rows = conn.execute("""
                    SELECT dt.* FROM dragon_tiger dt
                    JOIN concept_stock cs ON dt.stock_code = cs.stock_code
                    WHERE dt.trade_date=? AND cs.concept_id=?
                """, (trade_date, concept_id)).fetchall()
            else:
                dt_rows = conn.execute("""
                    SELECT * FROM dragon_tiger WHERE trade_date=?
                """, (trade_date,)).fetchall()
            for r in dt_rows:
                anomalies.append({
                    "anomaly_type": "dragon_tiger",
                    "stock_code": r["stock_code"],
                    "stock_name": r["stock_name"],
                    "detail": f"{r.get('reason', '')} 净买:{r.get('net_amount', 0)/10000:.0f}万",
                    "amount": r.get("net_amount", 0),
                    "trade_date": trade_date,
                })

        # 保存异动
        self._save_anomalies(anomalies)
        return anomalies

    def _save_anomalies(self, anomalies: list):
        if not anomalies:
            return
        with sqlite3.connect(self.concept_db) as conn:
            for a in anomalies:
                conn.execute("""
                    INSERT INTO capital_anomaly
                        (anomaly_type, stock_code, stock_name, concept_id,
                         amount, detail, trade_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (a.get("anomaly_type", ""),
                      a.get("stock_code", ""),
                      a.get("stock_name", ""),
                      a.get("concept_id", ""),
                      a.get("amount", 0),
                      a.get("detail", ""),
                      a.get("trade_date", "")))
            conn.commit()

    def get_recent_anomalies(self, hours=24) -> list:
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM capital_anomaly
                WHERE created_at > datetime('now', ? || ' hours')
                ORDER BY created_at DESC LIMIT 100
            """, (str(hours),)).fetchall()
            return [dict(r) for r in rows]
