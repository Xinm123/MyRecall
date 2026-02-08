"""Tests for structured SCK error classification."""

from openrecall.client.sck_stream import classify_sck_error


def test_classify_permission_denied():
    code, retryable = classify_sck_error("Screen recording permission denied")
    assert code == "permission_denied"
    assert retryable is True


def test_classify_timeout():
    code, retryable = classify_sck_error("Timed out starting stream")
    assert code == "start_timeout"
    assert retryable is True


def test_classify_no_displays():
    code, retryable = classify_sck_error("No displays found")
    assert code == "no_displays"
    assert retryable is True


def test_classify_unknown_defaults_retryable():
    code, retryable = classify_sck_error("unexpected random failure")
    assert code == "unknown"
    assert retryable is True
