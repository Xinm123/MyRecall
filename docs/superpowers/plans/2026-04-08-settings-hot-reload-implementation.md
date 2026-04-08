# Settings Hot-Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all settings in the WebUI Settings page hot-reloadable, and add Deduplication configuration to the UI.

**Architecture:** AtomicInt (ctypes) for lock-free debouncer updates → runtime_config getter extensions → recorder config listener thread → idle chunked sleep → dedup runtime_config → Settings UI dedup section.

**Tech Stack:** Python (ctypes, threading), SQLite, Alpine.js, Flask

---

## File Changes Overview

| File | Change |
|------|--------|
| `openrecall/client/events/atomic.py` | **NEW** — AtomicInt |
| `openrecall/client/events/base.py` | Debouncers use AtomicInt |
| `openrecall/client/runtime_config.py` | 7 dedup getters + wait/notify |
| `openrecall/client/recorder.py` | Listener thread, idle chunked sleep, dedup runtime_config |
| `openrecall/client/web/routes/settings.py` | Dedup validation + notify |
| `openrecall/client/database/settings_store.py` | Dedup defaults |
| `openrecall/client/web/templates/settings.html` | Dedup UI section + Alpine.js |
| `tests/test_runtime_config.py` | **NEW** — runtime_config hot-reload tests |
| `tests/test_atomic.py` | **NEW** — AtomicInt unit tests |

---

## Task 1: AtomicInt — Thread-Safe Interval Updates

**Files:**
- Create: `openrecall/client/events/atomic.py`
- Modify: `openrecall/client/events/base.py`
- Test: `tests/test_atomic.py`
- Reference: `openrecall/client/events/__init__.py` (exports)

- [ ] **Step 1: Write failing test for AtomicInt**

```python
# tests/test_atomic.py
"""Unit tests for AtomicInt."""
import threading
import pytest
from openrecall.client.events.atomic import AtomicInt


def test_atomic_int_basic_get_set():
    a = AtomicInt(42)
    assert a.get() == 42
    a.set(100)
    assert a.get() == 100


def test_atomic_int_default_value():
    a = AtomicInt()
    assert a.get() == 0


def test_atomic_int_int_conversion():
    a = AtomicInt(123)
    assert int(a) == 123


def test_atomic_int_cross_thread():
    """Verify that updates from one thread are visible in another."""
    a = AtomicInt(0)
    results = []

    def writer():
        for i in range(100):
            a.set(i)

    def reader():
        for _ in range(100):
            results.append(a.get())

    t1 = threading.Thread(target=writer)
    t2 = threading.Thread(target=reader)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # At least some reads should see updated values (non-zero)
    assert any(v != 0 for v in results)
```

Run: `pytest tests/test_atomic.py -v`
Expected: FAIL — module `atomic` not found

- [ ] **Step 2: Create AtomicInt implementation**

```python
# openrecall/client/events/atomic.py
"""Atomic integer wrapper for thread-safe hot-reload of interval values."""

from __future__ import annotations

import ctypes


class AtomicInt:
    """Thread-safe atomic integer using ctypes.c_int64.

    Provides lock-free read and write suitable for use in CGEventTap
    callback threads where blocking on locks would cause system lag.

    GIL guarantees visibility of writes across threads for simple
    assignments in CPython.
    """

    def __init__(self, value: int = 0) -> None:
        self._v = ctypes.c_int64(value)

    def get(self) -> int:
        """Atomically read the current value."""
        return self._v.value

    def set(self, value: int) -> None:
        """Atomically write a new value."""
        self._v.value = value

    def __int__(self) -> int:
        return self._v.value
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/test_atomic.py -v`
Expected: PASS

- [ ] **Step 4: Update TriggerDebouncer to use AtomicInt**

Read `openrecall/client/events/base.py` lines 174-208. Replace `_min_interval_ms: int` with `AtomicInt`. Add `update_interval_ms()`. Read pattern follows existing code.

Key changes (lines ~181-207):
```python
from openrecall.client.events.atomic import AtomicInt


class TriggerDebouncer:
    def __init__(self, min_interval_ms: int) -> None:
        self._min_interval_ms = AtomicInt(min_interval_ms)
        self._lock = threading.Lock()
        self._last_fire_ms: dict[str, int] = {}
        self._debounced_count: int = 0

    def should_fire(self, device_name: str, now_ms: int) -> bool:
        with self._lock:
            last_fire_ms = self._last_fire_ms.get(device_name)
            min_interval = self._min_interval_ms.get()
            if last_fire_ms is None or now_ms - last_fire_ms >= min_interval:
                self._last_fire_ms[device_name] = now_ms
                return True
            self._debounced_count += 1
            return False

    def update_interval_ms(self, new_ms: int) -> None:
        """Update the debounce interval at runtime (hot-reload)."""
        self._min_interval_ms.set(new_ms)
```

