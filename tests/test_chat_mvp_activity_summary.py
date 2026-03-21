"""Tests for activity summary query helpers.

Phase 6 of Chat MVP implementation.

These tests verify the query methods for the /v1/activity-summary endpoint.
SSOT: docs/v3/chat/mvp.md
"""

import json
import sqlite3
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore
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
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
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

        # Query 09:00 to 11:00 window
        apps = store.get_activity_summary_apps(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
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
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
            app_name="Safari",
        )

        assert len(apps) == 1
        assert apps[0]["name"] == "Safari"
        assert apps[0]["frame_count"] == 1

    def test_activity_summary_apps_approximates_minutes(
        self, store: FramesStore
    ):
        """Apps minutes should approximate frame_count * 2 / 60."""
        # Create 30 frames for Safari
        for i in range(30):
            _create_completed_frame_with_accessibility(
                store,
                f"cap-{i}",
                f"2026-03-20T10:{i:02d}:00Z",
                "Safari",
                f"Text {i}",
            )

        apps = store.get_activity_summary_apps(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        # minutes = frame_count * 2 / 60 = 30 * 2 / 60 = 1.0
        assert apps[0]["name"] == "Safari"
        assert apps[0]["frame_count"] == 30
        assert apps[0]["minutes"] == pytest.approx(1.0, rel=0.01)

    def test_activity_summary_apps_orders_by_frame_count_desc(
        self, store: FramesStore
    ):
        """Apps should be ordered by frame_count descending."""
        # Safari: 3 frames
        for i in range(3):
            _create_completed_frame_with_accessibility(
                store, f"safari-{i}", f"2026-03-20T10:0{i}:00Z", "Safari", f"Web {i}"
            )

        # Mail: 5 frames
        for i in range(5):
            _create_completed_frame_with_accessibility(
                store, f"mail-{i}", f"2026-03-20T10:1{i}:00Z", "Mail", f"Email {i}"
            )

        apps = store.get_activity_summary_apps(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert len(apps) == 2
        # Mail should be first (5 frames > 3 frames)
        assert apps[0]["name"] == "Mail"
        assert apps[0]["frame_count"] == 5
        assert apps[1]["name"] == "Safari"
        assert apps[1]["frame_count"] == 3


class TestActivitySummaryRecentTexts:
    """Tests for get_activity_summary_recent_texts query helper."""

    def test_activity_summary_recent_texts_uses_text_like_roles(
        self, store: FramesStore
    ):
        """recent_texts should only include AXStaticText, line, paragraph roles."""
        elements = [
            {"role": "AXStaticText", "text": "Static text content", "depth": 0},
            {"role": "AXButton", "text": "Button text", "depth": 0},  # Not text-like
            {"role": "line", "text": "Line content", "depth": 0},
            {"role": "paragraph", "text": "Paragraph content", "depth": 0},
            {"role": "AXLink", "text": "Link text", "depth": 0},  # Not text-like
        ]
        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "All text", elements
        )

        texts = store.get_activity_summary_recent_texts(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        # Should only have 3 entries (AXStaticText, line, paragraph)
        assert len(texts) == 3
        roles = {t["role"] for t in texts}
        assert roles == {"AXStaticText", "line", "paragraph"}

    def test_activity_summary_recent_texts_joins_frames(
        self, store: FramesStore
    ):
        """recent_texts should include frame_id, timestamp, app_name from frames."""
        elements = [
            {"role": "AXStaticText", "text": "Hello World", "depth": 0},
        ]
        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Hello World", elements
        )

        texts = store.get_activity_summary_recent_texts(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert len(texts) == 1
        assert texts[0]["text"] == "Hello World"
        assert texts[0]["app_name"] == "Safari"
        assert texts[0]["frame_id"] is not None
        assert texts[0]["timestamp"] == "2026-03-20T10:00:00Z"

    def test_activity_summary_recent_texts_orders_by_timestamp_desc(
        self, store: FramesStore
    ):
        """recent_texts should be ordered by frame timestamp descending."""
        elements = [{"role": "AXStaticText", "text": "Text", "depth": 0}]

        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "First", elements
        )
        _create_completed_frame_with_accessibility(
            store, "cap-2", "2026-03-20T10:30:00Z", "Safari", "Second", elements
        )
        _create_completed_frame_with_accessibility(
            store, "cap-3", "2026-03-20T10:15:00Z", "Safari", "Middle", elements
        )

        texts = store.get_activity_summary_recent_texts(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        # Should be ordered: Second (10:30), Middle (10:15), First (10:00)
        assert len(texts) == 3
        assert texts[0]["timestamp"] == "2026-03-20T10:30:00Z"
        assert texts[1]["timestamp"] == "2026-03-20T10:15:00Z"
        assert texts[2]["timestamp"] == "2026-03-20T10:00:00Z"

    def test_activity_summary_recent_texts_respects_limit(
        self, store: FramesStore
    ):
        """recent_texts should respect the limit parameter."""
        elements = [{"role": "AXStaticText", "text": "Text", "depth": 0}]

        for i in range(20):
            _create_completed_frame_with_accessibility(
                store, f"cap-{i}", f"2026-03-20T10:{i:02d}:00Z", "Safari", f"Text {i}", elements
            )

        texts = store.get_activity_summary_recent_texts(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
            limit=5,
        )

        assert len(texts) == 5

    def test_activity_summary_recent_texts_filters_by_app_name(
        self, store: FramesStore
    ):
        """recent_texts should optionally filter by app_name."""
        elements = [{"role": "AXStaticText", "text": "Content", "depth": 0}]

        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Web", elements
        )
        _create_completed_frame_with_accessibility(
            store, "cap-2", "2026-03-20T10:01:00Z", "Mail", "Email", elements
        )

        texts = store.get_activity_summary_recent_texts(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
            app_name="Safari",
        )

        assert len(texts) == 1
        assert texts[0]["app_name"] == "Safari"

    def test_activity_summary_recent_texts_only_completed_frames(
        self, store: FramesStore
    ):
        """recent_texts should only include elements from completed frames."""
        # Create a completed frame
        elements = [{"role": "AXStaticText", "text": "Completed text", "depth": 0}]
        _create_completed_frame_with_accessibility(
            store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Completed", elements
        )

        # Create a pending frame (should not appear)
        store.claim_frame(
            capture_id="cap-2",
            metadata={
                "timestamp": "2026-03-20T10:01:00Z",
                "app_name": "Safari",
            },
        )

        texts = store.get_activity_summary_recent_texts(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert len(texts) == 1
        assert texts[0]["text"] == "Completed text"


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
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
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

        # Query 09:00 to 11:00 window
        total = store.get_activity_summary_total_frames(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
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
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
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
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert time_range is not None
        assert time_range["start"] == "2026-03-20T10:00:00Z"
        assert time_range["end"] == "2026-03-20T10:30:00Z"

    def test_activity_summary_time_range_returns_none_when_no_frames(
        self, store: FramesStore
    ):
        """time_range should return None when no frames match."""
        time_range = store.get_activity_summary_time_range(
            start_time="2026-03-20T09:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )

        assert time_range is None
