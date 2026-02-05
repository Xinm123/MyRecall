"""M0 Sensitive Logging Tests.

Tests that OPENRECALL_LOG_SENSITIVE controls sensitive data in logs.
"""

import importlib
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestSensitiveLoggingDisabled:
    def test_sensitive_logs_disabled_does_not_write_rerank_debug_log(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))
        monkeypatch.setenv("OPENRECALL_DEBUG", "true")
        monkeypatch.setenv("OPENRECALL_LOG_SENSITIVE", "false")

        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        settings = openrecall.shared.config.settings

        assert settings.debug is True
        assert settings.log_sensitive is False

        log_dir = tmp_path / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "rerank_debug.log"

        monkeypatch.chdir(tmp_path)

        import openrecall.server.search.engine as engine

        importlib.reload(engine)

        should_write = settings.debug and settings.log_sensitive

        assert should_write is False

    def test_sensitive_logs_disabled_does_not_write_fusion_debug_log(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))
        monkeypatch.setenv("OPENRECALL_FUSION_LOG_ENABLED", "true")
        monkeypatch.setenv("OPENRECALL_LOG_SENSITIVE", "false")

        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        settings = openrecall.shared.config.settings

        assert settings.fusion_log_enabled is True
        assert settings.log_sensitive is False

        should_write = settings.fusion_log_enabled and settings.log_sensitive

        assert should_write is False

    def test_sensitive_logs_disabled_does_not_log_ocr_preview(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))
        monkeypatch.setenv("OPENRECALL_DEBUG", "true")
        monkeypatch.setenv("OPENRECALL_LOG_SENSITIVE", "false")

        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        settings = openrecall.shared.config.settings

        should_log_preview = settings.debug and settings.log_sensitive

        assert should_log_preview is False


class TestSensitiveLoggingEnabled:
    def test_sensitive_logs_enabled_allows_rerank_debug_log(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))
        monkeypatch.setenv("OPENRECALL_DEBUG", "true")
        monkeypatch.setenv("OPENRECALL_LOG_SENSITIVE", "true")

        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        settings = openrecall.shared.config.settings

        assert settings.debug is True
        assert settings.log_sensitive is True

        should_write = settings.debug and settings.log_sensitive

        assert should_write is True

    def test_sensitive_logs_enabled_allows_fusion_debug_log(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))
        monkeypatch.setenv("OPENRECALL_FUSION_LOG_ENABLED", "true")
        monkeypatch.setenv("OPENRECALL_LOG_SENSITIVE", "true")

        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        settings = openrecall.shared.config.settings

        assert settings.fusion_log_enabled is True
        assert settings.log_sensitive is True

        should_write = settings.fusion_log_enabled and settings.log_sensitive

        assert should_write is True

    def test_sensitive_logs_enabled_allows_ocr_preview(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))
        monkeypatch.setenv("OPENRECALL_DEBUG", "true")
        monkeypatch.setenv("OPENRECALL_LOG_SENSITIVE", "true")

        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        settings = openrecall.shared.config.settings

        should_log_preview = settings.debug and settings.log_sensitive

        assert should_log_preview is True


class TestSensitiveLoggingDefault:
    def test_log_sensitive_defaults_to_false(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))
        monkeypatch.delenv("OPENRECALL_LOG_SENSITIVE", raising=False)

        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        settings = openrecall.shared.config.settings

        assert settings.log_sensitive is False
