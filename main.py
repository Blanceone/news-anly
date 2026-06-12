import argparse
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from datetime import datetime

from scheduler import NewsScheduler


def run_pre_market():
    s = NewsScheduler()
    s.pre_market()
    s.generate_site()


def run_intraday():
    s = NewsScheduler()
    s.intraday()


def run_post_market():
    s = NewsScheduler()
    s.post_market()
    s.generate_site()


def run_all():
    s = NewsScheduler()
    s.pre_market()
    s.intraday()
    s.post_market()
    s.generate_site()


def run_init():
    from config import Config
    print("=== A股情报系统 初始化检查 ===")
    print(f"\nAI 提供商: {_detect_provider()}")
    feishu_status = "已配置" if Config.FEISHU_WEBHOOK_URL else "未配置"
    print(f"飞书推送: {feishu_status}")
    watchlist_status = ", ".join(Config.STOCK_WATCHLIST) if Config.STOCK_WATCHLIST else "未设置"
    print(f"自选股: {watchlist_status}")
    print(f"数据源: {len(Config.NEWS_SOURCES)} 个")
    print("\n环境检查:")
    print(f"  Python: {sys.version}")
    print(f"  工作目录: {os.getcwd()}")
    print("\n使用方式:")
    print("  python main.py pre_market   # 盘前汇总 (建议 08:30)")
    print("  python main.py intraday     #盘中采集 (建议 10:00/13:30/15:00)")
    print("  python main.py post_market  #盘后复盘 (建议 16:00)")
    print("  python main.py all          # 一键全流程")
    print("  python main.py init         # 本检查")


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
    parser.add_argument("mode", nargs="?", default="init",
                        choices=["pre_market", "intraday", "post_market", "all", "init"])
    args = parser.parse_args()

    modes = {
        "pre_market": run_pre_market,
        "intraday": run_intraday,
        "post_market": run_post_market,
        "all": run_all,
        "init": run_init,
    }
    modes[args.mode]()
