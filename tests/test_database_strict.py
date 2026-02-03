"""Tests for database type safety with RecallEntry."""

import os
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from openrecall.shared.models import RecallEntry


class TestRecallEntryModel:
    """Test the RecallEntry Pydantic model."""

    def test_embedding_from_bytes(self):
        """Verify bytes are converted to numpy array."""
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        entry = RecallEntry(
            timestamp=123,
            app="test",
            text="hello",
            embedding=arr.tobytes(),
        )
        assert isinstance(entry.embedding, np.ndarray)
        np.testing.assert_array_equal(entry.embedding, arr)

    def test_embedding_from_ndarray(self):
        """Verify numpy arrays pass through unchanged."""
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        entry = RecallEntry(
            timestamp=123,
            app="test",
            text="hello",
            embedding=arr,
        )
        assert isinstance(entry.embedding, np.ndarray)
        np.testing.assert_array_equal(entry.embedding, arr)

    def test_invalid_embedding_type_raises(self):
        """Verify invalid embedding types raise ValueError."""
        with pytest.raises(ValueError, match="must be bytes, np.ndarray or None"):
            RecallEntry(
                timestamp=123,
                app="test",
                text="hello",
                embedding="invalid",
            )


class TestDatabaseTypeConsistency:
    """Test that database functions return RecallEntry with numpy arrays."""

    def test_get_all_entries_returns_recall_entry(self):
        """Verify get_all_entries returns RecallEntry with np.ndarray embedding."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": tmp_dir}):
                # Reimport to get fresh settings
                import importlib
                import openrecall.shared.config
                importlib.reload(openrecall.shared.config)
                import openrecall.server.database
                importlib.reload(openrecall.server.database)
                
                from openrecall.server.database import create_db, insert_entry, get_all_entries
                from openrecall.shared.models import RecallEntry
                
                create_db()
                
                # Insert test data
                test_embedding = np.random.rand(384).astype(np.float32)
                test_timestamp = 1234567890
                insert_entry(
                    text="test text",
                    timestamp=test_timestamp,
                    embedding=test_embedding,
                    app="TestApp",
                    title="Test Title",
                )
                
                # Retrieve and verify
                entries = get_all_entries()
                assert len(entries) == 1
                assert isinstance(entries[0], RecallEntry)
                assert isinstance(entries[0].embedding, np.ndarray)
                np.testing.assert_array_almost_equal(entries[0].embedding, test_embedding)

    def test_get_entries_by_time_range_returns_recall_entry(self):
        """Verify get_entries_by_time_range returns RecallEntry with np.ndarray embedding."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": tmp_dir}):
                import importlib
                import openrecall.shared.config
                importlib.reload(openrecall.shared.config)
                import openrecall.server.database
                importlib.reload(openrecall.server.database)
                
                from openrecall.server.database import create_db, insert_entry, get_entries_by_time_range
                from openrecall.shared.models import RecallEntry
                
                create_db()
                
                # Insert test data
                test_embedding = np.random.rand(384).astype(np.float32)
                test_timestamp = 1234567890
                insert_entry(
                    text="test text",
                    timestamp=test_timestamp,
                    embedding=test_embedding,
                    app="TestApp",
                    title="Test Title",
                )
                
                # Retrieve and verify
                entries = get_entries_by_time_range(test_timestamp - 1, test_timestamp + 1)
                assert len(entries) == 1
                assert isinstance(entries[0], RecallEntry)
                assert isinstance(entries[0].embedding, np.ndarray)
                np.testing.assert_array_almost_equal(entries[0].embedding, test_embedding)

    def test_both_functions_return_same_type(self):
        """Verify both read functions return identical types."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": tmp_dir}):
                import importlib
                import openrecall.shared.config
                importlib.reload(openrecall.shared.config)
                import openrecall.server.database
                importlib.reload(openrecall.server.database)
                
                from openrecall.server.database import create_db, insert_entry, get_all_entries, get_entries_by_time_range
                
                create_db()
                
                test_embedding = np.random.rand(384).astype(np.float32)
                test_timestamp = 1234567890
                insert_entry(
                    text="test",
                    timestamp=test_timestamp,
                    embedding=test_embedding,
                    app="App",
                    title="Title",
                )
                
                all_entries = get_all_entries()
                range_entries = get_entries_by_time_range(test_timestamp - 1, test_timestamp + 1)
                
                assert type(all_entries[0]) == type(range_entries[0])
                assert type(all_entries[0].embedding) == type(range_entries[0].embedding)
