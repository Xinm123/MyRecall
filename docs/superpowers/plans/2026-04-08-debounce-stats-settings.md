# Debounce & Stats Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `[debounce]` and `[stats]` settings to the settings page with hot-reload, following the existing SQLite runtime config pattern.

**Architecture:** TOML acts as defaults; runtime values live in SQLite `client_settings` table. A `runtime_config.py` getter layer reads SQLite first, falls back to TOML. Alpine.js frontends stores/loads ms values but displays them as seconds.

**Tech Stack:** Python (Flask API, SQLite), Alpine.js (Jinja2 template), `openrecall.client` package

---

## Files to Modify

| File | Change |
|------|--------|
| `openrecall/client/database/settings_store.py` | Add 5 keys to `DEFAULTS` dict |
| `openrecall/client/runtime_config.py` | Add 5 getter functions |
| `openrecall/client/web/routes/settings.py` | Add 5 validation rules to `validators` dict |
| `openrecall/client/recorder.py` | Call `get_stats_interval_sec()` at top of each timer loop tick |
| `openrecall/client/web/templates/settings.html` | Add "Debounce" + "Stats" card sections; update JS for unit conversion |

---

## Task 1: Add DEFAULTS to settings_store.py

**Files:** Modify: `openrecall/client/database/settings_store.py:20-24`

- [ ] **Step 1: Add 5 new entries to DEFAULTS dict**

In the `DEFAULTS` dict on line 20, add these entries after the existing three:

```python
    DEFAULTS: dict[str, str] = {
        "edge_base_url": "",
        "capture_save_local_copies": "false",
        "capture_permission_poll_sec": "10",
        "debounce.click_ms": "3000",
        "debounce.trigger_ms": "3000",
        "debounce.capture_ms": "3000",
        "debounce.idle_interval_ms": "60000",
        "stats.interval_sec": "120",
    }
```

- [ ] **Step 2: Verify no other changes needed**

The `_ensure_defaults()` method iterates `DEFAULTS.items()` automatically — no changes required there.

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/database/settings_store.py
git commit -m "feat(settings): add debounce and stats keys to client_settings DEFAULTS"
```

---

## Task 2: Add getter functions to runtime_config.py

**Files:** Modify: `openrecall/client/runtime_config.py` (append 5 new functions after `get_save_local_copies`)

- [ ] **Step 1: Add 5 getter functions after `get_save_local_copies()` (after line 95)**

```python
def get_debounce_click_ms() -> int:
    """Get click debounce interval in milliseconds.

    Priority: SQLite runtime settings > TOML config (debounce.click_ms) > 3000
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
    return settings.debounce_click_ms


def get_debounce_trigger_ms() -> int:
    """Get trigger debounce interval in milliseconds.

    Priority: SQLite runtime settings > TOML config (debounce.trigger_ms) > 3000
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
    return settings.debounce_trigger_ms


def get_debounce_capture_ms() -> int:
    """Get global capture debounce interval in milliseconds.

    Priority: SQLite runtime settings > TOML config (debounce.capture_ms) > 3000
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
    return settings.debounce_capture_ms


def get_debounce_idle_interval_ms() -> int:
    """Get idle capture fallback interval in milliseconds.

    Priority: SQLite runtime settings > TOML config (debounce.idle_interval_ms) > 60000
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
    return settings.debounce_idle_interval_ms


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
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/runtime_config.py
git commit -m "feat(runtime_config): add debounce and stats getter functions"
```

---

## Task 3: Add validation rules to settings API

**Files:** Modify: `openrecall/client/web/routes/settings.py:62-66`

- [ ] **Step 1: Extend the validators dict**

Find the `validators` dict (line 62) and add the five new rules:

```python
    validators = {
        "edge_base_url": lambda v: v is None or v == "" or v.startswith(("http://", "https://")),
        "capture_save_local_copies": lambda v: str(v).lower() in ("true", "false"),
        "capture_permission_poll_sec": lambda v: str(v).isdigit() and 1 <= int(v) <= 300,
        "debounce.click_ms": lambda v: str(v).isdigit() and 0 <= int(v) <= 60000,
        "debounce.trigger_ms": lambda v: str(v).isdigit() and 0 <= int(v) <= 60000,
        "debounce.capture_ms": lambda v: str(v).isdigit() and 0 <= int(v) <= 60000,
        "debounce.idle_interval_ms": lambda v: str(v).isdigit() and 10000 <= int(v) <= 600000,
        "stats.interval_sec": lambda v: str(v).isdigit() and 10 <= int(v) <= 3600,
    }
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/web/routes/settings.py
git commit -m "feat(settings_api): add validation for debounce and stats settings"
```

---

## Task 4: Refresh stats interval in recorder timer loop

**Files:** Modify: `openrecall/client/recorder.py:1140-1147`

- [ ] **Step 1: Add `get_stats_interval_sec` import at top of file**

Find the existing imports (around line 10-20). Add:

```python
from openrecall.client.runtime_config import get_stats_interval_sec
```

- [ ] **Step 2: Call getter at top of each timer tick (before the stats comparison)**

In the main loop at lines 1140-1147, add a getter call at the top of the periodic-stats block:

```python
            # Periodic stats logging
            current_time = time.time()
            # Refresh stats interval each tick to support hot-reload
            self._stats_report_interval_sec = get_stats_interval_sec()
            if (
                current_time - self._last_stats_report_time
                >= self._stats_report_interval_sec
            ):
                self._report_stats()
                self._last_stats_report_time = current_time
