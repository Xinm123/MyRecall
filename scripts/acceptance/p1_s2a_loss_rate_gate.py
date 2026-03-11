#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    TriggerEvent,
    utc_now_iso,
)
from openrecall.client.recorder import ScreenRecorder
from openrecall.client.spool import SpoolQueue
from openrecall.client.v3_uploader import SpoolUploader
from openrecall.shared.config import settings


def utc_now_seconds() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class LossRateSummary:
    window_id: str
    edge_pid: str
    broken_window: bool
    injected_event_count: int
    produced_capture_count: int
    committed_capture_count: int
    lost_capture_count: int
    loss_rate: float
    capture_rate_per_min: int
    duration_seconds: int
    calculation_basis: str


def compute_loss_summary(
    *,
    window_id: str,
    edge_pid: str,
    injected_event_count: int,
    produced_capture_count: int,
    committed_capture_count: int,
    duration_seconds: int,
    capture_rate_per_min: int,
    broken_window: bool,
) -> LossRateSummary:
    lost_capture_count = max(injected_event_count - committed_capture_count, 0)
    loss_rate = (
        (lost_capture_count / injected_event_count) if injected_event_count > 0 else 0.0
    )
    return LossRateSummary(
        window_id=window_id,
        edge_pid=edge_pid,
        broken_window=broken_window,
        injected_event_count=injected_event_count,
        produced_capture_count=produced_capture_count,
        committed_capture_count=committed_capture_count,
        lost_capture_count=lost_capture_count,
        loss_rate=loss_rate,
        capture_rate_per_min=capture_rate_per_min,
        duration_seconds=duration_seconds,
        calculation_basis=(
            "loss_rate = (injected_event_count - committed_capture_count) / injected_event_count; "
            "committed_capture_count is SELECT COUNT(*) FROM frames WHERE app_name = window_id "
            "AND snapshot_path IS NOT NULL"
        ),
    )


class CountingSpool(SpoolQueue):
    def __init__(self, storage_dir: Path) -> None:
        super().__init__(storage_dir=storage_dir)
        self._lock: threading.Lock = threading.Lock()
        self._capture_ids: list[str] = []

    def enqueue(self, image: Image.Image, metadata: dict[str, Any]) -> str:
        capture_id = super().enqueue(image, metadata)
        with self._lock:
            self._capture_ids.append(capture_id)
        return capture_id

    def generated_capture_ids(self) -> list[str]:
        with self._lock:
            return list(self._capture_ids)


class LossRateRecorder(ScreenRecorder):
    def __init__(
        self,
        *,
        monitor_count: int,
        capture_delay_seconds: float,
        app_name: str,
    ) -> None:
        super().__init__()
        self._capture_delay_seconds: float = capture_delay_seconds
        self._app_name: str = app_name
        self._monitors: list[MonitorDescriptor] = [
            MonitorDescriptor(
                stable_id=f"loss-{index}",
                left=index * 8,
                top=0,
                width=4,
                height=4,
                is_primary=index == 0,
                source="section10a",
            )
            for index in range(monitor_count)
        ]
        self._counting_spool: CountingSpool = CountingSpool(settings.spool_path)
        self._spool = self._counting_spool
        self._spool_uploader: SpoolUploader = SpoolUploader(spool=self._counting_spool)

    def _start_event_sources(self) -> None:
        return None

    def _refresh_monitors(self) -> list[MonitorDescriptor]:
        _ = self._monitor_registry.refresh(self._monitors)
        return list(self._monitors)

    def _poll_permissions(self, *, now_epoch: float) -> None:
        return None

    def _capture_monitors(
        self, monitors: list[MonitorDescriptor]
    ) -> dict[str, NDArray[np.uint8]]:
        time.sleep(self._capture_delay_seconds)
        return {
            monitor.device_name: np.full((4, 4, 3), 240, dtype=np.uint8)
            for monitor in monitors
        }

    def _warn_if_blank_frame(
        self, event: TriggerEvent, screenshot: NDArray[np.uint8]
    ) -> None:
        return None

    def _build_capture_metadata(self, event: TriggerEvent) -> dict[str, str]:
        metadata = super()._build_capture_metadata(event)
        metadata["active_app"] = self._app_name
        metadata["active_window"] = (
            f"{self._app_name}:{event.device_name}:{event.capture_trigger.value}"
        )
        return metadata

    def generated_capture_ids(self) -> list[str]:
        return self._counting_spool.generated_capture_ids()

    def pending_spool_count(self) -> int:
        return self._counting_spool.count()

    def monitor_count(self) -> int:
        return len(self._monitors)

    def app_name(self) -> str:
        return self._app_name

    def inject_trigger(self, event: TriggerEvent) -> None:
        self._handle_external_trigger(event)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Section 10A loss-rate gate against a live Edge",
    )
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--summary-path", type=Path, required=True)
    parser.add_argument("--capture-id-path", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=int, default=300)
    parser.add_argument("--capture-rate-per-min", type=int, default=300)
    parser.add_argument("--monitor-count", type=int, default=16)
    parser.add_argument("--capture-delay-seconds", type=float, default=0.02)
    parser.add_argument("--edge-pid", default="unknown")
    return parser.parse_args()


