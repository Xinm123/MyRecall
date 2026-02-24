# Phase 2.6 Detailed Plan — Audio Freeze Governance (Hard Freeze)

**Phase**: 2.6 (Audio Freeze Governance)  
**Status**: Not Started  
**Scope Type**: target  
**Position**: Inserted before Phase 2.7 (hard pre-gate)  
**Authority**: `/Users/pyw/newpart/MyRecall/v3/metrics/phase-gates.md`  
**Decision Record**: `/Users/pyw/newpart/MyRecall/v3/decisions/ADR-0007-phase-2.6-audio-freeze-governance.md`

---

## 1. Goal

Convert Audio Freeze from a status label into an auditable governance phase.

This phase is a **governance-only hard gate**:
- No feature work is executed by default.
- Any change to frozen audio modules/config requires approved exception workflow.
- Phase 2.7 cannot enter execution until Phase 2.6 is marked `GO`.

**Non-goals**:
- No runtime API additions.
- No audio algorithm iteration.
- No expansion of audio scope in MVP critical path.

**Screenpipe alignment principle**: align on release-quality discipline (quality gate, rollback readiness, soak-style evidence), but keep MyRecall phase-gate governance as the controlling mechanism.

---

## 2. Freeze Scope Matrix

| FreezeScopeMatrix.object | Path/Key | Owner | Risk Tier | Exception Allowed |
|---|---|---|---|---|
| Client audio capture | `openrecall/client/audio_manager.py` | Client Lead | High | Yes (P0 only) |
| Client audio producer | `openrecall/client/audio_recorder.py` | Client Lead | High | Yes (P0 only) |
| Client audio buffer policy | `openrecall/client/buffer.py` | Platform Lead | Medium | Yes (P0/P1) |
| Client upload queue policy | `openrecall/client/upload_queue.py` | Platform Lead | High | Yes (P0 only) |
| Client audio upload | `openrecall/client/uploader.py` | Platform Lead | High | Yes (P0 only) |
| Server audio processing | `openrecall/server/audio/processor.py` | Server Lead | High | Yes (P0 only) |
| Server transcription engine | `openrecall/server/audio/transcriber.py` | Server Lead | High | Yes (P0 only) |
| Server audio worker | `openrecall/server/audio/worker.py` | Server Lead | High | Yes (P0 only) |
| Audio configuration contract | `openrecall/shared/config.py` (`OPENRECALL_AUDIO_*`) | Platform Lead | Critical | Yes (P0 only) |
| Audio transport critical keys | `OPENRECALL_UPLOAD_TIMEOUT`, `OPENRECALL_API_URL`, `OPENRECALL_CLIENT_AUDIO_CHUNKS_PATH`, `OPENRECALL_SERVER_AUDIO_PATH` | Platform Lead | High | Yes (P0 only) |

Rule: any object in this matrix is immutable unless an approved `ExceptionRequest` exists.

---

## 3. Allowed Exception Workflow

1. **Request**: submit `ExceptionRequest` with incident ID, blast radius, rollback plan, TTL.
2. **Triage**: classify severity (`P0`, `P1`, `P2`).
3. **Approval**:
   - `P0`: Product Owner + Chief Architect + Security Reviewer.
   - `P1`: Product Owner + Chief Architect.
   - `P2`: rejected during Phase 2.6.
4. **Execution Window**: approved changes must be scoped to declared files/keys and expire at request TTL.
5. **Revalidation**: all `2.6-G-*` gates touched by the exception must be re-attested.
6. **Closure**: attach evidence and mark request `closed`; unresolved requests block unfreeze.

---

## 4. Unfreeze Hard Gates (`2.6-G-*`)

All gates are mandatory; any single failure = `NO-GO`.

| Gate | Criteria | Evidence | Status |
|---|---|---|---|
| `2.6-G-01` Stability Evidence | Continuous 24h run evidence archived with no unresolved P0/P1 incidents | Stability report + incident log | ⬜️ |
| `2.6-G-02` Performance Budget | CPU growth `<= +12%`, storage growth `<= +10%`, query p95 no regression (target +10%-20% improvement) | Benchmark report + baseline comparison | ⬜️ |
| `2.6-G-03` Quality Baseline | Label mismatch `<= 2%-5%` and `Precision@10` uplift `>= 20%` vs Phase 1.5 baseline | Evaluation report | ⬜️ |
| `2.6-G-04` Rollback Readiness | Rollback drill succeeds and recovery objective is met (`< 2 minutes`) | Rollback log + checksum verification | ⬜️ |
| `2.6-G-05` Config Drift Audit | No unauthorized changes to frozen keys/paths during freeze window | Drift audit report + approvals map | ⬜️ |

---

## 5. Evidence Package Templates

All evidence for this phase is stored under:
`/Users/pyw/newpart/MyRecall/v3/results/phase-2.6-evidence/<run_id>/`

### 5.1 `FreezeScopeMatrix` template

| Field | Type | Description |
|---|---|---|
| `object` | string | Controlled object name |
| `path_or_key` | string | File path or config key |
| `owner` | string | Accountable role |
| `risk_tier` | enum | `Medium` / `High` / `Critical` |
| `exception_allowed` | bool | Whether exception is possible |

### 5.2 `ExceptionRequest` template

| Field | Type | Description |
|---|---|---|
| `request_id` | string | Unique request ID |
| `severity` | enum | `P0` / `P1` / `P2` |
| `reason` | string | Why exception is required |
| `impact_scope` | string | Module/key and user impact |
| `risk_assessment` | string | Added risks from exception |
| `rollback_plan` | string | Exact rollback path |
| `approvers` | list | Required approver names/roles |
| `ttl` | datetime | Expiry time for the exception |
| `status` | enum | `open` / `approved` / `closed` / `rejected` |

### 5.3 `GateEvidenceManifest` template

| Field | Type | Description |
|---|---|---|
| `gate_id` | string | `2.6-G-*` |
| `artifact_path` | string | Path to report/log |
| `generated_at` | datetime | Artifact generation time |
| `validator` | string | Evidence reviewer |
| `result` | enum | `PASS` / `FAIL` |
| `notes` | string | Optional context |

---

## 6. Roles and RACI

| Activity | Product Owner | Chief Architect | Client Lead | Server Lead | Security Reviewer | QA Lead |
|---|---|---|---|---|---|---|
| Define freeze scope | A | R | C | C | C | C |
| Approve exception (P0/P1) | A | A | C | C | R | C |
| Produce gate evidence | C | C | R | R | C | R |
| Validate rollback drill | C | A | C | R | C | R |
| Config drift audit sign-off | C | A | C | C | R | C |
| Final unfreeze decision | A | A | C | C | C | C |

Legend: `R` Responsible, `A` Accountable, `C` Consulted.

---

## 7. Dependency with Phase 2.7

Execution order is strict:

1. `Phase 2.6` governance lock-in and evidence closure (`2.6-G-01..05` all PASS).
2. `Phase 2.7` frame-label alignment implementation and validation.
3. `Phase 3` start only after `Phase 2.7 = GO`.

If `Phase 2.6` fails:
- Keep audio branch frozen.
- Re-open only unresolved gate IDs.
- Run targeted re-attestation and reissue `GateEvidenceManifest`.
- Do not advance to `Phase 2.7`.

---

**No-code rule for this phase**: this phase modifies and reviews governance documentation and evidence manifests only.
