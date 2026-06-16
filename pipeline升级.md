# Pipeline 深度升级方案

> 目标：将攻略、追星两条线从"换 Prompt 的聚合器"升级为具备独立技术深度的分析引擎。
> 原则：基于现有 `analysis_graph_*.py` 和 `PipelineConfig` 注入机制，只升级 LangGraph 子图内部节点和输出结构，不改 Pipeline 骨架。

## 一、当前状态（已实施）

| 线 | 图结构 | 节点 | 核心弱点 |
|----|--------|------|---------|
| 舆情 (risk) | analyst → (条件) → reviewer → director | 4 节点，含条件路由 | ✅ 架构完整 |
| 攻略 (guide) | extractor → comparer → summarizer | 3 节点串行 | ❌ 本质是 LLM 聚合摘要，无结构化提取 |
| 追星 (celebrity) | sentiment → heat → aggregator | 3 节点串行 | ❌ 情感/热度来自单次 LLM 估算，无时间维度 |
| 简报 (briefing) | categorizer → highlighter → writer | 3 节点串行 | ⬜ 保持现状，不需要深度升级 |

涉及文件：
- `analysis_graph_guide.py`（L1-L198，当前 ~200 行）
- `analysis_graph_celebrity.py`（L1-L186，当前 ~190 行）
- `schemas.py`（新增结构化 Pydantic model）
- `pipeline.py`（`_build_guide_results` / `_build_celebrity_results` 跟随新输出结构更新）

---

## 二、攻略线升级：从聚合摘要升级为可执行计划引擎

### 2.1 当前问题

现有 `extractor_node` 提取的是 `{place, experience, rating, source}`——扁平的四元组。一段"长沙三日游"攻略帖子包含的行程安排、时间顺序、预算区间这些结构化信息全部丢失。

现有 `comparer_node` 输出 `["共识点1", "争议点1"]`——丢掉了每个观点的来源数量，面试官看到"争议"会问"多少人这么说"。

现有 `summarizer_node` 输出 `summary + tips + sources`——没有可执行的行程结构。

### 2.2 升级目标

输出从"一篇汇总文章"变为"一份可执行的结构化计划"：

```
输入: keyword="长沙旅游"
输出:
  itinerary: [
    {day: 1, morning: {place, action, tips}, lunch: {...}, afternoon: {...}},
    {day: 2, ...}
  ]
  budget: {min: 1500, max: 2500, unit: "元/人"}
  consensus: [
    {point: "橘子洲值得去", support: 19, oppose: 4, total: 23, recommendation: "时间充裕则去"}
  ]
  tips: [
    {tip: "提前预约岳麓山索道", sources: 5, confidence: "high"},
    {tip: "文和友性价比低", sources: 3, confidence: "low"}
  ]
```

### 2.3 新图结构

```
extractor(structure) → comparer(weighted) → planner → summarizer
                          │
                          └─ 信源元数据注入
```

新增一个节点，升级两个节点。

#### Extractor 升级：结构化槽位提取

当前提取 `{place, experience, rating, source}` 四条信息。

改为提取 `{time_slot, location, action, cost, rating, source_platform, source_type}` 多个槽位。每条帖子被解析成结构化的"动作卡片"后，planner 节点才能对齐时间线。

```python
# schemas.py 新增

class GuideSlot(BaseModel):
    """单条帖子中的一条可执行信息"""
    time_slot: str = ""            # "上午" / "午餐" / "下午" / "晚上" / "全天"
    location: str = ""             # 具体地点
    action: str = ""               # "参观" / "用餐" / "住宿" / "购物"
    description: str = ""          # 体验描述
    rating: int = 1                # 1-5
    cost_min: int = 0              # 最低费用
    cost_max: int = 0              # 最高费用
    platform: str = ""             # "xhs" / "bili" / "zhihu"
    author_type: str = ""          # "素人" / "KOL" / "商家"
    confidence: float = 0.8        # LLM 对该提取结果的置信度


class GuideExtractionOutput(BaseModel):
    slots: list[GuideSlot]
    summary: str = ""              # 原文一句话摘要
```

