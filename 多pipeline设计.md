# 多 Pipeline 架构扩展设计

> 目标：在现有 RadarPipeline 骨架基础上，扩展出攻略、追星、综合简报三条独立流水线。
> 原则：舆情线不改一行，新线复用骨架，仅注入不同的配置和分析子图。

**实施状态：已全部完成（2026-06-16）。**

| 文件 | 状态 | 说明 |
|------|------|------|
| `pipeline.py` | ✅ | ScreenerStage/AnalysisSubGraph 配置化，4 个 mode 分支，4 个新 result builders |
| `schemas.py` | ✅ | 新增 GuideScreenerResult / CelebrityScreenerResult / BriefingScreenerResult |
| `prompt_templates.py` | ✅ | 新增 GUIDE/CELEBRITY/BRIEFING_SCREENER_PROMPT |
| `analysis_graph_guide.py` | ✅ | 新文件：extractor → comparer → summarizer |
| `analysis_graph_celebrity.py` | ✅ | 新文件：sentiment → heat → aggregator |
| `analysis_graph_briefing.py` | ✅ | 新文件：categorizer → highlighter → writer |
| `pipeline_configs.py` | ✅ | 新文件：4 个 builder + PIPELINE_BUILDERS 注册表 |
| `config.py` | ✅ | 新增 GUIDE/CELEBRITY/BRIEFING_MODEL + resolve_model() |
| `subscription_db.py` | ✅ | 新增 pipeline_types 字段 |
| `db_init.py` | ✅ | 新增 3 张结果表（guide_reports/celebrity_reports/daily_briefings） |
| `scheduler.py` | ✅ | 按 pipeline_types 分发，新增 _run_extra_pipelines |
| Agent tools (3 文件) | ✅ | guide/celebrity/briefing 查询工具 |
| `topic_aggregator.py` | ⬜ | 非风险线走独立结果表，不涉及 topic_summary |

## 一、现状复盘

### 1.1 现有架构（已稳定运行）

```
RadarPipeline(config: PipelineConfig)
  __init__:
    self.screener = ScreenerStage(config.keywords, config.keyword_levels)
    self.vision   = VisionStage()
    self.cluster  = ClusterStage()
    self.analysis = AnalysisSubGraph()    ← 硬编码 analyze_and_report
    self.aggregator = TopicAggregator()

  _run_inner(posts, background_tasks):
    screener_result = self.screener.run(posts)       # Stage 1: 文本初筛
    vision_passed   = self.vision.run(needs_vision)  # Stage 2: 视觉复判（仅 full）
    clusters        = self.cluster.run(final_screened) # Stage 3: 向量聚类
    analysis_outputs = asyncio.gather(                 # Stage 4: LangGraph 分析
        [self._run_with_semaphore(c) for c in clusters]
    )
    final_results, alerts = 收集结果 + 批量预警        # Stage 5: 输出
    self.aggregator.aggregate_clusters(...)           # 话题聚合写 SQLite
    return final_results
```

关键点：
- **ScreenerStage** 用 `SCREENER_PROMPT`（模块级 import）、`ScreenerResult`（Pydantic schema）、`call_llm`（engine="deepseek"）——全硬编码
- **AnalysisSubGraph** 调用 `analysis_graph.py` 的 `analyze_and_report()`——三节点（analyst/reviewer/director），双模型（DeepSeek/Kimi），风险判定
- **PipelineResult** 字段是 `risk_level/core_issue/report/sentiment`——风险特化
- **TopicAggregator** 写入 `topic_summary` 表，字段含 `risk_level/risk_class`——风险特化

### 1.2 已存在的 mode 系统

```python
@dataclass
class PipelineConfig:
    keywords: List[str]
    keyword_levels: dict
    platform: str
    mode: str = "trending"   # full / trending / fan_track / quick_search
    alert_negative: bool = True
    timeout: int = 300
    concurrent_limit: int = 2
    screener_concurrency: int = 10
    vision_concurrency: int = 5
    owner_id: Optional[str] = None
    persist: bool = True
    max_per_platform: int = 0
    push_mode: str = "every"   # every / important / silent
```

`_run_inner` 中根据 `mode` 走不同分支——这已经是一个多模式架构。本次扩展不推翻它，而是新增 `mode` 值并加对应分支，同时将硬编码的 Prompt/Graph 改为可配置。

