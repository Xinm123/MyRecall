# MyRecall v3 Chat Implementation Phases

## Purpose

This document defines the recommended implementation order for the reduced MyRecall v3 chat MVP.

It is intentionally phase-oriented rather than task-oriented.

It exists to answer:

- what should be built first
- what must be validated before the next phase starts
- which parts of the system are prerequisites for later chat capabilities

This document does not replace `docs/v3/chat/mvp.md`.

- `mvp.md` defines the target MVP behavior and contracts
- this document defines the recommended rollout sequence

## Document Boundaries

This document answers:

- what should be implemented first
- what depends on what
- what should be validated before the next phase begins

This document does not try to be the detailed implementation checklist.

The intended split is:

- `docs/v3/chat/mvp.md`
  - target behavior, contracts, and scope
- `docs/v3/chat/implementation-phases.md`
  - rollout order, dependencies, and phase-level milestones
- `docs/superpowers/plans/*.md`
  - task-level execution detail

## Out Of Scope For This Document

This document does not define:

- exact task checklists
- file-by-file implementation steps
- test-by-test instructions
- low-level API payload details beyond what is needed to explain phase ordering

Those details should live in the implementation plan and the MVP spec.

## Guiding Principle

The implementation order should follow the data plane, not the UI surface.

In particular:

- accessibility acquisition must be stabilized before downstream search and summary APIs
- persistence semantics must be stable before chat-facing tools are exposed
- observability must exist before optimization work is attempted

## Critical Path

The critical path for this MVP is the accessibility-first data plane:

```text
Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6
```

This path establishes:

- client-side accessibility contracts
- capture-time AX eligibility and adoption
- bounded focused-window AX collection
- accessibility-complete ingest behavior
- durable accessibility-backed search and summary inputs

Phases 7-10 are consumers of that stabilized foundation.

## Phase 0: Freeze Contracts

### Objective

Lock the MVP contracts before implementation starts.

### Depends on

- none

### Includes

- accessibility acquisition scope
- accessibility-canonical metadata contract
- ingest split semantics
- `frames`, `accessibility`, and `elements` roles
- search, summary, and frame-context contracts
- reason vocabulary for AX decisions

### Exit Criteria

- `docs/v3/chat/mvp.md` is accepted as the active MVP spec
- no unresolved contract ambiguity remains around accessibility acquisition or persistence

### Observable Milestone

- the MVP scope, accessibility semantics, and ingest split can be explained without referring back to older chat documents

## Phase 1: Reset Schema To MVP Shape

### Objective

Prepare the database for the new chat-oriented data model.

### Depends on

- Phase 0

### Includes

- `frames.text`
- `frames.accessibility_tree_json`
- metadata-only `frames_fts`
- frame-backed `accessibility + accessibility_fts`
- internal `elements`

### Why This Comes Early

All later client and server work depends on stable persistence targets.

### Exit Criteria

- the schema matches the MVP document
- no legacy `accessibility_text` dependency remains in the base schema

### Observable Milestone

- a fresh database contains the new `frames`, `accessibility`, `elements`, and FTS layout with no compatibility fields required for old chat assumptions

## Phase 2: Introduce Client-side Accessibility Contracts And Policy

### Objective

Add the accessibility subsystem boundaries before adding real platform collection.

### Depends on

- Phase 0
- Phase 1

### Includes

- `TreeWalkerConfig`
- `TreeSnapshot`
- `AccessibilityTreeNode`
- `AccessibilityDecision`
- focused-monitor AX eligibility rules
- terminal-class `app_prefers_ocr` rules
- debug log and dump contract

### Why This Comes Early

The system should know how to reason about accessibility before it knows how to collect it.

### Exit Criteria

- the client-side accessibility types are stable
- policy decisions are deterministic and testable
- debug output shape is defined

### Observable Milestone

- policy evaluation and debug payloads can be exercised without a real AX walker implementation

## Phase 3: Insert Accessibility Decision Stage Into Capture Flow

### Objective

Add the accessibility decision stage into the client capture pipeline without yet relying on real AX adoption for server-side completion.

### Depends on

- Phase 2

### Includes

- capture order is explicitly:
  - screenshot
  - active context
  - accessibility decision
  - metadata build
  - metadata merge (placeholder in Phase 3, enabled in Phase 5)
  - enqueue
