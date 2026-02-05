"""Device token authentication utilities for M0 cross-machine contract."""

import json
import logging
import time
from dataclasses import dataclass
from typing import Tuple

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Base authentication error."""

    def __init__(self, code: str, message: str, status_code: int = 401):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthUnauthorizedError(AuthError):
    """401 Unauthorized - missing or invalid token."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__("AUTH_UNAUTHORIZED", message, 401)


class AuthForbiddenError(AuthError):
    """403 Forbidden - valid token but wrong device or disabled."""

    def __init__(self, message: str = "Access denied"):
        super().__init__("AUTH_FORBIDDEN", message, 403)


@dataclass
class DeviceTokenConfig:
    """Token configuration for a device."""

    active_token: str
    previous_token: str = ""
    previous_valid_until_ms: int = 0


def parse_device_tokens() -> dict[str, DeviceTokenConfig]:
    """Parse device tokens from settings."""
    try:
        raw = json.loads(settings.device_tokens_json)
        result = {}
        for device_id, config in raw.items():
            result[device_id] = DeviceTokenConfig(
                active_token=config.get("active_token", ""),
                previous_token=config.get("previous_token", ""),
                previous_valid_until_ms=config.get("previous_valid_until_ms", 0),
            )
        return result
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"Failed to parse device tokens: {e}")
        return {}


def parse_bearer_token(auth_header: str | None) -> str | None:
    """Extract token from Authorization header."""
    if not auth_header:
        return None
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:].strip()


def resolve_device_from_token(token: str) -> str | None:
    """Find device_id that owns this token."""
    if not token:
        return None
    tokens = parse_device_tokens()
    now_ms = int(time.time() * 1000)

    for device_id, config in tokens.items():
        # Check active token
        if config.active_token == token:
            return device_id
        # Check previous token if still valid
        if config.previous_token == token and config.previous_valid_until_ms > now_ms:
            return device_id

    return None


def require_device_auth(
    auth_header: str | None,
    requested_device_id: str | None = None,
) -> Tuple[str, str]:
    """Validate auth and return (device_id, auth_mode).

    Args:
        auth_header: The Authorization header value
        requested_device_id: The device_id from request metadata (if any)

    Returns:
        Tuple of (resolved_device_id, auth_mode)

    Raises:
        AuthUnauthorizedError: If auth required but missing/invalid
        AuthForbiddenError: If token valid but device mismatch
    """
    auth_mode = settings.auth_mode

    # Disabled mode - skip all auth
    if auth_mode == "disabled":
        device_id = requested_device_id or settings.legacy_device_id
        return device_id, auth_mode

    # Parse token
    token = parse_bearer_token(auth_header)

    # No token provided
    if not token:
        if auth_mode == "strict":
            raise AuthUnauthorizedError("Authorization header required")
        # Permissive mode without token - use legacy device
        device_id = requested_device_id or settings.legacy_device_id
        logger.warning(f"Permissive mode: no auth, using device_id={device_id}")
        return device_id, auth_mode

    # Resolve device from token
    token_device = resolve_device_from_token(token)

    if not token_device:
        raise AuthUnauthorizedError("Invalid or unknown token")

    # If requested device specified, must match token's device
    if requested_device_id and requested_device_id != token_device:
        raise AuthForbiddenError(
            f"Token belongs to device '{token_device}', not '{requested_device_id}'"
        )

    return token_device, auth_mode
