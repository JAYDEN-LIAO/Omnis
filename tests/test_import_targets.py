"""Static smoke tests for backend import targets."""

from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
INTERNAL_TOP_LEVELS = {"services", "core", "shared", "gateway"}


def import_candidates(file: Path, level: int, module: str) -> list[Path]:
    """Resolve an internal import to its expected module or package file."""
    if level:
        base = file.parent
        for _ in range(level - 1):
            base = base.parent
        parts = module.split(".") if module else []
    else:
        parts = module.split(".") if module else []
        if not parts:
            return []
        if parts[0] == "backend":
            base, parts = BACKEND_ROOT, parts[1:]
        elif parts[0] in INTERNAL_TOP_LEVELS:
            base, parts = BACKEND_ROOT / parts[0], parts[1:]
        else:
            return []

    target = base.joinpath(*parts) if parts else base
    return [target.with_suffix(".py"), target / "__init__.py"]


def missing_import_targets() -> list[str]:
    """Return internal imports whose module or package file cannot be found."""
    missing: list[str] = []
    for file in BACKEND_ROOT.rglob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                candidates = import_candidates(file, node.level, node.module or "")
                if candidates and not any(path.exists() for path in candidates):
                    rendered = "." * node.level + (node.module or "")
                    missing.append(f"{file}:{node.lineno}: {rendered}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    candidates = import_candidates(file, 0, alias.name)
                    if candidates and not any(path.exists() for path in candidates):
                        missing.append(f"{file}:{node.lineno}: {alias.name}")
    return missing


def test_backend_internal_import_targets_exist() -> None:
    """Guard against service-split leftovers such as missing llm_gateway imports."""
    assert missing_import_targets() == []
