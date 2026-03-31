import pytest
from openrecall.client.config_client import ClientSettings


def test_client_settings_defaults():
    """ClientSettings should have correct defaults."""
    settings = ClientSettings._from_dict({})
    assert settings.server_api_url == "http://localhost:8083/api"
    assert settings.debounce_click_ms == 3000
    assert settings.dedup_enabled == True
    assert settings.dedup_threshold == 10


def test_client_settings_from_dict():
    """ClientSettings should parse flat dict correctly."""
    data = {
        "server.api_url": "http://192.168.1.100:8083/api",
        "debounce.click_ms": 5000,
        "dedup.enabled": False,
    }
    settings = ClientSettings._from_dict(data)
    assert settings.server_api_url == "http://192.168.1.100:8083/api"
    assert settings.debounce_click_ms == 5000
    assert settings.dedup_enabled == False


def test_client_settings_debounce_defaults():
    """Debounce settings should have correct defaults."""
    settings = ClientSettings._from_dict({})
    assert settings.debounce_click_ms == 3000
    assert settings.debounce_trigger_ms == 3000
    assert settings.debounce_capture_ms == 3000
    assert settings.debounce_idle_interval_ms == 60000


def test_client_settings_from_nested_dict():
    """Nested TOML structure should be flattened correctly."""
    data = {
        "server.api_url": "http://192.168.1.100:8083/api",
        "dedup.enabled": False,
        "dedup.threshold": 5,
        "dedup.for_click": False,
    }
    settings = ClientSettings._from_dict(data)
    assert settings.server_api_url == "http://192.168.1.100:8083/api"
    assert settings.dedup_enabled == False
    assert settings.dedup_threshold == 5
    assert settings.dedup_for_click == False
    # Defaults preserved
    assert settings.debounce_click_ms == 3000
