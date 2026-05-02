# Timeline Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `timeline.html` to use day-centric navigation with calendar picker and playback controls.

**Architecture:** Single-file rewrite of the `timeline.html` Jinja2 template. Reuses CSS classes and interaction patterns from `index.html` (Grid view). Alpine.js `timelineView()` manages day loading, calendar, and playback state. No backend changes.

**Tech Stack:** Jinja2, Alpine.js, vanilla CSS, existing Edge APIs

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `openrecall/client/web/templates/timeline.html` | Rewrite | Day navigation, calendar popover, slider, playback controls, image display |
| `openrecall/client/web/templates/index.html` | Reference only | Source of truth for calendar CSS, date nav markup, Alpine.js date/calendar patterns |
| `openrecall/client/web/templates/layout.html` | Reference only | Provides `parseTimestamp()`, `EDGE_BASE_URL` |

---

## Task 1: Add Calendar CSS Styles to Timeline

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html`

Copy calendar-related CSS classes from `index.html` into `timeline.html`'s `<style>` block. The styles needed are:

- `.date-nav-toolbar` (`position: relative` only — flex layout is inline in Task 2 HTML)
- `.today-btn`
- `.toolbar-nav-btn`
- `.date-picker-btn`
- `.calendar-popover` (update `animation` to use `calendarPopoverIn` — see note below)
- `.calendar-header`
- `.calendar-nav`
- `.calendar-weekdays`
- `.calendar-days`
- `.calendar-day` (with `.is-other-month`, `.is-selected`, `.is-today`, `.has-data` variants)
- `@keyframes calendarPopoverIn` (renamed from `popoverIn` to avoid conflict with `layout.html`)
- `.loading-bar`
- `@keyframes loadingShimmer`
- `[x-cloak]` (from index.html end of style block)

> **Note:** `.calendar-title` has no CSS rules in `index.html` (it's used only in HTML markup), so skip it. When copying `.calendar-popover` from `index.html`, change its `animation` property from `popoverIn` to `calendarPopoverIn`.

Also add `:root { --text-tertiary: #8E8E93; }` (needed for `.calendar-weekdays span` color; defined in `index.html`'s `:root` but not inherited by `timeline.html`).

Also add playback control styles:

```css
:root {
  --text-tertiary: #8E8E93;
}

.playback-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.play-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.play-btn:hover:not(:disabled) {
  background: var(--accent-color);
  color: white;
  border-color: var(--accent-color);
}

.play-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.speed-btn {
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  background: var(--bg-card);
  color: var(--text-primary);
  cursor: pointer;
  font-family: var(--font-stack);
  transition: all 0.2s;
  min-width: 40px;
}

.speed-btn:hover:not(:disabled) {
  border-color: var(--accent-color);
  color: var(--accent-color);
}

.speed-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.frame-counter {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  margin-left: 8px;
}
```

- [ ] **Step 1: Copy calendar and playback CSS into timeline.html**

Insert the above CSS into the `<style>` block within `{% block extra_head %}`.

- [ ] **Step 2: Verify CSS compiles**

Run: `python -c "from openrecall.client.web.app import app; print('OK')"`
Expected: `OK` (Flask app loads without template syntax errors)

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/web/templates/timeline.html
git commit -m "feat(timeline): add calendar and playback CSS styles"
```

---

## Task 2: Rewrite HTML Template Structure

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html`

Replace the content block (`{% block content %}`) with the new day-centric layout:

```html
{% block content %}
<div x-data="timelineView()" x-init="await init()" x-cloak>
  <!-- Loading Indicator -->
  <div x-show="loading" class="loading-bar" x-cloak></div>

  <!-- Date Navigation Toolbar -->
  <div class="date-nav-toolbar" style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
    <button type="button" class="today-btn" @click="goToday()" :disabled="isToday(currentDate)">
      Today
    </button>
    <button type="button" class="toolbar-nav-btn" @click="prevDay()" title="Previous day">
      &#8249;
    </button>
    <div @click.away="calendarOpen = false" style="position: relative;">
      <button type="button" class="date-picker-btn" @click="toggleCalendar()">
        <span>&#128197;</span>
        <span x-text="currentDate"></span>
        <span style="font-size: 10px; opacity: 0.6;">&#9660;</span>
      </button>
      <!-- Calendar Popover -->
      <div x-show="calendarOpen" class="calendar-popover" x-cloak style="animation: calendarPopoverIn 0.2s ease-out forwards;">
        <div class="calendar-header">
          <button type="button" class="calendar-nav" @click="prevMonth()">&#8249;</button>
          <span class="calendar-title" x-text="`${calendarYear}&#24180;${calendarMonth + 1}&#26376;`"></span>
          <button type="button" class="calendar-nav" @click="nextMonth()">&#8250;</button>
        </div>
        <div class="calendar-weekdays">
          <span>&#26085;</span><span>&#19968;</span><span>&#20108;</span><span>&#19977;</span><span>&#22235;</span><span>&#20116;</span><span>&#20845;</span>
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
      &#8250;
    </button>

    <!-- Playback Controls -->
    <div class="playback-controls">
      <button
        type="button"
        class="play-btn"
        @click="togglePlayback()"
        :disabled="frames.length <= 1"
        x-text="isPlaying ? '&#9646;&#9646;' : '&#9654;'"
        :title="isPlaying ? 'Pause' : 'Play'"
      ></button>
      <button type="button" class="speed-btn" @click="cycleSpeed()" :disabled="frames.length <= 1" x-text="playbackSpeed + 'x'" title="Playback speed"></button>
    </div>
  </div>

  <!-- No data -->
  <div x-show="!loading && frames.length === 0" class="alert" role="alert">
    No captures on <span x-text="currentDate"></span>.<br>
    <span style="font-size: 13px; color: var(--text-secondary);">Select another date to browse history.</span>
  </div>

  <!-- Timeline -->
  <div x-show="!loading && frames.length > 0">
    <div class="slider-container">
      <input type="range" class="slider" id="discreteSlider"
        x-model.number="currentIndex"
        :min="0" :max="frames.length - 1" step="1"
        :disabled="frames.length <= 1">
      <div class="slider-value">
        <span x-text="formattedTime"></span>
        <span class="frame-counter" x-show="frames.length > 0" x-text="`(${currentIndex + 1} / ${frames.length})`"></span>
      </div>
    </div>
    <div class="image-container">
      <img id="timestampImage"
        :src="currentFrame ? `${EDGE_BASE_URL}/v1/frames/${currentFrame.frame_id}` : ''"
        alt="Screenshot">
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 1: Replace content block with new markup**

- [ ] **Step 2: Verify template compiles**

Run: `python -c "from openrecall.client.web.app import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/web/templates/timeline.html
git commit -m "feat(timeline): add day navigation and playback controls HTML"
```

---

## Task 3: Implement Alpine.js Core Logic (Data Loading)

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html`

Replace the `timelineView()` function in `{% block extra_body %}` with the new implementation. Start with the core data loading and state:

```javascript
function timelineView() {
  return {
    // Data
    frames: [],
    currentIndex: 0,
    currentDate: '',
    datesWithData: new Set(),

    // Calendar
    calendarOpen: false,
    calendarYear: 0,
    calendarMonth: 0,

    // Playback
    isPlaying: false,
    playbackSpeed: 1,
    playbackTimer: null,
    BASE_INTERVAL: 1000,

    // UI
    loading: true,

    // Timers
    refreshTimer: null,

    // ---- Computed ----

    get currentFrame() {
      if (this.frames.length === 0) return null;
      return this.frames[this.currentIndex];
    },

    get formattedTime() {
      const frame = this.currentFrame;
      if (!frame) return '';
      const ts = frame.timestamp;
      if (!ts) return 'Invalid timestamp';
      const date = parseTimestamp(ts);
      if (!date || isNaN(date.getTime())) return 'Invalid timestamp';
      const y = date.getFullYear();
      const mo = String(date.getMonth() + 1).padStart(2, '0');
      const d = String(date.getDate()).padStart(2, '0');
      const h = String(date.getHours()).padStart(2, '0');
      const mi = String(date.getMinutes()).padStart(2, '0');
      const s = String(date.getSeconds()).padStart(2, '0');
      return `${y}-${mo}-${d} ${h}:${mi}:${s}`;
    },

    // ---- Date Helpers (match index.html) ----

    _formatDateStr(date) {
      const y = date.getFullYear();
      const m = String(date.getMonth() + 1).padStart(2, '0');
      const d = String(date.getDate()).padStart(2, '0');
      return `${y}-${m}-${d}`;
    },

    _utc8Now() {
      const now = new Date();
      now.setMinutes(now.getMinutes() + now.getTimezoneOffset() + 480);
      return now;
    },

    isToday(dateStr) {
      return dateStr === this._formatDateStr(this._utc8Now());
    },

    // ---- Data Loading ----

    async loadDay(date) {
      this.loading = true;
      try {
        const res = await fetch(`${EDGE_BASE_URL}/api/memories/by-day?date=${date}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (Array.isArray(data)) {
          // Sort ascending (oldest first) for timeline playback
          this.frames = data.sort((a, b) => {
            const ta = parseTimestamp(a.timestamp)?.getTime() || 0;
            const tb = parseTimestamp(b.timestamp)?.getTime() || 0;
            return ta - tb;
          });
        } else {
          this.frames = [];
        }
        this.currentIndex = 0;
      } catch (e) {
        console.error('Failed to load day:', e);
        this.frames = [];
        this.currentIndex = 0;
      } finally {
        this.loading = false;
      }
    },

    // ---- Day Navigation ----

    prevDay() {
      this.stopPlayback();
      const [y, m, d] = this.currentDate.split('-').map(Number);
      const date = new Date(y, m - 1, d);
      date.setDate(date.getDate() - 1);
      this.currentDate = this._formatDateStr(date);
      this.calendarYear = date.getFullYear();
      this.calendarMonth = date.getMonth();
      this.loadDay(this.currentDate);
    },

    nextDay() {
      this.stopPlayback();
      const [y, m, d] = this.currentDate.split('-').map(Number);
      const date = new Date(y, m - 1, d);
      date.setDate(date.getDate() + 1);
      this.currentDate = this._formatDateStr(date);
      this.calendarYear = date.getFullYear();
      this.calendarMonth = date.getMonth();
      this.loadDay(this.currentDate);
    },

    goToday() {
      this.stopPlayback();
      const now = this._utc8Now();
      this.currentDate = this._formatDateStr(now);
      this.calendarYear = now.getFullYear();
      this.calendarMonth = now.getMonth();
      this.loadDay(this.currentDate);
    },

    selectDate(date) {
      this.stopPlayback();
      this.currentDate = date;
      const [y, m] = date.split('-').map(Number);
      this.calendarYear = y;
      this.calendarMonth = m - 1;
      this.calendarOpen = false;
      this.loadDay(date);
    },

    // ---- Stubs (overridden in later tasks) ----

    stopPlayback() {},
    togglePlayback() {},
    cycleSpeed() {},
    refreshDay() {},

    // ---- Initialization (base — extended in Task 6) ----

    async init() {
      const now = this._utc8Now();
      this.currentDate = this._formatDateStr(now);
      this.calendarYear = now.getFullYear();
      this.calendarMonth = now.getMonth();
      await this.loadDay(this.currentDate);

      // Real-time refresh: every 5 seconds check for new frames
      this.refreshTimer = setInterval(() => {
        this.refreshDay();
      }, 5000);

      // Keyboard navigation
      this._keydownHandler = (e) => {
        if (e.key === 'ArrowLeft') {
          e.preventDefault();
          this.stopPlayback();
          if (this.currentIndex > 0) this.currentIndex -= 1;
        }
        if (e.key === 'ArrowRight') {
          e.preventDefault();
          this.stopPlayback();
          if (this.currentIndex < this.frames.length - 1) this.currentIndex += 1;
        }
        if (e.key === ' ') {
          e.preventDefault();
          this.togglePlayback();
        }
      };
      window.addEventListener('keydown', this._keydownHandler);

      // Cleanup on page leave
      this._beforeUnloadHandler = () => {
        this.stopPlayback();
        if (this.refreshTimer) {
          clearInterval(this.refreshTimer);
          this.refreshTimer = null;
        }
        if (this._keydownHandler) {
          window.removeEventListener('keydown', this._keydownHandler);
          this._keydownHandler = null;
        }
      };
      window.addEventListener('beforeunload', this._beforeUnloadHandler);
    }
  };
}
```

- [ ] **Step 1: Replace timelineView() with core logic**

- [ ] **Step 2: Verify template compiles**

Run: `python -c "from openrecall.client.web.app import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Start client and verify day loading works**

Start the client: `./run_client.sh --mode local --debug` (in a separate terminal)

Open browser to `http://localhost:8889/timeline`

Verify: Page loads, shows today's date, shows frames (or empty state if no data)

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/templates/timeline.html
git commit -m "feat(timeline): implement day-centric data loading"
```

---

## Task 4: Add Calendar Interaction Logic

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html`

Add calendar methods to `timelineView()`. Insert these methods after `selectDate()` and before `init()`:

```javascript
// ---- Calendar ----

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
```

- [ ] **Step 1: Add calendar methods to timelineView()**

- [ ] **Step 2: Verify template compiles**

Run: `python -c "from openrecall.client.web.app import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Browser test — verify calendar works**

With client running, open `http://localhost:8889/timeline`:

1. Click date picker button → calendar popover opens
2. Navigate months with ‹ › buttons
3. Dates with data show blue dot
4. Click a date → popover closes, loads that day's frames
5. Click Today → returns to today

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/templates/timeline.html
git commit -m "feat(timeline): add calendar interaction logic"
```

---

## Task 5: Add Real-Time Refresh

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html`

Add `refreshDay()` method to `timelineView()`. Insert after `hasData()` and before the playback methods:

```javascript
// ---- Real-Time Refresh ----

async refreshDay() {
  if (!this.isToday(this.currentDate)) return;
  try {
    const res = await fetch(`${EDGE_BASE_URL}/api/memories/by-day?date=${this.currentDate}`);
    if (!res.ok) return;
    const fresh = await res.json();
    if (!Array.isArray(fresh)) return;

    // Sort ascending (oldest first)
    fresh.sort((a, b) => {
      const ta = parseTimestamp(a.timestamp)?.getTime() || 0;
      const tb = parseTimestamp(b.timestamp)?.getTime() || 0;
      return ta - tb;
    });

    // Update existing frames by ID
    const freshById = new Map(fresh.map(e => [e.id, e]));
    for (let i = 0; i < this.frames.length; i++) {
      const frame = this.frames[i];
      if (!frame?.id) continue;
      const updated = freshById.get(frame.id);
      if (updated) {
        this.frames[i] = updated;
        freshById.delete(frame.id);
      }
    }

    // Append new frames to end
    const newFrames = Array.from(freshById.values());
    if (newFrames.length > 0) {
      this.frames.push(...newFrames);
    }
  } catch (_e) {
    // Silent fail
  }
},
```

- [ ] **Step 1: Add `refreshDay()` method to timelineView()**

- [ ] **Step 2: Verify template compiles**

Run: `python -c "from openrecall.client.web.app import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/web/templates/timeline.html
git commit -m "feat(timeline): add real-time day refresh"
```

---

## Task 6: Implement Playback Controls

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html`

Add playback methods to `timelineView()`. Insert after `refreshDay()` and before `init()`:

```javascript
// ---- Playback ----

onSliderInput() {
  // User manually dragged the slider — stop playback
  this.stopPlayback();
},

togglePlayback() {
  if (this.isPlaying) {
    this.stopPlayback();
  } else {
    this.startPlayback();
  }
},

startPlayback() {
  if (this.frames.length <= 1) return;
  if (this.currentIndex >= this.frames.length - 1) {
    // Already at the end — restart from beginning
    this.currentIndex = 0;
  }
  this.isPlaying = true;
  const interval = this.BASE_INTERVAL / this.playbackSpeed;
  this.playbackTimer = setInterval(() => {
    if (this.currentIndex >= this.frames.length - 1) {
      this.stopPlayback();
      return;
    }
    this.currentIndex += 1;
  }, interval);
},

stopPlayback() {
  this.isPlaying = false;
  if (this.playbackTimer) {
    clearInterval(this.playbackTimer);
    this.playbackTimer = null;
  }
},

cycleSpeed() {
  const speeds = [1, 2, 5, 10];
  const idx = speeds.indexOf(this.playbackSpeed);
  this.playbackSpeed = speeds[(idx + 1) % speeds.length];
  // If playing, restart with new speed
  if (this.isPlaying) {
    this.stopPlayback();
    this.startPlayback();
  }
},
```

Also add `@input="onSliderInput()"` to the slider input in the HTML (it was omitted in Task 2 because the method didn't exist yet):

```html
<input type="range" class="slider" id="discreteSlider"
  x-model.number="currentIndex"
  :min="0" :max="frames.length - 1" step="1"
  :disabled="frames.length <= 1"
  @input="onSliderInput()">
```

- [ ] **Step 1: Add playback methods to timelineView()**

- [ ] **Step 2: Replace the slider `<input>` in Task 2's HTML with the version below**

The Task 2 slider is missing both `:disabled` and `@input`. Replace the entire `<input>` element in the existing HTML with:

- [ ] **Step 3: Verify template compiles**

Run: `python -c "from openrecall.client.web.app import app; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Browser test — verify playback**

With client running, open `http://localhost:8889/timeline`:

1. Select a day with multiple frames
2. Click ▶ Play → image auto-advances, slider moves, counter updates
3. Click ⏸ Pause → stops advancing
4. Click speed button (1x → 2x → 5x → 10x → 1x) → speed changes
5. Press Spacebar → toggles play/pause
6. Press ← → → moves frame by frame, pauses playback
7. Drag slider → pauses playback
8. Let it play to last frame → auto-stops
9. On "today", wait 5s after new capture → frame count increases (real-time refresh)
10. Switch to past day → wait 5s → no refresh occurs

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/web/templates/timeline.html
git commit -m "feat(timeline): add playback controls with keyboard support"
```

---

## Task 7: Polish and Final Verification

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html`

### 6.1 Remove unused legacy CSS

Delete the `.timeline-loading` rule from the `<style>` block — it is no longer referenced (replaced by `.loading-bar` in Task 2). The remaining styles (`.slider-container`, `.slider`, `.slider-value`, `.image-container`, `.alert`) are still used by the new layout. Visually verify:

- `.slider-container` padding/margin still looks good with the new nav bar above
- `.slider-value` font size and positioning is clear
- `.image-container` max-height works well (`calc(72vh)`)

### 6.2 Verify timer cleanup on page leave

Timer cleanup is already implemented in Task 3's `init()`:
- `stopPlayback()` clears `playbackTimer`
- `beforeunload` handler clears both `playbackTimer` and `refreshTimer`

Verify in browser DevTools that navigating away from `/timeline` does not leave dangling intervals.

### 6.3 Ensure `html[data-current-view="timeline"]` CSS applies

The `layout.html` has `html[data-current-view="timeline"] a[href="/timeline"]` styling for active nav icon. Verify the Timeline icon is highlighted when on `/timeline`. This should already work (no change needed).

- [ ] **Step 1: Final browser verification checklist**

With client running, verify all of these on `http://localhost:8889/timeline`:

| # | Check | Expected |
|---|-------|----------|
| 1 | Page loads without JS errors | Console clean |
| 2 | Shows today's date in picker | Correct YYYY-MM-DD |
| 3 | Today button disabled when on today | `disabled` attribute |
| 4 | ‹ › buttons navigate days | Date changes, frames reload |
| 5 | Calendar opens/closes | Popover visibility toggles |
| 6 | Calendar month navigation works | Month/year updates |
| 7 | Dates with data have blue dot | `.has-data::after` visible |
| 8 | Selecting date loads that day | Frames update |
| 9 | Slider range matches frame index range | 0 to frames.length - 1 |
| 10 | Slider shows formatted timestamp | YYYY-MM-DD HH:MM:SS |
| 11 | Image loads for current frame | Screenshot visible |
| 12 | Play button starts playback | Images auto-advance |
| 13 | Pause button stops playback | Images stop advancing |
| 14 | Speed button cycles 1x→2x→5x→10x | Label updates, speed changes |
| 15 | Playback stops at last frame | Auto-pause, ▶ shown |
| 16 | Slider drag pauses playback | Stops when dragging |
| 17 | Arrow keys navigate frames | ← → moves frame by frame |
| 18 | Spacebar toggles playback | Play/pause |
| 19 | Switching days stops playback | Play stops, new day loads |
| 20 | Empty day shows message | "No captures on..." |
| 21 | Real-time refresh (today only) | New frames auto-append while on today |
| 22 | Real-time refresh (other day) | No refresh when viewing past day |
| 23 | Responsive layout | No horizontal scroll on mobile |
| 24 | Single-frame day | Slider and play button both disabled |
| 25 | Loading state | `loading-bar` visible while data loads |

- [ ] **Step 2: Commit final polish**

```bash
git add openrecall/client/web/templates/timeline.html
git commit -m "feat(timeline): add cleanup and finalize playback controls"
```

---

## Spec Coverage Checklist

| Spec Requirement | Task | Status |
|-----------------|------|--------|
| 日历导航栏（Today/‹/›/日期选择器） | Task 2 | ✅ |
| 日历弹出（月份导航、有数据标记、选中态） | Task 2, 4 | ✅ |
| 复用 Grid CSS 样式 | Task 1 | ✅ |
| 按天加载数据 `/api/memories/by-day`（升序排序） | Task 3 | ✅ |
| 播放/暂停按钮 | Task 2, 6 | ✅ |
| 倍速切换（1x/2x/5x/10x） | Task 2, 6 | ✅ |
| 滑块自动跟随播放 | Task 2 | ✅ |
| 播放到达最后一帧自动停止 | Task 6 | ✅ |
| 拖动滑块自动暂停 | Task 6 | ✅ |
| 键盘支持（← → 空格） | Task 6 | ✅ |
| 实时刷新（每 5 秒） | Task 5 | ✅ |
| 空状态显示 | Task 2 | ✅ |
| UTC+8 时区处理 | Task 3 | ✅ |
| 无需后端改动 | — | ✅ |

## Placeholder Scan

- No "TBD", "TODO", "implement later" found
- No "Add appropriate error handling" without specifics
- All code blocks contain complete, runnable code
- All file paths are exact
- All commands include expected output