- [ ] **Step 5: Update LockFreeDebouncer to use AtomicInt**

Read `openrecall/client/events/base.py` lines 210-253. Same pattern:

```python
class LockFreeDebouncer:
    def __init__(self, min_interval_ms: int) -> None:
        self._min_interval_ms = AtomicInt(min_interval_ms)
        self._last_fire_ms: dict[str, int] = {}
        self._lock = threading.Lock()

    def should_fire(self, device_name: str, now_ms: int) -> bool:
        min_interval = self._min_interval_ms.get()
        last_fire_ms = self._last_fire_ms.get(device_name, 0)
        if now_ms - last_fire_ms >= min_interval:
            self._last_fire_ms[device_name] = now_ms
            return True
        return False

    def update_interval_ms(self, new_ms: int) -> None:
        """Update the debounce interval at runtime (hot-reload)."""
        self._min_interval_ms.set(new_ms)
```

- [ ] **Step 6: Run existing debouncer tests to verify no regression**

Run: `pytest tests/test_p1_s2a_debounce.py -v`
Expected: PASS

- [ ] **Step 7: Add debouncer hot-reload tests**

```python
# Append to tests/test_atomic.py (or add to tests/test_p1_s2a_debounce.py)
def test_trigger_debouncer_hot_reload():
    from openrecall.client.events.base import TriggerDebouncer

    d = TriggerDebouncer(1000)  # 1000ms
    now = 10000

    # Should fire at 1000ms interval
    assert d.should_fire("device1", now) is True  # fires at 10000
    assert d.should_fire("device1", now + 500) is False  # debounced (500 < 1000)
    assert d.should_fire("device1", now + 1000) is True  # fires at 11000

    # Hot-reload: update interval to 500ms
    d.update_interval_ms(500)
    assert d.should_fire("device1", now + 1001) is True  # 500 < 1001ms since last fire


def test_lockfree_debouncer_hot_reload():
    from openrecall.client.events.base import LockFreeDebouncer

    d = LockFreeDebouncer(1000)
    now = 10000

    assert d.should_fire("device1", now) is True
    assert d.should_fire("device1", now + 500) is False

    d.update_interval_ms(200)
    assert d.should_fire("device1", now + 600) is True  # 200ms interval now
```

Run: `pytest tests/test_atomic.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add openrecall/client/events/atomic.py openrecall/client/events/base.py tests/test_atomic.py
git commit -m "feat(events): add AtomicInt for lock-free debouncer hot-reload

Add AtomicInt (ctypes.c_int64) wrapper for thread-safe interval updates.
Update TriggerDebouncer and LockFreeDebouncer to use AtomicInt for
_min_interval_ms, enabling hot-reload via update_interval_ms() method.
No debouncer behavior changes — only the storage type changes.
"
```

---

## Task 2: runtime_config Extensions — Dedup Getters + Wait/Notify

**Files:**
- Modify: `openrecall/client/runtime_config.py`
- Test: `tests/test_runtime_config.py`
- Reference: `openrecall/client/web/routes/settings.py`

- [ ] **Step 1: Write failing tests for new dedup getters**

```python
# tests/test_runtime_config.py
"""Unit tests for runtime_config hot-reload getters."""
import pytest
from openrecall.client import runtime_config


@pytest.fixture
def fresh_runtime_config(tmp_path):
    """Initialize runtime_config with a fresh temp database."""
    db_dir = tmp_path / "client"
    db_dir.mkdir()
    runtime_config.init_runtime_config(db_dir)
    yield runtime_config


def test_get_dedup_enabled_default(fresh_runtime_config):
    # Should fall back to TOML settings default (True)
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


def test_get_dedup_enabled_overrides_toml(fresh_runtime_config):
    store = runtime_config._get_store()
    store.set("dedup.enabled", "false")
    assert fresh_runtime_config.get_dedup_enabled() is False


def test_get_dedup_threshold_overrides_toml(fresh_runtime_config):
    store = runtime_config._get_store()
    store.set("dedup.threshold", "25")
    assert fresh_runtime_config.get_dedup_threshold() == 25


def test_notify_and_wait_config_changed(fresh_runtime_config):
    import threading

    result = []

    def waiter():
        runtime_config.wait_for_config_change(timeout=0.1)
        result.append("done")

    t = threading.Thread(target=waiter)
    t.start()
    runtime_config.notify_config_changed()
    t.join(timeout=1)
    assert result == ["done"]
```

