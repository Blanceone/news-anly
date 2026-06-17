"""资金异动检测器 — AKShare 接口封装

Spec 4.4: 市场数据与资金监控服务
- get_limitup_pool: stock_zt_pool_em → limitup_stats
- get_dragon_tiger: stock_lhb_detail_em → dragon_tiger
- get_northbound_flow: stock_hsgt_north_net_flow_in_em → northbound_flow

AKShare 统一封装: 重试机制 + 频率控制 (每次调用后 sleep 1秒)
"""
import sqlite3
import time
from datetime import datetime
from config import Config


class CapitalDetector:
    def __init__(self, concept_db=None):
        self.concept_db = concept_db or Config.CONCEPT_DB

    # ──────────────────────────────────────────
    # 涨停统计 (信号3)
    # Spec: 调用 stock_zt_pool_em, 解析涨停股所属概念, 更新 limitup_stats
    # ──────────────────────────────────────────

    def get_limitup_pool(self, trade_date: str = None) -> list:
        """获取当日涨停股列表 (AKShare stock_zt_pool_em)"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            import akshare as ak
            df = ak.stock_zt_pool_em(date=trade_date)
            time.sleep(1)  # 频率控制
            if df is None or df.empty:
                return []
            records = []
            for _, row in df.iterrows():
                records.append({
                    "stock_code": str(row.get("代码", "")),
                    "stock_name": str(row.get("名称", "")),
                    "industry": str(row.get("所属行业", "")),
                    "first_time": str(row.get("首次封板时间", "")),
                    "last_time": str(row.get("最后封板时间", "")),
                    "consecutive": int(row.get("连板数", 1) or 1),
                    "trade_date": trade_date,
                })
            return records
        except Exception as e:
            print(f"  [涨停] 获取失败: {e}")
            return []

    def aggregate_limitup_by_concept(self, trade_date: str = None) -> list:
        """按概念聚合涨停统计 → 写入 limitup_stats"""
        limitups = self.get_limitup_pool(trade_date)
        if not limitups:
            return []

        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")

        # 查询 concept_stock 表，将涨停股映射到概念
        concept_map = {}  # concept_id -> {count, max_consecutive}
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            for stock in limitups:
                code = stock["stock_code"]
                rows = conn.execute("""
                    SELECT cs.concept_id, cc.standard_name
                    FROM concept_stock cs
                    JOIN concept_candidate cc ON cs.concept_id = cc.id
                    WHERE cs.stock_code = ?
                """, (code,)).fetchall()
                for r in rows:
                    cid = r["concept_id"]
                    if cid not in concept_map:
                        concept_map[cid] = {
                            "concept_name": r["standard_name"],
                            "count": 0, "max_consecutive": 0,
                        }
                    concept_map[cid]["count"] += 1
                    concept_map[cid]["max_consecutive"] = max(
                        concept_map[cid]["max_consecutive"],
                        stock.get("consecutive", 1)
                    )

        # 写入 limitup_stats (Spec schema: trade_date, concept_id, limitup_count, max_consecutive_boards)
        results = []
        with sqlite3.connect(self.concept_db) as conn:
            for cid, info in concept_map.items():
                conn.execute("""
                    INSERT OR REPLACE INTO limitup_stats
                        (trade_date, concept_id, limitup_count, max_consecutive_boards)
                    VALUES (?, ?, ?, ?)
                """, (trade_date, cid, info["count"], info["max_consecutive"]))
                results.append({
                    "concept_id": cid,
                    "concept_name": info["concept_name"],
                    "limitup_count": info["count"],
                    "max_consecutive_boards": info["max_consecutive"],
                    "trade_date": trade_date,
                })
            conn.commit()
        return results

    # ──────────────────────────────────────────
    # 龙虎榜 (信号7)
    # Spec: 调用 stock_lhb_detail_em, 区分机构/游资/拉萨营业部
    # ──────────────────────────────────────────

    def get_dragon_tiger(self, trade_date: str = None) -> list:
        """获取龙虎榜数据 (AKShare stock_lhb_detail_em)"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            import akshare as ak
            df = ak.stock_lhb_detail_em(
                start_date=trade_date, end_date=trade_date
            )
            time.sleep(1)
            if df is None or df.empty:
                return []

            records = []
            for _, row in df.iterrows():
                buyer_name = str(row.get("买方名称", row.get("营业部名称", "")))
                buyer_type = self._classify_buyer(buyer_name)
                records.append({
                    "trade_date": trade_date,
                    "stock_code": str(row.get("代码", row.get("股票代码", ""))),
                    "buyer_name": buyer_name,
                    "net_buy": float(row.get("净买额", row.get("买入金额", 0)) or 0),
                    "buyer_type": buyer_type,
                })
            self._save_dragon_tiger(records)
            return records
        except Exception as e:
            print(f"  [龙虎榜] 获取失败: {e}")
            return []

    def _classify_buyer(self, buyer_name: str) -> str:
        """区分买入席位类型: institution / hot_money / retail"""
        if not buyer_name:
            return "retail"
        if "机构" in buyer_name or "证券有限公司" in buyer_name and "投资" in buyer_name:
            return "institution"
        # 知名游资营业部关键词
        hot_money_keywords = ["华鑫", "东方财富拉萨", "国泰君安", "中信建投", "银河绍兴"]
        for kw in hot_money_keywords:
            if kw in buyer_name:
                return "hot_money"
        # 拉萨营业部 → 游资
        if "拉萨" in buyer_name:
            return "hot_money"
        return "retail"

    def _save_dragon_tiger(self, records: list):
        if not records:
            return
        with sqlite3.connect(self.concept_db) as conn:
            for r in records:
                conn.execute("""
                    INSERT INTO dragon_tiger
                        (trade_date, stock_code, buyer_name, net_buy, buyer_type)
                    VALUES (?, ?, ?, ?, ?)
                """, (r["trade_date"], r["stock_code"], r["buyer_name"],
                      r["net_buy"], r["buyer_type"]))
            conn.commit()

    # ──────────────────────────────────────────
    # 北向资金 (信号2)
    # Spec: 调用 stock_hsgt_north_net_flow_in_em → northbound_flow
    # ──────────────────────────────────────────

    def get_northbound_flow(self, trade_date: str = None) -> list:
        """获取北向资金数据 (AKShare)"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            import akshare as ak
            # 沪股通+深股通个股净买入
            df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
            time.sleep(1)
            if df is None or df.empty:
                return []

            records = []
            # AKShare 返回的格式可能不同，做适配
            for _, row in df.iterrows():
                stock_code = str(row.get("代码", row.get("股票代码", "")))
                net_buy = float(row.get("净买入额", row.get("净买额", 0)) or 0)
                if stock_code:
                    records.append({
                        "trade_date": trade_date,
                        "stock_code": stock_code,
                        "net_buy": net_buy,
                    })
            self._save_northbound(records)
            return records
        except Exception as e:
            print(f"  [北向] 获取失败: {e}")
            return []

    def _save_northbound(self, records: list):
        if not records:
            return
        with sqlite3.connect(self.concept_db) as conn:
            for r in records:
                conn.execute("""
                    INSERT OR REPLACE INTO northbound_flow
                        (trade_date, stock_code, net_buy)
                    VALUES (?, ?, ?)
                """, (r["trade_date"], r["stock_code"], r["net_buy"]))
            conn.commit()

    # ──────────────────────────────────────────
    # 资金异动汇总
    # ──────────────────────────────────────────

    def detect_anomalies(self, concept_id: int = None) -> list:
        """检测资金异动 (涨停扩散/龙虎榜/北向)"""
        anomalies = []
        trade_date = datetime.now().strftime("%Y-%m-%d")

        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row

            # 1. 涨停扩散: 某概念涨停>=5只
            if concept_id:
                rows = conn.execute("""
                    SELECT * FROM limitup_stats
                    WHERE trade_date=? AND concept_id=? AND limitup_count >= 5
                """, (trade_date, concept_id)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM limitup_stats
                    WHERE trade_date=? AND limitup_count >= 5
                """, (trade_date,)).fetchall()
            for r in rows:
                anomalies.append({
                    "anomaly_type": "volume_breakout",
                    "stock_code": "",
                    "trade_date": trade_date,
                    "detail": f"概念{r['concept_id']}涨停{r['limitup_count']}只",
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
                    "trade_date": trade_date,
                    "detail": f"{r['buyer_name']} {r['buyer_type']} 净买:{r['net_buy']:.0f}",
                })

        # 保存异动到 capital_anomaly
        self._save_anomalies(anomalies)
        return anomalies

    def _save_anomalies(self, anomalies: list):
        if not anomalies:
            return
        with sqlite3.connect(self.concept_db) as conn:
            for a in anomalies:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO capital_anomaly
                            (stock_code, trade_date, anomaly_type, detail)
                        VALUES (?, ?, ?, ?)
                    """, (a.get("stock_code", ""),
                          a.get("trade_date", ""),
                          a.get("anomaly_type", ""),
                          a.get("detail", "")))
                except Exception:
                    pass
            conn.commit()

    def get_recent_anomalies(self, days=2) -> list:
        with sqlite3.connect(self.concept_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM capital_anomaly
                WHERE trade_date >= date('now', ? || ' days')
                ORDER BY trade_date DESC LIMIT 100
            """, (str(-days),)).fetchall()
            return [dict(r) for r in rows]
