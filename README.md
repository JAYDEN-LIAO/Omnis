# Omnis

AI-powered media intelligence platform. Cross-platform information collection, agent-driven analysis, workflow automation, and multi-channel alerting.

## Tech Stack

- **Backend**: FastAPI, SQLite, APScheduler, OpenAI SDK
- **Frontend**: Next.js 15, React 18, TypeScript, Tailwind v4, shadcn/ui
- **Agents**: DeepSeek (primary), Kimi (auxiliary), Qwen-VL (vision)
- **Crawler**: Playwright/Selenium
- **Deployment**: systemd + Nginx, GitHub Actions CI/CD

## Architecture

```
User → Agent (agent_service) → Tools → LLM / Crawler / Database
  │                              │
  └── Works Platform (platform_service)
       → Frontend APIs / Scheduler / Push Notifications
```

5 services with **unidirectional dependencies**:
- `auth_service` — Registration, login, OAuth, JWT, invite codes
- `agent_service` — AI agent orchestration, 24 atomic + 4 composite tools, workflow engine
- `platform_service` — Frontend APIs, scheduler, push (email/WeCom/Feishu/RSS)
- `subscription_service` — Subscription/model/quota management APIs
- `admin_service` — User management, agent monitoring, ops engine

## Quick Start

```bash
# Backend
python backend/gateway/main.py

# Frontend
cd frontend/web && npm run dev
```

## Key Features

- **AI Agent Chat**: Streaming conversation with tool-calling agent
- **Workspace**: Preset workflows, recent runs, user-defined cron workflows
- **Dashboard**: System overview, data source distribution, activity feed
- **Smart Alerts**: Multi-channel push via email, WeCom, Feishu, RSS
- **Invite System**: New users need invite code `KSKBL1027` to unlock system API keys
- **Security**: TLS 1.2+, CSP headers, encrypted API keys, brute force protection

## Directory Structure

```
backend/
├── core/          → Infrastructure (config, logger, database, security)
├── shared/        → Shared data access layer
├── services/
│   ├── auth_service/      → User authentication
│   ├── agent_service/     → AI agent (core)
│   ├── platform_service/  → Platform capabilities
│   ├── subscription_service/ → Subscription/quota API
│   └── admin_service/     → Admin management
├── gateway/main.py        → FastAPI entry point
└── data/                  → SQLite + Qdrant
```
