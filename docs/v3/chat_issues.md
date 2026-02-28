# MyRecall-v3 Chat 问题汇总（待专项讨论）

- 目的：把 v3 文档里与 Chat 相关的关键问题集中到一个入口，作为后续 #4 议题的讨论底稿。
- 范围：仅文档层（`spec.md` / `roadmap.md` / `open_questions.md` / `acceptance/` / `adr/`），不涉及实现改动。
- 状态：Draft（用于评审收敛，不是最终契约）。

## 1) 已拍板基线（本轮不重复争论）

- Chat 编排位置：Edge 侧 Orchestrator（非 Host）。
  - 依据：`adr/ADR-0004-chat-rag-orchestration-on-edge.md`
- Chat API 形态：OpenAI-compatible + tool schema。
  - 依据：`open_questions.md`（OQ-002= A）
- 模型策略：local/cloud 都支持，按配置切换，可选 fallback。
  - 依据：`open_questions.md`（OQ-005= A）
- 引用覆盖率：Soft KPI（non-blocking），分阶段目标 85% / 92%。
  - 依据：`gate_baseline.md`、`open_questions.md`（OQ-013= A）
- 索引/推理边界：索引时零 AI 增强，Chat 在查询时推理。
  - 依据：`spec.md`（014A/015A 相关条目）

## 2) 待重点讨论问题（P0-05）

| ID | 问题类型 | 当前状态 | 影响 | 主要证据（文档） | 需要拍板的点 |
|---|---|---|---|---|---|
| CH-001 | 契约缺口 | 未冻结 | P1-S5/S6 无法形成可执行验收 | `spec.md` 3.9 端点总览未列 Chat 端点；`gate_baseline.md` 已定义 Chat 首 token 指标 | 是否冻结 `POST /v1/chat/completions`（以及是否保留会话辅助端点） |
| CH-002 | 文档冲突 | 存在 | 计划与验收口径不一致 | `spec.md` 020A 仍写“Chat tool schema 推迟”；`roadmap.md` P1-S5 要求工具能力 100% | Tool schema 是否在 P1 直接冻结最小集（search/frame lookup/time range expansion） |
| CH-003 | 契约缺口 | 未冻结 | “引用可回溯”与“避免伪造引用”难以机审 | `spec.md` 3.6 现为软约束“尽量附引用”；`acceptance/phase1/p1-s5.md` 要求无依据拒答/标记低置信、不得伪造引用 | 引用最小必填字段、无依据回答语义、拒答/降级返回格式 |
| CH-004 | 协议缺口 | 未冻结 | P1-S6“流式协议一致性=100%”无法判定 | `acceptance/phase1/p1-s6.md` 有一致性 Gate；`spec.md` 未定义流式事件帧 | 流式协议（SSE/NDJSON）、事件类型（delta/tool_start/tool_end/done/error）、终止语义 |
| CH-005 | 策略缺口 | 未冻结 | fallback 行为不可预测，压测不可复现 | `open_questions.md` OQ-005 风险已写“需定义 fallback 阈值并做压测”；`p1-s6.md` 要求故障注入复现 | local->cloud/cloud->local 切换阈值、超时预算、最大重试次数 |
| CH-006 | 错误语义缺口 | 未冻结 | 客户端无法稳定处理 Chat 失败分型 | `spec.md` 统一错误码主要面向 ingest/search，未覆盖 Chat 专项场景 | 增补 Chat 专项错误码（如 `MODEL_TIMEOUT`/`TOOL_FAILED`/`NO_GROUNDED_CONTEXT`/`ROUTE_UNAVAILABLE`） |
| CH-007 | 可观测性缺口 | 部分定义 | 质量回归难定位根因 | `gate_baseline.md` 有首 token/citation coverage；缺少 tool 失败率、fallback 触发率、无引用回答占比 | Chat 指标最小集合与日志字段（request_id/session_id/route/tool/citation_count） |
| CH-008 | 数据契约缺口 | 未冻结 | 会话追踪与审计一致性不足 | `spec.md` 定义 `chat_messages` 表，但对 `citations/tool_calls` JSON 结构与版本缺少严格约束 | `chat_messages` 持久化 JSON schema、字段版本化、兼容策略 |
| CH-009 | 安全边界缺口 | 未冻结 | 工具越权风险/攻击面不清晰 | `roadmap.md` 仅列工具能力清单；无显式 allowlist/denylist 规则 | P1 工具白名单、参数边界、禁止工具（例如原始 SQL/文件系统直读） |

## 3) 建议讨论顺序（从“阻塞实现”到“优化质量”）

1. CH-001 + CH-002：先冻结 Chat API 与最小 tool schema（否则验收无锚点）。
2. CH-003 + CH-004：冻结引用语义与流式协议（否则 S5/S6 无法机审）。
3. CH-005 + CH-006：冻结路由/降级阈值与错误码（否则故障注入不可复现）。
4. CH-007 + CH-008 + CH-009：补齐观测、持久化与安全边界。

## 4) 讨论产出物（完成标准）

- `spec.md`：补齐 Chat 端点、请求/响应、流式协议、错误码、citation/tool schema。
- `roadmap.md`：P1-S5/P1-S6 Gate 与上面契约一一对应。
- `acceptance/phase1/p1-s5.md`、`acceptance/phase1/p1-s6.md`：步骤可执行、可机审。
- `open_questions.md`：把 CH-001~CH-009 的拍板结果落成 OQ 结论。
- （可选）新增 ADR：专门记录 Chat 契约冻结与版本策略。

## 5) 当前会话结论（便于续谈）

- 已确认本阶段只做文档收敛，不做实现。
- P0-01 ~ P0-04 已完成；下一焦点为 P0-05（Chat 契约与验收联动）。
