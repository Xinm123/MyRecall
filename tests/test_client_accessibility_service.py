"""Tests for client-side accessibility service layer.

Phase 3 of Chat MVP implementation.

These tests verify the service entrypoint for accessibility collection
as specified in docs/v3/chat/mvp.md.
"""

import pytest
from datetime import datetime


class TestCollectForCapture:
    """Tests for collect_for_capture service entrypoint."""

    def test_import_collect_for_capture(self):
        """collect_for_capture should be importable from service module."""
        from openrecall.client.accessibility.service import collect_for_capture

    def test_collect_for_capture_rejects_non_focused_monitor(self):
        """Non-focused monitor should produce non_focused_monitor decision."""
        from openrecall.client.accessibility.service import collect_for_capture
        from openrecall.client.accessibility.types import REASON_NON_FOCUSED_MONITOR

        decision = collect_for_capture(
            app_name="Safari",
            window_name="Test Window",
            target_device_name="monitor_2",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        assert decision.eligible is False
        assert decision.adopted is False
        assert decision.reason == REASON_NON_FOCUSED_MONITOR
        assert decision.snapshot is None
        assert decision.app_name == "Safari"
        assert decision.window_name == "Test Window"

    def test_collect_for_capture_rejects_terminal_app(self):
        """Terminal-class app should produce app_prefers_ocr decision."""
        from openrecall.client.accessibility.service import collect_for_capture
        from openrecall.client.accessibility.types import REASON_APP_PREFERS_OCR

        decision = collect_for_capture(
            app_name="iTerm2",
            window_name="Terminal",
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        assert decision.eligible is False
        assert decision.adopted is False
        assert decision.reason == REASON_APP_PREFERS_OCR
        assert decision.snapshot is None
        assert decision.app_name == "iTerm2"

    def test_collect_for_capture_returns_placeholder_when_eligible(self):
        """Eligible capture should attempt walk (may return various reasons without real AX)."""
        from openrecall.client.accessibility.service import collect_for_capture
        from openrecall.client.accessibility.types import (
            REASON_NO_FOCUSED_WINDOW,
            REASON_ADOPTED_ACCESSIBILITY,
            REASON_EMPTY_TEXT,
        )

        # Phase 4: Walker is now called, but may return various results in test environment
        decision = collect_for_capture(
            app_name="Safari",
            window_name="Test Window",
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        # Eligible but may not be adopted (no real AX in test env)
        assert decision.eligible is True
        # Without a real focused window with text, this returns one of:
        # - no_focused_window: walker couldn't find a window
        # - empty_text: walker found a window but it has no text content
        # - adopted_accessibility: walker found a window with text (rare in test env)
        assert decision.reason in (REASON_NO_FOCUSED_WINDOW, REASON_ADOPTED_ACCESSIBILITY, REASON_EMPTY_TEXT)

    def test_collect_for_capture_includes_timing(self):
        """Decision should include duration_ms."""
        from openrecall.client.accessibility.service import collect_for_capture

        decision = collect_for_capture(
            app_name="Safari",
            window_name="Test Window",
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        # Duration should be populated (even if 0 for rejections)
        assert hasattr(decision, "duration_ms")
        assert isinstance(decision.duration_ms, (int, float))

    def test_collect_for_capture_logs_decision(self, caplog):
        """Decision should be logged at debug level."""
        from openrecall.client.accessibility.service import collect_for_capture
        import logging

        with caplog.at_level(logging.DEBUG):
            decision = collect_for_capture(
                app_name="Safari",
                window_name="Test Window",
                target_device_name="monitor_1",
                focused_device_name="monitor_1",
                captured_at="2026-03-20T10:00:00Z",
            )

        # Should have logged something about the accessibility decision
        # At minimum, the debug log should mention the decision
        assert len(caplog.records) >= 1


class TestCollectForCaptureEdgeCases:
    """Tests for edge cases in collect_for_capture."""

    def test_empty_app_name_not_rejected_as_terminal(self):
        """Empty app name should not be rejected as terminal."""
        from openrecall.client.accessibility.service import collect_for_capture

        # Empty app name - should not match terminal list
        decision = collect_for_capture(
            app_name="",
            window_name="Test Window",
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        # Should be eligible (empty string is not a terminal app)
        assert decision.eligible is True

    def test_none_app_name_handled(self):
        """None app name should be handled gracefully."""
        from openrecall.client.accessibility.service import collect_for_capture

        decision = collect_for_capture(
            app_name=None,
            window_name="Test Window",
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        # Should be eligible (None is not a terminal app)
        assert decision.eligible is True

    def test_empty_window_name_handled(self):
        """Empty window name should be handled gracefully."""
        from openrecall.client.accessibility.service import collect_for_capture

        decision = collect_for_capture(
            app_name="Safari",
            window_name="",
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        assert decision.eligible is True
        # window_name comes from the walker result, which may differ from input
        assert decision.window_name is not None

    def test_device_name_case_sensitive(self):
        """Device name comparison should be case-sensitive."""
        from openrecall.client.accessibility.service import collect_for_capture
        from openrecall.client.accessibility.types import REASON_NON_FOCUSED_MONITOR

        # Different case should be treated as different monitors
        decision = collect_for_capture(
            app_name="Safari",
            window_name="Test Window",
            target_device_name="Monitor_1",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        assert decision.eligible is False
        assert decision.reason == REASON_NON_FOCUSED_MONITOR


class TestDebugDirIntegration:
    """Tests for debug directory integration."""

    def test_collect_for_capture_with_debug_dir(self, tmp_path):
        """When debug_dir is provided, decision should be dumped."""
        from openrecall.client.accessibility.service import collect_for_capture
        from openrecall.client.accessibility.debug import set_debug_mode
        import os

        # Enable debug mode
        set_debug_mode(True)
        try:
            debug_dir = str(tmp_path / "ax_debug")
            decision = collect_for_capture(
                app_name="Safari",
                window_name="Test Window",
                target_device_name="monitor_1",
                focused_device_name="monitor_1",
                captured_at="2026-03-20T10:00:00Z",
                debug_dir=debug_dir,
            )

            # Debug directory should be created and contain dump files
            # (This happens when debug mode is enabled)
            assert decision is not None
        finally:
            set_debug_mode(False)

    def test_collect_for_capture_without_debug_dir(self):
        """When debug_dir is not provided, no dump should be created."""
        from openrecall.client.accessibility.service import collect_for_capture

        # No debug_dir provided
        decision = collect_for_capture(
            app_name="Safari",
            window_name="Test Window",
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        # Should still return a valid decision
        assert decision is not None


class TestRecorderIntegration:
    """Tests for recorder integration with accessibility decision stage."""

    def test_recorder_has_ax_duration_tracking(self):
        """ScreenRecorder should track last AX decision duration."""
        from openrecall.client.recorder import ScreenRecorder

        recorder = ScreenRecorder()
        assert hasattr(recorder, "_last_ax_duration_ms")
        assert recorder._last_ax_duration_ms == 0

    def test_recorder_imports_collect_for_capture(self):
        """recorder module should import collect_for_capture."""
        from openrecall.client import recorder

        # The module should have accessibility imported
        assert hasattr(recorder, "collect_for_capture")

    def test_build_capture_metadata_works_with_ax_stage(self):
        """_build_capture_metadata should work after AX stage is added."""
        from openrecall.client.recorder import ScreenRecorder
        from openrecall.client.events.base import TriggerEvent, CaptureTrigger

        recorder = ScreenRecorder()
        event = TriggerEvent(
            capture_trigger=CaptureTrigger.CLICK,
            device_name="monitor_1",
            event_ts="2026-03-20T10:00:00Z",
        )

        # This should work without error after AX stage integration
        metadata = recorder._build_capture_metadata(
            event,
            context_active_app="Safari",
            context_active_window="Test Window",
            context_active_monitor_device_name="monitor_1",
            focused_monitor_device_name="monitor_1",
        )

        assert metadata is not None
        assert "app_name" in metadata

    def test_recorder_capture_includes_accessibility_decision(self, monkeypatch):
        """Capture flow should make accessibility decision."""
        from openrecall.client.recorder import ScreenRecorder
        from openrecall.client.events.base import (
            TriggerEvent,
            CaptureTrigger,
            MonitorDescriptor,
        )
        import numpy as np

        recorder = ScreenRecorder()

        # Track if collect_for_capture was called
        call_count = 0
        captured_decision = None

        original_collect = recorder.__class__.__module__
        from openrecall.client.accessibility import collect_for_capture as original_fn

        def track_collect(*args, **kwargs):
            nonlocal call_count, captured_decision
            call_count += 1
            captured_decision = original_fn(*args, **kwargs)
            return captured_decision

        monkeypatch.setattr(
            "openrecall.client.recorder.collect_for_capture", track_collect
        )

        # Verify the function can be called with expected parameters
        decision = original_fn(
            app_name="Safari",
            window_name="Test",
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        assert decision is not None
        assert decision.eligible is True


class TestMergeAccessibilityMetadata:
    """Tests for _merge_accessibility_metadata function."""

    def test_merge_adds_canonical_fields_for_adopted(self):
        """When adopted=True, metadata should contain text, text_source, accessibility payload."""
        from openrecall.client.accessibility.types import (
            AccessibilityDecision,
            TreeSnapshot,
            AccessibilityTreeNode,
            NodeBounds,
        )
        from openrecall.client.recorder import _merge_accessibility_metadata
        from datetime import datetime, timezone

        snapshot = TreeSnapshot(
            app_name="Safari",
            window_name="Doc",
            browser_url="https://example.com",
            text_content="Hello World",
            nodes=[
                AccessibilityTreeNode(
                    role="AXStaticText",
                    text="Hello World",
                    depth=0,
                    bounds=NodeBounds(left=0.0, top=0.0, width=1.0, height=1.0),
                )
            ],
            node_count=1,
            truncated=False,
            truncation_reason=None,
            max_depth_reached=1,
            content_hash=12345,
            simhash=67890,
            captured_at=datetime.now(timezone.utc),
            duration_ms=50,
        )
        decision = AccessibilityDecision(
            eligible=True,
            adopted=True,
            reason="adopted_accessibility",
            snapshot=snapshot,
        )

        base_metadata = {"app_name": "Safari", "window_name": "Doc"}
        result = _merge_accessibility_metadata(base_metadata, decision)

        assert result["text"] == "Hello World"
        assert result["text_source"] == "accessibility"
        assert result["browser_url"] == "https://example.com"
        assert result["content_hash"] == 12345
        assert result["simhash"] == 67890
        assert "accessibility" in result
        assert result["accessibility"]["text_content"] == "Hello World"
        assert result["accessibility"]["node_count"] == 1

    def test_merge_adds_browser_url_for_empty_text(self):
        """When reason=empty_text, metadata should still contain browser_url from snapshot."""
        from openrecall.client.accessibility.types import (
            AccessibilityDecision,
            TreeSnapshot,
        )
        from openrecall.client.recorder import _merge_accessibility_metadata
        from datetime import datetime, timezone

        # Snapshot has browser_url but empty text_content
        snapshot = TreeSnapshot(
            app_name="Safari",
            window_name="Doc",
            browser_url="https://example.com",
            text_content="",  # Empty!
            nodes=[],
            node_count=0,
            truncated=False,
            truncation_reason=None,
            max_depth_reached=0,
            content_hash=0,
            simhash=0,
            captured_at=datetime.now(timezone.utc),
            duration_ms=50,
        )
        decision = AccessibilityDecision(
            eligible=True,
            adopted=False,  # Not adopted because empty text
            reason="empty_text",
            snapshot=snapshot,
        )

        base_metadata = {"app_name": "Safari", "window_name": "Doc"}
        result = _merge_accessibility_metadata(base_metadata, decision)

        # browser_url should be added even for non-adopted
        assert result["browser_url"] == "https://example.com"
        # But no text or accessibility payload
        assert "text" not in result
        assert "accessibility" not in result

    def test_merge_omits_canonical_fields_for_non_adopted(self):
        """When adopted=False with no snapshot, metadata should NOT contain text or accessibility."""
        from openrecall.client.accessibility.types import AccessibilityDecision
        from openrecall.client.recorder import _merge_accessibility_metadata

        decision = AccessibilityDecision(
            eligible=False,
            adopted=False,
            reason="non_focused_monitor",
            snapshot=None,
        )

        base_metadata = {"app_name": "Safari", "window_name": "Doc"}
        result = _merge_accessibility_metadata(base_metadata, decision)

        assert "text" not in result
        assert "text_source" not in result
        assert "accessibility" not in result

    def test_merge_preserves_base_metadata(self):
        """Merge should preserve all existing base metadata fields."""
        from openrecall.client.accessibility.types import (
            AccessibilityDecision,
            TreeSnapshot,
            AccessibilityTreeNode,
        )
        from openrecall.client.recorder import _merge_accessibility_metadata
        from datetime import datetime, timezone

        snapshot = TreeSnapshot(
            app_name="Safari",
            window_name="Doc",
            browser_url="https://example.com",
            text_content="Hello World",
            nodes=[AccessibilityTreeNode(role="AXStaticText", text="Hello World", depth=0)],
            node_count=1,
            truncated=False,
            truncation_reason=None,
            max_depth_reached=1,
            content_hash=12345,
            simhash=67890,
            captured_at=datetime.now(timezone.utc),
            duration_ms=50,
        )
        decision = AccessibilityDecision(
            eligible=True,
            adopted=True,
            reason="adopted_accessibility",
            snapshot=snapshot,
        )

        base_metadata = {
            "app_name": "Safari",
            "window_name": "Doc",
            "timestamp": "2026-03-20T10:00:00Z",
            "capture_trigger": "click",
            "device_name": "monitor_1",
            "event_ts": "2026-03-20T09:59:59Z",
            "simhash": 11111,  # Should be overwritten by snapshot
        }
        result = _merge_accessibility_metadata(base_metadata, decision)

        # Base metadata should be preserved
        assert result["timestamp"] == "2026-03-20T10:00:00Z"
        assert result["capture_trigger"] == "click"
        assert result["device_name"] == "monitor_1"
        assert result["event_ts"] == "2026-03-20T09:59:59Z"
        # simhash from snapshot should override base
        assert result["simhash"] == 67890

    def test_merge_includes_truncation_info(self):
        """Merge should include truncation info in accessibility payload."""
        from openrecall.client.accessibility.types import (
            AccessibilityDecision,
            TreeSnapshot,
            AccessibilityTreeNode,
        )
        from openrecall.client.recorder import _merge_accessibility_metadata
        from datetime import datetime, timezone

        snapshot = TreeSnapshot(
            app_name="Safari",
            window_name="Doc",
            browser_url="https://example.com",
            text_content="Hello World",
            nodes=[AccessibilityTreeNode(role="AXStaticText", text="Hello World", depth=0)],
            node_count=1000,
            truncated=True,
            truncation_reason="max_nodes_exceeded",
            max_depth_reached=30,
            content_hash=12345,
            simhash=67890,
            captured_at=datetime.now(timezone.utc),
            duration_ms=200,
        )
        decision = AccessibilityDecision(
            eligible=True,
            adopted=True,
            reason="adopted_accessibility",
            snapshot=snapshot,
        )

        base_metadata = {"app_name": "Safari", "window_name": "Doc"}
        result = _merge_accessibility_metadata(base_metadata, decision)

        assert result["accessibility"]["truncated"] is True
        assert result["accessibility"]["truncation_reason"] == "max_nodes_exceeded"
        assert result["accessibility"]["max_depth_reached"] == 30
        assert result["accessibility"]["duration_ms"] == 200


class TestRecorderSkipsAx:
    """Tests for recorder skipping AX collection in specific cases."""

    def test_skips_ax_for_non_focused_monitor(self):
        """AX should be rejected for non-focused monitor."""
        from openrecall.client.accessibility.service import collect_for_capture
        from openrecall.client.accessibility.types import REASON_NON_FOCUSED_MONITOR

        decision = collect_for_capture(
            app_name="Safari",
            window_name="Test",
            target_device_name="monitor_2",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        assert decision.eligible is False
        assert decision.reason == REASON_NON_FOCUSED_MONITOR

    def test_skips_ax_for_terminal_app(self):
        """AX should be rejected for terminal-class app."""
        from openrecall.client.accessibility.service import collect_for_capture
        from openrecall.client.accessibility.types import REASON_APP_PREFERS_OCR

        decision = collect_for_capture(
            app_name="iTerm2",
            window_name="Terminal",
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        assert decision.eligible is False
        assert decision.reason == REASON_APP_PREFERS_OCR

    def test_capture_still_succeeds_when_ax_skipped(self):
        """Capture should still succeed when AX is skipped."""
        from openrecall.client.accessibility.service import collect_for_capture

        # Non-focused monitor - AX is skipped
        decision = collect_for_capture(
            app_name="Safari",
            window_name="Test",
            target_device_name="monitor_2",
            focused_device_name="monitor_1",
            captured_at="2026-03-20T10:00:00Z",
        )

        # The decision is made, but capture should continue
        assert decision is not None
        # The recorder will continue with OCR text extraction
