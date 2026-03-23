"""HTTP API tests for /v1/activity-summary endpoint.

Phase 8 of Chat MVP implementation.
SSOT: docs/v3/chat/mvp.md
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from openrecall.server.api_v1 import v1_bp
from openrecall.server.database.frames_store import FramesStore


@pytest.fixture
def app_with_activity_summary_route():
    """Create a Flask app with the v1 blueprint registered."""
    app = Flask(__name__)
    app.register_blueprint(v1_bp)
    yield app


@pytest.fixture
def mock_store():
    """Create a mock FramesStore with test data."""
    mock = MagicMock(spec=FramesStore)

    mock.get_activity_summary_apps.return_value = [
        {"name": "Safari", "frame_count": 10, "minutes": 0.33},
        {"name": "VSCode", "frame_count": 5, "minutes": 0.17},
    ]
    mock.get_activity_summary_recent_texts.return_value = [
        {"frame_id": 1, "text": "Hello world", "role": "AXStaticText", "app_name": "Safari", "timestamp": "2026-03-19T10:00:00Z"},
    ]
    mock.get_activity_summary_total_frames.return_value = 15
    mock.get_activity_summary_time_range.return_value = {
        "start": "2026-03-19T09:00:00Z",
        "end": "2026-03-19T10:00:00Z",
    }
    return mock


class TestActivitySummaryAPI:
    """Tests for GET /v1/activity-summary."""

    def test_returns_200_with_valid_params(self, app_with_activity_summary_route, mock_store):
        """Endpoint returns 200 with required parameters."""
        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_activity_summary_route.test_client()
            response = client.get("/v1/activity-summary?start_time=2026-03-19T00:00:00Z&end_time=2026-03-19T23:59:59Z")
            assert response.status_code == 200

    def test_returns_valid_json_structure(self, app_with_activity_summary_route, mock_store):
        """Response has required top-level keys."""
        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_activity_summary_route.test_client()
            response = client.get("/v1/activity-summary?start_time=2026-03-19T00:00:00Z&end_time=2026-03-19T23:59:59Z")
            data = json.loads(response.data)

            assert "apps" in data
            assert "recent_texts" in data
            assert "audio_summary" in data
            assert "total_frames" in data
            assert "time_range" in data

    def test_audio_summary_is_empty_shell(self, app_with_activity_summary_route, mock_store):
        """audio_summary is shape-compatible empty shell."""
        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_activity_summary_route.test_client()
            response = client.get("/v1/activity-summary?start_time=2026-03-19T00:00:00Z&end_time=2026-03-19T23:59:59Z")
            data = json.loads(response.data)

            assert data["audio_summary"] == {"segment_count": 0, "speakers": []}

    def test_returns_400_without_start_time(self, app_with_activity_summary_route, mock_store):
        """Returns 400 when start_time is missing."""
        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_activity_summary_route.test_client()
            response = client.get("/v1/activity-summary?end_time=2026-03-19T23:59:59Z")
            assert response.status_code == 400
            data = json.loads(response.data)
            assert "error" in data

    def test_returns_400_without_end_time(self, app_with_activity_summary_route, mock_store):
        """Returns 400 when end_time is missing."""
        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_activity_summary_route.test_client()
            response = client.get("/v1/activity-summary?start_time=2026-03-19T00:00:00Z")
            assert response.status_code == 400

    def test_time_range_falls_back_to_query_bounds_when_no_frames(self, app_with_activity_summary_route):
        """time_range is never null — falls back to query params when store returns None."""
        mock = MagicMock(spec=FramesStore)
        mock.get_activity_summary_apps.return_value = []
        mock.get_activity_summary_recent_texts.return_value = []
        mock.get_activity_summary_total_frames.return_value = 0
        mock.get_activity_summary_time_range.return_value = None  # no frames

        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock):
            client = app_with_activity_summary_route.test_client()
            response = client.get(
                "/v1/activity-summary?start_time=2026-03-19T09:00:00Z&end_time=2026-03-19T10:00:00Z"
            )
            data = json.loads(response.data)

            assert data["time_range"] is not None
            assert data["time_range"]["start"] == "2026-03-19T09:00:00Z"
            assert data["time_range"]["end"] == "2026-03-19T10:00:00Z"

    def test_filters_by_app_name(self, app_with_activity_summary_route, mock_store):
        """Passes app_name filter to store methods."""
        with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
            client = app_with_activity_summary_route.test_client()
            response = client.get("/v1/activity-summary?start_time=2026-03-19T00:00:00Z&end_time=2026-03-19T23:59:59Z&app_name=Safari")
            assert response.status_code == 200

            # Verify app_name was passed to store methods
            mock_store.get_activity_summary_apps.assert_called_once()
            call_kwargs = mock_store.get_activity_summary_apps.call_args[1]
            assert call_kwargs["app_name"] == "Safari"
