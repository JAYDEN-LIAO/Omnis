# Omnis — 部署指南

> 部署已通过 CI/CD 自动化（GitHub Actions），本文档仅供架构参考。
> 实际部署由 push-to-main 自动触发，无需手动操作。

---

## 1. 架构总览

```
                Internet
                   │
                   ▼
        ┌─────────────────────┐
        │  Nginx (aaPanel)    │   端口 443（HTTPS）
        │  TLS 终止 + 反代    │   域名 omnis.jaydennn.xyz
        └─────────┬───────────┘
                  │
        ┌─────────▼───────────┐
        │  omnis-api          │   systemd 服务
        │  FastAPI + Uvicorn  │   端口 8010（仅 localhost）
        │  /www/.../omnis_    │
        │  backend/           │
        └─────────┬───────────┘
                  │
        ┌─────────▼───────────┐
        │  SQLite + Qdrant    │   本地存储
        │  backend/data/      │
        └─────────────────────┘

前端静态文件托管于 /www/wwwroot/omnis.jaydennn.xyz/
```

## 2. CI/CD 自动部署

### 触发方式

推送代码到 `main` 分支，GitHub Actions 自动执行：

1. **构建前端** — `npm ci` + `STATIC_EXPORT=true npm run build`
2. **上传前端** — scp 到服务器 `/www/wwwroot/omnis.jaydennn.xyz/`
3. **同步后端** — 服务器端 `git pull` + `pip install -r requirements.txt`
4. **重启服务** — `systemctl restart omnis-api`
5. **健康检查** — 轮询 `/health` 端点，最多 15 次重试

### 所需 GitHub Secrets

| Secret | 用途 |
|--------|------|
| `SSH_HOST` | 服务器 IP |
| `SSH_PORT` | SSH 端口 |
| `SSH_USER` | 部署用户 |
| `SSH_KEY` | SSH 私钥 |

## 3. 服务器目录结构

```
/www/wwwroot/
├── omnis.jaydennn.xyz/       # 前端静态文件（CI/CD 自动推送）
│   └── index.html
└── omnis_backend/            # 后端代码（git clone）
    ├── backend/
    │   ├── gateway/main.py
    │   ├── core/
    │   ├── services/
    │   │   ├── auth_service/
    │   │   ├── agent_service/
    │   │   ├── platform_service/
    │   │   ├── subscription_service/
    │   │   └── admin_service/
    │   └── data/             # SQLite + Qdrant（持久化）
    ├── .env                  # 环境变量（手动配置）
    ├── venv/                 # Python 虚拟环境
    └── requirements.txt
```

## 4. 服务管理

```bash
# 状态查看
systemctl status omnis-api

# 重启
sudo systemctl restart omnis-api

# 查看日志
journalctl -u omnis-api -n 100 --no-pager
journalctl -u omnis-api -f

# 应用日志
tail -f /www/wwwroot/omnis_backend/logs/*.log
```

## 5. 健康检查

| 端点 | 说明 |
|------|------|
| `https://omnis.jaydennn.xyz/health` | 后端存活检查 |
| `https://omnis.jaydennn.xyz/api/*` | 业务 API |

## 6. 手动部署（备用）

仅当 CI/CD 不可用时参考：

```bash
# 前端
cd frontend/web
npm ci
STATIC_EXPORT=true npm run build
# 将 out/ 目录 scp 到服务器

# 后端
ssh <user>@<host>
cd /www/wwwroot/omnis_backend
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart omnis-api
```

## 7. 数据备份

```bash
# 备份数据库和向量数据
cp /www/wwwroot/omnis_backend/backend/data/*.db /backup/
cp -r /www/wwwroot/omnis_backend/backend/data/qdrant /backup/
```

---

> 首次部署需手动完成：服务器初始化、`.env` 配置、`systemd` 服务注册、Nginx 反代配置。
> 首次部署后，日常更新全由 CI/CD 自动处理。
