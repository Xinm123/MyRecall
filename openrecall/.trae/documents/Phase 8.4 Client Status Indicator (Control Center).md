## Prerequisite (Every Time)
- Before running any server/client command: `conda activate MyRecall`.

## Current State (What Exists)
- Server already exposes `client_online` via `GET /api/config` (computed from last heartbeat).
- Control Center Alpine component in [layout.html](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/templates/layout.html#L406-L481) fetches `/api/config` once in `init()` and stores the whole response in `this.config`, but:
  - `config` default object doesn’t include `client_online`.
  - There is no periodic refresh.
  - “Recording” row label is a plain text span, no indicator UI.

## Task 1 — Alpine Data & Polling
- Update the default `config` shape to include `client_online: false` so bindings are stable before the first fetch.
- Add a `refreshConfig()` method:
  - `fetch('/api/config')` → `this.config = data` → call `updateBodyClass()`.
  - On error, set `this.config.client_online = false` (keep the other toggles as-is) so the indicator falls back to Offline if the UI can’t refresh.
- In `init()`:
  - Replace the one-off fetch with `this.refreshConfig()`.
  - Add a poller: `this._pollerId = setInterval(() => this.refreshConfig(), 5000)`.
  - Add a `destroy()` hook that clears the interval if the component is ever removed.

## Task 2 — UI Indicator Next to “Recording”
- In the Popover, inside the “Recording” row, change the left label area to include a status pill:
  - If `config.client_online` is true: green dot + “Connected”.
  - Else: red dot + “Offline”.
- Add minimal CSS in the existing `<style>` block:
  - `.control-item-label-with-status { display:flex; align-items:center; gap:8px; }`
  - `.client-status { display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:500; }`
  - `.client-status-dot { width:8px; height:8px; border-radius:999px; background:... }`
  - `.client-status.online/.offline` to set dot + text colors.

## Verification (Matches Your Checklist)
- Kill Test:
  - `conda activate MyRecall`
  - Start server + client.
  - Stop the client process.
  - Wait ~15 seconds (server marks offline after 15s); within the next 5s poll, UI should flip to red “Offline”.
- Resurrection:
  - Start client again.
  - Within 5s (one poll interval), indicator should flip to green “Connected”.

## Files to Change
- [layout.html](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/templates/layout.html)
  - Alpine data + `refreshConfig()` + poller.
  - Recording row markup.
  - CSS for the dot/label.