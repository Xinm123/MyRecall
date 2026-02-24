# ADR-0002: Thin Client Architecture

**Status**: Approved

**Date**: 2026-02-06

**Deciders**: User + AI Architect
**SupersededBy**: N/A
**Supersedes**: N/A
**Scope**: target

---

## Context

MyRecall v3's Phase 5 plans to migrate the deployment model from a single-machine localhost setup (client + server on same PC) to a distributed setup where the server runs on a Debian box accessible over WAN.

The original design left open the question of where data resides after migration:
- Option A: **Thin client** - all data on Debian server only
- Option B: **Hybrid** - master copy on server, cache on clients
- Option C: **Replicated** - full database replicated on both sides

## Decision

We will adopt a **thin client architecture** where:

1. **Clients have NO local database** (no SQLite, no LanceDB, no persistent storage)
2. **Clients have NO local processing** (no OCR, no Whisper, no Search indexing)
3. **Clients HAVE temporary upload queue buffering** (see Local Buffering Policy below)
4. **All data operations go through remote API**
5. **Phase 0-4 run on localhost**, but APIs must be designed with remote-first assumptions

---

## Local Buffering Policy

### Purpose

Allow clients to temporarily buffer captured data (video/audio chunks) when the network is unavailable, avoiding data loss during transient connectivity issues.

### Scope

**Allowed**:
- Raw video chunks (未OCR的 .mp4 files)
- Raw audio chunks (未转录的 .wav files)
- Upload queue metadata (chunk ID, timestamp, upload retry count)

**Prohibited**:
- Database (SQLite, LanceDB) - all queries must go to server
- Processed data (OCR text, transcriptions, embeddings) - processing happens on server
- Search indexes (FTS, vector indexes) - indexing happens on server
- Long-term storage (>7 days) - buffering is temporary only

### Constraints

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Maximum Capacity** | 100GB | ~2 days of recording (50GB/day) |
| **TTL (Time-to-Live)** | 7 days | Prevents disk bloat if server is down for a week |
| **Deletion Policy** | FIFO (oldest first) | When capacity reached, delete oldest buffered chunks |
| **Post-Upload Behavior** | Immediate deletion | Once uploaded successfully, delete local copy |
| **Encryption** | Filesystem encryption | macOS FileVault / Linux LUKS (not app-layer) |
| **Retry Logic** | Exponential backoff | 1min → 5min → 15min → 1h → 6h |

### Implementation

```python
class UploadQueue:
    def __init__(self, buffer_dir="/tmp/myrecall_buffer", max_size_gb=100):
        self.buffer_dir = buffer_dir
        self.max_size = max_size_gb * 1024 * 1024 * 1024  # bytes

    def enqueue(self, chunk_path):
        # Check capacity, delete oldest if needed
        if self.get_total_size() > self.max_size:
            self.delete_oldest()

        # Move chunk to buffer directory
        shutil.move(chunk_path, self.buffer_dir)

    def upload_with_retry(self):
        # Exponential backoff: 1min, 5min, 15min, 1h, 6h
        for chunk in self.get_pending_chunks():
            try:
                response = upload_chunk_to_server(chunk)
                if response.status_code == 200:
                    os.remove(chunk)  # Delete after successful upload
            except NetworkError:
                chunk.retry_count += 1
                chunk.next_retry = calculate_backoff(chunk.retry_count)
```

### Verification

**Phase 0 Gates** (规划状态,待相应阶段执行时验证):
- [ ] Upload queue correctly buffers chunks when server offline
- [ ] FIFO deletion works when capacity exceeded
- [ ] Retry logic follows exponential backoff
- [ ] Successful uploads delete local copy within 1 second

**Phase 5 Gates** (规划状态,待相应阶段执行时验证):
- [ ] Client can buffer 100GB without crashing
- [ ] 7-day TTL cleanup runs daily
- [ ] Network reconnect resumes upload queue automatically

---

## Rationale

### Why Thin Client?

1. **Single source of truth**: No sync conflicts, no data consistency issues
2. **Simplified client**: No database maintenance, version upgrades, or schema migrations on client
3. **Multi-client support**: Easy to support multiple PCs → 1 central server
4. **Centralized backup**: Data backup and security policies enforced at one location
5. **User use case**: Single-user system doesn't need local caching for "offline work"

### Why NOT Hybrid/Replicated?

- **Hybrid**: Adds sync complexity, cache invalidation logic, conflict resolution
- **Replicated**: Unnecessary overhead for single-user use case, adds operational burden

## Consequences

### Positive ✅

- Client becomes lightweight (no DB engine, no storage management)
- Centralized data governance (encryption, backup, retention all at server)
- Easier to support future multi-device scenarios
- Clear separation of concerns (client = capture/upload/UI, server = storage/processing/search)

### Negative ❌

- **Network dependency**: No offline mode - client requires server connectivity
- **Upload bandwidth critical**: Video/audio files are large (gigabytes per day)
- **API latency**: All operations (search, timeline, chat) affected by network latency
- **Phase 0 impact**: Must design APIs for remote from day 1, even though running localhost

### Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Network unavailable | Client UI shows "offline" state, queues uploads for retry |
| Upload too slow | Compression (H.264), multi-threaded upload, chunked upload with resume |
| API latency high (search/timeline) | Pagination, metadata caching in client memory, async prefetch |
| Migration data loss | Checksum validation, rollback plan, 7-day backup retention |

## Alternatives Considered

### Option B: Hybrid Cache
- **Pros**: Offline capability, lower latency for recent data
- **Cons**: Sync complexity, cache invalidation bugs, increased client storage
- **Rejected**: Not worth the complexity for single-user use case

### Option C: Full Replication
- **Pros**: Full offline capability, zero API latency
- **Cons**: Heavy client storage, sync conflicts, operational burden
- **Rejected**: Defeats the purpose of remote deployment

## Implementation Notes

### Phase 0 (Foundation) Implications

**CRITICAL**: Phase 0 API design must assume remote server from the start:

1. **API Versioning**: `/api/v1/` prefix, versioned endpoints
2. **Pagination**: All list endpoints must paginate (limit/offset or cursor)
3. **Authentication**: JWT or API key even in localhost (migrate to actual auth in Phase 5)
4. **Compression**: Response compression headers (gzip)
5. **Stateless**: No server-side session state (RESTful principles)

### Phase 5 Migration Plan

**5.0**: API design audit - verify remote-first compliance
**5.1**: Network latency simulation (50ms) - test performance degradation
**5.2**: Server containerization (Docker + docker-compose)
**5.3**: Bulk data upload - migrate ALL existing local data to Debian server
**5.4**: Client refactor - remove SQLite/LanceDB/local storage code
**5.5**: Gray release + cutover (1 test PC → all clients)

## Success Criteria

(目标值已定义,待Phase 5执行期间验证):
- [ ] All Phase 0-4 features work with remote server (latency < 500ms p95)
- [ ] Upload throughput >1GB per 5 minutes
- [ ] Upload success rate >95% over 24 hours
- [ ] Zero data loss (checksums verified)
- [ ] Rollback drill successful (<1 hour to revert to localhost)

## Related ADRs

- ADR-0001: Python-First Principle
- ADR-0003: P3 Memory Scope Definition (depends on Phase 5 completion)

## References

- Phase 5 detailed plan: `v3/milestones/roadmap-status.md#phase-5-deployment-migration-serial-after-phase-3-4`
- Master prompt deployment constraints: `v3/plan/00-master-prompt.md#6-deployment-evolution`
