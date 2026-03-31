import pytest
from openrecall.server.config_server import ServerSettings


def test_server_settings_defaults():
    """ServerSettings should have correct defaults."""
    settings = ServerSettings._from_dict({})
    assert settings.server_host == "0.0.0.0"
    assert settings.server_port == 8083
    assert settings.ai_provider == "local"
    assert settings.ai_device == "cpu"


def test_server_settings_from_dict():
    """ServerSettings should parse flat dict correctly."""
    data = {
        "server.host": "127.0.0.1",
        "server.port": 9000,
        "ai.provider": "dashscope",
        "ai.device": "cuda",
    }
    settings = ServerSettings._from_dict(data)
    assert settings.server_host == "127.0.0.1"
    assert settings.server_port == 9000
    assert settings.ai_provider == "dashscope"
    assert settings.ai_device == "cuda"
