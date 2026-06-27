# MediaRadar 项目认知库

## 项目概述

舆情监控系统，基于 FastAPI + 双前端（Web + 小程序）构建。核心功能：多平台爬虫抓取 -> Multi-Agent AI 分析 -> 风险预警 + 多通道推送。

## 技术栈

- **后端**: FastAPI, SQLite, LangGraph, OpenAI SDK
- **爬虫**: Playwright/Selenium（crawler_service 子模块）
- **Web 前端**: Next.js 15 (App Router) + React 18 + TypeScript + Tailwind v4 + shadcn/ui (Radix + @base-ui/react)
  - 状态/数据: Zustand 5 + TanStack Query 5
  - 表格/虚拟化: TanStack Table + TanStack Virtual
  - 表单/校验: React Hook Form + Zod 4
  - 图表: Recharts 3 / 动画: framer-motion 12
  - 认证: NextAuth 5 (beta) + @auth/core（OAuth）
  - Mock: MSW 2 / 通知: sonner / 主题: next-themes / 图标: lucide-react / 命令面板: cmdk
- **小程序前端**: uni-app (Vue 3) — 旧版形态保留
- **AI**: DeepSeek（分析 + guide/celebrity/briefing 子图）、Kimi/Moonshot（risk 线 reviewer+direction 复核）、Qwen-VL（视觉）、BGE-M3（聚类）
- **Admin 监控**: Prometheus 指标 + AgentOpsEngine（LLM 运维健康巡检）

## 目录结构

