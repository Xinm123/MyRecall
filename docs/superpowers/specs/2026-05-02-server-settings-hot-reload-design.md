# Server Settings Hot-Reload Design

**Date:** 2026-05-02
**Status:** Draft
**Scope:** Add a SQLite-backed, hot-reloadable settings layer on the Edge (server) side for AI description provider/model. Expose configuration via Edge HTTP API; client settings page contains a new "Server Settings" section that talks to Edge directly.

---

## Background

The client side already has a mature hot-reload pipeline (`ClientSettingsStore` + `runtime_config.py` + `notify_config_changed()` + Alpine.js settings page). The server side currently:

- Reads all settings from TOML at startup (`config_server.ServerSettings`)
- Has an in-memory `RuntimeSettings` (`config_runtime.py`) for ephemeral feature toggles, but **no SQLite persistence**
- Caches AI providers in `ai/factory.py:_instances` with **no invalidation mechanism**
- Has **no `/v1/settings` API endpoints**

When a user wants to switch the description model from `gpt-4o` to `qwen-vl-max`, the only path today is: edit `server-local.toml` → restart server. This makes experimentation painful, especially in remote-deployment scenarios where the server runs on a different machine.

**Goal:** Allow the user to change description provider/model/api_key/api_base/timeout from the client UI while the server is running, with zero restart, and have running workers pick up the new provider on the next batch.

---

## Goals

- Hot-reload of these five fields in a single, focused iteration:
  - `description.provider` — `local` | `dashscope` | `openai`
  - `description.model` — provider-specific model id (free text)
  - `description.api_key` — secret
  - `description.api_base` — http(s) endpoint
  - `description.request_timeout` — seconds, integer
- SQLite persistence on the server side (settings survive restart)
- Client UI section in the existing settings page; client UI calls Edge API directly (no client-side proxy or cache)
- In-flight worker tasks complete on old provider; the next batch uses new provider (cancel-on-version-bump granularity)
- Test-Connection flow that probes a provider with given credentials without writing to SQLite
- Reset-to-defaults flow (deletes SQLite override rows; effective config falls back to TOML)

## Non-Goals

- Embedding model swap (deferred; vector dim mismatch with existing LanceDB rows is out of scope this iteration)
- Authentication / authorization on settings endpoints (deployment is assumed to be in a trusted network; users requiring stricter security should add a reverse proxy)
- Per-task cancellation granularity inside `DescriptionService` (worker-level cancellation is sufficient)
- Other server settings (OCR, reranker, processing tunables, debug, ports, paths) — they remain TOML-only
- Multi-server federation
- Audit log of settings changes (logs are sufficient)

---

## Architecture

### Component Map

```
┌────────────── Client (port 8889) ──────────────┐    ┌──────────── Server (port 8083) ────────────┐
│                                                │    │                                            │
│  templates/settings.html                       │    │  api_v1.py (Blueprint /v1)                 │
│   └─ Server Settings section (NEW)             │ ───┼──→ /v1/settings/description (NEW)          │
│       Alpine.js x-data="serverSettings"        │    │      GET (mask) / POST / .../test / ...    │
│                                                │    │                                            │
│  routes/settings.py                            │    │  database/settings_store.py (NEW)          │
│   └─ /api/client/settings/edge/health (existing)│    │   └─ ServerSettingsStore                  │
│        proxied healthcheck                     │    │       └─ ~/.myrecall/server/db/settings.db │
│                                                │    │                                            │
│  No client-side server-settings cache          │    │  runtime_config.py (NEW)                   │
└────────────────────────────────────────────────┘    │   └─ get_description_*() (SQLite>TOML>def) │
                                                      │                                            │
                                                      │  ai/factory.py (PATCHED)                   │
                                                      │   └─ invalidate(capability)                │
                                                      │                                            │
                                                      │  config_runtime.RuntimeSettings (PATCHED)  │
                                                      │   └─ bump_ai_processing_version() (NEW)    │
                                                      │       atomically increments + notify_change│
                                                      │                                            │
                                                      │  description/worker.py (PATCHED)           │
                                                      │   └─ batch loop checks version,            │
                                                      │       resets _service when changed         │
                                                      └────────────────────────────────────────────┘
```

### Configuration Priority

All getters read with the same priority (highest to lowest):

