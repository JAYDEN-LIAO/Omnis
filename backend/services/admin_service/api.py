"""
Admin Agent 监控 API + Agent Ops Engine 智能运维
"""
import asyncio
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from pydantic import BaseModel

from backend.core.auth_deps import require_admin
from backend.core.auth_jwt import decode_token
from .agent_monitor import get_agent_monitor

router = APIRouter(prefix="/api/admin/agents", tags=["Admin Agent 监控"])

# WebSocket 连接集合（供 OpsEngine 广播）
_ws_connections: set = set()


# ── 基础监控端点 ──

@router.get("/overview")
async def agent_overview(_=Depends(require_admin)):
    return get_agent_monitor().get_overview()


@router.get("/tools")
async def agent_tools_health(_=Depends(require_admin)):
    return {"tools": get_agent_monitor().get_tool_health()}


@router.get("/sessions")
async def agent_sessions(limit: int = 20, _=Depends(require_admin)):
    return {"sessions": get_agent_monitor().get_session_stats(limit=limit)}


@router.get("/diagnosis")
async def agent_diagnosis_log(limit: int = 50, _=Depends(require_admin)):
    return {"events": get_agent_monitor().get_diagnosis_events(limit=limit)}


@router.get("/memory")
async def agent_memory_overview(_=Depends(require_admin)):
    from backend.services.agent_service.memory.memory_store import AgentMemoryStore
    return AgentMemoryStore().get_memory_stats()


# ── Agent Ops Engine 智能运维端点 ──


@router.get("/report")
async def agent_health_report(_=Depends(require_admin)):
    """健康巡检报告（LLM 分析 + 异常 + 建议）"""
    from .agent_ops import get_agent_ops
    result = await get_agent_ops().health_scan()
    return {"code": 200, "data": result}


@router.get("/report/daily")
async def agent_daily_report(_=Depends(require_admin)):
    """过去 24h 运维日报（LLM 生成）"""
    from .agent_ops import get_agent_ops
    report = await get_agent_ops().daily_report()
    return {"code": 200, "data": {"report": report, "generated_at": datetime.now().isoformat()}}


class ChatQueryRequest(BaseModel):
    question: str


@router.post("/chat")
async def agent_ops_chat(request: ChatQueryRequest, _=Depends(require_admin)):
    """自然语言查询 Agent 系统状态（P7 增强版：注入工作流上下文）"""
    from .agent_ops import get_agent_ops
    answer = await get_agent_ops().chat_query_enhanced(request.question)
    return {"code": 200, "data": {"question": request.question, "answer": answer}}


# ── P7: 工作流 + 规划监控端点 ──


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
    hours: int = Query(168, ge=1, le=720),
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


@router.get("/workflows/{workflow_id}/trend")
async def admin_workflow_trend(
    workflow_id: int,
    hours: int = Query(168, ge=1, le=720),
    _=Depends(require_admin),
):
    """★ 弱点3：单工作流的执行趋势（每日成功率 + Top 失败原因）"""
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


# ── WebSocket（token 认证 + 加入广播集合）──

@router.websocket("/ws")
async def agent_monitor_ws(websocket: WebSocket, token: str = Query(...)):
    try:
        payload = decode_token(token, expected_type="access")
        if payload.get("role") != "admin":
            await websocket.close(code=4003, reason="Admin role required")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    _ws_connections.add(websocket)
    monitor = get_agent_monitor()
    try:
        while True:
            try:
                overview = monitor.get_overview()
                await websocket.send_json(overview)
                await asyncio.sleep(5)
            except WebSocketDisconnect:
                break
            except Exception as e:
                await websocket.send_json({"error": str(e)})
                await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
    finally:
        _ws_connections.discard(websocket)
