# backend/services/radar_service/api.py
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel
from backend.core.logger import get_logger
from backend.core.auth_deps import get_current_user, get_current_user_or_api_key, get_optional_user, require_admin, require_registered_user, can_view_all_data

logger = get_logger("radar.api")
from .db_manager import (
    get_latest_results, get_system_settings, save_system_settings,
    get_topic_summary_list, get_topic_summary_by_id, get_topic_posts,
    mark_topic_processed,
    get_volume_stats as _db_volume_stats,
    get_today_summary_data,
    get_today_topics,
    get_owner_by_rss_token,
)
from .main import api_start_task, radar_status, get_radar_status, reload_config
from typing import List, Optional, Dict, Any

router = APIRouter()

# ============================================================
# MCP Server 健康检查（Task 4.3）
# ============================================================

@router.get("/api/mcp/health")
def mcp_health_check(current_user: dict = Depends(get_current_user_or_api_key)):
    """
    MCP Server 健康检查端点（v2.2 Fix 6.7：需认证）
    用于外部服务（如 MCP Server）探测 radar_service 是否可用
    """
    from .main import radar_status as _global_status
    return {
        "status": "ok",
        "service": "radar_service",
        "radar_status": _global_status.status_text,
        "is_running": _global_status.is_running
    }


# ============================================================
# 熔断器状态端点（修复 #3.1）
# ============================================================

@router.get("/api/circuit/states")
def get_circuit_states(current_user: dict = Depends(require_admin)):
    """
    返回所有熔断器当前状态（v2.2：需认证）
    """
    from .llm_gateway import get_all_breakers
    breakers = get_all_breakers()
    breaker_dicts = [b.to_dict() for b in breakers]
    summary = {
        "total": len(breaker_dicts),
        "open": sum(1 for b in breaker_dicts if b["state"] == "open"),
        "half_open": sum(1 for b in breaker_dicts if b["state"] == "half_open"),
        "closed": sum(1 for b in breaker_dicts if b["state"] == "closed"),
    }
    return {"code": 200, "msg": "OK", "data": {"breakers": breaker_dicts, "summary": summary}}

@router.post("/api/start_task")
def start_task(background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user_or_api_key)):
    """WS4.6：扫描结果归属到当前用户（接受 JWT 或 API Key）"""
    if current_user.get("role") == "guest":
        return {"code": 403, "msg": "此功能需要注册账号"}
    success, msg = api_start_task(background_tasks, owner_id=current_user["id"])
    if success:
        return {"code": 200, "msg": msg}
    else:
        return {"code": 400, "msg": msg}


# ============================================================
# 定时调度器 API
# ============================================================

@router.post("/api/scheduler/start")
def start_scheduler(current_user: dict = Depends(require_registered_user)):
    from .scheduler import scheduler_start
    success, msg = scheduler_start()
    return {"code": 200, "msg": msg} if success else {"code": 400, "msg": msg}


@router.post("/api/scheduler/stop")
def stop_scheduler(current_user: dict = Depends(require_registered_user)):
    """停止定时调度器（v2.2：需认证）"""
    from .scheduler import scheduler_stop
    success, msg = scheduler_stop()
    return {"code": 200, "msg": msg}


@router.get("/api/scheduler/status")
def get_scheduler_status(current_user: dict = Depends(get_current_user)):
    """查询调度器状态（v2.2：需认证）"""
    from .scheduler import scheduler_status
    status = scheduler_status()
    return {"code": 200, "data": status}

@router.get("/api/radar_status")
def api_get_radar_status(current_user: dict = Depends(get_current_user_or_api_key)):
    """v2.2：支持 per-user 雷达状态（接受 JWT 或 API Key）"""
    from .main import get_radar_status as _get_radar_status
    owner_id = current_user["id"] if current_user else None
    status = _get_radar_status(owner_id)
    return {"code": 200, "data": status.get_status_dict()}

