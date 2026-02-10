"""Voice Activity Detection for audio processing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import requests

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

SILERO_MODEL_FILENAME = "silero_vad_v5.onnx"
SILERO_MODEL_URLS = [
    "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx",
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx",
]


@dataclass
class SpeechSegment:
    """A detected speech segment with time boundaries."""

    start_time: float
    end_time: float


@dataclass
class VadAnalysisResult:
    """Chunk-level VAD analysis output used by processor gates and telemetry."""

    segments: List[SpeechSegment]
    speech_duration_seconds: float
    total_duration_seconds: float
    speech_ratio: float
    backend_used: str


class VoiceActivityDetector:
    """Voice activity detector with ONNX Silero first and webrtcvad fallback."""

    def __init__(
        self,
        threshold: Optional[float] = None,
        backend: Optional[str] = None,
    ):
        self.threshold = (
            threshold if threshold is not None else settings.audio_vad_threshold
        )
        self.backend = (backend or settings.audio_vad_backend).lower()
        self.smoothing_window_frames = max(
            1,
            int(settings.audio_vad_smoothing_window_frames),
        )
        self.hysteresis_on_frames = max(
            1,
            int(settings.audio_vad_hysteresis_on_frames),
        )
        self.hysteresis_off_frames = max(
            1,
            int(settings.audio_vad_hysteresis_off_frames),
        )
        self._model = None
        self._backend_used = "none"
        self._initialized = False

    @property
    def backend_used(self) -> str:
        return self._backend_used

    def _init_model(self) -> None:
        """Lazy initialize VAD backend."""
        if self._initialized:
            return

        if self.backend == "webrtcvad":
            self._init_webrtcvad()
            self._initialized = True
            return

        try:
            self._init_silero_onnx()
            self._initialized = True
            return
        except Exception as exc:
            logger.warning(
                "🎧 [AUDIO-SERVER] Silero ONNX init failed, falling back to webrtcvad: %s",
                exc,
            )

        self._init_webrtcvad()
        self._initialized = True

    def _init_silero_onnx(self) -> None:
        """Initialize ONNXRuntime Silero backend."""
        try:
            import onnxruntime as ort
        except Exception as exc:
            raise RuntimeError("onnxruntime not available") from exc

        model_path = self._ensure_silero_model_file()
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = 1

        self._model = ort.InferenceSession(
            str(model_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
        self._backend_used = "silero"
        logger.info(
            "🎧 [AUDIO-SERVER] Silero ONNX VAD initialized | model=%s",
            model_path,
        )

    def _ensure_silero_model_file(self) -> Path:
        model_dir = settings.model_cache_path / "vad"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / SILERO_MODEL_FILENAME

        if model_path.exists():
            return model_path

        last_error: Optional[Exception] = None
        for url in SILERO_MODEL_URLS:
            try:
                self._download_file(url, model_path)
                logger.info(
                    "🎧 [AUDIO-SERVER] Downloaded Silero ONNX model to %s",
                    model_path,
                )
                return model_path
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "🎧 [AUDIO-SERVER] Failed to download Silero model from %s: %s",
                    url,
                    exc,
                )

        raise RuntimeError(
            f"unable to download silero ONNX model ({SILERO_MODEL_FILENAME})"
        ) from last_error

    def _download_file(self, url: str, path: Path) -> None:
        temp_path = path.with_suffix(".tmp")
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with temp_path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    fh.write(chunk)
        temp_path.replace(path)

    def _init_webrtcvad(self) -> None:
        """Initialize webrtcvad backend."""
        try:
            import webrtcvad

            self._model = webrtcvad.Vad(3)
            self._backend_used = "webrtcvad"
            logger.info("🎧 [AUDIO-SERVER] WebRTC VAD initialized (aggressiveness=3)")
        except Exception as exc:
            self._model = None
            self._backend_used = "none"
            logger.error("🎧 [AUDIO-SERVER] webrtcvad unavailable: %s", exc)

    def has_speech(self, wav_path: Union[str, Path]) -> bool:
        """Check if a WAV file contains any speech."""
        return len(self.get_speech_segments(wav_path)) > 0

    def analyze_chunk(self, wav_path: Union[str, Path]) -> VadAnalysisResult:
        """Analyze a WAV chunk and return segments + chunk-level ratio metrics."""
        self._init_model()

        if self._model is None:
            logger.warning(
                "🎧 [AUDIO-SERVER] No VAD backend available, returning empty analysis"
            )
            return VadAnalysisResult(
                segments=[],
                speech_duration_seconds=0.0,
                total_duration_seconds=0.0,
                speech_ratio=0.0,
                backend_used=self._backend_used,
            )

        try:
            from openrecall.server.audio.wav_utils import load_wav_16k

            audio = load_wav_16k(wav_path)
        except Exception as exc:
            logger.error("🎧 [AUDIO-SERVER] Failed to load WAV for VAD: %s", exc)
            return VadAnalysisResult(
                segments=[],
                speech_duration_seconds=0.0,
                total_duration_seconds=0.0,
                speech_ratio=0.0,
                backend_used=self._backend_used,
            )

        if audio.size == 0:
            return VadAnalysisResult(
                segments=[],
                speech_duration_seconds=0.0,
                total_duration_seconds=0.0,
                speech_ratio=0.0,
                backend_used=self._backend_used,
            )

        total_duration = float(len(audio) / 16000.0)
        frame_duration = self._frame_sample_count() / 16000.0
        frame_scores = self._compute_frame_scores(audio)
        segments = self._scores_to_segments(
            frame_scores=frame_scores,
            frame_duration_seconds=frame_duration,
            total_duration_seconds=total_duration,
        )
        speech_duration = sum(
            max(0.0, seg.end_time - seg.start_time) for seg in segments
        )
        speech_ratio = speech_duration / total_duration if total_duration > 0 else 0.0

        return VadAnalysisResult(
            segments=segments,
            speech_duration_seconds=speech_duration,
            total_duration_seconds=total_duration,
            speech_ratio=max(0.0, min(1.0, speech_ratio)),
            backend_used=self._backend_used,
        )

    def get_speech_segments(self, wav_path: Union[str, Path]) -> List[SpeechSegment]:
        """Detect speech segments in a WAV file."""
        return self.analyze_chunk(wav_path).segments

    def _frame_sample_count(self) -> int:
        # WebRTC expects 10/20/30ms frames; we use 20ms (320 samples).
        # Silero ONNX model is typically run on 32ms windows (512 samples).
        return 512 if self._backend_used == "silero" else 320

    def _compute_frame_scores(self, audio: np.ndarray) -> List[float]:
        if self._backend_used == "silero":
            return self._compute_silero_scores(audio)
        if self._backend_used == "webrtcvad":
            return self._compute_webrtc_scores(audio)
        return []

    def _compute_webrtc_scores(self, audio: np.ndarray) -> List[float]:
        if self._model is None:
            return []

        frame_samples = self._frame_sample_count()
        audio_int16 = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio_int16 * 32767.0).astype(np.int16)
        raw_bytes = audio_int16.tobytes()

        scores: List[float] = []
        bytes_per_frame = frame_samples * 2
        for start in range(0, len(audio_int16), frame_samples):
            frame = raw_bytes[start * 2 : start * 2 + bytes_per_frame]
            if len(frame) < bytes_per_frame:
                frame = frame + b"\x00" * (bytes_per_frame - len(frame))
            try:
                is_speech = self._model.is_speech(frame, 16000)
                scores.append(1.0 if is_speech else 0.0)
            except Exception:
                scores.append(0.0)
        return scores

    def _compute_silero_scores(self, audio: np.ndarray) -> List[float]:
        if self._model is None:
            return []

        frame_samples = self._frame_sample_count()
        scores: List[float] = []

        for start in range(0, len(audio), frame_samples):
            frame = audio[start : start + frame_samples]
            if len(frame) < frame_samples:
                frame = np.pad(frame, (0, frame_samples - len(frame)))
            frame = frame.astype(np.float32, copy=False)
            scores.append(self._silero_probability(frame))

        return scores

    def _silero_probability(self, frame: np.ndarray) -> float:
        """Run one ONNX forward pass and return speech probability."""
        session = self._model
        try:
            feeds = {}
            for input_meta in session.get_inputs():
                name = input_meta.name
                normalized = name.lower()
                if "input" in normalized or normalized in {"x"}:
                    feeds[name] = frame.reshape(1, -1)
                elif "sr" in normalized or "sample_rate" in normalized:
                    feeds[name] = np.array(16000, dtype=np.int64)
                elif "state" in normalized:
                    shape = [
                        dim if isinstance(dim, int) and dim > 0 else 1
                        for dim in input_meta.shape
                    ]
                    feeds[name] = np.zeros(shape, dtype=np.float32)
                else:
                    # Best-effort default for optional scalar inputs.
                    feeds[name] = np.array(0, dtype=np.float32)

            outputs = session.run(None, feeds)
            if not outputs:
                return 0.0

            value = float(np.array(outputs[0]).reshape(-1)[0])
            return max(0.0, min(1.0, value))
        except Exception as exc:
            logger.debug("🎧 [AUDIO-SERVER] Silero frame inference failed: %s", exc)
            return 0.0

    def _scores_to_segments(
        self,
        frame_scores: List[float],
        frame_duration_seconds: float,
        total_duration_seconds: float,
    ) -> List[SpeechSegment]:
        """Convert per-frame scores to speech segments using smoothing and hysteresis."""
        if not frame_scores:
            return []

        smoothed_scores: List[float] = []
        window: List[float] = []
        for score in frame_scores:
            window.append(float(score))
            if len(window) > self.smoothing_window_frames:
                window.pop(0)
            smoothed_scores.append(sum(window) / len(window))

        segments: List[SpeechSegment] = []
        in_speech = False
        speech_run = 0
        silence_run = 0
        start_time = 0.0

        for idx, score in enumerate(smoothed_scores):
            is_speech = score >= self.threshold
            current_time = idx * frame_duration_seconds

            if in_speech:
                if is_speech:
                    silence_run = 0
                else:
                    silence_run += 1
                    if silence_run >= self.hysteresis_off_frames:
                        end_idx = idx - self.hysteresis_off_frames + 1
                        end_time = min(
                            total_duration_seconds,
                            max(start_time, end_idx * frame_duration_seconds),
                        )
                        if end_time > start_time:
                            segments.append(
                                SpeechSegment(start_time=start_time, end_time=end_time)
                            )
                        in_speech = False
                        silence_run = 0
                        speech_run = 0
            else:
                if is_speech:
                    speech_run += 1
                    if speech_run >= self.hysteresis_on_frames:
                        start_idx = idx - self.hysteresis_on_frames + 1
                        start_time = max(0.0, start_idx * frame_duration_seconds)
                        in_speech = True
                        silence_run = 0
                else:
                    speech_run = 0

            # Guard against drift from floating arithmetic in long chunks.
            if current_time >= total_duration_seconds:
                break

        if in_speech and total_duration_seconds > start_time:
            segments.append(
                SpeechSegment(
                    start_time=start_time,
                    end_time=total_duration_seconds,
                )
            )

        return [seg for seg in segments if seg.end_time > seg.start_time]
