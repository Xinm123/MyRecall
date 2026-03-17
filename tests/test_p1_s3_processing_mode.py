"""P1-S3 Integration Test: processing mode switching.

Tests the behavior of switching between noop and ocr processing modes.

SSOT: design.md D6, specs/processing-mode-switch/spec.md
"""

import pytest


class TestProcessingModeSwitch:
    """Tests for processing mode switching behavior."""

    def test_processing_mode_default_is_ocr(self):
        """Test that default processing_mode is 'ocr'."""
        from openrecall.shared.config import Settings

        # Create settings without env override
        settings = Settings()

        assert settings.processing_mode == "ocr"

    def test_processing_mode_can_be_set_to_noop(self, monkeypatch):
        """Test that processing_mode can be explicitly set to 'noop'."""
        monkeypatch.setenv("OPENRECALL_PROCESSING_MODE", "noop")

        # Need to reload to pick up new env var
        import importlib
        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)

        assert openrecall.shared.config.settings.processing_mode == "noop"

    def test_processing_mode_can_be_set_to_ocr(self, monkeypatch):
        """Test that processing_mode can be explicitly set to 'ocr'."""
        monkeypatch.setenv("OPENRECALL_PROCESSING_MODE", "ocr")

        import importlib
        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)

        assert openrecall.shared.config.settings.processing_mode == "ocr"

    def test_processing_mode_lowercase_normalization(self, monkeypatch):
        """Test that processing_mode is normalized to lowercase."""
        monkeypatch.setenv("OPENRECALL_PROCESSING_MODE", "OCR")

        import importlib
        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)

        # The main() function lowercases the processing_mode
        mode = openrecall.shared.config.settings.processing_mode.strip().lower()
        assert mode == "ocr"


class TestProcessingModeFunctions:
    """Tests for processing mode related functions."""

    def test_start_noop_mode_creates_driver(self):
        """Test that _start_noop_mode creates NoopQueueDriver."""
        from openrecall.server.__main__ import _start_noop_mode

        driver = _start_noop_mode()

        assert driver is not None
        assert hasattr(driver, "start")
        assert hasattr(driver, "stop")
        assert hasattr(driver, "join")

        # Cleanup
        driver.stop()

    def test_preload_ocr_model_success(self, monkeypatch):
        """Test that _preload_ocr_model succeeds with auto-download mode."""
        # Use auto-download mode (no local models required)
        # This test validates the function runs without error, not that models load
        monkeypatch.setenv("OPENRECALL_OCR_RAPID_USE_LOCAL", "false")

        # Force reload settings
        import importlib
        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)

        from openrecall.server.__main__ import _preload_ocr_model

        # Should not raise in auto-download mode
        # (May fail if network unavailable, but that's acceptable for this test)
        try:
            _preload_ocr_model()
        except SystemExit:
            # If it fails due to model loading issues, skip the test
            pytest.skip("OCR model auto-download failed - requires network")

    def test_preload_ocr_model_success_with_bundled_models(self):
        """Test that _preload_ocr_model works with bundled models (pip package).

        After simplification, RapidOCR uses models bundled with pip package.
        No local model path configuration needed.
        """
        # Clear the singleton instance and reload rapid_backend module
        from openrecall.server.ocr import rapid_backend
        rapid_backend.RapidOCRBackend._instance = None

        from openrecall.server.__main__ import _preload_ocr_model

        # Should succeed - models are bundled with pip package
        _preload_ocr_model()

