# UTC+8 Local Timezone Support Design

## Date: 2026-04-26

## Status: ✅ Implemented (2026-04-27)

Implementation tracked in `docs/superpowers/plans/2026-04-26-utc8-local-timezone.md`. All design points below have been delivered. See the plan file's Closeout section for commit history, verification evidence, and triage of pre-existing failures.

## Problem Statement

MyRecall stores all timestamps in UTC but serves a UTC+8 (Asia/Shanghai) user base. This causes two problems:

1. **Display**: Chat responses and API results show UTC times, forcing users to mentally convert.
2. **Query**: Natural language queries like "today" map to UTC midnight, missing frames captured after 08:00 UTC+8 (i.e., 00:00 UTC).

## Solution Overview

Promote local time (UTC+8) to the primary query/display dimension for the **frame capture timestamp**. Keep UTC as a raw backup field. **Internal bookkeeping fields remain UTC.**

- Add `local_timestamp` (UTC+8, ISO8601 without offset) column to `frames`.
- SQL queries filter/sort on `local_timestamp`. SELECT clauses use `local_timestamp AS timestamp` so the store layer returns the correct field name directly.
- API responses: store results pass through to the client unchanged — no field-name mapping in the API layer.
- Frontend `parseTimestamp` becomes timezone-aware: strings with `Z`/`+`/`-` offsets are parsed as-is; bare strings (no offset) are interpreted as UTC+8.
- Pi/Chat SKILL.md simplified: no UTC conversion needed.

## Constraints

- Single fixed timezone: Asia/Shanghai (UTC+8). No configuration needed.
- `timestamp` (UTC) remains as raw backup, never used for query or display.
- No DST handling required (China uses fixed UTC+8 year-round).
- **Browser timezone assumption**: Frontend `datetime-local` pickers submit values in the browser's local timezone. This assumes the user's browser is set to UTC+8. Cross-timezone usage is out of scope for this iteration.
- **Scope: only `frames.timestamp` gets a local mirror.** All other timestamp columns stay UTC (see "Other Timestamps" below).
- **Legacy paths out of scope.** `openrecall/server/api.py` (`/api/*`, mostly 410 Gone), `openrecall/server/database/sql.py`, `openrecall/server/worker.py` legacy v1 path, `openrecall/server/app.py` Jinja templates, and `openrecall/server/templates/index.html` are NOT migrated. The active client web UI is `openrecall/client/web/templates/`.
- **`shared/utils.py` `human_readable_time` / `timestamp_to_human_readable`** are only referenced by legacy server templates; no migration required (audited — see "Audit Notes").
- **`server/utils/query_parser.py`** is not wired into the active v3 search path; no migration required (audited).
- **No historical data.** The database has been wiped; no backfill migration is needed.

## Other Timestamps (Internal — Remain UTC)

These columns continue to use UTC and are NOT mirrored to local time. They are either internal bookkeeping or processing-stage timestamps that users do not directly compare to wall-clock time.

| Column / Field | Table / Source | Visibility | Reason |
|----------------|----------------|------------|--------|
| `timestamp` | `frames` (raw) | Storage only | Backup; never queried/displayed after migration |
| `event_ts` | `frames` | Internal (capture latency math) | Used for capture-to-ingest latency only |
| `ingested_at` | `frames` | Health/queue diagnostics | Internal bookkeeping, system metrics |
| `processed_at` | `frames` | Diagnostics | Internal bookkeeping |
| `applied_at` | `schema_migrations` | Internal | Migration history |
| `timestamp` | `accessibility` | Internal (paired with frame) | Joins to `frames.id`; not exposed |
| `created_at` | `chat_messages` | UI render | Frontend renders via browser `Date()`; UTC ISO with offset, no change needed |
| `created_at`, `updated_at` | `Conversation` JSON files | UI render | Same as above |
| `generated_at` | `frame_descriptions` | Diagnostic surface | Internal; surfaced as `description_generated_at` UTC |
| `created_at`, `started_at`, `completed_at`, `next_retry_at` | `description_tasks` / `embedding_tasks` | Internal queue | Task scheduling |
| `last_frame_ingested_at` | `/v1/health` response | Internal diagnostic | Stays UTC; clients display via Date() |
| `oldest_pending_ingested_at` | `/v1/ingest/queue/status` | Internal diagnostic | Stays UTC |
| `since` | `/api/memories/latest` query param | Polling cursor | Legacy endpoint; not migrated |
| `FrameEmbedding.timestamp` | LanceDB | Internal embedding storage | Falls back to SQLite for display — see "LanceDB" below |

