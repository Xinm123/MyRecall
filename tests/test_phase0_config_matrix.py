"""Tests for Phase 0 configuration matrix (4 deployment modes)."""

import os
import importlib

import pytest


class TestDeploymentMode:
    def test_local_defaults(self, tmp_path, monkeypatch):
        """Default deployment mode is 'local'."""
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)
        s = openrecall.shared.config.Settings()

        assert s.deployment_mode == "local"
        assert s.host == "127.0.0.1"

    def test_no_mode_defaults_to_local(self, tmp_path, monkeypatch):
        """F-04: Unset DEPLOYMENT_MODE -> defaults to 'local'."""
        monkeypatch.delenv("OPENRECALL_DEPLOYMENT_MODE", raising=False)
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)
        s = openrecall.shared.config.Settings()

        assert s.deployment_mode == "local"

    def test_deployment_mode_set_via_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENRECALL_DEPLOYMENT_MODE", "debian_server")
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)
        s = openrecall.shared.config.Settings()

        assert s.deployment_mode == "debian_server"


class TestConfigPresets:
    def test_get_preset_local(self):
        from openrecall.shared.config_presets import get_preset
        preset = get_preset("local")
        assert preset["host"] == "127.0.0.1"
        assert preset["runs_server"] is True
        assert preset["runs_client"] is True

    def test_get_preset_debian_server(self):
        from openrecall.shared.config_presets import get_preset
        preset = get_preset("debian_server")
        assert preset["host"] == "0.0.0.0"
        assert preset["runs_server"] is True
        assert preset["runs_client"] is False

    def test_get_preset_debian_client(self):
        from openrecall.shared.config_presets import get_preset
        preset = get_preset("debian_client")
        assert preset["runs_server"] is False
        assert preset["runs_client"] is True

    def test_get_preset_remote(self):
        from openrecall.shared.config_presets import get_preset
        preset = get_preset("remote")
        assert preset["runs_server"] is True
        assert preset["runs_client"] is True

    def test_invalid_mode_raises(self):
        from openrecall.shared.config_presets import get_preset
        with pytest.raises(ValueError, match="Invalid deployment mode"):
            get_preset("invalid_mode")

    def test_all_four_modes_defined(self):
        from openrecall.shared.config_presets import VALID_MODES
        assert VALID_MODES == {"local", "remote", "debian_client", "debian_server"}


class TestEnvTemplates:
    def test_all_env_files_exist(self):
        """All 4 env template files exist."""
        from pathlib import Path
        config_dir = Path(__file__).resolve().parent.parent / "config"
        for mode in ["local", "remote", "debian_client", "debian_server"]:
            env_file = config_dir / f"{mode}.env"
            assert env_file.exists(), f"Missing env file: {env_file}"

    def test_env_files_contain_deployment_mode(self):
        """Each env file sets OPENRECALL_DEPLOYMENT_MODE."""
        from pathlib import Path
        config_dir = Path(__file__).resolve().parent.parent / "config"
        for mode in ["local", "remote", "debian_client", "debian_server"]:
            env_file = config_dir / f"{mode}.env"
            content = env_file.read_text()
            assert f"OPENRECALL_DEPLOYMENT_MODE={mode}" in content, (
                f"{env_file.name} missing OPENRECALL_DEPLOYMENT_MODE={mode}"
            )

    def test_debian_server_binds_all(self):
        """debian_server.env binds to 0.0.0.0."""
        from pathlib import Path
        config_dir = Path(__file__).resolve().parent.parent / "config"
        content = (config_dir / "debian_server.env").read_text()
        assert "OPENRECALL_HOST=0.0.0.0" in content
