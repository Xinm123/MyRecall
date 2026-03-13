## Why

P1-S2a exposed permission fields and introduced the event-driven capture path, but it did not fully close the Input Monitoring stability contract needed before P1-S2b. P1-S2a+ is needed now to prevent false healthy states when permissions are lost, freeze the degraded/recovery semantics, and produce the local gate evidence required to enter capture-completion work.

## What Changes

- Freeze the Input Monitoring-focused permission FSM for P1-S2a+ with the four externally visible states `granted`, `transient_failure`, `denied_or_revoked`, and `recovering`, including the required failure/success thresholds.
- Freeze `/v1/health` permission semantics so the response always includes `capture_permission_status`, `capture_permission_reason`, and `last_permission_check_ts`, never reports `status=ok` while permission is lost or recovering, and reports `stale_permission_state` when the permission snapshot is too old.
- Require controlled degradation of event-driven capture when Input Monitoring is denied or revoked: stop external event-trigger consumption while keeping permission polling, heartbeat reporting, and recovery guidance active instead of silently continuing.
- Require automatic recovery without process restart once permission is restored and the recovery threshold is satisfied.
- Add the mandatory P1-S2a+ automated tests, local gate entrypoint script, and evidence outputs defined in `docs/v3/acceptance/phase1/p1-s2a-plus.md`.
- Source authority is layered by concern to avoid ambiguity: behavior and API semantics follow `docs/v3/spec.md`, then `docs/v3/data-model.md`, then `docs/v3/open_questions.md`; phase scenario matrix and required evidence follow `docs/v3/acceptance/phase1/p1-s2a-plus.md`; Gate and SLO formulas or thresholds follow `docs/v3/gate_baseline.md`.

## Non-goals

- Re-opening AX as a primary capture path in v3.
- Adding browser URL capture, `content_hash`, OCR processing, search/chat behavior, or other non-permission scope from later phases.
- Expanding P1 beyond macOS Terminal mode or redefining signed-app production guarantees.
- Changing the existing S2a trigger taxonomy, debounce policy, or ingest payload shape beyond the permission stability closure needed for S2a+.

## Capabilities

### New Capabilities
- `permission-state-machine`: Freeze the Input Monitoring-focused permission FSM, transition thresholds, startup behavior, revoke behavior, and recovery behavior for P1-S2a+.
- `health-permission-semantics`: Freeze `/v1/health` permission field completeness, stale snapshot handling, and health-degraded semantics during denied, recovering, or stale permission conditions.
- `capture-permission-recovery`: Define controlled degradation of event-driven capture on permission loss and automatic recovery after permissions are restored.
- `permission-gate-evidence`: Define the mandatory automated tests, local gate entrypoint script, and evidence artifacts required to satisfy the P1-S2a+ gate.

### Modified Capabilities
- None. `openspec/specs/` is currently empty, so this change will create new capability specs rather than delta specs against an existing main spec set.

## Impact

- **Client runtime**: `openrecall/client/events/` and `openrecall/client/recorder.py` need stable permission-state, degradation, and auto-recovery behavior.
- **Server contracts**: `GET /v1/health` and runtime state mirroring must enforce the S2a+ permission semantics and stale-snapshot rules.
- **UI/read path**: health presentation must reflect degraded and recovery states consistently with the backend contract.
- **Tests and acceptance**: `tests/test_p1_s2a_plus_permission_fsm.py` and `scripts/acceptance/p1_s2a_plus_local.sh` become mandatory delivery artifacts, along with the evidence bundle described in the acceptance doc.
- **Phase gating**: P1-S2b cannot start until this permission stability closure is defined and passes its gate.
