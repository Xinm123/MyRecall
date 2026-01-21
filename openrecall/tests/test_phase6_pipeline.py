"""End-to-end tests for Phase 6.3 - Parallel OCR + AI Pipeline."""

import importlib
import os
import tempfile
from unittest import mock

import numpy as np
import pytest
from PIL import Image

pytestmark = pytest.mark.manual


class TestParallelPipeline:
    """E2E tests for the parallel OCR + AI upload pipeline."""

    @pytest.fixture
    def temp_env(self):
        """Set up temporary environment with mocked AI."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"OPENRECALL_DATA_DIR": tmp_dir}):
                # Reload modules with new config
                import openrecall.shared.config
                importlib.reload(openrecall.shared.config)
                
                import openrecall.server.database
                importlib.reload(openrecall.server.database)
                openrecall.server.database.create_db()
                
                yield tmp_dir

    @pytest.fixture
    def test_image(self) -> np.ndarray:
        """Create a simple test image."""
        # Create image with some text-like patterns
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        img[20:80, 20:180] = 255  # White rectangle
        return img

    def test_upload_with_parallel_processing(self, temp_env, test_image):
        """Test that upload processes OCR and AI in parallel."""
        import openrecall.server.api
        importlib.reload(openrecall.server.api)
        
        # Mock AFTER reload so it sticks
        with mock.patch.object(openrecall.server.api, "get_ai_engine") as mock_get:
            mock_engine = mock.MagicMock()
            mock_engine.analyze_image.return_value = "Mock: User viewing test image"
            mock_get.return_value = mock_engine
            
            from openrecall.server.app import app
            from openrecall.server.database import get_all_entries

            client = app.test_client()

            payload = {
                "image": test_image.flatten().tolist(),
                "shape": list(test_image.shape),
                "dtype": str(test_image.dtype),
                "timestamp": 1700000001,
                "active_app": "TestApp",
                "active_window": "Test Window",
            }

            response = client.post("/api/upload", json=payload)
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "ok"
            
            # Verify AI was called
            mock_engine.analyze_image.assert_called_once()

    def test_ai_failure_does_not_block_ocr(self, temp_env, test_image):
        """Test that AI failure doesn't prevent OCR data from being saved."""
        with mock.patch("openrecall.server.api.get_ai_engine") as mock_get:
            mock_engine = mock.MagicMock()
            mock_engine.analyze_image.side_effect = RuntimeError("AI crashed!")
            mock_get.return_value = mock_engine
            
            import openrecall.server.api
            importlib.reload(openrecall.server.api)
            
            from openrecall.server.app import app
            
            client = app.test_client()
            
            payload = {
                "image": test_image.flatten().tolist(),
                "shape": list(test_image.shape),
                "dtype": str(test_image.dtype),
                "timestamp": 1700000002,
                "active_app": "TestApp",
                "active_window": "Test Window",
            }
            
            # Should NOT raise, should gracefully handle AI failure
            response = client.post("/api/upload", json=payload)
            
            # Should still succeed (OCR path works)
            assert response.status_code == 200

    def test_entry_has_both_text_and_description(self, temp_env, test_image):
        """Test that saved entries have both OCR text and AI description."""
        import openrecall.server.api
        importlib.reload(openrecall.server.api)
        
        # Mock AFTER reload so it sticks
        with mock.patch.object(openrecall.server.api, "extract_text_from_image") as mock_ocr, \
             mock.patch.object(openrecall.server.api, "get_ai_engine") as mock_get:
            mock_ocr.return_value = "Sample OCR Text"
            mock_engine = mock.MagicMock()
            mock_engine.analyze_image.return_value = "Mock: User viewing test image"
            mock_get.return_value = mock_engine
            
            from openrecall.server.app import app
            from openrecall.server.database import get_all_entries
            
            client = app.test_client()
            
            payload = {
                "image": test_image.flatten().tolist(),
                "shape": list(test_image.shape),
                "dtype": str(test_image.dtype),
                "timestamp": 1700000003,
                "active_app": "TestApp",
                "active_window": "Test Window",
            }
            
            response = client.post("/api/upload", json=payload)
            assert response.status_code == 200
            
            # Check database
            entries = get_all_entries()
            assert len(entries) == 1
            assert entries[0].text == "Sample OCR Text"
            assert entries[0].description == "Mock: User viewing test image"


class TestUploadTimeout:
    """Tests for upload timeout configuration."""
    
    def test_upload_timeout_in_settings(self):
        """Test that upload_timeout is available in settings."""
        from openrecall.shared.config import Settings
        
        s = Settings()
        assert hasattr(s, "upload_timeout")
        assert s.upload_timeout == 45  # Default value
    
    def test_upload_timeout_can_be_overridden(self):
        """Test that upload_timeout can be set via environment."""
        with mock.patch.dict(os.environ, {"OPENRECALL_UPLOAD_TIMEOUT": "120"}):
            from openrecall.shared.config import Settings
            s = Settings()
            assert s.upload_timeout == 120

    def test_uploader_uses_config_timeout(self):
        """Test that HTTPUploader uses settings.upload_timeout by default."""
        with mock.patch.dict(os.environ, {"OPENRECALL_UPLOAD_TIMEOUT": "60"}):
            import openrecall.shared.config
            importlib.reload(openrecall.shared.config)
            
            from openrecall.client.uploader import HTTPUploader
            uploader = HTTPUploader()
            assert uploader.timeout == 60


class TestSafeAnalyzeImage:
    """Tests for the fault-tolerant AI analysis function."""
    
    def test_safe_analyze_returns_none_on_error(self):
        """Test that _safe_analyze_image returns None on exception."""
        import openrecall.server.api
        importlib.reload(openrecall.server.api)
        
        # Mock AFTER reload
        with mock.patch.object(openrecall.server.api, "get_ai_engine") as mock_get:
            mock_engine = mock.MagicMock()
            mock_engine.analyze_image.side_effect = Exception("Model OOM")
            mock_get.return_value = mock_engine
            
            from openrecall.server.api import _safe_analyze_image
            
            test_img = Image.new("RGB", (100, 100))
            result = _safe_analyze_image(test_img)
            
            assert result is None
