# MyRecall-v3 Phase 0 Detailed Plan

**Version**: 1.0
**Last Updated**: 2026-02-06
**Status**: Ready to Execute
**Timeline**: Week 1-2 (Day 1-10, 2026-02-06 to 2026-02-19)
**Owner**: Solo Developer

---

## 1. Goal

**Objective**: Establish the database schema, API versioning, upload queue, configuration matrix, and data governance foundation that all subsequent phases (1-5) depend on.

**Business Value**: Phase 0 creates the "rails" for multi-modal capture (video + audio) without implementing capture itself, and ensures every component is designed for the eventual Phase 5 remote deployment from day one.

**Non-Goals**:
- **No video/audio recording** -- recording is Phase 1/2
- **No OCR/Whisper processing** -- processing pipeline changes are Phase 1/2
- **No search changes** -- existing hybrid search continues as-is
- **No Web UI changes** -- UI is unchanged in Phase 0
- **No actual authentication enforcement** -- only placeholder decorator (real auth is Phase 5)
- **No Docker/containerization** -- containerization is Phase 5.2
- **No new AI provider integration** -- existing provider chain unchanged
- **No LanceDB schema changes** -- vector store remains untouched; new FTS tables are for future phases

---

## 2. Scope

### In-Scope

- [ ] Design: v3 database schema (5 new tables + schema_version + governance columns)
- [ ] Design: Migration script (forward) with idempotency
- [ ] Design: Rollback script with integrity verification
- [ ] Design: Pydantic models for all new entities + pagination wrapper
- [ ] Design: `/api/v1/*` blueprint with backward-compatible `/api/*` aliases
- [ ] Design: Auth placeholder decorator on all v1 routes
- [ ] Design: Pagination (`limit`/`offset`) on all list endpoints
- [ ] Design: Upload queue (ADR-0002: 100GB capacity, 7-day TTL, FIFO, backoff)
- [ ] Design: Configuration matrix (4 deployment modes)
- [ ] Design: Data governance foundation (PII policy, encryption schema, retention)
- [ ] Design: Comprehensive test suite for all Phase 0 gates

### Out-of-Scope

- Video/audio capture implementation (Phase 1/2)
- Search pipeline modifications (Phase 3)
- Chat functionality (Phase 4)
- Docker, TLS, real auth enforcement (Phase 5)
- Streaming (Phase 6)
- Memory capabilities (Phase 7)

---

## 3. Inputs / Outputs

### Inputs (Prerequisites)

| Input | Source | Status |
|-------|--------|--------|
| Existing v2 codebase | `/Users/pyw/new/MyRecall/openrecall/` | Available |
| Existing recall.db schema (`entries` table) | `~/MRS/db/recall.db` | Available |
| Existing FTS schema (`ocr_fts` in fts.db) | `~/MRS/fts.db` | Available |
| Existing LanceDB store | `~/MRS/lancedb/` | Available |
| screenpipe reference schema | `/Users/pyw/new/screenpipe/crates/screenpipe-db/` | Read-only reference |
| ADR-0001 (Python-first) | `v3/decisions/ADR-0001-python-first.md` | Approved |
| ADR-0002 (Thin client) | `v3/decisions/ADR-0002-thin-client-architecture.md` | Approved |
| Phase gates (authority) | `v3/metrics/phase-gates.md` | Approved |

### Outputs (Deliverables for Phase 1+)

| Output | Consumer | Purpose |
|--------|----------|---------|
| v3 DB schema (5 new tables) | Phase 1 (VideoRecorder), Phase 2 (AudioRecorder) | Store video/audio data |
| `/api/v1/*` routes with pagination | Phase 3 (Search), Phase 4 (Chat), Phase 5 (Remote) | Remote-first API surface |
| Auth placeholder decorator | Phase 5 (enforce real auth) | API security foundation |
| Upload queue (ADR-0002) | Phase 1 (video upload), Phase 2 (audio upload), Phase 5 (remote upload) | Resilient upload pipeline |
| Configuration matrix | Phase 5 (deployment migration) | Multi-mode deployment |
| Migration/rollback scripts | All phases | Schema evolution safety net |
| Phase 0 gate validation report | Phase 1 Go/No-Go decision | Evidence of foundation readiness |

---

## 4. Day-by-Day Plan (Week 1-2, 10 Days)

### Execution Tracks

```
Track A (Schema & Models):   Day 1 ████ Day 2 ████ Day 3 ████ Day 4 ████
Track B (API & Queue):                            Day 3 ██── Day 4 ──██ Day 5 ████ Day 6 ████ Day 7 ████
Track C (Config & Governance):                                          Day 5 ██── Day 6 ──██ Day 7 ████ Day 8 ████ Day 9 ████ Day 10 ████
```

### Day 1: Schema Design & Migration Script (Forward)

**Focus**: Create v3 SQL schema and migration runner

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 1.1 | Design v3 SQL DDL (5 tables + schema_version + indexes + FTS) | `openrecall/server/database/migrations/v3_001_add_multimodal_tables.sql` (new) |
| 1.2 | Write migration runner (apply SQL, measure time/memory) | `openrecall/server/database/migrations/runner.py` (new) |
| 1.3 | Add governance columns to existing `entries` table (ALTER TABLE) | Included in migration SQL |

