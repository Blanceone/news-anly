# A股智能选股终端

实时采集财联社电报 + 巨潮资讯公告 → AI 事件识别 → 知识图谱产业链推理 → 多因子评分 → TUI 终端看板。

```text
新闻/公告  →  AI事件抽取  →  图谱推理受益股  →  综合评分  →  推荐榜 + TUI看板
```

## 项目结构

```
├── main.py                 # CLI入口 (run / init / tui)
├── collectors/             # 数据源采集
│   ├── cls.py              # 财联社 (签名API，增量拉取)
│   └── cninfo.py           # 巨潮资讯 (POST分页，增量拉取)
├── services/               # 业务服务层
│   ├── event_service.py    # AI事件识别 (LLM结构化JSON)
│   ├── stock_service.py    # 股票关联映射 (10主题57只受益股, 含受益链分层)
│   ├── knowledge_graph.py  # 知识图谱 (47实体 + BFS推理引擎)
│   ├── scoring_engine.py   # 综合评分 V3 (7维公式)
│   ├── market_verifier.py  # 市场验证 (Tushare主力+AKShare补充)
│   ├── theme_heat.py       # 主题热度 (含时间衰减 + 涨停热度)
│   ├── theme_discovery.py  # 新概念自动发现
│   ├── embedding_service.py# TF-IDF语义匹配
│   ├── event_cluster.py    # 事件聚类 (含生命周期管理)
│   ├── stock_profile.py    # 股票画像+龙头评分 V3
│   ├── limitup_stats.py    # 涨停热度统计 V3
│   └── backtest.py         # 回测系统 V3
├── core/
│   ├── db_init.py          # 双数据库初始化 (news.db + stocks.db)
│   ├── scheduler.py        # 采集→分析→评分 全链路编排
│   ├── analyzer.py         # LLM分析 + keyword fallback
│   └── feishu_pusher.py    # 飞书交互式卡片推送
├── tui/                    # Textual TUI终端
│   ├── app.py              # 主应用 (顶部导航1-6 + 时钟)
│   ├── db.py               # DB查询层 (跨库合并)
│   └── screens/            # 6个屏幕
│       ├── dashboard.py    # 看板: 统计栏 + 新闻流 + 推荐榜 + 题材
│       ├── theme_view.py   # 三栏: 行业板块 / 概念主题 / 成分股
│       ├── stock_view.py   # 股票: 评分排行 → 事件/主题详情
│       ├── event_view.py   # 事件: 列表 → 影响股票 + 来源新闻
│       ├── discovery_view.py # 发现: 新概念候选
│       └── cluster_view.py # 簇: 事件聚类视图
├── prd/                    # 产品需求文档 (7份)
└── ── news.db + stocks.db  # 双数据库分离
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt
pip install textual        # TUI终端
pip install akshare        # 板块行情补充
pip install tushare        # 行业分类 + 日线行情

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Keys
# AI: Gemini (免费) / DeepSeek / OpenAI 兼容
# Tushare token 用于行业/日线数据

# 3. 运行
python main.py run              # 单次增量采集+分析+评分
python main.py run --loop       # 持续循环采集 (默认5秒)
python main.py run --loop -i 30 # 每30秒轮询
python main.py init             # 检查配置
python main.py tui              # TUI终端
```

## TUI 终端操作

| 按键 | 功能 |
|------|------|
| `1` | 看板 — 统计栏 + 新闻流 + 推荐榜 + 热门题材 |
| `2` | 主题 — 主题列表 → 关联股票 |
| `3` | 股票 — 评分排行 → 事件/主题详情 |
| `4` | 事件 — 事件列表 → 影响股票 |
| `r` | 手动刷新当前页面 |
| `q` | 退出 |

Dashboard 每10秒自动刷新，其余页面每30秒自动刷新。

## 系统架构

