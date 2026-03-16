## Context

The current Host capture path already contains most of the raw building blocks for P1-S2b, but they are wired together using older S2a assumptions rather than the frozen S2b contract. `openrecall/client/events/base.py` already provides `MonitorDescriptor`, `MonitorRegistry`, per-device debounce, and the bounded trigger channel. `openrecall/client/events/macos.py` already enumerates monitors and resolves click points to a monitor. `openrecall/client/recorder.py` already owns permission gating, monitor refresh, screenshot capture, focused-context snapshotting, and spool enqueue. `openrecall/client/spool.py` and `openrecall/client/v3_uploader.py` already implement the v3 spool-to-`/v1/ingest` handoff.

The gap is semantic, not foundational. `TriggerEvent` still carries an event-source-owned `device_name`, `MacOSAppSwitchMonitor` still routes to the current primary monitor, `_wait_for_trigger()` still uses one global idle fallback device, `_capture_monitors()` still grabs every enabled monitor before selecting one image, and `_build_capture_metadata()` still fills app/window values from whichever source is available instead of enforcing `focused_context` same-cycle coherence and `routing_filtered`. On the server side, `openrecall/server/database/frames_store.py` can already normalize `active_app` and `active_window` aliases into `app_name` and `window_name`, but there is no runtime structure yet for S2b outcomes such as `routing_filtered`, `capture_completed`, or topology rebuild evidence.

## Goals / Non-Goals

**Goals:**
- Freeze a codebase-grounded design for P1-S2b that matches `docs/v3/spec.md`, `docs/v3/data-model.md`, `docs/v3/open_questions.md`, and `docs/v3/acceptance/phase1/p1-s2b.md`.
- Insert an explicit router/coordinator/worker boundary into the existing Python recorder path instead of replacing the recorder architecture.
- Make `device_name` binding, focused-context coherence, topology rebuild, and spool handoff semantics implementation-ready.
- Define the verification path for routing, binding, topology, and handoff without reopening OCR or AX scope.

**Non-Goals:**
- Reopening AX capture, `accessibility_text`, `content_hash`, browser URL collection, OCR processing, or any S3+ behavior.
- Replacing the existing v3 uploader retry policy, ingest idempotency model, or `/api/*` compatibility path.
- Introducing a second long-lived Host daemon, a non-Python capture stack, or a new persistence table for P1-S2b.
- Promising Windows/Linux parity before P2.

## Decisions

### D1: Introduce an internal routing stage before capture execution

**Choice:** Keep the existing event-source threads and `TriggerEventChannel`, but split trigger handling inside `openrecall/client/recorder.py` into two stages: a routing/coordinator stage that decides the target monitor set for each trigger, and a monitor-bound capture stage that executes exactly one capture task per chosen monitor. Event sources may keep routing hints such as click coordinates, active app/window names, or explicit manual targets, but they no longer own the final persisted `device_name`.

**Boundary clarification:** In P1-S2b, the coordinator is a logical stage inside the existing recorder runtime, not a mandated thread, daemon, or top-level class split. The artifacts freeze the coordinator/worker contract, not the exact class layout. The coordinator owns monitor-enablement state, per-monitor idle partitions, debounce partitions, topology epoch, and routed capture outcomes before capture execution starts.

**Routed work item contract:** Each routed work item MUST carry, at minimum, `capture_trigger`, `target_device_name`, `routing_topology_epoch`, `event_ts`, and any routing hints needed for worker-side validation. Workers MAY receive additional implementation-specific fields, but they MUST NOT need to infer the target monitor by rereading global trigger state.

**Why:**
- `docs/v3/spec.md` and `docs/v3/data-model.md` explicitly freeze `device_name` as monitor-worker-owned, while the current implementation binds it at trigger time.
- The recorder already centralizes permission state, debounce, topology refresh, and spool enqueue, so it is the least disruptive place to insert the missing routing layer.
- This lets the implementation express all four frozen routing modes (`specific-monitor`, `active-monitor`, `per-monitor-idle`, `coordinator-defined`) without forcing every event source to understand worker enablement and filtered outcomes.

**Alternatives considered:**
- Push all routing into `openrecall/client/events/macos.py`. Rejected because worker enablement, topology state, and debounce ownership already live in the recorder.
- Replace the recorder with one fully independent recorder thread per monitor. Rejected for P1 because it would rewrite the current runtime rather than evolve it.

**Screenpipe reference:** `_ref/screenpipe/crates/screenpipe-server/src/event_driven_capture.rs` and `_ref/screenpipe/crates/screenpipe-server/src/vision_manager/manager.rs` — **aligned** on the principle that capture work becomes monitor-bound before the screenshot path runs; **intentional divergence** because MyRecall keeps routing/coordinator ownership inside one Python recorder process rather than Screenpipe's Rust server-side vision manager.

### D2: Use the existing monitor refresh loop as the topology authority and rebuild point

