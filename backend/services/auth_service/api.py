"""
WS4: /api/auth/* 路由

- /api/auth/me              — 当前用户信息（需 token）
- /api/auth/logout          — 撤销 token（需 token）
- /api/auth/oauth/{provider}/login    — 跳转 OAuth
- /api/auth/oauth/{provider}/callback — OAuth 回调
"""
import re
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from backend.core.config import settings
from backend.core.logger import get_logger
from .db import (
    init_auth_tables,
    get_user_by_id,
    update_user_profile,
    create_user,
    create_local_user,
    authenticate_local,
    update_last_login,
    change_password,
    set_password_for_oauth_user,
    redeem_invite_code,
    get_user_system_access,
)
from .jwt import encode_token, encode_access_token, encode_refresh_token, decode_token, revoke_token, encode_guest_access_token
from .deps import get_current_user, require_admin

logger = get_logger("auth.api")
router = APIRouter()

# 启动时确保表存在
init_auth_tables()


# ==================== Schemas ====================

class MeResponse(BaseModel):
    user_id: str
    email: Optional[str] = None
    nickname: str
    avatar_url: Optional[str] = None
    role: str
    oauth_provider: Optional[str] = None
    created_at: Optional[str] = None


class LogoutResponse(BaseModel):
    msg: str = "已登出"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


def _validate_password_strength(password: str) -> Optional[str]:
    """校验密码强度，返回错误信息或 None"""
    if len(password) < 8:
        return "密码至少 8 位"
    if not re.search(r"[A-Z]", password):
        return "密码需要包含至少一个大写字母"
    if not re.search(r"[a-z]", password):
        return "密码需要包含至少一个小写字母"
    if not re.search(r"\d", password):
        return "密码需要包含至少一个数字"
    return None


# v2.2 P1#14：refresh token 请求体
class RefreshRequest(BaseModel):
    refresh_token: str


class ProfileUpdateRequest(BaseModel):
    nickname: str = ""


class SetPasswordRequest(BaseModel):
    new_password: str


class InviteCodeRequest(BaseModel):
    code: str


class UpdateRoleRequest(BaseModel):
    role: str  # "user" | "admin"


# ==================== /api/auth/* ====================

@router.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """当前用户信息"""
    return {
        "code": 200,
        "msg": "OK",
        "data": {
            "user_id": current_user["id"],
            "email": current_user.get("email"),
            "nickname": current_user.get("nickname", ""),
            "avatar_url": current_user.get("avatar_url"),
            "role": current_user.get("role", "user"),
            "oauth_provider": current_user.get("oauth_provider"),
            "created_at": current_user.get("created_at"),
        },
    }


@router.post("/api/auth/logout")
async def logout(
    authorization: Optional[str] = Header(default=None),
    current_user: dict = Depends(get_current_user),
):
    """撤销当前 token"""
    token = authorization.split()[1] if authorization and len(authorization.split()) == 2 else None
    if token:
        revoke_token(token)
    logger.info(f"[AuthAPI] 用户 {current_user['id']} 登出")
    return {"code": 200, "msg": "已登出", "data": None}


# L3 v2.2: 修改密码（需已设置过本地密码）
@router.post("/api/auth/change-password")
async def change_password_endpoint(
    req: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """修改当前用户的密码。需提供旧密码。"""
    err = _validate_password_strength(req.new_password)
    if err:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": err, "data": None})
    try:
        ok = change_password(current_user["id"], req.old_password, req.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": str(e), "data": None})
    if not ok:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "旧密码错误或账号无本地密码", "data": None})
    return {"code": 200, "msg": "密码已更新", "data": None}


# L3 v2.2: OAuth 用户首次设置本地密码
@router.post("/api/auth/set-password")
async def set_password_endpoint(
    req: SetPasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """为 OAuth-only 用户首次设置本地密码（已设过密码的用户应走 change-password）。"""
    err = _validate_password_strength(req.new_password)
    if err:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": err, "data": None})
    try:
        ok = set_password_for_oauth_user(current_user["id"], req.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": str(e), "data": None})
    if not ok:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "用户已存在本地密码，请使用 change-password", "data": None})
    return {"code": 200, "msg": "密码已设置", "data": None}


@router.put("/api/auth/profile")
async def update_profile(
    req: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """更新当前用户资料（昵称）。"""
    if not req.nickname or not req.nickname.strip():
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "昵称不能为空", "data": None})
    ok = update_user_profile(current_user["id"], req.nickname.strip())
    if not ok:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "用户不存在", "data": None})
    return {"code": 200, "msg": "资料已更新", "data": None}


# ==================== 邮箱密码注册/登录 ====================