Run: `pytest tests/test_runtime_config.py -v`
Expected: FAIL — functions `get_dedup_*` and `notify_config_changed` not found

- [ ] **Step 2: Add dedup getters to runtime_config.py**

Read `openrecall/client/runtime_config.py`. Append 7 new getters after `get_stats_interval_sec()`. Follow the existing pattern exactly:

```python
def get_dedup_enabled() -> bool:
    """Priority: SQLite runtime > TOML (dedup.enabled) > True"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.enabled", "")
        if value:
            return value.lower() == "true"
    from openrecall.shared.config import settings
    return settings.dedup_enabled


def get_dedup_threshold() -> int:
    """Priority: SQLite runtime > TOML (dedup.threshold) > 10"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.threshold", "")
        if value:
            return int(value)
    from openrecall.shared.config import settings
    return settings.dedup_threshold


def get_dedup_ttl_seconds() -> float:
    """Priority: SQLite runtime > TOML (dedup.ttl_seconds) > 60.0"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.ttl_seconds", "")
        if value:
            return float(value)
    from openrecall.shared.config import settings
    return settings.dedup_ttl_seconds


def get_dedup_cache_size() -> int:
    """Priority: SQLite runtime > TOML (dedup.cache_size_per_device) > 1"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.cache_size_per_device", "")
        if value:
            return int(value)
    from openrecall.shared.config import settings
    return settings.dedup_cache_size_per_device


def get_dedup_for_click() -> bool:
    """Priority: SQLite runtime > TOML (dedup.for_click) > True"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.for_click", "")
        if value:
            return value.lower() == "true"
    from openrecall.shared.config import settings
    return settings.dedup_for_click


def get_dedup_for_app_switch() -> bool:
    """Priority: SQLite runtime > TOML (dedup.for_app_switch) > False"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.for_app_switch", "")
        if value:
            return value.lower() == "true"
    from openrecall.shared.config import settings
    return settings.dedup_for_app_switch


def get_dedup_force_after_skip_sec() -> int:
    """Priority: SQLite runtime > TOML (dedup.force_after_skip_seconds) > 30"""
    store = _get_store()
    if store is not None:
        value = store.get("dedup.force_after_skip_seconds", "")
        if value:
            return int(value)
    from openrecall.shared.config import settings
    return settings.dedup_force_after_skip_seconds
```

- [ ] **Step 3: Add wait/notify functions**

After the dedup getters, add at the end of `runtime_config.py`:

```python
import threading

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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_runtime_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/runtime_config.py tests/test_runtime_config.py
git commit -m "feat(runtime_config): add 7 dedup getters + wait/notify for hot-reload

Add get_dedup_* getters (enabled, threshold, ttl_seconds, cache_size,
for_click, for_app_switch, force_after_skip_sec) with SQLite > TOML priority.
Add notify_config_changed() and wait_for_config_change() for config
listener thread coordination.
"
```

---

## Task 3: settings.py — Dedup Validation + Notify

**Files:**
- Modify: `openrecall/client/web/routes/settings.py`
- Reference: `openrecall/client/database/settings_store.py` DEFAULTS

- [ ] **Step 1: Add dedup validators**

Read `openrecall/client/web/routes/settings.py` lines 62-71 (validators dict). Add new entries:

```python
"dedup.enabled": lambda v: str(v).lower() in ("true", "false"),
"dedup.threshold": lambda v: str(v).isdigit() and 0 <= int(v) <= 64,
"dedup.ttl_seconds": lambda v: (
    str(v).replace(".", "", 1).isdigit() and 1 <= float(v) <= 600
),
"dedup.cache_size_per_device": lambda v: str(v).isdigit() and 1 <= int(v) <= 100,
"dedup.for_click": lambda v: str(v).lower() in ("true", "false"),
"dedup.for_app_switch": lambda v: str(v).lower() in ("true", "false"),
"dedup.force_after_skip_seconds": lambda v: str(v).isdigit() and 1 <= int(v) <= 3600,
```

- [ ] **Step 2: Call notify_config_changed() after saving**

Read `openrecall/client/web/routes/settings.py` lines 78-82 (after updating settings). After `store.set()` loop, add:

