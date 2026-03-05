"""Tests for runtime configuration infrastructure.

Verifies RuntimeSettings singleton and API endpoints work correctly.
"""

import time
import json

import pytest
from openrecall.server.config_runtime import RuntimeSettings, runtime_settings


class TestRuntimeSettings:
    """Unit tests for RuntimeSettings class."""
    
    def test_singleton_initialization(self):
        """Test RuntimeSettings initializes with correct default values."""
        settings = RuntimeSettings()
        
        assert settings.recording_enabled is True
        assert settings.upload_enabled is True
        assert settings.ai_processing_enabled is True
        assert settings.ui_show_ai is True
        assert isinstance(settings.last_heartbeat, float)
    
    def test_to_dict_method(self):
        """Test to_dict() returns all fields as dictionary."""
        settings = RuntimeSettings()
        config_dict = settings.to_dict()
        
        assert "recording_enabled" in config_dict
        assert "upload_enabled" in config_dict
        assert "ai_processing_enabled" in config_dict
        assert "ui_show_ai" in config_dict
        assert "last_heartbeat" in config_dict
        
        assert config_dict["recording_enabled"] is True
        assert config_dict["upload_enabled"] is True
    
    def test_field_modification(self):
        """Test that fields can be modified safely."""
        settings = RuntimeSettings()
        original_heartbeat = settings.last_heartbeat
        
        settings.recording_enabled = False
        assert settings.recording_enabled is False
        
        settings.upload_enabled = False
        assert settings.upload_enabled is False
        
        new_time = time.time()
        settings.last_heartbeat = new_time
        assert settings.last_heartbeat == new_time
    
    def test_thread_safety_lock_exists(self):
        """Test that RuntimeSettings has thread safety lock."""
        settings = RuntimeSettings()
        assert hasattr(settings, '_lock')
        assert settings._lock is not None


class TestRuntimeConfigAPI:
    """Integration tests for runtime config API endpoints."""
    
    @pytest.fixture(autouse=True)
    def reset_runtime_settings(self):
        """Reset runtime settings before each test."""
        # Reset to defaults before test
        runtime_settings.recording_enabled = True
        runtime_settings.upload_enabled = True
        runtime_settings.ai_processing_enabled = True
        runtime_settings.ui_show_ai = True
        yield
        # Reset to defaults after test
        runtime_settings.recording_enabled = True
        runtime_settings.upload_enabled = True
        runtime_settings.ai_processing_enabled = True
        runtime_settings.ui_show_ai = True
    
    def test_get_config_endpoint(self, client):
        """Test GET /api/config returns current configuration."""
        response = client.get('/api/config')
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Check all expected fields are present
        assert "recording_enabled" in data
        assert "upload_enabled" in data
        assert "ai_processing_enabled" in data
        assert "ui_show_ai" in data
        assert "last_heartbeat" in data
        assert "client_online" in data
        
        # Check types
        assert isinstance(data["recording_enabled"], bool)
        assert isinstance(data["upload_enabled"], bool)
        assert isinstance(data["client_online"], bool)
        assert isinstance(data["last_heartbeat"], (int, float))
    
    def test_post_config_single_field(self, client):
        """Test POST /api/config updates a single field."""
        # First, get current state
        response = client.get('/api/config')
        original_config = response.get_json()
        
        # Update recording_enabled to false
        update_data = {"recording_enabled": False}
        response = client.post(
            '/api/config',
            data=json.dumps(update_data),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        updated_config = response.get_json()
        assert updated_config["recording_enabled"] is False
        
        # Verify other fields unchanged
        assert updated_config["upload_enabled"] == original_config["upload_enabled"]
        assert updated_config["ai_processing_enabled"] == original_config["ai_processing_enabled"]
    
    def test_post_config_multiple_fields(self, client):
        """Test POST /api/config updates multiple fields."""
        update_data = {
            "recording_enabled": False,
            "upload_enabled": False,
            "ai_processing_enabled": False
        }
        response = client.post(
            '/api/config',
            data=json.dumps(update_data),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        updated_config = response.get_json()
        assert updated_config["recording_enabled"] is False
        assert updated_config["upload_enabled"] is False
        assert updated_config["ai_processing_enabled"] is False
    
    def test_post_config_invalid_field(self, client):
        """Test POST /api/config rejects unknown fields."""
        update_data = {"unknown_field": True}
        response = client.post(
            '/api/config',
            data=json.dumps(update_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data["status"]
        assert "Unknown field" in data["message"]
    
    def test_post_config_invalid_type(self, client):
        """Test POST /api/config rejects non-boolean values."""
        update_data = {"recording_enabled": "not a boolean"}
        response = client.post(
            '/api/config',
            data=json.dumps(update_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data["status"]
        assert "must be boolean" in data["message"]
    
    def test_post_config_invalid_json(self, client):
        """Test POST /api/config rejects invalid JSON."""
        response = client.post(
            '/api/config',
            data='invalid json',
            content_type='application/json'
        )
        
        assert response.status_code == 400
    
    def test_post_heartbeat(self, client):
        """Test POST /api/heartbeat updates last_heartbeat."""
        # Get initial config
        response = client.get('/api/config')
        initial_config = response.get_json()
        initial_heartbeat = initial_config["last_heartbeat"]
        
        # Wait a bit and send heartbeat
        time.sleep(0.1)
        response = client.post('/api/heartbeat')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert "config" in data
        
        # Verify heartbeat was updated
        updated_heartbeat = data["config"]["last_heartbeat"]
        assert updated_heartbeat > initial_heartbeat
        
        # Verify client_online is true (within 15 seconds)
        assert data["config"]["client_online"] is True
    
    def test_client_online_calculation(self, client):
        """Test client_online field calculation."""
        # Send heartbeat to make sure it's recent
        client.post('/api/heartbeat')
        
        # Get config - should show client_online: true
        response = client.get('/api/config')
        data = response.get_json()
        assert data["client_online"] is True
    
    def test_config_persistence(self, client):
        """Test that configuration persists across multiple requests."""
        # Set recording_enabled to false
        update_data = {"recording_enabled": False}
        response = client.post(
            '/api/config',
            data=json.dumps(update_data),
            content_type='application/json'
        )
        assert response.get_json()["recording_enabled"] is False
        
        # Fetch config again - should still be false
        response = client.get('/api/config')
        assert response.get_json()["recording_enabled"] is False
        
        # Make another update
        update_data = {"upload_enabled": False}
        response = client.post(
            '/api/config',
            data=json.dumps(update_data),
            content_type='application/json'
        )
        
        # Verify both changes persisted
        response = client.get('/api/config')
        data = response.get_json()
        assert data["recording_enabled"] is False
        assert data["upload_enabled"] is False
        assert data["ai_processing_enabled"] is True  # Unchanged


# Fixtures for Flask test client
@pytest.fixture
def app():
    """Create and configure test app."""
    try:
        from openrecall.server.app import app as flask_app
    except ImportError:
        # If import fails, skip the integration tests
        pytest.skip("Could not import Flask app")
    
    flask_app.config['TESTING'] = True
    return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()
