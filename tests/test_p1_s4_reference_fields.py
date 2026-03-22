"""Hard Gate Test: Reference Field Completeness — P1-S4.

This is a Hard Gate 100% test: frame_id + timestamp must be simultaneously
non-null for ALL search results across ALL search scenarios.

Reference fields (frame_id, timestamp) are critical for:
- Frame retrieval via /v1/frames/{frame_id}
- Timeline navigation and ordering
- Audit trail and data integrity

Any result missing either field is a critical data integrity failure.

Test scenarios:
- Empty query (browse mode)
- Text search queries
- Metadata filters (app_name, window_name, focused)
- Time range filters
- Text length filters
- Combined filters
- Pagination scenarios
- Edge cases (special characters, unicode)

Per specs/fts-search/spec.md §3.2 and data-model.md §3.0.3.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.search.engine import SearchEngine

# Mark all tests in this module as integration and search tests
pytestmark = [pytest.mark.integration, pytest.mark.search]


@pytest.fixture
def temp_db_with_frames():
    """Create a temporary database with test frames for reference field testing."""
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
                ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
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

            -- Accessibility table for content_type=accessibility search
            CREATE TABLE IF NOT EXISTS accessibility (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frame_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                app_name TEXT NOT NULL,
                window_name TEXT NOT NULL,
                browser_url TEXT,
                text_content TEXT NOT NULL,
                text_length INTEGER DEFAULT 0,
                FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS accessibility_fts USING fts5(
                text_content, app_name, window_name, browser_url,
                content='accessibility', content_rowid='id', tokenize='unicode61'
            );

            CREATE INDEX IF NOT EXISTS idx_frames_timestamp ON frames(timestamp);
            CREATE INDEX IF NOT EXISTS idx_ocr_text_frame_id ON ocr_text(frame_id);
            CREATE INDEX IF NOT EXISTS idx_accessibility_frame_id ON accessibility(frame_id);

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

        # Insert diverse test frames covering various scenarios
        test_frames = [
            # (frame_id, capture_id, timestamp, app_name, window_name, focused, ocr_text)
            (
                1,
                "cap-001",
                "2026-03-18T08:00:00Z",
                "Safari",
                "Web Browser",
                True,
                "Hello world from Safari browser",
            ),
            (
                2,
                "cap-002",
                "2026-03-18T09:00:00Z",
                "VSCode",
                "main.py - Project",
                True,
                "def hello(): return 'world'",
            ),
            (
                3,
                "cap-003",
                "2026-03-18T10:00:00Z",
                "Terminal",
                "bash - ~/work",
                False,
                "git status && git commit -m 'hello'",
            ),
            (
                4,
                "cap-004",
                "2026-03-18T11:00:00Z",
                "Safari",
                "Google Search",
                True,
                "search query hello world results",
            ),
            (
                5,
                "cap-005",
                "2026-03-18T12:00:00Z",
                "Slack",
                "#general",
                True,
                "meeting at 3pm hello team",
            ),
            (
                6,
                "cap-006",
                "2026-03-18T13:00:00Z",
                "Mail",
                "Inbox",
                True,
                "Subject: Project update hello",
            ),
            (
                7,
                "cap-007",
                "2026-03-18T14:00:00Z",
                "Notes",
                "Meeting Notes",
                False,
                "Discussion points hello all",
            ),
            (
                8,
                "cap-008",
                "2026-03-18T15:00:00Z",
                "Finder",
                "Documents",
                True,
                "file.txt hello document",
            ),
            (
                9,
                "cap-009",
                "2026-03-18T16:00:00Z",
                "Preview",
                "report.pdf",
                True,
                "Page 1: Introduction hello world",
            ),
            (
                10,
                "cap-010",
                "2026-03-18T17:00:00Z",
                "Calendar",
                "Today",
                False,
                "Event: hello sync meeting",
            ),
        ]

        for frame_id, capture_id, ts, app, window, focused, ocr_text in test_frames:
            conn.execute(
                """INSERT INTO frames (id, capture_id, timestamp, app_name, window_name, browser_url, focused, status, text_source)
                   VALUES (?, ?, ?, ?, ?, NULL, ?, 'completed', 'ocr')""",
                (frame_id, capture_id, ts, app, window, focused),
            )
            conn.execute(
                """INSERT INTO ocr_text (frame_id, text, text_length, ocr_engine)
                   VALUES (?, ?, ?, 'test')""",
                (frame_id, ocr_text, len(ocr_text)),
            )

        conn.commit()
        conn.close()

        yield db_path, frames_dir


class TestReferenceFieldCompletenessHardGate:
    """Hard Gate tests ensuring frame_id + timestamp are always non-null.

    This is a 100% compliance test - every single search result must have
    both reference fields populated. Any failure is a critical data integrity
    issue that breaks frame retrieval and timeline navigation.
    """

    def _assert_all_results_have_reference_fields(
        self, results: list, scenario: str
    ) -> None:
        """Assert all results have both frame_id and timestamp non-null.

        Args:
            results: List of search result dictionaries
            scenario: Description of the test scenario for error messages

        Raises:
            AssertionError: If any result is missing frame_id or timestamp
        """
        assert isinstance(results, list), f"[{scenario}] Results should be a list"

        for i, result in enumerate(results):
            assert isinstance(result, dict), f"[{scenario}] Result {i} should be a dict"

            # Hard Gate: frame_id must be non-null
            assert result.get("frame_id") is not None, (
                f"[{scenario}] Result {i} missing frame_id: {result}"
            )
            assert isinstance(result.get("frame_id"), int), (
                f"[{scenario}] Result {i} frame_id should be int: {result.get('frame_id')}"
            )

            # Hard Gate: timestamp must be non-null
            assert result.get("timestamp") is not None, (
                f"[{scenario}] Result {i} missing timestamp: {result}"
            )
            assert isinstance(result.get("timestamp"), str), (
                f"[{scenario}] Result {i} timestamp should be str: {result.get('timestamp')}"
            )
            assert len(result.get("timestamp", "")) > 0, (
                f"[{scenario}] Result {i} timestamp should be non-empty: {result.get('timestamp')}"
            )

    # =========================================================================
    # Browse Mode (Empty Query) Tests
    # =========================================================================

    def test_browse_mode_all_results_have_reference_fields(self, temp_db_with_frames):
        """Browse mode (empty query) returns all results with reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="", limit=100, offset=0)

        assert total == 10, "Expected 10 frames in database"
        assert len(results) == 10, "Expected 10 results in browse mode"
        self._assert_all_results_have_reference_fields(results, "browse_mode")

    def test_browse_mode_with_pagination(self, temp_db_with_frames):
        """Browse mode pagination maintains reference field completeness."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # First page
        results_page1, total = engine.search(q="", limit=3, offset=0)
        assert len(results_page1) == 3
        self._assert_all_results_have_reference_fields(results_page1, "browse_page1")

        # Second page
        results_page2, _ = engine.search(q="", limit=3, offset=3)
        assert len(results_page2) == 3
        self._assert_all_results_have_reference_fields(results_page2, "browse_page2")

        # Third page
        results_page3, _ = engine.search(q="", limit=3, offset=6)
        assert len(results_page3) == 3
        self._assert_all_results_have_reference_fields(results_page3, "browse_page3")

        # Last partial page
        results_page4, _ = engine.search(q="", limit=3, offset=9)
        assert len(results_page4) == 1
        self._assert_all_results_have_reference_fields(results_page4, "browse_page4")

    # =========================================================================
    # Text Search Tests
    # =========================================================================

    def test_text_search_all_results_have_reference_fields(self, temp_db_with_frames):
        """Text search returns results with reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="hello", limit=100, offset=0)

        assert total >= 1, "Expected at least 1 result for 'hello'"
        self._assert_all_results_have_reference_fields(results, "text_search_hello")

    def test_text_search_single_word(self, temp_db_with_frames):
        """Single word search maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="Safari", limit=100, offset=0)
        self._assert_all_results_have_reference_fields(results, "text_search_safari")

    def test_text_search_phrase(self, temp_db_with_frames):
        """Phrase search maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="hello world", limit=100, offset=0)
        self._assert_all_results_have_reference_fields(results, "text_search_phrase")

    def test_text_search_no_results(self, temp_db_with_frames):
        """No results case returns empty list (no reference fields to check)."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="nonexistenttermxyz12345", limit=100, offset=0)

        assert total == 0
        assert len(results) == 0
        # Empty list is valid - no reference fields to validate

    def test_text_search_special_characters(self, temp_db_with_frames):
        """Special characters handled without breaking reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Query with special chars that might cause FTS issues
        results, _ = engine.search(q="foo(bar)", limit=100, offset=0)
        # May have no results, but should not error
        self._assert_all_results_have_reference_fields(
            results, "text_search_special_chars"
        )

    # =========================================================================
    # Metadata Filter Tests
    # =========================================================================

    def test_filter_by_app_name(self, temp_db_with_frames):
        """Filter by app_name maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="", limit=100, offset=0, app_name="Safari")
        assert total == 2, "Expected 2 Safari frames"
        self._assert_all_results_have_reference_fields(results, "filter_app_name")

    def test_filter_by_window_name(self, temp_db_with_frames):
        """Filter by window_name maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(
            q="", limit=100, offset=0, window_name="main.py - Project"
        )
        assert total == 1
        self._assert_all_results_have_reference_fields(results, "filter_window_name")

    def test_filter_by_focused_true(self, temp_db_with_frames):
        """Filter by focused=true maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="", limit=100, offset=0, focused=True)
        assert total == 7, "Expected 7 focused frames"
        self._assert_all_results_have_reference_fields(results, "filter_focused_true")

    def test_filter_by_focused_false(self, temp_db_with_frames):
        """Filter by focused=false maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="", limit=100, offset=0, focused=False)
        assert total == 3, "Expected 3 unfocused frames"
        self._assert_all_results_have_reference_fields(results, "filter_focused_false")

    # =========================================================================
    # Time Range Filter Tests
    # =========================================================================

    def test_filter_by_time_range(self, temp_db_with_frames):
        """Time range filter maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(
            q="",
            limit=100,
            offset=0,
            start_time="2026-03-18T10:00:00Z",
            end_time="2026-03-18T14:00:00Z",
        )
        # Should match frames at 10:00, 11:00, 12:00, 13:00, 14:00
        assert total == 5
        self._assert_all_results_have_reference_fields(results, "filter_time_range")

    def test_filter_by_start_time_only(self, temp_db_with_frames):
        """Start time filter maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(
            q="",
            limit=100,
            offset=0,
            start_time="2026-03-18T15:00:00Z",
        )
        assert total == 3  # 15:00, 16:00, 17:00
        self._assert_all_results_have_reference_fields(results, "filter_start_time")

    def test_filter_by_end_time_only(self, temp_db_with_frames):
        """End time filter maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(
            q="",
            limit=100,
            offset=0,
            end_time="2026-03-18T10:00:00Z",
        )
        assert total == 3  # 08:00, 09:00, 10:00
        self._assert_all_results_have_reference_fields(results, "filter_end_time")

    # =========================================================================
    # Text Length Filter Tests
    # =========================================================================

    def test_filter_by_min_length(self, temp_db_with_frames):
        """Min length filter maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="", limit=100, offset=0, min_length=30)
        assert total >= 1
        self._assert_all_results_have_reference_fields(results, "filter_min_length")

    def test_filter_by_max_length(self, temp_db_with_frames):
        """Max length filter maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="", limit=100, offset=0, max_length=25)
        assert total >= 1
        self._assert_all_results_have_reference_fields(results, "filter_max_length")

    def test_filter_by_length_range(self, temp_db_with_frames):
        """Length range filter maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(
            q="", limit=100, offset=0, min_length=20, max_length=35
        )
        self._assert_all_results_have_reference_fields(results, "filter_length_range")

    # =========================================================================
    # Combined Filter Tests
    # =========================================================================

    def test_combined_text_and_app_filter(self, temp_db_with_frames):
        """Combined text search + app filter maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(
            q="hello", limit=100, offset=0, app_name="Safari"
        )
        assert total >= 1
        self._assert_all_results_have_reference_fields(results, "combined_text_app")

    def test_combined_text_and_focused_filter(self, temp_db_with_frames):
        """Combined text search + focused filter maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="hello", limit=100, offset=0, focused=True)
        self._assert_all_results_have_reference_fields(results, "combined_text_focused")

    def test_combined_time_and_app_filter(self, temp_db_with_frames):
        """Combined time range + app filter maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(
            q="",
            limit=100,
            offset=0,
            app_name="Safari",
            start_time="2026-03-18T07:00:00Z",
            end_time="2026-03-18T12:00:00Z",
        )
        self._assert_all_results_have_reference_fields(results, "combined_time_app")

    def test_combined_multiple_filters(self, temp_db_with_frames):
        """Multiple combined filters maintain reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(
            q="hello",
            limit=100,
            offset=0,
            app_name="Safari",
            focused=True,
            start_time="2026-03-18T07:00:00Z",
            end_time="2026-03-18T12:00:00Z",
        )
        self._assert_all_results_have_reference_fields(results, "combined_multiple")

    # =========================================================================
    # Pagination with Filters Tests
    # =========================================================================

    def test_pagination_with_text_search(self, temp_db_with_frames):
        """Pagination with text search maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Get all results first
        all_results, total = engine.search(q="hello", limit=100, offset=0)

        # Paginate through them
        page_size = 2
        for offset in range(0, total, page_size):
            page_results, _ = engine.search(q="hello", limit=page_size, offset=offset)
            self._assert_all_results_have_reference_fields(
                page_results, f"pagination_text_search_offset_{offset}"
            )

    def test_pagination_with_filters(self, temp_db_with_frames):
        """Pagination with filters maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Paginate with focused=true filter
        for offset in [0, 2, 4, 6]:
            results, _ = engine.search(q="", limit=2, offset=offset, focused=True)
            self._assert_all_results_have_reference_fields(
                results, f"pagination_filter_offset_{offset}"
            )

    # =========================================================================
    # Edge Case Tests
    # =========================================================================

    def test_large_limit(self, temp_db_with_frames):
        """Large limit maintains reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(
            q="", limit=1000, offset=0
        )  # Will be clamped to 100
        self._assert_all_results_have_reference_fields(results, "large_limit")

    def test_zero_limit(self, temp_db_with_frames):
        """Zero limit returns empty results (clamped to 1)."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="", limit=0, offset=0)
        # Limit 0 is clamped to 1
        assert total == 10
        assert len(results) == 1
        self._assert_all_results_have_reference_fields(results, "zero_limit")

    def test_large_offset(self, temp_db_with_frames):
        """Large offset returns empty results."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total = engine.search(q="", limit=10, offset=1000)
        assert total == 10
        assert len(results) == 0
        # No results to validate - this is valid behavior

    def test_result_ordering_preserves_reference_fields(self, temp_db_with_frames):
        """Result ordering (timestamp DESC) preserves reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, _ = engine.search(q="", limit=100, offset=0)

        # Verify ordering while checking reference fields
        timestamps = []
        for result in results:
            self._assert_all_results_have_reference_fields([result], "ordering_check")
            timestamps.append(result["timestamp"])

        # Should be descending order
        assert timestamps == sorted(timestamps, reverse=True), (
            "Results should be ordered by timestamp DESC"
        )

    def test_text_search_ranking_preserves_reference_fields(self, temp_db_with_frames):
        """BM25 ranking for text search preserves reference fields."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, _ = engine.search(q="hello", limit=100, offset=0)
        self._assert_all_results_have_reference_fields(results, "bm25_ranking")


class TestReferenceFieldDataIntegrity:
    """Additional tests for reference field data integrity."""

    def test_frame_id_is_positive_integer(self, temp_db_with_frames):
        """All frame_id values are positive integers."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, _ = engine.search(q="", limit=100, offset=0)

        for result in results:
            frame_id = result.get("frame_id")
            assert frame_id > 0, f"frame_id should be positive: {frame_id}"
            assert isinstance(frame_id, int), (
                f"frame_id should be int: {type(frame_id)}"
            )

    def test_timestamp_is_iso8601_format(self, temp_db_with_frames):
        """All timestamps are valid ISO8601 UTC format."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, _ = engine.search(q="", limit=100, offset=0)

        for result in results:
            timestamp = result.get("timestamp")
            # ISO8601 format check: YYYY-MM-DDTHH:MM:SSZ
            assert "T" in timestamp, f"Timestamp should contain T: {timestamp}"
            assert timestamp.endswith("Z"), f"Timestamp should end with Z: {timestamp}"
            # Basic structure validation
            parts = timestamp.replace("Z", "").split("T")
            assert len(parts) == 2, (
                f"Timestamp should have date and time parts: {timestamp}"
            )
            date_part, time_part = parts
            assert len(date_part) == 10, f"Date part should be 10 chars: {date_part}"
            assert len(time_part) >= 8, (
                f"Time part should be at least 8 chars: {time_part}"
            )

    def test_frame_id_uniqueness_in_results(self, temp_db_with_frames):
        """All frame_id values are unique within a result set."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, _ = engine.search(q="", limit=100, offset=0)

        frame_ids = [r["frame_id"] for r in results]
        assert len(frame_ids) == len(set(frame_ids)), "All frame_ids should be unique"

    def test_timestamp_uniqueness_in_results(self, temp_db_with_frames):
        """All timestamp values are unique within a result set."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, _ = engine.search(q="", limit=100, offset=0)

        timestamps = [r["timestamp"] for r in results]
        assert len(timestamps) == len(set(timestamps)), (
            "All timestamps should be unique"
        )

    def test_reference_fields_match_database(self, temp_db_with_frames):
        """Reference fields in results match database values."""
        db_path, frames_dir = temp_db_with_frames
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Get results from search
        results, _ = engine.search(q="", limit=100, offset=0)

        # Query database directly for comparison
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        db_rows = conn.execute(
            """SELECT id, timestamp FROM frames ORDER BY timestamp DESC"""
        ).fetchall()
        conn.close()

        # Build expected map
        expected = {row["id"]: row["timestamp"] for row in db_rows}

        # Verify each result matches
        for result in results:
            frame_id = result["frame_id"]
            timestamp = result["timestamp"]
            assert frame_id in expected, f"frame_id {frame_id} not in database"
            assert expected[frame_id] == timestamp, (
                f"Timestamp mismatch for frame_id {frame_id}: "
                f"expected {expected[frame_id]}, got {timestamp}"
            )
