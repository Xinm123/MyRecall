"""Tests for search API response structure validation — P1-S4 Section 3.

Tests validate:
- Success response field completeness
- Empty result structure
- Reserved fields as null/[]
- Error response format

Per tasks.md §3 and specs/fts-search/spec.md §4.5.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from openrecall.server.api_v1 import v1_bp
from openrecall.server.search.engine import SearchEngine


pytestmark = [pytest.mark.integration, pytest.mark.api]


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

    test_results = [
        {
            "frame_id": 1,
            "timestamp": "2026-03-18T10:00:00Z",
            "text": "Hello world from Safari",
            "app_name": "Safari",
            "window_name": "Web Browser",
            "browser_url": None,
            "focused": True,
            "device_name": "monitor_0",
            "file_path": "2026-03-18T10:00:00Z.jpg",
            "frame_url": "/v1/frames/1",
            "tags": [],
        },
    ]

    mock_engine.search.return_value = (test_results, 1)
    return mock_engine


@pytest.fixture
def mock_empty_search_engine():
    """Create a mock search engine with no results."""
    mock_engine = MagicMock(spec=SearchEngine)
    mock_engine.search.return_value = ([], 0)
    return mock_engine


class TestResponseSchemaSuccess:
    """Success response structure validation."""

    def test_response_type_is_ocr(self, app_with_search_route, mock_search_engine):
        """Response type field is 'OCR'."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            assert data.get("type") == "OCR"

    def test_response_has_data_array(self, app_with_search_route, mock_search_engine):
        """Response has data field as array."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            assert "data" in data
            assert isinstance(data["data"], list)

    def test_response_has_pagination(self, app_with_search_route, mock_search_engine):
        """Response has pagination object."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            assert "pagination" in data
            assert isinstance(data["pagination"], dict)


class TestContentFieldCompleteness:
    """Content object field completeness tests."""

    def test_content_has_all_required_fields(
        self, app_with_search_route, mock_search_engine
    ):
        """Each content item has all required fields per spec."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            required_fields = [
                "frame_id",
                "text",
                "timestamp",
                "file_path",
                "frame_url",
                "app_name",
                "window_name",
                "browser_url",
                "focused",
                "device_name",
                "tags",
            ]

            for item in data.get("data", []):
                content = item.get("content", {})
                for field in required_fields:
                    assert field in content, f"Missing required field: {field}"

    def test_content_has_type_field(self, app_with_search_route, mock_search_engine):
        """Each data item has type field set to 'OCR'."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            for item in data.get("data", []):
                assert item.get("type") == "OCR"

    def test_frame_id_is_integer(self, app_with_search_route, mock_search_engine):
        """frame_id is an integer."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            for item in data.get("data", []):
                content = item.get("content", {})
                assert isinstance(content.get("frame_id"), int)

    def test_timestamp_is_string(self, app_with_search_route, mock_search_engine):
        """timestamp is a string (ISO8601)."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            for item in data.get("data", []):
                content = item.get("content", {})
                assert isinstance(content.get("timestamp"), str)

    def test_focused_is_boolean(self, app_with_search_route, mock_search_engine):
        """focused field is boolean."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            for item in data.get("data", []):
                content = item.get("content", {})
                assert isinstance(content.get("focused"), bool)


class TestReservedFields:
    """Reserved fields validation tests."""

    def test_browser_url_is_null(self, app_with_search_route, mock_search_engine):
        """browser_url is null (reserved for P2)."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            for item in data.get("data", []):
                content = item.get("content", {})
                assert "browser_url" in content
                assert content.get("browser_url") is None

    def test_tags_is_empty_list(self, app_with_search_route, mock_search_engine):
        """tags is an empty list (reserved for P2)."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            for item in data.get("data", []):
                content = item.get("content", {})
                assert "tags" in content
                assert content.get("tags") == []
                assert isinstance(content.get("tags"), list)


class TestPaginationStructure:
    """Pagination structure validation tests."""

    def test_pagination_has_limit(self, app_with_search_route, mock_search_engine):
        """Pagination has limit field."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello&limit=10")
            data = json.loads(response.data)

            pagination = data.get("pagination", {})
            assert "limit" in pagination
            assert pagination["limit"] == 10

    def test_pagination_has_offset(self, app_with_search_route, mock_search_engine):
        """Pagination has offset field."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello&offset=5")
            data = json.loads(response.data)

            pagination = data.get("pagination", {})
            assert "offset" in pagination
            assert pagination["offset"] == 5

    def test_pagination_has_total(self, app_with_search_route, mock_search_engine):
        """Pagination has total field."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            pagination = data.get("pagination", {})
            assert "total" in pagination
            assert pagination["total"] == 1

    def test_pagination_default_values(self, app_with_search_route, mock_search_engine):
        """Pagination uses correct defaults when not specified."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello")
            data = json.loads(response.data)

            pagination = data.get("pagination", {})
            assert pagination["limit"] == 20  # Default limit
            assert pagination["offset"] == 0  # Default offset

    def test_pagination_all_fields_present(
        self, app_with_search_route, mock_search_engine
    ):
        """Pagination has all required fields: limit, offset, total."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello&limit=5&offset=0")
            data = json.loads(response.data)

            pagination = data.get("pagination", {})
            required = ["limit", "offset", "total"]
            for field in required:
                assert field in pagination, f"Missing pagination field: {field}"


