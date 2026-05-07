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
    for d in data["dates"]:
        assert isinstance(d, str)
        assert len(d) == 10
        assert d.count("-") == 2


def test_memories_by_day_valid_date(flask_client):
    """Returns 200 and list of properly structured frames for valid date."""
    resp = flask_client.get("/api/memories/by-day?date=2026-04-28")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    for item in data:
        assert "frame_id" in item
        assert "timestamp" in item
        assert "visibility_status" in item
        assert "status" in item
        assert "app_name" in item
