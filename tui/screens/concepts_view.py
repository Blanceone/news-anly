"""Concepts — 概念候选池

Spec 6.2: 表格展示 concept_candidate
  列：标准概念名、状态、提及次数、最新验证结果、信号达成数(如5/7)
"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Header, Static

from tui.db import TuiDB


class ConceptsScreen(Screen):
    BINDINGS = [("r", "refresh", "刷新")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical():
                yield Static("概念候选池 (按提及数排序)", id="list_title")
                yield DataTable(id="concept_list")
            with Vertical():
                yield Static("概念详情", id="detail_title")
                yield Static("", id="detail_info")
                yield Static("关联事件", id="events_title")
                yield DataTable(id="events_table")
                yield Static("成分股", id="stocks_title")
                yield DataTable(id="stocks_table")

    def on_mount(self) -> None:
        self._setup_tables()
        self._load_concepts()

    def _setup_tables(self):
        cl = self.query_one("#concept_list", DataTable)
        cl.add_columns("标准概念名", "状态", "提及次数", "最新验证", "信号达成")
        cl.cursor_type = "row"

        ev = self.query_one("#events_table", DataTable)
        ev.add_columns("日期", "类型", "摘要")
        ev.cursor_type = "row"

        st = self.query_one("#stocks_table", DataTable)
        st.add_columns("股票代码", "角色", "目标股")
        st.cursor_type = "row"

    def _load_concepts(self):
        db = TuiDB()
        cl = self.query_one("#concept_list", DataTable)
        cl.clear()
        self._concepts = db.concepts(limit=100)
        for c in self._concepts:
            cl.add_row(
                c.get("standard_name", "")[:15],
                c.get("status", ""),
                str(c.get("mention_count", 0)),
                c.get("latest_verdict", "")[:12],
                f"{c.get('latest_signals', 0) or 0}/7",
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "concept_list":
            return
        row_idx = event.cursor_row
        if row_idx >= len(getattr(self, "_concepts", [])):
            return
        c = self._concepts[row_idx]
        db = TuiDB()
        cid = c["id"]

        # Detail
        detail = db.concept_detail(cid)
        info = self.query_one("#detail_info", Static)
        info.update(
            f"[{detail.get('status','')}] {detail.get('standard_name','')} "
            f"| 提及:{detail.get('mention_count',0)}次 "
            f"| 最近提及: {detail.get('last_mention_date','')} "
            f"| 创建: {detail.get('created_at','')[:16]}"
        )

        # Events
        ev_table = self.query_one("#events_table", DataTable)
        ev_table.clear()
        for e in db.concept_events(cid):
            ev_table.add_row(
                e.get("trade_date", "")[:10],
                e.get("event_type", ""),
                e.get("summary", "")[:40],
            )

        # Stocks
        st_table = self.query_one("#stocks_table", DataTable)
        st_table.clear()
        for s in db.concept_stocks(cid):
            st_table.add_row(
                s.get("stock_code", ""),
                s.get("role", ""),
                "Y" if s.get("is_target") else "",
            )

    def action_refresh(self):
        self._load_concepts()