```

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/recorder.py
git commit -m "feat(recorder): hot-reload stats interval via runtime_config getter"
```

---

## Task 5: Update settings.html with new card sections

**Files:** Modify: `openrecall/client/web/templates/settings.html`

This task has three sub-steps: add CSS, add HTML card sections, and update the Alpine.js component.

- [ ] **Step 1: Add CSS for the new form elements (after line 283, before `{% endblock %}`)**

```html
  .settings-section .inline-fields {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .settings-section .inline-fields .form-group {
    margin-bottom: 0;
  }

  .settings-section .inline-fields-3 {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16px;
  }

  .settings-section .inline-fields-3 .form-group {
    margin-bottom: 0;
  }
```

- [ ] **Step 2: Add HTML card sections (after the "Capture" section, before the btn-group)**

Insert after line 370 (after the closing `</div>` of the Capture section) and before line 372 (the btn-group div):

```html
  <div class="settings-section">
    <h2>Debounce</h2>

    <div class="inline-fields-3" style="margin-bottom: 16px;">
      <div class="form-group">
        <label class="form-label" for="debounce_click_sec">Click</label>
        <span class="form-label-description">Suppress rapid clicks (sec)</span>
        <input
          type="number"
          id="debounce_click_sec"
          class="form-input"
          x-model="settings.debounce_click_sec"
          min="0"
          max="60"
          step="0.1"
          style="width: 100%;"
        >
      </div>

      <div class="form-group">
        <label class="form-label" for="debounce_trigger_sec">Trigger</label>
        <span class="form-label-description">Suppress rapid app switches (sec)</span>
        <input
          type="number"
          id="debounce_trigger_sec"
          class="form-input"
          x-model="settings.debounce_trigger_sec"
          min="0"
          max="60"
          step="0.1"
          style="width: 100%;"
        >
      </div>

      <div class="form-group">
        <label class="form-label" for="debounce_capture_sec">Capture</label>
        <span class="form-label-description">Global min interval (sec)</span>
        <input
          type="number"
          id="debounce_capture_sec"
          class="form-input"
          x-model="settings.debounce_capture_sec"
          min="0"
          max="60"
          step="0.1"
          style="width: 100%;"
        >
      </div>
    </div>

    <div class="form-group" style="max-width: 200px;">
      <label class="form-label" for="debounce_idle_sec">Idle Interval</label>
      <span class="form-label-description">Background capture fallback (sec)</span>
      <input
        type="number"
        id="debounce_idle_sec"
        class="form-input"
        x-model="settings.debounce_idle_sec"
        min="10"
        max="600"
        step="1"
        style="width: 100%;"
      >
      <div class="current-value">
        Capture when idle for <code x-text="settings.debounce_idle_sec">60</code> seconds
      </div>
    </div>
  </div>

  <div class="settings-section">
    <h2>Stats</h2>

    <div class="form-group" style="max-width: 200px;">
      <label class="form-label" for="stats_interval_sec">Reporting Interval</label>
      <span class="form-label-description">How often to log capture statistics (sec)</span>
      <input
        type="number"
        id="stats_interval_sec"
        class="form-input"
        x-model="settings.stats_interval_sec"
        min="10"
        max="3600"
        step="1"
        style="width: 100%;"
      >
      <div class="current-value">
        Current: <code x-text="originalSettings.stats_interval_sec + ' seconds'">120 seconds</code>
      </div>
    </div>
  </div>
```

