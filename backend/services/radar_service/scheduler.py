# backend/services/radar_service/scheduler.py
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
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from backend.core.logger import get_logger
from backend.core.context import set_trace_id, generate_trace_id
import os

logger = get_logger("radar.scheduler")

# ---- 全局状态 ----
_scheduler: Optional[BackgroundScheduler] = None
_scan_lock: asyncio.Lock = asyncio.Lock()
_is_running: bool = False

# v2.2: per-user 最后扫描时间，用于决定本轮是否需要为某用户跑扫描
_user_last_scan_at: dict[str, datetime.datetime] = {}
_user_last_scan_lock: threading.Lock = threading.Lock()

# P6: 管线退化适配 — 旧路径(legacy) / 新路径(composite tools)
USE_COMPOSITE_TOOLS = os.getenv("USE_COMPOSITE_TOOLS", "0") == "1"


def _should_user_scan_now(owner_id: str, interval_min: float) -> bool:
    """根据 per-user 间隔判断是否该执行扫描。interval_min<=0 视为已暂停。"""
    if interval_min <= 0:
        return False
    with _user_last_scan_lock:
        last = _user_last_scan_at.get(owner_id)
    if last is None:
        return True  # 首次必跑
    delta_min = (datetime.datetime.now() - last).total_seconds() / 60.0
    return delta_min >= interval_min


def _mark_user_scanned(owner_id: str) -> None:
    with _user_last_scan_lock:
        _user_last_scan_at[owner_id] = datetime.datetime.now()


async def _run_extra_pipelines(owner_id: str, pipeline_types: list[str], keywords: list[str]):
    """P6: 根据 USE_COMPOSITE_TOOLS 开关走新/旧路径。"""
    if USE_COMPOSITE_TOOLS:
        await _run_extra_pipelines_composite(owner_id, pipeline_types, keywords)
    else:
        await _run_extra_pipelines_legacy(owner_id, pipeline_types, keywords)


async def _run_extra_pipelines_legacy(owner_id: str, pipeline_types, keywords):
    """旧路径：直接实例化 RadarPipeline（保留作为回退）"""
    from .pipeline_configs import PIPELINE_BUILDERS
    from .pipeline import PipelineConfig, RadarPipeline

    for pt in pipeline_types:
        builder = PIPELINE_BUILDERS.get(pt)
        if not builder:
            logger.warning(f"[Scheduler] 未知 pipeline_type={pt}，跳过")
            continue

        try:
            from .db import get_unprocessed_posts
            from backend.core.config import settings

            pipeline = builder(keywords[0] if keywords else "", [], owner_id)
            platform = pipeline.config.platform

            posts = get_unprocessed_posts(settings.CRAWLER_DB_PATH, platform)
            if posts:
                results = await pipeline.run(posts)
                logger.info(
                    f"[Scheduler] {pt} pipeline 完成: {len(results)} 条结果 (user={owner_id[:8]}...)"
                )
            else:
                logger.info(f"[Scheduler] {pt} pipeline: 无未处理数据")
        except Exception as e:
            logger.error(f"[Scheduler] {pt} pipeline 异常: {e}", exc_info=True)


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


def _get_scan_job_id() -> str:
    return "radar_scheduled_scan"


def _build_trigger(start_time: str, monitor_frequency: float):
    """
    构建 APScheduler trigger：
    - 每天在 start_time 执行第一次
    - 之后按 monitor_frequency 小时间隔重复
    """
    hour, minute = map(int, start_time.split(":"))
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    start_date = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if start_date <= now:
        start_date += datetime.timedelta(days=1)
    return IntervalTrigger(
        hours=monitor_frequency,
        start_date=start_date,
        timezone="Asia/Shanghai",
    )


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


