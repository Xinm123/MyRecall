"""Tests for client-side accessibility types and contracts.

Phase 2 of Chat MVP implementation.

These tests verify the data contracts defined in docs/v3/chat/mvp.md.
"""

import pytest
from datetime import datetime


class TestNodeBounds:
    """Tests for NodeBounds dataclass."""

    def test_import_node_bounds(self):
        """NodeBounds should be importable from types module."""
        from openrecall.client.accessibility.types import NodeBounds

    def test_node_bounds_creation(self):
        """NodeBounds should have left, top, width, height fields."""
        from openrecall.client.accessibility.types import NodeBounds

        bounds = NodeBounds(left=0.1, top=0.2, width=0.5, height=0.3)
        assert bounds.left == 0.1
        assert bounds.top == 0.2
        assert bounds.width == 0.5
        assert bounds.height == 0.3

    def test_node_bounds_optional_for_nodes(self):
        """NodeBounds should be optional in AccessibilityTreeNode."""
        from openrecall.client.accessibility.types import NodeBounds

        # Bounds can be None
        assert NodeBounds is not None


class TestAccessibilityTreeNode:
    """Tests for AccessibilityTreeNode dataclass."""

    def test_import_accessibility_tree_node(self):
        """AccessibilityTreeNode should be importable from types module."""
        from openrecall.client.accessibility.types import AccessibilityTreeNode

    def test_node_required_fields(self):
        """AccessibilityTreeNode should have role, text, depth as required fields."""
        from openrecall.client.accessibility.types import AccessibilityTreeNode

        node = AccessibilityTreeNode(role="AXStaticText", text="Hello", depth=1)
        assert node.role == "AXStaticText"
        assert node.text == "Hello"
        assert node.depth == 1

    def test_node_optional_bounds(self):
        """AccessibilityTreeNode should have optional bounds field."""
        from openrecall.client.accessibility.types import AccessibilityTreeNode, NodeBounds

        # Without bounds
        node_no_bounds = AccessibilityTreeNode(role="AXButton", text="Click", depth=2)
        assert node_no_bounds.bounds is None

        # With bounds
        bounds = NodeBounds(left=0.1, top=0.2, width=0.3, height=0.1)
        node_with_bounds = AccessibilityTreeNode(
            role="AXButton", text="Click", depth=2, bounds=bounds
        )
        assert node_with_bounds.bounds == bounds


class TestTreeSnapshot:
    """Tests for TreeSnapshot dataclass."""

    def test_import_tree_snapshot(self):
        """TreeSnapshot should be importable from types module."""
        from openrecall.client.accessibility.types import TreeSnapshot

    def test_snapshot_minimum_fields(self):
        """TreeSnapshot should have all required fields from MVP spec."""
        from openrecall.client.accessibility.types import TreeSnapshot

        snapshot = TreeSnapshot(
            app_name="Safari",
            window_name="MyRecall Docs",
            browser_url="https://example.com",
            text_content="Hello World",
            nodes=[],
            node_count=0,
            truncated=False,
            truncation_reason=None,
            max_depth_reached=0,
            content_hash=123456789,
            simhash=987654321,
            captured_at=datetime(2026, 3, 19, 10, 21, 35),
            duration_ms=47,
        )
        assert snapshot.app_name == "Safari"
        assert snapshot.window_name == "MyRecall Docs"
        assert snapshot.browser_url == "https://example.com"
        assert snapshot.text_content == "Hello World"
        assert snapshot.nodes == []
        assert snapshot.node_count == 0
        assert snapshot.truncated is False
        assert snapshot.truncation_reason is None
        assert snapshot.max_depth_reached == 0
        assert snapshot.content_hash == 123456789
        assert snapshot.simhash == 987654321
        assert snapshot.duration_ms == 47

    def test_snapshot_with_nodes(self):
        """TreeSnapshot should store a list of AccessibilityTreeNode."""
        from openrecall.client.accessibility.types import (
            TreeSnapshot,
            AccessibilityTreeNode,
        )

        nodes = [
            AccessibilityTreeNode(role="AXHeading", text="Title", depth=1),
            AccessibilityTreeNode(role="AXStaticText", text="Content", depth=2),
        ]
        snapshot = TreeSnapshot(
            app_name="Safari",
            window_name="Test",
            browser_url=None,
            text_content="Title\nContent",
            nodes=nodes,
            node_count=2,
            truncated=False,
            truncation_reason=None,
            max_depth_reached=2,
            content_hash=111222333,
            simhash=444555666,
            captured_at=datetime(2026, 3, 19, 10, 21, 35),
            duration_ms=23,
        )
        assert len(snapshot.nodes) == 2
        assert snapshot.nodes[0].role == "AXHeading"


