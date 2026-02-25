# Phase 2.6: Audio Freeze Governance — Detailed Plan

**Version**: 1.0
**Status**: Planned
**Last Updated**: 2026-02-25
**Authority Docs**:
- Gate 真源：`v3/metrics/phase-gates.md`（`2.6-G-*` 小节）
- 决策依据：`v3/decisions/ADR-0007-phase-2.6-audio-freeze-governance.md`
- 路线状态：`v3/milestones/roadmap-status.md`

---

## 1. Goal / Non-Goals

### Goal

将 Audio Freeze 从叙述性声明（narrative-only）升级为可审计的治理控制阶段：

1. 发布 `FreezeScopeMatrix`，锁定 capture / processing / indexing / retrieval / UI 五个维度的 default-deny 边界。
2. 建立 `ExceptionRequest` 工作流，含审批、TTL、auto-revert、closure evidence 四要素。
3. 发布 `GateEvidenceManifest`，每个 `2.6-G-*` gate 对应 evidence 路径、生成方式、review owner。
4. 设计双层采证方案：20 分钟预检 + 24h 正式验收（no-auto-capture / no-auto-processing）。
5. 更新 WebUI contract 文档，使 audio/video 页面可见性、入口文案、状态标识与冻结契约对齐。
6. 制定 Failure Signals 与 Rollback Playbook。

### Non-Goals

- **不引入**任何默认自动音频采集 / 处理 / 检索能力。
- **不修改**任何业务代码、测试代码、配置文件（Code changes: NONE）。
- **不验收**已有 Phase 2.0 遗留的 `2-S-01`（24h 稳定性）——该 gate 属于 frozen branch，不在本阶段范围。
- **不扩展** Phase 2.1（Speaker ID）工作范围。
- **不前置执行** Phase 2.7 label alignment 工作——Phase 2.6 GO 是 Phase 2.7 的启动前提。

---

## 2. Scope（In / Out）

### In Scope（本阶段产出）

| 产出物 | 类型 | 说明 |
|--------|------|------|
| `FreezeScopeMatrix` | 文档 | 五维度 default-deny 边界表 |
| `ExceptionRequest` workflow | 文档 | 申请→审批→TTL→rollback→closure 全链路 |
| `GateEvidenceManifest` | 文档 | `2.6-G-*` 到 evidence 路径的映射 |
| 双层采证方案（20 分钟预检 + 24h 正式验收） | 文档 | 计划态命令 + 证据结构（不执行） |
| WebUI contract 更新 | 文档 | audio/video 页面可见性 + 契约标注 |
| Rollback Playbook | 文档 | 误开开关、异常未回收、证据缺失三类 playbook |
| `v3/results/phase-2.6-validation.md` | 模板 | 仅模板，不写验收结论 |
| `roadmap-status.md` Phase 2.6 区块 | 文档更新 | status/timeline/dependencies/blockers/open questions |

### Out of Scope（本阶段不做）

- 修改 `openrecall/` 任何 `.py` 文件
- 修改 `tests/` 任何测试文件
- 修改 `.env` / `.sh` / `setup.py` / `requirements.txt` 等配置文件
- Phase 2.7 工程实施
- Phase 3/4 Search/Chat 实施

---

## 3. Inputs（来自已交付阶段）/ Outputs（给 Phase 2.7+）

### Inputs

| 来源 | 交付项 | 与本阶段关系 |
|------|--------|-------------|
| Phase 0 | `/api/v1/*` 路由体系、`@require_auth` placeholder、pagination contract | Freeze Scope 中 API 契约边界的基础参考 |
| Phase 1 | `VideoRecorder`、`FrameExtractor`、`VideoProcessingWorker`、`RetentionWorker` 视频链路 | 确认视频链路不在 freeze scope，提供对比基准 |
| Phase 2.0 | `AudioManager`、`AudioRecorder`、`AudioChunkProcessor`、`AudioProcessingWorker` — 已冻结 | FreezeScopeMatrix 需覆盖这些模块路径 |
| Phase 2.5 | `/audio` 页面、`/video` 页面、Navigation（5-page toolbar）、audio/video file serving API | WebUI contract 需标注 `/audio` 入口的冻结可见性契约 |
| ADR-0005 | Vision-Only Chat Pivot + Audio Freeze 决策 | 确认 Search/Chat grounding 为 vision-only |
| ADR-0007 | governance + default full-chain pause 契约定义 | FreezeScopeMatrix / ExceptionRequest / GateEvidenceManifest 三个 interface 结构来源 |
| phase-gates.md | `2.6-G-01..05` 定义（唯一 gate 真源） | 本阶段验收标准，不允许改写 |

### Outputs（给 Phase 2.7+）

| 产出物 | 给什么阶段使用 | 使用方式 |
|--------|-------------|---------|
| `FreezeScopeMatrix`（定稿） | Phase 2.7、Phase 3 | 确认 audio 模块不在 Phase 2.7 改动范围 |
| `GateEvidenceManifest`（定稿） | Phase 2.7 kickoff review | 作为 Phase 2.6 GO 的核心证据包 |
| WebUI contract 文档（更新） | Phase 3 Search/Chat UI 设计 | `/search`、`/timeline` 默认行为契约参考 |
| Phase 2.6 Validation template | Phase 2.6 执行者（即本阶段） | Go/No-Go review 时填充证据 |
| Rollback Playbook | Phase 2.6 执行周期 + Phase 2.7 维护期 | 治理异常应急响应 |

---

## 4. Day-by-Day 计划（按工作日粒度）

> 本阶段预计 **4 个工作日**，全部产出为 Markdown 文档。
> 执行前提：Phase 2.5 Go/No-Go = GO（已满足）。

