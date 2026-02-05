"""Integration tests for M0 upload contract.

Tests upload endpoint with auth, idempotency, conflict handling, and hash verification.
"""

import hashlib
import io
import json
import os
import tempfile
import time
from pathlib import Path
import importlib

import pytest


@pytest.fixture
def test_image_bytes():
    from PIL import Image

    img = Image.new("RGB", (100, 100), color="red")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    return img_bytes.getvalue()


@pytest.fixture
def test_metadata_factory(test_image_bytes):
    def _factory(device_id="test-device", client_ts=None, **overrides):
        if client_ts is None:
            client_ts = int(time.time() * 1000)

        image_hash = hashlib.sha256(test_image_bytes).hexdigest()

        metadata = {
            "device_id": device_id,
            "client_ts": client_ts,
            "client_tz": "America/Los_Angeles",
            "client_seq": 1,
            "image_hash": image_hash,
            "app_name": "TestApp",
            "window_title": "Test Window",
        }
        metadata.update(overrides)
        return metadata

    return _factory


@pytest.fixture
def auth_flask_client(tmp_path, monkeypatch):
    test_dir = tmp_path / str(time.time_ns())
    test_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(test_dir))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(test_dir))
    monkeypatch.setenv("OPENRECALL_AUTH_MODE", "strict")
    monkeypatch.setenv(
        "OPENRECALL_DEVICE_TOKENS_JSON",
        json.dumps(
            {
                "test-device": {"active_token": "test-token-123"},
                "device-a": {"active_token": "token-a"},
                "device-b": {"active_token": "token-b"},
            }
        ),
    )

    import openrecall.shared.config

    importlib.reload(openrecall.shared.config)
    openrecall.shared.config.settings = openrecall.shared.config.Settings()

    import openrecall.server.utils.auth

    importlib.reload(openrecall.server.utils.auth)

    import openrecall.server.database

    importlib.reload(openrecall.server.database)
    openrecall.server.database.SQLStore()

    import openrecall.server.api

    importlib.reload(openrecall.server.api)

    import openrecall.server.app

    importlib.reload(openrecall.server.app)

    app = openrecall.server.app.app
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client


