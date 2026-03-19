---
status: draft
owner: pyw
last_updated: 2026-03-13
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
> 所有已锁定决策的完整内容以 open_questions.md 为唯一事实源。本节不再重复列举。
>
> **OCR-only 收口**: 自 OQ-043 (2026-03-13) 起，v3 主线收口为 OCR-only；`accessibility` 相关 schema 仅保留为 v4 seam，不参与 v3 主线数据流。原 P1-S2b 已转型为 capture completion 阶段。

## 1. 阶段目标与里程碑

### 1.1 API 命名空间迁移策略

| 阶段 | /api/* 行为 |
|------|-------------|
| P1-S1 | `POST /api/upload`=308，其他 legacy GET=301 → /v1/* + [DEPRECATED] 日志 |
| P1-S2~S3 | 持续监控，逐步修改前端/测试/Client 走 /v1/* |
| P1-S4 | 410 Gone 完全废弃 |

### Phase 1：本机模拟 Edge（进程级隔离）
- 时间：2026-03-02 ~ 2026-03-20
- 目标：将当前单机闭环（client+server）按 Edge-Centric 职责拆为 Host/Edge 两进程，并在本机完成全功能闭环。
- 执行规则：P1-S1 -> P1-S2a -> P1-S2a+ -> P1-S2b -> P1-S3 -> P1-S4 -> P1-S5 -> P1-S6 -> P1-S7 串行推进；每阶段必须先通过验收 Gate。`P1-S2b+` 为 S2b 后可选增强，不占主线串行阻塞位。
- 阶段说明：P1-S2a 负责 trigger generation；P1-S2a+ 负责 permission stability closure；P1-S2b 负责 capture completion（trigger routing、monitor-aware coordination、device binding freeze、spool handoff）；P1-S3 起进入 OCR processing 主线。
- P1-S1（基础链路，2026-03-02 ~ 2026-03-05）
  - 交付：
    - Host spool + uploader（磁盘持久化；spool 落盘 JPEG（`.jpg`/`.jpeg` + `.json`，原子写入）；兼容读取历史 `.webp` 仅用于 drain；幂等、可续传）
    - Edge ingest + queue + frame 持久化（JPEG）+ 状态机骨架（不含 AX/OCR）
    - 图片格式主契约统一（主采集/主读取链路 JPEG）
    - Edge 继续承载现有 Flask 页面（`/`、`/search`、`/timeline`）
    - UI 基线可用（路由可达 + 基础健康态/错误态可见）
  - Gate：
    - 同机断网恢复后可自动重传，且重复上传不重复入库
    - ingest 队列可观测（pending/processing/completed/failed）完整
    - 图片格式契约一致性通过：`/v1/ingest` 主契约 `image/jpeg`，`/v1/frames/:frame_id` 返回 `image/jpeg`；兼容输入若启用，需验证入库前转码为 JPEG
    - 对外 API 命名空间一致性通过：验收脚本主流程仅调用 `/v1/*`；旧 `/api/*` 路径仅用于废弃回归检查，且按规则重定向（`POST /api/upload`=308，其余 legacy GET=301）至 `/v1/*` + 记录 `[DEPRECATED]` 日志
    - UI 基线路由可达率 = 100%
    - UI 健康态/错误态展示检查通过率 = 100%

- P1-S2a（事件驱动，2026-03-06 ~ 2026-03-09）
  - Entry prerequisites（允许进入 S2a 开发）：
    - P1-S1 防回归基线通过
    - S2a 文档口径已冻结（roadmap/acceptance/gate_baseline/open_questions/test_strategy 一致）
    - `scripts/acceptance/p1_s2a_local.sh` 已存在且可执行（可在 S2a 阶段内补齐完整能力）
  - 交付：
    - macOS CGEventTap 事件监听（click, app_switch；typing_pause/scroll_stop 推迟至 P2）
    - 触发标记（`capture_trigger` 字段赋值，P1 枚举：`idle/app_switch/manual/click`；`window_focus` 不纳入 P1）
    - 去抖门控（`min_capture_interval_ms=1000`，有意偏离 screenpipe Performance 200ms；Python 安全起点）
- idle fallback（超时触发语义，`idle_capture_interval_ms=30000`，不依赖用户活跃判定）
    - 背压保护（有界通道 + lag 折叠）
    - Grid（`/`）可见 capture 上传中/已入队状态（状态主视图）
    - `/timeline` 仅用于新帧可见与时间定位验证（浏览主视图）
    - **性能监控（强制观测记录）**：`capture_latency_p95` 作为端到端采集性能观测基线（non-blocking）
    - 本机 Gate 验收脚本：`scripts/acceptance/p1_s2a_local.sh`（产出标准证据包）
    - Gate 校验测试文件（本阶段必须新增并通过）：
      - `tests/test_p1_s2a_trigger_coverage.py`
      - `tests/test_p1_s2a_debounce.py`
  - 平台策略：macOS-first（P1 仅实现 macOS，Windows/Linux 推迟 P2）
  - 实现语言：Python（详见 ADR-0013）
  - **频率策略**：P1/P2 维持 1Hz（有意偏离 screenpipe 5Hz），详见 OQ-030
  - Exit Gate（允许进入 S2b）：
    - 每分钟 300 次事件压测下 Capture 丢失率 < 0.3%
    - 触发覆盖 Gate：`trigger_coverage = (covered_trigger_types / 4) × 100% = 100%`（`idle/app_switch/manual/click` 四类均需命中；每类样本 >= 20）
    - 去抖 Gate：同 monitor 连续 `app_switch/click` 入库间隔 < `min_capture_interval_ms`（1000ms，有意偏离）的违规数 = 0
    - 背压 Gate：过载注入窗口（5 分钟）满足 `queue_saturation_ratio <= 10%`（`queue_depth >= 0.9 * queue_capacity` 采样占比）且 `overflow_drop_count = 0`
    - `collapse_trigger_count` 仅作为观测/调试指标记录，不作为 S2a Exit Hard Gate
    - Grid（`/`）新 capture 可见性通过率 >= 95%（状态主视图）
    - Grid 端 `pending -> completed` 状态可见收敛 P95 <= 8s（观测与验收记录必填）
    - `/timeline` 仅用于新帧可见与时间定位验证（浏览主视图）
    - 本机 Gate 验收脚本可执行且证据产物齐全（日志/指标汇总/健康快照/UI 证据索引）
    - Gate 校验测试文件已落地并通过：`tests/test_p1_s2a_trigger_coverage.py`、`tests/test_p1_s2a_debounce.py`

- P1-S2a+（权限稳定性收口，2026-03-10，1-2 天）
  - **说明**：紧接 S2a 的独立收口阶段，非完整功能阶段
  - 范围修订：
    - **必须验证**：Input Monitoring 权限闭环（startup denied / mid-run revoked / recovered）
    - **必须验证**：`startup_not_determined` 与 `stale_permission_state` 的 health 语义
    - **可选验证**：Accessibility 权限降级行为（CoreGraphics 已满足基础需求）
    - **不在范围**：Browser URL、AX tree walk
  - 依赖：P1-S2a Pass
  - Gate：
    - Input Monitoring 异常闭环通过率 = 100%
    - /v1/health 权限状态机语义正确率 = 100%
    - S2a+ Gate 证据齐全（日志/health 快照/UI 证据/环境上下文）
  - 交付：
    - `docs/v3/acceptance/phase1/p1-s2a-plus.md` 完成并 Pass
    - `tests/test_p1_s2a_plus_permission_fsm.py` 落地并通过
    - 独立的 S2a+ 本机 Gate 执行入口落地
    - S2b Entry Gate 前置条件满足

- P1-S2b（Capture Completion / Monitor-Aware Coordination，2026-03-11 ~ 2026-03-13）
  - 交付：
    - Trigger routing 语义冻结：`specific-monitor` / `active-monitor` / `per-monitor-idle` / `coordinator-defined` 四类触发的目标 monitor 归属规则明确
    - TriggerSource -> TriggerRouter -> CaptureCoordinator -> MonitorWorker[target] 拓扑收口；`MonitorWorker` 只执行 monitor-bound capture work，不承担 fan-out 策略
    - `device_name` 绑定语义冻结：由实际完成截图的 monitor capture worker 负责最终绑定，保证与截图 monitor 同 cycle
    - monitor topology rebuild：monitor 增减、`primary_monitor_only` 变化、worker 集合重建与分区状态恢复
    - `focused_context = {app_name, window_name}` 与 `device_name` 的 capture completion 语义冻结；~~`browser_url`~~ P1 不采集
    - spool handoff correctness：capture completion 后入 spool 的 metadata、图像与 `capture_trigger`/`device_name` 一致
  - 平台策略：macOS-only（P1 仅实现 macOS，Windows/Linux 推迟 P2）
  - 实现语言：Python（详见 ADR-0013）
  - 依赖：P1-S2a 的触发机制 + P1-S2a+ 的权限稳定性收口（S2b 在事件触发后完成 monitor-aware capture coordination）
  - Gate：
    - trigger -> target monitor routing correctness = 100%（click/app_switch/manual/idle 的目标 monitor 行为与冻结语义一致）
    - `device_name` binding correctness = 100%（capture metadata 中 `device_name` 与实际截图 monitor 一致）
    - single-monitor trigger duplicate capture rate = 0（同一 monitor 在同一 user action / `min_capture_interval_ms` 窗口内不得产生重复持久化 capture）
    - monitor topology rebuild correctness = 100%（monitor 增减、不可用、切换 primary 后仍能恢复正确分发）
    - `capture_to_ingest_latency_ms`：Soft KPI（记录 P50/P90/P95/P99，按 `device_name` 分桶）
    - Entry prerequisites：P1-S2a+ 权限稳定性收口通过
    - 窗口有效性：Hard Gate 仅使用无 Host/Edge 重启的连续窗口；若窗口内发生 Host 或 Edge 重启则标记 `broken_window=true`，该窗口仅用于观测
  - Exit to：P1-S3（主线必经）；P1-S2b+（可选增强）

- P1-S2b+（感知哈希实现，2026-03-13 ~ 2026-03-14）
  - **说明**：S2b 之后的可选增强阶段；用于实现相似帧丢弃以节省存储空间，不阻塞 OCR-only 主线进入 S3
  - 范围：
    - 感知哈希（simhash）计算实现（PHash 算法）
    - **相似帧丢弃**：Host Spool 入队前检测相似性，相似帧跳过入库以节省存储空间
    - SimhashCache：Host 端内存缓存，按 device_name 分组存储最近 1 帧
    - Spool 层集成：capture 入队时计算 simhash 并判定是否丢弃
    - `frames.simhash` 字段写入（仅入库帧；schema 已预留）
    - 相似帧检测逻辑：基于汉明距离的相似性判定
  - 不在范围：
    - **不修改 S2b 已冻结语义**：routing、device_name binding、topology 等核心逻辑不变
    - **不替代 capture_id 幂等**：`capture_id` 仍是 Edge 端主去重键，simhash 为 Host 端内容级辅助
    - **不做 Edge 端去重**：simhash 丢弃仅发生在 Host 端
    - **引入 SciPy 依赖**：用于 PHash DCT 计算（性能不作为 Hard Gate）
  - 平台策略：macOS-only（P1 仅实现 macOS；Windows/Linux 推迟 P2）
  - 依赖：P1-S2b Pass
  - Hard Gate（仅阶段内自洽，不构成 S3 Entry Gate）：
    - simhash 计算实现率 = 100%
    - spool 集成成功率 = 100%
    - 相似帧检测准确率 >= 95%
    - 相似帧丢弃正确率 >= 95%
    - 不相似帧误丢弃率 <= 5%
  - Soft KPI（观测记录，non-blocking）：
    - 计算耗时 P50/P90/P95/P99 分布
    - 内存占用增加
    - capture latency 增加
    - 存储节省率（丢弃帧数 / 总触发帧数）
  - 交付：
    - `docs/v3/acceptance/phase1/p1-s2b-plus.md` 完成并 Pass
    - `tests/test_p1_s2b_plus_simhash.py` 落地并通过
    - 相似帧丢弃逻辑可用
  - 与 S3 关系：S3 主线只依赖 S2b Pass；S2b+ 若执行，不得反向改变 S2b/S3 的 OCR-only 主契约

- P1-S3（处理，2026-03-15 ~ 2026-03-17）✅ **Pass**
  - 验收记录：[`p1-s3.md`](acceptance/phase1/p1-s3.md)
  - 版本/提交：fn-3-0.99 (4c4563c)
  - 交付：
    - Edge OCR processing（RapidOCR，single-engine policy）
    - OCR 成功 → `ocr_text` 表；`frames.text_source='ocr'`
    - OCR 失败语义冻结：失败帧进入 `failed`，不得伪造 UI/accessibility 结果
    - S2b->S3 handoff 语义冻结：S3 仅依赖截图、`capture_trigger`、`device_name`、`focused_context` 等 capture-completion 产物
    - 上下文字段语义冻结：`focused_context = {app_name, window_name}`；`browser_url` 在 P1 保持 reserved/NULL，不作为 S2b->S3 active handoff 字段；`device_name` 为 same-cycle 的实际采样 monitor 绑定字段
    - 索引时零 AI 增强：不生成 `caption/keywords/fusion_text`，不写入 `ocr_text_embeddings`
    - Frame 详情可见 OCR 处理来源与处理时间戳（在 Grid `/` 的 frame 卡片下方呈现，不新增 `/frame/:id` 页面）
  - Gate：
    - OCR 成功帧写入 `ocr_text` 的正确率 = 100%
    - `frames.text_source='ocr'` 标记正确率 = 100%
    - OCR 失败帧 `failed` 语义正确率 = 100%
    - OCR 路径验收口径固定为 RapidOCR（P1 不做跨引擎归一化）
    - 索引时零 AI 增强检查通过率 = 100%（禁用字段/写入路径回归为 0）
    - 处理来源字段 UI 展示完整率 = 100%
- P1-S4（检索能力，2026-03-16 ~ 2026-03-18）
  - 交付：
    - `/v1/search`（含 keyword 检索语义，FTS+过滤完整能力）
    - OCR-only 搜索路径：FTS + 元数据过滤 + OCR/frame citation 返回结构
    - `focused`（若启用）、时间范围、应用/窗口过滤在 OCR 结果上正确生效；`browser_url` 在 P1 仅保留兼容参数，不作为 Hard Gate 过滤能力
    - 返回结构包含 frame/citation 关键字段；v3 主线不暴露 UI/accessibility result type
    - Search 页过滤项与 API 参数 1:1 映射，结果可回溯到 frame/citation
  - Gate：
    - 观测 KPI：Search P95 记录实际分布（P1 阶段暂不设硬性阈值，详见 [gate_baseline.md#35-search-p95p1-s4](./gate_baseline.md#35-search-p95p1-s4)；在 P1-S7 前根据实测数据确定最终目标）
    - `/v1/search` 过滤参数契约完成率 = 100%
    - OCR 搜索 SQL/返回结构一致性 = 100%
    - `focused` 过滤正确性 = 100%
    - OCR 检索结果引用字段完整率 = 100%（`frame_id`/`timestamp`，Hard Gate）
    - 观测 KPI（non-blocking）：OCR 检索结果 `capture_id` 覆盖率目标 >= 99%（未达标需提交整改动作）
    - Search UI 过滤项契约映射完成率 = 100%
    - 检索结果点击回溯成功率 >= 95%
- P1-S5（Chat-1 Grounding 与引用，2026-03-19 ~ 2026-03-21）
  - 交付：
    - Pi Sidecar 基础能力：PiProcess（subprocess wrapper）、PiManager（singleton 进程管理）、protocol.py（Pi JSON Lines ↔ SSE 桥接）
    - `myrecall-search` SKILL.md（tool-driven retrieval，对标 screenpipe `screenpipe-search`）
    - `/v1/chat` SSE streaming endpoint（Flask + threading，DP-1=A）
    - `chat_messages` 持久化（session history injection，DP-3=A）
    - Chat UI minimal（Alpine.js + EventSource）
    - 引用通过提示词与 Skill 显式要求输出 deep link：
      - OCR 结果：`myrecall://frame/{frame_id}`（点击后统一落到 `/timeline` 定位对应帧）
      - `frame_id`/`timestamp` 必须来自检索结果且禁止伪造（DA-8=A）
  - Gate：
    - Chat 工具能力清单（via myrecall-search SKILL.md）完成率 = 100%
    - Chat 引用点击回溯成功率 >= 95%
    - 观测 KPI（non-blocking）：Chat 引用覆盖率目标 >= 85%，未达标需提交整改动作
- P1-S6（Chat-2 路由与流式，2026-03-22 ~ 2026-03-23）
  - 交付：
    - Provider/model 路由（通过 Pi `--provider`/`--model` + `models.json` 配置，UI 配置页面切换）
    - Pi 事件流式输出（SSE 透传 Pi 原生 11 种事件类型）
    - PiManager watchdog（idle timeout、crash auto-restart、orphan cleanup）
    - Provider timeout 处理（180s 请求 watchdog → timeout error；不做 auto-fallback；超时不强制 abort，保留用户手动中断）
    - UI 可见 provider/model badge + timeout/error notification + Pi 健康状态
  - Gate：
    - Chat 系统可用率 >= 98%（仅系统错误计入失败；provider 5xx/429、180s timeout 不计入失败）
    - 观测 KPI（non-blocking）：Chat 完成率目标 >= 95%；Chat 首 token P95 <= 3.5s
    - Provider 切换可重复通过
    - 路由切换场景覆盖率 = 100%（provider 切换 + timeout 错误，不含 auto-fallback）
    - 流式输出协议一致性用例通过率 = 100%
    - 路由与 timeout 状态可见场景覆盖率 = 100%
- P1-S7（端到端验收，2026-03-24 ~ 2026-03-25）
  - 交付：
    - 端到端故障注入与回归报告（仅验收，不新增功能）
    - P1 功能冻结清单（进入 P2/P3 的基线）
    - UI 关键路径回归报告（timeline -> search -> chat -> citation -> frame）
  - Gate：
    - TTS（OCR路径）P95 <= 15s（Soft KPI，观测记录）
    - S1~S6 的 Hard Gate/SLO Gate 回归全通过（Soft KPI 仅记录偏差与整改动作）
    - P1 功能清单完成率 = 100%
    - P1 验收记录完整率 = 100%
    - UI 关键路径脚本通过率 = 100%
    - 观测 KPI（non-blocking）：Chat 引用覆盖率目标 >= 92%，Stretch >= 95%
    - 观测 KPI（non-blocking）：Capture 丢失率 <= 0.1%

### Phase 2：LAN 双机（另一台 Mac 作为 Edge）
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

### Phase 3：Debian Edge（生产形态）
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
- P1-S2a：事件驱动框架（macOS CGEventTap + 触发标记 + 去抖 + 背压保护）
- P1-S2b：trigger routing + monitor-aware capture coordination + `device_name`/context freeze + spool handoff
- P2/P3：Windows/Linux 事件监听与 capture coordination，功能冻结，仅做稳定性压测与参数调优。

2. Processing
- P1：完成功能实现（OCR-only；`ocr_text` 持久化；`frames.text_source='ocr'`；仅存储原始文本，不做索引时 AI 增强；Embedding 仅离线实验表）。
- P2/P3：功能冻结，仅做资源与性能稳定性优化。

3. Search
- P1：完成功能实现（FTS+过滤 API 与返回契约；OCR-only 搜索与 frame citation 回溯）。
- P2/P3：不新增检索功能，仅做性能与可观测性优化。

4. Chat
- P1：完成功能实现（Pi Sidecar + SKILL.md tool-driven retrieval + 提示词驱动引用 + provider/model 路由 + 流式输出 + timeout 处理）。
- P2/P3：不新增 Chat 功能，仅做延迟与稳定性治理。

5. UI（Edge 页面）
- P1：完成最小可用 UI 闭环（timeline/search/chat/citation 回溯），不做 UI 重构。
- P2/P3：功能冻结，仅做稳定性与异常可见性治理。

## 2.1 Phase 1 子阶段映射（串行）

- P1-S1：Host 上传链路 + Edge ingest/queue + 页面保持可用
- P1-S2a：事件驱动 capture（macOS-only，Python 实现）
- P1-S2a+：权限稳定性收口（Input Monitoring FSM、health 语义、受控降级/自动恢复）
- P1-S2b：Capture Completion / Monitor-Aware Coordination（macOS-only，Python 实现）
- P1-S2b+：感知哈希实现（可选增强阶段；不阻塞 S3 主线）
- P1-S3：OCR-only processing 能力闭环
- P1-S4：Search（FTS+过滤，OCR-only）能力闭环
- P1-S5：Chat Grounding 与引用闭环
- P1-S6：Chat 路由/流式/降级闭环
- P1-S7：端到端验收（仅验收，不新增功能）
- 说明：各子阶段都包含对应最小 UI Gate（可用性、可解释性、可恢复性）。

## 3. 风险清单（按优先级）

- P0：Edge 挂掉导致 Host 长时间积压。
- P0：Chat 无引用导致可用性失败。
- P0：Phase 1 范围膨胀导致里程碑延期。
- P1：事件驱动策略过激导致采集风暴。
- P1：trigger routing / monitor ownership 设计错误导致错 monitor capture 或重复 capture。
- P1：OCR 处理性能不达标导致 TTS（OCR路径）超过 15s，影响 P1-S7 观测指标。
- P1：语义型查询能力下降导致 Chat 检索上下文不充分。
- P1：macOS 权限瞬态失败导致 Gate 误判（需用 Python + pyobjc 实现 screenpipe permissions.rs 的瞬态检测逻辑）。
- P1：权限被拒绝/运行中撤销后未进入受控降级，导致“服务存活但采集不可用”不可观测。

## 4. 里程碑退出条件（DoD）

- 每个阶段都必须提供：
  - 功能验收报告
  - 故障注入报告
  - 性能指标报告
  - 权限异常演练报告（拒绝/撤销/恢复）
  - 未决问题转入 [open_questions.md](open_questions.md)

## 4.1 验收记录规范（强制，Markdown）

- 规则：
  - 每个阶段（Phase）与每个子阶段（P1-Sx）在 Gate 判定前，必须先完成对应 Markdown 验收记录。
  - 验收记录未完成，视为 Gate 未通过。
  - 验收记录必须包含：目标范围、输入版本、测试环境、测试步骤、指标结果、结论（Pass/Fail）、风险与后续动作。
- 归档目录：[acceptance/](./acceptance/)
- 统一模板：[acceptance/TEMPLATE.md](./acceptance/TEMPLATE.md)
- 文件映射（固定）：
  - `phase1/p1-s1.md`
  - `phase1/p1-s2a.md`
  - `phase1/p1-s2a-plus.md`
  - `phase1/p1-s2b.md`
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
  - 关键异常与降级场景通过率（目标：>= 95%；仅覆盖本阶段语义拥有的 failure classes）
  - 权限状态机与恢复闭环通过率（目标：100%；owner=采集能力阶段，P1-S2b 前必须关闭）
  - 可观测性检查项完成率（目标：100%，至少含日志/指标/错误码）
  - UI 关键路径通过率（按阶段定义，目标：100%）
  - 验收文档完整率（目标：100%）

### 4.4 权限稳定性阶段边界（P1/P2）

- P1 目标：
  - 建立权限状态机（`granted/transient_failure/denied_or_revoked/recovering`）与参数闭环（2 fail / 3 success / 300s cooldown / 10s poll）。
  - 明确受控降级与恢复路径，并在 `/v1/health` 暴露权限状态。
  - Dev（Terminal）模式允许用于开发验证，但不作为长期稳定运行承诺。
- P2 目标：
  - 引入固定签名身份的稳定运行模型，降低 TCC 身份漂移风险。
  - 完成重启/升级/权限撤销后的 soak 验证并固化运行手册。

## 4.3 指标口径（SSOT）

- Gate/SLO 的公式、样本数、时间窗、百分位算法与判定规则统一使用 [gate_baseline.md](./gate_baseline.md)。
- 本文中的阶段阈值若与 [gate_baseline.md](gate_baseline.md) 不一致，以 [gate_baseline.md](gate_baseline.md) 为准。

## 5. Post-P3 可选演进（不纳入当前承诺范围）

- 评估将 UI 从 Edge 迁移到 Host（仅在 P1/P2/P3 全部达标后启动）。
- 迁移前置条件：
  - Edge API 合同稳定（search/chat/frame lookup 无破坏性变更）
  - Host 侧具备独立发布与回滚能力
  - 可证明迁移不会降低 Chat 引用覆盖率与 Search 一致性
