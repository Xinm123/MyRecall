# MyRecall-v3 路线图（Edge-Centric, vision-only）

- 版本：Draft v0.1
- 日期：2026-02-26
- 节奏原则：每阶段都可独立验收；Edge 必须从 Day 1 参与。

## 0. 已锁定决策（Gate 0，2026-02-26）

1. 001A：对齐策略采用“行为/能力对齐”。  
2. 002A：Chat API 采用 OpenAI-compatible + tool schema。  
3. 003A（覆盖）：Search 完全对齐 screenpipe（vision-only），线上仅 FTS+过滤，舍弃 hybrid。  
4. 004A：Host 采集 accessibility 文本（仅采集，不推理）。  
5. 005A：Edge 支持本地/云端模型并按配置切换（可选 fallback）。  
6. 006A->B：传输安全分阶段升级（P1 token + TLS 可选，P2+ mTLS 强制）。  
7. 007A：P1~P3 页面继续在 Edge，Host 不负责 UI；Host 化仅作为 Post-P3 可选计划。  
8. 008A：功能开发集中在 Phase 1 完成；Phase 2/3 功能冻结，仅做部署与稳定性。  
9. 009A：Phase 1 拆分为串行子阶段（P1-S1~S7），其中 P1-S2/P1-S3 分别为采集/处理，Chat 拆分为多子阶段，端到端验收独立为最后阶段。  
10. 010A：每个阶段与子阶段的验收必须形成详细 Markdown 记录并归档。  
11. 011A：Gate 采用“数值指标适度放宽 + 功能完成度/完善度指标强化”的双轨策略。  
12. 012A：UI Gate 采用“最小可用集”策略（增强可用性验收，不做 UI 重构）。  

## 1. 阶段目标与里程碑

## Phase 1：本机模拟 Edge（进程级隔离）
- 时间：2026-03-02 ~ 2026-03-20
- 目标：将当前单机闭环（client+server）按 Edge-Centric 职责拆为 Host/Edge 两进程，并在本机完成全功能闭环。
- 执行规则：P1-S1 -> P1-S2 -> P1-S3 -> P1-S4 -> P1-S5 -> P1-S6 -> P1-S7 串行推进；每阶段必须先通过验收 Gate。
- P1-S1（基础链路，2026-03-02 ~ 2026-03-05）
  - 交付：
    - Host spool + uploader（幂等、可续传）
    - Edge ingest + queue + processing pipeline 骨架
    - Edge 继续承载现有 Flask 页面（`/`、`/search`、`/timeline`）
    - UI 基线可用（路由可达 + 基础健康态/错误态可见）
  - Gate：
    - 同机断网恢复后可自动重传，且重复上传不重复入库
    - ingest 队列可观测（pending/processing/completed）完整
    - UI 基线路由可达率 = 100%
    - UI 健康态/错误态展示检查通过率 = 100%
- P1-S2（采集，2026-03-06 ~ 2026-03-08）
  - 交付：
    - Host 事件驱动 capture（app switch/click/typing pause/idle）+ idle fallback
    - Host 采集 accessibility 文本并上传
    - Timeline 可见 capture 上传中/已入队状态
  - Gate：
    - 切窗场景 95% capture 在 3 秒内入 Edge 队列
    - 每分钟 300 次事件压测下 Host CPU < 25%，丢包率 < 0.3%
    - 事件触发清单（app switch/click/typing pause/idle）覆盖率 >= 95%
    - 新 capture 在 timeline 可见性通过率 >= 95%
- P1-S3（处理，2026-03-09 ~ 2026-03-11）
  - 交付：
    - Edge AX-first + OCR-fallback（含 `ocr_preferred_apps` 初版）
    - fusion 生成链路稳定运行
    - Frame 详情可见处理来源（AX/OCR fallback）与处理时间戳
  - Gate：
    - AX-first/OCR-fallback 决策日志可追溯率 >= 95%
    - 处理来源字段 UI 展示完整率 = 100%
- P1-S4（检索能力，2026-03-12 ~ 2026-03-13）
  - 交付：
    - `/v1/search` 与 `/v1/search/keyword`（FTS+过滤完整语义）
    - 返回结构包含 frame/citation 关键字段
    - Search 页过滤项与 API 参数 1:1 映射，结果可回溯到 frame/citation
  - Gate：
    - 精确词查询不低于对齐基线
    - Search P95 <= 1.8s（标准时间窗）
    - `/v1/search` 过滤参数契约完成率 = 100%
    - 检索结果引用字段（capture_id/frame_id/timestamp）完整率 = 100%
    - Search UI 过滤项契约映射完成率 = 100%
    - 检索结果点击回溯成功率 >= 95%
