"""#3 生产启动 fail-fast / fail-closed 回归用例。

用 SimpleNamespace 构造隔离的假配置，不修改全局 settings、不启动服务、不联网。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core import config, crypto_utils

STRONG_SECRET = "p" * 48


def prod_settings(**overrides) -> SimpleNamespace:
    base = dict(
        ENV="prod",
        ALLOWED_ORIGINS="https://omnis.example.com",
        JWT_SECRET=STRONG_SECRET,
        JWT_ALGORITHM="HS256",
        METRICS_TOKEN="metrics-token",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_prod_requires_allowed_origins() -> None:
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        config.parse_allowed_origins(prod_settings(ALLOWED_ORIGINS=""))
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        config.validate_production_settings(prod_settings(ALLOWED_ORIGINS=""))


@pytest.mark.parametrize(
    "origin",
    [
        "http://omnis.example.com",
        "https://*.example.com",
        "https://omnis.example.com/app",
        "https://user:pass@omnis.example.com",
        "https://omnis.example.com?x=1",
    ],
)
def test_prod_rejects_unsafe_origins(origin: str) -> None:
    with pytest.raises(RuntimeError):
        config.parse_allowed_origins(prod_settings(ALLOWED_ORIGINS=origin))


def test_prod_accepts_valid_origins() -> None:
    s = prod_settings(ALLOWED_ORIGINS="https://a.example.com, https://b.example.com/")
    assert config.parse_allowed_origins(s) == [
        "https://a.example.com",
        "https://b.example.com",
    ]


@pytest.mark.parametrize(
    "secret",
    ["", "dev-secret-change-me-in-prod-please-32bytes", "short"],
)
def test_prod_rejects_weak_or_short_jwt_secret(secret: str) -> None:
    with pytest.raises(RuntimeError):
        config._validate_jwt_secret(prod_settings(JWT_SECRET=secret))


def test_algorithm_allowlist() -> None:
    with pytest.raises(RuntimeError, match="JWT_ALGORITHM"):
        config._validate_jwt_secret(prod_settings(JWT_ALGORITHM="none"))


def test_prod_requires_metrics_token() -> None:
    with pytest.raises(RuntimeError, match="METRICS_TOKEN"):
        config.validate_production_settings(prod_settings(METRICS_TOKEN=""))


def test_prod_complete_config_passes(monkeypatch) -> None:
    monkeypatch.delenv("DB_ENCRYPTION_KEY", raising=False)
    config.validate_production_settings(prod_settings())


def test_dev_settings_are_not_blocked() -> None:
    s = SimpleNamespace(
        ENV="dev", ALLOWED_ORIGINS="", JWT_SECRET="",
        JWT_ALGORITHM="HS256", METRICS_TOKEN="",
    )
    config.validate_production_settings(s)
    assert config.parse_allowed_origins(s) == []


def test_system_key_permission_check_fails_closed(monkeypatch) -> None:
    """权限库不可读时不得默认放行系统 Key。"""
    import backend.services.auth_service.db as auth_db
    from backend.shared.db import model_config_db

    def _boom(*args, **kwargs):
        raise OSError("db unavailable")

    monkeypatch.setattr(auth_db, "get_user_system_access", _boom)
    assert model_config_db._check_user_system_access("user-1") is False


def test_encryption_fails_closed_in_prod(monkeypatch) -> None:
    """prod 缺密钥时禁止把凭据以明文写入数据库。"""
    monkeypatch.setattr(crypto_utils, "_get_fernet", lambda: None)
    monkeypatch.setenv("ENV", "prod")
    with pytest.raises(RuntimeError, match="明文"):
        crypto_utils.encrypt_api_key("secret-value")
    monkeypatch.setenv("ENV", "dev")
    assert crypto_utils.encrypt_api_key("secret-value") == "secret-value"


def test_decrypt_failure_does_not_return_ciphertext(monkeypatch) -> None:
    """解密失败必须返回空值，不能把密文当明文交给调用方。"""
    monkeypatch.setattr(crypto_utils, "_get_fernet", lambda: object())
    assert crypto_utils.decrypt_api_key("gAAAAA-ciphertext") == ""
