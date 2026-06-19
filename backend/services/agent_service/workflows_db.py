"""
统一工作流存储（v2.0 P1）

单表 workflows 三源合一：preset + auto_template + user
包含 execute_workflow_steps 统一执行器和 WorkflowsDB CRUD。
"""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.core.database import get_db_connection
from backend.core.logger import get_logger
from backend.services.agent_service.tools._base import get_tool

logger = get_logger("agent.workflows")

# ★ R-004: 正则提取 step_N 中的整数 N
_STEP_IDX_RE = re.compile(r"^step_(\d+)$")


def _resolve_step_index(token: str) -> Optional[int]:
    m = _STEP_IDX_RE.match(token.strip())
    return int(m.group(1)) if m else None


# ============================================================
# 预置组合工具（DB seed）
# ============================================================

PRESET_WORKFLOWS = [
    {
        "name": "deep_analyze_topic",
        "owner_id": "system",
        "source": "preset",
        "is_composite_tool": 1,
        "description": "对话题做深度分析：采集→过滤→聚类→提取→对比。适合需要结构化报告的场景。",
        "constraints_template": "{}",
        "steps_json": json.dumps([
            {"step": 1, "tool": "search_posts", "criticality": "critical",
             "params": {"keyword": "{{keyword}}", "platforms": "{{platforms}}"},
             "description": "搜索相关帖子"},
            {"step": 2, "tool": "filter_content", "criticality": "critical",
             "params": {"posts": "{{step_1_result}}", "intent": "{{analysis_type}}"},
             "description": "按意图过滤"},
            {"step": 3, "tool": "cluster_related", "criticality": "required",
             "params": {"posts": "{{step_2_result}}"},
             "description": "聚类分组"},
            {"step": 4, "tool": "extract_slots", "criticality": "required",
             "params": {"clusters": "{{step_3_result}}", "slot_type": "{{analysis_type}}"},
             "description": "提取结构化槽位"},
            {"step": 5, "tool": "compare_opinions", "criticality": "optional",
             "params": {"slots": "{{step_4_result}}"},
             "description": "跨来源加权对比"},
        ], ensure_ascii=False),
    },
    {
        "name": "scan_and_alert",
        "owner_id": "system", "source": "preset", "is_composite_tool": 1,
        "description": "舆情扫描并推送：搜索→过滤风险→聚类→情感分析→推送",
        "steps_json": json.dumps([
            {"step": 1, "tool": "search_posts", "criticality": "critical",
             "params": {"keyword": "{{keyword}}", "platforms": "{{platforms}}"},
             "description": "搜索关键词帖子"},
            {"step": 2, "tool": "filter_content", "criticality": "critical",
             "params": {"posts": "{{step_1_result}}", "intent": "risk"},
             "description": "过滤风险内容"},
            {"step": 3, "tool": "cluster_related", "criticality": "required",
             "params": {"posts": "{{step_2_result}}"},
             "description": "聚类"},
            {"step": 4, "tool": "analyze_sentiment", "criticality": "required",
             "params": {"texts": "{{step_3_result}}"},
             "description": "情感分析"},
            {"step": 5, "tool": "push_report", "criticality": "optional",
             "params": {"report_content": "{{step_4_result}}", "channel": "{{channel}}"},
             "description": "推送预警"},
        ], ensure_ascii=False),
    },
    {
        "name": "quick_guide",
        "owner_id": "system", "source": "preset", "is_composite_tool": 1,
        "description": "查攻略，没缓存就现采集分析，返回行程计划和预算估算",
        "steps_json": json.dumps([
            {"step": 1, "tool": "query_report", "criticality": "optional",
             "params": {"keyword": "{{keyword}}", "report_type": "guide"},
             "description": "先查缓存报告"},
            {"step": 2, "tool": "search_posts", "criticality": "critical",
             "params": {"keyword": "{{keyword}}", "platforms": "{{platforms}}"},
             "description": "无缓存则采集"},
            {"step": 3, "tool": "filter_content", "criticality": "critical",
             "params": {"posts": "{{step_2_result}}", "intent": "guide"},
             "description": "按攻略意图过滤"},
            {"step": 4, "tool": "cluster_related", "criticality": "required",
             "params": {"posts": "{{step_3_result}}"},
             "description": "聚类"},
            {"step": 5, "tool": "extract_slots", "criticality": "required",
             "params": {"clusters": "{{step_4_result}}", "slot_type": "guide"},
             "description": "提取攻略槽位"},
            {"step": 6, "tool": "generate_itinerary", "criticality": "optional",
             "params": {"opinions": "{{step_5_result}}", "slots": "{{step_5_result}}",
                        "keyword": "{{keyword}}"},
             "description": "生成行程"},
        ], ensure_ascii=False),
    },
    {
        "name": "briefing_digest",
        "owner_id": "system", "source": "preset", "is_composite_tool": 1,
        "description": "生成综合简报：搜索→过滤→聚类→汇总→推送，支持定时生成",
        "steps_json": json.dumps([
            {"step": 1, "tool": "search_posts", "criticality": "critical",
             "params": {"keyword": "{{keyword}}", "platforms": "{{platforms}}"},
             "description": "搜索全网"},
            {"step": 2, "tool": "filter_content", "criticality": "critical",
             "params": {"posts": "{{step_1_result}}", "intent": "briefing"},
             "description": "简报线全收"},
            {"step": 3, "tool": "cluster_related", "criticality": "required",
             "params": {"posts": "{{step_2_result}}"},
             "description": "按话题聚类"},
            {"step": 4, "tool": "push_report", "criticality": "optional",
             "params": {"report_content": "{{step_3_result}}", "channel": "{{channel}}"},
             "description": "推送简报"},
        ], ensure_ascii=False),
    },
]


