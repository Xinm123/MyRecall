# P1-S2b UI Evidence Index

- run_ts: 2026-03-15T08:55:07Z
- window_id: p1-s2b-20260315T085507Z
- edge_pid: unknown
- topology_method: injected
- gate_status: ✅ Pass

## Routing Scenarios
- [x] SC-R1 same-monitor click proof — `test_click_routes_to_primary_monitor_when_target_is_primary`
- [x] SC-R2 cross-monitor click proof — `test_click_routes_to_specific_monitor`
- [x] SC-F1 routing_filtered proof — `test_filtered_routing_produces_outcome_without_spool_enqueue`
- [x] SC-I1 per-monitor idle proof — `test_per_monitor_idle_partitions_reset_independently`
- [x] SC-I2 non-focused null-context proof — `test_non_focused_capture_writes_null_context`
- [x] SC-O1 one-action debounce proof — `test_same_monitor_debounce_and_cross_monitor_independence`

## Topology Scenarios
- [x] SC-T1 monitor add proof — `test_topology_add_monitor_scenario`
- [x] SC-T2 monitor remove proof — `test_topology_remove_monitor_scenario`
- [x] SC-T3 primary switch proof — `test_topology_primary_switch_updates_manual_target`
- [x] SC-T4 recovery proof — `test_topology_rebuild_add_remove_and_recovery`

## Exclusion Records
- [x] broken_window evidence — none detected (broken_window=false)
- [x] alias-only payload evidence — excluded (alias_only_count=0)
- [x] mixed-version evidence — excluded (mixed_version_count=0)

## Evidence References
- Metrics: `p1-s2b-metrics.json`
- Health snapshots: `p1-s2b-health-snapshots.json`
- Topology evidence: `p1-s2b-topology-evidence.json`
- Spool check: `p1-s2b-spool-check.json`
- Proof samples: `p1-s2b-proof-samples.json`
- Context: `p1-s2b-context.json`
