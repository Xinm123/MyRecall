# Screenpipe Reference Pack for MyRecall v3 P1-S1

This directory contains authoritative references and alignment documentation for MyRecall v3 Phase 1, Step 1 (P1-S1) with respect to Screenpipe upstream.

## 📄 Documents

### 1. **screenpipe-p1-s1-citation-pack.md** (Full Reference Pack)
   - **Audience**: Implementation teams, code reviewers, specification authors
   - **Length**: ~391 lines
   - **Contents**:
     - Screenpipe `HealthCheckResponse` structure (health.rs:35-53)
     - Frame serving content-type handling (frames.rs:955-979)
     - Snapshot vs video-chunk detection logic (frames.rs:82-102)
     - MyRecall health endpoint subset specification
     - Queue status endpoint (MyRecall-specific)
     - Ingest idempotency semantics
     - P1-S1 noop processing mode constraints
     - Divergence matrix (where/why MyRecall differs)
     - Alignment checklist (where MyRecall must match strictly)
     - Mandatory gate verification anchors
     - Citation strategy for future references
     - Outstanding questions for implementation

### 2. **screenpipe-alignment-quick-ref.md** (One-Page Cheat Sheet)
   - **Audience**: Developers, QA, quick reference
   - **Length**: ~131 lines
   - **Contents**:
     - Quick index table (topic → source → status)
     - Must-do alignments (3 critical items)
     - Intentional divergences (with rationale)
     - Outstanding questions with action items
     - Key evidence paths for both projects
     - Verification checklist (ready for Gate testing)

---

## 🎯 Key Findings

### Strict Alignments (MyRecall MUST match Screenpipe)

1. **Frame Content-Type Header**
   - Screenpipe: `content-type: image/jpeg` (fixed, always)
   - MyRecall: `GET /v1/frames/:frame_id` MUST return same
   - Evidence: screenpipe/frames.rs:962

2. **Snapshot Frame Serving**
   - Screenpipe: Direct JPEG file serve (no ffmpeg for snapshots)
   - MyRecall: Adopt snapshot-only approach (no video-chunk path in P1)
   - Evidence: screenpipe/frames.rs:82-102

3. **Health Endpoint Staleness Detection**
   - Screenpipe: Threshold-based logic (60s default)
   - MyRecall: Adopt threshold approach (recommend reconcile 60s vs 5min spec)
   - Evidence: screenpipe/health.rs:175-190

### Intentional Divergences (MyRecall design choice)

1. **Idempotency Key**
   - Screenpipe: `content_hash + device + timestamp window` (event-driven)
   - MyRecall: `capture_id` (UNIQUE constraint, explicit)
   - Reason: Single-machine P1; Host-driven identity for simplicity

2. **Queue Status Endpoint**
   - Screenpipe: No dedicated `/queue/status` endpoint
   - MyRecall: Yes, `/v1/ingest/queue/status` (for Host polling/backpressure)
   - Reason: Edge-Centric architecture; Host needs observability

3. **Processing Mode Field**
   - Screenpipe: Implicit in pipeline metrics
   - MyRecall: Explicit `processing_mode` field + log anchor `MRV3 processing_mode=noop`
   - Reason: P1-S1 Gate verification requirement

4. **Error Response Format**
   - Screenpipe: `{"error": "message"}` only
   - MyRecall: `{"error": "...", "code": "...", "request_id": "..."}`
   - Reason: Structured logging + client differentiation

---

## 🚨 Outstanding Implementation Questions

1. **Stale Threshold Conflict**
   - Screenpipe uses: 60 seconds
   - MyRecall spec mentions: 5 minutes
   - **Action**: Clarify in implementation; recommend 60s for consistency

2. **Health HTTP Status Code**
   - Screenpipe returns: HTTP 200 even when `status: "degraded"`
   - MyRecall should clarify: 200 for degraded? 503 for error?
   - **Action**: Document in spec.md before implementation

3. **Queue Capacity Field**
   - MyRecall adds `capacity` field (not in Screenpipe)
   - **Action**: Define semantics (max pending items? buffer size?)

