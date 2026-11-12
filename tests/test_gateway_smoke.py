"""Minimal gateway import and route smoke tests."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Iterable


def route_paths(routes: Iterable[object]) -> set[str]:
    """Collect paths from FastAPI routes, including versioned included routers."""
    paths: set[str] = set()
    for route in routes:
        if hasattr(route, "path"):
            paths.add(route.path)
            continue
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            paths.update(route_paths(original_router.routes))
    return paths


def test_gateway_imports_and_registers_core_routes(tmp_path: Path, monkeypatch) -> None:
    """The gateway must import with #5 fixed and expose its core observability routes."""
    from backend.core.config import settings
    from backend.services.agent_service.memory import memory_store

    monkeypatch.setattr(settings, "STATE_DB_PATH", str(tmp_path / "smoke-state.db"))
    monkeypatch.setattr(
        memory_store,
        "AGENT_MEMORY_DB_PATH",
        str(tmp_path / "agent-memory.db"),
    )

    from backend.gateway.main import app

    paths = route_paths(app.routes)
    assert {"/health", "/metrics", "/api/radar_status", "/api/auth/me"}.issubset(paths)
