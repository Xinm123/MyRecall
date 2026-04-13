# Remove LIFO Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove LIFO processing mode, always use FIFO for deterministic frame processing order.

**Architecture:** Remove `processing_lifo_threshold` config and `lifo_mode` parameter from `get_next_task()`. Simplify API responses to always indicate FIFO mode.

**Tech Stack:** Python, SQLite, Flask, Pydantic

---

## Files Changed

| File | Action |
|------|--------|
| `openrecall/server/database/sql.py` | Modify: Remove `lifo_mode` parameter from `get_next_task()` |
| `openrecall/server/worker.py` | Modify: Remove LIFO logic, always use FIFO |
| `openrecall/server/api.py` | Modify: Simplify queue status response |
| `openrecall/server/config_server.py` | Modify: Remove `processing_lifo_threshold` field and parsing |
| `openrecall/shared/config.py` | Modify: Remove `processing_lifo_threshold` field |
| `myrecall_server.toml.example` | Modify: Remove `lifo_threshold` line |
| `CLAUDE.md` | Modify: Remove LIFO documentation |

---

### Task 1: Remove `lifo_mode` parameter from `get_next_task()`

**Files:**
- Modify: `openrecall/server/database/sql.py:158-167`

- [ ] **Step 1: Update `get_next_task()` signature and implementation**

Current code (lines 158-167):
```python
def get_next_task(self, conn: sqlite3.Connection, lifo_mode: bool = False) -> Optional[RecallEntry]:
    """Get the next pending task to process."""
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        order = "DESC" if lifo_mode else "ASC"
        cursor.execute(
            f"SELECT id, app, title, text, description, timestamp, embedding, status "
            f"FROM entries WHERE status IN ('PENDING', 'CANCELLED') ORDER BY timestamp {order} LIMIT 1"
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_entry(row)
    except sqlite3.Error as e:
        logger.error(f"Database error while fetching next task: {e}")
    return None
```

New code:
```python
def get_next_task(self, conn: sqlite3.Connection) -> Optional[RecallEntry]:
    """Get the next pending task to process (FIFO - oldest first)."""
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, app, title, text, description, timestamp, embedding, status "
            "FROM entries WHERE status IN ('PENDING', 'CANCELLED') ORDER BY timestamp ASC LIMIT 1"
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_entry(row)
    except sqlite3.Error as e:
        logger.error(f"Database error while fetching next task: {e}")
    return None
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/server/database/sql.py
git commit -m "refactor(db): remove lifo_mode param from get_next_task()"
```

---

### Task 2: Update ProcessingWorker to remove LIFO logic

**Files:**
- Modify: `openrecall/server/worker.py:50-58, 136-161`

- [ ] **Step 1: Update class docstring**

Current docstring (lines 50-58):
```python
class ProcessingWorker(threading.Thread):
    """Background worker thread that processes PENDING screenshot tasks.

    Implements dynamic flow control:
    - LIFO mode (newest first) when queue size >= threshold
    - FIFO mode (oldest first) when queue size < threshold

    Thread-safe with isolated database connection.
    """
```

New docstring:
```python
class ProcessingWorker(threading.Thread):
    """Background worker thread that processes PENDING screenshot tasks.

    Uses FIFO (oldest first) processing order for deterministic behavior.

    Thread-safe with isolated database connection.
    """
```

- [ ] **Step 2: Remove LIFO logic in `run()` method**

Current code (lines 136-161):
```python
                    # Determine LIFO vs FIFO mode
                    lifo_mode = pending_count >= settings.processing_lifo_threshold
                    mode_str = (
                        "LIFO (newest first)" if lifo_mode else "FIFO (oldest first)"
                    )

                    # Get next task
                    task = (
                        sql_store.get_next_task(conn, lifo_mode=lifo_mode)
                        if sql_store
                        else None
                    )

                    if task is None:
                        # Race condition: task was taken by another process
                        if self._stop_event.wait(0.05):
                            continue
                        runtime_settings.wait_for_change(0.05)
                        continue

                    # Log processing start
                    if settings.debug:
                        logger.info(
                            f"📥 Processing task #{task.id} (timestamp={task.timestamp}) "
                            f"[Queue: {pending_count}, Mode: {mode_str}]"
                        )
```

New code:
```python
                    # Get next task (FIFO - oldest first)
                    task = (
                        sql_store.get_next_task(conn)
                        if sql_store
                        else None
                    )

                    if task is None:
                        # Race condition: task was taken by another process
                        if self._stop_event.wait(0.05):
                            continue
                        runtime_settings.wait_for_change(0.05)
                        continue

                    # Log processing start
                    if settings.debug:
                        logger.info(
                            f"📥 Processing task #{task.id} (timestamp={task.timestamp}) "
                            f"[Queue: {pending_count}]"
                        )
```

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/worker.py
git commit -m "refactor(worker): remove LIFO mode, always use FIFO"
```

---

### Task 3: Update API queue status response

**Files:**
- Modify: `openrecall/server/api.py:232-246, 329-336`

- [ ] **Step 1: Simplify queue status endpoint**

Current code (lines 232-246):
```python
        processing_mode = (
            "LIFO" if pending > settings.processing_lifo_threshold else "FIFO"
        )

        response = {
            "queue": {
                "pending": pending,
                "processing": status_counts.get("PROCESSING", 0),
                "completed": status_counts.get("COMPLETED", 0),
                "failed": status_counts.get("FAILED", 0),
            },
            "config": {
                "lifo_threshold": settings.processing_lifo_threshold,
                "current_mode": processing_mode,
            },
            "system": {
                "debug": settings.debug,
                "device": settings.device,
                "reranker_mode": settings.reranker_mode,
                "reranker_model": settings.reranker_model,
            },
        }
