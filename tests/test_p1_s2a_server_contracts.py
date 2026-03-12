from __future__ import annotations

import io
import json
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from openrecall.server import __main__ as server_main
from openrecall.server import api, api_v1
from openrecall.server.config_runtime import runtime_settings
from openrecall.server.database.frames_store import FramesStore
from openrecall.client import v3_uploader
from openrecall.client.spool import SpoolItem


def generate_uuid_v7() -> str:
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    uuid_int = (
        (timestamp_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0x2 << 62) | rand_b
    )
    return str(uuid.UUID(int=uuid_int))


def create_test_jpeg() -> bytes:
    return bytes(
        [
            0xFF,
            0xD8,
            0xFF,
            0xE0,
            0x00,
            0x10,
            0x4A,
            0x46,
            0x49,
            0x46,
            0x00,
            0x01,
            0x01,
            0x00,
            0x00,
            0x01,
            0x00,
            0x01,
            0x00,
            0x00,
            0xFF,
            0xD9,
        ]
    )


def iso_seconds_ago(seconds: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(seconds=seconds))
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_test_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[FlaskClient, FramesStore, Path]:
    db_path = tmp_path / "edge.db"
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    server_main.ensure_v3_schema(db_path=db_path)

    store = FramesStore(db_path=db_path)
    monkeypatch.setattr(api_v1, "_frames_store", None)
    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: store)
    monkeypatch.setattr(api_v1.settings, "server_data_dir", tmp_path)
    monkeypatch.setattr(api_v1.settings, "queue_capacity", 200)

    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    return app.test_client(), store, db_path


