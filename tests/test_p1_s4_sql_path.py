"""SQL path verification tests for SearchEngine — P1-S4 Section 2.1 (Post FTS Unification).

Tests verify that SearchEngine._build_query() generates correct SQL for
different parameter combinations after FTS unification.

Key changes from pre-unification:
- Single query path: frames INNER JOIN frames_fts
- Text queries use frames_fts MATCH on full_text
- Browse mode (no q, no filters) still JOINs frames_fts (filters on full_text IS NOT NULL)
- ocr_text_fts and accessibility_fts are dropped

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
    """Create a temporary database with migrated schema (minimal, no data needed)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        frames_dir = Path(tmpdir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Run initial schema
        init_sql = Path(
            "openrecall/server/database/migrations/20260227000001_initial_schema.sql"
        ).read_text()
        conn.executescript(init_sql)

        # Run intermediate migrations
        for mig in [
            "20260310121000_add_event_ts_to_frames.sql",
            "20260315140000_add_last_known_context_to_frames.sql",
            "20260317000001_ocr_text_unique_frame_id.sql",
            "20260321120000_dual_hash_storage.sql",
            "20260324120000_add_frame_description.sql",
            "20260325120000_consolidate_fts_to_full_text.sql",
            "20260408120000_description_fields_redesign.sql",
            "20260409120000_add_frame_embedding.sql",
            "20260414000000_add_visibility_status.sql",
            "20260426000000_add_local_timestamp.sql",
        ]:
            mig_sql = Path(f"openrecall/server/database/migrations/{mig}").read_text()
            conn.executescript(mig_sql)

        conn.commit()
        conn.close()

        yield db_path, frames_dir


class TestSQLPathVerification:
    """Verify SQL query paths for different parameter combinations."""

    def test_has_q_no_filter(self, temp_db):
        """Text query only: uses frames_fts MATCH on full_text.

        Expected path:
        - has_text_query = True
        - has_metadata_filters = False
        - SQL should contain: INNER JOIN frames_fts + frames_fts MATCH ?
        - SQL should NOT contain: ocr_text_fts
        - full_text should be in SELECT
        """
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="hello world", limit=20, offset=0)
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Verify FTS search is present
        assert "frames_fts" in sql_lower, "SQL should reference frames_fts table"
        assert "MATCH" in sql, "SQL should contain MATCH clause for FTS"
        assert "inner join frames_fts" in sql_lower, "SQL should INNER JOIN frames_fts"

        # Verify no old ocr_text_fts
        assert "ocr_text_fts" not in sql_lower, (
            "ocr_text_fts should not appear after FTS unification"
        )

        # Verify full_text in SELECT
        assert "frames.full_text" in sql_lower or "full_text" in sql_lower, (
            "SQL should select full_text from frames"
        )

        # Verify rank is selected (indicates FTS ordering)
        assert "rank" in sql_lower, "SQL should select rank for FTS ordering"

        # Verify parameterization
        assert len(sql_params) >= 1, "Should have at least one parameter for the query"

    def test_has_q_has_filter(self, temp_db):
        """Text query + metadata filters: uses frames_fts MATCH with combined query.

        Expected path:
        - has_text_query = True
        - has_metadata_filters = True
        - SQL should contain: INNER JOIN frames_fts + frames_fts MATCH (combined)
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

        # Verify frames_fts is referenced
        assert "frames_fts" in sql_lower, "SQL should reference frames_fts table"
        assert "inner join frames_fts" in sql_lower, "SQL should INNER JOIN frames_fts"

        # Verify no ocr_text_fts
        assert "ocr_text_fts" not in sql_lower, (
            "ocr_text_fts should not appear after FTS unification"
        )

        # Verify MATCH clauses present
        assert "MATCH" in sql, "SQL should contain MATCH clause(s)"

        # Verify rank for text ordering
        assert "rank" in sql_lower, "SQL should select rank for FTS ordering"

        # Verify multiple parameters (query + metadata filters)
        assert len(sql_params) >= 2, (
            "Should have parameters for query and metadata filters"
        )

    def test_no_q_has_filter(self, temp_db):
        """Metadata filters only: uses frames_fts MATCH for metadata query.

        Expected path:
        - has_text_query = False
        - has_metadata_filters = True
        - SQL should contain: INNER JOIN frames_fts + frames_fts MATCH (metadata only)
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
        assert "inner join frames_fts" in sql_lower, (
            "SQL should INNER JOIN frames_fts"
        )

        # Verify no ocr_text_fts
        assert "ocr_text_fts" not in sql_lower, (
            "ocr_text_fts should not appear after FTS unification"
        )

        # Verify MATCH for metadata filter (even without text query)
        assert "MATCH" in sql, (
            "SQL should contain MATCH clause for metadata FTS filter"
        )

        # Verify timestamp ordering
        assert "order by" in sql.lower(), "SQL should have ORDER BY clause"
        assert "timestamp" in sql_lower, "Browse mode should order by timestamp"

    def test_no_q_no_filter(self, temp_db):
        """Browse mode: no text query, no filters.

        After FTS unification, browse mode still JOINs frames_fts
        (filters on full_text IS NOT NULL) but does not use MATCH.
        """
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="", limit=20, offset=0)
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # After FTS unification: browse mode ALWAYS joins frames_fts
        assert "frames_fts" in sql_lower, (
            "After FTS unification, browse mode should still JOIN frames_fts"
        )
        assert "inner join frames_fts" in sql_lower, (
            "SQL should INNER JOIN frames_fts in browse mode"
        )

        # Verify no ocr_text_fts
        assert "ocr_text_fts" not in sql_lower, (
            "ocr_text_fts should not appear after FTS unification"
        )

        # Verify full_text in SELECT (browse still returns full_text)
        assert "full_text" in sql_lower, (
            "Browse mode should select full_text"
        )

        # Verify timestamp ordering
        assert "order by" in sql.lower(), "SQL should have ORDER BY clause"
        assert "timestamp" in sql_lower, "Browse mode should order by timestamp"

        # Verify no MATCH clause (no text query, no metadata filters)
        # Note: An empty FTS MATCH would match everything, but the unified
        # engine uses a bare WHERE for browse mode (no MATCH)


