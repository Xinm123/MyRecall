"""Tests for /api/vision/status and /api/v1/vision/status endpoints."""

import importlib
import time
import unittest.mock as mock

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
    monkeypatch.setenv("OPENRECALL_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENRECALL_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENRECALL_EMBEDDING_MODEL_NAME", "test-embed")
    monkeypatch.setenv("OPENRECALL_AI_API_KEY", "dummy")
    monkeypatch.setenv("OPENRECALL_AI_API_BASE", "http://localhost/v1")

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)

    import openrecall.server.database.sql
    importlib.reload(openrecall.server.database.sql)
    import openrecall.server.database
    importlib.reload(openrecall.server.database)
    openrecall.server.database.SQLStore()

    import openrecall.server.search.engine
    mock_se = mock.MagicMock()
    mock_se.search.return_value = []
    monkeypatch.setattr(openrecall.server.search.engine, "SearchEngine", lambda: mock_se)

    import openrecall.server.api
    importlib.reload(openrecall.server.api)
    import openrecall.server.api_v1
    importlib.reload(openrecall.server.api_v1)
    import openrecall.server.app
    importlib.reload(openrecall.server.app)

    app = openrecall.server.app.app
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_vision_status_ok_for_monitor_mode(client):
    from openrecall.server.config_runtime import runtime_settings

    with runtime_settings._lock:
        runtime_settings.capture_mode = "monitor_id"
        runtime_settings.sck_available = True
        runtime_settings.sck_last_error_code = ""
        runtime_settings.sck_last_error_at = 0.0
        runtime_settings.selected_monitors = ["1"]

    resp = client.get("/api/v1/vision/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["active_mode"] == "monitor_id"
    assert data["selected_monitors"] == ["1"]


def test_vision_status_permission_denied(client):
    from openrecall.server.config_runtime import runtime_settings

    with runtime_settings._lock:
        runtime_settings.capture_mode = "legacy"
        runtime_settings.sck_available = False
        runtime_settings.sck_last_error_code = "permission_denied"
        runtime_settings.sck_last_error_at = time.time()
        runtime_settings.selected_monitors = []

    resp = client.get("/api/vision/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "permission_denied"
    assert data["active_mode"] == "legacy"


def test_heartbeat_updates_capture_health_fields(client):
    from openrecall.server.config_runtime import runtime_settings

    resp = client.post(
        "/api/v1/heartbeat",
        json={
            "capture_mode": "legacy",
            "sck_available": False,
            "sck_last_error_code": "no_displays",
            "sck_last_error_at": 123.45,
            "selected_monitors": ["2"],
        },
    )
    assert resp.status_code == 200

    with runtime_settings._lock:
        assert runtime_settings.capture_mode == "legacy"
        assert runtime_settings.sck_available is False
        assert runtime_settings.sck_last_error_code == "no_displays"
        assert runtime_settings.sck_last_error_at == 123.45
        assert runtime_settings.selected_monitors == ["2"]
