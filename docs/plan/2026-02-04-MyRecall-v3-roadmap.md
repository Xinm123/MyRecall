# MyRecall-v3 Roadmap（借鉴 screenpipe：体验/检索/Chat 思路）

> 生成日期：2026-02-04  
> 状态：Proposed（仅落盘文档，暂不实现）  
> 目标读者：MyRecall 维护者/开发者（希望从 screenpipe 借鉴工程与产品体验）

## 1. 背景与目标

MyRecall 与 screenpipe 都是 **local-first 数字记忆层**（capture → index → search → timeline/chat），但侧重点不同：
- MyRecall：截图 + Web UI + 混合检索（FTS + 向量 + rerank），更“搜索引擎化”
- screenpipe：桌面产品化 + 时间轴流式体验 + tool-call chat + 多模态（音频/UI events）生态

**v3 的目标（MVP 口径）**
- 体验：timeline 从“slider 单图”升级为“可滚动/可分页/可增量”的可用体验
- 检索：keyword 搜索具备高亮/定位的基础设施（最小先做 snippet/highlight）
- Chat：引入 tool-call 思路（强约束截断/限额/超时），把“搜索”升级为“总结/问答”
- 稳定性：SQLite 在写入/读取并存时更稳（busy_timeout/WAL/重试策略），减少锁冲突

**v3 明确不做（进入 v3.1+）**
- 视频分片 + 帧索引 + 按需抽帧缓存
- 音频采集 + STT + 说话人/跨设备去重
- UI events（accessibility/input）
- WS 事件总线/插件生态、云同步

## 2. Source of Truth（对齐入口）

- MyRecall 端到端数据流：`MyRecall/docs/MyRecall_V2_Analysis.md`
- MyRecall 对比分析与借鉴点：
  - 主文：`MyRecall/docs/plan/MyRecall-vs-screenpipe.md`
  - 当日快照：`MyRecall/docs/plan/2026-02-04-MyRecall-vs-screenpipe.md`
- screenpipe 数据流（对齐思路，不复制实现）：`screenpipe/docs/dataflow-pipeline.zh-en.md`
- MyRecall 关键实现入口：
  - API：`MyRecall/openrecall/server/api.py`
  - Worker：`MyRecall/openrecall/server/worker.py`
  - 搜索引擎：`MyRecall/openrecall/server/search/engine.py`
  - FTS/SQLite：`MyRecall/openrecall/server/database/sql.py`
  - Web UI：`MyRecall/openrecall/server/templates/*`

## 3. 已确认的产品/技术决策（Decision complete）

- 总路线：**混合渐进**
  - 继续以“截图 + Web UI + 混合检索”为主线
  - 分阶段吸收 screenpipe 的工程/体验/Chat 思路
- MVP 优先：**体验 + 检索 + Chat**
- Timeline 增量：**HTTP Polling**（基于现有 `/api/memories/latest?since=` 或新增 v3 frames 接口）
- 时间跨度：**8 周**（4 个 2 周阶段）

## 4. 借鉴清单（screenpipe → MyRecall-v3）

### 4.1 Must-have（v3 必做）
1) Timeline 渐进加载范式（initial load + 分页/滚动 + 增量刷新 + 前端去重/缓冲）
2) Keyword 搜索的高亮/定位基础：`snippet/highlight`（positions 可后置）
3) Chat 的 tool-call 设计安全阀：limit 上限、单条截断、总长度上限、超时、tool-call 次数上限
4) SQLite 稳定性：WAL/busy_timeout/写入重试等“抗锁”策略（按 Python 语境实现）

### 4.2 Should-have（v3 应做）
1) 新增 v3 API（不破坏旧 UI/Client）：统一检索入口 + frames 分页入口
2) 指标体系（Metrics）：把体验/检索/Chat/稳定性变成可衡量的 Scorecard

### 4.3 Could-have（视风险/时间）
- 更强 filters：app/window/time range 作为一级能力（类似 screenpipe `/search` filters）
- Search → Timeline → Chat 的联动（点击结果跳时间轴并预填上下文）

### 4.4 Not in v3（明确不做）
- 视频分片/音频/UI events/WS events bus/云同步（全部进入 v3.1+）

## 5. Roadmap（8 周 / 4 阶段）

| 阶段 | 时间 | 主题 | 主要交付物 | 验收摘要 |
|---|---:|---|---|---|
| Phase 0 | Week 1-2 | Foundation | v3 API 骨架、SQLite 稳定性策略、frames endpoint、基础测试 | 无锁冲突回归；frames 可分页/增量 |
| Phase 1 | Week 3-4 | Timeline + Keyword | timeline-v3 UI（滚动/分页/增量）、keyword 高亮/snippet、跳转联动 | timeline 可用；keyword 高亮正确 |
| Phase 2 | Week 5-6 | Chat + 统一检索 | `/api/v3/search` + filters；`/api/v3/chat`（tool-call + 限额）+ 简单 UI | Chat 可回答“昨天做了啥”并带引用 |
| Phase 3 | Week 7-8 | Hardening + Metrics | Scorecard、回归清单、最小 eval 方案/脚本框架、错误处理与文档收敛 | 可衡量、可回归、可持续迭代 |

> 每个阶段的执行计划见：
> - `MyRecall/docs/plan/2026-02-04-MyRecall-v3-phase0-foundation.md`
> - `MyRecall/docs/plan/2026-02-04-MyRecall-v3-phase1-timeline-search.md`
> - `MyRecall/docs/plan/2026-02-04-MyRecall-v3-phase2-chat.md`
> - `MyRecall/docs/plan/2026-02-04-MyRecall-v3-phase3-hardening-metrics.md`

## 6. 风险与应对

- SQLite 锁冲突（写入 worker 与读 timeline/search 并存）
  - 应对：WAL + busy_timeout + 写入重试 + 连接策略一致化
- 数据规模增长导致 timeline/search 变慢
  - 应对：分页/增量；limit 上限；必要字段索引；UI 懒加载
- Chat 上下文爆炸（OCR 文本过长）
  - 应对：tool-call 强约束截断/限额/超时；“建议时间范围”策略
- 隐私与远程暴露风险
  - v3 默认本机：`OPENRECALL_HOST=127.0.0.1`；远程暴露另开安全门槛（Phase 3 文档明确）

## 7. v3.1+ Backlog（后续版本候选）

1) 视频分片 + 帧索引 + 按需抽帧缓存（screenpipe 的核心形态）
2) 音频采集 + STT + 说话人 + 去重（会议回忆）
3) UI events（可选、强隐私开关）
4) WS 事件总线、插件/MCP 生态
5) 云同步（zero-knowledge）