def _committed_capture_count(db_path: Path, app_name: str) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        return int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM frames
                WHERE app_name = ?
                  AND snapshot_path IS NOT NULL
                """,
                (app_name,),
            ).fetchone()[0]
        )


def _wait_for_commits(
    *,
    recorder: LossRateRecorder,
    db_path: Path,
    app_name: str,
    expected_count: int,
    timeout_seconds: float,
) -> int:
    deadline = time.monotonic() + timeout_seconds
    last_count = 0
    while time.monotonic() < deadline:
        committed = _committed_capture_count(db_path, app_name)
        last_count = committed
        if committed >= expected_count and recorder.pending_spool_count() == 0:
            return committed
        time.sleep(1.0)
    return last_count


def _emit_window(
    recorder: LossRateRecorder, *, duration_seconds: int, rate_per_sec: int
) -> int:
    start = time.monotonic()
    next_tick = start
    injected = 0
    while time.monotonic() - start < duration_seconds:
        now = time.monotonic()
        if now < next_tick:
            time.sleep(min(0.01, next_tick - now))
            continue
        second_index = int(now - start)
        for slot in range(rate_per_sec):
            index = injected + slot
            trigger = (
                CaptureTrigger.CLICK if index % 2 == 0 else CaptureTrigger.APP_SWITCH
            )
            device_name = f"monitor_loss-{index % recorder.monitor_count()}"
            recorder.inject_trigger(
                TriggerEvent(
                    capture_trigger=trigger,
                    device_name=device_name,
                    event_ts=utc_now_iso(),
                    active_app=recorder.app_name(),
                    active_window=f"{recorder.app_name()}:{second_index}:{slot}",
                )
            )
        injected += rate_per_sec
        next_tick += 1.0
    return injected


def main() -> int:
    args = parse_args()
    window_id = f"section10a-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    app_name = window_id
    rate_per_sec = args.capture_rate_per_min // 60
    recorder = LossRateRecorder(
        monitor_count=args.monitor_count,
        capture_delay_seconds=args.capture_delay_seconds,
        app_name=app_name,
    )
    worker = threading.Thread(target=recorder.run_capture_loop, daemon=True)
    worker.start()

    injected_event_count = 0
    try:
        time.sleep(2.0)
        injected_event_count = _emit_window(
            recorder,
            duration_seconds=args.duration_seconds,
            rate_per_sec=rate_per_sec,
        )
    finally:
        recorder.stop()
        worker.join(timeout=10.0)

    produced_capture_ids = recorder.generated_capture_ids()
    committed_capture_count = _wait_for_commits(
        recorder=recorder,
        db_path=args.db_path,
        app_name=app_name,
        expected_count=len(produced_capture_ids),
        timeout_seconds=120.0,
    )

    summary = compute_loss_summary(
        window_id=window_id,
        edge_pid=args.edge_pid,
        injected_event_count=injected_event_count,
        produced_capture_count=len(produced_capture_ids),
        committed_capture_count=committed_capture_count,
        duration_seconds=args.duration_seconds,
        capture_rate_per_min=args.capture_rate_per_min,
        broken_window=False,
    )

    args.capture_id_path.parent.mkdir(parents=True, exist_ok=True)
    args.capture_id_path.write_text(
        "".join(
            json.dumps({"capture_id": capture_id}) + "\n"
            for capture_id in produced_capture_ids
        ),
        encoding="utf-8",
    )
    args.summary_path.parent.mkdir(parents=True, exist_ok=True)
    args.summary_path.write_text(
        json.dumps(asdict(summary), indent=2), encoding="utf-8"
    )
    print(json.dumps(asdict(summary), indent=2))

    if summary.loss_rate >= 0.003:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
