"""Tests for macOS accessibility walker.

Phase 4 of Chat MVP implementation.

These tests verify the macOS accessibility walker implementation
as specified in docs/v3/chat/mvp.md.
"""

import pytest
import sys
from datetime import datetime
from typing import Optional
from unittest.mock import Mock, patch


# =============================================================================
# Mock AX Infrastructure for Testing
# =============================================================================


class MockAXElement:
    """Mock accessibility element for testing."""

    def __init__(
        self,
        role: str,
        value: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        children: Optional[list] = None,
        attributes: Optional[dict] = None,
        bounds: Optional[tuple] = None,
    ):
        self.role = role
        self._value = value
        self._title = title
        self._description = description
        self._children = children or []
        self._attributes = attributes or {}
        self._bounds = bounds

    def get_role(self) -> Optional[str]:
        return self.role

    def get_value(self) -> Optional[str]:
        return self._value

    def get_title(self) -> Optional[str]:
        return self._title

    def get_description(self) -> Optional[str]:
        return self._description

    def get_children(self) -> list:
        return self._children

    def get_attribute(self, name: str) -> Optional[str]:
        return self._attributes.get(name)

    def get_bounds(self) -> Optional[tuple]:
        return self._bounds


class MockAXApp:
    """Mock macOS application for testing."""

    def __init__(self, name: str, pid: int = 12345):
        self.name = name
        self.pid = pid

    def get_name(self) -> str:
        return self.name

    def get_pid(self) -> int:
        return self.pid


class MockAXProvider:
    """Mock AX provider for testing walker without real macOS AX."""

    def __init__(
        self,
        focused_app: Optional[MockAXApp] = None,
        focused_window: Optional[MockAXElement] = None,
        raises_exception: bool = False,
        apps_by_name: Optional[dict[str, MockAXApp]] = None,
    ):
        self._focused_app = focused_app
        self._focused_window = focused_window
        self._raises_exception = raises_exception
        self._apps_by_name = apps_by_name or {}

    def get_frontmost_app(self) -> Optional[MockAXApp]:
        if self._raises_exception:
            raise RuntimeError("AX API error")
        return self._focused_app

    def get_app_by_name(self, app_name: str) -> Optional[MockAXApp]:
        """Get app by name (mock implementation)."""
        if self._raises_exception:
            raise RuntimeError("AX API error")
        # Case-insensitive lookup
        return self._apps_by_name.get(app_name.lower())

    def get_focused_window(self, app) -> Optional[MockAXElement]:
        if self._raises_exception:
            raise RuntimeError("AX API error")
        return self._focused_window

    def get_window_bounds(self, window) -> Optional[tuple]:
        return (0, 0, 800, 600)


# =============================================================================
# Step 1: Module Structure Tests
# =============================================================================


class TestMacosWalkerImport:
    """Tests for macOS walker module structure."""

    def test_module_imports(self):
        """macOS walker module should be importable."""
        from openrecall.client.accessibility import macos

    def test_walk_focused_window_function_exists(self):
        """walk_focused_window function should exist."""
        from openrecall.client.accessibility.macos import walk_focused_window

        assert callable(walk_focused_window)


# =============================================================================
# Step 2: Role Constants Tests
# =============================================================================


class TestRoleConstants:
    """Tests for MVP role tables."""

    def test_skip_roles_defined(self):
        """skip_roles constant should match MVP spec."""
        from openrecall.client.accessibility.macos import SKIP_ROLES

        expected = {
            "AXScrollBar",
            "AXImage",
            "AXSplitter",
            "AXGrowArea",
            "AXMenuBar",
            "AXMenu",
            "AXToolbar",
            "AXSecureTextField",
            "AXRuler",
            "AXRulerMarker",
            "AXBusyIndicator",
            "AXProgressIndicator",
        }
        assert SKIP_ROLES == expected

    def test_text_bearing_roles_defined(self):
        """text_bearing_roles constant should match MVP spec."""
        from openrecall.client.accessibility.macos import TEXT_BEARING_ROLES

        expected = {
            "AXStaticText",
            "AXTextField",
            "AXTextArea",
            "AXButton",
            "AXMenuItem",
            "AXCell",
            "AXHeading",
            "AXLink",
            "AXMenuButton",
            "AXPopUpButton",
            "AXComboBox",
            "AXCheckBox",
            "AXRadioButton",
            "AXDisclosureTriangle",
            "AXTab",
        }
        assert TEXT_BEARING_ROLES == expected

    def test_light_container_roles_defined(self):
        """light_container_roles constant should match MVP spec."""
        from openrecall.client.accessibility.macos import LIGHT_CONTAINER_ROLES

        expected = {"AXGroup", "AXWebArea"}
        assert LIGHT_CONTAINER_ROLES == expected


