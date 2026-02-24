# ADR-0006: Screenpipe-Aligned Search Contract (Vision-Only)

**Status**: Accepted
**SupersededBy**: N/A
**Supersedes**: N/A
**Scope**: target
**Date**: 2026-02-23
**Deciders**: Product Owner + Chief Architect
**Context**: Phase 3 Vision Search Parity + Phase 4 Vision Chat MVP grounding

---

## Context and Problem Statement

MyRecall-v3 Phase 4 Chat MVP requires a **bounded, stable, and screenpipe-like** retrieval primitive to ground answers in real screen evidence.

Current MyRecall `/api/v1/search` behavior is not aligned with screenpipe in two critical ways:

1. `q`-first semantics (browse/feed mode not first-class) make it hard to implement “time-range summary” without extra endpoints.
2. Time bounds are not enforced as a hard constraint, risking unbounded scans and flaky latency.

We need a clear, locked Search API contract that:

- Can be used directly by Chat grounding in Phase 4 (single retrieval)
- Mirrors screenpipe’s `/search` mental model as closely as possible
- Stays within the vision-only pivot (Audio Freeze)

---

## Decision Drivers

1. **Chat MVP stability**: least moving parts (single retrieval + single summary).
2. **Screenpipe alignment**: reduce semantic drift; copy interaction expectations.
3. **Evidence-first**: chat claims must be traceable to real frame IDs and timestamps.
4. **Performance safety**: avoid unbounded scans; stable ordering + pagination.
5. **Vision-only pivot**: OCR-only contract; audio excluded from Search/Chat scope.

---

## Considered Options

### Option A: Keep current `/api/v1/search` (q required) + add separate browse endpoint

- **Pros**: minimal change to existing behavior
- **Cons**: two retrieval primitives; increases Phase 4 bug surface; diverges from screenpipe

### Option B: Make `/api/v1/search` screenpipe-like (Chosen)

- **Pros**: one canonical retrieval primitive; matches screenpipe’s `/search` mental model; easiest Phase 4 grounding
- **Cons**: requires tightening contract (q optional, time bounds required); may require compatibility handling

### Option C: Build Phase 4 Chat on timeline/frames APIs directly (no search)

- **Pros**: could avoid touching search
- **Cons**: loses screenpipe alignment; reinvents browse semantics; higher engineering complexity for Phase 4 sampling

---

## Decision Outcome

**Chosen Option: Option B**

MyRecall will treat `GET /api/v1/search` as the canonical, screenpipe-aligned vision retrieval endpoint.

Phase 4 Chat grounding will use **search browse/feed mode** (`q=""`) over a bounded time range, then sample/truncate before calling the LLM once.

---

## Contract (Phase 3+)

### Endpoint

- `GET /api/v1/search`

### Parameters (screenpipe-aligned semantics)

| Parameter | Type | Required | Semantics |
|---|---:|---:|---|
| `start_time` | float (epoch seconds) | Yes | Start of time window (browser-local authority; server filters absolute) |
| `end_time` | float (epoch seconds) | No | End of time window; default = now |
| `q` | string | No | Keywords; empty/missing means browse/feed mode |
| `content_type` | string | No | Vision-only: only `ocr` is allowed. Any non-`ocr` value MUST return `400 Bad Request`. |
| `limit` | int | No | Page size (bounded; prefer 5-20) |
| `offset` | int | No | Pagination offset |
| `app_name` | string | No | Filter by app substring |
| `window_name` | string | No | Filter by window title substring |
| `focused` | bool | No | Filter by focused windows |
| `browser_url` | string | No | Filter by browser URL substring |

### Ordering Rules

- If `q` is missing or empty:
  - browse/feed mode
  - order by `timestamp DESC`
- If `q` is non-empty:
  - rank results by search score
  - tie-break by `timestamp DESC` for stability

Pagination MUST be stable under both modes (no duplicates/gaps across pages with identical query parameters).

### Compatibility Window (Current -> Target)

- Transition period: Phase 3 implementation window.
- During transition, if `content_type` is omitted, server defaults to `ocr`.
- During transition, non-`ocr` `content_type` values MUST be rejected with `400` and a clear error payload.
- No silent ignore mode is allowed, to prevent ambiguous caller behavior.

### Response Expectations (minimum fields for Phase 4)

Each OCR result MUST include enough fields to render evidence and enable drill-down:

- `frame_id`
- `timestamp` (epoch seconds)
- `app_name`, `window_name`, `focused`, `browser_url`
- `ocr_snippet` (short, safe to display)
- `frame_url` (e.g. `/api/v1/frames/:id`)

---

## Screenpipe Reference (How it Does It)

Screenpipe’s `/search` endpoint:

- accepts `q` as optional (`q: Option<String>`)
- supports time bounds and filters (app/window/focused/browser_url)
- supports browse behavior when query is empty (returns OCR ordered by timestamp)

Repo references (for semantics, not code reuse):

- `screenpipe/crates/screenpipe-server/src/routes/search.rs`
- `screenpipe/apps/screenpipe-app-tauri/src-tauri/assets/skills/screenpipe-search/SKILL.md` (explicit rule: ALWAYS include `start_time`)

Key intentional differences:

- Screenpipe uses ISO-8601 UTC strings; MyRecall uses epoch seconds for browser-local authority.
- Screenpipe supports multi-modal `content_type`; MyRecall Phase 3/4 is vision-only (`ocr`).

---

## Consequences

### Positive ✅

- One canonical retrieval primitive for Phase 3 Search and Phase 4 Chat
- Strong semantic alignment with screenpipe’s bounded search discipline
- Enables Phase 4 “single retrieval + single summary” grounding with minimal orchestration

### Negative ❌

- Requires tightening `/api/v1/search` behavior (q optional + time bounds required)
- May need compatibility handling for any callers that assumed `q` is required

### Neutral 🔄

- Multi-modal search can be revisited later only if Audio Freeze is lifted by a new ADR

---

## Rollback Conditions

Rollback to Option A (separate browse endpoint) only if:

- Enforcing time bounds breaks an important legacy caller and cannot be adapted quickly, or
- Search performance/regressions cannot be stabilized within Phase 3 gates

Rollback must preserve evidence-first guarantees (never fabricate frame references).

---

## Related Docs

- `v3/milestones/roadmap-status.md` (Phase 3/4 tracker)
- `v3/metrics/phase-gates.md` (authority for Phase 3/4 gates)
- `v3/plan/06-vision-chat-mvp-spec.md` (Phase 4 grounding + sampling)
