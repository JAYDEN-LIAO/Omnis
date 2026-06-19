"""
AgentMonitorService：Agent 监控聚合层
"""
from typing import Dict, List, Any, Optional

from backend.core.logger import get_logger
from backend.core.metrics import (
    AGENT_TOOL_CALLS, AGENT_MEMORY_WRITES, AGENT_TURNS, CIRCUIT_BREAKER_STATE,
    AGENT_PLAN_GENERATION_TOTAL,
)
from .agent_health_db import AgentHealthDB

logger = get_logger("admin.agent_monitor")


class AgentMonitorService:
    def __init__(self):
        self.health_db = AgentHealthDB()

    def get_overview(self) -> Dict[str, Any]:
        tool_stats = self._get_tool_call_summary()
        mem = self._get_counter_sum_by_label(AGENT_MEMORY_WRITES, "status")
        mem_success, mem_error = mem.get("success", 0), mem.get("error", 0)
        circuit = self._get_circuit_summary()
        mem_store = self._get_memory_store_stats()
        wf_stats = self.health_db.get_workflow_stats(hours=24)
        plan_stats = self.get_planning_stats()

        return {
            "agent": {
                "total_turns": self._get_counter_value(AGENT_TURNS),
                "total_tool_calls": tool_stats["total"],
                "tool_error_rate": round(tool_stats["error_rate"], 3),
                "active_sessions": self._get_active_session_count(),
            },
            "memory": {
                "write_success": mem_success,
                "write_error": mem_error,
                "total_records": mem_store["total"],
                "breakdown": mem_store.get("breakdown", {}),
            },
            "circuit": {
                "open_count": circuit["open_count"],
                "breakers": circuit["details"],
            },
            "workflows": {
                "total_executions_24h": wf_stats["total_executions"],
                "success_count": wf_stats["success_count"],
                "failed_count": wf_stats["failed_count"],
                "cancelled_count": wf_stats["cancelled_count"],
                "success_rate": round(wf_stats["success_rate"], 3),
                "avg_duration_seconds": wf_stats["avg_duration_seconds"],
            },
            "planning": {
                "total_plans": plan_stats["total_plans"],
                "success_count": plan_stats["success_count"],
                "fallback_count": plan_stats["fallback_count"],
                "template_hit_count": plan_stats["template_hit_count"],
                "parse_error_count": plan_stats["parse_error_count"],
                "success_rate": round(plan_stats["success_rate"], 3),
                "template_hit_rate": round(plan_stats["template_hit_rate"], 3),
            },
        }

    def get_tool_health(self) -> List[Dict]:
        tools = []
        for name in self._get_known_tool_names():
            success = error = 0
            try:
                for s in AGENT_TOOL_CALLS.collect()[0].samples:
                    if s.name.endswith("_total") and s.labels.get("tool") == name:
                        if s.labels.get("status") == "success":
                            success += int(s.value)
                        elif s.labels.get("status") == "error":
                            error += int(s.value)
            except Exception:
                pass
            tools.append({
                "tool": name,
                "total_calls": success + error,
                "success_count": success,
                "error_count": error,
                "success_rate": round(success / max(success + error, 1), 3),
                "circuit_state": self._get_circuit_state(name),
            })
        tools.sort(key=lambda t: t["error_count"], reverse=True)
        return tools

    def get_session_stats(self, limit: int = 20) -> List[Dict]:
        from backend.services.agent_service.memory.memory_store import AgentMemoryStore
        store = AgentMemoryStore()
        sessions = store.get_all_sessions(limit=limit, owner_id="")
        for s in sessions:
            owner = s.get("owner_id", "")
            s["message_count"] = (
                len(store.get_messages(s["session_id"], owner_id=owner)) if owner else 0
            )
        return sessions

    def get_diagnosis_events(self, limit: int = 50) -> List[Dict]:
        return self.health_db.get_recent_diagnosis(limit=limit)

    def get_workflow_stats(self, owner_id: str = "", hours: int = 24) -> Dict:
        return self.health_db.get_workflow_stats(hours=hours)

    def get_planning_stats(self) -> Dict:
        """规划阶段统计（直接从 Prometheus 读）"""
        samples = self._get_counter_sum_by_label(AGENT_PLAN_GENERATION_TOTAL, "status")
        success = samples.get("success", 0)
        fallback = samples.get("fallback", 0)
        template_hit = samples.get("template_hit", 0)
        parse_error = samples.get("parse_error", 0)
        total = success + fallback + template_hit + parse_error
        return {
            "total_plans": total,
            "success_count": success,
            "fallback_count": fallback,
            "template_hit_count": template_hit,
            "parse_error_count": parse_error,
            "success_rate": success / max(total, 1),
            "template_hit_rate": template_hit / max(total, 1),
        }

    def record_diagnosis(self, owner_id: str, tool_name: str,
                         error_type: str, recovery: str, success: bool):
        self.health_db.insert_diagnosis(
            owner_id=owner_id, tool_name=tool_name,
            error_type=error_type, recovery=recovery, success=success)

    # ── 内部辅助 ──

    def _get_counter_value(self, counter) -> int:
        try:
            for s in counter.collect()[0].samples:
                if s.name.endswith("_total") and not s.labels:
                    return int(s.value)
        except Exception:
            pass
        return 0

    def _get_counter_sum_by_label(self, counter, key: str) -> Dict[str, int]:
        result = {}
        try:
            for s in counter.collect()[0].samples:
                if s.name.endswith("_total"):
                    v = s.labels.get(key, "")
                    result[v] = result.get(v, 0) + int(s.value)
        except Exception:
            pass
        return result

    def _get_tool_call_summary(self) -> Dict:
        total = errors = 0
        try:
            for s in AGENT_TOOL_CALLS.collect()[0].samples:
                if s.name.endswith("_total"):
                    total += int(s.value)
                    if s.labels.get("status") == "error":
                        errors += int(s.value)
        except Exception:
            pass
        return {"total": total, "error_count": errors, "error_rate": errors / max(total, 1)}

    def _get_circuit_summary(self) -> Dict:
        open_count = 0
        details = []
        try:
            for s in CIRCUIT_BREAKER_STATE.collect()[0].samples:
                state = {0: "closed", 1: "half_open", 2: "open"}.get(int(s.value), "unknown")
                if state == "open":
                    open_count += 1
                details.append({"name": s.labels.get("name", ""), "state": state})
        except Exception:
            pass
        return {"open_count": open_count, "details": details}

    def _get_circuit_state(self, tool_name: str) -> str:
        try:
            from backend.services.agent_service.diagnosis.diagnosis_engine import _circuit_registry
            return _circuit_registry.get(tool_name).state.value
        except Exception:
            pass
        return "unknown"

    def _get_memory_store_stats(self) -> Dict:
        try:
            from backend.services.agent_service.memory.memory_store import AgentMemoryStore
            stats = AgentMemoryStore().get_memory_stats()
            return {"total": sum(stats.values()), "breakdown": stats}
        except Exception:
            pass
        return {"total": 0, "breakdown": {}}

    def _get_active_session_count(self) -> int:
        try:
            from backend.services.agent_service.memory.memory_store import AgentMemoryStore
            return AgentMemoryStore().count_active_sessions(24)
        except Exception:
            pass
        return 0

    def _get_known_tool_names(self) -> List[str]:
        try:
            from backend.services.agent_service.tools import AVAILABLE_TOOLS
            return list(AVAILABLE_TOOLS.keys())
        except Exception:
            pass
        return []


_monitor: Optional[AgentMonitorService] = None


def get_agent_monitor() -> AgentMonitorService:
    global _monitor
    if _monitor is None:
        _monitor = AgentMonitorService()
    return _monitor
