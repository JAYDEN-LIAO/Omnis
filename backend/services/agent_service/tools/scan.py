"""
B 组 扫描 / 调度（6 个工具）

v2.2 per-user：每个用户独立的扫描频率 + 暂停状态（存 quota 表）。
trigger_scan 仍共享全局雷达实例（同一时刻只能一次扫描），但结果按 owner_id 归属。
"""
from __future__ import annotations

import json
from typing import Optional

from backend.core.logger import get_logger

from ._base import ToolResult, tool
from ._owner import with_owner

logger = get_logger("agent.tools.scan")



# ── B1. trigger_scan — 立即触发一次扫描 ──
@tool(
    name="trigger_scan",
    description=(
        "立即触发一次扫描（异步后台执行）。"
        "用户说'现在扫一下/抓最新/帮我看看新动态'时调用。"
        "调完此工具后**不要**再调任何其他工具，直接告诉用户任务已在后台跑。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["full", "trending", "fan_track", "quick_search"],
                "description": "扫描模式，默认 trending",
            },
            "subscription_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "只扫指定订阅；空 = 全部订阅",
            },
            "platforms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "限定平台；空 = 全平台",
            },
        },
    },
    group="scan",
)
@with_owner
def trigger_scan_tool(
    _owner_id: str,
    mode: str = "trending",
    subscription_ids: Optional[list] = None,
    platforms: Optional[list] = None,
) -> str:
    # 旧 Pipeline 扫描已移除，改用组合工作流
    from services.platform_service.main import get_radar_status
    from services.platform_service.scheduler import _run_extra_pipelines

    user_status = get_radar_status(_owner_id)
    if user_status.is_running:
        return ToolResult(
            success=True,
            data={"status": "already_running", "message": "扫描任务已在运行中"},
            ui={"type": "scan_progress", "data": {"status": "already_running"}},
        ).to_json()

    async def _run():
        try:
            user_status.set_running_sync(f"Agent 触发扫描: owner={_owner_id}")
            await _run_extra_pipelines(_owner_id, [mode], [])
        except Exception as e:
            logger.error(f"[trigger_scan] {e}")
        finally:
            user_status.set_idle_sync()

    try:
        asyncio.create_task(_run())
    except RuntimeError:
        pass

    return ToolResult(
        success=True,
        data={"status": "started", "mode": mode, "message": "扫描任务已下达"},
        ui={"type": "scan_progress", "data": {"status": "started"}},
    ).to_json()


# ── B2. get_scan_status ──
@tool(
    name="get_scan_status",
    description="查询雷达当前的扫描状态（是否运行中、上次完成时间、本轮已抓多少新内容）。",
    parameters=None,
    group="scan",
)
@with_owner
def get_scan_status_tool(_owner_id: str) -> str:
    from services.platform_service.main import get_radar_status
    st = get_radar_status(_owner_id)
    data = st.get_status_dict()
    return ToolResult(success=True, data=data, ui={"type": "scan_status", "data": data}).to_json()


# ── B3. set_scan_interval (v2.2 per-user) ──
@tool(
    name="set_scan_interval",
    description="修改你本人的扫描频率（不影响其他用户）。单位：分钟，范围 5~1440。",
    parameters={
        "type": "object",
        "properties": {
            "interval_min": {
                "type": "integer", "minimum": 5, "maximum": 1440,
                "description": "扫描间隔（分钟）",
            },
        },
        "required": ["interval_min"],
    },
    group="scan",
)
@with_owner
def set_scan_interval_tool(interval_min: int, _owner_id: str) -> str:
    if interval_min < 5 or interval_min > 1440:
        return ToolResult(
            success=False, error="interval_min 必须在 5~1440 之间", error_type="validation",
        ).to_json()

    from backend.shared.db.quota_db import get_scan_config, set_scan_interval
    old = get_scan_config(_owner_id)
    set_scan_interval(_owner_id, interval_min)

    return ToolResult(
        success=True,
        data={"old_interval_min": old["interval_min"], "new_interval_min": interval_min},
        ui={"type": "scheduler_info", "data": {"interval_min": interval_min, "changed": True}},
    ).to_json()


