"""Tests for Legacy API 410 Gone and Keyword 404 — P1-S4 Sections 4 & 5.

Tests cover:
- Legacy /api/* endpoints return 410 Gone
- /v1/search/keyword returns 404 Not Found
- No DEPRECATED log messages

Per tasks.md §4, §5 and specs/legacy-api-removal/spec.md.
"""

import json
import uuid

import pytest
from flask import Flask

from openrecall.server.api import api_bp
from openrecall.server.api_v1 import v1_bp


@pytest.fixture
def app_with_legacy_routes():
    """Create a Flask app with both api and v1 blueprints."""
    app = Flask(__name__)
    app.register_blueprint(api_bp)
    app.register_blueprint(v1_bp)
    return app


class TestLegacyAPI410Gone:
    """Legacy /api/* endpoints return 410 Gone."""

    def test_post_api_upload_410(self, app_with_legacy_routes):
        """POST /api/upload returns 410 Gone."""
        client = app_with_legacy_routes.test_client()
        response = client.post("/api/upload")
        assert response.status_code == 410

        data = json.loads(response.data)
        assert data.get("error") == "This API endpoint has been removed"
        assert data.get("code") == "GONE"
        assert "request_id" in data
        # Verify request_id is valid UUID
        uuid.UUID(data["request_id"])

    def test_get_api_search_410(self, app_with_legacy_routes):
        """GET /api/search returns 410 Gone."""
        client = app_with_legacy_routes.test_client()
        response = client.get("/api/search")
        assert response.status_code == 410

        data = json.loads(response.data)
        assert data.get("error") == "This API endpoint has been removed"
        assert data.get("code") == "GONE"

    def test_get_api_queue_status_410(self, app_with_legacy_routes):
        """GET /api/queue/status returns 410 Gone."""
        client = app_with_legacy_routes.test_client()
        response = client.get("/api/queue/status")
        assert response.status_code == 410

        data = json.loads(response.data)
        assert data.get("error") == "This API endpoint has been removed"
        assert data.get("code") == "GONE"

    def test_get_api_health_410(self, app_with_legacy_routes):
        """GET /api/health returns 410 Gone."""
        client = app_with_legacy_routes.test_client()
        response = client.get("/api/health")
        assert response.status_code == 410

        data = json.loads(response.data)
        assert data.get("error") == "This API endpoint has been removed"
        assert data.get("code") == "GONE"

    def test_unified_error_format(self, app_with_legacy_routes):
        """All 410 responses have unified error format."""
        client = app_with_legacy_routes.test_client()

        for endpoint in ["/api/upload", "/api/search", "/api/queue/status", "/api/health"]:
            if endpoint == "/api/upload":
                response = client.post(endpoint)
            else:
                response = client.get(endpoint)

            data = json.loads(response.data)

            # Required fields
            assert "error" in data
            assert "code" in data
            assert "request_id" in data

            # Correct values
            assert data["code"] == "GONE"
            assert isinstance(data["request_id"], str)


class TestSearchKeyword404:
    """/v1/search/keyword returns 404 Not Found."""

    def test_search_keyword_404(self, app_with_legacy_routes):
        """GET /v1/search/keyword returns 404."""
        client = app_with_legacy_routes.test_client()
        response = client.get("/v1/search/keyword")
        assert response.status_code == 404

        data = json.loads(response.data)
        assert data.get("error") == "not found"
        assert data.get("code") == "NOT_FOUND"
        assert "request_id" in data

    def test_search_keyword_does_not_shadow_search(self, app_with_legacy_routes):
        """/v1/search still works (not shadowed by keyword route)."""
        client = app_with_legacy_routes.test_client()
        response = client.get("/v1/search?q=test")
        # Should return 200 (mocked search) or 500 if no DB, but NOT 404
        assert response.status_code != 404


class TestNoDeprecatedLogs:
    """No [DEPRECATED] log messages for 410 responses."""

    def test_no_deprecated_in_logs(self, app_with_legacy_routes, caplog):
        """No [DEPRECATED] messages in logs for legacy endpoints."""
        client = app_with_legacy_routes.test_client()

        with caplog.at_level("INFO"):
            client.get("/api/search")
            client.get("/api/health")
            client.get("/api/queue/status")
            client.post("/api/upload")

        # Check no [DEPRECATED] in log messages
        for record in caplog.records:
            assert "[DEPRECATED]" not in record.message
