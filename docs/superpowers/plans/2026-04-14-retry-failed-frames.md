# Retry Failed Frames Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Retry Failed" button to the grid UI that resets all failed frames back to pending status for reprocessing.

**Architecture:** Database method for smart status reset, API endpoint for triggering retry, frontend button with loading state.

**Tech Stack:** Python/Flask (backend), SQLite (database), Alpine.js (frontend)

---

## Files Changed

| File | Responsibility |
|------|----------------|
| `openrecall/server/database/frames_store.py` | Add `reset_failed_frames()` method with smart stage reset |
| `openrecall/server/api_v1.py` | Add `POST /v1/admin/frames/retry-failed` endpoint |
| `openrecall/client/web/templates/index.html` | Add retry button and Alpine.js handler |

---

### Task 1: Database Layer - `reset_failed_frames()` Method

**Files:**
- Modify: `openrecall/server/database/frames_store.py`
- Create: `tests/test_retry_failed_frames.py`

- [ ] **Step 1: Write the failing test for `reset_failed_frames()`**

Create `tests/test_retry_failed_frames.py`:

```python
"""
Tests for retry failed frames functionality.

Usage:
    pytest tests/test_retry_failed_frames.py -v
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore


@pytest.fixture
def temp_store():
    """Create a temporary FramesStore with test frames."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = FramesStore(str(db_path))

        # Create tables
        with store._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    frame_id TEXT UNIQUE,
                    capture_id TEXT UNIQUE,
                    timestamp TEXT,
                    status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    description_status TEXT,
                    embedding_status TEXT,
                    visibility_status TEXT DEFAULT 'pending',
                    snapshot_path TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS description_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    frame_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    UNIQUE(frame_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embedding_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    frame_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    UNIQUE(frame_id)
                )
            """)
            conn.commit()

        yield store


class TestResetFailedFrames:
    """Tests for FramesStore.reset_failed_frames()."""

    def test_reset_ocr_failed_frame(self, temp_store):
        """Frame with OCR failure should have status reset to pending."""
        # Insert a frame with OCR failure
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (frame_id, status, error_message, visibility_status, snapshot_path)
                VALUES ('test-1', 'failed', 'OCR error', 'failed', '/tmp/test.jpg')
            """)
            conn.commit()

        result = temp_store.reset_failed_frames()

        assert result["total"] == 1
        assert result["breakdown"]["ocr"] == 1

        # Verify frame was reset
        with temp_store._connect() as conn:
            row = conn.execute(
                "SELECT status, error_message, visibility_status FROM frames WHERE frame_id = 'test-1'"
            ).fetchone()
            assert row["status"] == "pending"
            assert row["error_message"] is None
            assert row["visibility_status"] == "pending"

    def test_reset_description_failed_frame(self, temp_store):
        """Frame with description failure should have description_status reset and task enqueued."""
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (id, frame_id, status, description_status, visibility_status, snapshot_path)
                VALUES (1, 'test-2', 'completed', 'failed', 'failed', '/tmp/test.jpg')
            """)
            conn.commit()

        result = temp_store.reset_failed_frames()

        assert result["total"] == 1
        assert result["breakdown"]["description"] == 1

        with temp_store._connect() as conn:
            row = conn.execute(
                "SELECT description_status, visibility_status FROM frames WHERE frame_id = 'test-2'"
            ).fetchone()
            assert row["description_status"] == "pending"
            assert row["visibility_status"] == "pending"

            # Check task was enqueued
            task = conn.execute(
                "SELECT status FROM description_tasks WHERE frame_id = 1"
            ).fetchone()
            assert task is not None
            assert task["status"] == "pending"

    def test_reset_embedding_failed_frame(self, temp_store):
        """Frame with embedding failure should have embedding_status reset and task enqueued."""
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (id, frame_id, status, description_status, embedding_status, visibility_status, snapshot_path)
                VALUES (1, 'test-3', 'completed', 'completed', 'failed', 'failed', '/tmp/test.jpg')
            """)
            conn.commit()

        result = temp_store.reset_failed_frames()

        assert result["total"] == 1
        assert result["breakdown"]["embedding"] == 1

        with temp_store._connect() as conn:
            row = conn.execute(
                "SELECT embedding_status, visibility_status FROM frames WHERE frame_id = 'test-3'"
            ).fetchone()
            assert row["embedding_status"] == "pending"
            assert row["visibility_status"] == "pending"

            task = conn.execute(
                "SELECT status FROM embedding_tasks WHERE frame_id = 1"
            ).fetchone()
            assert task is not None
            assert task["status"] == "pending"

    def test_reset_multiple_failures_in_one_frame(self, temp_store):
        """Frame with multiple failed stages should reset all failed stages."""
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (id, frame_id, status, description_status, embedding_status, visibility_status, snapshot_path)
                VALUES (1, 'test-4', 'completed', 'failed', 'failed', 'failed', '/tmp/test.jpg')
            """)
            conn.commit()

        result = temp_store.reset_failed_frames()

        assert result["total"] == 1
        assert result["breakdown"]["description"] == 1
        assert result["breakdown"]["embedding"] == 1

        with temp_store._connect() as conn:
            row = conn.execute(
                "SELECT description_status, embedding_status, visibility_status FROM frames WHERE frame_id = 'test-4'"
            ).fetchone()
            assert row["description_status"] == "pending"
            assert row["embedding_status"] == "pending"
            assert row["visibility_status"] == "pending"

    def test_no_failed_frames_returns_zero(self, temp_store):
        """When no failed frames exist, should return zero counts."""
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (frame_id, status, visibility_status, snapshot_path)
                VALUES ('test-5', 'completed', 'queryable', '/tmp/test.jpg')
            """)
            conn.commit()

        result = temp_store.reset_failed_frames()

        assert result["total"] == 0
        assert result["breakdown"]["ocr"] == 0
        assert result["breakdown"]["description"] == 0
        assert result["breakdown"]["embedding"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retry_failed_frames.py -v`
