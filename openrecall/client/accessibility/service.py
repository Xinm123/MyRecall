from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from openrecall.client.accessibility import macos as accessibility_macos
from openrecall.client.accessibility.browser_url import (
    BrowserURLResolveContext,
    BrowserURLResolver,
)
from openrecall.client.accessibility.hash import compute_content_hash
from openrecall.client.accessibility.macos import (
    AXWalkResult,
    MacOSAXWalker,
    get_frontmost_ax_root,
)
from openrecall.client.accessibility.types import (
    AccessibilityRawHandoff,
    AXOutcome,
    BrowserURLResult,
    FocusedContext,
)


@dataclass(frozen=True)
class FocusedContextSnapshot:
    snapshot_id: str
    app_name: str | None
    window_name: str | None


class AXWalker(Protocol):
    def walk(self, root: object | None) -> AXWalkResult: ...


class PairedCaptureService:
    def __init__(
        self,
        *,
        walker: AXWalker | None = None,
        browser_url_resolver: Callable[[BrowserURLResolveContext], BrowserURLResult]
        | None = None,
        ax_root_provider: Callable[[FocusedContextSnapshot], object | None]
        | None = None,
        ax_focused_context_provider: (
            Callable[[object | None], tuple[str | None, str | None]] | None
        ) = None,
    ) -> None:
        self._walker: AXWalker
        self._browser_url_resolver: Callable[
            [BrowserURLResolveContext], BrowserURLResult
        ]
        self._default_browser_url_resolver: BrowserURLResolver | None = None
        self._ax_root_provider = ax_root_provider or (
            lambda _snapshot: get_frontmost_ax_root()
        )
        self._ax_focused_context_provider = (
            ax_focused_context_provider
            or accessibility_macos.extract_focused_context_from_ax_root
        )
        self._walker = walker or MacOSAXWalker()
        if browser_url_resolver is not None:
            self._browser_url_resolver = browser_url_resolver
        else:
            self._default_browser_url_resolver = BrowserURLResolver()
            self._browser_url_resolver = self._resolve_browser_url

    def collect_raw_handoff(
        self,
        *,
        final_device_name: str,
        event_device_hint: str | None,
        focused_context_snapshot: FocusedContextSnapshot,
        focused_context_snapshot_id_for_browser: str | None,
        permission_blocked: bool,
        ax_root: object | None = None,
    ) -> AccessibilityRawHandoff:
        if permission_blocked:
            focused_context = FocusedContext(
                app_name=None,
                window_name=None,
                browser_url=None,
            )
            return AccessibilityRawHandoff(
                accessibility_text="",
                content_hash=None,
                focused_context=focused_context,
                browser_url_classification="browser_url_skipped",
                event_device_hint=event_device_hint,
                final_device_name=final_device_name,
                outcome="permission_blocked",
            )

        walk_result, resolved_ax_root = self._walk_accessibility_tree(
            focused_context_snapshot=focused_context_snapshot,
            ax_root=ax_root,
        )
        ax_app_name, ax_window_name = self._ax_focused_context_provider(
            resolved_ax_root
        )
        if ax_app_name is None:
            ax_app_name = focused_context_snapshot.app_name
        if ax_window_name is None:
            ax_window_name = focused_context_snapshot.window_name
        ax_focused_context_snapshot = FocusedContextSnapshot(
            snapshot_id=focused_context_snapshot.snapshot_id,
            app_name=ax_app_name,
            window_name=ax_window_name,
        )
        browser_context = BrowserURLResolveContext(
            app_name=ax_focused_context_snapshot.app_name,
            focused_window_title=ax_focused_context_snapshot.window_name,
            ax_root=resolved_ax_root,
        )
        browser_result = self._browser_url_resolver(browser_context)
        focused_context, browser_rejected, browser_classification = (
            self._build_focused_context(
                focused_context_snapshot=ax_focused_context_snapshot,
                focused_context_snapshot_id_for_browser=focused_context_snapshot_id_for_browser,
                browser_result=browser_result,
            )
        )

        content_hash = compute_content_hash(walk_result.accessibility_text)
        outcome = self._classify_outcome(
            walk_result=walk_result,
            content_hash=content_hash,
            browser_rejected=browser_rejected,
        )

        return AccessibilityRawHandoff(
            accessibility_text=walk_result.accessibility_text,
            content_hash=content_hash,
            focused_context=focused_context,
            browser_url_classification=browser_classification,
            event_device_hint=event_device_hint,
            final_device_name=final_device_name,
            outcome=outcome,
        )

    def _walk_accessibility_tree(
        self,
        *,
        focused_context_snapshot: FocusedContextSnapshot,
        ax_root: object | None,
    ) -> tuple[AXWalkResult, object | None]:
        if ax_root is None:
            ax_root = self._ax_root_provider(focused_context_snapshot)
        return self._walker.walk(ax_root), ax_root

    def _resolve_browser_url(
        self,
        context: BrowserURLResolveContext,
    ) -> BrowserURLResult:
        assert self._default_browser_url_resolver is not None
        return self._default_browser_url_resolver.resolve(context)

    @staticmethod
    def _build_focused_context(
        *,
        focused_context_snapshot: FocusedContextSnapshot,
        focused_context_snapshot_id_for_browser: str | None,
        browser_result: BrowserURLResult,
    ) -> tuple[FocusedContext, bool, str]:
        browser_url: str | None = None
        browser_rejected = False
        classification = browser_result.classification

        if browser_result.browser_url is not None:
            if (
                focused_context_snapshot_id_for_browser
                == focused_context_snapshot.snapshot_id
            ):
                browser_url = browser_result.browser_url
            else:
                browser_rejected = True
                classification = "browser_url_rejected_stale"

        if browser_result.classification == "browser_url_rejected_stale":
            classification = "browser_url_rejected_stale"

        return (
            FocusedContext(
                app_name=focused_context_snapshot.app_name,
                window_name=focused_context_snapshot.window_name,
                browser_url=browser_url,
            ),
            browser_rejected
            or browser_result.classification == "browser_url_rejected_stale",
            classification,
        )

    @staticmethod
    def _classify_outcome(
        *,
        walk_result: AXWalkResult,
        content_hash: str | None,
        browser_rejected: bool,
    ) -> AXOutcome:
        if walk_result.timed_out and content_hash is not None:
            return "ax_timeout_partial"
        if content_hash is None:
            return "ax_empty"
        if browser_rejected:
            return "browser_url_rejected_stale"
        return "capture_completed"
