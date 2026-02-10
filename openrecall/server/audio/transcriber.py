"""Whisper-based audio transcription using faster-whisper."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

import numpy as np

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionSegment:
    """A single transcription segment with timing and confidence."""

    text: str
    start_time: float
    end_time: float
    confidence: float


class WhisperTranscriber:
    """Whisper transcriber using faster-whisper (CTranslate2 backend).

    Features:
    - Lazy model loading
    - GPU OOM -> CPU fallback
    - Configurable model size and compute type
    """

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
    ):
        self.model_size = model_size or settings.audio_whisper_model
        self.device = device or settings.device
        self.compute_type = compute_type or settings.audio_whisper_compute_type
        self._model = None
        self._initialized = False

    def _init_model(self) -> None:
        """Lazy initialize the Whisper model."""
        if self._initialized:
            return

        try:
            from faster_whisper import WhisperModel

            # Map device names
            if self.device in ("cuda", "gpu"):
                device = "cuda"
                compute_type = "float16"
            elif self.device == "mps":
                # MPS not supported by CTranslate2, use CPU
                device = "cpu"
                compute_type = self.compute_type
            else:
                device = "cpu"
                compute_type = self.compute_type

            logger.info(
                "🎧 [AUDIO-SERVER] Loading Whisper model | model=%s | device=%s | compute=%s",
                self.model_size,
                device,
                compute_type,
            )
            self._model = WhisperModel(
                self.model_size,
                device=device,
                compute_type=compute_type,
            )
            self._initialized = True
            logger.info(
                "🎧 [AUDIO-SERVER] Whisper model loaded successfully | model=%s",
                self.model_size,
            )
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            self._initialized = True  # Avoid retrying

    def _reinit_on_cpu(self) -> None:
        """Reinitialize model on CPU after GPU OOM."""
        logger.warning("Reinitializing Whisper on CPU due to GPU OOM")
        self._model = None
        self._initialized = False
        self.device = "cpu"
        self.compute_type = "int8"
        self._init_model()

    def transcribe(
        self,
        wav_path_or_array: Union[str, Path, np.ndarray],
        language: Optional[str] = None,
        _is_retry: bool = False,
    ) -> List[TranscriptionSegment]:
        """Transcribe audio using Whisper.

        Args:
            wav_path_or_array: Path to WAV file or float32 numpy array.
            language: Language code (e.g., "en"). Defaults to settings.
            _is_retry: Internal flag to prevent infinite OOM retry loop.

        Returns:
            List of TranscriptionSegment objects.
        """
        self._init_model()

        if self._model is None:
            logger.error("Whisper model not available")
            return []

        language = language or settings.audio_whisper_language
        beam_size = settings.audio_whisper_beam_size

        # Convert numpy array to path if needed
        if isinstance(wav_path_or_array, np.ndarray):
            audio_input = wav_path_or_array
        else:
            audio_input = str(wav_path_or_array)

        try:
            segments_iter, info = self._model.transcribe(
                audio_input,
                language=language,
                beam_size=beam_size,
                vad_filter=False,  # We do our own VAD
            )

            results = []
            for segment in segments_iter:
                text = segment.text.strip()
                if text:
                    results.append(
                        TranscriptionSegment(
                            text=text,
                            start_time=segment.start,
                            end_time=segment.end,
                            confidence=segment.avg_logprob
                            if hasattr(segment, "avg_logprob")
                            else -1.0,
                        )
                    )

            return results

        except RuntimeError as e:
            if "out of memory" in str(e).lower() and not _is_retry:
                self._reinit_on_cpu()
                return self.transcribe(wav_path_or_array, language, _is_retry=True)
            raise
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return []

    @property
    def engine_name(self) -> str:
        """Return engine identifier string."""
        return f"faster-whisper:{self.model_size}"