- recorder integration points are established
- eligibility and rejection reasons become visible in logs/debug dumps

### Why This Comes Before Walker Adoption

It validates routing, monitor ownership, and hot-path placement before real AX payloads start changing persistence behavior.

### Recommended Transitional State

Phase 3 should introduce the accessibility decision stage with a stable service interface before a real walker is required.

Recommended transitional behavior:

- the recorder calls a stable `collect_for_capture(...)` entrypoint
- policy-based rejections already work:
  - `non_focused_monitor`
  - `app_prefers_ocr`
- the non-rejected path may still return a non-adopted placeholder result while the real walker is not yet implemented
- decision logs and debug dumps are already emitted
- no accessibility-canonical payload is uploaded yet
- server ingest behavior remains unchanged in this phase

### Exit Criteria

- non-focused monitor captures are rejected from AX cleanly
- terminal-class apps are rejected from AX cleanly
- capture still completes normally when AX collection is skipped or unavailable

### Observable Milestone

- capture logs clearly show AX eligibility and rejection reasons while the existing screenshot/enqueue pipeline remains stable

## Phase 4: Implement Bounded Focused-window Accessibility Collection

### Objective

Implement the first real macOS accessibility walker for focused-window snapshots.

### Depends on

- Phase 2
- Phase 3

### Includes

- focused-window lookup
- bounded tree walk
- text-bearing role extraction
- `value -> title -> description` priority
- best-effort `bounds`
- best-effort browser URL extraction

For the first MVP, browser URL extraction means:

- treat app names containing `safari` or `chrome` as browser candidates
- attempt `AXDocument` only
- do not add browser-specific fallback strategies yet
- flat depth-first text-node list output
- `text_content`, `content_hash`, and `simhash`

### Boundaries

- focused window only
- no desktop-wide accessibility state
- no independent tree walker
- no complete raw-tree serialization

### Recommended Transitional State

Phase 4 should replace the Phase 3 placeholder path with a real focused-window walker, but should still prioritize local validation before server-side canonical completion.

Recommended transitional behavior:

- eligible captures run the real focused-window walker
- `TreeSnapshot` output is observable locally through logs and debug dumps
- accessibility adoption decisions become real (`adopted_accessibility`, `empty_text`, `no_focused_window`)
- recorder-side metadata merge can still remain disabled until Phase 5 if needed
- server ingest does not need to change during the earliest part of this phase

### Exit Criteria

- at least one known-good app yields usable `TreeSnapshot` output
- empty or failed snapshots degrade cleanly
- hot-path timing exists for AX collection

### Observable Milestone

- debug dumps contain real focused-window `TreeSnapshot` data with measurable `ax_walk_ms`, node counts, and truncation state

## Phase 5: Promote Accessibility Snapshots Into Canonical Ingest Completion

### Objective

Allow accessibility-complete frames to finish during ingest instead of waiting for OCR.

### Depends on

- Phase 1
- Phase 4

### Includes

- canonical accessibility metadata payload upload
- ingest validation for accessibility-canonical payloads
- one-transaction `complete_accessibility_frame(...)` that writes:
  - `frames.text`, `frames.text_source='accessibility'`
  - `frames.accessibility_tree_json`
  - `accessibility` row
  - `elements` rows with `parent_id` and `sort_order` derivation
- degradation to OCR-pending when accessibility payload is invalid

### Why This Is A Separate Phase

Accessibility collection and accessibility adoption should not be introduced at the same time. Collection quality should be understood first.

### Exit Criteria

- valid accessibility-canonical frames complete during ingest with all tables populated
- invalid AX payloads degrade safely to OCR-pending
- no duplicate or partial accessibility persistence appears

### Observable Milestone

- a captured frame with adopted AX data is immediately persisted as `completed` with matching `frames`, `accessibility`, and `elements` rows

## Phase 6: Expose Query Helpers For Chat APIs

### Objective

Provide read-side query methods for accessibility-persisted data, enabling summary and frame context APIs.

### Depends on

- Phase 5

### Includes

- query helpers for activity summary (`get_activity_summary_apps`, `get_activity_summary_recent_texts`)
- query helper for frame context (`get_frame_context`)
- validation that persisted `elements` rows are correctly queryable

### Why This Comes Before Chat APIs

Chat APIs should consume a stable query interface rather than directly querying tables.

