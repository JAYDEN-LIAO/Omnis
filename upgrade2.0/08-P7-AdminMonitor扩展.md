# P7 — Admin Monitor 同步改进

> 依赖：P4（工作流执行日志落库）、P5（工作流管理工具）
> 目标：Admin 监控看板覆盖工作流执行、规划阶段、工具分类三个新维度
> 原则：只做增量，不动现有监控逻辑

## 一、新增 Prometheus 指标（★ R-016 修订：去掉 workflow_id label）

```python
# backend/core/metrics.py 末尾追加

# ──────────────── v2.0：工作流 + 规划监控 ────────────────

# 工作流执行指标（不带 workflow_id label，避免时序爆炸）
WORKFLOW_EXECUTIONS_TOTAL = Counter(
    "workflow_executions_total",
    "Workflow execution count by status",
    ["status"]  # status: success / failed / cancelled
)
WORKFLOW_EXECUTION_DURATION = Histogram(
    "workflow_execution_duration_seconds",
    "Workflow execution duration in seconds",
    buckets=[5, 15, 30, 60, 120, 300, 600]
)

# 规划阶段指标
AGENT_PLAN_GENERATION_TOTAL = Counter(
    "agent_plan_generation_total",
    "Plan generation count by status",
    ["status"]  # status: success / fallback / template_hit / parse_error
)
```

> **R-016 关键**：不带 `workflow_id` label。每个工作流 ID 都不同，若作为 label 会导致 Prometheus 时序数随工作流数量线性增长（每 1000 个工作流 → 1000 条 histogram）。

埋点位置（`scheduler.py` `_execute_workflow_row`）：

```python
from backend.core.metrics import (
    WORKFLOW_EXECUTIONS_TOTAL, WORKFLOW_EXECUTION_DURATION,
)

# 成功
WORKFLOW_EXECUTIONS_TOTAL.labels(status="success").inc()
WORKFLOW_EXECUTION_DURATION.observe(duration)

# 失败
WORKFLOW_EXECUTIONS_TOTAL.labels(status="failed").inc()

# 取消
WORKFLOW_EXECUTIONS_TOTAL.labels(status="cancelled").inc()
```

## 二、新增数据库表

### 2.1 workflow_execution_log 表

```sql
-- agent_health_db.py — _init_db() 末尾新增
CREATE TABLE IF NOT EXISTS workflow_execution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL DEFAULT 0,
    workflow_name TEXT NOT NULL DEFAULT '',
    owner_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,         -- success / failed / cancelled
    duration_seconds REAL DEFAULT 0,
    total_steps INTEGER DEFAULT 0,
    failed_step INTEGER DEFAULT 0,
    error_message TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wflog_workflow ON workflow_execution_log(workflow_id);
CREATE INDEX IF NOT EXISTS idx_wflog_owner ON workflow_execution_log(owner_id);
CREATE INDEX IF NOT EXISTS idx_wflog_created ON workflow_execution_log(created_at);
CREATE INDEX IF NOT EXISTS idx_wflog_status ON workflow_execution_log(status);
```

### 2.2 snapshot 表迁移（★ R-017 修订：ALTER TABLE 幂等）

```python
# agent_health_db.py — _init_db() 中追加
def _migrate_snapshot_table(cursor):
    """给 agent_health_snapshot 表加工作流/规划字段（幂等迁移）"""
    fields = [
        ("workflow_total", "INTEGER DEFAULT 0"),
        ("workflow_failed", "INTEGER DEFAULT 0"),
        ("workflow_cancelled", "INTEGER DEFAULT 0"),
        ("plan_success_rate", "REAL DEFAULT 0"),
        ("plan_template_hit_rate", "REAL DEFAULT 0"),
    ]
    for col, decl in fields:
        try:
            cursor.execute(f"ALTER TABLE agent_health_snapshot ADD COLUMN {col} {decl}")
        except Exception:
            pass  # 已存在则跳过（SQLite 不支持 IF NOT EXISTS）


# 在 _init_db() 末尾调用：
# _migrate_snapshot_table(c)
```

> **R-017 关键**：SQLite 旧版本不支持 `ALTER TABLE ADD COLUMN IF NOT EXISTS`，
> 必须用 try/except 模式。已在 `memory_store.py` 的存量表迁移用过同款。

### 2.3 AgentHealthDB 新增方法

