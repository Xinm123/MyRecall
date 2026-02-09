"""Tests for Phase 0 backward compatibility."""

import io
import json
import sqlite3
import time

import pytest


@pytest.fixture
def flask_app_migrated(tmp_path, monkeypatch):
    """Flask app with v3 migration applied."""
    import importlib
    import unittest.mock as mock

    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)

    # Reload sql submodule so it picks up new settings
    import openrecall.server.database.sql
    importlib.reload(openrecall.server.database.sql)
    import openrecall.server.database
    importlib.reload(openrecall.server.database)
    openrecall.server.database.SQLStore()

    # Run v3 migration on the test DB
    from openrecall.server.database.migrations.runner import MigrationRunner
    db_path = openrecall.shared.config.settings.db_path
    runner = MigrationRunner(db_path)
    result = runner.run()
    assert result.success, f"Migration failed: {result.error}"

    import openrecall.server.auth
    importlib.reload(openrecall.server.auth)

    # Mock SearchEngine to avoid HuggingFace model download in test env
    import openrecall.server.search.engine
    mock_se = mock.MagicMock()
    mock_se.search.return_value = []
    monkeypatch.setattr(
        openrecall.server.search.engine, "SearchEngine", lambda: mock_se
    )

    import openrecall.server.api
    importlib.reload(openrecall.server.api)

    import openrecall.server.api_v1
    importlib.reload(openrecall.server.api_v1)

    import openrecall.server.app
    importlib.reload(openrecall.server.app)

    return openrecall.server.app.app


@pytest.fixture
def client_migrated(flask_app_migrated):
    flask_app_migrated.config["TESTING"] = True
    with flask_app_migrated.test_client() as client:
        yield client


class TestFullV2Pipeline:
    def test_upload_query_after_migration(self, client_migrated):
        """F-02: Upload -> PENDING -> query works after migration."""
        from PIL import Image

        # Step 1: Upload
        img = Image.new("RGB", (10, 10), color="blue")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        metadata = json.dumps({
            "timestamp": 1234567890,
            "app_name": "TestApp",
            "window_title": "TestWindow",
        })

        resp = client_migrated.post(
            "/api/upload",
            data={"file": (img_bytes, "test.png"), "metadata": metadata},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 202

        # Step 2: Query recent memories
        resp = client_migrated.get("/api/memories/recent?limit=10")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1
        assert any(m["timestamp"] == 1234567890 for m in data)


class TestLegacyApiUntouched:
    def test_all_legacy_endpoints(self, client_migrated):
        """F-02: All legacy /api/* endpoints still work."""
        # Health
        resp = client_migrated.get("/api/health")
        assert resp.status_code == 200

        # Memories recent
        resp = client_migrated.get("/api/memories/recent")
        assert resp.status_code == 200

        # Memories latest
        resp = client_migrated.get("/api/memories/latest?since=0")
        assert resp.status_code == 200

        # Queue status
        resp = client_migrated.get("/api/queue/status")
        assert resp.status_code == 200
        queue_data = resp.get_json()
        assert "video_queue" in queue_data
        assert "completed" in queue_data["video_queue"]
        assert "pending" in queue_data["video_queue"]

        # Config
        resp = client_migrated.get("/api/config")
        assert resp.status_code == 200

        # Search (empty query)
        resp = client_migrated.get("/api/search?q=")
        assert resp.status_code == 200


class TestV1AndLegacyCoexist:
    def test_both_health_endpoints(self, client_migrated):
        """Both /api/health and /api/v1/health return 200."""
        resp_legacy = client_migrated.get("/api/health")
        resp_v1 = client_migrated.get("/api/v1/health")

        assert resp_legacy.status_code == 200
        assert resp_v1.status_code == 200


class TestQueryOverhead:
    def test_query_overhead_under_10ms(self, tmp_path, monkeypatch):
        """P-02: Schema changes add <10ms to typical queries."""
        import importlib

        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)
        db_path = openrecall.shared.config.settings.db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create DB with entries (no migration)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app TEXT, title TEXT, text TEXT,
                timestamp INTEGER UNIQUE, embedding BLOB,
                description TEXT, status TEXT DEFAULT 'COMPLETED'
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)")
        for i in range(100):
            conn.execute(
                "INSERT INTO entries (timestamp, app, title, text, status) "
                "VALUES (?, ?, ?, ?, 'COMPLETED')",
                (2000000 + i, f"app_{i}", f"title_{i}", f"text_{i}"),
            )
        conn.commit()

        # Baseline: query 100 times
        def benchmark_query(conn):
            times = []
            for _ in range(100):
                start = time.perf_counter()
                conn.execute(
                    "SELECT id, app, title, text, timestamp, status "
                    "FROM entries ORDER BY timestamp DESC LIMIT 50"
                ).fetchall()
                times.append(time.perf_counter() - start)
            return sorted(times)[len(times) // 2]  # median

        baseline_median = benchmark_query(conn)
        conn.close()

        # Apply migration
        from openrecall.server.database.migrations.runner import MigrationRunner
        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        # Post-migration: query 100 times
        conn = sqlite3.connect(str(db_path))
        post_median = benchmark_query(conn)
        conn.close()

        overhead_ms = (post_median - baseline_median) * 1000
        assert overhead_ms < 10, (
            f"Query overhead {overhead_ms:.2f}ms exceeds 10ms target "
            f"(baseline: {baseline_median * 1000:.2f}ms, "
            f"post: {post_median * 1000:.2f}ms)"
        )
