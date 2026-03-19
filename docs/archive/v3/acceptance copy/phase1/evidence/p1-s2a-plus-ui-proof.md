# P1-S2a+ UI Evidence Index

- run_ts: 2026-03-13T15:14:11Z
- window_id: p1-s2a-plus-20260313T151411Z
- edge_pid: unknown
- base_url: http://localhost:8083
- health_snapshots: p1-s2a-plus-health-snapshots.json
- permission_transitions: p1-s2a-plus-permission-transitions.jsonl

## Required Scenario Proof

1. startup_not_determined
   - [ ] health snapshot
   - [ ] UI guidance proof
   - [ ] log reference
2. startup_denied
   - [ ] health snapshot
   - [ ] degraded UI proof
   - [ ] log reference
3. revoked_mid_run
   - [ ] permission timeline proof
   - [ ] degraded health proof
   - [ ] capture-stop proof
4. restored_after_denied
   - [ ] recovering health proof
   - [ ] granted recovery proof
   - [ ] no-restart proof
5. stale_permission_state
   - [ ] stale health proof
   - [ ] degraded UI proof
   - [ ] log reference
