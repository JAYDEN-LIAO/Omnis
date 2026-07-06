# Omnis

媒体信息智能平台。基于 Multi-Agent 架构，实现跨平台信息采集、智能分析、工作流自动化与多通道预警推送。

## 技术栈

- **后端**: FastAPI, SQLite, APScheduler, OpenAI SDK
- **前端**: Next.js 15, React 18, Tailwind v4, shadcn/ui
- **AI**: DeepSeek（主力）、Kimi（辅助）、Qwen-VL（视觉）
- **爬虫**: Playwright / Selenium
- **部署**: systemd + Nginx, GitHub Actions CI/CD

## 架构

5 个 service，单向依赖，无循环导入：

```
用户 → Agent (agent_service) → 工具 → LLM / 爬虫 / 数据库
  │
  └── 平台能力 (platform_service)
       → 前端 API / 调度器 / 推送（邮件/企微/飞书/RSS）
```

| 服务 | 职责 |
|------|------|
| `auth_service` | 注册、登录、OAuth、JWT、邀请码 |
| `agent_service` | AI 智能体编排、24 个原子工具、工作流引擎 |
| `platform_service` | 前端 API、调度器、推送通道 |
| `subscription_service` | 订阅/模型配置/配额 API |
| `admin_service` | 用户管理、Agent 监控、运维引擎 |

## 快速启动

```bash
# 后端
python backend/gateway/main.py

# 前端
cd frontend/web && npm run dev
```

## 关键功能

- **AI 助手**: 流式对话，Agent 自动调用工具完成任务
- **工作台**: 预设工作流、最近运行、用户自定义定时任务
- **数据看板**: 系统概览、数据来源分布、活动流
- **多通道推送**: 邮件、企业微信、飞书、RSS
- **邀请码系统**: 新用户需 `KSKBL1027` 解锁系统 Key
- **安全**: TLS 1.2+、CSP 安全头、API Key 加密存储、暴力破解防护

## 目录结构

```
backend/
├── core/          → 基础设施（配置、日志、数据库、安全）
├── shared/        → 共享数据访问层
├── services/
│   ├── auth_service/      → 认证
│   ├── agent_service/     → AI 智能体（核心）
│   ├── platform_service/  → 平台能力
│   ├── subscription_service/ → 订阅/配额
│   └── admin_service/     → 管理
├── gateway/main.py        → FastAPI 入口
└── data/                  → SQLite + Qdrant
```
