# MyRecall vs Screenpipe Alignment (Current)

## Alignment Baseline Date

- Baseline date: 2026-02-24
- Scope: MyRecall vision-only MVP path (Phase 2.6/2.7/3/4/5) with audio freeze on critical path
- Reference semantics source: `screenpipe/crates/screenpipe-server/src/routes/search.rs`

## Current vs Target Matrix

| Area | Screenpipe 做法 | MyRecall 当前 | MyRecall 目标 | 可行性 |
|---|---|---|---|---|
| Search `q` semantics | `q` optional; empty query supported | `/api/v1/search` empty `q` returns empty payload | Empty `q` browse/feed | High |
| Time bounds discipline | API allows optional bounds; skills enforce `start_time` | route 未强制 `start_time` | 强制 `start_time`（MyRecall policy） | High |
| Search filters | app/window/focused/browser_url supported | filters contract写入文档但未完整落地到 v1 search route | 完整过滤链路 | Medium |
| Retrieval modality | multi-content (`ocr/audio/input/...`) | SearchEngine仍含audio candidates | Search/Chat grounding vision-only | Medium |
| Timeline default | rich multi-source retrieval | `/api/v1/timeline` 默认 mixed | 保持 mixed for ops，不作为 chat 主证据源 | High |
| Chat grounding | bounded retrieval + evidence discipline | chat endpoint 未实现 | answer + evidence[] 合同 | Medium |

## Intentional Divergences

1. **Vision-only grounding (MVP)**
- Reason: reduce scope and privacy surface on critical path.
- Impact: audio-dependent user stories deferred or rewritten.

2. **Epoch-time contract in MyRecall docs**
- Reason: browser-local authority pipeline in current plan.
- Impact: format differs from screenpipe ISO timestamp usage.

3. **`start_time` required policy**
- Reason: bounded retrieval safety and predictable latency.
- Impact: stronger caller requirement than screenpipe API minimum.

## Feasibility by Dimension

| Dimension | Assessment | Notes |
|---|---|---|
| Semantic alignment | High | Search mental model and filter semantics are directly alignable |
| Operational discipline | High | Bounded-time query discipline already documented and enforceable |
| API isomorphism | Low | Not required; intentional differences remain |
| Data-model parity | Medium | Phase 2.7 quality hardening needed before stable parity claims |
| Chat evidence parity | Medium | Depends on Phase 4 endpoint and enforcement gates |

## Risk & Blind Spots

1. Doc drift risk: target behavior being described as current implementation.
2. Governance overlap risk: 2.6 (governance) and 2.7 (quality) boundary confusion.
3. Alignment overclaim risk: using “screenpipe-aligned” without labeling divergence level.
4. Migration risk: changing empty-`q` semantics without caller communication.

## Decision Hooks for roadmap/ADR

1. Roadmap: keep `Current vs Target` table updated whenever search behavior changes.
2. ADR-0006: maintain semantic/discipline/divergence labels in contract text.
3. Phase gates: keep 2.6 governance-only; place quality uplift metrics in 2.7.
4. WebUI docs: maintain dual-track language (`Current verified` vs `Target contract`).