---

## 二、核心设计：配置驱动，骨架不变

### 2.1 改造范围

| 组件 | 当前状态 | 改动 |
|------|---------|------|
| `PipelineConfig` | mode + 风险特化字段 | 加 `screener_prompt`、`screener_schema`、`analysis_graph`、`result_builder` 四个字段 |
| `ScreenerStage` | 硬编码 `SCREENER_PROMPT` + `ScreenerResult` | Prompt 和 schema 从 config 传入 |
| `AnalysisSubGraph` | 硬编码 `analyze_and_report()` | 接受 `analysis_callable` 注入 |
| `_run_inner` | mode 分支 for risk 模式 | 新增 guide/celebrity/briefing 分支 |
| `PipelineResult` | 风险字段 | 不变，新线用新的 result dataclass |
| `TopicAggregator` | 风险数据 | 新线用新的 aggregator |
| `scheduler.py` | 只调度 risk 扫描 | 按 subscription.pipeline_types 分发不同 pipeline |
| `subscription` 表 | 无 pipeline 区分 | 加 `pipeline_types` 字段 |

### 2.2 PipelineConfig 改动

```python
@dataclass
class PipelineConfig:
    # ── 现有字段不改 ──
    keywords: List[str]
    keyword_levels: dict
    platform: str
    alert_negative: bool = True
    timeout: int = 300
    concurrent_limit: int = 2
    screener_concurrency: int = 10
    vision_concurrency: int = 5
    owner_id: Optional[str] = None
    mode: str = "full"
    persist: bool = True
    max_per_platform: int = 0
    push_mode: str = "every"

    # ── 新增：可配置的 Screener 参数 ──
    screener_prompt: str = ""          # 空 = 回退到默认 SCREENER_PROMPT
    screener_pydantic_model: type = None  # 空 = 回退到 ScreenerResult

    # ── 新增：可配置的分析子图 ──
    analysis_callable: Callable = None  # 空 = 回退到 analyze_and_report

    # ── 新增：结果构建器 ──
    result_builder: Callable = None     # 空 = 回退到 build_results
    output_handler: Callable = None     # 新线定制输出（攻略报告/追星仪表盘/简报）
```

### 2.3 ScreenerStage 改造（关键：Prompt 配置化）

当前代码（`pipeline.py` L109-112）：

```python
class ScreenerStage:
    SCREENER_CONCURRENCY = 10

    def __init__(self, keywords: List[str], keyword_levels: dict):
        self.keywords = keywords
        self.keyword_levels = keyword_levels
        self._screener_semaphore = asyncio.Semaphore(self.SCREENER_CONCURRENCY)

    def _build_prompt(self, keyword: str) -> str:
        kw_with_level = f"{keyword}(监控等级:{self.keyword_levels.get(keyword, 'balanced')})"
        return SCREENER_PROMPT.format(keyword=kw_with_level)
```

改造后（最小改动，向后兼容）：

```python
class ScreenerStage:
    SCREENER_CONCURRENCY = 10

    def __init__(self, keywords: List[str], keyword_levels: dict,
                 prompt: str = "", pydantic_model=None):
        self.keywords = keywords
        self.keyword_levels = keyword_levels
        self._screener_semaphore = asyncio.Semaphore(self.SCREENER_CONCURRENCY)
        # 新：支持外部注入，不配则回退到默认
        self._prompt_template = prompt if prompt else SCREENER_PROMPT
        self._pydantic_model = pydantic_model if pydantic_model else ScreenerResult

    def _build_prompt(self, keyword: str) -> str:
        kw_with_level = f"{keyword}(监控等级:{self.keyword_levels.get(keyword, 'balanced')})"
        return self._prompt_template.format(keyword=kw_with_level)

    async def _screener_single(self, post, screener_prompt, keyword):
        # ...
        res = await asyncio.to_thread(
            call_llm,
            screener_prompt, text_to_analyze,
            response_format="json", engine="deepseek",
            pydantic_model=self._pydantic_model   # ← 改这里
        )
```

Pipeline 构造时传入：

