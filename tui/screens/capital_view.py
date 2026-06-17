"""Capital — 资金异动 + 涨停统计 + 龙虎榜 + 北向"""
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
                yield Static("资金异动", id="anomaly_title")
                yield DataTable(id="anomaly_table")
            with Vertical():
                yield Static("涨停统计", id="limitup_title")
                yield DataTable(id="limitup_table")
        with Horizontal():
            with Vertical():
                yield Static("龙虎榜", id="dt_title")
                yield DataTable(id="dt_table")
            with Vertical():
                yield Static("北向资金 (日)", id="nb_title")
                yield DataTable(id="nb_table")

    def on_mount(self) -> None:
        self._setup_tables()
        self._load_data()

    def _setup_tables(self):
        at = self.query_one("#anomaly_table", DataTable)
        at.add_columns("类型", "概念/股票", "金额", "详情", "时间")
        at.cursor_type = "row"

        lt = self.query_one("#limitup_table", DataTable)
        lt.add_columns("概念", "日期", "涨停数", "连板", "龙头")
        lt.cursor_type = "row"

        dt = self.query_one("#dt_table", DataTable)
        dt.add_columns("日期", "股票", "原因", "净买(万)", "买/卖")
        dt.cursor_type = "row"

        nb = self.query_one("#nb_table", DataTable)
        nb.add_columns("日期", "北向(亿)", "南向(亿)", "沪股通", "深股通")
        nb.cursor_type = "row"

    def _load_data(self):
        db = TuiDB()

        # 资金异动
        at = self.query_one("#anomaly_table", DataTable)
        at.clear()
        for a in db.capital_anomalies(48):
            target = a.get("concept_id", "") or a.get("stock_name", "")
            at.add_row(
                a.get("anomaly_type", "")[:12],
                target[:12],
                f"{a.get('amount', 0):.0f}",
                a.get("detail", "")[:30],
                a.get("trade_date", ""),
            )

        # 涨停统计
        lt = self.query_one("#limitup_table", DataTable)
        lt.clear()
        for l in db.limitup_stats(limit=30):
            lt.add_row(
                l.get("concept_name", "")[:10],
                l.get("trade_date", ""),
                str(l.get("limitup_count", 0)),
                str(l.get("consecutive_max", 0)),
                l.get("leader_stock", "")[:8],
            )

        # 龙虎榜
        dt = self.query_one("#dt_table", DataTable)
        dt.clear()
        for d in db.dragon_tiger(limit=30):
            net = d.get("net_amount", 0)
            dt.add_row(
                d.get("trade_date", ""),
                f"{d.get('stock_name','')}({d.get('stock_code','')[:6]})",
                d.get("reason", "")[:15],
                f"{net/10000:.0f}" if net else "0",
                f"{d.get('buy_amount',0)/10000:.0f}/{d.get('sell_amount',0)/10000:.0f}",
            )

        # 北向
        nb = self.query_one("#nb_table", DataTable)
        nb.clear()
        for n in db.northbound_flow(30):
            north = n.get("north_money", 0)
            south = n.get("south_money", 0)
            nb.add_row(
                n.get("trade_date", ""),
                f"{north/100:.1f}" if north else "0",
                f"{south/100:.1f}" if south else "0",
                f"{n.get('hgt', 0)/100:.1f}",
                f"{n.get('sgt', 0)/100:.1f}",
            )

    def action_refresh(self):
        self._load_data()
