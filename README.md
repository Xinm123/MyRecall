# MyRecall

MyRecall is a local-first digital memory system focused on screen capture, OCR indexing, timeline retrieval, and evidence-grounded chat planning.

## Program Snapshot (Authoritative as of 2026-02-24)

Roadmap authority: `MyRecall/v3/milestones/roadmap-status.md`

| Track | Current (Code Reality) | Target (Roadmap Contract) |
|---|---|---|
| Phase 0 | Complete | Stable baseline |
| Phase 1 | Engineering complete; long-run observations deferred | Historical complete |
| Phase 2.0 / 2.1 | Audio engineering preserved; currently frozen from MVP critical path | Historical/frozen |
| Phase 2.5 | WebUI audio/video dashboards complete | Historical complete |
| Phase 2.6 | Not started | Governance hard-gate for Audio Freeze |
| Phase 2.7 | Not started | Frame label alignment hard-gate |
| Phase 3 | Not started | Vision search parity (screenpipe-aligned semantics) |
| Phase 4 | Not started | Vision chat MVP (evidence-first) |
| Phase 5 | Not started | Deployment migration (serial critical path) |
| Phase 8 | Not started | Required post-MVP full alignment phase |

## Scope Lock

- Search/Chat MVP is **vision-only**.
- Audio implementation is kept for operations/history, but excluded from MVP Search/Chat critical path under Audio Freeze.
- Screenpipe alignment target is **semantic alignment + operational discipline**, not API isomorphism.

## Current vs Target (Key Contracts)

### `GET /api/v1/search`

| Item | Current (Verified) | Target (Phase 3 Contract) |
|---|---|---|
| `q` | Empty/missing returns empty paginated payload | Empty/missing enters browse/feed mode |
| `start_time` | Not enforced at route layer | Required (MyRecall policy for bounded retrieval) |
| Modality | Search engine may still include audio FTS candidates | Vision-only for Search/Chat grounding |

### `GET /api/v1/timeline`

| Item | Current (Verified) | Target Positioning |
|---|---|---|
| Default source | Mixed video + audio | Keep mixed for ops visibility |
| Search/Chat grounding | N/A | Search/Chat remain vision-only |

## Quick Start (Single Machine)

Prerequisites:

1. Python `3.9`-`3.12`
2. `ffmpeg` in `PATH`
3. macOS Screen Recording permission for video mode

Install:

```bash
cd MyRecall
python3 -m pip install -e .[test]
```

Run server:

```bash
conda activate v3
cd MyRecall
./run_server.sh --debug
```

Run client:

```bash
conda activate v3
cd MyRecall
./run_client.sh --debug
```

Default endpoints:

- Web UI: `http://127.0.0.1:18083`
- API root: `http://127.0.0.1:18083/api`
- Fallback port without env loading: `8083`

## Documentation Map

### Program authority

- Roadmap status: `MyRecall/v3/milestones/roadmap-status.md`
- Phase gates authority: `MyRecall/v3/metrics/phase-gates.md`
- Master prompt: `MyRecall/v3/plan/00-master-prompt.md`

### Decisions (ADR)

- ADR index: `MyRecall/v3/decisions/README.md`
- Vision-only pivot: `MyRecall/v3/decisions/ADR-0005-vision-only-chat-pivot.md`
- Search contract: `MyRecall/v3/decisions/ADR-0006-screenpipe-search-contract.md`
- Audio freeze governance: `MyRecall/v3/decisions/ADR-0007-phase-2.6-audio-freeze-governance.md`

### WebUI docs

- WebUI portal: `MyRecall/v3/webui/README.md`
- Route map: `MyRecall/v3/webui/ROUTE_MAP.md`
- Dataflow: `MyRecall/v3/webui/DATAFLOW.md`
- Search page doc: `MyRecall/v3/webui/pages/search.md`
- Timeline page doc: `MyRecall/v3/webui/pages/timeline.md`

### References

- References index: `MyRecall/v3/references/README.md`
- Historical baseline comparison: `MyRecall/v3/references/myrecall-vs-screenpipe.md`
- Current alignment analysis: `MyRecall/v3/references/myrecall-vs-screenpipe-alignment-current.md`

## Working Rules for Documentation

- Keep `Current (verified)` and `Target (contract)` explicitly separated.
- Do not describe target behavior as already implemented.
- Label historical artifacts as `historical` and preserve them for audit.
- Prefer repo-relative paths in docs; avoid machine-bound legacy absolute paths.

## License

AGPLv3 (`MyRecall/LICENSE`).
