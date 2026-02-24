# MyRecall v3 Documentation Hub

This directory is the authoritative documentation workspace for MyRecall-v3.

## Read This First

- Roadmap authority: `milestones/roadmap-status.md`
- Phase gates authority: `metrics/phase-gates.md`
- Decision authority: `decisions/README.md`

## Navigation by Document Scope

### Current (verified against code)

- `milestones/roadmap-status.md` (includes Current vs Target drift table)
- `webui/pages/search.md`
- `webui/pages/timeline.md`
- `webui/ROUTE_MAP.md`
- `webui/DATAFLOW.md`

### Target (contract for upcoming phases)

- `plan/00-master-prompt.md`
- `plan/06-vision-chat-mvp-spec.md`
- `decisions/ADR-0006-screenpipe-search-contract.md`
- `decisions/ADR-0007-phase-2.6-audio-freeze-governance.md`

### Historical (retained for audit)

- `plan/02-phase-0-detailed-plan.md`
- `plan/03-phase-1-detailed-plan.md`
- `plan/04-phase-2-detailed-plan.md`
- `plan/05-phase-2.5-webui-audio-video-detailed-plan.md`
- `plan/phase-1.5-video-pipeline-hardening-plan.md`
- `references/myrecall-vs-screenpipe.md` (historical baseline, 2026-02-04)

## Directory Layout

- `plan/`: planning specs and execution plans
- `metrics/`: gate definitions and acceptance criteria
- `milestones/`: roadmap and phase status tracking
- `decisions/`: ADR decision records
- `results/`: phase validation reports and changelogs
- `webui/`: WebUI behavior and dataflow docs
- `references/`: external references and comparison baselines

## Documentation Contract

1. Use dual-track wording: `Current (verified)` vs `Target (contract)`.
2. Mark historical docs clearly and keep them immutable except for historical labels.
3. Do not claim screenpipe API-level equivalence unless explicitly true in source.
4. Prefer repo-relative paths; avoid stale absolute machine paths.
5. Keep Search/Chat scope lock explicit: vision-only MVP, audio frozen for critical path.

## High-Signal Files

- `milestones/roadmap-status.md`
- `decisions/ADR-0005-vision-only-chat-pivot.md`
- `decisions/ADR-0006-screenpipe-search-contract.md`
- `plan/06-vision-chat-mvp-spec.md`
- `webui/pages/search.md`
