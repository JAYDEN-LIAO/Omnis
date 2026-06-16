# Admin Agent 监控看板方案

> 目标：为多用户 SaaS 系统提供完整的 Agent 运维监控能力。
> 原则：充分利用现有 Prometheus 指标 + 记忆库数据 + 熔断器状态，只做聚合和暴露。

**实施状态：全部完成（2026-06-16）。**

| 组件 | 状态 | 说明 |
|------|------|------|
| `admin_service/agent_health_db.py` | ✅ | 诊断事件 SQLite 持久化（WAL + 幂等建表） |
| `admin_service/agent_monitor.py` | ✅ | Prometheus 聚合层（overview / tools / sessions / diagnosis） |
| `admin_service/api.py` | ✅ | 5 个 REST 端点 + 1 个 WebSocket（JWT 认证） |
| `gateway/main.py` 集成 | ✅ | 挂载路由到 `/api/admin/agents/*` |
| `diagnosis_engine.py` 集成 | ✅ | 诊断事件落库钩子（try/except 包裹） |
| `memory_store.py` 修改 | ✅ | `get_all_sessions` 加 `owner_id` 列；`count_active_sessions()` |
| 前端 | ⬜ | Admin Agent 监控页面不在本次范围 |
| **Agent Ops 智能层** | ✅ | 全部完成 |
| `agent_ops.py` | ✅ | AgentOpsEngine — 健康巡检/日报/快照/LLM分析/NL查询 |
| `agent_health_db.py` 扩展 | ✅ | agent_health_snapshot 表 + 4 方法 |
| `api.py` Ops 端点 | ✅ | /report、/report/daily、/chat 端点 |
| `gateway/main.py` Ops 调度 | ✅ | lifespan start/stop Ops scheduler |

## 已实施：基础监控层

| 组件 | 状态 | 说明 |
|------|------|------|
| `admin_service/agent_health_db.py` | ✅ | 诊断事件 SQLite 持久化（WAL + 幂等建表） |
| `admin_service/agent_monitor.py` | ✅ | Prometheus 聚合层（overview / tools / sessions / diagnosis） |
| `admin_service/api.py` | ✅ | 5 个 REST 端点 + 1 个 WebSocket（JWT 认证） |
| `gateway/main.py` 集成 | ✅ | 挂载路由到 `/api/admin/agents/*` |
| `diagnosis_engine.py` 集成 | ✅ | 诊断事件落库钩子（try/except 包裹） |
| `memory_store.py` 修改 | ✅ | `get_all_sessions` 加 `owner_id` 列；`count_active_sessions()` |
| 前端 | ⬜ | Admin Agent 监控页面不在本次范围 |

### 数据源（直接可用）

| 数据源 | 位置 | 提供什么 |
|--------|------|---------|
| Prometheus 指标 | `core/metrics.py` | `AGENT_TOOL_CALLS`（按 tool+status）、`AGENT_TOOL_LATENCY`、`AGENT_MEMORY_WRITES`、`AGENT_TURNS`、`CIRCUIT_BREAKER_STATE` |
| 记忆库统计 | `memory_store.py` | `get_memory_stats()` → 4 张表的行数、`get_all_sessions()` → 会话列表 |
| 熔断器状态 | `diagnosis_engine.py` | `CircuitBreakerRegistry` → 按工具名的 3 态 |
| 诊断事件 | `agent_health_db.py` | `agent_diagnosis_log` 表 |

### 架构概要

```
API Layer:  /api/admin/agents/*
    │
    ▼
AgentMonitorService (单例)
    ├─ get_overview()          → 聚合仪表盘数据（轮次/工具/熔断/记忆）
    ├─ get_tool_health()       → 按工具统计成功率/熔断态
    ├─ get_session_stats()     → 活跃会话列表 + 消息数
    └─ get_diagnosis_events()  → 自愈事件日志
    │
    ▼
数据源（全部已有，只读）
    ├─ metrics.py (Prometheus Counter/Histogram/Gauge)
    ├─ memory_store.py (AgentMemoryStore)
    ├─ diagnosis_engine.py (CircuitBreakerRegistry)
    └─ agent_health_db.py (agent_diagnosis_log)
```

