# Frame Deletion Feature Design

## Overview

Add a delete button to the MyRecall web UI (Grid and Timeline views) that permanently removes a frame and all its associated data from the system.

## Strategy: Hard Delete

This is a privacy-first tool. When the user deletes a frame, it must be completely removed from all storage layers — database, search indexes, vector store, and disk.

No soft delete / recycle bin. Future extension to a two-phase delete (soft → hard) is possible without breaking changes, but is out of scope for this feature.

## Data Cleanup Scope

When a frame is deleted, the following must be cleaned up:

| Layer | Target | Method |
|-------|--------|--------|
| SQLite (transaction) | `frames` row | `DELETE FROM frames WHERE id = ?` |
| SQLite (transaction) | `ocr_text` row | `DELETE FROM ocr_text WHERE frame_id = ?` |
| SQLite (transaction) | `accessibility` row | `DELETE FROM accessibility WHERE frame_id = ?` |
| SQLite (transaction) | `elements` rows | `DELETE FROM elements WHERE frame_id = ?` |
| SQLite (transaction) | `frame_descriptions` row | `DELETE FROM frame_descriptions WHERE frame_id = ?` |
| SQLite (transaction) | `description_tasks` row | `DELETE FROM description_tasks WHERE frame_id = ?` |
| SQLite (transaction) | `embedding_tasks` row | `DELETE FROM embedding_tasks WHERE frame_id = ?` |
| SQLite (transaction) | `frames_fts` (FTS5) | Auto-cleaned via `content='frames'` + `content_rowid='id'` |
| LanceDB (post-transaction) | embedding vector | `EmbeddingStore.delete_by_frame_id(frame_id)` |
| Disk (post-transaction) | JPEG snapshot | `os.remove(snapshot_path)` |

**Transaction boundary**: All SQLite deletions happen in one transaction. LanceDB and disk cleanup run outside the transaction. If they fail, the API still returns 200 (data is gone from the primary store) but logs a warning.

## API

### `DELETE /v1/frames/<int:frame_id>`

**Request**: `DELETE /v1/frames/42`

**Success (200)**:
```json
{
  "deleted": true,
  "frame_id": 42,
  "request_id": "<uuid-v4>"
}
```

**Not Found (404)**:
```json
{
  "error": "frame not found",
  "code": "NOT_FOUND",
  "request_id": "<uuid-v4>"
}
```

**Internal Error (500)**: SQLite transaction failure.

**Implementation flow**:
1. Read frame to get `snapshot_path`
2. Begin SQLite transaction
3. Delete all associated rows (listed in table above)
4. Commit transaction
5. Delete LanceDB embedding (non-blocking, log warning on failure)
6. Delete JPEG file from disk (non-blocking, log warning on failure)

## FramesStore Method

```python
def delete_frame(self, frame_id: int) -> tuple[bool, Optional[str]]:
    """Delete a frame and all associated data.

    Returns:
        (success, snapshot_path_or_none)
        snapshot_path is returned for caller to delete from disk.
    """
```

## UI Design

### Grid View (index.html)

Delete button appears in the **top-right corner of the card image area** (C4 design). The button is semi-transparent by default and becomes fully visible on hover over the card image.

```
+-------------------------------+
| [header]                      |
+-------------------------------+
|                         [🗑️]  |
|      [screenshot]             |
|                               |
+-------------------------------+
| [footer status grid]          |
+-------------------------------+
```

**Button style**:
- 32x32px circular button
- Semi-transparent dark background (`rgba(0,0,0,0.4)`)
- White trash icon by default
- Red background (`#FF3B30`) + white icon on hover
- `title="Delete frame"` tooltip
- Hidden by default, visible on `.card-image-wrapper:hover`

**Hover behavior**: The button lives inside `.card-image-wrapper` which has `position: relative`. The button itself is `position: absolute; top: 8px; right: 8px;`.

### Timeline View (timeline.html)

Same style delete button, placed in the top-right corner of the large image container.

Unlike Grid, the Timeline delete button is **always visible** (not hover-dependent), because the user is actively viewing this single frame and the delete intent is unambiguous.

```
+-------------------------------+
|  [slider + controls]          |
+-------------------------------+
|                         [🗑️]  |
|      [large screenshot]       |
|                               |
+-------------------------------+
```

### Confirm Dialog

A centered modal overlay that appears when the delete button is clicked:

```
+-------------------------------+
|        [🗑️ icon]              |
|     Delete this frame?        |
|                               |
| This will permanently remove  |
| the screenshot, OCR text,     |
| description, and search index.|
|                               |
|  [Cancel]  [Delete]           |
+-------------------------------+
```

**Dialog style**:
- Overlay: `rgba(0,0,0,0.5)` background, covers full viewport
- Card: 360px width, 16px border-radius, white background
- Delete button: `#FF3B30` red background, white text
- Cancel button: gray border, white background
- Dismissible via Escape key, clicking outside, or Cancel button
- Delete button shows spinner + "Deleting..." while request is in flight

### Post-Delete UI Feedback

**Grid**:
1. Remove the deleted entry from `entries` array via `splice`
2. If the modal is open and the deleted frame is the current selection:
   - If there is a next frame → navigate to it (`next()`)
   - If it's the last frame → navigate to previous (`prev()`)
   - If no frames remain → close modal
3. Show toast: "Frame deleted" (auto-dismiss after 2 seconds)

**Timeline**:
1. Remove the deleted frame from `frames` array via `splice`
2. Adjust `currentIndex`:
   - If deleted frame was not the last → keep current index (next frame slides in)
   - If deleted frame was the last → `currentIndex -= 1`
   - If no frames remain → show "No captures" empty state
3. Show toast: "Frame deleted"

### Toast Component

Simple bottom-right notification:
- Fixed position, bottom 24px, right 24px
- Background: dark (`#333`), white text
- Padding: 12px 20px, border-radius: 8px
- Auto-dismiss after 2 seconds with fade-out animation

## Error Handling

| Scenario | API Response | UI Behavior |
|----------|-------------|-------------|
| Frame not found | 404 NOT_FOUND | Toast "Frame not found" |
| SQLite transaction fails | 500 INTERNAL_ERROR | Toast "Failed to delete frame" |
| LanceDB delete fails | 200 (warning logged) | Normal success flow |
| JPEG file delete fails | 200 (warning logged) | Normal success flow |
| Network error during DELETE | N/A (no response) | Toast "Network error, please try again" |

## Alpine.js State

**Grid** (`memoryGrid()`):
```javascript
deleteConfirmOpen: false,
frameToDelete: null,
deleting: false,
```

**Timeline** (`timelineView()`):
```javascript
deleteConfirmOpen: false,
deleting: false,
// Uses currentIndex to know which frame to delete
```

## Testing

### Unit Tests

1. `FramesStore.delete_frame(frame_id)`:
   - Delete existing frame → returns `(True, snapshot_path)`
   - Verify all associated rows are gone (ocr_text, accessibility, elements, descriptions, tasks)
   - Verify frame no longer appears in `get_frame()`
   - Delete non-existent frame → returns `(False, None)`

2. `DELETE /v1/frames/{id}`:
   - 200 on successful deletion
   - 404 on non-existent frame
   - Verify DB state after deletion

### Integration Tests

1. Delete frame → verify not returned by search API
2. Delete frame → verify not in timeline API
3. Delete frame → verify LanceDB embedding removed

## Files to Modify

| File | Change |
|------|--------|
| `openrecall/server/database/frames_store.py` | Add `delete_frame()` method |
| `openrecall/server/api_v1.py` | Add `DELETE /v1/frames/<frame_id>` route |
| `openrecall/client/web/templates/index.html` | Add delete button to card image + confirm dialog + Alpine.js methods |
| `openrecall/client/web/templates/timeline.html` | Add delete button to image container + confirm dialog + Alpine.js methods |
| `tests/test_p1_s1_frames.py` | Add tests for `delete_frame()` |
| `tests/test_api_v1.py` | Add tests for DELETE endpoint |

## Out of Scope

- Batch/multi-select delete
- Recycle bin / soft delete
- Undo functionality
- Delete from search results page (search.html)
- Keyboard shortcut for delete