```python
# 舆情线（不改，默认行为）
self.screener = ScreenerStage(config.keywords, config.keyword_levels)

# 攻略线（注入攻略 Prompt + 攻略 Schema）
self.screener = ScreenerStage(
    config.keywords, config.keyword_levels,
    prompt=GUIDE_SCREENER_PROMPT,
    pydantic_model=GuideScreenerResult,
)
```

### 2.4 AnalysisSubGraph 改造（关键：分析子图注入）

当前代码（`pipeline.py` L430-512）：

```python
class AnalysisSubGraph:
    def run(self, cluster: Cluster) -> tuple[Cluster, dict, dict]:
        combined_text = ...
        mock_post = {"title": ..., "content": combined_text[:2500]}
        result = analyze_and_report(mock_post, ...)  # ← 硬编码
        return cluster, result, evolution_timeline
```

改造后：

```python
class AnalysisSubGraph:
    def __init__(self, analysis_callable=None):
        # 不配则回退到默认风险分析
        self._analyze = analysis_callable if analysis_callable else analyze_and_report

    def run(self, cluster: Cluster) -> tuple[Cluster, dict, dict]:
        combined_text = ...
        mock_post = {"title": ..., "content": combined_text[:2500]}
        result = self._analyze(mock_post=mock_post, keyword=cluster.keyword,
                               sensitivity=cluster.sensitivity, evolution_timeline={})
        return cluster, result, evolution_timeline
```

Pipeline 构造时注入：

```python
# 舆情线
self.analysis = AnalysisSubGraph()  # 默认 analyze_and_report

# 攻略线
self.analysis = AnalysisSubGraph(analysis_callable=analyze_guide)

# 追星线
self.analysis = AnalysisSubGraph(analysis_callable=analyze_celebrity)
```

### 2.5 _run_inner 中的 mode 分支

现有代码（`pipeline.py` L692-737）已有 mode 分支：

```python
if self.config.mode == "quick_search":
    return self._to_search_results(screener_result.passed)
if self.config.mode == "fan_track":
    return self._sort_by_time(screener_result.passed)
# ...
if self.config.mode == "trending":
    return self._sort_by_heat(clusters)
# 以下仅 full mode
```

新增三条线的处理——与 `full` 模式共享 Stage 1-3（Screener→Vision→Cluster），Stage 4 已由注入的 `analysis_callable` 处理，Stage 5（输出）走向不同分支。实际上 analysis_callable 不同 + result_builder 不同 + 不推预警，即可覆盖新线：

```python
# _run_inner 中，analysis 阶段之前的行为完全复用（Screener→Vision→Cluster）

# Stage 4: 分析（可配置子图，all modes except quick_search/fan_track/trending）
if self.config.mode in ("full", "guide", "celebrity", "briefing"):
    tasks = [self._run_with_semaphore(c) for c in clusters]
    analysis_outputs = await asyncio.gather(*tasks, return_exceptions=True)

# Stage 5: 根据 mode 走不同结果收集
if self.config.mode == "full":
    # 现有风险收集 + 预警逻辑，不动
    ...
elif self.config.mode == "guide":
    final_results = self._build_guide_results(analysis_outputs)
elif self.config.mode == "celebrity":
    final_results = self._build_celebrity_results(analysis_outputs)
elif self.config.mode == "briefing":
    final_results = self._build_briefing_results(analysis_outputs)
```

新结果构建方法（与现有 `build_results` 对齐风格）：

```python
def _build_guide_results(self, analysis_outputs) -> List[GuideResult]:
    """攻略线结果收集（仿 build_results 的写法）"""
    results = []
    for item in analysis_outputs:
        if isinstance(item, Exception):
            continue
        cluster, guide_data, _ = item
        results.append(GuideResult(
            topic=cluster.topic_name,
            keyword=cluster.keyword,
            summary=guide_data.get("summary", ""),
            consensus=guide_data.get("consensus", []),
            controversial=guide_data.get("controversial", []),
            tips=guide_data.get("tips", []),
            source_breakdown=guide_data.get("sources", {}),
            post_count=len(cluster.posts),
        ))
    return results

def _build_celebrity_results(self, analysis_outputs) -> List[CelebrityResult]:
    """追星线结果收集"""
    ...

def _build_briefing_results(self, analysis_outputs) -> List[BriefingResult]:
    """简报线结果收集"""
    ...
```

