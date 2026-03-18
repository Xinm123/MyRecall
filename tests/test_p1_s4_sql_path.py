"""SQL path verification tests for SearchEngine — P1-S4 Section 2.1.

Tests verify that SearchEngine._build_query() generates correct SQL for
different parameter combinations:

- has-q-no-filter: Text query only (JOIN ocr_text_fts)
- has-q-has-filter: Text + metadata filters (JOIN both FTS tables)
- no-q-has-filter: Metadata filters only (JOIN frames_fts)
- no-q-no-filter: Browse mode (no FTS JOINs)

Per tasks.md §2 and specs/fts-search/spec.md.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.search.engine import SearchEngine, SearchParams


pytestmark = [pytest.mark.integration, pytest.mark.search]


@pytest.fixture
def temp_db():
    """Create a temporary database with test schema (minimal, no data needed)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        frames_dir = Path(tmpdir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create minimal schema for SQL path verification
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
        """)

        conn.commit()
        conn.close()

        yield db_path, frames_dir


class TestSQLPathVerification:
    """Verify SQL query paths for different parameter combinations."""

    def test_has_q_no_filter(self, temp_db):
        """Text query only triggers ocr_text_fts JOIN, no frames_fts JOIN.

        Expected path:
        - has_text_query = True
        - has_metadata_filters = False
        - SQL should contain: JOIN ocr_text_fts
        - SQL should NOT contain: JOIN frames_fts
        """
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="hello world", limit=20, offset=0)
        sql, sql_params = engine._build_query(params, is_count=False)

        # Verify FTS search is present
        assert "ocr_text_fts" in sql.lower(), "SQL should reference ocr_text_fts table"
        assert "MATCH" in sql.upper(), "SQL should contain MATCH clause for FTS"

        # Verify no frames_fts JOIN when no metadata filters
        sql_lower = sql.lower()
        assert "frames_fts" not in sql_lower or "ocr_text_fts" in sql_lower, (
            "frames_fts should not appear without metadata filters"
        )

        # Verify rank is selected (indicates FTS ordering)
        assert "rank" in sql.lower(), "SQL should select rank for FTS ordering"

        # Verify parameterization
        assert len(sql_params) >= 1, "Should have at least one parameter for the query"

    def test_has_q_has_filter(self, temp_db):
        """Text query + metadata filters triggers both FTS JOINs.

        Expected path:
        - has_text_query = True
        - has_metadata_filters = True
        - SQL should contain: JOIN ocr_text_fts AND JOIN frames_fts
        """
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(
            q="search term",
            limit=20,
            offset=0,
            app_name="Safari",
            focused=True,
        )
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Verify both FTS tables are referenced
        assert "ocr_text_fts" in sql_lower, "SQL should reference ocr_text_fts table"
        assert "frames_fts" in sql_lower, "SQL should reference frames_fts table"

        # Verify MATCH clauses present
        assert "MATCH" in sql.upper(), "SQL should contain MATCH clause(s)"

        # Verify rank for text ordering
        assert "rank" in sql_lower, "SQL should select rank for FTS ordering"

        # Verify multiple parameters (query + metadata filters)
        assert len(sql_params) >= 2, (
            "Should have parameters for query and metadata filters"
        )

    def test_no_q_has_filter(self, temp_db):
        """Metadata filters only triggers frames_fts JOIN, no ocr_text_fts JOIN.

        Expected path:
        - has_text_query = False
        - has_metadata_filters = True
        - SQL should contain: JOIN frames_fts
        - SQL should NOT contain: JOIN ocr_text_fts
        """
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(
            q="",
            limit=20,
            offset=0,
            app_name="Terminal",
            window_name="bash",
        )
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Verify frames_fts JOIN for metadata filtering
        assert "frames_fts" in sql_lower, (
            "SQL should reference frames_fts for metadata filters"
        )
        assert "MATCH" in sql.upper(), "SQL should contain MATCH clause for FTS filter"

        # Verify no ocr_text_fts when no text query
        assert "ocr_text_fts" not in sql_lower, (
            "ocr_text_fts should not be present without text query"
        )

        # Verify timestamp ordering (browse mode style)
        assert "ORDER BY" in sql.upper(), "SQL should have ORDER BY clause"
        assert "timestamp" in sql_lower, "Browse mode should order by timestamp"

    def test_no_q_no_filter(self, temp_db):
        """Browse mode: no query, no filters, no FTS JOINs.

        Expected path:
        - has_text_query = False
        - has_metadata_filters = False
        - SQL should NOT contain any FTS JOINs
        - Simple frames/ocr_text query with timestamp ordering
        """
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="", limit=20, offset=0)
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Verify no FTS tables referenced
        assert "frames_fts" not in sql_lower, (
            "frames_fts should not appear in browse mode"
        )
        assert "ocr_text_fts" not in sql_lower, (
            "ocr_text_fts should not appear in browse mode"
        )

        # Verify no MATCH clause
        assert "MATCH" not in sql.upper(), "Browse mode should not have MATCH clause"

        # Verify simple JOIN structure (lowercase with ON clause)
        assert "inner join ocr_text" in sql_lower, "Should always join ocr_text"

        # Verify timestamp ordering
        assert "ORDER BY" in sql.upper(), "SQL should have ORDER BY clause"
        assert "timestamp" in sql_lower, "Browse mode should order by timestamp"

        # Verify no parameters for FTS
        assert len(sql_params) == 0, "Browse mode should have no query parameters"


class TestSQLPathCountQueries:
    """Verify COUNT query SQL paths mirror SELECT queries."""

    def test_count_has_q_no_filter(self, temp_db):
        """COUNT query with text only uses ocr_text_fts JOIN."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="test query", limit=20, offset=0)
        sql, sql_params = engine._build_query(params, is_count=True)

        sql_lower = sql.lower()

        # Verify COUNT structure
        assert "COUNT" in sql.upper(), "COUNT query should use COUNT function"
        assert "ocr_text_fts" in sql_lower, "Should use ocr_text_fts for text search"

    def test_count_no_q_no_filter(self, temp_db):
        """COUNT query in browse mode has no FTS JOINs."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="", limit=20, offset=0)
        sql, sql_params = engine._build_query(params, is_count=True)

        sql_lower = sql.lower()

        # Verify simple COUNT
        assert "COUNT" in sql.upper(), "COUNT query should use COUNT function"
        assert "frames_fts" not in sql_lower, "Browse COUNT should not use frames_fts"
        assert "ocr_text_fts" not in sql_lower, (
            "Browse COUNT should not use ocr_text_fts"
        )


class TestSQLPathEdgeCases:
    """Edge cases for SQL path generation."""

    def test_whitespace_only_query_no_fts(self, temp_db):
        """Whitespace-only query is treated as no query (browse mode)."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Whitespace only should be treated as empty
        params = SearchParams(q="   ", limit=20, offset=0)
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Should behave like browse mode
        assert "ocr_text_fts" not in sql_lower, (
            "Whitespace-only query should not trigger ocr_text_fts JOIN"
        )
        assert "MATCH" not in sql.upper(), (
            "Whitespace query should not have MATCH clause"
        )

    def test_focused_false_triggers_frames_fts(self, temp_db):
        """focused=False is a valid metadata filter triggering frames_fts JOIN."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="", limit=20, offset=0, focused=False)
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Verify frames_fts JOIN for focused filter
        assert "frames_fts" in sql_lower, (
            "focused filter should trigger frames_fts JOIN"
        )
        assert "MATCH" in sql.upper(), "Should have MATCH clause for focused filter"

    def test_time_range_filters_no_fts_impact(self, temp_db):
        """Time range filters don't trigger FTS JOINs by themselves."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(
            q="",
            limit=20,
            offset=0,
            start_time="2026-03-01T00:00:00Z",
            end_time="2026-03-31T23:59:59Z",
        )
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Time filters are WHERE clauses, not FTS
        assert "frames_fts" not in sql_lower, (
            "Time range should not trigger frames_fts JOIN"
        )
        assert "ocr_text_fts" not in sql_lower, (
            "Time range should not trigger ocr_text_fts JOIN"
        )

        # But should have timestamp conditions
        assert "timestamp" in sql_lower, "Should filter by timestamp"

    def test_text_length_filters_no_fts_impact(self, temp_db):
        """Text length filters don't trigger FTS JOINs by themselves."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="", limit=20, offset=0, min_length=100, max_length=1000)
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Text length filters are WHERE clauses on ocr_text, not FTS
        assert "frames_fts" not in sql_lower, (
            "Length filter should not trigger frames_fts JOIN"
        )
        assert "ocr_text_fts" not in sql_lower, (
            "Length filter should not trigger ocr_text_fts JOIN"
        )

        # Should reference text_length
        assert "text_length" in sql_lower, "Should filter by text_length"
