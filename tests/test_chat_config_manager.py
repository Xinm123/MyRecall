import json  # noqa: F401
import os  # noqa: F401

import pytest  # noqa: F401

from openrecall.client.chat.config_manager import (
    AUTH_JSON,  # noqa: F401
    PROVIDER_ENV_MAP,
    SUPPORTED_PROVIDERS,
    get_api_key,
    get_default_model,
    get_default_provider,
    get_user_provider,
    get_user_model,
    get_provider_info,
    save_api_key,
    save_user_choice,
    get_current_config,
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


def test_save_api_key(tmp_path, monkeypatch):
    """save_api_key writes to auth.json with merge."""
    import openrecall.client.chat.config_manager as cm

    monkeypatch.setattr(cm, "AUTH_JSON", tmp_path / "auth.json")
    monkeypatch.setattr(cm, "PI_CONFIG_DIR", tmp_path)

    # Create initial auth.json
    (tmp_path / "auth.json").write_text('{"existing-provider": {"type": "api_key", "key": "existing-key"}}')

    # Save new key
    save_api_key("minimax-cn", "sk-new-key")

    # Verify merge
    data = json.loads((tmp_path / "auth.json").read_text())
    assert data["minimax-cn"]["key"] == "sk-new-key"
    assert data["existing-provider"]["key"] == "existing-key"  # Preserved


def test_save_user_choice(tmp_path, monkeypatch):
    """save_user_choice persists provider/model to myrecall-config.json."""
    import openrecall.client.chat.config_manager as cm

    monkeypatch.setattr(cm, "MYRECALL_CONFIG", tmp_path / "myrecall-config.json")
    monkeypatch.setattr(cm, "PI_CONFIG_DIR", tmp_path)

    save_user_choice("minimax-cn", "MiniMax-M2.7")

    data = json.loads((tmp_path / "myrecall-config.json").read_text())
    assert data["provider"] == "minimax-cn"
    assert data["model"] == "MiniMax-M2.7"


def test_get_user_provider_defaults(tmp_path, monkeypatch):
    """get_user_provider returns default when no config exists."""
    import openrecall.client.chat.config_manager as cm

    monkeypatch.setattr(cm, "MYRECALL_CONFIG", tmp_path / "nonexistent.json")
    assert get_user_provider() == "qianfan"


def test_get_provider_info():
    """get_provider_info returns provider details."""
    info = get_provider_info("qianfan")
    assert info is not None
    assert info["id"] == "qianfan"
    assert "models" in info

    assert get_provider_info("nonexistent") is None


def test_supported_providers_structure():
    """SUPPORTED_PROVIDERS has expected structure."""
    assert len(SUPPORTED_PROVIDERS) == 4

    for p in SUPPORTED_PROVIDERS:
        assert "id" in p
        assert "name" in p
        assert "url" in p
        assert "api_base" in p
        assert "models" in p
        assert len(p["models"]) > 0

        for m in p["models"]:
            assert "id" in m
            assert "name" in m


def test_provider_env_map():
    """PROVIDER_ENV_MAP contains expected mappings."""
    assert PROVIDER_ENV_MAP["minimax-cn"] == "MINIMAX_CN_API_KEY"
    assert PROVIDER_ENV_MAP["kimi-coding"] == "KIMI_API_KEY"
    assert PROVIDER_ENV_MAP["anthropic"] == "ANTHROPIC_API_KEY"
    assert PROVIDER_ENV_MAP["openai"] == "OPENAI_API_KEY"
    assert PROVIDER_ENV_MAP["qianfan"] == "QIANFAN_API_KEY"
