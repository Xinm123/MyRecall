# MyRecall-v3 Roadmap Status Tracker

**Last Updated**: 2026-02-06
**Overall Status**: 🟨 Phase 0 Planning Complete / Ready to Execute
**Target Completion**: Week 20 (2026-06-20) for MVP (P0-P4 deployed). Phase 5 deployment starts Week 16. Week 23+ for P7 Memory (不与Phase 6 Week 21-22重叠).

---

## Timeline Overview

**Timeline Start**: 2026-02-06 (Week 1)

```
Phase 0: Foundation            [Week 1-2]   ⬜️⬜️
Phase 1: Video Recording       [Week 3-6]   ⬜️⬜️⬜️⬜️
Phase 2.0: Audio MVP           [Week 7-8]   ⬜️⬜️
Phase 2.1: Speaker ID          [Week 9-10]  ⬜️⬜️ (OPTIONAL - decide after 2.0)
Phase 3: Multi-Modal Search    [Week 11-12] ⬜️⬜️
Phase 4: Chat                  [Week 13-15] ⬜️⬜️⬜️
Phase 5: Deployment (SERIAL)   [Week 16-20] ⬜️⬜️⬜️⬜️⬜️ (CRITICAL PATH)
Phase 6: Streaming Chat        [Week 21-22] ⬜️⬜️ (FUTURE)
Phase 7: Memory (A+C)          [Week 23+]   ⬜️⬜️⬜️ (FUTURE, 延后实施)

Legend: ⬜️ Not Started | 🟨 In Progress | 🟩 Complete | 🟥 Blocked

**Execution Strategy**: Phase 3/4/5 execute SERIALLY (not in parallel) to reduce complexity and ensure stability.
```

---

## Phase Status Details

### Phase 0: Foundation & Client-Server Boundary
**Status**: 🟨 Planning Complete / Ready to Execute
**Planned**: Week 1-2 (2026-02-06 to 2026-02-19, 10 working days)
**Actual**: TBD
**Owner**: Solo Developer (infrastructure setup)
**Detailed Plan**: `/Users/pyw/new/MyRecall/v3/plan/02-phase-0-detailed-plan.md`

**Execution Tracks**:
- Track A (Day 1-4): Schema, migration, rollback, Pydantic models
- Track B (Day 3-7): API v1 versioning, auth placeholder, pagination, upload queue
- Track C (Day 5-10): Config matrix, data governance, integration testing, gate validation

**Progress**:
- [ ] Day 1: v3 SQL schema DDL (video_chunks, frames, ocr_text, audio_chunks, audio_transcriptions, schema_version)
- [ ] Day 1: Migration runner with timing/memory checks
- [ ] Day 1: Governance columns on existing `entries` table (created_at, expires_at)
- [ ] Day 2: Rollback script (drop v3 tables, restore original state)
- [ ] Day 2: SHA256 integrity verification utility
- [ ] Day 2: Migration + rollback integration tests
- [ ] Day 3: Pydantic models (VideoChunk, Frame, OcrText, AudioChunk, AudioTranscription)
- [ ] Day 3: PaginatedResponse generic wrapper (ADR-0002)
- [ ] Day 4: `/api/v1/*` Flask blueprint with pagination
- [ ] Day 4: `@require_auth` placeholder decorator
- [ ] Day 4: Blueprint registration (v1 + legacy coexistence)
- [ ] Day 5: UploadQueue class (100GB capacity, 7-day TTL, FIFO, exponential backoff)
- [ ] Day 5: UploaderConsumer backoff update to ADR-0002 schedule
- [ ] Day 6: Configuration matrix (local/remote/debian_client/debian_server)
- [ ] Day 6: Template .env files per deployment mode
- [ ] Day 7: PII Classification Policy document
- [ ] Day 7: Retention Policy Design document
- [ ] Day 8: Full backward compatibility integration test (upload -> query -> search)
- [ ] Day 8: Query overhead benchmark (<10ms gate)
- [ ] Day 9: Gate validation suite (19 gate tests)
- [ ] Day 10: Documentation updates, code cleanup, Go/No-Go review

