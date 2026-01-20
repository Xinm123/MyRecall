"""HTTP Uploader for OpenRecall client.

Handles communication with the OpenRecall server API.
Provides health check and screenshot upload functionality.
"""

import time
from typing import Optional

import numpy as np
import requests

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
            payload = {
                "image": image.flatten().tolist(),
                "shape": list(image.shape),
                "dtype": str(image.dtype),
                "timestamp": timestamp,
                "active_app": active_app,
                "active_window": active_window,
            }
            
            response = requests.post(
                f"{self.api_url}/upload",
                json=payload,
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