---

## 三、四条流水线定义

### 3.1 舆情线（mode="full"，现有，不改）

| 维度 | 值 |
|------|-----|
| mode | `full` |
| screener_prompt | SCREENER_PROMPT（默认，不注入） |
| screener_model | ScreenerResult（默认） |
| analysis_callable | analyze_and_report（默认） |
| result_builder | build_results（默认） |
| output | send_batch_alert |
| pipeline_type | `risk` |

`_run_inner` 中 mode="full" 的逻辑一行不改。

### 3.2 攻略线（mode="guide"，新增）

| 维度 | 值 |
|------|-----|
| mode | `guide` |
| screener_prompt | GUIDE_SCREENER_PROMPT（新增文件 `prompt_templates.py`） |
| screener_model | GuideScreenerResult（新增 Pydantic model） |
| analysis_callable | analyze_guide（新增 `analysis_graph_guide.py` 的入口函数） |
| result_builder | _build_guide_results |
| output | 无预警——结果写入 `guide_reports` 表，Agent 查询工具读取 |
| pipeline_type | `guide` |

**GUIDE_SCREENER_PROMPT 设计要点**（在 `prompt_templates.py` 中新增）：

```
你是一个攻略与体验信息筛选专家。
目标：【{keyword}】
任务：判断内容是否为攻略/种草/踩坑/体验分享类有效信息。

【保留的信息类型】
1. 攻略型：旅游路线、餐饮推荐、购物心得、装修经验、学习路径
2. 体验型：探店评价、产品实测、服务体验分享
3. 对比型：多选项分析对比（如"三亚vs海口怎么选"）

【必须排除的噪音】
1. 纯广告/营销软文（无真实体验细节）
2. 个人情绪吐槽（无实质内容）
3. 纯图片无文字说明

输出 JSON：
{{
  "generated_title": "标准化标题（20字内）",
  "info_type": "guide|review|comparison|experience",
  "topic": "核心主题（如长沙旅游、AirPods实测）",
  "sentiment": "positive|negative|mixed",
  "key_points": ["关键信息点1", "关键信息点2"],
  "usefulness": 1-5,
  "is_relevant": true/false,
  "needs_vision": true/false
}}
```

**GuideAnalysisGraph**（新增 `analysis_graph_guide.py`）：

三节点：extractor → comparer → summarizer，单模型（DeepSeek），无交叉验证。

```python
# analysis_graph_guide.py

def extractor_node(state):
    """从每条帖子提取结构化信息"""
    ...

def comparer_node(state):
    """跨来源对比——不同作者对同一地点/产品的评价一致性"""
    ...

def summarizer_node(state):
    """合并为结构化攻略报告"""
    ...

# 编译
guide_workflow = StateGraph(GuideGraphState)
guide_workflow.add_node("extractor", extractor_node)
guide_workflow.add_node("comparer", comparer_node)
guide_workflow.add_node("summarizer", summarizer_node)
guide_workflow.set_entry_point("extractor")
guide_workflow.add_edge("extractor", "comparer")
guide_workflow.add_edge("comparer", "summarizer")
guide_workflow.add_edge("summarizer", END)
guide_app = guide_workflow.compile()


def analyze_guide(mock_post, keyword, sensitivity="balanced", evolution_timeline=None):
    """对外接口，签名与 analyze_and_report 一致"""
    initial_state = {..., "keyword": keyword}
    return guide_app.invoke(initial_state)
```

输出结构：
```json
{
  "summary": "综合 47 篇攻略的汇总建议",
  "consensus": ["必去：橘子洲", "推荐：茶颜悦色"],
  "controversial": ["文和友：评价两极分化"],
  "tips": ["避开周末", "地铁最便捷"],
  "sources": {"小红书": 23, "知乎": 12, "B站": 8}
}
```

### 3.3 追星线（mode="celebrity"，新增）

| 维度 | 值 |
|------|-----|
| mode | `celebrity` |
| screener_prompt | CELEBRITY_SCREENER_PROMPT |
| screener_model | CelebrityScreenerResult |
| analysis_callable | analyze_celebrity（`analysis_graph_celebrity.py`） |
| result_builder | _build_celebrity_results |
| output | 无预警——写入 `celebrity_reports` 表 |
| pipeline_type | `celebrity` |

