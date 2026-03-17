## Implementation Tasks

### 1. Query Utilities

- [ ] 1.1 Create `openrecall/server/search/query_utils.py` with `sanitize_fts5_query()` function per `data-model.md §3.0.3` (split by whitespace, strip internal double-quotes, wrap each token in double-quotes)
- [ ] 1.2 Add unit tests for `sanitize_fts5_query()` covering:
  - Basic: `hello world` → `"hello" "world"`, `100.100.0.42` → `"100.100.0.42"`, `foo(bar)` → `"foo(bar)"`, `C++` → `"C++"`
  - Empty/whitespace: empty string → empty string, single space ` ` → empty string, multiple spaces `   ` → empty string
  - Quote handling: `foo"bar` → `"foobar"`, `"""` (only quotes) → empty string, `"hello"` → `"hello"`
  - Unicode: `你好世界` → `"你好世界"`, `C++ 编程` → `"C++" "编程"`
  - Mixed: `foo(bar) "test"` → `"foo(bar)" "test"`

### 2. Search Engine (FTS5-only rewrite)

- [ ] 2.1 Rewrite `openrecall/server/search/engine.py` — replace v2 hybrid search with new `SearchEngine` class using SQLite FTS5 only (remove VectorStore, QueryParser, embedding, reranker dependencies)
- [ ] 2.2 Implement `search()` method with dynamic SQL builder following `data-model.md §3.0.3` JOIN strategy: `frames INNER JOIN ocr_text` base, conditional `frames_fts` JOIN (when app_name/window_name/focused present), conditional `ocr_text_fts` JOIN (when q non-empty). Must include `GROUP BY frames.id` to prevent JOIN explosion.
- [ ] 2.3 Implement ORDER BY logic: `ocr_text_fts.rank, frames.timestamp DESC` when q non-empty; `frames.timestamp DESC` when browsing
- [ ] 2.4 Implement `count()` method using `COUNT(DISTINCT frames.id)` with same JOIN/WHERE clauses as `search()`
- [ ] 2.5 Implement time-range filtering (`start_time`/`end_time` → `frames.timestamp >= ? AND frames.timestamp <= ?`)
- [ ] 2.6 Implement text-length filtering (`min_length`/`max_length` → `ocr_text.text_length >= ? AND ocr_text.text_length <= ?`)
- [ ] 2.7 Implement metadata filtering via `frames_fts MATCH` for `app_name`, `window_name`, `focused` parameters. Verify EXACT MATCH FTS5 column filter syntax is used (e.g., `'app_name:"value"'`).
- [ ] 2.8 Implement `limit` (default 20, max 100) and `offset` (default 0) pagination
- [ ] 2.9 Add per-request latency logging at info level using structured context (e.g., `MRV3 search_latency_ms=X query_type=standard q_present=true`) for search P95 baseline observation
- [ ] 2.10 Add COUNT query latency warning: log warning when `COUNT(DISTINCT frames.id)` exceeds 500ms (observation threshold, non-blocking)

### 3. Search API Route

- [ ] 3.1 Add `GET /v1/search` route in v1 API blueprint (`api_v1.py`) with parameter parsing: `q`, `limit`, `offset`, `start_time`, `end_time`, `app_name`, `window_name`, `focused`, `min_length`, `max_length`, `browser_url` (accepted but no-op), `include_frames` (accepted, always null)
- [ ] 3.2 Implement response serialization matching `spec.md §4.5`: `type: "OCR"`, `content` with `frame_id`, `text`, `timestamp`, `file_path`, `frame_url`, `app_name`, `window_name`, `browser_url` (null), `focused`, `device_name`, `tags` ([]), `pagination` with `limit`/`offset`/`total`
- [ ] 3.3 Ensure reserved fields (`browser_url`, `tags`, `include_frames`/`frame`) are present as `null`/`[]` in response, never omitted

### 4. Search Keyword Guard

- [ ] 4.1 Add `GET /v1/search/keyword` route that returns HTTP 404 Not Found
  - **IMPORTANT**: Register this route AFTER `/v1/search` to avoid shadowing the main search route
  - Add code comment explaining this is a guard route to prevent accidental implementation of independent keyword endpoint
  - Response body: `{"error": "not found", "code": "NOT_FOUND", "request_id": "<uuid>"}`

### 5. Legacy API 410 Gone

- [ ] 5.1 Replace `POST /api/upload` redirect (308) with 410 Gone returning `{"error": "gone", "message": "This API endpoint has been removed"}`
- [ ] 5.2 Replace `GET /api/search` redirect (301) with 410 Gone returning same error body
- [ ] 5.3 Replace `GET /api/queue/status` redirect (301) with 410 Gone returning same error body
- [ ] 5.4 Replace `GET /api/health` redirect (301) with 410 Gone returning same error body
- [ ] 5.5 Remove `[DEPRECATED]` log messages from legacy endpoint handlers

### 6. UI Search Filter Mapping

- [ ] 6.1 Verify Search page filter controls map 1:1 to API parameters: `start_time`/`end_time` (time range), `app_name`, `window_name`, `focused`, `min_length`/`max_length` (text length)
- [ ] 6.2 Update Search page JavaScript to call `GET /v1/search` with correct parameter names and pass through all filter values
- [ ] 6.3 Handle reserved/no-op UI parameters: `browser_url` and `include_frames` are accepted by API but not actively filtered in P1
  - UI SHOULD NOT display filter controls for `browser_url` or `include_frames` (P1 reserved, no-op)
  - If UI must display them for future compatibility, they MUST be clearly marked as "coming soon" or disabled

