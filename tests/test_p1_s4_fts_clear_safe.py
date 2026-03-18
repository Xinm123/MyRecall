"""FTS clear-safe regression tests — P1-S4.

Tests that when fields are cleared or updated, old FTS tokens
have 0 hits (no stale search results).

Covers:
- frames_fts: app_name, window_name clear/update
- ocr_text_fts: text, app_name, window_name clear/update
- Multi-field simultaneous updates

Per initial_schema.sql triggers: frames_au, ocr_text_update.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.search.engine import SearchEngine


pytestmark = [pytest.mark.integration, pytest.mark.search, pytest.mark.regression]


@pytest.fixture
def temp_db():
    """Create a temporary database with test data for FTS clear-safe testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "clearsafe.db"
        frames_dir = Path(tmpdir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create schema with UPDATE triggers (from initial_schema.sql)
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

            CREATE INDEX IF NOT EXISTS idx_frames_timestamp ON frames(timestamp);
            CREATE INDEX IF NOT EXISTS idx_ocr_text_frame_id ON ocr_text(frame_id);

            -- frames_fts INSERT trigger
            CREATE TRIGGER IF NOT EXISTS frames_ai AFTER INSERT ON frames BEGIN
                INSERT INTO frames_fts(id, app_name, window_name, browser_url, focused, accessibility_text)
                VALUES (NEW.id, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''),
                        COALESCE(NEW.browser_url, ''), COALESCE(NEW.focused, 0), '');
            END;

            -- frames_fts UPDATE trigger (clear-safe: delete old, insert new)
            CREATE TRIGGER IF NOT EXISTS frames_au AFTER UPDATE ON frames BEGIN
                DELETE FROM frames_fts WHERE id = OLD.id;
                INSERT INTO frames_fts(id, app_name, window_name, browser_url, focused, accessibility_text)
                VALUES (NEW.id, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''),
                        COALESCE(NEW.browser_url, ''), COALESCE(NEW.focused, 0), '');
            END;

            -- ocr_text_fts INSERT trigger
            CREATE TRIGGER IF NOT EXISTS ocr_text_ai AFTER INSERT ON ocr_text
            WHEN NEW.text IS NOT NULL AND NEW.text != '' BEGIN
                INSERT INTO ocr_text_fts(frame_id, text, app_name, window_name)
                VALUES (NEW.frame_id, NEW.text, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''));
            END;

            -- ocr_text_fts UPDATE trigger (clear-safe: delete old, conditionally insert new)
            CREATE TRIGGER IF NOT EXISTS ocr_text_update AFTER UPDATE ON ocr_text BEGIN
                DELETE FROM ocr_text_fts WHERE frame_id = OLD.frame_id;
                INSERT INTO ocr_text_fts(frame_id, text, app_name, window_name)
                SELECT NEW.frame_id, NEW.text, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, '')
                WHERE NEW.text IS NOT NULL AND NEW.text != '';
            END;
        """)

        # Insert test frames with OCR
        test_frames = [
            (
                1,
                "capture-001",
                "2026-03-18T10:00:00Z",
                "Safari",
                "Web Browser",
                True,
                "Hello world from Safari",
            ),
            (
                2,
                "capture-002",
                "2026-03-18T11:00:00Z",
                "VSCode",
                "main.py",
                True,
                "def hello(): pass",
            ),
            (
                3,
                "capture-003",
                "2026-03-18T12:00:00Z",
                "Terminal",
                "bash",
                False,
                "git status",
            ),
        ]

        for frame_id, capture_id, ts, app, window, focused, ocr_text in test_frames:
            conn.execute(
                """INSERT INTO frames (id, capture_id, timestamp, app_name, window_name, focused, status, text_source)
                   VALUES (?, ?, ?, ?, ?, ?, 'completed', 'ocr')""",
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


class TestFramesFtsAppNameClear:
    """Test app_name clear/update in frames_fts."""

    def test_update_app_name_old_tokens_zero_results(self, temp_db):
        """Updating app_name removes old tokens from frames_fts."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Verify Safari exists before update
        results, total = engine.search(q="", limit=20, offset=0, app_name="Safari")
        assert total == 1, "Safari should exist before update"

        # Update app_name via SQL
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET app_name = 'Chrome' WHERE id = 1",
            )
            conn.commit()

        # Old app_name "Safari" should return 0 results
        results, total = engine.search(q="", limit=20, offset=0, app_name="Safari")
        assert total == 0, "Safari should have 0 results after update"

        # New app_name "Chrome" should return 1 result
        results, total = engine.search(q="", limit=20, offset=0, app_name="Chrome")
        assert total == 1, "Chrome should have 1 result after update"
        assert results[0]["frame_id"] == 1

    def test_clear_app_name_to_null(self, temp_db):
        """Clearing app_name to NULL removes tokens from frames_fts."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Clear app_name to NULL
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET app_name = NULL WHERE id = 1",
            )
            conn.commit()

        # Safari should return 0 results
        results, total = engine.search(q="", limit=20, offset=0, app_name="Safari")
        assert total == 0, "Safari should have 0 results after clear to NULL"


class TestFramesFtsWindowNameClear:
    """Test window_name clear/update in frames_fts."""

    def test_update_window_name_old_tokens_zero_results(self, temp_db):
        """Updating window_name removes old tokens from frames_fts."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Verify "Web Browser" exists before update
        results, total = engine.search(
            q="", limit=20, offset=0, window_name="Web Browser"
        )
        assert total == 1, "Web Browser should exist before update"

        # Update window_name via SQL
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET window_name = 'Google Search' WHERE id = 1",
            )
            conn.commit()

        # Old window_name should return 0 results
        results, total = engine.search(
            q="", limit=20, offset=0, window_name="Web Browser"
        )
        assert total == 0, "Web Browser should have 0 results after update"

        # New window_name should return 1 result
        results, total = engine.search(
            q="", limit=20, offset=0, window_name="Google Search"
        )
        assert total == 1, "Google Search should have 1 result after update"

    def test_clear_window_name_to_null(self, temp_db):
        """Clearing window_name to NULL removes tokens from frames_fts."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Clear window_name to NULL
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET window_name = NULL WHERE id = 2",
            )
            conn.commit()

        # main.py should return 0 results
        results, total = engine.search(q="", limit=20, offset=0, window_name="main.py")
        assert total == 0, "main.py should have 0 results after clear to NULL"


class TestOcrTextFtsTextClear:
    """Test text clear/update in ocr_text_fts."""

    def test_update_ocr_text_old_tokens_zero_results(self, temp_db):
        """Updating ocr_text removes old tokens from ocr_text_fts."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Verify "Safari" in OCR text exists before update
        results, total = engine.search(q="Safari", limit=20, offset=0)
        assert total >= 1, "Safari should be searchable before update"

        # Update ocr_text via SQL
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE ocr_text SET text = 'Updated content only' WHERE frame_id = 1",
            )
            conn.commit()

        # Old token "Safari" in text should return 0 results (via OCR FTS)
        # Note: Safari also exists in frames.app_name, so we need to verify
        # the OCR text token is gone by checking the text field directly
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'Safari'",
            ).fetchall()
            assert len(rows) == 0, (
                "Safari should have 0 hits in ocr_text_fts after update"
            )

        # New text should be searchable
        results, total = engine.search(q="Updated", limit=20, offset=0)
        assert total >= 1, "Updated should be searchable after update"

    def test_clear_ocr_text_to_empty(self, temp_db):
        """Clearing ocr_text to empty string removes from ocr_text_fts."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Clear text to empty string
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE ocr_text SET text = '' WHERE frame_id = 2",
            )
            conn.commit()

        # Old text "hello" should return 0 results in ocr_text_fts
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'hello'",
            ).fetchall()
            # Note: "hello" might also appear in other frames
            # Check that frame_id 2 is not in results
            frame_ids = {row["frame_id"] for row in rows}
            assert 2 not in frame_ids, (
                "frame_id 2 should not be in ocr_text_fts after clear"
            )

    def test_clear_ocr_text_preserves_other_frames(self, temp_db):
        """Clearing one frame's text does not affect other frames."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Clear frame 1's text
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE ocr_text SET text = '' WHERE frame_id = 1",
            )
            conn.commit()

        # Frame 2 and 3 should still be searchable
        results, total = engine.search(q="hello", limit=20, offset=0)
        # "hello" appears in frame 2's OCR text
        assert total >= 1, "Other frames should still be searchable"

        results, total = engine.search(q="git", limit=20, offset=0)
        # "git" appears in frame 3's OCR text
        assert total >= 1, "Frame 3 should still be searchable"


