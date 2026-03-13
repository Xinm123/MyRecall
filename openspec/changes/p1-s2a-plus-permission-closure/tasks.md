## Implementation Tasks

### 1. Input Monitoring permission state ownership

- [ ] 1.1 Refactor `openrecall/client/events/permissions.py` so the permission truth source and reason codes align with the P1-S2a+ Input Monitoring contract rather than the earlier Accessibility and Screen Recording permission APIs.
- [ ] 1.2 Preserve the frozen four-state FSM and thresholds in `openrecall/client/events/permissions.py`, and ensure startup, consecutive-failure, recovering, and consecutive-success transitions match the S2a+ spec exactly.
- [ ] 1.3 Remove any use of blank-frame or other non-permission symptoms as the authoritative source of permission loss, keeping such signals observational only.

### 2. Recorder degradation and recovery behavior

- [ ] 2.1 Update `openrecall/client/recorder.py` so `denied_or_revoked` stops external event-trigger consumption while keeping the recorder process, permission polling, and heartbeat reporting alive.
- [ ] 2.2 Ensure `openrecall/client/recorder.py` resumes event-driven capture automatically only after the `recovering -> granted` success threshold is satisfied, without requiring manual restart.
- [ ] 2.3 Verify the controlled-degradation path does not let idle fallback or any other trigger path bypass the S2a+ rule that external event-trigger consumption halts while liveness signals stay active.

### 3. Mirrored health semantics and UI consistency

- [ ] 3.1 Update `openrecall/server/config_runtime.py` so the mirrored permission snapshot preserves a single coherent status/reason/timestamp view and enforces the 60s stale rule required by S2a+.
- [ ] 3.2 Update `openrecall/server/api_v1.py` so `GET /v1/health` always returns the full permission field set and never reports `status="ok"` during `denied_or_revoked`, `recovering`, or stale permission states.
- [ ] 3.3 Update `openrecall/server/templates/layout.html` so `#mr-health` stays contract-driven and renders degraded state correctly for `denied_or_revoked`, `recovering`, and `stale_permission_state`.

### 4. Acceptance-ready test and script deliverables

- [ ] 4.1 Add `tests/test_p1_s2a_plus_permission_fsm.py` covering `startup_not_determined` (externally surfacing as `transient_failure`), `startup_denied`, `revoked_mid_run`, `restored_after_denied`, stale permission snapshots, and `/v1/health` permission field completeness.
- [ ] 4.2 Add `scripts/acceptance/p1_s2a_plus_local.sh` as the dedicated S2a+ local gate entrypoint script that emits the required evidence bundle.
- [ ] 4.3 Add or update supporting test coverage for the S2a+ acceptance entrypoint and evidence skeleton so the script contract is statically verifiable in CI.

## Acceptance Verification

### 5. Automated verification

- [ ] 5.1 Run `pytest tests/test_p1_s2a_plus_permission_fsm.py` and fix any failures until the dedicated S2a+ suite passes.
- [ ] 5.2 Run the affected health/runtime regression tests for `openrecall/server/api_v1.py`, `openrecall/server/config_runtime.py`, and the acceptance script coverage.

### 6. Local gate verification

- [ ] 6.1 Execute the S2a+ local gate entrypoint and confirm it emits `p1-s2a-plus-local-gate.log`, `p1-s2a-plus-permission-transitions.jsonl`, `p1-s2a-plus-health-snapshots.json`, `p1-s2a-plus-ui-proof.md`, and `p1-s2a-plus-context.json`.
- [ ] 6.2 Confirm the evidence bundle records `Terminal mode`, git rev, execution window, and permission-related environment context.
- [ ] 6.3 Confirm the resulting permission timeline and health snapshots demonstrate degraded-on-loss, `status != ok` while recovering, stale snapshot degradation, and automatic recovery without process restart.
