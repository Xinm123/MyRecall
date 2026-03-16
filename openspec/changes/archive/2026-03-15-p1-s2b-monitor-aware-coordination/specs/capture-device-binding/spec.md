## ADDED Requirements

### Requirement: Final `device_name` MUST be bound by the monitor that actually performs capture
The event source MUST emit `capture_trigger` and routing hints only. The final persisted `device_name` MUST be assigned by the monitor-bound capture work item that actually produces the screenshot. The system MUST treat a mismatch between coordinator-selected target and worker-bound `device_name` as a binding failure or topology race; it MUST NOT silently rewrite the evidence after the fact.

**Acceptance impact**
- Hard Gate: `device_binding_correctness` MUST be 100%.

#### Scenario: Worker binds the monitor it actually captured
- **WHEN** the coordinator routes a capture task to an enabled monitor worker and that worker completes the screenshot
- **THEN** the resulting metadata MUST store that worker's `device_name` as the final binding

#### Scenario: Binding mismatch is surfaced as failure
- **WHEN** the worker cannot confirm that the captured screenshot belongs to the coordinator-selected monitor
- **THEN** the runtime MUST surface the event as a binding failure or equivalent non-success outcome instead of silently correcting `device_name`

### Requirement: Focused context MUST be emitted as a same-cycle bundle with explicit `null` fallback
`app_name` and `window_name` MUST be produced from one same-cycle focused-context snapshot for the captured monitor. The runtime MUST allow either field to be `null`, but it MUST NOT mix fields from different sources or reuse historical values from that monitor. Event-source `active_app` / `active_window` values are routing hints only, not authoritative persisted context. When the captured monitor is not the active/focused monitor or the context cannot be proven, the runtime MUST write `null` for both fields.

#### Scenario: Non-focused monitor capture writes null context
- **WHEN** a screenshot is captured from a monitor that is not the current active/focused monitor
- **THEN** the resulting metadata MUST write `app_name=null` and `window_name=null`

#### Scenario: Context fields are emitted together or not at all
- **WHEN** the runtime cannot obtain a same-cycle focused-context snapshot for the captured monitor
- **THEN** it MUST NOT combine `app_name` from one source with `window_name` from another source or prior capture

#### Scenario: Focus changes after routing but before worker finalization
- **WHEN** the coordinator routed a capture using same-cycle focus evidence, but the worker can no longer prove that the captured monitor is still the focused monitor for that capture cycle
- **THEN** the worker MUST persist `app_name=null` and `window_name=null` instead of promoting event-source hints to final metadata
