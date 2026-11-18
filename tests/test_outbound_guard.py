"""#2 出站安全策略与系统 Key 不外带的回归用例。

所有 DNS 解析均被 mock，测试不联网、不接触真实 LLM / 第三方服务。
"""

from __future__ import annotations

import socket

import pytest

from backend.core.outbound_guard import (
    OutboundPolicyError,
    validate_outbound_host,
    validate_outbound_url,
)


@pytest.fixture
def dns(monkeypatch):
    """把 DNS 解析结果固定为给定 IP 列表，避免测试联网。"""

    def _set(ips: list[str]):
        def _fake_getaddrinfo(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
                for ip in ips
            ]

        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    return _set


def test_public_https_url_allowed(dns) -> None:
    dns(["93.184.216.34"])
    assert validate_outbound_url("https://api.example.com/v1").startswith("https://")


def test_non_https_scheme_rejected(dns) -> None:
    dns(["93.184.216.34"])
    with pytest.raises(OutboundPolicyError):
        validate_outbound_url("http://api.example.com/v1")


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1", "169.254.169.254", "::1"],
)
def test_private_dns_result_rejected(dns, ip: str) -> None:
    dns([ip])
    with pytest.raises(OutboundPolicyError, match="受限网络地址"):
        validate_outbound_url("https://api.example.com/v1")


def test_ip_literal_rejected_without_dns(monkeypatch) -> None:
    def _must_not_resolve(*args, **kwargs):
        raise AssertionError("IP 字面量不应进入 DNS 解析")

    monkeypatch.setattr(socket, "getaddrinfo", _must_not_resolve)
    with pytest.raises(OutboundPolicyError, match="IP 字面量"):
        validate_outbound_url("https://127.0.0.1:9/v1")


def test_embedded_credentials_rejected(dns) -> None:
    dns(["93.184.216.34"])
    with pytest.raises(OutboundPolicyError, match="内嵌凭据"):
        validate_outbound_url("https://user:pass@api.example.com/v1")


def test_allowlist_enforced(monkeypatch, dns) -> None:
    dns(["93.184.216.34"])
    monkeypatch.setenv("OUTBOUND_HOST_ALLOWLIST", "*.trusted.example")
    assert validate_outbound_url("https://llm.trusted.example/v1")
    with pytest.raises(OutboundPolicyError, match="白名单"):
        validate_outbound_url("https://api.attacker.example/v1")


def test_dns_failure_fails_closed(monkeypatch) -> None:
    def _fail(host, port, *args, **kwargs):
        raise OSError("no dns")

    monkeypatch.setattr(socket, "getaddrinfo", _fail)
    with pytest.raises(OutboundPolicyError, match="解析失败"):
        validate_outbound_host("api.example.com")


def test_smtp_host_and_port_validation(dns) -> None:
    dns(["93.184.216.34"])
    assert validate_outbound_host("smtp.example.com", 587) == "smtp.example.com"
    with pytest.raises(OutboundPolicyError, match="端口"):
        validate_outbound_host("smtp.example.com", 0)
    dns(["10.0.0.5"])
    with pytest.raises(OutboundPolicyError):
        validate_outbound_host("smtp.example.com", 587)


def test_llm_test_refuses_system_default_key(monkeypatch) -> None:
    """系统默认 Key 不得进入对外连通性测试请求。"""
    from backend.services.platform_service import api as platform_api
    from backend.shared.db import model_config_db

    monkeypatch.setattr(model_config_db, "get_model_config", lambda *a, **k: {})
    monkeypatch.setattr(
        model_config_db,
        "get_effective_config",
        lambda *a, **k: {
            "api_key": "SYSTEM-DEFAULT-KEY",
            "base_url": "https://api.example.com/v1",
            "model": "test-model",
        },
    )
    result = platform_api.test_llm_config("default", None, {"id": "user-1"})
    assert result["code"] == 400
    assert "系统默认 Key" in result["msg"]


def test_llm_test_blocks_private_base_url_before_request(monkeypatch, dns) -> None:
    """即使调用方自带 Key，私网 base_url 也必须在发请求前被拒绝。"""
    import requests
    from backend.services.platform_service import api as platform_api
    from backend.shared.db import model_config_db

    dns(["127.0.0.1"])
    monkeypatch.setattr(model_config_db, "get_model_config", lambda *a, **k: {})
    monkeypatch.setattr(
        model_config_db,
        "get_effective_config",
        lambda *a, **k: {"api_key": "", "base_url": "https://internal.example/v1", "model": "m"},
    )

    def _must_not_request(*args, **kwargs):
        raise AssertionError("私网目标不应发起 HTTP 请求")

    monkeypatch.setattr(requests, "post", _must_not_request)
    req = platform_api.LLMConfigUpdateRequest(api_key="own-key")
    result = platform_api.test_llm_config("default", req, {"id": "user-1"})
    assert result["code"] == 400
    assert "出站安全策略" in result["msg"]


def test_system_key_forces_system_base_url(monkeypatch) -> None:
    """使用系统 Key 时忽略用户自定义 base_url，避免凭据被外带。"""
    from backend.core.config import settings
    from backend.shared.db import model_config_db

    monkeypatch.setattr(settings, "DEFAULT_API_KEY", "SYSTEM-DEFAULT-KEY")
    monkeypatch.setattr(
        model_config_db,
        "get_model_config",
        lambda *a, **k: {"api_key": "", "base_url": "https://attacker.example/v1", "model": ""},
    )
    monkeypatch.setattr(model_config_db, "_check_user_system_access", lambda *a, **k: True)
    eff = model_config_db.get_effective_config("user-1", "DEFAULT")
    assert eff["api_key"] == "SYSTEM-DEFAULT-KEY"
    assert eff["base_url"] == settings.DEFAULT_BASE_URL
