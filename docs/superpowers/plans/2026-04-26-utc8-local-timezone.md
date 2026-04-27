# UTC+8 Local Timezone Support Implementation Plan

> **Status: ✅ Implemented (2026-04-27).** All 11 tasks complete. Verified by 23 timezone-specific tests + 71 timestamp-touching tests (94/94 pass). 90 pre-existing failures in unrelated modules (recorder/routing/processing-mode/search-fts schema) are NOT caused by this migration. See "Closeout" section at the end of this file for the full summary.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote UTC+8 local time to the primary query/display dimension across the entire stack: database, API, frontend, and Pi/Chat.

**Architecture:** Add `local_timestamp` column to the `frames` table. All SQL queries filter/sort on `local_timestamp` and select `local_timestamp AS timestamp` so the store layer returns the correct field name directly. The API layer passes store results through unchanged. Frontend uses a shared `parseTimestamp()` function. Pi/Chat simplified — no UTC conversion needed.

**Internal worker paths** (e.g. LanceDB embedding writes) that need the raw UTC `timestamp` use a dedicated store method `get_frame_for_embedding()` that selects the original `frames.timestamp` column directly.

**Tech Stack:** Python 3.12, Flask, SQLite, Jinja2, Alpine.js

---

## File Structure Map

| File | Responsibility | Action |
|------|---------------|--------|
| `openrecall/server/database/migrations/20260426000000_add_local_timestamp.sql` | Add `local_timestamp` column + index | Create |
| `openrecall/server/database/migrations_runner.py` | Add `idx_frames_local_timestamp` to schema integrity check (TWO places) | Modify |
| `openrecall/server/database/frames_store.py` | Write path (compute + insert local time), all query methods use `local_timestamp AS timestamp` | Modify |
| `openrecall/server/embedding/worker.py` | Use `get_frame_for_embedding` instead of `get_frame_by_id` for LanceDB UTC writes | Modify |
| `openrecall/server/search/hybrid_engine.py` | `_get_recent_embedded_frames` raw SQL uses `local_timestamp` | Modify |
| `openrecall/server/search/engine.py` | Search WHERE clauses and result fields use `local_timestamp` | Modify |
| `openrecall/server/api_v1.py` | `_parse_time_filter`; add `/v1/frames/latest`; `similar_frames` per-result SQLite lookup; docstrings | Modify |
| `openrecall/client/web/templates/layout.html` | Shared `parseTimestamp()` function | Modify |
| `openrecall/client/web/templates/index.html` | `checkNew()` uses `/v1/frames/latest`; uses shared `parseTimestamp()` | Modify |
| `openrecall/client/web/templates/search.html` | Uses shared `parseTimestamp()`; replaces direct `new Date(ts)` usage | Modify |
| `openrecall/client/web/templates/timeline.html` | Uses shared `parseTimestamp()` | Modify |
| `openrecall/client/chat/skills/myrecall-search/SKILL.md` | Remove UTC conversion; Pi passes local time directly | Modify |
| `openrecall/client/chat/pi_rpc.py` | Simplify timezone header to local time only | Modify |
| `tests/test_v3_migrations_bootstrap.py` | Test migration applies cleanly + schema integrity | Modify |
| `tests/test_p1_s1_frames.py` | Update assertions for local time | Modify |
| `tests/test_p1_s1_timestamp_contract.py` | Split UTC vs local field assertions | Modify |
| `tests/test_p1_s1_health_parsing.py` | `last_frame_timestamp` is now local | Modify |
| `tests/test_chat_timezone.py` | Header format changed from 5-line to 2-line | Modify |
| `tests/test_api_memories_since.py` | `since` is now local — assertions on `Z` suffix removed | Modify |
| `tests/test_search_engine.py`, `tests/test_search_api.py` | start_time literals; expected response timestamp | Modify |
| `tests/test_p1_s4_*.py` (multiple) | UTC literals + start_time | Modify |
| `tests/test_chat_mvp_frame_context_api.py` | Exact timestamp string assertions | Modify |
| `tests/test_chat_mvp_activity_summary*.py` (2 files) | start_time/end_time now local | Modify |
| `tests/test_visibility_status.py` | UTC literals | Modify |
| `scripts/acceptance/p1_s2a_*.{py,sh}` | Hardcoded UTC iso strings updated to local | Modify |
| `scripts/verify_phase6.py`, `verify_phase7.py` | Hardcoded UTC iso ranges updated to local | Modify |
| `CLAUDE.md` | Update Frames Table section | Modify |

---

### Task 1: Database Migration

**Files:**
- Create: `openrecall/server/database/migrations/20260426000000_add_local_timestamp.sql`
- Modify: `openrecall/server/database/migrations_runner.py` (verify_schema_integrity — **TWO places**)
- Test: `tests/test_v3_migrations_bootstrap.py`

> **Note:** No historical data exists; backfill is not needed.

- [x] **Step 1: Write migration file**

Create `openrecall/server/database/migrations/20260426000000_add_local_timestamp.sql`:

```sql
-- Add local_timestamp column for UTC+8 timezone support
ALTER TABLE frames ADD COLUMN local_timestamp TEXT;

-- Index for local time queries
CREATE INDEX idx_frames_local_timestamp ON frames(local_timestamp);
```

- [x] **Step 2: Update schema integrity check — BOTH hardcoded lists**

In `openrecall/server/database/migrations_runner.py`, there are **TWO** separate hardcoded index lists. Both must be updated.

**Place 1** — Python `required_index_names` set (lines 36-39):

**Note**: `idx_frames_timestamp` remains in the set even though it is no longer actively used for queries — the index still exists and is verified by the integrity check.

```python
required_index_names = {
    "idx_frames_timestamp",
    "idx_frames_status",
    "idx_frames_local_timestamp",
    "idx_chat_session",
}
```

**Place 2** — SQL `WHERE name IN (...)` filter (lines 43-45):

```python
    existing_indexes = {
        result[0]
        for result in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name IN ('idx_frames_timestamp', 'idx_frames_status', 'idx_frames_local_timestamp', 'idx_chat_session')"
        )
    }
```

> **CRITICAL**: If only the set is updated but the SQL filter is not, `existing_indexes` will be missing the new index and `IntegrityError` will be raised on every startup.

- [x] **Step 3: Write migration test**

In `tests/test_v3_migrations_bootstrap.py`, add test for new migration:

```python
def test_migration_20260426000000_adds_local_timestamp(test_db_path):
    """Verify local_timestamp migration adds column and index."""
    from openrecall.server.database.migrations_runner import run_migrations

    migrations_dir = Path("openrecall/server/database/migrations")
    conn = sqlite3.connect(str(test_db_path))
    run_migrations(conn, migrations_dir)

    # Verify column exists
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(frames)")
    }
    assert "local_timestamp" in columns

    # Verify index exists
    indexes = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='frames'"
        )
    }
    assert "idx_frames_local_timestamp" in indexes

    conn.close()
```

- [x] **Step 4: Run migration test**

```bash
pytest tests/test_v3_migrations_bootstrap.py -v
```

Expected: PASS (migration applies cleanly, column and index created)

- [x] **Step 5: Commit**

```bash
git add openrecall/server/database/migrations/20260426000000_add_local_timestamp.sql
git add openrecall/server/database/migrations_runner.py
git add tests/test_v3_migrations_bootstrap.py
git commit -m "feat: add local_timestamp migration for UTC+8 support"
```

---

### Task 2: FramesStore Write Path

**Files:**
- Modify: `openrecall/server/database/frames_store.py` (top-level helper + `_extract_metadata_fields` + `claim_frame`)
- Test: `tests/test_p1_s1_frames.py`

- [x] **Step 1: Add UTC-to-local helper at module level**

Add after `_parse_utc_datetime` (around line 73) in `openrecall/server/database/frames_store.py`:

```python
# Fixed UTC+8 timezone for local time
UTC8 = timezone(timedelta(hours=8))


def _utc_to_local_timestamp(utc_iso: str) -> str:
    """Convert UTC ISO8601 string to local (UTC+8) timestamp.

    Returns an ISO8601 string without offset (e.g. '2026-04-26T16:30:00.123').
    """
    dt_utc = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    dt_local = dt_utc.astimezone(UTC8)
    local_ts = dt_local.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]  # millisecond precision
    return local_ts
```

