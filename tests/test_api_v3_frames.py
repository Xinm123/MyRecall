"""Tests for GET /api/v3/frames endpoint with pagination."""

import time
import pytest


class TestV3FramesEmpty:
    """Test frames endpoint with empty database."""

    def test_empty_db_returns_empty_items(self, flask_client):
        """Empty database should return empty items list."""
        resp = flask_client.get("/api/v3/frames")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["items"] == []
        assert data["next_before"] is None

    def test_empty_db_returns_server_time(self, flask_client):
        """Response should include server_time for sync."""
        resp = flask_client.get("/api/v3/frames")
        data = resp.get_json()
        assert "server_time" in data
        assert isinstance(data["server_time"], int)
        assert data["server_time"] > 0


class TestV3FramesWithData:
    """Test frames endpoint with seeded data."""

    @pytest.fixture
    def seeded_db(self, flask_app):
        """Seed database with test entries using unique timestamps."""
        from openrecall.server.database import SQLStore

        store = SQLStore()
        # Use a unique base timestamp to avoid collisions with other test runs
        import random

        base_ts = int(time.time() * 1000) + random.randint(1, 1000000)

        entries = []
        for i in range(5):
            ts = base_ts + (i * 100)
            store.insert_pending_entry(
                timestamp=ts,
                app=f"TestApp{i}_{base_ts}",
                title=f"TestWindow {i}_{base_ts}",
                image_path=f"/fake/{ts}.png",
            )
            entries.append(
                {
                    "timestamp": ts,
                    "app": f"TestApp{i}_{base_ts}",
                    "title": f"TestWindow {i}_{base_ts}",
                }
            )

        # Mark some as completed for status filter testing
        conn = store._connect_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE entries SET status='COMPLETED', description='Test desc' WHERE timestamp=?",
                (entries[0]["timestamp"],),
            )
            cursor.execute(
                "UPDATE entries SET status='COMPLETED', description='Test desc 2' WHERE timestamp=?",
                (entries[2]["timestamp"],),
            )
            conn.commit()
        finally:
            conn.close()

        return {"entries": entries, "store": store, "base_ts": base_ts}

    def test_default_limit(self, flask_client, seeded_db):
        """Default request should return items."""
        resp = flask_client.get("/api/v3/frames")
        assert resp.status_code == 200
        data = resp.get_json()
        # We inserted 5 entries, should have at least 5
        assert len(data["items"]) >= 5

    def test_limit_parameter(self, flask_client, seeded_db):
        """Limit parameter should restrict results."""
        resp = flask_client.get("/api/v3/frames?limit=2")
        data = resp.get_json()
        assert len(data["items"]) == 2

    def test_limit_max_cap(self, flask_client, seeded_db):
        """Limit should be capped at 200."""
        resp = flask_client.get("/api/v3/frames?limit=500")
        assert resp.status_code == 200
        # Should not crash, just cap

    def test_before_pagination(self, flask_client, seeded_db):
        """Before parameter should paginate backwards."""
        entries = seeded_db["entries"]
        # Get the middle timestamp
        middle_ts = entries[2]["timestamp"]

        resp = flask_client.get(f"/api/v3/frames?before={middle_ts}")
        data = resp.get_json()
        # Should only get entries with timestamp < middle_ts
        for item in data["items"]:
            assert item["timestamp"] < middle_ts

    def test_after_incremental(self, flask_client, seeded_db):
        """After parameter should get newer items (polling)."""
        entries = seeded_db["entries"]
        first_ts = entries[0]["timestamp"]

        resp = flask_client.get(f"/api/v3/frames?after={first_ts}")
        data = resp.get_json()
        # Should get entries with timestamp > first_ts
        for item in data["items"]:
            assert item["timestamp"] > first_ts

    def test_status_filter_pending(self, flask_client, seeded_db):
        """Status=PENDING should filter by status."""
        resp = flask_client.get("/api/v3/frames?status=PENDING")
        data = resp.get_json()
        for item in data["items"]:
            assert item["status"] == "PENDING"

    def test_status_filter_completed(self, flask_client, seeded_db):
        """Status=COMPLETED should filter by status."""
        base_ts = seeded_db["base_ts"]
        # Filter by both status and app prefix to isolate our test data
        resp = flask_client.get(f"/api/v3/frames?status=COMPLETED&app=TestApp")
        data = resp.get_json()
        # Filter to only our test entries
        our_items = [item for item in data["items"] if str(base_ts) in item["app_name"]]
        assert len(our_items) == 2
        for item in our_items:
            assert item["status"] == "COMPLETED"

    def test_app_filter(self, flask_client, seeded_db):
        """App filter should match by contains."""
        base_ts = seeded_db["base_ts"]
        entries = seeded_db["entries"]
        # Use the exact app name from our test entries
        app_name = entries[1]["app"]
        resp = flask_client.get(f"/api/v3/frames?app={app_name}")
        data = resp.get_json()
        assert len(data["items"]) == 1
        assert app_name in data["items"][0]["app_name"]

    def test_window_filter(self, flask_client, seeded_db):
        """Window filter should match by contains."""
        base_ts = seeded_db["base_ts"]
        entries = seeded_db["entries"]
        # Use the exact window title from our test entries
        window_title = entries[2]["title"]
        resp = flask_client.get(f"/api/v3/frames?window={window_title}")
        data = resp.get_json()
        assert len(data["items"]) == 1
        assert window_title in data["items"][0]["window_title"]

    def test_next_before_cursor(self, flask_client, seeded_db):
        """When paginating with limit, next_before should be set."""
        resp = flask_client.get("/api/v3/frames?limit=2")
        data = resp.get_json()
        assert len(data["items"]) == 2
        # next_before should be the timestamp of the last item for continuation
        if len(data["items"]) == 2:
            assert data["next_before"] == data["items"][-1]["timestamp"]

    def test_response_structure(self, flask_client, seeded_db):
        """Each item should have the expected fields."""
        resp = flask_client.get("/api/v3/frames?limit=1")
        data = resp.get_json()
        assert len(data["items"]) >= 1

        item = data["items"][0]
        required_fields = [
            "id",
            "timestamp",
            "app_name",
            "window_title",
            "status",
            "image_url",
        ]
        for field in required_fields:
            assert field in item, f"Missing field: {field}"
