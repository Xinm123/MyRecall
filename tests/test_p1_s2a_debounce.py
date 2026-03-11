from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from openrecall.client.events.base import CaptureTrigger, TriggerEvent
from openrecall.client.recorder import ScreenRecorder
from openrecall.server import __main__ as server_main


def _iso_now_minus_ms(milliseconds: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(milliseconds=milliseconds))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _seed_event(
    conn: sqlite3.Connection,
    *,
    capture_id: str,
    capture_trigger: str,
    device_name: str,
    event_ts: str,
) -> None:
    conn.execute(
        """
        INSERT INTO frames (
            capture_id, timestamp, app_name, window_name, device_name,
            snapshot_path, capture_trigger, event_ts, status, ingested_at, processed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            capture_id,
            event_ts,
            "Finder",
            "Desktop",
            device_name,
            f"/tmp/{capture_id}.jpg",
            capture_trigger,
            event_ts,
            "completed",
            event_ts,
            event_ts,
        ),
    )


def _count_debounce_violations(db_path: Path, min_interval_ms: int) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT device_name, capture_trigger, event_ts
            FROM frames
            WHERE capture_trigger IN ('app_switch', 'click')
            ORDER BY device_name ASC, event_ts ASC
            """
        ).fetchall()

    previous_by_device: dict[str, datetime] = {}
    violations = 0
    for row in rows:
        device_name = row["device_name"]
        event_ts = datetime.fromisoformat(row["event_ts"].replace("Z", "+00:00"))
        previous = previous_by_device.get(device_name)
        if previous is not None:
            delta_ms = (event_ts - previous).total_seconds() * 1000.0
            if delta_ms < min_interval_ms:
                violations += 1
        previous_by_device[device_name] = event_ts
    return violations


@pytest.mark.unit
def test_debounce_violation_count_is_zero_for_same_device_samples(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "edge.db"
    server_main.ensure_v3_schema(db_path=db_path)

    with sqlite3.connect(str(db_path)) as conn:
        _seed_event(
            conn,
            capture_id="debounce-1",
            capture_trigger="click",
            device_name="monitor_1",
            event_ts="2026-03-10T12:00:00.000Z",
        )
        _seed_event(
            conn,
            capture_id="debounce-2",
            capture_trigger="app_switch",
            device_name="monitor_1",
            event_ts="2026-03-10T12:00:01.000Z",
        )
        _seed_event(
            conn,
            capture_id="debounce-3",
            capture_trigger="click",
            device_name="monitor_2",
            event_ts="2026-03-10T12:00:00.500Z",
        )
        _seed_event(
            conn,
            capture_id="debounce-4",
            capture_trigger="app_switch",
            device_name="monitor_2",
            event_ts="2026-03-10T12:00:01.700Z",
        )
        conn.commit()

    assert _count_debounce_violations(db_path, min_interval_ms=1000) == 0


@pytest.mark.unit
def test_debounce_violation_count_detects_sub_interval_same_device_samples(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "edge.db"
    server_main.ensure_v3_schema(db_path=db_path)

    with sqlite3.connect(str(db_path)) as conn:
        _seed_event(
            conn,
            capture_id="violation-1",
            capture_trigger="click",
            device_name="monitor_1",
            event_ts="2026-03-10T12:00:00.000Z",
        )
        _seed_event(
            conn,
            capture_id="violation-2",
            capture_trigger="app_switch",
            device_name="monitor_1",
            event_ts="2026-03-10T12:00:00.250Z",
        )
        conn.commit()

    assert _count_debounce_violations(db_path, min_interval_ms=1000) == 1


@pytest.mark.unit
def test_manual_and_idle_share_the_same_debounce_gate() -> None:
    recorder = ScreenRecorder()

    accepted_manual = recorder.emit_manual_trigger(
        device_name="monitor_1",
        now_ms=1000,
        event_ts="2026-03-10T00:00:00Z",
    )
    accepted_idle = recorder._emit_trigger(
        TriggerEvent(
            capture_trigger=CaptureTrigger.IDLE,
            device_name="monitor_1",
            event_ts="2026-03-10T00:00:00.500Z",
        ),
        now_ms=1500,
    )
    accepted_idle_after_window = recorder._emit_trigger(
        TriggerEvent(
            capture_trigger=CaptureTrigger.IDLE,
            device_name="monitor_1",
            event_ts="2026-03-10T00:00:01.100Z",
        ),
        now_ms=2100,
    )

    assert accepted_manual is True
    assert accepted_idle is False
    assert accepted_idle_after_window is True
