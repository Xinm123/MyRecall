from __future__ import annotations

from scripts.acceptance.p1_s2a_loss_rate_gate import compute_loss_summary


def test_compute_loss_summary_tracks_numerator_and_denominator() -> None:
    summary = compute_loss_summary(
        window_id="section10a-demo",
        edge_pid="123",
        injected_event_count=1500,
        produced_capture_count=1499,
        committed_capture_count=1498,
        duration_seconds=300,
        capture_rate_per_min=300,
        broken_window=False,
    )

    assert summary.window_id == "section10a-demo"
    assert summary.injected_event_count == 1500
    assert summary.produced_capture_count == 1499
    assert summary.committed_capture_count == 1498
    assert summary.lost_capture_count == 2
    assert summary.loss_rate == 2 / 1500
    assert summary.capture_rate_per_min == 300
    assert summary.duration_seconds == 300
    assert summary.broken_window is False