@router.post("/api/auth/register")
async def register(req: RegisterRequest):
    """邮箱密码注册"""
    if not req.email or not req.password:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "邮箱和密码不能为空", "data": None})
    err = _validate_password_strength(req.password)
    if err:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": err, "data": None})

    nickname = req.nickname.strip() or req.email.split("@")[0]
    user = create_local_user(email=req.email.strip(), password=req.password, nickname=nickname)
    if not user:
        raise HTTPException(status_code=409, detail={"code": 409, "msg": "该邮箱已注册", "data": None})

    update_last_login(user["id"])
    logger.info(f"[AuthAPI] 注册成功: user={user['id']}, email={req.email.strip()}")
    access = encode_access_token(user["id"], user["role"])
    refresh = encode_refresh_token(user["id"], user["role"])
    return {
        "code": 200,
        "msg": "注册成功",
        "data": {
            "token": access,                # 向后兼容旧字段名
            "access_token": access,         # v2.2 P1#14：新标准字段
            "refresh_token": refresh,       # v2.2 P1#14：用于换 access
            "user": {"user_id": user["id"], "nickname": user["nickname"], "role": user["role"]},
        },
    }


@router.post("/api/auth/guest-login")
async def guest_login(request: Request):
    """游客登录：返回短生命周期 JWT（默认 2h），不创建 DB 记录。

    限流由全局 auth 限流覆盖（5 requests / min / IP）。
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )
    token = encode_guest_access_token(client_ip=client_ip)
    logger.info(f"[AuthAPI] 游客登录: ip={client_ip}, token={token[:12]}...")

    return {
        "code": 200,
        "msg": "游客登录成功",
        "data": {
            "token": token,
            "access_token": token,
            "refresh_token": "",
            "user": {
                "user_id": f"g_{token[:16]}",
                "nickname": "访客",
                "role": "guest",
            },
        },
    }


@router.post("/api/auth/redeem-invite")
async def redeem_invite(
    req: InviteCodeRequest,
    current_user: dict = Depends(get_current_user),
):
    """兑换邀请码，开通系统 Key 权限。"""
    if current_user.get("role") == "guest":
        raise HTTPException(status_code=403, detail={"code": 403, "msg": "游客无法兑换邀请码，请先注册", "data": None})

    success, msg = redeem_invite_code(req.code, current_user["id"])
    if not success:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": msg, "data": None})
    return {"code": 200, "msg": msg, "data": None}


@router.get("/api/auth/invite-status")
async def invite_status(
    current_user: dict = Depends(get_current_user),
):
    """查询当前用户的系统 Key 权限状态。"""
    if current_user.get("role") == "guest":
        return {"code": 200, "data": {"has_system_access": False}}

    has_access = get_user_system_access(current_user["id"])
    return {"code": 200, "data": {"has_system_access": has_access}}


@router.post("/api/auth/login")
async def login(req: LoginRequest):
    """邮箱密码登录"""
    email = req.email.strip()
    password = req.password

    # WS6-C4 v2.2: 失败锁定检查
    from .db.lockout import is_locked, record_failure, record_success
    locked, retry_after = is_locked(email)
    if locked:
        raise HTTPException(
            status_code=429,
            detail={"code": 429, "msg": f"登录失败次数过多，请 {retry_after}s 后再试", "data": None},
            headers={"Retry-After": str(retry_after)},
        )

    user = authenticate_local(email=email, password=password)
    if not user:
        count = record_failure(email)
        logger.warning(f"[AuthAPI] 登录失败: email={email}, failures={count}")
        if count >= 5:
            raise HTTPException(
                status_code=429,
                detail={"code": 429, "msg": "登录失败次数过多，已临时锁定 5 分钟", "data": None},
                headers={"Retry-After": "300"},
            )
        raise HTTPException(status_code=401, detail={"code": 401, "msg": "邮箱或密码错误", "data": None})

    record_success(email)
    update_last_login(user["id"])
    logger.info(f"[AuthAPI] 登录成功: user={user['id']}, email={email}")
    access = encode_access_token(user["id"], user["role"])
    refresh = encode_refresh_token(user["id"], user["role"])
    return {
        "code": 200,
        "msg": "登录成功",
        "data": {
            "token": access,                # 向后兼容旧字段名
            "access_token": access,         # v2.2 P1#14：新标准字段
            "refresh_token": refresh,       # v2.2 P1#14：用于换 access
            "user": {"user_id": user["id"], "nickname": user["nickname"], "role": user["role"]},
        },
    }


# v2.2 P1#14：/api/auth/refresh 端点（用 refresh_token 换新的 access_token）
@router.post("/api/auth/refresh")
async def refresh_access_token(req: RefreshRequest):
    """
    用 refresh_token 换取新的 access_token。

    安全约束：
    - 必须是 type=refresh 的 token（access token 调这里会被拒）
    - 必须未过期、未在黑名单
    - 对应用户必须仍是 active 状态（deactivated 用户的 token 一律拒绝）
    - 用户 iat 必须晚于 tokens_invalid_after（账号被踢下线后旧 refresh 无效）

    返回：新 access_token（不旋转 refresh_token，保持简单；refresh 用完才重发）
    """
    if not req.refresh_token or not req.refresh_token.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": 400, "msg": "refresh_token 不能为空", "data": None},
        )

    payload = decode_token(req.refresh_token, expected_type="refresh")
    if not payload:
        # 区分错误原因便于客户端处理
        raise HTTPException(
            status_code=401,
            detail={"code": 401, "msg": "refresh_token 无效、过期或类型不匹配", "data": None},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail={"code": 401, "msg": "refresh_token 缺少 sub 字段", "data": None},
        )

    # 检查用户仍 active（防止 deactivated 用户的旧 refresh token 仍能换 access）
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"code": 401, "msg": "用户不存在", "data": None},
        )
    if user.get("is_active") == 0 or user.get("is_active") is False:
        logger.warning(f"[AuthAPI] refresh 被拒：user={user_id} 已停用")
        raise HTTPException(
            status_code=403,
            detail={"code": 403, "msg": "账号已停用", "data": None},
        )

    # 用 refresh payload 里的 role 签发新 access（用户当前 role 由 get_user_by_id 重新取更准）
    new_access = encode_access_token(user["id"], user["role"])
    logger.info(f"[AuthAPI] refresh 换新 access: user={user_id}")
    return {
        "code": 200,
        "msg": "OK",
        "data": {
            "access_token": new_access,
            "token": new_access,  # 向后兼容旧字段
            "user": {"user_id": user["id"], "nickname": user.get("nickname", ""), "role": user["role"]},
        },
    }


# ==================== /api/auth/oauth/google ====================

@router.get("/api/auth/oauth/{provider}/login")
async def oauth_login(provider: str):
    """Google OAuth 登录入口"""
    if provider != "google":
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "不支持的 OAuth provider", "data": None})

    from .oauth_providers import google as google_oauth
    if not google_oauth.is_configured():
        return {
            "code": 503,
            "msg": "Google OAuth 尚未配置。请在 .env 中配置 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET。",
            "data": {"setup_url": "https://console.cloud.google.com/apis/credentials"},
        }
    try:
        authorize_url, state = google_oauth.build_authorize_url()
        return RedirectResponse(url=authorize_url, status_code=302)
    except Exception as e:
        logger.error(f"[AuthAPI] Google 授权 URL 构造失败: {e}", exc_info=True)
        return {"code": 500, "msg": f"Google OAuth 初始化失败: {e}", "data": None}


@router.get("/api/auth/oauth/{provider}/callback")
async def oauth_callback(provider: str, code: str, state: str = ""):
    """Google OAuth 回调：code → token → userinfo → JWT"""
    if provider != "google":
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "不支持的 provider", "data": None})

    # ── dev mock（仅 ENV=dev 时允许） ──
    if code in ("PLACEHOLDER", "xxx", "mock", "dev"):
        if settings.ENV != "dev":
            raise HTTPException(status_code=403, detail={"code": 403, "msg": "mock 登录仅开发环境可用", "data": None})
        import uuid
        mock_oauth_id = f"mock-google-{code}-{uuid.uuid4().hex[:8]}"
        mock_email = f"dev-google-{uuid.uuid4().hex[:4]}@dev.local"
        user = create_user(
            email=mock_email,
            nickname="Dev Google User",
            avatar_url=None,
            oauth_provider="google",
            oauth_id=mock_oauth_id,
            role="user",
        )
        update_last_login(user["id"])
        access = encode_access_token(user["id"], user["role"])
        refresh = encode_refresh_token(user["id"], user["role"])
        redirect_url = f"{settings.OAUTH_REDIRECT_BASE}/auth/callback?token={access}"
        return RedirectResponse(url=redirect_url, status_code=302)

    # ── 真实 Google OAuth ──
    from .oauth_providers import google as google_oauth
    from .oauth_providers.google import OAuthExchangeError

    if not google_oauth.is_configured():
        raise HTTPException(status_code=503, detail={"code": 503, "msg": "Google OAuth 未配置", "data": None})

    try:
        userinfo = google_oauth.handle_callback(code, state=state)
    except OAuthExchangeError as e:
        logger.error(f"[AuthAPI] Google OAuth 回调失败: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail={"code": 400, "msg": f"Google 登录失败: {e}", "data": None})

    google_sub = userinfo.get("sub")
    email = userinfo.get("email")
    nickname = userinfo.get("name") or (email.split("@")[0] if email else "Google User")
    avatar_url = userinfo.get("picture")

    if not google_sub:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Google userinfo 缺少 sub", "data": None})

    user = create_user(
        email=email, nickname=nickname, avatar_url=avatar_url,
        oauth_provider="google", oauth_id=google_sub, role="user",
    )
    update_last_login(user["id"])
    access = encode_access_token(user["id"], user["role"])
    refresh = encode_refresh_token(user["id"], user["role"])
    logger.info(f"[AuthAPI] Google 登录成功 user_id={user['id']} email={email}")
    redirect_url = f"{settings.OAUTH_REDIRECT_BASE}/auth/callback?token={access}"
    return RedirectResponse(url=redirect_url, status_code=302)
# Admin 用户管理路由已迁移至 admin_service/api.py