```
                    ┌─────────────────────────────────┐
                    │        Textual TUI 终端           │
                    │  看板 | 板块 | 股票 | 事件          │
                    └──────────┬──────────────────────┘
                               │
 ┌─────────┐  ┌────────┐  ┌───┴────────┐  ┌──────┐  ┌──────────┐
 │ 财联社    │  │ 巨潮    │  │ 事件识别    │  │ 知识  │  │ 综合评分   │
 │ 电报      │→│ 资讯    │→│ (LLM)     │→│ 图谱  │→│ +推荐榜   │
 └─────────┘  └────────┘  └───────┬────┘  └──┬───┘  └────┬─────┘
                                  │          │            │
                                  ▼          ▼            ▼
                            ┌──────────────────────────────┐
                            │    news.db  |  stocks.db      │
                            │  (新闻/事件) | (股票/评分/KG)   │
                            └──────────────────────────────┘
                                         │
                          ┌──────────────┼──────────────┐
                          ▼              ▼              ▼
                    ┌──────────┐  ┌──────────┐  ┌──────────┐
                    │ Tushare  │  │ AKShare  │  │ 飞书推送   │
                    │行业+日线  │  │板块行情   │  │ 卡片消息   │
                    └──────────┘  └──────────┘  └──────────┘
```

## 核心功能

### 1. 数据采集
- 财联社电报 — 签名JSON API，`since` 参数增量拉取
- 巨潮资讯公告 — POST分页，客户端时间过滤
- 自动去重 + 72小时数据保留

### 2. AI事件识别
- LLM 结构化抽取（Gemini / DeepSeek / OpenAI）
- 8大事件类型：ORDER / EARNINGS / TECHNOLOGY / POLICY / MNA / CAPITAL / RISK / OTHER
- JSON 输出校验 + 3次重试

### 3. 股票关联映射
- 10大主题 57 只受益股：AI/算力/半导体/机器人/创新药/先进封装/具身智能/低空经济/新能源/CPO
- 关键词+行业自动匹配事件与主题

### 4. 知识图谱推理
- 5种实体：Theme → Industry → Technology → Product → Stock
- 4种关系：CONTAINS / DEPENDS / SUPPLY / BENEFIT
- BFS 多级推理（最大深度4层，权重阈值≥0.05剪枝）
- 37实体 / 53关系 / 42直连受益
- 初始覆盖：AI/算力/半导体/先进封装/具身智能/低空经济/新能源/CPO/创新药 十大主题

### 5. 综合评分 (V3)
```
总分 = 事件×15% + 受益(分层)×20% + 市场×15%
     + 热度(衰减)×15% + 簇(生命周期)×10%
     + 龙头评分×15% + 生命周期系数×10%
```
- **EventScore**: S=100 / A=80 / B=60 / C=40
- **BenefitScore**: 分层加权 DIRECT×1.0 / INDIRECT×0.8 / SENTIMENT×0.5
- **MarketScore**: 板块涨跌幅+涨跌比+成交额 (0-100)
- **ThemeHeat**: 含时间衰减（半衰期3天）+ 涨停热度
- **ClusterHeat**: 生命周期加权 BIRTH(0.8) / GROWING(1.0) / PEAK(0.7) / DECLINING(0.3) / DEAD(0.0)
- **LeaderScore**: 流动性×20% + 活跃度×30% + 题材数×20% + 涨停历史×30%

### 6. 市场验证
- 交易时段（工作日 9:25-15:00）自动运行
- **Tushare 主力**: `stock_basic.industry` 110个行业 + `daily.pct_chg` 聚合
- **AKShare 补充**: 实时行业板块 / 概念板块行情
- 涨跌幅/成交额/涨跌比综合评分

### 7. 双数据库架构
- **news.db**: news / reports / event_analysis
- **stocks.db**: stock_basic / theme_stock_mapping / event_stock_mapping / market_confirmation / stock_score / recommendation_result / kg_entity / kg_relation / kg_direct_benefit / sector_cache / theme_candidate / theme_embedding / event_cluster / event_cluster_map / theme_heat / stock_profile / theme_limitup_stats / backtest_result / backtest_trades
- 跨库 JOIN 在 Python 应用层合并