**Choice:** Continue using `list_monitors()` plus `MonitorRegistry.refresh()` as the topology authority in `openrecall/client/recorder.py`, and extend that reconciliation step so monitor add/remove, primary-monitor changes, and temporary unavailability rebuild the enabled worker set, reset per-device debounce partitions, and update runtime observability state.

**Consistency rule:** Every routed work item is stamped with `routing_topology_epoch` from the monitor snapshot used for that routing decision. Before persisting metadata or writing spool artifacts, the worker MUST verify that the target monitor is still enabled for that epoch. If the task is stale because topology changed underneath it, the runtime MUST surface a non-success outcome and MUST NOT silently reroute, rebind, or persist a frame for a different monitor.

**Idle partition rule:** Per-monitor idle state is part of topology-owned coordinator state. When a monitor becomes newly enabled or recovers, its idle countdown starts fresh from rebuild completion. When a monitor is removed or disabled, its idle partition is dropped. Rebuilds MUST preserve the idle partitions of unchanged enabled monitors.

**Why:**
- The current recorder already calls `_refresh_monitors()` and `MonitorRegistry.refresh()` logs `device_name binding added` and `device_name binding removed`.
- This is sufficient for the frozen P1-S2b semantics without introducing a second watcher thread or callback-only architecture that does not yet exist in the codebase.
- The acceptance docs require registry/health consistency and topology recovery evidence, not a specific OS callback mechanism.

**Alternatives considered:**
- Add a dedicated Quartz reconfiguration callback as the only topology source. Rejected for P1 because the codebase already depends on polling refresh and the docs freeze behavior, not implementation style.
- Ignore topology changes until restart. Rejected because `topology_rebuild_correctness = 100%` is a Hard Gate.

**Screenpipe reference:** `_ref/screenpipe/crates/screenpipe-server/src/vision_manager/monitor_watcher.rs` — **aligned** on continuous monitor reconciliation and worker restart semantics; **intentional divergence** because MyRecall reuses its current recorder-loop refresh instead of Screenpipe's separate async watcher task for P1.

### D3: Bind final `device_name` and focused context inside monitor-bound capture work

**Choice:** After routing selects a target monitor, the monitor-bound capture step captures only that monitor, then emits one metadata bundle containing final `device_name`, `capture_trigger`, `event_ts`, and `focused_context = {app_name, window_name}`. If the captured monitor is not the active/focused monitor or the context cannot be proven for the same cycle, the bundle writes `null` for `app_name` and `window_name` instead of reusing prior values. The Host spool writes canonical `app_name` and `window_name` keys and may keep alias keys only as a compatibility bridge for unchanged ingest adapters.

**Timing clarification:** Event-source `active_app` / `active_window` values are routing hints only. They can help resolve `app_switch` routing, but they MUST NOT become final persisted context unless the worker can prove same-cycle focused-context coherence for the captured monitor. If focus changes between routing and worker finalization, or the worker cannot prove the captured monitor is still the focused monitor for this capture cycle, the worker MUST write `app_name=null` and `window_name=null`.

**Why:**
- The current `_capture_monitors()` grabs every monitor on each trigger and `_build_capture_metadata()` falls back to whichever app/window source is available, which violates the S2b `Better None than wrong` rule.
- `openrecall/server/database/frames_store.py` already accepts canonical keys and existing aliases, so the canonicalization can happen at the Host boundary without changing `/v1/ingest`.
- This keeps S2b responsible only for frozen capture metadata and leaves S3 to consume the resulting fields without additional repair logic.

**Alternatives considered:**
- Continue binding `device_name` at trigger time and only verify it later. Rejected because the docs freeze worker-owned binding, not post-hoc validation.
- Fill missing app/window values with the last known focused app on that monitor. Rejected because both `spec.md` and `data-model.md` explicitly forbid stale reuse.

**Screenpipe reference:** `_ref/screenpipe/crates/screenpipe-db/src/migrations/20260220000000_event_driven_capture.sql` and `_ref/screenpipe/crates/screenpipe-server/src/paired_capture.rs` — **aligned** on carrying `device_name` as first-class capture metadata; **intentional divergence** because MyRecall freezes same-cycle focused-context `null` semantics for non-focused monitor captures, which Screenpipe does not expose as a comparable requirement.

### D4: Record routing/capture outcomes through the existing heartbeat mirror and health view

**Choice:** Extend the current heartbeat-driven runtime mirror so the Host reports a compact `capture_runtime` block that includes `topology_epoch`, `primary_monitor_only`, `active_monitors`, and `last_capture_outcome`. The server keeps deriving `/v1/health` from mirrored Host state, while P1-S2b adds the required capture outcomes (`capture_completed`, `routing_filtered`, `permission_blocked`, `spool_failed`, `schema_rejected`, `topology_rebuilt`) for acceptance evidence.

**Outcome clarification:** `routing_filtered` is not purely a negative assertion. Every filtered routing decision MUST update `capture_runtime.last_capture_outcome` and emit observable evidence including the trigger type, resolved target monitor, and filter reason. The exact log format remains implementation-defined, but the evidence fields and health visibility are frozen.