| Day | 任务 | 产出物 |
|-----|------|--------|
| **D1** | 起草 `FreezeScopeMatrix`（五维度：capture/processing/indexing/retrieval/UI）；确认模块路径清单 | FreezeScopeMatrix draft |
| **D1** | 起草 `ExceptionRequest` template（字段：request_id/severity/reason/impact_scope/risk_assessment/rollback_plan/approvers/ttl/status/enable_window/auto_revert_rule/closure_evidence） | ExceptionRequest template |
| **D2** | 起草 `GateEvidenceManifest`（`2.6-G-01..05` 各 gate 的：artifact_path / generated_at / validator / result / contract_scope / exception_link） | GateEvidenceManifest draft |
| **D2** | 设计双层 no-auto-capture / no-auto-processing 采证方案（20 分钟预检 + 24h 正式验收） | 采证方案文档 |
| **D3** | 更新 WebUI contract 文档（ROUTE_MAP / DATAFLOW / pages/audio.md / pages/video.md / CHANGELOG） | WebUI docs（计划态） |
| **D3** | 起草 Rollback Playbook（三类 failure：误开开关 / 异常未回收 / 证据缺失） | Rollback Playbook |
| **D4** | Gate Traceability 自审（`2.6-G-*` 全覆盖检查） | Gate Traceability Matrix |
| **D4** | 填充 Deliverables Checklist + Execution Readiness Checklist；更新 roadmap-status.md Phase 2.6 区块 | 最终审核文档 |
| **D4** | 创建 `phase-2.6-validation.md` 模板 | Validation template |

---

## 5. Work Breakdown（WB）

### WB-01：FreezeScopeMatrix

**Purpose**：定义 Audio Freeze 的五维度 default-deny 边界，使冻结状态可以被审计和验证。

**Dependencies**：ADR-0007（governance interfaces），Phase 2.0 代码目录（模块路径），Phase 2.5 WebUI 实现（UI 入口路径）

**Target Files**：`v3/plan/07-phase-2.6-audio-freeze-governance-detailed-plan.md`（Appendix A）；引用路径同步更新到 `GateEvidenceManifest`

**API/Data Contract Changes**：无。本 WB 为文档产出，不修改任何 API 或数据契约。

**Validation Commands（计划态）**：

```bash
# 核查 FreezeScopeMatrix 中所有 path/key 在代码库中的实际存在性（read-only grep）
grep -Rn "audio_recorder\|audio_manager\|AudioProcessingWorker\|audio_chunks" openrecall/ --include="*.py" | head -50
# 预期：能找到所有矩阵中列出模块路径，证明矩阵覆盖真实代码
```

**FreezeScopeMatrix 结构（计划态内容 — Appendix A）**：

| Dimension | Object | Path/Key | Owner | Risk Tier | Exception Allowed | default_capture_state | default_processing_state | ui_default_visibility | search_chat_modalities |
|-----------|--------|----------|-------|-----------|-------------------|----------------------|------------------------|----------------------|----------------------|
| Capture | `AudioManager` | `openrecall/client/audio_manager.py` | Product Owner | P0 | Yes (with TTL) | **disabled** | N/A | N/A | excluded |
| Capture | `AudioRecorder` | `openrecall/client/audio_recorder.py` | Product Owner | P0 | Yes (with TTL) | **disabled** | N/A | N/A | excluded |
| Capture | `OPENRECALL_AUDIO_*` config keys | `openrecall/shared/config.py` | Product Owner | P0 | Yes (with TTL) | **disabled** | N/A | N/A | excluded |
| Processing | `VoiceActivityDetector` | `openrecall/server/audio/vad.py` | Product Owner | P0 | Yes (with TTL) | N/A | **disabled** | N/A | excluded |
| Processing | `WhisperTranscriber` | `openrecall/server/audio/transcriber.py` | Product Owner | P0 | Yes (with TTL) | N/A | **disabled** | N/A | excluded |
| Processing | `AudioChunkProcessor` | `openrecall/server/audio/processor.py` | Product Owner | P0 | Yes (with TTL) | N/A | **disabled** | N/A | excluded |
| Processing | `AudioProcessingWorker` | `openrecall/server/audio/worker.py` | Product Owner | P0 | Yes (with TTL) | N/A | **disabled** | N/A | excluded |
| Indexing | `audio_transcriptions_fts` | SQLite FTS5 table | Product Owner | P0 | Yes (with TTL) | N/A | **disabled** (write-path paused) | N/A | excluded |
| Retrieval | `search_audio_fts()` | `openrecall/server/search/engine.py` | Chief Architect | P0 | No (vision-only contract) | N/A | N/A | N/A | **vision-only** |
| Retrieval | `/api/v1/timeline` audio items | `openrecall/server/api_v1.py` | Chief Architect | P1 | Debug mode only | N/A | N/A | hidden by default | video-only default |
| UI | `/audio` page entrypoint | `layout.html` nav + `app.py:audio()` | Product Owner | P1 | Debug mode only | N/A | N/A | **hidden (default)** | N/A |
| UI | Audio nav icon | `layout.html` + `icons.html:icon_audio()` | Product Owner | P1 | Debug mode only | N/A | N/A | **hidden (default)** | N/A |

---

### WB-02：ExceptionRequest Workflow

**Purpose**：建立正式的例外申请生命周期，防止"便宜的 ad-hoc 开关"累积成不可审计的冻结漏洞。

**Dependencies**：FreezeScopeMatrix（确定哪些维度 `Exception Allowed = Yes`）

**Target Files**：本计划 Appendix B + `v3/results/phase-2.6-validation.md` Section 4（Governance Evidence）

**API/Data Contract Changes**：无。文档产出。

**ExceptionRequest Template（Appendix B — 计划态结构）**：

