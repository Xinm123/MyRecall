from __future__ import annotations

import pytest

from openrecall.client.accessibility.macos import AXWalkResult
from openrecall.client.accessibility.service import (
    FocusedContextSnapshot,
    PairedCaptureService,
)
from openrecall.client.accessibility.browser_url import (
    BrowserURLCandidate,
    BrowserURLResolveContext,
    BrowserURLResolver,
    resolve_arc_applescript_candidate,
    resolve_ax_document_candidate,
    resolve_shallow_textfield_candidate,
)


def _resolve(
    resolver: BrowserURLResolver,
    *,
    app_name: str | None,
    focused_window_title: str | None,
    ax_root: object | None = None,
):
    return resolver.resolve(
        BrowserURLResolveContext(
            app_name=app_name,
            focused_window_title=focused_window_title,
            ax_root=ax_root,
        )
    )


@pytest.mark.unit
def test_browser_url_resolver_uses_first_valid_tier_for_required_browser() -> None:
    resolver = BrowserURLResolver(
        tier1_ax_document=lambda: BrowserURLCandidate(
            url="https://example.com/tier1", title="Tab A"
        ),
        tier2_arc_applescript=lambda: BrowserURLCandidate(
            url="https://example.com/tier2", title="Tab A"
        ),
        tier3_ax_textfield=lambda: BrowserURLCandidate(
            url="https://example.com/tier3", title="Tab A"
        ),
    )

    result = _resolve(
        resolver,
        app_name="Google Chrome",
        focused_window_title="Tab A",
    )

    assert result.classification == "browser_url_success"
    assert result.browser_url == "https://example.com/tier1"


@pytest.mark.unit
def test_browser_url_resolver_rejects_arc_stale_url_on_title_mismatch() -> None:
    resolver = BrowserURLResolver(
        tier1_ax_document=lambda: None,
        tier2_arc_applescript=lambda: BrowserURLCandidate(
            url="https://arc.example.com", title="Different Title"
        ),
        tier3_ax_textfield=lambda: None,
    )

    result = _resolve(
        resolver,
        app_name="Arc",
        focused_window_title="Current Tab",
    )

    assert result.classification == "browser_url_rejected_stale"
    assert result.browser_url is None


@pytest.mark.unit
def test_browser_url_resolver_accepts_arc_title_with_badge_count() -> None:
    resolver = BrowserURLResolver(
        tier1_ax_document=lambda: None,
        tier2_arc_applescript=lambda: BrowserURLCandidate(
            url="https://arc.example.com", title="(45) WhatsApp"
        ),
        tier3_ax_textfield=lambda: None,
    )

    result = _resolve(
        resolver,
        app_name="Arc",
        focused_window_title="WhatsApp",
    )

    assert result.classification == "browser_url_success"
    assert result.browser_url == "https://arc.example.com"


@pytest.mark.unit
def test_browser_url_resolver_accepts_arc_title_with_bracketed_badge_count() -> None:
    resolver = BrowserURLResolver(
        tier1_ax_document=lambda: None,
        tier2_arc_applescript=lambda: BrowserURLCandidate(
            url="https://arc.example.com", title="[2] Gmail"
        ),
        tier3_ax_textfield=lambda: None,
    )

    result = _resolve(
        resolver,
        app_name="Arc",
        focused_window_title="Gmail",
    )

    assert result.classification == "browser_url_success"
    assert result.browser_url == "https://arc.example.com"


@pytest.mark.unit
def test_browser_url_resolver_accepts_arc_title_case_insensitively() -> None:
    resolver = BrowserURLResolver(
        tier1_ax_document=lambda: None,
        tier2_arc_applescript=lambda: BrowserURLCandidate(
            url="https://arc.example.com", title="WhatsApp"
        ),
        tier3_ax_textfield=lambda: None,
    )

    result = _resolve(
        resolver,
        app_name="Arc",
        focused_window_title="whatsapp",
    )

    assert result.classification == "browser_url_success"
    assert result.browser_url == "https://arc.example.com"


