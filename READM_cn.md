# MediaRadar 舆情雷达

多平台社交媒体监测、AI 舆情分析与智能预警系统。

MediaRadar 是一个全栈平台，支持对中文社交媒体（微博、小红书、B 站等）的内容爬取、多 Agent LLM 分析，以及通过邮件/企业微信/飞书/RSS 推送的 actionable intelligence。

## 核心架构

### v2.0 三层 Agent 架构

```
用户输入
     │
     ▼
┌──────────────────────────────────┐
│  phase_plan（规划层）           │
│  • 约束提取                      │
│  • 模板匹配                      │
│  • LLM 任务拆解                  │
│  • 动态调整                      │
│                                  │
│  mode=immediate ──────┐         │
│  mode=scheduled ──────┼──┐      │
└───────────────────────┼──┼──────┘
          │             │  │
          ▼             │  ▼
     执行主循环          │  user_workflows
     • 进度提示         │  (APScheduler)
     • 取消检查点       │     │
     • 优先级执行        │     ▼
          │             │  execute_workflow_steps
          ▼             │
          │             │
          ▼             ▼
┌──────────────────────────────────┐
│  工具层（50+ 个工具）           │
│                                  │
│  • 原子工具（13个）             │
│    search_posts · filter_content │
│    cluster_related · compare_   │
│    opinions · analyze_sentiment │
│    calc_velocity · push_report  │
│                                  │
│  • 预设工作流注册为工具（4个）  │
│    deep_analyze_topic（工作流）  │
│    quick_guide（工作流）        │
│    scan_and_alert（工作流）     │
│    briefing_digest（工作流）    │
│                                  │
│  • 传统管理工具（~30个）        │
│    A: 订阅 · B: 扫描            │
│    C: 查询 · D: 推送 · E: 模型  │
│    G: 系统状态                   │
└──────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────┐
│  Pipeline 内部阶段              │
│  （初筛 → 视觉 → 聚类          │
│   → LangGraph 分析 → 预警）     │
└──────────────────────────────────┘
```

系统从纯反应式的工具调用循环升级为**规划驱动架构**：智能规划层分解复杂请求，执行循环调用工具（含预设工作流注册成的工具）完成各步骤。

### 多管线支持

四种管线模式，共享同一初筛→聚类→分析骨架：

| 模式 | 用途 | 分析子图 |
|------|------|---------|
| `full` | 舆情风险监控 | 分析员 → 复核员 → 主管 |
| `guide` | 攻略类内容分析 | 提取器 → 比较器 → 总结器 |
| `celebrity` | 追星趋势追踪 | 情感 → 热度 → 聚合器 |
| `briefing` | 每日综合简报 | 分类器 → 高亮器 → 撰稿人 |

## 功能特性

- **多平台爬虫** — 微博、小红书、B 站、抖音、快手、贴吧、知乎
- **AI 分析** — LangGraph 流水线（分析员/复核员/主管 三级 Agent，DeepSeek + Kimi 交叉验证）
- **智能规划** — 复杂多步请求自动拆解（如"对比理想和蔚来过去一周在微博和小红书关于售后服务的讨论"）
- **用户工作流** — 自然语言创建、定时（cron）执行、管理工作流
- **多渠道预警** — 邮件、企业微信、飞书推送 + RSS 订阅
- **订阅引擎** — 每个用户独立配置（类型/极性/灵敏度/推送模式）
- **AI 助手** — 50+ Function Calling 工具，9 组分类，自然语言控制系统
- **用户级隔离** — 数据、配置、告警完全按用户隔离
- **打断机制** — 三层取消（Agent SSE / Pipeline / 爬虫），资源自动清理
- **Admin 监控** — 实时 Agent 指标、工作流执行日志、趋势分析、LLM 健康报告
- **网页仪表盘** — Next.js 15 + shadcn/ui + Framer Motion
- **微信小程序** — uni-app (Vue 3) 移动端
- **可观测性** — Prometheus 指标（LLM 调用/Pipeline 耗时/Agent 轮次/工作流执行）

## 技术栈

| 层 | 技术 |
|-------|-----------|
| 后端 | Python 3.11, FastAPI, SQLite |
| AI/LLM | LangGraph, DeepSeek, Kimi, Qwen-VL, BGE-M3 |
| 爬虫 | Playwright, httpx |
| 网页前端 | Next.js 15, Tailwind CSS 4, shadcn/ui (Radix + Base UI), Framer Motion |
| 小程序 | uni-app (Vue 3) |
| 认证 | JWT (HS256), bcrypt, Google OAuth 2.0 |
| 调度器 | APScheduler |
| 监控 | Prometheus + Admin Agent Monitor |
| 向量 | HDBSCAN 聚类，文本嵌入 |

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+

