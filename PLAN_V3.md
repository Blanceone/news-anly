# A股情报系统 — V3 开发计划

基于 `prd/# A股情报系统 V3 开发计划.md`，结合当前系统状态（V2 已完成）制定。

## V2 已完成状态

```
新闻采集 → AI事件分析 → Theme Discovery → Event Cluster → Embedding Match
→ Knowledge Graph → Market Verify → Theme Heat → Scoring Engine(V2) → TUI(V2)
```

当前系统具备 **事件驱动选股** 能力。

---

## V3 核心目标

从「找到相关股票」升级为「**找到最值得买的股票**」。

```
新闻 → 事件分析 → 主题发现 → 图谱推理 → 股票池
→ 股票质量评估 → 资金验证 → 生命周期判断 → 推荐排序 → 回测验证
```

---

## Phase 1：受益链分层系统（3天 ★★★★★）

### 当前问题
所有受益股 `BenefitScore` 差异不明显。如"华为发布先进封装技术"输出长电科技/通富微电/中芯国际/北方华创/寒武纪，但长电科技与寒武纪受益程度完全不同。

### 实现

#### 1. 新增 `benefit_type`

| 类型 | 含义 | 权重 | 示例 |
|------|------|------|------|
| DIRECT | 直接受益（产品/技术/客户一致） | 1.0 | 长电科技→先进封装 |
| INDIRECT | 间接受益（产业链上下游） | 0.8 | 中芯国际→封装设备 |
| SENTIMENT | 情绪关联（题材概念跟风） | 0.5 | 寒武纪→芯片概念 |

#### 2. 表变更：`event_stock_mapping`

```sql
ALTER TABLE event_stock_mapping ADD COLUMN benefit_type TEXT DEFAULT 'DIRECT';
ALTER TABLE event_stock_mapping ADD COLUMN benefit_path TEXT;
```

- `benefit_path` 记录推理路径，如 `"theme→industry→stock"`

#### 3. 评分权重

```python
BenefitScore = benefit_score * {
    'DIRECT': 1.0,
    'INDIRECT': 0.8,
    'SENTIMENT': 0.5,
}.get(benefit_type, 0.5)
```

#### 4. 集成点
- `StockService.process_event_stocks()` — 根据匹配来源分配 benefit_type
  - theme_stock_mapping 精准匹配 → DIRECT
  - Embedding 语义匹配 → INDIRECT
  - KG BFS 多跳推理 → 根据路径深度：1跳=DIRECT, 2跳=INDIRECT, ≥3跳=SENTIMENT
- `KnowledgeGraph._save_kg_result()` — 根据 BFS path_count 赋值 benefit_type
- `ScoringEngine` — 使用加权 BenefitScore

### 验收

```
华为先进封装技术 → 长电科技(DIRECT) / 通富微电(DIRECT)
                  / 中芯国际(INDIRECT) / 寒武纪(SENTIMENT)
```

---

## Phase 2：主题热度时间衰减（2天 ★★★★★）

### 当前问题
旧题材长期霸榜，缺乏时间衰减机制。

### 实现

#### 1. 新公式

```python
decay_heat = raw_heat * exp(-days_since_last_active / half_life)
# half_life = 3 天
```

衰减曲线：
| Day | Heat |
|-----|------|
| 0 | 100 |
| 3 | 50 |
| 6 | 25 |
| 9 | 12 |

#### 2. 表变更：`theme_heat`

```sql
ALTER TABLE theme_heat ADD COLUMN last_active_time TIMESTAMP;
ALTER TABLE theme_heat ADD COLUMN decay_heat REAL DEFAULT 0;
```

#### 3. 集成点
- `ThemeHeat.calculate()` — 每次计算时应用衰减因子
- `ScoringEngine` — 读取 `decay_heat` 替代 `raw_heat`
- 主题在 theme_candidate 中被新事件提及 → 重置 `last_active_time`

### 验收
超过一周无人提及的主题自动跌出热点榜。

---

## Phase 3：Stock Profile 引擎（1周 ★★★★★）

### 目标
建立股票画像，区分龙头股和跟风股。

### 实现

#### 1. 新表 `stock_profile`

