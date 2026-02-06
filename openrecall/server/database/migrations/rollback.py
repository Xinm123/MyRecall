"""Rollback script for MyRecall v3 database migration.

Restores the database to pre-v3 state by dropping v3 tables
and removing governance columns from the entries table.
"""

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Tables introduced in v3 migration
V3_TABLES = [
    "audio_transcriptions",
    "audio_chunks",
    "ocr_text",
    "frames",
    "video_chunks",
    "schema_version",
]

V3_VIRTUAL_TABLES = [
    "ocr_text_fts",
    "audio_transcriptions_fts",
]


@dataclass
class RollbackResult:
    """Result of a rollback operation."""
    success: bool
    elapsed_seconds: float = 0.0
    entries_before: int = 0
    entries_after: int = 0
    error: Optional[str] = None


class MigrationRollback:
    """Rolls back v3 migration, restoring original database state."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def _count_entries(self, conn: sqlite3.Connection) -> int:
        """Count rows in entries table."""
        cursor = conn.execute("SELECT COUNT(*) FROM entries")
        return cursor.fetchone()[0]

    def _drop_v3_tables(self, conn: sqlite3.Connection) -> None:
        """Drop all v3-introduced tables."""
        for table in V3_VIRTUAL_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        for table in V3_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()

    def _remove_governance_columns(self, conn: sqlite3.Connection) -> None:
        """Remove created_at and expires_at from entries table.

        Uses the standard SQLite table rebuild pattern:
        CREATE new -> INSERT SELECT -> DROP old -> RENAME new
        """
        # Check if columns exist first
        cursor = conn.execute("PRAGMA table_info(entries)")
        columns = {row[1] for row in cursor.fetchall()}

        if "created_at" not in columns and "expires_at" not in columns:
            logger.debug("Governance columns not present, skipping removal")
            return

        # Get original columns (minus governance columns)
        original_cols = [c for c in columns if c not in ("created_at", "expires_at")]
        cols_str = ", ".join(original_cols)

        conn.execute("BEGIN TRANSACTION")
        try:
            # Create new table with original schema
            conn.execute(
                f"""CREATE TABLE entries_backup (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app TEXT,
                    title TEXT,
                    text TEXT,
                    timestamp INTEGER UNIQUE,
                    embedding BLOB,
                    description TEXT,
                    status TEXT DEFAULT 'COMPLETED'
                )"""
            )

            # Copy data (only original columns)
            conn.execute(
                f"INSERT INTO entries_backup ({cols_str}) SELECT {cols_str} FROM entries"
            )

            # Drop old and rename
            conn.execute("DROP TABLE entries")
            conn.execute("ALTER TABLE entries_backup RENAME TO entries")

            # Recreate index
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)"
            )

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def _drop_v3_indexes(self, conn: sqlite3.Connection) -> None:
        """Drop v3-specific indexes."""
        v3_indexes = [
            "idx_frames_video_chunk_id",
            "idx_frames_timestamp",
            "idx_frames_app_name",
            "idx_frames_timestamp_offset",
            "idx_ocr_text_frame_id",
            "idx_audio_transcriptions_chunk_id",
            "idx_audio_transcriptions_timestamp",
            "idx_audio_transcriptions_chunk_ts",
            "idx_video_chunks_created_at",
            "idx_audio_chunks_created_at",
        ]
        for idx in v3_indexes:
            conn.execute(f"DROP INDEX IF EXISTS {idx}")
        conn.commit()

    def rollback(self) -> RollbackResult:
        """Execute full rollback to pre-v3 state.

        Returns:
            RollbackResult with success status and entry counts.
        """
        start_time = time.perf_counter()

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA foreign_keys=OFF")

            entries_before = self._count_entries(conn)

            # Step 1: Drop v3 indexes
            self._drop_v3_indexes(conn)

            # Step 2: Drop v3 tables
            self._drop_v3_tables(conn)

            # Step 3: Remove governance columns from entries
            self._remove_governance_columns(conn)

            entries_after = self._count_entries(conn)

            elapsed = time.perf_counter() - start_time
            conn.close()

            if entries_before != entries_after:
                return RollbackResult(
                    success=False,
                    elapsed_seconds=elapsed,
                    entries_before=entries_before,
                    entries_after=entries_after,
                    error=f"Entry count mismatch: {entries_before} -> {entries_after}",
                )

            logger.info(
                f"Rollback completed in {elapsed:.2f}s. "
                f"Entries preserved: {entries_after}"
            )

            return RollbackResult(
                success=True,
                elapsed_seconds=elapsed,
                entries_before=entries_before,
                entries_after=entries_after,
            )

        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.exception(f"Rollback failed: {e}")
            return RollbackResult(
                success=False,
                elapsed_seconds=elapsed,
                error=str(e),
            )
