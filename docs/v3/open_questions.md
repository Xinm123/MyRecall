---
status: active
owner: pyw
last_updated: 2026-03-11
depends_on: []
references:
  - spec.md
  - roadmap.md
---

# MyRecall-v3 待决问题（必须拍板）

- 日期：2026-02-26
- 说明：以下问题若不拍板，会直接阻塞实现。

| ID | 级别 | 问题 | 选项 | 建议 | 依据 | 风险 | 截止 |
|---|---|---|---|---|---|---|---|
| OQ-001 | P0 | "对齐 screenpipe" 的语义是行为对齐还是实现对齐？ | A 行为对齐（推荐）/ B 实现对齐 | A（已决） | 你的 Edge-Centric 要求与 screenpipe 单机拓扑冲突 | 不拍板会导致方案反复摇摆 | 2026-03-01 |
| OQ-002 | P0 | Chat API 形态 | A（修订）请求简单 JSON + 响应 SSE 透传 Pi 原生事件 / ~~原 A OpenAI-compatible~~ / B 自定义协议 | A 修订版（已决） | DA-7=A 确定 Pi Sidecar 后，Pi 有 11 种事件类型，OpenAI format 仅能无损映射 1 种；透传 Pi 原生事件避免有损翻译；行业趋势（AG-UI Protocol）验证 agent 场景用自定义事件协议；Chat UI 绿地开发无存量兼容需求 | 若未来需支持第三方 OpenAI-compatible 客户端（不在 P1-P3 范围），需额外适配层 | 2026-03-03 |
| OQ-003 | P0 | Search 策略（vision-only） | A 完全对齐 screenpipe（FTS+元数据过滤，舍弃 hybrid）/ B 保留 MyRecall hybrid | A（已决，覆盖原003） | 你明确要求"search 完全和 screenpipe 对齐，舍弃 hybrid" | 语义召回能力可能下降 | 2026-03-05 |
| OQ-004 | P1 | Host 是否采集 accessibility 文本 | A 采集（推荐）/ B 不采集 | ~~A（已决）~~ **被 OQ-043 superseded** | ~~可对齐 screenpipe paired capture，降低 Edge OCR 压力~~ | ~~A 需处理平台差异~~ | 2026-03-08 |
| OQ-005 | P1 | Edge 默认模型策略 | A 本地与云端都支持，按配置切换（P1 不做自动 fallback，推荐）/ B cloud-first 固定 | A（修订后已决） | 与 screenpipe 的 provider 配置切换能力对齐，且不破坏 Edge-Centric | 若 provider 故障将直接返回 timeout/error，需保证错误可见性与恢复流程 | 2026-03-10 |
| OQ-006 | P1 | 传输安全级别（LAN） | A token + TLS 可选（P1）/ B mTLS 强制（P2+） | A->B（已决） | 当前同 LAN，先保证可用性，再在 P2+ 强制 mTLS | 若迟迟不进入 B 阶段，存在长期内网信任风险 | 2026-03-12 |
| OQ-007 | P1 | 页面/UI 在 P1~P3 的部署位置 | A 继续部署在 Edge（推荐）/ B 迁移到 Host | A（已决） | 先保障 Edge 主链路与 Chat 能力收敛，避免并行改造 UI 拖慢节奏 | Edge 计算与 UI 资源争用风险上升 | 2026-03-14 |
| OQ-008 | P1 | 功能开发阶段策略 | A 功能集中在 P1 完成，P2/P3 功能冻结（推荐）/ B 功能按阶段渐进到 P3 | A（已决） | 你明确要求 P2/P3 只做部署与稳定性，不再做功能开发 | P1 范围膨胀导致延期风险上升 | 2026-03-16 |
| OQ-009 | P1 | Phase 1 执行方式 | A 拆分为串行子阶段并逐段验收（推荐）/ B 继续单阶段并行实现后统一验收 | A（已决） | 你明确要求"串行实现、分别验收"，并要求将原 P1-S2 再拆分为"采集/处理"，同时 Chat 再拆分、E2E 验收独立为最后阶段 | 串行化可能降低局部并行效率 | 2026-03-18 |
| OQ-010 | P1 | 验收记录要求 | A 每个阶段/子阶段都必须有 Markdown 详细验收记录（推荐）/ B 仅关键阶段记录 | A（已决） | 你明确要求"每个阶段（子阶段）验收都要用 Markdown 详细记录" | 文档维护成本上升 | 2026-03-19 |
| OQ-011 | P1 | Gate 指标策略 | A 数值阈值适度放宽 + 功能完成度/完善度 Gate 强化（推荐）/ B 维持原严格数值为主 | A（已决） | 你明确要求"数值可宽松一些，但增加功能是否完成/完善的指标和 Gate" | 若功能口径不清会引入主观判定风险 | 2026-03-20 |
| OQ-012 | P1 | UI Gate 粒度 | A 最小可用 Gate（推荐）/ B 完整 UI 契约测试 | A（已决） | 你已明确选择 A，优先保障 P1 交付节奏，同时补齐 UI 可用性验收 | 可能遗漏复杂交互缺陷，需在 P2/P3 重点监控稳定性 | 2026-03-21 |
| OQ-013 | P1 | Chat 引用覆盖率策略与统计口径 | A screenpipe 对齐软约束（分阶段目标 + non-blocking，推荐）/ B 分阶段硬门槛 | A（已决） | 你已明确选择 A：取消 citation hard gate，保留分阶段目标用于质量观测与回归 | 若无配套观测与整改机制，引用质量可能长期下滑 | 2026-03-22 |
| OQ-014 | P0 | 是否删除 fusion_text/caption/keywords | A 删除，完全对齐 screenpipe 索引时零 AI（推荐）/ B 保留 | A（已决） | screenpipe 索引时不做 AI 预计算，Chat grounding 查询时实时推理 | — | 2026-02-27 |
| OQ-015 | P1 | embedding 是否进入线上 search 主路径 | A 仅离线实验表（推荐）/ B 线上 hybrid | A（已决） | 完全对齐 screenpipe，控制 P1 复杂度 | — | 2026-02-27 |
| OQ-016 | P1 | v2 数据迁移 | A v3 全新起点不迁移（推荐）/ B 迁移 | A（已决） | 简化 P1 启动 | — | 2026-02-27 |
| OQ-017 | P0 | 数据模型 schema 对齐策略 | A 主路径对齐 + 差异显式（推荐）/ B 自定义 | A（已决） | P1 对齐 `frames`/`ocr_text`/`frames_fts`/`ocr_text_fts`；`ocr_text_embeddings` 为 P2+ 可选实验表（同名保留，P1 不建） | — | 2026-02-27 |
| OQ-018 | P0 | ocr_text 关系 + text_source 位置 | A ocr_text 1:1 / B 1:N / ~~A~~ → C Scheme C 分表写入（已决） | ~~C（已决，覆盖 A）~~ **被 OQ-043 superseded** | ~~Scheme C：AX 成功 → accessibility 表（无 ocr_text 行）；OCR fallback → ocr_text 表（无 accessibility 行）；text_source 仍在 frames 表。证据：paired_capture.rs:153-154, db.rs:1538~~ | — | 2026-03-02 |
| OQ-019 | P0 | P1 ingest 协议复杂度 | A 单次幂等上传 + queue/status 端点（推荐）/ B 4 端点全量 / C 折中 | A（已决） | P1 本机双进程，4 端点解决 P1 不存在的问题；session/chunk/commit/checkpoint 推迟 P2 | P2 LAN 场景需新增分片协议 | 2026-02-27 |
| OQ-020 | P0 | API 契约定义（P1 端点完整 schema） | A 按 020A 落盘（推荐）/ B 留白 | A（已决） | P1-S4 Gate 必须有完整接口约束 | — | 2026-02-27 |
| OQ-021 | P0 | `ocr_text` 表 `app_name`/`window_name` 补齐策略 | A 补齐列 + 接受 drift（推荐）/ B 触发器 JOIN frames | A（已决） | 对齐 screenpipe 历史 migration；B 引入不必要子查询耦合 | 与 frames 列潜在 drift（P1 内无修正场景，接受） | 2026-02-27 |
| OQ-022 | P0 | Search SQL JOIN 策略 | A INNER JOIN 单路径 / ~~A~~ → C 三路径分发（已决） | ~~C（已决，覆盖 A）~~ **被 OQ-043 superseded** | ~~Scheme C 下 search 拆为 search_ocr()（INNER JOIN ocr_text）+ search_accessibility()（accessibility 表 + accessibility_fts）+ search_all()（并行合并 by timestamp DESC）；content_type 参数路由~~ | — | 2026-03-02 |
| OQ-023 | P1 | Migration 策略 | A 手写 SQL + `schema_migrations` 表（推荐）/ B Alembic / C PRAGMA user_version | A（已决） | 零额外依赖；对齐 screenpipe sqlx migrate 命名规范 | — | 2026-02-27 |
| OQ-024 | P0 | API 命名空间冻结 | A /v1/* 统一 + /api/* 渐进废弃（推荐）| A（已决，2026-03-04 补充；2026-03-07 更新） | 对外 HTTP 契约统一 `/v1/*`；`/api/*` P1-S1~S3 按阶段策略重定向（`POST /api/upload`=308，其余 GET=301）至 `/v1/*` + `[DEPRECATED]` 日志，P1-S4 返回 410 Gone 完全废弃；不纳入客户端默认调用路径 | — | 2026-02-26 |
| OQ-025 | P0 | accessibility 表架构（Scheme C） | A P0 建表 + focused 修复 + frame_id 方案 3（推荐，已决）/ B 对齐 screenpipe 不加 focused / C P1+ 延迟建表 | A（已决，**语义调整为 v4 seam**） | (1) accessibility 表 P0 **建表保留**（作为 v4 seam）；(2) ~~paired_capture 按 text_source 分表写入~~（v3 主线不写入）；(3) 新增 focused 列等为 v4 预留；**v3 主线代码不触碰此表** | DDL 保留但不增加 v3 实现负担；v4 恢复时无需重建 schema | 2026-03-02 |
| OQ-026 | P1 | P1 Search UI 分页模式 | A 加载更多（对齐 screenpipe，推荐）/ B 跳页（需加 offset 上限约束） | A（已决） | screenpipe `search-modal.tsx` 纯"加载更多"（`hasMoreOcr/loadMoreOcr`），offset 步长=limit，实际不超过几百；跳页模式下 `search_all()` 过量拉取内存风险不可控（offset=10000 时各路径拉 10020 行）；P2+ keyset cursor 可彻底替代 | 若未来需跳页，需补 `offset max` 约束并在 `search_all()` 加运行时 reject | 2026-03-02 |
| OQ-027 | P1 | Capture 运行机制与频率口径 | A 事件驱动主机制 + 固定注入压测口径（推荐）/ B 全局固定频率假设 | A（已决，2026-03-04 补充） | 对齐 [spec.md](spec.md)/[roadmap.md](roadmap.md)/`acceptance/phase1/p1-s2a.md`/`acceptance/phase1/p1-s2b.md`，消除"事件驱动 vs 固定频率"文本冲突（`acceptance/phase1/archive/p1-s2.md` 仅历史参考） | 若 P2+ 引入 Power Profile，TTS 与丢失率阈值需按 profile 重新标定 | 2026-03-04 |
| OQ-028 | P1 | Host spool 持久化策略 | A 磁盘持久化（推荐）/ B 内存队列 | A（已决，2026-03-05） | 进程重启/断电/断网场景下内存方案会丢数据，与 P1-S1 "断网恢复可自动重传" Gate 不兼容 | — | 2026-03-05 |
| OQ-029 | P1 | P1-S2 是否拆分为事件驱动 (S2a) + AX 采集 (S2b) | A 拆分为 S2a + S2b 串行开发（推荐）/ B 合并为单一 S2 阶段 | A（已决，2026-03-09） | 事件驱动与 AX 采集是两个独立技术栈；dedup 效果 Gate 依赖 `content_hash` + `inter_write_gap_sec`（需 S2b）；拆分后可独立验收、降低单阶段风险 | P1 阶段 Win/Linux 用户仅能用 idle/manual 触发 | 2026-03-09 |
| OQ-030 | P1 | P2 频率目标（是否对齐 screenpipe 5Hz） | A 维持 1Hz（推荐）/ B 目标 5Hz / C 数据驱动 | A（已决，2026-03-09） | P1/P2 采用保守频率（1Hz），有意偏离 screenpipe（5Hz）；Python 实现安全余量充足；若未来需要更高频率需重新评估 | 与 screenpipe 频率差异可能影响部分用户预期 | 2026-03-09 |
| OQ-034 | P1 | `ocr_preferred_apps` P1 初版白名单 | A 终端类最小名单（推荐）/ B 空名单（全量AX优先）/ C 扩大到更多应用 | ~~A（已决，2026-03-09）~~ **被 OQ-043 superseded** | ~~对齐 screenpipe `paired_capture` 终端类 OCR 偏好~~；OCR-only 收口后无需 AX/OCR 优先级判定 | — | 2026-03-09 |
| OQ-035 | P1 | OCR 引擎策略（P1） | A RapidOCR 单引擎（推荐）/ B 多引擎可切换 | A（已决，2026-03-09） | 降低实现与验收复杂度；统一 OCR 指标口径；OCR-only 主路径固定为 RapidOCR | 失去跨引擎对照能力，多语言/极端场景需在 P2+ 再评估 | 2026-03-09 |
| OQ-036 | P1 | macOS 权限状态机与恢复闭环口径 | A 对齐 screenpipe（2 fail / 3 success / 300s cooldown / 10s poll，推荐）/ B 简化为一次失败即判定 | A（已决，2026-03-09） | 解决 TCC 瞬态抖动导致的误判；保证 denied/revoked/recovered 有一致可观测语义 | 若不收敛，Gate 易出现“服务存活但采集失效”误判 | 2026-03-09 |
| OQ-037 | P1 | S2a 背压 Gate 是否保留 `collapse_trigger_count >= 1` | A 移出 Hard Gate、降级为观测（推荐）/ B 保留 Hard Gate | A（已决，2026-03-11） | 过载窗口未命中 collapse 时，`=0` 不应制造假失败；背压放行以 saturation/overflow 为准 | 若无额外观测，保护路径是否命中过的可见性下降 | 2026-03-11 |
| OQ-038 | P1 | Arc Browser AppleScript URL 提取在 S2b 的阶段语义 | A timeboxed optional heuristic sub-scope（推荐）/ B 正式 Gate 分支 | A（已决，2026-03-11） | 运行时行为对齐 screenpipe，但 Day 3 defer 属于 MyRecall 的 staged-delivery 适配 | Arc 若长期 deferred，需要后续阶段重新规划兼容目标 | 2026-03-11 |
| OQ-039 | P1 | S2b / S3 的 failure-class ownership | A 按 handoff 边界分责（推荐）/ B 混合共享 | A（已决，2026-03-11） | S2b 负责 capability/context/raw handoff；S3 负责 semantic outcome/final persistence | 若文档不收口，阶段验收会重复或遗漏同类故障 | 2026-03-11 |
| OQ-043 | P0 | v3 是否正式收口为 OCR-only，并将 AX defer 到 v4 | A OCR-only + 保留 AX schema seam（推荐）/ B OCR-only + 移除 AX seam / C 维持 AX-first 计划 | A（已决） | 与当前代码现实一致：P1-S2a 已落地，AX 主链路仍主要停留在文档与 schema 预留；保留 seam 可避免已执行 migration 回退，同时为 v4 恢复 AX 留兼容边界 | 若不收口，spec/roadmap/acceptance/gate 会持续承诺未实现的 AX 主链路，导致后续实现与验收反复摇摆 | 2026-03-13 |

## 需实验清单

1. AX-first 是否显著提升检索质量（需实验）。
2. 事件驱动捕获在多显示器下的 CPU 上限（需实验）。
3. Debian 端 OCR/VL 组合在 24h soak 中的稳定性（需查证）。

## 已拍板结论（2026-02-26）

1. OQ-001 = A：按"行为/能力对齐"执行，不追求与 screenpipe 的部署拓扑一致。
2. OQ-002 = A（修订）：Chat 请求为简单 JSON，响应为 SSE 透传 Pi 原生事件（不做 OpenAI format 翻译）。Tool 以 Pi SKILL.md 格式定义。
3. OQ-003 = A（覆盖）：Search 完全对齐 screenpipe（vision-only），线上仅保留 FTS+过滤，舍弃 hybrid。
4. OQ-004 = A：Host 采集 accessibility 文本（仅采集，不做推理），Edge 继续 AX-first + OCR-fallback。
5. OQ-005 = A（修订）：Edge 支持本地与云端模型，按配置切换；P1 不做自动 fallback，对齐 screenpipe 的 provider 选择能力。
6. OQ-006 = A->B：P1 使用 token + TLS 可选，P2+ 升级为 mTLS 强制。
7. OQ-007 = A：P1~P3 页面继续在 Edge，Host 不负责 UI；UI 迁移到 Host 仅作为 Post-P3 可选项。
8. OQ-008 = A：功能开发集中在 P1 完成；P2/P3 功能冻结，仅做部署与稳定性。
9. OQ-009 = A：Phase 1 按 P1-S1~S7 串行推进，S2/S3 分别为采集/处理，Chat 拆为 S5/S6，S7 为独立端到端验收阶段。
10. OQ-010 = A：每个阶段/子阶段验收都必须有 Markdown 详细记录，并作为 Gate 输入。
11. OQ-011 = A：Gate 采用双轨策略：数值阈值适度放宽，功能完成度/完善度指标强化。
12. OQ-012 = A：UI Gate 采用"最小可用集"，在 P1 按子阶段强化 UI 可用性/可解释性验收，不做 UI 重构。
13. OQ-013 = A：引用覆盖率采用 soft KPI（P1-S5>=85%，P1-S7/P2/P3>=92%，Stretch 95%），不作为 Gate Fail 条件；DA-8=A 口径为 deep link：
   - OCR 结果：`myrecall://frame/{frame_id}`
   - UI 结果：优先 `myrecall://frame/{accessibility.frame_id}`（v3 改进，外键精确关联），无 frame_id 时回退 `myrecall://timeline?timestamp=...`
   - P1 阶段正常 paired_capture 路径下 UI 结果 frame_id 应为非 NULL（paired_capture 写入），此回退仅未来独立 walker 场景触发
   - DA-8=B 结构化 citations 为可选增强；统一口径以 [gate_baseline.md](gate_baseline.md) 为准。

### 已拍板结论（2026-02-27）

14. OQ-014 = A：删除 fusion_text/caption/keywords 索引时预计算，完全对齐 screenpipe vision-only 处理链路（索引时零 AI 调用，Chat grounding 由 LLM 查询时实时推理）。
15. OQ-015 = A：embedding 保留为离线实验表 `ocr_text_embeddings`（对齐 screenpipe），不进入线上 search 主路径。
16. OQ-016 = A：v3 全新数据起点，不做 v2 数据迁移。
17. OQ-017 = A：数据模型采用"主路径对齐 + 差异显式"策略：P1 对齐 `frames`/`ocr_text`/`frames_fts`/`ocr_text_fts` 的表名与核心字段；`ocr_text_embeddings` 为 P2+ 可选实验表（同名保留，P1 不建）；仅追加 Edge-Centric 必需字段（`capture_id`/`status`/`retry_count` 等）与 `chat_messages` 表。
18. OQ-018 = C（覆盖 A）：Scheme C 分表写入 — AX 成功帧写入 `accessibility` 表（无 `ocr_text` 行），OCR fallback 帧写入 `ocr_text` 表（无 `accessibility` 行）；`text_source` 仍在 `frames` 表。

### 已拍板结论（2026-02-27，续）

19. OQ-019 = A：P1 ingest 协议采用单次幂等上传（`POST /v1/ingest`）+ 队列状态端点（`GET /v1/ingest/queue/status`）。重复 `capture_id` 返回 `200 OK + "status": "already_exists"`（幂等语义，X 选项）。`GET /v1/ingest/queue/status` 返回 pending/processing/completed/failed 计数，供 Host client 决策与 P1-S1 Gate 验收（Y 选项）。session/chunk/commit/checkpoint 4 端点推迟到 P2 LAN 弱网场景实现，不破坏 P1 契约。

20. OQ-020 = A：API 契约定义（P1 端点完整 schema，020A/020B）：`/v1/search` 合并 `/v1/search/keyword`（P1 无 embedding，拆分无意义）；search response 同时返回 `file_path`（Edge 本地路径，对齐 screenpipe）和 `frame_url`（`/v1/frames/:id`，P2+ 跨机器可用）；`GET /v1/frames/:frame_id` 返回图像二进制；`GET /v1/frames/:frame_id/metadata` 返回 JSON（最小稳定契约为 `{frame_id,timestamp}`，扩展字段 best-effort）；新增 `GET /v1/frames/:frame_id/context`（020B）用于 text/urls（P2+ 扩展 nodes）；统一错误响应增加 `code`（SNAKE_CASE）和 `request_id`（UUID v4），不对齐 screenpipe（v3 更严谨）；Chat tool schema 已由 DA-3/DA-7 决定（Pi SKILL.md 格式）。

21. OQ-021 = A：`ocr_text` 表新增 `app_name`/`window_name` 两列（对齐 screenpipe 历史 migration 20240716/20240815）。写入时从 `CapturePayload` 取值，与 `frames` 同源。接受与 `frames` 列潜在 drift（P1 内无 frames 修正场景，对齐 screenpipe 行为）。

22. ~~OQ-022 = A~~（已被 2026-03-02 的 OQ-022 = C 覆盖，保留为历史记录）：Search SQL 主路径使用 `frames INNER JOIN ocr_text`（无条件）；`frames_fts`/`ocr_text_fts` 按需追加 JOIN；不使用 LEFT JOIN（对齐 screenpipe 性能注释 db.rs line 3133）；INNER JOIN 自然排除未处理帧，语义正确。

23. OQ-023 = A：Migration 策略采用手写 SQL + `schema_migrations` 跟踪表，零额外依赖；文件命名 `YYYYMMDDHHMMSS_描述.sql` 对齐 screenpipe；P1 全量 DDL 放入 `20260227000001_initial_schema.sql`；`ocr_text_embeddings` 表推迟至 P2+ migration 新增；已执行迁移不得修改。

24. OQ-024 = A（2026-03-04 补充；2026-03-07 更新）：API 命名空间冻结：v3 对外 HTTP 契约统一 `/v1/*`；`/api/*` P1-S1~S3 按阶段策略重定向（`POST /api/upload`=308，其余 GET=301）至 `/v1/*` + `[DEPRECATED]` 日志，P1-S4 返回 410 Gone 完全废弃；不纳入客户端默认调用路径。
- 重要澄清（P1 Gate scope）：legacy `/api/*` 渐进废弃的验收口径以 [http_contract_ledger.md](./http_contract_ledger.md) §4.0 为准，仅覆盖 `POST /api/upload`、`GET /api/search`、`GET /api/queue/status`、`GET /api/health`（其余 `/api/*` 行为不纳入 P1 Gate 口径）。

### 已拍板结论（2026-03-02）

25. OQ-022 = C（覆盖 A）：Search SQL 拆为三路径 — search_ocr()（INNER JOIN ocr_text，content_type=ocr）、search_accessibility()（accessibility + accessibility_fts，content_type=accessibility）、search_all()（并行合并 by timestamp DESC，content_type=all 默认）。v3 不做 screenpipe 的 focused/browser_url → force content_type=ocr 降级。
26. OQ-025 = A：accessibility 表 P0 建表（Scheme C），含 focused 列（P0 修复 screenpipe 限制）+ frame_id DEFAULT NULL（方案 3，paired_capture 精确关联）。DDL 对齐 screenpipe migration 20250202000000 并增强。
27. OQ-026 = A：P1 Search UI 采用"加载更多"分页模式（对齐 screenpipe `search-modal.tsx`），offset 单调递增步长=limit，实际不超过几百。`search_all()` 过量拉取内存可控前提成立；P2+ 可升级为 keyset cursor 分页彻底消除过量拉取。

### 已拍板结论（2026-03-04）

28. OQ-027 = A（2026-03-04 补充）：Capture 运行机制定义为"事件驱动触发（`idle/app_switch/manual/click`）+ `idle` timeout fallback + `min_capture_interval_ms` 去抖 + content_hash 内容去重（非 idle/manual + 30s 保底）+ 背压保护"；`300 events/min` 属于固定注入压测条件（用于可比性），不代表生产固定频率轮询；`OPENRECALL_CAPTURE_INTERVAL` 不作为 P1 主触发机制定义；若 P2+ 引入 Power Profile，`TTS P95` 与 `Capture 丢失率` 阈值须按各 profile（至少覆盖 Saver 最坏情况）重新标定。

### 已拍板结论（2026-03-05）

29. OQ-028 = A：Host spool 采用磁盘持久化，不使用内存队列。spool 落盘为 JPEG（`.jpg`/`.jpeg` + `.json`，原子写入）；兼容读取历史（`.webp` + `.json`）仅用于 drain 清空，新写入不再产生 `.webp`。理由：进程重启/断电/断网场景下内存方案会丢数据，与 P1-S1 "断网恢复可自动重传" Gate 不兼容。

> **补充（2026-03-05，按议题 1 收口更新）**：`capture_id` 幂等由 Edge `/v1/ingest` 实现；`content_hash` 内容去重由 Host 在 capture 前执行。Edge 仅接收并存储 `content_hash` 用于观测，不承担 dedup 判定职责。

### 已拍板结论（2026-03-09）

30. OQ-029 = A：P1-S2 拆分为 S2a（事件驱动 capture，Week 1-2）+ S2b（AX 文本采集，Week 3-4），串行开发，独立验收。实现语言为 Python（与现有 codebase 一致，开发周期 3-4 周）。平台策略 macOS-first，Win/Linux 推迟 P2。`dedup_skip_rate` 不再作为正式验收指标；dedup 效果由 `inter_write_gap_sec` Hard Gate 覆盖。详见 ADR-0013。
    - 阶段边界（强制）：P1-S2a 不判定 `content_hash` / `inter_write_gap_sec`；上述指标从 P1-S2b（`content_hash` 交付后）开始记录与评审。

31. OQ-030 = A：P2 频率目标维持 1Hz（有意偏离 screenpipe 5Hz）。理由：Python 实现在 1Hz 频率下安全余量充足；若未来需要更高频率需重新评估。

### 已拍板结论（2026-03-09，续）

33. OQ-032 = A：Browser URL 提取完全对齐 screenpipe，包含 Arc Stale URL 检测机制。关键决策：
    - **问题识别**：AppleScript 有 ~107ms 延迟，期间用户切换 tab 会导致 URL 与截图不匹配（stale URL）
    - **解决方案**：Arc 专用 title cross-check — 同时获取 title + URL，与 window_title 比对，不匹配时返回 None
    - **Title 匹配算法**：去除 badge 计数（`(45) WhatsApp` → `WhatsApp`）、大小写不敏感、包含匹配（处理截断）
    - **设计原则**：Better None than wrong URL
    - **失败分类统计**：`browser_url_success` / `browser_url_rejected_stale` / `browser_url_failed_all_tiers` / `browser_url_skipped`
    - 详见 `p1-s2b.md` §1.0 与 ADR-0013 §Browser URL 提取策略

34. OQ-033 = A：AX/OCR 决策契约采用“`ocr_preferred_apps` 优先、其后按归一化 AX 文本非空判定、否则 OCR fallback”的单一口径（P1-S3 SSOT）。
    - **优先级**：`app_name in ocr_preferred_apps` → `text_source='ocr'`；否则计算 `ax_text_normalized = TRIM(COALESCE(accessibility_text, ''))`。
    - **判定**：`ax_text_normalized != ''` → `text_source='accessibility'`；否则执行 OCR fallback，成功后 `text_source='ocr'`。
    - **边界规则**：空白 AX 文本视为空；AX 超时但有非空部分文本仍按 `accessibility`；Electron/Chromium 首次空树不做同帧重试。
    - **Scheme C 终态约束**：`text_source='accessibility'` 仅对应 `accessibility` 行；`text_source='ocr'` 仅对应 `ocr_text` 行；禁止同帧双写。
    - **失败语义**：AX 不可用且 OCR 失败时，帧状态必须为 `failed`，不得误标 `accessibility`。
    - **验收落点**：以 [spec.md](spec.md)（AX/OCR 决策契约）、[data-model.md](data-model.md)（终态不变量）、`acceptance/phase1/p1-s3.md`（边界用例）为执行依据。
    - **阶段边界补充**：P1-S2b 的 `content_hash` coverage 仅基于 raw `accessibility_text` 非空样本，不依赖 `text_source`。
    - **字段语义补充**：`accessibility_text` 在 S2b->S3 handoff 中必须为 string（允许 `""`，禁止 `null`）；`content_hash` key 必须存在，但值可为 `null`（禁止 `""`）。
    - **上下文契约补充**：`focused_context = {app_name, window_name, browser_url}`，`capture_device_binding = {device_name}`；P1 仅承诺 capture-cycle coherence，不承诺截图/AX/URL 的全局原子同瞬时快照；不确定时按 `Better None than wrong` 置 `None`，禁止字段级混拼。

35. OQ-034 = A：`ocr_preferred_apps` 采用 P1 初版“终端类最小名单”，匹配规则为 `app_name` 小写后子串包含。
    - **初版名单**：`wezterm`、`iterm`、`terminal`、`alacritty`、`kitty`、`hyper`、`warp`、`ghostty`。
    - **决策语义**：命中名单时强制 OCR 路径（即使 AX 非空）；未命中时仍按 OQ-033 的 AX 非空优先规则。
    - **范围约束（P1）**：不扩展到浏览器/IDE/远程桌面类应用，避免无证据扩大 OCR 开销。
    - **验收要求**：P1-S3 样本必须覆盖“命中名单且 AX 非空仍走 OCR”场景；若出现误判，先修正规则再扩名单。
    - **后续演进**：P2+ 才允许基于质量与耗时证据增删名单，变更须更新 [open_questions.md]() 与对应 acceptance 文档。

36. OQ-035 = A：P1 OCR 引擎策略固定为 RapidOCR 单引擎（single-engine policy）。
    - **语义边界**：保持 AX-first + OCR-fallback 主路径不变；仅将 fallback OCR 引擎固定为 RapidOCR。
    - **验收口径**：P1 阶段 OCR 指标均按 RapidOCR 路径统计，不做跨引擎归一化/切换对比。
    - **演进策略**：多引擎切换能力推迟到 P2+，需以质量与运维证据驱动再开放。

37. OQ-036 = A：P1 权限稳定性口径对齐 screenpipe（2 fail / 3 success / 300s cooldown / 10s poll）。
    - **状态机**：`granted/transient_failure/denied_or_revoked/recovering`。
    - **语义边界**：`AX empty/timeout` 归数据质量分支（OCR fallback）；`permission denied/revoked` 归能力失效分支（权限降级流）。
    - **验收要求**：必须覆盖 startup denied / mid-run revoked / restored 三类场景，并在 `/v1/health` 暴露权限状态。

### 已拍板结论（2026-03-11）

38. OQ-037 = A：`collapse_trigger_count` 从 P1-S2a Exit Hard Gate 移出，降级为观测/调试指标；S2a 背压放行仅以 `queue_saturation_ratio <= 10%` 与 `overflow_drop_count = 0` 为准。若权限异常闭环未在 S2a 执行，必须在 S2b Exit 前关闭，不允许长期 `N/A` 悬置。

39. OQ-038 = A：Arc Browser AppleScript URL 提取在 P1-S2b 中定义为 timeboxed optional heuristic sub-scope，而非正式 Gate 分支。若 Day 3 仍不稳定，则 defer Arc-specific support；S2b required browser evidence 仍以 Chrome/Safari/Edge 为准，Arc stale-url 测试仅作为 conditional evidence。

40. OQ-039 = A：S2b / S3 的 failure-class ownership 以 handoff 边界划分——S2b 负责 capability / frozen metadata / raw handoff correctness（permission denied/revoked/recovered、browser_url stale、Arc deferred、empty-AX no-drop）；S3 负责 semantic outcome / final persistence correctness（AX empty、AX timeout、ocr_preferred_apps、OCR fallback success/failure、failed 语义）。

41. OQ-040 = A：P1-S2b trigger / focused-context / dedup / URL stale 规则冻结为单一口径。
    - **Trigger 语义**：event source 仅发出 `capture_trigger`，不得绑定 `device_name`；`device_name` 由 monitor worker 在消费 trigger、执行实际截图时绑定。
    - **Focused-context 语义**：`app_name/window_name/browser_url` 必须由同一轮 focused-context snapshot 一次性产出；允许部分为 `None`，但禁止字段级混拼。
    - **Hash 语义**：`content_hash` 仅基于最终上报的 `accessibility_text` 计算；canonicalization 采用 Unicode NFC、换行统一为 `\n`、每行去尾部空白、整体 `strip()`；空字符串对应 `null`，partial AX text 仍正常计算。
    - **Dedup 语义**：Host 在 capture 完成并生成 `accessibility_text/content_hash` 后、upload 前执行 dedup；`last_write_time` 固定为最近一次成功写入 Host 本地 spool 的时间。
    - **URL stale 语义**：`browser_url` 获取成功不等于可写入；必须先完成与同轮 `focused_context` 的一致性校验，失败则写 `None`；Arc / AppleScript 路径标题匹配失败必须按 stale reject 处理。
    - **落点**：`spec.md` 作为规则 SSOT，`acceptance/phase1/p1-s2b.md` 作为阶段验收口径，`data-model.md` 仅承载数据契约结果。

42. OQ-041 = A：P1-S2b 的测试与 Gate 交付采用“TDD 开发 + 收口脚本”模式。
    - **开发方式**：S2b 核心能力采用 TDD；每推进一个冻结规则或核心能力，先写失败测试，再实现最小代码通过。
    - **测试产物语义**：`tests/test_p1_s2b_content_hash.py`、`tests/test_p1_s2b_ax_timeout.py` 等属于 S2b 阶段正式交付物，但应在开发过程中随功能自然落地，而不是要求在开工前一次性手工补齐。
    - **阶段收口方式**：`scripts/acceptance/p1_s2b_local.sh` 属于 S2b Exit Gate 交付物；其职责是编排已存在的测试、指标导出、health snapshot 与证据产物，而不是承担最早期规则发现责任。
    - **实施顺序**：先用 TDD 落实最小契约测试与必要集成测试，再在阶段收口时补齐并执行 Gate 编排层。
    - **目的**：避免过早写死验收脚本导致返工，同时避免把契约测试拖到功能完成后才补。

43. OQ-042 = A：P1-S2b 采用 v3-only 主链路；legacy `/api/*` 与旧 worker 仅保留兼容职责。
    - **主链路**：S2b 新语义仅允许沿 `Host capture -> spool/uploader -> POST /v1/ingest -> v3 queue/status -> S3 handoff` 生长。
    - **legacy 边界**：`/api/*` 仅用于渐进废弃与兼容回归检查；旧 worker / 旧处理心智模型不得承载新的 S2b 语义、字段规则或验收责任。
    - **语义范围**：`accessibility_text`、`content_hash`、browser URL stale rejection、Host dedup、`device_name` binding、`focused_context` frozen bundle 等规则仅属于 v3 主链路。
    - **实施方式**：如确需复用 legacy 代码，只允许通过 adapter 接入，不允许反向把 legacy 语义带回 v3 主链路。
    - **验收原则**：S2b 测试、Gate 脚本、runbook 与人工验证只认 `/v1/*` + v3 runtime/store；legacy 路径仅做兼容检查，不作为功能正确性的证明链路。

### 已拍板结论（2026-03-13）

44. OQ-043 = A：v3 正式收口为 OCR-only；AX 主链路 defer 到 v4。收口原则如下：
    - **活跃主线**：v3 仅承诺 `S2a event-driven capture -> ingest -> OCR processing -> OCR search -> frame citation`；不再以 AX 采集、AX-first 判定、UI 结果或 `accessibility.frame_id` citation 作为 v3 active semantics。
    - **保留 seam**：已存在的 `accessibility` / `accessibility_fts` 表、`frames.accessibility_text`、`frames.content_hash`、`frames.text_source` 等 schema 预留保持不删，作为 v4 恢复 AX 的兼容边界；其中 v3 active path 的 `text_source` 仅允许收口到 `'ocr'`。
    - **覆盖范围**：对 v3 active semantics 而言，OQ-004 / OQ-018 / OQ-022 / OQ-029 / OQ-033 / OQ-034 / OQ-035 / OQ-039 / OQ-040 / OQ-041 / OQ-042 中涉及 AX 主链路的表述均由本决议 supersede；这些条目保留为历史记录或 v4 设计输入，不再作为 v3 主线执行依据。
    - **引用口径收口**：OQ-013 中 UI 结果优先 `myrecall://frame/{accessibility.frame_id}` 的口径不再属于 v3 active path；v3 仅承诺 OCR/frame 结果 `myrecall://frame/{frame_id}`，UI/AX citation 回退到 v4 重新定义。
    - **S2b 阶段语义**：P1-S2b 不再作为 v3 主线的必经阶段；凡依赖 `accessibility_text`、AX timeout/empty、browser URL stale、Host AX dedup 的规则与 Gate，统一降级为 deferred AX scope，待 v4 重新收口。
    - **OQ-025 解释补充**：`accessibility` 表 P0 建表的决定仍保留，但其语义从“v3 active path”调整为“v4 reserved seam”；保留该表不构成 v3 必须实现 AX 采集或 AX 搜索的承诺。
