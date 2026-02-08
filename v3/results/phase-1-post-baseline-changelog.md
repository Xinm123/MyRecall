# MyRecall-v3 Phase 1 Post-Baseline Change Log

**Version**: 1.0  
**Date**: 2026-02-07  
**Scope**: Bug fixes and hardening completed after Phase 1 baseline engineering sign-off (2026-02-06)

---

## 1. Purpose

This document records all high-impact fixes and functional improvements made after the initial Phase 1 engineering completion, with implementation and verification evidence.

It is the authority for answering: "What changed after Phase 1 baseline?"

---

## 2. Post-Baseline Changes (Detailed)

| # | Area | Problem Observed | Implementation | Verification Evidence |
|---|------|------------------|----------------|-----------------------|
| 1 | Monitor-id capture hardening | Legacy device-index assumptions were fragile across machines/monitors | Added monitor-id driven pipeline with `SCKMonitorSource` + per-monitor `FFmpegManager` rawvideo stdin mode (`nv12`/`bgra`) | `tests/test_phase1_video_recorder.py`, `tests/test_phase1_sck_stride_unpadding.py` |
| 2 | Raw frame correctness | CVPixelBuffer stride/padding could corrupt frames (skew/garbled) | Added row-wise unpadding helpers for NV12/BGRA and locked pointer access lifecycle | `tests/test_phase1_sck_stride_unpadding.py` |
| 3 | Memory safety/perf | Frame packing path could cause repeated allocations and unstable memory profile | Added `FrameBufferPool` with growth strategy and max-bytes safety fallback | `tests/test_phase1_buffer_pool.py` + 10-minute stress delta (RSS) |
| 4 | Pipeline restart safety | Profile changes could cause stale writes/BrokenPipe storms | Added atomic restart state machine with generation guard in monitor pipeline controller | `tests/test_phase1_pipeline_profile_change.py` |
| 5 | Upload dispatch mismatch | Video chunks could be routed into screenshot upload branch | Consumer now dispatches by `metadata.type`; `video_chunk` routes to `upload_video_chunk` | `tests/test_phase5_buffer.py::TestUploaderConsumer` |
| 6 | Online troubleshooting gap | Hard to diagnose uploader branch on production logs | Added explicit dispatch log: `item_type` + target uploader branch | `tests/test_phase5_buffer.py::test_consumer_logs_dispatch_path` |
| 7 | Legacy API compatibility | `/api/upload` could treat MP4 as image and fail OCR/image decode paths | Legacy `/api/upload` now detects video payload and forwards to v1 video handler | `tests/test_phase1_monitor_upload_api.py::test_legacy_upload_routes_video_chunk_to_video_table` |
| 8 | Startup schema regression | Fresh server startup could fail video insert if migrations not manually run | `SQLStore` now ensures migrations on init (idempotent), with startup guard | `tests/test_phase1_monitor_metadata_migration.py::test_sql_store_init_auto_applies_video_migrations` |
| 9 | Metadata quality (`Unknown`) | Frame cards/search entries could show `Unknown` due to metadata key mismatch | Server upload accepts both canonical (`app_name/window_title`) and legacy (`active_*`) keys; chunk app/window is propagated to frames + FTS | `tests/test_phase1_monitor_upload_api.py` and `tests/test_phase1_ocr_pipeline.py` metadata propagation case |
| 10 | Search page crash on video-only results | `search_debug`/debug logging assumed snapshot object exists for all candidates | Added dedicated `video_frame` rendering/logging branch; no `NoneType.context` crash | `tests/test_phase1_search_debug_render.py` |
| 11 | OCR cold-start latency | OCR model loaded lazily after startup, causing first-request delay | Added OCR provider preload + warm-up in server startup | `tests/test_phase1_server_startup.py::test_server_preload_ai_models_includes_ocr_warmup` |
| 12 | Recording toggle UX | Runtime toggle could stop FFmpeg/watchdog and look like full offline shutdown | Toggle now pauses/resumes monitor frame sources without tearing down monitor pipelines | `tests/test_phase1_video_recorder.py` runtime pause/resume tests |
| 13 | Chunk segmentation operations | 5-minute segments were too coarse for queueing and diagnosis | Default chunk duration moved to 60s and exposed via client env as authoritative source | `openrecall/shared/config.py`, `myrecall_client.env`, runtime logs |
| 14 | Cross-machine config misunderstanding | Server env value for chunk duration could be mistaken as active recorder control | Added explicit note in `myrecall_server.env`: same key is for ops alignment only, currently not consumed by server runtime | `myrecall_server.env` comments |
| 15 | SCK robustness & observability | `Display not found`/`start timeout` could immediately degrade and was hard to diagnose | Added structured SCK error handling, delayed fallback policy, auto recovery probe from legacy, and `/api(/v1)/vision/status` | `openrecall/client/video_recorder.py`, `openrecall/server/api.py`, `openrecall/server/api_v1.py`, `tests/test_video_recorder_fallback_policy.py`, `tests/test_vision_status_api.py` |

---

## 3. Current Known Behavior (Not a New Bug)

1. `/api/v1/search` still returns snapshot-oriented records (`search()` path), while `/search` page uses `search_debug()` and can render `video_frame` rows.
2. This is consistent with current Phase 1/Phase 3 split: Phase 1 enables video OCR searchability; unified multimodal contract remains Phase 3 scope.

---

## 4. Related Documentation Updated

- `/Users/pyw/new/MyRecall/v3/results/phase-1-validation.md`
- `/Users/pyw/new/MyRecall/v3/metrics/phase-gates.md`
- `/Users/pyw/new/MyRecall/v3/milestones/roadmap-status.md`
- `/Users/pyw/new/MyRecall/v3/plan/03-phase-1-detailed-plan.md`
- `/Users/pyw/new/MyRecall/v3/results/README.md`
- `/Users/pyw/new/MyRecall/README.md`
- `/Users/pyw/new/MyRecall/myrecall_client.env`
- `/Users/pyw/new/MyRecall/myrecall_server.env`

---

## 5. Verification Commands (Regression Focus)

```bash
cd /Users/pyw/new/MyRecall
python3 -m pytest tests/test_phase1_search_debug_render.py -v
python3 -m pytest tests/test_phase1_server_startup.py -v
python3 -m pytest tests/test_phase1_monitor_upload_api.py -v
python3 -m pytest tests/test_phase5_buffer.py -k TestUploaderConsumer -v
```
