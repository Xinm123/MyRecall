# MyRecall-v3 Roadmap Status Tracker

**Last Updated**: 2026-02-24T22:10:00Z
**Overall Status**: 🟩 Phase 0 Complete / 🟩 Phase 1 Complete / 🟩 Phase 2.5 Complete / ⏸ Audio (Phase 2.0/2.1) Paused / ⬜ Phase 2.6 Audio Freeze Governance / ⬜ Phase 2.7 Label Alignment Gate / ⬜ Phase 3 Vision Search / ⬜ Phase 4 Vision Chat / ⬜ Phase 5 Deployment / ⬜ Phase 8 Full Alignment
**Target Completion**: Week 22 (2026-07-04) remains the outer bound for MVP deployment (Phase 3-5). Audio is excluded from MVP scope under the vision-only pivot.

---

## Roadmap Revision (2026-02-24, rev.2)

This revision inserts a standalone governance phase between Phase 2.5 and Phase 2.7:

- **Phase 2.6 Added**: `Audio Freeze Governance` as a hard governance gate.
- **Hard Gate Policy**: Phase 2.7 cannot start until Phase 2.6 gates (`2.6-G-*`) are all PASS.
- **Governance Scope**: frozen client/server audio modules plus critical audio-related config keys, with default full-chain pause contract.
- **Default Contract**: no auto capture, no auto processing/indexing, no default audio UI visibility, no Search/Chat audio grounding.
- **Controlled Exception Path**: only approved P0/P1 fixes can temporarily bypass freeze, with mandatory TTL, rollback, and closure evidence.
- **Alignment Strategy**: follow screenpipe quality-gate and rollback discipline principles, while preserving MyRecall phase-gate control model.

This revision does not re-open audio feature scope. It formalizes freeze governance so downstream quality evidence remains auditable.

## Roadmap Revision (2026-02-24)

This revision introduces a **hard pre-Phase-3 quality gate** for frame-label consistency:

- **Phase 2.7 Added**: `Frame Label Alignment Gate` is now a standalone milestone.
- **Hard Gate Policy**: Phase 3 cannot start until Phase 2.7 acceptance criteria pass.
- **Structural Alignment with screenpipe**: Align write-time metadata source traceability, label dedup/index strategy, and query-side quality controls without full event-driven capture rewrite.
- **Primary KPI Priority**: retrieval accuracy first, then latency/resource constraints.

This revision does not alter the vision-only product direction. It adds risk control to prevent noisy metadata from entering Search/Chat foundations.

## Roadmap Revision (2026-02-23)

This revision locks the near-term product scope and resolves prior contradictions:

- **Vision-only**: Search/Chat use only video frames + OCR text + metadata (`app_name`, `window_name`, `focused`, `browser_url`).
- **Audio Freeze**: No further audio work (capture/storage/search/chat parity) in the current and foreseeable phases.
- **Chat is the core**: All work is prioritized by how directly it enables an evidence-based chat loop.
- **Time semantics aligned with screenpipe**: Time ranges are defined in the user's local timezone (browser), converted to epoch seconds, and filtered server-side without timezone inference.

This revision **supersedes** the 2026-02-14 decision that made Phase 2.1 audio parity a hard precondition for Phase 3.

## Timeline Overview

**Timeline Start**: 2026-02-06 (Week 1)

| Phase | Relative Sequence (authoritative) | Calendar Mapping | Status |
|---|---|---|---|
| Phase 0: Foundation | Historical Week 1-2 | 2026-02-06 baseline | 🟩 Complete |
| Phase 1: Video Recording | Historical Week 3-6 | Engineering complete; long-run evidence deferred | 🟩 Complete |
| Phase 2.x: Audio (2.0/2.1) | Frozen branch | Not on MVP critical path | ⏸ Paused |
| Phase 2.5: WebUI Dashboards | Historical mini-sprint (~5 days) | Completed 2026-02-12 | 🟩 Complete |
| Phase 2.6: Audio Freeze Governance | **R1** | Hard governance lock before any pre-Phase-3 quality hardening | ⬜️ Not Started |
| Phase 2.7: Frame Label Alignment Gate | **R2** | Immediate quality hard-gate before Phase 3 kickoff | ⬜️ Not Started |
| Phase 3: Vision Search Parity | **R3-R4** | Starts only after Phase 2.7 GO; bounded by Week 22 outer deadline | ⬜️ Not Started |
| Phase 4: Vision Chat MVP | **R5-R6** | Assigned after Phase 3 completion; bounded by Week 22 | ⬜️ Not Started |
| Phase 5: Deployment (SERIAL) | **R7-R11** | Assigned after Phase 4 completion; bounded by Week 22 | ⬜️ Not Started |
| Phase 6: Streaming Chat | Post-MVP | Future | ⬜️ Future |
| Phase 7: Memory (A+C) | Post-MVP | Week 25+ | ⬜️ Future |
| Phase 8: Full Screenpipe Alignment (Required) | Post-MVP | Starts after Phase 7 completion | ⬜️ Future |

Legend: ⬜️ Not Started | 🟨 In Progress | 🟩 Complete | 🟥 Blocked | ⏸ Paused

**Execution Strategy**: MVP phases 2.6/2.7/3/4/5 execute SERIALLY (not in parallel); Post-MVP phases 6/7/8 also execute SERIALLY. Relative sequence (`R1..R11`) is authoritative for MVP ordering; calendar assignment is a scheduling output, not a contract.

---

## Current Deviation from Target

Target documents remain authoritative. The table below records known implementation drift that must be converged during Phase 3/4.

| Area | Target Contract | Current Implementation (as of 2026-02-24) | Convergence Action |
|---|---|---|---|
| `/api/v1/search` browse mode | `q` optional; empty/missing `q` returns browse feed ordered by `timestamp DESC` | Empty/missing `q` returns empty paginated payload | Implement browse/feed retrieval path in Phase 3 |
| `/api/v1/search` time bounds | `start_time` required; `end_time` optional | `start_time` is not enforced at route level | Enforce request validation in Phase 3 |
| Search modality | Vision-only for Search/Chat | Search engine still includes audio FTS candidates | Add vision-only enforcement for Search/Chat path in Phase 3 |
| Frame label provenance | Per-frame label truth with source traceability for search grounding | Most frame labels still inherit chunk-level fallback (low granularity under intra-chunk app/window switch) | Lock freeze scope in Phase 2.6, then implement and gate in Phase 2.7 before Phase 3 |
| `/api/v1/chat` | Phase 4 endpoint returns `answer + evidence[]` | Endpoint not implemented yet | Deliver Phase 4 API + evidence contract |
| `/api/v1/timeline` | Chat/Search MVP depends on vision-only evidence path; target contract defaults timeline to video-only (audio only via explicit parameter/debug mode) | Timeline currently returns mixed video+audio by default | Introduce target default video-only contract in docs; keep current mixed behavior documented until convergence |

This section must be updated whenever code reality changes or when convergence work lands.

---

## Phase Status Details

### Phase 0: Foundation & Client-Server Boundary
**Status**: 🟩 Complete
**Planned**: Week 1-2 (2026-02-06 to 2026-02-19, 10 working days)
**Actual**: Completed 2026-02-06
**Owner**: Solo Developer (infrastructure setup)
**Detailed Plan**: `v3/plan/02-phase-0-detailed-plan.md`

**Execution Tracks**:
- Track A (Day 1-4): Schema, migration, rollback, Pydantic models
- Track B (Day 3-7): API v1 versioning, auth placeholder, pagination, upload queue
- Track C (Day 5-10): Config matrix, data governance, integration testing, gate validation