4. **PII Redaction**
   - Screenpipe supports: `?redact_pii=true` parameter
   - MyRecall P1-S1: Defer to P2+; always return unredacted
   - **Action**: Document non-support in P1-S1 responses

5. **Accessibility Tree**
   - Screenpipe: Optional `accessibility` field in health response
   - MyRecall P1-S1: Skip (vision-only, no AX)
   - **Action**: Clarify P1-S3+ timeline for AX support

---

## 🔗 Evidence Paths

### Screenpipe (Reference: `_ref/screenpipe`, HEAD: e61501da)

**Health Endpoint**:
```
crates/screenpipe-server/src/routes/health.rs
  - Lines 35-53: HealthCheckResponse struct
  - Lines 56-70: PipelineHealthInfo struct
  - Lines 175-190: Stale detection threshold logic
  - Lines 369-470: Health response generation
```

**Frame Serving**:
```
crates/screenpipe-server/src/routes/frames.rs
  - Lines 82-102: Snapshot vs video-chunk detection
  - Lines 936, 962: Content-Type: image/jpeg hardcoding
  - Lines 955-979: serve_file() function with cache headers
```

### MyRecall (Repository: `/Users/pyw/old/MyRecall`)

**Specifications**:
```
../spec.md
  - §4.7: Ingest, queue status, processing semantics
  - §4.8.1: UI health component requirements
  - §4.9: Health endpoint, frames endpoint, error responses

../data-model.md
  - §3.0.3: frames table DDL (capture_id UNIQUE)
  - §3.0.6: CapturePayload schema
  - §3.0.7: Migration strategy

docs/v3/acceptance/phase1/p1-s1.md
  - §1.1: HTTP contract delta (POST /v1/ingest, GET /v1/frames/:id, GET /v1/health)
  - §3: Acceptance steps with verification anchors

openspec/changes/p1-s1-ingest-baseline/
  - proposal.md: Why/What changes
  - design.md: Architectural decisions & trade-offs
```

---

## ✅ How to Use These References

### For Specification Authors
- Read **screenpipe-p1-s1-citation-pack.md** §6 (Divergence Matrix) to understand intentional design decisions
- Use §7 (Gate Verification Anchors) to ground acceptance criteria in evidence

### For Implementation Teams
- Start with **screenpipe-alignment-quick-ref.md** for quick context
- Drill down to screenpipe/frames.rs:962 for content-type implementation
- Follow **Verification Checklist** during code review

### For QA/Gate Testing
- Use **screenpipe-alignment-quick-ref.md** §Verification Checklist
- Cross-reference each item with full citation pack for evidence
- Inspect `GET /v1/health` response against screenpipe/health.rs:35-53 structure

### For Future Phases (P1-S2+)
- Review §9 (Outstanding Questions) to identify P2+ carry-forward items
- Reference Divergence Matrix when reconciling AX-first/OCR-fallback with Screenpipe patterns

---

## 📝 Maintenance Notes

- **Screenpipe Reference Commit**: e61501da (fix: DB pool starvation + past-day timeline navigation)
- **Date Compiled**: 2026-03-06
- **MyRecall Change**: p1-s1-ingest-baseline
- **Next Review**: After P1-S1 implementation complete; before P1-S2 planning

**Updates Required If**:
- Screenpipe commits significant changes to health.rs or frames.rs
- MyRecall spec deviates from documented findings
- New P1-S2+ requirements affect alignment strategy

---

## 📚 Related Documents

- [MyRecall v3 Spec](../spec.md)
- [MyRecall v3 Data Model](../data-model.md)
- [P1-S1 Acceptance Record](../acceptance/phase1/p1-s1.md)
- [P1-S1 Design Document](../../openspec/changes/p1-s1-ingest-baseline/design.md)
- [Screenpipe Repository](/_ref/screenpipe)

---

**Generated by**: OpenCode / LibrarianAgent  
**Quality**: Authoritative (direct evidence from code + spec)  
**Confidence Level**: High (verified permalinks + exact line ranges)
