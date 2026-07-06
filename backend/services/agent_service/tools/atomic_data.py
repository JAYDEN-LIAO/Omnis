"""
原子工具层（H 组，共 12 个工具 + 2 个管理工具预留）

来自 pipeline 五阶段拆解。
所有工具带 @tool 装饰 + @with_owner 强制注入 owner_id。
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from backend.core.logger import get_logger

from ._base import ToolResult, tool
from ._owner import with_owner

logger = get_logger("agent.tools.atomic")

# H1-H3: search_posts / filter_content / cluster_related
# H1. search_posts — 跨平台按需搜索
# ───────────────────────────────────────────────────────────────
@tool(
    name="search_posts",
    description=(
        "按关键词+平台搜索帖子。返回原始帖子列表供后续处理。"
        "用户问'帮我看看最近小米/华为的动态'、'扫一下舆情'时调用。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "搜索关键词"},
            "platforms": {
                "type": "array", "items": {"type": "string"},
                "default": ["wb", "xhs"],
                "description": "限定平台，可选 wb/xhs/dy/bili/zhihu",
            },
            "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
        },
        "required": ["keyword"],
    },
    group="atomic",
)
@with_owner
async def search_posts_tool(
    keyword: str, _owner_id: str,
    platforms: Optional[list] = None, limit: int = 20,
) -> str:
    """按关键词+平台搜索帖子，启动爬虫子进程从各平台采集。"""
    logger.info(f"[search_posts] 开始搜索: keyword={keyword}, platforms={platforms}, limit={limit}, owner={_owner_id[:8]}")
    if not keyword.strip():
        return ToolResult(success=False, error="关键词不能为空", error_type="validation").to_json()
    plats = platforms or ["wb", "xhs"]

    # 确保爬虫数据库存在
    db_path = _ensure_crawler_db()
    logger.info(f"[search_posts] DB 路径: {db_path}")
    # 清空相关平台的旧数据，确保只等待本次爬虫的新结果
    _clear_crawler_data(plats)
    if not db_path:
        cached = _read_cached_posts(keyword, plats, limit)
        return ToolResult(
            success=True, data=cached,
            ui={"type": "post_list", "data": cached},
        ).to_json()

    try:
        from backend.services.agent_service.crawler_adapter import quick_crawl_stream
        from backend.core.config import settings

        cookie = settings.WEIBO_COOKIE
        # cookie 仅对微博平台生效，其他平台不使用
        if "wb" in plats:
            if not cookie:
                cookie_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "weibo_cookie.txt")
                if os.path.isfile(cookie_path):
                    try:
                        with open(cookie_path, "r", encoding="utf-8") as f:
                            cookie = f.read().strip()
                    except Exception:
                        pass
            if cookie:
                logger.info(f"[search_posts] 使用 cookie 登录")
        else:
            cookie = ""

        collected = []
        seen_urls: set = set()
        TIMEOUT = 180

        async def _collect():
            """在独立协程中收集结果，支持 asyncio.wait_for 超时取消。"""
            c = []
            s: set = set()
            async for chunk in quick_crawl_stream(
                query=keyword, platforms=plats, max_per_platform=min(limit, 10), cookie_str=cookie,
            ):
                if chunk["type"] == "item":
                    item = chunk["item"]
                    url = item.get("url", "") or item.get("post_id", "")
                    if url and url not in s:
                        s.add(url)
                        c.append({
                            "title": item.get("title", ""),
                            "content": item.get("content", ""),
                            "platform": item.get("platform", ""),
                            "url": url,
                            "time": "",
                        })
                        if len(c) >= limit:
                            break
            return c

        try:
            collected = await asyncio.wait_for(_collect(), timeout=TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"[search_posts] 爬虫超时 ({TIMEOUT}s)，返回已收集的结果")
        except Exception as e:
            logger.warning(f"[search_posts] 爬虫异常: {e}")

        logger.info(f"[search_posts] 收集到 {len(collected)} 条结果")
        if not collected:
            cached = _read_cached_posts(keyword, plats, limit)
            if cached:
                logger.info(f"[search_posts] 从缓存读到 {len(cached)} 条")
                return ToolResult(
                    success=True, data=cached,
                    ui={"type": "post_list", "data": cached},
                ).to_json()

        return ToolResult(
            success=True, data=collected[:limit],
            ui={"type": "post_list", "data": collected[:limit]},
        ).to_json()
    except Exception as e:
        logger.error(f"[search_posts] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


def _clear_crawler_data(platforms: list[str]) -> None:
    """清空指定平台在爬虫数据库中的旧数据，确保新爬虫的结果不被干扰。"""
    from backend.services.agent_service.crawler_adapter import PLATFORM_TABLE_MAP
    from backend.core.config import settings
    import sqlite3
    db_path = settings.CRAWLER_DB_PATH
    if not db_path or not os.path.isfile(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        for plat in platforms:
            table = PLATFORM_TABLE_MAP.get(plat)
            if table:
                # 先确保表存在（爬虫子进程会通过 --init_db 建表，但这里做兼容）
                conn.execute("BEGIN")
                try:
                    conn.execute(f"DELETE FROM {table}")
                except sqlite3.OperationalError:
                    conn.rollback()
                    continue
                conn.commit()
        conn.close()
        logger.info(f"[search_posts] 已清空 {platforms} 旧数据")
    except Exception as e:
        logger.warning(f"[search_posts] 清空旧数据失败: {e}")


def _ensure_crawler_db() -> str:
    """确保爬虫数据库文件存在，初始化所有爬虫所需表结构。返回 DB 路径。"""
    try:
        from backend.core.config import settings
        db_path = settings.CRAWLER_DB_PATH
        if not db_path:
            return ""
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        if not os.path.isfile(db_path):
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.close()
            logger.info(f"[search_posts] 已创建爬虫数据库: {db_path}")
        return db_path
    except Exception as e:
        logger.warning(f"[search_posts] 无法创建爬虫数据库: {e}")
        return ""


def _read_cached_posts(keyword: str, platforms: list[str], limit: int) -> list[dict]:
    """从已有爬虫数据库读取缓存数据，避免重复启动爬虫。"""
    try:
        from backend.services.agent_service.crawler_adapter import _read_latest_posts
        from backend.core.config import settings

        db_path = settings.CRAWLER_DB_PATH
        if not db_path or not os.path.exists(db_path):
            return []

        collected = []
        seen_urls: set = set()
        for plat in platforms:
            posts = _read_latest_posts(plat, keyword, max_count=limit)
            for p in posts:
                url = p.get("url", "") or p.get("post_id", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    collected.append({
                        "title": p.get("title", ""),
                        "content": p.get("content", ""),
                        "platform": p.get("platform", ""),
                        "url": url,
                        "time": "",
                    })
                    if len(collected) >= limit:
                        return collected
        return collected
    except Exception:
        return []


# ───────────────────────────────────────────────────────────────
# H2. filter_content — 按意图过滤帖子（ScreenerStage 封装）
# ───────────────────────────────────────────────────────────────
_INTENT_PROMPT_MAP = {}


def _lazy_init_intent_map():
    """惰性加载 Screener Prompt，避免循环导入。"""
    if _INTENT_PROMPT_MAP:
        return
    from backend.services.agent_service.tools.screener_prompts import (
        BRIEFING_SCREENER_PROMPT,
        CELEBRITY_SCREENER_PROMPT,
        GUIDE_SCREENER_PROMPT,
        SCREENER_PROMPT,
    )
    from backend.services.agent_service.schemas import (
        BriefingScreenerResult,
        CelebrityScreenerResult,
        GuideScreenerResult,
        ScreenerResult,
    )
    _INTENT_PROMPT_MAP.update({
        "risk": (SCREENER_PROMPT, ScreenerResult),
        "guide": (GUIDE_SCREENER_PROMPT, GuideScreenerResult),
        "celebrity": (CELEBRITY_SCREENER_PROMPT, CelebrityScreenerResult),
        "briefing": (BRIEFING_SCREENER_PROMPT, BriefingScreenerResult),
    })


@tool(
    name="filter_content",
    description=(
        "按意图过滤帖子。intent: risk/guide/celebrity/briefing 决定使用哪个 Screener Prompt。"
        "常作为 search_posts 的下一步调用。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "posts": {"type": "array", "description": "待过滤的帖子列表"},
            "intent": {
                "type": "string",
                "enum": ["risk", "guide", "celebrity", "briefing"],
                "description": "意图，决定使用哪个 Screener Prompt",
            },
        },
        "required": ["posts", "intent"],
    },
    group="atomic",
)
@with_owner
async def filter_content_tool(posts: list, intent: str, _owner_id: str) -> str:
    """按意图过滤帖子，返回过滤后的帖子 + Screener 判定字段。"""
    _lazy_init_intent_map()
    if intent not in _INTENT_PROMPT_MAP:
        return ToolResult(
            success=False, error=f"未知 intent: {intent}", error_type="validation",
        ).to_json()
    if not posts:
        return ToolResult(success=True, data=[]).to_json()
    prompt, pydantic_model = _INTENT_PROMPT_MAP[intent]
    try:
        from backend.services.agent_service.pipeline import ScreenerStage
        stage = ScreenerStage(
            keywords=[], keyword_levels={},
            prompt=prompt, pydantic_model=pydantic_model,
        )
        result = await stage.run_batch(posts, owner_id=_owner_id)
        return ToolResult(
            success=True,
            data=result,
            ui={"type": "filtered_list", "data": result},
        ).to_json()
    except Exception as e:
        logger.error(f"[filter_content] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


# ───────────────────────────────────────────────────────────────
# H3. cluster_related — 聚类
# ───────────────────────────────────────────────────────────────
@tool(
    name="cluster_related",
    description="对帖子列表进行话题聚类。常作为 filter_content 的下一步调用。",
    parameters={
        "type": "object",
        "properties": {
            "posts": {"type": "array", "description": "待聚类的帖子列表"},
            "min_cluster_size": {"type": "integer", "default": 2, "description": "最小聚类大小"},
        },
        "required": ["posts"],
    },
    group="atomic",
)
@with_owner
async def cluster_related_tool(posts: list, _owner_id: str, min_cluster_size: int = 2) -> str:
    """对帖子列表进行话题聚类，返回 [{topic_name, posts[], keyword}]。"""
    if not posts:
        return ToolResult(success=True, data=[]).to_json()
    try:
        from backend.services.agent_service.pipeline import ClusterStage
        stage = ClusterStage(min_cluster_size=min_cluster_size)
        result = await stage.run(posts, owner_id=_owner_id)
        return ToolResult(
            success=True,
            data=result,
            ui={"type": "cluster_result", "data": result},
        ).to_json()
    except Exception as e:
        logger.error(f"[cluster_related] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


