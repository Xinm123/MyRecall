# ADR-0005: Vision-Only Chat Pivot + Audio Freeze

**Status**: Accepted
**SupersededBy**: N/A
**Supersedes**: ADR-0004 (for MVP critical path)
**Scope**: target

**Date**: 2026-02-23

**Deciders**: Product Owner + Chief Architect

**Context**: MyRecall-v3 roadmap scope lock and Chat MVP definition

---

## Context and Problem Statement

MyRecall-v3 originally planned a multi-modal (vision + audio) path with audio parity work (Phase 2.1) gating downstream Phase 3 (search) and Phase 4 (chat). This created two problems:

1. **Roadmap contradiction**: Chat is the core user-facing value, but the critical path was dominated by audio parity work.
2. **Unclear evidence requirements**: Without a strict evidence contract, Chat risks producing plausible-sounding but unverifiable answers.

The project needs a scope lock that produces an executable roadmap and unblocks an end-to-end Chat MVP.

---

## Decision Drivers

1. **Chat-first user value**: Ship an evidence-based chat loop users can trust.
2. **Scope control**: Avoid multi-modal complexity and large privacy surface area expansion.
3. **Screenpipe alignment**: Align interaction model and time-filter semantics where feasible.
4. **Deployment critical path**: Preserve remote-first API foundations for Phase 5.
5. **Non-hallucinated evidence**: Every answer must cite real frames, not invented references.

---

## Considered Options

### Option A: Multi-Modal Parity Before Search/Chat (Previous Plan)

- **Description**: Complete Phase 2.1 audio parity work (screenpipe-aligned) before Phase 3/4.
- **Pros**:
  - Strong modality coverage (vision + audio) and future-proofing
  - Downstream search/chat can rely on richer data
- **Cons**:
  - High complexity and schedule risk
  - Larger privacy surface area
  - Delays the first trustworthy Chat demo

### Option B: Vision-Only Chat MVP (Chosen)

- **Description**: Redefine Phase 3/4 around vision-only search + evidence-first chat. Freeze all audio work.
- **Pros**:
  - Fastest path to a trustworthy Chat MVP
  - Smaller privacy surface area
  - Clear acceptance criteria (time-range summary + evidence[])
- **Cons**:
  - Use cases that depend on audio become invalid (must be rewritten or deferred)
  - Requires explicit product messaging: “vision-only evidence”

### Option C: Vision-First + Minimal Audio Read-Only

- **Description**: Keep audio capture, but treat audio as display-only and do not integrate into search/chat.
- **Pros**:
  - Preserves some audio value without full parity work
- **Cons**:
  - Still expands privacy and operational complexity
  - Creates confusion: “audio exists but chat can’t use it”

---

## Decision Outcome

**Chosen Option: Option B (Vision-Only Chat MVP + Audio Freeze)**

### What is Locked

1. **Vision-only scope for Search/Chat**
   - Allowed sources: video frames + OCR text + metadata (`app_name`, `window_name`, `focused`, `browser_url`)
   - Disallowed sources: audio transcriptions, speaker identity, UI/input events

2. **Audio Freeze**
   - Pause all audio development (capture/storage/search parity/chat integration).
   - Existing Phase 2.0/2.5 code and docs can remain, but are not on the MVP critical path.

3. **Evidence-first Chat**
   - When chat references user activity or specific moments, include `evidence[]` with real, retrievable frame references.
   - Pure how-to/explanation replies may omit evidence (or return `evidence=[]`), but must never fabricate IDs/timestamps.

4. **Time semantics aligned with screenpipe**
   - Authority: user local timezone (browser) defines time ranges.
   - Implementation: UI converts to epoch seconds and server filters by absolute time (no timezone inference on server).

---

## Screenpipe Reference (Alignment Notes)

This decision mirrors screenpipe’s proven approach:

- **Mention/time parsing (client-side local time)**:
  - `screenpipe/apps/screenpipe-app-tauri/lib/chat-utils.ts` (`parseMentions`)
- **Dynamic system prompt injection (current time + timezone + local time)**:
  - `screenpipe/apps/screenpipe-app-tauri/components/standalone-chat.tsx` (`buildSystemPrompt`)
- **Search API accepts bounded time filters**:
  - `screenpipe/crates/screenpipe-server/src/routes/search.rs` (`start_time/end_time` as `DateTime<Utc>`)

MyRecall can align on *semantics* without matching the exact parameter format (MyRecall uses epoch seconds; screenpipe uses ISO-8601 UTC).

---

## Consequences

### Positive ✅

- Unblocks Phase 4 Chat MVP quickly with a trustworthy evidence contract
- Removes Phase 2.1 audio parity from the critical path
- Makes roadmap executable and reduces schedule risk

### Negative ❌

- Audio-dependent scenarios (meetings, “what did I say”) are out of scope
- Some “screenpipe parity” items must be deferred or reinterpreted under vision-only constraints

### Neutral 🔄

- Audio can be revisited later as a separate scope decision with explicit privacy + quality gates

---

## Implementation Notes (Docs + Engineering)

- Update planning docs to reflect the pivot:
  - `MyRecall/v3/plan/00-master-prompt.md`
  - `MyRecall/v3/milestones/roadmap-status.md`
  - `MyRecall/v3/webui/pages/search.md`
  - `MyRecall/v3/webui/pages/timeline.md`
- Phase 3 should harden vision retrieval/search with strict time bounds (avoid unbounded scans).
- Phase 4 should implement “system prompt + skill-style tooling” with server-side validation to prevent fabricated evidence.

---

## Propagation Checklist

The following document sync actions are required by this ADR and tracked explicitly:

- [x] `v3/plan/00-master-prompt.md` updated to vision-only + audio freeze.
- [x] `v3/milestones/roadmap-status.md` updated with pivot and superseded decision log.
- [x] `v3/metrics/phase-gates.md` updated with Phase 3/4 vision-only gates.
- [x] `v3/decisions/ADR-0006-screenpipe-search-contract.md` published for the search contract lock.
- [x] `v3/plan/06-vision-chat-mvp-spec.md` published for Phase 4 grounding strategy.
- [x] `v3/webui/pages/search.md` and `v3/webui/pages/timeline.md` updated to reflect pivot semantics.

Checklist owner: Product Owner + Chief Architect. Any unchecked item blocks claiming pivot convergence complete.

---

## Validation

**Primary MVP Gate**:
- Chat answers: “总结一下我今天 14:00-17:00 做了什么”
- Output includes `evidence[]` with real `frame_id + timestamp + frame_url`
- Times are displayed in user local timezone; server receives epoch seconds for filtering

**Failure Signals** (trigger re-evaluation):
- Evidence cannot be traced to real frames (fabrication)
- Queries require unbounded scanning to find relevant results
- Timezone-related confusion or inconsistent time ranges across devices