def _run_scan():
    """
    定时扫描任务（v2.2 per-user 版本）。

    流程（v2.2 修订）：
      1. 收集所有活跃用户订阅
      2. 对每个用户读取 quota.scan_interval_min / scan_paused
      3. 若用户已暂停或距上次扫描未到间隔，跳过
      4. 否则为该用户跑 Pipeline（owner-scoped）
    """
    # Fix 7.7: 调度器在裸线程运行，ContextVar 不会传播，需手动设置 trace_id
    set_trace_id(generate_trace_id())
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if not _scan_lock.locked():
                async def _run():
                    async with _scan_lock:
                        logger.info("[Scheduler] 开始执行定时雷达扫描...")
                        try:
                            # 1. 收集所有活跃订阅
                            user_keywords = _collect_users_and_keywords()
                            if not user_keywords:
                                logger.info("[Scheduler] 无活跃订阅，跳过扫描")
                                return

                            # 2. 读取 per-user 扫描配置
                            from backend.core.quota_db import get_scan_config
                            from .main import job_async

                            ready_users: list[tuple[str, list[tuple[str, list[str], list[str]]]]] = []
                            skipped_paused = 0
                            skipped_interval = 0

                            for oid, sub_infos in user_keywords.items():
                                try:
                                    cfg = get_scan_config(oid)
                                except Exception as e:
                                    logger.warning(
                                        f"[Scheduler] 读取 user={oid[:8]}... scan config 失败: {e}"
                                    )
                                    cfg = {"interval_min": 60, "paused": False}
                                if cfg.get("paused"):
                                    skipped_paused += 1
                                    continue
                                interval_min = float(cfg.get("interval_min") or 60)
                                if not _should_user_scan_now(oid, interval_min):
                                    skipped_interval += 1
                                    continue
                                ready_users.append((oid, sub_infos))

                            logger.info(
                                f"[Scheduler] 候选用户 {len(user_keywords)} 个 → "
                                f"本轮触发 {len(ready_users)}，"
                                f"暂停 {skipped_paused}，未到间隔 {skipped_interval}"
                            )

                            if not ready_users:
                                return

                            # 3. 逐用户跑扫描
                            for oid, sub_info in ready_users:
                                # 收集所有唯一关键词
                                all_kws = list(set(kw for kw, _, _ in sub_info))
                                # 收集 pipeline_types
                                all_pts = set(pt for _, _, pts in sub_info for pt in pts)
                                logger.info(
                                    f"[Scheduler] 为用户 {oid[:8]}... 执行扫描"
                                    f"（{len(all_kws)} 关键词, {all_pts}）"
                                )
                                try:
                                    # 风险线：走原有完整流程（爬虫+分析）
                                    if "risk" in all_pts:
                                        await job_async(owner_id=oid)
                                    # 其他线：在已爬数据上运行不同 pipeline
                                    non_risk_pts = [pt for pt in all_pts if pt != "risk"]
                                    if non_risk_pts:
                                        await _run_extra_pipelines(oid, non_risk_pts, all_kws)
                                    _mark_user_scanned(oid)
                                except Exception as e:
                                    logger.error(
                                        f"[Scheduler] user={oid[:8]}... 扫描异常: {e}",
                                        exc_info=True,
                                    )

                            logger.info("[Scheduler] 定时雷达扫描完成")
                        except Exception as e:
                            logger.error(f"[Scheduler] 定时雷达扫描异常: {e}", exc_info=True)
                loop.run_until_complete(_run())
            else:
                logger.warning("[Scheduler] 扫描进行中，跳过本次触发")
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"[Scheduler] 扫描线程异常: {e}", exc_info=True)


def scheduler_start() -> tuple[bool, str]:
    """启动调度器，从数据库读取 start_time + monitor_frequency"""
    global _scheduler, _is_running

    if _is_running and _scheduler is not None:
        return True, "调度器已在运行中"

    try:
        from .db_manager import get_system_settings
        conf = get_system_settings()
    except Exception as e:
        logger.error(f"[Scheduler] 无法读取系统配置: {e}", exc_info=True)
        return False, f"读取配置失败: {e}"

    start_time = conf.get("start_time", "08:00")
    monitor_frequency = float(conf.get("monitor_frequency", 1.0))

    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    if monitor_frequency >= 0:
        trigger = _build_trigger(start_time, monitor_frequency)
        _scheduler.add_job(
            _run_scan,
            trigger=trigger,
            id=_get_scan_job_id(),
            replace_existing=True,
            misfire_grace_time=60,
        )
        freq_display = f"{monitor_frequency}h"
    else:
        freq_display = "已暂停"
        logger.info("[Scheduler] 扫描任务已暂停（频率为负值），仅运行每日简报")

    _scheduler.start()
    _is_running = True

    _schedule_daily_summary()
    _schedule_memory_cleanup()

    logger.info(f"[Scheduler] 调度器已启动: start_time={start_time}, frequency={freq_display}")
    if monitor_frequency >= 0:
        job = _scheduler.get_job(_get_scan_job_id())
        next_str = job.next_run_time.isoformat() if job and job.next_run_time else "未知"
        return True, f"调度器已启动，下次执行: {next_str}"
    else:
        return True, "调度器已启动，扫描任务已暂停（频率为负值），每日简报继续运行"


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
            "interval_hours": None,
            "start_time": None,
            "scan_in_progress": _scan_lock.locked(),
        }

    job = _scheduler.get_job(_get_scan_job_id())
    next_run_time = None
    if job and job.next_run_time:
        next_run_time = job.next_run_time.isoformat()

    # 活跃用户数
    user_count = len(_collect_users_and_keywords())

    try:
        from .db_manager import get_system_settings
        conf = get_system_settings()
        monitor_frequency = float(conf.get("monitor_frequency", 1.0))
        start_time = conf.get("start_time", "08:00")
    except Exception:
        monitor_frequency = None
        start_time = None

    return {
        "active": True,
        "next_run": next_run_time,
        "interval_hours": monitor_frequency,
        "start_time": start_time,
        "scan_in_progress": _scan_lock.locked(),
        "active_users": user_count,
    }


