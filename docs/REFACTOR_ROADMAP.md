# Omnis 改造计划与优先级

> **基线日期**：2026-11-10
> **核查范围**：707 个受版本控制文件（后端 258 个 `.py` / 46,066 行、前端 99 个文件、部署与 CI 配置、项目文档）
> **核查方式**：全仓静态分析 + 关键证据逐条复核
> **未做的事**：未安装 Python/Node 依赖、未启动后端、未运行 `npm run build`、未执行任何 git 写操作
> **状态标记**：`未开始` / `进行中` / `已完成` / `阻塞`；每批完成后回到本文件更新状态

本文件是后续「依次改造」的唯一跟踪基线，负责回答「改什么、按什么顺序改、改到什么程度算完成」。**开工前必读根目录 `AGENTS.md`**，它负责回答「怎么改」：必跑命令、测试要求、提交规范、安全红线、状态回写与禁止事项。每项包含**现状证据 → 影响 → 改造动作 → 验收方式**，证据中的路径与行号以 2026-11-10 的代码为准。

---

## 0. 阅读前须知

### 0.1 与 `problem_i_met.md` 的关系

根目录 `problem_i_met.md` 写于重构之前，其主体事实已过时，**不要直接照它排期**：

| 文档条目 | 文档说法 | 当前代码实测 | 判定 |
|---|---|---|---|
| P1 上下文重建竞态 | 理想修复未实现 | `agent_service/agent_core.py:411,791,813` 仍为 `asyncio.create_task(_write_memory_async(...))`；`:277` 仍从 DB 重建 | 仍存在，见 #16 |
| P2 尾巴消息数硬编码 | N=6 未修 | `agent_core.py:280` `stored[-6:]`；`memory/memory_manager.py:189,240` 同 | 仍存在，见 #16 |
| P3 4 个 >900 行文件 | 全在 `radar_service/` | 该目录已不存在；>700 行文件 5 个，>900 行仅 `pipeline.py`(1143) | 数量不实，问题仍在，见 #13 |
| P4 15 处 `sys.path.append` | radar 8 / search_lib 2 / gateway 1 / crawler 4 | 代码实测 4 处 | 数量不实，清理未完成，见 #10 |
| P5 Plan Overfitting | 三层修复 | `agent_core.py:756` `key not in step_results`；`prompts.py` 已改「steps 默认为空」 | **已修复** |

`radar_service/` 已重构为 `platform_service/`；`db_manager.py` 已拆为 `platform_service/db/` 7 个文件；`push_generator.py` 的 HTML 已抽到 `templates/`。但 `api.py`(858 行) 与 `pipeline.py`(1143 行) 未按文档计划拆分，且后者迁到 `agent_service/` 后反而更长。

### 0.2 排序依据

1. **损失是否已发生** —— 凭据已入库、可被任意注册用户利用的漏洞排最前。
2. **可利用门槛** —— 一行 HTTP 请求即可触发的，高于需要特定时序或特定场景的。
3. **功能是否阻断** —— 调用即 `ImportError`、构建出不了包，高于体验问题。
4. **是否具备回归防护** —— 零测试 + 零 CI 门禁是上述所有问题能长期潜伏的根因。
5. **改造依赖** —— 大重构必须建立在可验证的基础上。

### 0.3 依赖与执行顺序

```
[#9 最小 smoke test] ──► [批次 1: P0 止血] ──► [批次 2: P1 恢复可运行]
                                                      │
                                                      ▼
                              [批次 3: P2 防回归] ──► [批次 4: P3 提质]
```

- **#9 是所有代码改造的安全网**，虽然排在第三批，但应在动手改 P0 之前先补一个最小可运行的 smoke test。
- 批次 1 内部建议顺序：#1（先止损）→ #2 → #3 → #4。
- 每批结束必须跑一次「本批验收」并记录结果，再进入下一批。
- `#13` 的 God 文件拆分风险最高，**必须**在 #9 的测试覆盖到位之后才动。
- **2026-11-10 流程基建已补齐**：新增根级 `AGENTS.md`，按 `next@15` 改写 `frontend/web/AGENTS.md`，`CLAUDE.md` 引用根级规范，清理 `.claude/settings.local.json` 的其他项目残留并加入 `.gitignore`。这属于 #9 与 #15 的**规范前置**；`tests/`、测试用例与 CI 门禁仍为 0，**#9 尚未完成，不得视为已有安全网**。

### 0.4 需要人工确认的外部动作

以下动作**不在本文件内自动执行**，需项目负责人明确确认后单独处理：

