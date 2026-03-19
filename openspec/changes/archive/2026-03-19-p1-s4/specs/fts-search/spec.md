## ADDED Requirements

### Requirement: FTS5 full-text search endpoint
The system SHALL provide a `GET /v1/search` endpoint that performs FTS5 full-text search over OCR text with metadata filtering, returning paginated results with reference fields.

#### Scenario: Keyword search with results
- **WHEN** a client sends `GET /v1/search?q=hello&limit=20&offset=0`
- **THEN** the system returns HTTP 200 with `data` array containing OCR matches where `ocr_text_fts.text MATCH` the sanitized query, ordered by BM25 rank then timestamp DESC, with `pagination.total` reflecting total match count

#### Scenario: Empty query returns all frames
- **WHEN** a client sends `GET /v1/search?q=&limit=20`
- **THEN** the system returns HTTP 200 with `data` array of frames ordered by `frames.timestamp DESC` (browsing mode), joined with `ocr_text` via INNER JOIN

#### Scenario: No results
- **WHEN** a client sends `GET /v1/search?q=nonexistentterm12345`
- **THEN** the system returns HTTP 200 with `data` as empty array and `pagination.total` as 0

### Requirement: Query normalization via sanitize_fts5_query
The system SHALL sanitize user input `q` through `sanitize_fts5_query()` before constructing `ocr_text_fts MATCH` clauses, preventing FTS5 operator injection.

#### Scenario: Special characters are safely quoted
- **WHEN** a client sends `GET /v1/search?q=foo(bar)`
- **THEN** the system constructs MATCH clause with `"foo(bar)"` (quoted token), not interpreting parentheses as FTS5 grouping operators

#### Scenario: Multiple words are individually quoted
- **WHEN** a client sends `GET /v1/search?q=hello world`
- **THEN** the system constructs MATCH clause with `"hello" "world"` (each token quoted)

### Requirement: Metadata filtering via frames_fts
The system SHALL support exact-match metadata filtering through `frames_fts MATCH` for `app_name`, `window_name`, and `focused` parameters. The MATCH expression MUST use column-restricted syntax with quoted values to prevent false matches across columns (e.g., `frames_fts MATCH 'app_name:"Safari"'`).

**Note on `focused` parameter:** In the FTS layer, `focused` is populated via `COALESCE(NEW.focused, 0)`. Thus, frames with `focused=null` and `focused=false` are both indexed as `0`. A query for `focused:0` will match both. This is an accepted boundary condition since the UI only supports filtering by `focused=true`.

#### Scenario: Filter by app_name
- **WHEN** a client sends `GET /v1/search?app_name=Safari`
- **THEN** only frames where `frames_fts` matches the query `'app_name:"Safari"'` are returned

#### Scenario: Filter by focused state (true)
- **WHEN** a client sends `GET /v1/search?focused=true`
- **THEN** only frames where `frames_fts` matches the query `'focused:1'` are returned

#### Scenario: Filter by focused state (false)
- **WHEN** a client sends `GET /v1/search?focused=false`
- **THEN** only frames where `frames_fts` matches the query `'focused:0'` are returned
- **NOTE**: This includes frames with `focused=null` AND `focused=false` (both indexed as `0` per `COALESCE(NEW.focused, 0)` in trigger)

#### Scenario: Filter by focused state omitted
- **WHEN** a client sends `GET /v1/search` without `focused` parameter
- **THEN** no focused filter is applied; frames with any focused state are returned

#### Scenario: Combined metadata and text search
- **WHEN** a client sends `GET /v1/search?q=code&app_name=VSCode&focused=true`
- **THEN** frames matching all three conditions (using `'app_name:"VSCode" focused:1'`) are returned, ordered by BM25 rank

### Requirement: Time range filtering via B-tree index
The system SHALL support `start_time` and `end_time` ISO8601 UTC parameters for time-range filtering using the `idx_frames_timestamp` B-tree index.

#### Scenario: Time range filter
- **WHEN** a client sends `GET /v1/search?start_time=2026-03-01T00:00:00Z&end_time=2026-03-02T00:00:00Z`
- **THEN** only frames with `frames.timestamp` within the specified range are returned

