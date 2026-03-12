from __future__ import annotations

import json
import queue
import time
from pathlib import Path

import numpy as np
import pytest

from openrecall.client.accessibility.types import (
    AccessibilityRawHandoff,
    FocusedContext,
)
from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    TriggerIntent,
)
from openrecall.client.recorder import MonitorWorker, ScreenRecorder
from openrecall.shared.config import Settings


def _read_first_forensic_payload(log_path: Path) -> dict[str, object]:
    content = log_path.read_text(encoding="utf-8")
    json_start = content.index("{")
    return json.loads(content[json_start:])


@pytest.mark.unit
def test_plaintext_forensic_log_setting_defaults_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENRECALL_PLAINTEXT_FORENSIC_LOG_ENABLED", raising=False)
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))

    settings = Settings()

    assert settings.plaintext_forensic_log_enabled is True


@pytest.mark.unit
def test_plaintext_forensic_log_setting_can_be_disabled_via_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENRECALL_PLAINTEXT_FORENSIC_LOG_ENABLED", "false")
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))

    settings = Settings()

    assert settings.plaintext_forensic_log_enabled is False


@pytest.mark.unit
def test_write_plaintext_forensic_log_persists_full_plaintext_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    recorder = ScreenRecorder()
    monkeypatch.setattr("openrecall.client.recorder.settings.client_data_dir", tmp_path)
    monkeypatch.setattr(
        "openrecall.client.recorder.settings.plaintext_forensic_log_enabled", True
    )
    recorder._runtime_started_at = "2026-03-12T12:34:56Z"
    recorder._host_pid = 4321

    metadata = {
        "timestamp": "2026-03-12T12:35:00Z",
        "capture_trigger": "click",
        "device_name": "monitor_1",
        "event_device_hint": "monitor_hint",
        "event_ts": "2026-03-12T12:34:59Z",
        "active_app": "Legacy App",
        "active_window": "Legacy Window",
        "app_name": "AX App",
        "window_name": "AX Window Full Title",
        "browser_url": "https://example.com/path?q=1",
        "browser_url_classification": "browser_url_success",
        "focused": True,
        "accessibility_text": "Secret plaintext from AX",
        "content_hash": "sha256:" + "1" * 64,
        "outcome": "capture_completed",
        "capture_cycle_latency_ms": 137,
        "host_pid": 4321,
        "runtime_started_at": "2026-03-12T12:34:56Z",
    }

    recorder._write_plaintext_forensic_log(
        metadata=metadata,
        capture_id="capture-001",
        screenshot_path=str(tmp_path / "spool" / "capture-001.jpg"),
        spool_metadata_path=str(tmp_path / "spool" / "capture-001.json"),
        local_screenshot_path=str(tmp_path / "screenshots" / "capture-001.webp"),
    )

    log_path = recorder._plaintext_forensic_log_path()
    content = log_path.read_text(encoding="utf-8")
    assert '  "accessibility_text": "Secret plaintext from AX"' in content
    payload = _read_first_forensic_payload(log_path)
    assert payload["capture_id"] == "capture-001"
    assert payload["accessibility_text"] == "Secret plaintext from AX"
    assert payload["browser_url"] == "https://example.com/path?q=1"
    assert payload["window_name"] == "AX Window Full Title"
    assert str(payload["screenshot_path"]).endswith("capture-001.jpg")
    assert str(payload["spool_metadata_path"]).endswith("capture-001.json")
    assert str(payload["local_screenshot_path"]).endswith("capture-001.webp")


@pytest.mark.unit
def test_write_plaintext_forensic_log_skips_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    recorder = ScreenRecorder()
    monkeypatch.setattr("openrecall.client.recorder.settings.client_data_dir", tmp_path)
    monkeypatch.setattr(
        "openrecall.client.recorder.settings.plaintext_forensic_log_enabled", False
    )

    recorder._write_plaintext_forensic_log(
        metadata={"capture_trigger": "click"},
        capture_id=None,
        screenshot_path=None,
        spool_metadata_path=None,
        local_screenshot_path=None,
    )

    assert recorder._plaintext_forensic_log_path().exists() is False


