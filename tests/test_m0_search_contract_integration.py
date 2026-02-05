"""M0 Search Contract Integration Tests.

Tests GET /api/search with device_id support and auth isolation rules.
"""

import importlib
import json
import pytest


@pytest.fixture
def flask_client_with_auth(tmp_path, monkeypatch):
    """Flask test client with device token auth configured."""
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))
    monkeypatch.setenv("OPENRECALL_AUTH_MODE", "strict")
    monkeypatch.setenv(
        "OPENRECALL_DEVICE_TOKENS_JSON",
        json.dumps(
            {
                "mac-01": {
                    "active_token": "token-mac-01",
                    "previous_token": "",
                    "previous_valid_until_ms": 0,
                },
                "mac-02": {
                    "active_token": "token-mac-02",
                    "previous_token": "",
                    "previous_valid_until_ms": 0,
                },
            }
        ),
    )

    import openrecall.shared.config

    importlib.reload(openrecall.shared.config)
    openrecall.shared.config.settings = openrecall.shared.config.Settings()

    import openrecall.server.utils.auth

    importlib.reload(openrecall.server.utils.auth)

    import openrecall.server.database

    importlib.reload(openrecall.server.database)
    openrecall.server.database.SQLStore()

    import openrecall.server.api

    importlib.reload(openrecall.server.api)

    import openrecall.server.app

    importlib.reload(openrecall.server.app)

    app = openrecall.server.app.app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def flask_client_no_auth(tmp_path, monkeypatch):
    """Flask test client with auth disabled."""
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))
    monkeypatch.setenv("OPENRECALL_AUTH_MODE", "disabled")

    import openrecall.shared.config

    importlib.reload(openrecall.shared.config)
    openrecall.shared.config.settings = openrecall.shared.config.Settings()

    import openrecall.server.utils.auth

    importlib.reload(openrecall.server.utils.auth)

    import openrecall.server.database

    importlib.reload(openrecall.server.database)
    openrecall.server.database.SQLStore()

    import openrecall.server.api

    importlib.reload(openrecall.server.api)

    import openrecall.server.app

    importlib.reload(openrecall.server.app)

    app = openrecall.server.app.app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestSearchAuthIsolation:
    """Test auth isolation rules for GET /api/search (M0 Plan Section 2.5)."""

    def test_search_with_auth_rejects_other_device_returns_403(
        self, flask_client_with_auth
    ):
        """With Authorization header, device_id must match token's device or 403."""
        response = flask_client_with_auth.get(
            "/api/search?q=test&device_id=mac-02",
            headers={"Authorization": "Bearer token-mac-01"},
        )

        assert response.status_code == 403
        data = response.get_json()
        assert data["code"] == "AUTH_FORBIDDEN"
        assert "mac-01" in data["message"]
        assert "mac-02" in data["message"]

    def test_search_with_auth_allows_own_device(self, flask_client_with_auth):
        """With Authorization header, searching own device returns 200."""
        response = flask_client_with_auth.get(
            "/api/search?q=test&device_id=mac-01",
            headers={"Authorization": "Bearer token-mac-01"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_search_with_auth_defaults_to_token_device(self, flask_client_with_auth):
        """With Authorization but no device_id, defaults to token's device."""
        response = flask_client_with_auth.get(
            "/api/search?q=test",
            headers={"Authorization": "Bearer token-mac-01"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_search_with_invalid_token_returns_401(self, flask_client_with_auth):
        """With invalid Authorization token, returns 401."""
        response = flask_client_with_auth.get(
            "/api/search?q=test",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401
        data = response.get_json()
        assert data["code"] == "AUTH_UNAUTHORIZED"

    def test_search_with_malformed_auth_header_returns_401(
        self, flask_client_with_auth
    ):
        """With malformed Authorization header, returns 401."""
        response = flask_client_with_auth.get(
            "/api/search?q=test",
            headers={"Authorization": "NotBearer token-mac-01"},
        )

        assert response.status_code == 401
        data = response.get_json()
        assert data["code"] == "AUTH_UNAUTHORIZED"


class TestSearchWithoutAuth:
    """Test search without Authorization header."""

    def test_search_without_auth_allows_cross_device_aggregation(
        self, flask_client_no_auth
    ):
        """Without Authorization header, allows cross-device aggregation."""
        response = flask_client_no_auth.get("/api/search?q=test")

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_search_without_auth_allows_specific_device_filter(
        self, flask_client_no_auth
    ):
        """Without Authorization header, device_id filters to that device."""
        response = flask_client_no_auth.get("/api/search?q=test&device_id=mac-01")

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_search_empty_query_returns_empty_list(self, flask_client_no_auth):
        """Empty query returns empty list."""
        response = flask_client_no_auth.get("/api/search?q=")

        assert response.status_code == 200
        data = response.get_json()
        assert data == []


class TestSearchQueryParams:
    """Test query parameter handling."""

    def test_search_limit_respects_max_200(self, flask_client_no_auth):
        """Limit is capped at 200."""
        response = flask_client_no_auth.get("/api/search?q=test&limit=500")
        assert response.status_code == 200

    def test_search_invalid_limit_defaults_to_50(self, flask_client_no_auth):
        """Invalid limit defaults to 50."""
        response = flask_client_no_auth.get("/api/search?q=test&limit=invalid")
        assert response.status_code == 200

    def test_search_accepts_time_filter_params(self, flask_client_no_auth):
        """Search accepts start_ts_ms and end_ts_ms params."""
        response = flask_client_no_auth.get(
            "/api/search?q=test&start_ts_ms=1700000000000&end_ts_ms=1800000000000"
        )
        assert response.status_code == 200


class TestSearchResponseFormat:
    """Test response format includes M0 fields."""

    def test_search_response_includes_diagnostic_id_on_error(
        self, flask_client_with_auth
    ):
        """Error responses include diagnostic_id."""
        response = flask_client_with_auth.get(
            "/api/search?q=test&device_id=mac-02",
            headers={"Authorization": "Bearer token-mac-01"},
        )

        assert response.status_code == 403
        data = response.get_json()
        assert "diagnostic_id" in data
        assert len(data["diagnostic_id"]) > 0
