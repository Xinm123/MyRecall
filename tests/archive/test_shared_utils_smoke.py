import time


def test_human_readable_time_outputs_string():
    from openrecall.shared.utils import human_readable_time

    out = human_readable_time(int(time.time()) - 5)
    assert isinstance(out, str)
    assert out.endswith("ago")


def test_timestamp_to_human_readable_handles_invalid():
    from openrecall.shared.utils import timestamp_to_human_readable

    assert timestamp_to_human_readable("bad") == ""  # type: ignore[arg-type]


def test_osx_helpers_return_empty_when_unavailable(monkeypatch):
    import openrecall.shared.utils as u

    monkeypatch.setattr(u, "NSWorkspace", None)
    monkeypatch.setattr(u, "CGWindowListCopyWindowInfo", None)
    monkeypatch.setattr(u, "kCGNullWindowID", None)
    monkeypatch.setattr(u, "kCGWindowListOptionOnScreenOnly", None)
    assert u.get_active_app_name_osx() == ""
    assert u.get_active_window_title_osx() == ""

