"""Client-side accessibility types and contracts.

Phase 2 of Chat MVP implementation.

This module defines the data structures for accessibility acquisition
as specified in docs/v3/chat/mvp.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# =============================================================================
# Reason Vocabulary Constants
# =============================================================================

REASON_NON_FOCUSED_MONITOR = "non_focused_monitor"
REASON_APP_PREFERS_OCR = "app_prefers_ocr"
REASON_NO_FOCUSED_WINDOW = "no_focused_window"
REASON_WALK_FAILED = "walk_failed"
REASON_EMPTY_TEXT = "empty_text"
REASON_ADOPTED_ACCESSIBILITY = "adopted_accessibility"


# =============================================================================
# Text Source Constants
# =============================================================================

TEXT_SOURCE_ACCESSIBILITY = "accessibility"
TEXT_SOURCE_OCR = "ocr"


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class NodeBounds:
    """Normalized bounds for an accessibility node.

    Bounds are normalized relative to the focused window, expressed as
    fractions (0.0 to 1.0) of the window dimensions.

    Attributes:
        left: Left edge position (0.0-1.0)
        top: Top edge position (0.0-1.0)
        width: Width (0.0-1.0)
        height: Height (0.0-1.0)
    """

    left: float
    top: float
    width: float
    height: float


@dataclass
class AccessibilityTreeNode:
    """A single node in the accessibility tree.

    This represents a text-bearing node extracted from the focused window's
    accessibility tree. The snapshot stores a flat list of these nodes,
    not a full raw tree.

    Attributes:
        role: AX role name (e.g., "AXStaticText", "AXButton")
        text: Extracted text content
        depth: Depth in the tree (0-based from focused window root)
        bounds: Optional normalized bounds relative to focused window
    """

    role: str
    text: str
    depth: int
    bounds: Optional[NodeBounds] = None


@dataclass
class TreeWalkerConfig:
    """Configuration for bounded accessibility tree walks.

    Default values match the MVP spec bounds to keep Python-based
    acquisition viable.

    Attributes:
        max_depth: Maximum tree depth to traverse (default: 30)
        max_nodes: Maximum nodes to collect (default: 5000)
        max_text_length: Maximum total text content length (default: 50000)
        walk_timeout_ms: Whole-walk timeout budget in milliseconds (default: 250)
        element_timeout_ms: Per-element timeout target in milliseconds (default: 200)
    """

    max_depth: int = 30
    max_nodes: int = 5000
    max_text_length: int = 50000
    walk_timeout_ms: int = 250
    element_timeout_ms: int = 200


@dataclass
class TreeSnapshot:
    """A focused-window accessibility snapshot.

    This is the result of an accessibility walk, shaped like a screenpipe-style
    TreeSnapshot. It is the single source for all paired accessibility persistence.

    Attributes:
        app_name: Application name
        window_name: Window title
        browser_url: Browser URL if available (for browser candidates)
        text_content: Aggregated text content from all nodes
        nodes: Flat list of text-bearing nodes in depth-first order
        node_count: Number of nodes in the snapshot
        truncated: Whether the walk was truncated due to bounds
        truncation_reason: Reason for truncation if any
        max_depth_reached: Maximum depth reached during walk
        content_hash: Hash of text content for deduplication
        simhash: Similarity hash for near-duplicate detection
        captured_at: Timestamp when snapshot was captured
        duration_ms: Duration of the accessibility walk in milliseconds
    """

    app_name: str
    window_name: str
    browser_url: Optional[str]
    text_content: str
    nodes: list[AccessibilityTreeNode]
    node_count: int
    truncated: bool
    truncation_reason: Optional[str]
    max_depth_reached: int
    content_hash: int
    simhash: int
    captured_at: datetime
    duration_ms: int


@dataclass
class AccessibilityDecision:
    """The result of accessibility eligibility and adoption evaluation.

    This captures whether accessibility was eligible, whether it was adopted
    as the canonical text source, and why.

    Attributes:
        eligible: Whether accessibility was eligible for this frame
        adopted: Whether accessibility was adopted as canonical text
        reason: Vocabulary reason for the decision
        snapshot: The accessibility snapshot if one was produced
    """

    eligible: bool
    adopted: bool
    reason: str
    snapshot: Optional[TreeSnapshot] = None


@dataclass
class AccessibilityPayload:
    """The accessibility portion of an ingest upload payload.

    When a frame is accessibility-canonical, the client must upload this
    nested payload as part of the capture metadata.

    Attributes:
        text_content: Aggregated text content (must equal frames.text)
        tree_json: Serialized flat node list as JSON string
        node_count: Number of nodes in the tree
        truncated: Whether the tree was truncated
        truncation_reason: Reason for truncation if any
        max_depth_reached: Maximum depth reached during walk
        duration_ms: Duration of the accessibility walk in milliseconds
    """

    text_content: str
    tree_json: str
    node_count: int
    truncated: bool
    truncation_reason: Optional[str]
    max_depth_reached: int
    duration_ms: int
