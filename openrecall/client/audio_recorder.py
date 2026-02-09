"""Audio recorder (Producer) for OpenRecall client.

Captures microphone audio in fixed-duration chunks, saves to WAV,
and enqueues to the local buffer for upload to server.

Phase 2.0: Mic-only recording. System audio deferred.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from openrecall.client.audio_manager import AudioManager
from openrecall.client.buffer import LocalBuffer, get_buffer
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class AudioRecorder(threading.Thread):
    """Background thread that records audio chunks and enqueues them.

    Follows the same Producer pattern as ScreenRecorder/VideoRecorder:
    - Daemon thread with stop event
    - Writes WAV files to client_audio_chunks_path
    - Enqueues to LocalBuffer with metadata type="audio_chunk"
    """

    def __init__(
        self,
        buffer: Optional[LocalBuffer] = None,
        chunk_duration: Optional[int] = None,
        device: Optional[str] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
    ):
        """Initialize the audio recorder.

        Args:
            buffer: LocalBuffer instance. Defaults to global singleton.
            chunk_duration: Chunk duration in seconds. Defaults to settings.
            device: Audio device name/index. Defaults to settings.
            sample_rate: Sample rate. Defaults to settings.
            channels: Channels. Defaults to settings.
        """
        super().__init__(daemon=True, name="AudioRecorder")
        self.buffer = buffer or get_buffer()
        self._chunk_duration = chunk_duration or settings.audio_chunk_duration
        self._device = device if device is not None else (settings.audio_device_mic or None)
        self._sample_rate = sample_rate or settings.audio_sample_rate
        self._channels = channels or settings.audio_channels
        self._stop_event = threading.Event()
        self._manager: Optional[AudioManager] = None

    def run(self) -> None:
        """Main recording loop."""
        logger.info(
            "AudioRecorder started | device=%s | rate=%d | chunk_duration=%ds",
            self._device or "default",
            self._sample_rate,
            self._chunk_duration,
        )

        try:
            self._manager = AudioManager(
                device=self._device,
                sample_rate=self._sample_rate,
                channels=self._channels,
            )
            self._manager.start()
        except Exception as e:
            logger.error(f"AudioRecorder failed to start AudioManager: {e}")
            return

        output_dir = settings.client_audio_chunks_path
        output_dir.mkdir(parents=True, exist_ok=True)

        while not self._stop_event.is_set():
            try:
                chunk_start = time.time()
                chunk_start_utc = datetime.now(timezone.utc)

                # Record for chunk_duration seconds
                audio_data = self._manager.read_chunk(
                    duration_s=self._chunk_duration,
                    stop_event=self._stop_event,
                )

                if audio_data is None:
                    # Stopped during recording
                    break

                chunk_end = time.time()

                # Build filename with UTC timestamp
                ts_str = chunk_start_utc.strftime("%Y-%m-%d_%H-%M-%S")
                wav_filename = f"audio_{ts_str}.wav"
                wav_path = output_dir / wav_filename

                # Save WAV
                AudioManager.save_wav(
                    path=wav_path,
                    data=audio_data,
                    sample_rate=self._sample_rate,
                    channels=self._channels,
                )

                # Compute checksum
                checksum = AudioManager.compute_checksum(wav_path)
                file_size = wav_path.stat().st_size

                # Build metadata
                metadata = {
                    "type": "audio_chunk",
                    "timestamp": int(chunk_start),
                    "start_time": chunk_start,
                    "end_time": chunk_end,
                    "device_name": self._device or "default_mic",
                    "checksum": checksum,
                    "file_size_bytes": file_size,
                    "sample_rate": self._sample_rate,
                    "channels": self._channels,
                    "chunk_filename": wav_filename,
                }

                # Enqueue to buffer
                self.buffer.enqueue_file(wav_path, metadata)
                logger.info(
                    "Audio chunk recorded | file=%s | size_mb=%.2f | duration=%ds",
                    wav_filename,
                    file_size / (1024 * 1024),
                    self._chunk_duration,
                )

            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"AudioRecorder error: {e}")
                    # Brief pause before retry
                    self._stop_event.wait(2.0)

        # Cleanup
        if self._manager:
            self._manager.stop()

        logger.info("AudioRecorder stopped")

    def stop(self) -> None:
        """Signal the recorder to stop. Thread-safe."""
        logger.info("Stopping AudioRecorder...")
        self._stop_event.set()
        if self._manager:
            self._manager.stop()

    def is_stopping(self) -> bool:
        """Check if stop has been requested."""
        return self._stop_event.is_set()