```sql
CREATE TABLE stock_profile (
    stock_code TEXT PRIMARY KEY,
    stock_name TEXT NOT NULL,
    market_cap REAL,          -- 总市值(亿)
    turnover_rate REAL,        -- 近20日平均换手率(%)
    theme_count INTEGER,       -- 所属主题数量
    industry TEXT,             -- 所属行业
    volatility REAL,           -- 近20日波动率
    limitup_history INTEGER,   -- 近一年涨停次数
    leader_score REAL,         -- 龙头评分 0-100
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 2. 画像指标

| 指标 | 数据源 | 说明 |
|------|--------|------|
| 流动性 | Tushare daily.amount 近20日均值 | 成交额越大越好 |
| 活跃度 | Tushare daily.turnover_rate 近20日均值 | 换手率适中最优 |
| 题材丰富度 | theme_stock_mapping 计数 | 所属主题越多越好 |
| 妖股指数 | Tushare 近一年 limit_status=1 计数 | 涨停历史 |

#### 3. 龙头评分

```python
leader_score = (
    流动性 * 20% +
    活跃度 * 30% +
    题材数 * 20% +
    涨停历史 * 30%
)
```

#### 4. 数据源
- Tushare: `daily_basic(trade_date, ts_code)` — turnover_rate, amount
- Tushare: `limit_list(trade_date, ts_code)` — limit_status（涨停统计）
- Tushare: `stock_basic(ts_code)` — industry
- `theme_stock_mapping` — theme_count

#### 5. 集成点
- 新服务 `services/stock_profile.py`
- 在每个 `_tick()` 尾部更新（或每日首次运行时更新一次）
- `ScoringEngine` 读取 `leader_score`

### 验收
推荐排序明显向龙头股集中，跟风股排名自然下降。

---

## Phase 4：涨停热度系统（3天 ★★★★☆）

### 当前问题
资金热度不够敏感，无法通过涨停数据感知题材强度。

### 实现

#### 1. 新表 `theme_limitup_stats`

```sql
CREATE TABLE theme_limitup_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    theme_name TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    limitup_count INTEGER DEFAULT 0,      -- 涨停家数
    consecutive_count INTEGER DEFAULT 0,  -- 连板家数
    broken_count INTEGER DEFAULT 0,       -- 炸板家数
    first_limitup_count INTEGER DEFAULT 0,-- 首板家数
    UNIQUE(theme_name, trade_date)
);
```

#### 2. 数据源
- Tushare: `limit_list(trade_date)` — 获取每日涨停股票
- 结合 `theme_stock_mapping` 按主题聚合涨停/连板/炸板统计
- 获取 AKShare 或东方财富的炸板数据补充

#### 3. 热度公式升级

```python
ThemeHeat = (
    新闻热度 * 40% +
    资金热度 * 25% +
    板块热度 * 20% +
    涨停热度 * 15%
)

涨停热度 = (limitup_count * 10 + consecutive_count * 20 - broken_count * 5) / MAX_NORMALIZED
```

#### 4. 集成点
- 新服务 `services/limitup_stats.py`
- `ThemeHeat.calculate()` 中读取涨停数据
- 每日首次运行时更新

### 验收
热点题材切换速度提升，涨停集中题材在热度榜上明显突出。

---

## Phase 5：事件生命周期管理（4天 ★★★★☆）

### 当前问题
无法判断事件是刚启动还是已炒作结束，容易追高。

### 实现

#### 1. 表变更：`event_cluster`

```sql
ALTER TABLE event_cluster ADD COLUMN birth_time TIMESTAMP;
ALTER TABLE event_cluster ADD COLUMN peak_time TIMESTAMP;
ALTER TABLE event_cluster ADD COLUMN decline_time TIMESTAMP;
ALTER TABLE event_cluster ADD COLUMN status TEXT DEFAULT 'BIRTH';
-- status: BIRTH / GROWING / PEAK / DECLINING / DEAD
```

#### 2. 生命周期判定逻辑

```
BIRTH:      event_count < 3 且 首次出现 < 24h
GROWING:    event_count ≥ 3 且 新增频率上升
PEAK:       event_count ≥ 10 或 媒体覆盖密度最大
DECLINING:  超过 24h 无新增相关事件
DEAD:       超过 72h 无新增相关事件
```

#### 3. 评分权重调整

| 阶段 | 权重系数 |
|------|---------|
| BIRTH | 0.8 (加权，早期关注) |
| GROWING | 1.0 (最高权重) |
| PEAK | 0.7 (适度降权，防止追高) |
| DECLINING | 0.3 (大幅降权) |
| DEAD | 0.0 (忽略) |

#### 4. 集成点
- `EventClustering.cluster_event()` — 创建/更新簇时判断生命周期
- `ScoringEngine` — `ClusterHeat` 乘以生命周期系数

### 验收
减少追高情况，早期事件获得更高权重，衰退期事件自动降权。

---

## Phase 6：推荐引擎 V3（1周 ★★★★★）

### 目标
整合所有新维度，推出 V3 评分公式。

### 实现

#### 1. V3 评分公式

```python
TotalScore =
    EventScore      * 15% +
    BenefitScore    * 20% +    # 分层加权（Phase 1）
    MarketScore     * 15% +
    ThemeHeat       * 15% +    # 时间衰减后（Phase 2）
    ClusterHeat     * 10% +    # 生命周期加权（Phase 5）
    LeaderScore     * 15% +    # 龙头评分（Phase 3）
    LifecycleScore  * 10%      # 生命周期系数（Phase 5）