@pytest.mark.unit
def test_browser_url_resolver_rejects_arc_truncated_title_with_case_only_contains_match() -> (
    None
):
    resolver = BrowserURLResolver(
        tier1_ax_document=lambda: None,
        tier2_arc_applescript=lambda: BrowserURLCandidate(
            url="https://arc.example.com",
            title="github - screenpipe/screenpipe: ai powered by what you see",
        ),
        tier3_ax_textfield=lambda: None,
    )

    result = _resolve(
        resolver,
        app_name="Arc",
        focused_window_title="GitHub - screenpipe/screenpipe: AI powered",
    )

    assert result.classification == "browser_url_rejected_stale"
    assert result.browser_url is None


@pytest.mark.unit
def test_browser_url_resolver_accepts_arc_truncated_title_contains_match() -> None:
    resolver = BrowserURLResolver(
        tier1_ax_document=lambda: None,
        tier2_arc_applescript=lambda: BrowserURLCandidate(
            url="https://arc.example.com",
            title="GitHub - screenpipe/screenpipe: AI powered by what you see",
        ),
        tier3_ax_textfield=lambda: None,
    )

    result = _resolve(
        resolver,
        app_name="Arc",
        focused_window_title="GitHub - screenpipe/screenpipe: AI powered",
    )

    assert result.classification == "browser_url_success"
    assert result.browser_url == "https://arc.example.com"


@pytest.mark.unit
def test_browser_url_resolver_accepts_arc_title_with_emoji_badge_prefix() -> None:
    resolver = BrowserURLResolver(
        tier1_ax_document=lambda: None,
        tier2_arc_applescript=lambda: BrowserURLCandidate(
            url="https://arc.example.com", title="💬1 - screenpipe | Discord"
        ),
        tier3_ax_textfield=lambda: None,
    )

    result = _resolve(
        resolver,
        app_name="Arc",
        focused_window_title="screenpipe | Discord",
    )

    assert result.classification == "browser_url_success"
    assert result.browser_url == "https://arc.example.com"


@pytest.mark.unit
def test_browser_url_resolver_rejects_arc_empty_title() -> None:
    resolver = BrowserURLResolver(
        tier1_ax_document=lambda: None,
        tier2_arc_applescript=lambda: BrowserURLCandidate(
            url="https://arc.example.com", title=""
        ),
        tier3_ax_textfield=lambda: None,
    )

    result = _resolve(
        resolver,
        app_name="Arc",
        focused_window_title="WhatsApp",
    )

    assert result.classification == "browser_url_rejected_stale"
    assert result.browser_url is None


@pytest.mark.unit
def test_browser_url_resolver_required_browser_failed_all_tiers() -> None:
    resolver = BrowserURLResolver(
        tier1_ax_document=lambda: None,
        tier2_arc_applescript=lambda: None,
        tier3_ax_textfield=lambda: None,
    )

    result = _resolve(
        resolver,
        app_name="Safari",
        focused_window_title="Tab A",
    )

    assert result.classification == "browser_url_failed_all_tiers"
    assert result.browser_url is None


@pytest.mark.unit
def test_browser_url_resolver_skips_non_browser_context() -> None:
    resolver = BrowserURLResolver()

    result = _resolve(
        resolver,
        app_name="Finder",
        focused_window_title="Desktop",
    )

    assert result.classification == "browser_url_skipped"
    assert result.browser_url is None


class _WalkerReturning:
    def walk(self, root: object | None) -> AXWalkResult:
        return AXWalkResult(
            accessibility_text="text",
            timed_out=False,
            visited_nodes=1,
            max_depth_reached=0,
        )


@pytest.mark.unit
def test_service_preserves_required_browser_url_classification() -> None:
    service = PairedCaptureService(
        walker=_WalkerReturning(),
        ax_root_provider=lambda _snapshot: None,
        ax_focused_context_provider=lambda _root: ("Safari", "Tab A"),
    )

    handoff = service.collect_raw_handoff(
        final_device_name="monitor_1",
        event_device_hint="monitor_1",
        focused_context_snapshot=FocusedContextSnapshot(
            snapshot_id="snapshot-1",
            app_name="Safari",
            window_name="Tab A",
        ),
        focused_context_snapshot_id_for_browser="snapshot-1",
        permission_blocked=False,
    )

    assert handoff.browser_url_classification == "browser_url_failed_all_tiers"
    assert handoff.focused_context.browser_url is None


