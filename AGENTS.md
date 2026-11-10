# AGENTS.md — Omnis 开发规范

> **适用对象**：在本仓库工作的所有 AI 编码助手与人类开发者。
> **基线**：2026-11-10，代码基线 `main@b51571f`；本规范自 `Wuhj` 分支引入。
> **性质**：本文件定义**流程与硬性约束**，不描述架构。架构见 `CLAUDE.md`，改造排期见 `docs/REFACTOR_ROADMAP.md`。
> **语言**：中文正文，命令与标识符保持英文原样。

---

## 0. 规范优先级与事实来源

当多份文件说法冲突时，按下列顺序裁决：

1. **代码的实际内容**（唯一事实来源）
2. **本文件 `AGENTS.md`**（根级流程约束）
3. **子目录 `AGENTS.md`**（如 `frontend/web/AGENTS.md`，仅补充该目录特有规则）
4. **`CLAUDE.md`**（项目认知库，架构与目录索引）
5. `docs/API_CONTRACT.md`、`README*.md`、`功能清单与验证.md` 等其他文档
6. 代码注释

**发现冲突时，不得按旧文档改代码**：以代码为准，并把文档修正记入本次改动或登记到 `docs/REFACTOR_ROADMAP.md` #15。

### 0.1 文档索引

| 文件 | 权威内容 | 可否作为改造依据 |
|---|---|---|
| `AGENTS.md`（本文件） | 开发流程、命令、测试、提交、安全红线 | **是，强制** |
| `docs/REFACTOR_ROADMAP.md` | 16 项改造清单、状态、每批验收记录 | **是，唯一跟踪基线** |
| `docs/API_CONTRACT.md` | 后端 API 契约 | 改 API 时必须同步 |
| `CLAUDE.md` | 架构、目录、Agent 工作流、启动方式 | 参考；部分端口与邀请码说明已过时 |
| `功能清单与验证.md` | 功能验收清单 | 参考 |
| `problem_i_met.md` | 重构前的已知问题 | **否，已过时**（目录名、行号、数量均不实） |
| `frontend/web/AGENTS.md` | 前端子目录规范 | 是 |
| `.claude/settings.local.json` | Claude Code 本地权限白名单 | **否，不是项目事实**，见 0.2 |

### 0.2 明确不可参照的残留

- `problem_i_met.md`：写于 `radar_service → platform_service` 重构之前，其中 `smoke_test.py` 从未存在。
- `.claude/settings.local.json`：来自另一个 Windows 项目（`D:/JAYDEN/.../MediaRadar`、`selgetabel`、`pnpm --filter @selgetabel/web`），并引用不存在的 MCP `mediaradar`。其中的命令路径、包名、端口全部与本项目无关，**不得据此推断命令或目录**。该文件为本地工具配置，虽当前被 git 跟踪，也不属于项目事实；从索引移除属于 `docs/REFACTOR_ROADMAP.md` #15 的范围，需人工确认后执行 `git rm --cached`。
- `frontend/web/.env.example` 中的 `NEXT_PUBLIC_USE_MOCK`、NextAuth 相关环境变量：均为死配置，仓库无对应实现，不要为其补代码。

---

## 1. 仓库事实（开工前必读）

| 项 | 实际值 |
|---|---|
| 后端 | FastAPI + SQLite，入口 `backend/gateway/main.py`，依赖 `requirements.txt` |
| 前端 | `frontend/web`，Next.js **15.5.19** App Router + React **18.3.1** + TypeScript 5 + Tailwind v4 |
| 包管理 | 前端 `npm` + `package-lock.json`（用 `npm ci`）；后端 `pip` + `requirements*.txt` |
| 环境 | 根目录 `.env`（参考 `.env.example`），前端 `frontend/web/.env.local` |
| 工作分支 | `Wuhj`（日常开发） |
| 生产分支 | `main` |

**端口现状未统一，属于已知问题（#8），不要新增第三套硬编码值**：`CLAUDE.md` 写后端 `8008` / 前端 `3003`；`next.config.ts` 默认回退 `8008`；CI 健康检查用 `8010`；`package.json` 的 `next dev` 未指定端口，实际为 `3000`。改造时一律通过环境变量注入，不得再写死。

> **高风险**：`.github/workflows/deploy.yml` 在 `push` 到 `main` 时自动部署到生产服务器。任何对 `main` 的直接提交/推送都会上线，且该流程会先 `rm -rf` 生产前端目录再上传。

