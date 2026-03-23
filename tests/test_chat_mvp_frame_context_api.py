"""HTTP API tests for /v1/frames/{id}/context endpoint.

Phase 9 of Chat MVP implementation.
SSOT: docs/v3/chat/mvp.md
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from openrecall.server.api_v1 import v1_bp
from openrecall.server.database.frames_store import FramesStore


@pytest.fixture
def app_with_context_route():
    """Create a Flask app with the v1 blueprint registered."""
    app = Flask(__name__)
    app.register_blueprint(v1_bp)
    yield app


@pytest.fixture
def mock_store():
    """Create a mock FramesStore with test data."""
    mock = MagicMock(spec=FramesStore)
    return mock


def _seed_accessibility_context():
    """Return sample frame context for accessibility frame."""
    return {
        "frame_id": 1,
        "text": "Hello World",
        "text_source": "accessibility",
        "nodes": [
            {"role": "AXStaticText", "text": "Hello World", "depth": 0},
        ],
        "urls": [],
        "browser_url": "https://example.com",
    }


class TestFrameContextAPI:
    """Tests for GET /v1/frames/{id}/context."""

    def test_frame_context_returns_valid_response(self, app_with_context_route, mock_store):
        """Endpoint returns frame_id, text, nodes, urls, text_source."""
        mock_store.get_frame_context.return_value = _seed_accessibility_context()

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/1/context")

            assert response.status_code == 200
            body = json.loads(response.data)
            assert body["frame_id"] == 1
            assert "text" in body
            assert "nodes" in body
            assert "urls" in body
            assert body["text_source"] == "accessibility"

    def test_frame_context_returns_404_for_missing_frame(self, app_with_context_route, mock_store):
        """Endpoint returns 404 for non-existent frame."""
        mock_store.get_frame_context.return_value = None

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/99999/context")

            assert response.status_code == 404
            body = json.loads(response.data)
            assert body["code"] == "NOT_FOUND"

    def test_frame_context_supports_max_text_length(self, app_with_context_route, mock_store):
        """Endpoint respects max_text_length query parameter."""
        long_text = "A" * 1000
        mock_store.get_frame_context.return_value = {
            "frame_id": 1,
            "text": long_text[:100] + "...",
            "text_source": "accessibility",
            "nodes": [],
            "urls": [],
        }

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/1/context?max_text_length=100")

            assert response.status_code == 200
            body = json.loads(response.data)
            assert len(body["text"]) == 103  # 100 + "..."
            assert body["text"].endswith("...")

    def test_frame_context_supports_max_nodes(self, app_with_context_route, mock_store):
        """Endpoint respects max_nodes query parameter."""
        mock_store.get_frame_context.return_value = {
            "frame_id": 1,
            "text": "Test",
            "text_source": "accessibility",
            "nodes": [
                {"role": "AXStaticText", "text": f"Node {i}", "depth": 0}
                for i in range(5)
            ],
            "urls": [],
            "nodes_truncated": 10,
        }

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/1/context?max_nodes=5")

            assert response.status_code == 200
            body = json.loads(response.data)
            assert len(body["nodes"]) == 5
            assert "nodes_truncated" in body

    def test_frame_context_passes_params_to_store(self, app_with_context_route, mock_store):
        """Query parameters are passed to store method."""
        mock_store.get_frame_context.return_value = _seed_accessibility_context()

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/1/context?max_text_length=500&max_nodes=20")

            assert response.status_code == 200
            # Verify store was called with correct params
            mock_store.get_frame_context.assert_called_once_with(1, 500, 20)

    def test_frame_context_handles_invalid_max_text_length(self, app_with_context_route, mock_store):
        """Invalid max_text_length is ignored (treated as None)."""
        mock_store.get_frame_context.return_value = _seed_accessibility_context()

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/1/context?max_text_length=invalid")

            assert response.status_code == 200
            # Should be called with None for max_text_length
            mock_store.get_frame_context.assert_called_once_with(1, None, None)

    def test_frame_context_handles_invalid_max_nodes(self, app_with_context_route, mock_store):
        """Invalid max_nodes is ignored (treated as None)."""
        mock_store.get_frame_context.return_value = _seed_accessibility_context()

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/1/context?max_nodes=invalid")

            assert response.status_code == 200
            # Should be called with None for max_nodes
            mock_store.get_frame_context.assert_called_once_with(1, None, None)

    def test_frame_context_returns_ocr_fallback(self, app_with_context_route, mock_store):
        """Endpoint returns OCR data when accessibility unavailable."""
        mock_store.get_frame_context.return_value = {
            "frame_id": 3,
            "text": "OCR extracted text with https://ocr-url.com link",
            "text_source": "ocr",
            "nodes": [],
            "urls": ["https://ocr-url.com"],
            "browser_url": None,
        }

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/3/context")

            assert response.status_code == 200
            body = json.loads(response.data)
            assert body["text_source"] == "ocr"
            assert body["nodes"] == []
            assert "https://ocr-url.com" in body["urls"]

    def test_frame_context_includes_browser_url(self, app_with_context_route, mock_store):
        """Endpoint includes browser_url when available."""
        mock_store.get_frame_context.return_value = {
            "frame_id": 1,
            "text": "Page content",
            "text_source": "accessibility",
            "nodes": [],
            "urls": [],
            "browser_url": "https://example.com/page",
        }

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/1/context")

            assert response.status_code == 200
            body = json.loads(response.data)
            assert body["browser_url"] == "https://example.com/page"
