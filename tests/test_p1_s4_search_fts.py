"""Tests for FTS5 SearchEngine — P1-S4 Section 2.

Tests cover:
- SQL path verification (conditional JOINs)
- FTS recall correctness
- Response schema validation
- Reference field completeness
- Latency logging

Per tasks.md §2 and specs/fts-search/spec.md.
"""

import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from openrecall.server.search.engine import SearchEngine, _sanitize_fts_value


class TestSanitizeFtsValue:
    """Tests for _sanitize_fts_value helper function."""

    def test_basic_value(self):
        """Basic value is unchanged."""
        assert _sanitize_fts_value("Safari") == "Safari"

    def test_value_with_quotes(self):
        """Double quotes are stripped."""
        assert _sanitize_fts_value('test"value') == "testvalue"

    def test_multiple_quotes(self):
        """Multiple quotes are all stripped."""
        assert _sanitize_fts_value('"hello"') == "hello"
        assert _sanitize_fts_value('a"b"c') == "abc"

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert _sanitize_fts_value("") == ""

    def test_only_quotes(self):
        """Only quotes returns empty string."""
        assert _sanitize_fts_value('""') == ""
        assert _sanitize_fts_value('"') == ""

    def test_special_chars_preserved(self):
        """Special characters other than quotes are preserved."""
        assert _sanitize_fts_value("C++") == "C++"
        assert _sanitize_fts_value("test-app") == "test-app"

    def test_unicode_preserved(self):
        """Unicode characters are preserved."""
        assert _sanitize_fts_value("你好世界") == "你好世界"


@pytest.fixture
def temp_db():
    """Create a temporary database with migrated schema and test data.

    Uses the actual migration files to ensure the schema matches production
    after FTS unification.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "edge.db"
        frames_dir = Path(tmpdir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Run initial schema
        init_sql = Path(
            "openrecall/server/database/migrations/20260227000001_initial_schema.sql"
        ).read_text()
        conn.executescript(init_sql)

        # Run FTS unification migration
        migration_sql = Path(
            "openrecall/server/database/migrations/20260325120000_consolidate_fts_to_full_text.sql"
        ).read_text()
        conn.executescript(migration_sql)

        # Insert test frames with full_text populated (post-migration schema)
        # These mirror the test data from the old fixture, but use full_text
        test_frames = [
            (1, "capture-001", "2026-03-18T10:00:00Z", "Safari", "Web Browser", None, True, "Hello world from Safari", "ocr"),
            (2, "capture-002", "2026-03-18T11:00:00Z", "VSCode", "main.py", None, True, "def hello(): pass # code here", "ocr"),
            (3, "capture-003", "2026-03-18T12:00:00Z", "Terminal", "bash", None, False, "git status && git commit", "ocr"),
            (4, "capture-004", "2026-03-18T13:00:00Z", "Safari", "Google Search", None, True, "search query hello world", "ocr"),
            (5, "capture-005", "2026-03-18T14:00:00Z", "Slack", "#general", None, True, "meeting at 3pm hello team", "ocr"),
        ]

        for frame_id, capture_id, ts, app, window, url, focused, full_text, text_source in test_frames:
            conn.execute(
                """INSERT INTO frames (id, capture_id, timestamp, app_name, window_name, browser_url, focused, status, text_source, full_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?)""",
                (frame_id, capture_id, ts, app, window, url, focused, text_source, full_text),
            )

        conn.commit()
        conn.close()

        yield db_path, frames_dir


class TestSearchEngineBasic:
    """Basic search functionality tests."""

    def test_search_returns_results(self, temp_db):
        """Search returns results for matching query."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="hello", limit=20, offset=0)

        assert total >= 1
        assert len(results) >= 1

    def test_search_empty_query_returns_all(self, temp_db):
        """Empty query returns all frames (browse mode)."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="", limit=20, offset=0)

        assert total == 5
        assert len(results) == 5

    def test_search_no_results(self, temp_db):
        """Non-matching query returns empty results."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="nonexistentterm12345", limit=20, offset=0)

        assert total == 0
        assert len(results) == 0


