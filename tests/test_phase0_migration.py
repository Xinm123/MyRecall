"""Tests for Phase 0 database migration, rollback, and integrity."""

import os
import sqlite3
import time
import tracemalloc
from pathlib import Path

import pytest


def _create_test_db(db_path: Path, num_entries: int = 0) -> None:
    """Create a test database with the entries table and optional test data."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS entries (
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)")

    for i in range(num_entries):
        conn.execute(
            "INSERT INTO entries (timestamp, app, title, text, description, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1000000 + i, f"app_{i}", f"title_{i}", f"text_{i}", f"desc_{i}", "COMPLETED"),
        )
    conn.commit()
    conn.close()


def _get_tables(db_path: Path) -> set:
    """Get set of table names in a database."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
        "AND name NOT LIKE 'sqlite_%'"
    )
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    return tables


def _get_columns(db_path: Path, table_name: str) -> set:
    """Get set of column names for a table."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    return columns


class TestMigrationForward:
    """Tests for forward migration."""

    def test_migration_creates_all_tables(self, tmp_path):
        """F-01: All new tables created after migration."""
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "test.db"
        _create_test_db(db_path)

        runner = MigrationRunner(db_path)
        result = runner.run()

        assert result.success, f"Migration failed: {result.error}"

        tables = _get_tables(db_path)
        expected = {
            "entries",
            "schema_version",
            "video_chunks",
            "frames",
            "ocr_text",
            "audio_chunks",
            "audio_transcriptions",
            "ocr_text_fts",
            "audio_transcriptions_fts",
        }
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    def test_migration_idempotent(self, tmp_path):
        """Migration can run twice without errors."""
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "test.db"
        _create_test_db(db_path)

        runner = MigrationRunner(db_path)
        result1 = runner.run()
        assert result1.success

        result2 = runner.run()
        assert result2.success, f"Second run failed: {result2.error}"

    def test_migration_preserves_entries(self, tmp_path):
        """S-01 partial: 100 entries intact after migration."""
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "test.db"
        _create_test_db(db_path, num_entries=100)

        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM entries")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 100, f"Expected 100 entries, got {count}"

    def test_migration_performance_10k(self, tmp_path):
        """P-01: Migration completes in <5 seconds for 10K entries."""
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "test.db"
        _create_test_db(db_path, num_entries=10000)

        runner = MigrationRunner(db_path)
        result = runner.run()

        assert result.success, f"Migration failed: {result.error}"
        assert result.elapsed_seconds < 5.0, (
            f"Migration took {result.elapsed_seconds:.2f}s (target: <5s)"
        )

    def test_migration_memory_under_500mb(self, tmp_path):
        """R-01: Migration uses <500MB RAM."""
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "test.db"
        _create_test_db(db_path, num_entries=10000)

        runner = MigrationRunner(db_path)
        result = runner.run()

        assert result.success
        assert result.peak_memory_mb < 500, (
            f"Peak memory {result.peak_memory_mb:.1f}MB exceeds 500MB limit"
        )

    def test_schema_overhead_under_10mb(self, tmp_path):
        """R-02: Schema overhead <10MB for empty tables."""
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "test.db"
        _create_test_db(db_path)

        size_before = db_path.stat().st_size

        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        size_after = db_path.stat().st_size
        overhead_mb = (size_after - size_before) / (1024 * 1024)

        assert overhead_mb < 10, (
            f"Schema overhead {overhead_mb:.2f}MB exceeds 10MB limit"
        )


class TestGovernanceColumns:
    """Tests for governance columns on entries table."""

    def test_governance_columns_exist(self, tmp_path):
        """DG-03: entries table has created_at and expires_at."""
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "test.db"
        _create_test_db(db_path, num_entries=5)

        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        columns = _get_columns(db_path, "entries")
        assert "created_at" in columns, "Missing created_at column"
        assert "expires_at" in columns, "Missing expires_at column"

    def test_encryption_columns_exist(self, tmp_path):
        """DG-02: video_chunks and audio_chunks have encrypted column."""
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "test.db"
        _create_test_db(db_path)

        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        vc_cols = _get_columns(db_path, "video_chunks")
        ac_cols = _get_columns(db_path, "audio_chunks")

        assert "encrypted" in vc_cols, "Missing encrypted column in video_chunks"
        assert "encrypted" in ac_cols, "Missing encrypted column in audio_chunks"

    def test_created_at_backfill(self, tmp_path):
        """Backfilled entries have non-empty created_at."""
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "test.db"
        _create_test_db(db_path, num_entries=10)

        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE created_at = '' OR created_at IS NULL"
        )
        empty_count = cursor.fetchone()[0]
        conn.close()

        assert empty_count == 0, f"{empty_count} entries have empty created_at"


class TestRollback:
    """Tests for migration rollback."""

    def test_rollback_restores_original(self, tmp_path):
        """S-02 partial: Only original tables remain after rollback."""
        from openrecall.server.database.migrations.runner import MigrationRunner
        from openrecall.server.database.migrations.rollback import MigrationRollback

        db_path = tmp_path / "test.db"
        _create_test_db(db_path, num_entries=50)

        # Forward migration
        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        # Rollback
        rollback = MigrationRollback(db_path)
        rb_result = rollback.rollback()
        assert rb_result.success, f"Rollback failed: {rb_result.error}"

        tables = _get_tables(db_path)
        v3_tables = {
            "schema_version", "video_chunks", "frames", "ocr_text",
            "audio_chunks", "audio_transcriptions",
            "ocr_text_fts", "audio_transcriptions_fts",
        }
        remaining_v3 = tables & v3_tables
        assert not remaining_v3, f"V3 tables still present: {remaining_v3}"
        assert "entries" in tables, "entries table missing after rollback"

    def test_rollback_preserves_entry_count(self, tmp_path):
        """Rollback preserves entries row count."""
        from openrecall.server.database.migrations.runner import MigrationRunner
        from openrecall.server.database.migrations.rollback import MigrationRollback

        db_path = tmp_path / "test.db"
        _create_test_db(db_path, num_entries=100)

        runner = MigrationRunner(db_path)
        runner.run()

        rollback = MigrationRollback(db_path)
        rb_result = rollback.rollback()

        assert rb_result.success
        assert rb_result.entries_before == 100
        assert rb_result.entries_after == 100

    def test_rollback_removes_governance_columns(self, tmp_path):
        """Rollback removes created_at and expires_at from entries."""
        from openrecall.server.database.migrations.runner import MigrationRunner
        from openrecall.server.database.migrations.rollback import MigrationRollback

        db_path = tmp_path / "test.db"
        _create_test_db(db_path, num_entries=5)

        runner = MigrationRunner(db_path)
        runner.run()

        rollback = MigrationRollback(db_path)
        rollback.rollback()

        columns = _get_columns(db_path, "entries")
        assert "created_at" not in columns, "created_at still present after rollback"
        assert "expires_at" not in columns, "expires_at still present after rollback"

    def test_rollback_completes_under_2min(self, tmp_path):
        """S-02: Rollback completes in <2 minutes."""
        from openrecall.server.database.migrations.runner import MigrationRunner
        from openrecall.server.database.migrations.rollback import MigrationRollback

        db_path = tmp_path / "test.db"
        _create_test_db(db_path, num_entries=10000)

        runner = MigrationRunner(db_path)
        runner.run()

        rollback = MigrationRollback(db_path)
        rb_result = rollback.rollback()

        assert rb_result.success
        assert rb_result.elapsed_seconds < 120, (
            f"Rollback took {rb_result.elapsed_seconds:.1f}s (target: <120s)"
        )


class TestIntegrity:
    """Tests for data integrity verification."""

    def test_data_integrity_checksum(self, tmp_path):
        """S-01: SHA256 checksum matches before and after migration."""
        from openrecall.server.database.migrations.runner import MigrationRunner
        from openrecall.server.database.migrations.integrity import (
            compute_entries_checksum,
            save_checksum,
            verify_checksum,
        )

        db_path = tmp_path / "test.db"
        _create_test_db(db_path, num_entries=100)

        # Checksum before migration
        conn = sqlite3.connect(str(db_path))
        checksum_before = compute_entries_checksum(conn)
        checksum_path = tmp_path / "checksum.txt"
        save_checksum(checksum_before, checksum_path)
        conn.close()

        # Run migration
        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        # Verify checksum after migration
        conn = sqlite3.connect(str(db_path))
        assert verify_checksum(conn, checksum_path), "Checksum mismatch after migration"
        conn.close()

    def test_checksum_deterministic(self, tmp_path):
        """Checksum is deterministic for same data."""
        from openrecall.server.database.migrations.integrity import compute_entries_checksum

        db_path = tmp_path / "test.db"
        _create_test_db(db_path, num_entries=50)

        conn = sqlite3.connect(str(db_path))
        c1 = compute_entries_checksum(conn)
        c2 = compute_entries_checksum(conn)
        conn.close()

        assert c1 == c2, "Checksum not deterministic"
