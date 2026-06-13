from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable

from tui.db import TuiDB


class StockViewScreen(Screen):
    CSS = """
    StockViewScreen {
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
    #stock-detail {
        height: 1fr;
        overflow-y: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(classes="left-panel"):
                yield Static("股票列表", classes="panel-title")
                yield DataTable(id="stock-list", cursor_type="row")
            with Vertical(classes="right-panel"):
                yield Static("详情", classes="panel-title")
                yield Static("请选择左侧股票查看详情", id="stock-detail")
        yield Footer()

    def on_mount(self):
        self.db = TuiDB()
        self.query_one("#stock-list", DataTable).add_columns("排名", "代码", "名称", "总分", "事件", "关联主题")
        self._refresh()
        self.set_interval(30, self._refresh)

    def _refresh(self):
        table = self.query_one("#stock-list", DataTable)
        table.clear()
        self.stocks = self.db.all_stocks_summary()
        for i, s in enumerate(self.stocks, 1):
            table.add_row(
                str(i),
                s.get("stock_code", ""),
                s.get("stock_name", ""),
                str(int(s.get("total_score", 0))),
                str(s.get("event_count", 0)),
                str(s.get("theme_count", 0)),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "stock-list":
            idx = event.cursor_row
            if idx is not None and 0 <= idx < len(self.stocks):
                stock = self.stocks[idx]
                self._show_detail(stock["stock_code"])

    def _show_detail(self, stock_code):
        detail = self.db.stock_detail(stock_code)
        widget = self.query_one("#stock-detail", Static)
        lines = []

        score = detail.get("score")
        if score:
            lines.extend([
                f"[bold]{score.get('stock_name', '')} ({score.get('stock_code', '')})[/]",
                "",
                f"总分: {int(score.get('total_score', 0))} = "
                f"事件{int(score.get('event_score', 0))}*30% + "
                f"受益{int(score.get('benefit_score', 0))}*40% + "
                f"市场{int(score.get('market_score', 0))}*30%",
                f"触发事件数: {score.get('event_count', 0)}",
            ])
        else:
            lines.append("无评分数据")

        themes = detail.get("themes", [])
        if themes:
            level_map = {1: "一级", 2: "二级", 3: "三级"}
            lines.extend(["", "[bold]受益逻辑(主题映射):[/]"])
            for t in themes:
                lv = level_map.get(t.get("benefit_level"), "")
                lines.append(f"  {t.get('theme_name', '')} [{lv}] {t.get('benefit_reason', '')}")

        mkt = detail.get("market_confirmations", [])
        if mkt:
            lines.extend(["", "[bold]市场验证(板块):[/]"])
            for m in mkt:
                chg = m.get("sector_change", 0)
                sign = "+" if (chg or 0) >= 0 else ""
                lines.append(f"  {m.get('board_name', '')} {sign}{chg:.2f}% "
                             f"验证分: {m.get('confirmation_score', 0)}")

        events = detail.get("events", [])
        if events:
            lines.extend(["", "[bold]关联事件:[/]"])
            for e in events[:8]:
                ts = (e.get("created_at") or "")[11:19] if e.get("created_at") else ""
                score_ev = e.get("event_score", 0) or 0
                bscore = e.get("benefit_score", 0) or 0
                reason = (e.get("match_reason") or "")[:30]
                lines.append(
                    f"  {ts} [{e.get('event_type', '')}] "
                    f"事件{score_ev}分 受益{bscore}分"
                )
                if reason:
                    lines.append(f"    -> {reason}")
                summary = (e.get("ai_summary") or "")[:50]
                if summary:
                    lines.append(f"    {summary}")

        widget.update("\n".join(lines))
