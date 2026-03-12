from __future__ import annotations

import pytest

from openrecall.client.accessibility.macos import AXWalkResult
from openrecall.client.accessibility.browser_url import BrowserURLResolveContext
from openrecall.client.accessibility.service import (
    FocusedContextSnapshot,
    PairedCaptureService,
)
from openrecall.client.accessibility.types import BrowserURLResult


class _WalkerReturning:
    def walk(self, root: object | None) -> AXWalkResult:
        return AXWalkResult(
            accessibility_text="focused text",
            timed_out=False,
            visited_nodes=1,
            max_depth_reached=0,
        )


@pytest.mark.unit
def test_focused_context_uses_one_shot_snapshot_and_preserves_unknowns() -> None:
    service = PairedCaptureService(
        walker=_WalkerReturning(),
        browser_url_resolver=lambda _snapshot: BrowserURLResult(
            browser_url="https://example.com",
            classification="browser_url_success",
        ),
        ax_focused_context_provider=lambda _root: ("Safari", None),
    )

    handoff = service.collect_raw_handoff(
        final_device_name="monitor_1",
        event_device_hint="monitor_1",
        focused_context_snapshot=FocusedContextSnapshot(
            snapshot_id="snapshot-a",
            app_name="Safari",
            window_name=None,
        ),
        focused_context_snapshot_id_for_browser="snapshot-a",
        permission_blocked=False,
    )

    assert handoff.focused_context.app_name == "Safari"
    assert handoff.focused_context.window_name is None
    assert handoff.focused_context.browser_url == "https://example.com"


@pytest.mark.unit
def test_focused_context_rejects_field_level_mixing_across_snapshots() -> None:
    service = PairedCaptureService(
        walker=_WalkerReturning(),
        browser_url_resolver=lambda _snapshot: BrowserURLResult(
            browser_url="https://stale.example.com",
            classification="browser_url_success",
        ),
        ax_focused_context_provider=lambda _root: ("Safari", "Current Tab"),
    )

    handoff = service.collect_raw_handoff(
        final_device_name="monitor_1",
        event_device_hint="monitor_1",
        focused_context_snapshot=FocusedContextSnapshot(
            snapshot_id="snapshot-a",
            app_name="Safari",
            window_name="Current Tab",
        ),
        focused_context_snapshot_id_for_browser="snapshot-b",
        permission_blocked=False,
    )

    assert handoff.focused_context.app_name == "Safari"
    assert handoff.focused_context.window_name == "Current Tab"
    assert handoff.focused_context.browser_url is None
    assert handoff.outcome == "browser_url_rejected_stale"


@pytest.mark.unit
def test_service_uses_ax_snapshot_title_for_browser_coherence() -> None:
    captured_contexts: list[BrowserURLResolveContext] = []

    service = PairedCaptureService(
        walker=_WalkerReturning(),
        browser_url_resolver=lambda context: (
            captured_contexts.append(context)
            or BrowserURLResult(
                browser_url="https://example.com",
                classification="browser_url_success",
            )
        ),
        ax_focused_context_provider=lambda _root: ("AX App", "AX Window"),
    )

    handoff = service.collect_raw_handoff(
        final_device_name="monitor_1",
        event_device_hint="monitor_1",
        focused_context_snapshot=FocusedContextSnapshot(
            snapshot_id="snapshot-a",
            app_name="Legacy App",
            window_name="Legacy Window",
        ),
        focused_context_snapshot_id_for_browser="snapshot-a",
        permission_blocked=False,
    )

    assert len(captured_contexts) == 1
    assert captured_contexts[0].app_name == "AX App"
    assert captured_contexts[0].focused_window_title == "AX Window"
    assert handoff.focused_context.app_name == "AX App"
    assert handoff.focused_context.window_name == "AX Window"
