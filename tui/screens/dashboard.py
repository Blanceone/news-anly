import asyncio
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, DataTable

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
        self.last_fetch = datetime.now()
        self._init_tables()
        self._analyze_startup()
        self._refresh()
        self.set_interval(10, self._refresh)
        self.set_interval(30, self._background_fetch)

    def _repair_stock_mappings(self):
        import sqlite3, json
        from config import Config
        from services.stock_service import StockService
        from services.knowledge_graph import KnowledgeGraph
        from services.market_verifier import MarketVerifier
        from services.scoring_engine import ScoringEngine
        with sqlite3.connect(Config.STOCKS_DB) as sconn:
            mapped = {r[0] for r in sconn.execute("SELECT DISTINCT event_id FROM event_stock_mapping").fetchall()}
        with sqlite3.connect(Config.NEWS_DB) as nconn:
            nconn.row_factory = sqlite3.Row
            rows = nconn.execute("""
                SELECT e.event_id, e.keywords_json, e.industry
                FROM event_analysis e
                ORDER BY e.event_id
            """).fetchall()
        unmapped = [(r["event_id"], r["keywords_json"], r["industry"]) for r in rows if r["event_id"] not in mapped]
        if not unmapped:
            return
        stk = StockService()
        kg = KnowledgeGraph()
        mkt = MarketVerifier()
        for eid, kw_json, industry in unmapped:
            try:
                keywords = json.loads(kw_json or "[]")
                evt_dict = {"keywords": keywords, "industry": industry or ""}
                stk.process_event_stocks(eid, evt_dict)
                kg_result = kg.reason(keywords, industry or "")
                if kg_result:
                    self._save_kg(eid, kg_result)
                mkt.verify_event(eid, industry or "", keywords)
            except Exception:
                pass
        ScoringEngine().calculate(hours=72)

    def _analyze_startup(self):
        from collectors import NewsCollector
        collector = NewsCollector()
        backlog = collector.get_unanalyzed_news(limit=200)
        if backlog:
            self._analyze_items([], backlog)
        self._repair_stock_mappings()
        self._refresh()

    def _init_tables(self):
        self.query_one("#top-stocks-table", DataTable).add_columns("#", "code", "name", "score", "evt", "bnf", "mkt")
        self.query_one("#themes-table", DataTable).add_columns("theme", "stocks")

    async def _background_fetch(self):
        from collectors import NewsCollector
        collector = NewsCollector()
        since = collector.get_last_fetch_time()
        fresh = await asyncio.to_thread(collector.collect_since, since)
        changed = await asyncio.to_thread(self._analyze_items, fresh)
        if changed:
            self._refresh()

    def _analyze_items(self, fresh_items, backlog_items=None):
        from services.event_service import EventService
        from services.stock_service import StockService
        from services.knowledge_graph import KnowledgeGraph
        from services.market_verifier import MarketVerifier
        from services.scoring_engine import ScoringEngine
        from collectors import NewsCollector

        collector = NewsCollector()
        evt = EventService()
        stk = StockService()
        kg = KnowledgeGraph()
        mkt = MarketVerifier()
        analyzed_ids = []

        for item in fresh_items:
            try:
                event = evt.process_news_item(item)
                analyzed_ids.append(item["id"])
                event_id = self._last_event_id()
                if event_id:
                    stk.process_event_stocks(event_id, event)
                    kg_result = kg.reason(event.get("keywords", []), event.get("industry", ""),
                                           companies=event.get("companies", []))
                    if kg_result:
                        self._save_kg(event_id, kg_result)
                    mkt.verify_event(event_id, event.get("industry", ""), event.get("keywords", []))
            except Exception:
                pass

        backlog = backlog_items or collector.get_unanalyzed_news(limit=20)
        for item in backlog:
            if item["id"] in analyzed_ids:
                continue
            try:
                event = evt.process_news_item(item)
                analyzed_ids.append(item["id"])
                event_id = self._last_event_id()
                if event_id:
                    stk.process_event_stocks(event_id, event)
                    kg_result = kg.reason(event.get("keywords", []), event.get("industry", ""),
                                           companies=event.get("companies", []))
                    if kg_result:
                        self._save_kg(event_id, kg_result)
                    mkt.verify_event(event_id, event.get("industry", ""), event.get("keywords", []))
            except Exception:
                pass

        if analyzed_ids:
            collector.mark_analyzed(analyzed_ids)
            ScoringEngine().calculate(hours=72)
            return True
        return False

    def _last_event_id(self):
        import sqlite3
        from config import Config
        try:
            with sqlite3.connect(Config.NEWS_DB) as conn:
                row = conn.execute("SELECT MAX(event_id) FROM event_analysis").fetchone()
                return row[0]
        except Exception:
            return None

    def _save_kg(self, event_id, stocks):
        if not stocks:
            return
        import sqlite3
        from config import Config
        benefit_scores = {1: 95, 2: 80, 3: 60}
        with sqlite3.connect(Config.STOCKS_DB) as conn:
            for col in ("benefit_type", "benefit_path"):
                try:
                    conn.execute(f"ALTER TABLE event_stock_mapping ADD COLUMN {col} TEXT")
                except sqlite3.OperationalError:
                    pass
            for stock in stocks[:10]:
                level = 1 if stock["score"] >= 85 else (2 if stock["score"] >= 60 else 3)
                path_count = stock.get("path_count", 1)
                btype = "DIRECT" if path_count == 1 else ("INDIRECT" if path_count <= 3 else "SENTIMENT")
                bpath = f"图谱推理(路径{path_count}条,最大权重{stock['score']})"
                conn.execute("""
                    INSERT OR IGNORE INTO event_stock_mapping
                        (event_id, stock_code, stock_name, benefit_level, benefit_score,
                         benefit_type, benefit_path, match_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (event_id, stock["stock_code"], stock["stock_name"],
                      level, benefit_scores.get(level, 40),
                      btype, bpath, bpath))
            conn.commit()

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
