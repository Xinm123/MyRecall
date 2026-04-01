# Activity Summary Endpoint Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement four design decisions for `/v1/activity-summary`: (1) remove `recent_texts`, (2) redesign description fields, (3) remove max_descriptions default limit, (4) adopt screenpipe-style app time calculation.

**Architecture:** Three database query methods in `frames_store.py` need updating, plus the API endpoint in `api_v1.py`. The `recent_texts` method is deleted entirely. App time calculation migrates from simple COUNT to LEAD() window function with 5-min threshold.

**Tech Stack:** Python (Flask), SQLite with FTS5, pytest

---

## File Impact Map

| File | Change |
|------|--------|
| `openrecall/server/database/frames_store.py` | Rewrite `get_activity_summary_apps()`, delete `get_activity_summary_recent_texts()`, update `get_recent_descriptions()` |
| `openrecall/server/api_v1.py` | Remove `recent_texts` from response, change `max_descriptions` param handling |
| `tests/test_chat_mvp_activity_summary.py` | Rewrite tests for new `get_activity_summary_apps()`, delete `recent_texts` tests |
| `tests/test_chat_mvp_activity_summary_api.py` | Update API-level tests for new response shape |
| `docs/v3/chat/api-fields-reference.md` | Rewrite GET /v1/activity-summary section |
| `openrecall/client/chat/skills/myrecall-search/SKILL.md` | Remove `recent_texts` reference, update token guidance |
| `scripts/verify_phase6.py` | Remove `recent_texts` checks |

---

## Task 1: Rewrite `get_activity_summary_apps()` — screenpipe time-delta method

**Files:**
- Modify: `openrecall/server/database/frames_store.py:1236-1283`

- [ ] **Step 1: Write the failing test — minutes calculation with LEAD() window function**

Create `tests/test_activity_summary_apps_screenpipe.py`:

