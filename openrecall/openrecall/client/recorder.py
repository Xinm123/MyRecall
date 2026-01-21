"""Screenshot recorder (Producer) for OpenRecall client.

Captures screenshots, detects changes, and queues them to the local buffer.
The Consumer thread (UploaderConsumer) handles uploading to server.
"""

import json
import logging
import os
import time
import urllib.parse
from typing import List, Optional

import mss
import numpy as np
import requests
from PIL import Image

from openrecall.shared.config import settings
from openrecall.client.buffer import LocalBuffer, get_buffer
from openrecall.client.consumer import UploaderConsumer
from openrecall.shared.utils import (
    get_active_app_name,
    get_active_window_title,
    is_user_active,
)

logger = logging.getLogger(__name__)


def mean_structured_similarity_index(
    img1: np.ndarray, img2: np.ndarray, L: int = 255
) -> float:
    """Calculates the Mean Structural Similarity Index (MSSIM) between two images.

    Args:
        img1: The first image as a NumPy array (RGB).
        img2: The second image as a NumPy array (RGB).
        L: The dynamic range of the pixel values (default is 255).

    Returns:
        The MSSIM value between the two images (float between -1 and 1).
    """
    K1, K2 = 0.01, 0.03
    C1, C2 = (K1 * L) ** 2, (K2 * L) ** 2

    def rgb2gray(img: np.ndarray) -> np.ndarray:
        """Converts an RGB image to grayscale."""
        return 0.2989 * img[..., 0] + 0.5870 * img[..., 1] + 0.1140 * img[..., 2]

    img1_gray: np.ndarray = rgb2gray(img1)
    img2_gray: np.ndarray = rgb2gray(img2)
    mu1: float = np.mean(img1_gray)
    mu2: float = np.mean(img2_gray)
    sigma1_sq = np.var(img1_gray)
    sigma2_sq = np.var(img2_gray)
    sigma12 = np.mean((img1_gray - mu1) * (img2_gray - mu2))
    ssim_index = ((2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)) / (
        (mu1**2 + mu2**2 + C1) * (sigma1_sq + sigma2_sq + C2)
    )
    return ssim_index


def is_similar(
    img1: np.ndarray, img2: np.ndarray, similarity_threshold: Optional[float] = None
) -> bool:
    """Checks if two images are similar based on MSSIM.

    Args:
        img1: The first image as a NumPy array.
        img2: The second image as a NumPy array.
        similarity_threshold: The threshold above which images are considered similar.

    Returns:
        True if the images are similar, False otherwise.
    """
    if settings.disable_similarity_filter:
        return False
    similarity: float = compute_similarity(img1, img2)
    threshold = similarity_threshold if similarity_threshold is not None else settings.similarity_threshold
    return similarity >= threshold


def take_screenshots() -> List[np.ndarray]:
    """Takes screenshots of all connected monitors or just the primary one.

    Depending on the `settings.primary_monitor_only` flag, captures either
    all monitors or only the primary monitor (index 1 in mss.monitors).

    Returns:
        A list of screenshots, where each screenshot is a NumPy array (RGB).
    """
    screenshots: List[np.ndarray] = []
    with mss.mss() as sct:
        # sct.monitors[0] is the combined view of all monitors
        # sct.monitors[1] is the primary monitor
        # sct.monitors[2:] are other monitors
        monitor_indices = range(1, len(sct.monitors))  # Skip the 'all monitors' entry

        if settings.primary_monitor_only:
            monitor_indices = [1]  # Only index 1 corresponds to the primary monitor

        for i in monitor_indices:
            # Ensure the index is valid before attempting to grab
            if i < len(sct.monitors):
                monitor_info = sct.monitors[i]
                # Grab the screen
                sct_img = sct.grab(monitor_info)
                # Convert to numpy array and change BGRA to RGB
                screenshot = np.array(sct_img)[:, :, [2, 1, 0]]
                screenshots.append(screenshot)
            else:
                print(f"Warning: Monitor index {i} out of bounds. Skipping.")

    return screenshots


def resize_image(image: np.ndarray, max_dim: int = 800) -> np.ndarray:
    """
    Resizes an image to fit within a maximum dimension while maintaining aspect ratio.
    Args:
        image: The input image as a NumPy array (RGB).
        max_dim: The maximum dimension for resizing.
    Returns:
        The resized image as a NumPy array (RGB).
    """
    pil_image = Image.fromarray(image)
    pil_image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    return np.array(pil_image)


def compute_similarity(img1: np.ndarray, img2: np.ndarray) -> float:
    compress_img1: np.ndarray = resize_image(img1)
    compress_img2: np.ndarray = resize_image(img2)
    return mean_structured_similarity_index(compress_img1, compress_img2)


