# ADR-0006: Search Contract Alignment with Screenpipe (Vision-Only)

**Status**: Accepted
**SupersededBy**: N/A
**Supersedes**: N/A
**Scope**: target
**Date**: 2026-02-23
**Deciders**: Product Owner + Chief Architect
**Context**: Phase 3 Vision Search Parity + Phase 4 Vision Chat MVP grounding

---

## Context and Problem Statement

MyRecall-v3 needs one stable retrieval primitive for Phase 3/4, but current docs previously mixed three different claims:

1. screenpipe API behavior
2. screenpipe operator discipline
3. MyRecall target policy choices

This ADR separates them explicitly to avoid false equivalence.

---

## Decision Drivers

1. Chat MVP stability: one canonical retrieval endpoint.
2. Evidence-first correctness: bounded retrieval and traceable frame evidence.
3. Semantic alignment with screenpipe search model.
4. Explicit divergence control under vision-only pivot.

---

## Alignment Levels (Required)

- `semantic`: align query/filter/order mental model.
- `discipline`: align usage discipline (bounded time ranges, small limits).
- `divergence`: intentional product differences.

---

## Screenpipe Reference (Facts)

From screenpipe server route and DB behavior:

- `q` is optional (`Option<String>`).
- `start_time` and `end_time` are optional at API layer.
- Empty query supports browse-like retrieval behavior.

References:

- `screenpipe/crates/screenpipe-server/src/routes/search.rs`
- `screenpipe/crates/screenpipe-db/src/db.rs`

From screenpipe skills/system prompts:

- operational rule is to **always include `start_time`** to avoid broad expensive queries.

References:

- `screenpipe/apps/screenpipe-app-tauri/src-tauri/assets/skills/screenpipe-search/SKILL.md`
- `screenpipe/apps/screenpipe-app-tauri/src-tauri/src/pi.rs`

---

## Current Reality (Verified, 2026-02-24)

Current MyRecall `GET /api/v1/search` behavior:

- `q` empty/missing returns empty paginated payload.
- `start_time` is not enforced at route level.
- search engine can still merge audio FTS candidates.

References:

- `openrecall/server/api_v1.py` (`search_api`)
- `openrecall/server/search/engine.py`

---

## Decision Outcome

MyRecall keeps `GET /api/v1/search` as canonical endpoint, aligned to screenpipe at **semantic** level, with explicit MyRecall policy choices documented as **discipline/divergence**.

### Contract (Target for Phase 3+)

| Parameter | Required | Alignment Level | Notes |
|---|---:|---|---|
| `q` | No | semantic | Empty/missing means browse/feed mode |
| `start_time` (epoch float) | Yes | discipline | MyRecall policy for bounded retrieval stability |
| `end_time` (epoch float) | No | discipline | Defaults to now |
| `app_name`/`window_name`/`focused`/`browser_url` | No | semantic | Filter semantics aligned |
| `content_type` | No | divergence | Vision-only path permits `ocr` only |

### Ordering Rules

- Browse mode (`q` empty): `timestamp DESC`.
- Keyword mode (`q` non-empty): score-first, tie-break `timestamp DESC`.
- Pagination must remain stable under fixed query params.

### Intentional Divergences

1. **Vision-only MVP scope**: Search/Chat grounding excludes audio.
2. **`content_type` enforcement**: non-`ocr` may be rejected in the vision-only contract path.
3. **Time format**: MyRecall uses epoch seconds (browser-local authority -> absolute filtering), while screenpipe uses ISO timestamps.

---

## Compatibility Window (Current -> Target)

During Phase 3 migration:

1. Document current behavior as `Current (verified)`.
2. Implement target behavior behind phased convergence.
3. Keep response payload explicit for caller adaptation errors (no silent semantic fallback for invalid target-path params).

---

## Consequences

### Positive

- One retrieval contract for both Search and Chat grounding.
- Avoids doc-level ambiguity between parity and policy.
- Supports evidence-first phase gates.

### Negative

- Caller migration needed once empty-`q` behavior changes.
- Additional validation and mode handling complexity at route layer.

### Neutral

- Multi-modal search can be reconsidered only via future ADR that changes Audio Freeze scope.

---

## Rollback Conditions

Rollback to split endpoints only if:

1. Unified search contract cannot satisfy Phase 3 latency/reliability gates.
2. Compatibility burden on existing callers becomes unacceptable within planned migration window.

Any rollback must preserve evidence-first guarantees and non-fabrication policy.

---

## Related Docs

- `v3/milestones/roadmap-status.md`
- `v3/metrics/phase-gates.md`
- `v3/plan/06-vision-chat-mvp-spec.md`