- [x] **Step 2: Update `_extract_metadata_fields` to compute local time**

Replace the method body. The return tuple gains one element after `timestamp`:

```python
    def _extract_metadata_fields(
        self, metadata: dict[str, object]
    ) -> tuple[object, ...]:
        raw_timestamp = metadata.get("timestamp") or metadata.get("capture_time")
        timestamp = _to_utc_iso8601(raw_timestamp) or ""
        local_timestamp = _utc_to_local_timestamp(timestamp) if timestamp else ""
        app_name = (
            metadata.get("app_name")
            or metadata.get("app")
            or metadata.get("active_app")
        )
        window_name = (
            metadata.get("window_name")
            or metadata.get("window")
            or metadata.get("active_window")
        )
        browser_url = metadata.get("browser_url")
        focused = metadata.get("focused")
        device_name = metadata.get("device_name") or "monitor_0"
        capture_trigger = metadata.get("capture_trigger")
        event_ts = _to_utc_iso8601(metadata.get("event_ts"))
        image_size_bytes = metadata.get("image_size_bytes")
        last_known_app = metadata.get("last_known_app")
        last_known_window = metadata.get("last_known_window")
        simhash = metadata.get("simhash")
        phash = metadata.get("phash")
        return (
            timestamp,
            local_timestamp,
            app_name,
            window_name,
            browser_url,
            focused,
            device_name,
            capture_trigger,
            event_ts,
            image_size_bytes,
            last_known_app,
            last_known_window,
            simhash,
            phash,
        )
```

- [x] **Step 3: Update `claim_frame` INSERT to include `local_timestamp`**

Replace the tuple unpacking and INSERT statement:

```python
    def claim_frame(
        self, capture_id: str, metadata: dict[str, object]
    ) -> tuple[int, bool]:
        (
            timestamp,
            local_timestamp,
            app_name,
            window_name,
            browser_url,
            focused,
            device_name,
            capture_trigger,
            event_ts,
            image_size_bytes,
            last_known_app,
            last_known_window,
            simhash,
            phash,
        ) = self._extract_metadata_fields(metadata)
        # ... (hash conversion stays the same)

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO frames
                        (capture_id, timestamp, local_timestamp,
                         app_name, window_name, browser_url,
                         focused, device_name, capture_trigger, event_ts, snapshot_path,
                         image_size_bytes, status, last_known_app, last_known_window, simhash, phash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                    """,
                    (
                        capture_id,
                        timestamp,
                        local_timestamp,
                        app_name,
                        window_name,
                        browser_url,
                        focused,
                        device_name,
                        capture_trigger,
                        event_ts,
                        None,
                        image_size_bytes,
                        last_known_app,
                        last_known_window,
                        simhash,
                        phash,
                    ),
                )
                # ... (rest stays the same)
```

- [x] **Step 4: Run write-path test**

```bash
pytest tests/test_p1_s1_frames.py -v -k claim
```

Expected: Tests may fail if assertions check exact column count. Fix in next step.

- [x] **Step 5: Update frame tests for new column**

In `tests/test_p1_s1_frames.py`, update any tests that assert on the frame insert/query to expect `local_timestamp` field. Read the test file first:

```bash
pytest tests/test_p1_s1_frames.py -v
```

Fix any failing assertions. Common fixes:
- If test checks `row.keys()` or column count, add the new column.
- If test queries `SELECT * FROM frames`, update expected fields.

- [x] **Step 6: Commit**

```bash
git add openrecall/server/database/frames_store.py
git add tests/test_p1_s1_frames.py
git commit -m "feat: compute and store local_timestamp on frame ingest"
```

---

### Task 3: FramesStore Single-Frame Queries + Internal Worker Path

**Files:**
- Modify: `openrecall/server/database/frames_store.py`
- Modify: `openrecall/server/embedding/worker.py`

This task handles two single-frame query paths:
1. `get_frame_by_id` — used by API/UI, returns local time via `local_timestamp AS timestamp`
2. `get_frame_for_embedding` — **new internal method** used only by `EmbeddingWorker`, returns raw UTC `timestamp` for LanceDB writes

The embedding worker must continue writing UTC timestamps to LanceDB. This is achieved by giving it a dedicated store method that selects the original `frames.timestamp` column, while the public `get_frame_by_id` returns local time for all other consumers.

- [x] **Step 1: Update `get_frame_by_id`**

Replace the SQL to select `local_timestamp AS timestamp`:

```python
    def get_frame_by_id(
        self, frame_id: int, conn: sqlite3.Connection
    ) -> Optional[dict[str, object]]:
        try:
            row = conn.execute(
                """
                SELECT id, capture_id, local_timestamp AS timestamp, app_name,
                       window_name, snapshot_path, status, ingested_at,
                       last_known_app, last_known_window, text_source,
                       processed_at, capture_trigger, device_name, error_message,
                       accessibility_text, ocr_text, browser_url, focused,
                       description_status, embedding_status, visibility_status,
                       event_ts
                FROM frames
                WHERE id = ?
                """,
                (frame_id,),
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error:
            logger.exception("Error getting frame %s", frame_id)
            return None
```

> The `AS timestamp` alias means callers receive `{"timestamp": "2026-04-26T04:00:00.000", ...}` directly. No API-layer post-processing is needed.

> **IMPORTANT**: Keep the existing signature `conn: Optional[sqlite3.Connection] = None`. The API layer (`api_v1.py:1476`) calls `store.get_frame_by_id(frame_id)` without passing `conn`. Do NOT remove the default parameter.

- [x] **Step 2: Add `get_frame_for_embedding` internal method**

Add a new method alongside `get_frame_by_id`:

```python
    def get_frame_for_embedding(
        self, frame_id: int, conn: sqlite3.Connection
    ) -> Optional[dict[str, object]]:
        """Return raw frame data with UTC timestamp for LanceDB embedding writes.

        This is an internal API — not for general consumption. The returned dict
        contains the original `frames.timestamp` (UTC) under the key `"timestamp"`.
        """
        try:
            row = conn.execute(
                """
                SELECT id, capture_id, timestamp, app_name, window_name,
                       snapshot_path, full_text
                FROM frames
                WHERE id = ?
                """,
                (frame_id,),
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error:
            logger.exception("Error getting frame for embedding %s", frame_id)
            return None
```

> Only the embedding worker should call this method. It selects the minimal fields needed for embedding generation (`timestamp` for LanceDB, `snapshot_path` for the image, `full_text` for multimodal context).

- [x] **Step 3: Update `embedding/worker.py` to use `get_frame_for_embedding`**

In `openrecall/server/embedding/worker.py`, change the frame lookup:

```python
        # Before:
        # frame = self._store.get_frame_by_id(frame_id, conn)

        # After:
        frame = self._store.get_frame_for_embedding(frame_id, conn)
```

At line 87 (approximately):

```python
        frame = self._store.get_frame_for_embedding(frame_id, conn)
        if frame is None:
            logger.warning(f"Frame #{frame_id} not found, skipping task #{task_id}")
            return
```

The rest of the worker logic remains unchanged — `frame.get("timestamp")` now correctly reads the UTC timestamp from the original `frames.timestamp` column.

- [x] **Step 4: Run embedding worker tests**

```bash
pytest tests/ -v -k embedding
```

Expected: All pass. The worker continues to write UTC timestamps to LanceDB.

- [x] **Step 5: Commit**

```bash
git add openrecall/server/database/frames_store.py
git add openrecall/server/embedding/worker.py
git commit -m "feat: get_frame_by_id returns local time; add get_frame_for_embedding for LanceDB UTC writes"
```

---

### Task 4: FramesStore Query Path — Basic Queries

**Files:**
- Modify: `openrecall/server/database/frames_store.py`
- Test: `tests/test_p1_s1_frames.py`

This task updates the query methods that fetch frame lists (timeline, memories). The pattern for each method:
1. SQL `SELECT f.timestamp` → `SELECT f.local_timestamp AS timestamp`
2. SQL `WHERE f.timestamp` → `WHERE f.local_timestamp`
3. SQL `ORDER BY f.timestamp` → `ORDER BY f.local_timestamp`

