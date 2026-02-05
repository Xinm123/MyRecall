"""Unit tests for M0 client metadata upgrades."""

import hashlib
import io
import platform
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from openrecall.client.uploader import (
    CLIENT_VERSION,
    HTTPUploader,
    _compute_image_hash,
    _get_client_tz,
    _get_device_id,
    get_client_capabilities,
)


class TestM0ClientMetadata:
    """Test suite for M0 client metadata generation."""

    def test_compute_image_hash_returns_sha256_hex(self):
        """Test that image hash is computed correctly."""
        test_bytes = b"test image data"
        expected = hashlib.sha256(test_bytes).hexdigest()
        assert _compute_image_hash(test_bytes) == expected
        assert len(_compute_image_hash(test_bytes)) == 64

    def test_get_device_id_uses_settings_when_set(self, monkeypatch):
        """Test device ID uses settings.device_id when configured."""
        from openrecall.shared import config

        monkeypatch.setattr(config.settings, "device_id", "my-test-device")
        assert _get_device_id() == "my-test-device"

    def test_get_device_id_falls_back_to_hostname(self, monkeypatch):
        """Test device ID falls back to sanitized hostname."""
        from openrecall.shared import config

        monkeypatch.setattr(config.settings, "device_id", "")
        device_id = _get_device_id()
        assert len(device_id) >= 3
        assert len(device_id) <= 64
        assert all(c.isalnum() or c in "_-" for c in device_id)

    def test_get_client_tz_returns_string(self):
        """Test client timezone returns a string."""
        tz = _get_client_tz()
        assert isinstance(tz, str)
        assert len(tz) > 0

    def test_get_client_capabilities_structure(self, monkeypatch):
        """Test client capabilities dict has required fields."""
        from openrecall.shared import config

        monkeypatch.setattr(config.settings, "primary_monitor_only", True)
        caps = get_client_capabilities()

        assert caps["client_version"] == CLIENT_VERSION
        assert "platform" in caps
        assert "capture" in caps
        assert "upload" in caps
        assert caps["capture"]["primary_monitor_only"] is True
        assert caps["upload"]["formats"] == ["png"]
        assert caps["upload"]["hash"] == "sha256"


class TestM0UploaderMetadata:
    """Test suite for M0 uploader metadata generation."""

    def test_client_builds_upload_metadata_includes_device_and_hash(self, monkeypatch):
        """Test that upload includes M0 metadata fields."""
        from openrecall.shared import config

        monkeypatch.setattr(config.settings, "device_id", "test-device-01")
        monkeypatch.setattr(config.settings, "device_token", "test-token-123")
        monkeypatch.setattr(config.settings, "api_url", "http://localhost:8083/api")

        uploader = HTTPUploader()

        test_image = np.zeros((100, 100, 3), dtype=np.uint8)
        test_image[50, 50] = [255, 0, 0]

        captured_request = {}

        def mock_post(url, files=None, data=None, headers=None, timeout=None):
            captured_request["url"] = url
            captured_request["files"] = files
            captured_request["data"] = data
            captured_request["headers"] = headers
            captured_request["timeout"] = timeout
            mock_response = MagicMock()
            mock_response.status_code = 202
            return mock_response

        with patch("openrecall.client.uploader.requests.post", side_effect=mock_post):
            result = uploader.upload_screenshot(
                image=test_image,
                timestamp=1738752000,
                active_app="TestApp",
                active_window="TestWindow",
                client_seq=42,
            )

        assert result is True
        assert "url" in captured_request
        assert captured_request["url"] == "http://localhost:8083/api/upload"

        assert "headers" in captured_request
        assert captured_request["headers"]["Authorization"] == "Bearer test-token-123"

        import json

        metadata_str = captured_request["data"]["metadata"]
        metadata = json.loads(metadata_str)

        assert metadata["device_id"] == "test-device-01"
        assert metadata["client_ts"] == 1738752000 * 1000
        assert "client_tz" in metadata
        assert "image_hash" in metadata
        assert len(metadata["image_hash"]) == 64
        assert metadata["app_name"] == "TestApp"
        assert metadata["window_title"] == "TestWindow"
        assert metadata["timestamp"] == 1738752000
        assert metadata["client_seq"] == 42

    def test_upload_without_token_sends_no_auth_header(self, monkeypatch):
        """Test that upload without device_token sends no Authorization header."""
        from openrecall.shared import config

        monkeypatch.setattr(config.settings, "device_id", "test-device")
        monkeypatch.setattr(config.settings, "device_token", "")
        monkeypatch.setattr(config.settings, "api_url", "http://localhost:8083/api")

        uploader = HTTPUploader()
        test_image = np.zeros((10, 10, 3), dtype=np.uint8)

        captured_headers = {}

        def mock_post(url, files=None, data=None, headers=None, timeout=None):
            captured_headers.update(headers or {})
            mock_response = MagicMock()
            mock_response.status_code = 202
            return mock_response

        with patch("openrecall.client.uploader.requests.post", side_effect=mock_post):
            uploader.upload_screenshot(
                image=test_image,
                timestamp=1738752000,
                active_app="App",
                active_window="Window",
            )

        assert "Authorization" not in captured_headers

    def test_upload_image_hash_matches_png_bytes(self, monkeypatch):
        """Test that image_hash matches actual PNG bytes sent."""
        from openrecall.shared import config

        monkeypatch.setattr(config.settings, "device_id", "test-device")
        monkeypatch.setattr(config.settings, "device_token", "")
        monkeypatch.setattr(config.settings, "api_url", "http://localhost:8083/api")

        uploader = HTTPUploader()
        test_image = np.full((50, 50, 3), 128, dtype=np.uint8)

        captured_data = {}

        def mock_post(url, files=None, data=None, headers=None, timeout=None):
            captured_data["files"] = files
            captured_data["data"] = data
            mock_response = MagicMock()
            mock_response.status_code = 202
            return mock_response

        with patch("openrecall.client.uploader.requests.post", side_effect=mock_post):
            uploader.upload_screenshot(
                image=test_image,
                timestamp=1738752000,
                active_app="App",
                active_window="Window",
            )

        import json

        metadata = json.loads(captured_data["data"]["metadata"])
        sent_hash = metadata["image_hash"]

        file_tuple = captured_data["files"]["file"]
        file_obj = file_tuple[1]
        png_bytes = file_obj.read()
        expected_hash = hashlib.sha256(png_bytes).hexdigest()

        assert sent_hash == expected_hash