### 后端启动

```bash
pip install -r requirements.txt
cp .env.example .env   # 编辑 API 密钥
python backend/gateway/main.py   # API 地址 http://localhost:8008
```

### 网页前端启动

```bash
cd frontend/web
npm install
npm run dev   # 访问 http://localhost:3003
```

### 小程序启动

```bash
cd frontend/MiniApp
npm install
# 使用 HBuilder X 或微信开发者工具打开
```

## 项目结构

```
backend/
├── gateway/main.py              # FastAPI 统一网关（8008，挂载所有路由）
├── core/                        # 共享基础设施
│   ├── config.py                # 三层配置回退
│   ├── auth*.py                 # JWT、用户 CRUD、认证依赖、登录锁定
│   ├── database.py              # SQLite 连接管理
│   ├── metrics.py               # Prometheus 指标（含工作流/规划计数）
│   ├── circuit_breaker.py       # 每工具 LLM 熔断器
│   ├── logger.py                # 结构化 JSON 日志
│   ├── sanitize.py              # HTML/URL 净化
│   ├── security_middleware.py   # 安全头 + 请求体大小限制
│   ├── rate_limiter.py          # 请求限流
│   ├── subscription_db.py       # 订阅表 CRUD（per-owner）
│   ├── quota_db.py              # per-user 配额管理
│   ├── model_config_db.py       # 按 Agent 角色的模型配置 + 回退
│   └── agent_memory_db.py       # 会话记忆持久化
├── services/
│   ├── agent_service/           # AI 助手（v2.0 升级核心）
│   │   ├── agent_core.py        # 规划引擎 + 执行主循环 + CancelRegistry
│   │   ├── sse.py               # SSE 事件工厂（text/tool_call/plan/progress）
│   │   ├── workflows_db.py      # 统一工作流存储（preset/auto_template/user）
│   │   ├── tools/               # 50+ Function Calling 工具，9 组分类
│   │   │   ├── atomic.py        # H 组：13 个原子工具
│   │   │   ├── composite.py     # I 组：4 个组合工具（动态注册）
│   │   │   ├── subscription.py  # A 组：订阅管理
│   │   │   ├── scan.py          # B 组：扫描/调度控制
│   │   │   ├── query.py         # C 组：数据查询 + 网络搜索
│   │   │   ├── push.py          # D 组：推送通道管理
│   │   │   ├── model.py         # E 组：模型配置
│   │   │   ├── system.py        # G 组：系统状态
│   │   │   ├── guide.py         # 攻略管线查询工具
│   │   │   ├── celebrity.py     # 追星管线查询工具
│   │   │   ├── briefing.py      # 简报管线查询工具
│   │   │   ├── sentiment_dict.py# 领域情感词典
│   │   │   ├── _base.py         # @tool 装饰器 + 注册
│   │   │   └── _owner.py        # @with_owner owner_id 注入
│   │   └── memory/              # 会话记忆（jieba + TTL 缓存）
│   ├── radar_service/           # 舆情分析引擎
│   │   ├── pipeline.py          # Pipeline 调度器（4 模式 + PipelineCanceller）
│   │   ├── llm_gateway.py       # LangGraph 分析子图
│   │   ├── analysis_graph*.py   # 4 个分析子图（风险/攻略/追星/简报）
│   │   ├── pipeline_configs.py  # Pipeline 配置构建器
│   │   ├── prompt_templates.py  # 初筛提示词 + PLAN_PROMPT
│   │   ├── scheduler.py         # APScheduler（扫描 + 每日简报 + 用户工作流）
│   │   ├── db_manager.py        # SQLite 操作
│   │   ├── push_generator.py    # 邮件 HTML 模板
│   │   └── notifier/            # 预警推送通道（邮件/企微/飞书/RSS）
│   ├── auth_service/            # 多用户认证 & OAuth
│   │   └── oauth_providers/     # Google OAuth
│   ├── subscription_service/    # 订阅/配额/Admin API
│   ├── admin_service/           # Agent 监控 & 智能运维
│   │   ├── agent_monitor.py     # Prometheus 聚合层
│   │   ├── agent_health_db.py   # 诊断事件 + 工作流执行日志
│   │   ├── agent_ops.py         # LLM 健康巡检/日报
│   │   └── api.py               # REST 端点 + WebSocket
│   ├── search_lib/              # 搜索库
│   └── crawler_service/         # 平台爬虫（独立模块）
frontend/
├── web/                         # Next.js 15 仪表盘（3003）
│   ├── app/(app)/               # 已登录路由组
│   │   ├── dashboard/           # 统计 + 图表（Recharts）
│   │   ├── agent/               # AI 对话界面（SSE 流式）
│   │   ├── yq-list/             # 舆情列表（TanStack Table + Virtual）
│   │   └── settings/            # 账号 / 模型 / 推送 / 系统
│   └── components/
│       ├── layout/              # 侧边栏 + 顶栏
│       ├── ui/                  # shadcn/ui 组件
│       └── charts/              # 图表封装
└── MiniApp/                     # uni-app 小程序
upgrade2.0/                      # v2.0 升级设计文档
deploy/                          # 部署配置
scripts/                         # 验证测试脚本
```

