"""Tests for description API endpoints."""
import pytest


class TestDescriptionAPI:
    def test_description_queue_status_endpoint(self, flask_client, flask_app):
        """Test GET /v1/description/tasks/status returns queue stats."""
        # Enable description to ensure the endpoint works
        flask_app.config["TESTING"] = True
        response = flask_client.get("/v1/description/tasks/status")
        # Should return 200 with queue stats dict
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, dict)
        assert "pending" in data
        assert "completed" in data
        assert "processing" in data
        assert "failed" in data

    def test_description_backfill_endpoint(self, flask_client, flask_app):
        """Test POST /v1/admin/description/backfill returns backfill status."""
        flask_app.config["TESTING"] = True
        response = flask_client.post("/v1/admin/description/backfill")
        # Should return 202 with message and count
        assert response.status_code == 202
        data = response.get_json()
        assert "message" in data
        assert "estimated_count" in data
        assert "request_id" in data

    def test_trigger_description_not_found(self, flask_client, flask_app):
        """Test POST /v1/frames/<id>/description for non-existent frame."""
        flask_app.config["TESTING"] = True
        response = flask_client.post("/v1/frames/99999/description")
        assert response.status_code == 404
        data = response.get_json()
        assert data["code"] == "NOT_FOUND"

    def test_activity_summary_includes_descriptions(self, flask_client, flask_app):
        """Test GET /v1/activity-summary includes descriptions field."""
        flask_app.config["TESTING"] = True
        response = flask_client.get(
            "/v1/activity-summary?start_time=2026-01-01T00:00:00Z&end_time=2027-01-01T00:00:00Z"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "descriptions" in data
        assert isinstance(data["descriptions"], list)

    def test_frame_context_returns_new_description_format(self, flask_client, flask_app):
        """Test that /v1/frames/<id>/context returns tags instead of entities/intent."""
        flask_app.config["TESTING"] = True
        response = flask_client.get("/v1/frames/1/context")
        # Skip if frame doesn't exist (404) - we just verify the format when description exists
        if response.status_code == 404:
            pytest.skip("Frame 1 not found in test database")
        assert response.status_code == 200
        data = response.get_json()

        if data.get("description"):
            desc = data["description"]
            assert "narrative" in desc
            assert "summary" in desc
            assert "tags" in desc
            assert isinstance(desc["tags"], list)
            assert "entities" not in desc
            assert "intent" not in desc

    def test_activity_summary_returns_new_format(self, flask_client, flask_app):
        """Test that /v1/activity-summary returns tags instead of intent."""
        flask_app.config["TESTING"] = True
        response = flask_client.get(
            "/v1/activity-summary?start_time=2026-01-01T00:00:00Z&end_time=2027-01-01T00:00:00Z"
        )
        assert response.status_code == 200
        data = response.get_json()

        if data.get("descriptions"):
            for desc in data["descriptions"]:
                assert "summary" in desc
                assert "tags" in desc
                assert isinstance(desc["tags"], list)
                assert "intent" not in desc