class ScreenRecorder:
    """Producer: captures screenshots and enqueues to local buffer.
    
    Manages the consumer thread lifecycle and provides graceful shutdown.
    """
    
    def __init__(
        self,
        buffer: Optional[LocalBuffer] = None,
        consumer: Optional[UploaderConsumer] = None,
    ):
        """Initialize the recorder.
        
        Args:
            buffer: LocalBuffer instance. Defaults to global singleton.
            consumer: UploaderConsumer instance. Creates new if not provided.
        """
        self.buffer = buffer or get_buffer()
        self._stop_requested = False
        
        # Phase 8.2: Runtime configuration state
        self.recording_enabled = True
        self.upload_enabled = True
        self.last_heartbeat_time = 0
        self._no_change_cycles = 0
        self._warned_capture_issue = False
        self.consumer = consumer or UploaderConsumer(
            buffer=self.buffer,
            should_upload=lambda: self.upload_enabled,
        )
    
    def start(self) -> None:
        """Start the consumer thread."""
        if not self.consumer.is_alive():
            self.consumer.start()
    
    def _send_heartbeat(self) -> None:
        """Send heartbeat to server and sync runtime configuration.
        
        Phase 8.2: Periodically registers client activity and fetches current
        runtime settings (recording_enabled, upload_enabled, etc.) from server.
        """
        try:
            url = f"{settings.api_url.rstrip('/')}/heartbeat"
            parsed = urllib.parse.urlparse(url)
            is_loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}

            request_kwargs = {"timeout": 2}
            if is_loopback:
                request_kwargs["proxies"] = {"http": None, "https": None}

            response = requests.post(url, **request_kwargs)
            response.raise_for_status()

            data = response.json()
            config = data.get("config", {})
            self.recording_enabled = config.get("recording_enabled", True)
            self.upload_enabled = config.get("upload_enabled", True)
            if settings.debug:
                logger.debug(
                    f"Heartbeat synced: recording={self.recording_enabled}, "
                    f"upload={self.upload_enabled}"
                )
        except requests.RequestException as e:
            logger.warning(f"Heartbeat failed (network): {e}")
        except Exception as e:
            logger.warning(f"Heartbeat failed: {e}")
    
    def stop(self) -> None:
        """Stop the recorder and consumer thread gracefully."""
        self._stop_requested = True
        self.consumer.stop()
        if self.consumer.is_alive():
            self.consumer.join(timeout=2.0)  # Wait up to 2s for clean exit
    
    def run_capture_loop(self) -> None:
        """Main capture loop. Runs until stop() is called.
        
        Captures screenshots, detects changes, and enqueues to buffer.
        Blocks only on disk I/O, never on network.
        """
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        
        # Start the consumer thread
        self.start()
        
        logger.info("🎥 Recorder started (Producer-Consumer mode)")
        logger.info(f"   Monitors: {'Primary only' if settings.primary_monitor_only else 'All'}")
        
        last_screenshots: List[np.ndarray] = take_screenshots()
        logger.info(f"   Tracking {len(last_screenshots)} monitor(s)")

        while not self._stop_requested:
            # Phase 8.2: Sync runtime configuration every 5 seconds
            current_time = time.time()
            if current_time - self.last_heartbeat_time > 5:
                self._send_heartbeat()
                self.last_heartbeat_time = current_time
            
            # Phase 8.2: Rule 1 - Stop recording if recording_enabled=False
            if not self.recording_enabled:
                logger.info("⏸️  Recording paused (recording_enabled=False)")
                time.sleep(1)
                continue
            
            if not is_user_active():
                if settings.debug:
                    logger.debug("User inactive, skipping capture cycle")
                time.sleep(settings.capture_interval)
                continue

            screenshots = take_screenshots()
            if not screenshots:
                if settings.debug:
                    logger.debug("No screenshots captured, skipping capture cycle")
                time.sleep(settings.capture_interval)
                continue

            if not self._warned_capture_issue:
                try:
                    sample = screenshots[0]
                    if float(np.mean(sample)) < 1.0 and float(np.std(sample)) < 1.0:
                        self._warned_capture_issue = True
                        logger.warning(
                            "Captured frames look blank. On macOS this usually means missing Screen Recording permission "
                            "(System Settings → Privacy & Security → Screen Recording)."
                        )
                except Exception:
                    pass

            if len(last_screenshots) != len(screenshots):
                last_screenshots = screenshots
                time.sleep(settings.capture_interval)
                continue

            captured_any = False
            max_similarity = -1.0
            for i, screenshot in enumerate(screenshots):
                last_screenshot = last_screenshots[i]

                if settings.disable_similarity_filter:
                    should_capture = True
                    similarity = None
                else:
                    similarity = compute_similarity(screenshot, last_screenshot)
                    max_similarity = max(max_similarity, similarity)
                    should_capture = similarity < settings.similarity_threshold

                if should_capture:
                    captured_any = True
                    last_screenshots[i] = screenshot

                    try:
                        image = Image.fromarray(screenshot)
                        timestamp = int(time.time())

                        if settings.client_save_local_screenshots:
                            filepath = settings.client_screenshots_path / f"{timestamp}.webp"
                            image.save(str(filepath), format="webp", lossless=True)

                        metadata = {
                            "timestamp": timestamp,
                            "active_app": get_active_app_name() or "Unknown App",
                            "active_window": get_active_window_title() or "Unknown Title",
                        }

                        self.buffer.enqueue(image, metadata)
                        if not self.upload_enabled:
                            logger.debug("Upload disabled: buffered locally (will upload when enabled)")
                    except Exception:
                        logger.exception("Failed to persist buffered screenshot")

            if captured_any:
                self._no_change_cycles = 0
            else:
                self._no_change_cycles += 1
                if settings.debug and self._no_change_cycles in {6, 30, 120}:
                    msg = (
                        f"No new frames captured for {self._no_change_cycles} cycles. "
                        f"Try OPENRECALL_DISABLE_SIMILARITY_FILTER=true or raise OPENRECALL_SIMILARITY_THRESHOLD. "
                        f"Last max MSSIM={max_similarity:.4f} threshold={settings.similarity_threshold}."
                    )
                    logger.debug(msg)

            time.sleep(settings.capture_interval)


# Module-level singleton for backwards compatibility
_recorder: Optional[ScreenRecorder] = None


def get_recorder() -> ScreenRecorder:
    """Get or create the global ScreenRecorder instance."""
    global _recorder
    if _recorder is None:
        _recorder = ScreenRecorder()
    return _recorder


def record_screenshots_thread() -> None:
    """Legacy function for backwards compatibility.
    
    Wraps the new ScreenRecorder class.
    """
    recorder = get_recorder()
    recorder.run_capture_loop()
