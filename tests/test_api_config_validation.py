def test_get_config_includes_client_online(flask_client):
    resp = flask_client.get("/api/config")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "client_online" in data


def test_update_config_rejects_unknown_field(flask_client):
    resp = flask_client.post("/api/config", json={"unknown_field": True})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert "Unknown field" in data["message"]


def test_update_config_rejects_non_boolean(flask_client):
    resp = flask_client.post("/api/config", json={"recording_enabled": "nope"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert "must be boolean" in data["message"]