- `git rm -r --cached`（修改索引）、`git filter-repo` 等历史重写操作属于破坏性操作。
- 当前仓库是**公开仓库**，且本地为浅克隆（无历史）。已进入过远端历史的凭据应视为**已泄露**，清理当前树不等于消除风险。
- 需轮换：微博/微信登录态与 Cookie、系统 LLM API Key、SMTP 密码、JWT_SECRET、邀请码、RSS access_token。
- 轮换后需同步更新生产环境 `.env` 与 CI secrets。

---

## 1. 总览

| # | 批次 | 改造点 | 等级 | 状态 |
|---|------|--------|------|------|
| 1 | P0 | 清理已入库的登录态与运行日志 | 严重 | 未开始 |
| 2 | P0 | 封堵 SSRF 与系统 Key 外泄 | 严重 | 未开始 |
| 3 | P0 | 生产启动强校验（fail-fast / fail-closed） | 严重 | 未开始 |
| 4 | P0 | 修复授权链 4 处失效 + 调度器越权 | 严重 | 未开始 |
| 5 | P1 | 修复 22 处失效导入与 `ANALYST_*` 缺失 | 高 | 未开始 |
| 6 | P1 | 修复前端构建链（静态导出与 middleware 冲突） | 高 | 未开始 |
| 7 | P1 | 统一前端鉴权链路 | 高 | 未开始 |
| 8 | P1 | 部署配置归一化与 CI 原子发布 | 高 | 未开始 |
| 9 | P2 | 补最小 smoke test 与 CI 质量门禁 | 高 | 未开始 |
| 10 | P2 | 依赖清单与 Python 包边界 | 中 | 未开始 |
| 11 | P2 | 限流失效、中间件顺序、请求体限制 | 中 | 未开始 |
| 12 | P2 | 异常回显、日志脱敏、管理端点暴露 | 中 | 未开始 |
| 13 | P3 | 拆分 4 个 God 文件 | 中 | 未开始 |
| 14 | P3 | 假数据、假控件与高频轮询 | 低 | 未开始 |
| 15 | P3 | 文档治理与死配置清理 | 低 | 未开始 |
| 16 | P3 | 已知问题收尾（上下文竞态、尾巴 N=6） | 低 | 未开始 |

---

## 2. 批次 1：P0 止血

### #1 清理已入库的登录态与运行日志

**现状证据**

- `git ls-files | grep -c 'browser_data/'` = **258**，路径 `backend/services/crawler_service/browser_data/wb_user_data_dir/`，含 `Default/Network/Cookies`(57 KB)、`Default/Login Data`(51 KB)、`Default/History`(262 KB)、`Local State`；历史记录含微博 passport 与微信二维码登录 URL。
- `git ls-files logs` = **16 个文件，约 4.65 MB**，含真实邮箱与用户 ID；单个 `logs/gateway/gateway-2026-06-13.log.2026-06-13` 达 3.46 MB。
- `.gitignore:143` 忽略 `browser_data/`、`:176-177` 忽略 `logs/**/*.log`，但**对已跟踪文件无效**；轮转日志后缀 `.log.2026-06-13` 也不匹配 `*.log`。

**影响**：任何能 clone 仓库的人可获取真实会话 Cookie 与登录数据；日志泄露内部账号信息、路径与调用栈。

**改造动作**

- [ ] `git rm -r --cached backend/services/crawler_service/browser_data/` 与 `git rm -r --cached logs/`（需确认）
- [ ] `.gitignore` 改为整目录 `logs/`、补 `*.log.*`；`browser_data/` 规则保留
- [ ] 爬虫 profile 改为运行时临时目录，启动脚本不再复用已提交目录
- [ ] 按 0.4 轮换全部相关凭据；远端历史重写单独评估

**验收**：`git ls-files | grep -c browser_data/` 与 `git ls-files logs | wc -l` 均为 0；`.gitignore` 覆盖 `*.log.*`；爬虫仍能以临时 profile 启动。

---

### #2 封堵 SSRF 与系统 API Key 外泄

**现状证据**

- `backend/services/platform_service/api.py:798-818`：`/api/llm/test/{agent}` 的 `base_url` 完全来自请求体，`api_key` 回退到 `get_effective_config()` 中的系统默认 Key，然后 `requests.post(f"{base_url}/chat/completions", headers={"Authorization": f"Bearer {api_key}"})`。无 scheme/主机白名单、无私网黑名单、允许重定向。
- `:823-825` 回显 `resp.text[:100]` 与 `str(e)`。
- `/api/push/config/{channel}` (`:660,662`)、`/api/push/test` (`:684`) 的 `webhook_url` / `smtp_host` 同样无校验；`notifier/channel_wecom.py:38`、`channel_feishu.py:80,145`、`channel_email.py:37` 直接发起连接。
- `platform_service/db/db_push.py:78`：`smtp_password` 明文写入 `config_json`。

