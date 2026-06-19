# MediaRadar

Multi-platform social media monitoring, AI-powered opinion analysis, and intelligent alerting system.

MediaRadar is a full-stack platform that crawls content from Chinese social media (Weibo, Xiaohongshu, Bilibili, etc.), analyzes it with a multi-agent LLM pipeline, and delivers actionable intelligence via email/WeCom/Feishu/RSS.

## Architecture

### 3-Layer Agent Architecture (v2.0)

```
User Input
     │
     ▼
┌──────────────────────────────────┐
│  phase_plan (Planning Layer)    │
│  • Constraint extraction        │
│  • Template matching            │
│  • LLM task decomposition       │
│  • Dynamic adjustment           │
│                                  │
│  mode=immediate ──────┐         │
│  mode=scheduled ──────┼──┐      │
└───────────────────────┼──┼──────┘
          │             │  │
          ▼             │  ▼
     Execution Loop     │  user_workflows
     • Progress hints   │  (APScheduler)
     • Cancel checkpoints│     │
     • Criticality       │     ▼
          │             │  execute_workflow_steps
          ▼             │
          │             │
          ▼             ▼
┌──────────────────────────────────┐
│  Tool Layer (50+ tools)         │
│                                  │
│  • Atomic tools (13)            │
│    search_posts · filter_content │
│    cluster_related · compare_   │
│    opinions · analyze_sentiment │
│    calc_velocity · push_report  │
│                                  │
│  • Preset workflows as tools (4)│
│    deep_analyze_topic (workflow) │
│    quick_guide (workflow)       │
│    scan_and_alert (workflow)    │
│    briefing_digest (workflow)   │
│                                  │
│  • Legacy management tools (~30)│
│    A: subscription · B: scan    │
│    C: query · D: push · E: model│
│    G: system status             │
└──────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────┐
│  Pipeline Internal Stages       │
│  (screener → vision → cluster   │
│   → LangGraph analysis → alert) │
└──────────────────────────────────┘
```

The system evolved from a reactive tool-calling loop into a **plan-driven architecture**: an intelligent planner decomposes complex requests, and the execution loop calls tools (including preset workflows registered as tools) to fulfill each step.

### Multi-Pipeline Support

Four pipeline modes, sharing the same Screener→Cluster→Analysis skeleton:

| Mode | Purpose | Analysis Sub-Graph |
|------|---------|-------------------|
| `full` | Risk sentiment monitoring | Analyst → Reviewer → Director |
| `guide` | Travel/guide content analysis | Extractor → Comparer → Summarizer |
| `celebrity` | Celebrity trend tracking | Sentiment → Heat → Aggregator |
| `briefing` | Daily news digest | Categorizer → Highlighter → Writer |

## Features

- **Multi-Platform Crawling** — Weibo, Xiaohongshu, Bilibili, Douyin, Kuaishou, Tieba, Zhihu
- **AI-Powered Analysis** — LangGraph pipeline with analyst/reviewer/director agents (DeepSeek + Kimi cross-validation)
- **Intelligent Planning** — Automatic task decomposition for complex multi-step requests (e.g., "compare Li Auto and NIO service discussions across Weibo and Xiaohongshu over the past week")
- **User Workflows** — Save, schedule (cron), and manage custom workflows via natural language
- **Multi-Channel Alerts** — Email, WeCom, Feishu push + RSS feed
- **Subscription Engine** — Per-user configurable subscriptions with type/polarity/sensitivity control
- **AI Chat Agent** — 50+ function-calling tools across 9 groups for natural language system control
- **Per-User Isolation** — Complete data, config, and alert separation
- **Interrupt Mechanism** — 3-layer cancellation (Agent SSE / Pipeline / Crawler) with resource cleanup
- **Admin Monitoring** — Real-time agent metrics, workflow execution logs, trend analysis, LLM-powered health reports
- **Web Dashboard** — Next.js 15 + shadcn/ui + Framer Motion
- **WeChat Mini Program** — uni-app (Vue 3) mobile client
- **Observability** — Prometheus metrics (LLM calls, pipeline duration, agent turns, workflow executions)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLite |
| AI/LLM | LangGraph, DeepSeek, Kimi, Qwen-VL, BGE-M3 |
| Crawler | Playwright, httpx |
| Frontend (Web) | Next.js 15, Tailwind CSS 4, shadcn/ui (Radix + Base UI), Framer Motion |
| Frontend (Mobile) | uni-app (Vue 3) |
| Auth | JWT (HS256), bcrypt, Google OAuth 2.0 |
| Scheduler | APScheduler |
| Monitoring | Prometheus, custom Admin Agent Monitor |
| Vector | HDBSCAN clustering, text embeddings |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+

