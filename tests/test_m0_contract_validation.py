"""Tests for M0 contract validation models."""

import uuid

import pytest
from pydantic import ValidationError

from openrecall.shared.contract_m0 import (
    LEGACY_DEVICE_ID,
    UploadMetadataV1,
    generate_diagnostic_id,
)


def _base_upload_metadata() -> dict[str, object]:
    return {
        "client_ts": 1700000000123,
        "client_tz": "UTC",
        "image_hash": "a" * 64,
        "app_name": "MyApp",
        "window_title": "Main Window",
    }


def test_upload_metadata_legacy_timestamp_maps_to_client_ts_ms() -> None:
    payload = {
        "timestamp": 1700000000,
        "client_tz": "UTC",
        "image_hash": "a" * 64,
        "app_name": "MyApp",
        "window_title": "Main Window",
    }

    metadata = UploadMetadataV1(**payload)

    assert metadata.client_ts == 1700000000 * 1000
    assert metadata.device_id == LEGACY_DEVICE_ID


def test_upload_metadata_validates_device_id_pattern() -> None:
    payload = _base_upload_metadata()
    payload["device_id"] = "bad space"

    with pytest.raises(ValidationError):
        UploadMetadataV1(**payload)


def test_upload_metadata_validates_image_hash_length() -> None:
    payload = _base_upload_metadata()
    payload["image_hash"] = "a" * 63

    with pytest.raises(ValidationError):
        UploadMetadataV1(**payload)


def test_generate_diagnostic_id_returns_valid_uuid() -> None:
    diagnostic_id = generate_diagnostic_id()

    parsed = uuid.UUID(diagnostic_id)

    assert str(parsed) == diagnostic_id