@router.get("/api/yq_list")
def get_yq_list(current_user: dict = Depends(get_current_user)):
    """v2.2：按 owner 过滤（需登录）"""
    can_view_all = can_view_all_data(current_user.get("role"))
    owner_id = current_user["id"] if current_user and not can_view_all else None
    db_results = get_latest_results(limit=50, owner_id=owner_id, is_admin=can_view_all)
    
    plat_name_map = {
        "wb": "微博",
        "xhs": "小红书",
        "bili": "B站",
        "zhihu": "知乎",
        "dy": "抖音",
        "ks": "快手",
        "tieba": "贴吧"
    }
    
    formatted_data = []
    for r in db_results:
        risk_level = str(r.get("risk_level", "")).lower()
        if "high" in risk_level or "高" in risk_level:
            sentiment, risk_text = "negative", "高风险"
        elif "low" in risk_level or "低" in risk_level:
            sentiment, risk_text = "positive", "低风险"
        else:
            sentiment, risk_text = "neutral", "中风险"
            
        raw_content = r.get("content")
        if not raw_content or str(raw_content).strip() == "":
            raw_content = r.get("title") or "暂无内容"
            
        display_report = raw_content if sentiment != "negative" else r.get("report", "")
        
        if len(display_report) > 80:
            display_report = display_report[:80] + "..."

        formatted_data.append({
            "id": r.get("post_id", ""),
            "platform": plat_name_map.get(r.get("platform", ""), str(r.get("platform", "")).upper()),
            "sentiment": sentiment,
            "risk": risk_text,
            "keyword": r.get("keyword", "未知"), 
            "core_issue": r.get("core_issue", "无异常"), 
            "report": display_report,          
            "url": r.get("url", ""),           
            "create_time": r.get("create_time") or r.get("publish_time", "")
        })
        
    return {
        "code": 200,
        "msg": "成功",
        "data": formatted_data
    }

class SettingsRequest(BaseModel):
    keywords: list
    inactive_keywords: list = []
    platforms: list
    push_summary: bool
    push_time: str
    alert_negative: bool
    monitor_frequency: float
    start_time: str = "08:00"

@router.get("/api/settings")
def api_get_settings(current_user: dict = Depends(require_registered_user)):
    data = get_system_settings(owner_id=current_user["id"])
    # 兼容旧数据：keywords 可能是 [{"text":"...", "level":"..."}]，转成 ["..."]
    if data and "keywords" in data and isinstance(data["keywords"], list):
        data["keywords"] = [
            k["text"] if isinstance(k, dict) else str(k)
            for k in data["keywords"]
        ]
    if data and "inactive_keywords" in data and isinstance(data["inactive_keywords"], list):
        data["inactive_keywords"] = [
            k["text"] if isinstance(k, dict) else str(k)
            for k in data["inactive_keywords"]
        ]
    return {"code": 200, "data": data}

@router.post("/api/settings")
def api_save_settings(req: SettingsRequest, current_user: dict = Depends(require_registered_user)):
    save_system_settings(req.model_dump(), owner_id=current_user["id"])
    reload_config()

    # 同步关键词到用户的订阅表，使 Agent 能通过 list_subscriptions 看到
    try:
        from backend.core.subscription_db import list_subscriptions as _list_subs, create_subscription as _create_sub
        existing = {s["name"] for s in _list_subs(current_user["id"])}
        for kw in req.keywords:
            kw_name = kw["text"] if isinstance(kw, dict) else str(kw)
            if kw_name not in existing:
                _create_sub(
                    owner_id=current_user["id"],
                    name=kw_name,
                    type="keyword",
                    platforms=list(req.platforms) if req.platforms else [],
                )
    except Exception as e:
        logger.warning(f"[Settings] 同步关键词到订阅失败（非致命）: {e}")

    try:
        from .scheduler import reschedule_if_running, reschedule_daily_summary_if_running
        reschedule_if_running(req.start_time, req.monitor_frequency)
        reschedule_daily_summary_if_running()
    except Exception:
        pass

    return {"code": 200, "msg": "系统设置已更新并生效"}


# ============================================================
# 话题聚合 API（Task 5）
# ============================================================

