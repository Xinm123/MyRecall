"""Audio device manager for OpenRecall client.

Thin wrapper around sounddevice for audio capture.
Provides device enumeration, stream management, and WAV output.

Phase 2.0: Mic-only capture. System audio deferred.
"""

import hashlib
import logging
import queue
import struct
import threading
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class AudioManager:
    """Low-level audio device wrapper using sounddevice.

    Manages an InputStream, buffers audio into a queue, and provides
    blocking read_chunk() for collecting fixed-duration audio segments.

    Args:
        device: Device name or index. Empty string = system default.
        sample_rate: Sample rate in Hz (default: 16000).
        channels: Number of channels (default: 1 = mono).
    """

    def __init__(
        self,
        device: Optional[str] = None,
        sample_rate: int = 16000,
        channels: int = 1,
    ):
        self._device = device if device else None
        self._sample_rate = sample_rate
        self._channels = channels
        self._stream = None
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._lock = threading.Lock()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    @staticmethod
    def get_available_devices() -> list:
        """Return list of available audio devices."""
        try:
            import sounddevice as sd
            return sd.query_devices()
        except Exception as e:
            logger.error(f"Failed to query audio devices: {e}")
            return []

    def start(self) -> None:
        """Open the audio input stream."""
        with self._lock:
            if self._running:
                return

            try:
                import sounddevice as sd

                self._stream = sd.InputStream(
                    device=self._device,
                    samplerate=self._sample_rate,
                    channels=self._channels,
                    dtype="int16",
                    callback=self._audio_callback,
                    blocksize=1024,
                )
                self._stream.start()
                self._running = True
                logger.info(
                    "AudioManager started | device=%s | rate=%d | channels=%d",
                    self._device or "default",
                    self._sample_rate,
                    self._channels,
                )
            except Exception as e:
                logger.error(f"Failed to start audio stream: {e}")
                raise

    def stop(self) -> None:
        """Stop and close the audio stream."""
        with self._lock:
            if not self._running:
                return
            self._running = False

            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.warning(f"Error closing audio stream: {e}")
                finally:
                    self._stream = None

            # Flush queue
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break

            logger.info("AudioManager stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def _audio_callback(self, indata, frames, time_info, status):
        """Sounddevice callback — copies audio data to internal queue."""
        if status:
            logger.warning(f"Audio callback status: {status}")
        # Copy to avoid buffer reuse issues
        self._queue.put(indata.copy())

    def read_chunk(self, duration_s: float, stop_event: Optional[threading.Event] = None) -> Optional[np.ndarray]:
        """Block and collect audio for the given duration.

        Args:
            duration_s: Duration in seconds to collect.
            stop_event: Optional event to check for early termination.

        Returns:
            numpy int16 array of shape (samples, channels), or None if stopped.
        """
        target_samples = int(duration_s * self._sample_rate)
        chunks = []
        collected = 0

        while collected < target_samples:
            if stop_event and stop_event.is_set():
                return None
            try:
                data = self._queue.get(timeout=1.0)
                chunks.append(data)
                collected += data.shape[0]
            except queue.Empty:
                if not self._running:
                    return None
                continue

        if not chunks:
            return None

        audio = np.concatenate(chunks, axis=0)
        # Trim to exact duration
        return audio[:target_samples]

    @staticmethod
    def save_wav(
        path: Path,
        data: np.ndarray,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> None:
        """Save numpy int16 audio data as a WAV file.

        Args:
            path: Output file path.
            data: Audio data as int16 numpy array.
            sample_rate: Sample rate in Hz.
            channels: Number of channels.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(sample_rate)
            wf.writeframes(data.tobytes())

    @staticmethod
    def compute_checksum(path: Path) -> str:
        """Compute SHA-256 checksum of a file.

        Args:
            path: File path.

        Returns:
            Hex digest string prefixed with 'sha256:'.
        """
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"