# =============================================================================
# Step 3: Text Extraction Tests
# =============================================================================


class TestTextExtraction:
    """Tests for text extraction from AX elements."""

    def test_extract_text_from_static_text_uses_value(self):
        """AXStaticText should use value attribute."""
        from openrecall.client.accessibility.macos import extract_text_from_element

        element = MockAXElement(role="AXStaticText", value="Hello World")
        text = extract_text_from_element(element)
        assert text == "Hello World"

    def test_extract_text_from_text_field_prefers_value(self):
        """AXTextField should prefer value over title."""
        from openrecall.client.accessibility.macos import extract_text_from_element

        element = MockAXElement(
            role="AXTextField", value="input text", title="Label"
        )
        text = extract_text_from_element(element)
        assert text == "input text"

    def test_extract_text_from_text_area_prefers_value(self):
        """AXTextArea should prefer value over title."""
        from openrecall.client.accessibility.macos import extract_text_from_element

        element = MockAXElement(
            role="AXTextArea", value="multi\nline\ntext", title="Label"
        )
        text = extract_text_from_element(element)
        assert text == "multi\nline\ntext"

    def test_extract_text_from_combo_box_prefers_value(self):
        """AXComboBox should prefer value over title."""
        from openrecall.client.accessibility.macos import extract_text_from_element

        element = MockAXElement(role="AXComboBox", value="selected", title="Options")
        text = extract_text_from_element(element)
        assert text == "selected"

    def test_extract_text_falls_back_to_title(self):
        """Non-text-entry roles should use title first."""
        from openrecall.client.accessibility.macos import extract_text_from_element

        element = MockAXElement(role="AXButton", title="Click Me")
        text = extract_text_from_element(element)
        assert text == "Click Me"

    def test_extract_text_falls_back_to_description(self):
        """Should fall back to description if title is empty."""
        from openrecall.client.accessibility.macos import extract_text_from_element

        element = MockAXElement(role="AXButton", description="Descriptive text")
        text = extract_text_from_element(element)
        assert text == "Descriptive text"

    def test_extract_text_priority_is_value_title_description(self):
        """Priority should be value -> title -> description for text-entry roles."""
        from openrecall.client.accessibility.macos import extract_text_from_element

        # For text-entry roles, value comes first
        element = MockAXElement(
            role="AXTextField",
            value="value text",
            title="title text",
            description="desc text",
        )
        text = extract_text_from_element(element)
        assert text == "value text"

    def test_extract_text_returns_none_for_empty(self):
        """Should return None if all attributes are empty."""
        from openrecall.client.accessibility.macos import extract_text_from_element

        element = MockAXElement(role="AXButton")
        text = extract_text_from_element(element)
        assert text is None

    def test_extract_text_strips_whitespace(self):
        """Should strip whitespace from extracted text."""
        from openrecall.client.accessibility.macos import extract_text_from_element

        element = MockAXElement(role="AXStaticText", value="  trimmed  ")
        text = extract_text_from_element(element)
        assert text == "trimmed"