```python
# agent_health_db.py — AgentHealthDB 类追加

def insert_workflow_log(self, workflow_id: int, workflow_name: str,
                        owner_id: str, status: str, duration_seconds: float,
                        total_steps: int, failed_step: int,
                        error_message: str) -> int:
    """写入工作流执行日志"""
    with self._get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO workflow_execution_log
            (workflow_id, workflow_name, owner_id, status, duration_seconds,
             total_steps, failed_step, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (workflow_id, workflow_name, owner_id, status,
              duration_seconds, total_steps, failed_step,
              error_message[:1000] if error_message else "",
              datetime.now().isoformat()))
        conn.commit()
        return c.lastrowid


def get_workflow_logs(self, owner_id: str = "", workflow_id: int = 0,
                      hours: int = 24, limit: int = 50) -> List[Dict]:
    """查询工作流执行日志（多维过滤）"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    where = ["created_at >= ?"]
    params = [cutoff]
    if owner_id:
        where.append("owner_id = ?")
        params.append(owner_id)
    if workflow_id:
        where.append("workflow_id = ?")
        params.append(workflow_id)
    with self._get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(f"""
            SELECT * FROM workflow_execution_log
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC LIMIT ?
        """, params + [limit])
        return [dict(r) for r in c.fetchall()]


def get_workflow_stats(self, hours: int = 24) -> Dict:
    """工作流执行统计：总数/成功/失败/取消/平均耗时"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with self._get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count,
                SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancelled_count,
                AVG(duration_seconds) AS avg_duration
            FROM workflow_execution_log
            WHERE created_at >= ?
        """, (cutoff,))
        r = dict(c.fetchone())
        total = r.get("total") or 0
        return {
            "total_executions": total,
            "success_count": r.get("success_count") or 0,
            "failed_count": r.get("failed_count") or 0,
            "cancelled_count": r.get("cancelled_count") or 0,
            "success_rate": (r.get("success_count") or 0) / max(total, 1),
            "avg_duration_seconds": round(r.get("avg_duration") or 0, 1),
        }


def update_snapshot_with_workflow(self, snapshot_id: int,
                                  workflow_total: int, workflow_failed: int,
                                  workflow_cancelled: int,
                                  plan_success_rate: float,
                                  plan_template_hit_rate: float):
    """更新 snapshot 的工作流/规划字段（P7 写入）"""
    with self._get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE agent_health_snapshot
            SET workflow_total=?, workflow_failed=?, workflow_cancelled=?,
                plan_success_rate=?, plan_template_hit_rate=?
            WHERE id=?
        """, (workflow_total, workflow_failed, workflow_cancelled,
              plan_success_rate, plan_template_hit_rate, snapshot_id))
        conn.commit()


def get_workflow_trend(self, workflow_id: int, hours: int = 168) -> Dict:
    """★ 弱点3：单工作流的执行趋势（每日成功率/平均耗时/Top 失败原因）。

    返回结构：
    {
        "workflow_id": int,
        "hours": int,
        "daily": [{"date": "2026-06-14", "total": 5, "success": 4, "success_rate": 0.8, "avg_duration": 12.3}, ...],
        "top_errors": [{"error_message": "...", "count": 3}, ...],
        "summary": {"total_executions": 20, "success_rate": 0.85, "avg_duration": 15.2}
    }
    """
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with self._get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # 1. 总体统计
        c.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count,
                   AVG(duration_seconds) AS avg_duration
            FROM workflow_execution_log
            WHERE workflow_id=? AND created_at >= ?
        """, (workflow_id, cutoff))
        summary_row = dict(c.fetchone())
        total = summary_row.get("total") or 0
        summary = {
            "total_executions": total,
            "success_rate": (summary_row.get("success_count") or 0) / max(total, 1),
            "avg_duration_seconds": round(summary_row.get("avg_duration") or 0, 1),
        }

        # 2. 按天聚合（每日成功率）
        c.execute("""
            SELECT DATE(created_at) AS date,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count,
                   AVG(duration_seconds) AS avg_duration
            FROM workflow_execution_log
            WHERE workflow_id=? AND created_at >= ?
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """, (workflow_id, cutoff))
        daily = []
        for r in c.fetchall():
            day_total = r["total"]
            daily.append({
                "date": r["date"],
                "total": day_total,
                "success": r["success_count"] or 0,
                "success_rate": (r["success_count"] or 0) / max(day_total, 1),
                "avg_duration": round(r["avg_duration"] or 0, 1),
            })

        # 3. Top 失败原因
        c.execute("""
            SELECT error_message, COUNT(*) AS count
            FROM workflow_execution_log
            WHERE workflow_id=? AND created_at >= ?
                  AND status='failed' AND error_message != ''
            GROUP BY error_message
            ORDER BY count DESC
            LIMIT 3
        """, (workflow_id, cutoff))
        top_errors = [{"error_message": r["error_message"][:200], "count": r["count"]}
                      for r in c.fetchall()]

        return {
            "workflow_id": workflow_id,
            "hours": hours,
            "summary": summary,
            "daily": daily,
            "top_errors": top_errors,
        }
```

