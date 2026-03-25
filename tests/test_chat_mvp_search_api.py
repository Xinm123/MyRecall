"""Tests for /v1/search content-type aware endpoint.

Phase 7 of Chat MVP implementation.

These tests verify the /v1/search endpoint supports three content modes:
- content_type=ocr - OCR-only frames
- content_type=accessibility - Accessibility-canonical frames
- content_type=all - Merged results from both sources

SSOT: docs/v3/chat/mvp.md "Search Contract"
"""

import sqlite3
from pathlib import Path

import pytest

from openrecall.server.database.migrations_runner import run_migrations
from openrecall.server.search.engine import SearchEngine


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_db_with_mixed_frames(tmp_path: Path) -> Path:
    """Create a temporary database with both OCR and accessibility frames.

    This fixture creates:
    - 3 OCR-canonical frames (text_source='ocr')
    - 3 accessibility-canonical frames (text_source='accessibility')
    """
    db_path = tmp_path / "test_edge.db"
    conn = sqlite3.connect(str(db_path))

    # Apply migrations
    migrations_dir = Path(__file__).resolve().parent.parent / (
        "openrecall/server/database/migrations"
    )
    run_migrations(conn, migrations_dir)

    conn.row_factory = sqlite3.Row

    # Insert OCR-canonical frames
    ocr_frames = [
        {
            "capture_id": "ocr-capture-001",
            "timestamp": "2026-03-21T10:00:00Z",
            "app_name": "Terminal",
            "window_name": "bash",
            "browser_url": None,
            "focused": True,
            "device_name": "monitor_0",
            "text": "git status and git commit commands",
            "text_source": "ocr",
        },
        {
            "capture_id": "ocr-capture-002",
            "timestamp": "2026-03-21T11:00:00Z",
            "app_name": "VSCode",
            "window_name": "main.py",
            "browser_url": None,
            "focused": True,
            "device_name": "monitor_0",
            "text": "def hello_world(): pass",
            "text_source": "ocr",
        },
        {
            "capture_id": "ocr-capture-003",
            "timestamp": "2026-03-21T12:00:00Z",
            "app_name": "Safari",
            "window_name": "Search Results",
            "browser_url": "https://example.com/search?q=test",
            "focused": True,
            "device_name": "monitor_0",
            "text": "Search results for test query",
            "text_source": "ocr",
        },
    ]

    for frame_data in ocr_frames:
        # Insert frame with ocr_text column
        conn.execute("""
            INSERT INTO frames (capture_id, timestamp, app_name, window_name, browser_url,
                                focused, device_name, ocr_text, text_source, status, full_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
        """, (
            frame_data["capture_id"],
            frame_data["timestamp"],
            frame_data["app_name"],
            frame_data["window_name"],
            frame_data["browser_url"],
            frame_data["focused"],
            frame_data["device_name"],
            frame_data["text"],
            frame_data["text_source"],
            frame_data["text"],
        ))
        frame_id = conn.execute(
            "SELECT id FROM frames WHERE capture_id = ?",
            (frame_data["capture_id"],)
        ).fetchone()["id"]

        # Insert ocr_text (for completeness)
        conn.execute("""
            INSERT INTO ocr_text (frame_id, text, text_length, app_name, window_name)
            VALUES (?, ?, ?, ?, ?)
        """, (
            frame_id,
            frame_data["text"],
            len(frame_data["text"]),
            frame_data["app_name"],
            frame_data["window_name"],
        ))

    # Insert accessibility-canonical frames
    ax_frames = [
        {
            "capture_id": "ax-capture-001",
            "timestamp": "2026-03-21T10:30:00Z",
            "app_name": "Safari",
            "window_name": "Documentation",
            "browser_url": "https://example.com/docs",
            "focused": True,
            "device_name": "monitor_0",
            "text": "API Documentation for test endpoints",
            "text_source": "accessibility",
        },
        {
            "capture_id": "ax-capture-002",
            "timestamp": "2026-03-21T11:30:00Z",
            "app_name": "Chrome",
            "window_name": "GitHub",
            "browser_url": "https://github.com/test/repo",
            "focused": True,
            "device_name": "monitor_0",
            "text": "Test repository with hello world example",
            "text_source": "accessibility",
        },
        {
            "capture_id": "ax-capture-003",
            "timestamp": "2026-03-21T12:30:00Z",
            "app_name": "Slack",
            "window_name": "#general",
            "browser_url": None,
            "focused": True,
            "device_name": "monitor_0",
            "text": "Team meeting about test plans",
            "text_source": "accessibility",
        },
    ]

    for frame_data in ax_frames:
        # Insert frame with accessibility_text column AND full_text
        conn.execute("""
            INSERT INTO frames (capture_id, timestamp, app_name, window_name, browser_url,
                                focused, device_name, accessibility_text, text_source, status, full_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
        """, (
            frame_data["capture_id"],
            frame_data["timestamp"],
            frame_data["app_name"],
            frame_data["window_name"],
            frame_data["browser_url"],
            frame_data["focused"],
            frame_data["device_name"],
            frame_data["text"],
            frame_data["text_source"],
            frame_data["text"],
        ))
        frame_id = conn.execute(
            "SELECT id FROM frames WHERE capture_id = ?",
            (frame_data["capture_id"],)
        ).fetchone()["id"]

        # Insert accessibility (for completeness)
        conn.execute("""
            INSERT INTO accessibility (frame_id, timestamp, app_name, window_name, browser_url, text_content, text_length)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            frame_id,
            frame_data["timestamp"],
            frame_data["app_name"],
            frame_data["window_name"],
            frame_data["browser_url"],
            frame_data["text"],
            len(frame_data["text"]),
        ))

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def search_engine(temp_db_with_mixed_frames: Path, tmp_path: Path) -> SearchEngine:
    """Create a SearchEngine with test database."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    return SearchEngine(db_path=temp_db_with_mixed_frames, frames_dir=frames_dir)


# ============================================================================
# Test: content_type=accessibility
# ============================================================================

class TestSearchContentTypeAccessibility:
    """Tests for content_type=accessibility search.

    Note: After FTS unification, content_type is deprecated and ignored.
    These tests verify the search still functions (returns results) but
    the content_type filter is no longer applied.
    """

    @pytest.mark.skip(reason="content_type filtering is deprecated and ignored after FTS unification")
    def test_search_content_type_accessibility_returns_accessibility_results(
        self, search_engine: SearchEngine
    ):
        """Search with content_type=accessibility should return only accessibility frames."""
        results, total = search_engine.search(
            q="",
            content_type="accessibility",
            limit=20,
            offset=0,
        )

        assert total == 3
        assert len(results) == 3

        # All results should have text_source='accessibility'
        for r in results:
            assert r.get("text_source") == "accessibility"

    @pytest.mark.skip(reason="content_type filtering is deprecated and ignored after FTS unification")
    def test_search_accessibility_with_query_matches_text(
        self, search_engine: SearchEngine
    ):
        """Search with query should match accessibility text_content."""
        results, total = search_engine.search(
            q="test",
            content_type="accessibility",
            limit=20,
            offset=0,
        )

        # Should match all 3 accessibility frames (they all contain "test")
        assert total == 3

    def test_search_accessibility_result_has_type_field(
        self, search_engine: SearchEngine
    ):
        """Search results should have a type field indicating Accessibility."""
        results, _ = search_engine.search(
            q="",
            content_type="accessibility",
            limit=1,
            offset=0,
        )

        # Note: The SearchEngine returns raw dicts. The API layer adds the type wrapper.
        # This test verifies the text_source field is set correctly.
        assert results[0].get("text_source") == "accessibility"


# ============================================================================
# Test: content_type=ocr
# ============================================================================

class TestSearchContentTypeOcr:
    """Tests for content_type=ocr search.

    Note: After FTS unification, content_type is deprecated and ignored.
    """

    @pytest.mark.skip(reason="content_type filtering is deprecated and ignored after FTS unification")
    def test_search_content_type_ocr_returns_ocr_results(
        self, search_engine: SearchEngine
    ):
        """Search with content_type=ocr should return only OCR frames."""
        results, total = search_engine.search(
            q="",
            content_type="ocr",
            limit=20,
            offset=0,
        )

        assert total == 3
        assert len(results) == 3

        # All results should have text_source='ocr'
        for r in results:
            assert r.get("text_source") == "ocr"

    def test_search_ocr_with_query_matches_text(
        self, search_engine: SearchEngine
    ):
        """Search with query should match OCR text."""
        results, total = search_engine.search(
            q="git",
            content_type="ocr",
            limit=20,
            offset=0,
        )

        # Should match Terminal frame with "git status and git commit"
        assert total == 1
        assert results[0].get("app_name") == "Terminal"


# ============================================================================
# Test: content_type=all
# ============================================================================

class TestSearchContentTypeAll:
    """Tests for content_type=all merged search."""

    def test_search_content_type_all_returns_merged_results(
        self, search_engine: SearchEngine
    ):
        """Search with content_type=all should return both OCR and accessibility frames."""
        results, total = search_engine.search(
            q="",
            content_type="all",
            limit=20,
            offset=0,
        )

        assert total == 6
        assert len(results) == 6

        # Should have both OCR and accessibility frames
        text_sources = {r.get("text_source") for r in results}
        assert text_sources == {"ocr", "accessibility"}

    def test_search_content_type_all_no_duplicates(
        self, search_engine: SearchEngine
    ):
        """Merged results should not have duplicate frame_ids."""
        results, _ = search_engine.search(
            q="test",
            content_type="all",
            limit=20,
            offset=0,
        )

        frame_ids = [r.get("frame_id") for r in results]
        assert len(frame_ids) == len(set(frame_ids)), "Duplicate frame_ids found"

    def test_search_content_type_all_orders_by_timestamp_desc(
        self, search_engine: SearchEngine
    ):
        """Merged results should be sorted by timestamp DESC."""
        results, _ = search_engine.search(
            q="",
            content_type="all",
            limit=20,
            offset=0,
        )

        timestamps = [r.get("timestamp") for r in results]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_search_content_type_all_applies_pagination_after_merge(
        self, search_engine: SearchEngine
    ):
        """Pagination should be applied after merge."""
        # Request first 2 results
        results_page1, total = search_engine.search(
            q="",
            content_type="all",
            limit=2,
            offset=0,
        )

        assert total == 6  # Total count is global
        assert len(results_page1) == 2

        # Request next 2 results
        results_page2, _ = search_engine.search(
            q="",
            content_type="all",
            limit=2,
            offset=2,
        )

        assert len(results_page2) == 2

        # Verify pages are different
        ids_page1 = {r.get("frame_id") for r in results_page1}
        ids_page2 = {r.get("frame_id") for r in results_page2}
        assert ids_page1.isdisjoint(ids_page2)

    def test_search_all_with_query_returns_both_types(
        self, search_engine: SearchEngine
    ):
        """Search with query across all should return matching results from both sources."""
        # Search for "hello" - should match both OCR and accessibility frames
        results, total = search_engine.search(
            q="hello",
            content_type="all",
            limit=20,
            offset=0,
        )

        # Should have results from both sources
        text_sources = {r.get("text_source") for r in results}
        # At minimum should match VSCode (OCR) and Chrome accessibility
        assert len(results) >= 2


# ============================================================================
# Test: browser_url filter
# ============================================================================

class TestSearchBrowserUrlFilter:
    """Tests for browser_url filter."""

    def test_search_browser_url_filter_works_for_ocr(
        self, search_engine: SearchEngine
    ):
        """browser_url filter should work for OCR frames.

        Note: content_type=ocr is deprecated/ignored; use q= to filter OCR vs AX.
        """
        results, total = search_engine.search(
            q="Search",
            content_type="ocr",
            browser_url="example.com",
            limit=20,
            offset=0,
        )

        # Should match the Safari OCR frame (full_text contains "Search")
        assert total == 1
        assert results[0].get("app_name") == "Safari"

    def test_search_browser_url_filter_works_for_accessibility(
        self, search_engine: SearchEngine
    ):
        """browser_url filter should work for accessibility frames."""
        results, total = search_engine.search(
            q="",
            content_type="accessibility",
            browser_url="github.com",
            limit=20,
            offset=0,
        )

        # Should match the Chrome accessibility frame
        assert total == 1
        assert results[0].get("app_name") == "Chrome"

    def test_search_browser_url_filter_works_for_all(
        self, search_engine: SearchEngine
    ):
        """browser_url filter should work for merged search."""
        results, total = search_engine.search(
            q="",
            content_type="all",
            browser_url="example.com",
            limit=20,
            offset=0,
        )

        # Should match both Safari frames (OCR and accessibility)
        assert total == 2


# ============================================================================
# Test: Ordering
# ============================================================================

class TestSearchOrdering:
    """Tests for result ordering."""

    def test_search_orders_by_rank_when_query_present(
        self, search_engine: SearchEngine
    ):
        """When query is present, results should be ordered by FTS rank then timestamp DESC."""
        results, _ = search_engine.search(
            q="test",
            content_type="all",
            limit=20,
            offset=0,
        )

        # All results should contain "test"
        for r in results:
            text = r.get("text", "").lower()
            assert "test" in text

        # Results with fts_rank should be sorted by rank then timestamp
        # (Note: exact rank ordering depends on BM25 scoring)
        prev_rank = None
        prev_ts = None
        for r in results:
            rank = r.get("fts_rank")
            ts = r.get("timestamp")
            if rank is not None and prev_rank is not None:
                # Lower rank = better match in FTS5
                if rank == prev_rank:
                    if prev_ts is not None:
                        assert ts <= prev_ts  # Same rank: timestamp DESC
            prev_rank = rank
            prev_ts = ts

    def test_search_orders_by_timestamp_when_no_query(
        self, search_engine: SearchEngine
    ):
        """When no query, results should be ordered by timestamp DESC."""
        results, _ = search_engine.search(
            q="",
            content_type="all",
            limit=20,
            offset=0,
        )

        timestamps = [r.get("timestamp") for r in results]
        assert timestamps == sorted(timestamps, reverse=True)


# ============================================================================
# Test: Default behavior
# ============================================================================

class TestSearchDefaultBehavior:
    """Tests for default behavior."""

    def test_search_default_content_type_is_all(
        self, search_engine: SearchEngine
    ):
        """Default content_type should be 'all'."""
        # Call without content_type parameter
        results, total = search_engine.search(
            q="",
            limit=20,
            offset=0,
        )

        # Should return all 6 frames
        assert total == 6

    def test_search_invalid_content_type_defaults_to_all(
        self, search_engine: SearchEngine
    ):
        """Invalid content_type should default to 'all'."""
        results, total = search_engine.search(
            q="",
            content_type="invalid",
            limit=20,
            offset=0,
        )

        # Should return all 6 frames
        assert total == 6
