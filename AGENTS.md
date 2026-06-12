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
config.py → collector.py (fetch) → analyzer.py (summarize) → web_generator.py (HTML) + feishu_pusher.py (push)
                          ↘ SQLite (news.db) stores all articles & reports
```

Entrypoint: `main.py` parses `{pre_market, intraday, post_market, all, init}`.

## Config

All config lives in `config.py` + `.env` loaded via `python-dotenv`.

- **AI providers** (probed in order): Gemini > DeepSeek > OpenAI-compat. Fallback = keyword classification only.
- **NEWS_SOURCES**: dict in `config.py:26`. Each entry has `type` (`rss`|`api`) and source-specific URL/headers.
- **NEWS_CATEGORIES**: regex-free keyword matching dict in `config.py:70`. Pure substring match.
- `.env` is gitignored. GitHub Actions uses repo Secrets, not `.env`.

## Data Sources — Known State

| Source | Status | Issue |
|--------|--------|-------|
| wallstreetcn | ✅ 30 items/run | |
| 36kr (RSS) | ✅ 30 items/run | |
| cls (财联社 API) | ❌ returns empty | API/anti-scrape |
| xueqiu_hot | ❌ need cookies | login required |
| reuters (RSS) | ❌ unreachable | network |
| bloomberg_cn (RSS) | ❌ unreachable | network |

Adding a new data source requires:
1. Entry in `config.py` `NEWS_SOURCES` dict
2. Parse logic in `collector.py` `_collect_api()` or `_collect_rss()` (source-specific JSON path extraction)

## CI / GitHub Actions

3 separate workflow files in `.github/workflows/`:
- `pre_market.yml` — `30 0 * * 1-5` (UTC), deploys HTML to gh-pages
- `intraday.yml` — `0 2,6,7 * * 1-5` (UTC), push-only
- `post_market.yml` — `30 8 * * 1-5` (UTC), deploys HTML to gh-pages

Secrets needed: `GEMINI_API_KEY`, `FEISHU_WEBHOOK_URL`, `STOCK_WATCHLIST` (as Variable or Secret).

Env vars are written to `.env` in CI via `echo` in workflow step (not loaded from repo file).

Deploy uses `peaceiris/actions-gh-pages` from `./output`.

## SQLite Schema

Auto-created `news.db` with two tables:
- `news(id TEXT PK, title, content, summary, source, source_name, url, category, sentiment, impact, related_stocks, ai_analysis, created_at, updated_at)`
- `reports(id INTEGER PK, type, title, content, html_path, created_at)`

## Noteworthy

- HTML output goes to `output/` (gitignored). Index at `output/index.html`.
- Markdown→HTML converter is hand-written in `web_generator.py`, not a library.
- Feishu card messages are interactive JSON, sent via webhook POST. No Feishu SDK.
- `_get_page_url()` in `scheduler.py:96` has a placeholder URL — update before first deploy.