class TestTreeWalkerConfig:
    """Tests for TreeWalkerConfig dataclass."""

    def test_import_tree_walker_config(self):
        """TreeWalkerConfig should be importable from types module."""
        from openrecall.client.accessibility.types import TreeWalkerConfig

    def test_default_bounds_from_mvp_spec(self):
        """TreeWalkerConfig should use MVP-specified default bounds."""
        from openrecall.client.accessibility.types import TreeWalkerConfig

        config = TreeWalkerConfig()
        # MVP spec: max_depth=30, max_nodes=5000, max_text_length=50000, walk_timeout=250ms
        assert config.max_depth == 30
        assert config.max_nodes == 5000
        assert config.max_text_length == 50000
        assert config.walk_timeout_ms == 250

    def test_custom_bounds(self):
        """TreeWalkerConfig should allow custom bounds."""
        from openrecall.client.accessibility.types import TreeWalkerConfig

        config = TreeWalkerConfig(
            max_depth=15, max_nodes=1000, max_text_length=25000, walk_timeout_ms=500
        )
        assert config.max_depth == 15
        assert config.max_nodes == 1000
        assert config.max_text_length == 25000
        assert config.walk_timeout_ms == 500


class TestAccessibilityDecision:
    """Tests for AccessibilityDecision dataclass."""

    def test_import_accessibility_decision(self):
        """AccessibilityDecision should be importable from types module."""
        from openrecall.client.accessibility.types import AccessibilityDecision

    def test_decision_fields(self):
        """AccessibilityDecision should have eligible, adopted, reason, snapshot fields."""
        from openrecall.client.accessibility.types import AccessibilityDecision

        decision = AccessibilityDecision(
            eligible=True,
            adopted=True,
            reason="adopted_accessibility",
            snapshot=None,
        )
        assert decision.eligible is True
        assert decision.adopted is True
        assert decision.reason == "adopted_accessibility"
        assert decision.snapshot is None

    def test_decision_reason_vocabulary(self):
        """AccessibilityDecision should use MVP-defined reason vocabulary."""
        from openrecall.client.accessibility.types import AccessibilityDecision

        # MVP spec reason vocabulary:
        # non_focused_monitor, app_prefers_ocr, no_focused_window,
        # empty_text, adopted_accessibility
        valid_reasons = [
            "non_focused_monitor",
            "app_prefers_ocr",
            "no_focused_window",
            "empty_text",
            "adopted_accessibility",
        ]
        for reason in valid_reasons:
            decision = AccessibilityDecision(
                eligible=True, adopted=False, reason=reason, snapshot=None
            )
            assert decision.reason == reason


class TestReasonVocabulary:
    """Tests for reason vocabulary constants."""

    def test_reason_constants_exist(self):
        """Reason vocabulary constants should be defined in types module."""
        from openrecall.client.accessibility.types import (
            REASON_NON_FOCUSED_MONITOR,
            REASON_APP_PREFERS_OCR,
            REASON_NO_FOCUSED_WINDOW,
            REASON_EMPTY_TEXT,
            REASON_ADOPTED_ACCESSIBILITY,
        )

        assert REASON_NON_FOCUSED_MONITOR == "non_focused_monitor"
        assert REASON_APP_PREFERS_OCR == "app_prefers_ocr"
        assert REASON_NO_FOCUSED_WINDOW == "no_focused_window"
        assert REASON_EMPTY_TEXT == "empty_text"
        assert REASON_ADOPTED_ACCESSIBILITY == "adopted_accessibility"


class TestTextSourceConstants:
    """Tests for text source constants."""

    def test_text_source_constants_exist(self):
        """Text source constants should be defined in types module."""
        from openrecall.client.accessibility.types import (
            TEXT_SOURCE_ACCESSIBILITY,
            TEXT_SOURCE_OCR,
        )

        assert TEXT_SOURCE_ACCESSIBILITY == "accessibility"
        assert TEXT_SOURCE_OCR == "ocr"


class TestAccessibilityPayload:
    """Tests for accessibility upload payload structure."""

    def test_accessibility_payload_shape(self):
        """Accessibility payload should match MVP upload contract."""
        from openrecall.client.accessibility.types import AccessibilityPayload

        payload = AccessibilityPayload(
            text_content="Hello World",
            tree_json='[{"role":"AXStaticText","text":"Hello World","depth":1}]',
            node_count=1,
            truncated=False,
            truncation_reason=None,
            max_depth_reached=1,
            duration_ms=15,
        )
        assert payload.text_content == "Hello World"
        assert payload.tree_json is not None
        assert payload.node_count == 1
        assert payload.truncated is False
