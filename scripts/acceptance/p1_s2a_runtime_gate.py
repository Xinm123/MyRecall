#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from openrecall.client.events.base import CaptureTrigger, TriggerEvent, utc_now_iso
from openrecall.client.events.macos import list_monitors
from openrecall.client.recorder import ScreenRecorder
from openrecall.shared.config import settings


ALLOWED_TRIGGERS = ("idle", "app_switch", "manual", "click")


class GateRecorder(ScreenRecorder):
    def _start_event_sources(self) -> None:
        return None


@dataclass
class GateSummary:
    device_name: str
    trigger_counts: dict[str, int]
    trigger_coverage: float | None
    debounce_violations: int
    min_capture_interval_ms: int
    idle_capture_interval_ms: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Section 8 runtime trigger samples against a live Edge",
    )
    parser.add_argument("--db-path", type=Path, default=settings.db_path)
    parser.add_argument("--summary-path", type=Path)
    parser.add_argument("--manual-count", type=int, default=20)
    parser.add_argument("--click-count", type=int, default=20)
    parser.add_argument("--app-switch-count", type=int, default=20)
    parser.add_argument("--idle-count", type=int, default=20)
    parser.add_argument("--coverage-gap-ms", type=int, default=1100)
    parser.add_argument("--burst-count", type=int, default=30)
    parser.add_argument("--burst-gap-ms", type=int, default=100)
    parser.add_argument("--settle-seconds", type=float, default=2.0)
    return parser.parse_args()


def count_triggers(db_path: Path) -> Counter[str]:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT capture_trigger, COUNT(*)
            FROM frames
            WHERE capture_trigger IN ('idle', 'app_switch', 'manual', 'click')
            GROUP BY capture_trigger
            """
        ).fetchall()
    counts: Counter[str] = Counter({trigger: 0 for trigger in ALLOWED_TRIGGERS})
    for trigger, count in rows:
        counts[str(trigger)] = int(count)
    return counts


def trigger_coverage(db_path: Path) -> float | None:
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              COUNT(CASE
                WHEN capture_trigger IN ('idle', 'app_switch', 'manual', 'click')
                 AND device_name IS NOT NULL
                 AND event_ts IS NOT NULL
                THEN 1
              END) AS covered
            FROM frames
            """
        ).fetchone()
    if row is None or int(row[0]) == 0:
        return None
    return (int(row[1]) / int(row[0])) * 100.0


def debounce_violations(db_path: Path) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            """
            WITH ordered AS (
              SELECT
                device_name,
                timestamp,
                LAG(timestamp) OVER (
                  PARTITION BY device_name
                  ORDER BY timestamp
                ) AS prev_ts
              FROM frames
              WHERE capture_trigger IN ('app_switch', 'click')
            )
            SELECT COUNT(*)
            FROM ordered
            WHERE prev_ts IS NOT NULL
              AND ((julianday(timestamp) - julianday(prev_ts)) * 86400000.0) < ?
            """,
            (settings.min_capture_interval_ms,),
        ).fetchone()
    return int(row[0]) if row else 0


def wait_for_count(
    db_path: Path,
    trigger: str,
    target: int,
    *,
    timeout_seconds: float,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        counts = count_triggers(db_path)
        if counts[trigger] >= target:
            return
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for {trigger} count >= {target}")


def emit_trigger(
    recorder: GateRecorder,
    event: TriggerEvent,
    *,
    gap_seconds: float,
) -> None:
    while True:
        if recorder._emit_trigger(event):
            time.sleep(gap_seconds)
            return
        time.sleep(0.05)


def main() -> int:
    args = parse_args()
    monitors = list_monitors(settings.primary_monitor_only)
    if not monitors:
        raise RuntimeError("No monitors available for Section 8 runtime gate")

    device_name = monitors[0].device_name
    recorder = GateRecorder()
    worker = threading.Thread(target=recorder.run_capture_loop, daemon=True)
    worker.start()

    gap_seconds = args.coverage_gap_ms / 1000.0

    try:
        time.sleep(args.settle_seconds)

        for index in range(args.manual_count):
            while True:
                if recorder.emit_manual_trigger(device_name=device_name):
                    break
                time.sleep(0.05)
            wait_for_count(
                args.db_path,
                "manual",
                index + 1,
                timeout_seconds=max(15.0, gap_seconds * 4),
            )
            time.sleep(gap_seconds)

        for index in range(args.click_count):
            emit_trigger(
                recorder,
                TriggerEvent(
                    capture_trigger=CaptureTrigger.CLICK,
                    device_name=device_name,
                    event_ts=utc_now_iso(),
                    active_app="section8.click",
                    active_window=f"click-{index}",
                ),
                gap_seconds=gap_seconds,
            )
            wait_for_count(
                args.db_path,
                "click",
                index + 1,
                timeout_seconds=max(15.0, gap_seconds * 4),
            )

        for index in range(args.app_switch_count):
            emit_trigger(
                recorder,
                TriggerEvent(
                    capture_trigger=CaptureTrigger.APP_SWITCH,
                    device_name=device_name,
                    event_ts=utc_now_iso(),
                    active_app="section8.app_switch",
                    active_window=f"app-switch-{index}",
                ),
                gap_seconds=gap_seconds,
            )
            wait_for_count(
                args.db_path,
                "app_switch",
                index + 1,
                timeout_seconds=max(15.0, gap_seconds * 4),
            )

        wait_for_count(
            args.db_path,
            "idle",
            args.idle_count,
            timeout_seconds=(settings.idle_capture_interval_ms / 1000.0 + 10.0)
            * args.idle_count,
        )

        for index in range(args.burst_count):
            trigger = (
                CaptureTrigger.CLICK if index % 2 == 0 else CaptureTrigger.APP_SWITCH
            )
            recorder._handle_external_trigger(
                TriggerEvent(
                    capture_trigger=trigger,
                    device_name=device_name,
                    event_ts=utc_now_iso(),
                    active_app="section8.burst",
                    active_window=f"burst-{index}",
                )
            )
            time.sleep(args.burst_gap_ms / 1000.0)

        time.sleep(args.settle_seconds)
    finally:
        recorder.stop()
        worker.join(timeout=5.0)

    counts = count_triggers(args.db_path)
    coverage = trigger_coverage(args.db_path)
    violations = debounce_violations(args.db_path)

    summary = GateSummary(
        device_name=device_name,
        trigger_counts={trigger: counts[trigger] for trigger in ALLOWED_TRIGGERS},
        trigger_coverage=coverage,
        debounce_violations=violations,
        min_capture_interval_ms=settings.min_capture_interval_ms,
        idle_capture_interval_ms=settings.idle_capture_interval_ms,
    )

    if args.summary_path is not None:
        args.summary_path.parent.mkdir(parents=True, exist_ok=True)
        args.summary_path.write_text(json.dumps(asdict(summary), indent=2))

    print(json.dumps(asdict(summary), indent=2))

    if coverage != 100.0:
        return 1
    if any(counts[trigger] < 20 for trigger in ALLOWED_TRIGGERS):
        return 1
    if violations != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