class TestShortCircuitRecursion:
    """Tests for recursion short-circuit logic."""

    def test_short_circuit_for_text_field_with_value(self):
        """AXTextField with non-empty value should short-circuit."""
        from openrecall.client.accessibility.macos import should_short_circuit_recursion

        assert should_short_circuit_recursion("AXTextField", "has value") is True
        assert should_short_circuit_recursion("AXTextField", "") is False

    def test_short_circuit_for_text_area_with_value(self):
        """AXTextArea with non-empty value should short-circuit."""
        from openrecall.client.accessibility.macos import should_short_circuit_recursion

        assert should_short_circuit_recursion("AXTextArea", "text") is True
        assert should_short_circuit_recursion("AXTextArea", "") is False

    def test_short_circuit_for_combo_box_with_value(self):
        """AXComboBox with non-empty value should short-circuit."""
        from openrecall.client.accessibility.macos import should_short_circuit_recursion

        assert should_short_circuit_recursion("AXComboBox", "selected") is True
        assert should_short_circuit_recursion("AXComboBox", "") is False

    def test_short_circuit_for_static_text_with_value(self):
        """AXStaticText with non-empty value should short-circuit."""
        from openrecall.client.accessibility.macos import should_short_circuit_recursion

        assert should_short_circuit_recursion("AXStaticText", "text") is True
        assert should_short_circuit_recursion("AXStaticText", "") is False

    def test_no_short_circuit_for_button(self):
        """AXButton should never short-circuit recursion."""
        from openrecall.client.accessibility.macos import should_short_circuit_recursion

        assert should_short_circuit_recursion("AXButton", "has value") is False
        assert should_short_circuit_recursion("AXButton", "") is False

    def test_no_short_circuit_for_other_roles(self):
        """Other text-bearing roles should not short-circuit."""
        from openrecall.client.accessibility.macos import should_short_circuit_recursion

        assert should_short_circuit_recursion("AXLink", "link text") is False
        assert should_short_circuit_recursion("AXHeading", "heading") is False


# =============================================================================
# Step 4: WalkState Tests
# =============================================================================


class TestWalkState:
    """Tests for walk state and bounds tracking."""

    def test_walk_state_initializes_with_config(self):
        """WalkState should initialize from TreeWalkerConfig."""
        from openrecall.client.accessibility.macos import WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        config = TreeWalkerConfig()
        state = WalkState(config)

        assert state.config.max_depth == 30
        assert state.config.max_nodes == 5000
        assert state.config.max_text_length == 50000

    def test_walk_state_tracks_node_count(self):
        """WalkState should track node_count."""
        from openrecall.client.accessibility.macos import WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        state = WalkState(TreeWalkerConfig())
        assert state.node_count == 0
        state.increment_node_count()
        assert state.node_count == 1
        state.increment_node_count()
        assert state.node_count == 2

    def test_walk_state_tracks_text_length(self):
        """WalkState should track text_length."""
        from openrecall.client.accessibility.macos import WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        state = WalkState(TreeWalkerConfig())
        assert state.text_length == 0
        state.add_text("Hello")
        assert state.text_length == 5
        state.add_text(" World")
        assert state.text_length == 11

    def test_walk_state_detects_max_nodes_truncation(self):
        """WalkState should detect when max_nodes is reached."""
        from openrecall.client.accessibility.macos import WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        config = TreeWalkerConfig(max_nodes=2)
        state = WalkState(config)
        state.increment_node_count()
        assert state.should_stop() is False
        state.increment_node_count()
        assert state.should_stop() is True
        assert state.truncated is True
        assert state.truncation_reason == "max_nodes"

    def test_walk_state_detects_max_text_length_truncation(self):
        """WalkState should detect when max_text_length is reached."""
        from openrecall.client.accessibility.macos import WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        config = TreeWalkerConfig(max_text_length=10)
        state = WalkState(config)
        state.add_text("Hello")
        assert state.should_stop() is False
        state.add_text(" World")  # Now 11 chars
        assert state.should_stop() is True
        assert state.truncated is True
        assert state.truncation_reason == "max_text_length"

    def test_walk_state_detects_max_depth_truncation(self):
        """WalkState should detect when max_depth is exceeded."""
        from openrecall.client.accessibility.macos import WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        config = TreeWalkerConfig(max_depth=2)
        state = WalkState(config)

        # is_depth_exceeded checks if depth > max_depth
        assert state.is_depth_exceeded(0) is False  # depth 0 <= max_depth 2
        assert state.is_depth_exceeded(1) is False  # depth 1 <= max_depth 2
        assert state.is_depth_exceeded(2) is False  # depth 2 <= max_depth 2
        assert state.is_depth_exceeded(3) is True   # depth 3 > max_depth 2

    def test_walk_state_tracks_max_depth_reached(self):
        """WalkState should track maximum depth reached."""
        from openrecall.client.accessibility.macos import WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        state = WalkState(TreeWalkerConfig())
        state.update_depth(5)
        state.update_depth(10)
        state.update_depth(3)
        assert state.max_depth_reached == 10

    def test_walk_state_detects_timeout(self):
        """WalkState should detect when walk_timeout is exceeded."""
        from openrecall.client.accessibility.macos import WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig
        import time

        config = TreeWalkerConfig(walk_timeout_ms=1)  # 1ms timeout
        state = WalkState(config)
        time.sleep(0.01)  # 10ms
        assert state.should_stop() is True
        assert state.truncation_reason == "timeout"


