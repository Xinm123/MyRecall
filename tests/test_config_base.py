from __future__ import annotations

import os
import tempfile

import pytest
from dataclasses import dataclass
from openrecall.shared.config_base import TOMLConfig


@dataclass
class ConcreteConfig(TOMLConfig):
    @classmethod
    def _default_filename(cls) -> str:
        return "test.toml"

    @classmethod
    def _from_dict(cls, data: dict) -> "ConcreteConfig":
        return cls(value=data.get("value", "default"))

    value: str = "default"


def test_load_from_missing_file_uses_defaults():
    """Missing config file should return defaults."""
    config = ConcreteConfig.from_toml("/nonexistent/path.toml")
    assert config.value == "default"


def test_load_from_existing_file():
    """Existing TOML file should override defaults."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('value = "from_file"')
        path = f.name
    try:
        config = ConcreteConfig.from_toml(path)
        assert config.value == "from_file"
    finally:
        os.unlink(path)


def test_flatten_dict_nested():
    """Nested TOML structure should flatten to dot-notation keys."""
    result = ConcreteConfig._flatten_dict(
        {"server": {"host": "0.0.0.0", "port": 8083}, "ai": {"provider": "local"}}
    )
    assert result == {
        "server.host": "0.0.0.0",
        "server.port": 8083,
        "ai.provider": "local",
    }


def test_env_var_fallback(monkeypatch, tmp_path):
    """OPENRECALL_CONFIG_PATH env var should be used."""
    config_file = tmp_path / "server.toml"
    config_file.write_text('value = "from_env"')
    monkeypatch.setenv("OPENRECALL_CONFIG_PATH", str(config_file))

    config = ConcreteConfig.from_toml()
    assert config.value == "from_env"


def test_home_dir_fallback(monkeypatch, tmp_path):
    """~/.myrecall/<filename> should be used as fallback."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    myrecall_dir = home / ".myrecall"
    myrecall_dir.mkdir()
    config_file = myrecall_dir / "test.toml"
    config_file.write_text('value = "from_home"')

    config = ConcreteConfig.from_toml()
    assert config.value == "from_home"
