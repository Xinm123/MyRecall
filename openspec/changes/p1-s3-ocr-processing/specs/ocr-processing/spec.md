## ADDED Requirements

### Requirement: OCR execution on pending frames

The system SHALL execute RapidOCR on every frame with `status='pending'` when `processing_mode='ocr'`. The V3ProcessingWorker MUST poll for pending frames and process them sequentially via a background daemon thread.

#### Scenario: Successful OCR processing

- **WHEN** a frame has `status='pending'` and `processing_mode='ocr'`
- **THEN** the system extracts text via `RapidOCRBackend.extract_text()`, writes an `ocr_text` row, sets `frames.text_source='ocr'`, sets `frames.status='completed'`, and sets `frames.processed_at` to the current UTC timestamp

#### Scenario: OCR returns non-empty text

- **WHEN** `RapidOCRBackend.extract_text()` returns a non-empty string
- **THEN** the system MUST write one `ocr_text` row with `text=<extracted_text>`, `text_length=len(text)`, `ocr_engine='rapidocr'`, and `app_name`/`window_name` copied from the same frame's metadata

#### Scenario: No pending frames

- **WHEN** no frames have `status='pending'`
- **THEN** the worker MUST sleep for `poll_interval` seconds and check again (no error, no log noise)

---

### Requirement: OCR failure semantics

The system SHALL classify OCR failures into distinct error types and mark the frame as `failed` without writing an `ocr_text` row.

> **Acceptance impact**: Gate formula `OCR失败帧failed语义正确率 = (failed_with_ocr_row == 0)` — spec aligns with p1-s3.md §3.4 SQL.

#### Scenario: OCR throws exception

- **WHEN** `RapidOCRBackend.extract_text()` throws an exception
- **THEN** the system MUST set `frames.status='failed'`, `frames.error_message='OCR_FAILED: {exception_message}'`, MUST NOT write an `ocr_text` row, and MUST emit log `MRV3 ocr_failed frame_id=X reason=ocr_exception`

#### Scenario: OCR returns empty string

- **WHEN** `RapidOCRBackend.extract_text()` returns `""`
- **THEN** the system MUST set `frames.status='failed'`, `frames.error_message='OCR_EMPTY_TEXT'`, MUST NOT write an `ocr_text` row, and MUST emit log `MRV3 ocr_failed frame_id=X reason=ocr_empty_text`

#### Scenario: OCR returns None

- **WHEN** `RapidOCRBackend.extract_text()` returns `None`
- **THEN** the system MUST set `frames.status='failed'`, `frames.error_message='OCR_FAILED: null_result'`, and MUST NOT write an `ocr_text` row

---

### Requirement: capture_trigger validation (fail-loud)

The system SHALL validate `capture_trigger` before executing OCR. Invalid triggers MUST immediately fail the frame without OCR execution.

> **Note**: `capture_trigger` values are case-sensitive and must be lowercase. Uppercase or mixed-case values (e.g., `IDLE`, `App_Switch`) are considered invalid and will trigger the fail-loud path.

#### Scenario: Valid capture_trigger

- **WHEN** `frames.capture_trigger` is one of `{'idle', 'app_switch', 'manual', 'click'}` (lowercase)
- **THEN** OCR processing proceeds normally

#### Scenario: NULL capture_trigger

- **WHEN** `frames.capture_trigger` is `NULL`
- **THEN** the system MUST set `frames.status='failed'`, `frames.error_message='INVALID_TRIGGER: NULL'`, MUST NOT execute OCR, and MUST emit log `MRV3 ocr_failed frame_id=X reason=invalid_trigger value=NULL`

#### Scenario: Invalid capture_trigger value

- **WHEN** `frames.capture_trigger` is a non-NULL value not in the P1 enumeration
- **THEN** the system MUST set `frames.status='failed'`, `frames.error_message='INVALID_TRIGGER: {actual_value}'`, MUST NOT execute OCR, and MUST emit log `MRV3 ocr_failed frame_id=X reason=invalid_trigger value={actual_value}`

---

### Requirement: Idempotency defense

The system SHALL prevent duplicate processing of the same frame through a three-layer check strategy.

#### Scenario: Frame already completed or failed (pre-fetch layer)