```

#### 2. 输出扩展

| 输出 | 内容 |
|------|------|
| TOP20 热门股票 | 综合评分排序 |
| TOP10 热门主题 | theme_heat.decay_heat 排序 |
| TOP5 新发现题材 | theme_candidate(status='observing' or 'official') 按 mention_count |
| TOP5 潜伏题材 | BIRTH 阶段主题，低热度高潜力 |

#### 3. 集成点
- `ScoringEngine.calculate()` — 重写为 V3 公式
- 新输出指标 `recommendation_result` 增加 `strategy_type`:
  - `HOT` — 热门股
  - `THEME` — 热点题材
  - `NEW` — 新发现题材
  - `LATENT` — 潜伏题材

### 验收
评分更均衡，龙头+热点+新题材各有输出，推荐不扎堆。

---

## Phase 7：回测系统（2周 ★★★★★）

### 目标
验证系统推荐是否赚钱。

### 实现

#### 1. 新服务 `services/backtest.py`

```python
class BacktestEngine:
    def run(start_date, end_date, holding_days):
        # 1. 加载历史新闻
        # 2. 用当前分析管道处理
        # 3. 生成历史推荐
        # 4. 模拟买入
        # 5. 统计收益
```

#### 2. 回测流程

```
历史新闻 → 历史事件 → 系统推荐 → 模拟买入 → 统计收益
```

#### 3. 新表 `backtest_result`

```sql
CREATE TABLE backtest_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_type TEXT,
    start_date TEXT,
    end_date TEXT,
    holding_days INTEGER,
    win_rate REAL,
    avg_return REAL,
    max_drawdown REAL,
    sharpe_ratio REAL,
    excess_return REAL,
    total_trades INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_id INTEGER,
    trade_date TEXT,
    stock_code TEXT,
    stock_name TEXT,
    buy_price REAL,
    sell_price REAL,
    holding_days INTEGER,
    return_rate REAL,
    strategy_type TEXT
);
```

#### 4. 回测周期

| 持仓周期 | 用途 |
|---------|------|
| 1日 | 短线热点 |
| 3日 | 事件驱动 |
| 5日 | 周度策略 |
| 10日 | 题材趋势 |
| 20日 | 月度策略 |

#### 5. 输出指标

| 指标 | 说明 |
|------|------|
| 胜率 | 盈利交易占比 |
| 平均收益 | 每笔交易平均收益率 |
| 最大回撤 | 账户最大回撤比例 |
| 夏普比率 | 风险调整后收益 |
| 超额收益 | 相对大盘(沪深300)超额收益 |

### 验收
系统可在历史数据上验证策略有效性，输出完整回测报告。

---

## TUI 升级（与 Phase 6-7 并行）

新增 4 个页面（导航 7-10）：

| 按键 | 页面 | 内容 |
|------|------|------|
| 7 | Theme Heat | 热点题材榜 + 主题热度趋势 |
| 8 | Event Lifecycle | 事件生命周期一览 + 各阶段事件数 |
| 9 | Stock Profile | 股票画像详情 + 龙头评分分解 |
| 10 | Backtest | 策略收益曲线 + 历史回测结果 |

---

## 开发顺序与依赖关系

```
Phase 1 (受益链分层)
   └── Phase 6 (推荐引擎V3) — 需要分层评分

Phase 2 (时间衰减)
   └── Phase 6 (推荐引擎V3) — 需要衰减后的热度

Phase 3 (Stock Profile) — 独立
   └── Phase 6 (推荐引擎V3) — 需要 leader_score

Phase 4 (涨停热度)
   └── Phase 2 (时间衰减) — 温度热度同样需要衰减
   └── Phase 6 (推荐引擎V3) — 需要涨停热度

Phase 5 (生命周期)
   └── Phase 6 (推荐引擎V3) — 需要生命周期系数

Phase 6 (推荐引擎V3) — 依赖 P1/P2/P3/P4/P5
   └── Phase 7 (回测系统) — 需要 V3 推荐结果

Phase 7 (回测系统) — 依赖 Phase 6
```

### 并行执行建议

```
Week 1-2:   P1 + P2 + P3     (可并行)
Week 2-3:   P4 + P5           (P1/P2 完成后可开始)
Week 3-5:   P6                (等待 P1~P5 全部就绪)
            同期: TUI 升级
Week 5-7:   P7                (依赖 P6)
```

## 预计周期

| 模块 | 时间 |
|------|------|
| Phase 1 受益链分层 | 3天 |
| Phase 2 时间衰减 | 2天 |
| Phase 3 Stock Profile | 1周 |
| Phase 4 涨停热度 | 3天 |
| Phase 5 生命周期 | 4天 |
| Phase 6 推荐引擎V3 | 1周 |
| Phase 7 回测系统 | 2周 |
| TUI 升级 | 合并执行 |

**总计：约 6~7 周**

---

## V3 完成后的最终形态

```
新闻 → AI分析 → 主题发现 → 事件聚类 → 知识图谱推理
→ 股票池生成 → 股票画像 → 热点验证 → 生命周期判断
→ 综合评分(V3) → 推荐股票 → 回测验证
```

系统将从「**新闻分析工具**」升级为「**可验证收益的事件驱动选股系统**」。