## 三、AgentMonitorService 扩展

```python
# agent_monitor.py — AgentMonitorService 新增方法

def get_workflow_stats(self, owner_id: str = "", hours: int = 24) -> Dict:
    return self.health_db.get_workflow_stats(hours=hours)


def get_planning_stats(self) -> Dict:
    """规划阶段统计（直接从 Prometheus 读）"""
    from backend.core.metrics import AGENT_PLAN_GENERATION_TOTAL
    samples = _sample_counter_by_label(AGENT_PLAN_GENERATION_TOTAL)
    success = samples.get("success", 0)
    fallback = samples.get("fallback", 0)
    template_hit = samples.get("template_hit", 0)
    parse_error = samples.get("parse_error", 0)
    total = success + fallback + template_hit + parse_error
    return {
        "total_plans": total,
        "success_count": success,
        "fallback_count": fallback,
        "template_hit_count": template_hit,
        "parse_error_count": parse_error,
        "success_rate": success / max(total, 1),
        "template_hit_rate": template_hit / max(total, 1),
    }


def get_overview(self) -> Dict[str, Any]:
    """扩展：加入 workflows + planning 段"""
    tool_stats = self._get_tool_call_summary()
    mem = self._get_counter_sum_by_label(AGENT_MEMORY_WRITES, "status")
    mem_success, mem_error = mem.get("success", 0), mem.get("error", 0)
    circuit = self._get_circuit_summary()
    mem_store = self._get_memory_store_stats()
    wf_stats = self.health_db.get_workflow_stats(hours=24)
    plan_stats = self.get_planning_stats()

    return {
        "agent": {
            "total_turns": self._get_counter_value(AGENT_TURNS),
            "total_tool_calls": tool_stats["total"],
            "tool_error_rate": round(tool_stats["error_rate"], 3),
            "active_sessions": self._get_active_session_count(),
        },
        "memory": {
            "write_success": mem_success,
            "write_error": mem_error,
            "total_records": mem_store["total"],
            "breakdown": mem_store.get("breakdown", {}),
        },
        "circuit": {
            "open_count": circuit["open_count"],
            "breakers": circuit["details"],
        },
        "workflows": {
            "total_executions_24h": wf_stats["total_executions"],
            "success_count": wf_stats["success_count"],
            "failed_count": wf_stats["failed_count"],
            "cancelled_count": wf_stats["cancelled_count"],
            "success_rate": round(wf_stats["success_rate"], 3),
            "avg_duration_seconds": wf_stats["avg_duration_seconds"],
        },
        "planning": {
            "total_plans": plan_stats["total_plans"],
            "success_count": plan_stats["success_count"],
            "fallback_count": plan_stats["fallback_count"],
            "template_hit_count": plan_stats["template_hit_count"],
            "parse_error_count": plan_stats["parse_error_count"],
            "success_rate": round(plan_stats["success_rate"], 3),
            "template_hit_rate": round(plan_stats["template_hit_rate"], 3),
        },
    }
```

## 四、AgentOpsEngine 扩展

