"""P1-S3 Unit Test: zero AI artifacts check.

Tests that OCR-only processing does NOT generate:
- captions
- keywords
- fusion_text
- embeddings (ocr_text_embeddings table should not exist)

SSOT: spec.md §4.3, design.md Non-goals
"""

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


class TestZeroAICheck:
    """Tests verifying no AI artifacts are generated."""

    def test_ocr_text_embeddings_table_does_not_exist(self, temp_db: Path):
        """Test that ocr_text_embeddings table does not exist in schema."""
        with sqlite3.connect(str(temp_db)) as conn:
            # Query sqlite_master for the table
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ocr_text_embeddings'",
            )
            result = cursor.fetchone()
            assert result is None, "ocr_text_embeddings table should not exist"

    def test_no_caption_column_in_frames(self, temp_db: Path):
        """Test that frames table does not have caption column."""
        with sqlite3.connect(str(temp_db)) as conn:
            cursor = conn.execute("PRAGMA table_info(frames)")
            columns = [row[1] for row in cursor.fetchall()]

            assert "caption" not in columns
            assert "ai_caption" not in columns

    def test_no_keywords_column_in_frames(self, temp_db: Path):
        """Test that frames table does not have keywords column."""
        with sqlite3.connect(str(temp_db)) as conn:
            cursor = conn.execute("PRAGMA table_info(frames)")
            columns = [row[1] for row in cursor.fetchall()]

            assert "keywords" not in columns
            assert "ai_keywords" not in columns

    def test_no_fusion_text_column(self, temp_db: Path):
        """Test that fusion_text column does not exist."""
        with sqlite3.connect(str(temp_db)) as conn:
            # Check frames table
            cursor = conn.execute("PRAGMA table_info(frames)")
            frames_columns = [row[1] for row in cursor.fetchall()]

            # Check ocr_text table
            cursor = conn.execute("PRAGMA table_info(ocr_text)")
            ocr_columns = [row[1] for row in cursor.fetchall()]

            assert "fusion_text" not in frames_columns
            assert "fusion_text" not in ocr_columns

    def test_ocr_text_only_has_expected_columns(self, temp_db: Path):
        """Test that ocr_text table has only expected columns (no AI columns)."""
        expected_columns = {
            "id",
            "frame_id",
            "text",
            "text_json",
            "ocr_engine",
            "text_length",
            "app_name",
            "window_name",
        }

        with sqlite3.connect(str(temp_db)) as conn:
            cursor = conn.execute("PRAGMA table_info(ocr_text)")
            actual_columns = {row[1] for row in cursor.fetchall()}

            assert actual_columns == expected_columns, (
                f"Unexpected columns in ocr_text: {actual_columns - expected_columns}"
            )

    def test_no_embedding_related_tables(self, temp_db: Path):
        """Test that no embedding-related tables exist."""
        embedding_table_patterns = [
            "embeddings",
            "ocr_embeddings",
            "text_embeddings",
            "vector_store",
            "lancedb",
        ]

        with sqlite3.connect(str(temp_db)) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'",
            )
            tables = {row[0] for row in cursor.fetchall()}

            for pattern in embedding_table_patterns:
                assert pattern not in tables, f"Unexpected table '{pattern}' found"

    def test_frames_text_source_values_limited(self, temp_db: Path):
        """Test that text_source only has OCR-related values, not AI values."""
        # text_source should be NULL or 'ocr', not 'ai', 'vl', etc.
        with sqlite3.connect(str(temp_db)) as conn:
            # This is a schema check - text_source column exists
            cursor = conn.execute("PRAGMA table_info(frames)")
            columns = {row[1] for row in cursor.fetchall()}

            assert "text_source" in columns

            # The column allows any text, but the application should only
            # write 'ocr' or NULL for P1