**Note:** Field IDs use `_sec` suffix (`debounce_click_sec`, etc.) to indicate the display unit. The actual keys sent to the API are `debounce.click_ms` etc., via JS conversion in `saveSettings()`.

- [ ] **Step 3: Update Alpine.js `settings` and `originalSettings` objects**

Find the `settings:` and `originalSettings:` objects in the JS (around lines 391-400). Add the new fields:

```javascript
      settings: {
        edge_base_url: '',
        capture_save_local_copies: 'false',
        capture_permission_poll_sec: '10',
        // Debounce — displayed as seconds, stored as ms
        debounce_click_sec: '3.0',
        debounce_trigger_sec: '3.0',
        debounce_capture_sec: '3.0',
        debounce_idle_sec: '60',
        // Stats
        stats_interval_sec: '120'
      },
      originalSettings: {
        edge_base_url: '',
        capture_save_local_copies: 'false',
        capture_permission_poll_sec: '10',
        debounce_click_sec: '3.0',
        debounce_trigger_sec: '3.0',
        debounce_capture_sec: '3.0',
        debounce_idle_sec: '60',
        stats_interval_sec: '120'
      },
```

- [ ] **Step 4: Update `loadSettings()` to convert ms → sec on load**

Find `loadSettings()` and add the conversion after the existing field assignments (after line 424):

```javascript
            // Debounce: convert ms to seconds for display
            this.settings.debounce_click_sec = (parseInt(data['debounce.click_ms'] || '3000') / 1000).toFixed(1);
            this.originalSettings.debounce_click_sec = this.settings.debounce_click_sec;
            this.settings.debounce_trigger_sec = (parseInt(data['debounce.trigger_ms'] || '3000') / 1000).toFixed(1);
            this.originalSettings.debounce_trigger_sec = this.settings.debounce_trigger_sec;
            this.settings.debounce_capture_sec = (parseInt(data['debounce.capture_ms'] || '3000') / 1000).toFixed(1);
            this.originalSettings.debounce_capture_sec = this.settings.debounce_capture_sec;
            this.settings.debounce_idle_sec = (parseInt(data['debounce.idle_interval_ms'] || '60000') / 1000).toFixed(0);
            this.originalSettings.debounce_idle_sec = this.settings.debounce_idle_sec;
            // Stats
            this.settings.stats_interval_sec = data['stats.interval_sec'] || '120';
            this.originalSettings.stats_interval_sec = this.settings.stats_interval_sec;
```

- [ ] **Step 5: Update `hasChanges()` to include new fields**

Find `hasChanges()` (around line 434) and extend it:

```javascript
      hasChanges() {
        return this.settings.edge_base_url !== this.originalSettings.edge_base_url ||
               this.settings.capture_save_local_copies !== this.originalSettings.capture_save_local_copies ||
               this.settings.capture_permission_poll_sec !== this.originalSettings.capture_permission_poll_sec ||
               this.settings.debounce_click_sec !== this.originalSettings.debounce_click_sec ||
               this.settings.debounce_trigger_sec !== this.originalSettings.debounce_trigger_sec ||
               this.settings.debounce_capture_sec !== this.originalSettings.debounce_capture_sec ||
               this.settings.debounce_idle_sec !== this.originalSettings.debounce_idle_sec ||
               this.settings.stats_interval_sec !== this.originalSettings.stats_interval_sec;
      },
```

- [ ] **Step 6: Update `saveSettings()` to convert sec → ms and broadcast**

Find `saveSettings()` (around line 467). Build the payload with unit conversion and update `originalSettings` after save:

In the `try` block after the `fetch` succeeds (after line 481), replace the original-settings update block with:

