# backend/services/platform_service/scheduler.py
"""
APScheduler 定时调度模块（v2.2 per-user 版本）

架构：
  - 全局 BackgroundScheduler 管理所有 job
  - 一个全局扫描任务（每 monitor_frequency 小时执行），但会遍历所有有订阅的用户
  - 一个全局每日简报任务
  - 底层合并关键词：从所有用户的 subscription 表收集关键词，全局爬 1 轮，
    然后按 owner 拆分跑 Pipeline

全局锁：
  - _scan_lock: 全局唯一扫描锁，防止多用户并发扫描（爬虫会抢资源）
  - 锁被持有时，新触发的任务直接跳过
"""
import asyncio
import datetime
import threading
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.core.logger import get_logger
from backend.core.context import set_trace_id, generate_trace_id
import os

logger = get_logger("radar.scheduler")

# ---- 全局状态 ----
_scheduler: Optional[BackgroundScheduler] = None
_scan_lock: asyncio.Lock = asyncio.Lock()
_is_running: bool = False

async def _run_extra_pipelines(owner_id: str, pipeline_types: list[str], keywords: list[str]):
    """使用组合工具执行附加管线。"""
    await _run_extra_pipelines_composite(owner_id, pipeline_types, keywords)


async def _run_extra_pipelines_composite(owner_id: str, pipeline_types, keywords):
    """新路径：走组合工具（★ R-015 关键：set_current_owner 跨线程）"""
    from backend.services.agent_service.tools._owner import (
        set_current_owner, reset_current_owner,
    )
    from backend.services.agent_service.tools._base import (
        set_current_cancel_event, get_tool,
    )

    # ★ R-015 关键：scheduler 线程是新 loop，ContextVar 必须显式 set
    token = set_current_owner(owner_id)
    cancel_token = set_current_cancel_event(None)
    try:
        for pt in pipeline_types:
            if pt == "risk":
                continue  # risk 走原 job_async
            kw = keywords[0] if keywords else ""
            plat = ["wb", "xhs"]  # 默认平台（可扩展：读 subscription.platforms）

            if pt == "guide":
                func = get_tool("deep_analyze_topic")
                if func is None:
                    logger.warning("[Scheduler] composite tool deep_analyze_topic 未注册，跳过 guide")
                    continue
                result = await func["func"](keyword=kw, analysis_type="guide", platforms=plat)
            elif pt == "celebrity":
                func = get_tool("deep_analyze_topic")
                if func is None:
                    logger.warning("[Scheduler] composite tool deep_analyze_topic 未注册，跳过 celebrity")
                    continue
                result = await func["func"](keyword=kw, analysis_type="celebrity", platforms=plat)
            elif pt == "briefing":
                func = get_tool("briefing_digest")
                if func is None:
                    logger.warning("[Scheduler] composite tool briefing_digest 未注册，跳过 briefing")
                    continue
                result = await func["func"](keyword=kw, platforms=plat)
            elif pt == "alert":
                func = get_tool("scan_and_alert")
                if func is None:
                    logger.warning("[Scheduler] composite tool scan_and_alert 未注册，跳过 alert")
                    continue
                result = await func["func"](keyword=kw, platforms=plat, channel="email")
            else:
                logger.warning(f"[Scheduler] 未知 pipeline_type={pt}")
                continue

            logger.info(f"[Scheduler] {pt} composite 完成 (user={owner_id[:8]})")
    finally:
        set_current_cancel_event(None)
        reset_current_owner(token)


