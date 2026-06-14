# A股智能选股系统 V2 开发计划

## 当前系统评估

### 已完成能力

```text
新闻采集
↓
AI事件识别
↓
主题匹配
↓
知识图谱推理
↓
市场验证
↓
评分引擎
↓
TUI展示
```

当前系统已经能够完成：

* 实时接收新闻
* 自动识别事件
* 自动关联主题
* 自动关联股票
* 自动计算推荐分数
* 自动展示推荐结果

已经具备 MVP 和 V1 能力。

---

# V2 总目标

解决三个核心问题：

```text
1. 新题材发现能力
2. 主题语义理解能力
3. 公司关系推理能力
```

最终实现：

```text
新闻
↓
发现新概念
↓
自动构建主题
↓
自动推理受益链
↓
推荐股票
```

---

# Phase 1：Theme Discovery Engine

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

解决：

```text
系统只能识别已存在主题
```

的问题。

---

## 示例

新闻：

```text
华为发布半导体韬定律
```

AI提取：

```json
{
  "keywords":[
    "韬定律",
    "时间缩微",
    "τ-scaling"
  ]
}
```

系统发现：

```text
韬定律
```

不在主题库。

---

自动创建：

```text
theme_candidate
```

记录。

---

## 新表

### theme_candidate

```sql
CREATE TABLE theme_candidate (
    id INTEGER PRIMARY KEY,

    theme_name TEXT,

    first_seen DATETIME,

    last_seen DATETIME,

    mention_count INTEGER,

    heat_score REAL,

    status TEXT
);
```

---

## 状态

```text
candidate
observing
official
deprecated
```

---

## 自动升级规则

```text
出现次数 > 20
且
连续出现天数 > 3
```

升级：

```text
official_theme
```

---

## 验收标准

系统能够自动发现：

```text
韬定律
时间缩微
玻璃基板
AI Agent
```

等新概念。

---

# Phase 2：Embedding Theme Match

优先级：

```text
★★★★★
```

预计：

```text
1周
```

---

## 当前问题

目前：

```python
keyword in text
```

进行匹配。

---

存在问题：

```text
玻璃基板
≈先进封装

但关键词不一致
```

导致漏匹配。

---

## 新方案

为每个主题生成：

```text
Embedding
```

---

### theme_embedding

```sql
theme_embedding
```

字段：

```text
theme_name

description

embedding
```

---

## 匹配流程

```text
新闻
↓
Embedding

主题库
↓
Embedding

Cosine Similarity
```

---

输出：

```text
先进封装 0.92
HBM 0.85
半导体 0.77
```

---

## 验收标准

能够识别：

```text
玻璃基板
↓
先进封装

液冷服务器
↓
算力基础设施

端侧AI
↓
人工智能
```

---

# Phase 3：事件聚类引擎

优先级：

```text
★★★★☆
```

预计：

```text
3天
```

---

## 目标

解决：

```text
同一事件重复加分
```

问题。

---

## 示例

09:00

```text
华为发布韬定律
```

09:15

```text
机构解读韬定律
```

09:30

```text
韬定律引发关注
```

---

实际上：

```text
属于同一事件
```

---

## 新表

### event_cluster

```sql
event_cluster
```

字段：

```text
cluster_id

main_event_id

event_count

heat_score
```

---

## 实现

新闻Embedding

↓

相似度聚类

↓

归属事件簇

---

## 验收

同一事件只计算一次核心分数。

---

# Phase 4：Company Knowledge Graph

优先级：

```text
★★★★☆
```

预计：

```text
2周
```

---

## 当前图谱

```text
Theme
↓
Industry
↓
Technology
↓
Product
↓
Stock
```

---

## 升级后

```text
Theme
↓
Industry
↓
Technology
↓
Product
↓
Company
↓
Stock
```

---

## 新实体

### Company

例如：

```text
华为
英伟达
苹果
特斯拉
比亚迪
```

---

## 新关系

### SUPPLIER

```text
华为
↓
长电科技
```

---

### CUSTOMER

```text
华为
↓
赛力斯
```

---

### COMPETITOR

```text
寒武纪
↔
英伟达
```

---

### USES

```text
华为
↓
先进封装
```

---

## 验收

新闻：

```text
华为采用玻璃基板方案
```

系统输出：

```text
长电科技
通富微电
华天科技
```

---

# Phase 5：动态主题热度系统

优先级：

```text
★★★★☆
```

预计：

```text
3天
```

---

## 新表

### theme_heat

```sql
theme_heat
```

---

字段：

```text
theme_name

heat_score

mention_count

board_change

board_volume
```

---

## 热度公式

```text
新闻热度
+
板块热度
+
资金热度
```

---

## 输出

```text
HBM       95
机器人     90
先进封装   88
```

---

# Phase 6：推荐引擎V2

优先级：

```text
★★★★★
```

预计：

```text
1周
```

---

## 当前公式

```text
Event
30%

Benefit
40%

Market
30%
```

---

## 新公式

```text
EventScore      20%
BenefitScore    25%
MarketScore     20%
ThemeHeat       20%
ClusterHeat     15%
```

---

## 输出

```text
TOP20 推荐股票
TOP10 热门主题
TOP5 新发现题材
```

---

# Phase 7：TUI升级

优先级：

```text
★★★☆☆
```

预计：

```text
3天
```

---

新增页面

### Theme Discovery

显示：

```text
新发现主题

韬定律

时间缩微

玻璃基板
```

---

### Event Cluster

显示：

```text
热点事件簇
```

---

### Knowledge Graph

显示：

```text
主题
↓
技术
↓
公司
↓
股票
```

推理路径。

---

# 最终目标

系统形成：

```text
新闻
↓
AI识别
↓
主题发现
↓
事件聚类
↓
知识图谱推理
↓
市场验证
↓
主题热度
↓
评分引擎
↓
推荐股票
↓
TUI展示
```

---

# 开发顺序

```text
1. Theme Discovery Engine
2. Embedding Theme Match
3. Event Cluster
4. Theme Heat
5. Company Graph
6. Recommendation V2
7. TUI Upgrade
```

---

# 预计周期

| 模块                | 时间 |
| ----------------- | -- |
| Theme Discovery   | 1周 |
| Embedding Match   | 1周 |
| Event Cluster     | 3天 |
| Theme Heat        | 3天 |
| Company Graph     | 2周 |
| Recommendation V2 | 1周 |
| TUI Upgrade       | 3天 |

总计：

```text
约6~7周
```

完成后系统将从“主题映射选股系统”升级为“事件驱动智能选股系统”。