```
backend/
├── gateway/main.py           # FastAPI 统一网关
├── core/                     # 核心组件（logger, config, database, auth, circuit_breaker）
│   ├── config.py             # Settings（环境变量 + 三层回退 DEFAULT→LLM→硬编码）
│   ├── logger.py             # 结构化日志
│   ├── database.py           # 数据库连接
│   ├── auth.py               # API Key 验证（get_valid_api_keys, API_KEY_HEADER）
│   ├── auth_db.py            # 用户表 CRUD（create_user, get_user_by_id 等）
│   ├── auth_jwt.py           # JWT 签发/解码
│   ├── auth_deps.py          # FastAPI 依赖注入（get_current_user, get_current_user_or_api_key, require_admin）
│   ├── login_lockout.py      # 登录锁定（失败次数 + 冷却时间）
│   ├── subscription_db.py    # 订阅表 CRUD（per-owner）
│   ├── quota_db.py           # 配额管理（订阅数/API 调用次数的 per-user 限制）
│   ├── model_config_db.py    # 模型配置表 CRUD + 回退逻辑
│   ├── agent_memory_db.py    # Agent 会话记忆持久化
│   ├── circuit_breaker.py    # LLM 熔断器
│   ├── metrics.py            # Prometheus 指标
│   ├── sanitize.py           # HTML/URL 净化
│   ├── security_middleware.py # 安全头 + 请求体大小限制
│   └── rate_limiter.py       # 请求限流（未认证非 auth 路径跳过）
├── services/
│   ├── radar_service/        # 数据采集与分析（调度器 + 原子组件 + 预警推送）
│   │   ├── main.py           # 调度入口（旧 job/run_analysis_pipeline，仍供 risk 线使用）
│   │   ├── pipeline.py       # [库] ScreenerStage/ClusterStage/VisionStage 阶段组件，被原子工具引用
│   │   ├── pipeline_configs.py # 管线配置（旧注册表，保留向后兼容）
│   │   ├── analysis_graph.py           # 风险线：LangGraph（analyst→reviewer→director）
│   │   ├── analysis_graph_guide.py     # 攻略线：LangGraph（extractor→comparer→summarizer）
│   │   ├── analysis_graph_celebrity.py # 追星线：LangGraph（sentiment→heat→aggregator）
│   │   ├── analysis_graph_briefing.py  # 简报线：LangGraph（categorizer→highlighter→writer）
│   │   ├── llm_gateway.py    # LLM 调用统一网关（call_llm）
│   │   ├── prompt_templates.py # Screener + 各线分析 Prompt
│   │   ├── schemas.py        # Pydantic 数据契约（各线 ScreenerResult + Analyst/ReviewerResult）
│   │   ├── vision_agent.py   # Qwen-VL-Max 视觉模型调用
│   │   ├── embed_cluster.py  # HDBSCAN 向量聚类
│   │   ├── topic_tracker.py  # 话题演化追踪 + Qdrant 向量检索
│   │   ├── topic_aggregator.py # 聚合 Topic 写入 SQLite
│   │   ├── vector_store.py   # Qdrant 向量存储操作
│   │   ├── api.py            # /api/radar_status, /api/start_task 等
│   │   ├── db_manager.py     # SQLite 操作
│   │   ├── scheduler.py      # APScheduler 定时调度器
│   │   ├── push_generator.py # 邮件内容生成
│   │   └── notifier/          # 预警推送（包）
│   │       ├── __init__.py   # send_alert(), send_batch_alert()
│   │       ├── base.py       # NotifierBase 抽象类
│   │       ├── registry.py   # NotifierRegistry
│   │       ├── models.py     # AlertPayload, PushChannel
│   │       ├── channel_email.py / wecom.py / feishu.py / rss.py
│   ├── agent_service/        # AI 助手（重点 — 流式对话 + Function Calling + 适配器架构）
│   │   ├── agent_core.py     # 流式对话引擎，AgentContext 统一状态
│   │   ├── sse.py            # SSE 事件工厂
│   │   ├── workflows_db.py   # v2.0 统一工作流存储（preset + auto_template + user）
│   │   ├── adapters/         # 工具适配器层（路由到不同后端）
│   │   │   ├── base.py       # AbstractToolAdapter 抽象类
│   │   │   ├── direct_adapter.py # 直接调用 Python 函数
│   │   │   └── mcp_adapter.py    # HTTP transport 调用 FastMCP Server
│   │   ├── tools/            # 工具集（按组分文件）
│   │   │   ├── _base.py      # @tool 装饰器 + ToolResult
│   │   │   ├── _owner.py     # @with_owner 强制注入 owner_id
│   │   │   ├── _constants.py # 常量定义
│   │   │   ├── atomic.py     # H 组：12+ 原子工具（search_posts, filter_content 等）
│   │   │   ├── composite.py  # I 组：组合工具动态注册
│   │   │   ├── subscription.py / scan.py / query.py / push.py / model.py / system.py
│   │   │   ├── search.py / guide.py / celebrity.py / briefing.py  # 各线专用工具
│   │   │   └── sentiment_dict.py # 领域情感词典
│   │   ├── reflection/       # 置信度评估 + 补充探查
│   │   ├── diagnosis/        # 错误分类 + 熔断恢复
│   │   └── memory/           # 记忆管理（jieba 分词 + TTL 缓存）
│   ├── admin_service/        # Admin 监控（v2.2 新增）
│   │   ├── agent_monitor.py  # AgentMonitorService（Prometheus 聚合）
│   │   ├── agent_ops.py      # AgentOpsEngine（LLM 运维分析）
│   │   └── api.py            # Admin API + WebSocket
│   ├── subscription_service/ # 订阅/配额/Admin API
│   ├── search_lib/           # 搜索库（search_service 重命名）
│   └── crawler_service/      # 爬虫子模块（独立完整，暂不深入）
frontend/
├── web/                          # Next.js 15 Web 端（主推形态）
│   ├── app/
│   │   ├── (app)/                # 已登录路由组（含 sidebar 布局）
│   │   │   ├── dashboard/        # 仪表盘
│   │   │   ├── agent/            # AI 助手
│   │   │   ├── yq-list/          # 舆情列表
│   │   │   └── settings/         # 设置：account / llm / push / system
│   │   ├── admin/                # Admin 管理路由（独立布局）
│   │   ├── (auth)/login/         # 登录页
│   │   ├── api/auth/[...nextauth]/  # NextAuth 路由
│   │   └── auth/callback/        # OAuth 回调
│   ├── components/
│   │   ├── layout/               # sidebar / topbar / page-header
│   │   ├── ui/                   # shadcn 组件
│   │   ├── charts/               # 图表封装
│   │   ├── chat/                 # 对话组件
│   │   └── animated-number.tsx
│   ├── hooks/   lib/   stores/   types/
│   └── public/
└── MiniApp/                      # uni-app 小程序（旧版形态）
    ├── src/pages/
    │   ├── index/index.vue       # 首页仪表盘
    │   ├── chat/agentChat.vue    # AI 助手聊天
    │   ├── list/list.vue         # 舆情列表
    │   ├── profile/profile.vue   # 个人中心 V1.0.1
    │   └── settings/
    │       ├── settings.vue      # 监控设置
    │       ├── pushSettings.vue  # 推送设置（企业微信/飞书/邮箱）
    │       └── apiSettings.vue   # 模型设置（默认+5个Agent角色）
    └── src/utils/api.js          # API 调用封装（含 push / llm 相关）
```