def _collect_users_and_keywords():
    """
    从 subscription 表收集所有非暂停用户的订阅关键词和 pipeline 类型。

    Returns:
        dict[str, list[tuple[str, list[str], list[str]]]]:
            {owner_id: [(keyword, platforms, pipeline_types), ...]}
    """
    try:
        import sqlite3
        import json
        from backend.core.database import get_db_connection
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT owner_id, name, platforms, pipeline_types FROM subscription WHERE is_active = 1"
            )
            rows = cursor.fetchall()
        result: dict[str, list[tuple[str, list[str], list[str]]]] = {}
        for r in rows:
            oid = r["owner_id"]
            name = r["name"]
            platforms = []
            try:
                platforms = json.loads(r["platforms"] or "[]")
            except Exception:
                pass
            pipeline_types = ["risk"]
            try:
                pipeline_types = json.loads(r["pipeline_types"] or '["risk"]')
            except Exception:
                pass
            result.setdefault(oid, []).append((name, platforms, pipeline_types))
        return result
    except Exception as e:
        logger.warning(f"[Scheduler] 读取 subscriptions 失败: {e}")
        return {}


def scheduler_start() -> tuple[bool, str]:
    """启动调度器"""
    global _scheduler, _is_running

    if _is_running and _scheduler is not None:
        return True, "调度器已在运行中"

    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    _scheduler.start()
    _is_running = True

    _schedule_memory_cleanup()

    return True, "调度器已启动（仅运行用户定时工作流与内存清理）"


def scheduler_stop() -> tuple[bool, str]:
    """停止调度器"""
    global _scheduler, _is_running

    if _scheduler is None:
        return True, "调度器未运行"

    _scheduler.shutdown(wait=False)
    _is_running = False
    _scheduler = None
    logger.info("[Scheduler] 调度器已停止")
    return True, "调度器已停止"


def scheduler_status() -> dict:
    """返回调度器当前状态"""
    global _scheduler, _is_running

    if not _is_running or _scheduler is None:
        return {
            "active": False,
            "next_run": None,
            "interval_hours": 1,
            "scan_in_progress": _scan_lock.locked(),
        }

    user_count = len(_collect_users_and_keywords())

    return {
        "active": True,
        "next_run": None,
        "interval_hours": 1,
        "scan_in_progress": _scan_lock.locked(),
        "active_users": user_count,
    }


# ---- 每日简报任务 ----

# ---- 每日 03:00 fact_memory TTL 清理 ----

def _get_memory_cleanup_job_id() -> str:
    return "agent_memory_cleanup"


def _run_memory_cleanup():
    """每日 03:00 执行 fact_memory 过期清理"""
    try:
        from services.agent_service.memory.memory_manager import AgentMemoryManager
        mgr = AgentMemoryManager()
        deleted = mgr.cleanup_expired_memory()
        logger.info(f"[Scheduler] 记忆清理完成: 删除 {deleted} 条过期 fact")
    except Exception as e:
        logger.error(f"[Scheduler] 记忆清理异常: {e}", exc_info=True)


def _schedule_memory_cleanup():
    """注册每日 03:00 fact_memory 过期清理任务"""
    global _scheduler
    if _scheduler is None:
        return

    old_job = _scheduler.get_job(_get_memory_cleanup_job_id())
    if old_job:
        _scheduler.remove_job(_get_memory_cleanup_job_id())

    trigger = CronTrigger(hour=3, minute=0, second=0, timezone="Asia/Shanghai")
    _scheduler.add_job(
        _run_memory_cleanup,
        trigger=trigger,
        id=_get_memory_cleanup_job_id(),
        replace_existing=True,
        misfire_grace_time=600,
    )
    logger.info("[Scheduler] fact_memory 过期清理任务已注册: 03:00 (Asia/Shanghai)")


# ============================================================
# v2.0 P4: 用户工作流调度
# ============================================================

_MAX_CONCURRENT_WORKFLOWS = 4
_WF_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENT_WORKFLOWS)
from backend.services.agent_service.workflows_db import _WF_CANCEL_EVENTS, _WF_CANCEL_LOCK


def _run_user_workflows():
    """每分钟检查一次，执行到期的用户工作流。

    ★ R-011 修订：入口 set_trace_id；Semaphore(4) 限流。
    """
    set_trace_id(generate_trace_id())
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_due_workflows())
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"[Scheduler] _run_user_workflows 异常: {e}", exc_info=True)