**Progress**:
- [x] Day 1: v3 SQL schema DDL (video_chunks, frames, ocr_text, audio_chunks, audio_transcriptions, schema_version)
- [x] Day 1: Migration runner with timing/memory checks
- [x] Day 1: Governance columns on existing `entries` table (created_at, expires_at)
- [x] Day 2: Rollback script (drop v3 tables, restore original state)
- [x] Day 2: SHA256 integrity verification utility
- [x] Day 2: Migration + rollback integration tests
- [x] Day 3: Pydantic models (VideoChunk, Frame, OcrText, AudioChunk, AudioTranscription)
- [x] Day 3: PaginatedResponse generic wrapper (ADR-0002)
- [x] Day 4: `/api/v1/*` Flask blueprint with pagination
- [x] Day 4: `@require_auth` placeholder decorator
- [x] Day 4: Blueprint registration (v1 + legacy coexistence)
- [x] Day 5: UploadQueue class (100GB capacity, 7-day TTL, FIFO, exponential backoff)
- [x] Day 5: UploaderConsumer backoff update to ADR-0002 schedule
- [x] Day 6: Configuration matrix (local/remote/debian_client/debian_server)
- [x] Day 6: Template .env files per deployment mode
- [x] Day 7: PII Classification Policy document
- [x] Day 7: Retention Policy Design document
- [x] Day 8: Full backward compatibility integration test (upload -> query -> search)
- [x] Day 8: Query overhead benchmark (<10ms gate)
- [x] Day 9: Gate validation suite (19 gate tests)
- [x] Day 10: Documentation updates, code cleanup, Go/No-Go review

**Go/No-Go Gates** (authority: `v3/metrics/phase-gates.md`):
- [x] F-01: Schema migration success (all 5 new tables created)
- [x] F-02: 100% backward compatibility (existing screenshot pipeline works)
- [x] F-03: API versioning (`/api/v1/*` functional, `/api/*` aliases work)
- [x] F-04: Configuration matrix (4 deployment modes configurable)
- [x] P-01: Migration <5s for 10K entries
- [x] P-02: Query overhead <10ms added by schema changes
- [x] S-01: Zero data loss during migration (SHA256 checksum)
- [x] S-02: Rollback restores original state in <2 minutes
- [x] R-01: Migration <500MB RAM
- [x] R-02: Schema overhead <10MB
- [x] DG-01: PII Classification Policy documented
- [x] DG-02: Encryption schema design (encrypted column)
- [x] DG-03: Retention policy design (created_at, expires_at)
- [x] DG-04: API authentication placeholder on all v1 routes
- [x] UQ-01: Buffer 100GB capacity enforcement (FIFO)
- [x] UQ-02: TTL cleanup (>7 days auto-deleted)
- [x] UQ-03: FIFO deletion order
- [x] UQ-04: Post-upload deletion within 1s
- [x] UQ-05: Retry exponential backoff (1min->5min->15min->1h->6h)

**Go/No-Go Decision**: ✅ GO -- All 19 Phase 0 gates passed (Phase 0 suite: 86 passed, 0 failed)

**Blockers**: Phase 0 无阻塞；存在跨阶段外部依赖阻塞（`tests/test_phase2_ingestion.py` 依赖 HuggingFace 模型权限，`pytest tests/ -v --tb=short` 会在收集阶段报 401）。该阻塞不影响 Phase 0 Go 判定。

---

### Phase 1: Screen Recording Pipeline
**Status**: 🟩 Complete (engineering and non-long-run validation complete; long-run observations moved to future plan)
**Planned**: Week 3-6 (4 weeks, 20 working days)
**Actual**: Engineering completed 2026-02-06 (single session)
**Owner**: Solo Developer (core pipeline implementation)
**Detailed Plan**: `v3/plan/03-phase-1-detailed-plan.md`

**Execution Tracks**:
- Track A (Day 1-5): FFmpeg recording, chunk management, frame extraction, E2E wire-up
- Track B (Day 6-10): OCR pipeline, FTS indexing, search integration, E2E validation, dual-mode
- Track C (Day 11-15): Timeline API, frame serving, retention worker, degradation, upload resume
- Track D (Day 16-20): Performance tuning, quality measurement, stability review, gate validation

**Progress**:
- [x] Day 1: FFmpegManager class (subprocess + watchdog + auto-restart)
- [x] Day 2: VideoRecorder class (chunk rotation + metadata + enqueue)
- [x] Day 3: v3_002 migration (status column) + upload API extension for video + server storage
- [x] Day 4: FrameExtractor class (FFmpeg extraction + MSSIM dedup + DB writes)
- [x] Day 5: Integration test: upload chunk → extract frames → verify in DB
- [x] Day 6: OCR pipeline on video frames (reuse providers, write ocr_text + ocr_text_fts)
- [x] Day 7: VideoProcessingWorker (background chunk → frames → OCR → FTS)
- [x] Day 8: Search integration (extend SearchEngine to query ocr_text_fts)
- [x] Day 9: End-to-end validation: record → upload → process → search
- [x] Day 10: Dual-mode recording (video/screenshot/auto) + fallback logic
- [x] Day 11: Timeline API (GET /api/v1/timeline)
- [x] Day 12: Frame serving API (GET /api/v1/frames/:id)
- [x] Day 13: Retention cleanup worker + start 7-day stability test
- [x] Day 14: Degradation handlers (FFmpeg crash, disk full, OCR slow, network down)
- [x] Day 15: Upload resume capability for large video chunks
- [x] Day 16-19: Test suite (8 files, 102 tests: 93 passed + 9 skipped long-run)
- [x] Day 20: Gate validation + documentation (phase-1-validation.md)
- [x] Post-Day 20 hardening: SQLStore startup auto-migration guard + legacy `/api/upload` video insert regression fix (prevents `Failed to insert video chunk` on fresh DB)
- [x] Post-Day 20 hardening: consumer dispatch now routes by `item_type` and logs target uploader branch for fast triage
- [x] Post-Day 20 hardening: search debug path fixed for video-only result sets (`vframe:*`) to prevent `NoneType.context` crashes
- [x] Post-Day 20 hardening: runtime recording toggle supports pause/resume monitor sources without full pipeline teardown
- [x] Post-Day 20 hardening: server startup now includes OCR warm-up for local OCR providers
- [x] Post-Day 20 documentation: established WebUI documentation hub (`v3/webui`) and added phase-level maintenance constraint (`results/README.md` -> sync `webui/CHANGELOG.md` + impacted `webui/pages/*.md`)
- [x] Phase 1.5: Frame metadata resolver (frame > chunk > null priority chain with source traceability)
- [x] Phase 1.5: focused/browser_url explicit pipeline (NULL = unknown, not schema default)
- [x] Phase 1.5: OCR engine true value (real provider name: rapidocr/doctr/openai/etc.)
- [x] Phase 1.5: Offset guard (pre-insertion validation with structured RFC3339 logging)
- [x] Phase 1.5: v3_005 migration (video_chunks start_time/end_time for precise offset bounds)
- [~] Phase 1.5.1: Strict 60s chunking + chunk_process self-heal + observability (In Progress -> Done gate: `P15-I01/P15-I02/P15-R01`; current: `P15-R01` passed, long-run integration pending)

**Go/No-Go Gates** (authority: `v3/metrics/phase-gates.md`):
- [x] 1-F-01: 1-hour recording → valid video chunks (unit validated)
- [x] 1-F-02: Frame extraction working (all frames in DB)
- [x] 1-F-03: OCR indexed (all frames have OCR text in FTS)
- [x] 1-F-04: Timeline API functional
- [x] 1-F-05: Searchable (OCR text from video frames via search endpoint)
- [x] 1-P-01: Frame extraction <2s/frame
- [ ] 1-P-02: E2E indexing <60s per 1-min chunk (PENDING: requires real pipeline)
- [ ] 1-P-03: Recording <5% CPU (PENDING: requires 1-hour measurement)
- [ ] 1-Q-01: OCR accuracy ≥95% (PENDING: requires curated dataset)
- [x] 1-Q-02: Frame dedup <1% false negatives (unit validated)
- [ ] 1-S-01: 7-day zero-crash test (PENDING: requires 7 calendar days)
- [ ] 1-S-02: Upload retry >99% success (PENDING: requires 24h measurement)
- [ ] 1-R-01: Storage <50GB/day (PENDING: requires 24h measurement)
- [ ] 1-R-02: Memory <500MB RAM (PENDING: requires runtime measurement)
- [x] 1-D-01: FFmpeg crash → auto-restart ≤60s
- [x] 1-D-02: Disk full → pause + cleanup
- [x] 1-D-03: OCR slow → reduce FPS (design validated)
- [x] 1-D-04: Upload failure → local-only + retry
- [x] 1-DG-01: Video file encryption (filesystem) (env validated)
- [x] 1-DG-02: Retention policy active (>30 day auto-delete)
- [~] 1-DG-03: OCR PII detection (optional -- skipped)

