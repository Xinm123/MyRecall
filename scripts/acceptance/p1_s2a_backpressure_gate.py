#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import requests
from numpy.typing import NDArray

from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    TriggerEvent,
    utc_now_iso,
)
from openrecall.client.recorder import ScreenRecorder
from openrecall.client.spool import SpoolQueue


def utc_now_seconds() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class SamplePoint:
    ts: str
    queue_depth: int
    queue_capacity: int
    collapse_trigger_count: int
    overflow_drop_count: int
    status: str


@dataclass(frozen=True)
class BackpressureSummary:
    window_id: str
    sample_count: int
    saturated_sample_count: int
    queue_saturation_ratio: float
    collapse_trigger_count: int
    overflow_drop_count: int
    queue_capacity: int
    max_queue_depth: int
    broken_window: bool


def compute_summary(window_id: str, samples: list[SamplePoint]) -> BackpressureSummary:
    valid_samples = [
        sample
        for sample in samples
        if sample.status == "ok" and sample.queue_capacity > 0
    ]
    if valid_samples:
        saturated = [
            sample
            for sample in valid_samples
            if sample.queue_depth >= 0.9 * sample.queue_capacity
        ]
        ratio = (len(saturated) / len(valid_samples)) * 100.0
        collapse_count = max(sample.collapse_trigger_count for sample in valid_samples)
        overflow_count = max(sample.overflow_drop_count for sample in valid_samples)
        queue_capacity = max(sample.queue_capacity for sample in valid_samples)
        max_queue_depth = max(sample.queue_depth for sample in valid_samples)
    else:
        saturated = []
        ratio = 0.0
        collapse_count = 0
        overflow_count = 0
        queue_capacity = 0
        max_queue_depth = 0

    return BackpressureSummary(
        window_id=window_id,
        sample_count=len(valid_samples),
        saturated_sample_count=len(saturated),
        queue_saturation_ratio=ratio,
        collapse_trigger_count=collapse_count,
        overflow_drop_count=overflow_count,
        queue_capacity=queue_capacity,
        max_queue_depth=max_queue_depth,
        broken_window=not valid_samples,
    )


class _NoopSpool(SpoolQueue):
    def enqueue(self, image: object, metadata: object) -> str:
        return "noop"


class BackpressureRecorder(ScreenRecorder):
    def __init__(self, *, monitor_count: int, capture_delay_seconds: float) -> None:
        super().__init__()
        self._capture_delay_seconds: float = capture_delay_seconds
        self._monitors: list[MonitorDescriptor] = [
            MonitorDescriptor(
                stable_id=f"stress-{index}",
                left=index * 10,
                top=0,
                width=4,
                height=4,
                is_primary=index == 0,
                source="section10",
            )
            for index in range(monitor_count)
        ]
        self._spool = _NoopSpool()

    def start(self) -> None:
        return None

    def _start_event_sources(self) -> None:
        return None

    def _refresh_monitors(self) -> list[MonitorDescriptor]:
        self._monitor_registry.refresh(self._monitors)
        return list(self._monitors)

    def _capture_monitors(
        self, monitors: list[MonitorDescriptor]
    ) -> dict[str, NDArray[np.uint8]]:
        time.sleep(self._capture_delay_seconds)
        return {
            monitor.device_name: np.full((4, 4, 3), 255, dtype=np.uint8)
            for monitor in monitors
        }

    def _warn_if_blank_frame(
        self, event: TriggerEvent, screenshot: NDArray[np.uint8]
    ) -> None:
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Section 10 backpressure runtime gate against a live Edge",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8083")
    parser.add_argument("--duration-seconds", type=int, default=300)
    parser.add_argument("--monitor-count", type=int, default=80)
    parser.add_argument("--burst-size", type=int, default=72)
    parser.add_argument("--burst-interval-seconds", type=int, default=60)
    parser.add_argument("--initial-delay-seconds", type=int, default=5)
    parser.add_argument("--capture-delay-seconds", type=float, default=0.35)
    parser.add_argument("--sample-path", type=Path, required=True)
    parser.add_argument("--summary-path", type=Path, required=True)
    return parser.parse_args()


def fetch_queue_sample(base_url: str) -> SamplePoint:
    response = requests.get(
        f"{base_url.rstrip('/')}/v1/ingest/queue/status", timeout=10
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("queue/status response must be a JSON object")
    trigger_channel = payload.get("trigger_channel", {})
    if not isinstance(trigger_channel, dict):
        trigger_channel = {}
    return SamplePoint(
        ts=utc_now_seconds(),
        queue_depth=int(trigger_channel.get("queue_depth", 0) or 0),
        queue_capacity=int(trigger_channel.get("queue_capacity", 0) or 0),
        collapse_trigger_count=int(
            trigger_channel.get("collapse_trigger_count", 0) or 0
        ),
        overflow_drop_count=int(trigger_channel.get("overflow_drop_count", 0) or 0),
        status="ok",
    )


def emit_burst(
    recorder: BackpressureRecorder, *, burst_size: int, monitor_count: int
) -> None:
    for index in range(burst_size):
        trigger = CaptureTrigger.CLICK if index % 2 == 0 else CaptureTrigger.APP_SWITCH
        device_name = f"monitor_stress-{index % monitor_count}"
        recorder._handle_external_trigger(
            TriggerEvent(
                capture_trigger=trigger,
                device_name=device_name,
                event_ts=utc_now_iso(),
                active_app="section10.overload",
                active_window=f"burst-{index}",
            )
        )


def main() -> int:
    args = parse_args()
    window_id = f"section10-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    recorder = BackpressureRecorder(
        monitor_count=args.monitor_count,
        capture_delay_seconds=args.capture_delay_seconds,
    )
    worker = threading.Thread(target=recorder.run_capture_loop, daemon=True)
    worker.start()

    samples: list[SamplePoint] = []
    start = time.monotonic()
    next_burst = start + args.initial_delay_seconds
    next_sample = start

    try:
        while time.monotonic() - start < args.duration_seconds:
            now = time.monotonic()
            if now >= next_burst:
                emit_burst(
                    recorder,
                    burst_size=args.burst_size,
                    monitor_count=args.monitor_count,
                )
                next_burst += args.burst_interval_seconds

            if now >= next_sample:
                try:
                    samples.append(fetch_queue_sample(args.base_url))
                except requests.RequestException:
                    samples.append(
                        SamplePoint(
                            ts=utc_now_seconds(),
                            queue_depth=0,
                            queue_capacity=0,
                            collapse_trigger_count=0,
                            overflow_drop_count=0,
                            status="error",
                        )
                    )
                next_sample += 1.0

            time.sleep(0.02)
    finally:
        recorder.stop()
        worker.join(timeout=5.0)

    summary = compute_summary(window_id, samples)
    args.sample_path.parent.mkdir(parents=True, exist_ok=True)
    args.sample_path.write_text(
        "".join(json.dumps(asdict(sample)) + "\n" for sample in samples),
        encoding="utf-8",
    )
    args.summary_path.parent.mkdir(parents=True, exist_ok=True)
    args.summary_path.write_text(
        json.dumps(asdict(summary), indent=2), encoding="utf-8"
    )

    print(json.dumps(asdict(summary), indent=2))

    if summary.collapse_trigger_count < 1:
        return 1
    if summary.overflow_drop_count != 0:
        return 1
    if summary.queue_saturation_ratio > 10.0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