---

## 2. 开工前检查（Pre-flight）

每次接到开发任务，先完成以下确认，再动手改文件：

- [ ] `git status --short` 确认工作区状态，记录已有改动，**不要覆盖或顺手清理他人的未提交内容**
- [ ] `git branch --show-current` 确认在 `Wuhj` 或其他非生产分支
- [ ] 阅读 `docs/REFACTOR_ROADMAP.md`，确认本次对应哪个编号项、当前状态、验收标准
- [ ] 若任务不属于已有 16 项，先说明并建议登记新条目，不要静默扩大范围
- [ ] 确认依赖是否可用（`frontend/web/node_modules`、Python 包）；缺失时**如实说明**，不要用绕过手段伪装通过
- [ ] **一次只做一个编号项**。跨批次重构、拆分 God 文件（#13）在 #9 的测试覆盖到位之前禁止启动

---

## 3. 命令清单

所有命令均在**仓库根目录**执行，除非另有说明。

### 3.1 当前可执行（已核实存在）

| 目的 | 命令 | 前提 / 说明 |
|---|---|---|
| 后端依赖 | `pip install -r requirements.txt -r requirements-dev.txt` | 需 Python 3.10+ |
| 后端启动 | `python backend/gateway/main.py` | 需 `.env`；默认 8008 |
| 后端语法检查 | `python -m compileall -q backend` | **无需第三方依赖**，改动 `.py` 后必跑 |
| 前端依赖 | `cd frontend/web && npm ci` | 使用 lock 文件，不要用 `npm install` 改锁 |
| 前端开发 | `cd frontend/web && npm run dev` | 默认 3000 |
| 前端构建 | `cd frontend/web && npm run build` | 常规构建 |
| 静态导出构建 | `cd frontend/web && STATIC_EXPORT=true npm run build` | **CI 实际使用的命令**，产物 `out/` |
| Lint | `cd frontend/web && npm run lint` | `eslint.config.mjs` 关闭了大量 `react-hooks/*` 规则，见 #9 |
| 类型检查 | `cd frontend/web && npm run type-check` | `tsc --noEmit` |
| 格式检查 | `cd frontend/web && npm run format:check` | Prettier |
| 提交前空白检查 | `git diff --check` | 检测尾随空格、冲突标记 |

### 3.2 当前不可用 / 目标状态（**不得声称已通过**）

| 命令 | 现状 |
|---|---|
| `python -m pytest -q` | 全仓 **0 个测试文件**，无 `tests/`、`conftest.py`、`pytest.ini`、`pyproject.toml`。`requirements-dev.txt` 已声明 pytest 系列但无用例；此时运行会返回退出码 5（未收集到用例）。补基础设施属 #9。 |
| `npm test` | `package.json` 无 `test` 脚本，前端无测试框架。引入前需先确认技术选型。 |
| CI 质量门禁 | `.github/workflows/deploy.yml` 当前只有 `npm ci` + 构建，不跑 lint / type-check / test。属 #9。 |

> 写「已验证」之前必须先真的运行命令。推断出的结论要标注为「静态推断」，实证结论要附命令与输出摘要。

---

## 4. 强制流程

### 4.1 改动前

1. 说明本次要改的文件与预期行为，确认不触碰无关模块。
2. 若涉及 API 路径、请求/响应结构、状态码或鉴权方式，先读 `docs/API_CONTRACT.md`，把契约变更一并列出。
3. 若涉及环境变量，同步检查 `.env.example` 与 `frontend/web/.env.example`，但不写入任何真实值。
4. 若涉及部署或 CI，明确告知会影响 `main` 的自动发布，并取得人工确认。

### 4.2 改动中

- **测试要求（分阶段）**
  - **过渡期（#9 完成前）**：任何行为改动必须给出至少一种可执行的验证方式（命令 + 预期输出），并在交付时如实报告是否真的运行。无法运行就写「未验证」，禁止写「测试通过」。
  - **#9 完成后**：新增或修改的后端行为必须有对应 pytest 用例；每个 bug 修复必须附一个能复现该 bug 的回归用例。改了测试才能让旧行为通过，属于违规。
