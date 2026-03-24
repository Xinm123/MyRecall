# Search Content Type Filter — Design

**Date:** 2026-03-24
**Status:** Approved
**Scope:** Client web search page only (`openrecall/client/web/templates/search.html`)

## Overview

Add a content type filter (OCR / AX / All) to the client search page, allowing users to scope search results by text source type. The filter appears as compact pill chips inline with existing filters, with lazy-loaded per-type result counts.

## Decisions

| Decision | Choice |
|---|---|
| Target page | Client web only (`client/web/templates/search.html`) |
| Filter placement | Inline with existing filters as pill tabs |
| Default | `all` |
| Type badge on cards | Always shown |
| AX badge label | `AX` |
| Counts loading | Lazy-loaded after initial search |
| Counts endpoint | New `GET /v1/search/counts` |

## Architecture

```
User clicks pill
      │
      ▼
set selectedContentType in JS state
      │
      ▼
buildQueryString() adds content_type param
      │
      ▼
performSearch() → GET /v1/search?content_type=ocr
      │
      ▼
renderResults() with type badges on cards
      │
      ▼
fetchCounts() → GET /v1/search/counts (same filters, no content_type)
      │
      ▼
populate pill count spans
```

## API Changes

### New: `GET /v1/search/counts`

Return per-type result counts for the given query filters.

**Request params:** Same as `/v1/search` — `q`, `start_time`, `end_time`, `app_name`, `window_name`, `browser_url`, `focused`, `min_length`, `max_length`. No `limit`, `offset`, or `content_type`.

**Response:**
```json
{
  "counts": {
    "ocr": 142,
    "accessibility": 23
  }
}
```

Always returns both keys. Returns `{"counts": {"ocr": 0, "accessibility": 0}}` on empty results.

**Errors:** 400 for invalid params, 500 for server errors. Empty/invalid query returns `{"counts": {"ocr": 0, "accessibility": 0}}`.

**Implementation:** `SearchEngine.count_by_type(params)` — two count queries in one transaction, no frame data, no FTS ranking.

### Existing: `GET /v1/search`

Already supports `content_type` param (ocr/accessibility/all, default: all). No changes needed.

## Backend Files

| File | Change |
|---|---|
| `openrecall/server/api_v1.py` | Add `GET /v1/search/counts` endpoint |
| `openrecall/server/search/engine.py` | Add `count_by_type()` method |

## Frontend Files

| File | Change |
|---|---|
| `openrecall/client/web/templates/search.html` | Add pill filter, type badges, counts fetch |

## Frontend Details

### Filter Pills

Inline with the search form, above the results grid:
- `All` pill (default, active) — no count shown
- `OCR` pill — shows count after search
- `AX` pill — shows count after search

Active pill: accent background tint + accent text.
Inactive pill: border + muted text.

### Type Badge on Cards

In the card footer, adjacent to rank info:
- `OCR` badge (blue-ish tint) for OCR results
- `AX` badge (purple-ish tint) for accessibility results

Always rendered, even in single-type filtered mode.

### JavaScript State

```js
let selectedContentType = 'all';
```

Updated on pill click. Included in `buildQueryString()`. Synced to URL for shareability.

### Counts Flow

After `performSearch()` resolves:
1. Build counts URL from same query params (minus `content_type`)
2. `fetch('/v1/search/counts?' + params)`
3. On success: populate pill count spans
4. On failure: silently leave as `—`, don't block UI

### Error Handling

- Counts endpoint fails: count spans stay `—`
- Invalid content_type in URL: treat as `all`
- Empty results: show `0` for relevant type, `—` for other if counts failed
- AX count 0: normal (accessibility data may not be collected yet)

## Files Summary

### `openrecall/server/api_v1.py`
- New route: `GET /v1/search/counts`
- Reuses parameter parsing from existing search endpoint
- Calls `engine.count_by_type()` and returns JSON

### `openrecall/server/search/engine.py`
- New method: `SearchEngine.count_by_type(params: SearchParams) -> dict`
- Runs two `SELECT COUNT(DISTINCT frames.id)` queries in one transaction
- No frame data, no FTS ranking

### `openrecall/client/web/templates/search.html`
- CSS: pill filter styles, type badge styles
- HTML: pill container in search form, badge in card footer
- JS: `selectedContentType` state, pill click handler, `fetchCounts()` function, updated `buildQueryString()`
