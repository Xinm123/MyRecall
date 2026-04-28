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
