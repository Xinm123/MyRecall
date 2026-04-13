# PR 1: Remove LIFO Mode - Design Document

**Date:** 2026-04-13
**Status:** Draft
**Scope:** Processing queue simplification

---

## Summary

Remove LIFO (Last-In-First-Out) processing mode from the server's processing worker. The system will always use FIFO (First-In-First-Out) mode, ensuring frames are processed in chronological order with deterministic behavior.

---

## Motivation

**Current Behavior:**
- When pending task count >= `processing_lifo_threshold` (default: 10), the worker processes newest frames first (LIFO)
- When pending task count < threshold, the worker processes oldest frames first (FIFO)

**Problem:**
- Non-deterministic processing order — users cannot predict when their frames will be processed
- Complexity — LIFO logic adds conditional branching without clear benefit
- Edge case handling — threshold-based switching creates unpredictable behavior

**Goal:** Simplify to always use FIFO for deterministic, time-ordered processing.

---

## Design

### Processing Order

**Before:**
```
pending_count >= threshold → LIFO (newest first)
pending_count < threshold  → FIFO (oldest first)
```

**After:**
```
Always FIFO (oldest first)
```

### Files Changed

| File | Change |
|------|--------|
| `openrecall/server/worker.py` | Remove LIFO condition, always use FIFO |
| `openrecall/server/database/sql.py` | `get_next_task()` remove `lifo_mode` parameter |
| `openrecall/server/api.py` | Remove "LIFO"/"FIFO" status from queue status endpoint |
| `openrecall/shared/config.py` | Remove `processing_lifo_threshold` field |
| `openrecall/server/config_server.py` | Remove `processing_lifo_threshold` parsing |
| `myrecall_server.toml.example` | Remove `lifo_threshold` example |
| `CLAUDE.md` | Update documentation to remove LIFO references |

---

## Implementation Details

### 1. `openrecall/server/worker.py`

**Current code (lines 136-144):**
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
```

**New code:**
```python
# Get next task (FIFO - oldest first)
task = (
    sql_store.get_next_task(conn)
    if sql_store
    else None
)
```

### 2. `openrecall/server/database/sql.py`

**Current code (lines 158-166):**
```python
def get_next_task(self, conn: sqlite3.Connection, lifo_mode: bool = False) -> Optional[RecallEntry]:
    """Get the next pending task from the queue.

    Args:
        conn: Database connection
        lifo_mode: If True, get newest task; otherwise oldest
    """
    order = "DESC" if lifo_mode else "ASC"
```

**New code:**
```python
def get_next_task(self, conn: sqlite3.Connection) -> Optional[RecallEntry]:
    """Get the next pending task from the queue (FIFO - oldest first)."""
    order = "ASC"
```

### 3. `openrecall/server/api.py`

**Current code (lines 233-234, 333-334):**
```python
"LIFO" if pending > settings.processing_lifo_threshold else "FIFO"
# and
"processing_mode": "LIFO" if pending_count > settings.processing_lifo_threshold else "FIFO"
```

**New code:**
Remove `lifo_threshold` field, keep `current_mode` field for backwards compatibility:
```python
"config": {
    "current_mode": "FIFO",
},
```

### 4. `openrecall/shared/config.py`

**Current code (lines 388-392):**
```python
processing_lifo_threshold: int = Field(
    default=10,
    alias="OPENRECALL_PROCESSING_LIFO_THRESHOLD",
    description="When pending tasks > threshold, use LIFO (newest first) instead of FIFO",
)
```

**New code:**
Remove this field entirely.

### 5. `openrecall/server/config_server.py`

**Current code (lines 67, 118):**
```python
processing_lifo_threshold: int = 10
# and
processing_lifo_threshold=data.get("processing.lifo_threshold", 10),
```

**New code:**
Remove these lines.

### 6. `myrecall_server.toml.example`

**Current code (line 123):**
```toml
lifo_threshold = 10           # LIFO threshold
```

**New code:**
Remove this line.

---

## Migration

No database migration required. This is a code-only change.

**Backwards Compatibility:**
- Existing `myrecall_server.toml` files with `lifo_threshold` will log a warning about unknown config key (handled by existing TOML parser)
- API responses keep `current_mode` field name (backwards compatible), but always return `"FIFO"`
- API responses remove `lifo_threshold` field (clients should not depend on it)

---

## Testing

**Unit Tests:**
- Update tests that mock `get_next_task()` to remove `lifo_mode` parameter
- Add test verifying FIFO order is maintained under various queue sizes

**Integration Tests:**
- Verify frames are processed in timestamp order regardless of queue depth

---

## Out of Scope

This PR does NOT include:
- New `completed_status` field
- Changes to `description_status` or `embedding_status` logic
- API filtering changes

These are planned for a follow-up PR.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Users expect newest frames processed first during backlog | Document the change in release notes; users can still search by timestamp to find recent content |
| Existing config files have stale `lifo_threshold` | TOML parser ignores unknown keys; no error |