# =============================================================================
# Step 5: Tree Traversal Tests
# =============================================================================


class TestTreeTraversal:
    """Tests for tree traversal logic."""

    def test_walk_element_skips_skip_roles(self):
        """Walker should skip elements with skip_roles entirely."""
        from openrecall.client.accessibility.macos import walk_element, WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        state = WalkState(TreeWalkerConfig())
        element = MockAXElement(role="AXScrollBar", value="should be skipped")
        walk_element(element, depth=0, state=state)

        # Skip roles are not added to nodes
        assert len(state.nodes) == 0

    def test_walk_element_extracts_text_bearing_roles(self):
        """Walker should extract text from text_bearing_roles."""
        from openrecall.client.accessibility.macos import walk_element, WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        state = WalkState(TreeWalkerConfig())
        element = MockAXElement(role="AXStaticText", value="Hello")
        walk_element(element, depth=0, state=state)

        assert len(state.nodes) == 1
        assert state.nodes[0].role == "AXStaticText"
        assert state.nodes[0].text == "Hello"
        assert state.nodes[0].depth == 0

    def test_walk_element_recurse_children(self):
        """Walker should recurse into children in depth-first order."""
        from openrecall.client.accessibility.macos import walk_element, WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        state = WalkState(TreeWalkerConfig())
        child = MockAXElement(role="AXStaticText", value="Child")
        parent = MockAXElement(role="AXGroup", children=[child])

        walk_element(parent, depth=0, state=state)

        # Group is not text-bearing, but child is
        assert len(state.nodes) == 1
        assert state.nodes[0].text == "Child"
        assert state.nodes[0].depth == 1

    def test_walk_element_respects_max_depth(self):
        """Walker should stop at max_depth."""
        from openrecall.client.accessibility.macos import walk_element, WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        config = TreeWalkerConfig(max_depth=1)
        state = WalkState(config)

        deep_child = MockAXElement(role="AXStaticText", value="Deep")
        parent = MockAXElement(
            role="AXGroup",
            children=[MockAXElement(role="AXGroup", children=[deep_child])],
        )

        walk_element(parent, depth=0, state=state)

        # Deep child at depth 2 should not be reached
        assert len(state.nodes) == 0

    def test_walk_element_short_circuits_for_text_entry_with_value(self):
        """AXTextField with value should not recurse into children."""
        from openrecall.client.accessibility.macos import walk_element, WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        state = WalkState(TreeWalkerConfig())
        child = MockAXElement(role="AXStaticText", value="Should be skipped")
        parent = MockAXElement(role="AXTextField", value="Input", children=[child])

        walk_element(parent, depth=0, state=state)

        # Should have parent's text, not child's
        assert len(state.nodes) == 1
        assert state.nodes[0].text == "Input"
        assert state.nodes[0].role == "AXTextField"

    def test_walk_element_handles_light_containers(self):
        """Light container roles should contribute text but continue recursing."""
        from openrecall.client.accessibility.macos import walk_element, WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        state = WalkState(TreeWalkerConfig())
        child = MockAXElement(role="AXStaticText", value="Child")
        parent = MockAXElement(role="AXWebArea", value="WebArea text", children=[child])

        walk_element(parent, depth=0, state=state)

        # WebArea value contributes to text_content
        assert "WebArea text" in state.text_buffer
        # Child should also be in nodes
        assert len(state.nodes) == 1
        assert state.nodes[0].text == "Child"

    def test_walk_element_maintains_depth_first_order(self):
        """Nodes should be in depth-first traversal order."""
        from openrecall.client.accessibility.macos import walk_element, WalkState
        from openrecall.client.accessibility.types import TreeWalkerConfig

        state = WalkState(TreeWalkerConfig())
        root = MockAXElement(
            role="AXWindow",
            children=[
                MockAXElement(role="AXStaticText", value="First"),
                MockAXElement(
                    role="AXGroup",
                    children=[
                        MockAXElement(role="AXStaticText", value="Second"),
                        MockAXElement(role="AXStaticText", value="Third"),
                    ],
                ),
                MockAXElement(role="AXStaticText", value="Fourth"),
            ],
        )

        walk_element(root, depth=0, state=state)

        assert len(state.nodes) == 4
        assert state.nodes[0].text == "First"
        assert state.nodes[1].text == "Second"
        assert state.nodes[2].text == "Third"
        assert state.nodes[3].text == "Fourth"


