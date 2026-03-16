## ADDED Requirements

### Requirement: Trigger routing MUST select target monitors using the frozen P1-S2b taxonomy
The Host capture runtime MUST route triggers in two stages: event sources emit trigger facts, then the routing/coordinator layer selects the target monitor set before any screenshot work begins. The routing taxonomy MUST be: `click -> specific-monitor`, `app_switch -> active-monitor`, `idle -> per-monitor-idle`, and `manual -> coordinator-defined`. `OPENRECALL_PRIMARY_MONITOR_ONLY` MUST filter only the enabled monitor set; it MUST NOT rewrite the meaning of the trigger itself.

**Acceptance impact**
- Hard Gate: `trigger_target_routing_correctness` MUST be 100% using the sample rules in `docs/v3/gate_baseline.md`.

#### Scenario: Click routes to the monitor containing the pointer
- **WHEN** a `click` trigger is emitted at coordinates that belong to an enabled monitor
- **THEN** the coordinator MUST route capture work only to that monitor

#### Scenario: App switch to a disabled target monitor is filtered before capture
- **WHEN** an `app_switch` trigger resolves to a monitor that is not enabled because `OPENRECALL_PRIMARY_MONITOR_ONLY=true`
- **THEN** the coordinator MUST emit `routing_filtered` and MUST NOT enqueue screenshot work, spool files, or persisted frames

#### Scenario: Manual trigger defaults to the current primary monitor
- **WHEN** a `manual` trigger does not specify an explicit monitor target
- **THEN** the coordinator MUST route it to the current primary enabled monitor

#### Scenario: Idle routing is evaluated per enabled monitor
- **WHEN** the idle deadline expires for one enabled monitor
- **THEN** the coordinator MUST route an `idle` capture only for that monitor without forcing captures for other enabled monitors whose idle deadline has not expired

### Requirement: Per-monitor idle partitions MUST reset independently and rebuild predictably
Each enabled monitor MUST maintain its own idle partition. A capture completion for one monitor MUST reset only that monitor's idle deadline. Topology rebuilds MUST preserve unchanged monitors' idle partitions, drop removed monitors' idle partitions, and start a fresh idle deadline for newly enabled or recovered monitors.

#### Scenario: Local capture completion resets only the local idle deadline
- **WHEN** Monitor A completes a capture and Monitor B remains enabled
- **THEN** Monitor A's idle deadline MUST reset while Monitor B's idle deadline continues unaffected

#### Scenario: Recovered monitor starts with a fresh idle deadline
- **WHEN** a previously unavailable monitor becomes enabled again during the same Host run
- **THEN** the coordinator MUST create a fresh idle partition for that monitor from rebuild completion time instead of reusing stale idle state

### Requirement: `routing_filtered` MUST remain observable even though it creates no persisted frame
When a trigger resolves to `routing_filtered`, the runtime MUST avoid all persistence side effects while still exposing the outcome for verification. At minimum, the decision MUST update `/v1/health.capture_runtime.last_capture_outcome` and MUST emit Host-side evidence containing the trigger type, target monitor, and filter reason.

#### Scenario: Filtered trigger is observable without spool or frame artifacts
- **WHEN** a valid trigger resolves to `routing_filtered`
- **THEN** the runtime MUST create no spool or database artifacts, and it MUST still expose `last_capture_outcome=routing_filtered` plus filter evidence in Host logs

### Requirement: Same-monitor overlap MUST be debounced while cross-monitor captures remain independent
When one user action causes multiple triggers inside the shared `min_capture_interval_ms` window, the runtime MUST debounce repeated work within the same monitor scope while still allowing different monitors to capture independently.

**Acceptance impact**
- Hard Gate: `single_monitor_duplicate_capture_rate` MUST be 0% using the mechanical definition in `docs/v3/gate_baseline.md`.

#### Scenario: Same-monitor click and app switch collapse to one persisted capture
- **WHEN** `click` and `app_switch` triggers from one user action both route to the same monitor inside one `min_capture_interval_ms` window
- **THEN** the runtime MUST persist at most one frame for that monitor scope

#### Scenario: Cross-monitor routing does not count as a duplicate capture
- **WHEN** one user action produces trigger work for different monitors
- **THEN** the runtime MAY persist one frame per target monitor and MUST NOT classify those frames as same-monitor duplicates