```python
"""Tests for screenpipe-style app usage calculation.

Tests that minutes are calculated from actual timestamp gaps
(LEAD() window function) with a 5-minute threshold, plus first_seen/last_seen.
"""
import json
import sqlite3
from pathlib import Path
import pytest
from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_edge.db"
    conn = sqlite3.connect(str(db_path))
    migrations_dir = Path(__file__).resolve().parent.parent / (
        "openrecall/server/database/migrations"
    )
    run_migrations(conn, migrations_dir)
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db: Path) -> FramesStore:
    return FramesStore(db_path=temp_db)


def _claim_and_complete(store: FramesStore, capture_id: str, timestamp: str, app_name: str, text: str) -> int:
    frame_id, _ = store.claim_frame(
        capture_id=capture_id,
        metadata={"timestamp": timestamp, "app_name": app_name, "window_name": f"{app_name} Window"},
    )
    store.complete_accessibility_frame(
        frame_id=frame_id,
        text=text,
        browser_url=None,
        content_hash=None,
        simhash=None,
        accessibility_tree_json="[]",
        accessibility_text_content=text,
        accessibility_node_count=0,
        accessibility_truncated=False,
        elements=[],
    )
    return frame_id


class TestAppsScreenpipeMinutes:
    def test_apps_calculates_minutes_from_timestamp_gaps(self, store: FramesStore):
        """minutes should be SUM of gaps < 5 minutes, divided by 60.

        Setup: Safari frames at 10:00:00, 10:00:02, 10:00:04 (3 frames).
        LEAD() gives 2 real gaps:
          frame1→frame2: 2s, frame2→frame3: 2s, frame3→NULL: ignored
        Expected: 2 gaps * 2s = 4s / 60 = 0.067 minutes
        """
        _claim_and_complete(store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Hello")
        _claim_and_complete(store, "cap-2", "2026-03-20T10:00:02Z", "Safari", "World")
        _claim_and_complete(store, "cap-3", "2026-03-20T10:00:04Z", "Safari", "!")

        apps = store.get_activity_summary_apps(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert len(apps) == 1
        assert apps[0]["name"] == "Safari"
        assert apps[0]["frame_count"] == 3
        assert apps[0]["minutes"] == pytest.approx(0.1, rel=0.01)

    def test_apps_ignores_gaps_over_5_minutes(self, store: FramesStore):
        """Gaps >= 300 seconds should not count toward minutes.

        Setup: Frames at 10:00 and 10:06 (6 min gap).
        Expected: 0 minutes (gap excluded by threshold).
        """
        _claim_and_complete(store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Start")
        _claim_and_complete(store, "cap-2", "2026-03-20T10:06:00Z", "Safari", "Return")

        apps = store.get_activity_summary_apps(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert apps[0]["minutes"] == 0.0

    def test_apps_includes_first_seen_and_last_seen(self, store: FramesStore):
        """Apps should include first_seen and last_seen timestamps."""
        _claim_and_complete(store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "First")
        _claim_and_complete(store, "cap-2", "2026-03-20T10:30:00Z", "Safari", "Last")

        apps = store.get_activity_summary_apps(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert apps[0]["first_seen"] == "2026-03-20T10:00:00Z"
        assert apps[0]["last_seen"] == "2026-03-20T10:30:00Z"

    def test_apps_ordered_by_minutes_desc(self, store: FramesStore):
        """Apps should be ordered by minutes descending, not frame_count."""
        # Safari: 1 frame at 10:00
        _claim_and_complete(store, "saf-1", "2026-03-20T10:00:00Z", "Safari", "A")
        _claim_and_complete(store, "saf-2", "2026-03-20T10:00:01Z", "Safari", "B")
        _claim_and_complete(store, "saf-3", "2026-03-20T10:00:02Z", "Safari", "C")
        _claim_and_complete(store, "saf-4", "2026-03-20T10:00:03Z", "Safari", "D")
        _claim_and_complete(store, "saf-5", "2026-03-20T10:00:04Z", "Safari", "E")
        # Safari: 5 frames, 4 gaps of 1-2s = ~0.07 min

        # Mail: 1 frame (no gaps to accumulate minutes)
        _claim_and_complete(store, "mail-1", "2026-03-20T10:15:00Z", "Mail", "Mail")
        # Mail: 1 frame, 0 gaps = 0.0 min

        apps = store.get_activity_summary_apps(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert len(apps) == 2
        # Safari should be first (0.07 min > 0.0 min), even though it has more frames
        assert apps[0]["name"] == "Safari"
        assert apps[1]["name"] == "Mail"

    def test_apps_only_counts_completed_frames(self, store: FramesStore):
        """Pending frames should not appear in apps list."""
        _claim_and_complete(store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Done")
        store.claim_frame(capture_id="cap-2", metadata={"timestamp": "2026-03-20T10:01:00Z", "app_name": "Safari"})

        apps = store.get_activity_summary_apps(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert len(apps) == 1
        assert apps[0]["frame_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_activity_summary_apps_screenpipe.py -v`