#### Comparer 升级：信源加权对比

当前 comparer 只输出共识/争议字符串列表。

改为按平台和作者类型对同一目标做加权对比，输出带支持数的结论：

```python
# schemas.py 新增

class WeightedOpinion(BaseModel):
    """加权后的意见项"""
    point: str                     # 观点描述
    support_count: int             # 支持数
    oppose_count: int              # 反对数
    neutral_count: int             # 中立数
    platforms: dict[str, int]      # {平台: 样本数}
    weighted_score: float          # 平台加权后的综合评分（1-5）
    recommendation: str            # "推荐" / "谨慎" / "不推荐"


class GuideCompareOutput(BaseModel):
    opinions: list[WeightedOpinion]
    high_confidence: list[WeightedOpinion]    # 支持率 > 70%
    controversial: list[WeightedOpinion]      # 支持/反对均 > 30%
```

加权逻辑（代码中实现，非 LLM 判断）：

```python
PLATFORM_WEIGHTS = {
    "xhs": 0.3,      # 小红书偏主观
    "zhihu": 0.4,     # 知乎长文更理性
    "bili": 0.3,      # B站样本少
    "wb": 0.2,        # 微博信噪比低
}

def _calc_weighted_score(opinion: dict) -> float:
    """按平台类型加权计算综合评分，而非所有来源平等混合"""
    total_weight = 0
    weighted_sum = 0
    for platform, count in opinion["platforms"].items():
        w = PLATFORM_WEIGHTS.get(platform, 0.25)
        total_weight += w * count
        weighted_sum += w * opinion["avg_rating"] * count
    return weighted_sum / total_weight if total_weight > 0 else 3.0
```

#### Planner 节点（新增）

这是从"聚合"到"可执行"的核心差异。Planner 把提取到的多张 GuideSlot 按时间对齐、按地点聚类、补充空缺标记：

```python
def planner_node(state: GuideGraphState) -> dict:
    """
    将 extracted_slots 对齐为多日行程计划。
    核心逻辑：
    1. 按 location 聚类（同一地点不同帖子提到的内容合并）
    2. 按 time_slot 排序（早上 → 午餐 → 下午 → 晚餐 → 晚上）
    3. 标记空缺槽位（"Day 2 午餐无数据"）
    4. 汇总预算区间
    """
    slots = state.get("extracted_slots", [])
    opinions = state.get("weighted_opinions", [])

    # 1. 按地点聚类
    clusters = _cluster_by_location(slots)

    # 2. 为每个地点找最佳时间槽
    itinerary = _align_to_itinerary(clusters, slots)

    # 3. 检测空缺
    for day in itinerary:
        for slot_name in ["morning", "lunch", "afternoon", "dinner", "evening"]:
            if not any(s["time_slot"] == slot_name for s in day["slots"]):
                day["gaps"].append({
                    "slot": slot_name,
                    "note": "暂无足够数据，建议自行搜索",
                })

    # 4. 汇总预算
    all_costs = [(s.get("cost_min", 0), s.get("cost_max", 0)) for s in slots
                 if s.get("cost_min") or s.get("cost_max")]
    budget = _estimate_budget(all_costs, len(itinerary))

    # 5. LLM 润色（只在结构对齐后做一次）
    plan_text = _llm_polish(itinerary, budget, opinions, keyword)

    return {"itinerary": itinerary, "budget": budget, "plan_text": plan_text}
```

Planner 不是全 LLM 驱动——聚类、排序、空缺检测是纯规则代码。LLM 只在最后一步做文字润色。这样既保持了结构化输出的可靠性，又不需要 LLM 做精确的日程对齐。

#### 最终输出结构

```python
class GuidePlanOutput(BaseModel):
    """攻略线最终输出"""
    keyword: str
    itinerary: list[dict]     # [{day, morning, lunch, afternoon, dinner, gaps}]
    budget: dict              # {min, max, unit, note}
    high_confidence: list[WeightedOpinion]
    controversial: list[WeightedOpinion]
    tips: list[dict]          # [{text, sources_count, confidence_level}]
    source_summary: dict[str, int]  # {平台: 帖子数}
```

