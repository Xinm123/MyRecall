"""Tests for GET /v1/search/counts API endpoint.

Tests cover:
- Basic endpoint functionality
- Parameter parsing
- Edge cases and error handling
- Integration with real SearchEngine and database
"""

import json
import sqlite3
from pathlib import Path
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
            client.get("/v1/search/counts?q=test&start_time=2026-03-18T10:00:00&end_time=2026-03-18T11:00:00")

            call_args = mock_search_engine.count_by_type.call_args
            assert call_args.kwargs.get("start_time") == "2026-03-18T10:00:00"
            assert call_args.kwargs.get("end_time") == "2026-03-18T11:00:00"

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


# ---------------------------------------------------------------------------
# Integration tests: real SearchEngine with real database
# ---------------------------------------------------------------------------

@pytest.fixture
def integration_test_db(tmp_path):
    """Create a test database with frames, full_text, and frames_fts via migrations."""
    db_path = tmp_path / "integration_test.db"

    with sqlite3.connect(str(db_path)) as conn:
        # Run initial schema
        init_sql = Path("openrecall/server/database/migrations/20260227000001_initial_schema.sql").read_text()
        conn.executescript(init_sql)

        # Run intermediate migrations
        for mig in [
            "20260310121000_add_event_ts_to_frames.sql",
            "20260315140000_add_last_known_context_to_frames.sql",
            "20260317000001_ocr_text_unique_frame_id.sql",
            "20260321120000_dual_hash_storage.sql",
            "20260324120000_add_frame_description.sql",
            "20260325120000_consolidate_fts_to_full_text.sql",
            "20260408120000_description_fields_redesign.sql",
            "20260409120000_add_frame_embedding.sql",
            "20260414000000_add_visibility_status.sql",
            "20260426000000_add_local_timestamp.sql",
        ]:
            mig_sql = Path(f"openrecall/server/database/migrations/{mig}").read_text()
            conn.executescript(mig_sql)

        conn.commit()

    return db_path


@pytest.fixture
def app_with_real_engine(integration_test_db):
    """Flask app with a real SearchEngine backed by integration_test_db."""
    engine = SearchEngine(db_path=integration_test_db)

    app = Flask(__name__)
    app.register_blueprint(v1_bp)

    original_engine = None
    _api_v1 = None
    try:
        import openrecall.server.api_v1 as _api_v1
        original_engine = _api_v1._search_engine
        _api_v1._search_engine = engine
        yield app
    finally:
        if _api_v1 is not None and original_engine is not None:
            _api_v1._search_engine = original_engine


