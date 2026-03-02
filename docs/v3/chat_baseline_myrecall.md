# MyRecall-v3 Chat 当前方案基线摘要

- 版本：v1.1
- 日期：2026-03-01
- 适用范围：Chat 功能架构评审，与 `spec.md`、`ADR-0004`、`roadmap.md`、`gate_baseline.md` 联动
- 用途：作为 Chat 对齐/不对齐分析的 MyRecall-v3 侧基线锚点

---

## 基线项（10 项）


| #       | 基线项                                                                                                                                                                                                                                                                                                      | 证据来源                                                             |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| **B1**  | **Chat 编排（Pi Sidecar + Python Manager）部署在 Edge**，Host 零 Chat 职责。编排层拥有 query planning（由 Pi agent 自主决策）、tool-driven RAG retrieval（via SKILL.md）、citation binding（DA-8 渐进策略）、model routing（Pi `--provider`/`--model`）四大能力。                                                                                  | `spec.md` §3.6; `ADR-0004`（修订）                                   |
| **B2**  | **Pi Sidecar + Python Manager 架构**（DA-7=A，DA-2 修订）。请求为简单 JSON `{message, session_id, images?}`，响应为 SSE 透传 Pi 原生事件（`message_update`/`tool_execution_`*/`agent_start/end`/`response`）。不做 OpenAI format 翻译。内层 Manager ↔ Pi 使用 stdin/stdout JSON Lines（对齐 screenpipe `pi.rs`），外层前端 ↔ Edge 使用 HTTP SSE（拓扑适配）。 | `spec.md` §3.6; `ADR-0004`（修订）; `open_questions.md` OQ-002=A 修订版 |
| **B3**  | **索引时零 AI 调用**（Decision 014A），所有 grounding 由 Pi agent 在查询时通过 SKILL.md 工具实时完成。Embedding 表仅供离线实验。                                                                                                                                                                                                          | `spec.md` Decision 014A/015A                                     |
| **B4**  | **工具以 Pi SKILL.md 格式定义**（对齐 screenpipe DA-3），P1-S5 最小集为 `myrecall-search` Skill（对标 `screenpipe-search`），通过 `curl` 调用 Edge `/v1/search` FTS 端点。`frame_lookup` 和 `time_range_expansion` 按需在 P1-S7 后拆分为独立 Skill。                                                                                            | `spec.md` §3.6; `ADR-0004`（修订）                                   |
| **B5**  | `**chat_messages` SQLite 表持久化对话**，字段含 `session_id, role, content, citations(JSON), tool_calls(JSON), model, latency_ms`。注：DA-8=A 阶段（P1-S5）`citations` 字段留空，不做结构化 citation 解析；若 DA-8 进入 B 阶段则由 Manager 后处理填充。                                                                                             | `spec.md` §3.0.3 Table 5; `ADR-0004`（修订）DA-8                     |
| **B6**  | **Citation 软 KPI**：P1-S5 ≥85%、P1-S7/P2/P3 ≥92%、Stretch ≥95%；非阻塞 Gate，仅观测。                                                                                                                                                                                                                                | `gate_baseline.md`; `ADR-0004`                                   |
| **B7**  | **Model Routing** 由 Pi `--provider`/`--model` 启动参数 + `models.json` 配置控制（对齐 screenpipe）。P1 不做自动 fallback chain（对齐 screenpipe）。Provider 切换通过配置页面修改 + Manager 重启 Pi 进程生效。Chat first-token P95 ≤ 3.5 s 指标在 P1-S6 验证。                                                                                         | `spec.md` Decision 005A; `ADR-0004`（修订）DA-5; `roadmap.md` P1-S6  |
| **B8**  | **P1-S5（Grounding）→ P1-S6（Routing/Streaming）→ P1-S7（E2E 验证）** 串行 sub-stage 交付。                                                                                                                                                                                                                           | `roadmap.md`; `ADR-0008`                                         |
| **B9**  | **Vision-only scope**，Audio/Speaker 工具不在 P1-P3 范围。                                                                                                                                                                                                                                                       | `spec.md` 文件级范围约束（line 4-5：vision-only + 不含 audio）; `ADR-0005`   |
| **B10** | **UI 留在 Edge**（ADR-0006），Post-P3 才可选迁移至 Host。Chat UI 在 P1 仅需 route reachability + health 可见 + citation click-through。                                                                                                                                                                                    | `ADR-0006`; `ADR-0011`                                           |


---

## 关联锁定决策

以下 Decision 直接约束 Chat 设计，任何变更须走 ADR 流程：


| Decision | 内容                                                              | 影响              |
| -------- | --------------------------------------------------------------- | --------------- |
| 001A     | 与 screenpipe 做行为/能力对齐，不做拓扑对齐                                    | Chat 拓扑可以不同     |
| 002A（修订） | Chat 请求为简单 JSON，响应为 SSE 透传 Pi 原生事件；Tool 以 Pi SKILL.md 格式定义      | API 协议与工具格式锁定   |
| 005A（修订） | Edge 支持 local + cloud 双 provider，P1 无自动 fallback（对齐 screenpipe） | Routing 策略锁定    |
| 013A     | Citation coverage 为软 KPI，非阻塞 Gate                               | 质量观测不卡交付        |
| 014A     | 索引时零 AI 调用                                                      | Grounding 全在查询时 |
| 015A     | Embedding 表仅离线实验                                                | 主路径无向量检索        |


---

## 版本记录


| 版本   | 日期         | 变更                                                                                                                                             |
| ---- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| v1.0 | 2026-03-01 | 初始基线，从 spec.md / ADR-0004 / roadmap.md / gate_baseline.md 提取                                                                                   |
| v1.1 | 2026-03-01 | DA-2/DA-3/DA-5/DA-7/DA-8 决策落地：B2 改为 Pi Sidecar + SSE 透传；B4 改为 SKILL.md 工具格式；B5 补充 DA-8=A citation 留空说明；B7 去除自动 fallback；Decision 表更新 002A/005A |


