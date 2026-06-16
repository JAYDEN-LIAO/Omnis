# backend/services/radar_service/db/db_ai_results.py
"""ai_results 表操作"""
import sqlite3
import threading
from typing import Optional

from backend.core.database import get_db_connection
from backend.core.logger import get_logger

logger = get_logger("radar.db")


def _async_index_to_qdrant(result: dict):
    """异步将 ai_results 写入 Qdrant（不阻塞主流程）"""
    try:
        from ..vector_store import index_ai_result
        index_ai_result(result)
        logger.info(f"[RAG Index] post_id={result['post_id']} 已写入 Qdrant")
    except Exception as e:
        logger.warning(f"[RAG Index] 索引失败（不影响主流程）：{e}")


def save_ai_result(post_id, platform, keyword, title, content, url, risk_level, core_issue, report, publish_time="未知时间", sentiment="Neutral", owner_id: Optional[str] = None):
    """
    WS4.6：owner_id 标识数据归属。
    - owner_id=None  → 公共/历史数据（所有用户可见）
    - owner_id="u_xxx" → 该用户私有数据
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO ai_results
            (post_id, platform, keyword, title, content, url, risk_level, core_issue, report, publish_time, sentiment, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (post_id, platform, keyword, title, content, url, risk_level, core_issue, report, publish_time, sentiment, owner_id))
        conn.commit()

    # ── 异步触发 RAG 索引（新增）───────────────────
    result_dict = {
        "post_id": post_id,
        "platform": platform,
        "keyword": keyword,
        "title": title,
        "content": content,
        "url": url,
        "risk_level": risk_level,
        "core_issue": core_issue,
        "report": report,
        "publish_time": publish_time,
        "sentiment": sentiment,
        "owner_id": owner_id,
    }
    threading.Thread(target=_async_index_to_qdrant, args=(result_dict,), daemon=True).start()
    # ───────────────────────────────────────────────


def get_volume_stats(owner_id: Optional[str] = None, is_admin: bool = False, keyword: str = None) -> dict:
    """返回最近 7 天按天 + keyword 的帖子量统计

    Returns:
        {
            "daily_rows": [{"day": str, "total_count": int, "neg_count": int}, ...],
            "keyword_rows": [{"keyword": str, "day": str, "cnt": int}, ...],
        }
    """
    import datetime

    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=6)
    week_start = week_ago.isoformat()

    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query 1: daily volume aggregation
        if is_admin:
            cursor.execute('''
                SELECT DATE(create_time) as day,
                       COUNT(*) as total_count,
                       SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as neg_count
                FROM ai_results
                WHERE DATE(create_time) >= ?
                  AND (? = '' OR keyword = ?)
                GROUP BY DATE(create_time)
                ORDER BY day ASC
            ''', (week_start, keyword, keyword))
        else:
            cursor.execute('''
                SELECT DATE(create_time) as day,
                       COUNT(*) as total_count,
                       SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as neg_count
                FROM ai_results
                WHERE DATE(create_time) >= ?
                  AND (? = '' OR keyword = ?)
                  AND (owner_id = ? OR owner_id IS NULL)
                GROUP BY DATE(create_time)
                ORDER BY day ASC
            ''', (week_start, keyword, keyword, owner_id))
        daily_rows = [dict(r) for r in cursor.fetchall()]

        # Query 2: per-keyword volume breakdown
        keyword_rows = []
        try:
            if is_admin:
                cursor.execute('''
                    SELECT keyword, DATE(create_time) as day, COUNT(*) as cnt
                    FROM ai_results
                    WHERE DATE(create_time) >= ?
                    GROUP BY keyword, DATE(create_time)
                    ORDER BY keyword, day
                ''', (week_start,))
            else:
                cursor.execute('''
                    SELECT keyword, DATE(create_time) as day, COUNT(*) as cnt
                    FROM ai_results
                    WHERE DATE(create_time) >= ?
                      AND (owner_id = ? OR owner_id IS NULL)
                    GROUP BY keyword, DATE(create_time)
                    ORDER BY keyword, day
                ''', (week_start, owner_id))
            keyword_rows = [dict(r) for r in cursor.fetchall()]
        except Exception:
            pass

    return {"daily_rows": daily_rows, "keyword_rows": keyword_rows}


def get_today_summary_data(owner_id: Optional[str] = None, is_admin: bool = False) -> dict:
    """返回今日摘要所需的所有聚合数据

    Returns:
        {
            "today_data": [dict of ai_results rows for today],
            "risk_distribution": {"high": int, "medium": int, "low": int},
        }
    """
    import datetime

    today = datetime.date.today().isoformat()

    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query 1: today's ai_results
        if is_admin:
            cursor.execute('''
                SELECT * FROM ai_results
                WHERE DATE(create_time) = ?
                ORDER BY create_time DESC
            ''', (today,))
        else:
            cursor.execute('''
                SELECT * FROM ai_results
                WHERE DATE(create_time) = ?
                  AND (owner_id = ? OR owner_id IS NULL)
                ORDER BY create_time DESC
            ''', (today, owner_id))
        today_data = [dict(r) for r in cursor.fetchall()]

        # Query 2: risk distribution from topic_summary
        risk_distribution = {"high": 0, "medium": 0, "low": 0}
        try:
            if is_admin:
                cursor.execute('''
                    SELECT
                        SUM(CASE WHEN CAST(risk_level AS INTEGER) >= 4 THEN 1 ELSE 0 END) as high,
                        SUM(CASE WHEN CAST(risk_level AS INTEGER) = 3 THEN 1 ELSE 0 END) as medium,
                        SUM(CASE WHEN CAST(risk_level AS INTEGER) <= 2 THEN 1 ELSE 0 END) as low
                    FROM topic_summary
                    WHERE DATE(last_seen) >= ?
                ''', (today,))
            else:
                cursor.execute('''
                    SELECT
                        SUM(CASE WHEN CAST(risk_level AS INTEGER) >= 4 THEN 1 ELSE 0 END) as high,
                        SUM(CASE WHEN CAST(risk_level AS INTEGER) = 3 THEN 1 ELSE 0 END) as medium,
                        SUM(CASE WHEN CAST(risk_level AS INTEGER) <= 2 THEN 1 ELSE 0 END) as low
                    FROM topic_summary
                    WHERE DATE(last_seen) >= ?
                      AND (owner_id = ? OR owner_id IS NULL)
                ''', (today, owner_id))
            dist_row = cursor.fetchone()
            if dist_row:
                risk_distribution = {
                    "high": dist_row["high"] or 0,
                    "medium": dist_row["medium"] or 0,
                    "low": dist_row["low"] or 0,
                }
        except Exception:
            pass

    return {
        "today_data": today_data,
        "risk_distribution": risk_distribution,
    }


def get_latest_results(limit=50, owner_id: Optional[str] = None, is_admin: bool = False):
    """
    WS4.6：按 owner 过滤查询。
    - is_admin=True   → 看到全部（管理员）
    - owner_id 传值   → 仅看 owner_id == ? OR owner_id IS NULL（自己的 + 公共）
    - owner_id=None   → 仅看公共（owner_id IS NULL）
    """
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if is_admin:
            cursor.execute('SELECT * FROM ai_results ORDER BY create_time DESC LIMIT ?', (limit,))
        elif owner_id is not None:
            cursor.execute(
                'SELECT * FROM ai_results WHERE owner_id = ? OR owner_id IS NULL ORDER BY create_time DESC LIMIT ?',
                (owner_id, limit),
            )
        else:
            cursor.execute(
                'SELECT * FROM ai_results WHERE owner_id IS NULL ORDER BY create_time DESC LIMIT ?',
                (limit,),
            )
        rows = cursor.fetchall()
    return [dict(r) for r in rows]
