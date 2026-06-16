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
    """自然语言查询 Agent 系统状态"""
    from .agent_ops import get_agent_ops
    answer = await get_agent_ops().chat_query(request.question)
    return {"code": 200, "data": {"question": request.question, "answer": answer}}


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
