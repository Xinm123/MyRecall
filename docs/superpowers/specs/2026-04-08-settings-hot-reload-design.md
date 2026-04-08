# Settings Hot-Reload Design

**Date:** 2026-04-08
**Status:** Approved
**Scope:** Enable hot-reload for all settings exposed in the WebUI Settings page, including Debounce, Deduplication, and Idle Interval configurations.

---

## Background

The Settings page exposes 8 configuration fields. Currently:
- 4 fields are hot-reloadable: `edge_base_url`, `capture_save_local_copies`, `capture_permission_poll_sec`, `stats_interval_sec`
- 4 fields are NOT hot-reloadable: `debounce.click_ms`, `debounce.trigger_ms`, `debounce.capture_ms`, `debounce.idle_interval_ms`

Additionally, 7 Deduplication configuration fields exist in TOML/config but are not exposed in the Settings UI.

**Goal:** Make all settings hot-reloadable and expose Deduplication settings in the UI.

---

## Architecture

### Hot-Reload Flow

```
Settings UI (Alpine.js POST /api/client/settings)
    → Save to SQLite via ClientSettingsStore
    → Broadcast CustomEvent('openrecall-config-changed', detail)
    → Recorder listens, updates runtime_config
    → Consumers (debouncers, cache, loops) read updated values
```

### Configuration Priority

All settings use this priority (highest to lowest):
1. SQLite runtime settings (set via WebUI) — hot-reloadable
2. TOML config file — static, requires restart
3. Hard-coded defaults — fallback

---

## Part 1: Atomic Variable for Debouncers

### Problem

`LockFreeDebouncer.should_fire()` runs on the CGEventTap callback thread (macOS system thread). Using a regular Python `int` for `_min_interval_ms` risks stale reads during updates.

### Solution: AtomicInt via ctypes

**New file:** `openrecall/client/events/atomic.py`

```python
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

### TriggerDebouncer Update

**File:** `openrecall/client/events/base.py`

Changes to `TriggerDebouncer`:
1. Replace `self._min_interval_ms: int` with `self._min_interval_ms: AtomicInt`
2. Add `update_interval_ms(new_ms: int)` method
3. `should_fire()` reads via `.get()`, writes via `.set()` (already atomic)

Changes to `LockFreeDebouncer`:
1. Same replacement pattern
2. Same `update_interval_ms()` method

```python
# TriggerDebouncer
def __init__(self, min_interval_ms: int) -> None:
    from openrecall.client.events.atomic import AtomicInt
    self._min_interval_ms = AtomicInt(min_interval_ms)
    self._lock = threading.Lock()
    self._last_fire_ms: dict[str, int] = {}
    self._debounced_count: int = 0

def should_fire(self, device_name: str, now_ms: int) -> bool:
    with self._lock:
        last_fire_ms = self._last_fire_ms.get(device_name)
        min_interval = self._min_interval_ms.get()  # atomic read
        if last_fire_ms is None or now_ms - last_fire_ms >= min_interval:
            self._last_fire_ms[device_name] = now_ms
            return True
        self._debounced_count += 1
        return False

def update_interval_ms(self, new_ms: int) -> None:
    self._min_interval_ms.set(new_ms)

# LockFreeDebouncer — same pattern, no lock in should_fire()
def __init__(self, min_interval_ms: int) -> None:
    from openrecall.client.events.atomic import AtomicInt
    self._min_interval_ms = AtomicInt(min_interval_ms)
    self._last_fire_ms: dict[str, int] = {}
    self._lock = threading.Lock()  # Only for reset operations

def should_fire(self, device_name: str, now_ms: int) -> bool:
    min_interval = self._min_interval_ms.get()  # atomic read
    last_fire_ms = self._last_fire_ms.get(device_name, 0)
    if now_ms - last_fire_ms >= min_interval:
        self._last_fire_ms[device_name] = now_ms
        return True
    return False

def update_interval_ms(self, new_ms: int) -> None:
    self._min_interval_ms.set(new_ms)
