
import os
import shutil
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock
import sys

# Mock rapidocr_onnxruntime for tests if missing
try:
    import rapidocr_onnxruntime
except ImportError:
    sys.modules["rapidocr_onnxruntime"] = MagicMock()

# Import Settings to patch it
from openrecall.shared.config import Settings
from openrecall.server.ai.base import AIProvider

@pytest.fixture
def mock_env_dirs():
    """Create temporary directories for MRS and MRC."""
    base_temp = Path(tempfile.mkdtemp())
    mrs = base_temp / "MRS"
    mrc = base_temp / "MRC"
    mrs.mkdir()
    mrc.mkdir()
    
    yield mrs, mrc
    
    shutil.rmtree(base_temp)

@pytest.fixture
def mock_settings(mock_env_dirs):
    """Return a Settings object configured with temp directories."""
    mrs, mrc = mock_env_dirs
    
    # We create a new Settings instance with overridden values
    # Note: We must ensure these are absolute paths
    settings = Settings(
        OPENRECALL_SERVER_DATA_DIR=str(mrs),
        OPENRECALL_CLIENT_DATA_DIR=str(mrc),
        OPENRECALL_DEBUG=True,
        OPENRECALL_PROCESSING_LIFO_THRESHOLD=5, # Lower threshold for easier testing
        OPENRECALL_AI_PROVIDER="mock",
        OPENRECALL_EMBEDDING_PROVIDER="mock"
    )
    return settings

@pytest.fixture
def mock_ai_provider():
    """Mock AI Provider that returns predictable results."""
    mock = MagicMock()
    
    # Mock analyze_image
    mock.analyze_image.return_value = {
        "caption": "A test screenshot caption",
        "scene": "testing",
        "action": "running_tests"
    }
    
    # Mock extract_text (OCR)
    mock.extract_text.return_value = "import pytest\ndef test_func(): pass"
    
    # Mock embed_text
    # Returns a fixed list of 1024 floats
    mock.embed_text.return_value = [0.1] * 1024
    
    return mock
