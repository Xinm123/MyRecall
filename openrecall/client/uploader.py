"""HTTP Uploader for OpenRecall client."""

import logging
import io
import json
import time
from pathlib import Path
from typing import Optional, Any

import numpy as np
import requests
from numpy.typing import NDArray
from PIL import Image

from openrecall.shared.config import settings
from openrecall.shared.utils import _build_request_kwargs

logger = logging.getLogger(__name__)

ImageArray = NDArray[np.uint8]

# Settings store for hot-reload support
_settings_store: Optional[Any] = None


def _get_settings_store():
    """Get or create the settings store singleton."""
    global _settings_store
    if _settings_store is None:
        from openrecall.client.database import ClientSettingsStore

        db_path = Path(settings.client_data_dir) / "client.db"
        _settings_store = ClientSettingsStore(db_path)
    return _settings_store


def _get_api_url() -> str:
    """Get the API URL, preferring runtime settings over TOML config.

    Checks ClientSettingsStore first (for hot-reload), falls back to TOML settings.
    """
    store = _get_settings_store()

    # Try to get edge_base_url from database first (user may have updated it)
    db_url = store.get("edge_base_url", "").strip()
    if db_url:
        # edge_base_url is base URL like http://localhost:8083
        # Return the /api endpoint
        return f"{db_url.rstrip('/')}/api"

    # Fall back to TOML config
    return settings.api_url


class HTTPUploader:
    """HTTP client for uploading screenshots to the OpenRecall server.

    Attributes:
        _api_url_override: Optional override for the API URL.
        timeout: Request timeout in seconds.
    """

    def __init__(self, api_url: str | None = None, timeout: int | None = None):
        """Initialize the uploader.

        Args:
            api_url: Override the default API URL from settings.
            timeout: Request timeout in seconds. Defaults to settings.upload_timeout.
        """
        self._api_url_override: str | None = api_url
        self.timeout: int = timeout or settings.upload_timeout

    @property
    def api_url(self) -> str:
        """Get the current API URL, checking for runtime updates."""
        if self._api_url_override:
            return self._api_url_override
        return _get_api_url()

    def health_check(self) -> bool:
        """Check if the server is healthy.

        Returns:
            True if server responds with status "ok", False otherwise.
        """
        try:
            url = f"{self.api_url}/health"
            response = requests.get(url, **_build_request_kwargs(url, self.timeout))
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
        image: ImageArray,
        timestamp: int,
        active_app: str,
        active_window: str,
    ) -> bool:
        """Upload a screenshot to the server.

        Args:
            image: Screenshot as numpy array (RGB).
            timestamp: Unix timestamp when screenshot was taken.
            active_app: Name of the active application.
            active_window: Title of the active window.

        Returns:
            True if upload succeeded, False otherwise.
        """
        try:
            # Convert numpy array to PNG bytes
            img_pil = Image.fromarray(image)
            img_byte_arr = io.BytesIO()
            img_pil.save(img_byte_arr, format="PNG")
            img_byte_arr.seek(0)

            metadata = {
                "timestamp": timestamp,
                "app_name": active_app,
                "window_title": active_window,
            }

            response = requests.post(
                f"{self.api_url}/upload",
                files={"file": ("screenshot.png", img_byte_arr, "image/png")},
                data={"metadata": json.dumps(metadata)},
                **_build_request_kwargs(f"{self.api_url}/upload", self.timeout),
            )

            # Accept both 200 (old sync) and 202 (new async) as success
            if response.status_code in (200, 202):
                return True
            else:
                logger.error(
                    "Upload failed: %s - %s", response.status_code, response.text
                )
                return False

        except requests.RequestException as e:
            logger.error("Upload error: %s", e)
            return False


# Module-level singleton for convenience
_uploader: HTTPUploader | None = None


def get_uploader() -> HTTPUploader:
    """Get or create the global HTTPUploader instance.

    Returns:
        The global HTTPUploader instance.
    """
    global _uploader
    if _uploader is None:
        _uploader = HTTPUploader()
    return _uploader