**影响**：任意注册用户可把系统 LLM Key 发到自己的服务器，或探测内网 / 云元数据；SMTP 凭据投递；推送密码明文落库。

**改造动作**

- [ ] 抽出统一出站 URL 校验：仅 https、域名白名单、解析后拒绝私网/环回/链路本地/169.254.0.0/16、禁重定向、防 DNS rebinding
- [ ] `/api/llm/test` 禁止回退使用系统默认 Key，测试必须显式提供自有 Key
- [ ] webhook / SMTP 主机同样走白名单校验
- [ ] `smtp_password` 复用 `crypto_utils` 加密，读取时脱敏
- [ ] 统一错误文案，不回显上游响应与异常

**验收**：对 `base_url=http://127.0.0.1:9`、`http://169.254.169.254`、外部域名分别返回明确拒绝；单元测试覆盖白名单内外与 DNS 解析结果。

---

### #3 生产启动强校验

**现状证据**

- `backend/gateway/main.py:179-195`：`ENV=prod` 且 `ALLOWED_ORIGINS` 为空时 `logger.warning` 后回退 `_origins=["*"]`，同时 `_credentials=True`、`allow_methods/headers=["*"]`。
- `core/config.py:156-166` 只校验密钥长度，默认弱值 `dev-secret-change-me-in-prod-please-32bytes` 长 44 字符可顺利通过；`gateway/main.py:277-289` 的弱密钥检查只在 `if __name__ == "__main__"` 分支打印 stderr，`uvicorn` 导入 `app` 时不执行；`JWT_ALGORITHM` 无白名单（`config.py:102`）。
- `core/crypto_utils.py:52` 直接读 `os.getenv("JWT_SECRET")`，而 `config.py:147-148` 在 dev 下自动生成的临时密钥只写进 `settings`、不回写环境变量 → `_get_fernet()` 返回 None → `:79,93,103` 降级为明文存储/返回密文当明文。
- `shared/db/model_config_db.py:196-203` 权限检查异常时 `return True`（fail-open）。
- `gateway/main.py:146-151` prod 未关闭 Swagger；`:221-224` `/metrics` 无鉴权；`:232-276` `/health` 回显 `str(e)`；`core/security_middleware.py:39-51` 让 `/docs` 等路径跳过全部安全头。

**影响**：伪造 admin JWT、API Key 明文落库、任意源带凭证跨域、内部信息暴露——多处防护写了但生产不生效。

**改造动作**

- [ ] `ENV=prod` 时 `ALLOWED_ORIGINS` 为空直接 `raise RuntimeError`；校验每个 origin 为 https 且不含通配/路径
- [ ] 弱值/短密钥/空值/算法白名单统一放进 `_validate_jwt_secret()`，prod 一律 raise；删除 `__main__` 软警告
- [ ] 加密与权限检查改为 fail-closed；`crypto_utils` 从 `settings` 取密钥
- [ ] prod 关闭 `docs_url/redoc_url/openapi_url`；`/metrics` 加鉴权或只绑内网；`/health` 只返回 ok/fail

**验收**：构造空 `ALLOWED_ORIGINS`、默认 JWT_SECRET、缺失加密密钥三种启动场景，prod 下均拒绝启动；正常配置可启动。

---

### #4 修复授权链失效

**现状证据**

- `auth_service/db/__init__.py:458` `INVITE_CODE_PRESET = "KSKBL1027"`，`:467-469` 插入时 `max_uses=0`（`:517` 判定为不限次），`:546` 兑换后 `UPDATE users SET has_system_access = 1`。该码在 README、CLAUDE.md、功能清单中公开。
- `auth_service/db/__init__.py:57-65` `_migrate_existing_users_access()` 每次执行 `UPDATE users SET has_system_access = 1 WHERE ... = 0`，`:145` 由 `init_auth_tables()` 调用，后者在 `auth_service/api.py:37` 模块导入时执行 → **每次启动给全体用户提权**。
- `auth_service/deps.py:40,81,120` `decode_token(token)` 未传 `expected_type`；`jwt.py:107-117` 仅在显式传入时才拒绝 `type="refresh"` → 7 天有效的 refresh token 可当 access 用于所有接口。
- `platform_service/db/db_push.py:116-131` 用 `config_json LIKE '%token%' ESCAPE '\'` 子串匹配定位 owner；`api.py:660` 的 rss token 由用户任意指定；`api.py:832-848` `/rss/{token}.xml` 无 JWT 依赖。
- `platform_service/api.py:78-90` `/api/scheduler/start|stop` 仅用 `require_registered_user`（只拒绝 guest），对比同文件 `:352` 的管理端点用 `require_admin`。

