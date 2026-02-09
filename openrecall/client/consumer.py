"""Uploader Consumer thread for background upload processing.

Implements the Consumer side of Producer-Consumer pattern.
Reads from LocalBuffer and uploads to server with retry/backoff.
"""

import logging
import threading
import time
from pathlib import Path
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

                item_type = item.metadata.get("type")
                if item_type == "video_chunk":
                    target_uploader = "upload_video_chunk"
                elif item_type == "audio_chunk":
                    target_uploader = "upload_audio_chunk"
                else:
                    target_uploader = "upload_screenshot"
                logger.info(
                    "Dispatch buffered item | id=%s | item_type=%s | target=%s",
                    item.id,
                    item_type or "screenshot",
                    target_uploader,
                )
                upload_started_at = time.monotonic()
                video_details = None
                if item_type == "video_chunk":
                    chunk_path = Path(item.image_path)
                    chunk_name = str(item.metadata.get("chunk_filename") or chunk_path.name)
                    file_size_bytes = int(
                        item.metadata.get("file_size_bytes")
                        or (chunk_path.stat().st_size if chunk_path.exists() else 0)
                    )
                    monitor_id = str(item.metadata.get("monitor_id", "") or "legacy")
                    video_details = (chunk_name, file_size_bytes, monitor_id)
                    logger.info(
                        "Uploading video chunk | id=%s | file=%s | size_mb=%.1f | monitor_id=%s",
                        item.id,
                        chunk_name,
                        file_size_bytes / (1024 * 1024),
                        monitor_id,
                    )
                    upload_meta = {
                        k: v
                        for k, v in item.metadata.items()
                        if not str(k).startswith("_")
                    }
                    success = self.uploader.upload_video_chunk(
                        file_path=str(item.image_path),
                        metadata=upload_meta,
                    )
                elif item_type == "audio_chunk":
                    audio_path = Path(item.image_path)
                    audio_name = str(item.metadata.get("chunk_filename") or audio_path.name)
                    file_size_bytes = int(
                        item.metadata.get("file_size_bytes")
                        or (audio_path.stat().st_size if audio_path.exists() else 0)
                    )
                    logger.info(
                        "Uploading audio chunk | id=%s | file=%s | size_mb=%.1f",
                        item.id,
                        audio_name,
                        file_size_bytes / (1024 * 1024),
                    )
                    upload_meta = {
                        k: v
                        for k, v in item.metadata.items()
                        if not str(k).startswith("_")
                    }
                    success = self.uploader.upload_audio_chunk(
                        file_path=str(item.image_path),
                        metadata=upload_meta,
                    )
                else:
                    # Legacy/default path: screenshot image upload.
                    with Image.open(item.image_path) as pil_image:
                        image_array = np.array(pil_image)

                    success = self.uploader.upload_screenshot(
                        image=image_array,
                        timestamp=item.metadata.get("timestamp", 0),
                        active_app=item.metadata.get("active_app", "Unknown"),
                        active_window=item.metadata.get("active_window", "Unknown"),
                    )
                
                if success:
                    # Success: delete from buffer
                    elapsed_s = time.monotonic() - upload_started_at
                    if item_type == "video_chunk":
                        chunk_name, file_size_bytes, monitor_id = video_details or ("unknown", 0, "legacy")
                        self.buffer.commit([item.id])
                        remaining = self.buffer.count()
                        logger.info(
                            "📤 Uploaded video chunk | file=%s | size_mb=%.1f | monitor_id=%s | elapsed=%.2fs | remaining=%s",
                            chunk_name,
                            file_size_bytes / (1024 * 1024),
                            monitor_id,
                            elapsed_s,
                            remaining,
                        )
                    elif item_type == "audio_chunk":
                        self.buffer.commit([item.id])
                        remaining = self.buffer.count()
                        logger.info(
                            "📤 Uploaded audio chunk | file=%s | elapsed=%.2fs | remaining=%s",
                            item.metadata.get("chunk_filename", "unknown"),
                            elapsed_s,
                            remaining,
                        )
                    else:
                        app_name = item.metadata.get("active_app", "Unknown")
                        logger.info(f"📤 Uploaded: {app_name} | ts={item.metadata.get('timestamp', 0)}")
                        self.buffer.commit([item.id])
                    self._retry_count = 0
                else:
                    # Failure: keep files, apply backoff (unless stopping)
                    if not self._stop_event.is_set():
                        if item_type == "video_chunk":
                            chunk_name, file_size_bytes, monitor_id = video_details or ("unknown", 0, "legacy")
                            logger.warning(
                                "Video chunk upload failed | file=%s | size_mb=%.1f | monitor_id=%s",
                                chunk_name,
                                file_size_bytes / (1024 * 1024),
                                monitor_id,
                            )
                        self._handle_failure()
                    
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"Error processing {item.id}: {e}")
                    self._handle_failure()
        
        remaining = self.buffer.count()
        logger.info(f"🛑 Consumer stopped | Remaining in buffer: {remaining}")
    
    def _handle_failure(self) -> None:
        """Handle upload failure with exponential backoff (ADR-0002 schedule)."""
        self._retry_count += 1
        from openrecall.client.upload_queue import UploadQueue
        wait_time = UploadQueue.get_backoff_delay(self._retry_count)
        logger.warning(f"Upload failed. Backing off for {wait_time}s (retry #{self._retry_count})")
        
        # Interruptible sleep - allows immediate exit if stopped
        self._stop_event.wait(timeout=wait_time)
    
    def stop(self) -> None:
        """Signal the consumer to stop. Thread-safe."""
        logger.info("Stopping UploaderConsumer...")
        self._stop_event.set()
    
    def is_stopping(self) -> bool:
        """Check if stop has been requested."""
        return self._stop_event.is_set()
