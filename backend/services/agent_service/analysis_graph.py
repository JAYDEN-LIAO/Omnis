"""Risk analysis sub-graph restored as a small sequential implementation.

The old LangGraph dependency is no longer present in the repository. The
pipeline only needs the analyst → reviewer → director behavior and a stable
dictionary result, so this module keeps that contract without introducing a
new framework.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .llm_gateway import LLMCallResult, call_llm
from .tools.screener_prompts import (
    ANALYST_PROMPT,
    ANALYST_PROMPT_WITH_EVOLUTION,
    DIRECTOR_PROMPT,
    REVIEWER_PROMPT,
)


def _post_text(mock_post: dict[str, Any]) -> str:
    title = mock_post.get("title", "")
    content = mock_post.get("content", "")
    return f"标题：{title}\n内容：{content}".strip()


def _reference_cases(evolution_timeline: dict[str, Any]) -> str:
    cases = evolution_timeline.get("reference_cases") or evolution_timeline.get("similar_topics") or []
    if not isinstance(cases, list) or not cases:
        return "暂无相似历史案例。"
    return "\n".join(
        f"案例{i + 1}：{json.dumps(case, ensure_ascii=False)[:800]}"
        for i, case in enumerate(cases[:3])
    )


def _evolution_context(evolution_timeline: dict[str, Any]) -> str:
    if not evolution_timeline:
        return "暂无话题演化信息。"
    keys = ("evolution_signal", "is_new_topic", "trend", "summary")
    values = {key: evolution_timeline[key] for key in keys if key in evolution_timeline}
    return json.dumps(values, ensure_ascii=False) if values else "暂无话题演化信息。"


def _level_instruction(sensitivity: str) -> str:
    normalized = (sensitivity or "balanced").lower()
    if normalized in {"aggressive", "high"}:
        return "高敏模式：疑似群体共鸣、监管合规或资金安全问题时，倾向于维持 3 级及以上判定。"
    if normalized in {"conservative", "low"}:
        return "低敏模式：仅群体性维权、重大违规、资金安全或高管丑闻等强证据才允许维持 3 级及以上判定。"
    return "平衡模式：普通个案客诉降级，具备明显传播或共鸣风险的事件维持 3 级及以上判定。"


def _json_call(prompt: str, text: str, engine: str) -> dict[str, Any]:
    result: LLMCallResult = call_llm(
        prompt,
        text,
        engine=engine,
        response_format="json",
        temperature=0.1,
    )
    if not result.success or not isinstance(result.data, dict):
        raise RuntimeError(result.error or "analysis model returned invalid JSON")
    return result.data


def _risk_level(value: Any, fallback: int = 1) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return fallback


def analyze_and_report(
    mock_post: dict[str, Any],
    *,
    keyword: str = "",
    sensitivity: str = "balanced",
    evolution_timeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timeline = evolution_timeline or {}
    if timeline:
        analyst_prompt = ANALYST_PROMPT_WITH_EVOLUTION.format(
            keyword=keyword,
            evolution_context=_evolution_context(timeline),
            reference_cases=_reference_cases(timeline),
        )
    else:
        analyst_prompt = ANALYST_PROMPT.format(keyword=keyword)

    analyst = _json_call(analyst_prompt, _post_text(mock_post), "analyst")
    risk_level = _risk_level(analyst.get("risk_level"))
    reason = analyst.get("analysis_process", "")

    if risk_level >= 3:
        reviewer_prompt = REVIEWER_PROMPT.format(
            keyword=keyword,
            sensitivity=sensitivity,
            initial_risk=risk_level,
            level_instruction=_level_instruction(sensitivity),
        )
        reviewer = _json_call(reviewer_prompt, _post_text(mock_post), "reviewer")
        confirmed = bool(reviewer.get("is_confirmed"))
        adjusted_risk = _risk_level(reviewer.get("adjusted_risk_level"), risk_level)
        risk_level = adjusted_risk if confirmed else min(adjusted_risk, 2)
        reason = reviewer.get("reason") or reason

    if risk_level >= 3:
        report = call_llm(
            DIRECTOR_PROMPT.format(keyword=keyword),
            _post_text(mock_post),
            engine="default",
            temperature=0.2,
        )
        final_report = report.data if report.success and isinstance(report.data, str) else analyst.get("analysis_process", "")
    else:
        final_report = analyst.get("analysis_process", "未发现需要预警的舆情风险。")

    return {
        "status": "alert" if risk_level >= 3 else "safe",
        "risk_level": risk_level,
        "core_issue": analyst.get("core_issue") or "无",
        "report": final_report,
        "sentiment": analyst.get("sentiment", "Neutral"),
        "analysis_process": analyst.get("analysis_process", ""),
        "reason": reason,
        "evolution_timeline": timeline,
    }


async def analyze_and_report_async(
    mock_post: dict[str, Any],
    *,
    keyword: str = "",
    sensitivity: str = "balanced",
    evolution_timeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        analyze_and_report,
        mock_post,
        keyword=keyword,
        sensitivity=sensitivity,
        evolution_timeline=evolution_timeline,
    )