```yaml
# ExceptionRequest Template
request_id: "EXC-2.6-{YYYYMMDD}-{SEQ}"
severity: "P0 | P1"               # P0 = capture/processing freeze; P1 = UI visibility
reason: "<业务原因，不超过200字>"
impact_scope:
  dimensions: ["capture | processing | indexing | retrieval | ui"]
  paths: ["openrecall/client/audio_manager.py", ...]
  duration_hours: 24               # 最长 TTL
risk_assessment: "<风险评估，含数据隐私影响>"
rollback_plan: "<回滚步骤，要求 RTO < 2 分钟>"
approvers:
  - role: "Product Owner"
    approved_at: null              # 审批前留空
  - role: "Chief Architect"
    approved_at: null
ttl:
  enable_at: null                  # 批准后填写（ISO-8601 UTC）
  expires_at: null                 # enable_at + duration_hours
  auto_revert_rule: "config reset to freeze-default at expires_at; manual close required to cancel countdown"
status: "PENDING | APPROVED | ACTIVE | CLOSED | OVERDUE"
enable_window:
  start: null
  end: null
closure_evidence:
  revert_timestamp: null           # 实际回滚时间
  revert_confirmed_by: null        # 操作者
  no_drift_check: null             # grep 证据快照
  gate_reaudit_required: false     # 若开窗期间有代码改动则为 true
```

**审批流程（计划态）**：

```
申请者  ──► PENDING ──► Product Owner review ──► APPROVED ──► ACTIVE (enable_window)
                                                              │
                                                              ▼
                                               TTL 到期或手动关闭 ──► CLOSED
                                                              │
                                               超期未关 ──► OVERDUE ──► 触发 2.6-G-04 NO-GO
```

---

### WB-03：GateEvidenceManifest

**Purpose**：将每个 `2.6-G-*` gate 与可验证的 evidence artifact 绑定，防止"testimony-only"验收。

**Dependencies**：FreezeScopeMatrix（确定 contract_scope 字段），双层采证方案（确定 artifact_path）

**Target Files**：本计划 Section 6 + `v3/results/phase-2.6-validation.md` Section 3

**GateEvidenceManifest（计划态）**：

| Gate ID | Artifact Path（计划） | Generated At（计划） | Validator | Expected Result | Contract Scope | Exception Link |
|---------|----------------------|---------------------|-----------|----------------|---------------|---------------|
| 2.6-G-01 | `v3/evidence/phase2.6/freeze_scope_matrix.md` + `v3/evidence/phase2.6/20m_precheck_report.txt` + `v3/evidence/phase2.6/24h_no_capture_report.txt` | D4（Phase 2.6 执行日） | Product Owner | 20 分钟预检通过，且 24h report 无音频采集事件 | capture freeze | — |
| 2.6-G-02 | `v3/evidence/phase2.6/processing_path_manifest.txt` + `v3/evidence/phase2.6/queue_worker_snapshot.txt` | D4 | Product Owner | 无默认 auto-processing worker 启动；queue 无 PENDING audio 处理记录 | processing freeze | — |
| 2.6-G-03 | `v3/webui/ROUTE_MAP.md`（更新版）+ `v3/webui/DATAFLOW.md`（更新版）+ `v3/webui/pages/audio.md`（更新版） | D3 | Chief Architect | /audio 入口默认不可见；Search/Chat 契约为 vision-only；timeline 目标默认为 video-only | UI/retrieval freeze | — |
| 2.6-G-04 | `v3/evidence/phase2.6/exception_register.yaml` + `closure_evidence` 字段 | D4 | Product Owner | 所有 ExceptionRequest 状态为 CLOSED；无 OVERDUE | exception governance | 见 EXC register |
| 2.6-G-05 | `v3/evidence/phase2.6/drift_audit_report.txt` + `v3/evidence/phase2.6/rollback_drill_log.txt` | D4 | Chief Architect | drift count = 0；rollback drill 完成时间 < 2 分钟；integrity check 通过 | freeze integrity | — |

---

### WB-04：20 分钟预检 + 24h 正式验收采证方案（No-Auto-Capture / No-Auto-Processing）

**Purpose**：提供可重复执行的采证脚本和证据目录结构，供 Phase 2.6 执行阶段填充 `2.6-G-01` 和 `2.6-G-02` 证据。

**Dependencies**：FreezeScopeMatrix（确定采证范围）

**Target Files**：本计划 Appendix C + `phase-2.6-validation.md` Section 4

**API/Data Contract Changes**：无。

**计划态采证命令（Appendix C）**：

