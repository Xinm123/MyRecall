import os
import sys
import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from PIL import Image

from openrecall.server.ocr.rapid_backend import RapidOCRBackend
from openrecall.server.ai.factory import get_ocr_provider
from openrecall.server.ai.providers import RapidOCRProvider

@pytest.fixture
def mock_settings():
    with patch("openrecall.server.ocr.rapid_backend.settings") as mock_settings:
        # Default settings
        mock_settings.ocr_rapid_use_local = False
        mock_settings.ocr_rapid_model_dir = None
        yield mock_settings

@pytest.fixture
def reset_singleton():
    # Reset singleton before and after each test
    RapidOCRBackend._instance = None
    yield
    RapidOCRBackend._instance = None

@pytest.fixture
def mock_rapid_ocr():
    with patch("openrecall.server.ocr.rapid_backend.RapidOCR") as mock_ocr:
        yield mock_ocr

class TestRapidOCRBackend:
    
    def test_initialization_default(self, mock_settings, reset_singleton, mock_rapid_ocr):
        """Test initialization with default settings (auto-download)."""
        mock_settings.ocr_rapid_use_local = False
        
        backend = RapidOCRBackend()
        
        assert backend is not None
        mock_rapid_ocr.assert_called_once_with(use_angle_cls=True, use_gpu=True)

    def test_initialization_local_missing_dir(self, mock_settings, reset_singleton, mock_rapid_ocr):
        """Test initialization with local mode but missing directory config."""
        mock_settings.ocr_rapid_use_local = True
        mock_settings.ocr_rapid_model_dir = None
        
        with pytest.raises(ValueError, match="OPENRECALL_OCR_RAPID_MODEL_DIR is required"):
            RapidOCRBackend()

    def test_initialization_local_missing_files(self, mock_settings, reset_singleton, mock_rapid_ocr):
        """Test initialization with local mode but missing model files."""
        mock_settings.ocr_rapid_use_local = True
        mock_settings.ocr_rapid_model_dir = "/tmp/fake_dir"
        
        with patch("os.path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="Missing required ONNX models"):
                RapidOCRBackend()

    def test_initialization_local_success(self, mock_settings, reset_singleton, mock_rapid_ocr):
        """Test initialization with local mode and valid files."""
        mock_settings.ocr_rapid_use_local = True
        mock_settings.ocr_rapid_model_dir = "/tmp/valid_dir"
        
        with patch("os.path.exists", return_value=True):
            backend = RapidOCRBackend()
            
            assert backend is not None
            mock_rapid_ocr.assert_called_once()
            call_kwargs = mock_rapid_ocr.call_args.kwargs
            assert call_kwargs["det_model_path"] == "/tmp/valid_dir/ch_PP-OCRv4_det_infer.onnx"
            assert call_kwargs["rec_model_path"] == "/tmp/valid_dir/ch_PP-OCRv5_rec_infer.onnx"
            assert call_kwargs["cls_model_path"] == "/tmp/valid_dir/ch_ppocr_mobile_v2.0_cls_infer.onnx"

    def test_extract_text_success(self, mock_settings, reset_singleton, mock_rapid_ocr):
        """Test text extraction with valid result."""
        # Setup mock engine instance
        mock_engine_instance = MagicMock()
        mock_rapid_ocr.return_value = mock_engine_instance
        
        # Mock result: list of [box, text, score]
        mock_result = [
            [[[0,0], [10,0], [10,10], [0,10]], "Hello", 0.99],
            [[[0,20], [10,20], [10,30], [0,30]], "World", 0.98]
        ]
        mock_engine_instance.return_value = (mock_result, 0.1)
        
        backend = RapidOCRBackend()
        
        # Test with PIL Image
        img = Image.new('RGB', (100, 100), color='white')
        text = backend.extract_text(img)
        
        # Expect newline joined
        assert text == "Hello\nWorld"
        mock_engine_instance.assert_called_once()
        
        # Verify conversion logic (RGB -> BGR) implicitly by checking call args type/shape if needed
        # but here we trust the integration mainly.

    def test_extract_text_empty(self, mock_settings, reset_singleton, mock_rapid_ocr):
        """Test text extraction with no result."""
        mock_engine_instance = MagicMock()
        mock_rapid_ocr.return_value = mock_engine_instance
        mock_engine_instance.return_value = (None, 0.0)
        
        backend = RapidOCRBackend()
        text = backend.extract_text(np.zeros((100, 100, 3), dtype=np.uint8))
        
        assert text == ""

    def test_extract_text_error(self, mock_settings, reset_singleton, mock_rapid_ocr):
        """Test text extraction with exception."""
        mock_engine_instance = MagicMock()
        mock_rapid_ocr.return_value = mock_engine_instance
        mock_engine_instance.side_effect = Exception("Processing failed")
        
        backend = RapidOCRBackend()
        text = backend.extract_text(np.zeros((100, 100, 3), dtype=np.uint8))
        
        assert text == ""


class TestRapidOCRFactoryIntegration:
    
    @patch("openrecall.server.ai.factory.settings")
    @patch("openrecall.server.ai.factory.RapidOCRProvider")
    def test_get_ocr_provider_rapidocr(self, mock_provider_cls, mock_settings):
        """Verify factory returns RapidOCRProvider when configured."""
        mock_settings.ocr_provider = "rapidocr"
        mock_settings.ai_provider = "local" # Fallback shouldn't matter if override is set
        
        # Clear cache in factory if needed, or patch the dict
        with patch.dict("openrecall.server.ai.factory._instances", {}, clear=True):
            provider = get_ocr_provider()
            
            mock_provider_cls.assert_called_once()
            assert provider == mock_provider_cls.return_value

    @patch("openrecall.server.ai.providers.RapidOCRBackend")
    def test_provider_wrapper(self, mock_backend_cls):
        """Test the RapidOCRProvider wrapper."""
        mock_backend_instance = MagicMock()
        mock_backend_cls.return_value = mock_backend_instance
        mock_backend_instance.extract_text.return_value = "Extracted Text"
        
        provider = RapidOCRProvider()
        
        with patch("pathlib.Path.is_file", return_value=True):
            text = provider.extract_text("/tmp/test.png")
            
            assert text == "Extracted Text"
            mock_backend_instance.extract_text.assert_called_with("/tmp/test.png")
