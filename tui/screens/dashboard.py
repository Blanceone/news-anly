from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable, Label
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
    #news-feed Static {
        padding: 0 1;
        border-bottom: solid $border;
        height: 1;
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
                yield Static("📰 实时新闻", classes="panel-title")
                with ScrollableContainer(id="news-feed"):
                    yield Static("加载中...")
            with Vertical(classes="stocks-panel"):
                yield Static("🏆 推荐榜", classes="panel-title")
                yield DataTable(id="top-stocks-table")
        with Vertical(classes="themes-panel"):
            yield Static("🔥 热门题材", classes="panel-title")
            yield DataTable(id="themes-table")
        yield Footer()

    def on_mount(self):
        self.db = TuiDB()
        self._refresh()
        self.set_interval(10, self._refresh)

    def _refresh(self):
        self._update_stats()
        self._update_top_stocks()
        self._update_news()
        self._update_themes()

    def _update_stats(self):
        s = self.db.stats()
        self.query_one("#stat-news").update(f"📰 新闻: {s['news']}")
        self.query_one("#stat-events").update(f"📌 事件: {s['events']}")
        self.query_one("#stat-stocks").update(f"📈 股票: {s['stocks']}")

    def _update_top_stocks(self):
        table = self.query_one("#top-stocks-table", DataTable)
        table.clear()
        table.add_columns("排名", "代码", "名称", "总分", "事件", "受益", "市场")
        rows = self.db.top_stocks(15)
        for r in rows:
            table.add_row(
                str(r.get("total_score", 0)),
                r.get("stock_code", ""),
                r.get("stock_name", ""),
                str(int(r.get("total_score", 0))),
                str(int(r.get("event_score", 0))),
                str(int(r.get("benefit_score", 0))),
                str(int(r.get("market_score", 0))),
            )
        if not rows:
            table.add_row("—", "暂无数据", "", "", "", "", "")

    def _update_news(self):
        container = self.query_one("#news-feed", ScrollableContainer)
        container.remove_children()
        items = self.db.recent_news(hours=24, limit=30)
        if not items:
            container.mount(Static("暂无新闻"))
            return
        for n in items:
            cat = n.get("category") or n.get("source_name", "")
            ts = (n.get("created_at") or "")[11:19] if n.get("created_at") else ""
            label = f"[{ts}] [{cat}] {n['title'][:70]}"
            container.mount(Static(label))

    def _update_themes(self):
        table = self.query_one("#themes-table", DataTable)
        table.clear()
        table.add_columns("主题", "关联股票")
        themes = self.db.hot_themes()
        for t in themes:
            table.add_row(t.get("theme_name", ""), str(t.get("stock_count", 0)))
        if not themes:
            table.add_row("暂无数据", "0")
