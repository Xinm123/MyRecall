"""Offline A/B benchmark for audio VAD backends."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from openrecall.server.audio.transcriber import WhisperTranscriber
from openrecall.server.audio.vad import VoiceActivityDetector
from openrecall.server.audio.wav_utils import extract_segment, load_wav_16k
from openrecall.shared.config import settings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline benchmark for silero vs webrtcvad backends.",
    )
    parser.add_argument(
        "--backends",
        default="silero,webrtcvad",
        help="Comma-separated VAD backends to compare.",
    )
    parser.add_argument(
        "--dataset",
        choices=["synthetic", "real", "hybrid"],
        default="hybrid",
        help="Dataset mode to benchmark.",
    )
    parser.add_argument(
        "--real-samples-dir",
        type=Path,
        default=None,
        help="Directory containing manifest.json and referenced real sample WAV files.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("v3/results/phase-2-evidence/audio_ab_metrics.json"),
        help="Output path for JSON report.",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=None,
        help="Optional output path for Markdown summary.",
    )
    parser.add_argument(
        "--min-speech-ratio",
        type=float,
        default=settings.audio_vad_min_speech_ratio,
        help="Chunk-level speech_ratio threshold before transcription.",
    )
    return parser.parse_args(argv)


def _write_wav(path: Path, audio: np.ndarray) -> None:
    audio_int16 = np.clip(audio * 32768.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_int16.tobytes())


def generate_synthetic_dataset() -> list[dict[str, Any]]:
    """Generate a small synthetic benchmark dataset with rough ground truth labels."""
    root = Path(tempfile.mkdtemp(prefix="audio_ab_"))
    samples: list[dict[str, Any]] = []

    # 1) pure silence
    silence = np.zeros(16000 * 2, dtype=np.float32)
    silence_path = root / "silence.wav"
    _write_wav(silence_path, silence)
    samples.append(
        {
            "sample_id": "synthetic_silence",
            "path": silence_path,
            "has_speech": False,
            "subset": "synthetic",
        }
    )

    # 2) short speech-like burst in the middle (sine tone as proxy)
    burst = np.zeros(16000 * 2, dtype=np.float32)
    t = np.linspace(0, 0.35, int(16000 * 0.35), endpoint=False)
    burst_wave = (0.35 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    start = int(16000 * 0.8)
    burst[start : start + len(burst_wave)] = burst_wave
    burst_path = root / "speech_burst.wav"
    _write_wav(burst_path, burst)
    samples.append(
        {
            "sample_id": "synthetic_speech_burst",
            "path": burst_path,
            "has_speech": True,
            "subset": "synthetic",
        }
    )

    # 3) low-level noise
    rng = np.random.default_rng(42)
    noise = rng.normal(0.0, 0.02, 16000 * 2).astype(np.float32)
    noise_path = root / "noise_only.wav"
    _write_wav(noise_path, noise)
    samples.append(
        {
            "sample_id": "synthetic_noise_only",
            "path": noise_path,
            "has_speech": False,
            "subset": "synthetic",
        }
    )

    # 4) speech+noise mix proxy
    mix = noise.copy()
    t2 = np.linspace(0, 1.0, 16000, endpoint=False)
    tone = (0.20 * np.sin(2 * np.pi * 180 * t2)).astype(np.float32)
    mix[: len(tone)] += tone
    mix_path = root / "speech_noise_mix.wav"
    _write_wav(mix_path, np.clip(mix, -1.0, 1.0))
    samples.append(
        {
            "sample_id": "synthetic_speech_noise_mix",
            "path": mix_path,
            "has_speech": True,
            "subset": "synthetic",
        }
    )

    return samples


def load_real_dataset(real_samples_dir: Path | None) -> list[dict[str, Any]]:
    """Load minimal real dataset from manifest.json.

    Manifest schema:
    {
      "samples": [
        {"sample_id": "real-1", "path": "meeting.wav", "has_speech": true}
      ]
    }
    """
    if real_samples_dir is None:
        return []
    if not real_samples_dir.exists():
        return []

    manifest_path = real_samples_dir / "manifest.json"
    if not manifest_path.exists():
        return []

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = payload["samples"] if isinstance(payload, dict) else payload
    samples: list[dict[str, Any]] = []

    for idx, row in enumerate(rows):
        relative = Path(row.get("path", ""))
        resolved = (
            relative if relative.is_absolute() else (real_samples_dir / relative)
        ).resolve()
        if not resolved.exists():
            continue
        samples.append(
            {
                "sample_id": row.get("sample_id", f"real_{idx}"),
                "path": resolved,
                "has_speech": bool(row.get("has_speech", True)),
                "subset": "real",
            }
        )

    return samples


def _latency_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
    arr = np.array(values, dtype=np.float64)
    return {
        "mean": float(np.mean(arr)),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
    }


def benchmark_backend(
    backend: str,
    samples: list[dict[str, Any]],
    min_speech_ratio: float,
) -> dict[str, Any]:
    """Run one backend benchmark against the provided samples."""
    vad = VoiceActivityDetector(backend=backend)
    transcriber = WhisperTranscriber()

    latencies: list[float] = []
    empty_transcriptions = 0
    miss_detections = 0
    vad_positive = 0
    backend_used_counts: dict[str, int] = {}

    for sample in samples:
        sample_path = Path(sample["path"])
        has_speech = bool(sample.get("has_speech", True))

        t0 = time.perf_counter()
        analysis = vad.analyze_chunk(sample_path)
        used_backend = analysis.backend_used or "none"
        backend_used_counts[used_backend] = backend_used_counts.get(used_backend, 0) + 1
        segments = analysis.segments
        ratio_gate_passed = analysis.speech_ratio >= min_speech_ratio
        chunk_marked_speech = ratio_gate_passed and bool(segments)
        if chunk_marked_speech:
            vad_positive += 1

        transcribed_text_items: list[str] = []
        if chunk_marked_speech:
            audio = load_wav_16k(sample_path)
            for seg in segments:
                segment_audio = extract_segment(audio, seg.start_time, seg.end_time)
                if len(segment_audio) < 1600:
                    continue
                for ts in transcriber.transcribe(segment_audio):
                    text = ts.text.strip()
                    if text:
                        transcribed_text_items.append(text)

        latencies.append(time.perf_counter() - t0)

        if chunk_marked_speech and not transcribed_text_items:
            empty_transcriptions += 1
        if has_speech and not chunk_marked_speech:
            miss_detections += 1

    total = len(samples)
    effective_backend = (
        max(backend_used_counts.items(), key=lambda item: item[1])[0]
        if backend_used_counts
        else "none"
    )
    return {
        "requested_backend": backend,
        "effective_backend": effective_backend,
        "fallback_triggered": effective_backend != backend,
        "backend_used_counts": backend_used_counts,
        "transcription_latency_seconds": _latency_stats(latencies),
        "empty_transcription_ratio": (
            float(empty_transcriptions / total) if total > 0 else 0.0
        ),
        "miss_detection_rate": (
            float(miss_detections / total) if total > 0 else 0.0
        ),
        "counts": {
            "chunks": total,
            "vad_positive_chunks": vad_positive,
            "empty_transcriptions": empty_transcriptions,
            "miss_detections": miss_detections,
        },
    }


def _metric_value(metrics: dict[str, Any], key: str) -> float:
    if key == "transcription_latency_seconds":
        return float(metrics[key]["mean"])
    return float(metrics[key])


def _compare_metric(
    metric_name: str,
    backend_metrics: dict[str, dict[str, Any]],
    backends: list[str],
) -> dict[str, Any]:
    if not backends:
        return {"winner": "n/a", "delta": 0.0, "metric": metric_name}
    if len(backends) == 1:
        return {"winner": backends[0], "delta": 0.0, "metric": metric_name}

    first, second = backends[0], backends[1]
    first_value = _metric_value(backend_metrics[first], metric_name)
    second_value = _metric_value(backend_metrics[second], metric_name)
    winner = first if first_value <= second_value else second
    delta = first_value - second_value

    return {"winner": winner, "delta": float(delta), "metric": metric_name}


def run_benchmark(
    backends: list[str],
    dataset_mode: str,
    real_samples_dir: Path | None,
    min_speech_ratio: float | None = None,
) -> dict[str, Any]:
    """Run offline benchmark and return structured report payload."""
    if min_speech_ratio is None:
        min_speech_ratio = settings.audio_vad_min_speech_ratio

    synthetic_samples = (
        generate_synthetic_dataset() if dataset_mode in {"synthetic", "hybrid"} else []
    )
    real_samples = (
        load_real_dataset(real_samples_dir) if dataset_mode in {"real", "hybrid"} else []
    )
    samples = [*synthetic_samples, *real_samples]

    backend_metrics: dict[str, dict[str, Any]] = {}
    for backend in backends:
        backend_metrics[backend] = benchmark_backend(
            backend=backend,
            samples=samples,
            min_speech_ratio=float(min_speech_ratio),
        )

    comparison_summary = {
        "transcription_latency_seconds": _compare_metric(
            "transcription_latency_seconds",
            backend_metrics=backend_metrics,
            backends=backends,
        ),
        "empty_transcription_ratio": _compare_metric(
            "empty_transcription_ratio",
            backend_metrics=backend_metrics,
            backends=backends,
        ),
        "miss_detection_rate": _compare_metric(
            "miss_detection_rate",
            backend_metrics=backend_metrics,
            backends=backends,
        ),
    }

    return {
        "run": {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "dataset_mode": dataset_mode,
            "backends": backends,
            "min_speech_ratio": float(min_speech_ratio),
        },
        "sample_overview": {
            "synthetic": {
                "count": len(synthetic_samples),
                "included": dataset_mode in {"synthetic", "hybrid"},
            },
            "real": {
                "count": len(real_samples),
                "included": dataset_mode in {"real", "hybrid"} and len(real_samples) > 0,
            },
            "total": len(samples),
        },
        "backend_metrics": backend_metrics,
        "comparison_summary": comparison_summary,
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
        },
    }


def _to_markdown(report: dict[str, Any]) -> str:
    backends = report["run"]["backends"]
    lines = [
        "# Audio Backend A/B Benchmark",
        "",
        f"- Dataset mode: `{report['run']['dataset_mode']}`",
        f"- Backends: `{', '.join(backends)}`",
        f"- Total samples: `{report['sample_overview']['total']}`",
        "",
        "## Backend Metrics",
        "",
        "| Backend | Latency mean(s) | Latency p50(s) | Latency p95(s) | Empty Ratio | Miss Rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for backend in backends:
        metrics = report["backend_metrics"][backend]
        latency = metrics["transcription_latency_seconds"]
        lines.append(
            "| {backend} | {mean:.3f} | {p50:.3f} | {p95:.3f} | {empty:.4f} | {miss:.4f} |".format(
                backend=backend,
                mean=latency["mean"],
                p50=latency["p50"],
                p95=latency["p95"],
                empty=metrics["empty_transcription_ratio"],
                miss=metrics["miss_detection_rate"],
            )
        )

    lines.extend(
        [
            "",
            "## Comparison Summary",
            "",
            "| Metric | Winner | Delta(first-second) |",
            "|---|---|---:|",
        ]
    )
    for key, value in report["comparison_summary"].items():
        lines.append(f"| {key} | {value['winner']} | {value['delta']:.4f} |")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    backends = [item.strip() for item in args.backends.split(",") if item.strip()]
    report = run_benchmark(
        backends=backends,
        dataset_mode=args.dataset,
        real_samples_dir=args.real_samples_dir,
        min_speech_ratio=args.min_speech_ratio,
    )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if args.output_markdown is not None:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(_to_markdown(report), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