**Gate Summary**: 13 passed, 0 failed, 7 pending (long-run evidence), 1 skipped (optional)

**Go/No-Go Decision**: COMPLETE (execution closed; long-run observations deferred as non-blocking future work)

**Rationale**: 本轮审计范围内（非长时 gate）无失败，且无未解决 P0/P1；>30 天策略逻辑模拟通过（`-31d` 过期、`+30d` 不清理、`PENDING` 过期不清理、级联删除覆盖 DB+文件）；API 烟测 11/11 通过。7 个长时 gate 转入未来观测计划，不阻塞 Phase 2 执行。

**Test Results**: Post-Phase 1.5 regression: `tests/test_phase1_*` = 170 passed, 8 skipped, 0 failed；Phase 1.5 suite: 33 passed；`tests/test_phase1_gates.py` = 14 passed, 8 skipped, 0 failed；`tests/test_phase5_buffer.py -k TestUploaderConsumer` = 6 passed；Phase 1.5.1 strict60 regression: `tests/test_phase1_video_recorder.py` = 52 passed，`tests/test_phase1_pipeline_profile_change.py` = 4 passed，combined Phase 1 recorder fallback/probe regression = 60 passed.

**Blockers**: 无工程阻塞（Phase 1 已完成）。7 个长时 gate 已转入未来观测计划跟踪。

**Evidence**: `v3/evidence/phase1-audit/commands.log`, `v3/evidence/phase1-audit/api_smoke_status_lines_round1.txt`, `v3/evidence/phase1-audit/test_phase1_all_after_fix2.txt`, `v3/evidence/phase1_5_strict60/`

**Phase 1.5 Evidence Matrix**

| Change | Code Path | Test Command | Result | UTC Timestamp |
|---|---|---|---|---|
| Resolver `frame > chunk > null` for `app/window/focused/browser_url` | `openrecall/server/video/metadata_resolver.py` | `python3 -m pytest tests/test_phase1_5_metadata_resolver.py -v` | 12 passed | 2026-02-08T07:50:52Z |
| focused/browser_url explicit pipeline and query/read compatibility | `openrecall/server/video/processor.py`, `openrecall/server/database/sql.py`, `openrecall/server/api_v1.py` | `python3 -m pytest tests/test_phase1_5_focused_browser_url.py -v` | 10 passed | 2026-02-08T07:50:52Z |
| OCR engine true-value persistence | `openrecall/server/ai/base.py`, `openrecall/server/ai/providers.py`, `openrecall/server/video/processor.py` | `python3 -m pytest tests/test_phase1_5_ocr_engine.py -v` | 3 passed | 2026-02-08T07:50:52Z |
| Offset guard reject-write protection and structured logging | `openrecall/server/video/processor.py` | `python3 -m pytest tests/test_phase1_5_offset_guard.py -v` | 8 passed | 2026-02-08T07:50:52Z |
| Phase 1 + 1.5 full closure regression | `openrecall/server/video/metadata_resolver.py`, `openrecall/server/video/processor.py`, `openrecall/server/api_v1.py`, `openrecall/server/database/sql.py` | `python3 -m pytest tests/test_phase1_* -v` | 170 passed, 8 skipped | 2026-02-08T07:50:08Z |

### Phase 1 Long-Run Observation Plan (Future, Non-Blocking)
**Status**: ⬜️ Planned
**Window**: Week 9-12（与 Phase 2/3 并行观测，不阻塞主线）
**Scope**: 对 Phase 1 的 7 个 `LONGRUN` 指标补充日历时间证据

| Gate ID | Observation Goal | Planned Evidence |
|---|---|---|
| 1-P-02 | E2E indexing `<60s` per 1-min chunk | 连续 24h chunk 样本延迟分布 |
| 1-P-03 | Recording CPU `<5%` | 1h 录制 CPU 采样统计（avg/p95） |
| 1-Q-01 | OCR Accuracy `>=95%` | 100 帧标注集准确率报告 |
| 1-S-01 | 7-day zero-crash | 7 天运行日志 + crash 统计 |
| 1-S-02 | Upload retry success `>99%` | 24h 上传成功率与重试分布 |
| 1-R-01 | Storage `<50GB/day` | 24h 存储增长报告 |
| 1-R-02 | Memory `<500MB` | 运行期 RSS 采样（avg/p95/max） |

**Output Location**: `v3/results/phase-1-validation.md`（追加 LONGRUN 证据附录）

---

### Phase 2.0: Audio MVP (Paused / Frozen)
**Status**: ⏸ Paused (engineering complete; not on critical path under vision-only pivot)
**Planned**: Week 7-8 (10 working days, 2026-02-09 to 2026-02-20)
**Actual**: 2026-02-09 (implementation completed in single session)
**Owner**: Solo Developer (audio capture & transcription)
**Detailed Plan**: `v3/plan/04-phase-2-detailed-plan.md`
**Validation Report**: `v3/results/phase-2-validation.md`

**Test Results**: 477 passed, 19 skipped, 0 failed (full suite including Phase 0+1 regression)

**Note (2026-02-23)**: Audio Freeze is in effect. Phase 2.0 is preserved as completed engineering work, but it is not required for Phase 3/4 execution and will not be extended in the near term.

**Execution Tracks** (10 working days):
- Day 1-2: Audio capture foundation (AudioManager, AudioRecorder, config, upload dispatch)
- Day 3-4: VAD integration (silero-vad + fallback) + Whisper transcription pipeline (faster-whisper)
- Day 5-6: Server ingestion + migration v3_006 + AudioChunkProcessor + AudioProcessingWorker + retention extension
- Day 7-8: Search extension (audio FTS in SearchEngine) + Unified timeline API + audio endpoints
- Day 9-10: Performance/quality testing + degradation handlers + gate validation + documentation

**Progress**:
- [x] Day 1: Audio config extension + AudioManager (sounddevice wrapper)
- [x] Day 2: AudioRecorder (producer + buffer) + upload pipeline extension (consumer + uploader)
- [x] Day 3: VAD integration (silero-vad primary, webrtcvad fallback)
- [x] Day 4: Whisper transcription pipeline (faster-whisper, GPU/CPU dispatch)
- [x] Day 5: Server ingestion (migration v3_006, upload API audio detect, SQLStore audio methods, AudioChunkProcessor)
- [x] Day 6: AudioProcessingWorker + RetentionWorker audio extension
- [x] Day 7: Search extension (audio FTS in SearchEngine)
- [x] Day 8: Unified timeline API (video + audio) + dedicated audio endpoints
- [x] Day 9: Performance tuning + quality testing (WER) + degradation handlers
- [x] Day 10: Gate validation suite + documentation (24h stability test pending)

**Go/No-Go Gates** (authority: `v3/metrics/phase-gates.md`):
- [x] 2-F-01: Audio Capture Working (both system + mic, 1 hour, playable chunks)
- [x] 2-F-02: VAD Filtering (speech only transcribed, <50% of total duration)
- [x] 2-F-03: Whisper Transcription (all speech stored in audio_transcriptions)
- [x] 2-F-04: Audio FTS Indexed (searchable via audio_transcriptions_fts)
- [x] 2-F-05: Unified Timeline (video frames + audio transcriptions in /api/v1/timeline)
- [x] 2-P-01: Transcription Latency <30s/30s-segment (GPU) or <90s (CPU) — structural
- [x] 2-P-02: VAD Processing <1s/30s-segment — structural
- [x] 2-P-03: Transcription Throughput (no backlog growth over 1hr) — structural
- [x] 2-P-04: Audio Capture CPU <3% per device — structural
- [x] 2-Q-01: Transcription WER (clean) <=15% — structural (mock verified)
- [x] 2-Q-02: Transcription WER (noisy) <=30% — structural (mock verified)
- [ ] 2-S-01: 24-hour zero-crash continuous run — PENDING
- [x] 2-R-01: Whisper GPU VRAM <500MB — N/A (CPU-only on Apple Silicon)
- [x] 2-R-02: Audio Storage <2GB/day
- [x] 2-DG-01: Audio file encryption (filesystem — FileVault)
- [x] 2-DG-02: Transcription redaction (optional — N/A for Phase 2.0)
- [x] 2-DG-03: Retention policy active (audio >30 days auto-deleted)

