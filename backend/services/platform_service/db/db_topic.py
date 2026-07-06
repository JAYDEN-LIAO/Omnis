# backend/services/platform_service/db/db_topic.py
"""topic_summary + topic_posts 表操作"""
import json
import sqlite3
from typing import Optional

from backend.core.database import get_db_connection


def create_or_update_topic_summary(
    topic_id: str,
    keyword: str,
    topic_name: str,
    cluster_summary: str = "",
    risk_level: int = 2,
    risk_class: str = "neutral",
    alert_recommendation: str = "none",
    core_issue: str = "",
    report: str = "",
    platforms: list = None,
    sentiment: str = "neutral",
    owner_id: Optional[str] = None,
) -> bool:
    """
    创建或更新话题聚合记录。
    如果话题已存在（topic_id 相同），则合并（更新 post_count、scan_count、last_seen 等）。
    返回 True 表示新建，False 表示更新。

    WS4.6：owner_id 标识数据归属。
    - 新建时：写入 owner_id
    - 更新时：不动 owner_id（保持最初创建者；后续扫描若来自同 owner 自然一致）

    alert_recommendation: AI 最终决策结论，取值范围:
        - "high":     高风险预警（需处理）
        - "medium":   中风险（待观察）
        - "low":      低风险（忽略）
        - "none":     无风险（无需处理）
    """
    if platforms is None:
        platforms = []

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 检查是否已存在
        cursor.execute("SELECT topic_id FROM topic_summary WHERE topic_id = ?", (topic_id,))
        exists = cursor.fetchone() is not None

        import datetime
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        platforms_json = json.dumps(platforms)

        if exists:
            # 更新：累加 post_count、scan_count，更新 last_seen（不动 owner_id）
            # WS6-C2 v2.2: WHERE 加 owner_id 过滤，避免跨租户覆盖
            cursor.execute('''
                UPDATE topic_summary SET
                    cluster_summary = COALESCE(NULLIF(?, ''), cluster_summary),
                    risk_level = MAX(risk_level, ?),
                    risk_class = CASE
                        WHEN ? > risk_level THEN ?
                        ELSE risk_class
                    END,
                    alert_recommendation = ?,
                    core_issue = COALESCE(NULLIF(?, ''), core_issue),
                    report = COALESCE(NULLIF(?, ''), report),
                    platforms = ?,
                    sentiment = CASE
                        WHEN ? > risk_level THEN ?
                        ELSE sentiment
                    END,
                    scan_count = scan_count + 1,
                    last_seen = ?,
                    post_count = (
                        SELECT COUNT(*) FROM topic_posts WHERE topic_id = ?
                    )
                WHERE topic_id = ? AND owner_id = ?
            ''', (
                cluster_summary, risk_level, risk_level, risk_class,
                alert_recommendation,
                core_issue, report,
                platforms_json,
                risk_level, sentiment,
                now, topic_id, topic_id, owner_id
            ))
            conn.commit()
            return False
        else:
            # 新建（带 owner_id）
            cursor.execute('''
                INSERT INTO topic_summary
                (topic_id, keyword, topic_name, cluster_summary, risk_level, risk_class,
                 alert_recommendation, core_issue, report, platforms, sentiment,
                 first_seen, last_seen, post_count, owner_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                topic_id, keyword, topic_name, cluster_summary, risk_level, risk_class,
                alert_recommendation, core_issue, report, platforms_json, sentiment,
                now, now, 0, owner_id
            ))
            conn.commit()
            return True


def add_post_to_topic(topic_id: str, post_id: str, is_current: int = 1, owner_id: str = None):
    """将帖子关联到话题

    WS6-C2 v2.2: 必须传 owner_id，防止跨租户串改 ai_results.topic_id
    和 topic_summary.post_count。
    """
    if not owner_id:
        raise ValueError("add_post_to_topic 必须传 owner_id（WS6-C2 防越权）")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO topic_posts (topic_id, post_id, is_current)
            VALUES (?, ?, ?)
        ''', (topic_id, post_id, is_current))

        cursor.execute('''
            UPDATE ai_results SET topic_id = ?
            WHERE post_id = ? AND owner_id = ?
        ''', (topic_id, post_id, owner_id))

        cursor.execute('''
            UPDATE topic_summary SET post_count = (
                SELECT COUNT(*) FROM topic_posts WHERE topic_id = ?
            )
            WHERE topic_id = ? AND owner_id = ?
        ''', (topic_id, topic_id, owner_id))
        conn.commit()


