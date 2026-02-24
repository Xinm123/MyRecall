# ADR-0007: Phase 2.6 Audio Freeze Governance

**Status**: Accepted  
**SupersededBy**: N/A  
**Supersedes**: N/A  
**Scope**: target

**Date**: 2026-02-24  
**Updated**: 2026-02-24 (semantic upgrade: governance-only -> governance + default full-chain pause)

**Deciders**: Product Owner + Chief Architect

**Context**: MyRecall-v3 roadmap hardening between Phase 2.5 and Phase 2.7

---

## Context and Problem Statement

Audio Freeze has been documented, but the old Phase 2.6 semantics were still governance-heavy and behavior-light:

1. Freeze semantics were inconsistent across roadmap, gates, and WebUI docs.
2. Default behavior boundaries were unclear (capture/processing/UI/search/chat).
3. Existing docs allowed mixed interpretations such as "freeze is active but audio still default-visible."

The project needs a decision-complete, auditable contract that keeps "Current (verified)" and "Target (contract)" separated while locking a stable MVP boundary.

---

## Decision Drivers

1. **Auditability**: freeze state must be evidence-backed, not narrative-only.
2. **Default-safe behavior**: audio should be opt-in by approved exception, not opt-out by convention.
3. **Reliability**: Phase 2.7 quality evidence must not be contaminated by ungoverned audio drift.
4. **Security and privacy**: reduce accidental audio collection/processing surface under MVP.
5. **Delivery focus**: keep Search/Chat vision-only critical path explicit and enforceable.

---

## Considered Options

### Option A: Keep governance-only gate (historical baseline)

- **Description**: Phase 2.6 remains audit/exception governance without default behavior contract.
- **Pros**:
  - Lowest doc-change cost.
  - Minimal migration effort.
- **Cons**:
  - Cannot constrain default runtime posture at contract level.
  - Leaves WebUI/search/timeline semantics open to drift.

### Option B: Governance + default full-chain pause (Chosen)

- **Description**: Phase 2.6 governs and defines audio default posture end-to-end.
- **Pros**:
  - Makes freeze semantics decision-complete across capture, processing, UI, search/chat.
  - Reduces ambiguity in phase-gate evidence and operational expectations.
  - Supports controlled exceptions with explicit TTL and closure evidence.
- **Cons**:
  - Requires synchronized document updates across ADR/gates/roadmap/WebUI docs.
  - Adds governance overhead for temporary enablement.

### Option C: Full audio retirement from active docs

- **Description**: Remove audio from active contract surfaces entirely.
- **Pros**:
  - Smallest default privacy surface.
  - Simplest mainline messaging.
- **Cons**:
  - Conflicts with existing historical implementation and ops troubleshooting needs.
  - Higher future re-entry cost.

---

## Decision Outcome

Adopt **Option B**.

### What is locked

1. Insert **Phase 2.6** between Phase 2.5 and Phase 2.7 as a hard gate.
2. Phase 2.6 is now **governance + default full-chain pause**, not governance-only.
3. Default audio behavior contract:
   - No automatic audio capture.
   - No automatic audio processing/transcription/indexing.
   - WebUI default path does not show audio entrypoints/results.
   - Search/Chat contract excludes audio grounding.
4. Audio may be enabled only through approved `ExceptionRequest` with TTL, rollback plan, and closure evidence.
5. Phase 2.7 start condition remains `Phase 2.6 = GO`.

### Governance interfaces (document-layer only)

- `FreezeScopeMatrix`
  - Added required fields: `default_capture_state`, `default_processing_state`, `ui_default_visibility`, `search_chat_modalities`.
- `ExceptionRequest`
  - Added required fields: `enable_window`, `auto_revert_rule`, `closure_evidence`.
- `GateEvidenceManifest`
  - Added required fields: `contract_scope`, `exception_link`.

---

## Contract Implications (Target)

1. `GET /api/v1/search`: vision-only contract path for Search/Chat grounding.
2. `GET /api/v1/timeline`: target default is video-only; audio access is explicit parameter/debug-mode path.
3. `POST /api/v1/chat`: evidence contract is limited to vision sources.

This ADR defines target contract semantics. It does not claim all code paths are already converged.

---

## Consequences

### Positive

- Reduces freeze ambiguity and documentation drift.
- Improves incident attribution and exception traceability.
- Lowers default audio privacy surface in MVP documentation contract.

### Negative

- Increases doc synchronization burden.
- Requires stricter exception governance operations.

### Neutral

- No immediate runtime code mutation is introduced by this ADR alone.

---

## Rollback Conditions

Rollback this ADR only if one of the following is true:

1. Organization-wide release-control framework supersedes phase-gate governance.
2. MVP critical path is rebaselined and Phase 2.7 is removed.
3. Hard evidence shows default full-chain pause increases delivery risk more than risk reduction value.

If rolled back:
- Mark this ADR as `Superseded`.
- Publish replacement ADR with explicit freeze behavior semantics.
- Update roadmap + gates + WebUI contract docs in one change set.

---

## Implementation Notes

- Gate authority: `v3/metrics/phase-gates.md`
- Roadmap and sequencing authority: `v3/milestones/roadmap-status.md`
- Search/Chat contract context: `v3/decisions/ADR-0006-screenpipe-search-contract.md`