@router.get("/api/topic_list")
def get_topic_list(
    keyword: str = None,
    platform: str = None,
    sentiment: str = None,
    is_processed: int = None,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """
    获取话题聚合列表，替换原来的 /api/yq_list 单帖列表。

    WS4.6：无 token 视为 admin 看全部数据。
    """
    can_view_all = can_view_all_data(current_user.get("role"))
    owner_id = current_user["id"] if current_user and not can_view_all else None
    rows = get_topic_summary_list(
        keyword=keyword,
        platform=platform,
        sentiment=sentiment,
        is_processed=is_processed,
        limit=limit,
        owner_id=owner_id,
        is_admin=can_view_all,
    )

    # 平台英文标识 → 中文映射
    plat_name_map = {
        "wb": "微博", "xhs": "小红书", "bili": "B站",
        "zhihu": "知乎", "dy": "抖音", "ks": "快手", "tieba": "贴吧"
    }
    # sentiment 中文映射
    risk_class_map = {"negative": "负面", "positive": "正面", "neutral": "中性"}

    formatted = []
    for r in rows:
        risk_level = r.get("risk_level", 2)
        risk_class = r.get("risk_class", "neutral")
        alert_rec = r.get("alert_recommendation", "none")

        # 风险显示文本：以 AI 最终决策 alert_recommendation 为准
        if alert_rec == "high":
            risk_text = "高风险"
        elif alert_rec == "medium":
            risk_text = "中风险"
        elif alert_rec == "low":
            risk_text = "低风险"
        else:
            risk_text = "待观察"

        # 摘要截断
        summary = r.get("cluster_summary", "") or r.get("report", "") or ""
        if len(summary) > 80:
            summary = summary[:80] + "..."

        formatted.append({
            "topic_id": r.get("topic_id", ""),
            "keyword": r.get("keyword", ""),
            "topic_name": r.get("topic_name", ""),
            "cluster_summary": summary,
            "risk_level": risk_level,
            "risk_class": risk_class,
            "alert_recommendation": alert_rec,
            "risk_text": risk_text,
            "core_issue": r.get("core_issue", "无异常"),
            "sentiment": risk_class_map.get(risk_class, "中性"),
            "platforms": r.get("platforms", []),
            "post_count": r.get("post_count", 0),
            "first_seen": r.get("first_seen", "") or "",
            "last_seen": r.get("last_seen", "") or "",
            "scan_count": r.get("scan_count", 1),
            "is_processed": r.get("is_processed", 0),
            "evolution_signal": r.get("evolution_signal", "unknown"),
        })

    return {"code": 200, "msg": "成功", "data": formatted}


@router.get("/api/topic/{topic_id}")
def get_topic_detail(topic_id: str, current_user: dict = Depends(get_current_user)):
    """
    获取话题详情（含关联帖子列表 + 演化时间线）。
    WS4.6：无 token 视为 admin 看全部
    """
    can_view_all = can_view_all_data(current_user.get("role"))
    owner_id = current_user["id"] if current_user and not can_view_all else None
    # 话题聚合信息
    summary = get_topic_summary_by_id(topic_id, owner_id=owner_id, is_admin=can_view_all)
    if not summary:
        return {"code": 404, "msg": "话题不存在"}

    # 关联帖子列表
    posts = get_topic_posts(topic_id, owner_id=owner_id, is_admin=can_view_all)

    # 平台映射
    plat_name_map = {
        "wb": "微博", "xhs": "小红书", "bili": "B站",
        "zhihu": "知乎", "dy": "抖音", "ks": "快手", "tieba": "贴吧"
    }
    risk_class_map = {"negative": "负面", "positive": "正面", "neutral": "中性"}

    # 格式化帖子
    formatted_posts = []
    for p in posts:
        risk_level_str = str(p.get("risk_level", "")).lower()
        if "high" in risk_level_str or "高" in risk_level_str:
            sent, risk_t = "negative", "高风险"
        elif "low" in risk_level_str or "低" in risk_level_str:
            sent, risk_t = "positive", "低风险"
        else:
            sent, risk_t = "neutral", "中风险"

        # 时间处理：publish_time 为空或"未知时间"时用 create_time 兜底
        raw_publish_time = p.get("publish_time", "")
        fallback_time = p.get("create_time", "") or raw_publish_time
        display_time = fallback_time if raw_publish_time and raw_publish_time not in ("未知时间", "") else fallback_time

        formatted_posts.append({
            "post_id": p.get("post_id", ""),
            "platform": p.get("platform", ""),
            "platform_name": plat_name_map.get(p.get("platform", ""), p.get("platform", "")),
            "title": p.get("title", ""),
            "content": p.get("content", ""),
            "url": p.get("url", ""),
            "publish_time": display_time,
            "create_time": p.get("create_time", ""),
            "risk_level": p.get("risk_level", ""),
            "core_issue": p.get("core_issue", "无异常"),
            "report": p.get("report", ""),
            "sentiment": sent,
            "risk_text": risk_t,
        })

    # 演化时间线（从 topic_tracker 获取）
    evolution_timeline = []
    try:
        from .topic_tracker import get_topic_history
        ev_data = get_topic_history(topic_id=topic_id, keyword=summary.get("keyword", ""))
        if ev_data and ev_data.get("evolution"):
            evolution_timeline = ev_data["evolution"].get("timeline", [])
    except Exception as e:
        logger.warning(f"[TopicDetail] 获取演化时间线失败: {e}")

    # 话题整体风险（以 AI 最终决策 alert_recommendation 为准）
    risk_level = summary.get("risk_level", 2)
    risk_class = summary.get("risk_class", "neutral")
    alert_rec = summary.get("alert_recommendation", "none")

    if alert_rec == "high":
        risk_text = "高风险"
    elif alert_rec == "medium":
        risk_text = "中风险"
    elif alert_rec == "low":
        risk_text = "低风险"
    else:
        risk_text = "待观察"

    return {
        "code": 200,
        "data": {
            "topic_id": topic_id,
            "keyword": summary.get("keyword", ""),
            "topic_name": summary.get("topic_name", ""),
            "cluster_summary": summary.get("cluster_summary", "") or summary.get("report", ""),
            "report": summary.get("report", ""),
            "risk_level": risk_level,
            "risk_class": risk_class,
            "alert_recommendation": alert_rec,
            "risk_text": risk_text,
            "core_issue": summary.get("core_issue", "无异常"),
            "sentiment": risk_class_map.get(risk_class, "中性"),
            "platforms": summary.get("platforms", []),
            "post_count": summary.get("post_count", 0),
            "first_seen": summary.get("first_seen", ""),
            "last_seen": summary.get("last_seen", ""),
            "scan_count": summary.get("scan_count", 1),
            "is_processed": summary.get("is_processed", 0),
            "evolution_signal": summary.get("evolution_signal", "unknown"),
            "evolution_timeline": evolution_timeline,
            "posts": formatted_posts,
        }
    }


@router.post("/api/topic/{topic_id}/process")
def api_mark_topic_processed(topic_id: str, current_user: dict = Depends(require_registered_user)):
    """WS4.6：标记话题为已处理（仅本人或 admin）"""
    is_admin = current_user.get("role") == "admin"
    # 先校验权限
    summary = get_topic_summary_by_id(topic_id, owner_id=current_user["id"], is_admin=is_admin)
    if not summary:
        return {"code": 404, "msg": "话题不存在或无权访问"}
    success = mark_topic_processed(topic_id, owner_id=current_user["id"])
    if success:
        return {"code": 200, "msg": "话题已标记处理"}
    return {"code": 404, "msg": "话题不存在"}


# ============================================================
# Phase 6: 话题演化追踪 API
# ============================================================

@router.get("/api/topic_evolution")
def get_topic_evolution(keyword: str, topic_id: str = "", current_user: dict = Depends(get_current_user)):
    """
    前端详情页调用此接口，获取指定话题的完整演化时间线。

    参数：
        keyword: 监控关键词（必填）
        topic_id: 话题唯一标识（可选，不传则按 keyword 检索最新话题）

    返回：
        {
            "is_new_topic": bool,
            "topic_id": str,
            "topic_name": str,
            "keyword": str,
            "evolution": {
                "total_scan_count": int,
                "total_post_count": int,
                "duration_days": int,
                "risk_evolution_path": str,   # "2 → 3 → 4"
                "current_risk_level": int,
                "evolution_signal": str,       # "escalating" / "stable" / "deescalating" / "unknown"
                "timeline": [...],
            }
        }
    """
    from .topic_tracker import get_topic_history

    if not keyword:
        return {"code": 400, "msg": "keyword 参数必填"}

    can_view_all = can_view_all_data(current_user.get("role"))
    owner_id = current_user["id"] if not can_view_all else ""
    result = get_topic_history(topic_id=topic_id, keyword=keyword, owner_id=owner_id, is_admin=can_view_all)
    return {"code": 200, "data": result}


@router.post("/api/topic_evolution/migrate_clusters")
def migrate_topic_clusters(limit: int = 1000, current_user: dict = Depends(require_admin)):
    """
    将 ai_results 表中的历史数据，按 keyword 聚合后，
    批量生成 cluster_summary 并写入 topic_evolution 集合。

    用于初始化时一次性执行，或数据修复。

    参数：
        limit: 最多迁移多少条 ai_results（默认 1000）

    返回：
        {"migrated_topics": int, "total": int}
    """
    from .topic_tracker import migrate_topics_from_ai_results

    migrated, total = migrate_topics_from_ai_results(limit=limit)
    return {
        "code": 200,
        "msg": f"迁移完成，共处理 {total} 个话题簇，写入成功 {migrated} 个",
        "data": {"migrated_topics": migrated, "total": total},
    }


@router.get("/api/topic_stats")
def get_topic_stats(keyword: str = "", current_user: dict = Depends(get_current_user)):
    """
    获取话题演化库的统计信息（可选，用于管理后台）。

    参数：
        keyword: 可选，按关键词过滤

    返回：
        {
            "total_topics": int,
            "escalating_count": int,   # 风险升级中的话题数
            "new_topics_7d": int,      # 近7天新增话题数
        }
    """
    from .vector_store import get_topic_collection_info

    try:
        info = get_topic_collection_info()
        # qdrant CollectionInfo 对象属性：vectors_count 才是正确字段名
        vectors_count = info.vectors_count if hasattr(info, 'vectors_count') and info.vectors_count is not None else 0
        return {
            "code": 200,
            "data": {
                "total_topics": vectors_count,
                "keyword": keyword or "全部",
            }
        }
    except Exception as e:
        return {"code": 500, "msg": f"获取统计失败: {str(e)}"}


# ============================================================
# 首页统计 API
# ============================================================

@router.get("/api/volume_stats")
def get_volume_stats(keyword: str = "", current_user: dict = Depends(get_current_user)):
    """
    获取近7日每日声量数据（用于首页趋势图）。
    WS4.6：无 token 视为 admin 看全部

    参数：
        keyword: 可选，按关键词过滤

    返回：
        {
            "days": ["03-27", ...],
            "volumes": [12, ...],
            "negative_volumes": [2, ...],
            "total": int,
            "negative_total": int,
        }
    """
    import datetime

    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=6)
    can_view_all = can_view_all_data(current_user.get("role"))
    owner_id = current_user["id"] if current_user and not can_view_all else None

    result = _db_volume_stats(owner_id=owner_id, is_admin=can_view_all, keyword=keyword)
    daily_rows = result["daily_rows"]
    keyword_rows = result["keyword_rows"]

    # 补全7天数据（无数据的日期填0）
    row_map = {r["day"]: r for r in daily_rows}
    days, volumes, neg_vols = [], [], []
    cur = week_ago
    while cur <= today:
        day_str = cur.strftime("%m-%d")
        r = row_map.get(cur.isoformat())
        days.append(day_str)
        volumes.append(r["total_count"] if r else 0)
        neg_vols.append(r["neg_count"] if r else 0)
        cur += datetime.timedelta(days=1)

    # 按关键词拆分声量（取 Top 5 关键词，前端多线图用）
    keywords_volumes = {}
    try:
        # 聚合成 {keyword: {day_iso: count}}
        kw_map: dict[str, dict[str, int]] = {}
        for r in keyword_rows:
            kw_map.setdefault(r["keyword"], {})[r["day"]] = r["cnt"]

        # 取总量前 5 的关键词
        top_kws = sorted(kw_map.items(), key=lambda x: sum(x[1].values()), reverse=True)[:5]
        for kw, day_counts in top_kws:
            keywords_volumes[kw] = [
                day_counts.get(cur.isoformat(), 0)
                for cur in (week_ago + datetime.timedelta(days=i) for i in range(7))
            ]
    except Exception:
        pass

    return {
        "code": 200,
        "data": {
            "days": days,
            "volumes": volumes,
            "negative_volumes": neg_vols,
            "keywords_volumes": keywords_volumes,
            "total": sum(volumes),
            "negative_total": sum(neg_vols),
        }
    }