def reschedule_if_running(start_time: str, monitor_frequency: float) -> bool:
    """当系统配置变更时，重新调度已存在的任务。"""
    global _scheduler, _is_running

    if not _is_running or _scheduler is None:
        return False

    if monitor_frequency < 0:
        job = _scheduler.get_job(_get_scan_job_id())
        if job:
            _scheduler.remove_job(_get_scan_job_id())
            logger.info("[Scheduler] 扫描任务已暂停（频率为-1），每日简报继续运行")
        return True

    trigger = _build_trigger(start_time, monitor_frequency)
    job = _scheduler.get_job(_get_scan_job_id())

    if job:
        job.reschedule(trigger)
        logger.info(f"[Scheduler] 任务已重新调度: start_time={start_time}, frequency={monitor_frequency}h")
    else:
        _scheduler.add_job(
            _run_scan,
            trigger=trigger,
            id=_get_scan_job_id(),
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info(f"[Scheduler] 新任务已添加: start_time={start_time}, frequency={monitor_frequency}h")

    return True


# ---- 每日简报任务 ----

def _get_summary_job_id() -> str:
    return "daily_summary_job"


def _run_daily_summary():
    """每日简报任务（运行在线程中，per-user 分发）"""
    # Fix 7.7: ContextVar 不会传播到调度器线程，需手动设置
    set_trace_id(generate_trace_id())
    try:
        # v2.2: 收集所有活跃订阅用户，逐一为其生成 + 推送简报
        user_keywords = _collect_users_and_keywords()
        if not user_keywords:
            logger.info("[Scheduler] 无活跃订阅用户，跳过每日简报")
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _run():
                logger.info(
                    f"[Scheduler] 开始为 {len(user_keywords)} 个用户生成每日简报..."
                )
                from .db_manager import get_system_settings
                from .push_generator import generate_daily_summary_html
                from .notifier import send_alert

                for oid in user_keywords.keys():
                    try:
                        # 检查该用户是否开启了每日简报
                        user_conf = get_system_settings(owner_id=oid)
                        if not user_conf.get("push_summary", False):
                            logger.debug(
                                f"用户 {oid[:8]}... 每日简报未开启，跳过"
                            )
                            continue
                    except Exception:
                        continue
                    try:
                        html = await generate_daily_summary_html(owner_id=oid)
                        if not html:
                            logger.info(
                                f"[Scheduler] 用户 {oid[:8]}... 今日无新舆情，跳过"
                            )
                            continue
                        send_alert(
                            owner_id=oid,
                            keyword="舆情监测",
                            platform="全部平台",
                            risk_level=2,
                            risk_class="medium",
                            core_issue="每日舆情监测简报",
                            report="今日舆情概况已生成，请查收邮件。",
                            urls=[],
                            email_html=html,
                        )
                        logger.info(
                            f"[Scheduler] 用户 {oid[:8]}... 每日简报发送成功"
                        )
                    except Exception as e:
                        logger.error(
                            f"[Scheduler] 用户 {oid[:8]}... 每日简报异常: {e}",
                            exc_info=True,
                        )
            loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"[Scheduler] 每日简报线程异常: {e}", exc_info=True)


def _schedule_daily_summary():
    """注册每日简报任务（push_time 触发）"""
    global _scheduler
    if _scheduler is None:
        return

    try:
        from .db_manager import get_system_settings
        conf = get_system_settings()
    except Exception:
        return

    if not conf.get("push_summary", False):
        logger.info("[Scheduler] 每日简报未启用，不注册任务")
        return

    push_time = conf.get("push_time", "18:00")
    hour, minute = map(int, push_time.split(":"))

    old_job = _scheduler.get_job(_get_summary_job_id())
    if old_job:
        _scheduler.remove_job(_get_summary_job_id())

    trigger = CronTrigger(hour=hour, minute=minute, second=0, timezone="Asia/Shanghai")
    _scheduler.add_job(
        _run_daily_summary,
        trigger=trigger,
        id=_get_summary_job_id(),
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info(f"[Scheduler] 每日简报任务已注册: {push_time}")


def reschedule_daily_summary_if_running() -> bool:
    """当 push_summary / push_time 变更时，重新调度简报任务"""
    global _scheduler, _is_running
    if not _is_running or _scheduler is None:
        return False
    _schedule_daily_summary()
    return True


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
_WF_CANCEL_EVENTS: dict = {}
_WF_CANCEL_LOCK = threading.Lock()


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
        from backend.services.radar_service.notifier import send_alert
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
