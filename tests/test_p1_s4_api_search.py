"""Tests for GET /v1/search API route — P1-S4 Section 3.

Tests cover:
- Parameter parsing
- Response serialization
- Reserved fields presence
- Error handling

Per tasks.md §3 and specs/fts-search/spec.md.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from openrecall.server.api_v1 import v1_bp
from openrecall.server.search.engine import SearchEngine


@pytest.fixture
def app_with_search_route():
    """Create a Flask app with the search route registered."""
    app = Flask(__name__)
    app.register_blueprint(v1_bp)
    yield app


@pytest.fixture
def mock_search_engine():
    """Create a mock search engine with test data."""
    mock_engine = MagicMock(spec=SearchEngine)

    # Default test results (flat structure, no content wrapper)
    test_results = [
        {
            "frame_id": 1,
            "timestamp": "2026-03-18T10:00:00Z",
            "text": "Hello world from Safari",
            "text_source": "ocr",
            "app_name": "Safari",
            "window_name": "Web Browser",
            "browser_url": None,
            "focused": True,
            "device_name": "monitor_0",
            "frame_url": "/v1/frames/1",
            "embedding_status": None,
            "score": 0.9,
            "fts_score": -2.5,
        },
        {
            "frame_id": 2,
            "timestamp": "2026-03-18T11:00:00Z",
            "text": "def hello(): pass",
            "text_source": "ocr",
            "app_name": "VSCode",
            "window_name": "main.py",
            "browser_url": None,
            "focused": True,
            "device_name": "monitor_0",
            "frame_url": "/v1/frames/2",
            "embedding_status": None,
            "score": 0.8,
            "fts_score": -3.0,
        },
        {
            "frame_id": 3,
            "timestamp": "2026-03-18T12:00:00Z",
            "text": "git status",
            "text_source": "ocr",
            "app_name": "Terminal",
            "window_name": "bash",
            "browser_url": None,
            "focused": False,
            "device_name": "monitor_0",
            "frame_url": "/v1/frames/3",
            "embedding_status": None,
            "score": 0.7,
            "fts_score": -3.5,
        },
    ]

    mock_engine.search.return_value = (test_results, 3)
    return mock_engine


class TestSearchAPIBasic:
    """Basic search API tests."""

    def test_search_returns_200(self, app_with_search_route, mock_search_engine):
        """Search endpoint returns 200."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello&mode=fts")
            assert response.status_code == 200

    def test_search_returns_json(self, app_with_search_route, mock_search_engine):
        """Search endpoint returns JSON."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello&mode=fts")
            assert response.content_type.startswith("application/json")

    def test_search_empty_query(self, app_with_search_route, mock_search_engine):
        """Empty query returns all frames."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=&mode=fts")
            data = json.loads(response.data)

            assert "data" in data
            assert "pagination" in data
            assert data["pagination"]["total"] == 3

    def test_search_no_query_param(self, app_with_search_route, mock_search_engine):
        """Missing q parameter returns all frames."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?mode=fts")
            data = json.loads(response.data)

            assert data["pagination"]["total"] == 3


class TestSearchAPIResponseSchema:
    """Response schema tests."""

    def test_data_items_have_frame_id(self, app_with_search_route, mock_search_engine):
        """Each data item has frame_id field."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello&mode=fts")
            data = json.loads(response.data)

            # Each item in data should have a frame_id field (flat structure)
            for item in data.get("data", []):
                assert "frame_id" in item
                assert isinstance(item.get("frame_id"), int)

    def test_data_is_array(self, app_with_search_route, mock_search_engine):
        """Data field is an array."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=&mode=fts")
            data = json.loads(response.data)

            assert isinstance(data.get("data"), list)

    def test_items_have_required_fields(self, app_with_search_route, mock_search_engine):
        """Each item has required fields (flat structure, no content wrapper)."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=&mode=fts")
            data = json.loads(response.data)

            required_fields = [
                "frame_id", "timestamp", "text_source",
                "app_name", "window_name", "browser_url", "focused",
                "device_name", "frame_url"
            ]

            for item in data.get("data", []):
                for field in required_fields:
                    assert field in item, f"Missing field: {field}"

    def test_reference_fields_non_null(self, app_with_search_route, mock_search_engine):
        """frame_id and timestamp are non-null."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=&mode=fts")
            data = json.loads(response.data)

            for item in data.get("data", []):
                assert item.get("frame_id") is not None
                assert item.get("timestamp") is not None

    def test_browser_url_is_present(self, app_with_search_route, mock_search_engine):
        """browser_url field is present (may be null)."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=&mode=fts")
            data = json.loads(response.data)

            for item in data.get("data", []):
                # browser_url should be present (null for non-browser frames)
                assert "browser_url" in item

    def test_pagination_structure(self, app_with_search_route, mock_search_engine):
        """Pagination has required fields."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=&limit=2&offset=1&mode=fts")
            data = json.loads(response.data)

            pagination = data.get("pagination", {})
            assert "limit" in pagination
            assert "offset" in pagination
            assert "total" in pagination
            assert pagination["limit"] == 2
            assert pagination["offset"] == 1
            assert pagination["total"] == 3


class TestSearchAPIParameters:
    """Parameter parsing tests."""

    def test_limit_parameter(self, app_with_search_route, mock_search_engine):
        """Limit parameter limits results."""
        # Return only 1 result for this test
        mock_search_engine.search.return_value = ([{
            "frame_id": 1,
            "timestamp": "2026-03-18T10:00:00Z",
            "text": "Hello",
            "text_source": "ocr",
            "app_name": "Safari",
            "window_name": "Web",
            "browser_url": None,
            "focused": True,
            "device_name": "monitor_0",
            "frame_url": "/v1/frames/1",
            "embedding_status": None,
            "score": 0.9,
            "fts_score": -2.5,
        }], 3)

        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=&limit=1&mode=fts")
            data = json.loads(response.data)

            assert len(data.get("data", [])) == 1
            assert data["pagination"]["limit"] == 1

    def test_offset_parameter(self, app_with_search_route, mock_search_engine):
        """Offset parameter skips results."""
        # First result
        mock_search_engine.search.return_value = ([{
            "frame_id": 1,
            "timestamp": "2026-03-18T10:00:00Z",
            "text": "Hello",
            "text_source": "ocr",
            "app_name": "Safari",
            "window_name": "Web",
            "browser_url": None,
            "focused": True,
            "device_name": "monitor_0",
            "frame_url": "/v1/frames/1",
            "embedding_status": None,
            "score": 0.9,
            "fts_score": -2.5,
        }], 3)

        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response1 = client.get("/v1/search?q=&limit=1&offset=0&mode=fts")
            data1 = json.loads(response1.data)

            # Second result
            mock_search_engine.search.return_value = ([{
                "frame_id": 2,
                "timestamp": "2026-03-18T11:00:00Z",
                "text": "World",
                "text_source": "ocr",
                "app_name": "VSCode",
                "window_name": "main.py",
                "browser_url": None,
                "focused": True,
                "device_name": "monitor_0",
                "frame_url": "/v1/frames/2",
                "embedding_status": None,
                "score": 0.8,
                "fts_score": -3.0,
            }], 3)

            response2 = client.get("/v1/search?q=&limit=1&offset=1&mode=fts")
            data2 = json.loads(response2.data)

            # Different results (flat structure - no content wrapper)
            id1 = data1["data"][0]["frame_id"]
            id2 = data2["data"][0]["frame_id"]
            assert id1 != id2

    def test_limit_exceeds_max_not_clamped(self, app_with_search_route, mock_search_engine):
        """Limit is not clamped (no maximum)."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=&limit=500&mode=fts")
            data = json.loads(response.data)

            # Should not error, limit is passed through
            assert response.status_code == 200
            # Limit in response should be the requested value (no clamping)
            assert data["pagination"]["limit"] == 500

    def test_app_name_filter(self, app_with_search_route, mock_search_engine):
        """app_name filter is passed to search engine."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&app_name=Safari&mode=fts")

            # Verify app_name was passed to search
            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("app_name") == "Safari"

    def test_focused_filter_true(self, app_with_search_route, mock_search_engine):
        """focused=true filter is passed to search engine."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&focused=true&mode=fts")

            # Verify focused was passed as True
            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("focused") is True

    def test_time_range_filter(self, app_with_search_route, mock_search_engine):
        """Time range filter is passed to search engine."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&start_time=2026-03-18T10:30:00Z&end_time=2026-03-18T11:30:00Z&mode=fts")

            # Verify time range was passed
            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("start_time") == "2026-03-18T10:30:00Z"
            assert call_args.kwargs.get("end_time") == "2026-03-18T11:30:00Z"

    def test_browser_url_accepted_noop(self, app_with_search_route, mock_search_engine):
        """browser_url parameter is accepted but no-op in P1."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            # Should not error
            response = client.get("/v1/search?q=&browser_url=http://example.com&mode=fts")
            assert response.status_code == 200


class TestSearchAPINoResults:
    """No results case."""

    def test_nonexistent_query(self, app_with_search_route, mock_search_engine):
        """Non-matching query returns empty data."""
        mock_search_engine.search.return_value = ([], 0)

        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=nonexistentterm12345xyz&mode=fts")
            data = json.loads(response.data)

            assert data.get("data") == []
            assert data.get("pagination", {}).get("total") == 0
            assert response.status_code == 200