**Timestamp glossary:**
- `event_ts`: Host trigger time, emitted by the trigger source for the capture cycle.
- `timestamp`: Host capture-completion / spool-write completion time for the persisted capture. For S2b Gate calculations, this is the value referred to as `capture_completed_ts`.
- `ingested_at`: Edge database commit time after `/v1/ingest` succeeds.

**Ordering invariant:** For any persisted frame that participates in S2b evidence, `event_ts <= timestamp <= ingested_at` must hold when all values are present and valid. Samples that violate the ordering rule are observation anomalies and must be excluded from latency proof calculations rather than silently repaired.

**Why:**
- The current recorder already sends heartbeat payloads and the server already mirrors runtime state; this is the cleanest place to expose S2b evidence without inventing a new API.
- The acceptance doc explicitly requires `/v1/health.capture_runtime.last_capture_outcome` and active-monitor evidence.
- Outcome reporting must remain orthogonal to OCR processing because S2b owns raw handoff correctness, not semantic processing success.

**Alternatives considered:**
- Infer S2b outcomes from DB writes only. Rejected because `routing_filtered` and topology rebuild evidence can occur without persisted frames.
- Add a dedicated `/v1/capture-runtime` endpoint. Rejected because the docs already anchor health/runtime visibility on `/v1/health`.

**Screenpipe reference:** `_ref/screenpipe/crates/screenpipe-server/src/routes/health.rs` — **aligned** on deriving health from runtime state rather than from UI inference; **intentional divergence** because MyRecall needs a richer `capture_runtime` evidence block for S2b Gate closure and Screenpipe does not expose the same outcome taxonomy.

### D5: Deliver P1-S2b through TDD plus a local gate script, not through ad hoc manual validation

**Choice:** Treat `tests/test_p1_s2b_routing.py`, `tests/test_p1_s2b_device_binding.py`, and `scripts/acceptance/p1_s2b_local.sh` as mandatory artifacts of this change. The implementation work should land through focused unit/integration tests first, and the local gate script should orchestrate those tests plus health snapshots, spool checks, and evidence bundle generation once the behavior is stable.

**Why:**
- `docs/v3/open_questions.md` explicitly freezes S2b as "TDD development + local gate script".
- The routing, binding, and topology rules are mechanical enough to encode directly as tests before writing implementation code.
- A dedicated gate script keeps the proof chain repeatable and prevents the phase from depending on undocumented manual checks.

**Alternatives considered:**
- Write only the gate script and rely on manual scenario execution. Rejected because OQ-041 explicitly separates contract discovery from phase-close orchestration.
- Fold S2b cases into older S2a tests and scripts. Rejected because S2b owns distinct routing/topology semantics and deliverables.

**Screenpipe reference:** `_ref/screenpipe/docs/EVENT_DRIVEN_CAPTURE_SPEC.md` — **aligned** on specifying capture behavior before implementation; **no comparable pattern** for MyRecall's exact local gate artifact set, which is project-specific.

## Risks / Trade-offs

- **Coordinator complexity increases** -> keep the routing stage explicit and data-oriented so the recorder does not hide monitor decisions inside ad hoc conditionals.
- **macOS app-switch monitor inference may be imperfect** -> route from the best same-cycle evidence available, prefer `routing_filtered` or `null` over a wrong monitor/app binding, and cover the edge cases in dedicated routing tests.
- **Topology changes can race with capture execution** -> stamp topology snapshots/epochs into routing decisions and treat coordinator-worker mismatches as explicit binding failures rather than silently correcting them.
- **Topology changes can race with capture execution** -> stamp topology snapshots/epochs into routing decisions and treat stale tasks or coordinator-worker mismatches as explicit non-success outcomes rather than silently correcting them.
- **Heartbeat payload growth could blur concerns** -> keep `capture_runtime` compact and evidence-oriented, separate from queue and permission fields already mirrored today.
- **Canonical metadata changes can break older assumptions** -> keep server-side alias normalization intact while moving Host writes to canonical `app_name` and `window_name` keys.

## Migration Plan

1. Refactor the recorder path to derive routing decisions before screenshot capture while preserving the current permission gate and uploader lifecycle.
2. Move `device_name` binding and focused-context finalization into monitor-bound capture work.
3. Extend heartbeat/runtime mirroring so `/v1/health` can expose S2b capture-runtime evidence.
4. Add the dedicated routing and device-binding test files, then add the S2b local gate script once the behavioral tests pass.
5. No schema migration or rollback cleanup is required for the OpenSpec change itself; rollback remains code-only because the existing `frames` schema already stores the required S2b metadata fields.

## Open Questions

- None for artifact generation. The remaining uncertainty is implementation detail inside the coding phase, not a spec-level blocker: the change should proceed with the frozen S2b behavior and resolve any macOS-specific monitor inference gaps through tests and the minimal code path that satisfies the documented scenarios.
