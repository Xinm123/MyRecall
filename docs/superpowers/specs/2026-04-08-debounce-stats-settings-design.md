# Settings Page Extension: Debounce & Stats

## Status

**Implemented** — committed to `final-8` branch (2026-04-08)

## Goal

Expose `[debounce]` and `[stats]` settings from `client-local.toml` on the settings page with hot-reload support, following the existing SQLite runtime config pattern.

---

## Background

Currently the settings page supports three settings (edge URL, save local copies, permission poll). The debounce, dedup, and stats sections in TOML require a client restart to take effect. This spec adds debounce and stats to the settings page.

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | SQLite `client_settings` table | Consistent with existing runtime config pattern |
| Key format | `debounce.click_ms`, `stats.interval_sec` | Flat namespace, matches TOML hierarchy |
| Defaults source | TOML | Acts as fallback when SQLite key is absent |
| UI unit for time | Seconds (display) / Milliseconds (store) | User-friendly; backend unchanged |
| Hot-reload path | Debouncer reads `self._min_interval_ms` each call (already dynamic) | No object reconstruction needed |
| Stats interval | Updated in timer callback via getter | `_stats_report_interval_sec` is a cached copy |

---

## Architecture

### Data Flow

```
settings.html (Alpine.js)
    ↓ POST /api/client/settings
settings_store.py (SQLite)
    ↓
runtime_config.py (getters: SQLite → TOML fallback)
    ↓ (called by)
recorder.py (debouncers + timer)
    ↓ CustomEvent('openrecall-config-changed')
layout.html (already broadcasts)
```

### Key Insight: Debouncers Are Already Dynamic

`TriggerDebouncer.should_fire()` and `LockFreeDebouncer.should_fire()` read `self._min_interval_ms` on every call — not captured at construction. Hot-reload only needs to update `self._min_interval_ms` directly. No debouncer reconstruction required.

---

## Storage Schema

**New keys in `client_settings` table:**

| key | example value | unit in DB | display unit |
|-----|---------------|------------|--------------|
| `debounce.click_ms` | `3000` | ms | sec |
| `debounce.trigger_ms` | `3000` | ms | sec |
| `debounce.capture_ms` | `3000` | ms | sec |
| `debounce.idle_interval_ms` | `60000` | ms | sec |
| `stats.interval_sec` | `120` | sec | sec |

---

## API Changes

### `POST /api/client/settings` — Validation Rules

| key | validation |
|-----|------------|
| `debounce.click_ms` | integer, 0–60000 |
| `debounce.trigger_ms` | integer, 0–60000 |
| `debounce.capture_ms` | integer, 0–60000 |
| `debounce.idle_interval_ms` | integer, 10000–600000 |
| `stats.interval_sec` | integer, 10–3600 |

### Existing GET — No Changes

`GET /api/client/settings` already returns all keys from SQLite (with TOML fallback applied). The Alpine.js `settingsPage()` component will receive the new keys automatically.

---

## Frontend Changes

### `settings.html` — New Alpine.js Section

Two new `<template>` card sections added to the form, following the existing card pattern:

**Card 1: "Debounce"**
- `click_ms` → `<input type="number">`, step 0.1, display as `value / 1000` sec
- `trigger_ms` → `<input type="number">`, step 0.1, display as `value / 1000` sec
- `capture_ms` → `<input type="number">`, step 0.1, display as `value / 1000` sec
- `idle_interval_ms` → `<input type="number">`, step 1, display as `value / 1000` sec

**Card 2: "Stats"**
- `stats.interval_sec` → `<input type="number">`, step 1, no conversion needed

### Frontend Unit Conversion

In `saveSettings()`:
```javascript
// Convert seconds to ms before saving
const idle_sec = parseFloat(this.settings.debounce_idle_interval_sec);
this.settings.debounce_idle_interval_ms = Math.round(idle_sec * 1000);
```

In `loadSettings()`:
```javascript
// Convert ms to seconds for display
this.settings.debounce_idle_interval_sec =
    (this.settings.debounce_idle_interval_ms / 1000).toFixed(1);
```

---

## Backend Changes

### `openrecall/client/database/settings_store.py`

Add to `DEFAULTS`:
```python
"debounce.click_ms": "3000",
"debounce.trigger_ms": "3000",
"debounce.capture_ms": "3000",
"debounce.idle_interval_ms": "60000",
"stats.interval_sec": "120",
```

### `openrecall/client/runtime_config.py`

Add getter functions:
```python
def get_debounce_click_ms() -> int: ...
def get_debounce_trigger_ms() -> int: ...
def get_debounce_capture_ms() -> int: ...
def get_debounce_idle_interval_ms() -> int: ...
def get_stats_interval_sec() -> int: ...
```

Each getter:
1. Reads from SQLite via `settings_store.get(key)`
2. Falls back to TOML `ClientSettings` attributes
3. Falls back to hard-coded default

### `openrecall/client/recorder.py`

**`_report_stats` timer callback (line ~1140):**
```python
self._stats_report_interval_sec = get_stats_interval_sec()  # refresh each tick
```

**No changes needed for debouncers** — they already read `self._min_interval_ms` dynamically. The `should_fire()` calls at lines 386 and 1185 already use `self._trigger_debouncer._min_interval_ms` and `settings.capture_debounce_ms` respectively, which will reflect the updated value after the next CustomEvent.

### `openrecall/client/__main__.py` or init path

`runtime_config.init_runtime_config()` is called on startup. Ensure it loads the new keys. No changes needed if it already calls `settings_store.get_all()` — new keys will be present with defaults from TOML.

---

## Implementation Order

1. `settings_store.py` — add DEFAULTS entries
2. `runtime_config.py` — add getter functions
3. `web/routes/settings.py` — add validation rules
4. `recorder.py` — add `get_stats_interval_sec()` call in timer callback
5. `settings.html` — add two new card sections with unit conversion
6. Test: change debounce value in settings page, verify it affects next capture timing

---

## Open Questions

None — all decisions have been resolved.
