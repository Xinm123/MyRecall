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
    mock = MagicMock()
    # Configure _connect to return a context manager with a mock connection
    mock_conn = MagicMock()
    # Return None from execute().fetchone() so description_status stays None
    mock_conn.execute.return_value.fetchone.return_value = None
    mock.__enter__ = MagicMock(return_value=mock_conn)
    mock.__exit__ = MagicMock(return_value=None)
    mock._connect.return_value = mock
    # Configure description-related methods
    mock.get_frame_description.return_value = None
    return mock


class TestFrameContextAPI:
    """Tests for GET /v1/frames/{id}/context."""

    def test_frame_context_returns_valid_response(self, app_with_context_route, mock_store):
        """Endpoint returns frame_id, description, text, urls, text_source."""
        mock_store.get_frame_context.return_value = {
            "frame_id": 1,
            "timestamp": "2026-03-26T10:00:00Z",
            "app_name": "Claude Code",
            "window_name": "Claude Code — ~/chat",
            "text": "Hello World",
            "text_source": "accessibility",
            "urls": [],
            "browser_url": "https://example.com",
            "status": "completed",
        }

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/1/context")

            assert response.status_code == 200
            body = json.loads(response.data)
            assert body["frame_id"] == 1
            assert body["text"] == "Hello World"
            assert body["text_source"] == "accessibility"
            assert body["timestamp"] == "2026-03-26T10:00:00Z"
            assert body["app_name"] == "Claude Code"
            assert body["window_name"] == "Claude Code — ~/chat"
            # nodes and description_status are removed
            assert "nodes" not in body
            assert "description_status" not in body

    def test_frame_context_returns_404_for_missing_frame(self, app_with_context_route, mock_store):
        """Endpoint returns 404 for non-existent frame."""
        mock_store.get_frame_context.return_value = None

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/99999/context")

            assert response.status_code == 404
            body = json.loads(response.data)
            assert body["code"] == "NOT_FOUND"

    def test_frame_context_returns_ocr_fallback(self, app_with_context_route, mock_store):
        """Endpoint returns OCR data when accessibility unavailable."""
        mock_store.get_frame_context.return_value = {
            "frame_id": 3,
            "timestamp": "2026-03-26T10:00:00Z",
            "app_name": "Terminal",
            "window_name": "zsh — 120×40",
            "text": "OCR extracted text with https://ocr-url.com link",
            "text_source": "ocr",
            "urls": ["https://ocr-url.com"],
            "browser_url": None,
            "status": "completed",
        }

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/3/context")

            assert response.status_code == 200
            body = json.loads(response.data)
            assert body["text_source"] == "ocr"
            assert "https://ocr-url.com" in body["urls"]

    def test_frame_context_includes_browser_url(self, app_with_context_route, mock_store):
        """Endpoint includes browser_url when available."""
        mock_store.get_frame_context.return_value = {
            "frame_id": 1,
            "timestamp": "2026-03-26T10:00:00Z",
            "app_name": "Chrome",
            "window_name": "GitHub — MyRecall",
            "text": "Page content",
            "text_source": "accessibility",
            "urls": [],
            "browser_url": "https://example.com/page",
            "status": "completed",
        }

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/1/context")

            assert response.status_code == 200
            body = json.loads(response.data)
            assert body["browser_url"] == "https://example.com/page"

    def test_frame_context_includes_description_when_completed(self, app_with_context_route, mock_store):
        """Endpoint includes description object when description_status=completed."""
        mock_store.get_frame_context.return_value = {
            "frame_id": 1,
            "timestamp": "2026-03-26T10:00:00Z",
            "app_name": "Claude Code",
            "window_name": "Claude Code Window",
            "text": "Test",
            "text_source": "accessibility",
            "urls": [],
            "browser_url": None,
            "status": "completed",
        }

        # Configure mock to return description_status=completed
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = {"description_status": "completed"}
        # Set up mock_conn as a context manager
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=None)
        mock_store._connect.return_value = mock_conn
        mock_store.get_frame_description.return_value = {
            "narrative": "User is coding in Claude Code.",
            "summary": "Coding session",
            "tags": ["coding", "claude-code"],
        }

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/1/context")

            assert response.status_code == 200
            body = json.loads(response.data)
            assert body["description"] is not None
            assert body["description"]["narrative"] == "User is coding in Claude Code."
            assert body["description"]["summary"] == "Coding session"
            assert body["description"]["tags"] == ["coding", "claude-code"]
            # description_status should NOT be in response
            assert "description_status" not in body

    def test_frame_context_omits_description_when_not_completed(self, app_with_context_route, mock_store):
        """Endpoint returns description=null when no description generated."""
        mock_store.get_frame_context.return_value = {
            "frame_id": 1,
            "timestamp": "2026-03-26T10:00:00Z",
            "app_name": "Safari",
            "window_name": "Safari Window",
            "text": "Test",
            "text_source": "accessibility",
            "urls": [],
            "browser_url": None,
            "status": "completed",
        }

        # Configure mock to return description_status != completed
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = {"description_status": "pending"}
        # Set up mock_conn as a context manager
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=None)
        mock_store._connect.return_value = mock_conn
        mock_store.get_frame_description.return_value = None

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_context_route.test_client()
            response = client.get("/v1/frames/1/context")

            assert response.status_code == 200
            body = json.loads(response.data)
            assert body["description"] is None
            assert "description_status" not in body