@pytest.mark.unit
def test_claim_frame_persists_s2a_metadata_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "edge.db"
    server_main.ensure_v3_schema(db_path=db_path)

    store = FramesStore(db_path=db_path)
    capture_id = "0195789e-31bd-7ddf-b6d8-5f955dc6d6f0"
    metadata: dict[str, object] = {
        "timestamp": "2026-03-10T12:00:00Z",
        "capture_trigger": "click",
        "event_ts": "2026-03-10T11:59:59Z",
        "device_name": "monitor_7",
        "app_name": "Finder",
        "window_name": "Desktop",
        "accessibility_text": "AX text",
        "content_hash": "sha256:" + "f" * 64,
    }

    frame_id, is_new = store.claim_frame(capture_id=capture_id, metadata=metadata)

    assert is_new is True
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT capture_trigger, event_ts, device_name, app_name, window_name FROM frames WHERE id = ?",
            (frame_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "click"
    assert row[1] == "2026-03-10T11:59:59Z"
    assert row[2] == "monitor_7"
    assert row[3] == "Finder"
    assert row[4] == "Desktop"


@pytest.mark.unit
def test_frames_store_reports_capture_latency_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "edge.db"
    server_main.ensure_v3_schema(db_path=db_path)

    valid_event_ts = iso_seconds_ago(3)
    valid_ingested_at = iso_seconds_ago(1)
    valid_processed_at = iso_seconds_ago(0)
    invalid_ingested_at = iso_seconds_ago(2)
    future_event_ts = iso_seconds_ago(-2)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO frames (
                capture_id, timestamp, app_name, window_name, device_name,
                snapshot_path, capture_trigger, event_ts, status, ingested_at, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "0195789e-31bd-7ddf-b6d8-5f955dc6d6f1",
                "2026-03-10T12:00:00Z",
                "Finder",
                "Desktop",
                "monitor_1",
                "/tmp/a.jpg",
                "click",
                valid_event_ts,
                "completed",
                valid_ingested_at,
                valid_processed_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO frames (
                capture_id, timestamp, app_name, window_name, device_name,
                snapshot_path, capture_trigger, event_ts, status, ingested_at, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "0195789e-31bd-7ddf-b6d8-5f955dc6d6f2",
                "2026-03-10T12:00:00Z",
                "Finder",
                "Desktop",
                "monitor_1",
                "/tmp/b.jpg",
                "manual",
                "not-a-timestamp",
                "completed",
                invalid_ingested_at,
                valid_processed_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO frames (
                capture_id, timestamp, app_name, window_name, device_name,
                snapshot_path, capture_trigger, event_ts, status, ingested_at, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "0195789e-31bd-7ddf-b6d8-5f955dc6d6f3",
                "2026-03-10T12:00:00Z",
                "Finder",
                "Desktop",
                "monitor_1",
                "/tmp/c.jpg",
                "idle",
                future_event_ts,
                "completed",
                valid_ingested_at,
                valid_processed_at,
            ),
        )
        conn.commit()

    summary = FramesStore(db_path=db_path).get_capture_latency_summary()

    assert summary["capture_latency_sample_count"] == 1
    assert summary["capture_latency_anomaly_count"] == 2
    assert summary["capture_latency_p95"] == pytest.approx(2000.0, abs=100.0)
    assert isinstance(summary["edge_pid"], int)
    assert summary["edge_pid"] > 0
    assert summary["broken_window"] is False
    assert summary["window_id"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "metadata",
    [
        {"timestamp": "2026-03-10T12:00:00Z"},
        {"timestamp": "2026-03-10T12:00:00Z", "capture_trigger": None},
        {"timestamp": "2026-03-10T12:00:00Z", "capture_trigger": "typing_pause"},
    ],
)
def test_ingest_rejects_invalid_capture_trigger_without_claim(monkeypatch, metadata):
    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    client = app.test_client()

    class _FakeStore:
        @staticmethod
        def get_pending_count() -> int:
            return 0

        @staticmethod
        def claim_frame(*args, **kwargs):
            raise AssertionError(
                "claim_frame must not be called for invalid capture_trigger"
            )

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: _FakeStore())

    response = client.post(
        "/v1/ingest",
        data={
            "capture_id": generate_uuid_v7(),
            "metadata": json.dumps(metadata),
            "file": (io.BytesIO(create_test_jpeg()), "test.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "INVALID_PARAMS"


@pytest.mark.unit
@pytest.mark.parametrize(
    "missing_key",
    [
        "accessibility_text",
        "content_hash",
        "device_name",
    ],
)
def test_ingest_rejects_missing_s2b_required_keys_without_claim(
    monkeypatch: pytest.MonkeyPatch,
    missing_key: str,
) -> None:
    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    client = app.test_client()

    class _FakeStore:
        @staticmethod
        def get_pending_count() -> int:
            return 0

        @staticmethod
        def claim_frame(*args, **kwargs):
            raise AssertionError("claim_frame must not run for schema_rejected payload")

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: _FakeStore())

    metadata: dict[str, object] = {
        "timestamp": "2026-03-10T12:00:00Z",
        "capture_trigger": "manual",
        "device_name": "monitor_1",
        "accessibility_text": "",
        "content_hash": None,
    }
    _ = metadata.pop(missing_key)

    response = client.post(
        "/v1/ingest",
        data={
            "capture_id": generate_uuid_v7(),
            "metadata": json.dumps(metadata),
            "file": (io.BytesIO(create_test_jpeg()), "test.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "INVALID_PARAMS"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("accessibility_text", "content_hash"),
    [
        (None, None),
        ("ok", ""),
        ("ok", 123),
    ],
)
def test_ingest_rejects_invalid_s2b_field_types(
    monkeypatch: pytest.MonkeyPatch,
    accessibility_text: object,
    content_hash: object,
) -> None:
    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    client = app.test_client()

    class _FakeStore:
        @staticmethod
        def get_pending_count() -> int:
            return 0

        @staticmethod
        def claim_frame(*args, **kwargs):
            raise AssertionError("claim_frame must not run for invalid required fields")

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: _FakeStore())

    response = client.post(
        "/v1/ingest",
        data={
            "capture_id": generate_uuid_v7(),
            "metadata": json.dumps(
                {
                    "timestamp": "2026-03-10T12:00:00Z",
                    "capture_trigger": "manual",
                    "device_name": "monitor_1",
                    "accessibility_text": accessibility_text,
                    "content_hash": content_hash,
                }
            ),
            "file": (io.BytesIO(create_test_jpeg()), "test.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "INVALID_PARAMS"


@pytest.mark.unit
def test_ingest_accepts_empty_ax_payload_and_persists_s2b_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _store, db_path = build_test_client(tmp_path, monkeypatch)

    response = client.post(
        "/v1/ingest",
        data={
            "capture_id": generate_uuid_v7(),
            "metadata": json.dumps(
                {
                    "timestamp": "2026-03-10T12:00:00Z",
                    "capture_trigger": "manual",
                    "device_name": "monitor_2",
                    "app_name": "Finder",
                    "window_name": "Desktop",
                    "browser_url": None,
                    "accessibility_text": "",
                    "content_hash": None,
                }
            ),
            "file": (io.BytesIO(create_test_jpeg()), "test.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT accessibility_text, content_hash, device_name, app_name, window_name FROM frames"
        ).fetchone()

    assert row is not None
    assert row[0] == ""
    assert row[1] is None
    assert row[2] == "monitor_2"
    assert row[3] == "Finder"
    assert row[4] == "Desktop"


@pytest.mark.unit
def test_ingest_alias_only_payload_is_treated_as_migration_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _store, db_path = build_test_client(tmp_path, monkeypatch)

    response = client.post(
        "/v1/ingest",
        data={
            "capture_id": generate_uuid_v7(),
            "metadata": json.dumps(
                {
                    "timestamp": "2026-03-10T12:00:00Z",
                    "capture_trigger": "app_switch",
                    "device_name": "monitor_3",
                    "active_app": "Legacy Finder",
                    "active_window": "Legacy Window",
                    "accessibility_text": "AX text",
                    "content_hash": "sha256:" + "a" * 64,
                }
            ),
            "file": (io.BytesIO(create_test_jpeg()), "test.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT app_name, window_name FROM frames").fetchone()

    assert row is not None
    assert row[0] is None
    assert row[1] is None


@pytest.mark.unit
def test_v3_uploader_enforces_required_keys_and_canonical_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    jpg_path = tmp_path / "frame.jpg"
    jpg_path.write_bytes(create_test_jpeg())

    item = SpoolItem(
        capture_id=generate_uuid_v7(),
        jpg_path=jpg_path,
        metadata={
            "timestamp": "2026-03-10T12:00:00Z",
            "capture_trigger": "manual",
            "device_name": "monitor_9",
            "active_app": "Legacy App",
            "active_window": "Legacy Window",
        },
    )

    class _Response:
        status_code = 201

        @staticmethod
        def json() -> dict[str, object]:
            return {"status": "queued", "frame_id": 1}

    captured_data: dict[str, str] = {}

    def _fake_post(*args, **kwargs):
        captured_data.update(kwargs["data"])
        return _Response()

    class _FakeSpool:
        @staticmethod
        def commit(_capture_id: str) -> None:
            return None

    monkeypatch.setattr(v3_uploader.requests, "post", _fake_post)
    monkeypatch.setattr(v3_uploader, "get_spool", lambda: _FakeSpool())
    result = v3_uploader.upload_capture(item)

    assert result.success is True
    metadata = json.loads(captured_data["metadata"])
    assert metadata["capture_trigger"] == "manual"
    assert metadata["device_name"] == "monitor_9"
    assert metadata["browser_url"] is None
    assert metadata["accessibility_text"] == ""
    assert metadata["content_hash"] is None
    assert "active_app" not in metadata
    assert "active_window" not in metadata


@pytest.mark.unit
@pytest.mark.parametrize(
    "metadata_overrides",
    [
        {},
        {"event_ts": "not-a-timestamp"},
    ],
)
def test_ingest_accepts_missing_or_invalid_event_ts_but_excludes_latency_stats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata_overrides: dict[str, object],
) -> None:
    client, store, _db_path = build_test_client(tmp_path, monkeypatch)

    metadata: dict[str, object] = {
        "timestamp": iso_seconds_ago(1),
        "capture_trigger": "manual",
        "device_name": "monitor_1",
        "accessibility_text": "",
        "content_hash": None,
    }
    metadata.update(metadata_overrides)

    response = client.post(
        "/v1/ingest",
        data={
            "capture_id": generate_uuid_v7(),
            "metadata": json.dumps(metadata),
            "file": (io.BytesIO(create_test_jpeg()), "test.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    summary = store.get_capture_latency_summary(window_seconds=3600)
    assert summary["capture_latency_sample_count"] == 0
    assert summary["capture_latency_anomaly_count"] == 1


@pytest.mark.unit
def test_ingest_accepts_future_event_ts_but_excludes_negative_latency_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, store, _db_path = build_test_client(tmp_path, monkeypatch)

    response = client.post(
        "/v1/ingest",
        data={
            "capture_id": generate_uuid_v7(),
            "metadata": json.dumps(
                {
                    "timestamp": iso_seconds_ago(1),
                    "capture_trigger": "click",
                    "device_name": "monitor_1",
                    "event_ts": iso_seconds_ago(-60),
                    "accessibility_text": "",
                    "content_hash": None,
                }
            ),
            "file": (io.BytesIO(create_test_jpeg()), "test.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    summary = store.get_capture_latency_summary(window_seconds=3600)
    assert summary["capture_latency_sample_count"] == 0
    assert summary["capture_latency_anomaly_count"] == 1


@pytest.mark.unit
def test_duplicate_capture_id_with_valid_s2a_metadata_returns_already_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, store, db_path = build_test_client(tmp_path, monkeypatch)
    capture_id = generate_uuid_v7()
    metadata = {
        "timestamp": iso_seconds_ago(1),
        "capture_trigger": "manual",
        "device_name": "monitor_7",
        "event_ts": iso_seconds_ago(2),
        "accessibility_text": "",
        "content_hash": None,
    }

    first = client.post(
        "/v1/ingest",
        data={
            "capture_id": capture_id,
            "metadata": json.dumps(metadata),
            "file": (io.BytesIO(create_test_jpeg()), "test.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )
    counts_after_first = store.get_queue_counts()

    second = client.post(
        "/v1/ingest",
        data={
            "capture_id": capture_id,
            "metadata": json.dumps(metadata),
            "file": (io.BytesIO(create_test_jpeg()), "test.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert first.status_code == 201
    assert second.status_code == 200
    second_payload = second.get_json()
    assert second_payload["status"] == "already_exists"
    assert "code" not in second_payload
    assert store.get_queue_counts() == counts_after_first

    with sqlite3.connect(str(db_path)) as conn:
        total_rows = conn.execute("SELECT COUNT(*) FROM frames").fetchone()[0]

    assert total_rows == 1


@pytest.mark.unit
def test_heartbeat_updates_runtime_mirror_fields() -> None:
    app = Flask(__name__)
    app.register_blueprint(api.api_bp)
    client = app.test_client()

    response = client.post(
        "/api/heartbeat",
        json={
            "capture_permission_status": "recovering",
            "capture_permission_reason": "screen_recording_denied",
            "last_permission_check_ts": "2026-03-10T12:00:00Z",
            "screen_capture_status": "degraded",
            "screen_capture_reason": "screen_recording_denied",
            "queue_depth": 7,
            "queue_capacity": 64,
            "collapse_trigger_count": 2,
            "overflow_drop_count": 0,
        },
    )

    assert response.status_code == 200
    with runtime_settings._lock:
        assert runtime_settings.capture_permission_status == "recovering"
        assert runtime_settings.capture_permission_reason == "screen_recording_denied"
        assert runtime_settings.last_permission_check_ts == "2026-03-10T12:00:00Z"
        assert runtime_settings.screen_capture_status == "degraded"
        assert runtime_settings.screen_capture_reason == "screen_recording_denied"
        assert runtime_settings.queue_depth == 7
        assert runtime_settings.queue_capacity == 64
        assert runtime_settings.collapse_trigger_count == 2
        assert runtime_settings.overflow_drop_count == 0


@pytest.mark.unit
def test_health_degrades_for_stale_permission_snapshot(monkeypatch) -> None:
    class _FakeStore:
        @staticmethod
        def get_last_frame_timestamp() -> str | None:
            return "2026-03-10T12:00:00Z"

        @staticmethod
        def get_last_frame_ingested_at() -> str | None:
            return "2026-03-10T12:00:01Z"

        @staticmethod
        def get_queue_counts() -> dict[str, int]:
            return {"pending": 0, "processing": 0, "failed": 0}

    with runtime_settings._lock:
        runtime_settings.capture_permission_status = "granted"
        runtime_settings.capture_permission_reason = "granted"
        runtime_settings.last_permission_check_ts = "2026-03-10T12:00:00Z"
        runtime_settings.last_permission_snapshot_epoch = 0.0

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: _FakeStore())

    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    client = app.test_client()

    response = client.get("/v1/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["capture_permission_status"] == "granted"
    assert payload["capture_permission_reason"] == "stale_permission_state"
    assert payload["last_permission_check_ts"] == "2026-03-10T12:00:00Z"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("permission_status", "permission_reason", "expected_message"),
    [
        ("recovering", "granted", "权限恢复中"),
        ("denied_or_revoked", "screen_recording_denied", "权限异常"),
    ],
)
def test_health_degrades_for_permission_recovery_states(
    monkeypatch: pytest.MonkeyPatch,
    permission_status: str,
    permission_reason: str,
    expected_message: str,
) -> None:
    class _FakeStore:
        @staticmethod
        def get_last_frame_timestamp() -> str | None:
            return "2026-03-10T12:00:00Z"

        @staticmethod
        def get_last_frame_ingested_at() -> str | None:
            return iso_seconds_ago(1)

        @staticmethod
        def get_queue_counts() -> dict[str, int]:
            return {"pending": 0, "processing": 0, "failed": 0}

    with runtime_settings._lock:
        runtime_settings.capture_permission_status = permission_status
        runtime_settings.capture_permission_reason = permission_reason
        runtime_settings.last_permission_check_ts = "2026-03-10T12:00:00Z"
        runtime_settings.last_permission_snapshot_epoch = time.time()

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: _FakeStore())

    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    client = app.test_client()

    response = client.get("/v1/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["capture_permission_status"] == permission_status
    assert payload["capture_permission_reason"] == permission_reason
    assert payload["message"] == expected_message


@pytest.mark.unit
def test_queue_status_returns_trigger_channel_and_status_sync(monkeypatch) -> None:
    class _FakeStore:
        @staticmethod
        def get_queue_counts() -> dict[str, int]:
            return {"pending": 3, "processing": 1, "completed": 9, "failed": 0}

        @staticmethod
        def get_oldest_pending_ingested_at() -> str | None:
            return "2026-03-10T12:00:00Z"

        @staticmethod
        def get_capture_latency_summary() -> dict[str, object]:
            return {
                "capture_latency_p95": 2500.0,
                "capture_latency_sample_count": 4,
                "capture_latency_anomaly_count": 1,
                "window_id": "window-1",
                "edge_pid": 123,
                "broken_window": False,
            }

        @staticmethod
        def get_status_sync_summary() -> dict[str, object]:
            return {
                "status_sync_p95": 4000.0,
                "status_sync_sample_count": 5,
                "window_id": "window-1",
                "edge_pid": 123,
                "broken_window": False,
            }

    with runtime_settings._lock:
        runtime_settings.queue_depth = 6
        runtime_settings.queue_capacity = 64
        runtime_settings.collapse_trigger_count = 3
        runtime_settings.overflow_drop_count = 0

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: _FakeStore())

    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    client = app.test_client()

    response = client.get("/v1/ingest/queue/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["trigger_channel"] == {
        "queue_depth": 6,
        "queue_capacity": 64,
        "collapse_trigger_count": 3,
        "overflow_drop_count": 0,
    }
    assert payload["capture_latency"]["capture_latency_p95"] == 2500.0
    assert payload["status_sync"]["status_sync_p95"] == 4000.0


@pytest.mark.unit
def test_layout_health_polling_handles_permission_payload() -> None:
    content = Path(
        "/Users/pyw/old/MyRecall/openrecall/server/templates/layout.html"
    ).read_text(encoding="utf-8")

    assert "capture_permission_status" in content
    assert "capture_permission_reason" in content
    assert "screen_capture_status" in content
    assert "screen_capture_reason" in content
    assert "stale_permission_state" in content
    assert "权限异常" in content or "权限恢复中" in content