def add_posts_to_topic_batch(topic_id: str, post_ids: list[str], owner_id: str):
    """批量关联帖子到话题（Fix 5.3：替代 N+1 逐条写入）

    在同一连接内批量执行，减少连接创建和提交开销。
    """
    if not owner_id:
        raise ValueError("add_posts_to_topic_batch 必须传 owner_id")
    if not post_ids:
        return
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            'INSERT OR IGNORE INTO topic_posts (topic_id, post_id, is_current) VALUES (?, ?, 1)',
            [(topic_id, pid) for pid in post_ids],
        )
        cursor.executemany(
            'UPDATE ai_results SET topic_id = ? WHERE post_id = ? AND owner_id = ?',
            [(topic_id, pid, owner_id) for pid in post_ids],
        )
        cursor.execute(
            'UPDATE topic_summary SET post_count = (SELECT COUNT(*) FROM topic_posts WHERE topic_id = ?) WHERE topic_id = ? AND owner_id = ?',
            (topic_id, topic_id, owner_id),
        )
        conn.commit()


def get_topic_summary_list(
    keyword: str = None,
    platform: str = None,
    sentiment: str = None,
    is_processed: int = None,
    limit: int = 50,
    owner_id: Optional[str] = None,
    is_admin: bool = False,
) -> list:
    """
    获取话题聚合列表（支持筛选）
    WS4.6：按 owner_id 过滤
    - is_admin=True → 全部
    - owner_id 传值 → owner_id = ? OR owner_id IS NULL
    - owner_id=None → 仅 owner_id IS NULL
    """
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM topic_summary WHERE 1=1"
        params = []

        if keyword:
            query += " AND keyword LIKE ?"
            params.append(f"%{keyword}%")

        if sentiment:
            query += " AND risk_class = ?"
            params.append(sentiment)

        if is_processed is not None:
            query += " AND is_processed = ?"
            params.append(is_processed)

        # WS4.6 隔离
        if is_admin:
            pass  # 不过滤
        elif owner_id is not None:
            query += " AND (owner_id = ? OR owner_id IS NULL)"
            params.append(owner_id)
        else:
            query += " AND owner_id IS NULL"

        query += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        # platforms JSON → list
        try:
            d["platforms"] = json.loads(d.get("platforms", "[]"))
        except Exception:
            d["platforms"] = []

        # 平台筛选（如果指定了 platform）
        if platform:
            # platforms 存的是 ["微博", "小红书"]，需要匹配
            plat_map = {"wb": "微博", "xhs": "小红书", "bili": "B站", "zhihu": "知乎", "dy": "抖音", "ks": "快手", "tieba": "贴吧"}
            target = plat_map.get(platform, platform)
            if target not in d["platforms"]:
                continue

        # 转换 risk_class → 中文 sentiment
        risk_class = d.get("risk_class", "neutral")
        sentiment_map = {"negative": "负面", "positive": "正面", "neutral": "中性"}
        d["sentiment"] = sentiment_map.get(risk_class, "中性")

        # 演化信号（暂无，从 topic_tracker 获取）
        d["evolution_signal"] = "unknown"

        # alert_recommendation 字段（默认 none，兼容旧数据）
        d["alert_recommendation"] = d.get("alert_recommendation", "none")

        results.append(d)

    return results