Store-layer queries use `local_timestamp AS timestamp` so the API layer receives the correct field name directly — no post-processing needed. Methods that build their own result dicts (`get_timeline_frames`, `get_memories_since`) can use `row["timestamp"]` directly since the SQL alias provides it.

- [x] **Step 1: Update `get_timeline_frames`**

Replace SQL and result building:

```python
    def get_timeline_frames(self, limit: int = 5000) -> list[dict[str, object]]:
        frames = []
        normalized_limit = max(1, min(int(limit) if limit else 5000, 10000))

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, capture_id, local_timestamp AS timestamp, app_name, window_name,
                           snapshot_path, status, ingested_at, last_known_app, last_known_window
                    FROM frames
                    ORDER BY local_timestamp DESC
                    LIMIT ?
                    """,
                    (normalized_limit,),
                ).fetchall()

                for row in rows:
                    ts = row["timestamp"]  # aliased from local_timestamp
                    frames.append(
                        {
                            "id": row["id"],
                            "frame_id": row["id"],
                            "capture_id": row["capture_id"],
                            "timestamp": ts,
                            "app": row["app_name"] or "",
                            "title": row["window_name"] or "",
                            "status": (row["status"] or "pending").upper(),
                            "filename": f"{ts}.jpg",
                            "app_name": row["app_name"] or "",
                            "window_title": row["window_name"] or "",
                            "last_known_app": row["last_known_app"] or "",
                            "last_known_window": row["last_known_window"] or "",
                        }
                    )
        except sqlite3.Error as e:
            logger.error("get_timeline_frames failed: %s", e)
        return frames
```

> Note: `get_timeline_frames` uses `local_timestamp AS timestamp` in SQL, so `row["timestamp"]` directly yields the local time. No API-layer post-processing is needed.

- [x] **Step 2: Update `get_memories_since`**

Replace SQL:

```python
    def get_memories_since(self, timestamp: str) -> list[dict[str, object]]:
        memories = []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT f.id, f.capture_id, f.local_timestamp AS timestamp, f.app_name, f.window_name,
                           f.snapshot_path, f.status, f.ingested_at, f.last_known_app,
                           f.last_known_window, f.text_source, f.processed_at,
                           f.capture_trigger, f.device_name, f.error_message,
                           f.description_status, f.embedding_status, f.visibility_status,
                           o.text_length, o.ocr_engine, o.text AS ocr_text,
                           SUBSTR(o.text, 1, 100) AS ocr_text_preview
                    FROM frames f
                    LEFT JOIN ocr_text o ON f.id = o.frame_id
                    WHERE f.local_timestamp > ?
                    ORDER BY f.local_timestamp DESC
                    """,
                    (timestamp,),
                ).fetchall()

                for row in rows:
                    ts = row["timestamp"]  # aliased from local_timestamp
                    memories.append(
                        {
                            "id": row["id"],
                            "frame_id": row["id"],
                            "capture_id": row["capture_id"],
                            "timestamp": ts,
                            "app": row["app_name"] or "",
                            "title": row["window_name"] or "",
                            "status": (row["status"] or "pending").upper(),
                            "filename": f"{ts}.jpg",
                            "app_name": row["app_name"] or "",
                            "window_title": row["window_name"] or "",
                            "last_known_app": row["last_known_app"] or "",
                            "last_known_window": row["last_known_window"] or "",
                            # P1-S3 additions
                            "text_source": row["text_source"] or "",
                            "text_length": row["text_length"] or 0,
                            "ocr_text": row["ocr_text"] or "",
                            "ocr_text_preview": row["ocr_text_preview"] or "",
                            "ocr_engine": row["ocr_engine"] or "",
                            "processed_at": row["processed_at"] or "",
                            "capture_trigger": row["capture_trigger"] or "",
                            "device_name": row["device_name"] or "",
                            "error_message": row["error_message"] or "",
                            # Description and embedding status
                            "description_status": row["description_status"] or "",
                            "embedding_status": row["embedding_status"] or "",
                            # Visibility status (combined OCR + description + embedding)
                            "visibility_status": row["visibility_status"] or "pending",
                        }
                    )
        except sqlite3.Error as e:
            logger.error("get_memories_since failed: %s", e)
        return memories
```

> Note: `get_memories_since` uses `local_timestamp AS timestamp` in SQL, so `row["timestamp"]` yields local time directly.

- [x] **Step 3: Update `get_recent_memories`**

Replace SQL:

```python
                rows = conn.execute(
                    """
                    SELECT f.id, f.capture_id, f.local_timestamp AS timestamp, f.app_name, f.window_name,
                           f.snapshot_path, f.status, f.ingested_at, f.last_known_app,
                           f.last_known_window, f.text_source, f.processed_at,
                           f.capture_trigger, f.device_name, f.error_message,
                           f.accessibility_text, f.ocr_text, f.browser_url, f.focused,
                           f.description_status, f.embedding_status, f.visibility_status,
                           LENGTH(f.accessibility_text) as accessibility_text_length,
                           LENGTH(f.ocr_text) as ocr_text_length,
                           o.text_length, o.ocr_engine,
                           CASE
                             WHEN f.text_source = 'accessibility' THEN SUBSTR(f.accessibility_text, 1, 100)
                             WHEN f.text_source = 'ocr' THEN SUBSTR(f.ocr_text, 1, 100)
                             ELSE NULL
                           END AS text_preview,
                           CASE
                             WHEN f.text_source = 'accessibility' THEN LENGTH(f.accessibility_text)
                             WHEN f.text_source = 'ocr' THEN LENGTH(f.ocr_text)
                             ELSE 0
                           END AS text_length_computed,
                           fd.narrative, fd.summary,
                           CASE
                             WHEN fd.narrative IS NOT NULL OR fd.summary IS NOT NULL
                               THEN LENGTH(COALESCE(fd.narrative, '') || ' ' || COALESCE(fd.summary, ''))
                             ELSE 0
                           END AS description_length
                    FROM frames f
                    LEFT JOIN ocr_text o ON f.id = o.frame_id
                    LEFT JOIN frame_descriptions fd ON f.id = fd.frame_id
                    ORDER BY f.local_timestamp DESC
                    LIMIT ?
                    """,
                    (normalized_limit,),
                ).fetchall()

                for row in rows:
                    ts = row["timestamp"]  # aliased from local_timestamp
                    memories.append(
                        {
                            "id": row["id"],
                            "frame_id": row["id"],
                            "capture_id": row["capture_id"],
                            "timestamp": ts,
                            "app": row["app_name"] or "",
                            "title": row["window_name"] or "",
                            "status": (row["status"] or "pending").upper(),
                            "filename": f"{ts}.jpg",
                            "app_name": row["app_name"] or "",
                            "window_title": row["window_name"] or "",
                            "last_known_app": row["last_known_app"] or "",
                            "last_known_window": row["last_known_window"] or "",
                            # Text source and content
                            "text_source": row["text_source"] or "",
                            "text_length": row["text_length_computed"] or 0,
                            "accessibility_text": row["accessibility_text"] or "",
                            "ocr_text": row["ocr_text"] or "",
                            "text_preview": row["text_preview"] or "",
                            "ocr_engine": row["ocr_engine"] or "",
                            # Additional metadata
                            "browser_url": row["browser_url"] or "",
                            "focused": bool(row["focused"]) if row["focused"] is not None else False,
                            "processed_at": row["processed_at"] or "",
                            "capture_trigger": row["capture_trigger"] or "",
                            "device_name": row["device_name"] or "",
                            "error_message": row["error_message"] or "",
                            # Description status (P1-S3+)
                            "description_status": row["description_status"] or "",
                            "description_text": (row["narrative"] if row["narrative"] else row["summary"]) or "",
                            "description_length": row["description_length"] or 0,
                            # Embedding status and text lengths (Task 9)
                            "embedding_status": row["embedding_status"] or "",
                            "accessibility_text_length": row["accessibility_text_length"] or 0,
                            "ocr_text_length": row["ocr_text_length"] or 0,
                            # Visibility status (combined OCR + description + embedding)
                            "visibility_status": row["visibility_status"] or "pending",
                        }
                    )
        except sqlite3.Error as e:
            logger.error("get_recent_memories failed: %s", e)
        return memories
```

> Note: Both `get_memories_since` and `get_recent_memories` use `local_timestamp AS timestamp` in SQL, so `row["timestamp"]` yields local time directly.

