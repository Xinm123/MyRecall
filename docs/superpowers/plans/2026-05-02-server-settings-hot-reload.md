# Server Settings Hot-Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a SQLite-backed, hot-reloadable settings layer on the Edge (server) side for AI description provider/model configuration, with HTTP API endpoints and a client UI section.

**Architecture:** Mirror the existing client-side hot-reload pipeline (`ClientSettingsStore` + `runtime_config` + `notify_config_change` + Alpine.js) on the server side. Server-side uses a sparse SQLite table (no pre-inserted defaults), three-level config priority (SQLite > TOML > hardcoded), and signals workers via `ai_processing_version` bump.

**Tech Stack:** Python 3.12, Flask, SQLite, Alpine.js, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `openrecall/server/database/settings_store.py` | Create | `ServerSettingsStore` — SQLite persistence for server-side settings. Sparse table (no pre-inserted defaults). |
| `openrecall/server/runtime_config.py` | Create | Module-level getters that read SQLite > TOML > default, with per-field source tags. |
| `openrecall/server/config_server.py` | Modify | Add `description_request_timeout` field to `ServerSettings` dataclass. |
| `openrecall/server/config_runtime.py` | Modify | Add `bump_ai_processing_version()` atomic helper to `RuntimeSettings`. |
| `openrecall/server/ai/factory.py` | Modify | Add `invalidate()` + `_lock` + double-checked locking; replace `settings.description_*` with `runtime_config.get_description_*()`. |
| `openrecall/server/description/providers/openai.py` | Modify | Replace `settings.ai_request_timeout` with `get_description_request_timeout()` at request time. |
| `openrecall/server/description/worker.py` | Modify | Version-check guard at top of `_process_batch` that resets `_service` when version changes. |
| `openrecall/server/api_v1.py` | Modify | Add 4 routes: GET/POST `/v1/settings/description`, POST `/v1/settings/description/test`, POST `/v1/settings/description/reset`. |
| `openrecall/server/__main__.py` | Modify | Call `init_runtime_config()` in `main()` after `ensure_v3_schema()`. |
| `openrecall/client/web/templates/settings.html` | Modify | Add `serverSettings()` Alpine.js section after client sections. |
| `tests/test_server_settings_store.py` | Create | Unit tests for `ServerSettingsStore`. |
| `tests/test_server_runtime_config.py` | Create | Unit tests for `runtime_config.py` getters and source tags. |
| `tests/test_server_settings_mask.py` | Create | Unit tests for `api_key` mask function. |
| `tests/test_server_settings_api.py` | Create | Integration tests for all 4 API endpoints. |
| `tests/test_description_worker_hot_reload.py` | Create | Worker-level tests for version-triggered rebuild. |

---

### Task 1: ServerSettingsStore

**Files:**
- Create: `openrecall/server/database/settings_store.py`
- Test: `tests/test_server_settings_store.py`

**Context:** Mirrors `ClientSettingsStore` but with a **sparse** table (no pre-inserted defaults). This is what gives the source-tag mechanism three distinct states (`sqlite` / `toml` / `default`).

- [ ] **Step 1: Write failing test**

```python
# tests/test_server_settings_store.py
import pytest
from pathlib import Path
from openrecall.server.database.settings_store import ServerSettingsStore


class TestServerSettingsStore:
    def test_init_creates_table_no_defaults(self, tmp_path):
        """Init creates table; does NOT pre-insert default rows."""
        db_path = tmp_path / "settings.db"
        store = ServerSettingsStore(db_path)
        assert db_path.exists()
        # Table should be empty on first run
        assert store.get_all() == {}

    def test_set_get_round_trip(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        assert store.get("description.provider") == "openai"

    def test_two_sets_same_key_last_wins(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        store.set("description.provider", "dashscope")
        assert store.get("description.provider") == "dashscope"

    def test_delete_then_get_returns_none(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        store.delete("description.provider")
        assert store.get("description.provider") is None

    def test_get_all_returns_only_existing_rows(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        assert store.get_all() == {}
        store.set("description.provider", "openai")
        store.set("description.model", "gpt-4o")
        assert store.get_all() == {
            "description.provider": "openai",
            "description.model": "gpt-4o",
        }

    def test_reset_to_defaults_deletes_description_keys(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        store.set("description.model", "gpt-4o")
        store.set("other.key", "value")  # not a description key
        store.reset_to_defaults()
        assert store.get("description.provider") is None
        assert store.get("description.model") is None
        assert store.get("other.key") == "value"  # untouched

    def test_auto_creates_parent_dir(self, tmp_path):
        db_path = tmp_path / "deep" / "nested" / "settings.db"
        store = ServerSettingsStore(db_path)
        assert db_path.exists()

    def test_non_string_value_coerced(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.request_timeout", 120)  # int
        assert store.get("description.request_timeout") == "120"

    def test_set_many_atomic(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set_many({
            "description.provider": "openai",
            "description.model": "gpt-4o",
            "description.api_key": "sk-test",
        })
        assert store.get("description.provider") == "openai"
        assert store.get("description.model") == "gpt-4o"
        assert store.get("description.api_key") == "sk-test"

    def test_apply_changes_atomic(self, tmp_path):
        """apply_changes performs deletes + sets in a single transaction."""
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        store.set("description.model", "gpt-4o")
        store.set("description.api_base", "https://api.openai.com/v1")

        store.apply_changes(
            deletes=["description.provider", "description.model"],
            sets={"description.api_key": "sk-newkey"},
        )

        assert store.get("description.provider") is None
        assert store.get("description.model") is None
        assert store.get("description.api_base") == "https://api.openai.com/v1"
        assert store.get("description.api_key") == "sk-newkey"

    def test_apply_changes_empty_is_noop(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        store.apply_changes(deletes=[], sets={})
        assert store.get("description.provider") == "openai"
```

Run: `pytest tests/test_server_settings_store.py -v`
Expected: FAIL — `ServerSettingsStore` not defined

- [ ] **Step 2: Implement ServerSettingsStore**

```python
# openrecall/server/database/settings_store.py
"""SQLite-backed store for server-side settings."""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class ServerSettingsStore:
    """SQLite-backed store for server-side settings.

    Uses a SPARSE table: defaults are NOT pre-inserted. This gives the
    source-tag mechanism three distinct states (sqlite / toml / default).
    """

    DEFAULTS: dict[str, str] = {
        "description.provider": "local",
        "description.model": "",
        "description.api_key": "",
        "description.api_base": "",
        "description.request_timeout": "120",
    }

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS server_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get(self, key: str, default: str | None = None) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value FROM server_settings WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
            return row[0] if row else default

    def set(self, key: str, value: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO server_settings (key, value, updated_at)
                VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, str(value)),
            )
            conn.commit()
        logger.debug(f"Server setting updated: {key}")

    def set_many(self, items: dict[str, str]) -> None:
        """Atomic batch write of multiple settings."""
        with sqlite3.connect(self.db_path) as conn:
            for key, value in items.items():
                conn.execute(
                    """
                    INSERT INTO server_settings (key, value, updated_at)
                    VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, str(value)),
                )
            conn.commit()
        logger.debug(f"Server settings batch updated: {list(items.keys())}")

    def apply_changes(
        self,
        deletes: list[str],
        sets: dict[str, str],
    ) -> None:
        """Atomic: delete keys + upsert keys in ONE transaction.

        Used by the API layer to ensure POST /v1/settings/description either
        applies all field changes or none of them. A separate `set_many` after
        per-field `delete()` would NOT be atomic across both phases.
        """
        if not deletes and not sets:
            return
        with sqlite3.connect(self.db_path) as conn:
            for key in deletes:
                conn.execute("DELETE FROM server_settings WHERE key = ?", (key,))
            for key, value in sets.items():
                conn.execute(
                    """
                    INSERT INTO server_settings (key, value, updated_at)
                    VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, str(value)),
                )
            conn.commit()
        logger.debug(
            f"Server settings applied: deleted={deletes}, set={list(sets.keys())}"
        )

    def delete(self, key: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM server_settings WHERE key = ?", (key,))
            conn.commit()
        logger.debug(f"Server setting deleted: {key}")

    def get_all(self) -> dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT key, value FROM server_settings")
            return {row[0]: row[1] for row in cursor.fetchall()}

    def reset_to_defaults(self) -> None:
        """Delete all description.* keys from SQLite (fall back to TOML)."""
        with sqlite3.connect(self.db_path) as conn:
            for key in self.DEFAULTS:
                conn.execute("DELETE FROM server_settings WHERE key = ?", (key,))
            conn.commit()
        logger.info("Server description settings reset to defaults")
```

