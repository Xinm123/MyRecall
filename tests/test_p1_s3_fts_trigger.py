"""P1-S3 Integration Test: FTS trigger auto-population (Post FTS Unification).

Tests that the FTS triggers correctly populate frames_fts when
frames are inserted/updated/deleted with full_text.

SSOT: 20260325120000_consolidate_fts_to_full_text.sql - frames_ai/au/ad triggers

Key changes from pre-unification:
- Single frames_fts table indexes full_text + metadata
- INSERT trigger: populates frames_fts when full_text is non-empty
- UPDATE trigger: re-indexes on full_text or metadata change
- DELETE trigger: removes from frames_fts
- ocr_text_fts and accessibility_fts are dropped
"""

import sqlite3
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database with v3 schema via migrations."""
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


class TestFramesFtsInsertTrigger:
    """Tests for frames_fts INSERT trigger (frames_ai)."""

    def test_insert_frame_with_full_text_populates_fts(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that inserting a frame with full_text populates frames_fts."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-insert-1",
            metadata={
                "timestamp": "2026-03-17T12:00:00Z",
                "app_name": "TestApp",
                "window_name": "TestWindow",
            },
        )

        # Set full_text on the frame (simulating what V3ProcessingWorker does)
        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = ? WHERE id = ?",
                ("Hello World from frames", frame_id),
            )
            conn.commit()

        # Verify FTS was populated
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'Hello'",
            ).fetchall()

            assert len(rows) == 1, "frames_fts should have 1 entry after INSERT with full_text"
            assert rows[0]["id"] == frame_id
            assert "Hello" in rows[0]["full_text"]

    def test_insert_frame_without_full_text_not_indexed(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that inserting a frame without full_text does NOT populate frames_fts.

        Per the trigger: WHEN NEW.full_text IS NOT NULL AND NEW.full_text != ''
        """
        frame_id, _ = store.claim_frame(
            capture_id="fts-insert-empty",
            metadata={"timestamp": "2026-03-17T12:01:00Z"},
        )
        # Do NOT set full_text

        with sqlite3.connect(str(temp_db)) as conn:
            # Verify no entry in frames_fts for this frame
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE id = ?",
                (frame_id,),
            ).fetchall()

            assert len(rows) == 0, (
                "frames_fts should be empty for frame without full_text"
            )

    def test_frames_fts_search_by_word(
        self, store: FramesStore, temp_db: Path
    ):
        """Test FTS search by individual words."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-insert-2",
            metadata={"timestamp": "2026-03-17T12:02:00Z"},
        )

        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = ?, app_name = 'QuickApp' WHERE id = ?",
                ("The quick brown fox jumps over lazy dog", frame_id),
            )
            conn.commit()

        with sqlite3.connect(str(temp_db)) as conn:
            for word in ["quick", "brown", "fox", "jumps", "lazy", "dog"]:
                rows = conn.execute(
                    "SELECT * FROM frames_fts WHERE frames_fts MATCH ?",
                    (word,),
                ).fetchall()
                assert len(rows) == 1, f"Expected to find '{word}' in FTS"

    def test_frames_fts_search_by_app_name(
        self, store: FramesStore, temp_db: Path
    ):
        """Test FTS search includes app_name."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-insert-3",
            metadata={"timestamp": "2026-03-17T12:03:00Z"},
        )

        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = ?, app_name = 'UniqueAppSearchTerm' WHERE id = ?",
                ("Some text content", frame_id),
            )
            conn.commit()

        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'UniqueAppSearchTerm'",
            ).fetchall()

            assert len(rows) == 1, "Should find frame by app_name in frames_fts"

    def test_frames_fts_multiple_frames(
        self, store: FramesStore, temp_db: Path
    ):
        """Test frames_fts with multiple frames."""
        frame_ids = []
        for i in range(3):
            fid, _ = store.claim_frame(
                capture_id=f"fts-multi-{i}",
                metadata={"timestamp": f"2026-03-17T12:0{i}:00Z"},
            )
            frame_ids.append(fid)

        with sqlite3.connect(str(temp_db)) as conn:
            for i, fid in enumerate(frame_ids):
                conn.execute(
                    "UPDATE frames SET full_text = ? WHERE id = ?",
                    (f"Frame {i} content with keyword shared", fid),
                )
            conn.commit()

        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'shared'",
            ).fetchall()

            assert len(rows) == 3, "All 3 frames with 'shared' should be in frames_fts"


class TestFramesFtsUpdateTrigger:
    """Tests for frames_fts UPDATE trigger (frames_au)."""

    def test_update_full_text_reindexes_fts(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that updating full_text re-indexes frames_fts."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-update-1",
            metadata={"timestamp": "2026-03-17T12:04:00Z"},
        )

        # Set initial full_text
        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = ? WHERE id = ?",
                ("Original text keyword", frame_id),
            )
            conn.commit()

        # Verify original text in FTS
        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'Original'",
            ).fetchall()
            assert len(rows) == 1

        # Update full_text
        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = ? WHERE id = ?",
                ("Updated text keyword", frame_id),
            )
            conn.commit()

        # Verify FTS reflects update
        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'Original'",
            ).fetchall()
            assert len(rows) == 0, "Original text should be removed from FTS after update"

            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'Updated'",
            ).fetchall()
            assert len(rows) == 1, "Updated text should be in FTS"

    def test_update_app_name_reindexes_fts(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that updating app_name re-indexes frames_fts."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-update-2",
            metadata={"timestamp": "2026-03-17T12:05:00Z"},
        )

        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = ?, app_name = ? WHERE id = ?",
                ("Some text", "OldAppName", frame_id),
            )
            conn.commit()

        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'OldAppName'",
            ).fetchall()
            assert len(rows) == 1

        # Update app_name
        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE frames SET app_name = ? WHERE id = ?",
                ("NewAppName", frame_id),
            )
            conn.commit()

        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'OldAppName'",
            ).fetchall()
            assert len(rows) == 0, "OldAppName should be removed after update"

            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'NewAppName'",
            ).fetchall()
            assert len(rows) == 1, "NewAppName should be in FTS after update"

    def test_delete_frame_removes_from_fts(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that deleting a frame removes it from frames_fts."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-delete-1",
            metadata={"timestamp": "2026-03-17T12:06:00Z"},
        )

        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = ? WHERE id = ?",
                ("Text to be deleted", frame_id),
            )
            conn.commit()

        # Verify FTS has the row
        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'deleted'",
            ).fetchall()
            assert len(rows) == 1

        # Delete the frame
        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute("DELETE FROM frames WHERE id = ?", (frame_id,))
            conn.commit()

        # Verify FTS is also deleted
        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE frames_fts MATCH 'deleted'",
            ).fetchall()
            assert len(rows) == 0, "Deleted frame should not be in frames_fts"

    def test_clear_full_text_removes_from_fts(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that setting full_text to empty removes from frames_fts."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-clear-1",
            metadata={"timestamp": "2026-03-17T12:07:00Z"},
        )

        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = ? WHERE id = ?",
                ("Text to be cleared", frame_id),
            )
            conn.commit()

        # Verify in FTS
        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE id = ?",
                (frame_id,),
            ).fetchall()
            assert len(rows) == 1

        # Clear full_text
        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE frames SET full_text = '' WHERE id = ?",
                (frame_id,),
            )
            conn.commit()

        # Verify removed from FTS
        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM frames_fts WHERE id = ?",
                (frame_id,),
            ).fetchall()
            assert len(rows) == 0, (
                "Frame with cleared full_text should not be in frames_fts"
            )