- **API 变更必须同步 `docs/API_CONTRACT.md`**，并检查前端调用点（`frontend/web/lib/api.ts` 及各页面）。
- **不得用关闭检查来「通过」**：禁止新增 `eslint-disable`、`@ts-ignore`、`ignoreBuildErrors`、`ignoreDuringBuilds`、`skip` 标记来规避失败；已有同类开关按 #9 逐步恢复，不要扩大。
- **最小改动**：修一个编号项时，不顺手重命名、格式化整个文件、调整无关依赖。
- **安全红线**：
  - 禁止把密钥、token、Cookie、真实邮箱、服务器 IP 写进代码、文档、示例、测试固件或日志。
  - 禁止把任何密钥放进 `NEXT_PUBLIC_*` 变量（会编译进浏览器 bundle）。
  - 禁止在测试中调用真实 LLM、真实第三方登录态、真实 SMTP/RSS 凭据；一律 mock。
  - 新增配置必须 fail-fast：生产环境缺关键配置应启动失败，不得静默回退到不安全默认值（见 #3）。
  - 用户可控的 URL 必须做出站校验，禁止直接用于服务端请求（见 #2）。

### 4.3 改动后：必跑清单

| 改动类型 | 至少执行 |
|---|---|
| 任意改动 | `git status --short`、`git diff --check` |
| `backend/**/*.py` | `python -m compileall -q backend`；涉及导入链时补一次模块导入验证 |
| 前端 `.ts/.tsx` | `npm run type-check` + `npm run lint`（在 `frontend/web` 下） |
| 前端构建/路由/配置 | 追加 `STATIC_EXPORT=true npm run build`（CI 同款） |
| API 契约 | 人工核对 `docs/API_CONTRACT.md` 与前端调用点 |
| 依赖变更 | 说明 lock 文件是否变化，不得只改 `package.json` / `requirements.txt` |
| 测试基建（#9 起） | `python -m pytest -q` 且退出码为 0 |

**交付报告必须包含以下五项**，缺一不可：

1. 改动文件清单（路径 + 每个文件做了什么）
2. 实际运行的验证命令与结果摘要（含退出码/关键输出）
3. **未验证项**（因缺依赖、缺环境、需联网等未能执行的部分）
4. 遗留风险与后续动作
5. `docs/REFACTOR_ROADMAP.md` 的状态回写情况

---

## 5. 代码约定

### 5.1 Python（backend/）

- 导入风格现状混乱（`backend.*` / `services.*` / `core.*` 三种并存，另有 4 处 `sys.path` hack，见 #10）。**新增文件统一使用 `backend.` 开头的绝对导入，禁止新增 `sys.path.append/insert`**；存量代码在对应改造项内逐步收敛，不跨项批量改。
- 单文件超过 700 行应说明原因；禁止在零测试状态下拆分 God 文件（#13）。
- 新增函数带类型标注；异步代码用 `async/await`，不要在事件循环里做同步阻塞 IO。
- 禁止裸 `except:` 与静默吞异常；禁止把 `str(e)`、异常堆栈、上游响应体直接回显给客户端（见 #12）。
- 日志必须脱敏：不打印 token、密码、API Key、完整请求体。
- 数据库访问使用参数化查询，禁止字符串拼接 SQL。

### 5.2 TypeScript（frontend/web/）

- 禁止新增 `any`；优先用 Zod schema 推导类型。
- 组件必须有 loading / error / 空态处理，禁止空 `.catch(() => {})`。
- Hooks 必须在条件返回之前调用；`useSearchParams()` 必须包在 `<Suspense>` 内（静态导出下尤其关键，见 #6）。
- 密钥与 token 不写入 `localStorage` 明文长期留存、不放在 URL query 中传递；鉴权改造统一按 #7 收敛。
- 图标按钮补 `aria-label`，表单控件补 `label` / `htmlFor`。
- 前端 API 地址只从环境变量读取，禁止硬编码 `localhost:8008`。

### 5.3 配置、文档与数据

- `.env` 一律不入库；示例文件只放占位符。
- 运行时产物（`logs/`、`browser_data/`、`backend/data/*.db`、`node_modules/`、`.next/`、`out/`）不得提交。
- 改目录结构 → 同步 `CLAUDE.md`；改 API → 同步 `docs/API_CONTRACT.md`；改流程 → 同步本文件；改功能状态 → 同步 `功能清单与验证.md`。
- **行号会漂移**：`docs/REFACTOR_ROADMAP.md` 的证据行号以 `main@b51571f` 为基线，改动后需在对应条目注明新基线。

