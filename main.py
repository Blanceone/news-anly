import argparse
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.scheduler import NewsScheduler


def run():
    s = NewsScheduler()
    s.run()


def run_init():
    from config import Config
    print("=== A股情报系统 初始化检查 ===")
    print(f"\nAI 提供商: {_detect_provider()}")
    feishu_status = "已配置" if Config.FEISHU_WEBHOOK_URL else "未配置"
    print(f"飞书推送: {feishu_status}")
    watchlist_status = ", ".join(Config.STOCK_WATCHLIST) if Config.STOCK_WATCHLIST else "未设置"
    print(f"自选股: {watchlist_status}")
    print(f"数据源: {len(Config.NEWS_SOURCES)} 个")
    print(f"数据保留: {Config.DATA_RETENTION_HOURS} 小时")
    print("\n环境检查:")
    print(f"  Python: {sys.version}")
    print(f"  工作目录: {os.getcwd()}")
    print("\n使用方式:")
    print("  python main.py run   # 增量采集+分析+推送")
    print("  python main.py init  # 本检查")


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
                        choices=["run", "init"])
    args = parser.parse_args()

    if args.mode == "init":
        run_init()
    else:
        run()
