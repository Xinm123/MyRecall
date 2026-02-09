# MyRecall-v3 Phase Gates & Acceptance Criteria

**Version**: 1.6
**Last Updated**: 2026-02-09

⚠️ **Authority Notice**: 此文件为所有Phase (0-7) 的权威Go/No-Go验收标准。Roadmap文档仅引用此处定义,不重复定义Phase gates。任何关于Phase验收标准的变更必须首先更新本文件。

---

## Purpose

This document defines quantifiable acceptance criteria for each phase. A phase should proceed only after Go/No-Go criteria are satisfied, or after an explicit documented deferral decision (e.g., LONGRUN observation plan with traceable follow-up) is approved and recorded.

---

## Data Governance Gates (Cross-Phase)

This section defines data governance acceptance criteria that must be validated across multiple phases.

### Governance Principles

| Principle | Requirement | Validation Phase(s) |
|-----------|-------------|---------------------|
| **PII Handling** | Detect and classify PII data | Phase 0, Phase 5 |
| **Encryption at Rest** | All sensitive data encrypted | Phase 1, Phase 2 |
| **Encryption in Transit** | HTTPS + TLS 1.3 | Phase 5 |
| **Retention Policy** | Auto-delete >30 days | Phase 1, Phase 2, Phase 5 |
| **Deletion API** | Secure manual deletion | Phase 5 |
| **Authentication** | API key or JWT | Phase 0, Phase 5 |

### Phase 0: Data Governance Design

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **PII Classification Policy** | Document defines PII categories (screen text, audio, faces) | Review policy document | ✅ |
| **Encryption Schema Design** | Database schema supports encryption fields | Review `migration.sql` | ✅ |
| **Retention Policy Design** | Schema includes `created_at`, `expires_at` fields | Review schema | ✅ |
| **API Authentication Placeholder** | API routes include auth decorator (even if localhost) | Code review | ✅ |

### Phase 1: Video Data Governance

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Video File Encryption** | Video chunks stored with filesystem encryption (FileVault/LUKS) | Manual check: verify encryption status | ✅ (env) |
| **Retention Policy Active** | Chunks >30 days auto-deleted | Set test chunk to old timestamp, verify deletion after 24h | ✅ |
| **OCR PII Detection (Optional)** | OCR text scanned for SSN/credit card patterns | Test with sample PII text, verify detection | ⏭️ SKIP |

### Phase 2.0: Audio Data Governance

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Audio File Encryption** | Audio chunks stored with filesystem encryption | Manual check: verify encryption status | ⬜️ |
| **Transcription Redaction (Optional)** | Transcripts can redact detected PII | Test with sample PII audio, verify redaction | ⬜️ |
| **Retention Policy Active** | Audio >30 days auto-deleted | Set test chunk to old timestamp, verify deletion | ⬜️ |

### Phase 5: Remote Deployment Governance

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **HTTPS Only** | All API endpoints enforce HTTPS | `curl http://` returns 301 redirect to `https://` | ⬜️ |
| **TLS 1.3** | Server negotiates TLS 1.3 | `openssl s_client -connect server:443 -tls1_3` | ⬜️ |
| **Authentication Active** | All API routes require valid API key or JWT | `curl` without auth returns 401 | ⬜️ |
| **Deletion API Works** | Manual deletion securely removes data | Call deletion API, verify file + DB record removed | ⬜️ |
| **Data Export for Backup** | User can export all data with checksums | Run export script, verify `sha256sum -c` passes | ⬜️ |
| **Audit Log** | All deletion/modification operations logged | Review audit log after test operations | ⬜️ |

### Failure Signals

| Phase | Failure Signal | Action |
|-------|----------------|--------|
| **Phase 0** | Cannot define PII categories | Re-evaluate what data is captured |
| **Phase 1/2** | Filesystem encryption not available | Add application-layer encryption (AES-256) |
| **Phase 5** | TLS 1.3 not supported | Upgrade server OS or use reverse proxy (Nginx) |
| **Phase 5** | Deletion API leaves orphaned files | Fix deletion logic, add integrity check |

---

## Upload Queue Buffer Gates (ADR-0002 Compliance)