### Backend

```bash
pip install -r requirements.txt
cp .env.example .env   # Edit with your API keys
python backend/gateway/main.py   # API at http://localhost:8008
```

### Web Frontend

```bash
cd frontend/web
npm install
npm run dev   # UI at http://localhost:3003
```

### Mini Program

```bash
cd frontend/MiniApp
npm install
# Open with HBuilder X or Weixin DevTools
```

## Project Structure

```
backend/
├── gateway/main.py              # FastAPI entry (port 8008, mounts all routers)
├── core/                        # Shared infrastructure
│   ├── config.py                # 3-tier config fallback
│   ├── auth*.py                 # JWT, user CRUD, auth deps, login lockout
│   ├── database.py              # SQLite connection management
│   ├── metrics.py               # Prometheus metrics (incl. workflow/plan counters)
│   ├── circuit_breaker.py       # Per-tool LLM circuit breaker
│   ├── logger.py                # Structured JSON logging
│   ├── sanitize.py              # HTML/URL sanitization
│   ├── security_middleware.py   # Security headers + body size limit
│   ├── rate_limiter.py          # Rate limiter
│   ├── subscription_db.py       # Subscription CRUD (per-owner)
│   ├── quota_db.py              # Per-user quota management
│   ├── model_config_db.py       # Per-agent-role model config with fallback
│   └── agent_memory_db.py       # Session memory persistence
├── services/
│   ├── agent_service/           # AI chat agent (core of v2.0 upgrade)
│   │   ├── agent_core.py        # Planning engine + execution loop + CancelRegistry
│   │   ├── sse.py               # SSE event factory (text/tool_call/plan/progress)
│   │   ├── workflows_db.py      # Unified workflow storage (preset/auto_template/user)
│   │   ├── tools/               # 50+ function-calling tools in 9 groups
│   │   │   ├── atomic.py        # H group: 13 atomic tools
│   │   │   ├── composite.py     # I group: 4 composite tools (dynamic registration)
│   │   │   ├── subscription.py  # A group: subscription management
│   │   │   ├── scan.py          # B group: scan/schedule control
│   │   │   ├── query.py         # C group: data query + web search
│   │   │   ├── push.py          # D group: push channel management
│   │   │   ├── model.py         # E group: model configuration
│   │   │   ├── system.py        # G group: system status
│   │   │   ├── guide.py         # Guide pipeline query tool
│   │   │   ├── celebrity.py     # Celebrity pipeline query tool
│   │   │   ├── briefing.py      # Briefing pipeline query tool
│   │   │   ├── sentiment_dict.py# Domain sentiment dictionary
│   │   │   ├── _base.py         # @tool decorator + registration
│   │   │   └── _owner.py        # @with_owner owner_id injection
│   │   └── memory/              # Session memory (jieba + TTL cache)
│   ├── radar_service/           # Opinion monitoring engine
│   │   ├── pipeline.py          # Pipeline orchestrator (4 modes, PipelineCanceller)
│   │   ├── llm_gateway.py       # LangGraph analysis sub-graph
│   │   ├── analysis_graph*.py   # 4 analysis sub-graphs (risk/guide/celebrity/briefing)
│   │   ├── pipeline_configs.py  # Pipeline config builders
│   │   ├── prompt_templates.py  # Screener prompts + PLAN_PROMPT
│   │   ├── scheduler.py         # APScheduler (scan + daily summary + user workflows)
│   │   ├── db_manager.py        # SQLite operations
│   │   ├── push_generator.py    # HTML email templates
│   │   └── notifier/            # Alert push channels (email/wecom/feishu/rss)
│   ├── auth_service/            # Multi-user auth & OAuth
│   │   └── oauth_providers/     # Google OAuth
│   ├── subscription_service/    # Subscription/quota/admin API
│   ├── admin_service/           # Agent monitoring & ops
│   │   ├── agent_monitor.py     # Prometheus aggregation layer
│   │   ├── agent_health_db.py   # Diagnosis events + workflow execution logs
│   │   ├── agent_ops.py         # LLM-powered health scans / daily reports
│   │   └── api.py               # REST endpoints + WebSocket
│   ├── search_lib/              # Search library
│   └── crawler_service/         # Platform crawlers (independent module)
frontend/
├── web/                         # Next.js 15 dashboard (port 3003)
│   ├── app/(app)/               # Authenticated routes
│   │   ├── dashboard/           # Stats + charts (Recharts)
│   │   ├── agent/               # AI chat interface (SSE streaming)
│   │   ├── yq-list/             # Opinion list (TanStack Table + Virtual)
│   │   └── settings/            # Account / LLM / Push / System
│   └── components/
│       ├── layout/              # Sidebar + Topbar
│       ├── ui/                  # shadcn/ui components
│       └── charts/              # Chart wrappers
└── MiniApp/                     # uni-app mobile client
upgrade2.0/                      # v2.0 upgrade design documents
deploy/                          # Deployment configs
scripts/                         # Verification test scripts
```

