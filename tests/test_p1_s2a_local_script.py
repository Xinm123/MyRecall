from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "acceptance" / "p1_s2a_local.sh"


@pytest.mark.unit
def test_p1_s2a_local_script_exists_and_is_executable() -> None:
    assert SCRIPT_PATH.exists(), "scripts/acceptance/p1_s2a_local.sh must exist"
    assert SCRIPT_PATH.is_file()
    assert SCRIPT_PATH.stat().st_mode & 0o111, "script must be executable"


@pytest.mark.unit
def test_p1_s2a_local_script_help_returns_usage() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "p1_s2a_local.sh" in result.stdout
