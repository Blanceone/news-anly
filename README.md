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
│   ├── stock_service.py    # 股票关联映射 (5主题31只受益股)
│   ├── knowledge_graph.py  # 知识图谱 (28实体 + BFS推理引擎)
│   ├── scoring_engine.py   # 综合评分 (事件×30% + 受益×40% + 市场×30%)
│   └── market_verifier.py  # 市场验证 (AKShare行情 → MarketScore)
├── core/
│   ├── scheduler.py        # 采集→分析→评分 全链路编排
│   ├── analyzer.py         # LLM分析 + keyword fallback
│   └── feishu_pusher.py    # 飞书交互式卡片推送
├── tui/                    # Textual TUI终端
│   ├── app.py              # 主应用 (顶部导航1-4 + 时钟)
│   ├── db.py               # DB查询层
│   └── screens/            # 4个屏幕
│       ├── dashboard.py    # 看板: 统计栏 + 新闻流 + 推荐榜 + 题材
│       ├── theme_view.py   # 主题: 列表 → 关联股票详情
│       ├── stock_view.py   # 股票: 评分排行 → 事件/主题详情
│       └── event_view.py   # 事件: 列表 → 影响股票
└── prd/                    # 产品需求文档 (7份)
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt
pip install textual   # TUI终端
pip install akshare   # 行情数据

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Keys
# 支持: Gemini (免费) / DeepSeek / OpenAI 兼容

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
                   ┌──────────────────────────┐
                   │     Textual TUI 终端       │
                   │  看板 | 主题 | 股票 | 事件   │
                   └──────────┬───────────────┘
                              │
┌─────────┐  ┌────────┐  ┌───┴────────┐  ┌──────┐  ┌──────────┐
│ 财联社    │  │ 巨潮    │  │ 事件识别    │  │ 知识  │  │ 综合评分   │
│ 电报      │→│ 资讯    │→│ (LLM)     │→│ 图谱  │→│ +推荐榜   │
└─────────┘  └────────┘  └────────────┘  └──────┘  └──────────┘
                              │
                              ▼
                         ┌──────────┐
                         │ 市场验证   │
                         │ (AKShare) │
                         └──────────┘
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

### 3. 知识图谱推理
- 5种实体：Theme → Industry → Technology → Product → Stock
- 4种关系：CONTAINS / DEPENDS / SUPPLY / BENEFIT
- BFS 多级推理（最大深度4层，权重阈值≥0.05剪枝）
- 初始覆盖：AI/算力/半导体/先进封装/光模块/机器人/低空经济/创新药/新能源 九大主题

### 4. 综合评分
```
总分 = 事件强度×30% + 受益程度×40% + 市场验证×30%
```
- **EventScore**: S=100 / A=80 / B=60 / C=40
- **BenefitScore**: 一级=95 / 二级=80 / 三级=60
- **MarketScore**: 板块涨跌幅+涨跌比+成交额 (0-100)

### 5. 市场验证
- 交易时段（工作日 9:25-15:00）自动运行
- AKShare 实时板块行情 → 行业映射 → 涨跌幅/成交额/涨跌比评分

### 6. 飞书推送
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
- **行情**: AKShare
- **TUI**: Textual 8.x
- **数据库**: SQLite
- **推送**: 飞书 Webhook

## 开发状态

| Phase | 功能 | 状态 |
|-------|------|------|
| 1 | 数据流打通（采集+去重+入库） | ✅ |
| 2 | 事件识别引擎（8大类 + LLM抽取） | ✅ |
| 3 | 股票关联V1（5主题31只受益股） | ✅ |
| 4 | 知识图谱V1（28实体 + BFS推理） | ✅ |
| 5 | 评分系统（事件×40% + 受益×60%） | ✅ |
| 6 | 市场验证引擎（AKShare行情评分） | ✅ |
| 7 | TUI终端（Dashboard/Theme/Stock/Event） | ✅ |
| 8 | 历史回测 | ⬜ |