def get_topic_summary_by_id(topic_id: str, owner_id: Optional[str] = None, is_admin: bool = False) -> dict:
    """
    获取单个话题聚合详情
    WS4.6：返回 None 表示无权访问 / 不存在
    """
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if is_admin:
            cursor.execute("SELECT * FROM topic_summary WHERE topic_id = ?", (topic_id,))
        elif owner_id is not None:
            cursor.execute(
                "SELECT * FROM topic_summary WHERE topic_id = ? AND (owner_id = ? OR owner_id IS NULL)",
                (topic_id, owner_id),
            )
        else:
            cursor.execute(
                "SELECT * FROM topic_summary WHERE topic_id = ? AND owner_id IS NULL",
                (topic_id,),
            )
        row = cursor.fetchone()

    if not row:
        return None

    d = dict(row)
    try:
        d["platforms"] = json.loads(d.get("platforms", "[]"))
    except Exception:
        d["platforms"] = []

    risk_class = d.get("risk_class", "neutral")
    sentiment_map = {"negative": "负面", "positive": "正面", "neutral": "中性"}
    d["sentiment"] = sentiment_map.get(risk_class, "中性")

    # alert_recommendation 字段（默认 none，兼容旧数据）
    d["alert_recommendation"] = d.get("alert_recommendation", "none")

    return d


def get_topic_posts(topic_id: str, owner_id: Optional[str] = None, is_admin: bool = False) -> list:
    """
    获取话题关联的所有帖子详情
    WS4.6：按 owner_id 过滤
    """
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if is_admin:
            cursor.execute('''
                SELECT ar.* FROM topic_posts tp
                JOIN ai_results ar ON ar.post_id = tp.post_id
                WHERE tp.topic_id = ?
                ORDER BY tp.is_current DESC, ar.create_time DESC
            ''', (topic_id,))
        elif owner_id is not None:
            cursor.execute('''
                SELECT ar.* FROM topic_posts tp
                JOIN ai_results ar ON ar.post_id = tp.post_id
                WHERE tp.topic_id = ? AND (ar.owner_id = ? OR ar.owner_id IS NULL)
                ORDER BY tp.is_current DESC, ar.create_time DESC
            ''', (topic_id, owner_id))
        else:
            cursor.execute('''
                SELECT ar.* FROM topic_posts tp
                JOIN ai_results ar ON ar.post_id = tp.post_id
                WHERE tp.topic_id = ? AND ar.owner_id IS NULL
                ORDER BY tp.is_current DESC, ar.create_time DESC
            ''', (topic_id,))
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


def get_today_topics(owner_id: Optional[str] = None, is_admin: bool = False, limit: int = 5) -> list[dict]:
    """返回今日话题（按 risk_level 降序，用于今日摘要卡片）"""
    import datetime
    import sqlite3

    today = datetime.date.today().isoformat()

    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if is_admin:
            cursor.execute('''
                SELECT topic_name, risk_class, post_count, core_issue
                FROM topic_summary
                WHERE DATE(last_seen) = ?
                ORDER BY risk_level DESC
                LIMIT ?
            ''', (today, limit))
        else:
            cursor.execute('''
                SELECT topic_name, risk_class, post_count, core_issue
                FROM topic_summary
                WHERE DATE(last_seen) = ?
                  AND (owner_id = ? OR owner_id IS NULL)
                ORDER BY risk_level DESC
                LIMIT ?
            ''', (today, owner_id, limit))
        rows = cursor.fetchall()

    return [dict(r) for r in rows]


def mark_topic_processed(topic_id: str, owner_id: str = None) -> bool:
    """标记话题为已处理

    WS6-C2 v2.2: 必须传 owner_id，防止跨租户标记。
    """
    if not owner_id:
        raise ValueError("mark_topic_processed 必须传 owner_id（WS6-C2 防越权）")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE topic_summary SET is_processed = 1 WHERE topic_id = ? AND owner_id = ?",
            (topic_id, owner_id)
        )
        conn.commit()
        return cursor.rowcount > 0
