# P1-S2b AX Capture: External Reference Insight Note

**Date**: 2026-03-12  
**Scope**: Architecture-level patterns from screenpipe (vision-only capture pipeline) and related systems  
**Audience**: Architecture review, P1-S2b gate validation, upstream pattern analysis  
**Focus**: Capture triggering, debounce/backpressure, permission handling, verification patterns

---

## 1. SCREENPIPE: FOUNDATIONAL REFERENCE (Rust, Proven in Production)

### 1.1 Event-Driven Trigger Broadcasting (Multi-Monitor Pattern)

**Source**: `screenpipe/crates/screenpipe-server/src/event_driven_capture.rs:1-110`

**Pattern**:
- **Global trigger broadcast** using `tokio::sync::broadcast::channel(64)`
  - Capacity: 64 pending events
  - Multi-receiver: Each monitor worker subscribes independently
  - Non-blocking publish: External event sources (app switch, click, typing pause) send to shared channel
  
- **Per-monitor consumption loop**:
  ```rust
  event_driven_capture_loop(
    trigger_rx: TriggerReceiver,    // receives from global broadcast
    monitor_id: u32,
    device_name: String,            // determined at consumer time, not source
    ...
  )
  ```
  - Monitor worker polls broadcast at 50ms intervals (`Duration::from_millis(50)`)
  - Handles `Lagged(n)` condition (channel full) → triggers `Manual` capture immediately to drain backlog
  - Gracefully closes on `Closed` error (trigger source shutdown)

**MyRecall Relevance**:
- P1-S2a implements trigger source (event listeners)
- P1-S2b must ensure per-monitor AX capture loop subscribes to trigger broadcast
- **Backpressure pattern**: If S2b monitor loop is slow, broadcast Lagged condition signals need to drain (not block external event source)

**Architecture note**: Broadcast design prevents "thundering herd" problem—each monitor processes independently; doesn't cascade.

---

### 1.2 Debounce Strategy: "Min Interval + 30-Second Floor"

**Source**: `screenpipe/crates/screenpipe-server/src/event_driven_capture.rs:240-244, 560-586`

**Pattern**:
```rust
// Track last DB write time
let mut last_db_write = Instant::now();

// On each trigger:
let dedup_eligible = !matches!(trigger, CaptureTrigger::Idle | CaptureTrigger::Manual)
    && last_db_write.elapsed() < Duration::from_secs(30);

if dedup_eligible {
    if prev_hash == new_hash {
        return None;  // Skip write (dedup)
    }
}
// Always write if: (1) Idle/Manual trigger OR (2) 30s elapsed
```

**Key behaviors**:
1. **Content-hash dedup** only applies to user-action triggers (AppSwitch, Click, etc.) within 30s window
2. **Idle and Manual triggers bypass dedup** → force write every 30s guaranteed
3. **Empty text never dedups** → preserves frame even if no AX text
4. **Result**: Timeline never has gaps > 30s (hard floor guarantee)

**MyRecall P1-S2b alignment**:
- Spec mandates same 30s floor (p1-s2b.md §1.0d, §3 step 7)
- Use SHA256 instead of u64 hash → semantically equivalent (exact match dedup)
- **Gate criterion**: Max inter-write gap ≤ 45s per device (soft margin for network/processing variance)

**Critical insight**: 30s floor is not just performance optimization—it's a **timeline fidelity guarantee**. If dedup is too aggressive, user never sees activity in certain time windows.

---

### 1.3 Permission Handling: Non-Blocking Degradation (No Panic)

**Source**: `screenpipe/crates/screenpipe-server/src/event_driven_capture.rs:203-420`

**Pattern**:
- **Accessibility permission denial**: AX tree walk returns `None` (graceful failure)
  - No exception thrown
  - No thread blocked
  - Frame still written to disk (screenshot captures)
  - S3-equivalent processing layer decides fallback (OCR)

- **Sleep/Screen lock detection**: Skip captures, don't error
  ```rust
  if crate::sleep_monitor::screen_is_locked() {
      tokio::time::sleep(poll_interval).await;
      continue;  // Skip, try again
  }
  ```

- **Power profile changes**: Watch channel polls non-blocking updates
  ```rust
  if let Some(ref mut rx) = power_profile_rx {
      if rx.has_changed().unwrap_or(false) {
          let profile = rx.borrow_and_update().clone();
          // Apply new debounce/quality settings
      }
  }
  ```

