from __future__ import annotations

import time
import queue

import pytest
from flask import Flask

from openrecall.client.recorder import MonitorWorker
from openrecall.client.recorder import ScreenRecorder
from openrecall.client.events.permissions import (
    PermissionCheckResult,
    PermissionState,
    PermissionStateMachine,
)
from openrecall.server import api_v1
from openrecall.server.config_runtime import runtime_settings


@pytest.mark.unit
def test_permission_state_machine_converges_with_2_fail_3_success() -> None:
    fsm = PermissionStateMachine()

    assert fsm.state is PermissionState.GRANTED

    fsm.record_check(PermissionCheckResult(ok=False, reason="accessibility_denied"))
    assert fsm.state is PermissionState.TRANSIENT_FAILURE

    fsm.record_check(PermissionCheckResult(ok=False, reason="accessibility_denied"))
    assert fsm.state is PermissionState.DENIED_OR_REVOKED

    fsm.record_check(PermissionCheckResult(ok=True, reason="granted"))
    assert fsm.state is PermissionState.RECOVERING

    fsm.record_check(PermissionCheckResult(ok=True, reason="granted"))
    assert fsm.state is PermissionState.RECOVERING

    fsm.record_check(PermissionCheckResult(ok=True, reason="granted"))
    assert fsm.state is PermissionState.GRANTED


@pytest.mark.unit
def test_screen_recording_failure_does_not_reclassify_as_permission_blocked() -> None:
    fsm = PermissionStateMachine()

    snapshot = fsm.record_check(
        PermissionCheckResult(ok=True, reason="screen_recording_denied")
    )

    assert snapshot.status is PermissionState.GRANTED
    assert fsm.is_degraded() is False


@pytest.mark.unit
def test_health_keeps_permission_and_screen_capture_status_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStore:
        @staticmethod
        def get_last_frame_timestamp() -> str | None:
            return "2026-03-10T12:00:00Z"

        @staticmethod
        def get_last_frame_ingested_at() -> str | None:
            return "2026-03-10T12:00:01Z"

        @staticmethod
        def get_queue_counts() -> dict[str, int]:
            return {"pending": 0, "processing": 0, "failed": 0}

    with runtime_settings._lock:
        runtime_settings.capture_permission_status = "recovering"
        runtime_settings.capture_permission_reason = "accessibility_denied"
        runtime_settings.last_permission_check_ts = "2026-03-10T12:00:00Z"
        runtime_settings.last_permission_snapshot_epoch = time.time()
        runtime_settings.screen_capture_status = "ok"
        runtime_settings.screen_capture_reason = "capture_continuing"

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: _FakeStore())

    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    client = app.test_client()

    response = client.get("/v1/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["capture_permission_status"] == "recovering"
    assert payload["screen_capture_status"] == "ok"
    assert payload["screen_capture_reason"] == "capture_continuing"


@pytest.mark.unit
def test_permission_blocked_never_enters_dedup_skip() -> None:
    worker = MonitorWorker(
        worker_id="monitor_a",
        intent_queue=queue.Queue(),
        process_intent=lambda *_args: None,
    )
    same_hash = "sha256:" + "1" * 64

    worker.record_successful_spool_write(
        final_device_name="monitor_a",
        content_hash=same_hash,
        write_time_epoch=100.0,
    )

    assert (
        worker.should_skip_dedup(
            capture_trigger="click",
            final_device_name="monitor_a",
            content_hash=same_hash,
            now_epoch=129.9,
            permission_blocked=True,
        )
        is False
    )