```bash
# === 2.6-G-01：20 分钟预检（no-auto-capture）===

# Step 1：记录预检基线
sqlite3 ~/MRS/db/openrecall.db \
  "SELECT COUNT(*) AS baseline_count, MAX(created_at) AS last_created FROM audio_chunks;" \
  > v3/evidence/phase2.6/20m_capture_baseline.txt

# Step 2：启动服务（normal mode，不修改配置）
# ./run_server.sh --debug  # 由执行者手动执行

# Step 3：20 分钟后记录预检终态
sqlite3 ~/MRS/db/openrecall.db \
  "SELECT COUNT(*) AS final_count, MAX(created_at) AS last_created FROM audio_chunks;" \
  > v3/evidence/phase2.6/20m_precheck_report.txt

# 预期：final_count == baseline_count（20 分钟窗口内无新增 audio chunk）

# === 2.6-G-01：24h 正式验收（no-auto-capture）===

# Step 1：记录基线 — audio chunk 数量快照
sqlite3 ~/MRS/db/openrecall.db \
  "SELECT COUNT(*) AS baseline_count, MAX(created_at) AS last_created FROM audio_chunks;" \
  > v3/evidence/phase2.6/24h_capture_baseline.txt

# Step 2：启动服务（normal mode，不修改配置）
# ./run_server.sh --debug  # 由执行者手动执行

# Step 3：24h 后记录终态 — audio chunk 数量对比
sqlite3 ~/MRS/db/openrecall.db \
  "SELECT COUNT(*) AS final_count, MAX(created_at) AS last_created FROM audio_chunks;" \
  >> v3/evidence/phase2.6/24h_no_capture_report.txt

# 预期：final_count == baseline_count（无新增 audio chunk）

# Step 4：检查 audio 相关进程未运行
ps aux | grep -E "audio_recorder|audio_manager|AudioRecorder" | grep -v grep \
  >> v3/evidence/phase2.6/24h_no_capture_report.txt
# 预期：空输出（无相关进程）

# === 2.6-G-02：20 分钟预检（no-auto-processing）===

# Step 1：记录预检基线 — 同一指标用于前后对比
sqlite3 ~/MRS/db/openrecall.db "
  SELECT
    (SELECT COUNT(*) FROM audio_transcriptions) AS transcriptions_baseline,
    (SELECT COUNT(*) FROM audio_chunks WHERE status = 'PENDING') AS pending_baseline;
" > v3/evidence/phase2.6/20m_processing_baseline.txt

# Step 2：20 分钟后对比终态（与基线保持同一指标）
sqlite3 ~/MRS/db/openrecall.db "
  SELECT
    (SELECT COUNT(*) FROM audio_transcriptions) AS transcriptions_final,
    (SELECT COUNT(*) FROM audio_chunks WHERE status = 'PENDING') AS pending_final;
" > v3/evidence/phase2.6/20m_processing_precheck_report.txt

# 预期：transcriptions_final == transcriptions_baseline（无新增转写）
#       pending_final 与 pending_baseline 无异常增长

# === 2.6-G-02：24h 正式验收（no-auto-processing）===

# Step 1：记录基线 — audio_transcriptions 数量 + PENDING chunk 数量
sqlite3 ~/MRS/db/openrecall.db "
  SELECT
    (SELECT COUNT(*) FROM audio_transcriptions) AS transcriptions_baseline,
    (SELECT COUNT(*) FROM audio_chunks WHERE status = 'PENDING') AS pending_baseline;
" > v3/evidence/phase2.6/24h_processing_baseline.txt

# Step 2：24h 后对比到终态
sqlite3 ~/MRS/db/openrecall.db "
  SELECT
    (SELECT COUNT(*) FROM audio_transcriptions) AS transcriptions_final,
    (SELECT COUNT(*) FROM audio_chunks WHERE status = 'PENDING') AS pending_final;
" >> v3/evidence/phase2.6/queue_worker_snapshot.txt

# 预期：transcriptions_final == transcriptions_baseline（无新增转写）
#       pending_final 与 pending_baseline 无异常增长（无 worker 自动处理）

# === 2.6-G-05：Drift Audit（freeze scope 漂移检查）===

# Phase 2.6 execution window start (UTC). If schedule changes, update this one value only.
PHASE26_START_UTC="2026-02-25T00:00:00Z"

# Step 1：确认 audio 相关模块路径无未授权变更
git log --oneline --since="$PHASE26_START_UTC" -- \
  openrecall/client/audio_manager.py \
  openrecall/client/audio_recorder.py \
  openrecall/server/audio/ \
  openrecall/shared/config.py \
  > v3/evidence/phase2.6/drift_audit_report.txt
# 预期：空输出（无新 commit；或仅有 Phase 2.6 文档类 commit）

# Step 2：确认 OPENRECALL_AUDIO_* 配置键未被修改
grep -Rn "OPENRECALL_AUDIO" openrecall/shared/config.py \
  >> v3/evidence/phase2.6/drift_audit_report.txt

# === 采证目录结构 ===
# v3/evidence/phase2.6/
#   freeze_scope_matrix.md           （WB-01 产出的副本/链接）
#   20m_capture_baseline.txt         （20 分钟预检基线）
#   20m_precheck_report.txt          （20 分钟预检结果）
#   24h_capture_baseline.txt         （Step 1 输出）
#   24h_no_capture_report.txt        （Step 3+4 输出）
#   20m_processing_baseline.txt      （20 分钟 processing 预检基线）
#   20m_processing_precheck_report.txt（20 分钟 processing 预检结果）
#   24h_processing_baseline.txt      （Step 1 输出）
#   queue_worker_snapshot.txt        （Step 2 输出）
#   processing_path_manifest.txt     （grep audio worker 代码路径确认）
#   exception_register.yaml          （ExceptionRequest 记录）
#   drift_audit_report.txt           （grep 漂移审计结果）
#   rollback_drill_log.txt           （回滚演练记录）
```

**计划态证据目录结构**：

```
v3/evidence/phase2.6/
├── freeze_scope_matrix.md          # FreezeScopeMatrix 定稿
├── 20m_capture_baseline.txt        # 20 分钟预检：音频 chunk 基线
├── 20m_precheck_report.txt         # 20 分钟预检：capture 结果
├── 24h_capture_baseline.txt        # 音频 chunk 基线快照
├── 24h_no_capture_report.txt       # 24h 无自动采集证明
├── 20m_processing_baseline.txt     # 20 分钟预检：processing 基线
├── 20m_processing_precheck_report.txt # 20 分钟预检：processing 结果
├── 24h_processing_baseline.txt     # 转写记录基线快照
├── queue_worker_snapshot.txt       # worker 状态快照
├── processing_path_manifest.txt    # 处理链路代码路径确认
├── exception_register.yaml         # ExceptionRequest 记录本
├── drift_audit_report.txt          # 漂移审计报告
└── rollback_drill_log.txt          # 回滚演练日志
```

---

### WB-05：WebUI Contract 对齐

