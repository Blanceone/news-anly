import os
import re
from datetime import datetime

from config import Config


class WebGenerator:
    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_report(self, report_type: str, title: str, content: str, news: list = None) -> str:
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        filename = f"{report_type}_{date_str}.html"
        filepath = os.path.join(self.output_dir, filename)

        html = self._build_html(report_type, title, content, news)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  [Web] 已生成页面: {filepath}")
        return filepath

    def generate_index(self, reports: list):
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股情报系统</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; color: #333; }
.header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 40px 20px; text-align: center; }
.header h1 { font-size: 28px; margin-bottom: 8px; }
.header p { opacity: 0.8; font-size: 14px; }
.container { max-width: 800px; margin: 0 auto; padding: 20px; }
.report-card { background: white; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); transition: transform 0.2s; }
.report-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.12); }
.report-card h2 { font-size: 18px; margin-bottom: 8px; }
.report-card .meta { font-size: 12px; color: #999; margin-bottom: 12px; }
.report-card .type-badge { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px; color: white; margin-bottom: 8px; }
.type-pre { background: #e17055; }
.type-intraday { background: #00b894; }
.type-post { background: #6c5ce7; }
.report-card a { color: #2d3436; text-decoration: none; }
.report-card a:hover { color: #0984e3; }
.stock-ticker { display: flex; gap: 8px; flex-wrap: wrap; margin: 16px 0; }
.stock-ticker span { background: #dfe6e9; padding: 4px 12px; border-radius: 12px; font-size: 13px; font-weight: 500; }
.footer { text-align: center; padding: 30px; color: #999; font-size: 12px; }
</style>
</head>
<body>
<div class="header">
<h1>📈 A股情报系统</h1>
<p>盘前必读 · 盘中实时 · 盘后复盘</p>
</div>
<div class="container">
"""
        watchlist = Config.STOCK_WATCHLIST
        if watchlist:
            html += '<div class="stock-ticker">'
            for s in watchlist:
                html += f"<span>{s}</span>"
            html += "</div>"

        for report in reports:
            report_type = report.get("type", "")
            type_labels = {"pre_market": "盘前必读", "intraday": "盘中快讯", "post_market": "盘后复盘"}
            type_label = type_labels.get(report_type, report_type)
            type_badge_class = f"type-{report_type.split('_')[0]}"
            html += f"""
<div class="report-card">
<a href="{report['html_path']}">
<span class="type-badge {type_badge_class}">{type_label}</span>
<h2>{report['title']}</h2>
<div class="meta">{report['created_at']}</div>
</a>
</div>"""

        html += """
</div>
<div class="footer">
<p>数据来源：财联社、东方财富、华尔街见闻、新浪财经、雪球、证券时报</p>
<p>本系统不构成投资建议，投资有风险，入市需谨慎</p>
</div>
</body>
</html>"""
        with open(os.path.join(self.output_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  [Web] 已生成首页: {self.output_dir}/index.html")

    def _build_html(self, report_type: str, title: str, content: str, news: list = None) -> str:
        type_labels = {"pre_market": "盘前必读", "intraday": "盘中快讯", "post_market": "盘后复盘"}
        type_label = type_labels.get(report_type, report_type)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        news_html = ""
        if news:
            news_html = '<div class="news-list">'
            for item in news[:50]:
                cat = item.get("category", "")
                sentiment = item.get("sentiment", "")
                sentiment_icon = {"positive": "\U0001f4c8", "negative": "\U0001f4c9", "neutral": "\u2796"}
                icon = sentiment_icon.get(sentiment, "\U0001f4f0")
                cat_badge = f'<span class="cat-badge">{cat}</span>' if cat else ""
                news_html += f"""
<div class="news-item">
<div class="news-header">
<span class="news-source">{item['source_name']}</span>
{cat_badge}
</div>
<div class="news-title"><a href="{item.get('url', '#')}" target="_blank">{icon} {item['title']}</a></div>
<div class="news-meta">{self._fmt_time(item.get('created_at', ''))}</div>
</div>"""
            news_html += "</div>"

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - A股情报系统</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; color: #333; line-height: 1.8; }}
.header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 30px 20px; }}
.header h1 {{ font-size: 24px; margin-bottom: 6px; }}
.header .meta {{ opacity: 0.7; font-size: 13px; }}
.type-badge {{ display: inline-block; padding: 3px 12px; border-radius: 10px; font-size: 12px; color: white; margin-bottom: 8px; }}
.type-pre {{ background: #e17055; }}
.type-intraday {{ background: #00b894; }}
.type-post {{ background: #6c5ce7; }}
.container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
.content {{ background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.content h2 {{ font-size: 20px; margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 2px solid #0984e3; }}
.content h3 {{ font-size: 16px; margin: 16px 0 8px; color: #2d3436; }}
.content p {{ margin: 8px 0; }}
.content ul {{ padding-left: 20px; }}

.news-list {{ margin-top: 20px; }}
.news-item {{ padding: 14px 16px; border-bottom: 1px solid #eee; }}
.news-item:last-child {{ border-bottom: none; }}
.news-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.news-source {{ font-size: 12px; color: #0984e3; font-weight: 500; }}
.cat-badge {{ background: #dfe6e9; padding: 1px 8px; border-radius: 8px; font-size: 11px; color: #636e72; }}
.news-title {{ font-size: 15px; }}
.news-title a {{ color: #2d3436; text-decoration: none; }}
.news-title a:hover {{ color: #0984e3; }}
.news-meta {{ font-size: 12px; color: #b2bec3; margin-top: 4px; }}

.back-link {{ display: inline-block; margin: 20px 0; color: #0984e3; text-decoration: none; font-size: 14px; }}
.back-link:hover {{ text-decoration: underline; }}
.footer {{ text-align: center; padding: 30px; color: #999; font-size: 12px; }}
</style>
</head>
<body>
<div class="header">
<span class="type-badge type-{report_type.split('_')[0]}">{type_label}</span>
<h1>{title}</h1>
<div class="meta">更新时间：{now} | 自选股：{', '.join(Config.STOCK_WATCHLIST) if Config.STOCK_WATCHLIST else '未设置'}</div>
</div>
<div class="container">
<a href="index.html" class="back-link">← 返回首页</a>
<div class="content">
{self._markdown_to_html(content)}
</div>
{news_html}
<a href="index.html" class="back-link">← 返回首页</a>
</div>
<div class="footer">
<p>数据来源：财联社、东方财富、华尔街见闻、新浪财经、雪球、证券时报</p>
<p>本系统不构成投资建议</p>
</div>
</body>
</html>"""

    def _fmt_time(self, t):
        if isinstance(t, datetime):
            return t.strftime("%Y-%m-%d %H:%M")
        if isinstance(t, str):
            return t[:19]
        return str(t)

    def _markdown_to_html(self, md: str) -> str:
        html = md
        html = html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
        html = html.replace("\n\n", "</p><p>")
        html = html.replace("</p>\n<p>", "</p><p>")
        lines = html.split("\n")
        result = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- "):
                content = stripped[2:]
                if not in_list:
                    result.append("<ul>")
                    in_list = True
                result.append(f"<li>{content}</li>")
            else:
                if in_list:
                    result.append("</ul>")
                    in_list = False
                result.append(line)
        if in_list:
            result.append("</ul>")
        html = "".join(result)
        html = html.replace("<p></p>", "")
        return html
