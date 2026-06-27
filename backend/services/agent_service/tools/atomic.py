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

# ───────────────────────────────────────────────────────────────
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
        from backend.services.search_lib.crawler_adapter import quick_crawl_stream
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
    from backend.services.search_lib.crawler_adapter import PLATFORM_TABLE_MAP
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
        from backend.services.search_lib.crawler_adapter import _read_latest_posts
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
    from backend.services.radar_service.prompt_templates import (
        BRIEFING_SCREENER_PROMPT,
        CELEBRITY_SCREENER_PROMPT,
        GUIDE_SCREENER_PROMPT,
        SCREENER_PROMPT,
    )
    from backend.services.radar_service.schemas import (
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
        from backend.services.radar_service.pipeline import ScreenerStage
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
        from backend.services.radar_service.pipeline import ClusterStage
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


# ───────────────────────────────────────────────────────────────
# H4. extract_slots — 从聚类结果提取结构化槽位
# ───────────────────────────────────────────────────────────────
@tool(
    name="extract_slots",
    description="从聚类结果提取结构化信息槽位（时间/地点/花费等）。用于攻略/舆情分析场景。",
    parameters={
        "type": "object",
        "properties": {
            "clusters": {"type": "array", "description": "聚类结果列表"},
            "slot_type": {
                "type": "string",
                "enum": ["guide", "risk", "celebrity"],
                "default": "guide",
                "description": "槽位提取类型",
            },
        },
        "required": ["clusters"],
    },
    group="atomic",
)
@with_owner
def extract_slots_tool(clusters: list, _owner_id: str, slot_type: str = "guide") -> str:
    """从聚类结果提取结构化信息槽位。"""
    if not clusters:
        return ToolResult(success=True, data=[]).to_json()
    try:
        all_slots = []
        for cluster in clusters:
            posts = cluster.get("posts") or cluster.get("items", [])
            topic = cluster.get("topic_name") or cluster.get("topic", "")
            for post in posts:
                content = post.get("content") or post.get("text", "")
                slot = _extract_single_slot(content, topic, slot_type)
                if slot:
                    all_slots.append(slot)
        return ToolResult(
            success=True,
            data=all_slots,
            ui={"type": "slot_list", "data": all_slots},
        ).to_json()
    except Exception as e:
        logger.error(f"[extract_slots] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


def _extract_single_slot(content: str, topic: str, slot_type: str) -> Optional[dict]:
    """从单条内容提取槽位（规则版，后续可升级为 LLM 版）。"""
    if not content:
        return None
    content_lower = content.lower()
    slot = {
        "topic": topic,
        "time_slot": "全天",
        "location": "",
        "action": "参观",
        "description": content[:100],
        "rating": 3,
        "cost_min": 0,
        "cost_max": 0,
        "platform": "",
        "author_type": "素人",
        "confidence": 0.6,
    }
    # 简单规则提取时间槽
    time_keywords = {
        "上午": "上午", "早上": "上午", "早": "上午",
        "中午": "午餐", "午餐": "午餐",
        "下午": "下午",
        "晚上": "晚上", "晚饭": "晚上", "晚餐": "晚上",
        "夜": "晚上",
    }
    for kw, ts in time_keywords.items():
        if kw in content_lower:
            slot["time_slot"] = ts
            break
    # 提取地点（简单规则：含"在"、"去"后跟2-4字）
    import re
    loc_match = re.search(r'(?:在|去|到)([^\s，。,]{2,6}?(?:街|路|店|馆|园|山|湖|海|广场|大厦|中心|公园))', content)
    if loc_match:
        slot["location"] = loc_match.group(1)
    # 提取花费
    cost_match = re.search(r'(\d+)\s*[元块钱]', content)
    if cost_match:
        cost = int(cost_match.group(1))
        slot["cost_min"] = max(0, cost - cost // 4)
        slot["cost_max"] = cost + cost // 4
    return slot


# ───────────────────────────────────────────────────────────────
# H5. compare_opinions — 跨平台加权对比
# ───────────────────────────────────────────────────────────────

PLATFORM_WEIGHTS = {
    "xhs": 0.3, "zhihu": 0.4, "bili": 0.3, "wb": 0.2,
}


def _calc_weighted_score(opinion: dict) -> float:
    """按平台类型加权计算综合评分。"""
    total_weight = 0
    weighted_sum = 0
    platforms = opinion.get("platforms", {})
    avg_rating = opinion.get("avg_rating", 3.0)
    for platform, count in platforms.items():
        w = PLATFORM_WEIGHTS.get(platform, 0.25)
        total_weight += w * count
        weighted_sum += w * avg_rating * count
    return round(weighted_sum / total_weight, 2) if total_weight > 0 else 3.0


@tool(
    name="compare_opinions",
    description="跨平台加权对比观点。输入聚类/槽位数据，输出各平台对比分析。",
    parameters={
        "type": "object",
        "properties": {
            "slots": {"type": "array", "description": "槽位提取结果列表"},
            "min_support": {"type": "integer", "default": 2, "description": "最小支持数"},
        },
        "required": ["slots"],
    },
    group="atomic",
)
@with_owner
def compare_opinions_tool(slots: list, _owner_id: str, min_support: int = 2) -> str:
    """跨平台加权对比观点，输出带权重的分析结果。"""
    if not slots:
        return ToolResult(success=True, data=[]).to_json()
    try:
        # 按 location+action 聚合观点
        opinions: dict[str, dict] = {}
        for slot in slots:
            key = f"{slot.get('location', '')}:{slot.get('action', '')}"
            if key not in opinions:
                opinions[key] = {
                    "point": f"{slot.get('location', '')}的{slot.get('action', '')}体验",
                    "support_count": 0,
                    "oppose_count": 0,
                    "neutral_count": 0,
                    "platforms": {},
                    "avg_rating": 0,
                    "ratings_sum": 0,
                    "ratings_count": 0,
                }
            op = opinions[key]
            rating = slot.get("rating", 3)
            platform = slot.get("platform", "unknown")
            op["ratings_sum"] += rating
            op["ratings_count"] += 1
            op["platforms"][platform] = op["platforms"].get(platform, 0) + 1
            if rating >= 4:
                op["support_count"] += 1
            elif rating <= 2:
                op["oppose_count"] += 1
            else:
                op["neutral_count"] += 1

        result = []
        for key, op in opinions.items():
            if op["support_count"] + op["oppose_count"] + op["neutral_count"] < min_support:
                continue
            op["avg_rating"] = round(op["ratings_sum"] / max(op["ratings_count"], 1), 1)
            weighted = _calc_weighted_score(op)
            op["weighted_score"] = weighted
            if weighted >= 3.5:
                op["recommendation"] = "推荐"
            elif weighted <= 2.5:
                op["recommendation"] = "不推荐"
            else:
                op["recommendation"] = "谨慎"
            del op["ratings_sum"], op["ratings_count"], op["avg_rating"]
            result.append(op)

        return ToolResult(
            success=True,
            data=result,
            ui={"type": "opinion_comparison", "data": result},
        ).to_json()
    except Exception as e:
        logger.error(f"[compare_opinions] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


# ───────────────────────────────────────────────────────────────
# H6. generate_itinerary — 生成行程计划
# ───────────────────────────────────────────────────────────────
@tool(
    name="generate_itinerary",
    description="基于对比分析结果生成可执行行程计划。仅攻略场景使用。",
    parameters={
        "type": "object",
        "properties": {
            "opinions": {"type": "array", "description": "对比分析结果"},
            "slots": {"type": "array", "description": "原始槽位数据"},
            "keyword": {"type": "string", "default": "", "description": "关键词"},
        },
        "required": ["opinions", "slots"],
    },
    group="atomic",
)
@with_owner
def generate_itinerary_tool(
    opinions: list, slots: list, _owner_id: str, keyword: str = "",
) -> str:
    """基于对比分析结果生成可执行行程计划。"""
    try:
        days = _build_itinerary(slots)
        budget = _calc_budget(slots)
        tips = _gen_tips(opinions)
        source_summary: dict[str, int] = {}
        for s in slots:
            p = s.get("platform", "unknown")
            source_summary[p] = source_summary.get(p, 0) + 1

        result = {
            "keyword": keyword,
            "itinerary": days,
            "budget": budget,
            "tips": tips,
            "source_summary": source_summary,
        }
        return ToolResult(
            success=True,
            data=result,
            ui={"type": "itinerary", "data": result},
        ).to_json()
    except Exception as e:
        logger.error(f"[generate_itinerary] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


def _build_itinerary(slots: list[dict]) -> list[dict]:
    """按 time_slot 对齐为多日行程。"""
    from collections import defaultdict
    by_location: dict[str, list[dict]] = defaultdict(list)
    for s in slots:
        loc = s.get("location") or "默认地点"
        by_location[loc].append(s)

    days = []
    for loc, items in by_location.items():
        day = {
            "day": len(days) + 1,
            "theme": f"{loc}一日游",
            "spots": [],
        }
        for item in items:
            day["spots"].append({
                "time_slot": item.get("time_slot", "全天"),
                "action": item.get("action", "参观"),
                "location": item.get("location", loc),
                "description": item.get("description", "")[:80],
                "duration": "2小时",
                "cost": f"{item.get('cost_min', 0)}-{item.get('cost_max', 0)}元",
                "rating": item.get("rating", 3),
            })
        days.append(day)
    return days


def _calc_budget(slots: list[dict]) -> dict:
    """计算预算范围。"""
    costs = []
    for s in slots:
        if s.get("cost_max", 0) > 0:
            costs.append((s["cost_min"], s["cost_max"]))
    if not costs:
        return {"min": 0, "max": 0, "unit": "元", "note": "暂无数据"}
    total_min = sum(c[0] for c in costs)
    total_max = sum(c[1] for c in costs)
    return {
        "min": total_min,
        "max": total_max,
        "unit": "元",
        "note": f"基于 {len(costs)} 项来源估算",
    }


def _gen_tips(opinions: list[dict]) -> list[dict]:
    """生成实用贴士。"""
    tips = []
    for op in opinions:
        if op.get("recommendation") == "不推荐":
            tips.append({
                "type": "warning",
                "content": f"{op.get('point', '')}评价较低（{op.get('weighted_score', 0)}分），建议谨慎选择",
            })
        elif op.get("support_count", 0) >= 3:
            tips.append({
                "type": "positive",
                "content": f"{op.get('point', '')}广受好评（{op['support_count']}人推荐）",
            })
    return tips


# ───────────────────────────────────────────────────────────────
# H7. analyze_sentiment — 规则+LLM 混合情感判定
# ───────────────────────────────────────────────────────────────
@tool(
    name="analyze_sentiment",
    description="情感分析。先用规则词典判定（80%覆盖），模糊内容调用 LLM 补充。",
    parameters={
        "type": "object",
        "properties": {
            "texts": {"type": "array", "items": {"type": "string"}, "description": "待分析的文本列表"},
        },
        "required": ["texts"],
    },
    group="atomic",
)
@with_owner
def analyze_sentiment_tool(texts: list, _owner_id: str) -> str:
    """规则+LLM 混合情感判定。"""
    if not texts:
        return ToolResult(success=True, data=[]).to_json()
    try:
        from .sentiment_dict import classify_sentiment
        results = []
        need_llm = []

        for i, text in enumerate(texts):
            rule_result = classify_sentiment(text)
            if rule_result != "neutral":
                results.append({"index": i, "text": text[:100], "sentiment": rule_result, "method": "rule"})
            else:
                need_llm.append(i)

        # 模糊内容走 LLM 补充
        if need_llm:
            try:
                llm_results = _llm_sentiment_fallback([texts[i] for i in need_llm])
                for idx, sentiment in zip(need_llm, llm_results):
                    results.append({"index": idx, "text": texts[idx][:100], "sentiment": sentiment, "method": "llm"})
            except Exception as e:
                logger.warning(f"[analyze_sentiment] LLM 补充失败: {e}")
                for idx in need_llm:
                    results.append({"index": idx, "text": texts[idx][:100], "sentiment": "neutral", "method": "fallback"})

        # 汇总统计
        stats = {"positive": 0, "negative": 0, "neutral": 0}
        for r in results:
            s = r.get("sentiment", "neutral")
            stats[s] = stats.get(s, 0) + 1

        return ToolResult(
            success=True,
            data={"results": results, "stats": stats},
            ui={"type": "sentiment_analysis", "data": {"stats": stats}},
        ).to_json()
    except Exception as e:
        logger.error(f"[analyze_sentiment] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


def _llm_sentiment_fallback(texts: list[str]) -> list[str]:
    """LLM 补充情感判定。"""
    import json as _json
    from backend.core.config import settings, get_agent_config
    from openai import OpenAI

    key, url, model = get_agent_config()
    client = OpenAI(api_key=key, base_url=url)
    prompt = f"""请判断以下每条文本的情感倾向。只返回JSON数组，每个元素为"positive"/"negative"/"neutral"。

文本列表：
{_json.dumps(texts, ensure_ascii=False)}"""
    resp = client.chat.completions.create(
        model=model or settings.DEFAULT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=len(texts) * 10,
    )
    content = (resp.choices[0].message.content or "").strip()
    # 尝试解析 JSON
    if content.startswith("["):
        try:
            return _json.loads(content)
        except _json.JSONDecodeError:
            pass
    # 回退：全部 neutral
    return ["neutral"] * len(texts)


# ───────────────────────────────────────────────────────────────
# H8. calc_velocity — 时间序列情感速度计算
# ───────────────────────────────────────────────────────────────
@tool(
    name="calc_velocity",
    description="计算时间序列情感变化速度（Delta）。需传入带时间戳的快照数据。",
    parameters={
        "type": "object",
        "properties": {
            "snapshots": {
                "type": "array",
                "description": "快照列表，每项含 ts/positive/negative/neutral/volume 字段",
            },
        },
        "required": ["snapshots"],
    },
    group="atomic",
)
@with_owner
def calc_velocity_tool(snapshots: list, _owner_id: str) -> str:
    """计算时间序列情感变化速度。"""
    if not snapshots:
        return ToolResult(success=True, data=[]).to_json()
    try:
        result = _calc_velocity(snapshots)
        return ToolResult(
            success=True,
            data=result,
            ui={"type": "velocity_chart", "data": result},
        ).to_json()
    except Exception as e:
        logger.error(f"[calc_velocity] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


def _calc_velocity(snapshots: list[dict]) -> list[dict]:
    """输入 [{ts, positive, negative, neutral, volume}, ...]，输出带 delta 的快照列表。"""
    result = []
    prev: Optional[dict] = None
    for s in snapshots:
        delta = {"positive": 0.0, "negative": 0.0, "volume": 0}
        if prev:
            delta["positive"] = round(float(s.get("positive", 0)) - float(prev.get("positive", 0)), 2)
            delta["negative"] = round(float(s.get("negative", 0)) - float(prev.get("negative", 0)), 2)
            delta["volume"] = int(s.get("volume", 0)) - int(prev.get("volume", 0))
        result.append({**s, "delta": delta})
        prev = s
    return result


# ───────────────────────────────────────────────────────────────
# H9. compare_platforms — 跨平台叙事对比
# ───────────────────────────────────────────────────────────────
@tool(
    name="compare_platforms",
    description="对比不同平台对同一话题的叙事差异。输入各平台帖子列表，输出对比结果。",
    parameters={
        "type": "object",
        "properties": {
            "platform_data": {
                "type": "object",
                "description": "各平台帖子数据，格式: {platform_name: [{title, content, ...}]}",
            },
        },
        "required": ["platform_data"],
    },
    group="atomic",
)
@with_owner
def compare_platforms_tool(platform_data: dict, _owner_id: str) -> str:
    """跨平台叙事对比。"""
    if not platform_data:
        return ToolResult(success=True, data={}).to_json()
    try:
        result = {}
        for platform, posts in platform_data.items():
            if not posts:
                continue
            count = len(posts)
            # 统计情感
            pos = sum(1 for p in posts if p.get("sentiment") == "positive")
            neg = sum(1 for p in posts if p.get("sentiment") == "negative")
            result[platform] = {
                "post_count": count,
                "positive_ratio": round(pos / max(count, 1), 2),
                "negative_ratio": round(neg / max(count, 1), 2),
            }
        # LLM 叙事总结
        narratives = {}
        for platform, data in result.items():
            narratives[platform] = f"{data['post_count']}条帖子，正面{data['positive_ratio']:.0%}，负面{data['negative_ratio']:.0%}"
        return ToolResult(
            success=True,
            data={"statistics": result, "narratives": narratives},
            ui={"type": "platform_comparison", "data": result},
        ).to_json()
    except Exception as e:
        logger.error(f"[compare_platforms] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


# ───────────────────────────────────────────────────────────────
# H10. query_report — 查询已生成的报告
# ───────────────────────────────────────────────────────────────
@tool(
    name="query_report",
    description="查询已生成的攻略/追星/简报报告。支持按类型和关键词筛选。",
    parameters={
        "type": "object",
        "properties": {
            "report_type": {
                "type": "string",
                "enum": ["guide", "celebrity", "briefing"],
                "default": "guide",
                "description": "报告类型",
            },
            "keyword": {"type": "string", "default": "", "description": "关键词筛选"},
            "limit": {"type": "integer", "default": 10, "description": "返回条数上限"},
        },
        "required": [],
    },
    group="atomic",
)
@with_owner
def query_report_tool(_owner_id: str, report_type: str = "guide", keyword: str = "", limit: int = 10) -> str:
    """查询已生成的报告。"""
    try:
        table_map = {
            "guide": "guide_reports",
            "celebrity": "celebrity_reports",
            "briefing": "daily_briefings",
        }
        table = table_map.get(report_type, "guide_reports")
        import sqlite3
        from backend.core.database import get_db_connection
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = f"SELECT * FROM {table} WHERE owner_id = ?"
            params: list = [_owner_id]
            if keyword:
                query += " AND keyword LIKE ?"
                params.append(f"%{keyword}%")
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]
        if not rows:
            return ToolResult(success=True, data=[], ui={"type": "report_list", "data": []}).to_json()
        return ToolResult(
            success=True,
            data=rows,
            ui={"type": "report_list", "data": rows},
        ).to_json()
    except Exception as e:
        logger.error(f"[query_report] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


# ───────────────────────────────────────────────────────────────
# H11. push_report — 推送报告
# ───────────────────────────────────────────────────────────────
@tool(
    name="push_report",
    description="通过指定通道推送报告内容。支持 email/wecom/feishu/rss。",
    parameters={
        "type": "object",
        "properties": {
            "report_content": {"type": "string", "description": "报告内容"},
            "channel": {
                "type": "string",
                "enum": ["email", "wecom", "feishu", "rss"],
                "default": "email",
                "description": "推送通道",
            },
            "title": {"type": "string", "default": "", "description": "推送标题"},
        },
        "required": ["report_content"],
    },
    group="atomic",
)
@with_owner
def push_report_tool(report_content: str, _owner_id: str, channel: str = "email", title: str = "") -> str:
    """通过指定通道推送报告内容。"""
    if not report_content.strip():
        return ToolResult(success=False, error="推送内容不能为空", error_type="validation").to_json()
    try:
        from backend.services.radar_service.notifier import send_alert
        send_alert(
            owner_id=_owner_id,
            keyword=title or "Agent 报告推送",
            platform="system",
            risk_level=2,
            risk_class="medium",
            core_issue=title or "报告推送",
            report=report_content,
            urls=[],
            email_html=report_content,
        )
        return ToolResult(
            success=True,
            data={"channel": channel, "status": "sent", "title": title or "报告推送"},
            ui={"type": "push_result", "data": {"channel": channel, "status": "sent"}},
        ).to_json()
    except Exception as e:
        logger.error(f"[push_report] 异常: {e}", exc_info=True)
        return ToolResult(success=False, error=str(e), error_type="unknown").to_json()


# ───────────────────────────────────────────────────────────────
# H12. list_workflows — 列出当前用户可见工作流
# ───────────────────────────────────────────────────────────────
@tool(
    name="list_workflows",
    description=(
        "列出当前用户可见的所有工作流（user 自定义 + auto_template 累积 + 预置组合工具 preset）。"
        "用户问'我有哪些工作流'、'看 preset 工具'时调用。"
    ),
    parameters=None,
    group="atomic",
)
@with_owner
def list_workflows_tool(_owner_id: str) -> str:
    """返回工作流列表，按 source 分组"""
    from backend.services.agent_service.workflows_db import WorkflowsDB
    db = WorkflowsDB()
    # ★ R-013 修订：(owner=? AND source IN ('user','auto_template')) OR (source='preset')
    items = db.query(
        """
        SELECT id, owner_id, name, description, source,
               schedule_cron, schedule_desc, enabled,
               hit_count, last_hit, last_run, run_count,
               is_composite_tool, created_at, updated_at
        FROM workflows
        WHERE (owner_id = ? AND source IN ('user', 'auto_template'))
           OR (source = 'preset')
        ORDER BY source ASC, updated_at DESC
        """,
        [_owner_id],
    )
    return json.dumps({
        "success": True,
        "data": items,
        "ui": {"type": "workflow_list", "data": {"items": items, "count": len(items)}},
    }, ensure_ascii=False, default=str)


# ───────────────────────────────────────────────────────────────
# H13. manage_workflow — 管理工作流（5 种 action）
# ───────────────────────────────────────────────────────────────
@tool(
    name="manage_workflow",
    description=(
        "管理工作流。action: enable/disable/delete/run_now/save_as_preset。"
        "enable/disable：开关。delete：删除（preset 不可删）。"
        "run_now：立即执行（仅 user/auto_template）。"
        "save_as_preset：将 auto_template 升级为 user 工作流。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "workflow_id": {"type": "integer", "description": "工作流 ID"},
            "action": {
                "type": "string",
                "enum": ["enable", "disable", "delete", "run_now", "save_as_preset"],
                "description": "操作类型",
            },
        },
        "required": ["workflow_id", "action"],
    },
    group="atomic",
)
@with_owner
def manage_workflow_tool(workflow_id: int, action: str, _owner_id: str) -> str:
    from backend.services.agent_service.workflows_db import WorkflowsDB
    db = WorkflowsDB()
    wf = db.get_by_id(workflow_id)

    if not wf:
        return json.dumps({"success": False, "error": "工作流不存在"}, ensure_ascii=False)
    if wf["owner_id"] != _owner_id and wf["owner_id"] != "system":
        return json.dumps({
            "success": False, "error": "无权操作他人工作流",
        }, ensure_ascii=False)

    if action == "enable":
        db.set_enabled(workflow_id, True)
        msg = "已启用"
    elif action == "disable":
        db.set_enabled(workflow_id, False)
        msg = "已停用"
    elif action == "delete":
        if wf["source"] == "preset":
            return json.dumps({
                "success": False,
                "error": "系统预置工作流不可删除，请使用 disable 停用",
            }, ensure_ascii=False)
        db.delete(workflow_id)
        msg = "已删除"
    elif action == "run_now":
        if wf["source"] == "preset":
            return json.dumps({
                "success": False,
                "error": "预置组合工具由 Agent Function Calling 调用，无需手动 run_now",
            }, ensure_ascii=False)
        import asyncio
        from backend.services.radar_service.scheduler import _execute_workflow_row
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_execute_workflow_row(wf))
        except RuntimeError:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                ex.submit(_run_workflow_sync, wf)
        msg = "已加入执行队列"
    elif action == "save_as_preset":
        # ★ R-014 修订：只允许 auto_template → user，禁止其他转换
        if wf["source"] != "auto_template":
            return json.dumps({
                "success": False,
                "error": "save_as_preset 只能将 auto_template 转为 user 工作流。"
                         "若需把 user 升为 preset，请联系 Admin。",
            }, ensure_ascii=False)
        db.update(workflow_id, source="user")
        msg = "已转为 user 工作流（可加 cron 调度）"
    else:
        return json.dumps({
            "success": False, "error": f"未知 action: {action}",
        }, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "action": action,
        "workflow_id": workflow_id,
        "message": msg,
        "ui": {"type": "workflow_action_result", "data": {
            "workflow_id": workflow_id, "action": action, "message": msg,
        }},
    }, ensure_ascii=False)


def _run_workflow_sync(workflow: dict):
    """run_now 在非 event loop 上下文时的同步兜底"""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        from backend.services.radar_service.scheduler import _execute_workflow_row
        loop.run_until_complete(_execute_workflow_row(workflow))
    finally:
        loop.close()
