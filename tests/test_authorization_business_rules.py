"""Business regression tests for authorization and ownership rules."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.services.auth_service.db import (
    create_invite_code,
    create_user,
    get_user_system_access,
    init_auth_tables,
    migrate_existing_users_access_once,
    redeem_invite_code,
)
from backend.services.auth_service.deps import get_current_user
from backend.services.auth_service.jwt import encode_access_token, encode_refresh_token
from backend.services.platform_service.db.db_push import (
    ensure_rss_access_token,
    get_owner_by_rss_token,
    get_push_config,
    save_push_config,
)


def use_temp_db(tmp_path: Path, monkeypatch: Any) -> None:
    """Point all business DB helpers at an isolated SQLite file."""
    monkeypatch.setattr(settings, "STATE_DB_PATH", str(tmp_path / "auth-state.db"))
    monkeypatch.setattr(settings, "JWT_SECRET", "test-jwt-secret-with-enough-length")
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")


def test_invite_code_has_atomic_finite_redemption(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A one-use code must grant only the first user and then be exhausted."""
    use_temp_db(tmp_path, monkeypatch)
    init_auth_tables()
    first = create_user("first@example.test", "first")
    second = create_user("second@example.test", "second")
    code = create_invite_code(max_uses=1, created_by="pytest")

    assert redeem_invite_code(code, first["id"]) == (True, "邀请码兑换成功，已开通系统 Key 权限")
    assert get_user_system_access(first["id"]) is True

    success, message = redeem_invite_code(code, second["id"])
    assert success is False
    assert message == "邀请码已被用完"
    assert get_user_system_access(second["id"]) is False


def test_init_does_not_grant_system_access_and_disables_unlimited_codes(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Application startup must not elevate users or preserve unlimited codes."""
    use_temp_db(tmp_path, monkeypatch)
    from backend.core.database import get_db_connection

    # 模拟旧库：invite_codes 先以无 CHECK 的历史结构存在。
    with get_db_connection() as conn:
        conn.execute(
            "CREATE TABLE invite_codes ("
            "code TEXT PRIMARY KEY, max_uses INTEGER DEFAULT 0, "
            "current_uses INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1)"
        )
        conn.commit()
    init_auth_tables()
    user = create_user("startup@example.test", "startup")
    assert get_user_system_access(user["id"]) is False

    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO invite_codes (code, max_uses, current_uses, is_active) "
            "VALUES ('LEGACY-INFINITE', 0, 0, 1)"
        )
        conn.commit()

    init_auth_tables()
    with get_db_connection() as conn:
        active = conn.execute(
            "SELECT is_active FROM invite_codes WHERE code = 'LEGACY-INFINITE'"
        ).fetchone()[0]
    assert active == 0
    assert get_user_system_access(user["id"]) is False


def test_legacy_access_migration_runs_only_once(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The explicit legacy grant is schema-versioned and cannot run repeatedly."""
    use_temp_db(tmp_path, monkeypatch)
    init_auth_tables()
    before = create_user("before@example.test", "before")
    assert migrate_existing_users_access_once() is True
    assert get_user_system_access(before["id"]) is True

    after = create_user("after@example.test", "after")
    assert migrate_existing_users_access_once() is False
    assert get_user_system_access(after["id"]) is False


def test_refresh_token_cannot_call_access_token_apis(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Protected dependencies must reject refresh tokens as access tokens."""
    use_temp_db(tmp_path, monkeypatch)
    init_auth_tables()
    user = create_user("token@example.test", "token")
    access = encode_access_token(user["id"], user["role"])
    refresh = encode_refresh_token(user["id"], user["role"])

    current = asyncio.run(get_current_user(f"Bearer {access}"))
    assert current["id"] == user["id"]

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(f"Bearer {refresh}"))
    assert exc_info.value.status_code == 401


def test_rss_token_is_exact_server_generated_and_unique(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """RSS ownership lookup must use exact JSON field matching."""
    use_temp_db(tmp_path, monkeypatch)
    save_push_config("owner-a", "rss", {"enabled": True, "access_token": "a" * 32})
    save_push_config("owner-b", "rss", {"enabled": True, "access_token": "b" * 32})

    assert get_owner_by_rss_token("a" * 32) == "owner-a"
    assert get_owner_by_rss_token("a") is None
    assert get_owner_by_rss_token("bbbb") is None

    token = ensure_rss_access_token("owner-c", {"enabled": True})
    assert token is not None
    assert len(token) >= 32
    assert get_owner_by_rss_token(token) == "owner-c"

    from backend.services.platform_service import api as platform_api

    from backend.services.platform_service import notifier

    monkeypatch.setattr(notifier, "reload_registry", lambda **kwargs: None)
    response = platform_api.save_push_config(
        "rss",
        platform_api.PushConfigUpdateRequest(
            enabled=True, risk_min_level=2, webhook_url="client-controlled-token"
        ),
        {"id": "owner-c", "role": "user"},
    )
    assert response["code"] == 200
    saved_token = get_push_config("owner-c", "rss")["access_token"]
    assert saved_token != "client-controlled-token"
    assert len(saved_token) >= 32


def test_scheduler_mutations_require_admin(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A registered non-admin must get 403 from global scheduler mutations."""
    use_temp_db(tmp_path, monkeypatch)
    init_auth_tables()
    user = create_user("scheduler@example.test", "scheduler")
    access = encode_access_token(user["id"], user["role"])

    from backend.services.platform_service.api import router
    from backend.services.platform_service.main import radar_status

    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/api/scheduler/start",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == 403
    assert radar_status.is_running is False


def test_agent_cancel_is_owner_scoped(monkeypatch: Any) -> None:
    """A user must not cancel another owner's active agent stream."""
    from backend.services.agent_service import api as agent_api
    from backend.services.agent_service.agent_core import CancelRegistry

    registry = CancelRegistry()
    registry.register("session-1", "owner-a")
    monkeypatch.setattr(agent_api, "cancel_registry", registry)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            agent_api.cancel_agent_stream(
                "session-1", {"id": "owner-b", "role": "user"}
            )
        )
    assert exc_info.value.status_code == 403

    result = asyncio.run(
        agent_api.cancel_agent_stream(
            "session-1", {"id": "owner-a", "role": "user"}
        )
    )
    assert result["data"]["cancelled"] is True
