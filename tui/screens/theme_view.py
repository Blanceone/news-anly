from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable

from tui.db import TuiDB


class ThemeViewScreen(Screen):
    CSS = """
    ThemeViewScreen {
        background: $surface;
    }
    .left-panel {
        width: 2fr;
        border: solid $border;
        margin: 1 0 1 1;
    }
    .right-panel {
        width: 3fr;
        border: solid $border;
        margin: 1 1 1 0;
    }
    .panel-title {
        text-style: bold;
        color: $accent;
        padding: 0 1;
    }
    DataTable {
        height: 1fr;
    }
    #theme-detail {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(classes="left-panel"):
                yield Static("🔥 主题列表", classes="panel-title")
                yield DataTable(id="theme-list")
            with Vertical(classes="right-panel"):
                yield Static("📊 关联股票", classes="panel-title")
                yield DataTable(id="theme-stocks")
        yield Footer()

    def on_mount(self):
        self.db = TuiDB()
        self._refresh()
        self.set_interval(30, self._refresh)

    def _refresh(self):
        table = self.query_one("#theme-list", DataTable)
        table.clear()
        table.add_columns("主题", "关联股票")
        self.themes = self.db.hot_themes()
        for t in self.themes:
            table.add_row(
                t.get("theme_name", ""),
                str(t.get("stock_count", 0)),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "theme-list":
            idx = event.cursor_row
            if idx is not None and 0 <= idx < len(self.themes):
                theme = self.themes[idx]
                self._show_theme_stocks(theme["theme_key"])

    def _show_theme_stocks(self, theme_key):
        table = self.query_one("#theme-stocks", DataTable)
        table.clear()
        table.add_columns("代码", "名称", "受益等级", "原因")
        stocks = self.db.theme_stocks(theme_key)
        level_map = {1: "一级", 2: "二级", 3: "三级"}
        for s in stocks:
            lv = level_map.get(s.get("benefit_level"), str(s.get("benefit_level", "")))
            table.add_row(
                s.get("stock_code", ""),
                s.get("stock_name", ""),
                lv,
                (s.get("benefit_reason") or "")[:40],
            )
        if not stocks:
            table.add_row("—", "暂无数据", "", "")