**Blockers**: None (paused; long-run evidence is non-blocking while audio is frozen).

---

### Phase 2.5: WebUI Audio & Video Dashboard Pages
**Status**: 🟩 Complete
**Planned**: ~5 working days
**Actual**: 2026-02-12 (single session)
**Owner**: Solo Developer (WebUI + minimal backend APIs)
**Detailed Plan**: `v3/plan/05-phase-2.5-webui-audio-video-detailed-plan.md`
**Validation Report**: `v3/results/phase-2.5-validation.md`

**Dependencies**: Phase 2.0 Engineering Complete (all prerequisites met)

**Scope**: `/audio` and `/video` WebUI Dashboard pages with chunk management, inline media playback, content browsing (transcriptions / frames), processing queue status, and aggregated statistics. 6 new API endpoints + 1 existing endpoint extension.

**Test Results**: 59 Phase 2.5 tests passed (30 API + 8 audio page + 8 video page + 13 navigation). Full regression: 553 passed, 12 skipped, 0 failed.

**Progress**:
- [x] SQLStore: `get_video_chunks_paginated()`, `get_frames_paginated()`, `get_video_stats()`, `get_audio_stats()`
- [x] API: `GET /api/v1/video/chunks` (pagination + status/monitor_id filter)
- [x] API: `GET /api/v1/video/chunks/<id>/file` (mp4 serving + path traversal prevention)
- [x] API: `GET /api/v1/video/frames` (pagination + multi-filter + OCR snippet)
- [x] API: `GET /api/v1/video/stats` (aggregated statistics)
- [x] API: `GET /api/v1/audio/chunks/<id>/file` (WAV serving + path traversal prevention)
- [x] API: `GET /api/v1/audio/stats` (aggregated statistics)
- [x] API: Extend `GET /api/v1/audio/chunks` with `device` filter (additive)
- [x] Flask route: `/audio` → `audio()`
- [x] Template: `audio.html` (stats + chunks + transcriptions + playback + queue)
- [x] Flask route: `/video` → `video()`
- [x] Template: `video.html` (stats + chunks + frames + playback + queue)
- [x] Navigation: `layout.html` audio/video icons + current-view highlighting
- [x] Icons: `icons.html` `icon_audio()` + `icon_video()` macros
- [x] Tests: 4 test files (59 tests total)

**Gate Traceability** (authority: `v3/metrics/phase-gates.md`):

| ID | Check | Type | Status |
|----|-------|------|--------|
| 2.5-F-01 | `/audio` page renderable | Non-Gating | PASS |
| 2.5-F-02 | `/video` page renderable | Non-Gating | PASS |
| 2.5-F-03 | Video chunks API pagination | Non-Gating | PASS |
| 2.5-F-04 | Video frames API filtering | Non-Gating | PASS |
| 2.5-F-05 | Video file serving mp4 | Non-Gating | PASS |
| 2.5-F-06 | Audio file serving WAV | Non-Gating | PASS |
| 2.5-F-07 | Audio inline playback | Non-Gating | PASS |
| 2.5-F-08 | Video inline playback | Non-Gating | PASS |
| 2.5-F-09 | Stats endpoints correct | Non-Gating | PASS |
| 2.5-F-10 | Navigation icons + highlight | Non-Gating | PASS |
| 2.5-F-11 | Audio device filter (additive) | Non-Gating | PASS |
| 2.5-P-01 | Stats <500ms | Non-Gating | PASS (ref) |
| **2.5-S-01** | **No test regression (>=477)** | **GATING** | **PASS** (553 passed) |
| 2.5-R-01 | No full file load to memory | Non-Gating | PASS |
| **2.5-DG-01** | **Path traversal prevention** | **GATING** | **PASS** (4 security tests) |

**Go/No-Go Decision**: **GO** — All 15 gates PASS (2 GATING + 13 Non-Gating). 553 tests passed, 0 failed.

**Blockers**: None.

---

### Phase 2.1: Audio Parity with screenpipe (Paused / Frozen)
**Status**: ⏸ Paused (deferred; not on critical path under vision-only pivot)
**Planned**: TBD
**Actual**: TBD
**Owner**: TBD
**Alignment Target**: 尽可能对齐 screenpipe（架构/行为优先，保持 Python + ONNX）
**Execution Policy**: Paused. Not a precondition for Phase 3/4 while Audio Freeze is in effect.

**Architecture Constraints (Decoupled Client/Server)**:
- Client only handles capture and upload; it does not run speaker decisions, dedup logic, or speaker lifecycle operations.
- Server owns speaker persistence, lifecycle operations, overlap cleanup, dedup metrics, and observability output.
- All parity additions are additive and must not break existing upload protocol or current API behavior.

**Scope (MUST)**:
- [ ] Layered VAD decision chain aligned with chunk gate semantics (`speech_frame_count / total_frames`)
- [ ] Pre-segmentation handling aligned (`speech/silence/unknown` flow + noise path behavior)
- [ ] Recording stability aligned (overlap windows + disconnect recovery behavior)
- [ ] Transcription result fields and timestamp behavior aligned with screenpipe semantics
- [ ] Dedup baseline strategy aligned (time window + similarity threshold policy)
- [ ] Speaker persistence layer: `speakers`, `speaker_embeddings` (additive schema)
- [ ] Speaker lifecycle operations: identify/update centroid + merge + reassign + undo (server-side)
- [ ] Text overlap cleanup + dedup metrics: `total`, `inserted`, `duplicate_blocked`, `overlap_trimmed`, `duplicate_rate`
- [ ] Unified observability fields: `backend/speech_frames/total_frames/speech_ratio/min_speech_ratio/filtered/speaker_confidence/speaker_decision/dedup_action`
- [ ] Speaker quality guardrail: low-confidence samples default to `unknown` (no auto-merge), with later manual merge/reassign support

**Scope (SHOULD)**:
- [ ] Multi-engine STT strategy parity while keeping Python runtime
- [ ] Speaker/diarization compatibility path (Python stack)

**Planned Additive Interfaces**:
- [ ] DB: add `speakers` and `speaker_embeddings`; add `speaker_confidence` (or equivalent measurable field) on `audio_transcriptions`
- [ ] API: add speaker lifecycle endpoints (merge/reassign/undo) as server capabilities, without changing current upload protocol
- [ ] Observability contract: emit fixed unified fields for Phase 3/4 debugging and regression quality tracking

**Go/No-Go Gates**:
- [ ] Key evaluation corpus parity pass rate ≥85% against screenpipe reference behavior
- [ ] Silero `speech_ratio=0` anomaly chunk ratio reduced by ≥60% vs Phase 2.0 baseline
- [ ] Gate-fail path skips transcription with correct reason field (`speech_ratio_below_threshold`) in 100% validation cases
- [ ] Speaker persistence schema is present and writable (`speakers` + `speaker_embeddings`) with backward compatibility preserved
- [ ] Speaker lifecycle acceptance passes (`merge/reassign/undo`) with auditable operation traces
- [ ] Overlap dedup metrics are emitted and dedup effectiveness passes replay corpus checks (no regression on non-overlap set)
- [ ] Unified observability field completeness is ≥99% across processed chunks, and low-confidence speaker samples default to `unknown`

**Blockers**: N/A (paused)

