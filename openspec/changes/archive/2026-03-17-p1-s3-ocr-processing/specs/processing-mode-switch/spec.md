## ADDED Requirements

### Requirement: Three-way processing_mode startup branch

The server entry point (`__main__.py`) SHALL support three `processing_mode` values: `noop`, `ocr`, and legacy (any other value). The branch selection MUST occur at startup and determine which worker is instantiated.

#### Scenario: processing_mode=noop

- **WHEN** `settings.processing_mode` is `"noop"`
- **THEN** the system MUST start `NoopQueueDriver`, MUST NOT load any OCR/AI models, and MUST emit log `MRV3 processing_mode=noop`

#### Scenario: processing_mode=ocr

- **WHEN** `settings.processing_mode` is `"ocr"`
- **THEN** the system MUST preload only `RapidOCRBackend` (no VL/embedding models), start `V3ProcessingWorker`, and MUST emit log `MRV3 processing_mode=ocr`

#### Scenario: processing_mode=legacy

- **WHEN** `settings.processing_mode` is any value other than `"noop"` or `"ocr"`
- **THEN** the system MUST call `preload_ai_models()` and `init_background_worker(app)` (legacy path, v3 mainline does not use)

---

### Requirement: OCR-only model preloading

When `processing_mode='ocr'`, the system SHALL load only the RapidOCR engine at startup. No other AI models (vision, embedding, keyword) SHALL be loaded.

#### Scenario: Only RapidOCR loaded in ocr mode

- **WHEN** `processing_mode='ocr'` and the server starts
- **THEN** `RapidOCRBackend()` MUST be instantiated (triggering ONNX model load), and `get_ai_provider()`, `get_embedding_provider()` MUST NOT be called

#### Scenario: Model load failure in ocr mode

- **WHEN** `RapidOCRBackend()` initialization fails (missing ONNX files, etc.)
- **THEN** the server MUST log the error and exit (fail-fast), not silently fall back to noop mode

---

### Requirement: processing_mode reflected in queue status API

The `GET /v1/ingest/queue/status` response MUST reflect the current `processing_mode` value.

> **Acceptance impact**: HTTP contract delta — `processing_mode` value changes from `"noop"` (P1-S1) to `"ocr"` (P1-S3+). See http_contract_ledger.md §5.

#### Scenario: Queue status shows ocr mode

- **WHEN** `processing_mode='ocr'` and `GET /v1/ingest/queue/status` is called
- **THEN** the response MUST include `"processing_mode": "ocr"`

---

### Requirement: Environment variable configuration

The `processing_mode` MUST be configurable via the `OPENRECALL_PROCESSING_MODE` environment variable.

> **Default value evolution**: P1-S1 through P1-S2b use `"noop"` as the default. **P1-S3 and later stages use `"ocr"` as the default**. This ensures OCR functionality is available out-of-the-box after upgrading to S3+. Users can still explicitly set `OPENRECALL_PROCESSING_MODE=noop` to disable OCR processing (useful for debugging or resource-constrained environments).

#### Scenario: Environment variable override to noop

- **WHEN** `OPENRECALL_PROCESSING_MODE=noop` is set in the environment
- **THEN** `settings.processing_mode` MUST resolve to `"noop"` (OCR disabled)

#### Scenario: Environment variable override to ocr

- **WHEN** `OPENRECALL_PROCESSING_MODE=ocr` is set in the environment
- **THEN** `settings.processing_mode` MUST resolve to `"ocr"`

#### Scenario: Default value (P1-S3+)

- **WHEN** `OPENRECALL_PROCESSING_MODE` is not set
- **THEN** `settings.processing_mode` MUST default to `"ocr"`

---

### Requirement: Graceful shutdown for V3ProcessingWorker

The `V3ProcessingWorker` MUST support graceful shutdown via the same `stop()`/`join()` interface as `NoopQueueDriver`.

#### Scenario: Shutdown signal during processing

- **WHEN** a SIGINT/SIGTERM is received while `V3ProcessingWorker` is processing a frame
- **THEN** the worker MUST complete the current frame's processing (or abandon cleanly), then stop polling for new frames

#### Scenario: Shutdown when idle

- **WHEN** a SIGINT/SIGTERM is received while `V3ProcessingWorker` is sleeping between polls
- **THEN** the worker MUST stop within `poll_interval + 1` seconds
