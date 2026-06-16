"""
Agent 健康数据库 — 诊断事件持久化
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from backend.core.logger import get_logger

logger = get_logger("admin.health_db")

DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "agent_health.db"


class AgentHealthDB:
    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or DB_PATH)
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS agent_diagnosis_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT DEFAULT '',
                    tool_name TEXT NOT NULL,
                    error_type TEXT,
                    recovery_strategy TEXT,
                    success INTEGER DEFAULT 0,
                    latency_ms INTEGER,
                    created_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_diag_created
                ON agent_diagnosis_log(created_at DESC)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_diag_tool
                ON agent_diagnosis_log(tool_name)
            """)
            # -- agent_health_snapshot 表（Agent Ops Engine 趋势快照） --
            c.execute("""
                CREATE TABLE IF NOT EXISTS agent_health_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_turns INTEGER DEFAULT 0,
                    total_tool_calls INTEGER DEFAULT 0,
                    tool_error_rate REAL DEFAULT 0,
                    active_sessions INTEGER DEFAULT 0,
                    memory_records INTEGER DEFAULT 0,
                    open_circuits INTEGER DEFAULT 0,
                    tool_details TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshot_created
                ON agent_health_snapshot(created_at DESC)
            """)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=5000")
            conn.commit()

    def insert_diagnosis(self, owner_id: str, tool_name: str, error_type: str,
                         recovery: str, success: bool, latency_ms: int = 0) -> int:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO agent_diagnosis_log
                (owner_id, tool_name, error_type, recovery_strategy, success, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (owner_id, tool_name, error_type, recovery, int(success), latency_ms,
                  datetime.now().isoformat()))
            conn.commit()
            return c.lastrowid

    def get_recent_diagnosis(self, limit: int = 50) -> list:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT * FROM agent_diagnosis_log ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in c.fetchall()]

    def cleanup_old(self, keep: int = 2000) -> int:
        """惰性清理：保留最近 N 条，由调度器每天调用一次"""
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                DELETE FROM agent_diagnosis_log
                WHERE id NOT IN (SELECT id FROM agent_diagnosis_log ORDER BY created_at DESC LIMIT ?)
            """, (keep,))
            deleted = c.rowcount
            conn.commit()
            return deleted

    # ──────────────── Agent Ops Engine: 快照 ────────────────

    def insert_snapshot(self, total_turns: int = 0, total_tool_calls: int = 0,
                        tool_error_rate: float = 0, active_sessions: int = 0,
                        memory_records: int = 0, open_circuits: int = 0,
                        tool_details: str = "[]"):
        """插入 30min 粒度的指标快照，供趋势分析用。"""
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO agent_health_snapshot
                (total_turns, total_tool_calls, tool_error_rate, active_sessions,
                 memory_records, open_circuits, tool_details, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (total_turns, total_tool_calls, tool_error_rate, active_sessions,
                  memory_records, open_circuits, tool_details, datetime.now().isoformat()))
            conn.commit()

    def get_snapshots(self, hours: int = 24) -> List[Dict]:
        """查询最近 hours 小时内的快照，用于基线对比。"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT * FROM agent_health_snapshot
                WHERE created_at >= ?
                ORDER BY created_at ASC
            """, (cutoff,))
            return [dict(r) for r in c.fetchall()]

    def get_diagnosis_since(self, hours: int = 24, limit: int = 100) -> List[Dict]:
        """查询最近 hours 小时内的诊断事件。"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT * FROM agent_diagnosis_log
                WHERE created_at >= ?
                ORDER BY created_at DESC LIMIT ?
            """, (cutoff, limit))
            return [dict(r) for r in c.fetchall()]

    def cleanup_snapshots(self, keep_hours: int = 168) -> int:
        """删除超过 keep_hours 的旧快照（默认 7 天）。"""
        cutoff = (datetime.now() - timedelta(hours=keep_hours)).isoformat()
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                DELETE FROM agent_health_snapshot
                WHERE created_at < ?
            """, (cutoff,))
            deleted = c.rowcount
            conn.commit()
            return deleted