**影响**：配额与邀请码体系被完全绕过；refresh token 生命周期失效；单字符 token 即可越权读取他人话题数据；任意用户可停全局调度器。

**改造动作**

- [ ] 移除预设邀请码，改为部署时生成入库；`max_uses` 有限值 + 原子条件 UPDATE 扣减
- [ ] 全量提权迁移改为带 schema version 的一次性迁移，从 `init_auth_tables()` 移除
- [ ] `deps.py` 三个入口统一 `decode_token(token, expected_type="access")`；`revoke_token` 同步
- [ ] RSS 改为 `json_extract(config_json,'$.access_token') = ?` 精确匹配；token 由 `secrets.token_urlsafe(32)` 服务端生成，加唯一索引
- [ ] 调度器启停改为 `Depends(require_admin)`；顺带修 `agent_service/api.py:157-164` 的 cancel 越权（按 `(owner_id, session_id)` 校验）

**验收**：兑换第二次邀请码失败；重启后新用户仍无系统权限；refresh token 调受保护接口返回 401；`/rss/a.xml` 无法命中任何用户；普通用户调 scheduler 返回 403。

---

## 3. 批次 2：P1 恢复可运行

### #5 修复失效导入与缺失配置

**现状证据（实证，非推断）**

- `agent_service/pipeline.py:29-34` 顶层 `from .llm_gateway import call_llm`、`from .analysis_graph import analyze_and_report`、`from .llm.prompts import ...`、`from .analysis.topic_aggregator import ...`；已确认 `agent_service/` 下 `llm_gateway.py`、`analysis_graph.py`、`llm/`、`analysis/` **全部不存在**。
- 同类断链共 **22 处**，其中 6 处在模块顶层且无 try 兜底（`pipeline.py:29,32,33,34`、`embed_cluster.py:20`、`platform_service/analysis/topic_aggregator.py:22`）。
- 触发点：`tools/atomic_data.py:284,322` 的 Screener/Cluster 工具、`platform_service/api.py:51` 的 `/api/circuit/states`、`analysis/topic_tracker.py:66` 的 embedding。
- `gateway/main.py:139` `from services.platform_service.llm_gateway import global_http_client` 目标不存在，被 lifespan 的 try/except 静默吞掉，关闭全局 HTTP 客户端逻辑永远失效。
- `topic_tracker.py:108-114` 使用 `settings.ANALYST_API_KEY/BASE_URL/MODEL`，`core/config.py` 全文无 `ANALYST*` 定义 → 运行时 `AttributeError`。
- `pipeline.py:1` 文件头仍写 `# backend/services/platform_service/pipeline.py`，docstring 仍叫 Radar Pipeline。

**影响**：核心 Agent 工具、熔断状态接口、话题分析在运行时直接抛异常；因零测试（#9）只能在线上暴露。

**改造动作**

- [ ] 先跑一次真实启动，列出全部 `ImportError`／`AttributeError` 清单（当前环境缺依赖，需先完成 #10 的依赖补齐）
- [ ] 把残留的相对导入改为现存模块的绝对导入；被删功能明确标注 deprecated 或补回实现
- [ ] 补齐 `ANALYST_*` 配置或改用现有 `get_effective_config()`
- [ ] 清理 `pipeline.py` 文件头与 docstring 中的旧路径
- [ ] `gateway/main.py:139` 改为正确模块，或删除该 shutdown 分支

**验收**：启动后逐一调用 Screener/Cluster 工具、`/api/circuit/states`、话题 embedding，无 ImportError；静态扫描相对导入断链数为 0。

---

### #6 修复前端构建链

**现状证据（构建失败为静态推断，需实跑确认）**

- `.github/workflows/deploy.yml:28` `STATIC_EXPORT=true npm run build`；`frontend/web/next.config.ts:5-16` 因此走 `output: "export"`，`rewrites` 只在 else 分支生成。Next.js 静态导出不支持 Middleware / rewrites。
- `middleware.ts:53-60` 的 `/admin` 角色校验与 `:64-77` 的登录保护是唯一的服务端路由保护；静态导出下不运行；`:67-68` 保护了不存在的 `/list`、`/yq-list`，却漏掉真实的 `/workspace`。
- `app/(app)/agent/page.tsx:4,84` 使用 `useSearchParams()` 但无 `<Suspense>`，而 login/callback 两页已正确包裹；`next.config.ts:17-22` `eslint.ignoreDuringBuilds` 与 `typescript.ignoreBuildErrors` 双开。
- `app/layout.tsx` 使用 `next/font/google`，构建时需联网。

**改造动作**

