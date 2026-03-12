# P1-S2b AX Capture: Architecture Review Summary

**Date**: 2026-03-12  
**Reference**: External insights gathered from screenpipe, academic research, and EDA patterns  
**Status**: Ready for architecture review of P1-S2b implementation

---

## Quick Reference: Screenpipe Patterns MyRecall MUST Implement

### 1. Broadcast Channel for Trigger Distribution ✅
- **Why**: Non-blocking, prevents cascade failures, multi-monitor scalability
- **Pattern**: `tokio::sync::broadcast::channel(64)` — 64 capacity, Lagged handling
- **Implementation check**: Monitor loop detects `Lagged(n)` → immediate capture to drain backlog
- **Test**: Burst 100 events in 1s; verify no deadlock

### 2. 30-Second Forced-Write Floor (Non-Negotiable) ✅
- **Why**: Timeline fidelity guarantee — users must see activity within 30s windows
- **Pattern**: `Idle` and `Manual` triggers bypass dedup; always write. Other triggers dedup within 30s window.
- **MyRecall spec**: p1-s2b.md §1.0d, §3 step 7
- **Gate**: Max inter-write gap ≤ 45s per device (includes 15s variance margin)

### 3. Non-Blocking Permission Handling ✅
- **Why**: Captures must never block on accessibility permission denial
- **Pattern**: Return `None` on permission denied → proceed with screenshot + empty accessibility_text field
- **Permission state**: `granted` → `transient_failure` → `recovering` → `granted`
- **Design principle**: "Better None than wrong data" — skip AX if uncertain

### 4. Content-Hash Dedup (Exact Match, Empty Text Excluded) ✅
- **Why**: Eliminate duplicate frames (screenshot content unchanged, AX text unchanged)
- **Screenpipe**: u64 DefaultHasher → MyRecall: SHA256 (hex string)
- **Critical rule**: Empty text **never dedups** → preserve empty frames (OCR fallback handles)
- **Gate**: Content hash coverage ≥ 90% on non-empty AX frames

### 5. Per-Monitor Device Name Binding ✅
- **Why**: Pragmatic approach avoids global sync bottleneck; handles multi-monitor correctly
- **Pattern**: Trigger sent unbound → monitor worker assigns `device_name` independently at capture time
- **Constraint**: `focused_context = {app_name, window_name, browser_url}` + `device_name` must be non-split
- **Rule**: Better None than wrong window (`window_name=NULL` if uncertain)

### 6. Arc Stale URL Detection (Title Cross-Check) ✅
- **Why**: AppleScript latency (~107ms) causes stale URLs if user switches tabs during fetch
- **Pattern**: Fetch title + URL together → compare window title with title from AppleScript
- **Action**: Mismatch → reject URL, return None (stale)
- **Gate**: Browser URL success ≥ 95% on Chrome/Safari/Edge

---

## Intentional Deviations from Screenpipe (Documented & Justified)

| Item | Screenpipe | MyRecall P1-S2b | Justification |
|------|-----------|-----------|---------|
| AX Walk Timeout | 250ms (Rust/cidre) | 500ms (Python) | Python pyobjc has safety margin for complex apps |
| Content Hash | u64 in-memory | SHA256 hex (persistent) | Cross-session consistency + easier debugging |
| Permission State | Implicit in loop | Explicit state machine | More observable for debugging & TCC polling |
| Language | Rust (cidre bindings) | Python (pyobjc/macapptree) | Platform-native libraries; ADR-0013 documents choice |

---

## Gate Metrics & Verification Checklist

### Pre-Gate Validation

1. **Content Hash Coverage ≥ 90%** (non-empty AX frames)
   ```sql
   SELECT ROUND(100.0 * SUM(CASE WHEN content_hash IS NOT NULL 
     AND LENGTH(content_hash)=71 THEN 1 ELSE 0 END) / COUNT(*), 1)
   FROM frames WHERE TRIM(COALESCE(accessibility_text, '')) <> ''
   ```

2. **AX Walk Duration P95 < 500ms**
   - Measure tree walk time from screenpipe's TreeSnapshot model
   - Capture 100+ frames across diverse windows
   - Calculate P95 percentile

3. **Inter-Write Gap: Max ≤ 45s per Device**
   ```sql
   SELECT device_name, MAX(gap_seconds) AS max_gap_sec FROM (...) 
   GROUP BY device_name;
   ```
   - 30s floor enforced in code; 45s gate allows variance

4. **Browser URL Success ≥ 95%** (Chrome/Safari/Edge only)
   - Success rate: valid http(s) URLs returned
   - Rejected stale: Arc title mismatch (correctly rejected)
   - Failed all tiers: 3-tier fallback exhausted
   - Numerator: success / (success + rejected_stale + failed_all_tiers)