**Go/No-Go Gates** (authority: `v3/metrics/phase-gates.md`):
- [ ] F-01: Schema migration success (all 5 new tables created)
- [ ] F-02: 100% backward compatibility (existing screenshot pipeline works)
- [ ] F-03: API versioning (`/api/v1/*` functional, `/api/*` aliases work)
- [ ] F-04: Configuration matrix (4 deployment modes configurable)
- [ ] P-01: Migration <5s for 10K entries
- [ ] P-02: Query overhead <10ms added by schema changes
- [ ] S-01: Zero data loss during migration (SHA256 checksum)
- [ ] S-02: Rollback restores original state in <2 minutes
- [ ] R-01: Migration <500MB RAM
- [ ] R-02: Schema overhead <10MB
- [ ] DG-01: PII Classification Policy documented
- [ ] DG-02: Encryption schema design (encrypted column)
- [ ] DG-03: Retention policy design (created_at, expires_at)
- [ ] DG-04: API authentication placeholder on all v1 routes
- [ ] UQ-01: Buffer 100GB capacity enforcement (FIFO)
- [ ] UQ-02: TTL cleanup (>7 days auto-deleted)
- [ ] UQ-03: FIFO deletion order
- [ ] UQ-04: Post-upload deletion within 1s
- [ ] UQ-05: Retry exponential backoff (1min->5min->15min->1h->6h)

**Blockers**: None

---

### Phase 1: Screen Recording Pipeline
**Status**: ⬜️ Not Started
**Planned**: Week 3-6 (4 weeks)
**Actual**: TBD
**Owner**: Solo Developer (core pipeline implementation)

**Progress**:
- [ ] VideoRecorder class (FFmpeg-based)
- [ ] Frame extraction worker
- [ ] OCR pipeline integration
- [ ] Timeline API (`/api/v1/timeline`)
- [ ] Client uploader refactor (resume capability)

**Go/No-Go Gates**:
- [ ] 1-hour recording → searchable timeline
- [ ] Frame extraction <2s/frame
- [ ] OCR accuracy ≥95%
- [ ] 7-day zero-crash test
- [ ] Recording <5% CPU, <50GB/day

**Blockers**: Waiting for Phase 0 completion

---

### Phase 2.0: Audio MVP (No Speaker ID)
**Status**: ⬜️ Not Started
**Planned**: Week 7-8 (2 weeks)
**Actual**: TBD
**Owner**: Solo Developer (audio capture & transcription)

**Progress**:
- [ ] Audio capture (sounddevice: system + mic)
- [ ] VAD filtering (py-webrtcvad)
- [ ] Whisper transcription (faster-whisper)
- [ ] Audio FTS indexing
- [ ] Unified timeline API (video + audio)

**Go/No-Go Gates**:
- [ ] 1-hour recording → searchable audio
- [ ] Transcription WER ≤15%
- [ ] Transcription keeps up with 30s segments
- [ ] Audio recording <3% CPU

**Blockers**: Waiting for Phase 1 completion

---

### Phase 2.1: Speaker Identification (OPTIONAL)
**Status**: ⬜️ Not Started (OPTIONAL - User decides after Phase 2.0)
**Planned**: Week 9-10 (2 weeks) - IF NEEDED
**Actual**: TBD
**Owner**: TBD
**Decision**: ✅ CONFIRMED OPTIONAL (user can skip entirely)
**Decision Trigger**: After Phase 2.0 validation (Week 8)

**Progress**:
- [ ] Speaker diarization (pyannote-audio)
- [ ] Speaker embedding & clustering
- [ ] Cross-device audio deduplication

**Go/No-Go Gates**:
- [ ] Speaker DER ≤20%
- [ ] Clustering stable over 24 hours

**Blockers**: Phase 2.0 completion + user decision on priority

---

### Phase 3: Multi-Modal Search Integration
**Status**: ⬜️ Not Started
**Planned**: Week 11-12 (2 weeks)
**Actual**: TBD
**Owner**: Tech Lead (architecture + integration)

**Progress**:
- [ ] Unified search API (content_type: vision|audio|all)
- [ ] Timeline-aware search (time range filters)
- [ ] Cross-modal ranking
- [ ] Web UI (interleaved results)

**Go/No-Go Gates**:
- [ ] Search returns relevant results (vision + audio)
- [ ] Precision@10 ≥0.7
- [ ] Search latency <500ms p95

**Blockers**: Phase 2.0 completion

---

### Phase 4: Chat Capability
**Status**: ⬜️ Not Started
**Planned**: Week 13-15 (3 weeks)
**Actual**: TBD
**Owner**: Tech Lead (LLM integration)

**Progress**:
- [ ] LLM integration (OpenAI + Ollama)
- [ ] Tool definition: `search_timeline`
- [ ] Tool execution with strict truncation
- [ ] Chat API endpoint (`POST /api/v1/chat`)
- [ ] Web UI `/chat` page
- [ ] Natural language time parsing

**Go/No-Go Gates**:
- [ ] Chat answers "what did I work on yesterday?"
- [ ] Hallucination rate <10%
- [ ] Chat response <5s median
- [ ] Cost <$0.05/query

