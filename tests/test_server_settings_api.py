"""Integration tests for /v1/settings/description endpoints."""
import json
import pytest
from unittest.mock import patch, MagicMock

from openrecall.server.config_runtime import runtime_settings
from openrecall.server.ai import factory


class TestServerSettingsAPI:
    @pytest.fixture
    def client(self, tmp_path):
        """Test client + isolated runtime_config + clean factory cache + version restore."""
        from openrecall.server.app import app
        from openrecall.server.runtime_config import init_runtime_config
        from openrecall.server.config_server import ServerSettings

        app.config["TESTING"] = True

        saved_version = runtime_settings.ai_processing_version
        import openrecall.server.runtime_config as rc
        rc._settings_store = None
        rc._toml_settings = None
        factory.invalidate()

        with app.test_client() as client:
            toml = ServerSettings(
                description_provider="local",
                description_model="",
                description_api_key="",
                description_api_base="",
                description_request_timeout=120,
            )
            init_runtime_config(tmp_path, toml)
            yield client

        factory.invalidate()
        rc._settings_store = None
        rc._toml_settings = None
        with runtime_settings._lock:
            runtime_settings.ai_processing_version = saved_version

    @pytest.fixture
    def client_with_toml_overrides(self, tmp_path):
        """Variant fixture: TOML differs from DEFAULTS so source='toml' is observable."""
        from openrecall.server.app import app
        from openrecall.server.runtime_config import init_runtime_config
        from openrecall.server.config_server import ServerSettings

        app.config["TESTING"] = True
        saved_version = runtime_settings.ai_processing_version
        import openrecall.server.runtime_config as rc
        rc._settings_store = None
        rc._toml_settings = None
        factory.invalidate()

        with app.test_client() as client:
            toml = ServerSettings(
                description_provider="dashscope",
                description_model="qwen-vl-max",
                description_api_key="",
                description_api_base="",
                description_request_timeout=120,
            )
            init_runtime_config(tmp_path, toml)
            yield client

        factory.invalidate()
        rc._settings_store = None
        rc._toml_settings = None
        with runtime_settings._lock:
            runtime_settings.ai_processing_version = saved_version

    # ---------- GET ----------

    def test_get_default_settings(self, client):
        """GET with no SQLite + TOML matching DEFAULTS: source=default everywhere."""
        resp = client.get("/v1/settings/description")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "local"
        assert data["api_key_masked"] == ""
        assert data["source"]["provider"] == "default"
        assert data["source"]["model"] == "default"

    def test_get_returns_toml_source_when_toml_differs_from_defaults(
        self, client_with_toml_overrides
    ):
        """GET when TOML differs from DEFAULTS: source=toml for those fields."""
        resp = client_with_toml_overrides.get("/v1/settings/description")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "dashscope"
        assert data["source"]["provider"] == "toml"
        assert data["model"] == "qwen-vl-max"
        assert data["source"]["model"] == "toml"

    # ---------- POST update ----------

    def test_post_update_provider(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "openai"
        assert data["source"]["provider"] == "sqlite"

    def test_post_full_payload_updates_all_fields(self, client):
        """Full POST containing all 5 fields applies all of them."""
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "sk-1234567890XX12",
                "api_base": "https://api.openai.com/v1",
                "request_timeout": 60,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o"
        assert data["api_key_masked"] == "sk-***XX12"
        assert data["api_base"] == "https://api.openai.com/v1"
        assert data["request_timeout"] == 60
        assert data["source"]["provider"] == "sqlite"
        assert data["source"]["model"] == "sqlite"
        assert data["source"]["api_key"] == "sqlite"
        assert data["source"]["api_base"] == "sqlite"
        assert data["source"]["request_timeout"] == "sqlite"

    def test_post_invalid_provider_returns_400(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "invalid"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "provider" in data.get("details", {})

    def test_post_timeout_out_of_range_returns_400(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"request_timeout": 9999}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "request_timeout" in resp.get_json().get("details", {})

    def test_post_api_base_not_http_returns_400(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"api_base": "ftp://example.com"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "api_base" in resp.get_json().get("details", {})

    def test_post_empty_body_no_op(self, client):
        old_version = runtime_settings.ai_processing_version
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert runtime_settings.ai_processing_version == old_version

    def test_post_api_key_null_deletes(self, client):
        client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": "sk-1234567890XX12"}),
            content_type="application/json",
        )
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": None}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["api_key_masked"] == ""

    def test_post_api_key_empty_rejected(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_post_missing_api_key_preserves_existing(self, client):
        """POST without api_key field -> existing key preserved."""
        client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": "sk-1234567890XX12"}),
            content_type="application/json",
        )
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai", "model": "gpt-4o"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        get_resp = client.get("/v1/settings/description")
        assert get_resp.get_json()["api_key_masked"] == "sk-***XX12"

    def test_post_bumps_version_only_on_change(self, client):
        old_version = runtime_settings.ai_processing_version
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "local"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert runtime_settings.ai_processing_version == old_version

    def test_post_invalidates_factory_cache_on_change(self, client):
        factory._instances["description"] = "fake_provider_instance"
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert "description" not in factory._instances

    def test_post_no_factory_invalidate_on_no_op(self, client):
        factory._instances["description"] = "fake_provider_instance"
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "local"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert factory._instances.get("description") == "fake_provider_instance"

    def test_post_sqlite_failure_returns_500(self, client):
        from openrecall.server import runtime_config as rc

        before = client.get("/v1/settings/description").get_json()

        with patch.object(
            rc._settings_store, "apply_changes", side_effect=RuntimeError("db locked")
        ):
            resp = client.post(
                "/v1/settings/description",
                data=json.dumps({"provider": "openai"}),
                content_type="application/json",
            )
        assert resp.status_code == 500
        assert resp.get_json().get("code") == "internal_error"

        after = client.get("/v1/settings/description").get_json()
        assert after["provider"] == before["provider"]
        assert after["source"]["provider"] == before["source"]["provider"]

    # ---------- Reset ----------

    def test_reset_deletes_sqlite_rows(self, client):
        client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai"}),
            content_type="application/json",
        )
        resp = client.post("/v1/settings/description/reset")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "local"
        assert data["source"]["provider"] == "default"

    def test_reset_no_op_does_not_bump_version(self, client):
        old_version = runtime_settings.ai_processing_version
        resp = client.post("/v1/settings/description/reset")
        assert resp.status_code == 200
        assert runtime_settings.ai_processing_version == old_version

    def test_reset_bumps_version_when_changes_effective(self, client):
        client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai"}),
            content_type="application/json",
        )
        version_after_post = runtime_settings.ai_processing_version
        resp = client.post("/v1/settings/description/reset")
        assert resp.status_code == 200
        assert runtime_settings.ai_processing_version > version_after_post

    # ---------- Test endpoint ----------

    def test_test_endpoint_does_not_write(self, client):
        with patch("openrecall.server.api_v1._probe_provider") as mock_probe:
            mock_probe.return_value = {"ok": True, "latency_ms": 100, "detail": "ok"}
            resp = client.post(
                "/v1/settings/description/test",
                data=json.dumps({
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "request_timeout": 30,
                }),
                content_type="application/json",
            )
        assert resp.status_code == 200
        get_resp = client.get("/v1/settings/description")
        assert get_resp.get_json()["provider"] == "local"

    def test_test_endpoint_success(self, client):
        """Successful probe -> 200 + ok:true + latency_ms + detail."""
        with patch("openrecall.server.api_v1.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_get.return_value = mock_resp
            resp = client.post(
                "/v1/settings/description/test",
                data=json.dumps({
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_key": "sk-test1234567890",
                    "api_base": "https://api.openai.com/v1",
                    "request_timeout": 30,
                }),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "latency_ms" in data
        assert "detail" in data

    def test_test_endpoint_returns_ok_false_on_401(self, client):
        """Provider returns 401 -> 200 + ok:false + error."""
        with patch("openrecall.server.api_v1.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.reason = "Unauthorized"
            mock_get.return_value = mock_resp
            resp = client.post(
                "/v1/settings/description/test",
                data=json.dumps({
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_key": "sk-bad",
                    "api_base": "https://api.openai.com/v1",
                    "request_timeout": 30,
                }),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is False
        assert "401" in data.get("error", "")

    def test_test_endpoint_returns_ok_false_on_network_error(self, client):
        """Network timeout -> 200 + ok:false + error."""
        import requests as _requests

        with patch(
            "openrecall.server.api_v1.requests.get",
            side_effect=_requests.exceptions.Timeout("read timeout"),
        ):
            resp = client.post(
                "/v1/settings/description/test",
                data=json.dumps({
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "request_timeout": 30,
                }),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is False
        assert "timeout" in data.get("error", "").lower()

    def test_test_endpoint_uses_runtime_api_key_when_omitted(self, client):
        """If api_key is omitted in the test payload, runtime_config value is used."""
        client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": "sk-1234567890XX12"}),
            content_type="application/json",
        )
        captured = {}

        def fake_get(url, headers=None, timeout=None):
            captured["headers"] = headers or {}
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            return mock_resp

        with patch("openrecall.server.api_v1.requests.get", side_effect=fake_get):
            resp = client.post(
                "/v1/settings/description/test",
                data=json.dumps({
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "request_timeout": 30,
                }),
                content_type="application/json",
            )
        assert resp.status_code == 200
        assert captured["headers"].get("Authorization") == "Bearer sk-1234567890XX12"

    # ---------- Misc ----------

    def test_api_key_masking(self, client):
        client.post(
            "/v1/settings/description",
            data=json.dumps({"api_key": "sk-1234567890XX12"}),
            content_type="application/json",
        )
        resp = client.get("/v1/settings/description")
        data = resp.get_json()
        assert data["api_key_masked"] == "sk-***XX12"
        assert "api_key" not in data

    def test_post_unknown_keys_ignored(self, client):
        resp = client.post(
            "/v1/settings/description",
            data=json.dumps({"provider": "openai", "unknown_field": "value"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
