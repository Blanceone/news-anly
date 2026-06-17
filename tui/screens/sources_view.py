"""Sources — 信息源采集状态 + 风控总览

Spec 6.5:
  各Tier采集器的最后运行时间、今日采集条数、最新抓取的3条源头标题
"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Header, Static

from tui.db import TuiDB


class SourcesScreen(Screen):
    BINDINGS = [("r", "refresh", "刷新")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical():
                yield Static("信息源状态 (Tier 1-6)", id="source_title")
                yield DataTable(id="source_table")
            with Vertical():
                yield Static("风控总览", id="risk_title")
                yield DataTable(id="risk_table")
        yield Static("最近事件", id="event_title")
        yield DataTable(id="event_table")

    def on_mount(self) -> None:
        self._setup_tables()
        self._load_data()

    def _setup_tables(self):
        st = self.query_one("#source_table", DataTable)
        st.add_columns("Tier", "分类", "来源", "状态", "总数", "已分析", "最近采集")
        st.cursor_type = "row"

        rt = self.query_one("#risk_table", DataTable)
        rt.add_columns("概念", "风险类型", "详情")
        rt.cursor_type = "row"

        et = self.query_one("#event_table", DataTable)
        et.add_columns("时间", "类型", "情绪", "概念", "摘要")
        et.cursor_type = "row"

    def _load_data(self):
        db = TuiDB()

        # 信息源状态
        st = self.query_one("#source_table", DataTable)
        st.clear()
        source_stats = db.source_stats()

        try:
            from services.source_monitor import SourceMonitor
            tiers = SourceMonitor.get_all_tiers()
            for tier_no, tier_info in tiers.items():
                for src in tier_info["sources"]:
                    sid = src["id"]
                    stat = source_stats.get(sid, {})
                    is_active = src.get("active", False)
                    st.add_row(
                        f"Tier {tier_no}",
                        tier_info["name"][:8],
                        src["name"],
                        "active" if is_active else "planned",
                        str(stat.get("total", 0)),
                        str(stat.get("analyzed", 0)),
                        (stat.get("last_fetch", "") or "")[:16],
                    )
        except ImportError:
            for sid, stat in source_stats.items():
                st.add_row(
                    "-", "-", stat["name"],
                    "active", str(stat["total"]),
                    str(stat["analyzed"]),
                    (stat.get("last_fetch", "") or "")[:16],
                )

        # 风控总览
        rt = self.query_one("#risk_table", DataTable)
        rt.clear()
        for r in db.risk_summary():
            rt.add_row(
                r.get("standard_name", "")[:12],
                r.get("risk_type", ""),
                r.get("detail", "")[:30],
            )

        # 最近事件
        et = self.query_one("#event_table", DataTable)
        et.clear()
        for e in db.recent_events(30):
            # 解析 raw_concepts
            import json
            raw_concepts = e.get("raw_concepts", "[]")
            if isinstance(raw_concepts, str):
                try:
                    concepts_list = json.loads(raw_concepts)
                except Exception:
                    concepts_list = []
            else:
                concepts_list = raw_concepts if isinstance(raw_concepts, list) else []
            concepts_str = ", ".join(concepts_list[:3]) if concepts_list else ""

            et.add_row(
                e.get("created_at", "")[:16],
                e.get("event_type", ""),
                e.get("sentiment", ""),
                concepts_str[:15],
                e.get("summary", e.get("news_title", ""))[:35],
            )

    def action_refresh(self):
        self._load_data()