def init_preset_workflows():
    """DB seed — 启动时调用一次。重复调用不会产生重复条目（按 name UPSERT）。"""
    with get_db_connection() as conn:
        c = conn.cursor()
        for wf in PRESET_WORKFLOWS:
            c.execute("""
                INSERT INTO workflows
                (owner_id, name, description, steps_json, constraints_template,
                 source, is_composite_tool, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description = excluded.description,
                    steps_json = excluded.steps_json,
                    updated_at = excluded.updated_at
            """, (
                wf["owner_id"], wf["name"], wf["description"],
                wf["steps_json"], wf.get("constraints_template", "{}"),
                wf["source"], wf["is_composite_tool"],
                datetime.now().isoformat(), datetime.now().isoformat(),
            ))
        conn.commit()
    logger.info(f"[Workflows] preset seed 完成: {len(PRESET_WORKFLOWS)} 个")


# ============================================================
# 统一执行器 execute_workflow_steps
# ============================================================

def _resolve_params(params: dict, results: dict) -> dict:
    """解析 {{step_N_result}} 模板变量。"""
    resolved = {}
    for key, value in params.items():
        if not (isinstance(value, str) and value.startswith("{{") and value.endswith("}}")):
            resolved[key] = value
            continue
        ref = value[2:-2].strip()
        parts = ref.split(".")
        idx = _resolve_step_index(parts[0])
        if idx is None:
            resolved[key] = value
            continue
        val = results.get(f"step_{idx}")
        if val is None:
            resolved[key] = {}
            continue
        for p in parts[1:]:
            if isinstance(val, dict):
                val = val.get(p)
            elif isinstance(val, str):
                try:
                    val = json.loads(val).get(p)
                except Exception:
                    val = None
            else:
                val = None
            if val is None:
                break
        resolved[key] = val
    return resolved