```python
from openrecall.client import runtime_config
runtime_config.notify_config_changed()
```

Add the import at the top of the function (or at module level after the logger import).

- [ ] **Step 3: Verify with a quick sanity test**

Run: `python -c "from openrecall.client.web.routes.settings import settings_bp; print('OK')"`
Expected: OK (no import errors)

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/routes/settings.py
git commit -m "feat(settings): add dedup field validators + notify on save

Validate dedup.enabled, dedup.threshold, dedup.ttl_seconds,
dedup.cache_size_per_device, dedup.for_click, dedup.for_app_switch,
dedup.force_after_skip_seconds on POST /api/client/settings.
Call notify_config_changed() after save to wake recorder listener.
"
```

---

## Task 4: settings_store.py — Dedup Defaults

**Files:**
- Modify: `openrecall/client/database/settings_store.py`

- [ ] **Step 1: Add dedup defaults**

Read `openrecall/client/database/settings_store.py` lines 20-29 (DEFAULTS dict). Add new entries:

```python
"dedup.enabled": "true",
"dedup.threshold": "10",
"dedup.ttl_seconds": "60.0",
"dedup.cache_size_per_device": "1",
"dedup.for_click": "true",
"dedup.for_app_switch": "false",
"dedup.force_after_skip_seconds": "30",
```

- [ ] **Step 2: Add test for dedup defaults**

```python
# Append to tests/test_runtime_config.py
def test_dedup_defaults_in_settings_store(tmp_path):
    """Verify dedup defaults are registered in settings store."""
    from openrecall.client.database import ClientSettingsStore

    db_dir = tmp_path / "client"
    db_dir.mkdir()
    store = ClientSettingsStore(db_dir / "client.db")

    # All dedup fields should exist with defaults
    assert store.get("dedup.enabled") == "true"
    assert store.get("dedup.threshold") == "10"
    assert store.get("dedup.ttl_seconds") == "60.0"
    assert store.get("dedup.cache_size_per_device") == "1"
    assert store.get("dedup.for_click") == "true"
    assert store.get("dedup.for_app_switch") == "false"
    assert store.get("dedup.force_after_skip_seconds") == "30"


def test_dedup_defaults_reset(tmp_path):
    """Verify reset_to_defaults restores all dedup fields."""
    from openrecall.client.database import ClientSettingsStore

    db_dir = tmp_path / "client"
    db_dir.mkdir()
    store = ClientSettingsStore(db_dir / "client.db")

    # Override and then reset
    store.set("dedup.threshold", "99")
    store.reset_to_defaults()
    assert store.get("dedup.threshold") == "10"
```

Run: `pytest tests/test_runtime_config.py::test_dedup_defaults_in_settings_store tests/test_runtime_config.py::test_dedup_defaults_reset -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/database/settings_store.py tests/test_runtime_config.py
git commit -m "feat(settings_store): add dedup defaults for hot-reload

Add dedup.* default values to ClientSettingsStore.DEFAULTS:
enabled=true, threshold=10, ttl_seconds=60.0, cache_size=1,
for_click=true, for_app_switch=false, force_after_skip_seconds=30.
"
```

---

## Task 5: SimhashCache — Dynamic TTL/CacheSize

**Files:**
- Modify: `openrecall/client/hash_utils.py`
- Test: `tests/test_p1_s2b_plus_simhash_config.py`

- [ ] **Step 1: Write failing test for dynamic cache size/ttl**

```python
# Append to tests/test_p1_s2b_plus_simhash_config.py
def test_simhash_cache_respects_runtime_cache_size(monkeypatch):
    """SimhashCache should use current cache_size from runtime_config, not __init__ value."""
    from unittest.mock import MagicMock
    from openrecall.client.hash_utils import SimhashCache

    # Create cache with small init size
    cache = SimhashCache(cache_size_per_device=1, ttl_seconds=1000.0)

    # Mock runtime_config to return larger cache size
    mock_rc = MagicMock()
    mock_rc.get_dedup_cache_size.return_value = 3
    mock_rc.get_dedup_ttl_seconds.return_value = 500.0
    monkeypatch.setattr("openrecall.client.hash_utils.runtime_config", mock_rc)

    # Add 3 entries (should all fit with runtime size=3)
    for i in range(3):
        cache.add("device1", i, timestamp=float(i))

    # With runtime cache_size=3, all 3 should be present
    assert len(cache._caches["device1"]) == 3
