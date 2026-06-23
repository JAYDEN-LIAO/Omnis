# 已知问题

## P1. 上下文重建的竞态窗口

**问题**：`_write_memory_async` 是异步后台任务，`phase_build_context` 从 DB 重建历史时可能读到落后一轮的数据。

**触发条件**：用户在当前轮次 stream 结束后很快（< 1-2s）发送下一条消息，此时上一轮的 `_write_memory_async` 还未完成 `replace_messages`，`get_messages` 返回的是上上轮的数据，导致最新一轮的对话内容从 LLM 上下文中丢失。

**原因**：`chat_messages` 写入和 LLM 抽取在同一个异步任务里串行执行，消息表不是即时更新的。

**当前缓解**：
- `_write_memory_async` 中已将 `replace_messages` 移到 LLM 抽取之前（SQLite 写入优先，约 <10ms）
- 无摘要时回退到尾消息重建

**理想修复**（未实现）：`replace_messages` 应在 stream 结束时同步写入（而非异步），或者使用版本号机制检测数据陈旧程度。

---

## P2. 尾巴消息数硬编码

**问题**：`phase_build_context` 从 `chat_messages` 取最近 N 条作为上下文尾巴，目前 N=6 是硬编码。

**影响**：
- 短场景（单轮问答）够用
- 长场景（多工具调用、多轮 Agent 推理）可能截断关键上下文

**当前状态**：结构约束 + 摘要兜底，6 条在绝大多数场景下够用。

**理想修复**（未实现）：根据 `ctx.current_messages` 实际 token 占用动态调整 N，或根据工具调用链长度自适应。

---

## P3. God 文件问题（4 个文件 > 900 行）

### 问题

`backend/services/radar_service/` 下有 4 个文件超过 900 行，每个文件承担了多种不同的职责，违反了单一职责原则：

| 文件 | 行数 | 混在一起的职责 |
|------|------|---------------|
| `api.py` | 1090 | HTTP 路由定义 + SQL 查询 + 业务逻辑（LLM调用、风险分类、情感分析） |
| `db_manager.py` | 1043 | 40+ 个 CRUD 函数扁平堆叠，无分层（ai_results / topic_summary / push_settings / audit_log 全混在一起） |
| `push_generator.py` | 1195 | Python 逻辑 + 4 个 HTML 模板硬编码（800 行 HTML 字符串） |
| `pipeline.py` | 934 | 5 个 Pipeline 阶段（Screener / Vision / Cluster / Analysis / Alert）全塞一个文件 |

### 影响

1. **改动风险高**：改 `api.py` 里一个 SQL 查询可能不小心改了路由参数，反之亦然
2. **代码审查困难**：1000 行的文件很难理解完整的逻辑流，reviewer 容易遗漏边界情况
3. **无测试可写**：对于 1000 行的单一巨石，单元测试在技术上不可行
4. **团队协作瓶颈**：两个人不能同时在同一个 God 文件上工作
5. **HTML 模板维护困难**：改一个 CSS 颜色需要在 Python 源码里翻几百行找到对应字符串

### 根因

项目早期快速迭代，没有做模块分层。功能不断往已有文件里追加，缺乏定期拆分。

### 解决方案

#### P3.1 `api.py`：路由 / 业务 / 数据三层分离

```
重构前（1 文件 1090 行）：
  api.py → 路由 + SQL + 业务逻辑

重构后（5 文件）：
  api/
  ├── __init__.py          # router 注册
  ├── routes_radar.py      # /api/radar_status, /api/start_task, /api/yq_list
  ├── routes_settings.py   # /api/settings, /api/scheduler/*, /api/circuit/*
  ├── routes_topic.py      # /api/topic_*, /api/topic_evolution/*
  └── routes_rss.py        # /rss/{token}.xml
```

SQL 查询从路由函数中抽离到 `db_manager.py` 对应模块（如 `db_topic.py`），业务逻辑抽到 `services/` 层。

#### P3.2 `db_manager.py`：按数据域拆分

```
重构前（1 文件 1043 行）：
  db_manager.py → 所有 CRUD

重构后（6 文件）：
  db/
  ├── __init__.py
  ├── db_ai_results.py     # ai_results 表 CRUD
  ├── db_topic.py          # topic_summary + topic_posts
  ├── db_settings.py       # system_settings
  ├── db_push.py           # push_settings
  ├── db_audit.py          # audit_log
  └── db_model.py          # model_config
```

#### P3.3 `push_generator.py`：HTML 模板抽离

```
重构前（1 文件 1195 行）：
  push_generator.py → Python 逻辑 + HTML 模板

重构后（6 文件）：
  push_generator.py        # 仅保留数据准备和模板渲染逻辑（~400 行）
  templates/
  ├── push_alert.html      # PUSH_HTML_TEMPLATE（单条预警）
  ├── batch_alert.html     # BATCH_PUSH_HTML_TEMPLATE（批量预警）
  ├── daily_summary.html   # DAILY_SUMMARY_TEMPLATE（每日简报）
  └── topic_push.html      # TOPIC_PUSH_HTML_TEMPLATE（话题推送）
```

