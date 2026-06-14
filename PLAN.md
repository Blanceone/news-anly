# A股智能选股系统 — V2 开发计划

基于 `prd/# A股智能选股系统 V2 开发计划.md`，结合当前系统状态制定。

---

## V1 已完成（Phase 1-7 ✅）

```
新闻采集 → AI事件识别 → 主题匹配 → 知识图谱推理 → 市场验证 → 评分引擎 → TUI展示
```

| Phase | 功能 | 状态 |
|-------|------|------|
| 1 | 数据流打通（采集+去重+入库） | ✅ |
| 2 | 事件识别引擎（8大类 + LLM抽取 + 3次重试） | ✅ |
| 3 | 股票关联 V2（10主题57只受益股 + 关键词匹配） | ✅ |
| 4 | 知识图谱 V2（37实体/53关系 + BFS推理） | ✅ |
| 5 | 评分系统 V2（事件×30% + 受益×40% + 市场×30%） | ✅ |
| 6 | 市场验证引擎（Tushare主力 + AKShare补充） | ✅ |
| 7 | TUI终端（双库/4屏幕/板块129/自动刷新） | ✅ |

---

## V2 总目标

解决三个核心问题：

```
1. 新题材发现能力  —→  系统只能识别已存在的主题
2. 主题语义理解   —→  关键词匹配漏掉"玻璃基板≈先进封装"
3. 公司关系推理   —→  当前图谱缺公司层（华为→供应链）
```

最终链路：

```
新闻 → AI识别 → 主题发现 → 事件聚类 → 知识图谱推理 → 市场验证
      → 主题热度 → 评分引擎V2 → 推荐股票 → TUI展示
```

---

## Phase 8：Theme Discovery Engine（1周）

**优先级**: ★★★★★

### 目标
系统自动发现不在主题库中的新概念（如"韬定律"、"玻璃基板"、"AI Agent"）。

### 实现

1. **新表 `theme_candidate`**
   ```sql
   CREATE TABLE theme_candidate (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       theme_name TEXT NOT NULL,
       first_seen TIMESTAMP,
       last_seen TIMESTAMP,
       mention_count INTEGER DEFAULT 1,
       heat_score REAL DEFAULT 0,
       status TEXT DEFAULT 'candidate'  -- candidate / observing / official / deprecated
   );
   ```

2. **提取新概念**: 从 AI 事件识别的 `keywords` 和 `industry` 中，筛除已存在于 `theme_stock_mapping` / `kg_entity` / `theme_candidate` 的词，新增到 `theme_candidate`

3. **自动升级规则**: `mention_count > 20` 且 `连续出现 > 3天` → 升级为 `official`

4. **集成点**: 在 `EventService.process_news_item()` 尾部添加，每次事件分析后检查关键词

### 验收
系统能自动发现：韬定律、时间缩微、玻璃基板、AI Agent 等新概念。

---

## Phase 9：Embedding Theme Match（1周）

**优先级**: ★★★★★

### 目标
解决"玻璃基板 ≈ 先进封装"因关键词不一致导致漏匹配。

### 实现

1. **安装依赖**: `pip install sentence-transformers`
2. **新表 `theme_embedding`**
   ```sql
   CREATE TABLE theme_embedding (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       theme_name TEXT NOT NULL UNIQUE,
       description TEXT,
       embedding BLOB
   );
   ```

3. **为每个主题生成 embedding**: 用 `INITIAL_THEMES` 的 `name + keywords` 拼接描述文本，调用 sentence-transformer 生成向量

4. **匹配流程**
   ```
   新闻文本 → Embedding
                ↓
   Cosine Similarity 与所有主题 embedding 比较
                ↓
   输出 Top 3 匹配主题 + 相似度
   ```

5. **集成**: 替换 `StockService.match_event_to_stocks()` 中的纯关键词逻辑，改用 combination：embedding 匹配为主，关键词匹配为辅

### 验收
能识别：玻璃基板→先进封装(>0.8)、液冷服务器→算力基础设施(>0.8)、端侧AI→人工智能(>0.8)。

---

## Phase 10：Event Clustering Engine（3天）

**优先级**: ★★★★☆

### 目标
防止同一事件的多次报道（如"华为发布韬定律"→"机构解读"→"韬定律引发关注"）重复加分。

### 实现

1. **新表 `event_cluster`**
   ```sql
   CREATE TABLE event_cluster (
       cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
       main_event_id INTEGER,
       event_count INTEGER DEFAULT 1,
       first_seen TIMESTAMP,
       last_seen TIMESTAMP,
       heat_score REAL DEFAULT 0
   );
   ```

2. **聚类方式**: 新事件入库后，计算其 embedding 与已有事件的 cosine similarity，阈值 >0.85 则归入同一簇

3. **评分影响**: `ScoringEngine` 对同一簇内的事件去重，只取最高分事件参与计算

4. **集成**: 在 `EventService.process_news_item()` 返回前添加聚类步骤

