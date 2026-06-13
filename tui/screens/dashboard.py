from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable
from textual.reactive import reactive

from tui.db import TuiDB


class DashboardScreen(Screen):
    CSS = """
    DashboardScreen {
        background: $surface;
    }
    .stats-bar {
        height: 3;
        margin: 1 0;
        border: solid $primary;
    }
    .stat-item {
        width: 1fr;
        content-align: center middle;
    }
    .panel-title {
        text-style: bold;
        color: $accent;
        padding: 0 1;
    }
    .news-panel {
        height: 1fr;
        border: solid $border;
        margin: 0 1 1 0;
    }
    .stocks-panel {
        height: 1fr;
        border: solid $border;
        margin: 0 0 1 0;
    }
    .themes-panel {
        height: 8;
        border: solid $border;
        margin: 0 1 1 1;
    }
    DataTable {
        height: 1fr;
    }
    #news-feed {
        height: 1fr;
    }
    #news-content {
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(classes="stats-bar"):
            yield Static("", id="stat-news", classes="stat-item")
            yield Static("", id="stat-events", classes="stat-item")
            yield Static("", id="stat-stocks", classes="stat-item")
        with Horizontal():
            with Vertical(classes="news-panel"):
                yield Static("news 实时新闻", classes="panel-title")
                with ScrollableContainer(id="news-feed"):
                    yield Static("loading...", id="news-content")
            with Vertical(classes="stocks-panel"):
                yield Static("top 推荐榜", classes="panel-title")
                yield DataTable(id="top-stocks-table")
        with Vertical(classes="themes-panel"):
            yield Static("hot 热门题材", classes="panel-title")
            yield DataTable(id="themes-table")
        yield Footer()

    def _refresh(self):
        self._update_stats()
        self._update_top_stocks()
        self._update_news()
        self._update_themes()

    def _update_stats(self):
        s = self.db.stats()
        self.query_one("#stat-news").update(f"news: {s['news']}")
        self.query_one("#stat-events").update(f"event: {s['events']}")
        self.query_one("#stat-stocks").update(f"stock: {s['stocks']}")

    def on_mount(self):
        self.db = TuiDB()
        self._init_tables()
        self._refresh()
        self.set_interval(10, self._refresh)

    def _init_tables(self):
        self.query_one("#top-stocks-table", DataTable).add_columns("#", "code", "name", "score", "evt", "bnf", "mkt")
        self.query_one("#themes-table", DataTable).add_columns("theme", "stocks")

    def _update_top_stocks(self):
        table = self.query_one("#top-stocks-table", DataTable)
        table.clear()
        rows = self.db.top_stocks(15)
        for i, r in enumerate(rows, 1):
            table.add_row(
                str(i),
                r.get("stock_code", ""),
                r.get("stock_name", ""),
                str(int(r.get("total_score", 0))),
                str(int(r.get("event_score", 0))),
                str(int(r.get("benefit_score", 0))),
                str(int(r.get("market_score", 0))),
            )
        if not rows:
            table.add_row("--", "no data", "", "", "", "", "")

    def _update_news(self):
        items = self.db.recent_news(hours=72, limit=30)
        widget = self.query_one("#news-content", Static)
        if not items:
            widget.update("(no news)")
            return
        lines = []
        for n in items:
            ts = (n.get("created_at") or "")[11:19] if n.get("created_at") else ""
            lines.append(f"{ts} {n['title'][:70]}")
        widget.update("\n".join(lines))

    def _update_themes(self):
        table = self.query_one("#themes-table", DataTable)
        table.clear()
        themes = self.db.hot_themes()
        for t in themes:
            table.add_row(t.get("theme_name", ""), str(t.get("stock_count", 0)))
        if not themes:
            table.add_row("no data", "0")