---

### Phase 2.6: Audio Freeze Governance (Hard Governance Gate)
**Status**: ⬜️ Not Started
**Planned**: Relative R1 (must pass before Phase 2.7 starts)
**Actual**: TBD
**Owner**: Product Owner + Chief Architect
**Authority Docs**: `v3/decisions/ADR-0007-phase-2.6-audio-freeze-governance.md`, `v3/metrics/phase-gates.md`, `v3/milestones/roadmap-status.md`
**Decision Record**: `v3/decisions/ADR-0007-phase-2.6-audio-freeze-governance.md`

**Purpose**:
- Turn Audio Freeze into an auditable control phase with default full-chain pause semantics.
- Lock client/server audio code + config boundaries and default behavior boundaries.
- Keep Search/Chat target contract vision-only and timeline target contract default video-only.
- Provide controlled P0/P1 exception workflow with TTL + rollback + closure evidence.
- Produce evidence package required for Phase 2.7 kickoff.

**Governance Interfaces**:
- `FreezeScopeMatrix`
- `ExceptionRequest`
- `GateEvidenceManifest`

**Go/No-Go Gates** (authority: `v3/metrics/phase-gates.md`):
- [ ] 2.6-G-01: Default capture pause verified (no automatic audio capture in freeze mode).
- [ ] 2.6-G-02: Default processing pause verified (no automatic VAD/transcribe/index in freeze mode).
- [ ] 2.6-G-03: UI/retrieval contract verified (audio hidden by default; Search/Chat vision-only; timeline target default video-only).
- [ ] 2.6-G-04: Exception workflow closure validated (approved exceptions closed with TTL + rollback + closure evidence).
- [ ] 2.6-G-05: Drift and rollback readiness validated (no unauthorized drift; rollback objective <2 minutes).

**Blockers**: Blocks Phase 2.7 until all `2.6-G-*` gates PASS.

---

### Phase 2.7: Frame Label Alignment Gate (Screenpipe-Philosophy, Structural Alignment)
**Status**: ⬜️ Not Started
**Planned**: Relative R2 (hard gate milestone; must complete before Phase 3 kickoff)
**Actual**: TBD
**Owner**: Solo Developer (video metadata + indexing contracts)
**Detailed Plan**: `docs/plans/2026-02-24-phase-2.7-frame-label-alignment.md`

**Purpose**:
- Resolve chunk-level label drift where multiple frames inherit identical `app_name/window_name/focused/browser_url`.
- Introduce frame-level source traceability and confidence semantics.
- Reduce noisy evidence propagation into Phase 3 search relevance.
- Data Scope: only data ingested at/after `T0`; no historical backfill in this phase.

**Scope (selected architecture: A2 + B2)**:
- [ ] Add additive frame metadata contract: `metadata_source`, `metadata_confidence`.
- [ ] Define and expose `label_quality_score` for Search/Timeline ranking and filtering.
- [ ] Add normalized label key strategy with uniqueness/conflict policy.
- [ ] Add deferred incremental indexing strategy and freshness SLA.
- [ ] Add strict filtering mode to exclude `chunk_fallback` rows when needed.

**Go/No-Go Gates**:
- [ ] Label mismatch rate reduced to <=2%-5% (sampled labeled dataset).
- [ ] Vision search `Precision@10` improved by >=20% versus Phase 1.5 baseline.
- [ ] Query p95 does not regress; target 10%-20% improvement.
- [ ] Resource growth bounded (CPU <=+12%, storage <=+10%).
- [ ] No API compatibility regression and no unsafe migration side effects.

**Blockers**: Phase 2.6 hard-governance gate not completed.

---

### Phase 3: Vision Search Parity (Screenpipe-Aligned, Vision-Only)
**Status**: ⬜️ Not Started
**Planned**: Relative R3-R4 (2 weeks; calendar assigned at kickoff after Phase 2.7 GO)
**Actual**: TBD
**Owner**: Solo Developer (API + WebUI hardening)

**Progress**:
- [ ] `/api/v1/search` contract aligned to screenpipe `/search` (vision-only): `q` optional, `q=""` → browse/feed, `start_time` required, `end_time` optional
- [ ] Browse/feed mode ordering: `timestamp DESC` (stable pagination)
- [ ] Keyword mode ordering: rank-first, tie-break by `timestamp DESC`
- [ ] Vision search API supports `app_name/window_name/focused/browser_url` filters
- [ ] Search result presentation aligned to screenpipe (evidence-first cards, easy drill-down to frames)
- [ ] `/search` WebUI uses time bounds end-to-end (and supports browse/feed when `q` empty)
- [ ] Search performance guardrails (default narrow ranges, strict pagination, truncation)

**Go/No-Go Gates**:
- [ ] Search contract: `start_time` required; `q` optional; empty `q` is browse/feed; filters work; ordering stable
- [ ] Precision@10 ≥0.7 (vision-only evaluation set)
- [ ] Search latency <500ms p95 (bounded time ranges)

**Blockers**: Phase 2.7 hard-gate not completed

---

### Phase 4: Vision Chat MVP (Evidence-First, Non-Streaming)
**Status**: ⬜️ Not Started
**Planned**: Relative R5-R6 (2 weeks; starts after Phase 3 GO)
**Actual**: TBD
**Owner**: Solo Developer (LLM + WebUI integration)

**Progress**:
- [ ] Dynamic system prompt injection (current time + user timezone + local time; screenpipe-aligned)
- [ ] Grounding strategy (Phase 4): **single retrieval + single summary** (no tool-calling)
- [ ] Retrieval uses Phase 3 search browse/feed (`q=\"\"`) + bounded time range + sampling (5min bucket, 2 frames/bucket, auto-widen)
- [ ] Phase 4 LLM context is text-only (OCR+metadata+frame_url); no raw frame images sent to LLM
- [ ] Chat API endpoint (`POST /api/v1/chat`) returning `answer + evidence[]`
- [ ] WebUI `/chat` page (simple request-response; evidence drill-down to frames)
- [ ] Mention support parity subset: `@today/@yesterday/@last-hour/@selection` (UI shortcuts; time filters only; vision-only)
- [ ] Evidence policy: for user-activity claims, include `evidence[]` with real `frame_id + timestamp + frame_url`; allow `evidence=[]` for pure how-to replies; never fabricate

**Go/No-Go Gates**:
- [ ] Chat answers: "总结一下我今天 14:00-17:00 做了什么" (vision-only)
- [ ] For activity/time-range answers, response includes `evidence[]` with real `frame_id + timestamp + frame_url` (no fabricated evidence)
- [ ] Response quality: hallucination rate <10% on curated eval set
- [ ] Latency <5s median (bounded time ranges)

**Blockers**: Phase 3 completion (search/tooling hardening)

**Note**: Phase 4 delivers simple request-response chat. Streaming remains deferred to Phase 6.

---

### Phase 5: Deployment Migration (SERIAL, after Phase 3-4)
**Status**: ⬜️ Not Started
**Planned**: Relative R7-R11 (5 weeks; starts after Phase 4 GO)
**Actual**: TBD
**Owner**: Solo Developer + Product Owner (deployment & validation)
**Priority**: 🔴 CRITICAL PATH (Week 22 hard deadline)

**Architecture Decision**: Thin client model - all data stored on Debian server.

**Architecture Evolution**:
```
Before Phase 5 (Localhost):
┌─────────────────────┐
│   PC (localhost)    │
│  ┌──────┬────────┐  │
│  │Client│ Server │  │
│  │      │ +DB    │  │
│  └──────┴────────┘  │
└─────────────────────┘

After Phase 5 (Thin Client):
┌──────────┐          ┌─────────────────┐
│ PC       │          │   Debian Box    │
│ ┌──────┐ │          │  ┌────────────┐ │
│ │Client│─┼─────────→│  │ Server+DB  │ │
│ │(thin)│ │  WAN     │  │ (all data) │ │
│ └──────┘ │          │  └────────────┘ │
└──────────┘          └─────────────────┘
```