**Dependencies**: None (greenfield)

**Details - Task 1.1 (Schema DDL)**:

New tables adapted from screenpipe base schema with MyRecall governance additions:

```sql
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);

-- Video chunks (populated in Phase 1)
CREATE TABLE IF NOT EXISTS video_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    device_name TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT,                    -- Retention policy (DG-03)
    encrypted INTEGER DEFAULT 0,       -- Encryption placeholder (DG-02)
    checksum TEXT                       -- SHA256 for integrity
);

-- Frames (populated in Phase 1)
CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_chunk_id INTEGER NOT NULL,
    offset_index INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    app_name TEXT DEFAULT '',
    window_name TEXT DEFAULT '',
    focused INTEGER DEFAULT 0,
    browser_url TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (video_chunk_id) REFERENCES video_chunks(id) ON DELETE CASCADE
);

-- OCR text for frames (populated in Phase 1)
CREATE TABLE IF NOT EXISTS ocr_text (
    frame_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_json TEXT,
    ocr_engine TEXT DEFAULT '',
    text_length INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE
);

-- Audio chunks (populated in Phase 2)
CREATE TABLE IF NOT EXISTS audio_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    timestamp REAL NOT NULL,
    device_name TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT,
    encrypted INTEGER DEFAULT 0,
    checksum TEXT
);

-- Audio transcriptions (populated in Phase 2)
CREATE TABLE IF NOT EXISTS audio_transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audio_chunk_id INTEGER NOT NULL,
    offset_index INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    transcription TEXT NOT NULL,
    transcription_engine TEXT DEFAULT '',
    speaker_id INTEGER,               -- NULL if Phase 2.1 not implemented (ADR-0004)
    start_time REAL,
    end_time REAL,
    text_length INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (audio_chunk_id) REFERENCES audio_chunks(id) ON DELETE CASCADE
);
```

Indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_frames_video_chunk_id ON frames(video_chunk_id);
CREATE INDEX IF NOT EXISTS idx_frames_timestamp ON frames(timestamp);
CREATE INDEX IF NOT EXISTS idx_frames_app_name ON frames(app_name);
CREATE INDEX IF NOT EXISTS idx_frames_timestamp_offset ON frames(timestamp, offset_index);
CREATE INDEX IF NOT EXISTS idx_ocr_text_frame_id ON ocr_text(frame_id);
CREATE INDEX IF NOT EXISTS idx_audio_transcriptions_chunk_id ON audio_transcriptions(audio_chunk_id);
CREATE INDEX IF NOT EXISTS idx_audio_transcriptions_timestamp ON audio_transcriptions(timestamp);
CREATE INDEX IF NOT EXISTS idx_audio_transcriptions_chunk_ts ON audio_transcriptions(audio_chunk_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_video_chunks_created_at ON video_chunks(created_at);
CREATE INDEX IF NOT EXISTS idx_audio_chunks_created_at ON audio_chunks(created_at);
```

FTS virtual tables (for future Phase 1/2 writes):

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(
    text, app_name, window_name,
    frame_id UNINDEXED,
    tokenize='unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS audio_transcriptions_fts USING fts5(
    transcription, device,
    audio_chunk_id UNINDEXED, speaker_id UNINDEXED,
    tokenize='unicode61'
);
```

Governance columns on existing `entries` table:

```sql
ALTER TABLE entries ADD COLUMN created_at TEXT DEFAULT '';
ALTER TABLE entries ADD COLUMN expires_at TEXT DEFAULT '';

-- Backfill created_at from timestamp
UPDATE entries SET created_at = datetime(timestamp, 'unixepoch') WHERE created_at = '';
```

**Details - Task 1.2 (Migration Runner)**:

- Accept a SQLite DB path or connection
- Check/create `schema_version` table
- Read applied versions, apply unapplied `.sql` files in version order
- Compute SHA256 of `entries` data before and after migration
- Measure elapsed time via `time.perf_counter()` and peak memory via `psutil`
- Abort if elapsed > 5s for 10K entries or peak memory > 500MB

**Verification**:
```bash
pytest tests/test_phase0_migration.py::test_migration_creates_all_tables -v
pytest tests/test_phase0_migration.py::test_migration_performance_10k -v
```

---

### Day 2: Rollback Script & Integrity Verification

**Focus**: Build rollback mechanism and checksum verification

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 2.1 | Write rollback script (drop v3 tables, rebuild entries without governance cols) | `openrecall/server/database/migrations/rollback.py` (new) |
| 2.2 | Write checksum verification utility (SHA256 of entries data) | `openrecall/server/database/migrations/integrity.py` (new) |
| 2.3 | Write migration + rollback integration tests | `tests/test_phase0_migration.py` (new) |

**Dependencies**: Day 1

**Details - Task 2.1 (Rollback)**:
1. Drop v3-only tables: `video_chunks`, `frames`, `ocr_text` (new), `audio_chunks`, `audio_transcriptions`, `ocr_text_fts`, `audio_transcriptions_fts`, `schema_version`
2. Remove `created_at`/`expires_at` from `entries` via SQLite table rebuild (CREATE new → INSERT → DROP old → RENAME)
3. Verify `entries` row count matches pre-rollback count
4. Gate: rollback completes in <2 minutes

**Details - Task 2.2 (Integrity)**:
- `compute_entries_checksum(conn) -> str`: SHA256 of all rows serialized as `id|timestamp|app|title|text|status`
- `save_checksum(checksum, path)` / `verify_checksum(conn, path) -> bool`

**Details - Task 2.3 (Tests)**:
- `test_migration_creates_all_tables` -- 7 new tables exist
- `test_migration_idempotent` -- run twice, no errors
- `test_migration_preserves_entries` -- 100 entries intact after migration
- `test_rollback_restores_original` -- only original tables remain after rollback
- `test_migration_performance_10k` -- <5s for 10K entries
- `test_migration_memory_under_500mb` -- peak RSS check
- `test_schema_overhead_under_10mb` -- DB file size delta

**Verification**:
```bash
pytest tests/test_phase0_migration.py -v
```

---

### Day 3: Pydantic Models for v3 Entities

**Focus**: Define data models for all new DB entities

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 3.1 | Add VideoChunk, Frame, OcrText, AudioChunk, AudioTranscription models | `openrecall/shared/models.py` (extend) |
| 3.2 | Add PaginatedResponse generic wrapper (ADR-0002) | `openrecall/shared/models.py` (extend) |
| 3.3 | Write model unit tests | `tests/test_phase0_models.py` (new) |

**Dependencies**: None (models are standalone)

**Interface Changes**:

```python
# New models added to openrecall/shared/models.py

class VideoChunk(BaseModel):
    id: int | None = None
    file_path: str
    device_name: str = ""
    created_at: str = ""
    expires_at: str | None = None
    encrypted: int = 0
    checksum: str | None = None

class Frame(BaseModel):
    id: int | None = None
    video_chunk_id: int
    offset_index: int
    timestamp: float
    app_name: str = ""
    window_name: str = ""
    focused: bool = False
    browser_url: str = ""
    created_at: str = ""

class OcrText(BaseModel):
    frame_id: int
    text: str
    text_json: str | None = None
    ocr_engine: str = ""
    text_length: int | None = None
    created_at: str = ""

class AudioChunk(BaseModel):
    id: int | None = None
    file_path: str
    timestamp: float
    device_name: str = ""
    created_at: str = ""
    expires_at: str | None = None
    encrypted: int = 0
    checksum: str | None = None

class AudioTranscription(BaseModel):
    id: int | None = None
    audio_chunk_id: int
    offset_index: int
    timestamp: float
    transcription: str
    transcription_engine: str = ""
    speaker_id: int | None = None       # Nullable per ADR-0004
    start_time: float | None = None
    end_time: float | None = None
    text_length: int | None = None
    created_at: str = ""

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool
```

**Verification**:
```bash
pytest tests/test_phase0_models.py -v
```

---

### Day 4: API v1 Blueprint & Auth Placeholder

**Focus**: Create versioned API with remote-first design

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 4.1 | Create `/api/v1` Flask blueprint (re-export existing endpoints + pagination) | `openrecall/server/api_v1.py` (new) |
| 4.2 | Create auth placeholder decorator | `openrecall/server/auth.py` (new) |
| 4.3 | Register v1 blueprint in app.py (keep legacy `/api` intact) | `openrecall/server/app.py` (modify) |
| 4.4 | Write API v1 tests | `tests/test_phase0_api_v1.py` (new) |

**Dependencies**: Day 3 (PaginatedResponse model)

**Details - Task 4.1 (v1 Blueprint)**:

New blueprint at `/api/v1` re-exports all existing endpoints with enhancements:
- Pagination params (`limit`, `offset`) on: `/memories/recent`, `/memories/latest`, `/search`
- Response envelope: `{ "data": [...], "meta": { "total": N, "limit": L, "offset": O, "has_more": bool } }`
- All routes decorated with `@require_auth`
- Stateless: no server-side session usage (v2 is already stateless -- document explicitly)

**Details - Task 4.2 (Auth Placeholder)**:

```python
def require_auth(f):
    """Phase 0: Always passes. Phase 5: Enforce API key / JWT."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # TODO Phase 5: Check Authorization header
        return f(*args, **kwargs)
    return decorated
```

**Details - Task 4.3 (Blueprint Registration)**:

In `app.py`, register both blueprints:
```python
app.register_blueprint(api_bp)          # Legacy /api/* (unchanged)
app.register_blueprint(api_v1_bp)       # New /api/v1/*
```

**Verification**:
```bash
pytest tests/test_phase0_api_v1.py -v
# Verify: GET /api/v1/health -> 200
# Verify: GET /api/health -> 200 (backward compat)
# Verify: GET /api/v1/memories/recent?limit=10&offset=0 -> paginated response
# Verify: POST /api/v1/upload -> 202 (multipart still works)
```

---

### Day 5: Upload Queue (ADR-0002 Compliance)

**Focus**: Upgrade client upload buffer to meet all 5 upload queue gates

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 5.1 | Create UploadQueue class (wraps LocalBuffer with capacity/TTL/FIFO/backoff) | `openrecall/client/upload_queue.py` (new) |
| 5.2 | Update UploaderConsumer backoff to ADR-0002 schedule | `openrecall/client/consumer.py` (modify) |
| 5.3 | Write upload queue tests (all 5 gates) | `tests/test_phase0_upload_queue.py` (new) |

**Dependencies**: Existing `openrecall/client/buffer.py` (LocalBuffer)

**Details - Task 5.1 (UploadQueue)**:

Key parameters per ADR-0002:

| Parameter | Value |
|-----------|-------|
| Max capacity | 100 GB |
| TTL | 7 days |
| Deletion policy | FIFO (oldest first) |
| Post-upload behavior | Immediate deletion |
| Retry backoff | `[60, 300, 900, 3600, 21600]` seconds |

**Details - Task 5.2 (Backoff Update)**:

Replace current `min(2 ** retry_count, 60)` in `consumer.py` with `UploadQueue.get_backoff_delay(retry_count)` using the ADR-0002 schedule.

**Verification**:
```bash
pytest tests/test_phase0_upload_queue.py -v
# Verify: test_capacity_enforcement_fifo
# Verify: test_ttl_cleanup_7_days
# Verify: test_fifo_deletion_order
# Verify: test_post_upload_deletion_timing (<1s)
# Verify: test_exponential_backoff_schedule ([60, 300, 900, 3600, 21600])
```

---

### Day 6: Configuration Matrix (4 Deployment Modes)

**Focus**: Support local/remote/debian_client/debian_server configurations

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 6.1 | Add `deployment_mode` field to Settings | `openrecall/shared/config.py` (modify) |
| 6.2 | Create deployment presets module | `openrecall/shared/config_presets.py` (new) |
| 6.3 | Create template .env files for each mode | `config/{local,remote,debian_client,debian_server}.env` (new) |
| 6.4 | Write config matrix tests | `tests/test_phase0_config_matrix.py` (new) |

**Dependencies**: None

**Configuration Matrix**:

| Setting | `local` | `remote` | `debian_client` | `debian_server` |
|---------|---------|----------|-----------------|-----------------|
| `host` | `127.0.0.1` | `127.0.0.1` | N/A (client) | `0.0.0.0` |
| `api_url` | `http://localhost:{port}/api` | `http://{remote}:{port}/api` | `http://{remote}:{port}/api` | N/A (server) |
| Runs server? | Yes | Yes | No | Yes |
| Runs client? | Yes | Yes | Yes | No |
| Data dirs | `~/MRS` + `~/MRC` | `~/MRS` + `~/MRC` | `~/MRC` only | `~/MRS` only |

**Verification**:
```bash
pytest tests/test_phase0_config_matrix.py -v
# Verify: local defaults
# Verify: debian_server binds 0.0.0.0
# Verify: debian_client has no server dirs
# Verify: all 4 env files load without error
# Verify: no DEPLOYMENT_MODE set -> defaults to local (backward compat)
```

---

### Day 7: Data Governance Foundation

**Focus**: Satisfy all 4 Phase 0 data governance gates

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 7.1 | Write PII Classification Policy document | `v3/results/pii-classification-policy.md` (new) |
| 7.2 | Write Retention Policy Design document | `v3/results/retention-policy-design.md` (new) |
| 7.3 | Verify encryption schema in migration SQL (already done Day 1) | Review only |
| 7.4 | Verify auth placeholder on all v1 routes (already done Day 4) | Review only |
| 7.5 | Add governance column existence tests | `tests/test_phase0_migration.py` (extend) |

**Dependencies**: Days 1, 4

**Details - Task 7.1 (PII Policy)**:

| PII Category | Data Source | Sensitivity | Phase | Detection Strategy |
|---|---|---|---|---|
| Screen text (names, emails, SSN) | OCR | High | Phase 1 | Regex patterns (future) |
| Application credentials | OCR (browser/terminal) | Critical | Phase 1 | Pattern matching (future) |
| Audio speech content | Whisper transcription | High | Phase 2 | Encryption at rest |
| Speaker identity | Diarization | Medium | Phase 2.1 | Opt-in only (ADR-0004) |
| Facial images in frames | Video frames | High | Phase 1 | No face storage policy |
| App usage patterns | Frame metadata | Low | Phase 0+ | Retention policy |

**Details - Task 7.2 (Retention Policy Design)**:

- All tables include `created_at` (auto-populated via DEFAULT)
- `expires_at` nullable; when set, background cleanup job deletes expired rows
- Default retention: 30 days (configurable via `OPENRECALL_RETENTION_DAYS`)
- Cleanup scheduled as part of ProcessingWorker (future Phase 1/2)
- Phase 5 adds server-side enforcement; Phase 0 only ensures schema supports it

**Verification**:
```bash
pytest tests/test_phase0_migration.py::test_governance_columns_exist -v
# Manual review: pii-classification-policy.md covers all 6 categories
# Manual review: retention-policy-design.md documents the mechanism
```

---

### Day 8: Backward Compatibility & Integration Testing

**Focus**: Verify existing v2 pipeline works 100% after all Phase 0 changes

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 8.1 | Write full pipeline integration test (upload -> query -> search) | `tests/test_phase0_backward_compat.py` (new) |
| 8.2 | Benchmark query overhead (<10ms gate) | `tests/test_phase0_backward_compat.py` (extend) |
| 8.3 | Update conftest.py to run migration in test fixture | `tests/conftest.py` (modify) |
| 8.4 | Run entire existing test suite -- all must pass | Existing `tests/` |

**Dependencies**: Days 1-7 (all code complete)

**Details - Task 8.1**:

End-to-end test simulating full v2 workflow on migrated DB:
1. Upload screenshot via `POST /api/upload` -> verify 202
2. Verify `entries` table has PENDING row
3. Query `/api/memories/recent` -> verify entry returned
4. Query `/api/v1/memories/recent` -> verify same data with pagination envelope
5. Query `/api/health` and `/api/v1/health` -> both 200

**Details - Task 8.2**:

Benchmark approach:
1. Create DB with 1000 entries (non-migrated)
2. Run `/api/search?q=test` 100 times, record baseline median
3. Run migration
4. Run same 100 queries, record post-migration median
5. Assert difference < 10ms

**Verification**:
```bash
pytest tests/ -v --tb=short
# ALL existing tests must pass
pytest tests/test_phase0_backward_compat.py -v
```

---

### Day 9: Gate Validation Suite

**Focus**: Run every Phase 0 gate, record results

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 9.1 | Write comprehensive gate validation test file (1 test per gate) | `tests/test_phase0_gates.py` (new) |
| 9.2 | Run full gate suite, capture output | Terminal |
| 9.3 | Begin filling Phase 0 validation report | `v3/results/phase-0-validation.md` |

**Dependencies**: Days 1-8

**Gate-to-Test mapping** (see Gate Traceability Matrix in Section 7 below for complete list):

```
test_gate_F01_schema_migration_success
test_gate_F02_backward_compatibility
test_gate_F03_api_versioning
test_gate_F04_configuration_matrix
test_gate_P01_migration_latency
test_gate_P02_query_overhead
test_gate_S01_data_integrity
test_gate_S02_rollback_success
test_gate_R01_migration_memory
test_gate_R02_schema_overhead
test_gate_DG01_pii_classification_policy
test_gate_DG02_encryption_schema
test_gate_DG03_retention_policy
test_gate_DG04_auth_placeholder
test_gate_UQ01_buffer_capacity
test_gate_UQ02_ttl_cleanup
test_gate_UQ03_fifo_deletion
test_gate_UQ04_post_upload_deletion
test_gate_UQ05_retry_backoff
```

**Verification**:
```bash
pytest tests/test_phase0_gates.py -v
```

---

### Day 10: Documentation, Cleanup & Go/No-Go Review

**Focus**: Finalize all documentation, run final verification

| Task | Description | Target File(s) |
|------|-------------|-----------------|
| 10.1 | Update roadmap-status.md -- mark Phase 0 items complete | `v3/milestones/roadmap-status.md` |
| 10.2 | Update phase-gates.md -- mark Phase 0 gates with status | `v3/metrics/phase-gates.md` |
| 10.3 | Finalize phase-0-validation.md with actual results | `v3/results/phase-0-validation.md` |
| 10.4 | Code review: docstrings, type hints, no hardcoded paths | All new files |
| 10.5 | Final full test suite run | `pytest tests/ -v` |

**Dependencies**: Days 1-9

**Verification**:
```bash
# Final green run
pytest tests/ -v --tb=short
# Verify all 19 gate tests pass
pytest tests/test_phase0_gates.py -v
```

---

## 5. Work Breakdown

### Summary Table

| ID | Task | Purpose | Day | Dependencies | Target File(s) | Verification |
|----|------|---------|-----|--------------|-----------------|-------------|
| WB-01 | Schema DDL | Create 5 new tables + schema_version + governance cols | 1 | None | `migrations/v3_001_add_multimodal_tables.sql` | SQL syntax check |
| WB-02 | Migration runner | Apply migrations with timing/memory checks | 1 | WB-01 | `migrations/runner.py` | `test_migration_creates_all_tables` |
| WB-03 | Rollback script | Reverse migration, restore original state | 2 | WB-01 | `migrations/rollback.py` | `test_rollback_restores_original` |
| WB-04 | Integrity util | SHA256 checksum for zero-data-loss | 2 | WB-02 | `migrations/integrity.py` | `test_gate_S01_data_integrity` |
| WB-05 | Migration tests | Migration/rollback integration tests | 2 | WB-01-04 | `tests/test_phase0_migration.py` | `pytest -v` |
| WB-06 | Pydantic models | VideoChunk, Frame, AudioChunk, AudioTranscription, OcrText | 3 | None | `shared/models.py` | `test_phase0_models.py` |
| WB-07 | PaginatedResponse | Generic pagination wrapper (ADR-0002) | 3 | None | `shared/models.py` | `test_phase0_models.py` |
| WB-08 | v1 Blueprint | `/api/v1/*` routes with pagination | 4 | WB-07 | `server/api_v1.py` | `test_phase0_api_v1.py` |
| WB-09 | Auth placeholder | `@require_auth` decorator | 4 | None | `server/auth.py` | `test_auth_decorator_passes` |
| WB-10 | Blueprint registration | Register v1 in app.py, keep legacy | 4 | WB-08 | `server/app.py` | `test_legacy_still_works` |
| WB-11 | UploadQueue | ADR-0002 compliant queue | 5 | None | `client/upload_queue.py` | `test_phase0_upload_queue.py` |
| WB-12 | Backoff update | Replace consumer backoff schedule | 5 | WB-11 | `client/consumer.py` | `test_exponential_backoff_schedule` |
| WB-13 | Config matrix | 4 deployment modes in Settings | 6 | None | `shared/config.py`, `shared/config_presets.py` | `test_phase0_config_matrix.py` |
| WB-14 | Env templates | Template .env per mode | 6 | WB-13 | `config/*.env` | `test_all_modes_loadable` |
| WB-15 | PII policy doc | Define PII categories and handling | 7 | None | `v3/results/pii-classification-policy.md` | Manual review |
| WB-16 | Retention design doc | Document retention mechanism | 7 | WB-01 | `v3/results/retention-policy-design.md` | Manual review |
| WB-17 | Backward compat tests | Full v2 pipeline on migrated DB | 8 | WB-01-10 | `tests/test_phase0_backward_compat.py` | `pytest -v` |
| WB-18 | Query overhead bench | Measure <10ms delta | 8 | WB-17 | `tests/test_phase0_backward_compat.py` | `pytest -m perf` |
| WB-19 | Gate validation suite | 1 test per Phase 0 gate | 9 | WB-01-18 | `tests/test_phase0_gates.py` | `pytest -v` |
| WB-20 | Validation report | Fill phase-0-validation.md | 9-10 | WB-19 | `v3/results/phase-0-validation.md` | Manual review |
| WB-21 | Doc cleanup & Go/No-Go | Update roadmap, phase-gates, final run | 10 | WB-01-20 | Multiple docs | `pytest tests/ -v` |

---

## 6. Interface / Model Changes Summary

### Database Changes

| Change | Table | Type | Notes |
|--------|-------|------|-------|
| New table | `schema_version` | CREATE | Migration version tracking |
| New table | `video_chunks` | CREATE | Phase 1 data container |
| New table | `frames` | CREATE | Phase 1 data container |
| New table | `ocr_text` (new) | CREATE | Phase 1 data container (separate from legacy `ocr_fts`) |
| New table | `audio_chunks` | CREATE | Phase 2 data container |
| New table | `audio_transcriptions` | CREATE | Phase 2 data container |
| New FTS | `ocr_text_fts` | CREATE VIRTUAL | Future Phase 1 full-text search |
| New FTS | `audio_transcriptions_fts` | CREATE VIRTUAL | Future Phase 2 full-text search |
| ALTER | `entries` | ADD COLUMN `created_at`, `expires_at` | Governance (retention policy) |

### API Changes

| Endpoint | Change | Notes |
|----------|--------|-------|
| `GET /api/v1/health` | New | Mirrors `/api/health` |
| `POST /api/v1/upload` | New | Mirrors `/api/upload` with auth |
| `GET /api/v1/search` | New | Adds `limit`/`offset` pagination |
| `GET /api/v1/memories/recent` | New | Adds `limit`/`offset` pagination |
| `GET /api/v1/memories/latest` | New | Adds `limit`/`offset` pagination |
| `GET /api/v1/queue/status` | New | Mirrors `/api/queue/status` |
| `GET /api/v1/config` | New | Mirrors `/api/config` |
| `POST /api/v1/config` | New | Mirrors `/api/config` |
| `POST /api/v1/heartbeat` | New | Mirrors `/api/heartbeat` |
| All `/api/*` | Unchanged | Backward compatibility preserved |

### Config Changes

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `OPENRECALL_DEPLOYMENT_MODE` | str | `"local"` | New: `local`/`remote`/`debian_client`/`debian_server` |

---

## 7. Gate Traceability Matrix

All gate criteria sourced exclusively from `/Users/pyw/new/MyRecall/v3/metrics/phase-gates.md` (authority).

### Data Governance Gates (DG)

| Gate ID | Gate | Criteria (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| DG-01 | PII Classification Policy | Document defines PII categories (screen text, audio, faces) | WB-15: `pii-classification-policy.md` | 7 |
| DG-02 | Encryption Schema Design | Database schema supports encryption fields | WB-01: `encrypted` column on `video_chunks`, `audio_chunks` | 1 |
| DG-03 | Retention Policy Design | Schema includes `created_at`, `expires_at` fields | WB-01 + WB-16: DDL + `retention-policy-design.md` | 1, 7 |
| DG-04 | API Authentication Placeholder | API routes include auth decorator (even if localhost) | WB-09: `@require_auth` on all v1 routes | 4 |

### Upload Queue Buffer Gates (UQ)

| Gate ID | Gate | Criteria (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| UQ-01 | Buffer Capacity Enforcement | Client respects 100GB max; oldest deleted (FIFO) | WB-11: `UploadQueue._enforce_capacity()` | 5 |
| UQ-02 | TTL Cleanup | Chunks >7 days auto-deleted | WB-11: `UploadQueue.cleanup_expired()` | 5 |
| UQ-03 | FIFO Deletion | Oldest chunks deleted first when capacity reached | WB-11: FIFO sort in `_enforce_capacity()` | 5 |
| UQ-04 | Post-Upload Deletion | Successful upload deletes local copy within 1s | WB-11: `commit()` timing | 5 |
| UQ-05 | Retry Exponential Backoff | Delays: 1min -> 5min -> 15min -> 1h -> 6h | WB-12: `get_backoff_delay()` in consumer.py | 5 |

### Functional Gates (F)

| Gate ID | Gate | Criteria (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| F-01 | Schema Migration Success | All new tables created (video_chunks, frames, ocr_text, audio_chunks, audio_transcriptions) | WB-01 + WB-02: DDL + runner | 1 |
| F-02 | Backward Compatibility | Existing screenshot pipeline 100% functional after migration | WB-17: integration test (upload -> search) | 8 |
| F-03 | API Versioning | `/api/v1/*` routes functional, `/api/*` aliases work | WB-08 + WB-10: v1 blueprint + registration | 4 |
| F-04 | Configuration Matrix | All 4 deployment modes configurable | WB-13 + WB-14: Settings + presets + env files | 6 |

### Performance Gates (P)

| Gate ID | Gate | Target (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| P-01 | Migration Latency | <5 seconds for 10K entries | WB-02: runner with timing check | 1, 9 |
| P-02 | Query Overhead | Schema changes add <10ms to typical queries | WB-18: benchmark before/after migration | 8, 9 |

### Stability Gates (S)

| Gate ID | Gate | Criteria (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| S-01 | Data Integrity | Zero data loss during migration (SHA256 checksum) | WB-04: `integrity.py` checksum verification | 2, 9 |
| S-02 | Rollback Success | Rollback restores original state in <2 minutes | WB-03: `rollback.py` + timing test | 2, 9 |

### Resource Gates (R)

| Gate ID | Gate | Target (from phase-gates.md) | Satisfied By | Day |
|---------|------|------|-------------|-----|
| R-01 | Peak Memory | Migration uses <500MB RAM | WB-02: `psutil` monitoring in runner | 1, 9 |
| R-02 | Disk Space | Schema overhead <10MB (empty tables) | WB-05: DB file size comparison test | 2, 9 |

**Total: 19 gates, all traced to phase-gates.md authority.**

---

## 8. Test & Verification Plan

### Test Files

| File | Gate Coverage | Day Created |
|------|-------------|-------------|
| `tests/test_phase0_migration.py` | F-01, S-01, S-02, P-01, R-01, R-02, DG-02, DG-03 | Day 2 |
| `tests/test_phase0_models.py` | (model correctness) | Day 3 |
| `tests/test_phase0_api_v1.py` | F-03, DG-04 | Day 4 |
| `tests/test_phase0_upload_queue.py` | UQ-01, UQ-02, UQ-03, UQ-04, UQ-05 | Day 5 |
| `tests/test_phase0_config_matrix.py` | F-04 | Day 6 |
| `tests/test_phase0_backward_compat.py` | F-02, P-02 | Day 8 |
| `tests/test_phase0_gates.py` | All 19 gates (comprehensive) | Day 9 |

### Verification Categories

#### Migration Verification

| Test | Assertion | Gate |
|------|-----------|------|
| Forward migration creates tables | 7 new tables + 2 FTS exist | F-01 |
| Migration is idempotent | Run twice, no errors | F-01 |
| Migration preserves entries | 100 entries intact, checksums match | S-01 |
| Migration backfills created_at | Legacy entries have non-empty created_at | DG-03 |
| Migration <5s on 10K entries | `time.perf_counter()` delta < 5.0 | P-01 |

#### Rollback Verification

| Test | Assertion | Gate |
|------|-----------|------|
| Rollback drops v3 tables | Only original tables remain | S-02 |
| Rollback preserves entries | Row count and checksums match | S-01, S-02 |
| Rollback completes <2min | `time.perf_counter()` delta < 120.0 | S-02 |

#### Compatibility Verification

| Test | Assertion | Gate |
|------|-----------|------|
| Full v2 workflow after migration | Upload -> PENDING -> query -> search all work | F-02 |
| Legacy /api/* untouched | All v2 endpoints return expected responses | F-02 |
| Query overhead <10ms | Median delta of 100 queries < 10ms | P-02 |

#### Performance & Resource Verification

| Test | Assertion | Gate |
|------|-----------|------|
| Peak memory <500MB | `psutil.Process().memory_info().rss` < 500MB | R-01 |
| Schema overhead <10MB | DB file size delta < 10MB | R-02 |

---

## 9. Risks / Failure Signals / Fallback

### Risk Matrix

| # | Risk | Probability | Impact | Trigger Signal | Mitigation | Fallback |
|---|------|-------------|--------|----------------|------------|----------|
| 1 | SQLite ALTER TABLE fails on production DB | Low | High | Migration error on real `recall.db` | Test on copy of prod DB first; use IF NOT EXISTS | Manually apply DDL |
| 2 | Rollback column removal requires table rebuild | Medium | Medium | Rolled back DB has different PRAGMA table_info | Use standard CREATE-INSERT-DROP-RENAME pattern | Accept governance cols in rolled-back state |
| 3 | Existing tests break from schema changes | Medium | High | `pytest tests/` has failures | Run existing suite on Day 8 early; update conftest.py fixture | Isolate migration behind feature flag |
| 4 | Migration >5s on 10K entries | Low | Medium | `test_gate_P01` fails | PRAGMA optimizations, batch processing | Raise gate threshold with documented justification |
| 5 | New FTS tables cause locking issues | Medium | Medium | Concurrent read/write errors | Phase 0 only creates tables; no writes until Phase 1/2 | Move FTS creation to Phase 1 |
| 6 | UploadQueue 100GB test too slow in CI | High | Low | CI timeout on buffer tests | Use configurable small `max_size` param in tests (10MB) | Manual 100GB test documented as gate evidence |
| 7 | Migration across macOS/Linux differences | Low | Medium | Test passes on macOS but fails on Debian | Only standard SQLite features; no OS-specific calls | Add cross-platform CI step |

### Failure Signals (from phase-gates.md Failure Signal Matrix)

| Signal | Threshold | Action |
|--------|-----------|--------|
| Migration takes >30s on modest DB (10K entries) | 6x over 5s target | Optimize migration script or split into batches |
| Rollback corrupts data in any test case | Any data loss | Fix rollback script, add more validation before retry |

---

## 10. Deliverables Checklist

### Code Files (New)

- [ ] `openrecall/server/database/migrations/__init__.py`
- [ ] `openrecall/server/database/migrations/runner.py`
- [ ] `openrecall/server/database/migrations/rollback.py`
- [ ] `openrecall/server/database/migrations/integrity.py`
- [ ] `openrecall/server/database/migrations/v3_001_add_multimodal_tables.sql`
- [ ] `openrecall/server/api_v1.py`
- [ ] `openrecall/server/auth.py`
- [ ] `openrecall/client/upload_queue.py`
- [ ] `openrecall/shared/config_presets.py`
- [ ] `config/local.env`
- [ ] `config/remote.env`
- [ ] `config/debian_client.env`
- [ ] `config/debian_server.env`

### Code Files (Modified)

- [ ] `openrecall/shared/models.py` -- add 6 new Pydantic models
- [ ] `openrecall/server/app.py` -- register v1 blueprint
- [ ] `openrecall/client/consumer.py` -- replace backoff schedule
- [ ] `openrecall/shared/config.py` -- add `deployment_mode`
- [ ] `tests/conftest.py` -- add migration to test fixture

### Test Files (New)

- [ ] `tests/test_phase0_migration.py`
- [ ] `tests/test_phase0_models.py`
- [ ] `tests/test_phase0_api_v1.py`
- [ ] `tests/test_phase0_upload_queue.py`
- [ ] `tests/test_phase0_config_matrix.py`
- [ ] `tests/test_phase0_backward_compat.py`
- [ ] `tests/test_phase0_gates.py`

### Documentation Files

- [ ] `v3/plan/02-phase-0-detailed-plan.md` (this file)
- [ ] `v3/results/pii-classification-policy.md`
- [ ] `v3/results/retention-policy-design.md`
- [ ] `v3/results/phase-0-validation.md`
- [ ] `v3/milestones/roadmap-status.md` (updated Phase 0 section)
- [ ] `v3/metrics/phase-gates.md` (updated Phase 0 statuses)

---

## 11. Execution Readiness Checklist

1. [ ] All 8 required documents read and understood (master prompt, roadmap, phase-gates, ADR-0001 through ADR-0004, references)
2. [ ] v2 codebase architecture understood (producer-consumer, 3-tier storage, API routes, models, config)
3. [ ] screenpipe reference schema reviewed (table structures, FTS patterns, index strategies)
4. [ ] No unresolved open questions (all ADRs approved, all gates defined in phase-gates.md)
5. [ ] Development environment ready (Python, pytest, psutil available)
6. [ ] Copy of production `recall.db` available for migration testing
7. [ ] This plan reviewed and approved by Product Owner
8. [ ] No conflicting changes in progress on the v2 codebase
9. [ ] Git branch `phase-0/foundation` created from current `master`
10. [ ] Day 1 tasks have no external dependencies -- can start immediately

---

## 12. Last Updated

**Date**: 2026-02-06
**Author**: Chief Architect + Planning Agent
**Status**: Ready to Execute
**Next Review**: Day 5 (mid-phase checkpoint)