@router.get("/api/today_summary")
def get_today_summary(current_user: dict = Depends(get_current_user)):
    """
    获取今日舆情 AI 摘要。
    WS4.6：无 token 视为 admin 看全部

    返回：
        {
            "keyword": str,
            "sentiment": str,         # "中性偏负面" 等
            "summary": str,           # AI 生成的一句话摘要
            "high_risk_count": int,
            "hottest_topic": str,
            "escalating_topics": [str, ...],
        }
    """
    can_view_all = can_view_all_data(current_user.get("role"))
    user_id = current_user["id"] if current_user else None

    # 从 db 层获取今日聚合数据
    summary_data = get_today_summary_data(owner_id=user_id, is_admin=can_view_all)
    today_data = summary_data["today_data"]
    risk_distribution = summary_data["risk_distribution"]

    topics = get_today_topics(owner_id=user_id, is_admin=can_view_all, limit=5)

    # 高风险数量（risk_level 包含 high/高 或 sentiment=negative）
    high_risk = [r for r in today_data if "high" in str(r.get("risk_level", "")).lower() or "高" in str(r.get("risk_level", ""))]
    high_risk_count = len(high_risk)

    # 统计正负面
    pos = sum(1 for r in today_data if r.get("sentiment", "").lower() == "positive")
    neg = sum(1 for r in today_data if r.get("sentiment", "").lower() == "negative")
    neu = len(today_data) - pos - neg

    # 情感判断
    if neg > pos and neg > neu:
        sentiment_text = "中性偏负面"
    elif pos > neg and pos > neu:
        sentiment_text = "中性偏正面"
    else:
        sentiment_text = "中性态势"

    # 取监控关键词（从当前用户设置）
    settings = get_system_settings(owner_id=current_user["id"])
    raw = (settings.get("keywords") or [""])[0] if settings else ""
    keyword = raw.get("text", str(raw)) if isinstance(raw, dict) else str(raw)

    # 最热话题（post_count 最高）
    hottest = max(topics, key=lambda x: x.get("post_count", 0)) if topics else {}
    hottest_topic = hottest.get("topic_name", "") if hottest else ""

    # 风险升级话题（risk_class = negative）
    escalating = [t["topic_name"] for t in topics if t.get("risk_class") == "negative"][:3]

    # AI 生成摘要（从今日数据拼摘要，调用 LLM）
    summary = ""
    if today_data:
        sample = today_data[:5]
        content_parts = []
        for r in sample:
            title = r.get("title", "") or ""
            content = (r.get("content") or "")[:100]
            if title:
                content_parts.append(f"标题：{title}\\n内容：{content}")
        posts_text = "\\n---\\n".join(content_parts)
        try:
            from .topic_tracker import _call_topic_summary_llm
            summary = _call_topic_summary_llm(keyword or "舆情", posts_text, len(sample))
        except Exception as e:
            logger.warning(f"[TodaySummary] LLM 生成摘要失败: {e}")

    if not summary:
        summary = f"今日共捕获相关讨论 {len(today_data)} 条，其中高风险 {high_risk_count} 条。"

    # v2.2 被压住的推送数量
    try:
        from .db_manager import get_today_suppressed_count
        suppressed_count = get_today_suppressed_count(owner_id=user_id, is_admin=can_view_all)
    except Exception:
        suppressed_count = 0

    return {
        "code": 200,
        "data": {
            "keyword": keyword,
            "sentiment": sentiment_text,
            "summary": summary,
            "high_risk_count": high_risk_count,
            "hottest_topic": hottest_topic,
            "escalating_topics": escalating,
            "risk_distribution": risk_distribution,
            "suppressed_count": suppressed_count,
        }
    }


