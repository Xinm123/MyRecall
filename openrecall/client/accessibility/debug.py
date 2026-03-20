"""Client-side accessibility debug helpers.

Phase 2 of Chat MVP implementation.

This module provides debug logging and dump utilities for accessibility
acquisition as specified in docs/v3/chat/mvp.md.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from .types import (
    AccessibilityDecision,
)


# =============================================================================
# Debug Mode Configuration
# =============================================================================

# Module-level debug mode state (disabled by default)
_debug_mode: bool = False


def is_debug_mode() -> bool:
    """Check if accessibility debug mode is enabled.

    Debug mode enables verbose logging and JSON dumps of accessibility
    decisions and snapshots.

    Returns:
        True if debug mode is enabled, False otherwise
    """
    global _debug_mode
    # Also check environment variable
    env_debug = os.environ.get("OPENRECALL_ACCESSIBILITY_DEBUG", "").lower()
    return _debug_mode or env_debug in ("1", "true", "yes")


def set_debug_mode(enabled: bool) -> None:
    """Enable or disable accessibility debug mode.

    Args:
        enabled: True to enable debug mode, False to disable
    """
    global _debug_mode
    _debug_mode = enabled


# =============================================================================
# Text Preview Helper
# =============================================================================


def make_text_preview(
    text: Optional[str],
    max_length: int = 50,
) -> Optional[str]:
    """Create a truncated preview of text content.

    Args:
        text: The text to preview (may be None)
        max_length: Maximum length before truncation (default: 50)

    Returns:
        Truncated text with "..." suffix if needed, or None/empty string
    """
    if text is None:
        return None
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


# =============================================================================
# Structured Log Formatter
# =============================================================================


def format_accessibility_log(
    capture_id: str,
    device_name: str,
    eligible: bool,
    adopted: bool,
    reason: str,
    app_name: str,
    window_name: str,
    duration_ms: int,
    node_count: int,
    truncated: bool,
    text_preview: Optional[str],
) -> dict[str, Any]:
    """Format an accessibility decision as a structured log.

    The log contains all MVP-required fields for debugging accessibility
    acquisition during capture.

    Args:
        capture_id: Unique identifier for this capture
        device_name: The device name where the frame was captured
        eligible: Whether accessibility was eligible
        adopted: Whether accessibility was adopted as canonical
        reason: Vocabulary reason for the decision
        app_name: Application name
        window_name: Window title
        duration_ms: Duration of the accessibility walk
        node_count: Number of nodes in the snapshot
        truncated: Whether the snapshot was truncated
        text_preview: Preview of text content (truncated)

    Returns:
        A dictionary suitable for structured logging
    """
    return {
        "capture_id": capture_id,
        "device_name": device_name,
        "eligible": eligible,
        "adopted": adopted,
        "reason": reason,
        "app_name": app_name,
        "window_name": window_name,
        "duration_ms": duration_ms,
        "node_count": node_count,
        "truncated": truncated,
        "text_preview": make_text_preview(text_preview) if text_preview else None,
    }


# =============================================================================
# Performance Log Formatter
# =============================================================================


def format_performance_log(
    trigger: str,
    target_device: str,
    app_name: str,
    eligible: bool,
    adopted: bool,
    reason: str,
    capture_ms: int,
    ax_walk_ms: int,
    spool_enqueue_ms: int,
    total_ms: int,
    node_count: int,
    truncated: bool,
) -> dict[str, Any]:
    """Format a per-capture performance log.

    This captures timing breakdown for the capture hot path, allowing
    analysis of where time is spent.

    Args:
        trigger: The capture trigger type
        target_device: The device name where the frame was captured
        app_name: Application name
        eligible: Whether accessibility was eligible
        adopted: Whether accessibility was adopted
        reason: Vocabulary reason for the decision
        capture_ms: Time spent on screenshot capture
        ax_walk_ms: Time spent on accessibility walk
        spool_enqueue_ms: Time spent on spool enqueue
        total_ms: Total capture time
        node_count: Number of nodes in the snapshot
        truncated: Whether the snapshot was truncated

    Returns:
        A dictionary suitable for performance logging
    """
    return {
        "trigger": trigger,
        "target_device": target_device,
        "app_name": app_name,
        "eligible": eligible,
        "adopted": adopted,
        "reason": reason,
        "capture_ms": capture_ms,
        "ax_walk_ms": ax_walk_ms,
        "spool_enqueue_ms": spool_enqueue_ms,
        "total_ms": total_ms,
        "node_count": node_count,
        "truncated": truncated,
    }


# =============================================================================
# Debug Dump Writer
# =============================================================================


def dump_accessibility_decision(
    decision: AccessibilityDecision,
    capture_id: str,
    dump_dir: str,
) -> Optional[str]:
    """Dump an accessibility decision to JSON and Markdown files.

    When accessibility debug mode is enabled, this creates detailed JSON
    dumps of accessibility decisions and snapshots for debugging, plus
    a human-readable Markdown summary.

    Args:
        decision: The accessibility decision to dump
        capture_id: Unique identifier for this capture
        dump_dir: Directory to write dump files

    Returns:
        Path to the JSON dump file, or None if dump failed
    """
    if not is_debug_mode():
        return None

    dump_path = Path(dump_dir) / f"accessibility_{capture_id}.json"
    dump_path.parent.mkdir(parents=True, exist_ok=True)

    content: dict[str, Any] = {
        "capture_id": capture_id,
        "decision": {
            "eligible": decision.eligible,
            "adopted": decision.adopted,
            "reason": decision.reason,
        },
        "snapshot": None,
    }

    if decision.snapshot is not None:
        snapshot = decision.snapshot
        content["snapshot"] = {
            "app_name": snapshot.app_name,
            "window_name": snapshot.window_name,
            "browser_url": snapshot.browser_url,
            "text_content": snapshot.text_content,
            "node_count": snapshot.node_count,
            "truncated": snapshot.truncated,
            "truncation_reason": snapshot.truncation_reason,
            "max_depth_reached": snapshot.max_depth_reached,
            "duration_ms": snapshot.duration_ms,
            "nodes": [
                {
                    "role": node.role,
                    "text": node.text,
                    "depth": node.depth,
                    "bounds": (
                        {
                            "left": node.bounds.left,
                            "top": node.bounds.top,
                            "width": node.bounds.width,
                            "height": node.bounds.height,
                        }
                        if node.bounds
                        else None
                    ),
                }
                for node in snapshot.nodes
            ],
        }

    try:
        with open(dump_path, "w") as f:
            json.dump(content, f, indent=2, default=str)

        # Also write Markdown summary
        md_path = dump_path.with_suffix(".md")
        _write_markdown_summary(decision, capture_id, md_path)

        return str(dump_path)
    except Exception:
        return None


def _write_markdown_summary(
    decision: AccessibilityDecision,
    capture_id: str,
    md_path: Path,
) -> None:
    """Write a human-readable Markdown summary of the accessibility decision.

    Args:
        decision: The accessibility decision
        capture_id: Unique identifier for this capture
        md_path: Path to write the Markdown file
    """
    lines = [
        f"# Accessibility Debug: {capture_id}",
        "",
        "## Decision",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| **Eligible** | {decision.eligible} |",
        f"| **Adopted** | {decision.adopted} |",
        f"| **Reason** | `{decision.reason}` |",
        f"| **App** | {decision.app_name or 'N/A'} |",
        f"| **Window** | {decision.window_name or 'N/A'} |",
        f"| **Duration** | {decision.duration_ms}ms |",
        "",
    ]

    if decision.snapshot is not None:
        snapshot = decision.snapshot
        lines.extend([
            "## Snapshot",
            "",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| **App Name** | {snapshot.app_name} |",
            f"| **Window Name** | {snapshot.window_name} |",
            f"| **Browser URL** | {snapshot.browser_url or 'N/A'} |",
            f"| **Node Count** | {snapshot.node_count} |",
            f"| **Max Depth** | {snapshot.max_depth_reached} |",
            f"| **Truncated** | {snapshot.truncated} |",
            f"| **Truncation Reason** | {snapshot.truncation_reason or 'N/A'} |",
            f"| **Duration** | {snapshot.duration_ms}ms |",
            "",
        ])

        # Text content section
        if snapshot.text_content:
            lines.extend([
                "## Text Content",
                "",
                "```",
                snapshot.text_content,
                "```",
                "",
            ])

        # Nodes table (first 50)
        if snapshot.nodes:
            lines.extend([
                "## Nodes",
                "",
                f"| # | Role | Text | Depth |",
                f"|---|------|------|-------|",
            ])
            for i, node in enumerate(snapshot.nodes[:50]):
                # Truncate text for table readability
                text = node.text[:60] + "..." if len(node.text) > 60 else node.text
                # Escape pipe characters
                text = text.replace("|", "\\|")
                lines.append(f"| {i + 1} | `{node.role}` | {text} | {node.depth} |")

            if len(snapshot.nodes) > 50:
                lines.append(f"| ... | *{len(snapshot.nodes) - 50} more nodes* | | |")
            lines.append("")
    else:
        lines.extend([
            "## Snapshot",
            "",
            "*No snapshot available*",
            "",
        ])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
