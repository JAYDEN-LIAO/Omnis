# backend/services/agent_service/api.py
"""
Agent Chat API（v2.2 P1.10 接 auth + owner_id 注入）

变更要点：
- 所有端点都过 get_current_user，未登录 → 401
- chat 端点：把 owner_id 绑定到 contextvar，所有 @with_owner 工具自动拿到当前用户
- 流式响应里用 async wrapper set/reset contextvar，确保 yield 边界不漏 owner
- memory 端点 P1 仍是全局 session_id 视图，per-user 隔离待 P-future
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.services.auth_service.deps import get_current_user, require_registered_user
from backend.core.logger import get_logger

from .agent_core import chat_with_agent_stream, cancel_registry
from .memory import AgentMemoryManager
from .tools import reset_current_owner, set_current_owner

logger = get_logger("agent.api")

router = APIRouter()

memory_manager = AgentMemoryManager()


class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    session_id: Optional[str] = None


async def _stream_with_owner(
    owner_id: str,
    messages: List[Dict[str, str]],
    session_id: Optional[str],
):
    """包一层 async generator，进入时设 contextvar，退出时复位。
    _request 透传到 chat_with_agent_stream，便于工具拿到 owner_id + session_id。
    v2.3：聊天消息由 _write_memory_async 在 stream 完成后自动持久化。"""
    text_collector: list = []
    token = set_current_owner(owner_id)
    try:
        _request = {
            "owner_id": owner_id,
            "session_id": session_id,
            "_text_collector": text_collector,
        }
        async for chunk in chat_with_agent_stream(
            messages, session_id=session_id, _request=_request
        ):
            yield chunk
    finally:
        reset_current_owner(token)


@router.post("/api/agent/chat")
async def agent_chat_endpoint(
    request: ChatRequest,
    current_user: Dict = Depends(require_registered_user),
):
    """
    SSE 流式对话（v2.2 P2：多事件协议）。
    - 需注册用户（游客不可使用，LLM 成本控制）
    - owner_id 注入到 contextvar + _request，工具层双保险
    - 事件类型：text / tool_call / tool_progress / tool_result / error / done
    """
    owner_id = str(current_user["id"])
    session_id = request.session_id or None
    return StreamingResponse(
        _stream_with_owner(owner_id, request.messages, session_id),
        media_type="text/event-stream",
    )


# ==================== 记忆管理 API ====================


class ClearMemoryRequest(BaseModel):
    session_id: str


class MemoryResponse(BaseModel):
    session_id: str
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None


@router.get("/api/agent/memory")
async def get_memory_stats(current_user: Dict = Depends(get_current_user)):
    """返回历史会话列表（前端侧边栏用）。P1 仍是全局视图，P-future 加 owner_id 过滤。"""
    try:
        sessions = memory_manager.store.get_all_sessions(limit=50, owner_id=str(current_user["id"]))
        return {
            "success": True,
            "data": {
                "sessions": sessions,
                "total": len(sessions),
            },
        }
    except Exception as e:
        logger.error(f"[memory_stats] {e}")
        return {"success": False, "error": str(e)}


@router.get("/api/agent/memory/{session_id}")
async def get_session_memory(
    session_id: str, current_user: Dict = Depends(get_current_user)
):
    """获取指定 session 的记忆详情（owner 隔离，越权读取返回空）"""
    try:
        owner_id = str(current_user["id"])
        summary = memory_manager.store.get_summary(session_id, owner_id=owner_id)
        entities = memory_manager.store.get_frequent_entities(session_id, owner_id, min_count=1)
        facts = memory_manager.store.get_valid_facts(session_id, owner_id)

        return {
            "success": True,
            "data": {
                "summary": summary,
                "entities": entities,
                "facts": facts,
            },
        }
    except Exception as e:
        logger.error(f"[session_memory] {e}")
        return {"success": False, "error": str(e)}


@router.get("/api/agent/memory/{session_id}/messages")
async def get_session_messages(
    session_id: str, current_user: Dict = Depends(get_current_user)
):
    """获取指定 session 的聊天消息列表（owner 隔离，仅返回属于自己的消息）"""
    try:
        owner_id = str(current_user["id"])
        msgs = memory_manager.store.get_messages(session_id, owner_id)
        return {
            "success": True,
            "data": {
                "messages": msgs,
                "total": len(msgs),
            },
        }
    except Exception as e:
        logger.error(f"[session_messages] {e}")
        return {"success": False, "error": str(e)}


# ==================== 打断机制：取消指定 session ====================


@router.post("/api/agent/chat/{session_id}/cancel")
async def cancel_agent_stream(
    session_id: str,
    current_user: Dict = Depends(require_registered_user),
):
    """取消指定 session 当前正在执行的 Agent 流。"""
    cancelled = cancel_registry.cancel(session_id)
    return {"code": 200, "data": {"cancelled": cancelled}}


# ==================== v2.0 P4: 工作流列表 + 取消 ====================


@router.get("/api/agent/workflows")
async def list_workflows_endpoint(
    current_user: Dict = Depends(get_current_user),
):
    """返回工作流列表（预设 + 当前用户的自动模板 + 用户自定义）"""
    from backend.services.agent_service.workflows_db import WorkflowsDB
    db = WorkflowsDB()
    owner_id = str(current_user["id"])

    # 预设工作流（is_composite_tool=1）
    presets = db.query(
        "SELECT id, name, description, source, created_at FROM workflows "
        "WHERE source='preset' AND is_composite_tool=1 AND enabled=1 "
        "ORDER BY id"
    )

    # 用户的工作流（auto_template + user）
    user_workflows = db.query(
        "SELECT id, name, description, source, schedule_cron, "
        "last_run, run_count, enabled, created_at FROM workflows "
        "WHERE (owner_id=? AND source IN ('user','auto_template')) "
        "ORDER BY updated_at DESC LIMIT 20",
        [owner_id],
    )

    return {
        "code": 200,
        "data": {
            "presets": presets,
            "user_workflows": user_workflows,
        },
    }


@router.post("/api/agent/workflows/{workflow_id}/cancel")
async def cancel_workflow_endpoint(
    workflow_id: int,
    current_user: Dict = Depends(require_registered_user),
):
    """取消正在执行的工作流（仅本人工作流）。

    ★ R-012 修订：owner 权限校验，用户 A 不能取消用户 B 的工作流。
    """
    owner_id = str(current_user["id"])

    from backend.services.agent_service.workflows_db import WorkflowsDB
    db = WorkflowsDB()
    wf = db.get_by_id(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "工作流不存在"})
    if wf["owner_id"] != owner_id and wf["owner_id"] != "system":
        raise HTTPException(status_code=403, detail={"code": 403, "msg": "无权操作他人工作流"})

    from .workflows_db import _WF_CANCEL_EVENTS, _WF_CANCEL_LOCK
    with _WF_CANCEL_LOCK:
        event = _WF_CANCEL_EVENTS.get(workflow_id)
        if event:
            event.set()
            return {"code": 200, "data": {"cancelled": True}}
    return {"code": 404, "data": {"cancelled": False, "message": "工作流未在运行"}}


@router.delete("/api/agent/memory/{session_id}")
async def clear_session_memory(
    session_id: str, current_user: Dict = Depends(get_current_user)
):
    """清除指定 session 的所有记忆（owner 隔离，仅删自己的 session）"""
    try:
        owner_id = str(current_user["id"])
        deleted = memory_manager.delete_session(session_id, owner_id=owner_id)
        if deleted == 0:
            # 0 行被删：可能是该 session 不属于当前 owner，或不存在
            return {
                "success": False,
                "error": "session 不存在或不属于当前用户",
                "deleted": 0,
            }
        return {
            "success": True,
            "message": f"session {session_id} 的记忆已清除",
            "deleted": deleted,
        }
    except Exception as e:
        logger.error(f"[clear_memory] {e}")
        return {"success": False, "error": str(e)}
