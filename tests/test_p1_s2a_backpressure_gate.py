from __future__ import annotations

from scripts.acceptance.p1_s2a_backpressure_gate import SamplePoint, compute_summary


def test_compute_summary_uses_valid_samples_and_gate_formula() -> None:
    samples = [
        SamplePoint(
            ts="2026-03-10T00:00:00Z",
            queue_depth=10,
            queue_capacity=64,
            collapse_trigger_count=0,
            overflow_drop_count=0,
            status="ok",
        ),
        SamplePoint(
            ts="2026-03-10T00:00:01Z",
            queue_depth=60,
            queue_capacity=64,
            collapse_trigger_count=2,
            overflow_drop_count=0,
            status="ok",
        ),
        SamplePoint(
            ts="2026-03-10T00:00:02Z",
            queue_depth=0,
            queue_capacity=0,
            collapse_trigger_count=0,
            overflow_drop_count=0,
            status="error",
        ),
    ]

    summary = compute_summary("section10-demo", samples)

    assert summary.window_id == "section10-demo"
    assert summary.sample_count == 2
    assert summary.saturated_sample_count == 1
    assert summary.queue_saturation_ratio == 50.0
    assert summary.collapse_trigger_count == 2
    assert summary.overflow_drop_count == 0
    assert summary.queue_capacity == 64
    assert summary.max_queue_depth == 60
    assert summary.broken_window is False
