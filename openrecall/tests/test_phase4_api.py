"""Phase 4 API Implementation Tests.

Tests for HTTP communication between client and server:
- API endpoints (health, upload)
- HTTPUploader client
- Client-server integration
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Test configuration before importing modules
with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": tempfile.mkdtemp()}):
    from openrecall.shared.config import Settings
    from openrecall.server.app import app
    from openrecall.server.api import api_bp
    from openrecall.client.uploader import HTTPUploader, get_uploader


class TestAPISettings:
    """Tests for api_url configuration."""

    def test_default_api_url(self, tmp_path, monkeypatch):
        """Test default API URL."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        settings = Settings()
        assert settings.api_url == "http://localhost:8083/api"

    def test_custom_api_url(self, tmp_path, monkeypatch):
        """Test custom API URL from environment."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_API_URL", "http://myserver:9000/api")
        settings = Settings()
        assert settings.api_url == "http://myserver:9000/api"


class TestHealthEndpoint:
    """Tests for /api/health endpoint."""

    @pytest.fixture
    def client(self):
        """Create Flask test client."""
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_health_returns_ok(self, client):
        """Test health check returns ok status."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "ok"

    def test_health_returns_json(self, client):
        """Test health check returns JSON content type."""
        response = client.get("/api/health")
        assert response.content_type == "application/json"