设计原则：不引入新中间件，不引入时序数据库，API 风格对齐 `subscription_service/api.py`。

### API 一览

| 端点 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/api/admin/agents/overview` | GET | 总览仪表盘（对话轮次/工具调用/熔断/记忆） | Admin |
| `/api/admin/agents/tools` | GET | 工具级健康（成功率/熔断态） | Admin |
| `/api/admin/agents/sessions` | GET | 活跃会话列表 + 消息数 | Admin |
| `/api/admin/agents/diagnosis` | GET | 自愈诊断事件日志 | Admin |
| `/api/admin/agents/memory` | GET | 记忆库容量统计 | Admin |
| `/api/admin/agents/ws` | WS | 每 5s 推送实时总览（`?token=<jwt>`） | Admin |

### 数据流

```
Agent 运行时
  agent_core.py
    │─ ToolExecutor.execute() → AGENT_TOOL_CALLS.inc()
    │─ tool latency → AGENT_TOOL_LATENCY.observe()
    │─ _write_memory_async() → AGENT_MEMORY_WRITES.inc()
    │
    └─ DiagnosisEngine.execute_with_diagnosis()
         └─ .record_diagnosis(...)  ────────────────┐
                                                      │
Prometheus Metrics (内存)                              │
  AGENT_TOOL_CALLS / AGENT_TOOL_LATENCY / ...        │
         │                                            │
         ▼                                            ▼
AgentMonitorService (聚合层)          AgentHealthDB (SQLite)
  _sample_counter_by_label()          - agent_diagnosis_log
         │
         ▼