---

## 6. 提交与分支规范

### 6.1 分支

- 日常开发在 **`Wuhj`** 或经确认的功能分支；**禁止直接向 `main` 提交或推送**（会触发生产部署）。
- 不擅自新建、删除、重命名分支，不擅自 `git push`（含 `--force`）。推送由项目负责人执行。

### 6.2 提交信息

采用 Conventional Commits：`type(scope): 简述`，描述用中文或英文均可，`type` 固定为英文小写。

| type | 用途 |
|---|---|
| `feat` | 新功能 |
| `fix` | 缺陷修复 |
| `refactor` | 不改变行为的结构调整 |
| `test` | 仅测试 |
| `docs` | 仅文档 |
| `chore` | 依赖、构建、配置 |
| `security` | 安全相关修复 |

示例：`fix(auth): 校验 refresh token 不得用作 access token`

每次提交在描述中关联改造编号（如 `ref #4`），便于回溯 `docs/REFACTOR_ROADMAP.md`。

### 6.3 提交前自检

```
git status --short
git diff --check
git diff --cached --stat
```

确认暂存区**不含**：`.env*`（示例除外）、`*.db`、`logs/`、`browser_data/`、`node_modules/`、`out/`、`.next/`、任何真实凭据或个人信息。`git diff --cached` 必须逐份看过再提交，禁止 `git add -A` 一把梭。

### 6.4 破坏性操作：必须先取得人工确认

以下动作**一律不自动执行**，即便任务描述看起来需要：

- `git rm -r --cached`、`git filter-repo` / `filter-branch`（历史重写）
- `git reset --hard`、`git clean -fd`、`git push --force`、`git rebase`（改写已推送历史）
- 删除或重建远端分支、修改 CI secrets、轮换线上凭据（微博/微信登录态、LLM API Key、SMTP 密码、JWT_SECRET、邀请码、RSS token）
- 登录/操作生产服务器、修改 `.github/workflows/deploy.yml` 的部署步骤
- 批量删除仓库内文件

理由与待办见 `docs/REFACTOR_ROADMAP.md` 0.4：本仓库为公开仓库且本地为浅克隆，已进入远端历史的凭据应视为**已泄露**，清理当前树不等于消除风险，必须轮换。

---

## 7. 改造状态回写

每完成一个编号项，回到 `docs/REFACTOR_ROADMAP.md` 更新：

1. 「1. 总览」表中该项状态：`未开始` → `进行中` → `已完成`（受阻写 `阻塞` 并注明原因）
2. 该项「改造动作」的勾选框，未完成的保留未勾选并说明
3. 「6. 每批验收记录」：填写批次完成日期、实际验收命令与结果、备注
4. 若改动使证据行号失效，在该条目标注新的代码基线

**验收记录只能写实测结果**。写「CI 变绿」前必须真的看到 CI 结果；写「构建通过」前必须真的跑过 `npm run build`。

---

## 8. 硬性禁止事项汇总

1. 不照抄 `problem_i_met.md` 的目录名、行号与数量结论。
2. 不把 `.claude/settings.local.json` 里的路径、包名、端口当作本项目事实。
3. 不在 `main` 上直接提交或推送。
4. 不提交任何真实凭据、日志、数据库、登录态。
5. 不用关闭 lint / type-check / 测试的方式让检查「通过」。
6. 不把静态推断写成实测结论，不把未运行的命令写成「已通过」。
7. 不自动执行第 6.4 节的任何破坏性或外部操作。
8. 不在 #9 完成前启动 #13 的 God 文件拆分，不跨编号项批量重构。
9. 不新增 `sys.path` hack、不新增硬编码端口/域名/IP。
10. 不在未确认时引入新的前端测试框架或改动 CI 部署逻辑。

---

## 9. 生效与维护

- 本文件由 2026-11-10 的开发流程梳理引入，对应 `docs/REFACTOR_ROADMAP.md` #9（测试与门禁）与 #15（文档治理）的前置成果；它**不替代** #9 的测试基建本身。
- 规则与项目现状冲突时（例如 #9 完成后 pytest 已可用），应**立即更新本文件第 3.2 节与第 4.2 节**，避免规范本身变成新的过时文档。
- 修改本文件属于流程变更，需在提交信息中使用 `docs(agents):` 并说明原因。
