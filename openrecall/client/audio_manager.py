"""Low-level audio capture manager using sounddevice.

Records 16kHz mono WAV chunks with automatic rotation.
"""

import logging
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def list_audio_devices() -> List[dict]:
    """List available audio input devices.

    Returns:
        List of dicts with device info (index, name, channels, sample_rate).
    """
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        input_devices = []
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                input_devices.append(
                    {
                        "index": i,
                        "name": dev["name"],
                        "channels": dev["max_input_channels"],
                        "default_samplerate": dev["default_samplerate"],
                    }
                )
        return input_devices
    except Exception as e:
        logger.error(f"Failed to list audio devices: {e}")
        return []


class AudioManager:
    """sounddevice.InputStream wrapper that records 16kHz mono WAV chunks.

    Features:
    - Automatic chunk rotation based on duration
    - WAV format: 16kHz, mono, int16
    - Callback-based chunk completion notification
    - Thread-safe start/stop
    """

    def __init__(
        self,
        device_name: str,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration: int = 60,
        output_dir: Optional[Path] = None,
        on_chunk_complete: Optional[Callable[[Path, float], None]] = None,
    ):
        """Initialize AudioManager.

        Args:
            device_name: Device identifier (name or index as string).
            sample_rate: Sample rate in Hz (16000 for Whisper).
            channels: Number of channels (1 for mono).
            chunk_duration: Chunk duration in seconds.
            output_dir: Directory for WAV output files.
            on_chunk_complete: Callback fired when a chunk is complete.
        """
        self.device_name = device_name
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_duration = chunk_duration
        self.output_dir = output_dir or Path(".")
        self.on_chunk_complete = on_chunk_complete

        self._stream = None
        self._lock = threading.RLock()
        self._recording = False
        self._current_wav: Optional[wave.Wave_write] = None
        self._current_path: Optional[Path] = None
        self._chunk_start_time: float = 0.0
        self._frames_written: int = 0

    def _resolve_device(self) -> Optional[int]:
        """Resolve device name/index to a device index."""
        import sounddevice as sd

        # Try as integer index first
        try:
            idx = int(self.device_name)
            devices = sd.query_devices()
            if 0 <= idx < len(devices):
                return idx
        except (ValueError, TypeError):
            pass

        # Search by name substring
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if (
                dev["max_input_channels"] > 0
                and self.device_name.lower() in dev["name"].lower()
            ):
                return i

        return None

    def start(self) -> None:
        """Start recording audio."""
        import sounddevice as sd

        if self._recording:
            logger.warning(f"AudioManager({self.device_name}) already recording")
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        device_idx = self._resolve_device()
        if device_idx is None:
            logger.error(f"Audio device not found: {self.device_name}")
            return

        try:
            self._start_new_chunk()
            self._stream = sd.InputStream(
                device=device_idx,
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                blocksize=int(self.sample_rate * 0.1),  # 100ms blocks
                callback=self._audio_callback,
            )
            # Set recording before start() so audio callback can write immediately
            self._recording = True
            self._stream.start()
            logger.info(
                "🎤 [AUDIO] ▶️  Device started | device=%s (idx=%d) | rate=%dHz | channels=%d | chunk_duration=%ds",
                self.device_name,
                device_idx,
                self.sample_rate,
                self.channels,
                self.chunk_duration,
            )
        except Exception as e:
            self._recording = False
            logger.error(f"Failed to start AudioManager({self.device_name}): {e}")
            # Close the stream if it was created but start() failed
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            self._close_current_chunk(notify=False)

    def stop(self) -> None:
        """Stop recording and flush current chunk."""
        if not self._recording:
            return

        self._recording = False

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.warning(f"Error stopping stream: {e}")
            self._stream = None

        self._close_current_chunk(notify=True)
        logger.info("🎤 [AUDIO] ⏹️  Device stopped | device=%s", self.device_name)

    def is_alive(self) -> bool:
        """Check if recording is active."""
        return self._recording and self._stream is not None

    def get_current_chunk_duration(self) -> float:
        """Get the duration of the current chunk being recorded in seconds."""
        if not self._recording or self._chunk_start_time == 0.0:
            return 0.0
        return time.time() - self._chunk_start_time

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice callback - receives audio data."""
        if status:
            logger.warning(f"Audio callback status: {status}")

        if not self._recording:
            return

        with self._lock:
            if self._current_wav is None:
                return

            try:
                self._current_wav.writeframes(indata.tobytes())
                self._frames_written += frames

                # Check if chunk duration exceeded
                elapsed = self._frames_written / self.sample_rate
                if elapsed >= self.chunk_duration:
                    self._close_current_chunk(notify=True)
                    self._start_new_chunk()
            except Exception as e:
                logger.error(f"Error in audio callback: {e}")

    def _start_new_chunk(self) -> None:
        """Start a new WAV chunk file."""
        # Sanitize device name for filename
        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in self.device_name
        )
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        filename = f"{safe_name}_{timestamp_str}.wav"
        self._current_path = self.output_dir / filename

        self._current_wav = wave.open(str(self._current_path), "wb")
        self._current_wav.setnchannels(self.channels)
        self._current_wav.setsampwidth(2)  # int16 = 2 bytes
        self._current_wav.setframerate(self.sample_rate)

        self._chunk_start_time = time.time()
        self._frames_written = 0

        logger.info(
            "🎤 [AUDIO] Chunk started | device=%s | file=%s | chunk_duration=%ds",
            self.device_name,
            filename,
            self.chunk_duration,
        )

    def _close_current_chunk(self, notify: bool = True) -> None:
        """Close the current WAV chunk and optionally notify."""
        with self._lock:
            if self._current_wav is None:
                return

            chunk_path = self._current_path
            actual_duration = time.time() - self._chunk_start_time
            try:
                self._current_wav.close()
            except Exception as e:
                logger.warning(f"Error closing WAV: {e}")
            self._current_wav = None
            self._current_path = None

        if (
            notify
            and chunk_path
            and chunk_path.exists()
            and chunk_path.stat().st_size > 44
        ):
            if self.on_chunk_complete:
                try:
                    self.on_chunk_complete(chunk_path, actual_duration)
                except Exception as e:
                    logger.error(f"Error in chunk complete callback: {e}")
        elif chunk_path and chunk_path.exists() and chunk_path.stat().st_size <= 44:
            try:
                chunk_path.unlink()
            except OSError:
                pass
