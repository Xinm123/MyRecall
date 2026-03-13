# Screenpipe Reference: Vision-Only Pipeline Patterns (2026-02-20)

## CONTEXT: Project Status
- **Language**: Rust (server) + TypeScript (UI), multi-crate workspace
- **Vision-Only Design**: Event-driven capture, accessibility-first OCR fallback, no audio pipeline for comparison
- **Storage**: SQLite (FTS5) + JPEG snapshots + legacy video chunks (H.265)
- **Current Phase**: Transitioning from continuous polling (0.5-1 FPS) to event-driven capture
- **Reference Docs**: VISION_PIPELINE_SPEC.md, EVENT_DRIVEN_CAPTURE_SPEC.md (both Feb 2026)

---

## 1. INGESTION CADENCE PATTERNS

### Event-Driven Model (P1 Target)
```
Event Triggers → Debounce → Capture → Storage
├── Immediate (app_switch, click): 300-500ms debounce
├── Activity-driven (typing_pause, scroll_stop): 400-500ms debounce
├── Clipboard copy: 200ms debounce
└── Idle fallback: Every 5s (or 10s max gap safety net)
```

**Key Decisions**:
- **Min interval**: 200ms per monitor (non-negotiable)
- **Max gap**: 10s without any capture trigger (safety net)
- **Trigger types**: app_switch, window_focus_change, click, typing_pause, scroll_stop, clipboard_copy, idle
- **Multi-monitor**: Event-specific capture (capture affected monitor only), others get idle fallback only
- **Sensitivity presets**: Low (500ms debounce, 10s idle), Medium (200ms, 5s idle), High (100ms, 3s idle)

### Polling Model (Legacy Baseline)
- Fixed FPS: 0.5-1 fps target, actual 0.15-0.4 fps due to OCR blocking
- Frame comparison: 320×180 downscale (6× reduction), hash + histogram comparison
- CPU cost: ~15% sustained (spiky due to OCR blocking)
- Issue: False-match hash collisions at 320×180, ~10% frame reach DB (most dropped)

**Migration Path**: Keep frame-comparison for dedup only, move capture trigger to events.

---

## 2. OCR/VISION PROCESSING STAGES

### Multi-Stage Pipeline (v2 Current)
```
capture_image (1ms)
  ↓
frame_comparer.compare() (1ms) → if diff < 0.02: skip
  ↓
capture_windows() (50-200ms, per-window CGWindowList)
  ↓
process_max_average_frame() (500-5000ms) ← BLOCKING OCR per window
  ↓
result_tx.send()
  ↓
sleep(interval)
```
**Problem**: OCR blocks entire capture loop; after burst of frames, frame-compare false-matches cause silent skips.

### Decoupled Pipeline (v2 Target - Phase 2+)
```
Capture Thread:
  capture_monitor_image() (1ms)
  frame_comparer.compare() (1ms)
  if changed OR event-triggered:
    capture_windows() (50ms)
    → push to ocr_queue (non-blocking)
    ↓
    Total: 2-50ms, never blocks

OCR Worker Pool (separate threads):
  per-window change detection:
    hash → cache check (WindowOcrCache, 5min TTL)
    cache hit → reuse (free)
    cache miss → perform_ocr_apple() (500-2000ms per window)
```

### Text Extraction Strategy (Event-Driven)
**Accessibility-First (Primary)**:
- OS accessibility tree walk (AX API on macOS, UI Automation on Windows)
- ~10-50ms latency on macOS
- **200ms hard timeout** (safety against huge DOM trees)
- Returns: text_content, window_title, URL, focused_element

**OCR Fallback (When accessibility empty)**:
- Apple Vision Framework (macOS native, no Tesseract dependency)
- Fallback triggers: image-heavy apps (Figma, Photoshop), PDF viewers, video players, broken AX
- ~500-2000ms per frame
- Rare with event-driven (most events fire on text-producing actions)

**No "both" mode**: Choose one per-capture, not both. Accessibility wins if available.

---

## 3. STORAGE SCHEMA & INDEXING