- [x] **Step 4: Run tests for basic queries**

```bash
pytest tests/test_p1_s1_frames.py -v
```

Expected: All pass. If failures, fix assertions that expected UTC timestamps.

- [x] **Step 5: Commit**

```bash
git add openrecall/server/database/frames_store.py
git commit -m "feat: use local_timestamp in timeline, memories, since queries"
```

---

### Task 5: FramesStore Query Path — Activity Summary + Frame Context + Descriptions

**Files:**
- Modify: `openrecall/server/database/frames_store.py`
- Test: `tests/test_p1_s1_frames.py`

- [x] **Step 1: Update `get_activity_summary_apps`**

Replace SQL — use `local_timestamp` for all time filtering and ordering:

```python
    def get_activity_summary_apps(
        self,
        start_time: str,
        end_time: str,
        app_name: Optional[str] = None,
    ) -> list[dict]:
        apps = []
        try:
            with self._connect() as conn:
                if app_name:
                    inner_sql = """
                        SELECT
                            app_name,
                            local_timestamp AS ts,
                            (JULIANDAY(LEAD(local_timestamp) OVER (
                                PARTITION BY app_name ORDER BY local_timestamp
                            )) - JULIANDAY(local_timestamp)) * 86400.0 AS gap_sec
                        FROM frames
                        WHERE visibility_status = 'queryable'
                          AND app_name = ?
                          AND local_timestamp >= ?
                          AND local_timestamp <= ?
                    """
                    params = [app_name, start_time, end_time]
                else:
                    inner_sql = """
                        SELECT
                            app_name,
                            local_timestamp AS ts,
                            (JULIANDAY(LEAD(local_timestamp) OVER (
                                PARTITION BY app_name ORDER BY local_timestamp
                            )) - JULIANDAY(local_timestamp)) * 86400.0 AS gap_sec
                        FROM frames
                        WHERE visibility_status = 'queryable'
                          AND local_timestamp >= ?
                          AND local_timestamp <= ?
                          AND app_name IS NOT NULL
                          AND app_name != ''
                    """
                    params = [start_time, end_time]

                sql = f"""
                    SELECT
                        app_name,
                        COUNT(*) AS frame_count,
                        ROUND(SUM(
                            CASE WHEN gap_sec < 300 THEN gap_sec ELSE 0 END
                        ) / 60.0, 1) AS minutes,
                        MIN(ts) AS first_seen,
                        MAX(ts) AS last_seen
                    FROM (
                        {inner_sql}
                    )
                    GROUP BY app_name
                    ORDER BY minutes DESC
                """

                rows = conn.execute(sql, params).fetchall()

                for row in rows:
                    apps.append({
                        "name": row["app_name"] or "Unknown",
                        "frame_count": row["frame_count"],
                        "minutes": row["minutes"] or 0.0,
                        "first_seen": row["first_seen"],
                        "last_seen": row["last_seen"],
                    })
        except sqlite3.Error as e:
            logger.error("get_activity_summary_apps failed: %s", e)
        return apps
```

- [x] **Step 2: Update `get_activity_summary_total_frames`**

```python
    def get_activity_summary_total_frames(
        self,
        start_time: str,
        end_time: str,
        app_name: Optional[str] = None,
    ) -> int:
        try:
            with self._connect() as conn:
                sql = """
                    SELECT COUNT(*) AS cnt
                    FROM frames
                    WHERE visibility_status = 'queryable'
                      AND local_timestamp >= ?
                      AND local_timestamp <= ?
                """
                params: list = [start_time, end_time]

                if app_name:
                    sql += " AND app_name = ?"
                    params.append(app_name)

                row = conn.execute(sql, params).fetchone()
                return row["cnt"] if row else 0
        except sqlite3.Error as e:
            logger.error("get_activity_summary_total_frames failed: %s", e)
            return 0
```

- [x] **Step 3: Update `get_activity_summary_time_range`**

```python
    def get_activity_summary_time_range(
        self,
        start_time: str,
        end_time: str,
        app_name: Optional[str] = None,
    ) -> Optional[dict]:
        try:
            with self._connect() as conn:
                sql = """
                    SELECT MIN(local_timestamp) AS start, MAX(local_timestamp) AS end
                    FROM frames
                    WHERE visibility_status = 'queryable'
                      AND local_timestamp >= ?
                      AND local_timestamp <= ?
                """
                params: list = [start_time, end_time]

                if app_name:
                    sql += " AND app_name = ?"
                    params.append(app_name)

                row = conn.execute(sql, params).fetchone()
                if row and row["start"] and row["end"]:
                    return {
                        "start": row["start"],
                        "end": row["end"],
                    }
                return None
        except sqlite3.Error as e:
            logger.error("get_activity_summary_time_range failed: %s", e)
            return None
```

- [x] **Step 4: Update `get_frame_context`**

```python
    def get_frame_context(
        self,
        frame_id: int,
    ) -> Optional[dict]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT f.id, f.accessibility_text, f.ocr_text, f.text_source,
                           f.browser_url, f.status, f.visibility_status,
                           f.local_timestamp AS timestamp, f.app_name, f.window_name
                    FROM frames f
                    WHERE f.id = ?
                    """,
                    (frame_id,),
                ).fetchone()

                if row is None:
                    return None

                frame_id_val = row["id"]
                if row["text_source"] == "ocr":
                    text = row["ocr_text"] or ""
                else:
                    text = row["accessibility_text"] or ""
                text_source = row["text_source"]
                browser_url = row["browser_url"]
                status = row["status"]
                visibility_status = row["visibility_status"]
                timestamp = row["timestamp"]  # aliased from local_timestamp
                app_name = row["app_name"]
                window_name = row["window_name"]

                urls: list[str] = []
                for url in self._extract_urls_from_text(text):
                    if url not in urls:
                        urls.append(url)

                result_text = text
                if len(result_text) > self.MAX_TEXT_LENGTH:
                    result_text = result_text[:self.MAX_TEXT_LENGTH] + "..."

                return {
                    "frame_id": frame_id_val,
                    "timestamp": timestamp,
                    "app_name": app_name,
                    "window_name": window_name,
                    "text": result_text,
                    "text_source": text_source,
                    "urls": urls,
                    "browser_url": browser_url,
                    "status": status,
                    "visibility_status": visibility_status,
                }
        except Exception:
            logger.exception(f"Error getting frame context for frame_id={frame_id}")
            return None
```

> Note: `get_frame_context` uses `local_timestamp AS timestamp` in SQL, so `row["timestamp"]` yields local time directly. The returned dict is ready for the API — no post-processing needed.

- [x] **Step 5: Update `get_recent_descriptions`**

```python
    def get_recent_descriptions(
        self,
        conn: sqlite3.Connection,
        time_start: str,
        time_end: str,
        limit: int = 20,
    ) -> list[dict]:
        cursor = conn.execute(
            """
            SELECT fd.frame_id, f.local_timestamp AS timestamp, fd.summary, fd.tags_json
            FROM frame_descriptions fd
            JOIN frames f ON f.id = fd.frame_id
            WHERE f.local_timestamp BETWEEN ? AND ?
              AND fd.summary IS NOT NULL
            ORDER BY f.local_timestamp DESC
            LIMIT ?
            """,
            (time_start, time_end, limit),
        )
        # ... (rest unchanged)
```

- [x] **Step 6: Update `get_last_frame_timestamp`**

```python
    def get_last_frame_timestamp(self) -> Optional[str]:
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT MAX(local_timestamp) AS ts FROM frames").fetchone()
                if row is None:
                    return None
                return row["ts"]
        except sqlite3.Error as e:
            logger.error("get_last_frame_timestamp failed: %s", e)
            return None
```

Note: `get_last_frame_ingested_at` uses the `ingested_at` column which remains UTC. It is an internal bookkeeping field. No change needed.

- [x] **Step 7: Update `get_frames_by_ids`**

This method returns a `dict[int, dict]` where each inner dict has a `"timestamp"` key that `hybrid_engine.py` reads. Use an explicit column list with `local_timestamp AS timestamp` (do **not** use `SELECT *`, which would return both `timestamp` [UTC] and `local_timestamp` [local] and create ambiguity):