async def _run_due_workflows():
    """遍历到期工作流，用 Semaphore 限流执行。"""
    from backend.services.agent_service.workflows_db import WorkflowsDB
    db = WorkflowsDB()
    rows = db.list_due_user_workflows()
    for row in rows:
        await _WF_SEMAPHORE.acquire()
        try:
            await _execute_workflow_row(row)
        finally:
            _WF_SEMAPHORE.release()


async def _execute_workflow_row(workflow: dict):
    """执行单条用户工作流。"""
    from backend.services.agent_service.workflows_db import execute_workflow_steps
    from backend.core.metrics import WORKFLOW_EXECUTIONS_TOTAL, WORKFLOW_EXECUTION_DURATION
    import json as _json
    wf_id = workflow["id"]
    owner_id = workflow["owner_id"]
    steps = _json.loads(workflow["steps_json"])

    cancel_event = asyncio.Event()
    with _WF_CANCEL_LOCK:
        _WF_CANCEL_EVENTS[wf_id] = cancel_event

    start = time.time()
    status = "success"
    error_msg = ""
    try:
        result_json = await execute_workflow_steps(
            steps=steps,
            initial_params={},
            owner_id=owner_id,
            cancel_event=cancel_event,
            workflow_id=wf_id,
            workflow_name=workflow["name"],
        )
        result = _json.loads(result_json)
        duration = time.time() - start
        if result.get("error"):
            if result.get("message") == "用户取消":
                status = "cancelled"
            else:
                status = "failed"
            error_msg = result.get("error", "")
            WORKFLOW_EXECUTIONS_TOTAL.labels(status=status).inc()
            if status == "cancelled":
                WORKFLOW_EXECUTION_DURATION.observe(duration)
            logger.warning(
                f"[Workflow] wf={wf_id} {status}: "
                f"step={result.get('step')} err={error_msg[:100]}"
            )
        else:
            status = "success"
            logger.info(f"[Workflow] wf={wf_id} success: {duration:.1f}s")
            WORKFLOW_EXECUTIONS_TOTAL.labels(status="success").inc()
            WORKFLOW_EXECUTION_DURATION.observe(duration)
            _push_workflow_result(owner_id, workflow["name"], result.get("results", {}))
    except Exception as e:
        duration = time.time() - start
        status = "failed"
        error_msg = str(e)
        WORKFLOW_EXECUTIONS_TOTAL.labels(status="failed").inc()
        logger.error(f"[Workflow] wf={wf_id} 异常: {e}", exc_info=True)
        try:
            from backend.services.admin_service.agent_health_db import AgentHealthDB
            AgentHealthDB().insert_workflow_log(
                workflow_id=wf_id, workflow_name=workflow.get("name", ""),
                owner_id=owner_id, status="failed",
                duration_seconds=duration,
                total_steps=len(steps), failed_step=0,
                error_message=str(e)[:1000],
            )
        except Exception:
            pass
    finally:
        with _WF_CANCEL_LOCK:
            _WF_CANCEL_EVENTS.pop(wf_id, None)
        try:
            from backend.services.agent_service.workflows_db import WorkflowsDB
            WorkflowsDB().mark_workflow_run(wf_id, datetime.datetime.now().isoformat())
        except Exception:
            pass


def _push_workflow_result(owner_id: str, workflow_name: str, results: dict):
    """cron 执行成功后推送结果通知。"""
    try:
        from backend.services.platform_service.notifier import send_alert
        send_alert(
            owner_id=owner_id,
            keyword=workflow_name,
            platform="workflow",
            risk_level=2,
            risk_class="medium",
            core_issue=f"定时任务「{workflow_name}」执行完成",
            report=f"本次执行结果摘要：{len(results)} 个步骤完成",
            urls=[],
            post_count=1,
        )
    except Exception as e:
        logger.warning(f"[Workflow] 推送结果失败: {e}")