### 2.4 改动清单

| 文件 | 改动 | 行数 |
|------|------|------|
| `schemas.py` | 新增 GuideSlot / WeightedOpinion / GuidePlanOutput | ~40 |
| `analysis_graph_guide.py` | extractor 升级槽位提取 + comparer 加权 + 新增 planner + summarizer 改润色 | ~150 |
| `pipeline.py` | `_build_guide_results` 适配新输出结构 | ~25 |

---

## 三、追星线升级：从热度统计升级为叙事追踪

### 3.1 当前问题

现有 `sentiment_node` 输出的情感分布来自单次 LLM 估算——LLM 从内容推断情感，本质上是在猜"这条内容看起来像正面还是负面"。一方面猜不准，另一方面缺乏时间维度。

现有 `heat_node` 仅输出 `rising/stable/falling`——LLM 猜的，没有速度。

现有 `aggregator_node` 的跨平台分布也是 LLM 猜的——代码里没有实际统计每个平台的帖子数。

### 3.2 升级目标

从"当前快照"变为"带时间维度和跨平台叙事对比的追踪报告"：

```
输入: celebrity_name="某明星"
输出:
  sentiment_velocity: [
    {ts: "T0 14:00", positive: 0.55, negative: 0.05, neutral: 0.40, volume: 120},
    {ts: "T0 15:00", positive: 0.62, negative: 0.08, neutral: 0.30, volume: 208},
    {ts: "T0 16:00", positive: 0.78, negative: 0.06, neutral: 0.16, volume: 345},
  ]
  cross_platform_narrative: {
    "wb":  {count: 201, sentiment: {pos:0.85, neg:0.02}, narrative: "粉丝控评+新剧安利"},
    "xhs": {count: 89,  sentiment: {pos:0.60, neg:0.05}, narrative: "穿搭同款+美图分享"},
    "bili": {count: 38,  sentiment: {pos:0.40, neg:0.25}, narrative: "剪辑二创+演技质疑"},
    "narrative_contrast": "微博以粉丝正面声援为主，B站出现路人负面讨论，同一事件在不同圈层的叙事明显分化"
  }
```

### 3.3 关键点：情感不靠 LLM 猜

当前 sentiment_node 让 LLM 从文本内容猜情感——这不可靠。

改为**规则判定 + 自建领域情感词典**。追星场景的情感信号非常明确——"绝了""炸裂" = 正面，"糊了""塌房" = 负面——与通用情感词典（BosonNLP 等）差异显著，通用词典对"绝了"判定中性，对"塌房"不收录。

方案：在 `analysis_graph_celebrity.py` 同级新建 `sentiment_dict.py`，约 80 个种子词，按 positive / negative / neutral_hints 三类组织。零外部文件依赖，部署时仅多一个 Python 模块。

```python
SENTIMENT_DICT = {
    "positive": {"绝了", "太绝了", "炸裂", "宝藏", "爱了", "太帅了", "演技在线", ...},
    "negative": {"糊了", "塌房", "翻车", "油腻", "尴尬", "退圈", "太丑了", ...},
    "neutral_hints": {"据说", "听说", "可能", "好像", ...},
}

def _rule_sentiment(text: str) -> str:
    """规则层情感判定（零 token 成本）"""
    pos = sum(1 for w in SENTIMENT_DICT["positive"] if w in text)
    neg = sum(1 for w in SENTIMENT_DICT["negative"] if w in text)
    if pos > neg * 2:
        return "positive"
    if neg > pos * 2:
        return "negative"
    return "neutral"
```

sentiment_node 改为：规则层先判定 → LLM 只处理规则无法判断的模糊内容（< 20% 的情况）。

### 3.4 情感速度：时间维度的 Delta 计算

不是"现在热度上升"，而是"从什么时候开始上升、多快、持续多久"。