使用 `importlib.resources` 或直接 `open()` 读取模板文件，保留 `.format()` 变量替换逻辑。

#### P3.4 `pipeline.py`：按阶段拆分

```
重构前（1 文件 934 行）：
  pipeline.py → 5 个阶段全在一起

重构后（7 文件）：
  pipeline/
  ├── __init__.py             # RadarPipeline 调度器入口
  ├── stage_screener.py       # ① ScreenerStage
  ├── stage_vision.py         # ② VisionStage
  ├── stage_cluster.py        # ③ ClusterStage
  ├── stage_analysis.py       # ④ LangGraph 分析子图调度
  ├── stage_alert.py          # ⑤ 预警 + 聚合写入
  └── pipeline_config.py      # PipelineConfig + PipelineResult 数据结构
```

### 实施要求

1. **必须分批进行**：一个文件拆完后验证启动 + smoke test 通过再拆下一个
2. **保持 git 历史可追溯**：使用 `git mv` 拆分文件，不要删了重建
3. **优先拆 `push_generator.py`**：HTML 抽离风险最低（纯模板字符串移动），收益最大（前后端分离）
4. **最后拆 `pipeline.py`**：Pipeline 阶段之间依赖最复杂，需要先摸清跨阶段数据流

---

## P4. `sys.path.append` 滥用问题（15 处）

### 问题

`backend/` 下有 15 个文件通过运行时 `sys.path.append(BASE_DIR)` 来 hack 导入路径：

| 分布 | 数量 | 文件 |
|------|------|------|
| `radar_service/` | 8 | `db_manager.py`, `main.py`, `pipeline.py`, `topic_aggregator.py`, `vector_store.py`, `topic_tracker.py`, `notifier/channel_rss.py`, `llm_gateway.py` |
| `search_lib/` | 2 | `filter.py`, `crawler_adapter.py` |
| `gateway/` | 1 | `main.py` |
| `crawler_service/` | 4 | `database/db.py:30`, `tests/conftest.py:29`, `tools/utils.py:32`, `test/test_mongodb_integration.py:25` |

典型代码：

```python
# pipeline.py 开头
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)
```

### 影响

1. **导入顺序依赖**：A 文件先执行才加路径，B 文件后执行依赖 A 的 hack。如果执行顺序变化 → `ImportError`
2. **重复模块实例化**：同一模块被两个不同路径导入时，Python 认为是两个独立模块，各自初始化一次。你们的 `global_http_client`（模块级 `httpx.Client()`）如果被重复导入，会产生两个 TCP 连接池
3. **IDE / 静态分析全部失效**：PyCharm / VSCode 的"跳转到定义"、"重命名符号"、"自动补全"都依赖静态分析导入关系。`sys.path.append` 是运行时行为，静态分析看不到 → 重构时没有工具辅助，纯靠记忆
4. **安全扫描盲区**：`pip-audit`、`safety` 等依赖扫描工具也无法分析这种非标导入

### 根因

之前 `backend/core/` 和 `backend/services/` 不是合法 Python 包（缺 `__init__.py`），所以无法用标准的 `from core.xxx import yyy`。只能用 `sys.path.append(BASE_DIR)` 把 `backend/` 目录加入搜索路径，然后 `from core.xxx import yyy` 才能工作。

**现在 `__init__.py` 已创建**（P0 修复轮次），这三个目录已经是合法包了，消除 `sys.path.append` 的前提条件已满足。

### 解决方案

#### 步骤 1：确认包边界

当前物理结构已经是合法包：
```
backend/
├── __init__.py                    # 空文件，标记为包
├── core/
│   ├── __init__.py                # ✅ 已存在
│   ├── config.py
│   ├── database.py
│   └── ...
├── services/
│   ├── __init__.py                # ✅ 已存在
│   ├── radar_service/
│   │   ├── __init__.py            # ✅ 已存在
│   │   ├── api.py
│   │   └── ...
│   └── agent_service/
│       └── ...
└── gateway/
    └── main.py
```

#### 步骤 2：将 `backend/` 父目录加入 PYTHONPATH

修改启动入口 `backend/gateway/main.py`：

```python
# 替换当前的 sys.path hack（第 24-27 行）
# Before:
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# After:
# 标准做法：将 backend/ 父目录加入 PYTHONPATH
# 这样 from backend.core.config import settings 就是标准包导入
_BACKEND_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_PARENT not in sys.path:
    sys.path.insert(0, _BACKEND_PARENT)
```

这一步改动最小——只改 `gateway/main.py` 一处，其他 14 个文件后续逐一清理。

