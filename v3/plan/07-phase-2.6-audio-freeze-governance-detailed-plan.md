# Phase 2.6: Audio Hard Shutdown — Detailed Roadmap

**Version**: 2.0
**Status**: Completed (2026-02-26)
**Last Updated**: 2026-02-26
**Supersedes**: 本文件历史版本（Audio Freeze Governance v1.0，治理+例外开窗方案）

---

## 1. Roadmap Positioning

Phase 2.6 从本版开始不再是“治理冻结阶段”，而是**音频链路硬停机阶段**。
目标是将音频从当前和后续 MVP 主链路中完全摘除，形成可执行、可验证、不可绕行的统一契约。

**Hard Gate Policy**: Phase 2.7 不得启动，直到 Phase 2.6 全部 gate PASS。

---

## 2. Hard Contract (MUST)

Phase 2.6 结束时，系统必须同时满足以下约束：

1. **不采集**：系统音频与麦克风均不自动采集，不存在默认开启路径。
2. **不处理**：VAD、转写、音频处理 worker、音频索引写入全部停止。
3. **不检索**：timeline、search 不使用 audio 数据。
4. **不展示**：主导航与主产品路径不暴露 audio 能力入口。
5. **无例外开窗**：移除旧版 ExceptionRequest 治理逻辑，不保留临时启用音频的产品内流程。

---

## 3. Goals / Non-Goals

### Goals

- 将 audio 相关模块从 MVP 运行链路中彻底隔离。
- 将 Search / Timeline 收敛为 vision-only 合同。
- 保留历史 audio 数据仅用于离线审计，不进入产品主路径。
- 输出可追踪 gate 证据，支撑 Phase 2.7 启动评审。

### Non-Goals

- 不新增任何音频能力。
- 不做 Speaker ID、音频质量优化、音频检索优化。
- 不把历史 audio 数据迁移进新的检索或聊天证据链。
- 不通过“配置开关”保留生产可用音频回路。

---

## 4. Scope (In / Out)

### In Scope

- 客户端音频采集入口下线（manager/recorder/startup wiring）。
- 服务端音频处理链路下线（VAD/transcriber/processor/worker/scheduler）。
- 音频索引写入和检索路径下线（audio FTS write/read path）。
- timeline/search 的音频分支移除或强制禁用。
- WebUI 音频入口与音频页面从 MVP 主导航移除。
- 回归测试与 gate 证据补齐。
- 文档与契约统一（roadmap/gates/validation/webui contract）。

### Out of Scope

- 历史音频数据物理删除（可留存于 DB 作为历史记录）。
- Phase 2.7 的 frame label 对齐实施。
- Phase 3/4 的新功能开发。

---

## 5. Workstreams

### WB-01 Capture Shutdown

**Objective**: 关闭所有音频采集源和触发入口。
**Primary Targets**:
- `openrecall/client/audio_manager.py`
- `openrecall/client/audio_recorder.py`
- 客户端启动/模式调度中对 audio 的挂载点

**Done Criteria**:
- 默认运行不创建任何新 audio chunk。
- 采集线程/进程不存在音频分支。

### WB-02 Processing & Indexing Shutdown

**Objective**: 关闭音频处理与索引写链路。
**Primary Targets**:
- `openrecall/server/audio/`
- 音频处理调度入口
- `audio_transcriptions` / `audio_transcriptions_fts` 写入路径

**Done Criteria**:
- 无自动 VAD/transcribe/processor worker 执行。
- 无新 audio transcription 与音频 FTS 写入。

### WB-03 Retrieval Contract Hard Cut

**Objective**: timeline/search 不再消费音频数据。
**Primary Targets**:
- `openrecall/server/api_v1.py`
- `openrecall/server/search/`

**Done Criteria**:
- `timeline` 默认仅视频证据。
- `search` 不返回音频候选。

### WB-04 UI Surface Removal

**Objective**: 产品 UI 主路径不暴露 audio 能力。
**Primary Targets**:
- `v3/webui/ROUTE_MAP.md`
- `v3/webui/DATAFLOW.md`
- `v3/webui/pages/audio.md`
- Web 模板导航文档与实现对应路径