### Core Tables (v2 - migration-based evolution)
```sql
frames (primary)
├── id INTEGER PRIMARY KEY
├── timestamp DATETIME (capture time, NOT insertion time)
├── device_name TEXT (e.g., "monitor_0")
├── video_chunk_id FK (legacy: video file reference)
├── offset_index INTEGER (legacy: frame offset in video)
├── snapshot_path TEXT (NEW: direct JPEG path, v2 adoption)
├── accessibility_text TEXT (NEW: AX tree walk result)
├── capture_trigger TEXT (NEW: 'app_switch', 'click', 'typing_pause', 'scroll_stop', 'idle')
├── text_source TEXT ('ocr' or 'accessibility')
├── app_name TEXT
├── window_name TEXT
├── browser_url TEXT
├── focused INTEGER (boolean)
├── sync_id UUID (cloud sync, NULL → not synced)
├── machine_id TEXT (device fingerprint, NULL today)
├── synced_at DATETIME (NULL → not synced)

ocr_text (secondary, legacy compatibility)
├── id INTEGER PRIMARY KEY
├── frame_id FK
├── text TEXT (OCR result)
├── app_name, window_name, browser_url (denormalized from frame)
├── focused INTEGER

video_chunks (legacy, read-only for new data)
├── id INTEGER PRIMARY KEY
├── file_path TEXT (relative: "data/monitor_21_2026-02-13_02-24-24.mp4")
├── device_name TEXT
├── duration_seconds FLOAT
├── created_at DATETIME
├── file_size BYTES
└── (no new writes in v2+; read path only for old frames)
```

### Indexes (Performance)
```sql
-- Timeline queries (timestamp-first)
CREATE INDEX idx_frames_ts_device ON frames(timestamp DESC, device_name);

-- Search by source (accessibility_text is direct on frame, so no FK needed)
CREATE INDEX idx_frames_accessible_text ON frames(accessibility_text);

-- FTS5 indexes (already exist, keep for OCR legacy + new accessibility)
ocr_text_fts (virtual table, FTS5 MATCH queries)
accessibility_text_fts (NEW, FTS5 MATCH for accessibility_text column)

-- App filtering
CREATE INDEX idx_frames_app_name ON frames(app_name);
```

### Storage Layout (Filesystem)
```
~/.screenpipe/data/                         (configurable SCREENPIPE_DATA_DIR)
├── 2026-02-20/                           (date partition)
│   ├── 1708423935123_m0.jpg             (timestamp_monitorId.jpg, NEW event-driven)
│   ├── 1708423937456_m0.jpg
│   ├── 1708423939100_m1.jpg
│   └── ...
├── monitor_21_2026-02-13_02-24-24.mp4   (legacy H.265 chunks, read-only)
└── ...

Database:
├── edge.db (OR: screenpipe.db)           (frames + metadata, FTS indexes)
└── fts.db (optional, if split)           (search-only replica for concurrency)
```

**Migration Strategy**:
- Old frames: `snapshot_path = NULL`, use `video_chunk_id + offset_index` (FFmpeg extraction path)
- New frames: `snapshot_path` set, `video_chunk_id = NULL`, JPEG served directly (<5ms)
- Both coexist; timeline/search show both; no backfill pressure

---

## 4. RELIABILITY & BACKPRESSURE PATTERNS

### Frame Loss Prevention (Guarantees)
| Guarantee | Mechanism | Target |
|-----------|-----------|--------|
| **G1**: Every window transition captured | Event-driven on app_switch | <5s latency |
| **G2**: Active content changes captured | 1 frame per 5s min during activity | Reconstruct 10s window |
| **G3**: Static screens cost ~0 CPU | No frame comparison when idle >30s | <0.5% CPU idle |
| **G4**: OCR never blocks capture | Decoupled capture + OCR worker pool | Capture always <50ms |
| **G5**: First frame in DB within 5s | Skip similarity check on cold start | Cold start guarantee |
| **G6**: No silent drops | NULL video_offset backfill, log drops | 100% frame persistence |
| **G7**: Health reflects reality | frame_status: ok/stale/degraded | Tray icon synced with state |
| **G8**: Multi-monitor scales sublinearly | 3 monitors ≈ 1.5-2× CPU, not 3× | Active monitor priority |

### Backpressure & Queuing
```
Event Source → Debounce (async task)
  ├── IF qualified trigger:
  │   → Capture Worker (per-monitor)
  │       ├── capture_monitor_image() (1ms)
  │       ├── capture_windows() (50ms)
  │       ├── walk_focused_window() (10-200ms, with timeout)
  │       ├── OCR fallback (rare, 500-2000ms)
  │       ├── write JPEG (5-10ms)
  │       └── insert_frame() (5ms batched)
  └── IF NOT qualified (debounced):
      → drop (no queue buildup)
```