1. **SQLite runtime settings** (`server_settings` table in `settings.db`) — written via API
2. **TOML config file** (`server-local.toml`) — bootstrap defaults
3. **Hard-coded defaults** in `ServerSettingsStore.DEFAULTS` — fallback

A field with no SQLite row falls through to TOML. Reset-to-default deletes SQLite rows so subsequent reads fall through to TOML.

### Hot-Swap Mechanism

```
POST /v1/settings/description
  → validate
  → write SQLite (transaction)
  → factory.invalidate('description')        ← clears _instances cache
  → runtime_settings.bump_ai_processing_version()  ← signal workers
  → 200

(asynchronously, on next worker batch)
DescriptionWorker._process_batch():
  current_version = runtime_settings.ai_processing_version
  if current_version != self._last_processing_version:
    self._service = None              ← force lazy rebuild
    self._last_processing_version = current_version
  ...self.service... (property triggers rebuild → factory → runtime_config)
```

In-flight task: completes with old provider. Next batch builds with new provider.

---

## Components

### `openrecall/server/database/settings_store.py` (NEW)

`ServerSettingsStore` mirrors `ClientSettingsStore`.

```python
class ServerSettingsStore:
    DEFAULTS = {
        "description.provider":         "local",
        "description.model":            "",
        "description.api_key":          "",
        "description.api_base":         "",
        "description.request_timeout":  "120",
    }

    def __init__(self, db_path: pathlib.Path) -> None: ...
    def get(self, key: str, default: str | None = None) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def get_all(self) -> dict[str, str]: ...
    def reset_to_defaults(self) -> None: ...
```

- Schema: `server_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`
- DB path: `paths_data_dir / "db" / "settings.db"` (independent file, not mixed with `edge.db`)
- All values stored as TEXT; callers handle type coercion
- **Defaults are NOT pre-inserted.** `DEFAULTS` is a code-level fallback used by `runtime_config` when a row is absent in SQLite *and* TOML doesn't override the key. Keeping the SQLite table sparse is what gives the source-tag mechanism three distinct states (`sqlite` / `toml` / `default`) and makes Reset semantically meaningful.
- Single-process write, SQLite WAL mode, no explicit row-level locking (SQLite serializes writes)

### `openrecall/server/runtime_config.py` (NEW)

Module-level initialization + per-field getter functions.

```python
_settings_store: ServerSettingsStore | None = None
_toml_settings: ServerSettings | None = None  # config_server.ServerSettings

def init_runtime_config(data_dir: Path, toml_settings: ServerSettings) -> None: ...

def get_description_provider() -> str:
    val = _settings_store.get("description.provider")
    return val if val else _toml_settings.description_provider

def get_description_model() -> str: ...
def get_description_api_key() -> str: ...
def get_description_api_base() -> str: ...
def get_description_request_timeout() -> int: ...

def get_effective_description_settings() -> dict:
    """Returns 5 effective fields with per-field source tags. api_key NOT masked here."""
    return {
        "provider": <effective>, "model": ..., "api_key": ...,
        "api_base": ..., "request_timeout": ...,
        "source": {"provider": "sqlite|toml|default", ...},  # one tag per field
    }
```

**Source determination rule** (per-field):

1. If a non-NULL row exists in `server_settings` for the key → `source = "sqlite"`
2. Else if the TOML value differs from the hard-coded `ServerSettingsStore.DEFAULTS[key]` → `source = "toml"`
3. Else → `source = "default"`

