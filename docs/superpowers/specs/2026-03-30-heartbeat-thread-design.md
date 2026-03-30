# Heartbeat Thread Design

Date: 2026-03-30
Author: Claude

## Status

Approved (brainstorming) — ready for implementation planning.

## Problem

`_send_heartbeat()` currently runs synchronously inside `run_capture_loop()` (recorder.py). A blocking `requests.post()` call means network latency directly stalls the capture pipeline. This violates the architectural principle: "主采集循环完全不受网络延迟影响."

## Solution

Move heartbeat to an independent background thread (`HeartbeatThread`) that runs its own 5-second timer loop, completely decoupled from the capture loop.

## Architecture

```
ScreenRecorder (主线程)
  ├── run_capture_loop()     — screenshot → AX → spool (网络无关)
  ├── _trigger_channel       — 线程安全 queue
  ├── recording_enabled      — 心跳线程写入，采集线程读
  ├── upload_enabled         — 心跳线程写入，采集线程读
  └── _last_capture_outcome  — 心跳线程读取（快照复制）

HeartbeatThread (独立线程)
  └── 独立 5s 定时循环，POST /heartbeat
```

## Components

### 1. HeartbeatThread

New class in `recorder.py` (or `recorder/heartbeat.py` if extracted):

- **Responsibilities:**
  - Run a standalone `while not stop_event.is_set()` loop
  - Collect state snapshot from `ScreenRecorder`
  - POST to `POST /heartbeat`
  - Update `recording_enabled` / `upload_enabled` from response
  - Handle errors (log warning, continue)

- **Thread-safety:** All reads from `ScreenRecorder` are either:
  - Immutable values (`int`, `bool`, `float`)
  - Snapshot copies (`.snapshot()` method, `dict.copy()`, `set.copy()`)

- **Stop protocol:** Accepts a `threading.Event` shared with `ScreenRecorder.stop()`

### 2. ScreenRecorder changes

- **Remove** from `run_capture_loop()`:
  - The `if include_trigger or include_permission: self._send_heartbeat(...)` block
  - The `_last_trigger_report_time` / `_last_permission_report_time` fields (used only for heartbeat timing)
  - The `last_heartbeat_time` field

- **Add:**
  - `_heartbeat_thread: HeartbeatThread` field
  - `start()`: launch `_heartbeat_thread.start()`
  - `stop()`: set stop event + join heartbeat thread

### 3. _send_heartbeat refactor

Rename to `_build_heartbeat_payload()` and `_handle_heartbeat_response()` — pure functions with no side effects, callable from either the old location (during refactor) or the new thread.

Keep the actual `requests.post()` call in `HeartbeatThread.run()`.

## Data Flow

```
HeartbeatThread.run():
  1. snapshot = self._build_snapshot()
     - _last_permission_snapshot (ref copy, immutable)
     - _trigger_channel.snapshot() (creates new TriggerEventSnapshot)
     - _topology_epoch (int)
     - _enabled_monitor_devices (set copy)
     - _last_capture_outcome (dict copy)
  2. payload = _build_heartbeat_payload(snapshot, ...)
  3. response = requests.post(..., timeout=10)
  4. data = response.json()
  5. self.recorder.recording_enabled = data["config"].get("recording_enabled", True)
     self.recorder.upload_enabled = data["config"].get("upload_enabled", True)
  6. sleep(5)
```

## Thread-Safety Details

| Field | Access Pattern | Safe? |
|-------|---------------|-------|
| `_last_permission_snapshot` | Read by heartbeat, written by capture (permission poll) | Safe: ref copy of immutable dataclass |
| `_trigger_channel` | Read by heartbeat (snapshot), read/write by capture | Safe: `snapshot()` creates new object |
| `_topology_epoch` | Read by heartbeat, written by capture (monitor refresh) | Safe: Python int is GIL-protected for simple ops |
| `_enabled_monitor_devices` | Read by heartbeat (sorted copy), written by capture | Safe: `.copy()` before sorted() |
| `_last_capture_outcome` | Read by heartbeat (dict copy), written by capture | Safe: `.copy()` |
| `recording_enabled` | Write by heartbeat, read by capture | Safe: write happens before next capture loop iteration |
| `upload_enabled` | Write by heartbeat, read by capture | Safe: same as above |

## Error Handling

- **Network error:** Log warning, continue loop (heartbeat is best-effort)
- **Server error (5xx):** Same — log warning, continue
- **Bad response JSON:** Log warning, continue
- **Stop event set:** Exit loop cleanly

## Testing

1. **Unit test:** `HeartbeatThread` with mock HTTP server
   - Verify payload structure
   - Verify `recording_enabled` / `upload_enabled` updated from response
   - Verify thread stops cleanly on stop event

2. **Integration test:** Start `ScreenRecorder`, verify:
   - Capture loop is NOT blocked by heartbeat thread
   - `recording_enabled=False` from server stops capture loop
   - `recording_enabled=True` from server resumes capture loop

3. **Concurrency test:** Concurrent reads/writes to shared fields don't raise exceptions

## File Changes

| File | Change |
|------|--------|
| `openrecall/client/recorder.py` | Add `HeartbeatThread` class; modify `ScreenRecorder.start/stop/run_capture_loop` |
| `tests/test_p1_s2a_recorder.py` | Add tests for heartbeat thread behavior |
| `docs/superpowers/specs/2026-03-30-heartbeat-thread-design.md` | This file |
