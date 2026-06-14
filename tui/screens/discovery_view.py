"""Theme Discovery View — Phase 14 (nav key 5)"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable

from tui.db import TuiDB


class DiscoveryViewScreen(Screen):
    CSS = """
    DiscoveryViewScreen { background: $surface; }
    .left-panel { width: 1fr; border: solid $border; margin: 1 0 1 1; }
    .right-panel { width: 2fr; border: solid $border; margin: 1 1 1 0; }
    .panel-title { text-style: bold; color: $accent; padding: 0 1; }
    DataTable { height: 1fr; }
    #discovery-detail { height: 1fr; overflow-y: auto; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(classes="left-panel"):
                yield Static("新发现主题", classes="panel-title")
                yield DataTable(id="discovery-list", cursor_type="row")
            with Vertical(classes="right-panel"):
                yield Static("详情", classes="panel-title")
                yield Static("请选择左侧主题查看详情", id="discovery-detail")
        yield Footer()

    def on_mount(self):
        self.db = TuiDB()
        self.query_one("#discovery-list", DataTable).add_columns("主题名称", "状态", "出现次数", "热度")
        self._refresh()
        self.set_interval(30, self._refresh)

    def _refresh(self):
        table = self.query_one("#discovery-list", DataTable)
        table.clear()
        self.candidates = self.db.theme_candidates()
        for c in self.candidates:
            table.add_row(
                c.get("theme_name", ""),
                c.get("status", ""),
                str(c.get("mention_count", 0)),
                str(int(c.get("heat_score", 0))),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "discovery-list":
            idx = event.cursor_row
            if idx is not None and 0 <= idx < len(self.candidates):
                c = self.candidates[idx]
                widget = self.query_one("#discovery-detail", Static)
                widget.update(
                    f"[bold]主题名称:[/] {c.get('theme_name')}\n"
                    f"[bold]状态:[/] {c.get('status')}\n"
                    f"[bold]出现次数:[/] {c.get('mention_count')}\n"
                    f"[bold]热度:[/] {c.get('heat_score')}\n"
                    f"[bold]首次出现:[/] {c.get('first_seen') or ''}\n"
                    f"[bold]最近出现:[/] {c.get('last_seen') or ''}"
                )
