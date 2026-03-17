"""P1-S3 Unit Test: capture_trigger validation (fail-loud).

Tests that invalid capture_trigger values result in immediate failure
without attempting OCR.

Valid triggers (P1): {'idle', 'app_switch', 'manual', 'click'} (lowercase)
Invalid: NULL, uppercase, mixed-case, unknown values

SSOT: design.md D4
"""

import pytest

from openrecall.server.processing.v3_worker import (
    VALID_CAPTURE_TRIGGERS,
    V3ProcessingWorker,
)


class TestTriggerValidation:
    """Tests for capture_trigger validation."""

    def test_valid_triggers_lower_case(self):
        """Test that all valid lowercase triggers pass validation."""
        worker = V3ProcessingWorker()

        for trigger in VALID_CAPTURE_TRIGGERS:
            is_valid, error = worker._validate_trigger(trigger)
            assert is_valid is True, f"Trigger '{trigger}' should be valid"
            assert error == ""

    def test_valid_triggers_set(self):
        """Test that the valid triggers set matches P1 spec."""
        expected = {"idle", "app_switch", "manual", "click"}
        assert VALID_CAPTURE_TRIGGERS == expected

    def test_null_trigger_is_invalid(self):
        """Test that NULL (None) trigger is invalid."""
        worker = V3ProcessingWorker()

        is_valid, error = worker._validate_trigger(None)
        assert is_valid is False
        assert "INVALID_TRIGGER" in error
        assert "null" in error

    def test_uppercase_trigger_is_invalid(self):
        """Test that uppercase triggers are invalid (case-sensitive)."""
        worker = V3ProcessingWorker()

        for trigger in ["IDLE", "APP_SWITCH", "MANUAL", "CLICK"]:
            is_valid, error = worker._validate_trigger(trigger)
            assert is_valid is False, f"Trigger '{trigger}' should be invalid"
            assert "INVALID_TRIGGER" in error

    def test_mixed_case_trigger_is_invalid(self):
        """Test that mixed-case triggers are invalid."""
        worker = V3ProcessingWorker()

        invalid_triggers = [
            "Idle",
            "App_Switch",
            "Manual",
            "Click",
            "iDLE",
            "aPP_sWITCH",
        ]

        for trigger in invalid_triggers:
            is_valid, error = worker._validate_trigger(trigger)
            assert is_valid is False, f"Trigger '{trigger}' should be invalid"
            assert "INVALID_TRIGGER" in error

    def test_unknown_trigger_is_invalid(self):
        """Test that unknown trigger values are invalid."""
        worker = V3ProcessingWorker()

        unknown_triggers = [
            "timeout",
            "scheduled",
            "unknown",
            "random",
            "",  # Empty string
            " ",  # Whitespace
        ]

        for trigger in unknown_triggers:
            is_valid, error = worker._validate_trigger(trigger)
            assert is_valid is False, f"Trigger '{trigger}' should be invalid"
            assert "INVALID_TRIGGER" in error

    def test_trigger_validation_returns_reason(self):
        """Test that validation returns the reason for failure."""
        worker = V3ProcessingWorker()

        is_valid, error = worker._validate_trigger("UNKNOWN")
        assert is_valid is False
        assert error == "INVALID_TRIGGER: 'UNKNOWN'"

    def test_trigger_validation_null_reason(self):
        """Test that null trigger returns specific error reason."""
        worker = V3ProcessingWorker()

        is_valid, error = worker._validate_trigger(None)
        assert is_valid is False
        assert error == "INVALID_TRIGGER: null"