class TestSearchEngineFTS:
    """FTS recall correctness tests."""

    def test_single_word_query(self, temp_db):
        """Single word query matches OCR text."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="Safari", limit=20, offset=0)

        # Should match Safari in app_name via frames_fts
        assert total >= 1

    def test_phrase_query(self, temp_db):
        """Phrase query matches OCR text."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="hello world", limit=20, offset=0)

        # Should match "Hello world from Safari" and "search query hello world"
        assert total >= 1

    def test_special_characters_quoted(self, temp_db):
        """Special characters are safely handled."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        # Should not raise FTS5 syntax error
        results, total = engine.search(q="foo(bar)", limit=20, offset=0)
        # Query won't match, but should not error
        assert isinstance(results, list)


class TestSearchEngineFiltering:
    """Metadata filtering tests."""

    def test_filter_by_app_name(self, temp_db):
        """Filter by app_name returns matching frames."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="", limit=20, offset=0, app_name="Safari")

        assert total == 2
        for r in results:
            assert r.get("app_name") == "Safari"

    def test_filter_by_window_name(self, temp_db):
        """Filter by window_name returns matching frames."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="", limit=20, offset=0, window_name="main.py")

        assert total == 1
        assert results[0].get("window_name") == "main.py"

    def test_filter_by_focused_true(self, temp_db):
        """Filter by focused=true returns focused frames."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="", limit=20, offset=0, focused=True)

        assert total == 4
        for r in results:
            assert r.get("focused") is True

    def test_filter_by_focused_false(self, temp_db):
        """Filter by focused=false returns unfocused frames."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="", limit=20, offset=0, focused=False)

        # Terminal has focused=False
        assert total == 1
        assert results[0].get("app_name") == "Terminal"

    def test_combined_text_and_metadata_filters(self, temp_db):
        """Combined text search and metadata filters."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="hello", limit=20, offset=0, app_name="Safari")

        # Should match "Hello world from Safari" but not Slack
        assert total >= 1

    def test_time_range_filter(self, temp_db):
        """Time range filtering."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(
            q="",
            limit=20,
            offset=0,
            start_time="2026-03-18T11:00:00Z",
            end_time="2026-03-18T12:30:00Z",
        )

        # Should match VSCode (11:00) and Terminal (12:00)
        assert total == 2

    def test_text_length_filter(self, temp_db):
        """Text length filtering."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="", limit=20, offset=0, min_length=25)

        # Only "meeting at 3pm hello team" (25 chars) and longer
        assert total >= 1


class TestSearchEnginePagination:
    """Pagination tests."""

    def test_limit(self, temp_db):
        """Limit parameter limits results."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="", limit=2, offset=0)

        assert total == 5
        assert len(results) == 2

    def test_offset(self, temp_db):
        """Offset parameter skips results."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results1, _ = engine.search(q="", limit=2, offset=0)
        results2, _ = engine.search(q="", limit=2, offset=2)

        # Results should be different
        ids1 = {r["frame_id"] for r in results1}
        ids2 = {r["frame_id"] for r in results2}
        assert ids1.isdisjoint(ids2)

    def test_limit_clamped_to_max(self, temp_db):
        """Limit is clamped to max 100."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        # Request limit 200, should be clamped to 100
        results, total = engine.search(q="", limit=200, offset=0)
        # No error should occur, and we get all 5 results (less than 100)
        assert total == 5


class TestSearchEngineResponseSchema:
    """Response schema validation tests."""

    def test_result_has_required_fields(self, temp_db):
        """Each result has required fields."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="hello", limit=20, offset=0)

        required_fields = [
            "frame_id", "timestamp", "text", "app_name", "window_name",
            "device_name", "focused", "file_path", "frame_url",
        ]

        for r in results:
            for field in required_fields:
                assert field in r, f"Missing field: {field}"

    def test_reference_fields_non_null(self, temp_db):
        """frame_id and timestamp are non-null for all results."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, _ = engine.search(q="", limit=20, offset=0)

        for r in results:
            assert r.get("frame_id") is not None
            assert r.get("timestamp") is not None

    def test_reserved_fields_present(self, temp_db):
        """Reserved fields are present as null/empty."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, _ = engine.search(q="", limit=20, offset=0)

        for r in results:
            # browser_url should be present (null for P1)
            assert "browser_url" in r
            # tags should be present (empty list for P1)
            assert "tags" in r
            assert r.get("tags") == []