**CelebrityAnalysisGraph**：三节点（sentiment → heat → aggregator），单模型。

输出结构：
```json
{
  "celebrity": "某明星",
  "total_posts": 328,
  "sentiment_distribution": {"positive": 0.62, "negative": 0.08, "neutral": 0.30},
  "heat_trend": "rising",
  "hot_topics": ["新剧开播讨论"],
  "cross_platform": {
    "wb": {"count": 201, "focus": "粉丝控评"},
    "xhs": {"count": 89, "focus": "穿搭同款"},
    "bili": {"count": 38, "focus": "剪辑二创"}
  }
}
```

### 3.4 综合简报线（mode="briefing"，新增）

| 维度 | 值 |
|------|-----|
| mode | `briefing` |
| screener_prompt | BRIEFING_SCREENER_PROMPT（全量保留，只打标签） |
| screener_model | BriefingScreenerResult |
| analysis_callable | analyze_briefing（`analysis_graph_briefing.py`） |
| result_builder | _build_briefing_results |
| output | 无预警——写入 `daily_briefings` 表 |
| pipeline_type | `briefing` |

**BriefingAnalysisGraph**：三节点（categorizer → highlighter → writer），单模型。

---

## 四、Screener 各线关注点对比

| 线 | is_relevant 条件 | 丢弃条件 |
|----|-----------------|---------|
| 风险 | 含负面指控、质量投诉、危机信号 | 日常打卡、玩笑、纯广告 |
| 攻略 | 含体验分享、对比评测、具体建议 | 纯广告、情绪吐槽、无实质内容 |
| 追星 | 明星相关动态、作品讨论、争议 | 完全不相关的内容 |
| 简报 | 全量判定 is_relevant=true | 几乎不丢（全收） |

所有线共享 `needs_vision` 机制（文本存疑时申请看图），共享 VisionStage。

---

## 五、新增数据结构

### 5.1 新 Result dataclass

```python
@dataclass
class GuideResult:
    topic: str
    keyword: str
    summary: str
    consensus: List[str]
    controversial: List[str]
    tips: List[str]
    source_breakdown: dict      # {platform: count}
    post_count: int
    # DB 写入字段
    topic_id: str = ""

@dataclass
class CelebrityResult:
    celebrity: str
    keyword: str
    total_posts: int
    sentiment_distribution: dict
    heat_trend: str
    hot_topics: List[str]
    cross_platform: dict
    topic_id: str = ""

@dataclass
class BriefingResult:
    date: str
    domain: str
    highlight: str
    post_count: int
    sentiment: str
    topic_id: str = ""
```

### 5.2 新 Pydantic Schema（Screener 用）

```python
from pydantic import BaseModel
from typing import List, Optional

class GuideScreenerResult(BaseModel):
    generated_title: str = ""
    info_type: str = "guide"        # guide/review/comparison/experience
    topic: str = ""
    sentiment: str = "neutral"      # positive/negative/mixed
    key_points: List[str] = []
    usefulness: int = 1
    is_relevant: bool = False
    needs_vision: bool = False
    matched_keyword: str = ""
    reason: str = ""

class CelebrityScreenerResult(BaseModel):
    generated_title: str = ""
    celebrity_name: str = ""
    event_type: str = ""            # release/event/discussion/controversy/endorsement
    sentiment: str = "neutral"
    heat_score: int = 1
    is_relevant: bool = False
    needs_vision: bool = False
    matched_keyword: str = ""
    reason: str = ""

class BriefingScreenerResult(BaseModel):
    generated_title: str = ""
    info_type: str = ""             # tech/entertainment/travel/finance/other
    domain: str = ""
    sentiment: str = "neutral"
    abstract: str = ""              # 20 字摘要
    is_relevant: bool = True        # 简报线默认全收
    needs_vision: bool = False
    matched_keyword: str = ""
    reason: str = ""
```

---

## 六、调度器改造

### 6.1 订阅表改动

```sql
ALTER TABLE subscription ADD COLUMN pipeline_types TEXT DEFAULT '["risk"]';
```

存量数据默认 `["risk"]`，向后兼容。

### 6.2 调度器分发