Run: `pytest tests/test_server_settings_store.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/database/settings_store.py tests/test_server_settings_store.py
git commit -m "feat(settings): add ServerSettingsStore for server-side SQLite settings"
```

---

### Task 2: runtime_config.py

**Files:**
- Create: `openrecall/server/runtime_config.py`
- Test: `tests/test_server_runtime_config.py`
- Test: `tests/test_server_settings_mask.py`

**Context:** Module-level initialization + per-field getter functions. Read priority: SQLite > TOML > DEFAULTS. Returns per-field source tags.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_server_runtime_config.py
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from openrecall.server.database.settings_store import ServerSettingsStore
from openrecall.server.runtime_config import (
    init_runtime_config,
    get_description_provider,
    get_description_model,
    get_description_api_key,
    get_description_api_base,
    get_description_request_timeout,
    get_effective_description_settings,
    _settings_store,
    _toml_settings,
)
from openrecall.server.config_server import ServerSettings


class TestRuntimeConfig:
    @pytest.fixture(autouse=True)
    def reset_singleton(self, tmp_path):
        """Reset module-level singletons before each test."""
        import openrecall.server.runtime_config as rc
        rc._settings_store = None
        rc._toml_settings = None
        yield
        rc._settings_store = None
        rc._toml_settings = None

    def test_sqlite_value_takes_priority(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_provider="dashscope")
        init_runtime_config(db_path, toml)
        _settings_store.set("description.provider", "openai")
        assert get_description_provider() == "openai"

    def test_toml_value_when_sqlite_empty(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_provider="dashscope")
        init_runtime_config(db_path, toml)
        assert get_description_provider() == "dashscope"

    def test_hardcoded_default_when_both_empty(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_provider="local")
        init_runtime_config(db_path, toml)
        assert get_description_provider() == "local"

    def test_get_effective_returns_source_tags(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(
            description_provider="dashscope",  # differs from default "local"
            description_model="qwen-vl-max",
            description_api_key="",
            description_api_base="",
        )
        init_runtime_config(db_path, toml)
        _settings_store.set("description.provider", "openai")
        result = get_effective_description_settings()
        assert result["provider"] == "openai"
        assert result["source"]["provider"] == "sqlite"
        assert result["source"]["model"] == "toml"  # toml differs from default ""
        assert result["source"]["api_key"] == "default"  # toml "" == default ""

    def test_init_is_idempotent(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_provider="openai")
        init_runtime_config(db_path, toml)
        init_runtime_config(db_path, toml)
        assert get_description_provider() == "openai"

    def test_defaults_consistency(self):
        """ServerSettingsStore.DEFAULTS must match ServerSettings defaults (string-coerced)."""
        from openrecall.server.database.settings_store import ServerSettingsStore

        store_defaults = ServerSettingsStore.DEFAULTS
        toml = ServerSettings()
        # description.provider
        assert str(toml.description_provider) == store_defaults["description.provider"]
        # description.model
        assert str(toml.description_model) == store_defaults["description.model"]
        # description.api_key
        assert str(toml.description_api_key) == store_defaults["description.api_key"]
        # description.api_base
        assert str(toml.description_api_base) == store_defaults["description.api_base"]
        # description.request_timeout
        assert str(toml.description_request_timeout) == store_defaults["description.request_timeout"]

    def test_timeout_int_coercion(self, tmp_path):
        db_path = tmp_path / "settings.db"
        toml = ServerSettings(description_request_timeout=120)
        init_runtime_config(db_path, toml)
        assert get_description_request_timeout() == 120
        _settings_store.set("description.request_timeout", "60")
        assert get_description_request_timeout() == 60
```

```python
# tests/test_server_settings_mask.py
import pytest
from openrecall.server.runtime_config import _mask_api_key


class TestMaskApiKey:
    def test_empty_returns_empty(self):
        assert _mask_api_key("") == ""

    def test_short_returns_stars(self):
        # length < 8 → just "***"
        assert _mask_api_key("abc") == "***"

    def test_medium_returns_stars(self):
        # length 7 still < 8 → "***"
        assert _mask_api_key("sk-1234") == "***"

    def test_long_returns_first3_last4(self):
        # length ≥ 8 → "<first3>***<last4>"
        assert _mask_api_key("sk-1234567890XX12") == "sk-***XX12"

    def test_exactly_8_chars(self):
        # length == 8 → "<first3>***<last4>" → 3+3+4 = 10 chars; first3 and last4 may overlap on input but result is still 10 chars
        assert _mask_api_key("12345678") == "123***5678"

    def test_unicode_safe(self):
        # length 11 ≥ 8 → "<first3>***<last4>"
        # "日本語12345678" first3="日本語", last4="5678"
        assert _mask_api_key("日本語12345678") == "日本語***5678"
```

Run: `pytest tests/test_server_runtime_config.py tests/test_server_settings_mask.py -v`
Expected: FAIL — module not defined

- [ ] **Step 2: Implement runtime_config.py**

```python
# openrecall/server/runtime_config.py
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
    """Return the initialized singletons or raise RuntimeError.

    Use this instead of `assert` because production runs may use python -O,
    which strips assertions and would cause AttributeError on None instead
    of a clear error.
    """
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
```

Run: `pytest tests/test_server_runtime_config.py tests/test_server_settings_mask.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/runtime_config.py tests/test_server_runtime_config.py tests/test_server_settings_mask.py
git commit -m "feat(settings): add server runtime_config with SQLite>TOML>default priority"
```

---

### Task 3: config_server.py + config_runtime.py

**Files:**
- Modify: `openrecall/server/config_server.py`
- Modify: `openrecall/server/config_runtime.py`
- Modify: `openrecall/server/api.py`

**Scope note:** `description.enabled` is intentionally NOT included in this iteration (see spec Non-Goals). It remains a TOML-only field on `ServerSettings`. Hot-reloading it would require coordinating worker shutdown, which is out of scope.

- [ ] **Step 1: Add `description_request_timeout` to ServerSettings**

In `openrecall/server/config_server.py`, find the line containing `description_api_base: str = ""` in the `ServerSettings` class body and add the new field directly after it:

```python
# Add after description_api_base
description_request_timeout: int = 120  # NEW
```

In the same file, find `_from_dict()` and the line containing `description_api_base=data.get("description.api_base", "")`, and add directly after it:

```python
# Add after description_api_base assignment in _from_dict()
description_request_timeout=data.get("description.request_timeout", 120),  # NEW
```

- [ ] **Step 2: Add `bump_ai_processing_version()` to RuntimeSettings**

In `openrecall/server/config_runtime.py`, find the existing `notify_change(self)` method on `RuntimeSettings`. Add the following method directly after it:

```python
def bump_ai_processing_version(self) -> int:
    """Atomically increment ai_processing_version and notify waiters.
    Returns the new version. Used to signal that AI provider config changed.
    """
    with self._lock:
        self.ai_processing_version += 1
        new_version = self.ai_processing_version
    self.notify_change()
    return new_version
```

- [ ] **Step 3: Migrate existing callers in api.py**

In `openrecall/server/api.py`, the `update_config` route currently bumps the version manually inside its `with runtime_settings._lock:` block. Find both occurrences of `runtime_settings.ai_processing_version += 1` (one inside the `not value` branch, one inside the `value and not getattr(...)` branch).

Replace each with:

```python
runtime_settings.bump_ai_processing_version()
```

**Important — re-entrant lock interaction:** `bump_ai_processing_version()` itself takes `self._lock`. The existing code already holds the lock at the point of the increment (`with runtime_settings._lock:` wraps the whole body). `RuntimeSettings._lock` is an `RLock` (re-entrant — verify in `config_runtime.py`), so the nested acquire is safe. If it were a plain `Lock`, this would deadlock. Add an inline comment at each migrated call site:

```python
# RLock allows nested acquire — bump_ai_processing_version takes _lock again
runtime_settings.bump_ai_processing_version()
```

The existing `runtime_settings.notify_change()` at the end of the route can stay — calling it twice is harmless and the explicit final notification preserves the original behavior for non-`ai_processing_enabled` field updates.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_server_runtime_config.py -v
pytest tests/test_runtime_config.py -v 2>/dev/null || echo "no existing test"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/config_server.py openrecall/server/config_runtime.py openrecall/server/api.py
git commit -m "feat(settings): add description_request_timeout and bump_ai_processing_version helper"
```

---

### Task 4: ai/factory.py

**Files:**
- Modify: `openrecall/server/ai/factory.py`
- Test: `tests/test_server_settings_api.py` (will be written in Task 7, but factory tests belong here)

**Context:** Add `_lock`, `invalidate()`, double-checked locking in `get_description_provider()`, and replace `settings.description_*` reads with `runtime_config.get_description_*()`.

- [ ] **Step 1: Write failing test for invalidate**

Append to `tests/test_server_settings_api.py` (or create `tests/test_ai_factory_invalidate.py` if you prefer isolation):

```python
# tests/test_ai_factory_invalidate.py
import pytest
from openrecall.server.ai import factory


class TestFactoryInvalidate:
    def teardown_method(self):
        """Clear factory cache after each test."""
        factory.invalidate()

    def test_invalidate_clears_specific_capability(self):
        factory._instances["description"] = "fake_provider"
        factory.invalidate("description")
        assert "description" not in factory._instances

    def test_invalidate_clears_all_when_none(self):
        factory._instances["description"] = "fake"
        factory._instances["ocr"] = "fake2"
        factory.invalidate()
        assert factory._instances == {}

    def test_invalidate_no_op_when_key_missing(self):
        factory.invalidate("nonexistent")  # should not raise
```

Run: `pytest tests/test_ai_factory_invalidate.py -v`
Expected: FAIL — `invalidate` not defined

- [ ] **Step 2: Patch ai/factory.py**

```python
# openrecall/server/ai/factory.py
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Dict, Union

if TYPE_CHECKING:
    from openrecall.server.description.providers.base import DescriptionProvider
    from openrecall.server.embedding.providers.base import MultimodalEmbeddingProvider

from openrecall.server.ai.base import (
    AIProvider,
    AIProviderConfigError,
    EmbeddingProvider,
    OCRProvider,
)
from openrecall.server.ai.providers import (
    DashScopeEmbeddingProvider,
    DashScopeOCRProvider,
    DoctrOCRProvider,
    LocalEmbeddingProvider,
    LocalOCRProvider,
    OpenAIEmbeddingProvider,
    OpenAIOCRProvider,
    RapidOCRProvider,
)
from openrecall.shared.config import settings

_instances: Dict[str, object] = {}
_lock = threading.Lock()


def invalidate(capability: str | None = None) -> None:
    """Clear cached provider instance(s). None = clear all."""
    with _lock:
        if capability is None:
            _instances.clear()
        else:
            _instances.pop(capability, None)
```

Then replace `get_description_provider()`:

```python
def get_description_provider() -> "DescriptionProvider":
    """Get or create a cached DescriptionProvider instance."""
    capability = "description"

    # Fast path: lock-free read
    cached = _instances.get(capability)
    if cached is not None:
        return cached  # type: ignore[return-value]

    # Slow path: build under lock
    with _lock:
        # Re-check inside lock (double-checked locking)
        cached = _instances.get(capability)
        if cached is not None:
            return cached  # type: ignore[return-value]

        from openrecall.server.description.providers import (
            LocalDescriptionProvider,
            OpenAIDescriptionProvider,
            DashScopeDescriptionProvider,
        )
        from openrecall.server.runtime_config import (
            get_description_provider as get_provider_name,
            get_description_model,
            get_description_api_key,
            get_description_api_base,
        )

        provider = get_provider_name().strip().lower()
        model_name = get_description_model()
        api_key = get_description_api_key()
        api_base = get_description_api_base()

        if provider == "local":
            instance: DescriptionProvider = LocalDescriptionProvider(model_name=model_name)
        elif provider == "dashscope":
            instance = DashScopeDescriptionProvider(api_key=api_key, model_name=model_name)
        elif provider == "openai":
            instance = OpenAIDescriptionProvider(
                api_key=api_key, model_name=model_name, api_base=api_base
            )
        else:
            raise AIProviderConfigError(f"Unknown description provider: {provider}")

        _instances[capability] = instance
        return instance
```

Run: `pytest tests/test_ai_factory_invalidate.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/ai/factory.py tests/test_ai_factory_invalidate.py
git commit -m "feat(settings): add factory.invalidate and double-checked locking"
```

---

### Task 5: description/providers/openai.py

**Files:**
- Modify: `openrecall/server/description/providers/openai.py`
- Modify: `tests/test_description_provider.py` (fixture)

- [ ] **Step 1: Replace timeout read in openai.py**

In `openrecall/server/description/providers/openai.py`, find the import line `from openrecall.shared.config import settings` and replace with:

```python
# OLD
from openrecall.shared.config import settings

# NEW
from openrecall.server.runtime_config import get_description_request_timeout
```

Then find the line `resp = requests.post(url, headers=headers, json=payload, timeout=settings.ai_request_timeout)` and replace with:

```python
# OLD
resp = requests.post(url, headers=headers, json=payload, timeout=settings.ai_request_timeout)

# NEW
resp = requests.post(url, headers=headers, json=payload, timeout=get_description_request_timeout())
```

The `settings` import is no longer used in this file — verify by grepping for `settings\.` in the file after edit and remove the import only if no other reference remains.

- [ ] **Step 2: Add fixture to `tests/test_description_provider.py`**

The provider previously didn't depend on `runtime_config`. Now `OpenAIDescriptionProvider.generate()` calls `get_description_request_timeout()`, which raises `RuntimeError` if `runtime_config` is uninitialized. Existing tests that construct providers directly need a fixture.

In `tests/test_description_provider.py`, add (or extend an existing) `conftest.py`-equivalent fixture at the top of the test file (or in `tests/conftest.py` if you prefer global scope):

```python
# tests/test_description_provider.py (top of file)
import pytest
from pathlib import Path

from openrecall.server.config_server import ServerSettings


@pytest.fixture(autouse=True)
def _init_runtime_config(tmp_path: Path):
    """Initialize runtime_config so providers reading get_description_*() succeed.

    Autouse: every test in this module gets a fresh DB and TOML defaults.
    """
    import openrecall.server.runtime_config as rc
    rc._settings_store = None
    rc._toml_settings = None
    toml = ServerSettings(
        description_provider="openai",
        description_model="gpt-4o",
        description_api_key="",
        description_api_base="",
        description_request_timeout=120,
    )
    rc.init_runtime_config(tmp_path, toml)
    yield
    rc._settings_store = None
    rc._toml_settings = None
```

- [ ] **Step 3: Run existing tests**

```bash
pytest tests/test_description_provider.py -v
```

Expected: PASS

If tests fail with `RuntimeError: runtime_config not initialized`, the fixture is not autouse or not in scope — verify the fixture is at module top with `autouse=True`.

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/description/providers/openai.py tests/test_description_provider.py
git commit -m "feat(settings): read description timeout from runtime_config at request time"
```

---

### Task 6: description/worker.py

**Files:**
- Modify: `openrecall/server/description/worker.py`
- Test: `tests/test_description_worker_hot_reload.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_description_worker_hot_reload.py
import pytest
import threading
import time
from unittest.mock import MagicMock, patch

from openrecall.server.description.worker import DescriptionWorker
from openrecall.server.config_runtime import runtime_settings


@pytest.fixture(autouse=True)
def _reset_ai_processing_version():
    """Save and restore the global runtime_settings.ai_processing_version.

    The global is shared across the entire test session, so any test that bumps
    it would leak state into subsequent tests. Capture before, restore after.
    """
    saved = runtime_settings.ai_processing_version
    yield
    with runtime_settings._lock:
        runtime_settings.ai_processing_version = saved


class TestDescriptionWorkerHotReload:
    def test_service_is_none_on_init(self):
        store = MagicMock()
        worker = DescriptionWorker(store)
        assert worker._service is None
        assert worker._last_processing_version == -1

    def test_version_bump_triggers_service_reset(self):
        store = MagicMock()
        store._connect.return_value.__enter__ = MagicMock(return_value=MagicMock())
        store._connect.return_value.__exit__ = MagicMock(return_value=False)
        store.claim_description_task.return_value = None  # no tasks

        worker = DescriptionWorker(store)
        worker._service = MagicMock()  # pretend service exists
        worker._last_processing_version = runtime_settings.ai_processing_version

        # Simulate external version bump
        runtime_settings.bump_ai_processing_version()
        new_version = runtime_settings.ai_processing_version

        # Call _process_batch — should detect version change and reset service
        with patch.object(worker, '_log_queue_status'):
            worker._process_batch(MagicMock())

        assert worker._service is None
        assert worker._last_processing_version == new_version

    def test_no_reset_when_version_unchanged(self):
        store = MagicMock()
        store._connect.return_value.__enter__ = MagicMock(return_value=MagicMock())
        store._connect.return_value.__exit__ = MagicMock(return_value=False)
        store.claim_description_task.return_value = None

        worker = DescriptionWorker(store)
        fake_service = MagicMock()
        worker._service = fake_service
        worker._last_processing_version = runtime_settings.ai_processing_version

        with patch.object(worker, '_log_queue_status'):
            worker._process_batch(MagicMock())

        assert worker._service is fake_service  # unchanged
```

Run: `pytest tests/test_description_worker_hot_reload.py -v`
Expected: FAIL — `_last_processing_version` not defined

- [ ] **Step 2: Patch description/worker.py**

In `openrecall/server/description/worker.py`, find the `DescriptionWorker.__init__` method. After the existing initialization of `self._service` (the lazy-init field), add:

```python
self._last_processing_version: int = -1  # NEW; -1 forces first-batch alignment
```

Then find the `_process_batch(self, conn)` method. Add the version-check guard at the very top of the method body, before any existing logic (queue stats, claim_description_task, etc.):

```python
def _process_batch(self, conn: sqlite3.Connection) -> None:
    from openrecall.server.config_runtime import runtime_settings
    current_version = runtime_settings.ai_processing_version
    if current_version != self._last_processing_version:
        if self._service is not None:
            logger.info(
                f"DescriptionWorker rebuilding service (version "
                f"{self._last_processing_version} -> {current_version})"
            )
        self._service = None
        self._last_processing_version = current_version

    # ... rest of existing method (queue status, claim task, etc.)
```

The existing `except DescriptionProviderError` / `except Exception` handlers in the method body are unchanged — they already correctly mark a failed task and continue. Verify no edits are needed there.

Run: `pytest tests/test_description_worker_hot_reload.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/description/worker.py tests/test_description_worker_hot_reload.py
git commit -m "feat(settings): add version-check guard to DescriptionWorker for hot reload"
```

---

### Task 7: API Routes (api_v1.py)

**Files:**
- Modify: `openrecall/server/api_v1.py`
- Test: `tests/test_server_settings_api.py`

**Context:** 4 new routes on existing `v1_bp`. API layer owns mask logic and validation.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_server_settings_api.py
import pytest
import json
from unittest.mock import patch, MagicMock

from openrecall.server.config_runtime import runtime_settings
from openrecall.server.ai import factory


class TestServerSettingsAPI:
    @pytest.fixture
    def client(self, tmp_path):
        """Test client + isolated runtime_config + clean factory cache + version restore.

        Critical hygiene:
          - `runtime_settings.ai_processing_version` is global (process-wide). Save/restore
            so tests don't leak versions into each other.
          - `factory._instances` is global. Clear before AND after.
          - `runtime_config._settings_store` and `_toml_settings` are module singletons.
            Reset to None before AND after.
        """
        from openrecall.server.app import app
        from openrecall.server.runtime_config import init_runtime_config
        from openrecall.server.config_server import ServerSettings

        app.config["TESTING"] = True

        # Save version baseline
        saved_version = runtime_settings.ai_processing_version

        # Reset singletons
        import openrecall.server.runtime_config as rc
        rc._settings_store = None
        rc._toml_settings = None
        factory.invalidate()

        with app.test_client() as client:
            toml = ServerSettings(
                description_provider="local",
                description_model="",
                description_api_key="",
                description_api_base="",
                description_request_timeout=120,
            )
            init_runtime_config(tmp_path, toml)
            yield client

        # Cleanup
        factory.invalidate()
        rc._settings_store = None
        rc._toml_settings = None
        with runtime_settings._lock:
            runtime_settings.ai_processing_version = saved_version

    @pytest.fixture
    def client_with_toml_overrides(self, tmp_path):
        """Variant fixture: TOML differs from DEFAULTS so source='toml' is observable."""
        from openrecall.server.app import app
        from openrecall.server.runtime_config import init_runtime_config
        from openrecall.server.config_server import ServerSettings

        app.config["TESTING"] = True
        saved_version = runtime_settings.ai_processing_version
        import openrecall.server.runtime_config as rc
        rc._settings_store = None
        rc._toml_settings = None
        factory.invalidate()

        with app.test_client() as client:
            toml = ServerSettings(
                description_provider="dashscope",   # differs from DEFAULTS "local"
                description_model="qwen-vl-max",    # differs from DEFAULTS ""
                description_api_key="",
                description_api_base="",
                description_request_timeout=120,
            )
            init_runtime_config(tmp_path, toml)
            yield client

        factory.invalidate()
        rc._settings_store = None
        rc._toml_settings = None
        with runtime_settings._lock:
            runtime_settings.ai_processing_version = saved_version

    # ---------- GET ----------

    def test_get_default_settings(self, client):
        """GET with no SQLite + TOML matching DEFAULTS: source=default everywhere."""
        resp = client.get("/v1/settings/description")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "local"
        assert data["api_key_masked"] == ""
        assert data["source"]["provider"] == "default"
        assert data["source"]["model"] == "default"

    def test_get_returns_toml_source_when_toml_differs_from_defaults(
        self, client_with_toml_overrides
    ):
        """GET when TOML differs from DEFAULTS: source=toml for those fields."""
        resp = client_with_toml_overrides.get("/v1/settings/description")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "dashscope"
        assert data["source"]["provider"] == "toml"
        assert data["model"] == "qwen-vl-max"
        assert data["source"]["model"] == "toml"

    # ---------- POST update ----------

    def test_post_update_provider(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "openai"
        assert data["source"]["provider"] == "sqlite"

    def test_post_full_payload_updates_all_fields(self, client):
        """Full POST containing all 5 fields applies all of them."""
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "sk-1234567890XX12",
                "api_base": "https://api.openai.com/v1",
                "request_timeout": 60,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o"
        assert data["api_key_masked"] == "sk-***XX12"
        assert data["api_base"] == "https://api.openai.com/v1"
        assert data["request_timeout"] == 60
        # All 5 written → all sourced from sqlite
        assert data["source"]["provider"] == "sqlite"
        assert data["source"]["model"] == "sqlite"
        assert data["source"]["api_key"] == "sqlite"
        assert data["source"]["api_base"] == "sqlite"
        assert data["source"]["request_timeout"] == "sqlite"

    def test_post_invalid_provider_returns_400(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "invalid"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "provider" in data.get("details", {})

    def test_post_timeout_out_of_range_returns_400(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"request_timeout": 9999}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "request_timeout" in resp.get_json().get("details", {})

    def test_post_api_base_not_http_returns_400(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"api_base": "ftp://example.com"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "api_base" in resp.get_json().get("details", {})

    def test_post_empty_body_no_op(self, client):
        old_version = runtime_settings.ai_processing_version
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert runtime_settings.ai_processing_version == old_version

    def test_post_api_key_null_deletes(self, client):
        # First set a key
        client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": "sk-1234567890XX12"}),
            content_type="application/json",
        )
        # Then clear it
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": None}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["api_key_masked"] == ""

    def test_post_api_key_empty_rejected(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_post_missing_api_key_preserves_existing(self, client):
        """POST without api_key field → existing key preserved (not cleared)."""
        client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": "sk-1234567890XX12"}),
            content_type="application/json",
        )
        # POST other fields without api_key
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai", "model": "gpt-4o"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        get_resp = client.get("/v1/settings/description")
        # api_key still present and masked
        assert get_resp.get_json()["api_key_masked"] == "sk-***XX12"

    def test_post_bumps_version_only_on_change(self, client):
        old_version = runtime_settings.ai_processing_version
        # Post same value as default
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "local"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert runtime_settings.ai_processing_version == old_version

    def test_post_invalidates_factory_cache_on_change(self, client):
        """A real change must invalidate factory._instances['description']."""
        # Seed the cache
        factory._instances["description"] = "fake_provider_instance"
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert "description" not in factory._instances

    def test_post_no_factory_invalidate_on_no_op(self, client):
        """A no-op POST must NOT clear the factory cache."""
        factory._instances["description"] = "fake_provider_instance"
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "local"}),  # already effective
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert factory._instances.get("description") == "fake_provider_instance"

    def test_post_sqlite_failure_returns_500(self, client):
        """If SQLite write raises, return 500 + form preserved."""
        from openrecall.server import runtime_config as rc

        # Snapshot effective state
        before = client.get("/v1/settings/description").get_json()

        with patch.object(
            rc._settings_store, "apply_changes", side_effect=RuntimeError("db locked")
        ):
            resp = client.post(
                "/v1/settings/description",
                data=json.dumps({"provider": "openai"}),
                content_type="application/json",
            )
        assert resp.status_code == 500
        assert resp.get_json().get("code") == "internal_error"

        # GET still returns the previous effective state
        after = client.get("/v1/settings/description").get_json()
        assert after["provider"] == before["provider"]
        assert after["source"]["provider"] == before["source"]["provider"]

    # ---------- Reset ----------

    def test_reset_deletes_sqlite_rows(self, client):
        # Set a value first
        client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai"}),
            content_type="application/json",
        )
        # Reset
        resp = client.post("/v1/settings/description/reset")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "local"  # falls back to default
        assert data["source"]["provider"] == "default"

    def test_reset_no_op_does_not_bump_version(self, client):
        """Reset on a clean DB (no SQLite rows) must NOT bump version."""
        old_version = runtime_settings.ai_processing_version
        resp = client.post("/v1/settings/description/reset")
        assert resp.status_code == 200
        # Nothing was effectively changed
        assert runtime_settings.ai_processing_version == old_version

    def test_reset_bumps_version_when_changes_effective(self, client):
        """Reset with actual SQLite override → version bumps."""
        client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai"}),
            content_type="application/json",
        )
        version_after_post = runtime_settings.ai_processing_version
        resp = client.post("/v1/settings/description/reset")
        assert resp.status_code == 200
        assert runtime_settings.ai_processing_version > version_after_post

    # ---------- Test endpoint ----------

    def test_test_endpoint_does_not_write(self, client):
        with patch("openrecall.server.api_v1._probe_provider") as mock_probe:
            mock_probe.return_value = {"ok": True, "latency_ms": 100, "detail": "ok"}
            resp = client.post(
                "/v1/settings/description/test",
                data=json.dumps({
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "request_timeout": 30,
                }),
                content_type="application/json",
            )
        assert resp.status_code == 200
        # Verify GET still returns defaults (no write happened)
        get_resp = client.get("/v1/settings/description")
        assert get_resp.get_json()["provider"] == "local"

    def test_test_endpoint_success(self, client):
        """Successful probe → 200 + ok:true + latency_ms + detail."""
        with patch("openrecall.server.api_v1.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_get.return_value = mock_resp
            resp = client.post(
                "/v1/settings/description/test",
                data=json.dumps({
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_key": "sk-test1234567890",
                    "api_base": "https://api.openai.com/v1",
                    "request_timeout": 30,
                }),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "latency_ms" in data
        assert "detail" in data

    def test_test_endpoint_returns_ok_false_on_401(self, client):
        """Provider returns 401 → 200 + ok:false + error (HTTP still 200)."""
        with patch("openrecall.server.api_v1.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.reason = "Unauthorized"
            mock_get.return_value = mock_resp
            resp = client.post(
                "/v1/settings/description/test",
                data=json.dumps({
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_key": "sk-bad",
                    "api_base": "https://api.openai.com/v1",
                    "request_timeout": 30,
                }),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is False
        assert "401" in data.get("error", "")

    def test_test_endpoint_returns_ok_false_on_network_error(self, client):
        """Network timeout → 200 + ok:false + error."""
        import requests as _requests

        with patch(
            "openrecall.server.api_v1.requests.get",
            side_effect=_requests.exceptions.Timeout("read timeout"),
        ):
            resp = client.post(
                "/v1/settings/description/test",
                data=json.dumps({
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "request_timeout": 30,
                }),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is False
        assert "timeout" in data.get("error", "").lower()

    def test_test_endpoint_uses_runtime_api_key_when_omitted(self, client):
        """If api_key is omitted in the test payload, runtime_config value is used."""
        # Set api_key in SQLite first
        client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": "sk-1234567890XX12"}),
            content_type="application/json",
        )
        captured = {}

        def fake_get(url, headers=None, timeout=None):
            captured["headers"] = headers or {}
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            return mock_resp

        with patch("openrecall.server.api_v1.requests.get", side_effect=fake_get):
            resp = client.post(
                "/v1/settings/description/test",
                data=json.dumps({
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "request_timeout": 30,
                }),
                content_type="application/json",
            )
        assert resp.status_code == 200
        # Probe used the runtime api_key, not a missing/empty one
        assert captured["headers"].get("Authorization") == "Bearer sk-1234567890XX12"

    # ---------- Misc ----------

    def test_api_key_masking(self, client):
        client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": "sk-1234567890XX12"}),
            content_type="application/json",
        )
        resp = client.get("/v1/settings/description")
        data = resp.get_json()
        assert data["api_key_masked"] == "sk-***XX12"
        assert "api_key" not in data  # raw key never exposed

    def test_post_unknown_keys_ignored(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai", "unknown_field": "value"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
```

Run: `pytest tests/test_server_settings_api.py -v`
Expected: FAIL — routes not defined

- [ ] **Step 2: Implement API routes in api_v1.py**

Add the following at the end of `openrecall/server/api_v1.py` (after the last route, before any `if __name__` block):

```python
# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------

import requests  # module-level — `requests` is already a project dependency
from openrecall.server.runtime_config import _mask_api_key  # single source of truth

# Allowed provider values
_ALLOWED_DESCRIPTION_PROVIDERS = frozenset({"local", "dashscope", "openai"})

# Field validation rules
_SETTINGS_FIELD_VALIDATORS = {
    "provider": lambda v: v in _ALLOWED_DESCRIPTION_PROVIDERS,
    "model": lambda v: isinstance(v, str) and len(v.strip()) > 0,
    "api_key": lambda v: isinstance(v, str) and len(v) <= 1024,
    "api_base": lambda v: v == "" or (
        isinstance(v, str) and v.startswith(("http://", "https://")) and len(v) <= 512
    ),
    "request_timeout": lambda v: isinstance(v, int) and 1 <= v <= 600,
}

# Map flat field name to SQLite key
_FIELD_TO_KEY = {
    "provider": "description.provider",
    "model": "description.model",
    "api_key": "description.api_key",
    "api_base": "description.api_base",
    "request_timeout": "description.request_timeout",
}

# Default api_base per provider (matches frontend placeholders)
_PROVIDER_DEFAULT_API_BASE = {
    "openai": "https://api.openai.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "local": "http://localhost:11434/v1",
}


def _validate_settings_payload(
    payload: dict, allow_empty_api_key: bool = False
) -> tuple[bool, dict]:
    """Validate a settings payload. Returns (ok, details dict for errors).

    `allow_empty_api_key=True` is used by the test endpoint to permit an
    empty `api_key` value (which signals "fall through to the saved key").
    The update endpoint keeps the stricter behavior: empty api_key is a
    validation error.
    """
    details = {}
    for field, value in payload.items():
        if field not in _FIELD_TO_KEY:
            continue  # unknown keys silently ignored
        if value is None:
            continue  # null is valid (means delete)
        if value == "":
            if field == "api_base":
                continue  # empty api_base is allowed
            if field == "api_key" and allow_empty_api_key:
                continue  # test endpoint: empty key → fall back to saved
            details[field] = "cannot be empty"
            continue
        validator = _SETTINGS_FIELD_VALIDATORS.get(field)
        if validator and not validator(value):
            details[field] = _field_error_message(field, value)
    return (not details, details)


def _field_error_message(field: str, value) -> str:
    if field == "provider":
        return "must be one of: local, dashscope, openai"
    if field == "model":
        return "must be a non-empty string"
    if field == "api_key":
        return "must be a string with length <= 1024"
    if field == "api_base":
        return "must be empty or start with http:// or https://"
    if field == "request_timeout":
        return "must be an integer between 1 and 600"
    return "invalid value"


def _build_response_dict(effective: dict) -> dict:
    """Build the public response shape from a runtime_config effective dict."""
    return {
        "provider": effective["provider"],
        "model": effective["model"],
        "api_key_masked": _mask_api_key(effective["api_key"]),
        "api_base": effective["api_base"],
        "request_timeout": effective["request_timeout"],
        "source": effective["source"],
    }


@v1_bp.route("/settings/description", methods=["GET"])
def get_description_settings():
    """Get effective description settings with source tags."""
    from openrecall.server.runtime_config import get_effective_description_settings

    effective = get_effective_description_settings()
    return jsonify(_build_response_dict(effective)), 200


@v1_bp.route("/settings/description", methods=["POST"])
def update_description_settings():
    """Update description settings. Only listed fields are modified."""
    from openrecall.server.runtime_config import (
        get_effective_description_settings,
        _settings_store,
    )
    from openrecall.server.ai.factory import invalidate as factory_invalidate

    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        return make_error_response("Invalid request format", "invalid_request", 400)

    ok, details = _validate_settings_payload(payload)
    if not ok:
        return make_error_response(
            "Validation failed",
            "invalid_request",
            400,
            details=details,
        )

    effective_before = get_effective_description_settings()

    # Compute deletes & sets from the payload (no SQLite writes yet).
    deletes: list[str] = []
    sets: dict[str, str] = {}
    for field, value in payload.items():
        if field not in _FIELD_TO_KEY:
            continue
        key = _FIELD_TO_KEY[field]
        if value is None:
            if _settings_store.get(key) is not None:
                deletes.append(key)
        elif effective_before[field] == value:
            continue  # no-op: already effective; do NOT flip source toml→sqlite
        else:
            sets[key] = str(value)

    # Apply atomically. ANY SQLite failure → 500, no partial write
    # (apply_changes wraps deletes+upserts in ONE transaction; SQLite rolls back on error).
    try:
        _settings_store.apply_changes(deletes, sets)
    except Exception:
        logger.exception("SQLite write failed in update_description_settings")
        return make_error_response(
            "Storage error",
            "internal_error",
            500,
        )

    effective_after = get_effective_description_settings()

    # Compare values only (source map excluded) — version bump must reflect
    # whether functional config changed, not whether the source tag did.
    value_fields = {"provider", "model", "api_key", "api_base", "request_timeout"}
    changed = any(
        effective_before.get(f) != effective_after.get(f)
        for f in value_fields
    )

    if changed:
        try:
            factory_invalidate("description")
        except Exception:
            logger.exception("factory.invalidate failed (settings already saved)")
            # Don't fail the request — SQLite write succeeded; worker will
            # rebuild on next version bump anyway.
        runtime_settings.bump_ai_processing_version()
        logger.info(
            f"description settings updated: deletes={deletes}, sets={list(sets.keys())}, "
            f"version={runtime_settings.ai_processing_version}"
        )

    return jsonify(_build_response_dict(effective_after)), 200


@v1_bp.route("/settings/description/test", methods=["POST"])
def test_description_settings():
    """Test provider connectivity without writing to SQLite."""
    from openrecall.server.runtime_config import (
        get_description_provider,
        get_description_model,
        get_description_api_key,
        get_description_api_base,
        get_description_request_timeout,
    )

    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        return make_error_response("Invalid request format", "invalid_request", 400)

    ok, details = _validate_settings_payload(payload, allow_empty_api_key=True)
    if not ok:
        return make_error_response(
            "Validation failed", "invalid_request", 400, details=details
        )

    # Build effective config for probe.
    # Per spec test-endpoint semantics: api_key falls through to runtime_config
    # only when missing OR empty; other fields use payload value if present.
    provider = payload.get("provider", get_description_provider())
    model = payload.get("model", get_description_model())
    api_key_payload = payload.get("api_key")
    api_key = api_key_payload if api_key_payload else get_description_api_key()
    api_base = payload.get("api_base", get_description_api_base())
    timeout = payload.get("request_timeout", get_description_request_timeout())

    result = _probe_provider(provider, model, api_key, api_base, timeout)
    return jsonify(result), 200


def _probe_provider(
    provider: str, model: str, api_key: str, api_base: str, timeout: int
) -> dict:
    """Probe a provider via OpenAI-compat `GET {api_base}/models`.

    All three providers (openai, dashscope, local) speak OpenAI-compat for
    /models — this avoids token-charging probes (DashScope SDK call) and
    unifies error handling.
    """
    import time

    abs_timeout = min(int(timeout), 30)
    start = time.time()

    if provider not in _ALLOWED_DESCRIPTION_PROVIDERS:
        return {"ok": False, "error": f"Unknown provider: {provider}", "latency_ms": 0}

    base = (api_base or _PROVIDER_DEFAULT_API_BASE.get(provider, "")).rstrip("/")
    if not base:
        return {"ok": False, "error": "api_base is required", "latency_ms": 0}

    url = f"{base}/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.get(url, headers=headers, timeout=abs_timeout)
        latency_ms = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            return {
                "ok": True,
                "latency_ms": latency_ms,
                "detail": f"{provider}: reachable",
            }
        return {
            "ok": False,
            "error": f"{resp.status_code} {resp.reason}",
            "latency_ms": latency_ms,
        }
    except requests.exceptions.Timeout:
        latency_ms = int((time.time() - start) * 1000)
        return {"ok": False, "error": "timeout", "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        return {"ok": False, "error": str(e)[:200], "latency_ms": latency_ms}


@v1_bp.route("/settings/description/reset", methods=["POST"])
def reset_description_settings():
    """Reset all description settings to defaults (delete SQLite overrides)."""
    from openrecall.server.runtime_config import (
        get_effective_description_settings,
        _settings_store,
    )
    from openrecall.server.ai.factory import invalidate as factory_invalidate

    effective_before = get_effective_description_settings()

    # Single transactional reset — same atomicity guarantee as POST update.
    try:
        _settings_store.reset_to_defaults()
    except Exception:
        logger.exception("SQLite write failed in reset_description_settings")
        return make_error_response(
            "Storage error",
            "internal_error",
            500,
        )

    effective_after = get_effective_description_settings()

    value_fields = {"provider", "model", "api_key", "api_base", "request_timeout"}
    changed = any(
        effective_before.get(f) != effective_after.get(f)
        for f in value_fields
    )

    if changed:
        try:
            factory_invalidate("description")
        except Exception:
            logger.exception("factory.invalidate failed (settings already reset)")
        runtime_settings.bump_ai_processing_version()
        logger.info(
            f"description settings reset to defaults, version={runtime_settings.ai_processing_version}"
        )

    return jsonify(_build_response_dict(effective_after)), 200
```

Run: `pytest tests/test_server_settings_api.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/api_v1.py tests/test_server_settings_api.py
git commit -m "feat(settings): add /v1/settings/description endpoints (GET, POST, test, reset)"
```

---

### Task 8: Startup Wiring (`__main__.py`)

**Files:**
- Modify: `openrecall/server/__main__.py`

**Context:** The server entry point is `openrecall/server/__main__.py`. All three startup modes (`noop`, `ocr`, legacy) may start a `DescriptionWorker`:

- `_start_noop_mode()` starts `DescriptionWorker` if `settings.description_enabled=True`
- `_start_ocr_mode()` starts `DescriptionWorker` if `settings.description_enabled=True`
- Legacy mode dispatches via `init_background_worker(app)` which also starts a `DescriptionWorker`

`init_runtime_config()` MUST be called **before** any of these dispatches because the worker's first batch will read `runtime_config.get_description_*()`. We place the call in `main()` right after `ensure_v3_schema()` and before the `processing_mode` branch — this guarantees the `db/` directory exists (via `ServerSettings._ensure_dirs()`) and runs before any worker starts.

The settings.db file is independent of edge.db, so it does not depend on the v3 migrations runner. Placing the call after `ensure_v3_schema()` is conservative but clean.

- [ ] **Step 1: Add init_runtime_config to main()**

In `openrecall/server/__main__.py`, find the line `ensure_v3_schema()` inside `main()` (currently around line 225). Immediately after that line, insert:

```python
    ensure_v3_schema()

    # Initialize server-side runtime_config BEFORE any worker dispatch.
    # All three startup modes (noop, ocr, legacy) may start a DescriptionWorker,
    # whose first batch reads runtime_config.get_description_*().
    from openrecall.server.runtime_config import init_runtime_config
    init_runtime_config(settings.paths_data_dir, settings)
    logger.info("runtime_config initialized: data_dir=%s", settings.paths_data_dir)

    processing_mode = settings.processing_mode.strip().lower()
```

(The existing `processing_mode = settings.processing_mode.strip().lower()` line is already there — keep it; the insertion goes between `ensure_v3_schema()` and that line.)

- [ ] **Step 2: Verify server starts**

```bash
python -c "from openrecall.server.app import app; print('app loaded OK')"
```

Expected: No errors at module-import time. (`init_runtime_config` is called inside `main()`, so it does NOT run on bare import — module-import smoke test still passes.)

- [ ] **Step 3: Smoke-test all three modes (manual)**

```bash
# Noop mode
OPENRECALL_PROCESSING_MODE=noop python -m openrecall.server --config=server-local.toml &
SERVER_PID=$!
sleep 2
curl -s http://localhost:8083/v1/settings/description | jq .
kill $SERVER_PID
```

Expected: GET returns 200 with default config + source map (each field tagged `default` or `toml`).

Repeat with `processing_mode=ocr` (full OCR mode) — the same GET must work. The legacy mode is implicitly covered by the existing `app.run()` path.

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/__main__.py
git commit -m "feat(settings): wire init_runtime_config into server startup"
```

---

### Task 9: Client UI (settings.html)

**Files:**
- Modify: `openrecall/client/web/templates/settings.html`

**Context:** Add a new "Server (Edge) Settings" section after the existing client sections. This section calls Edge API directly via CORS. Uses Alpine.js `x-data="serverSettings()"`.

- [ ] **Step 1: Add HTML section**

Insert this after the closing `</div>` of the last client section (before the `<div class="btn-group">` containing Save Changes / Reset to Default buttons), around line ~620:

```html
  <!-- Server (Edge) Settings Section -->
  <div class="settings-section" x-data="serverSettings()" x-init="initServerSettings()">
    <h2>Server (Edge) Settings</h2>

    <!-- Connection status chip -->
    <div style="margin-bottom: 16px;">
      <span
        class="status-badge"
        :class="edgeConnected ? 'status-success' : 'status-error'"
        x-text="edgeStatusText"
      ></span>
    </div>

    <div class="form-group">
      <label class="form-label">Provider</label>
      <select
        class="form-input"
        x-model="serverForm.provider"
        @change="onProviderChange()"
        :disabled="!edgeConnected"
      >
        <option value="local">Local (Ollama)</option>
        <option value="openai">OpenAI</option>
        <option value="dashscope">DashScope</option>
      </select>
      <span
        x-show="serverPristine.source && serverPristine.source.provider === 'sqlite'"
        style="font-size: 11px; color: var(--accent-color); margin-top: 4px; display: inline-block;"
      >[overridden]</span>
    </div>

    <div class="form-group">
      <label class="form-label">Model</label>
      <input
        type="text"
        class="form-input"
        x-model="serverForm.model"
        :placeholder="providerPlaceholders[serverForm.provider]?.model || ''"
        :disabled="!edgeConnected"
      >
      <span
        x-show="serverPristine.source && serverPristine.source.model === 'sqlite'"
        style="font-size: 11px; color: var(--accent-color); margin-top: 4px; display: inline-block;"
      >[overridden]</span>
    </div>

    <div class="form-group">
      <label class="form-label">API Key</label>
      <div class="form-input-group">
        <input
          :type="apiKeyEditing ? 'text' : 'password'"
          class="form-input"
          x-model="serverForm.api_key"
          :disabled="!edgeConnected || !apiKeyEditing"
          :placeholder="apiKeyEditing ? 'Enter API key' : ''"
        >
        <button
          class="btn btn-secondary"
          @click="apiKeyEditing = !apiKeyEditing"
          :disabled="!edgeConnected"
          x-text="apiKeyEditing ? 'Cancel' : 'Edit'"
        ></button>
        <button
          class="btn btn-secondary"
          @click="clearApiKey()"
          :disabled="!edgeConnected"
          title="Clear API key"
        >Clear</button>
      </div>
      <span
        x-show="serverPristine.source && serverPristine.source.api_key === 'sqlite'"
        style="font-size: 11px; color: var(--accent-color); margin-top: 4px; display: inline-block;"
      >[overridden]</span>
    </div>

    <div class="form-group">
      <label class="form-label">API Base URL</label>
      <input
        type="url"
        class="form-input"
        x-model="serverForm.api_base"
        :placeholder="providerPlaceholders[serverForm.provider]?.api_base || ''"
        :disabled="!edgeConnected"
      >
      <span
        x-show="serverPristine.source && serverPristine.source.api_base === 'sqlite'"
        style="font-size: 11px; color: var(--accent-color); margin-top: 4px; display: inline-block;"
      >[overridden]</span>
    </div>

    <div class="form-group">
      <label class="form-label">Request Timeout</label>
      <div style="display: flex; align-items: center; gap: 8px;">
        <input
          type="number"
          class="form-input"
          x-model="serverForm.request_timeout"
          min="1"
          max="600"
          style="width: 100px;"
          :disabled="!edgeConnected"
        >
        <span style="color: var(--text-secondary); font-size: 13px;">sec</span>
      </div>
      <span
        x-show="serverPristine.source && serverPristine.source.request_timeout === 'sqlite'"
        style="font-size: 11px; color: var(--accent-color); margin-top: 4px; display: inline-block;"
      >[overridden]</span>
    </div>

    <!-- Test result line -->
    <div x-show="testResult" style="margin-bottom: 16px;">
      <span
        class="status-badge"
        :class="testResult?.ok ? 'status-success' : 'status-error'"
        x-text="testResultText"
      ></span>
    </div>

    <div class="btn-group">
      <button
        class="btn btn-secondary"
        @click="testConnection()"
        :disabled="!edgeConnected || testing"
      >
        <span x-show="!testing">Test Connection</span>
        <span x-show="testing">Testing...</span>
      </button>
      <button
        class="btn btn-primary"
        @click="saveServerSettings()"
        :disabled="!edgeConnected || !hasServerChanges() || saving"
      >
        <span x-show="!saving">Save</span>
        <span x-show="saving">Saving...</span>
      </button>
      <button
        class="btn btn-secondary"
        @click="resetServerSettings()"
        :disabled="!edgeConnected || !hasOverrides() || saving"
      >
        Reset
      </button>
    </div>
  </div>
```

- [ ] **Step 1.5: Wire toast bridge on the parent `settingsPage()` div**

The new `serverSettings()` component is a nested Alpine `x-data` block, so its `this` does NOT inherit the parent's reactive properties. Instead of duplicating the toast UI, we bridge child→parent via Alpine's `$dispatch` (see Step 2's `showToast` implementation). The parent listens for the bubbled `show-toast` event and forwards it to its own `showToast()` method.

Modify the existing outer `<div>` in `openrecall/client/web/templates/settings.html` (currently around line 307):

```html
<div class="settings-container" x-data="settingsPage()" x-init="init()">
```

to:

```html
<div class="settings-container"
     x-data="settingsPage()"
     x-init="init()"
     @show-toast="showToast($event.detail.message, $event.detail.type)">
```

This is a one-attribute addition — no other changes to the parent component or its `showToast()` method.

- [ ] **Step 2: Add serverSettings Alpine.js component**

Add the `serverSettings()` function inside the existing `<script>` block, immediately AFTER the closing `}` of `settingsPage()` (i.e. at module scope, NOT nested inside `settingsPage()`):

```javascript
  function serverSettings() {
    return {
      serverForm: {
        provider: 'local',
        model: '',
        api_key: '',
        api_base: '',
        request_timeout: 120,
      },
      serverPristine: {
        provider: 'local',
        model: '',
        api_key: '',
        api_base: '',
        request_timeout: 120,
        source: {},
      },
      apiKeyEditing: false,
      edgeConnected: false,
      edgeStatusText: 'Connecting...',
      testing: false,
      testResult: null,
      saving: false,
      providerPlaceholders: {
        openai: { model: 'gpt-4o', api_base: 'https://api.openai.com/v1' },
        dashscope: { model: 'qwen-vl-max', api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
        local: { model: 'qwen-vl-7b', api_base: 'http://localhost:11434/v1' },
      },

      initServerSettings() {
        this.checkEdgeHealth();
        // Poll health every 30s
        setInterval(() => this.checkEdgeHealth(), 30000);
      },

      async checkEdgeHealth() {
        try {
          const url = window.EDGE_BASE_URL || 'http://localhost:8083';
          const resp = await fetch(`${url}/v1/health`, { method: 'GET' });
          if (resp.ok) {
            const wasConnected = this.edgeConnected;
            this.edgeConnected = true;
            this.edgeStatusText = 'Connected';
            if (!wasConnected) {
              this.loadServerSettings();
            }
          } else {
            this.edgeConnected = false;
            this.edgeStatusText = 'Edge unreachable';
          }
        } catch (e) {
          this.edgeConnected = false;
          this.edgeStatusText = 'Edge unreachable';
        }
      },

      async loadServerSettings() {
        if (!this.edgeConnected) return;
        try {
          const base = window.EDGE_BASE_URL || 'http://localhost:8083';
          const resp = await fetch(`${base}/v1/settings/description`);
          if (resp.ok) {
            const data = await resp.json();
            this.serverForm.provider = data.provider || 'local';
            this.serverForm.model = data.model || '';
            this.serverForm.api_key = data.api_key_masked || '';
            this.serverForm.api_base = data.api_base || '';
            this.serverForm.request_timeout = data.request_timeout || 120;
            this.serverPristine = { ...this.serverForm, source: data.source || {} };
          }
        } catch (e) {
          console.error('Failed to load server settings:', e);
        }
      },

      onProviderChange() {
        const oldProvider = this.serverPristine.provider;
        const newProvider = this.serverForm.provider;
        const oldPlaceholder = this.providerPlaceholders[oldProvider];
        const newPlaceholder = this.providerPlaceholders[newProvider];
        // Auto-update model if it matches old provider's default
        if (oldPlaceholder && newPlaceholder && this.serverForm.model === oldPlaceholder.model) {
          this.serverForm.model = newPlaceholder.model;
        }
        // Auto-update api_base if it matches old provider's default
        if (oldPlaceholder && newPlaceholder && this.serverForm.api_base === oldPlaceholder.api_base) {
          this.serverForm.api_base = newPlaceholder.api_base;
        }
      },

      hasServerChanges() {
        return (
          String(this.serverForm.provider) !== String(this.serverPristine.provider) ||
          String(this.serverForm.model) !== String(this.serverPristine.model) ||
          (this.apiKeyEditing && this.serverForm.api_key !== '') ||
          String(this.serverForm.api_base) !== String(this.serverPristine.api_base) ||
          String(this.serverForm.request_timeout) !== String(this.serverPristine.request_timeout)
        );
      },

      hasOverrides() {
        return this.serverPristine.source &&
          Object.values(this.serverPristine.source).some(s => s === 'sqlite');
      },

      async testConnection() {
        this.testing = true;
        this.testResult = null;
        try {
          const base = window.EDGE_BASE_URL || 'http://localhost:8083';
          const payload = {
            provider: this.serverForm.provider,
            model: this.serverForm.model,
            api_base: this.serverForm.api_base,
            request_timeout: parseInt(this.serverForm.request_timeout) || 120,
          };
          if (this.apiKeyEditing && this.serverForm.api_key) {
            payload.api_key = this.serverForm.api_key;
          }
          const resp = await fetch(`${base}/v1/settings/description/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          if (resp.ok) {
            this.testResult = await resp.json();
          } else {
            this.testResult = { ok: false, error: 'Request failed' };
          }
        } catch (e) {
          this.testResult = { ok: false, error: e.message || 'Connection failed' };
        } finally {
          this.testing = false;
        }
      },

      get testResultText() {
        if (!this.testResult) return '';
        if (this.testResult.ok) {
          return `✓ ${this.testResult.latency_ms}ms · ${this.testResult.detail || 'OK'}`;
        }
        return `✗ ${this.testResult.error || 'Failed'}`;
      },

      async saveServerSettings() {
        this.saving = true;
        try {
          const payload = {};
          for (const k of Object.keys(this.serverForm)) {
            if (k === 'api_key') continue;
            const a = String(this.serverForm[k]);
            const b = String(this.serverPristine[k]);
            if (a !== b) {
              payload[k] = k === 'request_timeout' ? (parseInt(this.serverForm[k]) || 120) : this.serverForm[k];
            }
          }
          if (this.apiKeyEditing && this.serverForm.api_key) {
            payload.api_key = this.serverForm.api_key;
          }
          const base = window.EDGE_BASE_URL || 'http://localhost:8083';
          const resp = await fetch(`${base}/v1/settings/description`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          if (resp.ok) {
            const data = await resp.json();
            this.serverPristine = {
              provider: data.provider,
              model: data.model,
              api_key: data.api_key_masked || '',
              api_base: data.api_base,
              request_timeout: data.request_timeout,
              source: data.source,
            };
            this.apiKeyEditing = false;
            this.showToast('Server settings saved', 'success');
          } else {
            const err = await resp.json();
            this.showToast(err.error || 'Save failed', 'error');
          }
        } catch (e) {
          console.error('Save failed:', e);
          this.showToast('Save failed', 'error');
        } finally {
          this.saving = false;
        }
      },

      clearApiKey() {
        if (!confirm('Clear API key?')) return;
        this.serverForm.api_key = '';
        this.apiKeyEditing = false;
        this.saveServerSettingsWithKey(null);
      },

      async saveServerSettingsWithKey(apiKeyValue) {
        this.saving = true;
        try {
          const base = window.EDGE_BASE_URL || 'http://localhost:8083';
          const resp = await fetch(`${base}/v1/settings/description`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKeyValue }),
          });
          if (resp.ok) {
            const data = await resp.json();
            this.serverPristine.api_key = data.api_key_masked || '';
            this.serverPristine.source = data.source;
          }
        } catch (e) {
          console.error('Clear API key failed:', e);
        } finally {
          this.saving = false;
        }
      },

      async resetServerSettings() {
        if (!confirm('Reset all description settings to defaults? Workers will switch to TOML config.')) {
          return;
        }
        this.saving = true;
        try {
          const base = window.EDGE_BASE_URL || 'http://localhost:8083';
          const resp = await fetch(`${base}/v1/settings/description/reset`, { method: 'POST' });
          if (resp.ok) {
            const data = await resp.json();
            this.serverForm.provider = data.provider;
            this.serverForm.model = data.model;
            this.serverForm.api_key = data.api_key_masked || '';
            this.serverForm.api_base = data.api_base;
            this.serverForm.request_timeout = data.request_timeout;
            this.serverPristine = { ...this.serverForm, source: data.source };
            this.apiKeyEditing = false;
            this.showToast('Server settings reset to defaults', 'success');
          } else {
            this.showToast('Reset failed', 'error');
          }
        } catch (e) {
          console.error('Reset failed:', e);
          this.showToast('Reset failed', 'error');
        } finally {
          this.saving = false;
        }
      },

      // Bridge child-component toast messages to the parent settingsPage()'s
      // toast UI via an Alpine custom event. The parent's outer div listens
      // (see Step 1.5 above) and forwards the message to its own showToast().
      showToast(message, type) {
        this.$dispatch('show-toast', { message, type });
      },
    };
  }
```

- [ ] **Step 3: Verify HTML syntax**

Open the settings page in a browser (or check with a basic syntax check):

```bash
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('openrecall/client/web/templates'))
tmpl = env.get_template('settings.html')
print('Template parses OK')
"
```

Expected: `Template parses OK`

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/templates/settings.html
git commit -m "feat(settings): add Server Settings UI section with provider/model config"
```

---

### Task 10: Regression Test Run

- [ ] **Step 1: Run all existing tests**

```bash
pytest tests/test_description_provider.py tests/test_description_models.py tests/test_chat_mvp_*.py -v --tb=short
```

Expected: PASS (or known failures documented)

- [ ] **Step 2: Run all new tests**

```bash
pytest tests/test_server_settings_store.py tests/test_server_runtime_config.py tests/test_server_settings_mask.py tests/test_server_settings_api.py tests/test_ai_factory_invalidate.py tests/test_description_worker_hot_reload.py -v --tb=short
```

Expected: ALL PASS

- [ ] **Step 3: Run full test suite**

```bash
pytest -x --tb=short
```

Expected: PASS (fix any regressions before proceeding)

- [ ] **Step 4: Commit**

```bash
git commit -m "test(settings): add comprehensive tests for server settings hot-reload"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Section | Plan Task |
|---|---|
| ServerSettingsStore (sparse table, set_many) | Task 1 |
| runtime_config.py (getters + source tags) | Task 2 |
| config_server.py (description_request_timeout) | Task 3 |
| config_runtime.py (bump_ai_processing_version) | Task 3 |
| ai/factory.py (invalidate + double-checked locking) | Task 4 |
| description/providers/openai.py (timeout read) | Task 5 |
| description/worker.py (version check) | Task 6 |
| api_v1.py (4 routes) | Task 7 |
| `__main__.py` startup wiring | Task 8 |
| settings.html (server section) | Task 9 |
| Test-Connection probe | Task 7 (in _probe_provider) |
| Reset-to-defaults | Task 7 (reset route) |
| Masking | Task 2 (_mask_api_key) + Task 7 (GET response) |
| Dirty-only POST | Task 9 (frontend) |
| Source tags | Task 2 (runtime_config) + Task 7 (GET response) + Task 9 (UI chips) |

### Placeholder Scan

- No "TBD", "TODO", "implement later" in plan
- No "Add appropriate error handling" without code
- No "Write tests for the above" without test code
- All file paths are exact
- All function signatures match across tasks

### Type Consistency

- `ServerSettingsStore.DEFAULTS` — `dict[str, str]` in Task 1, referenced in Task 2
- `_settings_store` — module-level singleton in Task 2, used in Task 7
- `_toml_settings` — `ServerSettings` type in Task 2, initialized with `ServerSettings` in Task 7 tests
- `get_description_*()` functions — return types match usage in Task 4 (factory.py)
- `ai_processing_version` — `int` everywhere (Task 3, Task 6, Task 7)
- `_mask_api_key` — defined in Task 2, used in Task 7

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-02-server-settings-hot-reload.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review

**Which approach?**
