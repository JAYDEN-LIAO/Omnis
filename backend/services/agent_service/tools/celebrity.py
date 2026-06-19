"""
追星线 Agent 查询工具

F2. get_celebrity_reports: 查询追星分析报告
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from backend.core.database import get_db_connection
from backend.core.logger import get_logger

from ._base import ToolResult, tool
from ._owner import with_owner

logger = get_logger("agent.tools.celebrity")


@tool(
    name="get_celebrity_reports",
    description="查询明星/偶像追星分析报告（情感分布/热度趋势/跨平台对比）",
    group="query",
    parameters={
        "type": "object",
        "properties": {
            "celebrity": {
                "type": "string",
                "description": "明星姓名（可选，筛选用）",
            },
            "keyword": {
                "type": "string",
                "description": "关键词（可选）",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数上限",
                "default": 10,
            },
        },
    },
)
@with_owner
def get_celebrity_reports(celebrity: str = "", keyword: str = "",
                           limit: int = 10, _owner_id: str = "") -> str:
    """查询追星分析报告"""
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = "SELECT * FROM celebrity_reports WHERE owner_id = ?"
            params: list = [_owner_id]

            if celebrity:
                query += " AND celebrity LIKE ?"
                params.append(f"%{celebrity}%")
            if keyword:
                query += " AND keyword LIKE ?"
                params.append(f"%{keyword}%")

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

        if not rows:
            return "暂无追星分析报告。"

        results = []
        for r in rows:
            d = dict(r)
            for field in ("sentiment_distribution", "hot_topics", "cross_platform"):
                try:
                    d[field] = json.loads(d.get(field, "{}"))
                except Exception:
                    d[field] = {} if field != "hot_topics" else []
            results.append(d)

        parts = [f"找到 {len(results)} 份追星报告："]
        for idx, r in enumerate(results, 1):
            sd = r.get("sentiment_distribution", {})
            parts.append(
                f"\n{idx}. 【{r['celebrity']}】\n"
                f"   关键词: {r['keyword']}\n"
                f"   情感分布: 正面{sd.get('positive', 0):.0%} 负面{sd.get('negative', 0):.0%} 中性{sd.get('neutral', 0):.0%}\n"
                f"   热度趋势: {r.get('heat_trend', 'stable')}\n"
                f"   热门话题: {', '.join(r.get('hot_topics', [])[:3])}\n"
                f"   时间: {r.get('created_at', '')[:16]}"
            )
        return "\n".join(parts)
    except Exception as e:
        logger.error(f"查询追星报告失败: {e}", exc_info=True)
        return f"查询追星报告失败: {e}"