class TestEmptyResultStructure:
    """Empty result structure validation tests."""

    def test_empty_results_has_data_array(
        self, app_with_search_route, mock_empty_search_engine
    ):
        """Empty results returns data as empty array."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_empty_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=nonexistent")
            data = json.loads(response.data)

            assert "data" in data
            assert data["data"] == []
            assert isinstance(data["data"], list)

    def test_empty_results_has_type(
        self, app_with_search_route, mock_empty_search_engine
    ):
        """Empty results response still has type field."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_empty_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=nonexistent")
            data = json.loads(response.data)

            assert data.get("type") == "OCR"

    def test_empty_results_has_pagination(
        self, app_with_search_route, mock_empty_search_engine
    ):
        """Empty results has pagination with total=0."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_empty_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=nonexistent")
            data = json.loads(response.data)

            pagination = data.get("pagination", {})
            assert "limit" in pagination
            assert "offset" in pagination
            assert pagination["total"] == 0

    def test_empty_results_status_200(
        self, app_with_search_route, mock_empty_search_engine
    ):
        """Empty results returns 200 status."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_empty_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=nonexistent")

            assert response.status_code == 200

    def test_empty_results_complete_structure(
        self, app_with_search_route, mock_empty_search_engine
    ):
        """Empty results has complete response structure."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_empty_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=nonexistent")
            data = json.loads(response.data)

            # Top-level structure
            assert "type" in data
            assert "data" in data
            assert "pagination" in data

            # Values
            assert data["type"] == "OCR"
            assert data["data"] == []
            assert data["pagination"]["total"] == 0


class TestErrorResponseFormat:
    """Error response format validation tests."""

    def test_invalid_limit_handled_gracefully(
        self, app_with_search_route, mock_search_engine
    ):
        """Invalid limit parameter is handled gracefully (uses default)."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello&limit=invalid")

            # Should not error, defaults are used
            assert response.status_code == 200

    def test_invalid_offset_handled_gracefully(
        self, app_with_search_route, mock_search_engine
    ):
        """Invalid offset parameter is handled gracefully (uses default)."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello&offset=invalid")

            # Should not error, defaults are used
            assert response.status_code == 200

    def test_negative_limit_handled(self, app_with_search_route, mock_search_engine):
        """Negative limit is handled (clamped to minimum)."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello&limit=-5")
            data = json.loads(response.data)

            assert response.status_code == 200
            assert data["pagination"]["limit"] >= 1

    def test_negative_offset_handled(self, app_with_search_route, mock_search_engine):
        """Negative offset is handled (clamped to minimum)."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=hello&offset=-5")
            data = json.loads(response.data)

            assert response.status_code == 200
            assert data["pagination"]["offset"] == 0