HTTP API + WebSocket
  /api/admin/agents/*
```

---

## 待实施：智能运维扩展（Agent Ops Engine）

> 目标：在现有数据聚合层之上增加 LLM 驱动的分析决策层，将 Admin Monitor 从被动数据管道升级为主动智能运维体。
> 原则：只做增量，不动现有代码逻辑。所有数据源已就绪，只需加智能层。

### 1. 现状诊断：当前 Monitor 缺了什么

| 层次 | 已有 | 缺失 |
|------|------|------|
| 数据采集 | Prometheus 指标（自动） | — |
| 持久化 | agent_diagnosis_log（事件级，只存不挖） | 趋势快照（做基线对比用） |
| 聚合 | AgentMonitorService | — |
| 暴露 | 5 个 REST + 1 个 WebSocket | — |
| 分析 | — | 趋势分析、异常检测、关联归因 |
| 决策 | — | 主动告警、每日报告、自然语言查询 |

当前链路：`Prometheus 指标 → AgentMonitorService 聚合 → API 暴露 → Admin 前端`。其中分析、决策、主动输出全部缺失——Admin 必须盯着看板才能发现问题，系统不会自己说话。

### 2. 目标架构

```
                    AgentOpsEngine (新增)
                    ┌─────────────────────────────────────┐
                    │  定时任务 (BackgroundScheduler)       │
                    │  ├─ health_scan (每15min)            │
                    │  ├─ daily_report (每日08:07)         │
                    │  └─ take_snapshot (每30min)          │
                    │                                      │
                    │  LLM 分析层                          │
                    │  ├─ analyze_health() 趋势分析        │
                    │  ├─ detect_anomalies() 基线对比      │
                    │  ├─ correlate_failures() 关联归因    │
                    │  └─ chat_query() 自然语言查询        │
                    │                                      │
                    │  输出通道                            │
                    │  ├─ health_scan → WebSocket 推送     │
                    │  ├─ health_scan → notifier 告警      │
                    │  ├─ daily_report → API + WebSocket   │
                    │  └─ chat → API 直接返回              │
                    └──────────┬──────────────────────────┘
                               │ 读取
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
   AgentMonitorService  AgentHealthDB    agent_health_snapshot
   (已有，聚合层)        (已有，事件库)    (新增，趋势快照)
```

### 3. 新增文件：`backend/services/admin_service/agent_ops.py`

```python
"""
AgentOpsEngine：LLM 驱动的智能运维引擎

设计原则：
- 所有数据源来自现有 AgentMonitorService + AgentHealthDB，不做重复采集
- LLM 仅做分析和决策，不做数据搬运
- 定时任务使用独立 BackgroundScheduler（与 radar scheduler 解耦）
- 所有异步路径有 try/except 保护，运维引擎崩溃不影响 Agent 主流程
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from openai import OpenAI

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("admin.agent_ops")


class AgentOpsEngine:
    """智能运维引擎 — 在 AgentMonitorService 之上的 LLM 分析决策层"""

    def __init__(self):
        self._monitor = None  # 惰性初始化，避免循环导入
        self._llm_client = None
        self._scheduler: Optional[BackgroundScheduler] = None

    # ──────────────── 惰性初始化 ────────────────

    @property
    def monitor(self):
        if self._monitor is None:
            from .agent_monitor import get_agent_monitor
            self._monitor = get_agent_monitor()
        return self._monitor

    @property
    def llm(self):
        if self._llm_client is None:
            self._llm_client = OpenAI(
                api_key=settings.DEFAULT_API_KEY,
                base_url=settings.DEFAULT_BASE_URL,
            )
        return self._llm_client

    # ──────────────── 定时任务调度 ────────────────

    def start(self):
        """启动运维定时任务（在 gateway lifespan 中调用）"""
        if self._scheduler is not None:
            return False, "Ops 调度器已运行"

        self._scheduler = BackgroundScheduler(daemon=True)
        self._scheduler.add_job(
            self._run_health_scan,
            IntervalTrigger(minutes=15),
            id="ops_health_scan",
            name="Agent 健康巡检",
            misfire_grace_time=120,
        )
        self._scheduler.add_job(
            self._run_daily_report,
            CronTrigger(hour=8, minute=7),
            id="ops_daily_report",
            name="Agent 每日健康简报",
            misfire_grace_time=300,
        )
        self._scheduler.add_job(
            self._run_snapshot,
            IntervalTrigger(minutes=30),
            id="ops_snapshot",
            name="Agent 指标快照",
            misfire_grace_time=300,
        )
        self._scheduler.start()
        logger.info("[AgentOps] 智能运维调度器已启动 (巡检/15min + 简报/每日 + 快照/30min)")
        return True, "智能运维调度器已启动"

    def stop(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            logger.info("[AgentOps] 智能运维调度器已停止")
            return True, "已停止"
        return True, "调度器未运行"

    # ──────────────── 核心能力 1：定时健康巡检 ────────────────

    async def _run_health_scan(self):
        """每 15 分钟执行：采集 → LLM 分析 → 异常判断 → 推送"""
        try:
            result = await self.health_scan()
            logger.info(f"[AgentOps] 健康巡检完成, alerts={len(result.get('alerts', []))}")
            await self._broadcast_health(result)
            if result.get("alerts"):
                await self._push_alerts(result["alerts"])
        except Exception as e:
            logger.error(f"[AgentOps] 健康巡检异常: {e}", exc_info=True)

    async def health_scan(self, admin_id: str = "") -> Dict[str, Any]:
        """
        全量健康巡检：采集当前指标 + 近期快照 → LLM 趋势分析 → 异常标记。
        返回 {timestamp, overview, tools, analysis, alerts, recommendations}
        """
        overview = self.monitor.get_overview()
        tools = self.monitor.get_tool_health()
        sessions = self.monitor.get_session_stats(limit=20)
        recent_diagnosis = self.monitor.get_diagnosis_events(limit=30)
        baseline = self._get_baseline(hours=24)

        context = self._build_health_context(overview, tools, sessions,
                                             recent_diagnosis, baseline)
        analysis = await self._llm_analyze_health(context)
        rule_alerts = self._rule_based_alerts(overview, tools, baseline)

        return {
            "timestamp": datetime.now().isoformat(),
            "overview": overview,
            "tools": tools,
            "analysis": analysis.get("summary", ""),
            "alerts": rule_alerts + analysis.get("alerts", []),
            "recommendations": analysis.get("recommendations", []),
            "trend": analysis.get("trend", "stable"),
        }

    # ──────────────── 核心能力 2：每日健康简报 ────────────────

    async def _run_daily_report(self):
        """每日执行：生成过去 24h 结构化健康简报"""
        try:
            report = await self.daily_report()
            logger.info(f"[AgentOps] 每日简报生成完成, {len(report)} 字符")
            await self._broadcast_health({"type": "daily_report", "content": report})
        except Exception as e:
            logger.error(f"[AgentOps] 每日简报生成异常: {e}", exc_info=True)

    async def daily_report(self, admin_id: str = "") -> str:
        """生成过去 24h 的 Agent 健康简报"""
        overview = self.monitor.get_overview()
        tools = self.monitor.get_tool_health()
        diagnosis_24h = self.monitor.health_db.get_diagnosis_since(hours=24, limit=100)
        baseline = self._get_baseline(hours=24)
        sessions = self.monitor.get_session_stats(limit=50)
        active_count = self.monitor._get_active_session_count()

        context = self._build_daily_context(overview, tools, diagnosis_24h,
                                            baseline, sessions, active_count)
        prompt = self._daily_report_prompt(context)
        result = await self._call_llm(prompt)
        return result or "每日简报生成失败，请稍后重试"

    # ──────────────── 核心能力 3：自然语言查询 ────────────────

    async def chat_query(self, question: str, admin_id: str = "") -> str:
        """Admin 自然语言查询：采集当前全量指标作为上下文，LLM 回答"""
        if not question.strip():
            return "请描述你想了解的问题。"

        overview = self.monitor.get_overview()
        tools = self.monitor.get_tool_health()
        recent_diag = self.monitor.get_diagnosis_events(limit=30)
        baseline = self._get_baseline(hours=24)

        context = self._build_health_context(overview, tools, [],
                                             recent_diag, baseline)
        prompt = self._chat_prompt(context, question)
        result = await self._call_llm(prompt)
        return result or "抱歉，暂时无法回答这个问题，请稍后重试。"

    # ──────────────── 核心能力 4：定时快照 ────────────────

    async def _run_snapshot(self):
        """每 30 分钟：采集指标快照，用于趋势对比"""
        try:
            overview = self.monitor.get_overview()
            tools = self.monitor.get_tool_health()
            self._save_snapshot(overview, tools)
        except Exception as e:
            logger.error(f"[AgentOps] 快照采集异常: {e}", exc_info=True)

    def _save_snapshot(self, overview: Dict, tools: List[Dict]):
        from .agent_health_db import AgentHealthDB
        db = AgentHealthDB()
        db.insert_snapshot(
            total_turns=overview["agent"]["total_turns"],
            total_tool_calls=overview["agent"]["total_tool_calls"],
            tool_error_rate=overview["agent"]["tool_error_rate"],
            active_sessions=overview["agent"]["active_sessions"],
            memory_records=overview["memory"]["total_records"],
            open_circuits=overview["circuit"]["open_count"],
            tool_details=json.dumps(tools, ensure_ascii=False),
        )

    def _get_baseline(self, hours: int = 24) -> List[Dict]:
        from .agent_health_db import AgentHealthDB
        db = AgentHealthDB()
        return db.get_snapshots(hours=hours)

    # ──────────────── LLM 调用 ────────────────

    async def _llm_analyze_health(self, context: str) -> Dict[str, Any]:
        prompt = f"""你是一个 Agent 系统运维专家。根据以下实时指标数据，分析当前系统健康状态。

{context}

请严格按以下 JSON 格式输出（不要其他内容）：
{{
  "summary": "2-3 句话概括当前系统整体健康状态",
  "trend": "stable|degrading|improving|critical",
  "alerts": [
    {{"level": "warning|critical", "tool": "工具名", "message": "告警描述", "suggestion": "建议操作"}}
  ],
  "recommendations": ["具体可执行的优化建议"]
}}

分析要点：
- 工具错误率是否异常（超过 10% 需关注，超过 30% 需告警）
- 是否有熔断器处于 open 状态
- 活跃会话数是否异常波动
- 诊断事件中是否有重复出现的错误模式
- 对比历史基线判断趋势"""

        result = await self._call_llm(prompt)
        try:
            return json.loads(result) if result else {}
        except json.JSONDecodeError:
            if result and "```json" in result:
                try:
                    return json.loads(result.split("```json")[1].split("```")[0])
                except Exception:
                    pass
            return {"summary": result or "", "trend": "stable", "alerts": [], "recommendations": []}

    async def _call_llm(self, prompt: str) -> Optional[str]:
        try:
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self.llm.chat.completions.create(
                    model=settings.DEFAULT_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                )
            )
            if resp.choices and resp.choices[0].message.content:
                return resp.choices[0].message.content.strip()
            return None
        except Exception as e:
            logger.error(f"[AgentOps] LLM 调用失败: {e}")
            return None

    # ──────────────── 规则层：硬阈值异常检测 ────────────────

    def _rule_based_alerts(self, overview: Dict, tools: List[Dict],
                           baseline: List[Dict]) -> List[Dict]:
        """不依赖 LLM 的硬阈值检测（LLM 可能遗漏，规则层作为安全网）"""
        alerts = []

        err_rate = overview["agent"]["tool_error_rate"]
        if err_rate > 0.3:
            alerts.append({
                "level": "critical", "tool": "*",
                "message": f"全局工具错误率达到 {err_rate:.1%}，严重超标",
                "suggestion": "立即检查 LLM API 连通性和各工具依赖服务状态",
            })
        elif err_rate > 0.1:
            alerts.append({
                "level": "warning", "tool": "*",
                "message": f"全局工具错误率 {err_rate:.1%}，超过关注阈值 10%",
                "suggestion": "排查错误率最高的工具，检查是否有公共依赖异常",
            })

        for t in tools:
            if t["total_calls"] >= 5 and t["success_rate"] < 0.5:
                alerts.append({
                    "level": "warning", "tool": t["tool"],
                    "message": f"工具 {t['tool']} 成功率仅 {t['success_rate']:.0%}（{t['error_count']}/{t['total_calls']}）",
                    "suggestion": f"检查 {t['tool']} 的依赖服务或参数格式",
                })

        open_circuits = overview["circuit"]["open_count"]
        if open_circuits > 0:
            open_names = [b["name"] for b in overview["circuit"]["breakers"]
                         if b["state"] == "open"]
            alerts.append({
                "level": "critical" if open_circuits >= 3 else "warning",
                "tool": ", ".join(open_names),
                "message": f"{open_circuits} 个工具处于熔断状态: {', '.join(open_names)}",
                "suggestion": "熔断工具将在 30s 后自动半开探测，若反复熔断需人工介入",
            })

        if baseline:
            recent_avg = sum(
                b.get("active_sessions", 0) for b in baseline[-6:]
            ) / max(len(baseline[-6:]), 1)
            current = overview["agent"]["active_sessions"]
            if recent_avg > 0 and current < recent_avg * 0.5:
                alerts.append({
                    "level": "warning", "tool": "*",
                    "message": f"活跃会话从基线 {recent_avg:.0f} 骤降至 {current}",
                    "suggestion": "检查前端服务是否正常，或是否有用户大规模掉线",
                })

        return alerts

    # ──────────────── 输出通道 ────────────────

    async def _broadcast_health(self, payload: Dict):
        try:
            from backend.services.admin_service.api import _ws_connections
            stale = set()
            for ws in list(_ws_connections):
                try:
                    await ws.send_json(payload)
                except Exception:
                    stale.add(id(ws))
            for s in stale:
                try:
                    _ws_connections.discard(s)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[AgentOps] WebSocket 广播失败: {e}")

    async def _push_alerts(self, alerts: List[Dict]):
        try:
            from backend.services.radar_service.notifier import send_alert
            for alert in alerts[:3]:
                send_alert(
                    owner_id="admin",
                    keyword=f"[AgentOps] {alert.get('tool', 'System')}",
                    platform="system",
                    risk_level=5 if alert["level"] == "critical" else 3,
                    risk_class="critical" if alert["level"] == "critical" else "medium",
                    core_issue=alert["message"],
                    report=f"建议: {alert.get('suggestion', '')}",
                    post_count=1,
                    urls=[],
                )
        except Exception as e:
            logger.error(f"[AgentOps] 告警推送失败: {e}")

    # ──────────────── 上下文构建 ────────────────

    def _build_health_context(self, overview: Dict, tools: List[Dict],
                              sessions: List[Dict], diagnosis: List[Dict],
                              baseline: List[Dict]) -> str:
        parts = []

        parts.append("=== 当前 Agent 概览 ===")
        parts.append(f"总轮次: {overview['agent']['total_turns']}")
        parts.append(f"总工具调用: {overview['agent']['total_tool_calls']}")
        parts.append(f"工具错误率: {overview['agent']['tool_error_rate']:.1%}")
        parts.append(f"24h 活跃会话: {overview['agent']['active_sessions']}")
        parts.append(f"记忆库总量: {overview['memory']['total_records']}")
        parts.append(f"熔断开路数: {overview['circuit']['open_count']}")

        if tools:
            parts.append("\n=== 工具健康明细（按错误量降序）===")
            for t in tools[:10]:
                parts.append(
                    f"  {t['tool']}: 调用{t['total_calls']}次, "
                    f"成功率{t['success_rate']:.0%}, 熔断:{t['circuit_state']}"
                )

        if diagnosis:
            parts.append("\n=== 最近诊断事件（最近 30 条）===")
            error_types = {}
            for d in diagnosis:
                et = d.get("error_type", "unknown")
                error_types[et] = error_types.get(et, 0) + 1
            for et, count in sorted(error_types.items(), key=lambda x: -x[1]):
                parts.append(f"  {et}: {count} 次")
            parts.append("  最近事件:")
            for d in diagnosis[:5]:
                parts.append(
                    f"    [{d.get('created_at', '')[:19]}] "
                    f"{d.get('tool_name', '?')} → {d.get('error_type', '?')} "
                    f"→ {d.get('recovery_strategy', '?')} "
                    f"({'成功' if d.get('success') else '失败'})"
                )

        if baseline:
            parts.append(f"\n=== 历史基线（最近 {len(baseline)} 个快照）===")
            if len(baseline) >= 2:
                recent = baseline[-6:]
                all_avg_err = sum(b.get("tool_error_rate", 0) for b in baseline) / len(baseline)
                recent_avg_err = sum(b.get("tool_error_rate", 0) for b in recent) / len(recent)
                parts.append(f"  全期平均错误率: {all_avg_err:.2%}")
                parts.append(f"  近 3h 平均错误率: {recent_avg_err:.2%}")
                parts.append(f"  趋势: {'上升' if recent_avg_err > all_avg_err * 1.3 else '下降' if recent_avg_err < all_avg_err * 0.7 else '平稳'}")

        return "\n".join(parts)

    def _build_daily_context(self, overview: Dict, tools: List[Dict],
                             diagnosis: List[Dict], baseline: List[Dict],
                             sessions: List[Dict], active_count: int) -> str:
        ctx = self._build_health_context(overview, tools, sessions, diagnosis, baseline)
        ctx += f"\n\n=== 会话活跃度 ===\n24h 活跃会话数: {active_count}"
        if sessions:
            ctx += f"\n总会话数: {len(sessions)}"
            owners = {}
            for s in sessions:
                oid = (s.get("owner_id") or "legacy")[:12]
                owners[oid] = owners.get(oid, 0) + 1
            ctx += "\n用户分布: " + ", ".join(f"{k}({v})" for k, v in owners.items())
        return ctx

    def _daily_report_prompt(self, context: str) -> str:
        return f"""你是一个 Agent 系统运维分析师。根据过去 24 小时的运维数据，生成一份运维日报。

{context}

请输出结构化的日报（纯文本，不要 JSON）：
1. 总体评估（50 字以内，一句话概括）
2. 关键指标（工具调用量、错误率、活跃用户、熔断情况）
3. 异常事件（按严重程度列出）
4. 趋势判断（相比昨日改善/恶化/持平）
5. 运维建议（1-3 条具体建议）

语气专业简洁，数据引用精确到百分比。"""

    def _chat_prompt(self, context: str, question: str) -> str:
        return f"""你是一个 Agent 系统运维助手，帮助管理员理解和诊断系统运行状态。

当前系统状态数据：
{context}

管理员提问：{question}

请直接回答问题，基于提供的数据给出准确的分析和建议。如数据不足以回答，明确指出需要补充什么信息。"""


# ── 全局单例 ──

_ops_engine: Optional[AgentOpsEngine] = None


def get_agent_ops() -> AgentOpsEngine:
    global _ops_engine
    if _ops_engine is None:
        _ops_engine = AgentOpsEngine()
    return _ops_engine
```

### 4. 修改文件 1：`backend/services/admin_service/agent_health_db.py`

**文件顶部**：`from datetime import datetime` 改为 `from datetime import datetime, timedelta`，新增 `from typing import Dict, List`。

**`_init_db()` 末尾**新增建表语句：

```python
c.execute("""
    CREATE TABLE IF NOT EXISTS agent_health_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_turns INTEGER DEFAULT 0,
        total_tool_calls INTEGER DEFAULT 0,
        tool_error_rate REAL DEFAULT 0,
        active_sessions INTEGER DEFAULT 0,
        memory_records INTEGER DEFAULT 0,
        open_circuits INTEGER DEFAULT 0,
        tool_details TEXT DEFAULT '[]',
        created_at TEXT NOT NULL
    )
""")
c.execute("""
    CREATE INDEX IF NOT EXISTS idx_snapshot_created
    ON agent_health_snapshot(created_at DESC)
""")
```

**`AgentHealthDB` 类**新增 4 个方法：`insert_snapshot()`、`get_snapshots(hours)`、`get_diagnosis_since(hours)`、`cleanup_snapshots(keep_hours)`。完整代码见上文 10.4 节。

### 5. 修改文件 2：`backend/services/admin_service/api.py`

**文件顶部**新增 `from pydantic import BaseModel` 和 `from datetime import datetime`。

**`router` 定义之后**新增 `_ws_connections: set = set()` 供 OpsEngine 广播。

**新增 3 个端点**：

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/admin/agents/report` | GET | 健康巡检报告（LLM 分析 + 异常 + 建议） |
| `/api/admin/agents/report/daily` | GET | 过去 24h 运维日报 |
| `/api/admin/agents/chat` | POST | 自然语言查询（`{"question": "..."}`） |

**WebSocket 函数修改**：`accept()` 后加 `_ws_connections.add(websocket)`，结束分支加 `finally: _ws_connections.discard(websocket)`。

### 6. 修改文件 3：`backend/gateway/main.py`

**lifespan → startup**：在 radar `scheduler_start` 之后追加：

```python
try:
    from backend.services.admin_service.agent_ops import get_agent_ops
    ops_success, ops_msg = get_agent_ops().start()
    if ops_success:
        logger.info(f"[Gateway] {ops_msg}")
    else:
        logger.warning(f"[Gateway] Ops 调度器: {ops_msg}")
except Exception as e:
    logger.error(f"[Gateway] Ops 调度器启动异常: {e}", exc_info=True)
```

**lifespan → shutdown**：在 radar `scheduler_stop` 之前追加对应的 `get_agent_ops().stop()`。

### 7. 修改文件 4：`backend/services/admin_service/__init__.py`

新增 `get_agent_ops` 导出。

### 8. 与现有组件的集成关系

| 现有组件 | 怎么用 | 说明 |
|----------|--------|------|
| `AgentMonitorService` | `get_agent_monitor()` 直接调用 | 只读，不改一行 |
| `AgentHealthDB` | 新增 4 方法 + 1 表 | 纯增量 |
| `notifier.send_alert()` | 检测到异常时调用 | 走 Admin 已有推送通道 |
| `APScheduler` | 独立实例，不与 radar scheduler 共享 | 完全解耦 |
| `settings.DEFAULT_*` | 复用默认模型配置 | 复用 |
| `gateway/main.py` lifespan | start/stop 对齐 radar scheduler 模式 | 对齐现有模式 |

### 9. 关键安全设计

- **LLM 分析失败不阻断运维**：全部 `try/except` 包裹，LLM 挂了仍输出规则层告警
- **告警频控**：`_push_alerts` 每次最多推 3 条，health_scan 间隔 15min
- **快照 TTL**：7 天自动清理（48 条/天 × 7 天 = 336 条，总计 < 1MB）
- **不阻塞 Agent 主流程**：OpsEngine 崩溃不影响 Agent 对话和工具调用，完全旁路

### 10. 实施清单

| 步骤 | 内容 | 预计 |
|------|------|------|
| 1 | `agent_health_db.py` 新增 snapshot 表 + 4 方法 | 15 min |
| 2 | 创建 `agent_ops.py`（完整实现） | 45 min |
| 3 | `api.py` 新增 3 端点 + WebSocket 连接集合 | 15 min |
| 4 | `gateway/main.py` 启动/停止 Ops 调度器 | 5 min |
| 5 | `__init__.py` 导出新类 | 2 min |
| 6 | 集成测试：curl + WebSocket 验证 | 20 min |
| **总计** | | **~100 min** |

### 11. 智能运维成熟度对比

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| 数据采集 | Prometheus 指标（自动） | 同左 + 定时快照（30min 粒度） |
| 趋势分析 | 无 | LLM 分析 + 基线对比 |
| 异常检测 | 无 | LLM 判断 + 规则硬阈值双保险 |
| 主动告警 | 无 | WebSocket + notifier 双通道 |
| 每日报告 | 无 | LLM 生成结构化日报 |
| 自然语言查询 | 无 | Admin 直接用中文问系统状态 |
| 故障归因 | 无 | LLM 关联分析跨工具、跨时间失败模式 |

### 12. 为什么这才是真正的"智能"

1. **LLM 做真正的分析，不是 if-else**：趋势判断、异常关联、自然语言报告这三个能力是规则引擎做不到的。规则层只做硬阈值兜底，语义层由 LLM 负责。

2. **三层输出形成闭环**：定时巡检（主动发现）→ 自然语言查询（被动响应）→ 每日简报（定期总结），覆盖运维的全部核心场景。

3. **零外部依赖**：不引入 Prometheus Server、Grafana、PagerDuty 等外部系统，Python + SQLite + OpenAI SDK 全部搞定。

4. **与项目 Agent 体系同构**：AgentOpsEngine 本质上是一个"运维 Agent"——采集数据、调用 LLM 做决策、通过工具输出。和诊断引擎、反思引擎是同一套设计哲学，可以自然演进为注册在 Agent 工具集中的"运维工具"。
