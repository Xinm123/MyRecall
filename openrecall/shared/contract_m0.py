"""M0 cross-machine contract models and constants."""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - fallback for older Python
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception


CONTRACT_VERSION = 1
LEGACY_DEVICE_ID = "legacy"
DRIFT_THRESHOLD_MS = 300000
TIME_UNIT = "ms"
MAX_UPLOAD_BYTES = 10485760
DEVICE_ID_PATTERN = r"^[a-zA-Z0-9_-]{3,64}$"
IMAGE_HASH_LENGTH = 64

_DEVICE_ID_RE = re.compile(DEVICE_ID_PATTERN)
_IMAGE_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def generate_diagnostic_id() -> str:
    """Generate a UUID string for diagnostics.

    Returns:
        Random UUID string.
    """

    return str(uuid.uuid4())


def compute_idempotency_key(device_id: str, client_ts: int, image_hash: str) -> str:
    """Compute a stable idempotency key for uploads.

    Args:
        device_id: Client device identifier.
        client_ts: Client timestamp in milliseconds.
        image_hash: Lowercase hex image hash.

    Returns:
        SHA-256 hex digest for the upload key.
    """

    payload = f"{device_id}:{client_ts}:{image_hash}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_timezone(value: str) -> str:
    """Validate the timezone string.

    Args:
        value: IANA timezone string.

    Returns:
        The timezone string if valid.

    Raises:
        ValueError: If the timezone is invalid.
    """

    if not value:
        raise ValueError("client_tz is required")
    if ZoneInfo is not None:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid IANA timezone: {value}") from exc
    else:  # pragma: no cover - pytz fallback
        import pytz

        if value not in pytz.all_timezones:
            raise ValueError(f"Invalid IANA timezone: {value}")
    return value


def _validate_positive_int(value: int, field_name: str) -> int:
    """Validate that a value is a positive integer.

    Args:
        value: Integer value to validate.
        field_name: Name of the field for error messages.

    Returns:
        The validated integer.

    Raises:
        ValueError: If value is not a positive integer.
    """

    if value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


class UploadMetadataV1(BaseModel):
    """Metadata payload for M0 upload requests."""

    model_config = ConfigDict(extra="ignore")

    device_id: str = Field(default=LEGACY_DEVICE_ID, description="Client device ID")
    client_ts: int = Field(description="Client timestamp in milliseconds")
    client_tz: str = Field(description="Client timezone (IANA)")
    client_seq: int | None = Field(default=None, description="Client sequence number")
    image_hash: str = Field(description="Lowercase hex image hash")
    app_name: str = Field(description="Foreground application name")
    window_title: str = Field(description="Foreground window title")
    timestamp: int | None = Field(
        default=None, description="Legacy timestamp in seconds"
    )

    @model_validator(mode="before")
    @classmethod
    def apply_legacy_fields(cls, values: Any) -> Any:
        """Apply legacy compatibility transformations."""

        if not isinstance(values, dict):
            return values
        device_id = values.get("device_id")
        if not device_id:
            values["device_id"] = LEGACY_DEVICE_ID
        client_ts = values.get("client_ts")
        timestamp = values.get("timestamp")
        if client_ts is None and timestamp is not None:
            values["client_ts"] = int(timestamp) * 1000
        if values.get("client_ts") is None:
            raise ValueError("client_ts is required")
        return values

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, value: str) -> str:
        """Validate the device ID format."""

        if not _DEVICE_ID_RE.fullmatch(value):
            raise ValueError("device_id must match DEVICE_ID_PATTERN")
        return value

    @field_validator("image_hash")
    @classmethod
    def validate_image_hash(cls, value: str) -> str:
        """Validate the image hash format."""

        if not _IMAGE_HASH_RE.fullmatch(value):
            raise ValueError("image_hash must be 64 lowercase hex characters")
        return value

    @field_validator("client_tz")
    @classmethod
    def validate_client_tz(cls, value: str) -> str:
        """Validate the client timezone."""

        return _validate_timezone(value)

    @field_validator("client_ts")
    @classmethod
    def validate_client_ts(cls, value: int) -> int:
        """Validate the client timestamp."""

        return _validate_positive_int(value, "client_ts")


class LastError(BaseModel):
    """Represents the last client-side error state."""

    model_config = ConfigDict(extra="ignore")

    code: str = Field(description="Error code identifier")
    message: str = Field(description="Error message")
    at_ms: int = Field(description="Timestamp of error in milliseconds")


class ClientCapabilities(BaseModel):
    """Describes client capabilities for M0."""

    model_config = ConfigDict(extra="ignore")

    client_version: str = Field(description="Client version string")
    platform: str = Field(description="Client platform")
    capture: dict[str, Any] = Field(description="Capture capability info")
    upload: dict[str, Any] = Field(description="Upload capability info")


class HeartbeatRequestV1(BaseModel):
    """Heartbeat payload sent from the client."""

    model_config = ConfigDict(extra="ignore")

    device_id: str = Field(default=LEGACY_DEVICE_ID, description="Client device ID")
    client_ts: int = Field(description="Client timestamp in milliseconds")
    client_tz: str = Field(description="Client timezone (IANA)")
    queue_depth: int = Field(description="Upload queue depth")
    last_error: LastError | None = Field(default=None, description="Last error")
    capabilities: ClientCapabilities = Field(description="Client capabilities")

    @model_validator(mode="before")
    @classmethod
    def apply_device_defaults(cls, values: Any) -> Any:
        """Apply legacy defaults for device identifiers."""

        if not isinstance(values, dict):
            return values
        if not values.get("device_id"):
            values["device_id"] = LEGACY_DEVICE_ID
        return values

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, value: str) -> str:
        """Validate the device ID format."""

        if not _DEVICE_ID_RE.fullmatch(value):
            raise ValueError("device_id must match DEVICE_ID_PATTERN")
        return value

    @field_validator("client_tz")
    @classmethod
    def validate_client_tz(cls, value: str) -> str:
        """Validate the client timezone."""

        return _validate_timezone(value)

    @field_validator("client_ts")
    @classmethod
    def validate_client_ts(cls, value: int) -> int:
        """Validate the client timestamp."""

        return _validate_positive_int(value, "client_ts")


class ErrorEnvelope(BaseModel):
    """Standard error response envelope."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field(default="error", description="Envelope status")
    code: str = Field(description="Error code")
    message: str = Field(description="Human-readable error message")
    diagnostic_id: str = Field(description="Diagnostic UUID")
    details: dict[str, Any] | None = Field(default=None, description="Error details")
    server_received_at: int | None = Field(
        default=None,
        description="Server timestamp when the request was received",
    )

    @field_validator("server_received_at")
    @classmethod
    def validate_server_received_at(cls, value: int | None) -> int | None:
        """Validate server timestamps when present."""

        if value is None:
            return value
        return _validate_positive_int(value, "server_received_at")


class DriftInfo(BaseModel):
    """Clock drift diagnostic information."""

    model_config = ConfigDict(extra="ignore")

    estimate: int = Field(description="Estimated drift in milliseconds")
    exceeded: bool = Field(description="Whether drift exceeds threshold")
    threshold: int = Field(description="Drift threshold in milliseconds")
