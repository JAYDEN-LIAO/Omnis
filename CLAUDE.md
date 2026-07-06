# Omnis 项目认知库

## 项目概述

媒体信息智能平台，基于 FastAPI + Next.js 构建。核心模式：Agent 驱动的智能工作流，用户通过对话或工作台进行信息采集、分析、对比和推送。原名为 MediaRadar，已全面重构为 Omnis。

## 技术栈

- **后端**: FastAPI, SQLite, APScheduler, OpenAI SDK
- **爬虫**: Playwright/Selenium（crawler_service 子模块）
- **Web 前端**: Next.js 15 (App Router) + React 18 + TypeScript + Tailwind v4 + shadcn/ui
  - 状态/数据: Zustand 5 + TanStack Query 5
  - 表格/虚拟化: TanStack Table + TanStack Virtual
  - 表单/校验: React Hook Form + Zod 4
  - 图表: Recharts 3 / 动画: framer-motion 12
  - 认证: NextAuth 5 + @auth/core（OAuth）
  - Mock: MSW 2 / 通知: sonner / 图标: lucide-react
- **AI**: DeepSeek（主力模型）、Kimi（辅助分析）、Qwen-VL（视觉）
- **Admin**: Prometheus 指标 + AgentOpsEngine

## 后端架构

```
backend/
├── gateway/main.py          # FastAPI 入口 + 6 个 router 挂载
├── core/                    # 基础设施（无业务逻辑）
│   ├── config.py / logger.py / database.py / context.py / metrics.py
│   ├── crypto_utils.py / circuit_breaker.py / rate_limiter.py
│   ├── security_middleware.py / sanitize.py
│   └── auth.py / quota.py
├── shared/                  # 共享数据访问层
│   ├── audit.py / qdrant_client.py
│   └── db/ (subscription_db / quota_db / model_config_db)
├── services/
│   ├── auth_service/        # 用户认证
│   │   ├── api.py / deps.py / jwt.py
│   │   ├── db/ (CRUD + lockout)
│   │   └── oauth_providers/
│   ├── agent_service/       # AI 智能体（核心）
│   │   ├── agent_core.py        # 主循环 + AgentContext + ToolExecutor
│   │   ├── agent_planner.py     # 规划层
│   │   ├── prompts.py           # Agent 规划 Prompt
│   │   ├── workflows_db.py      # 工作流存储 + cron + 取消事件
│   │   ├── pipeline.py          # ScreenerStage / ClusterStage / VisionStage
│   │   ├── schemas.py / llm_gateway.py
│   │   ├── embed_cluster.py / vision_agent.py
│   │   ├── crawler_adapter.py / search_filter.py
│   │   ├── api.py / sse.py
│   │   ├── tools/               # 24 个原子 + 组合工具
│   │   │   ├── __init__.py      # 注册中心
│   │   │   ├── _base.py / _owner.py
│   │   │   ├── atomic_data.py   # H1-H3: search / filter / cluster
│   │   │   ├── atomic_analysis.py # H4-H9: 分析工具
│   │   │   ├── atomic_mgmt.py   # H10-H12: 管理工具
│   │   │   ├── composite.py     # I 组: 组合工具
│   │   │   ├── subscription / scan / query / push / model / system
│   │   │   ├── search / guide / celebrity / briefing
│   │   │   ├── screener_prompts.py
│   │   │   └── sentiment_dict.py
│   │   ├── adapters/ (DirectAdapter / MCPAdapter)
│   │   ├── memory/ (Manager + Store + DB)
│   │   ├── reflection/          # 置信度评估
│   │   └── diagnosis/           # 错误诊断 + 熔断
│   ├── platform_service/   # 平台能力（原 radar_service）
│   │   ├── api.py / main.py / scheduler.py
│   │   ├── db/ / analysis/ / push/ / notifier/
│   ├── subscription_service/ # 订阅/配额 API
│   └── admin_service/       # Admin 监控 + 用户管理
└── data/                    # SQLite + Qdrant（统一存放）
```

## 核心架构：Agent 驱动

```
用户输入
  → phase_build_context（system prompt + 长期记忆注入）
  → phase_plan（LLM 规划 → 生成 plan）
  → 主循环（最多 N 次迭代）
       → LLM 流式调用（回复或工具调用）
       → phase_act（执行工具 → Reflection 质量把关 → Diagnosis 错误恢复）
       → 返回结果 → 循环判断是否满足用户需求
  → phase_finish（emit_done + 异步写记忆）
```

### 工具注册机制

`@tool()` 装饰器自动注册到全局 `_REGISTRY`，运行时通过 `DirectAdapter` 直调 Python 函数。

### 工作流系统

单表 `workflows` 三源合一：
- **preset**: 4 个预置组合工具（deep_analyze_topic / scan_and_alert / quick_guide / briefing_digest）
- **auto_template**: 用户对话自动累积的模板
- **user**: 用户自定义 cron 定时任务

## 关键 API

### 认证（auth_service）
`/api/auth/register` | `/login` | `/me` | `/logout` | `/oauth/*` | `/api/auth/redeem-invite` | `/invite-status`

### Agent（agent_service）
`POST /api/agent/chat`（SSE 流式）| `GET /api/agent/memory` | `GET /api/agent/workflows`

### 数据（platform_service）
`/api/topic_list` | `/api/topic/{id}` | `/api/volume_stats` | `/api/today_summary` | `/api/radar_status`
`/api/push/configs` | `/api/push/config/{channel}` | `/api/push/test`
`/api/llm/configs` | `/api/llm/config/{agent}` | `/api/llm/test/{agent}`
`/api/scheduler/start|stop|status`

### 订阅（subscription_service）
`/api/subscriptions/*` | `/api/model-configs/*` | `/api/quota`

### Admin（admin_service）
`/api/admin/users/*` | `/api/admin/agents/*`

## 前端关键页面

- **登录** `/login`: 邮箱注册/登录 + Google OAuth + 游客访问
- **信息助手** `/agent`: 与 Agent 流式对话 + 智能实况面板
- **工作台** `/workspace`: 预设工作流卡片 + 最近运行 + 我的工作流
- **数据看板** `/dashboard`: 系统概览 + Agent 状态 + 数据来源 + 活动流
- **设置** `/settings/*`: 关于 / 推送 / 模型配置 / 账号

## 开发注意事项

1. **启动后端**: `python backend/gateway/main.py`（端口 8008）
2. **启动前端**: `cd frontend/web && npm run dev`（端口 3003）
3. **环境变量**: 项目根目录 `.env`，参考 `.env.example`
4. **ScreenerStage/ClusterStage**: 在 `agent_service/pipeline.py` 中，被 `atomic_data.py` 的工具调用，不是独立服务
5. **推送通道**: `platform_service/notifier/`，支持企业微信/飞书/邮箱/RSS，Agent 通过 `push_report` 工具触发
6. **模型配置**: 每个 Agent 角色可单独配置，未配置时回退到 DEFAULT 模型
7. **调度器**: `platform_service/scheduler.py` 仅执行用户 cron 工作流 + 每日记忆清理，不自动扫描
8. **邀请码**: 新用户无系统 Key 权限，需在模型设置页输入 `KSKBL1027` 兑换
