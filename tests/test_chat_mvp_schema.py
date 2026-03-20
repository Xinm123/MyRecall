"""
Chat MVP Schema Tests

Validates that the database schema matches the MVP shape defined in docs/v3/chat/mvp.md.

Phase 1 Exit Criteria:
- frames table has 'text' and 'accessibility_tree_json', no 'accessibility_text'
- frames_fts is metadata-only (no accessibility_text)
- accessibility table has required frame_id and text_length, no 'focused'
- elements table exists with all required columns
"""

import pytest
import sqlite3
from pathlib import Path


def get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Get column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def get_required_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Get NOT NULL columns for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall() if row[3] != 0}  # notnull == 1


def get_fts_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Get columns indexed by FTS table (excluding UNINDEXED)."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = set()
    for row in cursor.fetchall():
        col_name = row[1]
        # FTS5 stores column definitions in the schema, UNINDEXED columns are marked
        columns.add(col_name)
    return columns


def get_fts_indexed_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """
    Get only the indexed columns from FTS table (excluding UNINDEXED).
    FTS5 schema format: col_name, col_name UNINDEXED
    We need to parse the CREATE TABLE statement.
    """
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    row = cursor.fetchone()
    if not row or not row[0]:
        return set()

    sql = row[0]
    # Extract content between USING fts5(...)
    import re
    match = re.search(r'USING fts5\(([^)]+)\)', sql, re.IGNORECASE)
    if not match:
        return set()

    columns_str = match.group(1)
    indexed = set()
    for col_def in columns_str.split(','):
        col_def = col_def.strip()
        # Skip tokenize options (they contain '=')
        if '=' in col_def:
            continue
        if ' UNINDEXED' not in col_def.upper():
            # This column is indexed
            indexed.add(col_def.split()[0])  # Get just the column name
    return indexed


@pytest.fixture
def sqlite_conn():
    """Create an in-memory SQLite database with migrations applied."""
    conn = sqlite3.connect(":memory:")

    # Find and apply migrations
    migrations_dir = Path(__file__).parent.parent / "openrecall" / "server" / "database" / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    for mf in migration_files:
        sql = mf.read_text()
        conn.executescript(sql)

    yield conn
    conn.close()


class TestFramesTable:
    """Tests for frames table MVP shape."""

    def test_frames_has_text_column(self, sqlite_conn):
        """frames.text must exist for unified text storage."""
        cols = get_table_columns(sqlite_conn, "frames")
        assert "text" in cols, "frames.text column is required for MVP"

    def test_frames_has_accessibility_tree_json(self, sqlite_conn):
        """frames.accessibility_tree_json must exist for storing raw accessibility data."""
        cols = get_table_columns(sqlite_conn, "frames")
        assert "accessibility_tree_json" in cols, "frames.accessibility_tree_json is required for MVP"

    def test_frames_no_accessibility_text(self, sqlite_conn):
        """frames.accessibility_text must be removed (moved to accessibility table)."""
        cols = get_table_columns(sqlite_conn, "frames")
        assert "accessibility_text" not in cols, "frames.accessibility_text should be removed in MVP"

    def test_frames_retains_text_source(self, sqlite_conn):
        """frames.text_source must exist to indicate text origin."""
        cols = get_table_columns(sqlite_conn, "frames")
        assert "text_source" in cols, "frames.text_source must be retained"

    def test_frames_retains_content_hash(self, sqlite_conn):
        """frames.content_hash must exist for deduplication."""
        cols = get_table_columns(sqlite_conn, "frames")
        assert "content_hash" in cols, "frames.content_hash must be retained"

    def test_frames_retains_simhash(self, sqlite_conn):
        """frames.simhash must exist for near-duplicate detection."""
        cols = get_table_columns(sqlite_conn, "frames")
        assert "simhash" in cols, "frames.simhash must be retained"


class TestFramesFts:
    """Tests for frames_fts MVP shape."""

    def test_frames_fts_is_metadata_only(self, sqlite_conn):
        """frames_fts should only index metadata fields, not text content."""
        indexed = get_fts_indexed_columns(sqlite_conn, "frames_fts")
        expected = {"app_name", "window_name", "browser_url", "focused", "id"}
        # Allow for id being UNINDEXED (common pattern)
        assert indexed == expected or indexed == {"app_name", "window_name", "browser_url", "focused"}, \
            f"frames_fts should only index metadata, got: {indexed}"

    def test_frames_fts_no_accessibility_text(self, sqlite_conn):
        """frames_fts should not index accessibility_text."""
        cols = get_table_columns(sqlite_conn, "frames_fts")
        assert "accessibility_text" not in cols, "frames_fts should not have accessibility_text column"


