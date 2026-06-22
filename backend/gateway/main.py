# backend/gateway/main.py

# ── Windows: 强制 ProactorEventLoop，否则子进程无法启动 ──
import asyncio as _asyncio_init
import sys as _sys_init
if _sys_init.platform == "win32":
    _asyncio_init.set_event_loop_policy(_asyncio_init.WindowsProactorEventLoopPolicy())
    # 强制 stdout 行缓冲，确保 uvicorn reload 子进程日志实时显示在终端
    try:
        _sys_init.stdout.reconfigure(line_buffering=True)
        _sys_init.stderr.reconfigure(line_buffering=True)
    except Exception:
        # stdout/stderr reconfigure 非关键路径，失败不影响功能
        pass

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import traceback
import sys
import os

# P4: 将项目根目录和 backend/ 目录加入 PYTHONPATH
# - project root → from backend.xxx 标准包导入
# - backend/ dir → 兼容遗留的 from core.xxx 导入
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_BACKEND_DIR = os.path.join(_PROJECT_ROOT, "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# 标准包导入
from backend.services.radar_service.api import router as radar_router
from backend.services.agent_service.api import router as agent_router
from backend.services.auth_service.api import router as auth_router  # WS4: 多用户认证
from backend.services.subscription_service.api import router as subscription_router  # v2.2: 订阅/模型/配额/admin
from backend.services.admin_service.api import router as admin_monitor_router  # Admin Agent 监控

# 触发 agent_service加载，确保其 Counter/Histogram 已注册到 prometheus 默认注册表
import backend.services.agent_service.agent_core  # noqa: F401
 
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from backend.core.config import settings
from backend.core.logger import get_logger
from backend.core.rate_limiter import add_rate_limiting_middleware
from backend.core.security_middleware import (
    add_security_headers_middleware,
    add_max_body_size_middleware,
)
# v2.2: 触发订阅表初始化
import backend.services.radar_service.db_manager  # noqa: F401  触发 init_radar_db
logger = get_logger("gateway")


# v2.2 P1#17：迁移 @app.on_event 到 lifespan 上下文管理器
# 原 @app.on_event("startup")/("shutdown") 已被 FastAPI 弃用
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期：启动调度器（P0#5 失败时升级日志 + 暴露 /health）+ 关闭时停止。"""
    # ── startup ──
    app.state.scheduler_healthy = False
    app.state.scheduler_start_msg = "未启动"
    try:
        from services.radar_service.scheduler import scheduler_start
        success, msg = scheduler_start()
        app.state.scheduler_healthy = bool(success)
        app.state.scheduler_start_msg = msg
        if success:
            logger.info(f"[Gateway] {msg}")
        else:
            # P0#5：启动返回 False 视为失败，升级到 error 级别
            logger.error(f"[Gateway] 调度器启动失败: {msg}")
    except Exception as e:
        # P0#5：原 logger.warning 升级为 logger.error，且标记状态
        logger.error(f"[Gateway] 调度器启动异常: {e}", exc_info=True)
        app.state.scheduler_start_msg = f"启动异常: {e}"
        app.state.scheduler_healthy = False

    # 用户工作流调度器（每分钟检查 cron 到期）
    try:
        from services.radar_service.scheduler import _run_user_workflows
        from apscheduler.triggers.interval import IntervalTrigger
        from services.radar_service.scheduler import _scheduler as _wf_sched
        from apscheduler.schedulers.background import BackgroundScheduler
        # 获取或创建调度器
        _user_wf_scheduler = _wf_sched or BackgroundScheduler(timezone="Asia/Shanghai")
        _user_wf_scheduler.add_job(
            _run_user_workflows,
            IntervalTrigger(minutes=1),
            id="user_workflows",
            name="用户自定义工作流",
            misfire_grace_time=30,
        )
        if _wf_sched is None:
            _user_wf_scheduler.start()
        logger.info("[Gateway] 用户工作流调度器已注册 (每分钟检查)")
    except Exception as e:
        logger.error(f"[Gateway] 用户工作流调度器注册失败: {e}", exc_info=True)

    # Agent Ops 调度器（智能运维引擎）
    try:
        from backend.services.admin_service.agent_ops import get_agent_ops
        ops_success, ops_msg = get_agent_ops().start()
        if ops_success:
            logger.info(f"[Gateway] {ops_msg}")
        else:
            logger.warning(f"[Gateway] Ops 调度器: {ops_msg}")
    except Exception as e:
        logger.error(f"[Gateway] Ops 调度器启动异常: {e}", exc_info=True)

    yield  # ── 应用运行中 ──

    # ── shutdown ──
    try:
        from services.radar_service.scheduler import scheduler_stop
        success, msg = scheduler_stop()
        if success:
            logger.info(f"[Gateway] {msg}")
        else:
            logger.error(f"[Gateway] 调度器关闭失败: {msg}")
    except Exception as e:
        logger.error(f"[Gateway] 调度器关闭异常: {e}", exc_info=True)

    # Agent Ops 调度器停止
    try:
        from backend.services.admin_service.agent_ops import get_agent_ops
        ops_success, ops_msg = get_agent_ops().stop()
        if ops_success:
            logger.info(f"[Gateway] {ops_msg}")
    except Exception as e:
        logger.error(f"[Gateway] Ops 调度器关闭异常: {e}", exc_info=True)

    # Fix 3.4: 关闭全局 HTTP 客户端，避免 TCP 连接泄漏
    try:
        from services.radar_service.llm_gateway import global_http_client
        global_http_client.close()
        logger.info("[Gateway] 全局 HTTP 客户端已关闭")
    except Exception:
        pass


app = FastAPI(
    title="MediaRadar 统一接口网关",
    version="2.0",
    description="基于微服务架构的全局 API 网关",
    lifespan=lifespan,
)

# 8.1 trace_id 中间件：每个请求生成/沿用 trace_id，注入 ContextVar，回写响应头
from backend.core.context import set_trace_id, generate_trace_id, clear_trace_id


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """
    每个 HTTP 请求注入 trace_id：
      - 入：读 X-Trace-Id；没有则生成 uuid4().hex
      - 中：set ContextVar，使下游所有日志自动带上 trace_id
      - 出：响应头回写 X-Trace-Id，便于前端 / 日志聚合关联
    """
    incoming = request.headers.get("X-Trace-Id", "").strip()
    trace_id = incoming if incoming else generate_trace_id()
    set_trace_id(trace_id)
    try:
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
    finally:
        clear_trace_id()

# 修复 #1.3：CORS 错配（* + credentials=True 违反 CORS 规范）
# 按 ENV 区分：
#   dev  环境：allow_origins=["*"]，credentials=False（便于本地联调）
#   prod 环境：allow_origins 来自 ALLOWED_ORIGINS，credentials=True（精确控制）
if settings.ENV == "prod":
    _origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    if not _origins:
        logger.warning("[Gateway] ENV=prod 但 ALLOWED_ORIGINS 为空，将回退到 *（不安全）")
        _origins = ["*"]
    _credentials = True
else:
    _origins = ["*"]
    _credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WS3: 安全加固中间件（按顺序：限流 → 安全头 → 请求体大小）
add_rate_limiting_middleware(app)
add_security_headers_middleware(app)
add_max_body_size_middleware(app)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc)
    logger.error(f"Global exception caught at {request.url}: {error_msg}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "系统内部处理异常", "data": None}
    )