**No persistent queues**: Events either pass debounce (capture now) or drop. No queue overflow risk because:
- Min interval 200ms enforces max 5 captures/sec per monitor
- Worst case: 2 monitors, 10 captures/sec = 20 operations/sec (easy to handle)
- If capture lags (e.g., OCR fallback), debounce skips redundant events automatically

**DB Writer Backpressure**:
- Batched inserts (multiple frames per transaction)
- Video offset linking: Option A (recommended) = ensure video written before OCR queue processing
- Option B = allow NULL offset, backfill async (more complex, no immediate need)

---

## 5. OBSERVABILITY & HEALTH PATTERNS

### Health Endpoint Response
```json
{
  "frame_status": "ok" | "stale" | "degraded",
  "last_frame_timestamp": "2026-02-13T02:25:06Z",
  "last_capture_timestamp": "2026-02-13T02:31:00Z",
  "frames_in_ocr_queue": 3,
  "capture_fps_actual": 0.45,
  "capture_fps_target": 0.5,
  "ocr_queue_depth": 2,
  "frames_skipped_since_last_ocr": 15
}
```

**Status Rules**:
- `ok`: last_frame_timestamp ≤ 30s old
- `stale`: last_frame_timestamp > 30s old AND last_capture_timestamp < 5s (capturing but OCR stalled)
- `degraded`: last_frame_timestamp > 60s old OR capture_fps_actual < 50% of target

### Logging Strategy
```
DEBUG: Per-frame events (noisy), capture loop ticks, debounce decisions
INFO:  Lifecycle (server start, capture pause/resume), phase transitions
WARNING: Recoverable issues (frame drop retry, OCR cache miss, permission lost)
ERROR: Failures with degraded behavior (DB write fail, video encoder stall)
EXCEPTION: Caught exceptions with traceback (critical paths)
```

### Tray Icon & UI Indicators
- Green: frame_status = ok
- Yellow: stale or degraded
- Red: stopped
- Menu text: "● recording" (ok) or "● recording (12 segments pending)" (backlog)

### Metrics (PostHog / Telemetry)
```
pipeline_stall_duration (seconds)
frames_reaching_db_pct (actual vs captured)
capture_fps_actual vs target
cpu_usage_per_monitor
time_to_first_frame_cold_start (seconds)
ocr_queue_depth (max during session)
accessibility_fallback_rate (% of captures needing OCR)
```

---

## 6. PRIVACY BOUNDARIES & CONSENT PATTERNS

### Data Boundaries (Local-First by Default)
| Data | Storage | Transmission | User Control |
|------|---------|--------------|--------------|
| JPEG snapshots | ~/data/ (local disk) | None (default) | Pause/resume, file cleanup |
| Accessibility text | edge.db (local SQLite) | None (default) | Pause/resume, ignored windows list |
| OCR text | edge.db (local SQLite) | None (default) | Pause/resume |
| Metadata (app_name, URL) | edge.db (local SQLite) | Optional (cloud sync) | Opt-in sync, selective device |

### Privacy Controls
1. **Ignored Windows List** — apps/URLs never captured (Safari Incognito, password managers, banking)
2. **Pause/Resume** — stop all capture without restarting
3. **Selective Retention** — delete snapshots older than N days (configurable)
4. **Cloud Sync** (optional, P2) — end-to-end encrypted, zero-knowledge upload (off by default)

### Consent & Permissions (macOS)
```
First launch → Request:
  ✓ Screen Recording (TCC)
  ✓ Accessibility (TCC)
  ✓ Microphone (if audio enabled)
```

**No background tracking without explicit permission**. Permissions are OS-enforced (TCC) and persistent.

### Multi-Device Sync Strategy (Future, P2)
```
Local machine:
  capture → sync_id (UUID, set at frame insertion)
  send_to_cloud {
    frame_id: UUID,
    machine_id: "macbook-abc" (device fingerprint),
    timestamp: capture_time (not insertion time),
    text: accessibility_text or ocr_text,
    snapshot: [optional, full JPEG sync or text-only]
  }

Cloud merge:
  Same text from MacBook + Mac Mini → deduplicate by (machine_id, timestamp, text_similarity)
  OR show grouped by source machine
```