@pytest.mark.unit
def test_live_tier1_reads_ax_document_from_ax_root() -> None:
    root = object()

    def _reader(node: object, attribute: str) -> object | None:
        assert node is root
        if attribute == "AXDocument":
            return "https://example.com/from-ax-document"
        return None

    candidate = resolve_ax_document_candidate(root, attribute_reader=_reader)

    assert candidate is not None
    assert candidate.url == "https://example.com/from-ax-document"


@pytest.mark.unit
def test_live_tier3_reads_url_from_shallow_ax_textfield_walk() -> None:
    root = object()
    child = object()

    def _reader(node: object, attribute: str) -> object | None:
        if attribute == "AXChildren" and node is root:
            return [child]
        if attribute == "AXRole" and node is child:
            return "AXTextField"
        if attribute == "AXValue" and node is child:
            return "https://example.com/from-address-bar"
        return None

    candidate = resolve_shallow_textfield_candidate(root, attribute_reader=_reader)

    assert candidate is not None
    assert candidate.url == "https://example.com/from-address-bar"


@pytest.mark.unit
def test_arc_applescript_candidate_parses_title_and_url() -> None:
    def _runner(_script: str) -> tuple[int, str, str]:
        return 0, "Active Arc Tab\nhttps://arc.example.com/page", ""

    candidate = resolve_arc_applescript_candidate(run_script=_runner)

    assert candidate is not None
    assert candidate.title == "Active Arc Tab"
    assert candidate.url == "https://arc.example.com/page"


@pytest.mark.unit
def test_arc_applescript_candidate_preserves_multiline_title() -> None:
    def _runner(_script: str) -> tuple[int, str, str]:
        return 0, "Sprint Plan\nLine Two\nhttps://arc.example.com/page", ""

    candidate = resolve_arc_applescript_candidate(run_script=_runner)

    assert candidate is not None
    assert candidate.title == "Sprint Plan\nLine Two"
    assert candidate.url == "https://arc.example.com/page"


@pytest.mark.unit
def test_service_passes_live_ax_root_to_browser_url_resolver_context() -> None:
    seen_context: BrowserURLResolveContext | None = None
    expected_root = object()

    def _resolver(context: BrowserURLResolveContext):
        nonlocal seen_context
        seen_context = context
        return BrowserURLResolver(
            tier1_ax_document=lambda _context: BrowserURLCandidate(
                url="https://example.com/live", title="Tab A"
            )
        ).resolve(context)

    service = PairedCaptureService(
        walker=_WalkerReturning(),
        browser_url_resolver=_resolver,
        ax_root_provider=lambda _snapshot: expected_root,
        ax_focused_context_provider=lambda _root: ("Safari", "Tab A"),
    )

    handoff = service.collect_raw_handoff(
        final_device_name="monitor_1",
        event_device_hint="monitor_1",
        focused_context_snapshot=FocusedContextSnapshot(
            snapshot_id="snapshot-1",
            app_name="Safari",
            window_name="Tab A",
        ),
        focused_context_snapshot_id_for_browser="snapshot-1",
        permission_blocked=False,
    )

    assert seen_context is not None
    assert seen_context.ax_root is expected_root
    assert handoff.focused_context.browser_url == "https://example.com/live"
    assert handoff.browser_url_classification == "browser_url_success"


@pytest.mark.unit
def test_service_marks_browser_url_stale_when_snapshot_mismatched() -> None:
    service = PairedCaptureService(
        walker=_WalkerReturning(),
        browser_url_resolver=lambda _context: BrowserURLResolver(
            tier1_ax_document=lambda _ctx: BrowserURLCandidate(
                url="https://example.com/stale", title="Tab A"
            )
        ).resolve(
            BrowserURLResolveContext(
                app_name="Safari",
                focused_window_title="Tab A",
                ax_root=None,
            )
        ),
    )

    handoff = service.collect_raw_handoff(
        final_device_name="monitor_1",
        event_device_hint="monitor_1",
        focused_context_snapshot=FocusedContextSnapshot(
            snapshot_id="snapshot-new",
            app_name="Safari",
            window_name="Tab A",
        ),
        focused_context_snapshot_id_for_browser="snapshot-old",
        permission_blocked=False,
    )

    assert handoff.focused_context.browser_url is None
    assert handoff.browser_url_classification == "browser_url_rejected_stale"
    assert handoff.outcome == "browser_url_rejected_stale"
