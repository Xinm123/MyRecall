from datetime import datetime, timedelta, timezone

import pytest

from openrecall.server import api_v1


def _seconds_ago(seconds: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "should_parse"),
    [
        (_seconds_ago(30).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), True),
        (_seconds_ago(30).isoformat(), True),
        (_seconds_ago(30).strftime("%Y-%m-%d %H:%M:%S"), True),
        (_seconds_ago(30).strftime("%Y-%m-%dT%H:%M:%S.%fZ "), True),
        ("not-a-timestamp", False),
    ],
)
def test_parse_utc_timestamp_normalization(raw: str, should_parse: bool):
    parsed = api_v1._parse_utc_timestamp(raw)
    if should_parse:
        assert parsed is not None
        assert parsed.tzinfo is not None
    else:
        assert parsed is None


@pytest.mark.unit
def test_health_degrades_when_timestamp_unparseable(monkeypatch):
    class _FakeStore:
        @staticmethod
        def get_last_frame_timestamp() -> str | None:
            return None

        @staticmethod
        def get_last_frame_ingested_at() -> str | None:
            return "not-a-timestamp"

        @staticmethod
        def get_queue_counts() -> dict[str, int]:
            return {"pending": 0, "processing": 0, "failed": 0}

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: _FakeStore())

    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    client = app.test_client()

    response = client.get("/v1/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["frame_status"] == "stale"
    assert payload["status"] == "degraded"


@pytest.mark.unit
def test_health_timestamp_fields_format(monkeypatch):
    """last_frame_timestamp is local time (no Z); last_frame_ingested_at is UTC (with Z)."""

    class _FakeStore:
        @staticmethod
        def get_last_frame_timestamp() -> str | None:
            return "2026-04-26T16:30:00.123"  # local time, no Z

        @staticmethod
        def get_last_frame_ingested_at() -> str | None:
            return "2026-04-26T08:30:00.123Z"  # UTC, with Z

        @staticmethod
        def get_queue_counts() -> dict[str, int]:
            return {"pending": 0, "processing": 0, "failed": 0}

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: _FakeStore())

    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    client = app.test_client()

    response = client.get("/v1/health")
    assert response.status_code == 200
    payload = response.get_json()

    # last_frame_timestamp is local time — no Z suffix
    assert payload["last_frame_timestamp"] == "2026-04-26T16:30:00.123"
    assert not payload["last_frame_timestamp"].endswith("Z")

    # last_frame_ingested_at is UTC — has Z suffix
    assert payload["last_frame_ingested_at"] == "2026-04-26T08:30:00.123Z"
    assert payload["last_frame_ingested_at"].endswith("Z")
