# MyRecall-v3 Phase 1 Detailed Plan — Screen Recording Pipeline

**Version**: 1.1
**Last Updated**: 2026-02-07
**Status**: Executed (Engineering Complete; long-run evidence pending)
**Timeline**: Week 3-6 (Day 1-20, 20 working days)
**Owner**: Solo Developer

---

## Execution Status Addendum (2026-02-07)

This document remains the execution baseline plan. The implementation has been completed and validated at engineering level.

Post-baseline bugfixes and hardening changes are tracked in:

- `/Users/pyw/newpart/MyRecall/v3/results/phase-1-validation.md`
- `/Users/pyw/newpart/MyRecall/v3/results/phase-1-post-baseline-changelog.md`

Audio Freeze relationship:
- This is a historical execution document for vision pipeline hardening.
- As of ADR-0005, audio extensions are frozen for MVP critical path and do not gate this plan's completed status.

---

## 1. Goal / Non-Goals

### Goal

**Objective**: Replace the screenshot-based capture pipeline with an FFmpeg-based continuous video recording system that produces searchable, time-indexed OCR text from screen activity.

**Business Value**: Video recording captures continuous screen activity (vs discrete snapshots), enabling richer timeline browsing, higher OCR coverage, and alignment with the screenpipe reference architecture. This is the data foundation for Phase 2 (audio), Phase 3 (search), and Phase 4 (chat).

### Non-Goals

- **No audio capture** — audio is Phase 2
- **No multi-modal unified search** — unified search API (`content_type` filtering) is Phase 3
- **No chat or LLM integration** — chat is Phase 4
- **No real authentication enforcement** — real auth is Phase 5
- **No Docker/containerization** — containerization is Phase 5.2
- **No VLM caption/embedding for video frames** — Phase 1 uses OCR-only indexing; VLM + vector search for frames deferred to Phase 3 implementation
- **No Web UI changes** — timeline UI improvements are Phase 3 scope
- **No Speaker ID** — Phase 2.1 (optional)
- **No cross-encoder rerank on video frames** — existing rerank operates on SemanticSnapshot (screenshot pipeline); video frame reranking is Phase 3

---

## 2. Scope

### In-Scope

- FFmpeg-based screen recording with 1-minute chunk rotation
- FFmpeg subprocess management (watchdog, auto-restart, crash handling)
- Client-side VideoRecorder class (replaces ScreenRecorder as primary)
- Server-side video chunk storage and DB writes (video_chunks table)
- Frame extraction from video chunks (configurable interval, default 1 frame/5s)
- Frame deduplication (MSSIM-based, skip similar consecutive frames)
- OCR on extracted frames (reuse existing OCR providers)
- Write OCR results to ocr_text table + ocr_text_fts virtual table
- Extend search engine to query ocr_text_fts (keyword search for video frames)
- Timeline API endpoint (GET /api/v1/timeline)
- Frame serving API (GET /api/v1/frames/:id)
- Retention cleanup worker (expires_at enforcement, file + DB cleanup)
- Screenshot fallback (video fails → auto-switch to screenshot mode)
- Degradation handlers (FFmpeg crash, disk full, OCR slow, network down)
- Upload resume capability for large video chunks
- Schema extension: add status column to video_chunks (migration v3_002)
- Comprehensive test suite for all Phase 1 gates

### Out-of-Scope

- Audio capture/transcription (Phase 2)
- Unified multi-modal search API (Phase 3)
- VLM analysis / embedding generation for video frames (Phase 3)
- Chat functionality (Phase 4)
- Docker, TLS, real auth (Phase 5)
- Streaming chat (Phase 6)
- Memory capabilities (Phase 7)

---

## 3. Inputs / Outputs

### Inputs (from Phase 0)

| Input | Source | Status |
|-------|--------|--------|
| v3 DB schema (video_chunks, frames, ocr_text tables) | `migrations/v3_001_add_multimodal_tables.sql` | Available (Phase 0) |
| FTS virtual tables (ocr_text_fts) | Same migration SQL | Available (empty) |
| Pydantic models (VideoChunk, Frame, OcrText) | `openrecall/shared/models.py` | Available |
| API v1 blueprint with pagination | `openrecall/server/api_v1.py` | Available |
| Auth placeholder decorator | `openrecall/server/auth.py` | Available |
| Upload queue (ADR-0002) | `openrecall/client/upload_queue.py` | Available |
| Configuration matrix (4 modes) | `openrecall/shared/config.py` + presets | Available |
| Migration runner | `migrations/runner.py` | Available |
| Runtime hardening note | `openrecall/server/database/sql.py` | SQLStore init runs migration runner idempotently; `/api/upload` video path no longer depends on manual migration |
| PII Classification Policy | `v3/results/pii-classification-policy.md` | Available |
| Retention Policy Design | `v3/results/retention-policy-design.md` | Available |
| Phase 0 validation (19/19 gates passed) | `v3/results/phase-0-validation.md` | Frozen |
| Existing OCR providers (DocTR, RapidOCR) | `openrecall/server/ocr/` | Available |
| Existing search engine (hybrid + rerank) | `openrecall/server/search/engine.py` | Available |

### Outputs (for Phase 2/3)

| Output | Consumer | Purpose |
|--------|----------|---------|
| VideoRecorder + FFmpegManager | Phase 2 (audio will use similar pattern) | Capture architecture reference |
| Populated video_chunks + frames + ocr_text tables | Phase 3 (search), Phase 4 (chat) | Searchable video data |
| ocr_text_fts populated + search integration | Phase 3 (unified search) | OCR text queryable |
| Timeline API (GET /api/v1/timeline) | Phase 3 (UI), Phase 4 (chat tool) | Time-range frame queries |
| Frame serving API (GET /api/v1/frames/:id) | Phase 3 (UI thumbnails) | On-demand frame images |
| Retention cleanup worker | Phase 2 (audio retention), Phase 5 (server enforcement) | expires_at enforcement |
| Degradation patterns | Phase 2 (audio degradation) | Fallback architecture reference |
| Phase 1 gate validation report | Phase 2 Go/No-Go decision | Evidence of pipeline readiness |

---

## 4. Day-by-Day Plan (Week 3-6, 20 Working Days)

### Execution Tracks

```
Track A (Recording):     Day 1 ████ Day 2 ████ Day 3 ──── Day 4 ──── Day 5 ████
Track B (Processing):                            Day 3 ██── Day 4 ████ Day 5 ──██ Day 6 ████ Day 7 ████
Track C (Search+API):                                                              Day 8 ████ Day 9 ████ Day 10 ████ Day 11 ████ Day 12 ████
Track D (Infra):                                                                                                                              Day 13 ████ Day 14 ████ Day 15 ████
Track E (Validation):                                                                                                                                                                 Day 16 ████ Day 17 ████ Day 18 ████ Day 19 ████ Day 20 ████
```

