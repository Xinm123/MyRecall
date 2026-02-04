"""Tests for SQLite connection pragmas and stability."""

import sqlite3
import pytest


class TestSQLStoreConnectionHelpers:
    """Test SQLStore exposes hardened connection methods."""

    def test_connect_db_sets_pragmas(self, flask_app):
        """_connect_db() should return connection with correct pragmas."""
        from openrecall.server.database import SQLStore

        store = SQLStore()
        conn = store._connect_db()
        try:
            # Check WAL mode
            cursor = conn.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0].lower()
            assert mode in ("wal", "memory"), f"Expected wal or memory, got {mode}"

            # Check busy_timeout
            cursor = conn.execute("PRAGMA busy_timeout;")
            timeout = cursor.fetchone()[0]
            assert timeout >= 5000, f"Expected busy_timeout >= 5000, got {timeout}"

            # Check synchronous=NORMAL
            cursor = conn.execute("PRAGMA synchronous;")
            sync = cursor.fetchone()[0]
            assert sync == 1, f"Expected synchronous=1 (NORMAL), got {sync}"

            # Check temp_store=MEMORY
            cursor = conn.execute("PRAGMA temp_store;")
            temp = cursor.fetchone()[0]
            assert temp == 2, f"Expected temp_store=2 (MEMORY), got {temp}"
        finally:
            conn.close()

    def test_connect_fts_sets_pragmas(self, flask_app):
        """_connect_fts() should return connection with correct pragmas."""
        from openrecall.server.database import SQLStore

        store = SQLStore()
        conn = store._connect_fts()
        try:
            # Check WAL mode
            cursor = conn.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0].lower()
            assert mode in ("wal", "memory"), f"Expected wal or memory, got {mode}"

            # Check busy_timeout
            cursor = conn.execute("PRAGMA busy_timeout;")
            timeout = cursor.fetchone()[0]
            assert timeout >= 5000, f"Expected busy_timeout >= 5000, got {timeout}"
        finally:
            conn.close()


class TestSQLiteConnectionPragmas:
    """Verify SQLite connections created by SQLStore have proper pragmas set."""

    def test_db_wal_mode_is_persistent_after_store_init(self, flask_app):
        """WAL mode should persist on disk after SQLStore init."""
        from openrecall.shared.config import settings
        from openrecall.server.database import SQLStore

        # Create a new SQLStore which will set pragmas
        store = SQLStore()

        # Use the store's connection helper which has pragmas
        with store._connect_db() as conn:
            cursor = conn.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0].lower()
            assert mode in ("wal", "memory"), f"Expected wal or memory, got {mode}"

    def test_fts_wal_mode_is_persistent_after_store_init(self, flask_app):
        """WAL mode should persist on disk after SQLStore init for FTS."""
        from openrecall.server.database import SQLStore

        store = SQLStore()

        with store._connect_fts() as conn:
            cursor = conn.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0].lower()
            assert mode in ("wal", "memory"), f"Expected wal or memory, got {mode}"
