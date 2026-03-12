from __future__ import annotations

import pytest
from itertools import count

from openrecall.client.accessibility import macos as macos_module
from openrecall.client.accessibility.macos import AXNode, AXWalkResult, MacOSAXWalker
from openrecall.client.accessibility.service import (
    FocusedContextSnapshot,
    PairedCaptureService,
)
from openrecall.client.accessibility.types import BrowserURLResult


class _WalkerReturning:
    def __init__(self, result: AXWalkResult) -> None:
        self._result = result

    def walk(self, root: object | None) -> AXWalkResult:
        return self._result


class _WalkerRecordingRoot:
    def __init__(self) -> None:
        self.seen_root: object | None = None

    def walk(self, root: object | None) -> AXWalkResult:
        self.seen_root = root
        return AXWalkResult(
            accessibility_text="from-live-root",
            timed_out=False,
            visited_nodes=1,
            max_depth_reached=0,
        )


@pytest.mark.unit
def test_macos_ax_walker_enforces_walk_timeout_and_keeps_partial_text() -> None:
    root = AXNode(
        text="root",
        children=(
            AXNode(text="child-1"),
            AXNode(text="child-2"),
        ),
    )
    ticks = iter([0.00, 0.20, 0.40])
    walker = MacOSAXWalker(walk_timeout_ms=150, clock=lambda: next(ticks))

    result = walker.walk(root)

    assert result.timed_out is True
    assert result.accessibility_text == "root"


@pytest.mark.unit
def test_paired_capture_classifies_ax_timeout_partial() -> None:
    service = PairedCaptureService(
        walker=_WalkerReturning(
            AXWalkResult(
                accessibility_text="partial text",
                timed_out=True,
                visited_nodes=3,
                max_depth_reached=2,
            )
        ),
        browser_url_resolver=lambda _snapshot: BrowserURLResult(
            browser_url=None,
            classification="browser_url_skipped",
        ),
    )

    handoff = service.collect_raw_handoff(
        final_device_name="monitor_final",
        event_device_hint="monitor_hint",
        focused_context_snapshot=FocusedContextSnapshot(
            snapshot_id="snap-1",
            app_name="Google Chrome",
            window_name="Tab A",
        ),
        focused_context_snapshot_id_for_browser="snap-1",
        permission_blocked=False,
    )

    assert handoff.outcome == "ax_timeout_partial"
    assert handoff.accessibility_text == "partial text"
    assert handoff.content_hash is not None


@pytest.mark.unit
def test_paired_capture_distinguishes_ax_empty_from_permission_blocked() -> None:
    empty_service = PairedCaptureService(
        walker=_WalkerReturning(
            AXWalkResult(
                accessibility_text="",
                timed_out=False,
                visited_nodes=1,
                max_depth_reached=0,
            )
        )
    )
    empty_handoff = empty_service.collect_raw_handoff(
        final_device_name="monitor_final",
        event_device_hint="monitor_hint",
        focused_context_snapshot=FocusedContextSnapshot(
            snapshot_id="snap-1",
            app_name="Finder",
            window_name="Desktop",
        ),
        focused_context_snapshot_id_for_browser="snap-1",
        permission_blocked=False,
    )

    blocked_handoff = empty_service.collect_raw_handoff(
        final_device_name="monitor_final",
        event_device_hint="monitor_hint",
        focused_context_snapshot=FocusedContextSnapshot(
            snapshot_id="snap-1",
            app_name="Finder",
            window_name="Desktop",
        ),
        focused_context_snapshot_id_for_browser="snap-1",
        permission_blocked=True,
    )

    assert empty_handoff.outcome == "ax_empty"
    assert blocked_handoff.outcome == "permission_blocked"


@pytest.mark.unit
def test_macos_ax_walker_handles_live_root_and_recurses_children() -> None:
    class _LiveAXRoot:
        pass

    class _LiveAXChild:
        pass

    child = _LiveAXChild()
    root = _LiveAXRoot()

    values: dict[tuple[type[object], str], object] = {
        (_LiveAXRoot, "AXValue"): "Root Value",
        (_LiveAXRoot, "AXTitle"): "Root Title",
        (_LiveAXRoot, "AXDescription"): "Root Description",
        (_LiveAXRoot, "AXChildren"): [child],
        (_LiveAXChild, "AXValue"): "Child Value",
        (_LiveAXChild, "AXTitle"): None,
        (_LiveAXChild, "AXDescription"): None,
        (_LiveAXChild, "AXChildren"): [],
    }

    def _read_attribute(node: object, attribute: str) -> object:
        return values[(type(node), attribute)]

    walker = MacOSAXWalker(
        attribute_reader=_read_attribute,
        walk_timeout_ms=500,
        element_timeout_ms=200,
    )

    result = walker.walk(root)

    assert result.accessibility_text == (
        "Root Value\nRoot Title\nRoot Description\nChild Value"
    )
    assert result.visited_nodes == 2
    assert result.timed_out is False


