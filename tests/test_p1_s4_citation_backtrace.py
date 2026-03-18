"""Tests for Citation Backtrace — P1-S4 Section 3.

Tests verify search result → frame/timeline click-through:
- frame_id resolves correctly via FramesStore.get_frame()
- timestamp matches between search result and frame record
- Success rate >= 95%

Per tasks.md §3 and specs/fts-search/spec.md.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.search.engine import SearchEngine


pytestmark = [pytest.mark.integration, pytest.mark.e2e]


@pytest.fixture
def temp_db_with_frames():
    """Create a temporary database with test frames and OCR text."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "edge.db"
        frames_dir = Path(tmpdir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create schema matching production
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capture_id TEXT NOT NULL UNIQUE,
                timestamp TEXT NOT NULL,
                app_name TEXT DEFAULT NULL,
                window_name TEXT DEFAULT NULL,
                browser_url TEXT DEFAULT NULL,
                focused BOOLEAN DEFAULT NULL,
                device_name TEXT NOT NULL DEFAULT 'monitor_0',
                snapshot_path TEXT DEFAULT NULL,
                status TEXT NOT NULL DEFAULT 'completed',
                text_source TEXT DEFAULT NULL,
                ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                image_size_bytes INTEGER DEFAULT NULL,
                error_message TEXT DEFAULT NULL,
                last_known_app TEXT DEFAULT NULL,
                last_known_window TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS ocr_text (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frame_id INTEGER NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                text_length INTEGER DEFAULT 0,
                ocr_engine TEXT,
                app_name TEXT DEFAULT NULL,
                window_name TEXT DEFAULT NULL,
                FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS frames_fts USING fts5(
                app_name, window_name, browser_url, focused, accessibility_text,
                id UNINDEXED, tokenize='unicode61'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(
                text, app_name, window_name, frame_id UNINDEXED, tokenize='unicode61'
            );

            CREATE INDEX IF NOT EXISTS idx_frames_timestamp ON frames(timestamp);
            CREATE INDEX IF NOT EXISTS idx_ocr_text_frame_id ON ocr_text(frame_id);

            -- FTS triggers
            CREATE TRIGGER IF NOT EXISTS frames_ai AFTER INSERT ON frames BEGIN
                INSERT INTO frames_fts(id, app_name, window_name, browser_url, focused, accessibility_text)
                VALUES (NEW.id, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''),
                        COALESCE(NEW.browser_url, ''), COALESCE(NEW.focused, 0), '');
            END;

            CREATE TRIGGER IF NOT EXISTS ocr_text_ai AFTER INSERT ON ocr_text
            WHEN NEW.text IS NOT NULL AND NEW.text != '' BEGIN
                INSERT INTO ocr_text_fts(frame_id, text, app_name, window_name)
                VALUES (NEW.frame_id, NEW.text, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''));
            END;
        """)

        # Insert test frames with OCR - diverse content for citation testing
        test_frames = [
            (
                1,
                "capture-001",
                "2026-03-18T10:00:00Z",
                "Safari",
                "Web Browser",
                None,
                True,
                "Hello world from Safari browser",
            ),
            (
                2,
                "capture-002",
                "2026-03-18T11:00:00Z",
                "VSCode",
                "main.py - MyProject",
                None,
                True,
                "def hello(): pass # Python code here",
            ),
            (
                3,
                "capture-003",
                "2026-03-18T12:00:00Z",
                "Terminal",
                "bash - git",
                None,
                False,
                "git status && git commit -m 'update'",
            ),
            (
                4,
                "capture-004",
                "2026-03-18T13:00:00Z",
                "Safari",
                "Google Search",
                None,
                True,
                "search query hello world results",
            ),
            (
                5,
                "capture-005",
                "2026-03-18T14:00:00Z",
                "Slack",
                "#general - Team",
                None,
                True,
                "meeting at 3pm hello team members",
            ),
            (
                6,
                "capture-006",
                "2026-03-18T15:00:00Z",
                "Mail",
                "Inbox - Work",
                None,
                True,
                "Important email about project deadline",
            ),
            (
                7,
                "capture-007",
                "2026-03-18T16:00:00Z",
                "Notes",
                "Meeting Notes",
                None,
                True,
                "Discussion points from today's meeting",
            ),
            (
                8,
                "capture-008",
                "2026-03-18T17:00:00Z",
                "Calendar",
                "Weekly Schedule",
                None,
                True,
                "Appointments for the week ahead",
            ),
            (
                9,
                "capture-009",
                "2026-03-18T18:00:00Z",
                "Finder",
                "Documents",
                None,
                False,
                "File browser showing project files",
            ),
            (
                10,
                "capture-010",
                "2026-03-18T19:00:00Z",
                "Spotify",
                "Now Playing",
                None,
                True,
                "Spotify music player showing playlist",
            ),
        ]

        for (
            frame_id,
            capture_id,
            ts,
            app,
            window,
            url,
            focused,
            ocr_text,
        ) in test_frames:
            conn.execute(
                """INSERT INTO frames (id, capture_id, timestamp, app_name, window_name, browser_url, focused, status, text_source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', 'ocr')""",
                (frame_id, capture_id, ts, app, window, url, focused),
            )
            conn.execute(
                """INSERT INTO ocr_text (frame_id, text, text_length, ocr_engine)
                   VALUES (?, ?, ?, 'test')""",
                (frame_id, ocr_text, len(ocr_text)),
            )

        conn.commit()
        conn.close()

        yield db_path, frames_dir


class TestCitationBacktrace:
    """Tests for search result to frame citation backtrace."""

    def test_frame_id_resolves_correctly(self, temp_db_with_frames):
        """Each search result's frame_id resolves to a valid frame."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        store = FramesStore(db_path=db_path)

        results, total = engine.search(q="hello", limit=20, offset=0)

        assert total >= 1, "Expected at least one search result"

        success_count = 0
        for r in results:
            frame_id = r.get("frame_id")
            assert frame_id is not None, "frame_id should not be None"

            frame = store.get_frame(frame_id)
            if frame is not None:
                success_count += 1

        success_rate = success_count / len(results) if results else 0
        assert success_rate >= 0.95, f"Success rate {success_rate:.2%} < 95%"

    def test_timestamp_matches_frame_record(self, temp_db_with_frames):
        """Search result timestamp matches the frame's timestamp."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        store = FramesStore(db_path=db_path)

        results, total = engine.search(q="hello", limit=20, offset=0)

        assert total >= 1, "Expected at least one search result"

        success_count = 0
        for r in results:
            frame_id = r.get("frame_id")
            search_timestamp = r.get("timestamp")

            if frame_id is None or search_timestamp is None:
                continue

            frame = store.get_frame(frame_id)
            if frame is not None:
                # Compare timestamps (both should be ISO8601 strings)
                if frame.timestamp == search_timestamp:
                    success_count += 1

        success_rate = success_count / len(results) if results else 0
        assert success_rate >= 0.95, f"Timestamp match rate {success_rate:.2%} < 95%"

    def test_full_citation_backtrace_flow(self, temp_db_with_frames):
        """Complete citation backtrace: search → frame_id → frame record."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        store = FramesStore(db_path=db_path)

        # Test multiple queries to ensure robustness
        queries = ["hello", "meeting", "project", "Safari", ""]
        total_checks = 0
        successful_checks = 0

        for query in queries:
            results, total = engine.search(q=query, limit=20, offset=0)

            for r in results:
                total_checks += 1
                frame_id = r.get("frame_id")
                search_timestamp = r.get("timestamp")
                search_app_name = r.get("app_name")

                # Step 1: Verify frame_id is present
                if frame_id is None:
                    continue

                # Step 2: Fetch frame by ID
                frame = store.get_frame(frame_id)
                if frame is None:
                    continue

                # Step 3: Verify timestamp matches
                if frame.timestamp != search_timestamp:
                    continue

                # Step 4: Verify app_name matches (if present in search result)
                if search_app_name is not None and frame.app_name != search_app_name:
                    continue

                successful_checks += 1

        success_rate = successful_checks / total_checks if total_checks > 0 else 0
        assert success_rate >= 0.95, (
            f"Full backtrace success rate {success_rate:.2%} < 95%"
        )

    def test_browse_mode_citation_backtrace(self, temp_db_with_frames):
        """Citation backtrace works in browse mode (empty query)."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        store = FramesStore(db_path=db_path)

        # Browse mode: no query, returns all frames
        results, total = engine.search(q="", limit=20, offset=0)

        assert total == 10, f"Expected 10 frames, got {total}"

        success_count = 0
        for r in results:
            frame_id = r.get("frame_id")
            search_timestamp = r.get("timestamp")

            frame = store.get_frame(frame_id)
            if frame is not None and frame.timestamp == search_timestamp:
                success_count += 1

        success_rate = success_count / len(results) if results else 0
        assert success_rate >= 0.95, (
            f"Browse mode success rate {success_rate:.2%} < 95%"
        )

    def test_citation_backtrace_with_filters(self, temp_db_with_frames):
        """Citation backtrace works with metadata filters."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        store = FramesStore(db_path=db_path)

        # Search with app_name filter
        results, total = engine.search(q="", limit=20, offset=0, app_name="Safari")

        assert total == 2, f"Expected 2 Safari frames, got {total}"

        for r in results:
            frame_id = r.get("frame_id")
            search_timestamp = r.get("timestamp")

            frame = store.get_frame(frame_id)
            assert frame is not None, f"Frame {frame_id} not found"
            assert frame.timestamp == search_timestamp, "Timestamp mismatch"
            assert frame.app_name == "Safari", (
                f"Expected app_name='Safari', got '{frame.app_name}'"
            )

    def test_nonexistent_frame_id_returns_none(self, temp_db_with_frames):
        """Requesting a non-existent frame_id returns None."""
        db_path, _ = temp_db_with_frames
        store = FramesStore(db_path=db_path)

        # Use a frame_id that doesn't exist
        frame = store.get_frame(99999)
        assert frame is None, "Expected None for non-existent frame_id"

    def test_citation_success_rate_metric(self, temp_db_with_frames):
        """Calculate and verify citation success rate metric."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        store = FramesStore(db_path=db_path)

        # Run comprehensive search
        results, total = engine.search(q="", limit=100, offset=0)

        # Calculate success metrics
        total_results = len(results)
        frames_found = 0
        timestamps_matched = 0
        app_names_matched = 0

        for r in results:
            frame_id = r.get("frame_id")
            search_ts = r.get("timestamp")
            search_app = r.get("app_name")

            frame = store.get_frame(frame_id)
            if frame is None:
                continue

            frames_found += 1
            if frame.timestamp == search_ts:
                timestamps_matched += 1
            if frame.app_name == search_app:
                app_names_matched += 1

        # Verify all metrics >= 95%
        frame_resolution_rate = frames_found / total_results if total_results else 0
        timestamp_match_rate = (
            timestamps_matched / total_results if total_results else 0
        )
        app_name_match_rate = app_names_matched / total_results if total_results else 0

        assert frame_resolution_rate >= 0.95, (
            f"Frame resolution rate {frame_resolution_rate:.2%} < 95%"
        )
        assert timestamp_match_rate >= 0.95, (
            f"Timestamp match rate {timestamp_match_rate:.2%} < 95%"
        )
        assert app_name_match_rate >= 0.95, (
            f"App name match rate {app_name_match_rate:.2%} < 95%"
        )


class TestCitationBacktraceEdgeCases:
    """Edge case tests for citation backtrace."""

    def test_single_result_citation(self, temp_db_with_frames):
        """Citation backtrace works with a single search result."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        store = FramesStore(db_path=db_path)

        # Search for unique term
        results, total = engine.search(q="Spotify", limit=20, offset=0)

        assert total == 1, f"Expected 1 result, got {total}"
        assert len(results) == 1

        r = results[0]
        frame_id = r.get("frame_id")
        frame = store.get_frame(frame_id)

        assert frame is not None
        assert frame.app_name == "Spotify"

    def test_pagination_citation_consistency(self, temp_db_with_frames):
        """Citation backtrace is consistent across paginated results."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        store = FramesStore(db_path=db_path)

        # Get first page
        results1, _ = engine.search(q="", limit=5, offset=0)
        # Get second page
        results2, _ = engine.search(q="", limit=5, offset=5)

        all_results = results1 + results2

        success_count = 0
        for r in all_results:
            frame_id = r.get("frame_id")
            frame = store.get_frame(frame_id)
            if frame is not None:
                success_count += 1

        success_rate = success_count / len(all_results) if all_results else 0
        assert success_rate >= 0.95, f"Pagination success rate {success_rate:.2%} < 95%"

    def test_time_range_citation_backtrace(self, temp_db_with_frames):
        """Citation backtrace works with time range filters."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        store = FramesStore(db_path=db_path)

        results, total = engine.search(
            q="",
            limit=20,
            offset=0,
            start_time="2026-03-18T12:00:00Z",
            end_time="2026-03-18T16:00:00Z",
        )

        # Should match frames 3-8 (12:00 to 16:00 inclusive)
        assert total >= 1, "Expected at least one result in time range"

        for r in results:
            frame_id = r.get("frame_id")
            frame = store.get_frame(frame_id)
            assert frame is not None, f"Frame {frame_id} not found"
            # Verify timestamp is within range (inclusive of endpoints)
            assert (
                "2026-03-18T12:00:00Z" <= frame.timestamp <= "2026-03-18T16:00:00Z"
            ), f"Timestamp {frame.timestamp} not in expected range"
