---
status: draft
owner: pyw
last_updated: 2026-03-04
depends_on:
  - gate_baseline.md
  - open_questions.md
references:
  - spec.md
---

# MyRecall-v3 路线图（Edge-Centric, vision-only）

- 版本：Draft v0.1
- 首版日期：2026-02-26
- 节奏原则：每阶段都可独立验收；Edge 必须从 Day 1 参与。

## 0. 已锁定决策

> **SSOT**: [open_questions.md](open_questions.md) — "已拍板结论" 各节
> 
> 所有已锁定决策（当前范围：001A–026A）的完整内容以 open_questions.md 为唯一事实源。本节不再重复列举。

## 1. 阶段目标与里程碑

## Phase 1：本机模拟 Edge（进程级隔离）
- 时间：2026-03-02 ~ 2026-03-20
- 目标：将当前单机闭环（client+server）按 Edge-Centric 职责拆为 Host/Edge 两进程，并在本机完成全功能闭环。
- 执行规则：P1-S1 -> P1-S2 -> P1-S3 -> P1-S4 -> P1-S5 -> P1-S6 -> P1-S7 串行推进；每阶段必须先通过验收 Gate。
- P1-S1（基础链路，2026-03-02 ~ 2026-03-05）
  - 交付：
    - Host spool + uploader（幂等、可续传）
    - Edge ingest + queue + processing pipeline 骨架
    - 图片格式主契约统一（主采集/主读取链路 JPEG）
    - Edge 继续承载现有 Flask 页面（`/`、`/search`、`/timeline`）
    - UI 基线可用（路由可达 + 基础健康态/错误态可见）
  - Gate：
    - 同机断网恢复后可自动重传，且重复上传不重复入库
    - ingest 队列可观测（pending/processing/completed/failed）完整
    - 图片格式契约一致性通过：`/v1/ingest` 主契约 `image/jpeg`，`/v1/frames/:frame_id` 返回 `image/jpeg`；兼容输入若启用，需验证入库前转码为 JPEG
    - 对外 API 命名空间一致性通过：验收脚本仅调用 `/v1/*`，旧 `/api/*` 路径不得返回业务成功（2xx）
    - UI 基线路由可达率 = 100%
    - UI 健康态/错误态展示检查通过率 = 100%
- P1-S2（采集，2026-03-06 ~ 2026-03-08）
  - 交付：
    - Host 事件驱动 capture（app switch/click/idle）+ manual trigger + idle fallback（P1 触发枚举：`idle/app_switch/manual/click`；`window_focus` 不纳入 P1）
    - Host 采集 accessibility 文本并上传
    - 高频事件抑制链路（对齐 screenpipe）：共享去抖（`min_capture_interval_ms`，默认 200ms）+ 内容去重（非 `idle/manual`）+ 有界通道 lag 折叠
    - Timeline 可见 capture 上传中/已入队状态
  - Gate：
    - 入队时延 Gate：压测窗口（5 分钟）`enqueue_latency_p95 <= 3s`（`eligible_events >= 200`）
    - 每分钟 300 次事件压测下丢包率 < 0.3%
    - 触发覆盖 Gate：`trigger_coverage = covered_trigger_types / 4 = 100%`（`idle/app_switch/manual/click` 四类均需命中；每类样本 >= 20）
    - 去抖 Gate：同 monitor 连续 `app_switch/click` 入库间隔 < `min_capture_interval_ms`（200ms）的违规数 = 0
    - 去重 Gate：重复内容压测窗口（5 分钟）满足 `dedup_skip_rate = dedup_skipped / dedup_eligible >= 95%`（`dedup_eligible >= 500`），且 `inter_write_gap_sec` 满足 `P99 <= 30s` 与 `max <= 45s`
    - 背压 Gate：过载注入窗口（5 分钟）满足 `collapse_trigger_count >= 1`、`queue_saturation_ratio <= 10%`（`queue_depth >= 0.9 * queue_capacity` 采样占比）且 `overflow_drop_count = 0`
    - 新 capture 在 timeline 可见性通过率 >= 95%
