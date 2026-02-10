"""WAV file utilities for audio processing."""

import logging
import struct
import wave
from pathlib import Path
from typing import Optional, Union

import numpy as np

logger = logging.getLogger(__name__)


def load_wav_16k(path: Union[str, Path]) -> np.ndarray:
    """Load a WAV file as float32 numpy array at 16kHz mono.

    Args:
        path: Path to the WAV file.

    Returns:
        Audio data as float32 numpy array normalized to [-1.0, 1.0].

    Raises:
        ValueError: If file cannot be loaded or is not valid WAV.
    """
    path = Path(path)
    if not path.exists():
        raise ValueError(f"WAV file not found: {path}")

    try:
        with wave.open(str(path), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()

            raw_data = wf.readframes(n_frames)
    except Exception as e:
        raise ValueError(f"Failed to read WAV file {path}: {e}")

    if sampwidth == 2:
        dtype = np.int16
    elif sampwidth == 4:
        dtype = np.int32
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    audio = np.frombuffer(raw_data, dtype=dtype).astype(np.float32)

    # Normalize to [-1.0, 1.0]
    if dtype == np.int16:
        audio /= 32768.0
    elif dtype == np.int32:
        audio /= 2147483648.0

    # Convert to mono if stereo
    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)

    # Resample to 16kHz if needed
    if framerate != 16000:
        try:
            import scipy.signal
            num_samples = int(len(audio) * 16000 / framerate)
            audio = scipy.signal.resample(audio, num_samples).astype(np.float32)
        except ImportError:
            # Simple decimation/interpolation fallback
            ratio = 16000 / framerate
            indices = np.arange(0, len(audio), 1 / ratio).astype(int)
            indices = indices[indices < len(audio)]
            audio = audio[indices]

    return audio


def extract_segment(wav_data: np.ndarray, start: float, end: float, sr: int = 16000) -> np.ndarray:
    """Extract a time segment from audio data.

    Args:
        wav_data: Audio data as float32 array.
        start: Start time in seconds.
        end: End time in seconds.
        sr: Sample rate.

    Returns:
        Extracted segment as float32 array.
    """
    start_sample = max(0, int(start * sr))
    end_sample = min(len(wav_data), int(end * sr))
    return wav_data[start_sample:end_sample]


def save_segment(wav_data: np.ndarray, path: Union[str, Path], sr: int = 16000) -> None:
    """Save audio data as 16-bit WAV file.

    Args:
        wav_data: Audio data as float32 array.
        path: Output path.
        sr: Sample rate.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert float32 to int16
    audio_int16 = np.clip(wav_data * 32768.0, -32768, 32767).astype(np.int16)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_int16.tobytes())


def get_wav_duration(path: Union[str, Path]) -> float:
    """Get duration of a WAV file in seconds."""
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception as e:
        logger.warning(f"Failed to get WAV duration for {path}: {e}")
        return 0.0
