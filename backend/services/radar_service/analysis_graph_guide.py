"""
攻略线 LangGraph 分析子图

三节点：extractor → comparer → summarizer
单模型（DeepSeek），无交叉验证。
对外暴露 analyze_guide() 接口，签名与 analyze_and_report 一致。
"""

from langgraph.graph import StateGraph, END
from typing import TypedDict, List


class GuideGraphState(TypedDict):
    """攻略图状态"""
    mock_post: dict
    keyword: str
    sensitivity: str
    # extractor 输出
    extracted_items: list[dict]
    # comparer 输出
    consensus: list[str]
    controversial: list[str]
    # summarizer 输出
    summary: str
    tips: list[str]
    sources: dict


def _call_llm_simple(prompt: str, text: str) -> str:
    """同步调用 DeepSeek（简化版，复用 llm_gateway 但无 pydantic 约束）"""
    from .llm_gateway import call_llm
    res = call_llm(prompt, text, response_format="text", engine="deepseek")
    return res.data if res.success and res.data is not None else ""


def extractor_node(state: GuideGraphState) -> dict:
    """从帖子中提取结构化攻略信息"""
    text = f"标题：{state['mock_post'].get('title', '')}\n内容：{state['mock_post'].get('content', '')}"
    prompt = f"""你是一个攻略信息提取专家。
关键词：{state['keyword']}

从以下内容中提取攻略相关信息，输出 JSON（不要其他内容）：
{{
  "items": [
    {{"place": "地点/产品名", "experience": "体验描述", "rating": "推荐等级 1-5", "source": "来源平台"}}
  ]
}}

如果没有可用信息，返回 {{"items": []}}"""

    from .llm_gateway import call_llm
    from pydantic import BaseModel, Field

    class ExtractedItem(BaseModel):
        place: str = Field(default="")
        experience: str = Field(default="")
        rating: int = Field(default=3)
        source: str = Field(default="")

    class ExtractionResult(BaseModel):
        items: list[ExtractedItem] = Field(default_factory=list)

    res = call_llm(prompt, text, response_format="json", engine="deepseek",
                   pydantic_model=ExtractionResult)
    items = []
    if res.success and res.data:
        items = [{"place": i.place, "experience": i.experience,
                   "rating": i.rating, "source": i.source}
                 for i in res.data.items]

    return {"extracted_items": items}


def comparer_node(state: GuideGraphState) -> dict:
    """跨来源对比——找共识和争议"""
    items = state.get("extracted_items", [])
    if not items:
        return {"consensus": [], "controversial": []}

    items_text = "\n".join([
        f"- {i.get('place', '?')}: {i.get('experience', '')} (评分:{i.get('rating', 3)})"
        for i in items
    ])
    prompt = f"""你是一个攻略信息对比专家。
关键词：{state['keyword']}

分析以下多条攻略/体验信息，找出共识点和争议点：

{items_text}

输出 JSON：
{{
  "consensus": ["共识点1（如：茶颜悦色推荐幽兰拿铁）"],
  "controversial": ["争议点1（如：文和友评价两极分化）"]
}}"""

    from .llm_gateway import call_llm
    from pydantic import BaseModel, Field

    class CompareResult(BaseModel):
        consensus: list[str] = Field(default_factory=list)
        controversial: list[str] = Field(default_factory=list)

    res = call_llm(prompt, "", response_format="json", engine="deepseek",
                   pydantic_model=CompareResult)
    if res.success and res.data:
        return {"consensus": res.data.consensus, "controversial": res.data.controversial}
    return {"consensus": [], "controversial": []}


def summarizer_node(state: GuideGraphState) -> dict:
    """生成结构化攻略报告"""
    items = state.get("extracted_items", [])
    consensus = state.get("consensus", [])
    controversial = state.get("controversial", [])

    context = f"共 {len(items)} 条攻略信息"
    if consensus:
        context += "\n共识：" + "\n".join(f"- {c}" for c in consensus)
    if controversial:
        context += "\n争议：" + "\n".join(f"- {c}" for c in controversial)

    prompt = f"""你是一个攻略总结专家。
关键词：{state['keyword']}

基于以下分析结果，生成综合攻略报告：

{context}

输出 JSON：
{{
  "summary": "综合 50 字以内的汇总建议",
  "tips": ["实用建议1", "实用建议2"],
  "sources": {{"平台名": 数量}}
}}"""

    from .llm_gateway import call_llm
    from pydantic import BaseModel, Field

    class SummaryResult(BaseModel):
        summary: str = Field(default="")
        tips: list[str] = Field(default_factory=list)
        sources: dict = Field(default_factory=dict)

    res = call_llm(prompt, "", response_format="json", engine="deepseek",
                   pydantic_model=SummaryResult)
    if res.success and res.data:
        return {
            "summary": res.data.summary,
            "tips": res.data.tips,
            "sources": res.data.sources,
        }
    return {"summary": "", "tips": [], "sources": {}}


# 编译图
guide_workflow = StateGraph(GuideGraphState)
guide_workflow.add_node("extractor", extractor_node)
guide_workflow.add_node("comparer", comparer_node)
guide_workflow.add_node("summarizer", summarizer_node)
guide_workflow.set_entry_point("extractor")
guide_workflow.add_edge("extractor", "comparer")
guide_workflow.add_edge("comparer", "summarizer")
guide_workflow.add_edge("summarizer", END)
guide_app = guide_workflow.compile()


def analyze_guide(mock_post: dict, keyword: str, sensitivity: str = "balanced",
                  evolution_timeline: dict = None) -> dict:
    """
    攻略线分析入口。
    签名与 analyze_and_report 一致。

    Returns:
        dict 包含 summary / consensus / controversial / tips / sources
    """
    initial_state = {
        "mock_post": mock_post,
        "keyword": keyword,
        "sensitivity": sensitivity,
        "extracted_items": [],
        "consensus": [],
        "controversial": [],
        "summary": "",
        "tips": [],
        "sources": {},
    }

    final_state = guide_app.invoke(initial_state)

    return {
        "summary": final_state.get("summary", ""),
        "consensus": final_state.get("consensus", []),
        "controversial": final_state.get("controversial", []),
        "tips": final_state.get("tips", []),
        "sources": final_state.get("sources", {}),
    }
