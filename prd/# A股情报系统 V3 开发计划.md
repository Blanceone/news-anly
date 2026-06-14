# A股情报系统 V3 开发计划

## 当前系统状态

### 已完成

```text
新闻采集
✓

AI事件分析
✓

Theme Discovery
✓

Event Cluster
✓

Embedding Match
✓

Knowledge Graph
✓

Market Verify
✓

Theme Heat
✓

Scoring Engine
✓

TUI
✓
```

当前系统已经具备：

```text
事件驱动选股
```

能力。

---

# V3 核心目标

从：

```text
找到相关股票
```

升级为：

```text
找到最值得买的股票
```

---

# 架构升级路线

```text
新闻
↓
事件分析
↓
主题发现
↓
图谱推理
↓
股票池
↓
股票质量评估
↓
资金验证
↓
推荐排序
```

---

# Phase 1：受益链分层系统

优先级：

```text
★★★★★
```

预计：

```text
3天
```

---

## 当前问题

所有受益股：

```text
BenefitScore
```

差异不明显。

例如：

```text
华为发布先进封装技术
```

输出：

```text
长电科技
通富微电
中芯国际
北方华创
寒武纪
```

实际上：

```text
长电科技
```

和：

```text
寒武纪
```

受益程度完全不同。

---

## 新增字段

### benefit_type

```text
DIRECT
INDIRECT
SENTIMENT
```

---

## 评分权重

```text
DIRECT      1.0

INDIRECT    0.8

SENTIMENT   0.5
```

---

## 数据表

### event_stock_mapping

新增：

```sql
benefit_type TEXT
benefit_path TEXT
```

---

## 验收标准

输出：

```text
长电科技
DIRECT

通富微电
DIRECT

中芯国际
INDIRECT

寒武纪
SENTIMENT
```

---

# Phase 2：主题热度时间衰减

优先级：

```text
★★★★★
```

预计：

```text
2天
```

---

## 当前问题

旧题材长期霸榜。

---

## 新公式

```python
heat =
raw_heat *
exp(-days / half_life)
```

---

### 半衰期

```text
3天
```

---

## 示例

```text
Day0 = 100

Day3 = 50

Day6 = 25

Day9 = 12
```

---

## 新字段

### theme_heat

```sql
last_active_time
decay_heat
```

---

## 验收标准

超过一周无人提及主题：

```text
自动跌出热点榜
```

---

# Phase 3：Stock Profile 引擎

优先级：

```text
★★★★★
```

预计：

```text
1周
```

---

## 目标

建立股票画像。

---

## 新表

### stock_profile

```sql
stock_code
market_cap
turnover_rate
theme_count
industry
volatility
leader_score
```

---

## 画像指标

### 流动性

```text
近20日成交额
```

---

### 活跃度

```text
近20日换手率
```

---

### 题材丰富度

```text
所属主题数量
```

---

### 历史妖股指数

```text
近一年涨停次数
```

---

## 龙头评分

```python
leader_score =
流动性 * 20%
+
活跃度 * 30%
+
题材数 * 20%
+
涨停历史 * 30%
```

---

## 验收标准

推荐排序明显向龙头股集中。

---

# Phase 4：涨停热度系统

优先级：

```text
★★★★☆
```

预计：

```text
3天
```

---

## 当前问题

资金热度不够敏感。

---

## 新数据

每日统计：

```text
涨停数量

连板数量

炸板数量
```

---

## 新表

### theme_limitup_stats

```sql
theme_name
limitup_count
consecutive_count
broken_count
```

---

## 热度升级

```python
ThemeHeat =
新闻热度 * 40%
+
资金热度 * 25%
+
板块热度 * 20%
+
涨停热度 * 15%
```

---

## 验收标准

热点题材切换速度提升。

---

# Phase 5：事件生命周期管理

优先级：

```text
★★★★☆
```

预计：

```text
4天
```

---

## 当前问题

无法判断：

```text
事件刚启动

还是已经炒作结束
```

---

## 新字段

### event_cluster

```sql
birth_time
peak_time
decline_time
status
```

---

## 生命周期

```text
BIRTH

GROWING

PEAK

DECLINING

DEAD
```

---

## 推荐策略

### BIRTH

```text
加权
```

---

### GROWING

```text
最高权重
```

---

### PEAK

```text
适度降权
```

---

### DECLINING

```text
大幅降权
```

---

### DEAD

```text
忽略
```

---

## 验收标准

减少追高情况。

---

# Phase 6：推荐引擎V3

优先级：

```text
★★★★★
```

预计：

```text
1周
```

---

## 当前评分

```python
EventScore
BenefitScore
MarketScore
ThemeHeat
ClusterHeat
```

---

## V3评分

```python
TotalScore =

EventScore      * 15%

BenefitScore    * 20%

MarketScore     * 15%

ThemeHeat       * 15%

ClusterHeat     * 10%

LeaderScore     * 15%

LifecycleScore  * 10%
```

---

## 输出

### 热门股票

```text
TOP20
```

---

### 热门主题

```text
TOP10
```

---

### 新发现题材

```text
TOP5
```

---

### 潜伏题材

```text
TOP5
```

---

# Phase 7：回测系统

优先级：

```text
★★★★★
```

预计：

```text
2周
```

---

## 目标

验证系统是否赚钱。

---

## 回测流程

```text
历史新闻

↓

历史事件

↓

系统推荐

↓

模拟买入

↓

统计收益
```

---

## 输出指标

```text
胜率

平均收益

最大回撤

夏普比率

超额收益
```

---

## 回测周期

```text
1日

3日

5日

10日

20日
```

---

# TUI 升级

新增页面：

---

## Theme Heat

```text
热点题材榜
```

---

## Event Lifecycle

```text
事件生命周期
```

---

## Stock Profile

```text
股票画像
```

---

## Backtest

```text
策略收益曲线
```

---

# 开发顺序

```text
P1 受益链分层
P2 时间衰减
P3 Stock Profile
P4 涨停热度
P5 生命周期
P6 推荐引擎V3
P7 回测系统
```

---

# 预计周期

| 模块            | 时间 |
| ------------- | -- |
| 受益链分层         | 3天 |
| 时间衰减          | 2天 |
| Stock Profile | 1周 |
| 涨停热度          | 3天 |
| 生命周期          | 4天 |
| 推荐引擎V3        | 1周 |
| 回测系统          | 2周 |

总计：

```text
约6周
```

---

# V3 完成后的最终形态

```text
新闻
↓
AI分析
↓
主题发现
↓
事件聚类
↓
知识图谱推理
↓
股票池生成
↓
股票画像
↓
热点验证
↓
生命周期判断
↓
综合评分
↓
推荐股票
↓
回测验证
```

系统将从：

```text
新闻分析工具
```

升级为：

```text
可验证收益的事件驱动选股系统
```