**Sub-Phases**:
- [ ] Phase 5.0: Remote API Readiness Audit (Week 7) - validate Phase 0-4 APIs are remote-ready
- [ ] Phase 5.1: Local-Remote Simulation (Week 8) - 50ms latency testing
- [ ] Phase 5.2: Server Containerization (Week 9) - Dockerfile + docker-compose
- [ ] Phase 5.3: Bulk Data Upload (Week 10) - migrate all existing local data
- [ ] Phase 5.4: Client Refactor (Week 10-11) - remove local DB, switch to API-only, parallel with 5.3 second half
- [ ] Phase 5.5: Gray Release & Cutover (Week 11)

**Progress**:
- [ ] Phase 5.0: API versioning and remote-first design
- [ ] Phase 5.1: Network latency testing (50ms simulation)
- [ ] Phase 5.2: Dockerfile + docker-compose.yml
- [ ] Phase 5.3: Bulk upload tool with checksum validation
- [ ] Phase 5.4: Client refactor (remove SQLite, LanceDB, local storage)
- [ ] Phase 5.5: Gray release (1 test PC) + rollback drill

**Go/No-Go Gates**:
- [ ] All features work with remote server
- [ ] Upload <5 min/1GB
- [ ] Upload success rate >95%
- [ ] Zero data loss (checksums match)
- [ ] Rollback drill successful (<1 hour)

**Blockers**: Phase 4 completion

---

### Phase 6: Streaming Chat
**Status**: ⬜️ Not Started (FUTURE)
**Planned**: Week 23-24 (2 weeks)
**Actual**: TBD
**Owner**: TBD

**Progress**:
- [ ] SSE (Server-Sent Events) or WebSocket streaming implementation
- [ ] Progressive response rendering in Web UI
- [ ] Streaming token limits and cost controls
- [ ] Connection error handling and fallback to request-response

**Go/No-Go Gates**:
- [ ] First token <1s (TTFT - Time To First Token)
- [ ] Streaming throughput >50 tokens/s
- [ ] Graceful degradation if streaming fails

**Blockers**: Phase 4 completion

---

### Phase 7: Memory Capabilities
**Status**: ⬜️ Not Started (FUTURE)
**Planned**: Week 25+ (TBD)
**Actual**: TBD
**Owner**: TBD

**Scope Definition**:
- **(A) Daily/Weekly Summaries**: Auto-generated activity digests
- **(C) Persistent Agent State**: Multi-turn reasoning memory, user preferences

**Progress**:
- [ ] Summary Engine (scheduled background job, LLM summarization)
- [ ] Agent Memory Store (preferences, conversation history, learned patterns)
- [ ] Memory API endpoints (`GET /api/v1/memory/summary`, `POST /api/v1/memory/preference`)
- [ ] Chat tool integration (`get_user_context()`)

**Go/No-Go Gates**:
- TBD (depends on Phase 4 learnings)

**Blockers**: Phase 4 completion

---

### Phase 8: Full Screenpipe Alignment (Post-MVP, Required)
**Status**: ⬜️ Not Started (FUTURE)
**Planned**: Post-MVP, starts after Phase 7 completion
**Actual**: TBD
**Owner**: TBD

**Purpose**:
- Achieve end-to-end behavior alignment with screenpipe for capture semantics, metadata fidelity, indexing freshness, and evidence-grounded retrieval/chat behaviors.

**Initial Scope (summary, detailed planning deferred)**:
- [ ] Capture-time metadata fidelity alignment (event semantics + timing guarantees).
- [ ] Indexing/search behavior alignment (freshness, ranking, and provenance visibility).
- [ ] Chat grounding/alignment parity where Phase 4 remains intentionally simplified.
- [ ] Cross-phase observability parity for long-run quality and reliability tracking.

**Go/No-Go Gates**:
- TBD (to be defined in dedicated Phase 8 planning document)

**Blockers**: Phase 7 completion

---

## Risk Dashboard

### High Risks (Active Monitoring)

| Risk | Phase | Probability | Impact | Status | Mitigation |
|------|-------|-------------|--------|--------|------------|
| FFmpeg crashes/hangs | Phase 1 | Medium | High | 🟨 Mitigated | Watchdog timer, auto-restart, fallback implemented |
| Frame-label drift pollutes retrieval grounding | Phase 2.6/2.7/3 | High | Critical | ⬜️ | Phase 2.6 governance lock + Phase 2.7 hard gate: source/confidence fields + strict filtering + quality SLA before Phase 3 kickoff |
| Chat grounding/evidence fabrication | Phase 4 | Medium | Critical | ⬜️ | Evidence must be sourced from real frames only; strict time bounds; server-side validation + curated eval set |
| Bulk upload too slow | Phase 5.3 | High | High | ⬜️ | Compression, multi-thread upload, progress UI |
| Network outage during migration | Phase 5 | Medium | Critical | ⬜️ | Checksum validation, resume capability, rollback |
| Client API latency high | Phase 5+ | Medium | Medium | ⬜️ | Pagination, metadata caching, async operations |
| Debian box disk full | Phase 5+ | Low | High | ⬜️ | Disk quota alerts, auto-cleanup >90 days |
| Deployment data loss | Phase 5 | Low | Critical | ⬜️ | Checksum verify, rollback drill, 7-day backup |
| Phase 5 延期超 Week 22 | Phase 5 | Medium | Critical | ⚠️ | 串行执行,严控 scope,weekly check-ins |

---

## Key Metrics Tracking

| Metric | Phase 1 Target | Phase 2 Target | Phase 2.6 Target | Phase 2.7 Target | Phase 3 Target | Phase 4 Target | Phase 5 Target |
|--------|----------------|----------------|------------------|------------------|----------------|----------------|----------------|
| **Performance** | Frame <2s | N/A (paused) | Freeze-scope modules show no unacceptable regression | Query p95 no regression; target +10%-20% | Search <500ms | Chat <5s | Upload <5min |
| **Accuracy** | OCR ≥95% | N/A (paused) | Freeze contract evidence complete (capture/processing/UI/retrieval boundaries auditable) | Label mismatch <=2%-5%; P@10 uplift >=20% vs baseline | P@10 ≥0.7 | Hallucination <10% | Checksum 100% |
| **Stability** | 7-day 0-crash | N/A (paused) | 24h stability evidence + rollback drill pass | No API compatibility or migration regression | N/A | N/A | >99.5% uptime |
| **Resource** | <5% CPU | N/A (paused) | Config/code drift audit = 0 unauthorized changes | CPU <=+12%, storage <=+10% | N/A | <$0.05/query | Queue <10 p95 |

**Current Baseline**: Phase 0 measured on 2026-02-06: migration <1s (10K entries), query overhead <10ms, rollback <1s, schema overhead <1MB, migration memory <1MB. Source: `v3/results/phase-0-validation.md`.

---

## Decision Log (Resolved Questions)

This section tracks questions that have been resolved through architectural decisions.

### ✅ Resolution 1: Vision-Only Chat Pivot + Audio Freeze (2026-02-23)

**Original Question**: Do we need to complete audio parity before building search/chat, or can we ship an evidence-based chat MVP using vision-only data?

**Decision**:
- **Vision-only** for Search/Chat (frames + OCR + metadata).
- **Audio Freeze**: Pause all audio development (capture/storage/search/chat parity).
- Rebaseline Phase 3/4/5 around: **Vision Search Parity → Vision Chat MVP → Deployment**.
- Align time semantics with screenpipe: user local timezone authority in UI, convert to epoch seconds for server filtering.

**Rationale**:
- Chat’s core user value comes from *retrievable evidence*, not modality count.
- Audio expands privacy surface area and operational complexity; pausing it reduces schedule risk.
- Vision-only keeps the product coherent: “what happened 14:00-17:00” is answerable from frames/OCR without inventing audio context.

**Screenpipe Reference**:
- Mention/time parsing: `screenpipe/apps/screenpipe-app-tauri/lib/chat-utils.ts`
- Dynamic system prompt (time + timezone): `screenpipe/apps/screenpipe-app-tauri/components/standalone-chat.tsx`
- Search API accepts `start_time/end_time` in UTC: `screenpipe/crates/screenpipe-server/src/routes/search.rs`

