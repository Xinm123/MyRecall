import time

import openrecall.server.utils.auth as auth
import openrecall.shared.config as config
from openrecall.shared.contract_m0 import DRIFT_THRESHOLD_MS


def _heartbeat_payload(client_ts: int) -> dict:
    return {
        "device_id": "device-a",
        "client_ts": client_ts,
        "client_tz": "UTC",
        "queue_depth": 0,
        "capabilities": {
            "client_version": "0.1.0",
            "platform": "darwin",
            "capture": {},
            "upload": {},
        },
    }


def test_heartbeat_returns_server_time_and_drift(flask_client, monkeypatch):
    monkeypatch.setattr(config.settings, "auth_mode", "disabled", raising=False)
    monkeypatch.setattr(auth.settings, "auth_mode", "disabled", raising=False)
    client_ts = int(time.time() * 1000)
    payload = _heartbeat_payload(client_ts)

    resp = flask_client.post("/api/heartbeat", json=payload)

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["server_time_ms"], int)
    drift = data["drift_ms"]
    assert isinstance(drift["estimate"], int)
    assert drift["threshold"] == DRIFT_THRESHOLD_MS
    assert abs(drift["estimate"]) <= DRIFT_THRESHOLD_MS


def test_heartbeat_legacy_no_body_still_works(flask_client, monkeypatch):
    monkeypatch.setattr(config.settings, "auth_mode", "permissive", raising=False)
    monkeypatch.setattr(auth.settings, "auth_mode", "permissive", raising=False)

    resp = flask_client.post("/api/heartbeat")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "config" in data


def test_heartbeat_large_drift_sets_exceeded_true(flask_client, monkeypatch):
    monkeypatch.setattr(config.settings, "auth_mode", "disabled", raising=False)
    monkeypatch.setattr(auth.settings, "auth_mode", "disabled", raising=False)
    client_ts = int(time.time() * 1000) - (DRIFT_THRESHOLD_MS + 10000)
    payload = _heartbeat_payload(client_ts)

    resp = flask_client.post("/api/heartbeat", json=payload)

    assert resp.status_code == 200
    data = resp.get_json()
    drift = data["drift_ms"]
    assert drift["exceeded"] is True


def test_heartbeat_auth_required_in_strict_mode(flask_client, monkeypatch):
    monkeypatch.setattr(config.settings, "auth_mode", "strict", raising=False)
    monkeypatch.setattr(auth.settings, "auth_mode", "strict", raising=False)
    payload = _heartbeat_payload(int(time.time() * 1000))

    resp = flask_client.post("/api/heartbeat", json=payload)

    assert resp.status_code == 401
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["code"] == "AUTH_UNAUTHORIZED"
    assert "diagnostic_id" in data