async def execute_workflow_steps(
    steps: list,
    initial_params: dict,
    owner_id: str,
    cancel_event: Optional[asyncio.Event] = None,
    workflow_id: Optional[int] = None,
    workflow_name: str = "",
) -> str:
    """统一步骤执行器。"""
    results: Dict[str, Any] = {}
    if not owner_id:
        return json.dumps({"error": "owner_id 缺失", "step": 0}, ensure_ascii=False)

    start_ts = time.time()
    failed_step = 0
    status = "success"

    for i, step in enumerate(steps):
        # 取消检查点
        if cancel_event and cancel_event.is_set():
            status = "cancelled"
            failed_step = i + 1
            _log_workflow_execution(
                workflow_id, workflow_name, owner_id, "cancelled",
                time.time() - start_ts, len(steps), failed_step, "用户取消",
            )
            return json.dumps({
                "error": "cancelled", "step": i + 1, "message": "用户取消",
            }, ensure_ascii=False)

        tool_name = step["tool"]
        params = _resolve_params(step.get("params", {}), results)
        # initial_params 覆盖
        for k, v in initial_params.items():
            if k not in params:
                params[k] = v
        params["_owner_id"] = owner_id  # 强制注入

        # ★ R-001: get_tool 返回 dict，用 ["func"] 取
        meta = get_tool(tool_name)
        if not meta or "func" not in meta:
            return json.dumps({
                "error": f"工具 {tool_name} 不存在或未注册", "step": i + 1,
            }, ensure_ascii=False)
        tool_func = meta["func"]

        criticality = step.get("criticality", "required")
        max_retries = {"critical": 1, "required": 2, "optional": 0}.get(criticality, 1)

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                # ★ R-002: sync/async 分支
                if asyncio.iscoroutinefunction(tool_func):
                    result = await tool_func(**params)
                else:
                    result = await asyncio.to_thread(tool_func, **params)
                results[f"step_{i+1}"] = result
                last_error = None
                break
            except Exception as e:
                last_error = e
                logger.warning(
                    f"[Workflow] step {i+1} ({tool_name}) "
                    f"重试 {attempt+1}/{max_retries+1} 失败: {e}"
                )
                if attempt < max_retries:
                    continue
                if criticality == "critical":
                    status = "failed"
                    failed_step = i + 1
                    _log_workflow_execution(
                        workflow_id, workflow_name, owner_id, "failed",
                        time.time() - start_ts, len(steps), failed_step, str(e),
                    )
                    return json.dumps({
                        "error": str(e), "step": i + 1,
                        "message": "关键步骤失败，执行终止",
                    }, ensure_ascii=False)
                results[f"step_{i+1}"] = json.dumps({
                    "skipped": True, "reason": str(e),
                }, ensure_ascii=False)
                last_error = None
                break

    duration = time.time() - start_ts
    _log_workflow_execution(
        workflow_id, workflow_name, owner_id, status,
        duration, len(steps), failed_step,
        str(last_error) if last_error else "",
    )
    return json.dumps({"success": True, "results": results}, ensure_ascii=False)


def _log_workflow_execution(
    workflow_id: Optional[int], workflow_name: str, owner_id: str,
    status: str, duration: float, total_steps: int,
    failed_step: int, error_message: str,
):
    """执行日志落库（静默失败不影响主流程）。"""
    try:
        from backend.services.admin_service.agent_health_db import AgentHealthDB
        db = AgentHealthDB()
        db.insert_workflow_log(
            workflow_id=workflow_id or 0,
            workflow_name=workflow_name or "",
            owner_id=owner_id or "",
            status=status,
            duration_seconds=duration,
            total_steps=total_steps,
            failed_step=failed_step,
            error_message=error_message[:500] if error_message else "",
        )
    except Exception as e:
        logger.warning(f"[Workflow] 写执行日志失败: {e}")


# ============================================================
# WorkflowsDB CRUD
# ============================================================

