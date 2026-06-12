import json
import re
from datetime import datetime

import requests

from config import Config


class NewsAnalyzer:
    def __init__(self):
        self.provider = self._detect_provider()

    def _detect_provider(self) -> str:
        if Config.GEMINI_API_KEY:
            return "gemini"
        if Config.DEEPSEEK_API_KEY:
            return "deepseek"
        if Config.OPENAI_API_KEY:
            return "openai"
        return "none"

    def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        if self.provider == "gemini":
            return self._call_gemini(prompt, system_prompt)
        elif self.provider == "deepseek":
            return self._call_openai_compat(
                prompt, system_prompt,
                api_key=Config.DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com/v1",
                model=Config.DEEPSEEK_MODEL,
            )
        elif self.provider == "openai":
            return self._call_openai_compat(
                prompt, system_prompt,
                api_key=Config.OPENAI_API_KEY,
                base_url=Config.OPENAI_BASE_URL or "https://api.openai.com/v1",
                model=Config.OPENAI_MODEL,
            )
        return ""

    def _call_gemini(self, prompt: str, system_prompt: str = "") -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={Config.GEMINI_API_KEY}"
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": system_prompt}]})
            contents.append({"role": "model", "parts": [{"text": "好的，我明白要求了。"}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        payload = {"contents": contents}
        try:
            resp = requests.post(url, json=payload, timeout=60)
            data = resp.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return text
        except Exception as e:
            return f"[Gemini 调用失败] {e}"

    def _call_openai_compat(self, prompt: str, system_prompt: str, api_key: str, base_url: str, model: str) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers, timeout=60)
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return f"[API 调用失败] {e}"

    def summarize_news(self, news: list) -> str:
        if self.provider == "none":
            return self._generate_basic_summary(news)
        text = "请对以下财经新闻进行分类汇总和分析，输出格式如下：\n\n"
        text += "## 市场概览\n(总结今日市场整体情绪和走势)\n\n"
        text += "## 重点新闻分析\n(按重要性排序，每条包含：标题、来源、核心要点、影响判断)\n\n"
        text += "## 自选股相关\n(列出与自选股相关的新闻及影响分析)\n\n"
        text += "## 风险提示\n(提示需要关注的潜在风险)\n\n"
        text += f"以下是今日新闻数据（共{len(news)}条）：\n\n"
        for i, item in enumerate(news[:50], 1):
            text += f"{i}. 【{item['source_name']}】{item['title']}\n   {item.get('content', '')[:200]}\n\n"
        return self._call_llm(text, "你是一个专业的A股财经分析师，请对新闻进行专业、简洁的分析。使用中文，输出Markdown格式。")

    def _generate_basic_summary(self, news: list) -> str:
        categorized = {}
        for item in news:
            text = f"{item['title']} {item.get('content', '')}"
            found = False
            for cat, keywords in Config.NEWS_CATEGORIES.items():
                for kw in keywords:
                    if kw in text:
                        if cat not in categorized:
                            categorized[cat] = []
                        categorized[cat].append(item)
                        found = True
                        break
                if found:
                    break
            if not found:
                if "其他" not in categorized:
                    categorized["其他"] = []
                categorized["其他"].append(item)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        report = f"# 财经新闻简报 ({now})\n\n"
        report += "> 当前未配置 AI API，此为纯关键词分类摘要。配置 Gemini 可获取 AI 智能分析。\n\n"
        for cat, items in categorized.items():
            if items:
                report += f"## {cat}\n\n"
                for item in items[:10]:
                    report += f"- [{item['source_name']}] {item['title']}\n"
                report += "\n"
        return report

    def quick_analysis(self, news_item: dict) -> dict:
        if self.provider == "none":
            return {"sentiment": "neutral", "impact": 0, "reason": "未配置 AI API"}
        text = f"新闻标题：{news_item['title']}\n新闻内容：{news_item.get('content', '')[:500]}"
        prompt = f"""{text}
请分析这条新闻对A股市场的影响，返回JSON格式：
{{"sentiment": "positive/negative/neutral", "impact": "1-10的数值表示影响程度", "affected_sectors": ["受影响板块"], "reason": "分析理由"}}"""
        result = self._call_llm(prompt)
        try:
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        return {"sentiment": "neutral", "impact": 0, "affected_sectors": [], "reason": "分析失败"}
