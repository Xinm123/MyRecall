import sqlite3
from pathlib import Path

import pytest

from openrecall.server import __main__ as server_main
from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import (
    run_migrations,
    verify_schema_integrity,
)


def _has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def test_run_migrations_rejects_self_recording_sql(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir(parents=True, exist_ok=True)
    migrations_dir.joinpath("20260101010101_initial.sql").write_text(
        "\n".join(
            [
                "CREATE TABLE IF NOT EXISTS sample_data(id INTEGER PRIMARY KEY);",
                "INSERT INTO schema_migrations(version, description) VALUES ('20260101010101', 'initial');",
            ]
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "edge.db"
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(ValueError):
            run_migrations(conn, migrations_dir)


def test_run_migrations_is_atomic_on_script_failure(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir(parents=True, exist_ok=True)
    migrations_dir.joinpath("20260101010101_broken.sql").write_text(
        "\n".join(
            [
                "CREATE TABLE partial_data(id INTEGER PRIMARY KEY);",
                "INSERT INTO not_existing_table(x) VALUES (1);",
            ]
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "edge.db"
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.Error):
            run_migrations(conn, migrations_dir)

    with sqlite3.connect(db_path) as conn:
        assert not _has_table(conn, "partial_data")
        row = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version='20260101010101'"
        ).fetchone()
        assert row is not None
        assert row[0] == 0


def test_verify_schema_integrity_detects_marked_but_missing_structure(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "edge.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE schema_migrations (
                version TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        conn.execute(
            "INSERT INTO schema_migrations(version, description) VALUES (?, ?)",
            ("20260227000001", "initial_schema"),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            verify_schema_integrity(conn)


def test_startup_bootstrap_creates_frames_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "edge.db"

    server_main.ensure_v3_schema(db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        assert _has_table(conn, "frames")


def test_frames_store_without_bootstrap_does_not_create_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "edge.db"

    store = FramesStore(db_path=db_path)
    counts = store.get_queue_counts()

    assert counts == {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    with sqlite3.connect(db_path) as conn:
        assert not _has_table(conn, "frames")


class TestFtsUnificationMigration:
    """Tests for the FTS unification migration (20260325120000).

    Verifies that the migration correctly:
    - Adds the full_text column to frames
    - Backfills from all text source combinations
    - Rebuilds frames_fts with full_text indexing
    - Drops old FTS tables
    - Sets up proper INSERT/UPDATE/DELETE triggers
    """

    @pytest.fixture
    def db_pre_migration(self, tmp_path: Path) -> tuple[sqlite3.Connection, Path]:
        """Create a db with initial v3 schema + test frames inserted BEFORE migration.

        Bootstraps with initial schema using the initial SQL file directly, so the
        FTS unification migration has NOT been applied yet. This allows tests to
        verify the backfill behavior: insert frames, then apply migration, verify.
        """
        db_path = tmp_path / "edge.db"

        # Bootstrap using the initial schema SQL directly to avoid applying all migrations
        initial_sql = (
            Path(__file__).resolve().parent.parent
            / "openrecall/server/database/migrations/20260227000001_initial_schema.sql"
        ).read_text()

        conn = sqlite3.connect(db_path)
        conn.executescript(initial_sql)

        # Apply subsequent migrations up to (but not including) FTS unification
        migrations_dir = (
            Path(__file__).resolve().parent.parent
            / "openrecall/server/database/migrations"
        )
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            version = sql_file.stem.split("_")[0]
            if version >= "20260325120000":
                break
            if not conn.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = ?", (version,)
            ).fetchone()[0]:
                script = sql_file.read_text(encoding="utf-8")
                conn.executescript(script)
                conn.execute(
                    "INSERT INTO schema_migrations(version, description) VALUES (?, ?)",
                    (version, sql_file.stem),
                )
        conn.commit()

        return conn, db_path

    def _apply_fts_unification_migration(
        self, db_path: Path
    ) -> sqlite3.Connection:
        """Apply the FTS unification migration to a db that already has prior migrations."""
        migrations_dir = (
            Path(__file__).resolve().parent.parent
            / "openrecall/server/database/migrations"
        )
        conn = sqlite3.connect(db_path)
        run_migrations(conn, migrations_dir)
        conn.commit()
        return conn

    def _insert_frame(
        self,
        conn: sqlite3.Connection,
        accessibility_text: str | None = None,
        ocr_text: str | None = None,
        ocr_text_table: str | None = None,
        app_name: str = "TestApp",
        window_name: str = "TestWindow",
        browser_url: str = "",
    ) -> int:
        """Insert a minimal frame row and return its id."""
        cursor = conn.execute(
            """
            INSERT INTO frames (
                timestamp, app_name, window_name, browser_url, status,
                capture_id, ingested_at, accessibility_text, ocr_text
            )
            VALUES (?, ?, ?, ?, 'completed', ?, ?, ?, ?)
            """,
            (
                "2026-03-25T00:00:00Z",
                app_name,
                window_name,
                browser_url,
                f"capture-{id(object())}",
                "2026-03-25T00:00:00Z",
                accessibility_text,
                ocr_text,
            ),
        )
        frame_id = cursor.lastrowid

        if ocr_text_table is not None:
            conn.execute(
                "INSERT INTO ocr_text(frame_id, text, app_name, window_name) VALUES (?, ?, ?, ?)",
                (frame_id, ocr_text_table, app_name, window_name),
            )

        conn.commit()
        return frame_id

    def test_adds_full_text_column(self, db_pre_migration) -> None:
        """Verify full_text column is added to frames table after migration."""
        conn, db_path = db_pre_migration
        self._insert_frame(conn, accessibility_text="test")
        conn.close()

        conn = self._apply_fts_unification_migration(db_path)
        col_info = conn.execute("PRAGMA table_info(frames)").fetchall()
        col_names = {row[1] for row in col_info}
        assert "full_text" in col_names
        conn.close()

    def test_backfill_from_accessibility_text(self, db_pre_migration) -> None:
        """Verify backfill from frames.accessibility_text (AX-only path)."""
        conn, db_path = db_pre_migration
        self._insert_frame(conn, accessibility_text="accessibility content here")
        conn.close()

        # Apply migration (this backfills)
        conn = self._apply_fts_unification_migration(db_path)

        row = conn.execute(
            "SELECT full_text FROM frames WHERE accessibility_text = ?",
            ("accessibility content here",),
        ).fetchone()
        assert row is not None
        assert row[0] == "accessibility content here"
        conn.close()

    def test_backfill_from_ocr_text_column(self, db_pre_migration) -> None:
        """Verify backfill from frames.ocr_text column (OCR-only path)."""
        conn, db_path = db_pre_migration
        self._insert_frame(conn, ocr_text="ocr text content here")
        conn.close()

        conn = self._apply_fts_unification_migration(db_path)
        row = conn.execute(
            "SELECT full_text FROM frames WHERE ocr_text = ?",
            ("ocr text content here",),
        ).fetchone()
        assert row is not None
        assert row[0] == "ocr text content here"
        conn.close()

    def test_backfill_from_ocr_text_table(self, db_pre_migration) -> None:
        """Verify backfill from ocr_text table (OCR fallback via table)."""
        conn, db_path = db_pre_migration
        self._insert_frame(conn, ocr_text_table="text from ocr_text table")
        conn.close()

        conn = self._apply_fts_unification_migration(db_path)
        row = conn.execute(
            "SELECT full_text FROM frames WHERE id IN (SELECT frame_id FROM ocr_text WHERE text = ?)",
            ("text from ocr_text table",),
        ).fetchone()
        assert row is not None
        assert row[0] == "text from ocr_text table"
        conn.close()

    def test_hybrid_merge_both_columns(self, db_pre_migration) -> None:
        """Verify merge when both accessibility_text and ocr_text columns exist."""
        conn, db_path = db_pre_migration
        self._insert_frame(
            conn,
            accessibility_text="accessibility text",
            ocr_text="ocr text",
        )
        conn.close()

        conn = self._apply_fts_unification_migration(db_path)
        row = conn.execute(
            "SELECT full_text FROM frames WHERE accessibility_text = ? AND ocr_text = ?",
            ("accessibility text", "ocr text"),
        ).fetchone()
        assert row is not None
        assert "accessibility text" in row[0]
        assert "ocr text" in row[0]
        # Should be concatenated with newline
        assert "\n" in row[0]
        conn.close()

    def test_fts_table_has_full_text(self, db_pre_migration) -> None:
        """Verify frames_fts includes full_text column and indexes it."""
        conn, db_path = db_pre_migration
        # Insert a frame before migration, then apply migration to trigger backfill
        frame_id = self._insert_frame(conn, accessibility_text="searchable content xyz")
        conn.close()

        conn = self._apply_fts_unification_migration(db_path)

        # frames_fts should exist and have full_text column
        fts_cols = {row[1] for row in conn.execute("PRAGMA table_info(frames_fts)").fetchall()}
        assert "full_text" in fts_cols
        assert "app_name" in fts_cols
        assert "window_name" in fts_cols
        assert "browser_url" in fts_cols
        assert "focused" not in fts_cols  # focused was removed from FTS

        # After migration, frame should be in frames_fts via backfill
        result = conn.execute(
            "SELECT full_text FROM frames_fts WHERE id = ?",
            (frame_id,),
        ).fetchone()
        assert result is not None
        assert result[0] == "searchable content xyz"
        conn.close()

    def test_old_fts_tables_dropped(self, db_pre_migration) -> None:
        """Verify ocr_text_fts and accessibility_fts are dropped."""
        conn, db_path = db_pre_migration
        conn.close()
        conn = self._apply_fts_unification_migration(db_path)

        assert not _has_table(conn, "ocr_text_fts")
        assert not _has_table(conn, "accessibility_fts")
        conn.close()

    def test_insert_trigger_populates_fts(self, db_pre_migration) -> None:
        """Verify INSERT trigger on frames populates frames_fts when full_text is set."""
        conn, db_path = db_pre_migration
        conn.close()
        conn = self._apply_fts_unification_migration(db_path)

        # Insert a frame with full_text set directly (new frame after migration)
        cursor = conn.execute(
            """
            INSERT INTO frames (
                timestamp, app_name, window_name, browser_url, status,
                capture_id, ingested_at, full_text
            )
            VALUES (?, ?, ?, ?, 'completed', ?, ?, ?)
            """,
            (
                "2026-03-25T01:00:00Z",
                "TriggerTestApp",
                "TriggerTestWindow",
                "",
                f"capture-trigger-{id(object())}",
                "2026-03-25T01:00:00Z",
                "trigger searchable content",
            ),
        )
        conn.commit()
        frame_id = cursor.lastrowid

        result = conn.execute(
            "SELECT full_text FROM frames_fts WHERE id = ?",
            (frame_id,),
        ).fetchone()
        assert result is not None
        assert result[0] == "trigger searchable content"

        # Verify insert with NULL full_text does NOT populate FTS
        cursor2 = conn.execute(
            """
            INSERT INTO frames (
                timestamp, app_name, window_name, browser_url, status,
                capture_id, ingested_at
            )
            VALUES (?, ?, ?, ?, 'completed', ?, ?)
            """,
            (
                "2026-03-25T02:00:00Z",
                "TriggerTestApp",
                "TriggerTestWindow",
                "",
                f"capture-trigger-null-{id(object())}",
                "2026-03-25T02:00:00Z",
            ),
        )
        conn.commit()
        frame_id2 = cursor2.lastrowid

        result2 = conn.execute(
            "SELECT full_text FROM frames_fts WHERE id = ?",
            (frame_id2,),
        ).fetchone()
        assert result2 is None  # NULL full_text should not be indexed
        conn.close()

    def test_update_trigger_updates_fts(self, db_pre_migration) -> None:
        """Verify UPDATE trigger on frames updates frames_fts."""
        conn, db_path = db_pre_migration
        conn.close()
        conn = self._apply_fts_unification_migration(db_path)

        # Insert frame without full_text first
        cursor = conn.execute(
            """
            INSERT INTO frames (
                timestamp, app_name, window_name, browser_url, status,
                capture_id, ingested_at
            )
            VALUES (?, ?, ?, ?, 'completed', ?, ?)
            """,
            (
                "2026-03-25T03:00:00Z",
                "UpdateTestApp",
                "UpdateTestWindow",
                "",
                f"capture-update-{id(object())}",
                "2026-03-25T03:00:00Z",
            ),
        )
        conn.commit()
        frame_id = cursor.lastrowid

        # Should not be in FTS
        assert (
            conn.execute(
                "SELECT 1 FROM frames_fts WHERE id = ?", (frame_id,)
            ).fetchone()
            is None
        )

        # Update full_text - should trigger FTS insert
        conn.execute(
            "UPDATE frames SET full_text = ? WHERE id = ?",
            ("updated searchable content", frame_id),
        )
        conn.commit()

        result = conn.execute(
            "SELECT full_text FROM frames_fts WHERE id = ?",
            (frame_id,),
        ).fetchone()
        assert result is not None
        assert result[0] == "updated searchable content"

        # Update full_text to NULL - should remove from FTS
        conn.execute("UPDATE frames SET full_text = NULL WHERE id = ?", (frame_id,))
        conn.commit()

        result2 = conn.execute(
            "SELECT full_text FROM frames_fts WHERE id = ?",
            (frame_id,),
        ).fetchone()
        assert result2 is None
        conn.close()


class TestVisibilityStatusMigration:
    """Tests for the visibility_status migration (20260414000000).

    Verifies that the migration correctly:
    - Adds visibility_status column to frames
    - Backfills fully processed frames as 'queryable'
    - Leaves partially processed frames as 'pending'
    - Marks frames with failures as 'failed'
    """

    @pytest.fixture
    def db_pre_migration(self, tmp_path: Path) -> tuple[sqlite3.Connection, Path]:
        """Create a db with migrations applied up to (but not including) visibility_status.

        This allows inserting test data BEFORE the visibility_status migration,
        then applying the migration to test backfill behavior.
        """
        db_path = tmp_path / "edge.db"

        # Bootstrap using the initial schema SQL directly
        initial_sql = (
            Path(__file__).resolve().parent.parent
            / "openrecall/server/database/migrations/20260227000001_initial_schema.sql"
        ).read_text()

        conn = sqlite3.connect(db_path)
        conn.executescript(initial_sql)

        # Apply subsequent migrations up to (but not including) visibility_status
        migrations_dir = (
            Path(__file__).resolve().parent.parent
            / "openrecall/server/database/migrations"
        )
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            version = sql_file.stem.split("_")[0]
            if version >= "20260414000000":  # Stop before visibility_status migration
                break
            if not conn.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = ?", (version,)
            ).fetchone()[0]:
                script = sql_file.read_text(encoding="utf-8")
                conn.executescript(script)
                conn.execute(
                    "INSERT INTO schema_migrations(version, description) VALUES (?, ?)",
                    (version, sql_file.stem),
                )
        conn.commit()

        return conn, db_path

    def _apply_visibility_status_migration(
        self, db_path: Path
    ) -> sqlite3.Connection:
        """Apply the visibility_status migration to a db that already has prior migrations."""
        migrations_dir = (
            Path(__file__).resolve().parent.parent
            / "openrecall/server/database/migrations"
        )
        conn = sqlite3.connect(db_path)
        run_migrations(conn, migrations_dir)
        conn.commit()
        return conn

    def test_visibility_status_migration_backfill(self, db_pre_migration) -> None:
        """Verify visibility_status migration correctly backfills existing frames."""
        conn, db_path = db_pre_migration

        # Insert test data BEFORE the visibility_status migration
        # Insert a fully processed frame
        conn.execute("""
            INSERT INTO frames (capture_id, timestamp, status, description_status,
                               embedding_status, app_name)
            VALUES ('test-1', '2026-04-14T00:00:00Z', 'completed', 'completed',
                    'completed', 'TestApp')
        """)
        # Insert a partially processed frame
        conn.execute("""
            INSERT INTO frames (capture_id, timestamp, status, description_status,
                               embedding_status, app_name)
            VALUES ('test-2', '2026-04-14T00:01:00Z', 'completed', 'completed',
                    'pending', 'TestApp')
        """)
        # Insert a failed frame
        conn.execute("""
            INSERT INTO frames (capture_id, timestamp, status, description_status,
                               embedding_status, app_name)
            VALUES ('test-3', '2026-04-14T00:02:00Z', 'failed', 'pending',
                    'pending', 'TestApp')
        """)
        conn.commit()
        conn.close()

        # Apply the visibility_status migration (this triggers backfill)
        conn = self._apply_visibility_status_migration(db_path)

        # Verify backfill
        conn.row_factory = sqlite3.Row

        # Check fully processed frame is queryable
        row = conn.execute(
            "SELECT visibility_status FROM frames WHERE capture_id = 'test-1'"
        ).fetchone()
        assert row["visibility_status"] == "queryable"

        # Check partially processed frame is pending
        row = conn.execute(
            "SELECT visibility_status FROM frames WHERE capture_id = 'test-2'"
        ).fetchone()
        assert row["visibility_status"] == "pending"

        # Check failed frame is failed
        row = conn.execute(
            "SELECT visibility_status FROM frames WHERE capture_id = 'test-3'"
        ).fetchone()
        assert row["visibility_status"] == "failed"

        conn.close()


def test_migration_20260426000000_adds_local_timestamp(tmp_path: Path) -> None:
    """Verify local_timestamp migration adds column and index."""
    from openrecall.server.database.migrations_runner import run_migrations

    migrations_dir = Path("openrecall/server/database/migrations")
    db_path = tmp_path / "edge.db"
    conn = sqlite3.connect(str(db_path))
    run_migrations(conn, migrations_dir)

    # Verify column exists
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(frames)")
    }
    assert "local_timestamp" in columns

    # Verify index exists
    indexes = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='frames'"
        )
    }
    assert "idx_frames_local_timestamp" in indexes

    conn.close()
