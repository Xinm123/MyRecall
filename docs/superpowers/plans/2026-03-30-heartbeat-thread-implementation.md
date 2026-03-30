# Heartbeat Thread Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move heartbeat from synchronous call in `run_capture_loop()` to an independent `HeartbeatThread` so the capture pipeline is never blocked by network latency.

**Architecture:** Add `HeartbeatThread` (daemon thread) to `recorder.py` that runs its own 5-second timer loop. Refactor `_send_heartbeat` into pure functions (`_build_heartbeat_payload`, `_handle_heartbeat_response`). Remove heartbeat call from capture loop entirely.

**Tech Stack:** Python `threading`, `requests`, `threading.Event`

---

## File Changes Summary

| File | Change |
|------|--------|
| `openrecall/client/recorder.py` | Add `HeartbeatThread` class; modify `__init__`, `start()`, `stop()`, `run_capture_loop()` |
| `tests/test_p1_s2a_recorder.py` | Add unit tests for heartbeat thread |

---

## Task 1: Write failing tests for HeartbeatThread

**Files:**
- Modify: `tests/test_p1_s2a_recorder.py`

- [ ] **Step 1: Add heartbeat thread tests**

Add the following test class to `tests/test_p1_s2a_recorder.py`:

```python
import threading
import time
from unittest.mock import patch, MagicMock

import pytest

from openrecall.client.recorder import HeartbeatThread, ScreenRecorder


class TestHeartbeatThread:
    """Tests for HeartbeatThread independent background heartbeat."""

    def test_thread_posts_heartbeat_and_updates_config(self):
        """HeartbeatThread should POST /heartbeat and update recording_enabled from response."""
        recorder = ScreenRecorder()
        stop_event = threading.Event()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "config": {"recording_enabled": False, "upload_enabled": False},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response) as mock_post:
            with patch("time.sleep", return_value=None) as mock_sleep:
                thread = HeartbeatThread(recorder=recorder, stop_event=stop_event)
                thread.start()
                # Wait for one heartbeat cycle
                time.sleep(0.1)
                stop_event.set()
                thread.join(timeout=2.0)

        # Verify POST was called
        assert mock_post.called
        # Verify recording_enabled updated from response
        assert recorder.recording_enabled is False
        assert recorder.upload_enabled is False

    def test_thread_stops_cleanly_on_stop_event(self):
        """HeartbeatThread should exit when stop_event is set."""
        recorder = ScreenRecorder()
        stop_event = threading.Event()

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok", "config": {}}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response):
            with patch("time.sleep", return_value=None):
                thread = HeartbeatThread(recorder=recorder, stop_event=stop_event)
                thread.start()
                stop_event.set()
                thread.join(timeout=2.0)

        assert not thread.is_alive()

    def test_thread_continues_on_network_error(self):
        """HeartbeatThread should log warning and continue loop on network error."""
        recorder = ScreenRecorder()
        stop_event = threading.Event()

        import requests as req

        with patch("requests.post", side_effect=req.RequestException("network error")):
            with patch("time.sleep", return_value=None) as mock_sleep:
                with patch("openrecall.client.recorder.logger") as mock_logger:
                    thread = HeartbeatThread(recorder=recorder, stop_event=stop_event)
                    thread.start()
                    time.sleep(0.1)
                    stop_event.set()
                    thread.join(timeout=2.0)

        assert mock_logger.warning.called

    def test_payload_contains_required_fields(self):
        """HeartbeatThread payload should include permission, trigger, and runtime info."""
        recorder = ScreenRecorder()
        recorder._last_permission_snapshot = MagicMock()
        recorder._last_permission_snapshot.status.value = "granted"
        recorder._last_permission_snapshot.reason = "ok"
        recorder._last_permission_snapshot.last_check_ts = "2026-03-30T00:00:00Z"
        recorder._trigger_channel = MagicMock()
        recorder._trigger_channel.snapshot.return_value = MagicMock(
            queue_depth=0, queue_capacity=100, collapse_trigger_count=0, overflow_drop_count=0
        )
        recorder._topology_epoch = 1
        recorder._enabled_monitor_devices = {"monitor_1"}
        recorder._last_capture_outcome = {"outcome": "capture_completed"}

        stop_event = threading.Event()

        captured_payload = {}

        def capture_payload(*args, **kwargs):
            captured_payload["json"] = kwargs.get("json", {})
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"status": "ok", "config": {}}
            mock_resp.raise_for_status = MagicMock()
            stop_event.set()
            return mock_resp

        with patch("requests.post", side_effect=capture_payload):
            with patch("time.sleep", return_value=None):
                thread = HeartbeatThread(recorder=recorder, stop_event=stop_event)
                thread.start()
                thread.join(timeout=2.0)

        payload = captured_payload.get("json", {})
        assert "capture_permission_status" in payload
        assert "capture_runtime" in payload
        assert payload["capture_runtime"]["topology_epoch"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_p1_s2a_recorder.py::TestHeartbeatThread -v`