This section validates the temporary local buffer strategy defined in ADR-0002.

### Phase 0: Upload Queue Design Validation

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Buffer Capacity Enforcement** | Client respects 100GB max capacity | Fill buffer to 101GB, verify oldest chunk deleted (FIFO) | ✅ |
| **TTL Cleanup** | Chunks >7 days auto-deleted | Set test chunk timestamp to 8 days ago, verify cleanup job removes it | ✅ |
| **FIFO Deletion** | Oldest chunks deleted first when capacity reached | Create chunks with sequential timestamps, fill capacity, verify deletion order | ✅ |
| **Post-Upload Deletion** | Successful upload deletes local copy within 1s | Upload chunk, verify local file removed after 202 Accepted | ✅ |
| **Retry Exponential Backoff** | Retry delays: 1min → 5min → 15min → 1h → 6h | Simulate upload failures, measure retry intervals | ✅ |

### Phase 5: Upload Queue Production Validation

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **100GB Stress Test** | Client buffers 100GB without crash | Record 2 days with server offline (50GB/day), verify no crashes | ⬜️ |
| **Network Reconnect Resume** | Queue resumes automatically after network restore | Disconnect network for 1 hour, reconnect, verify uploads resume | ⬜️ |
| **7-Day TTL Enforcement** | Daily cleanup job runs successfully | Monitor TTL cleanup job for 7 days, verify old chunks removed | ⬜️ |
| **Zero Data Loss** | All queued chunks eventually uploaded | Compare local enqueue count vs server receive count over 48h | ⬜️ |

### Failure Signals

| Scenario | Failure Signal | Action |
|----------|----------------|--------|
| **Buffer Capacity** | Disk full despite 100GB limit | Fix capacity calculation bug, add disk space pre-check |
| **TTL Cleanup** | Chunks >7 days still present | Debug cleanup job scheduling, verify cron/scheduler working |
| **FIFO Deletion** | Wrong chunks deleted (not oldest) | Fix deletion sort order, add unit tests |
| **Retry Backoff** | Upload attempts too frequent or too infrequent | Adjust backoff parameters, add jitter to prevent thundering herd |

---

## Phase 0: Foundation & Client-Server Boundary

### 1. Functional Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Schema Migration Success** | All new tables created (video_chunks, frames, ocr_text, audio_chunks, audio_transcriptions) | Run migration script, check `sqlite3 recall.db ".tables"` | ✅ |
| **Backward Compatibility** | Existing screenshot pipeline 100% functional after migration | Run full screenshot capture → upload → OCR → search workflow | ✅ |
| **API Versioning** | `/api/v1/*` routes functional, `/api/*` aliases work | Automated API test suite (pytest) | ✅ |
| **Configuration Matrix** | All 4 deployment modes configurable (local, remote, debian_client, debian_server) | Load each config variant, verify env vars parsed | ✅ |

### 2. Performance Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Migration Latency** | <5 seconds for 10K entries | Time migration script on test DB (10K rows) | ✅ |
| **Query Overhead** | Schema changes add <10ms to typical queries | Benchmark search query before/after migration (100 runs) | ✅ |

### 3. Stability Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Data Integrity** | Zero data loss during migration | Compare checksums (SHA256) of data before/after | ✅ |
| **Rollback Success** | Rollback script restores original state in <2 minutes | Execute rollback, verify all tables, run test query | ✅ |

### 4. Resource Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Peak Memory** | Migration uses <500MB RAM | Monitor with `psutil` during migration | ✅ |
| **Disk Space** | Schema overhead <10MB (empty tables) | Compare DB file size before/after | ✅ |

---

## Phase 1: Screen Recording Pipeline

### 1. Functional Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Recording Loop Stable** | 1-hour continuous recording produces valid video chunks | Run VideoRecorder for 1 hour, verify all chunks playable with FFmpeg | ✅ (unit) |
| **Frame Extraction Working** | All frames extracted from video chunks and stored in DB | Query `SELECT COUNT(*) FROM frames` after 1-hour recording | ✅ |
| **OCR Indexed** | All extracted frames have OCR text in FTS database | Query `ocr_text_fts` for sample frames, verify text returned | ✅ |
| **Timeline API Functional** | API returns correct frames for time range queries | `GET /api/v1/timeline?start_time=...&end_time=...`, verify frame count | ✅ |
| **Searchable** | Can search OCR text from video frames via existing search endpoint | Search for known text from video frame, verify result returned | ✅ |