- P1-S3（处理，2026-03-09 ~ 2026-03-11）
  - 交付：
    - Edge AX-first + OCR-fallback（含 `ocr_preferred_apps` 初版）
    - Scheme C 分表写入：AX 成功 → `accessibility` 表（含 `focused`/`frame_id`）；OCR fallback → `ocr_text` 表
    - AX/OCR 决策记录到 `frames.text_source`
    - 索引时零 AI 增强：不生成 `caption/keywords/fusion_text`，不写入 `ocr_text_embeddings`
    - Frame 详情可见处理来源（AX/OCR fallback）与处理时间戳
  - Gate：
    - AX 成功帧写入 `accessibility` 表的正确率 = 100%
    - AX-first/OCR-fallback 决策日志可追溯率 >= 95%
    - 索引时零 AI 增强检查通过率 = 100%（禁用字段/写入路径回归为 0）
    - 处理来源字段 UI 展示完整率 = 100%
- P1-S4（检索能力，2026-03-12 ~ 2026-03-13）
  - 交付：
    - `/v1/search`（含 keyword 检索语义，FTS+过滤完整能力）
    - Scheme C 三路径分发：`search_ocr()`、`search_accessibility()`、`search_all()`，由 `content_type` 参数路由
    - `focused` 过滤在 `search_accessibility()` 直接支持（P0 修复，不做 screenpipe force-OCR 降级）
    - 返回结构包含 frame/citation 关键字段，`type` 字段区分 `OCR`/`UI`
    - Search 页过滤项与 API 参数 1:1 映射，结果可回溯到 frame/citation
  - Gate：
    - Search P95 <= 1.8s（标准时间窗）
    - `/v1/search` 过滤参数契约完成率 = 100%（含 `content_type`）
    - Search SQL 三路径分发一致性 = 100%（search_ocr：INNER JOIN ocr_text；search_accessibility：accessibility + FTS；search_all：并行合并）
    - `focused` 过滤在 `search_accessibility()` 正确性 = 100%（不降级为 OCR-only）
    - OCR 检索结果引用字段完整率 = 100%（`frame_id`/`timestamp`，Hard Gate）
    - UI 检索结果引用字段完整率 = 100%（`id`/`timestamp`，Hard Gate）
    - 观测 KPI（non-blocking）：OCR 检索结果 `capture_id` 覆盖率目标 >= 99%（未达标需提交整改动作）
    - Search UI 过滤项契约映射完成率 = 100%
    - 检索结果点击回溯成功率 >= 95%
- P1-S5（Chat-1 Grounding 与引用，2026-03-14 ~ 2026-03-16）
  - 交付：
    - Pi Sidecar 基础能力：PiProcess（subprocess wrapper）、PiManager（singleton 进程管理）、protocol.py（Pi JSON Lines ↔ SSE 桥接）
    - `myrecall-search` SKILL.md（tool-driven retrieval，对标 screenpipe `screenpipe-search`）
    - `/v1/chat` SSE streaming endpoint（Flask + threading，DP-1=A）
    - `chat_messages` 持久化（session history injection，DP-3=A）
    - Chat UI minimal（Alpine.js + EventSource）
    - 引用通过提示词与 Skill 显式要求输出 deep link：默认 `myrecall://frame/{frame_id}`；当结果缺少 `frame_id` 时回退为 `myrecall://timeline?timestamp=ISO8601`。`frame_id`/`timestamp` 必须来自检索结果且禁止伪造（DA-8=A）
  - Gate：
    - Chat 工具能力清单（search/frame lookup/time range expansion via myrecall-search SKILL.md）完成率 = 100%
    - Chat 引用点击回溯成功率 >= 95%
    - 观测 KPI（non-blocking）：Chat 引用覆盖率目标 >= 85%，未达标需提交整改动作