**Purpose**：更新 WebUI 契约文档，使 audio/video 页面的可见性、入口、文案、状态标识与冻结契约精确对齐。
所有更新均为 **Planned/Proposed** 状态，不写 Done/Pass/Complete/GO。

**Dependencies**：FreezeScopeMatrix（确认 `/audio` 入口 `ui_default_visibility = hidden`），ADR-0005（Search/Chat vision-only），ADR-0007（timeline target default video-only）

**Target Files**：
- `v3/webui/ROUTE_MAP.md`（更新 Current vs Target 表格）
- `v3/webui/DATAFLOW.md`（更新 Target Dataflow + 维护规则）
- `v3/webui/pages/audio.md`（追加 Section 10 Phase 2.6 Freeze Status）
- `v3/webui/pages/video.md`（追加 Section 10 Phase 2.6 对比说明）
- `v3/webui/CHANGELOG.md`（追加 Phase 2.6 条目）

**API/Data Contract Changes（计划态）**：

| Interface | Current Behavior | Phase 2.6 Target Contract | Convergence Phase |
|-----------|-----------------|--------------------------|------------------|
| `/audio` page visibility | 可见（nav icon 常驻） | **默认隐藏**；仅 debug 模式或批准的 ExceptionRequest 激活期间可见 | Phase 2.6 contract docs |
| Navigation audio icon | 5-page toolbar 常驻 | **Phase 2.6 target：默认不渲染**；合规行为留 Phase 3 收敛 | Phase 3 |
| `GET /api/v1/timeline` audio items | mixed 默认（video + audio） | **target default：video-only**；audio 仅 explicit `source=audio` + debug 模式 | Phase 3 |
| `GET /api/v1/search` audio FTS | SearchEngine 仍有 audio FTS 路径 | **target：vision-only**；audio FTS 路径需在 Phase 3 关闭 | Phase 3 |

> 注：Current Behavior 对应代码现状，不在 Phase 2.6 期间修改；Phase 2.6 只发布 **target contract 文档**，代码收敛发生在 Phase 3。

**Validation Commands（计划态）**：

```bash
# 验证 5 个 WebUI 文件均已更新并包含 Phase 2.6 标注
grep -l "Phase 2.6" \
  v3/webui/CHANGELOG.md \
  v3/webui/ROUTE_MAP.md \
  v3/webui/DATAFLOW.md \
  v3/webui/pages/audio.md \
  v3/webui/pages/video.md
# 预期：5 行（每个文件各一行）
```

---

### WB-06：Failure Signals 与 Rollback Playbook

**Purpose**：为三类主要治理失效场景提供明确的应急响应路径。

**Target Files**：本计划 Section 8 + `phase-2.6-validation.md` Section 5

**Rollback Playbook（计划态）**：

**场景 A：误开音频采集开关**

```
触发条件：AudioManager / AudioRecorder 在未批准的 ExceptionRequest 下被激活
响应步骤：
  1. 立即停止相关进程（kill PID 或 stop AudioManager）
  2. 检查 audio_chunks 新增数量（sqlite3 query）
  3. 若有新增：执行 delete_audio_chunk_cascade() 清理
  4. 记录 incident 到 exception_register.yaml（status: OVERDUE / UNAUTHORIZED）
  5. 触发 2.6-G-01 重验证
  6. 通知 Product Owner + Chief Architect
RTO 目标：< 2 分钟（停止进程；不含数据清理时间计入 RTO）
```

**场景 B：ExceptionRequest 异常未回收（超过 TTL）**

```
触发条件：exception_register.yaml 中存在 status=ACTIVE 且 expires_at < now()
响应步骤：
  1. 检测：grep ACTIVE exception_register.yaml 并比对 expires_at
  2. 执行 auto_revert_rule 中定义的回滚步骤
  3. 将 status 更新为 OVERDUE
  4. 生成 closure_evidence（包含 revert_timestamp + operator）
  5. 触发 2.6-G-04 重验证
RTO 目标：< 2 分钟（配置重置）
```

**场景 C：Evidence 缺失或过期**

```
触发条件：GateEvidenceManifest 中某 gate 的 artifact_path 文件不存在或 generated_at > 7天
响应步骤：
  1. 识别缺失 gate（ls -la v3/evidence/phase2.6/）
  2. 重新执行对应 WB 的采证命令（WB-04 命令集）
  3. 更新 GateEvidenceManifest 中 generated_at
  4. 重置 phase-2.6-validation.md 对应行的 result 为 Pending
  5. 通知 review owner 重审
```

---

### WB-07：Gate Traceability 自审

**Purpose**：确认所有文档产出与 `2.6-G-*` 完整对齐，无 gate 无主或证据路径断链。

**Target Files**：本计划 Section 6

**执行方式**：D4 对照 `v3/metrics/phase-gates.md` `2.6-G-*` 逐条确认文档覆盖度。

**Validation Commands（计划态）**：

```bash
# 确认 2.6-G-* 全部在本文档中有对应 WB 和 evidence artifact
grep "2.6-G-0" v3/plan/07-phase-2.6-audio-freeze-governance-detailed-plan.md | wc -l
# 预期：>= 25（5 个 gate 各被引用多次，证明全覆盖）
```

---

## 6. Gate Traceability Matrix

> Gate 定义来源：`v3/metrics/phase-gates.md` Phase 2.6 小节（唯一真源，禁止改写数值）