**Blockers**: Phase 3 completion

**Note**: Phase 4 delivers simple request-response chat. Streaming is deferred to Phase 6.

---

### Phase 5: Deployment Migration (SERIAL, after Phase 3-4)
**Status**: ⬜️ Not Started
**Planned**: Week 16-20 (5 weeks)
**Actual**: TBD
**Owner**: Solo Developer + Product Owner (deployment & validation)
**Priority**: 🔴 CRITICAL PATH (5-month hard deadline)

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
- [ ] Phase 5.0: Remote API Readiness Audit (Week 16) - validate Phase 0-4 APIs are remote-ready
- [ ] Phase 5.1: Local-Remote Simulation (Week 17) - 50ms latency testing
- [ ] Phase 5.2: Server Containerization (Week 18) - Dockerfile + docker-compose
- [ ] Phase 5.3: Bulk Data Upload (Week 19) - migrate all existing local data
- [ ] Phase 5.4: Client Refactor (Week 19-20) - remove local DB, switch to API-only, parallel with 5.3 second half
- [ ] Phase 5.5: Gray Release & Cutover (Week 20)

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
**Planned**: Week 21-22 (2 weeks)
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
**Planned**: Week 23+ (TBD)
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

## Risk Dashboard

### High Risks (Active Monitoring)

| Risk | Phase | Probability | Impact | Status | Mitigation |
|------|-------|-------------|--------|--------|------------|
| FFmpeg crashes/hangs | Phase 1 | Medium | High | ⬜️ | Watchdog timer, auto-restart, fallback |
| Whisper too slow (CPU) | Phase 2 | High | High | ⬜️ | faster-whisper, GPU accel, batch processing |
| Bulk upload too slow | Phase 5.3 | High | High | ⬜️ | Compression, multi-thread upload, progress UI |
| Network outage during migration | Phase 5 | Medium | Critical | ⬜️ | Checksum validation, resume capability, rollback |
| Client API latency high | Phase 5+ | Medium | Medium | ⬜️ | Pagination, metadata caching, async operations |
| Debian box disk full | Phase 5+ | Low | High | ⬜️ | Disk quota alerts, auto-cleanup >90 days |
| Deployment data loss | Phase 5 | Low | Critical | ⬜️ | Checksum verify, rollback drill, 7-day backup |
| Phase 5 延期超 Week 20 | Phase 5 | Medium | Critical | ⚠️ | 串行执行,严控 scope,weekly check-ins |

---

## Key Metrics Tracking

| Metric | Phase 1 Target | Phase 2 Target | Phase 3 Target | Phase 4 Target | Phase 5 Target |
|--------|----------------|----------------|----------------|----------------|----------------|
| **Performance** | Frame <2s | Transcribe <30s | Search <500ms | Chat <5s | Upload <5min |
| **Accuracy** | OCR ≥95% | WER ≤15% | P@10 ≥0.7 | Hallucination <10% | Checksum 100% |
| **Stability** | 7-day 0-crash | 24h 0-crash | N/A | N/A | >99.5% uptime |
| **Resource** | <5% CPU | <3% CPU | N/A | <$0.05/query | Queue <10 p95 |

**Current Baseline**: TBD (measure after Phase 0)

---

## Decision Log (Resolved Questions)

This section tracks questions that have been resolved through architectural decisions.

### ✅ Resolution 1: Phase 2.1 Speaker ID Priority (2026-02-06)

**Original Question**: Is speaker identification required for MVP, or truly optional?

**Decision**: OPTIONAL - User decides after Phase 2.0 validation (Week 8)

**Rationale**:
- Speaker ID adds 2 weeks + complexity
- Value depends on use case (meetings vs solo work)
- Better to validate Phase 2.0 audio quality first

**Reference**: ADR-0004

---

### ✅ Resolution 2: P3 Memory Capability Definition (2026-02-06)

**Original Question**: What does "memory capability" (P3) actually mean?

**Decision**: A (Daily/Weekly Summaries) + C (Persistent Agent State)

**Rationale**:
- Summaries provide user value for reviewing past activity
- Agent state enables smarter chat with context memory
- Requires Phase 4 (Chat) foundation first
- Not MVP-critical, deferred to Phase 7 (Week 23+)

**Reference**: ADR-0003

---

### ✅ Resolution 3: Streaming Chat Priority (2026-02-06)

**Original Question**: Should streaming be added to Phase 4, or deferred to Phase 6+?

**Decision**: Phase 6+ (Week 21-22)

**Rationale**:
- Phase 4 delivers simple request-response first
- Streaming added in Phase 6 if on schedule

---