5. **Permission State Transitions Observable**
   - [ ] `granted` → `transient_failure` → `recovering` → `granted` logged
   - [ ] TCC revocation detected, state transitions correctly
   - [ ] No captures blocked (screenshot always written)

6. **Broadcast Channel Lag Handling**
   - [ ] Monitor detects `Lagged(n)` → immediate capture
   - [ ] No cascade/deadlock under burst load
   - [ ] Lag counter resets after drain

---

## Known Challenges & Solutions

### SQLite Write Contention (Screenpipe Issue #2181)
- **Problem**: Multiple writers → lock contention → 485–1088ms spikes
- **Solution**: Semaphore serialization, per-writer queue, 15s timeout protection
- **MyRecall**: S2b baseline (AX only) has lower contention; S3+ (OCR) will need same pattern

### Electron Async DOM Building
- **Problem**: VS Code, Figma, Discord return empty AX on first capture
- **Solution**: Accept empty frame as valid; next event fetches complete text
- **MyRecall**: Same approach; OCR fallback covers first-capture gaps

### macOS Permission (TCC) Handling
- **Screenpipe**: Implicit in capture loop (returns None on denial)
- **MyRecall**: Explicit permission state machine (more observable)
- **Both**: Non-blocking, graceful degradation

---

## Sources & Evidence

| Source | Type | Evidence |
|--------|------|----------|
| screenpipe/crates/screenpipe-server/src/event_driven_capture.rs | Implementation | Broadcast pattern, 30s floor, non-blocking degradation |
| screenpipe/crates/screenpipe-server/src/paired_capture.rs | Implementation | AX + content_hash paired capture, empty text handling |
| screenpipe Issue #2181 (2026-02) | Known issue | SQLite contention + semaphore solution |
| Screenpipe Blog (Feb 2026) | Design rationale | AX-first 100x less CPU than OCR |
| Screen2AX (MacPaw, arXiv:2507.16704) | Academic | Vision-based synthetic AX (P2+ exploration) |
| Mokarchi (2025) | EDA patterns | Back-pressure, rate limiting, graceful degradation |
| MyRecall ADR-0013 | Architecture | Event-driven-ax-split, Python implementation choices |
| MyRecall p1-s2b.md | Specification | Frozen requirements, gate criteria, handoff contract |

---

## Architecture Highlights

### What Makes This Design Robust

1. **Broadcast ≠ Queue**: Trigger source never blocked by slow monitors
2. **30-second floor**: Not performance; it's timeline fidelity (users see activity within windows)
3. **Non-blocking degrades gracefully**: Permission denied → proceed with screenshot + empty AX
4. **Content-hash dedup is semantics-aware**: Empty text excluded, Idle/Manual always write
5. **Device binding is pragmatic**: No global atomicity; each monitor owns its timestamp

### Why This Matters for MyRecall

- **Scalability**: Multi-monitor support without cascade failures
- **Reliability**: Non-blocking paths prevent watchdog timeouts
- **Data fidelity**: 30s floor guarantees searchable timeline
- **Maintainability**: Permission state machine explicit (vs implicit in loop logic)
- **Observability**: Broadcast lag, hash coverage, walk duration measurable

---

## For Architecture Review

### Red Flags to Check

- [ ] Is trigger broadcast implemented with lag handling?
- [ ] Is 30s forced-write floor enforced in code?
- [ ] Can permission denial happen without blocking captures?
- [ ] Is content_hash computed on text only (not including URL)?
- [ ] Are empty frames preserved (not deduplicated)?
- [ ] Is device_name assigned at monitor consumer time?
- [ ] Is Arc stale URL detection implemented (title cross-check)?

### Green Flags to Verify

- [ ] Broadcast channel capacity ≥ 64
- [ ] Lagged condition triggers immediate capture
- [ ] Idle/Manual triggers bypass dedup
- [ ] Permission returns None gracefully
- [ ] AX walk has timeout protection (500ms)
- [ ] Monitor loops poll at 50ms intervals
- [ ] Three-tier browser URL fallback implemented

---

## Next Steps

1. **Pre-Implementation Review** → Read screenpipe event_driven_capture.rs (640 lines)
2. **Implementation** → Follow checklist in §Verification Checklist
3. **Pre-Gate Testing** → Execute tests in §Pre-Gate Validation
4. **Gate Validation** → Verify all 4 metrics + permission/broadcast sanity checks
5. **Archive** → Document any implementation-specific deviations from pattern

---

**Full external insights**: See `p1-s2b-external-insights.md` (this directory)  
**Screenpipe reference commit**: 2026-03-07  
**MyRecall spec reference**: p1-s2b.md (2026-03-09)  
**Next review date**: After P1-S2b implementation code lands

