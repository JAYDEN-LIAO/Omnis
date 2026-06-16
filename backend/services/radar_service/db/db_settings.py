# backend/services/radar_service/db/db_settings.py
"""system_settings 表操作 — per-user 隔离"""
import json

from backend.core.database import get_db_connection

DEFAULT_CONFIG = {
    "keywords": [],
    "inactive_keywords": [],
    "platforms": ["wb", "xhs"],
    "push_summary": True,
    "push_time": "18:00",
    "alert_negative": True,
    "monitor_frequency": 60,
    "start_time": "08:00",
}


def get_system_settings(owner_id: str = "admin") -> dict:
    """获取指定用户的系统配置。owner_id='admin' 返回全局默认配置。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT config_json FROM system_settings WHERE owner_id = ?", (owner_id,))
        row = cursor.fetchone()
    if row:
        return json.loads(row[0])
    return dict(DEFAULT_CONFIG)


def save_system_settings(config_dict: dict, owner_id: str = "admin") -> None:
    """保存指定用户的系统配置。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM system_settings WHERE owner_id = ?", (owner_id,))
        cursor.execute(
            "INSERT INTO system_settings (owner_id, config_json) VALUES (?, ?)",
            (owner_id, json.dumps(config_dict)),
        )


def get_aggregated_keywords() -> list[str]:
    """收集所有用户的关键词并集，用于调度器/爬虫全局扫描。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT config_json FROM system_settings")
        rows = cursor.fetchall()
    seen = set()
    result = []
    for r in rows:
        conf = json.loads(r[0])
        for kw in conf.get("keywords", []):
            text = kw["text"] if isinstance(kw, dict) else str(kw)
            if text and text not in seen:
                seen.add(text)
                result.append(text)
    return result


def get_aggregated_platforms() -> list[str]:
    """收集所有用户的平台并集，用于调度器/爬虫。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT config_json FROM system_settings")
        rows = cursor.fetchall()
    seen = set()
    for r in rows:
        conf = json.loads(r[0])
        for p in conf.get("platforms", []):
            if p not in seen:
                seen.add(p)
    return sorted(seen)
