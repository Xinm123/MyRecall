from __future__ import annotations

import types

import pytest

import openrecall.shared.utils as utils


@pytest.mark.unit
def test_get_active_app_name_linux_logs_missing_subprocess_warning(
    monkeypatch, caplog
) -> None:
    monkeypatch.setattr(utils, "subprocess", None)

    with caplog.at_level("WARNING"):
        app_name = utils.get_active_app_name_linux()

    assert app_name == ""
    assert "subprocess" in caplog.text


@pytest.mark.unit
def test_get_active_window_title_osx_logs_unexpected_exception(
    monkeypatch, caplog
) -> None:
    workspace = types.SimpleNamespace(
        sharedWorkspace=lambda: types.SimpleNamespace(
            activeApplication=lambda: {"NSApplicationName": "Finder"}
        )
    )

    monkeypatch.setattr(utils, "NSWorkspace", workspace)
    monkeypatch.setattr(utils, "kCGWindowListOptionOnScreenOnly", 1)
    monkeypatch.setattr(utils, "kCGNullWindowID", 0)

    def _raise_window_error(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(utils, "CGWindowListCopyWindowInfo", _raise_window_error)

    with caplog.at_level("ERROR"):
        title = utils.get_active_window_title_osx()

    assert title == ""
    assert "Error getting macOS window title: boom" in caplog.text


@pytest.mark.unit
def test_is_user_active_linux_logs_missing_command_warning(monkeypatch, caplog) -> None:
    fake_subprocess = types.SimpleNamespace(
        check_output=lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
        CalledProcessError=RuntimeError,
        TimeoutExpired=TimeoutError,
    )
    monkeypatch.setattr(utils, "subprocess", fake_subprocess)

    with caplog.at_level("WARNING"):
        active = utils.is_user_active_linux()

    assert active is True
    assert "xprintidle" in caplog.text