#### 步骤 3：逐模块替换导入语句

**当前（hack 模式）**：
```python
# db_manager.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)
from core.database import get_db_connection
from core.logger import get_logger
```

**目标（标准包导入）**：
```python
# db_manager.py
from backend.core.database import get_db_connection
from backend.core.logger import get_logger
```

不再需要 `sys.path.append`，因为 `backend/` 的父目录已在 PYTHONPATH 中。

#### 步骤 4：清理顺序（按依赖从底层到上层）

```
1. backend/core/database.py       ← 最底层，被最多模块引用
2. backend/core/logger.py         ← 同样底层
3. backend/services/search_lib/   ← 被 radar_service 引用
4. backend/services/radar_service/db_manager.py
5. backend/services/radar_service/vector_store.py
6. backend/services/radar_service/topic_tracker.py
7. backend/services/radar_service/topic_aggregator.py
8. backend/services/radar_service/pipeline.py
9. backend/services/radar_service/main.py
10. backend/services/radar_service/llm_gateway.py
11. backend/services/radar_service/notifier/channel_rss.py
12. backend/services/radar_service/api.py
13. backend/services/crawler_service/ 各文件（独立子系统，最后处理）
```

### 风险与缓解

| 风险 | 缓解 |
|------|------|
| 改了导入路径但某处仍用旧路径 → `ImportError` | smoke_test.py 一键验证所有关键端点 |
| `from backend.xxx` 和 `from .xxx` 混用导致循环导入 | 保持函数体内延迟导入的模式不变 |
| crawler_service 是独立子系统，改动影响大 | 最后处理，且在独立 git worktree 中进行 |

### 为什么现在可以做了

之前不能做是因为 `__init__.py` 缺失——`backend/core/` 不是合法包，标准导入根本无法工作。P0 修复轮次已创建这三个 `__init__.py`：

- `backend/core/__init__.py`
- `backend/services/__init__.py`
- `backend/services/radar_service/__init__.py`

前提条件已满足，现在是动手的时机。

---

## P5. Plan Overfitting：Agent 重复执行已完成步骤

### 问题现象

用户说"搜微博关于 EDG 的六条帖子"，Agent 搜到了 6 条结果，但**又搜了一遍**。伴随三个症状：

1. **Agent 重复搜索** — plan 规划的 2 个 step 都调了 `search_posts`，搜完 6 条满足要求后，轮次 2 又调了一次
2. **计划修正失败** (`Expecting value: line 1 column 1`) — `_maybe_adjust_plan` 调 LLM 返回空，`json.loads("")` 抛异常
3. **跳过 auto_template 累积** — `_maybe_save_template` 检测到 critical 步骤失败，拒绝保存模板

### 根因

**三层问题叠加：**

#### 第一层：step_results 覆盖污染（代码 bug）

原始 step 跟踪逻辑用 `break` 匹配第一个同名工具，两次 `search_posts` 调用都把结果写到同一个 `step_1`：

```
轮次1: search_posts → 匹配 step_1 → step_1 = {6条, success}
轮次2: search_posts → 匹配 step_1 → step_1 = {0条, success=false}  ← 覆盖了轮次1
```

**修复：** `step_results` 已有值的 key 不再覆盖。只有**首次**写入才触发 plan adjustment。

#### 第二层：进度提示的矛盾信息（prompt 设计缺陷）

原进度提示同时告诉 LLM 两件事：
- "还有 1 步计划" — 催促执行
- "已完成目标可停止" — 建议停止

LLM 优先服从 plan，选了继续执行。

**修复：** 进度提示改为纯 goal-check："在决定下一步之前，先判断当前是否已满足用户的原始请求。如果是，直接回复用户，不要调任何工具。"

#### 第三层：Plan 格式过于强制（架构哲学的偏差）

原 `PLAN_PROMPT` 把几乎所有问题都引导到"拆为 2-5 步"，包括简单的搜索/查询。这造成了大量不必要的 plan 步骤，LLM 受 plan 约束执行了多余的轮次。

**修复：** `PLAN_PROMPT` 改为"绝大多数问题 → steps 为空数组"。只有定时调度和明确的多步组合（搜+滤+析+推）才需要填 steps。让 ReAct 循环根据实际数据自主决策，而不是被 JSON 计划锁死。

### 解决方案总结

三个修改同时生效：

| 文件 | 改动 |
|------|------|
| `agent_core.py` step 跟踪 | `key not in step_results` 防止覆盖 |
| `agent_core.py` 进度提示 | goal-check 替代 plan 步数提示 |
| `prompt_templates.py` PLAN_PROMPT | steps 默认为空，plan 降级为建议 |

**核心思想：** Plan 是建议，不是命令。执行路径由 ReAct 循环的 Observed→Decide→Act 驱动，不预先锁定。
