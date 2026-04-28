import pytest


def test_memories_by_day_missing_param(flask_client):
    """Returns 400 when date param is missing."""
    resp = flask_client.get("/api/memories/by-day")
    assert resp.status_code == 400
    assert "date" in resp.get_json()["message"].lower()


def test_memories_by_day_invalid_format(flask_client):
    """Returns 400 when date format is invalid."""
    resp = flask_client.get("/api/memories/by-day?date=bad-date")
    assert resp.status_code == 400
    assert "YYYY-MM-DD" in resp.get_json()["message"]


def test_memories_dates_missing_param(flask_client):
    """Returns 400 when month param is missing."""
    resp = flask_client.get("/api/memories/dates")
    assert resp.status_code == 400
    assert "month" in resp.get_json()["message"].lower()


def test_memories_dates_invalid_format(flask_client):
    """Returns 400 when month format is invalid."""
    resp = flask_client.get("/api/memories/dates?month=bad")
    assert resp.status_code == 400
    assert "YYYY-MM" in resp.get_json()["message"]


def test_memories_dates_returns_dates(flask_client):
    """Returns list of dates for a month."""
    resp = flask_client.get("/api/memories/dates?month=2026-04")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dates" in data
    assert isinstance(data["dates"], list)