class TestOcrTextFtsAppNameClear:
    """Test app_name clear/update in ocr_text_fts."""

    def test_update_ocr_app_name_old_tokens_zero_results(self, temp_db):
        """Updating ocr_text.app_name removes old tokens from ocr_text_fts.

        Uses unique app name that only appears in app_name column, not text.
        """
        db_path, frames_dir = temp_db

        # First, set a unique app_name that doesn't appear in text
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE ocr_text SET app_name = 'UniqueAppNameOnly' WHERE frame_id = 1",
            )
            conn.commit()

        # Verify the unique name is searchable
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'UniqueAppNameOnly'",
            ).fetchall()
            assert len(rows) == 1, "Unique app name should be searchable"
            assert rows[0]["frame_id"] == 1

        # Now update to a different app_name
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE ocr_text SET app_name = 'DifferentAppName' WHERE frame_id = 1",
            )
            conn.commit()

        # Old unique app_name should return 0 results for frame 1
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'UniqueAppNameOnly'",
            ).fetchall()
            assert len(rows) == 0, "UniqueAppNameOnly should have 0 hits after update"

            # New app_name should be searchable
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'DifferentAppName'",
            ).fetchall()
            assert len(rows) == 1, "DifferentAppName should be searchable"


class TestOcrTextFtsWindowNameClear:
    """Test window_name clear/update in ocr_text_fts."""

    def test_update_ocr_window_name_old_tokens_zero_results(self, temp_db):
        """Updating ocr_text.window_name removes old tokens from ocr_text_fts.

        Uses unique window name that only appears in window_name column.
        """
        db_path, frames_dir = temp_db

        # First, set a unique window_name that doesn't appear in text
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE ocr_text SET window_name = 'UniqueWindowName' WHERE frame_id = 2",
            )
            conn.commit()

        # Verify the unique name is searchable
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'UniqueWindowName'",
            ).fetchall()
            assert len(rows) == 1, "Unique window name should be searchable"
            assert rows[0]["frame_id"] == 2

        # Now update to a different window_name
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE ocr_text SET window_name = 'DifferentWindowName' WHERE frame_id = 2",
            )
            conn.commit()

        # Old unique window_name should return 0 results for frame 2
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'UniqueWindowName'",
            ).fetchall()
            assert len(rows) == 0, "UniqueWindowName should have 0 hits after update"

            # New window_name should be searchable
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'DifferentWindowName'",
            ).fetchall()
            assert len(rows) == 1, "DifferentWindowName should be searchable"


