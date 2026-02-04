"""Tests for v3 role-based directory isolation."""

import importlib
import sys
import pytest
from pydantic import ValidationError


def _reload_config():
    """Force reload the config module to pick up new env vars."""
    if "openrecall.shared.config" in sys.modules:
        del sys.modules["openrecall.shared.config"]
    import openrecall.shared.config

    return openrecall.shared.config


class TestRoleValidation:
    def test_settings_requires_role(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OPENRECALL_ROLE", raising=False)
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))

        with pytest.raises((ValueError, ValidationError), match="(?i)OPENRECALL_ROLE"):
            _reload_config()

    def test_settings_rejects_invalid_role(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENRECALL_ROLE", "invalid_role")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))

        with pytest.raises((ValueError, ValidationError), match="(?i)role"):
            _reload_config()


class TestServerRoleIsolation:
    def test_server_role_does_not_touch_client_paths(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "server")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        config = _reload_config()
        s = config.settings

        assert server_dir.exists(), "Server data dir should be created"
        assert not client_dir.exists(), (
            "Client data dir should NOT be created by server role"
        )

    def test_server_role_accessing_buffer_path_fails(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "server")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        config = _reload_config()
        s = config.settings

        with pytest.raises(ValueError, match="(?i)client|role|buffer"):
            _ = s.buffer_path

    def test_server_role_accessing_client_screenshots_fails(
        self, monkeypatch, tmp_path
    ):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "server")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        config = _reload_config()
        s = config.settings

        with pytest.raises(ValueError, match="(?i)client|role"):
            _ = s.client_screenshots_path


class TestClientRoleIsolation:
    def test_client_role_does_not_touch_server_paths(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "client")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        config = _reload_config()
        s = config.settings

        assert client_dir.exists(), "Client data dir should be created"
        assert not server_dir.exists(), (
            "Server data dir should NOT be created by client role"
        )

    def test_client_role_accessing_db_path_fails(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "client")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        config = _reload_config()
        s = config.settings

        with pytest.raises(ValueError, match="(?i)server|role|db"):
            _ = s.db_path

    def test_client_role_accessing_screenshots_path_fails(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "client")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        config = _reload_config()
        s = config.settings

        with pytest.raises(ValueError, match="(?i)server|role"):
            _ = s.screenshots_path


class TestCombinedRoleAccess:
    def test_combined_role_creates_both_directories(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "combined")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        config = _reload_config()
        s = config.settings

        assert server_dir.exists(), "Server data dir should be created"
        assert client_dir.exists(), "Client data dir should be created"

    def test_combined_role_can_access_all_paths(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "combined")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        config = _reload_config()
        s = config.settings

        assert s.db_path is not None
        assert s.fts_path is not None
        assert s.lancedb_path is not None
        assert s.screenshots_path is not None
        assert s.buffer_path is not None
        assert s.client_screenshots_path is not None
        assert s.model_cache_path is not None
        assert s.cache_path is not None
        assert s.client_cache_path is not None


class TestClientCachePath:
    def test_client_role_can_access_client_cache_path(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "client")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        config = _reload_config()
        s = config.settings

        assert s.client_cache_path == client_dir / "cache"

    def test_client_role_cannot_access_server_cache_path(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "client")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        config = _reload_config()
        s = config.settings

        with pytest.raises(ValueError, match="(?i)server|role|cache"):
            _ = s.cache_path

    def test_server_role_cannot_access_client_cache_path(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "server")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        config = _reload_config()
        s = config.settings

        with pytest.raises(ValueError, match="(?i)client|role"):
            _ = s.client_cache_path

    def test_client_main_imports_without_error(self, monkeypatch, tmp_path):
        server_dir = tmp_path / "server"
        client_dir = tmp_path / "client"

        monkeypatch.setenv("OPENRECALL_ROLE", "client")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

        _reload_config()

        if "openrecall.client.__main__" in sys.modules:
            del sys.modules["openrecall.client.__main__"]

        from openrecall.client.__main__ import main

        assert callable(main)
