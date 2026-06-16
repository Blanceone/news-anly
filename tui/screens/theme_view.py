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
    .panel {
        border: solid $border;
        margin: 1 0 1 1;
    }
    .panel-right {
        border: solid $border;
        margin: 1 1 1 0;
    }
    .panel-title {
        text-style: bold;
        color: $accent;
        padding: 0 1;
    }
    .sector-list {
        width: 2fr;
    }
    .concept-list {
        width: 2fr;
    }
    .stock-list {
        width: 3fr;
    }
    DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(classes="panel sector-list"):
                yield Static("行业板块", classes="panel-title")
                yield DataTable(id="sector-list", cursor_type="row")
            with Vertical(classes="panel concept-list"):
                yield Static("概念主题", classes="panel-title")
                yield DataTable(id="concept-list", cursor_type="row")
            with Vertical(classes="panel-right stock-list"):
                yield Static("成分股", classes="panel-title")
                yield DataTable(id="sector-stocks", cursor_type="row")
        yield Footer()

    def on_mount(self):
        self.db = TuiDB()
        self.query_one("#sector-list", DataTable).add_columns("板块", "涨跌幅", "上涨", "下跌", "成交额(亿)")
        self.query_one("#concept-list", DataTable).add_columns("主题", "类型", "涨跌", "股票数", "成员")
        self.query_one("#sector-stocks", DataTable).add_columns("代码", "名称", "涨跌", "排名", "得分")
        self._refresh()
        self.set_interval(30, self._refresh)

    def _refresh(self):
        self._refresh_industries()
        self._refresh_concepts()

    def _refresh_industries(self):
        table = self.query_one("#sector-list", DataTable)
        table.clear()
        self.industries = self.db.industry_sectors()
        if not self.industries:
            table.add_row("(非交易时段，暂无实时行情)", "", "", "", "")
            return
        for s in self.industries:
            chg = s.get("change", 0)
            display = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else str(chg)
            table.add_row(
                s.get("name", ""),
                display,
                str(s.get("up", 0)),
                str(s.get("down", 0)),
                str(s.get("volume", 0)),
            )

    def _refresh_concepts(self):
        table = self.query_one("#concept-list", DataTable)
        table.clear()
        self.concepts = self.db.concept_themes()
        if not self.concepts:
            table.add_row("(暂无数据)", "", "", "", "")
            return
        for t in self.concepts:
            chg = t.get("change", 0)
            display = f"{chg:+.2f}%" if isinstance(chg, (int, float)) and chg != 0 else "-"
            cid = t.get("concept_id", t.get("key", ""))
            ctype = t.get("concept_type", t.get("source", ""))
            if cid.startswith("SW1_"):
                type_label = "L1"
            elif cid.startswith("SW2_"):
                type_label = "L2"
            elif cid.startswith("EM_"):
                type_label = "题材"
            else:
                type_label = {"industry": "行业", "concept": "题材", "kg": "KG"}.get(ctype, ctype)
            table.add_row(
                t.get("name", ""),
                type_label,
                display,
                str(t.get("stock_count", 0)),
                str(t.get("member_count", t.get("stock_count", 0))),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "sector-list":
            idx = event.cursor_row
            if idx is not None and 0 <= idx < len(self.industries):
                sector = self.industries[idx]
                self._show_sector_stocks(sector["name"])
        elif event.data_table.id == "concept-list":
            idx = event.cursor_row
            if idx is not None and 0 <= idx < len(self.concepts):
                concept = self.concepts[idx]
                self._show_concept_stocks(concept)

    def _show_sector_stocks(self, sector_name):
        table = self.query_one("#sector-stocks", DataTable)
        table.clear()
        stocks = self.db.sector_stocks(sector_name)
        if not stocks:
            table.add_row("(数据不可用或非交易时段)", "", "", "", "")
            return
        stocks.sort(key=lambda s: -s.get("change", 0))
        for i, s in enumerate(stocks[:30], 1):
            chg = s.get("change", 0)
            display = f"{chg:+.2f}%" if isinstance(chg, (int, float)) and chg != 0 else "-"
            table.add_row(
                s.get("stock_code", ""),
                s.get("stock_name", ""),
                display,
                str(s.get("rank", s.get("rank_in_concept", i))),
                str(int(s.get("score", s.get("total_score", 0)))),
            )

    def _show_concept_stocks(self, concept):
        table = self.query_one("#sector-stocks", DataTable)
        table.clear()
        concept_id = concept.get("key", concept.get("concept_id", ""))
        concept_name = concept.get("name", "")

        # V4: 优先从 concept_board_stocks 获取（带排名信息）
        stocks = self.db.concept_board_stocks(concept_id)
        if stocks:
            for i, s in enumerate(stocks[:30], 1):
                rank = s.get("rank_in_concept", i)
                score = s.get("total_score", 0)
                table.add_row(
                    s.get("stock_code", ""),
                    s.get("stock_name", ""),
                    "-",
                    f"#{rank}" if rank else str(i),
                    str(int(score)) if score else "-",
                )
            return

        # fallback: 旧方式
        stocks = self.db.theme_stocks(concept.get("key", concept_name))
        if not stocks:
            table.add_row("(暂无成分股数据)", "", "", "", "")
            return
        for i, s in enumerate(stocks[:30], 1):
            table.add_row(
                s.get("stock_code", ""),
                s.get("stock_name", ""),
                "-",
                str(i),
                "-",
            )