- [ ] 本地实跑 `cd frontend/web && STATIC_EXPORT=true npm run build`，记录真实报错
- [ ] 二选一：改回 `next start`（SSR）部署并保留 middleware；或静态站由 nginx 在边缘做鉴权。不要把 middleware 与 `output: export` 混用
- [ ] 用 `<Suspense>` 包裹 `AgentPage`；修正 middleware 的保护路径清单
- [ ] 关闭 `ignoreBuildErrors`，逐个修掉类型错误；`eslint-config-next` 对齐到 15.5.x（见 #15）
- [ ] CI 增加 `npm run lint && npm run type-check`（见 #9）

**验收**：`STATIC_EXPORT=true npm run build` 成功产出 `out/`；`/admin` 未授权访问在所选方案下确实被拦截。

---

### #7 统一前端鉴权链路

**现状证据**

- `lib/api.ts:7,10` `process.env.NEXT_PUBLIC_API_KEY` 会被内联进浏览器 bundle，并作为 `X-API-Key` 发送；`.env.production.example:22-26` 把它注释为「后端鉴权 + 前端调用」。
- `lib/auth-client.ts:10,14,17,24-25` token 存 localStorage，另写 `mediaradar_token_cookie`（`max-age=86400; SameSite=Lax`，无 Secure/HttpOnly）；`app/auth/callback/page.tsx:11,16-19` 从 `?token=` URL 读取；`deploy/nginx/nginx.conf:29-33` 的 log_format 记录 `$request`（含 query）。
- `app/admin/layout.tsx:21-31` 只读 `document.cookie` 的 `mediaradar_role === 'admin'`；`middleware.ts:5` 注释明确「不再信任该 cookie」，两处自相矛盾；`auth/callback/page.tsx:23-24` 还把 URL 的 `?role=` 写进该 cookie。
- `lib/api.ts:23-29` 401 仅在 token 存在时跳转；`components/chat/useAgentStream.ts:104-109` SSE 的 401 只 setError；`admin/page.tsx`、`admin/users/page.tsx` 共 5 处直接 fetch 绕过统一封装；`components/layout/topbar.tsx:114-117` 退出登录只 `localStorage.removeItem`，不删 cookie、不调 `/api/auth/logout`。

**改造动作**

- [ ] 删除 `NEXT_PUBLIC_API_KEY` 与 `X-API-Key`，鉴权统一走 JWT
- [ ] 后端下发 HttpOnly + Secure + SameSite cookie；OAuth 改一次性 code 换 token，禁止 token 走 URL
- [ ] admin 角色统一由后端 `/api/auth/me` 返回，删除 role cookie 与 URL `role` 参数信任链
- [ ] 抽统一请求拦截器（含 SSE 401）；退出登录调 `clearToken()` + `/api/auth/logout`
- [ ] 配合 #4 修复 OAuth `state` 未校验（`oauth_providers/google.py:62,123-130`）

**验收**：构建产物中检索不到 API Key；普通用户伪造 role cookie 或访问 `?role=admin` 无法进入管理页；会话过期与退出登录行为一致。

---

### #8 部署配置归一化与 CI 原子发布

**现状证据**

- 后端端口三套：`gateway/main.py:292` 8008、`deploy/nginx/omnis_baota.conf:41` 与 `deploy.yml:103` 8010、`deploy/nginx/nginx.conf:100` 与 `deploy/Dockerfile.backend:125` 8000；前端端口 CLAUDE.md 说 3003，`package.json:6` 的 `next dev` 实际默认 3000。
- 域名两套：`mediaradar.jaydennn.xyz`（`.env.production.example:3`）vs `omnis.jaydennn.xyz`（宝塔/CI/DEPLOY.md）；nginx 仍留旧名 `mediaradar.conf`。
- `deploy.yml:40` `rm -rf /www/wwwroot/omnis.jaydennn.xyz` 与 `:43-53` 的 scp 上传是**两个独立 step**，中途失败即整站为空；`:81` `git reset --hard` 丢弃服务器本地改动；无回滚。
- 实际生效的 `omnis_baota.conf:23,24` 启用 `TLSv1.1` 与 `EECDH+3DES:RSA+3DES`，全文件只有 HSTS，无 CSP / X-Frame-Options / X-Content-Type-Options；全套安全头只存在于备用容器配置 `conf.d/mediaradar.conf:54-61`。README 与 `功能清单与验证.md:123-125` 的宣称不实。
- `NEXT_PUBLIC_API_BASE` 语义冲突：`lib/api.ts:6` 用作客户端请求前缀，`next.config.ts:12` 又用作 rewrite 目标，`.env.example:10` 默认值 `http://127.0.0.1:8008` 会让生产浏览器打向用户本机。

**改造动作**

