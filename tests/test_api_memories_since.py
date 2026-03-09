from flask import Flask

from openrecall.server import api


def _make_client():
    app = Flask(__name__)
    app.register_blueprint(api.api_bp)
    return app.test_client()


def test_memories_latest_normalizes_unix_since(monkeypatch):
    captured = {}

    def _fake_get_memories_since(since: str):
        captured["since"] = since
        return []

    monkeypatch.setattr(
        api.frames_store, "get_memories_since", _fake_get_memories_since
    )
    client = _make_client()

    response = client.get("/api/memories/latest?since=1741434245")

    assert response.status_code == 200
    assert isinstance(captured["since"], str)
    assert "T" in captured["since"]
    assert captured["since"].endswith("Z")


def test_memories_latest_rejects_invalid_since(monkeypatch):
    def _fake_get_memories_since(_since: str):
        raise AssertionError("should not query DB for invalid since")

    monkeypatch.setattr(
        api.frames_store, "get_memories_since", _fake_get_memories_since
    )
    client = _make_client()

    response = client.get("/api/memories/latest?since=not-a-timestamp")

    assert response.status_code == 400
    body = response.get_json()
    assert body["status"] == "error"
    assert "since" in body["message"]
