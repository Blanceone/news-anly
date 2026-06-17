"""Validation — 7信号验证详情 + 个股3步验证

Spec 6.3:
  左侧：选中概念后，展示7个信号的 is_met 状态及 evidence
  右侧：展示该概念下 is_target=1 的个股3步验证结果
"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Header, Static

from tui.db import TuiDB


SIGNAL_NAMES = {
    1: "源头事件",
    2: "3日净流入",
    3: "涨停>=5",
    4: "竞价抢筹",
    5: "上下游扩散",
    6: "媒体热度",
    7: "研报覆盖",
}


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
        vt.add_columns("概念", "日期", "信号#", "信号名", "满足", "证据")
        vt.cursor_type = "row"

        st = self.query_one("#score_table", DataTable)
        st.add_columns("概念", "日期", "信号数", "判定")
        st.cursor_type = "row"

        svt = self.query_one("#stock_val_table", DataTable)
        svt.add_columns("股票", "概念", "日期", "关联度", "公告", "研报")
        svt.cursor_type = "row"

    def _load_data(self):
        db = TuiDB()

        # 7信号验证
        vt = self.query_one("#validation_table", DataTable)
        vt.clear()
        for v in db.concept_validations():
            signal_no = v.get("signal_no", 0)
            vt.add_row(
                v.get("standard_name", "")[:12],
                v.get("trade_date", "")[:10],
                str(signal_no),
                SIGNAL_NAMES.get(signal_no, "")[:6],
                "Y" if v.get("is_met") else "N",
                v.get("evidence", "")[:30],
            )

        # 评分
        st = self.query_one("#score_table", DataTable)
        st.clear()
        for s in db.concept_scores(50):
            st.add_row(
                s.get("standard_name", "")[:12],
                s.get("trade_date", "")[:10],
                str(s.get("signal_count", 0)),
                s.get("verdict", ""),
            )

        # 个股验证
        svt = self.query_one("#stock_val_table", DataTable)
        svt.clear()
        for sv in db.stock_validations():
            svt.add_row(
                sv.get("stock_code", ""),
                str(sv.get("concept_id", "")),
                sv.get("trade_date", "")[:10],
                sv.get("relevance", ""),
                sv.get("announce_check", ""),
                sv.get("report_check", ""),
            )

    def action_refresh(self):
        self._load_data()