```javascript
            // Convert seconds to ms for storage keys
            const payload = {
              edge_base_url: this.settings.edge_base_url,
              capture_save_local_copies: this.settings.capture_save_local_copies,
              capture_permission_poll_sec: this.settings.capture_permission_poll_sec,
              'debounce.click_ms': String(Math.round(parseFloat(this.settings.debounce_click_sec) * 1000)),
              'debounce.trigger_ms': String(Math.round(parseFloat(this.settings.debounce_trigger_sec) * 1000)),
              'debounce.capture_ms': String(Math.round(parseFloat(this.settings.debounce_capture_sec) * 1000)),
              'debounce.idle_interval_ms': String(Math.round(parseFloat(this.settings.debounce_idle_sec) * 1000)),
              'stats.interval_sec': String(parseInt(this.settings.stats_interval_sec)),
            };

            // Broadcast event for hot reload
            window.dispatchEvent(new CustomEvent('openrecall-config-changed', {
              detail: {
                edge_base_url: this.settings.edge_base_url,
                capture_save_local_copies: this.settings.capture_save_local_copies,
                capture_permission_poll_sec: this.settings.capture_permission_poll_sec,
                'debounce.click_ms': payload['debounce.click_ms'],
                'debounce.trigger_ms': payload['debounce.trigger_ms'],
                'debounce.capture_ms': payload['debounce.capture_ms'],
                'debounce.idle_interval_ms': payload['debounce.idle_interval_ms'],
                'stats.interval_sec': payload['stats.interval_sec'],
              }
            }));
```

Also update the `originalSettings` sync (after the `window.EDGE_BASE_URL` line, around line 484):

```javascript
            // Sync originalSettings
            this.originalSettings.debounce_click_sec = this.settings.debounce_click_sec;
            this.originalSettings.debounce_trigger_sec = this.settings.debounce_trigger_sec;
            this.originalSettings.debounce_capture_sec = this.settings.debounce_capture_sec;
            this.originalSettings.debounce_idle_sec = this.settings.debounce_idle_sec;
            this.originalSettings.stats_interval_sec = this.settings.stats_interval_sec;
```

And update the fetch body to send `payload` instead of `this.settings`:

```javascript
            body: JSON.stringify(payload)
```

- [ ] **Step 7: Update `resetSettings()` to reload the new fields**

In the reset success handler (after the existing field resets, around line 527), add:

```javascript
            this.settings.debounce_click_sec = (parseInt(data['debounce.click_ms'] || '3000') / 1000).toFixed(1);
            this.originalSettings.debounce_click_sec = this.settings.debounce_click_sec;
            this.settings.debounce_trigger_sec = (parseInt(data['debounce.trigger_ms'] || '3000') / 1000).toFixed(1);
            this.originalSettings.debounce_trigger_sec = this.settings.debounce_trigger_sec;
            this.settings.debounce_capture_sec = (parseInt(data['debounce.capture_ms'] || '3000') / 1000).toFixed(1);
            this.originalSettings.debounce_capture_sec = this.settings.debounce_capture_sec;
            this.settings.debounce_idle_sec = (parseInt(data['debounce.idle_interval_ms'] || '60000') / 1000).toFixed(0);
            this.originalSettings.debounce_idle_sec = this.settings.debounce_idle_sec;
            this.settings.stats_interval_sec = data['stats.interval_sec'] || '120';
            this.originalSettings.stats_interval_sec = this.settings.stats_interval_sec;
```

Also update the reset `CustomEvent` detail:

```javascript
            window.dispatchEvent(new CustomEvent('openrecall-config-changed', {
              detail: {
                edge_base_url: data.edge_base_url,
                capture_save_local_copies: data.capture_save_local_copies,
                capture_permission_poll_sec: data.capture_permission_poll_sec,
                'debounce.click_ms': data['debounce.click_ms'],
                'debounce.trigger_ms': data['debounce.trigger_ms'],
                'debounce.capture_ms': data['debounce.capture_ms'],
                'debounce.idle_interval_ms': data['debounce.idle_interval_ms'],
                'stats.interval_sec': data['stats.interval_sec'],
              }
            }));
```

- [ ] **Step 8: Commit**

```bash
git add openrecall/client/web/templates/settings.html
git commit -m "feat(settings): add debounce and stats sections with sec/ms conversion"
```

---

## Spec Coverage Check

- [ ] `settings_store.py` DEFAULTS — Task 1 ✓
- [ ] `runtime_config.py` getters — Task 2 ✓
- [ ] `settings.py` validation — Task 3 ✓
- [ ] `recorder.py` hot-reload — Task 4 ✓
- [ ] `settings.html` UI + unit conversion — Task 5 ✓

## Self-Review

- No placeholders or TBDs
- Function names in later tasks match earlier task definitions (`get_stats_interval_sec`, `get_debounce_*_ms`)
- No contradictions with the spec
- All 5 spec requirements mapped to tasks
