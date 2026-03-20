"""Tests for client-side accessibility policy helpers.

Phase 2 of Chat MVP implementation.

These tests verify the policy rules defined in docs/v3/chat/mvp.md.
"""

import pytest
from datetime import datetime


class TestAppPrefersOcr:
    """Tests for terminal-class OCR preference detection."""

    def test_import_app_prefers_ocr(self):
        """app_prefers_ocr should be importable from policy module."""
        from openrecall.client.accessibility.policy import app_prefers_ocr

    def test_terminal_apps_prefer_ocr(self):
        """Terminal-class apps should prefer OCR over accessibility."""
        from openrecall.client.accessibility.policy import app_prefers_ocr

        # MVP spec terminal apps:
        # wezterm, iterm, terminal, alacritty, kitty, hyper, warp, ghostty
        terminal_apps = [
            "WezTerm",
            "iTerm2",
            "Terminal",
            "Alacritty",
            "kitty",
            "Hyper",
            "Warp",
            "Ghostty",
        ]
        for app_name in terminal_apps:
            assert app_prefers_ocr(app_name), f"{app_name} should prefer OCR"

    def test_terminal_apps_case_insensitive(self):
        """Terminal app detection should be case-insensitive."""
        from openrecall.client.accessibility.policy import app_prefers_ocr

        assert app_prefers_ocr("wezterm")
        assert app_prefers_ocr("WEZTERM")
        assert app_prefers_ocr("WeZtErM")
        assert app_prefers_ocr("ITERM2")
        assert app_prefers_ocr("ghostty")

    def test_non_terminal_apps_dont_prefer_ocr(self):
        """Non-terminal apps should not prefer OCR."""
        from openrecall.client.accessibility.policy import app_prefers_ocr

        non_terminal_apps = [
            "Safari",
            "Chrome",
            "Firefox",
            "VS Code",
            "Cursor",
            "Finder",
            "Mail",
            "Notes",
        ]
        for app_name in non_terminal_apps:
            assert not app_prefers_ocr(app_name), f"{app_name} should not prefer OCR"

    def test_empty_app_name(self):
        """Empty or None app name should not prefer OCR."""
        from openrecall.client.accessibility.policy import app_prefers_ocr

        assert not app_prefers_ocr("")
        assert not app_prefers_ocr(None)


class TestFocusedMonitorEligibility:
    """Tests for focused-monitor AX eligibility rules."""

    def test_import_is_focused_monitor_eligible(self):
        """is_focused_monitor_eligible should be importable from policy module."""
        from openrecall.client.accessibility.policy import is_focused_monitor_eligible

    def test_focused_monitor_eligible(self):
        """Frames on focused monitor should be AX-eligible."""
        from openrecall.client.accessibility.policy import is_focused_monitor_eligible

        result = is_focused_monitor_eligible(
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
        )
        assert result is True

    def test_non_focused_monitor_not_eligible(self):
        """Frames on non-focused monitor should not be AX-eligible."""
        from openrecall.client.accessibility.policy import is_focused_monitor_eligible

        result = is_focused_monitor_eligible(
            target_device_name="monitor_2",
            focused_device_name="monitor_1",
        )
        assert result is False

    def test_cross_monitor_window_eligibility(self):
        """Windows spanning monitors follow focused-monitor routing."""
        from openrecall.client.accessibility.policy import is_focused_monitor_eligible

        # Even if a window spans monitors, eligibility follows focused monitor
        result = is_focused_monitor_eligible(
            target_device_name="monitor_2",
            focused_device_name="monitor_1",
        )
        assert result is False


class TestAccessibilityAdoption:
    """Tests for accessibility adoption rules."""

    def test_import_should_adopt_accessibility(self):
        """should_adopt_accessibility should be importable from policy module."""
        from openrecall.client.accessibility.policy import should_adopt_accessibility

    def test_adopt_with_non_empty_text(self):
        """Accessibility with non-empty text_content should be adopted."""
        from openrecall.client.accessibility.policy import should_adopt_accessibility

        result = should_adopt_accessibility(text_content="Hello World")
        assert result is True

    def test_reject_empty_text(self):
        """Accessibility with empty text_content should not be adopted."""
        from openrecall.client.accessibility.policy import should_adopt_accessibility

        result = should_adopt_accessibility(text_content="")
        assert result is False

    def test_reject_whitespace_only_text(self):
        """Accessibility with whitespace-only text_content should not be adopted."""
        from openrecall.client.accessibility.policy import should_adopt_accessibility

        result = should_adopt_accessibility(text_content="   \n\t  ")
        assert result is False

    def test_reject_none_text(self):
        """Accessibility with None text_content should not be adopted."""
        from openrecall.client.accessibility.policy import should_adopt_accessibility

        result = should_adopt_accessibility(text_content=None)
        assert result is False