@pytest.mark.unit
def test_macos_ax_walker_preserves_partial_text_on_element_timeout() -> None:
    class _LiveAXRoot:
        pass

    class _SlowChild:
        pass

    slow_child = _SlowChild()
    root = _LiveAXRoot()

    values: dict[tuple[type[object], str], object] = {
        (_LiveAXRoot, "AXValue"): "Root Value",
        (_LiveAXRoot, "AXTitle"): None,
        (_LiveAXRoot, "AXDescription"): None,
        (_LiveAXRoot, "AXChildren"): [slow_child],
        (_SlowChild, "AXValue"): "Slow Child Value",
        (_SlowChild, "AXTitle"): None,
        (_SlowChild, "AXDescription"): None,
        (_SlowChild, "AXChildren"): [],
    }

    ticks = count(start=0.00, step=0.01)

    def _read_attribute(node: object, attribute: str) -> object:
        if node is slow_child and attribute == "AXValue":
            raise TimeoutError("element timed out")
        return values[(type(node), attribute)]

    walker = MacOSAXWalker(
        attribute_reader=_read_attribute,
        clock=lambda: next(ticks),
        walk_timeout_ms=500,
        element_timeout_ms=150,
    )

    result = walker.walk(root)

    assert result.accessibility_text == "Root Value"
    assert result.visited_nodes == 2
    assert result.timed_out is False


@pytest.mark.unit
def test_paired_capture_passes_live_ax_root_to_walker() -> None:
    recording_walker = _WalkerRecordingRoot()
    service = PairedCaptureService(
        walker=recording_walker,
        browser_url_resolver=lambda _snapshot: BrowserURLResult(
            browser_url=None,
            classification="browser_url_skipped",
        ),
    )
    root = object()

    handoff = service.collect_raw_handoff(
        final_device_name="monitor_final",
        event_device_hint="monitor_hint",
        focused_context_snapshot=FocusedContextSnapshot(
            snapshot_id="snap-1",
            app_name="Finder",
            window_name="Desktop",
        ),
        focused_context_snapshot_id_for_browser="snap-1",
        permission_blocked=False,
        ax_root=root,
    )

    assert handoff.accessibility_text == "from-live-root"
    assert recording_walker.seen_root is root


@pytest.mark.unit
def test_timeout_error_stops_node_processing_and_keeps_prior_partial_text() -> None:
    class _Root:
        pass

    class _TimeoutNode:
        pass

    class _GrandChild:
        pass

    timeout_node = _TimeoutNode()
    grand_child = _GrandChild()
    root = _Root()

    values: dict[tuple[type[object], str], object] = {
        (_Root, "AXValue"): "Root",
        (_Root, "AXTitle"): None,
        (_Root, "AXDescription"): None,
        (_Root, "AXChildren"): [timeout_node],
        (_TimeoutNode, "AXTitle"): "Should not be read",
        (_TimeoutNode, "AXDescription"): None,
        (_TimeoutNode, "AXChildren"): [grand_child],
        (_GrandChild, "AXValue"): "Should not be read",
        (_GrandChild, "AXTitle"): None,
        (_GrandChild, "AXDescription"): None,
        (_GrandChild, "AXChildren"): [],
    }

    def _read_attribute(node: object, attribute: str) -> object:
        if node is timeout_node and attribute == "AXValue":
            raise TimeoutError("per-element timeout")
        return values[(type(node), attribute)]

    walker = MacOSAXWalker(
        attribute_reader=_read_attribute,
        walk_timeout_ms=500,
        element_timeout_ms=200,
    )

    result = walker.walk(root)

    assert result.accessibility_text == "Root"


@pytest.mark.unit
def test_service_uses_ax_root_provider_when_explicit_root_not_given() -> None:
    recording_walker = _WalkerRecordingRoot()
    provider_root = object()
    service = PairedCaptureService(
        walker=recording_walker,
        browser_url_resolver=lambda _snapshot: BrowserURLResult(
            browser_url=None,
            classification="browser_url_skipped",
        ),
        ax_root_provider=lambda _snapshot: provider_root,
    )

    service.collect_raw_handoff(
        final_device_name="monitor_final",
        event_device_hint="monitor_hint",
        focused_context_snapshot=FocusedContextSnapshot(
            snapshot_id="snap-1",
            app_name="Finder",
            window_name="Desktop",
        ),
        focused_context_snapshot_id_for_browser="snap-1",
        permission_blocked=False,
    )

    assert recording_walker.seen_root is provider_root


