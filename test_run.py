"""完整测试：采集 -> 摘要 -> 页面生成"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from collector import NewsCollector
from analyzer import NewsAnalyzer
from web_generator import WebGenerator

print("=" * 50)
print("1. 采集新闻")
print("=" * 50)
c = NewsCollector()
news = c.collect_all()
print(f"\n共获取 {len(news)} 条新闻")
for n in news[:10]:
    print(f"  [{n['source_name']}] {n['title'][:60]}")

print("\n" + "=" * 50)
print("2. 生成摘要")
print("=" * 50)
analyzer = NewsAnalyzer()
summary = analyzer.summarize_news(news[:30])
print(summary[:500])

print("\n" + "=" * 50)
print("3. 生成页面")
print("=" * 50)
web = WebGenerator("output")
from datetime import datetime
html_path = web.generate_report("pre_market", f"测试简报 ({datetime.now().strftime('%m-%d')})", summary, news[:30])
print(f"\n页面路径: {html_path}")

print("\n" + "=" * 50)
print("4. 生成首页")
print("=" * 50)
web.generate_index([{
    "type": "pre_market",
    "title": f"测试简报 ({datetime.now().strftime('%m-%d')})",
    "html_path": html_path,
    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
}])

print("\n✅ 测试完成")
print(f"打开 output/index.html 查看结果")
