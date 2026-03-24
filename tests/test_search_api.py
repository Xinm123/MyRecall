"""Tests for GET /v1/search/counts API endpoint.

Tests cover:
- Basic endpoint functionality
- Parameter parsing
- Edge cases and error handling
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from openrecall.server.api_v1 import v1_bp
from openrecall.server.search.engine import SearchEngine


@pytest.fixture
def app_with_search_counts_route():
    """Create a Flask app with the search routes registered."""
    app = Flask(__name__)
    app.register_blueprint(v1_bp)
    yield app


@pytest.fixture
def mock_search_engine():
    """Create a mock search engine with count_by_type method."""
    mock_engine = MagicMock(spec=SearchEngine)
    mock_engine.count_by_type.return_value = {"ocr": 142, "accessibility": 23}
    return mock_engine


class TestSearchCountsAPI:
    """Tests for GET /v1/search/counts endpoint."""

    def test_search_counts_endpoint_returns_type_counts(self, app_with_search_counts_route, mock_search_engine):
        """Test /v1/search/counts returns ocr and accessibility counts."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_counts_route.test_client()
            response = client.get("/v1/search/counts?q=test")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert "counts" in data
            assert "ocr" in data["counts"]
            assert "accessibility" in data["counts"]
            assert isinstance(data["counts"]["ocr"], int)
            assert isinstance(data["counts"]["accessibility"], int)

    def test_search_counts_endpoint_handles_invalid_params(self, app_with_search_counts_route, mock_search_engine):
        """Test /v1/search/counts handles invalid params gracefully."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_counts_route.test_client()
            response = client.get("/v1/search/counts?min_length=invalid")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert "counts" in data
            assert "ocr" in data["counts"]
            assert "accessibility" in data["counts"]

    def test_search_counts_endpoint_passes_query_params(self, app_with_search_counts_route, mock_search_engine):
        """Test /v1/search/counts passes query params to search engine."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_counts_route.test_client()
            client.get("/v1/search/counts?q=hello&app_name=Safari&focused=true")

            # Verify count_by_type was called with correct params
            call_args = mock_search_engine.count_by_type.call_args
            assert call_args.kwargs.get("q") == "hello"
            assert call_args.kwargs.get("app_name") == "Safari"
            assert call_args.kwargs.get("focused") is True

    def test_search_counts_endpoint_passes_time_range(self, app_with_search_counts_route, mock_search_engine):
        """Test /v1/search/counts passes time range params."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_counts_route.test_client()
            client.get("/v1/search/counts?q=test&start_time=2026-03-18T10:00:00Z&end_time=2026-03-18T11:00:00Z")

            call_args = mock_search_engine.count_by_type.call_args
            assert call_args.kwargs.get("start_time") == "2026-03-18T10:00:00Z"
            assert call_args.kwargs.get("end_time") == "2026-03-18T11:00:00Z"

    def test_search_counts_endpoint_passes_window_name(self, app_with_search_counts_route, mock_search_engine):
        """Test /v1/search/counts passes window_name param."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_counts_route.test_client()
            client.get("/v1/search/counts?q=test&window_name=MyWindow")

            call_args = mock_search_engine.count_by_type.call_args
            assert call_args.kwargs.get("window_name") == "MyWindow"

    def test_search_counts_endpoint_passes_browser_url(self, app_with_search_counts_route, mock_search_engine):
        """Test /v1/search/counts passes browser_url param."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_counts_route.test_client()
            client.get("/v1/search/counts?q=test&browser_url=http://example.com")

            call_args = mock_search_engine.count_by_type.call_args
            assert call_args.kwargs.get("browser_url") == "http://example.com"

    def test_search_counts_endpoint_passes_text_length_filters(self, app_with_search_counts_route, mock_search_engine):
        """Test /v1/search/counts passes min_length and max_length params."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_counts_route.test_client()
            client.get("/v1/search/counts?q=test&min_length=10&max_length=1000")

            call_args = mock_search_engine.count_by_type.call_args
            assert call_args.kwargs.get("min_length") == 10
            assert call_args.kwargs.get("max_length") == 1000

    def test_search_counts_endpoint_empty_query(self, app_with_search_counts_route, mock_search_engine):
        """Test /v1/search/counts handles empty query."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_counts_route.test_client()
            response = client.get("/v1/search/counts")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert "counts" in data
            assert "ocr" in data["counts"]
            assert "accessibility" in data["counts"]

    def test_search_counts_endpoint_focused_false(self, app_with_search_counts_route, mock_search_engine):
        """Test /v1/search/counts handles focused=false."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_counts_route.test_client()
            client.get("/v1/search/counts?q=test&focused=false")

            call_args = mock_search_engine.count_by_type.call_args
            assert call_args.kwargs.get("focused") is False

    def test_search_counts_endpoint_focused_variants(self, app_with_search_counts_route, mock_search_engine):
        """Test /v1/search/counts handles various focused param values."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_counts_route.test_client()

            # Test "1" for true
            client.get("/v1/search/counts?q=test&focused=1")
            call_args = mock_search_engine.count_by_type.call_args
            assert call_args.kwargs.get("focused") is True

            # Test "0" for false
            client.get("/v1/search/counts?q=test&focused=0")
            call_args = mock_search_engine.count_by_type.call_args
            assert call_args.kwargs.get("focused") is False

            # Test "yes" for true
            client.get("/v1/search/counts?q=test&focused=yes")
            call_args = mock_search_engine.count_by_type.call_args
            assert call_args.kwargs.get("focused") is True

            # Test "no" for false
            client.get("/v1/search/counts?q=test&focused=no")
            call_args = mock_search_engine.count_by_type.call_args
            assert call_args.kwargs.get("focused") is False