class TestUploadEndpoint:
    """Tests for /api/upload endpoint."""

    @pytest.fixture
    def client(self):
        """Create Flask test client."""
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_upload_missing_json(self, client):
        """Test upload fails without JSON body."""
        response = client.post("/api/upload")
        # Flask returns 415 when content-type is missing, or 400 with empty JSON
        assert response.status_code in (400, 415)

    def test_upload_missing_fields(self, client):
        """Test upload fails with missing required fields."""
        response = client.post(
            "/api/upload",
            data=json.dumps({"image": [1, 2, 3]}),
            content_type="application/json"
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "Missing field" in data["message"]

    @patch("openrecall.server.api.extract_text_from_image")
    @patch("openrecall.server.api.get_embedding")
    @patch("openrecall.server.api.insert_entry")
    def test_upload_success_with_text(self, mock_insert, mock_embed, mock_ocr, client):
        """Test successful upload with OCR text."""
        mock_ocr.return_value = "Sample extracted text"
        mock_embed.return_value = np.random.rand(384).astype(np.float32)

        test_image = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
        payload = {
            "image": test_image.flatten().tolist(),
            "shape": list(test_image.shape),
            "dtype": "uint8",
            "timestamp": 1234567890,
            "active_app": "TestApp",
            "active_window": "Test Window",
        }

        response = client.post(
            "/api/upload",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "ok"
        assert "stored" in data["message"].lower()
        mock_insert.assert_called_once()

    @patch("openrecall.server.api.extract_text_from_image")
    def test_upload_skips_empty_text(self, mock_ocr, client):
        """Test upload skips storage when no text extracted."""
        mock_ocr.return_value = "   "  # Whitespace only

        test_image = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
        payload = {
            "image": test_image.flatten().tolist(),
            "shape": list(test_image.shape),
            "dtype": "uint8",
            "timestamp": 1234567890,
            "active_app": "TestApp",
            "active_window": "Test Window",
        }

        response = client.post(
            "/api/upload",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "ok"
        assert "skipped" in data["message"].lower()


class TestHTTPUploader:
    """Tests for HTTPUploader client."""

    def test_init_default_url(self, tmp_path, monkeypatch):
        """Test uploader uses settings URL by default."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        uploader = HTTPUploader()
        assert "localhost" in uploader.api_url
        assert "/api" in uploader.api_url

    def test_init_custom_url(self, tmp_path, monkeypatch):
        """Test uploader accepts custom URL."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        uploader = HTTPUploader(api_url="http://custom:5000/api")
        assert uploader.api_url == "http://custom:5000/api"

    @patch("openrecall.client.uploader.requests.get")
    def test_health_check_success(self, mock_get, tmp_path, monkeypatch):
        """Test health check returns True on success."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_response

        uploader = HTTPUploader()
        assert uploader.health_check() is True

    @patch("openrecall.client.uploader.requests.get")
    def test_health_check_failure(self, mock_get, tmp_path, monkeypatch):
        """Test health check returns False on failure."""
        import requests as req
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        mock_get.side_effect = req.RequestException("Connection refused")

        uploader = HTTPUploader()
        assert uploader.health_check() is False

    @patch("openrecall.client.uploader.requests.post")
    def test_upload_screenshot_success(self, mock_post, tmp_path, monkeypatch):
        """Test upload returns True on success."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        uploader = HTTPUploader()
        test_image = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)

        result = uploader.upload_screenshot(
            image=test_image,
            timestamp=1234567890,
            active_app="TestApp",
            active_window="Test Window",
        )

        assert result is True
        mock_post.assert_called_once()

    @patch("openrecall.client.uploader.requests.post")
    def test_upload_screenshot_failure(self, mock_post, tmp_path, monkeypatch):
        """Test upload returns False on failure."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        uploader = HTTPUploader()
        test_image = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)

        result = uploader.upload_screenshot(
            image=test_image,
            timestamp=1234567890,
            active_app="TestApp",
            active_window="Test Window",
        )

        assert result is False

    @patch.object(HTTPUploader, "health_check")
    def test_wait_for_server_immediate_success(self, mock_health, tmp_path, monkeypatch):
        """Test wait_for_server returns immediately when healthy."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        mock_health.return_value = True

        uploader = HTTPUploader()
        result = uploader.wait_for_server(max_retries=5, retry_delay=0.01)

        assert result is True
        assert mock_health.call_count == 1

    @patch.object(HTTPUploader, "health_check")
    def test_wait_for_server_eventual_success(self, mock_health, tmp_path, monkeypatch):
        """Test wait_for_server retries until success."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        mock_health.side_effect = [False, False, True]

        uploader = HTTPUploader()
        result = uploader.wait_for_server(max_retries=5, retry_delay=0.01)

        assert result is True
        assert mock_health.call_count == 3

    @patch.object(HTTPUploader, "health_check")
    def test_wait_for_server_timeout(self, mock_health, tmp_path, monkeypatch):
        """Test wait_for_server returns False after max retries."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        mock_health.return_value = False

        uploader = HTTPUploader()
        result = uploader.wait_for_server(max_retries=3, retry_delay=0.01)

        assert result is False
        assert mock_health.call_count == 3


class TestClientRecorderNoServerImports:
    """Tests to ensure client recorder doesn't import server modules directly."""

    def test_recorder_no_database_import(self):
        """Test recorder doesn't import database module."""
        import openrecall.client.recorder as recorder_module
        import sys
        
        # Check the module's imports don't include server modules
        recorder_source = open(recorder_module.__file__).read()
        assert "from openrecall.server.database" not in recorder_source
        assert "import openrecall.server.database" not in recorder_source

    def test_recorder_no_nlp_import(self):
        """Test recorder doesn't import nlp module."""
        import openrecall.client.recorder as recorder_module
        
        recorder_source = open(recorder_module.__file__).read()
        assert "from openrecall.server.nlp" not in recorder_source
        assert "import openrecall.server.nlp" not in recorder_source

    def test_recorder_no_ocr_import(self):
        """Test recorder doesn't import ocr module."""
        import openrecall.client.recorder as recorder_module
        
        recorder_source = open(recorder_module.__file__).read()
        assert "from openrecall.server.ocr" not in recorder_source
        assert "import openrecall.server.ocr" not in recorder_source

    def test_recorder_uses_uploader(self):
        """Test recorder uses buffer/consumer pattern (Phase 5 upgrade)."""
        import openrecall.client.recorder as recorder_module
        
        recorder_source = open(recorder_module.__file__).read()
        # Phase 5: recorder now uses buffer and consumer instead of direct uploader
        assert "from openrecall.client.buffer" in recorder_source
        assert "from openrecall.client.consumer" in recorder_source


class TestAPIBlueprintRegistration:
    """Tests for API blueprint integration."""

    def test_api_blueprint_registered(self):
        """Test API blueprint is registered with Flask app."""
        assert "api" in app.blueprints

    def test_api_routes_exist(self):
        """Test expected API routes are registered."""
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert "/api/health" in rules
        assert "/api/upload" in rules


class TestGetUploaderSingleton:
    """Tests for get_uploader singleton function."""

    def test_get_uploader_returns_instance(self, tmp_path, monkeypatch):
        """Test get_uploader returns HTTPUploader instance."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        
        # Reset singleton for test
        import openrecall.client.uploader as uploader_module
        uploader_module._uploader = None
        
        uploader = get_uploader()
        assert isinstance(uploader, HTTPUploader)

    def test_get_uploader_same_instance(self, tmp_path, monkeypatch):
        """Test get_uploader returns same instance on multiple calls."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        
        # Reset singleton for test
        import openrecall.client.uploader as uploader_module
        uploader_module._uploader = None
        
        uploader1 = get_uploader()
        uploader2 = get_uploader()
        assert uploader1 is uploader2