class TestSearchCountsIntegration:
    """Integration tests for GET /v1/search/counts with real database."""

    def _insert_ocr_frame(self, conn, text, app_name, timestamp):
        """Insert a completed OCR frame with full_text and frames_fts.

        After FTS unification: full_text is set on frames, triggering frames_ai → frames_fts.
        timestamp is UTC, local_timestamp is local time (UTC+8).
        """
        # Compute local_timestamp from UTC timestamp (UTC+8)
        from openrecall.server.database.frames_store import _utc_to_local_timestamp
        local_ts = _utc_to_local_timestamp(timestamp)
        cursor = conn.execute(
            """INSERT INTO frames (capture_id, timestamp, local_timestamp, app_name, text_source, status, full_text, visibility_status)
               VALUES (?, ?, ?, ?, 'ocr', 'completed', ?, 'queryable')""",
            (f"cap-ocr-{timestamp}", timestamp, local_ts, app_name, text),
        )
        return cursor.lastrowid

    def _insert_ax_frame(self, conn, text, app_name, timestamp):
        """Insert a completed accessibility frame with full_text and frames_fts.

        After FTS unification: full_text is set on frames, triggering frames_ai → frames_fts.
        timestamp is UTC, local_timestamp is local time (UTC+8).
        """
        from openrecall.server.database.frames_store import _utc_to_local_timestamp
        local_ts = _utc_to_local_timestamp(timestamp)
        cursor = conn.execute(
            """INSERT INTO frames (capture_id, timestamp, local_timestamp, app_name, text_source, status, full_text, visibility_status)
               VALUES (?, ?, ?, ?, 'accessibility', 'completed', ?, 'queryable')""",
            (f"cap-ax-{timestamp}", timestamp, local_ts, app_name, text),
        )
        return cursor.lastrowid

    def test_returns_correct_counts_for_ocr_frames(self, app_with_real_engine, integration_test_db):
        """Integration: /v1/search/counts with q=python returns correct OCR count."""
        with sqlite3.connect(str(integration_test_db)) as conn:
            self._insert_ocr_frame(conn, "python is great", "Safari", "2024-01-01T00:00:00Z")
            self._insert_ocr_frame(conn, "python tutorial", "Chrome", "2024-01-01T00:00:01Z")
            self._insert_ax_frame(conn, "rust programming", "Terminal", "2024-01-01T00:00:02Z")
            conn.commit()

        client = app_with_real_engine.test_client()
        response = client.get("/v1/search/counts?q=python")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["counts"]["ocr"] == 2
        assert data["counts"]["accessibility"] == 0

    def test_returns_correct_counts_for_accessibility_frames(self, app_with_real_engine, integration_test_db):
        """Integration: /v1/search/counts returns correct accessibility count."""
        with sqlite3.connect(str(integration_test_db)) as conn:
            self._insert_ocr_frame(conn, "javascript code", "VSCode", "2024-01-01T00:00:00Z")
            self._insert_ax_frame(conn, "swift programming", "Xcode", "2024-01-01T00:00:01Z")
            self._insert_ax_frame(conn, "swift language basics", "Xcode", "2024-01-01T00:00:02Z")
            self._insert_ax_frame(conn, "swift tutorial overview", "Safari", "2024-01-01T00:00:03Z")
            conn.commit()

        client = app_with_real_engine.test_client()
        response = client.get("/v1/search/counts?q=swift")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["counts"]["ocr"] == 0
        assert data["counts"]["accessibility"] == 3

    def test_returns_correct_counts_for_both_types(self, app_with_real_engine, integration_test_db):
        """Integration: /v1/search/counts returns correct counts for both types."""
        with sqlite3.connect(str(integration_test_db)) as conn:
            self._insert_ocr_frame(conn, "golang concurrency", "Terminal", "2024-01-01T00:00:00Z")
            self._insert_ax_frame(conn, "golang channels", "Terminal", "2024-01-01T00:00:01Z")
            conn.commit()

        client = app_with_real_engine.test_client()
        response = client.get("/v1/search/counts?q=golang")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["counts"]["ocr"] == 1
        assert data["counts"]["accessibility"] == 1

    def test_returns_zeros_for_empty_database(self, app_with_real_engine):
        """Integration: /v1/search/counts returns zeros on empty database."""
        client = app_with_real_engine.test_client()
        response = client.get("/v1/search/counts?q=python")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["counts"]["ocr"] == 0
        assert data["counts"]["accessibility"] == 0

    def test_returns_zeros_for_no_matching_query(self, app_with_real_engine, integration_test_db):
        """Integration: /v1/search/counts returns zeros when no frames match."""
        with sqlite3.connect(str(integration_test_db)) as conn:
            self._insert_ocr_frame(conn, "python code", "Safari", "2024-01-01T00:00:00Z")
            conn.commit()

        client = app_with_real_engine.test_client()
        response = client.get("/v1/search/counts?q=rust")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["counts"]["ocr"] == 0
        assert data["counts"]["accessibility"] == 0

    def test_empty_query_returns_all_counts(self, app_with_real_engine, integration_test_db):
        """Integration: /v1/search/counts with no q returns counts for all frames."""
        with sqlite3.connect(str(integration_test_db)) as conn:
            self._insert_ocr_frame(conn, "any text", "Safari", "2024-01-01T00:00:00Z")
            self._insert_ocr_frame(conn, "other text", "Chrome", "2024-01-01T00:00:01Z")
            self._insert_ax_frame(conn, "ax text", "Xcode", "2024-01-01T00:00:02Z")
            conn.commit()

        client = app_with_real_engine.test_client()
        response = client.get("/v1/search/counts")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["counts"]["ocr"] == 2
        assert data["counts"]["accessibility"] == 1

    def test_app_name_filter_affects_counts(self, app_with_real_engine, integration_test_db):
        """Integration: /v1/search/counts respects app_name filter."""
        with sqlite3.connect(str(integration_test_db)) as conn:
            self._insert_ocr_frame(conn, "python code", "Safari", "2024-01-01T00:00:00Z")
            self._insert_ocr_frame(conn, "python code", "Chrome", "2024-01-01T00:00:01Z")
            conn.commit()

        client = app_with_real_engine.test_client()
        response = client.get("/v1/search/counts?q=python&app_name=Safari")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["counts"]["ocr"] == 1
        assert data["counts"]["accessibility"] == 0
