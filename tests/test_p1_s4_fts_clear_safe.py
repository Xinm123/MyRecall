"""FTS clear-safe regression tests — P1-S4 (Post FTS Unification).

Tests that when fields are cleared or updated, old FTS tokens
have 0 hits (no stale search results).

Covers post-unification:
- frames_fts: full_text, app_name, window_name, browser_url clear/update
- Single unified FTS index (dropped ocr_text_fts and accessibility_fts)

Per 20260325120000_consolidate_fts_to_full_text.sql triggers: frames_au.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.search.engine import SearchEngine


pytestmark = [pytest.mark.integration, pytest.mark.search, pytest.mark.regression]


@pytest.fixture
def temp_db():
    """Create a temporary database with migrated schema and test data.

    Uses the actual migrations for correct post-FTS-unification schema.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "clearsafe.db"
        frames_dir = Path(tmpdir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Use actual migrations for correct schema
        init_sql = Path(
            "openrecall/server/database/migrations/20260227000001_initial_schema.sql"
        ).read_text()
        conn.executescript(init_sql)

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

        # Insert test frames with full_text populated (post-migration schema)
        # timestamp is UTC (with Z), local_timestamp is local time (UTC+8, no Z)
        from openrecall.server.database.frames_store import _utc_to_local_timestamp
        test_frames = [
            (1, "capture-001", "2026-03-18T10:00:00Z", "Safari", "Web Browser", True, "Hello world from Safari"),
            (2, "capture-002", "2026-03-18T11:00:00Z", "VSCode", "main.py", True, "def hello(): pass"),
            (3, "capture-003", "2026-03-18T12:00:00Z", "Terminal", "bash", False, "git status"),
        ]

        for frame_id, capture_id, ts, app, window, focused, full_text in test_frames:
            local_ts = _utc_to_local_timestamp(ts)
            conn.execute(
                """INSERT INTO frames (id, capture_id, timestamp, local_timestamp, app_name, window_name, focused, status, text_source, full_text, visibility_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', 'ocr', ?, 'queryable')""",
                (frame_id, capture_id, ts, local_ts, app, window, focused, full_text),
            )

        conn.commit()
        conn.close()

        yield db_path, frames_dir


class TestFramesFtsFullTextClear:
    """Test full_text clear/update in frames_fts (post-unification)."""

    def test_update_full_text_old_tokens_zero_results(self, temp_db):
        """Updating full_text removes old tokens from frames_fts."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Verify "world" (in full_text only, not in app_name) exists before update
        results, total = engine.search(q="world", limit=20, offset=0)
        assert total >= 1, "world should be searchable before update"

        # Update full_text via SQL
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = 'Updated content only' WHERE id = 1",
            )
            conn.commit()

        # Old token "world" (only in old full_text) should return 0 results
        results, total = engine.search(q="world", limit=20, offset=0)
        assert total == 0, "world should have 0 results after full_text update"

        # New text should be searchable
        results, total = engine.search(q="Updated", limit=20, offset=0)
        assert total >= 1, "Updated should be searchable after update"

    def test_clear_full_text_to_empty_removes_from_fts(self, temp_db):
        """Clearing full_text to empty removes from frames_fts."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Verify "hello" is searchable
        results, total = engine.search(q="hello", limit=20, offset=0)
        assert total >= 1, "hello should be searchable before clear"

        # Clear full_text to empty string
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = '' WHERE id = 2",
            )
            conn.commit()

        # "hello" should not appear for frame 2 in FTS
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE id = 2",
            ).fetchall()
            assert len(rows) == 0, (
                "Frame 2 should have no entry in frames_fts after clearing full_text"
            )

    def test_clear_full_text_preserves_other_frames(self, temp_db):
        """Clearing one frame's full_text does not affect other frames."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Clear frame 1's full_text
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = '' WHERE id = 1",
            )
            conn.commit()

        # Frame 2 and 3 should still be searchable
        results, total = engine.search(q="hello", limit=20, offset=0)
        assert total >= 1, "Frame 2 should still be searchable"

        results, total = engine.search(q="git", limit=20, offset=0)
        assert total >= 1, "Frame 3 should still be searchable"


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


class TestMultiFieldClear:
    """Test multi-field simultaneous updates."""

    def test_update_multiple_fields_atomically(self, temp_db):
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

    def test_clear_all_fields_removes_from_fts(self, temp_db):
        """Clearing full_text removes frame from frames_fts (no other fields indexed for text)."""
        db_path, frames_dir = temp_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # Clear full_text for frame 1
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = '' WHERE id = 1",
            )
            conn.commit()

        # Frame 1 should not appear in text search
        results, total = engine.search(q="Safari", limit=20, offset=0)
        assert total == 0, "Frame 1 should not be in search results after clearing full_text"


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

    def test_update_full_text_from_nonempty_to_nonempty(self, temp_db):
        """Updating full_text from one non-empty to another replaces tokens."""
        db_path, frames_dir = temp_db

        # Update text from "git status" to "git commit"
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = 'git commit new feature' WHERE id = 3",
            )
            conn.commit()

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row

            # "status" should be gone
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE id = 3",
            ).fetchall()
            assert len(rows) == 1  # Still in FTS
            assert "status" not in (rows[0]["full_text"] or ""), "'status' should not be in frame 3's full_text"

            # "feature" should exist
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'feature'",
            ).fetchall()
            frame_ids = {row["id"] for row in rows}
            assert 3 in frame_ids, "'feature' should be in frame 3's FTS"

    def test_update_to_empty_string_vs_null_both_clear(self, temp_db):
        """Updating full_text to empty string vs NULL both clear FTS tokens."""
        db_path, frames_dir = temp_db

        # Update frame 1 to empty string
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = '' WHERE id = 1",
            )
            conn.commit()

        # Update frame 2 to NULL
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = NULL WHERE id = 2",
            )
            conn.commit()

        # Both should return 0 results for their original text
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        # "world" only in frame 1's old full_text
        results, total = engine.search(q="world", limit=20, offset=0)
        assert total == 0, "world should have 0 results after clearing frame 1's full_text"

        # "hello" only in frame 2's old full_text
        results, total = engine.search(q="hello", limit=20, offset=0)
        assert total == 0, "hello should have 0 results after clearing frame 2's full_text"