**Impact**:
- Supersedes the 2026-02-14 decision that made Phase 2.1 audio parity a hard precondition for Phase 3.
- Existing Phase 2.x implementation remains in repo, but is **frozen** and not on the MVP critical path.

---

### ✅ Resolution 2: Phase 2.1 Audio Parity Priority (2026-02-06, updated 2026-02-14) — SUPERSEDED

**Original Question**: Should Phase 2.1 remain optional speaker ID work, or become required audio parity alignment before search/chat?

**Decision (superseded)**: Phase 2.1 was defined as a required precondition before Phase 3.

**Rationale**:
- Audio parity reduces downstream data-quality risk for Phase 3 search relevance and Phase 4 chat grounding
- Keep alignment at architecture/behavior level while preserving Python + ONNX runtime choices
- Replace optional single-metric diarization scope with multi-dimensional parity gates for operational confidence

**Reference**: ADR-0004

---

### ✅ Resolution 3: P3 Memory Capability Definition (2026-02-06)

**Original Question**: What does "memory capability" (P3) actually mean?

**Decision**: A (Daily/Weekly Summaries) + C (Persistent Agent State)

**Rationale**:
- Summaries provide user value for reviewing past activity
- Agent state enables smarter chat with context memory
- Requires Phase 4 (Chat) foundation first
- Not MVP-critical, deferred to Phase 7 (Week 25+)

**Reference**: ADR-0003

---

### ✅ Resolution 4: Streaming Chat Priority (2026-02-06)

**Original Question**: Should streaming be added to Phase 4, or deferred to Phase 6+?

**Decision**: Phase 6+ (Week 23-24)

**Rationale**:
- Phase 4 delivers simple request-response first
- Streaming added in Phase 6 if on schedule

---

### ✅ Resolution 5: Execution Strategy (2026-02-06, updated 2026-02-24)

**Original Question**: Should Phase 2.6/2.7/3/4/5 run in parallel or serial?

**Decision**: SERIAL execution (Phase 2.6 → 2.7 → 3 → 4 → 5)

**Rationale**:
- Reduces complexity and coordination overhead
- Prioritizes stability over speed
- Adds explicit quality gate to reduce Phase 3 rework risk from frame-label drift

---

### ✅ Resolution 6: Phase 2.6 Hard Freeze Governance Before Phase 2.7 (2026-02-24)

**Original Question**: Should audio freeze remain a roadmap note, or become a standalone auditable gate?

**Decision**:
- Add standalone **Phase 2.6** between Phase 2.5 and Phase 2.7.
- Upgrade Phase 2.6 semantics from governance-only to governance + default full-chain pause contract.
- Define hard gates `2.6-G-*` for default capture pause, default processing pause, UI/retrieval contract lock, exception closure, and drift/rollback readiness.
- Allow only approved P0/P1 exception workflow with TTL, rollback, and closure evidence.

**Rationale**:
- Prevents governance controls from being mixed into feature-change phases.
- Improves traceability, auditability, and incident handling.
- Reduces noise contamination and accidental audio-surface expansion before Phase 2.7 quality evidence collection.

---

### ✅ Resolution 7: Phase 2.7 Hard Gate Before Vision Search (2026-02-24)

**Original Question**: Should frame-label consistency be handled inside Phase 3 or as a standalone gate?

**Decision**:
- Add standalone **Phase 2.7** before Phase 3.
- Treat Phase 2.7 as hard gate with quantitative acceptance criteria.
- Adopt structural alignment with screenpipe principles (metadata provenance, dedup/index discipline, quality-first filtering), not full event-driven rewrite in this phase.

**Rationale**:
- Current chunk-level fallback creates semantic drift and noisy retrieval evidence.
- Search and chat quality depend on trustworthy per-frame context.
- Hard-gate governance lowers downstream rework and user-trust risk.

---

### ✅ Resolution 8: Retire Former Mid-Phase Metadata Track and Introduce Phase 8 (2026-02-24)

**Original Question**: Should we keep the former mid-phase metadata-signal track, or split strategy into MVP pre-hardening + Post-MVP full alignment?

**Decision**:
- Remove standalone former mid-phase metadata-signal track from roadmap.
- Keep **Phase 2.7** as MVP pre-Phase-3 hardening (new-data-only scope).
- Add **Phase 8** as required Post-MVP phase for full screenpipe alignment.

**Rationale**:
- Avoid overlap and ambiguous ownership between former metadata track and Phase 2.7.
- Keep MVP critical path focused and measurable.
- Preserve a clear, explicit path for full alignment after MVP.

---

## Open Questions (Active)

The following open questions are currently active and must be resolved before corresponding execution gates:

1. **Phase 2.6 evidence granularity**: What exact artifact schema is required for exception-closure evidence so that review is deterministic?
2. **Phase 2.7 baseline lock**: Which concrete dataset snapshot ID is frozen as the Phase 1.5 comparison baseline for mismatch/P@10 checks?
3. **Phase 3 browse semantics transition**: During migration from empty-q=empty-payload to empty-q=browse-feed, what compatibility notice window is required for existing callers?

**Review Trigger**: Update this section whenever a question is resolved, superseded, or newly discovered.

---

## Change Log