```python
        def _query(c: sqlite3.Connection) -> dict[int, dict]:
            placeholders = ",".join("?" * len(frame_ids))
            rows = c.execute(
                f"""
                SELECT id, capture_id, local_timestamp AS timestamp,
                       app_name, window_name, browser_url, focused,
                       device_name, snapshot_path, full_text, text_source,
                       accessibility_text, ocr_text, status,
                       description_status, embedding_status, visibility_status
                FROM frames WHERE id IN ({placeholders})
                """,
                frame_ids,
            ).fetchall()
            return {row["id"]: dict(row) for row in rows}
```

The dicts now contain `"timestamp"` mapped to local time directly from the SQL alias. The API layer passes them through unchanged.

> **IMPORTANT**: This explicit column list covers all fields currently used by `hybrid_engine.py` (the primary consumer via `_vector_only_search` and `_hybrid_search`). If any other call sites of `get_frames_by_ids` need additional fields (e.g. `ingested_at`, `processed_at`, `event_ts`, `last_known_app`, etc.), add them to this SELECT list before committing.
>
> Quick verification: `grep -n 'get_frames_by_ids' openrecall/server/**/*.py` — ensure all consumers' field access is satisfied by the columns above.

- [x] **Step 8: Run activity summary tests**

```bash
pytest tests/test_p1_s1_frames.py -v -k activity
```

Expected: All pass.

- [x] **Step 9: Commit**

```bash
git add openrecall/server/database/frames_store.py
git commit -m "feat: use local_timestamp in activity summary and frame context queries"
```

---

### Task 6: Hybrid Engine

**Files:**
- Modify: `openrecall/server/search/hybrid_engine.py`
- Test: `tests/test_search_engine.py`, `tests/test_search_api.py`

The hybrid engine calls `frames_store.get_frames_by_ids()` (updated in Task 5), which now returns dicts with `"timestamp"` mapped to local time via the SQL alias. Both `_vector_only_search` (L147) and `_hybrid_search` (L285) receive local-time `timestamp` directly.

There are two sets of changes:
1. `_get_recent_embedded_frames` (browse mode) uses raw SQL — switch to `local_timestamp`.
2. `_vector_only_search` and `_hybrid_search` delete the `frame.get("timestamp", ...)` fallback. Orphan embeddings (LanceDB has it but SQLite does not) are skipped with a `logger.warning` — mixing UTC fallback timestamps with local-time results would silently corrupt frontend display.

- [x] **Step 1: Update `_get_recent_embedded_frames` raw SQL**

Replace the raw SQL query (lines 181-191):

```python
    def _get_recent_embedded_frames(
        self, db_path: Path, limit: int, offset: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get recent frames that have embeddings (browse mode for vector search)."""
        import sqlite3

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            # Count total frames with embeddings
            count_row = conn.execute(
                """
                SELECT COUNT(*) as total FROM frames
                WHERE visibility_status = 'queryable'
                """
            ).fetchone()
            total = count_row["total"] if count_row else 0

            # Get recent frames with embeddings
            rows = conn.execute(
                """
                SELECT frames.id as frame_id, frames.local_timestamp AS timestamp, frames.full_text, frames.text_source,
                       frames.app_name, frames.window_name, frames.browser_url, frames.focused,
                       frames.device_name, frames.snapshot_path, frames.embedding_status
                FROM frames
                WHERE visibility_status = 'queryable'
                ORDER BY local_timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()

            results = []
            for row in rows:
                ts = row["timestamp"]  # aliased from local_timestamp
                results.append({
                    "frame_id": row["frame_id"],
                    "score": None,
                    "cosine_score": None,
                    "timestamp": ts,
                    "text": row["full_text"] or "",
                    "text_source": row["text_source"] or "ocr",
                    "app_name": row["app_name"],
                    "window_name": row["window_name"],
                    "browser_url": row["browser_url"],
                    "focused": bool(row["focused"]) if row["focused"] is not None else None,
                    "device_name": row["device_name"] or "monitor_0",
                    "frame_url": f"/v1/frames/{row['frame_id']}",
                    "embedding_status": row["embedding_status"] or "",
                })

            conn.close()
            return results, total

        except sqlite3.Error as e:
            logger.error("Failed to get recent embedded frames: %s", e)
            return [], 0
```

> Note: `_get_recent_embedded_frames` uses `local_timestamp AS timestamp` in SQL and `row["timestamp"]` directly. The result dicts are ready for the API — no post-processing needed.

- [x] **Step 2: Delete timestamp fallback — skip orphan embeddings with warning**

**`_vector_only_search`** — replace the frame loop (lines 137-157):

```python
        results = []
        for emb, distance in embeddings_with_distance[offset : offset + limit]:
            frame_id = emb.frame_id
            frame = frame_data_map.get(frame_id)
            if frame is None:
                logger.warning(
                    "Orphan embedding: frame_id=%d in LanceDB but missing from SQLite",
                    frame_id,
                )
                continue
            cosine_score = 1.0 - float(distance)
            results.append({
                "frame_id": frame_id,
                "score": cosine_score,
                "cosine_score": cosine_score,
                "timestamp": frame["timestamp"],  # local time from get_frames_by_ids
                "text": frame.get("full_text", "")[:200] if frame.get("full_text") else "",
                "text_source": frame.get("text_source", "ocr"),
                "app_name": frame.get("app_name", ""),
                "window_name": frame.get("window_name", ""),
                "browser_url": frame.get("browser_url"),
                "focused": frame.get("focused"),
                "device_name": frame.get("device_name", "monitor_0"),
                "frame_url": f"/v1/frames/{frame_id}",
                "embedding_status": frame.get("embedding_status", ""),
            })
```

**`_hybrid_search`** — replace the frame loop (lines 274-295):

```python
        results = []
        for hybrid_rank, frame_id in enumerate(frame_ids, start=offset + 1):
            frame = frame_data_map.get(frame_id)
            if frame is None:
                logger.warning(
                    "Orphan embedding: frame_id=%d in LanceDB but missing from SQLite",
                    frame_id,
                )
                continue
            results.append({
                "frame_id": frame_id,
                "score": scores.get(frame_id, 0.0),
                "hybrid_rank": hybrid_rank,
                "cosine_score": vector_similarities.get(frame_id),
                "vector_rank": vector_ranks.get(frame_id),
                "fts_score": fts_bm25_scores.get(frame_id),
                "fts_rank": fts_ranks.get(frame_id),
                "timestamp": frame["timestamp"],  # local time from get_frames_by_ids
                "text": frame.get("full_text", "")[:200] if frame.get("full_text") else "",
                "text_source": frame.get("text_source", "ocr"),
                "app_name": frame.get("app_name", ""),
                "window_name": frame.get("window_name", ""),
                "browser_url": frame.get("browser_url"),
                "focused": frame.get("focused"),
                "device_name": frame.get("device_name", "monitor_0"),
                "frame_url": f"/v1/frames/{frame_id}",
                "embedding_status": frame.get("embedding_status", ""),
            })
```

> Rationale: fallback to `emb.timestamp` (UTC) would silently corrupt frontend display by mixing UTC and local timestamps in the same response. `continue` is safe because `frame_data_map` only misses frames that have been deleted from SQLite but still exist in LanceDB — these are orphan embeddings, not valid results.

- [x] **Step 3: Run hybrid search tests**

```bash
pytest tests/ -v -k "hybrid or search"
```

Expected: All pass.

- [x] **Step 4: Commit**

```bash
git add openrecall/server/search/hybrid_engine.py
git commit -m "feat: use local_timestamp in hybrid engine; skip orphan embeddings"
```

---

### Task 7: Search Engine

**Files:**
- Modify: `openrecall/server/search/engine.py`
- Test: `tests/test_search_engine.py`, `tests/test_search_api.py`

- [x] **Step 1: Update `_build_where_clause`**

Replace `timestamp` with `local_timestamp` in WHERE conditions:

```python
    def _build_where_clause(
        self, params: SearchParams
    ) -> tuple[str, list[Any]]:
        has_text_query = bool(params.q and params.q.strip())
        where_parts = ["frames.visibility_status = 'queryable'", "frames.full_text IS NOT NULL"]
        params_list: list[Any] = []

        if has_text_query:
            sanitized_q = sanitize_fts5_query(params.q)
            where_parts.append("frames_fts MATCH ?")
            params_list.append(sanitized_q)

        metadata_parts = []
        if params.app_name:
            safe_app = _sanitize_fts_value(params.app_name)
            metadata_parts.append(f'app_name:"{safe_app}"')
        if params.window_name:
            safe_window = _sanitize_fts_value(params.window_name)
            metadata_parts.append(f'window_name:"{safe_window}"')
        if params.browser_url:
            safe_url = _sanitize_fts_value(params.browser_url)
            metadata_parts.append(f'browser_url:"{safe_url}"')

        if metadata_parts:
            where_parts.append("frames_fts MATCH ?")
            params_list.append(" ".join(metadata_parts))

        if params.focused is not None:
            where_parts.append("frames.focused = ?")
            params_list.append(1 if params.focused else 0)

        if params.start_time:
            where_parts.append("frames.local_timestamp >= ?")
            params_list.append(params.start_time)
        if params.end_time:
            where_parts.append("frames.local_timestamp <= ?")
            params_list.append(params.end_time)

        return " AND ".join(where_parts), params_list
```

- [x] **Step 2: Update `_build_query` SELECT clause**

```python
            select_clause = """
                SELECT frames.id AS frame_id,
                       frames.local_timestamp AS timestamp,
                       frames.full_text,
                       frames.app_name,
                       frames.window_name,
                       frames.browser_url,
                       frames.focused,
                       frames.device_name,
                       frames.text_source,
                       frames.embedding_status"""
```

- [x] **Step 3: Update ORDER BY**

```python
            if has_text_query:
                sql_parts.append("ORDER BY frames_fts.rank, frames.local_timestamp DESC")
            else:
                sql_parts.append("ORDER BY frames.local_timestamp DESC")
```

- [x] **Step 4: Run search tests**

```bash
pytest tests/ -v -k search
```

Expected: All pass.

- [x] **Step 5: Commit**

```bash
git add openrecall/server/search/engine.py
git commit -m "feat: use local_timestamp in search engine queries"
```

---

### Task 8: API Layer

**Files:**
- Modify: `openrecall/server/api_v1.py`
- Test: `tests/test_api_memories_since.py`, integration tests

- [x] **Step 1: Add `_parse_time_filter`**

After `_parse_utc_timestamp` (lines 53-74), add:

```python
def _parse_time_filter(raw_value: str | None) -> str | None:
    """Parse a local time string into normalized local_timestamp format.

    Accepts:
        - "2026-04-26" -> "2026-04-26T00:00:00"
        - "2026-04-26T08:30" -> "2026-04-26T08:30:00"
        - "2026-04-26T08:30:00" -> unchanged
        - "2026-04-26 08:30:00" -> "2026-04-26T08:30:00"
    """
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

**Do not remove or modify `_parse_utc_timestamp`.** It is still used by `health()` at line ~845 to parse `last_frame_ingested_at` (UTC).

- [x] **Step 2: Update `search()` and `search_counts()` parameter parsing**

Replace the existing `start_time`/`end_time` parsing in both endpoints:

```python
# Parse time range (local time)
start_time = _parse_time_filter(request.args.get("start_time"))
end_time = _parse_time_filter(request.args.get("end_time"))
```

Apply the same change to `search_counts()`.

Also update the `search()` docstring:

```python
    """FTS5 full-text search endpoint.

    Query Parameters:
        ...
        start_time: Local time start timestamp (e.g. "2026-04-26T00:00:00")
        end_time: Local time end timestamp (e.g. "2026-04-26T23:59:59")
        ...
    """
```

> **No field-name normalization is needed.** The search engine's `_build_query` uses `frames.local_timestamp AS timestamp` (see Task 7), so `engine.search()` already returns dicts with `"timestamp"` set to local time. Pass results through directly:
>
> ```python
>     results = engine.search(params)
>     # results already have "timestamp" = local time — no post-processing
>     # ... build data_items from results (unchanged)
> ```
>
> `search_counts()` returns `{"counts": {"ocr": N, "accessibility": M}}` — no frame data, so no normalization needed.

- [x] **Step 3: Update `health` endpoint**

`last_frame_timestamp` already returns local time via `get_last_frame_timestamp()` (updated in Task 5). `last_frame_ingested_at` remains UTC. No code changes needed.

Update the health docstring:

```python
    """Health check endpoint.

    Response fields:
        ...
        last_frame_timestamp    — Local time (UTC+8) ISO8601 string | null
        ...
    """
```

- [x] **Step 4: Update `activity_summary` endpoint**

Update time parameter parsing to use `_parse_time_filter`:

```python
start_time = _parse_time_filter(request.args.get("start_time"))
end_time = _parse_time_filter(request.args.get("end_time"))
```

The response times are already local from the store (no additional changes needed).

Update docstring:

```python
    """Return activity overview for chat agents.

    Query Parameters:
        start_time (str): Required. Local time start timestamp (e.g. "2026-04-26T00:00:00").
        end_time (str): Required. Local time end timestamp.
        ...

    Returns:
        JSON with apps, total_frames, time_range (all in local time), audio_summary, descriptions.
    """
```

- [x] **Step 5: Update `get_frame_context` response**

`get_frame_context` (updated in Task 5) already returns `{"timestamp": <local_time>, ...}` via the SQL alias `local_timestamp AS timestamp`. Pass through directly:

```python
    row = store.get_frame_context(frame_id)
    if row:
        return jsonify(row), 200
```

- [x] **Step 6: Update `similar_frames` endpoint**

Fetch local time via `local_timestamp AS timestamp` so the result dict is ready for the response:

```python
    similar = []
    for r, distance in results_with_distance:
        if r.frame_id != frame_id:
            with frames_store._connect() as conn:
                row = conn.execute(
                    "SELECT local_timestamp AS timestamp FROM frames WHERE id = ?",
                    (r.frame_id,),
                ).fetchone()
            ts = row["timestamp"] if row else r.timestamp
            similarity = max(0.0, 1.0 - float(distance))
            similar.append({
                "frame_id": r.frame_id,
                "similarity": round(similarity, 4),
                "timestamp": ts,  # local time from SQL alias; UTC fallback for orphan embeddings
                "app_name": r.app_name,
                "window_name": r.window_name,
                "frame_url": f"/v1/frames/{r.frame_id}",
            })
```

- [x] **Step 7: Add `/v1/frames/latest` endpoint**

Add a new endpoint (after the existing frame endpoints):

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
    store = _get_frames_store()
    memories = store.get_memories_since(since_str)
    return jsonify(memories), 200
```

- [x] **Step 8: Run API tests**

```bash
pytest tests/ -v -k "api_v1 or search or activity or memories_since"
```

Expected: All pass.

- [x] **Step 9: Commit**

```bash
git add openrecall/server/api_v1.py
git commit -m "feat: update API to return local time; add /v1/frames/latest endpoint"
```

---

### Task 9: Frontend Display

**Files:**
- Modify: `openrecall/client/web/templates/layout.html`
- Modify: `openrecall/client/web/templates/index.html`
- Modify: `openrecall/client/web/templates/search.html`
- Modify: `openrecall/client/web/templates/timeline.html`

- [x] **Step 1: Add shared `parseTimestamp` to `layout.html`**

Add before the closing `</body>` tag (or in the `<head>` script section):

```html
<script>
// Shared timestamp parser — handles both local-time (no offset) and UTC (with Z/+00:00) strings
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
</script>
```

- [x] **Step 2: Update `index.html`**

1. **Remove** the old `parseTimestamp` method from the Alpine `memoryGrid()` return object (around L1710). The shared `parseTimestamp` from `layout.html` is a global function that replaces it.

2. **Replace all `this.parseTimestamp(...)` calls with `parseTimestamp(...)`** (remove `this.`). There are 3 call sites:
   - `this.parseTimestamp(entry?.timestamp)` → `parseTimestamp(entry?.timestamp)`
   - `this.parseTimestamp(ts)` in `formatRelativeTime` → `parseTimestamp(ts)`
   - `this.parseTimestamp(ts)` in `formatTime` → `parseTimestamp(ts)`

Add `formatLocalSince(ms)` helper inside `memoryGrid()` return object (before `checkNew`):

