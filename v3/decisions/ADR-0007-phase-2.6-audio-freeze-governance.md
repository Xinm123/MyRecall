# ADR-0007: Phase 2.6 Audio Freeze Governance

**Status**: Accepted  
**SupersededBy**: N/A  
**Supersedes**: N/A  
**Scope**: target

**Date**: 2026-02-24

**Deciders**: Product Owner + Chief Architect

**Context**: MyRecall-v3 roadmap hardening between Phase 2.5 and Phase 2.7

---

## Context and Problem Statement

Audio Freeze exists in roadmap narrative, but governance controls are fragmented across roadmap, plans, and gate files.  
Without a dedicated phase-level control point, three risks remain:

1. Freeze semantics are inconsistent across documents.
2. P0 security/stability fixes have no explicit exception path.
3. Phase 2.7 quality-gate evidence can be polluted by uncontrolled audio/config drift.

The project needs an auditable, decision-complete gate before Phase 2.7 starts.

---

## Decision Drivers

1. **Auditability**: freeze state must be evidence-backed, not descriptive text only.
2. **Separation of concerns**: governance controls must be separated from feature-change phases.
3. **Reliability**: hard unfreeze conditions must be explicit and measurable.
4. **Screenpipe alignment without forced isomorphism**: align principles (quality gate + rollback + soak evidence), preserve MyRecall phase-gate mechanism.

---

## Considered Options

### Option A: Add standalone Phase 2.6 hard freeze governance (Chosen)

- **Description**: Insert Phase 2.6 before Phase 2.7 as governance-only hard gate.
- **Pros**:
  - Clarifies ownership and change authority.
  - Reduces regression leakage and cross-doc contradiction.
  - Creates explicit exception workflow for P0/P1 fixes.
- **Cons**:
  - Adds documentation overhead and one more release checkpoint.
  - Shifts relative sequence by one step.

### Option B: Fold freeze governance into Phase 2.7

- **Description**: Keep one combined phase.
- **Pros**:
  - Fewer phase nodes and less documentation work.
- **Cons**:
  - Governance and feature outcomes become hard to attribute.
  - Gate failures become harder to triage.

### Option C: Keep freeze as soft policy only

- **Description**: No dedicated hard gate; track freeze via ad hoc checklist.
- **Pros**:
  - Fastest short-term execution.
- **Cons**:
  - High drift risk and low audit traceability.
  - Inconsistent exception handling and rollback readiness evidence.

---

## Decision

Adopt **Option A**.

### What is locked

1. Insert **Phase 2.6** between Phase 2.5 and Phase 2.7.
2. Define hard governance gates `2.6-G-01..05` (stability, performance budget, quality baseline, rollback readiness, config drift audit).
3. Freeze scope explicitly covers:
   - Client audio modules
   - Server audio processing/transcription/worker modules
   - Audio-critical config contracts (`OPENRECALL_AUDIO_*` and transport-critical keys)
4. Phase 2.7 start condition: `Phase 2.6 = GO`.

### Governance interfaces (document-layer only)

- `FreezeScopeMatrix`
- `ExceptionRequest`
- `GateEvidenceManifest`

---

## Consequences

### Positive

- Improves governance traceability and reduces ambiguous freeze interpretations.
- Enables controlled emergency fixes without silently breaking freeze integrity.
- Improves reliability of Phase 2.7 quality evidence.

### Negative

- Adds process and documentation maintenance overhead.
- Requires synchronized updates across roadmap, plan, gate, and ADR records.

### Neutral

- No runtime API changes are introduced by this ADR.

---

## Rollback Conditions

Rollback this ADR only if one of the following is true:

1. Phase-gate governance is formally replaced by a stronger organization-wide release-control framework.
2. MVP critical path is rebaselined and Phase 2.7 is removed.
3. Hard evidence shows Phase 2.6 increases delivery risk more than it reduces regression risk.

If rolled back:
- Mark this ADR as `Superseded`.
- Publish replacement ADR with explicit freeze governance semantics.
- Update roadmap and gates in the same change set.

---

## Implementation Notes

- Primary plan document: `/Users/pyw/newpart/MyRecall/v3/plan/phase-2.6-audio-freeze-governance.md`
- Gate authority: `/Users/pyw/newpart/MyRecall/v3/metrics/phase-gates.md`
- Roadmap and execution sequencing: `/Users/pyw/newpart/MyRecall/v3/milestones/roadmap-status.md`
