"""Integration tests for TOML-based configuration system.

Tests config precedence, singleton replacement, and backward-compatible aliases.
Run with: pytest tests/test_config_integration.py -v
"""

import os
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


class TestServerSettingsAliases:
    """Verify backward-compatible aliases exist on ServerSettings."""

    def test_device_alias(self):
        """settings.device should alias ai_device."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({"ai.device": "cuda"})
        assert settings.device == "cuda"
        assert settings.ai_device == "cuda"

    def test_host_alias(self):
        """settings.host should alias server_host."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({"server.host": "127.0.0.1"})
        assert settings.host == "127.0.0.1"
        assert settings.server_host == "127.0.0.1"

    def test_port_alias(self):
        """settings.port should alias server_port."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({"server.port": 9000})
        assert settings.port == 9000
        assert settings.server_port == 9000

    def test_debug_alias(self):
        """settings.debug should alias server_debug."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({"server.debug": True})
        assert settings.debug is True
        assert settings.server_debug is True

    def test_preload_models_alias(self):
        """settings.preload_models should alias processing_preload_models."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({"processing.preload_models": False})
        assert settings.preload_models is False
        assert settings.processing_preload_models is False

    def test_base_path_alias(self):
        """settings.base_path should alias paths_data_dir."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({})
        assert settings.base_path == settings.paths_data_dir

    def test_db_path(self):
        """settings.db_path should be computed."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({})
        assert settings.db_path == settings.paths_data_dir / "db" / "edge.db"

    def test_fts_path(self):
        """settings.fts_path should be computed."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({})
        assert settings.fts_path == settings.paths_data_dir / "fts.db"

    def test_frames_dir(self):
        """settings.frames_dir should be computed."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({})
        assert settings.frames_dir == settings.paths_data_dir / "frames"

    def test_cache_path(self):
        """settings.cache_path should alias paths_cache_dir."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({})
        assert settings.cache_path == settings.paths_cache_dir

    def test_model_cache_path(self):
        """settings.model_cache_path should be computed."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({})
        assert settings.model_cache_path == settings.paths_data_dir / "models"

    def test_screenshots_path(self):
        """settings.screenshots_path should be computed."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({})
        assert settings.screenshots_path == settings.paths_data_dir / "screenshots"


class TestClientSettingsAliases:
    """Verify backward-compatible aliases exist on ClientSettings."""

    def test_debug_alias(self):
        """settings.debug should alias client_debug."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict({"client.debug": True})
        assert settings.debug is True

    def test_buffer_path_alias(self):
        """settings.buffer_path should alias paths_buffer_dir."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict({})
        assert settings.buffer_path == settings.paths_buffer_dir

    def test_cache_path_alias(self):
        """settings.cache_path should be computed."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict({})
        assert settings.cache_path == settings.paths_data_dir / "cache"

    def test_api_url_alias(self):
        """settings.api_url should alias server_api_url."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict(
            {"server.api_url": "http://custom:8083/api"}
        )
        assert settings.api_url == "http://custom:8083/api"

    def test_upload_timeout_alias(self):
        """settings.upload_timeout should alias server_upload_timeout."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict({"server.upload_timeout": 300})
        assert settings.upload_timeout == 300

    def test_click_debounce_alias(self):
        """settings.click_debounce_ms should alias debounce_click_ms."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict({"debounce.click_ms": 5000})
        assert settings.click_debounce_ms == 5000

    def test_trigger_debounce_alias(self):
        """settings.trigger_debounce_ms should alias debounce_trigger_ms."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict({"debounce.trigger_ms": 4000})
        assert settings.trigger_debounce_ms == 4000

    def test_capture_debounce_alias(self):
        """settings.capture_debounce_ms should alias debounce_capture_ms."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict({"debounce.capture_ms": 2000})
        assert settings.capture_debounce_ms == 2000

    def test_idle_capture_interval_alias(self):
        """settings.idle_capture_interval_ms should alias debounce_idle_interval_ms."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict({"debounce.idle_interval_ms": 30000})
        assert settings.idle_capture_interval_ms == 30000

    def test_primary_monitor_only_alias(self):
        """settings.primary_monitor_only should alias capture_primary_monitor_only."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict({"capture.primary_monitor_only": False})
        assert settings.primary_monitor_only is False

    def test_client_web_enabled_alias(self):
        """settings.client_web_enabled should alias ui_web_enabled."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict({"ui.web_enabled": False})
        assert settings.client_web_enabled is False

    def test_simhash_enabled_aliases(self):
        """simhash enabled flags should alias dedup flags."""
        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings._from_dict(
            {
                "dedup.for_click": False,
                "dedup.for_app_switch": True,
            }
        )
        assert settings.simhash_enabled_for_click is False
        assert settings.simhash_enabled_for_app_switch is True


class TestOCRParams:
    """OCR params should be loaded correctly from TOML."""

    def test_ocr_rapid_use_local_property(self):
        """ocr_rapid_use_local should be True when provider is rapidocr."""
        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings._from_dict({"ocr.provider": "rapidocr"})
        assert settings.ocr_rapid_use_local is True

        settings2 = ServerSettings._from_dict({"ocr.provider": "dashscope"})
        assert settings2.ocr_rapid_use_local is False


class TestConfigPrecedence:
    """Test config file loading precedence."""

    def test_server_from_toml_file(self, tmp_path):
        """ServerSettings.from_toml should load from file."""
        toml_content = """