**MyRecall relevance**:
- P1-S2b must **not block on permission denial**
- Permission state machine: `granted` → `transient_failure` → `recovering` → `granted`
  - TCC (Transparency, Consent, Logging) permission check happens async
  - Non-blocking fallback: return empty `accessibility_text` field, proceed with screenshot + OCR path
- **Design principle**: "Better None than wrong data" — skip AX if uncertain (Electron async DOM case, permission edge cases)

---

### 1.4 Multi-Monitor Binding: Device Name Assigned at Consume Time

**Source**: `screenpipe/crates/screenpipe-server/src/event_driven_capture.rs:200-210, 380-386`

**Pattern**:
- Event source sends **unbound trigger** (app_name, window_name from focused context at trigger source time)
- Per-monitor loop assigns `device_name` **independently** at capture time
- Result: same trigger processes on multiple monitors with different `device_name` values
  - No attempt to globally sync "which screenshot on which monitor" at trigger moment
  - Each monitor uses its own `SafeMonitor` instance to fetch frame + AX

**MyRecall relevance** (P1-S2b §1.0e):
- Frozen alignment: trigger broadcast sends global event (no device binding)
- S2b monitor worker assigns `device_name` at capture time
- **Constraint**: `focused_context = {app_name, window_name, browser_url}` + `capture_device_binding = {device_name}` must be non-split
  - One AX snapshot → one device binding
  - No partial context from different sources

---

## 2. BROADER ECOSYSTEM: CAPTURE PIPELINE PATTERNS

### 2.1 Vision Framework (macOS/iOS) – On-Device Text Recognition

**Source**: WWDC 2025 Vision Framework updates + Apple Vision documentation  
**Key insight**: Native OCR fallback alternative to Tesseract

**Patterns**:
- Vision framework: 25+ APIs for ML-based image analysis
- Real-time performance: suitable for fallback when AX unavailable
- Apple Intelligence integration (M-series Macs): local on-device summarization/action extraction
- **Relevance to MyRecall P1-S3**: Vision framework could replace RapidOCR for macOS path (P1 currently fixed on RapidOCR)

---

### 2.2 Screen2AX (Academic, 2025) – Vision-Based Accessibility Generation

**Source**: arXiv:2507.16704 (MacPaw research)  
**Key insight**: When native AX unavailable, use vision-based synthetic AX tree

**Pattern**:
- Input: screenshot only
- Output: synthetic AXDocument tree (roles, descriptions, hierarchy)
- Use case: Apps with no accessibility support (legacy, closed-source remote desktops)

**Relevance**: 
- Complements screenpipe's dual-path approach (AX-first, OCR fallback)
- Could be P2+ enhancement if dealing with problematic legacy apps
- **Current MyRecall strategy**: OCR text extraction (simpler, proven), not synthetic AX tree generation

---

### 2.3 Back-Pressure in Event-Driven Architectures (Medium/Generic)

**Source**: A. Mokarchi, "Managing Back-Pressure in Event-Driven Architectures" (2025)  
**Patterns**:
- **Rate limiting**: Token bucket to cap event processing rate
- **Queue depth monitoring**: When pending events exceed threshold, signal upstream to slow down
- **Graceful degradation**: Drop lowest-priority events rather than cascade failure
- **Timeout enforcement**: Prevent indefinite blocking of downstream processors

**MyRecall relevance**:
- S2b capture loop timeout: `tokio::time::timeout(Duration::from_secs(15), do_capture(...))` (screenpipe pattern)
- Broadcast channel lag handling: If monitor loop slow, channel fills → detectable via `Lagged(n)` → trigger immediate capture to flush
- **For P1-S2b gate**: Measure capture latency P95, ensure no sustained backlog

---

## 3. SCREENPIPE HEALTH CHECK & VERIFICATION PATTERNS

### 3.1 Health Check Debouncing (Stability Signal)

**Source**: `screenpipe/crates/screenpipe-server/tests/health_debounce_test.rs`

**Pattern** (UI resilience):
```
Status Machine:
  Starting (0–30s startup grace period, never connected)
  ↓
  Recording (connected once, even if briefly failing)
  ↓
  Error (3+ consecutive health check failures)
  ↓
  Stopped (connection lost)
```

**Principle**: UI shows "Starting" for 30s even if health endpoint fails → avoids false negatives during app startup.

