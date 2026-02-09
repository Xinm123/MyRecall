"""HTTP Uploader for OpenRecall client.

Handles communication with the OpenRecall server API.
Provides health check and screenshot upload functionality.
"""

import time
import json
import io
from typing import Optional

import numpy as np
import requests
from PIL import Image

from openrecall.shared.config import settings


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
            response = requests.get(
                f"{self.api_url}/health",
                timeout=self.timeout
            )
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
            img_pil.save(img_byte_arr, format='PNG')
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
                timeout=self.timeout
            )
            
            # Accept both 200 (old sync) and 202 (new async) as success
            if response.status_code in (200, 202):
                return True
            else:
                print(f"Upload failed: {response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            print(f"Upload error: {e}")
            return False

    def upload_video_chunk(
        self,
        file_path: str,
        metadata: dict,
    ) -> bool:
        """Upload a video chunk to the server with resume support.

        Args:
            file_path: Path to the .mp4 video chunk file.
            metadata: Dictionary with type, checksum, file_size_bytes, etc.

        Returns:
            True if upload succeeded, False otherwise.
        """
        import hashlib
        from pathlib import Path

        chunk_path = Path(file_path)
        if not chunk_path.exists():
            print(f"Video chunk not found: {file_path}")
            return False

        checksum = metadata.get("checksum", "")

        # Check for resume: query server for bytes already received
        bytes_received = 0
        if checksum:
            try:
                resp = requests.get(
                    f"{self.api_url}/upload/status",
                    params={"checksum": checksum},
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "completed":
                        return True  # Already uploaded
                    bytes_received = data.get("bytes_received", 0)
            except requests.RequestException:
                pass  # Proceed with full upload

        try:
            total_size = chunk_path.stat().st_size
            upload_metadata = dict(metadata)
            upload_metadata["file_size_bytes"] = total_size
            # Backward compatibility: normalize app/window keys for server ingestion.
            if "app_name" not in upload_metadata and "active_app" in upload_metadata:
                upload_metadata["app_name"] = upload_metadata.get("active_app")
            if "window_title" not in upload_metadata and "active_window" in upload_metadata:
                upload_metadata["window_title"] = upload_metadata.get("active_window")

            with open(chunk_path, "rb") as f:
                if bytes_received > 0:
                    f.seek(bytes_received)

                headers = {}
                if bytes_received > 0:
                    headers["X-Upload-Offset"] = str(bytes_received)

                response = requests.post(
                    f"{self.api_url}/upload",
                    files={"file": (chunk_path.name, f, "video/mp4")},
                    data={"metadata": json.dumps(upload_metadata)},
                    headers=headers,
                    timeout=max(self.timeout, 120),  # Video uploads need more time
                )

            if response.status_code in (200, 202):
                return True
            else:
                print(f"Video upload failed: {response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            print(f"Video upload error: {e}")
            return False

    def upload_audio_chunk(
        self,
        file_path: str,
        metadata: dict,
    ) -> bool:
        """Upload an audio chunk (WAV) to the server.

        Args:
            file_path: Path to the .wav audio chunk file.
            metadata: Dictionary with type, checksum, file_size_bytes, device_name, etc.

        Returns:
            True if upload succeeded, False otherwise.
        """
        from pathlib import Path

        chunk_path = Path(file_path)
        if not chunk_path.exists():
            print(f"Audio chunk not found: {file_path}")
            return False

        try:
            upload_metadata = dict(metadata)
            upload_metadata["file_size_bytes"] = chunk_path.stat().st_size

            with open(chunk_path, "rb") as f:
                response = requests.post(
                    f"{self.api_url}/upload",
                    files={"file": (chunk_path.name, f, "audio/wav")},
                    data={"metadata": json.dumps(upload_metadata)},
                    timeout=max(self.timeout, 60),
                )

            if response.status_code in (200, 202):
                return True
            else:
                print(f"Audio upload failed: {response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            print(f"Audio upload error: {e}")
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
