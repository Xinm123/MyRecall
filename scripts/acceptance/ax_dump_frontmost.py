#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from openrecall.client.accessibility.macos import (  # noqa: E402
    AXWalkResult,
    MacOSAXWalker,
    extract_focused_context_from_ax_root,
)


def _load_ax_create_application() -> Any | None:
    for module_name in ("ApplicationServices", "HIServices", "Quartz"):
        try:
            module: ModuleType = import_module(module_name)
        except Exception:
            continue
        candidate = getattr(module, "AXUIElementCreateApplication", None)
        if callable(candidate):
            return candidate
    return None


def _copy_attribute_value(node: object, attribute: str) -> object | None:
    for module_name in ("ApplicationServices", "HIServices", "Quartz"):
        try:
            module: ModuleType = import_module(module_name)
        except Exception:
            continue
        copy_attribute_value = getattr(module, "AXUIElementCopyAttributeValue", None)
        if not callable(copy_attribute_value):
            continue
        try:
            result = copy_attribute_value(node, attribute, None)
        except TypeError:
            try:
                result = copy_attribute_value(node, attribute)
            except Exception:
                return None
        except Exception:
            return None
        if isinstance(result, tuple) and len(result) >= 2:
            return result[1]
        return result
    return None


def get_frontmost_application() -> tuple[object | None, str | None, int | None]:
    try:
        appkit: ModuleType = import_module("AppKit")
    except Exception:
        return None, None, None

    workspace_class = getattr(appkit, "NSWorkspace", None)
    create_application = _load_ax_create_application()
    if workspace_class is None or not callable(create_application):
        return None, None, None

    try:
        app = workspace_class.sharedWorkspace().frontmostApplication()
        if app is None:
            return None, None, None
        pid = int(app.processIdentifier())
        name = str(app.localizedName() or "").strip() or None
        return create_application(pid), name, pid
    except Exception:
        return None, None, None


def get_focus_roots(app_element: object | None) -> tuple[object | None, object | None]:
    if app_element is None:
        return None, None
    focused_element = _copy_attribute_value(app_element, "AXFocusedUIElement")
    focused_window = _copy_attribute_value(app_element, "AXFocusedWindow")
    if focused_window is None:
        focused_window = _copy_attribute_value(app_element, "AXMainWindow")
    return focused_element, focused_window


def walk_root(root: object | None, *, walker: MacOSAXWalker) -> AXWalkResult:
    return walker.walk(root)


def _serialize_walk_result(
    result: AXWalkResult,
    *,
    available: bool,
) -> dict[str, object]:
    return {
        "available": available,
        "accessibility_text": result.accessibility_text,
        "timed_out": result.timed_out,
        "visited_nodes": result.visited_nodes,
        "max_depth_reached": result.max_depth_reached,
    }


def build_payload(
    *,
    app_name: str | None,
    window_name: str | None,
    focused_element_result: AXWalkResult,
    focused_window_result: AXWalkResult,
    focused_element_available: bool,
    focused_window_available: bool,
) -> dict[str, object]:
    primary_source = "none"
    primary_text = ""
    if focused_element_result.accessibility_text:
        primary_source = "focused_element"
        primary_text = focused_element_result.accessibility_text
    elif focused_window_result.accessibility_text:
        primary_source = "focused_window"
        primary_text = focused_window_result.accessibility_text

    return {
        "app_name": app_name,
        "window_name": window_name,
        "primary_source": primary_source,
        "primary_accessibility_text": primary_text,
        "focused_element": _serialize_walk_result(
            focused_element_result,
            available=focused_element_available,
        ),
        "focused_window": _serialize_walk_result(
            focused_window_result,
            available=focused_window_available,
        ),
    }


def collect_payload() -> dict[str, object]:
    app_element, app_name, pid = get_frontmost_application()
    if app_element is None:
        raise RuntimeError("frontmost application unavailable")

    focused_element_root, focused_window_root = get_focus_roots(app_element)
    walker = MacOSAXWalker()
    focused_element_result = walk_root(focused_element_root, walker=walker)
    focused_window_result = walk_root(focused_window_root, walker=walker)

    _, resolved_window_name = extract_focused_context_from_ax_root(focused_window_root)
    if resolved_window_name is None:
        _, resolved_window_name = extract_focused_context_from_ax_root(app_element)

    payload = build_payload(
        app_name=app_name,
        window_name=resolved_window_name,
        focused_element_result=focused_element_result,
        focused_window_result=focused_window_result,
        focused_element_available=focused_element_root is not None,
        focused_window_available=focused_window_root is not None,
    )
    payload.update(
        {
            "pid": pid,
            "focused_element_window_name": (
                extract_focused_context_from_ax_root(focused_element_root)[1]
                if focused_element_root is not None
                else None
            ),
        }
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dump macOS accessibility text for the current frontmost app, "
            "including both focused element and focused window results."
        )
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of pretty JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        payload = collect_payload()
    except Exception as exc:
        error_payload = {
            "error": "accessibility_capture_failed",
            "message": str(exc),
            "hint": (
                "Check macOS Accessibility permission for the current Python/app "
                "and ensure a normal frontmost app/window is available."
            ),
        }
        print(json.dumps(error_payload, ensure_ascii=False, indent=2))
        return 1

    if args.compact:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