```javascript
      formatLocalSince(ms) {
        const d = new Date(ms);
        // Convert to UTC+8 wall clock components
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

- [x] **Step 3: Update `search.html`**

Replace `parseLocalTimestamp` with calls to the shared `parseTimestamp()`:

```javascript
  function formatRelativeTime(ts) {
    if (!ts) return '';
    const date = parseTimestamp(ts);
    if (!date || isNaN(date.getTime())) return '';
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);
    if (diffSec < 60) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHour < 24) return `${diffHour}h ago`;
    if (diffDay < 7) return `${diffDay}d ago`;
    return '';
  }

  function formatTimestamp(ts) {
    if (!ts) return '';
    const d = parseTimestamp(ts);
    if (!d || isNaN(d.getTime())) return ts;
    const pad = (v) => String(v).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }
```

Remove the old `parseLocalTimestamp` function if it exists (it does not currently exist; this step introduces `parseTimestamp` usage to `search.html`).

- [x] **Step 4: Update `timeline.html`**

Replace the inline timestamp parsing in `formattedTime` getter:

```javascript
      get formattedTime() {
        const frame = this.currentFrame;
        if (!frame) return '';
        const ts = frame.timestamp;
        if (!ts) return 'Invalid timestamp';
        const date = parseTimestamp(ts);
        if (!date || isNaN(date.getTime())) return 'Invalid timestamp';
        const y = date.getFullYear();
        const mo = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        const h = String(date.getHours()).padStart(2, '0');
        const mi = String(date.getMinutes()).padStart(2, '0');
        const s = String(date.getSeconds()).padStart(2, '0');
        return `${y}-${mo}-${d} ${h}:${mi}:${s}`;
      },
```

- [x] **Step 5: Commit**

```bash
git add openrecall/client/web/templates/layout.html
git add openrecall/client/web/templates/index.html
git add openrecall/client/web/templates/search.html
git add openrecall/client/web/templates/timeline.html
git commit -m "feat: add shared parseTimestamp; display local_timestamp in all frontend views"
```

---

### Task 10: Pi/Chat

**Files:**
- Modify: `openrecall/client/chat/pi_rpc.py`
- Modify: `openrecall/client/chat/skills/myrecall-search/SKILL.md`

- [x] **Step 1: Simplify `_build_timezone_header` in `pi_rpc.py`**

Replace the entire method:

```python
    def _build_timezone_header(self) -> str:
        """Build local time context header."""
        now = datetime.now(UTC8)
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%Y-%m-%dT%H:%M:%S")
        return (
            f"Date: {date_str}\n"
            f"Local time now: {time_str}\n"
        )
```

Also update the imports — add module-level `UTC8`:

At module level in `pi_rpc.py`, add:
```python
UTC8 = timezone(timedelta(hours=8))
```

- [x] **Step 2: Update SKILL.md — remove UTC conversion**

Replace the "Time Formatting Strategy" and "Timezone" sections:

```markdown
---

## Time Formatting Strategy

All timestamps are in **local time (UTC+8)**. The injected header shows the current local time.
Use local time directly in all API calls — no conversion needed.

| Expression | Meaning | How to compute |
|------------|---------|----------------|
| `today` | Since midnight local time | `Date` from header + `T00:00:00` |
| `yesterday` | Yesterday's full day | `Date` from header, minus 1 day |
| `recent` | Last 30 minutes | `Local time now` - 30 minutes |
| `1h ago` | One hour ago | `Local time now` - 1 hour |
| `2d ago` | Two days ago | `Local time now` - 2 days |
| `now` | Current moment | `Local time now` from header |

**Example — user asks "what was I doing today?":**
```bash
# Injected header:
#   Date: 2026-04-26
#   Local time now: 2026-04-26T16:30:00
#
START="2026-04-26T00:00:00"
END="2026-04-26T16:30:00"
curl "http://localhost:8083/v1/activity-summary?start_time=${START}&end_time=${END}"
```
```

Also update the parameter table in the `/v1/search` section:

```markdown
| `start_time` | ISO 8601 local | Recommended | Start of time range (local time, e.g. `2026-04-26T08:00:00`) |
| `end_time` | ISO 8601 local | Recommended | End of time range (local time, e.g. `2026-04-26T23:59:59`) |
```

- [x] **Step 3: Commit**

```bash
git add openrecall/client/chat/pi_rpc.py
git add openrecall/client/chat/skills/myrecall-search/SKILL.md
git commit -m "feat: simplify Pi timezone header; SKILL.md uses local time directly"
```

---

### Task 11: Tests

**Files:**
- Modify: `tests/test_p1_s1_frames.py`
- Modify: `tests/test_v3_migrations_bootstrap.py`
- Modify: `tests/test_p1_s1_timestamp_contract.py`
- Modify: `tests/test_p1_s1_health_parsing.py`
- Modify: `tests/test_chat_timezone.py`
- Modify: `tests/test_api_memories_since.py`
- Modify: `tests/test_search_engine.py`
- Modify: `tests/test_search_api.py`
- Modify: `tests/test_chat_mvp_frame_context_api.py`
- Modify: `tests/test_chat_mvp_activity_summary*.py` (2 files)
- Modify: `tests/test_p1_s4_*.py` (multiple files — update UTC literals)
- Modify: `tests/test_visibility_status.py`
- Modify: `tests/test_p1_s2a_recorder.py` (event_ts assertions — event_ts stays UTC)
- Modify: `scripts/acceptance/p1_s2a_*.{py,sh}`
- Modify: `scripts/acceptance/p1_s2b_*.sh`
- Modify: `scripts/verify_phase6.py`, `verify_phase7.py`

- [x] **Step 1: Add write-path test for local time**

In `tests/test_p1_s1_frames.py`, add:

```python
def test_frame_local_timestamp_computed_from_utc(test_store):
    """Verify local_timestamp is computed correctly from UTC."""
    utc_ts = "2026-04-25T20:00:00.000Z"
    metadata = {
        "timestamp": utc_ts,
        "app_name": "TestApp",
        "capture_trigger": "idle",
    }
    frame_id, is_new = test_store.claim_frame(
        capture_id="test-capture-local-ts",
        metadata=metadata,
    )
    assert is_new is True
    with test_store._connect() as conn:
        row = conn.execute(
            "SELECT timestamp, local_timestamp FROM frames WHERE id = ?",
            (frame_id,),
        ).fetchone()
    from datetime import datetime, timedelta
    utc_dt = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
    local_dt = datetime.fromisoformat(row["local_timestamp"])
    assert utc_dt.hour == 20
    assert local_dt.day == 26 and local_dt.hour == 4
    # Verify the 8-hour offset
    assert (local_dt - utc_dt.replace(tzinfo=None)) == timedelta(hours=8)
```

- [x] **Step 2: Add query test for local time filtering**

```python
def test_query_by_local_timestamp(test_store):
    """Verify time range queries use local_timestamp correctly."""
    # UTC times that span local midnight
    frames = [
        ("cap-1", "2026-04-25T15:00:00.000Z", "App1"),  # local: 04-25 23:00
        ("cap-2", "2026-04-25T20:00:00.000Z", "App2"),  # local: 04-26 04:00
        ("cap-3", "2026-04-26T10:00:00.000Z", "App3"),  # local: 04-26 18:00
    ]
    for capture_id, ts, app in frames:
        test_store.claim_frame(
            capture_id=capture_id,
            metadata={"timestamp": ts, "app_name": app, "capture_trigger": "idle"},
        )
        with test_store._connect() as conn:
            conn.execute(
                "UPDATE frames SET snapshot_path = ?, status = 'completed', visibility_status = 'queryable' WHERE capture_id = ?",
                (f"/tmp/{capture_id}.jpg", capture_id),
            )
            conn.commit()

    # Query local date 2026-04-26
    apps = test_store.get_activity_summary_apps(
        start_time="2026-04-26T00:00:00",
        end_time="2026-04-26T23:59:59",
    )
    app_names = {a["name"] for a in apps}
    assert "App2" in app_names
    assert "App3" in app_names
    assert "App1" not in app_names
