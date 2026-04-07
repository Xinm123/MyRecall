"""Tests for ClientSettingsStore."""

import pytest
from pathlib import Path
from openrecall.client.database.settings_store import ClientSettingsStore


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_client.db"
    return db_path


@pytest.fixture
def store(temp_db):
    """Create a ClientSettingsStore with test database."""
    return ClientSettingsStore(temp_db)


class TestClientSettingsStore:
    """Test suite for ClientSettingsStore."""

    def test_get_existing_key(self, store):
        """Test getting an existing key returns its value."""
        store.set("edge_base_url", "http://localhost:8083")
        result = store.get("edge_base_url")
        assert result == "http://localhost:8083"

    def test_get_nonexistent_key_returns_default(self, store):
        """Test getting a non-existent key returns default value."""
        result = store.get("nonexistent", "default_value")
        assert result == "default_value"

    def test_get_nonexistent_key_returns_empty_string(self, store):
        """Test getting a non-existent key without default returns empty string."""
        result = store.get("nonexistent")
        assert result == ""

    def test_set_creates_new_key(self, store):
        """Test setting a new key creates it."""
        store.set("new_key", "new_value")
        result = store.get("new_key")
        assert result == "new_value"

    def test_set_updates_existing_key(self, store):
        """Test setting an existing key updates its value."""
        store.set("edge_base_url", "http://localhost:8083")
        store.set("edge_base_url", "http://remote:8083")
        result = store.get("edge_base_url")
        assert result == "http://remote:8083"

    def test_get_all_returns_dict(self, store):
        """Test get_all returns all settings as a dictionary."""
        store.set("edge_base_url", "http://localhost:8083")
        store.set("another_key", "another_value")
        result = store.get_all()
        assert isinstance(result, dict)
        assert result["edge_base_url"] == "http://localhost:8083"
        assert result["another_key"] == "another_value"

    def test_get_all_includes_defaults(self, store):
        """Test get_all includes default settings."""
        result = store.get_all()
        assert "edge_base_url" in result

    def test_reset_to_defaults(self, store):
        """Test reset_to_defaults restores default values."""
        store.set("edge_base_url", "http://modified:8083")
        store.reset_to_defaults()
        result = store.get("edge_base_url")
        assert result == ""  # Default is empty string