- [ ] 确定唯一生产部署路径（宝塔 systemd 或容器二选一），统一端口/域名表并写进文档
- [ ] CI 改为「上传至临时目录 → 原子 `mv`」，补失败回滚与部署前门禁
- [ ] 把容器配置的 TLS 1.2+ 与安全头同步进宝塔配置；移除 TLSv1.1 与 3DES
- [ ] 生产保持 `NEXT_PUBLIC_API_BASE` 为空，代理目标改用私有变量（如 `API_PROXY_TARGET`）
- [ ] 清理旧名 `mediaradar.conf`、`logs/radar/`

**验收**：一份端口/域名表可复现部署；CI 上传失败时站点仍可用；`curl -I` 命中安全头且 TLS 扫描无 TLSv1.1/3DES。

---

## 4. 批次 3：P2 防回归

### #9 补最小 smoke test 与 CI 质量门禁

**现状证据**

- 全仓 **0 个测试文件**：无 `tests/`、`test_*.py`、`conftest.py`、`pytest.ini`、`pyproject.toml`、`smoke_test.py`；`requirements-dev.txt` 声明了 pytest 系列却无用例。
- 前端无 `*.test.*` / `*.spec.*` / vitest / jest，`package.json` 无 `test` 脚本；`eslint.config.mjs:11-26` 关闭全部 `react-hooks/*` 规则。
- `.github/workflows/deploy.yml` 只有 `npm ci` + `STATIC_EXPORT=true npm run build`，无 lint / type-check / test；部署后仅 `curl /health`。
- 文档 `problem_i_met.md:130,261` 反复提到的 `smoke_test.py` 实际不存在。

**这是 #5 等断链能长期潜伏的根因，也是 #13 等重构的前置条件。**

**已完成的前置工作（2026-11-10，仅规范层）**

- 新增根级 `AGENTS.md`：规定改动前/后必跑命令清单、分阶段单测要求、API 契约同步、状态回写、提交规范与 10 条硬性禁止事项；明确 `python -m pytest -q` 当前无用例（退出码 5）不得写成「测试通过」。
- 按 `next@15.5.19` 改写 `frontend/web/AGENTS.md`，移除 Next 16 模板的误导说明；`CLAUDE.md` 通过 `@AGENTS.md` 引用根级规范。
- 清理 `.claude/settings.local.json` 中其他 Windows 项目的残留权限与无效 MCP，加入 `.gitignore`（该文件仍被 git 跟踪，移出索引需人工确认后 `git rm --cached`）。

> 以上**不是测试**。下方改造动作与验收标准未达成前，#9 状态保持「未开始」。

**改造动作**

- [ ] 建 `tests/` 与 pytest 配置，先写「导入链 + 关键端点」最小 smoke test（覆盖 #5 的断链与 #3 的启动校验）
- [ ] 前端补 `npm run lint` / `type-check` 脚本并恢复 react-hooks 规则
- [ ] CI 增加门禁：`pytest` + `npm run lint` + `npm run type-check`，失败即阻止部署
- [ ] 把 `功能清单与验证.md` 里的关键路径逐步固化为自动化用例

**验收**：CI 在故意引入一个错误 import 时变红；正常提交变绿。

---

### #10 依赖清单与 Python 包边界

**现状证据**

- `requirements.txt` 未声明代码实际 import 的：`playwright`(28 处/26 文件)、`sqlalchemy`(19/9)、`aiofiles`(11/11)、`openpyxl`、`redis`、`pandas`、`parsel`、`execjs` 等。
- 导入风格双轨：`from backend.*` 227 次/75 文件、`from services.*` 23 次/7 文件、`from core.*` 6 文件、crawler 扁平 `import config`(48)/`tools`(72)/`base`(34)/`proxy`(29) 等。
- 代码中 `sys.path.append/insert` 4 处：`gateway/main.py:30,33`、`crawler_service/database/db.py:30`、`crawler_service/tools/utils.py:32`。
- `backend/`、`backend/gateway/`、`backend/services/crawler_service/` 缺 `__init__.py`；`backend/__init__.py` 缺失意味着 `import backend.*` 依赖 namespace package + gateway 的 sys.path 注入。
- `crawler_service/` 146 个 `.py` 中 142 个标注外部仓库来源，是独立子系统，不宜与主项目强行统一导入风格。

**改造动作**

- [ ] 补齐 `requirements.txt`；把 crawler 的可选依赖单独成文件并说明
- [ ] 补 `__init__.py`，统一主项目为 `from backend.*` 绝对导入，清掉 `gateway/main.py` 的 sys.path hack
- [ ] crawler 子系统维持独立边界，文档说明其启动方式，不强行改造
- [ ] 用 `python -c "import backend.gateway.main"` 之类做导入自检并纳入 #9

**验收**：在干净环境按 README 安装依赖后可启动；主项目代码中 `from core.*` / `from services.*` 计数为 0。