## 核心架构：Agent + Tools + Workflows

旧 Pipeline（`RadarPipeline` → `ScreenerStage` → `ClusterStage` → `LangGraph`）已被**拆解为原子工具 + 组合工作流**，由 Agent Function Calling 动态编排，而非硬编码管线。

```
用户 → Agent 流式对话 (agent_core.py)
         │
         ├── DirectAdapter → 从 _REGISTRY 直调 Python 函数
         │     ├── A~G 组工具 (subscription/scan/query/push/model/search/system)
         │     ├── H 组原子工具 (atomic.py, 12+ 个)
         │     │   ├── search_posts → crawler_adapter → 爬虫子进程
         │     │   ├── filter_content → ScreenerStage
         │     │   ├── cluster_related → ClusterStage
         │     │   └── extract_slots / compare_opinions / analyze_sentiment / ...
         │     └── I 组组合工具 (composite.py, 动态注册)
         │         └── execute_workflow_steps() 链式执行
         │
         └── MCPAdapter → HTTP transport 调 FastMCP Server（可选）
```

### 工作流系统（workflows_db.py）

单表 `workflows` 三源合一，`execute_workflow_steps()` 统一执行：

| 来源 | 说明 | 例子 |
|------|------|------|
| `preset` | 预置组合工具，启动时注册为 FC 工具 | `deep_analyze_topic`, `scan_and_alert`, `quick_guide`, `briefing_digest` |
| `auto_template` | 用户对话自动累积的模板 | 命中时 `hit_count++` |
| `user` | 用户自定义 cron 定时任务 | 调度器每分钟轮询到期执行 |

### 原子工具（atomic.py H 组，12+ 个）

| 工具 | 对应旧阶段 | 说明 |
|------|-----------|------|
| `search_posts` | 爬虫采集 | 调 `quick_crawl_stream()` 启动爬虫子进程 |
| `filter_content` | ScreenerStage | 封装 `ScreenerStage`，4 种 intent (risk/guide/celebrity/briefing) |
| `cluster_related` | ClusterStage | 封装 `ClusterStage`，HDBSCAN 聚类 |
| `extract_slots` | 分析 | 规则提取结构化槽位（时间/地点/花费） |
| `compare_opinions` | 分析 | 跨平台加权观点对比 |
| `generate_itinerary` | 结果 | 行程计划生成 |
| `analyze_sentiment` | 分析 | 规则词典 + LLM 混合情感判定 |
| `calc_velocity` | 分析 | 时间序列情感速度变化 |
| `compare_platforms` | 分析 | 跨平台叙事对比 |
| `query_report` | 查询 | 查询已生成的报告 |
| `push_report` | 推送 | 通过指定通道推送 |
| `list_workflows` | 管理 | 列出工作流 |
| `manage_workflow` | 管理 | 启用/停用/删除/立即执行/另存 |

### AI 助手（Agent Service）

```
AgentContext (session_id/owner_id/messages/iteration)
         │
    phase_build_context → 注入 system prompt + 长期记忆
         │
    [循环] phase_plan → phase_act → phase_observe
         │                          │
        LLM 调用                   ToolExecutor.execute()
         │                          ├── DirectAdapter.supports() 优先
         │                          └── 失败 → MCPAdapter 回退
         │
    TokenBudgetManager → 超预算自动压缩历史

```

### 调度流程（scheduler.py）

