## Why

P1-S2a and P1-S2a+ established trigger generation and permission stability, but the current capture path still binds triggers too early, captures all monitors in one loop, and does not freeze the monitor-aware completion contract required before OCR can safely consume frames. P1-S2b is needed now to close the routing, device binding, focused-context, topology rebuild, and spool handoff semantics that define the v3 capture-completion boundary for P1-S3.

## What Changes

- Freeze the two-layer P1-S2b capture model from `docs/v3/spec.md`: routing selects the target monitor first, then a monitor-bound capture worker performs the screenshot and binds final `device_name` plus focused context.
- Freeze the implementation-facing coordinator contract needed to realize that model: coordinator remains an internal recorder stage, routed work items carry target monitor plus topology epoch, and stale tasks must fail loud instead of silently rerouting or rebinding.
- Define the four trigger routing modes and filtered outcomes for `click`, `app_switch`, `idle`, and `manual`, including `PRIMARY_MONITOR_ONLY` filtering and same-monitor debounce behavior.
- Freeze `device_name` same-cycle binding and `focused_context = {app_name, window_name}` coherence rules so non-focused captures write `null` instead of stale values and event sources no longer own final monitor binding.
- Define monitor topology rebuild behavior for monitor add/remove, primary-display changes, and temporary monitor unavailability, including runtime observability through registry and health snapshots.
- Freeze spool-to-ingest handoff correctness for capture-completion payloads, outcomes, and evidence so S3 can rely only on screenshot + capture metadata without reviving AX-era semantics.
- Clarify S2b timestamp and evidence terminology so `event_ts`, Host capture-completion time (`timestamp`, used as `capture_completed_ts` in Gate math), and `ingested_at` are unambiguous during verification.
- Require the mandatory P1-S2b delivery artifacts: focused routing/device-binding tests, the local gate script, and evidence outputs described by the acceptance and test-strategy docs.
- Source authority is layered by concern: frozen behavior follows `docs/v3/spec.md`, then `docs/v3/data-model.md`, then `docs/v3/open_questions.md`; executable scenarios and required evidence follow `docs/v3/acceptance/phase1/p1-s2b.md`; Gate formulas and sample rules follow `docs/v3/gate_baseline.md`.

## Non-goals

- Reopening AX capture, `accessibility_text`, `content_hash`, browser URL capture, or any other pre-OQ-043 semantics in the v3 active path.
- Changing OCR processing, `text_source`, `/v1/search`, `/v1/chat`, or any downstream S3+ behavior.
- Redefining ingest idempotency, retry policy, or legacy `/api/*` compatibility beyond the capture-completion contract already frozen for the v3 mainline.
- Expanding P1 beyond macOS or introducing Windows/Linux runtime guarantees before P2.

## Capabilities

### New Capabilities
- `trigger-target-routing`: Freeze target-monitor selection, `routing_filtered`, and overlap/debounce semantics for `click`, `app_switch`, `idle`, and `manual` triggers.
- `capture-device-binding`: Freeze monitor-worker-owned `device_name` binding and same-cycle `focused_context` coherence, including `null` rules for non-focused monitor captures.
- `monitor-topology-rebuild`: Define how monitor add/remove, primary-monitor changes, and temporary unavailability rebuild worker state, registry state, and routing state.
- `capture-spool-handoff`: Freeze capture-completion payload, outcome, and spool-to-`/v1/ingest` handoff semantics for the v3-only mainline.
- `capture-completion-gate-evidence`: Define the mandatory P1-S2b tests, local gate script, health/runtime evidence, and proof-sample exclusions required to exit the phase.

### Modified Capabilities
- None. `openspec/specs/` is currently empty, so this change adds new capability specs rather than delta specs against an existing main spec set.

## Impact

- **Client capture runtime**: `openrecall/client/events/` and `openrecall/client/recorder.py` need a monitor-aware routing/coordinator/worker boundary instead of the current event-bound device ownership and all-monitor capture loop.
- **Client spool/uploader path**: `openrecall/client/spool.py` and `openrecall/client/v3_uploader.py` must preserve the frozen capture-completion payload and outcome semantics into `/v1/ingest`.
- **Server/runtime observability**: runtime health and capture evidence must reflect active monitors, topology rebuild outcomes, and last capture outcome without changing the OCR-only downstream boundary.
- **Tests and acceptance**: `tests/test_p1_s2b_routing.py`, `tests/test_p1_s2b_device_binding.py`, and `scripts/acceptance/p1_s2b_local.sh` become mandatory delivery artifacts, alongside the evidence bundle defined in `docs/v3/acceptance/phase1/p1-s2b.md`.
- **Phase gating**: P1-S3 should only begin after S2b freezes the capture-completion contract and proves the four Hard Gate metrics against the v3 mainline.
