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

# H4-H9: extract_slots / compare_opinions / generate_itinerary / analyze_sentiment / calc_velocity / compare_platforms
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