**Frontend implication**: `parseTimestamp` must correctly handle BOTH formats — strings with `Z`/offset (UTC fields above) and bare local strings (only `frames.local_timestamp` mapped to `timestamp` in API response). The new logic does this by branching on the presence of `Z` / `+` / `-` in the offset position.

## Database Changes

### Migration

```sql
-- openrecall/server/database/migrations/20260426000000_add_local_timestamp.sql

ALTER TABLE frames ADD COLUMN local_timestamp TEXT;

-- Index for local time queries
CREATE INDEX idx_frames_local_timestamp ON frames(local_timestamp);
```

No backfill is required because there is no historical data.

### Schema Integrity Check

`migrations_runner.py` has TWO places where the index list is hardcoded — both must be updated:

1. The Python `required_index_names: set` (originally L36-39)
2. The SQL filter `WHERE name IN (...)` (originally L42-45) used to populate `existing_indexes`

If only the set is updated, the SQL query still won't return the new index rows, causing `existing_indexes` to be missing them and `IntegrityError` to be raised on every startup.

### Field Semantics

| Field | Format | Example | Purpose |
|-------|--------|---------|---------|
| `timestamp` | ISO8601 UTC with `Z` | `2026-04-26T08:30:00.123Z` | **Storage only**. Original UTC time, not used for query or display. |
| `local_timestamp` | ISO8601 without offset | `2026-04-26T16:30:00.123` | **Query + sort + API response source**. UTC+8 local time. |

`local_timestamp` intentionally omits the `+08:00` offset — its absence is the marker the frontend uses to detect a local-time field vs. a UTC field.

### Write Path

In `FramesStore._extract_metadata_fields()` and `claim_frame()`, compute `local_timestamp` from the incoming UTC `timestamp`:

```python
from datetime import timezone, timedelta

UTC8 = timezone(timedelta(hours=8))


def _utc_to_local_timestamp(utc_iso: str) -> str:
    dt_utc = datetime.fromisoformat(utc_iso.replace('Z', '+00:00'))
    dt_local = dt_utc.astimezone(UTC8)
    local_ts = dt_local.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]  # millisecond precision
    return local_ts
```

Insert alongside `timestamp` in `INSERT INTO frames ...`.

## API Response Normalization

The store layer produces `timestamp` directly via SQL alias `local_timestamp AS timestamp`. The API layer does **not** do field-name mapping — it passes store results through to the client unchanged.

Benefits:
- No indirection: one `SELECT ... AS timestamp` per query, self-documenting
- No risk of dual-column dicts (`SELECT *` silently carrying both `timestamp` and `local_timestamp`)
- API layer is thin and predictable

Exception: internal worker paths that need the raw UTC `timestamp` (e.g. LanceDB embedding writes) use a dedicated store method (`get_frame_for_embedding`) that selects the original `frames.timestamp` column directly.

## API Changes

### Response Field Mapping

The `timestamp` response field name is preserved across endpoints — its **value source** changes from `frames.timestamp` (UTC) to `frames.local_timestamp` (local), via SQL alias `local_timestamp AS timestamp` in store-layer queries. Other timestamp fields remain UTC.

| Endpoint | Field | Value Source | Format |
|----------|-------|--------------|--------|
| `GET /v1/search` (all modes) | `timestamp` | `local_timestamp AS timestamp` in SQL | Local (no offset) |
| `GET /v1/search` (hybrid/vector via embedding) | `timestamp` | `frames_store.get_frames_by_ids` uses `local_timestamp AS timestamp` | Local (no offset) |
| `GET /v1/frames/<id>/context` | `timestamp` | `local_timestamp AS timestamp` in SQL | Local (no offset) |
| `GET /v1/frames/<id>/similar` | `timestamp` | `local_timestamp AS timestamp` queried per-result | Local (no offset) |
| `GET /v1/timeline` | `timestamp` | `local_timestamp` via store-layer mapping (get_timeline_frames builds its own result dict) | Local (no offset) |
| `GET /v1/activity-summary` | `apps[].first_seen`, `apps[].last_seen`, `time_range.start/end` | `local_timestamp` | Local (no offset) |
| `GET /v1/activity-summary` | `descriptions[].timestamp` | `local_timestamp AS timestamp` (in SQL) | Local (no offset) |
| `GET /v1/health` | `last_frame_timestamp` | `local_timestamp` (via `get_last_frame_timestamp`) | Local (no offset) |
| `GET /v1/health` | `last_frame_ingested_at` | `ingested_at` | UTC with `Z` |
| `GET /v1/ingest/queue/status` | `oldest_pending_ingested_at` | `ingested_at` | UTC with `Z` |
| `GET /v1/ingest/queue/status` | `capture_latency.window_id` | epoch int | n/a |
| `GET /v1/ingest/queue/status` | `status_sync.window_id` | epoch int | n/a |
| `GET /v1/search` results | `event_ts` (if exposed) | `event_ts` | UTC with `Z` |
| `GET /v1/search` results | `ingested_at`, `processed_at` (in detail dicts) | unchanged | UTC with `Z` |
| `GET /v1/frames/<id>/context` | `description.generated_at` | unchanged | UTC with `Z` |

