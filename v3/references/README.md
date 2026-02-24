# MyRecall-v3 References Index

This folder stores reference materials used by roadmap/ADR/doc decisions.

## Reference Freshness Policy

Every reference should be tagged with one of:

- `current-supporting`: directly supports current roadmap/ADR decisions.
- `historical-baseline`: useful for audit/history; not authoritative for current strategy.
- `external-concept`: conceptual source only.

## Core References

### 1. Screenpipe (external project)

- Path: `screenpipe/`
- Type: `current-supporting`
- Usage in MyRecall docs:
  - Search semantics and filters
  - Time-range discipline patterns
  - Evidence-grounded chat workflow constraints

### 2. openclaw memory concepts

- Link: https://docs.openclaw.ai/concepts/memory
- Type: `external-concept`

## Internal Reference Files

| File | Type | Note |
|---|---|---|
| `myrecall-vs-screenpipe.md` | historical-baseline | Snapshot from 2026-02-04; multi-modal context |
| `myrecall-vs-screenpipe-alignment-current.md` | current-supporting | Current alignment assessment under vision-only MVP |
| `myrecall-v2-analysis.md` | historical-baseline | v2 pipeline analysis baseline |
| `encryption.md` | current-supporting | Data-at-rest guidance |
| `hardware.md` | current-supporting | Environment and capacity reference |

## Historical Baseline Rule

If a historical reference conflicts with current strategy:

1. Keep the historical file unchanged except clear historical labeling.
2. Add or update a `current-supporting` companion document.
3. Update roadmap/ADR links to point to the current companion document for active decisions.

## Path Convention

Use repo-relative paths in docs by default.

## Version

- 2026-02-24: Reclassified references by freshness and historical status.