- P1-S6（Chat-2 路由与流式，2026-03-17 ~ 2026-03-18）
  - 交付：
    - Provider/model 路由（通过 Pi `--provider`/`--model` + `models.json` 配置，UI 配置页面切换）
    - Pi 事件流式输出（SSE 透传 Pi 原生 11 种事件类型）
    - PiManager watchdog（idle timeout、crash auto-restart、orphan cleanup）
    - Provider timeout 处理（180s 请求 watchdog → timeout error；不做 auto-fallback；超时不强制 abort，保留用户手动中断）
    - UI 可见 provider/model badge + timeout/error notification + Pi 健康状态
  - Gate：
    - Chat 请求成功率 >= 98%（timeout/error 计入失败；用户主动 abort 不计入样本）
    - 观测 KPI（non-blocking）：Chat 首 token P95 <= 3.5s
    - Provider 切换可重复通过
    - 路由切换场景覆盖率 = 100%（provider 切换 + timeout 错误，不含 auto-fallback）
    - 流式输出协议一致性用例通过率 = 100%
    - 路由与 timeout 状态可见场景覆盖率 = 100%
- P1-S7（端到端验收，2026-03-19 ~ 2026-03-20）
  - 交付：
    - 端到端故障注入与回归报告（仅验收，不新增功能）
    - P1 功能冻结清单（进入 P2/P3 的基线）
    - UI 关键路径回归报告（timeline -> search -> chat -> citation -> frame）
  - Gate：
    - TTS P95 <= 12s
    - S1~S6 的 Hard Gate/SLO Gate 回归全通过（Soft KPI 仅记录偏差与整改动作）
    - P1 功能清单完成率 = 100%
    - P1 验收记录完整率 = 100%
    - UI 关键路径脚本通过率 = 100%
    - 观测 KPI（non-blocking）：Chat 引用覆盖率目标 >= 92%，Stretch >= 95%

## Phase 2：LAN 双机（另一台 Mac 作为 Edge）
- 时间：2026-03-23 ~ 2026-04-17
- 目标：验证 LAN 链路稳定性与重放正确性（功能冻结，不新增功能）。
- 核心交付：
  - LAN 传输稳定性与重放正确性
  - 24h soak test 报告与瓶颈定位
  - 传输安全升级到 mTLS（按 006A->B）
- 验收门槛：
  - 24h soak test 无致命中断
  - capture 丢失率 <= 0.2%
  - 重放一致性校验通过率 = 100%（同一 `capture_id` 结果一致）
  - mTLS 握手与证书轮换演练通过率 = 100%
  - UI 关键路径在 LAN 24h 中致命中断次数 = 0
  - 观测 KPI（non-blocking）：Chat 引用覆盖率目标 >= 92%，Stretch >= 95%

## Phase 3：Debian Edge（生产形态）
- 时间：2026-04-20 ~ 2026-05-29
- 目标：完成生产化部署与运维闭环（功能冻结，不新增功能）。
- 核心交付：
  - Debian 服务化部署（systemd 或容器）
  - 指标面板（ingest lag/queue depth/search latency/chat latency）
  - 灰度升级与回滚策略
- 验收门槛：
  - 7 天稳定运行
  - Debian 部署脚本（systemd/容器）成功率 = 100%
  - 回滚演练通过率 = 100%
  - UI 关键路径在 7 天内致命中断次数 = 0
  - 观测 KPI（non-blocking）：Chat 引用覆盖率目标 >= 92%，Stretch >= 95%

## 2. 工作流分解（按链路）

1. Capture
- P1：完成功能实现（事件驱动 + idle fallback + trigger/capture_id + AX 文本采集）。
- P2/P3：功能冻结，仅做稳定性压测与参数调优。

2. Processing
- P1：完成功能实现（AX-first + OCR-fallback；Scheme C 分表写入 — AX→accessibility 表，OCR→ocr_text 表；仅存储原始文本，不做索引时 AI 增强；Embedding 仅离线实验表）。
- P2/P3：功能冻结，仅做资源与性能稳定性优化。

3. Search
- P1：完成功能实现（完全对齐 screenpipe vision-only：FTS+过滤 API 与返回契约；Scheme C 三路径分发 search_ocr/search_accessibility/search_all；`content_type` 参数路由）。
- P2/P3：不新增检索功能，仅做性能与可观测性优化。

