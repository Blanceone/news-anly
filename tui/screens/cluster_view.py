"""Event Cluster View — Phase 14 (nav key 6)"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable

from tui.db import TuiDB


class ClusterViewScreen(Screen):
    CSS = """
    ClusterViewScreen { background: $surface; }
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
                yield Static("事件簇", classes="panel-title")
                yield DataTable(id="cluster-list", cursor_type="row")
            with Vertical(classes="right-panel"):
                yield Static("簇内事件", classes="panel-title")
                yield Static("请选择左侧簇查看详情", id="cluster-detail")
        yield Footer()

    def on_mount(self):
        self.db = TuiDB()
        self.query_one("#cluster-list", DataTable).add_columns("簇ID", "事件数", "热度")
        self._refresh()
        self.set_interval(30, self._refresh)

    def _refresh(self):
        table = self.query_one("#cluster-list", DataTable)
        table.clear()
        self.clusters = self.db.event_clusters()
        for c in self.clusters:
            table.add_row(
                str(c.get("cluster_id", "")),
                str(c.get("event_count", 0)),
                str(int(c.get("heat_score", 0))),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "cluster-list":
            idx = event.cursor_row
            if idx is not None and 0 <= idx < len(self.clusters):
                c = self.clusters[idx]
                events = self.db.cluster_events(c["cluster_id"])
                lines = [f"[bold]事件簇 {c['cluster_id']}[/] 共{c['event_count']}个事件"]
                for e in events:
                    lines.append(f"\n  {e.get('title', '')[:60]}")
                    lines.append(f"  类型: {e.get('event_type','')} 评分: {e.get('event_score',0)}")
                self.query_one("#cluster-detail", Static).update("\n".join(lines) if events else "(空)")
