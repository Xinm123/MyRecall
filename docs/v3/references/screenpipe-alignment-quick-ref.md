# MyRecall v3 P1-S1 ↔ Screenpipe: Alignment Quick Reference

**Last Updated**: 2026-03-06  
**Screenpipe Ref**: e61501da (HEAD)  
**MyRecall Spec**: spec.md + data-model.md + p1-s1.md

---

## 📋 Quick Index

| Topic | Screenpipe Source | MyRecall Spec | Status |
|-------|-------------------|---------------|--------|
| **Health Response Schema** | health.rs:35-53 | spec.md §4.9 | ✅ ALIGNED (subset) |
| **Frame Content-Type** | frames.rs:962 | spec.md §4.9 | ✅ STRICT ALIGNMENT |
| **Snapshot Serving** | frames.rs:82-102 | design.md | ✅ ALIGNED |
| **Stale Detection** | health.rs:175-190 | spec.md §4.7 | ⚠️ THRESHOLD DIFFERS |
| **Idempotency Key** | db.rs | spec.md §4.7 | ⚠️ INTENTIONAL DIVERGENCE |
| **Queue Endpoint** | ❌ None | spec.md §4.7 | ✅ MyRecall-specific |

---

## 🎯 Must-Do Alignments (P1-S1)

### 1️⃣ Frame Serving: Always JPEG

```rust
// Screenpipe: frames.rs:962
.header("content-type", "image/jpeg")

// MyRecall: Implement same
GET /v1/frames/:frame_id → Content-Type: image/jpeg
```

**Verification**: Response header inspection + JPEG magic bytes check.

---

### 2️⃣ Health Endpoint: Presence + Threshold

```rust
// Screenpipe: health.rs:175-190
let threshold_secs = 60u64;
let frame_status = if now.timestamp() as u64 - last_frame_ts < threshold_secs {
    "ok"
} else {
    "stale"
};

// MyRecall: Adopt logic
GET /v1/health → frame_status: "ok" | "stale"
```

**MyRecall Note**: Spec says 5 min; implementation should clarify or justify 60s vs 5m.

---

### 3️⃣ Snapshot Frames: Direct Serve (No FFmpeg)

```rust
// Screenpipe: frames.rs:82-102 (is_snapshot path)
if is_snapshot {
    return serve_file(&file_path).await;  // Direct JPEG serve
}

// MyRecall: P1-S1 only supports snapshot approach
POST /v1/ingest → frames.snapshot_path (JPEG file)
GET /v1/frames/:frame_id → Stream from snapshot_path
```

**MyRecall Note**: No video-chunk path in P1.

---

## ⚠️ Intentional Divergences (P1-S1)

### Why Different?

| Feature | Screenpipe | MyRecall | Reason |
|---------|-----------|---------|--------|
| **Dedup Key** | content_hash + timestamp | capture_id (UNIQUE) | Host-driven identity; simpler for single-machine |
| **Queue Endpoint** | No `/queue/status` | Yes, `/v1/ingest/queue/status` | Host needs to poll for backpressure |
| **Processing Mode** | Implicit in metrics | Explicit field + log | Gate verification requirement |
| **Error Format** | `{"error": "msg"}` | `{error, code, request_id}` | Structured logging + tracing |

**None of these divergences break Screenpipe alignment**—they're *additive* or *local simplifications*.

---

## 🚨 Outstanding Questions

| Issue | Screenpipe Value | MyRecall Spec | Action |
|-------|------------------|---------------|--------|
| Stale threshold | 60s | 5 min (unclear) | ✏️ Clarify in impl |
| Health HTTP code for "degraded" | 200 | Unclear | ✏️ Clarify in impl |
| PII redaction | Optional (`?redact_pii=true`) | Defer P2+ | ✅ Skip P1 |

---

## 📚 Key Evidence Paths

### Screenpipe (e61501da)

- **Health endpoint**: `crates/screenpipe-server/src/routes/health.rs:35-105`
  - `HealthCheckResponse` struct (line 35-53)
  - `health_check()` function (line 107+)
  - Stale logic (line 175-190)

- **Frame serving**: `crates/screenpipe-server/src/routes/frames.rs:955-979`
  - `serve_file()` function with JPEG hardcoding
  - Snapshot detection (line 82-102)
  - PII redaction (line 935-939)

### MyRecall (v3)

- **Health spec**: `docs/v3/spec.md` §4.9 (line 753+)
- **Ingest spec**: `docs/v3/spec.md` §4.7 (line 437+)
- **P1-S1 acceptance**: `docs/v3/acceptance/phase1/p1-s1.md` §1.1 (HTTP contract delta)
- **Design decisions**: `openspec/changes/p1-s1-ingest-baseline/design.md` §Decisions

---

## ✅ Verification Checklist

- [ ] `GET /v1/health` returns JSON with `frame_status` ∈ {ok, stale}
- [ ] `GET /v1/frames/:id` → `Content-Type: image/jpeg` header (not text/html, not image/webp)
- [ ] `POST /v1/ingest` (duplicate `capture_id`) → HTTP 200, not 201
- [ ] `frames.snapshot_path` points to JPEG file on disk (`.jpg` or `.jpeg`)
- [ ] Server log contains exactly once: `MRV3 processing_mode=noop`
- [ ] No OCR/embedding/vision provider loaded during startup
- [ ] `GET /v1/ingest/queue/status` counters match DB row counts in real-time

