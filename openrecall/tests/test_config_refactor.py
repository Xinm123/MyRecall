"""Tests for the refactored configuration system."""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest


class TestSettingsDefaults:
    """Test default configuration values."""

    def test_default_base_path_is_myrecall_data(self):
        """Verify default base_path points to ~/.myrecall_data."""
        # Import with clean environment to get defaults
        with mock.patch.dict(os.environ, {}, clear=True):
            # Need to reimport to get fresh Settings instance
            from openrecall.config import Settings
            
            # Create new Settings instance with defaults
            new_settings = Settings()
            expected_path = Path.home() / ".myrecall_data"
            assert new_settings.base_path == expected_path

    def test_default_port(self):
        """Verify default port is 8083."""
        from openrecall.config import Settings
        
        with mock.patch.dict(os.environ, {}, clear=True):
            test_settings = Settings()
            assert test_settings.port == 8083

    def test_default_primary_monitor_only(self):
        """Verify primary_monitor_only defaults to False."""
        from openrecall.config import Settings
        
        with mock.patch.dict(os.environ, {}, clear=True):
            test_settings = Settings()
            assert test_settings.primary_monitor_only is False


class TestSettingsAutoCreation:
    """Test automatic directory creation."""

    def test_directories_created_on_init(self):
        """Verify all required directories are created when Settings is initialized."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_path = Path(tmp_dir) / "test_myrecall"
            
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": str(custom_path)}):
                from openrecall.config import Settings
                
                test_settings = Settings()
                
                # Verify base path
                assert test_settings.base_path == custom_path
                assert custom_path.exists()
                
                # Verify screenshots directory
                screenshots_dir = custom_path / "screenshots"
                assert screenshots_dir.exists()
                assert screenshots_dir.is_dir()
                
                # Verify buffer directory
                buffer_dir = custom_path / "buffer"
                assert buffer_dir.exists()
                assert buffer_dir.is_dir()
                
                # Verify db parent directory
                db_dir = custom_path / "db"
                assert db_dir.exists()
                assert db_dir.is_dir()
                
                # Verify models directory
                models_dir = custom_path / "models"
                assert models_dir.exists()
                assert models_dir.is_dir()

    def test_ensure_directories_is_idempotent(self):
        """Verify calling ensure_directories multiple times is safe."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_path = Path(tmp_dir) / "test_myrecall"
            
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": str(custom_path)}):
                from openrecall.config import Settings
                
                test_settings = Settings()
                
                # Call ensure_directories again - should not raise
                test_settings.ensure_directories()
                test_settings.ensure_directories()
                
                # All directories should still exist
                assert custom_path.exists()
                assert test_settings.screenshots_path.exists()
                assert test_settings.buffer_path.exists()
                assert test_settings.db_path.parent.exists()


class TestSettingsEnvOverride:
    """Test environment variable overrides."""

    def test_env_override_base_path(self):
        """Verify OPENRECALL_DATA_DIR overrides base_path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_path = Path(tmp_dir) / "custom_data"
            
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": str(custom_path)}):
                from openrecall.config import Settings
                
                test_settings = Settings()
                assert test_settings.base_path == custom_path

    def test_env_override_port(self):
        """Verify OPENRECALL_PORT overrides port."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {
                "OPENRECALL_DATA_DIR": tmp_dir,
                "OPENRECALL_PORT": "9999"
            }):
                from openrecall.config import Settings
                
                test_settings = Settings()
                assert test_settings.port == 9999

    def test_env_override_primary_monitor_only(self):
        """Verify OPENRECALL_PRIMARY_MONITOR_ONLY overrides primary_monitor_only."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {
                "OPENRECALL_DATA_DIR": tmp_dir,
                "OPENRECALL_PRIMARY_MONITOR_ONLY": "true"
            }):
                from openrecall.config import Settings
                
                test_settings = Settings()
                assert test_settings.primary_monitor_only is True


class TestSettingsComputedProperties:
    """Test computed property paths."""

    def test_screenshots_path_computed_correctly(self):
        """Verify screenshots_path is base_path / 'screenshots'."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": tmp_dir}):
                from openrecall.config import Settings
                
                test_settings = Settings()
                expected = Path(tmp_dir) / "screenshots"
                assert test_settings.screenshots_path == expected

    def test_db_path_computed_correctly(self):
        """Verify db_path is base_path / 'db' / 'recall.db'."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": tmp_dir}):
                from openrecall.config import Settings
                
                test_settings = Settings()
                expected = Path(tmp_dir) / "db" / "recall.db"
                assert test_settings.db_path == expected

    def test_buffer_path_computed_correctly(self):
        """Verify buffer_path is base_path / 'buffer'."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": tmp_dir}):
                from openrecall.config import Settings
                
                test_settings = Settings()
                expected = Path(tmp_dir) / "buffer"
                assert test_settings.buffer_path == expected

    def test_model_cache_path_computed_correctly(self):
        """Verify model_cache_path is base_path / 'models'."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": tmp_dir}):
                from openrecall.config import Settings
                
                test_settings = Settings()
                expected = Path(tmp_dir) / "models"
                assert test_settings.model_cache_path == expected
