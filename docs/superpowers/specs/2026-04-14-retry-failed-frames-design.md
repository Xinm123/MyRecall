# Retry Failed Frames - Design Spec

**Date:** 2026-04-14
**Status:** Draft

## Overview

Add a "Retry Failed" button to the grid interface that resets all frames with `visibility_status = 'failed'` back to pending, allowing workers to reprocess them.

## Background

Frames can fail at three stages:
- OCR (`status = 'failed'`)
- Description (`description_status = 'failed'`)
- Embedding (`embedding_status = 'failed'`)

When any stage fails, `visibility_status` is set to `'failed'` and the frame becomes invisible in search results. Currently there's no way to retry these failed frames from the UI.

## Design

### Backend API

**New Endpoint:** `POST /v1/admin/frames/retry-failed`

**Request:** No body required

**Response:**
```json
{
  "message": "Retry triggered",
  "reset_count": 5,
  "breakdown": {
    "ocr": 1,
    "description": 2,
    "embedding": 3
  },
  "request_id": "uuid-v4"
}
```

**Logic:**
1. Query all frames where `visibility_status = 'failed'`
2. For each frame, determine which stage(s) failed
3. Reset only the failed stage(s) to `pending`:
   - OCR failed → `status = 'pending'`, clear `error_message`
   - Description failed → `description_status = 'pending'`, reset task to pending, enqueue if needed
   - Embedding failed → `embedding_status = 'pending'`, reset task to pending, enqueue if needed
4. Set `visibility_status = 'pending'` for all affected frames
5. Return count and breakdown

**Location:** `openrecall/server/api_v1.py`

### Database Layer

**New method:** `FramesStore.reset_failed_frames()`

**Returns:** Dict with `total` count and `breakdown` by stage

**SQL Operations (executed in order):**
1. Count and update OCR failures
2. Count and update description failures
3. Count and update embedding failures
4. Set `visibility_status = 'pending'` where `visibility_status = 'failed'`
5. Re-enqueue description/embedding tasks for reset frames

**Location:** `openrecall/server/database/frames_store.py`

### Frontend UI

**Button placement:** Stats bar, after the "Failed" counter

**Visual design:**
```
[Completed: 42] [Pending: 3] [Failed: 5] [↻ Retry Failed]
```

**Button behavior:**
- Only visible when `stats().failed > 0`
- Shows loading spinner during request
- On success: refresh grid via `loadEntries()`
- On error: show error message

**Alpine.js method:**
```javascript
async retryFailed() {
  this.retrying = true;
  try {
    const res = await fetch(`${EDGE_BASE_URL}/v1/admin/frames/retry-failed`, {
      method: 'POST'
    });
    if (res.ok) {
      const data = await res.json();
      // Optionally show toast with count
      this.refreshRecent();
    }
  } finally {
    this.retrying = false;
  }
}
```

**Location:** `openrecall/client/web/templates/index.html`

## Files Changed

| File | Change |
|------|--------|
| `openrecall/server/api_v1.py` | Add `retry_failed()` endpoint |
| `openrecall/server/database/frames_store.py` | Add `reset_failed_frames()` method |
| `openrecall/client/web/templates/index.html` | Add retry button and Alpine.js handler |

## Testing

- Unit test for `reset_failed_frames()` with various failure combinations
- Integration test for the API endpoint
- Manual test in browser with failed frames
