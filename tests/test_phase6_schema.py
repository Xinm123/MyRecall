"""Tests for Phase 6.1 schema migration - adding description column."""

import importlib
import os
import sqlite3
import tempfile
from unittest import mock

import numpy as np
import pytest


class TestDescriptionColumnMigration:
    """Tests for the description column migration."""

    def test_migration_adds_description_column_to_old_schema(self):
        """Test that migration adds description column to existing table without it."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "db", "recall.db")
            os.makedirs(os.path.dirname(db_path))

            # Create OLD schema (without description column)
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """CREATE TABLE entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        app TEXT,
                        title TEXT,
                        text TEXT,
                        timestamp INTEGER UNIQUE,
                        embedding BLOB
                    )"""
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)"
                )
                conn.commit()

            # Verify description column does NOT exist yet
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(entries)")
                columns = {row[1] for row in cursor.fetchall()}
                assert "description" not in columns, "Column should not exist before migration"

            # Now initialize database module with patched data dir
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": tmp_dir}):
                import openrecall.shared.config
                import openrecall.server.database

                importlib.reload(openrecall.shared.config)
                importlib.reload(openrecall.server.database)

                # This should trigger migration
                openrecall.server.database.create_db()

            # Verify description column now exists
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(entries)")
                columns = {row[1] for row in cursor.fetchall()}
                assert "description" in columns, "Migration should have added description column"

    def test_migration_is_idempotent(self):
        """Test that running migration multiple times doesn't cause errors."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": tmp_dir}):
                import openrecall.shared.config
                import openrecall.server.database

                importlib.reload(openrecall.shared.config)
                importlib.reload(openrecall.server.database)

                # Run create_db multiple times - should not raise
                openrecall.server.database.create_db()
                openrecall.server.database.create_db()
                openrecall.server.database.create_db()

                # Verify schema is still correct
                db_path = openrecall.shared.config.settings.db_path
                with sqlite3.connect(str(db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA table_info(entries)")
                    columns = {row[1] for row in cursor.fetchall()}
                    assert "description" in columns


class TestDescriptionReadWrite:
    """Tests for reading and writing entries with description field."""

    @pytest.fixture
    def temp_db_env(self):
        """Set up a temporary database environment."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": tmp_dir}):
                import openrecall.shared.config
                import openrecall.server.database

                importlib.reload(openrecall.shared.config)
                importlib.reload(openrecall.server.database)

                openrecall.server.database.create_db()
                yield openrecall.server.database

    def test_insert_entry_with_description(self, temp_db_env):
        """Test inserting an entry with a description."""
        db = temp_db_env
        test_embedding = np.random.rand(384).astype(np.float32)
        test_timestamp = 1700000001
        test_description = "A user is coding in VS Code with Python file open"

        row_id = db.insert_entry(
            text="def hello(): pass",
            timestamp=test_timestamp,
            embedding=test_embedding,
            app="VS Code",
            title="main.py",
            description=test_description,
        )

        assert row_id is not None

        # Read back and verify
        entries = db.get_all_entries()
        assert len(entries) == 1
        assert entries[0].description == test_description
        assert entries[0].text == "def hello(): pass"
        assert entries[0].app == "VS Code"

    def test_insert_entry_without_description(self, temp_db_env):
        """Test inserting an entry without a description (backward compatibility)."""
        db = temp_db_env
        test_embedding = np.random.rand(384).astype(np.float32)
        test_timestamp = 1700000002

        row_id = db.insert_entry(
            text="Some OCR text",
            timestamp=test_timestamp,
            embedding=test_embedding,
            app="Safari",
            title="Google",
        )

        assert row_id is not None

        # Read back and verify description is None
        entries = db.get_all_entries()
        assert len(entries) == 1
        assert entries[0].description is None
        assert entries[0].text == "Some OCR text"

    def test_get_entries_by_time_range_includes_description(self, temp_db_env):
        """Test that get_entries_by_time_range includes description field."""
        db = temp_db_env
        test_embedding = np.random.rand(384).astype(np.float32)
        test_description = "User browsing documentation"

        db.insert_entry(
            text="API docs",
            timestamp=1700000010,
            embedding=test_embedding,
            app="Firefox",
            title="Docs",
            description=test_description,
        )

        entries = db.get_entries_by_time_range(1700000000, 1700000020)
        assert len(entries) == 1
        assert entries[0].description == test_description

    def test_mixed_entries_with_and_without_description(self, temp_db_env):
        """Test reading multiple entries, some with description, some without."""
        db = temp_db_env
        test_embedding = np.random.rand(384).astype(np.float32)

        # Insert entry WITH description
        db.insert_entry(
            text="Text 1",
            timestamp=1700000001,
            embedding=test_embedding,
            app="App1",
            title="Title1",
            description="Description for entry 1",
        )

        # Insert entry WITHOUT description
        db.insert_entry(
            text="Text 2",
            timestamp=1700000002,
            embedding=test_embedding,
            app="App2",
            title="Title2",
        )

        entries = db.get_all_entries()
        assert len(entries) == 2

        # Entries are ordered by timestamp DESC, so entry 2 comes first
        entry_with_desc = next(e for e in entries if e.text == "Text 1")
        entry_without_desc = next(e for e in entries if e.text == "Text 2")

        assert entry_with_desc.description == "Description for entry 1"
        assert entry_without_desc.description is None


class TestRecallEntryModel:
    """Tests for the updated RecallEntry model."""

    def test_recall_entry_with_description(self):
        """Test creating RecallEntry with description field."""
        from openrecall.shared.models import RecallEntry

        embedding = np.random.rand(384).astype(np.float32)
        entry = RecallEntry(
            id=1,
            timestamp=1700000000,
            app="VS Code",
            title="test.py",
            text="print('hello')",
            description="User writing Python code",
            embedding=embedding,
        )

        assert entry.description == "User writing Python code"

    def test_recall_entry_without_description_defaults_to_none(self):
        """Test that description defaults to None when not provided."""
        from openrecall.shared.models import RecallEntry

        embedding = np.random.rand(384).astype(np.float32)
        entry = RecallEntry(
            timestamp=1700000000,
            app="VS Code",
            text="some text",
            embedding=embedding,
        )

        assert entry.description is None