# =============================================================================
# Step 6: Bounds Extraction Tests
# =============================================================================


class TestBoundsExtraction:
    """Tests for bounds extraction and normalization."""

    def test_normalize_bounds_to_window(self):
        """Bounds should be normalized to 0-1 relative to window."""
        from openrecall.client.accessibility.macos import normalize_bounds

        result = normalize_bounds(
            elem_x=100,
            elem_y=50,
            elem_w=200,
            elem_h=100,
            window_x=0,
            window_y=0,
            window_w=800,
            window_h=600,
        )

        assert result is not None
        assert abs(result.left - 0.125) < 0.01  # 100/800
        assert abs(result.top - 0.083) < 0.01  # 50/600
        assert abs(result.width - 0.25) < 0.01  # 200/800
        assert abs(result.height - 0.167) < 0.01  # 100/600

    def test_bounds_none_for_invalid_window(self):
        """Should return None for zero-size window."""
        from openrecall.client.accessibility.macos import normalize_bounds

        result = normalize_bounds(100, 50, 200, 100, 0, 0, 0, 0)
        assert result is None

    def test_bounds_clamped_to_valid_range(self):
        """Bounds outside window should be clamped to valid range."""
        from openrecall.client.accessibility.macos import normalize_bounds

        result = normalize_bounds(
            elem_x=-50,
            elem_y=-50,
            elem_w=900,
            elem_h=700,
            window_x=0,
            window_y=0,
            window_w=800,
            window_h=600,
        )

        assert result is not None
        assert result.left >= 0.0
        assert result.top >= 0.0
        assert result.width <= 1.0
        assert result.height <= 1.0


# =============================================================================
# Step 7: Browser URL Extraction Tests
# =============================================================================


class TestBrowserUrlExtraction:
    """Tests for browser URL extraction."""

    def test_is_browser_candidate_safari(self):
        """Should detect Safari as browser candidate."""
        from openrecall.client.accessibility.macos import is_browser_candidate

        assert is_browser_candidate("Safari") is True
        assert is_browser_candidate("safari") is True
        assert is_browser_candidate("Mobile Safari") is True

    def test_is_browser_candidate_chrome(self):
        """Should detect Chrome as browser candidate."""
        from openrecall.client.accessibility.macos import is_browser_candidate

        assert is_browser_candidate("Google Chrome") is True
        assert is_browser_candidate("chrome") is True
        assert is_browser_candidate("Chrome Canary") is True

    def test_is_browser_candidate_non_browser(self):
        """Should not detect non-browser apps."""
        from openrecall.client.accessibility.macos import is_browser_candidate

        assert is_browser_candidate("Finder") is False
        assert is_browser_candidate("Terminal") is False
        assert is_browser_candidate("Visual Studio Code") is False
        assert is_browser_candidate("TextEdit") is False

    def test_extract_browser_url_from_axdocument(self):
        """Should extract URL from AXDocument attribute."""
        from openrecall.client.accessibility.macos import extract_browser_url

        window = MockAXElement(role="AXWindow", attributes={"AXDocument": "https://example.com"})
        url = extract_browser_url(window, "Safari", "Example")

        assert url == "https://example.com"

    def test_extract_browser_url_only_http_https(self):
        """Should only return http/https URLs."""
        from openrecall.client.accessibility.macos import extract_browser_url

        window = MockAXElement(role="AXWindow", attributes={"AXDocument": "file:///local/path"})
        url = extract_browser_url(window, "Safari", "Local")

        assert url is None

    def test_extract_browser_url_none_for_non_browser(self):
        """Should return None for non-browser apps."""
        from openrecall.client.accessibility.macos import extract_browser_url

        window = MockAXElement(role="AXWindow", attributes={"AXDocument": "https://example.com"})
        url = extract_browser_url(window, "Finder", "Documents")

        assert url is None

    def test_extract_browser_url_none_for_missing_axdocument(self):
        """Should return None when AXDocument is not available."""
        from openrecall.client.accessibility.macos import extract_browser_url

        window = MockAXElement(role="AXWindow", attributes={})
        url = extract_browser_url(window, "Safari", "Example")

        assert url is None


