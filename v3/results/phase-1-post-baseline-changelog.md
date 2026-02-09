# MyRecall-v3 Phase 1 Post-Baseline Change Log

**Version**: 1.2
**Date**: 2026-02-08T07:50:52Z
**Scope**: Bug fixes and hardening completed after Phase 1 baseline engineering sign-off (2026-02-06), including Phase 1.5 metadata precision upgrade (2026-02-08)

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
| 16 | Phase 1.5: Frame metadata resolver | Chunk metadata was blindly copied to all frames; no per-frame override, no source traceability | `metadata_resolver.py` enforces frame > chunk > null priority for `app/window/focused/browser_url`; `ResolvedFrameMetadata` includes source traceability | `openrecall/server/video/metadata_resolver.py`, `tests/test_phase1_5_metadata_resolver.py` (12 passed) |
| 17 | Phase 1.5: focused/browser_url pipeline | `focused` defaulted to 0 (schema DEFAULT); `browser_url` never written; NULL semantics lost | Processor explicitly writes `focused`/`browser_url`; SQL normalizes on read (NULL→None); `/api/v1/search` and `/api/v1/timeline` provide additive optional fields | `openrecall/server/database/sql.py`, `openrecall/server/video/processor.py`, `openrecall/server/api_v1.py`, `tests/test_phase1_5_focused_browser_url.py` (10 passed) |
| 18 | Phase 1.5: OCR engine true value | `ocr_engine` field always stored hardcoded "rapidocr" regardless of actual provider | Added `engine_name` class attribute to `OCRProvider` base and all 5 concrete providers; processor passes real name to `insert_ocr_text()` | `openrecall/server/ai/base.py`, `openrecall/server/ai/providers.py`, `tests/test_phase1_5_ocr_engine.py` (3 passed) |
| 19 | Phase 1.5: Offset guard | No validation that frame timestamp/offset aligns with its parent chunk before insertion | Pre-insertion guard checks time window, non-negative offset, monotonicity, required fields; rejects with structured RFC3339 log | `openrecall/server/video/processor.py`, `tests/test_phase1_5_offset_guard.py` (8 passed) |
| 20 | Phase 1.5: v3_005 migration (chunk timestamps) | Offset guard needed precise chunk time bounds; `created_at` was only approximation | Added `start_time`/`end_time` REAL columns to `video_chunks`; worker reads from DB; upload API passes from client metadata | `openrecall/server/database/migrations/v3_005_add_video_chunk_timestamps.sql`, `openrecall/server/video/worker.py`, `openrecall/server/api_v1.py` |
| 21 | Client chunk naming observability | `chunk_%04d` restarts from zero after client reboot, making diagnostics harder | Switched client FFmpeg segment naming to UTC monitor timestamp format (`monitor_{monitor_id}_{YYYY-MM-DD_HH-MM-SS}.mp4`) for both monitor-id and legacy capture pipelines; updated segment path resolution logic in `current_chunk_path` | `openrecall/client/ffmpeg_manager.py`, `tests/test_phase1_video_recorder.py` |

---

## 3. Current Known Behavior (Not a New Bug)

1. `/search` 页面仍以 `search_debug()` 作为主展示路径；`/api/v1/search` 已兼容 video-frame 结果序列化并追加可选字段（旧字段语义保持不变）。
2. 统一多模态排序与更丰富融合策略仍属于 Phase 3 范围。

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
- `/Users/pyw/new/MyRecall/v3/webui/DATAFLOW.md`
- `/Users/pyw/new/MyRecall/v3/webui/ROUTE_MAP.md`
- `/Users/pyw/new/MyRecall/v3/webui/CHANGELOG.md`

---

## 5. Verification Commands (Regression Focus)

```bash
cd /Users/pyw/new/MyRecall
python3 -m pytest tests/test_phase1_search_debug_render.py -v
python3 -m pytest tests/test_phase1_server_startup.py -v
python3 -m pytest tests/test_phase1_monitor_upload_api.py -v
python3 -m pytest tests/test_phase5_buffer.py -k TestUploaderConsumer -v
```

### Phase 1.5 Verification Commands

```bash
cd /Users/pyw/new/MyRecall
python3 -m pytest tests/test_phase1_5_metadata_resolver.py -v
python3 -m pytest tests/test_phase1_5_offset_guard.py -v
python3 -m pytest tests/test_phase1_5_ocr_engine.py -v
python3 -m pytest tests/test_phase1_5_focused_browser_url.py -v
# Full regression (Phase 1 + 1.5):
python3 -m pytest tests/test_phase1_* -v
# Result: 170 passed, 8 skipped, 0 failed
```

## 6. Phase 1.5 Evidence Matrix

| Change | Code Path | Test Command | Result | UTC Timestamp |
|---|---|---|---|---|
| Resolver fallback chain includes `focused/browser_url` | `/Users/pyw/new/MyRecall/openrecall/server/video/metadata_resolver.py` | `python3 -m pytest tests/test_phase1_5_metadata_resolver.py -v` | 12 passed | 2026-02-08T07:50:52Z |
| `focused/browser_url` write + query/read path + v1 search optional fields | `/Users/pyw/new/MyRecall/openrecall/server/video/processor.py`, `/Users/pyw/new/MyRecall/openrecall/server/database/sql.py`, `/Users/pyw/new/MyRecall/openrecall/server/api_v1.py` | `python3 -m pytest tests/test_phase1_5_focused_browser_url.py -v` | 10 passed | 2026-02-08T07:50:52Z |
| OCR engine true value propagation | `/Users/pyw/new/MyRecall/openrecall/server/ai/base.py`, `/Users/pyw/new/MyRecall/openrecall/server/ai/providers.py`, `/Users/pyw/new/MyRecall/openrecall/server/video/processor.py` | `python3 -m pytest tests/test_phase1_5_ocr_engine.py -v` | 3 passed | 2026-02-08T07:50:52Z |
| Offset guard reject logging contract hardening | `/Users/pyw/new/MyRecall/openrecall/server/video/processor.py` | `python3 -m pytest tests/test_phase1_5_offset_guard.py -v` | 8 passed | 2026-02-08T07:50:52Z |
| Full post-fix regression closure | `/Users/pyw/new/MyRecall/openrecall/server/video/metadata_resolver.py`, `/Users/pyw/new/MyRecall/openrecall/server/video/processor.py`, `/Users/pyw/new/MyRecall/openrecall/server/api_v1.py`, `/Users/pyw/new/MyRecall/openrecall/server/database/sql.py` | `python3 -m pytest tests/test_phase1_* -v` | 170 passed, 8 skipped | 2026-02-08T07:50:08Z |