Expected: FAIL (method signature / return fields don't match)

- [ ] **Step 3: Implement the new `get_activity_summary_apps()`**

Replace the method at line 1236 in `frames_store.py`:

```python
def get_activity_summary_apps(
    self,
    start_time: str,
    end_time: str,
    app_name: Optional[str] = None,
) -> list[dict]:
    """Return apps with accurate usage minutes from timestamp gaps.

    Uses SQLite LEAD() window function to calculate the actual time gap
    between consecutive frames per app. Only gaps < 300 seconds (5 min)
    count toward usage time, filtering out "away from computer" periods.

    Also returns first_seen and last_seen timestamps.

    Args:
        start_time: ISO8601 start timestamp
        end_time: ISO8601 end timestamp
        app_name: Optional filter by app name

    Returns:
        List of dicts with name, frame_count, minutes, first_seen, last_seen
    """
    apps = []
    try:
        with self._connect() as conn:
            # Use LEAD() to get next frame's timestamp per app, then compute gap
            # Build inner SQL conditionally to avoid fragile string replacement
            params: list = [start_time, end_time]

            if app_name:
                inner_sql = """
                    SELECT
                        app_name,
                        timestamp AS ts,
                        (JULIANDAY(LEAD(timestamp) OVER (
                            PARTITION BY app_name ORDER BY timestamp
                        )) - JULIANDAY(timestamp)) * 86400.0 AS gap_sec
                    FROM frames
                    WHERE status = 'completed'
                      AND app_name = ?
                      AND timestamp >= ?
                      AND timestamp <= ?
                """
                params = [app_name, start_time, end_time]
            else:
                inner_sql = """
                    SELECT
                        app_name,
                        timestamp AS ts,
                        (JULIANDAY(LEAD(timestamp) OVER (
                            PARTITION BY app_name ORDER BY timestamp
                        )) - JULIANDAY(timestamp)) * 86400.0 AS gap_sec
                    FROM frames
                    WHERE status = 'completed'
                      AND timestamp >= ?
                      AND timestamp <= ?
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_activity_summary_apps_screenpipe.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_activity_summary_apps_screenpipe.py openrecall/server/database/frames_store.py
git commit -m "feat(activity-summary): rewrite app time calc with screenpipe LEAD() method"
```

---

## Task 2: Rewrite `get_recent_descriptions()` — update fields, add timestamp

**Files:**
- Modify: `openrecall/server/database/frames_store.py:1797-1831`

- [ ] **Step 1: Write the failing test — new description fields**

Create `tests/test_activity_summary_descriptions_fields.py`:

```python
"""Tests for redesigned activity-summary description fields.

Verifies that descriptions include frame_id, timestamp, summary, intent, entities
(narrative removed) in the correct order.
"""
import json
import sqlite3
from pathlib import Path
import pytest
from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_edge.db"
    conn = sqlite3.connect(str(db_path))
    migrations_dir = Path(__file__).resolve().parent.parent / (
        "openrecall/server/database/migrations"
    )
    run_migrations(conn, migrations_dir)
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db: Path) -> FramesStore:
    return FramesStore(db_path=temp_db)


def _create_frame_and_description(
    store: FramesStore, capture_id: str, timestamp: str, app_name: str,
    narrative: str, entities: list, intent: str, summary: str,
) -> int:
    frame_id, _ = store.claim_frame(
        capture_id=capture_id,
        metadata={"timestamp": timestamp, "app_name": app_name, "window_name": f"{app_name} Window"},
    )
    store.complete_accessibility_frame(
        frame_id=frame_id,
        text="frame text",
        browser_url=None,
        content_hash=None,
        simhash=None,
        accessibility_tree_json="[]",
        accessibility_text_content="frame text",
        accessibility_node_count=0,
        accessibility_truncated=False,
        elements=[],
    )
    with store._connect() as conn:
        store.insert_description_task(conn, frame_id)
        conn.commit()
        # Simulate completed description
        conn.execute(
            """INSERT OR REPLACE INTO frame_descriptions
               (frame_id, narrative, entities_json, intent, summary)
               VALUES (?, ?, ?, ?, ?)""",
            (frame_id, narrative, json.dumps(entities), intent, summary),
        )
        conn.execute(
            "UPDATE frames SET description_status = 'completed' WHERE id = ?",
            (frame_id,),
        )
        conn.commit()
    return frame_id


class TestDescriptionsNewFields:
    def test_descriptions_includes_timestamp(self, store: FramesStore):
        """Each description entry must include timestamp from frames table."""
        _create_frame_and_description(
            store, "cap-1", "2026-03-20T10:30:00Z", "Safari",
            "Test narrative", [], "testing", "Testing",
        )

        with store._connect() as conn:
            descs = store.get_recent_descriptions(conn, "2026-03-20T09:00:00Z", "2026-03-20T11:00:00Z", 10)

        assert len(descs) == 1
        assert descs[0]["timestamp"] == "2026-03-20T10:30:00Z"

    def test_descriptions_excludes_narrative(self, store: FramesStore):
        """Descriptions should NOT include narrative field."""
        _create_frame_and_description(
            store, "cap-1", "2026-03-20T10:30:00Z", "Safari",
            "This is a very long narrative that should not appear",
            [], "testing", "Short summary",
        )

        with store._connect() as conn:
            descs = store.get_recent_descriptions(conn, "2026-03-20T09:00:00Z", "2026-03-20T11:00:00Z", 10)

        assert len(descs) == 1
        assert "narrative" not in descs[0]
        assert "summary" in descs[0]
        assert "intent" in descs[0]
        assert "entities" in descs[0]

    def test_descriptions_has_frame_id_timestamp_summary_intent_entities(self, store: FramesStore):
        """Description must have exactly these 5 fields."""
        _create_frame_and_description(
            store, "cap-1", "2026-03-20T10:30:00Z", "Safari",
            "Narrative text", ["Claude Code", "API"], "coding", "Coding in Claude",
        )

        with store._connect() as conn:
            descs = store.get_recent_descriptions(conn, "2026-03-20T09:00:00Z", "2026-03-20T11:00:00Z", 10)

        assert set(descs[0].keys()) == {"frame_id", "timestamp", "summary", "intent", "entities"}

    def test_descriptions_ordered_by_timestamp_desc(self, store: FramesStore):
        """Descriptions should be ordered by frame timestamp descending."""
        _create_frame_and_description(store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "N", [], "first", "First")
        _create_frame_and_description(store, "cap-2", "2026-03-20T10:30:00Z", "Safari", "N", [], "second", "Second")
        _create_frame_and_description(store, "cap-3", "2026-03-20T10:15:00Z", "Safari", "N", [], "middle", "Middle")

        with store._connect() as conn:
            descs = store.get_recent_descriptions(conn, "2026-03-20T09:00:00Z", "2026-03-20T11:00:00Z", 10)

        assert descs[0]["intent"] == "second"
        assert descs[1]["intent"] == "middle"
        assert descs[2]["intent"] == "first"

    def test_descriptions_respects_limit(self, store: FramesStore):
        """Descriptions should respect the limit parameter."""
        for i in range(5):
            _create_frame_and_description(
                store, f"cap-{i}", f"2026-03-20T10:{i:02d}:00Z", "Safari",
                "N", [], f"intent-{i}", f"Summary {i}",
            )

        with store._connect() as conn:
            descs = store.get_recent_descriptions(conn, "2026-03-20T09:00:00Z", "2026-03-20T11:00:00Z", 3)

        assert len(descs) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_activity_summary_descriptions_fields.py -v`
Expected: FAIL (key errors, missing fields)

- [ ] **Step 3: Implement the new `get_recent_descriptions()`**

Replace the method at line 1797 in `frames_store.py`:

```python
def get_recent_descriptions(
    self,
    conn: sqlite3.Connection,
    time_start: str,
    time_end: str,
    limit: int = 20,
) -> list[dict]:
    """Get recent frame descriptions within a time range.

    Returns simplified description entries: frame_id, timestamp, summary, intent, entities.
    The narrative field is excluded from activity-summary responses — detailed descriptions
    are available via GET /v1/frames/{id}/context.

    Args:
        conn: SQLite connection
        time_start: ISO8601 start timestamp
        time_end: ISO8601 end timestamp
        limit: Maximum number of descriptions to return (no default enforced here)

    Returns:
        List of dicts with frame_id, timestamp, summary, intent, entities
    """
    cursor = conn.execute(
        """
        SELECT fd.frame_id, f.timestamp, fd.summary, fd.intent, fd.entities_json
        FROM frame_descriptions fd
        JOIN frames f ON f.id = fd.frame_id
        WHERE f.timestamp BETWEEN ? AND ?
          AND fd.summary IS NOT NULL
        ORDER BY f.timestamp DESC
        LIMIT ?
        """,
        (time_start, time_end, limit),
    )
    rows = cursor.fetchall()
    result = []
    for r in rows:
        try:
            entities = json.loads(r[4])
        except (json.JSONDecodeError, TypeError):
            entities = []
        result.append({
            "frame_id": r[0],
            "timestamp": r[1],
            "summary": r[2],
            "intent": r[3],
            "entities": entities,
        })
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_activity_summary_descriptions_fields.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_activity_summary_descriptions_fields.py openrecall/server/database/frames_store.py
git commit -m "feat(activity-summary): simplify description fields, add timestamp"
```

---

## Task 3: Update `api_v1.py` — remove `recent_texts`, update param handling

**Files:**
- Modify: `openrecall/server/api_v1.py:1188-1261`

- [ ] **Step 1: Write the failing test — API response shape**

Add to `tests/test_chat_mvp_activity_summary_api.py`:

```python
def test_activity_summary_api_no_recent_texts_field(app_with_activity_summary_route):
    """API response must NOT contain the recent_texts field."""
    with patch('openrecall.server.api_v1._get_frames_store') as mock_get_store:
        mock_store = MagicMock()
        mock_store.get_activity_summary_apps.return_value = [
            {"name": "Safari", "frame_count": 5, "minutes": 0.2, "first_seen": "2026-03-20T10:00:00Z", "last_seen": "2026-03-20T10:05:00Z"}
        ]
        mock_store.get_activity_summary_total_frames.return_value = 5
        mock_store.get_activity_summary_time_range.return_value = {
            "start": "2026-03-20T09:00:00Z",
            "end": "2026-03-20T11:00:00Z",
        }
        mock_conn = MagicMock()
        mock_store._connect.return_value.__enter__.return_value = mock_conn
        mock_store.get_recent_descriptions.return_value = [
            {"frame_id": 1, "timestamp": "2026-03-20T10:00:00Z", "summary": "Test", "intent": "testing", "entities": []}
        ]
        mock_get_store.return_value = mock_store

        app = app_with_activity_summary_route
        with app.test_client() as client:
            resp = client.get(
                "/v1/activity-summary",
                query_string={
                    "start_time": "2026-03-20T09:00:00Z",
                    "end_time": "2026-03-20T11:00:00Z",
                },
            )
        data = resp.get_json()
        assert resp.status_code == 200
        assert "recent_texts" not in data, "API must not return recent_texts field"
        assert "descriptions" in data
        # Verify description fields match new schema (no narrative)
        desc = data["descriptions"][0]
        assert set(desc.keys()) == {"frame_id", "timestamp", "summary", "intent", "entities"}
        assert "narrative" not in desc
```

Also add a test that `max_descriptions` has no default (let the caller specify):

```python
def test_activity_summary_api_max_descriptions_none_default(app_with_activity_summary_route):
    """When max_descriptions is not specified, all available descriptions are returned."""
    with patch('openrecall.server.api_v1._get_frames_store') as mock_get_store:
        mock_store = MagicMock()
        mock_store.get_activity_summary_apps.return_value = []
        mock_store.get_activity_summary_total_frames.return_value = 0
        mock_store.get_activity_summary_time_range.return_value = None
        mock_conn = MagicMock()
        mock_store._connect.return_value.__enter__.return_value = mock_conn
        # Return 25 descriptions (no limit applied since param is None)
        mock_store.get_recent_descriptions.return_value = [
            {"frame_id": i, "timestamp": f"2026-03-20T10:{i%24:02d}:00Z", "summary": f"Summary {i}", "intent": f"intent-{i}", "entities": []}
            for i in range(25)
        ]
        mock_get_store.return_value = mock_store

        app = app_with_activity_summary_route
        with app.test_client() as client:
            resp = client.get(
                "/v1/activity-summary",
                query_string={
                    "start_time": "2026-03-20T09:00:00Z",
                    "end_time": "2026-03-20T11:00:00Z",
                },
            )
        data = resp.get_json()
        assert resp.status_code == 200
        # No default cap — limit=1000 when param is None, all 25 returned
        assert len(data["descriptions"]) == 25
        # Verify the store was called with limit=1000 (the default when param is None)
        mock_store.get_recent_descriptions.assert_called_once()
        call_args = mock_store.get_recent_descriptions.call_args
        assert call_args[0][2] == 1000, "limit should default to 1000 when max_descriptions not specified"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chat_mvp_activity_summary_api.py -v -k "no_recent_texts or none_default"`
Expected: FAIL (API still returns recent_texts, store still returns narrative)

- [ ] **Step 3: Update the `activity_summary()` endpoint**

Replace the endpoint at line 1188 in `api_v1.py`:

```python
@v1_bp.route("/activity-summary", methods=["GET"])
def activity_summary():
    """Return activity overview for chat agents.

    Query Parameters:
        start_time (str): Required. ISO8601 start timestamp.
        end_time (str): Required. ISO8601 end timestamp.
        app_name (str): Optional. Filter by app name.
        max_descriptions (int): Optional. Maximum descriptions to return.
            No default — all available descriptions within the time range
            are returned if not specified.

    Returns:
        JSON with apps, total_frames, time_range, audio_summary, descriptions.
        The recent_texts field has been removed — descriptions provide sufficient
        semantic context for activity overview.
    """
    request_id = str(uuid.uuid4())

    # Parse required parameters
    start_time = request.args.get("start_time", "").strip()
    end_time = request.args.get("end_time", "").strip()

    if not start_time or not end_time:
        return make_error_response(
            "start_time and end_time are required",
            "INVALID_PARAMS",
            400,
            request_id=request_id,
        )

    # Parse optional parameters
    app_name = request.args.get("app_name")
    if app_name:
        app_name = app_name.strip()
        if not app_name:
            app_name = None

    # Parse optional max_descriptions (no default — return all available)
    max_descriptions = request.args.get("max_descriptions", type=int)
    if max_descriptions is not None:
        max_descriptions = max(1, min(max_descriptions, 1000))

    # Get store instance
    store = _get_frames_store()

    # Call store methods
    apps = store.get_activity_summary_apps(
        start_time=start_time,
        end_time=end_time,
        app_name=app_name,
    )
    total_frames = store.get_activity_summary_total_frames(
        start_time=start_time,
        end_time=end_time,
        app_name=app_name,
    )
    time_range = store.get_activity_summary_time_range(
        start_time=start_time,
        end_time=end_time,
        app_name=app_name,
    )

    # Get descriptions within the time range
    with store._connect() as conn:
        descriptions = store.get_recent_descriptions(
            conn, start_time, end_time,
            limit=max_descriptions if max_descriptions is not None else 1000,
        )

    return jsonify({
        "apps": apps,
        "total_frames": total_frames,
        "time_range": time_range or {"start": start_time, "end": end_time},
        "audio_summary": {"segment_count": 0, "speakers": []},
        "descriptions": descriptions,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chat_mvp_activity_summary_api.py -v -k "no_recent_texts or none_default"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/api_v1.py tests/test_chat_mvp_activity_summary_api.py
git commit -m "feat(activity-summary): remove recent_texts, no max_descriptions default"
```

---

## Task 4: Delete `get_activity_summary_recent_texts()` and update tests

**Files:**
- Modify: `openrecall/server/database/frames_store.py` (delete lines 1285-1361)
- Modify: `tests/test_chat_mvp_activity_summary.py` (delete `TestActivitySummaryRecentTexts` class)
- Modify: `tests/test_chat_mvp_activity_summary_api.py` (remove recent_texts assertions)
- Modify: `scripts/verify_phase6.py` (remove recent_texts checks)

- [ ] **Step 1: Delete `get_activity_summary_recent_texts()` from frames_store.py**

Delete the entire method at lines 1285-1361. The method is no longer needed since the API no longer returns `recent_texts`.

After deletion, verify the file still has valid syntax:

Run: `python -c "import openrecall.server.database.frames_store"`
Expected: No output (no import error)

- [ ] **Step 2: Delete `TestActivitySummaryRecentTexts` class from test file**

Delete the entire `TestActivitySummaryRecentTexts` class (lines 203-379) from `tests/test_chat_mvp_activity_summary.py`.

- [ ] **Step 3: Update `test_chat_mvp_activity_summary_api.py`**

Find and remove all assertions that check for `recent_texts` in API responses. Search for `"recent_texts"` in the test file and remove those assertions.

Run: `pytest tests/test_chat_mvp_activity_summary_api.py -v`
Expected: PASS (all remaining tests pass)

- [ ] **Step 4: Update `scripts/verify_phase6.py`**

Search for `recent_texts` in `scripts/verify_phase6.py` and remove any checks or references.

- [ ] **Step 5: Run the full activity-summary test suite**

Run: `pytest tests/test_chat_mvp_activity_summary.py tests/test_chat_mvp_activity_summary_api.py tests/test_activity_summary_apps_screenpipe.py tests/test_activity_summary_descriptions_fields.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add openrecall/server/database/frames_store.py tests/test_chat_mvp_activity_summary.py tests/test_chat_mvp_activity_summary_api.py scripts/verify_phase6.py
git commit -m "refactor(activity-summary): remove recent_texts method and tests"
```

---

## Task 5: Update documentation

**Files:**
- Modify: `docs/v3/chat/api-fields-reference.md`
- Modify: `openrecall/client/chat/skills/myrecall-search/SKILL.md`

- [ ] **Step 1: Update `docs/v3/chat/api-fields-reference.md`**

Rewrite the **GET /v1/activity-summary** section. Key changes:

- Remove `recent_texts` from response fields table
- Update `apps[].minutes` description: describe screenpipe time-delta method
- Add `apps[].first_seen` and `apps[].last_seen` fields
- Change `apps` sort order: from `frame_count DESC` to `minutes DESC`
- Update `descriptions` fields: remove `narrative`, add `timestamp`, reorder to `frame_id, timestamp, summary, intent, entities`
- Remove default value for `max_descriptions`
- Update example JSON response
- Update the "Known Gaps vs screenpipe" table: first_seen/last_seen now implemented

- [ ] **Step 2: Update `openrecall/client/chat/skills/myrecall-search/SKILL.md`**

- Remove the section referencing `recent_texts`
- Update token guidance: remove 200-500 token target constraint, add rough estimate for new response size
- Update any example curl commands that reference `recent_texts`

- [ ] **Step 3: Update `docs/v3/chat/mvp.md`**

Search for any activity-summary references and update to match the new schema.

- [ ] **Step 4: Commit**

```bash
git add docs/v3/chat/api-fields-reference.md openrecall/client/chat/skills/myrecall-search/SKILL.md docs/v3/chat/mvp.md
git commit -m "docs(activity-summary): update API reference and SKILL docs"
```

---

## Verification Checklist

After all tasks complete, run:

```bash
# Full test suite
pytest tests/test_chat_mvp_activity_summary.py tests/test_chat_mvp_activity_summary_api.py tests/test_activity_summary_apps_screenpipe.py tests/test_activity_summary_descriptions_fields.py -v

# Syntax check
python -c "import openrecall.server.api_v1; import openrecall.server.database.frames_store"

# API smoke test (requires running server)
curl -s "http://localhost:8083/v1/activity-summary?start_time=2026-03-20T09:00:00Z&end_time=2026-03-20T11:00:00Z" | python -m json.tool | head -60
```

Expected: All tests pass, no syntax errors, API returns valid JSON matching new schema (apps with first_seen/last_seen, no recent_texts, descriptions without narrative).
