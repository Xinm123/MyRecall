import json
import shutil
from pathlib import Path

import pytest

from openrecall.client.chat.pi_manager import (
    PI_INSTALL_DIR,  # noqa: F401
    PiInstallError,
    ensure_installed,  # noqa: F401
    find_bun_executable,
    find_pi_executable,  # noqa: F401
    is_version_current,  # noqa: F401
)


@pytest.mark.unit
def test_find_bun_executable_returns_path():
    """find_bun_executable returns a valid path when bun is installed."""
    result = find_bun_executable()
    if result is not None:
        assert shutil.which(result) is not None


@pytest.mark.unit
def test_find_bun_executable_returns_none_when_missing(monkeypatch):
    """find_bun_executable returns None when bun is not installed."""
    monkeypatch.setattr(shutil, "which", lambda _: None)
    # Also patch Path.exists checks for common paths
    monkeypatch.setattr(Path, "exists", lambda self, *args, **kwargs: False)
    result = find_bun_executable()
    assert result is None


@pytest.mark.unit
def test_find_pi_executable_returns_path_after_install(tmp_path, monkeypatch):
    """find_pi_executable returns cli.js path after installation."""
    import openrecall.client.chat.pi_manager as pm

    monkeypatch.setattr(pm, "PI_INSTALL_DIR", tmp_path)
    cli = (
        tmp_path
        / "node_modules"
        / "@mariozechner"
        / "pi-coding-agent"
        / "dist"
        / "cli.js"
    )
    cli.parent.mkdir(parents=True)
    cli.write_text("")
    result = pm.find_pi_executable()
    assert result == str(cli)


@pytest.mark.unit
def test_find_pi_executable_returns_none_when_not_installed(tmp_path, monkeypatch):
    """find_pi_executable returns None when Pi is not installed."""
    import openrecall.client.chat.pi_manager as pm

    monkeypatch.setattr(pm, "PI_INSTALL_DIR", tmp_path / "nonexistent")
    result = pm.find_pi_executable()
    assert result is None


@pytest.mark.unit
def test_is_version_current_false_when_not_installed(tmp_path, monkeypatch):
    """is_version_current returns False when Pi is not installed."""
    import openrecall.client.chat.pi_manager as pm

    monkeypatch.setattr(pm, "PI_INSTALL_DIR", tmp_path / "nonexistent")
    assert pm.is_version_current() is False


@pytest.mark.unit
def test_is_version_current_true_when_matching(tmp_path, monkeypatch):
    """is_version_current returns True when version matches."""
    import openrecall.client.chat.pi_manager as pm

    monkeypatch.setattr(pm, "PI_INSTALL_DIR", tmp_path)
    pkg = tmp_path / "package.json"
    pkg.write_text(
        json.dumps({"dependencies": {"@mariozechner/pi-coding-agent": "0.60.0"}})
    )
    assert pm.is_version_current() is True


@pytest.mark.unit
def test_is_version_current_false_when_version_mismatch(tmp_path, monkeypatch):
    """is_version_current returns False when version does not match."""
    import openrecall.client.chat.pi_manager as pm

    monkeypatch.setattr(pm, "PI_INSTALL_DIR", tmp_path)
    pkg = tmp_path / "package.json"
    pkg.write_text(
        json.dumps({"dependencies": {"@mariozechner/pi-coding-agent": "0.59.0"}})
    )
    assert pm.is_version_current() is False


@pytest.mark.unit
def test_is_version_current_false_when_missing_dep(tmp_path, monkeypatch):
    """is_version_current returns False when dependency is missing."""
    import openrecall.client.chat.pi_manager as pm

    monkeypatch.setattr(pm, "PI_INSTALL_DIR", tmp_path)
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"dependencies": {}}))
    assert pm.is_version_current() is False


@pytest.mark.unit
def test_ensure_installed_raises_when_bun_missing(monkeypatch):
    """ensure_installed raises PiInstallError when bun is not found."""
    import openrecall.client.chat.pi_manager as pm

    monkeypatch.setattr(pm, "find_bun_executable", lambda: None)
    with pytest.raises(PiInstallError) as exc_info:
        pm.ensure_installed()
    assert "bun not found" in str(exc_info.value)