# ============================================================
# 推送配置 API（Phase 4）
# ============================================================

from pydantic import BaseModel, Field
from .notifier.models import PushChannel, EmailConfig, WeComConfig, FeishuConfig


class PushConfigUpdateRequest(BaseModel):
    """推送配置更新请求"""
    enabled: bool = False
    risk_min_level: int = Field(ge=1, le=5, default=2)
    # Email 专用
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    from_addr: str = ""
    to_addrs: list[str] = Field(default_factory=list)
    # Webhook 专用
    webhook_url: str = ""


class PushTestRequest(BaseModel):
    channel: str  # email | wecom | feishu


@router.get("/api/push/configs")
def get_all_push_configs(current_user: dict = Depends(require_registered_user)):
    """
    获取当前用户的所有推送通道的简洁配置（不含密码，v2.2 per-owner）
    """
    from .db_manager import get_all_push_configs as _db_get_all
    configs = _db_get_all(owner_id=current_user["id"])
    # 隐藏密码
    for ch in configs.values():
        ch.pop("smtp_password", None)
    return {"code": 200, "data": configs}


@router.get("/api/push/config/{channel}")
def get_push_config(channel: str, current_user: dict = Depends(require_registered_user)):
    """获取当前用户指定通道的完整配置（含密码）"""
    valid = [c.value for c in PushChannel]
    if channel not in valid:
        return {"code": 400, "msg": f"无效通道，支持: {valid}"}
    from .db_manager import get_push_config as _db_get
    cfg = _db_get(current_user["id"], channel)
    # 隐藏密码返回
    safe_cfg = dict(cfg)
    safe_cfg.pop("smtp_password", None)
    return {"code": 200, "data": safe_cfg}