```python
def _calc_velocity(snapshots: list[dict]) -> list[dict]:
    """
    输入: [{ts, positive, negative, neutral, volume}, ...]
    输出: 带 delta 的快照列表
    """
    result = []
    prev = None
    for s in snapshots:
        delta = {"positive": 0.0, "negative": 0.0, "volume": 0}
        if prev:
            delta["positive"] = s["positive"] - prev["positive"]
            delta["negative"] = s["negative"] - prev["negative"]
            delta["volume"] = s["volume"] - prev["volume"]
        result.append({**s, "delta": delta})
        prev = s
    return result
```

时间快照来自定时采集的历史数据——每条 pipeline 运行后往 `celebrity_snapshots` 表写一行，查最近 24 小时的快照做 Delta。

### 3.5 跨平台叙事对比

当前 aggregator_node 的跨平台分布是 LLM 猜的。

改为从实际数据计算：posts 表里每条记录的 platform 字段直接分组统计，叙事描述才由 LLM 根据实际分布生成。

```python
def _calc_platform_distribution(posts: list[dict]) -> dict:
    """从实际数据计算平台分布，不需要 LLM 猜"""
    platforms = {}
    for p in posts:
        plat = p.get("platform", "unknown")
        platforms.setdefault(plat, {"count": 0, "posts": []})
        platforms[plat]["count"] += 1
        platforms[plat]["posts"].append(p.get("content", "")[:100])

    # 每个平台的叙事描述由 LLM 根据该平台的 sample posts 生成
    for plat, data in platforms.items():
        sample = "\n".join(data["posts"][:5])  # 最多 5 条
        data["narrative"] = _llm_narrative(plat, sample)

    return platforms
```

### 3.6 新图结构与 State 定义

```
sentinel(路由) ─┬─ sentiment(规则+LLM) ─┐
                ├─ platform_counter      ─┤
                └─ snapshot_loader       ─┘
                           │
                           ▼
                     velocity_calc(规则) → narrative_writer(LLM)
```

改动：sentinel 节点做并行分发（LangGraph Send API），三个子节点各自跑完再汇总到 velocity_calc，最后 narrative_writer 生成最终报告。

**完整的 State 定义**：

```python
# analysis_graph_celebrity.py 中替换现有 CelebrityGraphState

class CelebrityGraphState(TypedDict):
    """追星图状态（升级后）"""
    # 输入
    mock_post: dict
    keyword: str
    sensitivity: str
    # sentiment 输出（规则层 + LLM 补充）
    rule_sentiment: dict          # {"positive": int, "negative": int, "neutral": int, "fuzzy": int}
    llm_sentiment: dict           # LLM 仅对 fuzzy 内容做情感判定
    # platform_counter 输出
    platform_counts: dict         # {platform: count}，数据源：posts 表
    # snapshot_loader 输出
    historical_snapshots: list    # 过去 24h 快照，供 velocity_calc 做 Delta
    # velocity_calc 输出
    sentiment_velocity: list      # [{ts, positive, negative, neutral, volume, delta}]
    # narrative_writer 输出
    cross_platform_narrative: dict  # {"wb": {count, sentiment, narrative}, ...}
    narrative_contrast: str       # LLM 生成的跨平台叙事对比
    final_report: str             # 最终追踪报告
```

**并行 Fan-In 机制（关键设计决策）**：

LangGraph 的 `StateGraph` 默认用 `dict.update()` 合并并行节点的输出——最后一个到达的会覆盖前面的同名 key。方案不使用 Send API，而是使用 **独立 key 前缀隔离**：三个并行节点各自写入不同前缀的 state key（`rule_sentiment` / `platform_counts` / `historical_snapshots`），互不覆盖。velocity_calc 作为汇聚节点分别读取这三个 key，做合并计算。

```python
def sentinel_node(state: CelebrityGraphState) -> list[Send]:
    """分发到三个子节点并行处理，使用独立 key 避免覆盖"""
    return [
        Send("sentiment", {"mock_post": state["mock_post"], "keyword": state["keyword"]}),
        Send("platform_counter", {"mock_post": state["mock_post"]}),
        Send("snapshot_loader", {"keyword": state["keyword"]}),
    ]
```

