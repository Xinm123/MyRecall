"""macOS accessibility walker implementation.

Phase 4 of Chat MVP implementation.

This module implements the bounded focused-window accessibility tree walker
for macOS using the Accessibility API via PyObjC.

The walker produces a flat depth-first list of text-bearing nodes,
as specified in docs/v3/chat/mvp.md.
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Protocol

from .types import (
    AccessibilityTreeNode,
    NodeBounds,
    TreeSnapshot,
    TreeWalkerConfig,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# =============================================================================
# Platform Detection
# =============================================================================

IS_MACOS = sys.platform == "darwin"

# =============================================================================
# Role Tables (from MVP spec)
# =============================================================================

# Roles to skip entirely - not traversed, not extracted
SKIP_ROLES: frozenset[str] = frozenset({
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
})

# Roles that can have text extracted from them
TEXT_BEARING_ROLES: frozenset[str] = frozenset({
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
})

# Roles that contribute text but continue recursing
LIGHT_CONTAINER_ROLES: frozenset[str] = frozenset({
    "AXGroup",
    "AXWebArea",
})

# Roles that short-circuit recursion when they have non-empty value
TEXT_ENTRY_ROLES: frozenset[str] = frozenset({
    "AXTextField",
    "AXTextArea",
    "AXComboBox",
    "AXStaticText",
})

# Browser candidate substrings (case-insensitive)
_BROWSER_CANDIDATE_SUBSTRINGS = ("safari", "chrome")


# =============================================================================
# Text Extraction
# =============================================================================


def extract_text_from_element(element) -> Optional[str]:
    """Extract text from an accessibility element.

    Uses MVP extraction priority: value -> title -> description.
    For text-entry roles (AXTextField, AXTextArea, AXComboBox, AXStaticText),
    the 'value' attribute is preferred.

    Args:
        element: Accessibility element with get_value(), get_title(), get_description() methods

    Returns:
        Extracted text or None if all attributes are empty
    """
    role = element.get_role()

    # For text-entry roles, prefer value
    if role in TEXT_ENTRY_ROLES:
        value = element.get_value()
        if value and value.strip():
            return value.strip()

    # For other text-bearing roles, use title first
    title = element.get_title()
    if title and title.strip():
        return title.strip()

    # Fall back to description
    description = element.get_description()
    if description and description.strip():
        return description.strip()

    return None


def should_short_circuit_recursion(role: str, value: Optional[str]) -> bool:
    """Determine if recursion should be short-circuited for this element.

    Text-entry roles with non-empty value should not recurse into children.

    Args:
        role: The AX role of the element
        value: The value attribute (may be None or empty)

    Returns:
        True if recursion should be skipped
    """
    if role not in TEXT_ENTRY_ROLES:
        return False
    return bool(value and value.strip())


# =============================================================================
# Browser URL Extraction
# =============================================================================


def is_browser_candidate(app_name: str) -> bool:
    """Check if the app is a browser candidate for URL extraction.

    Browser candidates are apps whose names contain 'safari' or 'chrome'.

    Args:
        app_name: The application name

    Returns:
        True if this is a browser candidate
    """
    if not app_name:
        return False
    lower_name = app_name.lower()
    return any(substr in lower_name for substr in _BROWSER_CANDIDATE_SUBSTRINGS)


def extract_browser_url(window_element, app_name: str, window_name: str) -> Optional[str]:
    """Extract browser URL from a window element.

    Only extracts from browser candidates using AXDocument attribute.
    Only returns http/https URLs.

    Args:
        window_element: The window accessibility element
        app_name: Application name (for browser detection)
        window_name: Window title (unused but kept for API consistency)

    Returns:
        Browser URL if available, None otherwise
    """
    if not is_browser_candidate(app_name):
        return None

    # Try AXDocument attribute
    url = window_element.get_attribute("AXDocument")
    if not url:
        return None

    # Only return http/https URLs
    if url.startswith("http://") or url.startswith("https://"):
        return url

    return None


# =============================================================================
# Bounds Normalization
# =============================================================================


def normalize_bounds(
    elem_x: float,
    elem_y: float,
    elem_w: float,
    elem_h: float,
    window_x: float,
    window_y: float,
    window_w: float,
    window_h: float,
) -> Optional[NodeBounds]:
    """Normalize element bounds relative to window.

    Args:
        elem_x, elem_y, elem_w, elem_h: Element position and size
        window_x, window_y, window_w, window_h: Window position and size

    Returns:
        NodeBounds normalized to 0-1, or None if invalid
    """
    if window_w <= 0 or window_h <= 0:
        return None

    # Calculate relative position
    left = max(0.0, min(1.0, (elem_x - window_x) / window_w))
    top = max(0.0, min(1.0, (elem_y - window_y) / window_h))

    # Calculate relative size (clamped)
    width = max(0.0, min(1.0, elem_w / window_w))
    height = max(0.0, min(1.0, elem_h / window_h))

    return NodeBounds(left=left, top=top, width=width, height=height)


# =============================================================================
# Walk State
# =============================================================================


@dataclass
class WalkState:
    """State for a bounded accessibility tree walk.

    Tracks node count, text length, depth, and truncation state.
    """

    config: TreeWalkerConfig
    nodes: list[AccessibilityTreeNode] = field(default_factory=list)
    text_buffer: list[str] = field(default_factory=list)
    node_count: int = 0
    text_length: int = 0
    max_depth_reached: int = 0
    truncated: bool = False
    truncation_reason: Optional[str] = None
    _start_time: float = field(default_factory=time.time)

    def increment_node_count(self) -> None:
        """Increment node count."""
        self.node_count += 1

    def add_text(self, text: str) -> None:
        """Add text to the buffer."""
        self.text_buffer.append(text)
        self.text_length += len(text)

    def update_depth(self, depth: int) -> None:
        """Update maximum depth reached."""
        if depth > self.max_depth_reached:
            self.max_depth_reached = depth

    def should_stop(self) -> bool:
        """Check if walk should stop due to bounds or timeout."""
        # Check node count
        if self.node_count >= self.config.max_nodes:
            self.truncated = True
            self.truncation_reason = "max_nodes"
            return True

        # Check text length
        if self.text_length >= self.config.max_text_length:
            self.truncated = True
            self.truncation_reason = "max_text_length"
            return True

        # Check timeout
        elapsed_ms = (time.time() - self._start_time) * 1000
        if elapsed_ms >= self.config.walk_timeout_ms:
            self.truncated = True
            self.truncation_reason = "timeout"
            return True

        return False

    def is_depth_exceeded(self, depth: int) -> bool:
        """Check if depth exceeds max_depth."""
        return depth > self.config.max_depth


# =============================================================================
# Tree Traversal
# =============================================================================


def walk_element(
    element,
    depth: int,
    state: WalkState,
    window_bounds: Optional[tuple] = None,
) -> None:
    """Walk an accessibility element recursively.

    Performs bounded depth-first traversal, extracting text from
    text-bearing roles while respecting skip_roles and bounds.

    Args:
        element: The accessibility element to walk
        depth: Current depth in the tree
        state: Walk state for tracking bounds and nodes
        window_bounds: Optional (x, y, w, h) of the window for bounds normalization
    """
    # Check depth bound
    if state.is_depth_exceeded(depth):
        state.truncated = True
        if not state.truncation_reason:
            state.truncation_reason = "max_depth"
        return

    # Check if we should stop
    if state.should_stop():
        return

    state.update_depth(depth)

    role = element.get_role()
    if not role:
        role = "Unknown"

    # Skip entirely
    if role in SKIP_ROLES:
        return

    # Track visited elements
    state.increment_node_count()

    # Handle light container roles - contribute text but continue recursing
    if role in LIGHT_CONTAINER_ROLES:
        value = element.get_value()
        if value and value.strip():
            state.add_text(value.strip())
        # Continue to children
        for child in element.get_children():
            if state.should_stop():
                return
            walk_element(child, depth + 1, state, window_bounds)
        return

    # Handle text-bearing roles
    if role in TEXT_BEARING_ROLES:
        text = extract_text_from_element(element)

        if text:
            # Add to text buffer
            state.add_text(text)

            # Extract bounds if available
            bounds = None
            elem_bounds = element.get_bounds()
            if elem_bounds and window_bounds:
                ex, ey, ew, eh = elem_bounds
                wx, wy, ww, wh = window_bounds
                bounds = normalize_bounds(ex, ey, ew, eh, wx, wy, ww, wh)

            # Create node
            node = AccessibilityTreeNode(
                role=role,
                text=text,
                depth=depth,
                bounds=bounds,
            )
            state.nodes.append(node)

        # Check for short-circuit recursion
        if should_short_circuit_recursion(role, element.get_value()):
            return

        # Continue to children
        for child in element.get_children():
            if state.should_stop():
                return
            walk_element(child, depth + 1, state, window_bounds)
        return

    # Unknown roles - recurse into children
    for child in element.get_children():
        if state.should_stop():
            return
        walk_element(child, depth + 1, state, window_bounds)


# =============================================================================
# AX Provider Protocol and Real Implementation
# =============================================================================


class AXProvider(Protocol):
    """Protocol for AX providers (for dependency injection)."""

    def get_frontmost_app(self): ...

    def get_app_by_name(self, app_name: str): ...

    def get_focused_window(self, app): ...

    def get_window_bounds(self, window) -> Optional[tuple]: ...


class RealAXProvider:
    """Real macOS AX provider using PyObjC.

    Only works on macOS. Returns None on non-macOS platforms.
    """

    def __init__(self):
        if not IS_MACOS:
            self._workspace = None
            return

        try:
            from AppKit import NSWorkspace
            self._workspace = NSWorkspace.sharedWorkspace()
        except ImportError:
            self._workspace = None
            logger.debug("AppKit not available")

    def get_frontmost_app(self):
        """Get the frontmost application."""
        if not self._workspace:
            return None

        try:
            app = self._workspace.frontmostApplication()
            if app:
                return _AXAppWrapper(app)
        except Exception as e:
            logger.debug("Failed to get frontmost app: %s", e)

        return None

    def get_app_by_name(self, app_name: str):
        """Get an application by name.

        Searches through running applications to find one matching the given name.
        Returns the first match, or None if not found.

        Args:
            app_name: The application name to search for

        Returns:
            _AXAppWrapper for the matching app, or None
        """
        if not self._workspace or not app_name:
            return None

        try:
            # Get all running applications
            running_apps = self._workspace.runningApplications()
            for app in running_apps:
                try:
                    name = app.localizedName()
                    if name and name.lower() == app_name.lower():
                        return _AXAppWrapper(app)
                except Exception:
                    continue
        except Exception as e:
            logger.debug("Failed to get app by name '%s': %s", app_name, e)

        return None

    def get_focused_window(self, app) -> Optional["_AXWindowWrapper"]:
        """Get the focused window of an application."""
        if not app:
            return None

        try:
            return app.get_focused_window()
        except Exception as e:
            logger.debug("Failed to get focused window: %s", e)
            return None

    def get_window_bounds(self, window) -> Optional[tuple]:
        """Get window bounds as (x, y, width, height)."""
        if not window:
            return None

        try:
            return window.get_bounds()
        except Exception as e:
            logger.debug("Failed to get window bounds: %s", e)
            return None


class _AXAppWrapper:
    """Wrapper for NSRunningApplication with AX support."""

    def __init__(self, app):
        self._app = app
        self._ax_element = None
        try:
            from ApplicationServices import AXUIElementCreateApplication
            pid = app.processIdentifier()
            self._ax_element = AXUIElementCreateApplication(pid)
        except Exception as e:
            logger.debug("Failed to create AX element: %s", e)

    def get_name(self) -> str:
        """Get application name."""
        try:
            return self._app.localizedName() or ""
        except Exception:
            return ""

    def get_pid(self) -> int:
        """Get process ID."""
        try:
            return self._app.processIdentifier()
        except Exception:
            return 0

    def get_focused_window(self) -> Optional["_AXWindowWrapper"]:
        """Get focused window."""
        if not self._ax_element:
            return None

        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXFocusedWindowAttribute,
            )
            result = AXUIElementCopyAttributeValue(
                self._ax_element, kAXFocusedWindowAttribute, None
            )
            if result and len(result) == 2:
                err, window = result
                from ApplicationServices import kAXErrorSuccess
                if err == kAXErrorSuccess and window:
                    return _AXWindowWrapper(window)
        except Exception as e:
            logger.debug("Failed to get focused window: %s", e)

        return None


class _AXWindowWrapper:
    """Wrapper for AXUIElement representing a window."""

    def __init__(self, element):
        self._element = element

    def get_role(self) -> Optional[str]:
        return "AXWindow"

    def get_title(self) -> Optional[str]:
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXTitleAttribute,
                kAXErrorSuccess,
            )
            result = AXUIElementCopyAttributeValue(self._element, kAXTitleAttribute, None)
            if result and len(result) == 2:
                err, title = result
                if err == kAXErrorSuccess:
                    return title
        except Exception:
            pass
        return None

    def get_value(self) -> Optional[str]:
        return None

    def get_description(self) -> Optional[str]:
        return None

    def get_attribute(self, name: str) -> Optional[str]:
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXErrorSuccess,
            )
            result = AXUIElementCopyAttributeValue(self._element, name, None)
            if result and len(result) == 2:
                err, value = result
                if err == kAXErrorSuccess:
                    return str(value) if value else None
        except Exception:
            pass
        return None

    def get_bounds(self) -> Optional[tuple]:
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXSizeAttribute,
                kAXPositionAttribute,
                kAXErrorSuccess,
            )
            result = AXUIElementCopyAttributeValue(self._element, kAXSizeAttribute, None)
            if result and len(result) == 2:
                err, bounds = result
                if err == kAXErrorSuccess and bounds:
                    result2 = AXUIElementCopyAttributeValue(self._element, kAXPositionAttribute, None)
                    if result2 and len(result2) == 2:
                        err2, position = result2
                        if err2 == kAXErrorSuccess and position:
                            return (
                                float(position.x),
                                float(position.y),
                                float(bounds.width),
                                float(bounds.height),
                            )
        except Exception:
            pass
        return None

    def get_children(self) -> list:
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXChildrenAttribute,
                kAXErrorSuccess,
            )
            result = AXUIElementCopyAttributeValue(self._element, kAXChildrenAttribute, None)
            if result and len(result) == 2:
                err, children = result
                if err == kAXErrorSuccess and children:
                    return [_AXElementWrapper(child) for child in children]
        except Exception:
            pass
        return []


class _AXElementWrapper:
    """Wrapper for generic AXUIElement."""

    def __init__(self, element):
        self._element = element

    def get_role(self) -> Optional[str]:
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXRoleAttribute,
                kAXErrorSuccess,
            )
            result = AXUIElementCopyAttributeValue(self._element, kAXRoleAttribute, None)
            if result and len(result) == 2:
                err, role = result
                if err == kAXErrorSuccess:
                    return role
        except Exception:
            pass
        return None

    def get_title(self) -> Optional[str]:
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXTitleAttribute,
                kAXErrorSuccess,
            )
            result = AXUIElementCopyAttributeValue(self._element, kAXTitleAttribute, None)
            if result and len(result) == 2:
                err, title = result
                if err == kAXErrorSuccess:
                    return title
        except Exception:
            pass
        return None

    def get_value(self) -> Optional[str]:
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXValueAttribute,
                kAXErrorSuccess,
            )
            result = AXUIElementCopyAttributeValue(self._element, kAXValueAttribute, None)
            if result and len(result) == 2:
                err, value = result
                if err == kAXErrorSuccess:
                    return str(value) if value else None
        except Exception:
            pass
        return None

    def get_description(self) -> Optional[str]:
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXDescriptionAttribute,
                kAXErrorSuccess,
            )
            result = AXUIElementCopyAttributeValue(self._element, kAXDescriptionAttribute, None)
            if result and len(result) == 2:
                err, desc = result
                if err == kAXErrorSuccess:
                    return desc
        except Exception:
            pass
        return None

    def get_attribute(self, name: str) -> Optional[str]:
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXErrorSuccess,
            )
            result = AXUIElementCopyAttributeValue(self._element, name, None)
            if result and len(result) == 2:
                err, value = result
                if err == kAXErrorSuccess:
                    return str(value) if value else None
        except Exception:
            pass
        return None

    def get_bounds(self) -> Optional[tuple]:
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXSizeAttribute,
                kAXPositionAttribute,
                kAXErrorSuccess,
            )
            result = AXUIElementCopyAttributeValue(self._element, kAXSizeAttribute, None)
            if result and len(result) == 2:
                err, bounds = result
                if err == kAXErrorSuccess and bounds:
                    result2 = AXUIElementCopyAttributeValue(self._element, kAXPositionAttribute, None)
                    if result2 and len(result2) == 2:
                        err2, position = result2
                        if err2 == kAXErrorSuccess and position:
                            return (
                                float(position.x),
                                float(position.y),
                                float(bounds.width),
                                float(bounds.height),
                            )
        except Exception:
            pass
        return None

    def get_children(self) -> list:
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXChildrenAttribute,
                kAXErrorSuccess,
            )
            result = AXUIElementCopyAttributeValue(self._element, kAXChildrenAttribute, None)
            if result and len(result) == 2:
                err, children = result
                if err == kAXErrorSuccess and children:
                    return [_AXElementWrapper(child) for child in children]
        except Exception:
            pass
        return []


# =============================================================================
# Main Walker Function
# =============================================================================


def walk_focused_window(
    config: Optional[TreeWalkerConfig] = None,
    ax_provider: Optional[AXProvider] = None,
    expected_app_name: Optional[str] = None,
) -> Optional[TreeSnapshot]:
    """Walk the focused window's accessibility tree.

    This is the main entry point for accessibility collection. It performs
    a bounded depth-first walk of the focused window's accessibility tree,
    extracting text from text-bearing nodes.

    Args:
        config: Bounds configuration (defaults to TreeWalkerConfig())
        ax_provider: Optional AX provider for testing (defaults to RealAXProvider)
        expected_app_name: Optional app name to target (avoids race condition
            when user switches apps between trigger and walk)

    Returns:
        TreeSnapshot if successful, None if no focused window or walk failed
    """
    if config is None:
        config = TreeWalkerConfig()

    start_time = time.time()

    # Use real provider on macOS, or injected provider for testing
    if ax_provider is None:
        if not IS_MACOS:
            logger.debug("Accessibility walker only works on macOS")
            return None
        ax_provider = RealAXProvider()

    try:
        # Get the target application
        # Priority: use expected_app_name if provided to avoid race condition
        app = None
        if expected_app_name:
            app = ax_provider.get_app_by_name(expected_app_name)
            if app:
                logger.debug(
                    "Found target app '%s' by name (avoiding race condition)",
                    expected_app_name,
                )
            else:
                logger.debug(
                    "App '%s' not found by name, falling back to frontmost",
                    expected_app_name,
                )

        # Fall back to frontmost app if not found by name
        if not app:
            app = ax_provider.get_frontmost_app()

        if not app:
            logger.debug("No target application found")
            return None

        # Get the focused window
        window = ax_provider.get_focused_window(app)
        if not window:
            logger.debug("No focused window found")
            return None

        # Get app and window names
        app_name = app.get_name() if hasattr(app, "get_name") else ""
        window_name = window.get_title() if hasattr(window, "get_title") else ""

        # Get window bounds for normalization
        window_bounds = ax_provider.get_window_bounds(window)

        # Try to extract browser URL
        browser_url = extract_browser_url(window, app_name, window_name)

        # Initialize walk state
        state = WalkState(config)

        # Walk the window's children
        for child in window.get_children():
            if state.should_stop():
                break
            walk_element(child, depth=1, state=state, window_bounds=window_bounds)

        # Build text content
        text_content = "\n".join(state.text_buffer)

        # Compute hashes
        content_hash = hash(text_content) if text_content else 0
        try:
            from .policy import compute_simhash
            simhash = compute_simhash(text_content) if text_content else 0
        except Exception:
            simhash = 0

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Build snapshot
        from datetime import datetime, timezone

        return TreeSnapshot(
            app_name=app_name,
            window_name=window_name or "",
            browser_url=browser_url,
            text_content=text_content,
            nodes=state.nodes,
            node_count=len(state.nodes),
            truncated=state.truncated,
            truncation_reason=state.truncation_reason,
            max_depth_reached=state.max_depth_reached,
            content_hash=content_hash,
            simhash=simhash,
            captured_at=datetime.now(timezone.utc),
            duration_ms=duration_ms,
        )

    except Exception as e:
        logger.debug("Accessibility walk failed: %s", e)
        return None
