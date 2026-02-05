"""Unit tests for M0 client heartbeat upgrade (Task 9)."""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestRecorderHeartbeatM0:
    """Tests for recorder _send_heartbeat M0 contract compliance."""

    @pytest.fixture
    def mock_buffer(self) -> MagicMock:
        """Create a mock buffer with count method."""
        buffer = MagicMock()
        buffer.count.return_value = 5
        return buffer

    @pytest.fixture
    def mock_consumer(self) -> MagicMock:
        """Create a mock consumer."""
        consumer = MagicMock()
        consumer.is_alive.return_value = False
        return consumer

    def test_recorder_send_heartbeat_sends_json_body(
        self,
        mock_buffer: MagicMock,
        mock_consumer: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Heartbeat request includes JSON body with M0 fields."""
        monkeypatch.setenv("OPENRECALL_API_URL", "http://localhost:8083/api")
        monkeypatch.setenv("OPENRECALL_DEVICE_ID", "test-device-01")
        monkeypatch.setenv("OPENRECALL_DEVICE_TOKEN", "test-token-123")

        import importlib
        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        import openrecall.client.uploader

        importlib.reload(openrecall.client.uploader)
        import openrecall.client.recorder

        importlib.reload(openrecall.client.recorder)

        from openrecall.client.recorder import ScreenRecorder

        captured_request: dict[str, Any] = {}

        def mock_post(url: str, **kwargs: Any) -> MagicMock:
            captured_request["url"] = url
            captured_request["kwargs"] = kwargs
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "status": "ok",
                "config": {"recording_enabled": True, "upload_enabled": True},
                "server_time_ms": int(time.time() * 1000),
                "drift_ms": {"estimate": 50, "exceeded": False, "threshold": 300000},
            }
            return response

        with patch("openrecall.client.recorder.requests.post", side_effect=mock_post):
            recorder = ScreenRecorder(buffer=mock_buffer, consumer=mock_consumer)
            recorder._send_heartbeat()

        assert "url" in captured_request
        assert captured_request["url"].endswith("/heartbeat")

        kwargs = captured_request["kwargs"]
        assert "json" in kwargs
        body = kwargs["json"]

        assert body["device_id"] == "test-device-01"
        assert "client_ts" in body
        assert body["client_ts"] > 0
        assert "client_tz" in body
        assert body["queue_depth"] == 5
        assert "capabilities" in body
        assert body["capabilities"]["client_version"] == "3.0.0"

    def test_recorder_send_heartbeat_includes_authorization_header(
        self,
        mock_buffer: MagicMock,
        mock_consumer: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Heartbeat includes Authorization header when device_token is set."""
        monkeypatch.setenv("OPENRECALL_API_URL", "http://localhost:8083/api")
        monkeypatch.setenv("OPENRECALL_DEVICE_TOKEN", "secret-token-xyz")

        import importlib
        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        import openrecall.client.uploader

        importlib.reload(openrecall.client.uploader)
        import openrecall.client.recorder

        importlib.reload(openrecall.client.recorder)

        from openrecall.client.recorder import ScreenRecorder

        captured_headers: dict[str, str] = {}

        def mock_post(url: str, **kwargs: Any) -> MagicMock:
            captured_headers.update(kwargs.get("headers", {}))
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"status": "ok", "config": {}}
            return response

        with patch("openrecall.client.recorder.requests.post", side_effect=mock_post):
            recorder = ScreenRecorder(buffer=mock_buffer, consumer=mock_consumer)
            recorder._send_heartbeat()

        assert "Authorization" in captured_headers
        assert captured_headers["Authorization"] == "Bearer secret-token-xyz"

    def test_recorder_send_heartbeat_no_auth_header_without_token(
        self,
        mock_buffer: MagicMock,
        mock_consumer: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Heartbeat omits Authorization header when device_token is not set."""
        monkeypatch.setenv("OPENRECALL_API_URL", "http://localhost:8083/api")
        monkeypatch.delenv("OPENRECALL_DEVICE_TOKEN", raising=False)

        import importlib
        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        import openrecall.client.uploader

        importlib.reload(openrecall.client.uploader)
        import openrecall.client.recorder

        importlib.reload(openrecall.client.recorder)

        from openrecall.client.recorder import ScreenRecorder

        captured_headers: dict[str, str] = {}

        def mock_post(url: str, **kwargs: Any) -> MagicMock:
            captured_headers.update(kwargs.get("headers", {}))
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"status": "ok", "config": {}}
            return response

        with patch("openrecall.client.recorder.requests.post", side_effect=mock_post):
            recorder = ScreenRecorder(buffer=mock_buffer, consumer=mock_consumer)
            recorder._send_heartbeat()

        assert "Authorization" not in captured_headers

    def test_recorder_send_heartbeat_includes_queue_depth_from_buffer(
        self, mock_consumer: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Heartbeat queue_depth reflects actual buffer count."""
        monkeypatch.setenv("OPENRECALL_API_URL", "http://localhost:8083/api")

        import importlib
        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        import openrecall.client.uploader

        importlib.reload(openrecall.client.uploader)
        import openrecall.client.recorder

        importlib.reload(openrecall.client.recorder)

        from openrecall.client.recorder import ScreenRecorder

        mock_buffer = MagicMock()
        mock_buffer.count.return_value = 42

        captured_body: dict[str, Any] = {}

        def mock_post(url: str, **kwargs: Any) -> MagicMock:
            captured_body.update(kwargs.get("json", {}))
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"status": "ok", "config": {}}
            return response

        with patch("openrecall.client.recorder.requests.post", side_effect=mock_post):
            recorder = ScreenRecorder(buffer=mock_buffer, consumer=mock_consumer)
            recorder._send_heartbeat()

        assert captured_body["queue_depth"] == 42

    def test_recorder_send_heartbeat_includes_last_error_when_present(
        self,
        mock_buffer: MagicMock,
        mock_consumer: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Heartbeat includes last_error when an error was recorded."""
        monkeypatch.setenv("OPENRECALL_API_URL", "http://localhost:8083/api")

        import importlib
        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        import openrecall.client.uploader

        importlib.reload(openrecall.client.uploader)
        import openrecall.client.recorder

        importlib.reload(openrecall.client.recorder)

        from openrecall.client.recorder import ScreenRecorder

        captured_body: dict[str, Any] = {}

        def mock_post(url: str, **kwargs: Any) -> MagicMock:
            captured_body.update(kwargs.get("json", {}))
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"status": "ok", "config": {}}
            return response

        with patch("openrecall.client.recorder.requests.post", side_effect=mock_post):
            recorder = ScreenRecorder(buffer=mock_buffer, consumer=mock_consumer)
            recorder._record_error("UPLOAD_TIMEOUT", "Connection timed out")
            recorder._send_heartbeat()

        assert captured_body["last_error"] is not None
        assert captured_body["last_error"]["code"] == "UPLOAD_TIMEOUT"
        assert captured_body["last_error"]["message"] == "Connection timed out"
        assert "at_ms" in captured_body["last_error"]

    def test_recorder_send_heartbeat_last_error_is_none_initially(
        self,
        mock_buffer: MagicMock,
        mock_consumer: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Heartbeat last_error is None when no error has been recorded."""
        monkeypatch.setenv("OPENRECALL_API_URL", "http://localhost:8083/api")

        import importlib
        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        import openrecall.client.uploader

        importlib.reload(openrecall.client.uploader)
        import openrecall.client.recorder

        importlib.reload(openrecall.client.recorder)

        from openrecall.client.recorder import ScreenRecorder

        captured_body: dict[str, Any] = {}

        def mock_post(url: str, **kwargs: Any) -> MagicMock:
            captured_body.update(kwargs.get("json", {}))
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"status": "ok", "config": {}}
            return response

        with patch("openrecall.client.recorder.requests.post", side_effect=mock_post):
            recorder = ScreenRecorder(buffer=mock_buffer, consumer=mock_consumer)
            recorder._send_heartbeat()

        assert captured_body["last_error"] is None

    def test_recorder_send_heartbeat_includes_capabilities(
        self,
        mock_buffer: MagicMock,
        mock_consumer: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Heartbeat includes client capabilities dict."""
        monkeypatch.setenv("OPENRECALL_API_URL", "http://localhost:8083/api")

        import importlib
        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        import openrecall.client.uploader

        importlib.reload(openrecall.client.uploader)
        import openrecall.client.recorder

        importlib.reload(openrecall.client.recorder)

        from openrecall.client.recorder import ScreenRecorder

        captured_body: dict[str, Any] = {}

        def mock_post(url: str, **kwargs: Any) -> MagicMock:
            captured_body.update(kwargs.get("json", {}))
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"status": "ok", "config": {}}
            return response

        with patch("openrecall.client.recorder.requests.post", side_effect=mock_post):
            recorder = ScreenRecorder(buffer=mock_buffer, consumer=mock_consumer)
            recorder._send_heartbeat()

        caps = captured_body["capabilities"]
        assert "client_version" in caps
        assert "platform" in caps
        assert "capture" in caps
        assert "upload" in caps
        assert caps["upload"]["formats"] == ["png"]
        assert caps["upload"]["hash"] == "sha256"

    def test_recorder_records_error_on_heartbeat_failure(
        self,
        mock_buffer: MagicMock,
        mock_consumer: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Heartbeat failure records an error for next heartbeat."""
        monkeypatch.setenv("OPENRECALL_API_URL", "http://localhost:8083/api")

        import importlib
        import openrecall.shared.config

        importlib.reload(openrecall.shared.config)
        import openrecall.client.uploader

        importlib.reload(openrecall.client.uploader)
        import openrecall.client.recorder

        importlib.reload(openrecall.client.recorder)

        from openrecall.client.recorder import ScreenRecorder
        import requests

        def mock_post_fail(url: str, **kwargs: Any) -> MagicMock:
            raise requests.RequestException("Connection refused")

        with patch(
            "openrecall.client.recorder.requests.post", side_effect=mock_post_fail
        ):
            recorder = ScreenRecorder(buffer=mock_buffer, consumer=mock_consumer)
            recorder._send_heartbeat()

        assert recorder._last_error is not None
        assert recorder._last_error["code"] == "HEARTBEAT_NETWORK_ERROR"
