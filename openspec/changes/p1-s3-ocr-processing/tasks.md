## Implementation Tasks

### 0. OCR Backend Patches (`rapid_backend.py`)

> **决策依据**: design.md D2/D2.1 — 直接修复 `rapid_backend.py` 是最简洁方案，让异常向上传播以便 `ocr_processor.py` 区分「引擎异常」与「图像无文字」，同时修复 singleton `__new__` 模式避免 broken 实例残留。

- [ ] 0.1 Remove `try/except` exception swallowing in `extract_text()` (L281-283) — let OCR engine exceptions propagate so `ocr_processor.py` can distinguish engine errors from empty text. **After this change**: exceptions will propagate to caller; `ocr_processor.py` will catch and classify as `OCR_FAILED`.
- [ ] 0.2 Fix singleton `__new__` pattern + remove defensive re-init guard (L243-249). **Problem**: current `__new__` assigns `cls._instance` before `_initialize()`, so if init fails `_instance` is a broken object without `engine` attribute. **Fix**: defer `cls._instance = instance` until after `_initialize()` succeeds (see design.md D2.1). Then remove the re-init guard in `extract_text()` since it's no longer needed.
- [ ] 0.3 Move `OCRPostProcessor()` instantiation from per-call (L271) to module-level singleton — avoid unnecessary object creation per frame. **Implementation**: `_POSTPROCESSOR = OCRPostProcessor()` at module level, use `_POSTPROCESSOR.process()` in `extract_text()`.

### 1. Processing Module Scaffolding

- [ ] 1.1 Create `openrecall/server/processing/__init__.py`
- [ ] 1.2 Create `openrecall/server/processing/ocr_processor.py` with `OcrResult` dataclass and `execute_ocr(image_path)` function that calls `RapidOCRBackend`, distinguishes exceptions / None / empty text, and returns structured result. **Note**: must explicitly handle `None` return from `extract_text()` as `OCR_FAILED: null_result` (see design.md D2 table row 2, defensive path)
- [ ] 1.3 Create `openrecall/server/processing/idempotency.py` with `check_ocr_text_exists(conn, frame_id) -> bool` function for pre-write duplicate check

### 2. V3ProcessingWorker Core

- [ ] 2.1 Create `openrecall/server/processing/v3_worker.py` with `V3ProcessingWorker` class: daemon thread, `_stop_event`, `start()`/`stop()`/`join()` interface (matching `NoopQueueDriver` pattern)
- [ ] 2.2 Implement `_fetch_pending_frames()` — query `frames WHERE status='pending'` returning `(frame_id, capture_id, capture_trigger, app_name, window_name, snapshot_path)` tuples
- [ ] 2.3 Implement `_validate_trigger(capture_trigger)` — check against P1 valid set `{'idle', 'app_switch', 'manual', 'click'}` (lowercase, case-sensitive), fail-loud on NULL or invalid values (including uppercase/mixed-case like `IDLE`, `App_Switch`)
- [ ] 2.4 Implement `_process_frame()` main loop body: record `start_time`, advance `pending→processing`, validate trigger, execute OCR, write `ocr_text` or mark failed, advance to `completed`/`failed`, set `frames.processed_at=utcnow()` on completion (same transaction as status advancement)
- [ ] 2.5 Implement `ocr_text` write logic: `INSERT OR IGNORE` with `frame_id`, `text`, `text_length`, `text_json=NULL` (P1 不填充 bounding box JSON，详见 design.md D3.1), `ocr_engine='rapidocr'`, `app_name`, `window_name` from frame metadata (see design.md D5.1 for `INSERT OR IGNORE` rationale)
- [ ] 2.6 Implement `frames.text_source='ocr'` + `frames.processed_at=utcnow()` update on OCR success (same transaction as status advancement to `completed`)
- [ ] 2.7 Implement three-layer idempotency: (1) skip frames already completed/failed at fetch time, (2) check `ocr_text` existence before write, (3) `INSERT OR IGNORE` + `UNIQUE(frame_id)` as DB-level safety net (see design.md D5/D5.1)
- [ ] 2.8 Add structured logging: `MRV3 ocr_completed frame_id=X text_length=Y engine=rapidocr elapsed_ms=Z` (success, `Z` = time since `pending→processing` advancement) and `MRV3 ocr_failed frame_id=X reason={error_type} elapsed_ms=Z` (failure). The `elapsed_ms` field enables `ocr_processing_latency_p95` Soft KPI measurement (gate_baseline.md §3.4)

