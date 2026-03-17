## Context

P1-S3 delivered OCR processing, writing `ocr_text` rows and populating `ocr_text_fts`/`frames_fts` indexes. P1-S4 introduces `GET /v1/search` — the first API consumer of these FTS5 indexes.

**Current state**: `openrecall/server/search/engine.py` implements a v2 hybrid search (VectorStore + FTS + reranker + embeddings). This is incompatible with v3 OCR-only FTS5 search. The engine will be **replaced** with a new `SearchEngine` following `data-model.md §3.0.3` JOIN strategy.

**Legacy endpoints**: `api.py` currently returns 301/308 redirects for 4 legacy `/api/*` endpoints. P1-S4 switches these to `410 Gone`.

## Goals / Non-Goals

**Goals:**
- Implement `GET /v1/search` with FTS5 full-text search + metadata filtering per `spec.md §4.5`
- Dynamic SQL builder following `data-model.md §3.0.3` conditional JOIN strategy
- Query normalization via `sanitize_fts5_query()` per `data-model.md §3.0.3`
- Response schema with reference fields (`frame_id`, `timestamp`) as Hard Gate
- Legacy `/api/*` endpoints return `410 Gone` per `http_contract_ledger.md §4.1`
- `/v1/search/keyword` returns `404 Not Found`
- Search P95 latency baseline recording (observation only, no threshold)

**Non-Goals:**
- No embedding/hybrid/vector search (FTS5-only)
- No `expand_search_query` (deferred to P2+)
- No search result caching (deferred to P2)
- No `browser_url` active filtering validation
- No `include_frames` implementation

## Decisions

### D1: Replace v2 SearchEngine entirely
**Decision**: Replace `openrecall/server/search/engine.py` with a new FTS5-only implementation.

**Why not refactor**: The v2 engine depends on `VectorStore`, `QueryParser`, embedding provider, and reranker — none of which are used in v3 OCR-only search. A clean rewrite is simpler than gutting the existing engine.

**screenpipe**: `search_ocr()` in `db.rs:2057` — **aligned** (same FTS5-only approach, dynamic SQL with conditional JOINs).

### D2: Dynamic SQL builder with conditional JOINs
**Decision**: Build SQL dynamically with optional `frames_fts` and `ocr_text_fts` JOINs per `data-model.md §3.0.3`. To prevent duplicate results from 1:N JOINs (multiple OCR lines or tags per frame), all queries must include `GROUP BY frames.id`.

| Condition | `frame_fts_join` | `ocr_fts_join` | `order_clause` |
|-----------|-----------------|----------------|----------------|
| `q` empty, no metadata filters | none | none | `frames.timestamp DESC` |
| `q` empty, has metadata filters | `JOIN frames_fts ON frames.id = frames_fts.id` | none | `frames.timestamp DESC` |
| `q` non-empty, no metadata filters | none | `JOIN ocr_text_fts ON ocr_text.frame_id = ocr_text_fts.frame_id` | `ocr_text_fts.rank, frames.timestamp DESC` |
| `q` non-empty, has metadata filters | both JOINs | both JOINs | `ocr_text_fts.rank, frames.timestamp DESC` |

**screenpipe**: `db.rs:2156-2161` — **aligned** (BM25 rank when query present, timestamp DESC when browsing). `db.rs:2131` — **aligned** (uses `GROUP BY frames.id`).

### D3: Query normalization — sanitize_fts5_query only
**Decision**: Use `sanitize_fts5_query()` from `data-model.md §3.0.3` for user `q` input. No `expand_search_query` in P1.

**screenpipe**: `text_normalizer` — **aligned** (FTS5 injection prevention).

### D4: Module structure
**Decision**: Keep the `openrecall/server/search/` package. Replace `engine.py` internals. Add `query_utils.py` for `sanitize_fts5_query`.

Files:
- `openrecall/server/search/engine.py` — `SearchEngine` class with `search()` and `count()` methods
- `openrecall/server/search/query_utils.py` [NEW] — `sanitize_fts5_query()`, FTS5 MATCH clause builders
- `openrecall/server/api_v1.py` (v1 API blueprint) — Add `/v1/search` route, update or add `/v1/search/keyword` 404 guard
- `openrecall/server/api.py` — Convert legacy redirects to 410 Gone

**screenpipe**: No comparable pattern (Rust module vs Python package).

### D5: Pagination via COUNT(DISTINCT)
**Decision**: `pagination.total` computed via `COUNT(DISTINCT frames.id)` with same JOIN/WHERE as the main query. No caching.

**Performance observation**: Add warning log when COUNT query exceeds 500ms (observation threshold, non-blocking). P1 data volume is expected to be small (~1000 rows), but this provides early warning for larger datasets in P2+.

**Note**: The COUNT query uses the same JOIN/WHERE clauses as the main SELECT query but without GROUP BY (COUNT doesn't need GROUP BY). Both queries must maintain identical filter conditions.

**screenpipe**: **aligned** (screenpipe computes total in the same query scope).

### D6: Legacy 410 Gone with unified error format
**Decision**: Replace 4 redirect handlers in `api.py` with `410 Gone` returning unified error format per `spec.md §4.9`:
```json
{"error": "This API endpoint has been removed", "code": "GONE", "request_id": "<uuid-v4>"}
```

**screenpipe**: **no comparable pattern** (screenpipe has no legacy namespace migration).

### D7: Response serialization
**Decision**: Response follows `spec.md §4.5` exactly. Reserved fields (`browser_url`, `tags`, `include_frames`) are present in response as `null`/`[]`, never omitted.

**screenpipe**: **aligned** (screenpipe returns all fields including null values).

### D8: ocr_text app_name/window_name sync semantics
**Decision**: `ocr_text.app_name` and `ocr_text.window_name` are **write-once copies** populated at OCR processing time from the same `CapturePayload` as `frames.app_name/window_name`. They are NOT automatically synced when `frames` fields are updated.

**Rationale**: Aligns with screenpipe behavior. `ocr_text_fts` trigger fires on `ocr_text` table changes, not `frames` changes. If `frames.app_name` is corrected post-OCR, `ocr_text.app_name` remains unchanged (acceptable drift).

**FTS clear-safe implication**: Clearing `frames.app_name` updates `frames_fts` via trigger, but does NOT update `ocr_text_fts`. This is acceptable because:
1. `ocr_text_fts` MATCH queries only search `text` column in P1 (per D2)
2. `ocr_text_fts.app_name/window_name` are reserved for P2+ column-filter expansion

**screenpipe**: **aligned** (same write-once pattern in `db.rs`).

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| COUNT query slow on large datasets | `idx_frames_timestamp` B-tree covers main filter; P1 data ~1000 rows, risk is low; P2 adds LRU cache |
| `sanitize_fts5_query` may over-quote tokens | Follow `data-model.md` spec exactly; test with special chars (`C++`, `100.100.0.42`, `foo(bar)`) |
| Removing v2 SearchEngine breaks existing `/api/search` | Legacy search is already behind 301 redirect; `/api/search` converts to 410 — old behavior is intentionally removed |
| FTS5 `rank` function differences across SQLite versions | Pin to system SQLite; rank is standard BM25 in FTS5 |
