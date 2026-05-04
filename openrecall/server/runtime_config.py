"""Module-level runtime configuration getters for server-side settings.

Read priority (per field):
1. SQLite runtime settings (server_settings table)
2. TOML config file (ServerSettings)
3. Hard-coded defaults (ServerSettingsStore.DEFAULTS)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openrecall.server.config_server import ServerSettings

from openrecall.server.database.settings_store import ServerSettingsStore

logger = logging.getLogger(__name__)

_settings_store: ServerSettingsStore | None = None
_toml_settings: ServerSettings | None = None


def init_runtime_config(data_dir: Path, toml_settings: ServerSettings) -> None:
    """Initialize module-level singletons. Idempotent."""
    global _settings_store, _toml_settings
    if _settings_store is None:
        db_path = Path(data_dir) / "db" / "settings.db"
        _settings_store = ServerSettingsStore(db_path)
    if _toml_settings is None:
        _toml_settings = toml_settings


def _require_initialized() -> tuple[ServerSettingsStore, "ServerSettings"]:
    """Return the initialized singletons or raise RuntimeError."""
    if _settings_store is None or _toml_settings is None:
        raise RuntimeError(
            "runtime_config not initialized — call init_runtime_config() first"
        )
    return _settings_store, _toml_settings


def _get_value(key: str, toml_attr: str, default: str) -> str:
    """Get effective string value with priority: SQLite > TOML > default."""
    store, toml = _require_initialized()
    sqlite_val = store.get(key)
    if sqlite_val is not None:
        return sqlite_val
    toml_val = getattr(toml, toml_attr, default)
    return str(toml_val) if toml_val is not None else default


def _get_source(key: str, toml_attr: str) -> str:
    """Determine source tag for a field: 'sqlite' | 'toml' | 'default'."""
    store, toml = _require_initialized()
    store_defaults = ServerSettingsStore.DEFAULTS
    sqlite_val = store.get(key)
    if sqlite_val is not None:
        return "sqlite"
    toml_val = getattr(toml, toml_attr, "")
    toml_str = str(toml_val) if toml_val is not None else ""
    default_str = store_defaults.get(key, "")
    if toml_str != default_str:
        return "toml"
    return "default"


def get_description_provider() -> str:
    return _get_value("description.provider", "description_provider", "local")


def get_description_model() -> str:
    return _get_value("description.model", "description_model", "")


def get_description_api_key() -> str:
    return _get_value("description.api_key", "description_api_key", "")


def get_description_api_base() -> str:
    return _get_value("description.api_base", "description_api_base", "")


def get_description_request_timeout() -> int:
    val = _get_value("description.request_timeout", "description_request_timeout", "120")
    try:
        return int(val)
    except (ValueError, TypeError):
        return 120


def _mask_api_key(api_key: str) -> str:
    """Mask API key for responses. Never log plaintext.

    Rule:
      - "" → ""
      - len < 8 → "***"
      - len ≥ 8 → "<first3>***<last4>"  e.g. sk-1234567890XX12 → sk-***XX12
    """
    if not api_key:
        return ""
    if len(api_key) < 8:
        return "***"
    return f"{api_key[:3]}***{api_key[-4:]}"


def get_effective_description_settings() -> dict:
    """Returns 5 effective fields with per-field source tags. api_key NOT masked."""
    return {
        "provider": get_description_provider(),
        "model": get_description_model(),
        "api_key": get_description_api_key(),
        "api_base": get_description_api_base(),
        "request_timeout": get_description_request_timeout(),
        "source": {
            "provider": _get_source("description.provider", "description_provider"),
            "model": _get_source("description.model", "description_model"),
            "api_key": _get_source("description.api_key", "description_api_key"),
            "api_base": _get_source("description.api_base", "description_api_base"),
            "request_timeout": _get_source("description.request_timeout", "description_request_timeout"),
        },
    }
