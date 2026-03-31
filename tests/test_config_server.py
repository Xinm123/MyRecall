import pytest
from pathlib import Path

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


def test_server_settings_ocr_defaults():
    """OCR settings should have correct defaults."""
    settings = ServerSettings._from_dict({})
    assert settings.ocr_provider == "rapidocr"
    assert settings.ocr_rapid_version == "PP-OCRv4"
    assert settings.ocr_model_type == "mobile"


def test_server_settings_paths():
    """Path fields should be Path objects."""
    settings = ServerSettings._from_dict({})
    assert isinstance(settings.paths_data_dir, Path)
    assert isinstance(settings.paths_cache_dir, Path)


def test_server_settings_from_nested_dict():
    """Nested TOML structure should be flattened correctly."""
    data = {
        "server.host": "192.168.1.1",
        "server.port": 9000,
        "ai.provider": "dashscope",
        "ocr.rapid_version": "PP-OCRv5",
    }
    settings = ServerSettings._from_dict(data)
    assert settings.server_host == "192.168.1.1"
    assert settings.server_port == 9000
    assert settings.ai_provider == "dashscope"
    assert settings.ocr_rapid_version == "PP-OCRv5"
