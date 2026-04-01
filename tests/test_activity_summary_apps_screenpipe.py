"""Tests for screenpipe-style app usage calculation.

Tests that minutes are calculated from actual timestamp gaps
(LEAD() window function) with a 5-minute threshold, plus first_seen/last_seen.
"""
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
          frame1->frame2: 2s, frame2->frame3: 2s, frame3->NULL: ignored
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
        # Safari: 5 frames with small gaps (accumulates minutes)
        _claim_and_complete(store, "saf-1", "2026-03-20T10:00:00Z", "Safari", "A")
        _claim_and_complete(store, "saf-2", "2026-03-20T10:00:01Z", "Safari", "B")
        _claim_and_complete(store, "saf-3", "2026-03-20T10:00:02Z", "Safari", "C")
        _claim_and_complete(store, "saf-4", "2026-03-20T10:00:03Z", "Safari", "D")
        _claim_and_complete(store, "saf-5", "2026-03-20T10:00:04Z", "Safari", "E")
        # Safari: 5 frames, 4 gaps of 1-2s each = ~0.067 min

        # Mail: 1 frame (no gaps to accumulate minutes = 0.0 min)
        _claim_and_complete(store, "mail-1", "2026-03-20T10:15:00Z", "Mail", "Mail")

        apps = store.get_activity_summary_apps(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert len(apps) == 2
        # Safari should be first (0.067 min > 0.0 min)
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

    def test_apps_filters_by_app_name(self, store: FramesStore):
        """Apps should filter correctly when app_name is specified."""
        _claim_and_complete(store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "SafariPage")
        _claim_and_complete(store, "cap-2", "2026-03-20T10:00:01Z", "Safari", "SafariPage2")
        _claim_and_complete(store, "cap-3", "2026-03-20T10:15:00Z", "Mail", "MailApp")

        apps = store.get_activity_summary_apps(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
            app_name="Safari",
        )

        assert len(apps) == 1
        assert apps[0]["name"] == "Safari"
        assert apps[0]["frame_count"] == 2

    def test_apps_single_frame_zero_minutes(self, store: FramesStore):
        """A single frame has no gaps, so minutes should be 0.0."""
        _claim_and_complete(store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Solo")

        apps = store.get_activity_summary_apps(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert apps[0]["minutes"] == 0.0
        assert apps[0]["frame_count"] == 1
        assert apps[0]["first_seen"] == apps[0]["last_seen"]
