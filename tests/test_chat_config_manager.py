import json  # noqa: F401
import os  # noqa: F401

import pytest  # noqa: F401

from openrecall.client.chat.config_manager import (
    AUTH_JSON,  # noqa: F401
    PROVIDER_ENV_MAP,
    get_api_key,
    get_default_model,
    get_default_provider,
    validate_pi_config,
)


def test_get_default_provider():
    assert get_default_provider() == "qianfan"


def test_get_default_model():
    assert get_default_model() == "glm-5"


def test_get_api_key_from_env_var(monkeypatch):
    """get_api_key reads from environment variable."""
    monkeypatch.setenv("MINIMAX_CN_API_KEY", "sk-test-minimax")
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    assert get_api_key("minimax-cn") == "sk-test-minimax"


def test_get_api_key_kimi_from_env_var(monkeypatch):
    """get_api_key reads KIMI_API_KEY for kimi-coding provider."""
    monkeypatch.setenv("KIMI_API_KEY", "sk-test-kimi")
    monkeypatch.delenv("MINIMAX_CN_API_KEY", raising=False)
    assert get_api_key("kimi-coding") == "sk-test-kimi"


def test_get_api_key_falls_back_to_auth_json(tmp_path, monkeypatch):
    """get_api_key falls back to auth.json when env var not set."""
    import openrecall.client.chat.config_manager as cm

    monkeypatch.setattr(cm, "AUTH_JSON", tmp_path / "auth.json")
    monkeypatch.delenv("MINIMAX_CN_API_KEY", raising=False)
    (tmp_path / "auth.json").write_text(
        '{"minimax-cn": {"type": "api_key", "key": "sk-from-auth"}}'
    )
    assert get_api_key("minimax-cn") == "sk-from-auth"


def test_validate_pi_config_is_noop():
    """validate_pi_config is a no-op stub in Phase 1."""
    # Should not raise, should not write anything
    validate_pi_config("minimax-cn", "MiniMax-M2.7", "sk-test")
    validate_pi_config("kimi-coding", "k2p5", "sk-test")


def test_provider_env_map():
    """PROVIDER_ENV_MAP contains expected mappings."""
    assert PROVIDER_ENV_MAP["minimax-cn"] == "MINIMAX_CN_API_KEY"
    assert PROVIDER_ENV_MAP["kimi-coding"] == "KIMI_API_KEY"
    assert PROVIDER_ENV_MAP["anthropic"] == "ANTHROPIC_API_KEY"
    assert PROVIDER_ENV_MAP["openai"] == "OPENAI_API_KEY"
    assert PROVIDER_ENV_MAP["qianfan"] == "QIANFAN_API_KEY"
