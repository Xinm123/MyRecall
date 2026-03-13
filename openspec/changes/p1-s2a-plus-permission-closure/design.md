## Context

P1-S2a already added the event-driven recorder path and the server-side permission fields, and the current codebase contains most of the mechanical pieces: `openrecall/client/events/permissions.py` has a four-state `PermissionStateMachine`, `openrecall/client/recorder.py` polls permissions and halts capture when the machine is degraded, `openrecall/server/config_runtime.py` mirrors the latest permission snapshot with a 60s TTL, `openrecall/server/api_v1.py` degrades `/v1/health` when permission is stale or non-granted, and `openrecall/server/templates/layout.html` renders degraded health states in the UI.

The remaining gap is that these pieces do not yet fully implement the P1-S2a+ Input Monitoring closure scope defined in `docs/v3/spec.md` and `docs/v3/acceptance/phase1/p1-s2a-plus.md`: the detector in `openrecall/client/events/permissions.py` still evaluates Accessibility and Screen Recording instead of the S2a+ Input Monitoring capability probe, the startup/revoke/restore/stale scenarios are not yet frozen as an end-to-end contract, and the required test and evidence entrypoints are not yet defined as mandatory delivery artifacts.

## Goals / Non-Goals

**Goals:**
- Freeze a code-level design for the P1-S2a+ permission stability closure without reopening S2a scope.
- Reconcile the existing recorder, permission monitor, runtime mirror, health endpoint, and UI health anchor around the recorder-owned, Input Monitoring-focused state machine defined by S2a+.
- Define how controlled degradation and automatic recovery work without process restart.
- Define the required automated tests and local acceptance evidence so the change is implementation-ready.

**Non-Goals:**
- Replacing the existing event-driven trigger architecture from P1-S2a.
- Expanding v3 back into AX-primary capture, browser URL capture, OCR pipeline work, or S2b topology/routing scope.
- Introducing a new external service, persistence table, or long-lived permission event store for this phase.
- Changing frozen Gate thresholds or adding new state names beyond the four states already locked in `docs/v3/spec.md`.

## Decisions

### D1: Reuse the existing four-state FSM, but change its ownership target to Input Monitoring

**Choice:** Keep `openrecall/client/events/permissions.py` as the single recorder-owned FSM implementation, preserve the frozen thresholds, and change `detect_permissions()` to report S2a+ Input Monitoring truth and S2a+ reason codes rather than the earlier Accessibility/Screen Recording checks. For Terminal-mode P1, the canonical Input Monitoring truth source is whether the same listen-only `CGEventTapCreate` path used by `openrecall/client/events/macos.py` can be created successfully; `detect_permissions()` should wrap that capability probe instead of consulting unrelated permission APIs.

**Why:**
- The code already has the correct externally visible states and thresholds, so replacing the state machine would create unnecessary churn.
- The real gap is semantic ownership: S2a+ is about Input Monitoring stability closure, not generic permission API visibility.
- Reusing the existing recorder-owned FSM keeps all permission transitions serialized on the capture loop thread, which matches the current concurrency model and avoids split-brain permission state.
- Reusing the event-tap creation path as the probe keeps permission truth aligned with the actual event-driven capability that S2a/S2a+ owns, rather than with Accessibility or Screen Recording side signals.

**Alternatives considered:**
- Add a second Input Monitoring FSM alongside the current one. Rejected because it would create multiple health truth sources.
- Move the permission FSM into the server. Rejected because the permission truth originates on the Host, and the server only mirrors it.

**Screenpipe reference:** `_ref/screenpipe/apps/screenpipe-app-tauri/src-tauri/src/permissions.rs` - intentional divergence. Screenpipe uses a background permission monitor with the same debounce-style thresholds, but MyRecall keeps the state machine owned by the recorder path and narrows S2a+ to Input Monitoring closure only.

### D2: Permission loss pauses external-trigger consumption through the recorder gate, not by tearing down the whole recorder

**Choice:** Keep `openrecall/client/recorder.py` as the enforcement point for controlled degradation. When the FSM is in `denied_or_revoked` or `recovering`, the recorder continues running, keeps polling permissions and sending heartbeats, but does not consume external event triggers for capture work until the success threshold is met.

**Why:**
- The current recorder loop already has the right control point: it polls permissions, emits heartbeats, and short-circuits on degraded state before waiting for triggers.
- This gives the required controlled degradation behavior - halt external event-trigger consumption while preserving liveness - and still allows stale detection and automatic recovery.
- Avoiding process restart is an explicit S2a+ requirement and also the lowest-risk path for P1.

**Alternatives considered:**
- Stop and restart the whole client process on permission changes. Rejected because S2a+ explicitly requires recovery without manual restart.
- Keep accepting trigger events into the queue while degraded. Rejected because S2a+ requires capture to stop consuming external event triggers during denied/revoked states.

**Screenpipe reference:** `_ref/screenpipe/crates/screenpipe-server/src/event_driven_capture.rs` - aligned for the event-driven capture loop shape, intentional divergence for degradation control. Screenpipe has the event-driven loop and heartbeat pattern, but no comparable queue-integrated permission pause that feeds back into capture gating.

### D3: `/v1/health` remains a derived view over mirrored Host permission state, with stale snapshot semantics enforced server-side