@router.post("/api/push/config/{channel}")
def save_push_config(channel: str, req: PushConfigUpdateRequest, current_user: dict = Depends(require_registered_user)):
    """保存当前用户的指定通道配置（v2.2 per-owner）"""
    valid = [c.value for c in PushChannel]
    if channel not in valid:
        return {"code": 400, "msg": f"无效通道，支持: {valid}"}
    from .db_manager import save_push_config as _db_save
    from .notifier import reload_registry

    # 根据通道类型构建完整配置
    cfg = {
        "enabled": req.enabled,
        "risk_min_level": req.risk_min_level,
    }
    if channel == "email":
        cfg.update({
            "smtp_host": req.smtp_host,
            "smtp_port": req.smtp_port,
            "smtp_user": req.smtp_user,
            "smtp_password": req.smtp_password,
            "smtp_use_tls": req.smtp_use_tls,
            "from_addr": req.from_addr,
            "to_addrs": req.to_addrs,
        })
    elif channel == "rss":
        cfg["access_token"] = req.webhook_url or ""
    else:
        cfg["webhook_url"] = req.webhook_url

    _db_save(current_user["id"], channel, cfg)
    reload_registry(owner_id=current_user["id"])
    return {"code": 200, "msg": f"{channel} 配置已保存"}


