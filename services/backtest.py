"""回测系统 — Phase 7 (V3)

验证推荐策略是否赚钱。
流程：历史新闻 → 历史事件 → 系统推荐 → 模拟买入 → 统计收益
"""
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict


class BacktestEngine:
    def __init__(self, news_db=None, stocks_db=None):
        from config import Config
        self.news_db = news_db or Config.NEWS_DB
        self.stocks_db = stocks_db or Config.STOCKS_DB

    def _last_trade_date(self):
        d = datetime.today()
        while True:
            if d.weekday() < 5:
                return d.strftime("%Y%m%d")
            d -= timedelta(days=1)

    def run(self, start_date: str = None, end_date: str = None,
            holding_days: int = 3, strategy: str = "HOT",
            top_n: int = 5):
        """运行回测

        Args:
            start_date: YYYYMMDD, 默认7天前
            end_date: YYYYMMDD, 默认昨天
            holding_days: 持仓天数 (1/3/5/10/20)
            strategy: HOT / THEME / LATENT
            top_n: 每日买入前N只
        """
        end = datetime.strptime(end_date, "%Y%m%d") if end_date else \
              datetime.strptime(self._last_trade_date(), "%Y%m%d") - timedelta(days=1)
        start = datetime.strptime(start_date, "%Y%m%d") if start_date else end - timedelta(days=7)

        import tushare as ts
        from config import Config
        pro = ts.pro_api(Config.TUSHARE_TOKEN)

        # 获取历史评分记录
        with sqlite3.connect(self.stocks_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM recommendation_result
                WHERE strategy_type=? AND created_at BETWEEN ? AND ?
                ORDER BY created_at, rank_no
            """, (strategy, start.isoformat(), end.isoformat())).fetchall()

        # 按天分组推荐
        daily_recs = defaultdict(list)
        for r in rows:
            day = r["created_at"][:10]
            daily_recs[day].append(dict(r))

        trades = []
        for day, recs in daily_recs.items():
            candidates = sorted(recs, key=lambda x: x.get("score", 0), reverse=True)[:top_n]
            for rec in candidates:
                code = rec["stock_code"]
                # 买入价：当天收盘价
                buy = pro.daily(ts_code=code, trade_date=day.replace("-", ""))
                if buy.empty:
                    continue
                buy_price = float(buy.iloc[0].get("close", 0))
                if buy_price == 0:
                    continue

                # 卖出价：N天后收盘价
                sell_date = (datetime.strptime(day, "%Y-%m-%d") +
                             timedelta(days=holding_days)).strftime("%Y%m%d")
                sell = pro.daily(ts_code=code, trade_date=sell_date)
                if sell.empty:
                    # 向后找最近交易日
                    for i in range(1, 10):
                        sd = (datetime.strptime(sell_date, "%Y%m%d") +
                              timedelta(days=i)).strftime("%Y%m%d")
                        sell = pro.daily(ts_code=code, trade_date=sd)
                        if not sell.empty:
                            break
                if sell.empty:
                    continue
                sell_price = float(sell.iloc[0].get("close", 0))
                if sell_price == 0:
                    continue

                ret = (sell_price - buy_price) / buy_price * 100
                trades.append({
                    "trade_date": day,
                    "stock_code": code,
                    "stock_name": rec.get("stock_name", ""),
                    "buy_price": round(buy_price, 2),
                    "sell_price": round(sell_price, 2),
                    "holding_days": holding_days,
                    "return_rate": round(ret, 2),
                    "strategy_type": strategy,
                })

        # 统计
        if not trades:
            return {"trades": [], "win_rate": 0, "avg_return": 0,
                    "max_drawdown": 0, "sharpe": 0, "total_trades": 0}

        returns = [t["return_rate"] for t in trades]
        wins = [r for r in returns if r > 0]
        win_rate = len(wins) / len(returns) * 100 if returns else 0
        avg_ret = sum(returns) / len(returns) if returns else 0
        max_dd = 0
        peak = 0
        cumulative = 0
        for r in returns:
            cumulative += r
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        risk_free = 0.02  # 2% 无风险利率
        excess = [r - risk_free for r in returns]
        std = (sum((r - avg_ret) ** 2 for r in returns) / len(returns)) ** 0.5 if len(returns) > 1 else 1
        sharpe = (avg_ret - risk_free) / std * (252 ** 0.5) if std > 0 else 0

        result = {
            "trades": trades,
            "win_rate": round(win_rate, 1),
            "avg_return": round(avg_ret, 2),
            "max_drawdown": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "total_trades": len(trades),
        }
        self._save_result(result, strategy, start.strftime("%Y%m%d"),
                          end.strftime("%Y%m%d"), holding_days)
        return result

    def _save_result(self, result: dict, strategy: str,
                     start_date: str, end_date: str, holding_days: int):
        with sqlite3.connect(self.stocks_db) as conn:
            conn.execute("""
                INSERT INTO backtest_result
                    (strategy_type, start_date, end_date, holding_days,
                     win_rate, avg_return, max_drawdown, sharpe_ratio,
                     excess_return, total_trades)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (strategy, start_date, end_date, holding_days,
                  result["win_rate"], result["avg_return"],
                  result["max_drawdown"], result["sharpe_ratio"],
                  0, result["total_trades"]))
            bt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for t in result["trades"]:
                conn.execute("""
                    INSERT INTO backtest_trades
                        (backtest_id, trade_date, stock_code, stock_name,
                         buy_price, sell_price, holding_days, return_rate, strategy_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (bt_id, t["trade_date"], t["stock_code"],
                      t["stock_name"], t["buy_price"], t["sell_price"],
                      t["holding_days"], t["return_rate"], t["strategy_type"]))
            conn.commit()

    def get_latest_results(self, limit=10) -> list:
        with sqlite3.connect(self.stocks_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM backtest_result
                ORDER BY created_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
