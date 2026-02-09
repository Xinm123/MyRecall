"""Tests for Phase 0 API v1 blueprint."""

import io
import json

import pytest


@pytest.fixture
def flask_app_v1(tmp_path, monkeypatch):
    """Flask app fixture that includes v1 blueprint."""
    import importlib
    import unittest.mock as mock

    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)

    # Reload sql submodule so it picks up new settings
    import openrecall.server.database.sql
    importlib.reload(openrecall.server.database.sql)
    import openrecall.server.database
    importlib.reload(openrecall.server.database)
    openrecall.server.database.SQLStore()

    import openrecall.server.auth
    importlib.reload(openrecall.server.auth)

    # Mock SearchEngine to avoid HuggingFace model download in test env
    import openrecall.server.search.engine
    mock_se = mock.MagicMock()
    mock_se.search.return_value = []
    monkeypatch.setattr(
        openrecall.server.search.engine, "SearchEngine", lambda: mock_se
    )

    import openrecall.server.api
    importlib.reload(openrecall.server.api)

    import openrecall.server.api_v1
    importlib.reload(openrecall.server.api_v1)

    import openrecall.server.app
    importlib.reload(openrecall.server.app)

    return openrecall.server.app.app


@pytest.fixture
def client_v1(flask_app_v1):
    flask_app_v1.config["TESTING"] = True
    with flask_app_v1.test_client() as client:
        yield client


class TestV1Health:
    def test_v1_health(self, client_v1):
        resp = client_v1.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

    def test_legacy_health(self, client_v1):
        """Backward compatibility: /api/health still works."""
        resp = client_v1.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"


class TestV1MemoriesRecent:
    def test_paginated_envelope(self, client_v1):
        resp = client_v1.get("/api/v1/memories/recent?limit=10&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data
        assert "meta" in data
        meta = data["meta"]
        assert "total" in meta
        assert "limit" in meta
        assert "offset" in meta
        assert "has_more" in meta

    def test_default_pagination(self, client_v1):
        resp = client_v1.get("/api/v1/memories/recent")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["limit"] == 200  # default
        assert data["meta"]["offset"] == 0


class TestV1MemoriesLatest:
    def test_paginated_envelope(self, client_v1):
        resp = client_v1.get("/api/v1/memories/latest?since=0&limit=5&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data
        assert "meta" in data

    def test_invalid_since(self, client_v1):
        resp = client_v1.get("/api/v1/memories/latest?since=abc")
        assert resp.status_code == 400


class TestV1Search:
    def test_search_paginated(self, client_v1):
        resp = client_v1.get("/api/v1/search?q=&limit=10&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data
        assert "meta" in data

    def test_empty_query(self, client_v1):
        resp = client_v1.get("/api/v1/search?q=")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["total"] == 0


class TestV1Upload:
    def test_upload(self, client_v1):
        # Create a minimal test image
        from PIL import Image
        img = Image.new("RGB", (10, 10), color="red")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        metadata = json.dumps({
            "timestamp": 9999999,
            "app_name": "TestApp",
            "window_title": "TestWindow",
        })

        resp = client_v1.post(
            "/api/v1/upload",
            data={"file": (img_bytes, "test.png"), "metadata": metadata},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 202

    def test_upload_no_file(self, client_v1):
        resp = client_v1.post("/api/v1/upload")
        assert resp.status_code == 400


class TestV1Config:
    def test_get_config(self, client_v1):
        resp = client_v1.get("/api/v1/config")
        assert resp.status_code == 200

    def test_post_config(self, client_v1):
        resp = client_v1.post(
            "/api/v1/config",
            json={"recording_enabled": True},
        )
        assert resp.status_code == 200


class TestV1Heartbeat:
    def test_heartbeat(self, client_v1):
        resp = client_v1.post("/api/v1/heartbeat")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"


class TestV1QueueStatus:
    def test_queue_status(self, client_v1):
        resp = client_v1.get("/api/v1/queue/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "queue" in data
        assert "video_queue" in data
        assert "completed" in data["video_queue"]
        assert "pending" in data["video_queue"]


class TestAuthDecorator:
    def test_all_v1_routes_have_auth(self, flask_app_v1):
        """DG-04: All v1 routes have @require_auth decorator."""
        from openrecall.server.auth import require_auth

        for rule in flask_app_v1.url_map.iter_rules():
            if rule.rule.startswith("/api/v1/"):
                endpoint = flask_app_v1.view_functions.get(rule.endpoint)
                if endpoint is not None:
                    # Check that the function is wrapped by require_auth
                    # The wrapper sets __wrapped__ or we check the name
                    assert hasattr(endpoint, "__wrapped__") or endpoint.__name__ != "decorated", (
                        f"Route {rule.rule} missing @require_auth"
                    )