# ── B4a/B4b. pause_scheduler / resume_scheduler (v2.2 per-user) ──
@tool(
    name="pause_scheduler",
    description="暂停你本人的定时扫描（不影响其他用户）。",
    parameters=None,
    group="scan",
)
@with_owner
def pause_scheduler_tool(_owner_id: str) -> str:
    from backend.shared.db.quota_db import set_scan_paused
    set_scan_paused(_owner_id, True)
    return ToolResult(
        success=True, data={"active": False},
        ui={"type": "scheduler_info", "data": {"active": False}},
    ).to_json()


@tool(
    name="resume_scheduler",
    description="恢复你本人的定时扫描。",
    parameters=None,
    group="scan",
)
@with_owner
def resume_scheduler_tool(_owner_id: str) -> str:
    from backend.shared.db.quota_db import set_scan_paused
    set_scan_paused(_owner_id, False)
    return ToolResult(
        success=True, data={"active": True},
        ui={"type": "scheduler_info", "data": {"active": True}},
    ).to_json()


# ── B5. get_next_run_time (v2.2 per-user) ──
@tool(
    name="get_next_run_time",
    description="查询你本人的下次扫描时间、频率和调度器状态。",
    parameters=None,
    group="scan",
)
@with_owner
def get_next_run_time_tool(_owner_id: str) -> str:
    from backend.shared.db.quota_db import get_scan_config
    conf = get_scan_config(_owner_id)

    # 全局调度器状态作为辅助信息
    next_run = None
    try:
        from services.platform_service.scheduler import scheduler_status
        gs = scheduler_status()
        next_run = gs.get("next_run")
    except Exception:
        pass

    data = {
        "next_run_at": next_run,
        "interval_min": conf["interval_min"],
        "start_time": conf["start_time"],
        "paused": conf["paused"],
    }
    return ToolResult(
        success=True, data=data, ui={"type": "scheduler_info", "data": data},
    ).to_json()


# ── B6/B7. pause_scan / resume_scan — 爬虫采集暂停/恢复 ──
@tool(
    name="pause_scan",
    description=(
        "暂停当前正在运行的爬虫采集任务（允许当前页面完成，不再启动新页面）。"
        "用户说'暂停/停一下/先别抓了'时调用。"
    ),
    parameters=None,
    group="scan",
)
@with_owner
def pause_scan_tool(_owner_id: str) -> str:
    import asyncio
    try:
        from services.crawler_service.api.services import crawler_manager
        loop = asyncio.get_event_loop()
        ok = loop.run_until_complete(crawler_manager.pause())
        if ok:
            return ToolResult(
                success=True,
                data={"status": "paused"},
                ui={"type": "scan_progress", "data": {"status": "paused"}},
            ).to_json()
        return ToolResult(
            success=False,
            error="爬虫不在运行中",
            error_type="state",
        ).to_json()
    except Exception as e:
        logger.error(f"[pause_scan] {e}")
        return ToolResult(success=False, error=str(e), error_type="internal").to_json()


@tool(
    name="resume_scan",
    description="恢复已暂停的爬虫采集任务。用户说'继续/恢复/接着抓'时调用。",
    parameters=None,
    group="scan",
)
@with_owner
def resume_scan_tool(_owner_id: str) -> str:
    import asyncio
    try:
        from services.crawler_service.api.services import crawler_manager
        loop = asyncio.get_event_loop()
        ok = loop.run_until_complete(crawler_manager.resume())
        if ok:
            return ToolResult(
                success=True,
                data={"status": "running"},
                ui={"type": "scan_progress", "data": {"status": "running"}},
            ).to_json()
        return ToolResult(
            success=False,
            error="爬虫不在暂停状态",
            error_type="state",
        ).to_json()
    except Exception as e:
        logger.error(f"[resume_scan] {e}")
        return ToolResult(success=False, error=str(e), error_type="internal").to_json()