## API 概览

### AI 助手（agent_service）
| 端点 | 方法 | 说明 |
|----------|--------|-------------|
| `/api/agent/chat` | POST | AI 对话（SSE 流：text/tool_call/tool_progress/plan/done） |
| `/api/agent/chat/{session_id}/cancel` | POST | 取消正在运行的会话 |
| `/api/agent/workflows/{workflow_id}/cancel` | POST | 取消正在运行的工作流 |
| `/api/agent/memory` | GET | 记忆列表 |
| `/api/agent/memory/{session_id}` | GET/DELETE | 会话详情/删除 |
| `/api/agent/memory/{session_id}/messages` | GET | 会话消息 |

### 用户认证（auth_service）
| 端点 | 方法 | 说明 |
|----------|--------|-------------|
| `/api/auth/register` | POST | 邮箱注册 |
| `/api/auth/login` | POST | 登录（返回 JWT） |
| `/api/auth/refresh` | POST | Token 刷新 |
| `/api/auth/me` | GET | 当前用户信息 |
| `/api/auth/logout` | POST | 登出 |
| `/api/auth/change-password` | POST | 修改密码 |
| `/api/auth/set-password` | POST | 设置密码（OAuth 用户） |
| `/api/auth/oauth/{provider}/login` | GET | OAuth 登录（微信/Google） |
| `/api/auth/oauth/{provider}/callback` | GET | OAuth 回调 |
| `/api/admin/users` | GET | 用户列表（admin） |
| `/api/admin/users/{id}` | DELETE | 删除用户（admin） |
| `/api/admin/users/{id}/reactivate` | POST | 恢复用户（admin） |

### 舆情雷达（radar_service）
| 端点 | 方法 | 说明 |
|----------|--------|-------------|
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
| `/api/topic/{id}` | GET | 话题详情 |
| `/api/topic/{id}/process` | POST | 处理话题 |
| `/api/topic_evolution` | GET | 话题演变 |
| `/api/topic_evolution/migrate_clusters` | POST | 迁移聚类 |
| `/api/topic_stats` | GET | 话题统计 |
| `/api/volume_stats` | GET | 声量统计 |
| `/api/today_summary` | GET | 今日 AI 摘要 |
| `/rss/{token}.xml` | GET | RSS 订阅源 |

### 推送配置
| 端点 | 方法 | 说明 |
|----------|--------|-------------|
| `/api/push/configs` | GET | 所有推送配置 |
| `/api/push/config/{channel}` | GET/POST | 获取/保存通道配置 |
| `/api/push/test` | POST | 测试推送通道 |

### 模型配置
| 端点 | 方法 | 说明 |
|----------|--------|-------------|
| `/api/llm/configs` | GET | 所有模型配置（含默认回退） |
| `/api/llm/config/{agent}` | POST | 更新 Agent 模型配置 |
| `/api/llm/test/{agent}` | POST | 测试 Agent 连通性 |

### 订阅管理（subscription_service）
| 端点 | 方法 | 说明 |
|----------|--------|-------------|
| `/api/subscriptions` | GET/POST | 订阅列表/创建 |
| `/api/subscriptions/{id}` | GET/DELETE | 订阅详情/删除 |
| `/api/model-configs` | GET | 模型配置 |
| `/api/model-configs/{role}` | PUT/DELETE | 更新/删除模型配置 |
| `/api/quota` | GET | 配额查询 |
| `/api/admin/stats` | GET | Admin 统计 |
| `/api/admin/users/{id}` | GET | 用户详情（admin） |
| `/api/admin/users/{id}/quota` | GET/PUT | 用户配额（admin） |
| `/api/admin/users/{id}/deactivate` | POST | 停用用户（admin） |
| `/api/admin/users/{id}/role` | POST | 修改角色（admin） |