---

### #11 限流、中间件顺序与请求体限制

**现状证据**

- 全仓 **无任何 `request.state.user_id =` 赋值**（认证发生在路由依赖，晚于中间件）；`core/rate_limiter.py:173-175` 的 `_has_auth` 恒为 False，除 `/api/auth/*` 外所有接口直接放行。
- `rate_limiter.py:53-55` 直接信任 `X-Forwarded-For` 伪造即可轮换限流 key；`:134` `_decode_guest_from_header` 明确不验签。
- `core/security_middleware.py:72-88` 只检查 `Content-Length`，chunked 或畸形值 `pass`；`gateway/main.py:197-200` 注释顺序与实际 `add_middleware`(insert(0)) 的执行顺序相反，短路响应缺安全头/CORS 头。

**改造动作**

- [ ] 在认证中间件解析并写入 `request.state.user_id`；未认证请求按 `request.client.host` 限流
- [ ] XFF 仅在可信代理链下取可信值；guest 档位复用已验签结果
- [ ] 请求体改为流式累计 `len(chunk)`；显式按逆序注册中间件并核对实际栈顺序
- [ ] 对 413/429/500 等短路响应补安全头与 CORS 头

**验收**：未认证接口连续请求触发 429；伪造 XFF 无效；chunked 超 1 MB 被拒。

---

### #12 异常回显、日志脱敏与管理端点

**现状证据**

- `platform_service/api.py:404,823,825`、`agent_service/api.py:107,131,151,254`、`auth_service/api.py:407,448`、`oauth_providers/google.py:100` 把 `str(e)` / 上游响应 / payload 回给客户端；`gateway/main.py:202-209` 的全局 handler 本身是正确的。
- `core/logger.py:45-54` 脱敏 filter 只处理 `record.msg`/`record.args`，`JSONFormatter:133-134` 的 `formatException(record.exc_info)` 未脱敏。
- `platform_service/api.py:727-730` 把系统默认 Key 末 4 位回显给任意注册用户；`api.py:124,194,415,487` 注释写「无 token 视为 admin」而实现是 `Depends(get_current_user)`，注释与实现严重不符。
- 多处 `except Exception: pass`（`gateway/main.py:142-143`、`admin_service/agent_monitor.py` 等）掩盖故障。

**改造动作**

- [ ] 统一 500 文案，堆栈只写服务端日志；脱敏 filter 覆盖 `exc_info` 与 `getMessage()`
- [ ] 模型配置接口只返回 `has_key`，不回显任何片段
- [ ] 修正误导性注释；清理吞异常的 `except: pass`
- [ ] 顺带处理 `core/auth.py:5,7` 的 `APIKeyHeader` 重复定义

**验收**：构造异常请求，响应不含路径/堆栈/上游内容；日志文件中检索不到明文密钥。

---

## 5. 批次 4：P3 提质

### #13 拆分 4 个 God 文件

**现状证据**：`agent_service/pipeline.py` 1143 行（14 个顶层类，4 个 Pipeline 阶段 + 调度器 + 数据结构，文件头仍写旧路径）、`agent_service/agent_core.py` 867 行（主循环/上下文/工具执行/记忆写入）、`platform_service/api.py` 858 行（23 个路由）、`platform_service/analysis/topic_tracker.py` 809 行（11 个函数无分层）。

**改造动作**：优先拆 `platform_service/api.py` 为 `api/routes_*.py`（路由边界清晰、风险最低），再拆 `pipeline.py` 为 `pipeline/stage_*.py`；每拆一个跑一次 #9 的测试；用 `git mv` 保留历史；`agent_core.py` 与 `topic_tracker.py` 最后处理。

**验收**：单文件均 < 500 行；#9 全绿；对外 API 路径与响应不变。

> **前置条件**：#9 测试覆盖到位。禁止在零测试状态下拆分。

---

### #14 假数据、假控件与高频轮询

**现状证据**

- `app/(app)/dashboard/page.tsx:124` Agent 活跃度写死 `'94'`；5 个 query 的 `refetchInterval` 为 3000/10000/30000/30000/15000 ms。`功能清单与验证.md:40` 明确要求「无硬编码假数据」。
- `dashboard/page.tsx:36` 需三个错误同时发生才提示；`agent/page.tsx:162-164,176` 静默 catch；`settings/llm/page.tsx:196-199` 测试连接 mutation 只有 `onSuccess` 无 `onError`；`admin/page.tsx:30` `.catch(() => {})`。
- `功能清单与验证.md` 多项落空：`6.8` 修改密码（后端 `/api/auth/change-password` 存在，前端零调用）、`8.3` 修改角色（后端端点存在，前端只有禁用按钮）、配额页整页占位、workspace「新建工作流」只做跳转；2FA 与通知开关为纯前端 state；登录页「保持 30 天登录」checkbox 无 onChange，而 cookie 只有 1 天。
- 可访问性：图标按钮无 `aria-label`、textarea 无 label、部分 `<label>` 缺 `htmlFor`；`settings/llm/page.tsx:30-32`、`settings/push/page.tsx:46-48` 在 hooks 之前提前 return（违反 Hooks 规则，因 lint 规则被关而未报）。

