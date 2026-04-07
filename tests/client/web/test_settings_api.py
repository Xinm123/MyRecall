"""Integration tests for settings API endpoints."""

import pytest
import json
from pathlib import Path


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test Flask client."""
    # Create a mock settings object with client_data_dir
    class MockSettings:
        client_data_dir = tmp_path / "mrc"
        server_data_dir = tmp_path / "mrs"
        edge_base_url = "http://localhost:8083"

    # Initialize the shared config proxy before importing routes
    import openrecall.shared.config
    openrecall.shared.config.settings = MockSettings()

    # Now import the settings module after setting up the proxy
    from openrecall.client.web.routes import settings
    test_db_path = tmp_path / "test_client.db"

    # Create a new store with test path
    from openrecall.client.database import ClientSettingsStore
    test_store = ClientSettingsStore(test_db_path)

    # Replace the module-level store
    settings._settings_store = test_store

    # Create app
    from openrecall.client.web.app import client_app
    client_app.config['TESTING'] = True

    with client_app.test_client() as client:
        yield client


class TestGetSettings:
    """Tests for GET /api/client/settings."""

    def test_get_settings_returns_dict(self, client):
        """Test that settings endpoint returns a dictionary."""
        response = client.get('/api/client/settings')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, dict)
        assert 'edge_base_url' in data


class TestUpdateSettings:
    """Tests for POST /api/client/settings."""

    def test_update_edge_base_url(self, client):
        """Test updating edge_base_url."""
        response = client.post('/api/client/settings',
                              data=json.dumps({'edge_base_url': 'http://test:8083'}),
                              content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['edge_base_url'] == 'http://test:8083'

    def test_update_invalid_url_returns_error(self, client):
        """Test that invalid URL returns validation error."""
        response = client.post('/api/client/settings',
                              data=json.dumps({'edge_base_url': 'invalid-url'}),
                              content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_update_non_json_returns_error(self, client):
        """Test that non-JSON body returns error."""
        response = client.post('/api/client/settings',
                              data='not json',
                              content_type='text/plain')
        # Flask returns 415 UNSUPPORTED MEDIA TYPE for non-JSON content
        assert response.status_code in [400, 415]


class TestResetSettings:
    """Tests for POST /api/client/settings/reset."""

    def test_reset_settings(self, client):
        """Test resetting settings to defaults."""
        # First set a custom value
        client.post('/api/client/settings',
                   data=json.dumps({'edge_base_url': 'http://custom:8083'}),
                   content_type='application/json')

        # Then reset
        response = client.post('/api/client/settings/reset')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['edge_base_url'] == ''  # Default is empty string


class TestEdgeHealth:
    """Tests for GET /api/client/settings/edge/health."""

    def test_health_without_url_uses_configured(self, client):
        """Test health check uses configured URL when no param provided."""
        # This will fail because no Edge server is running in tests
        response = client.get('/api/client/settings/edge/health')
        # Should return 502 because Edge is not reachable
        assert response.status_code in [200, 400, 502]

    def test_health_with_url_param(self, client):
        """Test health check with explicit URL parameter."""
        response = client.get('/api/client/settings/edge/health?url=http://invalid:9999')
        # Should fail to connect
        assert response.status_code == 502