### Week 3 (Day 1-5): Core Recording + Frame Extraction

#### Day 1: FFmpeg Manager

**Focus**: FFmpeg subprocess wrapper with lifecycle management

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 1.1 | Create FFmpegManager class: start/stop FFmpeg subprocess, pipe control | `openrecall/client/ffmpeg_manager.py` (new) |
| 1.2 | Implement watchdog timer: detect hung/crashed FFmpeg, auto-restart | Same file |
| 1.3 | Logging: capture FFmpeg stderr for diagnostics | Same file |
| 1.4 | Unit tests for FFmpegManager | `tests/test_phase1_video_recorder.py` (new) |

**Dependencies**: FFmpeg installed (external dependency)

**Interface Details - FFmpegManager**:

```python
class FFmpegManager:
    def __init__(self, output_dir: str, chunk_duration: int = 60,
                 fps: int = 30, crf: int = 23, resolution: str = ""):
        ...

    def start(self) -> None:
        """Legacy platform capture mode (kept for backward fallback)."""
        ...

    def start_with_profile(self, profile: PixelFormatProfile) -> None:
        """Start rawvideo stdin mode (monitor-id driven pipeline)."""
        # Input: -f rawvideo -pixel_format nv12|bgra -video_size WxH -framerate FPS -i -
        # Output: H.264 segment muxer, 1-min chunks
        ...

    def reconfigure(self, profile: PixelFormatProfile) -> bool:
        """Profile changed -> atomic restart with new -pixel_format/-video_size."""
        ...

    def write_frame(self, frame_bytes: bytes) -> float:
        """Write one frame to stdin, return write latency (seconds)."""
        ...

    def stop(self) -> str | None:
        """Signal FFmpeg to stop, return last chunk path."""
        ...

    def is_alive(self) -> bool:
        """Check if FFmpeg process is running."""
        ...

    def restart(self) -> None:
        """Kill and restart FFmpeg (watchdog recovery)."""
        ...

    @property
    def current_chunk_path(self) -> str | None:
        """Path to the chunk currently being written."""
        ...
```

**FFmpeg Command Template**:
```bash
ffmpeg -f rawvideo \                    # stdin raw frame stream
  -pixel_format nv12 \                  # or bgra (profile driven)
  -video_size 1920x1080 \               # profile driven
  -framerate 30 \                       # profile driven
  -i - \                                # read from pipe
  -c:v h264_videotoolbox \              # macOS default, fallback libx264
  -pix_fmt yuv420p \
  -f segment -segment_time 60 \         # 1-minute chunks
  -segment_format mp4 \                # MP4 container
  -reset_timestamps 1 \                # Reset timestamps per chunk
  -strftime 1 \                        # Use strftime pattern expansion
  monitor_{monitor_id}_%Y-%m-%d_%H-%M-%S.mp4   # UTC output pattern
```

**Verification**:
```bash
pytest tests/test_phase1_video_recorder.py::TestFFmpegManager -v
```

---

#### Day 2: VideoRecorder Class

**Focus**: High-level recording coordinator with chunk lifecycle

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 2.1 | Create VideoRecorder class: coordinates FFmpegManager + metadata | `openrecall/client/video_recorder.py` (new) |
| 2.2 | Chunk rotation: detect completed chunks, generate metadata JSON | Same file |
| 2.3 | Enqueue completed chunks into UploadQueue | Same file |
| 2.4 | Active app/window metadata per chunk (start/end) | Same file |
| 2.5 | Unit tests for VideoRecorder | `tests/test_phase1_video_recorder.py` (extend) |

**Dependencies**: Day 1 (FFmpegManager)

**Interface Details - VideoRecorder**:

```python
class VideoRecorder:
    def __init__(self, buffer: LocalBuffer, consumer: UploaderConsumer):
        ...

    def start(self) -> None:
        """Start uploader consumer."""
        ...

    def stop(self) -> None:
        """Stop monitor sources + pipelines + uploader consumer."""
        ...

class MonitorPipelineController:
    def start(self, profile: PixelFormatProfile) -> None: ...
    def submit_frame(self, frame: RawFrame) -> None: ...
    def stop(self) -> None: ...
    # Atomic restart state machine: RUNNING/RESTARTING/STOPPING + generation_id

class SCKMonitorSource:
    # CMSampleBuffer -> CVPixelBuffer -> stride-unpadded bytes -> RawFrame
    def start(self) -> None: ...
    def stop(self) -> None: ...

def pack_nv12_planes(...): ...
def pack_bgra_plane(...): ...
# Both helpers remove per-row padding, preventing skew/corruption.
```

**Hardening Notes (Section A/B/C)**:
```text
1) Smart Memory Pooling:
   FrameBufferPool.acquire(required_size) auto-grows to next power-of-two.
   If required_size > OPENRECALL_VIDEO_POOL_MAX_BYTES, use temporary buffer.

2) Atomic Restart:
   profile change (pix_fmt/width/height/color_range) => immediate reconfigure().
   writer checks generation_id before write; mismatched frames are dropped.

3) Pointer Safety:
   CVPixelBufferLockBaseAddress -> copy rows -> UnlockBaseAddress in finally.
   Never dump full plane memory directly to ffmpeg without unpadding.
```

**Chunk Metadata Extension (Monitor Identity)**:
```json
{
  "monitor_id": "69734144",
  "monitor_width": 3840,
  "monitor_height": 2160,
  "monitor_is_primary": 1,
  "monitor_backend": "sck",
  "monitor_fingerprint": "3840x2160:1"
}
```

**Compatibility**:
```text
- OPENRECALL_AVFOUNDATION_VIDEO_DEVICE: still accepted, but deprecated.
- Legacy FFmpeg platform capture remains as fallback only.
```

```python
def _on_chunk_complete(self, chunk_path: str, monitor: MonitorInfo | None = None) -> None:
    # Compute checksum + enqueue metadata (includes monitor_id fields)
        ...
```

**Chunk Metadata Schema**:
```json
{
  "type": "video_chunk",
  "start_time": 1710000000.0,
  "end_time": 1710000300.0,
  "device_name": "MacBook-Pro-Display",
  "checksum": "sha256:abc123...",
  "resolution": "2560x1600",
  "fps": 30,
  "codec": "h264",
  "crf": 23,
  "file_size_bytes": 52428800
}
```