```python
# agent_ops.py — AgentOpsEngine 修改

def _rule_based_alerts(self, overview, tools, baseline) -> List[Dict]:
    """扩展：加入工作流 + 规划告警检查"""
    alerts = []
    # ... 原有检查 ...

    # 工作流失败率检查
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

    # 规划回退率检查
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


def _save_snapshot(self, overview: Dict, tools: List[Dict]):
    """扩展：写入工作流 + 规划字段"""
    from .agent_health_db import AgentHealthDB
    db = AgentHealthDB()
    # 主表 INSERT
    snapshot_id = db.insert_snapshot(
        total_turns=overview["agent"]["total_turns"],
        total_tool_calls=overview["agent"]["total_tool_calls"],
        tool_error_rate=overview["agent"]["tool_error_rate"],
        active_sessions=overview["agent"]["active_sessions"],
        memory_records=overview["memory"]["total_records"],
        open_circuits=overview["circuit"]["open_count"],
        tool_details=json.dumps(tools, ensure_ascii=False),
    )
    # 追加字段 UPDATE
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


# ★ 弱点4 补强：chat_query 增强版（注入工作流详细上下文）
async def chat_query_enhanced(self, question: str, admin_id: str = "") -> str:
    """Admin 自然语言查询（弱点4 增强版）。

    从问题中识别工作流 ID，注入该工作流的详细执行历史和趋势。
    上下文深度：overview + tools + diagnosis + baseline + **单工作流历史/趋势**。
    """
    if not question.strip():
        return "请描述你想了解的问题。"

    overview = self.monitor.get_overview()
    tools = self.monitor.get_tool_health()
    recent_diag = self.monitor.get_diagnosis_events(limit=30)
    baseline = self._get_baseline(hours=24)

    context = self._build_health_context(overview, tools, [], recent_diag, baseline)
    extra = self._extract_workflow_context(question)
    if extra:
        context += extra

    prompt = self._chat_prompt(context, question)
    result = await self._call_llm(prompt)
    return result or "抱歉，暂时无法回答这个问题，请稍后重试。"


def _extract_workflow_context(self, question: str) -> str:
    """从问题中识别工作流 ID，注入该工作流的最近 10 次执行 + 7 天趋势。

    支持的提问模式：
    - "工作流 5 为什么..." → 注入 wf_id=5
    - "workflow 12 最近状态" → 注入 wf_id=12
    - "wf 3 失败原因" → 注入 wf_id=3
    - "#5" → 注入 wf_id=5
    """
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
```

> 注：原方案 `chat_query` 调用方保持不变；新方案在 `agent_ops.py` 中用 `chat_query_enhanced` 替换实现，api.py 的 `/chat` 端点改为调用增强版。

## 五、新增 API 端点

```python
# admin_service/api.py 末尾追加

@router.get("/workflows")
async def admin_workflow_stats(
    owner_id: str = Query("", description="按用户过滤（空=全部）"),
    workflow_id: int = Query(0, description="按工作流过滤（0=全部）"),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(50, ge=1, le=500),
    _=Depends(require_admin),
):
    """工作流执行统计 + 最近日志"""
    from .agent_monitor import get_agent_monitor
    monitor = get_agent_monitor()
    stats = monitor.get_workflow_stats(hours=hours)
    logs = monitor.health_db.get_workflow_logs(
        owner_id=owner_id, workflow_id=workflow_id,
        hours=hours, limit=limit,
    )
    return {
        "code": 200,
        "data": {
            "stats": stats,
            "logs": logs,
            "filter": {
                "owner_id": owner_id,
                "workflow_id": workflow_id,
                "hours": hours,
            },
        },
    }


@router.get("/workflows/{workflow_id}")
async def admin_workflow_history(
    workflow_id: int,
    hours: int = Query(168, ge=1, le=720),  # 默认 7 天
    limit: int = Query(100, ge=1, le=1000),
    _=Depends(require_admin),
):
    """单个工作流执行历史"""
    from .agent_monitor import get_agent_monitor
    monitor = get_agent_monitor()
    logs = monitor.health_db.get_workflow_logs(
        workflow_id=workflow_id, hours=hours, limit=limit,
    )
    return {"code": 200, "data": {"workflow_id": workflow_id, "logs": logs}}


# ★ 弱点3 补强：单工作流执行趋势（每日成功率 + Top 失败原因）
@router.get("/workflows/{workflow_id}/trend")
async def admin_workflow_trend(
    workflow_id: int,
    hours: int = Query(168, ge=1, le=720),
    _=Depends(require_admin),
):
    """★ 弱点3：单工作流的执行趋势

    返回：
    - summary: 总执行/成功率/平均耗时
    - daily: 每日聚合成功率 + 平均耗时
    - top_errors: Top 3 失败原因 + 次数
    """
    from .agent_monitor import get_agent_monitor
    monitor = get_agent_monitor()
    trend = monitor.health_db.get_workflow_trend(workflow_id=workflow_id, hours=hours)
    return {"code": 200, "data": trend}


@router.get("/planning")
async def admin_planning_stats(_=Depends(require_admin)):
    """规划阶段统计"""
    from .agent_monitor import get_agent_monitor
    monitor = get_agent_monitor()
    return {"code": 200, "data": monitor.get_planning_stats()}


# Admin 取消任意用户工作流（管理员特权，无 owner 校验）
@router.post("/workflows/{workflow_id}/cancel")
async def admin_cancel_workflow(
    workflow_id: int,
    _=Depends(require_admin),
):
    """Admin 取消任意用户的工作流（无需 owner 校验）"""
    from backend.services.radar_service.scheduler import (
        _WF_CANCEL_EVENTS, _WF_CANCEL_LOCK,
    )
    with _WF_CANCEL_LOCK:
        event = _WF_CANCEL_EVENTS.get(workflow_id)
        if event:
            event.set()
            return {"code": 200, "data": {"cancelled": True}}
    return {"code": 404, "data": {
        "cancelled": False, "message": "工作流未在运行"
    }}
```

