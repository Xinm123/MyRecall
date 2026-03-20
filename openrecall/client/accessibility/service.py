"""Client-side accessibility service layer.

Phase 3-4 of Chat MVP implementation.

This module provides the recorder-facing entrypoint for accessibility collection
as specified in docs/v3/chat/mvp.md.
"""

from __future__ import annotations

import logging
from typing import Optional

from .debug import dump_accessibility_decision, format_accessibility_log
from .policy import app_prefers_ocr, is_focused_monitor_eligible, make_accessibility_decision
from .types import (
    AccessibilityDecision,
    REASON_APP_PREFERS_OCR,
    REASON_NON_FOCUSED_MONITOR,
)

logger = logging.getLogger(__name__)


def collect_for_capture(
    app_name: Optional[str],
    window_name: Optional[str],
    target_device_name: str,
    focused_device_name: str,
    captured_at: str,
    debug_dir: Optional[str] = None,
) -> AccessibilityDecision:
    """Recorder-facing entrypoint for accessibility collection.

    Phase 4: Calls the macOS walker for eligible frames and makes adoption decisions.

    This function makes the accessibility eligibility and adoption decision
    for a single frame capture. It checks:
    1. Is this frame on the focused monitor?
    2. Is this a terminal-class app that prefers OCR?
    3. Walk the accessibility tree (Phase 4)

    Args:
        app_name: The active application name (may be None or empty)
        window_name: The active window title (may be None or empty)
        target_device_name: The device name where the frame is captured
        focused_device_name: The device name of the currently focused monitor
        captured_at: ISO timestamp when the capture was initiated
        debug_dir: Optional directory to write debug dumps

    Returns:
        AccessibilityDecision with eligibility, adoption status, and reason
    """
    # Normalize inputs
    app_name_str = app_name or ""
    window_name_str = window_name or ""

    # Check focused monitor eligibility
    if not is_focused_monitor_eligible(target_device_name, focused_device_name):
        decision = AccessibilityDecision(
            eligible=False,
            adopted=False,
            reason=REASON_NON_FOCUSED_MONITOR,
            snapshot=None,
            app_name=app_name_str,
            window_name=window_name_str,
            duration_ms=0,
        )
        _log_decision(decision, target_device_name, captured_at, debug_dir)
        return decision

    # Check terminal OCR preference
    if app_prefers_ocr(app_name_str):
        decision = AccessibilityDecision(
            eligible=False,
            adopted=False,
            reason=REASON_APP_PREFERS_OCR,
            snapshot=None,
            app_name=app_name_str,
            window_name=window_name_str,
            duration_ms=0,
        )
        _log_decision(decision, target_device_name, captured_at, debug_dir)
        return decision

    # Phase 4: Walk the accessibility tree
    walk_error = None
    snapshot = None

    try:
        from .macos import walk_focused_window
        from .types import TreeWalkerConfig

        # Pass app_name to walker to avoid race condition when user switches apps
        snapshot = walk_focused_window(
            TreeWalkerConfig(),
            expected_app_name=app_name_str,
        )
    except Exception as e:
        logger.debug("AX walk failed: %s", e)
        walk_error = e

    # Use make_accessibility_decision to map result
    decision = make_accessibility_decision(
        target_device_name=target_device_name,
        focused_device_name=focused_device_name,
        app_name=app_name_str,
        snapshot=snapshot,
        walk_error=walk_error,
    )

    _log_decision(decision, target_device_name, captured_at, debug_dir)
    return decision


def _log_decision(
    decision: AccessibilityDecision,
    device_name: str,
    capture_id: str,
    debug_dir: Optional[str],
) -> None:
    """Log and optionally dump the accessibility decision.

    Args:
        decision: The accessibility decision to log
        device_name: The target device name
        capture_id: Unique identifier for this capture (used as capture_id)
        debug_dir: Optional directory to write debug dumps
    """
    # Build structured log entry
    log_entry = format_accessibility_log(
        capture_id=capture_id,
        device_name=device_name,
        eligible=decision.eligible,
        adopted=decision.adopted,
        reason=decision.reason,
        app_name=decision.app_name,
        window_name=decision.window_name,
        duration_ms=decision.duration_ms,
        node_count=decision.snapshot.node_count if decision.snapshot else 0,
        truncated=decision.snapshot.truncated if decision.snapshot else False,
        text_preview=decision.snapshot.text_content if decision.snapshot else None,
    )

    logger.debug(
        "AX decision: eligible=%s adopted=%s reason=%s app=%s device=%s duration_ms=%d",
        decision.eligible,
        decision.adopted,
        decision.reason,
        decision.app_name,
        device_name,
        decision.duration_ms,
        extra=log_entry,
    )

    # Optionally dump to file
    if debug_dir:
        dump_accessibility_decision(
            decision=decision,
            capture_id=capture_id,
            dump_dir=debug_dir,
        )