class WorkflowsDB:
    """统一工作流 CRUD（preset + auto_template + user 共用）"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        return get_db_connection(self.db_path) if self.db_path else get_db_connection()

    def _init_db(self):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    steps_json TEXT NOT NULL,
                    constraints_template TEXT DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'user',
                    schedule_cron TEXT DEFAULT '',
                    schedule_desc TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1,
                    hit_count INTEGER DEFAULT 0,
                    last_hit TEXT DEFAULT '',
                    last_run TEXT DEFAULT '',
                    run_count INTEGER DEFAULT 0,
                    is_composite_tool INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            for ddl in [
                "CREATE INDEX IF NOT EXISTS idx_wf_owner ON workflows(owner_id)",
                "CREATE INDEX IF NOT EXISTS idx_wf_source ON workflows(source)",
                "CREATE INDEX IF NOT EXISTS idx_wf_enabled ON workflows(enabled)",
                "CREATE INDEX IF NOT EXISTS idx_wf_composite ON workflows(is_composite_tool)",
            ]:
                try:
                    c.execute(ddl)
                except Exception:
                    pass
            conn.commit()

    def query(self, sql: str, params: list = None) -> List[Dict]:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params or []).fetchall()
            return [dict(r) for r in rows]

    def get_composite_tools(self) -> List[Dict]:
        return self.query(
            "SELECT * FROM workflows WHERE is_composite_tool=1 AND enabled=1"
        )

    def get_by_id(self, wf_id: int) -> Optional[Dict]:
        rows = self.query("SELECT * FROM workflows WHERE id=?", [wf_id])
        return rows[0] if rows else None

    def upsert_auto_template(
        self, owner_id: str, name: str, steps_json: str,
        constraints_template: str = "{}",
    ) -> int:
        """累积 auto_template：已存在同 owner + 同 name 时 hit_count++，否则 INSERT。"""
        existing = self.query(
            "SELECT id, hit_count FROM workflows "
            "WHERE owner_id=? AND name=? AND source='auto_template'",
            [owner_id, name],
        )
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            c = conn.cursor()
            if existing:
                wf_id = existing[0]["id"]
                c.execute("""
                    UPDATE workflows
                    SET hit_count = hit_count + 1,
                        last_hit = ?,
                        enabled = 1,
                        updated_at = ?
                    WHERE id = ?
                """, [now, now, wf_id])
            else:
                c.execute("""
                    INSERT INTO workflows
                    (owner_id, name, steps_json, constraints_template, source,
                     enabled, hit_count, last_hit, is_composite_tool, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'auto_template', 1, 1, ?, 0, ?, ?)
                """, [owner_id, name, steps_json, constraints_template,
                      now, now, now])
                wf_id = c.lastrowid
            conn.commit()
        return wf_id

    def insert_workflow(
        self, owner_id: str, name: str, steps_json: str,
        constraints_template: str = "{}",
        source: str = "user",
        schedule_cron: str = "",
        schedule_desc: str = "",
        is_composite_tool: int = 0,
    ) -> int:
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO workflows
                (owner_id, name, steps_json, constraints_template, source,
                 schedule_cron, schedule_desc, is_composite_tool,
                 enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, [owner_id, name, steps_json, constraints_template, source,
                  schedule_cron, schedule_desc, is_composite_tool,
                  now, now])
            conn.commit()
            return c.lastrowid

    def set_enabled(self, wf_id: int, enabled: bool):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE workflows SET enabled=?, updated_at=? WHERE id=?",
                [1 if enabled else 0, datetime.now().isoformat(), wf_id],
            )
            conn.commit()

    def update(self, wf_id: int, **fields):
        allowed = {"name", "description", "steps_json", "constraints_template",
                   "schedule_cron", "schedule_desc", "source", "enabled",
                   "is_composite_tool"}
        sets = []
        params = []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?")
                params.append(v)
        if not sets:
            return
        sets.append("updated_at=?")
        params.append(datetime.now().isoformat())
        params.append(wf_id)
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(f"UPDATE workflows SET {', '.join(sets)} WHERE id=?", params)
            conn.commit()

    def delete(self, wf_id: int):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM workflows WHERE id=?", [wf_id])
            conn.commit()

    def list_due_user_workflows(self) -> List[Dict]:
        return self.query(
            "SELECT * FROM workflows WHERE source='user' "
            "AND schedule_cron != '' AND enabled=1"
        )

    def mark_workflow_run(self, wf_id: int, last_run_iso: str):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE workflows
                SET last_run=?, run_count=run_count+1, updated_at=?
                WHERE id=?
            """, [last_run_iso, datetime.now().isoformat(), wf_id])
            conn.commit()