---

## 7. ARCHITECTURAL DECISION PATTERNS

### Key Tradeoffs Documented in Screenpipe

| Decision | Choice | Alternative Rejected | Rationale |
|----------|--------|----------------------|-----------|
| **Capture trigger** | Event-driven (app_switch, click) | Polling (fixed FPS) | Human-observable events align with user intent; eliminates empty-frame skipping |
| **Text source** | Accessibility first, OCR fallback | Both or OCR-only | 10x faster, 10x more accurate on supported apps; fallback for edge cases |
| **Video format** | JPEG snapshots (event-driven) | H.265 continuous (polling) | Event timing is irregular (not FPS-aligned); FFmpeg extraction = timeline bottleneck |
| **Frame dedup** | Hash comparison (legacy, kept for idle) | Similarity threshold only | False-match hash collisions at 320×180; larger resolution (640×360) + timeout = safety net |
| **OCR strategy** | Decoupled from capture (Phase 1-2) | Inline in capture loop | Blocking capture loop → 15% sustained CPU, frame drops; decoupled → 5% steady |
| **Multi-monitor** | Per-trigger + idle fallback | Simultaneous all monitors | Event-specific capture saves 3× CPU on 3-monitor setups; all-at-once for completeness (rejected) |
| **DB schema** | Additive (snapshot_path, accessibility_text) | Replace old columns | Backward compat with video-chunk frames; dual-path read (legacy + new) with no migration |
| **Cloud sync** | Optional, encrypt end-to-end (P2) | Built-in from start | Focus on local reliability first; sync is nice-to-have, not core value |

---

## 8. IMPLEMENTATION CHECKLIST FOR P1-S2a (VISION-ONLY)

### Must-Have (P1 Scope)
- [ ] Event-driven capture loop (app_switch, click, typing_pause, scroll_stop, idle)
- [ ] Accessibility-tree walk + OCR fallback (no dual-capture)
- [ ] JPEG snapshot storage (direct write, no FFmpeg encoding on hot path)
- [ ] DB migration: snapshot_path, accessibility_text, capture_trigger, text_source columns
- [ ] Debounce logic (200ms min interval, 10s max gap safety net)
- [ ] Health endpoint: frame_status (ok/stale/degraded), queue depth, actual vs target FPS
- [ ] Frame-reach guarantee: >95% captured frames reach DB (no silent drops)
- [ ] Ignore windows list (privacy controls)
- [ ] Cold-start guarantee: first frame in DB <5s

### Nice-To-Have (P1 Polish)
- [ ] Tray icon status colors (green/yellow/red)
- [ ] Capture sensitivity presets (Low/Medium/High)
- [ ] Multi-monitor frame-comparison tuning (downscale 6→3)
- [ ] OCR queue metrics (pending, max depth)

### Post-P1 (P2+ Scope)
- [ ] Cloud sync (optional, end-to-end encrypted)
- [ ] GPU batching for OCR (process multiple windows per model load)
- [ ] Disk cleanup (retention policy)
- [ ] E2E robot testing (osascript-driven capture verification)
- [ ] Parallel multi-monitor OCR worker pool (shared across monitors)

---

## 9. COMPARISON CRITERIA FOR MyRecall P1-S2a REVIEW

Use these questions to sanity-check your design docs:

1. **Ingestion Cadence**: Do you have explicit debounce times + min interval + max gap safety net?
2. **OCR/Vision**: Is accessibility extraction documented separately from OCR fallback?
3. **Storage**: Do you have migration strategy for dual-path reads (old + new) without rewriting history?
4. **Reliability**: Are the 8 guarantees (G1-G8) explicitly stated and testable?
5. **Observability**: Does health endpoint distinguish between "capturing but OCR stalled" vs "not capturing"?
6. **Privacy**: Is local-first the default? Are ignored windows + pause/resume documented?
7. **Multi-Monitor**: How does CPU scale with N monitors? Is active-monitor priority documented?
8. **Cold Start**: Is there a fast path to get first frame in DB within 5s?
9. **Frame Loss**: Can frames reach DB without video_chunk (NULL offset with backfill)?
10. **Backward Compat**: Can old video-chunk frames still be served after migration?

