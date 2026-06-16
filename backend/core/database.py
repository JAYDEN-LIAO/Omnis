# backend/core/database.py
import sqlite3
from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("core.db")

def get_db_connection(db_path=None, timeout=15.0):
    target_path = db_path if db_path else settings.STATE_DB_PATH
    try:
        conn = sqlite3.connect(target_path, timeout=timeout)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection failed: {e}")
        raise