**MyRecall relevance**:
- Client health polling for server readiness (Client-to-Edge uplink verification)
- Don't show "error" until stable failure pattern observed (threshold: 3 consecutive failures)

---

## 4. CRITICAL ARCHITECTURAL DECISIONS FOR P1-S2B REVIEW

| Decision | Screenpipe Approach | MyRecall P1-S2b | Review Note |
|----------|-------|-----------|---------|
| **Trigger Broadcasting** | Tokio broadcast channel (64 capacity) | Same pattern required | Backpressure handling critical—monitor loop must not starve trigger source |
| **Debounce Floor** | 30s hard floor (Idle/Manual bypass dedup) | 30s (frozen) | Gate: max gap <= 45s allows 15s network/processing margin |
| **Content Hash** | u64 DefaultHasher | SHA256 hex | Different function, same semantics (exact-match dedup) |
| **Empty Text** | Skip dedup, preserve frame | Skip dedup, preserve frame | Ensures empty AX frames still written (OCR fallback handles) |
| **Device Binding** | Assigned at monitor consumer time | Same pattern required | No global timestamp atomicity attempt—pragmatic choice |
| **Permission Denial** | Return None, continue (non-blocking) | Same pattern required | Never panic/block on TCC; degrade gracefully |
| **Sleep/Lock Detection** | Skip captures, poll at interval | Same pattern required | Avoids storing black/locked frames |
| **Arc URL Stale Detection** | Title cross-check, reject if mismatch | Same pattern (p1-s2b §1.0) | Critical for browser URL accuracy |
| **Electron Async DOM** | Accept empty AX on first capture | Accept empty AX on first capture | Don't retry; next event will fetch complete text |
| **AX Tree Timeout** | 250ms (Rust/cidre perf) | 500ms (Python safety margin) | Documented deviation; reasonable for Python pyobjc |
| **Multi-Monitor Loop** | Independent per-monitor consumers | Same pattern required | Avoids global sync bottleneck |

---

## 5. PATTERNS TO VALIDATE IN P1-S2B IMPLEMENTATION

### 5.1 Broadcast Channel Lag Handling
**Verification**: 
- [ ] Monitor loop detects `Lagged(n)` condition
- [ ] Responds with immediate capture (drain backlog, reset lag counter)
- [ ] Logs incident for observability
- **Test**: Burst 100 events in 1s; verify no cascade or deadlock

### 5.2 Content Hash Coverage (Gate #1)
**Verification**:
```sql
SELECT
  COUNT(*) AS total_ax_frames,
  SUM(CASE WHEN content_hash IS NOT NULL AND LENGTH(content_hash)=71 THEN 1 ELSE 0 END) AS with_hash,
  ROUND(100.0 * with_hash / total_ax_frames, 1) AS coverage_pct
FROM frames
WHERE TRIM(COALESCE(accessibility_text, '')) <> ''
  AND timestamp >= datetime('now', '-5 minutes');
-- Expected: coverage_pct >= 90%
```
**Source**: Screenpipe guarantees hash on non-empty text (tree/mod.rs:79-85)

### 5.3 AX Walk Duration P95 (Gate #2)
**Verification**:
- Measure each `do_capture()` tree walk time (screenpipe records in TreeSnapshot)
- Calculate P95 percentile
- **Gate**: P95 < 500ms
**Test**: Capture 100+ frames across diverse app windows

### 5.4 Inter-Write Gap (Gate #3)
**Verification**:
```sql
SELECT device_name, MAX(gap_seconds) AS max_gap_sec
FROM (
  SELECT device_name, timestamp,
         (julianday(timestamp) - julianday(prev_ts)) * 86400.0 AS gap_seconds
  FROM ordered_frames
) WHERE prev_ts IS NOT NULL
GROUP BY device_name;
-- Expected: ALL devices max_gap_sec <= 45s (soft margin on 30s floor)
```
**Interpretation**: 30s floor enforced by code; 45s gate allows variance

### 5.5 Browser URL Success Rate (Gate #4)
**Verification**:
```sql
SELECT
  SUM(CASE WHEN browser_url LIKE 'http%' THEN 1 ELSE 0 END) AS success,
  SUM(CASE WHEN browser_url IS NULL THEN 1 ELSE 0 END) AS null_url,
  ROUND(100.0 * success / NULLIF(success + null_url, 0), 1) AS pct
FROM frames
WHERE app_name IN ('Chrome', 'Safari', 'Edge')
  AND timestamp >= datetime('now', '-30 minutes');
-- Expected: pct >= 95%
```
**Screenpipe three-tier fallback achieves 95%+** → MyRecall must implement same logic (p1-s2b §1.0)