```

---

## Part 2: Recorder Listens for Config Changes

**File:** `openrecall/client/recorder.py`

### Setup: Register Event Listener

In `Recorder.__init__()`:
```python
import threading
self._config_listener_thread: threading.Thread | None = None
self._running = True
self._config_listener_thread = threading.Thread(
    target=self._config_change_listener, daemon=True
)
self._config_listener_thread.start()
```

### Listener Thread

```python
def _config_change_listener(self) -> None:
    """Listen for openrecall-config-changed events and update debouncers."""
    import threading

    class ConfigChangeEventListener:
        def __init__(self, recorder: Recorder):
            self.recorder = recorder
            self._running = True

        def __call__(self, event: CustomEvent) -> None:
            detail = event.detail
            if detail.get('debounce.click_ms'):
                self.recorder._click_debouncer.update_interval_ms(
                    int(detail['debounce.click_ms'])
                )
            if detail.get('debounce.trigger_ms'):
                self.recorder._trigger_debouncer.update_interval_ms(
                    int(detail['debounce.trigger_ms'])
                )
            if detail.get('debounce.capture_ms'):
                # Capture debounce also uses trigger debouncer internally
                # No separate debouncer needed — captured by trigger path
                pass
            if detail.get('debounce.idle_interval_ms'):
                # Idle interval is handled by the idle loop itself
                # (dynamic read on each iteration)
                pass
            logger.info("[Recorder] Hot-reloaded debounce settings")

    listener = ConfigChangeEventListener(self)

    def _wait_for_event(stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            from openrecall.client.runtime_config import wait_for_config_change
            wait_for_config_change(timeout=1.0)

    stop_event = threading.Event()
    try:
        _wait_for_event(stop_event)
    except Exception:
        pass
    finally:
        stop_event.set()
```

**Note on capture debounce:** `debounce.capture_ms` is used directly in recorder.py's capture gate (line ~1188) as a per-device min interval check, not via a debouncer. Replace `settings.capture_debounce_ms` with `runtime_config.get_debounce_capture_ms()` to enable hot-reload. The getter already exists in runtime_config.py.

---

## Part 3: Idle Interval Hot-Reload

**File:** `openrecall/client/recorder.py`

Current: `time.sleep(idle_interval_ms)` blocks the entire idle loop.

**Solution:** Chunked sleep with dynamic re-read every 5 seconds.

```python
_POLL_INTERVAL_SEC = 5  # Max delay for idle interval hot-reload

def _idle_loop(self) -> None:
    """Background idle monitoring loop with hot-reload support."""
    from openrecall.client import runtime_config

    while self._running:
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
        # ... capture logic using idle trigger
```

**Acceptable trade-off:** Max 5 second delay on hot-reload for idle interval. User changes take effect within one poll cycle.

---

## Part 4: runtime_config Extensions

**File:** `openrecall/client/runtime_config.py`

### Existing Getters (already implemented)

| Getter | Field | Status |
|--------|-------|--------|
| `get_permission_poll_interval_sec()` | `capture_permission_poll_sec` | ✅ |
| `get_save_local_copies()` | `capture_save_local_copies` | ✅ |
| `get_debounce_click_ms()` | `debounce.click_ms` | ✅ |
| `get_debounce_trigger_ms()` | `debounce.trigger_ms` | ✅ |
| `get_debounce_capture_ms()` | `debounce.capture_ms` | ✅ |
| `get_debounce_idle_interval_ms()` | `debounce.idle_interval_ms` | ✅ |
| `get_stats_interval_sec()` | `stats.interval_sec` | ✅ |

### New Getters for Deduplication

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

### Wait Function for Listener

```python
import threading

_config_change_event = threading.Event()


def notify_config_changed() -> None:
    """Call after saving settings to SQLite. Wakes the config listener.

    Sets the event; listener clears it after processing.
    This prevents race conditions where notify fires while listener is
    between wait() and processing.
    """
    _config_change_event.set()


def wait_for_config_change(timeout: float | None = None) -> bool:
    """Block until config changed event is set, then clear and return.

    Returns:
        True if event was set (config changed), False if timeout expired

    Caller must call notify_config_changed() to set the event again
    for subsequent notifications.
    """
    triggered = _config_change_event.wait(timeout=timeout)
    if triggered:
        _config_change_event.clear()
    return triggered
```

**Update `settings.py`** to call `notify_config_changed()` after saving.

---

## Part 5: Recorder Deduplication Hot-Reload

**File:** `openrecall/client/recorder.py`

Replace direct `settings.xxx` references with `runtime_config.get_xxx()` for deduplication fields:

| Current | Replacement |
|---------|------------|
| `settings.simhash_dedup_enabled` | `runtime_config.get_dedup_enabled()` |
| `settings.simhash_dedup_threshold` | `runtime_config.get_dedup_threshold()` |
| `settings.simhash_enabled_for_click` | `runtime_config.get_dedup_for_click()` |
| `settings.simhash_enabled_for_app_switch` | `runtime_config.get_dedup_for_app_switch()` |
| `settings.simhash_force_after_skip_seconds` | `runtime_config.get_dedup_force_after_skip_sec()` |

For `SimhashCache` ttl and cache_size: dynamically read in `add()`:

```python
# In SimhashCache.add()
def add(self, device_name: str, phash: int, timestamp: float) -> None:
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

---

## Part 6: Settings UI — Deduplication Section

**File:** `openrecall/client/web/templates/settings.html`

### New Section: Deduplication (after Stats section)

```html
<div class="settings-section">
  <h2>Deduplication</h2>

  <div class="form-group">
    <div class="toggle-wrapper">
      <div class="toggle-label">
        <span class="label-title">Enable Deduplication</span>
        <span class="label-description">Drop visually similar consecutive frames</span>
      </div>
      <label class="toggle-switch">
        <input type="checkbox" id="dedup_enabled"
          x-model="settings.dedup_enabled"
          :checked="settings.dedup_enabled === 'true'"
          @change="settings.dedup_enabled = $event.target.checked ? 'true' : 'false'">
        <span class="toggle-slider"></span>
      </label>
    </div>
  </div>

  <div class="form-group">
    <label class="form-label" for="dedup_threshold">Similarity Threshold</label>
    <span class="form-label-description">Hamming distance threshold (lower = more strict)</span>
    <div style="display: flex; align-items: center; gap: 8px;">
      <input type="range" min="0" max="64" step="1"
        x-model="settings.dedup_threshold" style="flex: 1;">
      <input type="number" id="dedup_threshold" class="form-input"
        x-model="settings.dedup_threshold" min="0" max="64" step="1"
        style="width: 60px;">
      <span style="color: var(--text-secondary); font-size: 13px;">bits</span>
    </div>
  </div>

  <div class="form-group">
    <label class="form-label" for="dedup_ttl_seconds">Cache TTL</label>
    <span class="form-label-description">Duration before similar content can be recaptured</span>
    <div style="display: flex; align-items: center; gap: 8px;">
      <input type="range" min="1" max="600" step="1"
        x-model="settings.dedup_ttl_seconds" style="flex: 1;">
      <input type="number" id="dedup_ttl_seconds" class="form-input"
        x-model="settings.dedup_ttl_seconds" min="1" max="600" step="1"
        style="width: 80px;">
      <span style="color: var(--text-secondary); font-size: 13px;">sec</span>
    </div>
  </div>

  <div class="form-group" style="max-width: 200px;">
    <label class="form-label" for="dedup_cache_size_per_device">Cache Size</label>
    <span class="form-label-description">Recent hashes to keep per device</span>
    <input type="number" id="dedup_cache_size_per_device" class="form-input"
      x-model="settings.dedup_cache_size_per_device" min="1" max="100" step="1">
  </div>

  <div class="inline-fields" style="margin-top: 16px;">
    <div class="form-group" style="margin-bottom: 0;">
      <div class="toggle-wrapper">
        <div class="toggle-label">
          <span class="label-title">For Click</span>
          <span class="label-description">Dedup on click triggers</span>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" id="dedup_for_click"
            x-model="settings.dedup_for_click"
            :checked="settings.dedup_for_click === 'true'"
            @change="settings.dedup_for_click = $event.target.checked ? 'true' : 'false'">
          <span class="toggle-slider"></span>
        </label>
      </div>
    </div>

    <div class="form-group" style="margin-bottom: 0;">
      <div class="toggle-wrapper">
        <div class="toggle-label">
          <span class="label-title">For App Switch</span>
          <span class="label-description">Dedup on app_switch triggers</span>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" id="dedup_for_app_switch"
            x-model="settings.dedup_for_app_switch"
            :checked="settings.dedup_for_app_switch === 'true'"
            @change="settings.dedup_for_app_switch = $event.target.checked ? 'true' : 'false'">
          <span class="toggle-slider"></span>
        </label>
      </div>
    </div>
  </div>

  <div class="form-group" style="max-width: 300px; margin-top: 16px;">
    <label class="form-label" for="dedup_force_after_skip_seconds">Force After Skip</label>
    <span class="form-label-description">Force capture after N seconds even if similar</span>
    <div style="display: flex; align-items: center; gap: 8px;">
      <input type="range" min="1" max="3600" step="1"
        x-model="settings.dedup_force_after_skip_seconds" style="flex: 1;">
      <input type="number" id="dedup_force_after_skip_seconds" class="form-input"
        x-model="settings.dedup_force_after_skip_seconds" min="1" max="3600" step="1"
        style="width: 80px;">
      <span style="color: var(--text-secondary); font-size: 13px;">sec</span>
    </div>
  </div>
</div>
```

### Alpine.js Data Model Updates

Add to `settings:` and `originalSettings:` objects, and update `loadSettings()`, `hasChanges()`, `saveSettings()`, `resetSettings()` to handle the 7 new fields.

---

## Part 7: API Validation

**File:** `openrecall/client/web/routes/settings.py`

Add validation rules for dedup fields:

```python
"dedup.enabled": lambda v: str(v).lower() in ("true", "false"),
"dedup.threshold": lambda v: str(v).isdigit() and 0 <= int(v) <= 64,
"dedup.ttl_seconds": lambda v: str(v).replace(".", "", 1).isdigit() and 1 <= float(v) <= 600,
"dedup.cache_size_per_device": lambda v: str(v).isdigit() and 1 <= int(v) <= 100,
"dedup.for_click": lambda v: str(v).lower() in ("true", "false"),
"dedup.for_app_switch": lambda v: str(v).lower() in ("true", "false"),
"dedup.force_after_skip_seconds": lambda v: str(v).isdigit() and 1 <= int(v) <= 3600,
```

After saving, call `notify_config_changed()` to wake the listener thread.

---

## Part 8: ClientSettingsStore Default Values

**File:** `openrecall/client/database/settings_store.py`

Ensure all new dedup fields have proper defaults in `reset_to_defaults()`.

---

## Testing Strategy

- **Unit tests:** `test_config_client.py` — verify runtime_config getter priority
- **Integration tests:** `test_config_integration.py` — verify debouncer hot-reload
- **Dedup tests:** `test_p1_s2b_plus_simhash_config.py` — verify dedup hot-reload
- **Acceptance:** `scripts/acceptance/` — manual verification script

---

## File Changes Summary

| File | Change |
|------|--------|
| `openrecall/client/events/atomic.py` | **NEW** — AtomicInt for lock-free interval updates |
| `openrecall/client/events/base.py` | TriggerDebouncer/LockFreeDebouncer use AtomicInt |
| `openrecall/client/runtime_config.py` | Add 7 dedup getters + wait/notify functions |
| `openrecall/client/recorder.py` | Config listener thread, idle chunked sleep, dedup runtime_config |
| `openrecall/client/web/routes/settings.py` | Dedup validation + notify on save |
| `openrecall/client/database/settings_store.py` | Dedup defaults |
| `openrecall/client/web/templates/settings.html` | Dedup UI section + Alpine.js updates |