### 8. 采集即分析
- 采集后立即逐条全链路 AI 分析：事件识别 → 股票匹配 → 图谱推理 → 市场验证 → 评分
- 启动自动处理积压：未分析新闻 + 缺少股票映射的事件

### 9. 板块视图
- Tushare 110 行业 + KG 主题 + AKShare 概念 + 事件行业 = 129 板块聚合

### 10. 飞书推送
- 交互式 JSON 消息卡片
- 新闻快讯 + 每日分析报告

## 数据源

| 来源 | 类型 | 说明 |
|------|------|------|
| 财联社 (cls.cn) | JSON API | SHA1→MD5 签名，增量拉取，客户端时间过滤 |
| 巨潮资讯 (cninfo.com.cn) | POST | 分页查询，按公告日期排序，客户端时间过滤 |

## 快速体验（无需AI Key）

不配置 API Key 时，系统使用基础关键词分类运行：
- 事件类型回退为 `OTHER`
- 情绪回退为 `neutral`
- 重要性回退为 `C`
- 评分仍需事件数据支撑，建议至少配置一个 AI Provider

## 配置说明

配置文件 `.env`（参考 `.env.example`）:

| 变量 | 说明 |
|------|------|
| `TUSHARE_TOKEN` | Tushare 数据平台 Token（行业/日线数据） |
| `GEMINI_API_KEY` | Google Gemini API Key（免费，推荐首选） |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（极低成本） |
| `OPENAI_API_KEY` | OpenAI 兼容接口 Key |
| `FEISHU_WEBHOOK_URL` | 飞书机器人 Webhook URL |
| `STOCK_WATCHLIST` | 自选股逗号分隔 |
| `DATA_RETENTION_HOURS` | 数据保留小时数（默认72） |
| `FETCH_INTERVAL_SECONDS` | 循环采集间隔秒数（默认5） |

## 技术栈

- **语言**: Python 3.10+
- **采集**: requests, beautifulsoup4
- **AI**: google-genai, openai (兼容 DeepSeek/通义千问等)
- **行情**: Tushare (主力) + AKShare (补充)
- **TUI**: Textual 8.x
- **数据库**: SQLite (双库: news.db + stocks.db)
- **推送**: 飞书 Webhook
- **配置**: python-dotenv

## 开发状态

| Phase | 功能 | 状态 |
|-------|------|------|
| V1-1 | 数据流打通（采集+去重+入库） | ✅ |
| V1-2 | 事件识别引擎（8大类 + LLM抽取） | ✅ |
| V1-3 | 股票关联（10主题57只受益股） | ✅ |
| V1-4 | 知识图谱（47实体 + BFS推理） | ✅ |
| V1-5 | 评分系统V2（事件×30% + 受益×40% + 市场×30%） | ✅ |
| V1-6 | 市场验证引擎（Tushare主力 + AKShare补充） | ✅ |
| V1-7 | TUI终端（双库/6屏幕/启动分析） | ✅ |
| V2-8 | Theme Discovery（新概念自动发现） | ✅ |
| V2-9 | Embedding Match（TF-IDF语义匹配） | ✅ |
| V2-10 | Event Clustering（事件聚类+生命周期） | ✅ |
| V2-11 | Company KG（10家公司实体） | ✅ |
| V2-12 | Theme Heat（含时间衰减+涨停热度） | ✅ |
| V2-13 | 评分引擎V3（7维公式+多策略输出） | ✅ |
| V3-1 | 受益链分层（DIRECT/INDIRECT/SENTIMENT） | ✅ |
| V3-2 | 主题热度时间衰减（半衰期3天） | ✅ |
| V3-3 | Stock Profile引擎（龙头评分） | ✅ |
| V3-4 | 涨停热度系统（涨停/连板/炸板） | ✅ |
| V3-5 | 事件生命周期（BIRTH→DEAD） | ✅ |
| V3-6 | 推荐引擎V3（7维评分） | ✅ |
| V3-7 | 回测系统（胜率/夏普/回撤） | ✅ |