### 3. Database Layer Extension

- [ ] 3.1 Add `insert_ocr_text(conn, frame_id, text, text_length, ocr_engine, app_name, window_name)` method to `FramesStore` or a new `OcrTextStore`. **Implementation**: use `INSERT OR IGNORE INTO ocr_text (...)` (design.md D5.1). Add front-guard assertion `assert text and len(text) > 0` to prevent accidental empty-text writes bypassing `ocr_processor.py`.
- [ ] 3.2 Add `update_text_source(conn, frame_id, text_source)` method for setting `frames.text_source`
- [ ] 3.3 Add `check_ocr_text_exists(conn, frame_id) -> bool` query method
- [ ] 3.4 Add migration for `UNIQUE(frame_id)` on `ocr_text`: `CREATE UNIQUE INDEX IF NOT EXISTS idx_ocr_text_frame_id_unique ON ocr_text(frame_id);` (replaces existing `idx_ocr_text_frame_id` non-unique index; see design.md D5.1)

### 4. processing_mode=ocr Startup

- [ ] 4.1 Add `_start_ocr_mode()` function in `__main__.py` — instantiate and start `V3ProcessingWorker`
- [ ] 4.2 Add `_preload_ocr_model()` function in `__main__.py` — instantiate `RapidOCRBackend()` only (no VL/embedding models). **Fail-fast**: if `RapidOCRBackend()` initialization fails, log the error and call `sys.exit(1)`; do NOT silently fall back to noop mode (see specs/processing-mode-switch/spec.md §Model load failure scenario)
- [ ] 4.3 Add `elif processing_mode == "ocr":` branch in `main()` — call `_preload_ocr_model()` then `_start_ocr_mode()`, emit `MRV3 processing_mode=ocr` log
- [ ] 4.4 Update shutdown handler in `main()` to handle `V3ProcessingWorker` (same `stop()`/`join()` pattern as `NoopQueueDriver`)
- [ ] 4.5 Update `config.py`: change `processing_mode` default value from `"noop"` to `"ocr"` (see design.md D6)
- [ ] 4.6 Verify `OPENRECALL_PROCESSING_MODE` env var in `config.py` supports `"noop"` value for explicit disable (backward compatibility)

### 5. Backend API Extension (Grid Data)

- [ ] 5.1 Modify `FramesStore.get_recent_memories()` SQL to LEFT JOIN `ocr_text` and return additional fields: `text_source`, `text_length`, `ocr_text_preview` (SUBSTR 100), `ocr_engine`, `processed_at`, `capture_trigger`, `device_name`, `error_message`
- [ ] 5.2 Modify `FramesStore.get_memories_since()` SQL with same LEFT JOIN and field additions
- [ ] 5.3 Ensure returned dict includes all fields from p1-s3.md §1.4.2 (backward compatible — additive only)

### 6. UI Card Improvements

- [ ] 6.1 Modify `index.html` Grid card header to display `app_name`, `window_name`, `device_name`
- [ ] 6.2 Modify card footer to show `capture_trigger` and human-readable `timestamp`
- [ ] 6.3 Add visual status distinction for `pending`/`processing`/`completed`/`failed` (CSS classes or labels)
- [ ] 6.4 Add OCR info section in footer for completed frames: engine name, `processed_at`, `text_length`
- [ ] 6.5 Add OCR text preview (≤100 chars) display for completed frames
- [ ] 6.6 Add error message display for failed frames
- [ ] 6.7 Add `data-frame-status` attribute to each card DOM element with value `pending|processing|completed|failed`

### 7. Unit Tests (TDD — write before implementation)

- [ ] 7.1 Create `tests/edge/test_p1_s3_ocr_text_write.py` — test `ocr_text` row creation with correct fields
- [ ] 7.2 Create `tests/edge/test_p1_s3_text_source_mark.py` — test `frames.text_source='ocr'` marking
- [ ] 7.3 Create `tests/edge/test_p1_s3_failed_semantic.py` — test failed state for exception, empty text, null result
- [ ] 7.4 Create `tests/edge/test_p1_s3_trigger_validation.py` — test capture_trigger validation fail-loud
- [ ] 7.5 Create `tests/edge/test_p1_s3_idempotency.py` — test three-layer idempotency defense (fetch filter, pre-write check, INSERT OR IGNORE)
- [ ] 7.6 Create `tests/edge/test_p1_s3_zero_ai_check.py` — test no AI artifacts generated, ocr_text_embeddings table absent