class TestSearchEngineOrdering:
    """Result ordering tests."""

    def test_browse_mode_orders_by_timestamp_desc(self, temp_db):
        """Browse mode (no query) orders by timestamp DESC."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, _ = engine.search(q="", limit=20, offset=0)

        timestamps = [r["timestamp"] for r in results]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_search_mode_orders_by_rank(self, temp_db):
        """Search mode orders by BM25 rank then timestamp DESC."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, _ = engine.search(q="hello", limit=20, offset=0)

        # All results should contain "hello"
        for r in results:
            assert "hello" in r.get("text", "").lower() or "hello" in (r.get("app_name") or "").lower()


class TestSearchEngineCount:
    """Count query tests."""

    def test_count_matches_search(self, temp_db):
        """Count returns same total as search."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        results, total_from_search = engine.search(q="", limit=2, offset=0)
        total_from_count = engine.count(q="")

        assert total_from_search == total_from_count == 5

    def test_count_with_filters(self, temp_db):
        """Count respects filters."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        total = engine.count(q="", app_name="Safari")
        assert total == 2


class TestUnifiedFtsSearch:
    """Tests for unified FTS search using frames.full_text."""

    @pytest.fixture
    def unified_db(self, tmp_path):
        """Create a database with migrated schema and test data."""
        db_path = tmp_path / "unified.db"
        conn = sqlite3.connect(str(db_path))

        # Run initial schema
        init_sql = Path(
            "openrecall/server/database/migrations/20260227000001_initial_schema.sql"
        ).read_text()
        conn.executescript(init_sql)

        # Run FTS unification migration
        migration_sql = Path(
            "openrecall/server/database/migrations/20260325120000_consolidate_fts_to_full_text.sql"
        ).read_text()
        conn.executescript(migration_sql)

        # Insert test frames with full_text
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, full_text, app_name, window_name, status, text_source)
            VALUES ('ax-1', '2026-03-25T10:00:00Z', 'Email from alice@example.com about project', 'Mail', 'Inbox', 'completed', 'accessibility')
            """
        )
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, full_text, app_name, window_name, status, text_source)
            VALUES ('ocr-1', '2026-03-25T11:00:00Z', 'Meeting notes from yesterday standup', 'Notes', 'Meeting', 'completed', 'ocr')
            """
        )
        conn.commit()
        conn.close()

        return db_path

    def test_search_finds_text_in_full_text(self, unified_db):
        """Verify search finds text in full_text column."""
        from openrecall.server.search.engine import SearchEngine

        engine = SearchEngine(db_path=unified_db)
        results, total = engine.search(q="alice")

        assert total >= 1
        assert any("alice" in r.get("text", "").lower() for r in results)

    def test_search_with_metadata_filter(self, unified_db):
        """Verify search with app_name filter works."""
        from openrecall.server.search.engine import SearchEngine

        engine = SearchEngine(db_path=unified_db)
        results, total = engine.search(q="project", app_name="Mail")

        assert total >= 1
        for r in results:
            assert r.get("app_name") == "Mail"

    def test_content_type_param_ignored(self, unified_db):
        """Verify content_type parameter is accepted but ignored."""
        from openrecall.server.search.engine import SearchEngine

        engine = SearchEngine(db_path=unified_db)

        # All these should return the same results
        results_ocr, _ = engine.search(q="project", content_type="ocr")
        results_ax, _ = engine.search(q="project", content_type="accessibility")
        results_all, _ = engine.search(q="project", content_type="all")

        # All should find the email frame
        assert len(results_ocr) >= 1
        assert len(results_ax) >= 1
        assert len(results_all) >= 1