**Verification**:
```bash
pytest tests/test_phase1_video_recorder.py -v
```

---

#### Day 3: Video Upload & Server Storage

**Focus**: Extend upload API for video chunks, server-side storage

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 3.1 | Schema migration v3_002: add status column to video_chunks | `migrations/v3_002_add_video_chunk_status.sql` (new) |
| 3.1b | Schema migration v3_003: add monitor_id + monitor_* columns | `migrations/v3_003_add_video_chunk_monitor_fields.sql` (new) |
| 3.2 | Extend POST /api/v1/upload to accept video/mp4 MIME type | `openrecall/server/api_v1.py` (modify) |
| 3.3 | Server-side video chunk storage: save to `~/MRS/video_chunks/` | `openrecall/server/api_v1.py` (modify) |
| 3.4 | SQLStore: add insert_video_chunk() method | `openrecall/server/database/sql.py` (modify) |
| 3.5 | Unit + integration tests for video upload | `tests/test_phase1_video_recorder.py` (extend) |

**Dependencies**: Day 2

**Schema Extension (v3_002)**:
```sql
-- v3_002: Add processing status to video_chunks
ALTER TABLE video_chunks ADD COLUMN status TEXT DEFAULT 'PENDING';
CREATE INDEX IF NOT EXISTS idx_video_chunks_status ON video_chunks(status);
```

**Schema Extension (v3_003)**:
```sql
ALTER TABLE video_chunks ADD COLUMN monitor_id TEXT DEFAULT '';
ALTER TABLE video_chunks ADD COLUMN monitor_width INTEGER DEFAULT 0;
ALTER TABLE video_chunks ADD COLUMN monitor_height INTEGER DEFAULT 0;
ALTER TABLE video_chunks ADD COLUMN monitor_is_primary INTEGER DEFAULT 0;
ALTER TABLE video_chunks ADD COLUMN monitor_backend TEXT DEFAULT '';
ALTER TABLE video_chunks ADD COLUMN monitor_fingerprint TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_video_chunks_monitor_id ON video_chunks(monitor_id);
```

**Interface Changes**:
- `POST /api/v1/upload`: Accept `Content-Type: multipart/form-data` with video/mp4 file
  - Metadata JSON `type` field: `"video_chunk"` (vs existing `"screenshot"`)
  - Client consumer dispatches by `metadata.type`:
    - `video_chunk` -> `upload_video_chunk`
    - otherwise -> `upload_screenshot`
- Returns `202 Accepted` with `{"chunk_id": <id>}`
- New directory: `~/MRS/video_chunks/{chunk_id}_{timestamp}.mp4`

**Verification**:
```bash
pytest tests/test_phase1_video_recorder.py::test_video_upload_accepted -v
```

---

#### Day 4: Frame Extraction

**Focus**: Extract frames from video chunks, deduplicate, store

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 4.1 | Create FrameExtractor class: FFmpeg-based frame extraction | `openrecall/server/video/frame_extractor.py` (new) |
| 4.2 | Frame deduplication: MSSIM comparison of consecutive frames | Same file |
| 4.3 | SQLStore: add insert_frame(), insert_frames_batch() methods | `openrecall/server/database/sql.py` (modify) |
| 4.4 | Frame file storage: `~/MRS/frames/{frame_id}.png` | `openrecall/server/video/frame_extractor.py` |
| 4.5 | Unit tests for FrameExtractor | `tests/test_phase1_frame_extractor.py` (new) |

**Dependencies**: Day 3 (video chunks in DB + filesystem)

**Interface Details - FrameExtractor**:

```python
class FrameExtractor:
    def __init__(self, extraction_interval: float = 5.0,
                 dedup_threshold: float = 0.95,
                 frames_dir: str = ""):
        ...

    def extract_frames(self, chunk_path: str,
                       video_chunk_id: int) -> list[ExtractedFrame]:
        """Extract frames at interval, deduplicate, return kept frames."""
        # 1. ffmpeg -i chunk.mp4 -vf "fps=1/5" -q:v 2 frame_%04d.png
        # 2. For each frame: compute MSSIM vs previous
        # 3. Skip if MSSIM > threshold (too similar)
        # 4. Return list of ExtractedFrame(path, offset_index, timestamp)
        ...

    def _compute_mssim(self, img_a: bytes, img_b: bytes) -> float:
        """Structural similarity between two frame images."""
        ...
```

**FFmpeg Frame Extraction Command**:
```bash
ffmpeg -i chunk.mp4 -vf "fps=1/5" -q:v 2 frame_%04d.png
```
This extracts 1 frame every 5 seconds (0.2 FPS).

**Verification**:
```bash
pytest tests/test_phase1_frame_extractor.py -v
```

---

#### Day 5: Recording-to-Frames Integration

**Focus**: Wire upload → storage → extraction → DB in end-to-end flow

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 5.1 | Integration test: upload chunk → extract frames → verify in DB | `tests/test_phase1_frame_extractor.py` (extend) |
| 5.2 | Verify frame deduplication works correctly on real video | Same file |
| 5.3 | Performance baseline: measure extraction time per chunk | Same file |
| 5.4 | Fix issues discovered during integration | Various |

**Dependencies**: Days 1-4

**Verification**:
```bash
pytest tests/test_phase1_frame_extractor.py -v
# Verify: 1-min chunk → ~12 extracted frames (1/5s) → N deduplicated frames in DB
# Verify: Frame files exist at expected paths
# Verify: frames table has correct video_chunk_id FKs
```

---

### Week 4 (Day 6-10): OCR & Search Pipeline

#### Day 6: OCR on Video Frames

**Focus**: Run OCR on extracted frames, write to v3 tables + FTS

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 6.1 | Create frame OCR pipeline: read frame image → OCR → write results | `openrecall/server/video/processor.py` (new) |
| 6.2 | SQLStore: add insert_ocr_text(), insert_ocr_text_fts() methods | `openrecall/server/database/sql.py` (modify) |
| 6.3 | Batch OCR support: process multiple frames efficiently | `openrecall/server/video/processor.py` |
| 6.4 | Unit tests for OCR pipeline | `tests/test_phase1_ocr_pipeline.py` (new) |

**Dependencies**: Day 4 (extracted frames available)

**Interface Details**:

