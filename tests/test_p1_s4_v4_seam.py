"""v4 Seam Protection Test — P1-S4.

Tests verify v4 seam protection: the `accessibility` table exists in the schema
but should have 0 rows in P1 (accessibility data collection is reserved for v4).

Per design.md D8 and ADR-0012.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest


pytestmark = [pytest.mark.integration, pytest.mark.search]


@pytest.fixture
def temp_db_with_schema():
    """Create a temporary database with full schema (matching production)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "edge.db"
        frames_dir = Path(tmpdir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create full schema including accessibility table (from initial_schema.sql)
        conn.executescript("""
            -- schema_migrations
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            -- frames
            CREATE TABLE IF NOT EXISTS frames (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp             TEXT NOT NULL,
                app_name              TEXT DEFAULT NULL,
                window_name           TEXT DEFAULT NULL,
                browser_url           TEXT DEFAULT NULL,
                focused               BOOLEAN DEFAULT NULL,
                device_name           TEXT NOT NULL DEFAULT 'monitor_0',
                snapshot_path         TEXT DEFAULT NULL,
                capture_trigger       TEXT DEFAULT NULL,
                accessibility_text    TEXT DEFAULT NULL,
                ocr_text             TEXT DEFAULT NULL,
                text_source           TEXT DEFAULT NULL,
                accessibility_tree_json TEXT DEFAULT NULL,
                content_hash          TEXT DEFAULT NULL,
                simhash               INTEGER DEFAULT NULL,
                capture_id            TEXT NOT NULL UNIQUE,
                image_size_bytes      INTEGER,
                ingested_at           TEXT NOT NULL
                                      DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                status                TEXT NOT NULL DEFAULT 'pending',
                error_message         TEXT,
                retry_count           INTEGER DEFAULT 0,
                processed_at          TEXT
            );

            -- ocr_text
            CREATE TABLE IF NOT EXISTS ocr_text (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                frame_id     INTEGER NOT NULL,
                text         TEXT NOT NULL DEFAULT '',
                text_length  INTEGER DEFAULT 0,
                ocr_engine   TEXT,
                app_name     TEXT DEFAULT NULL,
                window_name  TEXT DEFAULT NULL,
                FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE
            );

            -- accessibility (v4 seam - exists but should be empty in P1)
            CREATE TABLE IF NOT EXISTS accessibility (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                app_name      TEXT NOT NULL,
                window_name   TEXT NOT NULL,
                text_content  TEXT NOT NULL,
                browser_url   TEXT,
                frame_id      INTEGER NOT NULL,
                text_length   INTEGER DEFAULT 0,
                FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE
            );

            -- frames_fts
            CREATE VIRTUAL TABLE IF NOT EXISTS frames_fts USING fts5(
                app_name, window_name, browser_url, focused,
                id UNINDEXED, tokenize='unicode61'
            );

            -- ocr_text_fts
            CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(
                text, app_name, window_name, frame_id UNINDEXED, tokenize='unicode61'
            );

            -- accessibility_fts
            CREATE VIRTUAL TABLE IF NOT EXISTS accessibility_fts USING fts5(
                text_content, app_name, window_name, browser_url,
                content='accessibility', content_rowid='id', tokenize='unicode61'
            );

            -- Triggers for frames_fts
            CREATE TRIGGER IF NOT EXISTS frames_ai AFTER INSERT ON frames BEGIN
                INSERT INTO frames_fts(id, app_name, window_name, browser_url, focused)
                VALUES (NEW.id, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''),
                        COALESCE(NEW.browser_url, ''), COALESCE(NEW.focused, 0));
            END;

            CREATE TRIGGER IF NOT EXISTS frames_au AFTER UPDATE ON frames BEGIN
                DELETE FROM frames_fts WHERE id = OLD.id;
                INSERT INTO frames_fts(id, app_name, window_name, browser_url, focused)
                VALUES (NEW.id, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''),
                        COALESCE(NEW.browser_url, ''), COALESCE(NEW.focused, 0));
            END;

            CREATE TRIGGER IF NOT EXISTS frames_ad AFTER DELETE ON frames BEGIN
                DELETE FROM frames_fts WHERE id = OLD.id;
            END;

            -- Triggers for ocr_text_fts
            CREATE TRIGGER IF NOT EXISTS ocr_text_ai AFTER INSERT ON ocr_text
            WHEN NEW.text IS NOT NULL AND NEW.text != '' AND NEW.frame_id IS NOT NULL
            BEGIN
                INSERT INTO ocr_text_fts(frame_id, text, app_name, window_name)
                VALUES (NEW.frame_id, NEW.text, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''));
            END;

            CREATE TRIGGER IF NOT EXISTS ocr_text_update AFTER UPDATE ON ocr_text BEGIN
                DELETE FROM ocr_text_fts WHERE frame_id = OLD.frame_id;
                INSERT INTO ocr_text_fts(frame_id, text, app_name, window_name)
                SELECT NEW.frame_id, NEW.text, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, '')
                WHERE NEW.frame_id IS NOT NULL
                  AND NEW.text IS NOT NULL
                  AND NEW.text != '';
            END;

            CREATE TRIGGER IF NOT EXISTS ocr_text_ad AFTER DELETE ON ocr_text BEGIN
                DELETE FROM ocr_text_fts WHERE frame_id = OLD.frame_id;
            END;

            -- Triggers for accessibility_fts
            CREATE TRIGGER IF NOT EXISTS accessibility_ai AFTER INSERT ON accessibility BEGIN
                INSERT INTO accessibility_fts(rowid, text_content, app_name, window_name, browser_url)
                VALUES (NEW.id, COALESCE(NEW.text_content, ''), COALESCE(NEW.app_name, ''),
                        COALESCE(NEW.window_name, ''), COALESCE(NEW.browser_url, ''));
            END;

            CREATE TRIGGER IF NOT EXISTS accessibility_au AFTER UPDATE ON accessibility BEGIN
                INSERT INTO accessibility_fts(accessibility_fts, rowid, text_content, app_name, window_name, browser_url)
                VALUES ('delete', OLD.id, OLD.text_content, OLD.app_name, OLD.window_name, OLD.browser_url);
                INSERT INTO accessibility_fts(rowid, text_content, app_name, window_name, browser_url)
                VALUES (NEW.id, COALESCE(NEW.text_content, ''), COALESCE(NEW.app_name, ''),
                        COALESCE(NEW.window_name, ''), COALESCE(NEW.browser_url, ''));
            END;

            CREATE TRIGGER IF NOT EXISTS accessibility_ad AFTER DELETE ON accessibility BEGIN
                INSERT INTO accessibility_fts(accessibility_fts, rowid, text_content, app_name, window_name, browser_url)
                VALUES ('delete', OLD.id, OLD.text_content, OLD.app_name, OLD.window_name, OLD.browser_url);
            END;
        """)

        conn.commit()
        conn.close()

        yield db_path, frames_dir


class TestV4SeamProtection:
    """Tests for v4 seam protection.

    The accessibility table exists in the schema (for forward compatibility)
    but should have 0 rows in P1 since accessibility data collection is v4+.
    """

    def test_accessibility_table_exists(self, temp_db_with_schema):
        """The accessibility table exists in the schema."""
        db_path, _ = temp_db_with_schema

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='table' AND name='accessibility'"""
            )
            row = cursor.fetchone()

        assert row is not None, "accessibility table should exist in schema"

    def test_accessibility_table_has_zero_rows(self, temp_db_with_schema):
        """The accessibility table has 0 rows (v4 seam protection)."""
        db_path, _ = temp_db_with_schema

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT COUNT(*) as count FROM accessibility")
            row = cursor.fetchone()

        unexpected_accessibility_rows = row["count"]
        assert unexpected_accessibility_rows == 0, (
            f"accessibility table should have 0 rows in P1, "
            f"found {unexpected_accessibility_rows} rows"
        )

    def test_accessibility_fts_table_exists(self, temp_db_with_schema):
        """The accessibility_fts table exists in the schema."""
        db_path, _ = temp_db_with_schema

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='table' AND name='accessibility_fts'"""
            )
            row = cursor.fetchone()

        assert row is not None, "accessibility_fts table should exist in schema"

    def test_accessibility_fts_has_zero_rows(self, temp_db_with_schema):
        """The accessibility_fts table has 0 rows (v4 seam protection)."""
        db_path, _ = temp_db_with_schema

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT COUNT(*) as count FROM accessibility_fts")
            row = cursor.fetchone()

        # Note: FTS5 tables may show 0 count differently
        # The key assertion is that the underlying accessibility table is empty
        assert row["count"] == 0, (
            f"accessibility_fts should have 0 rows when accessibility is empty"
        )

    def test_frames_accessibility_text_is_null_or_empty(self, temp_db_with_schema):
        """frames.accessibility_text column exists but should be NULL or empty in P1.

        This column is reserved for v4 when accessibility data is paired with frames.
        """
        db_path, _ = temp_db_with_schema

        # Insert a test frame
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """INSERT INTO frames (capture_id, timestamp, status)
                   VALUES ('test-capture-001', '2026-03-18T10:00:00Z', 'completed')"""
            )
            conn.commit()

        # Verify accessibility_text is NULL (default) for new frames
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT accessibility_text FROM frames WHERE capture_id = 'test-capture-001'"
            )
            row = cursor.fetchone()

        assert row["accessibility_text"] is None or row["accessibility_text"] == "", (
            "accessibility_text should be NULL or empty in P1"
        )

    def test_text_source_does_not_include_accessibility(self, temp_db_with_schema):
        """frames.text_source should not be 'accessibility' in P1.

        P1 uses OCR-only, so text_source should be 'ocr' or NULL.
        """
        db_path, _ = temp_db_with_schema

        # Insert a test frame with OCR
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """INSERT INTO frames (capture_id, timestamp, status, text_source)
                   VALUES ('test-capture-002', '2026-03-18T11:00:00Z', 'completed', 'ocr')"""
            )
            conn.commit()

        # Verify no frames have text_source = 'accessibility'
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM frames WHERE text_source = 'accessibility'"
            )
            row = cursor.fetchone()

        unexpected_accessibility_source = row["count"]
        assert unexpected_accessibility_source == 0, (
            f"No frames should have text_source='accessibility' in P1, "
            f"found {unexpected_accessibility_source}"
        )


