"""Unit tests for runtime_config hot-reload getters."""
import threading
import time

import pytest

from openrecall.client import runtime_config
from openrecall.client.database import ClientSettingsStore


@pytest.fixture
def fresh_runtime_config(tmp_path):
    """Initialize runtime_config with a fresh temp database."""
    db_dir = tmp_path / "client"
    db_dir.mkdir()
    runtime_config.init_runtime_config(db_dir)
    yield runtime_config
    # Reset global state between tests
    runtime_config._settings_store = None
    runtime_config._data_dir = None
    # Reset the config change event
    runtime_config._config_change_event.clear()


# ---------------------------------------------------------------------------
# Dedup getter defaults (fall back to TOML / ClientSettingsStore.DEFAULTS)
# ---------------------------------------------------------------------------

def test_get_dedup_enabled_default(fresh_runtime_config):
    """Should fall back to TOML / settings store default (True)."""
    assert fresh_runtime_config.get_dedup_enabled() is True


def test_get_dedup_threshold_default(fresh_runtime_config):
    assert fresh_runtime_config.get_dedup_threshold() == 10


def test_get_dedup_ttl_seconds_default(fresh_runtime_config):
    assert fresh_runtime_config.get_dedup_ttl_seconds() == 60.0


def test_get_dedup_cache_size_default(fresh_runtime_config):
    assert fresh_runtime_config.get_dedup_cache_size() == 1


def test_get_dedup_for_click_default(fresh_runtime_config):
    assert fresh_runtime_config.get_dedup_for_click() is True


def test_get_dedup_for_app_switch_default(fresh_runtime_config):
    assert fresh_runtime_config.get_dedup_for_app_switch() is False


def test_get_dedup_force_after_skip_sec_default(fresh_runtime_config):
    assert fresh_runtime_config.get_dedup_force_after_skip_sec() == 30


# ---------------------------------------------------------------------------
# Dedup getter overrides (SQLite takes priority over TOML)
# ---------------------------------------------------------------------------

def test_get_dedup_enabled_overrides_toml(fresh_runtime_config):
    """SQLite value should take priority over TOML."""
    store = runtime_config._get_store()
    assert store is not None, "store should be initialized by fresh_runtime_config fixture"
    store.set("dedup.enabled", "false")
    assert fresh_runtime_config.get_dedup_enabled() is False


def test_get_dedup_threshold_overrides_toml(fresh_runtime_config):
    store = runtime_config._get_store()
    assert store is not None
    store.set("dedup.threshold", "25")
    assert fresh_runtime_config.get_dedup_threshold() == 25


def test_get_dedup_ttl_overrides_toml(fresh_runtime_config):
    store = runtime_config._get_store()
    assert store is not None
    store.set("dedup.ttl_seconds", "120.5")
    assert fresh_runtime_config.get_dedup_ttl_seconds() == 120.5


# ---------------------------------------------------------------------------
# wait / notify
# ---------------------------------------------------------------------------

def test_notify_and_wait_config_changed(fresh_runtime_config):
    """wait_for_config_change should unblock after notify_config_changed."""
    result = []

    def waiter():
        fresh_runtime_config.wait_for_config_change(timeout=2.0)
        result.append("done")

    t = threading.Thread(target=waiter)
    t.start()
    # Small delay to ensure waiter is blocking
    time.sleep(0.1)
    fresh_runtime_config.notify_config_changed()
    t.join(timeout=3.0)
    assert result == ["done"], f"Expected ['done'], got {result}"


def test_wait_for_config_change_timeout(fresh_runtime_config):
    """wait_for_config_change should return after timeout even without notify."""
    start = time.time()
    fresh_runtime_config.wait_for_config_change(timeout=0.1)
    elapsed = time.time() - start
    assert elapsed < 0.5, f"Timeout should be immediate, took {elapsed}s"


# ---------------------------------------------------------------------------
# Full settings cycle
# ---------------------------------------------------------------------------

def test_full_settings_save_and_reload_dedup(fresh_runtime_config):
    """Simulate a full settings save cycle: store -> getter -> updated value."""
    store = fresh_runtime_config._get_store()
    assert store is not None

    # Save dedup settings
    store.set("dedup.enabled", "false")
    store.set("dedup.threshold", "20")
    store.set("dedup.cache_size_per_device", "5")

    # Verify getters return new values
    assert runtime_config.get_dedup_enabled() is False
    assert runtime_config.get_dedup_threshold() == 20
    assert runtime_config.get_dedup_cache_size() == 5


# ---------------------------------------------------------------------------
# ClientSettingsStore defaults
# ---------------------------------------------------------------------------

def test_dedup_defaults_in_settings_store(tmp_path):
    """Verify dedup defaults are registered in ClientSettingsStore."""
    db_dir = tmp_path / "client"
    db_dir.mkdir()
    store = ClientSettingsStore(db_dir / "client.db")

    assert store.get("dedup.enabled") == "true"
    assert store.get("dedup.threshold") == "10"
    assert store.get("dedup.ttl_seconds") == "60.0"
    assert store.get("dedup.cache_size_per_device") == "1"
    assert store.get("dedup.for_click") == "true"
    assert store.get("dedup.for_app_switch") == "false"
    assert store.get("dedup.force_after_skip_seconds") == "30"


def test_dedup_defaults_reset(tmp_path):
    """Verify reset_to_defaults restores all dedup fields."""
    db_dir = tmp_path / "client"
    db_dir.mkdir()
    store = ClientSettingsStore(db_dir / "client.db")

    # Override and then reset
    store.set("dedup.threshold", "99")
    store.reset_to_defaults()
    assert store.get("dedup.threshold") == "10"