### 5.6 Permission State Transitions
**Verification**:
- [ ] Detect `permission_state: granted` at startup
- [ ] Handle `transient_failure` (Electron, async DOM) → log, continue
- [ ] Detect `permission_revoked` (user disabled TCC) → enter `recovering` state
- [ ] Poll at `permission_poll_interval_sec` (default: 10s)
- [ ] Transition back to `granted` when permission re-enabled
- **Non-blocking**: All transitions allow capture to proceed (screenshot always written)

---

## 6. KNOWN CHALLENGES & SCREENPIPE SOLUTIONS

### 6.1 SQLite Write Contention (Screenpipe Issue #2181, 2026-02)

**Problem**: Multiple concurrent writers (OCR, AX, audio) → `BEGIN IMMEDIATE` lock contention → 485–1088ms insert spikes

**Screenpipe solution**:
- Semaphore serialization (one writer at a time to DB)
- Per-writer queue (prevent pile-up of requests)
- Timeout protection (15s capture timeout prevents indefinite waits)
- Health metrics track write latency

**MyRecall relevance** (P1-S3+):
- When adding OCR fallback, expect similar contention
- S2b baseline: only AX writes (single path) → lower contention
- Gate metric: capture latency P95 (non-blocking heartbeat, not writes)

---

### 6.2 Accessibility Permission on macOS

**Screenpipe approach**:
- Uses cidre (Rust bindings to NSAccessibilityElement)
- Graceful None return on permission denial
- No retry logic (let next trigger fetch)

**MyRecall approach** (P1-S2b):
- Uses pyobjc + macapptree (Python bindings)
- Same None return pattern
- Permission state machine (granted/denied/recovering) explicit
- TCC guide/retry loop in P1-S2a (already complete)

**Key difference**: MyRecall formalizes permission state tracking; Screenpipe implicit in loop logic.

---

### 6.3 Electron Async Tree Building

**Problem**: Electron apps (VS Code, Figma, Discord) build DOM asynchronously → first AX query returns empty; second query (after event) returns full tree.

**Both screenpipe & MyRecall solution**: 
- Don't retry on empty AX within same capture cycle
- Accept empty frame (valid result)
- Next trigger will fetch complete text
- Upstream (S3 equivalent) handles OCR fallback

---

## 7. VERIFICATION CHECKLIST FOR P1-S2B GATE

### Pre-Implementation
- [ ] Read screenpipe event_driven_capture.rs (640 lines) — understand trigger handling
- [ ] Read screenpipe paired_capture.rs — understand AX + content_hash together
- [ ] Review ADR-0013 (MyRecall event-driven-ax-split) for Python-specific choices

### Implementation
- [ ] Broadcast channel: 64 capacity, lag handling → immediate capture
- [ ] Debounce: min_capture_interval_ms (1000ms), idle_capture_interval_ms (30000ms)
- [ ] Content hash: SHA256, compute on AX text, store as hex string
- [ ] 30s floor: Idle/Manual triggers bypass dedup, force write
- [ ] Empty text: Skip dedup, preserve frame
- [ ] Permission: Non-blocking, return None on denial, continue with screenshot
- [ ] Browser URL: 3-tier fallback + Arc title cross-check
- [ ] Multi-monitor: Per-monitor loop assigns device_name independently

### Testing (Pre-Gate)
- [ ] 100+ captures across app switches, clicks, idle periods
- [ ] Multi-monitor test (if available): verify device_name binding correct
- [ ] Permission denied test: verify AX returns empty, screenshot still written
- [ ] Broadcast channel lag test: 100 events in 1s, no deadlock
- [ ] Arc browser test (if available): title mismatch → reject stale URL

### Gate Metrics
- [ ] Content hash coverage >= 90% (non-empty AX frames)
- [ ] AX walk duration P95 < 500ms
- [ ] Inter-write gap: max per device <= 45s
- [ ] Browser URL success >= 95% (Chrome/Safari/Edge only)
- [ ] Permission state transitions logged and observable

---

## 8. DESIGN-LEVEL RECOMMENDATIONS