```python
# In processor.py
class VideoChunkProcessor:
    def __init__(self, frame_extractor: FrameExtractor,
                 ocr_provider, sql_store, config: Settings):
        ...

    def process_chunk(self, video_chunk_id: int,
                      chunk_path: str) -> ProcessingResult:
        """Full pipeline: extract → dedup → OCR → store."""
        frames = self.frame_extractor.extract_frames(chunk_path, video_chunk_id)
        for frame in frames:
            frame_id = self.sql_store.insert_frame(frame)
            ocr_text = self.ocr_provider.extract_text(frame.path)
            self.sql_store.insert_ocr_text(frame_id, ocr_text)
            self.sql_store.insert_ocr_text_fts(frame_id, ocr_text,
                                                frame.app_name, frame.window_name)
        return ProcessingResult(total_frames=len(frames), ...)
```

**Verification**:
```bash
pytest tests/test_phase1_ocr_pipeline.py -v
# Verify: ocr_text table populated for each frame
# Verify: ocr_text_fts queryable with MATCH
```

---

#### Day 7: Video Processing Worker

**Focus**: Integrate video chunk processing into server worker

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 7.1 | Add video chunk processing to background worker | `openrecall/server/worker.py` (modify) |
| 7.2 | Queue management: poll video_chunks(status=PENDING) | Same file |
| 7.3 | Status transitions: PENDING → PROCESSING → COMPLETED/FAILED | Same file |
| 7.4 | Crash recovery: reset PROCESSING → PENDING on startup | Same file |
| 7.5 | Tests for video worker integration | `tests/test_phase1_ocr_pipeline.py` (extend) |

**Dependencies**: Day 6

**Worker Integration Design**:
- Existing worker loop: polls entries(status=PENDING) for screenshots
- New: also polls video_chunks(status=PENDING) for video chunks
- Video chunks processed via VideoChunkProcessor (Day 6)
- Two queues coexist: screenshot queue + video chunk queue
- Priority: video chunks first (they contain more data per item)

**Verification**:
```bash
pytest tests/test_phase1_ocr_pipeline.py -v
```

---

#### Day 8: Search Integration

**Focus**: Extend search engine to find OCR text from video frames

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 8.1 | Add ocr_text_fts query method to SQLStore | `openrecall/server/database/sql.py` (modify) |
| 8.2 | Extend SearchEngine._search_impl to include ocr_text_fts results | `openrecall/server/search/engine.py` (modify) |
| 8.3 | Merge video frame results with screenshot results | Same file |
| 8.4 | Tests for search across both sources | `tests/test_phase1_search_integration.py` (new) |

**Dependencies**: Day 7 (OCR text in FTS)

**Search Extension Design**:
- Existing: SearchEngine queries `ocr_fts` (fts.db) for screenshots
- New: Also query `ocr_text_fts` (recall.db) for video frames
- Results merged into unified result set
- Video frame results include: frame_id, timestamp, app_name, OCR text snippet
- Scoring: FTS BM25 score, same fusion logic as screenshots

**Verification**:
```bash
pytest tests/test_phase1_search_integration.py -v
# Verify: search query finds text from video frame OCR
# Verify: results include both screenshot and video frame sources
```

---

#### Day 9: End-to-End Pipeline Validation

**Focus**: Full flow test from recording to search

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 9.1 | End-to-end integration test: record → upload → process → search | `tests/test_phase1_search_integration.py` (extend) |
| 9.2 | 1-hour recording dry run (manual, validate chunks produced) | Manual |
| 9.3 | Measure end-to-end indexing time (recording → searchable) | Same test file |
| 9.4 | Fix pipeline issues discovered during integration | Various |

**Dependencies**: Days 1-8

**Verification**:
```bash
pytest tests/test_phase1_search_integration.py -v
# Verify: known text recorded on screen → found via /api/v1/search
```

---

#### Day 10: Screenshot Fallback & Dual-Mode

**Focus**: Ensure graceful fallback when video recording fails

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 10.1 | Add recording mode config: OPENRECALL_RECORDING_MODE | `openrecall/shared/config.py` (modify) |
| 10.2 | Implement mode switching in client main loop | `openrecall/client/recorder.py` (modify) |
| 10.3 | Auto fallback: video → screenshot on FFmpeg failure | Same file |
| 10.4 | Tests for mode switching and fallback | `tests/test_phase1_degradation.py` (new, partial) |

**Dependencies**: Days 1-2, existing ScreenRecorder

**Configuration**:

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `OPENRECALL_RECORDING_MODE` | `video`, `screenshot`, `auto` | `auto` | Recording mode |

- `video`: Only video recording (fail if FFmpeg unavailable)
- `screenshot`: Only screenshots (existing behavior)
- `auto`: Try video first, fallback to screenshots on failure

**Verification**:
```bash
pytest tests/test_phase1_degradation.py::test_fallback_video_to_screenshot -v
```

---

### Week 5 (Day 11-15): Timeline, Retention & Infrastructure

#### Day 11: Timeline API

**Focus**: New API endpoint for time-based frame browsing

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 11.1 | Implement GET /api/v1/timeline endpoint | `openrecall/server/api_v1.py` (modify) |
| 11.2 | SQLStore: add query_frames_by_time_range() method | `openrecall/server/database/sql.py` (modify) |
| 11.3 | Pagination support per ADR-0002 | `openrecall/server/api_v1.py` |
| 11.4 | Include OCR text in timeline response | Same file |
| 11.5 | Tests for timeline API | `tests/test_phase1_timeline_api.py` (new) |

**Dependencies**: Days 4, 6 (frames + OCR in DB)

**API Endpoint**:

```
GET /api/v1/timeline?start_time=<unix>&end_time=<unix>&limit=50&offset=0
```

**Response**:
```json
{
  "data": [
    {
      "frame_id": 123,
      "timestamp": 1710000005.0,
      "video_chunk_id": 1,
      "app_name": "VS Code",
      "window_name": "main.py",
      "ocr_text": "def hello_world()...",
      "frame_url": "/api/v1/frames/123"
    }
  ],
  "meta": {
    "total": 1200,
    "limit": 50,
    "offset": 0,
    "has_more": true
  }
}
```

**Verification**:
```bash
pytest tests/test_phase1_timeline_api.py -v
# Verify: GET /api/v1/timeline?start_time=...&end_time=... returns frames
# Verify: Pagination works
# Verify: OCR text included
```

---

#### Day 12: Frame Serving API

**Focus**: Serve individual frame images on demand

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 12.1 | Implement GET /api/v1/frames/:frame_id endpoint | `openrecall/server/api_v1.py` (modify) |
| 12.2 | On-demand extraction: if frame not cached, extract from video chunk | Same file |
| 12.3 | Frame cache management (LRU, configurable max size) | `openrecall/server/video/frame_extractor.py` (extend) |
| 12.4 | Tests for frame serving | `tests/test_phase1_timeline_api.py` (extend) |