### Admin Agent 监控
| 端点 | 方法 | 说明 |
|----------|--------|-------------|
| `/api/admin/agents/overview` | GET | Agent/系统/工作流概览 |
| `/api/admin/agents/tools` | GET | 按工具统计健康度 |
| `/api/admin/agents/sessions` | GET | 活跃会话列表 |
| `/api/admin/agents/diagnosis` | GET | 诊断事件日志 |
| `/api/admin/agents/memory` | GET | 记忆统计 |
| `/api/admin/agents/report` | GET | LLM 健康巡检报告 |
| `/api/admin/agents/report/daily` | GET | 24h 运维日报（LLM 生成） |
| `/api/admin/agents/chat` | POST | 自然语言查询系统状态 |
| `/api/admin/agents/workflows` | GET | 工作流执行统计（多维过滤） |
| `/api/admin/agents/workflows/{id}` | GET | 单工作流执行历史 |
| `/api/admin/agents/workflows/{id}/trend` | GET | 工作流趋势分析 |
| `/api/admin/agents/workflows/{id}/cancel` | POST | 取消工作流（admin） |
| `/api/admin/agents/planning` | GET | 规划阶段统计 |
| `/api/admin/agents/ws` | WS | 实时监控 WebSocket |

### 网关
| 端点 | 方法 | 说明 |
|----------|--------|-------------|
| `/metrics` | GET | Prometheus 指标 |
| `/health` | GET | 健康检查（含 scheduler 状态） |

## AI 助手

AI 助手拥有 **50+ Function Calling 工具**，分 9 组，三层架构：

| 层级 | 分组 | 工具数 | 用途 |
|-------|-------|-------|---------|
| **原子层** | H（atomic） | 13 | 基础操作：搜索、过滤、聚类、情感分析、比较、报告 |
| **组合层** | I（composite） | 4 | 编排多步工作流，动态注册 |
| **查询层** | — | 3 | 管线专用查询（攻略/追星/简报） |
| **传统层** | A-G | ~30 | 订阅、扫描、数据查询、推送、模型、系统管理 |

### 工具分组

| 分组 | 工具数 | 用途 |
|-------|-------|---------|
| A | 5 | 订阅管理 + 意图解析 |
| B | 6+ | 扫描/调度控制（触发、暂停、恢复、状态查询） |
| C | 3 | 数据查询 + 网络搜索 |
| D | 4 | 推送通道管理（邮件/企微/飞书） |
| E | 3 | 模型配置 |
| F | — | 预留 |
| G | 1 | 系统状态 |
| H（原子层） | 13 | `search_posts`、`filter_content`、`cluster_related`、`extract_slots`、`compare_opinions`、`generate_itinerary`、`analyze_sentiment`、`calc_velocity`、`compare_platforms`、`query_report`、`push_report`、`list_workflows`、`manage_workflow` |
| I（组合层） | 4 | `deep_analyze_topic`、`quick_guide`、`scan_and_alert`、`briefing_digest` |

### 核心能力

- **智能规划**：`phase_plan` 自动分解复杂多步请求，支持约束提取、模板复用、LLM 步骤生成
- **进度感知**：执行循环注入进度提示（第 N 步/共 M 步），防止 LLM 长链漂移
- **动态调整**：执行结果异常时 `_maybe_adjust_plan` 重写剩余步骤
- **用户工作流**：自然语言创建定时工作流（"每天早上 9 点扫蔚来舆情"），统一 `workflows` 表 + cron 调度
- **取消支持**：三层取消（Agent SSE / Pipeline / 爬虫），资源自动释放

## 模型配置机制

每个 Agent 角色可独立配置模型，未配置时自动回退到**默认模型**：

| 角色 | 用途 |
|------|------|
| 默认模型 | 所有 Agent 的兜底配置 |
| 分析员 | 舆情风险分析 |
| 复核员 | 交叉复核判定 |
| 向量引擎 | 文本聚类（BGE-M3） |
| 视觉引擎 | 图片证据解析（Qwen-VL） |

## 配置说明

关键环境变量（`.env`）：

```env
# LLM API 密钥
DEFAULT_API_KEY=sk-...
ANALYST_API_KEY=sk-...

# 认证
JWT_SECRET=your-secret-32bytes-min
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# 部署
ENV=dev|prod
ALLOWED_ORIGINS=https://your-domain.com
```

完整配置参考 `.env.production.example`。

## License

MIT
