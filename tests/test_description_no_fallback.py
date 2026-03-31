"""Test that description provider has no fallback to [ai] settings."""
import tempfile
from pathlib import Path

from openrecall.server.config_server import ServerSettings


def test_description_no_fallback_to_ai():
    """Description provider must NOT fallback to [ai] settings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "server.toml"

        # Config with different [ai] and [description] settings
        config_path.write_text("""
[server]
host = "0.0.0.0"
port = 8083

[ai]
provider = "openai"
model_name = "gpt-4"
api_key = "ai-key-123"
api_base = "https://api.openai.com/v1"

[description]
enabled = true
provider = "dashscope"
model = "qwen-vl"
api_key = "desc-key-456"
api_base = "https://dashscope.aliyuncs.com/api/v1"
""")

        settings = ServerSettings.from_toml(config_path)

        # Verify [description] settings are independent
        assert settings.description_provider == "dashscope", "Should use [description] provider, not [ai]"
        assert settings.description_model == "qwen-vl", "Should use [description] model, not [ai]"
        assert settings.description_api_key == "desc-key-456", "Should use [description] api_key, not [ai]"
        assert settings.description_api_base == "https://dashscope.aliyuncs.com/api/v1", "Should use [description] api_base, not [ai]"

        # Verify [ai] settings are different
        assert settings.ai_provider == "openai"
        assert settings.ai_model_name == "gpt-4"
        assert settings.ai_api_key == "ai-key-123"
        assert settings.ai_api_base == "https://api.openai.com/v1"


def test_description_defaults_to_local():
    """When [description] section is missing, defaults to 'local' provider."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "server.toml"

        # Config WITHOUT [description] section
        config_path.write_text("""
[server]
host = "0.0.0.0"
port = 8083

[ai]
provider = "openai"
api_key = "ai-key-123"
""")

        settings = ServerSettings.from_toml(config_path)

        # Verify description defaults to 'local', not fallback to 'openai'
        assert settings.description_enabled is True
        assert settings.description_provider == "local", "Should default to 'local', not fallback to [ai]"
        assert settings.description_model == ""
        assert settings.description_api_key == ""


def test_description_uses_local_when_provider_empty():
    """When description.provider is explicitly set to empty string in TOML,
    the config stores empty string, but factory defaults to 'local' at runtime."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "server.toml"

        config_path.write_text("""
[description]
enabled = true
provider = ""
""")

        settings = ServerSettings.from_toml(config_path)

        # Config stores the empty string from TOML
        assert settings.description_provider == "", "TOML empty string is preserved in config"

        # But factory will default to 'local' when provider is empty
        # (tested in factory tests, not config tests)