**Choice:** Keep `openrecall/server/config_runtime.py` as the freshness authority for mirrored permission state and keep `openrecall/server/api_v1.py` as the single place that derives overall health from queue, frame, and permission conditions. Stale detection remains server-enforced from mirror freshness, surfaces through `capture_permission_reason=stale_permission_state` plus `status != ok`, and is not inferred from client UI behavior or frame output.

**Why:**
- The runtime mirror already has the TTL and field completeness mechanism needed by S2a+.
- Server-side derivation prevents the UI from becoming the source of truth.
- The acceptance docs explicitly require stale permission snapshots to degrade health even if the last known state value is unchanged.

**Alternatives considered:**
- Derive stale state in the client before posting heartbeat payloads. Rejected because stale freshness is fundamentally about missing updates at the server boundary.
- Infer permission loss from blank frames or missing captures. Rejected because `docs/v3/spec.md` explicitly says empty extraction or related capture symptoms are not permission truth.

**Screenpipe references:** `_ref/screenpipe/crates/screenpipe-server/src/routes/health.rs` - aligned for derived degraded health semantics; `_ref/screenpipe/crates/screenpipe-server/src/event_driven_capture.rs` - aligned for heartbeat-before-health reasoning. MyRecall intentionally diverges by making stale permission snapshots an explicit contract field (`stale_permission_state`).

### D4: UI health rendering stays contract-driven and must not invent extra permission states

**Choice:** Keep the existing `#mr-health` anchor in `openrecall/server/templates/layout.html` and continue mapping UI state entirely from `/v1/health`, with only the frozen S2a+ distinctions: stale permission snapshot, recovering, denied/revoked, waiting for first frame, queue issue, or other degraded health state.

**Why:**
- The current UI already follows this architecture and contains explicit branches for `stale_permission_state`, `recovering`, and `denied_or_revoked`.
- S2a+ needs semantic correctness, not a new UI architecture.
- Reusing the same anchor preserves the inherited P1-S1 and S2a read-path contracts.

**Alternatives considered:**
- Add a separate permission status widget with independent polling. Rejected because it would create duplicate logic and drift risk.
- Infer UI health directly from recorder-side state. Rejected because `/v1/health` is the frozen external contract.

**Screenpipe reference:** `_ref/screenpipe/apps/screenpipe-app-tauri/lib/hooks/use-health-check.tsx` - aligned. Both systems keep the UI health presentation downstream of the backend health contract rather than inventing a separate frontend-only truth source.

### D5: Acceptance readiness is delivered through one focused test file and one focused local gate entrypoint

**Choice:** Treat `tests/test_p1_s2a_plus_permission_fsm.py` and `scripts/acceptance/p1_s2a_plus_local.sh` as mandatory P1-S2a+ delivery artifacts of this change, with the evidence files from `docs/v3/acceptance/phase1/p1-s2a-plus.md` generated from that single local gate entrypoint script.

**Why:**
- The acceptance doc makes these artifacts mandatory, not optional follow-up work.
- A single focused test file and local gate entrypoint script keep S2a+ isolated from S2b work and make the phase boundary auditable.
- Evidence generation needs to be implementation-ready before `/opsx-apply` starts, or the phase will drift into undocumented manual work.

**Alternatives considered:**
- Fold S2a+ checks into older S2a test files and scripts. Rejected because the acceptance doc explicitly calls for a distinct S2a+ entrypoint and evidence set.
- Treat evidence generation as out-of-band documentation work. Rejected because P1-S2a+ cannot pass its local gate verification or phase gate without it.

**Screenpipe reference:** no comparable pattern. The required MyRecall artifact set and Terminal-mode gate evidence are project-specific.

## Risks / Trade-offs

- **Input Monitoring detection on macOS Terminal identity can be noisy** -> keep Terminal mode explicitly recorded in the evidence bundle and avoid over-claiming production guarantees.
- **Current permission detector semantics are broader than S2a+ scope** -> narrow the detector and reason codes to the S2a+ contract before implementation tasks begin.
- **Stopping external-trigger consumption may hide bugs if idle fallback still fires unexpectedly** -> cover degraded and recovery behavior explicitly in the required FSM tests.
- **Server mirror freshness can drift from client poll timing** -> keep stale evaluation server-side with the fixed 60s TTL and validate it with dedicated stale-snapshot tests.
- **Archived S2a specs already describe part of this space** -> keep this change narrowly framed as closure and avoid inventing new states or thresholds that conflict with the frozen docs.

## Migration Plan

1. Align `openrecall/client/events/permissions.py` with the S2a+ Input Monitoring contract while preserving the frozen four-state FSM and thresholds.
2. Update `openrecall/client/recorder.py` so degraded and recovery behavior precisely matches the S2a+ capture-stop and auto-recovery semantics.
3. Keep `openrecall/server/config_runtime.py`, `openrecall/server/api_v1.py`, and `openrecall/server/templates/layout.html` synchronized around the frozen health semantics and stale handling.
4. Add the dedicated S2a+ tests and local gate entrypoint script, then use them as the verification path for the implementation.
5. No schema migration or rollback data cleanup is required; rollback is code-only because this change freezes behavior rather than adding durable storage.

## Resolved Clarifications

- `detect_permissions()` uses a wrapper around the existing listen-only `CGEventTapCreate` startup path as the canonical Input Monitoring probe for Terminal-mode P1.
- `startup_not_determined` does not introduce a fifth external state; until the recorder observes a confirmed successful permission check, the externally visible state surfaces as `transient_failure` and the UI follows the degraded health contract from decision D4, which satisfies the acceptance contract without inventing extra FSM states.