## API Overview

### AI Agent (`agent_service`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agent/chat` | POST | AI chat (SSE stream: text/tool_call/tool_progress/plan/done) |
| `/api/agent/chat/{session_id}/cancel` | POST | Cancel running session |
| `/api/agent/workflows/{workflow_id}/cancel` | POST | Cancel running workflow |
| `/api/agent/memory` | GET | Session list |
| `/api/agent/memory/{session_id}` | GET/DELETE | Session detail/delete |
| `/api/agent/memory/{session_id}/messages` | GET | Session messages |

### Auth (`auth_service`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | Email/password registration |
| `/api/auth/login` | POST | Login (returns JWT) |
| `/api/auth/refresh` | POST | Token refresh |
| `/api/auth/me` | GET | Current user info |
| `/api/auth/logout` | POST | Logout |
| `/api/auth/change-password` | POST | Change password |
| `/api/auth/set-password` | POST | Set password (OAuth users) |
| `/api/auth/oauth/{provider}/login` | GET | OAuth login (WeChat/Google) |
| `/api/auth/oauth/{provider}/callback` | GET | OAuth callback |
| `/api/admin/users` | GET | User list (admin) |
| `/api/admin/users/{id}` | DELETE | Delete user (admin) |
| `/api/admin/users/{id}/reactivate` | POST | Reactivate user (admin) |

### Radar (`radar_service`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/radar_status` | GET | Radar running status |
| `/api/start_task` | POST | Trigger full scan |
| `/api/yq_list` | GET | Opinion list |
| `/api/settings` | GET/POST | System config (keywords/platforms) |
| `/api/circuit/states` | GET | Circuit breaker status |
| `/api/mcp/health` | GET | MCP health |
| `/api/scheduler/start` | POST | Start APScheduler |
| `/api/scheduler/stop` | POST | Stop scheduler |
| `/api/scheduler/status` | GET | Scheduler status |
| `/api/topic_list` | GET | Topic list |
| `/api/topic/{id}` | GET | Topic detail |
| `/api/topic/{id}/process` | POST | Process topic |
| `/api/topic_evolution` | GET | Topic evolution |
| `/api/topic_evolution/migrate_clusters` | POST | Migrate clusters |
| `/api/topic_stats` | GET | Topic statistics |
| `/api/volume_stats` | GET | Volume statistics |
| `/api/today_summary` | GET | Today's AI summary |
| `/rss/{token}.xml` | GET | RSS feed |

### Push Config
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/push/configs` | GET | All push configs |
| `/api/push/config/{channel}` | GET/POST | Get/save channel config |
| `/api/push/test` | POST | Test push channel |

### Model Config
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/llm/configs` | GET | All model configs (with fallback) |
| `/api/llm/config/{agent}` | POST | Update agent model config |
| `/api/llm/test/{agent}` | POST | Test agent connectivity |

### Subscription (`subscription_service`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/subscriptions` | GET/POST | List/create subscriptions |
| `/api/subscriptions/{id}` | GET/DELETE | Subscription detail/delete |
| `/api/model-configs` | GET | Model configs |
| `/api/model-configs/{role}` | PUT/DELETE | Update/delete model config |
| `/api/quota` | GET | Quota info |
| `/api/admin/stats` | GET | Admin statistics |
| `/api/admin/users/{id}` | GET | User detail (admin) |
| `/api/admin/users/{id}/quota` | GET/PUT | User quota (admin) |
| `/api/admin/users/{id}/deactivate` | POST | Deactivate user (admin) |
| `/api/admin/users/{id}/role` | POST | Change role (admin) |

