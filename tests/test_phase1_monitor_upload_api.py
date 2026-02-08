"""API tests for monitor metadata upload path."""

import io
import json
import sqlite3


def test_upload_status_accepts_sha256_prefix(flask_client, tmp_path):
    from openrecall.shared.config import settings

    checksum = "abcdef012345"
    settings.video_chunks_path.mkdir(parents=True, exist_ok=True)
    file_path = settings.video_chunks_path / f"{checksum}.mp4"
    file_path.write_bytes(b"video-bytes")

    response = flask_client.get(f"/api/v1/upload/status?checksum=sha256:{checksum}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "completed"
    assert data["bytes_received"] == len(b"video-bytes")


def test_legacy_upload_status_accepts_sha256_prefix(flask_client, tmp_path):
    from openrecall.shared.config import settings

    checksum = "facefeed9876"
    settings.video_chunks_path.mkdir(parents=True, exist_ok=True)
    file_path = settings.video_chunks_path / f"{checksum}.mp4"
    file_path.write_bytes(b"video-bytes")

    response = flask_client.get(f"/api/upload/status?checksum=sha256:{checksum}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "completed"
    assert data["bytes_received"] == len(b"video-bytes")


def test_video_upload_persists_monitor_metadata(flask_client):
    from openrecall.shared.config import settings
    from openrecall.server.database.migrations.runner import MigrationRunner

    result = MigrationRunner(settings.db_path).run()
    assert result.success

    metadata = {
        "type": "video_chunk",
        "checksum": "sha256:feedface",
        "device_name": "display-main",
        "active_app": "Cursor",
        "active_window": "settings.json",
        "monitor_id": "42",
        "monitor_width": 3840,
        "monitor_height": 2160,
        "monitor_is_primary": 1,
        "monitor_backend": "sck",
        "monitor_fingerprint": "3840x2160:1",
    }

    payload = {
        "file": (io.BytesIO(b"video-chunk-data"), "chunk.mp4"),
    }
    response = flask_client.post(
        "/api/v1/upload",
        data={
            "metadata": json.dumps(metadata),
            **payload,
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 202

    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM video_chunks ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()

    assert row is not None
    assert row["monitor_id"] == "42"
    assert row["monitor_width"] == 3840
    assert row["monitor_height"] == 2160
    assert row["monitor_is_primary"] == 1
    assert row["monitor_backend"] == "sck"
    assert row["monitor_fingerprint"] == "3840x2160:1"
    assert row["app_name"] == "Cursor"
    assert row["window_name"] == "settings.json"


def test_legacy_upload_routes_video_chunk_to_video_table(flask_client):
    from openrecall.shared.config import settings
    from openrecall.server.database.migrations.runner import MigrationRunner

    result = MigrationRunner(settings.db_path).run()
    assert result.success

    metadata = {
        "type": "video_chunk",
        "checksum": "sha256:legacyfeed",
        "device_name": "legacy-display",
        "monitor_id": "7",
    }

    response = flask_client.post(
        "/api/upload",
        data={
            "metadata": json.dumps(metadata),
            "file": (io.BytesIO(b"video-data"), "chunk.mp4", "video/mp4"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["status"] == "accepted"
    assert "chunk_id" in payload

    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    video_row = conn.execute("SELECT * FROM video_chunks ORDER BY id DESC LIMIT 1").fetchone()
    entries_count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    conn.close()

    assert video_row is not None
    assert video_row["monitor_id"] == "7"
    # Legacy route should not insert screenshot task rows for video payload.
    assert entries_count == 0


def test_legacy_video_upload_works_without_manual_migration(flask_client):
    """Regression: server must not require manual MigrationRunner invocation."""
    from openrecall.shared.config import settings

    metadata = {
        "type": "video_chunk",
        "checksum": "sha256:autoinitfeed",
        "device_name": "auto-migrate-display",
        "monitor_id": "1",
    }

    response = flask_client.post(
        "/api/upload",
        data={
            "metadata": json.dumps(metadata),
            "file": (io.BytesIO(b"video-data"), "chunk.mp4", "video/mp4"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 202

    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    video_row = conn.execute("SELECT * FROM video_chunks ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()

    assert video_row is not None
    assert video_row["monitor_id"] == "1"