class TestAccessibilityDecisionMapping:
    """Tests for accessibility decision mapping."""

    def test_import_make_accessibility_decision(self):
        """make_accessibility_decision should be importable from policy module."""
        from openrecall.client.accessibility.policy import make_accessibility_decision

    def test_decision_non_focused_monitor(self):
        """Non-focused monitor should produce non_focused_monitor decision."""
        from openrecall.client.accessibility.policy import make_accessibility_decision
        from openrecall.client.accessibility.types import REASON_NON_FOCUSED_MONITOR

        decision = make_accessibility_decision(
            target_device_name="monitor_2",
            focused_device_name="monitor_1",
            app_name="Safari",
            snapshot=None,
        )

        assert decision.eligible is False
        assert decision.adopted is False
        assert decision.reason == REASON_NON_FOCUSED_MONITOR
        assert decision.snapshot is None

    def test_decision_app_prefers_ocr(self):
        """Terminal app should produce app_prefers_ocr decision."""
        from openrecall.client.accessibility.policy import make_accessibility_decision
        from openrecall.client.accessibility.types import REASON_APP_PREFERS_OCR

        decision = make_accessibility_decision(
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            app_name="iTerm2",
            snapshot=None,
        )

        assert decision.eligible is False
        assert decision.adopted is False
        assert decision.reason == REASON_APP_PREFERS_OCR
        assert decision.snapshot is None

    def test_decision_no_focused_window(self):
        """No snapshot should produce no_focused_window decision."""
        from openrecall.client.accessibility.policy import make_accessibility_decision
        from openrecall.client.accessibility.types import REASON_NO_FOCUSED_WINDOW

        decision = make_accessibility_decision(
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            app_name="Safari",
            snapshot=None,
        )

        assert decision.eligible is True
        assert decision.adopted is False
        assert decision.reason == REASON_NO_FOCUSED_WINDOW
        assert decision.snapshot is None

    def test_decision_empty_text(self):
        """Empty text snapshot should produce empty_text decision."""
        from openrecall.client.accessibility.policy import make_accessibility_decision
        from openrecall.client.accessibility.types import (
            TreeSnapshot,
            REASON_EMPTY_TEXT,
        )

        snapshot = TreeSnapshot(
            app_name="Safari",
            window_name="Test",
            browser_url=None,
            text_content="",
            nodes=[],
            node_count=0,
            truncated=False,
            truncation_reason=None,
            max_depth_reached=0,
            content_hash=0,
            simhash=0,
            captured_at=datetime(2026, 3, 19, 10, 21, 35),
            duration_ms=10,
        )

        decision = make_accessibility_decision(
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            app_name="Safari",
            snapshot=snapshot,
        )

        assert decision.eligible is True
        assert decision.adopted is False
        assert decision.reason == REASON_EMPTY_TEXT
        assert decision.snapshot == snapshot

    def test_decision_adopted_accessibility(self):
        """Valid snapshot with text should produce adopted_accessibility decision."""
        from openrecall.client.accessibility.policy import make_accessibility_decision
        from openrecall.client.accessibility.types import (
            TreeSnapshot,
            REASON_ADOPTED_ACCESSIBILITY,
        )

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
            content_hash=123456789,
            simhash=987654321,
            captured_at=datetime(2026, 3, 19, 10, 21, 35),
            duration_ms=15,
        )

        decision = make_accessibility_decision(
            target_device_name="monitor_1",
            focused_device_name="monitor_1",
            app_name="Safari",
            snapshot=snapshot,
        )

        assert decision.eligible is True
        assert decision.adopted is True
        assert decision.reason == REASON_ADOPTED_ACCESSIBILITY
        assert decision.snapshot == snapshot


class TestBrowserCandidateDetection:
    """Tests for browser candidate detection."""

    def test_import_is_browser_candidate(self):
        """is_browser_candidate should be importable from policy module."""
        from openrecall.client.accessibility.policy import is_browser_candidate

    def test_safari_is_browser_candidate(self):
        """Safari should be detected as browser candidate."""
        from openrecall.client.accessibility.policy import is_browser_candidate

        assert is_browser_candidate("Safari")
        assert is_browser_candidate("safari")
        assert is_browser_candidate("SAFARI")

    def test_chrome_is_browser_candidate(self):
        """Chrome should be detected as browser candidate."""
        from openrecall.client.accessibility.policy import is_browser_candidate

        assert is_browser_candidate("Google Chrome")
        assert is_browser_candidate("Chrome")
        assert is_browser_candidate("CHROME")
        assert is_browser_candidate("chrome")

    def test_non_browser_apps(self):
        """Non-browser apps should not be detected as browser candidates."""
        from openrecall.client.accessibility.policy import is_browser_candidate

        assert not is_browser_candidate("Finder")
        assert not is_browser_candidate("Terminal")
        assert not is_browser_candidate("VS Code")
        assert not is_browser_candidate("Mail")

    def test_edge_cases(self):
        """Edge cases for browser detection."""
        from openrecall.client.accessibility.policy import is_browser_candidate

        # Apps with 'chrome' or 'safari' in name
        assert is_browser_candidate("Chrome Canary")
        assert is_browser_candidate("Safari Technology Preview")

        # Empty/None
        assert not is_browser_candidate("")
        assert not is_browser_candidate(None)