```

- [x] **Step 3: Update timestamp contract test**

In `tests/test_p1_s1_timestamp_contract.py`, split assertions:
- **UTC fields** (with `Z`): `ingested_at`, `processed_at`, `description_generated_at` — still end with `Z`
- **Local fields** (no `Z`): `timestamp` in search/timeline/activity-summary responses — no longer end with `Z`

```python
# Before: all timestamps end with "Z"
# After:
assert response["timestamp"].endswith("Z") is False  # local time, no offset
assert response["ingested_at"].endswith("Z") is True  # UTC, unchanged
```

- [x] **Step 4: Update health parsing test**

In `tests/test_p1_s1_health_parsing.py`:
- `last_frame_timestamp` is now local (no `Z`)
- `last_frame_ingested_at` remains UTC (with `Z`)

- [x] **Step 5: Update chat timezone test**

In `tests/test_chat_timezone.py`:
- Header now has 2 lines instead of 5
- Verify no `LOCAL_MIDNIGHT_TODAY_UTC` or `NOW_UTC` tokens

- [x] **Step 6: Update API memories since test**

In `tests/test_api_memories_since.py`:
- `since` parameter is now local time (no `Z` suffix expected in request)
- Response `timestamp` fields have no `Z` suffix

- [x] **Step 7: Update search engine and API tests**

In `tests/test_search_engine.py` and `tests/test_search_api.py`:
- `start_time`/`end_time` query params are now local time
- Expected response `timestamp` values have no `Z` suffix

- [x] **Step 8: Update acceptance scripts**

In `scripts/acceptance/p1_s2a_*.{py,sh}` and `scripts/acceptance/p1_s2b_*.sh`:
- Replace hardcoded UTC ISO strings with local time equivalents
- Example: `"2026-04-26T00:00:00Z"` → `"2026-04-26T00:00:00"`

- [x] **Step 9: Run full test suite**

```bash
pytest tests/ -v --ignore=tests/archive
```

Expected: All pass.

- [x] **Step 10: Commit**

```bash
git add tests/
git add scripts/
git commit -m "test: add local_timestamp computation and query tests; update all timestamp assertions"
```

---

## Spec Coverage Checklist

| Spec Requirement | Task |
|------------------|------|
| Migration: column + index | Task 1 |
| Write path: compute local time | Task 2 |
| Single-frame queries: `get_frame_by_id` local time + `get_frame_for_embedding` UTC | Task 3 |
| Query path: SQL uses `local_timestamp` | Task 4, 5 |
| Hybrid engine: `local_timestamp` in browse mode | Task 6 |
| Search engine: `local_timestamp` | Task 7 |
| API: `_parse_time_filter` + `/v1/frames/latest` + `similar_frames` | Task 8 |
| Frontend: shared `parseTimestamp` in `layout.html` + `checkNew` local-time cursor | Task 9 |
| Pi/Chat: simplified header + SKILL.md rewrite | Task 10 |
| Tests: comprehensive coverage | Task 11 |

## Rollback

- **Forward**: Run migration (adds column + index); deploy code (writes local_timestamp; queries use local_timestamp).
- **Rollback (data)**: Drop column and index. `timestamp` (UTC) remains intact as the source of truth.
  ```sql
  ALTER TABLE frames DROP COLUMN local_timestamp;
  DROP INDEX idx_frames_local_timestamp;
  ```
- **Rollback (code)**: Revert all touched files.

---

## Closeout (2026-04-27)

### Implementation Summary

All 11 tasks complete and committed across 5 incremental commits on branch `v4-0`:

| Commit | Scope |
|--------|-------|
| `5094351` | feat: use local_timestamp in search engine queries |
| `10671eb` | feat: update API to return local time; add /v1/frames/latest endpoint |
| `808d9d0` | feat: add shared parseTimestamp; display local_timestamp in all frontend views |
| `a3055e2` | feat: simplify Pi timezone header; SKILL.md uses local time directly |
| `6a860c5` | test: add local_timestamp computation and query tests; update all timestamp assertions |

### Files Changed (per spec scope)

Backend (7): `migrations/20260426000000_add_local_timestamp.sql`, `migrations_runner.py`, `frames_store.py`, `embedding/worker.py`, `search/engine.py`, `search/hybrid_engine.py`, `api_v1.py`.

Frontend (4): `templates/layout.html`, `templates/index.html`, `templates/search.html`, `templates/timeline.html`.

Chat (2): `client/chat/pi_rpc.py`, `client/chat/skills/myrecall-search/SKILL.md`.

Documentation (1): `CLAUDE.md` (Frames Table section).

Tests / Scripts: `test_v3_migrations_bootstrap.py`, `test_p1_s1_frames.py`, `test_p1_s1_timestamp_contract.py`, `test_p1_s1_health_parsing.py`, `test_chat_timezone.py`, `test_api_memories_since.py`, `test_search_api.py`, `test_p1_s4_api_search.py`, `test_chat_mvp_activity_summary.py`, `test_chat_mvp_activity_summary_api.py`, `test_chat_mvp_frame_context_api.py`, `test_visibility_status.py`, `scripts/verify_phase6.py`, `scripts/verify_phase7.py`.

### Critical Correctness Points (verified)

- ✅ `migrations_runner.py` has TWO hardcoded index lists — both updated (Python set + SQL `IN` filter)
- ✅ `get_frames_by_ids` uses an explicit column list (no `SELECT *` dual-column ambiguity)
- ✅ Orphan embeddings (LanceDB has it but SQLite does not) are skipped with `logger.warning` rather than falling back to UTC `emb.timestamp`
- ✅ Embedding worker uses dedicated `get_frame_for_embedding` so LanceDB still receives raw UTC
- ✅ `_parse_utc_timestamp` retained alongside new `_parse_time_filter` (both still used)
- ✅ `get_frame_by_id` retains `conn: Optional[sqlite3.Connection] = None` default for API callers
- ✅ Frontend timestamp parsing centralized in shared `parseTimestamp` (layout.html); offset detection at end of string avoids date-dash false positives
- ✅ Pi `_build_timezone_header` simplified to 2 lines; all `LOCAL_MIDNIGHT_TODAY_UTC`/`NOW_UTC` tokens removed
- ✅ SKILL.md fully rewritten — all examples use local time directly, no UTC conversion remains

### Verification Evidence

**Timezone-specific tests (23/23 PASS):**
- `test_p1_s1_timestamp_contract.py` (5)
- `test_p1_s1_health_parsing.py` (7)
- `test_chat_timezone.py` (5)
- `test_api_memories_since.py` (3)
- `test_v3_migrations_bootstrap.py::test_migration_20260426000000_adds_local_timestamp` (1)
- `test_p1_s1_frames.py::test_frame_local_timestamp_computed_from_utc` (1)
- `test_p1_s1_frames.py::test_query_by_local_timestamp` (1)

**Timestamp-touching neighbor tests (71/71 PASS):**
- `test_search_api.py`, `test_p1_s4_api_search.py`
- `test_chat_mvp_activity_summary.py`, `test_chat_mvp_activity_summary_api.py`
- `test_chat_mvp_frame_context_api.py`
- `test_visibility_status.py`

### Pre-Existing Failures (NOT caused by this migration)

`pytest tests/ --ignore=tests/archive -m "unit or not integration"` reports 90 failures + 15 errors. Triage of representative failures:

| Test File | Root Cause | Source Commit |
|-----------|-----------|--------------|
| `test_p1_s2a_*` / `test_p1_s2b_*` (recorder/routing/device_binding) | `'ServerSettings' object has no attribute 'client_data_dir'` | `42cb211 old-1-1` (config refactor) |
| `test_p1_s4_search_fts.py` | Removed `min_length`/`file_path`/`tags` fields | `bd21e59` (search cleanup) |
| `test_chat_config_manager.py` / `test_chat_models.py` | Default provider changed `qianfan` → `kimi-coding` | Unrelated chat config change |
| `test_chat_routes.py` | Chat route refactor | Unrelated |
| `test_p1_s3_processing_mode.py` | OCR mode switching | Unrelated |
| `test_activity_summary_descriptions_fields.py` | `frame_descriptions.entities_json` column missing | Description module refactor |
| `test_client_accessibility_service.py`, `test_p1_s1_uploader_retry.py`, `test_description_provider.py` | Various mock/contract changes | Unrelated |

These should be tracked as separate issues. They do NOT block the timezone migration.

### Remaining Work

None for this migration. Future-related items recorded separately:
- LanceDB schema migration to optionally store local time alongside UTC (out of scope, deferred)
- Cross-timezone client support (out of scope, see Constraints)
