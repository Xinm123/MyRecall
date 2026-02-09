# MyRecall Phase 1.5 Video Pipeline Hardening Plan

**Version**: 1.0  
**Last Updated**: 2026-02-09  
**Scope**: Phase 1/1.5 only (no Phase 2 audio changes)

---

## 1. Objective

Fix monitor video pipeline stalls where chunk boundaries stop advancing after several chunks while process remains alive, and introduce a screenpipe-style chunk-process pipeline mode as a configurable option.

---

## 2. Scope

### In Scope

- `/Users/pyw/new/MyRecall/openrecall/client/ffmpeg_manager.py`
- `/Users/pyw/new/MyRecall/openrecall/client/video_recorder.py`
- `/Users/pyw/new/MyRecall/openrecall/shared/config.py`
- `/Users/pyw/new/MyRecall/tests/test_phase1_video_recorder.py`
- `/Users/pyw/new/MyRecall/tests/test_phase1_pipeline_profile_change.py`

### Out of Scope

- Any Phase 2 audio implementation or docs
- Server OCR/search behavior changes

---

## 3. Configuration Interface Changes

Add three config knobs:

- `OPENRECALL_VIDEO_PIPELINE_MODE` (`segment|chunk_process`, default `chunk_process`)
- `OPENRECALL_VIDEO_PIPE_WRITE_TIMEOUT_MS` (single ffmpeg stdin write timeout, default `1500`)
- `OPENRECALL_VIDEO_NO_CHUNK_PROGRESS_TIMEOUT_SECONDS` (no chunk-boundary progress timeout, default `180`)

Backward compatibility:

- Existing `OPENRECALL_VIDEO_CHUNK_DURATION`, `OPENRECALL_VIDEO_FPS`, `OPENRECALL_VIDEO_PIPE_WRITE_WARN_MS`, `OPENRECALL_VIDEO_PIPELINE_RESTART_ON_PROFILE_CHANGE` remain valid.

---

## 4. Implementation Breakdown

### A. Pipeline mode abstraction

- Add mode branch in `FFmpegManager` for rawvideo pipeline path:
  - `segment`: current segment muxer behavior
  - `chunk_process`: single-output process per chunk
- Unify chunk lifecycle events:
  - chunk started
  - chunk completed

### B. chunk_process mode

- Rotate by `frames_per_chunk = fps * chunk_duration`
- On threshold hit:
  1. close stdin
  2. wait process exit
  3. emit chunk completed callback
  4. start next ffmpeg process with timestamp filename

### C. segment mode hardening

- Keep segment mode as fallback option
- If chunk boundary has no progress over timeout, force monitor pipeline restart even when writes still happen

### D. Single write timeout hardening

- Add single-write timeout for ffmpeg stdin write
- Timeout behavior:
  - raise timeout error
  - let upper controller trigger pipeline recovery
  - keep slow-write warning and timeout error as separate signals

### E. Observability

- Keep periodic client status output
- Keep started/ended logs around every chunk boundary
- Ensure status `monitor_chunks` reflects active chunk path from lifecycle state

### F. Verification

- Add unit tests for:
  - chunk_process command behavior and rotation
  - write timeout propagation and controller recovery path
  - segment no-progress restart
  - chunk_process no false restart when writes remain healthy
- Run phase1 video recorder and profile-change regression suites

---

## 5. Acceptance Criteria

- Default mode `chunk_process` rotates chunks continuously without freezing on a stale filename.
- `segment` mode auto-recovers from no-progress chunk boundaries.
- Client status aligns with chunk started/ended lifecycle logs.
- No P0/P1 regressions in Phase 1/1.5 test surface.

---

## 6. Rollback

- Runtime fallback: set `OPENRECALL_VIDEO_PIPELINE_MODE=segment`
- No DB migration required for rollback

