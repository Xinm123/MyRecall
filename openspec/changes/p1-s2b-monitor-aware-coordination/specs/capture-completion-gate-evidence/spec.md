## ADDED Requirements

### Requirement: P1-S2b MUST ship dedicated routing and binding verification artifacts
The change MUST deliver dedicated verification artifacts for routing, binding, topology rebuild, and spool handoff correctness. At minimum, the change MUST include `tests/test_p1_s2b_routing.py`, `tests/test_p1_s2b_device_binding.py`, and `scripts/acceptance/p1_s2b_local.sh` as first-class delivery artifacts for the phase.

**Acceptance impact**
- Required evidence: the S2b local gate MUST produce the logs, health snapshots, spool checks, and context bundle required by `docs/v3/acceptance/phase1/p1-s2b.md`.

#### Scenario: Dedicated routing tests exist for frozen trigger semantics
- **WHEN** the S2b implementation is verified in automated tests
- **THEN** there MUST be dedicated tests that exercise the frozen routing modes, filtered outcomes, duplicate-capture rules, and topology rebuild scenarios

#### Scenario: Dedicated binding tests exist for metadata coherence
- **WHEN** the S2b implementation is verified in automated tests
- **THEN** there MUST be dedicated tests that exercise worker-owned `device_name` binding and focused-context `null`/same-cycle coherence rules

### Requirement: Topology and filtered-routing proof MUST use dual evidence
S2b verification MUST prove both behavior and observability. For topology rebuild and `routing_filtered` scenarios, tests or gate scripts MUST assert (a) the functional result, and (b) the corresponding evidence exposed through Host logs and `/v1/health.capture_runtime`.

#### Scenario: Filtered routing is proven by both absence and outcome evidence
- **WHEN** a trigger is intentionally routed to `routing_filtered`
- **THEN** verification MUST assert both that no spool/frame artifacts were created and that `capture_runtime.last_capture_outcome` plus Host logs record the filtered decision

#### Scenario: Topology rebuild is proven by both state parity and scenario outcome
- **WHEN** a topology change scenario is executed for S2b verification
- **THEN** verification MUST assert both the functional routing result for that scenario and the parity of Host registry evidence, `/v1/health.capture_runtime.active_monitors`, and `/v1/health.capture_runtime.topology_epoch`

### Requirement: S2b proof windows MUST exclude incompatible samples
S2b Gate proof MUST use only continuous windows that satisfy the frozen sampling rules. Samples marked `alias-only payload`, `mixed-version`, or `broken_window=true` MUST be excluded from Gate proof calculations.

**Acceptance impact**
- Required sample rule: Hard Gate calculations MUST follow the exclusion rules and minimum sample requirements in `docs/v3/acceptance/phase1/p1-s2b.md` and `docs/v3/gate_baseline.md`.

#### Scenario: Broken windows are excluded from Gate proof
- **WHEN** a Host or Edge restart occurs inside an S2b verification window
- **THEN** the resulting samples MUST be marked `broken_window=true` and excluded from Hard Gate proof

#### Scenario: Alias-only payloads do not count as proof samples
- **WHEN** a payload reaches Edge using only compatibility aliases and does not satisfy the canonical S2b field set
- **THEN** that sample MUST be excluded from S2b Gate proof even if it is accepted for compatibility reasons

### Requirement: S2b topology verification MUST support either injected or manual topology changes
The local gate MAY satisfy topology scenarios using deterministic monitor-topology injection/mocking, real hardware operator steps, or both. Regardless of method, the evidence bundle MUST capture the change method, the before/after health snapshots, and the Host log window used to justify the result.

#### Scenario: Gate records topology evidence collection method
- **WHEN** the local gate evaluates SC-T1, SC-T2, SC-T3, or SC-T4
- **THEN** the evidence bundle MUST record whether the topology change was produced by injected test doubles, helper tooling, or operator-driven physical steps