### 2. Performance Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Frame Extraction Latency** | <2 seconds per frame (average) | Measure time for `extract_frames()` call on 100 frames | ✅ |
| **End-to-End Indexing** | <60 seconds per 1-minute chunk (recording → searchable) | Timestamp: chunk complete → frame searchable via API | 🟨 PENDING |
| **Recording CPU Overhead** | <5% CPU during recording | Monitor `psutil.cpu_percent()` over 1-hour recording | 🟨 PENDING |
| **FFmpeg Stdin Write Latency** | p95 under frame budget | Track per-frame `write_frame()` latency, report p95/max | ✅ (synthetic: p95=0.30ms) |

### 3. Quality Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **OCR Accuracy** | ≥95% character accuracy on video frames | Test on 100-frame curated dataset, measure WER vs ground truth | 🟨 PENDING |
| **Frame Deduplication** | <1% false negatives (missed changes) | Manual review of 100 deduplicated frames, count missed changes | ✅ (unit) |

### 4. Stability Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **7-Day Continuous Run** | Zero crashes over 7 days of continuous recording | Run VideoRecorder 24/7 for 7 days, monitor logs for crashes | 🟨 PENDING |
| **Upload Retry Success** | >99% upload success rate (including retries) | Count successful uploads / total uploads over 24 hours | 🟨 PENDING |

### 5. Resource Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Storage per Day** | <50GB per day (24-hour recording) | Measure disk usage after 24-hour recording session | 🟨 PENDING |
| **Memory Footprint** | <500MB RAM for VideoRecorder + uploader | Monitor `psutil.memory_info().rss` during recording | 🟨 PENDING |
| **10-Minute Memory Drift** | RSS delta (minute10-minute1) <=80MB | Record process RSS at minute 1 and minute 10 in stress run | ✅ (synthetic: Δ0.02MB) |

### 6. Degradation Strategy Validation

| Scenario | Expected Behavior | Validation Method | Status |
|----------|-------------------|-------------------|--------|
| **FFmpeg Crash** | Auto-restart within 60s, log incident | Kill FFmpeg process, verify auto-restart and logging | ✅ |
| **Disk Full** | Recording pauses, oldest chunks deleted | Fill disk to <10GB, verify pause and cleanup | ✅ |
| **OCR Processing Slow** | Reduce FPS to 1/10, skip deduplication | Simulate slow OCR, verify FPS reduction | ✅ (design) |
| **Upload Failure (Network Down)** | Switch to local-only mode, retry hourly | Disconnect network, verify local buffering and retry; confirm consumer dispatch logs show `item_type` + target uploader branch | ✅ |
| **Profile Change (pix_fmt/size/range)** | Immediate per-monitor atomic restart, no mixed input session | Inject profile switch, verify `reconfigure()` + generation guard | ✅ |

### 7. Post-Baseline Regression Checks (Non-Gating)

These checks do not change the original 21 gate counts. They capture high-priority regressions fixed after initial Phase 1 engineering sign-off.

| Check | Expected Behavior | Validation Method | Status |
|------|-------------------|-------------------|--------|
| **Legacy Upload Video Routing** | `/api/upload` forwards video payload to v1 video handler, not screenshot OCR path | Upload MP4 to legacy endpoint, verify `video_chunks` insert succeeds | ✅ |
| **Search Debug Video-Only Rendering** | Search debug path handles `video_frame` entries without snapshot object | Query that returns only `vframe:*`, verify no `NoneType.context` crash | ✅ |
| **Runtime Recording Toggle Pause/Resume** | Toggle OFF pauses source capture only; toggle ON resumes without rebuilding pipelines | Control toggle integration + unit tests on pause/resume helpers | ✅ |
| **OCR Startup Warm-up** | Startup preload path warms OCR provider when local OCR backend is enabled | Startup regression test verifies OCR preload call path | ✅ |
| **SCK Fallback/Recovery Observability** | SCK errors are classified, fallback is delayed by retry policy, and capture health is queryable | Verify `/api/v1/vision/status` fields + retry/backoff/recovery unit tests | ✅ |

