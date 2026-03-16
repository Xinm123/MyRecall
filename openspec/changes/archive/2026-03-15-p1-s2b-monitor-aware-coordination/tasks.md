## Implementation Tasks

### Dependency ordering

- [x] D0.1 Treat task group 1 as the protocol-definition prerequisite for task groups 2-4.
- [x] D0.2 Do not start task group 4 or gate scripting until the stale-task, timestamp, and `routing_filtered` protocols from task groups 1-3 are implemented and testable.
- [x] D0.3 Do not treat task group 5 as complete until tests prove both functional behavior and `/v1/health` plus log evidence.

### 1. Routing and coordinator boundary

- [x] 1.1 Add coordinator-owned state for enabled monitors, debounce partitions, idle partitions, topology epoch, and last capture outcome inside the Host runtime.
- [x] 1.2 Define and use a routed work item shape that carries `capture_trigger`, `target_device_name`, `routing_topology_epoch`, `event_ts`, and routing hints needed by worker-side validation.
- [x] 1.3 Refactor `openrecall/client/events/macos.py` so trigger sources emit routing hints without owning the final persisted `device_name` or persisted focused context.
- [x] 1.4 Implement the frozen routing taxonomy for `click`, `app_switch`, `idle`, and `manual` triggers in the recorder path.
- [x] 1.5 Implement explicit `routing_filtered` handling when a valid trigger resolves to a monitor outside the enabled worker set.
- [x] 1.6 Emit observable `routing_filtered` evidence including trigger type, target monitor, and filter reason.

### 2. Monitor-aware capture execution

- [x] 2.1 Replace the current global idle fallback behavior with per-enabled-monitor idle scheduling.
- [x] 2.2 Reset idle deadlines only for the monitor that completed capture; preserve unaffected monitors' idle deadlines.
- [x] 2.3 Rebuild monitor eligibility, debounce partitions, and idle partitions when topology changes are detected.
- [x] 2.4 Start fresh idle deadlines for newly enabled or recovered monitors and drop partitions for removed or disabled monitors.
- [x] 2.5 Refactor `openrecall/client/recorder.py` so one routed capture task targets one monitor-bound capture path instead of capturing all monitors first.
- [x] 2.6 Reject stale routed tasks when `routing_topology_epoch` no longer matches the active topology for that monitor.
- [x] 2.7 Track topology epochs and non-success outcomes inside the recorder runtime.

### 3. Metadata binding and spool handoff

- [x] 3.1 Move final `device_name` binding into the monitor-bound capture step.
- [x] 3.2 Treat event-source `active_app` / `active_window` values as routing hints only, never as authoritative persisted context.
- [x] 3.3 Enforce same-cycle `focused_context = {app_name, window_name}` bundling with `null` fallback for non-focused or unprovable monitor captures.
- [x] 3.4 Write canonical spool metadata keys (`app_name`, `window_name`, `device_name`, `capture_trigger`, `event_ts`, `timestamp`) atomically with each JPEG spool item.
- [x] 3.5 Preserve the S2b timestamp glossary so `timestamp` is the Host capture-completion time used as `capture_completed_ts` in Gate math.
- [x] 3.6 Preserve ingest compatibility by keeping only the metadata aliases that existing server adapters still need.

### 4. Runtime observability and server mirror

- [x] 4.1 Extend the heartbeat/runtime mirror to carry `capture_runtime.topology_epoch` and `capture_runtime.primary_monitor_only`.
- [x] 4.2 Extend the heartbeat/runtime mirror to carry `capture_runtime.active_monitors`.
- [x] 4.3 Extend the heartbeat/runtime mirror and `/v1/health` to surface `capture_runtime.last_capture_outcome`.
- [x] 4.4 Include enough outcome context to verify `routing_filtered`, stale-task rejection, and topology rebuild decisions without requiring spool artifacts.

### 5. Automated S2b test coverage

- [x] 5.1 Add `tests/test_p1_s2b_routing.py` covering the four frozen routing modes and `routing_filtered` behavior.
- [x] 5.2 Add routing tests covering same-monitor debounce and cross-monitor non-duplicate behavior.
- [x] 5.3 Add routing tests proving filtered routing produces both no spool/frame artifacts and observable `last_capture_outcome` evidence.
- [x] 5.4 Add topology rebuild tests covering monitor add, remove, primary switch, and temporary recovery scenarios.
- [x] 5.5 Add topology tests proving stale routed tasks are rejected instead of silently rerouted or rebound.
- [x] 5.6 Add `tests/test_p1_s2b_device_binding.py` covering worker-owned `device_name` binding.
- [x] 5.7 Add device-binding tests covering focused-context `null` semantics, no field-mixing guarantees, and null-on-race behavior.
- [x] 5.8 Add tests that verify the S2b timestamp terminology and ordering invariants used by Gate calculations.

## Acceptance Verification

### 6. Automated verification

- [x] 6.1 Run `pytest tests/test_p1_s2b_routing.py` and fix failures until the routing suite passes.
- [x] 6.2 Run `pytest tests/test_p1_s2b_device_binding.py` and fix failures until the binding suite passes.
- [x] 6.3 Run the affected ingest/runtime regression tests that validate metadata mapping and `/v1/health` runtime fields.
- [x] 6.4 Verify that automated tests assert both functional outcomes and health/log evidence for filtered routing and topology rebuild.

### 7. Local gate script and evidence bundle

- [x] 7.1 Add `scripts/acceptance/p1_s2b_local.sh` as the dedicated S2b local gate entrypoint.
- [x] 7.2 Add helper coverage for topology verification using deterministic injection/mocking, operator-driven physical steps, or both.
- [x] 7.3 Make the S2b gate script emit the required evidence bundle: logs, health snapshots, spool checks, topology-change method, and execution context.
- [x] 7.4 Verify the gate script records `broken_window`, `alias-only payload`, and `mixed-version` exclusions when present.

### 8. Scenario and metric closure

- [x] 8.1 Verify SC-R1, SC-R2, SC-F1, SC-I1, SC-I2, and SC-O1 evidence against the frozen routing and context rules.
- [x] 8.2 Verify SC-T1, SC-T2, SC-T3, and SC-T4 evidence against topology rebuild and active-monitor parity rules.
- [x] 8.3 Verify that each topology scenario includes dual evidence: functional result plus Host registry/log and `/v1/health` parity for the same epoch.
- [x] 8.4 Compute and record `trigger_target_routing_correctness`, `device_binding_correctness`, `single_monitor_duplicate_capture_rate`, and `topology_rebuild_correctness` using the S2b proof-sample rules.
- [x] 8.5 Record `capture_to_ingest_latency_ms` by `device_name` as the required non-blocking S2b Soft KPI.
