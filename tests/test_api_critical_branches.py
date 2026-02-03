import numpy as np


def test_queue_status_success(flask_client):
    resp = flask_client.get("/api/queue/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "queue" in data
    assert "config" in data


def test_queue_status_exception_returns_500(flask_client, monkeypatch):
    import sqlite3
    def boom(*args, **kwargs):
        raise sqlite3.Error("boom")
    monkeypatch.setattr(sqlite3, "connect", boom)
    resp = flask_client.get("/api/queue/status")
    assert resp.status_code == 500


def test_upload_no_json_returns_400(flask_client):
    resp = flask_client.post("/api/upload", data="{}", content_type="application/json")
    assert resp.status_code == 400


def test_upload_duplicate_timestamp_returns_409(flask_client):
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    payload = {
        "image": image.flatten().tolist(),
        "shape": list(image.shape),
        "dtype": "uint8",
        "timestamp": 1700000000,
        "active_app": "App",
        "active_window": "Win",
    }
    resp1 = flask_client.post("/api/upload", json=payload)
    assert resp1.status_code == 202
    resp2 = flask_client.post("/api/upload", json=payload)
    assert resp2.status_code == 409


def test_upload_bad_shape_returns_500(flask_client):
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    payload = {
        "image": image.flatten().tolist(),
        "shape": [999, 999, 3],
        "dtype": "uint8",
        "timestamp": 1700000001,
        "active_app": "App",
        "active_window": "Win",
    }
    resp = flask_client.post("/api/upload", json=payload)
    assert resp.status_code == 500


def test_update_config_invalid_json_payload(flask_client):
    resp = flask_client.post("/api/config", data="[]", content_type="application/json")
    assert resp.status_code == 400


def test_update_config_exception_returns_500(flask_client, monkeypatch):
    import openrecall.server.api as api

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(api.runtime_settings, "to_dict", boom)
    resp = flask_client.post("/api/config", json={"recording_enabled": True})
    assert resp.status_code == 500


def test_heartbeat_exception_returns_500(flask_client, monkeypatch):
    import openrecall.server.api as api

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(api.runtime_settings, "to_dict", boom)
    resp = flask_client.post("/api/heartbeat")
    assert resp.status_code == 500
