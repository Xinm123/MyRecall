"""Tests for optimized GET /v1/search API endpoint.

Tests cover:
- Mode defaults to hybrid
- Flattened response structure (no content wrapper, no type/tags/file_path)
- include_text and max_text_length parameters
- Limit without max restriction
- Removal of min_length/max_length parameters
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from openrecall.server.api_v1 import v1_bp


@pytest.fixture
def app_with_search_route():
    """Create a Flask app with the search route registered."""
    app = Flask(__name__)
    app.register_blueprint(v1_bp)
    yield app


@pytest.fixture
def mock_hybrid_engine():
    """Create a mock hybrid search engine with search method."""
    mock_engine = MagicMock()
    mock_engine.search.return_value = (
        [
            {
                "frame_id": "frame-001",
                "text": "This is sample text for testing search results",
                "text_source": "ocr",
                "timestamp": "2026-04-13T10:00:00Z",
                "frame_url": "/v1/frames/frame-001",
                "app_name": "Safari",
                "window_name": "Test Window",
                "browser_url": "https://example.com",
                "focused": True,
                "device_name": "monitor_0",
                "embedding_status": "completed",
                "score": 0.95,
                "fts_score": 0.85,
                "fts_rank": 1,
                "cosine_score": 0.92,
                "hybrid_rank": 1,
                "vector_rank": 2,
            }
        ],
        1,
    )
    return mock_engine


class TestSearchAPIOptimized:
    """Tests for GET /v1/search endpoint optimizations."""

    def test_mode_defaults_to_hybrid(self, app_with_search_route, mock_hybrid_engine):
        """Test that mode parameter defaults to 'hybrid' instead of 'fts'."""
        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_hybrid_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test")

            assert response.status_code == 200
            # Verify HybridSearchEngine was called (default mode is hybrid)
            mock_hybrid_engine.search.assert_called_once()
            call_kwargs = mock_hybrid_engine.search.call_args.kwargs
            assert call_kwargs.get("mode") == "hybrid"

    def test_no_type_field_in_response(self, app_with_search_route, mock_hybrid_engine):
        """Test that response items do not contain 'type' field."""
        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_hybrid_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data["data"]) > 0
            item = data["data"][0]
            assert "type" not in item, "Response should not contain 'type' field"

    def test_no_tags_field_in_response(self, app_with_search_route, mock_hybrid_engine):
        """Test that response items do not contain 'tags' field."""
        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_hybrid_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test")

            assert response.status_code == 200
            data = json.loads(response.data)
            item = data["data"][0]
            assert "tags" not in item, "Response should not contain 'tags' field"

    def test_no_file_path_field_in_response(self, app_with_search_route, mock_hybrid_engine):
        """Test that response items do not contain 'file_path' field."""
        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_hybrid_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test")

            assert response.status_code == 200
            data = json.loads(response.data)
            item = data["data"][0]
            assert "file_path" not in item, "Response should not contain 'file_path' field"

    def test_no_content_wrapper(self, app_with_search_route, mock_hybrid_engine):
        """Test that response items are flat, not wrapped in 'content'."""
        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_hybrid_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test")

            assert response.status_code == 200
            data = json.loads(response.data)
            item = data["data"][0]
            assert "content" not in item, "Response should not have 'content' wrapper"
            # Fields should be at top level
            assert "frame_id" in item
            assert "timestamp" in item
            assert "app_name" in item

    def test_include_text_false_hides_text(self, app_with_search_route, mock_hybrid_engine):
        """Test that include_text=false (default) does not include text field."""
        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_hybrid_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test")  # No include_text param

            assert response.status_code == 200
            data = json.loads(response.data)
            item = data["data"][0]
            # text should not be present by default
            assert "text" not in item, "text field should not be present when include_text=false"

    def test_include_text_true_shows_text(self, app_with_search_route, mock_hybrid_engine):
        """Test that include_text=true includes text field."""
        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_hybrid_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test&include_text=true")

            assert response.status_code == 200
            data = json.loads(response.data)
            item = data["data"][0]
            assert "text" in item
            assert item["text"] == "This is sample text for testing search results"

    def test_text_truncated_to_max_text_length(self, app_with_search_route):
        """Test that text is truncated when exceeding max_text_length."""
        long_text = "A" * 3000  # 3000 chars
        mock_engine = MagicMock()
        mock_engine.search.return_value = (
            [
                {
                    "frame_id": "frame-001",
                    "text": long_text,
                    "text_source": "ocr",
                    "timestamp": "2026-04-13T10:00:00Z",
                    "frame_url": "/v1/frames/frame-001",
                    "app_name": "Safari",
                    "window_name": "Test Window",
                    "browser_url": None,
                    "focused": True,
                    "device_name": "monitor_0",
                    "embedding_status": "completed",
                    "score": 0.95,
                }
            ],
            1,
        )

        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_engine,
        ):
            client = app_with_search_route.test_client()
            # Request with max_text_length=100
            response = client.get("/v1/search?q=test&include_text=true&max_text_length=100")

            assert response.status_code == 200
            data = json.loads(response.data)
            item = data["data"][0]

            # Text should be truncated with middle removed
            assert "text" in item
            text = item["text"]
            # Should start and end with 50 chars each (half of 100)
            assert text.startswith("A" * 50)
            assert text.endswith("A" * 50)
            # Should contain truncation indicator
            assert "...2900 chars..." in text or "...2900" in text

    def test_limit_no_max_restriction(self, app_with_search_route, mock_hybrid_engine):
        """Test that limit has no maximum restriction (was capped at 100)."""
        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_hybrid_engine,
        ):
            client = app_with_search_route.test_client()
            # Request with limit > 100
            response = client.get("/v1/search?q=test&limit=500")

            assert response.status_code == 200
            call_kwargs = mock_hybrid_engine.search.call_args.kwargs
            # Limit should be passed as-is, not capped
            assert call_kwargs.get("limit") == 500

    def test_no_min_length_parameter(self, app_with_search_route, mock_hybrid_engine):
        """Test that min_length parameter is not passed to engine (removed)."""
        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_hybrid_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test&min_length=10")

            assert response.status_code == 200
            call_kwargs = mock_hybrid_engine.search.call_args.kwargs
            # min_length should not be in kwargs
            assert "min_length" not in call_kwargs, "min_length should be removed from engine call"

    def test_no_max_length_parameter(self, app_with_search_route, mock_hybrid_engine):
        """Test that max_length parameter is not passed to engine (removed)."""
        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_hybrid_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test&max_length=1000")

            assert response.status_code == 200
            call_kwargs = mock_hybrid_engine.search.call_args.kwargs
            # max_length should not be in kwargs
            assert "max_length" not in call_kwargs, "max_length should be removed from engine call"

    def test_description_included_when_available(self, app_with_search_route):
        """Test that description is included when frame has one."""
        mock_engine = MagicMock()
        mock_engine.search.return_value = (
            [
                {
                    "frame_id": 1,
                    "text": "sample text",
                    "text_source": "ocr",
                    "timestamp": "2026-04-13T10:00:00Z",
                    "frame_url": "/v1/frames/1",
                    "app_name": "Safari",
                    "window_name": "Test Window",
                    "browser_url": None,
                    "focused": True,
                    "device_name": "monitor_0",
                    "embedding_status": "completed",
                    "score": 0.95,
                }
            ],
            1,
        )

        mock_store = MagicMock()
        mock_store.get_frame_descriptions_batch.return_value = {
            1: {"narrative": None, "summary": "A detailed description", "tags": []}
        }

        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_engine,
        ):
            with patch(
                "openrecall.server.api_v1._get_frames_store",
                return_value=mock_store,
            ):
                client = app_with_search_route.test_client()
                response = client.get("/v1/search?q=test")

                assert response.status_code == 200
                data = json.loads(response.data)
                item = data["data"][0]
                assert "description" in item
                assert item["description"] == {"narrative": None, "summary": "A detailed description", "tags": []}

    def test_score_fields_copied_to_response(self, app_with_search_route, mock_hybrid_engine):
        """Test that all score fields from engine are copied to response."""
        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_hybrid_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test")

            assert response.status_code == 200
            data = json.loads(response.data)
            item = data["data"][0]

            # Check all score fields are present
            assert "score" in item
            assert item["score"] == 0.95
            assert "fts_score" in item
            assert item["fts_score"] == 0.85
            assert "fts_rank" in item
            assert "cosine_score" in item
            assert "hybrid_rank" in item
            assert "vector_rank" in item

    def test_fts_mode_uses_fts_engine(self, app_with_search_route):
        """Test that mode=fts still uses the FTS engine (not hybrid)."""
        mock_fts_engine = MagicMock()
        mock_fts_engine.search.return_value = (
            [
                {
                    "frame_id": "frame-001",
                    "text": "sample text",
                    "text_source": "ocr",
                    "timestamp": "2026-04-13T10:00:00Z",
                    "frame_url": "/v1/frames/frame-001",
                    "app_name": "Safari",
                    "score": 0.85,
                    "fts_score": 0.85,
                    "fts_rank": 1,
                }
            ],
            1,
        )

        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_fts_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test&mode=fts")

            assert response.status_code == 200
            mock_fts_engine.search.assert_called_once()


class TestSearchAPIIncludeTextVariants:
    """Tests for include_text parameter variants."""

    def test_include_text_1_means_true(self, app_with_search_route):
        """Test that include_text=1 is treated as true."""
        mock_engine = MagicMock()
        mock_engine.search.return_value = (
            [{"frame_id": "f1", "text": "hello", "text_source": "ocr", "timestamp": "2026-04-13T10:00:00Z"}],
            1,
        )

        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test&include_text=1")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert "text" in data["data"][0]

    def test_include_text_yes_means_true(self, app_with_search_route):
        """Test that include_text=yes is treated as true."""
        mock_engine = MagicMock()
        mock_engine.search.return_value = (
            [{"frame_id": "f1", "text": "hello", "text_source": "ocr", "timestamp": "2026-04-13T10:00:00Z"}],
            1,
        )

        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test&include_text=yes")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert "text" in data["data"][0]

    def test_include_text_false_explicit(self, app_with_search_route):
        """Test that include_text=false explicitly hides text."""
        mock_engine = MagicMock()
        mock_engine.search.return_value = (
            [{"frame_id": "f1", "text": "hello", "text_source": "ocr", "timestamp": "2026-04-13T10:00:00Z"}],
            1,
        )

        with patch(
            "openrecall.server.search.hybrid_engine.HybridSearchEngine",
            return_value=mock_engine,
        ):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test&include_text=false")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert "text" not in data["data"][0]
