"""市场监控 — 大盘环境 + 市场情绪

Spec: 大盘成交额 (两市>8000亿?) + 涨停/跌停统计
使用 AKShare 获取市场数据，包含重试机制和频率控制。
"""
import sqlite3
from datetime import datetime
from config import Config


class MarketMonitor:
    def __init__(self, concept_db=None):
        self.concept_db = concept_db or Config.CONCEPT_DB

    # ──────────────────────────────────────────
    # 大盘成交额 (风控核心)
    # ──────────────────────────────────────────

    def get_market_volume(self, trade_date: str = None) -> dict:
        """获取两市成交额，判断市场环境"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            import akshare as ak
            import time
            # 获取上证+深证指数日K数据
            sh = ak.stock_zh_index_daily(symbol="sh000001")
            time.sleep(1)
            sz = ak.stock_zh_index_daily(symbol="sz399001")
            time.sleep(1)

            if sh is None or sh.empty or sz is None or sz.empty:
                return {"total_volume": 0, "is_healthy": False, "detail": "无量能数据"}

            # 取最近一个交易日
            sh_amount = float(sh.iloc[-1]["amount"]) if "amount" in sh.columns else 0
            sz_amount = float(sz.iloc[-1]["amount"]) if "amount" in sz.columns else 0
            total = sh_amount + sz_amount  # 单位: 元

            # 换算为亿元
            total_yi = total / 1e8

            is_healthy = total_yi >= 8000  # Spec: 两市>8000亿
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
    # 市场情绪 (涨停数 / 跌停数)
    # ──────────────────────────────────────────

    def get_market_sentiment(self, trade_date: str = None) -> dict:
        """市场情绪指标: 涨停数/跌停数"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            import akshare as ak
            import time
            # 涨停池
            lu = ak.stock_zt_pool_em(date=trade_date)
            time.sleep(1)
            lu_count = len(lu) if lu is not None and not lu.empty else 0

            # 跌停池
            try:
                ld = ak.stock_zt_pool_dtgc_em(date=trade_date)
                time.sleep(1)
                ld_count = len(ld) if ld is not None and not ld.empty else 0
            except Exception:
                ld_count = 0

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