三个节点分别写不同 key：
- `sentiment_node` → `rule_sentiment` + `llm_sentiment`
- `platform_counter_node` → `platform_counts`
- `snapshot_loader_node` → `historical_snapshots`

velocity_calc 读取三个独立 key，不存在覆盖。

### 3.7 改动清单

| 文件 | 改动 | 行数 |
|------|------|------|
| `schemas.py` | 新增 CelebritySnapshot / SentimentVelocity / CrossPlatformNarrative | ~30 |
| `sentiment_dict.py` | 新文件：自建领域情感词典（~80 词） | ~20 |
| `analysis_graph_celebrity.py` | sentiment_node 规则+LLM，新增 sentinel/platform_counter/snapshot_loader/velocity_calc/narrative_writer 节点 | ~180 |
| `pipeline.py` | `_build_celebrity_results` 适配新输出 | ~20 |
| 数据库 | 新增 `celebrity_snapshots` 表（存时间序列） | 1 SQL |
| Scheduler | 追星线跑完后写快照 | ~15 |

---

## 四、升级前后对比

### 攻略线

| 维度 | 升级前 | 升级后 |
|------|--------|--------|
| 提取方式 | 扁平四元组 (place, experience, rating, source) | 多维槽位 (time, location, action, cost, rating, platform, author_type) |
| 对比方式 | 字符串列表 ("共识1", "争议1") | 加权对比，带支持/反对数 + 平台权重 |
| 输出形态 | 一篇摘要文章 | 可执行的多日行程计划 + 预算 + 共识/争议 |
| 核心技术点 | LLM 聚合 | 结构化槽位提取 + 规则层时间对齐 + 空缺标记 + LLM 润色 |

### 追星线

| 维度 | 升级前 | 升级后 |
|------|--------|--------|
| 情感判定 | LLM 猜情感（全量） | 规则词典（80%）+ LLM 补位（20%） |
| 热度分析 | LLM 猜 rising/stable/falling | 时间序列 Delta 计算，带速度和加速度 |
| 跨平台分析 | LLM 猜分布和叙事 | 实际数据统计（count）+ LLM 生成叙事描述 |
| 核心技术点 | LLM 估算 | 规则+LLM 混合 + 时间序列 Delta + LangGraph Send API 并行 |

---

## 五、实施路线

| 阶段 | 内容 | 行数 | 时间 |
|------|------|------|------|
| 1 | `schemas.py` 新增全部 Pydantic model | ~70 | 30min |
| 2 | 攻略线 extractor 升级为槽位提取 | ~50 | 45min |
| 3 | 攻略线 comparer 升级为加权对比 | ~40 | 30min |
| 4 | 攻略线新增 planner 节点 | ~70 | 1.5h |
| 5 | `sentiment_dict.py` 自建领域情感词典 | ~20 | 30min |
| 6 | 追星线 sentinel + 规则情感 + platform_counter + snapshot_loader | ~60 | 1h |
| 7 | 追星线 velocity_calc + narrative_writer | ~60 | 1h |
| 8 | 追星线 LangGraph Send 并行编排（含 fan-in 调试） | ~40 | 1.5h |
| 9 | 新增 `celebrity_snapshots` 表 + scheduler 写快照 | ~25 | 45min |
| 10 | `pipeline.py` 两个 result builder 适配新输出 | ~45 | 30min |
| 11 | 集成测试 | — | 1.5h |
| **总计** | | **~480 行** | **~11h** |

### 不改动的文件

- `pipeline_configs.py` — 注册表不变，四个 builder 函数签名不变
- `analysis_graph.py` — 舆情线不动
- `analysis_graph_briefing.py` — 简报线不动
- `scheduler.py` 主逻辑 — 只加写快照的行
- `prompt_templates.py` Screener Prompt — Screener 过滤逻辑不变
