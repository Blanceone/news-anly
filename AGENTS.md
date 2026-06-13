# A股情报系统 — Agent Guide

## Secrets / API Keys

All tokens and API keys are stored in `C:\Users\13979\Desktop\notes\apis.txt`. Always read from that file when any credential is needed. Never hardcode keys in code or commit them.

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env        # then edit with keys
python main.py init          # check config
python main.py pre_market    # 盘前汇总 08:30
python main.py intraday      # 盘中采集
python main.py post_market   # 盘后复盘 16:30
python main.py all           # full pipeline
```

Windows encoding quirk: always set `$env:PYTHONIOENCODING="utf-8"` before running, or script auto-fixes it via `sys.stdout = io.TextIOWrapper(...)`.

## Architecture

Single Python app, 4 loosely-coupled modules orchestrated by `scheduler.py`.

```
config.py → collectors/ (fetch) → core/analyzer.py (summarize) → core/feishu_pusher.py (push)
                          ↘ SQLite (news.db) stores all articles & reports
```

Entrypoint: `main.py` parses `{pre_market, intraday, post_market, all, init}`.

## Project Structure

```
news-anly/
├── main.py                 # CLI entrypoint
├── config.py               # All config: sources, categories, API keys
├── collectors/             # Data source handlers (add new source = new file here)
│   ├── __init__.py         # NewsCollector: pipeline orchestration + DB
│   ├── cls.py              # 财联社 - sign-based JSON API
│   └── cninfo.py           # 巨潮资讯 - POST form announcements
├── core/                   # Business logic
│   ├── analyzer.py         # LLM summarization + keyword fallback
│   ├── scheduler.py        # pre_market / intraday / post_market orchestration
│   ├── web_generator.py    # Static HTML report generation
│   └── feishu_pusher.py    # Feishu card message push
├── output/                 # Generated HTML (gitignored)
└── .github/workflows/      # CI automation
```

## Config

All config lives in `config.py` + `.env` loaded via `python-dotenv`.

- **AI providers** (probed in order): Gemini > DeepSeek > OpenAI-compat. Fallback = keyword classification only.
- **NEWS_SOURCES**: dict in `config.py:26`. Each entry has `type` (`rss`|`api`) and source-specific URL/headers.
- **NEWS_CATEGORIES**: regex-free keyword matching dict in `config.py:70`. Pure substring match.
- `.env` is gitignored. GitHub Actions uses repo Secrets, not `.env`.

## Data Sources — Known State

| Source | Type | Status | Detail |
|--------|------|--------|--------|
| cls (财联社) | JSON API | ✅ 30 items/run | Sign: SHA1→MD5 of sorted params. Requires `last_time` + `sign` params. See `_collect_api()` in `collector.py:58`. |
| cninfo (巨潮资讯) | POST form | ✅ 30 items/run | Company announcements. POST to `http://www.cninfo.com.cn/new/hisAnnouncement/query`. Title format: `[股票代码 股票名] 公告标题`. |

Adding a new data source requires:
1. Entry in `config.py` `NEWS_SOURCES` dict (with `type`, `api_url`, `params`)
2. New source file in `collectors/` with a `collect(config) -> list[dict]` function
3. Register module in `collectors/__init__.py` `_HANDLERS` dict

## CI / GitHub Actions

3 separate workflow files in `.github/workflows/`:
- `pre_market.yml` — `30 0 * * 1-5` (UTC), deploys HTML to gh-pages
- `intraday.yml` — `0 2,6,7 * * 1-5` (UTC), push-only
- `post_market.yml` — `30 8 * * 1-5` (UTC), deploys HTML to gh-pages

Secrets needed: `GEMINI_API_KEY`, `FEISHU_WEBHOOK_URL`, `STOCK_WATCHLIST` (as Variable or Secret).

Env vars are written to `.env` in CI via `echo` in workflow step (not loaded from repo file).

## SQLite Schema

Auto-created `news.db` with two tables:
- `news(id TEXT PK, title, content, summary, source, source_name, url, category, sentiment, impact, related_stocks, ai_analysis, created_at, updated_at)`
- `reports(id INTEGER PK, type, title, content, created_at)`

## Noteworthy

- Feishu card messages are interactive JSON, sent via webhook POST. No Feishu SDK.
- Data older than 7 days is auto-deleted on each collection run (configurable via `DATA_RETENTION_DAYS`).