### 8.1 Favor Pragmatism Over Atomicity
Screenpipe doesn't attempt single-instant screenshot+AX+metadata snapshot. Instead:
- Screenshot captured
- AX tree walked (may take 50–500ms)
- Metadata (app_name, window_name) determined at AX walk time (may be stale)
- Result: pragmatic, handles Electron/permissions naturally
- **MyRecall adoption**: Frozen in S2b spec (focused_context + device_binding as non-atomic handoff)

### 8.2 Broadcast Channel Prevents Cascade Failures
Using broadcast (not queue) means:
- Trigger source is **never blocked** by slow monitor loops
- If monitor slow, channel lags → detectable, recoverable (Lagged handling)
- **For MyRecall**: Don't use queue for triggers; broadcast allows independent monitor work

### 8.3 30-Second Floor is Non-Negotiable
The 30s forced-write floor is not performance tuning; it's **timeline fidelity**:
- Users should always see activity within 30s windows
- Dedup is content-aware (hash-based), not frequency-based
- **For MyRecall**: Enforce in S2b, verify in gate

### 8.4 Permission Handling is Graceful Degradation, Not Error
Screenpipe treats permission denial as a normal path (AX → empty → OCR fallback):
- No exceptions, no user-facing error dialogs in capture loop
- State machine handles recovery (watch TCC, poll, transition)
- **For MyRecall**: S2b just captures; S3 handles fallback decision

### 8.5 Async Tree Building (Electron) is Expected
Don't retry or block on first-capture empty AX:
- Electron DOM builds asynchronously
- Next user action triggers next capture → full tree available
- **For MyRecall**: Accept as valid behavior; OCR covers first-capture gaps

---

## 9. EXTERNAL SOURCES SUMMARY

| Source | Role | Key Finding | Evidence |
|--------|------|-------------|----------|
| **Screenpipe** | Production reference (Rust) | Broadcast pattern, 30s floor, non-blocking degradation | github.com/screenpipe/screenpipe (HEAD: 2026-03-07) |
| **Screenpipe Blog** (Feb 2026) | Design rationale | AX-first 100x less CPU than OCR; 100% accuracy vs fallback | screenpi.pe/blog/screenpipe-v2-03-accessibility-capture |
| **Screenpipe Perf Issue #2181** | Known challenge | SQLite contention 485–1088ms; semaphore + timeout solution | github.com/screenpipe/screenpipe/issues/2181 |
| **Screen2AX (MacPaw, 2025)** | Vision-based AX generation | Synthetic AX for unsupported apps; academic prototype | arXiv:2507.16704 |
| **Mokarchi (2025)** | Back-pressure patterns | Rate limiting, queue depth, graceful degradation | Medium article on EDA back-pressure |
| **Apple Vision Framework** | Native macOS OCR | 2025 updates: new document/smudge APIs | developer.apple.com + Vision docs |

---

## 10. CONCLUSION & ACTION ITEMS

### What P1-S2b Should Adopt From Screenpipe
1. **Broadcast channel** for trigger distribution (multi-monitor scalability)
2. **30-second forced-write floor** (timeline fidelity guarantee)
3. **Non-blocking permission handling** (graceful degradation pattern)
4. **Content-hash dedup** (exact match, empty-text excluded)
5. **Per-monitor device_name binding** (pragmatic, avoids global sync bottleneck)
6. **Arc stale URL detection** (title cross-check before returning URL)

### What MyRecall Intentionally Differs In
1. **Timeout**: 500ms (Python safety) vs 250ms (Rust perf) — documented, justified
2. **Hash**: SHA256 (cross-session consistency) vs u64 (in-memory only) — semantically equivalent
3. **Permission state machine**: Explicit (granted/denied/recovering) vs implicit (loop logic) — more observable
4. **Language**: Python (pyobjc) vs Rust (cidre) — platform-native trade-off

### Gate Verification Focus
- Broadcast lag handling (capture attempt on Lagged condition)
- Content hash coverage >= 90% on non-empty AX
- AX walk P95 < 500ms
- Inter-write gap max <= 45s per device
- Browser URL success >= 95% (3-tier + Arc stale detection)
- Permission state transitions logged and observable

---

**Generated by**: Librarian Agent  
**Quality**: Authoritative (direct source evidence + design pattern analysis)  
**Review Date**: 2026-03-12  
**Next Review**: After P1-S2b implementation code lands; before gate validation

