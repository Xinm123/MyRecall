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
    import tempfile, os

    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('value = "from_file"')
        path = f.name
    try:
        config = ConcreteConfig.from_toml(path)
        assert config.value == "from_file"
    finally:
        os.unlink(path)