### Query Parameters

`start_time` and `end_time` parameters on `/v1/search`, `/v1/search/counts`, `/v1/activity-summary` accept local time strings and filter on `local_timestamp`:

```python
def _parse_time_filter(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None

    normalized = raw_value.strip().replace(" ", "T")
    if not normalized:
        return None

    # "2026-04-26" -> append time
    if "T" not in normalized and len(normalized) == 10:
        normalized = f"{normalized}T00:00:00"

    # "2026-04-26T08:30" -> append seconds
    if normalized.count(":") == 1:
        normalized = f"{normalized}:00"

    return normalized
```

SQL WHERE clauses change from:
```sql
WHERE timestamp >= ? AND timestamp <= ?
```
to:
```sql
WHERE local_timestamp >= ? AND local_timestamp <= ?
```

**Behavior change**: The frontend `search.html` already sends `datetime-local` values without timezone (e.g., `2026-04-26T08:00:00`). Pre-migration the server compared this naive string against UTC-formatted `timestamp` strings — incorrect for non-UTC users. Post-migration the comparison is against `local_timestamp` (also naive UTC+8) — correct. **This is an intentional bug fix.**

### `/api/memories/latest` (Legacy)

This legacy endpoint is **not migrated**. The active frontend (`index.html`) is updated to use the new `/v1/frames/latest` endpoint instead (see below).

### New Endpoint: `GET /v1/frames/latest`

A lightweight polling endpoint for the grid view to check for newly-arrived frames:

```python
@api_v1_bp.route("/frames/latest", methods=["GET"])
def frames_latest():
    """Return frames newer than a given local timestamp.

    Query Parameters:
        since (str): Local timestamp (e.g. "2026-04-26T16:30:00.123")

    Returns:
        JSON list of frame objects with local timestamps.
    """
    since_str = request.args.get("since", "1970-01-01T00:00:00")
    memories = frames_store.get_memories_since(since_str)
    return jsonify(memories), 200
```

This replaces the legacy `/api/memories/latest` usage in `index.html` `checkNew()`.

### Pi/Chat Timezone Header

Simplify `_build_timezone_header()` in `pi_rpc.py` to two lines:

```
Date: 2026-04-26
Local time now: 2026-04-26T16:30:00
```

Pi no longer needs to convert UTC expressions. SKILL.md is **fully rewritten** (not partially patched) to remove all references to `Local midnight today (UTC)`, `Local midnight yesterday (UTC)`, `Now (UTC)`, `LOCAL_MIDNIGHT_TODAY_UTC`, `NOW_UTC`, and replace example bash snippets with local-time `start_time`/`end_time`.

## Frontend Changes

### Shared `parseTimestamp` in `layout.html`

Instead of duplicating offset-detection logic across three templates, define it once in `layout.html` (which all pages extend):

```javascript
function parseTimestamp(value) {
  const raw = String(value).trim();
  if (!raw) return null;
  // numeric epoch
  if (/^\d+(\.\d+)?$/.test(raw)) {
    return new Date(Number(raw) * 1000);
  }
  const base = raw.includes(' ') ? raw.replace(' ', 'T') : raw;
  // Detect offset/Z at END of string (avoid false positives on date dashes)
  const hasOffset = /[Zz]$/.test(base) || /[+-]\d{2}:?\d{2}$/.test(base);
  const withOffset = hasOffset ? base : base + '+08:00';
  const date = new Date(withOffset);
  return Number.isNaN(date.getTime()) ? null : date;
}
```

All three templates (`index.html`, `search.html`, `timeline.html`) call this shared function. `search.html` currently uses `new Date(ts)` directly and needs to be updated to use `parseTimestamp()` instead.

### `search.html`

Replace direct `new Date(ts)` usage in `formatRelativeTime()` and `formatTimestamp()` with `parseTimestamp()` from `layout.html`.

### `timeline.html`

`formattedTime` getter calls `parseTimestamp()` from `layout.html`.

### `index.html` — `checkNew` Local-Time Cursor

`index.html` `checkNew()` is updated to use the new `/v1/frames/latest` endpoint and send local time:

