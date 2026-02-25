# ADR-0007: Phase 2.6 Audio Hard Shutdown

**Status**: Accepted  
**SupersededBy**: N/A  
**Supersedes**: 2026-02-24 rev.2（Governance + Exception 语义）  
**Scope**: target

**Date**: 2026-02-24  
**Updated**: 2026-02-25（Phase 2.6 语义升级为 Hard Shutdown）

**Deciders**: Product Owner + Chief Architect

**Context**: MyRecall-v3 roadmap hardening between Phase 2.5 and Phase 2.7

---

## Context and Problem Statement

旧版 Phase 2.6（governance + exception）存在运行边界歧义：

1. 文档允许“冻结中但可临时开窗恢复音频主链路”的解释空间。
2. Search/Timeline/UI 的 audio 可见性没有形成不可绕行约束。
3. Phase 2.7 前置条件缺乏“音频主链路已完全摘除”的硬证据要求。

项目需要一个可执行、可审计、不可绕过的硬停机合同。

---

## Decision Drivers

1. **Auditability**: 2.6 gate 必须由可复现实证据支撑。
2. **Boundary clarity**: 明确 MVP 主链路仅保留 vision。
3. **Reliability**: 避免 audio 残留污染 2.7/3/4 的质量评估。
4. **Security/Privacy**: 降低默认音频采集与处理风险面。
5. **Delivery focus**: 在进入 Phase 2.7 前完成硬边界收口。

---

## Considered Options

### Option A: Governance + Exception（旧方案）

- **Description**: 通过 ExceptionRequest 管理临时启用音频。
- **Pros**:
  - 迁移成本低。
  - 保留调试便利性。
- **Cons**:
  - 主链路可被配置/流程回开。
  - 审计边界依赖流程执行质量，风险较高。

### Option B: Hard Shutdown（Chosen）

- **Description**: Phase 2.6 直接执行音频主链路硬停机，移除例外开窗机制。
- **Pros**:
  - 边界清晰，不可绕过。
  - 与 `2.6-G-*` gate 一一对齐。
  - 为 Phase 2.7 提供稳定前置条件。
- **Cons**:
  - 需要同步更新多份文档并完成代码收敛。

---

## Decision Outcome

Adopt **Option B（Hard Shutdown）**。

### What is locked

1. Phase 2.6 是 **Audio Hard Shutdown**，不是治理窗口。
2. 必须同时满足以下约束：
   - No automatic audio capture.
   - No automatic audio processing/transcription/indexing.
   - No audio retrieval in default search/timeline path.
   - No audio entrypoints in MVP primary UI path.
   - No runtime/config bypass that restores audio mainline.
3. **No Exception Workflow**：Phase 2.6 合同内不再保留 ExceptionRequest/TTL 临时开窗流程。
4. Phase 2.7 仅在 `2.6-G-01..05` 全部 PASS 后启动。

### Implementation Status (2026-02-25)

- Code convergence completed for capture/processing/retrieval/UI/anti-bypass shutdown paths.
- Gate runtime status at this timestamp:
  - `2.6-G-03`: PASS
  - `2.6-G-04`: PASS
  - `2.6-G-05`: PASS
  - `2.6-G-01`: PENDING（24h window）
  - `2.6-G-02`: PENDING（24h window）
- Release decision remains NO-GO until `2.6-G-01` and `2.6-G-02` are closed with 24h evidence.

---

## Contract Implications (Target)

1. `GET /api/v1/search`: 默认/标准路径不返回 audio。
2. `GET /api/v1/timeline`: 默认/标准路径不返回 audio。
3. WebUI 主导航不暴露 audio 主入口。
4. 音频历史数据仅用于离线审计，不进入 MVP 主路径。

This ADR defines target contract semantics. It does not claim all code paths are already converged at document update time.

---

## Consequences

### Positive

- 清除文档和实现边界歧义。
- 降低音频链路误激活概率。
- 提高 2.7 启动前的可审计性。

### Negative

- 需要一次性完成文档与代码的联动收敛。
- 对历史调试路径提出更严格约束。

### Neutral

- 历史音频数据可保留但不作为主链路数据源。

---

## Rollback Conditions

Rollback this ADR only if:

1. 组织级别发布控制策略替代当前 phase-gate 体系；或
2. MVP 关键路径被重排且 Phase 2.6 不再作为前置硬门槛。

If rolled back:

- Mark this ADR as `Superseded`.
- Publish replacement ADR with explicit phase boundary semantics.
- Update roadmap + gates + webui docs in one synchronized change set.

---

## Implementation Notes

- Gate authority: `v3/metrics/phase-gates.md`
- Roadmap authority: `v3/milestones/roadmap-status.md`
- Detailed plan: `v3/plan/07-phase-2.6-audio-freeze-governance-detailed-plan.md`
