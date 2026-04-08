"""Runtime configuration that supports hot-reload from SQLite settings.

This module provides a way to read configuration values that can be
modified at runtime via the WebUI settings page, without requiring
a process restart.

Settings are stored in client.db within the client data directory
(e.g., ~/.myrecall/client/client.db or ~/MRC/client.db depending on config).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from openrecall.client.database import ClientSettingsStore

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Cache for settings store to avoid repeated DB opens
_settings_store: ClientSettingsStore | None = None
_data_dir: Path | None = None


def init_runtime_config(data_dir: Path) -> None:
    """Initialize the runtime configuration with the client data directory.

    This should be called once during client startup.

    Args:
        data_dir: Path to the client data directory (e.g., ~/.myrecall/client)
    """
    global _data_dir, _settings_store
    _data_dir = Path(data_dir)
    _settings_store = ClientSettingsStore(_data_dir / "client.db")
    logger.debug(f"Runtime config initialized with data_dir: {_data_dir}")


def _get_store() -> ClientSettingsStore | None:
    """Get the settings store, or None if not initialized."""
    return _settings_store


def get_permission_poll_interval_sec() -> int:
    """Get permission poll interval from runtime settings.

    Priority:
    1. SQLite runtime settings (set via WebUI)
    2. TOML config (via settings.permission_poll_interval_sec)

    Returns:
        Permission poll interval in seconds
    """
    store = _get_store()
    if store is not None:
        try:
            value = store.get("capture_permission_poll_sec", "")
            if value:
                return int(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid capture_permission_poll_sec in runtime settings: {e}")

    # Fall back to TOML config
    from openrecall.shared.config import settings

    return settings.permission_poll_interval_sec


def get_save_local_copies() -> bool:
    """Get save local copies setting from runtime settings.

    Priority:
    1. SQLite runtime settings (set via WebUI)
    2. TOML config (via settings.client_save_local_screenshots)

    Returns:
        True if local copies should be saved
    """
    store = _get_store()
    if store is not None:
        try:
            value = store.get("capture_save_local_copies", "")
            if value:
                return value.lower() == "true"
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid capture_save_local_copies in runtime settings: {e}")

    # Fall back to TOML config
    from openrecall.shared.config import settings

    return settings.client_save_local_screenshots


def get_debounce_click_ms() -> int:
    """Get click debounce interval in milliseconds.

    Priority: SQLite runtime settings > TOML config (click_debounce_ms) > 3000
    """
    store = _get_store()
    if store is not None:
        try:
            value = store.get("debounce.click_ms", "")
            if value:
                return int(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid debounce.click_ms in runtime settings: {e}")

    from openrecall.shared.config import settings
    return settings.click_debounce_ms


def get_debounce_trigger_ms() -> int:
    """Get trigger debounce interval in milliseconds.

    Priority: SQLite runtime settings > TOML config (trigger_debounce_ms) > 3000
    """
    store = _get_store()
    if store is not None:
        try:
            value = store.get("debounce.trigger_ms", "")
            if value:
                return int(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid debounce.trigger_ms in runtime settings: {e}")

    from openrecall.shared.config import settings
    return settings.trigger_debounce_ms


def get_debounce_capture_ms() -> int:
    """Get global capture debounce interval in milliseconds.

    Priority: SQLite runtime settings > TOML config (capture_debounce_ms) > 3000
    """
    store = _get_store()
    if store is not None:
        try:
            value = store.get("debounce.capture_ms", "")
            if value:
                return int(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid debounce.capture_ms in runtime settings: {e}")

    from openrecall.shared.config import settings
    return settings.capture_debounce_ms


def get_debounce_idle_interval_ms() -> int:
    """Get idle capture fallback interval in milliseconds.

    Priority: SQLite runtime settings > TOML config (idle_capture_interval_ms) > 60000
    """
    store = _get_store()
    if store is not None:
        try:
            value = store.get("debounce.idle_interval_ms", "")
            if value:
                return int(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid debounce.idle_interval_ms in runtime settings: {e}")

    from openrecall.shared.config import settings
    return settings.idle_capture_interval_ms


def get_stats_interval_sec() -> int:
    """Get stats reporting interval in seconds.

    Priority: SQLite runtime settings > TOML config (stats.interval_sec) > 120
    """
    store = _get_store()
    if store is not None:
        try:
            value = store.get("stats.interval_sec", "")
            if value:
                return int(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid stats.interval_sec in runtime settings: {e}")

    from openrecall.shared.config import settings
    return settings.stats_interval_sec


def get_dedup_enabled() -> bool:
    """Priority: SQLite runtime > TOML (dedup.enabled) > True"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.enabled", "")
        if value:
            return value.lower() == "true"
    from openrecall.shared.config import settings
    return settings.simhash_dedup_enabled


def get_dedup_threshold() -> int:
    """Priority: SQLite runtime > TOML (dedup.threshold) > 10"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.threshold", "")
        if value:
            return int(value)
    from openrecall.shared.config import settings
    return settings.simhash_dedup_threshold


def get_dedup_ttl_seconds() -> float:
    """Priority: SQLite runtime > TOML (dedup.ttl_seconds) > 60.0"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.ttl_seconds", "")
        if value:
            return float(value)
    from openrecall.shared.config import settings
    return settings.simhash_ttl_seconds


def get_dedup_cache_size() -> int:
    """Priority: SQLite runtime > TOML (dedup.cache_size_per_device) > 1"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.cache_size_per_device", "")
        if value:
            return int(value)
    from openrecall.shared.config import settings
    return settings.simhash_cache_size_per_device


def get_dedup_for_click() -> bool:
    """Priority: SQLite runtime > TOML (dedup.for_click) > True"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.for_click", "")
        if value:
            return value.lower() == "true"
    from openrecall.shared.config import settings
    return settings.simhash_enabled_for_click


def get_dedup_for_app_switch() -> bool:
    """Priority: SQLite runtime > TOML (dedup.for_app_switch) > False"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.for_app_switch", "")
        if value:
            return value.lower() == "true"
    from openrecall.shared.config import settings
    return settings.simhash_enabled_for_app_switch


def get_dedup_force_after_skip_sec() -> int:
    """Priority: SQLite runtime > TOML (dedup.force_after_skip_seconds) > 30"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.force_after_skip_seconds", "")
        if value:
            return int(value)
    from openrecall.shared.config import settings
    return settings.max_skip_duration_sec


_config_change_event = threading.Event()


def notify_config_changed() -> None:
    """Call after saving settings to SQLite. Wakes the config listener.

    Leaves the event in SET state — the listener clears it after processing.
    This prevents race conditions where notify fires while listener is
    between wait() and the set() call.
    """
    _config_change_event.set()


def wait_for_config_change(timeout: float | None = None) -> None:
    """Block until config changed event is set, then clear and return.

    Caller must call notify_config_changed() to set the event again
    for subsequent notifications.
    """
    _config_change_event.wait(timeout=timeout)
    if _config_change_event.is_set():
        _config_change_event.clear()
