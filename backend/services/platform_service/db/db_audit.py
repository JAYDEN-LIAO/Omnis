# backend/services/platform_service/db/db_audit.py
"""audit_log 表操作"""
import json
import sqlite3
from datetime import datetime
from typing import Optional

from backend.core.database import get_db_connection

from .db_init import init_radar_db


def insert_audit_log(
    action: str,
    detail: dict = None,
    keyword: str = "",
    topic_id: str = "",
    risk_level: int = 0,
    level: str = "INFO",
    owner_id: str = "",
) -> int:
    """插入一条审计日志，返回 rowid。

    v2.2: owner_id 单列存储（取代 detail.owner_id 的 json_extract 查询）。
    系统级事件可传空串。
    """
    init_radar_db()
    # 兼容旧调用方：若 detail 里塞了 owner_id 而未显式传，则提升到列
    if not owner_id and isinstance(detail, dict):
        owner_id = str(detail.get("owner_id") or "")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_log
                (action, keyword, topic_id, risk_level, level, detail, owner_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action,
                keyword,
                topic_id,
                int(risk_level or 0),
                level,
                json.dumps(detail or {}, ensure_ascii=False),
                owner_id,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0


def get_audit_log(
    limit: int = 50,
    action: str = None,
    owner_id: Optional[str] = None,
) -> list:
    """查询审计日志（按时间倒序）。

    v2.2: owner_id 非 None 时仅返回该用户 + 系统级（owner_id 为空）的事件。
    owner_id=None 视为 admin/全局视角（返回全部）。
    """
    init_radar_db()
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        params: list = []
        where_clauses: list[str] = []
        if action:
            where_clauses.append("action = ?")
            params.append(action)
        if owner_id is not None:
            # per-user 视角：自己的 + 系统级（owner_id 为空）
            where_clauses.append("(owner_id = ? OR owner_id = '' OR owner_id IS NULL)")
            params.append(owner_id)
        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        params.append(int(limit))
        cursor.execute(
            f"""
            SELECT id, action, keyword, topic_id, risk_level, level, detail, owner_id, created_at
            FROM audit_log
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        )
        rows = [dict(r) for r in cursor.fetchall()]
    for r in rows:
        try:
            r["detail"] = json.loads(r.get("detail") or "{}")
        except Exception:
            r["detail"] = {}
    return rows
