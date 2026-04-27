"""Tests for UI filter parameter mapping — P1-S4 UI Filter Verification.

Tests verify that each UI filter parameter maps 1:1 to API request
and is correctly passed to the search engine.

Filter parameters tested:
- Time range (start_time, end_time)
- app_name
- window_name
- focused
- Combined filters

Per tasks.md §4 and specs/fts-search/spec.md.
"""

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

    # Default test results
    # timestamp is local time (from local_timestamp, no Z suffix)
    test_results = [
        {
            "frame_id": 1,
            "timestamp": "2026-03-18T18:00:00.000",
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


class TestTimeRangeFilterMapping:
    """Tests for time range filter parameter mapping."""

    def test_start_time_passed_to_engine(
        self, app_with_search_route, mock_search_engine
    ):
        """start_time parameter is passed to search engine."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&start_time=2026-03-18T09:00:00&mode=fts")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("start_time") == "2026-03-18T09:00:00"

    def test_end_time_passed_to_engine(self, app_with_search_route, mock_search_engine):
        """end_time parameter is passed to search engine."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&end_time=2026-03-18T17:00:00&mode=fts")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("end_time") == "2026-03-18T17:00:00"

    def test_both_time_filters_passed(self, app_with_search_route, mock_search_engine):
        """Both start_time and end_time are passed together."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get(
                "/v1/search?q=&mode=fts&start_time=2026-03-18T09:00:00&end_time=2026-03-18T17:00:00&mode=fts"
            )

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("start_time") == "2026-03-18T09:00:00"
            assert call_args.kwargs.get("end_time") == "2026-03-18T17:00:00"

    def test_time_range_preserves_iso_format(
        self, app_with_search_route, mock_search_engine
    ):
        """Time range filters preserve local time format."""
        local_time = "2026-03-18T10:30:45.123"
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get(f"/v1/search?q=&mode=fts&start_time={local_time}")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("start_time") == local_time


class TestAppNameFilterMapping:
    """Tests for app_name filter parameter mapping."""

    def test_app_name_passed_to_engine(self, app_with_search_route, mock_search_engine):
        """app_name parameter is passed to search engine."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&app_name=Safari")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("app_name") == "Safari"

    def test_app_name_with_spaces(self, app_with_search_route, mock_search_engine):
        """app_name with spaces is correctly parsed."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&app_name=Visual%20Studio%20Code")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("app_name") == "Visual Studio Code"

    def test_app_name_with_special_chars(
        self, app_with_search_route, mock_search_engine
    ):
        """app_name with special characters is preserved."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&app_name=WeChat")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("app_name") == "WeChat"


class TestWindowNameFilterMapping:
    """Tests for window_name filter parameter mapping."""

    def test_window_name_passed_to_engine(
        self, app_with_search_route, mock_search_engine
    ):
        """window_name parameter is passed to search engine."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&window_name=main.py")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("window_name") == "main.py"

    def test_window_name_with_path(self, app_with_search_route, mock_search_engine):
        """window_name containing path is preserved."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&window_name=project%2Fsrc%2Fmain.py")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("window_name") == "project/src/main.py"

    def test_window_name_with_spaces(self, app_with_search_route, mock_search_engine):
        """window_name with spaces is correctly parsed."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&window_name=Google%20Chrome")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("window_name") == "Google Chrome"


class TestFocusedFilterMapping:
    """Tests for focused filter parameter mapping."""

    def test_focused_true_passed_as_bool(
        self, app_with_search_route, mock_search_engine
    ):
        """focused=true is passed as boolean True."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&focused=true")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("focused") is True

    def test_focused_false_passed_as_bool(
        self, app_with_search_route, mock_search_engine
    ):
        """focused=false is passed as boolean False."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&focused=false")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("focused") is False

    def test_focused_case_insensitive(self, app_with_search_route, mock_search_engine):
        """focused parameter is case-insensitive."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&focused=TRUE")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("focused") is True

    def test_focused_1_passed_as_true(self, app_with_search_route, mock_search_engine):
        """focused=1 is passed as boolean True."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&focused=1")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("focused") is True

    def test_focused_0_passed_as_false(self, app_with_search_route, mock_search_engine):
        """focused=0 is passed as boolean False."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&focused=0")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("focused") is False


class TestCombinedFilterMapping:
    """Tests for combined filter parameter mapping."""

    def test_app_name_and_window_name_together(
        self, app_with_search_route, mock_search_engine
    ):
        """app_name and window_name filters work together."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&app_name=VSCode&window_name=main.py")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("app_name") == "VSCode"
            assert call_args.kwargs.get("window_name") == "main.py"

    def test_app_name_and_focused_together(
        self, app_with_search_route, mock_search_engine
    ):
        """app_name and focused filters work together."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&app_name=Safari&focused=true")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("app_name") == "Safari"
            assert call_args.kwargs.get("focused") is True

    def test_time_range_and_app_name_together(
        self, app_with_search_route, mock_search_engine
    ):
        """Time range and app_name filters work together."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get(
                "/v1/search?q=&mode=fts&start_time=2026-03-18T09:00:00"
                "&end_time=2026-03-18T17:00:00&app_name=Terminal"
            )

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("start_time") == "2026-03-18T09:00:00"
            assert call_args.kwargs.get("end_time") == "2026-03-18T17:00:00"
            assert call_args.kwargs.get("app_name") == "Terminal"

    def test_all_filters_together(self, app_with_search_route, mock_search_engine):
        """All filter parameters work together."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get(
                "/v1/search?q=test&mode=fts&start_time=2026-03-18T09:00:00"
                "&end_time=2026-03-18T17:00:00"
                "&app_name=VSCode"
                "&window_name=main.py"
                "&focused=true"
            )

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("start_time") == "2026-03-18T09:00:00"
            assert call_args.kwargs.get("end_time") == "2026-03-18T17:00:00"
            assert call_args.kwargs.get("app_name") == "VSCode"
            assert call_args.kwargs.get("window_name") == "main.py"
            assert call_args.kwargs.get("focused") is True
            # Query should also be passed
            assert call_args.kwargs.get("q") == "test"

    def test_filters_with_pagination(self, app_with_search_route, mock_search_engine):
        """Filters work correctly with pagination parameters."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=&mode=fts&app_name=Safari&limit=10&offset=20")

            call_args = mock_search_engine.search.call_args
            assert call_args.kwargs.get("app_name") == "Safari"
            assert call_args.kwargs.get("limit") == 10
            assert call_args.kwargs.get("offset") == 20

    def test_query_plus_filters_together(
        self, app_with_search_route, mock_search_engine
    ):
        """Query text plus all filters work together."""
        with patch(
            "openrecall.server.api_v1._get_search_engine",
            return_value=mock_search_engine,
        ):
            client = app_with_search_route.test_client()
            client.get(
                "/v1/search?q=error&mode=fts&app_name=Terminal&window_name=bash&focused=false"
                "&start_time=2026-03-18T00:00:00&end_time=2026-03-18T23:59:59"
            )

            call_args = mock_search_engine.search.call_args
            # Query should be passed
            assert call_args.kwargs.get("q") == "error"
            # All filters should be passed
            assert call_args.kwargs.get("app_name") == "Terminal"
            assert call_args.kwargs.get("window_name") == "bash"
            assert call_args.kwargs.get("focused") is False
            assert call_args.kwargs.get("start_time") == "2026-03-18T00:00:00"
            assert call_args.kwargs.get("end_time") == "2026-03-18T23:59:59"