class TestMultiFieldClear:
    """Test multi-field simultaneous updates."""

    def test_update_multiple_fields_frames(self, temp_db):
        """Updating multiple fields in frames updates FTS atomically."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Update both app_name and window_name
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET app_name = 'NewApp', window_name = 'NewWindow' WHERE id = 1",
            )
            conn.commit()

        # Old values should return 0 results
        results, total = engine.search(q="", limit=20, offset=0, app_name="Safari")
        assert total == 0, "Safari should have 0 results after multi-field update"

        results, total = engine.search(
            q="", limit=20, offset=0, window_name="Web Browser"
        )
        assert total == 0, "Web Browser should have 0 results after multi-field update"

        # New values should be searchable
        results, total = engine.search(q="", limit=20, offset=0, app_name="NewApp")
        assert total == 1, "NewApp should be searchable"

        results, total = engine.search(
            q="", limit=20, offset=0, window_name="NewWindow"
        )
        assert total == 1, "NewWindow should be searchable"

    def test_update_multiple_fields_ocr_text(self, temp_db):
        """Updating multiple fields in ocr_text updates FTS atomically."""
        db_path, frames_dir = temp_db

        # Update text, app_name, and window_name in ocr_text
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """UPDATE ocr_text 
                   SET text = 'New text content', app_name = 'NewApp', window_name = 'NewWindow'
                   WHERE frame_id = 1""",
            )
            conn.commit()

        # Old tokens should return 0 results for frame 1
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            # Check old text
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'Safari'",
            ).fetchall()
            frame_ids = {row["frame_id"] for row in rows}
            assert 1 not in frame_ids, "Frame 1 should not have old text token"

            # Check new text
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'content'",
            ).fetchall()
            frame_ids = {row["frame_id"] for row in rows}
            assert 1 in frame_ids, "Frame 1 should have new text token"

    def test_clear_all_fields_in_frame(self, temp_db):
        """Clearing all searchable fields in a frame removes it from FTS."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Clear all fields in frame 1
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET app_name = NULL, window_name = NULL WHERE id = 1",
            )
            conn.execute(
                "UPDATE ocr_text SET text = '' WHERE frame_id = 1",
            )
            conn.commit()

        # Frame 1 should not appear in app_name/window_name filters
        results, total = engine.search(q="", limit=20, offset=0, app_name="Safari")
        assert total == 0, "Safari filter should return 0 results"

        results, total = engine.search(
            q="", limit=20, offset=0, window_name="Web Browser"
        )
        assert total == 0, "Web Browser filter should return 0 results"

        # Frame 1 should not appear in text search
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE frame_id = 1",
            ).fetchall()
            assert len(rows) == 0, "Frame 1 should have no entries in ocr_text_fts"


