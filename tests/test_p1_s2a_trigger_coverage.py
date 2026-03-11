from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from openrecall.server import __main__ as server_main


ALLOWED_TRIGGERS = ("idle", "app_switch", "manual", "click")


def _iso_now_minus(seconds: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(seconds=seconds))
        .isoformat()
        .replace("+00:00", "Z")
    )


def _seed_frame(
    conn: sqlite3.Connection,
    *,
    capture_id: str,
    capture_trigger: str,
    device_name: str,
    event_ts: str | None,
) -> None:
    timestamp = _iso_now_minus(5)
    conn.execute(
        """
        INSERT INTO frames (
            capture_id, timestamp, app_name, window_name, device_name,
            snapshot_path, capture_trigger, event_ts, status, ingested_at, processed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            capture_id,
            timestamp,
            "Finder",
            "Desktop",
            device_name,
            f"/tmp/{capture_id}.jpg",
            capture_trigger,
            event_ts,
            "completed",
            timestamp,
            timestamp,
        ),
    )


def _load_trigger_samples(db_path: Path) -> list[dict[str, str | None]]:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT capture_trigger, device_name, event_ts
            FROM frames
            ORDER BY id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _compute_trigger_coverage(
    samples: list[dict[str, str | None]],
) -> tuple[float | None, Counter[str]]:
    if not samples:
        return None, Counter()

    covered = 0
    counts: Counter[str] = Counter()
    for sample in samples:
        trigger = sample["capture_trigger"]
        if trigger in ALLOWED_TRIGGERS and sample["device_name"] and sample["event_ts"]:
            covered += 1
            counts[str(trigger)] += 1

    return (covered / len(samples)) * 100.0, counts


@pytest.mark.unit
def test_trigger_coverage_reaches_100_percent_with_four_trigger_classes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "edge.db"
    server_main.ensure_v3_schema(db_path=db_path)

    with sqlite3.connect(str(db_path)) as conn:
        for trigger_index, trigger in enumerate(ALLOWED_TRIGGERS):
            for sample_index in range(20):
                _seed_frame(
                    conn,
                    capture_id=f"coverage-{trigger_index}-{sample_index}",
                    capture_trigger=trigger,
                    device_name=f"monitor_{trigger_index % 2}",
                    event_ts=_iso_now_minus(sample_index + 1),
                )
        conn.commit()

    coverage, counts = _compute_trigger_coverage(_load_trigger_samples(db_path))

    assert coverage == 100.0
    assert set(counts) == set(ALLOWED_TRIGGERS)
    assert all(counts[trigger] >= 20 for trigger in ALLOWED_TRIGGERS)


@pytest.mark.unit
def test_trigger_coverage_drops_when_required_metadata_is_missing(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "edge.db"
    server_main.ensure_v3_schema(db_path=db_path)

    with sqlite3.connect(str(db_path)) as conn:
        _seed_frame(
            conn,
            capture_id="valid-sample",
            capture_trigger="click",
            device_name="monitor_1",
            event_ts=_iso_now_minus(1),
        )
        _seed_frame(
            conn,
            capture_id="missing-event-ts",
            capture_trigger="manual",
            device_name="monitor_1",
            event_ts=None,
        )
        conn.commit()

    coverage, counts = _compute_trigger_coverage(_load_trigger_samples(db_path))

    assert coverage == 50.0
    assert counts == Counter({"click": 1})