| Gate ID | Gate 名称 | 验证方式 | Evidence Artifact | WB 编号 | 类型 |
|---------|-----------|---------|------------------|---------|------|
| **2.6-G-01** | Default Capture Pause | 20 分钟预检无新增采集 + 24h 正式验收无采集操作报告 | `v3/evidence/phase2.6/freeze_scope_matrix.md` + `20m_precheck_report.txt` + `24h_no_capture_report.txt` | WB-01 + WB-04 | **GATING** |
| **2.6-G-02** | Default Processing Pause | processing path manifest + queue/worker 快照显示无默认 auto-processing | `v3/evidence/phase2.6/processing_path_manifest.txt` + `queue_worker_snapshot.txt` | WB-01 + WB-04 | **GATING** |
| **2.6-G-03** | UI and Retrieval Contract | WebUI 契约文档（ROUTE_MAP + DATAFLOW + pages/audio.md）+ API 契约说明 | `v3/webui/ROUTE_MAP.md`（更新版）、`DATAFLOW.md`（更新版）、`pages/audio.md`（Section 10） | WB-05 | **GATING** |
| **2.6-G-04** | Exception Closure | ExceptionRequest register 无 OVERDUE；所有 CLOSED 项含 closure_evidence | `v3/evidence/phase2.6/exception_register.yaml` | WB-02 + WB-06 | **GATING** |
| **2.6-G-05** | Drift and Rollback Readiness | drift audit = 0 unauthorized changes；rollback drill < 2 min | `v3/evidence/phase2.6/drift_audit_report.txt` + `rollback_drill_log.txt` | WB-03 + WB-06 | **GATING** |
| 2.6-NG-01 | FreezeScopeMatrix 模块路径覆盖完整性 | grep 确认矩阵中所有路径在 codebase 中存在 | grep 输出 | WB-01 | Non-Gating |
| 2.6-NG-02 | ExceptionRequest template 字段完整性 | 字段与 ADR-0007 governance interfaces 对齐核查 | ADR-0007 字段对比 | WB-02 | Non-Gating |
| 2.6-NG-03 | GateEvidenceManifest 与 gates 一对一覆盖 | manifest 行数 >= 5（每个 G-* gate 一行） | manifest 文档行数检查 | WB-03 | Non-Gating |
| 2.6-NG-04 | Rollback Playbook 覆盖三类场景 | playbook 含场景 A/B/C 各有 RTO 目标 | 本文档 WB-06 | WB-06 | Non-Gating |
| 2.6-NG-05 | WebUI 文档（5 个文件）全部更新 | 检查更新日期 + Phase 2.6 标注存在 | CHANGELOG 条目 + 各页面标注 | WB-05 | Non-Gating |

**Gate Summary（计划态）**：5 GATING + 5 Non-Gating = 10 checks
**评估时点**：D4 Review（Go/No-Go 评审）

---

## 7. Test & Verification Plan

### 7.1 Unit（文档完整性检查）

| 检查项 | 命令（计划态） | 通过标准 |
|--------|-------------|---------|
| FreezeScopeMatrix 模块路径存在验证 | `grep -Rn "AudioManager\|AudioRecorder\|AudioChunkProcessor\|AudioProcessingWorker\|search_audio_fts" openrecall/ --include="*.py"` | 所有矩阵中列出的路径对应代码存在 |
| ExceptionRequest YAML 结构校验 | `python3 -c "import yaml; yaml.safe_load(open('v3/evidence/phase2.6/exception_register.yaml'))"` | 无解析错误 |
| GateEvidenceManifest 覆盖完整性 | `awk '/2\\.6-G-0/{n++} END{print n}' v3/plan/07-phase-2.6-*.md` | >= 25 行（5 gate × 多次引用） |

### 7.2 Integration（数据库状态核查）

| 检查项 | 命令（计划态） | 通过标准 |
|--------|-------------|---------|
| 20 分钟预检：无新增 audio_chunk | `sqlite3 ~/MRS/db/openrecall.db "SELECT COUNT(*) FROM audio_chunks"` 对比 20m 基线 | delta = 0 |
| 20 分钟预检：无新增 audio_transcription | `sqlite3 ~/MRS/db/openrecall.db "SELECT COUNT(*) FROM audio_transcriptions"` 对比 20m 基线 | delta = 0 |
| 24h 正式验收：无新增 audio_chunk | `sqlite3 ~/MRS/db/openrecall.db "SELECT COUNT(*) FROM audio_chunks"` 对比 24h 基线 | delta = 0 |
| 24h 正式验收：无新增 audio_transcription | `sqlite3 ~/MRS/db/openrecall.db "SELECT COUNT(*) FROM audio_transcriptions"` 对比 24h 基线 | delta = 0 |
| 20m/24h 两窗口：audio_chunks PENDING 数未异常增长 | `sqlite3 ~/MRS/db/openrecall.db "SELECT COUNT(*) FROM audio_chunks WHERE status='PENDING'"` | delta <= 0 或按白名单波动解释 |

### 7.3 API Smoke（契约不含音频候选验证）

