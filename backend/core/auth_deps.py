"""
WS4: FastAPI 依赖注入

- get_current_user: 解析 Bearer token，返回 user dict
- require_admin: 仅 admin 通过，否则 403
- get_optional_user: 有 token 就解析，没有返回 None（公开端点用）
"""
from fastapi import Header, HTTPException, status, Depends, Security
from typing import Optional, Dict, Any

from backend.core.auth_jwt import decode_token
from backend.core.auth_db import get_user_by_id
from backend.core.logger import get_logger
from backend.core.auth import API_KEY_HEADER, get_valid_api_keys

logger = get_logger("auth.deps")


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """FastAPI 依赖项：从 Authorization: Bearer <token> 解析当前用户"""
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 401, "msg": "未登录或 token 缺失", "data": None},
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 401, "msg": "token 无效或已过期", "data": None},
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 401, "msg": "token payload 缺少 sub", "data": None},
        )

    # 游客分支：返回合成 dict，不走 DB
    if payload.get("role") == "guest":
        return {
            "id": user_id,
            "role": "guest",
            "is_active": True,
            "nickname": "访客",
            "email": None,
        }

    user = get_user_by_id(user_id)
    if not user or not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 401, "msg": "用户不存在或已禁用", "data": None},
        )
    return user


async def get_optional_user(
    authorization: Optional[str] = Header(default=None),
) -> Optional[Dict[str, Any]]:
    """公开端点用：有 token 解析用户，无 token 返回 None"""
    token = _extract_bearer(authorization)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None

    # 游客分支：返回合成 dict
    if payload.get("role") == "guest":
        return {
            "id": user_id,
            "role": "guest",
            "is_active": True,
            "nickname": "访客",
            "email": None,
        }

    user = get_user_by_id(user_id)
    return user if user and user.get("is_active") else None


async def get_current_user_or_api_key(
    authorization: Optional[str] = Header(default=None),
    api_key: Optional[str] = Security(API_KEY_HEADER),
) -> Dict[str, Any]:
    """
    v2.2 P1#16：接受 JWT（Bearer token）或 API Key（X-API-Key），任一即可。

    策略：
      1. 优先尝试 JWT：成功 → 返回完整 user dict
      2. 回退到 API Key：有效 → 返回最小服务账户 dict（不映射到具体用户）
      3. 都失败 → 401

    用于同时需要前端（JWT）和外部工具（API Key）访问的端点，
    比如 /api/start_task 和 /api/radar_status。
    """
    # 先试 JWT
    token = _extract_bearer(authorization)
    if token:
        payload = decode_token(token)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                user = get_user_by_id(user_id)
                if user and user.get("is_active"):
                    return user

    # 再试 API Key
    if api_key and api_key in get_valid_api_keys():
        logger.info("[Auth] API Key 认证成功 (service_id=api_service)")
        return {"id": "api_service", "role": "api_service", "is_active": True}

    # 记录 API Key 失败尝试（区分于无 Key 场景）
    if api_key and api_key not in get_valid_api_keys():
        masked = api_key[:4] + "***" if len(api_key) > 4 else "***"
        logger.warning(f"[Auth] API Key 认证失败: invalid key prefix={masked}")

    # 都失败
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": 401, "msg": "需要有效的 JWT（Bearer token）或 API Key（X-API-Key）", "data": None},
    )


async def require_admin(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """仅 admin 通过；普通用户 → 403"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 403, "msg": "需要 admin 权限", "data": None},
        )
    return current_user


async def require_registered_user(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """拒绝 guest 角色，仅允许已注册用户（user/admin）通过。

    用于写入/敏感端点，确保游客无法执行需要注册账号的操作。
    """
    if current_user.get("role") == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 403, "msg": "此功能需要注册账号", "data": None},
        )
    return current_user


def can_view_all_data(role: str) -> bool:
    """仅 admin 能查看全局数据；普通用户和 guest 按 owner_id 过滤"""
    return role == "admin"
