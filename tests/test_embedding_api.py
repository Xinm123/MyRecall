"""Tests for embedding API endpoints."""
import pytest


class TestEmbeddingAPI:
    def test_embedding_queue_status_endpoint(self, flask_client, flask_app):
        """Test GET /v1/embedding/tasks/status returns queue stats."""
        flask_app.config["TESTING"] = True
        response = flask_client.get("/v1/embedding/tasks/status")
        # Should return 200 with queue stats dict
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, dict)
        assert "pending" in data
        assert "completed" in data
        assert "processing" in data
        assert "failed" in data

    def test_embedding_backfill_endpoint(self, flask_client, flask_app):
        """Test POST /v1/admin/embedding/backfill returns backfill status."""
        flask_app.config["TESTING"] = True
        response = flask_client.post("/v1/admin/embedding/backfill")
        # Should return 202 with message and count
        assert response.status_code == 202
        data = response.get_json()
        assert "message" in data
        assert "estimated_count" in data
        assert "request_id" in data

    def test_trigger_embedding_not_found(self, flask_client, flask_app):
        """Test POST /v1/frames/<id>/embedding for non-existent frame."""
        flask_app.config["TESTING"] = True
        response = flask_client.post("/v1/frames/99999/embedding")
        assert response.status_code == 404
        data = response.get_json()
        assert data["code"] == "NOT_FOUND"

    def test_similar_frames_no_embedding(self, flask_client, flask_app):
        """Test GET /v1/frames/<id>/similar for frame without embedding."""
        flask_app.config["TESTING"] = True
        try:
            response = flask_client.get("/v1/frames/99999/similar")
            # Should return 404 if frame/embedding not found
            assert response.status_code == 404
        except AttributeError as e:
            # Skip if settings.lancedb_path not properly configured in test environment
            if "lancedb_path" in str(e):
                pytest.skip("LanceDB path not configured in test environment")
            raise

    def test_search_with_mode_parameter(self, flask_client, flask_app):
        """Test GET /v1/search with mode parameter."""
        flask_app.config["TESTING"] = True

        # Test FTS mode (default)
        response = flask_client.get("/v1/search?q=test&mode=fts")
        assert response.status_code == 200
        data = response.get_json()
        assert "data" in data
        assert "pagination" in data

        # Test hybrid mode (skip if LanceDB not configured)
        try:
            response = flask_client.get("/v1/search?q=test&mode=hybrid")
            assert response.status_code == 200
            data = response.get_json()
            assert "data" in data
            assert "pagination" in data
        except AttributeError as e:
            if "lancedb_path" in str(e):
                pytest.skip("LanceDB path not configured in test environment")
            raise

        # Test vector mode (skip if LanceDB not configured)
        try:
            response = flask_client.get("/v1/search?q=test&mode=vector")
            assert response.status_code == 200
            data = response.get_json()
            assert "data" in data
            assert "pagination" in data
        except AttributeError as e:
            if "lancedb_path" in str(e):
                pytest.skip("LanceDB path not configured in test environment")
            raise
