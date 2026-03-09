import threading
from pathlib import Path
from typing import Any

import pytest

from openrecall.client.spool import SpoolItem, SpoolQueue
from openrecall.client.v3_uploader import SpoolUploader, UploadResult, upload_capture


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = ""

    def json(self):
        return self._payload


class _TrackingEvent(threading.Event):
    def __init__(self):
        super().__init__()
        self.wait_calls: list[float] = []

    def wait(self, timeout: float | None = None) -> bool:
        self.wait_calls.append(0.0 if timeout is None else float(timeout))
        return super().wait(timeout)


def _make_item(tmp_path: Path, capture_id: str = "capture-id") -> SpoolItem:
    jpg_path = tmp_path / f"{capture_id}.jpg"
    jpg_path.write_bytes(b"jpeg")
    return SpoolItem(capture_id=capture_id, jpg_path=jpg_path, metadata={})


@pytest.mark.unit
def test_upload_capture_503_returns_retry_hint_without_sleep(
    tmp_path: Path, monkeypatch
):
    item = _make_item(tmp_path, capture_id="c1")
    spool = SpoolQueue(storage_dir=tmp_path)
    commits: list[str] = []
    monkeypatch.setattr(spool, "commit", lambda capture_id: commits.append(capture_id))

    monkeypatch.setattr(
        "openrecall.client.v3_uploader.requests.post",
        lambda *args, **kwargs: _FakeResponse(503, {"retry_after": 7}),
    )

    def _should_not_sleep(_seconds: float) -> None:
        raise AssertionError("upload_capture should not sleep on 503")

    monkeypatch.setattr("openrecall.client.v3_uploader.time.sleep", _should_not_sleep)

    result = upload_capture(item, spool=spool)

    assert result.success is False
    assert result.retry_after == 7
    assert result.apply_backoff is False
    assert commits == []


@pytest.mark.unit
def test_spool_uploader_uses_single_wait_for_retry_after(tmp_path: Path, monkeypatch):
    item = _make_item(tmp_path, capture_id="c2")
    spool = SpoolQueue(storage_dir=tmp_path)
    monkeypatch.setattr(spool, "get_pending", lambda limit=1: [item])
    event = _TrackingEvent()
    uploader = SpoolUploader(spool=spool, stop_event=event)

    calls = {"n": 0}

    def _fake_upload_capture(_item, spool=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return UploadResult(success=False, retry_after=3, apply_backoff=False)
        event.set()
        return UploadResult(success=True, apply_backoff=False)

    monkeypatch.setattr(
        "openrecall.client.v3_uploader.upload_capture", _fake_upload_capture
    )

    uploader.run()

    assert calls["n"] == 2
    assert event.wait_calls == [3.0]
    assert uploader._retry_count == 0