### 验收
同一事件的 3 篇报道只算 1 次核心分数。

---

## Phase 11：Company Knowledge Graph（2周）

**优先级**: ★★★★☆

### 目标
当前图谱缺"公司"实体层，无法推理"华为采用玻璃基板"→供应链受益。

### 实现

1. **新增实体层**: `Company`
   ```python
   ("company", "华为", "通信设备、芯片设计"),
   ("company", "英伟达", "GPU、AI芯片"),
   ("company", "苹果", "消费电子"),
   ("company", "特斯拉", "电动车、机器人"),
   ```

2. **新增关系类型**
   | 关系 | 语义 | 示例 |
   |------|------|------|
   | SUPPLIER | 供应商 | 华为 → 长电科技 |
   | CUSTOMER | 客户 | 华为 → 赛力斯 |
   | COMPETITOR | 竞争对手 | 寒武纪 ↔ 英伟达 |
   | USES | 使用技术 | 华为 → 先进封装 |

3. **关系路径扩展**: `News → Company → (SUPPLIER/CUSTOMER) → Stock`

4. **AI提取公司**: 在 `EventService.extract()` 的 entities 中增加 company 识别，Prompt 加入"提取新闻中提到的上市公司或知名科技公司"

### 验收
新闻"华为采用玻璃基板方案"→ 输出长电科技、通富微电、华天科技。

---

## Phase 12：Dynamic Theme Heat System（3天）

**优先级**: ★★★★☆

### 目标
实时反映主题热度变化。

### 实现

1. **新表 `theme_heat`**
   ```sql
   CREATE TABLE theme_heat (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       theme_name TEXT NOT NULL,
       heat_score REAL DEFAULT 0,
       mention_count INTEGER DEFAULT 0,
       board_change REAL DEFAULT 0,
       board_volume REAL DEFAULT 0,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

2. **热度公式**
   ```
   HeatScore = 新闻热度(40%) + 板块热度(35%) + 资金热度(25%)
   
   新闻热度 = 过去24h提及次数 × 归一化系数
   板块热度 = 板块涨跌幅(0-40) + 板块成交额(0-30) + 涨跌比(0-30)  / 100 * 100
   资金热度 = 板块成交额 / 近5日均值 × 100 (上限100)
   ```

3. **集成**: 每次 `ScoringEngine.calculate()` 后更新；TUI Dashboard 展示热门主题

---

## Phase 13：Recommendation Engine V2（1周）

**优先级**: ★★★★★

### 目标
升级评分公式，纳入主题热度和事件簇热度。

### 实现

1. **新公式**
   ```
   TotalScore = EventScore(20%) + BenefitScore(25%) + MarketScore(20%)
              + ThemeHeat(20%) + ClusterHeat(15%)
   ```

2. **输出扩展**
   - TOP20 推荐股票（现有）
   - TOP10 热门主题（新增）
   - TOP5 新发现题材（新增）

### 验收
评分更均衡，热点题材股票排名自然上升。

---

## Phase 14：TUI V2 升级（3天）

**优先级**: ★★★☆☆

### 新增页面（作为导航 5-7）

| 按键 | 页面 | 内容 |
|------|------|------|
| 5 | Theme Discovery | 新发现主题列表 + 热度/状态/首次出现时间 |
| 6 | Event Cluster | 热点事件簇 + 簇内事件列表 + 热度 |
| 7 | Knowledge Graph View | 推理路径可视化（文本树状结构） |

---

## 开发顺序 & 预计周期

| 顺序 | Phase | 模块 | 预计时间 | 优先级 |
|------|-------|------|---------|--------|
| 1 | 8 | Theme Discovery Engine | 1周 | ★★★★★ |
| 2 | 9 | Embedding Theme Match | 1周 | ★★★★★ |
| 3 | 10 | Event Clustering | 3天 | ★★★★☆ |
| 4 | 11 | Company Knowledge Graph | 2周 | ★★★★☆ |
| 5 | 12 | Theme Heat System | 3天 | ★★★★☆ |
| 6 | 13 | Recommendation V2 | 1周 | ★★★★★ |
| 7 | 14 | TUI V2 Upgrade | 3天 | ★★★☆☆ |

**总计**: 约 6~7 周

完成后系统将从"主题映射选股系统"升级为"事件驱动智能选股系统"。

---

## 依赖关系

```
Phase 8 (Theme Discovery)
   └── Phase 9 (Embedding) — 需要 embedding 基础设施
         └── Phase 10 (Event Cluster) — 复用 embedding
               └── Phase 11 (Company KG) — 独立可并行
               └── Phase 12 (Theme Heat) — 依赖 Phase 8
                     └── Phase 13 (Rec V2) — 依赖 8/10/12
                           └── Phase 14 (TUI) — 依赖 8/10/11/12
```

Phase 8-9 可连续做（共用 embedding 基础设施），Phase 10-12 在 Phase 9 之后可并行。