### Requirement: Text length filtering
The system SHALL support `min_length` and `max_length` uint parameters to filter by `ocr_text.text_length`.

#### Scenario: Minimum text length
- **WHEN** a client sends `GET /v1/search?min_length=100`
- **THEN** only frames with OCR text of at least 100 characters are returned

### Requirement: Pagination with total count
The system SHALL support `limit` (max 100, default 20) and `offset` (default 0) pagination parameters, returning `pagination.total` via `COUNT(DISTINCT frames.id)`.

#### Scenario: Paginated results
- **WHEN** a client sends `GET /v1/search?q=test&limit=10&offset=10`
- **THEN** results 11-20 are returned with `pagination.total` reflecting the full count

#### Scenario: Limit exceeds maximum
- **WHEN** a client sends `GET /v1/search?limit=200`
- **THEN** the limit is clamped to 100

### Requirement: Response schema with reference fields
The system SHALL return responses matching `spec.md §4.5` format with `type: "OCR"` items containing `frame_id` and `timestamp` (Hard Gate fields), and reserved fields (`browser_url`, `tags`, `include_frames`) as `null`/`[]`.

**Acceptance impact**: `frame_id` + `timestamp` completeness is a Hard Gate per `gate_baseline.md §3.1`. 100% completeness required.

#### Scenario: Reference fields always present
- **WHEN** any search result is returned
- **THEN** every item in `data` contains `content.frame_id` (non-null integer) and `content.timestamp` (non-null ISO8601 string)

#### Scenario: Reserved fields are explicit null
- **WHEN** any search result is returned
- **THEN** `content.browser_url` is `null` (not omitted), `content.tags` is `[]`, and `content.frame` is `null` (for `include_frames=false`)

### Requirement: BM25 ranking when query present
The system SHALL order results by `ocr_text_fts.rank` (BM25) then `frames.timestamp DESC` when `q` is non-empty, and by `frames.timestamp DESC` when `q` is empty.

#### Scenario: BM25 ordering with query
- **WHEN** a client sends `GET /v1/search?q=important`
- **THEN** results are ordered by BM25 relevance score, with ties broken by most recent timestamp

#### Scenario: Timestamp ordering without query
- **WHEN** a client sends `GET /v1/search` (no `q` parameter)
- **THEN** results are ordered by `frames.timestamp` descending (most recent first)

### Requirement: Search keyword endpoint guard
The system SHALL NOT expose `GET /v1/search/keyword` as an independent endpoint. Requests to this path MUST return `404 Not Found`.

#### Scenario: Keyword endpoint returns 404
- **WHEN** a client sends `GET /v1/search/keyword`
- **THEN** the system returns HTTP 404

### Requirement: Dynamic SQL with conditional JOINs
The system SHALL construct SQL following `data-model.md §3.0.3` JOIN strategy: `frames INNER JOIN ocr_text` always, with `frames_fts` JOIN only when metadata filters are present, and `ocr_text_fts` JOIN only when `q` is non-empty.

#### Scenario: No filters, no query (browse mode)
- **WHEN** `q` is empty and no metadata filters are specified
- **THEN** SQL uses `frames INNER JOIN ocr_text` with no FTS JOINs, ordered by `frames.timestamp DESC`

#### Scenario: Query only
- **WHEN** `q` is "hello" with no metadata filters
- **THEN** SQL adds `JOIN ocr_text_fts ON ocr_text.frame_id = ocr_text_fts.frame_id` with MATCH clause

#### Scenario: Metadata filter only
- **WHEN** `q` is empty but `app_name=Safari` is specified
- **THEN** SQL adds `JOIN frames_fts ON frames.id = frames_fts.id` with MATCH clause

### Requirement: Search P95 latency observation
The system SHALL record per-request latency for `GET /v1/search` and log P95 statistics for baseline observation (no hard threshold in P1-S4).

**Acceptance impact**: Per `gate_baseline.md §3.5`, P1-S4 records actual distribution only. SLO threshold deferred to P1-S7.

#### Scenario: Latency recorded
- **WHEN** any search request completes
- **THEN** the elapsed time (API receive to last byte sent) is logged at info level
