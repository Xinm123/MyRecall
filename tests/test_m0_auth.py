import json

import pytest

from openrecall.server.utils.auth import (
    AuthForbiddenError,
    AuthUnauthorizedError,
    parse_bearer_token,
    require_device_auth,
)
from openrecall.shared.config import settings


def _configure_auth_settings(
    monkeypatch,
    *,
    auth_mode: str,
    device_tokens_json: str,
    legacy_device_id: str,
) -> None:
    monkeypatch.setenv("OPENRECALL_AUTH_MODE", auth_mode)
    monkeypatch.setenv("OPENRECALL_DEVICE_TOKENS_JSON", device_tokens_json)
    monkeypatch.setenv("OPENRECALL_LEGACY_DEVICE_ID", legacy_device_id)
    monkeypatch.setattr(settings, "auth_mode", auth_mode, raising=False)
    monkeypatch.setattr(
        settings, "device_tokens_json", device_tokens_json, raising=False
    )
    monkeypatch.setattr(settings, "legacy_device_id", legacy_device_id, raising=False)


def test_parse_bearer_token_extracts_token():
    assert parse_bearer_token("Bearer abc123") == "abc123"


def test_parse_bearer_token_returns_none_for_invalid():
    assert parse_bearer_token(None) is None
    assert parse_bearer_token("Basic abc123") is None
    assert parse_bearer_token("") is None


def test_auth_missing_header_returns_401(monkeypatch):
    tokens = json.dumps({"device-a": {"active_token": "token-a"}})
    _configure_auth_settings(
        monkeypatch,
        auth_mode="strict",
        device_tokens_json=tokens,
        legacy_device_id="legacy-1",
    )

    with pytest.raises(AuthUnauthorizedError) as excinfo:
        require_device_auth(None)

    assert excinfo.value.status_code == 401


def test_auth_token_device_mismatch_returns_403(monkeypatch):
    tokens = json.dumps({"device-a": {"active_token": "token-a"}})
    _configure_auth_settings(
        monkeypatch,
        auth_mode="strict",
        device_tokens_json=tokens,
        legacy_device_id="legacy-1",
    )

    with pytest.raises(AuthForbiddenError) as excinfo:
        require_device_auth("Bearer token-a", requested_device_id="device-b")

    assert excinfo.value.status_code == 403


def test_auth_permissive_mode_allows_no_token(monkeypatch):
    tokens = json.dumps({"device-a": {"active_token": "token-a"}})
    _configure_auth_settings(
        monkeypatch,
        auth_mode="permissive",
        device_tokens_json=tokens,
        legacy_device_id="legacy-1",
    )

    device_id, auth_mode = require_device_auth(None)

    assert device_id == "legacy-1"
    assert auth_mode == "permissive"


def test_auth_disabled_mode_skips_validation(monkeypatch):
    tokens = json.dumps({"device-a": {"active_token": "token-a"}})
    _configure_auth_settings(
        monkeypatch,
        auth_mode="disabled",
        device_tokens_json=tokens,
        legacy_device_id="legacy-1",
    )

    device_id, auth_mode = require_device_auth(None, requested_device_id="device-b")

    assert device_id == "device-b"
    assert auth_mode == "disabled"