```javascript
      formatLocalSince(ms) {
        const d = new Date(ms);
        // Convert to UTC+8 wall clock components.
        const utc = d.getTime() + d.getTimezoneOffset() * 60000;
        const local = new Date(utc + 8 * 3600 * 1000);
        const pad = (v) => String(v).padStart(2, '0');
        return `${local.getUTCFullYear()}-${pad(local.getUTCMonth() + 1)}-${pad(local.getUTCDate())}T`
             + `${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}:${pad(local.getUTCSeconds())}.${String(local.getUTCMilliseconds()).padStart(3, '0')}`;
      },

      async checkNew() {
        try {
          const sinceIso = this.lastCheckMs > 0
            ? this.formatLocalSince(this.lastCheckMs)
            : '1970-01-01T00:00:00.000';
          const res = await fetch(`${EDGE_BASE_URL}/v1/frames/latest?since=${encodeURIComponent(sinceIso)}`);
          // ... (rest unchanged)
```

## LanceDB Embedding Store

`FrameEmbedding` records are stored in LanceDB with their own `timestamp` (UTC). LanceDB schema migration is non-trivial (`embedding_store.py:69-86` already has a "drop and recreate" branch on schema mismatch).

**Decision: do NOT modify the LanceDB schema.** LanceDB keeps UTC timestamps; local time is fetched from SQLite at response-build time:

- `hybrid_engine.py` already calls `frames_store.get_frames_by_ids(frame_ids)` to fetch full frame data (`hybrid_engine.py:272`). `get_frames_by_ids` must use an explicit column list with `local_timestamp AS timestamp` (not `SELECT *`).
- `similar_frames` endpoint: per-result SQLite lookup (`api_v1.py`).

**Orphan Embedding Handling**: In `hybrid_engine.py`, both `_vector_only_search` and `_hybrid_search` query LanceDB first, then look up frames in SQLite via `get_frames_by_ids`. If a frame exists in LanceDB but not in SQLite (orphan embedding), the result is **skipped** (`continue`) with a `logger.warning`. No fallback to `emb.timestamp` — mixing UTC and local timestamps in the same response would silently corrupt frontend display. The `_get_recent_embedded_frames` (browse mode) queries SQLite directly with `visibility_status = 'queryable'` and does not hit this path.

**Files affected**:
- `openrecall/server/search/hybrid_engine.py` (2 sites: `_vector_only_search` and `_hybrid_search`)
- `openrecall/server/database/frames_store.py:get_frames_by_ids` (returns `local_timestamp AS timestamp`)
- No changes to `embedding/models.py`, `embedding/service.py`, or `embedding_store.py`.

## Audit Notes (Out of Scope but Verified)

- `openrecall/shared/utils.py` `human_readable_time` / `timestamp_to_human_readable` use naive `datetime.now()` and `fromtimestamp`. Grep shows these are referenced only by `openrecall/server/app.py` (legacy server) and `openrecall/server/templates/timeline.html` (legacy templates). The active client web UI does not use them. **No change required.** A note in CLAUDE.md will direct future contributors to the spec.
- `openrecall/server/utils/query_parser.py` `QueryParser.parse()` uses naive `datetime.now()` for "today/yesterday/last week" parsing. Grep shows no callers in the active v3 search path. **No change required.** If wired in later, `now` should be replaced with `datetime.now(UTC8)` to produce correct local-day boundaries.
- `openrecall/client/buffer.py:72` uses naive `datetime.now()` for unique filename generation only. Filename, not data. **No change required.**

## Files to Modify

