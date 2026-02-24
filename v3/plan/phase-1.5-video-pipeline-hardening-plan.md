# MyRecall Phase 1.5 Video Pipeline Hardening Plan

**Version**: 1.1  
**Last Updated**: 2026-02-10  
**Status**: Executed (Historical Hardening Plan)
**Scope**: Phase 1/1.5 only (no Phase 2 audio changes)
**Evidence Index**: `/Users/pyw/newpart/MyRecall/v3/evidence/phase1_5_strict60/`

---

## 1. Summary

This plan hardens the Phase 1/1.5 video recording pipeline with three goals:

1. `chunk_process` uses strict wallclock-based 60s chunk rotation (not frame-count threshold).
2. Stalled pipelines self-heal in both modes (`segment` and `chunk_process`) with mode-specific criteria.
3. Client observability is corrected so status and chunk lifecycle logs consistently reflect real active chunks.

Phase 2 audio design/implementation is explicitly out of scope.

---

## 2. Scope

### In Scope

- `/Users/pyw/newpart/MyRecall/openrecall/client/ffmpeg_manager.py`
- `/Users/pyw/newpart/MyRecall/openrecall/client/video_recorder.py`
- `/Users/pyw/newpart/MyRecall/openrecall/client/__main__.py`
- `/Users/pyw/newpart/MyRecall/openrecall/shared/config.py`
- `/Users/pyw/newpart/MyRecall/myrecall_client.env`
- `/Users/pyw/newpart/MyRecall/myrecall_client_low_latency.env`
- `/Users/pyw/newpart/MyRecall/tests/test_phase1_video_recorder.py`
- `/Users/pyw/newpart/MyRecall/tests/test_phase1_pipeline_profile_change.py`

### Out of Scope

- Phase 2 audio chain and docs.
- Server OCR/search protocol changes.

---

## 3. Public Config / Interface Contract

No new env keys are introduced in v1.1.

Existing keys and semantics:

- `OPENRECALL_VIDEO_PIPELINE_MODE=segment|chunk_process`
- `OPENRECALL_VIDEO_CHUNK_DURATION`:
  - In `chunk_process`: strict monotonic wallclock target for chunk rotation.
- `OPENRECALL_VIDEO_PIPE_WRITE_TIMEOUT_MS`:
  - Single `stdin` write timeout; also contributes to chunk-process grace window.
- `OPENRECALL_VIDEO_NO_CHUNK_PROGRESS_TIMEOUT_SECONDS`:
  - **Segment mode only** no-progress timeout.

Read-only FFmpeg manager status fields exposed for recorder/watcher/status logging:

- `active_chunk_path`
- `write_stuck_seconds`
- `seconds_since_last_write`
- `chunk_age_seconds`
- `chunk_deadline_in_seconds`

---

## 4. Strict 60s Chunk Semantics

For `chunk_process`:

1. On chunk start, initialize:
   - `chunk_started_monotonic`
   - `chunk_deadline_monotonic = started + chunk_duration`
2. On each successful `write_frame`, compare current monotonic time with deadline.
3. If `now >= deadline`, rotate with reason `deadline`:
   - close current ffmpeg `stdin`
   - wait process exit (or kill on timeout)
   - emit chunk completed callback
   - spawn next per-chunk ffmpeg process
4. Rotation trigger is independent of actual input FPS (low FPS still rotates by wallclock).

---

## 5. Chunk-Process No-Progress Policy

`segment` mode remains chunk-name-progress based.

`chunk_process` mode restart criteria:

- `overdue = chunk_age_seconds > (video_chunk_duration + grace_seconds)`, where
  - `grace_seconds = max(3, min(15, 4 * video_pipe_write_timeout_ms / 1000))`
- OR `write_stuck_seconds >= write_stall_timeout`
- OR `writer_alive == False`
- OR `seconds_since_last_write >= write_stall_timeout`

`OPENRECALL_VIDEO_NO_CHUNK_PROGRESS_TIMEOUT_SECONDS` is not used by `chunk_process`.

---

## 6. Observability Contract

### Chunk Lifecycle Logs

- Start: `Video chunk recording started | file=... | monitor_id=...`
- End: `Video chunk recording ended | file=... | size_mb=... | duration=... | monitor_id=...`
- Rotate reason: `chunk_rotate | reason=... | file=... | monitor_id=... | age=...`

### Periodic Client Status (20s)

`Client status | state=recording | monitor_chunks=... | monitor_health=... | duration=... | pending_uploads=...`

`monitor_health` carries per-monitor fields:

- `chunk_age_s`
- `deadline_in_s`
- `last_write_ago_s`
- `writer_alive`

Status and lifecycle events now share the same active chunk source.

---

## 7. Test Matrix

### Automated (must pass)

- `python3 -m pytest tests/test_phase1_video_recorder.py -v`
- `python3 -m pytest tests/test_phase1_pipeline_profile_change.py -v`
- `python3 -m pytest tests/test_phase1_video_recorder.py tests/test_phase1_pipeline_profile_change.py tests/test_video_recorder_fallback_policy.py tests/test_video_recorder_recovery_probe.py -v`

### Manual Long-Run (acceptance evidence)

- `chunk_process` 30-minute run:
  - chunk boundary advances continuously.
  - no long freeze on stale chunk name.
- `segment` 15-minute run:
  - no-progress triggers restart and recovers.
- Ctrl-C shutdown:
  - no duplicate shutdown completion logs.

---

## 8. Rollout & Rollback

### Rollout

1. Default mode remains `chunk_process`.
2. Observe:
   - chunk output continuity
   - restart count
   - write timeout count
   - upload backlog trend

### Rollback

- Runtime fallback: `OPENRECALL_VIDEO_PIPELINE_MODE=segment`
- No DB/schema migration dependency.

---

## 9. Completion Gates

Engineering complete when:

- Automated regression suite passes.
- Status and lifecycle logs meet observability contract.

Phase 1.5.1 fully closed when:

- Manual long-run evidence is attached under:
  - `/Users/pyw/newpart/MyRecall/v3/evidence/phase1_5_strict60/`

---

## 10. Phase Boundary

This plan and implementation are bounded to Phase 1/1.5.  
Phase 2 design, scope, and docs are intentionally unchanged.
