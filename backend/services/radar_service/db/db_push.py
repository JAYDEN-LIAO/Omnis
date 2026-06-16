# backend/services/radar_service/db/db_push.py
"""push_settings 表操作 + suppressed push"""
import json
import datetime
from typing import Optional

from backend.core.database import get_db_connection
from backend.core.logger import get_logger

logger = get_logger("radar.db")

from .db_audit import insert_audit_log


def _ensure_push_settings_table():
    """确保 push_settings 表存在（v2.2：per-owner，含 rss 通道）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # 检查表是否已有 owner_id 列（v2.2 迁移）
        cursor.execute("PRAGMA table_info(push_settings)")
        cols = {row[1] for row in cursor.fetchall()}

        if cols and "owner_id" not in cols:
            # 旧表（无 owner_id）→ 先备份到 push_settings_backup，再重建
            logger.warning("[push_settings] 旧表无 owner_id，备份后重建")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS push_settings_backup AS SELECT * FROM push_settings
            """)
            cursor.execute("DROP TABLE push_settings")
            cols = set()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS push_settings (
                owner_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                config_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (owner_id, channel)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_push_settings_owner ON push_settings(owner_id)')
        conn.commit()


def get_push_config(owner_id: str, channel: str) -> dict:
    """读取指定用户指定通道的配置（v2.2：per-owner）"""
    _ensure_push_settings_table()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT config_json FROM push_settings WHERE owner_id = ? AND channel = ?",
            (owner_id, channel)
        )
        row = cursor.fetchone()
    if row:
        return json.loads(row[0])
    # 返回默认空配置
    defaults = {
        "email": {"enabled": False, "risk_min_level": 3},
        "wecom": {"enabled": False, "risk_min_level": 2},
        "feishu": {"enabled": False, "risk_min_level": 2},
        "rss": {"enabled": False, "access_token": ""},
    }
    return defaults.get(channel, {"enabled": False, "risk_min_level": 1})


def save_push_config(owner_id: str, channel: str, config: dict) -> None:
    """保存指定用户指定通道的配置（v2.2：per-owner）"""
    _ensure_push_settings_table()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO push_settings (owner_id, channel, config_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(owner_id, channel) DO UPDATE SET
                config_json = excluded.config_json,
                updated_at = CURRENT_TIMESTAMP
        ''', (owner_id, channel, json.dumps(config)))
        conn.commit()


def get_all_push_configs(owner_id: Optional[str] = None) -> dict[str, dict]:
    """返回某用户的所有推送通道配置（v2.2：per-owner）
    owner_id=None 时返回全部（admin 视角）"""
    _ensure_push_settings_table()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if owner_id is None:
            cursor.execute("SELECT owner_id, channel, config_json FROM push_settings")
            rows = cursor.fetchall()
        else:
            cursor.execute(
                "SELECT channel, config_json FROM push_settings WHERE owner_id = ?",
                (owner_id,)
            )
            rows = cursor.fetchall()
    result: dict[str, dict] = {}
    for row in rows:
        if owner_id is None and len(row) == 3:
            # 全部模式：{(owner_id, channel): config}
            result[f"{row[0]}:{row[1]}"] = json.loads(row[2])
        else:
            result[row[0]] = json.loads(row[1])
    # 补全未配置的通道默认值
    default_channels = ("email", "wecom", "feishu", "rss")
    if owner_id is not None:
        for ch in default_channels:
            if ch not in result:
                if ch == "rss":
                    result[ch] = {"enabled": False, "access_token": ""}
                else:
                    result[ch] = {"enabled": False, "risk_min_level": 2}
    return result


def get_owner_by_rss_token(token: str) -> Optional[str]:
    """根据 RSS token 查找 owner_id"""
    import re

    safe_token = re.sub(r'([%_])', r'\\\1', token)
    _ensure_push_settings_table()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT owner_id FROM push_settings WHERE channel = 'rss' AND config_json LIKE ? ESCAPE '\\'",
            (f'%{safe_token}%',),
        )
        row = cursor.fetchone()

    return row[0] if row else None


# ============================================================
# v2.2 suppressed push tracking
# ============================================================

def record_suppressed_push(
    owner_id: str,
    keyword: str,
    topic_id: str,
    topic_name: str,
    reason: str = "agent_decision",
):
    """
    记录 Agent 压住的推送内容（push_mode=important 时 Agent 决定不推）。

    reason:
      - "agent_decision": Agent 判断为普通讨论，不值得推
      - "frequency_throttle": 同一话题短时间内多次更新，只推一次
    """
    insert_audit_log(
        action="suppressed_push",
        detail={
            "owner_id": owner_id,
            "topic_name": topic_name,
            "reason": reason,
        },
        keyword=keyword,
        topic_id=topic_id,
        level="INFO",
        owner_id=owner_id,  # v2.2: 写入专列，便于高效过滤
    )


def get_today_suppressed_count(owner_id: Optional[str] = None, is_admin: bool = False) -> int:
    """获取今日被 Agent 压住的推送数量（v2.2: 使用 owner_id 专列查询）。"""
    import datetime
    today = datetime.date.today().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if is_admin:
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM audit_log "
                "WHERE action = 'suppressed_push' AND DATE(created_at) = ?",
                (today,),
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM audit_log "
                "WHERE action = 'suppressed_push' AND DATE(created_at) = ? "
                "AND owner_id = ?",
                (today, owner_id or ""),
            )
        row = cursor.fetchone()
    return row[0] if row else 0