### Exit Criteria

- query helpers return correct data for accessibility-complete frames
- summary and frame context APIs can use these helpers

### Observable Milestone

- `get_activity_summary_recent_texts` returns text from `elements` table
- `get_frame_context` returns parsed nodes from `accessibility_tree_json`

## Phase 7: Upgrade /v1/search To Content-Type Aware

### Objective

Upgrade the search endpoint to support OCR, accessibility, and merged search modes.

### Depends on

- Phase 5 (accessibility-canonical frames with text_source)

### Includes

- `GET /v1/search` with `content_type = ocr | accessibility | all`
- Split SearchEngine into content-type-specific paths
- Typed union response entries
- `all` search ordering and non-duplication semantics

### Why This Phase

Search is the primary chat tool and should be delivered first. The current OCR-only search is insufficient for accessibility-canonical frames.

### Exit Criteria

- `content_type=ocr` returns only OCR frames
- `content_type=accessibility` returns only accessibility frames
- `content_type=all` merges both without duplication
- Ordering follows mvp.md specification

### Observable Milestone

- `/v1/search?content_type=all&q=hello` returns mixed results with correct pagination

## Phase 8: Add /v1/activity-summary

### Objective

Provide activity overview for chat agents.

### Depends on

- Phase 6 (query helpers for activity summary)
- Phase 7 (search endpoint pattern established)

### Includes

- `GET /v1/activity-summary`
- Apps aggregation from completed frames
- Recent texts from accessibility elements
- Audio summary as empty shell

### Why This Phase

Activity summary gives chat agents a broad overview before targeted search. It depends on elements table population from Phase 6.

### Exit Criteria

- Returns apps with frame counts and approximate minutes
- Returns recent_texts from accessibility elements
- Returns audio_summary as shape-compatible empty shell

### Observable Milestone

- `/v1/activity-summary?start_time=...&end_time=...` returns valid payload matching mvp.md contract

## Phase 9: Add /v1/frames/{id}/context

### Objective

Provide detailed frame context for chat grounding.

### Depends on

- Phase 5 (accessibility_tree_json persistence)
- Phase 6 (get_frame_context query helper)

### Includes

- `GET /v1/frames/{id}/context`
- Node parsing from accessibility_tree_json
- URL extraction from link-like nodes and text
- OCR fallback when accessibility unavailable

### Why This Phase

Frame context is the main evidence layer for chat answers. It should come after search and summary are available.

### Exit Criteria

- Returns text, nodes, urls, text_source for accessibility frames
- Falls back to OCR data when accessibility unavailable
- Node filtering and URL extraction match screenpipe behavior

### Observable Milestone

- `/v1/frames/123/context` returns parsed accessibility nodes with extracted URLs

## Phase 10: Validate Accessibility Coverage And Performance

### Objective

Decide whether the Python accessibility implementation is sufficient for MVP.

### Depends on

- Phase 4
- Phase 5
- Phase 6
- Phase 7
- Phase 8
- Phase 9

### Includes

- capture hot-path timing review
- AX decision reason review
- timeout and truncation review
- multi-monitor focused/non-focused verification
- terminal OCR-preference verification

### Success Signals

- acceptable AX walk latency
- acceptable total capture latency
- low timeout rate
- low unexpected empty-text rate on supported apps

### Decision Gate

Only after this phase should the project decide whether to:

- keep the Python walker as-is
- optimize the Python implementation
- or replace the walker with a lower-level helper

### Observable Milestone

- the team has real evidence about supported apps, latency, truncation, and timeout behavior rather than assumptions

## Recommended Sequence Summary

```text
Phase 0   Freeze contracts
Phase 1   Reset schema
Phase 2   Add accessibility types/policy/debug contracts
Phase 3   Insert accessibility decision stage into capture flow
Phase 4   Implement bounded focused-window walker
Phase 5   Promote accessibility-complete ingest path
Phase 6   Persist accessibility into queryable planes
Phase 7   Upgrade /v1/search to content-type aware
Phase 8   Add /v1/activity-summary
Phase 9   Add /v1/frames/{id}/context
Phase 10  Validate coverage and performance
```

## Notes

- Accessibility acquisition is the critical path for the MVP.
- Downstream APIs should be treated as consumers of a stabilized accessibility-aware data plane.
- Optimization should follow observability, not precede it.
