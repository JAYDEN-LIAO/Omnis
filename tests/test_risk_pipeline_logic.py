"""Pure logic tests for the restored risk pipeline components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Literal

from backend.services.agent_service import analysis_graph, llm_gateway


def test_json_response_with_code_fence_is_parsed() -> None:
    """Providers may wrap JSON in Markdown; the gateway must recover the object."""
    assert llm_gateway._parse_json_content(
        '```json\n{"risk_level": 3}\n```'
    ) == {"risk_level": 3}
    assert llm_gateway._parse_json_content('说明 {"risk_level": 2} 说明') == {
        "risk_level": 2
    }


def test_analyst_settings_fall_back_to_default(monkeypatch: Any) -> None:
    """Analyst and reviewer settings must inherit safe defaults when omitted."""
    monkeypatch.setattr(llm_gateway.settings, "ANALYST_API_KEY", "")
    monkeypatch.setattr(llm_gateway.settings, "ANALYST_BASE_URL", "")
    monkeypatch.setattr(llm_gateway.settings, "ANALYST_MODEL", "")
    monkeypatch.setattr(llm_gateway.settings, "DEFAULT_API_KEY", "test-key")
    monkeypatch.setattr(llm_gateway.settings, "DEFAULT_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(llm_gateway.settings, "DEFAULT_MODEL", "test-model")

    assert llm_gateway._config_for("analyst") == (
        "analyst",
        "test-key",
        "https://example.test/v1",
        "test-model",
    )


def test_reviewer_rejection_downgrades_high_risk(monkeypatch: Any) -> None:
    """A reviewer rejection must prevent the director alert report from running."""

    @dataclass
    class StubResult:
        success: Literal[True] = True
        data: dict[str, Any] | None = None
        error: str = ""
        raw: str = ""

    def fake_call_llm(prompt: str, text: str, **kwargs: Any) -> StubResult:
        if kwargs.get("engine") == "analyst":
            return StubResult(data={
                "risk_level": 4,
                "sentiment": "Negative",
                "core_issue": "测试风险",
                "analysis_process": "初步判断为高风险",
            })
        if kwargs.get("engine") == "reviewer":
            return StubResult(data={
                "is_confirmed": False,
                "adjusted_risk_level": 2,
                "reason": "仅是个案投诉，驳回高风险",
            })
        raise AssertionError("downgraded result must not invoke the director node")

    monkeypatch.setattr(analysis_graph, "call_llm", fake_call_llm)

    result = analysis_graph.analyze_and_report(
        {"title": "测试话题", "content": "测试内容"},
        keyword="测试关键词",
        sensitivity="balanced",
    )

    assert result["status"] == "safe"
    assert result["risk_level"] == 2
    assert result["reason"] == "仅是个案投诉，驳回高风险"