@pytest.mark.unit
def test_process_intent_writes_plaintext_forensic_log_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    recorder = ScreenRecorder()
    monkeypatch.setattr("openrecall.client.recorder.settings.client_data_dir", tmp_path)
    monkeypatch.setattr(
        "openrecall.client.recorder.settings.plaintext_forensic_log_enabled", True
    )
    recorder._runtime_started_at = "2026-03-12T12:34:56Z"
    recorder._host_pid = 4321

    monitor = MonitorDescriptor(
        stable_id="1",
        left=0,
        top=0,
        width=100,
        height=100,
        is_primary=True,
    )
    recorder._monitor_registry.refresh([monitor])
    worker = MonitorWorker(
        worker_id=monitor.device_name,
        intent_queue=queue.Queue(),
        process_intent=lambda *_args: None,
    )

    monkeypatch.setattr(
        recorder,
        "_capture_monitors",
        lambda _monitors: {
            monitor.device_name: np.ones((2, 2, 3), dtype=np.uint8) * 255,
        },
    )
    monkeypatch.setattr(recorder, "_warn_if_blank_frame", lambda *_args: None)

    class _Service:
        def collect_raw_handoff(self, **_kwargs: object) -> AccessibilityRawHandoff:
            return AccessibilityRawHandoff(
                accessibility_text="Secret plaintext from AX",
                content_hash="sha256:" + "2" * 64,
                focused_context=FocusedContext(
                    app_name="AX App",
                    window_name="AX Window Full Title",
                    browser_url="https://example.com/path?q=1",
                ),
                browser_url_classification="browser_url_success",
                event_device_hint="monitor_hint",
                final_device_name=monitor.device_name,
                outcome="capture_completed",
            )

    monkeypatch.setattr(recorder, "_accessibility_service", _Service(), raising=False)

    def _enqueue(_image: object, _metadata: dict[str, object]) -> str:
        return "capture-001"

    monkeypatch.setattr(recorder._spool, "enqueue", _enqueue)
    monkeypatch.setattr(recorder._spool, "count", lambda: 1)

    recorder._process_trigger_intent_for_monitor(
        worker,
        TriggerIntent(
            capture_trigger=CaptureTrigger.CLICK,
            event_ts="event-ts",
            event_device_hint="monitor_hint",
            active_app="Legacy App",
            active_window="Legacy Window",
        ),
        time.perf_counter(),
    )

    payload = _read_first_forensic_payload(recorder._plaintext_forensic_log_path())
    assert payload["capture_id"] == "capture-001"
    assert payload["outcome"] == "capture_completed"
    assert payload["accessibility_text"] == "Secret plaintext from AX"
    assert payload["browser_url"] == "https://example.com/path?q=1"
    assert payload["window_name"] == "AX Window Full Title"
    assert str(payload["screenshot_path"]).endswith("capture-001.jpg")


@pytest.mark.unit
def test_write_plaintext_forensic_log_appends_pretty_printed_blocks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    recorder = ScreenRecorder()
    monkeypatch.setattr("openrecall.client.recorder.settings.client_data_dir", tmp_path)
    monkeypatch.setattr(
        "openrecall.client.recorder.settings.plaintext_forensic_log_enabled", True
    )

    recorder._write_plaintext_forensic_log(
        metadata={"capture_trigger": "click", "accessibility_text": "first"},
        capture_id="capture-001",
        screenshot_path=None,
        spool_metadata_path=None,
        local_screenshot_path=None,
    )
    recorder._write_plaintext_forensic_log(
        metadata={"capture_trigger": "manual", "accessibility_text": "second"},
        capture_id="capture-002",
        screenshot_path=None,
        spool_metadata_path=None,
        local_screenshot_path=None,
    )

    content = recorder._plaintext_forensic_log_path().read_text(encoding="utf-8")
    assert content.count("{\n") == 2
    assert (
        "==== capture-001 | unknown-timestamp | click | unknown-device | unknown-outcome ===="
        in content
    )
    assert (
        "==== capture-002 | unknown-timestamp | manual | unknown-device | unknown-outcome ===="
        in content
    )
    assert '\n  "capture_id": "capture-001"' in content
    assert '\n  "capture_id": "capture-002"' in content