| File | Change | Notes |
|------|--------|-------|
| `openrecall/server/database/migrations/20260426000000_add_local_timestamp.sql` | Create | New migration; no backfill needed |
| `openrecall/server/database/migrations_runner.py` | Modify | TWO places: `required_index_names` set AND SQL `IN (...)` clause |
| `openrecall/server/database/frames_store.py` | Modify | Write path (`_utc_to_local_timestamp` + insert); all query methods use `local_timestamp AS timestamp`; add `get_frame_for_embedding` internal method |
| `openrecall/server/embedding/worker.py` | Modify | Use `get_frame_for_embedding` instead of `get_frame_by_id` to read raw UTC timestamp for LanceDB |
| `openrecall/server/search/engine.py` | Modify | WHERE/ORDER BY/SELECT use `local_timestamp` |
| `openrecall/server/search/hybrid_engine.py` | Modify | `_get_recent_embedded_frames` raw SQL uses `local_timestamp` |
| `openrecall/server/api_v1.py` | Modify | `_parse_time_filter`; `similar_frames` per-result SQLite lookup; add `/v1/frames/latest`; docstrings |
| `openrecall/client/web/templates/layout.html` | Modify | Add shared `parseTimestamp()` function |
| `openrecall/client/web/templates/index.html` | Modify | `checkNew()` uses `/v1/frames/latest` + `formatLocalSince()`; uses shared `parseTimestamp()` |
| `openrecall/client/web/templates/search.html` | Modify | Uses shared `parseTimestamp()`; replaces direct `new Date(ts)` usage |
| `openrecall/client/web/templates/timeline.html` | Modify | Uses shared `parseTimestamp()` |
| `openrecall/client/chat/skills/myrecall-search/SKILL.md` | **Rewrite (full file)** | Remove ALL UTC conversion references, including bash snippets and field descriptions |
| `openrecall/client/chat/pi_rpc.py` | Modify | Simplify `_build_timezone_header`; add module-level `UTC8` |
| `tests/test_v3_migrations_bootstrap.py` | Modify | Add migration test (no backfill assertions needed) |
| `tests/test_p1_s1_frames.py` | Modify | Update timestamp assertions for new columns |
| `tests/test_p1_s1_timestamp_contract.py` | Modify | `.endswith("Z")` assertions: split into UTC fields (still Z) and local fields (no Z) |
| `tests/test_p1_s1_health_parsing.py` | Modify | `last_frame_timestamp` is now local; `last_frame_ingested_at` is UTC |
| `tests/test_chat_timezone.py` | Rewrite | Header format changed from 5-line to 2-line |
| `tests/test_chat_mvp_frame_context_api.py` | Modify | Exact timestamp string assertions |
| `tests/test_chat_mvp_activity_summary*.py` (2 files) | Modify | start_time/end_time now local |
| `tests/test_api_memories_since.py` | Modify | `since` parameter and response timestamps are now local |
| `tests/test_p1_s4_*.py` (multiple) | Modify | UTC literals + start_time |
| `tests/test_search_engine.py`, `tests/test_search_api.py` | Modify | start_time literals; expected response timestamp |
| `tests/test_p1_s2a_recorder.py` | Modify | event_ts assertions (event_ts stays UTC) |
| `tests/test_visibility_status.py` | Modify | UTC literals |
| `tests/test_chat_types.py` | Verify | `created_at.isoformat()` continues to work (UTC `+00:00`) — no change expected |
| `scripts/acceptance/p1_s2a_*.{py,sh}` | Modify | Hardcoded UTC iso strings updated to local |
| `scripts/acceptance/p1_s2b_*.sh` | Modify | Same |
| `scripts/verify_phase6.py`, `verify_phase7.py` | Modify | Hardcoded UTC iso ranges updated to local |
| `CLAUDE.md` | Modify | "Frames Table" section: clarify `timestamp` is now local via API normalization; add `local_timestamp` row |

## Testing Strategy

1. **Migration test**: Verify `local_timestamp` column and index are created.
2. **Schema integrity test**: Verify `migrations_runner.verify_schema_integrity` does NOT raise after the migration (catches the L42-45 SQL filter bug).
3. **Write path test**: Ingest a frame with known UTC timestamp, verify `local_timestamp` is exactly UTC+8 (including local-day-rollover case: UTC 20:00 → local 04:00 next day).
4. **Query test**: Query with `start_time=2026-04-26T00:00:00` and `end_time=2026-04-26T23:59:59`, verify only that local day's frames are returned.
5. **API response test**: Verify `timestamp` field in `/v1/search`, `/v1/timeline`, `/v1/activity-summary`, `/v1/frames/<id>/context` responses is local (no `Z`); verify `ingested_at`, `processed_at`, `last_frame_ingested_at` remain UTC (with `Z`).
6. **Hybrid search test**: Verify `_get_recent_embedded_frames` (browse mode) and `_hybrid_search` results carry local-time `timestamp`.
7. **Frontend test (manual)**: Open timeline, search, grid views — verify times displayed match wall-clock UTC+8. Verify `ingested_at` / `processed_at` in metadata panel display correctly (parseTimestamp branches on `Z`).
8. **`/v1/frames/latest` test**: Verify new endpoint returns frames newer than given local timestamp.
9. **Chat header test**: Verify `_build_timezone_header` produces 2-line output; verify SKILL.md no longer references `LOCAL_MIDNIGHT_*_UTC` tokens.
10. **Edge case**: Frame captured at UTC `2026-04-25T20:00:00Z` should have `local_timestamp` equivalent to `2026-04-26T04:00:00` (verify by parsing both sides to datetime objects and comparing, rather than exact string equality — the output format of `_to_utc_iso8601` may vary in trailing precision).
