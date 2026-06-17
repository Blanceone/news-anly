"""市场监控 — 大盘环境 + 板块涨跌 + 市场情绪

PRD 第六章: 风控红线
- 大盘成交额 (两市>8000亿?)
- 板块涨跌排名
- 市场情绪指标
"""
import sqlite3
from datetime import datetime
from config import Config


class MarketMonitor:
    def __init__(self, concept_db=None):
        self.concept_db = concept_db or Config.CONCEPT_DB
        self._ts = None

    def _get_tushare(self):
        if self._ts is None:
            import tushare as ts
            self._ts = ts.pro_api(Config.TUSHARE_TOKEN)
        return self._ts

    # ──────────────────────────────────────────
    # 大盘成交额 (风控核心)
    # ──────────────────────────────────────────

    def get_market_volume(self, trade_date: str = None) -> dict:
        """获取两市成交额，判断市场环境"""
        if not Config.TUSHARE_TOKEN:
            return {"total_volume": 0, "is_healthy": False, "detail": "无Tushare"}
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            pro = self._get_tushare()
            # 获取上证+深证指数
            sh = pro.index_daily(ts_code="000001.SH", start_date=trade_date, end_date=trade_date)
            sz = pro.index_daily(ts_code="399001.SZ", start_date=trade_date, end_date=trade_date)

            sh_amount = float(sh.iloc[0]["amount"]) if sh is not None and not sh.empty else 0
            sz_amount = float(sz.iloc[0]["amount"]) if sz is not None and not sz.empty else 0
            total = sh_amount + sz_amount  # 单位: 千元

            # 换算为亿元
            total_yi = total / 100000

            is_healthy = total_yi >= 8000  # PRD: 两市>8000亿
            return {
                "trade_date": trade_date,
                "sh_amount": sh_amount,
                "sz_amount": sz_amount,
                "total_volume": total_yi,
                "is_healthy": is_healthy,
                "detail": f"两市成交 {total_yi:.0f}亿 {'(健康)' if is_healthy else '(缩量,风险)'}",
            }
        except Exception as e:
            return {"total_volume": 0, "is_healthy": False, "detail": f"获取失败: {e}"}

    # ──────────────────────────────────────────
    # 板块涨跌排名
    # ──────────────────────────────────────────

    def get_sector_ranking(self, limit=20) -> list:
        """获取板块涨幅排名 (用 Tushare 申万行业)"""
        if not Config.TUSHARE_TOKEN:
            return []
        try:
            pro = self._get_tushare()
            trade_date = datetime.now().strftime("%Y%m%d")
            # 获取申万一级行业指数
            df = pro.index_classify(level='L1', src='SW2021')
            if df is None or df.empty:
                return []
            rankings = []
            for _, row in df.iterrows():
                idx_code = row.get("index_code", "")
                idx_name = row.get("industry_name", "")
                try:
                    daily = pro.index_daily(ts_code=idx_code,
                                            start_date=trade_date, end_date=trade_date)
                    if daily is not None and not daily.empty:
                        pct = float(daily.iloc[0].get("pct_chg", 0))
                        rankings.append({
                            "name": idx_name,
                            "change": pct,
                            "code": idx_code,
                        })
                except Exception:
                    pass
            rankings.sort(key=lambda x: x["change"], reverse=True)
            return rankings[:limit]
        except Exception as e:
            print(f"  [板块] 获取失败: {e}")
            return []

    # ──────────────────────────────────────────
    # 市场情绪 (涨停数 / 跌停数 / 上涨家数)
    # ──────────────────────────────────────────

    def get_market_sentiment(self, trade_date: str = None) -> dict:
        """市场情绪指标: 涨停数/跌停数/涨跌比"""
        if not Config.TUSHARE_TOKEN:
            return {}
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            pro = self._get_tushare()
            # 涨停
            lu = pro.limit_list_d(trade_date=trade_date, limit_type='U')
            lu_count = len(lu) if lu is not None and not lu.empty else 0
            # 跌停
            ld = pro.limit_list_d(trade_date=trade_date, limit_type='D')
            ld_count = len(ld) if ld is not None and not ld.empty else 0

            return {
                "trade_date": trade_date,
                "limitup_count": lu_count,
                "limitdown_count": ld_count,
                "ratio": f"{lu_count}:{ld_count}",
                "is_bullish": lu_count > ld_count * 2,
            }
        except Exception as e:
            return {"error": str(e)}

    # ──────────────────────────────────────────
    # 综合市场评估
    # ──────────────────────────────────────────

    def assess_market(self, trade_date: str = None) -> dict:
        """综合市场评估 → 用于风控判断"""
        volume = self.get_market_volume(trade_date)
        sentiment = self.get_market_sentiment(trade_date)
        return {
            "volume": volume,
            "sentiment": sentiment,
            "is_safe_to_trade": volume.get("is_healthy", False),
            "summary": self._build_summary(volume, sentiment),
        }

    def _build_summary(self, volume: dict, sentiment: dict) -> str:
        parts = []
        vol = volume.get("total_volume", 0)
        if vol > 0:
            parts.append(f"两市{vol:.0f}亿")
            if vol >= 10000:
                parts.append("量能充沛")
            elif vol >= 8000:
                parts.append("量能尚可")
            else:
                parts.append("缩量风险")
        lu = sentiment.get("limitup_count", 0)
        ld = sentiment.get("limitdown_count", 0)
        if lu or ld:
            parts.append(f"涨停{lu}/跌停{ld}")
        return " | ".join(parts) if parts else "无数据"

    def is_trading_hours(self) -> bool:
        """判断当前是否在交易时间 (工作日 9:25-15:00)"""
        now = datetime.now()
        if now.weekday() >= 5:  # 周末
            return False
        t = now.hour * 100 + now.minute
        return 925 <= t <= 1500
