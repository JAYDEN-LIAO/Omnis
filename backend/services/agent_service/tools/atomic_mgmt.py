"""
原子工具层（H 组，共 12 个工具 + 2 个管理工具预留）

来自 pipeline 五阶段拆解。
所有工具带 @tool 装饰 + @with_owner 强制注入 owner_id。
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from backend.core.logger import get_logger

from ._base import ToolResult, tool
from ._owner import with_owner

logger = get_logger("agent.tools.atomic")

# H10-H12: query_report / push_report / list_workflows / manage_workflow

# ───────────────────────────────────────────────────────────────
# H10. query_report — 查询已生成的报告
# ───────────────────────────────────────────────────────────────
@tool(
    name="query_report",
    description="查询已生成的攻略/追星/简报报告。支持按类型和关键词筛选。",
    parameters={
        "type": "object",
        "properties": {
            "report_type": {
                "type": "string",
                "enum": ["guide", "celebrity", "briefing"],
                "default": "guide",
                "description": "报告类型",
            },
            "keyword": {"type": "string", "default": "", "description": "关键词筛选"},
            "limit": {"type": "integer", "default": 10, "description": "返回条数上限"},
        },
        "required": [],
    },
    group="atomic",
)
@with_owner
def query_report_tool(_owner_id: str, report_type: str = "guide", keyword: str = "", limit: int = 10) -> str:
    """查询已生成的报告。"""
    try:
        table_map = {
            "guide": "guide_reports",
            "celebrity": "celebrity_reports",
            "briefing": "daily_briefings",
        }
        table = table_map.get(report_type, "guide_reports")
        import sqlite3
        from backend.core.database import get_db_connection
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = f"SELECT * FROM {table} WHERE owner_id = ?"
            params: list = [_owner_id]
            if keyword:
                query += " AND keyword LIKE ?"
                params.append(f"%{keyword}%")
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]
        if not rows:
            return ToolResult(success=True, data=[], ui={"type": "report_list", "data": []}).to_json()
        return ToolResult(
            success=True,
            data=rows,
            ui={"type": "report_list", "data": rows},
        ).to_json()
    except Exception as e:
        logger.error(f"[query_report] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


# ───────────────────────────────────────────────────────────────
# H11. push_report — 推送报告
# ───────────────────────────────────────────────────────────────
@tool(
    name="push_report",
    description="通过指定通道推送报告内容。支持 email/wecom/feishu/rss。",
    parameters={
        "type": "object",
        "properties": {
            "report_content": {"type": "string", "description": "报告内容"},
            "channel": {
                "type": "string",
                "enum": ["email", "wecom", "feishu", "rss"],
                "default": "email",
                "description": "推送通道",
            },
            "title": {"type": "string", "default": "", "description": "推送标题"},
        },
        "required": ["report_content"],
    },
    group="atomic",
)
@with_owner
def push_report_tool(report_content: str, _owner_id: str, channel: str = "email", title: str = "") -> str:
    """通过指定通道推送报告内容。"""
    if not report_content.strip():
        return ToolResult(success=False, error="推送内容不能为空", error_type="validation").to_json()
    try:
        from backend.services.platform_service.notifier import send_alert
        send_alert(
            owner_id=_owner_id,
            keyword=title or "Agent 报告推送",
            platform="system",
            risk_level=2,
            risk_class="medium",
            core_issue=title or "报告推送",
            report=report_content,
            urls=[],
            email_html=report_content,
        )
        return ToolResult(
            success=True,
            data={"channel": channel, "status": "sent", "title": title or "报告推送"},
            ui={"type": "push_result", "data": {"channel": channel, "status": "sent"}},
        ).to_json()
    except Exception as e:
        logger.error(f"[push_report] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


# ───────────────────────────────────────────────────────────────
# H12. list_workflows — 列出当前用户可见工作流
# ───────────────────────────────────────────────────────────────
@tool(
    name="list_workflows",
    description=(
        "列出当前用户可见的所有工作流（user 自定义 + auto_template 累积 + 预置组合工具 preset）。"
        "用户问'我有哪些工作流'、'看 preset 工具'时调用。"
    ),
    parameters=None,
    group="atomic",
)
@with_owner
def list_workflows_tool(_owner_id: str) -> str:
    """返回工作流列表，按 source 分组"""
    from backend.services.agent_service.workflows_db import WorkflowsDB
    db = WorkflowsDB()
    # ★ R-013 修订：(owner=? AND source IN ('user','auto_template')) OR (source='preset')
    items = db.query(
        """
        SELECT id, owner_id, name, description, source,
               schedule_cron, schedule_desc, enabled,
               hit_count, last_hit, last_run, run_count,
               is_composite_tool, created_at, updated_at
        FROM workflows
        WHERE (owner_id = ? AND source IN ('user', 'auto_template'))
           OR (source = 'preset')
        ORDER BY source ASC, updated_at DESC
        """,
        [_owner_id],
    )
    return json.dumps({
        "success": True,
        "data": items,
        "ui": {"type": "workflow_list", "data": {"items": items, "count": len(items)}},
    }, ensure_ascii=False, default=str)


# ───────────────────────────────────────────────────────────────
# H13. manage_workflow — 管理工作流（5 种 action）
# ───────────────────────────────────────────────────────────────
@tool(
    name="manage_workflow",
    description=(
        "管理工作流。action: enable/disable/delete/run_now/save_as_preset。"
        "enable/disable：开关。delete：删除（preset 不可删）。"
        "run_now：立即执行（仅 user/auto_template）。"
        "save_as_preset：将 auto_template 升级为 user 工作流。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "workflow_id": {"type": "integer", "description": "工作流 ID"},
            "action": {
                "type": "string",
                "enum": ["enable", "disable", "delete", "run_now", "save_as_preset"],
                "description": "操作类型",
            },
        },
        "required": ["workflow_id", "action"],
    },
    group="atomic",
)
@with_owner
def manage_workflow_tool(workflow_id: int, action: str, _owner_id: str) -> str:
    from backend.services.agent_service.workflows_db import WorkflowsDB
    db = WorkflowsDB()
    wf = db.get_by_id(workflow_id)

    if not wf:
        return json.dumps({"success": False, "error": "工作流不存在"}, ensure_ascii=False)
    if wf["owner_id"] != _owner_id and wf["owner_id"] != "system":
        return json.dumps({
            "success": False, "error": "无权操作他人工作流",
        }, ensure_ascii=False)

    if action == "enable":
        db.set_enabled(workflow_id, True)
        msg = "已启用"
    elif action == "disable":
        db.set_enabled(workflow_id, False)
        msg = "已停用"
    elif action == "delete":
        if wf["source"] == "preset":
            return json.dumps({
                "success": False,
                "error": "系统预置工作流不可删除，请使用 disable 停用",
            }, ensure_ascii=False)
        db.delete(workflow_id)
        msg = "已删除"
    elif action == "run_now":
        if wf["source"] == "preset":
            return json.dumps({
                "success": False,
                "error": "预置组合工具由 Agent Function Calling 调用，无需手动 run_now",
            }, ensure_ascii=False)
        import asyncio
        from backend.services.platform_service.scheduler import _execute_workflow_row
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_execute_workflow_row(wf))
        except RuntimeError:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                ex.submit(_run_workflow_sync, wf)
        msg = "已加入执行队列"
    elif action == "save_as_preset":
        # ★ R-014 修订：只允许 auto_template → user，禁止其他转换
        if wf["source"] != "auto_template":
            return json.dumps({
                "success": False,
                "error": "save_as_preset 只能将 auto_template 转为 user 工作流。"
                         "若需把 user 升为 preset，请联系 Admin。",
            }, ensure_ascii=False)
        db.update(workflow_id, source="user")
        msg = "已转为 user 工作流（可加 cron 调度）"
    else:
        return json.dumps({
            "success": False, "error": f"未知 action: {action}",
        }, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "action": action,
        "workflow_id": workflow_id,
        "message": msg,
        "ui": {"type": "workflow_action_result", "data": {
            "workflow_id": workflow_id, "action": action, "message": msg,
        }},
    }, ensure_ascii=False)


def _run_workflow_sync(workflow: dict):
    """run_now 在非 event loop 上下文时的同步兜底"""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        from backend.services.platform_service.scheduler import _execute_workflow_row
        loop.run_until_complete(_execute_workflow_row(workflow))
    finally:
        loop.close()