class TestAccessibilityTable:
    """Tests for accessibility table MVP shape."""

    def test_accessibility_has_frame_id(self, sqlite_conn):
        """accessibility.frame_id must exist."""
        cols = get_table_columns(sqlite_conn, "accessibility")
        assert "frame_id" in cols, "accessibility.frame_id is required"

    def test_accessibility_frame_id_required(self, sqlite_conn):
        """accessibility.frame_id must be NOT NULL in MVP."""
        required = get_required_columns(sqlite_conn, "accessibility")
        assert "frame_id" in required, "accessibility.frame_id should be NOT NULL in MVP"

    def test_accessibility_has_text_length(self, sqlite_conn):
        """accessibility.text_length must exist for efficient text size queries."""
        cols = get_table_columns(sqlite_conn, "accessibility")
        assert "text_length" in cols, "accessibility.text_length is required for MVP"

    def test_accessibility_fts_indexes_browser_url(self, sqlite_conn):
        """accessibility_fts must index browser_url for URL-based search."""
        indexed = get_fts_indexed_columns(sqlite_conn, "accessibility_fts")
        assert "browser_url" in indexed, "accessibility_fts should index browser_url"

    def test_accessibility_no_focused(self, sqlite_conn):
        """accessibility.focused should be removed (focused is per-frame, not per-accessibility)."""
        cols = get_table_columns(sqlite_conn, "accessibility")
        assert "focused" not in cols, "accessibility.focused should be removed in MVP"


class TestElementsTable:
    """Tests for elements table MVP shape."""

    def test_elements_table_exists(self, sqlite_conn):
        """elements table must exist for storing individual accessibility elements."""
        cursor = sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='elements'"
        )
        assert cursor.fetchone() is not None, "elements table must exist in MVP"

    def test_elements_has_source(self, sqlite_conn):
        """elements.source must exist to indicate data origin."""
        cols = get_table_columns(sqlite_conn, "elements")
        assert "source" in cols, "elements.source is required"

    def test_elements_has_role(self, sqlite_conn):
        """elements.role must exist for accessibility role (button, text, etc.)."""
        cols = get_table_columns(sqlite_conn, "elements")
        assert "role" in cols, "elements.role is required"

    def test_elements_has_text(self, sqlite_conn):
        """elements.text must exist for element text content."""
        cols = get_table_columns(sqlite_conn, "elements")
        assert "text" in cols, "elements.text is required"

    def test_elements_has_parent_id(self, sqlite_conn):
        """elements.parent_id must exist for tree structure."""
        cols = get_table_columns(sqlite_conn, "elements")
        assert "parent_id" in cols, "elements.parent_id is required for hierarchy"

    def test_elements_has_depth(self, sqlite_conn):
        """elements.depth must exist for tree depth tracking."""
        cols = get_table_columns(sqlite_conn, "elements")
        assert "depth" in cols, "elements.depth is required"

    def test_elements_has_bounds(self, sqlite_conn):
        """elements must have bounds fields for spatial queries."""
        cols = get_table_columns(sqlite_conn, "elements")
        assert "left_bound" in cols, "elements.left_bound is required"
        assert "top_bound" in cols, "elements.top_bound is required"
        assert "width_bound" in cols, "elements.width_bound is required"
        assert "height_bound" in cols, "elements.height_bound is required"

    def test_elements_has_sort_order(self, sqlite_conn):
        """elements.sort_order must exist for ordering elements within a frame."""
        cols = get_table_columns(sqlite_conn, "elements")
        assert "sort_order" in cols, "elements.sort_order is required"

    def test_elements_frame_id_required(self, sqlite_conn):
        """elements.frame_id must be NOT NULL."""
        required = get_required_columns(sqlite_conn, "elements")
        assert "frame_id" in required, "elements.frame_id should be NOT NULL"

    def test_elements_frame_id_foreign_key(self, sqlite_conn):
        """elements.frame_id should reference frames.id with CASCADE delete."""
        cursor = sqlite_conn.execute("PRAGMA foreign_key_list(elements)")
        fks = cursor.fetchall()
        # Check that there's a FK to frames
        fk_targets = [(fk[2], fk[3], fk[4]) for fk in fks]  # table, from, to
        assert any(t[0] == "frames" and t[1] == "frame_id" and t[2] == "id" for t in fk_targets), \
            "elements.frame_id should reference frames(id)"


class TestTriggers:
    """Tests for trigger behavior."""

    def test_frames_insert_trigger_exists(self, sqlite_conn):
        """frames_ai trigger should exist for FTS sync."""
        cursor = sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='frames_ai'"
        )
        assert cursor.fetchone() is not None, "frames_ai trigger must exist"

    def test_frames_update_trigger_exists(self, sqlite_conn):
        """frames_au trigger should exist for FTS sync."""
        cursor = sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='frames_au'"
        )
        assert cursor.fetchone() is not None, "frames_au trigger must exist"

    def test_frames_delete_trigger_exists(self, sqlite_conn):
        """frames_ad trigger should exist for FTS cleanup."""
        cursor = sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='frames_ad'"
        )
        assert cursor.fetchone() is not None, "frames_ad trigger must exist"
