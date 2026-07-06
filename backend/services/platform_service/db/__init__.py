# backend/services/platform_service/db/__init__.py
"""
数据库访问层 — 按数据域拆分
对外接口与 db_manager.py 完全兼容
"""
from backend.core.database import get_db_connection  # re-export for backward compat

from .db_init import init_radar_db
from .db_processed import is_processed, mark_processed, get_processed_status_batch, mark_processed_batch, get_unprocessed_posts
from .db_ai_results import save_ai_result, get_latest_results, get_volume_stats, get_today_summary_data
from .db_topic import create_or_update_topic_summary, get_topic_summary_list, get_topic_summary_by_id, mark_topic_processed, add_post_to_topic, add_posts_to_topic_batch, get_topic_posts, get_today_topics
from .db_settings import get_system_settings, save_system_settings, get_aggregated_keywords, get_aggregated_platforms
from .db_push import _ensure_push_settings_table, get_push_config, save_push_config, get_all_push_configs, record_suppressed_push, get_today_suppressed_count, get_owner_by_rss_token
from .db_audit import insert_audit_log, get_audit_log

__all__ = [
    "init_radar_db",
    "is_processed", "mark_processed", "get_processed_status_batch", "mark_processed_batch", "get_unprocessed_posts",
    "save_ai_result", "get_latest_results", "get_volume_stats", "get_today_summary_data",
    "create_or_update_topic_summary", "get_topic_summary_list", "get_topic_summary_by_id", "mark_topic_processed",
    "add_post_to_topic", "add_posts_to_topic_batch", "get_topic_posts", "get_today_topics",
    "get_system_settings", "save_system_settings", "get_aggregated_keywords", "get_aggregated_platforms",
    "get_db_connection",
    "_ensure_push_settings_table", "get_push_config", "save_push_config", "get_all_push_configs",
    "record_suppressed_push", "get_today_suppressed_count", "get_owner_by_rss_token",
    "insert_audit_log", "get_audit_log",
    "get_db_connection",
]

# 保持模块级初始化行为（与旧 db_manager.py 底部 init_radar_db() 一致）
init_radar_db()