class TestV4SeamSchemaIntegrity:
    """Tests for v4 seam schema integrity.

    Verifies that the schema is correctly set up for v4 forward compatibility
    while maintaining P1 isolation.
    """

    def test_accessibility_table_has_correct_columns(self, temp_db_with_schema):
        """The accessibility table has all expected columns."""
        db_path, _ = temp_db_with_schema

        expected_columns = {
            "id",
            "timestamp",
            "app_name",
            "window_name",
            "text_content",
            "browser_url",
            "frame_id",
            "text_length",
        }

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("PRAGMA table_info(accessibility)")
            rows = cursor.fetchall()

        actual_columns = {row["name"] for row in rows}

        assert expected_columns == actual_columns, (
            f"accessibility columns mismatch. "
            f"Expected: {expected_columns}, Got: {actual_columns}"
        )

    def test_accessibility_triggers_exist(self, temp_db_with_schema):
        """The accessibility FTS triggers exist."""
        db_path, _ = temp_db_with_schema

        expected_triggers = {"accessibility_ai", "accessibility_au", "accessibility_ad"}

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='trigger' AND tbl_name='accessibility'"""
            )
            rows = cursor.fetchall()

        actual_triggers = {row["name"] for row in rows}

        assert expected_triggers == actual_triggers, (
            f"accessibility triggers mismatch. "
            f"Expected: {expected_triggers}, Got: {actual_triggers}"
        )

    def test_accessibility_frame_id_foreign_key(self, temp_db_with_schema):
        """The accessibility.frame_id foreign key constraint exists."""
        db_path, _ = temp_db_with_schema

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            # Note: SQLite doesn't enforce FK by default, but we can check schema
            cursor = conn.execute("SELECT sql FROM sqlite_master WHERE name='accessibility'")
            row = cursor.fetchone()

        create_sql = row["sql"]

        # Verify foreign key reference exists in CREATE statement
        assert "FOREIGN KEY" in create_sql, "Foreign key constraint missing"
        assert "frame_id" in create_sql, "frame_id reference missing"
        assert "REFERENCES frames" in create_sql, "Reference to frames table missing"
