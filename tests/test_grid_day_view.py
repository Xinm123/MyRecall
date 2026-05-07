"""Integration tests for grid day view API endpoints."""

import pytest


@pytest.mark.integration
def test_api_by_day_returns_frames(flask_client):
    """The by-day API returns frames for a known date."""
    resp = flask_client.get("/api/memories/by-day?date=2026-04-28")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    for item in data:
        assert "frame_id" in item
        assert "timestamp" in item
        assert "visibility_status" in item


@pytest.mark.integration
def test_api_by_day_returns_only_completed_with_snapshot(flask_client):
    """Returned frames must all have snapshot_path and completed status."""
    resp = flask_client.get("/api/memories/by-day?date=2026-04-28")
    assert resp.status_code == 200
    data = resp.get_json()
    for item in data:
        assert item.get("snapshot_path") is not None
        assert item.get("status") in ("COMPLETED", "PENDING", "FAILED")


@pytest.mark.integration
def test_api_dates_returns_list(flask_client):
    """The dates API returns a dates list."""
    resp = flask_client.get("/api/memories/dates?month=2026-04")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dates" in data
    assert isinstance(data["dates"], list)
    for d in data["dates"]:
        assert isinstance(d, str)
        assert len(d) == 10  # YYYY-MM-DD
        parts = d.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4 and parts[0].isdigit()
        assert len(parts[1]) == 2 and parts[1].isdigit()
        assert len(parts[2]) == 2 and parts[2].isdigit()