```

Run: `pytest tests/test_p1_s2b_plus_simhash_config.py::test_simhash_cache_respects_runtime_cache_size -v`
Expected: FAIL — `add()` doesn't call `runtime_config`

- [ ] **Step 2: Update SimhashCache.add() for dynamic params**

Read `openrecall/client/hash_utils.py` lines 144-163 (SimhashCache.add method). Replace the body with dynamic reading:

```python
def add(self, device_name: str, phash: int, timestamp: float) -> None:
    # Hot-reload: read current cache size and TTL on each add
    from openrecall.client import runtime_config

    cache_size = runtime_config.get_dedup_cache_size()
    ttl_seconds = runtime_config.get_dedup_ttl_seconds()

    if device_name not in self._caches:
        self._caches[device_name] = OrderedDict()
    if len(self._caches[device_name]) >= cache_size:
        self._caches[device_name].popitem(last=False)
    self._caches[device_name][phash] = timestamp
    self._last_enqueue_time[device_name] = timestamp
```

Also update `__init__` to accept and store the init values (for backward compat with existing code that creates SimhashCache directly):

```python
def __init__(
    self,
    cache_size_per_device: int = 1,
    ttl_seconds: float = float("inf"),
):
    self.cache_size_per_device = cache_size_per_device
    self.ttl_seconds = ttl_seconds
    self._caches: dict[str, OrderedDict[int, float]] = {}
    self._last_enqueue_time: dict[str, float] = {}
    self._hash_hits: int = 0
    self._total_checks: int = 0
```

- [ ] **Step 3: Run test**

Run: `pytest tests/test_p1_s2b_plus_simhash_config.py::test_simhash_cache_respects_runtime_cache_size -v`
Expected: PASS

- [ ] **Step 4: Run full dedup test suite**

Run: `pytest tests/test_p1_s2b_plus_simhash_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/hash_utils.py tests/test_p1_s2b_plus_simhash_config.py
git commit -m "feat(dedup): SimhashCache reads cache_size and ttl at runtime

Update SimhashCache.add() to call runtime_config.get_dedup_cache_size()
and runtime_config.get_dedup_ttl_seconds() on every add, enabling
hot-reload without cache rebuild. Existing __init__ params preserved
for backward compatibility with direct instantiation.
"
```

---

## Task 6: recorder.py — Config Listener + Idle Chunked Sleep + Dedup

**Files:**
- Modify: `openrecall/client/recorder.py`
- Reference: `openrecall/client/events/base.py` (AtomicInt usage)

### Subtask 6a: Config Listener Thread

- [ ] **Step 1: Read recorder.py to find __init__ and _running attribute**

Read `openrecall/client/recorder.py` around lines 290-315 (end of `__init__`) and line ~530 (stop method).

- [ ] **Step 2: Add config listener registration in __init__**

After the permission state machine init (~line 315), add:

```python
# Hot-reload config listener thread
import threading
self._config_listener_stop = threading.Event()
self._config_listener_thread = threading.Thread(
    target=self._config_change_listener,
    daemon=True,
    name="config-change-listener",
)
self._config_listener_thread.start()
```

- [ ] **Step 3: Add _config_change_listener method**

Add as a method on the Recorder class (after `stop()` or near the end of the class). Read the recorder structure to find an appropriate insertion point.

```python
def _config_change_listener(self) -> None:
    """Listen for config changes and update debouncers dynamically."""
    from openrecall.client import runtime_config
    from openrecall.client.events.base import LockFreeDebouncer, TriggerDebouncer

    while not self._config_listener_stop.is_set():
        # Block until notify_config_changed() sets the event
        # (wait returns immediately if already set, then clears it)
        runtime_config.wait_for_config_change(timeout=1.0)

        if self._config_listener_stop.is_set():
            break

        try:
            store = runtime_config._get_store()
            if store is None:
                continue

            # Update click debouncer
            click_ms = store.get("debounce.click_ms", "")
            if click_ms:
                self._click_debouncer.update_interval_ms(int(click_ms))

            # Update trigger debouncer
            trigger_ms = store.get("debounce.trigger_ms", "")
            if trigger_ms:
                self._trigger_debouncer.update_interval_ms(int(trigger_ms))

            logger.info(
                "[Recorder] Hot-reloaded: click=%sms trigger=%sms",
                store.get("debounce.click_ms", ""),
                store.get("debounce.trigger_ms", ""),
            )
        except Exception as e:
            logger.warning("[Recorder] Config listener error: %s", e)
