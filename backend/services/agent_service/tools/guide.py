"""
攻略线 Agent 查询工具

F1. get_guide_reports: 查询攻略报告
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from backend.core.database import get_db_connection
from backend.core.logger import get_logger

from ._base import ToolResult, tool
from ._owner import with_owner

logger = get_logger("agent.tools.guide")


@tool(
    name="get_guide_reports",
    description="查询攻略分析报告（支持按关键词/话题筛选）",
    group="query",
    parameters={
        "keyword": {
            "type": "string",
            "description": "关键词（可选，筛选用）",
        },
        "topic": {
            "type": "string",
            "description": "话题名（可选，筛选用）",
        },
        "limit": {
            "type": "integer",
            "description": "返回条数上限",
            "default": 10,
        },
    },
)
@with_owner
def get_guide_reports(keyword: str = "", topic: str = "",
                       limit: int = 10, _owner_id: str = "") -> str:
    """查询攻略报告"""
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = "SELECT * FROM guide_reports WHERE owner_id = ?"
            params: list = [_owner_id]

            if keyword:
                query += " AND keyword LIKE ?"
                params.append(f"%{keyword}%")
            if topic:
                query += " AND topic LIKE ?"
                params.append(f"%{topic}%")

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

        if not rows:
            return "暂无攻略报告。"

        results = []
        for r in rows:
            d = dict(r)
            # JSON 字段反序列化
            for field in ("consensus", "controversial", "tips"):
                try:
                    d[field] = json.loads(d.get(field, "[]"))
                except Exception:
                    d[field] = []
            try:
                d["source_breakdown"] = json.loads(d.get("source_breakdown", "{}"))
            except Exception:
                d["source_breakdown"] = {}
            results.append(d)

        parts = [f"找到 {len(results)} 份攻略报告："]
        for idx, r in enumerate(results, 1):
            parts.append(
                f"\n{idx}. 【{r['topic']}】\n"
                f"   关键词: {r['keyword']}\n"
                f"   摘要: {r.get('summary', '')[:100]}\n"
                f"   帖子数: {r['post_count']}\n"
                f"   共识: {', '.join(r.get('consensus', [])[:3])}\n"
                f"   时间: {r.get('created_at', '')[:16]}"
            )
        return "\n".join(parts)
    except Exception as e:
        logger.error(f"查询攻略报告失败: {e}", exc_info=True)
        return f"查询攻略报告失败: {e}"
