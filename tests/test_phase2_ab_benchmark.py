"""Phase 2 tests: offline audio backend A/B benchmark tool."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _fake_report() -> dict:
    return {
        "run": {
            "dataset_mode": "hybrid",
            "backends": ["silero", "webrtcvad"],
        },
        "sample_overview": {
            "synthetic": {"count": 4, "included": True},
            "real": {"count": 0, "included": False},
        },
        "backend_metrics": {
            "silero": {
                "transcription_latency_seconds": {"mean": 0.8, "p50": 0.7, "p95": 1.2},
                "empty_transcription_ratio": 0.05,
                "miss_detection_rate": 0.08,
            },
            "webrtcvad": {
                "transcription_latency_seconds": {"mean": 0.9, "p50": 0.8, "p95": 1.4},
                "empty_transcription_ratio": 0.09,
                "miss_detection_rate": 0.12,
            },
        },
        "comparison_summary": {
            "transcription_latency_seconds": {"winner": "silero", "delta": -0.1},
            "empty_transcription_ratio": {"winner": "silero", "delta": -0.04},
            "miss_detection_rate": {"winner": "silero", "delta": -0.04},
        },
        "environment": {
            "python_version": "3.11",
            "platform": "darwin",
        },
    }


class TestAudioAbBenchmarkCli:
    """Tests for openrecall.server.audio.ab_benchmark CLI behavior."""

    def test_parse_args_defaults(self, tmp_path):
        from openrecall.server.audio.ab_benchmark import parse_args

        out_path = tmp_path / "audio_ab_metrics.json"
        args = parse_args(["--output-json", str(out_path)])

        assert args.backends == "silero,webrtcvad"
        assert args.dataset == "hybrid"
        assert args.output_json == out_path

    def test_run_benchmark_degrades_without_real_samples(self, tmp_path):
        from openrecall.server.audio.ab_benchmark import run_benchmark

        with patch(
            "openrecall.server.audio.ab_benchmark.generate_synthetic_dataset",
            return_value=[{"sample_id": "synthetic-1", "has_speech": True}],
        ), patch(
            "openrecall.server.audio.ab_benchmark.load_real_dataset",
            return_value=[],
        ), patch(
            "openrecall.server.audio.ab_benchmark.benchmark_backend",
            side_effect=lambda backend, *_args, **_kwargs: {
                "transcription_latency_seconds": {
                    "mean": 1.0 if backend == "webrtcvad" else 0.9,
                    "p50": 0.9,
                    "p95": 1.3,
                },
                "empty_transcription_ratio": 0.1,
                "miss_detection_rate": 0.2,
            },
        ):
            report = run_benchmark(
                backends=["silero", "webrtcvad"],
                dataset_mode="hybrid",
                real_samples_dir=tmp_path / "missing_real",
            )

        assert report["sample_overview"]["synthetic"]["included"] is True
        assert report["sample_overview"]["real"]["included"] is False
        assert report["sample_overview"]["real"]["count"] == 0
        assert "silero" in report["backend_metrics"]
        assert "webrtcvad" in report["backend_metrics"]

    def test_main_writes_json_schema(self, tmp_path):
        from openrecall.server.audio.ab_benchmark import main

        out_path = tmp_path / "audio_ab_metrics.json"
        with patch(
            "openrecall.server.audio.ab_benchmark.run_benchmark",
            return_value=_fake_report(),
        ):
            exit_code = main(["--output-json", str(out_path)])

        assert exit_code == 0
        assert out_path.exists()

        payload = json.loads(out_path.read_text(encoding="utf-8"))
        assert "backend_metrics" in payload
        assert "comparison_summary" in payload
        assert "environment" in payload
        assert "transcription_latency_seconds" in payload["backend_metrics"]["silero"]

    def test_benchmark_backend_reports_effective_backend(self):
        from openrecall.server.audio.ab_benchmark import benchmark_backend

        fake_vad = SimpleNamespace()
        fake_vad.analyze_chunk = lambda _path: analyses.pop(0)
        analyses = [
            SimpleNamespace(segments=[], speech_ratio=0.0, backend_used="webrtcvad"),
            SimpleNamespace(
                segments=[SimpleNamespace(start_time=0.0, end_time=1.0)],
                speech_ratio=0.2,
                backend_used="webrtcvad",
            ),
        ]

        fake_transcriber = SimpleNamespace()
        fake_transcriber.transcribe = lambda _audio: []

        with patch(
            "openrecall.server.audio.ab_benchmark.VoiceActivityDetector",
            return_value=fake_vad,
        ), patch(
            "openrecall.server.audio.ab_benchmark.WhisperTranscriber",
            return_value=fake_transcriber,
        ), patch(
            "openrecall.server.audio.ab_benchmark.load_wav_16k",
            return_value=[0.0] * 16000,
        ), patch(
            "openrecall.server.audio.ab_benchmark.extract_segment",
            return_value=[0.0] * 2000,
        ):
            report = benchmark_backend(
                backend="silero",
                samples=[
                    {"sample_id": "a", "path": Path("/tmp/a.wav"), "has_speech": False},
                    {"sample_id": "b", "path": Path("/tmp/b.wav"), "has_speech": True},
                ],
                min_speech_ratio=0.05,
            )

        assert report["requested_backend"] == "silero"
        assert report["effective_backend"] == "webrtcvad"
        assert report["fallback_triggered"] is True
        assert report["backend_used_counts"]["webrtcvad"] == 2