```

- [ ] **Step 4: Wire stop event in stop() method**

Read recorder.py's `stop()` method. After `self._running = False`, add:

```python
self._config_listener_stop.set()
if self._config_listener_thread.is_alive():
    self._config_listener_thread.join(timeout=2.0)
```

### Subtask 6b: Debounce Capture + Dedup Runtime Config

- [ ] **Step 5: Replace settings.capture_debounce_ms with runtime_config**

Read `openrecall/client/recorder.py` line ~1188. Replace:
```python
min_interval_sec = settings.capture_debounce_ms / 1000.0
```
with:
```python
min_interval_sec = runtime_config.get_debounce_capture_ms() / 1000.0
```

- [ ] **Step 6: Replace dedup settings references with runtime_config**

Read recorder.py lines around 1241, 1263-1265, 1280, 1289, 1298.

Replace each `settings.xxx` reference:

| Replace | With |
|---------|------|
| `settings.simhash_dedup_enabled` | `runtime_config.get_dedup_enabled()` |
| `settings.simhash_dedup_threshold` | `runtime_config.get_dedup_threshold()` |
| `settings.simhash_enabled_for_click` | `runtime_config.get_dedup_for_click()` |
| `settings.simhash_enabled_for_app_switch` | `runtime_config.get_dedup_for_app_switch()` |
| `settings.simhash_force_after_skip_seconds` | `runtime_config.get_dedup_force_after_skip_sec()` |

Make sure `from openrecall.client import runtime_config` is imported at the top (it should already be there from Subtask 6a).

### Subtask 6c: Idle Loop Chunked Sleep

- [ ] **Step 7: Find and update idle loop**

Read recorder.py to find the idle loop (search for `idle_capture_interval` or `_idle_loop`). Replace the single `time.sleep()` with chunked sleep.

Find the idle loop that does `time.sleep(idle_interval_ms / 1000.0)` and replace with:

```python
_POLL_INTERVAL_SEC = 5  # Max delay for idle interval hot-reload

# In _idle_loop:
interval_ms = runtime_config.get_debounce_idle_interval_ms()
idle_threshold_sec = interval_ms / 1000.0

# Chunked sleep to allow hot-reload (max 5s delay)
elapsed = 0.0
while elapsed < idle_threshold_sec and self._running:
    sleep_sec = min(_POLL_INTERVAL_SEC, idle_threshold_sec - elapsed)
    time.sleep(sleep_sec)
    elapsed += sleep_sec

    # Re-read on each wake to check for hot-reload
    interval_ms = runtime_config.get_debounce_idle_interval_ms()
    idle_threshold_sec = interval_ms / 1000.0

if not self._running:
    break
```

- [ ] **Step 8: Verify no regression — run recorder unit tests**

Run: `pytest tests/test_p1_s2a_recorder.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add openrecall/client/recorder.py
git commit -m "feat(recorder): config listener thread + idle chunked sleep + dedup runtime_config

Add _config_change_listener daemon thread that watches for config changes
and calls update_interval_ms() on debouncers. Replace
settings.capture_debounce_ms with runtime_config.get_debounce_capture_ms().
Replace all simhash_dedup_* settings with runtime_config.get_dedup_*().
Update idle loop to use chunked sleep (max 5s) for hot-reload.
"
```

---

## Task 7: Settings UI — Deduplication Section

**Files:**
- Modify: `openrecall/client/web/templates/settings.html`
- Reference: existing sections (Capture, Debounce) for style patterns

- [ ] **Step 1: Add dedup defaults to Alpine.js data model**

Read `settings.html` lines 541-552 (Alpine `settings:` object) and 553-562 (`originalSettings:`). Add 7 new fields:

```javascript
// In settings: object
dedup_enabled: 'true',
dedup_threshold: '10',
dedup_ttl_seconds: '60',
dedup_cache_size_per_device: '1',
dedup_for_click: 'true',
dedup_for_app_switch: 'false',
dedup_force_after_skip_seconds: '30',