# 挂载雷达业务子路由
# 注：为严格保持原有前端接口调用路径 (/api/...) 不变，此处暂不添加统一前缀
app.include_router(radar_router, tags=["舆情雷达业务层"])
app.include_router(agent_router, tags=["AI助手业务层"])
app.include_router(auth_router, tags=["WS4 用户认证"])
app.include_router(subscription_router, tags=["v2.2 订阅/模型/配额"])
app.include_router(admin_monitor_router, tags=["Admin Agent 监控"])


@app.get("/metrics", tags=["可观测性"])
async def metrics():
    """Prometheus 指标暴露端点（7.2）"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ===============================================================
# P0#5：Gateway 健康检查端点
# 用于外部探活 / 监控告警 / 部署平台 liveness probe
# 仅反映 scheduler 启动状态，详细信息见 /api/scheduler/status
# ===============================================================
@app.get("/health", tags=["可观测性"])
async def health_check():
    """
    Gateway 健康检查（v2.2 P2 Fix 10）：
      - scheduler: 调度器状态
      - database: SQLite 连通性 (SELECT 1)
      - qdrant: Qdrant 连通性 (get_collections)
      任一组件 unhealthy → 503
    """
    healthy = getattr(app.state, "scheduler_healthy", False)
    msg = getattr(app.state, "scheduler_start_msg", "未启动")

    checks = {
        "scheduler": "ok" if healthy else "failed",
    }
    if not healthy:
        checks["scheduler_msg"] = msg

    # DB 连通性检查
    try:
        import sqlite3
        from core.config import settings
        conn = sqlite3.connect(settings.STATE_DB_PATH, timeout=5.0)
        conn.execute("SELECT 1")
        conn.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = "failed"
        checks["database_msg"] = str(e)[:200]

    # Qdrant 连通性检查
    try:
        from core.qdrant_client import get_qdrant_client
        client = get_qdrant_client()
        client.get_collections()
        checks["qdrant"] = "ok"
    except Exception as e:
        checks["qdrant"] = "failed"
        checks["qdrant_msg"] = str(e)[:200]

    all_healthy = all(v == "ok" for v in checks.values() if isinstance(v, str))
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content=checks,
    )
if __name__ == "__main__":
    # ── v2.2 安全检查 ─────────────────────────────────────
    from core.config import settings
    import sys as _sys_check
    if not settings.JWT_SECRET or settings.JWT_SECRET in (
        "dev-secret-change-me-in-prod-please-32bytes", "your-secret-key", "changeme", ""):
        _sys_check.stderr.write(
            "\n" + "="*60 + "\n"
            "!!! 安全警告: JWT_SECRET 未设置或使用默认值 !!!\n"
            "上线前必须设置环境变量 JWT_SECRET=<强随机密钥>\n"
            "生成方式: python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            + "="*60 + "\n\n"
        )
    # ─────────────────────────────────────────────────────

    uvicorn.run("gateway.main:app", host="0.0.0.0", port=8008, reload=True)