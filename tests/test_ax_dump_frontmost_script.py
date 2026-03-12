import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from openrecall.client.accessibility.macos import AXWalkResult


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "acceptance" / "ax_dump_frontmost.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("ax_dump_frontmost", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_ax_dump_frontmost_script_exists() -> None:
    assert SCRIPT_PATH.exists(), "scripts/acceptance/ax_dump_frontmost.py must exist"
    assert SCRIPT_PATH.is_file()


@pytest.mark.unit
def test_ax_dump_frontmost_script_help_returns_usage() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
    assert "ax_dump_frontmost.py" in result.stdout
    assert "focused element" in result.stdout.lower()
    assert "focused window" in result.stdout.lower()


@pytest.mark.unit
def test_build_payload_prefers_focused_element_text_as_primary() -> None:
    module = _load_script_module()

    payload = module.build_payload(
        app_name="Code",
        window_name="proposal.md — models",
        focused_element_result=AXWalkResult(
            accessibility_text="editor text",
            timed_out=False,
            visited_nodes=3,
            max_depth_reached=1,
        ),
        focused_window_result=AXWalkResult(
            accessibility_text="window text",
            timed_out=False,
            visited_nodes=12,
            max_depth_reached=4,
        ),
        focused_element_available=True,
        focused_window_available=True,
    )

    assert payload["app_name"] == "Code"
    assert payload["window_name"] == "proposal.md — models"
    assert payload["primary_source"] == "focused_element"
    assert payload["primary_accessibility_text"] == "editor text"
    assert payload["focused_element"]["available"] is True
    assert payload["focused_element"]["accessibility_text"] == "editor text"
    assert payload["focused_window"]["available"] is True
    assert payload["focused_window"]["accessibility_text"] == "window text"


@pytest.mark.unit
def test_build_payload_falls_back_to_focused_window_when_element_is_empty() -> None:
    module = _load_script_module()

    payload = module.build_payload(
        app_name="Antigravity",
        window_name="MyRecall — data-model.md",
        focused_element_result=AXWalkResult(
            accessibility_text="",
            timed_out=False,
            visited_nodes=1,
            max_depth_reached=0,
        ),
        focused_window_result=AXWalkResult(
            accessibility_text="terminal text",
            timed_out=False,
            visited_nodes=20,
            max_depth_reached=5,
        ),
        focused_element_available=True,
        focused_window_available=True,
    )

    assert payload["primary_source"] == "focused_window"
    assert payload["primary_accessibility_text"] == "terminal text"
