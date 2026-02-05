"""Uploader Consumer thread for background upload processing.

Implements the Consumer side of Producer-Consumer pattern.
Reads from LocalBuffer and uploads to server with retry/backoff.
"""

import logging
import threading
from typing import Callable, Optional

import numpy as np
from PIL import Image

from openrecall.client.buffer import LocalBuffer, get_buffer
from openrecall.client.uploader import HTTPUploader, get_uploader

logger = logging.getLogger(__name__)


class UploaderConsumer(threading.Thread):
    """Background thread that consumes buffered items and uploads to server.

    Features:
    - Exponential backoff on failure (max 60s)
    - Interruptible sleep (responds to stop signal immediately)
    - Only deletes files after confirmed upload
    """

    def __init__(
        self,
        buffer: Optional[LocalBuffer] = None,
        uploader: Optional[HTTPUploader] = None,
        should_upload: Optional[Callable[[], bool]] = None,
        name: str = "UploaderConsumer",
    ):
        """Initialize the consumer thread.

        Args:
            buffer: LocalBuffer instance. Defaults to global singleton.
            uploader: HTTPUploader instance. Defaults to global singleton.
            name: Thread name for debugging.
        """
        super().__init__(name=name, daemon=False)
        self.buffer = buffer or get_buffer()
        self.uploader = uploader or get_uploader()
        self.should_upload = should_upload or (lambda: True)
        self._stop_event = threading.Event()
        self._retry_count = 0

    def run(self) -> None:
        """Main consumer loop. Runs until stop() is called."""
        pending = self.buffer.count()
        logger.info(f"🚀 Consumer started | Pending uploads: {pending}")

        while not self._stop_event.is_set():
            if not self.should_upload():
                self._stop_event.wait(timeout=1.0)
                continue

            # Get next item from buffer
            items = self.buffer.get_next_batch(limit=1)

            if not items:
                # Buffer empty, wait for new items (interruptible)
                self._stop_event.wait(timeout=1.0)
                continue

            item = items[0]

            try:
                # Check if stop requested before upload
                if self._stop_event.is_set():
                    break

                # Load image from disk
                pil_image = Image.open(item.image_path)
                image_array = np.array(pil_image)

                # Attempt upload
                success = self.uploader.upload_screenshot(
                    image=image_array,
                    timestamp=item.metadata.get("timestamp", 0),
                    active_app=item.metadata.get("active_app", "Unknown"),
                    active_window=item.metadata.get("active_window", "Unknown"),
                    client_seq=item.metadata.get("client_seq"),
                )

                if success:
                    # Success: delete from buffer
                    app_name = item.metadata.get("active_app", "Unknown")
                    logger.info(
                        f"📤 Uploaded: {app_name} | ts={item.metadata.get('timestamp', 0)}"
                    )
                    self.buffer.commit([item.id])
                    self._retry_count = 0
                else:
                    # Failure: keep files, apply backoff (unless stopping)
                    if not self._stop_event.is_set():
                        self._handle_failure()

            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"Error processing {item.id}: {e}")
                    self._handle_failure()

        remaining = self.buffer.count()
        logger.info(f"🛑 Consumer stopped | Remaining in buffer: {remaining}")

    def _handle_failure(self) -> None:
        """Handle upload failure with exponential backoff."""
        self._retry_count += 1
        wait_time = min(2**self._retry_count, 60)  # Max 60s
        logger.warning(
            f"Upload failed. Backing off for {wait_time}s (retry #{self._retry_count})"
        )

        # Interruptible sleep - allows immediate exit if stopped
        self._stop_event.wait(timeout=wait_time)

    def stop(self) -> None:
        """Signal the consumer to stop. Thread-safe."""
        logger.info("Stopping UploaderConsumer...")
        self._stop_event.set()

    def is_stopping(self) -> bool:
        """Check if stop has been requested."""
        return self._stop_event.is_set()
