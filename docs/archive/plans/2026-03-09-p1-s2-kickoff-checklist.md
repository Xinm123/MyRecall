# P1-S2 Kickoff Checklist (Mapped to Current Code + Acceptance Docs)

> Scope: Turn current P1-S1 verified code state into a clean, auditable start point for P1-S2.

## 1) Current Code Baseline (Must Be Preserved)

- [x] Re-run regression baseline and archive output:
  - `pytest tests/test_v3_migrations_bootstrap.py tests/test_p1_s1_*.py -q`
  - Result: `43 passed in 8.13s` (2026-03-09, post grid fix)
  - Evidence:
    - `docs/v3/acceptance/phase1/evidence/2026-03-09-p1-s1-baseline.txt`
    - `docs/v3/acceptance/phase1/evidence/2026-03-09-p1-s1-baseline-after-grid-fix.txt`
  - Pass condition: all green, no new skips/xfails.
- [x] Confirm the following P1-S1 behaviors are treated as frozen contracts for P1-S2:
  - UUIDv7 ingest validation
  - `/v1/health` UTC timestamp parsing + stale/degraded behavior
  - noop-safe lazy search engine initialization
  - ingest idempotency and concurrency ownership (DB-first claim/finalize)
  - atomic spool writes (`.jpg` and `.json`)
  - UTC ISO8601 timestamp contract across client/server/UI
  - UI health gate explicit `frame_status == "ok"`
  - uploader 503 retry_after single-wait behavior
  - migration runner safeguards (no self-record, atomicity, integrity checks)
  - timeline/grid timestamp parsing compatibility (ISO/unix/float-string paths)
  - Evidence anchors:
    - `openrecall/server/api_v1.py` (UUIDv7 + health parse)
    - `openrecall/server/api.py` (noop lazy search + since normalization)
    - `openrecall/server/database/frames_store.py` (claim/finalize + UTC normalization)
    - `openrecall/client/spool.py` (atomic jpg/json writes)
    - `openrecall/client/v3_uploader.py` (503 retry_after single-wait)
    - `openrecall/server/database/migrations_runner.py` (migration safeguards)
    - `openrecall/server/templates/layout.html` and `openrecall/server/templates/index.html` (UI gates/parsing)

## 2) Acceptance Documentation Closure for P1-S1 (Blocking for Clean Handoff)

- [x] Update `docs/v3/acceptance/phase1/p1-s1.md` header metadata:
  - Replace planned/TBD fields (`日期/负责人/版本-提交/状态`) with actual values.
- [x] Fill section `4.1/4.2/4.3/4.4` with actual verification outcomes and evidence links/paths.
- [x] Fill section `5. 结论` with explicit Gate result (`Pass` or `Fail`) and concrete rationale.
- [x] Ensure section `2.1 指标口径与样本说明（必填）` remains complete (required by acceptance README).
- [x] If any non-blocking KPI is not met, mark it clearly as `non-blocking` with remediation action and owner.
  - Note: Current gate is `Fail` due sample/evidence closure gaps (not a soft KPI pass with non-blocking waiver).

## 3) Spec/OpenSpec Consistency Sweep (Recommended Before P1-S2 Coding)

- [x] Confirm `docs/v3/spec.md` language matches implemented P1-S1 runtime behavior:
  - ingest status semantics (`queued` / `already_exists`)
  - error-code no-DB-side-effect guarantees
  - timestamp format and parsing compatibility expectations
  - Synced updates include: metadata compatibility keys, UI bridge status normalization, health message example, and de-`TODO` wording for capture_id idempotency.
- [x] Confirm `openspec` P1-S1 change artifacts reflect final implementation (no stale TODOs or mismatched assumptions).
  - Updated: `tasks.md` (migration runner semantics + grid compatibility task), `design.md` non-goal wording, `specs/health-endpoint/spec.md`, `specs/ingest/spec.md`.
- [x] Record any intentional divergence from screenpipe reference as "behavior aligned / topology differs" notes.
  - Recorded stance unchanged: behavior aligned for P1-S1 contracts; topology remains Host/Edge split (not single-node screenpipe runtime).

## 4) P1-S2 Entry Contract (Define Before Implementation)

- [x] Create/refresh `docs/v3/acceptance/phase1/p1-s2.md` with:
  - In-scope outcomes
  - Explicit out-of-scope items
  - Input dependencies from stable P1-S1 contracts
  - Verification commands and minimum pass criteria
- [x] Define rollback rule for P1-S2: no change may break P1-S1 regression baseline.
- [x] Define release gate for P1-S2: code checks + acceptance document completeness.
  - Synced to `p1-s2.md` Section `7` (Rollback Rule) and Section `8` (Release Gate).

## 5) Execution Order (Practical)

1. [x] Re-run baseline tests and capture evidence.
   - Evidence: `docs/v3/acceptance/phase1/evidence/2026-03-09-p1-s1-baseline-section5-rerun-final.txt` (`43 passed in 6.99s`)
2. [x] Close P1-S1 acceptance record (`p1-s1.md`) to final state.
   - Final state: `Closed (Pass)`
3. [x] Run spec/OpenSpec consistency sweep.
   - Evidence: `docs/v3/acceptance/phase1/evidence/2026-03-09-p1-s1-spec-openspec-sweep-section5.md`
4. [x] Finalize P1-S2 acceptance template/scope.
5. [ ] Start P1-S2 implementation work.

## 6) Go/No-Go Rules for Starting P1-S2

Start P1-S2 only when all three are true:

1. P1-S1 baseline regression is green.
2. `docs/v3/acceptance/phase1/p1-s1.md` is fully closed (not Planned/TBD).
3. P1-S2 scope + acceptance contract is written and reviewable.

If any one is false, status remains **No-Go (process incomplete)** even if runtime code is healthy.