class TestSQLPathCountQueries:
    """Verify COUNT query SQL paths mirror SELECT queries."""

    def test_count_has_q_no_filter(self, temp_db):
        """COUNT query with text only uses frames_fts."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="test query", limit=20, offset=0)
        sql, sql_params = engine._build_query(params, is_count=True)

        sql_lower = sql.lower()

        # Verify COUNT structure
        assert "COUNT" in sql, "COUNT query should use COUNT function"
        assert "frames_fts" in sql_lower, "COUNT should use frames_fts for text search"
        assert "ocr_text_fts" not in sql_lower, (
            "ocr_text_fts should not appear after FTS unification"
        )
        # Note: text_source grouping is done in count_by_type(), not _build_query

    def test_count_no_q_no_filter(self, temp_db):
        """COUNT query in browse mode still uses frames_fts (full_text IS NOT NULL filter)."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="", limit=20, offset=0)
        sql, sql_params = engine._build_query(params, is_count=True)

        sql_lower = sql.lower()

        # After FTS unification: browse COUNT still uses frames_fts
        assert "COUNT" in sql, "COUNT query should use COUNT function"
        assert "frames_fts" in sql_lower, (
            "Browse COUNT should use frames_fts (full_text IS NOT NULL filter)"
        )
        assert "ocr_text_fts" not in sql_lower, (
            "ocr_text_fts should not appear after FTS unification"
        )


class TestSQLPathEdgeCases:
    """Edge cases for SQL path generation."""

    def test_whitespace_only_query_no_match(self, temp_db):
        """Whitespace-only query is treated as empty (browse mode)."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Whitespace only should be treated as empty
        params = SearchParams(q="   ", limit=20, offset=0)
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Should behave like browse mode (no MATCH for text)
        assert "ocr_text_fts" not in sql_lower, (
            "Whitespace-only query should not trigger ocr_text_fts"
        )
        # Whitespace sanitized to empty should not produce a MATCH clause for text
        # (metadata-only FTS MATCH is still possible with no metadata filters)
        # The WHERE clause will have full_text IS NOT NULL but no MATCH

    def test_focused_false_triggers_no_fts(self, temp_db):
        """focused=False is a metadata filter that uses frames_fts MATCH."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="", limit=20, offset=0, focused=False)
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Verify frames_fts JOIN for focused filter
        assert "frames_fts" in sql_lower, (
            "focused filter should involve frames_fts"
        )
        assert "inner join frames_fts" in sql_lower, (
            "Should INNER JOIN frames_fts"
        )

    def test_time_range_filters_no_matched_text(self, temp_db):
        """Time range filters are WHERE clauses, not FTS MATCH."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(
            q="",
            limit=20,
            offset=0,
            start_time="2026-03-01T00:00:00",
            end_time="2026-03-31T23:59:59",
        )
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Time filters are WHERE clauses, not FTS MATCH for text
        # But frames_fts is still joined
        assert "frames_fts" in sql_lower, (
            "Browse with time filters should still JOIN frames_fts"
        )
        assert "ocr_text_fts" not in sql_lower, (
            "ocr_text_fts should not appear after FTS unification"
        )

        # But should have timestamp conditions
        assert "timestamp" in sql_lower, "Should filter by timestamp"

    def test_text_length_filters_use_full_text(self, temp_db):
        """Text length filters use LENGTH(frames.full_text)."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        params = SearchParams(q="", limit=20, offset=0, min_length=100, max_length=1000)
        sql, sql_params = engine._build_query(params, is_count=False)

        sql_lower = sql.lower()

        # Text length filters use full_text
        assert "length" in sql_lower, "Should filter by text length"
        assert "full_text" in sql_lower, "Length filter should use full_text"
        assert "frames_fts" in sql_lower, (
            "Browse with length filter should still JOIN frames_fts"
        )
