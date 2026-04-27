"""Tests for activity summary query helpers.

Phase 6 of Chat MVP implementation.

These tests verify the query methods for the /v1/activity-summary endpoint.
SSOT: docs/v3/chat/mvp.md
"""

import json
import sqlite3
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore, _utc_to_local_timestamp
from openrecall.server.database.migrations_runner import run_migrations


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database with v3 schema."""
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
    """Create a FramesStore with temporary database."""
    return FramesStore(db_path=temp_db)


def _create_completed_frame_with_accessibility(
    store: FramesStore,
    capture_id: str,
    timestamp: str,
    app_name: str,
    text: str,
    elements: list[dict] | None = None,
    browser_url: str | None = None,
) -> int:
    """Helper to create a completed accessibility-canonical frame."""
    frame_id, _ = store.claim_frame(
        capture_id=capture_id,
        metadata={
            "timestamp": timestamp,
            "app_name": app_name,
            "window_name": f"{app_name} Window",
            "browser_url": browser_url,
        },
    )

    tree_json = json.dumps(elements or [])
    store.complete_accessibility_frame(
        frame_id=frame_id,
        text=text,
        browser_url=browser_url,
        content_hash=None,
        simhash=None,
        accessibility_tree_json=tree_json,
        accessibility_text_content=text,
        accessibility_node_count=len(elements or []),
        accessibility_truncated=False,
        elements=elements or [],
    )
    return frame_id


class TestActivitySummaryApps:
    """Tests for get_activity_summary_apps query helper."""

    def test_activity_summary_apps_counts_completed_frames(
        self, store: FramesStore
    ):
        """Apps summary should only count completed frames."""
        # Create completed frames
        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Hello"
        )
        _create_completed_frame_with_accessibility(
            store, "cap-2", "2026-03-20T10:01:00Z", "Safari", "World"
        )

        # Create pending frame (should not count)
        store.claim_frame(
            capture_id="cap-3",
            metadata={
                "timestamp": "2026-03-20T10:02:00Z",
                "app_name": "Safari",
            },
        )

        apps = store.get_activity_summary_apps(
            start_time=_utc_to_local_timestamp("2026-03-20T09:00:00Z"),
            end_time=_utc_to_local_timestamp("2026-03-20T11:00:00Z"),
        )

        assert len(apps) == 1
        assert apps[0]["name"] == "Safari"
        assert apps[0]["frame_count"] == 2

    def test_activity_summary_apps_filters_by_time_range(
        self, store: FramesStore
    ):
        """Apps summary should filter by time range."""
        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T09:30:00Z", "Safari", "Early"
        )
        _create_completed_frame_with_accessibility(
            store, "cap-2", "2026-03-20T10:00:00Z", "Safari", "Mid"
        )
        _create_completed_frame_with_accessibility(
            store, "cap-3", "2026-03-20T11:30:00Z", "Safari", "Late"
        )

        # Query 09:00 to 11:00 window (local time = UTC+8)
        apps = store.get_activity_summary_apps(
            start_time=_utc_to_local_timestamp("2026-03-20T09:00:00Z"),
            end_time=_utc_to_local_timestamp("2026-03-20T11:00:00Z"),
        )

        assert apps[0]["frame_count"] == 2  # Only cap-1 and cap-2

    def test_activity_summary_apps_filters_by_app_name(
        self, store: FramesStore
    ):
        """Apps summary should optionally filter by app_name."""
        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Web"
        )
        _create_completed_frame_with_accessibility(
            store, "cap-2", "2026-03-20T10:01:00Z", "Mail", "Email"
        )

        apps = store.get_activity_summary_apps(
            start_time=_utc_to_local_timestamp("2026-03-20T09:00:00Z"),
            end_time=_utc_to_local_timestamp("2026-03-20T11:00:00Z"),
            app_name="Safari",
        )

        assert len(apps) == 1
        assert apps[0]["name"] == "Safari"
        assert apps[0]["frame_count"] == 1


class TestActivitySummaryTotalFrames:
    """Tests for get_activity_summary_total_frames query helper."""

    def test_activity_summary_total_frames_counts_completed(
        self, store: FramesStore
    ):
        """Total frames should only count completed frames."""
        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Hello"
        )
        _create_completed_frame_with_accessibility(
            store, "cap-2", "2026-03-20T10:01:00Z", "Safari", "World"
        )

        # Pending frame
        store.claim_frame(
            capture_id="cap-3",
            metadata={"timestamp": "2026-03-20T10:02:00Z", "app_name": "Safari"},
        )

        total = store.get_activity_summary_total_frames(
            start_time=_utc_to_local_timestamp("2026-03-20T09:00:00Z"),
            end_time=_utc_to_local_timestamp("2026-03-20T11:00:00Z"),
        )

        assert total == 2

    def test_activity_summary_total_frames_filters_by_time_range(
        self, store: FramesStore
    ):
        """Total frames should filter by time range."""
        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T09:30:00Z", "Safari", "Early"
        )
        _create_completed_frame_with_accessibility(
            store, "cap-2", "2026-03-20T10:00:00Z", "Safari", "Mid"
        )
        _create_completed_frame_with_accessibility(
            store, "cap-3", "2026-03-20T11:30:00Z", "Safari", "Late"
        )

        # Query 09:00 to 11:00 window (local time = UTC+8)
        total = store.get_activity_summary_total_frames(
            start_time=_utc_to_local_timestamp("2026-03-20T09:00:00Z"),
            end_time=_utc_to_local_timestamp("2026-03-20T11:00:00Z"),
        )

        assert total == 2  # Only cap-1 and cap-2

    def test_activity_summary_total_frames_filters_by_app_name(
        self, store: FramesStore
    ):
        """Total frames should optionally filter by app_name."""
        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Web"
        )
        _create_completed_frame_with_accessibility(
            store, "cap-2", "2026-03-20T10:01:00Z", "Mail", "Email"
        )

        total = store.get_activity_summary_total_frames(
            start_time=_utc_to_local_timestamp("2026-03-20T09:00:00Z"),
            end_time=_utc_to_local_timestamp("2026-03-20T11:00:00Z"),
            app_name="Safari",
        )

        assert total == 1


class TestActivitySummaryTimeRange:
    """Tests for activity summary time_range helper."""

    def test_activity_summary_time_range_returns_bounds(
        self, store: FramesStore
    ):
        """time_range should return min/max timestamps of completed frames."""
        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "First"
        )
        _create_completed_frame_with_accessibility(
            store, "cap-2", "2026-03-20T10:30:00Z", "Safari", "Last"
        )

        time_range = store.get_activity_summary_time_range(
            start_time=_utc_to_local_timestamp("2026-03-20T09:00:00Z"),
            end_time=_utc_to_local_timestamp("2026-03-20T11:00:00Z"),
        )

        assert time_range is not None
        # Returns local_timestamp (UTC+8)
        assert time_range["start"] == _utc_to_local_timestamp("2026-03-20T10:00:00Z")
        assert time_range["end"] == _utc_to_local_timestamp("2026-03-20T10:30:00Z")

    def test_activity_summary_time_range_returns_none_when_no_frames(
        self, store: FramesStore
    ):
        """time_range should return None when no frames match."""
        time_range = store.get_activity_summary_time_range(
            start_time=_utc_to_local_timestamp("2026-03-20T09:00:00Z"),
            end_time=_utc_to_local_timestamp("2026-03-20T11:00:00Z"),
        )

        assert time_range is None