| 检查项 | 命令（计划态） | 通过标准 |
|--------|-------------|---------|
| `/api/v1/search` 默认不返回音频结果 | `curl "http://localhost:8083/api/v1/search?q=test&start_time=1"` | `items` 中无 `type=audio_transcription` |
| `/api/v1/timeline` 目标默认不含音频条目 | `curl "http://localhost:8083/api/v1/timeline?start_time=1"` | target contract = video-only（Current 为 mixed，已知 deviation，Phase 3 收敛） |
| `/audio` 页面 HTTP 状态（历史兼容） | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8083/audio` | 200（页面仍可访问；nav 入口默认隐藏为 Target contract，Phase 3 代码收敛） |

> 注：Timeline API current 实现仍返回 mixed，与 Target contract 存在偏差（已知 deviation），不影响 Phase 2.6 Go/No-Go。

### 7.4 Manual（人工审计）

| 检查项 | 执行者 | 通过标准 |
|--------|--------|---------|
| FreezeScopeMatrix 五维度全覆盖 | Product Owner | 所有行 `default_capture_state` 或 `default_processing_state` 为 "disabled" 或 N/A |
| ExceptionRequest register 状态核查 | Product Owner | 无 ACTIVE/OVERDUE 项（Phase 2.6 执行期无 exception 则为空 register） |
| Rollback Drill 执行记录 | Chief Architect | `rollback_drill_log.txt` 包含完成时间戳，实际时间 < 2 分钟 |
| WebUI 文档 Phase 2.6 标注存在 | Chief Architect | 5 个 WebUI 文件均含 "Phase 2.6" 相关条目，且状态标注为 Planned/Proposed |

### 7.5 Governance Audit（治理完整性）

| 检查项 | 通过标准 |
|--------|---------|
| GateEvidenceManifest 5 行（`2.6-G-01..05`）全部有 `artifact_path` + `validator` 填写 | 完整（无空字段） |
| 所有 gate evidence artifact 文件存在于 `v3/evidence/phase2.6/` | `ls v3/evidence/phase2.6/` 含所有计划文件 |
| Blocking Decisions（Section 12）所有 owner + target date 已填写 | 完整（允许 Pending Answer） |

---

## 8. Risks / Failure Signals / Fallback

| # | Risk | Failure Signal | Fallback / Mitigation |
|---|------|---------------|----------------------|
| R-01 | 采证命令执行时发现 AudioProcessingWorker 自动启动（server 启动脚本未屏蔽） | 20 分钟预检或 24h report 期间 audio_transcriptions delta > 0 | 立即停止 worker 进程；触发 WB-06 场景 A playbook；记录 incident；重新采证 |
| R-02 | ExceptionRequest 申请 TTL 过期但未关闭，变为 OVERDUE | `exception_register.yaml` 存在 status=ACTIVE 且 expires_at < now() | 触发 WB-06 场景 B playbook；自动回滚到冻结基线；向 Product Owner 报警 |
| R-03 | Evidence artifact 文件在 Git 提交前意外丢失（tmp 目录回收） | `ls v3/evidence/phase2.6/` 所需文件缺失 | 触发 WB-06 场景 C；重新执行 WB-04 采证命令；Gate 审核时间后延 |
| R-04 | WebUI 文档更新与代码现实存在偏差（contract 写了"hidden"但代码尚未收敛） | ROUTE_MAP.md 中 Target 列与 Current 列不一致 | 在文档中明确标注"Current Behavior（Pending Convergence in Phase 3）"，不视为 2.6-G-03 失败 |
| R-05 | Rollback Drill 超时（实际操作 > 2 分钟） | `rollback_drill_log.txt` 完成时间超标 | 分析操作瓶颈；优化 playbook 步骤；增补快捷命令；重新演练直至达标 |
| R-06 | FreezeScopeMatrix 遗漏音频相关 config key（如 `OPENRECALL_AUDIO_ENABLED`） | Phase 2.6 执行时 grep 发现未覆盖的 audio config key 被读取 | 补充矩阵条目；标记为 P0 级别；若已实际影响行为则触发 R-01 playbook |
| R-07 | Phase 2.7 过早启动（未等 Phase 2.6 GO） | roadmap-status.md Phase 2.7 变更为 In Progress 时 Phase 2.6 状态仍为 Not Started/In Progress | Hard block：Phase 2.7 任何工程变更必须附 `2.6-G-* all PASS` 证明；否则 revert Phase 2.7 变更 |
| R-08 | 文档版本漂移（WebUI 文档与 phase-gates.md 不同步） | ROUTE_MAP 或 DATAFLOW 中 Target 列描述与 phase-gates.md `2.6-G-03` 标准不一致 | D4 审计时逐条比对；发现不一致立即修订；不允许以 narrative 覆盖 gate 定义 |
| R-09 | Phase 2.6 执行期间有代码变更意外触及 audio 模块（如 PR merge） | `git log --oneline` 显示 audio 相关文件有新 commit | 触发 drift_audit；追加 exception_register 记录；重新验证 2.6-G-05 |
| R-10 | Product Owner / Chief Architect 不可用导致 ExceptionRequest 无法获得第二签名 | `approvers[1].approved_at = null` 在 enable_window.start 之前 | 单一 approver（Product Owner）可临时授权 P1 级别 exception；P0 级别需双签，否则 exception 状态为 PENDING，操作不可进行 |

---

## 9. Deliverables Checklist

> 全部为计划态，不写 Done/Pass/Complete/GO。

| # | Deliverable | File Path | 状态 | Due |
|---|-------------|-----------|------|-----|
| D-01 | 本计划文档（详细计划） | `v3/plan/07-phase-2.6-audio-freeze-governance-detailed-plan.md` | Planned | D1 |
| D-02 | FreezeScopeMatrix | Appendix A（本文档内）+ `v3/evidence/phase2.6/freeze_scope_matrix.md`（执行期） | Planned | D1 |
| D-03 | ExceptionRequest template + register | Appendix B（本文档内）+ `v3/evidence/phase2.6/exception_register.yaml`（执行期） | Planned | D1 |
| D-04 | GateEvidenceManifest | Section 6（本文档）+ `v3/results/phase-2.6-validation.md` Section 3 | Planned | D2 |
| D-05 | 双层采证方案（20 分钟预检 + 24h 正式验收） | Appendix C（本文档内） | Planned | D2 |
| D-06 | WebUI contract 更新（5 个文件） | `v3/webui/CHANGELOG.md`, `ROUTE_MAP.md`, `DATAFLOW.md`, `pages/audio.md`, `pages/video.md` | Planned | D3 |
| D-07 | Rollback Playbook（3 场景） | Section 8 + WB-06 | Planned | D3 |
| D-08 | `phase-2.6-validation.md` 模板 | `v3/results/phase-2.6-validation.md` | Planned | D4 |
| D-09 | roadmap-status.md Phase 2.6 区块更新 | `v3/milestones/roadmap-status.md` | Planned | D4 |

---

## 10. Execution Readiness Checklist（<= 10 条）

> Go/No-Go 执行前必须全部确认。

- [ ] Phase 2.5 验收报告（`v3/results/phase-2.5-validation.md`）确认为 GO 状态
- [ ] ADR-0007 已处于 Accepted 状态（不是 Draft/Proposed）
- [ ] `v3/metrics/phase-gates.md` `2.6-G-*` 节已存在（不允许执行时新增 gate）
- [ ] `v3/evidence/phase2.6/` 目录已创建（或确认可写权限）
- [ ] SQLite DB 路径可访问（`~/MRS/db/openrecall.db` 或等效路径）
- [ ] Product Owner 和 Chief Architect 均已收到本计划文档并确认
- [ ] Phase 2.7 未进入 In Progress 状态（防止乱序执行）
- [ ] 本计划文档（本文件）已落盘到 `v3/plan/07-*.md`
- [ ] Blocking Decisions（Section 12）中所有 P0 Decision 已有初步答案或明确 Pending
- [ ] WebUI docs（5 个文件）已更新到计划态内容（CHANGELOG 条目存在）

---

## 11. Documentation Sync Matrix

| 文档 | 更新时点 | 更新内容 | Owner |
|------|---------|---------|-------|
| `v3/plan/07-phase-2.6-*.md`（本文档） | D1（初稿）→ D4（定稿） | 全量创建 | Chief Architect |
| `v3/milestones/roadmap-status.md` | D4 | Phase 2.6 区块：status/timeline/dependencies/blockers/open questions | Product Owner |
| `v3/webui/CHANGELOG.md` | D3 | 追加 Phase 2.6 条目（计划态） | Chief Architect |
| `v3/webui/ROUTE_MAP.md` | D3 | Current vs Target 表格新增 Phase 2.6 Contract Note 列 | Chief Architect |
| `v3/webui/DATAFLOW.md` | D3 | Target Dataflow 第 6 条（Audio Freeze 全链路契约）+ 维护规则 | Chief Architect |
| `v3/webui/pages/audio.md` | D3 | 追加 Section 10（Phase 2.6 Freeze Status） | Chief Architect |
| `v3/webui/pages/video.md` | D3 | 追加 Section 10（Phase 2.6 对比说明） | Chief Architect |
| `v3/results/phase-2.6-validation.md` | D4（模板）→ 执行期（填充） | 创建模板；执行期填充证据 | Product Owner |
| `v3/evidence/phase2.6/*.txt/yaml` | D4（采证执行） | 实际采证产出 | Product Owner |
| `v3/metrics/phase-gates.md` | **禁止在 Phase 2.6 期间改写** | 只读引用 | N/A |

---

## 12. Blocking Decisions & Assumptions

| # | Decision / Question | Impact | Owner | Target Date | Status |
|---|---------------------|--------|-------|------------|--------|
| BD-01 | **Rollback RTO 目标是否需从 "< 2 分钟" 放宽到 "< 5 分钟"（若服务器环境配置复杂）？** | 影响 2.6-G-05 通过标准；不允许改写 gate，只允许在执行中确认是否满足 | Product Owner | D1 | Pending Answer |
| BD-02 | **Phase 2.6 执行期间是否有任何 P0/P1 ExceptionRequest 需要预申请（如 debug 录音测试）？** | 影响 exception_register 初始状态；若有则 D1 需同步起草 ExceptionRequest 表单 | Product Owner | D1 | Pending Answer |
| BD-03 | **`/audio` Navigation icon 的"默认隐藏"是否需在 Phase 2.6 期间通过代码变更实现，还是仅作为 Target Contract 文档声明，收敛到 Phase 3？** | 若需立即实现则 Phase 2.6 需增加代码改动（当前计划 Code changes: NONE）；若推迟到 Phase 3 则文档标注 "Pending Phase 3 convergence" | Chief Architect | D2 | Pending Answer；默认假设：文档声明 + Phase 3 收敛，Code changes: NONE |
| BD-04 | **Drift Audit 的"漂移"定义范围是否仅限于 audio 模块文件，还是包含所有引用 audio 路径的配置文件和启动脚本？** | 影响 2.6-G-05 drift_audit_report 的搜索范围 | Chief Architect | D2 | Pending Answer；默认假设包含 `.sh`、`.env`、`config/` 目录 |
| BD-05 | **`v3/evidence/phase2.6/` 目录是否需要纳入 Git 版本控制（证据文件可能含系统输出）？** | 影响 Execution Readiness 第 4 条；若不纳入 Git 则需额外备份方案 | Product Owner | D1 | Pending Answer；默认假设：纳入 Git，忽略 `.gitignore` 中临时文件规则 |

**Assumptions（已做假设，无 owner）**：

1. Phase 2.6 遵从 ADR-0001（Python-first），本阶段无 Rust/其他语言改动。
2. ADR-0002 remote-first contract（`/api/v1`、pagination、stateless、auth placeholder）在 Phase 2.6 期间不改变。
3. `v3/metrics/phase-gates.md` `2.6-G-*` gate 定义在 Phase 2.6 执行期间不改写（immutable gate authority）。
4. Phase 2.5 Go/No-Go = GO 为已知事实（`v3/results/phase-2.5-validation.md` 已确认，non-negotiable input）。
5. 所有文档产出状态为 Planned/Proposed，验收结论（PASS/GO）由 Phase 2.6 实际执行填充，不在本计划文档中预写。

---

## 13. Last Updated

**Date**: 2026-02-25
**Author**: Planning Agent（GitHub Copilot）
**Version**: 1.0
**Status**: Planned（待执行确认后更新为 In Execution）
