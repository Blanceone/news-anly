"""Validation — 7信号验证详情 + 个股3步验证"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Header, Static

from tui.db import TuiDB


class ValidationScreen(Screen):
    BINDINGS = [("r", "refresh", "刷新")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical():
                yield Static("7信号验证", id="val_title")
                yield DataTable(id="validation_table")
            with Vertical():
                yield Static("概念评分", id="score_title")
                yield DataTable(id="score_table")
        yield Static("个股3步验证", id="stock_val_title")
        yield DataTable(id="stock_val_table")

    def on_mount(self) -> None:
        self._setup_tables()
        self._load_data()

    def _setup_tables(self):
        vt = self.query_one("#validation_table", DataTable)
        vt.add_columns("概念", "信号", "名称", "满足", "证据", "得分")
        vt.cursor_type = "row"

        st = self.query_one("#score_table", DataTable)
        st.add_columns("概念", "信号数", "评分", "判定", "动作", "时间")
        st.cursor_type = "row"

        svt = self.query_one("#stock_val_table", DataTable)
        svt.add_columns("概念", "股票", "步骤", "通过", "证据", "排除原因")
        svt.cursor_type = "row"

    def _load_data(self):
        db = TuiDB()

        # 7信号验证
        vt = self.query_one("#validation_table", DataTable)
        vt.clear()
        for v in db.concept_validations(limit=200):
            vt.add_row(
                v.get("concept_name", v.get("concept_id", ""))[:10],
                str(v.get("signal_no", "")),
                v.get("signal_name", "")[:8],
                "Y" if v.get("is_met") else "N",
                v.get("evidence", "")[:30],
                f"{v.get('score', 0):.0f}",
            )

        # 评分
        st = self.query_one("#score_table", DataTable)
        st.clear()
        for s in db.concept_scores(50):
            st.add_row(
                s.get("concept_name", "")[:10],
                str(s.get("signal_count", 0)),
                f"{s.get('total_score', 0):.0f}",
                s.get("verdict", ""),
                s.get("action", ""),
                s.get("scored_at", "")[:16],
            )

        # 个股验证
        svt = self.query_one("#stock_val_table", DataTable)
        svt.clear()
        for sv in db.stock_validations():
            svt.add_row(
                sv.get("concept_id", "")[:10],
                f"{sv.get('stock_name','')}({sv.get('stock_code','')})",
                sv.get("step", ""),
                "Y" if sv.get("is_passed") else "N",
                sv.get("evidence", "")[:25],
                sv.get("exclude_reason", "")[:20],
            )

    def action_refresh(self):
        self._load_data()
