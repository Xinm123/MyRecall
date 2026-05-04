"""Unit tests for server-side runtime_config hot-reload getters."""

import pytest
from pathlib import Path

import openrecall.server.runtime_config as rc
from openrecall.server.runtime_config import (
    init_runtime_config,
    get_description_provider,
    get_description_model,
    get_description_api_key,
    get_description_api_base,
    get_description_request_timeout,
    get_effective_description_settings,
)
from openrecall.server.config_server import ServerSettings


class TestRuntimeConfig:
    @pytest.fixture(autouse=True)
    def reset_singleton(self, tmp_path):
        """Reset module-level singletons before each test."""
        rc._settings_store = None
        rc._toml_settings = None
        yield
        rc._settings_store = None
        rc._toml_settings = None

    def test_sqlite_value_takes_priority(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_provider="dashscope")
        init_runtime_config(db_path, toml)
        rc._settings_store.set("description.provider", "openai")
        assert get_description_provider() == "openai"

    def test_toml_value_when_sqlite_empty(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_provider="dashscope")
        init_runtime_config(db_path, toml)
        assert get_description_provider() == "dashscope"

    def test_hardcoded_default_when_both_empty(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_provider="local")
        init_runtime_config(db_path, toml)
        assert get_description_provider() == "local"

    def test_get_effective_returns_source_tags(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(
            description_provider="dashscope",  # differs from default "local"
            description_model="qwen-vl-max",
            description_api_key="",
            description_api_base="",
        )
        init_runtime_config(db_path, toml)
        rc._settings_store.set("description.provider", "openai")
        result = get_effective_description_settings()
        assert result["provider"] == "openai"
        assert result["source"]["provider"] == "sqlite"
        assert result["source"]["model"] == "toml"  # toml differs from default ""
        assert result["source"]["api_key"] == "default"  # toml "" == default ""

    def test_init_is_idempotent(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_provider="openai")
        init_runtime_config(db_path, toml)
        init_runtime_config(db_path, toml)
        assert get_description_provider() == "openai"

    def test_defaults_consistency(self):
        """ServerSettingsStore.DEFAULTS must match ServerSettings defaults (string-coerced)."""
        from openrecall.server.database.settings_store import ServerSettingsStore

        store_defaults = ServerSettingsStore.DEFAULTS
        toml = ServerSettings()
        assert str(toml.description_provider) == store_defaults["description.provider"]
        assert str(toml.description_model) == store_defaults["description.model"]
        assert str(toml.description_api_key) == store_defaults["description.api_key"]
        assert str(toml.description_api_base) == store_defaults["description.api_base"]
        # description_request_timeout may not exist on ServerSettings yet (Task 3)
        # Use getattr with fallback to avoid AttributeError
        toml_timeout = getattr(toml, "description_request_timeout", 120)
        assert str(toml_timeout) == store_defaults["description.request_timeout"]

    def test_timeout_int_coercion(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_request_timeout=120)
        init_runtime_config(db_path, toml)
        assert get_description_request_timeout() == 120
        rc._settings_store.set("description.request_timeout", "60")
        assert get_description_request_timeout() == 60

    def test_uninitialized_raises(self):
        """Calling getters before init_runtime_config should raise RuntimeError."""
        rc._settings_store = None
        rc._toml_settings = None
        with pytest.raises(RuntimeError, match="runtime_config not initialized"):
            get_description_provider()

    def test_source_tag_sqlite(self, tmp_path):
        """Source tag should be 'sqlite' when value comes from SQLite."""
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_provider="dashscope")
        init_runtime_config(db_path, toml)
        rc._settings_store.set("description.provider", "openai")
        result = get_effective_description_settings()
        assert result["source"]["provider"] == "sqlite"

    def test_source_tag_toml(self, tmp_path):
        """Source tag should be 'toml' when value differs from default."""
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_provider="dashscope")
        init_runtime_config(db_path, toml)
        result = get_effective_description_settings()
        assert result["source"]["provider"] == "toml"

    def test_source_tag_default(self, tmp_path):
        """Source tag should be 'default' when toml value matches default."""
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_provider="local")
        init_runtime_config(db_path, toml)
        result = get_effective_description_settings()
        assert result["source"]["provider"] == "default"

    def test_timeout_invalid_fallback(self, tmp_path):
        """Invalid timeout string should fall back to 120."""
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_request_timeout=120)
        init_runtime_config(db_path, toml)
        rc._settings_store.set("description.request_timeout", "not-a-number")
        assert get_description_request_timeout() == 120

    def test_api_key_not_masked_in_effective_settings(self, tmp_path):
        """api_key in effective settings should NOT be masked — masking is API layer responsibility."""
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_api_key="sk-1234567890XX12")
        init_runtime_config(db_path, toml)
        result = get_effective_description_settings()
        assert result["api_key"] == "sk-1234567890XX12"