**Dependencies**: Day 11

**API Endpoint**:
```
GET /api/v1/frames/:frame_id
Content-Type: image/png
```

Returns the raw PNG image for the frame. If the frame image is not cached on disk, extracts it from the parent video chunk on demand.

**Verification**:
```bash
pytest tests/test_phase1_timeline_api.py::test_frame_serving -v
```

---

#### Day 13: Retention Cleanup Worker + Start 7-Day Test

**Focus**: Implement data retention enforcement; begin stability test

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 13.1 | Create RetentionWorker class | `openrecall/server/retention.py` (new) |
| 13.2 | Scan and delete expired rows (expires_at < now()) | Same file |
| 13.3 | Delete associated files (video chunks, frame images) | Same file |
| 13.4 | Clean up orphaned FTS entries | Same file |
| 13.5 | Integrate into server startup (background thread, 6h interval) | `openrecall/server/app.py` (modify) |
| 13.6 | Set expires_at on new records (OPENRECALL_RETENTION_DAYS) | `openrecall/server/database/sql.py` (modify) |
| 13.7 | Tests for retention cleanup | `tests/test_phase1_retention.py` (new) |
| 13.8 | **Start 7-day stability test** (background: run VideoRecorder 24/7) | Manual |

**Dependencies**: Days 1-9 (full pipeline working)

**RetentionWorker Interface**:
```python
class RetentionWorker:
    def __init__(self, sql_store, config: Settings):
        self.interval = config.retention_check_interval  # default: 6h (21600s)
        ...

    def run(self) -> None:
        """Background loop: sleep → cleanup → repeat."""
        ...

    def cleanup_expired(self) -> CleanupResult:
        """Delete all rows where expires_at < datetime('now')."""
        # 1. Find expired video_chunks → delete files + DB rows (CASCADE to frames, ocr_text)
        # 2. Find expired entries → delete screenshot files + DB rows
        # 3. Vacuum orphaned FTS entries
        # 4. Log results
        ...
```

**7-Day Stability Test Protocol**:
- Start recording on Day 13 (Wednesday, Week 5)
- Runs through Day 19 (Tuesday, Week 6) — 7 calendar days
- Monitor via logs: check for crashes, FFmpeg restarts, errors
- On Day 19: collect metrics (crash count, restart count, disk usage, memory peak)

**Verification**:
```bash
pytest tests/test_phase1_retention.py -v
# Verify: expired chunks deleted from DB
# Verify: associated files removed from disk
# Verify: non-expired data intact
```

---

#### Day 14: Degradation Handlers

**Focus**: Implement all 4 degradation strategies from phase-gates.md

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 14.1 | FFmpeg crash handler: detect, log, auto-restart ≤60s | `openrecall/client/ffmpeg_manager.py` (extend) |
| 14.2 | Disk full handler: pause recording when <10GB free, clean oldest | `openrecall/client/video_recorder.py` (extend) |
| 14.3 | OCR processing slow handler: reduce extraction FPS dynamically | `openrecall/server/video/processor.py` (extend) |
| 14.4 | Upload failure handler: switch to local-only, retry hourly | `openrecall/client/video_recorder.py` (extend) |
| 14.5 | Tests for all degradation scenarios | `tests/test_phase1_degradation.py` (extend) |

**Dependencies**: Days 1-2, 6-7

**Degradation Matrix (from phase-gates.md)**:

| Scenario | Expected Behavior | Implementation |
|----------|-------------------|----------------|
| FFmpeg Crash | Auto-restart within 60s, log incident | FFmpegManager.watchdog detects exit, calls restart() |
| Disk Full (<10GB) | Recording pauses, oldest chunks deleted | Check disk_usage before chunk rotation, FIFO cleanup |
| OCR Processing Slow | Reduce extraction to 1/10 FPS, skip dedup | Monitor processing backlog, adjust extraction_interval |
| Upload Failure (Network) | Local-only mode, retry hourly | UploadQueue backoff, log offline state; consumer logs `item_type` + target uploader branch |

**Verification**:
```bash
pytest tests/test_phase1_degradation.py -v
```

---

#### Day 15: Upload Resume & Large Chunk Handling

**Focus**: Robust upload for large video files

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 15.1 | Chunked upload support for files >100MB | `openrecall/client/uploader.py` (modify) |
| 15.2 | Server: accept chunked transfer encoding | `openrecall/server/api_v1.py` (modify) |
| 15.3 | Upload progress tracking (for future UI) | `openrecall/client/video_recorder.py` (extend) |
| 15.4 | Resume after interruption (track uploaded bytes) | `openrecall/client/uploader.py` (modify) |
| 15.5 | Tests for large file upload + resume | `tests/test_phase1_video_recorder.py` (extend) |

**Dependencies**: Day 3

**Design**: Video chunks at CRF 23 are ~2-10MB per 1-min segment (depending on screen content). For robustness, implement simple resume by tracking bytes uploaded and using HTTP Range header for partial uploads.

**Verification**:
```bash
pytest tests/test_phase1_video_recorder.py::test_upload_resume -v
```

---

### Week 6 (Day 16-20): Gate Validation & Documentation

#### Day 16: Performance Optimization

**Focus**: Measure and optimize against performance gates

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 16.1 | Measure recording CPU overhead (<5% gate) | Manual + script |
| 16.2 | Optimize frame extraction batch processing | `openrecall/server/video/frame_extractor.py` |
| 16.3 | Measure end-to-end indexing (<60s per 1-min chunk gate) | Test script |
| 16.4 | Tune CRF/resolution if storage >50GB/day | Config tuning |

**Dependencies**: Full pipeline (Days 1-15)

**Performance Targets (from phase-gates.md)**:

| Metric | Target | Measurement |
|--------|--------|-------------|
| Recording CPU | <5% | `psutil.cpu_percent(interval=60)` over 1-hour recording |
| Frame Extraction | <2s per frame | `time.perf_counter()` on 100 frames |
| E2E Indexing | <60s per 1-min chunk | Timestamp: chunk complete → frame searchable |

---

#### Day 17: Quality Measurement

**Focus**: OCR accuracy and deduplication quality

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 17.1 | Create 100-frame curated test dataset (known text on screen) | `tests/fixtures/phase1_ocr_testset/` |
| 17.2 | Measure OCR character accuracy (≥95% gate) | Test script |
| 17.3 | Measure frame deduplication accuracy (<1% false negatives gate) | Test script |
| 17.4 | Measure 24-hour storage (<50GB/day gate) | Manual monitoring |