## 六、文件改动汇总

| 文件 | 操作 | 内容 |
|------|------|------|
| `core/metrics.py` | 修改 | 新增 3 个 Prometheus 指标（~25 行） |
| `agent_health_db.py` | 修改 | 新增 workflow_execution_log 表 + 5 个方法（含 get_workflow_trend 弱点3）+ snapshot 迁移函数 + update_snapshot_with_workflow（~190 行） |
| `agent_monitor.py` | 修改 | 新增 get_workflow_stats/get_planning_stats + get_overview 扩展（~70 行） |
| `agent_ops.py` | 修改 | health_scan 规则扩展 + _save_snapshot 扩展 + chat_query_enhanced 弱点4 增强（~120 行） |
| `api.py` | 修改 | 新增 5 个端点（含 workflow_trend 弱点3）（~85 行） |
| `scheduler.py` | 修改 | _execute_workflow_row 埋 Prometheus 指标 + insert_workflow_log（已在 P4 实现） |

## 七、验收标准

- [ ] `GET /api/admin/agents/overview` 返回数据包含 `workflows` 和 `planning` 字段
- [ ] `GET /api/admin/agents/workflows` 支持 `?owner_id=&workflow_id=&hours=` 三维过滤
- [ ] `GET /api/admin/agents/workflows/{wf_id}` 返回该工作流历史
- [ ] `GET /api/admin/agents/planning` 返回规划阶段成功率 + 模板命中率
- [ ] 工作流执行成功/失败/取消时，`workflow_executions_total` 按 status 标签递增
- [ ] `_migrate_snapshot_table` 给存量 snapshot 表加字段，**幂等**——重复启动不报错
- [ ] Admin `/workflows/cancel/{wf_id}` 可取消任意用户工作流（不走 owner 校验）
- [ ] AgentOpsEngine health_scan 在工作流失败率 > 20% 时产生 warning
- [ ] AgentOpsEngine health_scan 在规划回退率 > 30% 时产生 warning
- [ ] WebSocket 推送的 overview 数据包含 workflows + planning 字段
- [ ] 现有 5 个 REST 端点 + 1 个 WebSocket 行为不变
- [ ] Prometheus `/metrics` 端点能查到 3 个新指标

**弱点 3 补强（单工作流趋势）：**
- [ ] `GET /api/admin/agents/workflows/{wf_id}/trend?hours=168` 返回 summary + daily + top_errors
- [ ] `daily` 数组按 DATE(created_at) 聚合，含 success_rate + avg_duration
- [ ] `top_errors` 按出现次数排序，最多 3 条
- [ ] `get_workflow_trend` 在 `AgentHealthDB` 中实现，可独立调用

**弱点 4 补强（chat_query 上下文深度）：**
- [ ] 提问包含 "工作流 N" / "workflow N" / "wf N" / "#N" 时，正则提取 wf_id
- [ ] 注入该工作流最近 10 次执行详情（含 status / step / 耗时 / err）
- [ ] 注入 7 天 daily 趋势 + Top 失败原因
- [ ] 单问题最多解析 5 个 wf_id（避免 context 爆炸）
- [ ] admin `/chat` 端点改用 chat_query_enhanced
