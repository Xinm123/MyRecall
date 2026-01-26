
import os
from pathlib import Path
from unittest.mock import patch
from openrecall.shared.config import Settings

def test_path_expansion():
    """Test that paths are expanded and resolved correctly."""
    # We mock the writable check to prevent fallback to tempdir during testing
    with patch("openrecall.shared.config.os.access", return_value=True):
        settings = Settings(
            OPENRECALL_SERVER_DATA_DIR="~/MRS_TEST"
        )
        assert settings.server_data_dir.is_absolute()
        assert str(settings.server_data_dir).endswith("MRS_TEST")

def test_env_override(monkeypatch):
    """Test that environment variables override defaults."""
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", "/tmp/OVERRIDE_MRS")
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", "/tmp/OVERRIDE_MRC")
    
    settings = Settings()
    
    assert str(settings.server_data_dir).endswith("/tmp/OVERRIDE_MRS")
    assert str(settings.client_data_dir).endswith("/tmp/OVERRIDE_MRC")

def test_directory_creation(mock_settings):
    """Test that directories are automatically created."""
    # mock_settings fixture already initializes settings, which triggers ensure_directories
    assert mock_settings.server_data_dir.exists()
    assert mock_settings.client_data_dir.exists()
    assert (mock_settings.server_data_dir / "screenshots").exists()
    assert (mock_settings.server_data_dir / "db").exists()
    # lancedb dir is created by settings now
    assert (mock_settings.server_data_dir / "lancedb").exists()

def test_legacy_path_compatibility():
    """Test backward compatibility for base_path_legacy."""
    settings = Settings(OPENRECALL_DATA_DIR="/tmp/LEGACY_PATH")
    assert str(settings.base_path_legacy).endswith("/tmp/LEGACY_PATH")
    # base_path property should return legacy path if set
    assert str(settings.base_path).endswith("/tmp/LEGACY_PATH")

def test_default_behavior():
    """Test default values without env vars."""
    # Clear env vars that might be set by the environment
    env_vars_to_clear = ["OPENRECALL_SERVER_DATA_DIR", "OPENRECALL_CLIENT_DATA_DIR", "OPENRECALL_DATA_DIR"]
    original_environ = os.environ.copy()
    for key in env_vars_to_clear:
        if key in os.environ:
            del os.environ[key]
            
    try:
        # Mock writable check to avoid fallback to temp paths
        with patch("openrecall.shared.config.os.access", return_value=True):
            settings = Settings()
            # Should default to ~/MRS and ~/MRC (expanded)
            assert settings.server_data_dir == Path.home() / "MRS"
            assert settings.client_data_dir == Path.home() / "MRC"
    finally:
        os.environ.update(original_environ)
