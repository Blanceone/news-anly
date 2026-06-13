from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable

from tui.db import TuiDB


class EventViewScreen(Screen):
    CSS = """
    EventViewScreen {
        background: $surface;
    }
    .left-panel {
        width: 3fr;
        border: solid $border;
        margin: 1 0 1 1;
    }
    .right-panel {
        width: 2fr;
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
    #event-detail {
        height: 1fr;
        overflow-y: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(classes="left-panel"):
                yield Static("事件列表", classes="panel-title")
                yield DataTable(id="event-list", cursor_type="row")
            with Vertical(classes="right-panel"):
                yield Static("影响股票", classes="panel-title")
                yield Static("请选择左侧事件查看详情", id="event-detail")
        yield Footer()

    def on_mount(self):
        self.db = TuiDB()
        self.query_one("#event-list", DataTable).add_columns("时间", "类型", "行业", "强度", "市场验证", "摘要")
        self._refresh()
        self.set_interval(30, self._refresh)

    def _refresh(self):
        table = self.query_one("#event-list", DataTable)
        table.clear()
        self.events = self.db.event_list(hours=48, limit=60)
        for e in self.events:
            ts = (e.get("created_at") or "")[11:19] if e.get("created_at") else ""
            event_type = e.get("event_type", "") or ""
            industry = e.get("industry", "") or ""
            score = e.get("event_score", 0) or 0
            mscore = e.get("market_score", 0) or 0
            summary = (e.get("ai_summary") or "")[:40]
            table.add_row(ts, event_type, industry, str(score), str(mscore), summary)

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "event-list":
            idx = event.cursor_row
            if idx is not None and 0 <= idx < len(self.events):
                ev = self.events[idx]
                self._show_event_detail(ev["event_id"])

    def _show_event_detail(self, event_id):
        widget = self.query_one("#event-detail", Static)
        ev = None
        for e in self.events:
            if e["event_id"] == event_id:
                ev = e
                break
        if not ev:
            widget.update("事件未找到")
            return

        lines = [
            f"[bold]事件ID: {event_id}[/]",
            f"类型: {ev.get('event_type', '')}",
            f"行业: {ev.get('industry', '')} / {ev.get('sub_industry', '')}",
            f"情绪: {ev.get('sentiment', '')}  重要性: {ev.get('importance', '')}",
            f"事件评分: {ev.get('event_score', 0)}  市场验证: {ev.get('market_score', 0)}",
            f"新颖度: {ev.get('novelty_score', 0)}",
            "",
            f"[bold]摘要:[/] {ev.get('ai_summary', '')}",
            "",
            "[bold]影响股票:[/]",
        ]
        stocks = self.db.event_stocks(event_id)
        level_map = {1: "一级", 2: "二级", 3: "三级"}
        for s in stocks:
            lv = level_map.get(s.get("benefit_level"), str(s.get("benefit_level", "")))
            lines.append(f"  {s.get('stock_code', '')} {s.get('stock_name', '')} [{lv}] {s.get('match_reason', '')}")
        if not stocks:
            lines.append("  (无关联股票)")

        widget.update("\n".join(lines))
