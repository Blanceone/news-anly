"""Event Lifecycle View — V3 (nav key 8)"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable

from tui.db import to_bjt

_LIFECYCLE_COLORS = {
    "BIRTH": "green",
    "GROWING": "bright_cyan",
    "PEAK": "yellow",
    "DECLINING": "orange3",
    "DEAD": "red",
}


class LifecycleScreen(Screen):
    CSS = """
    LifecycleScreen { background: $surface; }
    .left-panel { width: 1fr; border: solid $border; margin: 1 0 1 1; }
    .right-panel { width: 2fr; border: solid $border; margin: 1 1 1 0; }
    .panel-title { text-style: bold; color: $accent; padding: 0 1; }
    DataTable { height: 1fr; }
    #cluster-detail { height: 1fr; overflow-y: auto; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(classes="left-panel"):
                yield Static("生命周期阶段", classes="panel-title")
                yield DataTable(id="lifecycle-stats", cursor_type="row")
            with Vertical(classes="right-panel"):
                yield Static("阶段内簇", classes="panel-title")
                yield DataTable(id="phase-clusters", cursor_type="row")
        yield Footer()

    def on_mount(self):
        from tui.db import TuiDB
        self.db = TuiDB()
        tbl = self.query_one("#lifecycle-stats", DataTable)
        tbl.add_columns("阶段", "系数", "簇数", "平均事件数")
        self._refresh()
        self.set_interval(30, self._refresh)

    def _refresh(self):
        tbl = self.query_one("#lifecycle-stats", DataTable)
        tbl.clear()
        self.stats = self.db.lifecycle_stats()
        for s in self.stats:
            color = _LIFECYCLE_COLORS.get(s["status"], "white")
            tbl.add_row(
                f"[{color}]{s['status']}[/]",
                str({"BIRTH":0.8,"GROWING":1.0,"PEAK":0.7,"DECLINING":0.3,"DEAD":0.0}.get(s["status"], "-")),
                str(s["cnt"]),
                str(s["avg_events"]),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "lifecycle-stats":
            idx = event.cursor_row
            if idx is not None and 0 <= idx < len(self.stats):
                status = self.stats[idx]["status"]
                clusters = self.db.lifecycle_clusters(status=status)
                tbl = self.query_one("#phase-clusters", DataTable)
                tbl.clear()
                tbl.add_columns("簇ID", "事件数", "关键词", "最后活跃")
                for c in clusters:
                    tbl.add_row(
                        str(c.get("cluster_id", "")),
                        str(c.get("event_count", 0)),
                        (c.get("keywords", "") or "")[:25],
                        to_bjt(c.get("last_seen", "")),
                    )
