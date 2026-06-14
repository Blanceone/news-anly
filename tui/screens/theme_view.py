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
        self.query_one("#concept-list", DataTable).add_columns("主题", "涨跌幅", "上涨", "下跌", "股票数")
        self.query_one("#sector-stocks", DataTable).add_columns("代码", "名称", "涨跌幅")
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
            display = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else str(chg)
            table.add_row(
                t.get("name", ""),
                display,
                str(t.get("up", 0)),
                str(t.get("down", 0)),
                str(t.get("stock_count", 0)),
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
            table.add_row("(数据不可用或非交易时段)", "", "")
            return
        stocks.sort(key=lambda s: -s.get("change", 0))
        for s in stocks[:30]:
            chg = s.get("change", 0)
            display = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else str(chg)
            table.add_row(
                s.get("stock_code", ""),
                s.get("stock_name", ""),
                display,
            )

    def _show_concept_stocks(self, concept):
        table = self.query_one("#sector-stocks", DataTable)
        table.clear()
        name = concept["name"]
        stocks = []
        # 优先AKShare概念成分股（有实时行情）
        import akshare as ak
        try:
            df = ak.stock_board_concept_cons_em(symbol=name)
            for _, row in df.iterrows():
                d = {}
                for k, v in row.items():
                    k = k.strip()
                    if "代码" in k:
                        d["stock_code"] = str(v)
                    elif "名称" in k:
                        d["stock_name"] = str(v)
                    elif "涨跌幅" in k:
                        d["change"] = round(float(v), 2) if v else 0.0
                if d.get("stock_code") and d.get("stock_name"):
                    stocks.append(d)
        except Exception:
            pass
        # 若没有实时数据，从theme_stock_mapping取
        if not stocks:
            stocks = self.db.theme_stocks(concept.get("key", name))
        if not stocks:
            table.add_row("(数据不可用)", "", "")
            return
        stocks.sort(key=lambda s: -s.get("change", 0))
        for s in stocks[:30]:
            chg = s.get("change", 0)
            display = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else str(chg)
            table.add_row(
                s.get("stock_code", ""),
                s.get("stock_name", ""),
                display,
            )