- **WHEN** a frame's `status` is `'completed'` or `'failed'`
- **THEN** the worker MUST skip it during the fetch phase (only `status='pending'` frames are fetched)

#### Scenario: ocr_text row already exists (pre-write layer)

- **WHEN** the worker attempts to write an `ocr_text` row but `ocr_text` already contains a row with the same `frame_id`
- **THEN** the system MUST skip the write, emit a warning log, and NOT mark the frame as failed

#### Scenario: DB-level safety net (INSERT OR IGNORE + UNIQUE constraint)

- **WHEN** the first two layers both fail to prevent a duplicate write (extreme race condition)
- **THEN** the `UNIQUE(frame_id)` constraint on `ocr_text` combined with `INSERT OR IGNORE` MUST silently prevent duplicate row insertion at the database level

#### Scenario: Concurrent status advancement race

- **WHEN** `advance_frame_status(frame_id, 'pending', 'processing')` returns `False`
- **THEN** the worker MUST skip this frame silently (another worker/thread already claimed it)

---

### Requirement: ocr_text persistence contract

The system SHALL write `ocr_text` rows that satisfy the data-model.md Table 2 schema and include `app_name`/`window_name` from the same frame's metadata.

> **Acceptance impact**: Gate formula `OCR成功帧写入ocr_text正确率 = (missing_ocr == 0)` — spec aligns with p1-s3.md §3.3 SQL.

#### Scenario: ocr_text row content correctness

- **WHEN** OCR completes successfully for a frame
- **THEN** the `ocr_text` row MUST contain: `frame_id = frames.id`, `text = <OCR extracted text>`, `text_length = len(text)`, `ocr_engine = 'rapidocr'`, `app_name` and `window_name` copied from `frames.app_name`/`frames.window_name`

#### Scenario: FTS trigger auto-fires

- **WHEN** an `ocr_text` row is inserted with non-empty `text`
- **THEN** the `ocr_text_ai` trigger MUST automatically insert a corresponding `ocr_text_fts` row (no application code needed)

---

### Requirement: Zero AI enhancement guard

The system MUST NOT generate `caption`, `keywords`, `fusion_text`, or `embedding` during OCR processing. The `ocr_text_embeddings` table MUST NOT exist in the database.

> **Acceptance impact**: Gate formula `零AI增强确认 = (table_exists == 0 for ocr_text_embeddings)` — spec aligns with p1-s3.md §3.6 SQL.

#### Scenario: No AI artifacts generated

- **WHEN** `processing_mode='ocr'` and a frame is processed
- **THEN** the processing worker MUST NOT initialize or call any vision provider, embedding provider, or keyword extractor

#### Scenario: ocr_text_embeddings table absence

- **WHEN** querying `sqlite_master` for table `ocr_text_embeddings`
- **THEN** the query MUST return 0 rows

#### Scenario: accessibility table remains empty

- **WHEN** querying `SELECT COUNT(*) FROM accessibility`
- **THEN** the result MUST be 0 (v4 reserved seam, not written by v3)

---

### Requirement: Structured logging for OCR processing

The system SHALL emit structured log lines for OCR processing outcomes to support observability and Gate verification.

#### Scenario: OCR success log

- **WHEN** OCR processing completes successfully for a frame
- **THEN** the system MUST emit: `MRV3 ocr_completed frame_id=X text_length=Y engine=rapidocr elapsed_ms=Z` (where `Z` is the time in milliseconds from `pending→processing` advancement to OCR completion, enabling `ocr_processing_latency_p95` Soft KPI measurement)

#### Scenario: OCR failure log

- **WHEN** OCR processing fails for a frame
- **THEN** the system MUST emit: `MRV3 ocr_failed frame_id=X reason={error_type} elapsed_ms=Z` where `error_type` is one of `ocr_exception`, `ocr_empty_text`, `null_result`, `invalid_trigger`

---

### Requirement: No OCR retry on failure

The system MUST NOT automatically retry OCR processing for failed frames. `frames.retry_count` MUST remain 0 for all frames in P1.

#### Scenario: OCR failure is terminal

- **WHEN** OCR processing fails for any reason
- **THEN** `frames.status` MUST be set to `'failed'` and the frame MUST NOT be requeued for processing
