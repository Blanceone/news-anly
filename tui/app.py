"""
A-Stock Intelligence Terminal — TUI 终端

启动: python -m tui.app  或  python main.py tui
"""
import sys
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Static
from textual.binding import Binding

from tui.screens.dashboard import DashboardScreen
from tui.screens.theme_view import ThemeViewScreen
from tui.screens.stock_view import StockViewScreen
from tui.screens.event_view import EventViewScreen
from tui.screens.discovery_view import DiscoveryViewScreen
from tui.screens.cluster_view import ClusterViewScreen
from tui.screens.theme_heat_view import ThemeHeatScreen
from tui.screens.lifecycle_view import LifecycleScreen
from tui.screens.profile_view import ProfileScreen
from tui.screens.backtest_view import BacktestScreen


class StockTUI(App):
    SCREENS = {
        "dashboard": DashboardScreen,
        "themes": ThemeViewScreen,
        "stocks": StockViewScreen,
        "events": EventViewScreen,
        "discovery": DiscoveryViewScreen,
        "clusters": ClusterViewScreen,
        "heat": ThemeHeatScreen,
        "lifecycle": LifecycleScreen,
        "profile": ProfileScreen,
        "backtest": BacktestScreen,
    }
    BINDINGS = [
        Binding("1", "switch('dashboard')", "看板"),
        Binding("2", "switch('themes')", "主题"),
        Binding("3", "switch('stocks')", "股票"),
        Binding("4", "switch('events')", "事件"),
        Binding("5", "switch('discovery')", "发现"),
        Binding("6", "switch('clusters')", "簇"),
        Binding("7", "switch('heat')", "热度"),
        Binding("8", "switch('lifecycle')", "周期"),
        Binding("9", "switch('profile')", "画像"),
        Binding("0", "switch('backtest')", "回测"),
        Binding("q", "quit", "退出"),
        Binding("r", "refresh", "刷新"),
    ]

    CSS = """
    Screen {
        background: $surface;
    }
    #top-bar {
        dock: top;
        height: 3;
        background: $panel;
        border-bottom: solid $primary;
    }
    .tab-item {
        width: 1fr;
        content-align: center middle;
        color: $text-muted;
    }
    .tab-item.active {
        color: $text;
        text-style: bold;
        background: $accent 10%;
    }
    #clock {
        width: 16;
        content-align: right middle;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-bar"):
            yield Static(" [1]看板 ", id="tab-dashboard", classes="tab-item active")
            yield Static(" [2]板块 ", id="tab-themes", classes="tab-item")
            yield Static(" [3]股票 ", id="tab-stocks", classes="tab-item")
            yield Static(" [4]事件 ", id="tab-events", classes="tab-item")
            yield Static(" [5]发现 ", id="tab-discovery", classes="tab-item")
            yield Static(" [6]簇   ", id="tab-clusters", classes="tab-item")
            yield Static(" [7]热度 ", id="tab-heat", classes="tab-item")
            yield Static(" [8]周期 ", id="tab-lifecycle", classes="tab-item")
            yield Static(" [9]画像 ", id="tab-profile", classes="tab-item")
            yield Static(" [0]回测 ", id="tab-backtest", classes="tab-item")
            yield Static("", id="clock")
        yield Footer()

    def on_mount(self):
        self._update_clock()
        self.set_interval(1, self._update_clock)
        self.push_screen("dashboard")

    def _update_clock(self):
        w = self.query_one("#clock", Static)
        w.update(datetime.now().strftime("%H:%M:%S"))

    def action_switch(self, screen_name: str):
        self.push_screen(screen_name)
        all_tabs = ["dashboard", "themes", "stocks", "events", "discovery",
                     "clusters", "heat", "lifecycle", "profile", "backtest"]
        for name in all_tabs:
            w = self.query_one(f"#tab-{name}", Static)
            w.remove_class("active")
        w = self.query_one(f"#tab-{screen_name}", Static)
        w.add_class("active")

    def action_refresh(self):
        screen = self.screen
        if hasattr(screen, "_refresh"):
            screen._refresh()

    def action_quit(self):
        self.exit()


def main():
    app = StockTUI()
    app.run()


if __name__ == "__main__":
    main()