def test_upload_valid_contract_returns_202_and_persists_new_columns(
    auth_flask_client, test_image_bytes, test_metadata_factory
):
    metadata = test_metadata_factory(device_id="test-device")

    response = auth_flask_client.post(
        "/api/upload",
        data={
            "file": (io.BytesIO(test_image_bytes), "test.png", "image/png"),
            "metadata": json.dumps(metadata),
        },
        headers={"Authorization": "Bearer test-token-123"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    data = response.get_json()

    assert data["status"] == "accepted"
    assert "entry_id" in data
    assert data["device_id"] == "test-device"
    assert data["client_ts"] == metadata["client_ts"]
    assert "server_received_at" in data
    assert data["image_hash"] == metadata["image_hash"]
    assert "idempotency_key" in data
    assert "diagnostic_id" in data
    assert "queue" in data


def test_upload_idempotent_replay_returns_200(
    auth_flask_client, test_image_bytes, test_metadata_factory
):
    metadata = test_metadata_factory(device_id="test-device", client_ts=1738752000123)

    response1 = auth_flask_client.post(
        "/api/upload",
        data={
            "file": (io.BytesIO(test_image_bytes), "test.png", "image/png"),
            "metadata": json.dumps(metadata),
        },
        headers={"Authorization": "Bearer test-token-123"},
        content_type="multipart/form-data",
    )

    assert response1.status_code == 202
    data1 = response1.get_json()
    entry_id = data1["entry_id"]

    response2 = auth_flask_client.post(
        "/api/upload",
        data={
            "file": (io.BytesIO(test_image_bytes), "test.png", "image/png"),
            "metadata": json.dumps(metadata),
        },
        headers={"Authorization": "Bearer test-token-123"},
        content_type="multipart/form-data",
    )

    assert response2.status_code == 200
    data2 = response2.get_json()

    assert data2["status"] == "ok"
    assert data2["idempotent_replay"] is True
    assert data2["entry_id"] == entry_id
    assert "original_server_received_at" in data2
    assert "existing_status" in data2


def test_upload_conflict_returns_409(
    auth_flask_client, test_image_bytes, test_metadata_factory
):
    client_ts = 1738752000456
    metadata1 = test_metadata_factory(device_id="test-device", client_ts=client_ts)

    response1 = auth_flask_client.post(
        "/api/upload",
        data={
            "file": (io.BytesIO(test_image_bytes), "test.png", "image/png"),
            "metadata": json.dumps(metadata1),
        },
        headers={"Authorization": "Bearer test-token-123"},
        content_type="multipart/form-data",
    )

    assert response1.status_code == 202

    from PIL import Image

    different_img = Image.new("RGB", (100, 100), color="blue")
    different_bytes = io.BytesIO()
    different_img.save(different_bytes, format="PNG")
    different_image_bytes = different_bytes.getvalue()
    different_hash = hashlib.sha256(different_image_bytes).hexdigest()

    metadata2 = test_metadata_factory(
        device_id="test-device", client_ts=client_ts, image_hash=different_hash
    )

    response2 = auth_flask_client.post(
        "/api/upload",
        data={
            "file": (io.BytesIO(different_image_bytes), "test2.png", "image/png"),
            "metadata": json.dumps(metadata2),
        },
        headers={"Authorization": "Bearer test-token-123"},
        content_type="multipart/form-data",
    )

    assert response2.status_code == 409
    data2 = response2.get_json()

    assert data2["status"] == "conflict"
    assert data2["code"] == "UPLOAD_CONFLICT"
    assert data2["device_id"] == "test-device"
    assert data2["client_ts"] == client_ts
    assert "existing" in data2
    assert data2["existing"]["image_hash"] == metadata1["image_hash"]
    assert "incoming" in data2
    assert data2["incoming"]["image_hash"] == different_hash


def test_upload_missing_auth_returns_401_in_strict_mode(
    auth_flask_client, test_image_bytes, test_metadata_factory
):
    metadata = test_metadata_factory(device_id="test-device")

    response = auth_flask_client.post(
        "/api/upload",
        data={
            "file": (io.BytesIO(test_image_bytes), "test.png", "image/png"),
            "metadata": json.dumps(metadata),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 401
    data = response.get_json()

    assert data["status"] == "error"
    assert data["code"] == "AUTH_UNAUTHORIZED"
    assert "diagnostic_id" in data


def test_upload_hash_mismatch_returns_422(
    auth_flask_client, test_image_bytes, test_metadata_factory
):
    metadata = test_metadata_factory(device_id="test-device")
    metadata["image_hash"] = "0" * 64

    response = auth_flask_client.post(
        "/api/upload",
        data={
            "file": (io.BytesIO(test_image_bytes), "test.png", "image/png"),
            "metadata": json.dumps(metadata),
        },
        headers={"Authorization": "Bearer test-token-123"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 422
    data = response.get_json()

    assert data["status"] == "error"
    assert data["code"] == "UPLOAD_HASH_MISMATCH"
    assert "computed" in data
    assert "provided" in data
    assert data["provided"] == "0" * 64


def test_upload_forbidden_device_mismatch_returns_403(
    auth_flask_client, test_image_bytes, test_metadata_factory
):
    metadata = test_metadata_factory(device_id="device-b")

    response = auth_flask_client.post(
        "/api/upload",
        data={
            "file": (io.BytesIO(test_image_bytes), "test.png", "image/png"),
            "metadata": json.dumps(metadata),
        },
        headers={"Authorization": "Bearer token-a"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 403
    data = response.get_json()

    assert data["status"] == "error"
    assert data["code"] == "AUTH_FORBIDDEN"


def test_upload_too_large_returns_413(tmp_path, monkeypatch, test_metadata_factory):
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_AUTH_MODE", "strict")
    monkeypatch.setenv("OPENRECALL_MAX_UPLOAD_BYTES", "100")
    monkeypatch.setenv(
        "OPENRECALL_DEVICE_TOKENS_JSON",
        json.dumps({"test-device": {"active_token": "test-token-ghi"}}),
    )

    import openrecall.shared.config

    importlib.reload(openrecall.shared.config)
    openrecall.shared.config.settings = openrecall.shared.config.Settings()

    import openrecall.server.utils.auth

    importlib.reload(openrecall.server.utils.auth)

    import openrecall.server.database

    importlib.reload(openrecall.server.database)
    openrecall.server.database.SQLStore()

    import openrecall.server.api

    importlib.reload(openrecall.server.api)

    import openrecall.server.app

    importlib.reload(openrecall.server.app)

    app = openrecall.server.app.app
    app.config["TESTING"] = True

    large_bytes = b"\x89PNG\r\n\x1a\n" + (b"X" * 200)
    large_hash = hashlib.sha256(large_bytes).hexdigest()

    metadata = test_metadata_factory(device_id="test-device", image_hash=large_hash)

    with app.test_client() as client:
        response = client.post(
            "/api/upload",
            data={
                "file": (io.BytesIO(large_bytes), "large.png", "image/png"),
                "metadata": json.dumps(metadata),
            },
            headers={"Authorization": "Bearer test-token-ghi"},
            content_type="multipart/form-data",
        )

    assert response.status_code == 413
    data = response.get_json()

    assert data["status"] == "error"
    assert data["code"] == "UPLOAD_TOO_LARGE"
