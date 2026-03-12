from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AXOutcome = Literal[
    "capture_completed",
    "ax_empty",
    "ax_timeout_partial",
    "browser_url_rejected_stale",
    "permission_blocked",
    "dedup_skipped",
    "spool_failed",
]


@dataclass(frozen=True)
class FocusedContext:
    app_name: str | None
    window_name: str | None
    browser_url: str | None


@dataclass(frozen=True)
class BrowserURLResult:
    browser_url: str | None
    classification: str


@dataclass(frozen=True)
class AccessibilityRawHandoff:
    accessibility_text: str
    content_hash: str | None
    focused_context: FocusedContext
    browser_url_classification: str
    event_device_hint: str | None
    final_device_name: str
    outcome: AXOutcome
