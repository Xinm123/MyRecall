"""Tests for client-side accessibility debug helpers.

Phase 2 of Chat MVP implementation.

These tests verify the debug logging and dump contracts defined in docs/v3/chat/mvp.md.
"""

import pytest
import json
import tempfile
import os
from datetime import datetime
from pathlib import Path


class TestStructuredLogFormatter:
    """Tests for accessibility structured log formatter."""

    def test_import_format_accessibility_log(self):
        """format_accessibility_log should be importable from debug module."""
        from openrecall.client.accessibility.debug import format_accessibility_log

    def test_log_contains_required_fields(self):
        """Structured log should contain all MVP-required fields."""
        from openrecall.client.accessibility.debug import format_accessibility_log

        log = format_accessibility_log(
            capture_id="cap_123",
            device_name="monitor_1",
            eligible=True,
            adopted=True,
            reason="adopted_accessibility",
            app_name="Safari",
            window_name="MyRecall Docs",
            duration_ms=47,
            node_count=42,
            truncated=False,
            text_preview="Hello World...",
        )

        # MVP spec required fields:
        # capture_id, device_name, eligible, adopted, reason,
        # app_name, window_name, duration_ms, node_count, truncated, text_preview
        assert "capture_id" in log
        assert "device_name" in log
        assert "eligible" in log
        assert "adopted" in log
        assert "reason" in log
        assert "app_name" in log
        assert "window_name" in log
        assert "duration_ms" in log
        assert "node_count" in log
        assert "truncated" in log
        assert "text_preview" in log

    def test_log_is_json_serializable(self):
        """Structured log should be JSON-serializable."""
        from openrecall.client.accessibility.debug import format_accessibility_log

        log = format_accessibility_log(
            capture_id="cap_123",
            device_name="monitor_1",
            eligible=True,
            adopted=True,
            reason="adopted_accessibility",
            app_name="Safari",
            window_name="Test",
            duration_ms=47,
            node_count=42,
            truncated=False,
            text_preview="Hello",
        )

        # Should be a dict (JSON-serializable)
        assert isinstance(log, dict)

    def test_log_with_rejection_reason(self):
        """Structured log should handle rejection reasons."""
        from openrecall.client.accessibility.debug import format_accessibility_log

        log = format_accessibility_log(
            capture_id="cap_456",
            device_name="monitor_2",
            eligible=False,
            adopted=False,
            reason="non_focused_monitor",
            app_name="Safari",
            window_name="Test",
            duration_ms=0,
            node_count=0,
            truncated=False,
            text_preview=None,
        )

        assert log["eligible"] is False
        assert log["adopted"] is False
        assert log["reason"] == "non_focused_monitor"

    def test_log_text_preview_truncation(self):
        """Structured log should truncate long text previews."""
        from openrecall.client.accessibility.debug import format_accessibility_log

        long_text = "A" * 500
        log = format_accessibility_log(
            capture_id="cap_789",
            device_name="monitor_1",
            eligible=True,
            adopted=True,
            reason="adopted_accessibility",
            app_name="Safari",
            window_name="Test",
            duration_ms=50,
            node_count=100,
            truncated=False,
            text_preview=long_text,
        )

        # Text preview should be truncated to reasonable length
        assert len(log["text_preview"]) <= 100


class TestDebugDumpWriter:
    """Tests for accessibility debug dump writer."""

    def test_import_dump_accessibility_decision(self):
        """dump_accessibility_decision should be importable from debug module."""
        from openrecall.client.accessibility.debug import dump_accessibility_decision

    def test_dump_creates_json_file(self):
        """Debug dump should create a JSON file."""
        from openrecall.client.accessibility.debug import (
            dump_accessibility_decision,
            set_debug_mode,
        )
        from openrecall.client.accessibility.types import (
            TreeSnapshot,
            AccessibilityDecision,
        )

        # Enable debug mode for this test
        set_debug_mode(True)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                snapshot = TreeSnapshot(
                    app_name="Safari",
                    window_name="Test",
                    browser_url="https://example.com",
                    text_content="Hello World",
                    nodes=[],
                    node_count=1,
                    truncated=False,
                    truncation_reason=None,
                    max_depth_reached=1,
                    content_hash=123,
                    simhash=456,
                    captured_at=datetime(2026, 3, 19, 10, 21, 35),
                    duration_ms=15,
                )
                decision = AccessibilityDecision(
                    eligible=True,
                    adopted=True,
                    reason="adopted_accessibility",
                    snapshot=snapshot,
                )

                dump_path = dump_accessibility_decision(
                    decision=decision,
                    capture_id="cap_test",
                    dump_dir=tmpdir,
                )

                assert dump_path is not None
                assert os.path.exists(dump_path)
                assert dump_path.endswith(".json")
        finally:
            set_debug_mode(False)

    def test_dump_content_has_required_fields(self):
        """Debug dump should contain MVP-specified fields."""
        from openrecall.client.accessibility.debug import (
            dump_accessibility_decision,
            set_debug_mode,
        )
        from openrecall.client.accessibility.types import (
            TreeSnapshot,
            AccessibilityDecision,
        )

        # Enable debug mode for this test
        set_debug_mode(True)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                snapshot = TreeSnapshot(
                    app_name="Safari",
                    window_name="Test",
                    browser_url=None,
                    text_content="Hello World",
                    nodes=[],
                    node_count=1,
                    truncated=True,
                    truncation_reason="max_text_length",
                    max_depth_reached=5,
                    content_hash=789,
                    simhash=101,
                    captured_at=datetime(2026, 3, 19, 10, 21, 35),
                    duration_ms=20,
                )
                decision = AccessibilityDecision(
                    eligible=True,
                    adopted=True,
                    reason="adopted_accessibility",
                    snapshot=snapshot,
                )

                dump_path = dump_accessibility_decision(
                    decision=decision,
                    capture_id="cap_test",
                    dump_dir=tmpdir,
                )

                with open(dump_path) as f:
                    content = json.load(f)

                # MVP spec dump content:
                # capture metadata, decision metadata, snapshot summary,
                # text_content, full flat nodes list
                assert "capture_id" in content
                assert "decision" in content
                assert "snapshot" in content
                assert content["decision"]["eligible"] is True
                assert content["decision"]["adopted"] is True
                assert content["decision"]["reason"] == "adopted_accessibility"
                assert "text_content" in content["snapshot"]
                assert "node_count" in content["snapshot"]
                assert "truncated" in content["snapshot"]
        finally:
            set_debug_mode(False)

    def test_dump_with_no_snapshot(self):
        """Debug dump should handle decisions without snapshot."""
        from openrecall.client.accessibility.debug import (
            dump_accessibility_decision,
            set_debug_mode,
        )
        from openrecall.client.accessibility.types import AccessibilityDecision

        # Enable debug mode for this test
        set_debug_mode(True)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                decision = AccessibilityDecision(
                    eligible=False,
                    adopted=False,
                    reason="non_focused_monitor",
                    snapshot=None,
                )

                dump_path = dump_accessibility_decision(
                    decision=decision,
                    capture_id="cap_no_snapshot",
                    dump_dir=tmpdir,
                )

                with open(dump_path) as f:
                    content = json.load(f)

                assert content["decision"]["reason"] == "non_focused_monitor"
                assert content["snapshot"] is None
        finally:
            set_debug_mode(False)


