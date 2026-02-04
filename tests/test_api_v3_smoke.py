"""Smoke tests for v3 API blueprint."""

import pytest


class TestV3Blueprint:
    """Basic smoke tests for v3 API endpoints."""

    def test_v3_frames_route_exists(self, flask_client):
        """GET /api/v3/frames should return 200 (or 400 for invalid params)."""
        resp = flask_client.get("/api/v3/frames?limit=1")
        assert resp.status_code in (200, 400), (
            f"Expected 200 or 400, got {resp.status_code}"
        )

    def test_v3_frames_returns_json_structure(self, flask_client):
        """GET /api/v3/frames should return proper JSON structure."""
        resp = flask_client.get("/api/v3/frames?limit=10")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "items" in data
        assert "next_before" in data
        assert isinstance(data["items"], list)