### 8. Integration Tests

- [ ] 8.1 Create `tests/edge/test_p1_s3_ocr_pipeline.py` — end-to-end: sample JPEG → OCR → `ocr_text` row → FTS index
- [ ] 8.2 Create `tests/edge/test_p1_s3_processing_mode.py` — test noop/ocr mode switching behavior
- [ ] 8.3 Create `tests/edge/test_p1_s3_v3_worker_lifecycle.py` — test worker start, stop, status transitions
- [ ] 8.4 Create `tests/edge/test_p1_s3_fts_trigger.py` — test FTS trigger auto-populates `ocr_text_fts`

### 9. E2E/UI Tests

- [ ] 9.1 Create `tests/e2e/test_p1_s3_ui_card_display.py` — verify Grid card header/footer content and OCR info
- [ ] 9.2 Create `tests/e2e/test_p1_s3_ui_status_display.py` — verify visual status distinction and `data-frame-status` attribute
- [ ] 9.3 Create `tests/e2e/test_p1_s3_ui_empty_db.py` — smoke test: empty database renders Grid `/` without JS errors or literal `null` strings

### 10. Test Fixtures

- [ ] 10.1 Ensure `tests/fixtures/images/sample_jpeg.jpg` exists (normal OCR scenario)
- [ ] 10.2 Ensure `tests/fixtures/images/corrupted_image.jpg` exists (OCR failure scenario)
- [ ] 10.3 Ensure `tests/fixtures/images/empty_text_image.jpg` exists (OCR returns empty text scenario)
- [ ] 10.4 Ensure integration/E2E test fixtures call `ensure_v3_schema()` or execute DDL explicitly to guarantee FTS triggers (`ocr_text_ai`, `ocr_text_update`, `ocr_text_delete`) are present before testing FTS auto-population (required by §8.4)

## Acceptance Verification

### 11. Gate SQL Verification

- [ ] 11.1 Run §3.3 SQL: verify `missing_ocr = 0` (all completed+ocr frames have `ocr_text` row)
- [ ] 11.2 Run §3.4 SQL: verify `failed_with_ocr_row = 0` (no failed frame has `ocr_text` row)
- [ ] 11.3 Run §3.5 SQL: verify `unexpected_accessibility_rows = 0` (accessibility table empty)
- [ ] 11.4 Run §3.6 SQL: verify `table_exists = 0` for `ocr_text_embeddings`
- [ ] 11.5 Run §3.7 SQL: verify `wrong_text_source = 0` (all completed frames have `text_source='ocr'`)
- [ ] 11.6 Run §3.8 SQL: verify `inconsistent_engine = 0` (all `ocr_text` rows have `ocr_engine='rapidocr'`)

### 12. Sample Verification

- [ ] 12.1 Verify ≥100 processing records exist for statistical significance
- [ ] 12.2 Verify ≥3 OCR failure sample classes (exception, empty text, invalid trigger)
- [ ] 12.3 Spot-check ≥3 OCR success frames: verify `ocr_text` row contains correct text and frame metadata matches

### 13. UI Verification

- [ ] 13.1 Verify Grid `/` card header shows `app_name`, `window_name`, `device_name` for ≥20 completed frames
- [ ] 13.2 Verify ≥5 failed frames show error message in card footer
- [ ] 13.3 Verify ≥5 pending/processing frames show correct status labels
- [ ] 13.4 Verify `data-frame-status` attribute present on all rendered cards
- [ ] 13.5 Capture UI evidence (screenshots) for acceptance record

### 14. Processing Mode Verification

- [ ] 14.1 Verify startup log contains `MRV3 processing_mode=ocr`
- [ ] 14.2 Verify `GET /v1/ingest/queue/status` returns `"processing_mode": "ocr"`
- [ ] 14.3 Verify noop mode still works when `OPENRECALL_PROCESSING_MODE=noop` (regression check)

### 15. Code Review Checks

- [ ] 15.1 Verify `V3ProcessingWorker` does NOT call `get_active_window()` or other context-supplement APIs (p1-s3.md §3.10)
- [ ] 15.2 Verify `V3ProcessingWorker` does NOT initialize vision_provider, embedding_provider, or keyword_extractor
- [ ] 15.3 Verify `ocr_text` writes include `app_name`/`window_name` from frame metadata (data-model.md Table 2 requirement)