@pytest.mark.unit
def test_get_frontmost_ax_root_prefers_focused_element_then_window() -> None:
    class _Workspace:
        @staticmethod
        def sharedWorkspace() -> "_Workspace":
            return _Workspace()

        @staticmethod
        def frontmostApplication() -> object:
            class _App:
                @staticmethod
                def processIdentifier() -> int:
                    return 1234

            return _App()

    class _Quartz:
        @staticmethod
        def AXUIElementCreateApplication(_pid: int) -> object:
            return "app-element"

    class _AppKit:
        NSWorkspace = _Workspace

    attributes = {
        ("app-element", "AXFocusedUIElement"): "focused-ui",
        ("app-element", "AXFocusedWindow"): "focused-window",
        ("app-element", "AXMainWindow"): "main-window",
    }

    def _fake_import(name: str) -> object:
        if name == "Quartz":
            return _Quartz()
        if name == "AppKit":
            return _AppKit()
        raise ImportError(name)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        macos_module,
        "_ax_create_application_cache",
        macos_module._UNSET,
        raising=False,
    )
    monkeypatch.setattr(macos_module, "import_module", _fake_import)
    monkeypatch.setattr(
        macos_module,
        "_default_attribute_reader",
        lambda node, attr: attributes.get((node, attr)),
    )
    try:
        assert macos_module.get_frontmost_ax_root() == "focused-ui"
    finally:
        monkeypatch.undo()


@pytest.mark.unit
def test_get_frontmost_ax_root_uses_applicationservices_when_quartz_lacks_create_application() -> (
    None
):
    class _Workspace:
        @staticmethod
        def sharedWorkspace() -> "_Workspace":
            return _Workspace()

        @staticmethod
        def frontmostApplication() -> object:
            class _App:
                @staticmethod
                def processIdentifier() -> int:
                    return 4321

            return _App()

    class _Quartz:
        pass

    class _ApplicationServices:
        @staticmethod
        def AXUIElementCreateApplication(_pid: int) -> object:
            return "app-element"

    class _AppKit:
        NSWorkspace = _Workspace

    attributes = {
        ("app-element", "AXFocusedUIElement"): "focused-ui",
    }

    def _fake_import(name: str) -> object:
        if name == "Quartz":
            return _Quartz()
        if name == "ApplicationServices":
            return _ApplicationServices()
        if name == "HIServices":
            raise ImportError(name)
        if name == "AppKit":
            return _AppKit()
        raise ImportError(name)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        macos_module,
        "_ax_create_application_cache",
        macos_module._UNSET,
        raising=False,
    )
    monkeypatch.setattr(macos_module, "import_module", _fake_import)
    monkeypatch.setattr(
        macos_module,
        "_default_attribute_reader",
        lambda node, attr: attributes.get((node, attr)),
    )
    try:
        assert macos_module.get_frontmost_ax_root() == "focused-ui"
    finally:
        monkeypatch.undo()


@pytest.mark.unit
def test_default_attribute_reader_uses_applicationservices_when_quartz_lacks_copy() -> (
    None
):
    class _Quartz:
        pass

    class _ApplicationServices:
        @staticmethod
        def AXUIElementCopyAttributeValue(
            node: object,
            attribute: str,
            _unused: object,
        ) -> tuple[int, object]:
            assert node == "node"
            assert attribute == "AXValue"
            return 0, "copied-value"

    def _fake_import(name: str) -> object:
        if name == "Quartz":
            return _Quartz()
        if name == "ApplicationServices":
            return _ApplicationServices()
        if name == "HIServices":
            raise ImportError(name)
        raise ImportError(name)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        macos_module,
        "_ax_copy_attribute_value_cache",
        macos_module._UNSET,
        raising=False,
    )
    monkeypatch.setattr(macos_module, "import_module", _fake_import)
    try:
        assert (
            macos_module._default_attribute_reader("node", "AXValue") == "copied-value"
        )
    finally:
        monkeypatch.undo()


@pytest.mark.unit
def test_default_attribute_reader_caches_copy_symbol_resolution() -> None:
    class _ApplicationServices:
        @staticmethod
        def AXUIElementCopyAttributeValue(
            _node: object,
            _attribute: str,
            _unused: object,
        ) -> tuple[int, object]:
            return 0, "cached-value"

    import_calls = {"count": 0}

    def _fake_import(name: str) -> object:
        import_calls["count"] += 1
        if name == "ApplicationServices":
            return _ApplicationServices()
        raise ImportError(name)

    monkeypatch = pytest.MonkeyPatch()
    marker = object()
    monkeypatch.setattr(macos_module, "_UNSET", marker, raising=False)
    monkeypatch.setattr(
        macos_module, "_ax_copy_attribute_value_cache", marker, raising=False
    )
    monkeypatch.setattr(macos_module, "import_module", _fake_import)
    try:
        first = macos_module._default_attribute_reader("node", "AXValue")
        second = macos_module._default_attribute_reader("node", "AXTitle")
        assert first == "cached-value"
        assert second == "cached-value"
        assert import_calls["count"] == 1
    finally:
        monkeypatch.undo()


@pytest.mark.unit
def test_walker_stops_at_max_nodes_without_overcounting() -> None:
    root = AXNode(text="root", children=(AXNode(text="child"),))
    walker = MacOSAXWalker(max_nodes=1)

    result = walker.walk(root)

    assert result.accessibility_text == "root"
    assert result.visited_nodes == 1