```
调度器启动 (scheduler_start → BackgroundScheduler)
    │
    ├── _run_scan() (按 IntervalTrigger 定时触发)
    │       ↓
    │   收集所有用户订阅 → 逐用户执行：
    │     ├── risk 类型 → job_async(owner_id) → 旧 pipeline（爬虫 + RadarPipeline）
    │     └── 其他类型 → _run_extra_pipelines_composite() → 调组合工具
    │
    ├── _run_user_workflows() (每分钟) → 检查用户 cron 工作流到期
    │
    └── _run_daily_summary() (按 push_time 触发) → 每日简报邮件
```

### 旧 Pipeline.py 现状

`pipeline.py` 中的 `ScreenerStage`、`ClusterStage`、`VisionStage` 等类仍被原子工具作为**库**引用（`filter_content` 导入 `ScreenerStage`，`cluster_related` 导入 `ClusterStage`）。`RadarPipeline` 编排器仅在 risk 线的 `job_async()` 旧路径中使用。详见开发注意事项 #5。

## 关键 API

### 网关
| 端点 | 方法 | 描述 |
|------|------|------|
| `/metrics` | GET | Prometheus 指标 |
| `/health` | GET | 健康检查（含 scheduler 状态） |

### 用户认证（auth_service）
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/auth/register` | POST | 用户注册 |
| `/api/auth/login` | POST | 登录（返回 JWT） |
| `/api/auth/refresh` | POST | Token 刷新 |
| `/api/auth/me` | GET | 当前用户信息 |
| `/api/auth/logout` | POST | 登出 |
| `/api/auth/change-password` | POST | 修改密码 |
| `/api/auth/set-password` | POST | 设置密码 |
| `/api/auth/oauth/{provider}/login` | GET | OAuth 登录（微信/Google） |
| `/api/auth/oauth/{provider}/callback` | GET | OAuth 回调 |
| `/api/admin/users` | GET | 用户列表（admin） |
| `/api/admin/users/{user_id}` | DELETE | 删除用户（admin） |
| `/api/admin/users/{user_id}/reactivate` | POST | 恢复用户（admin） |

### 舆情雷达（radar_service）
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/radar_status` | GET | 雷达运行状态 |
| `/api/start_task` | POST | 触发全网扫描 |
| `/api/yq_list` | GET | 舆情列表 |
| `/api/settings` | GET/POST | 系统配置（关键词/平台等） |
| `/api/circuit/states` | GET | 熔断器状态 |
| `/api/mcp/health` | GET | MCP 健康 |
| `/api/scheduler/start` | POST | 启动 APScheduler |
| `/api/scheduler/stop` | POST | 停止调度器 |
| `/api/scheduler/status` | GET | 调度器状态 |
| `/api/topic_list` | GET | 话题列表 |
| `/api/topic/{topic_id}` | GET | 话题详情 |
| `/api/topic/{topic_id}/process` | POST | 处理话题 |
| `/api/topic_evolution` | GET | 话题演变 |
| `/api/topic_evolution/migrate_clusters` | POST | 迁移聚类 |
| `/api/topic_stats` | GET | 话题统计 |
| `/api/volume_stats` | GET | 声量统计 |
| `/api/today_summary` | GET | 今日摘要 |
| `/rss/{token}.xml` | GET | RSS 订阅 |

### 推送配置
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/push/configs` | GET | 所有推送配置 |
| `/api/push/config/{channel}` | GET/POST | 获取/保存通道配置 |
| `/api/push/test` | POST | 测试推送通道 |

### 模型配置
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/llm/configs` | GET | 所有模型配置（含默认回退） |
| `/api/llm/config/{agent}` | POST | 更新 Agent 模型配置 |
| `/api/llm/test/{agent}` | POST | 测试 Agent 连通性 |

### AI 助手（agent_service）
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/agent/chat` | POST | AI 助手对话（SSE 流式） |
| `/api/agent/memory` | GET | 记忆列表 |
| `/api/agent/memory/{session_id}` | GET/DELETE | 记忆详情/删除 |

### Admin 监控（admin_service）
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/admin/agents/overview` | GET | Agent 概览（工具调用/错误率/会话数） |
| `/api/admin/agents/tools` | GET | 工具健康明细 |
| `/api/admin/agents/sessions` | GET | 会话统计数据 |
| `/api/admin/agents/diagnosis` | GET | 诊断事件日志 |
| `/api/admin/agents/memory` | GET | 记忆库统计 |
| `/api/admin/agents/report` | GET | 健康巡检报告（LLM 分析+告警+建议） |
| `/api/admin/agents/report/daily` | GET | 每日运维日报（LLM 生成） |
| `/api/admin/agents/chat` | POST | 自然语言查询 Agent 状态 |