### Phase 1 Gate Summary

| Category | Total | Passed | Failed | Pending | Skipped |
|----------|-------|--------|--------|---------|---------|
| Functional (F) | 5 | 5 | 0 | 0 | 0 |
| Performance (P) | 3 | 1 | 0 | 2 | 0 |
| Quality (Q) | 2 | 1 | 0 | 1 | 0 |
| Stability (S) | 2 | 0 | 0 | 2 | 0 |
| Resource (R) | 2 | 0 | 0 | 2 | 0 |
| Degradation (D) | 4 | 4 | 0 | 0 | 0 |
| Data Governance (DG) | 3 | 2 | 0 | 0 | 1 |
| **Total** | **21** | **13** | **0** | **7** | **1** |

**Go/No-Go**: COMPLETE (non-long-run closure). Long-run evidence remains `PENDING` and is tracked as future non-blocking observation work.

---

## Phase 2.0: Audio MVP (No Speaker ID)

### 1. Functional Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Audio Capture Working** | Both system audio and microphone captured for 1 hour | Verify audio chunk files created, playable with media player | ⬜️ |
| **VAD Filtering** | Only speech segments transcribed (silence skipped) | Compare total audio duration vs transcribed duration (expect <50%) | ⬜️ |
| **Whisper Transcription** | All speech segments transcribed and stored in DB | Query `SELECT COUNT(*) FROM audio_transcriptions` after 1 hour | ⬜️ |
| **Audio FTS Indexed** | Transcriptions searchable via FTS | Query `audio_fts` for known phrase, verify result returned | ⬜️ |
| **Unified Timeline** | Timeline API returns both video frames AND audio transcriptions | `GET /api/v1/timeline`, verify both frame and audio entries | ⬜️ |

### 2. Performance Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Transcription Latency** | <30 seconds for 30-second audio segment (GPU) or <90s (CPU) | Measure time for `transcribe()` call on 30s audio | ⬜️ |
| **VAD Processing** | <1 second per 30-second segment | Measure time for `has_speech()` call on 30s audio | ⬜️ |
| **Transcription Throughput** | Keeps up with real-time recording (no backlog growth) | Monitor queue depth over 1-hour recording, verify stable | ⬜️ |
| **Audio Capture CPU** | <3% CPU per audio device | Monitor `psutil.cpu_percent()` for audio capture process | ⬜️ |

### 3. Quality Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Transcription WER (Clean Audio)** | ≤15% Word Error Rate | Test on LibriSpeech test-clean dataset, compute WER | ⬜️ |
| **Transcription WER (Noisy Audio)** | ≤30% Word Error Rate | Test on real-world meeting recordings, compute WER | ⬜️ |

### 4. Stability Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **24-Hour Continuous Run** | Zero crashes over 24 hours of audio recording | Run AudioRecorder 24/7 for 24 hours, monitor logs | ⬜️ |

### 5. Resource Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Whisper GPU VRAM** | <500MB GPU memory | Monitor `nvidia-smi` during transcription | ⬜️ |
| **Audio Storage** | <2GB per day (system + mic, 16kHz WAV) | Measure disk usage after 24-hour recording | ⬜️ |

---

## Phase 2.1: Speaker Identification (OPTIONAL)

### 1. Functional Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Speaker Diarization** | Audio segments labeled with speaker IDs | Query `audio_transcriptions`, verify `speaker_id` populated | ⬜️ |
| **Cross-Device Deduplication** | Duplicate transcriptions (system + mic) merged | Record same audio on both devices, verify only 1 transcription stored | ⬜️ |

### 2. Quality Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Speaker Diarization Error Rate (DER)** | ≤20% | Test on AMI corpus or similar, compute DER | ⬜️ |
| **Speaker Clustering Stability** | Same speaker maintains same ID over 24 hours | Record known speaker at T=0 and T=24h, verify ID consistency | ⬜️ |

---

## Phase 3: Multi-Modal Search Integration

