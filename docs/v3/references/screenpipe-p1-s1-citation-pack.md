# MyRecall v3 P1-S1 Screenpipe Reference Citation Pack

**Compiled**: 2026-03-06  
**MyRecall Change**: p1-s1-ingest-baseline  
**Screenpipe Reference**: `_ref/screenpipe` (HEAD: e61501da)  
**Date Awareness**: Current year is 2026; Screenpipe commit reflects current upstream baseline.

---

## 1. HEALTH ENDPOINT SCHEMA

### 1.1 Screenpipe HealthCheckResponse Structure

**Evidence** ([screenpipe/health.rs:35-53](https://github.com/screenpipe/screenpipe/blob/e61501da/crates/screenpipe-server/src/routes/health.rs#L35-L53)):

```rust
#[derive(Serialize, OaSchema, Deserialize)]
pub struct HealthCheckResponse {
    pub status: String,                    // "healthy", "degraded", "error"
    pub status_code: u16,                  // HTTP status (200, 503, 500)
    pub last_frame_timestamp: Option<chrono::DateTime<Utc>>,
    pub last_audio_timestamp: Option<chrono::DateTime<Utc>>,
    pub frame_status: String,              // "ok", "stale", "disabled", "not_started"
    pub audio_status: String,
    pub message: String,
    pub verbose_instructions: Option<String>,
    pub device_status_details: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub monitors: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pipeline: Option<PipelineHealthInfo>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub audio_pipeline: Option<AudioPipelineHealthInfo>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub accessibility: Option<TreeWalkerSnapshot>,
}
```

### 1.2 Screenpipe PipelineHealthInfo (Vision Metrics)

**Evidence** ([screenpipe/health.rs:56-70](https://github.com/screenpipe/screenpipe/blob/e61501da/crates/screenpipe-server/src/routes/health.rs#L56-L70)):

```rust
#[derive(Serialize, OaSchema, Deserialize)]
pub struct PipelineHealthInfo {
    pub uptime_secs: f64,
    pub frames_captured: u64,
    pub frames_db_written: u64,
    pub frames_dropped: u64,
    pub frame_drop_rate: f64,
    pub capture_fps_actual: f64,
    pub avg_ocr_latency_ms: f64,
    pub avg_db_latency_ms: f64,
    pub ocr_queue_depth: u64,
    pub video_queue_depth: u64,
    pub time_to_first_frame_ms: Option<f64>,
    pub pipeline_stall_count: u64,
    pub ocr_cache_hit_rate: f64,
}
```

### 1.3 Screenpipe Health Status Logic (Stale Detection Threshold)

**Evidence** ([screenpipe/health.rs:175-190](https://github.com/screenpipe/screenpipe/blob/e61501da/crates/screenpipe-server/src/routes/health.rs#L175-L190)):

```rust
let now = Utc::now();
// 60 seconds — tight enough to detect real stalls, loose enough to
// tolerate adaptive FPS (0.1-0.5 fps) and brief DB contention spikes.
let threshold_secs = 60u64;

let frame_status = if state.vision_disabled {
    "disabled"
} else if crate::sleep_monitor::screen_is_locked() {
    "ok" // screen locked — no captures expected, not a real stall
} else if last_frame_ts == 0 {
    "not_started"
} else if now.timestamp() as u64 - last_frame_ts < threshold_secs {
    "ok"
} else {
    "stale"
};
```

**Key Insight**: Screenpipe uses **60-second threshold** (not 5 minutes) for stale detection. Uses `last_frame_ts` (max of DB write or capture attempt).

### 1.4 MyRecall v3 P1-S1 Divergence: Health Response Subset

**Evidence** (MyRecall: [spec.md §4.9](../spec.md)):

```json
{
  "status": "ok",
  "last_frame_timestamp": "2026-02-26T10:00:00Z",
  "frame_status": "ok",
  "message": "",
  "queue": {
    "pending": 0,
    "processing": 0,
    "failed": 0
  }
}
```

**MyRecall P1-S1 Constraints**:
- ❌ No `audio_status`, `audio_pipeline`, `device_status_details` (vision-only)
- ❌ No `monitors`, `pipeline`, `accessibility` (P1-S1 noop mode)
- ✅ Adds `queue` sub-object with ingest queue counts (Screenpipe has no queue field)
- ✅ `status`: `"ok"` / `"degraded"` / `"error"` (Screenpipe uses "healthy")
- ⚠️ `frame_status`: still `"ok"` / `"stale"`, but stale threshold TBD (proposal: 5 min for UI, 60s for logs)

---

## 2. FRAME SERVING BEHAVIOR

### 2.1 Screenpipe Frame Serving: Content-Type Header

**Evidence** ([screenpipe/frames.rs:955-979](https://github.com/screenpipe/screenpipe/blob/e61501da/crates/screenpipe-server/src/routes/frames.rs#L955-L979)):

```rust
pub(crate) async fn serve_file(path: &str) -> Result<Response, (StatusCode, JsonResponse<Value>)> {
    match File::open(path).await {
        Ok(file) => {
            let stream = ReaderStream::new(file);
            let body = Body::from_stream(stream);

            let response = Response::builder()
                .header("content-type", "image/jpeg")                    // ← FIXED: JPEG
                .header("cache-control", "public, max-age=604800")      // 7-day cache
                .body(body)
                .map_err(|e| {
                    (
                        StatusCode::INTERNAL_SERVER_ERROR,
                        JsonResponse(json!({"error": format!("Failed to create response: {}", e)})),
                    )
                })?;

            Ok(response)
        }
        Err(e) => Err((
            StatusCode::INTERNAL_SERVER_ERROR,
            JsonResponse(json!({"error": format!("Failed to open file: {}", e)})),
        )),
    }
}
```

**Key Pattern**: Always `content-type: image/jpeg`, regardless of disk file type.

### 2.2 Screenpipe PII-Redacted Frame Response

**Evidence** ([screenpipe/frames.rs:935-939](https://github.com/screenpipe/screenpipe/blob/e61501da/crates/screenpipe-server/src/routes/frames.rs#L935-L939)):

```rust
let body = Body::from(redacted_data);
Response::builder()
    .header("content-type", "image/jpeg")          // ← FIXED: JPEG even when redacted
    .header("cache-control", "no-cache")           // Don't cache redacted
    .header("x-pii-redacted", "true")              // Signal redaction
    .header("x-pii-regions-count", pii_regions.len().to_string())
    .body(body)
```

**Pattern**: Redacted frames still `image/jpeg`, with extra headers for metadata.

### 2.3 Screenpipe Snapshot vs Video-Chunk Frame Handling

**Evidence** ([screenpipe/frames.rs:82-102](https://github.com/screenpipe/screenpipe/blob/e61501da/crates/screenpipe-server/src/routes/frames.rs#L82-L102)):

```rust
match state.db.get_frame(frame_id).await {
    Ok(Some((file_path, offset_index, is_snapshot))) => {
        if is_snapshot {
            // Snapshot frame — serve JPEG directly (no ffmpeg needed)
            if query.redact_pii {
                return apply_pii_redaction(&state, frame_id, &file_path).await;
            }
            // Cache snapshot path too
            if let Some(cache) = &state.frame_image_cache {
                if let Ok(mut cache) = cache.try_lock() {
                    cache.put(frame_id, (file_path.clone(), Instant::now()));
                }
            }
            debug!(
                "Snapshot frame {} served in {:?}",
                frame_id,
                start_time.elapsed()
            );
            return serve_file(&file_path).await;    // ← Direct serve
        }

        // Legacy video-chunk frame — extract via ffmpeg
        match try_extract_and_serve_frame(...).await { ... }
    }
}
```

**Key Insight**: Screenpipe has dual paths—modern "snapshot" (direct JPEG serve) and legacy "video-chunk" (ffmpeg extract). P1-S1 aligns with snapshot approach.

### 2.4 MyRecall v3 Alignment: Frame Serving Contract

**Evidence** (MyRecall: [spec.md §4.9](../spec.md), [p1-s1.md §1.1](../acceptance/phase1/p1-s1.md)):

```
GET /v1/frames/:frame_id

Response 200 OK:
Content-Type: image/jpeg
[raw JPEG binary]
```

**MyRecall P1-S1 Constraints**:
- ✅ Always `Content-Type: image/jpeg` (matches Screenpipe)
- ✅ Fixed to snapshot JPEG serve (no ffmpeg complexity)
- ✅ `frames.snapshot_path` stores JPEG file path (`.jpg`/`.jpeg`)
- ⚠️ Cache strategy TBD (Screenpipe uses 7 days for unredacted, no-cache for redacted)

---

## 3. QUEUE STATUS ENDPOINT

### 3.1 MyRecall v3 P1-S1 Queue Status Schema

**Evidence** (MyRecall: [spec.md §4.7](../spec.md), [p1-s1.md §1.1](../acceptance/phase1/p1-s1.md)):

```json
{
  "pending": 10,
  "processing": 2,
  "completed": 50,
  "failed": 0,
  "processing_mode": "noop",
  "capacity": 1000,
  "oldest_pending_ingested_at": "2026-02-26T10:00:00Z"
}
```

**P1-S1 Invariants**:
- Four counts (`pending/processing/completed/failed`) MUST match DB `frames.status` row counts in real-time
- `processing_mode` fixed to `"noop"` in P1-S1 (no AI initialized)
- When `pending=0`, `oldest_pending_ingested_at` MUST be `null` (not empty string/0/current time)
- **Screenpipe Note**: Screenpipe has no queue endpoint; this is MyRecall-specific

---

## 4. INGEST PAYLOAD & IDEMPOTENCY

### 4.1 MyRecall Ingest Payload Structure

**Evidence** (MyRecall: [data-model.md §3.0.6](../data-model.md)):

```json
{
  "capture_id": "uuid-v7-string",
  "metadata": {
    "timestamp": "2026-02-26T10:00:00Z",
    "app_name": "Chrome",
    "window_title": "...",
    "monitor_id": 0,
    "trigger": "click|keypress|idle",
    "content_hash": "sha256-hex"
  },
  "image": "base64-jpeg-or-binary"
}
```

### 4.2 Idempotency via Capture_ID UNIQUE Constraint

**Evidence** (MyRecall: [spec.md §4.7 Ingest Semantics](../spec.md), [design.md §Decision 3](../../openspec/changes/p1-s1-ingest-baseline/design.md#97)):

- `frames.capture_id` has UNIQUE constraint (DB level)
- Duplicate `capture_id` → `INSERT OR IGNORE` → HTTP 200 + `{"status": "already_exists"}`
- New `capture_id` → INSERT → HTTP 201 + `{"status": "queued"}`
- **Screenpipe Note**: Screenpipe uses different dedup (content_hash + per-device, event-driven), but MyRecall aligns on `capture_id` for P1-S1 simplicity

---

## 5. PROCESSING_MODE SEMANTICS (P1-S1 NOOP)

### 5.1 MyRecall P1-S1 No-Op Processing Constraint

**Evidence** (MyRecall: [spec.md §4.7 P1-S1 Processing Semantics](../spec.md), [design.md Goals](../../openspec/changes/p1-s1-ingest-baseline/design.md#47)):

**Edge MUST NOT** (P1-S1):
- Initialize OCR provider (RapidOCR, Tesseract, etc.)
- Initialize Vision LLM (Qwen-VL, LLaVA, etc.)
- Initialize embedding model (BGE, e5, etc.)
- Write AI-derived fields (`accessibility_text`, `ocr_text`, `keywords`, `caption`, etc.)
- Output preload logs for models

**Edge MUST** (P1-S1):
- Create `frames` rows with snapshot JPEG path
- Move frames from `pending` → `completed` (no `processing` state exposed in metrics)
- Output exactly once: `MRV3 processing_mode=noop` (after HTTP server ready)
- Output on failure: `MRV3 frame_failed reason=<DB_WRITE_FAILED|IO_ERROR|STATE_MACHINE_ERROR> ...`

**Screenpipe Context**: Screenpipe's health check distinguishes pipeline states (`uptime_secs`, `frames_captured`, `frames_db_written`), but has no `processing_mode` field. P1-S1 borrows the concept from operational requirements, not Screenpipe.

---

## 6. DIVERGENCE MATRIX: Screenpipe vs MyRecall v3 P1-S1

### 6.1 Where MyRecall Intentionally Diverges

| Aspect | Screenpipe | MyRecall v3 P1-S1 | Reason |
|--------|-----------|-------------------|--------|
| **Health Endpoint** | Comprehensive (vision+audio+accessibility) | Subset (vision-only) + queue counts | Vision-first product; queue for observability |
| **Queue Status** | No dedicated endpoint | `/v1/ingest/queue/status` present | Host needs to poll for retry/backpressure decisions |
| **Idempotency Key** | `content_hash` + device + timestamp window | `capture_id` (UUID v7, explicit) | Edge-Centric; Host controls identity |
| **Frame Dedup Logic** | Event-driven (accessibility tree hash + 30s floor) | Explicit UNIQUE(capture_id) | P1-S1 single-machine; async event model not yet ready |
| **Processing Mode Field** | No field (state implicit in metrics) | Explicit `processing_mode` field | P1-S1 Gate verification (must log "noop" exactly) |
| **Error Response Format** | `{"error": "msg"}` only | `{"error": "...", "code": "...", "request_id": "..."}` | Structured tracing + client differentiation |
| **Frame Serving Path** | Dual (snapshot + video-chunk with ffmpeg) | Snapshot only (no ffmpeg in P1) | Simplification for local JPEG baseline |

### 6.2 Where MyRecall Should Align Strictly

| Aspect | Screenpipe Pattern | MyRecall P1-S1 Alignment | Verification Point |
|--------|-------------------|-------------------------|-------------------|
| **Snapshot JPEG Serving** | Direct file serve with fixed `Content-Type: image/jpeg` | Match exactly | `GET /v1/frames/:frame_id` response header |
| **Stale Detection Logic** | Threshold-based (60s default) | Adopt for health status (may differ for UI display) | Health response `frame_status: "stale"` when ts > threshold |
| **Cache Headers** | `public, max-age=604800` for unredacted; `no-cache` for redacted | Adopt or document exception | Response headers on frame GET |
| **Status Naming** | `"healthy"` / `"degraded"` / Error status code | Use `"ok"` / `"degraded"` / `"error"` with HTTP codes | Health endpoint JSON + HTTP status consistency |

---

## 7. MANDATORY GATE VERIFICATION ANCHORS (P1-S1)

### 7.1 Screenpipe-Inspired Verification Points

1. **Health Endpoint Presence & Staleness** ([screenpipe/health.rs:175-190](https://github.com/screenpipe/screenpipe/blob/e61501da/crates/screenpipe-server/src/routes/health.rs#L175-L190))
   - Gate: `GET /v1/health` must distinguish `frame_status: "ok"` vs `"stale"` based on threshold
   - Accept threshold value from MyRecall spec (may differ from Screenpipe's 60s)

2. **Frame Content-Type Immutability** ([screenpipe/frames.rs:962](https://github.com/screenpipe/screenpipe/blob/e61501da/crates/screenpipe-server/src/routes/frames.rs#L962))
   - Gate: `GET /v1/frames/:frame_id` MUST return `Content-Type: image/jpeg` always
   - Verification: Response header inspection + sample binary validation (JPEG magic bytes)

3. **Idempotency via Capture_ID** (Screenpipe alignment on concept, MyRecall implementation)
   - Gate: Duplicate `capture_id` → HTTP 200 (not 201)
   - Verification: POST same payload twice, check status code + DB row count (UNIQUE constraint enforced)

4. **Processing Mode Logging** (MyRecall-specific requirement, no Screenpipe equivalent)
   - Gate: Exactly one log line `MRV3 processing_mode=noop` after server ready
   - Verification: Grep server startup logs for exact match

---

## 8. CITE & REFERENCE STRATEGY

### For Code Claims
```markdown
**Evidence** ([repo/file.rs:LINE-LINE](https://github.com/screenpipe/screenpipe/blob/e61501da/crates/screenpipe-server/src/routes/health.rs#L35-L53)):

[code snippet or description]
```

### For Specification Claims
```markdown
**Evidence** (MyRecall: [spec.md §X.Y](path), [p1-s1.md §A.B](path)):

[quote or bullet point]
```

### For Architectural Notes
```markdown
**Screenpipe Pattern** (screenpipe/frames.rs:955-979):
Snapshot frames are served directly as JPEG, bypassing ffmpeg for performance.

**MyRecall P1-S1 Alignment**:
Adopt snapshot-only approach; no video-chunk path in P1.
```

---

## 9. OUTSTANDING QUESTIONS FOR IMPLEMENTATION

1. **Stale Threshold for `frame_status`**: 
   - Screenpipe uses 60s; MyRecall spec says 5 min. Reconcile or document exception.

2. **Health Status Codes**:
   - Screenpipe returns HTTP 200 even when `status: "degraded"`. MyRecall should clarify (200 for degraded? 503 for error?).

3. **Queue Depth Capacity Field**:
   - Screenpipe has no queue endpoint. MyRecall `capacity` field—define semantics (buffer size? max pending count?).

4. **PII Redaction**:
   - Screenpipe supports `?redact_pii=true`. Defer to P2+; P1-S1 always returns unredacted.

5. **Accessibility Tree Export**:
   - Screenpipe includes optional `accessibility` in health response. MyRecall P1-S1 skips; P1-S3+ to add if needed.
