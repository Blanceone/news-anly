"""Capital — 资金异动 + 涨停统计 + 龙虎榜 + 北向

Spec 6.4:
  涨停梯队（按概念聚合）、今日龙虎榜知名游资动向、北向资金净买入TOP10
"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Header, Static

from tui.db import TuiDB


class CapitalScreen(Screen):
    BINDINGS = [("r", "refresh", "刷新")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical():
                yield Static("涨停梯队 (按概念聚合)", id="limitup_title")
                yield DataTable(id="limitup_table")
            with Vertical():
                yield Static("资金异动", id="anomaly_title")
                yield DataTable(id="anomaly_table")
        with Horizontal():
            with Vertical():
                yield Static("龙虎榜 (游资/机构)", id="dt_title")
                yield DataTable(id="dt_table")
            with Vertical():
                yield Static("北向资金净买入TOP10", id="nb_title")
                yield DataTable(id="nb_table")

    def on_mount(self) -> None:
        self._setup_tables()
        self._load_data()

    def _setup_tables(self):
        lt = self.query_one("#limitup_table", DataTable)
        lt.add_columns("概念", "日期", "涨停数", "最高连板")
        lt.cursor_type = "row"

        at = self.query_one("#anomaly_table", DataTable)
        at.add_columns("股票", "类型", "详情", "日期")
        at.cursor_type = "row"

        dt = self.query_one("#dt_table", DataTable)
        dt.add_columns("日期", "股票", "买方", "类型", "净买入")
        dt.cursor_type = "row"

        nb = self.query_one("#nb_table", DataTable)
        nb.add_columns("股票", "净买入(万)")
        nb.cursor_type = "row"

    def _load_data(self):
        db = TuiDB()

        # 涨停统计
        lt = self.query_one("#limitup_table", DataTable)
        lt.clear()
        for l in db.limitup_stats(limit=30):
            lt.add_row(
                l.get("concept_name", "")[:12],
                l.get("trade_date", ""),
                str(l.get("limitup_count", 0)),
                str(l.get("max_consecutive_boards", 0)),
            )

        # 资金异动
        at = self.query_one("#anomaly_table", DataTable)
        at.clear()
        for a in db.capital_anomalies(2):
            at.add_row(
                a.get("stock_code", "")[:10],
                a.get("anomaly_type", "")[:12],
                a.get("detail", "")[:30],
                a.get("trade_date", ""),
            )

        # 龙虎榜
        dt = self.query_one("#dt_table", DataTable)
        dt.clear()
        for d in db.dragon_tiger(limit=30):
            net = d.get("net_buy", 0)
            dt.add_row(
                d.get("trade_date", ""),
                d.get("stock_code", "")[:10],
                d.get("buyer_name", "")[:15],
                d.get("buyer_type", ""),
                f"{net:.0f}",
            )

        # 北向TOP10
        nb = self.query_one("#nb_table", DataTable)
        nb.clear()
        for n in db.northbound_top10():
            nb.add_row(
                n.get("stock_code", "")[:10],
                f"{n.get('net_buy', 0):.0f}",
            )

    def action_refresh(self):
        self._load_data()