现有 scheduler 从 subscription 表读取关键词，遍历用户跑 `job_async()`。改造为按 `pipeline_type` 区分 Pipeline 实例：

```python
# scheduler.py

from .pipeline import RadarPipeline, PipelineConfig, build_results
from .pipeline_configs import PIPELINE_BUILDERS  # 新增：pipeline 工厂注册表

def _run_scan():
    """定时扫描：按 subscription.pipeline_types 分发不同 pipeline"""
    # ...
    user_subscriptions = _collect_user_subscriptions()
    # 现在 _collect 也返回 pipeline_types：
    # {owner_id: [(keyword, platforms, pipeline_types), ...]}

    for oid, subs in user_subscriptions.items():
        for keyword, platforms, pipeline_types in subs:
            for pt in pipeline_types:
                if pt not in PIPELINE_BUILDERS:
                    continue
                pipeline = PIPELINE_BUILDERS[pt](keyword, platforms, oid)
                # 不同 pipeline_type 用不同调度间隔：
                # risk → scan_interval（现有逻辑）
                # guide → 默认 480min（早晚各一次）
                # celebrity → 默认 120min
                # briefing → 默认 1440min（每天一次）
                if _should_run_pipeline(oid, pt):
                    await pipeline.run(raw_posts)
```

### 6.3 Pipeline 工厂注册表

```python
# pipeline_configs.py（新增文件）

def build_risk_pipeline(keyword: str, platforms: List[str], owner_id: str) -> RadarPipeline:
    return RadarPipeline(PipelineConfig(
        keywords=[keyword],
        keyword_levels={keyword: "balanced"},
        platform=platforms[0] if platforms else "wb",
        mode="full",
        owner_id=owner_id,
        alert_negative=True,
        push_mode="every",
        # 以下不传 = 默认 risk 行为
    ))

def build_guide_pipeline(keyword: str, platforms: List[str], owner_id: str) -> RadarPipeline:
    return RadarPipeline(PipelineConfig(
        keywords=[keyword],
        keyword_levels={keyword: "balanced"},
        platform=platforms[0] if platforms else "wb",
        mode="guide",
        owner_id=owner_id,
        screener_prompt=GUIDE_SCREENER_PROMPT,          # ← 注入
        screener_pydantic_model=GuideScreenerResult,     # ← 注入
        analysis_callable=analyze_guide,                 # ← 注入
        result_builder=_build_guide_results,             # ← 注入
    ))

# 同理 build_celebrity_pipeline / build_briefing_pipeline

PIPELINE_BUILDERS = {
    "risk":     build_risk_pipeline,
    "guide":    build_guide_pipeline,
    "celebrity": build_celebrity_pipeline,
    "briefing": build_briefing_pipeline,
}
```

---

## 七、模型配置方案（Pipeline 级 + 节点级覆盖）

详见设计文档第五节。简要：每条线一个默认模型（`RISK_MODEL` / `GUIDE_MODEL` / `CELEBRITY_MODEL` / `BRIEFING_MODEL`），从 `DEFAULT_MODEL` 回退。节点级可覆盖（如 risk/reviewer → Kimi），新线不需要节点覆盖。

### 7.1 配置解析函数

```python
def resolve_model(pipeline_id: str, node: str = "") -> str:
    """优先级：节点覆盖 > Pipeline 默认 > 全局 DEFAULT"""
    settings = Settings()
    node_env = NODE_OVERRIDES.get(f"{pipeline_id}/{node}")
    if node_env:
        val = getattr(settings, node_env, "")
        if val:
            return val
    pipeline_model = getattr(settings, f"{pipeline_id.upper()}_MODEL", "")
    return pipeline_model or settings.DEFAULT_MODEL
```

### 7.2 与现有 config.py 的整合

```python
class Settings:
    # 现有
    DEFAULT_MODEL = "deepseek-chat"
    ANALYST_MODEL = os.getenv("ANALYST_MODEL") or DEFAULT_MODEL   # → risk/analyst
    REVIEWER_MODEL = os.getenv("REVIEWER_MODEL") or DEFAULT_MODEL # → risk/reviewer

    # 新增：Pipeline 级
    RISK_MODEL = os.getenv("RISK_MODEL") or DEFAULT_MODEL
    GUIDE_MODEL = os.getenv("GUIDE_MODEL") or DEFAULT_MODEL
    CELEBRITY_MODEL = os.getenv("CELEBRITY_MODEL") or DEFAULT_MODEL
    BRIEFING_MODEL = os.getenv("BRIEFING_MODEL") or DEFAULT_MODEL
```

