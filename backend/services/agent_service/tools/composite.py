"""
组合工具动态注册（I 组）

启动时从 workflows 表读取所有 is_composite_tool=1 AND enabled=1 的条目，
动态注册为 Agent Function Calling 工具。
"""
from __future__ import annotations

import json
from typing import Optional

from backend.core.logger import get_logger

from ._base import _REGISTRY, get_current_cancel_event, tool
from ._owner import with_owner

logger = get_logger("agent.tools.composite")


def register_composite_tools():
    """启动时调用：从 workflows 表读取 → 动态注册 @tool()

    幂等：_REGISTRY 中已存在的同名工具跳过（重启不抛 ValueError）。
    """
    from backend.services.agent_service.workflows_db import WorkflowsDB
    db = WorkflowsDB()
    presets = db.get_composite_tools()
    registered = 0
    for wf in presets:
        if _register_single(wf):
            registered += 1
    logger.info(f"[Composite] 动态注册完成：{registered} 个新工具")


def _register_single(wf: dict) -> bool:
    """注册单个组合工具。返回 True 表示新增，False 表示已存在跳过。"""
    if wf["name"] in _REGISTRY:
        return False

    steps = json.loads(wf["steps_json"])
    params_schema = _extract_params_from_steps(steps)

    @tool(
        name=wf["name"],
        description=wf["description"],
        parameters=params_schema,
        group="composite",
    )
    @with_owner
    async def composite_tool(_owner_id: str = "", **kwargs):
        """通用组合工具执行器。"""
        from backend.services.agent_service.workflows_db import execute_workflow_steps
        cancel_event = get_current_cancel_event()
        return await execute_workflow_steps(
            steps=steps, initial_params=kwargs,
            owner_id=_owner_id, cancel_event=cancel_event,
        )

    composite_tool.__name__ = wf["name"]
    return True


def _extract_params_from_steps(steps: list) -> dict:
    """从 steps 中提取 {{param_name}} 占位符，生成 OpenAI function calling schema。

    只识别 step_N 之外的占位符作为工具入参；step_N_result 视为内部引用。
    """
    import re
    PLACEHOLDER_RE = re.compile(r"^\s*\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}\s*$")
    STEP_REF_RE = re.compile(r"^\s*step_(\d+)(?:\..*)?\s*$")

    params = {"type": "object", "properties": {}, "required": []}
    seen = set()

    for step in steps:
        for key, val in step.get("params", {}).items():
            if not isinstance(val, str):
                continue
            m = PLACEHOLDER_RE.match(val)
            if not m:
                continue
            pname = m.group(1)
            if STEP_REF_RE.match(pname):
                continue
            if pname in seen:
                continue
            seen.add(pname)
            params["properties"][pname] = {
                "type": "string",
                "description": f"参数: {pname}",
            }
            if step.get("criticality") == "critical":
                params["required"].append(pname)
    return params
