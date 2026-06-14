"""Backtest View — V3 (nav key 10)"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable


class BacktestScreen(Screen):
    CSS = """
    BacktestScreen { background: $surface; }
    .left-panel { width: 1fr; border: solid $border; margin: 1 0 1 1; }
    .right-panel { width: 2fr; border: solid $border; margin: 1 1 1 0; }
    .panel-title { text-style: bold; color: $accent; padding: 0 1; }
    DataTable { height: 1fr; }
    #trade-detail { height: 1fr; overflow-y: auto; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(classes="left-panel"):
                yield Static("回测结果", classes="panel-title")
                yield DataTable(id="backtest-list", cursor_type="row")
            with Vertical(classes="right-panel"):
                yield Static("交易明细", classes="panel-title")
                yield DataTable(id="trade-table", cursor_type="row")
        yield Footer()

    def on_mount(self):
        from tui.db import TuiDB
        self.db = TuiDB()
        tbl = self.query_one("#backtest-list", DataTable)
        tbl.add_columns("策略", "持仓(天)", "交易数", "胜率", "平均收益", "夏普", "回撤")
        self._refresh()
        self.set_interval(30, self._refresh)

    def _refresh(self):
        tbl = self.query_one("#backtest-list", DataTable)
        tbl.clear()
        self.results = self.db.backtest_results()
        for r in self.results:
            tbl.add_row(
                str(r.get("strategy_type", "")),
                str(int(r.get("holding_days", 0))),
                str(int(r.get("total_trades", 0))),
                f"{r.get('win_rate', 0):.1f}%",
                f"{r.get('avg_return', 0):+.2f}%",
                str(r.get("sharpe_ratio", 0)),
                f"{r.get('max_drawdown', 0):.1f}%",
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "backtest-list":
            idx = event.cursor_row
            if idx is not None and 0 <= idx < len(self.results):
                r = self.results[idx]
                trades = self.db.backtest_trades_by_id(r["id"])
                tbl = self.query_one("#trade-table", DataTable)
                tbl.clear()
                tbl.add_columns("日期", "代码", "名称", "买入", "卖出", "收益")
                for t in trades:
                    tbl.add_row(
                        str(t.get("trade_date", ""))[5:10],
                        str(t.get("stock_code", "")),
                        str(t.get("stock_name", ""))[:8],
                        str(t.get("buy_price", 0)),
                        str(t.get("sell_price", 0)),
                        f"{t.get('return_rate', 0):+.2f}%",
                    )