- P1-S5（Chat-1 Grounding 与引用，2026-03-14 ~ 2026-03-16）
  - 交付：
    - Chat orchestrator 基础能力（tool-driven retrieval + frame lookup + time range expansion）
    - 引用链路落地（`capture_id/frame_id/timestamp`）
    - Chat 引用在 UI 中可点击并可回溯到 frame/timeline
  - Gate：
    - Chat 引用覆盖率 >= 85%（阶段门槛）
    - 无引用回答可被网关拒绝或标记
    - Chat 工具能力清单（search/frame lookup/time range expansion）完成率 = 100%
    - Chat 引用点击回溯成功率 >= 95%
- P1-S6（Chat-2 路由与流式，2026-03-17 ~ 2026-03-18）
  - 交付：
    - local/cloud 模型路由
    - 流式输出
    - 超时降级与 fallback
    - UI 可见模型路由状态与超时/降级提示
  - Gate：
    - Chat 首 token P95 <= 3.5s
    - 路由切换与超时降级在故障注入下可重复通过
    - 路由切换场景（local->cloud / cloud->local / timeout fallback）覆盖率 = 100%
    - 流式输出协议一致性用例通过率 = 100%
    - 路由与降级状态可见场景覆盖率 = 100%
- P1-S7（端到端验收，2026-03-19 ~ 2026-03-20）
  - 交付：
    - 端到端故障注入与回归报告（仅验收，不新增功能）
    - P1 功能冻结清单（进入 P2/P3 的基线）
    - UI 关键路径回归报告（timeline -> search -> chat -> citation -> frame）
  - Gate：
    - Chat 引用覆盖率 >= 92%
    - TTS P95 <= 12s
    - S1~S6 回归全通过
    - P1 功能清单完成率 = 100%
    - P1 验收记录完整率 = 100%
    - UI 关键路径脚本通过率 = 100%

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

## Phase 3：Debian Edge（生产形态）
- 时间：2026-04-20 ~ 2026-05-29
- 目标：完成生产化部署与运维闭环（功能冻结，不新增功能）。
- 核心交付：
  - Debian 服务化部署（systemd 或容器）
  - 指标面板（ingest lag/queue depth/search latency/chat latency）
  - 灰度升级与回滚策略
- 验收门槛：
  - 7 天稳定运行
  - Chat 引用覆盖率 >= 92%
  - Debian 部署脚本（systemd/容器）成功率 = 100%
  - 回滚演练通过率 = 100%
  - UI 关键路径在 7 天内致命中断次数 = 0

## 2. 工作流分解（按链路）

1. Capture
- P1：完成功能实现（事件驱动 + idle fallback + trigger/capture_id + AX 文本采集）。
- P2/P3：功能冻结，仅做稳定性压测与参数调优。

2. Processing
- P1：完成功能实现（AX-first + OCR-fallback + fusion；Embedding 仅离线实验开关）。
- P2/P3：功能冻结，仅做资源与性能稳定性优化。

3. Search
- P1：完成功能实现（完全对齐 screenpipe vision-only：FTS+过滤 API 与返回契约）。
- P2/P3：不新增检索功能，仅做性能与可观测性优化。

4. Chat
- P1：完成功能实现（tool-driven retrieval + 结构化引用 + local/cloud 路由 + 流式输出 + 超时降级）。
- P2/P3：不新增 Chat 功能，仅做延迟与稳定性治理。

5. UI（Edge 页面）
- P1：完成最小可用 UI 闭环（timeline/search/chat/citation 回溯），不做 UI 重构。
- P2/P3：功能冻结，仅做稳定性与异常可见性治理。

## 2.1 Phase 1 子阶段映射（串行）

- P1-S1：Host 上传链路 + Edge ingest/queue + 页面保持可用
- P1-S2：Capture 事件化能力闭环
- P1-S3：AX-first/OCR-fallback 处理能力闭环
- P1-S4：Search（FTS+过滤）能力闭环
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

## 5. Post-P3 可选演进（不纳入当前承诺范围）

- 评估将 UI 从 Edge 迁移到 Host（仅在 P1/P2/P3 全部达标后启动）。
- 迁移前置条件：
  - Edge API 合同稳定（search/chat/frame lookup 无破坏性变更）
  - Host 侧具备独立发布与回滚能力
  - 可证明迁移不会降低 Chat 引用覆盖率与 Search 一致性
