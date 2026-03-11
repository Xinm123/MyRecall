from __future__ import annotations

import numpy as np
import pytest
import requests

from openrecall.client.uploader import HTTPUploader


@pytest.mark.unit
def test_upload_screenshot_logs_http_failure(monkeypatch, caplog) -> None:
    uploader = HTTPUploader(api_url="http://127.0.0.1:8083/api", timeout=1)
    image = np.zeros((2, 2, 3), dtype=np.uint8)

    class _Response:
        status_code = 500
        text = "server error"

    def _fake_post(*args, **kwargs):
        return _Response()

    monkeypatch.setattr("openrecall.client.uploader.requests.post", _fake_post)

    with caplog.at_level("ERROR"):
        ok = uploader.upload_screenshot(
            image=image,
            timestamp=123,
            active_app="Finder",
            active_window="Desktop",
        )

    assert ok is False
    assert "Upload failed: 500 - server error" in caplog.text


@pytest.mark.unit
def test_upload_screenshot_logs_request_exception(monkeypatch, caplog) -> None:
    uploader = HTTPUploader(api_url="http://127.0.0.1:8083/api", timeout=1)
    image = np.zeros((2, 2, 3), dtype=np.uint8)

    def _fake_post(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr("openrecall.client.uploader.requests.post", _fake_post)

    with caplog.at_level("ERROR"):
        ok = uploader.upload_screenshot(
            image=image,
            timestamp=123,
            active_app="Finder",
            active_window="Desktop",
        )

    assert ok is False
    assert "Upload error: boom" in caplog.text
