from __future__ import annotations

from dataclasses import dataclass
import inspect
import subprocess
from typing import Callable
from urllib.parse import urlparse

from openrecall.client.accessibility.macos import _default_attribute_reader
from openrecall.client.accessibility.types import BrowserURLResult

REQUIRED_BROWSERS = frozenset({"Google Chrome", "Safari", "Microsoft Edge"})
ARC_BROWSER_NAMES = frozenset({"Arc"})


@dataclass(frozen=True)
class BrowserURLCandidate:
    url: str
    title: str | None = None


@dataclass(frozen=True)
class BrowserURLResolveContext:
    app_name: str | None
    focused_window_title: str | None
    ax_root: object | None


def resolve_ax_document_candidate(
    ax_root: object | None,
    *,
    attribute_reader: Callable[[object, str], object | None] | None = None,
) -> BrowserURLCandidate | None:
    if ax_root is None:
        return None

    reader = attribute_reader or _default_attribute_reader
    value = reader(ax_root, "AXDocument")
    if not isinstance(value, str):
        return None
    url = value.strip()
    if not url:
        return None
    return BrowserURLCandidate(url=url)


def resolve_shallow_textfield_candidate(
    ax_root: object | None,
    *,
    attribute_reader: Callable[[object, str], object | None] | None = None,
    max_nodes: int = 30,
) -> BrowserURLCandidate | None:
    if ax_root is None:
        return None

    reader = attribute_reader or _default_attribute_reader
    queue: list[object] = [ax_root]
    visited = 0
    while queue and visited < max_nodes:
        node = queue.pop(0)
        visited += 1

        role = reader(node, "AXRole")
        value = reader(node, "AXValue")
        if role == "AXTextField" and isinstance(value, str):
            url = value.strip()
            if url:
                return BrowserURLCandidate(url=url)

        children = reader(node, "AXChildren")
        if isinstance(children, (list, tuple)):
            for child in children:
                if child is not None:
                    queue.append(child)

    return None


def _run_applescript(script: str) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=1.0,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def resolve_arc_applescript_candidate(
    *,
    run_script: Callable[[str], tuple[int, str, str]] | None = None,
) -> BrowserURLCandidate | None:
    runner = run_script or _run_applescript
    script = (
        'tell application "Arc"\n'
        "  set tabTitle to title of active tab of front window\n"
        "  set tabUrl to URL of active tab of front window\n"
        "  return tabTitle & linefeed & tabUrl\n"
        "end tell"
    )

    try:
        code, stdout, _stderr = runner(script)
    except Exception:
        return None
    if code != 0:
        return None

    normalized = stdout.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    title, separator, url = normalized.rpartition("\n")
    if not separator:
        return None
    title = title.strip()
    url = url.strip()
    if not title or not url:
        return None
    return BrowserURLCandidate(url=url, title=title)


