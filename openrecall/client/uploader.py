"""HTTP Uploader for OpenRecall client.

Handles communication with the OpenRecall server API.
Provides health check and screenshot upload functionality.
"""

import hashlib
import io
import json
import logging
import platform
import time
from typing import Any, Optional

import numpy as np
import requests
from PIL import Image

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

CLIENT_VERSION = "3.0.0"


def _get_device_id() -> str:
    """Get device ID from settings or generate from hostname."""
    if settings.device_id:
        return settings.device_id
    hostname = platform.node() or "unknown"
    sanitized = "".join(c if c.isalnum() or c in "_-" else "_" for c in hostname)
    if len(sanitized) < 3:
        sanitized = sanitized + "_dev"
    return sanitized[:64]


def _get_client_tz() -> str:
    """Get client timezone as IANA name (e.g., 'Asia/Shanghai', 'America/New_York')."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        local_tz = datetime.now().astimezone().tzinfo
        if local_tz is not None:
            tz_name = str(local_tz)
            if "/" in tz_name or tz_name == "UTC":
                return tz_name
    except Exception:
        pass

    try:
        import subprocess

        result = subprocess.run(
            ["readlink", "/etc/localtime"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0 and "zoneinfo/" in result.stdout:
            parts = result.stdout.strip().split("zoneinfo/")
            if len(parts) == 2 and "/" in parts[1]:
                return parts[1]
    except Exception:
        pass

    return "UTC"


def _compute_image_hash(image_bytes: bytes) -> str:
    """Compute SHA-256 hash of image bytes."""
    return hashlib.sha256(image_bytes).hexdigest()


def get_client_capabilities() -> dict[str, Any]:
    """Build client capabilities dict for heartbeat."""
    return {
        "client_version": CLIENT_VERSION,
        "platform": platform.system(),
        "capture": {"primary_monitor_only": settings.primary_monitor_only},
        "upload": {"formats": ["png"], "hash": "sha256"},
    }


class HTTPUploader:
    """HTTP client for uploading screenshots to the OpenRecall server.

    Attributes:
        api_url: Base URL for the API endpoints.
        timeout: Request timeout in seconds.
    """

    def __init__(self, api_url: Optional[str] = None, timeout: Optional[int] = None):
        """Initialize the uploader.

        Args:
            api_url: Override the default API URL from settings.
            timeout: Request timeout in seconds. Defaults to settings.upload_timeout.
        """
        self.api_url = api_url or settings.api_url
        self.timeout = timeout or settings.upload_timeout

    def health_check(self) -> bool:
        """Check if the server is healthy.

        Returns:
            True if server responds with status "ok", False otherwise.
        """
        try:
            response = requests.get(f"{self.api_url}/health", timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                return data.get("status") == "ok"
            return False
        except requests.RequestException:
            return False

    def wait_for_server(self, max_retries: int = 10, retry_delay: float = 1.0) -> bool:
        """Wait for the server to become available.

        Args:
            max_retries: Maximum number of retry attempts.
            retry_delay: Delay between retries in seconds.

        Returns:
            True if server became available, False if max retries exceeded.
        """
        for attempt in range(max_retries):
            if self.health_check():
                return True
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
        return False

    def upload_screenshot(
        self,
        image: np.ndarray,
        timestamp: int,
        active_app: str,
        active_window: str,
        client_seq: Optional[int] = None,
    ) -> bool:
        """Upload a screenshot to the server using M0 contract.

        Args:
            image: Screenshot as numpy array (RGB).
            timestamp: Unix timestamp when screenshot was taken (seconds).
            active_app: Name of the active application.
            active_window: Title of the active window.
            client_seq: Optional monotonic sequence number.

        Returns:
            True if upload succeeded, False otherwise.
        """
        try:
            img_pil = Image.fromarray(image)
            img_byte_arr = io.BytesIO()
            img_pil.save(img_byte_arr, format="PNG")
            png_bytes = img_byte_arr.getvalue()
            img_byte_arr.seek(0)

            image_hash = _compute_image_hash(png_bytes)
            device_id = _get_device_id()
            client_ts = timestamp * 1000
            client_tz = _get_client_tz()

            metadata: dict[str, Any] = {
                "device_id": device_id,
                "client_ts": client_ts,
                "client_tz": client_tz,
                "image_hash": image_hash,
                "app_name": active_app,
                "window_title": active_window,
                "timestamp": timestamp,
            }
            if client_seq is not None:
                metadata["client_seq"] = client_seq

            headers = {}
            if settings.device_token:
                headers["Authorization"] = f"Bearer {settings.device_token}"

            response = requests.post(
                f"{self.api_url}/upload",
                files={"file": ("screenshot.png", img_byte_arr, "image/png")},
                data={"metadata": json.dumps(metadata)},
                headers=headers,
                timeout=self.timeout,
            )

            if response.status_code in (200, 202):
                return True
            else:
                logger.warning(
                    f"Upload failed: {response.status_code} - {response.text}"
                )
                return False

        except requests.RequestException as e:
            logger.error(f"Upload error: {e}")
            return False


# Module-level singleton for convenience
_uploader: Optional[HTTPUploader] = None


def get_uploader() -> HTTPUploader:
    """Get or create the global HTTPUploader instance.

    Returns:
        The global HTTPUploader instance.
    """
    global _uploader
    if _uploader is None:
        _uploader = HTTPUploader()
    return _uploader
