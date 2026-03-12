from __future__ import annotations

import logging
import time
from importlib import import_module
from dataclasses import dataclass, field
from types import ModuleType
from typing import Callable


logger = logging.getLogger(__name__)

AXAttributeReader = Callable[[object, str], object | None]

_UNSET = object()
_ax_copy_attribute_value_cache: object = _UNSET
_ax_create_application_cache: object = _UNSET


def _default_attribute_reader(node: object, attribute: str) -> object | None:
    copy_attribute_value = _load_ax_copy_attribute_value()
    if not callable(copy_attribute_value):
        return None

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


def _load_ax_copy_attribute_value() -> Callable[..., object] | None:
    global _ax_copy_attribute_value_cache
    if _ax_copy_attribute_value_cache is not _UNSET:
        if callable(_ax_copy_attribute_value_cache):
            return _ax_copy_attribute_value_cache
        return None

    for module_name in ("ApplicationServices", "HIServices", "Quartz"):
        try:
            module: ModuleType = import_module(module_name)
        except Exception:
            continue
        candidate = getattr(module, "AXUIElementCopyAttributeValue", None)
        if callable(candidate):
            _ax_copy_attribute_value_cache = candidate
            return candidate
    _ax_copy_attribute_value_cache = None
    return None


def get_frontmost_ax_root() -> object | None:
    try:
        appkit: ModuleType = import_module("AppKit")
    except Exception:
        return None

    workspace_class = getattr(appkit, "NSWorkspace", None)
    if workspace_class is None:
        return None

    create_application = _load_ax_create_application()
    if not callable(create_application):
        return None

    try:
        app = workspace_class.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        pid = int(app.processIdentifier())
        application_element = create_application(pid)
    except Exception:
        return None

    for attribute in ("AXFocusedUIElement", "AXFocusedWindow", "AXMainWindow"):
        value = _default_attribute_reader(application_element, attribute)
        if value is not None:
            return value

    return application_element


def _load_ax_create_application() -> Callable[[int], object] | None:
    global _ax_create_application_cache
    if _ax_create_application_cache is not _UNSET:
        if callable(_ax_create_application_cache):
            return _ax_create_application_cache
        return None

    for module_name in ("ApplicationServices", "HIServices", "Quartz"):
        try:
            module: ModuleType = import_module(module_name)
        except Exception:
            continue
        candidate = getattr(module, "AXUIElementCreateApplication", None)
        if callable(candidate):
            _ax_create_application_cache = candidate
            return candidate
    _ax_create_application_cache = None
    return None


def _frontmost_app_name() -> str | None:
    try:
        appkit: ModuleType = import_module("AppKit")
    except Exception:
        return None

    workspace_class = getattr(appkit, "NSWorkspace", None)
    if workspace_class is None:
        return None

    try:
        app = workspace_class.sharedWorkspace().frontmostApplication()
    except Exception:
        return None
    if app is None:
        return None

    for attribute in ("localizedName", "bundleIdentifier"):
        value = getattr(app, attribute, None)
        try:
            candidate = value() if callable(value) else value
        except Exception:
            continue
        if isinstance(candidate, str):
            text = candidate.strip()
            if text:
                return text
    return None


def extract_focused_context_from_ax_root(
    root: object | None,
    *,
    attribute_reader: AXAttributeReader | None = None,
) -> tuple[str | None, str | None]:
    if root is None:
        return None, None

    reader = attribute_reader or _default_attribute_reader
    window_name: str | None = None
    for attribute in ("AXTitle", "AXDescription"):
        value = reader(root, attribute)
        if isinstance(value, str):
            text = value.strip()
            if text:
                window_name = text
                break

    return _frontmost_app_name(), window_name


@dataclass(frozen=True)
class AXNode:
    text: str | None = None
    children: tuple["AXNode", ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AXWalkResult:
    accessibility_text: str
    timed_out: bool
    visited_nodes: int
    max_depth_reached: int


class MacOSAXWalker:
    def __init__(
        self,
        *,
        walk_timeout_ms: int = 500,
        element_timeout_ms: int = 200,
        max_nodes: int = 5000,
        max_depth: int = 30,
        clock: Callable[[], float] | None = None,
        attribute_reader: AXAttributeReader | None = None,
    ) -> None:
        self.walk_timeout_ms = walk_timeout_ms
        self.element_timeout_ms = element_timeout_ms
        self.max_nodes = max_nodes
        self.max_depth = max_depth
        self._clock = clock or time.monotonic
        self._attribute_reader = attribute_reader or _default_attribute_reader

    def walk(self, root: object | None) -> AXWalkResult:
        start = self._clock()
        if root is None:
            return AXWalkResult(
                accessibility_text="",
                timed_out=False,
                visited_nodes=0,
                max_depth_reached=0,
            )

        lines: list[str] = []
        stack: list[tuple[object, int]] = [(root, 0)]
        visited_nodes = 0
        max_depth_reached = 0
        timed_out = False

        while stack:
            node, depth = stack.pop()
            if depth > self.max_depth:
                continue

            if visited_nodes >= self.max_nodes:
                break
            visited_nodes += 1

            max_depth_reached = max(max_depth_reached, depth)

            node_started_at = self._clock()
            node_lines, children = self._extract_node_data(node, node_started_at)
            lines.extend(node_lines)

            for child in reversed(children):
                stack.append((child, depth + 1))

            now = self._clock()
            if (now - start) * 1000 >= self.walk_timeout_ms:
                timed_out = True
                break

        return AXWalkResult(
            accessibility_text="\n".join(lines),
            timed_out=timed_out,
            visited_nodes=visited_nodes,
            max_depth_reached=max_depth_reached,
        )

    def _extract_node_data(
        self,
        node: object,
        node_started_at: float,
    ) -> tuple[list[str], list[object]]:
        if isinstance(node, AXNode):
            lines: list[str] = []
            if node.text:
                text = node.text.strip()
                if text:
                    lines.append(text)
            return lines, list(node.children)

        lines: list[str] = []
        children: list[object] = []

        for attribute in ("AXValue", "AXTitle", "AXDescription"):
            if self._element_timed_out(node_started_at):
                return lines, children
            try:
                value = self._attribute_reader(node, attribute)
            except TimeoutError:
                return lines, children
            except Exception:
                logger.debug("Failed reading %s from AX node", attribute, exc_info=True)
                if self._element_timed_out(node_started_at):
                    return lines, children
                continue
            self._append_text(lines, value)

        if self._element_timed_out(node_started_at):
            return lines, children

        try:
            raw_children = self._attribute_reader(node, "AXChildren")
        except Exception:
            logger.debug("Failed reading AXChildren from AX node", exc_info=True)
            return lines, children

        if isinstance(raw_children, (list, tuple)):
            for child in raw_children:
                if child is not None:
                    children.append(child)

        return lines, children

    def _element_timed_out(self, started_at: float) -> bool:
        return (self._clock() - started_at) * 1000 >= self.element_timeout_ms

    @staticmethod
    def _append_text(lines: list[str], value: object | None) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text:
                lines.append(text)