[server]
host = "192.168.1.100"
port = 9999
debug = true

[ai]
provider = "dashscope"
device = "cuda"
"""
        toml_file = tmp_path / "test_server.toml"
        toml_file.write_text(toml_content)

        from openrecall.server.config_server import ServerSettings

        settings = ServerSettings.from_toml(str(toml_file))
        assert settings.server_host == "192.168.1.100"
        assert settings.server_port == 9999
        assert settings.server_debug is True
        assert settings.ai_provider == "dashscope"
        assert settings.ai_device == "cuda"

    def test_client_from_toml_file(self, tmp_path):
        """ClientSettings.from_toml should load from file."""
        toml_content = """
[server]
api_url = "http://192.168.1.100:9999/api"

[debounce]
click_ms = 7777
"""
        toml_file = tmp_path / "test_client.toml"
        toml_file.write_text(toml_content)

        from openrecall.client.config_client import ClientSettings

        settings = ClientSettings.from_toml(str(toml_file))
        assert settings.server_api_url == "http://192.168.1.100:9999/api"
        assert settings.debounce_click_ms == 7777

    def test_server_default_path_uses_home(self):
        """ServerSettings should use ~/.myrecall/server.toml as default."""
        from openrecall.server.config_server import ServerSettings

        assert ServerSettings._default_filename() == "server.toml"

    def test_client_default_path_uses_home(self):
        """ClientSettings should use ~/.myrecall/client.toml as default."""
        from openrecall.client.config_client import ClientSettings

        assert ClientSettings._default_filename() == "client.toml"


class TestSingletonReplacement:
    """Test that __main__.py correctly replaces the global singleton."""

    def test_server_singleton_replaced(self):
        """After __main__ loads, openrecall.shared.config.settings should be ServerSettings."""
        import openrecall.shared.config

        original = openrecall.shared.config.settings

        from openrecall.server.config_server import ServerSettings

        new_settings = ServerSettings._from_dict({})
        openrecall.shared.config.settings = new_settings

        try:
            assert openrecall.shared.config.settings.server_host == "0.0.0.0"
            assert openrecall.shared.config.settings.port == 8083
            assert openrecall.shared.config.settings.device == "cpu"
            assert openrecall.shared.config.settings.debug is False
        finally:
            openrecall.shared.config.settings = original

    def test_client_singleton_replaced(self):
        """After __main__ loads, openrecall.shared.config.settings should be ClientSettings."""
        import openrecall.shared.config

        original = openrecall.shared.config.settings

        from openrecall.client.config_client import ClientSettings

        new_settings = ClientSettings._from_dict({})
        openrecall.shared.config.settings = new_settings

        try:
            assert openrecall.shared.config.settings.debug is False
            assert (
                openrecall.shared.config.settings.api_url == "http://localhost:8083/api"
            )
            assert openrecall.shared.config.settings.click_debounce_ms == 3000
        finally:
            openrecall.shared.config.settings = original
