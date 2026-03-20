"""Client-side accessibility acquisition module.

Phase 2 of Chat MVP implementation.

This module provides accessibility acquisition for the client (Host) process.
Accessibility is captured at capture time and uploaded as part of frame metadata.
"""

from .types import (
    NodeBounds,
    AccessibilityTreeNode,
    TreeSnapshot,
    TreeWalkerConfig,
    AccessibilityDecision,
    AccessibilityPayload,
    # Reason vocabulary
    REASON_NON_FOCUSED_MONITOR,
    REASON_APP_PREFERS_OCR,
    REASON_NO_FOCUSED_WINDOW,
    REASON_WALK_FAILED,
    REASON_EMPTY_TEXT,
    REASON_ADOPTED_ACCESSIBILITY,
    # Text sources
    TEXT_SOURCE_ACCESSIBILITY,
    TEXT_SOURCE_OCR,
)

__all__ = [
    # Types
    "NodeBounds",
    "AccessibilityTreeNode",
    "TreeSnapshot",
    "TreeWalkerConfig",
    "AccessibilityDecision",
    "AccessibilityPayload",
    # Reason vocabulary
    "REASON_NON_FOCUSED_MONITOR",
    "REASON_APP_PREFERS_OCR",
    "REASON_NO_FOCUSED_WINDOW",
    "REASON_WALK_FAILED",
    "REASON_EMPTY_TEXT",
    "REASON_ADOPTED_ACCESSIBILITY",
    # Text sources
    "TEXT_SOURCE_ACCESSIBILITY",
    "TEXT_SOURCE_OCR",
]
