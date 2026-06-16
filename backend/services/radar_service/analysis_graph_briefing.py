"""
简报线 LangGraph 分析子图

三节点：categorizer → highlighter → writer
单模型（DeepSeek），无交叉验证。
对外暴露 analyze_briefing() 接口。
"""

from langgraph.graph import StateGraph, END
from typing import TypedDict, List
from datetime import datetime


class BriefingGraphState(TypedDict):
    """简报图状态"""
    mock_post: dict
    keyword: str
    sensitivity: str
    # categorizer 输出
    domain: str
    info_type: str
    # highlighter 输出
    highlight: str
    key_numbers: list[str]
    # writer 输出
    date: str
    sentiment: str


def categorizer_node(state: BriefingGraphState) -> dict:
    """内容分类打标"""
    text = f"标题：{state['mock_post'].get('title', '')}\n内容：{state['mock_post'].get('content', '')}"
    prompt = f"""你是一个信息分类专家。
目标领域：{state['keyword']}

对以下内容进行分类，输出 JSON：
{{
  "domain": "最具体的领域标签（如：新能源汽车/AI大模型/医美/留学）",
  "info_type": "tech|entertainment|travel|finance|other"
}}"""

    from .llm_gateway import call_llm
    from pydantic import BaseModel, Field

    class CategoryResult(BaseModel):
        domain: str = Field(default="")
        info_type: str = Field(default="other")

    res = call_llm(prompt, text, response_format="json", engine="deepseek",
                   pydantic_model=CategoryResult)
    if res.success and res.data:
        info_type = res.data.info_type if res.data.info_type in ("tech", "entertainment", "travel", "finance", "other") else "other"
        return {"domain": res.data.domain, "info_type": info_type}
    return {"domain": "", "info_type": "other"}


def highlighter_node(state: BriefingGraphState) -> dict:
    """提取关键信息亮点"""
    text = f"标题：{state['mock_post'].get('title', '')}\n内容：{state['mock_post'].get('content', '')}"
    domain = state.get("domain", "")
    prompt = f"""你是一个简报内容提炼专家。
领域：{domain}

从以下内容中提取最有信息量的亮点，输出 JSON：
{{
  "highlight": "一句话概括核心信息（20字以内）",
  "key_numbers": ["关键数据1", "关键数据2"]
}}

如果无突出亮点，highlight 输出"常规信息"。"""

    from .llm_gateway import call_llm
    from pydantic import BaseModel, Field

    class HighlightResult(BaseModel):
        highlight: str = Field(default="")
        key_numbers: list[str] = Field(default_factory=list)

    res = call_llm(prompt, text, response_format="json", engine="deepseek",
                   pydantic_model=HighlightResult)
    if res.success and res.data:
        return {"highlight": res.data.highlight, "key_numbers": res.data.key_numbers}
    return {"highlight": "", "key_numbers": []}


def writer_node(state: BriefingGraphState) -> dict:
    """生成简报条目"""
    domain = state.get("domain", "")
    highlight = state.get("highlight", "")
    info_type = state.get("info_type", "other")

    prompt = f"""你是一个简报撰写专家。
领域：{domain}
类型：{info_type}
亮点：{highlight}

输出 JSON：
{{
  "sentiment": "positive|negative|neutral"
}}"""

    from .llm_gateway import call_llm
    from pydantic import BaseModel, Field

    class SentimentResult(BaseModel):
        sentiment: str = Field(default="neutral")

    res = call_llm(prompt, "", response_format="json", engine="deepseek",
                   pydantic_model=SentimentResult)
    sentiment = "neutral"
    if res.success and res.data:
        sentiment = res.data.sentiment if res.data.sentiment in ("positive", "negative", "neutral") else "neutral"

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sentiment": sentiment,
    }


# 编译图
briefing_workflow = StateGraph(BriefingGraphState)
briefing_workflow.add_node("categorizer", categorizer_node)
briefing_workflow.add_node("highlighter", highlighter_node)
briefing_workflow.add_node("writer", writer_node)
briefing_workflow.set_entry_point("categorizer")
briefing_workflow.add_edge("categorizer", "highlighter")
briefing_workflow.add_edge("highlighter", "writer")
briefing_workflow.add_edge("writer", END)
briefing_app = briefing_workflow.compile()


def analyze_briefing(mock_post: dict, keyword: str, sensitivity: str = "balanced",
                     evolution_timeline: dict = None) -> dict:
    """
    简报线分析入口。

    Returns:
        dict 包含 date / domain / highlight / sentiment / info_type
    """
    initial_state = {
        "mock_post": mock_post,
        "keyword": keyword,
        "sensitivity": sensitivity,
        "domain": "",
        "info_type": "other",
        "highlight": "",
        "key_numbers": [],
        "date": "",
        "sentiment": "neutral",
    }

    final_state = briefing_app.invoke(initial_state)

    return {
        "date": final_state.get("date", ""),
        "domain": final_state.get("domain", ""),
        "highlight": final_state.get("highlight", ""),
        "sentiment": final_state.get("sentiment", "neutral"),
        "info_type": final_state.get("info_type", "other"),
    }
