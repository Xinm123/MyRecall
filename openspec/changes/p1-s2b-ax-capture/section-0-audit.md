## Section 0 Audit (S2b Preflight)

### 0.1 TriggerEvent `device_name` usage audit

- `openrecall/client/events/base.py` defines `TriggerEvent.device_name` as an event field and `TriggerDebouncer` keys by this value.
- `openrecall/client/events/macos.py` event sources emit `TriggerEvent` with monitor-derived `device_name`.
- `openrecall/client/recorder.py` treats `event.device_name` as both routing key and persisted payload truth (`metadata["device_name"]`).

Conclusion:

- Current runtime conflates event hint and final capture-time truth.
- For S2b, treat `TriggerEvent.device_name` as `event_device_hint` internally and derive persisted `final_device_name` from capture monitor binding in recorder/worker path.

### 0.2 PermissionStateMachine constraint audit

- `openrecall/client/events/permissions.py` constants already match S2b requirements:
  - `REQUIRED_CONSECUTIVE_FAILURES = 2`
  - `REQUIRED_CONSECUTIVE_SUCCESSES = 3`
  - `EMIT_COOLDOWN_SEC = 300`
- Poll interval is driven by `settings.permission_poll_interval_sec`, defaulting to 10 in `openrecall/shared/config.py`.

Conclusion:

- Constraint values already align with `2 fail / 3 success / 300s cooldown / 10s poll`.
- No pre-S2b parameter change needed.

### 0.3 `/v1/ingest` legacy/alias/mixed-version audit

- `openrecall/server/api_v1.py` currently validates `capture_trigger`, but does not enforce required `accessibility_text`/`content_hash` contract keys.
- `openrecall/server/database/frames_store.py` currently falls back from canonical fields to aliases (`active_app`, `active_window`).

Conclusion:

- Legacy/alias payloads are currently accepted as canonical truth.
- S2b needs explicit contract rejection for missing required keys and migration-observation handling for alias-only context.

### 0.4 Recorder topology audit (`run_capture_loop`)

- `openrecall/client/recorder.py` uses single consumer loop:
  - trigger wait
  - capture monitors
  - select event device screenshot
  - build metadata
  - enqueue spool
- Trigger channel and monitor refresh are owned by `ScreenRecorder`; no dedicated `TriggerBus(broadcast)` and no per-monitor worker owner.

Conclusion:

- Current code is single-loop orchestration and not yet S2b worker topology.
- For S2b migration, promote broadcast trigger ownership at recorder level and push capture-time ownership (device truth + handoff bundle) into per-monitor worker path.
