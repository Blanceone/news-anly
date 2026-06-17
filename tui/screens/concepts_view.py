"""Concepts — 概念候选池 (状态/生命周期/信号数/verdict)"""
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
        cl.add_columns("概念", "状态", "周期", "类型", "提及", "天数", "信号", "判定")
        cl.cursor_type = "row"

        ev = self.query_one("#events_table", DataTable)
        ev.add_columns("时间", "类型", "强度", "新闻标题")
        ev.cursor_type = "row"

        st = self.query_one("#stocks_table", DataTable)
        st.add_columns("股票", "角色", "来源", "核心")
        st.cursor_type = "row"

    def _load_concepts(self):
        db = TuiDB()
        cl = self.query_one("#concept_list", DataTable)
        cl.clear()
        self._concepts = db.concepts(limit=100)
        for c in self._concepts:
            cl.add_row(
                c.get("concept_name", "")[:12],
                c.get("status", ""),
                c.get("lifecycle", ""),
                c.get("concept_type", ""),
                str(c.get("mention_count", 0)),
                str(c.get("mention_days", 0)),
                f"{c.get('signal_count', 0)}/7",
                c.get("verdict", "")[:12],
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "concept_list":
            return
        row_idx = event.cursor_row
        if row_idx >= len(getattr(self, "_concepts", [])):
            return
        c = self._concepts[row_idx]
        db = TuiDB()
        cid = c["concept_id"]

        # Detail
        detail = db.concept_detail(cid)
        info = self.query_one("#detail_info", Static)
        info.update(
            f"[{detail.get('status','')}] {detail.get('concept_name','')} "
            f"| {detail.get('lifecycle','')} | "
            f"提及:{detail.get('mention_count',0)}次/{detail.get('mention_days',0)}天 "
            f"| 信号:{detail.get('signal_count',0)}/7 "
            f"| {detail.get('verdict','')}\n"
            f"行业: {detail.get('industry','')} | "
            f"首次: {detail.get('first_seen','')[:16]} | "
            f"最近: {detail.get('last_seen','')[:16]}"
        )

        # Events
        ev_table = self.query_one("#events_table", DataTable)
        ev_table.clear()
        for e in db.concept_events(cid):
            ev_table.add_row(
                e.get("created_at", "")[:16],
                e.get("event_type", ""),
                str(e.get("event_score", 0)),
                e.get("news_title", "")[:40],
            )

        # Stocks
        st_table = self.query_one("#stocks_table", DataTable)
        st_table.clear()
        for s in db.concept_stocks(cid):
            st_table.add_row(
                f"{s.get('stock_name','')}({s.get('stock_code','')})",
                s.get("role", ""),
                s.get("match_source", ""),
                "Y" if s.get("is_core") else "",
            )

    def action_refresh(self):
        self._load_concepts()
