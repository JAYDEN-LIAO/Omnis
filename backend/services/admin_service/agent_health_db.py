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
            # P7: workflow_execution_log 表
            c.execute("""
                CREATE TABLE IF NOT EXISTS workflow_execution_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id INTEGER NOT NULL DEFAULT 0,
                    workflow_name TEXT NOT NULL DEFAULT '',
                    owner_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    duration_seconds REAL DEFAULT 0,
                    total_steps INTEGER DEFAULT 0,
                    failed_step INTEGER DEFAULT 0,
                    error_message TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_wflog_workflow ON workflow_execution_log(workflow_id)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_wflog_owner ON workflow_execution_log(owner_id)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_wflog_created ON workflow_execution_log(created_at)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_wflog_status ON workflow_execution_log(status)
            """)
            # P7: 幂等迁移 snapshot 表加字段
            self._migrate_snapshot_table(c)
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
            return c.lastrowid

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

    # ──────────────── P7: snapshot 表迁移 ────────────────

    def _migrate_snapshot_table(self, cursor):
        """给 agent_health_snapshot 表加工作流/规划字段（幂等迁移）"""
        fields = [
            ("workflow_total", "INTEGER DEFAULT 0"),
            ("workflow_failed", "INTEGER DEFAULT 0"),
            ("workflow_cancelled", "INTEGER DEFAULT 0"),
            ("plan_success_rate", "REAL DEFAULT 0"),
            ("plan_template_hit_rate", "REAL DEFAULT 0"),
        ]
        for col, decl in fields:
            try:
                cursor.execute(f"ALTER TABLE agent_health_snapshot ADD COLUMN {col} {decl}")
            except Exception:
                pass  # 已存在则跳过

    # ──────────────── P7: 工作流日志 CRUD ────────────────

    def insert_workflow_log(self, workflow_id: int, workflow_name: str,
                            owner_id: str, status: str, duration_seconds: float,
                            total_steps: int, failed_step: int,
                            error_message: str) -> int:
        """写入工作流执行日志"""
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO workflow_execution_log
                (workflow_id, workflow_name, owner_id, status, duration_seconds,
                 total_steps, failed_step, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (workflow_id, workflow_name, owner_id, status,
                  duration_seconds, total_steps, failed_step,
                  error_message[:1000] if error_message else "",
                  datetime.now().isoformat()))
            conn.commit()
            return c.lastrowid

    def get_workflow_logs(self, owner_id: str = "", workflow_id: int = 0,
                          hours: int = 24, limit: int = 50) -> list:
        """查询工作流执行日志（多维过滤）"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        where = ["created_at >= ?"]
        params = [cutoff]
        if owner_id:
            where.append("owner_id = ?")
            params.append(owner_id)
        if workflow_id:
            where.append("workflow_id = ?")
            params.append(workflow_id)
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(f"""
                SELECT * FROM workflow_execution_log
                WHERE {' AND '.join(where)}
                ORDER BY created_at DESC LIMIT ?
            """, params + [limit])
            return [dict(r) for r in c.fetchall()]

    def get_workflow_stats(self, hours: int = 24) -> dict:
        """工作流执行统计：总数/成功/失败/取消/平均耗时"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count,
                    SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count,
                    SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancelled_count,
                    AVG(duration_seconds) AS avg_duration
                FROM workflow_execution_log
                WHERE created_at >= ?
            """, (cutoff,))
            r = dict(c.fetchone())
            total = r.get("total") or 0
            return {
                "total_executions": total,
                "success_count": r.get("success_count") or 0,
                "failed_count": r.get("failed_count") or 0,
                "cancelled_count": r.get("cancelled_count") or 0,
                "success_rate": (r.get("success_count") or 0) / max(total, 1),
                "avg_duration_seconds": round(r.get("avg_duration") or 0, 1),
            }

    def update_snapshot_with_workflow(self, snapshot_id: int,
                                      workflow_total: int, workflow_failed: int,
                                      workflow_cancelled: int,
                                      plan_success_rate: float,
                                      plan_template_hit_rate: float):
        """更新 snapshot 的工作流/规划字段"""
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE agent_health_snapshot
                SET workflow_total=?, workflow_failed=?, workflow_cancelled=?,
                    plan_success_rate=?, plan_template_hit_rate=?
                WHERE id=?
            """, (workflow_total, workflow_failed, workflow_cancelled,
                  plan_success_rate, plan_template_hit_rate, snapshot_id))
            conn.commit()

    def get_workflow_trend(self, workflow_id: int, hours: int = 168) -> dict:
        """★ 弱点3：单工作流的执行趋势（每日成功率/平均耗时/Top 失败原因）"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            # 1. 总体统计
            c.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count,
                       AVG(duration_seconds) AS avg_duration
                FROM workflow_execution_log
                WHERE workflow_id=? AND created_at >= ?
            """, (workflow_id, cutoff))
            summary_row = dict(c.fetchone())
            total = summary_row.get("total") or 0
            summary = {
                "total_executions": total,
                "success_rate": (summary_row.get("success_count") or 0) / max(total, 1),
                "avg_duration_seconds": round(summary_row.get("avg_duration") or 0, 1),
            }

            # 2. 按天聚合
            c.execute("""
                SELECT DATE(created_at) AS date,
                       COUNT(*) AS total,
                       SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count,
                       AVG(duration_seconds) AS avg_duration
                FROM workflow_execution_log
                WHERE workflow_id=? AND created_at >= ?
                GROUP BY DATE(created_at)
                ORDER BY date ASC
            """, (workflow_id, cutoff))
            daily = []
            for r in c.fetchall():
                day_total = r["total"]
                daily.append({
                    "date": r["date"],
                    "total": day_total,
                    "success": r["success_count"] or 0,
                    "success_rate": (r["success_count"] or 0) / max(day_total, 1),
                    "avg_duration": round(r["avg_duration"] or 0, 1),
                })

            # 3. Top 失败原因
            c.execute("""
                SELECT error_message, COUNT(*) AS count
                FROM workflow_execution_log
                WHERE workflow_id=? AND created_at >= ?
                      AND status='failed' AND error_message != ''
                GROUP BY error_message
                ORDER BY count DESC
                LIMIT 3
            """, (workflow_id, cutoff))
            top_errors = [{"error_message": r["error_message"][:200], "count": r["count"]}
                          for r in c.fetchall()]

            return {
                "workflow_id": workflow_id,
                "hours": hours,
                "summary": summary,
                "daily": daily,
                "top_errors": top_errors,
            }