4. Chat
- P1：完成功能实现（Pi Sidecar + SKILL.md tool-driven retrieval + 提示词驱动引用 + provider/model 路由 + 流式输出 + timeout 处理）。
- P2/P3：不新增 Chat 功能，仅做延迟与稳定性治理。

5. UI（Edge 页面）
- P1：完成最小可用 UI 闭环（timeline/search/chat/citation 回溯），不做 UI 重构。
- P2/P3：功能冻结，仅做稳定性与异常可见性治理。

## 2.1 Phase 1 子阶段映射（串行）

- P1-S1：Host 上传链路 + Edge ingest/queue + 页面保持可用
- P1-S2：Capture 事件化能力闭环
- P1-S3：AX-first/OCR-fallback 处理 + Scheme C 分表写入能力闭环
- P1-S4：Search（FTS+过滤，三路径分发）能力闭环
- P1-S5：Chat Grounding 与引用闭环
- P1-S6：Chat 路由/流式/降级闭环
- P1-S7：端到端验收（仅验收，不新增功能）
- 说明：各子阶段都包含对应最小 UI Gate（可用性、可解释性、可恢复性）。

## 3. 风险清单（按优先级）

- P0：Edge 挂掉导致 Host 长时间积压。
- P0：Chat 无引用导致可用性失败。
- P0：Phase 1 范围膨胀导致里程碑延期。
- P1：事件驱动策略过激导致采集风暴。
- P1：语义型查询能力下降导致 Chat 检索上下文不充分。

## 4. 里程碑退出条件（DoD）

- 每个阶段都必须提供：
  - 功能验收报告
  - 故障注入报告
  - 性能指标报告
  - 未决问题转入 `open_questions.md`

## 4.1 验收记录规范（强制，Markdown）

- 规则：
  - 每个阶段（Phase）与每个子阶段（P1-Sx）在 Gate 判定前，必须先完成对应 Markdown 验收记录。
  - 验收记录未完成，视为 Gate 未通过。
  - 验收记录必须包含：目标范围、输入版本、测试环境、测试步骤、指标结果、结论（Pass/Fail）、风险与后续动作。
- 归档目录：`MyRecall/docs/v3/acceptance/`
- 统一模板：`MyRecall/docs/v3/acceptance/TEMPLATE.md`
- 文件映射（固定）：
  - `phase1/p1-s1.md`
  - `phase1/p1-s2.md`
  - `phase1/p1-s3.md`
  - `phase1/p1-s4.md`
  - `phase1/p1-s5.md`
  - `phase1/p1-s6.md`
  - `phase1/p1-s7.md`
  - `phase2/phase2-lan-validation.md`
  - `phase3/phase3-debian-production.md`

## 4.2 功能完成度/完善度 Gate（强制）

- 每个阶段/子阶段 Gate 评审除了性能数字，还必须包含以下功能指标：
  - 功能清单完成率（目标：100%）
  - API/Schema 契约完成率（目标：100%）
  - 关键异常与降级场景通过率（目标：>= 95%）
  - 可观测性检查项完成率（目标：100%，至少含日志/指标/错误码）
  - UI 关键路径通过率（按阶段定义，目标：100%）
  - 验收文档完整率（目标：100%）

## 4.3 指标口径（SSOT）

- Gate/SLO 的公式、样本数、时间窗、百分位算法与判定规则统一使用 `MyRecall/docs/v3/gate_baseline.md`。
- 本文中的阶段阈值若与 `gate_baseline.md` 不一致，以 `gate_baseline.md` 为准。

## 5. Post-P3 可选演进（不纳入当前承诺范围）

- 评估将 UI 从 Edge 迁移到 Host（仅在 P1/P2/P3 全部达标后启动）。
- 迁移前置条件：
  - Edge API 合同稳定（search/chat/frame lookup 无破坏性变更）
  - Host 侧具备独立发布与回滚能力
  - 可证明迁移不会降低 Chat 引用覆盖率与 Search 一致性
