"""
AgentOpsEngine：LLM 驱动的智能运维引擎

Design doc: ADMIN_AGENT_MONITOR.md §3
原则：
- 所有数据源来自现有 AgentMonitorService + AgentHealthDB，不做重复采集
- LLM 仅做分析和决策，不做数据搬运
- 定时任务使用独立 BackgroundScheduler（与 radar scheduler 解耦）
- 所有异步路径有 try/except 保护，运维引擎崩溃不影响 Agent 主流程
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from openai import OpenAI

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("admin.agent_ops")


class AgentOpsEngine:
    """智能运维引擎 — 在 AgentMonitorService 之上的 LLM 分析决策层"""

    def __init__(self):
        self._monitor = None  # 惰性初始化，避免循环导入
        self._llm_client: Optional[OpenAI] = None
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
        active_count = self._get_active_session_count()

        context = self._build_daily_context(overview, tools, diagnosis_24h,
                                            baseline, sessions, active_count)
        prompt = self._daily_report_prompt(context)
        result = await self._call_llm(prompt)
        return result or "每日简报生成失败，请稍后重试"

    # ──────────────── 核心能力 3：自然语言查询 ────────────────

    async def chat_query(self, question: str, admin_id: str = "") -> str:
        """Admin 自然语言查询（★ 弱点4 增强版：注入工作流上下文）"""
        return await self.chat_query_enhanced(question, admin_id)

    async def chat_query_enhanced(self, question: str, admin_id: str = "") -> str:
        """Admin 自然语言查询（弱点4 增强版）。

        从问题中识别工作流 ID，注入该工作流的详细执行历史和趋势。
        """
        if not question.strip():
            return "请描述你想了解的问题。"

        overview = self.monitor.get_overview()
        tools = self.monitor.get_tool_health()
        recent_diag = self.monitor.get_diagnosis_events(limit=30)
        baseline = self._get_baseline(hours=24)

        context = self._build_health_context(overview, tools, [],
                                             recent_diag, baseline)
        extra = self._extract_workflow_context(question)
        if extra:
            context += extra
        prompt = self._chat_prompt(context, question)
        result = await self._call_llm(prompt)
        return result or "抱歉，暂时无法回答这个问题，请稍后重试。"

    def _extract_workflow_context(self, question: str) -> str:
        """从问题中识别工作流 ID，注入该工作流的最近 10 次执行 + 7 天趋势。"""
        import re
        wf_ids = []
        for pattern in [r'工作流\s*(\d+)', r'workflow\s*(\d+)', r'wf\s*(\d+)',
                        r'工作流\s*id\s*[=:]\s*(\d+)', r'#(\d+)']:
            matches = re.findall(pattern, question, re.IGNORECASE)
            wf_ids.extend(int(m) for m in matches)
        wf_ids = list(dict.fromkeys(wf_ids))[:5]

        if not wf_ids:
            return ""

        parts = []
        try:
            from .agent_health_db import AgentHealthDB
            db = AgentHealthDB()
            for wf_id in wf_ids:
                recent_logs = db.get_workflow_logs(workflow_id=wf_id, limit=10, hours=168)
                if recent_logs:
                    parts.append(f"\n=== 工作流 {wf_id} 最近 10 次执行 ===")
                    for log in recent_logs:
                        parts.append(
                            f"- [{log['created_at'][:19]}] {log['status']} "
                            f"step{log['failed_step']}/{log['total_steps']} "
                            f"耗时{log.get('duration_seconds', 0):.1f}s "
                            f"err={log.get('error_message', '')[:120]}"
                        )

                trend = db.get_workflow_trend(wf_id, hours=168)
                if trend.get("daily"):
                    parts.append(f"\n=== 工作流 {wf_id} 7 天趋势 ===")
                    parts.append(
                        f"总执行: {trend['summary']['total_executions']} 次, "
                        f"成功率: {trend['summary']['success_rate']:.0%}, "
                        f"平均耗时: {trend['summary']['avg_duration_seconds']}s"
                    )
                    for d in trend["daily"]:
                        parts.append(
                            f"  {d['date']}: {d['success']}/{d['total']} "
                            f"({d['success_rate']:.0%}), avg {d['avg_duration']}s"
                        )
                    if trend.get("top_errors"):
                        parts.append("Top 失败原因:")
                        for err in trend["top_errors"]:
                            parts.append(f"  - {err['error_message'][:100]} (×{err['count']})")
        except Exception as e:
            logger.warning(f"[AgentOps] 提取工作流上下文失败: {e}")

        return "\n".join(parts) if parts else ""

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
        snapshot_id = db.insert_snapshot(
            total_turns=overview["agent"]["total_turns"],
            total_tool_calls=overview["agent"]["total_tool_calls"],
            tool_error_rate=overview["agent"]["tool_error_rate"],
            active_sessions=overview["agent"]["active_sessions"],
            memory_records=overview["memory"]["total_records"],
            open_circuits=overview["circuit"]["open_count"],
            tool_details=json.dumps(tools, ensure_ascii=False),
        )
        # P7: 追加工作流/规划字段
        if snapshot_id:
            wf = overview.get("workflows", {})
            plan = overview.get("planning", {})
            db.update_snapshot_with_workflow(
                snapshot_id=snapshot_id,
                workflow_total=wf.get("total_executions_24h", 0),
                workflow_failed=wf.get("failed_count", 0),
                workflow_cancelled=wf.get("cancelled_count", 0),
                plan_success_rate=plan.get("success_rate", 0),
                plan_template_hit_rate=plan.get("template_hit_rate", 0),
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

        # P7: 工作流失败率检查
        wf = overview.get("workflows", {})
        if wf.get("total_executions_24h", 0) >= 5 and wf.get("success_rate", 1) < 0.8:
            alerts.append({
                "level": "warning", "tool": "workflow",
                "message": (
                    f"过去24h工作流成功率仅 {wf['success_rate']:.0%}"
                    f"（{wf['failed_count']}/{wf['total_executions_24h']}）"
                ),
                "suggestion": "检查失败的工作流，确认是否因工具异常或参数错误导致",
            })

        # P7: 规划回退率检查
        plan = overview.get("planning", {})
        if plan.get("total_plans", 0) >= 20:
            sr = plan.get("success_rate", 1)
            if sr < 0.7:
                alerts.append({
                    "level": "warning", "tool": "phase_plan",
                    "message": f"规划成功率仅 {sr:.0%}，LLM 可能异常",
                    "suggestion": "检查 LLM API 连通性和模型响应格式",
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
            from backend.services.platform_service.notifier import send_alert
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

    # ──────────────── 辅助 ────────────────

    def _get_active_session_count(self) -> int:
        try:
            from backend.services.agent_service.memory.memory_store import AgentMemoryStore
            return AgentMemoryStore().count_active_sessions(24)
        except Exception:
            return 0


# ── 全局单例 ──

_ops_engine: Optional[AgentOpsEngine] = None


def get_agent_ops() -> AgentOpsEngine:
    global _ops_engine
    if _ops_engine is None:
        _ops_engine = AgentOpsEngine()
    return _ops_engine