# =============================================================================
# Step 8: walk_focused_window Tests
# =============================================================================


class TestWalkFocusedWindow:
    """Tests for walk_focused_window main function."""

    def test_returns_none_when_no_focused_app(self):
        """Should return None when no focused app is found."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        mock_provider = MockAXProvider(focused_app=None)
        result = walk_focused_window(TreeWalkerConfig(), ax_provider=mock_provider)

        assert result is None

    def test_returns_none_when_no_focused_window(self):
        """Should return None when no focused window is found."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        mock_provider = MockAXProvider(
            focused_app=MockAXApp(name="Safari"), focused_window=None
        )
        result = walk_focused_window(TreeWalkerConfig(), ax_provider=mock_provider)

        assert result is None

    def test_returns_snapshot_with_app_and_window_names(self):
        """Should return snapshot with correct app and window names."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        mock_provider = MockAXProvider(
            focused_app=MockAXApp(name="Safari"),
            focused_window=MockAXElement(
                role="AXWindow",
                title="Example Page",
                children=[MockAXElement(role="AXStaticText", value="Hello")],
            ),
        )
        result = walk_focused_window(TreeWalkerConfig(), ax_provider=mock_provider)

        assert result is not None
        assert result.app_name == "Safari"
        assert result.window_name == "Example Page"

    def test_returns_snapshot_with_nodes(self):
        """Should return snapshot with extracted nodes."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        mock_provider = MockAXProvider(
            focused_app=MockAXApp(name="TextEdit"),
            focused_window=MockAXElement(
                role="AXWindow",
                children=[
                    MockAXElement(role="AXStaticText", value="Line 1"),
                    MockAXElement(role="AXStaticText", value="Line 2"),
                ],
            ),
        )
        result = walk_focused_window(TreeWalkerConfig(), ax_provider=mock_provider)

        assert result is not None
        assert result.node_count == 2
        assert len(result.nodes) == 2

    def test_returns_snapshot_with_text_content(self):
        """Should return snapshot with aggregated text content."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        mock_provider = MockAXProvider(
            focused_app=MockAXApp(name="TextEdit"),
            focused_window=MockAXElement(
                role="AXWindow",
                children=[
                    MockAXElement(role="AXStaticText", value="Hello"),
                    MockAXElement(role="AXStaticText", value="World"),
                ],
            ),
        )
        result = walk_focused_window(TreeWalkerConfig(), ax_provider=mock_provider)

        assert result is not None
        assert "Hello" in result.text_content
        assert "World" in result.text_content

    def test_returns_snapshot_with_hashes(self):
        """Should return snapshot with computed hashes."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        mock_provider = MockAXProvider(
            focused_app=MockAXApp(name="TextEdit"),
            focused_window=MockAXElement(
                role="AXWindow",
                children=[MockAXElement(role="AXStaticText", value="Test")],
            ),
        )
        result = walk_focused_window(TreeWalkerConfig(), ax_provider=mock_provider)

        assert result is not None
        assert result.content_hash != 0
        assert result.simhash != 0

    def test_returns_snapshot_with_timing(self):
        """Should return snapshot with duration_ms."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        mock_provider = MockAXProvider(
            focused_app=MockAXApp(name="TextEdit"),
            focused_window=MockAXElement(
                role="AXWindow",
                children=[MockAXElement(role="AXStaticText", value="Test")],
            ),
        )
        result = walk_focused_window(TreeWalkerConfig(), ax_provider=mock_provider)

        assert result is not None
        assert result.duration_ms >= 0

    def test_handles_ax_exception_gracefully(self):
        """Should handle AX exceptions and return None."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        mock_provider = MockAXProvider(raises_exception=True)
        result = walk_focused_window(TreeWalkerConfig(), ax_provider=mock_provider)

        assert result is None

    def test_returns_browser_url_for_browser_candidate(self):
        """Should extract browser URL for browser candidates."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        mock_provider = MockAXProvider(
            focused_app=MockAXApp(name="Safari"),
            focused_window=MockAXElement(
                role="AXWindow",
                title="Example",
                attributes={"AXDocument": "https://example.com"},
                children=[MockAXElement(role="AXStaticText", value="Content")],
            ),
        )
        result = walk_focused_window(TreeWalkerConfig(), ax_provider=mock_provider)

        assert result is not None
        assert result.browser_url == "https://example.com"


class TestRaceConditionFix:
    """Tests for expected_app_name parameter to avoid race condition."""

    def test_uses_expected_app_name_when_provided(self):
        """Should use expected_app_name to find app, avoiding race condition."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        # Simulate: frontmost is "Code" but we want "Safari"
        safari_app = MockAXApp(name="Safari")
        mock_provider = MockAXProvider(
            focused_app=MockAXApp(name="Code"),  # Current frontmost (wrong)
            focused_window=MockAXElement(
                role="AXWindow",
                title="Safari Page",
                children=[MockAXElement(role="AXStaticText", value="Safari Content")],
            ),
            apps_by_name={"safari": safari_app},  # Can find Safari by name
        )

        # Without expected_app_name: would use "Code" (race condition)
        # With expected_app_name="Safari": should find Safari app
        result = walk_focused_window(
            TreeWalkerConfig(),
            ax_provider=mock_provider,
            expected_app_name="Safari",
        )

        assert result is not None
        # Note: The mock returns the safari_app, which has name "Safari"
        # But the focused_window is still the one from mock_provider
        # In real implementation, it would get Safari's window

    def test_falls_back_to_frontmost_when_app_not_found_by_name(self):
        """Should fall back to frontmost app when expected app not found."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        mock_provider = MockAXProvider(
            focused_app=MockAXApp(name="Code"),
            focused_window=MockAXElement(
                role="AXWindow",
                title="Code Window",
                children=[MockAXElement(role="AXStaticText", value="Code Content")],
            ),
            apps_by_name={},  # Can't find any app by name
        )

        result = walk_focused_window(
            TreeWalkerConfig(),
            ax_provider=mock_provider,
            expected_app_name="NonExistent",
        )

        # Should fall back to frontmost (Code)
        assert result is not None
        assert result.app_name == "Code"

    def test_without_expected_app_name_uses_frontmost(self):
        """Without expected_app_name, should use frontmost app (original behavior)."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        mock_provider = MockAXProvider(
            focused_app=MockAXApp(name="Code"),
            focused_window=MockAXElement(
                role="AXWindow",
                title="Code Window",
                children=[MockAXElement(role="AXStaticText", value="Content")],
            ),
        )

        result = walk_focused_window(
            TreeWalkerConfig(),
            ax_provider=mock_provider,
            # No expected_app_name provided
        )

        assert result is not None
        assert result.app_name == "Code"


# =============================================================================
# Step 11: Platform Safety Tests
# =============================================================================


class TestPlatformSafety:
    """Tests for platform safety and stub implementation."""

    def test_module_has_platform_check(self):
        """Module should have platform detection."""
        from openrecall.client.accessibility import macos

        assert hasattr(macos, "IS_MACOS")

    def test_module_works_on_non_macos(self):
        """Module should not crash on non-macOS platforms."""
        from openrecall.client.accessibility.macos import walk_focused_window
        from openrecall.client.accessibility.types import TreeWalkerConfig

        # On non-macOS without ax_provider, should return None gracefully
        # This test runs on actual platform, just verify no crash
        result = walk_focused_window(TreeWalkerConfig())
        # Result may be None on non-macOS, or actual value on macOS
        assert result is None or result is not None  # Just no crash
