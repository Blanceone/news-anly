"""Dashboard — SOP阶段 + 概念验证摘要 + 风控状态 + 大盘量能

Spec 6.1:
  顶部：当前时间、SOP阶段、大盘当前量能及状态（充足/萎缩）
  中部：今日触发main_concept的概念列表及最高连板龙头
  底部：最新的风控预警信号（红色高亮）
"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Header, Static

from tui.db import TuiDB


class DashboardScreen(Screen):
    BINDINGS = [("r", "refresh", "刷新")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="stats_bar")
        with Horizontal():
            with Vertical():
                yield Static("📰 最近新闻", id="news_title")
                yield DataTable(id="news_table")
            with Vertical():
                yield Static("🎯 主线概念 (main_concept)", id="concept_title")
                yield DataTable(id="concept_table")
        yield Static("📋 SOP执行日志 + 风控预警", id="bottom_title")
        with Horizontal():
            yield DataTable(id="sop_table")
            yield DataTable(id="risk_table")

    def on_mount(self) -> None:
        self._setup_tables()
        self._load_data()

    def _setup_tables(self):
        news = self.query_one("#news_table", DataTable)
        news.add_columns("时间", "标题", "来源", "类型", "情绪")
        news.cursor_type = "row"

        concept = self.query_one("#concept_table", DataTable)
        concept.add_columns("概念", "信号数", "判定", "连板", "涨停数")
        concept.cursor_type = "row"

        sop = self.query_one("#sop_table", DataTable)
        sop.add_columns("阶段", "任务", "状态", "时间")
        sop.cursor_type = "row"

        risk = self.query_one("#risk_table", DataTable)
        risk.add_columns("概念", "风险类型", "详情")
        risk.cursor_type = "row"

    def _load_data(self):
        db = TuiDB()
        stats = db.dashboard_stats()

        # Stats bar
        bar = self.query_one("#stats_bar", Static)
        bar.update(
            f"新闻: {stats.get('news_total',0)} "
            f"(今日{stats.get('news_today',0)}) | "
            f"事件: {stats.get('events_total',0)} | "
            f"概念: {stats.get('concepts_total',0)} "
            f"(验证{stats.get('concepts_validated',0)} "
            f"观察{stats.get('concepts_observing',0)} "
            f"候选{stats.get('concepts_candidate',0)}) | "
            f"未分析: {stats.get('unanalyzed',0)}"
        )

        # News table
        news_table = self.query_one("#news_table", DataTable)
        news_table.clear()
        for n in db.recent_news(30):
            t = n.get("created_at", "")[:16]
            title = n.get("title", "")[:40]
            src = n.get("source_name", "")[:6]
            cat = n.get("category", "")[:8]
            sentiment = n.get("sentiment", "")[:6]
            news_table.add_row(t, title, src, cat, sentiment)

        # Main concepts
        concept_table = self.query_one("#concept_table", DataTable)
        concept_table.clear()
        for c in db.main_concepts_today():
            concept_table.add_row(
                c.get("standard_name", "")[:12],
                f"{c.get('signal_count', 0)}/7",
                c.get("verdict", ""),
                str(c.get("max_consecutive_boards", 0)),
                str(c.get("limitup_count", 0)),
            )
        # 如果没有main_concept，显示所有概念
        if not db.main_concepts_today():
            for c in db.concepts(limit=10):
                concept_table.add_row(
                    c.get("standard_name", "")[:12],
                    f"{c.get('latest_signals', 0) or 0}/7",
                    c.get("latest_verdict", c.get("status", "")),
                    "-", "-",
                )

        # SOP logs
        sop_table = self.query_one("#sop_table", DataTable)
        sop_table.clear()
        for log in db.sop_logs(10):
            sop_table.add_row(
                log.get("phase", ""),
                log.get("task_name", ""),
                log.get("status", ""),
                log.get("started_at", "")[:19],
            )

        # Risk warnings
        risk_table = self.query_one("#risk_table", DataTable)
        risk_table.clear()
        for r in db.risk_summary():
            risk_table.add_row(
                r.get("standard_name", "")[:12],
                r.get("risk_type", ""),
                r.get("detail", "")[:30],
            )

    def action_refresh(self):
        self._load_data()