### 1. Functional Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Unified Search API** | Single API endpoint returns results from both vision and audio | `GET /api/v1/search?q=test&content_type=all`, verify mixed results | ⬜️ |
| **Content Type Filtering** | Can filter by `vision` only, `audio` only, or `all` | Test each content_type parameter, verify filtering works | ⬜️ |
| **Time Range Filtering** | Search respects `start_time` and `end_time` parameters | Query with time bounds, verify all results within range | ⬜️ |
| **Web UI Rendering** | UI distinguishes vision results (thumbnails) from audio (transcription snippets) | Manual inspection of search results page | ⬜️ |

### 2. Performance Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Search Latency (Median)** | <300ms | Measure 100 typical queries, compute median latency | ⬜️ |
| **Search Latency (p95)** | <500ms | Measure 100 typical queries, compute 95th percentile | ⬜️ |
| **Indexing Latency** | <60 seconds per 1-min chunk (end-to-end searchable) | Timestamp: chunk upload → searchable via API | ⬜️ |

### 3. Quality Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Precision@10** | ≥0.7 (70% of top 10 results relevant) | Manual relevance judgments on 50 test queries | ⬜️ |
| **Recall@50** | ≥0.8 (80% of relevant docs in top 50) | Manual relevance judgments on 50 test queries | ⬜️ |
| **NDCG@10** | ≥0.75 (ranking quality) | Compute NDCG on 50 test queries with graded relevance | ⬜️ |

---

## Phase 4: Chat Capability

### 1. Functional Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Chat API Functional** | `POST /api/v1/chat` returns relevant response | Send test message "what did I work on yesterday?", verify response | ⬜️ |
| **Tool Calling Works** | Chat correctly calls `search_timeline` tool | Send query requiring search, verify tool_calls in response | ⬜️ |
| **Time Parsing** | Natural language time expressions parsed (`@yesterday`, `last hour`) | Test queries with time expressions, verify correct time range used | ⬜️ |
| **Web UI Chat Page** | `/chat` page renders, accepts input, displays responses | Manual testing of chat interface | ⬜️ |
| **Tool Call Visualization** | UI shows which tool calls were made and results | Verify expandable tool call cards in UI | ⬜️ |

### 2. Performance Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Chat Latency (Median)** | <5 seconds | Measure 50 typical queries, compute median latency | ⬜️ |
| **Chat Latency (p95)** | <10 seconds | Measure 50 typical queries, compute 95th percentile | ⬜️ |
| **Tool Execution Latency** | <2 seconds per tool call | Measure time for `search_timeline` execution | ⬜️ |

### 3. Quality Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Relevance** | ≥80% of responses on-topic | Human evaluation on 50 test queries | ⬜️ |
| **Groundedness** | ≥90% of facts from tool results (no hallucination) | Manual fact-checking on 50 responses | ⬜️ |
| **Helpfulness** | ≥70% of responses actionable/useful | User survey (5-point Likert scale) | ⬜️ |
| **Hallucination Rate** | <10% | Count hallucinated facts / total facts in 50 responses | ⬜️ |

### 4. Resource Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Cost per Query** | <$0.05 (with gpt-4o-mini) | Track OpenAI API costs for 100 queries | ⬜️ |
| **Tokens per Query** | <3000 (input + output) | Log token usage from API responses | ⬜️ |

### 5. Degradation Strategy Validation

| Scenario | Expected Behavior | Validation Method | Status |
|----------|-------------------|-------------------|--------|
| **Infinite Tool Call Loop** | Max 2 tool calls enforced, chat returns partial result | Craft query triggering loop, verify limit enforced | ⬜️ |
| **Tool Execution Timeout** | Chat returns error after 30s, graceful failure | Simulate slow search, verify timeout handling | ⬜️ |
| **LLM API Failure** | Fallback to cached response or error message | Disconnect from OpenAI API, verify fallback | ⬜️ |

---

## Phase 5: Deployment Migration