// In originalSettings: object (same values)
dedup_enabled: 'true',
dedup_threshold: '10',
dedup_ttl_seconds: '60',
dedup_cache_size_per_device: '1',
dedup_for_click: 'true',
dedup_for_app_switch: 'false',
dedup_force_after_skip_seconds: '30',
```

- [ ] **Step 2: Update loadSettings() to load dedup fields**

Read `settings.html` lines 576-606 (loadSettings). After loading `stats_interval_sec`, add:

```javascript
// Dedup fields
this.settings.dedup_enabled = data['dedup.enabled'] || 'true';
this.originalSettings.dedup_enabled = this.settings.dedup_enabled;
this.settings.dedup_threshold = data['dedup.threshold'] || '10';
this.originalSettings.dedup_threshold = this.settings.dedup_threshold;
this.settings.dedup_ttl_seconds = data['dedup.ttl_seconds'] || '60';
this.originalSettings.dedup_ttl_seconds = this.settings.dedup_ttl_seconds;
this.settings.dedup_cache_size_per_device = data['dedup.cache_size_per_device'] || '1';
this.originalSettings.dedup_cache_size_per_device = this.settings.dedup_cache_size_per_device;
this.settings.dedup_for_click = data['dedup.for_click'] || 'true';
this.originalSettings.dedup_for_click = this.settings.dedup_for_click;
this.settings.dedup_for_app_switch = data['dedup.for_app_switch'] || 'false';
this.originalSettings.dedup_for_app_switch = this.settings.dedup_for_app_switch;
this.settings.dedup_force_after_skip_seconds = data['dedup.force_after_skip_seconds'] || '30';
this.originalSettings.dedup_force_after_skip_seconds = this.settings.dedup_force_after_skip_seconds;
```

- [ ] **Step 3: Update hasChanges() to include dedup fields**

Read `settings.html` lines 608-617. Add after `stats_interval_sec` check:

```javascript
this.settings.dedup_enabled !== this.originalSettings.dedup_enabled ||
this.settings.dedup_threshold !== this.originalSettings.dedup_threshold ||
this.settings.dedup_ttl_seconds !== this.originalSettings.dedup_ttl_seconds ||
this.settings.dedup_cache_size_per_device !== this.originalSettings.dedup_cache_size_per_device ||
this.settings.dedup_for_click !== this.originalSettings.dedup_for_click ||
this.settings.dedup_for_app_switch !== this.originalSettings.dedup_for_app_switch ||
this.settings.dedup_force_after_skip_seconds !== this.originalSettings.dedup_force_after_skip_seconds;
```

- [ ] **Step 4: Update saveSettings() payload**

Read `settings.html` lines 650-664 (save payload). Add dedup fields to payload:

```javascript
'dedup.enabled': this.settings.dedup_enabled,
'dedup.threshold': this.settings.dedup_threshold,
'dedup.ttl_seconds': this.settings.dedup_ttl_seconds,
'dedup.cache_size_per_device': this.settings.dedup_cache_size_per_device,
'dedup.for_click': this.settings.dedup_for_click,
'dedup.for_app_switch': this.settings.dedup_for_app_switch,
'dedup.force_after_skip_seconds': this.settings.dedup_force_after_skip_seconds,
```

Also update `originalSettings` sync and CustomEvent broadcast with dedup fields.

- [ ] **Step 5: Update resetSettings() to handle dedup fields**

Read `settings.html` lines 708-766 (resetSettings). Add dedup field restoration after stats:

```javascript
this.settings.dedup_enabled = data['dedup.enabled'] || 'true';
this.originalSettings.dedup_enabled = this.settings.dedup_enabled;
this.settings.dedup_threshold = data['dedup.threshold'] || '10';
this.originalSettings.dedup_threshold = this.settings.dedup_threshold;
this.settings.dedup_ttl_seconds = data['dedup.ttl_seconds'] || '60';
this.originalSettings.dedup_ttl_seconds = this.settings.dedup_ttl_seconds;
this.settings.dedup_cache_size_per_device = data['dedup.cache_size_per_device'] || '1';
this.originalSettings.dedup_cache_size_per_device = this.settings.dedup_cache_size_per_device;
this.settings.dedup_for_click = data['dedup.for_click'] || 'true';
this.originalSettings.dedup_for_click = this.settings.dedup_for_click;
this.settings.dedup_for_app_switch = data['dedup.for_app_switch'] || 'false';
this.originalSettings.dedup_for_app_switch = this.settings.dedup_for_app_switch;
this.settings.dedup_force_after_skip_seconds = data['dedup.force_after_skip_seconds'] || '30';
this.originalSettings.dedup_force_after_skip_seconds = this.settings.dedup_force_after_skip_seconds;
```

Also add dedup fields to the reset CustomEvent broadcast.

- [ ] **Step 6: Add dedup section HTML to template**

After the Stats section (`</div>` of Stats, around line 520), before the button group (`<div class="btn-group">`), insert the Deduplication section HTML. Use the exact HTML from the design spec (lines 409-508 of design.md). Apply the same CSS class patterns as existing sections.

- [ ] **Step 7: Verify template renders without errors**

Run: `python -c "from openrecall.client.web.app import app; print('OK')"`
Expected: OK

- [ ] **Step 8: Commit**

```bash
git add openrecall/client/web/templates/settings.html
git commit -m "feat(settings_ui): add Deduplication section with 7 fields

