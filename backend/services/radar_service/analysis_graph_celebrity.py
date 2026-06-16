"""
追星线 LangGraph 分析子图

三节点：sentiment → heat → aggregator
单模型（DeepSeek），无交叉验证。
对外暴露 analyze_celebrity() 接口。
"""

from langgraph.graph import StateGraph, END
from typing import TypedDict, List


class CelebrityGraphState(TypedDict):
    """追星图状态"""
    mock_post: dict
    keyword: str
    sensitivity: str
    # 中间结果
    sentiment_distribution: dict
    heat_trend: str
    hot_topics: list[str]
    cross_platform: dict


def sentiment_node(state: CelebrityGraphState) -> dict:
    """分析情感分布"""
    text = f"标题：{state['mock_post'].get('title', '')}\n内容：{state['mock_post'].get('content', '')}"
    prompt = f"""你是一个娱乐舆情情感分析专家。
目标明星：{state['keyword']}

分析以下内容的情感倾向和讨论焦点，输出 JSON：
{{
  "distribution": {{"positive": 0.0, "negative": 0.0, "neutral": 0.0}},
  "hot_topics": ["讨论话题1", "讨论话题2"]
}}

注意：distribution 的三项之和应为 1.0。"""

    from .llm_gateway import call_llm
    from pydantic import BaseModel, Field

    class SentimentResult(BaseModel):
        distribution: dict = Field(default_factory=lambda: {"positive": 0.0, "negative": 0.0, "neutral": 0.0})
        hot_topics: list[str] = Field(default_factory=list)

    res = call_llm(prompt, text, response_format="json", engine="deepseek",
                   pydantic_model=SentimentResult)
    if res.success and res.data:
        return {
            "sentiment_distribution": res.data.distribution,
            "hot_topics": res.data.hot_topics,
        }
    return {"sentiment_distribution": {"positive": 0.0, "negative": 0.0, "neutral": 0.0},
            "hot_topics": []}


def heat_node(state: CelebrityGraphState) -> dict:
    """判断热度趋势"""
    dist = state.get("sentiment_distribution", {})
    total = sum(dist.values()) if dist else 0
    prompt = f"""你是一个娱乐热度趋势分析师。
目标明星：{state['keyword']}

当前情感分布：positive={dist.get('positive', 0):.0%}, negative={dist.get('negative', 0):.0%}, neutral={dist.get('neutral', 0):.0%}
总讨论量级：{total:.0%}

输出 JSON（仅输出以下结构）：
{{
  "heat_trend": "rising|stable|falling",
  "reason": "趋势判断理由（15字内）"
}}"""

    from .llm_gateway import call_llm
    from pydantic import BaseModel, Field

    class HeatResult(BaseModel):
        heat_trend: str = Field(default="stable")
        reason: str = Field(default="")

    res = call_llm(prompt, "", response_format="json", engine="deepseek",
                   pydantic_model=HeatResult)
    heat_trend = "stable"
    if res.success and res.data:
        heat_trend = res.data.heat_trend if res.data.heat_trend in ("rising", "stable", "falling") else "stable"

    return {"heat_trend": heat_trend}


def aggregator_node(state: CelebrityGraphState) -> dict:
    """聚合多平台数据"""
    keyword = state["keyword"]
    sentiment_dist = state.get("sentiment_distribution", {})
    hot_topics = state.get("hot_topics", [])
    heat_trend = state.get("heat_trend", "stable")

    prompt = f"""你是一个多平台娱乐数据聚合专家。
目标明星：{keyword}

情感分布：positive={sentiment_dist.get('positive', 0):.0%}, negative={sentiment_dist.get('negative', 0):.0%}, neutral={sentiment_dist.get('neutral', 0):.0%}
热度趋势：{heat_trend}
热门话题：{', '.join(hot_topics[:5])}

输出 JSON：
{{
  "cross_platform": {{
    "wb": {{"count": 0, "focus": "粉丝控评/作品讨论"}},
    "xhs": {{"count": 0, "focus": "穿搭同款/生活方式"}},
    "bili": {{"count": 0, "focus": "剪辑二创/混剪"}}
  }}
}}

注意：count 根据实际情况估算相对比例。"""

    from .llm_gateway import call_llm
    from pydantic import BaseModel, Field

    class PlatformInfo(BaseModel):
        count: int = Field(default=0)
        focus: str = Field(default="")

    class CrossPlatform(BaseModel):
        wb: PlatformInfo = Field(default_factory=lambda: PlatformInfo(count=0, focus=""))
        xhs: PlatformInfo = Field(default_factory=lambda: PlatformInfo(count=0, focus=""))
        bili: PlatformInfo = Field(default_factory=lambda: PlatformInfo(count=0, focus=""))

    class AggResult(BaseModel):
        cross_platform: CrossPlatform = Field(default_factory=CrossPlatform)

    res = call_llm(prompt, "", response_format="json", engine="deepseek",
                   pydantic_model=AggResult)
    cross_platform = {}
    if res.success and res.data:
        cp = res.data.cross_platform
        cross_platform = {
            "wb": {"count": cp.wb.count, "focus": cp.wb.focus},
            "xhs": {"count": cp.xhs.count, "focus": cp.xhs.focus},
            "bili": {"count": cp.bili.count, "focus": cp.bili.focus},
        }

    return {
        "celebrity": keyword,
        "cross_platform": cross_platform,
    }


# 编译图
celebrity_workflow = StateGraph(CelebrityGraphState)
celebrity_workflow.add_node("sentiment", sentiment_node)
celebrity_workflow.add_node("heat", heat_node)
celebrity_workflow.add_node("aggregator", aggregator_node)
celebrity_workflow.set_entry_point("sentiment")
celebrity_workflow.add_edge("sentiment", "heat")
celebrity_workflow.add_edge("heat", "aggregator")
celebrity_workflow.add_edge("aggregator", END)
celebrity_app = celebrity_workflow.compile()


def analyze_celebrity(mock_post: dict, keyword: str, sensitivity: str = "balanced",
                      evolution_timeline: dict = None) -> dict:
    """
    追星线分析入口。

    Returns:
        dict 包含 celebrity / sentiment_distribution / heat_trend /
              hot_topics / cross_platform
    """
    initial_state = {
        "mock_post": mock_post,
        "keyword": keyword,
        "sensitivity": sensitivity,
        "sentiment_distribution": {},
        "heat_trend": "stable",
        "hot_topics": [],
        "cross_platform": {},
    }

    final_state = celebrity_app.invoke(initial_state)

    return {
        "celebrity": final_state.get("celebrity", keyword),
        "sentiment_distribution": final_state.get("sentiment_distribution", {}),
        "heat_trend": final_state.get("heat_trend", "stable"),
        "hot_topics": final_state.get("hot_topics", []),
        "cross_platform": final_state.get("cross_platform", {}),
    }