**Done Criteria**:
- 主导航无 `/audio` 入口。
- 文档与实现一致反映“Audio Disabled”。

### WB-05 Config & Runtime Guardrails

**Objective**: 防止通过遗留配置恢复音频主链路。
**Primary Targets**:
- `openrecall/shared/config.py`
- 运行时模式解析逻辑

**Done Criteria**:
- 音频相关环境变量不再驱动主链路行为。
- 非法音频模式请求被拒绝或降级到 vision-only。

### WB-06 Validation & Evidence

**Objective**: 以 gate 证据证明音频链路已硬停机。
**Primary Targets**:
- `v3/results/phase-2.6-validation.md`
- `v3/evidence/phase2.6/`

**Done Criteria**:
- 所有 `2.6-G-*` gate 均有证据并 PASS。

---

## 6. New Gates (Replaces Old 2.6 Semantics)

> 本节定义 Phase 2.6 新 gate 语义；旧的“Exception closure / governance window”语义全部废弃。

| Gate ID | Name | PASS Criteria |
|---|---|---|
| `2.6-G-01` | Capture Off | 24h 运行窗口内新增 `audio_chunks = 0` |
| `2.6-G-02` | Processing Off | 24h 窗口内新增 `audio_transcriptions = 0` 且无音频处理 worker 活跃 |
| `2.6-G-03` | Retrieval Off | timeline/search 接口返回中音频项数量为 0（默认与标准路径） |
| `2.6-G-04` | UI Off | 主导航和主页面流无 audio 入口，产品文案与契约一致 |
| `2.6-G-05` | Anti-Bypass Guard | 配置与运行模式无法恢复音频主链路；相关回归测试全部通过 |

---

## 7. Day-by-Day Execution Plan

| Day | Focus | Deliverables |
|---|---|---|
| D1 | Contract freeze + scope lock | 本路线图定稿；目标文件清单；旧语义废弃清单 |
| D2 | Capture/Processing shutdown implementation | WB-01 / WB-02 完成，单测更新 |
| D3 | Retrieval/UI decouple | WB-03 / WB-04 完成，接口与页面回归通过 |
| D4 | Config guardrails + regression | WB-05 完成，关键回归套件通过 |
| D5 | Evidence & Go/No-Go package | WB-06 完成，`2.6-G-*` gate 评审 |

---

## 8. Testing Strategy

### Required Test Buckets

- `tests/test_phase2_timeline.py`: 验证默认不含音频。
- `tests/test_phase2_search.py`: 验证搜索结果不含音频。
- `tests/test_phase25_*`: 验证 UI 导航不暴露 audio 主入口。
- 新增/更新 `phase2.6` gate 测试：覆盖 `2.6-G-01..05`。

### Validation Commands (Template)

```bash
python3 -m pytest tests/test_phase2_timeline.py -v
python3 -m pytest tests/test_phase2_search.py -v
python3 -m pytest tests/test_phase25_navigation.py -v
python3 -m pytest -k "phase2 and gate" -v
```

---

## 9. Risks and Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| 音频残留路径遗漏 | timeline/search 污染 | 按 WB-03 逐路径审计 + gate 自动化 |
| UI 文档与实现不一致 | 用户认知混乱 | WB-04 同步改文档和实现并做截图审查 |
| 旧配置绕过 | 音频链路被误恢复 | WB-05 强制降级/拒绝 + 回归测试 |

---

## 10. Exit Criteria

Phase 2.6 仅在以下条件全部满足时可判定 GO：

- `2.6-G-01..05` 全部 PASS。
- 验证报告与证据目录完整。
- roadmap-status 和 gate 文档已同步为“Audio Hard Shutdown”语义。
- Phase 2.7 启动前审查确认：timeline/search 为 vision-only。

---

## 11. Supersession Note

自本版本起，以下旧语义全部失效：

- “Audio Freeze Governance”作为主路线语义。
- ExceptionRequest（审批/TTL/auto-revert/closure evidence）作为 Phase 2.6 必需机制。
- 任何“临时开窗可恢复 audio 主链路”的产品内流程。

Phase 2.6 的唯一目标是：**把 audio 从运行主链路彻底拿掉**。