### 1. Functional Gates (Phase 5.0: Remote API Readiness Audit)

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **API Versioning Coverage** | All public endpoints exposed under `/api/v1/*` | Endpoint inventory + integration tests | ⬜️ |
| **Stateless API Compliance** | No server-side session dependency in request handling | Code review + restart server during requests, verify continuity | ⬜️ |
| **Pagination on List Endpoints** | All list/search endpoints support pagination (`limit/offset` or cursor) | API contract tests on list endpoints | ⬜️ |
| **Auth Placeholder Coverage** | Protected routes enforce auth middleware placeholder in localhost mode | `curl` protected route without auth, verify rejection behavior | ⬜️ |

### 2. Functional Gates (Phase 5.1: Local-Remote Simulation)

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Latency Simulation** | System functional with 50ms artificial latency | Use `tc` or Network Link Conditioner, run full workflow | ⬜️ |
| **Bottleneck Identification** | Top 3 latency-sensitive endpoints identified | Profile all endpoints under simulated latency | ⬜️ |

### 3. Functional Gates (Phase 5.2: Containerization)

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Docker Build Success** | `docker build` completes without errors | Run `docker build -t myrecall-server .` | ⬜️ |
| **Docker Compose Up** | Server starts via docker-compose, passes health check | Run `docker-compose up`, curl `/api/health` | ⬜️ |
| **Volume Persistence** | Data persists across container restarts | Stop & restart container, verify data intact | ⬜️ |

### 4. Functional Gates (Phase 5.3: Bulk Data Upload)

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Chunked Upload Works** | Large file (1GB) uploaded in chunks | Upload 1GB video, verify multipart upload | ⬜️ |
| **Resume After Failure** | Upload resumes from last byte after interruption | Kill upload mid-transfer, restart, verify resume | ⬜️ |
| **Upload Prioritization** | Recent chunks uploaded first (LIFO) | Queue 10 chunks, verify upload order | ⬜️ |

### 5. Functional Gates (Phase 5.4: Client Refactor)

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **No Local DB Dependency** | Client no longer reads/writes SQLite or LanceDB in runtime path | Disable local DB files, run client workflow, verify success | ⬜️ |
| **API-Only Data Path** | Timeline/search/chat all fetched from remote API | Network trace + integration tests for core user flows | ⬜️ |
| **Offline Buffer-Only Storage** | Client stores only temporary upload queue artifacts locally | Inspect client filesystem during run, verify policy compliance | ⬜️ |

### 6. Functional Gates (Phase 5.5: Gray Release & Cutover)

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Data Export Success** | All data exported to tar.gz with checksums | Run export script, verify checksum file | ⬜️ |
| **Data Import Success** | All data imported to Debian server, checksums match | Run import script, verify `sha256sum -c checksums.txt` | ⬜️ |
| **Gray Release (1 PC)** | 1 test client works with remote server for 24 hours | Update 1 client config, monitor for 24 hours | ⬜️ |
| **Full Cutover** | All clients switched to remote server, monitored for 48 hours | Update all clients, monitor logs and metrics | ⬜️ |
| **Rollback Drill** | Rollback to local server completes in <1 hour | Execute rollback procedure, time completion | ⬜️ |

### 7. Performance Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Upload Time (1GB Chunk)** | <5 minutes over 50Mbps uplink | Upload 1GB test file, measure time | ⬜️ |
| **Upload Queue Depth (p95)** | <10 chunks queued | Monitor queue depth over 7 days, compute p95 | ⬜️ |
| **Server Uptime** | >99.5% (downtime <1 hour/week) | Monitor server over 4 weeks, compute uptime | ⬜️ |

### 8. Stability Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Upload Success Rate** | >95% over 7 days (including retries) | Count successful uploads / total attempts | ⬜️ |
| **Server Crash Recovery** | Server restarts within 60s, no data loss | Kill server process, verify auto-restart and data integrity | ⬜️ |

### 9. Data Integrity Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Zero Checksum Mismatches** | All files match during migration | Verify `sha256sum -c checksums.txt` all pass | ⬜️ |
| **SQLite Integrity Check** | Database passes integrity check | Run `PRAGMA integrity_check` on all DBs | ⬜️ |
| **Zero Data Loss** | All local chunks successfully uploaded | Compare local chunk count vs server chunk count | ⬜️ |

---

## Failure Signal Matrix