class BrowserURLResolver:
    def __init__(
        self,
        *,
        tier1_ax_document: Callable[..., BrowserURLCandidate | None] | None = None,
        tier2_arc_applescript: Callable[..., BrowserURLCandidate | None] | None = None,
        tier3_ax_textfield: Callable[..., BrowserURLCandidate | None] | None = None,
    ) -> None:
        self._tier1_ax_document: Callable[..., BrowserURLCandidate | None]
        self._tier2_arc_applescript: Callable[..., BrowserURLCandidate | None]
        self._tier3_ax_textfield: Callable[..., BrowserURLCandidate | None]
        self._tier1_ax_document = tier1_ax_document or self._default_tier1
        self._tier2_arc_applescript = tier2_arc_applescript or self._default_tier2
        self._tier3_ax_textfield = tier3_ax_textfield or self._default_tier3

    def resolve(self, context: BrowserURLResolveContext) -> BrowserURLResult:
        app = context.app_name or ""
        is_required = app in REQUIRED_BROWSERS
        is_arc = app in ARC_BROWSER_NAMES
        if not is_required and not is_arc:
            return BrowserURLResult(
                browser_url=None, classification="browser_url_skipped"
            )

        saw_rejected_stale = False
        tiers: list[Callable[..., BrowserURLCandidate | None]]
        if is_arc:
            tiers = [
                self._tier1_ax_document,
                self._tier2_arc_applescript,
                self._tier3_ax_textfield,
            ]
        else:
            tiers = [
                self._tier1_ax_document,
                self._tier3_ax_textfield,
            ]

        for tier in tiers:
            candidate = self._call_tier(tier, context)
            if candidate is None:
                continue

            if not self._is_http_url(candidate.url):
                saw_rejected_stale = True
                continue

            if is_arc and not self._arc_title_matches(
                candidate_title=candidate.title,
                focused_window_title=context.focused_window_title,
            ):
                saw_rejected_stale = True
                continue

            return BrowserURLResult(
                browser_url=candidate.url,
                classification="browser_url_success",
            )

        if saw_rejected_stale:
            return BrowserURLResult(
                browser_url=None,
                classification="browser_url_rejected_stale",
            )
        if is_required:
            return BrowserURLResult(
                browser_url=None,
                classification="browser_url_failed_all_tiers",
            )
        return BrowserURLResult(browser_url=None, classification="browser_url_skipped")

    @staticmethod
    def _default_tier1(context: BrowserURLResolveContext) -> BrowserURLCandidate | None:
        return resolve_ax_document_candidate(context.ax_root)

    @staticmethod
    def _default_tier2(
        _context: BrowserURLResolveContext,
    ) -> BrowserURLCandidate | None:
        return resolve_arc_applescript_candidate()

    @staticmethod
    def _default_tier3(context: BrowserURLResolveContext) -> BrowserURLCandidate | None:
        return resolve_shallow_textfield_candidate(context.ax_root)

    @staticmethod
    def _call_tier(
        tier: Callable[..., BrowserURLCandidate | None],
        context: BrowserURLResolveContext,
    ) -> BrowserURLCandidate | None:
        try:
            signature = inspect.signature(tier)
        except (TypeError, ValueError):
            return tier()

        if len(signature.parameters) == 0:
            return tier()
        return tier(context)

    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _arc_title_matches(
        *,
        candidate_title: str | None,
        focused_window_title: str | None,
    ) -> bool:
        if candidate_title is None or focused_window_title is None:
            return False

        candidate = BrowserURLResolver._strip_title_badge(candidate_title)
        focused = BrowserURLResolver._strip_title_badge(focused_window_title)
        if not candidate or not focused:
            return False

        if candidate == focused:
            return True

        if candidate.lower() == focused.lower():
            return True

        if len(candidate) >= 4 and len(focused) >= 4:
            return candidate in focused or focused in candidate

        return False

    @staticmethod
    def _strip_title_badge(title: str) -> str:
        trimmed = title.strip()
        stripped = BrowserURLResolver._strip_bracketed_badge(trimmed, "(", ")")
        if stripped != trimmed:
            return stripped

        stripped = BrowserURLResolver._strip_bracketed_badge(trimmed, "[", "]")
        if stripped != trimmed:
            return stripped

        separator = " - "
        separator_index = trimmed.find(separator)
        if separator_index == -1:
            return trimmed

        prefix = trimmed[:separator_index]
        if (
            len(prefix) <= 5
            and not prefix.isascii()
            and any(char.isdigit() for char in prefix)
        ):
            return trimmed[separator_index + len(separator) :].lstrip()

        return trimmed

    @staticmethod
    def _strip_bracketed_badge(title: str, opening: str, closing: str) -> str:
        if not title.startswith(opening):
            return title

        remainder = title[len(opening) :]
        closing_index = remainder.find(closing)
        if closing_index == -1:
            return title

        inside = remainder[:closing_index]
        if not inside or not inside.isascii() or not inside.isdigit():
            return title

        after = remainder[closing_index + 1 :].lstrip()
        if not after:
            return title

        return after
