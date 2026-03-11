#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import sqlite3
import struct
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from PIL import Image


def _uuid_v7() -> str:
    ts_ms = int(time.time() * 1000) & 0xFFFF_FFFF_FFFF
    rand_bytes = __import__("os").urandom(10)
    rand_a, rand_b_raw = struct.unpack(">HQ", rand_bytes)
    rand_a &= 0x0FFF
    rand_b = (rand_b_raw & ~(0b11 << 62)) | (0b10 << 62)
    hi = (ts_ms << 16) | (0x7 << 12) | rand_a
    lo = rand_b
    h = f"{hi:016x}{lo:016x}"
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _iso_seconds(offset_seconds: int) -> str:
    return (
        (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (4, 4), color=(128, 64, 32))
    with io.BytesIO() as buffer:
        image.save(buffer, format="JPEG")
        return buffer.getvalue()


@dataclass
class CaseResult:
    name: str
    status_code: int
    response_status: str | None
    response_code: str | None
    db_count_before: int
    db_count_after: int
    queue_before: dict[str, int | str | None]
    queue_after: dict[str, int | str | None]
    latency_before: dict[str, Any]
    latency_after: dict[str, Any]


@dataclass
class GateResult:
    invalid_trigger_cases: list[CaseResult]
    missing_event_ts_case: CaseResult
    invalid_event_ts_case: CaseResult
    future_event_ts_case: CaseResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Section 9 live ingest contract gate against a live Edge",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8083")
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--summary-path", type=Path)
    return parser.parse_args()


def _queue_status(base_url: str) -> dict[str, Any]:
    response = requests.get(
        f"{base_url.rstrip('/')}/v1/ingest/queue/status", timeout=10
    )
    response.raise_for_status()
    return response.json()


def _db_count(db_path: Path) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM frames").fetchone()[0])


def _comparable_queue(status: dict[str, Any]) -> dict[str, int | str | None]:
    return {
        "pending": int(status["pending"]),
        "processing": int(status["processing"]),
        "completed": int(status["completed"]),
        "failed": int(status["failed"]),
        "processing_mode": str(status["processing_mode"]),
        "capacity": int(status["capacity"]),
    }


def _latency(status: dict[str, Any]) -> dict[str, Any]:
    return dict(status.get("capture_latency", {}))


def _post_ingest(base_url: str, metadata: dict[str, Any]) -> requests.Response:
    jpeg = _jpeg_bytes()
    files = {"file": ("test.jpg", io.BytesIO(jpeg), "image/jpeg")}
    data = {
        "capture_id": _uuid_v7(),
        "metadata": json.dumps(metadata),
    }
    return requests.post(
        f"{base_url.rstrip('/')}/v1/ingest",
        files=files,
        data=data,
        timeout=10,
    )


def _run_case(
    *,
    name: str,
    base_url: str,
    db_path: Path,
    metadata: dict[str, Any],
) -> CaseResult:
    queue_before_full = _queue_status(base_url)
    latency_before = _latency(queue_before_full)
    db_before = _db_count(db_path)

    response = _post_ingest(base_url, metadata)
    body = response.json()

    queue_after_full = _queue_status(base_url)
    latency_after = _latency(queue_after_full)
    db_after = _db_count(db_path)

    return CaseResult(
        name=name,
        status_code=response.status_code,
        response_status=body.get("status"),
        response_code=body.get("code"),
        db_count_before=db_before,
        db_count_after=db_after,
        queue_before=_comparable_queue(queue_before_full),
        queue_after=_comparable_queue(queue_after_full),
        latency_before=latency_before,
        latency_after=latency_after,
    )


def _assert_invalid_trigger(case: CaseResult) -> None:
    assert case.status_code == 400, case
    assert case.response_code == "INVALID_PARAMS", case
    assert case.db_count_before == case.db_count_after, case
    assert case.queue_before == case.queue_after, case


def _assert_event_ts_anomaly(case: CaseResult) -> None:
    assert case.status_code == 201, case
    assert case.db_count_after == case.db_count_before + 1, case
    assert (
        case.latency_after["capture_latency_sample_count"]
        == case.latency_before["capture_latency_sample_count"]
    ), case
    assert (
        case.latency_after["capture_latency_anomaly_count"]
        == case.latency_before["capture_latency_anomaly_count"] + 1
    ), case


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")

    invalid_trigger_cases = [
        _run_case(
            name="missing_capture_trigger",
            base_url=base_url,
            db_path=args.db_path,
            metadata={
                "timestamp": _iso_seconds(-1),
                "device_name": "monitor_1",
                "event_ts": _iso_seconds(-2),
            },
        ),
        _run_case(
            name="null_capture_trigger",
            base_url=base_url,
            db_path=args.db_path,
            metadata={
                "timestamp": _iso_seconds(-1),
                "capture_trigger": None,
                "device_name": "monitor_1",
                "event_ts": _iso_seconds(-2),
            },
        ),
        _run_case(
            name="invalid_capture_trigger_enum",
            base_url=base_url,
            db_path=args.db_path,
            metadata={
                "timestamp": _iso_seconds(-1),
                "capture_trigger": "scroll_stop",
                "device_name": "monitor_1",
                "event_ts": _iso_seconds(-2),
            },
        ),
    ]

    for case in invalid_trigger_cases:
        _assert_invalid_trigger(case)

    baseline = _run_case(
        name="baseline_valid_event_ts",
        base_url=base_url,
        db_path=args.db_path,
        metadata={
            "timestamp": _iso_seconds(-1),
            "capture_trigger": "manual",
            "device_name": "monitor_1",
            "event_ts": _iso_seconds(-2),
        },
    )
    assert baseline.status_code == 201, baseline

    missing_event_ts_case = _run_case(
        name="missing_event_ts",
        base_url=base_url,
        db_path=args.db_path,
        metadata={
            "timestamp": _iso_seconds(-1),
            "capture_trigger": "manual",
            "device_name": "monitor_1",
        },
    )
    _assert_event_ts_anomaly(missing_event_ts_case)

    invalid_event_ts_case = _run_case(
        name="invalid_event_ts",
        base_url=base_url,
        db_path=args.db_path,
        metadata={
            "timestamp": _iso_seconds(-1),
            "capture_trigger": "manual",
            "device_name": "monitor_1",
            "event_ts": "not-a-timestamp",
        },
    )
    _assert_event_ts_anomaly(invalid_event_ts_case)

    future_event_ts_case = _run_case(
        name="future_event_ts",
        base_url=base_url,
        db_path=args.db_path,
        metadata={
            "timestamp": _iso_seconds(-1),
            "capture_trigger": "click",
            "device_name": "monitor_1",
            "event_ts": _iso_seconds(60),
        },
    )
    _assert_event_ts_anomaly(future_event_ts_case)

    result = GateResult(
        invalid_trigger_cases=invalid_trigger_cases,
        missing_event_ts_case=missing_event_ts_case,
        invalid_event_ts_case=invalid_event_ts_case,
        future_event_ts_case=future_event_ts_case,
    )

    payload = asdict(result)
    if args.summary_path is not None:
        args.summary_path.parent.mkdir(parents=True, exist_ok=True)
        args.summary_path.write_text(json.dumps(payload, indent=2))

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