@router.post("/api/push/test")
def test_push_channel(req: PushTestRequest, current_user: dict = Depends(require_registered_user)):
    """发送测试消息到当前用户指定的通道"""
    from .notifier import test_channel
    from .db_manager import get_push_config as _db_get

    try:
        ch = PushChannel(req.channel)
    except ValueError:
        return {"code": 400, "msg": f"无效通道: {req.channel}"}

    cfg = _db_get(current_user["id"], req.channel)
    if not cfg.get("enabled"):
        return {"code": 400, "msg": "请先启用该通道再测试"}

    ok = test_channel(ch, cfg)
    if ok:
        return {"code": 200, "msg": f"测试消息发送成功"}
    else:
        return {"code": 500, "msg": "发送失败，请检查配置是否正确"}


# ============================================================
# 大模型 API 配置 API
# ============================================================

from pydantic import BaseModel


class LLMConfigUpdateRequest(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""


LLM_AGENTS = {
    "default":   {"label": "默认模型",  "role": "所有未单独配置的 AI 能力兜底",  "default_model": "deepseek-chat"},
    "assistant": {"label": "AI 助手",  "role": "Agent 对话、规划与工具编排",   "default_model": "deepseek-chat"},
    "embedding": {"label": "嵌入模型",  "role": "文本向量聚类与语义检索",        "default_model": "BAAI/bge-m3"},
    "vision":    {"label": "视觉模型",  "role": "图片分析与 OCR 识别",          "default_model": "qwen-vl-max"},
}


@router.get("/api/llm/configs")
def get_llm_configs(current_user: dict = Depends(require_registered_user)):
    """获取当前用户所有 LLM Agent 的配置（v2.2 per-user）。
    user 未配置的角色回退到系统默认（admin 在 .env / settings 设的 DEFAULT_*）。"""
    from backend.core.model_config_db import get_model_config, get_effective_config

    owner_id = current_user["id"]
    result = {}
    for agent, info in LLM_AGENTS.items():
        role_upper = agent.upper()
        user_cfg = get_model_config(owner_id, role_upper) or {}
        eff = get_effective_config(owner_id, role_upper)

        # 脱敏显示实际生效的 API 密钥（系统默认或用户自定义）
        effective_api_key = eff.get("api_key", "") or ""
        api_key_masked = (
            "****" + effective_api_key[-4:] if effective_api_key and len(effective_api_key) >= 4
            else ("***" if effective_api_key else "")
        )

        result[agent] = {
            "label": info["label"],
            "role": info["role"],
            "default_model": info["default_model"],
            "api_key_masked": api_key_masked,
            "has_key": bool(effective_api_key),
            "base_url": user_cfg.get("base_url", ""),
            "model": user_cfg.get("model", ""),
            "effective_base_url": eff.get("base_url", ""),
            "effective_model": eff.get("model", ""),
            "uses_default": not bool(user_cfg.get("model")),
        }
    return {"code": 200, "data": result}


@router.post("/api/llm/config/{agent}")
def update_llm_config(agent: str, req: LLMConfigUpdateRequest, current_user: dict = Depends(require_registered_user)):
    """更新当前用户指定 Agent 的 LLM 配置（v2.2 per-user，不影响他人）。"""
    from backend.core.model_config_db import upsert_model_config

    if agent not in LLM_AGENTS:
        return {"code": 400, "msg": f"无效 Agent：{agent}，支持: {list(LLM_AGENTS.keys())}"}

    role_upper = agent.upper()
    # 仅传入非空字段；api_key=None 让 upsert 保留旧值
    kwargs = {}
    if req.base_url:
        kwargs["base_url"] = req.base_url
    if req.model:
        kwargs["model"] = req.model
    # api_key 显式为空串时表示清空；非空时更新；不传留旧
    if req.api_key:
        kwargs["api_key"] = req.api_key

    if not kwargs:
        return {"code": 400, "msg": "没有要更新的字段"}

    try:
        upsert_model_config(
            owner_id=current_user["id"],
            agent_role=role_upper,
            **kwargs,
        )
    except ValueError as e:
        return {"code": 400, "msg": str(e)}
    except Exception as e:
        logger.error(f"[LLMConfig] upsert failed: {e}")
        return {"code": 500, "msg": "更新失败"}

    return {"code": 200, "msg": f"{LLM_AGENTS[agent]['label']} 配置已保存"}


@router.post("/api/llm/test/{agent}")
def test_llm_config(
    agent: str,
    req: LLMConfigUpdateRequest = None,
    current_user: dict = Depends(require_registered_user),
):
    """测试当前用户指定 Agent 的 API 连通性。
    可选传入 api_key/base_url/model 覆盖当前配置测试。"""
    from backend.core.model_config_db import get_effective_config

    if agent not in LLM_AGENTS:
        return {"code": 400, "msg": f"无效 Agent：{agent}"}

    # 优先用请求中传入的新值测试，未传则从生效配置读取
    eff = get_effective_config(current_user["id"], agent.upper())
    api_key = (req.api_key.strip() if req and req.api_key else "") or eff.get("api_key") or ""
    base_url = (req.base_url.strip() if req and req.base_url else "") or eff.get("base_url") or ""
    model = (req.model.strip() if req and req.model else "") or eff.get("model") or ""

    if not api_key or not base_url:
        return {"code": 400, "msg": "API Key 或 Base URL 未配置"}

    base_url = base_url.rstrip("/")
    try:
        import requests
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        if agent == "embedding":
            # 向量引擎走 /embeddings 接口
            payload = {"model": model, "input": "test"}
            resp = requests.post(f"{base_url}/embeddings", headers=headers, json=payload, timeout=15)
        else:
            # 其他 Agent 走 /chat/completions
            payload = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}
            resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=15)

        if resp.status_code == 200:
            return {"code": 200, "msg": "连接成功"}
        else:
            return {"code": 500, "msg": f"接口返回错误: {resp.status_code} - {resp.text[:100]}"}
    except Exception as e:
        return {"code": 500, "msg": f"连接失败: {str(e)}"}


# ============================================================
# RSS 通道端点（v2.2）
# ============================================================

@router.get("/rss/{token}.xml")
def rss_feed(token: str, request: Request):
    """
    RSS 2.0 Feed 端点。

    根据 token 查找对应用户的推送配置，
    生成该用户订阅话题的 RSS XML。
    """
    # 查找 token 对应的 owner_id
    owner_id = get_owner_by_rss_token(token)

    if not owner_id:
        logger.warning(f"[RSS] 无效 token: {token[:10]}...")
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>无效订阅</title><description>RSS 链接无效或已过期，请重新从 MediaRadar 设置中获取。</description></channel></rss>',
            media_type="application/rss+xml; charset=utf-8",
        )

    from .notifier.channel_rss import generate_rss_xml

    base_url = str(request.base_url).rstrip("/")
    xml_content = generate_rss_xml(owner_id, token, base_url=base_url)

    return Response(
        content=xml_content,
        media_type="application/rss+xml; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )