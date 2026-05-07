# Grid Day Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the Grid view to display captures for a single day at a time, with a floating date picker and prev/next day navigation.

**Architecture:** Two new API endpoints (`/api/memories/by-day`, `/api/memories/dates`) backed by new FramesStore methods. Frontend switches from flat list to day-centric Alpine.js state with a calendar popover.

**Tech Stack:** Python (Flask/SQLite), Alpine.js, Jinja2 templates

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `openrecall/server/database/frames_store.py` | Modify | Add `get_frames_by_day()` and `get_dates_with_data()` |
| `openrecall/server/api.py` | Modify | Add `/api/memories/by-day` and `/api/memories/dates` endpoints |
| `openrecall/client/web/templates/index.html` | Modify | Refactor to day view: date toolbar, day header with stats, calendar popover, single-day grid |
| `tests/test_p1_s1_frames.py` | Modify | Add tests for new FramesStore methods |

---

## Task 1: FramesStore — `get_frames_by_day`

**Files:**
- Modify: `openrecall/server/database/frames_store.py`
- Test: `tests/test_p1_s1_frames.py`

**Context:** `get_recent_memories()` (line 750) already has the exact SQL and field mapping we need. `get_frames_by_day()` is the same query with `WHERE DATE(local_timestamp) = ?` and no `LIMIT`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_p1_s1_frames.py`:

```python
def test_get_frames_by_day(test_store):
    """get_frames_by_day returns frames for a specific date."""
    frame_id, _ = test_store.claim_frame(
        capture_id="test-cap-day",
        metadata={
            "timestamp": "2026-04-28T02:00:00.000Z",
            "app_name": "TestApp",
            "capture_trigger": "idle",
        },
    )
    with test_store._connect() as conn:
        conn.execute(
            "UPDATE frames SET snapshot_path = ?, status = 'completed' WHERE id = ?",
            ("/tmp/test.jpg", frame_id),
        )
        conn.commit()
    result = test_store.get_frames_by_day("2026-04-28")
    assert len(result) >= 1
    assert result[0]["frame_id"] == frame_id
    # All expected fields present
    assert "app_name" in result[0]
    assert "visibility_status" in result[0]


def test_get_frames_by_day_empty(test_store):
    """get_frames_by_day returns empty list for date with no frames."""
    result = test_store.get_frames_by_day("1999-01-01")
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_p1_s1_frames.py::test_get_frames_by_day -v
```
Expected: `AttributeError: 'FramesStore' object has no attribute 'get_frames_by_day'`

- [ ] **Step 3: Implement `get_frames_by_day`**

Add the method immediately after `get_recent_memories()` (around line 845) in `openrecall/server/database/frames_store.py`:

```python
    def get_frames_by_day(self, date: str) -> list[dict[str, object]]:
        """Retrieve all frames for a specific day.

        Args:
            date: Date string in YYYY-MM-DD format (local_timestamp).

        Returns:
            List of dicts with frame data formatted for UI consumption.
            Same fields as get_recent_memories().
        """
        memories = []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT f.id, f.capture_id, f.local_timestamp AS timestamp, f.app_name, f.window_name,
                           f.snapshot_path, f.status, f.ingested_at, f.last_known_app,
                           f.last_known_window, f.text_source, f.processed_at,
                           f.capture_trigger, f.device_name, f.error_message,
                           f.accessibility_text, f.ocr_text, f.browser_url, f.focused,
                           f.description_status, f.embedding_status, f.visibility_status,
                           LENGTH(f.accessibility_text) as accessibility_text_length,
                           LENGTH(f.ocr_text) as ocr_text_length,
                           o.text_length, o.ocr_engine,
                           CASE
                             WHEN f.text_source = 'accessibility' THEN SUBSTR(f.accessibility_text, 1, 100)
                             WHEN f.text_source = 'ocr' THEN SUBSTR(f.ocr_text, 1, 100)
                             ELSE NULL
                           END AS text_preview,
                           CASE
                             WHEN f.text_source = 'accessibility' THEN LENGTH(f.accessibility_text)
                             WHEN f.text_source = 'ocr' THEN LENGTH(f.ocr_text)
                             ELSE 0
                           END AS text_length_computed,
                           fd.narrative, fd.summary,
                           CASE
                             WHEN fd.narrative IS NOT NULL OR fd.summary IS NOT NULL
                               THEN LENGTH(COALESCE(fd.narrative, '') || ' ' || COALESCE(fd.summary, ''))
                             ELSE 0
                           END AS description_length
                    FROM frames f
                    LEFT JOIN ocr_text o ON f.id = o.frame_id
                    LEFT JOIN frame_descriptions fd ON f.id = fd.frame_id
                    WHERE DATE(f.local_timestamp) = ?
                    ORDER BY f.local_timestamp DESC
                    """,
                    (date,),
                ).fetchall()

                for row in rows:
                    ts = row["timestamp"]
                    memories.append(
                        {
                            "id": row["id"],
                            "frame_id": row["id"],
                            "capture_id": row["capture_id"],
                            "timestamp": ts,
                            "app": row["app_name"] or "",
                            "title": row["window_name"] or "",
                            "status": (row["status"] or "pending").upper(),
                            "filename": f"{ts}.jpg",
                            "app_name": row["app_name"] or "",
                            "window_title": row["window_name"] or "",
                            "last_known_app": row["last_known_app"] or "",
                            "last_known_window": row["last_known_window"] or "",
                            "text_source": row["text_source"] or "",
                            "text_length": row["text_length_computed"] or 0,
                            "accessibility_text": row["accessibility_text"] or "",
                            "ocr_text": row["ocr_text"] or "",
                            "text_preview": row["text_preview"] or "",
                            "ocr_engine": row["ocr_engine"] or "",
                            "browser_url": row["browser_url"] or "",
                            "focused": bool(row["focused"]) if row["focused"] is not None else False,
                            "processed_at": row["processed_at"] or "",
                            "capture_trigger": row["capture_trigger"] or "",
                            "device_name": row["device_name"] or "",
                            "error_message": row["error_message"] or "",
                            "description_status": row["description_status"] or "",
                            "description_text": (row["narrative"] if row["narrative"] else row["summary"]) or "",
                            "description_length": row["description_length"] or 0,
                            "embedding_status": row["embedding_status"] or "",
                            "accessibility_text_length": row["accessibility_text_length"] or 0,
                            "ocr_text_length": row["ocr_text_length"] or 0,
                            "visibility_status": row["visibility_status"] or "pending",
                        }
                    )
        except sqlite3.Error as e:
            logger.error("get_frames_by_day failed: %s", e)
        return memories
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_p1_s1_frames.py::test_get_frames_by_day tests/test_p1_s1_frames.py::test_get_frames_by_day_empty -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/database/frames_store.py tests/test_p1_s1_frames.py
git commit -m "feat(frames): add get_frames_by_day for day-grouped grid"
```

---

## Task 2: FramesStore — `get_dates_with_data`

**Files:**
- Modify: `openrecall/server/database/frames_store.py`
- Test: `tests/test_p1_s1_frames.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_p1_s1_frames.py`:

```python
def test_get_dates_with_data(test_store):
    """get_dates_with_data returns dates that have frames in a month."""
    frame_id, _ = test_store.claim_frame(
        capture_id="test-cap-dates",
        metadata={
            "timestamp": "2026-04-28T02:00:00.000Z",
            "app_name": "TestApp",
            "capture_trigger": "idle",
        },
    )
    with test_store._connect() as conn:
        conn.execute(
            "UPDATE frames SET snapshot_path = ? WHERE id = ?",
            ("/tmp/test.jpg", frame_id),
        )
        conn.commit()
    result = test_store.get_dates_with_data("2026-04")
    assert "2026-04-28" in result


def test_get_dates_with_data_empty_month(test_store):
    """get_dates_with_data returns empty list for month with no frames."""
    result = test_store.get_dates_with_data("1999-01")
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_p1_s1_frames.py::test_get_dates_with_data -v
```
Expected: `AttributeError: 'FramesStore' object has no attribute 'get_dates_with_data'`

- [ ] **Step 3: Implement `get_dates_with_data`**

Add immediately after `get_frames_by_day()`:

```python
    def get_dates_with_data(self, month: str) -> list[str]:
        """Return dates in a month that have at least one frame.

        Args:
            month: Month string in YYYY-MM format.

        Returns:
            List of date strings in YYYY-MM-DD format, sorted ascending.
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT DISTINCT DATE(local_timestamp) AS date
                    FROM frames
                    WHERE DATE(local_timestamp) LIKE ?
                    ORDER BY date
                    """,
                    (f"{month}-%",),
                ).fetchall()
                return [row["date"] for row in rows]
        except sqlite3.Error as e:
            logger.error("get_dates_with_data failed: %s", e)
            return []
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_p1_s1_frames.py::test_get_dates_with_data tests/test_p1_s1_frames.py::test_get_dates_with_data_empty_month -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/database/frames_store.py tests/test_p1_s1_frames.py
git commit -m "feat(frames): add get_dates_with_data for calendar marks"
```

---

## Task 3: API — `/api/memories/by-day` Endpoint

**Files:**
- Modify: `openrecall/server/api.py`
- Test: `tests/test_api.py` (or create if not existing)

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_memories_by_day.py`:

```python
import pytest


def test_memories_by_day_missing_param(flask_client):
    """Returns 400 when date param is missing."""
    resp = flask_client.get("/api/memories/by-day")
    assert resp.status_code == 400
    assert "date" in resp.get_json()["message"].lower()


def test_memories_by_day_invalid_format(flask_client):
    """Returns 400 when date format is invalid."""
    resp = flask_client.get("/api/memories/by-day?date=bad-date")
    assert resp.status_code == 400
    assert "YYYY-MM-DD" in resp.get_json()["message"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_api_memories_by_day.py -v
```
Expected: 404 (endpoint not registered yet)

- [ ] **Step 3: Implement the endpoint**

Add to `openrecall/server/api.py`, immediately after the `memories_recent()` function (around line 212):

```python


@api_bp.route("/memories/by-day", methods=["GET"])
def memories_by_day():
    """Retrieve all frames for a specific day.

    Query Params:
        date: Date in YYYY-MM-DD format (local_timestamp).

    Returns:
        JSON list of frame dicts (same format as /api/memories/recent).
    """
    import re

    date_str = (request.args.get("date") or "").strip()
    if not date_str:
        return jsonify({"status": "error", "message": "Query parameter 'date' is required"}), 400
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return (
            jsonify({"status": "error", "message": "Query parameter 'date' must be in YYYY-MM-DD format"}),
            400,
        )

    try:
        memories = frames_store.get_frames_by_day(date=date_str)
        return jsonify(memories), 200
    except Exception as e:
        logger.exception("Error fetching frames by day")
        return jsonify({"status": "error", "message": str(e)}), 500
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_api_memories_by_day.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/api.py tests/test_api_memories_by_day.py
git commit -m "feat(api): add /api/memories/by-day endpoint"
```

---

## Task 4: API — `/api/memories/dates` Endpoint

**Files:**
- Modify: `openrecall/server/api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_memories_by_day.py`:

```python
def test_memories_dates_missing_param(flask_client):
    """Returns 400 when month param is missing."""
    resp = flask_client.get("/api/memories/dates")
    assert resp.status_code == 400
    assert "month" in resp.get_json()["message"].lower()


def test_memories_dates_invalid_format(flask_client):
    """Returns 400 when month format is invalid."""
    resp = flask_client.get("/api/memories/dates?month=bad")
    assert resp.status_code == 400
    assert "YYYY-MM" in resp.get_json()["message"]


def test_memories_dates_returns_dates(flask_client):
    """Returns list of dates for a month."""
    resp = flask_client.get("/api/memories/dates?month=2026-04")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dates" in data
    assert isinstance(data["dates"], list)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_api_memories_by_day.py::test_memories_dates_missing_param -v
```
Expected: 404

- [ ] **Step 3: Implement the endpoint**

Add to `openrecall/server/api.py`, immediately after `memories_by_day()`:

```python


@api_bp.route("/memories/dates", methods=["GET"])
def memories_dates():
    """Return dates in a month that have frame captures.

    Query Params:
        month: Month in YYYY-MM format.

    Returns:
        JSON {"dates": ["YYYY-MM-DD", ...]}.
    """
    import re

    month_str = (request.args.get("month") or "").strip()
    if not month_str:
        return jsonify({"status": "error", "message": "Query parameter 'month' is required"}), 400
    if not re.match(r"^\d{4}-\d{2}$", month_str):
        return (
            jsonify({"status": "error", "message": "Query parameter 'month' must be in YYYY-MM format"}),
            400,
        )

    try:
        dates = frames_store.get_dates_with_data(month=month_str)
        return jsonify({"dates": dates}), 200
    except Exception as e:
        logger.exception("Error fetching dates with data")
        return jsonify({"status": "error", "message": str(e)}), 500
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_api_memories_by_day.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/api.py tests/test_api_memories_by_day.py
git commit -m "feat(api): add /api/memories/dates endpoint for calendar marks"
```

---

## Task 5: Frontend — Toolbar + Day Header + Calendar Popover CSS

**Files:**
- Modify: `openrecall/client/web/templates/index.html`

**Context:** `layout.html` does NOT define a `toolbar_center` block — the existing `toolbar_center` in `index.html` is an orphan block that is never rendered. The date navigation must be placed inside the `content` block instead. Also add CSS for the calendar popover and day header.

- [ ] **Step 1: Remove orphan `toolbar_center` block**

In `openrecall/client/web/templates/index.html`, delete the entire `toolbar_center` block (lines 5-14):

```html
{% block toolbar_center %}
<div class="form-group">
  <label for="start_time">Start Time</label>
  <input type="datetime-local" id="start_time" name="start_time">
</div>
<div class="form-group">
  <label for="end_time">End Time</label>
  <input type="datetime-local" id="end_time" name="end_time">
</div>
{% endblock %}
```

**This block has no effect** — `layout.html` does not contain `{% block toolbar_center %}` — so removing it is safe.

- [ ] **Step 2: Add CSS for calendar popover and day header**

Add the following CSS to the `<style>` block in `index.html` (insert before the `/* Spinner Animation */` comment around line 74):

```css
  /* =============================================
     Day Header + Date Navigation
     ============================================= */

  .day-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 0;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--border-color);
  }

  .day-title {
    font-size: 20px;
    font-weight: 600;
    color: var(--text-primary);
    letter-spacing: -0.3px;
  }

  .day-stats {
    display: flex;
    gap: 16px;
    align-items: center;
  }

  .day-stat {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .day-stat-value {
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 12px;
    font-family: 'SF Mono', Monaco, Consolas, monospace;
  }

  .day-stat.completed .day-stat-value {
    background: var(--color-success-bg);
    color: #2A9D4A;
  }

  .day-stat.pending .day-stat-value {
    background: var(--color-warning-bg);
    color: #D4840D;
  }

  .day-stat.failed .day-stat-value {
    background: rgba(255, 59, 48, 0.1);
    color: #FF3B30;
  }

  /* Date Navigation Toolbar */
  .date-nav-toolbar {
    position: relative;
  }

  .today-btn {
    font-size: 13px;
    font-weight: 500;
    padding: 6px 14px;
    border-radius: 6px;
    border: 1px solid var(--border-color);
    background: var(--bg-card);
    color: var(--text-primary);
    cursor: pointer;
    transition: all 0.2s;
  }

  .today-btn:hover:not(:disabled) {
    background: var(--accent-color);
    color: white;
    border-color: var(--accent-color);
  }

  .toolbar-nav-btn {
    width: 32px;
    height: 32px;
    border-radius: 6px;
    border: 1px solid var(--border-color);
    background: var(--bg-card);
    color: var(--text-primary);
    font-size: 18px;
    line-height: 1;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
    padding-bottom: 2px;
  }

  .toolbar-nav-btn:hover {
    background: var(--icon-hover);
    border-color: var(--accent-color);
    color: var(--accent-color);
  }

  .date-picker-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    border-radius: 8px;
    border: 1px solid var(--border-color);
    background: var(--bg-card);
    color: var(--text-primary);
    font-size: 14px;
    font-weight: 500;
    font-family: var(--font-stack);
    cursor: pointer;
    transition: all 0.2s;
  }

  .date-picker-btn:hover {
    border-color: var(--accent-color);
    background: rgba(0, 122, 255, 0.05);
  }

  /* Calendar Popover */
  .calendar-popover {
    position: absolute;
    top: 44px;
    left: 50%;
    transform: translateX(-50%);
    width: 280px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
    padding: 16px;
    z-index: 1002;
    animation: popoverIn 0.2s ease-out forwards;
  }

  .calendar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }

  .calendar-nav {
    width: 28px;
    height: 28px;
    border-radius: 6px;
    border: none;
    background: transparent;
    color: var(--text-secondary);
    font-size: 16px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }

  .calendar-nav:hover {
    background: var(--icon-hover);
    color: var(--text-primary);
  }

  .calendar-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .calendar-weekdays {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 2px;
    margin-bottom: 4px;
  }

  .calendar-weekdays span {
    text-align: center;
    font-size: 11px;
    font-weight: 500;
    color: var(--text-tertiary);
    padding: 4px;
  }

  .calendar-days {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 2px;
  }

  .calendar-day {
    aspect-ratio: 1;
    border: none;
    border-radius: 8px;
    background: transparent;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    transition: all 0.15s;
  }

  .calendar-day:hover:not(:disabled) {
    background: rgba(0, 122, 255, 0.1);
  }

  .calendar-day.is-other-month {
    color: var(--text-tertiary);
    opacity: 0.5;
  }

  .calendar-day.is-selected {
    background: var(--accent-color);
    color: white;
  }

  .calendar-day.is-today:not(.is-selected) {
    border: 1.5px solid var(--accent-color);
    color: var(--accent-color);
  }

  .calendar-day.has-data::after {
    content: '';
    position: absolute;
    bottom: 3px;
    left: 50%;
    transform: translateX(-50%);
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: var(--accent-color);
  }

  .calendar-day:disabled {
    cursor: default;
    opacity: 0.2;
  }

  @keyframes popoverIn {
    from { opacity: 0; transform: translateX(-50%) translateY(-8px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
```

- [ ] **Step 3: Update content block — add date navigation toolbar + day header**

Replace the content block in `index.html` (lines 1278-1696) with the day-centric layout. Keep the same grid card markup, just wrap it:

**At the top of the content block, right after `<div x-data="memoryGrid()" x-init="await init()" x-cloak>`, add the date navigation toolbar:**

```html
  <!-- Date Navigation Toolbar (replaces orphan toolbar_center) -->
  <div class="date-nav-toolbar" style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
    <button type="button" class="toolbar-nav-btn today-btn" @click="goToday()" :disabled="isToday(currentDate)">
      Today
    </button>
    <button type="button" class="toolbar-nav-btn" @click="prevDay()" title="Previous day">
      ‹
    </button>
    <!-- Calendar wrapper: click.away on the parent so clicking the button does NOT close -->
    <div @click.away="calendarOpen = false" style="position: relative;">
      <button type="button" class="date-picker-btn" @click="toggleCalendar()">
        <span>📅</span>
        <span x-text="currentDate"></span>
        <span style="font-size: 10px; opacity: 0.6;">▼</span>
      </button>
      <!-- Calendar Popover -->
      <div x-show="calendarOpen" class="calendar-popover" x-cloak>
        <div class="calendar-header">
          <button type="button" class="calendar-nav" @click="prevMonth()">‹</button>
          <span class="calendar-title" x-text="`${calendarYear}年${calendarMonth + 1}月`"></span>
          <button type="button" class="calendar-nav" @click="nextMonth()">›</button>
        </div>
        <div class="calendar-weekdays">
          <span>日</span><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span>
        </div>
        <div class="calendar-days">
          <template x-for="day in calendarDays()" :key="day.date || `${calendarYear}-${calendarMonth}-${day.day}`">
            <button
              type="button"
              class="calendar-day"
              :class="{
                'is-other-month': day.isOtherMonth,
                'is-selected': day.date === currentDate,
                'is-today': day.date && isToday(day.date),
                'has-data': day.date && hasData(day.date)
              }"
              :disabled="!day.date"
              @click="day.date && selectDate(day.date)"
              x-text="day.day"
            ></button>
          </template>
        </div>
      </div>
    </div>
    <button type="button" class="toolbar-nav-btn" @click="nextDay()" title="Next day">
      ›
    </button>
  </div>
```

**Then before the `<template x-if="entries.length > 0">` (around line 1280), add the day header:**

```html
  <!-- Day Header -->
  <div class="day-header">
    <h2 class="day-title" x-text="formatDateDisplay(currentDate)"></h2>
    <div class="day-stats">
      <div class="day-stat completed">
        <span>Completed</span>
        <span class="day-stat-value" x-text="stats().completed"></span>
      </div>
      <div class="day-stat pending">
        <span>Pending</span>
        <span class="day-stat-value" x-text="stats().pending"></span>
      </div>
      <div class="day-stat failed">
        <span>Failed</span>
        <span class="day-stat-value" x-text="stats().failed"></span>
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
  </div>
```

**Remove the old `stats-bar` div** (lines 1282-1309, the stats-bar that was inside the template). The stats are now in the day header.

**Update the empty state** (around line 1691) to show the date:

```html
  <template x-if="entries.length === 0">
    <div class="empty-state">
      <div>No captures on <span x-text="currentDate"></span>.</div>
      <div style="font-size: 13px; color: var(--text-tertiary); margin-top: 8px;">Select another date to browse history.</div>
    </div>
  </template>
```

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "feat(ui): add day header, date toolbar, and calendar popover CSS"
```

---

## Task 6: Frontend — Alpine.js State Refactor

**Files:**
- Modify: `openrecall/client/web/templates/index.html`

**Context:** The existing Alpine.js `memoryGrid()` function (lines 1701-2271) has many helper methods that stay unchanged. Only the state initialization, data loading, and date navigation methods need changes.

- [ ] **Step 1: Replace the `memoryGrid()` return object**

Replace the entire `memoryGrid()` function body (lines 1701-2271). Keep all unchanged helper methods, replace/ add the state and navigation methods:

```javascript
  function memoryGrid() {
    return {
      entries: [],
      config: window.initialConfig || { show_ai_description: false },
      currentDate: '',
      datesWithData: new Set(),
      calendarOpen: false,
      calendarYear: 0,
      calendarMonth: 0,
      lastCheckMs: 0,
      selectedIndex: null,
      modalTab: 'image',
      retrying: false,

      // ---- Date Navigation (new) ----

      _formatDateStr(date) {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
      },

      // Return current time as if in UTC+8, regardless of browser timezone.
      // We start with local time, then shift by (browser offset + 480min) to get UTC+8 wall-clock.
      _utc8Now() {
        const now = new Date();
        now.setMinutes(now.getMinutes() + now.getTimezoneOffset() + 480);
        return now;
      },

      async loadDay(date) {
        try {
          const res = await fetch(`${EDGE_BASE_URL}/api/memories/by-day?date=${date}`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          if (Array.isArray(data)) {
            this.entries = data;
            this.syncLastCheckFromEntries(data);
          }
        } catch (e) {
          console.error('Failed to load day:', e);
        }
      },

      prevDay() {
        const [y, m, d] = this.currentDate.split('-').map(Number);
        const date = new Date(y, m - 1, d);
        date.setDate(date.getDate() - 1);
        this.currentDate = this._formatDateStr(date);
        this.loadDay(this.currentDate);
      },

      nextDay() {
        const [y, m, d] = this.currentDate.split('-').map(Number);
        const date = new Date(y, m - 1, d);
        date.setDate(date.getDate() + 1);
        this.currentDate = this._formatDateStr(date);
        this.loadDay(this.currentDate);
      },

      goToday() {
        const now = this._utc8Now();
        this.currentDate = this._formatDateStr(now);
        this.calendarYear = now.getFullYear();
        this.calendarMonth = now.getMonth();
        this.loadDay(this.currentDate);
      },

      isToday(date) {
        return date === this._formatDateStr(this._utc8Now());
      },

      formatDateDisplay(date) {
        const [y, m, day] = date.split('-').map(Number);
        const d = new Date(y, m - 1, day);
        const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
        return `${y}年${m}月${day}日（星期${weekdays[d.getDay()]}）`;
      },

      // ---- Calendar (new) ----

      async loadCalendarDates() {
        const monthStr = `${this.calendarYear}-${String(this.calendarMonth + 1).padStart(2, '0')}`;
        try {
          const res = await fetch(`${EDGE_BASE_URL}/api/memories/dates?month=${monthStr}`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          this.datesWithData = new Set(data.dates || []);
        } catch (e) {
          console.error('Failed to load calendar dates:', e);
        }
      },

      toggleCalendar() {
        this.calendarOpen = !this.calendarOpen;
        if (this.calendarOpen) {
          this.loadCalendarDates();
        }
      },

      selectDate(date) {
        this.currentDate = date;
        this.calendarOpen = false;
        this.loadDay(date);
      },

      prevMonth() {
        this.calendarMonth -= 1;
        if (this.calendarMonth < 0) {
          this.calendarMonth = 11;
          this.calendarYear -= 1;
        }
        this.loadCalendarDates();
      },

      nextMonth() {
        this.calendarMonth += 1;
        if (this.calendarMonth > 11) {
          this.calendarMonth = 0;
          this.calendarYear += 1;
        }
        this.loadCalendarDates();
      },

      calendarDays() {
        const firstDay = new Date(this.calendarYear, this.calendarMonth, 1);
        const lastDay = new Date(this.calendarYear, this.calendarMonth + 1, 0);
        const startOffset = firstDay.getDay();
        const days = [];

        const prevMonthLastDay = new Date(this.calendarYear, this.calendarMonth, 0).getDate();
        for (let i = startOffset - 1; i >= 0; i--) {
          days.push({ date: null, day: prevMonthLastDay - i, isOtherMonth: true });
        }

        for (let i = 1; i <= lastDay.getDate(); i++) {
          const dateStr = `${this.calendarYear}-${String(this.calendarMonth + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
          days.push({ date: dateStr, day: i, isOtherMonth: false });
        }

        const remaining = 42 - days.length;
        for (let i = 1; i <= remaining; i++) {
          days.push({ date: null, day: i, isOtherMonth: true });
        }

        return days;
      },

      hasData(date) {
        return this.datesWithData.has(date);
      },

      // Refresh status of already-loaded entries for today (avoids stale pending/completed states)
      async refreshCurrentDay() {
        if (!this.isToday(this.currentDate)) return;
        try {
          const res = await fetch(`${EDGE_BASE_URL}/api/memories/by-day?date=${this.currentDate}`);
          if (!res.ok) return;
          const fresh = await res.json();
          if (!Array.isArray(fresh)) return;
          const freshById = new Map(fresh.map(e => [e.id, e]));
          for (let i = 0; i < this.entries.length; i++) {
            const entry = this.entries[i];
            if (!entry?.id) continue;
            const updated = freshById.get(entry.id);
            if (updated) {
              this.entries[i] = updated;
            }
          }
          const existingIds = new Set(this.entries.map(e => e.id).filter(Boolean));
          const newItems = fresh.filter(e => e.id && !existingIds.has(e.id));
          if (newItems.length > 0) {
            this.entries.unshift(...newItems);
            this.syncLastCheckFromEntries(newItems);
          }
        } catch (_e) {
          // Silent fail
        }
      },

      // ---- Modified Init ----

      async init() {
        const now = this._utc8Now();
        this.currentDate = this._formatDateStr(now);
        this.calendarYear = now.getFullYear();
        this.calendarMonth = now.getMonth();

        await this.loadDay(this.currentDate);

        window.addEventListener("openrecall-config-changed", () => {
          this.loadDay(this.currentDate);
        });

        window.addEventListener("keydown", (e) => {
          if (!this.isOpen()) return;
          if (e.key === "Escape") this.closeModal();
          if (e.key === "ArrowLeft") this.prev();
          if (e.key === "ArrowRight") this.next();
        });

        setInterval(() => {
          this.checkNew();
          this.refreshCurrentDay();
        }, 5000);
      },

      // ---- Modified checkNew (only for today) ----

      async checkNew() {
        if (!this.isToday(this.currentDate)) return;

        try {
          const sinceIso = this.lastCheckMs > 0
            ? this.formatLocalSince(this.lastCheckMs)
            : '1970-01-01T00:00:00.000';
          const res = await fetch(`${EDGE_BASE_URL}/v1/frames/latest?since=${encodeURIComponent(sinceIso)}`);
          if (!res.ok) return;
          const newItems = await res.json();
          if (!Array.isArray(newItems) || newItems.length === 0) return;

          const existingKeys = new Set(
            this.entries.map((e, idx) => (e?.id ?? `${e?.timestamp}-${idx}`)).filter((v) => v !== undefined)
          );
          const uniqueItems = newItems.filter((e, idx) => {
            const key = e?.id ?? `${e?.timestamp}-${idx}`;
            return !existingKeys.has(key);
          });
          if (uniqueItems.length === 0) return;

          if (this.selectedIndex !== null) {
            this.selectedIndex += uniqueItems.length;
          }
          this.entries.unshift(...uniqueItems);
          this.syncLastCheckFromEntries(uniqueItems);
        } catch (_e) {
          return;
        }
      },

      // refreshRecent replaced by refreshCurrentDay (status refresh) + loadDay (full reload)
      // retryFailed() MUST call this.loadDay(this.currentDate) instead of this.refreshRecent()

      // ---- Unchanged helper methods (keep all existing ones) ----

      syncLastCheckFromEntries(list) {
        let maxMs = this.lastCheckMs;
        for (const entry of list) {
          const date = parseTimestamp(entry?.timestamp);
          if (!date) continue;
          const ms = date.getTime();
          if (ms > maxMs) maxMs = ms;
        }
        this.lastCheckMs = maxMs;
      },

      formatLocalSince(ms) {
        const d = new Date(ms);
        const utc = d.getTime() + d.getTimezoneOffset() * 60000;
        const local = new Date(utc + 8 * 3600 * 1000);
        const pad = (v) => String(v).padStart(2, '0');
        return `${local.getUTCFullYear()}-${pad(local.getUTCMonth() + 1)}-${pad(local.getUTCDate())}T`
             + `${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}:${pad(local.getUTCSeconds())}.${String(local.getUTCMilliseconds()).padStart(3, '0')}`;
      },

      stats() {
        const out = { completed: 0, pending: 0, failed: 0 };
        for (const entry of this.entries) {
          const status = (entry?.visibility_status || 'pending').toLowerCase();
          if (status === "queryable") out.completed += 1;
          else if (status === "pending") out.pending += 1;
          else if (status === "failed") out.failed += 1;
        }
        return out;
      },

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
            await this.loadDay(this.currentDate);
          } else {
            console.error('Retry failed:', res.status);
          }
        } catch (e) {
          console.error('Retry failed:', e);
        } finally {
          this.retrying = false;
        }
      },

      // ... [keep ALL existing helper methods unchanged]
      // getDeviceIcon, formatRelativeTime, getAppDisplay, getAppNameTooltip,
      // getProcessingDuration, copyOcrText, copyAccessibilityText,
      // fetchDescriptionData, formatFileSize, getTextSourceClass,
      // getTextSourceStatusIcon, getTextSourceStatusClass,
      // getAccessibilityCharCount, getOcrCharCount,
      // getDescriptionStatusIcon, getDescriptionStatusClass,
      // getEmbeddingStatusIcon, getEmbeddingStatusClass,
      // getFrameStatus, getFrameStatusIcon, getFrameStatusClass,
      // getFrameStatusText, formatAxCount, getAppIcon, formatOcrCount,
      // getDescriptionCharCount, getDescriptionStatusText,
      // getEmbeddingStatusText, formatTime, imageSrc,
      // isOpen, openAt, closeModal, prev, next
    };
  }
```

**Important:** When editing, keep all the unchanged helper methods that follow `retryFailed()` in the original file. Only replace the top portion (state vars, init, checkNew, refreshRecent, syncLastCheckFromEntries, stats, retryFailed) and add the new date/calendar methods.

Specifically, do NOT delete these existing methods: `getDeviceIcon`, `formatRelativeTime`, `getAppDisplay`, `getAppNameTooltip`, `getProcessingDuration`, `copyOcrText`, `copyAccessibilityText`, `fetchDescriptionData`, `formatFileSize`, `getTextSourceClass`, `getTextSourceStatusIcon`, `getTextSourceStatusClass`, `getAccessibilityCharCount`, `getOcrCharCount`, `getDescriptionStatusIcon`, `getDescriptionStatusClass`, `getEmbeddingStatusIcon`, `getEmbeddingStatusClass`, `getFrameStatus`, `getFrameStatusIcon`, `getFrameStatusClass`, `getFrameStatusText`, `formatAxCount`, `getAppIcon`, `formatOcrCount`, `getDescriptionCharCount`, `getDescriptionStatusText`, `getEmbeddingStatusText`, `formatTime`, `imageSrc`, `isOpen`, `openAt`, `closeModal`, `prev`, `next`.

- [ ] **Step 2: Remove `refreshRecent` call from init**

Confirm that `init()` no longer calls `this.refreshRecent()`. It should only call `this.loadDay(this.currentDate)`.

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "feat(ui): refactor Alpine.js to day-centric state with calendar nav"
```

---

## Task 7: Integration Test — End-to-End

**Files:**
- Test: `tests/test_grid_day_view.py` (new file)

- [ ] **Step 1: Write integration test**

```python
"""Integration tests for grid day view API endpoints."""

import pytest


@pytest.mark.integration
def test_api_by_day_returns_frames(flask_client):
    """The by-day API returns frames for a known date."""
    resp = flask_client.get("/api/memories/by-day?date=2026-04-28")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


@pytest.mark.integration
def test_api_dates_returns_list(flask_client):
    """The dates API returns a dates list."""
    resp = flask_client.get("/api/memories/dates?month=2026-04")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dates" in data
    assert isinstance(data["dates"], list)
```

- [ ] **Step 2: Run the tests**

```bash
pytest tests/test_grid_day_view.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_grid_day_view.py
git commit -m "test: add integration tests for grid day view"
```

---

## Task 8: Manual Verification

- [ ] **Step 1: Start the Edge server**

```bash
./run_server.sh --mode local --debug
```

- [ ] **Step 2: Start the client**

```bash
./run_client.sh --mode local --debug
```

- [ ] **Step 3: Open browser and verify**

Navigate to `http://localhost:8889` and check:

1. Page loads with today's date shown in the toolbar
2. Grid shows captures for today only
3. Stats bar shows today's completed/pending/failed counts
4. Click date picker button → calendar popover opens
5. Days with captures show a dot mark
6. Click a different date → grid updates to that day's captures
7. Click ◀ / ▶ arrows → navigates prev/next day
8. Click Today → jumps back to today
9. Switch months in calendar → dot marks update
10. Modal still works (click card image → full view with tabs)

- [ ] **Step 4: Commit any fixes**

If any bugs found, fix and commit with descriptive messages.

---

## Self-Review

### 1. Spec Coverage

| Spec Requirement | Task |
|-----------------|------|
| `GET /api/memories/by-day` endpoint | Task 3 |
| `GET /api/memories/dates` endpoint | Task 4 |
| `FramesStore.get_frames_by_day()` | Task 1 |
| `FramesStore.get_dates_with_data()` | Task 2 |
| Today button | Task 5 (toolbar) + Task 6 (goToday) |
| Date picker button with calendar popover | Task 5 (HTML/CSS) + Task 6 (calendar methods) |
| Prev/Next day navigation | Task 5 (HTML) + Task 6 (prevDay/nextDay) |
| Day header with date + stats | Task 5 (HTML/CSS) |
| Calendar marks (dots for dates with data) | Task 6 (hasData + calendarDays) |
| Single-day grid, no limit | Task 1 (no LIMIT in SQL) + Task 6 (loadDay) |
| Empty state for dates with no captures | Task 5 |
| Real-time updates only for today | Task 6 (checkNew modified) |

**Coverage: complete. No gaps.**

### 2. Placeholder Scan

- No TBD/TODO/fill in details — all steps have concrete code
- No vague instructions like "add appropriate error handling" — validation logic is explicit
- No "similar to Task N" references — each task is self-contained
- All file paths are exact

### 3. Type Consistency

- `get_frames_by_day(date: str) -> list[dict[str, object]]` — consistent with `get_recent_memories`
- `get_dates_with_data(month: str) -> list[str]` — consistent naming
- `currentDate` uses `YYYY-MM-DD` format throughout
- `_formatDateStr()` and `_utc8Now()` used consistently

### 4. Review Fixes Applied

| Issue | Fix |
|-------|-----|
| `toolbar_center` block doesn't exist in `layout.html` | Removed orphan block; date nav moved into `content` block |
| `prevDay`/`nextDay`/`formatDateDisplay` timezone bug with `+08:00` strings | Changed to `new Date(y, m-1, d)` local constructor |
| `_utc8Now()` implementation obscure | Added explanatory comment |
| Test fixture `client` doesn't exist in conftest.py | Changed all test params to `flask_client` |
| HTML page test uses server client for client web route | Simplified to API-only integration tests |
| `sample_frame` fixture doesn't exist in `test_p1_s1_frames.py` | Changed to `test_store` with inline frame creation |
| `@click.away` conflicts with `toggleCalendar()` | Wrapped button + popover in a parent div with `@click.away` |
| Stale frame statuses not refreshed after background processing | Added `refreshCurrentDay()` method in setInterval |
| `loadDay()` clears entries before fetch, violating spec "keep data on error" | Removed `this.entries = []`; new data replaces old directly |
| `formatDateDisplay` uses English weekday names | Changed to Chinese `星期X` |
| `.toolbar-nav-btn` class used in HTML but no CSS defined | Added `.toolbar-nav-btn` CSS block |
| `retryFailed()` still calls removed `refreshRecent()` | Provided modified `retryFailed()` in code snippet; calls `this.loadDay()` |
| `init()` not async, `loadDay()` not awaited → blank flash on load | Changed `init()` to async with `await this.loadDay()` |
| `x-init="init()"` doesn't wait for async init in Alpine.js | Changed to `x-init="await init()"` |

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-28-grid-day-grouping.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review

**Which approach?**
