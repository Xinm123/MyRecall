## ADDED Requirements

### Requirement: Monitor topology changes MUST rebuild worker eligibility and routing state
The Host runtime MUST reconcile monitor topology continuously. When monitors are added, removed, change primary status, or temporarily disappear and recover, the enabled worker set, routing eligibility, and per-monitor debounce/idle partitions MUST be rebuilt so that subsequent routing decisions reflect the new topology.

Routed work items MUST carry `routing_topology_epoch` from the topology snapshot that produced them. Before persisting spool artifacts or final metadata, a worker MUST verify that its target monitor is still valid for that epoch. If the task is stale because topology changed in the meantime, the runtime MUST emit a non-success outcome and MUST NOT silently reroute, rebind, or persist a frame for a different monitor.

**Acceptance impact**
- Hard Gate: `topology_rebuild_correctness` MUST be 100%.

#### Scenario: Added monitor becomes routable after rebuild
- **WHEN** a new monitor appears during runtime
- **THEN** the monitor registry and enabled worker set MUST include that monitor before subsequent eligible triggers are routed to it

#### Scenario: Removed monitor stops receiving capture work
- **WHEN** a monitor is disconnected or otherwise removed from the active topology
- **THEN** the runtime MUST stop routing new capture work to that `device_name`

#### Scenario: Primary monitor change updates primary-only routing
- **WHEN** the primary display changes while `OPENRECALL_PRIMARY_MONITOR_ONLY=true`
- **THEN** subsequent primary-only routing decisions MUST use the new primary monitor

#### Scenario: Temporarily unavailable monitor can recover without restart
- **WHEN** a previously enabled monitor disappears and later becomes available again in the same run
- **THEN** the runtime MUST restore routing eligibility for that monitor without requiring a Host or Edge restart

#### Scenario: Stale routed task is rejected after topology change
- **WHEN** a worker receives or is about to finalize a routed task whose `routing_topology_epoch` no longer matches the active topology state for that monitor
- **THEN** the runtime MUST reject that task as stale, emit a non-success outcome, and MUST NOT persist spool or frame artifacts for a different monitor binding

### Requirement: Runtime topology evidence MUST stay consistent across registry and health views
The runtime MUST expose one coherent view of active monitors and capture-topology state for acceptance evidence. `MonitorRegistry` state and `/v1/health.capture_runtime.active_monitors` MUST describe the same enabled monitor set for a given topology epoch.

#### Scenario: Registry and health expose the same active monitors
- **WHEN** the topology changes and reconciliation completes
- **THEN** the monitor list shown by the Host registry and the monitor list surfaced through `/v1/health.capture_runtime.active_monitors` MUST match

#### Scenario: Topology epoch is consistent across routing and evidence
- **WHEN** a topology rebuild completes and a subsequent trigger is routed
- **THEN** the routed work item, the Host registry view, and `/v1/health.capture_runtime.topology_epoch` MUST all reflect the same active topology epoch for that routing decision