存量 API Key 环境变量（`ANALYST_API_KEY` 等）不变，新线回退到 `DEFAULT_API_KEY`。

---

## 八、改动文件清单

```
backend/services/radar_service/
├── pipeline.py                  # 改：ScreenerStage/AnalysisSubGraph 配置化
│                                    PipelineConfig 加 4 字段
│                                    _run_inner 加 3 个 mode 分支
│                                    新增 _build_guide/celebrity/briefing_results
├── pipeline_configs.py          # 新：4 个 builder + PIPELINE_BUILDERS 注册表
├── prompt_templates.py          # 改：加 GUIDE/CELEBRITY/BRIEFING_SCREENER_PROMPT
├── schemas.py                   # 改：加 Guide/Celebrity/Briefing ScreenerResult
├── analysis_graph.py            # 不改
├── analysis_graph_guide.py      # 新：GuideAnalysisGraph + analyze_guide()
├── analysis_graph_celebrity.py  # 新：CelebrityAnalysisGraph + analyze_celebrity()
├── analysis_graph_briefing.py   # 新：BriefingAnalysisGraph + analyze_briefing()
├── topic_aggregator.py          # 改：支持 guide/celebrity/briefing 聚合写入
├── scheduler.py                 # 改：按 pipeline_types 分发
└── db/
    └── db_topic.py              # 改：新增 guide_reports/celebrity_reports 表写入

backend/core/
└── config.py                    # 改：加 GUIDE_MODEL / CELEBRITY_MODEL / BRIEFING_MODEL
                                   + NODE_OVERRIDES 表 + resolve_model()

backend/services/agent_service/tools/
├── guide.py                     # 新：get_guide 工具
├── celebrity.py                 # 新：track_celebrity 工具
└── briefing.py                  # 新：get_briefing 工具

数据层：
└── subscription 表 ALTER COLUMN pipeline_types
```

---

## 九、关键代码改动量

| 文件 | 操作 | 行数 |
|------|------|------|
| `pipeline.py` | ScreenerStage/AnalysisSubGraph 配置化 + 3 mode 分支 | ~60 |
| `pipeline_configs.py` | 新文件 | ~80 |
| `prompt_templates.py` | 加 3 个 Screener Prompt | ~120 |
| `schemas.py` | 加 3 个 Pydantic model | ~40 |
| `analysis_graph_guide.py` | 新文件 | ~120 |
| `analysis_graph_celebrity.py` | 新文件 | ~120 |
| `analysis_graph_briefing.py` | 新文件 | ~100 |
| `topic_aggregator.py` | 加 3 个聚合方法 | ~60 |
| `scheduler.py` | pipeline 分发逻辑 | ~40 |
| `db/db_topic.py` | 新表写入 | ~30 |
| `config.py` | 加 model 配置 | ~25 |
| Agent 工具（3 文件） | 查询工具 | ~50 |
| **总计** | | **~850 行** |

**舆情线改动量**：~15 行（ScreenerStage 和 AnalysisSubGraph 加可选参数，默认行为不变）。

---

## 十、与原有 mode 系统的关系

现有的 `mode`（full/trending/fan_track/quick_search）和新的 `pipeline_type`（risk/guide/celebrity/briefing）是正交的：

| 维度 | mode | pipeline_type |
|------|------|-------------|
| 控制什么 | 同一条线的运行深度 | 不同业务线的分析方向 |
| 举例 | risk 线可以 full（含分析）或 trending（热度排序不分析） | guide 线定义一个完全不同的分析目标 |
| 实现 | `_run_inner` 中的 if/else | 不同的 PipelineConfig 注入 + 不同的分析子图 |

两者可以组合：`pipeline_type="guide"` + `mode="full"`（攻略线完整跑），`pipeline_type="guide"` + `mode="trending"`（攻略线只看热度，不分析）。但初期建议新线只用 full 模式，trending/fan_track 暂时不加。
