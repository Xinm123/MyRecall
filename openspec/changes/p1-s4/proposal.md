## Why

P1-S3 delivered OCR processing and `ocr_text`/`ocr_text_fts` indexing, but captured text is **not yet searchable** via the API. Users cannot query their screen history. P1-S4 adds the `GET /v1/search` endpoint — the first consumer of the FTS5 index — making OCR results discoverable through keyword search with metadata filtering. This also completes the legacy API removal (410 Gone) and validates the end-to-end data pipeline from capture to retrieval.

**Source precedence**: This proposal touches frozen behavior (search contract §4.5), Gate thresholds (§3.1/§3.5), and data-model JOIN strategy (§3.0.3). SSOTs: `spec.md` > `data-model.md` > `gate_baseline.md` > `p1-s4.md`.

## What Changes

- **New endpoint `GET /v1/search`**: FTS5 full-text search over `ocr_text_fts` with metadata filtering via `frames_fts`, time-range via B-tree index, and text-length filtering via `ocr_text.text_length`. Implements `search_ocr()` JOIN strategy from `data-model.md §3.0.3`.
- **Query normalization**: `sanitize_fts5_query()` for user input → `ocr_text_fts MATCH` (prevents FTS5 operator injection).
- **Response schema**: Matches `spec.md §4.5` — `type:"OCR"`, reference fields `frame_id`+`timestamp` (Hard Gate), reserved fields (`browser_url`, `tags`, `include_frames`) returned as `null`/`[]`.
- **Pagination**: `limit`/`offset` with `pagination.total` via `COUNT(DISTINCT frames.id)`.
- **Sorting**: BM25 rank when `q` is non-empty (`ocr_text_fts.rank, frames.timestamp DESC`); timestamp DESC when browsing.
- **Legacy API removal**: 4 legacy endpoints (`POST /api/upload`, `GET /api/search`, `GET /api/queue/status`, `GET /api/health`) change from 301/308 redirects to `410 Gone` with unified error format.
- **`GET /v1/search/keyword` guard**: Must return `404 Not Found` (no independent keyword endpoint in P1).
- **UI filter mapping**: Search page filters map 1:1 to API parameters (`start_time`/`end_time`, `app_name`, `window_name`, `focused`, `min_length`/`max_length`).

## Non-goals

- **No embedding/hybrid search**: P1 is FTS5-only; no `ocr_text_embeddings` table, no vector similarity.
- **No `expand_search_query`**: OCR concatenation splitting + prefix matching deferred to P2+ fuzzy_match.
- **No accessibility search**: `search_accessibility()` / `search_all()` / `content_type=accessibility/all` are v4 seam only.
- **No search cache**: COUNT computed per-request; LRU cache deferred to P2.
- **No `browser_url` active filtering**: Parameter accepted but not validated as active filter capability in P1.
- **No `include_frames` implementation**: Parameter accepted, always returns `null`.
- **No `ocr_text.app_name/window_name` sync**: `ocr_text` metadata fields are write-once at OCR processing time; not automatically synced when `frames` fields are updated.

## Capabilities

### New Capabilities
- `fts-search`: FTS5 full-text search engine — `search_ocr()` SQL builder, `sanitize_fts5_query`, response serialization, pagination with COUNT
- `legacy-api-removal`: Transition legacy `/api/*` endpoints from redirects to 410 Gone

### Modified Capabilities
_(none — P1-S4 introduces new search capability, no existing spec requirements change)_

## Impact

- **Code**: `openrecall/server/search/engine.py` (major rewrite — FTS5 query builder), `openrecall/server/api.py` (new `/v1/search` route, legacy 410 conversion, `/v1/search/keyword` 404 guard)
- **API surface**: `GET /v1/search` added; 4 legacy endpoints switch to 410 Gone
- **Database**: Read-only consumer of existing `frames`, `ocr_text`, `frames_fts`, `ocr_text_fts` tables; no schema changes
- **Dependencies**: No new dependencies required
- **UI**: Search page filter controls must map 1:1 to API query parameters
