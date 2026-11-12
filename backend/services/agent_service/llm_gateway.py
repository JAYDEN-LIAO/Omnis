"""Small compatibility gateway for the analysis pipeline.

The historical ``llm_gateway`` module was removed during the service split while
``pipeline.py`` and ``embed_cluster.py`` continued to import it. This module
restores only the interface those callers need and delegates to the existing
OpenAI-compatible settings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from openai import OpenAI

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("agent.llm_gateway")


@dataclass
class LLMCallResult:
    """Normalized result used by pipeline stages."""

    success: bool
    data: Any = None
    error: str = ""
    raw: str = ""


global_http_client = httpx.Client(timeout=60.0)
_client_cache: dict[tuple[str, str, str, str], OpenAI] = {}

_ENGINE_PREFIXES = {
    "analyst": "ANALYST",
    "reviewer": "REVIEWER",
    "assistant": "ASSISTANT",
    "vision": "VISION",
    "default": "DEFAULT",
    "deepseek": "DEFAULT",
    "kimi": "DEFAULT",
}


def _config_for(engine: str) -> tuple[str, str, str, str]:
    engine = (engine or "default").lower()
    prefix = _ENGINE_PREFIXES.get(engine, "DEFAULT")

    def field(name: str) -> str:
        specific = getattr(settings, f"{prefix}_{name.upper()}", "") or ""
        return specific if specific else getattr(settings, f"DEFAULT_{name.upper()}", "") or ""

    return engine, field("api_key"), field("base_url"), field("model")


def _client_for(engine: str) -> tuple[OpenAI | None, str, str]:
    engine, api_key, base_url, model = _config_for(engine)
    cache_key = (engine, api_key, base_url, model)
    client = _client_cache.get(cache_key)
    if client is None:
        if not api_key:
            return None, model, f"{engine} model API key is not configured"
        client = OpenAI(
            api_key=api_key,
            base_url=base_url or None,
            http_client=global_http_client,
            timeout=60.0,
        )
        _client_cache[cache_key] = client
    return client, model, ""


def _parse_json_content(content: str) -> dict:
    text = content.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Some providers prepend reasoning before the JSON object. Parse the
        # outermost object instead of accepting that prose as a final answer.
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            value = json.loads(text[start:end + 1])
            if isinstance(value, dict):
                return value
        raise


def call_llm(
    prompt: str,
    text: str = "",
    *,
    engine: str = "default",
    response_format: str | None = None,
    pydantic_model: Any = None,
    max_tokens: int = 2000,
    temperature: float = 0.2,
) -> LLMCallResult:
    """Call an OpenAI-compatible chat model and normalize its response."""

    client, model, configuration_error = _client_for(engine)
    if client is None:
        return LLMCallResult(success=False, error=configuration_error)

    user_content = f"{prompt}\n\n{text}".strip() if text else prompt
    request_kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": user_content}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format == "json":
        request_kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**request_kwargs)
        if not response.choices:
            return LLMCallResult(success=False, error="LLM returned no choices")
        content = response.choices[0].message.content or ""
        if not content.strip():
            return LLMCallResult(success=False, error="LLM returned empty content")

        if response_format == "json" or pydantic_model is not None:
            data: Any = _parse_json_content(content)
            if pydantic_model is not None:
                data = pydantic_model.model_validate(data).model_dump()
            return LLMCallResult(success=True, data=data, raw=content)

        return LLMCallResult(success=True, data=content, raw=content)
    except Exception as exc:
        logger.error(f"[LLMGateway] engine={engine} call failed: {type(exc).__name__}")
        return LLMCallResult(success=False, error=f"LLM call failed: {type(exc).__name__}")


class _LazyEmbeddingClient:
    """Create the embedding client on first use."""

    _client: OpenAI | None = None

    def _get(self) -> OpenAI:
        if self._client is None:
            api_key = settings.EMBEDDING_API_KEY or settings.DEFAULT_API_KEY
            if not api_key:
                raise RuntimeError("embedding model API key is not configured")
            self._client = OpenAI(
                api_key=api_key,
                base_url=settings.EMBEDDING_BASE_URL or settings.DEFAULT_BASE_URL or None,
                http_client=global_http_client,
                timeout=60.0,
            )
        return self._client

    def __getattr__(self, name: str):
        return getattr(self._get(), name)


embedding_client = _LazyEmbeddingClient()