| Date | Type | Description | Impact |
|------|------|-------------|--------|
| 2026-02-24 | Freeze Contract Upgrade | Upgraded Phase 2.6 from governance-only to governance + default full-chain pause contract (`no auto capture/processing`, `no default audio UI`, `no Search/Chat audio grounding`) and removed dependency on missing plan file. | Clarifies default behavior boundary and closes governance/documentation gap before Phase 2.7 |
| 2026-02-24 | Governance Hardening | Added Phase 2.6 Audio Freeze Governance as a standalone hard gate with explicit exception workflow and evidence contract. | Converts freeze from status text to auditable control; Phase 2.7 start now gated by `2.6-G-*` closure |
| 2026-02-24 | Scope Hardening | Added Phase 2.7 Frame Label Alignment as hard pre-Phase-3 gate; introduced explicit frame metadata quality and indexing alignment targets. | Reduces retrieval noise risk before Search/Chat scaling; sequence updated to R1-R11 |
| 2026-02-24 | Roadmap Refactor | Removed former mid-phase metadata track, added required Post-MVP Phase 8 (Full Screenpipe Alignment), and constrained Phase 2.7 to new-data-only (`timestamp >= T0`). | Eliminates phase overlap, clarifies ownership, and stabilizes MVP gate semantics |
| 2026-02-23 | Scope Pivot | Vision-only Chat pivot + Audio Freeze; Phase 3/4/5 rebaselined (Vision Search → Vision Chat → Deployment). Phase 2.1 no longer gates Phase 3. | Audio removed from MVP critical path; schedule risk reduced |
| 2026-02-14 | Roadmap Rebaseline *(superseded)* | Phase 2.1 redefined to `Audio Parity with screenpipe` (Week 9-12), no longer optional; downstream phases shifted by +2 weeks | Superseded by 2026-02-23 vision-only pivot |
| 2026-02-06 | Priority Change | P0: Chat → Multi-modal capture | +2 weeks to first chat demo, better foundation |
| 2026-02-06 | User Decision | Chat mode: Streaming → Simple request-response | -3 days to Phase 4 completion |
| 2026-02-06 | User Decision | Audio scope: Align with screenpipe (full stack) | +1 week to Phase 2, better capability |
| 2026-02-06 | User Decision | Deployment timeline: 20周硬约束(约5个月) *(superseded by 2026-02-14 rebaseline)* | Superseded by Week 22 critical path |
| 2026-02-06 | Architecture Decision | Thin client architecture for Phase 5 | All data on Debian server, Phase 0 must be remote-first |
| 2026-02-06 | User Decision | Phase 2.1 Speaker ID: Confirmed OPTIONAL *(superseded by 2026-02-14 parity decision)* | Replaced by required Phase 2.1 parity work |
| 2026-02-06 | User Decision | P3 Memory scope: A+C (Summaries + Agent State) | Deferred to Phase 7 (Week 25+) |
| 2026-02-06 | Roadmap Addition | Phase 6: Streaming Chat (Week 23-24) | +2 weeks for streaming capability |
| 2026-02-06 | Roadmap Addition | Phase 7: Memory Capabilities (Week 25+, 延后实施) | Future feature, gates defined post-Phase 4 |
| 2026-02-06 | Documentation Fix | Roadmap consistency pass: unified timeline (20周), fixed Search priority, clarified execution strategy | Resolved 12 documentation conflicts |
| 2026-02-06 | Phase 0 Planning | Phase 0 detailed plan produced (`02-phase-0-detailed-plan.md`), roadmap Phase 0 section expanded with 21 progress items and 19 gate IDs, validation template created | Phase 0 ready to execute |
| 2026-02-06 | Phase 0 Complete | All 19 Phase 0 gates passed (155 tests, 0 failures). 20 new files, 5 modified files, 2 governance docs. Go decision confirmed. | Phase 1 unblocked |
| 2026-02-06 | Baseline Freeze | Phase 0 result frozen and baseline tagged (`v3-phase0-go`) on branch `v3.0-p0` | Stable rollback point for Phase 1+ |
| 2026-02-06 | Phase 1 Engineering | All Phase 1 code + tests implemented (15 source files, 8 test files, 254 passed/9 skipped/0 failures). 13/21 gates passed. 7 pending long-run evidence. Go/No-Go: NO-GO (pending calendar-time evidence) | Phase 2 unblocked for planning; long-run evidence collection required |
| 2026-02-07 | Phase 1 Post-Baseline Hardening | Added regression fixes for consumer dispatch, legacy upload forwarding, search debug rendering, runtime pause/resume semantics, and OCR startup warm-up; aligned docs/config authority for 60s chunk duration | Improves operational stability and troubleshooting clarity while keeping Phase 1 gate state unchanged |
| 2026-02-07 | WebUI Documentation Governance | Added dedicated `v3/webui` documentation hub (route map/dataflow/comparison/page docs/templates) and linked maintenance rule into results workflow | Keeps phase results and WebUI behavior docs synchronized and auditable |
| 2026-02-08 | Phase 1.5 Metadata Precision | Frame metadata resolver (A), focused/browser_url pipeline (B), OCR engine true value (C), offset guard (D), v3_005 migration, API v1 search compatibility serialization, 33 tests (170 total passed) | Precise per-frame metadata, NULL semantics, pre-insertion validation, real OCR engine name, additive API compatibility |
| 2026-02-09 | Status Update | Phase 1 marked complete; 7 long-run observations moved to future non-blocking plan (Week 9-12 tracking) | Unblocks Phase 2 execution while preserving long-run evidence collection |
| 2026-02-09 | Phase 2.0 Planning | Phase 2.0 detailed plan produced (`04-phase-2-detailed-plan.md`), roadmap Phase 2.0 section expanded with 10-day progress breakdown, 17 gate IDs, validation template created | Phase 2.0 ready to execute on 2026-02-09 |
| 2026-02-12 | Phase 2.5 Planning | Phase 2.5 detailed plan produced (`05-phase-2.5-webui-audio-video-detailed-plan.md`): 2 new dashboard pages (`/audio`, `/video`), 6 new API endpoints, navigation update, 12 WBs, 15 gate checks, 4 test files (~35 tests), validation template created | Phase 2.5 ready to execute; can run in parallel with 2-S-01 observation |
| 2026-02-12 | Phase 2.5 Complete | All 15 Phase 2.5 gates PASS (2 GATING + 13 Non-Gating). 59 new tests (30 API + 8 audio page + 8 video page + 13 nav). Full regression: 553 passed, 0 failed. `/audio` + `/video` dashboards with Alpine.js SSR pattern, 6 new API endpoints, path traversal prevention. | Phase 2.5 engineering closed; Phase 2.1 or Phase 3 unblocked |

---

## Execution Strategy

### Serial vs Parallel Execution

**Decision**: MVP path (Phase 2.6, Phase 2.7, Phase 3, Phase 4, Phase 5) and Post-MVP path (Phase 6, Phase 7, Phase 8) both execute SERIALLY (not in parallel).

**Rationale**:
1. **Complexity Reduction**: Eliminates resource conflicts, coordination overhead, and parallel debugging challenges
2. **Quality Focus**: Each phase can be fully validated before the next begins
3. **Single-Person Team**: Serial execution aligns better with solo development workflow
4. **Schedule Control**: Week 22 remains the outer bound; serial execution keeps the critical path stable under the vision-only pivot

**Timeline Impact**:
- Previous plan (serial + audio parity): 22 weeks (Week 22)
- Revised MVP plan (vision-only serial + Phase 2.6/2.7 hard gates): executed as `R1-R11` (Week 22 retained as outer buffer)
- Post-MVP plan: serial `6 -> 7 -> 8` to keep integration and reliability validation tractable

**Sequence**:
```
MVP:
R1:    Phase 2.6 (Audio Freeze Governance)
R2:    Phase 2.7 (Frame Label Alignment Gate)
R3-R4: Phase 3 (Vision Search Parity)
R5-R6: Phase 4 (Vision Chat MVP)
R7-R11: Phase 5 (Deployment Migration)

Post-MVP:
6 -> 7 -> 8
```

**Cross-Phase Dependencies**:
- Phase 2.7 depends on Phase 2.6 governance hard-gate completion
- Phase 3 depends on Phase 2.7 hard-gate completion
- Phase 4 depends on Phase 3 completion (bounded vision retrieval/search needed for chat grounding)
- Phase 5 depends on Phase 4 completion (chat/search must work remotely)
- Phase 7 depends on Phase 6 completion
- Phase 8 depends on Phase 7 completion

---

## Next Review

**Scheduled Reviews**:

1. **✅ Week 2 End (Phase 0 Verification) — Completed 2026-02-06**
   - Phase 0 completion confirmed (19/19 gates passed)
   - Remote-first foundation verified for Phase 5 path

2. **Week 4 End (Phase 1 Midpoint Check)**
   - ~~Verify recording → extraction → OCR pipeline is functionally connected~~
   - ~~Validate early performance signals (CPU, extraction latency, indexing latency)~~
   - **Completed early**: All Phase 1 engineering done in single session (2026-02-06)

3. **Week 6 End (Phase 1 Go/No-Go)**
   - ~~Confirm all Phase 1 gates passed (functional/performance/quality/stability/resource/degradation/governance)~~
   - **Completed with decision update (2026-02-09)**: Phase 1 marked complete; 13 passed, 7 long-run observations moved to future non-blocking plan
   - Remaining evidence tracked under `Phase 1 Long-Run Observation Plan (Future, Non-Blocking)`

4. **R2 Checkpoint (Phase 2.7 Go/No-Go)**
   - Validate Phase 2.6 closure evidence (`2.6-G-*`) and exception log closure
   - Confirm Phase 2.7 can start with stable freeze boundary

5. **R4 Checkpoint (Phase 3 Go/No-Go)**
   - Validate vision search parity gates (bounded time-range filtering, UX drill-down, p95 latency)
   - Confirm Chat grounding has safe retrieval primitives (no unbounded scans)

6. **R6 Checkpoint (Phase 4 Go/No-Go)**
   - Validate Chat MVP gates (time-range summary + evidence[] correctness)
   - Confirm timezone semantics are correct (browser-local authority → epoch seconds)

7. **R10 Checkpoint (Phase 5 Go/No-Go)**
   - Confirm remote deployment cutover + rollback drill completed
   - Verify remote deployment quality targets are met

8. **Week 22 End (Buffer / Final MVP Validation)**
   - Use remaining time buffer for hardening, regressions, and long-run evidence collection
   - If Phase 5 slips, Week 22 remains the hard deadline for MVP sign-off

**Review Frequency**: Weekly (bi-weekly acceptable if on track)