### 订阅管理（subscription_service）
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/subscriptions` | GET/POST | 订阅列表/创建 |
| `/api/subscriptions/{sub_id}` | GET/DELETE | 订阅详情/删除 |
| `/api/model-configs` | GET | 模型配置 |
| `/api/model-configs/{agent_role}` | PUT/DELETE | 更新/删除模型配置 |
| `/api/quota` | GET | 配额查询 |
| `/api/admin/stats` | GET | Admin 统计 |
| `/api/admin/users/{user_id}` | GET | 用户详情（admin） |
| `/api/admin/users/{user_id}/quota` | GET/PUT | 用户配额（admin） |
| `/api/admin/users/{user_id}/deactivate` | POST | 停用用户（admin） |
| `/api/admin/users/{user_id}/role` | POST | 修改角色（admin） |

## AI 助手（Agent Service）

### 架构：适配器模式 + Function Calling

```
agent_core.py (AgentContext 流式主循环)
  ├── phase_build_context → 注入 system prompt + 长期记忆
  ├── phase_plan → LLM 规划
  ├── phase_act → ToolExecutor.execute()
  │     ├── DirectAdapter → 从 _REGISTRY 直调 Python 函数（优先）
  │     └── MCPAdapter → HTTP transport 调 FastMCP Server（回退）
  └── phase_observe → 观察结果
