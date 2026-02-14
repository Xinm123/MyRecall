"""Audio recorder that manages capture devices and enqueues chunks to buffer.

Implements the Producer side of the audio capture pipeline.
"""

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

from openrecall.client.buffer import LocalBuffer, get_buffer
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Manages system + mic AudioManagers, enqueues WAV chunks to buffer.

    Features:
    - Starts AudioManager instances for configured devices
    - Computes SHA256 checksum for each chunk
    - Enqueues chunks with metadata to LocalBuffer
    - Graceful shutdown
    """

    def __init__(
        self,
        buffer: Optional[LocalBuffer] = None,
    ):
        self.buffer = buffer or get_buffer()
        self._managers = []
        self._running = False
        self._chunk_start_times: dict = {}  # Maps chunk_path -> actual start time

    def start(self) -> None:
        """Start audio recording for configured devices."""
        if self._running:
            logger.warning("AudioRecorder already running")
            return

        if not settings.audio_enabled:
            logger.info("Audio capture disabled by configuration")
            return

        from openrecall.client.audio_manager import AudioManager

        output_dir = settings.client_audio_chunks_path
        output_dir.mkdir(parents=True, exist_ok=True)

        devices_started = 0

        # Start microphone capture
        mic_device = settings.audio_device_mic
        if mic_device:
            try:
                mgr = AudioManager(
                    device_name=mic_device,
                    sample_rate=settings.audio_sample_rate,
                    channels=settings.audio_channels,
                    chunk_duration=settings.audio_chunk_duration,
                    output_dir=output_dir,
                    on_chunk_complete=lambda path,
                    duration,
                    dn=mic_device: self._on_chunk_complete(path, dn, duration),
                )
                mgr.start()
                if mgr.is_alive():
                    self._managers.append(mgr)
                    devices_started += 1
                    logger.info("🎤 [AUDIO] Microphone capture started: %s", mic_device)
            except Exception as e:
                logger.warning(
                    f"Failed to start microphone capture ({mic_device}): {e}"
                )
        else:
            # Try default input device
            try:
                from openrecall.client.audio_manager import list_audio_devices

                devices = list_audio_devices()
                if devices:
                    default_dev = devices[0]
                    dev_name = str(default_dev["index"])
                    mgr = AudioManager(
                        device_name=dev_name,
                        sample_rate=settings.audio_sample_rate,
                        channels=settings.audio_channels,
                        chunk_duration=settings.audio_chunk_duration,
                        output_dir=output_dir,
                        on_chunk_complete=lambda path,
                        duration,
                        dn="default_mic": self._on_chunk_complete(path, dn, duration),
                    )
                    mgr.start()
                    if mgr.is_alive():
                        self._managers.append(mgr)
                        devices_started += 1
                        logger.info(
                            f"Default microphone capture started: {default_dev['name']}"
                        )
            except Exception as e:
                logger.warning(f"Failed to start default microphone: {e}")

        # Start system audio capture (if configured)
        sys_device = settings.audio_device_system
        if sys_device:
            try:
                mgr = AudioManager(
                    device_name=sys_device,
                    sample_rate=settings.audio_sample_rate,
                    channels=settings.audio_channels,
                    chunk_duration=settings.audio_chunk_duration,
                    output_dir=output_dir,
                    on_chunk_complete=lambda path,
                    duration,
                    dn=sys_device: self._on_chunk_complete(path, dn, duration),
                )
                mgr.start()
                if mgr.is_alive():
                    self._managers.append(mgr)
                    devices_started += 1
                    logger.info(
                        "🎤 [AUDIO] System audio capture started: %s", sys_device
                    )
            except Exception as e:
                logger.warning(f"Failed to start system audio ({sys_device}): {e}")

        self._running = devices_started > 0
        if self._running:
            logger.info(
                "🎤 [AUDIO] ▶️  Recording started | devices=%d | chunk_duration=%ds | rate=%dHz | channels=%d | output_dir=%s",
                devices_started,
                settings.audio_chunk_duration,
                settings.audio_sample_rate,
                settings.audio_channels,
                output_dir,
            )
        else:
            logger.warning("🎤 [AUDIO] AudioRecorder: no audio devices started")

    def stop(self) -> None:
        """Stop all audio managers."""
        if not self._running:
            return

        logger.info("🎤 [AUDIO] ⏸️  Stopping AudioRecorder...")
        managers_count = len(self._managers)
        for mgr in self._managers:
            try:
                mgr.stop()
            except Exception as e:
                logger.warning("🎤 [AUDIO] Error stopping audio manager: %s", e)

        self._managers.clear()
        self._running = False
        logger.info(
            "🎤 [AUDIO] ⏹️  Recording stopped | devices_stopped=%d",
            managers_count,
        )

    def is_running(self) -> bool:
        """Check if any audio manager is active."""
        return self._running and any(m.is_alive() for m in self._managers)

    def get_total_recording_duration(self) -> float:
        """Get total recording duration across all active managers in seconds."""
        total = 0.0
        for mgr in self._managers:
            if mgr.is_alive():
                total += mgr.get_current_chunk_duration()
        return total

    def _on_chunk_complete(
        self, chunk_path: Path, device_name: str, actual_duration: float
    ) -> None:
        """Handle completed audio chunk - compute checksum and enqueue to buffer."""
        try:
            if not chunk_path.exists():
                logger.warning(f"Chunk file not found: {chunk_path}")
                return

            file_size = chunk_path.stat().st_size
            if file_size <= 44:
                logger.debug(f"Skipping empty audio chunk: {chunk_path}")
                return

            h = hashlib.sha256()
            with open(chunk_path, "rb") as f:
                for block in iter(lambda: f.read(8192), b""):
                    h.update(block)
            checksum = f"sha256:{h.hexdigest()}"

            now = time.time()
            start_time = now - actual_duration
            end_time = now
            device_text = (device_name or "").strip().lower()
            if any(token in device_text for token in ("mic", "microphone", "input")):
                source_kind = "input"
                is_input = True
            elif any(token in device_text for token in ("system", "speaker", "loopback", "output")):
                source_kind = "output"
                is_input = False
            else:
                source_kind = "unknown"
                is_input = None

            metadata = {
                "type": "audio_chunk",
                "timestamp": start_time,
                "start_time": start_time,
                "end_time": end_time,
                "device_name": device_name,
                "source_kind": source_kind,
                "is_input": is_input,
                "sample_rate": settings.audio_sample_rate,
                "channels": settings.audio_channels,
                "format": settings.audio_format,
                "file_size_bytes": file_size,
                "checksum": checksum,
                "chunk_filename": chunk_path.name,
            }

            self.buffer.enqueue_file(str(chunk_path), metadata)
            size_kb = file_size / 1024
            logger.info(
                "🎤 [AUDIO] Chunk complete | device=%s | file=%s | size=%.1fKB | duration=%.1fs | checksum=%s",
                device_name,
                chunk_path.name,
                size_kb,
                actual_duration,
                checksum[:20],
            )

        except Exception as e:
            logger.error(f"Failed to process audio chunk {chunk_path}: {e}")
