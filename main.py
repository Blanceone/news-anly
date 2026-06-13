import argparse
import io
import os
import sys

from core.scheduler import NewsScheduler


def run(loop=False, interval=None):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    s = NewsScheduler()
    if loop:
        s.run_loop(interval)
    else:
        s.run()


def run_init():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    from config import Config
    print("=== A股情报系统 初始化检查 ===")
    print(f"\nAI 提供商: {_detect_provider()}")
    feishu_status = "已配置" if Config.FEISHU_WEBHOOK_URL else "未配置"
    print(f"飞书推送: {feishu_status}")
    watchlist_status = ", ".join(Config.STOCK_WATCHLIST) if Config.STOCK_WATCHLIST else "未设置"
    print(f"自选股: {watchlist_status}")
    print(f"数据源: {len(Config.NEWS_SOURCES)} 个")
    print(f"数据保留: {Config.DATA_RETENTION_HOURS} 小时")
    print(f"采集间隔: {Config.FETCH_INTERVAL_SECONDS} 秒")
    print(f"事件识别: {'已启用 (AI)' if _detect_provider().startswith('Google') else '未启用 (需配置API)'}")
    print(f"股票映射: AI/算力/半导体/机器人/创新药 (共31只)")
    kg_count = _kg_count()
    print(f"知识图谱: {'已加载' if kg_count else '空'} ({kg_count}个实体)")
    score_count = _score_count()
    print(f"评分系统: {'已启用' if score_count else '待运行'}")
    print("\n环境检查:")
    print(f"  Python: {sys.version}")
    print(f"  工作目录: {os.getcwd()}")
    print("\n使用方式:")
    print("  python main.py run              # 单次增量采集+分析+推送")
    print("  python main.py run --loop       # 持续循环采集")
    print("  python main.py run --loop -i 30 # 每30秒轮询一次")
    print("  python main.py init             # 本检查")


def _kg_count():
    import sqlite3
    from config import Config
    try:
        with sqlite3.connect(Config.STOCKS_DB) as conn:
            return conn.execute("SELECT COUNT(*) FROM kg_entity").fetchone()[0]
    except Exception:
        return 0


def _score_count():
    import sqlite3
    from config import Config
    try:
        with sqlite3.connect(Config.STOCKS_DB) as conn:
            return conn.execute("SELECT COUNT(DISTINCT stock_code) FROM stock_score").fetchone()[0]
    except Exception:
        return 0


def _detect_provider():
    from config import Config
    if Config.GEMINI_API_KEY:
        return "Google Gemini (免费)"
    if Config.DEEPSEEK_API_KEY:
        return f"DeepSeek ({Config.DEEPSEEK_MODEL})"
    if Config.OPENAI_API_KEY:
        return f"OpenAI 兼容 ({Config.OPENAI_MODEL})"
    return "未配置 (使用基础关键词分类)"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A股情报系统")
    parser.add_argument("mode", nargs="?", default="run",
                        choices=["run", "init", "tui"])
    parser.add_argument("--loop", action="store_true", help="持续循环采集")
    parser.add_argument("-i", "--interval", type=int, default=None, help="轮询间隔（秒）")
    args = parser.parse_args()

    if args.mode == "init":
        run_init()
    elif args.mode == "tui":
        from tui.app import main as tui_main
        tui_main()
    else:
        run(loop=args.loop, interval=args.interval)