**改造动作**：接真实指标或移除假数字、轮询改 SSE/按页面可见性暂停；补全局 error boundary 与 onError；补齐或如实标注未实现功能；实现或删除假控件；补 a11y 属性并把游客拦截上提到 layout。

**验收**：`功能清单与验证.md` 中每一项状态可勾选；控制台无 Hooks 报错。

---

### #15 文档治理与死配置清理

**现状证据**

- `problem_i_met.md` 过时（见 0.1）；README 的 TLS/CSP 宣称与实际配置不符；CLAUDE.md 端口 3003 与实际 3000 不符；`.env.production.example:3-4` 明文写生产域名与服务器 IP `124.220.10.233`。
- `frontend/web/.env.example:5-6` 宣称 `NEXT_PUBLIC_USE_MOCK=true` 启用 MSW，但全仓无 handlers、无 worker 初始化、无 `public/mockServiceWorker.js`；`msw` 还在 `dependencies`。
- `lib/auth.ts` 导出 NextAuth handlers，但无 `app/api/auth/[...nextauth]/route.ts`，`AUTH_SECRET`/`NEXTAUTH_URL`/`GOOGLE_*` 全是无效配置；实际 Google 登录直跳后端。
- `package.json` 中 `eslint-config-next@16.2.7` 配 `next@15.5.19`；`AGENTS.md` 讲的是 Next 16 规则；`shadcn`(CLI) 误列 dependencies。

**改造动作**：在本文件完成后给 `problem_i_met.md` 顶部加「已过时，见 REFACTOR_ROADMAP.md」指引；统一 README 的安全与端口表述；移除示例里的生产 IP；删除或补齐 MSW；删除 next-auth 死代码与依赖；对齐 eslint 版本、改写 AGENTS.md。

**已完成的子项（2026-11-10）**：已新增根级 `AGENTS.md` 开发规范，`frontend/web/AGENTS.md` 已按 `next@15.5.19` 改写并移除 Next 16 模板，`CLAUDE.md` 已补充流程引用与「部分事实已过时」提示，`.claude/settings.local.json` 已清理旧项目残留并加入 `.gitignore`。仍待处理：给 `problem_i_met.md` 加过时指引、统一 README 安全/端口表述、移除示例中的生产 IP、清理 MSW 与 next-auth 死代码、对齐 `eslint-config-next` 版本、把 `settings.local.json` 移出索引。

**验收**：按 README 从零启动无歧义；`npm ls` 无版本冲突告警。

---

### #16 已知问题收尾

**现状证据**

- `problem_i_met.md` P1：`_write_memory_async` 异步写记忆，`phase_build_context` 从 DB 重建时可能读到落后一轮数据（`agent_core.py:277,411,791,813`）；已有「先写 SQLite 后 LLM 抽取」缓解（`:830-842`）。
- P2：`agent_core.py:280` `stored[-6:]` 硬编码，`memory/memory_manager.py:189,240` 同，且 `agent_core.py:247,279` 注释写「最近 4 条」与代码 6 矛盾。

**改造动作**：stream 结束时同步落库 `replace_messages`，或引入版本号检测陈旧；尾巴条数按 token 占用/工具链长度动态计算；修正注释。

**验收**：连续快速发送两条消息，第二轮上下文包含第一轮内容；长工具链场景不截断关键上下文。

---

## 6. 每批验收记录

| 批次 | 完成日期 | 验收结果 | 备注 |
|------|----------|----------|------|
| P0 止血 | — | — | — |
| P1 恢复可运行 | — | — | — |
| P2 防回归 | — | — | — |
| P3 提质 | — | — | — |

---

## 7. 已知局限

- 本轮结论来自**静态分析**。本机未安装项目依赖，后端未启动、前端未构建、无任何测试被执行。
- #6 的「构建失败」是基于 Next.js 静态导出规则与代码配置的推断，需实跑 `STATIC_EXPORT=true npm run build` 确认或推翻。
- #5 的断链是文件级实证（目标模块确实不存在），但完整影响面需在运行环境逐一复现。
- 凭据泄露的**历史范围**无法从浅克隆判断，本地无 git 历史；远端历史需单独审计。
- 行号以 2026-11-10 的 `main@b51571f` 为准，改动后需同步更新。
