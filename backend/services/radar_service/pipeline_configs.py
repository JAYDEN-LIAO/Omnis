"""
Pipeline 工厂注册表

为每个 pipeline_type 提供 builder 函数，
供 scheduler.py 按 subscription.pipeline_types 分发不同 Pipeline 实例。
"""

from typing import List

from .pipeline import RadarPipeline, PipelineConfig


def build_risk_pipeline(keyword: str, platforms: List[str], owner_id: str) -> RadarPipeline:
    """舆情风险线（默认，不改）"""
    return RadarPipeline(PipelineConfig(
        keywords=[keyword],
        keyword_levels={keyword: "balanced"},
        platform=platforms[0] if platforms else "wb",
        mode="full",
        owner_id=owner_id,
        alert_negative=True,
        push_mode="every",
    ))


def build_guide_pipeline(keyword: str, platforms: List[str], owner_id: str) -> RadarPipeline:
    """攻略线"""
    from .prompt_templates import GUIDE_SCREENER_PROMPT
    from .schemas import GuideScreenerResult
    from .analysis_graph_guide import analyze_guide

    return RadarPipeline(PipelineConfig(
        keywords=[keyword],
        keyword_levels={keyword: "balanced"},
        platform=platforms[0] if platforms else "wb",
        mode="guide",
        owner_id=owner_id,
        alert_negative=False,
        push_mode="silent",
        screener_prompt=GUIDE_SCREENER_PROMPT,
        screener_pydantic_model=GuideScreenerResult,
        analysis_callable=analyze_guide,
    ))


def build_celebrity_pipeline(keyword: str, platforms: List[str], owner_id: str) -> RadarPipeline:
    """追星线"""
    from .prompt_templates import CELEBRITY_SCREENER_PROMPT
    from .schemas import CelebrityScreenerResult
    from .analysis_graph_celebrity import analyze_celebrity

    return RadarPipeline(PipelineConfig(
        keywords=[keyword],
        keyword_levels={keyword: "balanced"},
        platform=platforms[0] if platforms else "wb",
        mode="celebrity",
        owner_id=owner_id,
        alert_negative=False,
        push_mode="silent",
        screener_prompt=CELEBRITY_SCREENER_PROMPT,
        screener_pydantic_model=CelebrityScreenerResult,
        analysis_callable=analyze_celebrity,
    ))


def build_briefing_pipeline(keyword: str, platforms: List[str], owner_id: str) -> RadarPipeline:
    """综合简报线"""
    from .prompt_templates import BRIEFING_SCREENER_PROMPT
    from .schemas import BriefingScreenerResult
    from .analysis_graph_briefing import analyze_briefing

    return RadarPipeline(PipelineConfig(
        keywords=[keyword],
        keyword_levels={keyword: "balanced"},
        platform=platforms[0] if platforms else "wb",
        mode="briefing",
        owner_id=owner_id,
        alert_negative=False,
        push_mode="silent",
        screener_prompt=BRIEFING_SCREENER_PROMPT,
        screener_pydantic_model=BriefingScreenerResult,
        analysis_callable=analyze_briefing,
    ))


# ── 注册表 ──
PIPELINE_BUILDERS = {
    "risk": build_risk_pipeline,
    "guide": build_guide_pipeline,
    "celebrity": build_celebrity_pipeline,
    "briefing": build_briefing_pipeline,
}
