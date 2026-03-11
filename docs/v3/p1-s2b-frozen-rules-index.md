# P1-S2b Frozen Rules Index

## Purpose

This file is the lookup index for P1-S2b frozen rules.

It does not redefine the rules. It tells readers where the authoritative rule lives, what the supporting document is, and which acceptance document enforces it.

## Source Priority

Use these sources in this order when reading or updating P1-S2b behavior:

1. `docs/v3/spec.md` — architecture and behavior SSOT
2. `docs/v3/data-model.md` — payload and storage contract consequences
3. `docs/v3/open_questions.md` — frozen decisions and rationale record
4. `docs/v3/acceptance/phase1/p1-s2b.md` — S2b stage acceptance and evidence requirements
5. `docs/v3/acceptance/phase1/p1-s3.md` — S2b->S3 handoff and ownership boundary enforcement

If these documents conflict, update them to match the first higher-priority source instead of reinterpreting the rule locally.

## Frozen Rule Map

| Rule area | Canonical source | Supporting source(s) | Acceptance / enforcement |
|---|---|---|---|
| Trigger semantics | `docs/v3/spec.md` (`P1-S2b frozen capture semantics`) | `docs/v3/open_questions.md` (OQ-040), `docs/v3/data-model.md` (`trigger / device binding 语义`) | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.0d`, `1.0e`) |
| `device_name` binding | `docs/v3/spec.md` (`P1-S2b frozen capture semantics`) | `docs/v3/data-model.md` (`capture_device_binding`), `docs/v3/open_questions.md` (OQ-040) | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.0c`, `1.0e`) |
| `focused_context` single-snapshot rule | `docs/v3/spec.md` (`P1-S2b frozen capture semantics`) | `docs/v3/data-model.md` (`上下文字段一致性契约`), `docs/v3/open_questions.md` (OQ-040) | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.0c`) |
| Browser URL stale rejection | `docs/v3/spec.md` (`Browser URL stale rejection`) | `docs/v3/data-model.md` (`上下文字段一致性契约`), `docs/v3/open_questions.md` (OQ-040) | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.0c`, Browser URL tests) |
| `accessibility_text` / `content_hash` handoff requiredness | `docs/v3/data-model.md` (`S2b handoff 字段语义`) | `docs/v3/spec.md` (CapturePayload contract), `docs/v3/open_questions.md` (OQ-033, OQ-040), `docs/v3/http_contract_ledger.md` (`P1-S2b delta`) | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.0c`), `docs/v3/acceptance/phase1/p1-s3.md` (`2.1`) |
| `content_hash` canonicalization | `docs/v3/spec.md` (`content_hash canonicalization`) | `docs/v3/data-model.md` (`S2b handoff 字段语义`), `docs/v3/open_questions.md` (OQ-040) | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.0c`) |
| Host-side dedup timing | `docs/v3/spec.md` (`内容去重实现`) | `docs/v3/data-model.md` (`dedup 语义`), `docs/v3/open_questions.md` (OQ-040) | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.0d`) |
| `last_write_time` semantics | `docs/v3/spec.md` (`Host 端 dedup 状态与重启语义`) | `docs/v3/data-model.md` (`dedup 运行态约束`), `docs/v3/open_questions.md` (OQ-040), `docs/v3/runbook_phase1.md` (restart note) | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.0d`) |
| Empty-AX no-drop rule | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.0c`) | `docs/v3/spec.md` (S2b raw handoff boundary), `docs/v3/open_questions.md` (OQ-039) | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.0c`, SQL gate notes) |
| AX timeout / empty text ownership | `docs/v3/open_questions.md` (OQ-039) | `docs/v3/spec.md` (`P1-S3 语义 SSOT`, `AX 降级策略`), `docs/v3/open_questions.md` (OQ-033) | `docs/v3/acceptance/phase1/p1-s3.md` (`2.1`) |
| S2b vs S3 ownership boundary | `docs/v3/open_questions.md` (OQ-039) | `docs/v3/spec.md` (`P1-S3 语义 SSOT`) | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.0c`), `docs/v3/acceptance/phase1/p1-s3.md` (`2.1`) |
| S2b test delivery strategy (TDD + Exit Gate script) | `docs/v3/open_questions.md` (OQ-041) | `docs/v3/test_strategy.md`, `docs/v3/acceptance/phase1/p1-s2b.md` | `docs/v3/acceptance/phase1/p1-s2b.md` (`3.1`, `3.2`) |
| S2b v3-only execution path / legacy isolation | `docs/v3/open_questions.md` (OQ-042) | `docs/v3/spec.md` (`/api/*` legacy boundary, `P1 协议：单次幂等上传`), `docs/v3/http_contract_ledger.md` (`Legacy namespace retirement`) | `docs/v3/acceptance/phase1/p1-s2b.md` (`1.1`) |
| Gate baseline version | `docs/v3/gate_baseline.md` | `docs/v3/acceptance/phase1/p1-s2b.md` (`2.1`), `docs/v3/roadmap.md` | `docs/v3/acceptance/phase1/p1-s2b.md` (`2.1`) |
| P1-S2b parameter baseline (`walk_timeout`, `max_depth`, `max_nodes`) | `docs/v3/acceptance/phase1/p1-s2b.md` | `docs/v3/adr/ADR-0013-event-driven-ax-split.md`, `docs/v3/references/screenpipe-p1-s2b-validation.md` | `docs/v3/acceptance/phase1/p1-s2b.md` (`2`, `3`) |

## Practical Reading Guide

- If you are implementing Host capture semantics, start with `docs/v3/spec.md`, then confirm payload/storage consequences in `docs/v3/data-model.md`.
- If you are deciding whether a behavior is frozen or still debatable, check `docs/v3/open_questions.md` first.
- If you are writing or updating gate scripts, metrics SQL, or manual validation steps, treat `docs/v3/acceptance/phase1/p1-s2b.md` as the operational source.
- If you are implementing processing behavior after upload, check `docs/v3/acceptance/phase1/p1-s3.md` to avoid pulling S3 semantics back into S2b.

## Change Rule

When a P1-S2b rule changes:

1. Update the canonical source first.
2. Update supporting sources that restate the rule.
3. Update the relevant acceptance document.
4. Update this index only if the ownership or source location changed.

## Non-Sources

These files are helpful references but not the final authority for frozen behavior:

- `docs/v3/references/screenpipe-p1-s2b-validation.md`
- `docs/v3/acceptance/phase1/archive/p1-s2.md`
- `docs/v3/roadmap.md`

They can explain or justify a rule, but they should not override the canonical sources listed above.