---

#### Day 18: Stability Review

**Focus**: Review 7-day test results, measure stability gates

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 18.1 | Collect 7-day stability test results (started Day 13) | Manual analysis |
| 18.2 | Zero-crash validation (gate) | Log analysis |
| 18.3 | Upload retry success rate (>99% gate) | Log analysis |
| 18.4 | Memory footprint analysis (<500MB gate) | psutil data |
| 18.5 | Fix any issues discovered | Various |

---

#### Day 19: Gate Validation Suite

**Focus**: Automated gate tests + validation report

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 19.1 | Write test_phase1_gates.py (1 test per gate) | `tests/test_phase1_gates.py` (new) |
| 19.2 | Run full gate suite | Terminal |
| 19.3 | Begin phase-1-validation.md with actual results | `v3/results/phase-1-validation.md` |

**Gate-to-Test Mapping**:
```
# Functional Gates
test_gate_1F01_recording_loop_stable
test_gate_1F02_frame_extraction_working
test_gate_1F03_ocr_indexed
test_gate_1F04_timeline_api_functional
test_gate_1F05_searchable

# Performance Gates
test_gate_1P01_frame_extraction_latency
test_gate_1P02_end_to_end_indexing
test_gate_1P03_recording_cpu_overhead

# Quality Gates
test_gate_1Q01_ocr_accuracy
test_gate_1Q02_frame_deduplication

# Stability Gates
test_gate_1S01_seven_day_continuous
test_gate_1S02_upload_retry_success

# Resource Gates
test_gate_1R01_storage_per_day
test_gate_1R02_memory_footprint

# Degradation Strategy
test_gate_1D01_ffmpeg_crash_recovery
test_gate_1D02_disk_full_handling
test_gate_1D03_ocr_slow_handling
test_gate_1D04_upload_failure_handling

# Data Governance
test_gate_1DG01_video_file_encryption
test_gate_1DG02_retention_policy_active
test_gate_1DG03_ocr_pii_detection_optional
```

---

#### Day 20: Documentation & Go/No-Go

**Focus**: Finalize all documentation, run final verification

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 20.1 | Finalize phase-1-validation.md with evidence | `v3/results/phase-1-validation.md` |
| 20.2 | Update roadmap-status.md (Phase 1 section) | `v3/milestones/roadmap-status.md` |
| 20.3 | Update phase-gates.md (Phase 1 gate statuses) | `v3/metrics/phase-gates.md` |
| 20.4 | Final full test suite run | `pytest tests/ -v` |
| 20.5 | Go/No-Go decision | Documentation |

---

## 5. Work Breakdown

| ID | Task | Purpose | Day | Dependencies | Target File(s) | Verification |
|----|------|---------|-----|--------------|-----------------|-------------|
| WB-01 | FFmpegManager | FFmpeg subprocess lifecycle, watchdog | 1 | None | `client/ffmpeg_manager.py` | `test_ffmpeg_start_stop` |
| WB-02 | VideoRecorder | Chunk rotation, metadata, enqueue | 2 | WB-01 | `client/video_recorder.py` | `test_chunk_rotation` |
| WB-03 | v3_002 migration | Add status to video_chunks | 3 | None | `migrations/v3_002_*.sql` | `test_migration_v3_002` |
| WB-04 | Upload API (video) | Accept video/mp4, store chunk | 3 | WB-03 | `server/api_v1.py`, `server/database/sql.py` | `test_video_upload_accepted` |
| WB-05 | FrameExtractor | FFmpeg frame extraction + dedup | 4 | WB-04 | `server/video/frame_extractor.py` | `test_frame_extraction` |
| WB-06 | Frame DB writes | INSERT frames + dedup logic | 4 | WB-05 | `server/database/sql.py` | `test_frames_in_db` |
| WB-07 | Recording→Frames E2E | Upload → extract → verify in DB | 5 | WB-01-06 | Tests | `test_upload_to_frames_e2e` |
| WB-08 | OCR pipeline | OCR on frames → ocr_text + FTS | 6 | WB-05 | `server/video/processor.py`, `database/sql.py` | `test_ocr_on_frames` |
| WB-09 | VideoProcessingWorker | Background chunk processing | 7 | WB-08 | `server/worker.py` | `test_video_worker` |
| WB-10 | Search extension | Query ocr_text_fts in search | 8 | WB-08 | `server/search/engine.py` | `test_search_video_ocr` |
| WB-11 | E2E pipeline | Record → search validation | 9 | WB-01-10 | Tests | `test_record_to_search_e2e` |
| WB-12 | Dual-mode recording | video/screenshot/auto + fallback | 10 | WB-01-02 | `client/recorder.py`, `shared/config.py` | `test_fallback` |
| WB-13 | Timeline API | GET /api/v1/timeline | 11 | WB-06 | `server/api_v1.py`, `database/sql.py` | `test_timeline_api` |
| WB-14 | Frame serving API | GET /api/v1/frames/:id | 12 | WB-13 | `server/api_v1.py` | `test_frame_serving` |
| WB-15 | RetentionWorker | Expire old data, delete files | 13 | WB-04, WB-06 | `server/retention.py`, `server/app.py` | `test_retention_cleanup` |
| WB-16 | Degradation handlers | FFmpeg crash, disk, OCR slow, network | 14 | WB-01, WB-08 | Multiple | `test_degradation_*` |
| WB-17 | Upload resume | Chunked upload, byte-level resume | 15 | WB-04 | `client/uploader.py` | `test_upload_resume` |
| WB-18 | Performance tuning | CPU, latency, storage optimization | 16 | WB-01-17 | Various | Benchmark scripts |
| WB-19 | Quality measurement | OCR accuracy, dedup accuracy | 17 | WB-08, WB-05 | Tests + fixtures | `test_ocr_accuracy` |
| WB-20 | Stability review | 7-day test analysis | 18 | WB-07 (started Day 13) | Analysis | Log review |
| WB-21 | Gate validation suite | 1 test per Phase 1 gate | 19 | WB-01-20 | `tests/test_phase1_gates.py` | `pytest -v` |
| WB-22 | Doc & Go/No-Go | Finalize docs, final run | 20 | WB-01-21 | Multiple docs | Full suite |

---

## 6. Gate Traceability Matrix

All gate criteria sourced exclusively from `/Users/pyw/newpart/MyRecall/v3/metrics/phase-gates.md`.

### Phase 1 Functional Gates

