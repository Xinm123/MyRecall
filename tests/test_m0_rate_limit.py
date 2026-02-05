"""M0 Rate Limiting Tests.

Tests that upload rate limiting works per device.
"""

import hashlib
import importlib
import io
import json
import time

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
def rate_limited_flask_client(tmp_path, monkeypatch):
    """Flask client with low rate limit for testing."""
    test_dir = tmp_path / str(time.time_ns())
    test_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(test_dir))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(test_dir))
    monkeypatch.setenv("OPENRECALL_AUTH_MODE", "strict")
    monkeypatch.setenv("OPENRECALL_RATE_LIMIT_UPLOAD_RPS", "2")
    monkeypatch.setenv(
        "OPENRECALL_DEVICE_TOKENS_JSON",
        json.dumps(
            {
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


def _do_upload(client, image_bytes, metadata, token):
    """Helper to perform an upload request."""
    return client.post(
        "/api/upload",
        data={
            "file": (io.BytesIO(image_bytes), "test.png", "image/png"),
            "metadata": json.dumps(metadata),
        },
        headers={"Authorization": f"Bearer {token}"},
        content_type="multipart/form-data",
    )


def test_upload_rate_limited_returns_429(
    rate_limited_flask_client, test_image_bytes, test_metadata_factory
):
    """Rapid uploads exceeding rate limit should return 429."""
    client = rate_limited_flask_client

    responses = []
    for i in range(5):
        metadata = test_metadata_factory(
            device_id="device-a", client_ts=int(time.time() * 1000) + i
        )
        response = _do_upload(client, test_image_bytes, metadata, "token-a")
        responses.append(response)

    status_codes = [r.status_code for r in responses]
    assert 429 in status_codes, f"Expected 429 in {status_codes}"

    rate_limited_response = next(r for r in responses if r.status_code == 429)
    data = rate_limited_response.get_json()

    assert data["status"] == "error"
    assert data["code"] == "RATE_LIMITED"
    assert data["message"] == "Upload rate limit exceeded"
    assert "diagnostic_id" in data


def test_upload_within_rate_limit_succeeds(
    rate_limited_flask_client, test_image_bytes, test_metadata_factory
):
    """Single upload within rate limit should succeed."""
    client = rate_limited_flask_client

    metadata = test_metadata_factory(device_id="device-a")
    response = _do_upload(client, test_image_bytes, metadata, "token-a")

    assert response.status_code == 202
    data = response.get_json()
    assert data["status"] == "accepted"


def test_rate_limit_is_per_device(
    rate_limited_flask_client, test_image_bytes, test_metadata_factory
):
    """Different devices should have separate rate limit buckets."""
    client = rate_limited_flask_client

    for i in range(3):
        metadata = test_metadata_factory(
            device_id="device-a", client_ts=int(time.time() * 1000) + i
        )
        _do_upload(client, test_image_bytes, metadata, "token-a")

    metadata_b = test_metadata_factory(device_id="device-b")
    response_b = _do_upload(client, test_image_bytes, metadata_b, "token-b")

    assert response_b.status_code == 202, (
        f"Device B should not be rate limited by device A's usage. "
        f"Got {response_b.status_code}: {response_b.get_json()}"
    )
    data = response_b.get_json()
    assert data["status"] == "accepted"
    assert data["device_id"] == "device-b"


class TestTokenBucketUnit:
    """Unit tests for TokenBucket class."""

    def test_token_bucket_allows_burst_up_to_capacity(self):
        from openrecall.server.api import TokenBucket

        bucket = TokenBucket(rate=2.0, capacity=3.0)

        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is False

    def test_token_bucket_refills_over_time(self):
        from openrecall.server.api import TokenBucket

        bucket = TokenBucket(rate=10.0, capacity=1.0)

        assert bucket.consume() is True
        assert bucket.consume() is False

        time.sleep(0.15)

        assert bucket.consume() is True


class TestDeviceRateLimiterUnit:
    """Unit tests for DeviceRateLimiter class."""

    def test_device_rate_limiter_creates_separate_buckets(self):
        from openrecall.server.api import DeviceRateLimiter

        limiter = DeviceRateLimiter(rps=1)

        assert limiter.check("device-1") is True
        assert limiter.check("device-1") is False

        assert limiter.check("device-2") is True

    def test_device_rate_limiter_bucket_refills(self):
        from openrecall.server.api import DeviceRateLimiter

        limiter = DeviceRateLimiter(rps=10)

        assert limiter.check("device-1") is True
        for _ in range(10):
            limiter.check("device-1")

        time.sleep(0.15)

        assert limiter.check("device-1") is True