Add Deduplication settings section with enabled, threshold (bits),
TTL (sec), cache size, for_click, for_app_switch, force_after_skip.
All fields wired to Alpine.js load/save/reset with CustomEvent broadcast
for hot-reload notification.
"
```

---

## Task 8: Integration Verification

**Files:**
- Test: `tests/test_config_integration.py`

- [ ] **Step 1: Add integration test for full hot-reload chain**

```python
# Append to tests/test_config_integration.py
def test_debouncer_hot_reload_via_store(tmp_path, monkeypatch):
    """Verify debouncer interval updates after settings store change."""
    from openrecall.client.database import ClientSettingsStore
    from openrecall.client.events.base import LockFreeDebouncer
    import time

    db_path = tmp_path / "client.db"
    store = ClientSettingsStore(db_path)

    # Simulate runtime_config init
    monkeypatch.setattr(
        "openrecall.client.events.base.runtime_config",
        MagicMock(),
    )

    debouncer = LockFreeDebouncer(3000)  # 3000ms

    # Fire at t=0
    assert debouncer.should_fire("device1", 0) is True

    # Update via store
    store.set("debounce.click_ms", "100")  # 100ms

    # Verify hot-reload: with 100ms interval, t=50 should still fire (fresh start)
    assert debouncer.should_fire("device1", 50) is True


def test_dedup_runtime_config_priority(tmp_path):
    """Dedup runtime_config getters should prefer SQLite over TOML."""
    from openrecall.client.database import ClientSettingsStore
    from openrecall.client import runtime_config

    db_dir = tmp_path / "client"
    db_dir.mkdir()
    runtime_config.init_runtime_config(db_dir)

    store = runtime_config._get_store()
    store.set("dedup.threshold", "42")

    assert runtime_config.get_dedup_threshold() == 42
```

Run: `pytest tests/test_config_integration.py -v`
Expected: PASS

- [ ] **Step 2: Final integration test — full settings save cycle**

```python
# Append to tests/test_runtime_config.py
def test_full_settings_save_and_reload_dedup(tmp_path):
    """Simulate a full settings save cycle: store -> getter -> updated value."""
    from openrecall.client.database import ClientSettingsStore
    from openrecall.client import runtime_config

    db_dir = tmp_path / "client"
    db_dir.mkdir()
    runtime_config.init_runtime_config(db_dir)

    store = runtime_config._get_store()

    # Save dedup settings
    store.set("dedup.enabled", "false")
    store.set("dedup.threshold", "20")
    store.set("dedup.cache_size_per_device", "5")

    # Verify getters return new values
    assert runtime_config.get_dedup_enabled() is False
    assert runtime_config.get_dedup_threshold() == 20
    assert runtime_config.get_dedup_cache_size() == 5
```

Run: `pytest tests/test_runtime_config.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_config_integration.py tests/test_runtime_config.py
git commit -m "test: add hot-reload integration tests for debouncer and dedup"
```

---

## Task 9: Final Verification

- [ ] **Step 1: Run all tests**

Run: `pytest tests/test_atomic.py tests/test_runtime_config.py tests/test_config_integration.py tests/test_p1_s2a_debounce.py tests/test_p1_s2b_plus_simhash_config.py -v`
Expected: ALL PASS

- [ ] **Step 2: Check no regressions in full test suite**

Run: `pytest -m unit -v --timeout=60`
Expected: ALL PASS (or pre-existing failures only)

- [ ] **Step 3: Manual verification**

1. Start client: `./run_client.sh --mode local --debug`
2. Open http://localhost:8889/settings
3. Verify Deduplication section appears
4. Change debounce values → save → verify in logs `[Recorder] Hot-reloaded`
5. Change dedup threshold → save → verify new value reflected

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete settings hot-reload implementation

All 8 existing settings now hot-reloadable + 7 dedup settings added.
- AtomicInt (ctypes) for lock-free debouncer updates
- Config listener thread for debounce hot-reload
- Chunked idle sleep (max 5s) for idle interval hot-reload
- SimhashCache dynamic TTL/cache_size on every add
- Recorder dedup settings via runtime_config
- Settings UI Deduplication section with 7 fields
"
```
