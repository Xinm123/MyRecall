"""Frame metadata resolution: frame-level > chunk-level > null.

Phase 1.5: Replaces blind chunk-to-frame metadata copy with a priority-based
resolver that supports per-frame override when available.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedFrameMetadata:
    """Resolved metadata for a single frame insertion."""
    app_name: Optional[str]       # None = unknown
    window_name: Optional[str]    # None = unknown
    focused: Optional[bool]       # None = unknown, True/False when known
    browser_url: Optional[str]    # None = unknown
    source: str                   # "frame" | "chunk" | "none"


def resolve_frame_metadata(
    frame_meta: Optional[dict],
    chunk_meta: Optional[dict],
) -> ResolvedFrameMetadata:
    """Resolve metadata using frame-level > chunk-level > None priority.

    Args:
        frame_meta: Per-frame metadata dict (may be None or empty).
            Keys: app_name, window_name, focused, browser_url
        chunk_meta: Chunk-level metadata dict from video_chunks row.
            Keys: app_name, window_name, focused, browser_url

    Returns:
        ResolvedFrameMetadata with the highest-priority value for each field.
    """
    frame_meta = frame_meta or {}
    chunk_meta = chunk_meta or {}

    app_name = _resolve_string(
        frame_meta.get("app_name"),
        chunk_meta.get("app_name"),
    )
    window_name = _resolve_string(
        frame_meta.get("window_name"),
        chunk_meta.get("window_name"),
    )
    focused = _resolve_bool(
        frame_meta.get("focused"),
        chunk_meta.get("focused"),
    )
    browser_url = _resolve_string(
        frame_meta.get("browser_url"),
        chunk_meta.get("browser_url"),
    )

    # Determine source for traceability
    source = _determine_source(
        frame_meta, chunk_meta, app_name, window_name, focused, browser_url,
    )

    return ResolvedFrameMetadata(
        app_name=app_name,
        window_name=window_name,
        focused=focused,
        browser_url=browser_url,
        source=source,
    )


def _resolve_string(*candidates: Optional[str]) -> Optional[str]:
    """Return the first non-empty string, or None."""
    for val in candidates:
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def _resolve_bool(*candidates) -> Optional[bool]:
    """Convert first parseable candidate to bool | None. None means unknown."""
    for value in candidates:
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
    return None


def _determine_source(
    frame_meta: dict,
    chunk_meta: dict,
    resolved_app: Optional[str],
    resolved_window: Optional[str],
    resolved_focused: Optional[bool],
    resolved_browser_url: Optional[str],
) -> str:
    """Determine the primary source of the resolved metadata."""
    # Check if any value actually came from frame-level
    for key in ("app_name", "window_name", "focused", "browser_url"):
        val = frame_meta.get(key)
        if _has_non_missing_value(val):
            return "frame"

    # Check if any value came from chunk-level
    resolved_by_key = {
        "app_name": resolved_app,
        "window_name": resolved_window,
        "focused": resolved_focused,
        "browser_url": resolved_browser_url,
    }
    for key, resolved_val in resolved_by_key.items():
        if resolved_val is None:
            continue
        if _has_non_missing_value(chunk_meta.get(key)):
            return "chunk"

    return "none"


def _has_non_missing_value(value) -> bool:
    """True when the metadata value is present (not None/empty/whitespace)."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True