```

工具通过 `@tool()` 装饰器注册到全局 `_REGISTRY`，通过 `@with_owner` 强制注入 `owner_id`。
启动时 `register_composite_tools()` 从 workflows 表读取 `is_composite_tool=1` 的 preset 条目，动态注册为 FC 工具。

### 工具分组

| 组 | 文件 | 用途 |
|----|------|------|
| A 组 | subscription.py | 订阅管理（list/add/update/remove/parse_intent） |
| B 组 | scan.py | 扫描/调度（trigger_scan/get_scan_status/set_scan_interval/pause/resume） |
| C 组 | query.py | 数据查询（search_alerts/get_topic_detail/web_search） |
| D 组 | push.py | 推送管理（list/toggle/configure/test_channel） |
| E 组 | model.py | 模型管理（list/switch/test_model） |
| F 组 | system.py | 系统状态（get_system_status） |
| H 组 | atomic.py | 12+ 原子工具（search_posts/filter_content/cluster_related/extract_slots/compare_opinions/analyze_sentiment/calc_velocity/compare_platforms/query_report/push_report/list_workflows/manage_workflow 等） |
| I 组 | composite.py | 组合工具动态注册（deep_analyze_topic/scan_and_alert/quick_guide/briefing_digest） |
| 线查询 | guide.py / celebrity.py / briefing.py / search.py | 各线报告查询工具 |

对话风格：公关总监口吻，专业简洁。

## 前端关键页面

### Web 端（Next.js，主推形态）
- **登录** (`/login`): NextAuth OAuth 登录
- **仪表盘** (`/dashboard`): 数据统计 + 图表（Recharts）
- **AI 助手** (`/agent`): 与 Agent 流式对话
- **舆情列表** (`/yq-list`): TanStack Table + Virtual 虚拟滚动
- **设置中心** (`/settings/{account|llm|push|system}`): 账号 / 模型 / 推送通道 / 系统配置
- **Admin 管理** (`/admin`): Agent 监控仪表盘 + 运维报表

### 小程序端（uni-app，旧版保留）
- **首页** (`/pages/index/index`): 仪表盘，展示今日舆情统计、AI 摘要、启动扫描按钮
- **AI 助手** (`/pages/chat/agentChat`): 与 Agent 流式对话
- **舆情列表** (`/pages/list/list`): 查看历史舆情
- **个人中心** (`/pages/profile/profile`): 推送设置、模型设置 V1.0.1
- **推送设置** (`/pages/settings/pushSettings`): 企业微信/飞书/邮箱通道配置
- **模型设置** (`/pages/settings/apiSettings`): 默认模型 + 5个 Agent 角色独立配置

## 模型配置机制

支持每个 Agent 角色单独配置模型，未配置时自动回退到**默认模型**：

| 角色 | 用途 | 属于 |
|------|------|------|
| 默认模型 | 所有 Agent 的兜底配置 | 全局 |
| 分析员 | 舆情风险分析（analyst node） | risk 线 |
| 复核员 | 交叉复核判定（reviewer node） | risk 线 |
| 向量引擎 | 文本向量聚类 | ClusterStage |
| 视觉引擎 | 图片证据解析 | VisionStage |

## 可用 Skills

| Skill | 用途 | 触发场景 |
|-------|------|----------|
| `/frontend-design` | 创建高质量前端界面，避免 AI 通用美学 | 构建 Web 组件、页面、落地页等 |
| `/shadcn-ui` | shadcn/ui 组件库指南 | 安装组件、表单、Dialog、Table 等 |
| `/ui-ux-pro-max` | UI/UX 设计智能（样式、配色、字体、UX 规则） | 设计新页面、选择配色/字体、UX 审核 |

## 开发注意事项

1. **启动后端**: `python backend/gateway/main.py`（端口 8008）
2. **启动 Web 前端**: `cd frontend/web && npm run dev`（端口 3003，Next.js 15 App Router）
   - ⚠️ Next.js 15 与 14/13 有破坏性变更，写代码前优先查 `node_modules/next/dist/docs/`
   - API 契约见 `docs/API_CONTRACT.md`，开发期可用 MSW mock
3. **环境变量**: 项目根目录 `.env`，Web 端 `frontend/web/.env`，Qdrant 配置在 `Settings` 类中有默认值
4. **爬虫目录**: `backend/services/crawler_service/` 启动命令 `python main.py`
5. **pipeline.py（库文件）**: `ScreenerStage`、`ClusterStage`、`VisionStage` 等阶段组件仍被原子工具作为库引用（如 `filter_content` 导入 `ScreenerStage`，`cluster_related` 导入 `ClusterStage`）。`RadarPipeline` 编排器仅在 risk 线的 `job_async()` 旧路径中使用。**新代码应调用原子工具/组合工具，而非直接实例化 `RadarPipeline`。**
6. **LangGraph**: 4 个分析子图仍在 `analysis_graph.py`（risk, analyst→reviewer→director, DeepSeek+Kimi）、`analysis_graph_guide.py`（extractor→comparer→summarizer）、`analysis_graph_celebrity.py`（sentiment→heat→aggregator）、`analysis_graph_briefing.py`（categorizer→highlighter→writer）中。risk 线由 `job_async()` 触发，其他线通过组合工具的 `analysis_callable` 注入调用。
7. **轮询间隔**: 前端首页 3 秒轮询一次后端状态
8. **推送通道**: 企业微信/飞书/邮箱/RSS，`notifier/` 包使用相对导入，通过 `send_alert()` / `send_batch_alert()` 触发。推送策略由 `push_mode` 控制（every=全推/important=仅≥4级/silent=不推），通过 `PipelineConfig.push_mode` 传入旧 pipeline，或由 Agent 工具 `push_report` 直接调用。
9. **模型配置**: `update_llm_config()` 写入 `.env` 并立即更新内存 `settings`，避免重复 key
10. **调度器**: `scheduler.py` 使用 APScheduler。`_run_scan()` 收集用户订阅，依 `pipeline_types` 分发：risk 走 `job_async()`（旧 pipeline），其他走 `_run_extra_pipelines_composite()`（组合工具）。`_run_user_workflows()` 每分钟检查用户 cron 工作流到期执行。
11. **邮件模板**: `push_generator.py` 中三个 HTML 模板，BATCH_PUSH_HTML_TEMPLATE（批量预警）/ PUSH_HTML_TEMPLATE（单条预警）/ DAILY_SUMMARY_TEMPLATE（每日简报），均支持 `<details>` 可折叠
12. **批量预警**: `send_batch_alert()` 将一次扫描的所有高危舆情合并成一封邮件/一条消息，各 channel 的 `send_batch()` 方法负责渲染批量内容。预警触发受 `push_mode` 管控（every=全部推/important=仅≥4级/silent=不推）。
