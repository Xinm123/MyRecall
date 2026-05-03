# Timeline Navigation Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add carousel-style prev/next frame navigation buttons on the timeline image viewer.

**Architecture:** Pure frontend UI change within a single Jinja2 template. Two overlay buttons (left/right) inside `.image-container`, styled as semi-transparent circular arrows that appear/hide based on `currentIndex` boundary. Alpine.js methods `goPrev()` and `goNext()` reuse existing `stopPlayback()` + `currentIndex` logic.

**Tech Stack:** HTML/CSS (Jinja2 template), Alpine.js, no backend changes.

---

### File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `openrecall/client/web/templates/timeline.html` | Modify | Add CSS, HTML buttons, JS methods |

---

### Task 1: Add CSS for Navigation Arrows

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html` (inside `<style>` block)

- [ ] **Step 1: Add navigation arrow CSS classes**

  Insert the following CSS after the `.image-container .delete-btn:hover` rule (around line 433):

  ```css
  /* Navigation arrows on timeline image */
  .nav-arrow {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: none;
    background: rgba(0, 0, 0, 0.35);
    color: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    z-index: 5;
    padding: 0;
    line-height: 1;
  }

  .nav-arrow:hover {
    background: rgba(0, 0, 0, 0.6);
    transform: translateY(-50%) scale(1.1);
  }

  .nav-arrow svg {
    display: block;
  }

  .nav-arrow-left {
    left: 12px;
  }

  .nav-arrow-right {
    right: 12px;
  }
  ```

- [ ] **Step 2: Verify CSS is syntactically valid**

  Run: `python -c "from bs4 import BeautifulSoup; soup = BeautifulSoup(open('openrecall/client/web/templates/timeline.html').read(), 'html.parser'); print('Style block found:', bool(soup.find('style')))"`

  Expected output: `Style block found: True`

---

### Task 2: Add HTML Navigation Buttons

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html` (inside `.image-container` div, around line 693-704)

- [ ] **Step 1: Insert prev/next buttons inside .image-container**

  In `timeline.html`, find the existing `.image-container` div (around line 693). After the existing delete button (`class="delete-btn"`) and before the `<img>` tag, insert two new buttons:

  ```html
    <!-- Previous frame button -->
    <button
      type="button"
      class="nav-arrow nav-arrow-left"
      title="Previous frame"
      aria-label="Previous frame"
      @click.stop="goPrev()"
      x-show="frames.length > 1 && currentIndex > 0"
      x-cloak
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    </button>

    <!-- Next frame button -->
    <button
      type="button"
      class="nav-arrow nav-arrow-right"
      title="Next frame"
      aria-label="Next frame"
      @click.stop="goNext()"
      x-show="frames.length > 1 && currentIndex < frames.length - 1"
      x-cloak
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
    </button>
  ```

  **Do NOT modify** the existing delete button or `<img>` tag.

- [ ] **Step 2: Verify template parses correctly**

  Run: `python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('openrecall/client/web/templates')); env.get_template('timeline.html')"`

  Expected: No error output.

---

### Task 3: Add JavaScript Navigation Methods

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html` (inside Alpine.js component)

- [ ] **Step 1: Add goPrev() and goNext() methods**

  In the `timelineView()` returned object, locate `stopPlayback()` (around line 1027). Add a comma after its closing `},` then insert the two new methods:

  ```javascript
  stopPlayback() {
    this.isPlaying = false;
    if (this.playbackTimer) {
      clearInterval(this.playbackTimer);
      this.playbackTimer = null;
    }
  },          // ← ensure comma here

  goPrev() {
    this.stopPlayback();
    if (this.currentIndex > 0) {
      this.currentIndex -= 1;
    }
  },

  goNext() {
    this.stopPlayback();
    if (this.currentIndex < this.frames.length - 1) {
      this.currentIndex += 1;
    }
  },          // ← add comma here; next method follows
  ```

  **Critical:** Each method in a JS object literal must be followed by a comma, including the last one if more methods follow. Verify that `goNext()` ends with `,` and the next existing method (`selectSpeed`) begins immediately after.

- [ ] **Step 2: Verify the methods are reachable**

  Check that the methods are siblings to `stopPlayback` within the returned object, not nested inside another method.

---

### Task 4: Manual Verification

**Files:**
- Modify: None (verification only)

- [ ] **Step 1: Start local servers**

  Terminal 1: `./run_server.sh --mode local`
  Terminal 2: `./run_client.sh --mode local`

- [ ] **Step 2: Open timeline in browser**

  Navigate to `http://localhost:8889/timeline`

- [ ] **Step 3: Verify button visibility**

  - [ ] When on the first frame, left arrow is hidden; right arrow is visible
  - [ ] When on the last frame, right arrow is hidden; left arrow is visible
  - [ ] When there is only 1 frame, both arrows are hidden
  - [ ] When there are no frames, both arrows are hidden

- [ ] **Step 4: Verify button functionality**

  - [ ] Click right arrow advances to next frame; slider moves; time updates
  - [ ] Click left arrow goes to previous frame; slider moves; time updates
  - [ ] During playback, clicking either arrow stops playback AND navigates
  - [ ] After deleting the last frame, Next arrow disappears automatically
  - [ ] After deleting frame 0 with only 2 frames total, Prev arrow disappears
  - [ ] After deleting a middle frame, both Prev and Next remain visible

- [ ] **Step 5: Verify visual appearance**

  - [ ] Arrows appear as 40px circles centered vertically on image
  - [ ] Left arrow positioned 12px from left edge; right arrow 12px from right edge
  - [ ] Default opacity is subtle but visible; hover makes them more prominent
  - [ ] Arrows do not overlap delete button at any window width
  - [ ] Works in both light and dark mode

---

### Task 5: Commit

- [ ] **Step 1: Commit the changes**

  ```bash
  git add openrecall/client/web/templates/timeline.html
  git commit -m "feat(ui/timeline): add prev/next frame navigation buttons

  Add carousel-style arrow buttons on left/right sides of the timeline
  image viewer. Clicking navigates to previous/next frame and stops
  playback. Buttons hide at boundary frames (first/last).

  - CSS: .nav-arrow, .nav-arrow-left, .nav-arrow-right
  - Alpine.js: goPrev(), goNext() methods
  - Visibility: x-show based on currentIndex and frames.length"
  ```

---

## Self-Review

**Spec coverage:**
- ✅ Carousel-style overlay buttons on image sides — Task 2
- ✅ 40px circle shape, semi-transparent, hover brightens — Task 1
- ✅ Prev/Next with boundary hiding — Task 2 (x-show) + Task 4 verification
- ✅ Stops playback on click — Task 3 (goPrev/goNext call stopPlayback)
- ✅ Delete button coexistence (right:12px vs delete top:12px right:12px) — Task 1 + Task 4
- ✅ Keyboard shortcuts unchanged — no changes needed

**Placeholder scan:** No TBD, TODO, or vague steps. All code is provided. No "implement later" references.

**Type consistency:** `currentIndex` and `frames` are the same properties used throughout the existing template. `stopPlayback()` is the existing method called by keyboard handler and slider input.

**Frontend testing:** No existing JavaScript test infrastructure in this project. This frontend-only change relies on manual verification (Task 4).
