# v3 Results

Store per-phase execution outcomes and verification reports.

## Naming

- `phase-0-validation.md`
- `phase-1-validation.md`
- `phase-1-post-baseline-changelog.md`
- `phase-2-validation.md`
- `phase-3-validation.md`
- `phase-4-validation.md`
- `phase-5-validation.md`

Each result file should include:
- What was implemented
- Test/verification evidence
- Metrics vs gate thresholds
- Known issues and follow-up actions
- A readable end-to-end behavior diagram section: `Request -> Processing -> Storage -> Retrieval` (Mermaid flowchart)
- Maintenance constraint: whenever a new `phase-*-validation.md` is added, update `v3/webui/CHANGELOG.md` and the impacted `v3/webui/pages/*.md` docs in the same change.

## Required Section Template (for every `phase-*-validation.md`)

Use this section title and keep it up to date with the phase-specific runtime path:

`### Request -> Processing -> Storage -> Retrieval Behavior Diagram`

Diagram expectations:
- Human-readable Chinese/English labels are both allowed
- Must contain 4 clear layers: request, processing, storage, retrieval
- Must include the primary happy path and at least one fallback/degradation path when applicable
- Must align with current phase implementation (do not paste stale diagrams across phases)

`phase-1-post-baseline-changelog.md` is a focused exception: it tracks only post-baseline hardening/regression changes after initial Phase 1 completion.