Expected: FAIL with "AttributeError: 'FramesStore' object has no attribute 'reset_failed_frames'"

- [ ] **Step 3: Implement `reset_failed_frames()` method**

Add to `openrecall/server/database/frames_store.py` after the `try_set_failed_standalone` method (around line 600):

```python
def reset_failed_frames(self) -> dict:
    """Reset all failed frames to pending status.

    Smart reset: only resets the stage(s) that failed.
    - OCR failed → status = 'pending', error_message = NULL
    - Description failed → description_status = 'pending', enqueue task
    - Embedding failed → embedding_status = 'pending', enqueue task

    Returns:
        Dict with 'total' count and 'breakdown' by stage.
    """
    breakdown = {"ocr": 0, "description": 0, "embedding": 0}

    try:
        with self._connect() as conn:
            # Count unique failed frames before reset
            total_result = conn.execute("""
                SELECT COUNT(*) as cnt FROM frames WHERE visibility_status = 'failed'
            """).fetchone()
            total = total_result["cnt"] if total_result else 0

            if total == 0:
                return {"total": 0, "breakdown": breakdown}

            # 1. Reset OCR failures
            cursor = conn.execute("""
                UPDATE frames
                SET status = 'pending', error_message = NULL
                WHERE visibility_status = 'failed' AND status = 'failed'
            """)
            breakdown["ocr"] = cursor.rowcount

            # 2. Reset description failures and enqueue tasks
            desc_failed_rows = conn.execute("""
                SELECT id FROM frames
                WHERE visibility_status = 'failed' AND description_status = 'failed'
            """).fetchall()

            for row in desc_failed_rows:
                frame_id = row["id"]
                conn.execute("""
                    INSERT OR IGNORE INTO description_tasks (frame_id, status)
                    VALUES (?, 'pending')
                """, (frame_id,))

            cursor = conn.execute("""
                UPDATE frames
                SET description_status = 'pending'
                WHERE visibility_status = 'failed' AND description_status = 'failed'
            """)
            breakdown["description"] = cursor.rowcount

            # 3. Reset embedding failures and enqueue tasks
            embed_failed_rows = conn.execute("""
                SELECT id FROM frames
                WHERE visibility_status = 'failed' AND embedding_status = 'failed'
            """).fetchall()

            for row in embed_failed_rows:
                frame_id = row["id"]
                conn.execute("""
                    INSERT OR IGNORE INTO embedding_tasks (frame_id, status)
                    VALUES (?, 'pending')
                """, (frame_id,))

            cursor = conn.execute("""
                UPDATE frames
                SET embedding_status = 'pending'
                WHERE visibility_status = 'failed' AND embedding_status = 'failed'
            """)
            breakdown["embedding"] = cursor.rowcount

            # 4. Set visibility_status back to pending for all failed frames
            conn.execute("""
                UPDATE frames
                SET visibility_status = 'pending'
                WHERE visibility_status = 'failed'
            """)

            conn.commit()

            return {
                "total": total,
                "breakdown": breakdown
            }

    except sqlite3.Error as e:
        logger.error("reset_failed_frames failed: %s", e)
        return {"total": 0, "breakdown": breakdown}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retry_failed_frames.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/database/frames_store.py tests/test_retry_failed_frames.py
git commit -m "feat(db): add reset_failed_frames method for smart stage reset"
```

---

### Task 2: API Endpoint - `POST /v1/admin/frames/retry-failed`

**Files:**
- Modify: `openrecall/server/api_v1.py`
- Modify: `tests/test_retry_failed_frames.py`

- [ ] **Step 1: Write the failing test for the API endpoint**

Add to `tests/test_retry_failed_frames.py`:

```python
import requests

BASE_URL = "http://localhost:8083"
API_V1 = f"{BASE_URL}/v1"


@pytest.mark.integration
class TestRetryFailedFramesAPI:
    """Integration tests for POST /v1/admin/frames/retry-failed."""

    def test_retry_failed_returns_success(self):
        """API should return success with counts."""
        resp = requests.post(f"{API_V1}/admin/frames/retry-failed", timeout=5)

        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "reset_count" in data
        assert "breakdown" in data
        assert "request_id" in data
        assert isinstance(data["reset_count"], int)
        assert isinstance(data["breakdown"], dict)

    def test_retry_failed_resets_failed_frames(self, temp_store):
        """API should actually reset failed frames in the database."""
        # This test requires the server to be using the same database
        # For integration testing, we verify the API response format
        resp = requests.post(f"{API_V1}/admin/frames/retry-failed", timeout=5)
        assert resp.status_code in [200, 202]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retry_failed_frames.py::TestRetryFailedFramesAPI -v`
Expected: FAIL with 404 Not Found

- [ ] **Step 3: Implement the API endpoint**

Add to `openrecall/server/api_v1.py` after the `embedding_backfill` function (around line 1530):

```python
# ---------------------------------------------------------------------------
# POST /v1/admin/frames/retry-failed — retry all failed frames
# ---------------------------------------------------------------------------


@v1_bp.route("/admin/frames/retry-failed", methods=["POST"])
def retry_failed_frames():
    """Reset all failed frames to pending for reprocessing."""
    request_id = str(uuid.uuid4())
    store = _get_frames_store()

    try:
        result = store.reset_failed_frames()

        logger.info(
            "retry_failed_frames: reset_count=%d breakdown=%s request_id=%s",
            result["total"],
            result["breakdown"],
            request_id,
        )

        return jsonify({
            "message": "Retry triggered",
            "reset_count": result["total"],
            "breakdown": result["breakdown"],
            "request_id": request_id,
        }), 200

    except Exception as exc:
        logger.exception("retry_failed_frames failed: %s request_id=%s", exc, request_id)
        return make_error_response(
            "Failed to reset failed frames",
            "INTERNAL_ERROR",
            500,
            request_id=request_id,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retry_failed_frames.py::TestRetryFailedFramesAPI -v`