Expected: FAIL — `HeartbeatThread` not yet defined

---

## Task 2: Implement HeartbeatThread class

**Files:**
- Modify: `openrecall/client/recorder.py:1` (add imports)
- Modify: `openrecall/client/recorder.py` (add class after SpoolUploader reference)

- [ ] **Step 1: Add imports**

Add `import threading` and `import requests` to recorder.py imports if not already present (check existing imports).

- [ ] **Step 2: Add HeartbeatThread class**

Add after the `SpoolUploader` class definition (around line 190, before `_uploader: Optional[SpoolUploader] = None`):

```python
class HeartbeatThread(threading.Thread):
    """Independent background thread that sends heartbeat to server.

    Runs its own 5-second timer loop, completely decoupled from the
    capture loop. Posts /heartbeat and updates recording_enabled /
    upload_enabled from the server response.

    Thread-safety: All reads from ScreenRecorder use snapshot copies
    (dict.copy(), set.copy(), TriggerChannel.snapshot()) to avoid
    holding locks on the main capture loop.
    """

    HEARTBEAT_INTERVAL_SEC = 5

    def __init__(
        self,
        recorder: "ScreenRecorder",
        stop_event: threading.Event,
        name: str = "HeartbeatThread",
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.recorder = recorder
        self._stop_event = stop_event

    def run(self) -> None:
        """Send heartbeat every 5 seconds until stop event is set."""
        logger.info("heartbeat: HeartbeatThread started")

        while not self._stop_event.is_set():
            try:
                self._send_heartbeat()
            except Exception:
                logger.warning("HeartbeatThread: unexpected error: %s", exc_info=True)

            # Wait for next interval or stop signal
            self._stop_event.wait(timeout=self.HEARTBEAT_INTERVAL_SEC)

        logger.info("heartbeat: HeartbeatThread stopped")

    def _send_heartbeat(self) -> None:
        """Build payload, POST to /heartbeat, update config from response."""
        url = f"{settings.api_url.rstrip('/')}/heartbeat"

        # Build snapshot of recorder state (thread-safe reads)
        payload: dict[str, object] = {}

        # Permission snapshot (frozen dataclass, safe to share)
        perm = self.recorder._last_permission_snapshot
        payload["capture_permission_status"] = perm.status.value
        payload["capture_permission_reason"] = perm.reason
        payload["last_permission_check_ts"] = perm.last_check_ts

        # Trigger channel snapshot (creates new object)
        trigger_snapshot = self.recorder.trigger_channel_snapshot()
        payload["queue_depth"] = trigger_snapshot.queue_depth
        payload["queue_capacity"] = trigger_snapshot.queue_capacity
        payload["collapse_trigger_count"] = trigger_snapshot.collapse_trigger_count
        payload["overflow_drop_count"] = trigger_snapshot.overflow_drop_count

        # Runtime info (copy-on-read for mutable containers)
        payload["capture_runtime"] = {
            "topology_epoch": self.recorder._topology_epoch,
            "primary_monitor_only": settings.primary_monitor_only,
            "active_monitors": sorted(self.recorder._enabled_monitor_devices.copy()),
            "last_capture_outcome": self.recorder._last_capture_outcome.copy(),
        }

        try:
            response = requests.post(
                url,
                json=payload,
                **_build_request_kwargs(url, timeout=10),
            )
            response.raise_for_status()

            data = response.json()
            config = data.get("config", {})
            # Write back to recorder (safe: next capture loop iteration sees new value)
            self.recorder.recording_enabled = config.get("recording_enabled", True)
            self.recorder.upload_enabled = config.get("upload_enabled", True)

            if settings.debug:
                logger.debug(
                    "heartbeat: synced recording=%s upload=%s",
                    self.recorder.recording_enabled,
                    self.recorder.upload_enabled,
                )
        except requests.RequestException as e:
            logger.warning("heartbeat: network error: %s", e)
        except Exception as e:
            logger.warning("heartbeat: failed: %s", e)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/test_p1_s2a_recorder.py::TestHeartbeatThread -v`
Expected: PASS

---

## Task 3: Integrate HeartbeatThread into ScreenRecorder

**Files:**
- Modify: `openrecall/client/recorder.py`

- [ ] **Step 1: Add _heartbeat_thread field in __init__**

In `ScreenRecorder.__init__` (around line 278), add:

```python
self._heartbeat_thread: HeartbeatThread | None = None
```

Add it after `self._app_switch_monitor: MacOSAppSwitchMonitor | None = None` (line 278).

- [ ] **Step 2: Add _last_permission_report_time and _last_trigger_report_time removal**

These fields are no longer needed (used only for the old heartbeat timing in the capture loop). Remove these lines from `__init__`:
- `self._last_permission_report_time: float = 0.0` (around line 251)
- `self._last_trigger_report_time: float = 0.0` (around line 252)

Also remove `self.last_heartbeat_time: float = 0.0` (around line 250).

- [ ] **Step 3: Modify start() to launch HeartbeatThread**

Replace the current `start()` method (line 333):

```python
def start(self) -> None:
    """Start the consumer thread and heartbeat thread."""
    if self.consumer is not None and not self.consumer.is_alive():
        self.consumer.start()
    if not self._spool_uploader.is_alive():
        self._spool_uploader.start()
    if self._heartbeat_thread is None:
        self._heartbeat_thread = HeartbeatThread(recorder=self, stop_event=self._stop_event)
        self._heartbeat_thread.start()
```

- [ ] **Step 4: Modify stop() to stop HeartbeatThread**

In `stop()` (around line 472), add heartbeat thread shutdown:

Find the existing stop block and add:

```python
# Stop heartbeat thread
if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
    self._heartbeat_thread.join(timeout=2.0)
```

Add after the spool uploader stop, before the thread join section (around line 501).

- [ ] **Step 5: Remove heartbeat call from run_capture_loop()**

In `run_capture_loop()` (around line 1149-1163), remove the entire heartbeat block:

```python
# REMOVE THIS BLOCK:
# Phase 8.2: Sync runtime configuration every 5 seconds
current_time = time.time()
include_trigger = current_time - self._last_trigger_report_time >= 5
include_permission = current_time - self._last_permission_report_time >= 5
if include_trigger or include_permission:
    self._send_heartbeat(
        include_permission=include_permission,
        include_trigger=include_trigger,
    )
    self.last_heartbeat_time = current_time
    if include_trigger:
        self._last_trigger_report_time = current_time
    if include_permission:
        self._last_permission_report_time = current_time
```

The `self._poll_permissions(now_epoch=current_time)` call (line 1164) should remain — move it to the top of the loop if needed to ensure it runs even when recording is paused.

Also remove `self._poll_permissions(now_epoch=current_time)` from the old heartbeat block and place it at the beginning of the while loop (before the recording_enabled check), since it should run independently:

```python
while not self._stop_requested:
    self._poll_permissions(now_epoch=time.time())
    if not self.recording_enabled:
        ...
```

- [ ] **Step 6: Remove _send_heartbeat method**

Delete the entire `_send_heartbeat` method (lines 340-398) from `ScreenRecorder`. The logic is now in `HeartbeatThread._send_heartbeat()`.

- [ ] **Step 7: Run unit tests to verify nothing is broken**

Run: `pytest tests/test_p1_s2a_recorder.py -v`
Expected: All tests PASS

---

## Task 4: Final verification

- [ ] **Step 1: Run all recorder-related tests**

Run: `pytest tests/test_p1_s2a_recorder.py tests/test_p1_s1_uploader_retry.py -v`
Expected: All PASS

- [ ] **Step 2: Run linter**

Run: `ruff check openrecall/client/recorder.py`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/recorder.py tests/test_p1_s2a_recorder.py
git commit -m "$(cat <<'EOF'
feat(client): move heartbeat to independent HeartbeatThread

Decouples heartbeat network calls from the capture loop so network
latency never stalls screenshot → AX → spool pipeline.

HeartbeatThread runs its own 5-second timer loop, reads recorder
state via snapshot copies (thread-safe), and writes back
recording_enabled/upload_enabled from the server response.
EOF
)"
```

---

## Self-Review Checklist

- [ ] Spec Section 1 (HeartbeatThread): Task 2 implements this
- [ ] Spec Section 2 (ScreenRecorder changes): Tasks 3.2–3.6 implement this
- [ ] Spec Section 3 (_send_heartbeat refactor): Task 2.2 + 3.6 implement this
- [ ] Spec Data Flow: HeartbeatThread.run() matches spec diagram
- [ ] Spec Thread-Safety: All reads use copy() or snapshot()
- [ ] Spec Error Handling: requests.RequestException and general Exception both caught
- [ ] No placeholder / TODO / TBD in any step
- [ ] All code is complete (not "implement similar pattern")
- [ ] Type consistency: `HeartbeatThread(recorder=recorder, stop_event=stop_event)` matches `__init__` signature
