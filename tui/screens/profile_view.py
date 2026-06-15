"""Stock Profile View — V3 (nav key 9)"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable


class ProfileScreen(Screen):
    CSS = """
    ProfileScreen { background: $surface; }
    .panel-title { text-style: bold; color: $accent; padding: 0 1; }
    DataTable { height: 1fr; margin: 0 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("股票画像 & 龙头评分", classes="panel-title")
        yield DataTable(id="profile-table", cursor_type="row")
        yield Static("", id="profile-detail")
        yield Footer()

    def on_mount(self):
        from tui.db import TuiDB
        self.db = TuiDB()
        table = self.query_one("#profile-table", DataTable)
        table.add_columns("代码", "名称", "龙头评分", "换手率", "市值(亿)", "题材数", "涨停数")
        self._refresh()
        self.set_interval(30, self._refresh)

    def _refresh(self):
        table = self.query_one("#profile-table", DataTable)
        table.clear()
        self.rows = self.db.stock_profile_list()
        for r in self.rows:
            table.add_row(
                str(r.get("stock_code", "")),
                str(r.get("stock_name", ""))[:8],
                str(round(r.get("leader_score", 0), 1)),
                f"{r.get('turnover_rate', 0):.2f}%",
                str(r.get("market_cap", 0)),
                str(int(r.get("theme_count", 0))),
                str(int(r.get("limitup_history", 0))),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "profile-table":
            idx = event.cursor_row
            if idx is not None and 0 <= idx < len(self.rows):
                r = self.rows[idx]
                lines = [
                    f"[bold]{r.get('stock_name','')} ({r.get('stock_code','')})[/]",
                    f"龙头评分: {r.get('leader_score', 0)}",
                    f"行业: {r.get('industry', '')}  波动率: {r.get('volatility', 0):.2f}%",
                    f"题材数: {r.get('theme_count', 0)}  涨停历史: {r.get('limitup_history', 0)}",
                    f"换手率: {r.get('turnover_rate', 0):.2f}%  市值: {r.get('market_cap', 0)}亿",
                ]
                self.query_one("#profile-detail", Static).update("\n".join(lines))