## Acceptance Verification

### 7. Query Utilities Tests

- [ ] 7.1 Create `tests/test_p1_s4_query_utils.py` — `sanitize_fts5_query` edge cases:
  - Basic tokenization: `hello world` → `"hello" "world"`
  - Special characters: `C++`, `100.100.0.42`, `foo(bar)`
  - Empty/whitespace: `""`, `" "`, `"   "` → `""`
  - Quote handling: `foo"bar` → `"foobar"`, `"""` → `""`
  - Unicode: `你好世界` → `"你好世界"`, `C++ 编程` → `"C++" "编程"`

### 8. FTS Search Tests

- [ ] 8.1 Create `tests/test_p1_s4_search_fts.py` — FTS recall correctness: single-word query, phrase query, prefix matching, empty query, special character escaping (per `p1-s4.md §1.3`)
- [ ] 8.2 Create `tests/test_p1_s4_sql_path.py` — SQL path verification: has-q-no-filter, has-q-has-filter, no-q-has-filter, no-q-no-filter; use loose keyword assertions (e.g. `USING FTS5 SEARCH`), avoid binding to specific SQLite internal plan text
- [ ] 8.3 Create `tests/test_p1_s4_response_schema.py` — Response structure: success response field completeness, empty result structure, reserved fields as null/[], error response format
- [ ] 8.4 Create `tests/test_p1_s4_reference_fields.py` — Reference field completeness: `frame_id` + `timestamp` simultaneously non-null for all results (Hard Gate 100%)

### 9. FTS Clear-Safe and Seam Tests

- [ ] 9.1 Create `tests/test_p1_s4_fts_clear_safe.py` — FTS clear-safe regression: app_name clear, window_name clear, text clear, multi-field clear; verify old tokens have 0 hits after UPDATE
- [ ] 9.2 Create `tests/test_p1_s4_v4_seam.py` — v4 seam protection: `accessibility` table has 0 rows; verify `unexpected_accessibility_rows = 0`

### 10. Legacy API and Keyword Guard Tests

- [ ] 10.1 Create `tests/test_p1_s4_legacy_api.py` — Legacy 410: all 4 endpoints return 410, response body matches unified error format `{"error": "This API endpoint has been removed", "code": "GONE", "request_id": "<uuid>"}`, no `[DEPRECATED]` in logs
- [ ] 10.2 Verify `GET /v1/search/keyword` returns 404 with `{"error": "not found", "code": "NOT_FOUND", "request_id": "<uuid>"}`

### 11. UI and Citation Tests

- [ ] 11.1 Create `tests/test_p1_s4_ui_filter_mapping.py` — UI filter mapping: each filter parameter maps 1:1 to API request (time range, app_name, window_name, focused, combined filters)
- [ ] 11.2 Create `tests/test_p1_s4_citation_backtrace.py` — Citation backtrace: search result → frame/timeline click-through, frame_id resolves, timestamp locates (success rate >= 95%)

### 12. Data Integrity Verification

- [ ] 12.1 Run S3→S4 handoff contract SQL checks:
  - `missing_ocr = 0`: `SELECT COUNT(*) FROM frames f LEFT JOIN ocr_text o ON o.frame_id=f.id WHERE f.status='completed' AND f.text_source='ocr' AND o.id IS NULL;`
  - `orphan_ocr = 0`: `SELECT COUNT(*) FROM ocr_text ot LEFT JOIN frames f ON f.id = ot.frame_id WHERE f.id IS NULL;`
  - `duplicate_ocr_per_frame = 0`: `SELECT COUNT(*) FROM (SELECT frame_id FROM ocr_text GROUP BY frame_id HAVING COUNT(*) > 1);`
  - FTS triggers >= 3: `SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND tbl_name IN ('frames', 'ocr_text');`
  - `ocr_text` row count >= 1: `SELECT COUNT(*) FROM ocr_text;`
- [ ] 12.2 Run search P95 latency baseline: >= 200 queries, record P50/P90/P95/P99 distribution (observation only)
  - **Collection method**: Use automated test script `tests/test_p1_s4_search_latency_baseline.py` that executes:
    1. 50 empty queries (browse mode)
    2. 50 single-word queries
    3. 50 phrase queries
    4. 50 queries with metadata filters (app_name, window_name, focused)
    5. 50 combined queries (text + filters)
  - Script must log individual latencies and compute percentiles using Nearest-rank algorithm
  - Report must include: total queries, P50/P90/P95/P99, max latency, timeout count (>30s)

### 13. End-to-End Acceptance

- [ ] 13.1 Start server, run full test suite (`pytest tests/test_p1_s4_*.py -v`), capture evidence
- [ ] 13.2 Verify all Gate metrics: search reference field completeness = 100%, FTS clear-safe consistency = 100%, v4 seam unexpected_accessibility_rows = 0, legacy API 410 = 100%
- [ ] 13.3 Collect UI evidence: search page filter operation screenshots, API request/response capture