class TestFtsClearSafeEdgeCases:
    """Edge cases for FTS clear-safe behavior."""

    def test_update_same_value_no_change(self, temp_db):
        """Updating to the same value keeps FTS intact."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Update to same value
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET app_name = 'Safari' WHERE id = 1",
            )
            conn.commit()

        # Safari should still be searchable
        results, total = engine.search(q="", limit=20, offset=0, app_name="Safari")
        assert total == 1, "Safari should still be searchable after no-change update"

    def test_update_text_from_nonempty_to_nonempty(self, temp_db):
        """Updating text from one non-empty to another non-empty replaces tokens."""
        db_path, frames_dir = temp_db

        # Update text from "git status" to "git commit"
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE ocr_text SET text = 'git commit new feature' WHERE frame_id = 3",
            )
            conn.commit()

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row

            # "status" should be gone
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'status'",
            ).fetchall()
            frame_ids = {row["frame_id"] for row in rows}
            assert 3 not in frame_ids, "'status' should not be in frame 3's FTS"

            # "commit" should exist (was there before, still there)
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'feature'",
            ).fetchall()
            frame_ids = {row["frame_id"] for row in rows}
            assert 3 in frame_ids, "'feature' should be in frame 3's FTS"

    def test_update_to_empty_string_vs_null(self, temp_db):
        """Updating to empty string vs NULL both clear FTS tokens."""
        db_path, frames_dir = temp_db

        # Update frame 1 to empty string
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET app_name = '' WHERE id = 1",
            )
            conn.commit()

        # Update frame 2 to NULL
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET app_name = NULL WHERE id = 2",
            )
            conn.commit()

        # Both should return 0 results
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)
        results, total = engine.search(q="", limit=20, offset=0, app_name="Safari")
        assert total == 0, "Safari should have 0 results"

        results, total = engine.search(q="", limit=20, offset=0, app_name="VSCode")
        assert total == 0, "VSCode should have 0 results"
