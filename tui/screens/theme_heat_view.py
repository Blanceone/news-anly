"""Theme Heat View — V3 (nav key 7)"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable

from tui.db import to_bjt


class ThemeHeatScreen(Screen):
    CSS = """
    ThemeHeatScreen { background: $surface; }
    .panel-title { text-style: bold; color: $accent; padding: 0 1; }
    DataTable { height: 1fr; margin: 0 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("主题热度 (衰减排序)", classes="panel-title")
        yield DataTable(id="heat-table", cursor_type="row")
        yield Footer()

    def on_mount(self):
        from tui.db import TuiDB
        self.db = TuiDB()
        table = self.query_one("#heat-table", DataTable)
        table.add_columns("主题", "原始热度", "衰减热度", "涨跌幅", "成交额(亿)", "涨停数")
        self._refresh()
        self.set_interval(30, self._refresh)

    def _refresh(self):
        table = self.query_one("#heat-table", DataTable)
        table.clear()
        rows = self.db.theme_heat_list()
        for r in rows:
            table.add_row(
                str(r.get("theme_name", ""))[:20],
                str(int(r.get("raw_heat", r.get("heat", 0)))),
                str(int(r.get("decay_heat", 0))),
                f"{r.get('board_change', 0):+.2f}%",
                str(r.get("board_volume", 0)),
                str(int(r.get("limitup_count", 0))),
            )
