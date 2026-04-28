"""Integration tests for grid day view API endpoints."""

import pytest


@pytest.mark.integration
def test_api_by_day_returns_frames(flask_client):
    """The by-day API returns frames for a known date."""
    resp = flask_client.get("/api/memories/by-day?date=2026-04-28")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


@pytest.mark.integration
def test_api_dates_returns_list(flask_client):
    """The dates API returns a dates list."""
    resp = flask_client.get("/api/memories/dates?month=2026-04")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dates" in data
    assert isinstance(data["dates"], list)