This requires comparing the TOML value against `DEFAULTS` (string-coerced). The two value sets must therefore be kept in lock-step: any change to a default value should be applied in both `ServerSettings` (TOML schema) and `ServerSettingsStore.DEFAULTS`. A unit test asserts equality between the two on import (see Testing § Unit `test_server_runtime_config.py` #6).

Masking is the responsibility of the API layer, not `runtime_config`.

### `openrecall/server/ai/factory.py` (PATCHED)

The current module has a global `_instances: Dict[str, object] = {}` cache (line 27) but **no lock**. Introduce a module-level lock and an invalidator:

```python
import threading

_instances: Dict[str, object] = {}
_lock = threading.Lock()                       # NEW

def invalidate(capability: str | None = None) -> None:
    """Clear cached provider instance(s). None = clear all."""
    with _lock:
        if capability is None:
            _instances.clear()
        else:
            _instances.pop(capability, None)
```

Cache reads/writes inside `get_*_provider()` should also be guarded by `_lock` to prevent the rare race where one thread is rebuilding while another invalidates. (The dict ops are individually atomic under the GIL, but the read-then-build sequence is not.)

Replace direct `settings.description_*` reads in `get_description_provider()` with `runtime_config.get_description_*()` calls. The function body otherwise stays the same — caching, branching by provider, etc.

### `openrecall/server/config_runtime.py` (PATCHED — small addition)

Add one method to the existing `RuntimeSettings` class so the API and reset paths have a single, locked, atomic call site:

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

Existing callers in `api.py:467,473` (toggle on/off) continue to use `runtime_settings.ai_processing_version += 1`; we do not refactor them in this iteration. The new helper is used only by the new `/v1/settings/description` POST and reset endpoints.

### `openrecall/server/description/worker.py` (PATCHED)

The current worker has a `service: DescriptionService` lazy-init property (line 31, 35-39) and a `run()` loop that calls `_process_batch(conn)` per cycle. The hot-reload guard goes at the top of `_process_batch`, before any work:

```python
def __init__(self, ...):
    ...
    self._last_processing_version: int = -1   # NEW; -1 forces first-batch alignment

def _process_batch(self, conn):
    from openrecall.server.config_runtime import runtime_settings   # existing import
    current_version = runtime_settings.ai_processing_version
    if current_version != self._last_processing_version:
        if self._service is not None:
            logger.info(
                f"DescriptionWorker rebuilding service (version "
                f"{self._last_processing_version} → {current_version})"
            )
        self._service = None                  # next `self.service` access rebuilds
        self._last_processing_version = current_version
    # ... existing batch logic (queue stats, claim_description_task, ...)
```

`self.service` accessor (line 36-39) already lazy-rebuilds when `_service` is None. The new `DescriptionService` it constructs has its own `_provider` cache that calls `factory.get_description_provider()`, which now reads from `runtime_config` and is no longer pinned to a stale instance because `factory.invalidate('description')` cleared the entry.

If `factory.get_description_provider()` raises (e.g. invalid config) on rebuild, log error, mark current task as `description_status='failed'`, **do not exit the worker**. Subsequent batches retry; user-facing symptom is a growing description backlog, which is observable in the UI.

### `openrecall/server/config_server.py` (PATCHED — small addition)

Currently `ServerSettings` has `description_provider`, `description_model`, `description_api_key`, `description_api_base` fields but **no** `description_request_timeout`. The OpenAI description provider uses `settings.ai_request_timeout` at `description/providers/openai.py:71`.

This iteration adds:

```python
# in ServerSettings dataclass
description_request_timeout: int = 120  # NEW

# in from_dict()
description_request_timeout=data.get("description.request_timeout", 120),  # NEW
```

The new TOML key is `description.request_timeout` (under `[description]` section).

### `openrecall/server/description/providers/openai.py` (PATCHED — small change)

Replace `timeout=settings.ai_request_timeout` (line 71) with `timeout=get_description_request_timeout()` (read at request time, not construction). This makes timeout changes take effect on the very next request without waiting for service rebuild.

DashScope and Local providers do not currently expose a timeout — leave them unchanged in this iteration. Their effective timeout is bounded by SDK defaults; the spec field is mostly meaningful for OpenAI in v1.

### `openrecall/server/api_v1.py` (PATCHED — adds 4 routes)

Routes mounted on existing `v1_bp` blueprint:

- `GET /v1/settings/description`
- `POST /v1/settings/description`
- `POST /v1/settings/description/test`
- `POST /v1/settings/description/reset`

API layer owns mask logic (`api_key` → `api_key_masked` in responses).

### `openrecall/server/app.py` (PATCHED — startup wiring)

A single new line inserted in startup, before workers are launched:

```python
init_runtime_config(data_dir, toml_settings)   # NEW — must come before start_workers()
# factory.py now reads via runtime_config; no further app-level wiring needed
start_workers(...)                              # existing
```

Existing initialization of `RuntimeSettings` (feature toggles like `recording_enabled`, `ai_processing_enabled`) is unchanged.

### `openrecall/client/web/templates/settings.html` (PATCHED)

Add `<div class="settings-section" x-data="serverSettings()">...</div>` after the existing client sections. The Alpine component:

- Calls `/api/client/settings/edge/health` to confirm Edge reachability
- On reachable: fetches `<edge_base_url>/v1/settings/description`
- Three buttons: Save / Test / Reset
- API key input behaves as: disabled+masked by default → click Edit → enabled+empty → user types → Cancel returns to disabled+masked
- Dirty tracking: form fields compared against `pristine` (last fetched values) on every Save
- Save POST contains only dirty fields (api_key only if user clicked Edit)
- Test POST contains the full current form state (omits api_key if user did not edit it)
- Source tags: only fields with source `sqlite` show `[overridden]` chip; hover/tooltip on every field shows source detail

The client does **not** persist server settings in `client.db`. Each visit to the settings page fetches fresh from Edge.

---

## Data Flow

### 1. Server Startup

```
app.py main():
  ├─ load_toml_settings() → ServerSettings instance
  ├─ init_runtime_config(data_dir, toml_settings)
  │    └─ ServerSettingsStore(data_dir/db/settings.db).__init__()
  │         └─ create table if not exists  (no defaults pre-inserted)
  └─ start workers (DescriptionWorker reads ai_processing_version on first batch)
```

### 2. GET (read effective settings)

```
Client → GET /v1/settings/description
  Server:
    runtime_config.get_effective_description_settings() → {provider, model, api_key, api_base, request_timeout, source}
    mask api_key → api_key_masked (api_key dropped from response)
  ← 200 { provider, model, api_key_masked, api_base, request_timeout, source: {...} }
```

Mask rule:
- `""` → `""`
- length < 8 → `"***"`
- length ≥ 8 → `"<first2>***<last2>"` (e.g. `sk-***12`)

### 3. POST update + hot-swap

```
Client → POST /v1/settings/description
   body: { ...only dirty fields..., api_key: <new>|null|missing }
  Server:
    1. validate(payload)
    2. effective_before = runtime_config.get_effective_description_settings()
    3. transaction: apply per-field, no early return
         for k,v in payload:
           if v is None:
             if store.get(k) is not None:
               store.delete(k)                       ← null = explicit clear
           elif v == "" and k == "api_key":
             pass                                     ← empty key = preserve
           elif effective_before[k] == v:
             pass                                     ← already-effective: no-op
                                                       (avoids flipping source toml→sqlite)
           else:
             store.set(k, v)
       commit
    4. effective_after = runtime_config.get_effective_description_settings()
    5. if any value field differs between effective_before and effective_after:
         # (compare values only — source map is excluded)
         factory.invalidate('description')
         runtime_settings.bump_ai_processing_version()
       (else: skip — no functional change, no need to disturb workers)
    6. mask api_key, return effective_after
  ← 200 { ...updated effective + masked... }

(async, next worker batch)
DescriptionWorker._process_batch():
  current_version != self._last_processing_version → self._service = None
  next self.service access → DescriptionService.__init__()._provider==None
                          → factory.get_description_provider()
                          → reads runtime_config → builds with new values
```

### 4. POST test (probe without writing)

```
Client → POST /v1/settings/description/test
   body: full payload (api_key may be empty string → backend uses runtime_config value)
  Server:
    1. validate(payload)
    2. construct provider instance directly from payload (NOT cached)
    3. probe per provider:
         openai      → GET {api_base}/models with `Authorization: Bearer <api_key>`
                       Success = HTTP 200; payload not parsed beyond status
         dashscope   → SDK `chat.completions.create(model=<model>, messages=[{role:"user",content:"ping"}], max_tokens=1)`
                       Note: this consumes 1 token of quota per probe.
                       Considered acceptable for an explicitly user-triggered "Test Connection".
         local       → GET {api_base}/models  (OpenAI-compat /v1/models endpoint)
                       Success = HTTP 200
       absolute timeout = min(payload.timeout, 30)
    4. Do NOT write to SQLite. Do NOT invalidate factory.
  ← 200 { ok: true,  latency_ms: 423, detail: "..." }
   or  200 { ok: false, error: "401 Unauthorized", latency_ms: 220 }
```

Note: probe failures return HTTP 200 with `ok:false`. Only payload validation failures return 4xx.

### 5. POST reset

```
Client → POST /v1/settings/description/reset
  Server:
    effective_before = runtime_config.get_effective_description_settings()
    for k in [...5 description.* keys]:
      if store.get(k) is not None:
        store.delete(k)
    effective_after = runtime_config.get_effective_description_settings()
    if any value field differs between effective_before and effective_after:
      # (compare values only — source map is excluded; switching from `sqlite` to `toml`
      #  with the same value should NOT trigger a worker rebuild)
      factory.invalidate('description')
      runtime_settings.bump_ai_processing_version()
  ← 200 { ...effective_after (now reflects TOML)... }
```

### 6. Cancellation Granularity

Worker-level. In-flight tasks complete with old provider. Tasks not yet started in the current batch wait for the next batch where service is rebuilt. We do not cancel mid-task.

Mixed data is acceptable: the same hand-off occurs when a user restarts the server, so frames produced during transitions may have descriptions from different providers. This matches existing operational behavior.

---

## API Contract

### `GET /v1/settings/description`

**Request body:** none

**Response 200:**
```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "api_key_masked": "sk-***XX12",
  "api_base": "https://api.openai.com/v1",
  "request_timeout": 120,
  "source": {
    "provider": "sqlite",
    "model": "sqlite",
    "api_key": "toml",
    "api_base": "sqlite",
    "request_timeout": "default"
  }
}
```

`source.<field>` is one of `"sqlite"` | `"toml"` | `"default"`.

### `POST /v1/settings/description`

**Request body** (all fields optional; only listed fields are updated):
```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "api_key": "sk-newkey",
  "api_base": "https://api.openai.com/v1",
  "request_timeout": 120
}
```

**Field semantics:**

| Field | Missing | Empty string `""` | `null` | Validated value |
|---|---|---|---|---|
| `provider` | preserve | reject (400) | delete (revert to TOML) | upsert |
| `model` | preserve | reject (400) | delete | upsert |
| `api_key` | preserve | preserve (no-op) | delete | upsert |
| `api_base` | preserve | upsert (empty allowed) | delete | upsert |
| `request_timeout` | preserve | reject (400) | delete | upsert |

**Validation rules:**

| Field | Rule |
|---|---|
| `provider` | one of `local`, `dashscope`, `openai` |
| `model` | non-empty string |
| `api_key` | string, length ≤ 1024 |
| `api_base` | empty, or matches `^https?://`, length ≤ 512 |
| `request_timeout` | integer 1–600 |

**Unknown keys** in the request body are **ignored silently** (logged at DEBUG, not WARN). This matches the client settings endpoint's lenient behavior and lets older clients send extra fields without breaking forward-compat.

**Response 200:** same shape as GET, reflecting updated effective state.

**Response 400:**
```json
{ "error": "invalid_request", "message": "...", "details": { "provider": "must be one of: local, dashscope, openai" } }
```

**Response 500:** SQLite write failure or other unexpected error. Settings remain unchanged on the server (transactional rollback).

### `POST /v1/settings/description/test`

**Request body:** full payload (provider, model, api_key, api_base, request_timeout).

Test-specific field semantics (different from update):

| Field | Missing or `""` | Validated value |
|---|---|---|
| `api_key` | use current effective value (from `runtime_config`) | use payload value |
| other fields | use payload value if present; else 400 | use payload value |

This lets the user "test connectivity with the saved key + a tweaked api_base" without re-entering the key.

**Response 200 (success):** `{ "ok": true, "latency_ms": 423, "detail": "openai: model 'gpt-4o' reachable" }`

**Response 200 (probe failure):** `{ "ok": false, "error": "401 Unauthorized", "latency_ms": 220 }`

**Response 400:** payload validation failure (same rules as update).

### `POST /v1/settings/description/reset`

**Request body:** none

**Response 200:** same shape as GET, reflecting effective state after reset.

### Error response format

```json
{ "error": "<code>", "message": "<human-readable>", "details": { ... } }
```

Codes used:
- `invalid_request` (400) — validation failure
- `internal_error` (500) — unexpected exception

---

## UI / UX

### Layout (settings.html)

```
[existing sections: Recording, Capture, Dedup, ...]

┌─ Server (Edge) Settings              [● Connected] ─┐
│                                                     │
│  ┌─ Description Provider ───────────────────────┐  │
│  │ Provider:        [ openai ▾ ]    [overridden] │  │
│  │ Model:           [ gpt-4o                  ]  │  │
│  │ API Key:         [ sk-***XX12 ] [✎ Edit] [⌫] │  │
│  │ API Base URL:    [ https://api.openai.com/v1]│  │
│  │ Request Timeout: [ 120 ] sec                  │  │
│  │                                                │  │
│  │ [ Test Connection ]  [ Save ]  [ Reset ]      │  │
│  │ Last test: ✅ 423ms · openai: model reachable │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### Connection States

| State | Status chip | Body |
|---|---|---|
| Connected | green dot, "Connected" | form interactive |
| Unreachable | red dot, "Edge unreachable" | form disabled, hint text |
| Loading | spinner, "Connecting..." | skeleton |

### Source Tags

- Visible: `[overridden]` chip only on fields whose source is `sqlite`
- Hover tooltip on every field: `Source: TOML config` / `Source: default value` / `Source: user override`
- Reasoning: most fields are not customized; tagging them all creates clutter. Power users can hover for full source.

### API Key Editing

- Default: input `disabled`, `type="password"`, value=`api_key_masked`, button [✎ Edit]
- Click [✎ Edit]: input `enabled`, `type="text"`, value=`""`, button [✕ Cancel]
- Click [✕ Cancel]: revert to disabled+masked
- Click [⌫] Clear: confirm dialog → POST with `api_key: null` (explicit clear)

### Save Button (dirty-only POST)

- Active (primary color) when at least one field is dirty
- POST contains only dirty fields:
  ```js
  for (const k of Object.keys(this.form)) {
    if (this.form[k] !== this.pristine[k]) payload[k] = this.form[k];
  }
  if (!this.apiKeyEditing) delete payload.api_key;
  ```
- Reasoning:
  - `api_key` masked value bug: if frontend sends the masked string back, backend would save the mask. Dirty-tracking the api_key is necessary; once paid for one field, paying for all is trivial.
  - Concurrent edits: dirty-only respects "last-write-wins per field touched", not per whole form. A user editing model in tab 1 and another editing timeout in tab 2 do not clobber each other.
  - Server audit: `User updated: provider, model` is more informative than echoing the entire form.

### Test Button

- Sends full form state. If api_key is disabled+masked (user did not edit), the api_key field is omitted; backend then uses the effective value for the probe.
- During probe: button → spinner, disabled
- Result line shows ✅ or ❌ + latency + first detail line (e.g. `✅ 423ms · openai: model 'gpt-4o' reachable`)

### Reset Button

- Confirm dialog: `Reset all description settings to defaults? Workers will switch to TOML config.`
- Disabled when no fields are overridden

### Provider Switch Cascade

- Changing Provider does NOT auto-clear Model / API Key / API Base
- Placeholders update:
  - `openai` → model `gpt-4o`, base `https://api.openai.com/v1`
  - `dashscope` → model `qwen-vl-max`, base `https://dashscope.aliyuncs.com/...`
  - `local` → model `qwen-vl-7b`, base `http://localhost:11434/v1`

### Unsaved-Changes Guard

`beforeunload` warning when any field is dirty.

---

## Error Handling

### Matrix

| Error source | HTTP | Server action | Client UX |
|---|---|---|---|
| Body not JSON | 400 | log warn, return `invalid_request` | toast `Invalid request format` |
| Validation fail | 400 | return `invalid_request` + `details` | per-field red text under input |
| SQLite write fail | 500 | rollback, log error+traceback | toast `Save failed: storage error`; form preserved |
| `factory.invalidate` raises | 500 | log error; settings already saved but swap may be skipped | toast warn `Saved, but worker may need restart` |
| Test: network timeout / DNS / refused | 200 | `{ok:false, error, latency_ms}` | red `Last test: ❌ <error>` |
| Test: 401/403 from provider | 200 | `{ok:false, error}` | same |
| Edge unreachable (client→server) | n/a | n/a | section grayed + `Edge unreachable` chip |

### Worker Failure on Provider Rebuild

If `factory.get_description_provider()` raises (bad config, missing SDK, unparseable api_base):
- Worker catches, logs error
- Current task → `description_status='failed'` + `error_message`
- Worker continues; next batch retries (so when user fixes config, recovery is automatic)
- Log rate-limit: same error logged at most once per 60 seconds, to avoid log spam

### Test-Endpoint Hard Limits

Absolute timeout 30 seconds regardless of `payload.request_timeout`. Probe runs in a thread or async with `wait_for(timeout=30)` to prevent UI freeze.

### Client-Side Health Polling

- On settings page open: ping `/v1/health` every 30s
- Connected → unreachable: gray section, hint
- Unreachable → connected: refetch settings, restore form
- Settings GET is NOT polled; only health is.

### Logging

| Event | Level | Content |
|---|---|---|
| settings update | INFO | `description settings updated: keys=[provider, model], version=N+1` |
| settings reset | INFO | `description settings reset to defaults, version=N+1` |
| test invocation | DEBUG | `description test: provider=openai, latency=423ms, ok=true` |
| factory invalidate | DEBUG | `factory invalidated: capability=description` |
| worker rebuild | INFO | `DescriptionWorker rebuilt service due to version change` |
| validation fail | WARN | `validation failed: field=provider, value="X", reason="not in enum"` |
| sqlite write fail | ERROR | full traceback |
| provider build fail | ERROR | `failed to build description provider: <traceback>` |

**Sensitive data:** API key values are NEVER logged in plaintext. Any log mentioning api_key applies the mask first.

### Edge-Cases Test Checklist

- Empty body POST → 200 no-op, **no version bump** (no actual changes)
- POST where every field equals current effective value → 200, **no version bump**
- Body contains unknown keys → ignored (consistent with client behavior)
- Concurrent POSTs from multiple clients → SQLite serializes; last write wins per field
- Worker mid-batch when settings change → next batch swaps
- Server restart preserves SQLite state
- Reset → GET returns TOML
- `api_key: null` → SQLite row deleted, mask becomes ""
- `api_key` missing → preserved
- `api_key: ""` → preserved (NOT cleared)

---

## Testing Strategy

### Test Layers

| Layer | Scope | Tools | Marker |
|---|---|---|---|
| Unit | `ServerSettingsStore` / `runtime_config` getters / mask function | pytest + tmp sqlite | `unit` |
| Integration | API endpoints + factory invalidate + version bump | pytest + Flask test client | `integration` |
| Worker | `DescriptionWorker` rebuilds service on version change | pytest + threading | `integration` |
| End-to-end | client UI → CORS → server → DB | manual | `manual` |

### Unit (`tests/test_server_settings_store.py`)

1. Init creates table; **does not** pre-insert default rows (table starts empty on first run)
2. `set/get` round-trip
3. Two `set` calls on same key: last wins
4. `delete` then `get` returns None
5. `get_all` returns only keys that have rows in SQLite (empty dict on fresh init)
6. `reset_to_defaults` deletes all `description.*` SQLite rows; `get_all` returns `{}` afterwards
7. Non-existent parent dir → auto-created
8. Non-string value coerced to string

### Unit (`tests/test_server_runtime_config.py`)

1. SQLite has value → getter returns SQLite, source=`sqlite`
2. SQLite empty, TOML has value differing from `DEFAULTS` → getter returns TOML, source=`toml`
3. SQLite empty, TOML value equals `DEFAULTS` → getter returns the value, source=`default`
4. `get_effective_description_settings()` returns 5 fields + `source` map
5. `init_runtime_config` is idempotent
6. Consistency: every key in `ServerSettingsStore.DEFAULTS` has a matching default in `ServerSettings` (string-coerced equal). Guards against drift between the two default sets.

### Unit (`tests/test_server_settings_mask.py`)

1. `""` → `""`
2. Length < 8 → `"***"`
3. `"sk-1234567890XX12"` → `"sk-***XX12"`
4. Unicode-safe

### Integration (`tests/test_server_settings_api.py`)

GET:
1. Default GET (no SQLite, TOML matches `DEFAULTS`) returns hardcoded defaults; api_key_masked=""; source=`default` for every field
2. SQLite override → returns SQLite values, source=sqlite
3. TOML override (TOML != DEFAULTS) → source=toml
4. Mixed → mixed sources

POST update:
5. Partial POST updates only listed fields
6. Full POST updates all
7. Provider not in enum → 400 + details
8. Timeout out of range → 400
9. api_base not http(s) → 400
10. `api_key: null` → SQLite row deleted
11. `api_key: ""` → preserved
12. Missing `api_key` key → preserved
13. POST then GET returns updated values (masked)
14. POST bumps `runtime_settings.ai_processing_version` **only when state actually changes**
15. POST clears `factory._instances['description']` **only when state actually changes**
16. Empty `{}` body POST → 200, no version bump, no factory invalidate
17. POST with all values equal to current effective → 200, no version bump

POST test:
18. Successful probe → ok:true + latency_ms
19. 401 → ok:false + error (HTTP still 200)
20. Network timeout → ok:false + error (HTTP still 200)
21. Test does NOT write to SQLite; subsequent GET unchanged
22. Test with empty api_key → backend uses runtime_config effective value
23. Test with missing api_key field → backend uses runtime_config effective value (same as empty)

POST reset:
24. Reset deletes all `description.*` rows
25. After reset, GET returns TOML (or hardcoded default)
26. Reset bumps version **only if effective values changed** (no-op if all SQLite rows already matched TOML)

### Worker (`tests/test_description_worker_hot_reload.py`)

1. Init: `_service` is None, version captured
2. First batch instantiates `_service`; version unchanged
3. External `bump_ai_processing_version()` → next batch sets `_service = None`
4. After `_service` is reset, accessing `self.service` (lazy property) calls `factory.get_description_provider()` again
5. After `factory.invalidate('description')`, returned instance is not the previous one (`is not`)

### Mocking Strategy

- HTTP probes mocked via `responses` library
- Provider classes use fakes for tests
- `factory._instances` cleared in fixture teardown
- TOML settings: per-test temporary `ServerSettings` instance

### Existing Tests Affected

Re-run and adapt as needed:
- `tests/test_description_provider.py` — factory now reads `runtime_config`, may need stub
- `tests/test_description_models.py` — same
- `tests/test_chat_mvp_*.py` — smoke pass

### Out of Scope (this iteration)

- Multi-client concurrent edit race tests (SQLite serializes, single-user tool)
- UI automation tests (manual smoke)
- Auth/security tests (no-auth is declared)

### Acceptance Criteria

- [ ] All unit/integration/worker tests pass
- [ ] No regressions in `tests/test_description_*.py`
- [ ] Manual: change provider in UI from `openai` → `dashscope`; within 5s, worker logs show service rebuilt; new tasks processed by dashscope
- [ ] Manual: disconnect Edge, UI shows `Edge unreachable`; reconnect, UI restores
- [ ] Manual: Test Connection against real OpenAI/DashScope/local each shows correct ✅/❌

---

## Open Decisions Made During Brainstorming

| Decision | Outcome |
|---|---|
| Scope: which settings? | Description provider/model/api_key/api_base/timeout only. Embedding deferred. |
| Hot-swap: in-flight tasks? | Cancel via `ai_processing_version` bump (already exists). Worker-level granularity. |
| Authentication? | None. Deployment is trusted-network. API key still masked in GET for shoulder-surfing prevention. |
| UI placement? | Same `settings.html`, new section after client sections. |
| Model selection UX? | Free text input + provider dropdown (3 options). |
| Validation when saving? | Schema validation only. Separate "Test Connection" button for live probing. |
| Embedding scope? | Out of scope (vector dim mismatch with existing LanceDB rows). |
| DB file? | Independent `~/.myrecall/server/db/settings.db`, not mixed with `edge.db`. |
| Client→Server transport? | Direct CORS call from client UI to `<edge_base_url>/v1/...`; no client-side proxy. |
| Field-level explicit clear? | `api_key: null` = explicit delete; missing key or `""` = preserve. |
| Source tag display? | Only `[overridden]` chip on sqlite-sourced fields; hover for full source. |
| POST shape? | Dirty-only (frontend computes diff from `pristine`). |

---

## Future Work (not this iteration)

- Embedding provider/model swap (requires LanceDB rebuild flow)
- Reranker enable/disable + model swap
- OCR engine selection
- Per-task cancellation granularity inside `DescriptionService`
- Settings change history / audit log
- Authentication / per-user settings
- Multi-server federation
- Settings page UI consolidation (tabs for Client / Server)
