from flask import Flask

from openrecall.server import api_v1


def _make_client():
    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    return app.test_client()


class _FakeStore:
    """Fake FramesStore for testing."""

    def __init__(self, memories_result=None):
        self._memories = memories_result or []
        self.captured_since = None

    def get_memories_since(self, since: str):
        self.captured_since = since
        return list(self._memories)


def test_frames_latest_passes_local_since(monkeypatch):
    """V1 endpoint passes since parameter directly as local time (no Z suffix)."""
    fake_store = _FakeStore()

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: fake_store)
    client = _make_client()

    # Local timestamp without Z suffix
    response = client.get("/v1/frames/latest?since=2026-04-26T16:30:00.123")

    assert response.status_code == 200
    assert isinstance(fake_store.captured_since, str)
    assert "T" in fake_store.captured_since
    # since is now local time — no Z suffix
    assert not fake_store.captured_since.endswith("Z")


def test_frames_latest_response_timestamp_is_local(monkeypatch):
    """Response timestamp fields have no Z suffix (local time)."""
    fake_store = _FakeStore(memories_result=[
        {
            "id": "frame-1",
            "timestamp": "2026-04-26T16:30:00.123",  # local time, no Z
            "app_name": "TestApp",
        }
    ])

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: fake_store)
    client = _make_client()

    response = client.get("/v1/frames/latest?since=2026-04-26T00:00:00")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 1
    assert body[0]["timestamp"] == "2026-04-26T16:30:00.123"
    assert not body[0]["timestamp"].endswith("Z")


def test_frames_latest_uses_default_since(monkeypatch):
    """Default since is epoch start in local time format."""
    fake_store = _FakeStore()

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: fake_store)
    client = _make_client()

    response = client.get("/v1/frames/latest")

    assert response.status_code == 200
    # Default since is "1970-01-01T00:00:00" (local time, no Z)
    assert fake_store.captured_since == "1970-01-01T00:00:00"
    assert not fake_store.captured_since.endswith("Z")