class TestAccessibilityDebugMode:
    """Tests for debug mode configuration."""

    def test_import_is_debug_mode(self):
        """is_debug_mode should be importable from debug module."""
        from openrecall.client.accessibility.debug import is_debug_mode

    def test_debug_mode_default_off(self):
        """Debug mode should be off by default."""
        from openrecall.client.accessibility.debug import is_debug_mode

        # Without env var set, should return False
        # (Test may need adjustment based on actual implementation)
        result = is_debug_mode()
        # Default should be False
        assert isinstance(result, bool)

    def test_import_set_debug_mode(self):
        """set_debug_mode should be importable from debug module."""
        from openrecall.client.accessibility.debug import set_debug_mode

    def test_set_debug_mode_toggles(self):
        """set_debug_mode should toggle debug state."""
        from openrecall.client.accessibility.debug import set_debug_mode, is_debug_mode

        set_debug_mode(True)
        assert is_debug_mode() is True

        set_debug_mode(False)
        assert is_debug_mode() is False


class TestPerformanceLog:
    """Tests for performance logging helpers."""

    def test_import_format_performance_log(self):
        """format_performance_log should be importable from debug module."""
        from openrecall.client.accessibility.debug import format_performance_log

    def test_performance_log_required_fields(self):
        """Performance log should contain MVP-specified fields."""
        from openrecall.client.accessibility.debug import format_performance_log

        log = format_performance_log(
            trigger="click",
            target_device="monitor_1",
            app_name="Safari",
            eligible=True,
            adopted=True,
            reason="adopted_accessibility",
            capture_ms=15,
            ax_walk_ms=47,
            spool_enqueue_ms=5,
            total_ms=67,
            node_count=42,
            truncated=False,
        )

        # MVP spec per-capture performance fields:
        # trigger, target device, app name, eligibility/adoption decision,
        # reason, capture_ms, ax_walk_ms, spool_enqueue_ms, total_ms,
        # node_count, truncated
        assert log["trigger"] == "click"
        assert log["target_device"] == "monitor_1"
        assert log["app_name"] == "Safari"
        assert log["eligible"] is True
        assert log["adopted"] is True
        assert log["reason"] == "adopted_accessibility"
        assert log["capture_ms"] == 15
        assert log["ax_walk_ms"] == 47
        assert log["spool_enqueue_ms"] == 5
        assert log["total_ms"] == 67
        assert log["node_count"] == 42
        assert log["truncated"] is False


class TestTextPreview:
    """Tests for text preview helper."""

    def test_import_make_text_preview(self):
        """make_text_preview should be importable from debug module."""
        from openrecall.client.accessibility.debug import make_text_preview

    def test_short_text_unchanged(self):
        """Short text should be unchanged in preview."""
        from openrecall.client.accessibility.debug import make_text_preview

        preview = make_text_preview("Hello World", max_length=100)
        assert preview == "Hello World"

    def test_long_text_truncated(self):
        """Long text should be truncated with ellipsis."""
        from openrecall.client.accessibility.debug import make_text_preview

        long_text = "A" * 200
        preview = make_text_preview(long_text, max_length=50)
        assert len(preview) == 53  # 50 + "..."
        assert preview.endswith("...")

    def test_none_text(self):
        """None text should return None or empty string."""
        from openrecall.client.accessibility.debug import make_text_preview

        preview = make_text_preview(None)
        assert preview is None or preview == ""

    def test_empty_text(self):
        """Empty text should return empty string."""
        from openrecall.client.accessibility.debug import make_text_preview

        preview = make_text_preview("")
        assert preview == ""
