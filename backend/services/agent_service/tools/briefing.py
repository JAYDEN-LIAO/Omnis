"""
简报线 Agent 查询工具

F3. get_briefings: 查询综合简报
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from backend.core.database import get_db_connection
from backend.core.logger import get_logger

from ._base import ToolResult, tool
from ._owner import with_owner

logger = get_logger("agent.tools.briefing")


@tool(
    name="get_briefings",
    description="查询每日信息简报（按关键词/领域/日期筛选）",
    group="query",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "关键词（可选）",
            },
            "domain": {
                "type": "string",
                "description": "领域（可选，如：新能源汽车/AI大模型）",
            },
            "date": {
                "type": "string",
                "description": "日期（可选，格式：YYYY-MM-DD）",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数上限",
                "default": 20,
            },
        },
    },
)
@with_owner
def get_briefings(keyword: str = "", domain: str = "",
                   date: str = "", limit: int = 20,
                   _owner_id: str = "") -> str:
    """查询简报"""
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = "SELECT * FROM daily_briefings WHERE owner_id = ?"
            params: list = [_owner_id]

            if keyword:
                query += " AND keyword LIKE ?"
                params.append(f"%{keyword}%")
            if domain:
                query += " AND domain LIKE ?"
                params.append(f"%{domain}%")
            if date:
                query += " AND date = ?"
                params.append(date)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

        if not rows:
            return "暂无简报。"

        results = [dict(r) for r in rows]
        parts = [f"找到 {len(results)} 条简报："]
        for idx, r in enumerate(results, 1):
            parts.append(
                f"\n{idx}. 【{r.get('domain', '未分类')}】{r.get('highlight', '')[:50]}\n"
                f"   关键词: {r['keyword']} | 情感: {r.get('sentiment', 'neutral')}\n"
                f"   日期: {r.get('date', '')} | 帖子数: {r['post_count']}"
            )
        return "\n".join(parts)
    except Exception as e:
        logger.error(f"查询简报失败: {e}", exc_info=True)
        return f"查询简报失败: {e}"
