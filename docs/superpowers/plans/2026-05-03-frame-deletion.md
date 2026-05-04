# Frame Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a delete button to Grid and Timeline views that permanently removes a frame and all associated data.

**Architecture:** Hard delete through a single SQLite transaction (frames + all child tables), with FTS5 auto-cleanup via trigger. LanceDB embedding and disk JPEG cleanup run post-transaction. UI uses a confirmation modal with toast feedback.

**Tech Stack:** Python (Flask, SQLite), Alpine.js, Jinja2 templates

> **Line numbers:** All line numbers referenced in this plan are approximate and based on the codebase state at plan-writing time. Implementers should use the actual line numbers from the current files.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `openrecall/server/database/frames_store.py` | `delete_frame()` — SQLite transaction with all child table deletions |
| `openrecall/server/api_v1.py` | `DELETE /v1/frames/<frame_id>` route |
| `openrecall/client/web/templates/index.html` | Grid card hover-delete button, confirm dialog, post-delete logic |
| `openrecall/client/web/templates/timeline.html` | Timeline image delete button, confirm dialog, post-delete logic |
| `tests/test_p1_s1_frames.py` | Unit tests for `delete_frame()` and integration tests for DELETE endpoint |

---

## Task 1: Add `delete_frame()` to FramesStore

**Files:**
- Modify: `openrecall/server/database/frames_store.py`
- Test: `tests/test_p1_s1_frames.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_p1_s1_frames.py`, after the existing `test_query_by_local_timestamp` test (around line 178):

```python
def test_delete_frame_removes_all_data(test_store):
    """Verify delete_frame removes frame and all associated child rows."""
    # Create a frame
    metadata = {
        "timestamp": "2026-04-25T20:00:00.000Z",
        "app_name": "TestApp",
        "capture_trigger": "idle",
    }
    frame_id, is_new = test_store.claim_frame(
        capture_id="test-delete-frame",
        metadata=metadata,
    )
    assert is_new is True

    # Finalize with a fake snapshot path
    test_store.finalize_claimed_frame(
        frame_id=frame_id,
        capture_id="test-delete-frame",
        snapshot_path="/fake/path/test.jpg",
    )

    # Insert child rows manually to verify cascade cleanup
    with test_store._connect() as conn:
        conn.execute(
            "INSERT INTO ocr_text (frame_id, text, text_length, ocr_engine) VALUES (?, 'hello', 5, 'test')",
            (frame_id,),
        )
        conn.execute(
            "INSERT INTO accessibility (frame_id, timestamp, app_name, window_name, text_content, text_length) VALUES (?, ?, 'App', 'Win', 'text', 4)",
            (frame_id, "2026-04-25T20:00:00.000Z"),
        )
        conn.execute(
            "INSERT INTO elements (frame_id, source, role, text, depth, sort_order) VALUES (?, 'accessibility', 'button', 'Click', 0, 0)",
            (frame_id,),
        )
        conn.execute(
            "INSERT INTO frame_descriptions (frame_id, narrative, summary, tags_json) VALUES (?, 'narrative', 'summary', '[]')",
            (frame_id,),
        )
        conn.execute(
            "INSERT INTO description_tasks (frame_id, status) VALUES (?, 'completed')",
            (frame_id,),
        )
        conn.execute(
            "INSERT INTO embedding_tasks (frame_id, status) VALUES (?, 'completed')",
            (frame_id,),
        )
        conn.commit()

    # Delete the frame
    success, snapshot_path = test_store.delete_frame(frame_id)
    assert success is True
    assert snapshot_path == "/fake/path/test.jpg"

    # Verify frame and all associated rows are gone (query DB directly)
    with test_store._connect() as conn:
        assert conn.execute("SELECT 1 FROM frames WHERE id = ?", (frame_id,)).fetchone() is None
        assert conn.execute("SELECT 1 FROM ocr_text WHERE frame_id = ?", (frame_id,)).fetchone() is None
        assert conn.execute("SELECT 1 FROM accessibility WHERE frame_id = ?", (frame_id,)).fetchone() is None
        assert conn.execute("SELECT 1 FROM elements WHERE frame_id = ?", (frame_id,)).fetchone() is None
        assert conn.execute("SELECT 1 FROM frame_descriptions WHERE frame_id = ?", (frame_id,)).fetchone() is None
        assert conn.execute("SELECT 1 FROM description_tasks WHERE frame_id = ?", (frame_id,)).fetchone() is None
        assert conn.execute("SELECT 1 FROM embedding_tasks WHERE frame_id = ?", (frame_id,)).fetchone() is None
        # Verify FTS5 is also cleaned (trigger should handle this)
        assert conn.execute("SELECT 1 FROM frames_fts WHERE id = ?", (frame_id,)).fetchone() is None


def test_delete_frame_nonexistent_returns_false(test_store):
    """Verify delete_frame returns False for non-existent frame."""
    success, snapshot_path = test_store.delete_frame(999999)
    assert success is False
    assert snapshot_path is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_p1_s1_frames.py::test_delete_frame_removes_all_data -v
```

Expected: FAIL with `AttributeError: 'FramesStore' object has no attribute 'delete_frame'`

- [ ] **Step 3: Write minimal implementation**

Add `delete_frame()` method to `FramesStore` class in `openrecall/server/database/frames_store.py`. Place it after `delete_unfinalized_claim()` (around line 344):

```python
    def delete_frame(self, frame_id: int) -> tuple[bool, Optional[str]]:
        """Delete a frame and all associated data.

        Deletes the frame row from `frames` plus all child rows in:
        ocr_text, accessibility, elements, frame_descriptions,
        description_tasks, embedding_tasks. The frames_fts virtual
        table is cleaned automatically by the frames_ad trigger.

        LanceDB embedding and disk JPEG cleanup are the caller's
        responsibility (they run outside the SQLite transaction).

        Args:
            frame_id: The frame ID to delete.

        Returns:
            (success, snapshot_path_or_none)
            snapshot_path is returned so the caller can delete the
            JPEG file from disk. None if frame not found.
        """
        try:
            with self._connect() as conn:
                # Read snapshot_path before deleting
                row = conn.execute(
                    "SELECT snapshot_path FROM frames WHERE id = ?",
                    (frame_id,),
                ).fetchone()
                if row is None:
                    return False, None
                snapshot_path = row["snapshot_path"]

                # Delete child tables first (SQLite foreign keys not enforced)
                conn.execute("DELETE FROM ocr_text WHERE frame_id = ?", (frame_id,))
                conn.execute("DELETE FROM accessibility WHERE frame_id = ?", (frame_id,))
                conn.execute("DELETE FROM elements WHERE frame_id = ?", (frame_id,))
                conn.execute("DELETE FROM frame_descriptions WHERE frame_id = ?", (frame_id,))
                conn.execute("DELETE FROM description_tasks WHERE frame_id = ?", (frame_id,))
                conn.execute("DELETE FROM embedding_tasks WHERE frame_id = ?", (frame_id,))

                # Delete the frame (frames_fts trigger handles FTS cleanup)
                conn.execute("DELETE FROM frames WHERE id = ?", (frame_id,))
                conn.commit()

                logger.info("delete_frame: frame_id=%d deleted", frame_id)
                return True, snapshot_path

        except sqlite3.Error as e:
            logger.error("delete_frame failed frame_id=%d: %s", frame_id, e)
            raise
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_p1_s1_frames.py::test_delete_frame_removes_all_data tests/test_p1_s1_frames.py::test_delete_frame_nonexistent_returns_false -v
```

Expected: PASS on both tests.

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/database/frames_store.py tests/test_p1_s1_frames.py
git commit -m "$(cat <<'EOF'
feat(frames): add delete_frame() to FramesStore

Hard delete of a frame and all child rows in a single transaction.
Returns snapshot_path for caller to clean up disk file.
FTS5 auto-cleaned via frames_ad trigger.
EOF
)"
```

---

## Task 2: Add DELETE /v1/frames/<frame_id> API Endpoint

**Files:**
- Modify: `openrecall/server/api_v1.py`
- Test: `tests/test_p1_s1_frames.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_p1_s1_frames.py`, after the `TestFrameReading` class (around line 149):

```python
class TestFrameDeletion:
    """Integration tests for DELETE /v1/frames/:frame_id."""

    @pytest.mark.integration
    def test_delete_frame_success(self):
        """Verify DELETE /v1/frames/:frame_id removes a frame."""
        conn = sqlite3.connect(str(settings.db_path))
        cursor = conn.execute(
            "SELECT id FROM frames WHERE snapshot_path IS NOT NULL LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            pytest.skip("No existing frames to test deletion")

        frame_id = row[0]

        resp = requests.delete(f"{API_V1}/frames/{frame_id}", timeout=5)
        assert resp.status_code == 200

        data = resp.json()
        assert data["deleted"] is True
        assert data["frame_id"] == frame_id
        assert "request_id" in data

        # Verify frame is gone
        conn = sqlite3.connect(str(settings.db_path))
        cursor = conn.execute("SELECT 1 FROM frames WHERE id = ?", (frame_id,))
        assert cursor.fetchone() is None
        conn.close()

    @pytest.mark.integration
    def test_delete_nonexistent_frame_returns_404(self):
        """Verify DELETE for non-existent frame returns 404."""
        resp = requests.delete(f"{API_V1}/frames/999999999", timeout=5)
        assert resp.status_code == 404

        data = resp.json()
        assert data["code"] == "NOT_FOUND"
```

- [ ] **Step 2: Run test to verify it fails**

First, make sure the Edge server is running:
```bash
./run_server.sh --mode local --debug
```

Then run:
```bash
pytest tests/test_p1_s1_frames.py::TestFrameDeletion::test_delete_frame_success -v
```

Expected: FAIL with 405 (Method Not Allowed) because DELETE route does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add the DELETE route to `openrecall/server/api_v1.py`. Place it immediately after the `get_frame()` route (after line 706, before the `get_frame_context` comment block):

```python

# ---------------------------------------------------------------------------
# DELETE /v1/frames/<frame_id>
# ---------------------------------------------------------------------------


@v1_bp.route("/frames/<int:frame_id>", methods=["DELETE"])
def delete_frame(frame_id: int):
    """Permanently delete a frame and all associated data.

    Returns:
        200 JSON       — {"deleted": true, "frame_id": ..., "request_id": ...}
        404 NOT_FOUND  — Frame not found
        500 INTERNAL_ERROR — SQLite transaction failure
    """
    request_id = str(uuid.uuid4())
    store = _get_frames_store()

    try:
        success, snapshot_path = store.delete_frame(frame_id)
    except sqlite3.Error as exc:
        logger.exception("delete_frame: DB error frame_id=%d: %s", frame_id, exc)
        return make_error_response(
            "Failed to delete frame",
            "INTERNAL_ERROR",
            500,
            request_id=request_id,
        )

    if not success:
        return make_error_response(
            "frame not found",
            "NOT_FOUND",
            404,
            request_id=request_id,
        )

    # Post-transaction: delete LanceDB embedding (non-blocking)
    try:
        from openrecall.server.database.embedding_store import EmbeddingStore
        embedding_store = EmbeddingStore()
        embedding_store.delete_by_frame_id(frame_id)
    except Exception as exc:
        logger.warning(
            "delete_frame: LanceDB cleanup failed frame_id=%d: %s",
            frame_id,
            exc,
        )

    # Post-transaction: delete disk JPEG (non-blocking)
    if snapshot_path:
        try:
            path = Path(snapshot_path)
            if path.exists():
                path.unlink()
                logger.debug(
                    "delete_frame: removed snapshot frame_id=%d path=%s",
                    frame_id,
                    snapshot_path,
                )
        except OSError as exc:
            logger.warning(
                "delete_frame: disk cleanup failed frame_id=%d path=%s: %s",
                frame_id,
                snapshot_path,
                exc,
            )

    logger.info(
        "delete_frame: 200 OK frame_id=%d request_id=%s",
        frame_id,
        request_id,
    )
    return jsonify({
        "deleted": True,
        "frame_id": frame_id,
        "request_id": request_id,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Make sure the Edge server is running, then run:
```bash
pytest tests/test_p1_s1_frames.py::TestFrameDeletion -v
```

Expected: PASS on both tests.

**Note:** `test_delete_frame_success` actually deletes a real frame from the DB. After running it, that frame is gone. This is expected for integration tests.

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/api_v1.py tests/test_p1_s1_frames.py
git commit -m "$(cat <<'EOF'
feat(api): add DELETE /v1/frames/<frame_id> endpoint

Permanently removes frame, child rows (transaction), LanceDB embedding,
and disk JPEG (post-transaction, non-blocking).
EOF
)"
```

---

## Task 3: Grid Delete Button (index.html)

**Files:**
- Modify: `openrecall/client/web/templates/index.html`

- [ ] **Step 1: Add delete button styles**

Add the following CSS inside the existing `<style>` block in `index.html`, after the `.card-image-wrapper` rule (around line 417):

```css
  /* Delete button on card image */
  .card-image-wrapper .delete-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    border: none;
    background: rgba(0, 0, 0, 0.4);
    color: white;
    font-size: 16px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: all 0.2s ease;
    z-index: 10;
    padding: 0;
    line-height: 1;
  }

  .card-image-wrapper:hover .delete-btn {
    opacity: 1;
  }

  .card-image-wrapper .delete-btn:hover {
    background: #FF3B30;
    transform: scale(1.1);
  }
```

- [ ] **Step 2: Add confirm dialog and toast styles**

Add at the end of the `<style>` block, before the closing `</style>` tag (around line 1516):

```css
  /* Delete confirm dialog */
  .delete-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0, 0, 0, 0.5);
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .delete-dialog {
    width: 360px;
    background: var(--bg-card);
    border-radius: 16px;
    padding: 32px 28px;
    text-align: center;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  }

  .delete-dialog-icon {
    font-size: 40px;
    margin-bottom: 16px;
  }

  .delete-dialog h3 {
    margin: 0 0 8px 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .delete-dialog p {
    margin: 0 0 24px 0;
    font-size: 14px;
    color: var(--text-secondary);
    line-height: 1.5;
  }

  .delete-dialog-actions {
    display: flex;
    gap: 12px;
    justify-content: center;
  }

  .btn-cancel {
    padding: 10px 20px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-card);
    color: var(--text-primary);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    font-family: var(--font-stack);
  }

  .btn-cancel:hover {
    background: var(--bg-body);
  }

  .btn-delete-confirm {
    padding: 10px 20px;
    border: none;
    border-radius: 8px;
    background: #FF3B30;
    color: white;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    font-family: var(--font-stack);
    min-width: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }

  .btn-delete-confirm:hover:not(:disabled) {
    background: #E6352B;
  }

  .btn-delete-confirm:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* Toast notification */
  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    padding: 12px 20px;
    background: #333;
    color: white;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    z-index: 3000;
    animation: toastIn 0.3s ease-out;
  }

  .toast.toast-out {
    animation: toastOut 0.3s ease-in forwards;
  }

  @keyframes toastIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @keyframes toastOut {
    from { opacity: 1; transform: translateY(0); }
    to { opacity: 0; transform: translateY(20px); }
  }
```

- [ ] **Step 3: Add delete button to each card**

Find the card image wrapper in the template (around line 1677):

```html
            <div class="card-image-wrapper">
              <img
                :src="imageSrc(entry)"
                alt="Screenshot"
                class="card-image"
                :loading="i < 8 ? 'eager' : 'lazy'"
                decoding="async"
                :fetchpriority="i < 2 ? 'high' : 'auto'"
                @click="openAt(i)"
              >
            </div>
```

Replace with:

```html
            <div class="card-image-wrapper">
              <button
                type="button"
                class="delete-btn"
                title="Delete frame"
                @click.stop="promptDelete(entry, i)"
              >🗑️</button>
              <img
                :src="imageSrc(entry)"
                alt="Screenshot"
                class="card-image"
                :loading="i < 8 ? 'eager' : 'lazy'"
                decoding="async"
                :fetchpriority="i < 2 ? 'high' : 'auto'"
                @click="openAt(i)"
              >
            </div>
```

- [ ] **Step 4: Add confirm dialog HTML**

Add the confirm dialog and toast markup at the end of the main `div` (after the empty-state template, around line 2017), before the closing `</div>`:

```html
  <!-- Delete Confirm Dialog -->
  <div
    x-show="deleteConfirmOpen"
    class="delete-overlay"
    @click.self="deleteConfirmOpen = false"
    @keydown.escape.window="deleteConfirmOpen = false"
    x-cloak
  >
    <div class="delete-dialog">
      <div class="delete-dialog-icon">🗑️</div>
      <h3>Delete this frame?</h3>
      <p>This will permanently remove the screenshot, OCR text, description, and search index.</p>
      <div class="delete-dialog-actions">
        <button type="button" class="btn-cancel" @click="deleteConfirmOpen = false">Cancel</button>
        <button
          type="button"
          class="btn-delete-confirm"
          @click="confirmDelete()"
          :disabled="deleting"
        >
          <template x-if="!deleting">
            <span>Delete</span>
          </template>
          <template x-if="deleting">
            <span><span class="spinner" style="width: 12px; height: 12px; border-width: 2px;"></span> Deleting...</span>
          </template>
        </button>
      </div>
    </div>
  </div>

  <!-- Toast -->
  <div x-show="toastMessage" x-text="toastMessage" class="toast" :class="{ 'toast-out': toastFading }" x-cloak></div>
```

- [ ] **Step 5: Add Alpine.js state and methods**

Add to the `memoryGrid()` return object (around line 2023), after `loading: false,`:

```javascript
      deleteConfirmOpen: false,
      frameToDelete: null,
      frameToDeleteIndex: null,
      deleting: false,
      toastMessage: '',
      toastFading: false,
```

Add the following methods to `memoryGrid()`, before `syncLastCheckFromEntries()`:

```javascript
      // ---- Frame Deletion ----

      promptDelete(entry, index) {
        this.frameToDelete = entry;
        this.frameToDeleteIndex = index;
        this.deleteConfirmOpen = true;
      },

      async confirmDelete() {
        if (!this.frameToDelete) return;
        const entry = this.frameToDelete;
        const index = this.frameToDeleteIndex;

        this.deleting = true;
        try {
          const res = await fetch(`${EDGE_BASE_URL}/v1/frames/${entry.frame_id}`, {
            method: 'DELETE'
          });

          if (res.ok) {
            // Remove from entries array
            this.entries.splice(index, 1);

            // Adjust modal selection if needed
            if (this.selectedIndex !== null) {
              if (this.entries.length === 0) {
                this.selectedIndex = null;
              } else if (this.selectedIndex === index) {
                // splice slid next element into this index; keep it unless
                // we deleted the last item, in which case wrap to first
                if (this.selectedIndex >= this.entries.length) {
                  this.selectedIndex = 0;
                }
                // Reuse openAt to handle description tab refresh
                this.openAt(this.selectedIndex);
              } else if (this.selectedIndex > index) {
                this.selectedIndex -= 1;
              }
            }

            this.showToast('Frame deleted');
          } else {
            const data = await res.json().catch(() => ({}));
            this.showToast(data.error || 'Failed to delete frame');
          }
        } catch (e) {
          console.error('Delete failed:', e);
          this.showToast('Network error, please try again');
        } finally {
          this.deleting = false;
          this.deleteConfirmOpen = false;
          this.frameToDelete = null;
          this.frameToDeleteIndex = null;
        }
      },

      showToast(message) {
        this.toastMessage = message;
        this.toastFading = false;
        setTimeout(() => {
          this.toastFading = true;
          setTimeout(() => {
            this.toastMessage = '';
            this.toastFading = false;
          }, 300);
        }, 2000);
      },
```

- [ ] **Step 6: Verify UI by running client and checking Grid**

Start the Edge server:
```bash
./run_server.sh --mode local --debug
```

Start the client:
```bash
./run_client.sh --mode local --debug
```

Open http://localhost:8889 and verify:
- Hovering over a card image shows a 🗑️ button in the top-right
- Clicking the button opens a confirm dialog
- Cancel closes the dialog without deleting
- Delete removes the card from the grid and shows "Frame deleted" toast

- [ ] **Step 7: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "$(cat <<'EOF'
feat(ui/grid): add delete button to memory cards

Hover-activated delete button on card images with confirm dialog
and toast notification. Deletes via DELETE /v1/frames/:id.
EOF
)"
```

---

## Task 4: Timeline Delete Button (timeline.html)

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html`

- [ ] **Step 1: Add delete button styles**

Add the following CSS inside the existing `<style>` block in `timeline.html`, after the `.frame-counter` rule (around line 405):

```css
  /* Delete button on timeline image */
  .image-container {
    position: relative;
  }

  .image-container .delete-btn {
    position: absolute;
    top: 12px;
    right: 12px;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    border: none;
    background: rgba(0, 0, 0, 0.4);
    color: white;
    font-size: 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    z-index: 10;
    padding: 0;
    line-height: 1;
  }

  .image-container .delete-btn:hover {
    background: #FF3B30;
    transform: scale(1.1);
  }

  /* Delete confirm dialog (same styles as grid) */
  .delete-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0, 0, 0, 0.5);
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .delete-dialog {
    width: 360px;
    background: var(--bg-card);
    border-radius: 16px;
    padding: 32px 28px;
    text-align: center;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  }

  .delete-dialog-icon {
    font-size: 40px;
    margin-bottom: 16px;
  }

  .delete-dialog h3 {
    margin: 0 0 8px 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .delete-dialog p {
    margin: 0 0 24px 0;
    font-size: 14px;
    color: var(--text-secondary);
    line-height: 1.5;
  }

  .delete-dialog-actions {
    display: flex;
    gap: 12px;
    justify-content: center;
  }

  .btn-cancel {
    padding: 10px 20px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-card);
    color: var(--text-primary);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    font-family: var(--font-stack);
  }

  .btn-cancel:hover {
    background: var(--bg-body);
  }

  .btn-delete-confirm {
    padding: 10px 20px;
    border: none;
    border-radius: 8px;
    background: #FF3B30;
    color: white;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    font-family: var(--font-stack);
    min-width: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }

  .btn-delete-confirm:hover:not(:disabled) {
    background: #E6352B;
  }

  .btn-delete-confirm:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* Toast notification */
  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    padding: 12px 20px;
    background: #333;
    color: white;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    z-index: 3000;
    animation: toastIn 0.3s ease-out;
  }

  .toast.toast-out {
    animation: toastOut 0.3s ease-in forwards;
  }

  @keyframes toastIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @keyframes toastOut {
    from { opacity: 1; transform: translateY(0); }
    to { opacity: 0; transform: translateY(20px); }
  }
```

- [ ] **Step 2: Add delete button to image container**

Find the image container in the template (around line 541):

```html
    <div class="image-container">
      <img id="timestampImage"
        :src="currentFrame ? `${EDGE_BASE_URL}/v1/frames/${currentFrame.frame_id}` : ''"
        alt="Screenshot">
    </div>
```

Replace with:

```html
    <div class="image-container">
      <button
        type="button"
        class="delete-btn"
        title="Delete frame"
        @click.stop="promptDelete()"
        x-show="currentFrame"
      >🗑️</button>
      <img id="timestampImage"
        :src="currentFrame ? `${EDGE_BASE_URL}/v1/frames/${currentFrame.frame_id}` : ''"
        alt="Screenshot">
    </div>
```

- [ ] **Step 3: Add confirm dialog and toast HTML**

Add at the end of the main `div`, before the closing `</div>` (after line 547):

```html

  <!-- Delete Confirm Dialog -->
  <div
    x-show="deleteConfirmOpen"
    class="delete-overlay"
    @click.self="deleteConfirmOpen = false"
    @keydown.escape.window="deleteConfirmOpen = false"
    x-cloak
  >
    <div class="delete-dialog">
      <div class="delete-dialog-icon">🗑️</div>
      <h3>Delete this frame?</h3>
      <p>This will permanently remove the screenshot, OCR text, description, and search index.</p>
      <div class="delete-dialog-actions">
        <button type="button" class="btn-cancel" @click="deleteConfirmOpen = false">Cancel</button>
        <button
          type="button"
          class="btn-delete-confirm"
          @click="confirmDelete()"
          :disabled="deleting"
        >
          <template x-if="!deleting">
            <span>Delete</span>
          </template>
          <template x-if="deleting">
            <span><span class="spinner" style="width: 12px; height: 12px; border-width: 2px;"></span> Deleting...</span>
          </template>
        </button>
      </div>
    </div>
  </div>

  <!-- Toast -->
  <div x-show="toastMessage" x-text="toastMessage" class="toast" :class="{ 'toast-out': toastFading }" x-cloak></div>
```

- [ ] **Step 4: Add Alpine.js state and methods**

Add to the `timelineView()` return object, after `speedDropdownOpen: false,`:

```javascript
      deleteConfirmOpen: false,
      deleting: false,
      toastMessage: '',
      toastFading: false,
```

Add the following methods to `timelineView()`, before `formattedTime()` or other computed properties. Find where the methods are defined in the existing script and add these after `selectSpeed()`:

```javascript
      // ---- Frame Deletion ----

      promptDelete() {
        this.deleteConfirmOpen = true;
      },

      async confirmDelete() {
        if (!this.currentFrame) return;
        const frameId = this.currentFrame.frame_id;
        const index = this.currentIndex;

        this.deleting = true;
        try {
          const res = await fetch(`${EDGE_BASE_URL}/v1/frames/${frameId}`, {
            method: 'DELETE'
          });

          if (res.ok) {
            // Remove from frames array
            this.frames.splice(index, 1);

            // Adjust currentIndex
            if (this.frames.length === 0) {
              this.currentIndex = 0;
            } else if (index >= this.frames.length) {
              this.currentIndex = this.frames.length - 1;
            }
            // else: keep current index, next frame slides in

            this.showToast('Frame deleted');
          } else {
            const data = await res.json().catch(() => ({}));
            this.showToast(data.error || 'Failed to delete frame');
          }
        } catch (e) {
          console.error('Delete failed:', e);
          this.showToast('Network error, please try again');
        } finally {
          this.deleting = false;
          this.deleteConfirmOpen = false;
        }
      },

      showToast(message) {
        this.toastMessage = message;
        this.toastFading = false;
        setTimeout(() => {
          this.toastFading = true;
          setTimeout(() => {
            this.toastMessage = '';
            this.toastFading = false;
          }, 300);
        }, 2000);
      },
```

- [ ] **Step 5: Verify UI by checking Timeline page**

Open http://localhost:8889/timeline and verify:
- A 🗑️ button is visible in the top-right of the large image
- Clicking it opens the confirm dialog
- Deleting removes the frame and shows toast
- When the last frame is deleted, empty state appears

- [ ] **Step 6: Commit**

```bash
git add openrecall/client/web/templates/timeline.html
git commit -m "$(cat <<'EOF'
feat(ui/timeline): add delete button to timeline view

Always-visible delete button on the large image with confirm dialog
and toast notification. Adjusts slider and index on deletion.
EOF
)"
```

---

## Task 5: Run Full Test Suite

- [ ] **Step 1: Run FramesStore unit tests**

```bash
pytest tests/test_p1_s1_frames.py::test_delete_frame_removes_all_data tests/test_p1_s1_frames.py::test_delete_frame_nonexistent_returns_false -v
```

Expected: Both PASS.

- [ ] **Step 2: Run API integration tests**

Make sure Edge server is running on port 8083:
```bash
./run_server.sh --mode local --debug
```

```bash
pytest tests/test_p1_s1_frames.py::TestFrameDeletion -v
```

Expected: Both PASS.

- [ ] **Step 3: Run all existing tests to check for regressions**

```bash
pytest tests/test_p1_s1_frames.py -v
```

Expected: All PASS (or existing skips, no new failures).

- [ ] **Step 4: Commit (if any fixes needed)**

If no changes needed, skip. If fixes were made:

```bash
git add -A && git commit -m "fix: address review feedback from frame deletion tests"
```

---

## Plan Self-Review

### Spec Coverage Check

| Spec Section | Plan Task |
|-------------|-----------|
| Hard delete strategy | Task 1, Task 2 |
| Data cleanup scope (all tables) | Task 1 (FramesStore), Task 2 (API) |
| FTS5 auto-cleanup via trigger | Task 1 (mentioned in docstring, verified in test) |
| LanceDB + disk post-transaction | Task 2 (API endpoint) |
| DELETE /v1/frames/<frame_id> | Task 2 |
| Grid hover-delete button (C4) | Task 3 |
| Timeline always-visible delete button | Task 4 |
| Confirm dialog | Task 3, Task 4 |
| Post-delete UI feedback (splice, modal, toast) | Task 3, Task 4 |
| Error handling table | Task 2 (API), Task 3/4 (UI error paths) |
| Testing | Task 1, Task 2, Task 5 |

### Placeholder Scan

- No TBD/TODO/fill-in patterns found.
- All code blocks contain complete, runnable code.
- All test assertions are explicit.
- All commands have expected outputs.

### Type Consistency

- `delete_frame()` returns `tuple[bool, Optional[str]]` consistently in Task 1 and Task 2.
- API response shape matches: `{"deleted": true, "frame_id": ..., "request_id": ...}`.
- UI method names (`promptDelete`, `confirmDelete`, `showToast`) match across Task 3 and Task 4.