| Gate ID | Gate | Criteria (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| 1-F-01 | Recording Loop Stable | 1-hour continuous recording produces valid video chunks | WB-02 + WB-07: VideoRecorder + E2E test | 5, 16 |
| 1-F-02 | Frame Extraction Working | All frames extracted from video chunks and stored in DB | WB-05 + WB-06: FrameExtractor + DB writes | 4-5 |
| 1-F-03 | OCR Indexed | All extracted frames have OCR text in FTS database | WB-08: OCR pipeline + ocr_text_fts | 6-7 |
| 1-F-04 | Timeline API Functional | API returns correct frames for time range queries | WB-13: GET /api/v1/timeline | 11 |
| 1-F-05 | Searchable | Can search OCR text from video frames via search endpoint | WB-10: SearchEngine extension | 8-9 |

### Phase 1 Performance Gates

| Gate ID | Gate | Target (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| 1-P-01 | Frame Extraction Latency | <2 seconds per frame (average) | WB-05 + WB-18: FrameExtractor + tuning | 4, 16 |
| 1-P-02 | End-to-End Indexing | <60 seconds per 1-minute chunk | WB-09 + WB-18: Worker pipeline + tuning | 7, 16 |
| 1-P-03 | Recording CPU Overhead | <5% CPU during recording | WB-01 + WB-18: FFmpegManager + tuning | 1, 16 |

### Phase 1 Quality Gates

| Gate ID | Gate | Target (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| 1-Q-01 | OCR Accuracy | ≥95% character accuracy on video frames | WB-08 + WB-19: OCR pipeline + accuracy test | 6, 17 |
| 1-Q-02 | Frame Deduplication | <1% false negatives (missed changes) | WB-05 + WB-19: MSSIM dedup + accuracy test | 4, 17 |

### Phase 1 Stability Gates

| Gate ID | Gate | Criteria (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| 1-S-01 | 7-Day Continuous Run | Zero crashes over 7 days of continuous recording | WB-20: 7-day test (started Day 13) | 13-19 |
| 1-S-02 | Upload Retry Success | >99% upload success rate (including retries) | WB-17 + WB-20: Upload resume + measurement | 15, 18 |

### Phase 1 Resource Gates

| Gate ID | Gate | Target (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| 1-R-01 | Storage per Day | <50GB per day (24-hour recording) | WB-18: CRF tuning + measurement | 16-17 |
| 1-R-02 | Memory Footprint | <500MB RAM for VideoRecorder + uploader | WB-18 + WB-20: memory monitoring | 16, 18 |

### Phase 1 Degradation Strategy Gates

| Gate ID | Gate | Criteria (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| 1-D-01 | FFmpeg Crash | Auto-restart within 60s, log incident | WB-16 + WB-01: Watchdog in FFmpegManager | 1, 14 |
| 1-D-02 | Disk Full | Recording pauses, oldest chunks deleted | WB-16: Disk space check + FIFO cleanup | 14 |
| 1-D-03 | OCR Processing Slow | Reduce FPS to 1/10, skip deduplication | WB-16: Dynamic FPS adjustment | 14 |
| 1-D-04 | Upload Failure | Switch to local-only mode, retry hourly | WB-16: UploadQueue offline mode + consumer dispatch branch logs | 14 |

### Phase 1 Data Governance Gates

| Gate ID | Gate | Criteria (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| 1-DG-01 | Video File Encryption | Filesystem encryption (FileVault/LUKS) | Manual verification: check OS encryption status | 17 |
| 1-DG-02 | Retention Policy Active | Chunks >30 days auto-deleted | WB-15: RetentionWorker | 13 |
| 1-DG-03 | OCR PII Detection (Optional) | OCR text scanned for SSN/credit card patterns | WB-08 (optional): regex PII scanner | 6 (optional) |

**Total: 21 gates mapped (5F + 3P + 2Q + 2S + 2R + 4D + 3DG), all traced to phase-gates.md.**

---

## 7. Test & Verification Plan

### Test Files

| File | Gate Coverage | Day Created |
|------|-------------|-------------|
| `tests/test_phase1_video_recorder.py` | 1-F-01, 1-P-03, 1-D-01, WB-01-02, WB-17 | Day 1-2 |
| `tests/test_phase1_frame_extractor.py` | 1-F-02, 1-P-01, 1-Q-02, WB-05-07 | Day 4-5 |
| `tests/test_phase1_ocr_pipeline.py` | 1-F-03, 1-Q-01, WB-08-09 | Day 6-7 |
| `tests/test_phase1_timeline_api.py` | 1-F-04, WB-13-14 | Day 11-12 |
| `tests/test_phase1_search_integration.py` | 1-F-05, WB-10-11 | Day 8-9 |
| `tests/test_phase1_retention.py` | 1-DG-02, WB-15 | Day 13 |
| `tests/test_phase1_degradation.py` | 1-D-01 to 1-D-04, WB-12, WB-16 | Day 10, 14 |
| `tests/test_phase1_gates.py` | All 21 gates (comprehensive) | Day 19 |

### Verification Categories

#### Recording Verification

| Test | Assertion | Gate |
|------|-----------|------|
| 1-hour recording produces valid chunks | All chunks playable via FFmpeg | 1-F-01 |
| Chunk rotation works (1-min segments) | N chunks = ceil(duration/60) | 1-F-01 |
| Metadata JSON generated per chunk | All fields present and valid | WB-02 |
| Upload chunks reach server | video_chunks rows created | WB-04 |

#### Frame Extraction Verification

| Test | Assertion | Gate |
|------|-----------|------|
| Frames extracted at configured interval | ~12 frames per 1-min chunk (1/5s) | 1-F-02 |
| Frame dedup removes similar frames | Fewer stored than extracted | 1-Q-02 |
| Frame dedup keeps changed frames | <1% false negative rate | 1-Q-02 |
| Extraction <2s per frame average | perf_counter measurement | 1-P-01 |

#### OCR & Search Verification

| Test | Assertion | Gate |
|------|-----------|------|
| OCR text stored in ocr_text table | SELECT count matches frame count | 1-F-03 |
| OCR text indexed in FTS | MATCH query returns results | 1-F-03 |
| OCR accuracy ≥95% | Character-level comparison on test set | 1-Q-01 |
| Search finds video frame OCR text | /api/v1/search returns video frame result | 1-F-05 |
| E2E indexing <60s per 1-min chunk | Timestamp measurement | 1-P-02 |

#### Timeline & API Verification

| Test | Assertion | Gate |
|------|-----------|------|
| Timeline returns frames in time range | frame.timestamp within [start, end] | 1-F-04 |
| Timeline pagination works | limit/offset/has_more correct | 1-F-04 |
| Frame serving returns PNG | Content-Type: image/png, valid image | WB-14 |

#### Stability & Resource Verification

| Test | Assertion | Gate |
|------|-----------|------|
| 7-day zero crashes | Log analysis: no crash entries | 1-S-01 |
| Upload >99% success (24h) | success/total ratio | 1-S-02 |
| Recording CPU <5% | psutil.cpu_percent over 1h | 1-P-03 |
| Storage <50GB/day | disk_usage after 24h recording | 1-R-01 |
| Memory <500MB | psutil.memory_info().rss | 1-R-02 |

#### Degradation Verification

| Test | Assertion | Gate |
|------|-----------|------|
| Kill FFmpeg → restarts within 60s | Process restart timestamp delta | 1-D-01 |
| Fill disk → recording pauses, cleanup runs | Disk check + FIFO deletion | 1-D-02 |
| Simulate slow OCR → FPS reduced | Extraction interval increased | 1-D-03 |
| Simulate network down → local buffering | Queue grows, no upload attempts | 1-D-04 |

---

## 8. Risks / Failure Signals / Fallback

### Risk Matrix

| # | Risk | Probability | Impact | Trigger Signal | Mitigation | Fallback |
|---|------|-------------|--------|----------------|------------|----------|
| 1 | FFmpeg crashes >10/day | Medium | High | Watchdog restart count >10 in logs | Test FFmpeg with various screen content; use `-nostdin` flag | Abandon video recording, use screenshot-only mode |
| 2 | Frame extraction too slow (>10s/frame) | Low | High | 1-P-01 gate failure after optimization | Batch extraction, parallel processing, reduce resolution | Lower extraction FPS to 1/30s |
| 3 | OCR accuracy <90% on video frames | Medium | Medium | 1-Q-01 gate failure | Video frames may be blurrier than screenshots; test OCR on downscaled images | Increase extraction quality (lower CRF), use different OCR engine |
| 4 | Storage exceeds 50GB/day | High | Medium | 1-R-01 gate failure | CRF 23 on high-resolution screen produces large files | Increase CRF (23→28), reduce resolution, reduce FPS |
| 5 | CPU overhead >10% during recording | Medium | High | Recording doubles the 5% target | FFmpeg hardware encoding (VideoToolbox on macOS, VAAPI on Linux) | Reduce recording FPS (30→15→10) |
| 6 | Upload queue fills up (slow network) | Medium | Medium | Queue >50GB after 1 day | Chunks are 10-50MB each vs 0.1-1MB screenshots | Compress more aggressively, adaptive CRF based on queue depth |
| 7 | Disk fills during 7-day test | Medium | High | Disk <1GB free | 7 days x 50GB = 350GB without cleanup | Retention worker must be active; set retention to 3 days for test |
| 8 | macOS screen recording permission issues | Medium | Medium | FFmpeg produces blank/black frames | Check permission at startup, warn user | Fallback to mss screenshot mode |

### Failure Signals (from phase-gates.md)

| Signal | Threshold | Action |
|--------|-----------|--------|
| FFmpeg crashes >10 times/day in 7-day test | Abandon FFmpeg, evaluate PyAV or opencv | ADR-000X documenting the decision |
| Frame extraction cannot keep up with 1/10 FPS | Optimize pipeline or reduce FPS further | Profile bottleneck, consider Rust sidecar (ADR-0001 sequence) |
| Storage exceeds 50GB/day after CRF tuning | Increase CRF (28→32) or reduce resolution | Document compression tradeoff |

---

## 9. Deliverables Checklist

### Code Files (New)

- [ ] `openrecall/client/ffmpeg_manager.py`
- [ ] `openrecall/client/video_recorder.py`
- [ ] `openrecall/server/video/__init__.py`
- [ ] `openrecall/server/video/frame_extractor.py`
- [ ] `openrecall/server/video/processor.py`
- [ ] `openrecall/server/retention.py`
- [ ] `openrecall/server/database/migrations/v3_002_add_video_chunk_status.sql`

### Code Files (Modified)

- [ ] `openrecall/server/api_v1.py` — Timeline API, frame serving, video upload
- [ ] `openrecall/server/worker.py` — Video chunk processing integration
- [ ] `openrecall/server/search/engine.py` — Query ocr_text_fts
- [ ] `openrecall/server/database/sql.py` — v3 table CRUD methods
- [ ] `openrecall/server/app.py` — RetentionWorker startup
- [ ] `openrecall/shared/config.py` — Video recording configuration
- [ ] `openrecall/client/recorder.py` — Dual-mode + fallback logic
- [ ] `openrecall/client/uploader.py` — Upload resume for large files

### Test Files (New)

- [ ] `tests/test_phase1_video_recorder.py`
- [ ] `tests/test_phase1_frame_extractor.py`
- [ ] `tests/test_phase1_ocr_pipeline.py`
- [ ] `tests/test_phase1_timeline_api.py`
- [ ] `tests/test_phase1_search_integration.py`
- [ ] `tests/test_phase1_retention.py`
- [ ] `tests/test_phase1_degradation.py`
- [ ] `tests/test_phase1_gates.py`

### Documentation Files

- [ ] `v3/plan/03-phase-1-detailed-plan.md` (this file)
- [ ] `v3/results/phase-1-validation.md` (template, finalized Day 20)
- [ ] `v3/milestones/roadmap-status.md` (Phase 1 section updated)
- [ ] `v3/metrics/phase-gates.md` (Phase 1 statuses updated at Go/No-Go)

---

## 10. Historical Execution Readiness Snapshot (Completed)

1. [x] Phase 0 complete and baseline frozen (v3-phase0-go tag confirmed)
2. [x] FFmpeg installed and functional on development machine (`ffmpeg -version`)
3. [x] Screen recording permission granted (macOS: System Preferences → Privacy)
4. [x] Development environment: Python 3.10+, pytest, psutil available
5. [x] Phase 0 test suite still passes (`pytest tests/test_phase0_*.py -v`)
6. [x] Sufficient disk space for 7-day stability test (~150-350GB available)
7. [x] This plan reviewed and approved by Product Owner
8. [x] No conflicting changes in progress on the codebase
9. [x] Phase 1 Git branch created from Phase 0 baseline
10. [x] Day 1 tasks (FFmpegManager) had no external dependencies and started immediately

---

## 11. Last Updated

**Date**: 2026-02-07
**Author**: Chief Architect + Planning Agent
**Status**: Executed (Engineering Complete; long-run evidence pending)
**Next Review**: After long-run evidence collection (7-day stability + 24h resource measurements)