| Phase | Failure Signal | Action |
|-------|----------------|--------|
| **Phase 0** | Migration takes >30s on modest DB (10K entries) | Optimize migration script or split into batches |
| **Phase 0** | Rollback corrupts data in any test case | Fix rollback script, add more validation |
| **Phase 1** | FFmpeg crashes >10 times/day in 7-day test | Abandon FFmpeg approach, evaluate PyAV or opencv |
| **Phase 1** | Frame extraction cannot keep up with 1/10 FPS | Optimize extraction pipeline or reduce FPS further |
| **Phase 1** | Storage exceeds 50GB/day | Increase compression (CRF 28 → 32) or reduce resolution |
| **Phase 2** | Whisper transcription backlog grows indefinitely | Switch to faster model (base → tiny), add GPU, or simplify pipeline |
| **Phase 2** | Transcription WER >40% on typical audio | Re-evaluate Whisper model or add preprocessing |
| **Phase 3** | Search latency >1s p95 | Optimize FTS queries, add caching, or parallelize |
| **Phase 4** | Hallucination rate >30% | Improve prompt, add more grounding, or switch LLM |
| **Phase 4** | Cost per query >$0.20 | Reduce context size, use cheaper model, or add local LLM |
| **Phase 4** | Chat latency >20s median | Optimize tool execution, reduce tool calls, or simplify search |
| **Phase 5** | Upload failure rate >10% over 24 hours | Debug network issues, improve retry logic, or increase timeout |
| **Phase 5** | Data corruption detected during migration | Halt migration, debug export/import scripts, restore from backup |

---

## Continuous Monitoring (Post-MVP)

After Phase 5 completion, establish continuous monitoring for:

| Metric | Threshold | Alert Channel |
|--------|-----------|---------------|
| **Server Uptime** | <99.5% (weekly) | Email |
| **Upload Success Rate** | <95% (daily) | Email |
| **Search Latency p95** | >1s (hourly) | Dashboard |
| **Chat Hallucination Rate** | >20% (weekly sample) | Manual review |
| **Disk Space** | <10GB free | Email + desktop notification |
| **Error Rate** | >5% (5-min window) | Email |

---

## Phase 6: Streaming Chat (FUTURE)

Placeholder section for Phase 6 gates. To be detailed when streaming implementation begins.

**Timeline**: Week 21-22

**Owner**: TBD

---

## Phase 7: Memory Capabilities (FUTURE, Week 23+)

Placeholder section for Phase 7 gates. Go/No-Go criteria to be defined after Phase 4 completion, based on user feedback and deployment learnings.

**Timeline**: Week 23+ (延后实施)

**Owner**: TBD

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-06 | Initial phase gates definition (baseline for Phase 0) |
| 1.1 | 2026-02-06 | Phase 0 gates marked ✅ (all 19 passed: 4 Functional, 2 Performance, 2 Stability, 2 Resource, 4 Data Governance, 5 Upload Queue) |
| 1.2 | 2026-02-06 | Phase 1 gates updated: 13 ✅, 7 🟨 PENDING, 1 ⏭️ SKIP. All Functional (5/5) and Degradation (4/4) gates passed. Performance/Quality/Stability/Resource gates pending long-run evidence. |
| 1.3 | 2026-02-06 | Consistency cleanup: header version aligned to latest history entry; Phase 1 OCR gate validation method updated to `ocr_text_fts` terminology. |
| 1.4 | 2026-02-07 | Upload-failure gate observability tightened: validation now explicitly checks consumer dispatch logs for `item_type` and target uploader branch. |
| 1.5 | 2026-02-07 | Added Phase 1 post-baseline regression checks (non-gating): legacy video upload routing, search-debug video-only render safety, runtime recording pause/resume semantics, and OCR startup warm-up validation. |
| 1.6 | 2026-02-09 | Phase 1 decision status updated to COMPLETE for roadmap progression; 7 long-run items remain `PENDING` and move to future non-blocking observation tracking. |

---

**Next Update**: Long-run observation evidence append (1-P-02/1-P-03/1-Q-01/1-S-01/1-S-02/1-R-01/1-R-02) after Week 9-12 tracking window.
