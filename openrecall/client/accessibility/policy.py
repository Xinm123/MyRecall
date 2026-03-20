"""Client-side accessibility policy helpers.

Phase 2 of Chat MVP implementation.

This module provides policy helpers for accessibility eligibility and adoption
decisions as specified in docs/v3/chat/mvp.md.
"""

from __future__ import annotations

from typing import Optional

from .types import (
    TreeSnapshot,
    AccessibilityDecision,
    REASON_NON_FOCUSED_MONITOR,
    REASON_APP_PREFERS_OCR,
    REASON_NO_FOCUSED_WINDOW,
    REASON_EMPTY_TEXT,
    REASON_ADOPTED_ACCESSIBILITY,
)


# =============================================================================
# Terminal-Class OCR Preference
# =============================================================================

# Terminal-class apps that prefer OCR over accessibility (from MVP spec)
_TERMINAL_APP_NAMES: set[str] = {
    "wezterm",
    "iterm",
    "iterm2",
    "terminal",
    "alacritty",
    "kitty",
    "hyper",
    "warp",
    "ghostty",
}


def app_prefers_ocr(app_name: Optional[str]) -> bool:
    """Check if an app prefers OCR over accessibility.

    Terminal-class apps should use OCR instead of accessibility because
    their accessibility trees are often incomplete or malformed.

    Args:
        app_name: The application name to check

    Returns:
        True if the app prefers OCR, False otherwise
    """
    if not app_name:
        return False
    return app_name.lower() in _TERMINAL_APP_NAMES


# =============================================================================
# Focused Monitor Eligibility
# =============================================================================


def is_focused_monitor_eligible(
    target_device_name: str,
    focused_device_name: str,
) -> bool:
    """Check if a frame on the target device is eligible for accessibility.

    In multi-monitor mode, only the frame captured on the current focused
    monitor is AX-eligible. Non-focused monitor frames do not attempt
    accessibility acquisition.

    Args:
        target_device_name: The device name where the frame is captured
        focused_device_name: The device name of the currently focused monitor

    Returns:
        True if the frame is on the focused monitor, False otherwise
    """
    return target_device_name == focused_device_name


# =============================================================================
# Accessibility Adoption
# =============================================================================


def should_adopt_accessibility(text_content: Optional[str]) -> bool:
    """Determine if accessibility text should be adopted as canonical.

    For AX-eligible non-terminal focused-window captures, the accessibility
    snapshot may be adopted as canonical accessibility text if it has
    non-empty text_content.

    Args:
        text_content: The text content from the accessibility snapshot

    Returns:
        True if the accessibility should be adopted, False otherwise
    """
    if text_content is None:
        return False
    # Whitespace-only text should not be adopted
    return text_content.strip() != ""


# =============================================================================
# Browser Candidate Detection
# =============================================================================

# Browser candidate name substrings (from MVP spec)
_BROWSER_CANDIDATE_SUBSTRINGS: tuple[str, ...] = (
    "safari",
    "chrome",
)


def is_browser_candidate(app_name: Optional[str]) -> bool:
    """Check if an app is a browser candidate for URL extraction.

    The MVP uses a narrow browser-candidate rule: apps whose names contain
    'safari' or 'chrome' (case-insensitive).

    Args:
        app_name: The application name to check

    Returns:
        True if the app is a browser candidate, False otherwise
    """
    if not app_name:
        return False
    app_name_lower = app_name.lower()
    return any(substr in app_name_lower for substr in _BROWSER_CANDIDATE_SUBSTRINGS)


# =============================================================================
# Decision Mapping
# =============================================================================


def make_accessibility_decision(
    target_device_name: str,
    focused_device_name: str,
    app_name: str,
    snapshot: Optional[TreeSnapshot],
) -> AccessibilityDecision:
    """Make an accessibility eligibility and adoption decision.

    This maps policy and walker outcomes into a stable AccessibilityDecision
    following the MVP decision mapping:

    - non_focused_monitor: target_device != focused_device
    - app_prefers_ocr: terminal-class app
    - no_focused_window: walker returns None (no window found or walk failed)
    - empty_text: snapshot has empty text_content
    - adopted_accessibility: snapshot has non-empty text_content

    Args:
        target_device_name: The device name where the frame is captured
        focused_device_name: The device name of the currently focused monitor
        app_name: The application name
        snapshot: The accessibility snapshot from the walker (may be None)

    Returns:
        An AccessibilityDecision with eligibility, adoption, and reason
    """
    # Non-focused monitor: not eligible, not adopted
    if not is_focused_monitor_eligible(target_device_name, focused_device_name):
        return AccessibilityDecision(
            eligible=False,
            adopted=False,
            reason=REASON_NON_FOCUSED_MONITOR,
            snapshot=None,
            app_name=app_name,
            window_name="",
            duration_ms=0,
        )

    # Terminal app prefers OCR: not eligible, not adopted
    if app_prefers_ocr(app_name):
        return AccessibilityDecision(
            eligible=False,
            adopted=False,
            reason=REASON_APP_PREFERS_OCR,
            snapshot=None,
            app_name=app_name,
            window_name="",
            duration_ms=0,
        )

    # No snapshot: eligible but not adopted
    # This covers both "no focused window found" and "walk failed" cases
    # The walker returns None for both, logging the specific reason internally
    if snapshot is None:
        return AccessibilityDecision(
            eligible=True,
            adopted=False,
            reason=REASON_NO_FOCUSED_WINDOW,
            snapshot=None,
            app_name=app_name,
            window_name="",
            duration_ms=0,
        )

    # Empty text: eligible but not adopted, keep snapshot
    if not should_adopt_accessibility(snapshot.text_content):
        return AccessibilityDecision(
            eligible=True,
            adopted=False,
            reason=REASON_EMPTY_TEXT,
            snapshot=snapshot,
            app_name=app_name,
            window_name=snapshot.window_name,
            duration_ms=snapshot.duration_ms,
        )

    # Valid snapshot with text: adopted
    return AccessibilityDecision(
        eligible=True,
        adopted=True,
        reason=REASON_ADOPTED_ACCESSIBILITY,
        snapshot=snapshot,
        app_name=app_name,
        window_name=snapshot.window_name,
        duration_ms=snapshot.duration_ms,
    )


# =============================================================================
# Text Hashing
# =============================================================================


def compute_simhash(text: str) -> int:
    """Compute a simhash for near-duplicate detection.

    This is a simple simhash implementation using character n-grams.
    It produces a hash that can be used to detect near-duplicate text.

    Args:
        text: The text to hash

    Returns:
        A 64-bit simhash value
    """
    if not text:
        return 0

    # Use 3-character shingles
    shingles = []
    text = text.lower()
    for i in range(len(text) - 2):
        shingles.append(text[i : i + 3])

    if not shingles:
        return 0

    # Compute hash for each shingle
    import hashlib

    v = [0] * 64
    for shingle in shingles:
        h = int(hashlib.md5(shingle.encode()).hexdigest(), 16)
        for i in range(64):
            bit = (h >> i) & 1
            v[i] += 1 if bit else -1

    # Compute final hash
    result = 0
    for i in range(64):
        if v[i] > 0:
            result |= 1 << i

    return result