```

New code:
```python
        response = {
            "queue": {
                "pending": pending,
                "processing": status_counts.get("PROCESSING", 0),
                "completed": status_counts.get("COMPLETED", 0),
                "failed": status_counts.get("FAILED", 0),
            },
            "config": {
                "processing_mode": "FIFO",
            },
            "system": {
                "debug": settings.debug,
                "device": settings.device,
                "reranker_mode": settings.reranker_mode,
                "reranker_model": settings.reranker_model,
            },
        }
```

- [ ] **Step 2: Simplify upload response debug info**

Current code (lines 329-336):
```python
            # Add queue info in debug mode
            if settings.debug:
                response_data["debug"] = {
                    "queue_size": pending_count,
                    "processing_mode": "LIFO"
                    if pending_count > settings.processing_lifo_threshold
                    else "FIFO",
                }
```

New code:
```python
            # Add queue info in debug mode
            if settings.debug:
                response_data["debug"] = {
                    "queue_size": pending_count,
                    "processing_mode": "FIFO",
                }
```

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/api.py
git commit -m "refactor(api): simplify queue status, always report FIFO mode"
```

---

### Task 4: Remove `processing_lifo_threshold` from server config

**Files:**
- Modify: `openrecall/server/config_server.py:67, 118`

- [ ] **Step 1: Remove field from ServerSettings class**

Current code (line 67):
```python
    processing_lifo_threshold: int = 10
```

Remove this line entirely.

- [ ] **Step 2: Remove from `_from_dict` method**

Current code (line 118):
```python
            processing_lifo_threshold=data.get("processing.lifo_threshold", 10),
```

Remove this line entirely.

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/config_server.py
git commit -m "refactor(config-server): remove processing_lifo_threshold"
```

---

### Task 5: Remove `processing_lifo_threshold` from shared config

**Files:**
- Modify: `openrecall/shared/config.py:388-392`

- [ ] **Step 1: Remove the field**

Current code (lines 388-392):
```python
    processing_lifo_threshold: int = Field(
        default=10,
        alias="OPENRECALL_PROCESSING_LIFO_THRESHOLD",
        description="When pending tasks > threshold, use LIFO (newest first) instead of FIFO",
    )
```

Remove these lines entirely.

- [ ] **Step 2: Commit**

```bash
git add openrecall/shared/config.py
git commit -m "refactor(config): remove processing_lifo_threshold field"
```

---

### Task 6: Update TOML example config

**Files:**
- Modify: `myrecall_server.toml.example:123`

- [ ] **Step 1: Remove lifo_threshold line**

Current code (lines 120-124):
```toml
[processing]
mode = "ocr"                  # Processing mode: ocr
queue_capacity = 200          # Queue capacity
lifo_threshold = 10           # LIFO threshold
preload_models = true         # Preload models at startup
```

New code:
```toml
[processing]
mode = "ocr"                  # Processing mode: ocr
queue_capacity = 200          # Queue capacity
preload_models = true         # Preload models at startup
```

- [ ] **Step 2: Commit**

```bash
git add myrecall_server.toml.example
git commit -m "docs(config): remove lifo_threshold from example config"
```

---

### Task 7: Update CLAUDE.md documentation

**Files:**
- Modify: `CLAUDE.md:358`

- [ ] **Step 1: Remove LIFO documentation**

Find and remove the LIFO reference in the Queue Processing section. Search for:
```markdown
- LIFO mode when pending >= `processing_lifo_threshold` (default 10) — newest first
```

Remove this line from the "Queue Processing" section.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: remove LIFO mode from documentation"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run tests**

```bash
pytest -x -v
```

Expected: All tests pass.

- [ ] **Step 2: Verify no remaining LIFO references**

```bash
grep -rn "lifo" --include="*.py" openrecall/
```

Expected: No matches (except possibly in comments/docstrings that were missed).

- [ ] **Step 3: Create final commit**

```bash
git add -A
git commit -m "refactor: remove LIFO processing mode (PR 1 complete)

- Remove processing_lifo_threshold from config
- Always use FIFO (oldest first) for deterministic processing
- Simplify API queue status response
- Update documentation

Frames are now processed in strict chronological order regardless of queue depth."
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Remove `lifo_mode` from `get_next_task()` | `sql.py` |
| 2 | Update ProcessingWorker | `worker.py` |
| 3 | Simplify API response | `api.py` |
| 4 | Remove from server config | `config_server.py` |
| 5 | Remove from shared config | `config.py` |
| 6 | Update TOML example | `myrecall_server.toml.example` |
| 7 | Update documentation | `CLAUDE.md` |
| 8 | Verification & final commit | - |