### ✅ Resolution 4: Execution Strategy (2026-02-06)

**Original Question**: Should Phase 3/4/5 run in parallel or serial?

**Decision**: SERIAL execution (Phase 3 → 4 → 5)

**Rationale**:
- Reduces complexity and coordination overhead
- Prioritizes stability over speed
- Timeline extends to 5 months (Week 20) - acceptable tradeoff

---

## Open Questions (Active)

✅ **All Open Questions resolved as of 2026-02-06.** (See Changelog line 374-383 for all resolved decisions)

**Review Trigger**: Add new questions here when discovered during Phase 0+ execution.

---

## Change Log

| Date | Type | Description | Impact |
|------|------|-------------|--------|
| 2026-02-06 | Priority Change | P0: Chat → Multi-modal capture | +2 weeks to first chat demo, better foundation |
| 2026-02-06 | User Decision | Chat mode: Streaming → Simple request-response | -3 days to Phase 4 completion |
| 2026-02-06 | User Decision | Audio scope: Align with screenpipe (full stack) | +1 week to Phase 2, better capability |
| 2026-02-06 | User Decision | Deployment timeline: 20周硬约束(约5个月) | Phase 5 (Week 16-20) becomes critical path |
| 2026-02-06 | Architecture Decision | Thin client architecture for Phase 5 | All data on Debian server, Phase 0 must be remote-first |
| 2026-02-06 | User Decision | Phase 2.1 Speaker ID: Confirmed OPTIONAL | Can save 2 weeks if not needed |
| 2026-02-06 | User Decision | P3 Memory scope: A+C (Summaries + Agent State) | Deferred to Phase 7 (Week 23+) |
| 2026-02-06 | Roadmap Addition | Phase 6: Streaming Chat (Week 21-22) | +2 weeks for streaming capability |
| 2026-02-06 | Roadmap Addition | Phase 7: Memory Capabilities (Week 23+, 延后实施) | Future feature, gates defined post-Phase 4 |
| 2026-02-06 | Documentation Fix | Roadmap consistency pass: unified timeline (20周), fixed Search priority, clarified execution strategy | Resolved 12 documentation conflicts |
| 2026-02-06 | Phase 0 Planning | Phase 0 detailed plan produced (`02-phase-0-detailed-plan.md`), roadmap Phase 0 section expanded with 21 progress items and 19 gate IDs, validation template created | Phase 0 ready to execute |

---

## Execution Strategy

### Serial vs Parallel Execution

**Decision**: Phase 3, Phase 4, and Phase 5 will execute SERIALLY (not in parallel).

**Rationale**:
1. **Complexity Reduction**: Eliminates resource conflicts, coordination overhead, and parallel debugging challenges
2. **Quality Focus**: Each phase can be fully validated before the next begins
3. **Single-Person Team**: Serial execution aligns better with solo development workflow
4. **Acceptable Tradeoff**: 5-month timeline (Week 20) is acceptable vs. risk of parallel execution failures

**Timeline Impact**:
- Original plan (parallel): 15 weeks
- Adjusted plan (serial): 20 weeks
- Tradeoff: +5 weeks for stability and reduced risk

**Sequence**:
```
Week 11-12: Phase 3 (Multi-Modal Search)
Week 13-15: Phase 4 (Chat Capability)
Week 16-20: Phase 5 (Deployment Migration)
```

**Cross-Phase Dependencies**:
- Phase 4 depends on Phase 3 completion (multi-modal search needed for chat tool)
- Phase 5 depends on Phase 4 completion (all features must work remotely, including chat)

---

## Next Review

**Scheduled Reviews**:

1. **Week 2 End (Phase 0 Verification)**
   - Confirm Phase 0 completion (API versioning, DB migration, config matrix ready)
   - Validate that Phase 0-4 are properly designed for remote-first in Phase 5

2. **Week 8 (Phase 2.1 User Decision)**
   - Review Phase 2.0 validation results (Whisper WER, VAD effectiveness, audio sync)
   - User decides: Proceed with Phase 2.1 Speaker ID (Week 9-10) or skip to Phase 3
   - Reference: ADR-0004 decision criteria

3. **Week 15 End (Pre-Phase 5 Kickoff Checkpoint)**
   - Confirm all P0-P4 gates passed
   - Verify Phase 5 deployment readiness
   - Final go/no-go decision for Week 16 Phase 5 kickoff

4. **Week 20 End (MVP Validation After Phase 5 Completion)**
   - Confirm Phase 5 cutover and rollback drill completed
   - Verify remote deployment quality targets are met

**Review Frequency**: Weekly (bi-weekly acceptable if on track)