### Admin Agent Monitoring
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/agents/overview` | GET | Agent/system/workflow overview |
| `/api/admin/agents/tools` | GET | Per-tool health stats |
| `/api/admin/agents/sessions` | GET | Active sessions |
| `/api/admin/agents/diagnosis` | GET | Diagnosis event log |
| `/api/admin/agents/memory` | GET | Memory statistics |
| `/api/admin/agents/report` | GET | LLM-generated health scan report |
| `/api/admin/agents/report/daily` | GET | 24h ops daily report (LLM) |
| `/api/admin/agents/chat` | POST | Natural language query of system state |
| `/api/admin/agents/workflows` | GET | Workflow execution stats (multi-dimension filter) |
| `/api/admin/agents/workflows/{id}` | GET | Single workflow execution history |
| `/api/admin/agents/workflows/{id}/trend` | GET | Workflow trend analysis |
| `/api/admin/agents/workflows/{id}/cancel` | POST | Cancel running workflow (admin) |
| `/api/admin/agents/planning` | GET | Planning stage statistics |
| `/api/admin/agents/ws` | WS | Real-time monitoring WebSocket |

### Gateway
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/metrics` | GET | Prometheus metrics |
| `/health` | GET | Health check (incl. scheduler status) |

## AI Agent

The AI assistant has **50+ function-calling tools** across 9 groups, organized in a 3-layer hierarchy:

| Layer | Group | Tools | Purpose |
|-------|-------|-------|---------|
| **Atomic** | H (atomic) | 13 | Primitive operations: search, filter, cluster, sentiment, compare, report |
| **Composite** | I (composite) | 4 | Orchestrated multi-step workflows registered dynamically |
| **Query** | — | 3 | Pipeline-specific queries (guide/celebrity/briefing reports) |
| **Legacy** | A-G | ~30 | Subscription, scan, data query, push, model, system management |

### Tool Groups

| Group | Tools | Purpose |
|-------|-------|---------|
| A | 5 | Subscription management + intent parsing |
| B | 6+ | Scan/schedule control (trigger, pause, resume, crawl status) |
| C | 3 | Data query + web search |
| D | 4 | Push channel management (email/wecom/feishu) |
| E | 3 | Model configuration |
| F | — | Reserved |
| G | 1 | System status |
| H (atomic) | 13 | `search_posts`, `filter_content`, `cluster_related`, `extract_slots`, `compare_opinions`, `generate_itinerary`, `analyze_sentiment`, `calc_velocity`, `compare_platforms`, `query_report`, `push_report`, `list_workflows`, `manage_workflow` |
| I (composite) | 4 | `deep_analyze_topic`, `quick_guide`, `scan_and_alert`, `briefing_digest` |

### Key Capabilities

- **Intelligent Planning**: Complex multi-step requests are automatically decomposed by `phase_plan` with constraint extraction, template reuse, and LLM-based step generation
- **Progress Awareness**: The execution loop injects progress hints with remaining steps, preventing LLM drift in long chains
- **Dynamic Adjustment**: If a step returns unexpected results, `_maybe_adjust_plan` rewrites remaining steps
- **User Workflows**: Users can create custom workflows via natural language ("scan NIO every morning at 9am and alert me"), stored in the unified `workflows` table with cron scheduling
- **Cancel Support**: 3-layer cancellation (Agent SSE / Pipeline / Crawler) with resource cleanup

## Model Configuration

Each agent role can be configured independently, with fallback to the **default model**:

| Role | Purpose |
|------|---------|
| Default | Fallback for all agents |
| Analyst | Risk level assessment |
| Reviewer | Cross-validation |
| Vector Engine | Text clustering (BGE-M3) |
| Vision Engine | Image evidence analysis (Qwen-VL) |

## Configuration

Key environment variables (`.env`):

```env
# LLM API Keys
DEFAULT_API_KEY=sk-...
ANALYST_API_KEY=sk-...

# Auth
JWT_SECRET=your-secret-32bytes-min
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Deployment
ENV=dev|prod
ALLOWED_ORIGINS=https://your-domain.com
```

See `.env.production.example` for full reference.

## License

MIT
