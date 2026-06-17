import argparse
import io
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
    print("=== A股概念发现系统 初始化检查 ===")
    print(f"\nAI 提供商: {_detect_provider()}")
    print(f"数据源: {len(Config.NEWS_SOURCES)} 个")
    print(f"数据保留: {Config.DATA_RETENTION_HOURS} 小时")
    print(f"采集间隔: {Config.FETCH_INTERVAL_SECONDS} 秒")
    print(f"事件识别: {'已启用 (AI)' if not _detect_provider().startswith('未配置') else '未启用 (需配置API)'}")
    print(f"概念数据库: {Config.CONCEPT_DB}")
    print("\n环境检查:")
    print(f"  Python: {sys.version}")
    import os
    print(f"  工作目录: {os.getcwd()}")
    print("\n使用方式:")
    print("  python main.py run              # 单次增量采集+分析+概念发现")
    print("  python main.py run --loop       # 持续循环采集")
    print("  python main.py run --loop -i 30 # 每30秒轮询一次")
    print("  python main.py init             # 本检查")
    print("  python main.py tui              # TUI终端")


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
    parser = argparse.ArgumentParser(description="A股概念发现系统")
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
