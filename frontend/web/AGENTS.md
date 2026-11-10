# AGENTS.md — frontend/web 前端子目录规范

> **先读仓库根目录的 `AGENTS.md`**，其中定义了全仓通用的流程、命令、测试、提交与安全红线；本文件只补充前端特有规则。冲突时以根级 `AGENTS.md` 为准。
>
> **版本事实**：本目录锁定 `next@15.5.19` + `react@18.3.1` + TypeScript 5 + Tailwind v4 + App Router，**不是 Next.js 16**。
> 本文件此前是 Next.js 16 命令行工具生成的 `BEGIN:nextjs-agent-rules` 模板，宣称「This is NOT the Next.js you know」并要求阅读 `node_modules/next/dist/docs/`。该模板与本项目版本不符（本机当前亦未安装 `node_modules`），已移除，请勿据其判断 API 或目录结构。

---

## 1. 本目录命令

在 `frontend/web/` 下执行：

| 目的 | 命令 |
|---|---|
| 安装依赖 | `npm ci`（有 `package-lock.json`，不要用 `npm install` 改锁） |
| 开发 | `npm run dev`（默认 3000） |
| 常规构建 | `npm run build` |
| CI 同款静态导出构建 | `STATIC_EXPORT=true npm run build`（产物 `out/`） |
| Lint | `npm run lint` |
| 类型检查 | `npm run type-check` |
| 格式检查 | `npm run format:check` |

目前**没有** `npm test`：无测试框架、无 `*.test.*` / `*.spec.*` 文件。不要在交付报告里写「前端测试通过」。

## 2. 构建与路由约束

- `next.config.ts` 在 `STATIC_EXPORT=true` 时启用 `output: "export"`，**静态导出不支持 middleware 与 rewrites**。改动 `middleware.ts`、`next.config.ts`、路由或 `useSearchParams()` 时，必须实跑 `STATIC_EXPORT=true npm run build` 验证，不能只跑普通构建。CI 使用的正是静态导出命令（见 `.github/workflows/deploy.yml`）。
- `next.config.ts` 当前把 `eslint.ignoreDuringBuilds` 与 `typescript.ignoreBuildErrors` 双开，`eslint.config.mjs` 又关闭了大部分 `react-hooks/*` 规则。**这意味着 `npm run build` 通过不代表代码合规**，所以 `npm run lint` 与 `npm run type-check` 必须单独跑。恢复这些开关属于 `docs/REFACTOR_ROADMAP.md` #9，不要为了「过构建」再关更多检查。
- `eslint-config-next@16.2.7` 与 `next@15.5.19` 版本错配（#15）。遇到 eslint 报出与版本相关的怪异错误时，先记录为版本问题，不要强行改业务代码绕过。
- 使用 `useSearchParams()` 的组件必须包在 `<Suspense>` 边界内，否则静态导出构建会失败（#6）。

## 3. 代码约定

- 禁止新增 `any`、`@ts-ignore`、`eslint-disable`；优先用 Zod schema 推导类型。
- Hooks 调用不得位于任何提前 `return` 之后；组件须有 loading / error / 空态，禁止空 `.catch(() => {})`。
- 图标按钮补 `aria-label`，表单控件补 `label` / `htmlFor`。
- UI 组件基于 `components/ui/`（shadcn/ui），该目录被 eslint 全局忽略；改动前先确认是否属于生成代码。
- `app/` 为 App Router；页面组件默认为服务端组件，使用 hooks / 浏览器 API 的文件需 `"use client"`。

## 4. 环境变量与鉴权

- 后端地址只从环境变量读取（当前 `NEXT_PUBLIC_API_BASE`，`next.config.ts` 回退 `http://localhost:8008`）。**禁止硬编码 `localhost`、生产域名或服务器 IP**。
- `NEXT_PUBLIC_*` 会编译进浏览器 bundle，**任何密钥、API Key、token 都不得放入此类变量**（现状 `NEXT_PUBLIC_API_KEY` 存在问题，见 #7）。
- JWT 现状为 localStorage 存储、经 URL query 传递、cookie 无 HttpOnly/Secure；`app/admin/layout.tsx` 信任可伪造的 `mediaradar_role` cookie。新增鉴权逻辑时不得沿用这些做法，按 #7 统一收敛。
- `frontend/web/.env.example` 中的 `NEXT_PUBLIC_USE_MOCK`、NextAuth 相关变量均为死配置（无 MSW handlers、无 `app/api/auth/[...nextauth]/route.ts`），不要为其补实现，也不要在代码中读取。

## 5. 与后端联动

- 改动 API 路径、请求/响应结构、状态码或鉴权方式时，同步更新根目录 `docs/API_CONTRACT.md`，并检查 `lib/api.ts` 与所有调用页面。
- 改完按根级 `AGENTS.md` 第 7 节回写 `docs/REFACTOR_ROADMAP.md` 的状态与验收记录。