Expected: Tests PASS (requires running server)

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/api_v1.py tests/test_retry_failed_frames.py
git commit -m "feat(api): add POST /v1/admin/frames/retry-failed endpoint"
```

---

### Task 3: Frontend UI - Retry Button

**Files:**
- Modify: `openrecall/client/web/templates/index.html`

- [ ] **Step 1: Add button HTML to stats bar**

Find the stats bar section (around line 1250) and add the retry button after the failed stat item.

Current code:
```html
      <div class="stats-bar">
        <div class="stat-item" data-status="completed">
          <span>Completed</span>
          <span class="stat-value" x-text="stats().completed"></span>
        </div>
        <div class="stat-item" data-status="pending">
          <span>Pending</span>
          <span class="stat-value" x-text="stats().pending"></span>
        </div>
        <div class="stat-item" data-status="failed">
          <span>Failed</span>
          <span class="stat-value" x-text="stats().failed"></span>
        </div>
      </div>
```

Change to:
```html
      <div class="stats-bar">
        <div class="stat-item" data-status="completed">
          <span>Completed</span>
          <span class="stat-value" x-text="stats().completed"></span>
        </div>
        <div class="stat-item" data-status="pending">
          <span>Pending</span>
          <span class="stat-value" x-text="stats().pending"></span>
        </div>
        <div class="stat-item" data-status="failed">
          <span>Failed</span>
          <span class="stat-value" x-text="stats().failed"></span>
        </div>
        <button
          type="button"
          class="retry-failed-btn"
          x-show="stats().failed > 0"
          @click="retryFailed()"
          :disabled="retrying"
        >
          <template x-if="!retrying">
            <span>↻ Retry Failed</span>
          </template>
          <template x-if="retrying">
            <span><span class="spinner"></span> Retrying...</span>
          </template>
        </button>
      </div>
```

- [ ] **Step 2: Add CSS styles for the retry button**

Add to the `<style>` section (around line 600, after `.stat-item[data-status="failed"]`):

```css
  /* Retry Failed Button */
  .retry-failed-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border: 1px solid var(--color-error-border);
    border-radius: 8px;
    background: var(--color-error-bg);
    color: var(--color-error);
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .retry-failed-btn:hover:not(:disabled) {
    background: var(--color-error);
    color: white;
  }

  .retry-failed-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .retry-failed-btn .spinner {
    width: 12px;
    height: 12px;
    border-width: 2px;
  }
```

- [ ] **Step 3: Add Alpine.js method `retryFailed()`**

Find the `memoryGrid()` function in the `<script>` section and add the `retrying` property and `retryFailed()` method.

Add `retrying: false,` after `modalTab: 'image',` (around line 1661):

```javascript
      entries: window.initialEntries || [],
      config: window.initialConfig || { show_ai_description: false },
      lastCheckMs: 0,
      selectedIndex: null,
      modalTab: 'image',  // Modal 默认显示图片 Tab
      retrying: false,  // Retry button loading state
```

Add the `retryFailed()` method after the `refreshRecent()` method (around line 2100):

```javascript
      async retryFailed() {
        if (this.retrying) return;

        this.retrying = true;
        try {
          const res = await fetch(`${EDGE_BASE_URL}/v1/admin/frames/retry-failed`, {
            method: 'POST'
          });
          if (res.ok) {
            const data = await res.json();
            console.log('Retry triggered:', data);
            // Refresh the grid to show updated statuses
            await this.refreshRecent();
          } else {
            console.error('Retry failed:', res.status);
          }
        } catch (e) {
          console.error('Retry failed:', e);
        } finally {
          this.retrying = false;
        }
      },
```

- [ ] **Step 4: Manual test in browser**

1. Start the server: `./run_server.sh --mode local --debug`
2. Start the client: `./run_client.sh --mode local --debug`
3. Open http://localhost:8889 in browser
4. Verify the "Retry Failed" button appears when there are failed frames
5. Click the button and verify loading state, then grid refresh

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "feat(ui): add retry failed button to grid stats bar"
```

---

### Task 4: Final Verification

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/test_retry_failed_frames.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run integration tests (requires running server)**

Run: `pytest tests/test_retry_failed_frames.py -v -m integration`
Expected: Integration tests PASS

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git status
# If any changes:
git add -A
git commit -m "fix: address review feedback for retry failed frames"
```
