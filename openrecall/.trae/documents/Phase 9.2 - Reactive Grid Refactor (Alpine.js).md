## Prerequisite
- Before starting server/client/tests, always run: `conda activate MyRecall`.

## Feasibility Analysis
- Alpine.js is already included globally in [layout.html](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/templates/layout.html#L8-L10), so no new dependency is needed.
- Flask’s `|tojson` filter is already used in [timeline.html](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/templates/timeline.html#L81-L84), so JSON injection is supported.
- **Key blocker to handle**: `/` currently passes `RecallEntry` objects (with `embedding` as numpy/bytes). `{{ entries|tojson }}` is very likely to fail or bloat the payload. Solution: serialize entries into plain dicts in `app.py` including only grid fields.
- Current modal JS snapshots DOM nodes at load; it won’t include newly inserted items. Solution: move modal state into Alpine so it always uses `entries[]`.

## Final User-Facing Effect
- Grid looks the same as today but is rendered via Alpine (`x-for`).
- Every ~5 seconds it polls `/api/memories/latest?since=...` and prepends new items to top-left.
- Keeping the page open while the client captures screenshots: new images appear automatically without refresh.
- Modal (prev/next, escape, arrow keys) works for both existing and newly added items.

## Implementation Plan

### 1) Backend: Make Initial Entries JSON-Safe (app.py)
- In the `/` route, convert `RecallEntry` objects into dicts (exclude `embedding`).
- Include fields:
  - `id, timestamp, app, title, description, status`
  - `filename: f"{timestamp}.png"`
- Pass this list to the template as `entries`.

### 2) Data Injection (index.html)
- Inject initial state:
  - `window.initialEntries = {{ entries | tojson | safe }};`
- Inject only the needed config (avoid dumping full `settings`):
  - `window.initialConfig = { show_ai_description: {{ settings.show_ai_description | tojson }} };`

### 3) Alpine Component (index.html)
- Add `x-data="memoryGrid()" x-init="init()"` on the main wrapper.
- Implement `memoryGrid()`:
  - `entries`, `config`
  - `lastCheck` initialized to max timestamp from initial entries (or 0)
  - `checkNew()` fetches `/api/memories/latest?since=${this.lastCheck}`, prepends new items, updates `lastCheck` to max seen
  - Helpers: `formatTime(ts)`, `imageSrc(entry)`, `stats()`

### 4) Replace Jinja Loop with x-for (index.html)
- Replace `{% for entry in entries %}` with `x-for` templates and translate:
  - app/time/image bindings
  - footer status logic using `x-if` (`PROCESSING`, `PENDING`, AI description, fallback)
- Bind stats bar values to `stats()`.

### 5) Modal Refactor (index.html)
- Replace current modal JS with Alpine state:
  - `selectedIndex` + `openAt/closeModal/prev/next`
  - Modal image/meta bound to `entries[selectedIndex]`
  - Keyboard navigation via `@keydown.window.*`

## Verification
- Refresh `/` and confirm identical rendering.
- Keep page open; run client capture; confirm new card appears top-left without refresh.
- Confirm modal works for newly inserted cards too.