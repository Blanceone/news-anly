"""A股概念发现系统 TUI 终端

5个页签:
  1 - Dashboard  (SOP阶段 + 概念验证摘要 + 风控 + 量能)
  2 - Concepts   (概念候选池)
  3 - Validation (7信号验证 + 个股3步验证)
  4 - Capital    (资金异动 + 涨停 + 龙虎榜 + 北向)
  5 - Sources    (信息源状态 + 风控总览 + 事件)
"""
from textual.app import App
from textual.binding import Binding

from tui.screens.dashboard import DashboardScreen
from tui.screens.concepts_view import ConceptsScreen
from tui.screens.validation_view import ValidationScreen
from tui.screens.capital_view import CapitalScreen
from tui.screens.sources_view import SourcesScreen


class ConceptApp(App):
    TITLE = "A股概念发现系统"
    SUB_TITLE = "概念发现 → 7信号验证 → 风控决策"

    BINDINGS = [
        Binding("1", "switch_tab('dashboard')", "Dashboard"),
        Binding("2", "switch_tab('concepts')", "Concepts"),
        Binding("3", "switch_tab('validation')", "Validation"),
        Binding("4", "switch_tab('capital')", "Capital"),
        Binding("5", "switch_tab('sources')", "Sources"),
        Binding("r", "refresh", "刷新"),
        Binding("q", "quit", "退出"),
    ]

    SCREENS = {
        "dashboard": DashboardScreen,
        "concepts": ConceptsScreen,
        "validation": ValidationScreen,
        "capital": CapitalScreen,
        "sources": SourcesScreen,
    }

    def on_mount(self) -> None:
        self.push_screen("dashboard")

    def action_switch_tab(self, tab: str) -> None:
        self.switch_mode(tab)

    def switch_mode(self, mode: str) -> None:
        self.push_screen(mode)

    def action_refresh(self) -> None:
        screen = self.screen
        if hasattr(screen, "action_refresh"):
            screen.action_refresh()


def main():
    from core.db_init import init_news_db, init_concept_db
    init_news_db()
    init_concept_db()
    app = ConceptApp()
    app.run()


if __name__ == "__main__":
    main()
